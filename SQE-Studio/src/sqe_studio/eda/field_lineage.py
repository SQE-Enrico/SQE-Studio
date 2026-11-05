"""M11: verified Palace complex-field *readiness* for ordinary saved EDA runs.

Every caller MUST first verify the full revision-bound RESULT_MANIFEST and all
native file hashes.  This diagnostic re-reads the SHA-bound Palace PVD/PVTU/VTU
references and headers; it does NOT decode or align field vectors, calculate
MAC, identify a physical eigenmode or establish mesh convergence.  No solver
or file export is invoked and no raw 3D data are sent to the browser.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..interop.native_field import (inspect_palace_field_export,
    screen_cross_mesh_visualization_overlap, NativeFieldEvidenceError,
    NativeFieldVectorContractError)
from ..orchestration.artifacts import safe_file, ArtifactInvalid

SCHEMA = 'sqe.palace-verified-field-lineage.m11.v1'
PAIR_SCHEMA = 'sqe.palace-field-readiness-series.m11.v1'
DECK = 'sqe_em/sqe_em.json'
MESH = 'sqe_em/sqe_em.msh'
EIG = 'sqe_em/outputFiles/eig.csv'


# M13: fixed diagnostic vocabulary. No exception text, host paths, user model
# names or raw field payloads are ever transmitted to Results/portable QA.
# These categories are only a format/debugging aid, never physics evidence.
_FAILURE_CATEGORIES = (
    ('Native field artifact digest/size differs', 'ARTIFACT_HASH_MISMATCH', 'inventory',
     'Re-run the native job; a SHA-bound field artifact differs from the signed manifest.'),
    ('Palace field lineage mutated', 'ARTIFACT_CHANGED_DURING_INSPECTION', 'inventory',
     'Re-run after the native output directory is no longer being written.'),
    ('Native field artifact missing', 'ARTIFACT_NOT_AVAILABLE', 'inventory',
     'Verify that the complete native output folder was preserved in this run.'),
    ('Native field artifact exceeds size budget', 'FIELD_SIZE_BUDGET', 'inventory',
     'Review native field size and the bounded inspection policy.'),
    ('Native field export missing SHA-bound', 'DECK_MESH_EIG_MISSING', 'input',
     'Check that the solver deck, mesh and eig.csv are retained in the signed manifest.'),
    ('Field export deck differs', 'DECK_DIGEST_MISMATCH', 'input',
     'Verify native configuration provenance before inspecting field exports.'),
    ('Unverified Palace eigenmode/model', 'DECK_COORDINATE_CONTRACT', 'input',
     'Review eigenmode configuration, mesh identifier and Palace length unit L0.'),
    ('Unverified Palace eigenmode field-save', 'DECK_SAVE_CONTRACT', 'input',
     'Review Solver.Eigenmode.Save in the native Palace configuration.'),
    ('Saved field count exceeds', 'DECK_MODE_COUNT_CONTRACT', 'input',
     'Review Solver.Eigenmode.N and Save.'),
    ('Native Palace mode ordinal/frequency', 'EIG_CSV_FORMAT', 'spectrum',
     'Inspect the signed native eig.csv header, units, mode rows and solver settings.'),
    ('Invalid Palace Collection descriptor', 'PVD_XML_INVALID', 'collection',
     'Inspect the native Palace PVD collection XML.'),
    ('Unexpected native VTK collection type', 'PVD_COLLECTION_KIND', 'collection',
     'Verify that the PVD is a VTK Collection.'),
    ('Unbounded or missing Palace PVD', 'PVD_CYCLES_INVALID', 'collection',
     'Inspect the number of native export cycles in the PVD collection.'),
    ('Unsafe Palace PVD dataset reference', 'PVD_CYCLE_REFERENCE', 'collection',
     'Inspect PVD DataSet references relative to the export folder.'),
    ('Duplicate Palace PVD output cycle', 'PVD_DUPLICATE_CYCLE', 'collection',
     'Review repeated DataSet references in the native PVD.'),
    ('PVD references an unverified PVTU', 'PVD_UNSIGNED_PVTU', 'collection',
     'Check that every PVD-linked PVTU is declared by the native SHA manifest.'),
    ('Invalid Palace PUnstructuredGrid descriptor', 'PVTU_XML_INVALID', 'parallel',
     'Inspect the native parallel-grid descriptor.'),
    ('Native field has no bounded MPI piece', 'PVTU_PIECE_COUNT', 'parallel',
     'Review MPI piece references in the PVTU descriptor.'),
    ('Unsafe Palace VTU MPI piece reference', 'PVTU_PIECE_REFERENCE', 'parallel',
     'Check MPI piece paths in the PVTU descriptor.'),
    ('PVTU references an unverified VTU', 'PVTU_UNSIGNED_VTU', 'parallel',
     'Check that every referenced MPI VTU is SHA-bound.'),
    ('Duplicate VTU reference', 'PVTU_DUPLICATE_PIECE', 'parallel',
     'Review repeated MPI piece references.'),
    ('Invalid Palace VTU metadata', 'VTU_XML_HEADER_INVALID', 'piece',
     'Inspect the bounded VTU XML header preceding the appended binary.'),
    ('Truncated raw-appended native VTU', 'VTU_RAW_PAYLOAD_TRUNCATED', 'piece',
     'Check completion of native VTU raw-appended data.'),
    ('VTU has no bounded XML/AppendedData header', 'VTU_HEADER_BUDGET', 'piece',
     'Review raw-appended VTU metadata; the bounded scanner permits up to 16 MiB of XML header.'),
    ('Native VTU lacks point-sampled fields', 'VTU_POINT_DATA_MISSING', 'piece',
     'Check the VTK array association; PointData is required by the visualization reader.'),
    ('Native VTU lacks complex E vector components', 'VTU_COMPLEX_E_MISSING', 'piece',
     'Check the declared E_real and E_imag three-component PointData arrays.'),
    ('Incomplete native complex B components', 'VTU_COMPLEX_B_INCOMPLETE', 'piece',
     'Check that B_real and B_imag are both declared or both absent.'),
    ('Invalid native complex B vector components', 'VTU_COMPLEX_B_INVALID', 'piece',
     'Check the magnetic flux-density vector declaration.'),
    ('Native VTU has no unstructured grid piece', 'VTU_UNSTRUCTURED_PIECE_MISSING', 'piece',
     'Inspect the VTU UnstructuredGrid/Piece descriptor.'),
    ('Unsupported native VTU file kind', 'VTU_KIND_UNSUPPORTED', 'piece',
     'Verify the VTU UnstructuredGrid type.'),
    ('Unsupported XML entity declaration', 'VTK_UNSAFE_XML_ENTITY', 'descriptor',
     'Review the XML descriptor without bypassing its safety validation.'),
    ('Unsupported VTU XML entity', 'VTK_UNSAFE_XML_ENTITY', 'piece',
     'Review VTU XML content without bypassing its safety validation.'),
    ('Oversized Palace', 'VTK_DESCRIPTOR_BUDGET', 'descriptor',
     'Review descriptor size against the bounded inspection policy.'),
)


def _diagnostic_for_native_error(exc: Exception) -> tuple[str, str, str]:
    # The match input is an internal fixed exception message; only the known
    # category and a fixed remediation message leave the worker.
    if not isinstance(exc, NativeFieldEvidenceError):
        return ('UNEXPECTED_INSPECTION_EXCEPTION', 'inspection',
                'Inspect local qualification logs; no field evidence can be promoted.')
    message = str(exc)
    for prefix, code, phase, action in _FAILURE_CATEGORIES:
        if message.startswith(prefix):
            return code, phase, action
    return ('OTHER_NATIVE_FIELD_CONTRACT', 'inspection',
            'Inspect the local native-field format and signed export descriptors.')


def _blocked(status: str, reason: str, *, diagnostic=None) -> dict:
    out = {'schema': SCHEMA, 'status': status, 'reason': reason,
            'saved_mode_ordinals_unverified': [], 'field_sample_count': 0,
            'coordinate_registration': 'NOT_ESTABLISHED',
            'vector_norm_and_phase': 'NOT_ESTABLISHED',
            'physical_mode_identity': 'UNRESOLVED',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD'}
    if diagnostic is not None:
        code, phase, action = diagnostic
        out.update({'diagnostic_code': code, 'diagnostic_phase': phase,
                    'recommended_action': action})
    return out


def inspect_verified_run_field_lineage(folder: Path, manifest: dict) -> dict:
    """Inspect actual saved run files, after the caller's manifest verification.

    The native-field inspection additionally SHA-checks the descriptor graph.
    Invalid or incomplete fields remain an explicit BLOCKED diagnostic, not a
    failed scalar eigensolve. The manifest never gives a VTK URL to the client.
    """
    if (type(manifest) is not dict or manifest.get('engine') != 'sqdmetal_palace'
            or manifest.get('artifact_type') != 'palace.eigenmodes'):
        return _blocked('NOT_APPLICABLE', 'Not a native Palace eigenmode run')
    entries = manifest.get('artifacts')
    if type(entries) is not list:
        return _blocked('BLOCKED_INVALID_INVENTORY', 'Native artifact inventory unavailable')
    names = [a.get('name') for a in entries if type(a) is dict]
    if len(names) != len(entries) or len(set(names)) != len(names):
        return _blocked('BLOCKED_INVALID_INVENTORY', 'Ambiguous native field inventory')
    field_names = [name for name in names if isinstance(name, str) and
                   name.startswith('sqe_em/outputFiles/paraview/')]
    if not field_names:
        return _blocked('BLOCKED_NO_PARAVIEW_EXPORT',
                        'No saved ParaView PVD/PVTU/VTU field lineage; inspect Palace Eigenmode.Save and OutputFormats')
    if not {DECK, MESH, EIG} <= set(names):
        return _blocked('BLOCKED_INCOMPLETE_NATIVE_LINEAGE',
                        'Field artifacts exist but a SHA-bound Palace deck, mesh or eig.csv is missing')
    try:
        deck = safe_file(Path(folder), DECK)
        if not 0 < deck.stat().st_size <= 2_000_000:
            raise NativeFieldEvidenceError('Palace deck exceeds field inspection budget')
        config = json.loads(deck.read_text(encoding='utf-8'))
        if type(config) is not dict:
            raise NativeFieldEvidenceError('Palace deck must be a JSON object')
        evidence = inspect_palace_field_export(Path(folder), config, entries)
    except (ArtifactInvalid, NativeFieldEvidenceError, ValueError, TypeError,
            KeyError, OSError, UnicodeError) as exc:
        # Raw exception messages can include private file paths. Never forward
        # paths or field values to clients. The original output remains signed.
        return _blocked('BLOCKED_INVALID_NATIVE_FIELD_LINEAGE',
                        'Native field descriptor, data format or SHA-bound reference invalid',
                        diagnostic=_diagnostic_for_native_error(exc)) | (
                            {'field_declaration_diagnostic': exc.declaration_diagnostic}
                            if isinstance(exc, NativeFieldVectorContractError) else {})
    if evidence.get('status') != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY':
        return _blocked('BLOCKED_INCOMPLETE_NATIVE_LINEAGE',
                        'Palace did not provide an unambiguous complete native field collection')
    samples = evidence['field_samples']
    pieces = [p for s in samples for p in s['vtk_pieces']]
    return {'schema': SCHEMA, 'status': 'VERIFIED_FORMAT_LINEAGE_ONLY',
            'reason': 'SHA-bound Palace PVD/PVTU/VTU reference chain and complex E declarations verified; field payload, registration, material weights and normalization unreviewed',
            'field_sample_count': len(samples),
            'saved_mode_ordinals_unverified': [s['saved_collection_ordinal_not_mode_identity'] for s in samples],
            'output_cycles_not_physical_modes': [s['native_output_cycle_not_mode_identity'] for s in samples],
            'native_requested_mode_save_count': evidence['requested_native_modes'],
            'vtk_piece_count': len(pieces),
            'mpi_piece_count_by_sample': [len(s['vtk_pieces']) for s in samples],
            'all_pieces_declare_complex_E': True,
            'complex_B_declared_in_all_pieces': all(p['B_complex_declared'] for p in pieces),
            'metres_per_mesh_unit': evidence['metres_per_mesh_unit'],
            'mesh_sha256': evidence['mesh_sha256'],
            'deck_sha256': evidence['deck_sha256'],
            'native_eig_sha256': evidence['native_eig_sha256'],
            'coordinate_registration': 'NOT_ESTABLISHED',
            'vector_norm_and_phase': 'NOT_ESTABLISHED',
            'physical_mode_identity': 'UNRESOLVED',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD',
            'limitations': [
                'VTK PointData vectors are visualization samples, not native H(curl) FE basis coefficients',
                'PVD collection order is not a field-matched physical mode identifier',
                'Cross-mesh geometry, region tags, orientations, material weights and phase are unreviewed',
                'No MAC, field overlap, mode assignment, EPR calibration or fabrication qualification computed']}


def compare_verified_field_lineages(rows: list[dict] | tuple[dict, ...], *,
                                    verified_mesh_screen: dict | None = None,
                                    verified_pairwise_screen: dict | None = None) -> dict:
    """Show exactly which readiness gates still block two/three saved EM runs.

    `verified_mesh_screen` is M10's already-verified *input* screening, not a
    scientific certificate. No ordinal/frequency-based pairing is attempted.
    """
    if type(rows) not in (tuple, list) or len(rows) not in (2, 3) or any(
            type(row) is not dict or row.get('schema') != SCHEMA for row in rows):
        raise ValueError('Two or three M11 field-lineage screens required')
    statuses = [row['status'] for row in rows]
    available = all(s == 'VERIFIED_FORMAT_LINEAGE_ONLY' for s in statuses)
    distinct = None
    l0_consistent = None
    if available:
        distinct = len({row['mesh_sha256'] for row in rows}) == len(rows)
        l0_consistent = len({row['metres_per_mesh_unit'] for row in rows}) == 1
    mesh_inputs_match = (verified_mesh_screen is not None and
                         verified_mesh_screen.get('status') == 'NUMERICAL_INDEX_TREND_ONLY' and
                         verified_mesh_screen.get('same_nonmesh_inputs') is True)
    pair_inputs_match = (verified_pairwise_screen is not None and
                         verified_pairwise_screen.get('status') ==
                         'native_mode_index_differences_for_expert_review')
    if not available:
        status = 'BLOCKED_MISSING_OR_INVALID_FIELD_EXPORT'
    elif not distinct:
        status = 'BLOCKED_SAME_NATIVE_MESH_BYTES'
    elif not l0_consistent:
        status = 'BLOCKED_DIFFERENT_PALACE_COORDINATE_UNITS'
    elif ((len(rows) == 3 and not mesh_inputs_match) or
          (len(rows) == 2 and not pair_inputs_match)):
        status = 'BLOCKED_UNVERIFIED_NONMESH_INPUTS'
    else:
        status = 'FIELD_EXPORTS_READY_FOR_INDEPENDENT_REGISTRATION_REVIEW'
    return {'schema': PAIR_SCHEMA, 'status': status,
            'run_count': len(rows), 'run_statuses': statuses,
            'sample_counts': [r['field_sample_count'] for r in rows],
            'native_mesh_hashes_distinct': distinct,
            'palace_coordinate_units_identical': l0_consistent,
            'same_nonmesh_inputs_verified': mesh_inputs_match if len(rows) == 3 else pair_inputs_match,
            'coordinate_registration': 'NOT_ESTABLISHED',
            'complex_overlap': 'NOT_COMPUTED', 'physical_mode_identity': 'UNRESOLVED',
            'mesh_convergence': 'NOT_ESTABLISHED', 'em_to_hamiltonian': 'BLOCKED',
            'fabrication': 'HOLD',
            'required_next_evidence': [
                'SHA-verified native complex field payload decode for every saved mode',
                'Reviewed common coordinate frame, material/region maps and physical boundary identifiers',
                'Reviewed cross-mesh H(curl) basis projection, material-weighted overlap and global phase',
                'Mode ambiguity/degeneracy review plus frequency, Q and independent mesh convergence']}


M12_SCHEMA = 'sqe.palace-cross-mesh-visualization-review.m12.v1'

def screen_verified_saved_pair_overlap(roots: tuple[Path, Path], manifests: tuple[dict, dict],
                                       lineages: list[dict], pair_screen: dict) -> dict:
    """Optional, bounded visualization-only diagnostic for ordinary saved runs.

    The caller MUST have verified both full run manifests (revision and SHA).
    This never guesses a field-cycle/mode pairing. Ambiguous multi-cycle or MPI
    outputs remain BLOCKED until a reviewed selection and MPI registration path
    exist. For exactly one cycle and one piece per side, reuse the conservative
    existing B03 cross-mesh barycentric routine. No physical mode match or
    scientific convergence can result from a visualization overlap.
    """
    base = {'schema': M12_SCHEMA, 'status': 'BLOCKED_UNVERIFIED_SOURCE',
            'reason': 'Both complete saved native runs and compatible nonmesh inputs are required',
            'overlap': None, 'selection': 'NO_AUTOMATIC_MODE_PAIRING',
            'physical_coordinate_registration': 'NOT_ESTABLISHED',
            'physical_mode_identity': 'UNRESOLVED', 'mesh_convergence': 'NOT_ESTABLISHED',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD'}
    if (type(lineages) is not list or len(lineages) != 2 or
            any(type(row) is not dict or row.get('schema') != SCHEMA or
                row.get('status') != 'VERIFIED_FORMAT_LINEAGE_ONLY' for row in lineages) or
            type(pair_screen) is not dict or
            pair_screen.get('status') != 'native_mode_index_differences_for_expert_review'):
        return base
    if lineages[0].get('mesh_sha256') == lineages[1].get('mesh_sha256'):
        return {**base, 'status': 'BLOCKED_IDENTICAL_NATIVE_MESH',
                'reason': 'A cross-mesh review requires two different SHA-bound native meshes'}
    if lineages[0].get('metres_per_mesh_unit') != lineages[1].get('metres_per_mesh_unit'):
        return {**base, 'status': 'BLOCKED_COORDINATE_UNITS_DIFFER',
                'reason': 'Different native Palace length units prevent field comparison'}
    counts = [row['field_sample_count'] for row in lineages]
    piece_counts = [row['mpi_piece_count_by_sample'] for row in lineages]
    if counts != [1, 1]:
        return {**base, 'status': 'BLOCKED_MULTIPLE_OUTPUT_CYCLES',
                'reason': 'PVD cycles do not uniquely identify physical modes; explicit reviewed cycle pairing is required',
                'output_cycles_not_physical_modes': [row['output_cycles_not_physical_modes'] for row in lineages]}
    if piece_counts != [[1], [1]]:
        return {**base, 'status': 'BLOCKED_MPI_VISUALIZATION_REGISTRATION',
                'reason': 'Multi-piece native exports need independently checked MPI assembly and interpolation'}
    try:
        exports = []
        for root, manifest in zip(roots, manifests):
            root = Path(root)
            config_path = safe_file(root, DECK)
            config = json.loads(config_path.read_text(encoding='utf-8'))
            exports.append(inspect_palace_field_export(root, config, manifest['artifacts']))
        # Do not allocate/parse large VTK arrays merely to discover that the
        # diagnostic's 256-tetra per-grid budget would reject them.
        for export in exports:
            piece=export['field_samples'][0]['vtk_pieces'][0]
            count=piece.get('cell_count_declared')
            if type(count) is not str or not count.isdecimal() or not 0 < int(count) <= 256:
                return {**base, 'status': 'BLOCKED_MESH_EXCEEDS_VISUALIZATION_BUDGET',
                        'reason': 'Native field cell count exceeds the bounded 256-tetra visualization protocol'}
        numerical = screen_cross_mesh_visualization_overlap(
            Path(roots[0]), manifests[0]['artifacts'], exports[0],
            Path(roots[1]), manifests[1]['artifacts'], exports[1],
            coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')
    except ImportError:
        return {**base, 'status': 'BLOCKED_OPTIONAL_VTK_READER_UNAVAILABLE',
                'reason': 'VTK/numpy numerical reader is not available in the active Python environment'}
    except (ArtifactInvalid, NativeFieldEvidenceError, ValueError, TypeError, KeyError,
            IndexError, OSError, UnicodeError):
        # No private worker file paths, mesh points or vectors in HTTP reports.
        return {**base, 'status': 'BLOCKED_NATIVE_VISUALIZATION_PRECONDITIONS',
                'reason': 'VTK decode, tetra budget, domain coverage or coordinate/field preconditions failed'}
    return {**base, 'status': 'VISUALIZATION_OVERLAP_DIAGNOSTIC_ONLY',
            'reason': 'Phase-invariant visualization L2 overlap, not H(curl) mode matching',
            'overlap': numerical, 'selection': 'UNAMBIGUOUS_SINGLE_OUTPUT_CYCLE_ONLY',
            'physical_coordinate_registration': 'BLOCKED_REQUIRES_REVIEW',
            'physical_mode_identity': 'UNRESOLVED'}
