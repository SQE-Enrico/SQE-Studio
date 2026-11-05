"""RC14.8 A16 admission/interop checks, not substitute native solver results.

Test doubles here exercise only Python control flow and artifact admission; they
are never presented as scqubits eigenvalues or Josephson solver evidence.
"""
from __future__ import annotations

import json
from contextlib import nullcontext
import sys
from types import SimpleNamespace

import pytest

from sqe_studio.adapters import josephson_adapter as jc, scqubits_adapter as scq
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.contracts import fresh_project


def transmon():
    return {'model': 'Transmon', 'levels': 3, 'source': 'independent',
            'parameters': {'EJ': 15., 'EC': .25, 'ng': 0., 'ncut': 10},
            'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'}}


def composite():
    q = transmon()
    p = dict(q['parameters'], truncated_dim=4)
    u = dict(q['parameter_units'], truncated_dim='1')
    return {'model': 'Composite', 'levels': 4, 'source': 'independent',
            'subsystems': [
                {'id': 'q1', 'model': 'Transmon', 'parameters': p, 'parameter_units': u},
                {'id': 'q2', 'model': 'Transmon', 'parameters': p, 'parameter_units': u},
            ],
            'interactions': [{'left': 'q1', 'right': 'q2',
                              'operator_left': 'n_operator', 'operator_right': 'n_operator',
                              'g': .025, 'unit': 'GHz'}]}


def make_case():
    schematic = {'nodes': ['0', 'in', 'tank'],
                 'elements': [
                     {'id': 'Ccoupling', 'kind': 'C', 'nodes': ['in', 'tank'],
                      'value': 1e-13, 'unit': 'F'},
                     {'id': 'Ltank', 'kind': 'L', 'nodes': ['tank', '0'],
                      'value': 1e-8, 'unit': 'H'}],
                 'ports': [{'number': 1, 'node': 'in', 'reference_impedance_ohm': 50.0}]}
    study = {'id': 'A16-port', 'engine': 'josephson_circuits', 'kind': 'rf_linear',
             'inputs': {'schematic_sha256': jc._hash(schematic), 'frequencies_hz': [5e9]}}
    return study, {'schematic': schematic}


def spectrum_study(inputs=None):
    return {'id': 'q', 'engine': 'scqubits', 'kind': 'spectrum',
            'inputs': inputs if inputs is not None else transmon()}


@pytest.mark.parametrize('engine,kind', [
    ('josephson_circuits', 'spectrum'),
    ('scqubits', 'rf_harmonic_balance'),
    ('scqubits', 'rf_linear'),
    ('unknown_engine', 'quantum_spectrum'),
    ('scqubits', 'script'),
])
def test_wrong_quantum_study_never_runs_as_scqubits(tmp_path, monkeypatch, engine, kind):
    monkeypatch.setattr(scq, 'require_module', lambda *args: pytest.fail('Wrong study reached native probe'))
    study = spectrum_study()
    study.update(engine=engine, kind=kind)
    with pytest.raises(EngineBlocked, match='requires scqubits engine'):
        scq.run(study, fresh_project('SQE A16', 'transmon'), tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('filename', ['spectrum.json', 'coupling.json', 'input_snapshot.json', 'series.json'])
def test_scqubits_refuses_preexisting_scientific_artifacts_without_solver(tmp_path, monkeypatch, filename):
    existing = tmp_path / filename
    existing.write_text('DO NOT REPLACE', encoding='utf-8')
    monkeypatch.setattr(scq, 'require_module', lambda *args: pytest.fail('Collision reached native probe'))
    with pytest.raises(EngineBlocked, match='refusing overwrite/replay'):
        scq.run(spectrum_study(), fresh_project('SQE A16', 'transmon'), tmp_path)
    assert existing.read_text(encoding='utf-8') == 'DO NOT REPLACE'
    assert [p.name for p in tmp_path.iterdir()] == [filename]


@pytest.mark.parametrize('adapter,filename', [
    ('scqubits', 'spectrum.json'),
    ('josephson', 'josephson_request.tsv'),
])
def test_dangling_symlink_cannot_redirect_native_writes(tmp_path, monkeypatch, adapter, filename):
    dst = tmp_path / 'outside_parent' / 'missing.txt'
    link = tmp_path / filename
    try:
        link.symlink_to(dst)
    except (OSError, NotImplementedError) as exc:
        pytest.skip('Symlink permission unavailable: ' + str(exc))
    assert link.is_symlink() and not link.exists()
    if adapter == 'scqubits':
        monkeypatch.setattr(scq, 'require_module', lambda *args: pytest.fail('Collision reached native probe'))
        with pytest.raises(EngineBlocked, match='refusing overwrite/replay'):
            scq.run(spectrum_study(), fresh_project('SQE A16', 'transmon'), tmp_path)
    else:
        monkeypatch.setattr(jc.shutil, 'which', lambda _: '/declared/julia')
        study, project = make_case()
        with pytest.raises(EngineBlocked, match='refusing overwrite/replay'):
            jc.run(study, project, tmp_path)
    assert link.is_symlink() and not dst.exists()


def test_composite_nonfinite_coupling_never_writes_provisional_spectrum(tmp_path, monkeypatch):
    """Control-flow spy only; no fabricated solver success or native artifact."""
    study = spectrum_study(composite())
    project = fresh_project('A16 Coupled', 'transmon')
    # This spy bypasses the installed native dependency and returns finite
    # shapes specifically chosen to overflow *only* coupled-minus-uncoupled.
    # Ground-referenced transitions are finite for both independent rows.
    def native_shape_spy(_native, _spec):
        return ([[-1e308, -9e307, -8e307, -7e307]],
                [[1e308, 1.1e308, 1.2e308, 1.3e308]], [])
    fake_engine = SimpleNamespace(set_units=lambda units: None, get_units=lambda: 'GHz')
    monkeypatch.setitem(sys.modules, 'scqubits', fake_engine)
    monkeypatch.setitem(sys.modules, 'scqubits.utils', SimpleNamespace(spectrum_utils=object()))
    monkeypatch.setattr(scq, 'require_module', lambda *args: None)
    monkeypatch.setattr(scq.metadata, 'version', lambda _: scq.SCQUBITS_NUMERICAL_PIN)
    monkeypatch.setattr(scq, '_scqubits_sparse_matrix_boundary', lambda _: nullcontext())
    monkeypatch.setattr(scq, '_execute', native_shape_spy)
    with pytest.raises(EngineBlocked, match='dressed-minus-uncoupled energy is nonfinite'):
        scq.run(study, project, tmp_path)
    assert list(tmp_path.iterdir()) == [], 'Provisional results must never be mistaken for completed native data'


def test_result_writer_requires_exclusive_creation(tmp_path):
    path = tmp_path / 'spectrum.json'
    scq._write(path, {'scope': 'admission-format-test-only'})
    with pytest.raises(FileExistsError):
        scq._write(path, {'scope': 'attempted-replacement'})
    assert json.loads(path.read_text()) == {'scope': 'admission-format-test-only'}


@pytest.mark.parametrize('mutation', [
    lambda rows: rows[:-1],                          # truncated response
    lambda rows: rows + [rows[-1]],                 # extra native response
    lambda rows: [rows[0]] + [rows[2], rows[1]],   # reordered port rows
    lambda rows: [rows[0], rows[1].replace('5e9', '5.1e9'), rows[2]],
    lambda rows: [rows[0], rows[1].replace('0.2', 'nan'), rows[2]],
    lambda rows: [rows[0], rows[1].replace('0.2', 'inf'), rows[2]],
])
def test_native_scattering_parser_rejects_corrupt_records(tmp_path, mutation):
    """Parser-only wire fixture: not a Julia solve or claimed S measurement."""
    from sqe_studio.adapters.base import EngineFailure
    path = tmp_path / 'parser_only.tsv'
    rows = ['frequency_hz\toutput_port\tinput_port\treal\timag',
            '5e9\t1\t1\t0.2\t0.1',
            '5e9\t1\t2\t-0.2\t0.0']
    path.write_text('\n'.join(mutation(rows)) + '\n', encoding='utf-8')
    with pytest.raises(EngineFailure, match='S-parameter artifact rejected'):
        jc._check_s(path, [5e9], [1, 2])


def test_valid_bounded_scattering_parser_preserves_complex_numbers(tmp_path):
    """Structural parser-only integrity case, not physics engine output."""
    path = tmp_path / 'parser_only.tsv'
    path.write_text('frequency_hz\toutput_port\tinput_port\treal\timag\n'
                    '5e9\t1\t1\t0.2\t0.1\n'
                    '5e9\t1\t2\t-0.2\t0.0\n'
                    '5e9\t2\t1\t-0.2\t0.0\n'
                    '5e9\t2\t2\t0.2\t0.1\n', encoding='utf-8')
    assert jc._check_s(path, [5e9], [1, 2]) is None
