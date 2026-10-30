"""Genuine external scqubits calls only; explicitly skipped if unavailable."""
import json
import time

import pytest
from sqe_studio.adapters import scqubits_adapter as a
from sqe_studio.contracts import fresh_project
from test_scqubits_validation import composite, fluxonium, transmon


def native():
    return pytest.importorskip('scqubits', reason='scqubits not installed; no synthetic solver fallback')


def _real_run(tmp_path, inp):
    scq = native()
    assert scq.get_units() in ('GHz', 'MHz', 'kHz', 'Hz')
    model = fresh_project('Native Check', 'transmon')
    start = time.perf_counter()
    record = a.run({'id': 'native_test', 'engine': 'scqubits', 'kind': 'spectrum',
                    'inputs': inp}, model, tmp_path)
    elapsed = time.perf_counter() - start
    spectrum = json.loads((tmp_path / 'spectrum.json').read_text())
    assert record['engine_version'] and record['scientific_status'] == 'review_required'
    assert spectrum['energy_unit'] == 'GHz'
    assert len(spectrum['energy_table']) == (len(inp['sweep']['values']) if 'sweep' in inp else 1)
    assert len(spectrum['energy_table'][0]) == inp['levels']
    assert all((tmp_path / f).is_file() for f in record['native_files'])
    assert json.loads((tmp_path / 'input_snapshot.json').read_text())['input_sha256'] == a._sha(inp)
    print('ACTUAL scqubits version', record['engine_version'], 'model', inp['model'],
          'basis', spectrum['basis'], 'runtime_s', round(elapsed, 6),
          'convergence', spectrum['convergence']['status'], flush=True)
    return spectrum


def test_real_transmon(tmp_path):
    inp = transmon()
    inp['convergence'] = {'enabled': True, 'tolerance_GHz': .1, 'basis_increment': 3}
    spectrum = _real_run(tmp_path, inp)
    assert spectrum['convergence']['status'] == 'checked_passed'


def test_real_fluxonium(tmp_path):
    _real_run(tmp_path, fluxonium())


def test_real_native_flux_sweep(tmp_path):
    inp = fluxonium()
    inp['sweep'] = {'subsystem': 'primary', 'parameter': 'flux',
                    'values': [0.4, 0.5, 0.6], 'unit': 'Phi0'}
    spectrum = _real_run(tmp_path, inp)
    assert spectrum['axis']['values'] == [0.4, 0.5, 0.6]
    assert len(json.loads((tmp_path / 'series.json').read_text())['series']) == 2 * inp['levels'] - 1


def test_real_native_composite_coupling(tmp_path):
    inp = composite()
    spectrum = _real_run(tmp_path, inp)
    record = json.loads((tmp_path / 'coupling.json').read_text())
    assert record['artifact_type'] == 'scqubits.coupling'
    assert len(record['uncoupled_native_energy_table_GHz'][0]) == inp['levels']
    assert spectrum['basis'][0]['truncated_dim'] == 4
