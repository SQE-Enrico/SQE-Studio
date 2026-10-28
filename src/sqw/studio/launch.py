"""Local/tunnel launcher. Production uses the separate supplied web and worker services."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer,make_server

from .server import Application
from .settings import Settings


class ThreadedServer(ThreadingMixIn,WSGIServer):
    daemon_threads=True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path('studio-data'))
    p.add_argument('--host',default='127.0.0.1',choices=['127.0.0.1','localhost'])
    p.add_argument('--port',type=int,default=8000)
    p.add_argument('--cpus',type=int,default=4)
    p.add_argument('--memory-gb',type=int,default=8)
    p.add_argument('--concurrent-jobs',type=int,default=2)
    p.add_argument('--no-worker',action='store_true')
    p.add_argument('--open-browser',action='store_true',help='Open the local workspace automatically')
    args=p.parse_args()
    origin=f'http://{args.host}:{args.port}'
    settings=Settings(args.data,origin,True,args.concurrent_jobs,args.cpus,args.memory_gb)
    application=Application(settings)
    token=application.auth.setup_token()
    print(f'SQE Studio: {origin}',flush=True)
    if token: print(f'One-time administrator setup: {origin}/#setup={token}',flush=True)
    if args.open_browser:
        import threading,webbrowser
        threading.Timer(1.5,lambda: webbrowser.open(f'{origin}/#setup={token}' if token else origin)).start()
    worker=None
    if not args.no_worker:
        env=os.environ.copy()
        env.update(SQE_DATA=str(settings.root),SQE_ORIGIN=origin,SQE_DEVELOPMENT='1',
                   SQE_TOTAL_CPUS=str(args.cpus),SQE_MEMORY_GB=str(args.memory_gb),SQE_MAX_JOBS=str(args.concurrent_jobs))
        worker=subprocess.Popen([sys.executable,'-m','sqw.studio.jobs'],env=env)
    try:
        with make_server(args.host,args.port,application,server_class=ThreadedServer) as server:
            server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if worker:
            worker.terminate()
            try: worker.wait(timeout=15)
            except subprocess.TimeoutExpired: worker.kill()


if __name__=='__main__': main()
