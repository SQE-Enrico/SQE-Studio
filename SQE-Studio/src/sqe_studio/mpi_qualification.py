"""Opt-in Palace MPI scaling diagnostic through the existing native adapter.

One production deck-only worker creates and hash-verifies a reviewed native
mesh/deck. Identical trusted input bytes are copied into isolated folders for
multiple MPI ranks and the *same* production Palace launcher is called. This
is a performance diagnostic, not a production solve/result or physics approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from .contracts import digest
from .interop.laptop_benchmark import resonator_project, approve_exploratory_stack, _native_eig
from .native_em_qualification import _zip_report, ASSUMPTIONS, SOURCE_URL
from .orchestration.artifacts import verify_manifest, safe_file
from .interop.em_convergence import palace_log_metrics
from .interop.palace_parallel import mpi_plan
from .qualification import _run, _safe_log


def validate_ranks(ranks):
    if (type(ranks) is not tuple or not 2 <= len(ranks) <= 3 or
        any(type(rank) is not int or not 1 <= rank <= 16 for rank in ranks) or
        len(set(ranks)) != len(ranks) or tuple(sorted(ranks)) != ranks):
        raise ValueError('Select two or three strictly increasing MPI ranks, each 1..16')
    return ranks


def _copy_verified_inputs(source, target, digest_map):
    """Hash each original and copy; reject symlinks/changed provenance."""
    target.mkdir(parents=True, exist_ok=False)
    for name in ('sqe_em.msh', 'sqe_em.json'):
        relative = 'sqe_em/'+name
        original = safe_file(source,relative)
        expected = digest_map.get(relative)
        if (not isinstance(expected,str) or len(expected)!=64 or
                hashlib.sha256(original.read_bytes()).hexdigest()!=expected):
            raise ValueError('Verified native mesh/deck changed before performance replay')
        copy = target/name
        shutil.copyfile(original,copy,follow_symlinks=False)
        if hashlib.sha256(copy.read_bytes()).hexdigest()!=expected:
            raise ValueError('Native input changed during isolated MPI replay')
    return True


def qualify_mpi_profile(source: Path, destination: Path, *, reviewer: str,
                        acknowledged: bool, ranks=(2,4), notify=None):
    """Generate one real mesh, then benchmark 2/4 or 2/4/6 native MPI ranks.

    Failure still yields a report. Does not touch saved designs or cache meshes
    across separate sessions, and does not claim mode equivalence/qualification.
    """
    validate_ranks(ranks)
    if not acknowledged or not isinstance(reviewer,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,47}',reviewer):
        raise ValueError('Explicit material acknowledgement and reviewer ID required')
    root=Path(source).resolve(strict=True)
    destination=Path(destination).expanduser().absolute()
    if (destination.suffix.lower()!='.zip' or destination.is_symlink() or
        destination.is_relative_to(root)):
        raise ValueError('ZIP destination must be outside the application source')
    if not (root/'src/sqe_studio/worker.py').is_file():
        raise ValueError('Missing native production worker')
    destination.parent.mkdir(parents=True,exist_ok=True)
    files={}
    report={'schema':'sqe.native-mpi-benchmark.v1',
            'started_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'reference':'same explicitly reviewed temporary CPW; NOT published geometry validation',
            'requested_mpi_ranks':list(ranks),'stages':[],
            'fabrication_status':'HOLD','rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE',
            'scientific_qualification':'not_established'}
    def stage(name,status,reason,**details):
        record={'id':name,'status':status,'reason':reason,**details}
        report['stages'].append(record)
        if notify:notify(f'{status}: {name} — {reason}')
    with tempfile.TemporaryDirectory(prefix='sqe-palace-mpi-') as temp:
        work=Path(temp)
        substitutions=(str(root),str(work),str(Path.home()),os.environ.get('USERPROFILE',''))
        env=os.environ.copy()
        env.update({'HOME':str(work/'home'),'USERPROFILE':str(work/'home'),
                    'XDG_CACHE_HOME':str(work/'cache'), 'XDG_CONFIG_HOME':str(work/'config'),
                    'PYTHONPATH':str(root/'src'),'PYTHONDONTWRITEBYTECODE':'1',
                    'PYTHONNOUSERSITE':'1','QT_QPA_PLATFORM':'offscreen'})
        (work/'home').mkdir()
        review=work/'review.txt'
        review.write_text('Exploratory test only\n'+ASSUMPTIONS+'\n',encoding='utf-8')
        model=resonator_project(execution='deck_only')
        reviewed, record=approve_exploratory_stack(model,reviewer=reviewer,
                                                   document=review,source_url=SOURCE_URL)
        report['review']={'assumptions':ASSUMPTIONS,'record':record}
        stage('physical_assumptions','PASS','Operator acknowledged reference only, not design approval')
        # Single real production A02/A03 worker; no mock or geometry fallback.
        from .interop.palace_parallel import mpi_plan
        try:
            probe=mpi_plan('auto')
            report['host_resource_probe']=probe.get('resources')
            cpus=probe.get('resources',{}).get('logical_cpus')
            if cpus and any(r>cpus for r in ranks):
                stage('mpi_resource_preflight','BLOCKED','Requested MPI rank exceeds WSL logical CPU visibility')
            else:
                stage('mpi_resource_preflight','PASS','Rank request fits WSL CPU visibility; RAM remains unbounded')
        except Exception as exc:
            stage('mpi_resource_preflight','BLOCKED','Unable to probe resource limits: '+type(exc).__name__)
        if not any(s['id']=='mpi_resource_preflight' and s['status']=='PASS' for s in report['stages']):
            # Never start an expensive job with an unverified CPU preflight.
            pass
        else:
            snapshot={'project':reviewed,'study':reviewed['studies'][0],
                      'revision_id':digest(reviewed)[:32],
                      'project_digest':digest(reviewed),'parents':[]}
            snapshot_file=work/'snapshot.json'
            snapshot_file.write_text(json.dumps(snapshot,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
            native=work/'generated'
            code, log, elapsed=_run([sys.executable,'-m','sqe_studio.worker',str(snapshot_file),str(native)],root,env,330)
            files['logs/mesh-preparation.txt']=(_safe_log(log,substitutions)+'\n').encode()
            if code != 0 or not (native/'RESULT_MANIFEST.json').is_file():
                stage('one_native_mesh','FAIL','Production deck-only worker did not return verified output',
                      exit_code=code,elapsed_seconds=elapsed)
            else:
                try:
                    verify_manifest(native,revision_id=snapshot['revision_id'],
                                    project_digest=snapshot['project_digest'],
                                    study_id='ResEigen',engine='sqdmetal_palace')
                    manifest=json.loads((native/'RESULT_MANIFEST.json').read_text(encoding='utf-8'))
                    artifacts={a['name']:a['sha256'] for a in manifest['artifacts']}
                    if not {'sqe_em/sqe_em.msh','sqe_em/sqe_em.json'} <= artifacts.keys():
                        raise ValueError('Mesh/deck missing from verified production manifest')
                    report['shared_input_sha256']={k:artifacts[k] for k in ('sqe_em/sqe_em.msh','sqe_em/sqe_em.json')}
                    stage('one_native_mesh','PASS','One production worker generated and hash-verified mesh/deck',elapsed_seconds=elapsed)
                    from .adapters.sqdmetal_palace_adapter import _palace_readiness, _run_palace
                    readiness=_palace_readiness()
                    measurements=[]
                    for rank in ranks:
                        tag=f'mpi_{rank}'
                        folder=work/tag/'sqe_em'
                        try:
                            _copy_verified_inputs(native,folder,artifacts)
                            completed=_run_palace(readiness,folder,'sqe_em.json',rank)
                            # Solver is never allowed to rewrite the reviewed mesh/deck.
                            for input_name in ('sqe_em.msh','sqe_em.json'):
                                expected=artifacts['sqe_em/'+input_name]
                                if hashlib.sha256((folder/input_name).read_bytes()).hexdigest()!=expected:
                                    raise ValueError('Solver changed its verified native input: '+input_name)
                            eig=folder/'outputFiles'/'eig.csv'
                            modes=_native_eig(eig)
                            if len(modes)!=1:
                                raise ValueError('Reference requires exactly one native mode')
                            local_log=folder/'palace-native.log'
                            if local_log.is_symlink() or not local_log.is_file() or local_log.stat().st_size>20_000_000:
                                raise ValueError('Native log missing or too large')
                            metrics=palace_log_metrics(local_log.read_text(encoding='utf-8',errors='replace'))
                            if not metrics['solver_converged_tol_in_log']:
                                raise ValueError('Solver did not report CONVERGED_TOL')
                            row={'mpi_ranks':rank,'solver_wall_seconds':completed['elapsed_seconds'],
                                 'frequency_GHz':modes[0]['frequency_GHz'],
                                 'mesh_sha256':artifacts['sqe_em/sqe_em.msh'],
                                 'deck_sha256':artifacts['sqe_em/sqe_em.json'],**metrics,
                                 'eig_csv_sha256':hashlib.sha256(eig.read_bytes()).hexdigest()}
                            measurements.append(row)
                            files[f'native/{tag}-eig.csv']=eig.read_bytes()
                            files[f'logs/{tag}.txt']=(_safe_log(local_log.read_text(encoding='utf-8',errors='replace'),substitutions)+'\n').encode()
                            stage(tag,'PASS','Palace ran on identical verified mesh/deck',mpi_ranks=rank,
                                  elapsed_seconds=completed['elapsed_seconds'])
                        except Exception as exc:
                            native_log=folder/'palace-native.log'
                            if native_log.is_file() and not native_log.is_symlink() and native_log.stat().st_size <= 20_000_000:
                                files[f'logs/{tag}.txt']=(_safe_log(native_log.read_text(encoding='utf-8',errors='replace'),substitutions)+'\n').encode()
                            phase=folder/'palace-phases.json'
                            if phase.is_file() and not phase.is_symlink() and phase.stat().st_size <= 16_000:
                                files[f'native/{tag}-phases-UNVERIFIED.json']=phase.read_bytes()
                            stage(tag,'FAIL','Native MPI trial failed; not promoted as a scientific result',
                                  exception_type=type(exc).__name__,message=str(exc)[:250])
                            break
                    if measurements:
                        baseline=measurements[0]
                        report['measurements']=measurements
                        report['scaling']=[{'mpi_ranks':r['mpi_ranks'],
                            'relative_speedup_vs_first':baseline['solver_wall_seconds']/r['solver_wall_seconds'],
                            'frequency_drift_relative_vs_first':abs(r['frequency_GHz']-baseline['frequency_GHz'])/max(r['frequency_GHz'],baseline['frequency_GHz'])}
                            for r in measurements]
                        report['performance_status']='MEASURED_SINGLE_RUN_PER_RANK_NOT_STATISTICAL'
                        report['mode_identity']='NOT_ESTABLISHED_NO_FIELD_OVERLAP'
                except Exception as exc:
                    stage('mpi_trials','FAIL','Native input validation/solver setup failed',
                          exception_type=type(exc).__name__,message=str(exc)[:250])
    counts={state:sum(x['status']==state for x in report['stages']) for state in ('PASS','FAIL','BLOCKED')}
    report['counts']=counts
    report['finished_utc']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    files['QUALIFICATION.json']=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
    summary=['# SQE Studio — Palace MPI scaling on one verified native mesh','',
             'Scientific qualification: NOT ESTABLISHED; fabrication HOLD.',
             'Same mesh/deck input SHA-256 across runs; MPI ranks vary. No personal designs read.',
             'Results are single-run performance diagnostics, not guaranteed scaling or field mode matching.','']
    summary += [f"- {x['status']}: {x['id']}: {x['reason']}" for x in report['stages']]
    files['SUMMARY.md']=('\n'.join(summary)+'\n').encode()
    _zip_report(destination,files)
    return report
