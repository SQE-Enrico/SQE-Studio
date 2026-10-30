"""Actual local-HTTP acceptance without a browser: auth, CAS revisions, failed native job, archive.

This deliberately does NOT claim Playwright coverage or screenshot/keyboard acceptance.
"""
from __future__ import annotations

import http.cookiejar
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from sqe_studio.server import make_server


def test_real_local_http_security_revision_and_native_failure(tmp_path):
    server = make_server(tmp_path / 'private-data', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
    csrf = ''
    def req(path, method='GET', payload=None, binary=False, auth_csrf=True):
        headers = {}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if method != 'GET' and auth_csrf:
            headers['X-CSRF-Token'] = csrf
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(origin + path, data=body, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            if binary and response.status == 200:
                return response.status, raw
            return response.status, json.loads(raw)
    try:
        assert req('/api/projects')[0] == 401
        token = server.app.setup_file.read_text()
        assert req('/api/setup', 'POST', {'email':'a07@local.test','password':'test-only-password-12345','setup_token':token})[0] == 200
        status, login = req('/api/login', 'POST', {'email':'a07@local.test','password':'test-only-password-12345'})
        assert status == 200
        csrf = login['csrf']
        assert req('/api/engines')[0] == 200
        status, project = req('/api/projects', 'POST', {'name':'HTTP A07 circuit','family':'transmon'})
        assert status == 201
        pid, old_head = project['id'], project['head']
        model = project['model']
        model['schematic']['elements'].append({'id':'C1','type':'Capacitor','a':'q','b':'gnd','value':1,'unit':'fF'})
        model['schematic']['nodes'] = ['q','gnd']
        model['studies'].append({'id':'sqdmetal_palace_primary','engine':'sqdmetal_palace','kind':'eigenmode','inputs':{'source':'project.layout','mode':'eigenmode'}})
        assert req(f'/api/projects/{pid}/commit', 'POST', {'expected_revision':old_head,'model':model})[0] == 200
        assert req(f'/api/projects/{pid}/commit', 'POST', {'expected_revision':old_head,'model':model})[0] == 409
        current = req(f'/api/projects/{pid}')[1]
        new_head = current['head']
        assert new_head != old_head
        assert current['stages']['schematic'] == 'draft_saved'
        assert current['stages']['em'] == 'draft_saved'  # request presence != EM science
        assert current['stages']['results'] == 'not_started'
        assert req(f'/api/projects/{pid}/revisions/{old_head}')[1]['model']['schematic']['elements'] == []
        status, run = req(f'/api/projects/{pid}/runs', 'POST', {'revision':new_head,'study_id':'sqdmetal_palace_primary'})
        assert status == 202
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            runs = req(f'/api/projects/{pid}/runs')[1]['runs']
            state = next(r['state'] for r in runs if r['id'] == run['run_id'])
            if state not in ('queued','running'):
                break
            time.sleep(.15)
        assert state == 'failed', f'unexpected native state: {state}'
        assert req(f'/api/projects/{pid}/runs/{run["run_id"]}/result')[0] == 404
        code, data = req(f'/api/projects/{pid}/runs/{run["run_id"]}/download', binary=True)
        assert code == 200
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert 'output/FAILURE.json' in z.namelist()
            assert 'engine.log' in z.namelist()
            assert 'output/RESULT_MANIFEST.json' not in z.namelist()
            failure = json.loads(z.read('output/FAILURE.json'))
            assert failure['status'] == 'failed'
            print('ACTUAL NATIVE BLOCKED WORKER:', failure['error'])
        assert req(f'/api/projects/{pid}')[1]['stages']['results'] == 'not_started'
        assert req('/api/logout', 'POST', {})[0] == 200
        assert req(f'/api/projects/{pid}')[0] == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
