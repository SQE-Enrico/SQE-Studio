#!/usr/bin/env python3
"""Record the optional Gmsh post-bootstrap install in the qualified venv manifest.

Called with that venv's interpreter. Fail if pip check or Gmsh import fails.
The new resolved dependency list is stored beside the original core record.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
manifest=ROOT/'.venv'/'sqw-environment.json'
if not manifest.is_file(): raise SystemExit('SQE bootstrap manifest missing')
record=json.loads(manifest.read_text(encoding='utf-8'))
if record.get('status')!='ready': raise SystemExit('SQE environment not ready')
subprocess.run([sys.executable,'-m','pip','check'],check=True)
import gmsh
if not gmsh.__version__.startswith('4.15.'):
    raise SystemExit('Unsupported Gmsh version; expected 4.15.x')
gmsh.initialize()
gmsh.finalize()
freeze=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
normalized='\n'.join(sorted(line.strip() for line in freeze.splitlines()
                           if line.strip() and not line.startswith(('-e ','#'))))+'\n'
record['freeze_sha256']=hashlib.sha256(normalized.encode()).hexdigest()
record.setdefault('optional_components',{})['gmsh']={
    'version':gmsh.__version__,'python':sys.executable,'native_api_initialized':True,
    'note':'Optional Windows FEM mesher installed after core bootstrap'}
result=ROOT/'.venv'/'sqw-environment-with-gmsh.txt'
result.write_text(normalized,encoding='utf-8')
record['freeze_file']=str(result)
manifest.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('Gmsh registered in SQE resolved environment manifest.')
