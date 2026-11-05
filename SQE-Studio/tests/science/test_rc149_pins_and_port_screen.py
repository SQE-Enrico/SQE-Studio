"""RC14.9 A16 software admission probes and opt-in *real* native tests.

Synthetic TSV data below are strictly parser/screen negative controls, NOT RF
measurements. Conditional tests must run actual engines or SKIP/BLOCKED.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
from importlib import metadata, util
import math
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sqe_studio.adapters import josephson_adapter as jc, scqubits_adapter as scq
from sqe_studio.adapters.base import EngineBlocked, EngineFailure
from sqe_studio.contracts import fresh_project


def _raw_s(tmp_path, values):
    path = tmp_path / 'parser_only_not_native.tsv'
    lines = ['frequency_hz\toutput_port\tinput_port\treal\timag']
    lines.extend(f'5e9\t{i}\t{j}\t{v.real:.17g}\t{v.imag:.17g}'
                 for i, row in enumerate(values, start=1)
                 for j, v in enumerate(row, start=1))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    jc._check_s(path, [5e9], list(range(1, len(values) + 1)))
    return path


def test_parser_only_reciprocal_lossy_asymmetric_reference_screen(tmp_path):
    # Shape fixture: a valid passive 2-port power-wave matrix only tests math.
    path = _raw_s(tmp_path, [[.7+.1j, .15-.1j], [.15-.1j, .6+.2j]])
    check = jc._screen_passive_linear_s(path, [5e9], [1, 2])
    assert check['status'] == 'bounded_linear_port_screen_passed'
    assert 0 < check['max_singular_value'] < 1
    assert check['max_reciprocity_difference'] == 0
    assert 'not EM calibration' in check['scope']


@pytest.mark.parametrize('rows,reason', [
    ([[1.01+0j, 0j], [0j, .2+0j]], 'passive/reciprocal'),
    ([[.6+0j, .3+0j], [.1+0j, .6+0j]], 'passive/reciprocal'),
    # Each column has norm < 1; simultaneous excitation singular value > 1.
    ([[.8+0j, .4+0j], [.4+0j, .8+0j]], 'passive/reciprocal'),
])
def test_parser_only_rf_safety_screen_rejects_nonpassive_or_nonreciprocal(tmp_path, rows, reason):
    path = _raw_s(tmp_path, rows)
    with pytest.raises(EngineFailure, match=reason):
        jc._screen_passive_linear_s(path, [5e9], [1, 2])


def test_julia_fixed_worker_requires_manifest_locked_real_package_tree():
    code = jc.FIXED_JULIA_WORKER
    assert 'using JosephsonCircuits' in code and 'using TOML' in code and 'using SHA' in code
    assert 'Base.active_project()' in code
    assert 'TOML.parsefile(manifest_file)' in code
    assert 'locked_version == string(ver)' in code
    assert 'git-tree-sha1' in code
    assert 'sha256(read(manifest_file))' in code
    assert 'println(io, "josephson_tree_sha1' in code
    assert 'eval(' not in code and 'include(' not in code


def test_scqubits_pinning_is_pre_execution_and_no_artifacts(tmp_path, monkeypatch):
    class FakeUnits:
        def set_units(self, *_):
            pytest.fail('Unpinned runtime reached unit setter / numerical execution')
    monkeypatch.setitem(sys.modules, 'scqubits', FakeUnits())
    monkeypatch.setattr(scq, 'require_module', lambda *args: None)
    monkeypatch.setattr(scq.metadata, 'version', lambda _: '4.4.0')
    study = {'id': 'pin-negative', 'engine': 'scqubits', 'kind': 'spectrum',
             'inputs': {'model': 'Transmon', 'levels': 3, 'source': 'independent',
                        'parameters': {'EJ': 15., 'EC': .25, 'ng': 0., 'ncut': 10},
                        'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'}}}
    with pytest.raises(EngineBlocked, match='not the pinned 4.3.1'):
        scq.run(study, fresh_project('Pin negative', 'transmon'), tmp_path)
    assert not list(tmp_path.iterdir())
    assert scq.SCQUBITS_NUMERICAL_PIN == '4.3.1'


def test_julia_missing_manifest_pin_is_rejected_before_native_signal_admission(tmp_path):
    from test_native_rf_boundaries import native_metadata
    raw = native_metadata().replace('manifest_sha256\t' + 'a' * 64 + '\n', '')
    file = tmp_path / 'metadata_fixture_only.tsv'
    file.write_text(raw, encoding='utf-8')
    with pytest.raises(EngineFailure, match='metadata rejected'):
        jc._parse_metadata(file, [1, 2])


def test_native_scqubits_version_pin_and_basis_only_when_installed(tmp_path):
    if util.find_spec('scqubits') is None:
        pytest.skip('BLOCKED: scqubits distribution unavailable; no native numerical solve')
    assert metadata.version('scqubits') == scq.SCQUBITS_NUMERICAL_PIN, (
        'Native scqubits installed, but compatibility version differs from reviewed 4.3.1 pin')
    study = {'id': 'RC14.9-A16-basis', 'engine': 'scqubits', 'kind': 'spectrum',
             'inputs': {'model': 'Transmon', 'source': 'independent', 'levels': 3,
                        'parameters': {'EJ': 15., 'EC': .25, 'ng': 0., 'ncut': 10},
                        'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
                        'convergence': {'enabled': True, 'basis_increment': 2,
                                        'tolerance_GHz': .05}}}
    result = scq.run(study, fresh_project('Native explicit basis', 'transmon'), tmp_path)
    snapshot = json.loads((tmp_path / 'input_snapshot.json').read_text())
    spectrum = json.loads((tmp_path / 'spectrum.json').read_text())
    assert snapshot['native_versions']['scqubits'] == scq.SCQUBITS_NUMERICAL_PIN
    assert snapshot['native_versions']['scqubits_compatibility_pin'] == scq.SCQUBITS_NUMERICAL_PIN
    assert spectrum['convergence']['checked_points'] == 1
    assert spectrum['convergence']['points'][0]['max_delta_GHz'] <= .05
    assert spectrum['scientific_status'] == result['scientific_status'] == 'review_required'
    assert snapshot['cross_engine_mapping']['status'] == 'blocked'
    print('ACTUAL NATIVE scqubits', result['engine_version'],
          'basis_delta_GHz=', spectrum['convergence']['points'][0]['max_delta_GHz'])


def test_native_julia_manifest_pin_and_rf_screen_only_when_installed(tmp_path):
    julia = shutil.which('julia')
    if not julia:
        pytest.skip('BLOCKED: Julia binary unavailable; no native JosephsonCircuits solve')
    check = subprocess.run([julia, '--startup-file=no', '--history-file=no', '-e',
                            'print(Base.find_package("JosephsonCircuits") === nothing ? "MISSING" : "PRESENT")'],
                           capture_output=True, text=True, timeout=25, check=False)
    if check.returncode == 0 and check.stdout.strip() == 'MISSING':
        pytest.skip('BLOCKED: native JosephsonCircuits package unavailable')
    assert check.returncode == 0 and check.stdout.strip() == 'PRESENT', (
        'Broken Julia package probe is FAIL, not a simulated native SKIP')
    from test_native_rf_boundaries import two_port_case
    study, project = two_port_case()
    result = jc.run(study, project, tmp_path)
    sidecar = json.loads((tmp_path / 'josephson_ports.json').read_text())
    pin = sidecar['native_version_pin']
    assert len(pin['manifest_sha256']) == 64 and len(pin['josephson_tree_sha1']) == 40
    assert sidecar['native_linear_port_screen']['status'] == 'bounded_linear_port_screen_passed'
    assert sidecar['native_process_exit_code'] == 0
    assert result['scientific_status'] == 'review_required'
    print('ACTUAL NATIVE JosephsonCircuits', result['engine_version'],
          'manifest_sha256=', pin['manifest_sha256'],
          'worst_S_singular=', sidecar['native_linear_port_screen']['max_singular_value'])
