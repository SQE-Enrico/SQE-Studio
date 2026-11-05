"""Sweeps; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import MAX_RESULT_JSON
from sqe_studio.interop.native_views import NativeDisplayError
from sqe_studio.interop.native_views import palace_eigenmodes
from sqe_studio.orchestration.artifacts import ArtifactInvalid

def create(self,request):
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if set(obj) not in ({'revision','study_id','axes','mode'},
                        {'revision','study_id','axes','mode','selected'}):
        raise ApiError('Sweep requires revision, study, numeric axes and mode',422)
    return self.send_json({'run_id':self.app.jobs.start_sweep(
        uid,pid,obj['revision'],obj['study_id'],obj['axes'],
        mode=obj['mode'],selected=obj.get('selected'))},202)


def inspect(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
    info,folder=self._run_folder(uid,pid,parts[4])
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

