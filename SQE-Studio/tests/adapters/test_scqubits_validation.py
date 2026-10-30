"""A04 preflight checks: no native outputs and no mocks of solver evidence."""
import copy
import hashlib
import json

import pytest

from sqe_studio.adapters import scqubits_adapter as a
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.contracts import fresh_project


def project():
    return fresh_project('A04 Circuit', 'transmon')


def transmon():
    return {'model': 'Transmon', 'parameters': {'EJ': 15., 'EC': 0.25,
            'ng': 0., 'ncut': 10}, 'levels': 3, 'source': 'independent',
            'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'}}


def fluxonium():
    return {'model': 'Fluxonium', 'parameters': {'EJ': 8., 'EC': 2., 'EL': .5,
            'flux': .5, 'cutoff': 20, 'truncated_dim': 5}, 'levels': 3,
            'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'EL': 'GHz',
                                'flux': 'Phi0', 'cutoff': '1', 'truncated_dim': '1'}}


def assert_blocks(inputs, pattern):
    with pytest.raises(EngineBlocked, match=pattern):
        a._spec(inputs, project())


@pytest.mark.parametrize('model', ['NotADevice', 'Oscillator', '__import__', None, ['Transmon']])
def test_unsupported_models_are_blocked(model):
    values = transmon()
    values['model'] = model
    assert_blocks(values, 'unsupported model')


@pytest.mark.parametrize('field', ['EC', 'EJ'])
def test_missing_required_energy(field):
    values = transmon()
    del values['parameters'][field]
    del values['parameter_units'][field]
    assert_blocks(values, 'requires')


def test_unqualified_cad_heuristics_and_em_origin_fail_closed():
    values = transmon()
    values['source'] = 'em'
    assert_blocks(values, 'trusted A01')
    values['source'] = 'independent'
    values['verified_em'] = True
    assert_blocks(values, 'unknown input keys|self-certify')


@pytest.mark.parametrize('field,value', [('EJ', 0), ('EC', -1), ('ng', True),
                                        ('ncut', 9.5), ('EJ', float('nan')),
                                        ('EC', float('inf')), ('ng', 12)])
def test_unphysical_or_unsafe_parameters(field, value):
    values = transmon()
    values['parameters'][field] = value
    with pytest.raises(EngineBlocked):
        a._spec(values, project())


@pytest.mark.parametrize('bad_flux', [-.01, 1.01, '0.5', float('inf')])
def test_invalid_flux(bad_flux):
    values = fluxonium()
    values['parameters']['flux'] = bad_flux
    with pytest.raises(EngineBlocked):
        a._spec(values, project())


@pytest.mark.parametrize('field,unit', [('EC', 'MHz'), ('EJ', 'J'), ('ng', 'GHz'),
                                        ('ncut', 'GHz')])
def test_wrong_units_are_blocked(field, unit):
    values = transmon()
    values['parameter_units'][field] = unit
    assert_blocks(values, 'explicit unit')


def test_flux_must_be_phi0_units():
    values = fluxonium()
    values['parameter_units']['flux'] = 'Wb'
    assert_blocks(values, 'Phi0')


def test_sweep_is_explicit_and_bounded():
    values = fluxonium()
    values['sweep'] = {'subsystem': 'primary', 'parameter': 'flux',
                       'values': [0, .5, 1], 'unit': 'Phi0'}
    parsed = a._spec(values, project())
    assert parsed['sweep']['values'] == [0, .5, 1]
    values['sweep']['values'] = list(range(22))
    assert_blocks(values, '2 to 21')
    values['sweep']['values'] = [0, 1.1]
    assert_blocks(values, 'normalized')
    values['sweep']['values'] = [0, .5]
    values['sweep']['unit'] = 'GHz'
    assert_blocks(values, 'Phi0')


def test_stale_context_and_self_digest():
    values = transmon()
    context = {key: project()[key] for key in ('schematic', 'layout', 'process')}
    values['context_sha256'] = a._sha(context)
    assert a._spec(values, project())['context_sha256'] == values['context_sha256']
    edited = project()
    edited['schematic']['nodes'].append({'id': 'n1'})
    with pytest.raises(EngineBlocked, match='stale'):
        a._spec(values, edited)
    values['input_sha256'] = a._sha(values)
    a._spec(values, project())
    values['parameters']['EJ'] = 16.
    assert_blocks(values, 'stale input_sha256')


def test_canonical_digest_is_stable_and_input_is_not_mutated():
    values = transmon()
    original = copy.deepcopy(values)
    a._spec(values, project())
    assert values == original
    assert a._sha({'b': 1, 'a': 2}) == a._sha({'a': 2, 'b': 1})
    assert a._sha(values) == hashlib.sha256(json.dumps(values, sort_keys=True,
                      ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def test_convergence_validation():
    values = transmon()
    values['convergence'] = {'enabled': True, 'tolerance_GHz': .005, 'basis_increment': 3}
    assert a._spec(values, project())['convergence']['enabled']
    values['convergence']['tolerance_GHz'] = 0
    assert_blocks(values, 'tolerance')
    values['convergence']['tolerance_GHz'] = .005
    values['parameters']['ncut'] = 80
    assert_blocks(values, 'expansion')


def composite():
    q1 = transmon()
    q2 = transmon()
    q1['parameters']['truncated_dim'] = 4
    q1['parameter_units']['truncated_dim'] = '1'
    q2['parameters']['truncated_dim'] = 4
    q2['parameter_units']['truncated_dim'] = '1'
    return {'model': 'Composite', 'levels': 4, 'source': 'independent',
            'subsystems': [
                {'id': 'q1', 'model': 'Transmon', 'parameters': q1['parameters'],
                 'parameter_units': q1['parameter_units']},
                {'id': 'q2', 'model': 'Transmon', 'parameters': q2['parameters'],
                 'parameter_units': q2['parameter_units']}],
            'interactions': [{'left': 'q1', 'right': 'q2',
                              'operator_left': 'n_operator', 'operator_right': 'n_operator',
                              'g': .025, 'unit': 'GHz'}]}


def test_explicit_composite_coupling_and_restricted_operators():
    values = composite()
    parsed = a._spec(values, project())
    assert parsed['composite_dim'] == 16
    values['interactions'][0]['operator_left'] = 'eval'
    assert_blocks(values, 'allowlisted')
    values['interactions'][0]['operator_left'] = 'n_operator'
    values['interactions'][0]['unit'] = 'MHz'
    assert_blocks(values, 'GHz')


def test_composite_basis_bounding():
    values = composite()
    values['subsystems'][0]['parameters']['truncated_dim'] = 16
    values['subsystems'][1]['parameters']['truncated_dim'] = 16
    assert_blocks(values, 'composite dimension')
    values['subsystems'][0]['parameters']['truncated_dim'] = 9
    values['subsystems'][1]['parameters']['truncated_dim'] = 9
    values['convergence'] = {'enabled': True, 'tolerance_GHz': .01, 'basis_increment': 4}
    assert_blocks(values, 'expansion')


def test_missing_native_engine_creates_no_artifact(tmp_path):
    from importlib.util import find_spec
    if find_spec('scqubits') is not None:
        pytest.skip('scqubits available; native integration covered separately')
    with pytest.raises(EngineBlocked, match='not installed'):
        a.run({'id': 'q', 'inputs': transmon()}, project(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_model_fails_before_module_import(tmp_path):
    values = transmon()
    values['model'] = 'RawPython'
    with pytest.raises(EngineBlocked, match='unsupported'):
        a.run({'id': 'q', 'inputs': values}, project(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_native_constructor_and_charge_coupling_allowlist_wiring():
    """Structural dispatch spy only: no eigenvalues or simulated outputs."""
    calls = []

    class FakeQubit:
        def __init__(self, **kwargs):
            self.args = kwargs
            calls.append(('Transmon', kwargs))

        def n_operator(self):
            raise AssertionError('Operator evaluation belongs to native scqubits')

    class FakeHilbertSpace:
        def __init__(self, devices):
            self.devices = devices
            self.interactions = []
            calls.append(('HilbertSpace', len(devices)))

        def add_interaction(self, **kwargs):
            assert kwargs['op1'].__self__ is self.devices[0]
            assert kwargs['op2'].__self__ is self.devices[1]
            self.interactions.append(kwargs)
            calls.append(('interaction', kwargs['g']))

    class FixedAllowlistedAPI:
        Transmon = FakeQubit
        HilbertSpace = FakeHilbertSpace

    spec = a._spec(composite(), project())
    result = a._native_system(FixedAllowlistedAPI, spec, increment=1)
    assert len(result.devices) == 2
    assert result.devices[0].args['ncut'] == 11
    assert result.devices[0].args['truncated_dim'] == 5
    assert result.interactions[0]['g'] == .025
    assert a._native_system(FixedAllowlistedAPI, spec, coupled=False).interactions == []
    assert len([row for row in calls if row[0] == 'Transmon']) == 4


def test_native_numpy_scalar_eigenvalues_are_accepted_without_solver_emulation():
    import numpy as np

    class NativeOutputShapeSpy:
        def eigenvals(self, evals_count):
            assert evals_count == 3
            return np.array([1., 2., 4.], dtype=np.float32)

    assert a._eigenvalues(NativeOutputShapeSpy(), 3) == [1., 2., 4.]


def test_nonreal_native_output_is_blocked():
    class InvalidNativeOutputShapeSpy:
        def eigenvals(self, evals_count):
            return [0., complex(1., 0.)]

    with pytest.raises(EngineBlocked, match='not real'):
        a._eigenvalues(InvalidNativeOutputShapeSpy(), 2)


def test_standalone_implicit_truncation_is_deterministic_and_declared():
    inp = transmon()
    resolved = a._spec(inp, project())
    assert 'truncated_dim' not in inp['parameters']
    assert resolved['groups'][0]['parameters']['truncated_dim'] == 6
    inp['levels'] = 9
    assert a._spec(inp, project())['groups'][0]['parameters']['truncated_dim'] == 9
    inp['parameters']['ncut'] = 3
    assert_blocks(inp, 'native basis dimension')
