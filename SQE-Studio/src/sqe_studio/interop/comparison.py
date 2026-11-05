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
           left_project, right_project, left_spectrum=None, right_spectrum=None,
           left_palace=None, right_palace=None, left_em=None, right_em=None,
           left_capacitance=None, right_capacitance=None):
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
    if same_type and left_manifest['artifact_type']=='palace.eigenmodes':
        numerical=compare_palace_modes(left_palace,right_palace,left_project['model'],right_project['model'],
                                       left_run['study_id'],right_run['study_id'])
    if same_type and left_manifest['artifact_type']=='palace.capacitance_matrix':
        numerical=compare_native_capacitance(left_capacitance, right_capacitance,
                                            left_project['model'], right_project['model'],
                                            left_run['study_id'], right_run['study_id'])
    from .native_em_evidence import compare_native_em_evidence
    em_observables=compare_native_em_evidence(left_em,right_em,numerical)
    return {'schema': 'sqe.expert-comparison.v1',
            'status': 'read_only_expert_review_not_scientifically_qualified',
            'left': item(left_manifest, left_run, left_project),
            'right': item(right_manifest, right_run, right_project),
            'same_revision': left_run['revision_id'] == right_run['revision_id'],
            'same_output_type': same_type,
            'design_input_changes': changes_between(left_project['model'], right_project['model'], left_run['study_id'], right_run['study_id']),
            'numerical_comparison': numerical,
            'em_observables':em_observables,
            'caveats': ['Results are native artifacts, not independent solver validation',
                        'No automatic EM-to-quantum or nonlinear port equivalence is inferred',
                        'Unreviewed kinetic inductance, EPR/BBQ, DRC/LVS and foundry approval remain unavailable',
                        'Fabrication remains HOLD; the expert must approve interpretation and optimization']}


def compare_palace_modes(left: dict | None, right: dict | None,
                         left_model: dict, right_model: dict,
                         left_study_id: str, right_study_id: str) -> dict:
    """Read-only native mode-index deltas for otherwise identical EM design inputs.

    Declaring mode identity, mesh convergence, or design validity from mode
    indices is forbidden. Both native CSVs must have been hash-verified upstream.
    """
    blocked = lambda reason: {'status':'not_comparable','reason':reason,'rows':[],
                              'convergence_verified':False}
    if left is None or right is None or left.get('source')!='palace.native_eig.csv' or right.get('source')!='palace.native_eig.csv':
        return blocked('Two verified native Palace eigenmode tables required')
    if left.get('units')!='GHz' or right.get('units')!='GHz':
        return blocked('Explicit matching GHz units required')
    if any(left_model.get(k)!=right_model.get(k) for k in ('layout','process','schematic')):
        return blocked('Geometry, materials or schematic changed; no mesh-only comparison')
    def selected(model, name):
        studies=[s for s in model.get('studies',[]) if s.get('id')==name and
                 s.get('engine')=='sqdmetal_palace' and s.get('kind')=='eigenmode']
        if len(studies)!=1:return None
        # Inspect the same immutable physical settings except the mesh specification.
        import copy
        x=copy.deepcopy(studies[0])
        x.pop('id',None)
        x['inputs']['em'].pop('mesh',None)
        return x
    a,b=selected(left_model,left_study_id),selected(right_model,right_study_id)
    if a is None or b is None or a!=b:
        return blocked('Native studies differ beyond mesh or lack reviewed physical mappings')
    lm,rm=left.get('modes'),right.get('modes')
    if not isinstance(lm,list) or not isinstance(rm,list) or len(lm)!=len(rm) or not 1<=len(lm)<=12:
        return blocked('Matching native eigenmode table size required')
    rows=[]
    for i,(l,r) in enumerate(zip(lm,rm),1):
        if l.get('mode_index')!=i or r.get('mode_index')!=i:
            return blocked('Native mode labels not sequential')
        f,g=l.get('frequency_GHz'),r.get('frequency_GHz')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (f,g)):
            return blocked('Nonfinite native frequency')
        rows.append({'transition':f'Native mode index {i} (identity UNVERIFIED)',
                     'left_GHz':f,'right_GHz':g,'delta_GHz':g-f,
                     'relative_difference':abs(g-f)/max(f,g)})
    return {'status':'native_mode_index_differences_for_expert_review',
            'method':'verified Palace eigenfrequency differences on compatible nonmesh physical inputs; NOT mode matching',
            'unit':'GHz','rows':rows,'convergence_verified':False,
            'mode_identity':'unverified_no_field_overlap',
            'scientific_qualification':'not_established'}


def compare_native_capacitance(left: dict | None, right: dict | None,
                               left_model: dict, right_model: dict,
                               left_study_id: str, right_study_id: str) -> dict:
    """Numerical Maxwell-matrix drift for two individually verified native runs.

    This is *not* electrostatic mesh convergence, physical terminal registration,
    independent solver validation or an EM-to-Hamiltonian transfer. Callers
    verify both complete artifact manifests before obtaining native screens.
    """
    blocked = lambda reason: {'status': 'not_comparable', 'reason': reason, 'rows': [],
                              'convergence_verified': False, 'mesh_convergence': 'NOT_ESTABLISHED'}
    if (type(left) is not dict or type(right) is not dict or
            any(s.get('schema') != 'sqe.native-capacitance-screen.v1' or
                s.get('status') != 'NATIVE_MAXWELL_MATRIX_SCREENED' or
                s.get('scientific_qualification') != 'NOT_ESTABLISHED' or
                s.get('fabrication') != 'HOLD' or
                s.get('scqubits_EC_transfer') != 'BLOCKED_REQUIRES_REVIEWED_CAPACITANCE_REDUCTION'
                for s in (left, right))):
        return blocked('Two separately verified native Palace Maxwell screens required')
    if any(left_model.get(k) != right_model.get(k) for k in ('layout', 'process', 'schematic')):
        return blocked('Geometry, materials or schematic differ; only matching physical design inputs can be compared')

    def study_without_mesh(model, study_id):
        studies = [s for s in model.get('studies', []) if s.get('id') == study_id
                   and s.get('engine') == 'sqdmetal_palace' and s.get('kind') == 'capacitance']
        if len(studies) != 1:
            return None
        import copy
        selected = copy.deepcopy(studies[0])
        selected.pop('id', None)
        em = selected.get('inputs', {}).get('em')
        if type(em) is not dict:
            return None
        em.pop('mesh', None)
        return selected

    first, second = (study_without_mesh(left_model, left_study_id),
                     study_without_mesh(right_model, right_study_id))
    if first is None or second is None or first != second:
        return blocked('Electrostatic studies differ beyond mesh, or reviewed settings are unavailable')
    names = left.get('conductor_order')
    if (type(names) is not list or not 2 <= len(names) <= 16 or
            any(type(n) is not str or not n for n in names) or len(set(names)) != len(names) or
            right.get('conductor_order') != names or
            left.get('terminal_surface_tags') != right.get('terminal_surface_tags') or
            type(left.get('reference_ground_surface_tags')) is not list or
            not left['reference_ground_surface_tags'] or
            left['reference_ground_surface_tags'] != right.get('reference_ground_surface_tags')):
        return blocked('Terminal labels/order, native surface groups, or reference-ground groups differ')
    if (left.get('conditional_assumption') != 'ALL_OTHER_MODELED_TERMINALS_AT_ZERO_VOLTAGE_CII_ONLY' or
            right.get('conditional_assumption') != left['conditional_assumption']):
        return blocked('Capacitance boundary-condition interpretation differs')
    matrices = [s.get('capacitance_matrix_F') for s in (left, right)]
    if any(type(m) is not list or len(m) != len(names) or
           any(type(row) is not list or len(row) != len(names) or
               any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e-6 for v in row)
               for row in m) for m in matrices):
        return blocked('Invalid finite SI-unit Maxwell matrix shape or entries')
    rows = []
    for i in range(len(names)):
        for j in range(i, len(names)):
            a, b = matrices[0][i][j], matrices[1][i][j]
            diff = b - a
            denom = max(abs(a), abs(b))
            rows.append({'terminal_a': names[i], 'terminal_b': names[j],
                         'kind': 'self' if i == j else 'mutual',
                         'left_fF': a * 1e15, 'right_fF': b * 1e15,
                         'delta_fF': diff * 1e15,
                         'relative_difference': abs(diff)/denom if denom > 1e-18 else None})
    return {'status': 'native_maxwell_matrix_differences_for_expert_review',
            'method': 'hash-verified native Maxwell terminal coefficients; upper triangle in fF; no interpolation',
            'unit': 'fF', 'conductor_order': list(names), 'rows': rows,
            'max_abs_delta_fF': max(abs(r['delta_fF']) for r in rows),
            'same_native_matrix_sha256': left.get('native_matrix_sha256') == right.get('native_matrix_sha256'),
            'convergence_verified': False, 'mesh_convergence': 'NOT_ESTABLISHED',
            'terminal_physical_identity': 'NOT_ESTABLISHED_BY_TAG_ORDER_ALONE',
            'physical_review': 'REQUIRED', 'em_to_scqubits_transfer': 'BLOCKED',
            'scientific_qualification': 'not_established', 'fabrication': 'HOLD'}
