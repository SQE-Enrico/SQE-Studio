"""Versioned declarative starter designs for the *single* general design workspace.

Templates are input snapshots, NOT separate execution paths or fixture results.
All studies must follow the ordinary authenticated revision-bound job API.
"""
from __future__ import annotations
from copy import deepcopy
from ._starter_models import CPW_RESONATOR_V1
from .eda.use_cases import list_use_cases

from .contracts import ValidationError, validate_project, fresh_project
from .adapters.quantum_metal_adapter import COMPONENTS, ROUTES, DIMENSIONS, validate_recipe

# Allowlisted literal resources: never interpret names/paths supplied by clients.
_LIBRARY = {
    'cpw_resonator_v1': {
        'title': 'CPW resonator / native EM study',
        'family': 'resonator',
        'description': 'Editable Quantum Metal route/layout with an unverified material stack and draft Palace eigenmode settings.',
        'reference': 'https://sqdlab.github.io/SQDMetal/examples/index.html',
        'scientific_status': 'illustrative_geometry_not_a_reproduced_literature_result',
    },
    'transmon_spectrum_v1': {
        'title': 'Transmon / explicit scqubits spectrum',
        'family': 'transmon',
        'description': 'Ordinary editable circuit with independent EJ/EC Hamiltonian inputs. No EM extraction.',
        'reference': 'https://doi.org/10.1063/1.5089550',
        'scientific_status': 'independent_hamiltonian_inputs_not_derived_from_layout',
    },
    'fluxonium_spectrum_v1': {
        'title': 'Fluxonium / scqubits flux sweep',
        'family': 'fluxonium',
        'description': 'Native scqubits flux scan with manually specified EJ, EC and EL; no CAD/EM inference.',
        'reference': 'https://scqubits.readthedocs.io/en/latest/guide/qubits/fluxonium.html',
        'scientific_status': 'independent_hamiltonian_inputs_not_derived_from_layout',
    },
}

def list_templates():
    return [{'id': key, **{k: v for k, v in entry.items() if k != 'model'}}
            for key, entry in _LIBRARY.items()]

def instantiate(template_id: str, name: str, family: str):
    if not isinstance(template_id, str) or template_id not in _LIBRARY:
        raise ValidationError('Unknown starter design')
    entry = _LIBRARY[template_id]
    if family != entry['family']:
        raise ValidationError('Starter design family does not match the selected design family')
    if template_id == 'cpw_resonator_v1':
        model = deepcopy(CPW_RESONATOR_V1)
        model['name'] = name
    else:
        model = fresh_project(name, family)
        model['notes'] = ('Illustrative independent Hamiltonian input, not fitted or extracted from EM. '
                          'Convergence and native solver availability require review.')
        if template_id == 'transmon_spectrum_v1':
            inputs = {'model': 'Transmon', 'source': 'independent', 'levels': 4,
                      'parameters': {'EJ': 15.0, 'EC': 0.25, 'ng': 0.0, 'ncut': 15},
                      'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
                      'convergence': {'enabled': True, 'tolerance_GHz': 0.01, 'basis_increment': 4}}
        else:
            inputs = {'model': 'Fluxonium', 'source': 'independent', 'levels': 4,
                      'parameters': {'EJ': 8.0, 'EC': 2.0, 'EL': 0.5, 'flux': 0.5,
                                     'cutoff': 20, 'truncated_dim': 6},
                      'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'EL': 'GHz',
                                          'flux': 'Phi0', 'cutoff': '1', 'truncated_dim': '1'},
                      'sweep': {'subsystem': 'primary', 'parameter': 'flux',
                                'values': [0.4, 0.45, 0.5, 0.55, 0.6], 'unit': 'Phi0'}}
        model['studies'] = [{'id': 'QuantumSpectrum', 'engine': 'scqubits',
                             'kind': 'spectrum', 'inputs': inputs}]
    validate_project(model)
    if model['layout']['components']:
        validate_recipe(model['layout'])
    if model['process']['source'] != 'unverified':
        raise ValidationError('Starter design material assumptions must remain unverified')
    return model

def use_case_catalog():
    """Read-only literature-based design intentions for the shared GUI."""
    cases = list_use_cases()
    starters = set(_LIBRARY)
    for case in cases:
        if case["starter_template"] and case["starter_template"] not in starters:
            raise RuntimeError("Use case references unregistered starter model")
        if case["readiness"] == "blocked_missing_edge" and case["starter_template"] is not None:
            raise RuntimeError("Blocked use cases may not advertise runnable templates")
    return cases

def component_catalog():
    return {'components': [
        {'kind': kind, 'route': kind in ROUTES,
         'options': sorted(DIMENSIONS.get(kind, ())) if kind not in ROUTES else [],
         'requires_subtract_layer': kind == 'ReadoutResFC'}
        for kind in COMPONENTS]}
