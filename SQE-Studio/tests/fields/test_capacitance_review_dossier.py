"""M3 Store-backed dossier tests; all Palace/mesh/CSV records are constructed fixtures."""
from __future__ import annotations

import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import shutil

import pytest

from sqe_studio.interop.capacitance_review_dossier import (
    CapacitanceReviewBlocked, SCHEMA, build_native_capacitance_review_dossier,
    serialize_capacitance_review_dossier,
)
from sqe_studio.store import Store

_spec = importlib.util.spec_from_file_location('a11_m1_fixture',
    Path(__file__).with_name('test_capacitance_topology.py'))
_m1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m1)


def provenance(tmp_path, mesh=_m1.MESH_V2):
    source, _, project, selection = _m1.setup(tmp_path, mesh)
    store = Store(tmp_path / 'store')
    owner = 'fixture-owner'
    created = store.create(owner, 'M3 test only', project['model']['family'], project['model'])
    pid, rid = created['id'], created['head']
    run_folder = store.root / 'runs' / 'fixture-run'
    folder = run_folder / 'output'
    shutil.copytree(source, folder)
    mf_path = folder / 'RESULT_MANIFEST.json'
    manifest = json.loads(mf_path.read_text())
    manifest['revision_id'] = rid
    manifest['provenance']['used_revision'] = rid
    mf_path.write_text(json.dumps(manifest))
    selection['revision_id'] = rid
    run_id = store.put_run(owner, pid, rid, manifest['study_id'], 'sqdmetal_palace', run_folder)
    store.set_run(run_id, 'completed')
    args = {'owner': owner, 'project_id': pid, 'run_id': run_id,
            'saved_selection': selection}
    return store, folder, args


def rehash(folder, file):
    mpath = folder / 'RESULT_MANIFEST.json'
    manifest = json.loads(mpath.read_text())
    item = next(a for a in manifest['artifacts'] if a['name'] == file)
    content = (folder / file).read_bytes()
    item.update(bytes=len(content), sha256=sha256(content).hexdigest())
    mpath.write_text(json.dumps(manifest))


def build(store, args):
    return build_native_capacitance_review_dossier(store, **args)


@pytest.mark.parametrize('mesh', [_m1.MESH_V2, _m1.MESH_V4], ids=['Gmsh-v2', 'Gmsh-v4'])
def test_dossier_complete_deterministic_and_unapproved(tmp_path, mesh):
    store, folder, args = provenance(tmp_path, mesh)
    dossier = build(store, args)
    assert dossier['schema'] == SCHEMA
    assert dossier['scientific_status'] == 'BLOCKED'
    assert dossier['fabrication'] == 'HOLD'
    assert dossier['em_to_scqubits_transfer'] == 'BLOCKED'
    assert dossier['b04_native_review'].startswith('BLOCKED')
    assert dossier['review']['status'] == 'NOT_APPROVED'
    assert dossier['review']['signatures'] == []
    assert len(dossier['review']['checklist']) == 10
    assert all(c['status'] == 'PENDING_INDEPENDENT_REVIEW' for c in dossier['review']['checklist'])
    assert dossier['source']['revision_id'] == store.project(args['owner'], args['project_id'])['revision']
    assert dossier['source']['manifest_sha256'] == sha256((folder / 'RESULT_MANIFEST.json').read_bytes()).hexdigest()
    assert dossier['source']['artifacts']['terminal_csv']['sha256'] == sha256(
        (folder / 'sqe_em/outputFiles/terminal-C.csv').read_bytes()).hexdigest()
    assert set(dossier['source']['artifacts']) == {
        'terminal_csv', 'palace_deck', 'gmsh_mesh', 'native_log', 'native_sidecar'}
    assert dossier['capacitance']['native_csv_unit'] == 'fF'
    assert dossier['capacitance']['matrix_entry_unit'] == 'F'
    assert dossier['capacitance']['terminal_count'] == 2
    assert dossier['terminals'] == [
        {'terminal_index': 1, 'component': 'LP1', 'native_group_ids': [9],
         'proposed_role': 'proposed_island_b'},
        {'terminal_index': 2, 'component': 'LP2', 'native_group_ids': [10],
         'proposed_role': 'proposed_island_a'}]
    assert dossier['ground']['native_group_ids'] == [3, 4]
    assert dossier['ground']['in_maxwell_matrix'] is False
    assert dossier['geometry']['cad_to_mesh_registration'].startswith('BLOCKED')
    assert dossier['selection']['persistence'].startswith('CALLER_SUPPLIED')
    raw = serialize_capacitance_review_dossier(dossier)
    assert raw == serialize_capacitance_review_dossier(build(store, args))
    assert raw.endswith(b'\n') and len(raw) < 65536
    assert json.loads(raw) == dossier
    assert b'mock mesh' not in raw and b'fixture log' not in raw
    assert str(store.root).encode() not in raw  # no private absolute path
    assert 'EC' not in dossier['capacitance']
    assert 'approval' not in dossier['review']


@pytest.mark.parametrize('fault', [
    'not_store', 'unowned', 'unknown_run', 'not_completed', 'wrong_engine',
    'stale_head', 'stale_selection', 'aliased_islands', 'alias_policy',
    'tampered_csv', 'tampered_mesh', 'tampered_deck', 'tampered_sidecar',
    'deleted_deck', 'deleted_mesh', 'missing_manifest', 'bad_csv_unit',
    'swapped_deck_indices', 'duplicate_ground_terminal', 'non_spd_matrix',
    'invalid_mesh_group', 'wrong_manifest_study', 'bad_native_completion',
    'linked_output', 'outside_store',
])
def test_fail_closed_store_provenance_and_negative_artifacts(tmp_path, fault):
    store, folder, args = provenance(tmp_path)
    if fault == 'not_store':
        store = {'manifest_sha256': sha256((folder / 'RESULT_MANIFEST.json').read_bytes()).hexdigest()}
    elif fault == 'unowned':
        args['owner'] = 'forged-other-owner'
    elif fault == 'unknown_run':
        args['run_id'] = 'forged-other-run'
    elif fault == 'not_completed':
        store.set_run(args['run_id'], 'queued')
    elif fault == 'wrong_engine':
        with store.conn() as db:
            db.execute('UPDATE runs SET engine=? WHERE id=?', ('scqubits', args['run_id']))
    elif fault == 'stale_head':
        snap = store.project(args['owner'], args['project_id'])
        store.commit(args['owner'], args['project_id'], snap['head'], snap['model'])
    elif fault == 'stale_selection':
        args['saved_selection']['revision_digest'] = '0' * 64
    elif fault == 'aliased_islands':
        args['saved_selection']['island_b'] = args['saved_selection']['island_a']
    elif fault == 'alias_policy':
        args['saved_selection']['other_terminal_policy']['fixed_zero'] = ['LP1']
    elif fault.startswith('tampered_'):
        file = {'tampered_csv': 'sqe_em/outputFiles/terminal-C.csv',
                'tampered_mesh': 'sqe_em/sqe_em.msh',
                'tampered_deck': 'sqe_em/sqe_em.json',
                'tampered_sidecar': 'a03-native-artifacts.json'}[fault]
        (folder / file).write_bytes((folder / file).read_bytes() + b'bad')
    elif fault in ('deleted_deck', 'deleted_mesh'):
        (folder / ('sqe_em/sqe_em.json' if fault == 'deleted_deck' else 'sqe_em/sqe_em.msh')).unlink()
    elif fault == 'missing_manifest':
        (folder / 'RESULT_MANIFEST.json').unlink()
    elif fault == 'bad_csv_unit':
        name = 'sqe_em/outputFiles/terminal-C.csv'
        (folder / name).write_text('Terminal,C1 (pF),C2 (pF)\n1,150,-50\n2,-50,160\n')
        rehash(folder, name)
    elif fault in ('swapped_deck_indices', 'duplicate_ground_terminal'):
        name = 'sqe_em/sqe_em.json'
        deck = json.loads((folder / name).read_text())
        if fault == 'swapped_deck_indices':
            deck['Boundaries']['Terminal'].reverse()
        else:
            deck['Boundaries']['Ground']['Attributes'] = [3, 9]
        (folder / name).write_text(json.dumps(deck))
        rehash(folder, name)
    elif fault == 'non_spd_matrix':
        name = 'sqe_em/outputFiles/terminal-C.csv'
        (folder / name).write_text('Terminal,C1 (fF),C2 (fF)\n1,100,-110\n2,-110,100\n')
        rehash(folder, name)
    elif fault == 'invalid_mesh_group':
        name = 'sqe_em/sqe_em.msh'
        (folder / name).write_text(_m1.MESH_V2.replace('3 2 2 9 103', '3 2 2 99 103'))
        rehash(folder, name)
    elif fault == 'wrong_manifest_study':
        m = folder / 'RESULT_MANIFEST.json'
        blob = json.loads(m.read_text())
        blob['study_id'] = 'false-study'
        m.write_text(json.dumps(blob))
    elif fault == 'bad_native_completion':
        name = 'a03-native-artifacts.json'
        blob = json.loads((folder / name).read_text())
        blob['native_completion']['exit_code'] = 1
        (folder / name).write_text(json.dumps(blob))
        rehash(folder, name)
    elif fault == 'linked_output':
        dest = folder.parent / 'real-output'
        folder.rename(dest)
        try:
            folder.symlink_to(dest, target_is_directory=True)
        except OSError as exc:
            # Windows without Developer Mode/SeCreateSymbolicLinkPrivilege
            # cannot create this adversarial fixture. Never convert this
            # permission denial into a successful symlink rejection assertion.
            if getattr(exc, 'winerror', None) == 1314:
                pytest.skip('Windows symlink privilege unavailable for negative fixture')
            raise
    elif fault == 'outside_store':
        with store.conn() as db:
            db.execute('UPDATE runs SET path=? WHERE id=?',
                       (str(tmp_path / 'native'), args['run_id']))
    with pytest.raises(CapacitanceReviewBlocked):
        build(store, args)


def test_linked_output_unavailable_privilege_is_not_security_pass(tmp_path, monkeypatch):
    """The Windows fixture can be unavailable; never report a false PASS.

    The actual negative test still runs when symlink creation is permitted.
    This test simulates only WinError 1314 so it runs on non-Windows CI.
    """
    original = Path.symlink_to

    def deny_only_test_link(self, target, target_is_directory=False):
        if self.name == 'output':
            exc = OSError('fixture privilege denied')
            exc.winerror = 1314
            raise exc
        return original(self, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, 'symlink_to', deny_only_test_link)
    with pytest.raises(pytest.skip.Exception, match='symlink privilege unavailable'):
        test_fail_closed_store_provenance_and_negative_artifacts(tmp_path, 'linked_output')


def test_linked_output_unexpected_error_is_not_ignored(tmp_path, monkeypatch):
    original = Path.symlink_to

    def fail_unexpected(self, target, target_is_directory=False):
        if self.name == 'output':
            raise OSError('unexpected I/O failure')
        return original(self, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, 'symlink_to', fail_unexpected)
    with pytest.raises(OSError, match='unexpected I/O failure'):
        test_fail_closed_store_provenance_and_negative_artifacts(tmp_path, 'linked_output')


def test_serializer_never_promotes_a_synthetic_approval(tmp_path):
    store, _, args = provenance(tmp_path)
    dossier = build(store, args)
    for field, invalid in [
        ('scientific_status', 'APPROVED'), ('fabrication', 'RELEASED'),
        ('em_to_scqubits_transfer', 'AUTHORIZED')]:
        copy = dict(dossier, **{field: invalid})
        with pytest.raises(CapacitanceReviewBlocked):
            serialize_capacitance_review_dossier(copy)
    changed = dict(dossier, review={'status': 'APPROVED', 'signatures': ['invented']})
    with pytest.raises(CapacitanceReviewBlocked):
        serialize_capacitance_review_dossier(changed)
    for field, invalid in [('b04_native_review', 'PASS'),
                           ('native_solver_execution', 'ATTESTED')]:
        with pytest.raises(CapacitanceReviewBlocked):
            serialize_capacitance_review_dossier(dict(dossier, **{field: invalid}))
    changed = dict(dossier, geometry=dict(dossier['geometry'],
                   cad_to_mesh_registration='APPROVED'))
    with pytest.raises(CapacitanceReviewBlocked):
        serialize_capacitance_review_dossier(changed)
    changed = dict(dossier, review=dict(dossier['review'], signatures=['invented']))
    with pytest.raises(CapacitanceReviewBlocked):
        serialize_capacitance_review_dossier(changed)
    changed = dict(dossier, physical_limits=['x'*70000])
    with pytest.raises(CapacitanceReviewBlocked):
        serialize_capacitance_review_dossier(changed)
