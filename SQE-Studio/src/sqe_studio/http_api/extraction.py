"""Extraction; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.interop.extracted_transmon import build_extraction
from sqe_studio.interop.extracted_transmon import resolve_source as resolve_extraction_source
from sqe_studio.interop.extracted_transmon import study_template as extraction_study_template
from sqe_studio.orchestration.artifacts import ArtifactInvalid
from sqe_studio.store import Conflict
import copy

def extract(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if (set(obj)!={'expected_revision','action','declaration'} or
            obj['action'] not in ('preview','execute')):
        raise ApiError('Extraction needs expected revision, preview/execute and conditional assumptions',422)
    project=self.app.store.project(uid,pid)
    if project['head']!=obj['expected_revision']:
        raise ApiError('Project revision changed; reload before extraction',409)
    try:
        context=resolve_extraction_source(self.app.store,uid,pid,project,parts[4])
        template=extraction_study_template(context,obj['declaration'])
        preview=build_extraction(template['inputs'],project['model'],context)
    except (ValueError,ArtifactInvalid,OSError,KeyError,TypeError,EngineBlocked) as exc:
        raise ApiError('Conditional extraction blocked: '+str(exc)[:300],409) from None
    if obj['action']=='preview':
        return self.send_json({'schema':'sqe.extraction-preview.m19.v1',
            'expected_revision':project['head'],'extraction':preview,
            'solver_execution':'NOT_EXECUTED'})
    model=copy.deepcopy(project['model'])
    ids={s['id'] for s in model['studies']}
    sid=next((f'extracted_transmon_{n:02d}' for n in range(1,31)
              if f'extracted_transmon_{n:02d}' not in ids),None)
    if sid is None or len(model['studies'])>=30:
        raise ApiError('Project study capacity reached',422)
    model['studies'].append({'id':sid,**template})
    revision=self.app.store.commit(uid,pid,obj['expected_revision'],model)
    try:
        run_id=self.app.jobs.start(uid,pid,revision,sid)
    except (ValueError,Conflict,ArtifactInvalid,OSError,EngineBlocked) as exc:
        return self.send_json({'schema':'sqe.extraction-execution.m19.v1',
            'status':'SAVED_JOB_NOT_QUEUED','revision':revision,'study_id':sid,
            'reason':str(exc)[:300],'extraction':preview,'fabrication':'HOLD'},202)
    return self.send_json({'schema':'sqe.extraction-execution.m19.v1',
        'status':'CONDITIONAL_NATIVE_JOB_QUEUED','revision':revision,
        'study_id':sid,'run_id':run_id,'extraction':preview,
        'scientific_qualification':'NOT_ESTABLISHED','fabrication':'HOLD'},202)

