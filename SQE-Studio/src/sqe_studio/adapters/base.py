"""Adapter ABI: one immutable study + project snapshot -> native output artifacts.

All adapters implement `run(study, project, output_dir) -> dict` and raise
`EngineBlocked` whenever inputs are incomplete or a package is unavailable.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

class EngineBlocked(RuntimeError):
    pass

class EngineFailure(RuntimeError):
    pass

def require_module(module, label):
    if importlib.util.find_spec(module) is None:
        raise EngineBlocked(f'{label} is not installed in the configured engine runtime')

def safe_output(directory):
    output=Path(directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return output
