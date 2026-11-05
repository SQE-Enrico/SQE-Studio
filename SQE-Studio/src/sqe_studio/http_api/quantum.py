"""Quantum; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import HEX_ID
from sqe_studio.interop.independent_transmon_execution import IndependentTransmonExecutionBlocked
from sqe_studio.interop.independent_transmon_execution import REQUEST_SCHEMA
from sqe_studio.interop.independent_transmon_execution import build_independent_transmon_execution_preflight
from sqe_studio.interop.independent_transmon_origin import ManualOriginBlocked
from sqe_studio.interop.independent_transmon_origin import record_manual_study_creation
from sqe_studio.interop.independent_transmon_origin import require_manual_study_creation
from sqe_studio.interop.transmon_quantum_preflight import TransmonPreflightBlocked
from sqe_studio.interop.transmon_quantum_preflight import build_independent_transmon_preflight
import copy

def declare_independent(self,request):
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if set(obj)!={'expected_revision','declaration','acknowledged'} or obj['acknowledged'] is not True:
        raise ApiError('Manual declaration requires exact fields and an explicit research acknowledgment',422)
    expected=obj['expected_revision']
    if type(expected) is not str or not HEX_ID.fullmatch(expected):
        raise ApiError('Invalid expected project revision',422)
    project=self.app.store.project(uid,pid)
    if project['head']!=expected:
        raise ApiError('Project revision changed; reload before saving research inputs',409)
    if project['model']['family'] not in ('transmon','multi_qubit'):
        raise ApiError('Manual transmon study requires a transmon design family',422)
    try:
        preflight=build_independent_transmon_preflight(obj['declaration'])
    except TransmonPreflightBlocked as exc:
        raise ApiError('Independent transmon declaration blocked: '+exc.code,422) from None
    model=copy.deepcopy(project['model'])
    ids={study['id'] for study in model['studies']}
    study_id=next((f'independent_transmon_{n:02d}' for n in range(1,31)
                   if f'independent_transmon_{n:02d}' not in ids),None)
    if not study_id or len(model['studies'])>=30:
        raise ApiError('Project study capacity reached',422)
    study={'id':study_id,**preflight['study_template']}
    model['studies'].append(study)
    revision=self.app.store.commit(uid,pid,expected,model)
    record_manual_study_creation(self.app.store,uid,pid,revision,study_id)
    return self.send_json({
        'schema':'sqe.independent-transmon-saved-research.a99.v1',
        'revision':revision,'study_id':study_id,
        'status':'SAVED_UNVERIFIED_INDEPENDENT_RESEARCH_STUDY',
        'parameter_provenance':'UNVERIFIED_DESIGNER_DECLARATION_ONLY',
        'scientific_authorization':'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION',
        'em_ec_transfer':'BLOCKED','em_to_hamiltonian':'BLOCKED',
        'solver_execution':'NOT_EXECUTED','fabrication':'HOLD',
    },201)


def independent_execution(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if set(obj)!={'schema','project_id','expected_revision','study_id'}:
        raise ApiError('Exact independent study selector required',422)
    if obj.get('project_id')!=pid or obj.get('schema')!=REQUEST_SCHEMA:
        raise ApiError('Independent study identity/schema mismatch',422)
    try:
        trusted=require_manual_study_creation(
            self.app.store,uid,pid,obj['expected_revision'],obj['study_id'])
        plan=build_independent_transmon_execution_preflight(
            obj,trusted_revision=trusted)
    except (ManualOriginBlocked,IndependentTransmonExecutionBlocked) as exc:
        raise ApiError('Independent study execution blocked: '+getattr(exc,'code','UNTRUSTED_ORIGIN'),409) from None
    if parts[4]=='preflight':
        return self.send_json(plan)
    run_id=self.app.jobs.start(uid,pid,obj['expected_revision'],obj['study_id'])
    return self.send_json({
        'schema':'sqe.independent-transmon-execution-response.a99.v1',
        'status':'NATIVE_JOB_QUEUED_OR_CACHED',
        'run_id':run_id,'revision':trusted['revision'],
        'study_id':obj['study_id'],
        'scientific_authorization':'BLOCKED',
        'em_ec_transfer':'BLOCKED','fabrication':'HOLD',
    },202)

