"""M10 scientific method and authenticated integration tests (fixtures, not Palace solves)."""
from __future__ import annotations
from copy import deepcopy
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request

import pytest

from sqe_studio.design_library import instantiate
from sqe_studio.eda.mesh_refinement import compare_verified_three_meshes
from sqe_studio.eda.scientific_references import list_reference_cases
from sqe_studio.orchestration.artifacts import sha_bytes
from sqe_studio.server import make_server


def _triple():
    a = instantiate('cpw_resonator_v1', 'Independent CPW', 'resonator')
    models = [deepcopy(a) for _ in range(3)]
    for model, size in zip(models, (120., 80., 50.)):
        mesh = model['studies'][0]['inputs']['em']['mesh']
        mesh['max_um'] = size
        mesh['min_um'] = size / 10
    native = [dict(source='palace.native_eig.csv', units='GHz',
                   mode_matching='not_established',
                   modes=[{'mode_index':1, 'frequency_GHz':value}])
              for value in (5.90, 5.94, 5.95)]
    manifest = [{'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes',
                 'engine_version':'fake_source_version'} for _ in range(3)]
    return models, native, manifest


def _eval(models=None, native=None, manifests=None):
    m, n, a = _triple()
    return compare_verified_three_meshes(models=m if models is None else models,
                                         study_ids=('ResEigen',)*3,
                                         native=n if native is None else native,
                                         manifests=a if manifests is None else manifests)


def test_three_verified_meshes_yield_only_a_numerical_index_drift():
    result = _eval()
    assert result['status'] == 'NUMERICAL_INDEX_TREND_ONLY'
    assert result['mesh_sizes_um'][0]['max_um'] == 120.
    assert result['rows'][0]['last_relative_drift'] == pytest.approx(.01/5.95)
    assert result['rows'][0]['step_drift_ratio'] == pytest.approx(.25)
    assert result['rows'][0]['trend'] == 'DECREASING_INDEX_DRIFT'
    assert result['mode_identity'].startswith('NOT_ESTABLISHED')
    assert result['mesh_convergence'] == 'NOT_ESTABLISHED'
    assert result['physical_validation'] == 'NOT_ESTABLISHED'
    assert result['fabrication'] == 'HOLD'


def test_drift_increases_but_not_a_false_pass():
    m,n,a = _triple()
    n[2]['modes'][0]['frequency_GHz'] = 6.1
    row = _eval(native=n)
    assert row['status'] == 'NUMERICAL_INDEX_TREND_ONLY'
    assert row['rows'][0]['trend'] == 'INCONCLUSIVE_OR_INCREASING_INDEX_DRIFT'
    assert row['mesh_convergence'] == 'NOT_ESTABLISHED'


@pytest.mark.parametrize('mutate', [
    lambda m,n,a: m[1]['layout']['components'][0].update(x_mm=2),
    lambda m,n,a: m[1]['process']['stack'][0].update(relative_permittivity=9.1),
    lambda m,n,a: m[2]['studies'][0]['inputs']['em']['solver'].update(order=2),
    lambda m,n,a: m[2]['studies'][0]['inputs']['em']['mesh'].update(relative_tolerance=.01),
    lambda m,n,a: m[2]['studies'][0]['inputs']['em']['mesh'].update(max_um=100),
    lambda m,n,a: m[0]['studies'][0]['inputs']['em']['mesh'].update(min_um=-2),
    lambda m,n,a: a[1].update(engine_version='different'),
    lambda m,n,a: a[2].update(artifact_type='scqubits.spectrum'),
    lambda m,n,a: n[2]['modes'][0].update(frequency_GHz=float('nan')),
    lambda m,n,a: n[2]['modes'].append({'mode_index':2,'frequency_GHz':10.}),
    lambda m,n,a: n[0].update(source='fabricated_fixture'),
    lambda m,n,a: n[0]['modes'][0].update(mode_index=9),
])
def test_confounded_or_invalid_refinement_blocks(mutate):
    m,n,a=_triple()
    mutate(m,n,a)
    assert _eval(models=m,native=n,manifests=a)['status']=='BLOCKED'


def test_case_registered_as_generic_eigenmode_diagnostic():
    cases = {x['id']:x for x in list_reference_cases()}
    r = cases['R03_PALACE_MESH_REFINEMENT']
    assert r['oracle_kind']=='THREE_RUN_NUMERICAL_REFINEMENT_SCREEN'
    assert r['tolerances'] is None
    assert 'overlap' in r['science_boundary']


def test_three_run_authenticated_http_and_tamper_rejection(tmp_path):
    """Real HTTP, auth, revision provenance and SHA gates; never a native solve."""
    server=make_server(tmp_path/'private',0)
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
        request=urllib.request.Request(base+path,method=method,headers=headers,
                    data=json.dumps(data).encode() if data is not None else None)
        try:response=opener.open(request,timeout=8)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            raw=response.read()
            return response.status,json.loads(raw) if response.headers.get('content-type','').startswith('application/json') else raw
    try:
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'m10@local.test',
                   'password':'local-test-long-password','setup_token':token})[0]==200
        rc,auth=req('/api/login','POST',{'email':'m10@local.test','password':'local-test-long-password'})
        assert rc==200
        csrf=auth['csrf']
        rc,new=req('/api/projects','POST',{'name':'Native Mesh Screen','family':'resonator',
                                           'template_id':'cpw_resonator_v1'})
        assert rc==201
        pid=new['id'];rid=new['head']
        models,natives,_=_triple()
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        revisions=[]
        # Same physical design; separate revision-bound mesh input and native CSV per run.
        for i,model in enumerate(models):
            if i:
                rc,commit=req(f'/api/projects/{pid}/commit','POST',
                              {'expected_revision':rid,'model':model})
                assert rc==200,commit
                rid=commit['revision']
            elif model != new['model']:
                rc,commit=req(f'/api/projects/{pid}/commit','POST',
                              {'expected_revision':rid,'model':model})
                assert rc==200,commit
                rid=commit['revision']
            revisions.append(rid)
        # The Store accepts jobs attached to older project revisions.
        run_ids=('a'*32,'b'*32,'c'*32)
        outputs=[]
        for i,(run_id,revision_id) in enumerate(zip(run_ids,revisions)):
            folder=server.app.store.root/'native-runs'/pid/run_id
            folder.mkdir(parents=True)
            server.app.store.put_run(owner,pid,revision_id,'ResEigen','sqdmetal_palace',folder)
            server.app.store.set_run(run_id,'completed')
            output=folder/'output'
            (output/'sqe_em/outputFiles').mkdir(parents=True)
            csv=f'm,f (GHz),Im(f) (GHz),Q\n1,{natives[i]["modes"][0]["frequency_GHz"]},0,359000\n'.encode()
            name='sqe_em/outputFiles/eig.csv'
            target=output/name;target.write_bytes(csv);outputs.append(target)
            project=server.app.store.project(owner,pid,revision_id)
            manifest={'schema':'sqe.artifact.v1','engine':'sqdmetal_palace',
                'engine_version':'fixture_only_not_native','kind':'eigenmode',
                'artifact_type':'palace.eigenmodes','scientific_status':'review_required',
                'fabrication_status':'HOLD','revision_id':revision_id,
                'project_digest':project['revision_digest'],'study_id':'ResEigen',
                'parents':[],'provenance':{'used_revision':revision_id,
                'used_project_sha256':project['revision_digest']},
                'artifacts':[{'name':name,'sha256':sha_bytes(csv),'bytes':len(csv)}]}
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
        endpoint=f'/api/projects/{pid}/compare?left={run_ids[0]}&right={run_ids[1]}&fine={run_ids[2]}'
        rc,result=req(endpoint)
        assert rc==200,result
        assert result['mesh_refinement_series']['status']=='NUMERICAL_INDEX_TREND_ONLY'
        assert result['fine']['run_id']==run_ids[2]
        assert result['mesh_refinement_series']['mesh_convergence']=='NOT_ESTABLISHED'
        assert req(endpoint.replace('&fine='+run_ids[2],'x'))[0]==400
        assert req(endpoint.replace('&fine='+run_ids[2],'&fine='+run_ids[1]))[0]==400
        outputs[2].write_bytes(b'changed native artifact')
        assert req(endpoint)[0]==409
        assert req('/api/logout','POST',{})[0]==200
        assert req(endpoint)[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
