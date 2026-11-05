"""Production JS controller and real authenticated HTTP (fixtures, no native solver)."""
from __future__ import annotations
import http.cookiejar
import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_production_transmon_editor_controller_validation_xss_conflict():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node not installed: production JS controller check not run')
    result = subprocess.run([node, str(Path(__file__).with_name('transmon_m2_controller.cjs')),
                             str(ROOT / 'src/sqe_studio/web/app.js')],
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, (result.stdout, result.stderr)
    print(result.stdout.strip())


def test_real_authenticated_revision_commit_csrf_conflict_history_and_no_runs(tmp_path):
    from sqe_studio.server import make_server
    server = make_server(tmp_path / 'only-m2-fixture', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies),
                                          urllib.request.ProxyHandler({}))
    csrf = ''
    def request(path, method='GET', data=None, csrf_header=True):
        headers = {'Content-Type': 'application/json'} if data is not None else {}
        if method != 'GET' and csrf_header:
            headers['X-CSRF-Token'] = csrf
        req = urllib.request.Request(origin+path, method=method, headers=headers,
                                     data=json.dumps(data).encode() if data is not None else None)
        try:
            res = opener.open(req, timeout=8)
        except urllib.error.HTTPError as exc:
            res = exc
        with res:
            b = res.read()
            return res.status, json.loads(b) if b and 'json' in res.headers.get('Content-Type','') else b
    try:
        assert request('/api/projects')[0] == 401
        token = server.app.setup_file.read_text(encoding='ascii')
        assert request('/api/setup', 'POST', {'email':'m2-test@example.invalid', 'password':'long-test-password-only', 'setup_token':token})[0] == 200
        rc,auth = request('/api/login', 'POST', {'email':'m2-test@example.invalid','password':'long-test-password-only'})
        assert rc == 200
        csrf = auth['csrf']
        rc,created = request('/api/projects', 'POST', {'name':'M2 Fixture Project','family':'transmon'})
        assert rc == 201
        pid=created['id']; old=created['head']; model=created['model']
        model['intent']['targets'].append({'name':'f01','value':5.4,'unit':'GHz','tolerance':0.05})
        model['intent']['notes']='unchanged design intent'
        ports=[{'index':i,'kind':'conductor','component':c,'native_attributes':[i+20]}
               for i,c in enumerate(['Q_A','Q_B','Screen','Pad'],1)]
        model['studies']=[{'id':'M2_CAP','engine':'sqdmetal_palace','kind':'capacitance',
                           'inputs':{'em':{'ports':ports}}},
                          {'id':'INDEPENDENT','engine':'scqubits','kind':'spectrum',
                           'inputs':{'model':'Transmon','parameters':{'EJ':19,'EC':0.31},'source':'independent'}}]
        # Start with a saved validated input revision; only the next commit adds selection.
        rc,intermediate=request(f'/api/projects/{pid}/commit','POST',{'expected_revision':old,'model':model})
        assert rc==200
        before=intermediate['revision']
        saved_selection={
          'schema':'sqe.saved-transmon-capacitance-selection.v1',
          'study_id':'M2_CAP','island_a':'Q_A','island_b':'Q_B',
          'other_terminal_policy':{'fixed_zero':['Screen'],'floating_zero_charge':['Pad']},
          'configuration':'TWO_ISLAND_CHARGE_TRANSFER',
          'junction_capacitance_assumption':'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'}
        next_model=json.loads(json.dumps(model));next_model['intent']['transmon_capacitance_selection']=saved_selection
        endpoint=f'/api/projects/{pid}/commit'
        assert request(endpoint,'POST',{'expected_revision':before,'model':next_model},csrf_header=False)[0] == 403
        assert request(f'/api/projects/{pid}')[1]['head'] == before
        rc,result=request(endpoint,'POST',{'expected_revision':before,'model':next_model})
        assert rc==200
        new=result['revision']
        assert new!=before
        rc,current=request(f'/api/projects/{pid}')
        assert rc==200 and current['head']==new
        assert current['model']['intent']['transmon_capacitance_selection']==saved_selection
        assert current['model']['intent']['targets']==model['intent']['targets']
        assert current['model']['intent']['notes']==model['intent']['notes']
        assert current['model']['studies']==model['studies']
        assert current['model']['studies'][1]['inputs']['parameters']=={'EJ':19,'EC':0.31}
        assert request(endpoint,'POST',{'expected_revision':before,'model':next_model})[0]==409
        assert request(f'/api/projects/{pid}')[1]['head']==new
        code,history=request(f'/api/projects/{pid}/revisions')
        assert code==200 and len(history['revisions'])==3
        code,previous=request(f'/api/projects/{pid}/revisions/{before}')
        assert code==200
        assert previous['model']['intent'].get('transmon_capacitance_selection') is None
        code,oldest=request(f'/api/projects/{pid}/revisions/{old}')
        assert code==200 and not oldest['model']['studies']
        assert request(f'/api/projects/{pid}/runs')[1]['runs']==[]
        # Session invalidation: no unauthenticated access to saved model.
        assert request('/api/logout','POST',{})[0]==200
        assert request(f'/api/projects/{pid}')[0]==401
        print('M2_HTTP_PASS real POST/GET, CSRF 403, CAS 409, immutable historic revision, targets/studies preserved, no run, logout 401')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
