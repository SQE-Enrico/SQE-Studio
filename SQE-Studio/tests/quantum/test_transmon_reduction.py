"""M1 synthetic/analytic mathematics only. NONE of these fixtures are Palace data."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

import pytest

from sqe_studio.interop.transmon_reduction import (
    ReviewedTopologyDeclaration, assess_transmon_capacitance,
)

FF = 1e-15
SOURCE = {
    'revision_digest': '0' * 64, 'study_id': 'native-study-001',
    'manifest_sha256': '1' * 64, 'terminal_csv_sha256': '2' * 64,
    'deck_sha256': '3' * 64, 'mesh_sha256': '4' * 64,
}
JUNCTION = 'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'


def fixture(matrix=None, labels=None):
    return {
        'schema': 'sqe.capacitance-topology.v1',
        'scientific_status': 'UNREVIEWED_TOPOLOGY',
        'source': dict(SOURCE),
        'terminal_labels': labels or ['a', 'b'],
        'maxwell_matrix_f': matrix or [[100 * FF, -40 * FF], [-40 * FF, 80 * FF]],
        'reference_ground': {'status': 'UNREVIEWED', 'native_group_ids': [5]},
        'proposed_pair': {'island_a': 'a', 'island_b': 'b'},
        'other_terminal_policy': {'fixed_zero': [], 'floating_zero_charge': []},
        'review': {'status': 'NOT_APPROVED', 'record_sha256': None},
    }


def call(payload=None, **overrides):
    t = fixture() if payload is None else payload
    kw = dict(expected_source=deepcopy(SOURCE),
              expected_terminal_labels=tuple(t['terminal_labels']),
              expected_ground_group_ids=(5,),
              junction_capacitance_assumption=JUNCTION)
    kw.update(overrides)
    return assess_transmon_capacitance(t, **kw)


def result(payload=None, **overrides):
    r = call(payload, **overrides)
    assert r.status == 'NUMERICAL_SCREEN_ONLY', r.as_dict()
    assert r.as_dict()['transfer_status'].startswith('BLOCKED_')
    assert r.as_dict()['scqubits_parameter'] is None
    assert r.as_dict()['ej_over_h_hz'] is None
    return r.numerical_preview


def blocked(payload=None, code=None, **overrides):
    d = call(payload, **overrides)
    assert d.status.startswith('BLOCKED_'), d.as_dict()
    if code is not None:
        assert d.status == code, d.as_dict()
    assert d.numerical_preview is None
    assert d.as_dict()['scqubits_parameter'] is None
    return d


def test_two_island_analytic_transfer_charge_mode_and_exact_si_constants():
    # [[100,-40],[-40,80]] fF -> det=6400 (fF)^2,
    # v^T C^-1 v = (100+80+2*(-40))/6400 = 1/(64 fF).
    p = result()
    assert p['configuration'] == 'TWO_ISLAND_CHARGE_TRANSFER'
    assert p['charge_vector_in_units_of_e'] == [1.0, -1.0]
    assert p['effective_capacitance_f'] == pytest.approx(64 * FF, rel=1e-13)
    assert p['ec_over_h_hz_matrix_only'] == pytest.approx(
        (1.602176634e-19)**2 / (2 * 6.62607015e-34 * 64 * FF), rel=1e-13)
    assert p['constants_exact_si'] == {'e_coulomb': '1.602176634E-19',
                                      'h_joule_second': '6.62607015E-34'}
    assert p['uncertainty_status'] == 'NOT_ESTABLISHED'
    assert p['review_declaration'] == 'NOT_APPROVED'


def test_grounded_single_island_is_different_circuit_than_two_island_charge_transfer():
    p = result(configuration='GROUNDED_SINGLE_ISLAND')
    assert p['fixed_zero'] == ['b']
    assert p['retained_terminal_labels'] == ['a']
    assert p['charge_vector_in_units_of_e'] == [1.0]
    assert p['effective_capacitance_f'] == pytest.approx(100 * FF)
    assert p['effective_capacitance_f'] != pytest.approx(64 * FF, abs=1e-16)


def test_three_terminal_floating_schur_and_charge_neutrality():
    # Ground caps (a,b,f)=(20,30,5)fF; mutual a-b=40, a-f=10, b-f=20.
    t = fixture([[70*FF, -40*FF, -10*FF],
                 [-40*FF, 90*FF, -20*FF],
                 [-10*FF, -20*FF, 35*FF]], ['a', 'b', 'f'])
    t['other_terminal_policy']['floating_zero_charge'] = ['f']
    p = result(t)
    eff = p['effective_matrix_f']
    assert eff[0] == pytest.approx([(70-100/35)*FF, (-40-200/35)*FF])
    assert eff[1] == pytest.approx([(-40-200/35)*FF, (90-400/35)*FF])
    # For any a,b voltage, Vf= (10 Va +20 Vb)/35 gives Qf=0.
    assert -10*1.25 -20*(-0.4) + 35*((10*1.25+20*(-0.4))/35) == pytest.approx(0)


def test_fixed_zero_guard_is_not_eliminated_by_floating_schur():
    t = fixture([[70*FF, -40*FF, -10*FF],
                 [-40*FF, 90*FF, -20*FF],
                 [-10*FF, -20*FF, 35*FF]], ['a', 'b', 'guard'])
    t['other_terminal_policy']['fixed_zero'] = ['guard']
    p = result(t)
    assert p['effective_matrix_f'][0] == pytest.approx([70*FF, -40*FF])
    assert p['effective_matrix_f'][1] == pytest.approx([-40*FF, 90*FF])
    assert p['fixed_zero'] == ['guard']
    assert p['floating_zero_charge'] == []
    floating = deepcopy(t)
    floating['other_terminal_policy'] = {'fixed_zero': [], 'floating_zero_charge': ['guard']}
    pf = result(floating)
    assert pf['effective_capacitance_f'] != pytest.approx(p['effective_capacitance_f'], abs=1e-17)


def test_full_permutation_preserves_screen_if_native_label_order_is_rebound():
    original = fixture()
    swapped = deepcopy(original)
    swapped['terminal_labels'] = ['b', 'a']
    swapped['maxwell_matrix_f'] = [[80*FF, -40*FF], [-40*FF, 100*FF]]
    # A11 externally supplies that different order; never guess by sorting.
    p = result(swapped, expected_terminal_labels=('b', 'a'))
    assert p['effective_capacitance_f'] == pytest.approx(result()['effective_capacitance_f'])
    blocked(swapped, 'BLOCKED_STALE_SOURCE', expected_terminal_labels=('a', 'b'))


def test_nonidentity_missing_native_group_and_implicit_junction_are_blocked():
    blocked(expected_terminal_labels=('b', 'a'), code='BLOCKED_STALE_SOURCE')
    blocked(expected_terminal_labels=None, code='BLOCKED_STALE_SOURCE')
    blocked(expected_ground_group_ids=(6,), code='BLOCKED_STALE_SOURCE')
    blocked(expected_ground_group_ids=None, code='BLOCKED_STALE_SOURCE')
    blocked(junction_capacitance_assumption=None, code='BLOCKED_JUNCTION_MODEL')
    blocked(junction_capacitance_assumption='JUNCTION_IS_ZERO', code='BLOCKED_JUNCTION_MODEL')
    blocked(configuration='SINGLE_ISLAND_WITHOUT_RETURN', code='BLOCKED_TOPOLOGY')


@pytest.mark.parametrize('field,value', [
    ('revision_digest', '9'*64), ('study_id', 'stale-study'),
    ('manifest_sha256', '9'*64), ('terminal_csv_sha256', '9'*64),
    ('deck_sha256', '9'*64), ('mesh_sha256', '9'*64),
])
def test_every_source_binding_must_match_independently_expected(field, value):
    t = fixture()
    t['source'][field] = value
    blocked(t, 'BLOCKED_STALE_SOURCE')


@pytest.mark.parametrize('mutation', [
    lambda t: t.pop('source'),
    lambda t: t['source'].pop('mesh_sha256'),
    lambda t: t['source'].update(revision_digest='X'*64),
    lambda t: t['source'].update(deck_sha256=t['source']['mesh_sha256']),
    lambda t: t.update(schema='sqe.capacitance-topology.v0'),
    lambda t: t.update(extra='no'),
    lambda t: t['source'].update(study_id=''),
])
def test_malformed_provenance_and_schema_block_without_numerics(mutation):
    t = fixture()
    mutation(t)
    blocked(t, 'BLOCKED_INVALID_INPUT')


@pytest.mark.parametrize('mutation', [
    lambda t: t.update(terminal_labels=['a', 'a']),
    lambda t: t.update(terminal_labels=['a']),
    lambda t: t.update(terminal_labels=['a', 'b', 'guard']),
    lambda t: t['proposed_pair'].update(island_b='unknown'),
    lambda t: t['proposed_pair'].update(island_a='b'),
    lambda t: t['other_terminal_policy'].update(fixed_zero=['b']),
    lambda t: t['other_terminal_policy'].update(floating_zero_charge=['a']),
    lambda t: t['reference_ground'].update(native_group_ids=[]),
    lambda t: t['reference_ground'].update(native_group_ids=[5, 5]),
    lambda t: t['reference_ground'].update(status='GUESS_GROUND'),
])
def test_identity_ground_and_exhaustive_terminal_classification_reject(mutation):
    t = fixture()
    mutation(t)
    blocked(t)


def test_rejected_unclassified_or_doubly_classified_other_terminal():
    t = fixture([[70*FF, -40*FF, -10*FF],
                 [-40*FF, 90*FF, -20*FF],
                 [-10*FF, -20*FF, 35*FF]], ['a', 'b', 'guard'])
    blocked(t, 'BLOCKED_TOPOLOGY')
    t['other_terminal_policy'] = {'fixed_zero': ['guard'],
                                  'floating_zero_charge': ['guard']}
    blocked(t, 'BLOCKED_TOPOLOGY')
    t['other_terminal_policy']['floating_zero_charge'] = ['unknown']
    blocked(t, 'BLOCKED_TOPOLOGY')


@pytest.mark.parametrize('matrix', [
    [[100*FF, 40*FF], [40*FF, 80*FF]],  # positive mutual (wrong convention)
    [[100*FF, -40*FF], [-39*FF, 80*FF]],  # reciprocity failure
    [[20*FF, -40*FF], [-40*FF, 80*FF]],  # negative reference-ground coupling
    [[-100*FF, -40*FF], [-40*FF, 80*FF]],
    [[100*FF, -100*FF], [-100*FF, 100*FF]],  # gauge singular
    [[100*FF, 0], [0, 0]],  # floating/degenerate node
    [[100, -40], [-40, 80]],  # fF numbers passed as SI F
    [[100*FF, float('nan')], [float('nan'), 80*FF]],
    [[100*FF, float('inf')], [float('inf'), 80*FF]],
    [[100*FF, '-40'], [-40*FF, 80*FF]],
    [[100*FF, True], [-40*FF, 80*FF]],
    [[100*FF, -40*FF]],
    [[100*FF, -40*FF], [-40*FF]],
])
def test_nonphysical_or_malformed_matrix_never_returns_a_number(matrix):
    blocked(fixture(matrix))


def test_non_spd_disconnected_laplacian_with_fixed_guard_cannot_hide_gauge():
    # Without external ground, a separately fixed guard could make a minor
    # SPD, but does not validate the mandated reference-ground condition.
    t = fixture([[10*FF, -10*FF, 0],
                 [-10*FF, 10*FF, 0],
                 [0, 0, 5*FF]], ['a', 'b', 'guard'])
    t['other_terminal_policy']['fixed_zero'] = ['guard']
    blocked(t, 'BLOCKED_NUMERICS')


def test_small_ground_anchoring_with_unstable_condition_number_blocked():
    t = fixture([[1e-15, -(1-1e-12)*1e-15],
                 [-(1-1e-12)*1e-15, 1e-15]])
    d = blocked(t, 'BLOCKED_NUMERICS')
    assert 'ill-conditioned' in d.reason


def test_floating_subnetwork_energy_degeneracy_is_blocked():
    t = fixture([[100*FF, -10*FF, -90*FF],
                 [-10*FF, 10*FF, 0],
                 [-90*FF, 0, 90*FF]], ['a', 'b', 'f'])
    t['other_terminal_policy']['floating_zero_charge'] = ['f']
    blocked(t, 'BLOCKED_NUMERICS')


def test_review_claim_cannot_self_authorize_or_create_scqubits_ec():
    t = fixture()
    t['scientific_status'] = 'REVIEWED_TOPOLOGY'
    t['review'] = {'status': 'APPROVED', 'record_sha256': '5'*64}
    blocked(t, 'BLOCKED_NOT_REVIEWED')
    declaration = ReviewedTopologyDeclaration(
        record_sha256='5'*64, revision_digest=SOURCE['revision_digest'],
        manifest_sha256=SOURCE['manifest_sha256'], terminal_labels=('a', 'b'),
        native_ground_group_ids=(5,), circuit_convention='TWO_ISLAND_CHARGE_TRANSFER')
    p = result(t, reviewed_topology=declaration)
    assert p['review_declaration'] == 'DECLARED_NOT_INDEPENDENTLY_AUTHENTICATED'
    blocked(t, 'BLOCKED_NOT_REVIEWED', reviewed_topology=replace(declaration, revision_digest='9'*64))
    blocked(t, 'BLOCKED_NOT_REVIEWED', reviewed_topology=replace(declaration, native_ground_group_ids=(7,)))
    blocked(t, 'BLOCKED_NOT_REVIEWED', reviewed_topology=replace(declaration, circuit_convention='GROUNDED_SINGLE_ISLAND'))
    t['review']['status'] = 'NOT_APPROVED'
    blocked(t, 'BLOCKED_NOT_REVIEWED', reviewed_topology=declaration)


def test_inputs_are_pure_and_no_external_solver_scqubits_access(monkeypatch):
    import builtins
    import subprocess

    t = fixture()
    original = deepcopy(t)
    real_import = builtins.__import__

    def no_native_import(name, *args, **kwargs):
        if name.startswith(('scqubits', 'gmsh', 'palace')):
            pytest.fail('Pure reduction attempted a native engine import')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_native_import)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected native run'))
    p = result(t)
    assert t == original
    assert math.isfinite(p['ec_over_h_hz_matrix_only'])
