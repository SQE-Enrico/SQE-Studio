"""Web-only orchestration of test projects across the optional EDA engines.

The web application launches a fixed internal worker, never shell commands or
untrusted uploaded Python. Imported projects use a constrained ZIP contract.
Runs are on the administrator's local workstation, never remote deployments.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import threading
import uuid
import zipfile

from .auth import Problem
from .support_bundles import create_support_bundle
from ..ecosystem import doctor, plan, validate

RUN_ID = re.compile(r'^[0-9a-f]{32}$')
EXAMPLE_DIRS = ('native-1q', 'quantum-models', 'metal-palace')
EXTENSIONS = {'.json', '.yaml', '.yml', '.csv'}
MAX_IMPORT = 24 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_ENTRIES = 48
MAX_RUNS = 30
RUN_TIMEOUT = 600


def utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data: dict):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, default=str) + '\n', encoding='utf-8')
    os.replace(temp, path)


class EcosystemControl:
    def __init__(self, storage: Path, source_root: Path, dependencies=None):
        self.dependencies = dependencies
        self.storage = storage / 'ecosystem-workspace'
        self.source_root = source_root
        self.examples = source_root / 'examples' / 'ecosystem'
        self.projects = self.storage / 'projects'
        self.runs = self.storage / 'runs'
        self.projects.mkdir(parents=True, exist_ok=True)
        self.runs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.active = None
        self.worker = None
        self.process = None
        self.cancelled = set()
        for entry in self.runs.glob('*/status.json'):
            try:
                data = json.loads(entry.read_text(encoding='utf-8'))
                if data.get('state') in ('queued', 'running'):
                    data.update(state='interrupted', error='Web service restarted while the run was active.',
                                completed_utc=utc())
                    atomic_json(entry, data)
            except (OSError, ValueError):
                continue

    def _directory(self, run_id):
        if not RUN_ID.fullmatch(str(run_id)):
            raise Problem('Invalid experiment identifier', 404)
        folder = self.runs / run_id
        if not folder.is_dir() or folder.is_symlink():
            raise Problem('Experiment not found', 404)
        return folder

    def detail(self, run_id):
        folder = self._directory(run_id)
        state = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        result_file = folder / 'output' / 'run.json'
        if result_file.is_file():
            try:
                state['result'] = json.loads(result_file.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                state['result'] = None
        path = folder / 'worker.log'
        state['log_tail'] = (path.read_bytes()[-65536:].decode('utf-8', 'replace') if path.is_file() else '')
        state['bundle_ready'] = state['state'] not in ('queued', 'running')
        return state

    def list(self):
        records = []
        for file in self.runs.glob('*/status.json'):
            if not RUN_ID.fullmatch(file.parent.name) or file.parent.is_symlink():
                continue
            try:
                records.append(json.loads(file.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda r: r.get('created_utc', ''), reverse=True)[:MAX_RUNS]

    def catalog(self):
        examples = []
        for name in EXAMPLE_DIRS:
            path = self.examples / name / 'workflow.json'
            spec = json.loads(path.read_text(encoding='utf-8'))
            examples.append({'id': name, 'name': spec['name'],
                             'steps': [{'id': s['id'], 'engine': s['engine'], 'operation': s['operation']}
                                       for s in validate(spec)], 'type': 'example'})
        for path in sorted(self.projects.glob('*/workflow.json')):
            if path.parent.is_symlink() or not RUN_ID.fullmatch(path.parent.name):
                continue
            try:
                spec = json.loads(path.read_text(encoding='utf-8'))
                examples.append({'id': path.parent.name, 'name': spec['name'],
                                 'steps': [{'id': s['id'], 'engine': s['engine'], 'operation': s['operation']}
                                           for s in validate(spec)], 'type': 'imported'})
            except (ValueError, OSError, KeyError):
                continue
        engines = doctor()
        if self.dependencies:
            ready = self.dependencies.readiness()
            for key, row in ready.items():
                name = {'quantum-metal': 'quantum-metal', 'sqdmetal': 'sqdmetal',
                        'scqubits': 'scqubits', 'josephsoncircuits': 'josephsoncircuits',
                        'palace': 'palace', 'gmsh': 'gmsh'}[key]
                engines[name].update(available=row['ready'], setup_detail=row['detail'])
        return {'projects': examples, 'engines': engines, 'runs': self.list(),
                'policy': {'admin_only': True, 'local_only': True, 'external_solvers_opt_in': True,
                           'uploaded_python_code': False}}

    def _project(self, name):
        if name in EXAMPLE_DIRS:
            folder = self.examples / name
        elif RUN_ID.fullmatch(str(name)):
            folder = self.projects / name
        else:
            raise Problem('Unknown experiment project', 404)
        if not folder.is_dir() or folder.is_symlink():
            raise Problem('Experiment project is missing', 404)
        return folder

    def preview(self, name):
        folder = self._project(name)
        spec = json.loads((folder / 'workflow.json').read_text(encoding='utf-8'))
        info = plan(spec, folder)
        if self.dependencies:
            engines = self.dependencies.readiness()
            for step in info['steps']:
                engine = step['adapter'].split('.')[0]
                if engine in engines:
                    step['available'] = engines[engine]['ready'] or (engine == 'josephsoncircuits' and step['adapter'].endswith('.export'))
        return {'id': name, 'spec': spec, 'plan': info,
                'trusted_python_factory': name == 'metal-palace'}

    def import_project(self, raw: bytes):
        if not isinstance(raw, bytes) or len(raw) > MAX_IMPORT:
            raise Problem('Project archive exceeds the 24 MiB limit', 413)
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except (zipfile.BadZipFile, ValueError):
            raise Problem('Upload a valid ZIP containing workflow.json')
        with archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= MAX_ENTRIES:
                raise Problem('ZIP must contain 1 to 48 entries')
            files = {}
            total = 0
            for info in infos:
                name = info.filename
                if info.is_dir():
                    continue
                # Disallow traversal, Windows paths, hidden files, encrypted entries,
                # nested ZIPs, symlinks, executable Python, and high compression bombs.
                parts = PurePosixPath(name).parts
                if (not parts or len(parts) > 4 or name.startswith('/') or '\\' in name
                        or ':' in name or '..' in parts or any(p.startswith('.') for p in parts)
                        or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts)
                        or (info.external_attr >> 16) & 0o170000 == 0o120000
                        or info.flag_bits & 1 or PurePosixPath(name).suffix.lower() not in EXTENSIONS):
                    raise Problem('ZIP contains a forbidden file path or type')
                if info.file_size > MAX_FILE or info.compress_size > MAX_IMPORT:
                    raise Problem('Project input file exceeds the 8 MiB limit', 413)
                total += info.file_size
                if total > MAX_IMPORT:
                    raise Problem('Project uncompressed size exceeds the 24 MiB limit', 413)
                if name in files:
                    raise Problem('Duplicate ZIP file name')
                content = archive.read(info)
                if len(content) != info.file_size:
                    raise Problem('Invalid file size in ZIP')
                files[name] = content
        if 'workflow.json' not in files:
            raise Problem('ZIP must include workflow.json at archive root')
        try:
            spec = json.loads(files['workflow.json'])
            validate(spec)
        except (ValueError, UnicodeError, TypeError) as exc:
            raise Problem('Invalid workflow.json: ' + str(exc))
        for step in spec['steps']:
            source = step['source']
            if isinstance(source, str) and source not in files:
                raise Problem('Project ZIP missing source: ' + source)
        project_id = uuid.uuid4().hex
        folder = self.projects / project_id
        folder.mkdir(mode=0o700)
        try:
            for name, content in files.items():
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return {'id': project_id, 'name': spec['name'], 'files': len(files),
                'note': 'No Python factories or shell commands can be uploaded.'}

    def start(self, name, *, allow_project_code=False, allow_solvers=False):
        if type(allow_project_code) is not bool or type(allow_solvers) is not bool:
            raise Problem('Execution permissions must be booleans')
        root = self._project(name)
        if allow_project_code and name != 'metal-palace':
            raise Problem('Trusted Python execution is restricted to the bundled example', 403)
        spec = json.loads((root / 'workflow.json').read_text(encoding='utf-8'))
        validate(spec)
        if self.dependencies and any(s['engine'] in ('quantum-metal', 'sqdmetal') for s in spec['steps']):
            checks = self.dependencies.readiness()
            missing = [s['engine'] for s in spec['steps'] if s['engine'] in ('quantum-metal','sqdmetal')
                       and not checks[s['engine']]['ready']]
            if missing:
                raise Problem('Install and verify required engines in Setup first: ' + ', '.join(sorted(set(missing))), 409)
        with self.lock:
            if self.active is not None:
                raise Problem('An experiment is already running', 409)
            if len(self.list()) >= MAX_RUNS:
                raise Problem('Experiment history is full. Export and delete an older run.', 409)
            run_id = uuid.uuid4().hex
            folder = self.runs / run_id
            folder.mkdir(mode=0o700)
            state = {'id': run_id, 'project_id': name, 'project': spec['name'],
                     'state': 'queued', 'created_utc': utc(), 'completed_utc': None,
                     'allow_project_code': allow_project_code, 'allow_solvers': allow_solvers,
                     'error': None, 'summary': None}
            atomic_json(folder / 'status.json', state)
            atomic_json(folder / 'policy.json', {'allow_project_code': allow_project_code,
                                                 'allow_solvers': allow_solvers})
            self.active = run_id
            self.worker = threading.Thread(target=self._run, args=(run_id, root),
                                           daemon=True, name='sqe-ecosystem-run')
            self.worker.start()
            return state

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process.poll() is None:
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _run(self, run_id, root):
        folder = self._directory(run_id)
        status_path = folder / 'status.json'
        state = json.loads(status_path.read_text(encoding='utf-8'))
        try:
            state['state'] = 'running'
            atomic_json(status_path, state)
            # Exactly one immutable copy of the sources per run. Existing example
            # sources are copied rather than executed from a mutable package tree.
            source = folder / 'project'
            shutil.copytree(root, source)
            output = folder / 'output'
            spec = json.loads((source / 'workflow.json').read_text(encoding='utf-8'))
            sidecar = self.dependencies.metal_python() if self.dependencies and any(
                step['engine'] in ('quantum-metal', 'sqdmetal') for step in spec['steps']) else None
            executable = sidecar or sys.executable
            args = [executable, '-m', 'sqw.studio.ecosystem_runner', str(source),
                    str(output), str(folder / 'policy.json')]
            kwargs = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                      else {'start_new_session': True})
            with (folder / 'worker.log').open('wb') as log:
                child_env = os.environ.copy()
                if self.dependencies and (self.dependencies.julia_project/'Project.toml').exists():
                    child_env['SQE_JULIA_ENV'] = str(self.dependencies.julia_project)
                process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                           env=child_env, **kwargs)
                with self.lock:
                    self.process = process
                try:
                    returncode = process.wait(timeout=RUN_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self._stop(process)
                    state.update(state='timed_out', error=f'Experiment exceeded {RUN_TIMEOUT} seconds')
                else:
                    was_cancelled = run_id in self.cancelled
                    state.update(state='cancelled' if was_cancelled else 'completed' if returncode == 0 else 'failed',
                                 error='Cancelled by the administrator' if was_cancelled else None if returncode == 0 else 'Worker failed; see worker.log and partial results')
            state['summary'] = ('INTEGRITY_VERIFIED_ONLY' if state['state'] == 'completed'
                                else state['state'].upper())
        except Exception as exc:
            state.update(state='failed', summary='FAILED', error=f'{type(exc).__name__}: {exc}'[:350])
        finally:
            state['completed_utc'] = utc()
            atomic_json(status_path, state)
            with self.lock:
                self.process = None
                self.cancelled.discard(run_id)
                if self.active == run_id:
                    self.active = None

    def cancel(self, run_id):
        with self.lock:
            if self.active != run_id or self.process is None:
                raise Problem('No active process to cancel', 409)
            self.cancelled.add(run_id)
            self._stop(self.process)
        return {'cancel_requested': True}

    def delete(self, run_id):
        with self.lock:
            if self.active == run_id:
                raise Problem('Cannot delete an active experiment', 409)
            folder = self._directory(run_id)
            shutil.rmtree(folder)
        return {'deleted': True}

    def archive(self, run_id):
        folder = self._directory(run_id)
        state = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        if state['state'] in ('queued', 'running'):
            raise Problem('The experiment has not finished', 409)
        return create_support_bundle(folder / 'SQE-experiment-support.zip', folder,
                                     category='ecosystem-experiment', job=state,
                                     include_inputs=True)
