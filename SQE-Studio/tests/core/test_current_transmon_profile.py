"""The real native profile is explicit and cannot silently select an EM fixture."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqe_studio.testing.catalog import PROFILES, resolve_selection
from sqe_studio.testing.native_transmon import run_workflow
from sqe_studio.testing.palace_reference import verify_inputs

ROOT = Path(__file__).resolve().parents[2]


class NativeTransmonProfile(unittest.TestCase):
    def test_real_chain_is_explicit_and_separate_from_fixture_and_recommended(self):
        chosen = resolve_selection(PROFILES['single_transmon'])['resolved']
        self.assertEqual(chosen, ['integrity', 'targeted', 'http', 'transmon_chain'])
        self.assertNotIn('transmon_chain', resolve_selection(PROFILES['recommended'])['resolved'])
        self.assertNotIn('extraction', chosen)
        self.assertIn('extraction', PROFILES['extraction'])

    def test_missing_tools_are_blocked_without_a_fixture_or_native_launch(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('sqe_studio.testing.native_transmon.importlib.util.find_spec', return_value=None):
            result = run_workflow(ROOT, Path(folder))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['native_palace_execution'], 'NOT_RUN')
        self.assertEqual(result['native_quantum_execution'], 'NOT_RUN')
        self.assertEqual(result['em_source_kind'], 'NO_FIXTURE_FALLBACK')

    def test_published_benchmark_inputs_and_predeclared_tolerance_are_pinned(self):
        source = ROOT / 'tests/fixtures/palace_spheres_0_16'
        reference = verify_inputs(source)
        self.assertEqual(reference['entry_relative_tolerance'], .05)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'mesh').mkdir()
            for name in ('spheres.json', 'mesh/spheres.msh'):
                (root/name).write_bytes((source/name).read_bytes())
            changed = deepcopy(reference)
            changed['entry_relative_tolerance'] = .5
            (root/'REFERENCE.json').write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'PREDECLARED_TOLERANCE'):
                verify_inputs(root)
            (root/'REFERENCE.json').write_text(json.dumps(reference), encoding='utf-8')
            (root/'spheres.json').write_bytes(b'changed input')
            with self.assertRaisesRegex(ValueError, 'INPUT_CHANGED'):
                verify_inputs(root)


if __name__ == '__main__':
    unittest.main()
