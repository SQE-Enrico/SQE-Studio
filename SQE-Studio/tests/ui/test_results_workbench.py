"""A14 browser/API contract: one authenticated EDA Results workspace, no fabricated science.

The injected job has deliberately invalid *test-only* evidence. It must never be
rendered as native physical data; this is not a native solver qualification.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'src' / 'sqe_studio' / 'web'


def test_scientific_review_renderer_is_read_only_and_escapes_untrusted_metadata():
    """Node exercises the actual production JS renderer, not a duplicate test UI."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for direct UI renderer check')
    script = r'''
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
assert.match(source, /start\(\);\s*$/);
const context = vm.createContext({});
vm.runInContext(source.replace(/start\(\);\s*$/, ''), context);
vm.runInContext("project = {head: 'current-revision'}", context);
const manifest = {schema:'sqe.artifact.v1', fabrication_status:'HOLD',
  scientific_status:'review_required', engine:'sqdmetal_palace'};
const em = {schema:'sqe.em-native-results-screen.v1', mode_identity:'UNRESOLVED',
  mesh_convergence:'NOT_ESTABLISHED', em_to_hamiltonian:'BLOCKED',
  field_acquisition:{status:'NO_NATIVE_COMPLEX_FIELD_EXPORT',artifact_count:0,
    common_coordinate_domain_verified:false,complex_vector_normalization_verified:false,
    artifact_names:[]},modes:[],limitations:['<img src=x onerror=alert(1)>']};
const review = vm.runInContext('scientificReview',context)(manifest,
  {revision_id:'previous-revision'}, {em_evidence:em});
assert.match(review, /Historical revision/);
assert.match(review, /SHA-256 checked/);
assert.match(review, /UNRESOLVED/);
assert.match(review, /NOT_ESTABLISHED/);
assert.match(review, /BLOCKED/);
assert.match(review, /HOLD/);
assert.equal((review.match(/class="passed"/g)||[]).length, 1); // only integrity may pass
const observation = vm.runInContext('nativeEMEvidenceView',context)(em);
assert.match(observation, /&lt;img/);
assert.doesNotMatch(observation, /<img/);
assert.match(observation, /NOT VERIFIED/);
assert.throws(()=>vm.runInContext('scientificReview',context)(
  {...manifest,fabrication_status:'APPROVED'}, {revision_id:'current-revision'},{}),
  /Fabrication status failed closed/);
const rows = vm.runInContext('runRows',context)([
  {id:'a'.repeat(32),state:'completed',revision_id:'old-revision',
   engine:'scqubits',study_id:'<svg onload=alert(1)>',is_sweep:false}]);
assert.match(rows, /Completed · inspection required/);
assert.match(rows, /historical/);
assert.match(rows, /&lt;svg/);
assert.doesNotMatch(rows, /<svg/);
console.log('JS_RENDERER_PASS fail-closed scientific gates, provenance, output escaping');
'''
    done = subprocess.run([node, '-e', script, str(WEB / 'app.js')],
                          capture_output=True, text=True, timeout=15)
    assert done.returncode == 0, (done.stdout, done.stderr)
    print(done.stdout.strip())


@pytest.fixture
def browser_server(tmp_path):
    from sqe_studio.server import make_server
    server = make_server(tmp_path / 'workspace', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_authenticated_browser_job_filter_and_tampered_result_fail_closed(browser_server):
    playwright = pytest.importorskip('playwright.sync_api')
    expect = playwright.expect
    server, url = browser_server
    with playwright.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        except playwright.Error as error:
            pytest.skip('Chromium runtime unavailable: ' + str(error).splitlines()[0][:150])
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        errors = []
        network = []  # API method / endpoint / HTTP status only; never credentials or URL query data.
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: network.append((response.request.method,
            response.url.split('?')[0].rsplit('/', 1)[-1], response.status))
            if '/api/' in response.url else None)
        try:
            landing = page.goto(url, wait_until='networkidle')
        except playwright.Error as error:
            if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(error):
                browser.close()
                pytest.skip('Managed Chromium URLBlocklist disallows local HTTP on this host')
            raise
        # CSP is the production security boundary, not a test-only relaxed policy.
        csp = landing.headers.get('content-security-policy', '')
        assert "script-src 'self'" in csp, csp
        assert 'unsafe-eval' not in csp and 'unsafe-inline' not in csp, csp
        # The real service remains authenticated; no custom Results test endpoint exists.
        status = page.evaluate('async () => (await fetch("/api/projects")).status')
        assert status == 401
        page.locator('#email').fill('a14@test.example')
        page.locator('#password').fill('a14-isolated-test-password')
        page.locator('#setupToken').fill(server.app.setup_file.read_text(encoding='ascii'))
        engine_aborts = []
        def disconnect_engines(route):
            engine_aborts.append(route.request.method)
            route.abort()
        page.route('**/api/engines', disconnect_engines)
        page.locator('#authSubmit').click()
        page.locator('#confirmNew').wait_for(state='visible')  # authenticated initial load complete
        page.locator('#newProjectName').fill('A14 UI verification')
        # Engine discovery aborted during authentication; revision readback
        # must not depend on that optional call.
        assert engine_aborts and all(method == 'GET' for method in engine_aborts)
        page.locator('#confirmNew').click()
        # Overlay disappearance is not a revision-readiness barrier. Require a real
        # server revision in the UI, then check it against two authenticated reads.
        expect(page.locator('#revisionLabel')).to_have_text(re.compile(r'^REV [0-9a-f]{8}$'))
        page.locator('#overlay').wait_for(state='hidden')
        persisted = page.evaluate('''async () => {
            const listing = await fetch('/api/projects');
            const projects = (await listing.json()).projects;
            const detail = await fetch(`/api/projects/${projects[0].id}`);
            return {listingStatus:listing.status, detailStatus:detail.status,
                    listingHead:projects[0].head, detail:await detail.json()};
        }''')
        assert persisted['listingStatus'] == persisted['detailStatus'] == 200
        assert persisted['detail']['head'] == persisted['listingHead']
        assert re.fullmatch('[a-f0-9]{64}', persisted['detail']['revision_digest'])
        assert page.locator('#revisionLabel').inner_text() == 'REV '+persisted['listingHead'][:8]
        assert any(method=='POST' and endpoint=='projects' and code==201
                   for method,endpoint,code in network)
        print('BROWSER_POST_CREATE_REVISION_CONFIRMED POST 201 / GET 200 / UI head matches persisted SHA-256')
        # B10: normal authenticated design iteration must create a new saved
        # revision; numerical results and previous head are not silently reused.
        first_head = persisted['listingHead']
        page.locator('#targetName').fill('a14_revision_target')
        page.locator('#targetValue').fill('5.75')
        page.locator('#addTarget').click()
        assert 'Unsaved draft' in page.locator('#stageBadge').inner_text()
        page.locator('#saveButton').click()
        expect(page.locator('#revisionLabel')).not_to_have_text('REV ' + first_head[:8])
        revisions = page.evaluate('''async () => {
          const list = (await (await fetch('/api/projects')).json()).projects;
          const detail = await (await fetch(`/api/projects/${list[0].id}`)).json();
          const history = await fetch(`/api/projects/${list[0].id}/revisions`);
          return {head:list[0].head,detail,historyStatus:history.status,
                  history:(await history.json()).revisions};
        }''')
        assert revisions['head'] != first_head
        assert revisions['head'] == revisions['detail']['head']
        assert re.fullmatch('[a-f0-9]{64}', revisions['detail']['revision_digest'])
        assert revisions['historyStatus'] == 200
        assert {item['id'] for item in revisions['history']} >= {first_head, revisions['head']}
        assert page.locator('#revisionLabel').inner_text() == 'REV ' + revisions['head'][:8]
        print('BROWSER_B10_AUTHENTIC_REVISION_ITERATION UI save / server history / new digest confirmed')
        page.locator('#stages [data-step="5"]').click()
        assert page.locator('#pageTitle').inner_text() == 'Results'
        assert page.locator('#runMetrics .metric').count() == 3
        assert 'No native job history' in page.locator('#runList').inner_text()
        assert 'scientifically accepted result' in page.locator('#workspaceBody').inner_text()
        # Authenticated history disconnects are not zero verified runs.
        page.route('**/api/projects/*/runs', lambda route: route.abort())
        page.locator('#refreshJobs').click()
        expect(page.locator('#runList')).to_contain_text('Job history unavailable')
        expect(page.locator('#runMetrics')).to_contain_text('unavailable')
        expect(page.locator('#compareSection')).to_contain_text('Job history is unavailable')
        page.unroute('**/api/projects/*/runs')
        page.locator('#refreshJobs').click()
        expect(page.locator('#runList')).to_contain_text('No native job history')
        page.locator('#workspaceBody .design-cases summary').first.click()
        assert 'EM' in page.locator('#workspaceBody .design-cases').first.inner_text()
        assert 'Review gate' in page.locator('#workspaceBody .design-cases').first.inner_text()
        # Inject only failed and tampered metadata into the isolated test store;
        # no native solution or physics value is invented.
        project = server.app.store.list_projects(server.app.store.conn().execute(
            'SELECT owner FROM projects LIMIT 1').fetchone()[0])[0]
        pid, head = project['id'], project['head']
        owner = server.app.store.conn().execute(
            'SELECT owner FROM projects WHERE id=?', (pid,)).fetchone()[0]
        for run_id, state in [('1'*32, 'failed'), ('2'*32, 'completed'), ('4'*32, 'completed')]:
            folder = server.app.store.root / 'native-runs' / pid / run_id
            (folder/'output').mkdir(parents=True)
            server.app.store.put_run(owner,pid,head,'T1','scqubits',folder)
            server.app.store.set_run(run_id,state)
            if state == 'completed':
                (folder/'output'/'RESULT_MANIFEST.json').write_text(json.dumps({
                    'schema':'sqe.artifact.v1','engine':'scqubits','study_id':'T1',
                    'revision_id':head,'project_digest':'0'*64,'artifacts':[]}),
                    encoding='utf-8')
        page.locator('#refreshJobs').click()
        expect(page.locator('#runList tbody tr')).to_have_count(3)
        assert 'Completed · inspection required' in page.locator('#runList').inner_text()
        assert 'failed' in page.locator('#runList').inner_text()
        page.locator('#runFilter').select_option('attention')
        assert page.locator('#runList tbody tr').count() == 1
        assert 'failed' in page.locator('#runList').inner_text()
        page.locator('#runFilter').select_option('current')
        assert page.locator('#runList tbody tr').count() == 3
        # Even two apparently completed runs cannot bypass server-side
        # revision/content verification in the real Compare endpoint.
        expect(page.locator('#compareRuns')).to_be_visible()
        page.locator('#compareRuns').click()
        expect(page.locator('#toast')).to_contain_text('Comparison source failed content/revision verification')
        assert page.locator('#comparisonView').inner_text() == ''
        # Server must reject forged project digest and the viewer must fail closed.
        assert page.evaluate('''async pid => {
            const r=await fetch(`/api/projects/${pid}/runs/${'2'.repeat(32)}/result`);
            return r.status;
        }''', pid) == 409
        page.locator(f'[data-get-result="{"2"*32}"]').click()
        page.locator('#resultView [role="alert"]').wait_for()
        assert 'No scientific result has been displayed' in page.locator('#resultView').inner_text()
        assert page.locator('#resultView .scientific-review').count() == 0
        assert not errors, errors
        browser.close()



def test_served_production_csp_and_browser_wait_contract(browser_server):
    """Real HTTP security header and a static guard against eval-based waits.

    This does not claim full browser acceptance when Chromium is policy blocked.
    """
    import urllib.request
    _, url = browser_server
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + '/', timeout=10) as response:
        assert response.status == 200
        policy = response.headers.get('Content-Security-Policy', '')
    assert "script-src 'self'" in policy
    assert 'unsafe-eval' not in policy and 'unsafe-inline' not in policy
    # Keep the CSP regression guard even when browser execution is BLOCKED.
    test_source = Path(__file__).read_text(encoding='utf-8')
    assert 'wait_for_' + 'function(' not in test_source
    assert "expect(page.locator('#revisionLabel'))" in test_source
    assert "expect(page.locator('#runList tbody tr'))" in test_source
    print('HTTP_CSP_PASS production script-src self; browser waits use locator assertions')


def test_real_authenticated_http_rejects_tampered_native_result(browser_server):
    """Independent of browser policies: real authenticated service and 409 provenance gate."""
    import http.cookiejar
    import urllib.error
    import urllib.request

    server, base = browser_server
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                         urllib.request.ProxyHandler({}))

    def request(path, method='GET', body=None, csrf=None):
        headers = {}
        if body is not None: headers['Content-Type'] = 'application/json'
        if csrf: headers['X-CSRF-Token'] = csrf
        raw = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base+path, data=raw, method=method, headers=headers)
        try: response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error: response = error
        with response: return response.status, json.loads(response.read())

    assert request('/api/design/capabilities')[0] == 401
    token = server.app.setup_file.read_text(encoding='ascii')
    assert request('/api/setup', 'POST', {
        'email':'a14-http@test.example', 'password':'isolated-http-test-password',
        'setup_token':token})[0] == 200
    code, login = request('/api/login', 'POST', {
        'email':'a14-http@test.example', 'password':'isolated-http-test-password'})
    assert code == 200
    csrf=login['csrf']
    status,cap = request('/api/design/capabilities')
    assert status==200 and cap['schema']=='sqe.eda-capability-map.v1'
    assert any(x['id']=='em_to_hamiltonian' and x['status']=='blocked' for x in cap['edges'])
    status,created = request('/api/projects','POST',{'name':'Evidence HTTP', 'family':'generic'},csrf)
    assert status == 201
    pid,head = created['id'],created['head']
    assert len(pid) == len(head) == 32
    status,listing = request('/api/projects')
    assert status == 200 and any(x['id']==pid and x['head']==head for x in listing['projects'])
    status,persisted = request(f'/api/projects/{pid}')
    assert status == 200 and persisted['head'] == head
    assert len(persisted['revision_digest']) == 64
    print('HTTP_PERSISTENCE_PASS POST 201 / authenticated list 200 / detail 200, exact revision and digest')
    # B10 real authenticated server revision iteration: no UI-only state or
    # invented optimizer is needed to test persisted lineage and stale conflicts.
    changed = persisted['model']
    changed['intent']['notes'] = 'A14 revision iteration, not a native optimization result'
    code,commit = request(f'/api/projects/{pid}/commit','POST',
                          {'expected_revision':head,'model':changed},csrf)
    assert code == 200 and commit['revision'] != head
    new_head = commit['revision']
    status,new_detail = request(f'/api/projects/{pid}')
    assert status == 200 and new_detail['head'] == new_head
    assert new_detail['revision_digest'] != persisted['revision_digest']
    status,old_snapshot = request(f'/api/projects/{pid}/revisions/{head}')
    assert status == 200 and old_snapshot['revision'] == head
    status,revisions = request(f'/api/projects/{pid}/revisions')
    assert status == 200 and {r['id'] for r in revisions['revisions']} >= {head,new_head}
    assert request(f'/api/projects/{pid}/commit','POST',
                   {'expected_revision':head,'model':changed},csrf)[0] == 409
    print('HTTP_B10_ITERATION_PASS saved head and SHA changed, old snapshot immutable, stale commit 409')
    owner = server.app.store.conn().execute(
        'SELECT owner FROM projects WHERE id=?', (pid,)).fetchone()[0]
    run_id='3'*32
    folder=server.app.store.root/'native-runs'/pid/run_id
    (folder/'output').mkdir(parents=True)
    server.app.store.put_run(owner,pid,head,'S1','scqubits',folder)
    server.app.store.set_run(run_id,'completed')
    (folder/'output'/'RESULT_MANIFEST.json').write_text(json.dumps({
        'schema':'sqe.artifact.v1', 'revision_id':head,
        'engine':'scqubits','study_id':'S1', 'project_digest':'f'*64,
        'artifacts':[]}), encoding='utf-8')
    assert request(f'/api/projects/{pid}/runs/{run_id}/result')[0]==409
    assert request(f'/api/projects/{pid}/runs/{run_id}/download')[0]==409
    print('HTTP_REJECTION_PASS tampered project SHA-256 -> 409, no native result')
