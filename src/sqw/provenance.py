"""Stage freshness and integrity checks, independent of scientific validation."""

from pathlib import Path
import os

from .io import read_json, sha256

DEPENDENTS = {
    "spec": ["report"],
    "layout": ["em-export", "mesh", "quantize", "report"],
    "em-export": ["solve:electrostatic", "solve:eigenmode", "solve:linearized"],
    "mesh": ["solve:electrostatic", "solve:eigenmode", "solve:linearized"],
    "solve:electrostatic": ["import"],
    "solve:eigenmode": ["import"],
    "import": ["quantize"],
    "quantize": ["experiment", "report"],
    "experiment": ["report"],
}


def invalidate(state, key):
    queue = list(DEPENDENTS.get(key, []))
    seen = set()
    while queue:
        child = queue.pop()
        if child in seen:
            continue
        seen.add(child)
        if child in state["stages"]:
            state["stages"][child] = "stale"
        queue.extend(DEPENDENTS.get(child, []))


def file_key(path, out):
    path, out = Path(path).resolve(), Path(out).resolve()
    try:
        return Path(os.path.relpath(path,out)).as_posix()
    except ValueError:  # Windows inputs on another drive cannot have relative paths.
        return str(path)


def hashes(paths, out):
    return {file_key(path, out): sha256(path) for path in paths}


def check_files(entries, out, description):
    for name, expected in entries.items():
        path = Path(out)/name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Changed or missing {description}: {name}; rerun its producer stage")


def check_stage(state, key, out, seen=None):
    seen = set() if seen is None else seen
    if key in seen:
        return
    seen.add(key)
    if state["stages"].get(key) != "completed":
        raise ValueError(f"Stage {key} must complete before this operation")
    record = state.get("stage_records", {}).get(key)
    if record is None:
        raise ValueError("Legacy run has no stage fingerprints; create a fresh v0.2 run")
    for parent in record.get("parents",[]):
        check_stage(state,parent,out,seen)
    check_files(record["inputs"], out, f"{key} input")
    check_files(record["outputs"], out, f"{key} output")


def verify(out):
    out = Path(out)
    state = read_json(out/"run.json")
    if not state["stages"]:
        raise ValueError("Run contains no completed stages")
    for key in state["stages"]:
        # An explicitly superseded FEM import is retained as history, not used downstream.
        if state["stages"][key] == "superseded":
            continue
        check_stage(state, key, out)
    check_files(read_json(out/"manifest.json")["sha256"], out, "manifest artifact")
    return {"status": "passed", "stage_count": len(state["stages"]),
            "physics_source": state.get("physics_source"),
            "scope": "artifact integrity and stage freshness; not fabrication or physics qualification"}
