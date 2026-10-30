"""Only fake metadata and numerical fixtures; NEVER native solver validation."""
from copy import deepcopy
import pytest
from sqe_studio.interop.comparison import compare_spectra, changes_between, report
from sqe_studio.contracts import fresh_project


def fake_spectrum(values, *, model='Transmon', axis=None, converged=False):
    return {'schema': 'sqe.scqubits.spectrum.v1', 'artifact_type': 'scqubits.spectrum',
            'source': 'native scqubits eigenvals', 'model': model,
            'units': 'GHz', 'energy_unit': 'GHz', 'levels': values,
            'axis': axis, 'preview_point_index': 0,
            'convergence': {'status': 'checked_passed' if converged else 'not_checked'}}


def test_same_model_uses_transition_not_absolute_energy_offsets():
    a=fake_spectrum([1.0,6.0,10.0],converged=True)
    b=fake_spectrum([5.0,10.5,14.0],converged=True)
    r=compare_spectra(a,b)
    assert r['status']=='numerical_differences_for_expert_review'
    assert r['rows'][0]['left_GHz']==5.0
    assert r['rows'][0]['right_GHz']==5.5
    assert r['rows'][0]['delta_GHz']==.5
    assert r['convergence_verified']


@pytest.mark.parametrize('change',[
    lambda s:s.update(model='Fluxonium'),
    lambda s:s.update(units='Hz'),
    lambda s:s.update(axis={'parameter':'EJ','values':[1,2]}),
    lambda s:s.update(levels=[1.0]),
    lambda s:s.update(levels=[float('nan'),2.0,3.0]),
    lambda s:s.update(source='fixture'),
])
def test_mismatched_semantics_are_blocked(change):
    a=fake_spectrum([0.,5.,8.]);b=deepcopy(a);change(b)
    assert compare_spectra(a,b)['status']=='not_comparable'


def test_design_revision_diff_is_bounded_and_not_solver_result():
    a=fresh_project('Unit','transmon')
    b=deepcopy(a);b['layout']['chip']['width_mm']=25
    result=changes_between(a,b,'missing','missing')
    assert result['total']==1
    assert result['shown'][0]['field']=='model.layout.chip.width_mm'
    assert result['meaning'].endswith('not_measured_or_verified_physics')
