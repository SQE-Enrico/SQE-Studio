"""Synthetic byte fixtures test integrity ONLY; no native acceptance claimed."""
import json
from pathlib import Path
import pytest
from sqe_studio.orchestration.artifacts import (
    ArtifactInvalid, sha_bytes, fingerprint, verify_manifest, safe_file)


def make_manifest(root: Path, *, rev='r1', source='a'*64, cache='b'*64):
    root.mkdir(parents=True, exist_ok=True)
    (root/'payload.bin').write_bytes(b'unqualified test bytes')
    manifest = {'schema': 'sqe.artifact.v1', 'engine': 'scqubits',
                'engine_version': 'TEST-FIXTURE-ONLY', 'kind': 'quantum_spectrum',
                'artifact_type': 'scqubits.spectrum', 'scientific_status': 'review_required',
                'fabrication_status': 'HOLD', 'revision_id': rev,
                'project_digest': source, 'study_id': 's1', 'cache_fingerprint': cache,
                'provenance': {'used_revision': rev, 'used_project_sha256': source},
                'parents': [], 'artifacts': [{'name': 'payload.bin',
                'sha256': sha_bytes(b'unqualified test bytes'), 'bytes': len(b'unqualified test bytes')}]}
    (root/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
    return manifest


def test_artifact_provenance_and_rehash(tmp_path):
    manifest = make_manifest(tmp_path)
    ref = verify_manifest(tmp_path, revision_id='r1', project_digest='a'*64,
                          study_id='s1', engine='scqubits', cache_fingerprint='b'*64)
    assert ref.artifact_type == 'scqubits.spectrum'
    assert len(ref.manifest_sha256) == 64
    assert ref.as_parent()['manifest_sha256'] == ref.manifest_sha256
    with pytest.raises(ArtifactInvalid, match='old or different'):
        verify_manifest(tmp_path, revision_id='r2', project_digest='a'*64)
    with pytest.raises(ArtifactInvalid, match='Stale fingerprint'):
        verify_manifest(tmp_path, revision_id='r1', project_digest='a'*64,
                        cache_fingerprint='c'*64)
    (tmp_path/'payload.bin').write_bytes(b'modified')
    with pytest.raises(ArtifactInvalid, match='changed'):
        verify_manifest(tmp_path, revision_id='r1', project_digest='a'*64)


def test_invalid_native_paths_and_manifest_claims(tmp_path):
    with pytest.raises(ArtifactInvalid):
        safe_file(tmp_path, '../outside')
    with pytest.raises(ArtifactInvalid):
        safe_file(tmp_path, 'C:\\Windows\\system32')
    m = make_manifest(tmp_path)
    m['fabrication_status'] = 'PASS'
    (tmp_path/'RESULT_MANIFEST.json').write_text(json.dumps(m))
    with pytest.raises(ArtifactInvalid, match='fabrication'):
        verify_manifest(tmp_path, revision_id='r1', project_digest='a'*64)
    m['fabrication_status'] = 'HOLD'
    m['parents'] = [{'revision_id': 'r0', 'project_digest': 'a'*64, 'manifest_sha256': 'd'*64}]
    (tmp_path/'RESULT_MANIFEST.json').write_text(json.dumps(m))
    with pytest.raises(ArtifactInvalid, match='upstream'):
        verify_manifest(tmp_path, revision_id='r1', project_digest='a'*64)


def test_fingerprint_invalidates_exact_inputs_engine_and_adapter():
    kw = {'revision_id': 'r1', 'project_digest': 'a'*64,
          'study': {'engine': 'scqubits', 'inputs': {'EJ': 3}},
          'native_version': '4.3', 'adapter_sha256': 'b'*64,
          'parent_sha256': ('c'*64,)}
    key = fingerprint(**kw)
    assert key == fingerprint(**kw)
    for field, value in [('revision_id','r2'), ('project_digest','d'*64),
                         ('native_version','4.4'), ('adapter_sha256','e'*64),
                         ('parent_sha256',('f'*64,)),
                         ('study', {'engine': 'scqubits', 'inputs': {'EJ': 4}})]:
        assert fingerprint(**{**kw, field:value}) != key
    with pytest.raises(ArtifactInvalid):
        fingerprint(**{**kw, 'native_version': ''})
