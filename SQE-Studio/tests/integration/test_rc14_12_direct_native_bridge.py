"""RC14.12 direct native connection tests; mocks prove routing, NOT physics."""
import json
import pytest
from pathlib import Path
from sqe_studio import native_case_bridge as bridge
from sqe_studio import cycle_qualification as cycle
from sqe_studio.adapters.base import EngineBlocked

ROOT = Path(__file__).resolve().parents[2]


def test_all_three_native_benchmarks_require_source_gate():
    assert cycle._trusted_case_commands(ROOT, {}) == {}
    source = {'software/QUALIFICATION.json': json.dumps({'gates': [
        {'id': 'source_integrity', 'status': 'PASS'}]}).encode()}
    commands = cycle._trusted_case_commands(ROOT, source)
    assert set(commands) == {'B05', 'B08', 'B09'}
    assert all(cmd[1] == '-I' and cmd[-1] == case for case, cmd in commands.items())
    with pytest.raises(ValueError, match='Unregistered'):
        bridge.execute('B01', 'ignored')


@pytest.mark.parametrize('case_id', ['B05','B08','B09'])
def test_unavailable_engine_never_accepted_as_native_pass(case_id, monkeypatch):
    if case_id == 'B08':
        from sqe_studio.adapters import scqubits_adapter as adapter
        monkeypatch.setattr(adapter, 'benchmark_b08', lambda folder: (_ for _ in ()).throw(EngineBlocked('missing')))
    else:
        from sqe_studio.adapters import josephson_adapter as adapter
        monkeypatch.setattr(adapter, 'benchmark_b05' if case_id=='B05' else 'benchmark_b09',
                            lambda folder: (_ for _ in ()).throw(EngineBlocked('missing')))
    result = bridge.execute(case_id, 'never-used.json')
    assert result['stage_status'] == 'BLOCKED'
    assert result['execution_kind'] == 'NOT_RUN'
    assert result['provenance'] is None
    assert result['solver_exit_code'] is None


def test_fabrication_and_mode_identity_remain_blocked():
    results = cycle.run_scientific_case_matrix(ROOT, {})
    assert results['fabrication'] == 'HOLD'
    assert results['mode_identity'] == 'UNRESOLVED'
    assert results['em_to_hamiltonian'] == 'BLOCKED'
    assert results['dispatch_release'] == 'RC14.12'


def test_qdesign_partial_native_gate_keeps_gds_mesh_blocked():
    source = {'software/QUALIFICATION.json': json.dumps({'gates': [
        {'id': 'source_integrity','status':'PASS'},
        {'id': 'native_quantum_metal','status':'PASS','counts':{'passed':5}}
    ]}).encode()}
    outcome = cycle._case_from_native_cad_gate(source, 'B01')
    assert outcome['execution_kind'] == 'NATIVE'
    assert outcome['measurements']['native_qdesign_tests_passed'] == 5
    assert outcome['stage_status'] == 'BLOCKED'
    assert 'GDS_GMSH' in outcome['failure_reason']
    source['software/QUALIFICATION.json'] = json.dumps({'gates': [
        {'id': 'source_integrity','status':'FAIL'},
        {'id': 'native_quantum_metal','status':'PASS','counts':{'passed':5}}
    ]}).encode()
    assert cycle._case_from_native_cad_gate(source,'B01')['execution_kind'] == 'NOT_RUN'
