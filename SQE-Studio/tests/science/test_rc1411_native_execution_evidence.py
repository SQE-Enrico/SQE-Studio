"""RC14.11 A16 preflight/data-validator fixtures (NOT native solver runs)."""

import pytest

from sqe_studio.adapters import scqubits_adapter as scq
from sqe_studio.adapters import josephson_adapter as jc
from sqe_studio.adapters.base import EngineFailure, EngineBlocked


def _cutoff_fixtures():
    samples = {}
    for model, base_cutoff in [('transmon', 12), ('fluxonium', 24)]:
        for step in (0, 2):
            samples[f'{model}_cutoff_plus_{step}'] = {
                'cutoff': base_cutoff + step,
                'units': {'energies': 'E/h GHz', 'sweep': '2e' if model == 'transmon' else 'Phi0'},
                'sweep_values': [0., .5, 1.],
                'sweep_transitions_GHz': [[3.0 + step * 0.01, 5.0 + step * 0.01]] * 3,
            }
    return samples


def test_cutoff_start_comparison_is_not_a_scientific_convergence_certificate():
    fixture = _cutoff_fixtures()
    result = scq._b08_cutoff_start_comparison(fixture)
    assert set(result) == {'transmon', 'fluxonium'}
    assert all(row['max_delta_GHz'] == pytest.approx(0.02) for row in result.values())
    assert all(row['qualification'].startswith('BLOCKED_') for row in result.values())
    assert all('NOT_PROOF' in row['numerical_screen'] for row in result.values())


def test_cutoff_start_large_disagreement_is_blocked_not_pass():
    fixture = _cutoff_fixtures()
    fixture['transmon_cutoff_plus_2']['sweep_transitions_GHz'][0][0] = 4.0
    assert scq._b08_cutoff_start_comparison(fixture)['transmon']['numerical_screen'] == \
        'BLOCKED_CUTOFF_START_DISAGREEMENT'


@pytest.mark.parametrize('fault', ['grid', 'unit', 'cutoff', 'transition_count', 'point_count', 'nonfinite'])
def test_cutoff_start_comparison_rejects_mismatched_native_structure(fault):
    fixture = _cutoff_fixtures()
    row = fixture['fluxonium_cutoff_plus_2']
    if fault == 'grid':
        row['sweep_values'] = [0., .4, 1.]
    elif fault == 'unit':
        row['units'] = {'energies': 'E/h GHz', 'sweep': 'GHz'}
    elif fault == 'cutoff':
        row['cutoff'] = 25
    elif fault == 'transition_count':
        row['sweep_transitions_GHz'][0] = [3.0]
    elif fault == 'point_count':
        row['sweep_transitions_GHz'] = row['sweep_transitions_GHz'][:2]
    elif fault == 'nonfinite':
        row['sweep_transitions_GHz'][0][0] = float('nan')
    with pytest.raises((EngineFailure, EngineBlocked)):
        scq._b08_cutoff_start_comparison(fixture)


def _rf_fixture():
    return {
        label: {'engine_version': '1.2.3', 'julia_version': '1.11.0',
                'native_version_pin': {'manifest_sha256': 'a' * 64, 'josephson_tree_sha1': 'b' * 40},
                'schematic_sha256': 'c' * 64, 'frequency_hz': [4.5e9, 5e9]}
        for label in ('pump_off', 'pump_harmonics_2', 'pump_harmonics_3')
    }


def test_cross_job_native_identity_gate_accepts_matching_provenance_fixture_only():
    assert jc._benchmark_rf_cross_job_identity(_rf_fixture(), 'B09') is None
    assert jc._benchmark_rf_cross_job_identity({'pump_off': _rf_fixture()['pump_off']}, 'B05') is None


@pytest.mark.parametrize('fault', ['missing', 'version', 'manifest', 'tree', 'schematic', 'frequency'])
def test_cross_job_identity_gate_rejects_mixed_native_provenance(fault):
    rows = _rf_fixture()
    victim = rows['pump_harmonics_3']
    if fault == 'missing':
        del rows['pump_harmonics_3']
    elif fault == 'version':
        victim['julia_version'] = '1.12.0'
    elif fault == 'manifest':
        victim['native_version_pin']['manifest_sha256'] = '0' * 64
    elif fault == 'tree':
        victim['native_version_pin']['josephson_tree_sha1'] = 'f' * 40
    elif fault == 'schematic':
        victim['schematic_sha256'] = 'd' * 64
    elif fault == 'frequency':
        victim['frequency_hz'] = [4.5e9, 5.1e9]
    with pytest.raises(EngineFailure, match='native subjobs|identity changed'):
        jc._benchmark_rf_cross_job_identity(rows, 'B09')
