"""Single-native-process laptop job lifecycle and revision-bound cache/sweeps.

The baseline HTTP start/archive API is preserved. A08 owns routes for the new
cancel, status, retry and sweep methods; no routes are changed by this agent.
"""
from __future__ import annotations
import io
import json
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from .contracts import digest
from .orchestration.artifacts import (ArtifactInvalid, adapter_digest, engine_version,
                                     fingerprint, parent_for_run, verify_manifest)
from .orchestration.sweep import plan_sweep
from .store import Conflict

MAX_SECONDS = 180
MAX_SWEEP_SECONDS = 600
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 150 * 1024 * 1024
MAX_ATTEMPTS = 3
POLL_SECONDS = 0.15
PROCESS_TERMINATE_GRACE = 3

# Cross-Service process-wide exclusion for the same workspace. A separate
# Windows process requires an exclusive OS lock, proposed for A08/A09.
_GLOBAL_GUARD = threading.Lock()
_WORKSPACE_LOCKS = {}


def _workspace_lock(root):
    with _GLOBAL_GUARD:
        return _WORKSPACE_LOCKS.setdefault(str(Path(root).resolve()), threading.Lock())


@dataclass
class _Control:
    cancel: threading.Event = field(default_factory=threading.Event)
    process: subprocess.Popen | None = None


class Jobs:
    def __init__(self, store):
        self.store = store
        self.lock = _workspace_lock(store.root)
        self._mutex = threading.RLock()
        self._active: dict[str, _Control] = {}
        self._slot_file = None

    def _acquire_slot(self):
        if not self.lock.acquire(blocking=False):
            raise Conflict('One native engine job at a time (laptop limit)')
        handle = None
        try:
            handle = (self.store.root / '.native-job.lock').open('a+b')
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'\x00')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._slot_file = handle
        except (OSError, BlockingIOError) as exc:
            if handle is not None:
                handle.close()
            self.lock.release()
            raise Conflict('Another SQE process holds the laptop native-engine slot') from exc

    def _release_slot(self):
        try:
            if self._slot_file is not None:
                try:
                    self._slot_file.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(self._slot_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self._slot_file.fileno(), fcntl.LOCK_UN)
                finally:
                    self._slot_file.close()
                    self._slot_file = None
        finally:
            self.lock.release()

    def _project(self, user, pid, rev, study_id):
        project = self.store.project(user, pid)
        if rev != project['head'] or project['revision'] != rev:
            raise Conflict('Cannot execute a stale revision')
        if project['revision_digest'] != digest(project['model']):
            raise Conflict('Saved revision digest does not match its immutable snapshot')
        studies = [s for s in project['model']['studies'] if s['id'] == study_id]
        if len(studies) != 1:
            raise ValueError('Save a valid study in the project before executing')
        return project, studies[0]

    def _candidate_cache(self, user, pid, rev, study, project_digest, parent_hashes):
        native_version = engine_version(study['engine'])
        if not native_version:  # Unknown/native CLI runtime: never reuse an unverified cache.
            return None
        key = fingerprint(revision_id=rev, project_digest=project_digest, study=study,
                          native_version=native_version, adapter_sha256=adapter_digest(study['engine']),
                          parent_sha256=parent_hashes)
        for run in self.store.runs(user, pid):
            if (run['revision_id'], run['study_id'], run['engine'], run['state']) != (rev, study['id'], study['engine'], 'completed'):
                continue
            info = self.store.run(user, pid, run['id'])
            try:
                ref = verify_manifest(Path(info['path']) / 'output', revision_id=rev,
                                      project_digest=project_digest, study_id=study['id'],
                                      engine=study['engine'], cache_fingerprint=key)
                if ref.engine_version == native_version:
                    return run['id']
            except (OSError, ArtifactInvalid, ValueError):
                continue
        return None

    def start(self, user, pid, rev, study_id, *, parents=(), force=False):
        """Run saved study; cache only byte-verified current native results."""
        return self._submit(user, pid, rev, study_id, parents=parents, force=force)

    def start_sweep(self, user, pid, rev, study_id, axes, *, mode='manual', selected=None):
        """One run record, up to 24 ordered native points; never parallel jobs."""
        project, study = self._project(user, pid, rev, study_id)
        points = plan_sweep(study, axes, mode=mode, selected=selected)
        return self._submit(user, pid, rev, study_id, points=points, mode=mode,
                            force=True)

    def _submit(self, user, pid, rev, study_id, *, parents=(), force=False,
                points=None, mode=None, retry_of=None, attempt=1):
        project, study = self._project(user, pid, rev, study_id)
        project_sha = project['revision_digest']
        if not isinstance(parents, (tuple, list)) or len(parents) > 32 or any(not isinstance(r, str) for r in parents):
            raise ValueError('Invalid parent run identities')
        parent_refs = tuple(parent_for_run(self.store, user, pid, run_id, revision_id=rev,
                                          project_digest=project_sha) for run_id in parents)
        if parent_refs:
            # A01 must provide the typed reviewed map before source artifacts
            # can feed another native scientific engine. Never guess a bridge.
            raise Conflict('Typed cross-engine input mapping/review not yet integrated by A01')
        if points is None and not force:
            hit = self._candidate_cache(user, pid, rev, study, project_sha, ())
            if hit:
                if not self._head_current(user, pid, rev):
                    raise Conflict('Cached output is from an old revision')
                return hit
        self._acquire_slot()
        folder = self.store.root / 'native-runs' / pid / uuid.uuid4().hex
        registered = False
        try:
            project, study = self._project(user, pid, rev, study_id)
            if project_sha != project['revision_digest']:
                raise Conflict('Revision changed during job submission')
            if points is None and not force:
                hit = self._candidate_cache(user, pid, rev, study, project_sha, ())
                if hit:
                    self._release_slot()
                    return hit
            folder.mkdir(parents=True, exist_ok=False, mode=0o700)
            expected = engine_version(study['engine'])
            snapshot = {'project': project['model'], 'project_digest': project_sha,
                        'revision_id': rev, 'study': study, 'parents': [p.as_parent() for p in parent_refs],
                        'expected_engine_version': expected,
                        'expected_adapter_sha256': adapter_digest(study['engine']),
                        'submitted_at_utc': time.time(), 'attempt': attempt,
                        'retry_of': retry_of}
            if points is not None:
                snapshot['sweep_plan'] = {'mode': mode, 'points': [
                    {'index': p.index, 'study': p.study,
                     'options_digest': p.options_digest,
                     'coordinates': list(map(list, p.coordinates))} for p in points]}
            _atomic_json(folder / 'snapshot.json', snapshot)
            self.store.put_run(user, pid, rev, study_id, study['engine'], folder)
            registered = True
            control = _Control()
            with self._mutex:
                self._active[folder.name] = control
                _progress(folder, 'queued', 0, len(points) if points else 1)
            thread = threading.Thread(target=self._work,
                                      args=(user, pid, rev, folder, control), daemon=True,
                                      name='sqe-native-' + folder.name[:8])
            thread.start()
            return folder.name
        except BaseException:
            try:
                with self._mutex:
                    self._active.pop(folder.name, None)
                if not registered:
                    shutil.rmtree(folder, ignore_errors=True)
                else:
                    self.store.set_run(folder.name, 'failed')
            finally:
                self._release_slot()
            raise

    def _head_current(self, user, pid, rev):
        try:
            project = self.store.project(user, pid)
            return project['head'] == rev
        except Exception:
            return False

    def _execute(self, folder, snapshot, output, log_path, control, deadline):
        output.mkdir(parents=True, exist_ok=False)
        snap_file = folder / ('snapshot.json' if log_path.name == 'engine.log' else log_path.stem + '.snapshot.json')
        if snap_file.name != 'snapshot.json':
            _atomic_json(snap_file, snapshot)
        else:
            # The original, immutable submitted snapshot already exists.
            pass
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get('PYTHONPATH', '')
        argv = [sys.executable, '-m', 'sqe_studio.worker', str(snap_file), str(output)]
        with log_path.open('wb') as log:
            popen_options = {'cwd': str(folder), 'env': env, 'stdout': log,
                             'stderr': subprocess.STDOUT, 'shell': False}
            if os.name == 'nt':
                popen_options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_options['start_new_session'] = True
            proc = subprocess.Popen(argv, **popen_options)
            with self._mutex:
                control.process = proc
            timed_out = False
            over_limit = False
            try:
                while proc.poll() is None:
                    if control.cancel.is_set():
                        _stop(proc)
                        return 'cancelled'
                    if time.monotonic() >= deadline:
                        timed_out = True
                        _stop(proc)
                        break
                    if log_path.stat().st_size > MAX_LOG_BYTES:
                        over_limit = True
                        _stop(proc)
                        break
                    try:
                        proc.wait(timeout=min(POLL_SECONDS, max(0.01, deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        pass
                if control.cancel.is_set():
                    return 'cancelled'
                if timed_out:
                    return 'timed_out'
                if over_limit or log_path.stat().st_size > MAX_LOG_BYTES:
                    return 'failed'
                return 'completed' if proc.returncode == 0 else 'failed'
            finally:
                with self._mutex:
                    control.process = None

    def _work(self, user, pid, rev, folder, control):
        result = 'failed'
        finished = []
        try:
            snapshot = json.loads((folder / 'snapshot.json').read_text(encoding='utf8'))
            points = snapshot.get('sweep_plan', {}).get('points')
            total = len(points) if points is not None else 1
            deadline = time.monotonic() + (MAX_SWEEP_SECONDS if points else MAX_SECONDS)
            if control.cancel.is_set():
                result = 'cancelled'
                return
            if not self._head_current(user, pid, rev):
                result = 'stale'
                _atomic_json(folder / 'FAILURE.json', {'error': 'Head revision changed before worker dispatch', 'state': result})
                return
            self.store.set_run(folder.name, 'running')
            _progress(folder, 'native_running', 0, total)
            for ordinal in range(total):
                if control.cancel.is_set():
                    result = 'cancelled'
                    break
                if not self._head_current(user, pid, rev):
                    result = 'stale'
                    break
                if time.monotonic() >= deadline:
                    result = 'timed_out'
                    break
                if points is None:
                    point_snapshot = snapshot
                    out = folder / 'output'
                    log_path = folder / 'engine.log'
                else:
                    point = points[ordinal]
                    point_snapshot = {k: v for k, v in snapshot.items() if k != 'sweep_plan'}
                    point_snapshot['study'] = point['study']
                    point_snapshot['sweep_point'] = {
                        'mode': snapshot['sweep_plan']['mode'], 'index': point['index'],
                        'options_digest': point['options_digest'],
                        'coordinates': point['coordinates']}
                    out = folder / 'output' / f'point_{point["index"]:04d}'
                    log_path = folder / f'point_{point["index"]:04d}.engine.log'
                status = self._execute(folder, point_snapshot, out, log_path, control,
                                       min(deadline, time.monotonic() + MAX_SECONDS))
                if status != 'completed':
                    result = status
                    break
                _progress(folder, 'validating_native_artifacts', ordinal, total)
                try:
                    ref = verify_manifest(out, revision_id=rev, project_digest=snapshot['project_digest'],
                                          study_id=point_snapshot['study']['id'],
                                          engine=point_snapshot['study']['engine'])
                    if ref.engine_version != point_snapshot['expected_engine_version'] and point_snapshot['expected_engine_version'] is not None:
                        raise ArtifactInvalid('Native runtime changed during execution')
                    if ref.cache_fingerprint != fingerprint(
                            revision_id=rev, project_digest=snapshot['project_digest'],
                            study=point_snapshot['study'], native_version=ref.engine_version,
                            adapter_sha256=snapshot['expected_adapter_sha256']):
                        raise ArtifactInvalid('Incorrect native output fingerprint')
                except (ArtifactInvalid, OSError, ValueError) as exc:
                    result = 'failed'
                    _atomic_json(folder / 'VALIDATION_FAILURE.json', {'error': str(exc)[:600]})
                    break
                finished.append({'index': ordinal if points is None else points[ordinal]['index'],
                                 'manifest_sha256': ref.manifest_sha256,
                                 'cache_fingerprint': ref.cache_fingerprint})
                _progress(folder, 'native_point_completed', len(finished), total)
            else:
                result = 'completed'
            if points is not None:
                if finished and result != 'completed':
                    result = 'partial_failed' if result == 'failed' else result
                _atomic_json(folder / 'SWEEP_MANIFEST.json', {
                    'schema': 'sqe.sweep.v1', 'revision_id': rev,
                    'project_digest': snapshot['project_digest'],
                    'mode': snapshot['sweep_plan']['mode'], 'state': result,
                    'requested_points': total, 'verified_points': finished,
                    'next_unexecuted_index': len(finished),
                    'scientific_status': 'review_required', 'fabrication_status': 'HOLD'})
        except Exception as exc:
            result = 'failed'
            _atomic_json(folder / 'LIFECYCLE_FAILURE.json', {'error': type(exc).__name__ + ': ' + str(exc)[:600]})
        finally:
            with self._mutex:
                try:
                    if control.cancel.is_set() and result not in ('timed_out',):
                        result = 'cancelled'
                    self.store.set_run(folder.name, result)
                    _progress(folder, result, len(finished),
                              len(points) if 'points' in locals() and points is not None else 1)
                finally:
                    self._active.pop(folder.name, None)
                    self._release_slot()

    def cancel(self, owner, pid, run_id):
        """Request cooperative cancellation; worker terminates its subprocess."""
        info = self.store.run(owner, pid, run_id)
        with self._mutex:
            control = self._active.get(run_id)
            if not control or info['state'] not in ('queued', 'running', 'cancelling'):
                raise Conflict('Run cannot be cancelled or is not active in this service')
            control.cancel.set()
            self.store.set_run(run_id, 'cancelling')
        return {'run_id': run_id, 'state': 'cancelling'}

    def _check_completed_artifacts(self, info, *, require_current_environment=False):
        folder = Path(info['path'])
        snapshot = json.loads((folder / 'snapshot.json').read_text(encoding='utf8'))
        revision, source = info['revision_id'], snapshot['project_digest']
        if snapshot['revision_id'] != revision or digest(snapshot['project']) != source:
            raise ArtifactInvalid('Stored native snapshot no longer matches revision content')
        if require_current_environment:
            installed = engine_version(info['engine'])
            if not installed or installed != snapshot.get('expected_engine_version'):
                raise ArtifactInvalid('Native engine version absent or changed')
            if adapter_digest(info['engine']) != snapshot.get('expected_adapter_sha256'):
                raise ArtifactInvalid('Native adapter source has changed')
        plan = snapshot.get('sweep_plan')
        if plan is None:
            return (verify_manifest(folder / 'output', revision_id=revision,
                                    project_digest=source, study_id=info['study_id'],
                                    engine=info['engine']),)
        summary = json.loads((folder / 'SWEEP_MANIFEST.json').read_text(encoding='utf8'))
        points = plan['points']
        if (summary.get('state') != 'completed' or summary.get('revision_id') != revision or
                summary.get('project_digest') != source or
                summary.get('requested_points') != len(points) or
                len(summary.get('verified_points', [])) != len(points)):
            raise ArtifactInvalid('Incomplete or altered native sweep provenance')
        references = []
        for point, evidence in zip(points, summary['verified_points']):
            if evidence['index'] != point['index']:
                raise ArtifactInvalid('Sweep point order changed')
            ref = verify_manifest(folder / 'output' / f'point_{point["index"]:04d}',
                                  revision_id=revision, project_digest=source,
                                  study_id=info['study_id'], engine=info['engine'])
            if ref.manifest_sha256 != evidence['manifest_sha256'] or ref.cache_fingerprint != evidence['cache_fingerprint']:
                raise ArtifactInvalid('Native sweep artifact hash differs from recorded manifest')
            references.append(ref)
        return tuple(references)

    def status(self, owner, pid, run_id):
        info = self.store.run(owner, pid, run_id)
        progress_file = Path(info['path']) / 'PROGRESS.json'
        progress = json.loads(progress_file.read_text(encoding='utf8')) if progress_file.is_file() else None
        project = self.store.project(owner, pid)
        current = info['revision_id'] == project['head']
        verified_current = False
        evidence = 'not_completed'
        if info['state'] == 'completed':
            evidence = 'old_revision' if not current else 'native_environment_unverified'
            if current:
                try:
                    self._check_completed_artifacts(info, require_current_environment=True)
                    verified_current = True
                    evidence = 'current_native_artifacts_unqualified'
                except (ArtifactInvalid, OSError, ValueError, KeyError, TypeError) as exc:
                    evidence = 'invalidated: ' + str(exc)[:200]
        return {'run_id': run_id, 'state': info['state'], 'revision_id': info['revision_id'],
                'is_current_revision': current, 'is_current_native_artifact': verified_current,
                'scientifically_qualified': False, 'artifact_evidence': evidence,
                'progress': progress}

    def retry(self, owner, pid, run_id):
        """Retry a failed/cancelled run at most twice, against the same head."""
        info = self.store.run(owner, pid, run_id)
        if info['state'] not in ('failed', 'timed_out', 'cancelled', 'stale', 'partial_failed'):
            raise Conflict('Only terminal unsuccessful runs can be retried')
        snap = json.loads((Path(info['path']) / 'snapshot.json').read_text(encoding='utf8'))
        attempt = snap.get('attempt', 1)
        if type(attempt) is not int or attempt < 1 or attempt >= MAX_ATTEMPTS:
            raise Conflict('Native job retry budget exhausted')
        if snap.get('sweep_plan') is not None:
            raise Conflict('Sweep retry requires a new explicit, reviewed point selection')
        return self._submit(owner, pid, info['revision_id'], info['study_id'], force=True,
                            retry_of=run_id, attempt=attempt + 1)

    def archive(self, owner, pid, run_id):
        info = self.store.run(owner, pid, run_id)
        folder = Path(info['path']).resolve()
        allowed_root = (self.store.root / 'native-runs' / pid).resolve()
        if folder.parent != allowed_root or folder.name != run_id:
            raise Conflict('Run path does not match its authorized workspace')
        if info['state'] in ('queued', 'running', 'cancelling'):
            raise Conflict('Engine has not finished')
        if info['state'] == 'completed':
            self._check_completed_artifacts(info)
        files = []
        total = 0
        for p in folder.rglob('*'):
            if p.is_symlink():
                raise ValueError('Linked files are not permitted in native archives')
            if not p.is_file():
                continue
            if not p.resolve().is_relative_to(folder):
                raise ValueError('Native archive path traversal detected')
            total += p.stat().st_size
            if total > MAX_ARTIFACT_BYTES:
                raise ValueError('Artifacts exceed laptop archive limit')
            files.append(p)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(files):
                archive.write(p, p.relative_to(folder).as_posix())
                if buffer.tell() > MAX_ARTIFACT_BYTES:
                    raise ValueError('ZIP exceeds laptop archive limit')
        return buffer.getvalue()


def _stop(proc):
    if proc.poll() is not None:
        return
    try:
        if os.name != 'nt' and hasattr(proc, 'pid'):
            # Worker was started in a separate process group; kill descendants.
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=PROCESS_TERMINATE_GRACE)
    except subprocess.TimeoutExpired:
        if os.name != 'nt' and hasattr(proc, 'pid'):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait(timeout=PROCESS_TERMINATE_GRACE)
    except ProcessLookupError:
        pass


def _atomic_json(path, obj):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8')
    os.replace(tmp, path)


def _progress(folder, phase, completed, total):
    # No made-up solver percentage: these are scheduler checkpoints only.
    _atomic_json(folder / 'PROGRESS.json', {'phase': phase, 'completed_native_points': completed,
                                           'requested_native_points': total,
                                           'solver_progress_fraction': None,
                                           'recorded_at_utc': time.time()})
