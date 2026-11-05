"""Research benchmark: native-run evidence and reviewed Palace kinetic deck preparation.

This is not an EM solver, Hamiltonian extractor, or qualification engine. The
material/geometry review and mode identity remain responsibilities of a physicist.
"""
from __future__ import annotations

import csv
from importlib import import_module
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import os

from sqe_studio.contracts import digest, fresh_project, validate_project
from sqe_studio.adapters.quantum_metal_adapter import _inspect_native_gds, validate_recipe
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.sqdmetal_palace_adapter import preflight
from sqe_studio.orchestration.artifacts import ArtifactInvalid, safe_file, verify_manifest


class BenchmarkBlocked(ValueError):
    """No result/modified boundary may be promoted to verified science."""


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _read_json(path: Path, maximum=128 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise BenchmarkBlocked('JSON file missing, linked or oversized')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise BenchmarkBlocked('Malformed JSON evidence') from exc


def _sha(path):
    h = sha256()
    with path.open('rb') as stream:
        for buf in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(buf)
    return h.hexdigest()


def resonator_project(*, execution='deck_only', mesh_min_um=12, mesh_max_um=120, mpi_ranks=2):
    """A simplified *adaptation* of SQDMetal's documented side-coupled CPW.

    The original has a CoupledLineTee not in A02's reviewed component list.
    This variant has **no** precisely equivalent coupling gap or literature
    benchmark frequency. Width/gap 10/6 um and length 3.7 mm are input values.
    The exploratory silicon constants follow SQDMetal's cryogenic 'silicon'
    material catalogue (epsilon_r=11.45, loss_tangent=2.7e-6), not
    independent measurement. Explicit expert review remains mandatory.
    """
    if execution not in ('deck_only', 'solve'):
        raise BenchmarkBlocked('execution must be deck_only or solve')
    model = fresh_project('Research CPW resonator', 'resonator')
    model['notes'] = ('Exploratory adaptation of SQDMetal Palace_Eigenmode_Res_Gmsh. '
                      'Not the original CoupledLineTee geometry. No measurement match or PDK approval.')
    model['layout'] = {'engine': 'quantum_metal',
                       'chip': {'width_mm': 4.8, 'height_mm': 2.4, 'thickness_um': 500},
                       'components': [
        {'kind': 'LaunchpadWirebond', 'name': 'LP1', 'x_mm': -2.0, 'y_mm': 0.0,
         'options': {'lead_length_um': 30, 'pad_height_um': 103, 'pad_width_um': 103, 'pad_gap_um': 60}},
        {'kind': 'LaunchpadWirebond', 'name': 'LP2', 'x_mm': 2.0, 'y_mm': 0.0,
         'orientation_deg': 180, 'options': {'lead_length_um': 30, 'pad_height_um': 103,
                                           'pad_width_um': 103, 'pad_gap_um': 60}},
        {'kind': 'OpenToGround', 'name': 'OTG', 'x_mm': -0.2, 'y_mm': -0.04,
         'orientation_deg': 180, 'options': {'width_um': 10, 'gap_um': 6}},
        {'kind': 'ShortToGround', 'name': 'STG', 'x_mm': 0.0, 'y_mm': -1.15,
         'orientation_deg': -90, 'options': {'width_um': 10}},
        {'kind': 'RouteStraight', 'name': 'Feedline', 'net': 'FeedlineN',
         'start': {'component': 'LP1', 'pin': 'tie'},
         'end': {'component': 'LP2', 'pin': 'tie'}, 'trace_width_um': 10, 'trace_gap_um': 6},
        {'kind': 'RouteMeander', 'name': 'Resonator', 'net': 'ResonatorN',
         'start': {'component': 'OTG', 'pin': 'open'},
         'end': {'component': 'STG', 'pin': 'short'}, 'trace_width_um': 10, 'trace_gap_um': 6,
         'total_length_mm': 3.7, 'fillet_um': 99.9, 'meander': {'spacing_um': 100}},
    ]}
    model['process'] = {'source': 'unverified', 'rules': {}, 'stack': [
        {'role': 'substrate', 'material': 'silicon', 'thickness_um': 500,
         'relative_permittivity': 11.45, 'loss_tangent': 2.7e-6},
        {'role': 'metal', 'material': 'aluminium', 'layer': 1,
         'thickness_nm': 100, 'em_model': 'PEC'},
        {'role': 'superstrate', 'material': 'vacuum', 'height_um': 500,
         'relative_permittivity': 1.0, 'loss_tangent': 0.0},
    ]}
    model['studies'] = [{'id': 'ResEigen', 'engine': 'sqdmetal_palace',
                         'kind': 'eigenmode', 'inputs': {'em': {
        'ground': {'kind': 'qdesign_ground_plane', 'layer': 1, 'verified': True},
        'boundaries': {'x_neg_um': 300, 'x_pos_um': 300, 'y_neg_um': 300,
                       'y_pos_um': 300, 'z_neg_um': 0, 'z_pos_um': 500,
                       'farfield': 'pec'},
        'ports': [{'index': 1, 'kind': 'cpw_launcher', 'component': 'LP1',
                   'length_um': 20, 'impedance_ohm': 50},
                  {'index': 2, 'kind': 'cpw_launcher', 'component': 'LP2',
                   'length_um': 20, 'impedance_ohm': 50}],
        'mesh': {'min_um': mesh_min_um, 'max_um': mesh_max_um,
                 'refinement_levels': [0, 1], 'relative_tolerance': 0.02},
        'execution': execution,
        'solver': {'order': 1, 'tolerance': 1e-7, 'max_iterations': 100,
                   'num_cpus': mpi_ranks, 'start_hz': 5e9, 'modes': 1},
    }}}]
    validate_recipe(model['layout'])
    validate_project(model)
    return model


def approve_exploratory_stack(model, *, reviewer, document: Path, source_url: str):
    """Explicit acknowledgement of engineering assumptions, NOT scientific approval."""
    if not isinstance(reviewer, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{2,47}', reviewer):
        raise BenchmarkBlocked('Reviewer must be a named ASCII identifier')
    if not isinstance(source_url, str) or not source_url.startswith('https://') or len(source_url) > 250:
        raise BenchmarkBlocked('Specify a traceable https source for material assumptions')
    document = Path(document)
    if document.is_symlink() or not document.is_file() or not 1 <= document.stat().st_size <= 1_000_000:
        raise BenchmarkBlocked('A real nonempty local review file is required')
    if model['process'].get('source') != 'unverified':
        raise BenchmarkBlocked('Only a pending exploratory stack can be reviewed')
    result = json.loads(_canonical(model))
    result['process']['source'] = 'reviewed'  # A03 ABI; NOT external accreditation.
    report = {'schema': 'sqe.research-material-review.v1',
              'reviewer': reviewer, 'review_evidence_sha256': _sha(document),
              'source_url': source_url,
              'input_process_sha256': digest(model['process']),
              'status': 'explicit_assumption_review_only_no_scientific_approval'}
    result['notes'] += '\nMaterial assumption review record SHA256: ' + digest(report)
    validate_project(result)
    preflight(result['studies'][0], result)
    return result, report


def _native_eig(path):
    if path.stat().st_size > 2_000_000 or path.is_symlink():
        raise BenchmarkBlocked('Untrusted Palace eig.csv')
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        head = next(reader, [])
        if len(head) < 2 or 'ghz' not in head[1].lower() or not ('f' in head[1].lower()):
            raise BenchmarkBlocked('Palace eigenfrequency column must declare GHz')
        modes = []
        for index, row in enumerate(reader, 1):
            if len(row) != len(head) or len(modes) >= 32:
                raise BenchmarkBlocked('Malformed or oversized native eigenmode table')
            try:
                # Palace (including 0.16.x) formats integer mode labels as
                # scientific-notation floats: 1.00e+00, 2.00e+00, ... .
                # Decimal accepts this exact representation without the
                # rounding/overflow ambiguity of float -> int conversion.
                native_mode = Decimal(row[0].strip())
                frequency = float(row[1])
            except (InvalidOperation, ValueError, IndexError) as exc:
                raise BenchmarkBlocked('Invalid mode index/frequency in Palace CSV') from exc
            if (not native_mode.is_finite() or native_mode != index
                    or not math.isfinite(frequency) or not 0 < frequency <= 1000):
                raise BenchmarkBlocked('Mode ordering/finite positive frequency required')
            modes.append({'mode_index': index, 'frequency_GHz': frequency})
    if not modes:
        raise BenchmarkBlocked('Palace eigenmode table is empty')
    return modes



def _raw_native_epr(path):
    """Only display native Palace port-EPR cells; NO Hamiltonian extraction."""
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise BenchmarkBlocked('Oversized/linked Palace EPR table')
    with path.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.reader(stream))
    if not 2 <= len(rows) <= 33 or not 2 <= len(rows[0]) <= 32:
        raise BenchmarkBlocked('Invalid native Palace EPR table dimensions')
    if any(len(row) != len(rows[0]) for row in rows):
        raise BenchmarkBlocked('Malformed Palace port-EPR.csv column structure')
    if any(not col.strip() or len(col) > 100 for col in rows[0]):
        raise BenchmarkBlocked('Unlabeled Palace EPR column')
    numeric = []
    for row in rows[1:]:
        try:
            values = [float(v) for v in row[1:]]
        except ValueError as exc:
            raise BenchmarkBlocked('Nonnumeric native Palace EPR cell') from exc
        if any(not math.isfinite(x) for x in values):
            raise BenchmarkBlocked('Nonfinite native Palace EPR value')
        numeric.append({'native_mode_label': row[0], 'native_signed_columns': values})
    return {'status': 'raw_native_palace_epr_not_quantization_or_validation',
            'columns_as_emitted': rows[0][1:], 'rows': numeric,
            'units_and_polarity': 'native_convention_requires_review'}

def assess_native_run(model, directory):
    """Read a real worker-produced run. Content integrity is not independent authenticity."""
    directory = Path(directory)
    manifest = _read_json(directory / 'RESULT_MANIFEST.json')
    validate_project(model)
    try:
        verify_manifest(directory, revision_id=manifest['revision_id'],
                        project_digest=digest(model), study_id='ResEigen',
                        engine='sqdmetal_palace')
    except (ArtifactInvalid, KeyError) as exc:
        raise BenchmarkBlocked('Native result manifest invalid or mismatched to saved model') from exc
    if (manifest.get('artifact_type') != 'palace.eigenmodes' or manifest.get('kind') != 'eigenmode'
            or 'not-reported' in manifest.get('engine_version', '').lower()
            or 'fixture' in manifest.get('engine_version', '').lower()):
        raise BenchmarkBlocked('A real named Palace eigenmode native version is required')
    sidecar = _read_json(safe_file(directory, 'a03-native-artifacts.json'))
    completion = sidecar.get('native_completion')
    if (type(sidecar) is not dict or sidecar.get('schema') != 'sqe.a03.native-artifacts.v1'
            or sidecar.get('execution') != 'solve'
            or not isinstance(completion, dict) or type(completion.get('exit_code')) is not int
            or completion.get('exit_code') != 0
            or not sidecar.get('versions', {}).get('palace')):
        raise BenchmarkBlocked('No successful Palace native solver completion evidence')
    expected_names = {r['name'] for r in manifest['artifacts']}
    if not {'sqe_em/outputFiles/eig.csv', 'sqe_em/palace-native.log'} <= expected_names:
        raise BenchmarkBlocked('Missing tracked native Palace eig.csv or solver log')
    modes = _native_eig(safe_file(directory, 'sqe_em/outputFiles/eig.csv'))
    epr = (_raw_native_epr(safe_file(directory, 'sqe_em/outputFiles/port-EPR.csv'))
           if 'sqe_em/outputFiles/port-EPR.csv' in expected_names else None)
    return {'schema': 'sqe.research-benchmark-observation.v1',
            'status': 'native_artifact_checked_not_independently_validated',
            'revision_id': manifest['revision_id'], 'project_digest': manifest['project_digest'],
            'manifest_sha256': _sha(directory / 'RESULT_MANIFEST.json'),
            'geometry_and_stack_sha256': digest({'layout': model['layout'], 'process': model['process']['stack']}),
            'engine_version': manifest['engine_version'], 'modes': modes,
            'raw_palace_epr': epr,
            'scientific_qualification': 'not_established', 'fabrication_status': 'HOLD'}



def trace_gds_mesh_lineage(model: dict, gds_output: Path, em_output: Path,
                           *, require_native_mesh_audit: bool = False) -> dict:
    """Rehash two worker artifacts and join *revision* lineage, never geometry.

    Sharing a QDesign recipe does not prove GDS polygons and Gmsh volume/surface
    tags correspond: no audited spatial/layer transform is currently exported
    by either worker. Optional native Gmsh group membership checking requires an
    installed native engine and confirms only 2D tag/face membership, NOT metal
    identity, mesh-to-GDS coordinates, field direction, or physical signoff.
    """
    if type(require_native_mesh_audit) is not bool:
        raise BenchmarkBlocked('Native mesh audit request must be explicit boolean')
    validate_project(model)
    validate_recipe(model['layout'])
    gds_output, em_output = Path(gds_output), Path(em_output)
    gds_manifest = _read_json(gds_output / 'RESULT_MANIFEST.json')
    em_manifest = _read_json(em_output / 'RESULT_MANIFEST.json')
    model_sha = digest(model)
    try:
        verify_manifest(gds_output, revision_id=gds_manifest['revision_id'],
                        project_digest=model_sha, engine='quantum_metal')
        verify_manifest(em_output, revision_id=em_manifest['revision_id'],
                        project_digest=model_sha, engine='sqdmetal_palace')
        if (gds_manifest['revision_id'] != em_manifest['revision_id']
                or gds_manifest.get('artifact_type') != 'quantum_metal.gdsii'
                or gds_manifest.get('kind') != 'gds_draft'
                or em_manifest.get('artifact_type') not in ('gmsh.mesh', 'palace.deck',
                                                            'palace.eigenmodes', 'palace.sparameters',
                                                            'palace.capacitance_matrix')):
            raise BenchmarkBlocked('GDS and EM artifacts are not the same saved design revision')
        gds_names = {r['name'] for r in gds_manifest['artifacts']}
        em_names = {r['name'] for r in em_manifest['artifacts']}
        if not {'quantum_metal_unqualified.gds', 'gds_hold.json'} <= gds_names or not {
                'sqe_em/sqe_em.msh', 'sqe_em/sqe_em.json',
                'a03-native-artifacts.json'} <= em_names:
            raise BenchmarkBlocked('Native GDS/mesh lineage artifacts are missing from the manifest')
        gds_file = safe_file(gds_output, 'quantum_metal_unqualified.gds')
        mesh_file = safe_file(em_output, 'sqe_em/sqe_em.msh')
        deck_file = safe_file(em_output, 'sqe_em/sqe_em.json')
        hold = _read_json(safe_file(gds_output, 'gds_hold.json'))
        sidecar = _read_json(safe_file(em_output, 'a03-native-artifacts.json'))
    except (ArtifactInvalid, KeyError, TypeError) as exc:
        raise BenchmarkBlocked('Stale, invalid or untracked GDS-to-mesh provenance') from exc
    if (type(hold.get('gds_structure')) is not dict
            or type(hold.get('layers_declared')) is not list
            or type(hold.get('qgeometry_layers')) is not list):
        raise BenchmarkBlocked('GDS structural inspection record missing')
    try:
        observed_gds = _inspect_native_gds(gds_file, set(hold['qgeometry_layers']), set(),
                                            set(hold['layers_declared']))
    except (EngineBlocked, ValueError, TypeError) as exc:
        raise BenchmarkBlocked('Native GDS structural inspection failed') from exc
    planned, chip = validate_recipe(model['layout'])
    gds_settings = model['layout'].get('gds')
    if (type(gds_settings) is not dict
            or type(gds_settings.get('layer_map')) is not dict
            or type(gds_settings['layer_map'].get('main')) is not list
            or type(gds_settings.get('negative_layers')) is not list):
        raise BenchmarkBlocked('Reviewed GDS layer map/polarity absent from saved project')
    declared_layers = gds_settings['layer_map']['main']
    negative_layers = gds_settings['negative_layers']
    geometry_layers = {p.layer for p in planned}
    geometry_layers.update(int(p.options['layer_subtract']) for p in planned
                           if 'layer_subtract' in p.options)
    if (hold['layers_declared'] != sorted(declared_layers)
            or hold.get('negative_mask_layers') != sorted(negative_layers)
            or hold['qgeometry_layers'] != sorted(geometry_layers)
            or not set(negative_layers) <= set(declared_layers)):
        raise BenchmarkBlocked('GDS layer mapping/polarity no longer matches saved layout')
    # A03 must report the ports in the original, operator-reviewed order.
    # A matching revision alone cannot bind native terminal identities.
    matching_studies = [study for study in model['studies']
                        if study['id'] == em_manifest.get('study_id')
                        and study['engine'] == 'sqdmetal_palace']
    if len(matching_studies) != 1:
        raise BenchmarkBlocked('No unique revision-bound EM study for this native mesh')
    em_inputs = matching_studies[0]['inputs']['em']
    port_convention = sidecar.get('port_convention')
    if (type(port_convention) is not dict
            or port_convention.get('index_base') != 1
            or port_convention.get('ordering') != 'reviewed SQDMetal creation order'
            or port_convention.get('ports') != em_inputs['ports']
            or port_convention.get('excited_port') != em_inputs['solver'].get('excited_port')):
        raise BenchmarkBlocked('Native EM port convention differs from reviewed design study')
    # Review the *actual* native Palace boundary records, not just metadata.
    # This establishes port numbering and referenced surface-tag literals;
    # only a separate native mesh/geometry audit could establish their physics.
    native_deck = _read_json(deck_file)
    native_boundaries = native_deck.get('Boundaries') if type(native_deck) is dict else None
    if type(native_boundaries) is not dict:
        raise BenchmarkBlocked('Native Palace port/boundary table missing')
    is_capacitance = matching_studies[0]['kind'] == 'capacitance'
    port_label = 'Terminal' if is_capacitance else 'LumpedPort'
    native_ports = native_boundaries.get(port_label)
    if (type(native_ports) is not list or len(native_ports) != len(em_inputs['ports'])
            or (not is_capacitance and native_boundaries.get('WavePort'))):
        raise BenchmarkBlocked('Native Palace port count/type differs from reviewed EM study')
    port_tags = {}
    for index, entry in enumerate(native_ports, 1):
        if type(entry) is not dict or type(entry.get('Index')) is not int or entry['Index'] != index:
            raise BenchmarkBlocked('Native Palace port index differs from reviewed ordering')
        attributes = entry.get('Attributes', [])
        if not is_capacitance and 'Elements' in entry:
            elements = entry['Elements']
            if type(elements) is not list or not elements or any(type(x) is not dict for x in elements):
                raise BenchmarkBlocked('Native Palace port elements malformed')
            attributes = [a for e in elements for a in e.get('Attributes', [])]
        if (type(attributes) is not list or not attributes
                or any(type(a) is not int or not 1 <= a <= 65535 for a in attributes)
                or len(attributes) != len(set(attributes))):
            raise BenchmarkBlocked('Native Palace port lacks unique positive physical tags')
        if is_capacitance and attributes != em_inputs['ports'][index-1]['native_attributes']:
            raise BenchmarkBlocked('Native capacitance terminal tag differs from reviewed study')
        port_tags[str(index)] = sorted(attributes)
    all_port_tags = [tag for tags in port_tags.values() for tag in tags]
    ground_label = 'Ground' if is_capacitance else 'PEC'
    ground = native_boundaries.get(ground_label)
    ground_tags = ground.get('Attributes') if type(ground) is dict else None
    if (type(ground_tags) is not list or not ground_tags
            or any(type(a) is not int or not 1 <= a <= 65535 for a in ground_tags)
            or len(ground_tags) != len(set(ground_tags))
            or len(all_port_tags) != len(set(all_port_tags))
            or set(all_port_tags) & set(ground_tags)):
        raise BenchmarkBlocked('Native Palace port tags duplicate or overlap ground/PEC')
    # Tag literals do not establish 3D geometry. This opt-in native audit only
    # proves group membership and disjoint group entities on the exact mesh.
    native_surface_audit = None
    if require_native_mesh_audit:
        native_surface_audit = _audit_native_surface_boundaries(
            mesh_file, set(all_port_tags) | set(ground_tags))
    if (observed_gds != hold['gds_structure']
            or hold.get('component_names') != [p.name for p in planned]
            or hold.get('route_net_names') != [p.net for p in planned if p.net]):
        raise BenchmarkBlocked('GDS structure/component lineage differs from saved QDesign recipe')
    if type(sidecar.get('units')) is not dict:
        raise BenchmarkBlocked('Native mesh unit provenance is missing')
    if (hold.get('fabrication_status') != 'HOLD'
            or hold.get('recipe_sha256') != digest(model['layout'])
            or hold.get('gds_sha256') != _sha(gds_file)
            or hold.get('gds_to_mesh_registration') !=
               'not_established_requires_native_mesh_and_independent_geometry_review'
            or hold.get('source') != 'Quantum Metal QGDSRenderer'
            or sidecar.get('schema') != 'sqe.a03.native-artifacts.v1'
            or sidecar.get('engine') != 'sqdmetal_palace'
            or not str(sidecar.get('geometry_source', '')).startswith('A02.build_qdesign(')
            or sidecar.get('units', {}).get('mesh_length') != 'mm'
            or sidecar.get('validation_status') != 'native_files_checked_not_scientifically_qualified'):
        raise BenchmarkBlocked('Native QDesign recipe, GDS hash or mesh provenance not established')
    return {
        'schema': 'sqe.research-gds-mesh-lineage.v1',
        'revision_id': gds_manifest['revision_id'], 'project_digest': model_sha,
        'layout_recipe_sha256': digest(model['layout']),
        'declared_chip_dimensions': {'width_mm': chip['width_mm'],
                                     'height_mm': chip['height_mm'],
                                     'thickness_um': chip['thickness_um']},
        'declared_gds_layers': sorted(declared_layers),
        'negative_mask_layers_not_process_qualified': sorted(negative_layers),
        'gds_manifest_sha256': _sha(gds_output / 'RESULT_MANIFEST.json'),
        'em_manifest_sha256': _sha(em_output / 'RESULT_MANIFEST.json'),
        'native_gds_sha256': _sha(gds_file), 'native_gmsh_mesh_sha256': _sha(mesh_file),
        'native_palace_deck_sha256': _sha(deck_file),
        'gds_native_layers': hold.get('gds_structure', {}).get('layers'),
        'gds_database_unit_m': observed_gds['database_unit_m'],
        'gds_user_unit_m': observed_gds['user_unit_m'],
        'gds_cell_local_xy_bounds_um_by_layer': observed_gds['xy_local_bounds_um_by_layer'],
        'gds_cell_local_xy_scope': observed_gds['xy_scope'],
        'gds_cell_local_polygon_primitive_area_um2_by_layer': observed_gds['polygon_primitive_area_um2_by_layer'],
        'gds_area_scope': observed_gds['area_scope'],
        'gds_component_names': hold.get('component_names'),
        'em_declared_port_convention': port_convention,
        'palace_native_port_surface_tags': port_tags,
        'palace_native_ground_surface_tags': sorted(ground_tags),
        'declared_process_stack_sha256': digest(model['process']['stack']),
        'declared_metal_process_layers': sorted({film['layer'] for film in model['process']['stack']
                                                  if film['role'] == 'metal'}),
        'native_mesh_surface_group_audit': native_surface_audit,
        'native_surface_group_membership': (
            '2d_tags_and_nonoverlapping_faces_checked_material_identity_unverified'
            if native_surface_audit is not None else 'BLOCKED_native_gmsh_audit_not_requested'),
        'shared_revision_and_declared_qdesign_recipe': True,
        'spatial_polygon_to_mesh_surface_registration': 'BLOCKED_not_verified',
        'metal_stack_to_mesh_material_registration': 'BLOCKED_requires_coordinate_and_film_review',
        'metal_surface_and_port_identity': 'BLOCKED_requires_native_tag_review',
        'native_port_to_gds_or_mesh_surface_registration': 'BLOCKED_not_verified',
        'scientific_qualification': 'not_established', 'fabrication_status': 'HOLD',
    }



# B04 native capacitance evidence readback, no substitute solver or predicted C values.

def _native_terminal_matrix(path: Path, *, unit: str, count: int) -> list[list[float]]:
    """Native Palace + legacy reviewed CSV layouts, always with source units.

    No caller-supplied units may override the tracked native CSV header.
    """
    from .native_capacitance_evidence import (parse_native_capacitance_table,
                                               NativeCapacitanceEvidenceError)
    try:
        values, _ = parse_native_capacitance_table(path, count=count, expected_unit=unit)
    except NativeCapacitanceEvidenceError as exc:
        raise BenchmarkBlocked(str(exc)) from exc
    return [[float(v) for v in row] for row in values]


def assess_native_capacitance_matrix(model: dict, native_output: Path, *, unit: str,
                                     reviewer: str, evidence_file: Path,
                                     symmetry_relative_tolerance: float = 1e-3,
                                     require_native_mesh_audit: bool = False) -> dict:
    """B04 read-only screening of an *actual* revision-bound Palace terminal-C.csv.

    Supports a strictly unit-labelled Maxwell capacitance matrix.  Neither
    conductor geometry -> field mapping nor EC/quantum Hamiltonian is approved;
    no scalar EC is guessed from diagonal C or an arbitrary floating node.
    """
    if type(require_native_mesh_audit) is not bool:
        raise BenchmarkBlocked('B04 native Gmsh audit request must be explicit boolean')
    validate_project(model)
    if model['process'].get('source') != 'reviewed':
        raise BenchmarkBlocked('B04 requires an explicitly reviewed exploratory material stack')
    if not isinstance(reviewer, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{2,47}', reviewer):
        raise BenchmarkBlocked('B04 requires named reviewer')
    evidence_file = Path(evidence_file)
    if (evidence_file.is_symlink() or not evidence_file.is_file()
            or not 1 <= evidence_file.stat().st_size <= 1_000_000):
        raise BenchmarkBlocked('B04 needs a nonempty independent review record')
    if (type(symmetry_relative_tolerance) not in (float, int)
            or not math.isfinite(symmetry_relative_tolerance)
            or not 0 < symmetry_relative_tolerance <= 0.01):
        raise BenchmarkBlocked('B04 symmetry tolerance must be explicit, finite and <=1%')
    native_output = Path(native_output)
    manifest = _read_json(native_output / 'RESULT_MANIFEST.json')
    try:
        verify_manifest(native_output, revision_id=manifest['revision_id'],
                        project_digest=digest(model), engine='sqdmetal_palace')
    except (ArtifactInvalid, KeyError, TypeError) as exc:
        raise BenchmarkBlocked('B04 native result is not revision/manifest verified') from exc
    # A03's production schema gate must accept the exact saved EM study;
    # this readback may not legitimize an unreviewed/malformed study.
    studies = [s for s in model['studies'] if s['id'] == manifest.get('study_id')
               and s['kind'] == 'capacitance' and s['engine'] == 'sqdmetal_palace']
    if (len(studies) != 1 or manifest.get('kind') != 'capacitance'
            or manifest.get('artifact_type') != 'palace.capacitance_matrix'
            or type(manifest.get('engine_version')) is not str
            or not manifest['engine_version']
            or 'fixture' in manifest['engine_version'].lower()):
        raise BenchmarkBlocked('B04 requires a completed native electrostatic study')
    try:
        preflight(studies[0], model)
    except EngineBlocked as exc:
        raise BenchmarkBlocked('B04 study fails production native EM preflight') from exc
    ports = studies[0]['inputs']['em']['ports']
    if (len(ports) < 2 or any(p.get('index') != i or p.get('kind') != 'conductor'
                             for i, p in enumerate(ports, 1))):
        raise BenchmarkBlocked('B04 requires >=2 reviewed and ordered conductor terminals')
    names = {entry['name'] for entry in manifest['artifacts']}
    required = {'sqe_em/outputFiles/terminal-C.csv', 'sqe_em/sqe_em.json',
                'sqe_em/sqe_em.msh', 'sqe_em/palace-native.log', 'a03-native-artifacts.json'}
    if not required <= names:
        raise BenchmarkBlocked('B04 missing manifest-tracked native outputs')
    sidecar = _read_json(safe_file(native_output, 'a03-native-artifacts.json'))
    if type(sidecar) is not dict:
        raise BenchmarkBlocked('B04 native sidecar must be a bounded JSON object')
    completion = sidecar.get('native_completion')
    convention = sidecar.get('port_convention')
    if (type(sidecar) is not dict or sidecar.get('schema') != 'sqe.a03.native-artifacts.v1'
            or sidecar.get('execution') != 'solve'
            or not isinstance(completion, dict) or type(completion.get('exit_code')) is not int
            or completion.get('exit_code') != 0
            or not sidecar.get('versions', {}).get('palace')
            or not isinstance(convention, dict)
            or convention.get('ordering') != 'reviewed SQDMetal creation order'
            or convention.get('index_base') != 1 or convention.get('ports') != ports):
        raise BenchmarkBlocked('B04 missing successful native Palace/terminal-convention provenance')
    deck_file = safe_file(native_output, 'sqe_em/sqe_em.json')
    deck = _read_json(deck_file)
    bc = deck.get('Boundaries') if type(deck) is dict else None
    terminals = bc.get('Terminal') if type(bc) is dict else None
    ground = bc.get('Ground') if type(bc) is dict else None
    if (type(terminals) is not list or len(terminals) != len(ports)
            or type(ground) is not dict or type(ground.get('Attributes')) is not list
            or not ground['Attributes']):
        raise BenchmarkBlocked('B04 native terminal/ground deck is absent or ambiguous')
    used = set(ground['Attributes'])
    if (len(used) != len(ground['Attributes'])
            or any(type(x) is not int or not 1 <= x <= 65535 for x in used)):
        raise BenchmarkBlocked('B04 invalid native ground attributes')
    for i, (port, terminal) in enumerate(zip(ports, terminals), 1):
        tags = port['native_attributes']
        if (type(terminal) is not dict or type(terminal.get('Index')) is not int
                or terminal.get('Index') != i
                or terminal.get('Attributes') != tags or type(tags) is not list
                or not tags or any(type(x) is not int or not 1 <= x <= 65535 for x in tags)
                or len(set(tags)) != len(tags) or used.intersection(tags)):
            raise BenchmarkBlocked('B04 native terminal overlaps/changes reviewed physical tags')
        used.update(tags)
    native_surface_audit = None
    if require_native_mesh_audit:
        native_surface_audit = _audit_native_surface_boundaries(
            safe_file(native_output, 'sqe_em/sqe_em.msh'), used)
    table = safe_file(native_output, 'sqe_em/outputFiles/terminal-C.csv')
    matrix = _native_terminal_matrix(table, unit=unit, count=len(ports))
    max_entry = max(abs(x) for row in matrix for x in row)
    if max_entry <= 0:
        raise BenchmarkBlocked('B04 empty/zero electrostatic capacitance matrix')
    max_skew = max(abs(matrix[i][j] - matrix[j][i])
                   for i in range(len(ports)) for j in range(len(ports)))
    relative_skew = max_skew / max_entry
    if relative_skew > symmetry_relative_tolerance:
        raise BenchmarkBlocked('B04 capacitance reciprocity/symmetry residual exceeds tolerance')
    # Maxwell matrix: Cii > 0, Cij <= 0, weak diagonal dominance.
    # A floating conductor may have a zero/common-mode energy; do not claim
    # positive definiteness, inversion, EC, or floating-node boundary validity.
    for i, row in enumerate(matrix):
        scale = symmetry_relative_tolerance * max_entry
        if (row[i] <= scale or any(x > scale for j, x in enumerate(row) if i != j)
                or row[i] + scale < sum(-min(0.0, x) for j, x in enumerate(row) if i != j)):
            raise BenchmarkBlocked('B04 Maxwell sign/diagonal dominance energy screening failed')
    return {'schema': 'sqe.research-capacitance-screen.v1',
            'status': 'native_csv_screened_not_physically_qualified',
            'execution_mode': 'NATIVE_ARTIFACT_READBACK_NOT_NEW_SOLVER_RUN',
            'revision_id': manifest['revision_id'], 'project_digest': digest(model),
            'native_manifest_sha256': _sha(native_output / 'RESULT_MANIFEST.json'),
            'native_mesh_sha256': _sha(safe_file(native_output, 'sqe_em/sqe_em.msh')),
            'native_deck_sha256': _sha(deck_file), 'native_matrix_csv_sha256': _sha(table),
            'native_log_sha256': _sha(safe_file(native_output, 'sqe_em/palace-native.log')),
            'palace_version': sidecar['versions']['palace'],
            'reviewer': reviewer, 'review_evidence_sha256': _sha(evidence_file),
            'conductor_order': [p['component'] for p in ports],
            'native_terminal_surface_tags': [p['native_attributes'] for p in ports],
            'capacitance_unit': 'F', 'capacitance_matrix_F': matrix,
            'symmetry_relative_residual': relative_skew,
            'symmetry_relative_tolerance': float(symmetry_relative_tolerance),
            'electrostatic_energy_screen': 'Maxwell_sign_and_diagonal_dominance_only',
            'native_mesh_surface_group_audit': native_surface_audit,
            'native_surface_group_membership': (
                '2d_tags_and_disjoint_faces_present_material_identity_unverified'
                if native_surface_audit is not None
                else 'BLOCKED_not_requested_or_native_runtime_unavailable'),
            'conductor_to_gmsh_spatial_registration': 'BLOCKED',
            'ground_and_floating_reference_review': 'BLOCKED',
            'Csum_and_EC_transfer': 'BLOCKED_requires_A12_reviewed_capacitance_reduction',
            'scientific_qualification': 'not_established', 'fabrication_status': 'HOLD'}


def compare_refinements(observations, *, mode_index=1, tolerance=0.02):
    """Numerical difference only. Expert must independently establish mode identity."""
    if type(mode_index) is not int or mode_index < 1 or not 0 < tolerance <= 0.2:
        raise BenchmarkBlocked('Invalid reviewed mode index/tolerance')
    if len(observations) != 2 or any(not isinstance(x, dict) for x in observations):
        raise BenchmarkBlocked('Two native observations are required')
    left, right = observations
    if left['geometry_and_stack_sha256'] != right['geometry_and_stack_sha256']:
        raise BenchmarkBlocked('Geometry/material conditions changed: not a mesh refinement comparison')
    if left['manifest_sha256'] == right['manifest_sha256']:
        raise BenchmarkBlocked('Cannot compare the same native run to itself')
    if any(mode_index > len(x['modes']) for x in (left, right)):
        raise BenchmarkBlocked('The manually selected mode is absent')
    a, b = (x['modes'][mode_index-1]['frequency_GHz'] for x in (left, right))
    rel = abs(b-a) / max(abs(b), abs(a))
    return {'schema': 'sqe.research-refinement-comparison.v1',
            'method': 'relative frequency change, no mode matching/interpolation',
            'mode_index_review_required': mode_index, 'first_GHz': a, 'second_GHz': b,
            'relative_difference': rel, 'requested_relative_tolerance': tolerance,
            'numerical_threshold_met': rel <= tolerance,
            'status': 'expert_mode_identification_and_convergence_review_required',
            'scientific_qualification': 'not_established'}



def _audit_native_surface_boundaries(mesh: Path, claimed_tags: set[int]) -> dict:
    """Read the native mesh, refusing missing or aliased port/ground 2D faces.

    Numerical Gmsh tags and disjoint groups are *not* conductor registration,
    spatial registration or a material/BC review.
    """
    audit = inspect_native_mesh_surface_groups(mesh)
    groups = audit['surface_entities_by_physical_tag']
    missing = claimed_tags - {int(tag) for tag in groups}
    if missing:
        raise BenchmarkBlocked('Native Palace surface tags absent from actual Gmsh 2D groups')
    observed_entities: dict[int, int] = {}
    for tag in sorted(claimed_tags):
        for entity in groups[str(tag)]:
            previous = observed_entities.setdefault(entity, tag)
            if previous != tag:
                raise BenchmarkBlocked('Native Palace port/ground tags share Gmsh 2D entities')
    return audit


def inspect_native_mesh_surface_groups(mesh: Path) -> dict:
    """Read real Gmsh 2D physical groups; no inference of metal/port meaning.

    An available native Gmsh installation is mandatory. Entity membership is
    observed, but physical-group names are *not* material classifications.
    """
    mesh = Path(mesh)
    if mesh.is_symlink() or not mesh.is_file() or not 1 <= mesh.stat().st_size <= 128 * 1024 * 1024:
        raise BenchmarkBlocked('Missing or unsafe native Gmsh mesh')
    try:
        gmsh = import_module('gmsh')
    except ImportError as exc:
        raise BenchmarkBlocked('Native Gmsh required to audit physical surface groups') from exc
    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.open(str(mesh))
        groups = gmsh.model.getPhysicalGroups(2)
        if not groups or len(groups) > 65535:
            raise BenchmarkBlocked('Native mesh has no bounded 2D physical groups')
        entities = {}
        for dim, tag in groups:
            if type(dim) is not int or dim != 2 or type(tag) is not int or not 1 <= tag <= 65535:
                raise BenchmarkBlocked('Invalid native Gmsh physical surface tag')
            members = [int(e) for e in gmsh.model.getEntitiesForPhysicalGroup(2, tag)]
            if not members or any(e <= 0 for e in members) or len(set(members)) != len(members):
                raise BenchmarkBlocked('Gmsh physical surface group lacks unique positive entities')
            if str(tag) in entities:
                raise BenchmarkBlocked('Duplicate Gmsh physical surface group')
            entities[str(tag)] = sorted(members)
    except BenchmarkBlocked:
        raise
    except Exception as exc:
        raise BenchmarkBlocked('Native Gmsh could not inspect mesh surface groups') from exc
    finally:
        if initialized:
            gmsh.finalize()
    return {'schema': 'sqe.research-gmsh-surface-groups.v1',
            'mesh_sha256': _sha(mesh), 'surface_entities_by_physical_tag': entities,
            'meaning': 'native_2d_group_presence_only_metal_identity_unverified'}


def _verify_prepared_kinetic_deck(experiment: Path, meta: dict, deck: Path, mesh: Path) -> None:
    """Fail closed on any post-review edits to boundary/material parameters."""
    record = _read_json(deck)
    review = _read_json(safe_file(experiment, 'SURFACE_REVIEW.json'))
    if type(record) is not dict or type(review) is not dict:
        raise BenchmarkBlocked('Kinetic deck and review must be JSON objects')
    selected = meta.get('surface_attributes')
    metals, excluded = review.get('conductor_attributes'), review.get('excluded_attributes')
    bounds = record.get('Boundaries')
    if (type(record.get('Problem')) is not dict
            or type(record.get('Model')) is not dict
            or record['Problem'].get('Type') != 'Eigenmode'
            or record['Problem'].get('Output') != 'outputFiles_kinetic'
            or record['Model'].get('Mesh') != 'sqe_em.msh'
            or type(bounds) is not dict or type(bounds.get('PEC')) is not dict
            or type(bounds.get('Impedance')) is not list or len(bounds['Impedance']) != 1
            or type(selected) is not list or not selected
            or any(type(a) is not int or not 1 <= a <= 65535 for a in selected)
            or len(set(selected)) != len(selected)
            or type(metals) is not list or type(excluded) is not list
            or not metals or not excluded
            or any(type(a) is not int or not 1 <= a <= 65535 for a in metals + excluded)
            or len(set(metals + excluded)) != len(metals) + len(excluded)
            or not set(selected) <= set(metals)
            or review.get('schema') != 'sqe.research-metal-surfaces.v1'
            or review.get('reviewer') != meta.get('reviewer')
            or review.get('basis') != 'manual_gmsh_physical_group_review'
            or review.get('source_deck_sha256') != meta.get('source_palace_deck_sha256')
            or review.get('source_mesh_sha256') != _sha(mesh)
            or meta.get('source_gmsh_mesh_sha256') != _sha(mesh)
            or meta.get('surface_review_sha256') != _sha(experiment / 'SURFACE_REVIEW.json')):
        raise BenchmarkBlocked('Kinetic surface review or mesh provenance changed')
    pec = bounds['PEC'].get('Attributes')
    impedance = bounds['Impedance'][0]
    if (type(pec) is not list or any(type(a) is not int for a in pec)
            or len(set(pec)) != len(pec)
            or set(pec) != (set(metals + excluded) - set(selected))
            or type(impedance) is not dict or set(impedance) != {'Attributes', 'Ls', 'Crack'}
            or impedance['Attributes'] != sorted(selected)
            or type(impedance['Crack']) is not bool
            or impedance['Crack'] != (meta.get('regime') == 'thick')
            or type(impedance['Ls']) not in (int, float)
            or type(meta.get('sheet_inductance_H_per_square')) not in (int, float)
            or not math.isfinite(impedance['Ls'])
            or not math.isfinite(meta['sheet_inductance_H_per_square'])
            or impedance['Ls'] != meta['sheet_inductance_H_per_square']
            or not 1e-16 <= impedance['Ls'] <= 1e-7):
        raise BenchmarkBlocked('Kinetic material/PEC/Impedance assignment differs from review')
    thickness = meta.get('thickness_nm')
    penetration = meta.get('penetration_depth_nm')
    if (type(thickness) not in (int, float) or type(penetration) not in (int, float)
            or not math.isfinite(thickness) or not math.isfinite(penetration)
            or not 0.01 <= thickness <= 1_000_000
            or not 0.01 <= penetration <= 1_000_000
            or meta.get('regime') not in ('thin', 'thick')
            or (meta['regime'] == 'thin' and thickness / penetration > 0.2)
            or (meta['regime'] == 'thick' and thickness / penetration < 5)):
        raise BenchmarkBlocked('Unreviewed film thickness, penetration depth or regime')
    for label, value in bounds.items():
        if label in ('PEC', 'Impedance'):
            continue
        for entry in (value if type(value) is list else [value]):
            if type(entry) is dict and 'Attributes' in entry:
                tags = entry['Attributes']
                if (type(tags) is not list or any(type(a) is not int for a in tags)
                        or len(set(tags)) != len(tags)):
                    raise BenchmarkBlocked('Unreviewed native boundary/port Attributes')
                if set(selected).intersection(tags):
                    raise BenchmarkBlocked('Kinetic metal surface overlaps native port/boundary')
    has_audit = 'native_gmsh_surface_audit' in review
    expected_evidence = ('native_gmsh_groups_present_operator_classification_unverified'
                         if has_audit else 'manual_only_native_mesh_group_presence_unverified')
    if meta.get('surface_domain_evidence') != expected_evidence:
        raise BenchmarkBlocked('Kinetic physical-domain audit status was altered')
    if has_audit:
        audit = inspect_native_mesh_surface_groups(mesh)
        if (review['native_gmsh_surface_audit'] != audit
                or not set(metals + excluded) <= set(map(int, audit['surface_entities_by_physical_tag']))):
            raise BenchmarkBlocked('Reviewed 2D Gmsh surface tags no longer match native mesh')



def prepare_kinetic_deck(native_output: Path, destination: Path, *, surface_attributes,
                         sheet_inductance_h, thickness_nm, penetration_depth_nm,
                         reviewer, evidence_file: Path, surface_review_file: Path, regime: str):
    """Experimental, independently reviewed Palace deck variant (not a worker result).

    Alters only a copy of Palace's native configuration, never its native mesh or
    the A03-verified original. SQE does NOT infer Ls from thickness or geometry.
    """
    native_output = Path(native_output)
    original_manifest = _read_json(native_output / 'RESULT_MANIFEST.json')
    try:
        verify_manifest(native_output, revision_id=original_manifest['revision_id'],
                        project_digest=original_manifest['project_digest'],
                        engine='sqdmetal_palace')
    except (ArtifactInvalid, KeyError) as exc:
        raise BenchmarkBlocked('Unverified A03 source manifest; never patch arbitrary solver files') from exc
    if (original_manifest.get('kind') != 'eigenmode'
            or original_manifest.get('artifact_type') not in ('palace.deck', 'palace.eigenmodes')):
        raise BenchmarkBlocked('Native A03 source must be a Palace eigenmode deck or solution')
    deck = safe_file(native_output, 'sqe_em/sqe_em.json')
    mesh = safe_file(native_output, 'sqe_em/sqe_em.msh')
    if not {'sqe_em/sqe_em.json', 'sqe_em/sqe_em.msh'} <= {
            a['name'] for a in original_manifest['artifacts']}:
        raise BenchmarkBlocked('Source mesh/deck absent from verified manifest')
    if not isinstance(reviewer, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{2,47}', reviewer):
        raise BenchmarkBlocked('Explicit named reviewer required')
    if type(surface_attributes) not in (tuple, list) or not surface_attributes or len(surface_attributes) > 16:
        raise BenchmarkBlocked('Explicit reviewed physical surface tags required')
    if any(type(tag) is not int or not 1 <= tag <= 65535 for tag in surface_attributes) or len(set(surface_attributes)) != len(surface_attributes):
        raise BenchmarkBlocked('Nonunique or invalid surface tags')
    for val in (sheet_inductance_h, thickness_nm, penetration_depth_nm):
        if type(val) not in (float, int) or not math.isfinite(val) or val <= 0:
            raise BenchmarkBlocked('Positive finite measured film parameters required')
    if not 1e-16 <= sheet_inductance_h <= 1e-7:
        raise BenchmarkBlocked('Sheet inductance must be finite H/square in reviewed range')
    if not (0.01 <= thickness_nm <= 1_000_000
            and 0.01 <= penetration_depth_nm <= 1_000_000):
        raise BenchmarkBlocked('Film thickness/penetration depth outside reviewed nm range')
    ratio = thickness_nm / penetration_depth_nm
    if regime not in ('thin', 'thick') or (regime == 'thin' and ratio > 0.2) or (regime == 'thick' and ratio < 5):
        raise BenchmarkBlocked('Film regime ambiguous: choose thin <=0.2 or thick >=5 of penetration depth')
    evidence_file = Path(evidence_file)
    if evidence_file.is_symlink() or not evidence_file.is_file() or not 1 <= evidence_file.stat().st_size <= 1_000_000:
        raise BenchmarkBlocked('Real independent material evidence file required')
    doc = _read_json(deck)
    if doc.get('Problem', {}).get('Type') != 'Eigenmode' or doc.get('Model', {}).get('Mesh') != 'sqe_em.msh':
        raise BenchmarkBlocked('Expected an untouched native Palace eigenmode deck/mesh')
    bounds = doc.get('Boundaries')
    if not isinstance(bounds, dict) or 'Impedance' in bounds or 'Superconductor' in bounds:
        raise BenchmarkBlocked('Unreviewed native material boundary already present')
    pec = bounds.get('PEC')
    if not isinstance(pec, dict) or not isinstance(pec.get('Attributes'), list):
        raise BenchmarkBlocked('Explicit PEC surface attribute list required')
    selected, original = set(surface_attributes), pec['Attributes']
    if (any(type(tag) is not int for tag in original)
            or len(original) != len(set(original)) or not selected <= set(original)):
        raise BenchmarkBlocked('PEC native surface tags are duplicate or selection is absent')
    if selected == set(original):
        raise BenchmarkBlocked('Cannot replace all PEC surfaces (farfield may be included)')
    surface_review_file = Path(surface_review_file)
    surface_review = _read_json(surface_review_file)
    if (surface_review.get('schema') != 'sqe.research-metal-surfaces.v1'
            or surface_review.get('source_deck_sha256') != _sha(deck)
            or surface_review.get('source_mesh_sha256') != _sha(mesh)
            or surface_review.get('reviewer') != reviewer
            or surface_review.get('basis') != 'manual_gmsh_physical_group_review'):
        raise BenchmarkBlocked('Metal-surface review must bind exact native mesh/deck and reviewer')
    metals = surface_review.get('conductor_attributes')
    other = surface_review.get('excluded_attributes')
    if (not isinstance(metals, list) or not metals or not isinstance(other, list) or not other
            or any(type(a) is not int or a <= 0 for a in metals+other)
            or len(set(metals+other)) != len(metals)+len(other)
            or set(metals+other) != set(original)
            or not selected <= set(metals)):
        raise BenchmarkBlocked('All native PEC surfaces must be classified: conductor or excluded farfield/other')
    if 'native_gmsh_surface_audit' in surface_review:
        observed = inspect_native_mesh_surface_groups(mesh)
        if (surface_review['native_gmsh_surface_audit'] != observed
                or not set(metals+other) <= set(map(int, observed['surface_entities_by_physical_tag']))):
            raise BenchmarkBlocked('Reviewed 2D Gmsh surface tags are absent or stale')
    for label, value in bounds.items():
        if label == 'PEC':
            continue
        for entry in (value if isinstance(value, list) else [value]):
            if isinstance(entry, dict) and selected.intersection(entry.get('Attributes', [])):
                raise BenchmarkBlocked('Selected surface overlaps another native boundary/port')
    if Path(destination).exists() or Path(destination).resolve().is_relative_to(native_output.resolve()):
        raise BenchmarkBlocked('Kinetic experiment destination must be a new, external directory')
    # Only create output after every preflight check. No simulated results produced.
    updated = json.loads(_canonical(doc))
    updated['Boundaries']['PEC']['Attributes'] = [a for a in original if a not in selected]
    updated['Boundaries']['Impedance'] = [{'Attributes': sorted(selected),
                                          'Ls': float(sheet_inductance_h),
                                          'Crack': regime == 'thick'}]
    updated['Problem']['Output'] = 'outputFiles_kinetic'
    meta = {'schema': 'sqe.research-kinetic-deck.v1',
            'status': 'reviewed_input_experimental_deck_not_a_native_result',
            'reviewer': reviewer, 'evidence_sha256': _sha(evidence_file),
            'surface_review_sha256': _sha(surface_review_file),
            'source_palace_deck_sha256': _sha(deck), 'source_gmsh_mesh_sha256': _sha(mesh),
            'source_result_manifest_sha256': _sha(native_output / 'RESULT_MANIFEST.json'),
            'sheet_inductance_H_per_square': float(sheet_inductance_h),
            'thickness_nm': float(thickness_nm), 'penetration_depth_nm': float(penetration_depth_nm),
            'regime': regime, 'surface_attributes': sorted(selected),
            'surface_domain_evidence': ('native_gmsh_groups_present_operator_classification_unverified'
                                        if 'native_gmsh_surface_audit' in surface_review else
                                        'manual_only_native_mesh_group_presence_unverified'),
            'caveats': ['Operator must verify metal surface tags in Gmsh',
                        'Requires solver execution and mesh convergence on actual laptop',
                        'Not approved as a native A03 worker artifact; no EPR/quantization approval']}
    generated_deck = json.dumps(updated, indent=2, sort_keys=True) + '\n'
    meta['generated_deck_sha256'] = sha256(generated_deck.encode('utf-8')).hexdigest()
    destination.mkdir(parents=True)
    created = ('sqe_em.msh', 'SURFACE_REVIEW.json', 'sqe_em_kinetic.json', 'KINETIC_REVIEW.json')
    try:
        shutil.copyfile(mesh, destination / created[0])
        shutil.copyfile(surface_review_file, destination / created[1])
        (destination / created[2]).write_bytes(generated_deck.encode('utf-8'))
        (destination / created[3]).write_text(json.dumps(meta, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        _verify_prepared_kinetic_deck(destination, meta, destination / created[2],
                                      destination / created[0])
    except Exception:
        # This directory was required not to exist; do not leave a partial deck.
        for name in created:
            (destination / name).unlink(missing_ok=True)
        destination.rmdir()
        raise
    return meta



def run_kinetic_native(experiment: Path, palace_binary: Path, *, cpus=2, timeout_seconds=900):
    """Execute actual, operator-selected Palace on the reviewed experimental deck.

    No synthetic output, no executable from a project/deck, no shell. An explicit
    local console action is required. This remains OUTSIDE the frozen A03 worker.
    """
    experiment = Path(experiment)
    meta = _read_json(experiment / 'KINETIC_REVIEW.json')
    if meta.get('schema') != 'sqe.research-kinetic-deck.v1':
        raise BenchmarkBlocked('Missing experimental kinetic source record')
    deck = safe_file(experiment, 'sqe_em_kinetic.json')
    mesh = safe_file(experiment, 'sqe_em.msh')
    if (_sha(deck) != meta.get('generated_deck_sha256')
            or _sha(mesh) != meta.get('source_gmsh_mesh_sha256')
            or _sha(safe_file(experiment, 'SURFACE_REVIEW.json')) != meta.get('surface_review_sha256')):
        raise BenchmarkBlocked('Source Palace deck or mesh changed after review')
    _verify_prepared_kinetic_deck(experiment, meta, deck, mesh)
    if type(cpus) is not int or not 1 <= cpus <= 8 or type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 7200:
        raise BenchmarkBlocked('Laptop solver bounds: 1-8 CPUs and 30-7200 seconds')
    binary = Path(palace_binary)
    if (not binary.is_absolute() or binary.is_symlink() or not binary.is_file()
            or not os.access(binary, os.X_OK)):
        raise BenchmarkBlocked('Palace must be an explicit absolute local executable')
    if (experiment / 'KINETIC_RUN_MANIFEST.json').exists() or (experiment / 'outputFiles_kinetic').exists():
        raise BenchmarkBlocked('Experimental output already exists; no overwrite')
    try:
        version = subprocess.run([str(binary), '--version'], timeout=15,
                                 capture_output=True, text=True, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkBlocked('Palace native version probe unavailable') from exc
    response = (version.stdout + '\n' + version.stderr).strip()
    if version.returncode != 0 or 'palace' not in response.lower():
        raise BenchmarkBlocked('Expected actual Palace native version report')
    log = experiment / 'palace-exec.log'
    with log.open('wb') as stream:
        try:
            done = subprocess.run([str(binary), '-np', str(cpus), '-nt', '1', deck.name],
                                  cwd=experiment, stdout=stream, stderr=subprocess.STDOUT,
                                  timeout=timeout_seconds, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BenchmarkBlocked('Palace solver failed or timed out; inspect palace-exec.log') from exc
    if done.returncode != 0:
        raise BenchmarkBlocked('Palace exited nonzero: inspect native palace-exec.log')
    eig = safe_file(experiment, 'outputFiles_kinetic/eig.csv')
    modes = _native_eig(eig)
    record = {'schema': 'sqe.research-kinetic-run.v1',
              'status': 'executed_native_palace_not_scientifically_validated',
              'palace_version': response.splitlines()[0][:200],
              'palace_binary_sha256': _sha(binary), 'exit_code': done.returncode,
              'generated_deck_sha256': _sha(deck), 'native_mesh_sha256': _sha(mesh),
              'kinetic_review_sha256': _sha(experiment / 'KINETIC_REVIEW.json'),
              'palace_stdout_stderr_sha256': _sha(log), 'native_eig_sha256': _sha(eig),
              'modes': modes, 'fabrication_status': 'HOLD',
              'scientific_qualification': 'not_established'}
    (experiment / 'KINETIC_RUN_MANIFEST.json').write_text(
        json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return record


def _check_kinetic_same_film_stack(model: dict, meta: dict) -> None:
    """B07 requires same reviewed metal film as the revision-bound PEC source."""
    validate_project(model)
    stack = model['process']
    films = [entry for entry in stack['stack'] if entry['role'] == 'metal']
    if (stack.get('source') != 'reviewed' or len(films) != 1
            or films[0].get('em_model') != 'PEC'
            or type(films[0].get('thickness_nm')) not in (int, float)
            or type(meta.get('thickness_nm')) not in (int, float)
            or not math.isclose(films[0]['thickness_nm'], meta['thickness_nm'], rel_tol=1e-9)
            or type(meta.get('sheet_inductance_H_per_square')) not in (int, float)
            or not 1e-16 <= meta['sheet_inductance_H_per_square'] <= 1e-7):
        raise BenchmarkBlocked('B07 PEC and sheet-Ls variants do not share reviewed source film/thickness')


def compare_kinetic_native(source_model: dict, source_output: Path,
                           experiment: Path, *, mode_index=1):
    """Difference of real Palace eigenmode frequencies, NOT a mode-identity proof."""
    source_output, experiment = Path(source_output), Path(experiment)
    baseline = assess_native_run(source_model, source_output)
    meta = _read_json(experiment / 'KINETIC_REVIEW.json')
    # Historical read-only subtraction remains possible for diagnosis, but
    # mismatched film assumptions must be visible and cannot become B07 PASS.
    try:
        _check_kinetic_same_film_stack(source_model, meta)
        same_film = True
    except BenchmarkBlocked:
        same_film = False
    record = _read_json(experiment / 'KINETIC_RUN_MANIFEST.json')
    if (meta.get('source_palace_deck_sha256') != _sha(safe_file(source_output, 'sqe_em/sqe_em.json'))
            or meta.get('source_gmsh_mesh_sha256') != _sha(safe_file(source_output, 'sqe_em/sqe_em.msh'))
            or meta.get('source_result_manifest_sha256') != _sha(source_output / 'RESULT_MANIFEST.json')):
        raise BenchmarkBlocked('Kinetic experiment not bound to this exact native source')
    eig = safe_file(experiment, 'outputFiles_kinetic/eig.csv')
    if (record.get('schema') != 'sqe.research-kinetic-run.v1'
            or record.get('status') != 'executed_native_palace_not_scientifically_validated'
            or record.get('exit_code') != 0
            or record.get('native_eig_sha256') != _sha(eig)
            or record.get('generated_deck_sha256') != _sha(safe_file(experiment, 'sqe_em_kinetic.json'))
            or record.get('kinetic_review_sha256') != _sha(experiment / 'KINETIC_REVIEW.json')
            or meta.get('surface_review_sha256') != _sha(safe_file(experiment, 'SURFACE_REVIEW.json'))
            or record.get('native_mesh_sha256') != _sha(safe_file(experiment, 'sqe_em.msh'))
            or record.get('palace_stdout_stderr_sha256') != _sha(safe_file(experiment, 'palace-exec.log'))
            or record.get('modes') != _native_eig(eig)):
        raise BenchmarkBlocked('Experimental kinetic solver provenance or output changed')
    _verify_prepared_kinetic_deck(experiment, meta,
                                  safe_file(experiment, 'sqe_em_kinetic.json'),
                                  safe_file(experiment, 'sqe_em.msh'))
    modes = _native_eig(eig)
    if type(mode_index) is not int or mode_index < 1 or mode_index > min(len(modes), len(baseline['modes'])):
        raise BenchmarkBlocked('Mode index absent or invalid')
    old = baseline['modes'][mode_index-1]['frequency_GHz']
    new = modes[mode_index-1]['frequency_GHz']
    return {'schema':'sqe.research-kinetic-comparison.v1',
            'mode_index_requires_expert_correspondence':mode_index,
            'pec_f_GHz':old, 'surface_inductance_f_GHz':new,
            'delta_GHz':new-old,
            'relative_delta':(new-old)/old,
            'sheet_inductance_H_per_square':meta['sheet_inductance_H_per_square'],
            'method':'native Palace PEC vs experimental impedance boundary on same mesh',
            'kinetic_film_correspondence': ('reviewed_pec_stack_thickness_matches'
                                            if same_film else 'BLOCKED_film_not_same_as_source_pec_stack'),
            'kinetic_experiment_film_thickness_nm':meta['thickness_nm'],
            'reviewed_pec_stack_sha256':digest(source_model['process']['stack']),
            'physical_mode_identity':'BLOCKED_requires_registered_complex_fields',
            'status':'read_only_difference_physical_validity_unverified',
            'fabrication_status':'HOLD', 'scientific_qualification':'not_established'}
