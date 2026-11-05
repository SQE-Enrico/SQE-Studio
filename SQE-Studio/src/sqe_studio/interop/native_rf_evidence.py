"""Read-only, revision-bound JosephsonCircuits native RF observations.

The Results HTTP handler MUST verify the enclosing RESULT_MANIFEST (all bytes,
revision, study and engine) before calling this reader. This routine adds
structural and port-reference checks; it does not run a solver, infer an EM
port mapping, or certify harmonic-balance convergence or physical gain.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re

from ..orchestration.artifacts import ArtifactInvalid, safe_file

SCHEMA = 'sqe.rf-native-results-screen.v1'
_MAX_SIDECAR_BYTES = 128_000
_MAX_TABLE_BYTES = 256_000
_TABLE = 'josephson_native_sparameters.tsv'
_SIDECAR = 'josephson_ports.json'
_REFERENCE_NAMES = frozenset({
    'josephson_request.tsv', 'josephson_fixed_worker.jl',
    'josephson_native_sparameters.tsv', 'josephson_native_metadata.tsv',
    'josephson_native_stdout.log', 'josephson_native_stderr.log',
})
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class NativeRFEvidenceError(ValueError):
    """Inconsistent or unsafe native RF evidence."""


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def _linear_s_matrix_diagnostics(points: list[dict], frequencies: list[float],
                                 port_order: list[int], analysis: str) -> dict:
    """Numeric summaries of verified complex S samples, without physical approval.

    For a pumped nonlinear calculation the signal-only (0->0) matrix does NOT
    contain the sideband/idler channels needed for a power accounting. Do not
    present such a matrix as a passivity or reciprocity check.
    """
    if analysis != 'rf_linear':
        return {'status': 'NOT_APPLICABLE_PUMPED_CHANNELS_NOT_EXPORTED',
                'rows': [], 'physical_validation': 'NOT_ESTABLISHED'}
    n = len(port_order)
    per_frequency = []
    index = 0
    for frequency in frequencies:
        matrix = []
        for output_port in port_order:
            row = []
            for input_port in port_order:
                point = points[index]
                # All ports, frequency and native order are independently
                # validated above. Consume precisely that verified grid.
                if (point['frequency_hz'] != frequency or
                        point['output_port'] != output_port or
                        point['input_port'] != input_port):
                    raise NativeRFEvidenceError('Native RF matrix ordering mismatch')
                row.append(complex(point['real'], point['imag']))
                index += 1
            matrix.append(row)
        powers = []
        for j in range(n):
            power_sum = math.fsum(abs(matrix[i][j])**2 for i in range(n))
            if not math.isfinite(power_sum):
                raise NativeRFEvidenceError('Unrepresentable numerical RF power sum')
            powers.append({'input_port': port_order[j], 'outgoing_power_sum': power_sum,
                           'above_unity_numeric': power_sum > 1.0 + 1e-10})
        deltas = [abs(matrix[i][j] - matrix[j][i])
                  for i in range(n) for j in range(i+1, n)]
        difference = max(deltas) if deltas else None
        if difference is not None and not math.isfinite(difference):
            raise NativeRFEvidenceError('Unrepresentable RF S-matrix asymmetry')
        per_frequency.append({'frequency_hz': frequency,
                              'outgoing_power_by_input': powers,
                              'max_pairwise_reciprocity_difference': difference})
    return {'status': 'NUMERIC_LINEAR_S_MATRIX_SCREEN_ONLY',
            'rows': per_frequency,
            'physical_validation': 'NOT_ESTABLISHED',
            'interpretation': 'No passivity/reciprocity certification; EM port correspondence unverified'}


def native_rf_evidence(folder: Path, manifest: dict) -> dict | None:
    """Screen verified JosephsonCircuits complex S samples, numerically only.

    No automatic S21 fit, power gain, idler, EM-coupling, or optimization claim.
    """
    if manifest.get('engine') != 'josephson_circuits' or manifest.get('artifact_type') != 'josephson.sparameters':
        return None
    try:
        entries = {record['name']: record for record in manifest['artifacts']}
        if not {_TABLE, _SIDECAR, *_REFERENCE_NAMES}.issubset(entries):
            raise NativeRFEvidenceError('Missing declared native Josephson RF provenance')
        sidepath = safe_file(folder, _SIDECAR)
        tablepath = safe_file(folder, _TABLE)
        if (not 0 < sidepath.stat().st_size <= _MAX_SIDECAR_BYTES or
                not 0 < tablepath.stat().st_size <= _MAX_TABLE_BYTES):
            raise NativeRFEvidenceError('Native RF result exceeds bounded display size')
        side = json.loads(sidepath.read_text(encoding='utf-8'))
        if not isinstance(side, dict) or side.get('schema') != 'sqe.josephson-port-contract.v1':
            raise NativeRFEvidenceError('Unsupported native Josephson port contract')
        if (side.get('analysis') not in ('rf_linear', 'rf_harmonic_balance') or
                side.get('native_process_exit_code') != 0 or
                side.get('scientific_status') != 'review_required' or
                side.get('frequency_unit') != 'Hz' or
                side.get('native_frequency_input_unit') != 'rad/s' or
                side.get('mode') != '(0,)->(0,) signal-only; nonlinear idler S not exported'):
            raise NativeRFEvidenceError('Unreviewed native RF analysis or frequency convention')
        obs = side.get('observable')
        if (not isinstance(obs, dict) or obs.get('quantity') != 'complex_scattering_amplitude' or
                obs.get('unit') != '1' or obs.get('representation') != 'real_and_imaginary' or
                obs.get('wave_convention') != 'native_power_wave' or
                obs.get('port_reference_plane') != 'explicit_schematic_node_to_ground_0'):
            raise NativeRFEvidenceError('Native RF observable lacks explicit wave/port convention')
        if (side.get('s_parameter_order') != 'frequency-major, output_port-major, input_port-minor' or
                side.get('s_parameter_unit') != 'dimensionless_complex_native_power_wave'):
            raise NativeRFEvidenceError('Unexpected native RF scattering matrix convention')
        hashes = side.get('artifact_sha256')
        if (not isinstance(hashes, dict) or set(hashes) != _REFERENCE_NAMES or
                any(not isinstance(sha, str) or not _SHA256.fullmatch(sha) or
                    entries[name].get('sha256') != sha for name, sha in hashes.items())):
            raise NativeRFEvidenceError('Native RF provenance hashes disagree with result manifest')
        # Validate against the actual files as defense in depth; callers have
        # already checked the entire run manifest against the saved revision.
        for name, sha in hashes.items():
            if hashlib.sha256(safe_file(folder, name).read_bytes()).hexdigest() != sha:
                raise NativeRFEvidenceError('Native RF reference evidence changed')
        ports = side.get('ports')
        order = side.get('port_order')
        if (not isinstance(ports, list) or not 1 <= len(ports) <= 4 or
                not isinstance(order, list) or order != list(range(1, len(ports) + 1)) or
                any(not isinstance(port, dict) or port.get('number') != i or
                    not _finite(port.get('reference_impedance_ohm')) or
                    not 0 < port['reference_impedance_ohm'] <= 10000 or
                    type(port.get('node')) is not str or
                    port.get('positive_terminal') != port['node'] or
                    port.get('negative_terminal') != '0'
                    for i, port in enumerate(ports, 1))):
            raise NativeRFEvidenceError('Ambiguous native RF port numbering or reference plane')
        freqs = side.get('frequency_points_hz')
        if (not isinstance(freqs, list) or not 1 <= len(freqs) <= 64 or
                any(not _finite(f) or f <= 0 for f in freqs) or
                len(set(freqs)) != len(freqs)):
            raise NativeRFEvidenceError('Ambiguous native RF frequency grid')
        with tablepath.open('r', encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle, delimiter='\t'))
        if (len(rows) != 1 + len(freqs)*len(ports)**2 or
                rows[0] != ['frequency_hz', 'output_port', 'input_port', 'real', 'imag']):
            raise NativeRFEvidenceError('Native RF table shape or header mismatch')
        points = []
        expected = ((f, po, pi) for f in freqs for po in order for pi in order)
        for row, (frequency, output_port, input_port) in zip(rows[1:], expected):
            if len(row) != 5 or any(len(cell) > 50 for cell in row):
                raise NativeRFEvidenceError('Malformed native RF sample')
            try:
                measured_f = float(row[0]); po = int(row[1]); pi = int(row[2])
                re_part = float(row[3]); im_part = float(row[4])
            except (ValueError, OverflowError) as exc:
                raise NativeRFEvidenceError('Non-numeric native RF observation') from exc
            if (not all(math.isfinite(v) for v in (measured_f, re_part, im_part)) or
                    not math.isclose(measured_f, frequency, rel_tol=1e-13, abs_tol=1e-6) or
                    row[1] != str(po) or row[2] != str(pi) or
                    po != output_port or pi != input_port):
                raise NativeRFEvidenceError('Native RF frequency or port grid does not match reviewed inputs')
            magnitude = math.hypot(re_part, im_part)
            if not math.isfinite(magnitude):
                raise NativeRFEvidenceError('Native RF magnitude is unrepresentable')
            points.append({'frequency_hz': frequency, 'output_port': po,
                           'input_port': pi, 'real': re_part, 'imag': im_part,
                           'magnitude': magnitude, 'phase_rad': math.atan2(im_part, re_part)})
        matrix_diagnostics = _linear_s_matrix_diagnostics(points, freqs, order, side['analysis'])
        # Only bounded read-only numerical observations, no RF->EM identity.
        return {'schema': SCHEMA, 'engine': 'josephson_circuits',
                'artifact_type': 'josephson.sparameters',
                'analysis': side['analysis'], 'native_engine_version': side.get('native_engine_version'),
                'ports': [{'number': p['number'], 'node': p['node'],
                           'reference_impedance_ohm': p['reference_impedance_ohm']} for p in ports],
                'frequency_points_hz': freqs, 'samples': points,
                'sample_count': len(points), 'display_limit': 64,
                'matrix_diagnostics': matrix_diagnostics,
                'signal_mode': '0_to_0_only',
                'normalization': 'native_power_wave_complex_amplitude',
                'numeric_status': 'NATIVE_RF_OBSERVATIONS_ONLY',
                'harmonic_balance_residual': ('NOT_EXPORTED' if side['analysis'] == 'rf_harmonic_balance' else 'NOT_APPLICABLE'),
                'reference_plane_review': 'SCHEMATIC_PORTS_ONLY_NO_EM_MAPPING',
                'cross_engine_mapping': 'BLOCKED_REQUIRES_REVIEWED_PORT_IDENTITY',
                'physical_validation': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error, ArtifactInvalid,
            KeyError, TypeError, OverflowError) as exc:
        raise NativeRFEvidenceError('Unreadable or unsafe native RF result') from exc
