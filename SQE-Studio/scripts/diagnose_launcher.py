"""Console-visible fallback for Windows file-association / silent pythonw failures.

Run by double-clicking the bundled Troubleshoot SQE Studio.cmd; no install and
no solver initialization outside the normal launcher takes place here.
"""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    print('SQE Studio desktop launcher diagnostic')
    try:
        sys.path.insert(0,str(root))
        from workstation_setup import environment_inventory
        status = environment_inventory(root)
        print('Current Python: '+status['active_python'])
        print('Ready managed environments: '+str(sum(int(item['ready']) for item in status['candidates'])))
        print('Incomplete managed environments: '+str(sum(int(not item['ready']) for item in status['candidates'])))
        print('Runtime connected: '+str(status['managed_selected']))
    except (RuntimeError, OSError, ValueError) as exc:
        print('Runtime inventory unavailable: '+type(exc).__name__)
    print('Starting the production entrypoint with visible errors...')
    runpy.run_path(str(root / 'Launch SQE Studio.pyw'), run_name='__main__')
