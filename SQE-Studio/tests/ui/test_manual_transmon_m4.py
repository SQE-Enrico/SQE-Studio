"""M4: production browser/controller and genuine read-only server boundary checks."""
from __future__ import annotations
from sqe_studio.web_assets import javascript_bundle
import http.cookiejar
import json
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_manual_transmon_production_controller():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node not installed; production controller unavailable')
    result=subprocess.run([node,str(Path(__file__).with_name('manual_transmon_m4_controller.cjs')),
                           str(ROOT/'src/sqe_studio/web/app.js')],capture_output=True,text=True,timeout=25)
    assert result.returncode==0,(result.stdout,result.stderr)
    print(result.stdout.strip())


def test_authenticated_http_read_only_and_stale_revision_no_study(tmp_path):
    """Only existing GET/commit flow is exercised: no invented preflight endpoint."""
    from sqe_studio.server import make_server
    server=make_server(tmp_path/'m4-http',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',data=None,with_csrf=True):
        headers={'Content-Type':'application/json'} if data is not None else {}
        if method!='GET' and with_csrf: headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(origin+path,method=method,headers=headers,
                                       data=json.dumps(data).encode() if data is not None else None)
        try:res=opener.open(request,timeout=8)
        except urllib.error.HTTPError as error:res=error
        with res:
            body=res.read()
            return res.status, json.loads(body) if 'json' in res.headers.get('Content-Type','') else body
    try:
        assert req('/api/projects')[0]==401
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'m4@example.invalid','password':'strong-password-not-real',
                                       'setup_token':token})[0]==200
        code,login=req('/api/login','POST',{'email':'m4@example.invalid','password':'strong-password-not-real'})
        assert code==200
        csrf=login['csrf']
        code,p=req('/api/projects','POST',{'name':'M4 isolation','family':'transmon'})
        assert code==201
        pid=p['id']; old=p['head']; original=p['model']
        code,readback=req(f'/api/projects/{pid}')
        assert code==200 and readback['head']==old
        assert readback['model']==original
        assert readback['model']['studies']==[]
        assert req(f'/api/projects/{pid}/runs')[1]['runs']==[]
        # Only a concurrent unrelated authorized writer can advance a revision.
        updated=json.loads(json.dumps(original));updated['intent']['notes']='other editor changed model'
        endpoint=f'/api/projects/{pid}/commit'
        assert req(endpoint,'POST',{'expected_revision':old,'model':updated},with_csrf=False)[0]==403
        assert req(f'/api/projects/{pid}')[1]['head']==old
        code,receipt=req(endpoint,'POST',{'expected_revision':old,'model':updated})
        assert code==200
        current=receipt['revision']
        assert current!=old
        assert req(endpoint,'POST',{'expected_revision':old,'model':updated})[0]==409
        code,new=req(f'/api/projects/{pid}')
        assert code==200 and new['head']==current
        assert new['model']['studies']==[]
        assert 'independent_transmon' not in json.dumps(new['model'])
        code,historical=req(f'/api/projects/{pid}/revisions/{old}')
        assert code==200 and historical['model']==original
        assert req(f'/api/projects/{pid}/runs')[1]['runs']==[]
        assert req('/api/logout','POST',{})[0]==200
        assert req(f'/api/projects/{pid}')[0]==401
        print('M4_HTTP_PASS 401/403/409, immutable historic revision, no invented writes, no studies or runs')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_manual_transmon_real_dom_when_browser_permits_loopback(tmp_path):
    playwright=pytest.importorskip('playwright.sync_api')
    from sqe_studio.server import make_server
    server=make_server(tmp_path/'m4-browser',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as pw:
            try:
                browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
            except playwright.Error as exc:
                pytest.skip(f'Chromium unavailable: {exc}')
            try:
                page=browser.new_page()
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                try:
                    response=page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded',timeout=15000)
                except playwright.Error as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc):
                        pytest.skip('Chromium environment blocks loopback HTTP (ERR_BLOCKED_BY_ADMINISTRATOR)')
                    raise
                if not response or response.status!=200:
                    pytest.skip(f'Chromium loopback prohibited: {response.status if response else "no response"}')
                page.locator('#email').fill('m4browser@example.invalid')
                page.locator('#password').fill('m4-browser-password-long')
                page.locator('#setupToken').fill(server.app.setup_file.read_text())
                page.locator('#authSubmit').click()
                page.locator('#confirmNew').wait_for()
                page.locator('#newProjectName').fill('M4 isolated Transmon UI')
                page.locator('#newProjectFamily').select_option('transmon')
                page.locator('#confirmNew').click()
                page.locator('#overlay').wait_for(state='hidden')
                page.locator('#stages [data-step="4"]').click()
                for key in ['EJ','EC','ng','ncut','levels']:
                    assert page.locator('#manualTransmon'+key).input_value()==''
                assert page.locator('#manualTransmonServerAction').is_disabled()
                assert 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION' in page.locator('#manualTransmonGate').inner_text()
                page.locator('#manualTransmonCheck').click()
                assert 'Confirm explicitly' in page.locator('#manualTransmonCheckResult').inner_text()
                for key,value in [('EJ','15'),('EC','0.25'),('ng','0'),('ncut','8'),('levels','4')]:
                    page.locator('#manualTransmon'+key).fill(value)
                page.locator('#manualTransmonAcknowledged').check()
                page.locator('#manualTransmonCheck').click()
                page.get_by_text('Local syntax checked against the current project head.',exact=False).wait_for()
                assert 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION' in page.locator('#manualTransmonGate').inner_text()
                assert page.locator('#manualTransmonServerAction').is_enabled()
                assert page.evaluate('activeModel().studies.length')==0
                page.locator('#manualTransmonEJ').fill('<img src=x onerror=alert(1)>')
                assert page.locator('#manualTransmonSummary').inner_text()==''
                assert page.locator('#manualTransmonEJ').input_value()=='<img src=x onerror=alert(1)>'
                assert page.locator('#manualTransmonEJ').count()==1
                page.locator('#manualTransmonReset').click()
                assert page.locator('#manualTransmonEJ').input_value()==''
                assert not page.locator('#manualTransmonAcknowledged').is_checked()
                page.locator('#stages [data-step="5"]').click()
                assert page.locator('#manualTransmonEJ').count()==0
                assert not errors,errors
                print('M4_BROWSER_PASS real DOM, accessibility labels, form/Results isolation, XSS text, no study, no save')
            finally:
                browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_manual_transmon_real_dom_offline_no_local_http():
    """Actual Chromium DOM/event/focus/XSS regression even if loopback HTTP is policy-blocked.

    This is a browser controller test, not an authenticated browser/server acceptance.
    """
    playwright=pytest.importorskip('playwright.sync_api')
    source=javascript_bundle((ROOT/'src/sqe_studio/web/app.js').parent).decode('utf-8')
    assert source.rstrip().endswith('start();')
    with playwright.sync_playwright() as pw:
        try:
            browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        try:
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.set_content('<!doctype html><html lang="en"><head><meta charset="utf-8"></head><body><main id="workspaceBody"></main></body></html>')
            page.add_script_tag(content=source[:source.rfind('start();')])
            page.evaluate("""() => {
              project={id:'a'.repeat(32),head:'b'.repeat(32),name:'browser DOM test',model:{family:'transmon',intent:{notes:'old'},studies:[{id:'pristine',engine:'scqubits',kind:'spectrum',inputs:{model:'Transmon',parameters:{EJ:900,EC:800}}}]}};
              step=4; render=()=>{document.getElementById('workspaceBody').innerHTML=independentTransmonEditor();wireIndependentTransmon()};
              api=async(path,method,body)=>{if(method||body||path!=='/api/projects/'+project.id)throw Error('Unexpected HTTP call');return {id:project.id,head:project.head}};
              render();
            }""")
            for key in ['EJ','EC','ng','ncut','levels']:
                loc=page.locator('#manualTransmon'+key)
                assert loc.input_value()==''
                assert loc.get_attribute('inputmode') in ('decimal','numeric')
                assert page.locator(f'label[for="manualTransmon{key}"]').count()==1
            assert page.locator('#manualTransmonServerAction').is_disabled()
            page.locator('#manualTransmonEJ').focus()
            page.keyboard.press('Tab')
            assert page.evaluate('document.activeElement.id')=='manualTransmonEC'
            assert page.locator('#manualTransmonGate').get_attribute('aria-live')=='polite'
            assert page.locator('#manualTransmonGate').inner_text()=='BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION'
            page.locator('#manualTransmonCheck').click()
            assert 'Confirm explicitly' in page.locator('#manualTransmonCheckResult').inner_text()
            for key,value in [('EJ','15'),('EC','0.2'),('ng','0'),('ncut','8'),('levels','4')]:
                page.locator('#manualTransmon'+key).fill(value)
            page.locator('#manualTransmonAcknowledged').check()
            page.locator('#manualTransmonCheck').click()
            page.wait_for_function('document.getElementById("manualTransmonCheckResult").textContent.includes("Local syntax checked")')
            assert page.locator('#manualTransmonServerAction').is_enabled()
            assert page.evaluate('project.model.studies[0].inputs.parameters.EJ')==900
            assert page.locator('#manualTransmonSummary').inner_text().startswith('Local syntax only')
            page.locator('#manualTransmonEJ').fill('<img src=x onerror=alert(1)>')
            assert page.locator('#manualTransmonSummary').inner_text()==''
            page.evaluate('render()')
            assert page.locator('#manualTransmonEJ').input_value()=='<img src=x onerror=alert(1)>'
            assert page.locator('#workspaceBody img').count()==0
            page.locator('#manualTransmonReset').click()
            assert page.locator('#manualTransmonEJ').input_value()==''
            assert not page.locator('#manualTransmonAcknowledged').is_checked()
            assert page.locator('#manualTransmonGate').inner_text()=='BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION'
            assert not errors,errors
            print('M4_OFFLINE_BROWSER_DOM_PASS real focus/input/labels/XSS/reset; fixture GET only, no backend qualification')
        finally:
            browser.close()
