"""M7: conditional transmon run-to-run drift, synthetic native fixtures only."""
from __future__ import annotations

import copy
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import shutil
import threading
import urllib.error
import urllib.request

import pytest

from sqe_studio.interop.transmon_comparison import compare_conditional_transmon_screens
from sqe_studio.interop.transmon_workflow import inspect_saved_transmon_screen
from sqe_studio.server import make_server

_FIXTURE_PATH = Path(__file__).with_name('test_rc14_20_transmon_workflow.py')
_spec = importlib.util.spec_from_file_location('_m7_transmon_fixture', _FIXTURE_PATH)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)

MATRIX = {'status': 'native_maxwell_matrix_differences_for_expert_review',
          'same_native_matrix_sha256': False}


def example(tmp_path):
    folder, manifest, project = _fixture.prepared(tmp_path)
    screen = inspect_saved_transmon_screen(folder, manifest, project)
    return folder, manifest, project, screen


def compare(a, b, selection, other=None, matrix=None):
    return compare_conditional_transmon_screens(
        a, b, selection, selection if other is None else other,
        MATRIX if matrix is None else matrix)


def test_conditional_capacitance_and_ec_changes_have_signs_but_no_physics_claim(tmp_path):
    _, _, project, screen = example(tmp_path)
    other = copy.deepcopy(screen)
    first = screen['reduction']['numerical_preview']
    second = other['reduction']['numerical_preview']
    second['effective_capacitance_f'] *= 1.04
    second['ec_over_h_hz_matrix_only'] /= 1.04
    saved = project['model']['intent']['transmon_capacitance_selection']
    result = compare(screen, other, saved)
    assert result['schema'] == 'sqe.conditional-transmon-drift.m7.v1'
    assert result['status'] == 'conditional_transmon_matrix_reduction_drift_for_expert_review'
    assert result['delta_effective_capacitance_fF'] > 0
    assert result['delta_ec_over_h_MHz_matrix_only'] < 0
    assert result['relative_effective_capacitance_change'] == pytest.approx(0.04/1.04)
    assert result['mesh_convergence'] == 'NOT_ESTABLISHED'
    assert result['em_to_scqubits_transfer'] == 'BLOCKED'
    assert result['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert result['fabrication'] == 'HOLD'
    assert result['same_native_matrix_sha256'] is False


@pytest.mark.parametrize('case', [
    'no_source', 'no_selection', 'incompatible_matrix', 'different_selection',
    'no_reduction', 'wrong_status', 'wrong_transfer', 'wrong_mapping',
    'revision_source_changed', 'floating_changed', 'nan', 'zero', 'unit_bad',
    'missing_source_sha', 'wrong_hamiltonian',
])
def test_both_verified_inputs_and_identical_assumptions_are_required(tmp_path, case):
    _, _, project, screen = example(tmp_path)
    left, right = copy.deepcopy(screen), copy.deepcopy(screen)
    saved = copy.deepcopy(project['model']['intent']['transmon_capacitance_selection'])
    other = copy.deepcopy(saved)
    matrix = MATRIX
    if case == 'no_source': right = None
    if case == 'no_selection': saved = None
    if case == 'incompatible_matrix': matrix = {'status': 'not_comparable'}
    if case == 'different_selection': other['island_a'] = 'another'
    if case == 'no_reduction': right['reduction'] = None
    if case == 'wrong_status': right['status'] = 'APPROVED'
    if case == 'wrong_transfer': right['scqubits_EC_transfer'] = 'AUTHORIZED'
    if case == 'wrong_mapping': right['native_mapping']['geometry_registration'] = 'REVIEWED'
    if case == 'revision_source_changed': right['reduction']['source']['revision_digest'] = '0' * 64
    if case == 'floating_changed': right['reduction']['numerical_preview']['floating_zero_charge'] = ['guard']
    if case == 'nan': right['reduction']['numerical_preview']['effective_capacitance_f'] = float('nan')
    if case == 'zero': right['reduction']['numerical_preview']['effective_capacitance_f'] = 0
    if case == 'unit_bad': right['reduction']['numerical_preview']['ec_over_h_hz_matrix_only'] = '1.2'
    if case == 'missing_source_sha': right['reduction']['source']['manifest_sha256'] = 'x' * 64
    if case == 'wrong_hamiltonian': right['reduction']['scqubits_parameter'] = {'EC': 2.0}
    result = compare(left, right, saved, other=other, matrix=matrix)
    assert result['status'] == 'not_comparable'
    assert result['em_to_scqubits_transfer'] == 'BLOCKED'
    assert 'delta_effective_capacitance_fF' not in result
    assert result['fabrication'] == 'HOLD'


def test_native_http_two_saved_transmon_runs_and_hash_tamper(tmp_path):
    server = make_server(tmp_path/'db', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                         urllib.request.ProxyHandler({}))
    csrf = ''
    def req(path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        if method == 'POST' and csrf: headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(base + path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        try: response = opener.open(request, timeout=15)
        except urllib.error.HTTPError as exc: response = exc
        with response: return response.status, json.loads(response.read())
    try:
        token = server.app.setup_file.read_text(encoding='utf-8')
        assert req('/api/setup', 'POST', {'email': 'm7@test.invalid', 'password': 'test-only-long-password',
                                          'setup_token': token})[0] == 200
        code, auth = req('/api/login', 'POST', {'email': 'm7@test.invalid',
                                                'password': 'test-only-long-password'})
        assert code == 200
        csrf = auth['csrf']
        code, created = req('/api/projects', 'POST', {'name': 'M7 fixture', 'family': 'transmon'})
        assert code == 201
        pid = created['id']
        folder, manifest, project, _ = example(tmp_path/'fixture')
        code, committed = req(f'/api/projects/{pid}/commit', 'POST',
                              {'expected_revision': created['head'], 'model': project['model']})
        assert code == 200, committed
        owner = server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        saved = server.app.store.project(owner, pid, committed['revision'])
        outputs = []
        for index, run_id in enumerate(['e' * 32, 'f' * 32]):
            root = server.app.store.root/'native-runs'/pid/run_id
            shutil.copytree(folder, root/'output')
            out = root/'output'
            man = copy.deepcopy(manifest)
            man['revision_id'] = saved['revision']
            man['project_digest'] = saved['revision_digest']
            man['provenance'] = {'used_revision': saved['revision'],
                                 'used_project_sha256': saved['revision_digest']}
            (out/'RESULT_MANIFEST.json').write_text(json.dumps(man), encoding='utf-8')
            if index:
                csvname = 'sqe_em/outputFiles/terminal-C.csv'
                (out/csvname).write_text('Terminal,C1 (fF),C2 (fF)\n1,160,-52\n2,-52,162\n',
                                         encoding='utf-8')
                _fixture.A11.rehash(out, csvname)
            server.app.store.put_run(owner, pid, saved['revision'], man['study_id'], 'sqdmetal_palace', root)
            server.app.store.set_run(run_id, 'completed')
            outputs.append(out)
        path = f'/api/projects/{pid}/compare?left={"e" * 32}&right={"f" * 32}'
        status, response = req(path)
        assert status == 200, response
        diag = response['transmon_reduction_comparison']
        assert diag['status'] == 'conditional_transmon_matrix_reduction_drift_for_expert_review'
        assert diag['left_native_manifest_sha256'] != diag['right_native_manifest_sha256']
        assert diag['delta_effective_capacitance_fF'] != 0
        assert diag['delta_ec_over_h_MHz_matrix_only'] != 0
        assert diag['em_to_scqubits_transfer'] == 'BLOCKED'
        assert diag['fabrication'] == 'HOLD'
        assert response['numerical_comparison']['mesh_convergence'] == 'NOT_ESTABLISHED'
        # A damaged native CSV must never reach a successful comparison.
        (outputs[1]/'sqe_em/outputFiles/terminal-C.csv').write_bytes(b'altered')
        assert req(path)[0] == 409
        assert req('/api/logout', 'POST', {})[0] == 200
        assert req(path)[0] == 401
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
