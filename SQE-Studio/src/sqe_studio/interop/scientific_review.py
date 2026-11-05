"""Verified native EM scientific screening, never automatic mode identification.

This review consumes the *same* hash-verified qualification ZIP as the desktop
convergence and native observables readers. Scalar comparisons cannot certify
mode identity, physical convergence, EPR parameters or fabrication.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

from .em_convergence import analyze_report_zip, ConvergenceEvidenceError
from .em_observables import assess_observables
from .native_field import (inspect_palace_field_export, inspect_local_palace_field_values,
                           compare_same_mesh_fields, inspect_palace_driven_sparameters,
                           inspect_palace_signed_port_kappa, NativeFieldEvidenceError)

SCHEMA = 'sqe.em-scientific-screen.v1'
ZIP_MAX = 12_000_000
TAGS = ('native_palace_solve', 'native_palace_refinement', 'native_palace_third')


def _eig_quality(raw: bytes) -> float:
    if not raw or len(raw) > 256_000:
        raise ConvergenceEvidenceError('Missing/oversized Palace eigenmode table')
    try:
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        head = [cell.strip().lower() for cell in rows[0]]
        if len(head) < 4 or len(rows) != 2 or head[0] != 'm' or head[3] != 'q':
            raise ValueError('Unrecognized eigenmode Q columns or mode count')
        values = [float(cell) for cell in rows[1]]
        if len(values) != len(head) or not all(math.isfinite(v) for v in values):
            raise ValueError('Malformed/nonfinite Palace eigenmode table')
        if values[0] != 1 or values[1] <= 0 or values[3] <= 0:
            raise ValueError('Invalid native eigenvalue index, frequency or Q')
        return values[3]
    except (UnicodeError, ValueError, IndexError) as exc:
        raise ConvergenceEvidenceError('Invalid native Palace eigenmode quality data') from exc


def _relative(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b))


def _screen_status(value: float, threshold: float) -> str:
    return 'NUMERIC_THRESHOLD_MET_NOT_PHYSICALLY_QUALIFIED' if value <= threshold else 'NUMERIC_DRIFT_REQUIRES_REVIEW'


def screen_native_field_pair(left_workspace: Path, left_config: dict, left_artifacts: list[dict],
                             right_workspace: Path, right_config: dict, right_artifacts: list[dict]) -> dict:
    """Optional local, *read-only* visualization overlap diagnostic.

    The native report ZIP intentionally excludes large/private mesh and VTU
    files. The two workspaces must originate from real, SHA-bound Palace
    worker manifests; this function does NOT load unverified ZIP contents.
    Even an overlap of 1 cannot certify physical mode identity without expert
    material/phase review and comparable H(curl) discretizations.
    """
    left = inspect_palace_field_export(left_workspace, left_config, left_artifacts)
    right = inspect_palace_field_export(right_workspace, right_config, right_artifacts)
    if (left['status'] != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY' or
            right['status'] != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY'):
        raise NativeFieldEvidenceError('Native complex field missing: mode-matching gate remains BLOCKED')
    # MPI visualization pieces can be verified and locally assembled, but their
    # numeric overlap is not an approved physical or FE mode-registration path.
    mpi = any(len(sample['vtk_pieces']) != 1 for export in (left, right)
              for sample in export['field_samples'])
    # No interpolation can be inferred solely from coordinate bounds or a
    # PVD ordinal. Retain bounded independent field hashes for the B03 handoff
    # even when the two genuinely refined meshes are different.
    cross_mesh = (left['mesh_sha256'] != right['mesh_sha256'] or
                  left['metres_per_mesh_unit'] != right['metres_per_mesh_unit'])
    if mpi or cross_mesh:
        local_left = inspect_local_palace_field_values(left_workspace, left_config, left_artifacts)
        local_right = inspect_local_palace_field_values(right_workspace, right_config, right_artifacts)
        result = {'status': ('BLOCKED_CROSS_MESH_HCURL_REGISTRATION_NOT_REVIEWED' if cross_mesh
                             else 'BLOCKED_MPI_PIECE_FIELDS_NOT_APPROVED_FOR_MODE_OVERLAP'),
                  'mode_identity': 'UNRESOLVED',
                  'left_mesh_sha256': left['mesh_sha256'],
                  'right_mesh_sha256': right['mesh_sha256'],
                  'reason': ('Cross-mesh interpolation needs a reviewed coordinate/unit, material-region, orientation, '
                             'FE basis and overlap-norm protocol; scalar/ordinal matching is forbidden' if cross_mesh
                             else 'MPI visualization seams are not reviewed H(curl) material-weighted mesh registration')}
    else:
        result = compare_same_mesh_fields(left_workspace, left_artifacts, left,
                                          right_workspace, right_artifacts, right)
        local_left = inspect_local_palace_field_values(left_workspace, left_config, left_artifacts)
        local_right = inspect_local_palace_field_values(right_workspace, right_config, right_artifacts)
    return {'schema': 'sqe.em-complex-field-scientific-screen.v1',
            'field_overlap': result,
            'local_sample_evidence': {'left': local_left, 'right': local_right},
            'surface_registration': 'BLOCKED_NO_REVIEWED_GMSH_SURFACE_TAG_MAP',
            'H_field': 'BLOCKED_NO_REVIEWED_B_TO_H_CONSTITUTIVE_TRANSFORMATION',
            'mode_identity': 'UNRESOLVED_REQUIRES_EXPERT_SCIENTIFIC_REVIEW',
            'physical_convergence': 'NOT_ESTABLISHED',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD'}


def review_scientific_report(source_zip: Path) -> dict:
    """Screen frequency, Q, ports separately; require no additional Palace run."""
    source_zip = Path(source_zip)
    series = analyze_report_zip(source_zip)  # every member + worker PASS verified
    scalar = assess_observables(source_zip)
    if len(series['points']) != len(scalar['points']):
        raise ConvergenceEvidenceError('Inconsistent native solve counts')
    quality = []
    with zipfile.ZipFile(source_zip) as bundle:
        for tag in TAGS[:len(series['points'])]:
            name = f'native/{tag}-eig.csv'
            if name not in bundle.namelist():
                raise ConvergenceEvidenceError('Native eig.csv not included in verified evidence')
            quality.append(_eig_quality(bundle.read(name)))
        # Current reference collects scalar tabulations, not aligned full vector
        # fields. If future reports include probe data, a separate explicit
        # coordinate/complex-field normalization review is still mandatory.
        field_names = [n for n in bundle.namelist()
                       if n.startswith('native/') and ('probe-E' in n or 'field-' in n.lower())]
    rows = []
    flags = list(scalar['advisory_flags'])
    for i, (freq, observed, qtot) in enumerate(zip(series['points'], scalar['points'], quality), 1):
        if observed['status'] != 'NUMERIC_INDICATORS_ONLY':
            raise ConvergenceEvidenceError('Incomplete native port/energy evidence')
        qext, kappas = observed['q_ext'], observed['kappa_ext_GHz']
        if len(qext) != len(kappas) or not 1 <= len(qext) <= 16:
            raise ConvergenceEvidenceError('Unpaired native port Q/kappa columns')
        ports = []
        for j, (q, k) in enumerate(zip(qext, kappas), 1):
            if not math.isfinite(q) or q <= 0 or not math.isfinite(k):
                raise ConvergenceEvidenceError('Invalid native external Q or kappa')
            expected = freq['frequency_GHz'] / q
            relative = abs(abs(k) - expected) / expected
            # This is ONLY a check of the numerical magnitude convention seen in
            # reported outputs. A sign discrepancy requires expert interpretation.
            status = ('SIGN_CONVENTION_REVIEW' if k < 0 else
                      'MAGNITUDE_CONVENTION_REVIEW' if relative > 0.02 else
                      'NUMERIC_MAGNITUDE_COHERENT_NOT_PHYSICALLY_QUALIFIED')
            ports.append({'port_index': j, 'q_ext': q, 'native_kappa_ext_GHz': k,
                          'frequency_over_q_ext_GHz': expected,
                          'kappa_abs_relative_mismatch': relative, 'status': status})
            if relative > 0.02:
                flags.append({'type': 'KAPPA_MAGNITUDE_MISMATCH', 'point': i,
                              'port': j, 'relative_mismatch': relative})
        rows.append({'point':i,'frequency_GHz':freq['frequency_GHz'],
                     'native_q_total':qtot,'ports':ports,
                     'energy_electric_over_magnetic':observed['energy_electric_over_magnetic'],
                     'numeric_eigensolve_converged':freq['solver_converged_tol_in_log']})
    freq_changes, q_changes, port_changes = [], [], []
    for i in range(1, len(rows)):
        old, new = rows[i-1], rows[i]
        fchange = _relative(old['frequency_GHz'],new['frequency_GHz'])
        freq_changes.append({'between_points':[i,i+1], 'relative_change':fchange,
                             'status':_screen_status(fchange,0.02)})
        qchange = _relative(old['native_q_total'],new['native_q_total'])
        q_changes.append({'between_points':[i,i+1], 'relative_change':qchange,
                          'status':_screen_status(qchange,0.10)})
        for before, after in zip(old['ports'],new['ports']):
            change = _relative(before['q_ext'],after['q_ext'])
            port_changes.append({'between_points':[i,i+1], 'port_index':before['port_index'],
                                 'q_ext_relative_change':change,
                                 'native_kappa_sign_changed': (before['native_kappa_ext_GHz'] < 0)
                                 != (after['native_kappa_ext_GHz'] < 0),
                                 'status': ('SIGN_AND_Q_REVIEW' if (before['native_kappa_ext_GHz'] < 0)
                                            != (after['native_kappa_ext_GHz'] < 0) else
                                            _screen_status(change,0.10))})
    return {'schema':SCHEMA, 'source_report_sha256':series['source_report_sha256'],
            'verification':'Source ZIP member hashes and successful native worker manifests checked',
            'solver_results':'VERIFIED_NATIVE_EIGENMODE_OUTPUT_NOT_INDEPENDENTLY_VALIDATED',
            'field_overlap':{'status':'BLOCKED_NO_COMMON_COMPLEX_VECTOR_FIELDS',
                             'detected_field_named_members':len(field_names),
                             'native_complex_export_evidence':'NOT_INCLUDED_IN_BOUNDED_PORTABLE_REPORT',
                             'reason':'No verified common-grid phase-aware complex E/H field vectors and normalization; scalar tables cannot identify modes'},
            'mode_identity':'UNRESOLVED',
            'frequency':{'adjacent':freq_changes,'last_step_numeric_screen':freq_changes[-1]['status'],
                         'physical_convergence':'NOT_ESTABLISHED'},
            'total_q':{'adjacent':q_changes,'last_step_numeric_screen':q_changes[-1]['status'],
                       'physical_convergence':'NOT_ESTABLISHED'},
            'external_ports':{'adjacent':port_changes,
                              'status':'EXPERT_REVIEW_REQUIRED_NOT_VALIDATED'},
            'points':rows,'advisory_flags':flags,
            'optimization':'BLOCKED_REQUIRES_EXPERT_MODE_AND_LOSS_REVIEW',
            'em_to_hamiltonian':'BLOCKED','fabrication':'HOLD',
            'limitations':['Numeric thresholds are screening heuristics, not error bars or physical acceptance',
                           'Q and port coupling require validated physical conventions and material/port models',
                           'Solver convergence, mesh-frequency stabilization and modal identity are distinct claims']}


def save_scientific_review(source_zip: Path, destination: Path) -> dict:
    """Produce one small, portable, self-checking review ZIP; no native rerun.

    Embed the bounded verified source evidence to permit independent checking
    after the user uploads the report. No files are fetched from user projects.
    """
    source_zip = Path(source_zip)
    destination = Path(destination).absolute()
    if destination.suffix.lower() != '.zip' or destination.is_symlink() or destination == source_zip.absolute():
        raise ValueError('Review destination must be a different ZIP file')
    review = review_scientific_report(source_zip)
    data = source_zip.read_bytes()
    if len(data) > ZIP_MAX:
        raise ValueError('Source native report too large to embed')
    review_bytes = (json.dumps(review,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    summary = ('# SQE Studio — scientific EM review (screening only)\n\n'
               'Source: verified native Palace report; no solver executed for this review.\n'
               'Mode identity: UNRESOLVED; field overlap: BLOCKED.\n'
               'Frequency convergence, Q, ports, extraction and optimization: NOT QUALIFIED.\n'
               'Fabrication: HOLD. Negative coupling signs are not automatically corrected.\n'
               'Share only after reviewing evidence/logs for private details.\n').encode('utf-8')
    payload = {'SCIENTIFIC_REVIEW.json':review_bytes,'SUMMARY.md':summary,
               'evidence/native-report.zip':data}
    payload['INTEGRITY.json'] = (json.dumps({'schema':'sqe.qualification-file-hashes.v1',
        'files':{name:hashlib.sha256(value).hexdigest() for name,value in sorted(payload.items())}},
        sort_keys=True,indent=2)+'\n').encode('utf-8')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=destination.parent, suffix='.partial')
    try:
        with os.fdopen(fd,'wb') as handle, zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as bundle:
            for name, value in sorted(payload.items()):
                bundle.writestr(name,value)
        with zipfile.ZipFile(temp) as bundle:
            if bundle.testzip() is not None:
                raise ValueError('Review ZIP was not readable')
        os.replace(temp,destination)
    finally:
        Path(temp).unlink(missing_ok=True)
    return review


def screen_native_em_benchmark_cases(root: Path, config: dict, artifacts: list[dict], *,
                                    kind: str, solve_completed: bool,
                                    requested_frequencies_hz: list[float] | None = None,
                                    excited_port: int | None = None) -> dict:
    """Reusable B02/B03/B05/B06/B07/B11 *production-adapter* evidence screen.

    Invoked after the adapter's actual solver completion and SHA manifest
    construction. `solve_completed` is the adapter's verified worker state,
    not proof an offline caller independently ran a solver. Scientific case
    status stays BLOCKED until separate convergence and reviewer gates pass.
    """
    if kind not in ('eigenmode', 'sparameters', 'capacitance') or type(solve_completed) is not bool:
        raise NativeFieldEvidenceError('Invalid native benchmark execution context')
    out = {'schema': 'sqe.a11-native-em-benchmarks.v1', 'fabrication': 'HOLD',
           'mode_identity': 'UNRESOLVED', 'em_to_hamiltonian': 'BLOCKED',
           'execution_kind': 'NATIVE' if solve_completed else 'NOT_RUN', 'cases': {}}
    if not solve_completed:
        for cid in ('B02', 'B03', 'B05', 'B06', 'B07', 'B11'):
            out['cases'][cid] = {'stage_status': 'NOT_RUN', 'reason': 'No native solver invoked'}
        return out
    if kind == 'eigenmode':
        field_export = inspect_palace_field_export(root, config, artifacts)
        local = None
        if field_export['status'] == 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY':
            try:
                local = inspect_local_palace_field_values(root, config, artifacts)
            except NativeFieldEvidenceError:
                # The export metadata can be genuine while VTK is unavailable,
                # out of budget, or its values unreadable. Never upgrade it.
                pass
        signed_kappa = inspect_palace_signed_port_kappa(root, artifacts)
        out['cases']['B02'] = {
            'stage_status': ('NATIVE_FIELD_VALUES_SCREENED_SCIENCE_BLOCKED' if local else
                             'BLOCKED_NO_VALIDATED_COMPLEX_FIELD_SAMPLES'),
            'native_operation': 'SOLVER_COMPLETED_BY_PRODUCTION_ADAPTER',
            'field_export_status': field_export['status'],
            'solver_eig_sha256': field_export.get('native_eig_sha256'),
            'mesh_sha256': field_export.get('mesh_sha256'),
            'field_sample_metadata': local,
            'physical_convergence': 'NOT_ESTABLISHED',
            'signed_kappa': signed_kappa,
            'reason': 'One native solve cannot prove refined-mesh mode identity or Q/energy convergence'}
        out['cases']['B03'] = {
            'stage_status': 'BLOCKED_NEEDS_INDEPENDENT_REGISTERED_COMPLEX_E_AND_H_PAIR',
            'reason': 'A single eigenmode field export cannot establish H(curl), B-to-H constitutive mapping, cross-mesh interpolation or phase orientation'}
        out['cases']['B06'] = {
            'stage_status': 'BLOCKED_UNREVIEWED_JUNCTION_EPR_AND_HAMILTONIAN_TRANSFER'}
        out['cases']['B07'] = {
            'stage_status': 'BLOCKED_NO_REVIEWED_PEC_KINETIC_SURFACE_PAIR_AND_MODE_IDENTITY'}
    else:
        signed_kappa = inspect_palace_signed_port_kappa(root, artifacts)
        out['cases']['B02'] = {'stage_status': 'NOT_RUN', 'reason': 'Study is not an eigenmode solve'}
        out['cases']['B03'] = {'stage_status': 'NOT_RUN', 'reason': 'No eigenmode field pair'}
        out['cases']['B06'] = {'stage_status': 'NOT_RUN'}
        out['cases']['B07'] = {'stage_status': 'NOT_RUN'}
    if kind == 'sparameters':
        native = inspect_palace_driven_sparameters(
            root, config, artifacts,
            frequencies_hz=requested_frequencies_hz, excited_port=excited_port)
        out['cases']['B05'] = {
            'stage_status': ('NATIVE_COMPLEX_COLUMN_SCREENED_SCIENCE_BLOCKED'
                             if native['status'] == 'VERIFIED_NATIVE_COMPLEX_DRIVEN_COLUMN_DIAGNOSTIC_ONLY'
                             else native['status']),
            'native_operation': 'SOLVER_COMPLETED_BY_PRODUCTION_ADAPTER',
            'native_driven_evidence': native,
            'reason': 'Port normalization/de-embedding and physical resonance correspondence require separate review'}
    else:
        out['cases']['B05'] = {'stage_status': 'NOT_RUN', 'reason': 'Study is not a driven two-port sweep'}
    out['cases']['B11'] = {
        'stage_status': 'NOT_IMPLEMENTED_MAGNETOSTATIC_REVIEWED_NATIVE_ADAPTER',
        'reason': 'No vetted flux-line/DC-current geometry and Palace magnetostatic deck in A11 production interface; no pilot run claimed'}
    return out
