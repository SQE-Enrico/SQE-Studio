"""Local-only, allowlisted optional-engine provisioning for the Web workspace.

Installation is best-effort and never blocks the HTTP server. Third-party
software is not downloaded on remote deployments. No shell or user-provided
package names are evaluated. SQDMetal is kept in a separate Python 3.11 venv.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile

from .auth import Problem
from .support_bundles import create_support_bundle

ENGINE_IDS = ('scqubits', 'gmsh', 'quantum-metal', 'sqdmetal', 'josephsoncircuits', 'palace')
AUTOMATIC = ('scqubits', 'gmsh', 'quantum-metal', 'sqdmetal', 'josephsoncircuits')
# No user-controlled install commands. Network packages come from a configured
# Python package index / the SQDMetal upstream repository. See the report.
PIP = {
    'scqubits': ['scqubits>=4.3.2,<5'],
    'gmsh': ['gmsh>=4.14,<5'],
    'quantum-metal': ['quantum-metal>=0.9,<1'],
    'sqdmetal': ['SQDMetal @ git+https://github.com/sqdlab/SQDMetal.git'],
}
CHECKS = {
    'scqubits': 'import scqubits as s; import numpy as np; v=s.Transmon(EJ=15, EC=0.25, ng=0, ncut=15, truncated_dim=5).eigenvals(evals_count=2); assert np.isfinite(v).all() and v[1]>v[0]; print("Transmon spectrum smoke test OK")',
    'gmsh': 'import gmsh; gmsh.initialize(); gmsh.model.add("sqe_smoke"); gmsh.model.geo.addPoint(0,0,0); gmsh.model.geo.synchronize(); gmsh.finalize(); print("Gmsh native geometry smoke test OK")',
    'quantum-metal': 'import qiskit_metal; from qiskit_metal.designs import DesignPlanar; print("Quantum Metal design API smoke test OK")',
    'sqdmetal': 'import SQDMetal; from SQDMetal.PALACE.Capacitance_Simulation import PALACE_Capacitance_Simulation; print("SQDMetal Palace API import OK")',
}
TIMEOUT = 900


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def _save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


class DependencyManager:
    def __init__(self, root: Path, source_root: Path):
        self.root = root / 'engine-setup'
        self.source_root = Path(source_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.venv_dir = self.root / 'python311'
        self.julia_project = self.root / 'julia'
        self.runs = self.root / 'runs'
        self.runs.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.worker = None
        self.active = None
        self._cache = None
        self._cache_at = 0.0
        for status in self.runs.glob('*/status.json'):
            try:
                row = json.loads(status.read_text(encoding='utf-8'))
                if row.get('state') in ('queued', 'running'):
                    row.update(state='interrupted', error='Server restarted during dependency setup.', completed_utc=timestamp())
                    _save(status, row)
            except (OSError, ValueError):
                continue

    def python311(self):
        env = os.environ.get('SQE_PYTHON311', '').strip()
        candidates = [[env]] if env else []
        if sys.version_info[:2] == (3, 11):
            candidates.append([sys.executable])
        if os.name == 'nt':
            candidates.extend([['py', '-3.11'], ['python3.11']])
        else:
            candidates.append(['python3.11'])
        for command in candidates:
            try:
                result = subprocess.run(command + ['-c', 'import sys; print(sys.executable if sys.version_info[:2] == (3,11) else "")'],
                                        text=True, capture_output=True, timeout=6, check=False)
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().splitlines()[-1]
            except (OSError, subprocess.TimeoutExpired):
                continue
        return None

    def metal_python(self):
        path = self.venv_dir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        return str(path) if path.is_file() else None

    @staticmethod
    def _probe(command, seconds=12, env=None):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=seconds,
                                    stdin=subprocess.DEVNULL, check=False, env=env)
            return {'ready': result.returncode == 0,
                    'detail': (result.stdout or result.stderr).strip()[-280:]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'ready': False, 'detail': str(exc)[:280]}

    def invalidate(self):
        self._cache = None
        self._cache_at = 0.0

    def readiness(self):
        if self._cache is not None and time.monotonic() - self._cache_at < 50:
            return self._cache
        metal_python = self.metal_python()
        julia = shutil.which('julia')
        results = {}
        for key in ENGINE_IDS:
            if key in ('scqubits', 'gmsh'):
                result = self._probe([sys.executable, '-c', CHECKS[key]])
                result['environment'] = 'Studio Python'
            elif key in ('quantum-metal', 'sqdmetal'):
                result = (self._probe([metal_python, '-c', CHECKS[key]], seconds=25)
                          if metal_python else {'ready': False, 'detail': 'Managed Python 3.11 environment is not installed.'})
                result['environment'] = 'Isolated Python 3.11'
                if not metal_python and not self.python311():
                    result['detail'] = 'Python 3.11 is required. Install it once, then choose Retry setup.'
            elif key == 'josephsoncircuits':
                env = {**os.environ, 'JULIA_PKG_PRECOMPILE_AUTO': '0'}
                result = (self._probe([julia, '--startup-file=no', '--project='+str(self.julia_project),
                        '-e', 'using JosephsonCircuits; println("JosephsonCircuits import OK")'], seconds=35, env=env)
                          if julia and (self.julia_project/'Project.toml').is_file()
                          else {'ready': False, 'detail': 'Julia or managed JosephsonCircuits project is not installed.'})
                result['environment'] = 'Isolated Julia project'
            else:
                result = self._probe(['palace', '--help'], seconds=6) if shutil.which('palace') else {
                    'ready': False, 'detail': 'Palace requires a qualified native Linux/WSL installation.'}
                result['environment'] = 'Native solver / WSL'
            result['automatic'] = key in AUTOMATIC
            result['label'] = {'quantum-metal': 'Quantum Metal', 'sqdmetal': 'SQDMetal',
                               'josephsoncircuits': 'JosephsonCircuits.jl', 'gmsh': 'Gmsh',
                               'palace': 'Palace', 'scqubits': 'scqubits'}[key]
            results[key] = result
        self._cache = results
        self._cache_at = time.monotonic()
        return results

    def list(self):
        rows = []
        for file in self.runs.glob('*/status.json'):
            try:
                rows.append(json.loads(file.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return sorted(rows, key=lambda x: x['created_utc'], reverse=True)[:30]

    def status(self):
        runs = self.list()
        return {'engines': self.readiness(), 'runs': runs,
                'active': self.active, 'automatic': list(AUTOMATIC),
                'disclosure': 'Installation uses third-party distributions and may require internet access. No project data is uploaded. Verify resulting numerical models separately.',
                'python311_present': bool(self.python311()),
                'runtime': {'current_python': f'{sys.version_info.major}.{sys.version_info.minor}',
                            'isolated_python311': bool(self.metal_python())}}

    def _folder(self, run_id):
        if not isinstance(run_id, str) or len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
            raise Problem('Invalid setup report identifier', 404)
        folder = self.runs / run_id
        if not folder.is_dir() or folder.is_symlink():
            raise Problem('Setup report not found', 404)
        return folder

    def detail(self, run_id):
        folder = self._folder(run_id)
        result = json.loads((folder/'status.json').read_text(encoding='utf-8'))
        log = folder/'install.log'
        result['log_tail'] = log.read_bytes()[-16000:].decode('utf-8', 'replace') if log.exists() else ''
        result['bundle_ready'] = result['state'] not in ('queued', 'running')
        return result

    def start(self, engines=None, *, auto=False):
        selection = list(AUTOMATIC) if engines is None else engines
        if (not isinstance(selection, list) or not selection or len(selection) > len(AUTOMATIC)
                or any(not isinstance(e, str) or e not in AUTOMATIC for e in selection)
                or len(set(selection)) != len(selection)):
            raise Problem('Choose one or more supported optional engines')
        with self.lock:
            if self.active:
                raise Problem('Another dependency setup is already running', 409)
            run_id = uuid.uuid4().hex
            folder = self.runs / run_id
            folder.mkdir(mode=0o700)
            state = {'id': run_id, 'state': 'queued', 'engines': selection, 'automatic': bool(auto),
                     'created_utc': timestamp(), 'completed_utc': None, 'checks': {}, 'error': None}
            _save(folder/'status.json', state)
            self.active = run_id
            self.worker = threading.Thread(target=self._run, args=(run_id,), daemon=True,
                                           name='sqe-engine-setup')
            self.worker.start()
            return state

    def auto_once(self):
        if (self.root/'automatic-setup-started.json').exists():
            return False
        # Marker prevents accidental repeated gigabyte installs on every start.
        _save(self.root/'automatic-setup-started.json', {'created_utc': timestamp(), 'engines': list(AUTOMATIC)})
        try:
            self.start(auto=True)
        except Problem:
            return False
        return True

    def _execute(self, command, log, *, timeout=TIMEOUT, env=None):
        log.write('$ ' + ' '.join(command) + '\n')
        log.flush()
        try:
            result = subprocess.run(command, cwd=self.source_root, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, timeout=timeout, env=env, check=False)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.write(f'Command failed: {type(exc).__name__}: {exc}\n')
            log.flush()
            return False

    def _install_one(self, key, log):
        if key in ('scqubits', 'gmsh'):
            executable = sys.executable
        elif key in ('quantum-metal', 'sqdmetal'):
            executable = self.metal_python()
            if not executable:
                python = self.python311()
                if not python:
                    return False, 'Python 3.11 is not present. Install Python 3.11 and retry from the browser.'
                if not self._execute([python, '-m', 'venv', str(self.venv_dir)], log, timeout=180):
                    return False, 'Failed to create the isolated Python 3.11 environment.'
                executable = self.metal_python()
                if not executable:
                    return False, 'Managed Python executable was not created.'
            # Install SQE core in the sidecar so the workflow worker uses the same API.
            if not self._execute([executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                                  '--no-input', '-e', str(self.source_root)], log):
                return False, 'Failed to install SQE core in isolated Python 3.11.'
        elif key == 'josephsoncircuits':
            julia = shutil.which('julia')
            if not julia:
                return False, 'Julia is not installed or available to the Studio service.'
            self.julia_project.mkdir(exist_ok=True)
            env = {**os.environ, 'JULIA_PKG_PRECOMPILE_AUTO': '0'}
            script = 'using Pkg; Pkg.activate(ARGS[1]); Pkg.add("JosephsonCircuits"); using JosephsonCircuits; println("Package import OK")'
            ok = self._execute([julia, '--startup-file=no', '-e', script, str(self.julia_project)],
                               log, env=env)
            return ok, 'Julia package installation and import completed.' if ok else 'Julia package install/import failed.'
        else:
            return False, 'Automatic installation is not supported.'
        ok = self._execute([executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                            '--no-input', *PIP[key]], log)
        if not ok:
            return False, 'pip installation failed; inspect install.log in the support ZIP.'
        if key in ('quantum-metal', 'sqdmetal'):
            # A mixed Metal/scqubits workflow runs under this same sidecar.
            # Keeping scqubits here prevents accidental cross-interpreter imports.
            if not self._execute([executable, '-m', 'pip', 'install',
                                  '--disable-pip-version-check', '--no-input',
                                  'scqubits>=4.3.2,<5'], log):
                return False, 'The Python 3.11 sidecar could not install scqubits for mixed workflows.'
        probe = self._probe([executable, '-c', CHECKS[key]], seconds=90)
        log.write('Post-install import: ' + json.dumps(probe) + '\n')
        return probe['ready'], probe['detail'] if probe['ready'] else 'Post-install import test failed: ' + probe['detail']

    def _run(self, run_id):
        folder = self._folder(run_id)
        path = folder/'status.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['state'] = 'running'
        _save(path, state)
        try:
            with (folder/'install.log').open('w', encoding='utf-8') as log:
                for key in state['engines']:
                    log.write(f'\n=== {key} ===\n')
                    log.flush()
                    try:
                        prior = self.readiness().get(key, {}) if state['automatic'] else {}
                        if prior.get('ready'):
                            success, detail = True, 'Existing installation passed its smoke test; no reinstall needed.'
                        else:
                            success, detail = self._install_one(key, log)
                    except Exception as exc:
                        success, detail = False, f'{type(exc).__name__}: {str(exc)[:300]}'
                    state['checks'][key] = {'status': 'PASS' if success else 'WARN', 'detail': detail}
                    _save(path, state)
                    self._cache = None
            state['state'] = ('completed' if all(v['status'] == 'PASS' for v in state['checks'].values())
                              else 'partial')
        except Exception as exc:
            state.update(state='failed', error=f'{type(exc).__name__}: {str(exc)[:250]}')
        finally:
            state['completed_utc'] = timestamp()
            _save(path, state)
            with self.lock:
                if self.active == run_id:
                    self.active = None

    def archive(self, run_id):
        row = self.detail(run_id)
        if not row['bundle_ready']:
            raise Problem('Setup is still running', 409)
        folder = self._folder(run_id)
        return create_support_bundle(folder/'SQE-engine-setup-support.zip', folder,
                                     category='engine-setup', job=row)
