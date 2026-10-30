"""Real installed Quantum Metal only: no mocks, synthetic GDS or fallback writer."""
from importlib.util import find_spec
import pytest
from sqe_studio.adapters.quantum_metal_adapter import build_qdesign, run
from sqe_studio.adapters.base import EngineBlocked

if find_spec('qiskit_metal') is None:
    pytestmark = pytest.mark.skip(reason='Native conditional checks BLOCKED: qiskit_metal not installed in this Python runtime')


def _layout():
    return {'engine': 'quantum_metal',
            'chip': {'width_mm': 8, 'height_mm': 8, 'thickness_um': 500},
            'components': [
                {'kind': 'LaunchpadWirebond', 'name': 'P1', 'x_mm': -1, 'y_mm': 0, 'orientation_deg': 0},
                {'kind': 'LaunchpadWirebond', 'name': 'P2', 'x_mm': 1, 'y_mm': 0, 'orientation_deg': 180},
                {'kind': 'RouteStraight', 'name': 'R1', 'net': 'Feedline',
                 'start': {'component': 'P1', 'pin': 'tie'},
                 'end': {'component': 'P2', 'pin': 'tie'}},
            ], 'gds': {'layer_map': {'main': [1]}, 'negative_layers': []}}


def test_native_qdesign_geometry_pin_identity_and_routed_net():
    layout = _layout()
    result = build_qdesign(layout)
    assert result.design.components['P1'].name == 'P1'
    assert ('P1', 'tie') in result.pin_identities
    assert ('P2', 'tie') in result.pin_identities
    assert result.routes == (('Feedline', 'R1', ('P1', 'tie'), ('P2', 'tie')),)
    assert 1 in result.layers
    assert build_qdesign(layout).recipe_sha256 == result.recipe_sha256


def test_missing_native_pin_is_not_silently_connected():
    layout = _layout()
    layout['components'][2]['end']['pin'] = 'Nonexistent'
    with pytest.raises(EngineBlocked):
        build_qdesign(layout)


def test_native_gds_structural_readback_and_hold(tmp_path):
    result = run({'engine': 'quantum_metal', 'kind': 'gds_draft'},
                 {'layout': _layout()}, tmp_path)
    assert result['scientific_status'] == 'review_required'
    assert set(result['native_files']) == {'quantum_metal_unqualified.gds', 'gds_hold.json'}
    import json
    hold = json.loads((tmp_path / 'gds_hold.json').read_text())
    assert hold['fabrication_status'] == 'HOLD'
    assert 1 in hold['gds_structure']['layers']
    assert (tmp_path / 'quantum_metal_unqualified.gds').stat().st_size > 32


def test_native_transmon_and_resonator_geometry_is_not_emulated():
    layout = _layout()
    layout['components'] = [
        {'kind': 'TransmonCross', 'name': 'Q1', 'x_mm': -1, 'y_mm': 0,
         'connection_pads': {'readout': {'connector_location': 90}},
         'junction_cell': 'JJ1'},
        {'kind': 'ResonatorLumped', 'name': 'RR', 'x_mm': 0, 'y_mm': 0,
         'n_turns': 10, 'options': {'box_width_um': 5000}},
    ]
    build = build_qdesign(layout)
    assert 'Q1' in build.component_names
    assert 'RR' in build.component_names
    assert build.junction_layers
    assert 'JJ1' in build.junction_cells


def test_native_gds_wrong_layer_and_missing_cell_inspection_blocks(tmp_path):
    run({'kind': 'gds_draft'}, {'layout': _layout()}, tmp_path)
    from sqe_studio.adapters.quantum_metal_adapter import _inspect_native_gds
    gds = tmp_path / 'quantum_metal_unqualified.gds'
    with pytest.raises(EngineBlocked, match='omit required'):
        _inspect_native_gds(gds, {255}, set(), {1})
    with pytest.raises(EngineBlocked, match='unmapped layers'):
        _inspect_native_gds(gds, {1}, set(), {255})
    with pytest.raises(EngineBlocked, match='missing required junction cells'):
        _inspect_native_gds(gds, {1}, {'JJ_MISSING'}, {1})
