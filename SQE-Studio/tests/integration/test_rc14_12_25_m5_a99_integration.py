"""A99 M5 integration: actual authenticated HTTP, no native solver on CI.

Synthetic project and Palace artifacts are never labeled physically qualified.
"""
from __future__ import annotations

import copy
import http.cookiejar
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqe_studio.interop.independent_transmon_origin import (
    ManualOriginBlocked, require_manual_study_creation,
)
from sqe_studio.interop.independent_transmon_execution import REQUEST_SCHEMA
from sqe_studio.jobs import Jobs
from sqe_studio.store import Conflict
from sqe_studio.server import make_server


def declaration():
    return {'schema': 'sqe.independent-transmon-declaration.a12.v1',
            'source': 'independent', 'model': 'Transmon',
            'parameters': {'EJ': 15, 'EC': 0.25, 'ng': 0, 'ncut': 20},
            'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
            'levels': 5}


def test_m5_authenticated_saved_manual_study_preflight_execution_and_denials(tmp_path, monkeypatch):
    server = make_server(tmp_path/'private', 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                         urllib.request.ProxyHandler({}))
    outsider = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    csrf = ''
    def req(path, method='GET', body=None, session=client, csrf_ok=True):
        headers = {'Content-Type':'application/json'} if body is not None else {}
        if method == 'POST' and csrf_ok:
            headers['X-CSRF-Token'] = csrf
        r = urllib.request.Request(base+path, method=method, headers=headers,
                                   data=json.dumps(body).encode('utf-8') if body is not None else None)
        try: response = session.open(r, timeout=9)
        except urllib.error.HTTPError as exc: response=exc
        with response:
            raw=response.read()
            return response.status, json.loads(raw) if raw else None
    try:
        token = server.app.setup_file.read_text()
        assert req('/api/setup','POST', {'email':'m5@test.invalid',
                   'password':'test-password-long-enough', 'setup_token':token})[0] == 200
        code, login=req('/api/login','POST',{'email':'m5@test.invalid',
                   'password':'test-password-long-enough'})
        assert code==200; csrf=login['csrf']
        code, created=req('/api/projects','POST', {'name':'M5 manual transmon', 'family':'transmon'})
        assert code==201
        pid,rev=created['id'],created['head']
        endpoint=f'/api/projects/{pid}/independent-transmon'
        code,saved=req(endpoint,'POST',{'expected_revision':rev,
                         'declaration':declaration(),'acknowledged':True})
        assert code==201
        newrev, study=saved['revision'],saved['study_id']
        owner=server.app.store.session(next(c.value for c in jar if c.name=='sqe_session'))['user_id']
        current=server.app.store.project(owner,pid)
        assert require_manual_study_creation(server.app.store, owner,pid,newrev,study)==current
        selector={'schema':REQUEST_SCHEMA,'project_id':pid,
                  'expected_revision':newrev,'study_id':study}
        pre=f'{endpoint}/preflight'
        execute=f'{endpoint}/execute'
        assert req(pre,'POST',selector,csrf_ok=False)[0]==403
        assert req(pre,'POST',selector,session=outsider)[0]==401
        code,plan=req(pre,'POST',selector)
        assert code==200 and plan['status']=='READY_FOR_SOFTWARE_EXECUTION_ONLY'
        assert plan['scientific_authorization'].startswith('BLOCKED')
        assert plan['em_ec_transfer']=='BLOCKED' and plan['fabrication']=='HOLD'
        assert plan['adapter_invocation_plan']['inputs']['parameters']['EC']==0.25
        assert req(pre,'POST',{**selector,'EC':0.25})[0]==422
        assert req(pre,'POST',{**selector,'expected_revision':'0'*32})[0]==409
        assert req(pre,'POST',{**selector,'study_id':'quantum_01'})[0]==409
        # The native worker is deliberately NOT invoked by this test: only
        # verify API routing, saved selectors, and successful explicit enqueue.
        mocked=Mock(return_value='c'*32)
        monkeypatch.setattr(server.app.jobs,'start',mocked)
        code,queued=req(execute,'POST',selector)
        assert code==202 and queued['run_id']=='c'*32
        assert queued['em_ec_transfer']=='BLOCKED' and queued['fabrication']=='HOLD'
        mocked.assert_called_once_with(owner,pid,newrev,study)
        # Fake generic project commit cannot create server-side origin proof.
        forged=copy.deepcopy(current['model'])
        forged['studies'][0]['id']='independent_transmon_02'
        code,committed=req(f'/api/projects/{pid}/commit','POST',
                           {'expected_revision':newrev,'model':forged})
        assert code==200
        fake_rev=committed['revision']
        fake_selector={**selector,'expected_revision':fake_rev,'study_id':'independent_transmon_02'}
        assert req(pre,'POST',fake_selector)[0]==409
        # Old head cannot be executed after any commit.
        assert req(pre,'POST',selector)[0]==409
        with pytest.raises(ManualOriginBlocked):
            require_manual_study_creation(server.app.store,owner,pid,fake_rev,'independent_transmon_02')
        assert req('/api/logout','POST',{})[0]==200
        assert req(pre,'POST',fake_selector)[0]==401
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)


def test_m5_job_core_refuses_manual_lookalikes_and_tampered_origin(tmp_path,monkeypatch):
    from sqe_studio.store import Store
    from sqe_studio.contracts import digest
    from sqe_studio.interop.transmon_quantum_preflight import build_independent_transmon_preflight
    store=Store(tmp_path/'db')
    original=store.create('user','M5 project','transmon')
    model=copy.deepcopy(original['model'])
    study={'id':'independent_transmon_01',
           **build_independent_transmon_preflight(declaration())['study_template']}
    model['studies'].append(study)
    revision=store.commit('user',original['id'],original['head'],model)
    job=Jobs(store)
    reached=[]
    monkeypatch.setattr(job,'_acquire_slot',lambda:reached.append(True))
    with pytest.raises(Conflict):
        job.start('user',original['id'],revision,'independent_transmon_01')
    assert reached==[]
    # Generic commits with a copied M4 study cannot manufacture origin evidence.
    marker=store.root/'manual-transmon-creation'/original['id']/(revision+'-independent_transmon_01.json')
    marker.write_text(json.dumps({'scientific_authorization':'APPROVED'}))
    with pytest.raises(Conflict):
        job.start('user',original['id'],revision,'independent_transmon_01')
    assert reached==[]


def test_m5_ancestry_accepts_unchanged_manual_study_but_not_mutate_restore(tmp_path):
    from sqe_studio.store import Store
    from sqe_studio.interop.independent_transmon_origin import record_manual_study_creation
    from sqe_studio.interop.transmon_quantum_preflight import build_independent_transmon_preflight
    store=Store(tmp_path/'ancestry')
    made=store.create('user','M5 history','transmon')
    pid=made['id']
    model=copy.deepcopy(made['model'])
    model['studies'].append({'id':'independent_transmon_01',
        **build_independent_transmon_preflight(declaration())['study_template']})
    one=store.commit('user',pid,made['head'],model)
    record_manual_study_creation(store,'user',pid,one,'independent_transmon_01')
    # A later normal project commit that does not edit these exact saved
    # inputs must not make an earlier manual study unusable.
    two=store.commit('user',pid,one,copy.deepcopy(model))
    assert require_manual_study_creation(store,'user',pid,two,'independent_transmon_01')['revision']==two
    # An edited numerical EC then restored later is not continuous evidence.
    altered=copy.deepcopy(model)
    altered['studies'][0]['inputs']['parameters']['EC']=0.3
    three=store.commit('user',pid,two,altered)
    four=store.commit('user',pid,three,copy.deepcopy(model))
    with pytest.raises(ManualOriginBlocked):
        require_manual_study_creation(store,'user',pid,four,'independent_transmon_01')


def test_m5_b04_fixture_remains_independent_of_native_solver(tmp_path):
    # The B04 readiness module is intentionally tested with synthetic records.
    # Production Results HTTP/current-head and historical protections are
    # asserted by test_rc14_20_transmon_workflow.py.
    path=Path(__file__).with_name('test_rc14_20_transmon_workflow.py')
    spec=importlib.util.spec_from_file_location('_m1_http_b04',path)
    m1=importlib.util.module_from_spec(spec);spec.loader.exec_module(m1)
    folder,manifest,project=m1.prepared(tmp_path)
    from sqe_studio.interop.transmon_workflow import inspect_saved_transmon_screen
    screen=inspect_saved_transmon_screen(folder,manifest,project)
    assert screen['status']=='NUMERICAL_SCREEN_ONLY'
    assert screen['scqubits_EC_transfer']=='BLOCKED_NOT_REVIEWED'
    assert screen['fabrication']=='HOLD'
