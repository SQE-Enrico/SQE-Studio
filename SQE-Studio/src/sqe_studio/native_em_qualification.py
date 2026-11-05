"""Operator-approved, temporary native EM qualification using the production A02/A03 worker.

This is not an alternative EDA path or a new electromagnetic engine. A documented
research geometry is used solely to exercise the same worker as ordinary saved
EDA studies. The operator must explicitly review its stated material assumptions;
no native outputs are synthesized. Evidence never contains a user's design.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import zipfile

from .contracts import digest
from .interop.laptop_benchmark import (approve_exploratory_stack,
                                        assess_native_run, compare_refinements,
                                        resonator_project)
from .orchestration.artifacts import verify_manifest
from .interop.em_convergence import (palace_log_metrics, convergence_series,
                                     third_mesh_preflight, frequency_tolerance_sensitivity)
from .qualification import _run, _safe_log, sha
from .interop.palace_parallel import mpi_plan

SOURCE_URL = 'https://sqdlab.github.io/SQDMetal/examples/Palace_Eigenmode_Res_PortFeed_Gmsh.html'
ASSUMPTIONS = ("Exploratory SQDMetal-adapted CPW, NOT a faithful reproduction of the published "
               "CoupledLineTee geometry. Silicon substrate: thickness 500 um, relative "
               "permittivity 11.45, dielectric loss tangent 2.7e-6 (SQDMetal silicon default, not measured). Aluminium conductor: "
               "100 nm, PEC approximation. Vacuum superstrate: 500 um, epsilon_r 1.0. "
               "Ground layer 1; PEC farfield; two 50-ohm CPW launcher ports. "
               "No measured film parameters, PDK approval, model convergence or fabrication claim.")
MATERIAL_SOURCE_URL = 'https://github.com/sqdlab/SQDMetal/blob/main/SQDMetal/Utilities/Materials.py'
REPORT_SCHEMA = 'sqe.native-em-qualification.v1'
MAX_EVIDENCE_BYTES = 256_000


def _option_check(reviewer, acknowledged, solve, refine, third_mesh=False, memory_budget_gb=8.0, time_budget_seconds=840, mpi_ranks="auto"):
    if not acknowledged or not isinstance(reviewer, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,47}', reviewer):
        raise ValueError('Native EM test requires explicit material-assumption acknowledgement and reviewer ID (3-48 ASCII characters)')
    if type(solve) is not bool or type(refine) is not bool or (refine and not solve):
        raise ValueError('Mesh-refinement comparison requires an actual Palace solve')
    if type(third_mesh) is not bool or (third_mesh and not refine):
        raise ValueError('Third mesh requires two prior native solves and explicit opt-in')
    if type(memory_budget_gb) not in (int,float) or not 4 <= memory_budget_gb <= 128:
        raise ValueError('Native third-mesh memory preflight budget must be 4-128 GB')
    if mpi_ranks != 'auto' and (type(mpi_ranks) is not int or not 1 <= mpi_ranks <= 16):
        raise ValueError('MPI ranks must be auto or an integer 1..16')
    if type(time_budget_seconds) is not int or not 300 <= time_budget_seconds <= 840:
        raise ValueError('Palace native timeout budget must be 300-840 seconds')


def _zip_report(destination, files):
    files['INTEGRITY.json'] = (json.dumps({'schema':'sqe.qualification-file-hashes.v1',
        'files': {name:sha(content) for name, content in sorted(files.items())}},
        indent=2, sort_keys=True)+'\n').encode('utf-8')
    temporary = destination.with_name(destination.name+'.partial')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=8) as bundle:
            for name, payload in sorted(files.items()):
                bundle.writestr(name, payload)
        with zipfile.ZipFile(temporary) as bundle:
            if bundle.testzip() is not None:
                raise RuntimeError('Generated EM evidence archive failed ZIP integrity')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def qualify_native_em(source: Path, destination: Path, *, reviewer: str,
                      acknowledged: bool, solve: bool = False, refine: bool = False,
                      third_mesh: bool = False, memory_budget_gb: float = 8.0,
                      time_budget_seconds: int = 840, mpi_ranks="auto", notify=None):
    """Run the genuine A02/A03 worker on a temporary reviewed reference snapshot.

    Deck-only is the fast default. Solve optionally exercises the configured
    local/WSL Palace and may take up to the bounded solver timeout per point.
    A numerical mode index is NOT equivalent to independently verified mode
    identity; even two successful solves cannot qualify convergence by themselves.
    """
    _option_check(reviewer, acknowledged, solve, refine, third_mesh, memory_budget_gb, time_budget_seconds, mpi_ranks)
    root = Path(source).resolve(strict=True)
    destination = Path(destination).expanduser().absolute()
    if destination.suffix.lower() != '.zip' or destination.is_symlink() or destination.is_relative_to(root):
        raise ValueError('EM report destination must be a ZIP outside the SQE source tree')
    if not (root/'src/sqe_studio/worker.py').is_file():
        raise ValueError('An extracted SQE Studio source tree is required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    report = {'schema': REPORT_SCHEMA, 'purpose': 'temporary_reference_native_eda_edge_qualification',
              'started_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'source': 'SQDMetal documentation, adapted CPW with different coupler topology',
              'literature_url': SOURCE_URL, 'material_catalog_url': MATERIAL_SOURCE_URL,
              'options': {'solve':solve, 'refine':refine, 'third_mesh':third_mesh,
                          'memory_budget_gb':memory_budget_gb,'time_budget_seconds':time_budget_seconds,
                          'mpi_ranks_requested':mpi_ranks,
                          'reviewed_reference_not_independent_validation':True},
              'review': {}, 'stages': [], 'scientific_qualification': 'not_established',
              'fabrication_status':'HOLD', 'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}

    def notify_user(s):
        if notify:
            notify(s)

    started_stages=set()
    def begin_stage(name):
        if name not in started_stages:
            started_stages.add(name)
            notify_user('STAGE_START native_em '+name)

    def stage(name, status, reason, **details):
        begin_stage(name)
        record = {'id':name, 'status':status, 'reason':reason, **details}
        report['stages'].append(record)
        notify_user('STAGE_END native_em '+name+' '+status)
        notify_user(status+': '+name+' — '+reason[:110])

    with tempfile.TemporaryDirectory(prefix='sqe-em-qualification-') as scratch:
        work = Path(scratch)
        original_home = str(Path.home())
        substitutions = (str(root), str(work), original_home, os.environ.get('USERPROFILE',''))
        env = os.environ.copy()
        env.update({'HOME':str(work/'home'), 'USERPROFILE':str(work/'home'),
                    'XDG_CACHE_HOME':str(work/'cache'), 'XDG_CONFIG_HOME':str(work/'config'),
                    'PYTHONPATH':str(root/'src'), 'PYTHONDONTWRITEBYTECODE':'1',
                    'PYTHONNOUSERSITE':'1', 'QT_QPA_PLATFORM':'offscreen'})
        (work/'home').mkdir()
        review_file = work/'material-review.txt'
        review_file.write_text(('Fixed exploratory RELEASE TEST protocol; no human material approval.\n'
                    if reviewer == 'SQEFixedProtocol' else 'Operator reviewed for exploratory TEST ONLY.\n')
                    +ASSUMPTIONS+'\n',encoding='utf-8')
        model = resonator_project(execution='deck_only')
        reviewed, record = approve_exploratory_stack(model, reviewer=reviewer,
                                                      document=review_file, source_url=SOURCE_URL)
        report['review'] = {'reviewer_id':reviewer, 'review_record':record,
                            'assumptions':ASSUMPTIONS,
                            'review_basis':('fixed_release_research_protocol_not_human_review'
                                            if reviewer == 'SQEFixedProtocol' else 'operator_acknowledgement'),
                            'note':('Fixed software QA research protocol; NOT human approval'
                                    if reviewer == 'SQEFixedProtocol' else 'Operator acknowledgement; NOT a material certificate')}
        stage('explicit_reference_review','PASS',
              ('Fixed research-only software-test assumptions loaded; no human material review or fabrication approval'
               if reviewer == 'SQEFixedProtocol' else
               'Explicit research assumptions acknowledged; not approved for fabrication'))
        # Only a diagnostic/resource plan: never claim scientific qualification.
        parallel = mpi_plan(mpi_ranks)
        report['parallelism'] = parallel
        files['native/parallelism-plan.json'] = (json.dumps(parallel, sort_keys=True, indent=2)+'\n').encode('utf-8')
        if solve:
            notify_user('Palace MPI ranks: '+str(parallel['mpi_ranks'])+'; one OpenMP thread per rank. '
                        'Scaling is not guaranteed; check WSL CPU/RAM.')
        observations = []
        readouts = []  # Only SHA-256-verified production results are admitted.
        readout_models = []
        readout_sources = []
        correlation = None
        metrics = []
        deck_hashes = []
        # A solved production worker already builds and validates its own mesh
        # and deck. Avoid repeating the identical ~minute-long native geometry
        # stage when a solve was requested. Deck-only retains the fast check.
        tasks = ([] if solve else [('mesh_and_deck','deck_only',12.,120.)])
        if solve:
            tasks.append(('native_palace_solve','solve',12.,120.))
        if refine:
            tasks.append(('native_palace_refinement','solve',8.,80.))
        if third_mesh:
            tasks.append(('native_palace_third','solve',7.5,75.))

        # Check only import availability here; genuine API and geometry are tested
        # by the worker itself. No substitute geometry or solver is permitted.
        required_modules = ('qiskit_metal','SQDMetal','gmsh')
        missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
        stage('native_em_toolchain', 'BLOCKED' if missing else 'PASS',
              'Unavailable native Python modules: '+', '.join(missing) if missing else
              'Required modules are present; successful import/mesh is not yet proven')
        stopped = bool(missing)
        for name, execution, minimum, maximum in tasks:
            if name == 'native_palace_third':
                # A third solve is expensive; require actual earlier solver resource
                # measurements and an explicit laptop budget. This is a preflight,
                # NOT OS-enforced memory isolation inside WSL2.
                resource = third_mesh_preflight(metrics[0],metrics[1],
                       memory_limit_gb=memory_budget_gb, time_limit_seconds=time_budget_seconds) if len(metrics)==2 else {
                       'allow':False,'reason':'Two prior native solves unavailable'}
                files['native/third-mesh-resource-preflight.json'] = (json.dumps(resource,indent=2,sort_keys=True)+'\n').encode()
                if not resource['allow']:
                    stage(name,'BLOCKED',resource['reason'],resource_preflight=resource)
                    break
            if stopped:
                stage(name,'BLOCKED','Native prerequisites or earlier stage unavailable')
                break
            if execution=='solve' and not (os.environ.get('SQE_PALACE_BINARY') or os.environ.get('SQE_PALACE_WSL_BINARY')):
                stage(name,'BLOCKED','Palace path not configured in desktop solver settings')
                stopped=True
                break
            begin_stage(name)
            notify_user('Starting '+name+' with genuine production worker (stage can take minutes)')
            model = resonator_project(execution=execution, mesh_min_um=minimum, mesh_max_um=maximum,
                                      mpi_ranks=parallel['mpi_ranks'])
            model, _ = approve_exploratory_stack(model, reviewer=reviewer,
                                                  document=review_file, source_url=SOURCE_URL)
            snapshot = {'project':model, 'study':model['studies'][0], 'revision_id':digest(model)[:32],
                        'project_digest':digest(model), 'parents':[]}
            snapshot_file = work/(name+'-snapshot.json')
            snapshot_file.write_text(json.dumps(snapshot,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
            folder = work/name
            # The fixed release plan budgets 840 seconds per native worker;
            # include native geometry/meshing in that same deadline, never run
            # a hidden longer subprocess than the stated budget.
            timeout = min(330, time_budget_seconds) if execution=='deck_only' else time_budget_seconds
            notify_user('Running native worker: '+name+' (bounded, no fixture results)')
            code, raw_log, elapsed = _run([sys.executable,'-m','sqe_studio.worker',str(snapshot_file),str(folder)],
                                          root,env,timeout)
            failed = folder/'FAILURE.json'
            if failed.is_file() and not failed.is_symlink() and failed.stat().st_size <= 65536:
                raw_log += '\nNATIVE WORKER FAILURE:\n'+failed.read_text(encoding='utf-8',errors='replace')
            native_log = folder/'sqe_em'/'palace-native.log'
            solver_metrics = None
            if native_log.is_file() and not native_log.is_symlink() and native_log.stat().st_size <= 20_000_000:
                native_data = native_log.read_bytes()
                solver_metrics = palace_log_metrics(native_data.decode('utf-8','replace'))
                raw_log += '\nPALACE LOG (head/tail):\n'+(native_data[:14000]+b'\n...\n'+native_data[-14000:]).decode('utf-8','replace')
            files['logs/'+name+'.txt'] = (_safe_log(raw_log, substitutions)+'\n').encode('utf-8')
            # Retain bounded *unverified* diagnostics on timeout/failure; never
            # call them a successful native result without the production manifest.
            phase_file = folder/'sqe_em'/'palace-phases.json'
            if phase_file.is_file() and not phase_file.is_symlink() and 0 < phase_file.stat().st_size <= 16000:
                files['native/'+name+'-palace-phases-unverified.json'] = phase_file.read_bytes()
            partial_eig = folder/'sqe_em'/'outputFiles'/'eig.csv'
            if (code != 0 and partial_eig.is_file() and not partial_eig.is_symlink()
                    and 0 < partial_eig.stat().st_size <= MAX_EVIDENCE_BYTES):
                files['native/'+name+'-eig-UNVERIFIED.csv'] = partial_eig.read_bytes()
            manifest_path = folder/'RESULT_MANIFEST.json'
            if code != 0 or not manifest_path.is_file():
                stage(name,'FAIL' if code is not None else 'BLOCKED',
                      'Native worker exited unsuccessfully or timed out; partial CSV (if any) is UNVERIFIED',
                      seconds=elapsed, worker_exit_code=code)
                stopped = True
                break
            try:
                verified = verify_manifest(folder, revision_id=snapshot['revision_id'],
                                           project_digest=snapshot['project_digest'],
                                           study_id='ResEigen',engine='sqdmetal_palace')
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                required = {'sqe_em/sqe_em.msh','sqe_em/sqe_em.json'}
                if not required <= {art['name'] for art in manifest['artifacts']}:
                    raise ValueError('Missing native mesh/deck in verified result manifest')
                if execution=='solve':
                    observation = assess_native_run(model,folder)
                    observations.append(observation)
                    metrics.append(solver_metrics or {})
                    # RC14.5: exercise the EXACT readers used by the generic Results
                    # endpoint, on genuine revision- and SHA-256-verified Palace files.
                    from .interop.native_em_evidence import native_em_evidence
                    from .interop.native_views import palace_eigenmodes
                    readout = native_em_evidence(folder, manifest)
                    eigenview = palace_eigenmodes(folder, manifest)
                    # M11: independent SHA-bound PVD/PVTU/VTU format/lineage
                    # readiness, without copying private VTK/mesh data into
                    # the portable qualification report or claiming mode overlap.
                    from .eda.field_lineage import inspect_verified_run_field_lineage
                    readout['field_lineage'] = inspect_verified_run_field_lineage(folder, manifest)
                    # M16: upstream backend is independent diagnostic evidence,
                    # not a replacement for B02 qualification criteria. Never
                    # export raw VTK or change scalar/native PASS on probe failure.
                    from .eda.upstream_vtk_probe import probe_verified_run
                    upstream_field = probe_verified_run(folder, manifest, timeout=25)
                    files['native/'+name+'-upstream-field-probe.json'] = (json.dumps(
                        upstream_field, indent=2, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')
                    readout['upstream_field_probe'] = upstream_field
                    if readout is None or eigenview is None or not readout['modes']:
                        raise ValueError('Results readers returned no verified native Palace modes')
                    readouts.append((readout, eigenview))
                    readout_models.append(model)
                    readout_sources.append((folder,manifest))
                    files['native/'+name+'-results-screen.json'] = (json.dumps(
                        readout, indent=2, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')
                    stage('results_screen_'+name,'PASS',
                          'Production Results scalar readers accepted verified real native tables; not scientific qualification',
                          mode_count=len(readout['modes']),
                          signed_native_kappa_preserved=True,
                          field_identity_verified=False)
                    deck_hashes.append(next(a['sha256'] for a in manifest['artifacts']
                                            if a['name']=='sqe_em/sqe_em.json'))
                    # Include SMALL native eigenfrequency tables; never include bulky mesh/field data.
                    eig = folder/'sqe_em'/'outputFiles'/'eig.csv'
                    if eig.is_file() and not eig.is_symlink() and eig.stat().st_size <= MAX_EVIDENCE_BYTES:
                        files['native/'+name+'-eig.csv'] = eig.read_bytes()
                    # Native modal INDICATORS for expert review, NOT mode-field overlap.
                    declared_names = {a['name'] for a in manifest['artifacts']}
                    for indicator in ('domain-E.csv','port-Q.csv'):
                        relative='sqe_em/outputFiles/'+indicator
                        candidate=folder/relative
                        if (relative in declared_names and candidate.is_file()
                            and not candidate.is_symlink() and 0 < candidate.stat().st_size <= MAX_EVIDENCE_BYTES):
                            files['native/'+name+'-'+indicator] = candidate.read_bytes()
                else:
                    observation = None
                metadata = {'artifact_type':manifest['artifact_type'],
                            'native_solver_version':manifest['engine_version'],
                            'artifacts':[{'name':x['name'],'sha256':x['sha256'],'bytes':x['bytes']}
                                         for x in manifest['artifacts']],
                            'model_digest':snapshot['project_digest'],
                            'result_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                            'observation':observation, 'solver_metrics':solver_metrics}
                files['native/'+name+'-manifest.json'] = (json.dumps(metadata,indent=2,sort_keys=True)+'\n').encode('utf-8')
                for source_name, target_name in (('sqe_em/sqe_em.json', name+'-palace-deck.json'),
                                                 ('a03-native-artifacts.json', name+'-adapter-sidecar.json')):
                    candidate = folder/source_name
                    if candidate.is_file() and not candidate.is_symlink() and 0 < candidate.stat().st_size <= MAX_EVIDENCE_BYTES:
                        files['native/'+target_name] = candidate.read_bytes()
                if name == 'native_palace_solve':
                    stage('mesh_and_deck','PASS',
                          'Mesh and deck verified inside the SAME native solve worker; redundant deck-only worker omitted',
                          from_solved_worker=True)
                stage(name,'PASS','Native worker returned a hash-verified manifest; scientific review still required',
                      seconds=elapsed, artifact_type=manifest['artifact_type'])
            except Exception as exc:
                files['logs/'+name+'.txt'] += ('\nVALIDATION ERROR: '+_safe_log(type(exc).__name__+': '+str(exc),substitutions)+'\n').encode()
                stage(name,'FAIL','Native output did not satisfy the production manifest/physics checks',
                      seconds=elapsed, validation_error=type(exc).__name__)
                stopped = True
                break

        if solve and len(readouts) >= 2:
            # Use the same comparison path as the normal Results/Compare endpoint.
            # Only the EM mesh may differ. No solver-index-to-mode mapping is inferred.
            try:
                from .interop.comparison import compare_palace_modes
                from .interop.native_em_evidence import compare_native_em_evidence
                frequency = compare_palace_modes(readouts[0][1],readouts[1][1],
                          readout_models[0],readout_models[1],
                          readout_models[0]['studies'][0]['id'],readout_models[1]['studies'][0]['id'])
                scalar = compare_native_em_evidence(readouts[0][0],readouts[1][0],frequency)
                files['native/results-cross-run-comparison.json'] = (json.dumps(
                    {'frequency':frequency,'observables':scalar},indent=2,
                    sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
                if frequency['status'] == 'native_mode_index_differences_for_expert_review' and scalar['status'] == 'NATIVE_INDEX_SCALAR_DIAGNOSTICS_ONLY':
                    stage('results_cross_run_comparison','PASS',
                          'Native mode-index frequency/Q/port deltas checked with production comparison logic; identity unresolved',
                          numerical_rows=len(scalar['rows']),physical_convergence='NOT_ESTABLISHED')
                else:
                    stage('results_cross_run_comparison','BLOCKED',
                          'Saved physical input compatibility or native port/mode evidence insufficient for numerical comparison',
                          frequency_status=frequency['status'],scalar_status=scalar['status'])
            except (ValueError,KeyError,TypeError) as exc:
                stage('results_cross_run_comparison','FAIL',
                      'Production native Results comparison rejected output: '+type(exc).__name__)
            from .eda.upstream_field_compare import compare_verified_fields, RECORDED
            correlation=compare_verified_fields(
                [s[0] for s in readout_sources[:2]], [s[1] for s in readout_sources[:2]],
                readout_models[:2], [m['studies'][0]['id'] for m in readout_models[:2]],
                same_frame=True)
            files['native/upstream-field-correlation.json'] = (json.dumps(
                correlation,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
            stage('upstream_field_correlation',
                  'PASS' if correlation['status']==RECORDED else correlation['status'],
                  'Discrete visualization statistic only; no physical mode identity or mesh convergence',
                  diagnostic_status=correlation['status'],reason_code=correlation['reason_code'],
                  physical_mode_identity='UNRESOLVED',mesh_convergence='NOT_ESTABLISHED')
        elif refine and solve:
            stage('results_cross_run_comparison','BLOCKED',
                  'Two verified native Palace solves required for the numerical-only Results comparison')
            stage('upstream_field_correlation','BLOCKED',
                  'Two verified native field outputs required; no synthetic replacement')
        if solve and not any(s['id']=='mesh_and_deck' and s['status']=='PASS' for s in report['stages']):
            stage('mesh_and_deck','BLOCKED',
                  'Requested solve did not return a verified production mesh/deck manifest')
        if not solve:
            stage('palace_solution','BLOCKED','Deck-only fast mode: solver not requested')
        elif stopped and not any(x['id']=='native_palace_solve' and x['status']=='PASS' for x in report['stages']):
            stage('palace_solution','BLOCKED','No verified native Palace eigenmode result')
        if not refine:
            stage('mesh_convergence','BLOCKED','Two native solves and reviewed field-mode identity required')
        elif len(observations)<2:
            stage('mesh_convergence','BLOCKED','Two verified native solutions unavailable')
        else:
            from .interop.laptop_benchmark import BenchmarkBlocked
            try:
                # Keep the original two-solve protocol for existing tools.
                comparison = compare_refinements(observations[:2], tolerance=0.02)
                files['native/refinement-comparison.json'] = (json.dumps(comparison,indent=2,sort_keys=True)+'\n').encode()
                if len(set(deck_hashes)) != 1:
                    raise ValueError('Palace deck changed across the nominal mesh-only refinements')
                series = convergence_series(observations, metrics, field_correlation=correlation)
                files['native/convergence-series.json'] = (json.dumps(series,indent=2,sort_keys=True)+'\n').encode()
                sensitivity=frequency_tolerance_sensitivity(observations,metrics,
                    recorded_tolerance=series['relative_tolerance'])
                files['native/frequency-tolerance-sensitivity.json']=(json.dumps(
                    sensitivity,indent=2,sort_keys=True)+'\n').encode()
                last=series['adjacent_differences'][-1]
                stage('mesh_convergence','BLOCKED',
                      ('Numeric drift and sampled field correlation recorded; physical mode identity and convergence unverified'
                       if correlation is not None and correlation['status']=='SAMPLED_FIELD_CORRELATION_RECORDED' else
                       'Numeric drift recorded; sampled fields unavailable and physical mode identity unverified'),
                      numerical_threshold_met=last['numeric_tolerance_met'],
                      last_step_relative_difference=last['relative_difference'],
                      number_of_native_meshes=len(observations),
                      sampled_field_correlation_status=series.get('field_evidence_status','NOT_RECORDED'),
                      frequency_criteria_sensitivity=[{'relative_tolerance':e['relative_tolerance'],
                          'last_interval_threshold_met':e['last_interval_threshold_met']} for e in sensitivity['evaluations']],
                      unresolved_requirements=series.get('unresolved_requirements', ['PHYSICAL_MODE_IDENTITY_UNRESOLVED']))
            except (BenchmarkBlocked,ValueError) as exc:
                stage('mesh_convergence','FAIL','Native comparison invalid: '+str(exc)[:200])

    report['finished_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    report['counts'] = {state:sum(s['status']==state for s in report['stages']) for state in ('PASS','FAIL','BLOCKED')}
    summary = ['# SQE Studio — native EM qualification (research reference)', '',
               'Result: **BLOCKED_NOT_RELEASE_CANDIDATE**',
               'PASS: '+str(report['counts']['PASS'])+' / FAIL: '+str(report['counts']['FAIL'])+' / BLOCKED: '+str(report['counts']['BLOCKED']),
               '', 'This runs the unmodified production A02/A03 worker on a temporary reference snapshot.',
               'Operator-reviewed assumptions are EXPLORATORY; no foundry or independent validation.',
               'No personal designs, material databases, original mesh or full field data are collected.', '',
               '| Stage | Status | Interpretation |', '|---|---|---|']
    for item in report['stages']:
        summary.append('| '+item['id']+' | '+item['status']+' | '+item['reason'].replace('|','/')+' |')
    summary.extend(['', 'MPI ranks: '+str(report.get('parallelism',{}).get('mpi_ranks','not recorded'))+
                    ' (1 OpenMP thread per rank). Speedup is not guaranteed.',
                    'Unverified partial eig.csv and phase diagnostics may be included after failure; NEVER solver acceptance.',
                    'Data: QUALIFICATION.json and native/* manifest summaries (SHA-256 for actual files).',
                    'Mesh and large solver outputs remain in the temporary workspace and are deleted.',
               'Third-mesh memory is a conservative PRE-FLIGHT estimate only; WSL usage is NOT OS-enforced.',
               'Solver-index matching is not verified field-overlap mode identity.',
                    'A successful native run is NOT independently validated or qualified as a device design.',
                    'Fabrication remains HOLD.',''])
    files['QUALIFICATION.json'] = (json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
    files['SUMMARY.md'] = ('\n'.join(summary)+'\n').encode('utf-8')
    _zip_report(destination,files)
    notify_user('Saved shareable native EM evidence ZIP; scientific qualification remains blocked')
    return report
