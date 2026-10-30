"""Adversarial local-HTTP tests. No fixture is a native solver qualification."""
import hashlib
import http.client
import http.cookiejar
import json
import os
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import pytest
from sqe_studio.server import make_server
from sqe_studio.store import Store

@pytest.fixture
def running(tmp_path):
    h=make_server(tmp_path/'private',0)
    t=threading.Thread(target=h.serve_forever,daemon=True)
    t.start()
    yield h
    h.shutdown();h.server_close();t.join(timeout=5)

class Client:
    def __init__(self,server):
        self.h=server
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def req(self,path,method='GET',body=None,headers=None):
        headers=dict(headers or {})
        if body is not None:
            headers.setdefault('Content-Type','application/json')
            body=json.dumps(body).encode()
        url=f'http://127.0.0.1:{self.h.server_port}{path}'
        req=urllib.request.Request(url,method=method,headers=headers,data=body)
        try:resp=self.opener.open(req,timeout=5)
        except urllib.error.HTTPError as exc:resp=exc
        with resp:
            data=resp.read()
            return resp.status, json.loads(data) if resp.headers.get('Content-Type','').startswith('application/json') else data,resp.headers
    def configured(self,email='me@example.test',password='ValidPassword_123'):
        token=self.h.app.setup_file.read_text()
        assert self.req('/api/setup','POST',{'setup_token':token,'email':email,'password':password})[0]==200
        code,resp,headers=self.req('/api/login','POST',{'email':email,'password':password})
        assert code==200
        return resp['csrf']

def test_default_bind_local_only_and_security_headers(running):
    h=running
    assert h.server_address[0]=='127.0.0.1'
    c=Client(h)
    status,obj,headers=c.req('/api/status')
    assert (status,obj['local_only'],obj['service'])==(200,True,'ready')
    assert headers['X-Frame-Options']=='DENY'
    assert 'frame-ancestors' in headers['Content-Security-Policy']
    assert headers['Cache-Control']=='no-store'
    for filename in ('index.html','app.js','style.css'):
        status,body,headers=c.req('/'+filename)
        assert status==200 and len(body)>30
        assert headers['X-Content-Type-Options']=='nosniff'
    assert c.req('/api/engines')[0]==401

def test_attack_headers_and_json_caps(running):
    h=running;c=Client(h)
    def raw(headers,body=b'',path='/api/status',method='GET'):
        con=http.client.HTTPConnection('127.0.0.1',h.server_port,timeout=4)
        con.putrequest(method,path,skip_host=True)
        for name,value in headers:con.putheader(name,value)
        con.endheaders(body)
        # A hardened server may send 400/403 and close as soon as it sees
        # a malformed header. A late client half-close can then raise EPIPE
        # or ENOTCONN; keep checking the *actual HTTP status*, never infer PASS.
        try:
            con.sock.shutdown(socket.SHUT_WR)
        except OSError as exc:
            import errno
            if exc.errno not in (errno.EPIPE, errno.ENOTCONN, errno.ECONNRESET):
                raise
        response=con.getresponse();result=response.status;response.read();con.close()
        return result
    host=('Host',f'127.0.0.1:{h.server_port}')
    assert raw([('Host','evil.example')])==403
    assert raw([host,('Host','evil.example')])==403
    assert raw([host,('Origin','null')],b'{}',method='POST',path='/api/login')==403
    assert raw([host,('Sec-Fetch-Site','cross-site')],b'{}',method='POST',path='/api/login')==403
    assert raw([host,('Transfer-Encoding','chunked')],b'0\r\n\r\n',method='POST',path='/api/login')==400
    assert raw([host,('Content-Type','application/json'),('Content-Length','262145')],method='POST',path='/api/login')==413
    assert raw([host,('Content-Type','application/json'),('Content-Length','2'),('Content-Length','2')],b'{}',method='POST',path='/api/login')==400
    assert raw([host,('Content-Type','application/json'),('Content-Length','3')],b'{',method='POST',path='/api/login')==400
    assert raw([host,('Content-Type','application/json'),('Content-Length','9')],b'{"v":NaN}',method='POST',path='/api/login')==400
    assert c.req('/api/status?session=private_value')[0]==200

def assert_transiently_aborted_rejection(request_status, unchanged, attempts=3):
    """Require a real 403 despite transient Windows client-side socket aborts.

    Never treat a connection abort as an accepted security rejection. Retry
    only this expected-to-be-denied operation, confirm no state mutation after
    every attempt, and fail closed if no HTTP response can be observed.
    """
    for _ in range(attempts):
        try:
            status = request_status()
        except ConnectionAbortedError:
            assert unchanged(), 'Forbidden request mutated state before disconnect'
            continue
        assert status == 403
        assert unchanged(), 'Forbidden request mutated state'
        return
    pytest.fail('Unable to observe HTTP 403 after repeated connection aborts')


def test_transient_abort_never_counts_as_a_security_pass():
    calls = iter([ConnectionAbortedError('Windows 10053'), 403])
    def request():
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item
    assert_transiently_aborted_rejection(request, lambda: True)
    with pytest.raises(BaseException, match='Unable to observe HTTP 403'):
        assert_transiently_aborted_rejection(
            lambda: (_ for _ in ()).throw(ConnectionAbortedError('Windows 10053')),
            lambda: True, attempts=2)
    with pytest.raises(AssertionError):
        assert_transiently_aborted_rejection(lambda: 200, lambda: True)
    with pytest.raises(AssertionError, match='mutated state'):
        assert_transiently_aborted_rejection(lambda: 403, lambda: False)


def test_login_cookie_csrf_rotation_and_throttle(running):
    h=running;c=Client(h);csrf=c.configured()
    assert not h.app.setup_file.exists()
    cookie=next(iter(c.jar))
    assert cookie.has_nonstandard_attr('HttpOnly') and cookie.get_nonstandard_attr('SameSite')=='Strict'
    assert cookie.path=='/'
    assert c.req('/api/projects','POST',{'name':'Test','family':'transmon'})[0]==403
    assert c.req('/api/projects','POST',{'name':'Test','family':'transmon'}, {'X-CSRF-Token':csrf,'Origin':'http://attacker.invalid'})[0]==403
    user_id = h.app.store.session(next(iter(c.jar)).value)['user_id']
    assert_transiently_aborted_rejection(
        lambda: c.req('/api/projects','POST',{'name':'Test','family':'transmon'},
                      {'X-CSRF-Token':csrf,'Sec-Fetch-Site':'same-site'})[0],
        lambda: not h.app.store.list_projects(user_id))
    bad={'current_password':'bad_password','new_password':'AnotherValidPassword__'}
    assert c.req('/api/password','POST',bad,{'X-CSRF-Token':csrf})[0]==401
    assert c.req('/api/me')[0]==200
    good={'current_password':'ValidPassword_123','new_password':'AnotherValidPassword__'}
    assert c.req('/api/password','POST',good,{'X-CSRF-Token':csrf})[0]==200
    assert c.req('/api/me')[0]==401
    assert c.req('/api/login','POST',{'email':'me@example.test','password':'ValidPassword_123'})[0]==401
    assert c.req('/api/login','POST',{'email':'me@example.test','password':'AnotherValidPassword__'})[0]==200
    assert c.req('/api/logout','POST',{}, {'X-CSRF-Token':c.req('/api/me')[1]['csrf']})[0]==200
    assert c.req('/api/me')[0]==401
    for _ in range(12):assert c.req('/api/login','POST',{'email':'missing@example.test','password':'WrongPassword123'})[0]==401
    assert c.req('/api/login','POST',{'email':'me@example.test','password':'AnotherValidPassword__'})[0]==429

def test_store_legacy_hash_upgrade_and_parallel_cas(tmp_path):
    s=Store(tmp_path/'store')
    s.setup('legacy@example.test','CorrectOldPassword')
    with s.conn() as db:
        row=db.execute('SELECT id,salt FROM accounts').fetchone()
        sha=hashlib.pbkdf2_hmac('sha256',b'CorrectOldPassword',bytes.fromhex(row['salt']),250_000).hex()
        db.execute('UPDATE accounts SET password_hash=? WHERE id=?',(sha,row['id']))
        db.commit()
    assert s.login('legacy@example.test','CorrectOldPassword')
    with s.conn() as db:
        assert db.execute('SELECT password_hash FROM accounts').fetchone()[0].startswith('pbkdf2_sha256$600000$')
    p=s.create(row['id'],'Parallel','transmon')
    from concurrent.futures import ThreadPoolExecutor
    def commit(_):return s.commit(row['id'],p['id'],p['head'],p['model'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: attempt(commit,_),range(2)))
    assert len([r for r in results if isinstance(r,str)])==1
    assert len([r for r in results if isinstance(r,Exception)])==1
    assert len(s.revisions(row['id'],p['id']))==2

def attempt(fn,arg):
    try:return fn(arg)
    except Exception as exc:return exc

def test_acl_and_run_directory_tamper(running,tmp_path):
    h=running;s=h.app.store;c=Client(h);csrf=c.configured()
    _,p,_=c.req('/api/projects','POST',{'name':'First','family':'transmon'},{'X-CSRF-Token':csrf})
    uid=s.session(next(iter(c.jar)).value)['user_id']
    # A second user is created using the same DB schema as an ACL adversary;
    # no second administrator setup endpoint is introduced in production.
    with s.conn() as db:
        db.execute('INSERT INTO accounts VALUES(?,?,?,?)',('other','other@example.test','00'*16,s._key('OtherPassword123','00'*16)))
        db.commit()
    assert s.list_projects('other')==[]
    from sqe_studio.store import NotFound
    with pytest.raises(NotFound):s.project('other',p['id'])
    with pytest.raises(NotFound):s.run('other',p['id'],'0'*32)
    run_id='a'*32
    folder=s.root/'native-runs'/p['id']/run_id
    folder.mkdir(parents=True)
    s.put_run(uid,p['id'],p['head'],'study_fixture','scqubits',folder)
    s.set_run(run_id,'completed')
    (folder/'output').mkdir()
    (folder/'output'/'RESULT_MANIFEST.json').write_text(json.dumps({'schema':'sqe.artifact.v1','revision_id':'different','project_digest':'wrong','engine':'scqubits','study_id':'study_fixture'}))
    assert c.req(f'/api/projects/{p["id"]}/runs/{run_id}/result')[0]==409
    (folder/'output'/'RESULT_MANIFEST.json').unlink()
    outside=tmp_path/'outside.json';outside.write_text('{"secret":1}')
    try:
        (folder/'output'/'RESULT_MANIFEST.json').symlink_to(outside)
        assert c.req(f'/api/projects/{p["id"]}/runs/{run_id}/result')[0]==404
    except (OSError,NotImplementedError):pytest.skip('No symlink permission on this host')


def test_setup_token_file_symlink_rejected(tmp_path):
    data=tmp_path/'data';data.mkdir()
    secret=tmp_path/'secret';secret.write_text('external secret')
    try:(data/'setup.token').symlink_to(secret)
    except (OSError,NotImplementedError):pytest.skip('No symlink permission')
    with pytest.raises(ValueError,match='Unsafe first-run'):make_server(data,0)
    assert secret.read_text()=='external secret'
