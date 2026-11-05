"""Selectable, bounded development feedback with immutable numbered evidence."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import tempfile
import threading
import time
import zipfile
import sys

from .catalog import TASKS, BY_ID, load_plan, resolve_selection
from .scopes import scope_files

STATUSES = ('PASS', 'FAIL', 'BLOCKED', 'TIMEOUT', 'CANCELLED', 'SKIPPED_BY_PLAN')


def _json(data):
    return (json.dumps(data, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def compare_tasks(previous, current):
    """Compare common scope only; never infer progress from a smaller selection."""
    old = {r['id']: r for r in previous.get('tasks', []) if type(r) is dict and 'id' in r}
    rows = []
    for row in current.get('tasks', []):
        left = old.get(row['id'])
        if (not left or left.get('status') == 'SKIPPED_BY_PLAN'
                or row.get('status') == 'SKIPPED_BY_PLAN'):
            continue
        if (not left.get('scope_sha256') or left['scope_sha256'] != row.get('scope_sha256')):
            rows.append({'id': row['id'], 'status': 'NOT_COMPARABLE_SCOPE_CHANGED'})
        else:
            rows.append({'id': row['id'], 'previous': left['status'], 'current': row['status'],
                         'comparison': 'status_only_same_case_definition'})
    return {'schema': 'sqe.selected-test-comparison.v1', 'common_tasks': rows,
            'same_selection': previous.get('selection_sha256') == current.get('selection_sha256'),
            'count_delta_is_progress': False, 'native_data_reused': False,
            'note': 'Matching status does not establish numerical/physical equivalence between engine versions.'}


def _previous(root, destination, current):
    from ..cycle_qualification import NAME_PATTERN
    from ..feedback_qualification import _checked_members
    paths = [p for p in destination.parent.iterdir() if NAME_PATTERN.fullmatch(p.name) and p != destination]
    if not paths:
        return None
    path = max(paths, key=lambda p: int(NAME_PATTERN.fullmatch(p.name).group(1)))
    try:
        content = _checked_members(path)
        doc = json.loads(content['QUALIFICATION.json'])
        cycle = json.loads(content['CYCLE.json'])
        if (cycle.get('schema') != 'sqe.agent-cycle-feedback.v1'
                or cycle.get('report_sequence') != int(NAME_PATTERN.fullmatch(path.name).group(1))
                or cycle.get('release') != 'RC14.12'):
            raise ValueError('Prior cycle identity mismatch')
        comparison = compare_tasks(doc, current)
        return {'report_name': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                'status': 'HASH_VERIFIED_METADATA_ONLY', 'comparison': comparison}
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile):
        return {'report_name': path.name, 'status': 'REJECTED_PRIOR_REPORT_NO_REUSE'}


def _publish(destination, members):
    from ..feedback_qualification import _checked_members
    members = dict(members)
    members['INTEGRITY.json'] = _json({'schema': 'sqe.qualification-file-hashes.v1',
        'files': {n: sha256(b).hexdigest() for n, b in sorted(members.items())}})
    partial = destination.with_name(destination.name+'.partial')
    created = False
    try:
        with zipfile.ZipFile(partial, 'x', zipfile.ZIP_DEFLATED, compresslevel=8) as z:
            created = True
            for name, data in sorted(members.items()):
                z.writestr(name, data)
        _checked_members(partial)
        os.link(partial, destination)  # Atomic create-only, same as the legacy publisher.
    finally:
        if created:
            partial.unlink(missing_ok=True)


def run_selected(root, destination, selected, *, notify=None, cancel=None):
    from .. import __version__
    from ..cycle_qualification import NAME_PATTERN, _report_folder, _case_record
    from ..qualification import _run, _safe_log
    from ..feedback_qualification import _checked_members

    root = Path(root).resolve(strict=True)
    destination = Path(destination).absolute()
    selection = resolve_selection(selected)
    if destination.parent != _report_folder(root) or not NAME_PATTERN.fullmatch(destination.name):
        raise ValueError('Use an incrementally numbered release-local report')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Report already exists')
    reservation = destination.with_name(destination.name+'.running')
    fd = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    emit = notify or (lambda msg: None)
    stop = threading.Event()
    cancel = cancel or threading.Event()
    began = time.monotonic()
    state = {'task': 'preparation'}
    events = []
    def say(message):
        try:
            emit(message)
        except Exception:
            pass
    def heartbeat():
        while not stop.wait(10):
            say(f'HEARTBEAT elapsed={int(time.monotonic()-began)}s task={state["task"]} (controller only)')
    thread = threading.Thread(target=heartbeat, daemon=True, name='sqe-m17-heartbeat')
    thread.start()
    members = {}
    rows = []
    plan_sha = None
    selection_sha = sha256(_json(selection)).hexdigest()
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        try:
            plan, plan_sha = load_plan(root)
            plan_error = None
        except (OSError, ValueError, TypeError, KeyError) as exc:
            plan = {'wall_budget_s': 3600, 'packaging_reserve_s': 120}
            plan_error = 'INVALID_RELEASE_PLAN_' + type(exc).__name__
        # Some locked-down hosts fall back to cwd when their OS temp is not
        # writable. Keep all transient work in the verified excluded report
        # area, never inside the inventoried source tree.
        with tempfile.TemporaryDirectory(prefix='.m17-work-', dir=destination.parent) as td:
            temp = Path(td)
            private = (str(root), str(temp), str(Path.home()), os.environ.get('USERPROFILE', ''))
            def sanitize(obj):
                if type(obj) is str:
                    return _safe_log(obj, private)
                if type(obj) is list:
                    return [sanitize(v) for v in obj]
                if type(obj) is dict:
                    return {k: sanitize(v) for k, v in obj.items()}
                return obj
            env = dict(os.environ)
            private_temp = temp/'process-temp'
            private_temp.mkdir(mode=0o700)
            env.update(PYTHONPATH=str(root/'src'), PYTHONDONTWRITEBYTECODE='1',
                       OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PIP_NO_INDEX='1',
                       TMPDIR=str(private_temp), TEMP=str(private_temp), TMP=str(private_temp))
            say('TASKS_TOTAL ' + str(len(selection['resolved'])))
            for task in TASKS:
                if task.id not in selection['resolved']:
                    reason = 'SUBSUMED_BY_EM_CONVERGENCE' if task.id in selection['superseded'] else 'NOT_SELECTED'
                    rows.append({'id': task.id, 'title': task.title, 'status': 'SKIPPED_BY_PLAN', 'reason': reason})
                    continue
                state['task'] = task.id
                say('TASK_START '+task.id+' · '+task.title)
                before = time.monotonic()
                deps = {r['id']: r['status'] for r in rows}
                if cancel.is_set():
                    result = {'status': 'CANCELLED', 'reason': 'STOP_AFTER_CURRENT_TASK_REQUESTED'}
                elif plan_error:
                    result = {'status': 'FAIL' if task.id == 'integrity' else 'BLOCKED', 'reason': plan_error}
                elif any(deps.get(i) != 'PASS' for i in task.dependencies):
                    result = {'status': 'BLOCKED', 'reason': 'REQUIRED_PREREQUISITE_NOT_PASSED'}
                else:
                    remaining = plan['wall_budget_s']-plan['packaging_reserve_s']-(time.monotonic()-began)
                    if remaining < task.timeout_s:
                        result = {'status': 'BLOCKED', 'reason': 'WALL_TIME_BUDGET_RESERVED_FOR_REPORT'}
                    else:
                        output = temp/(task.id+'.json')
                        code, log, seconds = _run([sys.executable,
                            str(root/'src/sqe_studio/testing/task_worker.py'), task.id, str(root), str(output)],
                            root, env, max(1, min(task.timeout_s, int(remaining))))
                        members['logs/'+task.id+'.txt'] = _safe_log(log[-160000:], private).encode()
                        if code is None:
                            result = {'status': 'TIMEOUT', 'reason': 'SUPERVISED_TASK_TIMEOUT_OR_SPAWN'}
                        elif code != 0 or not output.is_file() or output.is_symlink() or output.stat().st_size > 1_000_000:
                            result = {'status': 'FAIL', 'reason': 'TASK_DID_NOT_PRODUCE_BOUNDED_RESULT'}
                        else:
                            try:
                                result = sanitize(json.loads(output.read_text(encoding='utf-8')))
                                if type(result) is not dict or result.get('status') not in STATUSES[:4]:
                                    raise ValueError('Invalid task status')
                            except (ValueError, OSError, TypeError):
                                result = {'status': 'FAIL', 'reason': 'INVALID_TASK_RESULT'}
                        if task.id in ('em', 'em_convergence'):
                            subreport = temp/task.id/'em.zip'
                            if subreport.is_file():
                                try:
                                    payload = _checked_members(subreport)
                                    for name, data in payload.items():
                                        if name != 'INTEGRITY.json':
                                            members['em/'+name] = data
                                except (ValueError, OSError, zipfile.BadZipFile):
                                    result = {'status': 'FAIL', 'reason': 'NATIVE_SUBREPORT_INTEGRITY_FAILED'}
                # Scope fingerprints describe the case implementation, not a user's paths.
                files = scope_files(root,task.id)
                if task.id == 'extraction':
                    for evidence in sorted((temp/task.id/'extraction').glob('*.json')):
                        if evidence.is_symlink() or evidence.stat().st_size>200000:
                            raise ValueError('Unsafe extraction evidence')
                        members['extraction/'+evidence.name]=evidence.read_bytes()
                scope = sha256(_json({'task': task.id, 'plan': plan_sha,
                    'implementation': [sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink()
                        else 'MISSING_OR_LINKED' for p in files]})).hexdigest()
                row = {**result, 'id': task.id, 'title': task.title, 'purpose': task.purpose,
                       'scope_sha256': scope, 'duration_s': round(time.monotonic()-before, 3),
                       'dependencies': list(task.dependencies)}
                rows.append(row)
                events.append({'task': task.id, 'status': row['status'], 'elapsed_s': round(time.monotonic()-began, 2)})
                say('TASK_END '+task.id+' '+row['status'])
        state['task'] = 'report'
        counts = Counter(r['status'] for r in rows)
        coarse = {'PASS': counts['PASS'], 'FAIL': counts['FAIL'],
                  'BLOCKED': counts['BLOCKED']+counts['TIMEOUT']+counts['CANCELLED']}
        document = {'schema': 'sqe.selected-development-feedback.v2', 'profile': 'selected_development',
                    'runtime_version': __version__, 'milestone': 'M20',
                    'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'counts': coarse, 'execution_counts': {k: counts[k] for k in STATUSES},
                    'selection': selection, 'selection_sha256': selection_sha, 'plan_sha256': plan_sha,
                    'tasks': rows, 'scientific_qualification': 'NOT_ESTABLISHED',
                    'fabrication': 'HOLD', 'rc_status': 'BLOCKED_NOT_RELEASE_CANDIDATE',
                    'native_concurrency': 1, 'partial_scope': len(selection['resolved']) < len(TASKS),
                    'cancel_policy': 'finish_current_bounded_task_then_package',
                    'duration_s': round(time.monotonic()-began, 2)}
        prior = _previous(root, destination, document)
        cycle = {'schema': 'sqe.agent-cycle-feedback.v1', 'release': 'RC14.12',
                 'runtime_version': __version__, 'milestone': 'M20',
                 'report_sequence': int(NAME_PATTERN.fullmatch(destination.name).group(1)),
                 'finished_utc': document['finished_utc'], 'plan_sha256': plan_sha,
                 'baseline_source_sha256': sha256((root/'EDA_SOURCE_MANIFEST.json').read_bytes()).hexdigest(),
                 'research_protocol': 'owner_authorized_selected_development_not_physical_approval',
                 'unchanged_native_runs_reused': False, 'selection_sha256': selection_sha,
                 'prior_report': prior, 'benchmark_case_evidence': 'BENCHMARK_CASE_MATRIX.json',
                 'agent_feedback': {'analysis_contract': 'compare common test scope; numeric vs physical evidence separate'}}
        by_id = {r['id']: r for r in rows}
        mapping = {'B00': 'regression', 'B01': 'cad', 'B02': 'em_convergence' if 'em_convergence' in selection['resolved'] else 'em',
                   'B03': 'em_convergence' if 'em_convergence' in selection['resolved'] else 'field_compare',
                   'B05': 'rf', 'B08': 'quantum', 'B09': 'rf'}
        cases = []
        for i in range(12):
            case = f'B{i:02d}'
            task = by_id.get(mapping.get(case))
            reason = ('SKIPPED_BY_PLAN' if task and task['status'] == 'SKIPPED_BY_PLAN' else
                      'PARTIAL_CASE_SEE_TASK_SUBSTEPS' if task and task['status'] == 'PASS' else
                      'CASE_NOT_IMPLEMENTED' if not task else 'TASK_'+task['status'])
            cases.append(_case_record(case, status='FAIL' if task and task['status'] == 'FAIL' else 'BLOCKED',
                execution='NATIVE' if task and task.get('execution_kind') == 'NATIVE' else 'NOT_RUN', reason=reason,
                scientific_limitations='B00-B11 full-case acceptance is separate from the selected task substeps.'))
        members.update({
            'QUALIFICATION.json': _json(document), 'CYCLE.json': _json(cycle),
            'TEST_SELECTION.json': _json({'schema': 'sqe.selected-test-plan.v1', **selection,
                                         'selection_sha256': selection_sha, 'plan_sha256': plan_sha}),
            'PROGRESS.json': _json({'schema': 'sqe.selected-progress.v1', 'events': events,
                                   'heartbeat_is_not_solver_convergence': True}),
            'BENCHMARK_CASE_MATRIX.json': _json({'schema': 'sqe.scientific-benchmark-evidence.v1',
                'cases': cases, 'qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}),
            'AUTOMATIC_TEST_DIAGNOSTICS.json': _json({'schema': 'sqe.selected-diagnostics.v2',
                'tasks': [{'id': r['id'], 'status': r['status'], 'reason': r.get('reason')} for r in rows],
                'prior_report': prior, 'native_results_reused': False}),
            'ENVIRONMENT.json': _json({'schema': 'sqe.test-environment.v1', 'os': platform.system(),
                'python': platform.python_version(), 'architecture': platform.machine(),
                'packages': {name: _version(name) for name in ('pytest', 'scqubits', 'numpy', 'scipy', 'qutip', 'vtk', 'pyvista', 'quantum-metal', 'gmsh')},
                'thread_budget': {'OMP_NUM_THREADS': 1, 'OPENBLAS_NUM_THREADS': 1, 'MKL_NUM_THREADS': 1}}),
        })
        lines = ['# SQE Studio M20 - Automatic Test', '', 'Runtime: '+__version__,
                 'Selected: '+', '.join(selection['requested']),
                 'Automatic prerequisites: '+', '.join(selection['automatic_prerequisites']), '',
                 '## Current-run test outcomes (excluded tests never count as passed)', '',
                 '| Test | Status | Seconds |', '|---|---|---|']
        lines += [f'| {r["title"]} | {r["status"]} | {r.get("duration_s", "-")} |' for r in rows]
        lines += ['', 'Native execution, basis stability and literature comparison are separate substeps.',
                  'Physical qualification NOT ESTABLISHED; fabrication HOLD.',
                  'Share this original numbered ZIP. No user projects or raw native fields are included.',
                  'Cancellation takes effect after the current bounded task.',
                  'Compare common task scope; changing the selection is not scientific progress.']
        members['SUMMARY.md'] = ('\n'.join(lines)+'\n').encode()
        _publish(destination, members)
        say('REPORT_READY '+destination.name)
        return document
    except Exception as exc:
        # A controller failure must still yield bounded, shareable diagnostics.
        if destination.exists():
            raise
        message = _safe_log(type(exc).__name__+': '+str(exc)[:1000],
                            (str(root), str(Path.home()), os.environ.get('USERPROFILE','')))
        failed = {'schema': 'sqe.selected-development-feedback.v2', 'profile': 'selected_development',
                  'runtime_version': __version__, 'milestone': 'M20',
                  'counts': {'PASS':0,'FAIL':1,'BLOCKED':0},
                  'execution_counts': {s:int(s=='FAIL') for s in STATUSES},
                  'tasks': rows, 'controller_error': message,
                  'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD',
                  'rc_status': 'BLOCKED_NOT_RELEASE_CANDIDATE'}
        fallback = dict(members)
        source_hash = sha256((root/'EDA_SOURCE_MANIFEST.json').read_bytes()).hexdigest() if (root/'EDA_SOURCE_MANIFEST.json').is_file() else None
        fallback.update({'QUALIFICATION.json': _json(failed),
            'CYCLE.json': _json({'schema':'sqe.agent-cycle-feedback.v1','release':'RC14.12',
                'runtime_version':__version__,'milestone':'M20',
                'report_sequence':int(NAME_PATTERN.fullmatch(destination.name).group(1)),
                'finished_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'plan_sha256':plan_sha,'baseline_source_sha256':source_hash,
                'unchanged_native_runs_reused':False,'controller_failure':True}),
            'TEST_SELECTION.json': _json(selection),
            'SUMMARY.md': ('# Automatic Test controller failure\n\n'+message+
                           '\nCompleted work is not a scientific qualification.\n').encode(),
            'PROGRESS.json': _json({'events':events})})
        _publish(destination, fallback)
        say('REPORT_READY '+destination.name+' (controller failure diagnostics)')
        return failed
    finally:
        stop.set()
        thread.join(timeout=2)
        reservation.unlink(missing_ok=True)


def _version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def result_exit_code(result):
    """A successful process must mean every selected task actually passed."""
    counts = result.get('counts', {})
    rows = result.get('tasks', [])
    if counts.get('FAIL', 0) or any(row.get('status') == 'FAIL' for row in rows):
        return 1
    selected = result.get('selection', {}).get('resolved', [])
    executed = [row for row in rows if row.get('id') in selected]
    if (counts.get('BLOCKED', 0) or not selected or len(executed) != len(selected)
            or {row.get('id') for row in executed} != set(selected)
            or any(row.get('status') != 'PASS' for row in executed)):
        return 2
    return 0


def main():
    import argparse
    from .catalog import PROFILES
    from ..cycle_qualification import next_report_path
    parser = argparse.ArgumentParser(description='Run a trusted Automatic Test profile from an extracted source.')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--profile', choices=tuple(PROFILES), default='recommended')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    result = run_selected(root, next_report_path(root), PROFILES[args.profile], notify=print)
    print(json.dumps(result['execution_counts'], sort_keys=True))
    return result_exit_code(result)


if __name__ == '__main__':
    raise SystemExit(main())
