"""Isolated command entry point for a single browser-launched ecosystem run.

This entry point is internal to the web server and is not a user CLI workflow.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import traceback

from ..ecosystem import execute, verify


def main():
    if len(sys.argv) != 4:
        raise SystemExit('Internal ecosystem worker expects project root, output and policy')
    root = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    policy = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
    spec = json.loads((root / 'workflow.json').read_text(encoding='utf-8'))
    try:
        run = execute(spec, root, out, allow_project_code=policy['allow_project_code'],
                      allow_solvers=policy['allow_solvers'])
        result = verify(out)
        print('Workflow completed: ' + run['project'], flush=True)
        print('Integrity verification: ' + json.dumps(result), flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
