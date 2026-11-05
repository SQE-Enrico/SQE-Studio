"""M5 B04 electrostatic CASE readiness, never B04 scientific acceptance.

This is a read-only, *software* preflight over a current-head owner-scoped
Store run. It does not launch Palace, attest that Palace ran, verify CAD-to-mesh
registration, or convert the Maxwell matrix to EC. A signed/checksummed record
is not a signature of independent experimental or numerical physics review.

The v1 M1 topology and M3 dossier interfaces remain unchanged. The caller must
bind ``owner`` to a trusted authenticated session and supply an authenticated
saved selection; this library cannot attest the selection's persistence.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

from ..orchestration.artifacts import safe_file, verify_manifest
from ..store import Store
from .capacitance_review_dossier import (
    CapacitanceReviewBlocked, build_native_capacitance_review_dossier,
)
from .capacitance_topology import _spd
from .native_capacitance_evidence import parse_native_capacitance_table

SCHEMA = 'sqe.native-capacitance-case-readiness.v1'
MAX_REPORT_BYTES = 65536
_NATIVE_FILES = {
    'terminal_csv': 'sqe_em/outputFiles/terminal-C.csv',
    'palace_deck': 'sqe_em/sqe_em.json',
    'gmsh_mesh': 'sqe_em/sqe_em.msh',
    'native_log': 'sqe_em/palace-native.log',
    'native_sidecar': 'a03-native-artifacts.json',
}
_SOFTWARE_CHECKS = (
    'owner_scoped_completed_current_head_run',
    'native_manifest_and_all_artifact_sha256',
    'native_deck_mesh_units_and_material_tags',
    'unique_ordered_conductors_and_reference_ground',
    'physical_mesh_group_presence_not_cad_registration',
    'finite_reciprocal_positive_definite_maxwell_matrix',
    'explicit_island_pair_and_other_conductor_policy',
)
_PHYSICAL_GAPS = (
    ('real_b04_native_execution', 'Obtain independently verifiable native Palace electrostatic run and host/version/runtime evidence.'),
    ('cad_mesh_registration', 'Review CAD/QDesign metal islands and junction surfaces against Gmsh electrode faces and orientation.'),
    ('ground_and_bc_review', 'Review actual PEC reference-ground connectivity, farfield, terminal isolation and boundary constraints.'),
    ('dielectrics_and_materials', 'Independently review geometry scale, dielectric stack, kinetic/interface assumptions and materials.'),
    ('mesh_convergence', 'Perform independent native B04 mesh/order convergence and uncertainty analysis.'),
    ('junction_and_parasitics', 'Include junction, wiring, stray and distributed capacitance; review floating-network constraints.'),
    ('independent_hamiltonian_review', 'Validate effective network reduction, Hamiltonian convention and EJ/EC units independently.'),
    ('authenticated_selection_and_signoff', 'Authenticate saved current-head selection and independent expert review/signatures.'),
)


class NativeCapacitanceCaseBlocked(ValueError):
    """No trustworthy B04 software case evidence can be produced."""


def _require(condition: bool, why: str) -> None:
    if not condition:
        raise NativeCapacitanceCaseBlocked(why)


def _no_linked_parts(path: Path, root: Path) -> None:
    """Reject symlink/junction in *any* path component, including intermediates.

    resolve() containment alone does not reject a Windows junction or an
    inside-root symlink that can be swapped after source inspection.
    """
    _require(path.is_absolute() and '..' not in path.parts and '.' not in path.parts,
             'Untrusted relative or traversing native path')
    try:
        parts = path.relative_to(root).parts
    except ValueError as exc:
        raise NativeCapacitanceCaseBlocked('Native path is outside Store root') from exc
    here = root
    for component in parts:
        here = here / component
        is_junction = getattr(here, 'is_junction', None)
        _require(not here.is_symlink() and not (callable(is_junction) and is_junction()),
                 'Native path contains a symlink or Windows junction')
    _require(path.resolve().is_relative_to(root.resolve()),
             'Native path resolves outside Store root')


def _read_source(store: Store, owner: str, project_id: str, run_id: str,
                 expected_revision: str | None = None):
    """Recheck Store authority and path ancestry; no arbitrary folder input."""
    _require(type(store) is Store and all(type(t) is str and 0 < len(t) <= 128
             for t in (owner, project_id, run_id)), 'Authorized Store identity required')
    project = store.project(owner, project_id)
    run = store.run(owner, project_id, run_id)
    _require(project['revision'] == project['head'] and
             (expected_revision is None or project['revision'] == expected_revision) and
             run['revision_id'] == project['revision'] and run['state'] == 'completed' and
             run['engine'] == 'sqdmetal_palace', 'Wrong head/revision/engine/completion')
    root = store.root.resolve()
    folder = Path(run['path']) / 'output'
    _no_linked_parts(folder, root)
    _no_linked_parts(folder / 'RESULT_MANIFEST.json', root)
    mf = safe_file(folder, 'RESULT_MANIFEST.json')
    _require(mf.stat().st_size <= 128 * 1024, 'Oversize native manifest')
    manifest = json.loads(mf.read_bytes())
    _require(type(manifest) is dict and manifest.get('kind') == 'capacitance' and
             manifest.get('artifact_type') == 'palace.capacitance_matrix' and
             manifest.get('study_id') == run['study_id'], 'Not a Palace electrostatic B04 record')
    for item in manifest.get('artifacts', []):
        _require(type(item) is dict and type(item.get('name')) is str,
                 'Malformed artifact entry')
        _no_linked_parts(folder.joinpath(*item['name'].split('/')), root)
    ref = verify_manifest(folder, revision_id=project['revision'],
                          project_digest=project['revision_digest'],
                          study_id=run['study_id'], engine='sqdmetal_palace')
    _require(ref.artifact_type == 'palace.capacitance_matrix', 'Wrong Palace case type')
    return project, run, folder, manifest, ref


def serialize_native_capacitance_case_readiness(report: dict) -> bytes:
    """Machine-readable canonical JSON; never serialize a promoted B04 gate."""
    _require(type(report) is dict and report.get('schema') == SCHEMA and
             report.get('case_id') == 'B04' and report.get('decision') == 'BLOCKED' and
             report.get('scientific_status') == 'BLOCKED' and
             report.get('fabrication') == 'HOLD' and
             report.get('native_execution') == 'ARTIFACT_RECORD_ONLY_NOT_ATTESTED' and
             report.get('ec_to_scqubits') == 'BLOCKED',
             'B04 scientific status cannot be promoted by a report')
    _require(type(report.get('software_checks')) is list and
             report['software_checks'] == [
                 {'id': item, 'status': 'SCREENED_RECORD_ONLY'} for item in _SOFTWARE_CHECKS],
             'Software record checks cannot be promoted to physical approval')
    _require(type(report.get('missing_physical_evidence')) is list and
             report['missing_physical_evidence'] == [
                 {'id': key, 'status': 'MISSING_INDEPENDENT_EVIDENCE', 'required': requirement}
                 for key, requirement in _PHYSICAL_GAPS],
             'Independent B04 evidence cannot be self-attested')
    _require(set(report) == {
        'schema', 'case_id', 'decision', 'scientific_status', 'fabrication',
        'native_execution', 'ec_to_scqubits', 'source', 'terminals', 'ground',
        'geometry', 'capacitance', 'software_checks', 'missing_physical_evidence',
        'review', 'limitations',
    }, 'Unexpected case report field (possible forged approval)')
    _require(type(report.get('source')) is dict and
             set(report['source']) == {
                 'revision_id', 'revision_digest', 'study_id', 'engine',
                 'engine_version_as_recorded_not_attested', 'manifest_sha256',
                 'artifacts',
             } and report['source']['engine'] == 'sqdmetal_palace' and
             type(report.get('capacitance')) is dict and
             set(report['capacitance']) == {
                 'matrix_type', 'terminal_count', 'header_unit', 'normalized_unit',
                 'matrix_embedded', 'reciprocity_relative_residual', 'finite_spd_check',
             } and report['capacitance']['normalized_unit'] == 'F' and
             report['capacitance']['matrix_embedded'] is False and
             report['capacitance']['finite_spd_check'] == 'PASSED_NUMERICAL_SCREEN_ONLY' and
             type(report.get('terminals')) is list and
             type(report.get('ground')) is dict and
             report['ground'].get('in_maxwell_matrix') is False and
             type(report.get('geometry')) is dict and
             str(report['geometry'].get('cad_to_mesh_registration', '')).startswith('BLOCKED') and
             type(report.get('limitations')) is list and len(report['limitations']) == 5,
             'Case payload cannot declare unverified physical evidence')
    review = report.get('review')
    _require(type(review) is dict and
             set(review) == {'status', 'signatures', 'saved_selection'} and
             review.get('status') == 'NOT_APPROVED' and
             review.get('signatures') == [] and
             review.get('saved_selection') == 'CALLER_SUPPLIED_NOT_AUTHENTICATED_AS_PERSISTED',
             'Case review/selection cannot be automatically approved')
    try:
        raw = (json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False,
                          separators=(',', ':')) + '\n').encode('utf-8')
    except (ValueError, TypeError, OverflowError) as exc:
        raise NativeCapacitanceCaseBlocked('Non-JSON case report') from exc
    _require(len(raw) <= MAX_REPORT_BYTES, 'Case report exceeds bounded disclosure size')
    return raw


def build_native_capacitance_case_readiness(store: Store, *, owner: str,
                                            project_id: str, run_id: str,
                                            saved_selection: dict) -> dict:
    """Screen B04 readiness from a Store run. Returns BLOCKED, or raises.

    A successful software screen says only that the recorded native artifact
    syntax/digests and preexisting M1/M3 mapping conditions agree. It is NOT
    proof that Palace actually executed or a native scientific benchmark PASS.
    """
    try:
        project, run, folder, manifest, ref = _read_source(store, owner, project_id, run_id)
        dossier = build_native_capacitance_review_dossier(
            store, owner=owner, project_id=project_id, run_id=run_id,
            saved_selection=saved_selection)
        _require(dossier['source']['manifest_sha256'] == ref.manifest_sha256 and
                 dossier['source']['revision_id'] == project['revision'] and
                 dossier['source']['study_id'] == run['study_id'],
                 'M3 dossier and trusted Store source disagree')
        _require(set(dossier['source']['artifacts']) == set(_NATIVE_FILES),
                 'Missing required native Palace file hashes')
        for kind, name in _NATIVE_FILES.items():
            expected = dossier['source']['artifacts'][kind]
            item = next((a for a in manifest['artifacts'] if a['name'] == name), None)
            _require(item is not None and expected == {'sha256': item['sha256'], 'bytes': item['bytes']},
                     'Dossier file inventory no longer agrees with source')
        matrix, native_unit = parse_native_capacitance_table(
            safe_file(folder, _NATIVE_FILES['terminal_csv']),
            count=dossier['capacitance']['terminal_count'],
            expected_unit=dossier['capacitance']['native_csv_unit'])
        _spd(matrix)
        _require(dossier['capacitance']['matrix_entry_unit'] == 'F' and
                 len(dossier['terminals']) == len(matrix) and native_unit in ('F', 'fF'),
                 'Maxwell units or number of terminals ambiguous')
        scale = max(abs(value) for row in matrix for value in row)
        residual = max(abs(matrix[i][j] - matrix[j][i])
                       for i in range(len(matrix)) for j in range(len(matrix))) / scale
        _require(residual <= Decimal('0.001'), 'Reciprocity screen failed')
        ids = [group for entry in dossier['terminals'] for group in entry['native_group_ids']]
        ground = dossier['ground']['native_group_ids']
        _require(all(type(t) is int for t in ids + ground) and
                 len(set(ids + ground)) == len(ids + ground) and bool(ground) and
                 [t['terminal_index'] for t in dossier['terminals']] ==
                     list(range(1, len(matrix) + 1)) and
                 dossier['ground']['native_bc'] == 'Palace Electrostatic Ground' and
                 dossier['ground']['in_maxwell_matrix'] is False and
                 dossier['geometry']['cad_to_mesh_registration'].startswith('BLOCKED'),
                 'Terminal/ground/geometry evidence does not meet software preflight')
        # No output can assert scientific approval, even if a sidecar contains a
        # forged signature or a manifest's record status happens to be reviewed.
        latest, last_run, _, last_manifest, final = _read_source(
            store, owner, project_id, run_id, expected_revision=project['revision'])
        _require(latest == project and last_run == run and final == ref and
                 last_manifest == manifest, 'Native source changed during screening')
        report = {
            'schema': SCHEMA, 'case_id': 'B04', 'decision': 'BLOCKED',
            'scientific_status': 'BLOCKED', 'fabrication': 'HOLD',
            'native_execution': 'ARTIFACT_RECORD_ONLY_NOT_ATTESTED',
            'ec_to_scqubits': 'BLOCKED',
            'source': {'revision_id': project['revision'],
                       'revision_digest': project['revision_digest'],
                       'study_id': run['study_id'], 'engine': 'sqdmetal_palace',
                       'engine_version_as_recorded_not_attested': ref.engine_version,
                       'manifest_sha256': ref.manifest_sha256,
                       'artifacts': dossier['source']['artifacts']},
            'terminals': dossier['terminals'],
            'ground': dossier['ground'],
            'geometry': dossier['geometry'],
            'capacitance': {'matrix_type': 'Maxwell terminal capacitance',
                            'terminal_count': len(matrix),
                            'header_unit': native_unit, 'normalized_unit': 'F',
                            'matrix_embedded': False,
                            'reciprocity_relative_residual': str(residual),
                            'finite_spd_check': 'PASSED_NUMERICAL_SCREEN_ONLY'},
            'software_checks': [{'id': item, 'status': 'SCREENED_RECORD_ONLY'}
                                for item in _SOFTWARE_CHECKS],
            'missing_physical_evidence': [
                {'id': key, 'status': 'MISSING_INDEPENDENT_EVIDENCE', 'required': requirement}
                for key, requirement in _PHYSICAL_GAPS],
            'review': {'status': 'NOT_APPROVED', 'signatures': [],
                       'saved_selection': 'CALLER_SUPPLIED_NOT_AUTHENTICATED_AS_PERSISTED'},
            'limitations': [
                'Recorded native sidecar exit code, version and manifest SHA are not native solver attestation.',
                'Gmsh physical-tag presence is not CAD-to-conductor face registration.',
                'Finite, symmetric SPD screening is not physical B04 convergence or accuracy.',
                'No junction, parasitic, floating-network or E_C physics was approved or transferred.',
                'Independent Palace run and expert review are required before any B04 PASS.',
            ],
        }
        serialize_native_capacitance_case_readiness(report)
        return report
    except NativeCapacitanceCaseBlocked:
        raise
    except (CapacitanceReviewBlocked, OSError, ValueError, TypeError, KeyError,
            IndexError, StopIteration) as exc:
        raise NativeCapacitanceCaseBlocked(
            'Trusted B04 source/evidence invalid: ' + type(exc).__name__) from exc
