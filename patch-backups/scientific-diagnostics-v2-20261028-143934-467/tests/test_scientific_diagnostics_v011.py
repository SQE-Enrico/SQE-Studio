"""Web-first workflow testing, timeout/skip handling and localization regression."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqw import diagnostics
from sqw.studio.server import Application
from sqw.studio.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


class ScientificWorkflowTests(unittest.TestCase):
    def test_geometry_case_uses_actual_export_contract(self):
        with tempfile.TemporaryDirectory() as dirname:
            rc, timeout, seconds, log, obj = diagnostics._isolated_case(ROOT, Path(dirname), 'geometry', 25)
            self.assertEqual(rc,0,log)
            self.assertFalse(timeout)
            self.assertTrue(obj['gds_generated'])
            self.assertEqual(obj['scientific_qualification'],False)
            self.assertTrue((Path(dirname)/'physical_HOLD.gds').is_file())
            self.assertIn('driven-1',obj['configs'])

    def test_prerequisites_skipped_not_faked(self):
        with patch('sqw.diagnostics.versions', return_value={'gmsh': None}), \
             patch('sqw.palace_bridge.readiness', return_value={'installed':False}):
            checks, log = diagnostics.scientific_workflow(ROOT)
        actual={entry['id']:entry['status'] for entry in checks}
        self.assertEqual(actual['workflow.geometry'],'PASS')
        self.assertEqual(actual['workflow.mesh'],'SKIP')
        self.assertEqual(actual['workflow.electrostatic'],'SKIP')
        self.assertEqual(actual['workflow.eigenmode'],'SKIP')
        self.assertEqual(actual['workflow.driven'],'SKIP')

    def test_web_localization_core_messages(self):
        page=(ROOT/'src/sqw/studio/static/quantumlab.js').read_text(encoding='utf-8')
        for token in ('Geometria verificata','Job FEM e file risultati',' in coda;',
                      'Nessun job FEM avviato', 'Accesso di sola lettura',
                      'Componenti qubit','Sostituire la topologia'):
            self.assertNotIn(token,page)
        self.assertIn('Geometry validated / backend status updated',page)
        self.assertIn('FEM jobs and result files',page)

    def test_queue_status_admin_only(self):
        with tempfile.TemporaryDirectory() as dirname:
            app=Application(Settings(Path(dirname)))
            token=app.auth.setup_token()
            app.auth.setup(token,'tester@example.org','Tester','correct horse battery staple')
            cookie,csrf,_=app.auth.login('tester@example.org','correct horse battery staple','local')
            def call(auth=False):
                env={'REQUEST_METHOD':'GET', 'PATH_INFO':'/api/system/queue',
                     'HTTP_HOST':'127.0.0.1:8000', 'wsgi.input':io.BytesIO(b'')}
                if auth:env['HTTP_COOKIE']='sqe_session='+cookie
                response={}
                def start(status,headers):response['code']=int(status.split()[0])
                body=b''.join(app(env,start))
                return response['code'],json.loads(body)
            self.assertEqual(call()[0],401)
            code,value=call(True)
            self.assertEqual(code,200)
            self.assertEqual(value['counts']['queued'],0)
            self.assertEqual(value['stale_running_heartbeats'],0)


if __name__=='__main__': unittest.main()
