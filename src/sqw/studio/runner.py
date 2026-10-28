"""One job per subprocess. Browser disconnection never owns or stops a job."""
import copy
import json
import os
from pathlib import Path
import signal
import shutil
import sys
import threading
import time

from .. import __version__, provenance, workflow
from ..io import digest,environment,read_json,sha256,write_json
from .catalog import FEM,plan,signature
from .db import Store
from .process import export as export_process,resolve
from .settings import Settings


def seed(store,job,doc,run):
    if not job['baseline_id']: return {}
    base=store.one('SELECT * FROM jobs WHERE id=? AND project_id=?',(job['baseline_id'],job['project_id']))
    if not base: raise ValueError('Checkpoint does not belong to this project')
    source=store.root/'jobs'/base['id']/'run'
    if not (source/'run.json').exists(): return {}
    old=read_json(source/'run.json')
    results={r['stage']:r for r in store.rows('SELECT * FROM results WHERE job_id=?',(base['id'],))}
    kept={}
    for stage in FEM:
        if stage=='fabrication': continue
        record=old.get('stage_records',{}).get(stage)
        if not record or stage not in results or results[stage]['signature']!=signature(stage,doc,job['mode']): continue
        if not all(parent in kept for parent in record.get('parents',[])): continue
        provenance.check_stage(old,stage,source)
        kept[stage]=copy.deepcopy(record)
        for relative in record['outputs']:
            f=source/relative
            if not f.resolve().is_relative_to(source.resolve()) or f.is_symlink(): raise ValueError('Unsafe checkpoint artifact')
            dest=run/relative; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,dest)
        if stage.startswith('solve:'):
            folder=stage.split(':',1)[1]
            src=source/'em'/folder
            if src.exists(): shutil.copytree(src,run/'em'/folder,dirs_exist_ok=True)
    if not kept: return {}
    cfg,_=resolve(doc)
    run.mkdir(parents=True,exist_ok=True)
    write_json(run/'resolved_config.json',cfg)
    config_hash=sha256(run/'resolved_config.json')
    for stage,record in kept.items():
        if 'resolved_config.json' in record['inputs']: record['inputs']['resolved_config.json']=config_hash
        record['reused_from']={'job':base['id'],'run_sha256':sha256(source/'run.json'),
                               'stage_signature':results[stage]['signature']}
    state={'schema_version':1,'software_version':__version__,'config_sha256':digest(cfg),
           'environment':environment(),'stages':{s:'completed' for s in kept},'stage_records':kept,
           'physics_source':old.get('physics_source'),'fabrication_status':'HOLD'}
    write_json(run/'run.json',state)
    workflow.manifest(run)
    return {stage:base['id'] for stage in kept}


def execute(store,job_id):
    job=store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not job: raise ValueError('Unknown job')
    rev=store.one('SELECT * FROM revisions WHERE id=?',(job['revision_id'],))
    doc=json.loads(rev['document']); options=json.loads(job['options'])
    folder=store.root/'jobs'/job_id; folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'input.json',{'document':doc,'revision_id':job['revision_id'],'options':options,
                                  'software_version':__version__,'environment':environment()})
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(2):
            state=store.one('SELECT state FROM jobs WHERE id=?',(job_id,))
            if state and state['state'] in ('cancel_requested','interrupted'):
                if os.name=='posix' and os.getpgrp()==os.getpid(): os.killpg(os.getpgrp(),signal.SIGTERM)
                else: os.kill(os.getpid(),signal.SIGTERM)
                return
            if state and state['state'] not in ('running','queued'): return
            with store.connect(True) as db: db.execute('UPDATE jobs SET heartbeat=? WHERE id=?',(time.time(),job_id))
    thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
    def interrupted(signum,frame): raise InterruptedError('Job cancelled or service stopped')
    previous_handler=None
    if threading.current_thread() is threading.main_thread(): previous_handler=signal.signal(signal.SIGTERM,interrupted)
    try:
        if job['mode']=='physical':
            from ..physical_qpu import default_spec, run_workflow
            cfg,_=resolve(doc)
            spec=doc.get('physical_qpu') or default_spec(cfg)
            phase=job['target'].split(':',1)[1]
            with store.connect(True) as db:
                db.execute('UPDATE jobs SET stage=?,progress=?,heartbeat=? WHERE id=?',
                           (job['target'],0.1,time.time(),job_id))
            output=folder/'physical'
            print('Unified physical QPU / '+phase,flush=True)
            result=run_workflow(cfg,spec,phase,output,ranks=options.get('ranks',1),executable=store.settings.palace)
            result['provenance']={'software_version':__version__,
                'source_sha256':sha256(Path(__file__).parents[1]/'physical_qpu.py'),
                'revision_id':job['revision_id'],'spec_sha256':digest(spec),
                'solver_required':phase not in ('package','mesh')}
            write_json(output/'result.json',result)
            (output/'result.sha256').write_text(sha256(output/'result.json')+'\n',encoding='ascii')
            with store.connect(True) as db:
                db.execute('INSERT OR REPLACE INTO results(job_id,stage,signature,reused_from) VALUES(?,?,?,?)',
                           (job_id,job['target'],digest({'physical':spec,'config':cfg,'stage':phase,
                            'software_version':__version__}),None))
        elif job['mode']=='lab':
            from ..quantumlab import analyze, preset
            design=doc.get('quantum_lab') or preset(1)
            phase=job['target'].split(':',1)[1]
            with store.connect(True) as db:
                db.execute('UPDATE jobs SET stage=?,progress=?,heartbeat=? WHERE id=?',
                           (job['target'],0.2,time.time(),job_id))
            print(f'Quantum Lab / {phase} / reduced-order solver',flush=True)
            started=time.monotonic()
            result=analyze(design,phase,options.get('analysis_options',{}))
            result['provenance']={'engine':'sqw.quantumlab','software_version':__version__,
                'source_sha256':sha256(Path(__file__).parents[1]/'quantumlab.py'),
                'design_sha256':digest(design), 'analysis_options':options.get('analysis_options',{}),
                'elapsed_seconds':round(time.monotonic()-started,5),
                'revision_id':job['revision_id'],'fidelity_tier':result['fidelity']}
            lab=folder/'lab'; lab.mkdir(exist_ok=True)
            touchstone=result.pop('touchstone',None)
            if touchstone:
                suffix='s'+str(len(design.get('ports',[])))+'p'
                (lab/('network.'+suffix)).write_text(touchstone,encoding='ascii')
                result['touchstone_file']='network.'+suffix
            write_json(lab/'result.json',result)
            (lab/'result.sha256').write_text(sha256(lab/'result.json')+'\n')
            with store.connect(True) as db:
                db.execute('INSERT OR REPLACE INTO results(job_id,stage,signature,reused_from) VALUES(?,?,?,?)',
                    (job_id,job['target'],digest({'lab':design,'phase':phase,'options':options,
                      'source_sha256':result['provenance']['source_sha256'],
                      'software_version':__version__}),None))
        elif job['target'].startswith('macro:'):
            macro=options['macro']
            if digest(macro['code'])!=macro['sha256']: raise ValueError('Macro source checksum mismatch')
            artifacts=folder/'macro_artifacts'; artifacts.mkdir(exist_ok=True)
            namespace={'__name__':'sqe_trusted_macro','ARTIFACTS_DIR':str(artifacts.resolve())}
            (folder/'macro.py').write_text(macro['code'])
            exec(compile(macro['code'],str(folder/'macro.py'),'exec'),namespace)
            result=namespace['apply'](copy.deepcopy(doc))
            resolve(result)
            write_json(folder/'macro_result.json',result)
        else:
            cfg,p=resolve(doc)
            run=folder/'run'
            reused=seed(store,job,doc,run)
            stages=plan(job['target'],job['mode'])
            for index,stage in enumerate(stages):
                current=store.one('SELECT state FROM jobs WHERE id=?',(job_id,))
                if current['state']=='cancel_requested': raise InterruptedError('Cancelled by user')
                with store.connect(True) as db: db.execute('UPDATE jobs SET stage=?,progress=?,heartbeat=? WHERE id=?',(stage,index/len(stages),time.time(),job_id))
                print(f'[{index+1}/{len(stages)}] {stage}'+(' (reused)' if stage in reused else ''),flush=True)
                if stage not in reused:
                    if stage=='fabrication':
                        asset=None
                        if p['logo_asset_id']:
                            record=store.one('SELECT * FROM assets WHERE id=? AND project_id=?',(p['logo_asset_id'],job['project_id']))
                            if not record: raise ValueError('Logo asset is not part of this project')
                            asset=store.root/'assets'/job['project_id']/record['id']
                            if sha256(asset)!=record['sha256']: raise ValueError('Logo checksum mismatch')
                        junction=None
                        if p['junction_kind']=='lab_gds':
                            record=store.one('SELECT * FROM assets WHERE id=? AND project_id=? AND kind=?',(p['junction_asset_id'],job['project_id'],'junction_gds'))
                            if not record: raise ValueError('Select a junction GDS from this project')
                            junction=store.root/'assets'/job['project_id']/record['id']
                            if sha256(junction)!=record['sha256']: raise ValueError('Junction cell checksum mismatch')
                        export_process(doc,run,folder/'fabrication',asset,junction)
                    else:
                        name,_,problem=stage.partition(':')
                        if stage.startswith('solve:'): name='solve'
                        workflow.stage(name,cfg,run,cad_backend=doc.get('backends',{}).get('cad','native'),
                          quantum_backend=doc.get('backends',{}).get('quantum','scipy'),
                          dynamics_backend=doc.get('backends',{}).get('dynamics','scipy'),
                          palace=store.settings.palace,ranks=options.get('ranks',1),problem=problem or 'electrostatic',
                          readout_mode=doc.get('readout_mode'))
                with store.connect(True) as db:
                    db.execute('INSERT OR REPLACE INTO results(job_id,stage,signature,reused_from) VALUES(?,?,?,?)',
                               (job_id,stage,signature(stage,doc,job['mode']),reused.get(stage)))
        with store.connect(True) as db:
            state=db.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()['state']
            final='cancelled' if state=='cancel_requested' else 'succeeded'
            db.execute('UPDATE jobs SET state=?,progress=1,finished=?,heartbeat=? WHERE id=?',(final,time.time(),time.time(),job_id))
    except BaseException as exc:
        state=store.one('SELECT state FROM jobs WHERE id=?',(job_id,))
        final='cancelled' if state and state['state']=='cancel_requested' else 'interrupted' if isinstance(exc,InterruptedError) else 'failed'
        with store.connect(True) as db: db.execute('UPDATE jobs SET state=?,error=?,finished=? WHERE id=?',(final,str(exc),time.time(),job_id))
        print(f'{final}: {exc}',flush=True)
        if not isinstance(exc,InterruptedError): raise
    finally:
        stop.set(); thread.join(timeout=3)
        if previous_handler is not None: signal.signal(signal.SIGTERM,previous_handler)


if __name__=='__main__': execute(Store(Settings.from_env()),sys.argv[1])
