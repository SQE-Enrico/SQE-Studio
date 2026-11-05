"""Declarative single-transmon research input, never a fabricated solver result."""
from copy import deepcopy

from ._starter_models import CPW_RESONATOR_V1
from .contracts import fresh_project, validate_project


def single_transmon_model(name):
    model = fresh_project(name, 'transmon')
    model['process'] = deepcopy(CPW_RESONATOR_V1['process'])
    model['process']['source'] = 'unverified'
    # Explicit reference inputs from SQDMetal's installed silicon catalogue;
    # these remain unmeasured assumptions requiring user acknowledgment.
    model['process']['stack'][0].update(relative_permittivity=11.45, loss_tangent=2.7e-6)
    model['layout'] = {'engine': 'quantum_metal',
        'chip': {'width_mm': 1.2, 'height_mm': 1.2, 'thickness_um': 500},
        'components': [{'kind': 'TransmonPocket', 'name': 'Q1', 'x_mm': 0, 'y_mm': 0,
            'options': {'pad_width_um': 300, 'pad_height_um': 150, 'pad_gap_um': 30,
                        'pocket_width_um': 700, 'pocket_height_um': 500}}]}
    native = next(study for study in CPW_RESONATOR_V1['studies']
                  if study['engine'] == 'sqdmetal_palace')
    em = deepcopy(native['inputs']['em'])
    em['execution'] = 'solve'
    em['boundaries']['farfield'] = 'ground'
    em['mesh'].update(min_um=40, max_um=150)
    em['solver'] = {key: value for key, value in em['solver'].items()
                    if key not in ('start_hz', 'modes')}
    em['solver']['num_cpus'] = 1
    em['ground'].update(native_attributes=[1], native_terminal_index=1)
    em['ports'] = [
        {'index': 1, 'kind': 'conductor', 'component': 'Q1', 'qgeometry': 'pad_bot',
         'label': 'Q1_pad_bot', 'native_attributes': [2], 'native_terminal_index': 2},
        {'index': 2, 'kind': 'conductor', 'component': 'Q1', 'qgeometry': 'pad_top',
         'label': 'Q1_pad_top', 'native_attributes': [3], 'native_terminal_index': 3}]
    model['studies'] = [{'id': 'TransmonCapacitance', 'engine': 'sqdmetal_palace',
                         'kind': 'capacitance', 'inputs': {'em': em}}]
    model['intent']['transmon_capacitance_selection'] = {
        'schema': 'sqe.saved-transmon-capacitance-selection.v1',
        'study_id': 'TransmonCapacitance', 'island_a': 'Q1_pad_bot', 'island_b': 'Q1_pad_top',
        'other_terminal_policy': {'fixed_zero': [], 'floating_zero_charge': []},
        'configuration': 'TWO_ISLAND_CHARGE_TRANSFER',
        'junction_capacitance_assumption': 'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'}
    model['notes'] = (
        'Illustrative isolated two-pad TransmonPocket, not a reproduced fabricated device. '
        'Silicon eps_r=11.45 and tan_delta=2.7e-6 are SQDMetal catalogue assumptions. '
        'Review the process assumptions before native execution. Declare additional C_J and '
        'E_J/h or L_J separately at extraction; neither is inferred from PEC geometry. '
        'Mesh/domain convergence and physical qualification are not established.')
    return validate_project(model)
