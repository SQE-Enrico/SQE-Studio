"""Actual production browser behavior, when local browser policy permits loopback."""
from __future__ import annotations
import re
import shutil
import threading
import pytest


def test_transmon_editor_real_browser_authenticated_revision_and_history(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    from sqe_studio.server import make_server
    server = make_server(tmp_path/'browser-m2', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            except playwright.Error as err:
                pytest.skip('Host browser unavailable: '+str(err).splitlines()[0][:160])
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda err:errors.append(str(err)))
            try:
                try:
                    response=page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
                except playwright.Error as err:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(err):
                        pytest.skip('Managed Chromium URLBlocklist disallows local HTTP')
                    raise
                csp=response.headers.get('content-security-policy','')
                assert "script-src 'self'" in csp and "'unsafe-eval'" not in csp
                page.locator('#email').fill('m2browser@example.invalid')
                page.locator('#password').fill('browser-test-password-long')
                page.locator('#setupToken').fill(server.app.setup_file.read_text())
                page.locator('#authSubmit').click()
                page.locator('#confirmNew').wait_for()
                page.locator('#newProjectName').fill('Transmon UI M2')
                page.locator('#newProjectFamily').select_option('transmon')
                page.locator('#confirmNew').click()
                page.locator('#overlay').wait_for(state='hidden')
                page.locator('#stages [data-step="3"]').click()
                # A test fixture populated through the ordinary production model
                # editor, then saved by the real revision button. No fixture solver.
                page.evaluate('''() => {
                  const study=blankEMStudy();study.id='CAP_STUDY';study.kind='capacitance';
                  study.inputs.em.ports=['QA','QB','Guard','Return'].map((component,i)=>({
                   index:i+1,kind:'conductor',component,native_attributes:[i+40]}));
                  activeModel().studies.push(study);markDirty();render();
                }''')
                page.locator('#saveButton').click()
                page.locator('#saveButton').filter(has_text='Save revision').wait_for()
                head_before=page.evaluate('project.head')
                assert page.locator('#transmonState').inner_text().startswith('BLOCKED')
                page.locator('#transmonStudy').select_option('CAP_STUDY')
                page.locator('#transmonIslandA').select_option('QA')
                page.locator('#transmonIslandB').select_option('QB')
                page.locator('[data-transmon-terminal="0"]').select_option('fixed_zero')
                page.locator('[data-transmon-terminal="1"]').select_option('floating_zero_charge')
                page.locator('#transmonConfiguration').select_option('TWO_ISLAND_CHARGE_TRANSFER')
                page.locator('#transmonJunctionConfirm').check()
                assert 'READY_TO_SAVE' in page.locator('#transmonState').inner_text()
                page.locator('#commitTransmonSelection').click()
                page.wait_for_function('(oldHead) => project.head !== oldHead',arg=head_before)
                saved=page.evaluate('''async()=>{
                 const p=await(await fetch('/api/projects')).json();
                 const id=p.projects[0].id;
                 const detail=await(await fetch(`/api/projects/${id}`)).json();
                 const old=await(await fetch(`/api/projects/${id}/revisions/${detail.parent}`)).json();
                 return {detail,old};
                }''')
                assert saved['detail']['model']['intent']['transmon_capacitance_selection']['island_a']=='QA'
                assert saved['detail']['model']['intent']['transmon_capacitance_selection']['other_terminal_policy']=={
                    'fixed_zero':['Guard'],'floating_zero_charge':['Return']}
                assert saved['old']['model']['intent'].get('transmon_capacitance_selection') is None
                page.locator('#stages [data-step="5"]').click()
                assert 'Transmon revision lineage' in page.locator('#workspaceBody').inner_text()
                assert 'NUMERICAL_SCREEN_ONLY' in page.locator('#workspaceBody').inner_text()
                assert not errors,errors
                print('M2_BROWSER_PASS real DOM/CSP/CSRF commit/readback/old revision and Results distinction')
            finally:
                browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
