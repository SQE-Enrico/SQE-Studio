"""A99 bridge: authenticated saved transmon intent -> native topology -> numerical screen.

No request-supplied terminal selection enters this path. Only the project record
loaded by Store.project(owner, project_id, EXACT run revision) is permitted.
The stored selection is inside model.intent and is therefore part of the
revision digest. Its revision/digest pins are derived *after* Store loads that
immutable snapshot, avoiding self-referential hashes inside the model.

All physical results remain UNREVIEWED; no E_C is transferred to scqubits.
"""
from __future__ import annotations

from pathlib import Path

from .capacitance_topology import (
    CapacitanceTopologyBlocked, build_native_capacitance_topology,
    inspect_native_capacitance_mapping,
)
from .transmon_reduction import assess_transmon_capacitance

SCHEMA = 'sqe.transmon-integration-screen.m1.v1'
SELECTION_SCHEMA = 'sqe.saved-transmon-capacitance-selection.v1'
_JUNCTION = 'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'
_SELECTION_KEYS = frozenset({'schema', 'study_id', 'island_a', 'island_b',
                            'other_terminal_policy', 'configuration',
                            'junction_capacitance_assumption'})


def inspect_saved_transmon_screen(folder: Path, manifest: dict, project: dict) -> dict | None:
    """Produce a *conditional* preview only for the exact stored project revision.

    Missing selection is not a validation failure for legacy projects. A saved
    but malformed selection fails closed (the Results API maps it to HTTP 409).
    No E_J, Hamiltonian, scqubits call, or physical signoff is possible here.
    """
    if manifest.get('artifact_type') != 'palace.capacitance_matrix':
        return None
    model = project.get('model')
    if not isinstance(model, dict):
        raise CapacitanceTopologyBlocked('Saved project model is unavailable')
    if model.get('family') not in ('transmon', 'multi_qubit'):
        return None
    selection = model.get('intent', {}).get('transmon_capacitance_selection')
    if selection is None:
        return {'schema': SCHEMA, 'status': 'BLOCKED_NO_SAVED_SELECTION',
                'reason': 'Save an explicit island pair and classify every remaining terminal in the same design revision before the Palace run',
                'native_topology': None, 'native_mapping': None, 'reduction': None,
                'scqubits_EC_transfer': 'BLOCKED_NOT_REVIEWED',
                'fabrication': 'HOLD'}
    if not isinstance(selection, dict) or set(selection) != _SELECTION_KEYS or (
            selection.get('schema') != SELECTION_SCHEMA or
            selection.get('study_id') != manifest.get('study_id') or
            selection.get('configuration') not in ('TWO_ISLAND_CHARGE_TRANSFER',
                                                   'GROUNDED_SINGLE_ISLAND') or
            selection.get('junction_capacitance_assumption') != _JUNCTION):
        raise CapacitanceTopologyBlocked('Saved transmon selection schema, study or junction assumption invalid')
    snapshot = {
        'revision_id': project.get('revision'),
        'revision_digest': project.get('revision_digest'),
        'study_id': selection['study_id'],
        'island_a': selection['island_a'],
        'island_b': selection['island_b'],
        'other_terminal_policy': selection['other_terminal_policy'],
    }
    candidate = build_native_capacitance_topology(
        folder, manifest, project, saved_selection=snapshot)
    mapping = inspect_native_capacitance_mapping(
        folder, manifest, project, saved_selection=snapshot)
    decision = assess_transmon_capacitance(
        candidate,
        expected_source=candidate['source'],
        expected_terminal_labels=tuple(candidate['terminal_labels']),
        expected_ground_group_ids=tuple(candidate['reference_ground']['native_group_ids']),
        configuration=selection['configuration'],
        junction_capacitance_assumption=selection['junction_capacitance_assumption'],
    )
    # Both expected values came from independently rehashed A11 bytes, not the
    # incoming request. A12's review declaration is intentionally absent.
    if decision.status != 'NUMERICAL_SCREEN_ONLY' or decision.numerical_preview is None:
        raise CapacitanceTopologyBlocked('Native transmon capacitance reduction blocked: '+decision.status)
    if (candidate['scientific_status'] != 'UNREVIEWED_TOPOLOGY' or
            mapping['geometry_registration'] !=
            'BLOCKED_NO_INDEPENDENT_QDESIGN_TO_GMSH_FACE_REGISTRATION' or
            decision.transfer_status != 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION'):
        raise CapacitanceTopologyBlocked('Physical authorization gate unexpectedly changed')
    return {'schema': SCHEMA, 'status': 'NUMERICAL_SCREEN_ONLY',
            'reason': 'Saved conductor selection and native source checked; physical registration and model approval remain blocked',
            'native_topology': candidate, 'native_mapping': mapping,
            'reduction': decision.as_dict(),
            'scqubits_EC_transfer': 'BLOCKED_NOT_REVIEWED',
            'fabrication': 'HOLD'}
