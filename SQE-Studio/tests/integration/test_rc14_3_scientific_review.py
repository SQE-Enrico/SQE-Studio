"""Portable RC14.3 evidence tests; constructed fixtures are NOT scientific results."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
from sqe_studio.interop.scientific_review import (
    _eig_quality, review_scientific_report, save_scientific_review)


def _fixture(path: Path, negative=False):
    tags=['native_palace_solve','native_palace_refinement']
    payload={'QUALIFICATION.json':json.dumps({'schema':'sqe.native-em-qualification.v1',
             'stages':[{'id':x,'status':'PASS'} for x in tags]}).encode()}
    for i,tag in enumerate(tags,1):
        freq=5.9+(i-1)*0.03
        q=350000 if i==1 else 900000
        k=(-1 if negative and i==2 else 1)*freq/(1e7+i*1e6)
        obs={'geometry_and_stack_sha256':'a'*64,'manifest_sha256':str(i)*64,
             'modes':[{'mode_index':1,'frequency_GHz':freq}]}
        payload[f'native/{tag}-manifest.json']=json.dumps({'artifact_type':'palace.eigenmodes',
            'observation':obs,'artifacts':[{'name':'sqe_em/sqe_em.json','sha256':'f'*64}]}).encode()
        payload[f'logs/{tag}.txt']=(f'  elements 1 1 1 {i*10000}\n'
                'Linear eigensolve converged (1 eigenpair) due to CONVERGED_TOL; iterations 1\n').encode()
        payload[f'native/{tag}-eig.csv']=(
            'm, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)\n'
            f'1.00e+00, {freq:.10e}, 1.00e-06, {q:.10e}, 1.0e-11, 1.0e-08\n').encode()
        payload[f'native/{tag}-port-Q.csv']=(
            'm, Q_ext[1], kappa_ext[1] (GHz)\n'
            f'1.00e+00, {1e7+i*1e6:.10e}, {k:.12e}\n').encode()
        payload[f'native/{tag}-domain-E.csv']=(
            'm, E_elec (J), E_mag (J)\n1.00e+00, 1e-12, 1.00001e-12\n').encode()
    payload['INTEGRITY.json']=json.dumps({'schema':'sqe.qualification-file-hashes.v1',
         'files':{n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}}).encode()
    with zipfile.ZipFile(path,'w') as z:
        for name, data in payload.items(): z.writestr(name,data)
    return path


def test_scientific_screen_keeps_mode_unresolved_and_distinguishes_q(tmp_path):
    p=_fixture(tmp_path/'native.zip',negative=True)
    r=review_scientific_report(p)
    assert r['mode_identity']=='UNRESOLVED'
    assert r['field_overlap']['status']=='BLOCKED_NO_COMMON_COMPLEX_VECTOR_FIELDS'
    assert r['frequency']['last_step_numeric_screen']=='NUMERIC_THRESHOLD_MET_NOT_PHYSICALLY_QUALIFIED'
    assert r['total_q']['last_step_numeric_screen']=='NUMERIC_DRIFT_REQUIRES_REVIEW'
    assert r['points'][1]['ports'][0]['status']=='SIGN_CONVENTION_REVIEW'
    assert r['points'][1]['ports'][0]['kappa_abs_relative_mismatch']<1e-6
    assert r['fabrication']=='HOLD'
    assert r['optimization'].startswith('BLOCKED')
    assert r['em_to_hamiltonian']=='BLOCKED'


def test_screen_flags_native_magnitude_inconsistency(tmp_path):
    p=_fixture(tmp_path/'native.zip')
    # Alter native bytes and rebuild their SHA-256 declarations. This is a
    # *different* internally consistent fixture, not a real native result.
    with zipfile.ZipFile(p) as z: content={n:z.read(n) for n in z.namelist()}
    key='native/native_palace_refinement-port-Q.csv'
    content[key]=content[key].replace(b'e-07',b'e-05')
    content['INTEGRITY.json']=json.dumps({'files':{n:hashlib.sha256(b).hexdigest()
                     for n,b in content.items() if n!='INTEGRITY.json'}}).encode()
    with zipfile.ZipFile(p,'w') as z:
        for n,b in content.items():z.writestr(n,b)
    record=review_scientific_report(p)
    assert any(f['type']=='KAPPA_MAGNITUDE_MISMATCH' for f in record['advisory_flags'])


def test_scientific_review_zip_embeds_verified_source_and_hashes(tmp_path):
    p=_fixture(tmp_path/'input.zip',negative=True)
    target=tmp_path/'review.zip'
    result=save_scientific_review(p,target)
    assert result['fabrication']=='HOLD'
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        expected=json.loads(z.read('INTEGRITY.json'))['files']
        assert set(expected)==set(z.namelist())-{'INTEGRITY.json'}
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in expected.items())
        assert z.read('evidence/native-report.zip')==p.read_bytes()
        assert json.loads(z.read('SCIENTIFIC_REVIEW.json'))['mode_identity']=='UNRESOLVED'
    with pytest.raises(ValueError):
        save_scientific_review(p,p)


def test_modified_report_is_rejected_before_scientific_interpretation(tmp_path):
    p=_fixture(tmp_path/'input.zip')
    with zipfile.ZipFile(p,'a') as z:
        z.writestr('native/fake-field.csv','unverified')
    with pytest.raises(ConvergenceEvidenceError):
        review_scientific_report(p)


@pytest.mark.parametrize('raw',[
    b'm, Re{f} (GHz), Im{f} (GHz), Q\n1.00e+00, 5.9, 0, nan\n',
    b'm, Re{f} (GHz), Im{f} (GHz), Q\n1.00e+00, 5.9, 0, -1\n',
    b'm, Re{f} (GHz), Im{f} (GHz), Q\n2.00e+00, 5.9, 0, 100\n',
])
def test_native_quality_rejects_invalid_values(raw):
    with pytest.raises(ConvergenceEvidenceError):
        _eig_quality(raw)
