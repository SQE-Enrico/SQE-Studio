"""EDA capability declarations and UI use cases must remain fail closed."""
from pathlib import Path
import copy
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request

import pytest
from sqe_studio.design_library import instantiate, list_templates, use_case_catalog
from sqe_studio.eda.capabilities import list_capabilities
from sqe_studio.adapters.scqubits_adapter import _spec
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.contracts import validate_project
from sqe_studio.server import make_server


def test_examples_are_generic_project_models_with_no_fake_science():
    cases = use_case_catalog()
    template_ids = {t['id'] for t in list_templates()}
    assert len(cases) >= 6
    assert len({c['id'] for c in cases}) == len(cases)
    assert {c['starter_template'] for c in cases if c['starter_template']} == template_ids
    assert all(c['reference_url'].startswith('https://') for c in cases)
    for c in cases:
        if c['readiness'] == 'blocked_missing_edge':
            assert c['starter_template'] is None
            assert c['next_missing_edge']
            continue
        assert c['starter_template']
        model = instantiate(c['starter_template'], 'Regular Project', c['family'])
        assert validate_project(model) is model
        assert model['process']['source'] == 'unverified'
        assert model['schema'] == 'sqe.project.v1'
        assert model['studies']
        if model['studies'][0]['engine'] == 'scqubits':
            assert model['studies'][0]['inputs']['source'] == 'independent'
            result = _spec(model['studies'][0]['inputs'], model)
            assert result['source'] == 'independent'
    a = instantiate('transmon_spectrum_v1', 'First', 'transmon')
    b = instantiate('transmon_spectrum_v1', 'Second', 'transmon')
    a['studies'][0]['inputs']['parameters']['EJ'] = 99
    assert b['studies'][0]['inputs']['parameters']['EJ'] == 15.0
    with pytest.raises(ValueError):
        instantiate('epr_transmon_resonator', 'Injection', 'multi_qubit')
    with pytest.raises(ValueError):
        instantiate('transmon_spectrum_v1', 'Wrong', 'resonator')


def test_capabilities_are_explicit_and_blocked_edges_cannot_be_advertised():
    edges = list_capabilities()
    assert len({edge['id'] for edge in edges}) == len(edges)
    assert {'em_to_hamiltonian', 'sheet_to_palace', 'schematic_to_julia', 'cad_to_fab'} <= {
        edge['id'] for edge in edges if edge['status'] == 'blocked'}
    assert all(edge['scientific_gate'] and edge['prerequisite'] for edge in edges)
    assert all(edge['provider'] != 'not_implemented' for edge in edges if edge['status'] != 'blocked')
    edges[0]['source'] = 'tampered'
    assert list_capabilities()[0]['source'] != 'tampered'


def test_use_case_registry_is_visible_only_to_authenticated_gui(tmp_path):
    http = make_server(tmp_path/'private', 0)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{http.server_port}'
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(__import__("http.cookiejar", fromlist=["CookieJar"]).CookieJar()),
                                             urllib.request.ProxyHandler({}))
        def call(path, method='GET', data=None, csrf=''):
            headers = {}
            if data is not None: headers['Content-Type'] = 'application/json'
            if csrf: headers['X-CSRF-Token'] = csrf
            r = urllib.request.Request(url+path, method=method, headers=headers,
                                       data=json.dumps(data).encode() if data is not None else None)
            try: response = client.open(r, timeout=8)
            except urllib.error.HTTPError as err: response = err
            with response: return response.status, json.loads(response.read())
        assert call('/api/design/use-cases')[0] == 401
        assert call('/api/design/capabilities')[0] == 401
        assert call('/api/setup', 'POST', {'setup_token':http.app.setup_file.read_text(encoding='utf-8'),
                       'email':'cases@test.local','password':'very-long-test-password'})[0] == 200
        csrf = call('/api/login','POST',{'email':'cases@test.local',
                                       'password':'very-long-test-password'})[1]['csrf']
        status, cases = call('/api/design/use-cases')
        assert status == 200 and cases['schema'] == 'sqe.design-cases.v1'
        assert len(cases['cases']) == 6
        status, capabilities = call('/api/design/capabilities')
        assert status == 200 and capabilities['schema'] == 'sqe.eda-capability-map.v1'
        assert len(capabilities['edges']) >= 8
        assert call('/api/projects','POST',{'name':'Unreviewed EPR', 'family':'multi_qubit',
                         'template_id':'epr_transmon_resonator'},csrf)[0] == 422
        status, project = call('/api/projects','POST',{'name':'Editable Spectrum','family':'transmon',
                                       'template_id':'transmon_spectrum_v1'},csrf)
        assert status == 201 and project['model']['studies'][0]['engine'] == 'scqubits'
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=3)


def test_client_only_shows_case_info_not_engine_shortcuts():
    app=(Path(__file__).resolve().parents[2]/'src/sqe_studio/web/app.js').read_text(encoding='utf-8')
    assert 'function useCaseOverview' in app
    assert 'function capabilityOverview' in app
    assert 'Published-method design cases' in app
    assert 'Missing / blocked' in app
