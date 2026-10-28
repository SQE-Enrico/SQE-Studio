"""Postprocessing for two-level QPU h-refinement based on authentic Palace outputs.

This is a *numerical* study of a fixed single-transmon design, NOT a physical
qualification or an EPR/field-overlap based mode-identification procedure.
The diagnostic exporter only retains compact, allowlisted scientific results.
"""
from __future__ import annotations

import csv
from itertools import islice
import math
from pathlib import Path

import numpy as np

from . import em, palace_quality, fem_audit
from .io import read_json, sha256, write_json
from .physical_qpu import verify_solve

LEVELS = (0, 1)


def prepare(workspace: Path, problem: str) -> dict:
    """Prepare exactly two immutable solver configurations on the SAME QPU mesh."""
    if problem not in ('electrostatic', 'eigenmode'):
        raise ValueError('Unsupported QPU convergence problem')
    names = palace_quality.prepare(Path(workspace), problem, levels=LEVELS)
    # Capture one lightweight field frame for scientific inspection on L0 only.
    # Palace writes ParaView VTK data with this officially documented schema.
    # Large raw field arrays are NOT embedded in the diagnostics support ZIP.
    coarse = Path(workspace) / (names[0] + '.json')
    config = read_json(coarse)
    config['Problem']['OutputFormats'] = {'Paraview': True}
    config['Solver'][('Electrostatic' if problem=='electrostatic' else 'Eigenmode')]['Save'] = 1
    write_json(coarse, config)
    return {'kind': problem, 'levels': list(LEVELS), 'configurations': names,
            'mesh_refinement_method': 'Palace UniformLevels 0 and 1',
            'solver_executed': False, 'scientific_qualification': False}


def run_level(workspace: Path, problem: str, level: int, *, timeout: int = 600):
    """Run Palace once, refusing to reuse old outputs or mismatched configs."""
    if problem not in ('electrostatic', 'eigenmode') or type(level) is not int or level not in LEVELS:
        raise ValueError('Unsupported QPU convergence case')
    name = f'convergence-{problem}-L{level}'
    contract = read_json(Path(workspace) / 'contract.json')
    if name not in contract['palace_configs']:
        raise ValueError('QPU convergence configuration has not been prepared')
    from .physical_qpu import solve
    solve(workspace, [name], ranks=1, timeout=timeout)
    record = verify_solve(workspace, name)
    return {'kind': problem, 'level': level, 'solver_completed': True,
            'output_hashes': record['outputs_sha256'],
            'elapsed_seconds': round(record.get('elapsed_seconds', 0), 2),
            'scientific_qualification': False}


def _projection(order: list[str], nq: int) -> tuple[list[str], np.ndarray]:
    # Same explicitly defined differential coordinates as extract_capacitance().
    if nq < 1 or nq > 16 or len(order) > 64 or len(set(order)) != len(order):
        raise ValueError('Invalid physical-QPU terminal order')
    transform = np.zeros((len(order), 2*nq), dtype=float)
    for q in range(nq):
        for suffix, factor in (('pad_a', .5), ('pad_b', -.5)):
            transform[order.index(f'Q{q}.{suffix}'), q] = factor
        transform[order.index(f'Q{q}.resonator'), nq+q] = 1.
    return ([f'Q{q}.differential' for q in range(nq)] +
            [f'Q{q}.resonator' for q in range(nq)]), transform


def _energy_inventory(workspace: Path, names: list[str]) -> list[dict]:
    """Record actual solver field/energy outputs without inferring EPR values.

    CSV columns are reported as headers only; full field files can be huge and
    are deliberately excluded from the privacy-minimised diagnostics archive.
    """
    rows = []
    for level, name in zip(LEVELS, names):
        verify_solve(workspace, name)
        output = Path(workspace) / name
        for filename in ('domain-E.csv', 'port-EPR.csv', 'surface-Q.csv', 'probe-E.csv', 'probe-B.csv'):
            file = output / filename
            if not file.is_file() or not file.stat().st_size:
                continue
            # Verify against the original Palace manifest; never accept an extra
            # output file added after the solver run without provenance.
            record = read_json(Path(workspace)/f'solve-{name}.json')
            entry = f'{name}/{filename}'
            if record.get('outputs_sha256', {}).get(entry) != sha256(file):
                raise ValueError('Unverified Palace energy/field output: '+entry)
            metrics = []
            with file.open(encoding='utf-8-sig', errors='replace', newline='') as stream:
                table = csv.reader(stream)
                columns = next(table, [])[:24]
                # Inspect at most 1000 bounded Palace records; retain the last
                # finite numerical values with original column names and units.
                for idx, line in enumerate(table):
                    if idx >= 1000: break
                    if not line or len(line) > 64: continue
                    parsed = []
                    for col, raw in zip(columns, line):
                        try: value = float(raw)
                        except (ValueError, TypeError): continue
                        if math.isfinite(value): parsed.append({'name': col[:96], 'value': value})
                    if parsed: metrics = parsed[:12]
            rows.append({'level':level, 'file':filename, 'columns':columns[:24],
                         'last_numeric_row': metrics,
                         'sha256':sha256(file), 'kind':'palace_scalar_output'})
        # Presence alone is NOT permission to read binary Paraview field data.
        pv = output / 'paraview'
        if pv.is_dir() and not pv.is_symlink():
            files = list(islice((p for p in pv.rglob('*') if p.is_file() and not p.is_symlink()), 5000))
            rows.append({'level':level, 'kind':'paraview_inventory', 'files':len(files),
                         'formats':sorted({p.suffix.lower() for p in files})[:12],
                         'note':'Raw 3D fields are not included or rendered by this report.'})
    return rows


def assess(workspace: Path, problem: str, *, tolerance: float = 0.01) -> dict:
    """Compare two Palace runs and retain numeric evidence even on tolerance failure."""
    if problem not in ('electrostatic', 'eigenmode'):
        raise ValueError('Unsupported QPU convergence problem')
    names = [f'convergence-{problem}-L{level}' for level in LEVELS]
    comparison = palace_quality.summarize(workspace, problem, names, tolerance=tolerance)
    result = dict(comparison)
    result['source'] = 'verified_palace_FEM'
    result['device'] = 'isolated_fixed_single_transmon_diagnostic_geometry'
    result['energy_and_field_inventory'] = _energy_inventory(workspace, names)
    result['acceptance_pass'] = bool(comparison['numerically_converged'])
    result['scientific_qualification'] = False
    result['field_overlap_mode_identification'] = False
    audit_path = Path(workspace)/'geometry-boundary-audit.json'
    if audit_path.is_file():
        audit = read_json(audit_path)
        result['geometry_boundary_audit'] = {k:audit[k] for k in ('preflight_pass','failures','warnings','terminal_count','mesh_sha256')}
    else:
        result['geometry_boundary_audit'] = {'preflight_pass':False,'warnings':['No mesh-boundary audit available; run QPU Audit first']}
    if problem == 'electrostatic':
        contract = read_json(Path(workspace)/'contract.json')
        order = contract['terminal_order']
        labels, transform = _projection(order, len(contract['junction_order']))
        matrices = []
        for name in names:
            verify_solve(workspace, name)
            matrix = em.read_palace_capacitance(Path(workspace)/name/'terminal-C.csv', len(order))
            if not np.all(np.isfinite(matrix)) or not np.allclose(matrix,matrix.T,rtol=1e-8,atol=1e-7):
                raise ValueError('QPU Maxwell capacitance is nonfinite or asymmetric')
            projected = transform.T @ matrix @ transform
            eigen = np.linalg.eigvalsh((projected+projected.T)/2)
            if not np.all(np.isfinite(eigen)) or eigen.min() <= 0:
                raise ValueError('QPU differential capacitance is not positive definite')
            matrices.append(projected)
        reference = matrices[-1]
        floor = max(float(np.max(np.abs(reference)))*1e-3, 1e-20)
        changes = np.abs(matrices[1]-matrices[0]) / np.maximum(np.abs(reference), floor)
        result['energy_consistency'] = [
            {'level': level, **fem_audit.energy_consistency(workspace, name, matrix)}
            for level, name, matrix in zip(LEVELS, names, [em.read_palace_capacitance(Path(workspace)/nm/'terminal-C.csv', len(order)) for nm in names])
        ]
        result['qpu_capacitance'] = {'unit':'fF', 'coordinates':labels,
              'levels': [m.tolist() for m in matrices],
              'min_eigenvalue_fF': [float(np.linalg.eigvalsh(m).min()) for m in matrices],
              'max_projected_relative_change':float(np.max(changes)),
              'maximum_entry_change_fF':float(np.max(np.abs(matrices[1]-matrices[0]))),
              'note':'Differential C with readout conductors retained; no JJ capacitance or T1 inference.'}
        result['numerically_converged'] = (result['numerically_converged'] and
                                           result['qpu_capacitance']['max_projected_relative_change'] <= tolerance)
        result['acceptance_pass'] = result['numerically_converged']
        result['energy_audit_informational_only'] = True
    else:
        result['mode_tracking'] = 'INDEX_ONLY_NOT_FIELD_OVERLAP'
        result['acceptance_pass'] = True  # The stage extracted frequencies; identity remains unverified.
        result['assessment'] = 'INFORMATIONAL_ONLY_MODE_IDENTITY_UNVERIFIED'
        result['note'] = ('Frequency differences are measured by ordered Palace mode index. '
                          'No mode overlap and no certification of mode identity.')
    result['limitations'] = list(result['limitations']) + [
        'Only two levels: passing a tolerance is not proof of asymptotic convergence.',
        'No material, interface loss, EPR, mode-field overlap, or fabrication qualification.']
    write_json(Path(workspace)/f'qpu-{problem}-convergence-summary.json', result)
    return result


# Experimental AMR. It is opt-in and never replaces existing uniform runs.
AMR_NAME = 'convergence-electrostatic-L2'  # Already allowlisted by WSL runner.


def prepare_amr(workspace: Path) -> dict:
    """Create one bounded Palace 0.16-compatible electrostatic AMR run."""
    from copy import deepcopy
    out = Path(workspace)
    audit = read_json(out/'geometry-boundary-audit.json')
    if not audit.get('preflight_pass') or audit['mesh_sha256'] != sha256(out/'device.msh'):
        raise ValueError('A passing geometry/mesh preflight is required for AMR')
    target = out/(AMR_NAME + '.json')
    if target.exists() or (out/AMR_NAME).exists():
        raise ValueError('AMR output already exists')
    base = read_json(out/'electrostatic.json')
    if base['Problem']['Type'] != 'Electrostatic':
        raise ValueError('AMR is restricted to electrostatic problems')
    cfg = deepcopy(base)
    cfg['Problem']['Output'] = AMR_NAME
    cfg['Model']['Refinement'] = {
        'UniformLevels': 0, 'Tol': 0.02, 'MaxIts': 1,
        'MaxSize': 150000, 'UpdateFraction': 0.5,
        'Nonconformal': False, 'SaveAdaptIterations': True,
        'SaveAdaptMesh': False,
    }
    cfg['Problem']['OutputFormats'] = {'Paraview': False, 'GridFunction': False}
    write_json(target, cfg)
    contract = read_json(out/'contract.json')
    if AMR_NAME in contract['palace_configs']:
        raise ValueError('Repeated AMR configuration name')
    contract['palace_configs'].append(AMR_NAME)
    write_json(out/'contract.json', contract)
    return {'solver_executed':False, 'configuration':AMR_NAME,
            'refinement':cfg['Model']['Refinement'], 'scientific_qualification':False,
            'note':'One adaptive iteration and limited DOFs; solver acceptance not yet verified on Windows.'}


def run_amr(workspace: Path, *, timeout: int = 780) -> dict:
    from .physical_qpu import solve
    solve(workspace, [AMR_NAME], ranks=1, timeout=timeout)
    record = verify_solve(workspace, AMR_NAME)
    return {'solver_executed':True, 'output_hashes':record['outputs_sha256'],
            'elapsed_seconds':round(record.get('elapsed_seconds', 0),2),
            'scientific_qualification':False}


def assess_amr(workspace: Path) -> dict:
    out = Path(workspace)
    record = verify_solve(out, AMR_NAME)
    contract = read_json(out/'contract.json')
    matrix = em.read_palace_capacitance(out/AMR_NAME/'terminal-C.csv',len(contract['terminal_order']))
    metric = fem_audit.energy_consistency(out, AMR_NAME, matrix)
    iterations = []
    for ix in range(1,3):
        file = out/AMR_NAME/f'iteration{ix}'/'terminal-C.csv'
        entry = f'{AMR_NAME}/iteration{ix}/terminal-C.csv'
        if file.is_file() and record['outputs_sha256'].get(entry) == sha256(file):
            previous = em.read_palace_capacitance(file, len(contract['terminal_order']))
            delta = float(np.max(np.abs(matrix-previous)) / max(float(np.max(np.abs(matrix))),1e-20))
            iterations.append({'iteration':ix,'relative_maxwell_change_vs_final':delta,
                               'source_sha256':sha256(file)})
    output = {'source':'verified_palace_FEM', 'solver_executed':True,
              'adaptive_iterations_found':len(iterations), 'iterations':iterations,
              'final_maxwell_capacitance_fF':matrix.tolist(),
              'energy_consistency':metric,
              'convergence_qualified':False, 'scientific_qualification':False,
              'assessment':'INFORMATIONAL_AMR_SOLVE', 'acceptance_pass':True,
              'note':'One bounded AMR solve is not a mesh-convergence proof; check internal iteration outputs and geometry.'}
    write_json(out/'qpu-amr-audit.json', output)
    return output
