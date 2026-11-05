"""Release cycle qualification is a real service wrapper, not a solver fixture."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile
import time
import pytest
from sqe_studio import cycle_qualification as cycle
from sqe_studio.feedback_qualification import _checked_members

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(autouse=True)
def _copy_fixed_science_matrix(tmp_path):
    # Fake source roots in these controller tests must still carry the release
    # dispatch science plan. These are NOT real native scientific runs.
    target=tmp_path/'config/scientific_benchmarks.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/'config/scientific_benchmarks.json').read_bytes())



def test_local_report_numbers_increment_and_preserve_history(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    first=cycle.next_report_path(tmp_path)
    assert first.name == 'SQE-RC14_12-report-0001.zip'
    first.write_bytes(b'previous test data kept in place')
    next_one=cycle.next_report_path(tmp_path)
    assert next_one.name == 'SQE-RC14_12-report-0002.zip'
    assert first.read_bytes()==b'previous test data kept in place'


def test_one_button_generates_signed_incrementing_report_with_prior_metadata(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    calls=[]
    def fake_real_run(root,destination,*,em_options,notify):
        calls.append(em_options.copy())
        content={'QUALIFICATION.json':json.dumps({'counts':{'PASS':2,'FAIL':0,'BLOCKED':1},
                          'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}).encode(),
                 'SUMMARY.md':b'fixture ONLY: no solver executed'}
        content['INTEGRITY.json']=json.dumps({'files':{name:hashlib.sha256(body).hexdigest()
                            for name,body in content.items()}}).encode()
        with zipfile.ZipFile(destination,'w') as z:
            for name,body in content.items():z.writestr(name,body)
        return {'counts':{'PASS':2,'FAIL':0,'BLOCKED':1}}
    import sqe_studio.feedback_qualification as feedback
    monkeypatch.setattr(feedback,'qualify_eda_feedback',fake_real_run)
    p=cycle.next_report_path(tmp_path)
    output=cycle.run_release_qualification(tmp_path,p)
    assert output['counts']['PASS']==2
    assert calls[0]['reviewer']=='SQEFixedProtocol'
    assert calls[0]['solve'] and not calls[0]['refine']
    assert calls[0]['third_mesh'] is False
    check=_checked_members(p)
    assert json.loads(check['CYCLE.json'])['unchanged_native_runs_reused'] is False
    assert json.loads(check['CYCLE.json'])['progress_evidence'] == 'PROGRESS.json'
    first_progress=json.loads(check['PROGRESS.json'])
    assert first_progress['heartbeat_is_not_solver_convergence'] is True
    assert first_progress['outcome']=='REPORT_READY_NOT_SCIENTIFICALLY_APPROVED'
    diagnostics=json.loads(check['AUTOMATIC_TEST_DIAGNOSTICS.json'])
    assert diagnostics['mesh_comparison_executed'] is False
    assert diagnostics['mesh_identity_and_convergence']=='NOT_ESTABLISHED'
    next_p=cycle.next_report_path(tmp_path)
    cycle.run_release_qualification(tmp_path,next_p)
    check2=_checked_members(next_p)
    previous=json.loads(check2['CYCLE.json'])['prior_report']
    assert previous['status']=='HASH_VERIFIED_METADATA_ONLY_NO_SOLVER_CACHE'
    assert previous['prior_sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(calls)==2


def test_fixed_release_plan_has_one_mesh_only():
    plan=json.loads((ROOT/'qualification_plan.json').read_text())
    assert plan['native']['solve'] is True
    assert plan['native']['refine'] is False
    assert plan['native']['third_mesh'] is False
    assert plan['native_execution_purpose'].startswith('single_mesh_native_smoke')
    assert cycle._read_plan(ROOT)['native']==plan['native']


def test_plan_cannot_silently_add_third_mesh(tmp_path):
    plan=json.loads((ROOT/'qualification_plan.json').read_text())
    plan['native']['third_mesh']=True
    (tmp_path/'qualification_plan.json').write_text(json.dumps(plan),encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):
        cycle.next_report_path(tmp_path)


def test_supplying_untrusted_previous_report_does_not_reuse_it(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    path=cycle.next_report_path(tmp_path)
    path.write_bytes(b'not zip')
    result=cycle._previous(tmp_path,tmp_path/'qualification-reports/SQE-RC14_12-report-0002.zip')
    assert result['status']=='REJECTED_INVALID_NO_REUSE'


def test_crashing_test_still_produces_one_valid_feedback_zip(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    import sqe_studio.feedback_qualification as feedback
    def fail(*args,**kwargs):
        raise RuntimeError('solver crashed with unknown dependency')
    monkeypatch.setattr(feedback,'qualify_eda_feedback',fail)
    path=cycle.next_report_path(tmp_path)
    report=cycle.run_release_qualification(tmp_path,path)
    assert report['counts']=={'PASS':0,'FAIL':1,'BLOCKED':0}
    members=_checked_members(path)
    assert b'RuntimeError' in members['SUMMARY.md']
    assert json.loads(members['CYCLE.json'])['research_protocol'].startswith('fixed_release_')
    progress=json.loads(members['PROGRESS.json'])
    assert progress['outcome']=='FAIL_DIAGNOSTIC_NOT_SCIENTIFICALLY_APPROVED'
    assert progress['heartbeat_is_not_solver_convergence'] is True


def test_untrusted_previous_report_with_rehashed_wrong_provenance_rejected(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    report=cycle.next_report_path(tmp_path)
    original={'QUALIFICATION.json':json.dumps({'counts':{'PASS':100,'FAIL':0,'BLOCKED':0}}).encode(),
              'CYCLE.json':json.dumps({'schema':'sqe.agent-cycle-feedback.v1',
                 'release':'RC14.9','report_sequence':1,
                 'plan_sha256':'0'*64,'baseline_source_sha256':'0'*64,
                 'unchanged_native_runs_reused':False}).encode()}
    original['INTEGRITY.json']=json.dumps({'files':{
            k:hashlib.sha256(v).hexdigest() for k,v in original.items()}}).encode()
    with zipfile.ZipFile(report,'w') as z:
        for k,v in original.items():z.writestr(k,v)
    previous=cycle._previous(tmp_path,cycle.next_report_path(tmp_path))
    assert previous == {'prior_sequence':1,'status':'REJECTED_PROVENANCE_MISMATCH_NO_REUSE'}


def test_report_numbers_do_not_overwrite_nonregular_names(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    folder=tmp_path/'qualification-reports'
    folder.mkdir()
    (folder/'SQE-RC14_12-report-0001.zip').mkdir()
    assert cycle.next_report_path(tmp_path).name == 'SQE-RC14_12-report-0002.zip'


def test_current_run_blocker_hints_are_derived_not_passified():
    members={'software/QUALIFICATION.json':json.dumps({'gates':[
        {'id':'source_integrity','status':'FAIL'},
        {'id':'browser_real_http','status':'BLOCKED'},
        {'id':'test_ok','status':'PASS'}]}).encode(),
        'em/QUALIFICATION.json':json.dumps({'stages':[
        {'id':'native_palace_solve','status':'BLOCKED'}]}).encode()}
    assert cycle._blocker_hints(members) == [
        {'phase':'software','gate':'source_integrity','status':'FAIL'},
        {'phase':'software','gate':'browser_real_http','status':'BLOCKED'},
        {'phase':'native_em','gate':'native_palace_solve','status':'BLOCKED'}]


def test_report_existing_is_refused_without_calling_solver(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    dest=cycle.next_report_path(tmp_path)
    dest.write_bytes(b'old original evidence')
    import sqe_studio.feedback_qualification as feedback
    monkeypatch.setattr(feedback,'qualify_eda_feedback',lambda *a,**kw:
                        pytest.fail('must not overwrite or execute'))
    with pytest.raises(FileExistsError):
        cycle.run_release_qualification(tmp_path,dest)
    assert dest.read_bytes() == b'old original evidence'


def test_active_other_instance_gets_next_report_number(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    first=cycle.next_report_path(tmp_path)
    reserved=first.with_name(first.name+'.running')
    reserved.write_bytes(b'active other SQE instance')
    assert cycle.next_report_path(tmp_path).name=='SQE-RC14_12-report-0002.zip'
    assert reserved.read_bytes()==b'active other SQE instance'


def test_atomic_reservation_blocks_second_test_and_is_removed_after_failure(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    first=cycle.next_report_path(tmp_path)
    reservation=first.with_name(first.name+'.running')
    import sqe_studio.feedback_qualification as feedback
    def interrupted(*args,**kwargs):
        assert reservation.is_file()
        with pytest.raises(FileExistsError):
            cycle.run_release_qualification(tmp_path,first)
        raise RuntimeError('real production dependency interrupted')
    monkeypatch.setattr(feedback,'qualify_eda_feedback',interrupted)
    result=cycle.run_release_qualification(tmp_path,first)
    assert result['counts']['FAIL']==1
    assert not reservation.exists()
    assert _checked_members(first)['CYCLE.json']


def test_plan_cannot_promote_scientific_gates(tmp_path):
    plan=json.loads((ROOT/'qualification_plan.json').read_text())
    plan['scientific_gates']['mode_identity']='PASS'
    (tmp_path/'qualification_plan.json').write_text(json.dumps(plan),encoding='utf-8')
    with pytest.raises(ValueError,match='does not match'):
        cycle.next_report_path(tmp_path)


def test_interrupted_partial_archive_number_is_not_reused(tmp_path):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    first=cycle.next_report_path(tmp_path)
    partial=first.with_name(first.name+'.partial')
    partial.write_bytes(b'incomplete earlier evidence, retain for examination')
    assert cycle.next_report_path(tmp_path).name=='SQE-RC14_12-report-0002.zip'
    assert partial.is_file()


def test_controller_heartbeat_is_live_and_only_records_allowlisted_stage_metadata():
    messages=[]
    monitor=cycle._ProgressEvidence(messages.append,interval=0.01)
    monitor.start()
    monitor.notify('PHASE_START native_em')
    monitor.notify('STAGE_START native_em native_palace_solve')
    monitor.notify('Running raw local path /users/example/secret/instrument-output.txt')
    time.sleep(0.045)
    monitor.notify('STAGE_END native_em native_palace_solve BLOCKED')
    monitor.notify('PHASE_END native_em')
    snapshot=monitor.finish('TEST_ONLY_BLOCKED')
    assert snapshot['heartbeat_count'] >= 2
    assert snapshot['phases_completed']==1
    assert snapshot['stages_completed_by_phase']['native_em']==1
    assert snapshot['gate_event_counts']['BLOCKED']==1
    assert any(m.startswith('HEARTBEAT: phase=native_em stage=native_palace_solve') for m in messages)
    assert '/users/example/' not in json.dumps(snapshot)
    assert snapshot['heartbeat_is_not_solver_convergence'] is True
    assert snapshot['events'][-1]['event']=='PHASE_END'

def test_full_pipeline_progress_events_are_phase_separated_and_fail_closed(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    import sqe_studio.feedback_qualification as feedback
    emitted=[]
    def synthetic_report(root,destination,*,em_options,notify):
        assert em_options['solve'] is True and em_options['refine'] is False
        notify('PHASE_START software')
        notify('STAGE_START software integrated_regression')
        notify('STAGE_END software integrated_regression FAIL')
        notify('PHASE_END software')
        notify('PHASE_START native_em')
        notify('STAGE_START native_em native_palace_solve')
        notify('STAGE_END native_em native_palace_solve BLOCKED')
        notify('PHASE_END native_em')
        data={'QUALIFICATION.json':json.dumps({'counts':{'PASS':0,'FAIL':1,'BLOCKED':1},
              'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}).encode(),
              'SUMMARY.md':b'fixture only; no real run'}
        data['INTEGRITY.json']=json.dumps({'files':{
            k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}).encode()
        with zipfile.ZipFile(destination,'w') as z:
            for k,v in data.items():z.writestr(k,v)
        return {'counts':{'PASS':0,'FAIL':1,'BLOCKED':1}}
    monkeypatch.setattr(feedback,'qualify_eda_feedback',synthetic_report)
    path=cycle.next_report_path(tmp_path)
    out=cycle.run_release_qualification(tmp_path,path,notify=emitted.append)
    assert out['counts']['FAIL']==1
    data=_checked_members(path)
    progress=json.loads(data['PROGRESS.json'])
    assert progress['phases_completed']==3
    assert progress['stages_completed_by_phase']=={'software':1,'native_em':1,'science':12}
    assert progress['gate_event_counts']['FAIL']==1
    assert progress['gate_event_counts']['BLOCKED']==13
    assert progress['outcome']=='REPORT_READY_NOT_SCIENTIFICALLY_APPROVED'
    assert any(v=='STAGE_END native_em native_palace_solve BLOCKED' for v in emitted)
    assert json.loads(data['CYCLE.json'])['unchanged_native_runs_reused'] is False


def test_finalize_error_produces_numbered_fallback_not_a_fabricated_pass(tmp_path,monkeypatch):
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_bytes((ROOT/'EDA_SOURCE_MANIFEST.json').read_bytes())
    import sqe_studio.feedback_qualification as feedback
    def synthetic(*args,**kwargs):
        raw=args[1]
        members={'QUALIFICATION.json':json.dumps({'counts':{'PASS':9,'FAIL':0,'BLOCKED':0},
              'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}).encode()}
        members['INTEGRITY.json']=json.dumps({'files':{
             k:hashlib.sha256(v).hexdigest() for k,v in members.items()}}).encode()
        with zipfile.ZipFile(raw,'w') as archive:
            for key,data in members.items():archive.writestr(key,data)
        return {'counts':{'PASS':9,'FAIL':0,'BLOCKED':0}}
    monkeypatch.setattr(feedback,'qualify_eda_feedback',synthetic)
    actual=cycle._finalize_report
    count={'n':0}
    def one_failure(*args,**kwargs):
        count['n']+=1
        if count['n']==1:
            raise OSError('archive stage refused publication')
        return actual(*args,**kwargs)
    monkeypatch.setattr(cycle,'_finalize_report',one_failure)
    target=cycle.next_report_path(tmp_path)
    report=cycle.run_release_qualification(tmp_path,target)
    assert count['n']==2
    assert report['counts']=={'PASS':0,'FAIL':1,'BLOCKED':0}
    members=_checked_members(target)
    assert json.loads(members['QUALIFICATION.json'])['counts']['PASS']==0
    assert json.loads(members['PROGRESS.json'])['outcome'].startswith('FAIL_DIAGNOSTIC')
    assert not target.with_name(target.name+'.running').exists()
