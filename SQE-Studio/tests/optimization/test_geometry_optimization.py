"""A13 fixture tests: no native solver executed or scientific PASS asserted."""
from dataclasses import replace
import copy
import json
import uuid
from pathlib import Path

import pytest

from sqe_studio.contracts import digest, fresh_project
from sqe_studio.eda.capabilities import list_capabilities
from sqe_studio.orchestration.artifacts import adapter_digest, fingerprint, sha_bytes
from sqe_studio.orchestration.optimization import (
    Goal, OptimizationBlocked, inspect_native_candidate, plan_optimization,
    replan_after_native_candidate, submit_geometry_candidate, MAX_OPTIMIZATION_SOLVES,
    MAX_OPTIMIZATION_NATIVE_SECONDS,
)
from sqe_studio.orchestration.sweep import MAX_SWEEP_POINTS, plan_geometry_sweep
from sqe_studio.store import Store


def model(family='resonator'):
    project = fresh_project('RF prototype', family)
    project['layout']['components'] = [
        {'kind': 'ResonatorLumped', 'name': 'R1', 'x_mm': 0, 'y_mm': 0,
         'options': {'box_width_um': 22, 'box_height_um': 40}},
        {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': 1, 'y_mm': -1}]
    project['studies'] = [{'id': 'em1', 'engine': 'sqdmetal_palace',
                           'kind': 'eigenmode', 'inputs': {'em': {'execution': 'solve'}}}]
    project['process']['source'] = 'reviewed'
    return project


def axis(values=(24, 26)):
    return {'layout.components.R1.options.box_width_um':
            {'unit': 'um', 'lower': 10, 'upper': 100, 'values': list(values)}}


def mode_goal():
    return Goal('resonance', 'em.mode_frequency', 'GHz', 'target', 5.2,
                (('mode_label', 'resonator_mode'),), tolerance=0.01)


def rf_goal():
    return Goal('rf_transmission', 'rf.s_parameter_magnitude', '1', 'at_least', 0.9,
                (('input_port', 'P1'), ('output_port', 'P2'),
                 ('frequency_hz', 5e9), ('reference_plane', 'chip_edge')))


def plan(project=None, rev='rev0'):
    return plan_optimization(project or model(), rev, 'em1', axis(),
                             objectives=(mode_goal(),), constraints=(rf_goal(),),
                             mode='manual', selected=0)


def review(candidate, operator='owner'):
    return {'schema': 'sqe.geometry-review.v1', 'operator': operator,
            'candidate_digest': candidate.candidate_digest,
            'materials_rechecked': True, 'ports_boundaries_rechecked': True,
            'rationale': 'Rechecked candidate-specific geometry assumptions and EM ports.'}


def submit(store, jobs, owner, pid, plan_obj, candidate):
    return submit_geometry_candidate(store, jobs, owner, pid, plan_obj, candidate,
                                     review=review(candidate, owner))


def test_geometry_is_revision_bound_not_study_option_sweep():
    project = model()
    original = copy.deepcopy(project)
    a = plan_geometry_sweep(project, 'rev0', axis(), mode='automatic')
    b = plan_geometry_sweep(project, 'rev0', dict(reversed(list(axis().items()))),
                            mode='automatic')
    assert len(a) == 2 and a == b
    assert a[0].project != a[1].project and a[0].geometry_digest != a[1].geometry_digest
    assert a[0].project_digest != a[1].project_digest
    assert a[0].source_project_digest == digest(original)
    assert a[0].project['studies'] == original['studies']
    assert a[0].project['layout']['components'][0]['options']['box_width_um'] == 24
    assert project == original
    one = plan_geometry_sweep(project, 'rev0', axis(), mode='manual', selected=1)
    assert one[0].index == 1 and one[0].project['layout']['components'][0]['options']['box_width_um'] == 26
    # Separate explicit chip dimension bounds; no index-based component targeting.
    pts = plan_geometry_sweep(project, 'rev0', {
        'layout.chip.width_mm': {'unit':'mm','lower':3,'upper':6,'values':[5.5]}},
        mode='manual', selected=0)
    assert pts[0].project['layout']['chip']['width_mm'] == 5.5


@pytest.mark.parametrize('invalid', [
    {'layout.components.R1.options.box_width_um': {'unit':'mm','lower':10,'upper':100,'values':[25]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[float('nan')]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[float('inf')]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[True]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[20,20]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[22]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[1000]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':0,'upper':100,'values':[20]}},
    {'layout.components.R1.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':list(range(MAX_SWEEP_POINTS+1))}},
    {'layout.components.0.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[25]}},
    {'layout.components.R2.options.box_width_um': {'unit':'um','lower':10,'upper':100,'values':[25]}},
    {'layout.process.stack.0': {'unit':'um','lower':10,'upper':100,'values':[25]}},
    {'layout.components.R1.kind': {'unit':'um','lower':10,'upper':100,'values':[25]}},
    {'layout.components.R1.options.__class__': {'unit':'um','lower':10,'upper':100,'values':[25]}},
])
def test_unsafe_geometry_paths_units_and_limits_fail_closed(invalid):
    with pytest.raises(ValueError):
        plan_geometry_sweep(model(), 'rev0', invalid, mode='manual', selected=0)


def test_duplicate_component_names_and_noop_automatic_candidate_are_rejected():
    project = model()
    project['layout']['components'].append(copy.deepcopy(project['layout']['components'][0]))
    with pytest.raises(ValueError, match='uniquely named'):
        plan_geometry_sweep(project, 'rev0', axis(), mode='manual', selected=0)
    with pytest.raises(ValueError, match='must change'):
        plan_geometry_sweep(model(), 'rev0', axis((22, 24)), mode='automatic')
    with pytest.raises(ValueError):
        plan_geometry_sweep(model(), 'rev0', axis(), mode='manual', selected=True)
    with pytest.raises(ValueError):
        plan_geometry_sweep(model(), 'rev0', axis(), mode='automatic', selected=0)


def test_rf_device_neutral_objectives_constraints_and_holds():
    for family in ('generic', 'resonator', 'amplifier', 'fluxonium'):
        p = plan(model(family))
        assert p.schema == 'sqe.geometry-optimization.v1'
        assert p.fabrication_status == 'HOLD'
        assert p.physical_qualification.startswith('BLOCKED')
        assert p.objectives[0].metric == 'em.mode_frequency'
        assert p.constraints[0].metric == 'rf.s_parameter_magnitude'
    edges = {e['id']:e for e in list_capabilities()}
    assert edges['geometry_revision_to_native_em']['status'] == 'native_conditional'
    assert edges['native_em_to_geometry_objectives']['status'] == 'blocked'
    assert edges['cad_to_fab']['status'] == 'blocked'


@pytest.mark.parametrize('goal', [
    lambda: Goal('f', 'em.mode_frequency', 'Hz', 'target', 5, (('mode_label','R1'),), tolerance=.01),
    lambda: Goal('f', 'em.mode_frequency', 'GHz', 'target', float('nan'), (('mode_label','R1'),), tolerance=.01),
    lambda: Goal('f', 'em.mode_frequency', 'GHz', 'target', 5, (('mode_label','1'),), tolerance=.01),
    lambda: Goal('f', 'em.mode_frequency', 'GHz', 'target', 5, (('mode_label','R1'),)),
    lambda: Goal('f', 'em.mode_frequency', 'GHz', 'at_most', 5, (('mode_label','R1'),), tolerance=.01),
    lambda: Goal('f', 'rf.s_parameter_magnitude', '1', 'at_least', 0.9, (('input_port','P1'),)),
    lambda: Goal('f', 'rf.s_parameter_magnitude', '1', 'at_least', 0.9, (('input_port','P1'), ('output_port','P2'), ('frequency_hz',-1),('reference_plane','chip'))),
    lambda: Goal('f', 'unsupported', 'GHz', 'target', 5, (('mode_label','R1'),), tolerance=.1),
])
def test_goal_contract_rejects_untyped_and_unidentified_science(goal):
    with pytest.raises(ValueError):
        goal()


def test_objective_requires_em_study_and_constraint_type():
    p = model()
    with pytest.raises(ValueError):
        plan_optimization(p, 'rev0', 'em1', axis(), objectives=(rf_goal(),), mode='manual', selected=0)
    with pytest.raises(ValueError):
        plan_optimization(p, 'rev0', 'em1', axis(), objectives=(mode_goal(), mode_goal()), mode='manual', selected=0)
    with pytest.raises(OptimizationBlocked):
        plan_optimization(p, 'rev0', 'missing', axis(), objectives=(mode_goal(),), mode='manual', selected=0)
    p['studies'][0]['engine'] = 'scqubits'
    with pytest.raises(OptimizationBlocked):
        plan_optimization(p, 'rev0', 'em1', axis(), objectives=(mode_goal(),), mode='manual', selected=0)


class FixtureJobManager:
    """Only submits a Store record; no simulator / fabricated result API."""
    def __init__(self, store, fail=False):
        self.store = store
        self.fail = fail
        self.calls = []

    def start(self, owner, project_id, revision, study_id, *, force):
        self.calls.append((owner, project_id, revision, study_id, force))
        if self.fail:
            raise RuntimeError('Native Palace runtime not installed')
        folder = self.store.root / 'native-runs' / project_id / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=False)
        self.store.put_run(owner, project_id, revision, study_id, 'sqdmetal_palace', folder)
        return folder.name


def setup(tmp_path):
    store = Store(tmp_path / 'private')
    created = store.create('owner', 'RF prototype', 'resonator', model())
    p = plan(created['model'], created['head'])
    return store, created['id'], p, p.candidates[0]


def test_save_revision_then_force_native_not_cached_and_replan_after_head(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    jobs = FixtureJobManager(store)
    sub = submit(store, jobs, 'owner', pid, p, candidate)
    assert sub.status == 'NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED'
    assert sub.fabrication_status == 'HOLD' and sub.review_digest
    assert jobs.calls == [('owner', pid, sub.revision_id, 'em1', True)]
    saved = store.project('owner', pid)
    assert saved['head'] != p.source_revision
    assert saved['parent'] == p.source_revision
    assert saved['revision_digest'] == candidate.project_digest
    with pytest.raises(OptimizationBlocked, match='stale'):
        submit(store, jobs, 'owner', pid, p, p.candidates[1] if len(p.candidates)>1 else candidate)
    with pytest.raises(OptimizationBlocked, match='not complete'):
        inspect_native_candidate(store, 'owner', pid, p, candidate, sub)


def test_missing_material_review_and_no_solve_fail_before_committing(tmp_path):
    for key in ('material', 'execution'):
        m = model()
        if key == 'material':
            m['process']['source'] = 'unverified'
        else:
            m['studies'][0]['inputs']['em']['execution'] = 'mesh_only'
        store = Store(tmp_path/key)
        created = store.create('owner','RF prototype','resonator',m)
        p = plan(created['model'],created['head'])
        jobs = FixtureJobManager(store)
        with pytest.raises(OptimizationBlocked, match='reviewed materials'):
            submit(store,jobs,'owner',created['id'],p,p.candidates[0])
        assert jobs.calls == [] and store.project('owner',created['id'])['head'] == created['head']


def test_native_unavailable_stays_blocked_with_saved_revision(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    jobs = FixtureJobManager(store, fail=True)
    sub = submit(store, jobs, 'owner', pid, p, candidate)
    assert sub.status == 'BLOCKED_NATIVE_SUBMISSION' and sub.run_id is None
    assert 'Native Palace runtime not installed' in sub.reason
    assert store.project('owner',pid)['head'] == sub.revision_id
    with pytest.raises(OptimizationBlocked):
        inspect_native_candidate(store,'owner',pid,p,candidate,sub)


def test_mutated_snapshot_or_unrelated_revision_cannot_be_submitted(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    jobs = FixtureJobManager(store)
    candidate.project['layout']['chip']['width_mm'] += 1  # malicious mutation after planning
    with pytest.raises(OptimizationBlocked):
        submit(store,jobs,'owner',pid,p,candidate)
    assert jobs.calls == []
    with pytest.raises(Exception):
        submit(store,jobs,'different-owner',pid,p,candidate)


def write_fixture_native_output(store, pid, p, candidate, sub):
    """Make a manually constructed hash-consistent fixture, NOT a solver run."""
    folder = store.root / 'native-runs' / pid / sub.run_id
    snapshot = {'project': candidate.project, 'project_digest': candidate.project_digest,
                'revision_id': sub.revision_id, 'study':candidate.project['studies'][0],
                'parents': [], 'attempt': 1, 'retry_of': None,
                'expected_adapter_sha256': adapter_digest('sqdmetal_palace')}
    (folder / 'snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
    output = folder / 'output'
    path = output / 'sqe_em' / 'outputFiles' / 'eig.csv'
    path.parent.mkdir(parents=True)
    path.write_text('m,f (GHz),a,Q\n1,5.21,1,20000\n',encoding='utf-8')
    study = candidate.project['studies'][0]
    adapter_sha = adapter_digest('sqdmetal_palace')
    fingerprint_sha = fingerprint(revision_id=sub.revision_id,
                                  project_digest=candidate.project_digest,
                                  study=study, native_version='fixture-version',
                                  adapter_sha256=adapter_sha)
    manifest = {'schema':'sqe.artifact.v1', 'engine':'sqdmetal_palace',
                'engine_version':'fixture-version', 'study_id':p.study_id,
                'adapter_sha256': adapter_sha,
                'revision_id':sub.revision_id,'project_digest':candidate.project_digest,
                'kind':study['kind'],'artifact_type':
                {'eigenmode':'palace.eigenmodes','sparameters':'palace.sparameters',
                 'capacitance':'palace.capacitance_matrix'}[study['kind']],
                'fabrication_status':'HOLD','scientific_status':'review_required',
                'cache_fingerprint':fingerprint_sha,'parents':[],
                'provenance':{'used_revision':sub.revision_id,
                              'used_project_sha256':candidate.project_digest,
                              'was_generated_by':'sqdmetal_palace'},
                'artifacts':[{'name':'sqe_em/outputFiles/eig.csv',
                              'sha256':sha_bytes(path.read_bytes()), 'bytes':path.stat().st_size}]}
    (output / 'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    store.set_run(sub.run_id, 'completed')
    return path, output / 'RESULT_MANIFEST.json'


def test_hash_consistent_fixture_still_cannot_score_mode_or_rf(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid,p,candidate)
    write_fixture_native_output(store,pid,p,candidate,sub)
    evidence = inspect_native_candidate(store, 'owner', pid,p,candidate,sub)
    assert evidence['status'] == 'VERIFIED_NATIVE_ARTIFACT_REVIEW_REQUIRED'
    assert evidence['native_manifest_sha256'] and evidence['native_content_sha256']
    assert evidence['objective_results'][0]['status'] == 'BLOCKED_UNVERIFIED_COMPLEX_FIELD_MODE_IDENTITY'
    assert evidence['constraint_results'][0]['status'] == 'BLOCKED_INCOMPATIBLE_NATIVE_STUDY_KIND'
    assert evidence['native_observations_unassigned']['modes'] == [
        {'mode_index': 1, 'frequency_GHz': 5.21}]
    for result in evidence['objective_results'] + evidence['constraint_results']:
        assert result['value'] is None and result['feasible'] is None
        assert result['source_manifest_sha256'] == evidence['native_manifest_sha256']
        assert result['source_run_id'] == sub.run_id
        assert result['comparison'] in ('target', 'at_least')
        assert result['identity'] and result['threshold'] > 0
    assert evidence['native_budget_seconds'] == 900
    assert evidence['fabrication_status'] == 'HOLD'
    assert evidence['operator_review_sha256'] == sub.review_digest
    assert evidence['mode_matching'].startswith('BLOCKED')
    assert evidence['scientific_qualification'] == 'NOT_ESTABLISHED'


@pytest.mark.parametrize('case', ('bytes', 'manifest', 'snapshot', 'stale_head', 'failed_run', 'tampered_review'))
def test_corrupted_native_bytes_manifest_or_worker_snapshot_fail_closed(tmp_path, case):
    store, pid, p, candidate = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid,p,candidate)
    native, manifest = write_fixture_native_output(store,pid,p,candidate,sub)
    if case == 'bytes':
        native.write_text('m,f (GHz),a,Q\n1,9.9,1,1\n',encoding='utf-8')
    elif case == 'manifest':
        data = json.loads(manifest.read_text())
        data['project_digest'] = '0'*64
        manifest.write_text(json.dumps(data),encoding='utf-8')
    elif case == 'snapshot':
        snap = manifest.parent.parent / 'snapshot.json'
        assert snap.is_file(), 'Mutation must target the real worker snapshot'
        snap.write_text('{}',encoding='utf-8')
    elif case == 'tampered_review':
        review_file = store.root / 'optimization-reviews' / pid / (sub.revision_id + '.json')
        reviewed = json.loads(review_file.read_text())
        reviewed['review']['rationale'] = 'Changed review notes'
        review_file.write_text(json.dumps(reviewed),encoding='utf-8')
    elif case == 'stale_head':
        store.commit('owner',pid,sub.revision_id,store.project('owner',pid)['model'])
    else:
        store.set_run(sub.run_id, 'failed')
    with pytest.raises(OptimizationBlocked):
        inspect_native_candidate(store, 'owner', pid,p,candidate,sub)


def test_result_rejected_if_reused_run_id_from_another_candidate(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid,p,candidate)
    write_fixture_native_output(store,pid,p,candidate,sub)
    other = replace(sub, candidate_digest='0'*64)
    with pytest.raises(OptimizationBlocked):
        inspect_native_candidate(store,'owner',pid,p,candidate,other)
    with pytest.raises(Exception):
        inspect_native_candidate(store,'another-owner',pid,p,candidate,sub)


def test_new_geometry_revision_requires_new_explicit_operator_review(tmp_path):
    store, pid, p, candidate = setup(tmp_path)
    jobs = FixtureJobManager(store)
    for bad in (None, {}, dict(review(candidate), candidate_digest='0'*64),
                dict(review(candidate), materials_rechecked=False),
                dict(review(candidate), ports_boundaries_rechecked=False),
                dict(review(candidate), operator='imposter'),
                dict(review(candidate), rationale='ok')):
        with pytest.raises(OptimizationBlocked, match='Explicit owner review'):
            submit_geometry_candidate(store, jobs, 'owner', pid, p, candidate, review=bad)
    assert jobs.calls == [] and store.project('owner',pid)['head'] == p.source_revision


def test_finite_native_plan_budget_and_manual_review_at_each_iteration(tmp_path):
    store, pid, first, cand = setup(tmp_path)
    assert first.planned_native_budget_seconds == 900
    assert first.native_budget_seconds == 900
    assert MAX_OPTIMIZATION_SOLVES == 3
    assert MAX_OPTIMIZATION_NATIVE_SECONDS == 2700
    with pytest.raises(OptimizationBlocked, match='45-minute plan budget'):
        plan_optimization(model(), 'rev0', 'em1', axis((24, 26, 28, 30)),
                          objectives=(mode_goal(),), mode='automatic')
    many = plan_optimization(model(), 'rev0', 'em1', axis((24, 26, 28)),
                             objectives=(mode_goal(),), mode='automatic')
    assert len(many.candidates) == 3 and many.planned_native_budget_seconds == 2700
    jobs = FixtureJobManager(store)
    sub1 = submit(store, jobs, 'owner', pid, first, cand)
    write_fixture_native_output(store, pid, first, cand, sub1)
    next_plan = replan_after_native_candidate(
        store, 'owner', pid, first, cand, sub1, axis((26, 28)), selected=0)
    assert next_plan.source_revision == sub1.revision_id
    assert next_plan.source_project_digest == cand.project_digest
    assert next_plan.source_native_run_id == sub1.run_id
    assert next_plan.source_native_manifest_sha256
    assert next_plan.candidates[0].coordinates[0][1] == 26
    with pytest.raises(OptimizationBlocked, match='stale'):
        submit(store, jobs, 'owner', pid, first, cand)
    sub2 = submit(store, jobs, 'owner', pid, next_plan, next_plan.candidates[0])
    assert sub2.status == 'NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED'
    assert sub2.run_id != sub1.run_id
    assert len(jobs.calls) == 2 and all(call[-1] is True for call in jobs.calls)
    path = store.root / 'optimization-reviews' / pid / (sub2.revision_id + '.json')
    review_record = json.loads(path.read_text(encoding='utf-8'))
    assert review_record['source_native_run_id'] == sub1.run_id
    assert review_record['source_native_manifest_sha256'] == next_plan.source_native_manifest_sha256
    write_fixture_native_output(store, pid, next_plan, next_plan.candidates[0], sub2)
    result2 = inspect_native_candidate(store, 'owner', pid, next_plan,
                                       next_plan.candidates[0], sub2)
    assert result2['source_native_manifest_sha256'] == next_plan.source_native_manifest_sha256
    assert result2['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert result2['objective_results'][0]['value'] is None


def test_next_step_refuses_modified_prior_native_bytes_before_new_commit(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    jobs = FixtureJobManager(store)
    sub = submit(store, jobs, 'owner', pid, p, cand)
    native, _ = write_fixture_native_output(store, pid, p, cand, sub)
    following = replan_after_native_candidate(store, 'owner', pid, p, cand, sub,
                                               axis((26,)), selected=0)
    native.write_text('m,f (GHz),a,Q\n1,6.9,1,20000\n', encoding='utf-8')
    with pytest.raises(OptimizationBlocked, match='Previous native artifact'):
        submit(store, jobs, 'owner', pid, following, following.candidates[0])
    assert store.project('owner', pid)['head'] == sub.revision_id
    assert len(jobs.calls) == 1


def test_goal_spec_revision_integrity_cannot_be_substituted_after_submit(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid, p, cand)
    write_fixture_native_output(store, pid, p, cand, sub)
    tampered = replace(p, objectives=(Goal('altered', 'em.mode_frequency', 'GHz',
                'target', 7.0, (('mode_label', 'different'),), tolerance=0.02),))
    with pytest.raises(OptimizationBlocked, match='review changed'):
        inspect_native_candidate(store, 'owner', pid, tampered, cand, sub)
    broken_budget = replace(p, native_budget_seconds=3600)
    with pytest.raises(OptimizationBlocked, match='candidate or source binding'):
        inspect_native_candidate(store, 'owner', pid, broken_budget, cand, sub)


def test_native_route_never_scores_wrong_study_or_unverified_rf_ports(tmp_path):
    for kind, expected_mode, expected_rf in (
        ('eigenmode', 'BLOCKED_UNVERIFIED_COMPLEX_FIELD_MODE_IDENTITY',
                      'BLOCKED_INCOMPATIBLE_NATIVE_STUDY_KIND'),
        ('sparameters', 'BLOCKED_INCOMPATIBLE_NATIVE_STUDY_KIND',
                        'BLOCKED_UNREVIEWED_PORT_AND_REFERENCE_PLANE_IDENTITY'),
    ):
        m = model()
        m['studies'][0]['kind'] = kind
        store = Store(tmp_path / kind)
        created = store.create('owner', 'RF prototype', 'resonator', m)
        p = plan(m, created['head'])
        cand = p.candidates[0]
        sub = submit(store, FixtureJobManager(store), 'owner', created['id'], p, cand)
        write_fixture_native_output(store, created['id'], p, cand, sub)
        evidence = inspect_native_candidate(store, 'owner', created['id'], p, cand, sub)
        assert evidence['objective_results'][0]['status'] == expected_mode
        assert evidence['constraint_results'][0]['status'] == expected_rf
        assert all(r['value'] is None for r in evidence['objective_results'] + evidence['constraint_results'])
        assert (evidence['native_observations_unassigned'] is None) == (kind != 'eigenmode')


def test_fresh_job_registration_prevents_false_submitted_result(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    old_id = 'a' * 32
    folder = store.root / 'native-runs' / pid / old_id
    folder.mkdir(parents=True)
    store.put_run('owner', pid, p.source_revision, 'em1', 'sqdmetal_palace', folder)
    class CachedManager:
        def start(self, owner, project_id, revision, study_id, *, force):
            assert force is True
            return old_id
    sub = submit(store, CachedManager(), 'owner', pid, p, cand)
    assert sub.status == 'BLOCKED_NATIVE_SUBMISSION'
    assert sub.run_id is None
    assert 'stale' in sub.reason
    assert store.project('owner', pid)['head'] == sub.revision_id


def test_malformed_native_eigenfrequency_is_blocked_not_promoted(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid, p, cand)
    native, manifest_path = write_fixture_native_output(store, pid, p, cand, sub)
    native.write_text('m,f (GHz),a,Q\n1,nan,1,20000\n', encoding='utf-8')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['artifacts'][0]['sha256'] = sha_bytes(native.read_bytes())
    manifest['artifacts'][0]['bytes'] = native.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(OptimizationBlocked, match='observations are invalid'):
        inspect_native_candidate(store, 'owner', pid, p, cand, sub)


def test_three_step_revision_bound_lifetime_budget_and_scientific_holds(tmp_path):
    """Three linked *fixture* solves max; no silent fourth automatic job."""
    store, pid, first, candidate = setup(tmp_path)
    jobs = FixtureJobManager(store)
    plan_obj = first
    visited = set()
    for n in range(3):
        if n:
            plan_obj = replan_after_native_candidate(
                store, 'owner', pid, plan_obj, candidate, submission,
                axis((24 + n * 2,)), selected=0)
            candidate = plan_obj.candidates[0]
        assert len(plan_obj.native_lineage) == n
        assert plan_obj.planned_native_budget_seconds == 900
        submission = submit(store, jobs, 'owner', pid, plan_obj, candidate)
        assert submission.status == 'NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED'
        assert submission.run_id not in visited
        visited.add(submission.run_id)
        write_fixture_native_output(store, pid, plan_obj, candidate, submission)
        evidence = inspect_native_candidate(store, 'owner', pid, plan_obj, candidate, submission)
        assert evidence['native_lineage_solves_completed'] == n + 1
        assert evidence['native_lineage_budget_seconds'] == 2700
        assert evidence['native_lineage_remaining_seconds'] == (2 - n) * 900
        assert evidence['scientific_qualification'] == 'NOT_ESTABLISHED'
        assert evidence['fabrication_status'] == 'HOLD'
        assert all(g['value'] is None and g['feasible'] is None for g in
                   evidence['objective_results'] + evidence['constraint_results'])
        assert store.project('owner', pid)['revision'] == submission.revision_id
    assert len(jobs.calls) == 3 and all(call[-1] for call in jobs.calls)
    with pytest.raises(OptimizationBlocked, match='Three-solve lifetime budget exhausted'):
        replan_after_native_candidate(store, 'owner', pid, plan_obj, candidate, submission,
                                      axis((32,)), selected=0)
    assert len(jobs.calls) == 3


def test_replan_rejects_sweep_exceeding_remaining_linked_budget(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    jobs = FixtureJobManager(store)
    sub = submit(store, jobs, 'owner', pid, p, cand)
    write_fixture_native_output(store, pid, p, cand, sub)
    with pytest.raises(OptimizationBlocked, match='remaining three-solve lifetime budget'):
        replan_after_native_candidate(store, 'owner', pid, p, cand, sub,
                                      axis((26, 28, 30)), mode='automatic')
    allowed = replan_after_native_candidate(store, 'owner', pid, p, cand, sub,
                                             axis((26, 28)), mode='automatic')
    assert len(allowed.native_lineage) == 1
    assert len(allowed.candidates) == 2
    assert allowed.native_lineage[-1][4] == sub.review_digest
    assert len(jobs.calls) == 1


@pytest.mark.parametrize('kind', ['earlier_manifest', 'earlier_snapshot_material',
                                  'earlier_snapshot_study', 'earlier_review',
                                  'earlier_solver_run', 'earlier_project_revision'])
def test_multistep_rehash_blocks_changed_earlier_solver_and_materials(tmp_path, kind):
    store, pid, p, cand = setup(tmp_path)
    jobs = FixtureJobManager(store)
    sub1 = submit(store, jobs, 'owner', pid, p, cand)
    native1, manifest1 = write_fixture_native_output(store, pid, p, cand, sub1)
    p2 = replan_after_native_candidate(store, 'owner', pid, p, cand, sub1,
                                       axis((26,)), selected=0)
    cand2 = p2.candidates[0]
    sub2 = submit(store, jobs, 'owner', pid, p2, cand2)
    write_fixture_native_output(store, pid, p2, cand2, sub2)
    p3 = replan_after_native_candidate(store, 'owner', pid, p2, cand2, sub2,
                                       axis((28,)), selected=0)
    cand3 = p3.candidates[0]
    folder = store.root / 'native-runs' / pid / sub1.run_id
    if kind == 'earlier_manifest':
        manifest1.write_text('{}', encoding='utf-8')
    elif kind in ('earlier_snapshot_material', 'earlier_snapshot_study'):
        path = folder / 'snapshot.json'
        snap = json.loads(path.read_text(encoding='utf-8'))
        if kind == 'earlier_snapshot_material':
            snap['project']['process']['source'] = 'unverified'
        else:
            snap['study']['engine'] = 'scqubits'
        path.write_text(json.dumps(snap), encoding='utf-8')
    elif kind == 'earlier_review':
        path = store.root / 'optimization-reviews' / pid / (sub1.revision_id + '.json')
        rec = json.loads(path.read_text(encoding='utf-8'))
        rec['native_lineage'] = [['forged']]
        path.write_text(json.dumps(rec), encoding='utf-8')
    elif kind == 'earlier_solver_run':
        with store.conn() as db:
            db.execute('UPDATE runs SET engine=? WHERE id=?', ('scqubits', sub1.run_id))
            db.commit()
    else:
        with store.conn() as db:
            db.execute('UPDATE revisions SET digest=? WHERE id=?', ('0'*64, sub1.revision_id))
            db.commit()
    with pytest.raises(OptimizationBlocked, match='Previous native artifact/review unavailable or stale'):
        submit(store, jobs, 'owner', pid, p3, cand3)
    assert store.project('owner', pid)['head'] == sub2.revision_id
    assert len(jobs.calls) == 2


def test_ledger_shortening_replay_and_solver_mismatch_are_blocked(tmp_path):
    store, pid, p, cand = setup(tmp_path)
    jobs = FixtureJobManager(store)
    sub = submit(store, jobs, 'owner', pid, p, cand)
    write_fixture_native_output(store, pid, p, cand, sub)
    next_plan = replan_after_native_candidate(store, 'owner', pid, p, cand, sub,
                                              axis((26,)), selected=0)
    next_candidate = next_plan.candidates[0]
    # A source anchor cannot be presented without its provenance ledger.
    for changed in (replace(next_plan, native_lineage=()),
                    replace(next_plan, native_lineage=(('a'*32, 'b'*64, 'c'*32,
                                                       'd'*64, 'e'*64),)),
                    replace(next_plan, planned_native_budget_seconds=2700)):
        with pytest.raises(OptimizationBlocked, match='candidate or source binding'):
            submit(store, jobs, 'owner', pid, changed, next_candidate)
    assert store.project('owner', pid)['head'] == sub.revision_id
    assert len(jobs.calls) == 1

    class WrongSolverManager:
        def start(self, owner, project_id, revision, study_id, *, force):
            assert force is True
            folder = store.root / 'native-runs' / project_id / uuid.uuid4().hex
            folder.mkdir(parents=True)
            return store.put_run(owner, project_id, revision, study_id, 'scqubits', folder)

    bad = submit(store, WrongSolverManager(), 'owner', pid, next_plan, next_candidate)
    assert bad.status == 'BLOCKED_NATIVE_SUBMISSION' and bad.run_id is None
    assert 'stale' in bad.reason
    assert store.project('owner', pid)['head'] == bad.revision_id


def test_candidate_non_geometry_changes_cannot_sneak_into_a_saved_geometry_revision(tmp_path):
    for kind in ('same_geometry', 'changed_material', 'changed_solver'):
        store, pid, p, cand = setup(tmp_path / kind)
        jobs = FixtureJobManager(store)
        snapshot = copy.deepcopy(cand.project)
        if kind == 'same_geometry':
            snapshot['layout']['components'][0]['options']['box_width_um'] = 22
        elif kind == 'changed_material':
            snapshot['process']['source'] = 'unverified'
        else:
            snapshot['studies'][0]['engine'] = 'scqubits'
        # Do not let a caller replace the planned immutable snapshot to inject
        # a material/solver change or a zero-change geometry with a stale digest.
        with pytest.raises(OptimizationBlocked, match='candidate or source binding'):
            submit(store, jobs, 'owner', pid, p, replace(cand, project=snapshot))
        assert store.project('owner', pid)['head'] == p.source_revision
        assert jobs.calls == []

# RC14.10 / B10: actual persistent Store revision and named CAD parameter
# comparison. These are deterministic CAD facts, NOT Palace/EM/quantum data.
from sqe_studio.orchestration.optimization import inspect_saved_geometry_candidate


def cad_goal(target=26):
    return Goal('box_target', 'cad.dimension', 'um', 'target', target,
                (('parameter_path', 'layout.components.R1.options.box_width_um'),),
                tolerance=0.1)


def cad_constraint():
    return Goal('max_box', 'cad.dimension', 'um', 'at_most', 25,
                (('parameter_path', 'layout.components.R1.options.box_width_um'),))


def cad_plan(project, revision, *, selected=0, values=(24, 26)):
    return plan_optimization(project, revision, 'em1', axis(values),
                             objectives=(cad_goal(), mode_goal()),
                             constraints=(cad_constraint(), rf_goal()),
                             mode='manual', selected=selected)


def test_b10_real_store_cad_objective_is_available_when_native_solver_blocked(tmp_path):
    store = Store(tmp_path / 'private')
    saved = store.create('owner', 'B10 CAD', 'resonator', model())
    p = cad_plan(saved['model'], saved['head'])
    candidate = p.candidates[0]
    assert candidate.project['layout']['components'][0]['options']['box_width_um'] == 24
    sub = submit(store, FixtureJobManager(store, fail=True), 'owner', saved['id'], p, candidate)
    assert sub.status == 'BLOCKED_NATIVE_SUBMISSION' and sub.review_digest
    evidence = inspect_saved_geometry_candidate(store, 'owner', saved['id'], p, candidate, sub)
    assert evidence['status'] == 'VERIFIED_SAVED_CAD_ONLY'
    assert evidence['source_revision_id'] == saved['head']
    assert evidence['candidate_revision_id'] == sub.revision_id
    assert evidence['native_run_id'] is None
    assert evidence['native_runtime_seconds'] is None
    cad, mode = evidence['objective_results']
    assert cad['status'] == 'VERIFIED_CAD_PARAMETER_ONLY'
    assert cad['source_value'] == 22 and cad['value'] == 24 and cad['delta'] == 2
    assert cad['unit'] == 'um' and cad['feasible'] is False
    assert cad['physical_objective'] is False and cad['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert mode['value'] is None and mode['feasible'] is None
    assert mode['status'] == 'BLOCKED_NATIVE_PHYSICAL_EVIDENCE_NOT_VERIFIED'
    bound, rf = evidence['constraint_results']
    assert bound['feasible'] is True and bound['value'] == 24
    assert rf['value'] is None and rf['feasible'] is None
    assert evidence['fabrication_status'] == 'HOLD'
    with pytest.raises(OptimizationBlocked):
        inspect_native_candidate(store, 'owner', saved['id'], p, candidate, sub)
    with pytest.raises(Exception):
        inspect_saved_geometry_candidate(store, 'other-owner', saved['id'], p, candidate, sub)


def test_b10_linked_real_revisions_compare_different_cad_targets_without_physical_scoring(tmp_path):
    store = Store(tmp_path / 'private')
    original = store.create('owner', 'Two revised CAD designs', 'resonator', model())
    pid = original['id']
    jobs = FixtureJobManager(store)
    p1 = cad_plan(original['model'], original['head'])
    c1 = p1.candidates[0]
    sub1 = submit(store, jobs, 'owner', pid, p1, c1)
    write_fixture_native_output(store, pid, p1, c1, sub1)  # generated test fixture; not a Palace solve
    first = inspect_native_candidate(store, 'owner', pid, p1, c1, sub1)
    assert first['objective_results'][0]['value'] == 24
    assert first['objective_results'][0]['feasible'] is False
    assert first['objective_results'][1]['value'] is None
    assert first['native_runtime_seconds'] is None
    assert first['geometry_comparison']['source_project_digest'] == digest(original['model'])
    assert first['geometry_comparison']['candidate_project_digest'] == c1.project_digest
    assert first['status'] == 'VERIFIED_NATIVE_ARTIFACT_REVIEW_REQUIRED'
    assert first['scientific_qualification'] == 'NOT_ESTABLISHED'
    p2 = replan_after_native_candidate(store, 'owner', pid, p1, c1, sub1,
                                       axis((26,)), selected=0)
    c2 = p2.candidates[0]
    sub2 = submit(store, jobs, 'owner', pid, p2, c2)
    second = inspect_saved_geometry_candidate(store, 'owner', pid, p2, c2, sub2)
    assert second['source_revision_id'] == sub1.revision_id
    assert second['candidate_revision_id'] == sub2.revision_id
    assert second['objective_results'][0]['source_value'] == 24
    assert second['objective_results'][0]['value'] == 26
    assert second['objective_results'][0]['feasible'] is True
    assert second['constraint_results'][0]['feasible'] is False
    assert second['objective_results'][1]['value'] is None
    assert second['native_lineage_solves_completed'] == 1
    assert second['native_lineage_remaining_seconds'] == 1800
    assert len(jobs.calls) == 2 and all(call[-1] is True for call in jobs.calls)
    assert store.project('owner', pid)['head'] == sub2.revision_id
    # Source-of-truth is two distinct persisted project snapshot hashes.
    assert store.project('owner', pid, sub1.revision_id)['revision_digest'] == c1.project_digest
    assert store.project('owner', pid, sub2.revision_id)['revision_digest'] == c2.project_digest


@pytest.mark.parametrize('bad', [
    lambda: Goal('x', 'cad.dimension', 'dB', 'target', 20,
                 (('parameter_path', 'layout.chip.width_mm'),), tolerance=1),
    lambda: Goal('x', 'cad.dimension', 'um', 'target', 20,
                 (('parameter_path', 'layout.components.R1.options.box_width_um.__class__'),), tolerance=1),
    lambda: Goal('x', 'cad.dimension', 'um', 'target', 20,
                 (('parameter_path', 'layout.components.R1.options.0'),), tolerance=1),
])
def test_b10_goal_rejects_ambiguous_units_and_non_dimension_paths(bad):
    with pytest.raises(ValueError):
        bad()


def test_b10_plan_rejects_unit_mismatch_and_unrecognized_saved_dimension():
    wrong = Goal('box', 'cad.dimension', 'mm', 'target', 22,
                 (('parameter_path', 'layout.components.R1.options.box_width_um'),), tolerance=1)
    with pytest.raises(OptimizationBlocked, match='unit'):
        plan_optimization(model(), 'rev0', 'em1', axis(), objectives=(wrong,),
                          mode='manual', selected=0)
    missing = Goal('box', 'cad.dimension', 'um', 'target', 22,
                   (('parameter_path', 'layout.components.R1.options.fake_um'),), tolerance=1)
    with pytest.raises(OptimizationBlocked, match='saved named dimension'):
        plan_optimization(model(), 'rev0', 'em1', axis(), objectives=(missing,),
                          mode='manual', selected=0)


@pytest.mark.parametrize('tamper', ['source_revision', 'candidate_revision', 'review', 'job_id'])
def test_b10_cad_inspection_never_trusts_tampered_store_or_review(tmp_path, tamper):
    store = Store(tmp_path / 'private')
    saved = store.create('owner', 'B10 CAD', 'resonator', model())
    p = cad_plan(saved['model'], saved['head'])
    c = p.candidates[0]
    sub = submit(store, FixtureJobManager(store), 'owner', saved['id'], p, c)
    if tamper in ('source_revision', 'candidate_revision'):
        rid = saved['head'] if tamper == 'source_revision' else sub.revision_id
        with store.conn() as db:
            db.execute('UPDATE revisions SET digest=? WHERE id=?', ('0'*64, rid))
            db.commit()
    elif tamper == 'review':
        path = store.root / 'optimization-reviews' / saved['id'] / (sub.revision_id + '.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        data['review']['rationale'] = 'A replacement rationale without same digest.'
        path.write_text(json.dumps(data), encoding='utf-8')
    else:
        sub = replace(sub, run_id=uuid.uuid4().hex)
    with pytest.raises((OptimizationBlocked, ValueError)):
        inspect_saved_geometry_candidate(store, 'owner', saved['id'], p, c, sub)


def test_b10_recomputed_candidate_sha_cannot_smuggle_non_cad_revision(tmp_path):
    store = Store(tmp_path / 'private')
    saved = store.create('owner', 'B10 CAD', 'resonator', model())
    p = cad_plan(saved['model'], saved['head'])
    candidate = p.candidates[0]
    edited = copy.deepcopy(candidate.project)
    edited['process']['source'] = 'unverified'  # legal schema value, forbidden hidden change
    pdigest = digest(edited)
    geometry_digest = digest({'layout': edited['layout'], 'process': edited['process']})
    forged = replace(candidate, project=edited, project_digest=pdigest,
                     geometry_digest=geometry_digest,
                     candidate_digest=digest({
                         'source_revision': candidate.source_revision,
                         'source_project_digest': candidate.source_project_digest,
                         'project_digest': pdigest, 'coordinates': candidate.coordinates}))
    forged_plan = replace(p, candidates=(forged,))
    jobs = FixtureJobManager(store)
    with pytest.raises(OptimizationBlocked, match='non-parameter'):
        submit(store, jobs, 'owner', saved['id'], forged_plan, forged)
    assert store.project('owner', saved['id'])['head'] == saved['head']
    assert jobs.calls == []


def test_b10_minimize_is_cad_measurement_not_automatic_rank_or_scientific_pass(tmp_path):
    store = Store(tmp_path / 'private')
    created = store.create('owner', 'CAD direction', 'resonator', model())
    direct = Goal('min_width', 'cad.dimension', 'um', 'minimize', 0,
                  (('parameter_path', 'layout.components.R1.options.box_width_um'),))
    p = plan_optimization(created['model'], created['head'], 'em1', axis((24,)),
                          objectives=(direct,), mode='manual', selected=0)
    c = p.candidates[0]
    sub = submit(store, FixtureJobManager(store, fail=True), 'owner', created['id'], p, c)
    measure = inspect_saved_geometry_candidate(store, 'owner', created['id'], p, c, sub)
    result = measure['objective_results'][0]
    assert result['value'] == 24 and result['delta'] == 2
    assert result['feasible'] is None and result['physical_objective'] is False
    assert measure['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert measure['fabrication_status'] == 'HOLD'

# RC14.11 B10: Stored SHA-bound revision/mesh pairs are NOT physical mode matches.
# Every Palace-looking output here is constructed by a test fixture, not native.
def _add_b10_fixture_mesh(store, pid, submission, *, mesh_bytes):
    output = store.root / 'native-runs' / pid / submission.run_id / 'output'
    mesh = output / 'sqe_em' / 'model.msh'
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_bytes(mesh_bytes)
    path = output / 'RESULT_MANIFEST.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['artifacts'].append({'name': 'sqe_em/model.msh',
                                  'sha256': sha_bytes(mesh_bytes), 'bytes': len(mesh_bytes)})
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return mesh, path


def _b10_two_fixture_revisions(tmp_path, *, first_mesh=b'$MeshFormat\nfixture1',
                               second_mesh=b'$MeshFormat\nfixture2', missing=()):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, first, c1 = setup(tmp_path)
    jobs = FixtureJobManager(store)
    s1 = submit(store, jobs, 'owner', pid, first, c1)
    write_fixture_native_output(store, pid, first, c1, s1)
    if 'first' not in missing:
        _add_b10_fixture_mesh(store, pid, s1, mesh_bytes=first_mesh)
    second = replan_after_native_candidate(store, 'owner', pid, first, c1, s1,
                                           axis((26,)), selected=0)
    c2 = second.candidates[0]
    s2 = submit(store, jobs, 'owner', pid, second, c2)
    write_fixture_native_output(store, pid, second, c2, s2)
    if 'second' not in missing:
        _add_b10_fixture_mesh(store, pid, s2, mesh_bytes=second_mesh)
    return store, pid, second, c2, s2


def test_b10_two_revision_mesh_hashes_bound_but_mode_scoring_still_blocked(tmp_path):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, plan2, cand2, sub2 = _b10_two_fixture_revisions(tmp_path)
    result = inspect_b10_revision_pair(store, 'owner', pid, plan2, cand2, sub2)
    assert result['schema'] == 'sqe.b10-locked-revision-pair.v1'
    assert result['case_id'] == 'B10' and result['stage_status'] == 'BLOCKED'
    assert result['blocker'] == 'BLOCKED_INDEPENDENT_COMPLEX_FIELD_REGISTRATION_AND_MODE_IDENTITY_REVIEW'
    assert result['execution_kind'] == 'REPLAY_EXISTING_EVIDENCE'
    assert result['native_fresh_execution_this_call'] is False
    assert result['source']['mesh_sha256'] != result['candidate']['mesh_sha256']
    assert result['source']['revision_id'] == plan2.source_revision
    assert result['source']['manifest_sha256'] == plan2.source_native_manifest_sha256
    assert result['candidate']['revision_id'] == sub2.revision_id
    assert result['candidate']['project_digest'] == cand2.project_digest
    assert result['geometry_delta']['coordinates'] == [['layout.components.R1.options.box_width_um',26]]
    assert result['mode_overlap'] is None and result['mode_identity'] == 'UNRESOLVED'
    assert result['physical_objectives_evaluated'] is False
    assert result['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert result['fabrication_status'] == 'HOLD'
    assert all(r['value'] is None and r['feasible'] is None for r in
               result['objective_results'] + result['constraint_results'])
    edges = {x['id']: x for x in list_capabilities()}
    assert edges['native_revisions_to_b10_mode_review']['status'] == 'verified_inspection'
    assert edges['native_em_to_geometry_objectives']['status'] == 'blocked'


@pytest.mark.parametrize('missing', [('first',), ('second',), ('first', 'second')])
def test_b10_missing_source_or_candidate_mesh_never_scores(tmp_path, missing):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, p, c, s = _b10_two_fixture_revisions(tmp_path, missing=missing)
    evidence = inspect_b10_revision_pair(store, 'owner', pid, p, c, s)
    assert evidence['stage_status'] == 'BLOCKED'
    assert evidence['blocker'] == 'BLOCKED_NO_UNAMBIGUOUS_VERIFIED_GMSH_MESH'
    assert evidence['mode_overlap'] is None


def test_b10_same_mesh_bytes_across_distinct_geometry_are_rejected(tmp_path):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    mesh = b'$MeshFormat\nunchanged fixture'
    store, pid, p, c, s = _b10_two_fixture_revisions(tmp_path, first_mesh=mesh, second_mesh=mesh)
    evidence = inspect_b10_revision_pair(store, 'owner', pid, p, c, s)
    assert evidence['blocker'] == 'BLOCKED_IDENTICAL_MESH_FOR_CHANGED_CAD_REVISIONS'
    assert evidence['source']['mesh_sha256'] == evidence['candidate']['mesh_sha256']
    assert evidence['physical_objectives_evaluated'] is False


@pytest.mark.parametrize('tamper', ['source_mesh', 'candidate_mesh', 'manifest', 'run', 'review', 'wrong_owner'])
def test_b10_pair_rejects_stale_or_unowned_scientific_evidence(tmp_path, tamper):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, p, c, s = _b10_two_fixture_revisions(tmp_path)
    if tamper in ('source_mesh', 'candidate_mesh'):
        run_id = p.source_native_run_id if tamper == 'source_mesh' else s.run_id
        mesh = store.root / 'native-runs' / pid / run_id / 'output' / 'sqe_em' / 'model.msh'
        mesh.write_bytes(b'$MeshFormat\nmalicious replacement')
    elif tamper == 'manifest':
        path = store.root / 'native-runs' / pid / s.run_id / 'output' / 'RESULT_MANIFEST.json'
        path.write_text('{}', encoding='utf-8')
    elif tamper == 'review':
        path = store.root / 'optimization-reviews' / pid / (s.revision_id + '.json')
        rec = json.loads(path.read_text(encoding='utf-8'))
        rec['native_lineage'] = []
        path.write_text(json.dumps(rec), encoding='utf-8')
    elif tamper == 'run':
        store.set_run(p.source_native_run_id, 'failed')
    owner = 'another-owner' if tamper == 'wrong_owner' else 'owner'
    with pytest.raises((OptimizationBlocked, ValueError)):
        inspect_b10_revision_pair(store, owner, pid, p, c, s)


def test_b10_pair_wont_accept_unanchored_first_iteration_or_wrong_study(tmp_path):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, p, c = setup(tmp_path)
    sub = submit(store, FixtureJobManager(store), 'owner', pid, p, c)
    write_fixture_native_output(store, pid, p, c, sub)
    with pytest.raises(OptimizationBlocked, match='completed source revision'):
        inspect_b10_revision_pair(store, 'owner', pid, p, c, sub)
    store, pid, p, c, sub = _b10_two_fixture_revisions(tmp_path/'other')
    with pytest.raises(OptimizationBlocked, match='completed source revision'):
        inspect_b10_revision_pair(store, 'owner', pid, replace(p, source_native_run_id='0'*32), c, sub)


def test_b10_same_adapter_but_solver_version_change_is_not_comparable(tmp_path):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, p, c, s = _b10_two_fixture_revisions(tmp_path)
    output = store.root / 'native-runs' / pid / s.run_id / 'output'
    path = output / 'RESULT_MANIFEST.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['engine_version'] = 'another-fixture-version'
    record['cache_fingerprint'] = fingerprint(
        revision_id=s.revision_id, project_digest=c.project_digest,
        study=c.project['studies'][0], native_version='another-fixture-version',
        adapter_sha256=adapter_digest('sqdmetal_palace'))
    path.write_text(json.dumps(record), encoding='utf-8')
    result = inspect_b10_revision_pair(store, 'owner', pid, p, c, s)
    assert result['blocker'] == 'BLOCKED_DIFFERENT_NATIVE_SOLVER_VERSIONS'
    assert result['mode_identity'] == 'UNRESOLVED'


def test_b10_ambiguous_multiple_meshes_are_not_a_usable_lock(tmp_path):
    from sqe_studio.orchestration.optimization import inspect_b10_revision_pair
    store, pid, p, c, s = _b10_two_fixture_revisions(tmp_path)
    output = store.root / 'native-runs' / pid / s.run_id / 'output'
    extra = output / 'sqe_em' / 'other.msh'
    extra.write_bytes(b'$MeshFormat\nother mesh fixture')
    manifest = output / 'RESULT_MANIFEST.json'
    record = json.loads(manifest.read_text(encoding='utf-8'))
    record['artifacts'].append({'name': 'sqe_em/other.msh',
                                'sha256': sha_bytes(extra.read_bytes()),
                                'bytes': extra.stat().st_size})
    manifest.write_text(json.dumps(record), encoding='utf-8')
    result = inspect_b10_revision_pair(store, 'owner', pid, p, c, s)
    assert result['blocker'] == 'BLOCKED_NO_UNAMBIGUOUS_VERIFIED_GMSH_MESH'
    assert result['candidate']['mesh_sha256'] is None
