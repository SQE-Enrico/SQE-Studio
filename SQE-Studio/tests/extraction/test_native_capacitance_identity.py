"""Constructed protocol tests; these polygons/mesh bytes are not native evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from shapely.geometry import box
from pathlib import Path

from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.sqdmetal_palace_adapter import preflight
from sqe_studio.interop.capacitance_identity import (
    IDENTITY_FILE, ORIGIN_FILE, bind_native_terminals, named_terminals,
    validate_named_terminals, verify_saved_identity,
)
from sqe_studio.transmon_design import single_transmon_model


def acknowledged_model():
    model = single_transmon_model('Protocol fixture only')
    model['process']['source'] = 'reviewed'  # Explicit fixture assumption.
    model['studies'][0]['inputs']['em']['ground']['verified'] = True
    return model


@pytest.fixture
def native_fixture(tmp_path):
    model = acknowledged_model()
    em = model['studies'][0]['inputs']['em']
    bottom, top = box(-.15, -.165, .15, -.015), box(-.15, .015, .15, .165)
    ground = box(-.6, -.6, .6, .6).difference(box(-.35, -.25, .35, .25))
    rows = [
        {'component': 17, 'name': name, 'layer': 1, 'subtract': False, 'geometry': shape}
        for name, shape in [('pad_bot', bottom), ('pad_top', top)]]
    frame = SimpleNamespace(iterrows=lambda: enumerate(rows))
    design = SimpleNamespace(components={'Q1': SimpleNamespace(id=17)},
                             qgeometry=SimpleNamespace(tables={'poly': frame}))
    def process_layers(metals, ground_options, **options):
        assert metals == [] and ground_options == {'omit': False}
        assert options['unit_conv'] == 1e-3
        return [ground], []
    sim = SimpleNamespace(_cur_cap_terminals=[ground, bottom, top],
        _geom_processor=SimpleNamespace(process_layers=process_layers),
        _ground_plane={'omit': False},
        user_options={'fuse_threshold': 1e-9, 'threshold': 1e-9,
                      'fillet_resolution': 12, 'simplify_edge_min_angle_deg': -1})
    names = {1: 'metal_0', 2: 'metal_1', 3: 'metal_2'}
    gmsh = SimpleNamespace(model=SimpleNamespace(getPhysicalName=lambda dim, tag: names[tag]))
    folder = tmp_path / 'output'
    (folder / 'sqe_em').mkdir(parents=True)
    (folder / 'sqe_em/sqe_em.msh').write_bytes(b'SOFTWARE MESH FIXTURE ONLY')
    deck = {'Problem': {'Type': 'Electrostatic'}, 'Model': {'L0': 1e-3},
            'Boundaries': {'Ground': {'Attributes': [6, 7]},
                'Terminal': [{'Index': index, 'Attributes': [index]} for index in (1, 2, 3)]},
            'Solver': {'Electrostatic': {'Save': 3}}}
    raw = (json.dumps(deck, indent=2) + '\n').encode()
    (folder / 'sqe_em/sqe_em.json').write_bytes(raw)
    return SimpleNamespace(model=model, em=em, sim=sim, design=design,
                           gmsh=gmsh, names=names, rows=rows, folder=folder, raw=raw)


def bind(case):
    return bind_native_terminals(case.sim, case.design, case.model, case.em, case.folder, case.gmsh)


def test_starter_requires_process_and_ground_acknowledgment_before_native_work():
    model = single_transmon_model('Unverified reference')
    assert model['process']['source'] == 'unverified'
    with pytest.raises(EngineBlocked, match='Process source'):
        preflight(model['studies'][0], model)
    model['process']['source'] = 'reviewed'
    with pytest.raises(EngineBlocked, match='ground plane'):
        preflight(model['studies'][0], model)
    model['studies'][0]['inputs']['em']['ground']['verified'] = True
    assert preflight(model['studies'][0], model) == model['studies'][0]['inputs']['em']


@pytest.mark.parametrize('mutation', [
    'same_label', 'same_geometry', 'same_index', 'boolean_index', 'overlapping_groups',
    'missing_selector', 'unknown_geometry', 'extra_conductor', 'other_component', 'connection_pad',
])
def test_ambiguous_terminal_selection_is_rejected_before_native_import(mutation):
    model = acknowledged_model()
    em = model['studies'][0]['inputs']['em']
    if mutation == 'same_label':
        em['ports'][1]['label'] = em['ports'][0]['label']
    elif mutation == 'same_geometry':
        em['ports'][1]['qgeometry'] = em['ports'][0]['qgeometry']
    elif mutation == 'same_index':
        em['ports'][1]['native_terminal_index'] = 2
    elif mutation == 'boolean_index':
        em['ground']['native_terminal_index'] = True
    elif mutation == 'overlapping_groups':
        em['ports'][0]['native_attributes'] = [1]
    elif mutation == 'missing_selector':
        del em['ports'][0]['native_terminal_index']
    elif mutation == 'unknown_geometry':
        em['ports'][0]['qgeometry'] = 'closest_pad'
    elif mutation == 'extra_conductor':
        em['ports'].append(deepcopy(em['ports'][0]))
        em['ports'][-1]['index'] = 3
    elif mutation == 'other_component':
        em['ports'][1]['component'] = 'Q2'
    else:
        model['layout']['components'][0]['connection_pads'] = {'readout': {}}
    with pytest.raises(EngineBlocked):
        preflight(model['studies'][0], model)


def test_native_ground_is_removed_from_terminal_matrix_and_original_is_preserved(native_fixture):
    case = native_fixture
    identity = bind(case)
    assert (case.folder / ORIGIN_FILE).read_bytes() == case.raw
    deck = json.loads((case.folder / 'sqe_em/sqe_em.json').read_bytes())
    assert deck['Boundaries']['Ground']['Attributes'] == [1, 6, 7]
    assert deck['Boundaries']['Terminal'] == [
        {'Index': 1, 'Attributes': [2]}, {'Index': 2, 'Attributes': [3]}]
    assert [row['Index'] for row in deck['Boundaries']['Postprocessing']['SurfaceFlux']] == [1, 2]
    assert deck['Solver']['Electrostatic']['Save'] == 2
    assert [item['qgeometry'] for item in identity['ordered_conductors']] == ['pad_bot', 'pad_top']
    assert identity['scientific_qualification'] == 'NOT_ESTABLISHED'
    assert identity['fabrication'] == 'HOLD'


@pytest.mark.parametrize('mutation', ['swapped_shape', 'changed_cad', 'wrong_group', 'wrong_ground', 'wrong_layer'])
def test_geometry_disagreement_never_relabels_or_rewrites_a_native_deck(native_fixture, mutation):
    case = native_fixture
    if mutation == 'swapped_shape':
        case.sim._cur_cap_terminals[1], case.sim._cur_cap_terminals[2] = case.sim._cur_cap_terminals[2], case.sim._cur_cap_terminals[1]
    elif mutation == 'changed_cad':
        case.rows[0]['geometry'] = box(-.15, -.18, .15, -.015)
    elif mutation == 'wrong_group':
        case.names[2] = 'unrelated_surface'
    elif mutation == 'wrong_ground':
        case.sim._cur_cap_terminals[0] = box(-.6, -.6, .6, .6)
    else:
        case.rows[0]['layer'] = 2
    with pytest.raises(EngineBlocked):
        bind(case)
    assert (case.folder / 'sqe_em/sqe_em.json').read_bytes() == case.raw
    assert not (case.folder / IDENTITY_FILE).exists()


@pytest.mark.parametrize('mutation', ['layout', 'process', 'mesh', 'origin', 'label', 'ground', 'promotion'])
def test_saved_identity_binds_model_native_bytes_and_declared_roles(native_fixture, mutation):
    case = native_fixture
    bind(case)
    manifest = {'artifacts': [{'name': name} for name in (IDENTITY_FILE, ORIGIN_FILE)]}
    assert verify_saved_identity(case.folder, manifest, case.model, case.em)['schema'].endswith('.v1')
    if mutation == 'layout':
        case.model['layout']['components'][0]['x_mm'] = .1
    elif mutation == 'process':
        case.model['process']['stack'][0]['relative_permittivity'] += 1
    elif mutation in ('mesh', 'origin'):
        target = ORIGIN_FILE if mutation == 'origin' else 'sqe_em/sqe_em.msh'
        (case.folder / target).write_bytes(b'changed')
    else:
        file = case.folder / IDENTITY_FILE
        record = json.loads(file.read_bytes())
        if mutation == 'label':
            record['ordered_conductors'][0]['label'] = 'another_pad'
        elif mutation == 'ground':
            record['ground']['native_terminal_index'] = 2
        else:
            record['scientific_qualification'] = 'APPROVED'
        file.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(EngineBlocked):
        verify_saved_identity(case.folder, manifest, case.model, case.em)


def test_legacy_component_terminals_do_not_gain_native_geometry_claims(tmp_path):
    em = {'ports': [{'component': 'LP1'}, {'component': 'LP2'}]}
    assert not named_terminals(em)
    assert verify_saved_identity(tmp_path, {}, {}, em) is None


@pytest.mark.parametrize('engine', ['sqdmetal_palace', 'scqubits'])
def test_identity_implementation_changes_invalidate_native_and_quantum_caches(monkeypatch, engine):
    from sqe_studio.orchestration.artifacts import adapter_digest
    original = Path.read_bytes
    before = adapter_digest(engine)
    def edited(path):
        raw = original(path)
        return raw + b'\n# simulated identity implementation change\n' if path.name == 'capacitance_identity.py' else raw
    monkeypatch.setattr(Path, 'read_bytes', edited)
    assert adapter_digest(engine) != before
