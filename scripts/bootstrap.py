#!/usr/bin/env python3
"""Create a checked, isolated Python environment and run the first example."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def normalized_freeze(text):
    return "\n".join(sorted(line.strip() for line in text.splitlines()
                            if line.strip() and not line.startswith(("-e ", "#")))) + "\n"


def isolated_environment(path):
    cfg = Path(path)/"pyvenv.cfg"
    if not cfg.exists():
        return
    values = dict(line.lower().split("=", 1) for line in cfg.read_text().splitlines() if "=" in line)
    values = {key.strip(): value.strip() for key, value in values.items()}
    if values.get("include-system-site-packages") != "false":
        raise ValueError("Existing venv inherits system packages. Choose --venv .venv-clean; it is preserved.")


def install_plan(python, profile, lock=None, wheelhouse=None, offline=False):
    index = (["--no-index"] if offline else [])
    if wheelhouse:
        index += ["--find-links", str(wheelhouse)]
    base = [str(python), "-m", "pip", "install", *index]
    commands = [base + ["setuptools==84.1.0", "wheel==0.48.0"]]
    if lock:
        commands.append(base + ["-r", str(lock)])
    else:
        commands.append(base + ["-r", str(ROOT/"requirements/core.lock")])
        if profile == "full":
            commands.append(base + ["-c", str(ROOT/"requirements/core.lock"),
                                    "-r", str(ROOT/"requirements/reference.in")])
    commands.append(base + ["--no-deps", "--no-build-isolation", "-e", str(ROOT)])
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["core", "full"], default="core")
    parser.add_argument("--venv", type=Path, default=ROOT/".venv")
    parser.add_argument("--lock", type=Path, help="Restore a previously qualified full freeze")
    parser.add_argument("--wheelhouse", type=Path, help="Approved local wheel directory")
    parser.add_argument("--offline", action="store_true", help="Disable package-index access")
    parser.add_argument("--plan", action="store_true", help="Print commands without changing files")
    parser.add_argument("--skip-demo", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        parser.error("Use Python 3.11-3.13; Python 3.12 is the delivery baseline")
    dest = args.venv.resolve()
    lock = args.lock.resolve() if args.lock else None
    wheelhouse = args.wheelhouse.resolve() if args.wheelhouse else None
    if lock is not None and not lock.is_file():
        parser.error("The requested lock file does not exist")
    if wheelhouse is not None and not wheelhouse.is_dir():
        parser.error("The requested wheelhouse does not exist")
    if args.offline and wheelhouse is None:
        parser.error("--offline requires --wheelhouse with the project's approved wheels")
    python = dest/("Scripts/python.exe" if os.name == "nt" else "bin/python")
    plan = install_plan(python, args.profile, lock, wheelhouse, args.offline)
    if args.plan:
        print(json.dumps({"venv": str(dest), "profile": args.profile,
                          "network": "disabled" if args.offline else "package index or configured mirror",
                          "commands": plan}, indent=2))
        return
    try:
        isolated_environment(dest)
    except ValueError as exc:
        parser.error(str(exc))
    if not (dest/"pyvenv.cfg").exists():
        venv.EnvBuilder(with_pip=True).create(dest)
    state_path = dest/"sqw-environment.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else None

    def freeze():
        result = subprocess.check_output([str(python), "-m", "pip", "freeze"], cwd=ROOT, text=True)
        return normalized_freeze(result)

    if previous and previous.get("status") == "ready":
        actual = hashlib.sha256(freeze().encode()).hexdigest()
        if actual != previous["freeze_sha256"]:
            parser.error("Environment drift detected before installation; choose a new --venv to requalify")
        if previous["profile"] == "full" and args.profile == "core":
            parser.error("Use the existing full profile or select a separate core --venv")
    record_dir = ROOT/".sqw"
    record_dir.mkdir(exist_ok=True)
    suffix = "" if dest == ROOT/".venv" else "-"+hashlib.sha256(str(dest).encode()).hexdigest()[:10]
    record = record_dir/f"{args.profile}{suffix}-resolved.txt"
    state = {"status": "installing", "profile": args.profile, "python": str(python),
             "lock": str(lock) if lock else None, "commands": plan}
    state_path.write_text(json.dumps(state, indent=2)+"\n")
    try:
        for command in plan:
            subprocess.run(command, cwd=ROOT, check=True)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, check=True)
        if args.profile == "full":
            subprocess.run([str(python), "-c", "import scqubits, qpdk, gmsh, qutip"], cwd=ROOT, check=True)
        resolved = freeze()
        record.write_text(resolved)
        subprocess.run([str(python), "-m", "sqw", "doctor"], cwd=ROOT, check=True)
        if not args.skip_tests:
            subprocess.run([str(python), "-m", "unittest", "discover", "-s", "tests", "-v"],
                           cwd=ROOT, check=True)
        if not args.skip_demo:
            demo = ROOT/"build"/("first-run" if not suffix else f"first-run{suffix}")
            if not demo.exists():
                subprocess.run([str(python), "-m", "sqw", "run", "--out", str(demo)], cwd=ROOT, check=True)
            else:
                subprocess.run([str(python), "-m", "sqw", "verify", "--run", str(demo)], cwd=ROOT, check=True)
            print(f"Open {demo/'report.html'}")
        state.update(status="ready", freeze_sha256=hashlib.sha256(resolved.encode()).hexdigest(),
                     freeze_file=str(record))
        state_path.write_text(json.dumps(state, indent=2)+"\n")
    except (OSError, subprocess.SubprocessError) as exc:
        state.update(status="failed", error=str(exc))
        state_path.write_text(json.dumps(state, indent=2)+"\n")
        parser.exit(2, f"Setup did not complete: {exc}. Inspect {state_path}; no successful setup is claimed.\n")
    print(f"Ready. Use {python} -m sqw --help")
    if args.profile == "full":
        print("Palace, MPI and KLayout GUI are native tools. Continue with docs/setup.md.")


if __name__ == "__main__":
    main()
