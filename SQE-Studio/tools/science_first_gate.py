#!/usr/bin/env python3
"""Check the current policy; historical approvals are not needed by this release."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqe_studio.governance import check,ScienceFirstGateError

def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    try:result=check(args.root);code=0
    except (ScienceFirstGateError,OSError) as error:result={'status':'NO_GO','reason':str(error)};code=2
    print(json.dumps(result,sort_keys=True));return code

if __name__=='__main__':raise SystemExit(main())
