"""Fixed, isolated scientific validation cases for the local Web control center.

Invoked only by a time-limited diagnostics worker. Does not inspect SQE projects.
Case identifiers are allowlisted; Palace outputs are not synthesized.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import os
import shutil
import subprocess

from sqw.studio.process import document, resolve
from sqw.physical_qpu import default_spec, export_package, mesh, solve, verify_solve, extract_capacitance
from sqw.io import read_json, sha256
from sqw import qpu_validation, fem_audit

CASES = ('geometry', 'mesh', 'electrostatic', 'capacitance', 'eigenmode', 'driven', 'mesh_smoke', 'solver_sanity', 'reference_prepare', 'reference_cap_L1', 'reference_cap_L2', 'reference_cap_compare', 'reference_eigenmode', 'qpu_cap_prepare', 'qpu_cap_L0', 'qpu_cap_L1', 'qpu_cap_assess', 'qpu_mode_prepare', 'qpu_mode_L0', 'qpu_mode_L1', 'qpu_mode_assess', 'qpu_mesh_audit', 'qpu_amr_prepare', 'qpu_amr_run', 'qpu_amr_assess')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--solver', default='palace')
    parser.add_argument('--profile', choices=('quick','standard','numerical','full','qpu','qpu_modes','qpu_audit','qpu_amr'), default='full')
    parser.add_argument('--deadline', type=int, default=160)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    # Caller creates a private, isolated temporary folder. Never follow symlinks.
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError('Invalid isolated diagnostics workspace')
    cfg = spec = None
    if args.case in ('geometry','mesh'):
        cfg, _ = resolve(document())
        spec = default_spec(cfg, 1)
    if args.profile in ('standard','qpu','qpu_modes') and cfg is not None:
        # Only the diagnostic reference uses these coarser meshing values.
        # This is for execution tests, NOT mesh-converged physics.
        cfg['em']['mesh_min_um'] = max(cfg['em']['mesh_min_um'], 25.0)
        cfg['em']['mesh_max_um'] = max(cfg['em']['mesh_max_um'], 500.0)
    start = time.monotonic()
    result = {'case':args.case, 'source':'fixed_single_transmon_reference',
              'scientific_qualification':False}
    if args.case.startswith('qpu_'):
        result['source'] = 'isolated_single_transmon_QPU_convergence'
    if args.case.startswith('reference_'):
        result['source'] = 'independent_analytical_reference'
    elif args.case in ('mesh_smoke','solver_sanity'):
        result['source'] = 'tooling_sanity_no_device'
    if args.case == 'mesh_smoke':
        # A unit box takes seconds rather than constructing a million-cell QPU.
        import gmsh
        gmsh.initialize(['-nopopup'])
        try:
            gmsh.option.setNumber('General.Terminal', 0)
            gmsh.model.add('sqe_solver_sanity_box')
            gmsh.model.occ.addBox(0, 0, 0, 1, 1, 1)
            gmsh.model.occ.synchronize()
            gmsh.option.setNumber('Mesh.MeshSizeMax', 0.65)
            gmsh.model.mesh.generate(3)
            nodes = len(gmsh.model.mesh.getNodes()[0])
            types, tags, _ = gmsh.model.mesh.getElements(3)
            cells = sum(len(t) for t in tags)
            if nodes < 4 or cells < 1: raise ValueError('Empty Gmsh 3D mesh')
            result.update(nodes=nodes, volume_elements=cells,
                          method='isolated unit-box 3D mesh; not a QPU mesh')
        finally:
            gmsh.finalize()
    elif args.case == 'solver_sanity':
        # A genuine Palace executable/loader check. Not a numerical FEM solve.
        from sqw.palace_bridge import backend, distro
        if backend() == 'wsl':
            if os.name != 'nt': raise RuntimeError('WSL backend requires Windows')
            command = ['wsl.exe', '-d', distro(), '--exec', 'bash', '-lc',
                'set -e; if [ -x "$HOME/.sqe/palace/bin/palace" ]; then exe="$HOME/.sqe/palace/bin/palace"; '
                'else source "$HOME/.sqe/spack/share/spack/setup-env.sh"; spack load palace; exe="$(command -v palace)"; fi; '
                'test -x "$exe"; "$exe" --help >/dev/null; echo SQE_PALACE_EXECUTABLE_READY=1']
        else:
            exe = shutil.which('palace')
            if not exe: raise FileNotFoundError('Native Palace executable not found')
            command = [exe, '--help']
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=min(75, args.deadline), check=False)
        if completed.returncode != 0 or (backend() == 'wsl' and 'SQE_PALACE_EXECUTABLE_READY=1' not in completed.stdout):
            raise RuntimeError('Palace executable/Spack activation failed (exit code '+str(completed.returncode)+')')
        result.update(solver_executable_ready=True,
                      numerical_solver_executed=False,
                      method='Spack activation and executable permission check; not a solve')
    elif args.case.startswith('reference_'):
        from sqw import numerical_validation as numerical
        if args.case == 'reference_prepare':
            result.update(numerical.prepare(workspace))
        elif args.case == 'reference_cap_L1':
            result.update(numerical.execute(workspace, 'capacitor', 1, timeout=args.deadline))
        elif args.case == 'reference_cap_L2':
            result.update(numerical.execute(workspace, 'capacitor', 2, timeout=args.deadline))
        elif args.case == 'reference_cap_compare':
            result.update(numerical.capacitance_assessment(workspace))
        elif args.case == 'reference_eigenmode':
            result.update(numerical.execute(workspace, 'cavity', 1, timeout=args.deadline))
            result.update(numerical.eigenmode_assessment(workspace))
    elif args.case == 'geometry':
        export_package(cfg, spec, workspace)
        contract = read_json(workspace/'contract.json')
        result.update(geometry_sha256=contract['geometry_sha256'],
                      configs=contract['palace_configs'],
                      gds_generated=(workspace/'physical_HOLD.gds').stat().st_size > 0)
    elif args.case == 'mesh':
        contract = read_json(workspace/'contract.json')
        from sqw.physical_qpu import build
        generated = mesh(cfg, build(cfg, spec), workspace)
        if generated['mesh_sha256'] != sha256(workspace/'device.msh'):
            raise ValueError('3D mesh checksum does not match the output file')
        if contract['geometry_sha256'] != generated['geometry_sha256']:
            raise ValueError('Geometry and meshing source do not match')
        result.update(nodes=generated['nodes'],volume_elements=generated['volume_elements'],
                      mesh_sha256=generated['mesh_sha256'])
    elif args.case == 'qpu_mesh_audit':
        result.update(fem_audit.geometry_boundary_audit(workspace))
        result['acceptance_pass'] = result['preflight_pass']
    elif args.case == 'qpu_amr_prepare':
        result.update(qpu_validation.prepare_amr(workspace))
    elif args.case == 'qpu_amr_run':
        result.update(qpu_validation.run_amr(workspace, timeout=max(30,args.deadline-15)))
    elif args.case == 'qpu_amr_assess':
        result.update(qpu_validation.assess_amr(workspace))
    elif args.case in ('qpu_cap_prepare','qpu_mode_prepare'):
        problem = 'electrostatic' if args.case == 'qpu_cap_prepare' else 'eigenmode'
        result.update(qpu_validation.prepare(workspace, problem))
    elif args.case in ('qpu_cap_L0','qpu_cap_L1','qpu_mode_L0','qpu_mode_L1'):
        problem = 'electrostatic' if args.case.startswith('qpu_cap') else 'eigenmode'
        level = int(args.case[-1])
        result.update(qpu_validation.run_level(workspace, problem, level,
                      timeout=max(30, args.deadline-15)))
    elif args.case in ('qpu_cap_assess','qpu_mode_assess'):
        problem = 'electrostatic' if args.case == 'qpu_cap_assess' else 'eigenmode'
        result.update(qpu_validation.assess(workspace, problem, tolerance=0.01))
    elif args.case == 'capacitance':
        extracted = extract_capacitance(workspace)
        from sqw.numerical_validation import matrix_summary
        result.update(source=extracted['source'],
                      capacitance_matrix_size=len(extracted['projected_maxwell_c_ff']),
                      solver_completed=True,
                      capacitance=matrix_summary(extracted))
    else:
        problems = ['driven-1', 'driven-2'] if args.case == 'driven' else [args.case]
        if args.case == 'electrostatic' or args.case == 'eigenmode' or args.case == 'driven':
            inner = max(30, (args.deadline-25)//len(problems))
            solve(workspace, problems, ranks=1, executable=args.solver, timeout=inner)
        records = [verify_solve(workspace, problem) for problem in problems]
        result.update(artifact_count=sum(len(r['outputs_sha256']) for r in records),
                      output_hashes={name:hash for r in records for name,hash in r['outputs_sha256'].items()},
                      solver_completed=True)

    result['elapsed_seconds'] = round(time.monotonic()-start,2)
    print('SQE_PROBE_RESULT=' + json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('SQE_PROBE_FAILURE='+type(exc).__name__+': '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(1)
