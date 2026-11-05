"""M6: B04 cross-run native Maxwell diagnostics. Fixture bytes are NOT Palace solves."""
from __future__ import annotations

import copy
import http.cookiejar
import importlib.util
import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sqe_studio.interop.comparison import compare_native_capacitance
from sqe_studio.server import make_server

_FIXTURE_PATH = Path(__file__).with_name('test_rc14_19_native_capacitance_results.py')
_spec = importlib.util.spec_from_file_location('_m6_existing_native_fixture', _FIXTURE_PATH)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


def source(tmp_path):
    model, folder, manifest, project = _fixture.fixture(tmp_path)
    return model, folder, manifest, project, _fixture.verified(folder, manifest, project)


def test_maxwell_delta_is_real_numeric_and_never_physical_approval(tmp_path):
    model, _, _, _, left = source(tmp_path)
    right = copy.deepcopy(left)
    right['capacitance_matrix_F'] = [[152e-15, -51e-15], [-51e-15, 162e-15]]
    right['native_matrix_sha256'] = 'b' * 64
    # Study identifier is read from the saved fixture, not assumed.
    study_id = model['studies'][0]['id']
    outcome = compare_native_capacitance(left, right, model, model, study_id, study_id)
    assert outcome['status'] == 'native_maxwell_matrix_differences_for_expert_review'
    assert len(outcome['rows']) == 3
    assert outcome['max_abs_delta_fF'] == pytest.approx(2)
    assert outcome['rows'][1]['delta_fF'] == pytest.approx(-1)
    assert outcome['rows'][1]['relative_difference'] == pytest.approx(1/51)
    assert outcome['convergence_verified'] is False
    assert outcome['mesh_convergence'] == 'NOT_ESTABLISHED'
    assert outcome['em_to_scqubits_transfer'] == 'BLOCKED'
    assert outcome['fabrication'] == 'HOLD'
    same = compare_native_capacitance(left, left, model, model, study_id, study_id)
    assert same['same_native_matrix_sha256'] is True


@pytest.mark.parametrize('mutation', ['layout', 'process', 'schematic', 'ports', 'order',
                                      'attributes', 'ground', 'status', 'nonfinite', 'assumption'])
def test_comparison_blocks_incompatible_sources(tmp_path, mutation):
    model, _, _, _, left = source(tmp_path)
    a, b, right = copy.deepcopy(model), copy.deepcopy(model), copy.deepcopy(left)
    if mutation in ('layout', 'process', 'schematic'):
        b[mutation] = {'different': True}
    elif mutation == 'ports':
        b['studies'][0]['inputs']['em']['ports'][0]['component'] = 'NOT_SAME'
    elif mutation == 'order':
        right['conductor_order'] = list(reversed(right['conductor_order']))
    elif mutation == 'attributes':
        right['terminal_surface_tags'] = [[700], [701]]
    elif mutation == 'ground':
        right['reference_ground_surface_tags'] = [802]
    elif mutation == 'status':
        right['scqubits_EC_transfer'] = 'APPROVED'
    elif mutation == 'nonfinite':
        right['capacitance_matrix_F'][0][0] = float('nan')
    elif mutation == 'assumption':
        right['conditional_assumption'] = 'FLOATING_NODES'
    study = model['studies'][0]['id']
    result = compare_native_capacitance(left, right, a, b, study, study)
    assert result['status'] == 'not_comparable'
    assert not result['rows']


def test_authenticated_comparison_verifies_both_manifests_and_never_promotes_ec(tmp_path):
    server = make_server(tmp_path/'db', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                         urllib.request.ProxyHandler({}))
    csrf = ''

    def req(path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        if method == 'POST' and csrf:
            headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(base + path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        try:
            response = opener.open(request, timeout=8)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    try:
        ids = ['e' * 32, 'f' * 32]
        path_template = '/api/projects/{}/compare?left=' + ids[0] + '&right=' + ids[1]
        assert req(path_template.format('a' * 32))[0] == 401
        token = server.app.setup_file.read_text(encoding='utf-8')
        assert req('/api/setup', 'POST', {'email': 'm6@test.invalid',
                                           'password': 'test-only-long-password',
                                           'setup_token': token})[0] == 200
        status, auth = req('/api/login', 'POST', {'email': 'm6@test.invalid',
                                                  'password': 'test-only-long-password'})
        assert status == 200
        csrf = auth['csrf']
        status, created = req('/api/projects', 'POST', {'name': 'M6 fixture', 'family': 'resonator'})
        assert status == 201
        pid = created['id']
        model, folder, manifest, _, _ = source(tmp_path/'source')
        status, committed = req(f'/api/projects/{pid}/commit', 'POST',
                                {'expected_revision': created['head'], 'model': model})
        assert status == 200, committed
        revision = committed['revision']
        owner = server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        saved = server.app.store.project(owner, pid, revision)
        outputs = []
        for i, run_id in enumerate(ids):
            path = server.app.store.root/'native-runs'/pid/run_id
            shutil.copytree(folder, path/'output')
            output = path/'output'
            m = copy.deepcopy(manifest)
            m['revision_id'] = revision
            m['project_digest'] = saved['revision_digest']
            m['provenance'] = {'used_revision': revision,
                               'used_project_sha256': saved['revision_digest']}
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(m), encoding='utf-8')
            if i:
                csv_name = 'sqe_em/outputFiles/terminal-C.csv'
                (output/csv_name).write_text('Terminal,C1 (fF),C2 (fF)\n1,152,-51\n2,-51,162\n', encoding='utf-8')
                _fixture.rehash(output, csv_name)
            server.app.store.put_run(owner, pid, revision, m['study_id'], 'sqdmetal_palace', path)
            server.app.store.set_run(run_id, 'completed')
            outputs.append(output)
        url = path_template.format(pid)
        status, compared = req(url)
        assert status == 200, compared
        numeric = compared['numerical_comparison']
        assert numeric['status'] == 'native_maxwell_matrix_differences_for_expert_review'
        assert numeric['rows'][0]['delta_fF'] == pytest.approx(2)
        assert numeric['rows'][1]['delta_fF'] == pytest.approx(-1)
        assert numeric['convergence_verified'] is False
        assert numeric['em_to_scqubits_transfer'] == 'BLOCKED'
        assert compared['left']['run_id'] == ids[0]
        assert compared['right']['run_id'] == ids[1]
        assert compared['left']['artifacts'] != compared['right']['artifacts']
        # Never compare pre-verification tampered bytes, even if earlier GET succeeded.
        (outputs[1]/'sqe_em/outputFiles/terminal-C.csv').write_text('corrupt', encoding='utf-8')
        assert req(url)[0] == 409
        assert req('/api/logout', 'POST', {})[0] == 200
        assert req(url)[0] == 401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
