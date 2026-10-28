"""Versioned mesh-convergence workflow for authentic Palace calculations.

A numerical-convergence indication is NOT proof of correct ports, geometry,
mode identity, material physics or fabrication qualification. No solver fallback.
"""
from __future__ import annotations

from copy import deepcopy
import csv
import math
from pathlib import Path

import numpy as np

from . import em
from .io import read_json, sha256, write_json

KINDS = {'eigenmode': ('eig.csv', 'Re{f} (GHz)'),
         'electrostatic': ('terminal-C.csv', None)}
DEFAULT_LEVELS = (0, 1, 2)


def prepare(out, kind, levels=DEFAULT_LEVELS):
    """Create distinct, immutable-to-the-solver Palace configs with h-refinement.

    Must be called after the real device mesh exists and the geometry contract
    was exported. A successful preparation does not mean any FEM was executed.
    """
    out = Path(out)
    if kind not in KINDS:
        raise ValueError('Convergence supports eigenmode or electrostatic')
    if not isinstance(levels, (tuple, list)) or len(levels) not in (2, 3) or \
        any(type(n) is not int or not 0 <= n <= 3 for n in levels) or \
        list(levels) != sorted(set(levels)):
        raise ValueError('Use 2 or 3 increasing unique refinement levels between 0 and 3')
    if not (out / 'device.msh').is_file():
        raise ValueError('A real device.msh is required for refinement')
    manifest = read_json(out / 'mesh.json')
    contract = read_json(out / 'contract.json')
    if sha256(out / 'device.msh') != manifest['mesh_sha256'] or \
       manifest['geometry_sha256'] != contract['geometry_sha256']:
        raise ValueError('Mesh or physical design integrity mismatch')
    base = read_json(out / (kind + '.json'))
    if base['Problem']['Type'] != ('Eigenmode' if kind == 'eigenmode' else 'Electrostatic'):
        raise ValueError('Base Palace simulation has wrong problem type')
    names = []
    for level in levels:
        name = f'convergence-{kind}-L{level}'
        if (out / f'{name}.json').exists() or (out / name).exists():
            raise ValueError(f'Convergence output/configuration already exists: {name}')
        cfg = deepcopy(base)
        cfg['Problem']['Output'] = name
        cfg['Model'].setdefault('Refinement', {})['UniformLevels'] = level
        write_json(out / f'{name}.json', cfg)
        names.append(name)
    contract['palace_configs'].extend(names)
    write_json(out / 'contract.json', contract)
    return names


def eigen_frequencies(path):
    """Only accepts Palace's documented mode ID and real frequency columns."""
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream, skipinitialspace=True)
        fields = [name.strip() for name in (reader.fieldnames or [])]
        mode_col = next((f for f in fields if f in ('m', 'i', 'Mode', 'Index')), None)
        freq_col = next((f for f in fields if f == 'Re{f} (GHz)'), None)
        if len(fields) != len(set(fields)) or not mode_col or not freq_col:
            raise ValueError('Unsupported eig.csv header; explicit Palace GHz frequency is required')
        modes = {}
        for row in reader:
            cleaned = {k.strip(): v for k, v in row.items()}
            index = float(cleaned[mode_col]); freq = float(cleaned[freq_col])
            if not math.isfinite(index) or not index.is_integer() or index < 1 or \
               not math.isfinite(freq) or freq <= 0 or int(index) in modes:
                raise ValueError('Invalid/duplicate Palace eigenmode index or frequency')
            modes[int(index)] = freq
    if not modes or list(sorted(modes)) != list(range(1, len(modes) + 1)):
        raise ValueError('Eigenmode row indices must be consecutive from 1')
    return np.asarray([modes[i] for i in sorted(modes)], dtype=float)


def summarize(out, kind, names, *, tolerance=0.005):
    """Run-independent comparison that REQUIRES verified real Palace solve records.

    Modes are compared by Palace index, *not* matched by field overlap. At
    avoided crossings this comparison is unsafe: index-only mode tracking is
    never a scientific qualification gate.
    """
    from .physical_qpu import verify_solve
    out = Path(out)
    if kind not in KINDS or type(tolerance) not in (float, int) or \
       not math.isfinite(tolerance) or not 0 < tolerance < 0.5:
        raise ValueError('Invalid convergence problem or tolerance')
    if not isinstance(names, list) or len(names) not in (2, 3):
        raise ValueError('Two or three mesh levels are required')
    contract = read_json(out / 'contract.json')
    mesh_sha = sha256(out / 'device.msh')
    levels = []; values = []; records = []
    for name in names:
        prefix = f'convergence-{kind}-L'
        if not isinstance(name, str) or not name.startswith(prefix) or not name[len(prefix):].isdigit():
            raise ValueError('Non-convergence or malformed configuration name')
        level = int(name[len(prefix):])
        if level > 3 or name not in contract['palace_configs']:
            raise ValueError('Unregistered Palace refinement configuration')
        cfg = read_json(out / (name + '.json'))
        if cfg['Model'].get('Refinement', {}).get('UniformLevels') != level or \
           cfg['Problem']['Output'] != name:
            raise ValueError('Palace refinement settings are inconsistent')
        record = verify_solve(out, name)
        if record['mesh_sha256'] != mesh_sha:
            raise ValueError('Convergence cases do not share input mesh')
        source = out / name / KINDS[kind][0]
        if kind == 'eigenmode':
            item = eigen_frequencies(source)
        else:
            item = em.read_palace_capacitance(source, len(contract['terminal_order']))
        levels.append(level); values.append(item); records.append({
            'level': level, 'configuration_sha256': record['configuration_sha256'],
            'source_sha256': sha256(source), 'solver_identity': record['solver_identity']})
    if levels != sorted(set(levels)) or any(v.shape != values[0].shape for v in values):
        raise ValueError('Refinement levels unordered or quantities have different dimensions')
    if len({r['solver_identity'] for r in records}) != 1:
        raise ValueError('A convergence study must use the same solver installation')
    changes = []
    for a, b in zip(values, values[1:]):
        scale = max(float(np.max(np.abs(b))), 1e-20)
        # Element-wise check with 0.1% floor: off-diagonal couplings cannot
        # disappear behind a much larger diagonal capacitance.
        denominator = np.maximum(np.abs(b), scale * 1e-3)
        changes.append(float(np.max(np.abs(b-a) / denominator)))
    last = changes[-1]
    passed = last <= float(tolerance)
    # A converged eigenfrequency ordered by its mode number still may not
    # refer to the same physical eigenvector at all refinement levels.
    qualified = False  # Requires an independent analytic/measurement benchmark.
    result = {
        'schema_version': 1, 'problem': kind, 'geometry_sha256': contract['geometry_sha256'],
        'mesh_sha256': mesh_sha, 'levels': levels, 'tolerance_relative': float(tolerance),
        'max_relative_changes': changes, 'normalization_floor_fraction': 1e-3, 'last_relative_change': last,
        'numerically_converged': passed, 'scientifically_qualified': qualified, 'independent_reference_checked': False,
        'assessment': ('PASS_NUMERICAL_ONLY' if passed else 'FAIL_CONVERGENCE'),
        'quantity': ('frequency_GHz' if kind == 'eigenmode' else 'maxwell_capacitance_fF'),
        'values': [v.tolist() for v in values], 'cases': records,
        'limitations': [
            'Numerical h-convergence is not validation of EM boundary conditions or geometry',
            'All levels reuse one initial mesh with Palace uniform refinement',
            'No comparison to independent analytical or experimental reference',
        ] + (['Mode rows are aligned only by Palace index; field overlap/mode tracking is absent',
              'An eigenmode convergence pass cannot authorize mode-derived Kerr or g']
             if kind == 'eigenmode' else []),
    }
    write_json(out / f'convergence-{kind}-report.json', result)
    return result


def run(out, kind, *, ranks=1, executable='palace', levels=DEFAULT_LEVELS, tolerance=0.005):
    """Execute real solver separately on each refinement, then verify all artifacts."""
    from .physical_qpu import solve
    names = prepare(out, kind, levels)
    solve(out, names, ranks=ranks, executable=executable)
    return summarize(out, kind, names, tolerance=tolerance)
