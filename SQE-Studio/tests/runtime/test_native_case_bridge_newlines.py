"""Only native-report serialization checks: fixtures are NOT solver results."""
from __future__ import annotations
import json
from sqe_studio.native_case_bridge import _native_report_matches


def test_production_native_report_lf_and_windows_crlf_are_equivalent():
    document = {'case_id': 'B08', 'stage_status': 'BLOCKED_SCIENTIFIC_REVIEW',
                'measurements': {'frequency_GHz': [4.5, 4.7], 'notes': 'not qualified'}}
    canonical = (json.dumps(document,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    assert _native_report_matches(canonical, document)
    assert _native_report_matches(canonical.replace(b'\n',b'\r\n'), document)


def test_native_report_mismatch_still_fails_closed():
    document={'case_id': 'B09', 'measurements': [1,2]}
    canonical=(json.dumps(document,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    assert not _native_report_matches(canonical.replace(b'1',b'3'),document)
    assert not _native_report_matches(canonical + b'\n',document)
    assert not _native_report_matches(canonical.replace(b'\n',b'\r\n',1).replace(b'  ',b'   ',1),document)


def test_all_three_native_bridge_cases_accept_windows_serialized_results(tmp_path, monkeypatch):
    """Fixtures exercise OS serialization only; no solver or physics acceptance."""
    import hashlib
    from sqe_studio import native_case_bridge as bridge
    from sqe_studio.adapters import josephson_adapter, scqubits_adapter

    def make_runner(case):
        def fake_native(folder):
            folder.mkdir(parents=True)
            if case == 'B08':
                record = {'case_id': case, 'stage_status': 'BLOCKED_SCIENTIFIC_REVIEW',
                          'execution_kind': 'NATIVE_SCQUBITS', 'native_version': 'fixture',
                          'execution_resources': {'native_jobs_completed': 4},
                          'studies': {label: {} for label in ('tx1','tx2','fx1','fx2')}}
            else:
                record = {'case_id': case,
                          'stage_status': ('BLOCKED_NO_PALACE_EM_DRIVEN_COMPARISON' if case=='B05'
                                           else 'BLOCKED_NO_HB_RESIDUAL_OR_IDLER_REFERENCE'),
                          'studies': {name:{'native_process_exit_code':0} for name in
                                      (('pump_off',) if case=='B05' else
                                       ('pump_off','pump_harmonics_2','pump_harmonics_3'))}}
            source = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
            # A Windows TextIOWrapper serializes the same JSON with CRLF.
            (folder/('benchmark_'+case+'.json')).write_bytes(source.replace(b'\n',b'\r\n'))
            return record
        return fake_native
    monkeypatch.setattr(scqubits_adapter,'benchmark_b08',make_runner('B08'))
    monkeypatch.setattr(josephson_adapter,'benchmark_b05',make_runner('B05'))
    monkeypatch.setattr(josephson_adapter,'benchmark_b09',make_runner('B09'))
    for case in ('B05','B08','B09'):
        result=bridge.execute(case,tmp_path/(case+'-result.json'))
        assert result['execution_kind']=='NATIVE'
        assert result['stage_status']=='BLOCKED'
        assert result['solver_exit_code']==0
        native=(tmp_path/(case+'-native')/('benchmark_'+case+'.json')).read_bytes()
        assert result['provenance']['current_run_report_sha256']==hashlib.sha256(native).hexdigest()
        assert result['scientific_limitations'].startswith('Native numerical evidence only')
