"""Research benchmark: native-run evidence and reviewed Palace kinetic deck preparation.

This is not an EM solver, Hamiltonian extractor, or qualification engine. The
material/geometry review and mode identity remain responsibilities of a physicist.
"""
from __future__ import annotations

import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import os

from sqe_studio.contracts import digest, fresh_project, validate_project
from sqe_studio.adapters.quantum_metal_adapter import validate_recipe
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


def resonator_project(*, execution='deck_only', mesh_min_um=12, mesh_max_um=120):
    """A simplified *adaptation* of SQDMetal's documented side-coupled CPW.

    The original has a CoupledLineTee not in A02's reviewed component list.
    This variant has **no** precisely equivalent coupling gap or literature
    benchmark frequency. Width/gap 10/6 um and length 3.7 mm are input values.
    Material source remains unverified until explicit expert review.
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
         'relative_permittivity': 11.7, 'loss_tangent': 0.0},
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
                   'num_cpus': 2, 'start_hz': 5e9, 'modes': 1},
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
                mode = int(row[0].strip())
                frequency = float(row[1])
            except (ValueError, IndexError) as exc:
                raise BenchmarkBlocked('Invalid mode index/frequency in Palace CSV') from exc
            if mode != index or not math.isfinite(frequency) or not 0 < frequency <= 1000:
                raise BenchmarkBlocked('Mode ordering/finite positive frequency required')
            modes.append({'mode_index': mode, 'frequency_GHz': frequency})
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
    if (sidecar.get('schema') != 'sqe.a03.native-artifacts.v1'
            or sidecar.get('execution') != 'solve'
            or not isinstance(completion, dict) or completion.get('exit_code') != 0
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
            'caveats': ['Operator must verify metal surface tags in Gmsh',
                        'Requires solver execution and mesh convergence on actual laptop',
                        'Not approved as a native A03 worker artifact; no EPR/quantization approval']}
    generated_deck = json.dumps(updated, indent=2, sort_keys=True) + '\n'
    meta['generated_deck_sha256'] = sha256(generated_deck.encode('utf-8')).hexdigest()
    destination.mkdir(parents=True)
    shutil.copyfile(mesh, destination / 'sqe_em.msh')
    shutil.copyfile(surface_review_file, destination / 'SURFACE_REVIEW.json')
    (destination / 'sqe_em_kinetic.json').write_text(generated_deck, encoding='utf-8')
    (destination / 'KINETIC_REVIEW.json').write_text(json.dumps(meta, indent=2, sort_keys=True) + '\n', encoding='utf-8')
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


def compare_kinetic_native(source_model: dict, source_output: Path,
                           experiment: Path, *, mode_index=1):
    """Difference of real Palace eigenmode frequencies, NOT a mode-identity proof."""
    source_output, experiment = Path(source_output), Path(experiment)
    baseline = assess_native_run(source_model, source_output)
    meta = _read_json(experiment / 'KINETIC_REVIEW.json')
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
            'status':'read_only_difference_physical_validity_unverified',
            'fabrication_status':'HOLD', 'scientific_qualification':'not_established'}
