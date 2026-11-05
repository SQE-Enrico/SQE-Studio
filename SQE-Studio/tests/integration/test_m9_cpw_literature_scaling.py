"""Literature-method and fake-native-shaped data tests, NOT a Palace solve.

Physical source: Goppl et al., J. Appl. Phys. 104, 113904 (2008),
DOI 10.1063/1.3010859, Eq. (1), Table I. Table values are MEASUREMENTS.
No reference values are injected into SQE native results or a template.
"""
from __future__ import annotations

from copy import deepcopy
import math
import pytest

from sqe_studio.design_library import instantiate
from sqe_studio.eda.cpw_scaling import (
    RELATIVE_TOLERANCE_PROVISIONAL, compare_verified_cpw_length_scaling,
    length_scaling_ratio,
)
from sqe_studio.eda.scientific_references import list_reference_cases


def _models():
    left = instantiate('cpw_resonator_v1', 'Ordinary CPW', 'resonator')
    right = deepcopy(left)
    route = next(x for x in right['layout']['components'] if x['kind'] == 'RouteMeander')
    route['total_length_mm'] = 4.4
    return left, right


def _native(frequency, *, other_modes=()):
    return {'source':'palace.native_eig.csv', 'units':'GHz',
            'mode_matching':'not_established', 'convergence':'not_established',
            'modes':[{'mode_index':i, 'frequency_GHz':v}
                     for i,v in enumerate((frequency, *other_modes),1)]}


def _compare(left=None,right=None,fa=6.0,fb=None,**kwargs):
    a,b = _models()
    if left is not None: a = left
    if right is not None: b = right
    if fb is None: fb = fa*3.7/4.4*1.01
    return compare_verified_cpw_length_scaling(
        left_model=a,right_model=b,left_study_id='ResEigen',right_study_id='ResEigen',
        left_native=_native(fa),right_native=_native(fb), **kwargs)


def test_literature_table_i_halfwave_line_model_is_accurate_without_tuning():
    # Published Table I: design lengths (mm) vs MEASURED resonance (GHz).
    # epsilon_eff=5.05 comes from their fit, not a native SQE or Palace result.
    measured=((28.449,2.3430),(18.970,3.5199),(14.220,4.6846),
              (11.380,5.8491),(9.480,7.0162),(8.130,8.1778))
    for length_mm, f_GHz in measured:
        analytic=299792458/(2*(length_mm/1000)*math.sqrt(5.05))/1e9
        assert abs(analytic/f_GHz-1) < .01
    assert all(abs((f2/f1)-length_scaling_ratio(l1,l2))<.02
               for (l1,f1),(l2,f2) in zip(measured,measured[1:]))


def test_pairwise_screen_uses_actual_generic_saved_route_lengths():
    row=_compare()
    assert row['status']=='NUMERICAL_SCREEN_PASS'
    assert row['case_id']=='R02_CPW_LENGTH_SCALING'
    assert row['lengths_mm']=={'left':3.7,'right':4.4}
    assert row['checks'][0]['reference']==pytest.approx(3.7/4.4)
    assert row['checks'][0]['actual']==pytest.approx(3.7/4.4*1.01)
    assert row['checks'][0]['relative_tolerance']==RELATIVE_TOLERANCE_PROVISIONAL
    assert row['mode_identity']=='NOT_ESTABLISHED'
    assert row['mesh_convergence']=='NOT_ESTABLISHED'
    assert row['physical_validation']=='NOT_ESTABLISHED'
    assert row['fabrication']=='HOLD'


def test_unsuitable_native_numeric_produces_failure_not_a_blocked_result():
    row=_compare(fa=6.0,fb=6.0)
    assert row['status']=='NUMERICAL_SCREEN_FAIL'
    assert not row['checks'][0]['pass']
    assert row['physical_validation']=='NOT_ESTABLISHED'


@pytest.mark.parametrize('mutator', [
    lambda a,b: b['process']['stack'][0].update(relative_permittivity=9.8),
    lambda a,b: b['layout']['components'][0].update(x_mm=0.4),
    lambda a,b: b['layout']['components'][-1].update(trace_width_um=22),
    lambda a,b: b['studies'][0]['inputs']['em']['mesh'].update(max_um=220),
    lambda a,b: b['studies'][0]['inputs']['em']['solver'].update(modes=3),
    lambda a,b: b.update(family='transmon'),
    lambda a,b: b['layout']['components'][-1].update(total_length_mm=3.71),
    lambda a,b: b['layout']['components'][-1].update(total_length_mm=-4),
    lambda a,b: b['layout']['components'][-1].update(total_length_mm='4.4'),
    lambda a,b: b['layout']['components'][-1].update(kind='RouteStraight'),
])
def test_comparison_blocks_confounded_or_invalid_designs(mutator):
    a,b=_models()
    mutator(a,b)
    assert _compare(left=a,right=b)['status']=='BLOCKED'


def test_no_automated_physics_qualification_from_equal_or_ambiguous_modes():
    a,b=_models()
    base={'left_model':a,'right_model':b,'left_study_id':'ResEigen','right_study_id':'ResEigen',
          'left_native':_native(6.0),'right_native':_native(5.05)}
    for alteration in ({'right_native':_native(5.05, other_modes=(8.0,))},
                       {'right_native':_native(float('nan'))},
                       {'left_native':None},
                       {'left_native':{'source':'fixture-fabricated','units':'GHz','modes':[]}}):
        assert compare_verified_cpw_length_scaling(**{**base,**alteration})['status']=='BLOCKED'


def test_reference_catalog_keeps_measured_device_separate_from_generic_scaling():
    c={r['id']:r for r in list_reference_cases()}
    assert c['R01_GOPPL_CPW_2008']['oracle_kind']=='PUBLISHED_DEVICE_MEASUREMENT'
    assert c['R02_CPW_LENGTH_SCALING']['oracle_kind']=='LITERATURE_TRANSMISSION_LINE_SCALING'
    assert 'length_left/length_right' in c['R02_CPW_LENGTH_SCALING']['method']
    assert c['R02_CPW_LENGTH_SCALING']['reference']['doi']=='10.1063/1.3010859'


def test_authenticated_native_shaped_cpw_pair_http_and_sha_rejection(tmp_path):
    """Fixture files exercise original HTTP trust gate, not an EM calculation."""
    import http.cookiejar
    import json
    import threading
    import urllib.error
    import urllib.request
    from sqe_studio.server import make_server
    from sqe_studio.orchestration.artifacts import sha_bytes

    server=make_server(tmp_path/'private',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',data=None):
        headers={}
        if data is not None: headers['Content-Type']='application/json'
        if csrf and method=='POST':headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=headers,
                    data=json.dumps(data).encode() if data is not None else None)
        try: response=opener.open(request,timeout=8)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            raw=response.read()
            return response.status,json.loads(raw) if response.headers.get('content-type','').startswith('application/json') else raw
    try:
        assert req('/api/design/scientific-references')[0]==401
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'cpw@local.test','password':'test-only-long-password','setup_token':token})[0]==200
        rc,auth=req('/api/login','POST',{'email':'cpw@local.test','password':'test-only-long-password'})
        assert rc==200
        csrf=auth['csrf']
        rc,cases=req('/api/design/scientific-references')
        assert rc==200 and any(c['id']=='R02_CPW_LENGTH_SCALING' for c in cases['cases'])
        rc,initial=req('/api/projects','POST',{'name':'Research CPW','family':'resonator',
                                                 'template_id':'cpw_resonator_v1'})
        assert rc==201
        pid=initial['id'];rev_a=initial['head']
        changed=deepcopy(initial['model'])
        next(x for x in changed['layout']['components'] if x['kind']=='RouteMeander')['total_length_mm']=4.4
        rc,revision=req(f'/api/projects/{pid}/commit','POST',{'expected_revision':rev_a,'model':changed})
        assert rc==200
        rev_b=revision['revision']
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        ids=('a'*32,'b'*32)
        root=server.app.store.root/'native-runs'/pid
        def fake_run(run_id, revision_id, frequency):
            folder=root/run_id
            folder.mkdir(parents=True)
            server.app.store.put_run(owner,pid,revision_id,'ResEigen','sqdmetal_palace',folder)
            server.app.store.set_run(run_id,'completed')
            output=folder/'output';(output/'sqe_em/outputFiles').mkdir(parents=True)
            raw=f'm,f (GHz),Im(f) (GHz),Q\n1,{frequency},0,350000\n'.encode()
            name='sqe_em/outputFiles/eig.csv'
            target=output/name;target.write_bytes(raw)
            proj=server.app.store.project(owner,pid,revision_id)
            manifest={'schema':'sqe.artifact.v1','engine':'sqdmetal_palace',
                      'engine_version':'fixture_only_not_native', 'kind':'eigenmode',
                      'artifact_type':'palace.eigenmodes','scientific_status':'review_required',
                      'fabrication_status':'HOLD', 'revision_id':revision_id,
                      'project_digest':proj['revision_digest'],'study_id':'ResEigen','parents':[],
                      'provenance':{'used_revision':revision_id,
                                    'used_project_sha256':proj['revision_digest']},
                      'artifacts':[{'name':name,'sha256':sha_bytes(raw),'bytes':len(raw)}]}
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
            return target
        fake_run(ids[0],rev_a,6.0)
        changed_file=fake_run(ids[1],rev_b,6.0*3.7/4.4*1.01)
        endpoint=f'/api/projects/{pid}/compare?left={ids[0]}&right={ids[1]}'
        rc,compared=req(endpoint)
        assert rc==200,compared
        assert compared['numerical_comparison']['status']=='not_comparable' # geometry changed, mesh convergence not shown
        cpw=compared['cpw_length_scaling_reference']
        assert cpw['status']=='NUMERICAL_SCREEN_PASS'
        assert cpw['physical_validation']=='NOT_ESTABLISHED'
        assert cpw['checks'][0]['relative_error']==pytest.approx(.01)
        changed_file.write_text('m,f (GHz),Im(f) (GHz),Q\n1,6.0,0,350000\n')
        assert req(endpoint)[0]==409 # original authenticated hash gate, no stale numeric pass
        assert req('/api/logout','POST',{})[0]==200
        assert req(endpoint)[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_single_run_diagnostic_keeps_pairwise_reference_blocked():
    from sqe_studio.contracts import digest
    from sqe_studio.eda.scientific_references import evaluate_verified_result
    model=instantiate('cpw_resonator_v1','Research CPW','resonator')
    project={'revision':'a'*32,'revision_digest':digest(model),'model':model}
    manifest={'revision_id':project['revision'],'project_digest':project['revision_digest'],
              'study_id':'ResEigen','artifact_type':'palace.eigenmodes'}
    row=next(x for x in evaluate_verified_result(project=project,manifest=manifest)['evaluations']
             if x['case_id']=='R02_CPW_LENGTH_SCALING')
    assert row['status']=='BLOCKED'
    assert 'Expert cross-run' in row['reason']
    assert row['physical_validation']=='NOT_ESTABLISHED'
