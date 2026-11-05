"""Temporary authenticated local service for native workflow tests."""
import http.cookiejar
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request


class HttpSession:
    email = 'native-workflow@example.invalid'
    password = 'TemporaryNativeWorkflow123!'

    def __init__(self, folder):
        self.folder = Path(folder)
        self.csrf = ''

    def __enter__(self):
        from ..server import make_server
        self.server = make_server(self.folder / 'data', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.ProxyHandler({}))
        try:
            self.request('/api/setup', {'setup_token': self.server.app.setup_file.read_text(encoding='utf-8'),
                'email': self.email, 'password': self.password})
            self.csrf = self.request('/api/login', {'email': self.email, 'password': self.password})['csrf']
            project = self.request('/api/projects', {'name': 'Native single transmon reference',
                'family': 'transmon', 'template_id': 'single_transmon_native_v1'})
            self.pid = project['id']
            with self.server.app.store.conn() as db:
                self.owner = db.execute('SELECT id FROM accounts').fetchone()['id']
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if hasattr(self, 'owner') and hasattr(self, 'pid'):
            for run in self.server.app.store.runs(self.owner, self.pid):
                if run['state'] in ('queued', 'running'):
                    self.server.app.jobs.cancel(self.owner, self.pid, run['id'])
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def response(self, path, body=None, *, csrf=True):
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = self.csrf
        request = urllib.request.Request(self.base + path, headers=headers,
            data=json.dumps(body, allow_nan=False).encode() if body is not None else None)
        try:
            response = self.client.open(request, timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('NATIVE_WORKFLOW_HTTP_RESPONSE_LIMIT')
            return response.status, json.loads(raw)

    def request(self, path, body=None):
        status, data = self.response(path, body)
        if status >= 400:
            raise ValueError('HTTP_' + str(status) + ': ' + str(data)[:1000])
        return data

    def wait(self, run_id, deadline):
        while True:
            jobs = self.request(f'/api/projects/{self.pid}/runs')['runs']
            job = next(item for item in jobs if item['id'] == run_id)
            if job['state'] not in ('queued', 'running'):
                if job['state'] != 'completed':
                    info = self.server.app.store.run(self.owner, self.pid, run_id)
                    log = Path(info['path']) / 'engine.log'
                    detail = log.read_text(encoding='utf-8', errors='replace')[-12000:] if log.is_file() else ''
                    raise ValueError('NATIVE_JOB_' + job['state'].upper() + ': ' + detail)
                return self.request(f'/api/projects/{self.pid}/runs/{run_id}/result')
            if time.monotonic() >= deadline:
                self.server.app.jobs.cancel(self.owner, self.pid, run_id)
                raise TimeoutError('NATIVE_WORKFLOW_TIME_BUDGET')
            time.sleep(.5)
