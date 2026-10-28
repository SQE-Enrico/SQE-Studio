"""Web control-center permissions, lifecycle, persistence, and privacy boundaries."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from sqw.studio.server import Application
from sqw.studio.settings import Settings
from sqw.studio.auth import Problem

PASSWORD = 'correct horse battery staple'


class DiagnosticWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(Settings(Path(self.temp.name)))
        self.app.auth.setup(self.app.auth.setup_token(),'owner@example.org','Owner', PASSWORD)
        self.token, self.csrf, self.user = self.app.auth.login('owner@example.org',PASSWORD,'local')

    def tearDown(self):
        if self.app.diagnostics.worker:
            self.app.diagnostics.worker.join(timeout=5)
        self.temp.cleanup()

    def call(self, path, method='GET', payload=None, token=None, csrf=None):
        raw = json.dumps(payload or {}).encode()
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'CONTENT_LENGTH': str(len(raw)),
               'CONTENT_TYPE': 'application/json', 'wsgi.input': io.BytesIO(raw),
               'HTTP_HOST':'127.0.0.1:8000'}
        if token: env['HTTP_COOKIE']='sqe_session='+token
        if csrf: env['HTTP_X_CSRF_TOKEN']=csrf
        out = {}
        def start(status, headers): out.update(code=int(status.split()[0]), headers=dict(headers))
        response=self.app(env,start)
        out['body']=b''.join(response)
        if hasattr(response,'close'): response.close()
        if out['headers']['Content-Type'].startswith('application/json'):
            out['json']=json.loads(out['body'])
        return out

    @staticmethod
    def fake_bundle(root, folder, *, extended=False, skip_tests=False):
        path=folder/'SQE-DIAGNOSTICS-v0.10.0-20261028-120000Z.zip'
        checks=[{'id':'app.smoke','status':'PASS','code':'OK','detail':'Validated', 'next_action':''}]
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('SUMMARY.txt','Overall: PASS\n')
            z.writestr('checks.json',json.dumps(checks))
            z.writestr('environment.json',json.dumps({'platform':'Windows','python_version':'3.11'}))
        return path,checks

    def test_admin_auth_csrf_and_immutable_download(self):
        url='/api/system/diagnostics'
        self.assertEqual(self.call(url)['code'],401)
        self.assertEqual(self.call(url,'POST',{},self.token)['code'],403)
        self.assertEqual(self.call(url,'POST',{'extended':'yes'},self.token,self.csrf)['code'],400)
        self.assertEqual(self.call('/control.html')['code'],200)
        self.assertEqual(self.call('/control.js')['code'],200)
        self.assertEqual(self.call('/api/system/diagnostics/nope',token=self.token)['code'],404)
        with patch('sqw.studio.diagnostic_control.bundle',side_effect=self.fake_bundle):
            created=self.call(url,'POST',{'extended':True},self.token,self.csrf)
            self.assertEqual(created['code'],200)
            run_id=created['json']['id']
            for _ in range(120):
                report=self.call(url+'/'+run_id,token=self.token)
                if report['json']['state']=='completed': break
                time.sleep(.02)
            self.assertEqual(report['json']['summary'],'PASS')
            self.assertEqual(report['json']['checks'][0]['code'],'OK')
            out=self.call(url+'/'+run_id+'/bundle',token=self.token)
            self.assertEqual(out['code'],200)
            self.assertTrue(out['body'].startswith(b'PK'))
            self.assertIn('attachment;',out['headers']['Content-Disposition'])
            self.assertEqual(self.call(url+'/'+run_id+'/bundle')['code'],401)
            self.assertEqual(self.call(url+'/'+run_id+'/bundle/extra',token=self.token)['code'],404)
            self.assertEqual(self.call(url+'/'+run_id,'DELETE',token=self.token)['code'],403)
            self.assertEqual(self.call(url+'/'+run_id,'DELETE',token=self.token,csrf=self.csrf)['json']['deleted'],True)
            self.assertEqual(self.call(url+'/'+run_id,token=self.token)['code'],404)

    def test_failed_diagnostic_still_has_downloadable_zip(self):
        with patch('sqw.studio.diagnostic_control.bundle', side_effect=RuntimeError('Tool execution stopped')):
            created = self.call('/api/system/diagnostics', 'POST', {}, self.token, self.csrf)
            run_id = created['json']['id']
            for _ in range(100):
                report = self.call('/api/system/diagnostics/' + run_id, token=self.token)
                if report['json']['state'] == 'failed':
                    break
                time.sleep(.02)
            self.assertEqual(report['json']['state'], 'failed')
            archive = self.call('/api/system/diagnostics/' + run_id + '/bundle', token=self.token)
            self.assertEqual(archive['code'], 200)
            with zipfile.ZipFile(io.BytesIO(archive['body'])) as z:
                self.assertIn('Tool execution stopped', z.read('SUMMARY.txt').decode())
                self.assertIn('checks.json', z.namelist())

    def test_full_regression_is_explicit_and_skip_is_incompatible(self):
        url = '/api/system/diagnostics'
        rejected = self.call(url, 'POST', {'full_regressions': True, 'skip_tests': True},
                             self.token, self.csrf)
        self.assertEqual(rejected['code'], 400)
        calls = []
        def make_report(root, folder, **kwargs):
            calls.append(kwargs)
            return self.fake_bundle(root, folder)
        with patch('sqw.studio.diagnostic_control.bundle', side_effect=make_report):
            created = self.call(url, 'POST', {'full_regressions': True}, self.token, self.csrf)
            self.assertEqual(created['code'], 200)
            for _ in range(100):
                status = self.call(url + '/' + created['json']['id'], token=self.token)
                if status['json']['state'] == 'completed':
                    break
                time.sleep(.02)
        self.assertTrue(calls)
        self.assertIs(calls[0]['full_regressions'], True)

    def test_nonadmin_cannot_access_or_start_tests(self):
        invited=self.app.auth.invite(self.user,'guest@example.org','Guest','researcher')
        self.app.auth.activate(invited['activation_url'].split('=')[-1],PASSWORD)
        token,csrf,_=self.app.auth.login('guest@example.org',PASSWORD,'local')
        for path in ('/api/system/diagnostics','/api/system/startup'):
            self.assertEqual(self.call(path,token=token)['code'],403)
        self.assertEqual(self.call('/api/system/diagnostics','POST',{},token,csrf)['code'],403)

    def test_remote_deployment_rejects_native_probes(self):
        self.app.settings.development=False
        self.assertEqual(self.call('/api/system/diagnostics',token=self.token)['code'],403)

    def test_restart_marks_abandoned_runs_interrupted(self):
        manager=self.app.diagnostics
        record=manager.storage/('a'*32)
        record.mkdir()
        (record/'status.json').write_text(json.dumps({'id':'a'*32,'state':'running'}))
        from sqw.studio.diagnostic_control import DiagnosticControl
        other=DiagnosticControl(self.app.store.root,Path(self.temp.name))
        try:
            self.assertEqual(other.detail('a'*32)['state'],'interrupted')
        finally:
            if other.worker: other.worker.join(timeout=5)
