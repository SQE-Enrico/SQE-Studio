#!/usr/bin/env python3
"""Real Chromium/Playwright local HTTP smoke of installed SQE wheel UI.

Requires separately installed Playwright and Chromium test runner. Browser
acceptance here is Linux-host only unless the same script is run on Windows.
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--installed-python',required=True)
    parser.add_argument('--chromium', default='', help='Optional browser executable; default is Playwright Chromium or an installed browser')
    args=parser.parse_args()
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='sqe-a08-real-browser-') as td:
        data=Path(td)/'data';base=f'http://127.0.0.1:{port}'
        p=subprocess.Popen([args.installed_python,'-m','sqe_studio.server','--data',str(data),'--port',str(port)],
                           cwd=td,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if p.poll() is not None:raise RuntimeError('Service process exited')
                try:
                    with urllib.request.urlopen(base+'/api/status',timeout=1) as r:
                        if json.loads(r.read())['setup_required']:break
                except (OSError,ValueError):time.sleep(.1)
            else:raise RuntimeError('Service not ready')
            token=(data/'setup.token').read_text(encoding='ascii')
            with sync_playwright() as playwright:
                browser_path = args.chromium or next((shutil.which(name) for name in
                    ('chromium', 'chromium-browser', 'google-chrome', 'msedge', 'chrome') if shutil.which(name)), None)
                try:
                    options = {'headless': True, 'args': ['--no-sandbox']}
                    if browser_path: options['executable_path'] = browser_path
                    browser=playwright.chromium.launch(**options)
                except PlaywrightError as exc:
                    raise SystemExit('BROWSER_UNAVAILABLE: browser could not start: ' + str(exc)[:500])
                page=browser.new_page(viewport={'width':1440,'height':900})
                try:
                    failures=[]
                    page.on('pageerror',lambda error:failures.append(str(error)))
                    try:
                        page.goto(base,wait_until='networkidle',timeout=15000)
                    except PlaywrightError as exc:
                        if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc) or 'ERR_CONNECTION_REFUSED' in str(exc):
                            raise SystemExit('BROWSER_UNAVAILABLE: local browser navigation restricted: '+str(exc)[:500])
                        raise
                    page.locator('#authTitle').get_by_text('Create administrator').wait_for()
                    page.locator('#email').fill('ui@example.invalid')
                    page.locator('#password').fill('BrowserTestPassword__')
                    page.locator('#setupToken').fill(token)
                    page.locator('#authSubmit').click()
                    page.locator('#newProjectName').wait_for(timeout=10000)
                    page.locator('#newProjectName').fill('Installed Browser Project')
                    page.locator('#newProjectFamily').select_option('transmon')
                    page.locator('#confirmNew').click()
                    page.locator('#currentProjectName').get_by_text('Installed Browser Project').wait_for(timeout=10000)
                    assert page.locator('#stages button').count()==7
                    page.locator('#enginesButton').click()
                    page.locator('#dialogTitle').get_by_text('Native engine health').wait_for()
                    assert page.get_by_text('JosephsonCircuits.jl').count()>=1
                    page.locator('#closeDialog').click()
                    page.locator('#signOutButton').click()
                    page.locator('#auth').wait_for(state='visible')
                    if failures:raise RuntimeError('Browser JavaScript errors: '+str(failures))
                    print('PASS: real headless Chromium over local HTTP, installed UI assets, setup, login, project, 7-stage navigation, engine health and logout.',flush=True)
                    print('No native solver executed; browser exercised only installed UX.',flush=True)
                finally:browser.close()
        finally:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)

if __name__=='__main__':main()
