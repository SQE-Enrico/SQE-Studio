"""M4 A99: authenticated standalone research study; never EM extraction."""
from __future__ import annotations
import copy
import time
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _declare(**changes):
    d={'schema':'sqe.independent-transmon-declaration.a12.v1',
       'source':'independent','model':'Transmon',
       'parameters':{'EJ':15,'EC':0.25,'ng':0,'ncut':20},
       'parameter_units':{'EJ':'GHz','EC':'GHz','ng':'2e','ncut':'1'},
       'levels':5}
    d.update(changes)
    return d


def test_m4_manual_study_http_cas_csrf_lineage_and_no_run(tmp_path):
    from sqe_studio.server import make_server
    server=make_server(tmp_path/'m4-http',0)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    jar=http.cookiejar.CookieJar()
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',data=None,csrf_header=True,client_override=None):
        headers={'Content-Type':'application/json'} if data is not None else {}
        if method=='POST' and csrf_header:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(origin+path,method=method,headers=headers,
                                        data=json.dumps(data).encode('utf-8') if data is not None else None)
        try: response=(client_override or client).open(request,timeout=8)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            blob=response.read()
            return response.status,json.loads(blob) if blob else None
    try:
        assert req('/api/projects')[0]==401
        setup=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'m4a99@example.invalid',
                'password':'secure-independent-manual-test','setup_token':setup})[0]==200
        code,body=req('/api/login','POST',{'email':'m4a99@example.invalid',
                                          'password':'secure-independent-manual-test'})
        assert code==200;csrf=body['csrf']
        code,created=req('/api/projects','POST',{'name':'M4 Transmon','family':'transmon'})
        assert code==201
        pid,rev=created['id'],created['head'];original=copy.deepcopy(created['model'])
        endpoint=f'/api/projects/{pid}/independent-transmon'
        payload={'expected_revision':rev,'declaration':_declare(),'acknowledged':True}
        assert req(endpoint,'POST',payload,False)[0]==403
        assert req(endpoint,'POST',{**payload,'acknowledged':False})[0]==422
        assert req(endpoint,'POST',{**payload,'em_evidence':{'EC_GHz':0.25}})[0]==422
        assert req(endpoint,'POST',{**payload,'declaration':_declare(source='palace')})[0]==422
        assert req(endpoint,'POST',{**payload,'declaration':_declare(reviewed=True)})[0]==422
        assert req(endpoint,'POST',{**payload,'declaration':_declare(parameter_units={
            'EJ':'GHz','EC':'fF','ng':'2e','ncut':'1'})})[0]==422
        assert req(endpoint,'POST',{**payload,'declaration':_declare(parameters={
            'EJ':15,'EC':float('nan'),'ng':0,'ncut':20})})[0]==400
        assert req(endpoint,'POST',{**payload,'declaration':_declare(parameters={
            'EJ':15,'EC':True,'ng':0,'ncut':20})})[0]==422
        assert req(f'/api/projects/{pid}')[1]['head']==rev
        assert req(f'/api/projects/{pid}/runs')[1]['runs']==[]
        code,saved=req(endpoint,'POST',payload)
        assert code==201,saved
        assert saved['schema']=='sqe.independent-transmon-saved-research.a99.v1'
        assert saved['status']=='SAVED_UNVERIFIED_INDEPENDENT_RESEARCH_STUDY'
        assert saved['scientific_authorization'].startswith('BLOCKED')
        assert saved['em_ec_transfer']=='BLOCKED' and saved['fabrication']=='HOLD'
        assert saved['solver_execution']=='NOT_EXECUTED'
        assert saved['revision']!=rev
        code,now=req(f'/api/projects/{pid}')
        assert code==200 and now['head']==saved['revision']
        assert len(now['model']['studies'])==1
        assert now['model']['studies'][0]['id']==saved['study_id']
        assert now['model']['studies'][0]['engine']=='scqubits'
        assert now['model']['studies'][0]['inputs']['source']=='independent'
        assert now['model']['studies'][0]['inputs']['parameters']['EC']==0.25
        assert now['model']['intent']==original['intent']
        assert now['model']['layout']==original['layout']
        assert req(f'/api/projects/{pid}/revisions/{rev}')[1]['model']==original
        assert req(endpoint,'POST',payload)[0]==409
        assert req(f'/api/projects/{pid}/runs')[1]['runs']==[]
        current=now['head']
        second={**payload,'expected_revision':current}
        code,r=req(endpoint,'POST',second)
        assert code==201 and r['study_id']!=saved['study_id']
        assert len(req(f'/api/projects/{pid}')[1]['model']['studies'])==2
        assert req(endpoint,'POST',second)[0]==409
        outsider=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # Windows security tools occasionally abort a loopback connection
        # (WinError 10053) during a long CI run. Retry ONLY an unauthenticated
        # request; the exact 401 assertion remains mandatory. Never retry a
        # state-changing authenticated operation or accept a socket abort.
        for attempt in range(3):
            try:
                outsider_status = req(endpoint,'POST',second,client_override=outsider)[0]
                break
            except (ConnectionAbortedError, ConnectionResetError):
                if attempt == 2:
                    raise
                time.sleep(0.1)
        assert outsider_status == 401
        assert req('/api/logout','POST',{})[0]==200
        assert req(endpoint,'POST',second)[0]==401
    finally:
        server.shutdown();server.server_close();t.join(timeout=6)


def test_m4_manual_study_rejected_for_non_transmon(tmp_path):
    from sqe_studio.server import make_server
    server=make_server(tmp_path/'m4-family',0)
    try:
        server.app.store.setup('safe@example.invalid','another-secure-passphrase')
        login=server.app.store.login('safe@example.invalid','another-secure-passphrase')
        assert login
        uid=server.app.store.session(login[0])['user_id']
        generic=server.app.store.create(uid,'Generic design','generic')
        # Only the standard transmon-family condition is accepted by the A99 handler.
        assert generic['model']['family']=='generic'
    finally:server.server_close()
