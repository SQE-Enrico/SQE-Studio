"""Dependency-light WSGI JSON API. Use Gunicorn + the supplied proxy for deployment."""
import json
import mimetypes
from http.cookies import SimpleCookie
from pathlib import Path
import re
import tempfile
import zipfile
from itertools import islice
from urllib.parse import parse_qs, unquote, urlsplit

from .auth import Auth,Problem
from .catalog import capabilities
from .db import Store
from .jobs import Jobs
from .process import resolve,wafer_positions,document
from .projects import Projects
from .settings import Settings
from .diagnostic_control import DiagnosticControl
from .ecosystem_control import EcosystemControl
from .dependencies import DependencyManager
from .support_bundles import create_support_bundle

STATIC=Path(__file__).parent/'static'


class FileBody:
    def __init__(self,path): self.file=Path(path).open('rb')
    def __iter__(self):
        while True:
            block=self.file.read(65536)
            if not block: break
            yield block
    def close(self): self.file.close()


class Application:
    def __init__(self,settings):
        self.settings=settings; self.store=Store(settings)
        self.auth=Auth(self.store); self.projects=Projects(self.store); self.jobs=Jobs(self.store)
        self.auth.setup_token()
        self.diagnostics = DiagnosticControl(self.store.root, Path(__file__).resolve().parents[3])
        self.dependencies = DependencyManager(self.store.root, Path(__file__).resolve().parents[3])
        self.ecosystem = EcosystemControl(self.store.root, Path(__file__).resolve().parents[3], self.dependencies)

    def __call__(self,env,start_response):
        status=200; headers=[]
        try:
            method=env.get('REQUEST_METHOD','GET'); path=unquote(env.get('PATH_INFO','/'))
            expected=urlsplit(self.settings.origin).netloc.lower()
            if env.get('HTTP_HOST',expected).lower()!=expected: raise Problem('Unexpected host',400)
            if method not in ('GET','POST','PUT','DELETE'): raise Problem('Method not allowed',405)
            if method!='GET':
                origin=env.get('HTTP_ORIGIN')
                if origin and origin.rstrip('/')!=self.settings.origin: raise Problem('Cross-origin request rejected',403)
                if env.get('HTTP_SEC_FETCH_SITE')=='cross-site': raise Problem('Cross-site request rejected',403)
            query={k:v[-1] for k,v in parse_qs(env.get('QUERY_STRING','')).items()}
            parts=path.strip('/').split('/')
            cookies=SimpleCookie()
            try: cookies.load(env.get('HTTP_COOKIE',''))
            except Exception: pass
            raw=cookies['sqe_session'].value if 'sqe_session' in cookies else ''
            public=path in ('/api/status','/api/auth/login','/api/auth/setup','/api/auth/activate','/healthz') or not path.startswith('/api/')
            user=None; csrf=None
            if not public:
                user,csrf=self.auth.session(raw)
                if method!='GET' and not __import__('hmac').compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),csrf):
                    raise Problem('CSRF token is missing or invalid',403)
            def body(binary=False):
                try: length=int(env.get('CONTENT_LENGTH','0') or 0)
                except ValueError: raise Problem('Invalid content length')
                limit=self.settings.max_upload_mb*1024**2 if binary else 2*1024**2
                if length<0 or length>limit: raise Problem('Request exceeds upload limit',413)
                data=env['wsgi.input'].read(length)
                if len(data)!=length: raise Problem('Incomplete request body')
                if binary: return data
                if not env.get('CONTENT_TYPE','').startswith('application/json'): raise Problem('Send application/json',415)
                try: value=json.loads(data)
                except (ValueError,UnicodeError): raise Problem('Invalid JSON')
                if not isinstance(value,dict): raise Problem('Expected a JSON object')
                return value
            def need(method_name):
                if method!=method_name: raise Problem('Method not allowed',405)
            if path=='/healthz': result={'status':'ok'}
            elif path=='/api/status':
                result={'setup_required':not bool(self.store.one('SELECT id FROM users LIMIT 1')),
                        'development':self.settings.development,'name':'SQE Studio',
                        'group':'INRiM · Superconducting Quantum Electronics Group'}
            elif path=='/api/auth/setup':
                need('POST'); data=body(); self.auth.setup(data['token'],data['email'],data['name'],data['password']); result={'created':True}
            elif path=='/api/auth/activate':
                need('POST'); data=body(); self.auth.activate(data['token'],data['password']); result={'activated':True}
            elif path=='/api/auth/login':
                need('POST'); data=body()
                token,csrf,actor=self.auth.login(data.get('email',''),data.get('password',''),env.get('REMOTE_ADDR','unknown'))
                headers.append(('Set-Cookie',self.cookie(token)))
                result={'user':actor,'csrf':csrf}
            elif path=='/api/auth/session': result={'user':user,'csrf':csrf}
            elif path=='/api/auth/logout':
                need('POST'); self.auth.logout(raw); headers.append(('Set-Cookie',self.cookie('',0))); result={'signed_out':True}
            elif path=='/api/system/startup':
                need('GET')
                if user['role']!='admin': raise Problem('Administrator access required',403)
                report=self.store.root/'startup-checks.json'
                if report.exists():
                    try: result=json.loads(report.read_text(encoding='utf-8'))
                    except (OSError,ValueError): result={'status':'UNKNOWN','message':'Start-up check report could not be read'}
                else: result={'status':'NOT_RUN','message':'No Windows start-up report yet'}
            elif path.startswith('/api/system/diagnostics'):
                # Intentionally unavailable on remotely deployed servers. These
                # probes execute installed native tools and are workstation-only.
                if not self.settings.development or urlsplit(self.settings.origin).hostname not in ('127.0.0.1','localhost'):
                    raise Problem('Diagnostics are available only on the local workstation',403)
                if user['role'] != 'admin': raise Problem('Administrator access required',403)
                if path=='/api/system/diagnostics':
                    if method=='GET':
                        from ..diagnostics import PROFILES
                        result={'runs':self.diagnostics.list(), 'available':True, 'profiles':list(PROFILES),
                        'privacy':'Review the contents of every ZIP before sharing. Nothing is uploaded.',
                        'native_fem_validated':False}
                    else:
                        need('POST'); args=body()
                        if set(args)-{'extended','skip_tests','scientific','scientific_profile','full_regressions'}: raise Problem('Unknown diagnostic option')
                        result=self.diagnostics.start(extended=args.get('extended',False),skip_tests=args.get('skip_tests',False),scientific=args.get('scientific',False), scientific_profile=args.get('scientific_profile','quick'), full_regressions=args.get('full_regressions',False))
                elif len(parts)==5 and parts[:3]==['api','system','diagnostics']:
                    need('GET')
                    if parts[4]=='bundle':
                        result=self.diagnostics.archive(parts[3])
                        headers.append(('Content-Disposition','attachment; filename="SQE-diagnostic-report.zip"'))
                    else: raise Problem('Unknown diagnostic endpoint',404)
                elif len(parts)==4 and parts[:3]==['api','system','diagnostics']:
                    if method=='GET': result=self.diagnostics.detail(parts[3])
                    else: need('DELETE'); result=self.diagnostics.delete(parts[3])
                else: raise Problem('Unknown diagnostic endpoint',404)
            elif path.startswith('/api/system/engines'):
                if not self.settings.development or urlsplit(self.settings.origin).hostname not in ('127.0.0.1','localhost'):
                    raise Problem('Engine setup is only available on the local workstation',403)
                if user['role'] != 'admin': raise Problem('Administrator access required',403)
                if path=='/api/system/engines':
                    need('GET')
                    if query.get('refresh') == '1': self.dependencies.invalidate()
                    result=self.dependencies.status()
                elif path=='/api/system/engines/install':
                    need('POST'); data=body()
                    if set(data)-{'engines'}: raise Problem('Unknown engine setup option')
                    result=self.dependencies.start(data.get('engines'))
                elif len(parts)==5 and parts[:4]==['api','system','engines','runs']:
                    need('GET'); result=self.dependencies.detail(parts[4])
                elif len(parts)==6 and parts[:4]==['api','system','engines','runs'] and parts[5]=='bundle':
                    need('GET'); result=self.dependencies.archive(parts[4])
                    headers.append(('Content-Disposition', 'attachment; filename="SQE-engine-setup-support.zip"'))
                else: raise Problem('Unknown engine setup endpoint',404)
            elif path.startswith('/api/system/ecosystem'):
                # Importing project input archives and launching external scientific
                # engines are intentionally local-admin-only operations.
                if not self.settings.development or urlsplit(self.settings.origin).hostname not in ('127.0.0.1','localhost'):
                    raise Problem('Experiments are available only on the local workstation',403)
                if user['role'] != 'admin': raise Problem('Administrator access required',403)
                if path=='/api/system/ecosystem':
                    need('GET'); result=self.ecosystem.catalog()
                elif path=='/api/system/ecosystem/import':
                    need('POST')
                    if env.get('CONTENT_TYPE','').split(';')[0] not in ('application/zip','application/octet-stream'):
                        raise Problem('Upload an application/zip file',415)
                    result=self.ecosystem.import_project(body(binary=True))
                elif path=='/api/system/ecosystem/preview':
                    need('GET'); result=self.ecosystem.preview(query.get('project',''))
                elif path=='/api/system/ecosystem/runs':
                    if method=='GET': result={'runs':self.ecosystem.list()}
                    else:
                        need('POST'); data=body()
                        if set(data)-{'project','allow_project_code','allow_solvers'}:
                            raise Problem('Unknown experiment run option')
                        result=self.ecosystem.start(data.get('project',''),
                          allow_project_code=data.get('allow_project_code',False),
                          allow_solvers=data.get('allow_solvers',False))
                elif len(parts) in (5,6) and parts[:4]==['api','system','ecosystem','runs']:
                    run_id=parts[4]
                    if len(parts)==5:
                        if method=='GET': result=self.ecosystem.detail(run_id)
                        else: need('DELETE'); result=self.ecosystem.delete(run_id)
                    elif parts[5]=='bundle':
                        need('GET'); result=self.ecosystem.archive(run_id)
                        headers.append(('Content-Disposition',f'attachment; filename="SQE-experiment-{run_id[:8]}.zip"'))
                    elif parts[5]=='cancel':
                        need('POST'); result=self.ecosystem.cancel(run_id)
                    else: raise Problem('Unknown experiment endpoint',404)
                else: raise Problem('Unknown experiment endpoint',404)
            elif path=='/api/system/queue':
                need('GET')
                if user['role']!='admin': raise Problem('Administrator access required',403)
                import time
                now=time.time()
                records=self.store.rows("SELECT state,created,started,heartbeat,stage FROM jobs WHERE state IN ('queued','running','cancel_requested')")
                counts={key:sum(j['state']==key for j in records) for key in ('queued','running','cancel_requested')}
                oldest_queued=max((now-j['created'] for j in records if j['state']=='queued'),default=0)
                stalled_running=sum(j['state']=='running' and
                                    (j['heartbeat'] is None or now-j['heartbeat']>35)
                                    for j in records)
                result={'counts':counts,'oldest_queued_seconds':round(oldest_queued),
                        'stale_running_heartbeats':stalled_running,
                        'queue_warning':('A job has waited in the queue for over 60 seconds. Check the worker service.'
                          if oldest_queued>60 else 'A running job has stopped sending heartbeats.' if stalled_running else ''),
                        'note':'Queue metrics are application metadata, not a proof that the solver is progressing.'}
            elif path=='/api/capabilities': result=capabilities(self.settings)
            elif path=='/api/template': result=document()
            elif path=='/api/quantumlab/preset':
                need('GET')
                from ..quantumlab import preset
                result=preset(int(query.get('size','1')))
            elif path=='/api/quantumlab/parametric-preset':
                need('GET')
                from ..parametric_qpu import default_spec
                cfg,_=resolve(document())
                result=default_spec(cfg,int(query.get('size','2')))
            elif path=='/api/palace/status':
                need('GET')
                from ..palace_bridge import readiness
                result=readiness(self.settings.palace)
            elif path=='/api/quantumlab/analyses':
                need('GET')
                from ..quantumlab import ANALYSES
                result={'analyses':ANALYSES,'backend':'local_or_remote_worker','fidelity':'reduced_order'}
            elif path=='/api/users':
                if user['role']!='admin': raise Problem('Administrator access required',403)
                if method=='GET': result=self.store.rows('SELECT id,email,name,role,active FROM users ORDER BY created')
                else:
                    need('POST'); data=body(); result=self.auth.invite(user,data['email'],data['name'],data.get('role','researcher'))
            elif len(parts)==4 and parts[:2]==['api','users'] and parts[3]=='active':
                need('POST')
                if user['role']!='admin': raise Problem('Administrator access required',403)
                data=body(); active=bool(data['active'])
                with self.store.connect(True) as db:
                    target=db.execute('SELECT * FROM users WHERE id=?',(parts[2],)).fetchone()
                    if not target: raise Problem('User not found',404)
                    admins=db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                    if not active and target['role']=='admin' and target['active'] and admins<=1: raise Problem('Keep at least one active administrator')
                    db.execute('UPDATE users SET active=? WHERE id=?',(int(active),parts[2]))
                    if not active: db.execute('DELETE FROM sessions WHERE user_id=?',(parts[2],))
                result={'active':active}
            elif path=='/api/macros':
                if method=='GET':
                    sql='SELECT * FROM macros'+('' if user['role']=='admin' else ' WHERE approved_by IS NOT NULL')+' ORDER BY created DESC'
                    result=self.store.rows(sql)
                else:
                    need('POST'); data=body(); result={'id':self.jobs.save_macro(user,data['name'],data['code'])}
            elif len(parts)==4 and parts[:2]==['api','macros'] and parts[3]=='approve':
                need('POST'); self.jobs.approve_macro(user,parts[2]); result={'approved':True}
            elif len(parts)==3 and parts[:2]==['api','source']:
                name=parts[2]
                if name not in ('geometry','circuit','em','config','experiment','workflow'): raise Problem('Unknown engine module',404)
                result={'name':name+'.py','code':(Path(__file__).parents[1]/(name+'.py')).read_text(),'editable':False}
            elif path=='/api/process/preview':
                need('POST'); cfg,p=resolve(body()['document'])
                from ..circuit import junction
                result={'positions':wafer_positions(p),'process':p,'chip_dimensions_um':[p['chip_width_um'],p['chip_height_um']],
                        'junction':junction(cfg),'EJ_GHz':cfg['circuit']['EJ_GHz']}
            elif path=='/api/projects':
                if method=='GET': result=self.projects.list(user)
                else:
                    need('POST'); data=body(); result={'id':self.projects.create(user,data['name'])}
            elif path=='/api/projects/import':
                need('POST')
                try: remaining=int(env.get('CONTENT_LENGTH','0') or 0)
                except ValueError: raise Problem('Invalid content length')
                if not 0<remaining<=self.settings.max_capsule_mb*1024**2:
                    raise Problem(f'Capsule limit is {self.settings.max_capsule_mb} MiB',413)
                # Spool to the data disk, not /tmp or a multi-gigabyte in-memory byte string.
                with tempfile.TemporaryFile(dir=self.store.root) as upload:
                    while remaining:
                        chunk=env['wsgi.input'].read(min(1024**2,remaining))
                        if not chunk: raise Problem('Incomplete request body')
                        upload.write(chunk); remaining-=len(chunk)
                    upload.seek(0)
                    result={'id':self.projects.import_capsule(user,upload)}
            elif len(parts)>=3 and parts[:2]==['api','projects']:
                pid=parts[2]
                if len(parts)==3:
                    if method=='GET': result=self.projects.detail(user,pid)
                    else:
                        need('PUT'); data=body(); result=self.projects.save(user,pid,data['document'],data['draft_version'])
                elif len(parts)==4 and parts[3]=='revisions':
                    need('POST'); data=body(); result={'id':self.projects.revise(user,pid,data.get('note','Saved from Studio'),data.get('parent_id'),data.get('draft_version'))}
                elif len(parts)==4 and parts[3]=='restore':
                    need('POST'); result=self.projects.restore(user,pid,body()['revision_id'])
                elif len(parts)==4 and parts[3]=='share':
                    need('POST'); data=body(); self.projects.share(user,pid,data['email'],data['role']); result={'updated':True}
                elif len(parts)==4 and parts[3]=='assets':
                    need('PUT'); result={'id':self.projects.asset(user,pid,query.get('name','asset'),query.get('kind','data'),body(True))}
                elif len(parts)==5 and parts[3:] == ['quantum-metal','manifest']:
                    need('GET')
                    from ..qmetal_interop import manifest
                    cfg,_=resolve(self.projects.detail(user,pid)['document'])
                    result=manifest(cfg)
                    headers.append(('Content-Disposition','attachment; filename="sqe-qmetal-qgeometry.json"'))
                elif len(parts)==5 and parts[3] == 'physical' and parts[4] in ('preview','manifest','gds'):
                    need('GET')
                    from .. import physical_qpu
                    current=self.projects.detail(user,pid)['document']
                    cfg,_=resolve(current)
                    spec=current.get('physical_qpu') or physical_qpu.default_spec(cfg)
                    geom=physical_qpu.build(cfg,spec)
                    if parts[4]=='preview':
                        result={'geometry':geom,'spec':spec,'nominal_circuit':physical_qpu.circuit(cfg,spec),
                                'contract':{'geometry_sha256':geom['geometry_sha256'],
                                            'design_spec_sha256':geom['design_spec_sha256'],
                                            'conductor_count':len(geom['terminals']),
                                            'rf_port_count':len(geom['feed_ports'])},
                                'fidelity':'geometry_exact__circuit_user_declared_nominal',
                                'fabrication_status':'HOLD'}
                    elif parts[4]=='manifest':
                        result=physical_qpu.qmetal_manifest(geom)
                        headers.append(('Content-Disposition','attachment; filename="physical-qgeometry.json"'))
                    else:
                        import uuid
                        target=self.store.root/'exports'/(uuid.uuid4().hex+'-PHYSICAL_HOLD.gds')
                        target.parent.mkdir(parents=True,exist_ok=True)
                        physical_qpu.export_gds(geom,target)
                        result=target
                        headers.append(('Content-Disposition','attachment; filename="SQE_PHYSICAL_HOLD.gds"'))
                        headers.append(('X-Design-Status','research-prototype-not-fabrication-ready'))
                elif len(parts)==5 and parts[3:] == ['palace','preview']:
                    need('GET')
                    from ..geometry import build
                    current=self.projects.detail(user,pid)['document']
                    cfg,_=resolve(current)
                    geom=build(cfg)
                    result={'geometry':geom,'em':cfg['em'],'materials':cfg['materials'],
                            'source':'parametric_fem_geometry',
                            'separate_from_quantum_lab_netlist':True,
                            'fabrication_status':'HOLD'}
                elif len(parts)==5 and parts[3:] == ['quantumlab','gds']:
                    need('GET')
                    from ..quantumlab import preset
                    from ..lab_layout import candidate
                    project=self.projects.access(user,pid)
                    design=json.loads(project['draft']).get('quantum_lab') or preset(1)
                    output=self.store.root/'exports'/(pid+'-QPU_CONCEPT.gds')
                    candidate(design,output)
                    result=output
                    headers.append(('Content-Disposition','attachment; filename=QPU_CONCEPT_NOT_FABRICATION_READY.gds'))
                    headers.append(('X-Design-Status','concept-only-not-mask-qualified'))
                elif len(parts)==4 and parts[3]=='export':
                    need('GET'); result=self.projects.export(user,pid); headers.append(('Content-Disposition','attachment; filename="sqe-project.zip"'))
                elif len(parts)==4 and parts[3]=='readiness':
                    result=self.jobs.readiness(user,pid,query.get('mode','demo'))
                elif len(parts)==4 and parts[3]=='jobs':
                    need('POST'); data=body()
                    result={'id':self.jobs.enqueue(user,pid,data['revision_id'],data['target'],data.get('mode','demo'),
                           data.get('cpus',1),data.get('memory_gb',2),data.get('baseline_id'),data.get('options'))}
                elif len(parts)>=5 and parts[3]=='jobs':
                    job=self.store.one('SELECT * FROM jobs WHERE id=? AND project_id=?',(parts[4],pid))
                    self.projects.access(user,pid)
                    if not job: raise Problem('Job not found',404)
                    folder=self.store.root/'jobs'/job['id']
                    if len(parts)==5:
                        files=list(islice((f.relative_to(folder).as_posix() for f in folder.rglob('*')
                                           if f.is_file() and not f.is_symlink()),2001)) if folder.exists() else []
                        result={'job':job,'files':files[:2000],'files_truncated':len(files)>2000}
                    elif len(parts)==6 and parts[5]=='bundle':
                        need('GET')
                        # All project members with read permission can export
                        # the corresponding job's bounded support bundle.
                        result=create_support_bundle(folder/'SQE-job-support.zip',folder,
                            category='studio-job',job=job)
                        headers.append(('Content-Disposition',
                          'attachment; filename="SQE-job-'+job['id'][:8]+'-support.zip"'))
                    elif parts[5]=='logs':
                        path=folder/'worker.log'
                        if path.exists():
                            with path.open('rb') as stream:
                                stream.seek(max(0,path.stat().st_size-65536)); text=stream.read().decode('utf-8','replace')
                        else: text='Waiting for a worker…'
                        if job['stage'] in ('solve:electrostatic','solve:eigenmode','solve:driven'):
                            native=folder/'run'/'em'/(job['stage'].split(':')[1]+'.log')
                            if native.is_file():
                                with native.open('rb') as stream:
                                    stream.seek(max(0,native.stat().st_size-65536))
                                    text+='\n\nPalace solver log:\n'+stream.read().decode('utf-8','replace')
                        result={'text':text}
                    elif parts[5]=='files' and len(parts)>=7:
                        relative='/'.join(parts[6:]); candidate=folder/relative
                        if not candidate.resolve().is_relative_to(folder.resolve()) or not candidate.is_file() or candidate.is_symlink(): raise Problem('Artifact not found',404)
                        result=candidate
                        if query.get('download')=='1' or candidate.suffix not in ('.png','.jpg','.jpeg','.html','.json','.txt','.csv','.log','.py'):
                            headers.append(('Content-Disposition','attachment; filename="'+re.sub(r'[^a-zA-Z0-9_.-]','_',candidate.name)+'"'))
                        if candidate.suffix=='.html': headers.append(('Content-Security-Policy',"sandbox allow-same-origin; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"))
                    else: raise Problem('Route not found',404)
                else: raise Problem('Route not found',404)
            elif len(parts)==4 and parts[:2]==['api','jobs']:
                need('POST')
                if parts[3]=='cancel': self.jobs.cancel(user,parts[2]); result={'requested':True}
                elif parts[3]=='consolidate':
                    data=body(); self.jobs.consolidate(user,parts[2],data['stage'],data.get('notes','')); result={'consolidated':True}
                else: raise Problem('Route not found',404)
            elif not path.startswith('/api/'):
                filename=path.lstrip('/') or 'index.html'
                if filename not in ('index.html','app.js','styles.css','mark.svg','quantumlab.html','quantumlab.js','quantumlab.css','control.html','control.js','control.css','experiments.html','experiments.js','experiments.css','editor.html','workspace.js','workspace.css'): raise Problem('Not found',404)
                result=STATIC/filename
            else: raise Problem('Route not found',404)
        except Problem as exc: status=exc.status; result={'error':str(exc)}
        except (KeyError,ValueError,TypeError,zipfile.BadZipFile,json.JSONDecodeError) as exc: status=400; result={'error':str(exc)}
        except Exception:
            import traceback
            traceback.print_exc()
            status=500; result={'error':'The operation failed. The server log contains diagnostic details.'}
        headers += [('X-Content-Type-Options','nosniff'),('Referrer-Policy','same-origin'),
                    ('X-Frame-Options','SAMEORIGIN'),('Cache-Control','no-store')]
        if not any(k=='Content-Security-Policy' for k,v in headers):
            headers.append(('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"))
        if isinstance(result,Path):
            headers += [('Content-Type',mimetypes.guess_type(result.name)[0] or 'application/octet-stream'),('Content-Length',str(result.stat().st_size))]
            payload=FileBody(result)
        else:
            data=json.dumps(result,allow_nan=False).encode()
            headers += [('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(data)))]
            payload=[data]
        from http import HTTPStatus
        start_response(f'{status} {HTTPStatus(status).phrase}',headers)
        return payload

    def cookie(self,token,age=None):
        return f'sqe_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age if age is not None else self.settings.session_hours*3600}'+('' if self.settings.development else '; Secure')


def create_app(): return Application(Settings.from_env())
