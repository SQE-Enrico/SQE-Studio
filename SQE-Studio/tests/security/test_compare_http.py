"""Authenticated HTTP comparison over FAKE native-shaped fixture bytes only.

These fixtures do not execute a solver and must never be cited as numerical
validation of Quantum Metal, scqubits, Palace, or JosephsonCircuits.jl.
"""
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from sqe_studio.server import make_server
from sqe_studio.orchestration.artifacts import sha_bytes


def test_authenticated_revision_and_content_verified_comparison(tmp_path):
    server=make_server(tmp_path/'data', 0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',data=None):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if method=='POST' and csrf:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
                                       method=method,headers=headers)
        try:
            response=opener.open(request,timeout=6)
        except urllib.error.HTTPError as exc:
            response=exc
        with response:
            raw=response.read()
            return response.status,json.loads(raw) if response.headers.get('content-type','').startswith('application/json') else raw
    try:
        assert req('/api/projects/'+'a'*32+'/compare?left='+'a'*32+'&right='+'b'*32)[0]==401
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'comparison@test.invalid','password':'test-only-long-password','setup_token':token})[0]==200
        rc,auth=req('/api/login','POST',{'email':'comparison@test.invalid','password':'test-only-long-password'})
        assert rc==200
        csrf=auth['csrf']
        rc,project=req('/api/projects','POST',{'name':'Fixture comparison only','family':'transmon'})
        assert rc==201
        pid=project['id']; rev_a=project['head']
        model=project['model'];model['layout']['chip']['width_mm']+=0.5
        rc,saved=req(f'/api/projects/{pid}/commit','POST',{'expected_revision':rev_a,'model':model})
        assert rc==200;rev_b=saved['revision']
        root=server.app.store.root/'native-runs'/pid
        ids=('a'*32,'b'*32)
        def fixture(run_id,rev,levels):
            folder=root/run_id
            folder.mkdir(parents=True)
            server.app.store.put_run(server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id'],pid,rev,'S1','scqubits',folder)
            server.app.store.set_run(run_id,'completed')
            output=folder/'output'; output.mkdir()
            spec={'schema':'sqe.scqubits.spectrum.v1','artifact_type':'scqubits.spectrum',
                  'source':'native scqubits eigenvals', 'model':'Transmon','units':'GHz',
                  'energy_unit':'GHz','levels':levels,'axis':None,'preview_point_index':0,
                  'convergence':{'status':'not_checked'}}
            raw=json.dumps(spec).encode()
            (output/'spectrum.json').write_bytes(raw)
            project_revision=server.app.store.project(server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id'],pid,rev)
            sha=project_revision['revision_digest']
            manifest={'schema':'sqe.artifact.v1','engine':'scqubits',
                      'engine_version':'fixture_only_not_native', 'kind':'quantum_spectrum',
                      'artifact_type':'scqubits.spectrum','scientific_status':'review_required',
                      'fabrication_status':'HOLD','revision_id':rev,'project_digest':sha,
                      'study_id':'S1','parents':[],
                      'provenance':{'used_revision':rev,'used_project_sha256':sha},
                      'artifacts':[{'name':'spectrum.json','sha256':sha_bytes(raw),'bytes':len(raw)}]}
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
            return output
        left=fixture(ids[0],rev_a,[1.0,6.0,10.0]);right=fixture(ids[1],rev_b,[3.0,8.5,12.0])
        path=f'/api/projects/{pid}/compare?left={ids[0]}&right={ids[1]}'
        code,report=req(path)
        assert code==200,report
        assert report['status']=='read_only_expert_review_not_scientifically_qualified'
        assert not report['same_revision']
        assert report['design_input_changes']['total']>=1
        assert report['numerical_comparison']['rows'][0]['delta_GHz']==.5
        assert report['numerical_comparison']['convergence_verified'] is False
        assert req(f'/api/projects/{pid}/compare?left={ids[0]}&right={ids[0]}')[0]==400
        (right/'spectrum.json').write_text('maliciously edited fixture')
        assert req(path)[0]==409  # content SHA always checked before comparison
        assert req(f'/api/projects/{pid}/runs/{ids[1]}/result')[0]==409
        (right/'spectrum.json').write_text(json.dumps({'bad':'fixture'}))
        assert req(path)[0]==409
        assert req('/api/logout','POST',{})[0]==200
        assert req(path)[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
