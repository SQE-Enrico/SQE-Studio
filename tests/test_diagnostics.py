"""Privacy and packaging regressions; no Windows runtime is required."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from sqw import diagnostics as d


class DiagnosticBundleTests(unittest.TestCase):
    def test_scrub_windows_paths_linux_home_and_tokens(self):
        sample = ('File "C:\\Users\\Alice\\Code\\main.py" email alice@example.com '
                  'ip 192.168.0.42 password=secretVALUE '
                  'File "/home/alice/code/module.py", api_key:VALUE')
        result = d.scrub(sample)
        for private in ('Alice', 'alice@', '192.168.0.42', 'secretVALUE',
                        '/home/alice', 'api_key:VALUE'):
            self.assertNotIn(private, result)
        self.assertIn('[REDACTED]', result)

    def test_allowlisted_zip_has_no_user_project_or_credential_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            root.mkdir()
            (root / 'studio-data').mkdir()
            (root / 'studio-data' / 'project-secret.json').write_text('{"user_secret":"NeverCollectMe"}')
            (root / '.env').write_text('SUPER_SECRET=NotForBundle')
            fake = ([{'id':'x', 'status':'PASS','code':'OK','detail':'safe','next_action':''}])
            with patch.object(d, 'collect', return_value=({'platform':'Windows'}, fake, 'safe tests')):
                path, checks = d.bundle(root, root / 'diagnostics')
            self.assertEqual(len(checks),1)
            with ZipFile(path) as z:
                self.assertEqual(set(z.namelist()),set(d.SAFE_FILE_NAMES)|{'SHA256SUMS.txt'})
                contents = '\n'.join(z.read(n).decode('utf-8') for n in z.namelist())
                self.assertNotIn('NeverCollectMe', contents)
                self.assertNotIn('NotForBundle', contents)
                self.assertNotIn('project-secret.json', contents)
                self.assertEqual(json.loads(z.read('manifest.json'))['status'], 'PASS')
                for line in z.read('SHA256SUMS.txt').decode().splitlines():
                    digest, name = line.split('  ')
                    self.assertEqual(digest, hashlib.sha256(z.read(name)).hexdigest())

    def test_collect_read_only_standard_without_regression_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            env, checks, out = d.collect(Path(temp), skip_tests=True)
        self.assertEqual(env['schema'], d.SCHEMA)
        self.assertNotIn('username',json.dumps(env).lower())
        self.assertNotIn('computername',json.dumps(env).lower())
        self.assertTrue(any(x['id']=='app.regressions' and x['status']=='SKIP' for x in checks))
        self.assertEqual(out, '')

    def test_collect_records_regression_failure_without_project_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(d, 'run_regressions', return_value=(1, d.scrub('FAILED (failures=1)\nFile "/home/fred/private.py"'), False, 0)):
                env, checks, out = d.collect(Path(temp))
        self.assertTrue(any(x['id']=='app.regressions' and x['status']=='FAIL' for x in checks))
        self.assertNotIn('/home/fred', out)

    def test_subprocess_timeout_never_hangs(self):
        import sys
        with tempfile.TemporaryDirectory() as temp:
            rc, stdout, stderr, timeout = d.run([sys.executable,'-c','import time;time.sleep(10)'],root=Path(temp),timeout=1)
        self.assertIsNone(rc)
        self.assertTrue(timeout)
        self.assertEqual(stdout,'')

    def test_bootstrap_manifest_private_error_not_exported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / '.venv'
            state.mkdir()
            (state/'sqw-environment.json').write_text(json.dumps({
                'status':'failed', 'profile':'core',
                'python':'C:\\Users\\SecretUser\\python.exe',
                'error':'my-private-installer-token-DoNotExport',
            }))
            path, checks = d.bundle(root, root/'diagnostics', skip_tests=True)
            self.assertTrue(any(c['code']=='BOOTSTRAP_INCOMPLETE' for c in checks))
            with ZipFile(path) as z:
                report = ''.join(z.read(n).decode('utf-8') for n in z.namelist())
                self.assertNotIn('DoNotExport', report)
                self.assertNotIn('SecretUser', report)
                self.assertIn('BOOTSTRAP_INCOMPLETE', report)

    def test_failed_check_bundle_is_still_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            failed = [{'id':'app.regressions','status':'FAIL', 'code':'TESTS_FAILED',
                       'detail':'Tests: 1; exit: 1','next_action':'Review unit tests'}]
            with patch.object(d, 'collect', return_value=({'platform':'Windows'},failed,'FAILED')):
                path, _ = d.bundle(root,root/'diagnostics')
            with ZipFile(path) as z:
                self.assertEqual(json.loads(z.read('manifest.json'))['status'],'FAIL')

    def test_never_logs_full_runtime_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'SQE_PRIVATE_TEST_TOKEN':'VeryPrivateSecretNeverCopy'}):
                path, _ = d.bundle(Path(temp), Path(temp)/'out', skip_tests=True)
                with ZipFile(path) as z:
                    data=''.join(z.read(name).decode('utf-8') for name in z.namelist())
                    self.assertNotIn('VeryPrivateSecretNeverCopy',data)

if __name__ == '__main__':
    unittest.main()
