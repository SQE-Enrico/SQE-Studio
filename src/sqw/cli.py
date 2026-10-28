"""Command-line entry point; every backend is explicitly selected."""

import argparse
import importlib.util
import json
import shutil
import subprocess

from . import config, workflow
from .io import environment
from .provenance import verify


def main():
    parser = argparse.ArgumentParser(prog="sqw",description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("doctor",help="Inspect Python modules and native executables")
    p = commands.add_parser("verify",help="Verify artifact integrity and stage freshness")
    p.add_argument("--run",required=True)
    p = commands.add_parser("qualify",help="Prepare independent capacitor/cavity reference problems")
    p.add_argument("--out",required=True)
    p.add_argument("--solve",action="store_true",help="Run actual Palace solves and compare against analytical references")
    p.add_argument("--refinement",type=int,default=1)
    p.add_argument("--palace",default="palace")
    p.add_argument("--ranks",type=int,default=1)
    p = commands.add_parser("assemble-mask",help="Attach a laboratory process junction GDS")
    p.add_argument("--run",required=True)
    p.add_argument("--process",required=True)
    p.add_argument("--out",required=True)
    for name in ("run","stage"):
        p = commands.add_parser(name)
        if name == "stage":
            p.add_argument("stage",choices=["spec","layout","em-export","mesh","solve","import","quantize","experiment","report"])
            p.add_argument("--problem",choices=["electrostatic","eigenmode","linearized"],default="electrostatic")
            p.add_argument("--force-surrogate",action="store_true",help="Explicitly replace the current extraction for quantize")
        else:
            p.add_argument("--mode",choices=["demo","imported","fem"],default="demo")
        p.add_argument("--config",default="configs/demo.toml")
        p.add_argument("--out",required=True)
        p.add_argument("--cad-backend",choices=["native","qpdk"],default="native")
        p.add_argument("--quantum-backend",choices=["scipy","scqubits"],default="scipy")
        p.add_argument("--dynamics-backend",choices=["scipy","qutip"],default="scipy")
        p.add_argument("--extraction")
        p.add_argument("--readout-mode",type=int)
        p.add_argument("--palace",default="palace")
        p.add_argument("--ranks",type=int,default=1)
    p = commands.add_parser("compare")
    p.add_argument("--parameters",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--out",required=True)
    p = commands.add_parser("tolerance")
    p.add_argument("--config",default="configs/demo.toml")
    p.add_argument("--out",required=True)
    p.add_argument("--samples",type=int,default=50)
    p.add_argument("--seed",type=int,default=123)
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        if command == "doctor":
            result = environment()
            result["executables"] = {x:shutil.which(x) for x in ("palace","mpiexec","klayout")}
            result["reference_modules"] = {x:importlib.util.find_spec(x) is not None
                                           for x in ("scqubits","qpdk","gmsh","qutip")}
            print(json.dumps(result,indent=2))
        elif command == "assemble-mask":
            from .assembly import assemble
            assemble(args["run"],args["process"],args["out"])
            print(f"Process candidate mask written to {args['out']}; laboratory review required")
        elif command == "verify":
            print(json.dumps(verify(args["run"]),indent=2))
        elif command == "qualify":
            from .qualification import qualify
            print(json.dumps(qualify(**args),indent=2))
        elif command == "compare":
            workflow.compare(args["parameters"],args["reference"],args["out"])
            print(f"Comparison written to {args['out']}")
        elif command == "tolerance":
            if args["samples"] < 2:
                raise ValueError("At least two samples are required")
            workflow.monte_carlo(config.load(args["config"]),args["out"],args["samples"],args["seed"])
        else:
            cfg = config.load(args.pop("config"))
            if args["ranks"] < 1:
                raise ValueError("MPI ranks must be positive")
            if command == "stage":
                name = args.pop("stage")
                workflow.stage(name,cfg,**args)
            else:
                workflow.run(cfg,**args)
            print(f"{command} completed: {args['out']}")
    except (ValueError,OSError,ImportError,subprocess.SubprocessError) as exc:
        parser.exit(2,f"sqw: {exc}\n")


if __name__ == "__main__":
    main()
