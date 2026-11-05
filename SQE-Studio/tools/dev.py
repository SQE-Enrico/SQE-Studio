#!/usr/bin/env python3
"""Local development checks and save-triggered reruns, using Automatic Test."""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))

from sqe_studio.cycle_qualification import next_report_path
from sqe_studio.qualification import _run
from sqe_studio.testing.catalog import PROFILES
from sqe_studio.testing.runner import result_exit_code, run_selected
from verify_release_source import _ignored_dir

PROFILES = {**PROFILES, 'software': ('regression', 'http', 'browser', 'packaging')}
UI_CHECKS = ('m17_ui_qa.cjs', 'm18_ui_qa.cjs', 'm19_ui_qa.cjs')


def snapshot(root=None):
    """Watch source metadata, pruning the same output trees as source integrity."""
    root = ROOT if root is None else Path(root)
    state = {}

    def unreadable(error):
        raise error

    for base, directories, files in os.walk(root, onerror=unreadable, followlinks=False):
        folder = Path(base)
        directories[:] = [name for name in directories
                          if not _ignored_dir(name, at_root=folder == root)]
        for name in files:
            if name.endswith(('.pyc', '.pyo')):
                continue
            path = folder / name
            info = path.lstat()
            state[path.relative_to(root).as_posix()] = (info.st_mtime_ns, info.st_size)
    # These files live beside the package in the enclosing Git repository.
    if root.name == 'SQE-Studio' and (root.parent / 'dev.ps1').is_file():
        for path in (root.parent / 'dev.ps1', root.parent / 'AGENTS.md',
                     root.parent / '.gitattributes', root.parent / '.github/workflows/ci.yml'):
            if path.is_file():
                info = path.stat()
                state['../' + path.relative_to(root.parent).as_posix()] = (info.st_mtime_ns, info.st_size)
    return state


def snapshot_digest(state):
    return sha256(json.dumps(state, sort_keys=True).encode('utf-8')).hexdigest()


def wait_for_change(previous, *, root=None, interval=1.0, settle=1.0, stop=None):
    """Coalesce editor save bursts; changes during a test are never discarded."""
    candidate, since = previous, time.monotonic()
    while True:
        time.sleep(interval)
        if stop is not None and stop.is_set():
            return False
        current = snapshot(root)
        if current != candidate:
            candidate, since = current, time.monotonic()
        if candidate != previous and time.monotonic() - since >= settle:
            return True


def find_node():
    node = shutil.which('node')
    if node:
        return node
    configured = os.environ.get('PLAYWRIGHT_NODEJS_PATH')
    if configured and shutil.which(configured):
        return shutil.which(configured)
    # Playwright already ships Node. Reuse it for VM checks on a workstation
    # whose normal PowerShell PATH has no separate Node installation.
    spec = importlib.util.find_spec('playwright')
    if spec and spec.origin:
        candidate = Path(spec.origin).parent / 'driver' / ('node.exe' if os.name == 'nt' else 'node')
        if candidate.is_file():
            return str(candidate)
    return None


def doctor():
    packages = ('pytest', 'build', 'setuptools', 'wheel', 'playwright', 'scqubits',
                'qiskit_metal', 'gmsh', 'vtk')
    return {'python': sys.executable, 'python_version': sys.version.split()[0],
            'node': find_node(),
            'packages': {name: importlib.util.find_spec(name) is not None for name in packages},
            'profiles': list(PROFILES), 'native_solver_health': 'NOT_PROBED'}


def run_cycle(profile, *, check=False, cancel=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1',
               PYTHONUNBUFFERED='1', PYTHONUTF8='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    steps = []

    def command(name, args, timeout):
        print('LOCAL_START ' + name, flush=True)
        code, log, seconds = _run(args, ROOT, env, timeout)
        print(log, end='' if log.endswith('\n') else '\n', flush=True)
        steps.append({'id': name, 'status': 'TIMEOUT' if code is None else
                      'PASS' if code == 0 else 'FAIL', 'exit_code': code, 'duration_s': seconds})
        return code == 0

    if not check:
        print('Refreshing software fingerprints; numerical/core pins remain enforced.', flush=True)
        if not command('refresh', [sys.executable, str(ROOT / 'tools/update_release.py')], 45):
            baseline = snapshot()
            publish_summary({'schema': 'sqe.local-development-check.v1', 'profile': profile,
                             'exit_code': 1, 'steps': steps, 'automatic_test_report': None,
                             'source_snapshot_sha256': snapshot_digest(baseline),
                             'reason': 'SOFTWARE_FINGERPRINT_REFRESH_FAILED'})
            return 1, baseline
    baseline = snapshot()
    # Keep Node checks distinct: these execute real UI controllers in a VM.
    node = find_node()
    if node is None:
        steps.append({'id': 'ui_vm', 'status': 'BLOCKED', 'reason': 'NODE_NOT_INSTALLED'})
        print('BLOCKED: Node is required for UI controller checks.', flush=True)
    else:
        for script in UI_CHECKS:
            if cancel is not None and cancel.is_set():
                break
            command(script, [node, str(ROOT / 'scripts' / script)], 60)
    destination = next_report_path(ROOT)
    result = run_selected(ROOT, destination, PROFILES[profile], cancel=cancel,
                          notify=lambda line: print(line, flush=True))
    code = result_exit_code(result)
    if any(step['status'] == 'FAIL' for step in steps):
        code = 1
    elif code == 0 and any(step['status'] != 'PASS' for step in steps):
        code = 2
    stable = snapshot() == baseline
    if not stable:
        print('SOURCE_CHANGED_DURING_TEST: rerun required for the current files.', flush=True)
        code = code or 2
    summary = {'schema': 'sqe.local-development-check.v1', 'profile': profile,
               'exit_code': code, 'source_stable': stable, 'steps': steps,
               'source_snapshot_sha256': snapshot_digest(baseline),
               'automatic_test_report': destination.name,
               'counts': result['execution_counts'], 'scientific_qualification': 'NOT_ESTABLISHED'}
    publish_summary(summary)
    print('LOCAL_RESULT ' + str(code) + ' REPORT ' + str(destination), flush=True)
    return code, baseline


def publish_summary(summary):
    target = ROOT / 'qualification-reports/local-latest.json'
    target.parent.mkdir(exist_ok=True)
    partial = target.with_suffix('.partial')
    partial.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    os.replace(partial, target)


def watch(profile, check, stop):
    while not stop.is_set():
        # A fresh interpreter loads edits to the runner/catalog/UI on every cycle.
        # Reusing imported Python modules would test an obsolete controller.
        command = [sys.executable, '-u', str(Path(__file__).resolve()), '--profile', profile]
        if check:
            command.append('--check')
        latest = ROOT / 'qualification-reports/local-latest.json'
        try:
            previous_summary = latest.read_bytes()
        except OSError:
            previous_summary = None
        subprocess.call(command, cwd=ROOT)
        if stop.is_set():
            break
        current = snapshot()
        try:
            raw = latest.read_bytes()
            summary = json.loads(raw) if raw != previous_summary else {}
        except (OSError, ValueError):
            summary = {}
        if (summary.get('source_snapshot_sha256') and
                summary['source_snapshot_sha256'] != snapshot_digest(current)):
            print('WATCH: source changed during the cycle; rerunning with current code.', flush=True)
            time.sleep(1)
            continue
        print('WATCHING: saves trigger one new run; Ctrl+C requests stop.', flush=True)
        wait_for_change(current, stop=stop)
    return 130


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=tuple(PROFILES), default='recommended')
    parser.add_argument('--watch', action='store_true', help='Rerun after saves; Ctrl+C stops')
    parser.add_argument('--check', action='store_true', help='Verify existing fingerprints without refreshing (CI)')
    parser.add_argument('--doctor', action='store_true', help='Show interpreter and optional tools without running tests')
    args = parser.parse_args(argv)
    if args.watch and args.profile not in ('recommended', 'quick'):
        parser.error('--watch supports recommended/quick; run expensive profiles explicitly')
    if args.doctor:
        print(json.dumps(doctor(), indent=2))
        return 0
    os.environ.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    stop = threading.Event()
    def request_stop(_signal, _frame):
        stop.set()
        print('\nStop requested: finishing the bounded task and preserving its report.', flush=True)
    previous_signal = signal.signal(signal.SIGINT, request_stop)
    try:
        if args.watch:
            return watch(args.profile, args.check, stop)
        code, _ = run_cycle(args.profile, check=args.check, cancel=stop)
        return 130 if stop.is_set() else code
    except KeyboardInterrupt:
        print('\nStopped local tests.', flush=True)
        return 130
    except (OSError, ValueError) as error:
        print('LOCAL_ERROR ' + str(error), file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGINT, previous_signal)


if __name__ == '__main__':
    raise SystemExit(main())
