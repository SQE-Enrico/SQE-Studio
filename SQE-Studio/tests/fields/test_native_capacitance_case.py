"""M5 B04 Store-backed preflight: every Palace artifact is a constructed fixture.

These tests assert software consistency and denial of scientific approval;
NONE verifies an executed Palace solver, real Gmsh/CAD geometry, or EC.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

from sqe_studio.interop.native_capacitance_case import (
    NativeCapacitanceCaseBlocked, SCHEMA, build_native_capacitance_case_readiness,
    serialize_native_capacitance_case_readiness,
)

_spec = importlib.util.spec_from_file_location(
    'a11_m3_case_fixture', Path(__file__).with_name('test_capacitance_review_dossier.py'))
_m3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m3)


def case(tmp_path, mesh=_m3._m1.MESH_V2):
    store, folder, args = _m3.provenance(tmp_path, mesh)
    return store, folder, args


def build(store, args):
    return build_native_capacitance_case_readiness(store, **args)


@pytest.mark.parametrize('mesh', [_m3._m1.MESH_V2, _m3._m1.MESH_V4],
                         ids=['synthetic-gmsh-v2', 'synthetic-gmsh-v4'])
def test_hash_bound_b04_record_is_screened_but_permanently_blocked(tmp_path, mesh):
    store, folder, args = case(tmp_path, mesh)
    r = build(store, args)
    assert r['schema'] == SCHEMA and r['case_id'] == 'B04'
    assert r['scientific_status'] == r['decision'] == 'BLOCKED'
    assert r['fabrication'] == 'HOLD' and r['ec_to_scqubits'] == 'BLOCKED'
    assert r['native_execution'] == 'ARTIFACT_RECORD_ONLY_NOT_ATTESTED'
    assert r['capacitance']['finite_spd_check'] == 'PASSED_NUMERICAL_SCREEN_ONLY'
    assert r['capacitance']['header_unit'] == 'fF'
    assert r['capacitance']['normalized_unit'] == 'F'
    assert r['capacitance']['terminal_count'] == 2
    assert r['capacitance']['matrix_embedded'] is False
    assert r['terminals'][0]['component'] == 'LP1'
    assert r['terminals'][0]['native_group_ids'] == [9]
    assert r['terminals'][1]['component'] == 'LP2'
    assert r['terminals'][1]['native_group_ids'] == [10]
    assert r['ground']['native_group_ids'] == [3, 4]
    assert not r['ground']['in_maxwell_matrix']
    assert r['geometry']['cad_to_mesh_registration'].startswith('BLOCKED')
    assert len(r['software_checks']) == 7
    assert all(c['status'] == 'SCREENED_RECORD_ONLY' for c in r['software_checks'])
    assert len(r['missing_physical_evidence']) == 8
    assert all(c['status'] == 'MISSING_INDEPENDENT_EVIDENCE'
               for c in r['missing_physical_evidence'])
    assert r['review']['status'] == 'NOT_APPROVED'
    assert r['review']['signatures'] == []
    assert 'CALLER_SUPPLIED' in r['review']['saved_selection']
    for key, name in [('terminal_csv', 'sqe_em/outputFiles/terminal-C.csv'),
                      ('palace_deck', 'sqe_em/sqe_em.json'),
                      ('gmsh_mesh', 'sqe_em/sqe_em.msh'),
                      ('native_log', 'sqe_em/palace-native.log'),
                      ('native_sidecar', 'a03-native-artifacts.json')]:
        content = (folder / name).read_bytes()
        assert r['source']['artifacts'][key] == {
            'sha256': sha256(content).hexdigest(), 'bytes': len(content)}
    assert r['source']['manifest_sha256'] == sha256(
        (folder / 'RESULT_MANIFEST.json').read_bytes()).hexdigest()
    raw = serialize_native_capacitance_case_readiness(r)
    assert raw == serialize_native_capacitance_case_readiness(build(store, args))
    assert raw.endswith(b'\n') and len(raw) <= 65536 and json.loads(raw) == r
    assert str(store.root).encode() not in raw
    assert b'conditional_EC_over_h_GHz' not in raw
    assert b'mock mesh' not in raw


@pytest.mark.parametrize('fault', [
    'non_store', 'unknown_owner', 'unknown_run', 'stale_revision',
    'run_not_completed', 'unapproved_engine_mode', 'wrong_manifest_kind',
    'stale_selection', 'alias_terminal', 'missing_ground', 'swapped_terminal',
    'duplicate_terminal', 'duplicate_terminal_ground', 'missing_terminal_group',
    'non_finite_csv', 'non_spd_csv', 'bad_csv_unit', 'modified_csv',
    'modified_mesh', 'modified_deck', 'modified_log', 'missing_mesh',
    'modified_sidecar', 'fake_exit_failure', 'outside_store',
    'escaped_dotdot_run_path', 'linked_terminal_csv', 'linked_mesh_parent',
    'linked_output_parent',
])
def test_fail_closed_invalid_source_and_unapproved_modes(tmp_path, fault):
    store, folder, args = case(tmp_path)
    deck_name = 'sqe_em/sqe_em.json'
    csv_name = 'sqe_em/outputFiles/terminal-C.csv'
    mesh_name = 'sqe_em/sqe_em.msh'
    if fault == 'non_store':
        store = {'forged_hash': '0' * 64}
    elif fault == 'unknown_owner':
        args['owner'] = 'other'
    elif fault == 'unknown_run':
        args['run_id'] = 'nonexistent'
    elif fault == 'stale_revision':
        project = store.project(args['owner'], args['project_id'])
        store.commit(args['owner'], args['project_id'], project['head'], project['model'])
    elif fault == 'run_not_completed':
        store.set_run(args['run_id'], 'queued')
    elif fault == 'unapproved_engine_mode':
        with store.conn() as db:
            db.execute('UPDATE runs SET engine=? WHERE id=?', ('scqubits', args['run_id']))
    elif fault == 'wrong_manifest_kind':
        p = folder / 'RESULT_MANIFEST.json'
        obj = json.loads(p.read_text())
        obj['kind'] = 'eigenmode'
        p.write_text(json.dumps(obj))
    elif fault == 'stale_selection':
        args['saved_selection']['revision_id'] = 'not-the-head'
    elif fault == 'alias_terminal':
        args['saved_selection']['island_b'] = 'LP2'
    elif fault in ('missing_ground', 'swapped_terminal', 'duplicate_terminal_ground',
                   'duplicate_terminal'):
        p = folder / deck_name
        deck = json.loads(p.read_text())
        if fault == 'missing_ground':
            deck['Boundaries']['Ground']['Attributes'] = []
        elif fault == 'swapped_terminal':
            deck['Boundaries']['Terminal'].reverse()
        elif fault == 'duplicate_terminal':
            deck['Boundaries']['Terminal'][1]['Attributes'] = [9]
        else:
            deck['Boundaries']['Ground']['Attributes'] = [3, 9]
        p.write_text(json.dumps(deck))
        _m3.rehash(folder, deck_name)  # even rehashed tampering must fail
    elif fault == 'missing_terminal_group':
        p = folder / mesh_name
        p.write_text(_m3._m1.MESH_V2.replace('3 2 2 9 103', '3 2 2 99 103'))
        _m3.rehash(folder, mesh_name)
    elif fault in ('non_finite_csv', 'non_spd_csv', 'bad_csv_unit'):
        p = folder / csv_name
        body = {
            'non_finite_csv': 'Terminal,C1 (fF),C2 (fF)\n1,NaN,-50\n2,-50,160\n',
            'non_spd_csv': 'Terminal,C1 (fF),C2 (fF)\n1,100,-110\n2,-110,100\n',
            'bad_csv_unit': 'Terminal,C1 (pF),C2 (pF)\n1,150,-50\n2,-50,160\n',
        }[fault]
        p.write_text(body)
        _m3.rehash(folder, csv_name)
    elif fault.startswith('modified_'):
        name = {'modified_csv': csv_name, 'modified_mesh': mesh_name,
                'modified_deck': deck_name, 'modified_log': 'sqe_em/palace-native.log',
                'modified_sidecar': 'a03-native-artifacts.json'}[fault]
        p = folder / name
        p.write_bytes(p.read_bytes() + b'\ntampered')  # manifest unmodified
    elif fault == 'missing_mesh':
        (folder / mesh_name).unlink()
    elif fault == 'fake_exit_failure':
        p = folder / 'a03-native-artifacts.json'
        sidecar = json.loads(p.read_text())
        sidecar['native_completion']['exit_code'] = 1
        p.write_text(json.dumps(sidecar))
        _m3.rehash(folder, 'a03-native-artifacts.json')
    elif fault in ('outside_store', 'escaped_dotdot_run_path'):
        original = str(folder.parent)
        path = (str(tmp_path / 'other-run') if fault == 'outside_store'
                else original.replace('/output', '') + '/../../other-run')
        with store.conn() as db:
            db.execute('UPDATE runs SET path=? WHERE id=?', (path, args['run_id']))
    elif fault in ('linked_terminal_csv', 'linked_mesh_parent', 'linked_output_parent'):
        if fault == 'linked_terminal_csv':
            link = folder / csv_name
        elif fault == 'linked_mesh_parent':
            link = folder / 'sqe_em'
        else:
            link = folder
        destination = link.with_name(link.name + '-real')
        link.rename(destination)
        try:
            link.symlink_to(destination, target_is_directory=destination.is_dir())
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                pytest.skip('Windows symlink privilege unavailable for actual negative fixture')
            raise
    with pytest.raises(NativeCapacitanceCaseBlocked):
        build(store, args)


def test_manually_rehashed_fake_solver_claim_cannot_become_b04_approval(tmp_path):
    store, folder, args = case(tmp_path)
    name = 'a03-native-artifacts.json'
    path = folder / name
    sidecar = json.loads(path.read_text())
    sidecar['claimed_expert_signature'] = 'not-a-verifiable-credential'
    sidecar['native_completion']['exit_code'] = 0
    path.write_text(json.dumps(sidecar))
    _m3.rehash(folder, name)
    r = build(store, args)
    assert r['decision'] == 'BLOCKED' and r['native_execution'].endswith('NOT_ATTESTED')
    assert all(c['status'] == 'MISSING_INDEPENDENT_EVIDENCE'
               for c in r['missing_physical_evidence'])
    assert r['review']['signatures'] == []


@pytest.mark.parametrize('path', ['decision', 'native_execution', 'fabrication',
                                  'ec_to_scqubits', 'scientific_status',
                                  'software_checks', 'missing_physical_evidence', 'review'])
def test_serializer_refuses_forged_approval_or_missing_review(tmp_path, path):
    store, _, args = case(tmp_path)
    r = copy.deepcopy(build(store, args))
    if path == 'decision':
        r[path] = 'PASS'
    elif path == 'native_execution':
        r[path] = 'NATIVE_B04_EXECUTED'
    elif path == 'fabrication':
        r[path] = 'RELEASE'
    elif path == 'ec_to_scqubits':
        r[path] = 'APPROVED'
    elif path == 'scientific_status':
        r[path] = 'APPROVED'
    elif path == 'software_checks':
        r[path][0]['status'] = 'SCIENTIFICALLY_APPROVED'
    elif path == 'missing_physical_evidence':
        r[path][0]['status'] = 'PRESENT'
    elif path == 'review':
        r[path]['signatures'] = ['fake reviewer']
    with pytest.raises(NativeCapacitanceCaseBlocked):
        serialize_native_capacitance_case_readiness(r)


def test_simulated_windows_junction_is_fail_closed_not_a_windows_native_test(tmp_path, monkeypatch):
    store, folder, args = case(tmp_path)
    # Linux cannot create NTFS junctions. This checks the Windows is_junction
    # branch only, not actual NTFS behavior or native execution.
    # Path.is_junction is unavailable on Python 3.11, our supported Windows
    # runtime. Simulate its absence even on newer Pythons before installing the
    # test-only junction probe; production uses getattr() for this API.
    original = getattr(Path, 'is_junction', None)
    if original is not None:
        monkeypatch.delattr(Path, 'is_junction')
    monkeypatch.setattr(
        Path, 'is_junction',
        lambda p: p == folder / 'sqe_em' or (original(p) if original else False),
        raising=False,
    )
    with pytest.raises(NativeCapacitanceCaseBlocked, match='junction'):
        build(store, args)


def test_serializer_does_not_accept_non_finite_or_excessive_raw_data(tmp_path):
    store, _, args = case(tmp_path)
    r = build(store, args)
    with pytest.raises(NativeCapacitanceCaseBlocked):
        serialize_native_capacitance_case_readiness(dict(r, extra=float('nan')))
    with pytest.raises(NativeCapacitanceCaseBlocked):
        serialize_native_capacitance_case_readiness(dict(r, b04_approved=True))
    with pytest.raises(NativeCapacitanceCaseBlocked):
        serialize_native_capacitance_case_readiness(dict(r, extra='private' * 20000))
