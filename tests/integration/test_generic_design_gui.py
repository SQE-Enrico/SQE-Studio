"""HTTP and catalog regression for the one canonical GUI design workflow."""
from pathlib import Path
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request

import pytest
from sqe_studio.design_library import list_templates, instantiate, component_catalog
from sqe_studio.adapters.quantum_metal_adapter import validate_recipe
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.sqdmetal_palace_adapter import preflight
from sqe_studio.interop.native_views import palace_eigenmodes, NativeDisplayError
from sqe_studio.server import make_server


def test_all_starter_projects_are_ordinary_editable_models():
    catalog=list_templates()
    assert catalog and 'cpw_resonator_v1' in [v['id'] for v in catalog]
    model=instantiate('cpw_resonator_v1','Edited CPW Circuit','resonator')
    assert model['schema']=='sqe.project.v1'
    assert model['process']['source']=='unverified'
    assert model['studies'][0]['inputs']['em']['ground']['verified'] is False
    assert len(validate_recipe(model['layout'])[0]) >= 6
    assert any(c['kind']=='RouteMeander' for c in model['layout']['components'])
    assert model['studies'][0]['engine']=='sqdmetal_palace'
    with pytest.raises(EngineBlocked): preflight(model['studies'][0],model)
    with pytest.raises(ValueError): instantiate('../bad.py','Bad','resonator')
    with pytest.raises(ValueError): instantiate('cpw_resonator_v1','Wrong family','generic')
    assert {'TransmonPocket','RouteMeander','LaunchpadWirebond'} <= {c['kind'] for c in component_catalog()['components']}


def test_verified_native_eigenmode_display_requires_units_and_good_rows(tmp_path):
    root=tmp_path/'output'/'sqe_em'/'outputFiles'
    root.mkdir(parents=True)
    eig=root/'eig.csv';eig.write_text('Mode,Frequency (GHz)\n1,5.102\n2,6.550\n')
    manifest={'engine':'sqdmetal_palace','kind':'eigenmode','artifacts':[{'name':'sqe_em/outputFiles/eig.csv'}]}
    native=palace_eigenmodes(tmp_path/'output',manifest)
    assert native['modes'][0]['frequency_GHz']==5.102
    assert native['mode_matching']=='not_established'
    assert palace_eigenmodes(tmp_path/'output',dict(manifest,artifacts=[])) is None
    eig.write_text('Mode,Frequency (Hz)\n1,5102000000\n')
    with pytest.raises(NativeDisplayError): palace_eigenmodes(tmp_path/'output',manifest)
    eig.write_text('Mode,Frequency (GHz)\n1,NaN\n')
    with pytest.raises(NativeDisplayError): palace_eigenmodes(tmp_path/'output',manifest)


@pytest.fixture
def gui_host(tmp_path):
    server=make_server(tmp_path/'private',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server, f'http://127.0.0.1:{server.server_port}'
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


def test_generic_gui_template_auth_validation_and_study_edit(gui_host):
    server,base=gui_host
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def req(path, method='GET', data=None, csrf=None):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if csrf:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=headers,
                                       data=json.dumps(data).encode() if data is not None else None)
        try:
            with client.open(request, timeout=8) as response:
                return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code,json.loads(exc.read())
    assert req('/api/design/templates')[0]==401
    token=server.app.setup_file.read_text()
    assert req('/api/setup','POST',{'setup_token':token,'email':'gui@test.local','password':'very-long-test-password'})[0]==200
    status,login=req('/api/login','POST',{'email':'gui@test.local','password':'very-long-test-password'})
    assert status==200;csrf=login['csrf']
    status,catalog=req('/api/design/templates')
    assert status==200 and 'cpw_resonator_v1' in [s['id'] for s in catalog['templates']]
    assert req('/api/projects','POST',{'name':'Integrated CPW','family':'resonator','template_id':'cpw_resonator_v1'})[0]==403
    assert req('/api/projects','POST',{'name':'No','family':'generic','template_id':'cpw_resonator_v1'},csrf)[0]==422
    status,created=req('/api/projects','POST',{'name':'Integrated CPW','family':'resonator','template_id':'cpw_resonator_v1'},csrf)
    assert status==201
    pid=created['id'];model=created['model'];assert model['layout']['components'][0]['kind']=='LaunchpadWirebond'
    status,checked=req('/api/design/check','POST',{'model':model},csrf)
    assert status==200 and checked['layout']['ready'] is True
    assert checked['em'][0]['ready'] is False
    assert checked['fabrication_status']=='HOLD'
    assert req('/api/design/check','POST',{'model':model})[0]==403
    # Ordinary GUI edit -> immutable revision, no special benchmark executor.
    model['layout']['components'][5]['total_length_mm']=3.8
    status,commit=req(f'/api/projects/{pid}/commit','POST',{'expected_revision':created['head'],'model':model},csrf)
    assert status==200
    assert req(f'/api/projects/{pid}')[1]['model']['layout']['components'][5]['total_length_mm']==3.8
    assert req(f'/api/projects/{pid}/commit','POST',{'expected_revision':created['head'],'model':model},csrf)[0]==409


def test_native_parameter_sweep_api_rejects_invalid_axes_without_queue(gui_host):
    server,base=gui_host
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def req(path, method='GET',data=None,csrf=''):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=headers,
              data=json.dumps(data).encode() if data is not None else None)
        try:
            with client.open(request,timeout=8) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())
    token=server.app.setup_file.read_text()
    assert req('/api/setup','POST',{'setup_token':token,'email':'sweeps@test.local','password':'another-very-long-password'})[0]==200
    csrf=req('/api/login','POST',{'email':'sweeps@test.local','password':'another-very-long-password'})[1]['csrf']
    status,created=req('/api/projects','POST',{'name':'Sweep Design','family':'generic'},csrf)
    assert status==201
    model=created['model'];model['studies']=[{'id':'Native1','engine':'scqubits','kind':'spectrum',
         'inputs':{'model':'Transmon','parameters':{'EJ':15.0,'EC':0.25,'ng':0,'ncut':20},'levels':5}}]
    revision=req(f"/api/projects/{created['id']}/commit",'POST',{'expected_revision':created['head'],'model':model},csrf)[1]['revision']
    data={'revision':revision,'study_id':'Native1','axes':{'parameters.EJ':[15,16]},'mode':'automatic'}
    assert req(f"/api/projects/{created['id']}/sweeps",'POST',data)[0]==403
    assert req(f"/api/projects/{created['id']}/sweeps",'POST',dict(data,axes={'parameters.NoSuch':[15]}),csrf)[0]==422
    assert req(f"/api/projects/{created['id']}/sweeps",'POST',dict(data,axes={'parameters.EJ':[float('nan')]}),csrf)[0]==400
    assert req(f"/api/projects/{created['id']}/sweeps",'POST',dict(data,revision=created['head']),csrf)[0]==409
    assert not server.app.store.runs(server.app.store.conn().execute('SELECT owner FROM projects WHERE id=?',(created['id'],)).fetchone()[0],created['id'])


def test_generic_gui_assets_and_frozen_schema_unchanged():
    root=Path(__file__).resolve().parents[2]
    text=(root/'src/sqe_studio/web/app.js').read_text()
    assert 'function componentDialog' in text and 'function emEditor' in text
    assert 'Native parametric exploration' in text and 'designTemplates' in text
    assert 'sqe.project.v1' in text
    assert 'SQE Studio single workspace' in text


def test_gui_completed_sweep_is_not_misrepresented_as_single_result(gui_host):
    """Corrupt sweep evidence must never fall through to a fake single-run result."""
    server,base=gui_host
    jar=http.cookiejar.CookieJar()
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
    def req(path,method='GET',data=None,csrf=''):
        h={'Content-Type':'application/json'}
        if csrf:h['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=h,
            data=json.dumps(data).encode() if data is not None else None)
        try:response=client.open(request,timeout=8)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.status,json.loads(response.read())
    token=server.app.setup_file.read_text()
    assert req('/api/setup','POST',{'setup_token':token,'email':'viewer@test.local','password':'very-long-test-password'})[0]==200
    csrf=req('/api/login','POST',{'email':'viewer@test.local','password':'very-long-test-password'})[1]['csrf']
    _,project=req('/api/projects','POST',{'name':'Native sweep integrity','family':'generic'},csrf)
    owner=server.app.store.conn().execute('SELECT owner FROM projects WHERE id=?',(project['id'],)).fetchone()[0]
    rid='a'*32
    folder=server.app.store.root/'native-runs'/project['id']/rid
    folder.mkdir(parents=True)
    server.app.store.put_run(owner,project['id'],project['head'],'S1','scqubits',folder)
    server.app.store.set_run(rid,'completed')
    (folder/'SWEEP_MANIFEST.json').write_text('{"incomplete":"fixture-only"}')
    status,listed=req(f"/api/projects/{project['id']}/runs")
    assert status==200 and listed['runs'][0]['is_sweep'] is True
    assert req(f"/api/projects/{project['id']}/runs/{rid}/result")[0]==409
    assert req(f"/api/projects/{project['id']}/runs/{rid}/sweep")[0]==409
