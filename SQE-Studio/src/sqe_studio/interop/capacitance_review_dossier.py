"""M3 read-only, fail-closed native Palace capacitance *review request*.

Only an owner-authorized, completed Store run at the current saved project head
can supply the native source. Hashes are recomputed from its on-disk artifacts;
caller-provided checksums or untrusted project/manifest dictionaries are not an
acceptable substitute. The separately supplied M1 selection is validated, but
its *persistence and human intent* cannot be established by this module.

A dossier is a deterministic, bounded inventory/checklist, NOT a signed review,
physical conductor registration, fresh solver run, B04 approval, EC reduction,
or permission to create an scqubits study. No file contents or simulation mesh
are copied into the emitted dossier.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from ..orchestration.artifacts import ArtifactInvalid, safe_file, verify_manifest
from ..store import NotFound, Store
from .native_capacitance_evidence import native_capacitance_evidence
from .capacitance_topology import (
    CapacitanceTopologyBlocked, _read_mesh_groups, build_native_capacitance_topology,
    inspect_native_capacitance_mapping,
)

SCHEMA = 'sqe.capacitance-review-dossier.v1'
_MAX_DOSSIER_BYTES = 65536
_REQUIRED_FILES = (
    ('terminal_csv', 'sqe_em/outputFiles/terminal-C.csv'),
    ('palace_deck', 'sqe_em/sqe_em.json'),
    ('gmsh_mesh', 'sqe_em/sqe_em.msh'),
    ('native_log', 'sqe_em/palace-native.log'),
    ('native_sidecar', 'a03-native-artifacts.json'),
)
_CHECKS = (
    ('source_run_authenticity', 'Independently attest native solver execution, environment, version and source chain.'),
    ('geometry_registration', 'Review CAD/QDesign component-to-Gmsh face association, conductor surface coverage and orientation.'),
    ('ground_reference', 'Independently inspect actual PEC/reference ground, farfield and electrode isolation.'),
    ('terminal_identity', 'Review terminal labeling, ordered native physical groups, aliases and connected metal islands.'),
    ('selection_persistence', 'Authenticate the saved island selection and fixed/floating conductor policy in the project revision.'),
    ('materials_and_boundary_conditions', 'Review dielectric/metal geometry, material assumptions, units and boundary conditions.'),
    ('mesh_convergence', 'Repeat native electrostatic solves and quantify mesh/order/geometry uncertainty.'),
    ('junction_and_parasitics', 'Establish junction capacitance and missing pads, wiring and parasitic capacitances.'),
    ('floating_network_reduction', 'Validate ground/floating topology, constraints, Maxwell matrix reduction and charge conventions.'),
    ('independent_quantization', 'Independent physics review of circuit Hamiltonian, EJ/EC and scqubits model compatibility.'),
)


class CapacitanceReviewBlocked(ValueError):
    """Trusted Store provenance or mandatory scientific source screen is absent."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CapacitanceReviewBlocked(message)


def serialize_capacitance_review_dossier(dossier: dict) -> bytes:
    """Canonical UTF-8 JSON (no NaN, no incidental whitespace or nondeterministic keys)."""
    _require(type(dossier) is dict and dossier.get('schema') == SCHEMA and
             dossier.get('scientific_status') == 'BLOCKED' and
             dossier.get('fabrication') == 'HOLD' and
             dossier.get('b04_native_review') == 'BLOCKED_NOT_INDEPENDENTLY_REVIEWED' and
             dossier.get('em_to_scqubits_transfer') == 'BLOCKED' and
             dossier.get('native_solver_execution') ==
                 'ARTIFACT_RECORD_ONLY_NOT_REEXECUTED_OR_ATTESTED',
             'Not a scientifically blocked M3 capacitance dossier')
    review = dossier.get('review')
    _require(type(review) is dict and review.get('status') == 'NOT_APPROVED' and
             review.get('signatures') == [] and
             type(review.get('checklist')) is list and
             [c.get('id') for c in review['checklist'] if type(c) is dict] ==
                 [key for key, _ in _CHECKS] and
             all(type(c) is dict and c.get('status') == 'PENDING_INDEPENDENT_REVIEW'
                 for c in review['checklist']),
             'Dossier cannot attest missing scientific reviews')
    geometry = dossier.get('geometry')
    selection = dossier.get('selection')
    _require(type(geometry) is dict and
             geometry.get('cad_to_mesh_registration') ==
                 'BLOCKED_NO_INDEPENDENT_QDESIGN_TO_GMSH_FACE_REGISTRATION' and
             type(selection) is dict and selection.get('persistence') ==
                 'CALLER_SUPPLIED_NOT_VERIFIED_AS_SAVED_REVIEW',
             'Dossier cannot promote physical registration or saved selection')
    try:
        raw = (json.dumps(dossier, ensure_ascii=True, sort_keys=True,
                          separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError, OverflowError) as exc:
        raise CapacitanceReviewBlocked('Dossier is not strict JSON') from exc
    _require(len(raw) <= _MAX_DOSSIER_BYTES, 'Dossier exceeds privacy/size budget')
    return raw


def build_native_capacitance_review_dossier(store: Store, *, owner: str,
                                            project_id: str, run_id: str,
                                            saved_selection: dict) -> dict:
    """Inspect a trusted current-head Store run, without modifying it.

    The application must authenticate the requester and authorize *owner*.
    Store.project/run enforce owner/project isolation; run path must be within
    the trusted Store root. The selection is intentionally NOT treated as a
    signed or persisted expert decision, even if its v1 shape matches.

    All errors block the dossier rather than producing partial/misleading
    evidence; a caller cannot provide a manifest, project or SHA as authority.
    """
    _require(type(store) is Store and all(type(x) is str and 0 < len(x) <= 128
             for x in (owner, project_id, run_id)) and type(saved_selection) is dict,
             'Owner-authorized Store and explicit v1 selection required')
    try:
        project = store.project(owner, project_id)
        run = store.run(owner, project_id, run_id)
        revision = project['revision']
        _require(revision == project['head'] and run.get('state') == 'completed' and
                 run.get('revision_id') == revision and
                 run.get('engine') == 'sqdmetal_palace',
                 'Run is not a completed Palace result from current project head')
        run_folder = Path(run['path'])
        root = store.root.resolve()
        _require(run_folder.is_absolute() and not run_folder.is_symlink() and
                 run_folder.resolve().is_relative_to(root) and
                 run_folder.resolve() != root,
                 'Run directory is not contained in trusted Store storage')
        folder = run_folder / 'output'
        _require(folder.is_dir() and not folder.is_symlink(),
                 'Native output directory missing or linked')
        manifest_file = safe_file(folder, 'RESULT_MANIFEST.json')
        _require(0 < manifest_file.stat().st_size <= 128 * 1024,
                 'Native manifest exceeds verified source budget')
        manifest = json.loads(manifest_file.read_bytes())
        _require(type(manifest) is dict and manifest.get('study_id') == run['study_id'] and
                 manifest.get('kind') == 'capacitance' and
                 manifest.get('artifact_type') == 'palace.capacitance_matrix',
                 'Native manifest/study kind is not this completed capacitance run')
        ref = verify_manifest(folder, revision_id=revision,
                              project_digest=project['revision_digest'],
                              study_id=run['study_id'], engine='sqdmetal_palace')
        _require(ref.artifact_type == 'palace.capacitance_matrix' and
                 ref.manifest_sha256 == sha256(manifest_file.read_bytes()).hexdigest(),
                 'Native result manifest digest changed')
        candidate = build_native_capacitance_topology(
            folder, manifest, project, saved_selection=saved_selection)
        mapping = inspect_native_capacitance_mapping(
            folder, manifest, project, saved_selection=saved_selection)
        screen = native_capacitance_evidence(folder, manifest, project)
        _require(type(screen) is dict and
                 screen['capacitance_matrix_F'] == candidate['maxwell_matrix_f'] and
                 screen['conductor_order'] == candidate['terminal_labels'] and
                 screen['native_source_unit'] in ('F', 'fF'),
                 'Native CSV unit/order/matrix does not match topology')
        _require(candidate['source'] == mapping['source'] and
                 candidate['source']['manifest_sha256'] == ref.manifest_sha256 and
                 mapping['geometry_registration'].startswith('BLOCKED') and
                 mapping['reference_ground_group_ids'] ==
                 candidate['reference_ground']['native_group_ids'],
                 'M1 topology/mapping proof is inconsistent')
        _, _, mesh_format, _ = _read_mesh_groups(safe_file(folder, 'sqe_em/sqe_em.msh'))
        entries = {e['name']: e for e in manifest['artifacts']}
        _require(all(name in entries for _, name in _REQUIRED_FILES),
                 'Required hash-bound native evidence unavailable')
        artifact_hashes = {
            kind: {'sha256': entries[name]['sha256'], 'bytes': entries[name]['bytes']}
            for kind, name in _REQUIRED_FILES
        }
        ports = mapping['ordered_conductors']
        _require([p['component'] for p in ports] == candidate['terminal_labels'] and
                 [p['terminal_index'] for p in ports] == list(range(1, len(ports) + 1)),
                 'Mapping order differs from native matrix')
        pair = candidate['proposed_pair']
        fixed = candidate['other_terminal_policy']['fixed_zero']
        floating = candidate['other_terminal_policy']['floating_zero_charge']
        def role(label: str) -> str:
            if label == pair['island_a']:
                return 'proposed_island_a'
            if label == pair['island_b']:
                return 'proposed_island_b'
            if label in fixed:
                return 'fixed_zero_voltage'
            if label in floating:
                return 'floating_zero_charge'
            raise CapacitanceReviewBlocked('Unclassified terminal')
        terminals = [{'terminal_index': p['terminal_index'],
                      'component': p['component'],
                      'native_group_ids': list(p['native_group_ids']),
                      'proposed_role': role(p['component'])} for p in ports]
        # Last rehash + owner-scoped Store requery prevent an accepted dossier
        # from being assembled across two revisions/runs during inspection.
        final = verify_manifest(folder, revision_id=revision,
                                project_digest=project['revision_digest'],
                                study_id=run['study_id'], engine='sqdmetal_palace')
        latest = store.project(owner, project_id)
        final_run = store.run(owner, project_id, run_id)
        _require(final == ref and latest == project and final_run == run,
                 'Trusted source revision/run changed during dossier inspection')
        dossier = {
            'schema': SCHEMA,
            'scientific_status': 'BLOCKED', 'fabrication': 'HOLD',
            'b04_native_review': 'BLOCKED_NOT_INDEPENDENTLY_REVIEWED',
            'native_solver_execution': 'ARTIFACT_RECORD_ONLY_NOT_REEXECUTED_OR_ATTESTED',
            'em_to_scqubits_transfer': 'BLOCKED',
            'source': {
                'revision_id': revision, 'revision_digest': project['revision_digest'],
                'study_id': run['study_id'], 'engine': ref.engine,
                'engine_version_as_recorded': ref.engine_version,
                'manifest_sha256': ref.manifest_sha256,
                'artifacts': artifact_hashes,
                'verification': 'REHASHED_COMPLETED_OWNER_SCOPED_STORE_RUN',
            },
            'capacitance': {
                'matrix_kind': 'Palace Maxwell terminal capacitance',
                'native_csv_unit': screen['native_source_unit'],
                'matrix_entry_unit': 'F', 'terminal_count': len(terminals),
                'matrix_values_embedded': False,
                'status': 'SOFTWARE_SCREEN_ONLY_NO_PHYSICAL_CONVERGENCE',
            },
            'terminals': terminals,
            'ground': {'native_group_ids': mapping['reference_ground_group_ids'],
                       'native_bc': mapping['native_ground_bc'],
                       'farfield_bc': 'ground', 'in_maxwell_matrix': False,
                       'physical_ground_review': 'PENDING_INDEPENDENT_REVIEW'},
            'selection': {'proposed_islands': dict(pair),
                          'fixed_zero_voltage': list(fixed),
                          'floating_zero_charge': list(floating),
                          'persistence': 'CALLER_SUPPLIED_NOT_VERIFIED_AS_SAVED_REVIEW'},
            'geometry': {'native_mesh_format': 'Gmsh ASCII ' + mesh_format,
                         'mesh_length_scale_m': 1e-3,
                         'group_presence': 'HASH_VERIFIED_NATIVE_ELEMENT_TAGS_ONLY',
                         'cad_to_mesh_registration': mapping['geometry_registration']},
            'physical_limits': [
                'Group presence is not CAD/QDesign surface registration or connectivity.',
                'Process reviewed flag and native exit-code sidecar are not independent physical approval.',
                'Maxwell matrix SPD/sign screening is not mesh convergence or uncertainty quantification.',
                'Reference ground is excluded from terminal matrix; floating policies are proposals only.',
                'Junction capacitance, wiring parasitics and dielectric/interface uncertainties are not established.',
                'No EC/EJ reduction, junction/charge quantization or scqubits authorization is implied.',
            ],
            'review': {'status': 'NOT_APPROVED', 'signatures': [],
                       'checklist': [{'id': key, 'status': 'PENDING_INDEPENDENT_REVIEW',
                                      'required_evidence': requirement}
                                     for key, requirement in _CHECKS]},
        }
        serialize_capacitance_review_dossier(dossier)
        return dossier
    except CapacitanceReviewBlocked:
        raise
    except (ArtifactInvalid, CapacitanceTopologyBlocked, NotFound, OSError,
            ValueError, TypeError, KeyError, IndexError) as exc:
        raise CapacitanceReviewBlocked('Trusted native capacitance review source invalid: ' +
                                       type(exc).__name__) from exc
