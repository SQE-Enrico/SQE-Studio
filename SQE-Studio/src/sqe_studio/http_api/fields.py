"""Fields; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import HEX_ID
from .common import MAX_RESULT_JSON
from sqe_studio.orchestration.artifacts import ArtifactInvalid
from sqe_studio.orchestration.artifacts import verify_manifest
import hashlib

def compare(self,request):
    pid=request.pid
    uid=request.uid
    body=self.json_body()
    required={'left','right','experimental_diagnostic','same_frame_assumption'}
    if (type(body) is not dict or not required <= set(body) or
            not set(body) <= required | {'left_cycle','right_cycle'} or
            body.get('experimental_diagnostic') is not True or
            body.get('same_frame_assumption') is not True or
            any(type(body.get(k)) is not str or not HEX_ID.fullmatch(body[k])
                for k in ('left','right')) or body['left']==body['right'] or
            any(body.get(k) is not None and
                (type(body[k]) is not int or not 0 <= body[k] < 12)
                for k in ('left_cycle','right_cycle'))):
        raise ApiError('Two distinct saved runs and explicit same-frame diagnostic opt-in required',422)
    sources=[]
    roots=[]
    manifests=[]
    models=[]
    studies=[]
    from sqe_studio.eda.upstream_field_compare import enforce_source_budgets, ComparisonBlocked
    for key in ('left','right'):
        info,folder=self._run_folder(uid,pid,body[key])
        if (folder/'SWEEP_MANIFEST.json').exists():
            raise ApiError('Field comparison requires two single native runs',422)
        manifest=self._load_result_json(folder/'output','RESULT_MANIFEST.json',256*1024)
        try:
            enforce_source_budgets(folder/'output',manifest)
            self.app.jobs._check_completed_artifacts(info)
        except ComparisonBlocked as exc:
            raise ApiError('Field comparison source exceeds its bounded inventory limits',413) from exc
        except (ArtifactInvalid,OSError,ValueError,KeyError,TypeError) as exc:
            raise ApiError('Comparison archive failed content/revision verification',409) from exc
        self._check_manifest(uid,pid,info,manifest)
        design=self.app.store.project(uid,pid,info['revision_id'])
        if manifest.get('artifact_type')!='palace.eigenmodes':
            raise ApiError('Field comparison requires Palace eigenmode outputs',422)
        try:
            verify_manifest(folder/'output',revision_id=info['revision_id'],
                project_digest=design['revision_digest'],study_id=info['study_id'],
                engine=info['engine'])
        except (ArtifactInvalid,OSError) as exc:
            raise ApiError('Comparison output failed content/revision verification',409) from exc
        roots.append(folder/'output');manifests.append(manifest)
        models.append(design['model']);studies.append(info['study_id'])
        sources.append({'run_id':info['id'],'revision_id':info['revision_id'],
            'project_sha256':design['revision_digest'],'study_id':info['study_id'],
            'result_manifest_sha256':hashlib.sha256(
                (folder/'output'/'RESULT_MANIFEST.json').read_bytes()).hexdigest()})
    from sqe_studio.eda.upstream_field_compare import compare_verified_fields
    if not self.app.field_comparison_lock.acquire(blocking=False):
        raise ApiError('Another native field comparison is running; wait for its result',409)
    try:
        diagnostic=compare_verified_fields(roots,manifests,models,studies,same_frame=True,
            cycle_indices=(body.get('left_cycle'),body.get('right_cycle')))
    finally:
        self.app.field_comparison_lock.release()
    return self.send_json({'schema':'sqe.upstream-field-comparison-response.v1',
        'left':sources[0],'right':sources[1],'diagnostic':diagnostic,
        'scientific_approval':'NOT_ESTABLISHED','fabrication':'HOLD'})


def probe(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
    body=self.json_body()
    if body != {'experimental_diagnostic': True}:
        raise ApiError('Explicit experimental diagnostic opt-in required',422)
    info,folder=self._run_folder(uid,pid,parts[4])
    try:
        self.app.jobs._check_completed_artifacts(info)
    except (ArtifactInvalid, OSError, ValueError, KeyError, TypeError) as exc:
        raise ApiError('Native archive failed content/revision verification',409) from exc
    if (folder/'SWEEP_MANIFEST.json').exists():
        raise ApiError('Upstream field probe is available only for a single native run',422)
    manifest=self._load_result_json(folder/'output','RESULT_MANIFEST.json',MAX_RESULT_JSON)
    self._check_manifest(uid,pid,info,manifest)
    design=self.app.store.project(uid,pid,info['revision_id'])
    try:
        verify_manifest(folder/'output',revision_id=info['revision_id'],
            project_digest=design['revision_digest'],
            study_id=info['study_id'],engine=info['engine'])
    except (ArtifactInvalid, OSError) as exc:
        raise ApiError('Native output failed content/revision verification',409) from exc
    from sqe_studio.eda.upstream_vtk_probe import probe_verified_run
    return self.send_json({
        'schema':'sqe.m16.upstream-field-probe-response.v1',
        'run_id':parts[4],
        'revision_id':info['revision_id'],
        'result_manifest_sha256':hashlib.sha256(
            (folder/'output'/'RESULT_MANIFEST.json').read_bytes()).hexdigest(),
        'diagnostic':probe_verified_run(folder/'output',manifest),
        'scientific_approval':'NOT_ESTABLISHED','fabrication':'HOLD'})

