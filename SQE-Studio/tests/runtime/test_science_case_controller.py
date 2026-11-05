"""A15 expanded science dispatch: bounded orchestration and no fake native PASS."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

import pytest

from sqe_studio import cycle_qualification as c

ROOT = Path(__file__).resolve().parents[2]


def _members(software=None, em=None):
    result={}
    if software is not None:
        result['software/QUALIFICATION.json'] = json.dumps({'gates': software}).encode()
    if em is not None:
        result['em/QUALIFICATION.json'] = json.dumps({'stages': em}).encode()
    return result


def test_matrix_matches_dispatch_sha_and_is_not_runtime_evidence():
    matrix, digest = c._read_science_matrix(ROOT)
    assert digest == hashlib.sha256((ROOT/'config/scientific_benchmarks.json').read_bytes()).hexdigest()
    assert matrix['status'] == 'COORDINATION_SPECIFICATION_NOT_YET_IMPLEMENTED_OR_EXECUTED'
    assert len(matrix['benchmark_cases']) == 12


def test_existing_em_solve_cannot_grant_expanded_physics_pass():
    gates=[{'id': name,'status':'PASS','duration_seconds':0.5} for name in (
        'source_integrity','python_compile','javascript_syntax','integrated_regression',
        'browser_real_http','browser_deep_acceptance','source_wheel_build',
        'installed_wheel','installed_assets')]
    signals=[]
    matrix = c.run_scientific_case_matrix(ROOT,_members(gates,[
        {'id':'native_palace_solve','status':'PASS'},
        {'id':'native_palace_refinement','status':'PASS'}]),notify=signals.append)
    entries={item['case_id']:item for item in matrix['cases']}
    assert entries['B00']['stage_status']=='PASS'
    assert entries['B00']['execution_kind']=='NATIVE'  # real software checks, not a physics solve
    assert entries['B02']['stage_status']=='BLOCKED'
    assert entries['B02']['failure_reason']=='BLOCKED_EXPANDED_PHYSICS_CHECKS'
    assert entries['B02']['execution_kind']=='NATIVE'
    assert all(entries[case]['stage_status']=='BLOCKED' for case in c._CASE_IDS if case not in ('B00','B02'))
    assert all(entries[case]['execution_kind']=='NOT_RUN' for case in c._CASE_IDS if case not in ('B00','B02'))
    assert entries['B03']['failure_reason']=='BLOCKED_NOT_IMPLEMENTED'
    assert matrix['qualification']=='NOT_ESTABLISHED'
    assert matrix['mode_identity']=='UNRESOLVED'
    assert matrix['em_to_hamiltonian']=='BLOCKED'
    assert matrix['fabrication']=='HOLD'
    assert signals.count('PHASE_START science')==1
    assert signals.count('PHASE_END science')==1
    assert len([line for line in signals if line.startswith('STAGE_END science')])==12


def test_software_any_fail_or_missing_is_never_pass():
    actual=['source_integrity','python_compile','javascript_syntax','integrated_regression',
            'browser_real_http','browser_deep_acceptance','source_wheel_build',
            'installed_wheel','installed_assets']
    for missing in (None,'browser_real_http'):
        gates=[{'id':name,'status':'PASS'} for name in actual if name!=missing]
        b00=next(x for x in c.run_scientific_case_matrix(ROOT,_members(gates))['cases'] if x['case_id']=='B00')
        assert b00['stage_status']==('PASS' if missing is None else 'BLOCKED')
    gates=[{'id':name,'status':'FAIL' if name=='source_integrity' else 'PASS'} for name in actual]
    b00=next(x for x in c.run_scientific_case_matrix(ROOT,_members(gates))['cases'] if x['case_id']=='B00')
    assert b00['stage_status']=='FAIL'


def test_corrupt_or_missing_matrix_fails_closed(tmp_path):
    path=tmp_path/'config/scientific_benchmarks.json'
    path.parent.mkdir(parents=True)
    with pytest.raises(ValueError,match='missing'):
        c._read_science_matrix(tmp_path)
    doc=json.loads((ROOT/'config/scientific_benchmarks.json').read_text())
    doc['execution_policy']['user_selectable_parameters']=True
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='violates'):
        c._read_science_matrix(tmp_path)


def test_case_time_budget_skips_command_without_execute(tmp_path):
    command=[str(tmp_path/'missing-case-executable')]
    outputs=c.run_scientific_case_matrix(ROOT,{},elapsed_s=3450,commands={'B09':command})
    b09=next(item for item in outputs['cases'] if item['case_id']=='B09')
    assert b09['stage_status']=='BLOCKED'
    assert b09['failure_reason']=='BLOCKED_TIME_BUDGET'
    assert b09['solver_exit_code'] is None


def test_malformed_self_asserted_native_pass_is_rejected():
    command=[sys.executable,'-c',
             'import json,sys;json.dump({"case_id":"B09","stage_status":"PASS",'
             '"execution_kind":"FIXTURE"},open(sys.argv[-1],"w"))']
    result=c._case_command(ROOT,'B09',command,10,lambda _:None)
    assert result['stage_status']=='FAIL'
    assert result['failure_reason']=='UNVERIFIED_NATIVE_ADAPTER_REPORT'
    assert result['solver_exit_code']==0


def test_native_command_timeout_is_blocked_not_pass():
    command=[sys.executable,'-c','import time;time.sleep(8)']
    # _run enforces the adapter budget via a supervised child timeout.
    result=c._case_command(ROOT,'B09',command,1,lambda _:None)
    assert result['stage_status']=='BLOCKED'
    assert result['solver_exit_code'] is None
    assert result['execution_kind']=='NATIVE'


def test_numbered_archive_contains_checksum_checked_case_evidence(tmp_path,monkeypatch):
    from sqe_studio.feedback_qualification import _checked_members
    import sqe_studio.feedback_qualification as feedback
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    dest=tmp_path/'config/scientific_benchmarks.json'
    dest.parent.mkdir(parents=True)
    dest.write_bytes((ROOT/'config/scientific_benchmarks.json').read_bytes())
    def synthetic(*args,**kwargs):
        with __import__('zipfile').ZipFile(args[1],'w') as z:
            payload={'QUALIFICATION.json':json.dumps({'counts':{'PASS':0,'FAIL':0,'BLOCKED':1},
                      'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}).encode()}
            payload['INTEGRITY.json']=json.dumps({'files':{k:hashlib.sha256(v).hexdigest()
                      for k,v in payload.items()}}).encode()
            for key,val in payload.items():z.writestr(key,val)
        return {'counts':{'PASS':0,'FAIL':0,'BLOCKED':1}}
    monkeypatch.setattr(feedback,'qualify_eda_feedback',synthetic)
    path=c.next_report_path(tmp_path)
    c.run_release_qualification(tmp_path,path)
    members=_checked_members(path)
    matrix=json.loads(members['BENCHMARK_CASE_MATRIX.json'])
    assert matrix['case_count']==12
    assert len(matrix['cases'])==12
    assert all(item['stage_status'] != 'PASS' for item in matrix['cases'])
    assert json.loads(members['CYCLE.json'])['benchmark_case_evidence']=='BENCHMARK_CASE_MATRIX.json'
    assert json.loads(members['PROGRESS.json'])['stages_completed_by_phase']['science']==12


def test_adapter_cannot_pass_with_only_self_reported_native_artifact_hashes():
    # A native adapter claiming PASS without generating its attested output in
    # its private run dir cannot promote fixture text into physics evidence.
    forged=c._case_record('B09',status='PASS',reason=None,execution='NATIVE',
        provenance={'native_run':True,'native_artifacts':[
            {'path':'artifacts/native_solver_output.json','sha256':'0'*64}]},
        solver_version='fictional 1.0',input_sha256='0'*64,
        geometry_revision_sha256='1'*64,
        material_bc_mesh_hashes={'mesh':'2'*64},units={'frequency':'GHz'},
        measurements={'pump_off':0.0},numerical_tolerances={'residual':1e-6},
        solver_exit_code=0,duration_s=0.1,log_sha256='3'*64)
    command=[sys.executable,'-c',
             'import json,sys;json.dump('+repr(forged)+',open(sys.argv[-1],"w"))']
    result=c._case_command(ROOT,'B09',command,10,lambda _:None)
    assert result['stage_status']=='FAIL'
    assert result['failure_reason']=='UNVERIFIED_NATIVE_ADAPTER_REPORT'


def test_b00_rejects_extra_stale_release_failure_and_duplicate_gate_spoofing():
    names=('source_integrity','python_compile','javascript_syntax','integrated_regression',
           'browser_real_http','browser_deep_acceptance','source_wheel_build',
           'installed_wheel','installed_assets')
    gates=[{'id':n,'status':'PASS'} for n in names]
    contaminated=gates+[{'id':'obsolete_rc14_9_test','status':'FAIL'}]
    record=c._case_from_software(_members(contaminated),'B00')
    assert record['stage_status']=='FAIL'
    assert record['failure_reason']=='REAL_SOFTWARE_GATE_FAILED'
    spoofed=[{'id':'installed_wheel','status':'FAIL'},*gates]
    record=c._case_from_software(_members(spoofed),'B00')
    assert record['stage_status']=='FAIL'
    assert record['failure_reason']=='MALFORMED_SOFTWARE_EVIDENCE'
