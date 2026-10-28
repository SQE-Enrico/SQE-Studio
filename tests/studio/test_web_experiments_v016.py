"""Browser-facing multi-engine workflows, archives, permissions and ZIP safety."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile

from sqw.studio.server import Application
from sqw.studio.settings import Settings
from sqw.studio.support_bundles import create_support_bundle

PASSWORD = 'correct horse battery staple'


class WebExperimentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(Settings(Path(self.temp.name)))
        self.app.auth.setup(self.app.auth.setup_token(), 'admin@example.org', 'Admin', PASSWORD)
        self.token, self.csrf, self.admin = self.app.auth.login('admin@example.org', PASSWORD, 'local')

    def tearDown(self):
        if self.app.ecosystem.worker:
            self.app.ecosystem.worker.join(timeout=12)
        self.temp.cleanup()

    def call(self, path, method='GET', data=None, token=None, csrf=None, content_type='application/json'):
        raw = (data if isinstance(data, bytes) else json.dumps(data or {}).encode('utf-8'))
        target, _, query = path.partition('?')
        env = {'REQUEST_METHOD': method, 'PATH_INFO': target, 'QUERY_STRING': query,
               'HTTP_HOST': '127.0.0.1:8000', 'CONTENT_TYPE': content_type,
               'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw)}
        if token:
            env['HTTP_COOKIE'] = 'sqe_session=' + token
        if csrf:
            env['HTTP_X_CSRF_TOKEN'] = csrf
        response = {}
        def start(status, headers):
            response['code'] = int(status.split()[0])
            response['headers'] = dict(headers)
        output = self.app(env, start)
        response['body'] = b''.join(output)
        if hasattr(output, 'close'):
            output.close()
        if response['headers'].get('Content-Type', '').startswith('application/json'):
            response['json'] = json.loads(response['body'])
        return response

    def project_zip(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as zipfile_obj:
            for name, payload in entries.items():
                zipfile_obj.writestr(name, payload)
        return stream.getvalue()

    def test_catalog_preview_and_english_ui_pages(self):
        result = self.call('/api/system/ecosystem', token=self.token)
        self.assertEqual(result['code'], 200)
        self.assertIn('native-1q', [x['id'] for x in result['json']['projects']])
        plan = self.call('/api/system/ecosystem/preview?project=native-1q', token=self.token)
        self.assertEqual(plan['code'], 200)
        self.assertEqual(len(plan['json']['plan']['steps']), 3)
        for file in ('experiments.html', 'experiments.js', 'experiments.css'):
            self.assertEqual(self.call('/' + file)['code'], 200)
        html = self.call('/experiments.html')['body'].decode()
        self.assertIn('lang="en"', html)
        self.assertIn('Research Experiments', html)
        self.assertIn('RELEASE 0.16.0', html)

    def test_run_and_one_click_archive_with_valid_sha256(self):
        result = self.call('/api/system/ecosystem/runs', 'POST',
                           {'project': 'native-1q'}, self.token, self.csrf)
        self.assertEqual(result['code'], 200, result.get('json'))
        run_id = result['json']['id']
        for _ in range(150):
            detail = self.call('/api/system/ecosystem/runs/' + run_id, token=self.token)
            if detail['json']['state'] not in ('queued', 'running'):
                break
            time.sleep(.1)
        self.assertEqual(detail['json']['state'], 'completed', detail['json'].get('log_tail'))
        self.assertEqual(len(detail['json']['result']['steps']), 3)
        archive = self.call('/api/system/ecosystem/runs/' + run_id + '/bundle', token=self.token)
        self.assertEqual(archive['code'], 200)
        self.assertTrue(archive['body'].startswith(b'PK'))
        with zipfile.ZipFile(io.BytesIO(archive['body'])) as z:
            manifest = json.loads(z.read('manifest.json'))
            self.assertIn('artifacts/output/run.json', z.namelist())
            self.assertIn('artifacts/worker.log', z.namelist())
            self.assertIn('artifacts/output/inputs/modes.json', z.namelist())
            self.assertIn('artifacts/output/steps/modes/result.json', z.namelist())
            self.assertEqual(manifest['category'], 'ecosystem-experiment')
            for filename, checksum in manifest['checksums_sha256'].items():
                self.assertEqual(hashlib.sha256(z.read('artifacts/' + filename)).hexdigest(), checksum)
        self.assertEqual(self.call('/api/system/ecosystem/runs/' + run_id + '/bundle')['code'], 401)
        self.assertEqual(self.call('/api/system/ecosystem/runs/' + run_id + '/bundle/extra',
                                   token=self.token)['code'], 404)
        delete = self.call('/api/system/ecosystem/runs/' + run_id, 'DELETE', {}, self.token, self.csrf)
        self.assertEqual(delete['json'], {'deleted': True})

    def test_failed_workflow_support_archive_is_available(self):
        spec = {'schema_version': 1, 'name': 'Intentional failure fixture', 'steps': [
            {'id': 'invalid-model', 'engine': 'quantumlab', 'operation': 'modes',
             'source': 'design.json'}]}
        payload = self.project_zip({'workflow.json': json.dumps(spec), 'design.json': '{}'})
        imported = self.call('/api/system/ecosystem/import', 'POST', payload,
                             self.token, self.csrf, content_type='application/zip')
        self.assertEqual(imported['code'], 200)
        started = self.call('/api/system/ecosystem/runs', 'POST',
                            {'project': imported['json']['id']}, self.token, self.csrf)
        self.assertEqual(started['code'], 200)
        run_id = started['json']['id']
        for _ in range(120):
            detail = self.call('/api/system/ecosystem/runs/' + run_id, token=self.token)
            if detail['json']['state'] not in ('queued', 'running'):
                break
            time.sleep(.1)
        self.assertEqual(detail['json']['state'], 'failed')
        archive = self.call('/api/system/ecosystem/runs/' + run_id + '/bundle', token=self.token)
        self.assertEqual(archive['code'], 200)
        with zipfile.ZipFile(io.BytesIO(archive['body'])) as z:
            self.assertIn('artifacts/worker.log', z.namelist())
            self.assertIn('artifacts/output/run.json', z.namelist())
            self.assertEqual(json.loads(z.read('artifacts/output/run.json'))['state'], 'FAILED')

    def test_permissions_csrf_remote_and_opt_in(self):
        self.assertEqual(self.call('/api/system/ecosystem')['code'], 401)
        self.assertEqual(self.call('/api/system/ecosystem/runs', 'POST',
                                   {'project': 'native-1q'}, self.token)['code'], 403)
        self.assertEqual(self.call('/api/system/ecosystem/runs', 'POST',
                                   {'project': 'native-1q', 'allow_project_code': True},
                                   self.token, self.csrf)['code'], 403)
        invited = self.app.auth.invite(self.admin, 'reader@example.org', 'Reader', 'researcher')
        self.app.auth.activate(invited['activation_url'].split('=')[-1], PASSWORD)
        token, csrf, _ = self.app.auth.login('reader@example.org', PASSWORD, 'local')
        self.assertEqual(self.call('/api/system/ecosystem', token=token)['code'], 403)
        self.assertEqual(self.call('/api/system/ecosystem/runs', 'POST',
                                   {'project': 'native-1q'}, token, csrf)['code'], 403)
        self.app.settings.development = False
        self.assertEqual(self.call('/api/system/ecosystem', token=self.token)['code'], 403)

    def test_safe_browser_project_import(self):
        spec = {'schema_version': 1, 'name': 'Custom browser project', 'steps': [
            {'id': 'modes', 'engine': 'quantumlab', 'operation': 'modes', 'source': 'design.json'}]}
        # A template-provided source gives a valid test fixture.
        source = self.app.ecosystem.examples / 'native-1q' / 'design.json'
        payload = self.project_zip({'workflow.json': json.dumps(spec),
                                    'design.json': source.read_bytes()})
        imported = self.call('/api/system/ecosystem/import', 'POST', payload,
                             self.token, self.csrf, content_type='application/zip')
        self.assertEqual(imported['code'], 200, imported.get('json'))
        imported_id = imported['json']['id']
        self.assertEqual(self.call('/api/system/ecosystem/preview?project=' + imported_id,
                                   token=self.token)['code'], 200)
        for forbidden in ('../secret.json', '/absolute.json', 'app.py', 'a\\bad.json'):
            bad = self.project_zip({'workflow.json': json.dumps(spec), 'design.json': source.read_bytes(),
                                    forbidden: b'1'})
            self.assertEqual(self.call('/api/system/ecosystem/import', 'POST', bad,
                                       self.token, self.csrf,
                                       content_type='application/zip')['code'], 400, forbidden)
        self.assertEqual(self.call('/api/system/ecosystem/import', 'POST', b'notzip',
                                   self.token, self.csrf, content_type='application/zip')['code'], 400)

    def test_project_job_bundle_access_and_size_bounding(self):
        project_id = self.app.projects.create(self.admin, 'Test research project')
        revision = self.app.projects.revise(self.admin, project_id, 'Before test')
        job_id = self.app.jobs.enqueue(self.admin, project_id, revision, 'report')
        folder = self.app.store.root / 'jobs' / job_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'worker.log').write_text('First solver error\n', encoding='utf-8')
        (folder / 'private.env').write_text('TOKEN=secret\n', encoding='utf-8')
        (folder / 'huge.log').write_bytes(b'x' * (8 * 1024 * 1024 + 1))
        response = self.call(f'/api/projects/{project_id}/jobs/{job_id}/bundle',token=self.token)
        self.assertEqual(response['code'], 200)
        with zipfile.ZipFile(io.BytesIO(response['body'])) as z:
            self.assertIn('artifacts/worker.log', z.namelist())
            self.assertNotIn('artifacts/private.env', z.namelist())
            self.assertNotIn('artifacts/huge.log', z.namelist())
            manifest=json.loads(z.read('manifest.json'))
            self.assertGreaterEqual(len(manifest['excluded']),2)
        self.assertEqual(self.call(f'/api/projects/{project_id}/jobs/{job_id}/bundle')['code'],401)
        self.assertEqual(self.call(f'/api/projects/{project_id}/jobs/{job_id}/bundle/notvalid',token=self.token)['code'],404)


if __name__ == '__main__':
    unittest.main()
