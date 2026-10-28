#!/usr/bin/env python3
"""Postprocess authentic, hashed Palace physical workflow jobs; never generate fake EM data.

Usage:
  python scripts/postprocess_physical.py JOB_DIR capacitance
  python scripts/postprocess_physical.py JOB_DIR epr --mode-column i \
    --junction-col J0='p[100]' [--junction-col J1='p[101]']
  python scripts/postprocess_physical.py JOB_DIR purcell --fq 5 --fr 7 --g-mhz 40 --qc 15000
  python scripts/postprocess_physical.py JOB_DIR dielectric --freq 5 \
    --participation substrate=.1 --tan-delta substrate=1e-6

EPR column strings are VERSION-SPECIFIC and must match the actual CSV headers.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sqw import physical_qpu as physical


def pairs(items):
    out={}
    for item in items:
        key, sep, value = item.partition('=')
        if not sep or not key or key in out:
            raise ValueError(f'Expected unique NAME=VALUE mapping; got {item!r}')
        out[key]=value
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('job_dir',type=Path,help='Folder containing physical_spec.json, contract.json and solver outputs')
    p.add_argument('analysis',choices=('capacitance','epr','purcell','dielectric'))
    p.add_argument('--mode-column')
    p.add_argument('--junction-col',action='append',default=[],metavar='JID=CSV_HEADER')
    p.add_argument('--fq',type=float)
    p.add_argument('--fr',type=float)
    p.add_argument('--g-mhz',type=float)
    p.add_argument('--qc',type=float)
    p.add_argument('--freq',type=float)
    p.add_argument('--participation',action='append',default=[],metavar='REGION=ENERGY_FRACTION')
    p.add_argument('--tan-delta',action='append',default=[],metavar='REGION=LOSS_TANGENT')
    a=p.parse_args()
    try:
        if a.analysis=='capacitance':
            result=physical.extract_capacitance(a.job_dir)
        elif a.analysis=='epr':
            if not a.mode_column or not a.junction_col:p.error('epr requires --mode-column and --junction-col')
            result=physical.epr_from_palace_mapped(a.job_dir,a.mode_column,pairs(a.junction_col))
        elif a.analysis=='purcell':
            if None in (a.fq,a.fr,a.g_mhz,a.qc):p.error('purcell requires --fq --fr --g-mhz --qc')
            result=physical.purcell_estimate(a.fq,a.fr,a.g_mhz,a.qc)
        else:
            if a.freq is None:p.error('dielectric requires --freq')
            result=physical.dielectric_loss_budget(a.freq,
                {k:float(v) for k,v in pairs(a.participation).items()},
                {k:float(v) for k,v in pairs(a.tan_delta).items()})
    except (ValueError,KeyError,FileNotFoundError) as exc:
        p.error(str(exc))
    print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
