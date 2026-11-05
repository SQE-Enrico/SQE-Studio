"""M8: numerical fixture probes, NEVER reports of a native solver execution."""
import copy
import json
import math
import threading
import urllib.error
import urllib.request
import http.cookiejar
from pathlib import Path

import pytest

from sqe_studio.contracts import digest
from sqe_studio.design_library import instantiate, use_case_catalog
from sqe_studio.eda.scientific_references import (
    CASES, list_reference_cases, evaluate_verified_result,
)
from sqe_studio.server import make_server


def _source():
    model = instantiate('transmon_spectrum_v1', 'Diagnostic', 'transmon')
    p = {'revision': 'ab'*16, 'revision_digest': digest(model), 'model': model}
    m = {'revision_id': p['revision'], 'project_digest': p['revision_digest'],
         'study_id': 'QuantumSpectrum', 'engine': 'scqubits',
         'artifact_type': 'scqubits.spectrum'}
    inputs = model['studies'][0]['inputs']
    ej, ec = inputs['parameters']['EJ'], inputs['parameters']['EC']
    predicted = math.sqrt(8*ej*ec)-ec
    # Synthetic numbers exercise the comparator. They are NOT solver evidence.
    s = {'schema':'sqe.scqubits.spectrum.v1', 'model':'Transmon',
         'input_sha256':digest(inputs), 'units':'GHz', 'energy_unit':'GHz',
         'axis':None, 'preview_point_index':0,
         'levels':[-15, -15+predicted*.995, -15+2*predicted*.995-ec*1.04],
         'convergence':{'status':'not_checked'}}
    return p, m, s


def test_registry_links_to_generic_eda_use_cases_and_provenance():
    cases=list_reference_cases()
    assert len(cases)>=6 and len({x['id'] for x in cases})==len(cases)
    assert {'T01_KOCH_ASYMPTOTIC','T02_MAXWELL_CHARGING_UNITS',
            'R01_GOPPL_CPW_2008','R02_CPW_LENGTH_SCALING',
            'J01_KAUFMAN_2023','E01_MINEV_EPR_2021'} <= {x['id'] for x in cases}
    use_cases={x['id'] for x in use_case_catalog()}
    assert all(c['use_case_id'] in use_cases for c in cases)
    assert all(c['reference'].get('doi', '').startswith('10.') or
               c['reference'].get('url', '').startswith('https://') for c in cases)
    assert all(c['science_boundary'] and c['oracle_kind'] for c in cases)
    assert next(c for c in cases if c['id']=='R01_GOPPL_CPW_2008')['published']['resonator_length_mm']==14.220
    assert next(c for c in cases if c['id']=='J01_KAUFMAN_2023')['readiness']=='blocked_missing_native_edge'
    cases[0]['title']='untrusted mutation'
    assert list_reference_cases()[0]['title'] != 'untrusted mutation'


def test_koch_asymptotic_on_generic_native_spectrum_fixture():
    p,m,s=_source()
    result=evaluate_verified_result(project=p,manifest=m,spectrum=s)
    row=result['evaluations'][0]
    assert row['status']=='NUMERICAL_PASS'
    assert len(row['checks'])==2 and all(x['pass'] for x in row['checks'])
    assert row['basis_convergence']=='NOT_CHECKED'
    assert result['scientific_qualification']=='NOT_ESTABLISHED'
    assert result['fabrication']=='HOLD'
    s['levels'][1]+=1.5
    s['levels'][2]+=3
    assert evaluate_verified_result(project=p,manifest=m,spectrum=s)['evaluations'][0]['status']=='NUMERICAL_FAIL'


def test_analytical_oracle_fail_closed_on_invalid_source_or_physics():
    p,m,s=_source()
    assert evaluate_verified_result(project=p,manifest=m,spectrum=s)['evaluations'][0]['status']=='NUMERICAL_PASS'
    for change in ('sha','units','ratio','sweep','nan'):
        pp, mm, ss=copy.deepcopy((p,m,s))
        if change=='sha': ss['input_sha256']='0'*64
        if change=='units': ss['units']='MHz'
        if change=='ratio': pp['model']['studies'][0]['inputs']['parameters']['EJ']=2.0
        if change=='sweep': ss['axis']={'parameter':'ng','values':[0.,.5]}
        if change=='nan': ss['levels'][1]=float('nan')
        assert evaluate_verified_result(project=pp,manifest=mm,spectrum=ss)['evaluations'][0]['status']=='BLOCKED'
    m['revision_id']='changed'
    with pytest.raises(ValueError,match='revision/digest'):
        evaluate_verified_result(project=p,manifest=m,spectrum=s)


def test_maxwell_energy_unit_oracle_from_conditional_native_screen_fixture():
    p,m,s=_source()
    m.update(engine='sqdmetal_palace',artifact_type='palace.capacitance_matrix')
    capacitance=80.e-15
    # separate constants and conversion path; this fixture stands for an
    # already-authenticated upstream *read-only* reduction, not a Palace solve.
    energy=(1.602176634e-19**2)/(2*6.62607015e-34*capacitance)
    screen={'status':'NUMERICAL_SCREEN_ONLY', 'scqubits_EC_transfer':'BLOCKED_NOT_REVIEWED',
            'reduction': {'status':'NUMERICAL_SCREEN_ONLY', 'numerical_preview': {
                'effective_capacitance_f': capacitance,
                'ec_over_h_hz_matrix_only': energy}}}
    r=evaluate_verified_result(project=p,manifest=m,transmon_screen=screen)
    row=r['evaluations'][1]
    assert row['status']=='NUMERICAL_PASS'
    assert abs(row['checks'][0]['actual']/1e6-242.13)<.1
    assert row['measurements']['scqubits_EC_transfer']=='BLOCKED'
    screen['reduction']['numerical_preview']['ec_over_h_hz_matrix_only']*=1.02
    assert evaluate_verified_result(project=p,manifest=m,transmon_screen=screen)['evaluations'][1]['status']=='NUMERICAL_FAIL'
    screen['scqubits_EC_transfer']='APPROVED'
    assert evaluate_verified_result(project=p,manifest=m,transmon_screen=screen)['evaluations'][1]['status']=='BLOCKED'


def test_cpw_published_device_not_automatically_compared_to_arbitrary_native_run():
    p,m,s=_source()
    result=evaluate_verified_result(project=p,manifest=m,spectrum=s)
    assert all(r['status']=='NOT_APPLICABLE' for r in result['evaluations'][2:])
    assert all(r['physical_validation']=='NOT_ESTABLISHED' for r in result['evaluations'])


def test_authenticated_reference_catalog_api(tmp_path):
    server=make_server(tmp_path/'private',0)
    th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
    try:
        base=f'http://127.0.0.1:{server.server_port}'
        jar=http.cookiejar.CookieJar()
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
        def call(path,body=None,csrf=None):
            headers={}
            if body is not None:headers['Content-Type']='application/json'
            if csrf:headers['X-CSRF-Token']=csrf
            request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:r=client.open(request,timeout=5)
            except urllib.error.HTTPError as err:r=err
            with r:return r.status,json.loads(r.read())
        assert call('/api/design/scientific-references')[0]==401
        assert call('/api/setup',{'email':'user@local.test','password':'secure-test-password',
                                  'setup_token':server.app.setup_file.read_text()})[0]==200
        assert call('/api/login',{'email':'user@local.test','password':'secure-test-password'})[0]==200
        status,record=call('/api/design/scientific-references')
        assert status==200 and record['schema']=='sqe.scientific-reference-catalog.m8.v1'
        assert len(record['cases'])>=6
    finally:
        server.shutdown();server.server_close();th.join(timeout=3)


def test_real_native_scqubits_when_installed(tmp_path):
    pytest.importorskip('scqubits')
    from sqe_studio.adapters.scqubits_adapter import run
    p,m,_=_source()
    study=p['model']['studies'][0]
    output=tmp_path/'native'
    output.mkdir()
    run(study,p['model'],output)
    spectrum=json.loads((output/'spectrum.json').read_text())
    result=evaluate_verified_result(project=p,manifest=m,spectrum=spectrum)
    assert result['evaluations'][0]['status']=='NUMERICAL_PASS'
    assert result['evaluations'][0]['physical_validation']=='NOT_ESTABLISHED'
