"""Benchmark profiles, REST validation and bounded diagnostic log preservation."""
from pathlib import Path
from unittest.mock import patch
import io
import json
import tempfile
import unittest

from sqw import diagnostics
from sqw.studio.server import Application
from sqw.studio.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkProfileTests(unittest.TestCase):
    def test_profile_limits_default_to_small_quick_check(self):
        self.assertEqual([x[0] for x in diagnostics.profile_cases('quick')],
                         ['mesh_smoke','solver_sanity'])
        self.assertEqual([x[0] for x in diagnostics.profile_cases('standard')],
                         ['geometry','mesh','electrostatic','capacitance'])
        self.assertIn('driven', [x[0] for x in diagnostics.profile_cases('full')])
        with self.assertRaises(ValueError):
            diagnostics.profile_cases('arbitrary')

    def test_quick_skips_unavailable_tools_without_fake_solver_success(self):
        with patch('sqw.diagnostics.versions', return_value={'gmsh':None}), \
             patch('sqw.palace_bridge.readiness', return_value={'installed':False}):
            checks, logs = diagnostics.scientific_workflow(ROOT, profile='quick')
        self.assertEqual([x['status'] for x in checks], ['SKIP','SKIP'])
        self.assertNotIn('SQE_PROBE_RESULT', logs)

    def test_result_tails_survive_subprocess_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch('sqw.diagnostics._read_tail') as read:
                read.return_value = 'SQE_PROBE_FAILURE=RuntimeError: finite element solver stopped\n'
                rc, timed, duration, log, parsed = diagnostics._isolated_case(ROOT, base, 'solver_sanity', 15)
            self.assertIsInstance(log,str)
            self.assertGreaterEqual(duration,0)
            self.assertIsNone(parsed)

    def test_diagnostic_worker_rejects_unknown_profile(self):
        from sqw.studio.diagnostic_control import DiagnosticControl
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = DiagnosticControl(Path(tmp), ROOT)
            from sqw.studio.auth import Problem
            with self.assertRaises(Problem):
                diagnostic.start(scientific=True, scientific_profile='evil')

    def test_web_assets_expose_scientific_profile(self):
        javascript=(ROOT/'src/sqw/studio/static/control.js').read_text(encoding='utf-8')
        self.assertIn('scientific_profile:state.profile', javascript)
        for p in ('quick', 'standard', 'full'):
            self.assertIn('value="'+p+'"', javascript)

    def test_linux_runner_reports_solver_resources_if_available(self):
        bash=(ROOT/'scripts/palace-wsl-run.sh').read_text(encoding='utf-8')
        self.assertIn('SQE_RESOURCE_ACCOUNTING=GNU_TIME',bash)
        self.assertIn('/usr/bin/time -v',bash)

    def test_no_arbitrary_files_in_bundle(self):
        self.assertEqual(len(diagnostics.SAFE_FILE_NAMES),6)
        self.assertNotIn('studio-data', ' '.join(diagnostics.SAFE_FILE_NAMES))

if __name__ == '__main__': unittest.main()

class FailureEvidenceTests(unittest.TestCase):
    def test_failed_solver_log_is_kept_after_stage(self):
        # A fabricated failing subprocess, not a fabricated scientific result.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'src').mkdir()
            (root/'scripts'/'sqe_scientific_probe.py').write_text(
                'import argparse,pathlib,sys\n'
                'p=argparse.ArgumentParser();p.add_argument("--case");p.add_argument("--profile");'
                'p.add_argument("--deadline");p.add_argument("--workspace");a=p.parse_args()\n'
                '(pathlib.Path(a.workspace)/"electrostatic.log").write_text("FEM solver allocation failed: debug-token\\n")\n'
                'print("SQE_PROBE_FAILURE=RuntimeError: solver failed",flush=True)\n'
                'sys.exit(1)\n',encoding='utf-8')
            workspace=root/'scratch';workspace.mkdir()
            rc,timed,duration,log,parsed=diagnostics._isolated_case(root,workspace,'electrostatic',12)
            self.assertEqual(rc,1)
            self.assertFalse(timed)
            self.assertIn('FEM solver allocation failed',log)
            self.assertIn('SQE_PROBE_FAILURE',log)
            self.assertIsNone(parsed)

    def test_automatic_report_uses_new_release_and_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=ROOT
            path, checks=diagnostics.bundle(root,Path(tmp),skip_tests=True,scientific=True,scientific_profile='quick')
            import zipfile
            with zipfile.ZipFile(path) as z:
                metadata=json.loads(z.read('environment.json'))
                assert metadata['scientific_profile']=='quick'
                self.assertEqual(z.namelist()[-1], 'SHA256SUMS.txt')
                self.assertNotIn('studio-data', str(z.namelist()))
                self.assertIn('workflow.solver_sanity',[x['id'] for x in json.loads(z.read('checks.json'))])


class ScientificApiTests(unittest.TestCase):
    def test_scientific_profile_rejected_when_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Application(Settings(Path(tmp)))
            token=app.auth.setup_token()
            app.auth.setup(token,'sample@example.org','Sample','long and safe regression test password')
            session,csrf,_=app.auth.login('sample@example.org','long and safe regression test password','local')
            payload=json.dumps({'scientific':True,'scientific_profile':'../../bad'}).encode()
            request={'REQUEST_METHOD':'POST','PATH_INFO':'/api/system/diagnostics',
                     'CONTENT_LENGTH':str(len(payload)), 'CONTENT_TYPE':'application/json',
                     'HTTP_COOKIE':'sqe_session='+session, 'HTTP_X_CSRF_TOKEN':csrf,
                     'HTTP_HOST':'127.0.0.1:8000','wsgi.input':io.BytesIO(payload)}
            got={}
            def response(status,headers):got['status']=status
            result=b''.join(app(request,response))
            self.assertTrue(got['status'].startswith('400'),result)
            self.assertNotIn(b'Traceback',result)
