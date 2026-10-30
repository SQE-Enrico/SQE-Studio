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
