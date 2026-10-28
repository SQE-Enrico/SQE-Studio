#!/usr/bin/env python3
"""Export v0.7 parameter-driven QPU or compatible legacy v0.6 physical QPU.

Examples:
  python scripts/export_physical_qpu.py --parametric --size 4 --out exports/qpu4
  python scripts/export_physical_qpu.py --document examples/parametric-v07/manhattan-2q.json --out exports/2q
  python scripts/export_physical_qpu.py --size 2 --out exports/legacy2

All exports carry HOLD flags and user-declared nominal circuit elements.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqw import physical_qpu,parametric_qpu
from sqw.io import read_json
from sqw.studio.process import document,resolve


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--size',type=int,default=None,help='1..16 parametric; legacy 1/2/4 only')
    p.add_argument('--parametric',action='store_true',help='Use v0.7 materials/stack/graph/CPW schema')
    p.add_argument('--document',type=Path,help='SQE project or direct physical schema v2 JSON')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    doc=read_json(args.document) if args.document else document()
    if 'document' in doc and 'config' not in doc:doc=doc['document']
    if doc.get('schema_version')==2 and 'qubits' in doc and 'stack' in doc:
        spec=doc
        cfg,_=resolve(document())
    else:
        cfg,_=resolve(doc)
        spec=doc.get('physical_qpu')
    if spec is None:
        if args.parametric:spec=parametric_qpu.default_spec(cfg,args.size or 2)
        else:spec=physical_qpu.default_spec(cfg,args.size or 1)
    size=spec['size'] if spec.get('schema_version')==1 else len(spec['qubits'])
    if args.size is not None and size!=args.size:
        p.error(f'--size={args.size} conflicts with physical spec containing {size} qubits')
    out=physical_qpu.export_package(cfg,spec,args.out)
    print(f'Exported {size} qubit(s) into {args.out.resolve()}')
    print('Geometry SHA256:',out['contract']['geometry_sha256'])
    print('Status: HOLD — native Palace results and process DRC not implied')


if __name__=='__main__':main()
