"""Pure validation of A02's reviewed declarative recipe (no synthetic geometry)."""
import copy
import json
import pytest

from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.quantum_metal_adapter import (
    COMPONENTS, ROUTES, build_qdesign, run, validate_recipe,
)


def layout(*components, gds=None):
    recipe = {'engine': 'quantum_metal',
              'chip': {'width_mm': 8, 'height_mm': 8, 'thickness_um': 500},
              'components': list(components)}
    if gds is not None:
        recipe['gds'] = gds
    return recipe


def pad(name, x=0, y=0, **kw):
    return {'kind': 'LaunchpadWirebond', 'name': name, 'x_mm': x, 'y_mm': y, **kw}


def route(kind='RouteStraight', **kw):
    return {'kind': kind, 'name': 'r1', 'net': 'N1',
            'start': {'component': 'P1', 'pin': 'tie'},
            'end': {'component': 'P2', 'pin': 'tie'}, **kw}


def run_recipe(rec, tmp_path):
    return run({'kind': 'gds_draft', 'engine': 'quantum_metal'}, {'layout': rec}, tmp_path)


def test_allowlist_is_literal_and_restricted():
    assert {'TransmonPocket', 'TransmonCross', 'ResonatorLumped', 'ReadoutResFC',
            'LaunchpadWirebond', 'OpenToGround', 'ShortToGround',
            'RouteStraight', 'RouteMeander', 'RouteAnchors', 'RoutePathfinder'} <= set(COMPONENTS)
    assert ROUTES <= set(COMPONENTS)
    for module, symbol in COMPONENTS.values():
        assert module.startswith('qiskit_metal.qlibrary.')
        assert symbol.isidentifier()


@pytest.mark.parametrize('illegal', [
    {'kind': 'CustomComponent', 'name': 'P1', 'x_mm': 0, 'y_mm': 0},
    {'kind': '__import__', 'name': 'P1', 'x_mm': 0, 'y_mm': 0},
    {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': 0, 'y_mm': 0, 'options': {'expression': '1+evil()'}},
    {'kind': 'LaunchpadWirebond', 'name': '../escape', 'x_mm': 0, 'y_mm': 0},
    {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': True, 'y_mm': 0},
    {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': float('inf'), 'y_mm': 0},
    {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': 0, 'y_mm': 0, 'bad_path': 'hack'},
    {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': 0, 'y_mm': 0, 'connection_pads': {}},
])
def test_illegal_primitive_name_expression_transform_or_pad_rejected(illegal):
    with pytest.raises(EngineBlocked):
        validate_recipe(layout(illegal))


def test_duplicate_component_and_pin_route_rejected():
    with pytest.raises(EngineBlocked, match='duplicate QComponent'):
        validate_recipe(layout(pad('P1'), pad('P1', 1)))
    with pytest.raises(EngineBlocked, match='terminal pin'):
        validate_recipe(layout(pad('P1'), pad('P2', 1), route(),
                              {**route(), 'name': 'r2', 'net': 'N2'}))
    with pytest.raises(EngineBlocked, match='duplicate route net'):
        validate_recipe(layout(pad('P1'), pad('P2', 1), route(),
                              {**route(), 'name': 'r2'}))
    with pytest.raises(EngineBlocked, match='missing terminal'):
        validate_recipe(layout(pad('P1'), pad('P2', 1), {**route(), 'start': {'component': 'Missing', 'pin': 'x'}}))
    with pytest.raises(EngineBlocked, match='distinct component'):
        validate_recipe(layout(pad('P1'), pad('P2', 1), {**route(), 'end': {'component': 'P1', 'pin': 'other'}}))


def test_route_order_and_parameters_are_deterministic_no_mutation():
    rec = layout(route('RoutePathfinder', layer=2, step_size_um=250,
                       constraints={'avoid_collision': True},
                       anchors=[{'x_mm': 0.2, 'y_mm': 0.4}]),
                 pad('P2', 1, layer=2, orientation_deg=90,
                     options={'pad_width_um': 85}),
                 pad('P1', -1, layer=2))
    original = copy.deepcopy(rec)
    order, chip = validate_recipe(rec)
    assert [p.name for p in order] == ['P1', 'P2', 'r1']
    assert order[-1].endpoints == (('P1', 'tie'), ('P2', 'tie'))
    assert order[-1].options['anchors'][0] == (0.2, 0.4)
    assert order[1].options['orientation'] == '90'
    assert order[1].options['pad_width'] == '85um'
    assert rec == original
    assert chip['width_mm'] == 8
    assert json.dumps(rec, sort_keys=True)


def test_reviewed_cross_pads_and_resonator_dimensions():
    rec = layout({'kind': 'TransmonCross', 'name': 'Q1', 'x_mm': 0, 'y_mm': 0,
                  'junction_cell': 'JJ_CELL', 'layer': 3,
                  'connection_pads': {'readout': {'connector_type': 0,
                                                   'connector_location': 90,
                                                   'claw_gap_um': 6}}},
                 {'kind': 'ResonatorLumped', 'name': 'RR', 'x_mm': 1, 'y_mm': 1,
                  'n_turns': 12, 'options': {'box_width_um': 1000}})
    planned, _ = validate_recipe(rec)
    assert planned[0].options['connection_pads']['readout']['claw_gap'] == '6um'
    assert planned[0].junction_cell == 'JJ_CELL'
    assert planned[1].options['n_turns'] == '12'
    with pytest.raises(EngineBlocked, match='connector_type'):
        bad = copy.deepcopy(rec)
        bad['components'][0]['connection_pads']['readout']['connector_type'] = 7
        validate_recipe(bad)
    with pytest.raises(EngineBlocked, match='junction cell'):
        bad = copy.deepcopy(rec)
        bad['components'][0]['junction_cell'] = '../../bad'
        validate_recipe(bad)


@pytest.mark.parametrize('kind, settings', [
    ('RouteStraight', {'anchors': [{'x_mm': 0, 'y_mm': 0}]}),
    ('RouteMeander', {'constraints': {'avoid_collision': True}}),
    ('RoutePathfinder', {'constraints': {'avoid_collision': False}}),
    ('RouteMeander', {'meander': {'spacing_um': -5}}),
    ('RoutePathfinder', {'step_size_um': 0}),
    ('RouteStraight', {'total_length_mm': 2}),
    ('RouteAnchors', {'anchors': []}),
    ('RouteStraight', {'trace_width_um': float('nan')}),
])
def test_illegal_route_configuration_fails_closed(kind, settings):
    with pytest.raises(EngineBlocked):
        validate_recipe(layout(pad('P1'), pad('P2', 1), route(kind, **settings)))


def test_layer_mismatch_and_subtraction_layer_require_explicit_mapping():
    with pytest.raises(EngineBlocked, match='layer does not match'):
        validate_recipe(layout(pad('P1'), pad('P2', 1, layer=2), route(layer=1)))
    with pytest.raises(EngineBlocked, match='subtract_layer'):
        validate_recipe(layout({'kind': 'ReadoutResFC', 'name': 'RR', 'x_mm': 0, 'y_mm': 0}))
    planned, _ = validate_recipe(layout({'kind': 'ReadoutResFC', 'name': 'RR',
                                         'x_mm': 0, 'y_mm': 0, 'subtract_layer': 2}))
    assert planned[0].options['layer_subtract'] == '2'


@pytest.mark.parametrize('gds', [
    {'layer_map': {'main': [2]}, 'negative_layers': []},
    {'layer_map': {'main': [1]}, 'negative_layers': [2]},
    {'layer_map': {'main': [1, 1]}, 'negative_layers': []},
    {'layer_map': {'main': [True]}, 'negative_layers': []},
    {'layer_map': {'main': [1]}, 'negative_layers': [1, 1]},
    {'layer_map': {'other': [1]}, 'negative_layers': []},
])
def test_gds_mask_layer_mapping_rejected_before_native_run(gds, tmp_path):
    with pytest.raises(EngineBlocked):
        run_recipe(layout(pad('P1'), gds=gds), tmp_path)
    assert not list(tmp_path.glob('*.gds'))


def test_gds_missing_pdk_mapping_fails_closed(tmp_path):
    with pytest.raises(EngineBlocked, match='layout.gds'):
        run_recipe(layout(pad('P1')), tmp_path)
    assert not list(tmp_path.glob('*.gds'))


def test_junction_cell_mandatory_and_authenticated_asset_staging_blocked(tmp_path):
    transmon = {'kind': 'TransmonPocket', 'name': 'Q1', 'x_mm': 0, 'y_mm': 0}
    gds = {'layer_map': {'main': [1]}, 'negative_layers': []}
    with pytest.raises(EngineBlocked, match='junction_cell required'):
        run_recipe(layout(transmon, gds=gds), tmp_path)
    with pytest.raises(EngineBlocked, match='staging'):
        run_recipe(layout({**transmon, 'junction_cell': 'JJ1'}, gds=gds), tmp_path)
    assert not list(tmp_path.glob('*.gds'))


def test_uninstalled_engine_is_blocked_and_never_replaced(tmp_path):
    from importlib.util import find_spec
    if find_spec('qiskit_metal'):
        pytest.skip('Quantum Metal is installed; absence-only behavior not applicable')
    rec = layout(pad('P1'))
    with pytest.raises(EngineBlocked, match='not installed'):
        build_qdesign(rec)
    with pytest.raises(EngineBlocked, match='not installed'):
        run_recipe({**rec, 'gds': {'layer_map': {'main': [1]}, 'negative_layers': []}}, tmp_path)
    assert not list(tmp_path.glob('*'))


def test_read_only_gds_inspector_rejects_truncated_non_native_input(tmp_path):
    """Malformed bytes are rejected; this fixture is NOT a synthetic valid GDS."""
    from sqe_studio.adapters.quantum_metal_adapter import _inspect_native_gds
    bad = tmp_path / 'truncated-not-native.gds'
    bad.write_bytes(b'not a valid GDSII stream' * 3)
    with pytest.raises(EngineBlocked, match='malformed/truncated'):
        _inspect_native_gds(bad, {1}, set(), {1})
