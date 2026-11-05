"""M3 A12: synthetic-only, no Palace artifacts, saved edits or native solver."""
from __future__ import annotations

import copy
import json
import math

import pytest

from sqe_studio.adapters import scqubits_adapter
from sqe_studio.contracts import fresh_project
from sqe_studio.interop.transmon_quantum_preflight import (
    DECLARATION_SCHEMA, PREFLIGHT_SCHEMA, TransmonPreflightBlocked,
    build_independent_transmon_preflight,
)


def manual():
    return {
        'schema': DECLARATION_SCHEMA, 'model': 'Transmon',
        'source': 'independent',
        'parameters': {'EJ': 15.0, 'EC': .25, 'ng': 0.0, 'ncut': 30},
        'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
        'levels': 5,
    }


def assert_blocked(candidate, code=None):
    with pytest.raises(TransmonPreflightBlocked) as caught:
        build_independent_transmon_preflight(candidate)
    if code is not None:
        assert caught.value.code == code


def test_valid_study_is_unsaved_adapter_compatible_without_any_science_authorization(monkeypatch):
    # Neither public solver entrypoint nor installed scqubits is called.
    def forbidden(*args, **kwargs):
        raise AssertionError('Solver execution or native dependency forbidden')
    monkeypatch.setattr(scqubits_adapter, 'run', forbidden)
    candidate = manual()
    original = copy.deepcopy(candidate)
    result = build_independent_transmon_preflight(candidate)
    assert candidate == original
    assert result['schema'] == PREFLIGHT_SCHEMA
    assert result['status'] == 'VALID_INDEPENDENT_RESEARCH_PREFLIGHT_ONLY'
    assert result['em_ec_transfer'] == 'BLOCKED'
    assert result['em_to_hamiltonian'] == 'BLOCKED'
    assert result['energy_convention'] == 'E_OVER_H_GHz'
    assert result['scientific_authorization'].startswith('BLOCKED_')
    assert result['fabrication'] == 'HOLD'
    assert result['saved_study'] == 'NOT_CREATED'
    assert result['solver_execution'] == 'NOT_EXECUTED'
    assert result['parameter_provenance'] == 'UNVERIFIED_DESIGNER_DECLARATION_ONLY'
    template = result['study_template']
    assert set(template) == {'engine', 'kind', 'inputs'}
    assert (template['engine'], template['kind']) == ('scqubits', 'quantum_spectrum')
    assert template['inputs'] == {k: original[k] for k in (
        'source', 'model', 'parameters', 'parameter_units', 'levels')}
    parsed = scqubits_adapter._spec(template['inputs'], fresh_project('M3 synthetic', 'transmon'))
    assert parsed['source'] == 'independent'
    assert parsed['model'] == 'Transmon'
    assert parsed['groups'][0]['parameters']['EC'] == .25
    assert parsed['groups'][0]['parameters']['truncated_dim'] == 6
    assert 'context_sha256' not in template['inputs']  # A99 must bind on save
    assert 'input_sha256' not in template['inputs']
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('ej,ec,ng,ncut,levels', [
    (0.01, 0.01, -10, 3, 7), (1000, 1000, 10, 80, 12),
    (20, 0.2, -0.5, 4, 9), (15.4, 0.22, .4, 3, 2),
])
def test_valid_bounds_agree_with_existing_adapter(ej, ec, ng, ncut, levels):
    candidate = manual()
    candidate['parameters'].update(EJ=ej, EC=ec, ng=ng, ncut=ncut)
    candidate['levels'] = levels
    result = build_independent_transmon_preflight(candidate)
    parsed = scqubits_adapter._spec(result['study_template']['inputs'],
                                    fresh_project('Synthetic', 'transmon'))
    assert parsed['levels'] == levels
    assert parsed['groups'][0]['parameters']['ncut'] == ncut


@pytest.mark.parametrize('field,raw', [
    ('EJ', 0), ('EJ', -1), ('EC', 0), ('EC', -.001),
    ('EJ', 1000.000001), ('EC', 1001),
    ('EJ', float('nan')), ('EC', float('nan')),
    ('EJ', float('inf')), ('EC', float('-inf')),
    ('ng', float('nan')), ('ng', float('inf')),
    ('ng', 10.00001), ('ng', -10.00001),
    ('EJ', True), ('EC', False), ('ng', True),
    ('EJ', '15 GHz'), ('EC', '0.25'), ('EC', {'ec_over_h_hz_matrix_only': 0.25}),
    ('EC', [0.25]), ('EJ', 10**400),
])
def test_invalid_energy_and_offset_values_fail_closed(field, raw):
    d = manual()
    d['parameters'][field] = raw
    assert_blocked(d)


@pytest.mark.parametrize('field,raw', [
    ('ncut', 2), ('ncut', 81), ('ncut', 0), ('ncut', -10),
    ('ncut', 3.0), ('ncut', True), ('ncut', float('nan')),
    ('levels', 1), ('levels', 13), ('levels', 2.0),
    ('levels', True), ('levels', float('inf')),
])
def test_bad_dimensions_rejected(field, raw):
    d = manual()
    if field == 'levels': d['levels'] = raw
    else: d['parameters'][field] = raw
    assert_blocked(d, 'INVALID_DIMENSION')


def test_levels_cannot_exceed_charge_basis_even_if_below_max_levels():
    d = manual()
    d['parameters']['ncut'] = 3
    d['levels'] = 8
    assert_blocked(d, 'INVALID_DIMENSION')


@pytest.mark.parametrize('key,bad', [
    ('EJ', 'MHz'), ('EJ', 'J'), ('EC', 'F'), ('EC', 'GHz E/h from Palace'),
    ('EC', 'MHz'), ('ng', 'GHz'), ('ng', '1'), ('ncut', 'GHz'),
    ('EC', None), ('EJ', True), ('ncut', 1),
])
def test_wrong_units_never_converted(key, bad):
    d = manual()
    d['parameter_units'][key] = bad
    assert_blocked(d, 'INVALID_UNITS')


@pytest.mark.parametrize('change', [
    lambda d: d['parameter_units'].pop('EC'),
    lambda d: d['parameter_units'].update(extra='GHz'),
    lambda d: d.pop('parameter_units'),
    lambda d: d['parameters'].pop('EC'),
    lambda d: d['parameters'].update(EJmax=15),
    lambda d: d.update(parameters=None),
    lambda d: d.update(parameters=[]),
    lambda d: d.update(parameter_units='GHz'),
])
def test_mismatched_parameter_and_unit_sets_are_blocked(change):
    d = manual(); change(d)
    assert_blocked(d)


@pytest.mark.parametrize('source', [
    'em', 'palace', 'palace.capacitance_matrix', 'EM_DERIVED', 'engine-derived',
    'scqubits', None, True, 'independent ', 'INDEPENDENT',
])
def test_em_derived_or_mismatched_source_is_blocked(source):
    d = manual(); d['source'] = source
    assert_blocked(d, 'EM_DERIVATION_BLOCKED')


@pytest.mark.parametrize('model', ['Fluxonium', 'TunableTransmon', 'Composite',
                                  'transmon', None, 'TransmonPocket', True])
def test_only_scqubits_standalone_transmon_model_is_supported(model):
    d = manual(); d['model'] = model
    assert_blocked(d, 'UNSUPPORTED_MODEL')


@pytest.mark.parametrize('addition', [
    {'em_artifact': {'ec_over_h_hz_matrix_only': 0.25}},
    {'derived_from': 'Palace'},
    {'em_ec_transfer': 'APPROVED'},
    {'review': {'status': 'APPROVED', 'expert': 'self'}},
    {'approved': True},
    {'independent_review': 'PASS'},
    {'fabrication': 'APPROVED'},
    {'source_lineage': {'revision_digest': '1'*64}},
    {'project_revision': 'stale-old-revision'},
    {'context_sha256': '1'*64},
    {'input_sha256': '0'*64},
    {'study_id': 'this-is-an-EM-result'},
    {'sweep': {'parameter': 'EC'}},
    {'convergence': {'enabled': True}},
    {'subsystems': []},
    {'truncated_dim': 7},
])
def test_fake_approval_stale_revision_and_em_passthrough_are_rejected(addition):
    d = manual(); d.update(addition)
    assert_blocked(d, 'UNTRUSTED_INPUT_SHAPE')


def test_full_palace_capacitance_screen_cannot_be_recycled():
    from sqe_studio.interop.transmon_reduction import CapacitanceDecision
    screen = CapacitanceDecision('NUMERICAL_SCREEN_ONLY', 'unreviewed', None,
                                 {'ec_over_h_hz_matrix_only': 250_000_000})
    assert_blocked(screen.as_dict(), 'UNTRUSTED_INPUT_SHAPE')
    d = manual()
    d['parameters']['EC'] = screen.numerical_preview
    assert_blocked(d, 'INVALID_PARAMETER')
    d = manual(); d['parameters']['EC'] = screen.numerical_preview['ec_over_h_hz_matrix_only']
    d['source'] = 'em'
    assert_blocked(d, 'EM_DERIVATION_BLOCKED')


@pytest.mark.parametrize('schema', ['sqe.capacitance-reduction-decision.a12.v1',
                                   'sqe.saved-transmon-capacitance-selection.v1',
                                   'sqe.independent-transmon-declaration.a12.v0', None, True])
def test_wrong_schema_is_rejected_including_mislabelled_saved_studies(schema):
    d = manual(); d['schema'] = schema
    assert_blocked(d, 'UNTRUSTED_INPUT_SHAPE')


def test_no_mutation_or_alias_to_input_or_between_generated_studies():
    d = manual()
    before = copy.deepcopy(d)
    one = build_independent_transmon_preflight(d)
    two = build_independent_transmon_preflight(d)
    one['study_template']['inputs']['parameters']['EC'] = 1000
    one['study_template']['inputs']['parameter_units']['EC'] = 'J'
    assert d == before
    assert two['study_template']['inputs']['parameters']['EC'] == .25
    assert two['study_template']['inputs']['parameter_units']['EC'] == 'GHz'


def test_unexpected_outer_objects_and_extra_science_metadata_are_rejected():
    for value in (None, [], 'source=independent', 15, (manual(),)):
        assert_blocked(value, 'INVALID_DECLARATION')
    d = manual(); d['parameters']['EC'] = {'source':'Palace', 'value':.25,'unit':'GHz'}
    assert_blocked(d, 'INVALID_PARAMETER')
