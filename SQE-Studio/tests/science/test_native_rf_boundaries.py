"""A16 scientific boundaries and conditional native RF/quantum benchmarks.

Fixtures here test serialization and fail-closed parsing, NOT simulated native
solver success. Only tests invoking the real production adapters with installed
Julia/JosephsonCircuits or scqubits count as native execution evidence.
"""
import hashlib
import json
from importlib import metadata, util
import shutil
import subprocess

import pytest

from sqe_studio.adapters import josephson_adapter as jc, scqubits_adapter as scq
from sqe_studio.adapters.base import EngineBlocked, EngineFailure
from sqe_studio.contracts import fresh_project


def native_metadata(**overrides):
    # Parser-only synthetic TSV, never submitted to run() or called a solver result.
    values = {
        'schema': 'sqe.josephson-native.v1',
        'julia_version': '1.10.2', 'josephson_version': '0.4.2',
        'manifest_sha256': 'a' * 64, 'josephson_tree_sha1': 'b' * 40,
        'native_port_order': '1,2', 'native_impedance_indices': '2,4',
        'elapsed_seconds': '1.25', 'signal_mode': '0',
        'frequency_unit': 'Hz',
        's_parameter_unit': 'dimensionless_complex_native_power_wave',
        'convergence_evidence': 'linear_solve_returned',
    }
    values.update(overrides)
    return ''.join(f'{key}\t{value}\n' for key, value in values.items())


@pytest.mark.parametrize('change', [
    lambda txt: txt + 'julia_version\t0.0.0\n',
    lambda txt: txt.replace('julia_version\t1.10.2', 'julia_version\tunknown'),
    lambda txt: txt.replace('native_impedance_indices\t2,4', 'native_impedance_indices\t2,2'),
    lambda txt: txt.replace('manifest_sha256\t' + 'a' * 64, 'manifest_sha256\t' + 'a' * 63),
    lambda txt: txt.replace('josephson_tree_sha1\t' + 'b' * 40, 'josephson_tree_sha1\tunknown'),
    lambda txt: txt.replace('native_port_order\t1,2', 'native_port_order\t2,1'),
    lambda txt: txt.replace('frequency_unit\tHz', 'frequency_unit\tGHz'),
    lambda txt: txt.replace('elapsed_seconds\t1.25', 'elapsed_seconds\tnan'),
    lambda txt: txt.replace('schema\tsqe.josephson-native.v1', 'schema\tsqe.fake'),
    lambda txt: txt + 'invalid_row_without_separator\n',
])
def test_native_metadata_fails_closed_on_malformed_physical_or_provenance_claim(tmp_path, change):
    file = tmp_path / 'parser_only.tsv'
    file.write_text(change(native_metadata()), encoding='utf-8')
    with pytest.raises(EngineFailure, match='metadata rejected'):
        jc._parse_metadata(file, [1, 2])


def test_native_metadata_exact_units_and_nonaliased_port_indices(tmp_path):
    file = tmp_path / 'parser_only.tsv'
    file.write_text(native_metadata(), encoding='utf-8')
    data = jc._parse_metadata(file, [1, 2])
    assert data['manifest_sha256'] == 'a' * 64
    assert data['josephson_tree_sha1'] == 'b' * 40
    assert data['frequency_unit'] == 'Hz'
    assert data['s_parameter_unit'] == 'dimensionless_complex_native_power_wave'


def test_existing_port_provenance_never_overwritten(tmp_path, monkeypatch):
    study, project = two_port_case()
    (tmp_path / 'josephson_ports.json').write_text('DO NOT REPLACE', encoding='utf-8')
    monkeypatch.setattr(jc.shutil, 'which', lambda name: '/declared/julia')
    with pytest.raises(EngineBlocked, match='refusing overwrite'):
        jc.run(study, project, tmp_path)
    assert (tmp_path / 'josephson_ports.json').read_text() == 'DO NOT REPLACE'


def test_cross_engine_claims_do_not_turn_independent_inputs_into_em_mapping():
    study, project = two_port_case()
    study['inputs']['em_port_mapping'] = {'verified': True}
    with pytest.raises(EngineBlocked, match='exactly'):
        jc._validate(study, project)
    qubit = fresh_project('A16 edge', 'transmon')
    inputs = {'source': 'josephson_circuits', 'model': 'Transmon', 'levels': 3,
              'parameters': {'EJ': 15., 'EC': .25, 'ng': 0., 'ncut': 10},
              'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'}}
    with pytest.raises(EngineBlocked, match='trusted A01 verified'):
        scq._spec(inputs, qubit)


def two_port_case(pumped=False):
    # Declarative saved circuit, not a custom solver or synthetic S-parameter.
    sch = {
        'nodes': ['0', 'in', 'tank', 'out'],
        'elements': [
            {'id': 'Cin', 'kind': 'C', 'nodes': ['in', 'tank'], 'value': 1e-13, 'unit': 'F'},
            {'id': 'Cout', 'kind': 'C', 'nodes': ['tank', 'out'], 'value': 1e-13, 'unit': 'F'},
            {'id': 'Ltank', 'kind': 'L', 'nodes': ['tank', '0'], 'value': 1e-8, 'unit': 'H'},
        ],
        'ports': [
            {'number': 2, 'node': 'out', 'reference_impedance_ohm': 50.0},
            {'number': 1, 'node': 'in', 'reference_impedance_ohm': 50.0},
        ],
    }
    kind = 'rf_harmonic_balance' if pumped else 'rf_linear'
    if pumped:
        sch['elements'].append({'id': 'LjSQUID', 'kind': 'Lj',
                                'nodes': ['tank', '0'], 'value': 1e-9, 'unit': 'H'})
    opts = {'schematic_sha256': jc._hash(sch), 'frequencies_hz': [4e9, 5e9, 6e9]}
    if pumped:
        opts['pump'] = {'frequency_hz': 4.75e9, 'port': 1, 'current_a': 1e-9,
                        'pump_harmonics': 2, 'modulation_harmonics': 1}
    study = {'id': 'A16-RF', 'engine': 'josephson_circuits', 'kind': kind, 'inputs': opts}
    return study, {'schematic': sch}


def require_julia():
    julia = shutil.which('julia')
    if not julia:
        pytest.skip('BLOCKED: native Julia executable unavailable, no Josephson solve attempted')
    check = subprocess.run([julia, '--startup-file=no', '-e',
        'print(Base.find_package("JosephsonCircuits") === nothing ? "MISSING" : "PRESENT")'],
        text=True, capture_output=True, timeout=25, check=False)
    if check.returncode == 0 and check.stdout.strip() == 'MISSING':
        pytest.skip('BLOCKED: JosephsonCircuits.jl not installed, no native solve attempted')
    assert check.returncode == 0 and check.stdout.strip() == 'PRESENT', (
        f'Installed Julia package probe failed (exit={check.returncode}): {check.stderr[-700:]}')


@pytest.mark.parametrize('pumped', [False, True], ids=['two_port_resonator', 'pumped_nonlinear_candidate'])
def test_real_native_rf_benchmarks_only_when_installed(tmp_path, pumped):
    require_julia()
    study, project = two_port_case(pumped)
    result = jc.run(study, project, tmp_path)
    sidecar = json.loads((tmp_path / 'josephson_ports.json').read_text())
    assert result['engine_version'] == sidecar['native_engine_version']
    assert sidecar['port_order'] == [1, 2]
    assert [p['reference_impedance_ohm'] for p in sidecar['ports']] == [50., 50.]
    assert sidecar['observable']['unit'] == '1'
    assert sidecar['frequency_points_hz'] == [4e9, 5e9, 6e9]
    assert sidecar['scientific_status'] == 'review_required'
    assert sidecar['cross_engine_mapping']['status'] == 'blocked'
    assert len(sidecar['artifact_sha256']) == 6
    assert sidecar['native_process_exit_code'] == 0
    assert len(sidecar['native_version_pin']['manifest_sha256']) == 64
    assert len(sidecar['native_version_pin']['josephson_tree_sha1']) == 40
    assert sidecar['native_linear_port_screen']['status'] == (
        'bounded_linear_port_screen_passed' if not pumped else 'not_applicable_pumped_signal_only')
    assert sidecar['native_process_wall_seconds'] >= sidecar['native_elapsed_seconds']
    for filename, sha in sidecar['artifact_sha256'].items():
        assert hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest() == sha
    rows = (tmp_path / 'josephson_native_sparameters.tsv').read_text().splitlines()
    assert len(rows) == 1 + 3 * 2 * 2
    values = [complex(float(v[3]), float(v[4])) for line in rows[1:]
              if (v := line.split('\t'))]
    assert any(z != 0 for z in values), 'Unexpected all-zero native two-port response'
    if not pumped:
        # This fixture is symmetric, linear, and passive. These are physically
        # independent checks on native outputs, not an alternate RF solver.
        for k in range(3):
            s11, s12, s21, s22 = values[4*k:4*k+4]
            assert abs(s12 - s21) < 1e-5, 'Native reciprocal-network check failed'
            assert abs(s11 - s22) < 1e-5, 'Native symmetric-port check failed'
            assert max(map(abs, (s11, s12, s21, s22))) <= 1.00001, 'Native passive RF gain check failed'
    if pumped:
        assert sidecar['convergence_evidence'] == 'hbsolve_returned_no_iteration_log'
        assert 'Pumped idler channels not exported' in sidecar['limitations']
    else:
        assert sidecar['convergence_evidence'] == 'linear_solve_returned'
    print('NATIVE A16 RF', result['engine_version'], sidecar['native_julia_version'],
          'study=', study['kind'], 'elapsed_seconds=', sidecar['native_elapsed_seconds'])


def test_real_native_fluxonium_sweep_only_when_installed(tmp_path):
    if util.find_spec('scqubits') is None:
        pytest.skip('BLOCKED: native scqubits not installed; no flux spectrum computed')
    project = fresh_project('A16 Fluxonium', 'fluxonium')
    inputs = {'source': 'independent', 'model': 'Fluxonium', 'levels': 3,
              'parameters': {'EJ': 8., 'EC': 2., 'EL': .5, 'flux': .5, 'cutoff': 20,
                             'truncated_dim': 5},
              'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'EL': 'GHz',
                                  'flux': 'Phi0', 'cutoff': '1', 'truncated_dim': '1'},
              'sweep': {'subsystem': 'primary', 'parameter': 'flux',
                        'values': [0., .2, .5], 'unit': 'Phi0'}}
    result = scq.run({'id': 'A16-flux', 'engine': 'scqubits',
                      'kind': 'quantum_spectrum', 'inputs': inputs}, project, tmp_path)
    data = json.loads((tmp_path / 'spectrum.json').read_text())
    assert data['axis'] == {'parameter': 'flux', 'subsystem': 'primary',
                            'unit': 'Phi0', 'values': [0., .2, .5]}
    assert len(data['energy_table']) == 3
    assert data['energy_table'][0] != data['energy_table'][2], 'Flux sweep unexpectedly unchanged'
    assert data['scientific_status'] == 'review_required'
    assert data['energy_unit'] == 'GHz'
    assert data['convergence']['status'] == 'not_checked'
    assert result['engine_version'] == data['engine_version'] == metadata.version('scqubits')
    snapshot = json.loads((tmp_path / 'input_snapshot.json').read_text())
    assert snapshot['cross_engine_mapping']['status'] == 'blocked'
    assert snapshot['unit_convention'] == 'E/h in GHz'
    print('NATIVE A16 fluxonium', result['engine_version'], 'sweep_points=', 3)


def test_real_native_asymmetric_readout_ports_only_when_installed(tmp_path):
    """Native-only lossy readout/resonator with nonidentical ohmic references.

    This checks the real engine's typed port mapping, passivity and reciprocal
    power-wave normalization; it does not fit an EM port, material or mode.
    """
    require_julia()
    study, project = two_port_case()
    project['schematic']['ports'][0]['reference_impedance_ohm'] = 75.0
    project['schematic']['elements'].append({
        'id': 'Rdamping', 'kind': 'R', 'nodes': ['tank', '0'],
        'value': 500.0, 'unit': 'ohm',
    })
    study['inputs']['schematic_sha256'] = jc._hash(project['schematic'])
    assert jc._validate(study, project)[3] == [(1, 'in', 50.0), (2, 'out', 75.0)]
    result = jc.run(study, project, tmp_path)
    sidecar = json.loads((tmp_path / 'josephson_ports.json').read_text())
    assert result['scientific_status'] == sidecar['scientific_status'] == 'review_required'
    assert sidecar['native_process_exit_code'] == 0
    assert sidecar['port_order'] == [1, 2]
    assert [p['reference_impedance_ohm'] for p in sidecar['ports']] == [50.0, 75.0]
    assert sidecar['cross_engine_mapping']['status'] == 'blocked'
    rows = (tmp_path / 'josephson_native_sparameters.tsv').read_text().splitlines()[1:]
    values = [complex(float(s[3]), float(s[4])) for r in rows if (s := r.split('\t'))]
    assert len(values) == 12
    for k in range(3):
        s11, s12, s21, s22 = values[k*4:(k+1)*4]
        assert abs(s12 - s21) < 1e-5, 'Native readout network reciprocity check failed'
        assert max(map(abs, (s11, s12, s21, s22))) <= 1.00001, 'Native passive readout check failed'
    print('NATIVE A16 READOUT', sidecar['native_engine_version'],
          sidecar['native_julia_version'], 'exit=', sidecar['native_process_exit_code'])


def test_real_native_fluxonium_basis_scan_only_when_installed(tmp_path):
    """Native scqubits two-basis flux sweep; no eigenstate overlap is claimed."""
    if util.find_spec('scqubits') is None:
        pytest.skip('BLOCKED: native scqubits unavailable; no basis scan computed')
    study = {'id': 'A16-flux-convergence', 'engine': 'scqubits',
             'kind': 'quantum_spectrum',
             'inputs': {'source': 'independent', 'model': 'Fluxonium', 'levels': 3,
                        'parameters': {'EJ': 8., 'EC': 2., 'EL': .5, 'flux': .5,
                                       'cutoff': 20, 'truncated_dim': 5},
                        'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'EL': 'GHz',
                                            'flux': 'Phi0', 'cutoff': '1', 'truncated_dim': '1'},
                        'sweep': {'subsystem': 'primary', 'parameter': 'flux',
                                  'values': [0.4, 0.5, 0.6], 'unit': 'Phi0'},
                        'convergence': {'enabled': True, 'tolerance_GHz': 0.5,
                                        'basis_increment': 2}}}
    project = fresh_project('A16 Fluxonium basis audit', 'fluxonium')
    result = scq.run(study, project, tmp_path)
    spectrum = json.loads((tmp_path / 'spectrum.json').read_text())
    assert spectrum['convergence']['status'] == 'checked_passed'
    assert spectrum['convergence']['checked_points'] == 3
    assert all(p['max_delta_GHz'] <= .5 for p in spectrum['convergence']['points'])
    assert 'no eigenstate-overlap identity' in spectrum['convergence']['scientific_scope']
    assert result['scientific_status'] == 'review_required'
    print('NATIVE A16 FLUX BASIS', result['engine_version'],
          'points=', spectrum['convergence']['checked_points'])
