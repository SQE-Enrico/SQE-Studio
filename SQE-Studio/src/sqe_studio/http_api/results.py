"""Results; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import MAX_RESULT_JSON
from sqe_studio.eda.field_lineage import inspect_verified_run_field_lineage
from sqe_studio.eda.scientific_references import evaluate_verified_result
from sqe_studio.interop.capacitance_review_dossier import CapacitanceReviewBlocked
from sqe_studio.interop.capacitance_review_dossier import build_native_capacitance_review_dossier
from sqe_studio.interop.capacitance_review_dossier import serialize_capacitance_review_dossier
from sqe_studio.interop.capacitance_topology import CapacitanceTopologyBlocked
from sqe_studio.interop.design_targets import evaluate_design_targets
from sqe_studio.interop.extracted_transmon import ExtractionBlocked
from sqe_studio.interop.extracted_transmon import validate_saved_result
from sqe_studio.interop.native_capacitance_case import NativeCapacitanceCaseBlocked
from sqe_studio.interop.native_capacitance_case import build_native_capacitance_case_readiness
from sqe_studio.interop.native_capacitance_case import serialize_native_capacitance_case_readiness
from sqe_studio.interop.native_capacitance_evidence import NativeCapacitanceEvidenceError
from sqe_studio.interop.native_capacitance_evidence import native_capacitance_evidence
from sqe_studio.interop.native_em_evidence import NativeEMEvidenceError
from sqe_studio.interop.native_em_evidence import native_em_evidence
from sqe_studio.interop.native_rf_evidence import NativeRFEvidenceError
from sqe_studio.interop.native_rf_evidence import native_rf_evidence
from sqe_studio.interop.native_views import NativeDisplayError
from sqe_studio.interop.native_views import palace_eigenmodes
from sqe_studio.interop.transmon_workflow import inspect_saved_transmon_screen
from sqe_studio.orchestration.artifacts import ArtifactInvalid
from sqe_studio.orchestration.artifacts import verify_manifest

def inspect(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
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
        if manifest.get('artifact_type') == 'palace.eigenmodes':
            result['field_lineage'] = inspect_verified_run_field_lineage(
                folder/'output', manifest)
        if 'spectrum.json' in {a['name'] for a in manifest['artifacts']}:
            result['spectrum']=self._load_result_json(folder/'output','spectrum.json',MAX_RESULT_JSON)
        if 'extraction.json' in {a['name'] for a in manifest['artifacts']}:
            extraction=self._load_result_json(folder/'output','extraction.json',MAX_RESULT_JSON)
            try:
                studies=[s for s in project['model']['studies'] if s['id']==info['study_id']]
                if len(studies)!=1:
                    raise ExtractionBlocked('Saved research study unavailable')
                result['conditional_extraction']=validate_saved_result(
                    extraction,result.get('spectrum'),studies[0])
            except (ValueError,TypeError,KeyError):
                raise ApiError('Conditional extraction result is inconsistent',409) from None
        try:
            result['eigenmodes']=palace_eigenmodes(folder/'output',manifest)
            # Existing generic Results endpoint; all declared native
            # bytes have just passed the same revision/hash gate.
            result['em_evidence']=native_em_evidence(folder/'output',manifest)
        except (NativeDisplayError,NativeEMEvidenceError,OSError,ValueError) as exc:
            raise ApiError('Native EM table failed structural verification',409) from exc
        try:
            result['rf_evidence']=native_rf_evidence(folder/'output',manifest)
        except (NativeRFEvidenceError,OSError,ValueError) as exc:
            raise ApiError('Native RF evidence failed structural verification',409) from exc
        try:
            result['capacitance_evidence'] = native_capacitance_evidence(
                folder/'output', manifest, project)
        except (NativeCapacitanceEvidenceError, OSError, ValueError) as exc:
            raise ApiError('Native capacitance evidence failed structural verification', 409) from exc
        try:
            result['transmon_capacitance_screen'] = inspect_saved_transmon_screen(
                folder/'output', manifest, project)
        except (CapacitanceTopologyBlocked, OSError, ValueError, KeyError, TypeError) as exc:
            raise ApiError('Saved transmon topology or native mapping failed scientific/provenance screening',409) from exc
        # M3: read-only independent-review *request*, never an approval.
        # Selection is read from this authenticated immutable project
        # revision, not from request JSON or a Results screen scalar.
        screen=result.get('transmon_capacitance_screen')
        if isinstance(screen,dict) and screen.get('status')=='NUMERICAL_SCREEN_ONLY':
            current=self.app.store.project(uid,pid)
            if current['head']!=info['revision_id']:
                # Historic Results remain inspectable; a dossier only
                # attests current-head Store context, never a stale run.
                result['capacitance_review_dossier_status']='BLOCKED_HISTORICAL_REVISION'
                result['b04_case_readiness_status']='BLOCKED_HISTORICAL_REVISION'
            else:
                selection=project['model']['intent']['transmon_capacitance_selection']
                saved_selection={
                    'revision_id': project['revision'],
                    'revision_digest': project['revision_digest'],
                    'study_id': selection['study_id'],
                    'island_a': selection['island_a'],
                    'island_b': selection['island_b'],
                    'other_terminal_policy': selection['other_terminal_policy'],
                }
                try:
                    dossier=build_native_capacitance_review_dossier(
                        self.app.store,owner=uid,project_id=pid,
                        run_id=parts[4],saved_selection=saved_selection)
                    serialize_capacitance_review_dossier(dossier)
                except (CapacitanceReviewBlocked,OSError,ValueError,TypeError,KeyError) as exc:
                    raise ApiError('Native capacitance review dossier failed trusted-source verification',409) from exc
                result['capacitance_review_dossier']=dossier
                try:
                    b04=build_native_capacitance_case_readiness(
                        self.app.store,owner=uid,project_id=pid,
                        run_id=parts[4],saved_selection=saved_selection)
                    serialize_native_capacitance_case_readiness(b04)
                except (NativeCapacitanceCaseBlocked,OSError,ValueError,TypeError,KeyError) as exc:
                    raise ApiError('B04 native case readiness failed trusted-source verification',409) from exc
                result['b04_case_readiness']=b04
        # M5 independent spectrum execution has its own private
        # manual-origin gate; no EM-derived EC is imported.
        # The target screen uses goals saved in this very revision,
        # not the user's subsequently edited or current targets.
        # It is computed only AFTER every native artifact is rehashed.
        result['design_target_screen']=evaluate_design_targets(
            project=project, manifest=manifest,
            spectrum=result.get('spectrum'),
            em_evidence=result.get('em_evidence'),
            rf_evidence=result.get('rf_evidence'))
        # M8: diagnostics consume ONLY this already rehashed,
        # revision-bound native Results object and project.
        if 'conditional_extraction' not in result:
            result['scientific_references']=evaluate_verified_result(
                project=project, manifest=manifest,
                spectrum=result.get('spectrum'),
                transmon_screen=result.get('transmon_capacitance_screen'))
        return self.send_json(result)

