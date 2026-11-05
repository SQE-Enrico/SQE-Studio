"""RC14.19 electrostatic Results acceptance: fixtures are NOT native solver evidence."""
from __future__ import annotations

import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

from sqe_studio.contracts import digest
from sqe_studio.interop.laptop_benchmark import BenchmarkBlocked, _native_terminal_matrix
from sqe_studio.interop.native_capacitance_evidence import (
    NativeCapacitanceEvidenceError, native_capacitance_evidence,
    parse_native_capacitance_table,
)
from sqe_studio.orchestration.artifacts import ArtifactInvalid, verify_manifest

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / 'extraction' / 'test_capacitance_science.py'
_spec = importlib.util.spec_from_file_location('_a17_electrostatic_fixture_for_rc1419', _FIXTURE_PATH)
_fixture_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_mod)


def fixture(tmp_path):
    model, folder, _evidence = _fixture_mod._capacitance_fixture(tmp_path)
    manifest = json.loads((folder/'RESULT_MANIFEST.json').read_text(encoding='utf-8'))
    project = {'revision': manifest['revision_id'], 'revision_digest': digest(model), 'model': model}
    return model, folder, manifest, project


def rehash(folder, name):
    path = folder/name
    manifest_file = folder/'RESULT_MANIFEST.json'
    data = json.loads(manifest_file.read_text(encoding='utf-8'))
    entry = next(row for row in data['artifacts'] if row['name'] == name)
    entry.update(sha256=sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    manifest_file.write_text(json.dumps(data), encoding='utf-8')
    return data


def verified(folder, manifest, project):
    verify_manifest(folder, revision_id=project['revision'], project_digest=project['revision_digest'],
                    study_id=manifest['study_id'], engine='sqdmetal_palace')
    return native_capacitance_evidence(folder, manifest, project)


def test_legacy_reviewed_b04_matrix_now_visible_as_revision_bound_screen(tmp_path):
    model, folder, manifest, project = fixture(tmp_path)
    out = verified(folder, manifest, project)
    assert out['schema'] == 'sqe.native-capacitance-screen.v1'
    assert out['conductor_order'] == ['LP1', 'LP2']
    assert out['capacitance_matrix_F'][0] == pytest.approx([150e-15, -50e-15])
    assert out['conditional_island_indicators'][0]['conditional_EC_over_h_GHz'] == pytest.approx(0.129123, rel=5e-4)
    assert out['scqubits_EC_transfer'].startswith('BLOCKED')
    assert out['fabrication'] == 'HOLD'
    assert out['required_reviews']


def test_documented_palace_scientific_notation_and_farad_header(tmp_path):
    model, folder, manifest, project = fixture(tmp_path)
    name = 'sqe_em/outputFiles/terminal-C.csv'
    (folder/name).write_text('i,C[i][1] (F),C[i][2] (F)\n'
                             '1.00e+00,1.50e-13,-5.00e-14\n'
                             '2.00e+00,-5.00e-14,1.60e-13\n',encoding='utf-8')
    manifest = rehash(folder, name)
    out = verified(folder, manifest, project)
    assert out['native_source_unit'] == 'F'
    assert out['capacitance_matrix_F'][1] == pytest.approx([-50e-15,160e-15])
    assert _native_terminal_matrix(folder/name, unit='F', count=2)[0][0] == pytest.approx(150e-15)
    with pytest.raises(BenchmarkBlocked, match='units disagree'):
        _native_terminal_matrix(folder/name, unit='fF', count=2)


@pytest.mark.parametrize('text', [
    'i,C[i][1],C[i][2]\n1,1.5e-13,-5e-14\n2,-5e-14,1.6e-13\n',
    'i,C[i][2] (F),C[i][1] (F)\n1,1.5e-13,-5e-14\n2,-5e-14,1.6e-13\n',
    'i,C[i][1] (F),C[i][2] (fF)\n1,1.5e-13,-5e-14\n2,-5e-14,1.6e-13\n',
    'i,C[i][1] (F),C[i][2] (F)\n1,1.5e-13,-5e-14\n2,nan,1.6e-13\n',
    'i,C[i][1] (F),C[i][2] (F)\n2,1.5e-13,-5e-14\n1,-5e-14,1.6e-13\n',
])
def test_reject_ambiguous_or_nonfinite_palace_csv(tmp_path, text):
    path = tmp_path/'terminal-C.csv'
    path.write_text(text,encoding='utf-8')
    with pytest.raises(NativeCapacitanceEvidenceError):
        parse_native_capacitance_table(path, count=2)


@pytest.mark.parametrize('mutation', ['changed_csv_bytes', 'wrong_revision', 'wrong_ground_tag',
                                      'changed_study_port', 'bad_palace_exit', 'positive_mutual',
                                      'asymmetric', 'unreviewed_stack'])
def test_fail_closed_on_integrity_geometry_and_physics(tmp_path, mutation):
    model, folder, manifest, project = fixture(tmp_path)
    name = 'sqe_em/outputFiles/terminal-C.csv'
    if mutation == 'changed_csv_bytes':
        (folder/name).write_text('Terminal,C1 (fF),C2 (fF)\n1,151,-50\n2,-50,160\n',encoding='utf-8')
        with pytest.raises(ArtifactInvalid):
            verified(folder, manifest, project)
        return
    if mutation == 'wrong_revision':
        project['revision'] = 'b'*32
    elif mutation == 'wrong_ground_tag':
        p = folder/'sqe_em/sqe_em.json'
        obj = json.loads(p.read_text(encoding='utf-8'))
        obj['Boundaries']['Ground']['Attributes'] = [9]
        p.write_text(json.dumps(obj),encoding='utf-8')
        manifest = rehash(folder, 'sqe_em/sqe_em.json')
    elif mutation == 'changed_study_port':
        model['studies'][0]['inputs']['em']['ports'][0]['native_attributes'] = [11]
        project['revision_digest'] = manifest['project_digest'] = digest(model)
        manifest['provenance']['used_project_sha256'] = project['revision_digest']
        (folder/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    elif mutation == 'bad_palace_exit':
        p = folder/'a03-native-artifacts.json'
        obj = json.loads(p.read_text(encoding='utf-8'))
        obj['native_completion']['exit_code'] = 1
        p.write_text(json.dumps(obj),encoding='utf-8')
        manifest = rehash(folder,'a03-native-artifacts.json')
    elif mutation in ('positive_mutual','asymmetric'):
        text = ('Terminal,C1 (fF),C2 (fF)\n1,150,50\n2,50,160\n' if mutation == 'positive_mutual' else
                'Terminal,C1 (fF),C2 (fF)\n1,150,-50\n2,-2,160\n')
        (folder/name).write_text(text, encoding='utf-8')
        manifest = rehash(folder,name)
    else:
        model['process']['source'] = 'unverified'
        project['revision_digest'] = manifest['project_digest'] = digest(model)
        manifest['provenance']['used_project_sha256'] = project['revision_digest']
        (folder/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    if mutation == 'wrong_revision':
        with pytest.raises(ArtifactInvalid):
            verified(folder, manifest, project)
    else:
        with pytest.raises(NativeCapacitanceEvidenceError):
            verified(folder, manifest, project)


def test_absent_capacitance_is_not_synthesized(tmp_path):
    _, folder, manifest, project = fixture(tmp_path)
    manifest['artifact_type'] = 'palace.eigenmodes'
    assert native_capacitance_evidence(folder, manifest, project) is None


def test_authenticated_results_exposes_capacitance_but_never_active_quantum_mapping(tmp_path):
    """Production HTTP route, with fixture bytes only (no solver executed)."""
    import http.cookiejar
    import shutil
    import threading
    import urllib.error
    import urllib.request
    from sqe_studio.server import make_server

    server = make_server(tmp_path/'data', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.ProxyHandler({}))
    csrf = ''

    def req(path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        if method == 'POST' and csrf:
            headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(base+path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        try:
            response = opener.open(request, timeout=8)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())
    try:
        assert req('/api/projects/'+'a'*32+'/runs/'+'a'*32+'/result')[0] == 401
        token = server.app.setup_file.read_text(encoding='utf-8')
        assert req('/api/setup','POST',{'email':'cap@test.invalid','password':'test-only-long-password',
                                      'setup_token':token})[0] == 200
        code,auth = req('/api/login','POST',{'email':'cap@test.invalid','password':'test-only-long-password'})
        assert code == 200
        csrf = auth['csrf']
        code, created = req('/api/projects','POST',{'name':'Electrostatic fixture','family':'resonator'})
        assert code == 201
        pid = created['id']
        model, folder, manifest, _project = fixture(tmp_path/'native_fixture')
        code, committed = req(f'/api/projects/{pid}/commit','POST',
                               {'expected_revision':created['head'],'model':model})
        assert code == 200, committed
        revision = committed['revision']
        owner = server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        saved = server.app.store.project(owner, pid, revision)
        run_id = 'e'*32
        run_folder = server.app.store.root/'native-runs'/pid/run_id
        shutil.copytree(folder,run_folder/'output')
        output = run_folder/'output'
        manifest['revision_id'] = revision
        manifest['project_digest'] = saved['revision_digest']
        manifest['provenance'] = {'used_revision': revision,
                                  'used_project_sha256': saved['revision_digest']}
        (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
        server.app.store.put_run(owner,pid,revision,manifest['study_id'],'sqdmetal_palace',run_folder)
        server.app.store.set_run(run_id,'completed')
        url = f'/api/projects/{pid}/runs/{run_id}/result'
        code, report = req(url)
        assert code == 200, report
        assert report['capacitance_evidence']['schema'] == 'sqe.native-capacitance-screen.v1'
        assert report['capacitance_evidence']['scqubits_EC_transfer'].startswith('BLOCKED')
        assert report['design_target_screen']['automatic_optimization'] == 'BLOCKED'
        # Even a correctly stored response must fail closed after native bytes change.
        (output/'sqe_em/outputFiles/terminal-C.csv').write_text('modified',encoding='utf-8')
        assert req(url)[0] == 409
        assert req('/api/logout','POST',{})[0] == 200
        assert req(url)[0] == 401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
