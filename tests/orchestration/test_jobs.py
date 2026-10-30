"""Lifecycle tests use synthetic byte manifests, NOT real engine acceptance."""
import json
import subprocess
import threading
import time
from pathlib import Path
import pytest
from sqe_studio.contracts import digest
from sqe_studio.jobs import Jobs
from sqe_studio.orchestration.artifacts import sha_bytes, adapter_digest, fingerprint
from sqe_studio.store import Store, Conflict, NotFound
import sqe_studio.jobs as jobs_module


STUDY = {'id': 's1', 'engine': 'scqubits', 'kind': 'spectrum',
         'inputs': {'model': 'Transmon', 'parameters': {'EJ': 10.0, 'EC': 0.2,
         'ng': 0.0, 'ncut': 12}, 'levels': 3}}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    store = Store(tmp_path / 'private')
    project = store.create('owner', 'Laptop', 'transmon')
    model = project['model']
    model['studies'].append(STUDY)
    head = store.commit('owner', project['id'], project['head'], model)
    engine = Jobs(store)
    monkeypatch.setattr(jobs_module, 'engine_version', lambda name: 'TEST-FIXTURE-ONLY')
    return store, project['id'], head, engine


def wait_status(engine, pid, run_id, states=('completed', 'failed', 'timed_out', 'cancelled', 'stale', 'partial_failed')):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        result = engine.status('owner', pid, run_id)
        if result['state'] in states:
            return result
        time.sleep(0.01)
    pytest.fail(f'Job did not reach a terminal state: {result}')


class MockProcess:
    """Fixture-only subprocess supervisor double; writes no scientific dataset."""
    def __init__(self, argv, cwd, env, stdout, stderr, shell, *, mode='success', counter=None, entered=None, start_new_session=False, creationflags=0):
        assert argv[0] and argv[1:3] == ['-m', 'sqe_studio.worker']
        assert not shell and env['PYTHONPATH']
        self.mode = mode
        self.returncode = None
        self.terminated = False
        if entered:
            entered.set()
        if mode == 'hang':
            return
        snapshot = json.loads(Path(argv[3]).read_text())
        output = Path(argv[4])
        output.mkdir(parents=True, exist_ok=True)
        if mode == 'fail' or (mode == 'partial' and counter is not None and counter[0] > 0):
            (output/'FAILURE.json').write_text('{"status":"failed","error":"test failure"}')
            self.returncode = 1
            return
        if counter is not None:
            counter[0] += 1
        (output/'fixture.bin').write_bytes(b'fixture bytes without physics')
        version = 'TEST-FIXTURE-ONLY'
        adapter_sha = adapter_digest(snapshot['study']['engine'])
        key = fingerprint(revision_id=snapshot['revision_id'],
                          project_digest=snapshot['project_digest'], study=snapshot['study'],
                          native_version=version, adapter_sha256=adapter_sha)
        artifact = {'name': 'fixture.bin', 'sha256': sha_bytes(b'fixture bytes without physics'),
                    'bytes': len(b'fixture bytes without physics')}
        manifest = {'schema': 'sqe.artifact.v1', 'artifact_type': 'scqubits.spectrum',
                    'engine': 'scqubits', 'engine_version': version, 'kind': 'spectrum',
                    'study_id': snapshot['study']['id'], 'revision_id': snapshot['revision_id'],
                    'project_digest': snapshot['project_digest'], 'cache_fingerprint': key,
                    'scientific_status': 'review_required', 'fabrication_status': 'HOLD',
                    'artifacts': [artifact], 'parents': [],
                    'provenance': {'used_revision': snapshot['revision_id'],
                                   'used_project_sha256': snapshot['project_digest']}}
        (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            time.sleep(min(timeout or .01, .01))
            raise subprocess.TimeoutExpired(cmd='fixture-only', timeout=timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9


def fake_spawner(mode='success', counter=None, entered=None):
    return lambda *args, **kwargs: MockProcess(*args, **kwargs, mode=mode, counter=counter, entered=entered)


def test_completed_result_cache_archive_and_revision_invalidation(workspace, monkeypatch):
    store, pid, rev, engine = workspace
    launches = [0]
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', fake_spawner(counter=launches))
    first = engine.start('owner', pid, rev, 's1')
    assert wait_status(engine, pid, first)['state'] == 'completed'
    assert launches == [1]
    assert engine.start('owner', pid, rev, 's1') == first
    assert launches == [1]
    archive = engine.archive('owner', pid, first)
    import zipfile, io
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert 'snapshot.json' in z.namelist() and 'engine.log' in z.namelist()
        assert json.loads(z.read('output/RESULT_MANIFEST.json'))['fabrication_status'] == 'HOLD'
    (Path(store.run('owner', pid, first)['path'])/'output'/'fixture.bin').write_bytes(b'tampered')
    second = engine.start('owner', pid, rev, 's1')
    assert second != first
    assert wait_status(engine, pid, second)['state'] == 'completed'
    m = store.project('owner', pid)['model']
    head2 = store.commit('owner', pid, rev, m)
    with pytest.raises(Conflict, match='stale'):
        engine.start('owner', pid, rev, 's1')
    third = engine.start('owner', pid, head2, 's1')
    assert third != second
    assert wait_status(engine, pid, third)['state'] == 'completed'
    assert engine.status('owner', pid, first)['is_current_revision'] is False


def test_single_laptop_job_cancel_and_authenticated_scope(workspace, monkeypatch):
    _, pid, rev, engine = workspace
    entered = threading.Event()
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', fake_spawner(mode='hang', entered=entered))
    first = engine.start('owner', pid, rev, 's1')
    assert entered.wait(2)
    with pytest.raises(Conflict, match='One native'):
        engine.start('owner', pid, rev, 's1')
    with pytest.raises(NotFound):
        engine.cancel('other-user', pid, first)
    assert engine.cancel('owner', pid, first)['state'] == 'cancelling'
    assert wait_status(engine, pid, first)['state'] == 'cancelled'
    with pytest.raises(Conflict, match='cannot be cancelled'):
        engine.cancel('owner', pid, first)
    assert len(engine.archive('owner', pid, first)) > 0


def test_bounded_timeout_and_retry_budget(workspace, monkeypatch):
    _, pid, rev, engine = workspace
    monkeypatch.setattr(jobs_module, 'MAX_SECONDS', .04)
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', fake_spawner(mode='hang'))
    first = engine.start('owner', pid, rev, 's1')
    assert wait_status(engine, pid, first)['state'] == 'timed_out'
    second = engine.retry('owner', pid, first)
    assert wait_status(engine, pid, second)['state'] == 'timed_out'
    third = engine.retry('owner', pid, second)
    assert wait_status(engine, pid, third)['state'] == 'timed_out'
    with pytest.raises(Conflict, match='budget'):
        engine.retry('owner', pid, third)


def test_sweep_partial_failure_and_ordered_point_provenance(workspace, monkeypatch):
    store, pid, rev, engine = workspace
    counter = [0]
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', fake_spawner(mode='partial', counter=counter))
    run_id = engine.start_sweep('owner', pid, rev, 's1',
                                {'parameters.EJ': [9.0, 10.0, 11.0]}, mode='automatic')
    assert wait_status(engine, pid, run_id)['state'] == 'partial_failed'
    folder = Path(store.run('owner', pid, run_id)['path'])
    summary = json.loads((folder/'SWEEP_MANIFEST.json').read_text())
    assert summary['requested_points'] == 3
    assert len(summary['verified_points']) == 1
    assert summary['next_unexecuted_index'] == 1
    assert (folder/'output'/'point_0000'/'RESULT_MANIFEST.json').exists()
    assert not (folder/'output'/'point_0002').exists()
    assert (folder/'point_0000.engine.log').is_file()
    assert summary['scientific_status'] == 'review_required'
    with pytest.raises(Conflict, match='Sweep retry'):
        engine.retry('owner', pid, run_id)


def test_new_head_before_worker_dispatch_never_launches(workspace, monkeypatch):
    _, pid, rev, engine = workspace
    launched = []
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', lambda *a, **k: launched.append(True))
    monkeypatch.setattr(engine, '_head_current', lambda *a: False)
    run_id = engine.start('owner', pid, rev, 's1')
    assert wait_status(engine, pid, run_id)['state'] == 'stale'
    assert not launched
    assert engine.status('owner', pid, run_id)['progress']['solver_progress_fraction'] is None


def test_fail_closed_native_adapter_without_fixture(workspace):
    """Real process probes the installed environment; a blocked engine is failure."""
    store, pid, rev, engine = workspace
    study = {'id': 'blocked', 'engine': 'josephson_circuits', 'kind': 'native', 'inputs': {}}
    m = store.project('owner', pid)['model']
    m['studies'].append(study)
    head2 = store.commit('owner', pid, rev, m)
    run_id = engine.start('owner', pid, head2, 'blocked')
    assert wait_status(engine, pid, run_id)['state'] == 'failed'
    output = Path(store.run('owner', pid, run_id)['path'])/'output'
    assert (output/'FAILURE.json').exists()
    assert not (output/'RESULT_MANIFEST.json').exists()


@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX flock exercise; Windows uses msvcrt')
def test_second_process_cannot_dispatch_same_workspace(workspace):
    """Actual independent process holds the OS lock (no science executed)."""
    import os
    import sys
    _, pid, rev, engine = workspace
    lockfile = engine.store.root/'.native-job.lock'
    script = ('import fcntl,sys,time; '
              'f=open(sys.argv[1],"a+b"); '
              'fcntl.flock(f,fcntl.LOCK_EX); '
              'print("LOCKED",flush=True); '
              'time.sleep(5)')
    proc = subprocess.Popen([sys.executable, '-c', script, str(lockfile)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'LOCKED'
        with pytest.raises(Conflict, match='Another SQE process'):
            engine.start('owner', pid, rev, 's1')
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_archive_refuses_post_completion_tampering(workspace, monkeypatch):
    store, pid, rev, engine = workspace
    monkeypatch.setattr(jobs_module.subprocess, 'Popen', fake_spawner())
    run_id = engine.start('owner', pid, rev, 's1')
    assert wait_status(engine, pid, run_id)['state'] == 'completed'
    assert engine.status('owner', pid, run_id)['is_current_native_artifact'] is True
    folder = Path(store.run('owner', pid, run_id)['path'])
    (folder/'output'/'fixture.bin').write_bytes(b'forged-after-completion')
    assert engine.status('owner', pid, run_id)['is_current_native_artifact'] is False
    with pytest.raises(ValueError, match='changed'):
        engine.archive('owner', pid, run_id)
