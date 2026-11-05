"""Adversarial local-HTTP tests. No fixture is a native solver qualification."""
import hashlib
import importlib.util
import http.client
import http.cookiejar
import json
import os
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
import zipfile
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


def raw_http_status(port, headers, body=b'', *, path='/api/status', method='GET',
                    truncated_body=False):
    """Read a real rejection response without racing the server's early close.

    Do not send unneeded bytes or half-close a request whose headers are
    already rejectable: Windows can RST a connection with unread request
    bytes before http.client can observe the server's valid 400/403/413.
    Only explicitly truncated bodies require an EOF on the write half.
    """
    con = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        con.putrequest(method, path, skip_host=True)
        for name, value in headers:
            con.putheader(name, value)
        con.endheaders(body)
        if truncated_body:
            # The test explicitly asks the server to detect an incomplete
            # Content-Length body. Never use this for header-only rejection.
            con.sock.shutdown(socket.SHUT_WR)
        response = con.getresponse()
        status = response.status
        response.read()
        return status
    finally:
        con.close()


def test_early_rejection_does_not_require_windows_sensitive_half_close(monkeypatch):
    """A simulated Windows 10053 must not hide an actual HTTP 400 response."""
    class AbortingSocket:
        def shutdown(self, _):
            raise ConnectionAbortedError('Windows 10053: a request was aborted')

    class RejectedResponse:
        status = 400
        def read(self):
            return b'{"error":"not supported"}'

    class Connection:
        def __init__(self, *_args, **_kwargs):
            self.sock = AbortingSocket()
        def putrequest(self, *_args, **_kwargs):
            pass
        def putheader(self, *_args, **_kwargs):
            pass
        def endheaders(self, *_args, **_kwargs):
            pass
        def getresponse(self):
            return RejectedResponse()
        def close(self):
            pass

    monkeypatch.setattr(http.client, 'HTTPConnection', Connection)
    assert raw_http_status(12345, [('Host', '127.0.0.1:12345'),
                                   ('Transfer-Encoding', 'chunked')],
                           method='POST') == 400


def test_engine_get_and_revision_survive_project_creation_without_http_masking(running):
    """Probe the A14-reported GET /api/engines immediately after create.

    Authenticated server HTTP behavior is independently observable here; a
    browser disconnect cannot be reinterpreted as a successful request.
    This is not a Chromium/Windows investigation of the reported UI race.
    """
    client = Client(running)
    assert client.req('/api/engines')[0] == 401
    csrf = client.configured()
    created_status, created, _ = client.req('/api/projects', 'POST',
                                            {'name': 'Engine HTTP probe', 'family': 'transmon'},
                                            {'X-CSRF-Token': csrf})
    assert created_status == 201
    assert created['id'] and created['head']
    observed_digest = None
    for _ in range(3):
        status, engines, _ = client.req('/api/engines')
        assert status == 200
        assert isinstance(engines['engines'], list)
        status, persisted, _ = client.req(f'/api/projects/{created["id"]}')
        assert status == 200
        assert persisted['head'] == created['head']
        digest = persisted['revision_digest']
        assert isinstance(digest, str) and len(digest) == 64
        if observed_digest is None:
            observed_digest = digest
        else:
            assert digest == observed_digest


def test_engine_http_abort_is_not_mistaken_for_usable_response(monkeypatch):
    """A WinError 10053-like abort must propagate, not count as server PASS."""
    class AbortingConnection:
        def __init__(self, *_args, **_kwargs):
            self.sock = None
        def putrequest(self, *_args, **_kwargs):
            pass
        def putheader(self, *_args, **_kwargs):
            pass
        def endheaders(self, *_args, **_kwargs):
            pass
        def getresponse(self):
            raise ConnectionAbortedError('Injected WinError 10053 before HTTP status')
        def close(self):
            pass

    monkeypatch.setattr(http.client, 'HTTPConnection', AbortingConnection)
    with pytest.raises(ConnectionAbortedError, match='WinError 10053'):
        raw_http_status(12345, [('Host', '127.0.0.1:12345')], path='/api/engines')


def _serialized_unsafe_delta_archive(path, raw_name, *, safe_name):
    """Replace BOTH on-disk ZIP header names after writer normalization.

    zipfile.ZipInfo replaces Windows backslashes *while writing* on Win32,
    so writestr(raw_name) alone does not exercise the unsafe input on Win11.
    Equal-length patching retains all header offsets/CRC and ZIP validity.
    """
    assert len(raw_name.encode('ascii')) == len(safe_name.encode('ascii'))
    with zipfile.ZipFile(path, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr(safe_name, 'untrusted')
    data = path.read_bytes()
    assert data.count(safe_name.encode('ascii')) == 2, 'expected local + central header'
    data = data.replace(safe_name.encode('ascii'), raw_name.encode('ascii'))
    assert data.count(raw_name.encode('ascii')) == 2
    path.write_bytes(data)
    with zipfile.ZipFile(path) as bundle:
        # orig_filename retains raw, decoded on-disk central directory name
        # even if ZipInfo.filename was normalized by a Windows Python build.
        assert bundle.infolist()[-1].orig_filename == raw_name
    return data


@pytest.mark.parametrize('raw_name,safe_name', [
    ('../escape.txt', 'zz/escape.txt'),
    ('files/../escape.txt', 'files/aa/escape.txt'),
    ('/absolute.txt', 'aabsolute.txt'),
    (r'files\windows.txt', 'files/windows.txt'),
    (r'files\..\escaped.txt', 'files/aa/escaped.txt'),
    ('C:/escape.txt', 'aa/escape.txt'),
    ('files/ok.txt\x00hidden', 'files/ok.txt_hidden'),
])
def test_delta_archive_traversal_and_link_metadata_rejected_without_os_symlinks(
        tmp_path, raw_name, safe_name):
    """Reject actual malicious ZIP bytes, without privileged host symlinks."""
    tool = Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'orchestration' / 'archive_reader.py'
    spec = importlib.util.spec_from_file_location('a10_agent_delta_archive', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / 'unsafe.zip'
    _serialized_unsafe_delta_archive(path, raw_name, safe_name=safe_name)
    with pytest.raises(ValueError, match='Traversal|Invalid'):
        module.read_zip(path)


def test_delta_archive_symlink_metadata_rejected_on_all_hosts(tmp_path):
    tool = Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'orchestration' / 'archive_reader.py'
    spec = importlib.util.spec_from_file_location('a10_agent_delta_symlink', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / 'link.zip'
    linked = zipfile.ZipInfo('files/linked.txt')
    linked.create_system = 3
    linked.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(path, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr(linked, 'untrusted')
    with pytest.raises(ValueError, match='Symlink'):
        module.read_zip(path)


def test_attack_headers_and_json_caps(running):
    h=running;c=Client(h)
    def raw(headers, body=b'', path='/api/status', method='GET', *, truncated_body=False):
        return raw_http_status(h.server_port, headers, body, path=path,
                               method=method, truncated_body=truncated_body)
    host=('Host',f'127.0.0.1:{h.server_port}')
    assert raw([('Host','evil.example')])==403
    assert raw([host,('Host','evil.example')])==403
    assert raw([host,('Origin','null')],method='POST',path='/api/login')==403
    assert raw([host,('Sec-Fetch-Site','cross-site')],method='POST',path='/api/login')==403
    assert raw([host,('Transfer-Encoding','chunked')],method='POST',path='/api/login')==400
    assert raw([host,('Content-Type','application/json'),('Content-Length','262145')],method='POST',path='/api/login')==413
    assert raw([host,('Content-Type','application/json'),('Content-Length','2'),('Content-Length','2')],method='POST',path='/api/login')==400
    assert raw([host,('Content-Type','application/json'),('Content-Length','3')],b'{',method='POST',path='/api/login',truncated_body=True)==400
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
    user_id = h.app.store.session(next(iter(c.jar)).value)['user_id']
    # Windows can abort a socket after the server rejects an untrusted Origin.
    # A disconnect is NOT a PASS: require an observed HTTP 403 and prove that
    # no project was created after every rejected or aborted attempt.
    assert_transiently_aborted_rejection(
        lambda: c.req('/api/projects','POST',{'name':'Test','family':'transmon'},
                      {'X-CSRF-Token':csrf,'Origin':'http://attacker.invalid'})[0],
        lambda: not h.app.store.list_projects(user_id))
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


# RC14.9 A10 raw-archive and ZIP metadata regressions.
TOOL = Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'orchestration' / 'archive_reader.py'
spec = importlib.util.spec_from_file_location('a10_delta_raw_zip', TOOL)
cycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cycle)


def _raw_zip(tmp_path, *, raw_name: str, safe_name: str) -> Path:
    """Patch equal-size names in local and central headers, not Python ZipInfo."""
    path = tmp_path / 'raw.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('MANIFEST.json', '{}')
        z.writestr(safe_name, 'test payload')
    safe = safe_name.encode('ascii')
    raw = raw_name.encode('ascii')
    assert len(raw) == len(safe)
    encoded = path.read_bytes()
    assert encoded.count(safe) == 2, 'must patch local and central headers'
    encoded = encoded.replace(safe, raw)
    path.write_bytes(encoded)
    assert encoded.count(raw) == 2
    return path


def test_windows_zipinfo_normalization_cannot_hide_backslash(tmp_path):
    """Reject on-disk backslashes on CPython 3.11+ without private ZIP APIs.

    ``ZipInfo.orig_filename`` records the decoded central-directory name
    *before* the platform-dependent ``filename`` sanitization. We patch BOTH
    actual ZIP headers and never assume whether Windows or POSIX normalizes
    the public ``filename`` property. Not a native Windows execution.
    """
    archive = _raw_zip(tmp_path, raw_name=r'files\escape.txt',
                       safe_name='files/escape.txt')
    with zipfile.ZipFile(archive) as z:
        assert z.infolist()[-1].orig_filename == r'files\escape.txt'
    with pytest.raises(ValueError, match='Invalid|Traversal'):
        cycle.read_zip(archive)


def test_null_byte_filename_cannot_be_silently_truncated(tmp_path):
    archive = _raw_zip(tmp_path, raw_name='files/ok.txt\x00escape',
                       safe_name='files/ok.txt_escape')
    with zipfile.ZipFile(archive) as z:
        assert z.infolist()[-1].orig_filename == 'files/ok.txt\x00escape'
        assert z.infolist()[-1].filename == 'files/ok.txt'
    with pytest.raises(ValueError, match='Invalid|Traversal'):
        cycle.read_zip(archive)


def test_regular_delta_archive_still_reads(tmp_path):
    archive = tmp_path / 'okay.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('MANIFEST.json', '{"status":"test"}')
        z.writestr('files/agent_cycle/continuity/A10.md', 'safe')
    doc, body = cycle.read_zip(archive)
    assert doc == {'status': 'test'}
    assert body == {'files/agent_cycle/continuity/A10.md': b'safe'}


@pytest.mark.parametrize('mode', [0o010644, 0o020600, 0o060600])
def test_nonregular_posix_zip_metadata_is_not_a_delta_file(tmp_path, mode):
    """A delta member is regular source, never FIFO/device metadata."""
    archive = tmp_path / 'nonregular.zip'
    entry = zipfile.ZipInfo('files/tests/core/device.py')
    entry.create_system = 3
    entry.external_attr = mode << 16
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('MANIFEST.json', '{}')
        z.writestr(entry, b'not a file')
    with pytest.raises(ValueError, match='Non-regular'):
        cycle.read_zip(archive)


def test_bad_delta_manifest_must_be_json_object(tmp_path):
    archive = tmp_path / 'array.json.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('MANIFEST.json', '[1, 2]')
    with pytest.raises(ValueError, match='manifest object'):
        cycle.read_zip(archive)


def test_report_sequence_reservation_is_cross_process_and_fail_closed(tmp_path):
    """Real OS subprocesses, not two threads: O_EXCL stops duplicate reports.

    Native solver is stubbed only inside the worker subprocess. This proves
    software reservation behavior, not Windows or scientific qualification.
    """
    import subprocess
    import sys
    import time
    from sqe_studio import cycle_qualification as qualifier

    root = Path(__file__).resolve().parents[2]
    (tmp_path / 'qualification_plan.json').write_bytes(
        (root / 'qualification_plan.json').read_bytes())
    first = qualifier.next_report_path(tmp_path)
    reservation = first.with_name(first.name + '.running')
    started = tmp_path / 'worker_started'
    release = tmp_path / 'worker_release'
    worker_code = '''
import sys, time
from pathlib import Path
from sqe_studio import cycle_qualification as q
root, destination = map(Path, sys.argv[1:3])
def hold(root, destination, plan, *, notify=None):
    (root / 'worker_started').write_text('reserved', encoding='ascii')
    deadline = time.monotonic() + 8
    while not (root / 'worker_release').exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not (root / 'worker_release').exists():
        raise RuntimeError('test synchronization timed out')
    return {'status':'SOFTWARE_FIXTURE_ONLY'}
q._run_reserved_qualification = hold
q.run_release_qualification(root, destination)
'''
    challenger_code = '''
import sys
from pathlib import Path
from sqe_studio import cycle_qualification as q
root, destination = map(Path, sys.argv[1:3])
q._run_reserved_qualification = lambda *args, **kwargs: (_ for _ in ()).throw(
    RuntimeError('O_EXCL did not reject duplicate'))
try:
    q.run_release_qualification(root, destination)
except FileExistsError:
    sys.exit(7)
'''
    env = {**os.environ, 'PYTHONPATH': str(root / 'src')}
    first_worker = subprocess.Popen(
        [sys.executable, '-c', worker_code, str(tmp_path), str(first)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 8
        while not started.exists() and time.monotonic() < deadline:
            if first_worker.poll() is not None:
                break
            time.sleep(0.02)
        assert started.exists(), 'reservation worker did not start'
        assert reservation.is_file()
        assert qualifier.next_report_path(tmp_path).name.endswith('0002.zip')
        challenger = subprocess.run(
            [sys.executable, '-c', challenger_code, str(tmp_path), str(first)],
            env=env, capture_output=True, text=True, timeout=10)
        assert challenger.returncode == 7, challenger.stderr
        assert reservation.is_file()
    finally:
        release.write_text('done', encoding='ascii')
        try:
            stdout, stderr = first_worker.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            first_worker.kill()
            stdout, stderr = first_worker.communicate(timeout=5)
    assert first_worker.returncode == 0, (stdout, stderr)
    assert not reservation.exists()


@pytest.mark.parametrize('mode,accepted', [
    (0o100644, True), (0o100755, True), (0o100000, True),
    (0o120777, False), (0o040755, False), (0o010644, False),
    (0o020600, False),
])
def test_serialized_zip_permission_and_type_variants(tmp_path, mode, accepted):
    """Physical ZIP metadata is checked: executable regular files are safe,
    but link, directory, FIFO and device modes are never owned source.
    No privileged OS symlink or locale-specific ZIP writer is needed.
    """
    archive = tmp_path / f'permissions-{mode:o}.zip'
    member = zipfile.ZipInfo('files/agent_cycle/continuity/A10.md')
    member.create_system = 3
    member.external_attr = mode << 16
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr(member, b'content')
    if accepted:
        _, files = cycle.read_zip(archive)
        assert files[member.filename] == b'content'
    else:
        with pytest.raises(ValueError, match='Symlink|Non-regular'):
            cycle.read_zip(archive)


def test_raw_duplicate_names_are_rejected_before_members_are_admitted(tmp_path):
    archive = tmp_path / 'duplicated.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr('files/agent_cycle/continuity/A10.md', b'first')
        with pytest.warns(UserWarning, match='Duplicate name'):
            bundle.writestr('files/agent_cycle/continuity/A10.md', b'second')
    with zipfile.ZipFile(archive) as bundle:
        assert [i.orig_filename for i in bundle.infolist()].count(
            'files/agent_cycle/continuity/A10.md') == 2
    with pytest.raises(ValueError, match='duplicated'):
        cycle.read_zip(archive)


def test_differing_local_and_central_zip_headers_are_corruption(tmp_path):
    archive = tmp_path / 'headers.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr('files/agent_cycle/continuity/A10.md', b'content')
    original = b'files/agent_cycle/continuity/A10.md'
    other = b'files/agent_cycle/continuity/A10.xy'
    data = archive.read_bytes()
    assert len(original) == len(other) and data.count(original) == 2
    # Touch only the local header; zipfile itself must detect mismatch.
    archive.write_bytes(data.replace(original, other, 1))
    with pytest.raises(cycle.ArchiveCorruptError, match='Corrupt archive ZIP'):
        cycle.read_zip(archive)

@pytest.mark.parametrize('unsafe', [
    'files/CON.txt', 'files/a/aux', 'files/x/NUL.bin', 'files/LPT1',
    'files/name.', 'files/space ', 'files/COM9.txt',
])
def test_windows_noncanonical_delta_member_names_rejected(tmp_path, unsafe):
    archive = tmp_path / 'reserved.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr(unsafe, 'untrusted')
    with pytest.raises(ValueError, match='Windows-incompatible'):
        cycle.read_zip(archive)


def test_case_insensitive_zip_aliases_are_rejected_across_hosts(tmp_path):
    archive = tmp_path / 'alias.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr('files/agent_cycle/continuity/A10.md', b'one')
        bundle.writestr('files/agent_cycle/continuity/a10.md', b'two')
    with pytest.raises(ValueError, match='case-colliding'):
        cycle.read_zip(archive)


def test_unicode_delta_path_roundtrips_without_cp1252_assumptions(tmp_path):
    archive = tmp_path / 'utf8.zip'
    member = 'files/agent_cycle/continuity/résumé.md'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('MANIFEST.json', '{}')
        bundle.writestr(member, b'source')
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.infolist()[-1].flag_bits & 0x800  # ZIP UTF-8 flag
        assert bundle.infolist()[-1].orig_filename == member
    _, files = cycle.read_zip(archive)
    assert files[member] == b'source'
