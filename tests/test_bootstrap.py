import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/bootstrap.py'


class BootstrapTests(unittest.TestCase):
    def test_offline_plan_never_creates_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wheels = root/'wheels'
            wheels.mkdir()
            result = subprocess.run([sys.executable,str(SCRIPT),'--plan','--profile','full',
                                     '--offline','--wheelhouse',str(wheels),'--venv',str(root/'venv')],
                                    text=True,capture_output=True,check=True)
            plan = json.loads(result.stdout)
            self.assertEqual(plan['network'],'disabled')
            self.assertFalse((root/'venv').exists())
            for command in plan['commands']:
                self.assertIn('--no-index',command)
            self.assertTrue(any('-c' in command and str(ROOT/'requirements/core.lock') in command
                                for command in plan['commands']))

    def test_inherited_environment_is_rejected_before_any_install(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d)/'pyvenv.cfg'
            cfg.write_text('include-system-site-packages = true\n')
            result = subprocess.run([sys.executable,str(SCRIPT),'--venv',d],text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('inherits system packages',result.stderr)
            self.assertEqual(list(Path(d).iterdir()),[cfg])


if __name__ == '__main__':
    unittest.main()
