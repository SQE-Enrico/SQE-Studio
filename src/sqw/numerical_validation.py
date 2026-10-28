"""Independent, immutable-reference Palace FEM numerical validation.

All inputs are generated in an isolated diagnostic workspace. No user projects are
read and no solver output is synthesized. A passed analytical patch test does NOT
qualify an arbitrary superconducting-QPU simulation or its surface physics.
"""
from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

import numpy as np

from . import em, qualification
from .io import read_json, sha256, write_json
from .palace_bridge import command
from .palace_quality import eigen_frequencies

CAP_ERROR_LIMIT = 0.05
CAP_REFINEMENT_LIMIT = 0.02
CAVITY_ERROR_LIMIT = 0.10


def prepare(workspace: Path) -> dict:
    base = Path(workspace) / 'numerical-reference'
    if base.exists():
        raise ValueError('Numerical reference already prepared; refusing to overwrite')
    for level in (1, 2):
        qualification.prepare(base / f'L{level}', refinement=level)
    index = {'schema_version': 1, 'kind': 'independent_analytical_reference',
             'levels': [1, 2], 'capacitance_unit': 'F',
             'cavity_frequency_unit': 'GHz',
             'notes': ['The capacitor is an exact linear-potential FEM patch test.',
                       'Refinement invariance here does not establish QPU mesh convergence.',
                       'All Palace runs must produce authentic solver CSV files.']}
    write_json(base / 'reference-index.json', index)
    return {'reference': 'parallel_plate_capacitor_and_PEC_cavity',
            'levels': [1, 2], 'independent_reference_generated': True,
            'solver_executed': False, 'scientific_qualification': False}


def _case_dir(workspace: Path, kind: str, level: int) -> Path:
    if kind not in ('capacitor', 'cavity') or level not in (1, 2):
        raise ValueError('Unsupported fixed reference case')
    folder = Path(workspace) / 'numerical-reference' / f'L{level}' / kind
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('Reference geometry must be generated before solve')
    return folder


def execute(workspace: Path, kind: str, level: int, *, ranks=1, timeout=240):
    """Run a single Palace solve with strict provenance, bounded wall time, log retention."""
    folder = _case_dir(workspace, kind, level)
    name = 'electrostatic' if kind == 'capacitor' else 'eigenmode'
    output = folder / name / ('terminal-C.csv' if kind == 'capacitor' else 'eig.csv')
    if output.exists() or (folder / 'solver-record.json').exists():
        raise ValueError('Refusing to overwrite existing Palace reference output')
    mesh_sha = sha256(folder / 'device.msh')
    if mesh_sha != read_json(folder / 'mesh.json')['mesh_sha256']:
        raise ValueError('Reference mesh changed since generation')
    config = read_json(folder / f'{name}.json')
    if config.get('Problem', {}).get('Type') != ('Electrostatic' if kind == 'capacitor' else 'Eigenmode'):
        raise ValueError('Unexpected reference problem type')
    if config['Problem']['Output'] != name or config['Model']['Mesh'] != 'device.msh':
        raise ValueError('Reference output path or input mesh mismatch')
    args, solver = command(folder, name, ranks)
    if args and args[0].lower().endswith('wsl.exe'):
        args = args[:4] + ['timeout', '--signal=TERM', '--kill-after=10s', f'{int(timeout)}s'] + args[4:]
    start = time.monotonic()
    log = Path(workspace) / f'reference-{kind}-L{level}.log'
    record = {'schema_version': 1, 'kind': kind, 'level': level, 'solver_identity': solver,
              'mesh_sha256': mesh_sha, 'configuration_sha256': sha256(folder / f'{name}.json'),
              'status': 'started'}
    try:
        with log.open('wb') as stream:
            subprocess.run(args, cwd=folder, stdin=subprocess.DEVNULL,
                           stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=True)
        if not output.is_file() or not output.stat().st_size:
            raise ValueError('Palace completed without its expected reference CSV')
        record.update(status='completed', elapsed_seconds=round(time.monotonic()-start, 2),
                      output_sha256=sha256(output))
        write_json(folder / 'solver-record.json', record)
        return {'solver_completed': True, 'solver_identity': solver,
                'level': level, 'reference_case': kind,
                'mesh_sha256': mesh_sha, 'output_sha256': record['output_sha256'],
                'elapsed_seconds': record['elapsed_seconds'], 'scientific_qualification': False}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        record.update(status='failed', elapsed_seconds=round(time.monotonic()-start, 2),
                      error=type(exc).__name__)
        write_json(folder / 'solver-record.json', record)
        raise


def _verify(folder: Path, name: str, csv_name: str):
    record = read_json(folder / 'solver-record.json')
    source = folder / name / csv_name
    if (record.get('status') != 'completed' or
        record.get('mesh_sha256') != sha256(folder / 'device.msh') or
        record.get('configuration_sha256') != sha256(folder / (name + '.json')) or
        record.get('output_sha256') != sha256(source)):
        raise ValueError('Palace reference provenance is missing or modified')
    return record, source


def capacitance_assessment(workspace: Path):
    """Compare two authentic Palace solves to epsilon*A/d and each other."""
    base = Path(workspace) / 'numerical-reference'
    rows = []
    identity = None
    for level in (1, 2):
        folder = _case_dir(workspace, 'capacitor', level)
        record, source = _verify(folder, 'electrostatic', 'terminal-C.csv')
        if identity is not None and identity != record['solver_identity']:
            raise ValueError('Reference runs used different solver installations')
        identity = record['solver_identity']
        observed_f = float(em.read_palace_capacitance(source, 1)[0, 0]) * 1e-15
        expected_f = float(read_json(folder / 'reference.json')['analytic_capacitance_F'])
        if not all(math.isfinite(v) and v > 0 for v in (observed_f, expected_f)):
            raise ValueError('Nonpositive reference capacitance')
        rows.append({'level': level, 'mesh_sha256': record['mesh_sha256'],
                     'output_sha256': record['output_sha256'], 'observed_F': observed_f,
                     'analytic_F': expected_f, 'relative_error': abs(observed_f/expected_f-1)})
    reference_delta = abs(rows[1]['observed_F']-rows[0]['observed_F']) / rows[1]['observed_F']
    reference_pass = max(r['relative_error'] for r in rows) <= CAP_ERROR_LIMIT
    mesh_pass = reference_delta <= CAP_REFINEMENT_LIMIT
    result = {'schema_version': 1, 'kind': 'parallel_plate_patch_test', 'source': 'verified_palace_solver_CSV',
              'units': 'F', 'relative_error_limit': CAP_ERROR_LIMIT,
              'refinement_change_limit': CAP_REFINEMENT_LIMIT, 'levels': rows,
              'max_relative_error': max(r['relative_error'] for r in rows),
              'relative_refinement_change': reference_delta,
              'analytical_benchmark_pass': reference_pass,
              'reference_refinement_stable': mesh_pass,
              'numerical_reference_pass': reference_pass and mesh_pass,
              'scientific_qualification': False,
              'limitations': ['This parallel-plate potential is exactly linear and is a patch test, not a general convergence study.',
                              'No QPU geometry, material boundary interfaces, or conductor loss was validated.']}
    write_json(base / 'capacitance-benchmark.json', result)
    result['acceptance_pass'] = result['numerical_reference_pass']
    return result


def eigenmode_assessment(workspace: Path):
    """Compare lowest PEC-cavity eigenfrequency with its independent analytic value.

    Mode *ordering* alone cannot guarantee identity through degeneracies and crossing.
    """
    folder = _case_dir(workspace, 'cavity', 1)
    record, source = _verify(folder, 'eigenmode', 'eig.csv')
    observed = eigen_frequencies(source)
    expected = np.asarray(read_json(folder / 'reference.json')['frequencies_GHz'], dtype=float)
    if observed.size < 1 or not np.all(np.isfinite(expected)):
        raise ValueError('Cavity eigenmode data missing')
    # With shift-and-invert near the first cavity resonance, check the lowest mode.
    observed_first = float(np.min(observed))
    exact_first = float(expected[0])
    error = abs(observed_first / exact_first - 1)
    result = {'schema_version': 1, 'kind': 'PEC_rectangular_cavity',
              'source': 'verified_palace_solver_CSV', 'unit': 'GHz',
              'first_observed_GHz': observed_first, 'first_analytic_GHz': exact_first,
              'relative_error': error, 'relative_error_limit': CAVITY_ERROR_LIMIT,
              'analytical_benchmark_pass': error <= CAVITY_ERROR_LIMIT,
              'modes_observed_GHz': observed[:6].tolist(),
              'modes_analytic_GHz': expected[:6].tolist(),
              'mesh_sha256': record['mesh_sha256'], 'output_sha256': record['output_sha256'],
              'scientific_qualification': False,
              'limitations': ['Only the lowest frequency is compared; higher modes may be degenerate.',
                              'No field-overlap mode tracking and no QPU eigenmode qualification.']}
    write_json(Path(workspace) / 'numerical-reference' / 'eigenmode-benchmark.json', result)
    result['acceptance_pass'] = result['analytical_benchmark_pass']
    return result


def matrix_summary(extracted: dict) -> dict:
    """Expose safe, size-limited QPU capacitance results with physical units."""
    names = extracted['differential_coordinate_order']
    raw_names = extracted['terminal_order']
    projected = np.asarray(extracted['projected_maxwell_c_ff'], dtype=float)
    raw = np.asarray(extracted['conductor_maxwell_c_ff'], dtype=float)
    if (projected.ndim != 2 or projected.shape[0] != projected.shape[1] or
        projected.shape[0] != len(names) or projected.size > 256 or
        raw.ndim != 2 or raw.shape != (len(raw_names), len(raw_names)) or raw.size > 1024 or
        not np.all(np.isfinite(projected)) or not np.all(np.isfinite(raw))):
        raise ValueError('Invalid capacitance display dimensions or values')
    symmetry = float(np.max(np.abs(projected-projected.T)))
    eigenvalues = np.linalg.eigvalsh((projected+projected.T)/2)
    if eigenvalues.min() <= 0:
        raise ValueError('Projected capacitance is not positive definite')
    return {'source': 'verified_palace_electrostatic', 'unit': 'fF',
            'raw_terminal_names': raw_names, 'raw_maxwell_matrix': raw.tolist(),
            'coordinate_names': names, 'projected_matrix': projected.tolist(),
            'symmetry_max_abs_fF': symmetry,
            'minimum_eigenvalue_fF': float(eigenvalues.min()),
            'source_sha256': extracted['raw_sha256'],
            'scientifically_qualified': False,
            'note': 'Differential-coordinate Maxwell capacitance; feedlines held at zero AC potential. Not a fitted circuit or measured T1.'}
