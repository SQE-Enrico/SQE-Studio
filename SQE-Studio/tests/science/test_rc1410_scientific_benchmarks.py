"""RC14.10 A16 B05/B08/B09 production-entrypoint checks.

Preflight/parser checks are software fixtures, NOT native scientific evidence.
Conditional tests invoke *real* adapter.run and raw engine outputs; missing
native engines must SKIP as BLOCKED and never be logged as executed PASS.
"""
from importlib import metadata, util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from sqe_studio.adapters import josephson_adapter as jc
from sqe_studio.adapters import scqubits_adapter as scq
from sqe_studio.adapters.base import EngineBlocked, EngineFailure
from sqe_studio.contracts import fresh_project


def test_b08_curated_cases_are_bounded_revision_scoped_and_independent():
    all_cases = list(scq._b08_native_studies())
    assert [label for label, _ in all_cases] == [
        'transmon_cutoff_plus_0', 'transmon_cutoff_plus_2',
        'fluxonium_cutoff_plus_0', 'fluxonium_cutoff_plus_2']
    for label, study in all_cases:
        project = fresh_project('B08 independent', 'transmon')
        assert study['engine'] == 'scqubits'
        spec = scq._spec(study['inputs'], project)
        assert spec['source'] == 'independent'
        assert spec['convergence']['enabled'] is True
        assert spec['levels'] == 3
        assert spec['sweep']['values'] == [0., .5, 1.]
        assert all(p['parameters']['truncated_dim'] == 6 for p in spec['groups'])
        assert spec['convergence']['tolerance_GHz'] == .5
        assert spec['convergence']['basis_increment'] == 2
        if label.startswith('fluxonium'):
            assert spec['sweep']['unit'] == 'Phi0'
        else:
            assert spec['sweep']['unit'] == '2e'
        assert not any(k in study['inputs'] for k in ('verified_em', 'em_artifact', 'lineage'))


@pytest.mark.parametrize('case_id', ['B05', 'B09'])
def test_b05_b09_curated_native_studies_are_admitted_only_by_production_validator(case_id):
    samples = list(jc._b05_b09_native_studies(case_id))
    assert len(samples) == (1 if case_id == 'B05' else 3)
    for label, study, project in samples:
        valid = jc._validate(study, project)
        assert valid[0] == ('rf_linear' if label == 'pump_off' else 'rf_harmonic_balance')
        assert valid[3] == [(1, 'in', 50.), (2, 'out', 75.)]
        assert valid[1] == [4.5e9, 4.75e9, 5e9, 5.25e9, 5.5e9]
        if label == 'pump_off':
            assert valid[4] is None
        else:
            assert valid[4][3] in (2, 3) and valid[4][4] == 1
        assert valid[5] == jc._hash(project['schematic'])


def test_benchmark_rejects_unowned_names_and_corrupt_ports():
    with pytest.raises(EngineBlocked, match='Only A16'):
        list(jc._b05_b09_native_studies('B11'))
    label, study, project = next(iter(jc._b05_b09_native_studies('B05')))
    study['inputs']['schematic_sha256'] = '0' * 64
    with pytest.raises(EngineBlocked, match='does not match immutable revision'):
        jc._validate(study, project)
    assert label == 'pump_off'


def test_b08_existing_output_blocks_before_running_solver(tmp_path, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        pytest.fail('No native solve or artifact should be created on output collision')
    monkeypatch.setattr(scq, 'require_module', lambda *_: None)
    monkeypatch.setattr(scq.metadata, 'version', lambda *_: scq.SCQUBITS_NUMERICAL_PIN)
    monkeypatch.setattr(scq, 'run', should_not_run)
    existing = tmp_path / 'b08'
    existing.mkdir()
    with pytest.raises(EngineBlocked, match='fresh non-existing'):
        scq.benchmark_b08(existing)
    assert list(existing.iterdir()) == []


def test_b08_version_mismatch_blocks_before_output_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(scq, 'require_module', lambda *_: None)
    monkeypatch.setattr(scq.metadata, 'version', lambda *_: '4.4.0')
    with pytest.raises(EngineBlocked, match='pinned native scqubits 4.3.1'):
        scq.benchmark_b08(tmp_path / 'b08')
    assert not (tmp_path / 'b08').exists()


@pytest.mark.parametrize('case_id,entrypoint', [
    ('B05', jc.benchmark_b05), ('B09', jc.benchmark_b09)])
def test_rf_existing_output_blocks_before_running_solver(tmp_path, monkeypatch, case_id, entrypoint):
    monkeypatch.setattr(jc.shutil, 'which', lambda name: '/bin/installed-julia')
    monkeypatch.setattr(jc, 'run', lambda *_args: pytest.fail('Collision reached native RF'))
    existing = tmp_path / case_id
    existing.mkdir()
    with pytest.raises(EngineBlocked, match='already exists'):
        entrypoint(existing)
    assert list(existing.iterdir()) == []


def test_rf_parser_fixture_cannot_be_misread_as_native_s21(tmp_path):
    bad = tmp_path / 'PARSER_FIXTURE_ONLY.tsv'
    bad.write_text('frequency_hz\toutput_port\tinput_port\treal\timag\n'
                   '5000000000\t2\t1\t1\t0\n', encoding='utf-8')
    with pytest.raises(EngineFailure, match='Missing native S rows|ordering'):
        jc._benchmark_native_s21(bad, [5e9])


def _julia_native_ready():
    binary = shutil.which('julia')
    if not binary:
        pytest.skip('BLOCKED: B05/B09 Julia executable missing; no native solve executed')
    probe = subprocess.run([binary, '--startup-file=no', '--history-file=no', '-e',
                            'print(Base.find_package("JosephsonCircuits") === nothing ? "MISSING" : "PRESENT")'],
                           text=True, capture_output=True, timeout=25, check=False)
    if probe.returncode == 0 and probe.stdout.strip() == 'MISSING':
        pytest.skip('BLOCKED: B05/B09 JosephsonCircuits.jl missing; no native solve executed')
    assert probe.returncode == 0 and probe.stdout.strip() == 'PRESENT', (
        'Broken native Julia installation is a FAIL, not native SKIP: ' + probe.stderr[-500:])


def test_real_b08_scqubits_transmon_fluxonium_benchmark_if_installed(tmp_path):
    if util.find_spec('scqubits') is None:
        pytest.skip('BLOCKED: native B08 scqubits not installed; no native spectra or convergence')
    assert metadata.version('scqubits') == scq.SCQUBITS_NUMERICAL_PIN, (
        'Installed scqubits differs from reviewed numerical 4.3.1 compatibility pin')
    root = tmp_path / 'B08'
    report = scq.benchmark_b08(root)
    assert json.loads((root / 'benchmark_B08.json').read_text()) == report
    assert report['execution_kind'] == 'NATIVE_SCQUBITS'
    assert report['stage_status'] == 'BLOCKED_SCIENTIFIC_REVIEW'
    assert len(report['studies']) == 4
    assert all(len(sample['native_result_sha256']) >= 3 for sample in report['studies'].values())
    print('NATIVE B08', report['native_version'], [(k, v['maximum_basis_delta_GHz'])
                                                 for k, v in report['studies'].items()])


def test_real_b05_lumped_rf_screen_if_installed(tmp_path):
    _julia_native_ready()
    root = tmp_path / 'B05'
    report = jc.benchmark_b05(root)
    assert json.loads((root / 'benchmark_B05.json').read_text()) == report
    assert report['stage_status'] == 'BLOCKED_NO_PALACE_EM_DRIVEN_COMPARISON'
    sample = report['studies']['pump_off']
    assert sample['linear_passivity_screen']['status'] == 'bounded_linear_port_screen_passed'
    assert len(sample['s21_real_imag']) == 5
    assert sample['native_process_exit_code'] == 0
    print('NATIVE B05', sample['engine_version'], sample['native_version_pin'])


def test_real_b09_jpa_native_pump_and_harmonics_if_installed(tmp_path):
    _julia_native_ready()
    root = tmp_path / 'B09'
    report = jc.benchmark_b09(root)
    assert json.loads((root / 'benchmark_B09.json').read_text()) == report
    assert report['stage_status'] == 'BLOCKED_NO_HB_RESIDUAL_OR_IDLER_REFERENCE'
    for label in ('pump_harmonics_2', 'pump_harmonics_3'):
        study = report['studies'][label]
        assert study['hb_residual_status'] == 'BLOCKED_NOT_EXPORTED_BY_NATIVE_WORKER'
        assert len(study['signal_only_amplitude_ratio_to_pump_off']) == 5
        assert study['native_completion_evidence'] == 'hbsolve_returned_no_iteration_log'
        assert study['native_process_exit_code'] == 0
    assert report['studies']['pump_off']['linear_passivity_screen']['status'] == 'bounded_linear_port_screen_passed'
    print('NATIVE B09', {k: v['engine_version'] for k, v in report['studies'].items()})
