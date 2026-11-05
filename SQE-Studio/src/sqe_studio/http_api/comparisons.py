"""Comparisons; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import HEX_ID
from .common import MAX_RESULT_JSON
from sqe_studio.eda.cpw_scaling import compare_verified_cpw_length_scaling
from sqe_studio.eda.field_lineage import compare_verified_field_lineages
from sqe_studio.eda.field_lineage import inspect_verified_run_field_lineage
from sqe_studio.eda.field_lineage import screen_verified_saved_pair_overlap
from sqe_studio.eda.mesh_refinement import compare_verified_three_meshes
from sqe_studio.interop.capacitance_topology import CapacitanceTopologyBlocked
from sqe_studio.interop.comparison import report as comparison_report
from sqe_studio.interop.native_capacitance_evidence import NativeCapacitanceEvidenceError
from sqe_studio.interop.native_capacitance_evidence import native_capacitance_evidence
from sqe_studio.interop.native_em_evidence import NativeEMEvidenceError
from sqe_studio.interop.native_em_evidence import native_em_evidence
from sqe_studio.interop.native_views import NativeDisplayError
from sqe_studio.interop.native_views import palace_eigenmodes
from sqe_studio.interop.transmon_comparison import compare_conditional_transmon_screens
from sqe_studio.interop.transmon_workflow import inspect_saved_transmon_screen
from sqe_studio.orchestration.artifacts import ArtifactInvalid
from sqe_studio.orchestration.artifacts import verify_manifest
from urllib.parse import parse_qs
import re

def compare(self,request):
    parsed=request.parsed
    pid=request.pid
    uid=request.uid
    q=parse_qs(parsed.query, keep_blank_values=True, max_num_fields=3)
    if (not {'left','right'} <= set(q) or
            not set(q) <= {'left','right','fine'} or
            any(len(v) != 1 or not HEX_ID.fullmatch(v[0]) for v in q.values())):
        raise ApiError('Two or three valid run identifiers are required',400)
    selected_ids=[q['left'][0],q['right'][0]]
    if 'fine' in q: selected_ids.append(q['fine'][0])
    if len(set(selected_ids)) != len(selected_ids):
        raise ApiError('Comparison requires distinct completed runs',400)
    reviews=[]
    for run_id in selected_ids:
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
        palace=None
        em_evidence=None
        capacitance=None
        if ref.artifact_type=='palace.capacitance_matrix':
            try:
                capacitance=native_capacitance_evidence(folder/'output',manifest,project)
                if capacitance is None:
                    raise NativeCapacitanceEvidenceError('Missing native Maxwell evidence')
            except (NativeCapacitanceEvidenceError,OSError,ValueError) as exc:
                raise ApiError('Comparison native capacitance evidence failed structural verification',409) from exc
        if ref.artifact_type=='palace.eigenmodes':
            try:
                palace=palace_eigenmodes(folder/'output',manifest)
                em_evidence=native_em_evidence(folder/'output',manifest)
            except (NativeDisplayError,NativeEMEvidenceError,OSError,ValueError) as exc:
                raise ApiError('Comparison native EM evidence failed structural verification',409) from exc
        reviews.append((info,project,manifest,spectrum,palace,em_evidence,capacitance))
    (li,lp,lm,ls,le,loe,lc),(ri,rp,rm,rs,re,roe,rc)=reviews[:2]
    result=comparison_report(lm,rm,li,ri,lp,rp,ls,rs,le,re,loe,roe,lc,rc)
    if len(reviews) == 3:
        fi,fp,fm,fs,fe,foe,fc=reviews[2]
        result['fine']={
            'run_id':fi['id'], 'study_id':fi['study_id'],
            'revision_id':fi['revision_id'],
            'project_sha256':fp['revision_digest'],
            'engine':fm['engine'], 'native_version':fm['engine_version'],
            'artifact_type':fm['artifact_type'],
            'fabrication_status':fm['fabrication_status'],
            'artifacts':[{'name':a['name'],'sha256':a['sha256']} for a in fm['artifacts']]}
        result['mesh_refinement_series']=compare_verified_three_meshes(
            models=(lp['model'],rp['model'],fp['model']),
            study_ids=(li['study_id'],ri['study_id'],fi['study_id']),
            native=(le,re,fe),manifests=(lm,rm,fm))
    if all(x[2]['artifact_type'] == 'palace.eigenmodes' for x in reviews):
        field_rows=[]
        for run_info, _proj, signed_manifest, *_rest in reviews:
            _verified_info, saved_folder=self._run_folder(uid,pid,run_info['id'])
            field_rows.append(inspect_verified_run_field_lineage(
                saved_folder/'output', signed_manifest))
        result['field_lineage_by_run']=field_rows
        result['field_lineage_comparison']=compare_verified_field_lineages(
            field_rows, verified_mesh_screen=result.get('mesh_refinement_series'),
            verified_pairwise_screen=result.get('numerical_comparison'))
        # M12: only an unambiguous single-cycle/single-piece pair
        # may enter the bounded B03 diagnostic. In all other cases
        # report explicit blockers; never synthesize a mode match.
        if len(reviews) == 2:
            folders=[]
            for run_info, *_unused in reviews:
                _verified_info, saved_folder=self._run_folder(uid,pid,run_info['id'])
                folders.append(saved_folder/'output')
            result['cross_mesh_visualization_review']=screen_verified_saved_pair_overlap(
                (folders[0],folders[1]), (lm,rm), field_rows,
                result['numerical_comparison'])
    if (lm['artifact_type'] == rm['artifact_type'] == 'palace.eigenmodes'
            and lp['model'].get('family') == rp['model'].get('family') == 'resonator'):
        result['cpw_length_scaling_reference'] = compare_verified_cpw_length_scaling(
            left_model=lp['model'], right_model=rp['model'],
            left_study_id=li['study_id'], right_study_id=ri['study_id'],
            left_native=le, right_native=re)
    if (result['numerical_comparison']['status']==
            'native_maxwell_matrix_differences_for_expert_review' and
            all(p['model'].get('family') in ('transmon','multi_qubit')
                for p in (lp,rp))):
        selections=[p['model'].get('intent',{}).get('transmon_capacitance_selection')
                    for p in (lp,rp)]
        if all(x is not None for x in selections):
            try:
                screened=[]
                for info,project,manifest in ((li,lp,lm),(ri,rp,rm)):
                    _checked,base=self._run_folder(uid,pid,info['id'])
                    screened.append(inspect_saved_transmon_screen(
                        base/'output',manifest,project))
            except (CapacitanceTopologyBlocked,ArtifactInvalid,OSError,ValueError) as exc:
                raise ApiError('Comparison transmon source failed trusted native verification',409) from exc
            result['transmon_reduction_comparison']=compare_conditional_transmon_screens(
                screened[0],screened[1],selections[0],selections[1],
                result['numerical_comparison'])
        else:
            result['transmon_reduction_comparison']={
                'schema':'sqe.conditional-transmon-drift.m7.v1',
                'status':'not_comparable',
                'reason':'Both revisions need explicit saved island selections; none inferred',
                'mesh_convergence':'NOT_ESTABLISHED',
                'em_to_scqubits_transfer':'BLOCKED','fabrication':'HOLD'}
    return self.send_json(result)

