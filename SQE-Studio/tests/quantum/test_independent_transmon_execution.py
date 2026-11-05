"""M5 A12: fixture-only request preparation, not a native scqubits solve."""
from __future__ import annotations

import copy
import json

import pytest

from sqe_studio.adapters import scqubits_adapter
from sqe_studio.contracts import digest, fresh_project
from sqe_studio.interop.independent_transmon_execution import (
    IndependentTransmonExecutionBlocked, PREFLIGHT_SCHEMA, REQUEST_SCHEMA,
    build_independent_transmon_execution_preflight,
)
from sqe_studio.interop.transmon_quantum_preflight import (
    DECLARATION_SCHEMA, build_independent_transmon_preflight,
)
from sqe_studio.store import NotFound, Store


OWNER = 'authenticated-owner-fixture-only'


def manual_study():
    declaration = {
        'schema': DECLARATION_SCHEMA, 'source': 'independent',
        'model': 'Transmon',
        'parameters': {'EJ': 15.0, 'EC': 0.25, 'ng': 0.0, 'ncut': 30},
        'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
        'levels': 5,
    }
    return {'id': 'independent_transmon_01',
            **build_independent_transmon_preflight(declaration)['study_template']}


@pytest.fixture
def saved(tmp_path):
    """A real local SQLite immutable revision, but NOT an M4 native or reviewer receipt."""
    store = Store(tmp_path / 'data')
    project = store.create(OWNER, 'Transmon Fixture', 'transmon')
    model = copy.deepcopy(project['model'])
    model['studies'].append(manual_study())
    revision = store.commit(OWNER, project['id'], project['head'], model)
    context = store.project(OWNER, project['id'])
    assert context['revision'] == context['head'] == revision
    request = {'schema': REQUEST_SCHEMA, 'project_id': project['id'],
               'expected_revision': revision, 'study_id': 'independent_transmon_01'}
    return store, request, context


def preflight(request, context):
    return build_independent_transmon_execution_preflight(request, trusted_revision=context)


def blocked(request, context, code):
    with pytest.raises(IndependentTransmonExecutionBlocked) as caught:
        preflight(request, context)
    assert caught.value.code == code


def edited(saved, edit, *, recompute_digest=True):
    _, req, context = saved
    req, ctx = copy.deepcopy(req), copy.deepcopy(context)
    edit(req, ctx)
    if recompute_digest:
        try:
            ctx['revision_digest'] = digest(ctx['model'])
        except (ValueError, TypeError, OverflowError):
            # Invalid/non-finite fixture model cannot be a Store-backed snapshot.
            pass
    return req, ctx


def test_trusted_store_saved_revision_success_is_software_only(saved, monkeypatch):
    store, request, context = saved
    before_request, before_context = copy.deepcopy(request), copy.deepcopy(context)
    monkeypatch.setattr(scqubits_adapter, 'run',
                        lambda *a, **k: pytest.fail('native solver must not execute'))
    monkeypatch.setattr(store, 'commit',
                        lambda *a, **k: pytest.fail('preflight must not write revisions'))
    output = preflight(request, context)
    assert output['schema'] == PREFLIGHT_SCHEMA
    assert output['status'] == 'READY_FOR_SOFTWARE_EXECUTION_ONLY'
    assert output['target'] == {
        'project_id': context['id'], 'revision': context['head'],
        'revision_digest': context['revision_digest'],
        'study_id': request['study_id'], 'engine': 'scqubits',
        'kind': 'quantum_spectrum',
        'saved_input_sha256': digest(context['model']['studies'][0]['inputs']),
    }
    assert output['adapter_invocation_plan']['inputs'] == context['model']['studies'][0]['inputs']
    parsed = scqubits_adapter._spec(output['adapter_invocation_plan']['inputs'],
                                    context['model'])
    assert parsed['model'] == 'Transmon'
    assert parsed['source'] == 'independent'
    assert parsed['groups'][0]['parameters']['EC'] == .25
    for key in ('em_ec_transfer', 'em_to_hamiltonian', 'b04_approval'):
        assert output[key] == 'BLOCKED'
    assert output['fabrication'] == 'HOLD'
    assert output['solver_execution'] == 'NOT_EXECUTED'
    assert output['native_solver_evidence'] == 'NONE'
    assert output['saved_revision_mutation'] == 'NONE'
    assert output['scientific_authorization'].startswith('BLOCKED_')
    assert request == before_request and context == before_context
    json.dumps(output, allow_nan=False)


@pytest.mark.parametrize('ej,ec,ng,ncut,levels', [
    (0.01, .01, -10, 3, 7), (1000, 1000, 10, 80, 12),
    (20, .2, -.5, 4, 9), (15.4, .22, .4, 3, 2),
])
def test_valid_frozen_adapter_bounds(saved, ej, ec, ng, ncut, levels):
    def change(req, ctx):
        inp = ctx['model']['studies'][0]['inputs']
        inp['parameters'].update(EJ=ej, EC=ec, ng=ng, ncut=ncut)
        inp['levels'] = levels
    req, ctx = edited(saved, change)
    result = preflight(req, ctx)
    parsed = scqubits_adapter._spec(result['adapter_invocation_plan']['inputs'], ctx['model'])
    assert parsed['levels'] == levels
    assert parsed['groups'][0]['parameters']['ncut'] == ncut


@pytest.mark.parametrize('change,code', [
    (lambda r: r.pop('schema'), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(schema='sqe.capacitance-reduction-decision.a12.v1'), 'INVALID_REQUEST_SCHEMA'),
    (lambda r: r.update(em_ec_transfer='APPROVED'), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(approved=True), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(EC=0.25), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(parameters={'EC': 0.25}), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(trusted_revision={'id': 'forge'}), 'INVALID_REQUEST_SHAPE'),
    (lambda r: r.update(project_id='not-a-real-id'), 'INVALID_PROJECT_ID'),
    (lambda r: r.update(project_id=True), 'INVALID_PROJECT_ID'),
    (lambda r: r.update(expected_revision='1234'), 'INVALID_REVISION'),
    (lambda r: r.update(expected_revision=True), 'INVALID_REVISION'),
    (lambda r: r.update(study_id='palace_capacitance'), 'UNTRUSTED_STUDY_ORIGIN'),
    (lambda r: r.update(study_id='independent_transmon_99'), 'UNTRUSTED_STUDY_ORIGIN'),
    (lambda r: r.update(study_id=True), 'UNTRUSTED_STUDY_ORIGIN'),
])
def test_request_selector_must_not_contain_science_claims_or_parameters(saved, change, code):
    _, request, ctx = saved
    req = copy.deepcopy(request)
    change(req)
    blocked(req, ctx, code)


@pytest.mark.parametrize('change,code', [
    (lambda r, c: c.update(head='f' * 32), 'STALE_OR_MISMATCHED_REVISION'),
    (lambda r, c: c.update(revision='f' * 32), 'STALE_OR_MISMATCHED_REVISION'),
    (lambda r, c: c.update(id='f' * 32), 'STALE_OR_MISMATCHED_REVISION'),
    (lambda r, c: r.update(expected_revision='e' * 32), 'STALE_OR_MISMATCHED_REVISION'),
    (lambda r, c: r.update(project_id='e' * 32), 'STALE_OR_MISMATCHED_REVISION'),
    (lambda r, c: c.update(head='bad'), 'UNTRUSTED_REVISION_CONTEXT'),
    (lambda r, c: c.update(revision_digest='not-a-digest'), 'UNTRUSTED_REVISION_CONTEXT'),
    (lambda r, c: c.update(parent='fake'), 'UNTRUSTED_REVISION_CONTEXT'),
    (lambda r, c: c.update(review='APPROVED'), 'UNTRUSTED_REVISION_CONTEXT'),
    (lambda r, c: c.pop('model'), 'UNTRUSTED_REVISION_CONTEXT'),
    (lambda r, c: c.update(name='Other name'), 'REVISION_DIGEST_MISMATCH'),
    (lambda r, c: c['model'].update(name='Tampered'),
     'REVISION_DIGEST_MISMATCH'),
])
def test_revision_and_identity_must_be_exact(saved, change, code):
    req, ctx = edited(saved, change, recompute_digest=False)
    blocked(req, ctx, code)


def test_historical_saved_revision_is_rejected_even_when_it_exists(saved):
    store, request, ctx = saved
    model = copy.deepcopy(ctx['model'])
    model['notes'] = 'next saved change'
    latest = store.commit(OWNER, ctx['id'], ctx['head'], model)
    historical = store.project(OWNER, ctx['id'], ctx['revision'])
    assert historical['head'] == latest and historical['revision'] != latest
    blocked(request, historical, 'STALE_OR_MISMATCHED_REVISION')
    latest_context = store.project(OWNER, ctx['id'])
    blocked(request, latest_context, 'STALE_OR_MISMATCHED_REVISION')


def test_store_owner_scoping_is_required_for_integrator(saved):
    store, _, ctx = saved
    with pytest.raises(NotFound):
        store.project('another-owner', ctx['id'])


@pytest.mark.parametrize('change,code', [
    (lambda s: s.update(engine='sqdmetal_palace'), 'UNTRUSTED_STUDY_SHAPE'),
    (lambda s: s.update(kind='capacitance'), 'UNTRUSTED_STUDY_SHAPE'),
    (lambda s: s['inputs'].update(source='em'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(source='palace'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(model='Fluxonium'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(em_artifact={'EC': 0.25}), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(derived_from='Palace'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(ec_over_h_hz_matrix_only=250e6), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(lineage={'em':'Palace'}), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(review={'status':'APPROVED'}), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(scientific_authorization='SCIENTIFICALLY_APPROVED'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(em_ec_transfer='APPROVED'), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(input_sha256='f'*64), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(context_sha256='f'*64), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(sweep={'parameter':'EC'}), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s['inputs'].update(convergence={'enabled':True}), 'SAVED_PARAMETERS_BLOCKED'),
    (lambda s: s.update(provenance='reviewed'), 'UNTRUSTED_REVISION_CONTEXT'),
])
def test_unapproved_native_em_review_or_adapter_extras_fail_closed(saved, change, code):
    def edit(req, ctx): change(ctx['model']['studies'][0])
    req, ctx = edited(saved, edit)
    blocked(req, ctx, code)


@pytest.mark.parametrize('field,raw', [
    ('EJ', 0), ('EJ', -1), ('EJ', float('inf')), ('EJ', float('nan')),
    ('EJ', '15'), ('EJ', True), ('EJ', 1001), ('EJ', 10**400),
    ('EC', 0), ('EC', -0.01), ('EC', float('nan')), ('EC', float('-inf')),
    ('EC', '0.25'), ('EC', {'ec_over_h_hz_matrix_only': 250_000_000}),
    ('EC', [0.25]), ('EC', 1000.1), ('EC', False),
    ('ng', -10.1), ('ng', 10.1), ('ng', float('inf')), ('ng', '0'),
    ('ncut', 2), ('ncut', 81), ('ncut', 3.0), ('ncut', True),
])
def test_numerical_parameters_reject_coercion_nonfinite_or_palace_payload(saved, field, raw):
    req, ctx = edited(saved, lambda r, c: c['model']['studies'][0]['inputs']['parameters'].update({field:raw}))
    # Model validation runs before M3 on nonfinite snapshots.
    nonfinite = type(raw) is float and (raw != raw or raw in (float('inf'), float('-inf')))
    blocked(req, ctx, 'UNTRUSTED_REVISION_CONTEXT' if nonfinite else 'SAVED_PARAMETERS_BLOCKED')


@pytest.mark.parametrize('field,unit', [
    ('EJ', 'J'), ('EJ', 'MHz'), ('EC', 'F'), ('EC', 'MHz'),
    ('EC', 'GHz from Palace'), ('ng', '1'), ('ng', 'GHz'), ('ncut', 'GHz'),
    ('EC', None), ('EJ', True),
])
def test_units_never_implicitly_converted(saved, field, unit):
    req, ctx = edited(saved, lambda r, c: c['model']['studies'][0]['inputs']['parameter_units'].update({field:unit}))
    blocked(req, ctx, 'SAVED_PARAMETERS_BLOCKED')


@pytest.mark.parametrize('raw', [1, 13, 2.0, True, float('nan'), float('inf')])
def test_invalid_level_bounds(saved, raw):
    req, ctx = edited(saved, lambda r, c: c['model']['studies'][0]['inputs'].update(levels=raw))
    code = 'UNTRUSTED_REVISION_CONTEXT' if type(raw) is float and (raw != raw or raw == float('inf')) else 'SAVED_PARAMETERS_BLOCKED'
    blocked(req, ctx, code)


def test_charge_basis_dimension_is_checked(saved):
    def edit(req, ctx):
        p = ctx['model']['studies'][0]['inputs']
        p['parameters']['ncut'] = 3
        p['levels'] = 8
    req, ctx = edited(saved, edit)
    blocked(req, ctx, 'SAVED_PARAMETERS_BLOCKED')


def test_missing_or_mismatched_saved_study_not_selected_by_position(saved):
    req, ctx = edited(saved, lambda r, c: c['model']['studies'].clear())
    blocked(req, ctx, 'SAVED_STUDY_NOT_FOUND')
    req, ctx = edited(saved, lambda r, c: c['model']['studies'][0].update(id='independent_transmon_02'))
    blocked(req, ctx, 'SAVED_STUDY_NOT_FOUND')


def test_project_family_restriction(saved):
    req, ctx = edited(saved, lambda r, c: c['model'].update(family='generic'))
    blocked(req, ctx, 'UNSUPPORTED_DESIGN_FAMILY')


def test_context_hash_mismatch_and_unauthorized_edits(saved):
    req, ctx = edited(saved, lambda r, c: c['model']['studies'][0]['inputs']['parameters'].update(EC=0.3),
                      recompute_digest=False)
    blocked(req, ctx, 'REVISION_DIGEST_MISMATCH')
    req, ctx = edited(saved, lambda r, c: c.update(revision_digest='f'*64), recompute_digest=False)
    blocked(req, ctx, 'REVISION_DIGEST_MISMATCH')


def test_no_cross_revision_or_cross_call_aliasing(saved):
    _, req, ctx = saved
    original = copy.deepcopy(ctx)
    one, two = preflight(req, ctx), preflight(req, ctx)
    one['adapter_invocation_plan']['inputs']['parameters']['EC'] = 999
    one['target']['study_id'] = 'other'
    assert ctx == original
    assert two['adapter_invocation_plan']['inputs']['parameters']['EC'] == .25
    assert two['target']['study_id'] == req['study_id']


def test_nonmapping_context_blocked_even_when_request_is_valid(saved):
    _, req, _ = saved
    for invalid in (None, {}, 'owner verified', req, ['saved']):
        blocked(req, invalid, 'UNTRUSTED_REVISION_CONTEXT')
