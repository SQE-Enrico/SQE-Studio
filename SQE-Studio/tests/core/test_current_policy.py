"""Current release integrity without a historical permit chain."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sqe_studio import governance as gate

ROOT=Path(__file__).resolve().parents[2]


class CurrentPolicy(unittest.TestCase):
    def clone(self):
        temp=tempfile.TemporaryDirectory(prefix='sqe-current-policy-')
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'source'
        shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('__pycache__','*.pyc',
            '*.egg-info','wheels','build','dist','qualification-reports'))
        return root

    def test_current_development_is_not_physical_approval(self):
        result=gate.check(ROOT)
        self.assertEqual(result['code_status'],'CURRENT_MODULAR_SOURCE_VERIFIED')
        self.assertEqual(result['science_status'],'NOT_QUALIFIED')
        self.assertEqual(result['independent_review'],'MISSING')

    def test_source_mutation_invalidates_current_fingerprint(self):
        root=self.clone();path=root/'src/sqe_studio/http_api/extraction.py'
        path.write_bytes(path.read_bytes()+b'\n# changed after review\n')
        with self.assertRaises(gate.ScienceFirstGateError):gate.check(root)

    def test_untracked_solver_cannot_enter_a_signed_tree(self):
        root=self.clone();(root/'src/unapproved_solver.py').write_text('unexpected=True\n')
        with self.assertRaises(gate.ScienceFirstGateError):gate.check(root)

    def test_fabricated_reviewer_or_scientific_release_is_rejected(self):
        root=self.clone();path=root/gate.POLICY;original=path.read_bytes()
        for field,value in [('independent_scientific_reviewer','invented'),('scientific_release','GO')]:
            data=json.loads(original);data[field]=value;path.write_text(json.dumps(data))
            with self.subTest(field=field),self.assertRaises(gate.ScienceFirstGateError):gate.check(root)

    def test_refreshing_software_fingerprint_cannot_change_numerical_core(self):
        root=self.clone();path=root/'src/sqe_studio/adapters/scqubits_adapter.py'
        path.write_bytes(path.read_bytes()+b'\n# numerical source mutation\n')
        policy=root/gate.POLICY;data=json.loads(policy.read_text())
        data['protected_fingerprint']=gate.fingerprint(root);policy.write_text(json.dumps(data))
        with self.assertRaisesRegex(gate.ScienceFirstGateError,'numerical/core'):gate.check(root)

    def test_core_pin_map_cannot_be_replaced_with_self_asserted_hashes(self):
        root=self.clone();path=root/gate.CORE;path.write_text('{}')
        with self.assertRaisesRegex(gate.ScienceFirstGateError,'baseline'):gate.check(root)

    def test_historical_sources_are_not_required(self):
        self.assertFalse((ROOT/'agent_cycle').exists())
        self.assertFalse((ROOT/'docs/history').exists())
        self.assertFalse(any(ROOT.rglob('*rollback.zip')))
        gate.check(ROOT)

    def test_cli_fails_closed_for_changed_source(self):
        root=self.clone();path=root/'src/sqe_studio/http_api/handler.py'
        path.write_bytes(path.read_bytes()+b'\n# changed\n')
        result=subprocess.run([sys.executable,str(ROOT/'tools/science_first_gate.py'),str(root)],
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['status'],'NO_GO')

    def test_source_and_ui_modules_remain_small_at_the_moved_boundary(self):
        self.assertLess(len((ROOT/'src/sqe_studio/server.py').read_text(encoding='utf-8').splitlines()),80)
        for path in (ROOT/'src/sqe_studio/http_api').glob('*.py'):
            self.assertLess(len(path.read_text(encoding='utf-8').splitlines()),250,path.name)
        for path in (ROOT/'src/sqe_studio/web/modules').glob('*.js'):
            self.assertLess(len(path.read_text(encoding='utf-8').splitlines()),250,path.name)

    def test_module_size_check_works_with_a_windows_cp1252_default(self):
        original=Path.read_text
        def windows_default(path,encoding=None,errors=None):
            return original(path,encoding=encoding or 'cp1252',errors=errors)
        with patch.object(Path,'read_text',new=windows_default):
            self.test_source_and_ui_modules_remain_small_at_the_moved_boundary()


if __name__=='__main__':unittest.main()
