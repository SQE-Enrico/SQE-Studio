"""Study-option enumeration tests; no fake scientific outputs."""
import pytest
from sqe_studio.orchestration.sweep import MAX_SWEEP_POINTS, plan_sweep


def study():
    return {'id': 'sp1', 'engine': 'scqubits', 'kind': 'quantum_spectrum',
            'inputs': {'model': 'Transmon', 'parameters': {'EJ': 11.0, 'EC': 0.2, 'ng': 0.0, 'ncut': 12},
                       'levels': 5}}


def test_sweep_deterministic_immutability_manual_and_auto():
    source = study()
    a = plan_sweep(source, {'parameters.EJ': [9.0, 10.0], 'parameters.EC': [0.1, 0.2]}, mode='automatic')
    b = plan_sweep(source, {'parameters.EC': [0.1, 0.2], 'parameters.EJ': [9.0, 10.0]}, mode='automatic')
    assert a == b and len(a) == 4
    assert a[0].coordinates == (('parameters.EC', 0.1), ('parameters.EJ', 9.0))
    assert source['inputs']['parameters']['EJ'] == 11.0
    assert a[0].options_digest != a[1].options_digest
    one = plan_sweep(source, {'parameters.EJ': [9, 10]}, mode='manual', selected=1)
    assert len(one) == 1 and one[0].index == 1
    assert one[0].study['inputs']['parameters']['EJ'] == 10


@pytest.mark.parametrize('axes,mode,selected', [
    ({'parameters.BAD': [10]}, 'manual', 0),
    ({'model': [1.1]}, 'manual', 0),
    ({'parameters.EJ': [float('nan')]}, 'manual', 0),
    ({'parameters.EJ': list(range(MAX_SWEEP_POINTS+1))}, 'automatic', None),
    ({'parameters.EJ': [1,2], 'parameters.EC': list(range(20))}, 'automatic', None),
    ({'parameters.EJ': [1]}, 'manual', None),
    ({'parameters.EJ': [1]}, 'automatic', 0),
    ({'parameters.EJ': [1]}, 'shell', None),
    ({'parameters.__class__': [1]}, 'automatic', None),
])
def test_fail_closed_sweep_planning(axes, mode, selected):
    with pytest.raises(ValueError):
        plan_sweep(study(), axes, mode=mode, selected=selected)
