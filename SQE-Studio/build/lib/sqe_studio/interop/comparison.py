"""Read-only expert comparison of verified native runs; never an engine solver.

No interpolation, model-fitting, inferred cross-engine correspondence, or approval.
The HTTP service verifies content hashes before calling these pure functions.
"""
from __future__ import annotations

import math


LIMIT = 64


def _brief(value):
    if value is None or type(value) in (int, float, bool):
        return value
    if type(value) is str:
        return value[:100] + ('...' if len(value) > 100 else '')
    return '<structured value>'


def _flatten(value, prefix, result, *, budget=256):
    if len(result) >= budget:
        return
    if type(value) is dict:
        for key in sorted(value):
            if key in ('notes', 'name'):
                continue
            _flatten(value[key], f'{prefix}.{key}', result, budget=budget)
    elif type(value) is list:
        for index, child in enumerate(value[:128]):
            _flatten(child, f'{prefix}[{index}]', result, budget=budget)
    else:
        result[prefix] = value


def changes_between(left_model, right_model, left_study, right_study):
    """Only differences in saved engineering *inputs*, never inferred outputs."""
    def selected(model, study_id):
        studies = [s for s in model['studies'] if s['id'] == study_id]
        return {'schematic': model['schematic'], 'layout': model['layout'],
                'process': model['process'],
                'selected_study': studies[0] if studies else {}}
    a, b = {}, {}
    _flatten(selected(left_model, left_study), 'model', a)
    _flatten(selected(right_model, right_study), 'model', b)
    keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return {'shown': [{'field': key, 'left': _brief(a.get(key)), 'right': _brief(b.get(key))}
                      for key in keys[:LIMIT]],
            'total': len(keys), 'truncated': len(keys) > LIMIT,
            'meaning': 'saved_design_inputs_only_not_measured_or_verified_physics'}


def compare_spectra(left, right):
    """Compare actual native transition frequencies for identical model semantics.

    Only unswept scqubits energy data in GHz are supported. Energy zero is
    arbitrary, so compare E_n-E_0, not absolute eigenvalue differences.
    """
    blocked = lambda reason: {'status': 'not_comparable', 'reason': reason, 'rows': []}
    if left is None or right is None:
        return blocked('Both runs must include a verified native scqubits spectrum')
    if any(not isinstance(s, dict) or s.get('schema') != 'sqe.scqubits.spectrum.v1'
           or s.get('source') != 'native scqubits eigenvals' or
           s.get('artifact_type') != 'scqubits.spectrum' for s in (left, right)):
        return blocked('Unrecognized native scqubits spectrum or provenance')
    if left.get('model') != right.get('model'):
        return blocked('Distinct Hamiltonian model families; reviewed mapping required')
    if left.get('units') != 'GHz' or right.get('units') != 'GHz' or left.get('energy_unit') != 'GHz' or right.get('energy_unit') != 'GHz':
        return blocked('Explicit matching GHz energy/frequency units required')
    if left.get('axis') is not None or right.get('axis') is not None or left.get('preview_point_index') != 0 or right.get('preview_point_index') != 0:
        return blocked('Native parameter sweeps require explicit axis alignment; no interpolation')
    a, b = left.get('levels'), right.get('levels')
    if (type(a) is not list or type(b) is not list or len(a) != len(b)
            or not 2 <= len(a) <= 12 or any(type(v) not in (int, float)
             or not math.isfinite(v) for v in a + b)):
        return blocked('Matching finite native eigenvalue lists of 2-12 levels required')
    rows = []
    for i in range(1, len(a)):
        f_left, f_right = float(a[i] - a[0]), float(b[i] - b[0])
        rows.append({'transition': f'0->{i}', 'left_GHz': f_left,
                     'right_GHz': f_right, 'delta_GHz': f_right - f_left})
    conv = [s.get('convergence', {}).get('status') for s in (left, right)]
    return {'status': 'numerical_differences_for_expert_review',
            'method': 'native scqubits E_n - E_0 differences; no interpolation or fitting',
            'model': left['model'], 'unit': 'GHz', 'rows': rows,
            'convergence_statuses': conv,
            'convergence_verified': all(x == 'checked_passed' for x in conv),
            'scientific_qualification': 'not_established'}


def report(left_manifest, right_manifest, left_run, right_run,
           left_project, right_project, left_spectrum=None, right_spectrum=None):
    """Inputs must already be authenticated, revision- and content-verified."""
    def item(m, r, project):
        return {'run_id': r['id'], 'study_id': r['study_id'],
                'revision_id': r['revision_id'], 'project_sha256': project['revision_digest'],
                'engine': m['engine'], 'native_version': m['engine_version'],
                'artifact_type': m['artifact_type'], 'scientific_status': m['scientific_status'],
                'fabrication_status': m['fabrication_status'],
                'artifacts': [{'name': a['name'], 'sha256': a['sha256']} for a in m['artifacts']]}
    same_type = left_manifest['artifact_type'] == right_manifest['artifact_type']
    numerical = compare_spectra(left_spectrum, right_spectrum) if same_type and left_manifest['artifact_type'] == 'scqubits.spectrum' else {'status': 'not_comparable', 'reason': 'Different output types or no reviewed numerical comparison protocol', 'rows': []}
    return {'schema': 'sqe.expert-comparison.v1',
            'status': 'read_only_expert_review_not_scientifically_qualified',
            'left': item(left_manifest, left_run, left_project),
            'right': item(right_manifest, right_run, right_project),
            'same_revision': left_run['revision_id'] == right_run['revision_id'],
            'same_output_type': same_type,
            'design_input_changes': changes_between(left_project['model'], right_project['model'], left_run['study_id'], right_run['study_id']),
            'numerical_comparison': numerical,
            'caveats': ['Results are native artifacts, not independent solver validation',
                        'No automatic EM-to-quantum or nonlinear port equivalence is inferred',
                        'Unreviewed kinetic inductance, EPR/BBQ, DRC/LVS and foundry approval remain unavailable',
                        'Fabrication remains HOLD; the expert must approve interpretation and optimization']}
