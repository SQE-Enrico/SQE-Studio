"""Installed-wheel HTTP acceptance in an isolated interpreter and temporary workspace.

No pytest, mock scientific result, source PYTHONPATH or non-loopback network.
"""
from __future__ import annotations

import http.cookiejar
import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from sqe_studio.server import make_server
from sqe_studio.eda.use_cases import list_use_cases


def main():
    with tempfile.TemporaryDirectory(prefix='sqe-wheel-http-') as td:
        server=make_server(Path(td)/'data',port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            jar=http.cookiejar.CookieJar()
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            def request(path, obj=None, csrf=None, method=None):
                data=None if obj is None else json.dumps(obj).encode('utf-8')
                hdr={'Content-Type':'application/json'} if data is not None else {}
                if csrf: hdr['X-CSRF-Token']=csrf
                req=urllib.request.Request(base+path,data=data,headers=hdr,method=method or ('POST' if obj is not None else 'GET'))
                try:
                    with client.open(req,timeout=6) as response:
                        return response.status, response.read(), response.headers.get('Content-Type','')
                except urllib.error.HTTPError as error:
                    return error.code, error.read(), error.headers.get('Content-Type','')
            assert request('/api/projects')[0]==401
            assert request('/api/status')[0]==200
            assert request('/app.js')[0]==200
            assert request('/style.css')[0]==200
            assert len(list_use_cases())>=6
            setup=server.app.setup_file.read_text(encoding='ascii')
            assert request('/api/setup', {'setup_token':setup,'email':'wheel@example.invalid',
                                          'password':'LocalTemporaryTestPassword123'})[0]==200
            status, raw, _=request('/api/login', {'email':'wheel@example.invalid',
                                                'password':'LocalTemporaryTestPassword123'})
            assert status==200
            csrf=json.loads(raw)['csrf']
            status, raw, _=request('/api/projects',{'name':'CPW Installed Acceptance',
                              'family':'resonator','template_id':'cpw_resonator_v1'},csrf)
            assert status==201, (status,raw[:300])
            project=json.loads(raw)
            assert project['model']['layout']['components']
            assert request('/api/projects/'+project['id'])[0]==200
            assert request('/api/projects/'+project['id']+'/commit',
                           {'expected_revision':'0'*64,'model':project['model']},csrf)[0]==409
            assert request('/api/engines')[0]==200
            assert request('/api/logout',{},csrf)[0]==200
            assert request('/api/projects')[0]==401
            print('PASS: installed wheel, real local HTTP, auth/CSRF, CPW model, stale revision, UI resources, logout')
            print('No native EM solve or scientific validation was asserted.')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=4)


if __name__=='__main__':main()
