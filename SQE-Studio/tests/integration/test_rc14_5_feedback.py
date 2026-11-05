"""RC14.5: unit/fixture harness. No native solver claimed unless actually run."""
from __future__ import annotations
import hashlib
import json
import zipfile
from pathlib import Path
import os
import pytest
from sqe_studio.feedback_qualification import qualify_eda_feedback, _checked_members
from sqe_studio.interop.native_em_evidence import native_em_evidence, compare_native_em_evidence
from sqe_studio.interop.native_views import palace_eigenmodes
from sqe_studio.interop.comparison import compare_palace_modes
from sqe_studio.interop.laptop_benchmark import resonator_project


def _subreport(path, label):
    payload={'QUALIFICATION.json':json.dumps({'schema':'test.'+label,'profile':label,
              'counts':{'PASS':2,'FAIL':0,'BLOCKED':1},
              'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}).encode(),
             'SUMMARY.md':label.encode()}
    payload['INTEGRITY.json']=json.dumps({'files':{
             k:hashlib.sha256(v).hexdigest() for k,v in payload.items()}}).encode()
    with zipfile.ZipFile(path,'w') as z:
        for k,v in payload.items():z.writestr(k,v)


def test_one_zip_aggregates_independent_reports_with_integrity(tmp_path,monkeypatch):
    import sqe_studio.qualification as q
    root=tmp_path/'source';(root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/server.py').touch()
    (root/'src/sqe_studio/worker.py').touch()
    calls=[]
    def fixture_runner(root, destination, *, profile, **kwargs):
        calls.append(profile)
        _subreport(destination, profile)
        return {'schema':'test.'+profile,'profile':profile,'counts':{'PASS':2,'FAIL':0,'BLOCKED':1},
                'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}
    monkeypatch.setattr(q,'qualify',fixture_runner)
    destination=tmp_path/'all.zip'
    out=qualify_eda_feedback(root,destination,em_options={
        'reviewer':'LabOperator','acknowledged':True,'solve':True,'refine':False})
    assert calls == ['comprehensive','native_em']
    assert out['counts']=={'PASS':4,'FAIL':0,'BLOCKED':2}
    assert out['scientific_qualification']=='NOT_ESTABLISHED'
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        assert 'software/QUALIFICATION.json' in z.namelist()
        assert 'em/QUALIFICATION.json' in z.namelist()
        assert json.loads(z.read('QUALIFICATION.json'))['profile']=='eda_feedback'
    assert _checked_members(destination)['QUALIFICATION.json']


def test_feedback_refuses_unreviewed_and_deck_only_without_running(tmp_path,monkeypatch):
    import sqe_studio.qualification as q
    monkeypatch.setattr(q,'qualify',lambda *a,**kw:pytest.fail('must not execute'))
    for options in ({'reviewer':'LabOperator','acknowledged':False,'solve':True,'refine':False},
                    {'reviewer':'LabOperator','acknowledged':True,'solve':False,'refine':False}):
        with pytest.raises(ValueError):
            qualify_eda_feedback(tmp_path,tmp_path/'no.zip',em_options=options)
    assert not (tmp_path/'no.zip').exists()


def test_corrupted_subreport_is_rejected(tmp_path):
    path=tmp_path/'bad.zip';_subreport(path,'a')
    with zipfile.ZipFile(path,'a') as z:z.writestr('evil.txt','unhashed')
    with pytest.raises(ValueError,match='inventory'):_checked_members(path)


def test_manifests_with_real_production_artifact_type_dispatch(tmp_path):
    # Synthetic CSVs, but production-shaped manifest lacks the non-existent "kind" field.
    p=tmp_path/'sqe_em/outputFiles';p.mkdir(parents=True)
    raw=(b'm, Re{f} (GHz), Im{f} (GHz), Q\n1, 6.1, 2e-6, 1e5\n')
    (p/'eig.csv').write_bytes(raw)
    a={'name':'sqe_em/outputFiles/eig.csv','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    m={'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes','artifacts':[a]}
    assert native_em_evidence(tmp_path,m)['modes'][0]['q_total']==100000
    assert palace_eigenmodes(tmp_path,m)['modes'][0]['frequency_GHz']==6.1
    assert native_em_evidence(tmp_path,m | {'artifact_type':'other'}) is None
    assert palace_eigenmodes(tmp_path,m | {'artifact_type':'other'}) is None


REPORT=Path(os.environ.get('SQE_TEST_NATIVE_REPORT','tests/fixtures/optional-native-report.zip'))


def test_real_palace_csv_replay_for_results_and_two_mesh_comparison(tmp_path):
    """Optional user-supplied original bytes, NOT a new solver run."""
    if not REPORT.is_file():pytest.skip('Native report not bundled with release')
    out=[];models=[]
    with zipfile.ZipFile(REPORT) as z:
        for j,stem in enumerate(('native_palace_solve','native_palace_refinement')):
            folder=tmp_path/stem/'sqe_em/outputFiles';folder.mkdir(parents=True)
            entries=[]
            for table in ('eig','port-Q','domain-E'):
                raw=z.read('native/'+stem+'-'+table+'.csv')
                (folder/(table+'.csv')).write_bytes(raw)
                entries.append({'name':'sqe_em/outputFiles/'+table+'.csv',
                                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
            manifest={'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes',
                      'artifacts':entries}
            base=tmp_path/stem
            out.append((native_em_evidence(base,manifest),palace_eigenmodes(base,manifest)))
            models.append(resonator_project(execution='solve',mesh_min_um=(12. if j==0 else 8.),
                                          mesh_max_um=(120. if j==0 else 80.)))
    assert out[0][0]['modes'][0]['ports'][0]['q_ext'] > 0
    assert out[0][0]['modes'][0]['frequency_GHz']==pytest.approx(5.904977748367)
    compare=compare_palace_modes(out[0][1],out[1][1],models[0],models[1],'ResEigen','ResEigen')
    assert compare['status']=='native_mode_index_differences_for_expert_review'
    scalars=compare_native_em_evidence(out[0][0],out[1][0],compare)
    assert scalars['status']=='NATIVE_INDEX_SCALAR_DIAGNOSTICS_ONLY'
    assert scalars['mode_identity']=='UNRESOLVED'


def test_launch_single_button_cycle_and_no_file_dialog():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2]/'Launch SQE Studio.pyw').read_text(encoding='utf-8')
    dialog = (Path(__file__).resolve().parents[2]/'src/sqe_studio/testing/desktop.py').read_text(encoding='utf-8')
    assert "text='Run release qualification'" not in dialog
    assert 'install_controls(root,' in src
    assert "text='Automatic Test'" in dialog
    assert "text='Qualify this laptop'" not in src
    assert 'TASK_END ' in dialog
    assert 'progress[\'value\']' in dialog
    assert "mode='determinate'" in dialog
    assert 'next_report_path(source)' in dialog
    assert 'run_release_qualification(source, destination' in dialog
    assert 'threading.Thread(target=worker' in dialog
    assert 'filedialog.' not in dialog
    assert 'Radiobutton' not in dialog
    assert 'reviewer_id' not in dialog
    assert "messagebox.showinfo('Report ready'" not in dialog
    assert "messagebox.showwarning('Report saved with failures'" not in dialog
    assert "busy['value']" in dialog
    assert 'Stop after current test' in dialog


def test_runtime_version_matches_release_metadata():
    import tomllib
    import sqe_studio
    root=Path(__file__).resolve().parents[2]
    release=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    assert sqe_studio.__version__==release


def test_native_exception_preserves_prior_software_report_and_fails_closed(tmp_path, monkeypatch):
    import sqe_studio.qualification as q
    root=tmp_path/'source';(root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/server.py').touch()
    (root/'src/sqe_studio/worker.py').touch()
    def runner(root, destination, *, profile, **kwargs):
        if profile == 'native_em':
            raise RuntimeError('Palace execution interrupted')
        _subreport(destination,profile)
        return {'schema':'test.'+profile,'profile':profile,'counts':{'PASS':2,'FAIL':0,'BLOCKED':1},
                'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}
    monkeypatch.setattr(q,'qualify',runner)
    dest=tmp_path/'feedback.zip'
    report=qualify_eda_feedback(root,dest,em_options={
        'reviewer':'SQEFixedProtocol','acknowledged':True,'solve':True,'refine':True})
    assert report['counts']=={'PASS':2,'FAIL':1,'BLOCKED':1}
    assert report['scientific_qualification']=='NOT_ESTABLISHED'
    members=_checked_members(dest)
    assert b'comprehensive' in members['software/SUMMARY.md']
    native=json.loads(members['em/QUALIFICATION.json'])
    assert native['counts']['PASS']==0
    assert native['stages'][0]['id']=='native_em_exception'
    assert native['stages'][0]['status']=='FAIL'


def test_reject_symlink_member_even_when_it_has_correct_checksum(tmp_path):
    from zipfile import ZipInfo
    path=tmp_path/'symlink.zip'
    payload=b'fake scientific evidence'
    with zipfile.ZipFile(path,'w') as z:
        link=ZipInfo('native/eig.csv'); link.create_system=3
        link.external_attr=(0o120777 << 16)
        z.writestr(link,payload)
        z.writestr('INTEGRITY.json',json.dumps({'files':{
            'native/eig.csv':hashlib.sha256(payload).hexdigest()}}))
    with pytest.raises(ValueError,match='Unsafe'):
        _checked_members(path)


def test_report_file_cannot_be_overwritten(tmp_path,monkeypatch):
    import sqe_studio.qualification as q
    root=tmp_path/'source';(root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/server.py').touch()
    (root/'src/sqe_studio/worker.py').touch()
    monkeypatch.setattr(q,'qualify',lambda *args,**kwargs:
                        pytest.fail('must not run against an existing report'))
    report=tmp_path/'keep.zip';report.write_bytes(b'important prior evidence')
    with pytest.raises(FileExistsError):
        qualify_eda_feedback(root,report,em_options={
            'reviewer':'SQEFixedProtocol','acknowledged':True,'solve':True,'refine':True})
    assert report.read_bytes()==b'important prior evidence'


def test_returned_pass_not_in_hashed_evidence_becomes_fail(tmp_path,monkeypatch):
    import sqe_studio.qualification as q
    root=tmp_path/'source';(root/'src/sqe_studio').mkdir(parents=True)
    (root/'src/sqe_studio/server.py').touch()
    (root/'src/sqe_studio/worker.py').touch()
    def false_pass(root,destination,*,profile,**kwargs):
        _subreport(destination,profile)
        return {'schema':'test.'+profile,'profile':profile,
                'counts':{'PASS':3,'FAIL':0,'BLOCKED':0},
                'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}
    monkeypatch.setattr(q,'qualify',false_pass)
    output=tmp_path/'mismatch.zip'
    result=qualify_eda_feedback(root,output,em_options={
        'reviewer':'SQEFixedProtocol','acknowledged':True,'solve':True,'refine':True})
    assert result['counts']=={'PASS':0,'FAIL':2,'BLOCKED':0}
    records=_checked_members(output)
    assert json.loads(records['software/QUALIFICATION.json'])['stages'][0]['status']=='FAIL'
    assert json.loads(records['em/QUALIFICATION.json'])['stages'][0]['status']=='FAIL'
