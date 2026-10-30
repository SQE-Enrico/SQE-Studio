"""Worker provenance checks; mocked native adapter is byte fixture only."""
import json
from copy import deepcopy
import pytest
from sqe_studio.contracts import digest, fresh_project
from sqe_studio.orchestration.artifacts import verify_manifest, ArtifactInvalid
from sqe_studio.orchestration.sweep import plan_sweep
from sqe_studio import worker


def snapshot():
    m = fresh_project('Saved Design', 'transmon')
    study = {'id': 'a1', 'engine': 'scqubits', 'kind': 'spectrum',
             'inputs': {'model': 'Transmon', 'parameters': {'EJ': 10.0, 'EC': 0.2,
                         'ng': 0.0, 'ncut': 12}, 'levels': 4}}
    m['studies'].append(study)
    return {'project': m, 'project_digest': digest(m),
            'revision_id': 'r1', 'study': deepcopy(study), 'parents': []}


def test_worker_rejects_modified_source_unsaved_study_and_unsafe_sweep():
    s = snapshot()
    assert worker._validated_snapshot(s)[1] == s['study']
    s['project']['layout']['chip']['width_mm'] = 33
    with pytest.raises(ValueError, match='digest'):
        worker._validated_snapshot(s)
    s = snapshot()
    s['study']['inputs']['levels'] = 8
    with pytest.raises(ValueError, match='differs'):
        worker._validated_snapshot(s)
    s = snapshot()
    p = plan_sweep(s['study'], {'parameters.EJ': [9.0]}, mode='manual', selected=0)[0]
    s['study'] = p.study
    s['sweep_point'] = {'index': p.index, 'mode': 'manual',
                        'options_digest': p.options_digest,
                        'coordinates': list(map(list, p.coordinates))}
    assert worker._validated_snapshot(s)[1] == p.study
    s['study']['inputs']['parameters']['EC'] = 2.0
    with pytest.raises(ValueError, match='recorded numeric'):
        worker._validated_snapshot(s)


def test_worker_native_mock_manifest_is_rehashed_and_not_qualified(tmp_path, monkeypatch):
    s = snapshot()
    p = tmp_path/'snapshot.json'
    p.write_text(json.dumps(s))
    def fixture(study, model, root):
        (root/'fixture.bin').write_bytes(b'NOT PHYSICS')
        return {'engine_version': 'TEST-FIXTURE-ONLY', 'native_files': ['fixture.bin'],
                'kind': 'quantum_spectrum'}
    monkeypatch.setitem(worker.REGISTRY, 'scqubits', fixture)
    monkeypatch.setattr(worker, 'adapter_digest', lambda engine: 'a'*64)
    root = tmp_path/'output'
    assert worker.run(p, root) == 0
    m = json.loads((root/'RESULT_MANIFEST.json').read_text())
    assert m['scientific_status'] == 'review_required'
    assert m['fabrication_status'] == 'HOLD'
    assert m['parents'] == []
    assert m['engine_version'] == 'TEST-FIXTURE-ONLY'
    assert m['cache_fingerprint']
    assert verify_manifest(root, revision_id='r1', project_digest=s['project_digest'])
    (root/'fixture.bin').write_bytes(b'TAMPERED')
    with pytest.raises(ArtifactInvalid, match='changed'):
        verify_manifest(root, revision_id='r1', project_digest=s['project_digest'])


def test_worker_rejects_unlisted_native_files(tmp_path, monkeypatch):
    s = snapshot()
    p = tmp_path/'snapshot.json'
    p.write_text(json.dumps(s))
    def fixture(study, model, root):
        (root/'fixture.bin').write_bytes(b'fixture')
        (root/'undeclared.bin').write_bytes(b'unlisted')
        return {'engine_version': 'TEST-FIXTURE-ONLY', 'native_files': ['fixture.bin'],
                'kind': 'quantum_spectrum'}
    monkeypatch.setitem(worker.REGISTRY, 'scqubits', fixture)
    monkeypatch.setattr(worker, 'adapter_digest', lambda engine: 'a'*64)
    with pytest.raises(ArtifactInvalid, match='undeclared'):
        worker.run(p, tmp_path/'output')
    assert not (tmp_path/'output'/'RESULT_MANIFEST.json').exists()
