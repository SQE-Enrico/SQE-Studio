"""A03 contract/preflight tests. NO mocked fixture is claimed as a native solve."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters import sqdmetal_palace_adapter as em
from sqe_studio.contracts import fresh_project, validate_project


def physical_case(kind='eigenmode'):
    project = fresh_project('A03 test', 'transmon')
    project['process'] = {
        'source': 'reviewed', 'rules': {}, 'stack': [
            {'role': 'substrate', 'material': 'silicon', 'thickness_um': 500,
             'relative_permittivity': 11.7, 'loss_tangent': 0.0},
            {'role': 'metal', 'material': 'aluminium', 'layer': 1,
             'thickness_nm': 100, 'em_model': 'PEC'},
            {'role': 'superstrate', 'material': 'vacuum', 'height_um': 500,
             'relative_permittivity': 1.0, 'loss_tangent': 0.0},
        ]}
    ports = [{'index': 1, 'kind': 'junction', 'component': 'Q1', 'L_nH': 10,
              'C_fF': 1}]
    solver = {'order': 2, 'tolerance': 1e-8, 'max_iterations': 100,
              'num_cpus': 2, 'start_hz': 5e9, 'modes': 2}
    if kind == 'capacitance':
        ports = [{'index': 1, 'kind': 'conductor', 'component': 'Q1',
                  'native_attributes': [17]}]
        solver = {k: solver[k] for k in ('order', 'tolerance', 'max_iterations', 'num_cpus')}
    if kind == 'sparameters':
        project['layout']['components'].append({'kind': 'LaunchpadWirebond', 'name': 'LP1',
                                                 'x_mm': 1, 'y_mm': 0})
        ports = [{'index': 1, 'kind': 'cpw_launcher', 'component': 'LP1',
                  'length_um': 20, 'impedance_ohm': 50}]
        solver = {k: solver[k] for k in ('order', 'tolerance', 'max_iterations', 'num_cpus')}
        solver.update(frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    study = {'id': 'EM1', 'engine': 'sqdmetal_palace', 'kind': kind,
             'inputs': {'em': {
                 'ground': {'kind': 'qdesign_ground_plane', 'layer': 1, 'verified': True},
                 'boundaries': {'x_neg_um': 200, 'x_pos_um': 200, 'y_neg_um': 200,
                                'y_pos_um': 200, 'z_neg_um': 0, 'z_pos_um': 500,
                                'farfield': 'ground' if kind == 'capacitance' else 'pec'},
                 'ports': ports,
                 'mesh': {'min_um': 10, 'max_um': 100,
                          'refinement_levels': [0, 1, 2], 'relative_tolerance': 0.02},
                 'execution': 'deck_only', 'solver': solver,
             }}}
    project['studies'] = [study]
    validate_project(project)
    return study, project


@pytest.mark.parametrize('kind', ['capacitance', 'eigenmode', 'sparameters'])
def test_explicit_physical_study_preflight(kind):
    study, project = physical_case(kind)
    assert em.preflight(study, project) is study['inputs']['em']


@pytest.mark.parametrize('change, phrase', [
    (lambda s, p: p['process'].update(stack=[]), 'material stack'),
    (lambda s, p: p['process'].update(source='unverified'), 'reviewed'),
    (lambda s, p: p['process']['stack'][0].update(thickness_um=400), 'thickness'),
    (lambda s, p: p['process']['stack'][1].update(em_model='unknown'), 'PEC'),
    (lambda s, p: p['process']['stack'][2].update(material='sio2'), 'vacuum'),
    (lambda s, p: s['inputs']['em'].pop('ground'), 'ground'),
    (lambda s, p: s['inputs']['em']['ground'].update(verified=False), 'ground'),
    (lambda s, p: s['inputs']['em'].pop('ports'), 'ports'),
    (lambda s, p: s['inputs']['em'].update(ports=[]), 'ports'),
    (lambda s, p: s['inputs']['em'].pop('boundaries'), 'boundaries'),
    (lambda s, p: s['inputs']['em']['boundaries'].update(farfield='absorbing'), 'farfield'),
    (lambda s, p: s['inputs']['em']['boundaries'].update(z_pos_um=20), 'superstrate'),
    (lambda s, p: s['inputs']['em']['mesh'].update(refinement_levels=[0]), 'refinement'),
    (lambda s, p: s['inputs']['em']['mesh'].update(min_um=0), 'mesh minimum'),
    (lambda s, p: s['inputs']['em']['ports'][0].update(index=2), 'numbering'),
    (lambda s, p: s['inputs']['em']['ports'][0].update(component='Bad'), 'missing QDesign'),
    (lambda s, p: s['inputs'].update(python='os'), 'unexpected input'),
])
def test_fail_closed_missing_or_inconsistent_inputs(change, phrase, tmp_path):
    study, project = physical_case()
    change(study, project)
    with pytest.raises(EngineBlocked, match=phrase):
        em.run(study, project, tmp_path / 'must-not-exist')
    assert not (tmp_path / 'must-not-exist').exists()


def test_no_native_module_no_output(tmp_path, monkeypatch):
    # Exercise the missing-dependency branch even on a workstation where
    # SQDMetal is installed. Otherwise the test can proceed into native mesh
    # / material checks, producing an unrelated failure.
    study, project = physical_case()
    folder = tmp_path / 'no-output'
    def missing_native_module(module, label):
        raise EngineBlocked(f'{label} native module deliberately unavailable for test')
    monkeypatch.setattr(em, 'require_module', missing_native_module)
    with pytest.raises(EngineBlocked, match='SQDMetal'):
        em.run(study, project, folder)
    assert not folder.exists()


def test_native_imports_reject_missing_a02_builder(monkeypatch):
    from sqe_studio.adapters import quantum_metal_adapter
    monkeypatch.setattr(em, 'require_module', lambda *args: None)
    monkeypatch.delattr(quantum_metal_adapter, 'build_qdesign')
    with pytest.raises(EngineBlocked, match='A02 native QDesign builder'):
        em._native_imports()


def test_a02_a03_qdesign_bridge_exact_layout_and_identity(monkeypatch):
    from sqe_studio.adapters import quantum_metal_adapter as a02
    from hashlib import sha256
    study, project = physical_case()
    layout = project['layout']
    expected = sha256(json.dumps(layout, sort_keys=True, separators=(',', ':'),
                                 allow_nan=False).encode()).hexdigest()
    class NativeDesign:
        components = {'Q1': object()}
        qgeometry = object()
    native = NativeDesign()
    calls = []
    def build(received):
        calls.append(received)
        return a02.QDesignBuild(native, expected, ('Q1',), (), (), (1,), (), ())
    monkeypatch.setattr(a02, 'build_qdesign', build)
    assert em._checked_qdesign(project, a02) is native
    assert calls == [layout] and calls[0] is not project
    monkeypatch.setattr(a02, 'build_qdesign', lambda _: a02.QDesignBuild(
        native, '0'*64, ('Q1',), (), (), (1,), (), ()))
    with pytest.raises(EngineBlocked, match='digest'):
        em._checked_qdesign(project, a02)
    monkeypatch.setattr(a02, 'build_qdesign', lambda _: a02.QDesignBuild(
        native, expected, ('WRONG',), (), (), (1,), (), ()))
    with pytest.raises(EngineBlocked, match='component identity'):
        em._checked_qdesign(project, a02)


def test_invalid_kind_cannot_reach_native_module(tmp_path):
    study, project = physical_case()
    study['kind'] = 'fake_fem'
    with pytest.raises(EngineBlocked, match='Unsupported EM kind'):
        em.run(study, project, tmp_path / 'out')


def test_driven_frequency_grid_and_excitation_fail_closed():
    study, project = physical_case('sparameters')
    study['inputs']['em']['solver']['frequencies_hz'] = [4e9, 4.2e9, 5e9]
    with pytest.raises(EngineBlocked, match='uniform'):
        em.preflight(study, project)
    study['inputs']['em']['solver']['frequencies_hz'] = [4e9, 4.5e9, 5e9]
    study['inputs']['em']['solver']['excited_port'] = 2
    with pytest.raises(EngineBlocked, match='excitation'):
        em.preflight(study, project)


def test_capacitance_terminal_native_tag_required():
    study, project = physical_case('capacitance')
    study['inputs']['em']['ports'][0]['native_attributes'] = []
    with pytest.raises(EngineBlocked, match='physical tags'):
        em.preflight(study, project)


def test_gmsh_deck_validation_rejects_missing_native_boundaries():
    study, project = physical_case('eigenmode')
    deck = {
        'Problem': {'Type': 'Eigenmode', 'Output': 'outputFiles'},
        'Model': {'L0': 1e-3, 'Mesh': 'sqe_em.msh'},
        'Solver': {'Order': 2, 'Eigenmode': {'N': 2, 'Target': 5.0}},
        'Domains': {'Materials': [
            {'Attributes': [2], 'Permittivity': 1.0, 'LossTan': 0.0},
            {'Attributes': [1], 'Permittivity': 11.7, 'LossTan': 0.0},
        ]},
        'Boundaries': {'PEC': {'Attributes': [5]}, 'WavePort': [],
                       'LumpedPort': [{'Index': 1, 'Attributes': [6]}]},
    }
    em._validate_deck(deck, study['inputs']['em'],
                      {'kind': 'eigenmode', '_stack_for_validation': project['process']['stack']},
                      {1, 2}, {5, 6})
    broken = copy.deepcopy(deck)
    broken['Boundaries']['LumpedPort'][0]['Attributes'] = [99]
    with pytest.raises(EngineBlocked, match='physical attributes'):
        em._validate_deck(broken, study['inputs']['em'],
                          {'kind': 'eigenmode', '_stack_for_validation': project['process']['stack']},
                          {1, 2}, {5, 6})
    broken = copy.deepcopy(deck)
    broken['Domains']['Materials'][1]['Permittivity'] = 12.0
    with pytest.raises(EngineBlocked, match='permittivity'):
        em._validate_deck(broken, study['inputs']['em'],
                          {'kind': 'eigenmode', '_stack_for_validation': project['process']['stack']},
                          {1, 2}, {5, 6})


def test_native_csv_axis_parser_is_not_a_solver(tmp_path):
    path = tmp_path / 'port-S.csv'
    path.write_text('Frequency (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg)\n'
                    '4.0,-1.0,0\n4.5,-2.0,2\n5.0,-3.0,4\n')
    assert em._csv_frequency(path, [4e9, 4.5e9, 5e9]) == [4e9, 4.5e9, 5e9]
    with pytest.raises(EngineBlocked, match='axis'):
        em._csv_frequency(path, [4e9, 4.5e9, 6e9])
    path.write_text('Frequency,-1\n4,-1\n')
    with pytest.raises(EngineBlocked, match='ambiguous'):
        em._csv_frequency(path, [4e9])


def test_palace_binary_readiness_requires_operator_path(monkeypatch):
    monkeypatch.setenv('SQE_PALACE_BACKEND', 'native')
    monkeypatch.delenv('SQE_PALACE_BINARY', raising=False)
    with pytest.raises(EngineBlocked, match='SQE_PALACE_BINARY'):
        em._palace_readiness()


def test_wsl_readiness_refuses_non_windows(monkeypatch):
    monkeypatch.setenv('SQE_PALACE_BACKEND', 'wsl')
    monkeypatch.setenv('SQE_PALACE_WSL_BINARY', '/opt/palace/bin/palace')
    monkeypatch.setattr(em.platform, 'system', lambda: 'Linux')
    with pytest.raises(EngineBlocked, match='Windows'):
        em._palace_readiness()
