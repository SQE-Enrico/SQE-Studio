"""M7 read-only drift of two independently verified conditional transmon screens.

The server authenticates each saved run/revision, checks every native artifact
hash and calls the existing full Gmsh/Palace -> A11/A12 screen independently.
This pure post-processing step cannot establish convergence, terminal geometry
identity, junction capacitance, or permission to feed E_C to scqubits.
"""
from __future__ import annotations

import math

SCHEMA = 'sqe.conditional-transmon-drift.m7.v1'
_REQUIRED_PREVIEW = ('configuration', 'retained_terminal_labels',
                     'charge_vector_in_units_of_e', 'fixed_zero',
                     'floating_zero_charge', 'reference_ground_native_group_ids',
                     'junction_capacitance_assumption', 'formula')


def _blocked(reason: str) -> dict:
    return {'schema': SCHEMA, 'status': 'not_comparable', 'reason': reason,
            'scientific_qualification': 'NOT_ESTABLISHED',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'em_to_scqubits_transfer': 'BLOCKED', 'fabrication': 'HOLD'}


def _positive(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def compare_conditional_transmon_screens(left: dict | None, right: dict | None,
                                         left_selection: dict | None,
                                         right_selection: dict | None,
                                         maxwell_comparison: dict) -> dict:
    """Compare numerical screens only if all native/saved assumptions align.

    A matching numerical result means neither convergence nor equivalence.
    Both screens *must* be independently produced from authenticated native
    sources; this routine cannot verify incoming bytes on its own.
    """
    if (type(maxwell_comparison) is not dict or
            maxwell_comparison.get('status') != 'native_maxwell_matrix_differences_for_expert_review'):
        return _blocked('Native Maxwell matrices not verified and comparable')
    if (type(left_selection) is not dict or type(right_selection) is not dict or
            left_selection.get('schema') != 'sqe.saved-transmon-capacitance-selection.v1' or
            left_selection != right_selection):
        return _blocked('Selections must be explicitly saved, identical and revision-bound in both runs')
    if type(left) is not dict or type(right) is not dict:
        return _blocked('Both independently screened saved transmon reductions are required')
    previews = []
    sources = []
    for screen in (left, right):
        if (screen.get('schema') != 'sqe.transmon-integration-screen.m1.v1' or
                screen.get('status') != 'NUMERICAL_SCREEN_ONLY' or
                screen.get('scqubits_EC_transfer') != 'BLOCKED_NOT_REVIEWED' or
                screen.get('fabrication') != 'HOLD'):
            return _blocked('Unrecognized transmon screen or altered scientific hold')
        reduction, topology, mapping = (screen.get('reduction'), screen.get('native_topology'),
                                        screen.get('native_mapping'))
        if (type(reduction) is not dict or type(topology) is not dict or
                type(mapping) is not dict or
                reduction.get('status') != 'NUMERICAL_SCREEN_ONLY' or
                reduction.get('transfer_status') != 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION' or
                reduction.get('scqubits_parameter') is not None or
                reduction.get('ej_over_h_hz') is not None or
                topology.get('scientific_status') != 'UNREVIEWED_TOPOLOGY' or
                mapping.get('geometry_registration') !=
                'BLOCKED_NO_INDEPENDENT_QDESIGN_TO_GMSH_FACE_REGISTRATION' or
                topology.get('source') != reduction.get('source')):
            return _blocked('Native topology, source or physical review gate is unverified')
        src = reduction.get('source')
        if (type(src) is not dict or type(src.get('manifest_sha256')) is not str or
                len(src['manifest_sha256']) != 64 or
                any(ch not in '0123456789abcdef' for ch in src['manifest_sha256'])):
            return _blocked('No valid per-run source manifest SHA-256')
        p = reduction.get('numerical_preview')
        if type(p) is not dict or any(key not in p for key in _REQUIRED_PREVIEW):
            return _blocked('Missing explicit conditional reduction configuration')
        if (p.get('scientific_claim') != 'MATRIX_ONLY_NUMERICAL_SCREEN_NOT_A_TRANSMON_HAMILTONIAN' or
                p.get('uncertainty_status') != 'NOT_ESTABLISHED' or
                not _positive(p.get('effective_capacitance_f')) or
                not _positive(p.get('ec_over_h_hz_matrix_only'))):
            return _blocked('Unqualified or nonfinite conditional capacitance result')
        previews.append(p)
        sources.append(src['manifest_sha256'])
    if any(previews[0][key] != previews[1][key] for key in _REQUIRED_PREVIEW):
        return _blocked('Charge vector, conductor classes, reference ground or junction assumptions changed')
    c1, c2 = (float(p['effective_capacitance_f']) for p in previews)
    e1, e2 = (float(p['ec_over_h_hz_matrix_only']) for p in previews)
    return {
        'schema': SCHEMA,
        'status': 'conditional_transmon_matrix_reduction_drift_for_expert_review',
        'method': 'Two independently screened native Maxwell matrices, same saved topology; no fit, E_J or quantum solve',
        'configuration': previews[0]['configuration'],
        'retained_terminal_labels': previews[0]['retained_terminal_labels'],
        'fixed_zero': previews[0]['fixed_zero'],
        'floating_zero_charge': previews[0]['floating_zero_charge'],
        'left_native_manifest_sha256': sources[0],
        'right_native_manifest_sha256': sources[1],
        'same_native_matrix_sha256': maxwell_comparison.get('same_native_matrix_sha256') is True,
        'left_effective_capacitance_fF': c1 * 1e15,
        'right_effective_capacitance_fF': c2 * 1e15,
        'delta_effective_capacitance_fF': (c2 - c1) * 1e15,
        'relative_effective_capacitance_change': abs(c2 - c1) / max(c1, c2),
        'left_ec_over_h_MHz_matrix_only': e1 / 1e6,
        'right_ec_over_h_MHz_matrix_only': e2 / 1e6,
        'delta_ec_over_h_MHz_matrix_only': (e2 - e1) / 1e6,
        'relative_ec_over_h_change': abs(e2 - e1) / max(e1, e2),
        'mesh_convergence': 'NOT_ESTABLISHED',
        'terminal_physical_identity': 'NOT_ESTABLISHED_BY_NATIVE_TAGS_ALONE',
        'junction_capacitance_review': 'MISSING',
        'uncertainty_status': 'NOT_ESTABLISHED',
        'scientific_qualification': 'NOT_ESTABLISHED',
        'em_to_scqubits_transfer': 'BLOCKED',
        'fabrication': 'HOLD',
    }
