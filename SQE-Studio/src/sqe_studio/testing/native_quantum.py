"""Native test of the ordinary saved-project -> job -> authenticated Results API.

No surrogate spectrum. All data live in a new temporary workstation workspace.
"""
from __future__ import annotations

import hashlib
import http.cookiejar
from importlib import metadata, util
import json
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
import urllib.error
import io
import zipfile


def run_workflow():
    if util.find_spec('scqubits') is None:
        return {'status': 'BLOCKED', 'reason': 'SCQUBITS_NOT_INSTALLED', 'execution_kind': 'NOT_RUN'}
    try:
        version = metadata.version('scqubits')
    except metadata.PackageNotFoundError:
        version = 'unknown'
    if version != '4.3.1':
        return {'status': 'BLOCKED', 'reason': 'SCQUBITS_PIN_REQUIRES_4_3_1',
                'engine_version': version, 'execution_kind': 'NOT_RUN'}
    from sqe_studio.server import make_server
    with tempfile.TemporaryDirectory(prefix='sqe-m17-native-quantum-') as td:
        server = make_server(Path(td) / 'data', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                            urllib.request.ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        csrf = ''
        def request(path, body=None):
            headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}
            req = urllib.request.Request(base + path, headers=headers,
                data=json.dumps(body).encode() if body is not None else None)
            try:
                response = client.open(req, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(2_000_000)
                result = json.loads(raw)
                if response.status >= 400:
                    raise ValueError('HTTP_WORKFLOW_' + str(response.status))
                return result
        rows = []
        started = time.monotonic()
        try:
            request('/api/setup', {'setup_token': server.app.setup_file.read_text(),
                                  'email': 'm17@example.invalid', 'password': 'M17TemporaryWorkflow123!'})
            csrf = request('/api/login', {'email': 'm17@example.invalid',
                                         'password': 'M17TemporaryWorkflow123!'})['csrf']
            for family in ('transmon', 'fluxonium'):
                project = request('/api/projects', {'name': 'M17 ' + family,
                    'family': family, 'template_id': family + '_spectrum_v1'})
                pid = project['id']
                model = project['model']
                study = model['studies'][0]
                inputs = study['inputs']
                inputs.pop('sweep', None)
                inputs['parameters']['ncut' if family == 'transmon' else 'cutoff'] = (15 if family == 'transmon' else 50)
                inputs['convergence'] = {'enabled': True, 'basis_increment': 5,
                                         'steps': 3, 'tolerance_GHz': 1e-5}
                revision = request(f'/api/projects/{pid}/commit',
                    {'expected_revision': project['head'], 'model': model})['revision']
                run_id = request(f'/api/projects/{pid}/runs',
                    {'revision': revision, 'study_id': study['id']})['run_id']
                while True:
                    runs = request(f'/api/projects/{pid}/runs')['runs']
                    job = next(r for r in runs if r['id'] == run_id)
                    if job['state'] not in ('queued', 'running'):
                        break
                    if time.monotonic() - started > 185:
                        return {'status': 'TIMEOUT', 'reason': 'NATIVE_QUANTUM_WORKFLOW_BUDGET',
                                'execution_kind': 'NATIVE', 'models': rows}
                    time.sleep(.25)
                if job['state'] != 'completed':
                    diagnostics = {}
                    try:
                        with client.open(base+f'/api/projects/{pid}/runs/{run_id}/download', timeout=10) as response:
                            raw = response.read(1_000_001)
                        if len(raw) <= 1_000_000:
                            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                                for name in archive.namelist()[:40]:
                                    if name.rsplit('/', 1)[-1] in ('FAILURE.json','engine.log'):
                                        with archive.open(name) as stream:
                                            diagnostics[name.rsplit('/',1)[-1]] = stream.read(32000).decode('utf-8','replace')
                    except (OSError, ValueError, zipfile.BadZipFile, urllib.error.URLError):
                        diagnostics['availability'] = 'DIAGNOSTIC_ARCHIVE_UNAVAILABLE'
                    return {'status': 'FAIL', 'reason': 'NATIVE_JOB_' + job['state'].upper(),
                            'execution_kind': 'NATIVE', 'models': rows, 'diagnostics': diagnostics}
                result = request(f'/api/projects/{pid}/runs/{run_id}/result')
                spectrum = result['spectrum']
                manifest = result['manifest']
                curve = spectrum['convergence']
                if (manifest['revision_id'] != revision or curve.get('steps') != 3
                        or len(curve['points'][0]['curve']) != 4):
                    raise ValueError('NATIVE_RESULTS_CONTRACT_MISMATCH')
                reference = next(r for r in result['scientific_references']['evaluations']
                                 if r['case_id'] == 'T01_KOCH_ASYMPTOTIC')
                numeric = curve['numeric_status']
                theory = reference['status']
                okay = numeric == 'NUMERICAL_PASS' and (family != 'transmon' or theory == 'NUMERICAL_PASS')
                rows.append({'model': family, 'status': 'PASS' if okay else 'FAIL',
                             'native_execution': 'PASS', 'basis_convergence': numeric,
                             'theory_reference': reference, 'convergence': curve,
                             'saved_revision': revision,
                             'input_sha256': spectrum['input_sha256'],
                             'native_artifacts': manifest['artifacts'],
                             'engine_version': manifest['engine_version'],
                             'em_transfer': 'BLOCKED', 'physical_validation': 'NOT_ESTABLISHED'})
            request('/api/logout', {})
            return {'status': 'PASS' if all(r['status'] == 'PASS' for r in rows) else 'FAIL',
                    'execution_kind': 'NATIVE', 'models': rows,
                    'units': 'E/h in GHz; charge 2e; flux Phi0',
                    'workflow': 'saved_project_http_job_verified_results',
                    'scientific_qualification': 'NOT_ESTABLISHED'}
        finally:
            # Cancel only jobs owned by this temporary server before deleting it.
            with server.app.jobs._mutex:
                controls = list(server.app.jobs._active.values())
            for control in controls:
                control.cancel.set()
            deadline = time.monotonic() + 8
            while server.app.jobs._active and time.monotonic() < deadline:
                time.sleep(.1)
            server.shutdown()
            server.server_close()
            thread.join(timeout=4)
