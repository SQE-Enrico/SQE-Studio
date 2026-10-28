#!/usr/bin/env python3
"""One-command local/tunnel start; routine work happens in the browser."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists():
    subprocess.run([sys.executable,str(root/'scripts/bootstrap.py'),'--skip-demo','--skip-tests'],cwd=root,check=True)
subprocess.run([str(python),'-m','sqw.studio.launch',*sys.argv[1:]],cwd=root,check=True)
