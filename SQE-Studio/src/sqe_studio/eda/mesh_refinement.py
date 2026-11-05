"""M10: three-run *numerical* Palace eigenfrequency mesh-refinement screening.

The caller MUST authenticate all three saved runs and SHA-verify each native
artifact against its immutable project revision.  A frequency index is NOT a
physical eigenmode identity; decreasing deltas never grant scientific approval.
No asymptotic order/GCI can be inferred from nominal max mesh size alone.
"""
from __future__ import annotations

from copy import deepcopy
import math

SCHEMA = 'sqe.native-mesh-three-run.m10.v1'


def _blocked(reason):
    return {'schema': SCHEMA, 'case_id': 'R03_PALACE_MESH_REFINEMENT',
            'status': 'BLOCKED', 'reason': reason, 'rows': [],
            'mode_identity': 'NOT_ESTABLISHED_NO_COMPLEX_FIELD_OVERLAP',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'physical_validation': 'NOT_ESTABLISHED',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD'}


def _study(model, study_id):
    matches = [s for s in model.get('studies', ()) if type(s) is dict and
               s.get('id') == study_id and s.get('kind') == 'eigenmode' and
               s.get('engine') == 'sqdmetal_palace']
    if len(matches) != 1:
        return None, None
    study = deepcopy(matches[0])
    study.pop('id', None)
    em = study.get('inputs', {}).get('em')
    if type(em) is not dict or type(em.get('mesh')) is not dict:
        return None, None
    mesh = em.pop('mesh')
    if set(mesh) != {'max_um', 'min_um', 'refinement_levels', 'relative_tolerance'}:
        return None, None
    # Only discretization lengths may vary.  Solver, ports, boundary conditions,
    # material declaration, order and every other mesh policy MUST be unchanged.
    settings = {k: v for k, v in mesh.items() if k not in ('max_um', 'min_um')}
    return (study, settings), mesh


def compare_verified_three_meshes(*, models, study_ids, native, manifests) -> dict:
    """Compare coarse/medium/fine in that explicit order; all are verified first.

    No synthetic mesh or solver input, no interpolation/field matching, no
    extrapolated eigenvalue.  Trend result is ONLY an index-level diagnostic.
    """
    if not all(type(x) in (tuple, list) and len(x) == 3
               for x in (models, study_ids, native, manifests)):
        return _blocked('Exactly three saved independently verified native runs are required')
    if any(type(m) is not dict for m in models):
        return _blocked('Missing saved model input')
    if any(m.get('layout') != models[0].get('layout') or
           m.get('process') != models[0].get('process') or
           m.get('schematic') != models[0].get('schematic') or
           m.get('family') != models[0].get('family') for m in models[1:]):
        return _blocked('Geometry, materials, family and schematic must be identical')
    studies = [_study(model, study_id) for model, study_id in zip(models, study_ids)]
    if any(s is None or mesh is None for s, mesh in studies):
        return _blocked('Matching saved Palace eigenmode studies with explicit mesh required')
    if any(s != studies[0][0] for s, _ in studies[1:]):
        return _blocked('Mesh policy, solver, ports or other physical inputs differ')
    values = []
    for _settings, mesh in studies:
        a, b = mesh['max_um'], mesh['min_um']
        if (type(a) not in (int, float) or type(b) not in (int, float) or
                not math.isfinite(a) or not math.isfinite(b) or
                not 0 < b <= a < 100000):
            return _blocked('Finite positive mesh max/min in micrometers required')
        values.append((float(a), float(b)))
    if not (values[0][0] > values[1][0] > values[2][0]):
        return _blocked('Choose three distinct coarse-to-fine maximum element sizes')
    if not (values[0][1] >= values[1][1] >= values[2][1]):
        return _blocked('Minimum element size cannot increase on mesh refinement')
    if any(type(m) is not dict or m.get('artifact_type') != 'palace.eigenmodes'
           or m.get('engine') != 'sqdmetal_palace' for m in manifests):
        return _blocked('Three authentic Palace eigenmode manifests required')
    frequencies = []
    for item in native:
        if (type(item) is not dict or item.get('source') != 'palace.native_eig.csv'
                or item.get('units') != 'GHz' or item.get('mode_matching') != 'not_established'):
            return _blocked('Three verified Palace native frequency tables in GHz required')
        modes = item.get('modes')
        if (type(modes) is not list or not 1 <= len(modes) <= 12 or
            any(type(row) is not dict or row.get('mode_index') != i or
                type(row.get('frequency_GHz')) not in (int, float) or
                not math.isfinite(row['frequency_GHz']) or row['frequency_GHz'] <= 0
                for i, row in enumerate(modes, 1))):
            return _blocked('Valid indexed, finite and positive eigenfrequencies required')
        frequencies.append([float(row['frequency_GHz']) for row in modes])
    if len(set(map(len, frequencies))) != 1:
        return _blocked('Native mode table sizes differ; no mode pairing inferred')
    # A strict science gate must not compare different solver versions as though
    # a mesh-only change caused all observed variations.
    if any(m.get('engine_version') != manifests[0].get('engine_version')
           for m in manifests[1:]):
        return _blocked('Native engine versions differ across refinements')
    rows = []
    for index in range(len(frequencies[0])):
        a, b, c = (s[index] for s in frequencies)
        coarse_step = abs(b - a)
        fine_step = abs(c - b)
        # This is a measured drift ratio, not Richardson order or GCI.
        ratio = fine_step / coarse_step if coarse_step > 1e-12 else None
        trend = ('DECREASING_INDEX_DRIFT' if ratio is not None and ratio < 1
                 else 'INCONCLUSIVE_OR_INCREASING_INDEX_DRIFT')
        rows.append({'native_mode_index_unverified': index + 1,
                     'coarse_GHz': a, 'medium_GHz': b, 'fine_GHz': c,
                     'coarse_to_medium_abs_GHz': coarse_step,
                     'medium_to_fine_abs_GHz': fine_step,
                     'last_relative_drift': fine_step / max(abs(b), abs(c)),
                     'step_drift_ratio': ratio,
                     'trend': trend})
    return {
        'schema': SCHEMA, 'case_id': 'R03_PALACE_MESH_REFINEMENT',
        'status': 'NUMERICAL_INDEX_TREND_ONLY',
        'reason': ('Three SHA-verified native solutions and unchanged nonmesh inputs. '
                   'Indexed eigenfrequencies can swap physical modes across meshes.'),
        'mesh_sizes_um': [{'max_um': x, 'min_um': y} for x, y in values],
        'rows': rows,
        'method': 'three independent mesh settings; adjacent native-index frequency drift, without extrapolation',
        'same_nonmesh_inputs': True, 'mode_identity': 'NOT_ESTABLISHED_NO_COMPLEX_FIELD_OVERLAP',
        'mesh_convergence': 'NOT_ESTABLISHED',
        'physics_gate': 'BLOCKED_REQUIRES_COMPLEX_FIELD_OVERLAP_AND_SOLVER_MESH_REVIEW',
        'physical_validation': 'NOT_ESTABLISHED',
        'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD',
    }
