"""Fixed, trusted, bounded native numerical benchmark bridge for Automatic Test.

The CLI has NO arbitrary command, model or path arguments. B05/B08/B09 call
production adapters and keep every unvalidated physical transfer BLOCKED.
This is not a scientific qualification or a substitute solver.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import time

# -I ignores PYTHONPATH. Import this exact source release, not a system wheel.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(case_id, status='BLOCKED', execution='NOT_RUN',
            reason='NATIVE_PREREQUISITE_NOT_AVAILABLE', **kw):
    result = dict(case_id=case_id, stage_status=status, execution_kind=execution,
                  provenance=None, solver_version=None, input_sha256=None,
                  geometry_revision_sha256=None, material_bc_mesh_hashes=None,
                  units=None, measurements=None, numerical_tolerances=None,
                  solver_exit_code=None, duration_s=0,
                  scientific_limitations='Native numerical evidence only. No validated EM-to-quantum/RF transfer, eigenstate overlap, experimental calibration, or fabrication permission.',
                  failure_reason=reason, log_sha256=None)
    result.update(kw)
    return result


def _native_report_matches(raw: bytes, report: dict) -> bool:
    """Verify an actual production report without OS newline false negatives.

    TextIOWrapper with its default newline policy writes CRLF on Windows,
    while json.dumps builds LF-only bytes. Accept precisely either complete
    platform representation, not altered values, whitespace, extra JSON, or
    fabricated benchmark output. Hash the ORIGINAL bytes for provenance.
    """
    canonical = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    return raw == canonical or raw == canonical.replace(b'\n', b'\r\n')


def execute(case_id, output_json):
    if case_id not in ('B05', 'B08', 'B09'):
        raise ValueError('Unregistered native case')
    from sqe_studio.adapters.base import EngineBlocked, EngineFailure
    started = time.monotonic()
    folder = Path(output_json).parent / (case_id + '-native')
    try:
        if case_id == 'B08':
            from sqe_studio.adapters.scqubits_adapter import benchmark_b08
            report = benchmark_b08(folder)
            valid = (report.get('execution_kind') == 'NATIVE_SCQUBITS' and
                     report.get('stage_status') == 'BLOCKED_SCIENTIFIC_REVIEW' and
                     report.get('execution_resources', {}).get('native_jobs_completed') == 4)
            named = 'benchmark_B08.json'
            numbers = {'native_jobs_completed': 4,
                       'cutoff_start_comparison': report.get('cutoff_start_comparison'),
                       'study_hashes': {name: row.get('native_result_sha256')
                                        for name, row in report.get('studies', {}).items()},
                       'sweep_transitions_GHz': {name: row.get('sweep_transitions_GHz')
                                                for name, row in report.get('studies', {}).items()},
                       'basis_delta_GHz': {name: row.get('maximum_basis_delta_GHz')
                                           for name, row in report.get('studies', {}).items()},
                       'periodicity_delta_GHz': {name: row.get('periodicity_transition_delta_GHz')
                                                 for name, row in report.get('studies', {}).items()}}
            units = {'energies': 'E/h GHz', 'flux': 'Phi0', 'charge': '2e'}
            version = 'scqubits ' + str(report.get('native_version', 'unknown'))
            reason = 'NATIVE_SPECTRA_EXECUTED_EM_HAMILTONIAN_TRANSFER_UNVALIDATED'
        else:
            from sqe_studio.adapters.josephson_adapter import benchmark_b05, benchmark_b09
            report = benchmark_b05(folder) if case_id == 'B05' else benchmark_b09(folder)
            expected = ('BLOCKED_NO_PALACE_EM_DRIVEN_COMPARISON' if case_id == 'B05'
                        else 'BLOCKED_NO_HB_RESIDUAL_OR_IDLER_REFERENCE')
            study_count = 1 if case_id == 'B05' else 3
            valid = (report.get('case_id') == case_id and
                     report.get('stage_status') == expected and
                     len(report.get('studies', {})) == study_count and
                     all(row.get('native_process_exit_code') == 0
                         for row in report['studies'].values()))
            named = 'benchmark_' + case_id + '.json'
            numbers = {'native_jobs_completed': study_count,
                       'study_statuses': {name: {
                           'native_process_exit_code': row.get('native_process_exit_code'),
                           'engine_version': row.get('engine_version'),
                           's21_real_imag': row.get('s21_real_imag'),
                           'signal_only_amplitude_ratio_to_pump_off': row.get('signal_only_amplitude_ratio_to_pump_off'),
                           'hb_residual_status': row.get('hb_residual_status')}
                           for name, row in report['studies'].items()}}
            units = {'frequency': 'Hz', 'ports': 'native reference-impedance convention'}
            version = 'JosephsonCircuits.jl native'
            reason = ('NATIVE_RF_EXECUTED_EM_DRIVEN_COMPARISON_UNVALIDATED' if case_id == 'B05'
                      else 'NATIVE_HARMONIC_BALANCE_EXECUTED_RESIDUAL_UNVALIDATED')
        raw = (folder / named).read_bytes()
        if not valid or not _native_report_matches(raw, report):
            # Preserve a path-free diagnostic reason to distinguish Windows
            # serialization from a changed production benchmark contract.
            reason = ('PRODUCTION_NATIVE_REPORT_STRUCTURE_MISMATCH' if not valid else
                      'PRODUCTION_NATIVE_REPORT_SERIALIZATION_MISMATCH')
            return _record(case_id, status='FAIL', execution='NATIVE',
                           solver_exit_code=1, reason=reason)
        # Bounded current-run measurements and hashes: NEVER a physical PASS.
        # Source native files remain temporary and are not copied into user reports.
        return _record(case_id, execution='NATIVE', solver_exit_code=0,
                       reason=reason, duration_s=round(time.monotonic() - started, 2),
                       provenance={'native_run': True, 'current_run_report_sha256': _digest(raw),
                                   'historical_data_reused': False,
                                   'native_artifacts': [{'path': case_id + '-native/' + named,
                                                         'sha256': _digest(raw)}]},
                       solver_version=version,
                       input_sha256=_digest(raw), log_sha256=_digest(raw),
                       units=units, measurements=numbers,
                       numerical_tolerances={'physical_gate': 'BLOCKED_REQUIRES_REVIEW'})
    except EngineBlocked:
        return _record(case_id, reason='NATIVE_PREREQUISITE_BLOCKED',
                       duration_s=round(time.monotonic() - started, 2))
    except EngineFailure:
        return _record(case_id, status='FAIL', execution='NATIVE', solver_exit_code=1,
                       reason='NATIVE_SOLVER_OR_NUMERICAL_CHECK_FAILED',
                       duration_s=round(time.monotonic() - started, 2))


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('B05', 'B08', 'B09'):
        raise SystemExit(2)
    try:
        result = execute(sys.argv[1], sys.argv[2])
    except Exception as exc:
        # Do not reveal an unsanitized native exception or machine-local path.
        result = _record(sys.argv[1], status='FAIL', execution='NOT_RUN',
                         reason='BENCHMARK_ADAPTER_EXCEPTION_' + type(exc).__name__)
    Path(sys.argv[2]).write_text(json.dumps(result, sort_keys=True, allow_nan=False) + '\n',
                                 encoding='utf-8')


if __name__ == '__main__':
    main()
