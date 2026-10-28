"""Local-only diagnostic runs exposed to authenticated workstation administrators.

Never executes user-provided commands. Diagnostics are opt-in, isolated from user
projects, allowlisted, and downloadable only after explicit review. The Web
server stays responsive while fixed checks execute in a background thread.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
import zipfile

from .auth import Problem
from ..diagnostics import VERSION, bundle, scrub, PROFILES, profile_cases

ID = re.compile(r"^[0-9a-f]{32}$")
LIMIT = 15


class DiagnosticControl:
    def __init__(self, storage: Path, source_root: Path):
        self.storage = storage / 'diagnostic-reports'
        self.source_root = source_root
        self.storage.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.worker = None
        self.active = None
        # A server restart must not leave an old run marked as active forever.
        for file in self.storage.glob('*/status.json'):
            try:
                state = json.loads(file.read_text(encoding='utf-8'))
                if state.get('state') in ('queued', 'running'):
                    state.update(state='interrupted', error='The application restarted during this diagnostic run.')
                    self._atomic(file, state)
            except (OSError, ValueError):
                pass

    @staticmethod
    def _atomic(path: Path, value: dict):
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        os.replace(temp, path)

    def _folder(self, run_id):
        if not ID.fullmatch(str(run_id)):
            raise Problem('Invalid diagnostic run identifier', 404)
        folder = self.storage / run_id
        if not folder.is_dir() or folder.is_symlink():
            raise Problem('Diagnostic run was not found', 404)
        return folder

    def _state(self, run_id):
        path = self._folder(run_id) / 'status.json'
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise Problem('Diagnostic report is not available', 404)

    def list(self):
        values = []
        for path in self.storage.glob('*/status.json'):
            if path.parent.is_symlink() or not ID.fullmatch(path.parent.name):
                continue
            try:
                values.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return sorted(values, key=lambda x: x.get('created_utc',''), reverse=True)[:LIMIT]

    def start(self, *, extended=False, skip_tests=False, scientific=False,
              scientific_profile="quick", full_regressions=False):
        if not all(isinstance(value, bool) for value in (extended, skip_tests, scientific, full_regressions)):
            raise Problem('Diagnostic options must be booleans')
        if skip_tests and full_regressions:
            raise Problem('Cannot request full regressions and skip tests together')
        if scientific_profile not in PROFILES:
            raise Problem('Unknown scientific profile')
        with self.lock:
            if self.active is not None:
                raise Problem('A diagnostic run is already active', 409)
            recent = self.list()
            if len(recent) >= LIMIT:
                raise Problem('Diagnostic history is full. Export and archive reports before starting more runs.', 409)
            run_id = uuid.uuid4().hex
            folder = self.storage / run_id
            folder.mkdir(mode=0o700)
            state = {'id': run_id, 'state': 'queued', 'mode': 'scientific' if scientific else 'extended' if extended else 'standard',
                     'skip_tests': skip_tests, 'full_regressions': full_regressions, 'scientific_profile': scientific_profile if scientific else None, 'created_utc': datetime.now(timezone.utc).isoformat(),
                     'completed_utc': None, 'summary': None, 'counts': None, 'error': None, 'progress': None}
            self._atomic(folder / 'status.json', state)
            self.active = run_id
            # Daemon execution permits Ctrl+C to stop the local server without
            # waiting for a slow external Julia/WSL timeout; interrupted runs
            # are marked on the next start.
            self.worker = threading.Thread(target=self._run, args=(run_id, extended, skip_tests, scientific, scientific_profile, full_regressions),
                                           name='sqe-diagnostics', daemon=True)
            self.worker.start()
            return state

    def _run(self, run_id, extended, skip_tests, scientific, scientific_profile, full_regressions):
        folder = self._folder(run_id)
        state = self._state(run_id)
        try:
            state['state'] = 'running'
            if scientific:
                state['progress'] = {'current_check':'preflight', 'completed':0, 'total': len(profile_cases(scientific_profile)), 'message':'System checks and software preflight'}
            self._atomic(folder / 'status.json', state)
            def progress(update):
                # Each stage completion remains inspectable while the run executes.
                current = self._state(run_id)
                if current['state'] == 'running':
                    current['progress'] = update
                    self._atomic(folder / 'status.json', current)
            options = dict(extended=extended, skip_tests=skip_tests)
            if full_regressions:
                options['full_regressions'] = True
            if scientific:
                options.update(scientific=True, stage_callback=progress, scientific_profile=scientific_profile)
            zip_path, checks = bundle(self.source_root, folder, **options)
            counts = {name: sum(c['status'] == name for c in checks) for name in ('PASS','WARN','FAIL','SKIP')}
            state = self._state(run_id)
            state['counts'] = counts
            state['state'] = 'completed'
            state['summary'] = ('FAIL' if counts['FAIL'] else 'WARN' if counts['WARN'] else 'PASS')
            state['bundle'] = zip_path.name
        except Exception as exc:
            message = scrub(str(exc), self.source_root)[:300]
            state.update(state='failed', summary='FAIL', error=message)
            # Unexpected probe failures must still be reportable by one click.
            # The fallback archive contains no project files or arbitrary logs.
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
            name = f'SQE-DIAGNOSTICS-v{VERSION}-{timestamp}.zip'
            with zipfile.ZipFile(folder / name, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('SUMMARY.txt', 'Diagnostic execution failed.\n' + message + '\n')
                archive.writestr('checks.json', json.dumps([{
                    'id': 'diagnostics.worker', 'status': 'FAIL', 'code': 'WORKER_EXCEPTION',
                    'detail': message, 'next_action': 'Inspect the system and retry.'}]))
                archive.writestr('environment.json', '{}')
                archive.writestr('README-PRIVACY.txt',
                                 'Review this sanitized, best-effort failure report before sharing.\n')
            state['bundle'] = name
        finally:
            state['completed_utc'] = datetime.now(timezone.utc).isoformat()
            self._atomic(folder / 'status.json', state)
            with self.lock:
                if self.active == run_id:
                    self.active = None

    def delete(self, run_id):
        # An explicit administrator action after any needed ZIP export.
        with self.lock:
            if self.active == run_id:
                raise Problem('Cannot delete a running diagnostic', 409)
            folder = self._folder(run_id)
            if self._state(run_id)['state'] in ('queued','running'):
                raise Problem('Cannot delete an incomplete diagnostic run',409)
            shutil.rmtree(folder)
            return {'deleted':True}

    def detail(self, run_id):
        state = self._state(run_id)
        if state['state'] in ('completed', 'failed') and state.get('bundle'):
            path = self.archive(run_id)
            with zipfile.ZipFile(path) as z:
                for name, field in [('SUMMARY.txt', 'summary_text'), ('checks.json','checks'), ('environment.json','environment')]:
                    data = z.read(name)
                    state[field] = json.loads(data) if name.endswith('.json') else data.decode('utf-8','replace')[:20000]
                if 'scientific-results.json' in z.namelist():
                    state['scientific_results'] = json.loads(z.read('scientific-results.json'))
        return state

    def archive(self, run_id):
        state = self._state(run_id)
        if state.get('state') not in ('completed', 'failed'):
            raise Problem('The diagnostic ZIP is not ready yet', 409)
        name = state.get('bundle','')
        if not re.fullmatch(r'SQE-DIAGNOSTICS-v[0-9.]+-[0-9]{8}-[0-9]{6}Z\.zip', name):
            raise Problem('Invalid diagnostic ZIP', 404)
        path = self._folder(run_id) / name
        if path.is_symlink() or not path.is_file():
            raise Problem('Diagnostic ZIP is missing', 404)
        return path
