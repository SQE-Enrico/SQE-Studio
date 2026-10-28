#!/usr/bin/env python3
"""Fast non-blocking start-up check; results are visible in the Web UI.

All commands are fixed. This never executes project macros or installs anything.
"""
import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ('test_quantumlab.py','test_physical_qpu.py','test_palace_quality.py','test_parametric_qpu.py')


def main():
    results = []
    for name in TESTS:
        try:
            p = subprocess.run([sys.executable, '-m','unittest','discover', '-s', 'tests', '-p', name, '-q'],
                               cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=45, check=False)
            state = 'PASS' if p.returncode == 0 else 'FAIL'
        except (OSError, subprocess.TimeoutExpired):
            state = 'FAIL'
        results.append({'test':name,'status':state})
        print('[%s] %s' % (state,name),flush=True)
    report = {'checks':results,'status':'PASS' if all(x['status']=='PASS' for x in results) else 'WARN',
              'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'message':'Failures are recorded but do not prevent the local Web interface from opening.'}
    folder = ROOT / 'studio-data'
    folder.mkdir(parents=True,exist_ok=True)
    target = folder / 'startup-checks.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2)+'\n',encoding='utf-8')
    temp.replace(target)
    print('Start-up validation: '+report['status']+' (full details: System & Diagnostics in Web UI)',flush=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
