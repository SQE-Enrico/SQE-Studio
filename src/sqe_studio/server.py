"""Loopback-only SQE Studio HTTP API, independent of native engine processes.

Security boundary: strict Host/Origin, session + CSRF, project ACL, bounded JSON,
revision-bound run results. Do not place behind a proxy or expose on a LAN.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from . import __version__
from .contracts import STEPS, ENGINES, ValidationError, stage_status, validate_project
from .jobs import Jobs
from .orchestration.artifacts import verify_manifest, ArtifactInvalid
from .interop.comparison import report as comparison_report
from .store import Store, Conflict, NotFound
from .design_library import list_templates, instantiate, component_catalog, use_case_catalog
from .eda.capabilities import list_capabilities
from .interop.native_views import palace_eigenmodes, NativeDisplayError
from .adapters.base import EngineBlocked
from .adapters.quantum_metal_adapter import validate_recipe
from .adapters.sqdmetal_palace_adapter import preflight as em_preflight

STATIC=Path(__file__).parent/'web'
ASSETS={'index.html':'text/html; charset=utf-8',
        'app.js':'text/javascript; charset=utf-8',
        'style.css':'text/css; charset=utf-8'}
COOKIE_CLEAR='sqe_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
MAX_JSON=256*1024
MAX_RESULT_JSON=8*1024*1024
HEX_ID=re.compile(r'[0-9a-f]{32}\Z')

class ApiError(Exception):
    def __init__(self,message,status=400):self.message,self.status=message,status

class Service:
    def __init__(self,data):
        self.store=Store(data)
        self.jobs=Jobs(self.store)
        self.setup_file=self.store.root/'setup.token'
        if self.setup_file.is_symlink():raise ValueError('Unsafe first-run token file')
        if self.store.has_account():
            # In a crash between first account creation and token deletion,
            # never leave a reusable bootstrap credential on disk.
            self.setup_file.unlink(missing_ok=True)
        elif not self.setup_file.exists():
            try:
                fd=os.open(self.setup_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w',encoding='ascii') as out:
                    out.write(secrets.token_urlsafe(32))
            except FileExistsError:raise ValueError('First-run setup token race') from None
        self._login_lock=threading.Lock()
        self._failures=[]
    def login_allowed(self):
        with self._login_lock:
            now=time.monotonic()
            self._failures=[t for t in self._failures if now-t<300]
            return len(self._failures)<12
    def login_result(self,successful):
        with self._login_lock:
            if successful:self._failures.clear()
            else:self._failures.append(time.monotonic())
    def engines(self):
        def available(x):
            try:return importlib.util.find_spec(x) is not None
            except (ImportError,ValueError,AttributeError):return False
        return [
          {'id':'quantum_metal','name':'Quantum Metal','available':available('qiskit_metal'),'capability':'Native QDesign + GDS renderer','mode':'native'},
          {'id':'sqdmetal_palace','name':'SQDMetal / Gmsh / Palace','available':available('SQDMetal') and available('gmsh') and available('qiskit_metal'), 'capability':'3D EM workflow · reviewed physical setup required','mode':'native_conditional'},
          {'id':'scqubits','name':'scqubits','available':available('scqubits'),'capability':'Quantum spectra','mode':'native'},
          {'id':'josephson_circuits','name':'JosephsonCircuits.jl','available':False,'capability':'Julia circuit/RF','mode':'blocked_pending_reviewed_adapter'},
        ]

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
            path=parsed.path
            if method=='GET' and path in ('/','/index.html','/app.js','/style.css'):
                target='index.html' if path=='/' else path[1:]
                return self.send_bytes((STATIC/target).read_bytes(),200,ASSETS[target])
            if method=='GET' and path=='/api/status':
                return self.send_json({'version':__version__,'setup_required':not self.app.store.has_account(),
                                       'local_only':True,'service':'ready'})
            if method=='POST' and path=='/api/setup':
                obj=self.json_body()
                key=self.app.setup_file.read_text(encoding='ascii') if self.app.setup_file.is_file() else ''
                supplied=obj.get('setup_token','')
                if not isinstance(supplied,str) or len(supplied)>128 or not key or not hmac.compare_digest(supplied,key):
                    raise ApiError('Invalid first-run setup token',403)
                self.app.store.setup(obj.get('email'),obj.get('password'))
                self.app.setup_file.unlink(missing_ok=True)
                return self.send_json({'ok':True})
            if method=='POST' and path=='/api/login':
                obj=self.json_body()
                if not self.app.login_allowed():raise ApiError('Too many login failures; retry after five minutes',429)
                session=self.app.store.login(obj.get('email'),obj.get('password'))
                self.app.login_result(bool(session))
                if not session:raise ApiError('Invalid credentials',401)
                token,csrf=session
                return self.send_json({'ok':True,'csrf':csrf},200,{'Set-Cookie':f'sqe_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            user=self.identity();uid=user['user_id']
            if method=='POST':
                tokens=self.headers.get_all('X-CSRF-Token',[])
                if len(tokens)!=1 or not hmac.compare_digest(tokens[0],user['csrf']):
                    raise ApiError('CSRF token is missing or invalid',403)
            if method=='GET' and path=='/api/me':return self.send_json({'authenticated':True,'csrf':user['csrf']})
            if method=='POST' and path=='/api/logout':
                self.app.store.logout(self.token())
                return self.send_json({'ok':True},200,{'Set-Cookie':COOKIE_CLEAR})
            if method=='POST' and path=='/api/password':
                obj=self.json_body()
                if set(obj)!={'current_password','new_password'}:
                    raise ApiError('Password change requires current_password and new_password',422)
                if not self.app.store.change_password(uid,obj['current_password'],obj['new_password']):
                    raise ApiError('Current password is invalid',401)
                return self.send_json({'ok':True,'reauthentication_required':True},200,{'Set-Cookie':COOKIE_CLEAR})
            if method=='GET' and path=='/api/engines':return self.send_json({'engines':self.app.engines()})
            if method=='GET' and path=='/api/workflow':return self.send_json({'stages':STEPS,'engines':ENGINES})
            if method=='GET' and path=='/api/projects':return self.send_json({'projects':self.app.store.list_projects(uid)})
            if method=='GET' and path=='/api/design/templates':
                return self.send_json({'templates':list_templates()})
            if method=='GET' and path=='/api/design/capabilities':
                return self.send_json({'schema':'sqe.eda-capability-map.v1',
                                       'edges':list_capabilities()})
            if method=='GET' and path=='/api/design/use-cases':
                return self.send_json({'schema':'sqe.design-cases.v1','cases':use_case_catalog()})
            if method=='GET' and path=='/api/design/components':
                return self.send_json(component_catalog())
            if method=='POST' and path=='/api/design/check':
                obj=self.json_body()
                if set(obj) != {'model'}:raise ApiError('Check requires a project model',422)
                model=validate_project(obj['model'])
                result={'schema':'sqe.design-check.v1','layout':{'ready':False},
                        'em':[],'scientific_status':'not_qualified','fabrication_status':'HOLD'}
                try:
                    validate_recipe(model['layout'])
                    result['layout']={'ready':True,'message':'Reviewed recipe syntax; native geometry not yet built'}
                except (ValueError,TypeError,EngineBlocked) as exc:
                    result['layout']={'ready':False,'message':str(exc)[:300]}
                for study in model['studies']:
                    if study['engine'] != 'sqdmetal_palace':continue
                    try:
                        if not result['layout']['ready']:
                            raise ValueError('Native layout recipe must pass its own validation first')
                        em_preflight(study, model)
                        check={'study_id':study['id'],'ready':True,
                               'message':'Physical mapping schema accepted; no native mesh, solver or scientific validation performed'}
                    except (ValueError,TypeError,EngineBlocked) as exc:
                        check={'study_id':study['id'],'ready':False,'message':str(exc)[:300]}
                    result['em'].append(check)
                return self.send_json(result)
            if method=='POST' and path=='/api/projects':
                obj=self.json_body()
                if set(obj) not in ({'name','family'}, {'name','family','template_id'}):
                    raise ApiError('Project requires name, family and optional starter design',422)
                name, family=obj['name'],obj['family']
                model=instantiate(obj['template_id'],name,family) if 'template_id' in obj else None
                return self.send_json(self.app.store.create(uid,name,family,model=model),201)
            parts=path.strip('/').split('/')
            if len(parts)>=3 and parts[:2]==['api','projects']:
                pid=parts[2]
                if not HEX_ID.fullmatch(pid):raise ApiError('Project not found',404)
                if len(parts)==3 and method=='GET':
                    project=self.app.store.project(uid,pid)
                    project['stages']=stage_status(project['model'],[r['engine'] for r in self.app.store.runs(uid,pid) if r['state']=='completed' and r['revision_id']==project['head']])
                    return self.send_json(project)
                if len(parts)==4 and parts[3]=='revisions' and method=='GET':
                    return self.send_json({'revisions':self.app.store.revisions(uid,pid)})
                if len(parts)==5 and parts[3]=='revisions' and method=='GET':
                    return self.send_json(self.app.store.project(uid,pid,parts[4]))
                if len(parts)==4 and parts[3]=='commit' and method=='POST':
                    obj=self.json_body()
                    if set(obj)!={'expected_revision','model'}:raise ApiError('Commit requires expected_revision and model',422)
                    rid=self.app.store.commit(uid,pid,obj['expected_revision'],obj['model'])
                    return self.send_json({'revision':rid})
                if len(parts)==4 and parts[3]=='runs' and method=='GET':
                    listed=self.app.store.runs(uid,pid)
                    for item in listed:
                        item['is_sweep']=False
                        if item['state']!='completed':continue
                        try:
                            _info,run_dir=self._run_folder(uid,pid,item['id'])
                            marker=run_dir/'SWEEP_MANIFEST.json'
                            item['is_sweep']=marker.is_file() and not marker.is_symlink()
                        except ApiError:
                            # An unsafe run stays visible as evidence, but is not
                            # presented as a verified result or eligible for comparison.
                            item['unsafe_location']=True
                    return self.send_json({'runs':listed})
                if len(parts)==4 and parts[3]=='compare' and method=='GET':
                    q=parse_qs(parsed.query, keep_blank_values=True, max_num_fields=2)
                    if set(q) != {'left','right'} or any(len(q[k]) != 1 or not HEX_ID.fullmatch(q[k][0]) for k in q):
                        raise ApiError('Two run identifiers are required',400)
                    if q['left'][0] == q['right'][0]:
                        raise ApiError('Comparison requires two distinct completed runs',400)
                    reviews=[]
                    for run_id in (q['left'][0],q['right'][0]):
                        info,folder=self._run_folder(uid,pid,run_id)
                        project=self.app.store.project(uid,pid,info['revision_id'])
                        try:
                            ref=verify_manifest(folder/'output',revision_id=info['revision_id'],
                                                project_digest=project['revision_digest'],
                                                study_id=info['study_id'],engine=info['engine'])
                        except (ArtifactInvalid, OSError) as exc:
                            raise ApiError('Comparison source failed content/revision verification',409) from exc
                        manifest=self._load_result_json(folder/'output','RESULT_MANIFEST.json',MAX_RESULT_JSON)
                        self._check_manifest(uid,pid,info,manifest)
                        spectrum=None
                        if ref.artifact_type=='scqubits.spectrum' and 'spectrum.json' in {a['name'] for a in manifest['artifacts']}:
                            spectrum=self._load_result_json(folder/'output','spectrum.json',MAX_RESULT_JSON)
                        reviews.append((info,project,manifest,spectrum))
                    (li,lp,lm,ls),(ri,rp,rm,rs)=reviews
                    return self.send_json(comparison_report(lm,rm,li,ri,lp,rp,ls,rs))
                if len(parts)==4 and parts[3]=='runs' and method=='POST':
                    obj=self.json_body()
                    if set(obj)!={'revision','study_id'}:raise ApiError('Run requires revision and study_id',422)
                    return self.send_json({'run_id':self.app.jobs.start(uid,pid,obj['revision'],obj['study_id'])},202)
                if len(parts)==4 and parts[3]=='sweeps' and method=='POST':
                    obj=self.json_body()
                    if set(obj) not in ({'revision','study_id','axes','mode'},
                                        {'revision','study_id','axes','mode','selected'}):
                        raise ApiError('Sweep requires revision, study, numeric axes and mode',422)
                    return self.send_json({'run_id':self.app.jobs.start_sweep(
                        uid,pid,obj['revision'],obj['study_id'],obj['axes'],
                        mode=obj['mode'],selected=obj.get('selected'))},202)

                if len(parts)==6 and parts[3]=='runs' and parts[5]=='sweep' and method=='GET':
                    info,folder=self._run_folder(uid,pid,parts[4])
                    # The native-job verifier checks the immutable snapshot, point order,
                    # revision, engine, content hashes and per-point fingerprints.
                    try:
                        refs=self.app.jobs._check_completed_artifacts(info)
                        snapshot=self._load_result_json(folder,'snapshot.json',MAX_RESULT_JSON)
                        summary=self._load_result_json(folder,'SWEEP_MANIFEST.json',MAX_RESULT_JSON)
                        plan=snapshot.get('sweep_plan')
                        if not isinstance(plan,dict) or len(plan.get('points',[]))!=len(refs):
                            raise ArtifactInvalid('Incomplete sweep point provenance')
                        rows=[]
                        for point,ref in zip(plan['points'],refs):
                            out=folder/'output'/f'point_{point["index"]:04d}'
                            m=self._load_result_json(out,'RESULT_MANIFEST.json',MAX_RESULT_JSON)
                            self._check_manifest(uid,pid,info,m)
                            row={'index':point['index'],'coordinates':point['coordinates'],
                                 'artifact_type':m['artifact_type'],'engine_version':m['engine_version'],
                                 'scientific_status':m['scientific_status']}
                            if ref.artifact_type=='scqubits.spectrum' and 'spectrum.json' in {a['name'] for a in m['artifacts']}:
                                row['spectrum']=self._load_result_json(out,'spectrum.json',MAX_RESULT_JSON)
                            if ref.artifact_type=='palace.eigenmodes':
                                row['eigenmodes']=palace_eigenmodes(out,m)
                            rows.append(row)
                        return self.send_json({'schema':'sqe.sweep-view.v1','status':'native_outputs_unqualified',
                                               'revision_id':info['revision_id'],
                                               'study_id':info['study_id'],'engine':info['engine'],
                                               'points':rows,'convergence_verified':False,
                                               'mode_matching_verified':False,
                                               'fabrication_status':'HOLD'})
                    except (ArtifactInvalid,NativeDisplayError,KeyError,TypeError,ValueError,OSError) as exc:
                        raise ApiError('Native sweep evidence failed verification',409) from exc
                if len(parts)==6 and parts[3]=='runs' and parts[5] in ('result','download') and method=='GET':
                    if parts[5]=='download':
                        info,folder=self._run_folder(uid,pid,parts[4],allow_diagnostics=True)
                        # Completed runs require a checked native result manifest;
                        # failed runs may expose only their own authenticated diagnostics.
                        if info['state']=='completed':
                            # Both ordinary runs and sweeps are content verified by Jobs.archive.
                            try:self.app.jobs._check_completed_artifacts(info)
                            except (ArtifactInvalid,OSError,ValueError,KeyError,TypeError) as exc:
                                raise ApiError('Native archive failed content verification',409) from exc
                        try:raw=self.app.jobs.archive(uid,pid,parts[4])
                        except (ArtifactInvalid,OSError,ValueError,KeyError,TypeError) as exc:
                            raise ApiError('Native archive failed content verification',409) from exc
                        return self.send_bytes(raw,200,'application/zip',{'Content-Disposition':f'attachment; filename="SQE-run-{parts[4]}.zip"'})
                    info,folder=self._run_folder(uid,pid,parts[4])
                    if (folder/'SWEEP_MANIFEST.json').exists():
                        # A sweep has per-point RESULT_MANIFEST files rather than
                        # one fabricated aggregate scientific result.
                        try:self.app.jobs._check_completed_artifacts(info)
                        except (ArtifactInvalid,OSError,ValueError,KeyError,TypeError) as exc:
                            raise ApiError('Native sweep evidence failed verification',409) from exc
                        raise ApiError('This run is a native sweep; inspect its verified points',404)
                    manifest=self._load_result_json(folder/'output','RESULT_MANIFEST.json',MAX_RESULT_JSON)
                    self._check_manifest(uid,pid,info,manifest)
                    if parts[5]=='result':
                        project=self.app.store.project(uid,pid,info['revision_id'])
                        try:
                            verify_manifest(folder/'output',revision_id=info['revision_id'],
                                            project_digest=project['revision_digest'],
                                            study_id=info['study_id'],engine=info['engine'])
                        except (ArtifactInvalid, OSError) as exc:
                            raise ApiError('Native output failed content/revision verification',409) from exc
                        result={'manifest':manifest}
                        if 'spectrum.json' in {a['name'] for a in manifest['artifacts']}:
                            result['spectrum']=self._load_result_json(folder/'output','spectrum.json',MAX_RESULT_JSON)
                        try:
                            result['eigenmodes']=palace_eigenmodes(folder/'output',manifest)
                        except (NativeDisplayError,OSError,ValueError) as exc:
                            raise ApiError('Native EM table failed structural verification',409) from exc
                        return self.send_json(result)
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

def make_server(data,port=8000):
    http=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    http.daemon_threads=True
    try:http.app=Service(data)
    except BaseException:
        http.server_close()
        raise
    return http

def main():
    p=argparse.ArgumentParser(description='SQE Studio local-only product foundation')
    p.add_argument('--data',default='studio-data',help='Private local database/artifact path')
    p.add_argument('--port',type=int,default=8000)
    args=p.parse_args()
    if not 1024<=args.port<=65535:p.error('Port must be 1024..65535')
    server=make_server(args.data,args.port)
    if not server.app.store.has_account():
        print('FIRST-RUN SETUP TOKEN (local console only):',server.app.setup_file.read_text(encoding='ascii'),flush=True)
    print(f'SQE Studio running: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
