#!/usr/bin/env python3
"""Offline installed-wheel and local HTTP process smoke; no scientific outputs.

Run under the isolated *installed* environment, not with PYTHONPATH=src.
Exit nonzero if any required installed UX asset or service behavior is missing.
"""
from __future__ import annotations
import argparse
import hashlib
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from importlib import resources
from pathlib import Path

ASSETS=('index.html','app.js','style.css')

def get_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

def req(opener,url,path,data=None,csrf=None):
    headers={}
    if data is not None:headers['Content-Type']='application/json'
    if csrf:headers['X-CSRF-Token']=csrf
    r=urllib.request.Request(url+path,data=json.dumps(data).encode('utf-8') if data is not None else None,headers=headers)
    try:result=opener.open(r,timeout=3)
    except urllib.error.HTTPError as e:result=e
    with result:
        body=result.read()
        return result.status,json.loads(body) if result.headers.get('Content-Type','').startswith('application/json') else body

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--wheel',type=Path,required=True)
    args=p.parse_args()
    wheel=args.wheel.resolve()
    if not wheel.is_file() or not wheel.name.endswith('.whl'):
        raise RuntimeError('Verified wheel path is required')
    import sqe_studio
    pkg=Path(sqe_studio.__file__).resolve().parent
    print('Python executable:',sys.executable,flush=True)
    print('Python version:',sys.version.split()[0],flush=True)
    print('Installed package:',pkg,flush=True)
    if not pkg.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError('Imported from outside installed interpreter prefix')
    hashes={}
    with zipfile.ZipFile(wheel) as z:
        for a in ASSETS:
            matches=[n for n in z.namelist() if n==f'sqe_studio/web/{a}']
            if len(matches)!=1:raise RuntimeError('Missing or duplicate wheel asset: '+a)
            raw=z.read(matches[0]);installed=resources.files('sqe_studio').joinpath('web',a).read_bytes()
            if raw!=installed:raise RuntimeError('Wheel/install asset hash mismatch: '+a)
            hashes[a]=hashlib.sha256(raw).hexdigest()
            print('Asset SHA-256:',a,hashes[a],flush=True)
    with tempfile.TemporaryDirectory(prefix='sqe-a08-install-smoke-') as td:
        data=Path(td)/'data';port=get_port();base=f'http://127.0.0.1:{port}'
        process=subprocess.Popen([sys.executable,'-m','sqe_studio.server','--data',str(data),'--port',str(port)],
                                 cwd=td,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            jar=http.cookiejar.CookieJar()
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
            for attempt in range(100):
                if process.poll() is not None:raise RuntimeError('Independent service process exited unexpectedly')
                try:code,body=req(client,base,'/api/status');break
                except (urllib.error.URLError,TimeoutError):time.sleep(0.1)
            else:raise RuntimeError('Installed service failed to become healthy')
            if code!=200 or not body.get('setup_required') or body.get('local_only') is not True:
                raise RuntimeError('Unhealthy first-run service')
            for a in ASSETS:
                code,served=req(client,base,'/'+a)
                if code!=200 or hashlib.sha256(served).hexdigest()!=hashes[a]:
                    raise RuntimeError('HTTP asset does not match wheel: '+a)
            if req(client,base,'/api/me')[0]!=401:raise RuntimeError('Unauthenticated access')
            token=(data/'setup.token').read_text(encoding='ascii')
            assert req(client,base,'/api/setup',{'setup_token':token,'email':'smoke@example.invalid','password':'WheelSmokePassword_123'})[0]==200
            assert not (data/'setup.token').exists()
            code,session=req(client,base,'/api/login',{'email':'smoke@example.invalid','password':'WheelSmokePassword_123'})
            if code!=200 or not session.get('csrf'):raise RuntimeError('Installed login failed')
            if req(client,base,'/api/projects',{'name':'Denied','family':'transmon'})[0]!=403:
                raise RuntimeError('Missing installed CSRF protection')
            code,p=req(client,base,'/api/projects',{'name':'Offline Smoke','family':'transmon'},session['csrf'])
            if code!=201 or not p.get('head'):raise RuntimeError('Installed revision creation failed')
            if req(client,base,'/api/projects/'+p['id'])[0]!=200:raise RuntimeError('Installed project ACL failed')
            if req(client,base,'/api/logout',{},session['csrf'])[0]!=200:raise RuntimeError('Installed logout failed')
            if req(client,base,'/api/projects')[0]!=401:raise RuntimeError('Logout did not revoke session')
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',port))!=0:raise RuntimeError('Service terminated too early')
            print('PASS: independently started wheel service, real HTTP, wheel assets, setup/login, CSRF, revision, logout.',flush=True)
            print('Scientific engine execution: NOT TESTED; no synthetic outputs produced.',flush=True)
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('FAIL:',type(exc).__name__,str(exc),file=sys.stderr,flush=True)
        raise SystemExit(1)
