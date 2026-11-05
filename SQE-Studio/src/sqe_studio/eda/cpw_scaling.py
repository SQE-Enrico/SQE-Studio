"""M9 CPW scaling screen for TWO previously hash-verified Palace eigenmode runs.

Goppl et al., J. Appl. Phys. 104, 113904 (2008), Eq. (1), Table I.
The f ~ 1/length relationship is a transmission-line approximation, not an
unqualified prediction of a specific physical mode or experimental agreement.
The authenticated caller verifies BOTH native manifests and immutable models.
"""
from __future__ import annotations

from copy import deepcopy
import math

SCHEMA = 'sqe.cpw-length-scaling.m9.v1'
DOI = '10.1063/1.3010859'
RELATIVE_TOLERANCE_PROVISIONAL = 0.15


def _blocked(reason: str) -> dict:
    return {
        'schema': SCHEMA, 'case_id': 'R02_CPW_LENGTH_SCALING',
        'status': 'BLOCKED', 'reason': reason, 'checks': [],
        'oracle_kind': 'LITERATURE_TRANSMISSION_LINE_SCALING',
        'reference_doi': DOI, 'mode_identity': 'NOT_ESTABLISHED',
        'mesh_convergence': 'NOT_ESTABLISHED',
        'physical_validation': 'NOT_ESTABLISHED', 'fabrication': 'HOLD',
    }


def length_scaling_ratio(left_length_mm: float, right_length_mm: float) -> float:
    """The expected right/left f0 ratio for a uniform CPW with fixed ends/stack.

    Pure geometry/analytic method; does NOT read or compute native solver data.
    """
    for value in (left_length_mm, right_length_mm):
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 1000:
            raise ValueError('Finite positive CPW route length in mm required')
    return float(left_length_mm / right_length_mm)


def _single_native_f0(native: dict | None):
    if (not isinstance(native, dict) or native.get('source') != 'palace.native_eig.csv'
            or native.get('units') != 'GHz' or native.get('mode_matching') != 'not_established'):
        return None
    modes = native.get('modes')
    # Do not silently select an arbitrary mode among several unidentifed peaks.
    if not isinstance(modes, list) or len(modes) != 1 or not isinstance(modes[0], dict):
        return None
    if modes[0].get('mode_index') != 1:
        return None
    f = modes[0].get('frequency_GHz')
    return float(f) if type(f) in (int, float) and math.isfinite(f) and 0 < f <= 1000 else None


def _study(model, study_id):
    found = [s for s in model.get('studies', []) if s.get('id') == study_id
             and s.get('engine') == 'sqdmetal_palace' and s.get('kind') == 'eigenmode']
    if len(found) != 1:
        return None
    result = deepcopy(found[0])
    result.pop('id', None)
    return result


def _only_route_length_changed(left_model, right_model):
    if any(m.get('family') != 'resonator' for m in (left_model, right_model)):
        return None
    if any(left_model.get(k) != right_model.get(k) for k in ('process', 'schematic')):
        return None
    a, b = deepcopy(left_model.get('layout')), deepcopy(right_model.get('layout'))
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    lcomps, rcomps = a.get('components'), b.get('components')
    if not isinstance(lcomps, list) or not isinstance(rcomps, list) or len(lcomps) != len(rcomps):
        return None
    changed = []
    for i, (l, r) in enumerate(zip(lcomps, rcomps)):
        if not isinstance(l, dict) or not isinstance(r, dict):
            return None
        if l == r:
            continue
        # The generic Quantum Metal CPW route has a declared path-length input;
        # no particular template, route name, net name or literature length used.
        if l.get('kind') != 'RouteMeander' or r.get('kind') != 'RouteMeander':
            return None
        llen, rlen = l.get('total_length_mm'), r.get('total_length_mm')
        try:
            length_scaling_ratio(llen, rlen)
        except ValueError:
            return None
        changed.append((l.get('name'), float(llen), float(rlen)))
        l['total_length_mm'] = rlen
    if len(changed) != 1 or a != b:
        return None
    return changed[0]


def compare_verified_cpw_length_scaling(*, left_model: dict, right_model: dict,
                                        left_study_id: str, right_study_id: str,
                                        left_native: dict | None,
                                        right_native: dict | None) -> dict:
    """Numerical screening, NOT a field-matched mode or convergence decision.

    Expected to be called only after both authentic native result manifests and
    their contents were SHA-checked. Never takes a client target or tuning knob.
    """
    a, b = _single_native_f0(left_native), _single_native_f0(right_native)
    if a is None or b is None:
        return _blocked('Two verified single-mode Palace eigenfrequency tables in GHz are required')
    s1, s2 = _study(left_model, left_study_id), _study(right_model, right_study_id)
    if s1 is None or s2 is None or s1 != s2:
        return _blocked('Native study settings differ or cannot be matched; only route length may change')
    route = _only_route_length_changed(left_model, right_model)
    if route is None:
        return _blocked('Exactly one CPW RouteMeander total_length_mm may change; stack and all other geometry must match')
    name, length_a, length_b = route
    if abs(length_a-length_b)/max(length_a, length_b) < 0.02:
        return _blocked('Length perturbation below 2%; expected signal too small for this screen')
    predicted = length_scaling_ratio(length_a, length_b)
    observed = b / a
    relative_error = abs(observed-predicted)/predicted
    passed = relative_error <= RELATIVE_TOLERANCE_PROVISIONAL
    return {
        'schema': SCHEMA, 'case_id': 'R02_CPW_LENGTH_SCALING',
        'status': 'NUMERICAL_SCREEN_PASS' if passed else 'NUMERICAL_SCREEN_FAIL',
        'reason': ('Goppl half-wave inverse-length method adapted to two equivalent CPW '
                   'routes; the actual route can have end/coupling/kinetic corrections. '
                   'Native mode index 1 is NOT a verified physical mode correspondence.'),
        'oracle_kind': 'LITERATURE_TRANSMISSION_LINE_SCALING',
        'reference_doi': DOI, 'reference_location': 'Eq. (1), Table I',
        'route_name': name, 'lengths_mm': {'left': length_a, 'right': length_b},
        'frequencies_GHz': {'left_native': a, 'right_native': b},
        'checks': [{'quantity': 'f_right_over_f_left', 'unit': 'dimensionless',
                    'actual': observed, 'reference': predicted,
                    'relative_error': relative_error,
                    'relative_tolerance': RELATIVE_TOLERANCE_PROVISIONAL,
                    'pass': passed}],
        'same_material_and_study_inputs': True,
        'mode_identity': 'NOT_ESTABLISHED', 'mesh_convergence': 'NOT_ESTABLISHED',
        'physical_validation': 'NOT_ESTABLISHED', 'fabrication': 'HOLD',
    }
