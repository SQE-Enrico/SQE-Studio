#!/usr/bin/env python3
"""Optional Quantum Metal headless interop (run with .venv-metal Python)."""
import argparse
import json
from pathlib import Path
import sys

# Use the project's code directly even when Quantum Metal has its own venv.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqw.qmetal_interop import to_qdesign


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path, help='SQE positive-metal QGeometry JSON file')
    p.add_argument('--report',type=Path, help='Save component/QGeometry inventory as JSON')
    args=p.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    design=to_qdesign(manifest)
    polygons=design.qgeometry.tables['poly']
    report={'component_names':list(design.components.keys()),'polygons':len(polygons),
            'source_geometry_sha256':manifest['geometry_sha256'],
            'status':'real_Quantum_Metal_QGeometry_not_Palace_model',
            'note':'Import is one way; Gmsh and mesh use the original SQE geometry. No automatic pins, junction EPR or routes.'}
    if args.report:
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
