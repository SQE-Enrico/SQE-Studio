"""All CSV/deck bytes below are fixture-only; NO Palace/Quantum Metal run is performed."""
import copy
import json
from pathlib import Path

import pytest

from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.quantum_metal_adapter import validate_recipe
from sqe_studio.adapters.sqdmetal_palace_adapter import preflight
from sqe_studio.contracts import digest, validate_project
from sqe_studio.interop.laptop_benchmark import (
    BenchmarkBlocked, _native_eig, approve_exploratory_stack,
    assess_native_run, compare_refinements, prepare_kinetic_deck, resonator_project,
)
from sqe_studio.orchestration.artifacts import sha_bytes


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data if isinstance(data, bytes) else json.dumps(data).encode('utf-8')
    path.write_bytes(raw)
    return {'name': str(path), 'sha256': sha_bytes(raw), 'bytes': len(raw)}


def _reviewed(tmp_path, *, execution='solve'):
    model = resonator_project(execution=execution)
    evidence = tmp_path / 'assumptions.md'
    evidence.write_text('Research assumptions only: silicon 11.7, Al film assumed, not independently measured.\n')
    reviewed, record = approve_exploratory_stack(model, reviewer='PhysicsReviewer',
                 document=evidence, source_url='https://sqdlab.github.io/SQDMetal/examples/Palace_Eigenmode_Res_Gmsh.html')
    return reviewed, evidence, record


def _fixture(tmp_path, model, *, run='run', frequency=5.01, kind='eigenmode', output_type='palace.eigenmodes'):
    root = tmp_path / run
    sidecar = {'schema':'sqe.a03.native-artifacts.v1', 'execution':'solve',
               'native_completion':{'exit_code':0},'versions':{'palace':'Palace 0.15'}}
    data = [('sqe_em/sqe_em.msh', b'$MeshFormat\n4.1 0 8\n'),
            ('sqe_em/sqe_em.json', json.dumps({'Problem': {'Type':'Eigenmode','Output':'outputFiles'},
                                               'Model':{'Mesh':'sqe_em.msh'},
                                               'Boundaries':{'PEC':{'Attributes':[1,2,3,4]},
                                                           'LumpedPort':[{'Index':1,'Attributes':[9]}]}}).encode()),
            ('sqe_em/outputFiles/eig.csv', f'Mode,Re{{f}} (GHz),Quality\n1,{frequency},1000\n'.encode()),
            ('sqe_em/palace-native.log', b'fixture -- NOT A SOLVER LOG\n'),
            ('a03-native-artifacts.json', json.dumps(sidecar).encode())]
    entries = []
    for name, content in data:
        _write(root / name, content)
        entries.append({'name':name,'sha256':sha_bytes(content),'bytes':len(content)})
    manifest = {'schema':'sqe.artifact.v1','engine':'sqdmetal_palace',
                'engine_version':'SQDMetal 1.0; Gmsh 4.12; Palace 0.15',
                'revision_id':'1'*32, 'project_digest':digest(model),
                'study_id':'ResEigen','kind':kind,'artifact_type':output_type,
                'fabrication_status':'HOLD','scientific_status':'review_required',
                'provenance':{'used_revision':'1'*32,'used_project_sha256':digest(model)},
                'parents':[],'artifacts':entries}
    _write(root / 'RESULT_MANIFEST.json', manifest)
    return root


def _surface_review(tmp_path, source, *, metal=(1,2), excluded=(3,4)):
    from sqe_studio.interop.laptop_benchmark import _sha
    path = tmp_path / ('review-' + source.name + '.json')
    path.write_text(json.dumps({
        'schema':'sqe.research-metal-surfaces.v1',
        'source_deck_sha256':_sha(source/'sqe_em/sqe_em.json'),
        'source_mesh_sha256':_sha(source/'sqe_em/sqe_em.msh'),
        'reviewer':'PhysicsReviewer', 'basis':'manual_gmsh_physical_group_review',
        'conductor_attributes':list(metal), 'excluded_attributes':list(excluded)}))
    return path


def test_paper_adapted_recipe_is_gateable(tmp_path):
    p = resonator_project()
    assert p['family'] == 'resonator'
    assert len(validate_recipe(p['layout'])[0]) == 6
    assert all(x.options['trace_gap'] == '6um' for x in validate_recipe(p['layout'])[0]
               if x.kind.startswith('Route'))
    validate_project(p)
    with pytest.raises(EngineBlocked, match='reviewed'):
        preflight(p['studies'][0], p)
    ready, evidence, record = _reviewed(tmp_path)
    assert ready['process']['source'] == 'reviewed'
    assert len(record['review_evidence_sha256']) == 64
    assert preflight(ready['studies'][0], ready)
    evidence.write_text('subsequently altered')
    assert record['review_evidence_sha256'] != sha_bytes(evidence.read_bytes())


def test_review_blocked_for_invalid_identity_or_missing_evidence(tmp_path):
    p = resonator_project()
    with pytest.raises(BenchmarkBlocked):
        approve_exploratory_stack(p, reviewer='n', document=tmp_path / 'no-file',
                                  source_url='https://example.org')
    evidence = tmp_path / 'review.md'; evidence.write_text('review')
    with pytest.raises(BenchmarkBlocked):
        approve_exploratory_stack(p, reviewer='Reviewer', document=evidence,
                                  source_url='file:///etc/passwd')
    with pytest.raises(EngineBlocked, match='unexpected'):
        p['studies'][0]['inputs']['extra'] = {'arbitrary': 'python'}
        preflight(p['studies'][0], {**p, 'process': {**p['process'], 'source':'reviewed'}})


def test_explicit_no_fabrication_and_corrupt_native_rejection(tmp_path):
    ready, _, _ = _reviewed(tmp_path)
    run = _fixture(tmp_path, ready)
    result = assess_native_run(ready, run)
    assert result['fabrication_status'] == 'HOLD'
    assert result['modes'][0]['frequency_GHz'] == 5.01
    (run/'sqe_em/outputFiles/eig.csv').write_text('Mode,Re{f} (GHz),Quality\n1,999,1\n')
    with pytest.raises(BenchmarkBlocked, match='manifest'):
        assess_native_run(ready, run)


def test_eigenmode_parser_rejects_units_empty_and_nonfinite(tmp_path):
    f = tmp_path / 'eig.csv'
    for content in ('Mode,Re{f} (MHz)\n1,5\n',
                    'Mode,Re{f} (GHz)\n',
                    'Mode,Re{f} (GHz)\n1,nan\n',
                    'Mode,Re{f} (GHz)\n2,5\n'):
        f.write_text(content)
        with pytest.raises(BenchmarkBlocked):
            _native_eig(f)


def test_refinement_numeric_difference_requires_consistent_geometry(tmp_path):
    ready, _, _ = _reviewed(tmp_path)
    a = assess_native_run(ready, _fixture(tmp_path, ready, run='a', frequency=5.00))
    b = assess_native_run(ready, _fixture(tmp_path, ready, run='b', frequency=5.05))
    result = compare_refinements([a, b], tolerance=.02)
    assert result['numerical_threshold_met']
    assert result['scientific_qualification'] == 'not_established'
    b['geometry_and_stack_sha256'] = '0'*64
    with pytest.raises(BenchmarkBlocked, match='Geometry'):
        compare_refinements([a, b])
    with pytest.raises(BenchmarkBlocked, match='same native run'):
        compare_refinements([a, a])


def test_kinetic_deck_uses_verified_native_source_and_never_modifies_it(tmp_path):
    ready, evidence, _ = _reviewed(tmp_path)
    source = _fixture(tmp_path, ready, run='native_source', output_type='palace.deck')
    before = (source/'sqe_em/sqe_em.json').read_bytes()
    surface_review = _surface_review(tmp_path, source)
    target = tmp_path/'experimental_kinetic'
    meta = prepare_kinetic_deck(source, target,
             surface_attributes=[1,2], sheet_inductance_h=2.0e-12,
             thickness_nm=20, penetration_depth_nm=120,
             reviewer='PhysicsReviewer', evidence_file=evidence,
             surface_review_file=surface_review, regime='thin')
    config = json.loads((target/'sqe_em_kinetic.json').read_text())
    assert config['Boundaries']['Impedance'] == [{'Attributes':[1,2], 'Ls':2.0e-12, 'Crack':False}]
    assert config['Boundaries']['PEC']['Attributes'] == [3,4]
    assert config['Problem']['Output'] == 'outputFiles_kinetic'
    assert meta['status'] == 'reviewed_input_experimental_deck_not_a_native_result'
    assert (source/'sqe_em/sqe_em.json').read_bytes() == before
    assert (target/'sqe_em.msh').read_bytes() == (source/'sqe_em/sqe_em.msh').read_bytes()
    with pytest.raises(BenchmarkBlocked, match='new, external'):
        prepare_kinetic_deck(source, target, surface_attributes=[1], sheet_inductance_h=2e-12,
                thickness_nm=20, penetration_depth_nm=120, reviewer='PhysicsReviewer',
                evidence_file=evidence, surface_review_file=surface_review, regime='thin')


def test_kinetic_boundary_fail_closed_for_unknown_tag_overlap_and_stale_native(tmp_path):
    ready, evidence, _ = _reviewed(tmp_path)
    source = _fixture(tmp_path, ready, run='kinetic_gates', output_type='palace.deck')
    surface_review = _surface_review(tmp_path, source)
    params = dict(sheet_inductance_h=2e-12, thickness_nm=20,
                  penetration_depth_nm=120, reviewer='PhysicsReviewer',
                  evidence_file=evidence, surface_review_file=surface_review, regime='thin')
    for n, attrs in enumerate(([999], [1,2,3,4], [9])):
        with pytest.raises(BenchmarkBlocked):
            prepare_kinetic_deck(source, tmp_path/f'blocked{n}', surface_attributes=attrs, **params)
        assert not (tmp_path/f'blocked{n}').exists()
    with pytest.raises(BenchmarkBlocked, match='regime'):
        prepare_kinetic_deck(source, tmp_path/'blocked-regime', surface_attributes=[1],
                             **{**params, 'regime':'thick'})
    partial_review = _surface_review(tmp_path, source, metal=(1,), excluded=(3,4))
    with pytest.raises(BenchmarkBlocked, match='All native PEC surfaces'):
        prepare_kinetic_deck(source, tmp_path/'blocked-unclassified', surface_attributes=[1],
                             **{**params, 'surface_review_file': partial_review})
    (source/'sqe_em/sqe_em.json').write_text('{"tampered":true}')
    with pytest.raises(BenchmarkBlocked, match='manifest'):
        prepare_kinetic_deck(source, tmp_path/'blocked-tamper', surface_attributes=[1], **params)


def test_kinetic_deck_rejects_forged_manifest(tmp_path):
    fake = tmp_path/'fake'; (fake/'sqe_em').mkdir(parents=True)
    (fake/'sqe_em/sqe_em.msh').write_text('fixture')
    (fake/'sqe_em/sqe_em.json').write_text('{}')
    (fake/'RESULT_MANIFEST.json').write_text('{}')
    e = tmp_path/'evidence'; e.write_text('evidence')
    with pytest.raises(BenchmarkBlocked):
        prepare_kinetic_deck(fake, tmp_path/'no', surface_attributes=[1],
             sheet_inductance_h=1e-12, thickness_nm=20,
             penetration_depth_nm=100, reviewer='PhysicsReviewer',
             evidence_file=e, surface_review_file=tmp_path/'missing-surface-review', regime='thin')


def test_a03_worker_output_type_and_native_epr_tables_are_not_hidden(tmp_path, monkeypatch):
    """Fixture wiring only, NOT actual Palace execution or valid numerical EPR."""
    import types
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    reviewed, _, _ = _reviewed(tmp_path)
    study = reviewed['studies'][0]
    monkeypatch.setattr(em, '_native_imports', lambda: object())
    monkeypatch.setattr(em, '_palace_readiness', lambda: {'backend':'native', 'version':'fixture Palace',
                                                        'binary_sha256':None, 'command':['not-run']})
    original_import = em.importlib.import_module
    monkeypatch.setattr(em.importlib, 'import_module', lambda name: (
        types.SimpleNamespace(__version__='fixture gmsh') if name == 'gmsh' else original_import(name)))
    def make(study, project, opts, a02, root):
        folder = root/'sqe_em'
        (folder/'outputFiles').mkdir()
        (folder/'sqe_em.msh').write_text('mock meshing fixture')
        (folder/'sqe_em.json').write_text(json.dumps({
            'Problem':{'Type':'Eigenmode', 'Output':'outputFiles'}, 'Model':{'Mesh':'sqe_em.msh'}}))
    def solve(readiness, folder, deck, cpus):
        (folder/'palace-native.log').write_text('test fixture only')
        (folder/'outputFiles/eig.csv').write_text('Mode,Re{f} (GHz)\n1,5.01\n')
        (folder/'outputFiles/port-EPR.csv').write_text('Mode,Port1\n1,0.2\n')
        return {'exit_code':0,'elapsed_seconds':0.0}
    monkeypatch.setattr(em,'_make_native',make)
    monkeypatch.setattr(em,'_run_palace',solve)
    monkeypatch.setattr(em,'_physical_ids', lambda *args: ({1},{2}))
    monkeypatch.setattr(em,'_validate_deck',lambda *args:None)
    root=tmp_path/'fixture-out'
    result=em.run(study,reviewed,root)
    assert result['artifact_type']=='palace.eigenmodes'
    assert 'sqe_em/outputFiles/port-EPR.csv' in result['native_files']
    assert json.loads((root/'a03-native-artifacts.json').read_text())['epr_quantization'].startswith('not_performed')


def test_raw_epr_is_exposed_but_never_interpreted_as_hamiltonian(tmp_path):
    from sqe_studio.interop.laptop_benchmark import _raw_native_epr
    p=tmp_path/'port-EPR.csv'
    p.write_text('Mode,Junction1,Junction2\n1,-0.987,0.002\n2,-0.01,0.003\n')
    result=_raw_native_epr(p)
    assert result['rows'][0]['native_signed_columns'][0] == -0.987
    assert 'not_quantization' in result['status']
    p.write_text('Mode,Junction1\n1,NaN\n')
    with pytest.raises(BenchmarkBlocked, match='Nonfinite'):
        _raw_native_epr(p)


def test_kinetic_native_runner_and_comparison_are_provenance_bound_fixtures(tmp_path, monkeypatch):
    """Subprocess return and CSV are FAKE; tests wiring, not Palace physics."""
    import os
    from sqe_studio.interop import laptop_benchmark as bench
    reviewed, evidence, _ = _reviewed(tmp_path)
    src = _fixture(tmp_path, reviewed, run='solved-reference')
    exp = tmp_path/'kinetic-test'
    surface_review = _surface_review(tmp_path, src)
    bench.prepare_kinetic_deck(src, exp, surface_attributes=[1], sheet_inductance_h=1.0e-12,
          thickness_nm=20, penetration_depth_nm=120, reviewer='PhysicsReviewer',
          evidence_file=evidence, surface_review_file=surface_review, regime='thin')
    palace_bin = tmp_path/'fake-palace'
    palace_bin.write_text('UNIT TEST FIXTURE, NOT AN EXECUTABLE PALACE ENGINE')
    palace_bin.chmod(0o700)
    def fake_runner(args, **kw):
        from types import SimpleNamespace
        if '--version' in args:
            return SimpleNamespace(returncode=0, stdout='Palace fixture-only 0\n', stderr='')
        (exp/'outputFiles_kinetic').mkdir()
        (exp/'outputFiles_kinetic/eig.csv').write_text('Mode,Re{f} (GHz)\n1,4.99\n')
        kw['stdout'].write(b'FIXTURE SOLVE ONLY\n')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(bench.subprocess,'run',fake_runner)
    rec = bench.run_kinetic_native(exp, palace_bin)
    assert rec['scientific_qualification'] == 'not_established'
    comparison = bench.compare_kinetic_native(reviewed, src, exp)
    assert comparison['delta_GHz'] == pytest.approx(-.02)
    assert comparison['status'] == 'read_only_difference_physical_validity_unverified'
    with pytest.raises(BenchmarkBlocked, match='already exists'):
        bench.run_kinetic_native(exp, palace_bin)
    (exp/'outputFiles_kinetic/eig.csv').write_text('Mode,Re{f} (GHz)\n1,4.3\n')
    with pytest.raises(BenchmarkBlocked, match='changed'):
        bench.compare_kinetic_native(reviewed, src, exp)


def test_kinetic_native_binary_is_never_taken_from_input_deck(tmp_path):
    from sqe_studio.interop.laptop_benchmark import run_kinetic_native
    exp=tmp_path/'experiment'
    exp.mkdir()
    (exp/'KINETIC_REVIEW.json').write_text(json.dumps({'schema':'sqe.research-kinetic-deck.v1'}))
    (exp/'sqe_em_kinetic.json').write_text('{}')
    (exp/'sqe_em.msh').write_text('fixture')
    with pytest.raises(BenchmarkBlocked, match='changed'):
        run_kinetic_native(exp, Path('/bin/sh'))
