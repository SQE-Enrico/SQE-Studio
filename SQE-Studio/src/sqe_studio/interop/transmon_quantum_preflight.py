"""Pure, standalone scqubits Transmon *study-template* preflight (M3 A12).

This builder only accepts a **new, independently designer-entered** Hamiltonian
parameter declaration. It cannot authenticate *how* an arbitrary scalar was
obtained: A99 must keep the dedicated manual-entry boundary separate from EM
Results and must never feed it an EM-extracted capacitance-screen value.

This module does not open a project, import scqubits, run a solver, create a
saved study, attest a reviewer, or authorize EM -> Hamiltonian transfer.
"""
from __future__ import annotations

import math

DECLARATION_SCHEMA = 'sqe.independent-transmon-declaration.a12.v1'
PREFLIGHT_SCHEMA = 'sqe.independent-transmon-study-preflight.a12.v1'
_PARAMETER_KEYS = frozenset({'EJ', 'EC', 'ng', 'ncut'})
_UNITS = {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'}
_DECLARATION_KEYS = frozenset({'schema', 'source', 'model', 'parameters',
                               'parameter_units', 'levels'})


class TransmonPreflightBlocked(ValueError):
    """Invalid or unsafe declaration; no study-template is returned."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def _block(code: str, reason: str) -> None:
    raise TransmonPreflightBlocked(code, reason)


def _finite_number(raw: object, name: str) -> float:
    # Match the scqubits adapter: reject bool, Decimal, numeric strings, and
    # arbitrary numeric coercion; never turn an EM-result dict into a scalar.
    if type(raw) not in (int, float):
        _block('INVALID_PARAMETER', f'{name} must be an explicit finite number, not a boolean/string/object')
    try:
        value = float(raw)
    except (OverflowError, ValueError):
        _block('INVALID_PARAMETER', f'{name} exceeds supported numerical range')
    if not math.isfinite(value):
        _block('INVALID_PARAMETER', f'{name} must be finite')
    return value


def _bounded_int(raw: object, name: str, lo: int, hi: int) -> int:
    if type(raw) is not int or not lo <= raw <= hi:
        _block('INVALID_DIMENSION', f'{name} must be an integer in [{lo}, {hi}]')
    return raw


def build_independent_transmon_preflight(declaration: object) -> dict[str, object]:
    """Validate a *manual independent* declaration; return an unsaved template.

    Exact input shape::

      {'schema': 'sqe.independent-transmon-declaration.a12.v1',
       'source': 'independent', 'model': 'Transmon',
       'parameters': {'EJ': 15, 'EC': 0.25, 'ng': 0, 'ncut': 30},
       'parameter_units': {'EJ': 'GHz', 'EC': 'GHz',
                           'ng': '2e', 'ncut': '1'},
       'levels': 5}

    EJ/EC are E/h in GHz, not joules and never Palace-derived E_C/h. Inputs
    with revision/EM source lineage, extraction, approved/review claims, or
    additional keys are rejected, even when they also claim independence.
    The output contains a new scqubits adapter-compatible *unsaved* study
    template. A99 alone may bind that template to a trusted project revision.

    Pure syntax checks cannot prove the real-world origin of a scalar typed by
    an operator. Caller/UI separation is therefore a mandatory integration
    gate, NOT replaced by declaration.source='independent'.
    """
    if type(declaration) is not dict:
        _block('INVALID_DECLARATION', 'Expected a standalone designer-entry declaration object')
    if set(declaration) != _DECLARATION_KEYS:
        _block('UNTRUSTED_INPUT_SHAPE', 'Only schema, source, model, parameters, parameter_units and levels are accepted; never EM/review fields')
    if declaration['schema'] != DECLARATION_SCHEMA:
        _block('UNTRUSTED_INPUT_SHAPE', 'Wrong declaration schema; EM/saved Results cannot be reused')
    if type(declaration['source']) is not str or declaration['source'] != 'independent':
        _block('EM_DERIVATION_BLOCKED', 'EM-, Palace-, engine- or derived-origin parameters are not supported')
    if type(declaration['model']) is not str or declaration['model'] != 'Transmon':
        _block('UNSUPPORTED_MODEL', 'Only standalone scqubits Transmon is supported')

    params = declaration['parameters']
    units = declaration['parameter_units']
    if type(params) is not dict or set(params) != _PARAMETER_KEYS:
        _block('INVALID_PARAMETER', 'Exactly EJ, EC, ng and ncut are required; no derived EC or truncated_dim')
    if type(units) is not dict or set(units) != _PARAMETER_KEYS:
        _block('INVALID_UNITS', 'Every supplied parameter needs one explicit matching unit')
    for key, expected in _UNITS.items():
        if type(units[key]) is not str or units[key] != expected:
            _block('INVALID_UNITS', f'{key} must use exactly {expected!r}; no implicit conversions')

    ej = _finite_number(params['EJ'], 'EJ')
    ec = _finite_number(params['EC'], 'EC')
    ng = _finite_number(params['ng'], 'ng')
    if not 0 < ej <= 1000 or not 0 < ec <= 1000:
        _block('INVALID_ENERGY', 'EJ and EC must each be positive and <= 1000 GHz (E/h)')
    if not -10 <= ng <= 10:
        _block('INVALID_PARAMETER', 'ng must be in [-10, 10] offset-charge units (2e)')
    ncut = _bounded_int(params['ncut'], 'ncut', 3, 80)
    levels = _bounded_int(declaration['levels'], 'levels', 2, 12)
    # The frozen adapter adds truncated_dim=max(6,levels). Its charge basis
    # has 2*ncut+1 states; reject rather than silently truncate the study.
    if max(6, levels) > 2 * ncut + 1:
        _block('INVALID_DIMENSION', 'levels exceed the available Transmon charge basis')

    # Fresh, allowlisted scalar copies only: never forward arbitrary metadata
    # or nested user objects to a scientific worker or a saved project.
    inputs = {
        'source': 'independent',
        'model': 'Transmon',
        'parameters': {'EJ': ej, 'EC': ec, 'ng': ng, 'ncut': ncut},
        'parameter_units': dict(_UNITS),
        'levels': levels,
    }
    return {
        'schema': PREFLIGHT_SCHEMA,
        'status': 'VALID_INDEPENDENT_RESEARCH_PREFLIGHT_ONLY',
        'study_template': {'engine': 'scqubits', 'kind': 'quantum_spectrum',
                           'inputs': inputs},
        'saved_study': 'NOT_CREATED',
        'solver_execution': 'NOT_EXECUTED',
        'parameter_provenance': 'UNVERIFIED_DESIGNER_DECLARATION_ONLY',
        'energy_convention': 'E_OVER_H_GHz',
        'scientific_authorization': 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION',
        'em_ec_transfer': 'BLOCKED',
        'em_to_hamiltonian': 'BLOCKED',
        'fabrication': 'HOLD',
    }
