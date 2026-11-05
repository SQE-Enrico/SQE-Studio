"""Constructed Gmsh/Palace fixtures ONLY; no native mesh/solve or expert signoff."""
from __future__ import annotations

import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

from sqe_studio.contracts import digest
from sqe_studio.interop.capacitance_topology import (
    CapacitanceTopologyBlocked, build_native_capacitance_topology,
    inspect_native_capacitance_mapping,
)

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / 'extraction' / 'test_capacitance_science.py'
_spec = importlib.util.spec_from_file_location('_a11_fixture_helper', _FIXTURE_PATH)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


MESH_V2 = '''$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
5
1 0 0 0
2 1 0 0
3 0 1 0
4 0 0 1
5 0 0 -1
$EndNodes
$Elements
6
1 2 2 3 101 1 2 4
2 2 2 4 102 2 3 4
3 2 2 9 103 1 3 4
4 2 2 10 104 1 2 3
5 4 2 1 201 1 2 3 4
6 4 2 2 202 1 3 2 5
$EndElements
'''

MESH_V4 = '''$MeshFormat
4.1 0 8
$EndMeshFormat
$Entities
0 0 4 2
1 0 0 0 1 1 1 1 3 0
2 0 0 0 1 1 1 1 4 0
3 0 0 0 1 1 1 1 9 0
4 0 0 0 1 1 1 1 10 0
1 0 0 0 1 1 1 1 1 0
2 0 0 -1 1 1 0 1 2 0
$EndEntities
$Nodes
1 5 1 5
3 1 0 5
1
2
3
4
5
0 0 0
1 0 0
0 1 0
0 0 1
0 0 -1
$EndNodes
$Elements
6 6 1 6
2 1 2 1
1 1 2 4
2 2 2 1
2 2 3 4
2 3 2 1
3 1 3 4
2 4 2 1
4 1 2 3
3 1 4 1
5 1 2 3 4
3 2 4 1
6 1 3 2 5
$EndElements
'''


def rehash(folder, name):
    data = json.loads((folder/'RESULT_MANIFEST.json').read_text(encoding='utf-8'))
    item = next(a for a in data['artifacts'] if a['name'] == name)
    data_bytes = (folder/name).read_bytes()
    item.update(sha256=sha256(data_bytes).hexdigest(), bytes=len(data_bytes))
    (folder/'RESULT_MANIFEST.json').write_text(json.dumps(data), encoding='utf-8')
    return data


def setup(tmp_path, mesh=MESH_V2):
    model, folder, _ = _fixture._capacitance_fixture(tmp_path)
    study = model['studies'][0]
    stack = model['process']['stack']
    deck_path = folder/'sqe_em/sqe_em.json'
    deck = json.loads(deck_path.read_text(encoding='utf-8'))
    deck.update({
        'Problem': {'Type': 'Electrostatic', 'Output': 'outputFiles'},
        'Model': {'Mesh': 'sqe_em.msh', 'L0': 1e-3},
        'Solver': {'Order': study['inputs']['em']['solver']['order']},
        'Domains': {'Materials': [
            {'Attributes': [1], 'Permittivity': stack[2]['relative_permittivity'],
             'LossTan': stack[2]['loss_tangent']},
            {'Attributes': [2], 'Permittivity': stack[0]['relative_permittivity'],
             'LossTan': stack[0]['loss_tangent']}]},
    })
    deck_path.write_text(json.dumps(deck), encoding='utf-8')
    (folder/'sqe_em/sqe_em.msh').write_text(mesh, encoding='utf-8')
    rehash(folder, 'sqe_em/sqe_em.json')
    manifest = rehash(folder, 'sqe_em/sqe_em.msh')
    project = {'revision': manifest['revision_id'], 'revision_digest': digest(model), 'model': model}
    selection = {'revision_id': project['revision'], 'revision_digest': project['revision_digest'],
                 'study_id': study['id'], 'island_a': 'LP2', 'island_b': 'LP1',
                 'other_terminal_policy': {'fixed_zero': [], 'floating_zero_charge': []}}
    return folder, manifest, project, selection


@pytest.mark.parametrize('mesh', [MESH_V2, MESH_V4], ids=['gmsh-2.2-ascii', 'gmsh-4.1-ascii'])
def test_exact_native_manifest_mesh_deck_terminal_csv_and_explicit_pair(tmp_path, mesh):
    folder, manifest, project, selection = setup(tmp_path, mesh)
    data = build_native_capacitance_topology(folder, manifest, project, saved_selection=selection)
    assert set(data) == {'schema', 'scientific_status', 'source', 'terminal_labels',
                         'maxwell_matrix_f', 'reference_ground', 'proposed_pair',
                         'other_terminal_policy', 'review'}
    assert data['schema'] == 'sqe.capacitance-topology.v1'
    assert data['scientific_status'] == 'UNREVIEWED_TOPOLOGY'
    assert data['reference_ground'] == {'status': 'UNREVIEWED', 'native_group_ids': [3, 4]}
    assert data['proposed_pair'] == {'island_a': 'LP2', 'island_b': 'LP1'}
    assert data['terminal_labels'] == ['LP1', 'LP2']  # CSV order, NOT chosen pair order
    assert data['maxwell_matrix_f'][0] == pytest.approx([150e-15, -50e-15])
    assert data['review'] == {'status': 'NOT_APPROVED', 'record_sha256': None}
    for name, key in [('sqe_em/outputFiles/terminal-C.csv', 'terminal_csv_sha256'),
                      ('sqe_em/sqe_em.json', 'deck_sha256'),
                      ('sqe_em/sqe_em.msh', 'mesh_sha256')]:
        assert data['source'][key] == sha256((folder/name).read_bytes()).hexdigest()
    assert data['source']['manifest_sha256'] == sha256((folder/'RESULT_MANIFEST.json').read_bytes()).hexdigest()
    assert 'EC' not in data and 'scqubits' not in data
    mapping = inspect_native_capacitance_mapping(folder, manifest, project,
                                                 saved_selection=selection)
    assert mapping['ordered_conductors'] == [
        {'terminal_index': 1, 'component': 'LP1', 'native_group_ids': [9]},
        {'terminal_index': 2, 'component': 'LP2', 'native_group_ids': [10]}]
    assert mapping['reference_ground_group_ids'] == [3, 4]
    assert mapping['geometry_registration'].startswith('BLOCKED')
    assert mapping['fabrication'] == 'HOLD'


@pytest.mark.parametrize('mutation', [
    'missing_selection', 'unknown_island', 'duplicate_islands', 'stale_selection',
    'unknown_other_node', 'conflicting_policy', 'unclassified_extra',
    'stale_revision', 'wrong_project_digest', 'wrong_manifest_argument',
    'tamper_csv', 'tamper_mesh', 'tamper_deck', 'tamper_log',
    'swapped_terminal_indices', 'duplicate_terminal_tags', 'duplicate_ground_terminal',
    'wrong_ground_group', 'no_mesh_ground_group', 'wrong_native_deck_order',
    'wrong_mesh_units', 'wrong_material', 'wrong_volume', 'missing_native_deck',
    'missing_native_mesh', 'invalid_native_physical_entity', 'non_spd_matrix',
    'unreviewed_process', 'unverified_saved_ground', 'wrong_farfield',
    'bad_port_convention', 'bad_native_exit', 'binary_mesh', 'degenerate_mesh',
])
def test_negative_provenance_and_topology(tmp_path, mutation):
    folder, manifest, project, selection = setup(tmp_path)
    deckname = 'sqe_em/sqe_em.json'
    deck = json.loads((folder/deckname).read_text(encoding='utf-8'))
    if mutation == 'missing_selection':
        selection = {}
    elif mutation == 'unknown_island':
        selection['island_a'] = 'fake_electrode'
    elif mutation == 'duplicate_islands':
        selection['island_a'] = 'LP1'
    elif mutation == 'stale_selection':
        selection['revision_digest'] = 'a'*64
    elif mutation == 'unknown_other_node':
        selection['other_terminal_policy']['fixed_zero'] = ['unknown']
    elif mutation == 'conflicting_policy':
        selection['other_terminal_policy']['fixed_zero'] = ['LP2']
    elif mutation == 'unclassified_extra':
        selection['other_terminal_policy']['fixed_zero'] = ['LP1']
    elif mutation == 'stale_revision':
        project['revision'] = 'd'*32
    elif mutation == 'wrong_project_digest':
        project['revision_digest'] = 'e'*64
    elif mutation == 'wrong_manifest_argument':
        manifest = dict(manifest, engine_version='forge')
    elif mutation.startswith('tamper_'):
        name = {'tamper_csv':'sqe_em/outputFiles/terminal-C.csv',
                'tamper_mesh':'sqe_em/sqe_em.msh',
                'tamper_deck':deckname,
                'tamper_log':'sqe_em/palace-native.log'}[mutation]
        (folder/name).write_bytes((folder/name).read_bytes()+b'\nchanged')
    elif mutation == 'swapped_terminal_indices':
        deck['Boundaries']['Terminal'].reverse()
    elif mutation == 'duplicate_terminal_tags':
        deck['Boundaries']['Terminal'][1]['Attributes'] = [9]
    elif mutation == 'duplicate_ground_terminal':
        deck['Boundaries']['Ground']['Attributes'] = [3, 9]
    elif mutation == 'wrong_ground_group':
        deck['Boundaries']['Ground']['Attributes'] = [99]
    elif mutation == 'no_mesh_ground_group':
        (folder/'sqe_em/sqe_em.msh').write_text(MESH_V2.replace('2 2 2 4 102', '2 2 2 99 102'))
        manifest = rehash(folder, 'sqe_em/sqe_em.msh')
    elif mutation == 'wrong_native_deck_order':
        deck['Boundaries']['Terminal'][0]['Index'] = 2
    elif mutation == 'wrong_mesh_units':
        deck['Model']['L0'] = 1.0
    elif mutation == 'wrong_material':
        deck['Domains']['Materials'][0]['Permittivity'] = 88
    elif mutation == 'wrong_volume':
        deck['Domains']['Materials'][1]['Attributes'] = [3]
    elif mutation == 'missing_native_deck':
        (folder/deckname).unlink()
    elif mutation == 'missing_native_mesh':
        (folder/'sqe_em/sqe_em.msh').unlink()
    elif mutation == 'invalid_native_physical_entity':
        (folder/'sqe_em/sqe_em.msh').write_text(MESH_V2.replace('3 2 2 9 103', '3 2 2 99 103'))
        manifest = rehash(folder,'sqe_em/sqe_em.msh')
    elif mutation == 'non_spd_matrix':
        path = folder/'sqe_em/outputFiles/terminal-C.csv'
        path.write_text('Terminal,C1 (fF),C2 (fF)\n1,100,-110\n2,-110,100\n')
        manifest = rehash(folder, 'sqe_em/outputFiles/terminal-C.csv')
    elif mutation == 'unreviewed_process':
        project['model']['process']['source'] = 'unverified'
    elif mutation == 'unverified_saved_ground':
        project['model']['studies'][0]['inputs']['em']['ground']['verified'] = False
    elif mutation == 'wrong_farfield':
        project['model']['studies'][0]['inputs']['em']['boundaries']['farfield'] = 'pec'
    elif mutation == 'bad_port_convention':
        name = 'a03-native-artifacts.json'
        data = json.loads((folder/name).read_text())
        data['port_convention']['ports'].reverse()
        (folder/name).write_text(json.dumps(data))
        manifest = rehash(folder, name)
    elif mutation == 'bad_native_exit':
        name = 'a03-native-artifacts.json'
        data = json.loads((folder/name).read_text())
        data['native_completion']['exit_code'] = 1
        (folder/name).write_text(json.dumps(data))
        manifest = rehash(folder, name)
    elif mutation == 'binary_mesh':
        (folder/'sqe_em/sqe_em.msh').write_bytes(MESH_V2.encode()+b'\x00')
        manifest = rehash(folder,'sqe_em/sqe_em.msh')
    elif mutation == 'degenerate_mesh':
        (folder/'sqe_em/sqe_em.msh').write_text(MESH_V2.replace('4 0 0 1','4 0 0 0'))
        manifest = rehash(folder,'sqe_em/sqe_em.msh')
    if mutation in {'swapped_terminal_indices', 'duplicate_terminal_tags',
                    'duplicate_ground_terminal', 'wrong_ground_group',
                    'wrong_native_deck_order', 'wrong_mesh_units', 'wrong_material',
                    'wrong_volume'}:
        (folder/deckname).write_text(json.dumps(deck), encoding='utf-8')
        manifest = rehash(folder, deckname)
    with pytest.raises(CapacitanceTopologyBlocked):
        build_native_capacitance_topology(folder, manifest, project, saved_selection=selection)


def test_floating_and_fixed_zero_must_exhaust_three_terminals(tmp_path):
    folder, manifest, project, selection = setup(tmp_path)
    # A third verified terminal would require matching genuine native CSV,
    # deck, sidecar, saved em and Gmsh; inventing only an entry is blocked.
    selection['other_terminal_policy'] = {'fixed_zero': ['LP1'], 'floating_zero_charge': []}
    with pytest.raises(CapacitanceTopologyBlocked):
        build_native_capacitance_topology(folder, manifest, project, saved_selection=selection)


def test_three_terminal_fixed_vs_floating_classification_without_reduction(tmp_path):
    folder, manifest, project, selection = setup(tmp_path)
    model = project['model']
    ports = model['studies'][0]['inputs']['em']['ports']
    ports.append({'index': 3, 'kind': 'conductor', 'component': 'OTG',
                  'native_attributes': [11]})
    sidecar_name = 'a03-native-artifacts.json'
    sidecar = json.loads((folder/sidecar_name).read_text())
    sidecar['port_convention']['ports'] = ports
    (folder/sidecar_name).write_text(json.dumps(sidecar))
    rehash(folder, sidecar_name)
    deck_name = 'sqe_em/sqe_em.json'
    deck = json.loads((folder/deck_name).read_text())
    deck['Boundaries']['Terminal'].append({'Index': 3, 'Attributes': [11]})
    (folder/deck_name).write_text(json.dumps(deck))
    rehash(folder, deck_name)
    mesh_name = 'sqe_em/sqe_em.msh'
    mesh = MESH_V2.replace('$Elements\n6\n', '$Elements\n7\n').replace(
        '6 4 2 2 202 1 3 2 5\n',
        '6 4 2 2 202 1 3 2 5\n7 2 2 11 105 1 2 5\n')
    (folder/mesh_name).write_text(mesh)
    rehash(folder, mesh_name)
    csv_name = 'sqe_em/outputFiles/terminal-C.csv'
    (folder/csv_name).write_text(
        'i,C[i][1] (fF),C[i][2] (fF),C[i][3] (fF)\n'
        '1,150,-50,-20\n2,-50,160,-30\n3,-20,-30,180\n')
    manifest = rehash(folder, csv_name)
    project['revision_digest'] = digest(model)
    selection['revision_digest'] = project['revision_digest']
    manifest['project_digest'] = project['revision_digest']
    manifest['provenance']['used_project_sha256'] = project['revision_digest']
    (folder/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
    selection['other_terminal_policy'] = {'fixed_zero': ['OTG'], 'floating_zero_charge': []}
    fixed = build_native_capacitance_topology(folder, manifest, project,
                                              saved_selection=selection)
    assert fixed['terminal_labels'] == ['LP1', 'LP2', 'OTG']
    assert fixed['other_terminal_policy']['fixed_zero'] == ['OTG']
    selection['other_terminal_policy'] = {'fixed_zero': [], 'floating_zero_charge': ['OTG']}
    floating = build_native_capacitance_topology(folder, manifest, project,
                                                 saved_selection=selection)
    assert floating['other_terminal_policy']['floating_zero_charge'] == ['OTG']
    assert fixed['maxwell_matrix_f'] == floating['maxwell_matrix_f']
    assert fixed['scientific_status'] == floating['scientific_status'] == 'UNREVIEWED_TOPOLOGY'
    selection['other_terminal_policy'] = {'fixed_zero': ['OTG'], 'floating_zero_charge': ['OTG']}
    with pytest.raises(CapacitanceTopologyBlocked):
        build_native_capacitance_topology(folder, manifest, project,
                                          saved_selection=selection)
    selection['other_terminal_policy'] = {'fixed_zero': [], 'floating_zero_charge': []}
    with pytest.raises(CapacitanceTopologyBlocked):
        build_native_capacitance_topology(folder, manifest, project,
                                          saved_selection=selection)
