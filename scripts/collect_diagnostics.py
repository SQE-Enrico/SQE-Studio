#!/usr/bin/env python3
"""Standalone entrypoint: works with a compatible Python even without pip install."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqw.diagnostics import main

if __name__ == '__main__':
    raise SystemExit(main(['--root', str(ROOT), *sys.argv[1:]]))
