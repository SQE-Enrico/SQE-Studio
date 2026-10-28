"""Explicit export only; will not install Julia or run a nonlinear simulation."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqw.josephson_bridge import export_design


def main():
    p=argparse.ArgumentParser(description='Export SQE circuit for JosephsonCircuits.jl')
    p.add_argument('design',help='QuantumLab design JSON OR physical package nominal_circuit.json')
    p.add_argument('output',help='New output directory for Julia source and provenance')
    a=p.parse_args()
    data=json.loads(Path(a.design).read_text(encoding='utf-8'))
    print(json.dumps(export_design(data,a.output),indent=2))

if __name__=='__main__':main()
