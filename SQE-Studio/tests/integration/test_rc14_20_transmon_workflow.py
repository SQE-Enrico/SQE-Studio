"""A99 integrator regression: two agent modules bound to a saved revision.

All Palace/Gmsh input is synthetic-fixture evidence. No native solver runs.
"""
import copy
from hashlib import sha256
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import shutil
import threading
import urllib.error
import urllib.request

import pytest
from sqe_studio.contracts import digest
from sqe_studio.interop.transmon_workflow import inspect_saved_transmon_screen
from sqe_studio.interop.capacitance_topology import CapacitanceTopologyBlocked
from sqe_studio.server import make_server

SPEC = importlib.util.spec_from_file_location(
    '_a11_synthetic', Path(__file__).resolve().parents[1] / 'fields/test_capacitance_topology.py')
A11 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A11)


def selection(study):
    return {
        'schema': 'sqe.saved-transmon-capacitance-selection.v1',
        'study_id': study,
        'island_a': 'LP1', 'island_b': 'LP2',
        'other_terminal_policy': {'fixed_zero': [], 'floating_zero_charge': []},
        'configuration': 'TWO_ISLAND_CHARGE_TRANSFER',
        'junction_capacitance_assumption': 'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED',
    }


def prepared(tmp_path):
    folder, manifest, project, _ = A11.setup(tmp_path)
    project['model']['family'] = 'transmon'
    project['model']['intent']['transmon_capacitance_selection'] = selection(manifest['study_id'])
    project['revision_digest'] = digest(project['model'])
    manifest['project_digest'] = project['revision_digest']
    manifest['provenance']['used_project_sha256'] = project['revision_digest']
    (folder/'RESULT_MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    return folder, manifest, project


def test_two_agent_pipeline_binds_saved_snapshot_and_never_authorizes_ec(tmp_path):
    folder, manifest, project = prepared(tmp_path)
    out = inspect_saved_transmon_screen(folder, manifest, project)
    assert out['status'] == 'NUMERICAL_SCREEN_ONLY'
    assert out['native_topology']['scientific_status'] == 'UNREVIEWED_TOPOLOGY'
    assert out['native_topology']['source']['revision_digest'] == project['revision_digest']
    assert out['native_mapping']['geometry_registration'].startswith('BLOCKED')
    assert out['reduction']['status'] == 'NUMERICAL_SCREEN_ONLY'
    assert out['reduction']['numerical_preview']['effective_capacitance_f'] > 0
    assert out['reduction']['numerical_preview']['ec_over_h_hz_matrix_only'] > 0
    assert out['reduction']['scqubits_parameter'] is None
    assert out['reduction']['ej_over_h_hz'] is None
    assert out['scqubits_EC_transfer'] == 'BLOCKED_NOT_REVIEWED'
    assert out['fabrication'] == 'HOLD'


def test_no_saved_selection_is_blocked_without_guessing(tmp_path):
    folder, manifest, project = prepared(tmp_path)
    del project['model']['intent']['transmon_capacitance_selection']
    out = inspect_saved_transmon_screen(folder, manifest, project)
    assert out['status'] == 'BLOCKED_NO_SAVED_SELECTION'
    assert out['reduction'] is None
    assert out['scqubits_EC_transfer'].startswith('BLOCKED')


@pytest.mark.parametrize('mutation', ['bad_revision_selection', 'wrong_study', 'duplicate_islands',
                                      'missing_junction_assumption', 'unclassified_port',
                                      'tamper_csv', 'tamper_mesh', 'wrong_saved_digest'])
def test_fail_closed_without_inferring_conductor_mapping(tmp_path, mutation):
    folder, manifest, project = prepared(tmp_path)
    opts = project['model']['intent']['transmon_capacitance_selection']
    if mutation == 'bad_revision_selection':
        opts['revision_digest'] = '0'*64  # forbidden self-referential field
    elif mutation == 'wrong_study':
        opts['study_id'] = 'other_study'
    elif mutation == 'duplicate_islands':
        opts['island_b'] = 'LP1'
    elif mutation == 'missing_junction_assumption':
        opts.pop('junction_capacitance_assumption')
    elif mutation == 'unclassified_port':
        opts['other_terminal_policy']['floating_zero_charge'] = ['LP1']
    elif mutation == 'tamper_csv':
        (folder/'sqe_em/outputFiles/terminal-C.csv').write_bytes(b'fake')
    elif mutation == 'tamper_mesh':
        (folder/'sqe_em/sqe_em.msh').write_bytes(b'fake')
    else:
        project['revision_digest'] = '0'*64
    with pytest.raises(CapacitanceTopologyBlocked):
        inspect_saved_transmon_screen(folder, manifest, project)


def test_wrong_family_and_wrong_engine_do_not_call_quantum_pipeline(tmp_path):
    folder, manifest, project = prepared(tmp_path)
    assert inspect_saved_transmon_screen(folder, {**manifest, 'artifact_type': 'palace.eigenmodes'}, project) is None
    project['model']['family'] = 'resonator'
    assert inspect_saved_transmon_screen(folder, manifest, project) is None


def test_saved_revision_authenticated_http_and_tamper_409(tmp_path):
    server = make_server(tmp_path/'storage', 0)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    base = f'http://127.0.0.1:{server.server_port}'
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                     urllib.request.ProxyHandler({}))
    csrf = ''
    def req(path, method='GET', data=None):
        headers = {'Content-Type':'application/json'}
        if method == 'POST' and csrf:
            headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(base + path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        try:
            response = op.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())
    try:
        token = server.app.setup_file.read_text(encoding='utf-8')
        assert req('/api/setup','POST',{'email':'m1@test.invalid','password':'test-only-long-password',
                                      'setup_token':token})[0] == 200
        code, auth = req('/api/login','POST',{'email':'m1@test.invalid','password':'test-only-long-password'})
        assert code == 200
        csrf = auth['csrf']
        code, created = req('/api/projects','POST',{'name':'M1 Transmon','family':'transmon'})
        assert code == 201
        pid = created['id']
        folder, manifest, project = prepared(tmp_path/'fixture')
        code, committed = req(f'/api/projects/{pid}/commit','POST',
                              {'expected_revision':created['head'],'model':project['model']})
        assert code == 200, committed
        owner = server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        saved = server.app.store.project(owner,pid,committed['revision'])
        output = server.app.store.root/'native-runs'/pid/('b'*32)/'output'
        shutil.copytree(folder,output)
        manifest['revision_id'] = saved['revision']
        manifest['project_digest'] = saved['revision_digest']
        manifest['provenance'] = {'used_revision':saved['revision'],
                                   'used_project_sha256':saved['revision_digest']}
        (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
        run_id = server.app.store.put_run(owner,pid,saved['revision'],manifest['study_id'],
                                          'sqdmetal_palace',output.parent)
        server.app.store.set_run(run_id,'completed')
        url = f'/api/projects/{pid}/runs/{run_id}/result'
        code, result = req(url)
        assert code == 200, result
        # M3 dossier is current-head-only, sourced from the authenticated Store,
        # and includes physical-review gaps rather than scientific approval.
        b04 = result['b04_case_readiness']
        assert b04['schema'] == 'sqe.native-capacitance-case-readiness.v1'
        assert b04['decision'] == b04['scientific_status'] == 'BLOCKED'
        assert b04['native_execution'] == 'ARTIFACT_RECORD_ONLY_NOT_ATTESTED'
        assert b04['ec_to_scqubits'] == 'BLOCKED' and b04['fabrication'] == 'HOLD'
        assert len(b04['missing_physical_evidence']) == 8
        dossier = result['capacitance_review_dossier']
        assert dossier['schema'] == 'sqe.capacitance-review-dossier.v1'
        assert dossier['source']['revision_id'] == saved['revision']
        assert dossier['source']['manifest_sha256'] == sha256((output/'RESULT_MANIFEST.json').read_bytes()).hexdigest()
        assert dossier['review']['status'] == 'NOT_APPROVED'
        assert len(dossier['review']['checklist']) == 10
        assert dossier['em_to_scqubits_transfer'] == 'BLOCKED'
        assert dossier['fabrication'] == 'HOLD'
        screen = result['transmon_capacitance_screen']
        assert screen['status'] == 'NUMERICAL_SCREEN_ONLY'
        # M8 follows exactly the rehashed native Results path; it checks SI
        # conversion, not solver physics or E_C-to-scqubits authorization.
        diagnostic = result['scientific_references']
        assert diagnostic['schema'] == 'sqe.scientific-reference-diagnostics.m8.v1'
        assert diagnostic['provenance']['revision_id'] == saved['revision']
        assert diagnostic['evaluations'][1]['status'] == 'NUMERICAL_PASS'
        assert diagnostic['fabrication'] == 'HOLD'
        assert screen['native_topology']['source']['revision_digest'] == saved['revision_digest']
        assert screen['scqubits_EC_transfer'] == 'BLOCKED_NOT_REVIEWED'
        assert result['capacitance_evidence']['fabrication'] == 'HOLD'
        # Committing a new head cannot retroactively make the historical run
        # physically reviewed. Existing source inspection remains available.
        code, newer = req(f'/api/projects/{pid}/commit','POST',
                          {'expected_revision':saved['revision'],'model':saved['model']})
        assert code == 200, newer
        code, historic = req(url)
        assert code == 200, historic
        assert 'capacitance_review_dossier' not in historic
        assert 'b04_case_readiness' not in historic
        assert historic['b04_case_readiness_status']=='BLOCKED_HISTORICAL_REVISION'
        assert historic['capacitance_review_dossier_status'] == 'BLOCKED_HISTORICAL_REVISION'
        assert historic['transmon_capacitance_screen']['scqubits_EC_transfer'] == 'BLOCKED_NOT_REVIEWED'
        (output/'sqe_em/sqe_em.msh').write_bytes(b'altered')
        assert req(url)[0] == 409
        assert req('/api/logout','POST',{})[0] == 200
        assert req(url)[0] == 401
    finally:
        server.shutdown();server.server_close();th.join(timeout=5)
