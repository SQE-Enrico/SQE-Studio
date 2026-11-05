"""RC14.12.14 numeric design-feedback contract; synthetic values are NOT science."""
from __future__ import annotations
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from sqe_studio.interop.design_targets import evaluate_design_targets

REV = 'a'*32
SHA = 'b'*64


def source(targets, engine='sqdmetal_palace'):
    project = {'revision': REV,'head':'c'*32,'revision_digest':SHA,
               'model':{'intent':{'targets':targets}}}
    manifest = {'schema':'sqe.artifact.v1','revision_id':REV,
                'project_digest':SHA,'engine':engine}
    return project,manifest


def em_screen():
    return {'schema':'sqe.em-native-results-screen.v1', 'modes':[
        {'native_mode_index':1,'frequency_GHz':6.02,'q_total':110000},
        {'native_mode_index':2,'frequency_GHz':7.2,'q_total':90000}]}


def test_saved_historical_revision_and_numeric_only_gates():
    targets=[{'name':'em_mode_1','unit':'GHz','value':6.0,'tolerance':0.03},
             {'name':'em_Q_mode_1','unit':'1','value':100000,'tolerance':500},
             {'name':'f01','unit':'GHz','value':5.1,'tolerance':0.05}]
    p,m=source(targets)
    out=evaluate_design_targets(project=p,manifest=m,em_evidence=em_screen())
    assert out['revision_id']==REV and out['project_digest']==SHA
    assert out['rows'][0]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
    assert out['rows'][0]['signed_delta']==pytest.approx(0.02)
    assert out['rows'][1]['numeric_status']=='OUTSIDE_NUMERIC_TOLERANCE'
    assert out['rows'][2]['numeric_status']=='NO_NATIVE_OBSERVATION_FOR_THIS_RUN'
    assert all(r['physical_status']=='NOT_QUALIFIED' for r in out['rows'])
    assert out['automatic_optimization']=='BLOCKED' and out['fabrication']=='HOLD'
    assert out['cross_engine_parameter_transfer'].startswith('BLOCKED')


def test_mismatches_ambiguity_and_missing_mapping_fail_closed():
    targets=[{'name':'em_mode_1','unit':'MHz','value':6020},
             {'name':'em_mode_1','unit':'GHz','value':6.1},
             {'name':'em_mode_2','unit':'MHz','value':7200},
             {'name':'S21','unit':'dB','value':-15},
             {'name':'em_mode_3','unit':'GHz','value':6.7},
             {'name':'em_Q_mode_1','unit':'1','value':1e5}]
    p,m=source(targets)
    out=evaluate_design_targets(project=p,manifest=m,em_evidence=em_screen())
    assert [r['numeric_status'] for r in out['rows']] == [
        'AMBIGUOUS_TARGET_NAME','AMBIGUOUS_TARGET_NAME','UNIT_MISMATCH',
        'UNMAPPED_DESIGN_TARGET','NO_NATIVE_OBSERVATION_FOR_THIS_RUN',
        'NO_TOLERANCE_DEFINED']


def test_scqubits_spectrum_must_be_native_finite_strictly_ordered():
    p,m=source([{'name':'f01','unit':'GHz','value':5,'tolerance':.2}], 'scqubits')
    spectrum={'schema':'sqe.scqubits.spectrum.v1','artifact_type':'scqubits.spectrum',
              'engine':'scqubits','source':'native scqubits eigenvals','units':'GHz',
              'levels':[1,6.1,8]}
    out=evaluate_design_targets(project=p,manifest=m,spectrum=spectrum)
    assert out['rows'][0]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
    assert out['rows'][0]['observed']==pytest.approx(5.1)
    for levels in [[1,1], [0,float('nan')], [3,2], [0,float('inf')]]:
        bad={**spectrum,'levels':levels}
        out=evaluate_design_targets(project=p,manifest=m,spectrum=bad)
        assert out['rows'][0]['numeric_status']=='NO_NATIVE_OBSERVATION_FOR_THIS_RUN'


def test_reject_stale_or_rebound_manifest():
    p,m=source([{'name':'f01','unit':'GHz','value':5}])
    for change in [{'revision_id':'d'*32},{'project_digest':'e'*64},{'schema':'unknown'}]:
        with pytest.raises(ValueError,match='saved revision'):
            evaluate_design_targets(project=p,manifest={**m,**change})


def test_many_saved_targets_bounded_without_hidden_promotion():
    p,m=source([{'name':f'X{i}','unit':'1','value':i} for i in range(140)])
    out=evaluate_design_targets(project=p,manifest=m)
    assert out['truncated'] is True
    assert len(out['rows'])==128
    assert out['total_saved_targets']==140


def test_gui_renders_server_screen_and_never_subtracts_unverified_values():
    node=shutil.which('node')
    if not node: pytest.skip('Node not installed')
    app=Path(__file__).resolve().parents[2]/'src/sqe_studio/web/app.js'
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const context=vm.createContext({});
vm.runInContext(source.replace(/start\(\);\s*$/, ''),context);
const screen={schema:'sqe.native-design-target-screen.v1',revision_id:'past',
 project_digest:'b'.repeat(64),fabrication:'HOLD',automatic_optimization:'BLOCKED',
 rows:[{name:'<img src=x onerror=alert(1)>',unit:'GHz',target:5,tolerance:0.1,
        observed:5.1,signed_delta:0.1,numeric_status:'WITHIN_NUMERIC_TOLERANCE',
        scientific_note:'NATIVE_INDEX_NOT_MODE_IDENTITY'}]};
const r=vm.runInContext('goalComparison',context)({design_target_screen:screen,
 manifest:{project_digest:'b'.repeat(64)}},{revision_id:'past'});
assert(r.includes('WITHIN_NUMERIC_TOLERANCE'));
assert(r.includes('NATIVE_INDEX_NOT_MODE_IDENTITY'));
assert(r.includes('&lt;img')&&!r.includes('<img'));
assert.throws(()=>vm.runInContext('goalComparison',context)(
 {design_target_screen:{...screen,revision_id:'different'},manifest:{project_digest:'b'.repeat(64)}},
 {revision_id:'past'}));
assert(!/obs-t\.value|Math\.abs\(obs-t\.value\)/.test(source));
console.log('TARGET_SCREEN_GUI_OK');
'''
    done=subprocess.run([node,'-e',script,str(app)],capture_output=True,text=True,timeout=15)
    assert done.returncode==0,(done.stdout,done.stderr)


def test_authenticated_results_revision_owned_targets_and_hash_gate(tmp_path):
    """HTTP fixture tests verification, NOT native EM or scqubits validity."""
    import hashlib
    import http.cookiejar
    import threading
    import urllib.error
    import urllib.request
    from sqe_studio.server import make_server

    server=make_server(tmp_path/'runtime',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    jar=http.cookiejar.CookieJar()
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                       urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',body=None):
        headers={'Content-Type':'application/json'}
        if csrf: headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,headers=headers,method=method,
            data=json.dumps(body).encode() if body is not None else None)
        try: response=client.open(request,timeout=5)
        except urllib.error.HTTPError as err: response=err
        with response:return response.status,json.loads(response.read())
    try:
        assert req('/api/projects')[0]==401
        token=server.app.setup_file.read_text(encoding='ascii')
        assert req('/api/setup','POST',{'email':'goals@test.invalid',
            'password':'long-isolated-password','setup_token':token})[0]==200
        code,auth=req('/api/login','POST',{'email':'goals@test.invalid','password':'long-isolated-password'})
        assert code==200
        csrf=auth['csrf']
        _,created=req('/api/projects','POST',{'name':'Revision targets','family':'transmon'})
        pid,original=created['id'],created['head']
        saved=copy.deepcopy(created['model'])
        saved['intent']['targets']=[{'name':'f01','unit':'GHz','value':5,'tolerance':0.2}]
        code,revision=req(f'/api/projects/{pid}/commit','POST',
            {'expected_revision':original,'model':saved})
        assert code==200
        rev=revision['revision']
        # Create a later revision with a DIFFERENT target. Results must read
        # the run's old saved target even if the current project changes.
        revised=copy.deepcopy(saved)
        revised['intent']['targets'][0]['value']=12
        code,next_revision=req(f'/api/projects/{pid}/commit','POST',
            {'expected_revision':rev,'model':revised})
        assert code==200
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        run='f'*32
        folder=server.app.store.root/'native-runs'/pid/run
        folder.mkdir(parents=True)
        server.app.store.put_run(owner,pid,rev,'S1','scqubits',folder)
        server.app.store.set_run(run,'completed')
        out=folder/'output';out.mkdir()
        spectrum={'schema':'sqe.scqubits.spectrum.v1','artifact_type':'scqubits.spectrum',
                  'engine':'scqubits','source':'native scqubits eigenvals',
                  'units':'GHz','levels':[1.,6.1,8.0]}
        raw=json.dumps(spectrum).encode('utf-8')
        (out/'spectrum.json').write_bytes(raw)
        digest=server.app.store.project(owner,pid,rev)['revision_digest']
        manifest={'schema':'sqe.artifact.v1','engine':'scqubits',
                  'engine_version':'test-fixture-not-native',
                  'artifact_type':'scqubits.spectrum','scientific_status':'review_required',
                  'fabrication_status':'HOLD','revision_id':rev,'project_digest':digest,
                  'study_id':'S1','parents':[],
                  'provenance':{'used_revision':rev,'used_project_sha256':digest},
                  'artifacts':[{'name':'spectrum.json',
                                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}]}
        (out/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
        url=f'/api/projects/{pid}/runs/{run}/result'
        code,result=req(url)
        assert code==200,result
        assert result['design_target_screen']['revision_id']==rev
        assert result['design_target_screen']['rows'][0]['target']==5
        assert result['design_target_screen']['rows'][0]['observed']==pytest.approx(5.1)
        assert result['design_target_screen']['rows'][0]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
        assert result['design_target_screen']['fabrication']=='HOLD'
        (out/'spectrum.json').write_text('{"levels":[999]}',encoding='utf-8')
        assert req(url)[0]==409
        assert req('/api/logout','POST',{})[0]==200
        assert req(url)[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
