"""A99 RC14.11 integration: real-bounded B08 path and safety invariants."""
from pathlib import Path
import json
import sys
from sqe_studio import cycle_qualification as c

ROOT=Path(__file__).resolve().parents[2]


def test_default_registry_must_have_current_run_source_gate():
    assert c._trusted_case_commands(ROOT, {}) == {}
    assert c._trusted_case_commands(ROOT, {'software/QUALIFICATION.json':json.dumps({
        'gates':[{'id':'source_integrity','status':'FAIL'}]}).encode()}) == {}
    commands=c._trusted_case_commands(ROOT, {'software/QUALIFICATION.json':json.dumps({
        'gates':[{'id':'source_integrity','status':'PASS'}]}).encode()})
    assert set(commands)=={'B05','B08','B09'}  # B01 must not be misrepresented as registered native mesh.
    assert commands['B08'][1]=='-I'
    assert commands['B08'][2]==str(ROOT/'src/sqe_studio/native_case_bridge.py')
    assert commands['B08'][3]=='B08'


def test_missing_scqubits_is_bounded_blocker_not_fixture_pass(monkeypatch):
    # A native adapter result is valid only if it was actually run. On machines
    # without the pinned engine the real production CLI must return NOT_RUN.
    from sqe_studio.adapters import scqubits_adapter as a
    import sqe_studio.native_case_bridge as b
    def blocked(*args,**kwargs):
        from sqe_studio.adapters.base import EngineBlocked
        raise EngineBlocked('no pinned scqubits')
    monkeypatch.setattr(a,'benchmark_b08',blocked)
    result=b.execute('B08','unused-result-path.json')
    assert result['case_id']=='B08'
    assert result['execution_kind']=='NOT_RUN'
    assert result['stage_status']=='BLOCKED'
    assert result['solver_exit_code'] is None
    assert result['provenance'] is None


def test_actual_child_sanitized_not_run_or_numerics_but_not_scientific_pass():
    commands=c._trusted_case_commands(ROOT,{'software/QUALIFICATION.json':json.dumps({
        'gates':[{'id':'source_integrity','status':'PASS'}]}).encode()})
    outcome=c._case_command(ROOT,'B08',commands['B08'],60,lambda _message:None)
    assert outcome['case_id']=='B08'
    assert outcome['stage_status'] in ('BLOCKED','FAIL')  # no physical qualification
    assert outcome['stage_status'] != 'PASS'
    assert outcome['execution_kind'] in ('NOT_RUN','NATIVE')
    assert outcome['solver_exit_code'] in (None,0,1)
    assert outcome['failure_reason'] != 'UNVERIFIED_NATIVE_ADAPTER_REPORT'


def test_b01_unwired_and_scientific_gates_fail_closed():
    commands=c._trusted_case_commands(ROOT, {'software/QUALIFICATION.json':json.dumps({
        'gates':[{'id':'source_integrity','status':'PASS'}]}).encode()})
    result=c.run_scientific_case_matrix(ROOT,{},commands=commands)
    cases={x['case_id']:x for x in result['cases']}
    assert cases['B01']['execution_kind']=='NOT_RUN'
    assert cases['B01']['stage_status']=='BLOCKED'
    assert cases['B08']['stage_status']!='PASS'
    assert result['mode_identity']=='UNRESOLVED'
    assert result['em_to_hamiltonian']=='BLOCKED'
    assert result['fabrication']=='HOLD'
