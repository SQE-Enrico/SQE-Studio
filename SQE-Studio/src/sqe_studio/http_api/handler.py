"""Handler; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import HEX_ID
from .common import MAX_JSON
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from sqe_studio import __version__
from sqe_studio.contracts import ValidationError
from sqe_studio.store import Conflict
from sqe_studio.store import NotFound
from urllib.parse import urlsplit
import hmac
import json
import socket
import sqlite3
from .router import Request,public_route,authenticated_route

class Handler(BaseHTTPRequestHandler):
    server_version='SQE-Studio/'+__version__
    sys_version=''
    def log_message(self,fmt,*args):
        # Never log URLs, query strings, credentials, cookies, request bodies or
        # exception details; the default BaseHTTPRequestHandler logs full paths.
        return
    def log_request(self,code='-',size='-'):
        print(f'HTTP {self.command if self.command in ("GET","POST") else "OTHER"} status={code}',flush=True)
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    @property
    def app(self):return self.server.app
    def send_bytes(self,content,status=200,content_type='application/json',extra=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Cross-Origin-Opener-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError):pass
    def send_json(self,obj,status=200,extra=None):
        self.send_bytes(json.dumps(obj,sort_keys=True,allow_nan=False).encode('utf-8'),status,'application/json; charset=utf-8',extra)
    def json_body(self):
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:
            raise ApiError('A single Content-Length is required',400)
        value=self.headers.get('Content-Length','')
        if not value.isascii() or not value.isdecimal():raise ApiError('Invalid Content-Length',400)
        if len(value)>8:raise ApiError('JSON body outside 256 KiB limit',413)
        size=int(value)
        if size>MAX_JSON:raise ApiError('JSON body outside 256 KiB limit',413)
        if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
            raise ApiError('Expected application/json',415)
        try:
            raw=self.rfile.read(size)
            if len(raw)!=size:raise ApiError('Truncated request body',400)
            def unique_pairs(pairs):
                out={}
                for name,val in pairs:
                    if name in out:raise ValueError('Duplicate JSON field')
                    out[name]=val
                return out
            obj=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (ValueError,UnicodeDecodeError,RecursionError):raise ApiError('Invalid JSON',400) from None
        if not isinstance(obj,dict):raise ApiError('Expected JSON object',400)
        return obj
    def token(self):
        if len(self.headers.get_all('Cookie',[]))!=1:return ''
        c=SimpleCookie()
        try:c.load(self.headers.get('Cookie',''))
        except Exception:return ''
        token=c['sqe_session'].value if 'sqe_session' in c else ''
        return token if len(token)<=128 else ''
    def identity(self,required=True):
        sess=self.app.store.session(self.token())
        if required and not sess:raise ApiError('Sign in to continue',401)
        return sess
    def security(self,write=False):
        if self.client_address[0]!='127.0.0.1':raise ApiError('Loopback only',403)
        hosts=self.headers.get_all('Host',[])
        if len(hosts)!=1 or hosts[0] not in (
                f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            raise ApiError('Unexpected Host header',403)
        if self.headers.get('Transfer-Encoding'):
            raise ApiError('Transfer-Encoding is not supported',400)
        if write:
            origins=self.headers.get_all('Origin',[])
            if len(origins)>1 or (origins and origins[0] not in (
                    f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')):
                raise ApiError('Cross-origin request rejected',403)
            fetch_site=self.headers.get('Sec-Fetch-Site','')
            if fetch_site not in ('','same-origin','none'):
                raise ApiError('Cross-site request rejected',403)
    @staticmethod
    def _load_result_json(folder,name,limit):
        target=folder/name
        if folder.is_symlink() or target.is_symlink() or not target.is_file():
            raise ApiError('Native results unavailable',404)
        if not target.resolve().is_relative_to(folder.resolve()):
            raise ApiError('Native result path rejected',403)
        if target.stat().st_size>limit:raise ApiError('Native result exceeds JSON limit',413)
        try:return json.loads(target.read_text(encoding='utf-8'))
        except (ValueError,UnicodeDecodeError):raise ApiError('Invalid native result JSON',502) from None
    def _run_folder(self,user,pid,run_id,*,allow_diagnostics=False):
        if not HEX_ID.fullmatch(pid) or not HEX_ID.fullmatch(run_id):raise ApiError('Run not found',404)
        info=self.app.store.run(user,pid,run_id)
        expected=self.app.store.root/'native-runs'/pid/run_id
        run_base=self.app.store.root/'native-runs'
        if (Path(info['path']).absolute()!=expected or
            run_base.is_symlink() or (run_base/pid).is_symlink() or expected.is_symlink() or
            not expected.resolve().is_relative_to(self.app.store.root) or
            (expected/'output').is_symlink()):
            raise ApiError('Unsafe native result location',403)
        allowed=('completed','failed','timed_out','cancelled') if allow_diagnostics else ('completed',)
        if info['state'] not in allowed:raise ApiError('Native results unavailable',404)
        return info,expected
    def _check_manifest(self,user,pid,info,manifest):
        if not isinstance(manifest,dict) or manifest.get('schema')!='sqe.artifact.v1':
            raise ApiError('Invalid native result manifest',502)
        project=self.app.store.project(user,pid,info['revision_id'])
        if (manifest.get('revision_id')!=info['revision_id'] or
            manifest.get('project_digest')!=project['revision_digest'] or
            manifest.get('engine')!=info['engine'] or
            manifest.get('study_id')!=info['study_id']):
            raise ApiError('Native result provenance mismatch',409)
        return manifest
    def call(self,method):
        try:
            self.security(method!='GET')
            parsed=urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith('/') or parsed.fragment:
                raise ApiError('Invalid request target',400)
            request=Request(method,parsed)
            if public_route(self,request):return
            user=self.identity()
            if method=='POST':
                tokens=self.headers.get_all('X-CSRF-Token',[])
                if len(tokens)!=1 or not hmac.compare_digest(tokens[0],user['csrf']):
                    raise ApiError('CSRF token is missing or invalid',403)
            if authenticated_route(self,Request(method,parsed,user)):return
            raise ApiError('Route not found',404)
        except Conflict as exc:self.send_json({'error':str(exc)},409)
        except NotFound as exc:self.send_json({'error':str(exc)},404)
        except (ValidationError,ValueError,TypeError) as exc:
            # Validation messages are declarative. Never expose traceback or
            # database paths, internal stack traces or native stderr.
            self.send_json({'error':str(exc)[:400]},422)
        except ApiError as exc:self.send_json({'error':exc.message},exc.status)
        except (TimeoutError,socket.timeout):self.send_json({'error':'Request timed out'},408)
        except (OSError,sqlite3.Error) as exc:self.send_json({'error':'Local storage error'},500)
    def do_GET(self):self.call('GET')
    def do_POST(self):self.call('POST')
