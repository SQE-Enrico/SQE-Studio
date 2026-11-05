"""Revision-bound numerical design-target screen for verified native Results.

This is a *design feedback* service, not quantum parameter extraction or an
optimizer. Call only AFTER verify_manifest and obtain target specifications from
that exact saved project revision. Never infer modes, couplings or conversions.
"""
from __future__ import annotations

import math
import re

SCHEMA = 'sqe.native-design-target-screen.v1'
_MAX_TARGETS = 128
_EM_FREQUENCY = re.compile(r'^em_mode_([1-9][0-9]?)$')
_EM_Q = re.compile(r'^em_Q_mode_([1-9][0-9]?)$')
# Explicit port order (output,input) and EXACT sampled frequency in GHz.
_RF_SAMPLE = re.compile(r'^rf_S([1-4])([1-4])_(mag|dB)_at_([1-9][0-9]*(?:\.[0-9]{1,6})?)GHz$')


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _observations(manifest: dict, spectrum: dict | None, em_evidence: dict | None):
    engine = manifest.get('engine')
    observations = {}
    if engine == 'scqubits' and isinstance(spectrum, dict):
        if (spectrum.get('schema') == 'sqe.scqubits.spectrum.v1' and
                spectrum.get('artifact_type') == 'scqubits.spectrum' and
                spectrum.get('engine') == 'scqubits' and
                spectrum.get('source') == 'native scqubits eigenvals' and
                spectrum.get('units') == 'GHz'):
            values = spectrum.get('levels')
            if (isinstance(values, list) and 2 <= len(values) <= 12 and
                    all(_finite_number(v) for v in values) and
                    all(b > a for a,b in zip(values,values[1:]))):
                gap = values[1] - values[0]
                if math.isfinite(gap) and gap > 0:
                    origin=('CONDITIONAL_EM_DERIVED_JUNCTION_MODEL' if
                            spectrum.get('parameter_origin')=='EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS'
                            else 'INDEPENDENT_QUANTUM_MODEL_PARAMETERS')
                    observations['f01'] = ('GHz', gap, origin)
    if engine == 'sqdmetal_palace' and isinstance(em_evidence, dict):
        if em_evidence.get('schema') != 'sqe.em-native-results-screen.v1':
            return observations
        modes = em_evidence.get('modes')
        if not isinstance(modes, list) or len(modes) > 32:
            return observations
        for row in modes:
            if not isinstance(row, dict):
                continue
            i = row.get('native_mode_index')
            f, q = row.get('frequency_GHz'), row.get('q_total')
            if type(i) is not int or not 1 <= i <= 32:
                continue
            if _finite_number(f) and f > 0:
                observations[f'em_mode_{i}'] = ('GHz', f, 'NATIVE_INDEX_NOT_MODE_IDENTITY')
            if _finite_number(q) and q > 0:
                observations[f'em_Q_mode_{i}'] = ('1', q, 'Q_NOT_INDEPENDENTLY_VALIDATED')
    return observations



def _rf_sample_for_target(name: str, manifest: dict, rf_evidence: dict | None):
    """Exact-grid numerical RF screen; no interpolation or port/field matching.

    The authenticated Results route verifies all output hashes before it calls
    this helper, then native_rf_evidence validates S conventions and port order.
    This function deliberately refuses to infer a response at uncomputed points.
    """
    match = _RF_SAMPLE.fullmatch(name)
    if match is None:
        return None, None
    if manifest.get('engine') != 'josephson_circuits' or not isinstance(rf_evidence, dict):
        return 'NO_NATIVE_OBSERVATION_FOR_THIS_RUN', None
    if (manifest.get('artifact_type') != 'josephson.sparameters' or
            rf_evidence.get('schema') != 'sqe.rf-native-results-screen.v1' or
            rf_evidence.get('engine') != 'josephson_circuits' or
            rf_evidence.get('artifact_type') != 'josephson.sparameters' or
            rf_evidence.get('physical_validation') != 'NOT_ESTABLISHED' or
            rf_evidence.get('cross_engine_mapping') != 'BLOCKED_REQUIRES_REVIEWED_PORT_IDENTITY' or
            rf_evidence.get('analysis') not in ('rf_linear', 'rf_harmonic_balance')):
        return 'NO_VERIFIED_RF_EVIDENCE', None
    out_port, in_port, representation, freq_ghz = match.groups()
    if len(freq_ghz) > 22:
        return 'INVALID_TARGET_FREQUENCY', None
    requested_hz = float(freq_ghz) * 1e9
    if not math.isfinite(requested_hz) or requested_hz <= 0:
        return 'INVALID_TARGET_FREQUENCY', None
    samples = rf_evidence.get('samples')
    freqs = rf_evidence.get('frequency_points_hz')
    ports = rf_evidence.get('ports')
    if (not isinstance(samples, list) or len(samples) > 1024 or
            not isinstance(freqs, list) or not 1 <= len(freqs) <= 64 or
            not isinstance(ports, list) or not 1 <= len(ports) <= 4 or
            rf_evidence.get('sample_count') != len(samples)):
        return 'NO_VERIFIED_RF_EVIDENCE', None
    # A selected frequency must be exactly one native grid point at solver
    # floating-point precision; otherwise do not pick a nearest neighbour.
    matching = [f for f in freqs if _finite_number(f) and
                math.isclose(f, requested_hz, rel_tol=1e-12, abs_tol=0.01)]
    if len(matching) != 1:
        return ('NO_EXACT_NATIVE_FREQUENCY_POINT' if not matching else
                'AMBIGUOUS_NATIVE_FREQUENCY_POINT'), None
    if not any(isinstance(p, dict) and p.get('number') == int(out_port)
               for p in ports) or not any(
               isinstance(p, dict) and p.get('number') == int(in_port)
               for p in ports):
        return 'NO_NATIVE_PORT_FOR_TARGET', None
    candidates = [r for r in samples if isinstance(r, dict) and
                  r.get('frequency_hz') == matching[0] and
                  r.get('output_port') == int(out_port) and
                  r.get('input_port') == int(in_port)]
    if len(candidates) != 1:
        return 'NO_UNAMBIGUOUS_NATIVE_RF_SAMPLE', None
    sample = candidates[0]
    magnitude = sample.get('magnitude')
    if not _finite_number(magnitude) or magnitude < 0:
        return 'NO_VERIFIED_RF_EVIDENCE', None
    if representation == 'dB':
        if magnitude == 0:
            return 'UNDEFINED_LOG_MAGNITUDE', None
        observed = 20 * math.log10(magnitude)
        unit = 'dB'
    else:
        observed = magnitude
        unit = '1'
    if not math.isfinite(observed):
        return 'NUMERICAL_RANGE_ERROR', None
    return None, (unit, observed, 'NATIVE_SIGNAL_S_AMPLITUDE_ONLY_NO_EM_OR_GAIN_VALIDATION')

def evaluate_design_targets(*, project: dict, manifest: dict,
                            spectrum: dict | None = None,
                            em_evidence: dict | None = None,
                            rf_evidence: dict | None = None) -> dict:
    """Numeric-only comparison, scoped to the SAVED revision of this run.

    Inputs must be rehashed by the calling Results route; this function never
    reads a file or trusts an unverified client-supplied target. No pass here
    can release EM->Hamiltonian, mode identity, optimization or fabrication.
    """
    if (manifest.get('schema') != 'sqe.artifact.v1' or
            manifest.get('revision_id') != project.get('revision',project.get('head')) or
            manifest.get('project_digest') != project.get('revision_digest')):
        raise ValueError('Native target screen requires the run\'s saved revision and verified manifest')
    targets = project.get('model',{}).get('intent',{}).get('targets',[])
    if not isinstance(targets, list):
        raise ValueError('Invalid saved design target list')
    observations = _observations(manifest, spectrum, em_evidence)
    counts = {}
    for t in targets:
        if isinstance(t, dict) and type(t.get('name')) is str:
            counts[t['name']] = counts.get(t['name'], 0) + 1
    rows = []
    for t in targets[:_MAX_TARGETS]:
        if not isinstance(t,dict):
            continue
        name,unit = t.get('name'),t.get('unit')
        value,tolerance = t.get('value'),t.get('tolerance')
        if not isinstance(name,str) or not isinstance(unit,str):
            continue
        item = {'name':name,'unit':unit,'target':value if _finite_number(value) else None,
                'tolerance':tolerance if _finite_number(tolerance) and tolerance>=0 else None,
                'observed':None,'signed_delta':None,'absolute_delta':None,
                'numeric_status':'NOT_EVALUATED','physical_status':'NOT_QUALIFIED',
                'scientific_note':'No validated physical equivalence inferred'}
        known_name = (name == 'f01' or _EM_FREQUENCY.fullmatch(name) or
                      _EM_Q.fullmatch(name) or _RF_SAMPLE.fullmatch(name))
        if counts[name] != 1:
            item['numeric_status'] = 'AMBIGUOUS_TARGET_NAME'
        elif not _finite_number(value):
            item['numeric_status'] = 'INVALID_SAVED_TARGET'
        else:
            rf_failure, rf_sample = _rf_sample_for_target(name, manifest, rf_evidence)
            if rf_failure is not None:
                item['numeric_status'] = rf_failure
            elif rf_sample is not None:
                observations[name] = rf_sample
        if item['numeric_status'] == 'NOT_EVALUATED' and name in observations:
            observed_unit, observed, note = observations[name]
            if unit != observed_unit:
                item['numeric_status'] = 'UNIT_MISMATCH'
            else:
                delta = observed - value
                if math.isfinite(delta):
                    item.update(observed=observed, signed_delta=delta,
                                absolute_delta=abs(delta),scientific_note=note)
                    item['numeric_status'] = ('NO_TOLERANCE_DEFINED' if item['tolerance'] is None else
                        'WITHIN_NUMERIC_TOLERANCE' if abs(delta) <= item['tolerance'] else
                        'OUTSIDE_NUMERIC_TOLERANCE')
                else:
                    item['numeric_status'] = 'NUMERICAL_RANGE_ERROR'
        elif item['numeric_status'] == 'NOT_EVALUATED':
            item['numeric_status'] = ('NO_NATIVE_OBSERVATION_FOR_THIS_RUN' if known_name
                                      else 'UNMAPPED_DESIGN_TARGET')
        rows.append(item)
    return {'schema':SCHEMA, 'source':'saved_revision_plus_sha256_verified_native_run',
            'revision_id':manifest['revision_id'], 'project_digest':manifest['project_digest'],
            'engine':manifest.get('engine'),'rows':rows,
            'truncated':len(targets)>_MAX_TARGETS,'total_saved_targets':len(targets),
            'scientific_status':'NUMERIC_DESIGN_FEEDBACK_ONLY',
            'cross_engine_parameter_transfer':'BLOCKED_REQUIRES_VALIDATED_MAPPING',
            'mode_identity':'UNRESOLVED','automatic_optimization':'BLOCKED',
            'fabrication':'HOLD'}
