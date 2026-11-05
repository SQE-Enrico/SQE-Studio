"""RC14.2 security and scientific non-promotion tests (no fixture-as-native claims)."""
from __future__ import annotations

from pathlib import Path
import io
import json
import zipfile
import os

import pytest

from sqe_studio.interop.em_observables import assess_observables, _table
from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
from sqe_studio.mpi_qualification import validate_ranks, _copy_verified_inputs, qualify_mpi_profile

# Optional field-evidence regression: never bundle a user's private report.
REPORT = Path(os.environ.get('SQE_TEST_NATIVE_REPORT', 'tests/fixtures/optional-native-report.zip'))


def test_real_uploaded_native_evidence_observables():
    if not REPORT.is_file():
        pytest.skip('External user report is not part of delivered release')
    record=assess_observables(REPORT)
    assert len(record['points']) == 3
    assert all(point['status']=='NUMERIC_INDICATORS_ONLY' for point in record['points'])
    assert record['points'][2]['negative_coupling_columns']==2
    assert 'KAPPA_SIGN_CHANGED' in {flag['type'] for flag in record['advisory_flags']}
    assert record['mode_identity']=='UNRESOLVED'
    assert record['downstream_automatic_optimization'].startswith('BLOCKED')


def test_reject_modified_evidence(tmp_path):
    if not REPORT.is_file():
        pytest.skip('External report not distributed')
    altered=tmp_path/'tampered.zip'
    with zipfile.ZipFile(REPORT) as origin, zipfile.ZipFile(altered,'w') as dest:
        for item in origin.namelist():
            data=origin.read(item)
            if item.endswith('-port-Q.csv'):
                data+=b'\n1,+99,0\n'
            dest.writestr(item,data)
    with pytest.raises(ConvergenceEvidenceError):
        assess_observables(altered)


def test_reject_nonfinite_or_extra_data():
    with pytest.raises(ConvergenceEvidenceError):
        _table(b'm,Q_ext[1]\n1,nan\n','Q_ext')
    with pytest.raises(ConvergenceEvidenceError):
        _table(b'm,Q_ext[1]\n1,1\n2,1,3\n','Q_ext')


@pytest.mark.parametrize('ranks',[(2,2),(4,2),(0,4),(2,17),[2,4],(2,4,6,8)])
def test_mpi_ranks_invalid(ranks):
    with pytest.raises(ValueError):
        validate_ranks(ranks)


def test_verified_mesh_deck_copy_and_tamper(tmp_path):
    native=tmp_path/'original'/'sqe_em'
    native.mkdir(parents=True)
    hashes={}
    import hashlib
    for name,body in [('sqe_em.msh',b'native mesh'),('sqe_em.json',b'{"native":true}')]:
        (native/name).write_bytes(body)
        hashes['sqe_em/'+name]=hashlib.sha256(body).hexdigest()
    assert _copy_verified_inputs(tmp_path/'original',tmp_path/'clone',hashes)
    assert (tmp_path/'clone'/'sqe_em.msh').read_bytes()==b'native mesh'
    (native/'sqe_em.msh').write_bytes(b'tampered mesh')
    with pytest.raises(ValueError):
        _copy_verified_inputs(tmp_path/'original',tmp_path/'next',hashes)


def test_mpi_profile_requires_review_and_rejects_source_destination(tmp_path):
    with pytest.raises(ValueError):
        qualify_mpi_profile(tmp_path,tmp_path/'out.zip',reviewer='Expert',acknowledged=False)
    root=tmp_path/'root'; (root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/worker.py').touch()
    with pytest.raises(ValueError):
        qualify_mpi_profile(root,root/'unsafe.zip',reviewer='Expert',acknowledged=True)


def test_failed_worker_still_yields_shareable_report(tmp_path,monkeypatch):
    import sqe_studio.mpi_qualification as module
    root=tmp_path/'source'
    (root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/worker.py').write_text('# placeholder, never executed\n')
    monkeypatch.setattr(module,'mpi_plan',lambda *_: {'resources':{'logical_cpus':14,'memory_available_gb':15}})
    monkeypatch.setattr(module,'_run',lambda *_: (1,'native worker refused to continue',0.4))
    destination=tmp_path/'fail-report.zip'
    output=module.qualify_mpi_profile(root,destination,reviewer='Expert',acknowledged=True)
    assert any(s['id']=='one_native_mesh' and s['status']=='FAIL' for s in output['stages'])
    with zipfile.ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        assert 'INTEGRITY.json' in bundle.namelist()
        assert b'native worker refused' in bundle.read('logs/mesh-preparation.txt')
        assert b'fabrication HOLD' in bundle.read('SUMMARY.md')
