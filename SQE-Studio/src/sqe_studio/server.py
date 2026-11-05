"""Stable HTTP entry point. Routes: http_api/; UI assets: web/."""
import argparse
from http.server import ThreadingHTTPServer
from .http_api.common import ApiError
from .http_api.handler import Handler
from .http_api.service import Service

def make_server(data,port=8000):
    http=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    http.daemon_threads=True
    try:http.app=Service(data)
    except BaseException:
        http.server_close()
        raise
    return http

def main():
    p=argparse.ArgumentParser(description='SQE Studio local-only product foundation')
    p.add_argument('--data',default='studio-data',help='Private local database/artifact path')
    p.add_argument('--port',type=int,default=8000)
    args=p.parse_args()
    if not 1024<=args.port<=65535:p.error('Port must be 1024..65535')
    server=make_server(args.data,args.port)
    if not server.app.store.has_account():
        print('FIRST-RUN SETUP TOKEN (local console only):',server.app.setup_file.read_text(encoding='ascii'),flush=True)
    print(f'SQE Studio running: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
