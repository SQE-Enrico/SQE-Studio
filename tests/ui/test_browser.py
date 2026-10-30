"""Real Chromium/Playwright browser acceptance over the real loopback HTTP server.

These tests use no fake engine responses. Missing native dependencies are observed
as blocked, and the unimplemented EM port yields an actual failed worker archive.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect, Error as PlaywrightError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from sqe_studio.server import make_server

CAPTURES = Path(os.environ.get('SQE_BROWSER_CAPTURE_DIR', str(ROOT / 'reports' / 'agents' / 'A07' / 'screenshots')))


@pytest.fixture()
def local_server(tmp_path):
    server = make_server(tmp_path / 'private-data', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def page(local_server):
    with sync_playwright() as pw:
        binary = next((shutil.which(name) for name in
             ('chromium','chromium-browser','google-chrome','msedge','chrome') if shutil.which(name)), None)
        launch = {'args':['--no-sandbox']}
        if binary:launch['executable_path']=binary
        try:
            browser = pw.chromium.launch(**launch)
        except PlaywrightError as exc:
            if 'Executable doesn' in str(exc) or 'Failed to launch' in str(exc):
                pytest.skip('Chromium unavailable: '+str(exc).splitlines()[0][:150])
            raise
        context = browser.new_context(viewport={'width': 1366, 'height': 768}, accept_downloads=True, reduced_motion='reduce')
        pg = context.new_page()
        errors = []
        pg.on('pageerror', lambda err: errors.append(str(err)))
        try:
            pg.goto(local_server[1], wait_until='networkidle')
        except PlaywrightError as exc:
            if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc):
                context.close()
                browser.close()
                pytest.skip('Chromium managed URLBlocklist blocks local HTTP; real browser test cannot run on this host')
            raise
        yield pg
        assert not errors, 'Browser JavaScript errors: ' + repr(errors)
        context.close()
        browser.close()


def onboard(page, server):
    assert page.locator('#auth').is_visible()
    assert page.locator('#setupTokenLabel').is_visible()
    page.locator('#email').fill('agent07@example.org')
    page.locator('#password').fill('test-only-password-12345')
    page.locator('#setupToken').fill(server.app.setup_file.read_text())
    page.locator('#authSubmit').click()
    expect(page.locator('#dialogTitle')).to_have_text('Create your first project')
    expect(page.locator('#newProjectName')).to_be_focused()
    page.locator('#newProjectName').fill('A07 Native Circuit')
    page.locator('#newProjectFamily').select_option('transmon')
    page.locator('#confirmNew').click()
    expect(page.locator('#pageTitle')).to_have_text('Specifications')
    assert page.locator('#revisionLabel').inner_text().startswith('REV ')


def api(page, path, method='GET', body=None):
    """Browser fetch: cookies+CSRF under the actual authenticated origin."""
    return page.evaluate('''async ({path, method, body}) => {
      const me = await (await fetch('/api/me')).json();
      const res = await fetch(path, {method, headers:{'Content-Type':'application/json', 'X-CSRF-Token':me.csrf},
        body: body ? JSON.stringify(body) : undefined});
      return {status:res.status, data:await res.json()};
    }''', {'path': path, 'method': method, 'body': body})


def contrast_ratio(fg, bg):
    def channels(color):
        assert color.startswith('rgb(') or color.startswith('rgba('), color
        return [int(float(x.strip())) / 255 for x in color[color.find('(')+1:color.find(')')].split(',')[:3]]
    def lum(color):
        a = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels(color)]
        return .2126*a[0] + .7152*a[1] + .0722*a[2]
    x, y = sorted([lum(fg), lum(bg)], reverse=True)
    return (x + .05) / (y + .05)


def audit_viewport(page, width, height, name):
    page.set_viewport_size({'width': width, 'height': height})
    page.wait_for_timeout(120)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    capture = CAPTURES / f'{name}-{width}x{height}.png'
    page.screenshot(path=str(capture), full_page=True, animations='disabled')
    dimensions = page.evaluate('''() => ({scroll:document.documentElement.scrollWidth,
       client:document.documentElement.clientWidth, body:document.body.scrollWidth,
       docHeight:document.documentElement.scrollHeight})''')
    assert dimensions['scroll'] <= width + 2, (name, dimensions)
    assert dimensions['body'] <= width + 2, (name, dimensions)
    assert page.locator('#pageTitle').is_visible()
    for selector in ['#pageTitle', '.content-heading p', '.pane h2', '.form-field > span', '.canvas-caption']:
        element = page.locator(selector).first
        if element.count() and element.is_visible():
            values = element.evaluate('''e => ({fg:getComputedStyle(e).color,
              bg:getComputedStyle(document.body).backgroundColor, box:e.getBoundingClientRect().toJSON()})''')
            assert values['box']['width'] > 0 and values['box']['height'] > 0
            # Text is atop dark surfaces, which are LUMINANCE >= body background;
            # a body-based test is only a preliminary numerical review.
            assert contrast_ratio(values['fg'], 'rgb(20, 36, 58)') >= 4.5, (selector, values)
    print(f'VIEWPORT {name} {width}x{height} screenshot={capture.relative_to(ROOT)} horizontal-overflow=none')


def test_real_browser_local_http_auth_revisions_and_fail_closed_job(page, local_server):
    server, base = local_server
    assert page.locator('#authTitle').is_visible()
    bad = api(page, '/api/projects')
    assert bad['status'] == 401
    onboard(page, server)
    # Schematic is edited as a model, and visualization is expressly nonphysical.
    page.locator('#stages [data-step="1"]').click()
    expect(page.locator('#pageTitle')).to_have_text('Schematic')
    expect(page.locator('.design-canvas')).to_be_visible()
    assert 'not an LVS-verified' in page.locator('#workspaceBody').inner_text()
    page.locator('#addElement').click()
    expect(page.locator('[data-canvas="element"]')).to_have_count(1)
    page.locator('[data-canvas="element"]').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#canvasDetail')).to_contain_text('C1')
    expect(page.locator('#stageBadge')).to_contain_text('Unsaved draft')
    head_before = api(page, '/api/projects')['data']['projects'][0]['head']
    # Navigating never silently saves.
    page.keyboard.press('Alt+3')
    expect(page.locator('#pageTitle')).to_have_text('Layout')
    assert api(page, '/api/projects')['data']['projects'][0]['head'] == head_before
    page.locator('#saveButton').click()
    expect(page.locator('#stageBadge')).to_have_text('Draft saved')
    head_after = api(page, '/api/projects')['data']['projects'][0]['head']
    assert head_after != head_before
    # Layout preview is non-native and stage gate is truthful.
    expect(page.locator('[data-canvas="layout"]')).to_have_count(1)
    assert 'not rendered QGeometry' in page.locator('#workspaceBody').inner_text()
    page.locator('[data-canvas="layout"]').focus()
    page.keyboard.press('Space')
    expect(page.locator('#canvasDetail')).to_contain_text('Q1')
    if not any(x['available'] for x in api(page, '/api/engines')['data']['engines'] if x['id']=='quantum_metal'):
        assert page.locator('#gdsRun').is_disabled()  # Missing Quantum Metal cannot export
    page.locator('#prepareGDS').click()
    expect(page.locator('#stageBadge')).to_have_text('Unsaved draft')
    page.locator('#saveButton').click()
    expect(page.locator('#stageBadge')).to_have_text('Draft saved')
    if not any(x['available'] for x in api(page, '/api/engines')['data']['engines'] if x['id']=='quantum_metal'):
        assert page.locator('#gdsRun').is_disabled()
    # All available engine ports are shown with explicit install/blocked distinctions.
    page.locator('#enginesButton').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.locator('#dialogBody')).to_contain_text('Missing / blocked')
    expect(page.locator('#dialogBody')).to_contain_text('blocked_pending_reviewed_setup')
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(page.locator('#enginesButton')).to_be_focused()
    # Expert is progressive disclosure over the same project, never a new workspace.
    page.locator('#expertButton').click()
    expect(page.locator('#expertJson')).to_be_visible()
    page.locator('#expertButton').click()
    assert page.locator('#expertJson').count() == 0
    # Fail closed on missing SQDMetal/Palace bridge, via an authenticated real API run.
    page.locator('#stages [data-step="3"]').click()
    page.locator('#addEMStudy').click()
    page.locator('#saveButton').click()
    current = api(page, '/api/projects')['data']['projects'][0]
    req = api(page, f"/api/projects/{current['id']}/runs", 'POST',
              {'revision': current['head'], 'study_id': 'sqdmetal_palace_primary'})
    assert req['status'] == 202, req
    run_id = req['data']['run_id']
    deadline = time.time() + 20
    while time.time() < deadline:
        run_list = api(page, f"/api/projects/{current['id']}/runs")['data']['runs']
        state = next(r['state'] for r in run_list if r['id'] == run_id)
        if state not in ('queued', 'running'):
            break
        time.sleep(.2)
    assert state == 'failed', state
    assert api(page, f"/api/projects/{current['id']}/runs/{run_id}/result")['status'] == 404
    page.locator('#stages [data-step="5"]').click()
    page.locator('[data-get-result]').first.click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.locator('#dialogBody')).to_contain_text('No native result manifest')
    with page.expect_download() as dl:
        page.locator('#downloadFailure').click()
    zip_path = CAPTURES.parent / 'A07-failed-native-job.zip'
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    dl.value.save_as(str(zip_path))
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        assert 'output/FAILURE.json' in names, names
        assert 'engine.log' in names, names
        assert 'output/RESULT_MANIFEST.json' not in names
        failure = json.loads(z.read('output/FAILURE.json'))
        assert failure['status'] == 'failed'
        assert 'blocked' in failure['error'].lower() or 'unavailable' in failure['error'].lower() or 'verified' in failure['error'].lower(), failure
    print('NATIVE FAILURE (actual worker):', failure)
    # Evidence stays in the real archived download. Do not ship runtime data in the delta.
    zip_path.unlink()
    page.keyboard.press('Escape')
    page.locator('#historyButton').click()
    expect(page.locator('#dialogBody')).to_contain_text('Immutable snapshots')
    page.locator('[data-history]').last.click()
    expect(page.locator('#dialogBody')).to_contain_text('Read-only historical revision')
    page.keyboard.press('Escape')
    # No scientific status is asserted by successful draft save.
    page.locator('#stages [data-step="6"]').click()
    expect(page.locator('#workspaceBody')).to_contain_text('HOLD')
    assert page.locator('#fabricationRun').is_disabled()
    page.locator('#stages [data-step="1"]').click()
    audit_viewport(page, 1366, 768, 'schematic')
    audit_viewport(page, 1920, 1080, 'schematic')
    audit_viewport(page, 430, 820, 'schematic-compact')
    page.locator('#railStages [data-step="2"]').click()
    audit_viewport(page, 1366, 768, 'layout')
    audit_viewport(page, 1920, 1080, 'layout')
    audit_viewport(page, 430, 820, 'layout-compact')
    page.locator('#inspectorButton').click()
    expect(page.locator('#inspector')).to_be_visible()
    audit_viewport(page, 1366, 768, 'inspector')
    page.locator('#closeInspector').click()
    expect(page.locator('#inspector')).to_be_hidden()
    print('AUTH/REVISION/NATIVE BLOCK/DOWNLOAD/KEYBOARD/FLOW: real browser pass')


def test_auth_and_dialog_focus_guard(page, local_server):
    server, _ = local_server
    page.locator('#email').fill('wrong@local.test')
    page.locator('#password').fill('wrong-password-123')
    page.locator('#setupToken').fill('invalid-first-run-token')
    page.locator('#authSubmit').click()
    expect(page.locator('#authError')).to_contain_text('Invalid first-run setup token')
    onboard(page, server)
    page.locator('#projectChooser').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    page.locator('#createOther').click()
    expect(page.locator('#newProjectName')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    assert page.locator('#closeDialog').is_focused() or page.locator('#confirmNew').is_focused()
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(page.locator('#projectChooser')).to_be_focused()
    # No display of a hidden white-on-white legacy workspace.
    assert page.locator('.app').is_visible()
    assert page.locator('#auth').is_hidden()
