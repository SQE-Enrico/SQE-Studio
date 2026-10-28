"""Durable queue, resource admission and immutable per-job workspaces."""
import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .auth import Problem
from .catalog import DEMO,FEM,blockers,signature
from .db import dumps,uid
from .projects import Projects


class Jobs:
    def __init__(self,store):
        self.store=store; self.projects=Projects(store)

    def enqueue(self,user,project_id,revision_id,target,mode='demo',cpus=1,memory_gb=2,baseline_id=None,options=None):
        self.projects.access(user,project_id,True)
        rev=self.store.one('SELECT * FROM revisions WHERE id=? AND project_id=?',(revision_id,project_id))
        if not rev: raise Problem('Save a revision before running a simulation')
        if mode not in ('demo','fem','lab','physical'): raise Problem('Invalid workflow mode')
        doc=json.loads(rev['document']); options=options or {}
        if type(cpus) is not int or not 1<=cpus<=self.store.settings.total_cpus: raise Problem('Requested CPU count exceeds server capacity')
        if type(memory_gb) is not int or not 1<=memory_gb<=self.store.settings.total_memory_gb: raise Problem('Requested memory exceeds server capacity')
        if baseline_id and not self.store.one('SELECT id FROM jobs WHERE id=? AND project_id=? AND state IN (?,?,?,?)',
                (baseline_id,project_id,'succeeded','failed','cancelled','interrupted')):
            raise Problem('Choose a finalized checkpoint from this project')
        if mode=='lab':
            from ..quantumlab import ANALYSES, preset, validate
            if target not in ('lab:'+name for name in ANALYSES):
                raise Problem('Unknown Quantum Design Lab analysis')
            validate(doc.get('quantum_lab') or preset(1))
            requested=options.get('analysis_options',{})
            if not isinstance(requested,dict) or len(requested)>20: raise Problem('Invalid lab options')
            options={'analysis_options':requested}
        elif mode=='physical':
            from ..physical_qpu import SIZES, default_spec, validate_spec, build
            from .process import resolve
            from ..palace_bridge import readiness
            cfg,_=resolve(doc)
            spec=doc.get('physical_qpu') or default_spec(cfg)
            validate_spec(spec)
            build(cfg,spec)
            allowed={'physical:package','physical:mesh','physical:electrostatic',
                     'physical:eigenmode','physical:driven','physical:capacitance',
                     'physical:convergence-eigenmode','physical:convergence-electrostatic'}
            if target not in allowed: raise Problem('Unknown physical design stage')
            import importlib.util
            if target!='physical:package' and importlib.util.find_spec('gmsh') is None:
                raise Problem('Gmsh not installed on this worker',422)
            if target not in ('physical:package','physical:mesh') and not readiness(self.store.settings.palace).get('installed'):
                raise Problem('Palace solver not installed on this worker',422)
            options={'ranks':min(cpus,max(1,int(options.get('ranks',1))))}
        elif target.startswith('macro:'):
            macro=self.store.one('SELECT * FROM macros WHERE id=? AND approved_by IS NOT NULL',(target.split(':',1)[1],))
            if not macro: raise Problem('Choose an administrator-reviewed macro')
            options={'macro':macro}
        else:
            if target not in (FEM if mode=='fem' else DEMO): raise Problem('Unknown workflow stage')
            errors=blockers(target,doc,mode,self.store.settings)
            if errors: raise Problem('; '.join(errors),422)
            # Launcher paths are server configuration, never a client-controlled command.
            options={'ranks':min(cpus,max(1,int(options.get('ranks',1))))}
        job_id=uid()
        with self.store.connect(True) as db:
            db.execute('INSERT INTO jobs(id,project_id,revision_id,author_id,target,mode,state,cpus,memory_gb,baseline_id,options,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (job_id,project_id,revision_id,user['id'],target,mode,'queued',cpus,memory_gb,baseline_id,dumps(options),time.time()))
        self.store.audit(user['id'],project_id,'enqueue',{'job':job_id,'target':target,'revision':revision_id})
        return job_id

    def cancel(self,user,job_id):
        job=self.store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
        if not job: raise Problem('Job not found',404)
        self.projects.access(user,job['project_id'],True)
        with self.store.connect(True) as db:
            db.execute("UPDATE jobs SET state='cancelled',finished=? WHERE id=? AND state='queued'",(time.time(),job_id))
            db.execute("UPDATE jobs SET state='cancel_requested' WHERE id=? AND state='running'",(job_id,))
        self.store.audit(user['id'],job['project_id'],'cancel_job',{'job':job_id})

    def consolidate(self,user,job_id,stage,notes=''):
        job=self.store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
        if not job: raise Problem('Job not found',404)
        self.projects.access(user,job['project_id'],True)
        if job['state'] not in ('succeeded','failed','interrupted','cancelled'): raise Problem('Wait until the job is finalized')
        if stage.startswith('physical:'):
            from ..io import sha256
            folder=self.store.root/'jobs'/job_id/'physical'
            if not (folder/'result.sha256').is_file() or (folder/'result.sha256').read_text().strip()!=sha256(folder/'result.json'):
                raise Problem('Physical job checksum mismatch',422)
        elif stage.startswith('lab:'):
            from ..io import sha256
            folder=self.store.root/'jobs'/job_id/'lab'
            manifest=folder/'result.sha256'
            if not manifest.is_file() or manifest.read_text().strip()!=sha256(folder/'result.json'):
                raise Problem('Quantum Lab result checksum mismatch',422)
        elif stage!='fabrication':
            from ..provenance import check_stage
            from ..io import read_json
            run=self.store.root/'jobs'/job_id/'run'
            check_stage(read_json(run/'run.json'),stage,run)
        with self.store.connect(True) as db:
            cur=db.execute('UPDATE results SET consolidated_by=?,consolidated_at=?,notes=? WHERE job_id=? AND stage=?',
                           (user['id'],time.time(),str(notes)[:4000],job_id,stage))
            if cur.rowcount!=1: raise Problem('This stage has no completed result')
        self.store.audit(user['id'],job['project_id'],'consolidate',{'job':job_id,'stage':stage})

    def readiness(self,user,project_id,mode='demo'):
        p=self.projects.access(user,project_id); doc=json.loads(p['draft'])
        result=[]
        jobs=self.store.rows('SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC',(project_id,))
        for stage in FEM if mode=='fem' else DEMO:
            issues=blockers(stage,doc,mode,self.store.settings)
            try: sig=signature(stage,doc,mode)
            except Exception: sig=None
            found=None; old=False; active=None
            for job in jobs:
                r=self.store.one('SELECT * FROM results WHERE job_id=? AND stage=?',(job['id'],stage))
                if r:
                    old=True
                    if r['signature']==sig and found is None:
                        found={**r,'state':job['state']}
                        if r['consolidated_by']:
                            actor=self.store.one('SELECT name FROM users WHERE id=?',(r['consolidated_by'],))
                            found['reviewer_name']=actor['name'] if actor else 'Imported reviewer'
                if job['state'] in ('running','queued','cancel_requested') and job['target']==stage: active=job['state']
            status=active or ('consolidated' if found and found['consolidated_by'] else 'computed' if found else 'stale' if old else 'blocked' if issues else 'ready')
            result.append({'stage':stage,'state':status,'blockers':issues,'result':found})
        return result

    def save_macro(self,user,name,code):
        if user['role']!='admin': raise Problem('Only administrators may install worker code',403)
        if len(code)>100_000: raise Problem('Macro source is too large')
        try: tree=ast.parse(code)
        except SyntaxError as exc: raise Problem(f'Python syntax: {exc}') from exc
        if not any(isinstance(n,ast.FunctionDef) and n.name=='apply' for n in tree.body):
            raise Problem('Define apply(project), returning a project document')
        from ..io import digest
        macro_id=uid()
        with self.store.connect(True) as db:
            db.execute('INSERT INTO macros VALUES(?,?,?,?,?,?,?)',(macro_id,str(name)[:100],code,digest(code),user['id'],None,time.time()))
        self.store.audit(user['id'],None,'draft_macro',{'macro':macro_id})
        return macro_id

    def approve_macro(self,user,macro_id):
        if user['role']!='admin': raise Problem('Administrator access required',403)
        with self.store.connect(True) as db:
            if db.execute('UPDATE macros SET approved_by=? WHERE id=?',(user['id'],macro_id)).rowcount!=1: raise Problem('Macro not found',404)
        self.store.audit(user['id'],None,'approve_macro',{'macro':macro_id})


class Scheduler:
    def __init__(self,store):
        self.store=store; self.children={}; self.lock=None

    def acquire(self):
        self.lock=(self.store.root/'scheduler.lock').open('a+b')
        if os.name=='nt':
            import msvcrt
            self.lock.seek(0,2)
            if self.lock.tell()==0:
                self.lock.write(b'0');self.lock.flush()
            self.lock.seek(0)
            try: msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc: raise RuntimeError('Exactly one scheduler may own this data directory') from exc
        else:
            import fcntl
            try: fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise RuntimeError('Exactly one scheduler may own this data directory') from exc
        # A scheduler crash must not start duplicate MPI jobs. A fresh runner heartbeat
        # keeps its reservation until it exits or becomes stale.

    @staticmethod
    def terminate_tree(proc):
        if proc.poll() is not None: return
        if os.name=='nt':
            # Terminate child Palace/MPI processes too; the PID is spawned by our own scheduler.
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            if proc.poll() is None: proc.terminate()
        else:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass

    def tick(self):
        now=time.time()
        for job_id,proc in list(self.children.items()):
            state=self.store.one('SELECT state FROM jobs WHERE id=?',(job_id,))
            if state and state['state']=='cancel_requested' and proc.poll() is None:
                self.terminate_tree(proc)
            code=proc.poll()
            if code is not None:
                with self.store.connect(True) as db:
                    db.execute("UPDATE jobs SET state=CASE WHEN state='cancel_requested' THEN 'cancelled' ELSE 'interrupted' END,finished=?,error=COALESCE(error,?) WHERE id=? AND state IN ('running','cancel_requested')",(now,f'Worker exited with code {code}',job_id))
                del self.children[job_id]
        with self.store.connect(True) as db:
            db.execute("UPDATE jobs SET state='interrupted',finished=?,error='Worker heartbeat expired; resume from a completed checkpoint' WHERE state IN ('running','cancel_requested') AND COALESCE(heartbeat,started)<?",(now,now-90))
            live=db.execute("SELECT COUNT(*) n,COALESCE(SUM(cpus),0) cpu,COALESCE(SUM(memory_gb),0) mem FROM jobs WHERE state IN ('running','cancel_requested')").fetchone()
            for row in db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created").fetchall():
                if live['n']>=self.store.settings.max_jobs: break
                if live['cpu']+row['cpus']>self.store.settings.total_cpus or live['mem']+row['memory_gb']>self.store.settings.total_memory_gb: continue
                db.execute("UPDATE jobs SET state='running',started=?,heartbeat=? WHERE id=? AND state='queued'",(now,now,row['id']))
                job=dict(row)
                break
            else: job=None
            if live['n']>=self.store.settings.max_jobs: job=None
        if job is not None:
            folder=self.store.root/'jobs'/job['id']; folder.mkdir(parents=True,exist_ok=True)
            env=os.environ.copy()
            threads=max(1,job['cpus']//max(1,json.loads(job['options']).get('ranks',1)))
            for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): env[name]=str(threads)
            env.update(SQE_DATA=str(self.store.root),SQE_ORIGIN=self.store.settings.origin,
                       SQE_DEVELOPMENT='1' if self.store.settings.development else '0',SQE_PALACE=self.store.settings.palace)
            with (folder/'worker.log').open('ab') as log:
                proc=subprocess.Popen([sys.executable,'-m','sqw.studio.runner',job['id']],stdout=log,stderr=subprocess.STDOUT,
                                      env=env,**({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
                                                    if os.name=='nt' else {'start_new_session':True}))
            self.children[job['id']]=proc
            with self.store.connect(True) as db: db.execute('UPDATE jobs SET pid=? WHERE id=?',(proc.pid,job['id']))
            return job['id']
        return None

    def run(self):
        self.acquire()
        try:
            while True:
                self.tick(); time.sleep(.5)
        finally:
            # Terminate process groups so the service does not leave unmanaged Palace children.
            for proc in self.children.values():
                if proc.poll() is None:
                    self.terminate_tree(proc)


def main():
    from .settings import Settings
    from .db import Store
    def shutdown(signum,frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,shutdown)
    try: Scheduler(Store(Settings.from_env())).run()
    except KeyboardInterrupt: pass


if __name__=='__main__': main()
