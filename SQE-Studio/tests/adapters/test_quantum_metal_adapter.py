"""Pure contract tests of Quantum Metal endpoint QNet semantics (not native runs)."""
import pytest
from types import SimpleNamespace
from sqe_studio.adapters.quantum_metal_adapter import _verify_route_endpoint_connections
from sqe_studio.adapters.base import EngineBlocked


def test_endpoint_pair_nets_are_independently_linked():
    a = SimpleNamespace(pins={'tie': {'net_id': 11}})
    b = SimpleNamespace(pins={'tie': {'net_id': 12}})
    route = SimpleNamespace(pins={'start': {'net_id': 11}, 'end': {'net_id': 12}})
    design = SimpleNamespace(components={'P1': a, 'P2': b})
    # Two distinct IDs are valid in Quantum Metal: each identifies an endpoint pair.
    _verify_route_endpoint_connections(design, route, ('P1', 'tie'), ('P2', 'tie'), 'R1')
    b.pins['tie']['net_id'] = 13
    with pytest.raises(EngineBlocked, match='end.*not connected'):
        _verify_route_endpoint_connections(design, route, ('P1', 'tie'), ('P2', 'tie'), 'R1')
    b.pins['tie']['net_id'] = 12
    route.pins['start']['net_id'] = 0
    with pytest.raises(EngineBlocked, match='start.*not connected'):
        _verify_route_endpoint_connections(design, route, ('P1', 'tie'), ('P2', 'tie'), 'R1')


def test_device_neutral_passive_layout_is_accepted_without_junction_assumptions():
    """Recipe contract only; does not emulate a Quantum Metal renderer."""
    from sqe_studio.adapters.quantum_metal_adapter import validate_recipe, ROUTES
    layout = {'engine': 'quantum_metal',
              'chip': {'width_mm': 6, 'height_mm': 3, 'thickness_um': 450},
              'components': [
                  {'kind': 'LaunchpadWirebond', 'name': 'In', 'x_mm': -1, 'y_mm': 0},
                  {'kind': 'LaunchpadWirebond', 'name': 'Out', 'x_mm': 1, 'y_mm': 0},
                  {'kind': 'ResonatorLumped', 'name': 'Filter', 'x_mm': 0, 'y_mm': 1,
                   'options': {'box_width_um': 80}},
                  {'kind': 'RouteStraight', 'name': 'Through', 'net': 'S21',
                   'start': {'component': 'In', 'pin': 'tie'},
                   'end': {'component': 'Out', 'pin': 'tie'}},
              ]}
    planned, _ = validate_recipe(layout)
    assert {x.kind for x in planned} == {'LaunchpadWirebond', 'ResonatorLumped', 'RouteStraight'}
    assert all(x.junction_cell is None for x in planned)
    assert {x.net for x in planned if x.kind in ROUTES} == {'S21'}


def test_qdesign_layout_digest_changes_with_geometry_and_is_order_independent():
    """Content revisions are bound to layout, not labels or mode indices."""
    from sqe_studio.contracts import digest
    original = {'engine': 'quantum_metal',
                'chip': {'width_mm': 4, 'height_mm': 4, 'thickness_um': 500},
                'components': [{'kind': 'OpenToGround', 'name': 'Stub', 'x_mm': 0, 'y_mm': 0}]}
    reordered = {'components': original['components'], 'chip': original['chip'], 'engine': original['engine']}
    assert digest(original) == digest(reordered)
    changed = {**original, 'components': [{**original['components'][0], 'x_mm': 0.1}]}
    assert digest(original) != digest(changed)
