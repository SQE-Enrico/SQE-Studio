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

from sqw.studio.process import document, resolve
from sqw.physical_qpu import default_spec, export_package, mesh, solve, verify_solve, extract_capacitance
from sqw.io import read_json, sha256

CASES = ('geometry', 'mesh', 'electrostatic', 'capacitance', 'eigenmode', 'driven')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--solver', default='palace')
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    # Caller creates a private, isolated temporary folder. Never follow symlinks.
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError('Invalid isolated diagnostics workspace')
    cfg, _ = resolve(document())
    spec = default_spec(cfg, 1)
    start = time.monotonic()
    result = {'case':args.case, 'source':'fixed_single_transmon_reference',
              'scientific_qualification':False}
    if args.case == 'geometry':
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
    elif args.case == 'capacitance':
        extracted = extract_capacitance(workspace)
        result.update(source=extracted['source'],
                      capacitance_matrix_size=len(extracted['projected_maxwell_c_ff']),
                      solver_completed=True)
    else:
        problems = ['driven-1', 'driven-2'] if args.case == 'driven' else [args.case]
        if args.case == 'electrostatic' or args.case == 'eigenmode' or args.case == 'driven':
            solve(workspace, problems, ranks=1, executable=args.solver, timeout=180)
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
