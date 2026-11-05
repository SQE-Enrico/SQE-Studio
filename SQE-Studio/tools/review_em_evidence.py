#!/usr/bin/env python3
"""Review one explicit saved report without executing a solver or rewriting it."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError


def main():
    parser=argparse.ArgumentParser(description='Review recorded SQE native EM evidence; no native execution')
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, help='Create a new JSON file; existing files are preserved')
    parser.add_argument('--frequency-tolerance',type=float,
        help='Explicit what-if frequency criterion as a fraction, e.g. 0.03; original evidence stays unchanged')
    args=parser.parse_args()
    try:
        result=analyze_report_zip(args.report,frequency_tolerance=args.frequency_tolerance)
        text=json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n'
        if args.output:
            with args.output.open('x',encoding='utf-8') as output:
                output.write(text)
        else:
            print(text,end='')
        return 0
    except (ConvergenceEvidenceError,OSError,ValueError):
        print('Evidence review failed: invalid report or output unavailable; no native execution.',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
