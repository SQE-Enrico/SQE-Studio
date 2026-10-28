"""Unified Web flow and safe, optional external engine installation controls."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from sqw.studio.dependencies import AUTOMATIC, DependencyManager
from sqw.studio.server import Application
from sqw.studio.settings import Settings

PASSWORD = 'correct horse battery staple'


class UnifiedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.app = Application(Settings(Path(self.data.name)))
        self.app.auth.setup(self.app.auth.setup_token(), 'admin@example.org', 'Administrator', PASSWORD)
        self.token, self.csrf, _ = self.app.auth.login('admin@example.org', PASSWORD, 'local')

    def tearDown(self):
        if self.app.dependencies.worker:
            self.app.dependencies.worker.join(3)
        self.data.cleanup()

    def call(self, route, method='GET', body=None, auth=True, csrf=True):
        payload = json.dumps(body or {}).encode()
        path, _, query = route.partition('?')
        env = {'PATH_INFO': path, 'QUERY_STRING': query, 'REQUEST_METHOD': method,
               'HTTP_HOST': '127.0.0.1:8000', 'CONTENT_TYPE': 'application/json',
               'CONTENT_LENGTH': str(len(payload)), 'wsgi.input': io.BytesIO(payload)}
        if auth:
            env['HTTP_COOKIE'] = 'sqe_session=' + self.token
        if csrf:
            env['HTTP_X_CSRF_TOKEN'] = self.csrf
        res = {}
        def start(code, headers):
            res['code'] = int(code.split()[0]); res['headers'] = dict(headers)
        returned = self.app(env, start)
        try:
            res['body'] = b''.join(returned)
        finally:
            if hasattr(returned, 'close'):
                returned.close()
        if res['headers'].get('Content-Type', '').startswith('application/json'):
            res['json'] = json.loads(res['body'])
        return res

    def test_primary_ui_is_single_english_pipeline_and_legacy_editor_exists(self):
        root = self.call('/')
        self.assertEqual(root['code'], 200)
        html = root['body'].decode()
        self.assertIn('lang="en"', html)
        self.assertIn('/workspace.js', html)
        self.assertIn('Research Workspace', html)
        js = self.call('/workspace.js')
        self.assertEqual(js['code'], 200)
        for label in ('Project', 'Setup', 'Run', 'Results', 'Support ZIP'):
            self.assertIn(label, js['body'].decode())
        self.assertEqual(self.call('/workspace.css')['code'], 200)
        self.assertIn('/app.js', self.call('/editor.html')['body'].decode())
        self.assertEqual(self.call('/workspace.html')['code'], 404)

    def test_engine_setup_is_admin_only_cors_and_csrf_protected(self):
        self.assertEqual(self.call('/api/system/engines', auth=False)['code'], 401)
        self.assertEqual(self.call('/api/system/engines/install', 'POST', {'engines':['gmsh']}, csrf=False)['code'], 403)
        self.assertEqual(self.call('/api/system/engines/install', 'POST', {'engines':['bad-tool']})['code'], 400)
        self.assertEqual(self.call('/api/system/engines/install', 'POST', {'engines':['palace']})['code'], 400)
        self.assertEqual(self.call('/api/system/engines/install', 'POST', {'engines':['gmsh','gmsh']})['code'], 400)
        self.app.settings.development = False
        self.assertEqual(self.call('/api/system/engines')['code'], 403)

    def test_setup_archive_contains_diagnostic_manifest_and_checksum(self):
        with mock.patch.object(self.app.dependencies, '_install_one', return_value=(False, 'offline test environment')):
            launched = self.call('/api/system/engines/install', 'POST', {'engines':['scqubits']})
            self.assertEqual(launched['code'], 200)
            self.app.dependencies.worker.join(5)
        run_id = launched['json']['id']
        detail = self.call('/api/system/engines/runs/' + run_id)
        self.assertEqual(detail['json']['checks']['scqubits']['status'], 'WARN')
        self.assertEqual(detail['json']['state'], 'partial')
        self.assertTrue(detail['json']['bundle_ready'])
        archive = self.call('/api/system/engines/runs/' + run_id + '/bundle')
        self.assertEqual(archive['code'], 200)
        with zipfile.ZipFile(io.BytesIO(archive['body'])) as z:
            manifest = json.loads(z.read('manifest.json'))
            self.assertEqual(manifest['category'], 'engine-setup')
            self.assertIn('artifacts/status.json', z.namelist())
            self.assertIn('artifacts/install.log', z.namelist())
        self.assertEqual(self.call('/api/system/engines/runs/'+run_id+'/bundle',auth=False)['code'],401)

    def test_auto_setup_runs_only_once_and_does_not_start_in_application_constructor(self):
        manager = self.app.dependencies
        self.assertEqual(manager.list(), [])
        with mock.patch.object(manager, '_install_one', return_value=(False, 'test')), mock.patch.object(manager, 'readiness', return_value={}):
            self.assertTrue(manager.auto_once())
            manager.worker.join(10)
            self.assertFalse(manager.worker.is_alive())
        self.assertFalse(manager.auto_once())
        self.assertEqual(manager.list()[0]['engines'], list(AUTOMATIC))

    def test_no_shell_or_untrusted_installer_arguments(self):
        manager = self.app.dependencies
        with self.assertRaises(Exception):
            manager.start(['python -c "print(1)"'])
        with self.assertRaises(Exception):
            manager.start([])
        with self.assertRaises(Exception):
            manager.start('scqubits')


if __name__ == '__main__':
    unittest.main()
