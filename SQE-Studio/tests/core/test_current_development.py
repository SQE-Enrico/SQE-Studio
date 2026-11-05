"""Development automation must never turn incomplete checks into success."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqe_studio.testing.runner import result_exit_code

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sqe_development', ROOT / 'tools/dev.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


def report(status='PASS'):
    return {'selection': {'resolved': ['integrity', 'http']},
            'counts': {'PASS': 2 if status == 'PASS' else 1, 'FAIL': 0, 'BLOCKED': 0},
            'execution_counts': {},
            'tasks': [{'id': 'integrity', 'status': 'PASS'}, {'id': 'http', 'status': status},
                      {'id': 'em', 'status': 'SKIPPED_BY_PLAN'}]}


class DevelopmentExitCodes(unittest.TestCase):
    def test_only_selected_tasks_must_pass(self):
        self.assertEqual(result_exit_code(report()), 0)

    def test_blocked_timeout_cancelled_and_unknown_are_not_success(self):
        for status in ('BLOCKED', 'TIMEOUT', 'CANCELLED', 'SKIPPED_BY_PLAN', 'UNKNOWN'):
            with self.subTest(status=status):
                self.assertEqual(result_exit_code(report(status)), 2)

    def test_failure_has_priority_over_blocked(self):
        value = report('BLOCKED')
        value['tasks'][0]['status'] = 'FAIL'
        self.assertEqual(result_exit_code(value), 1)
        value = report()
        value['counts']['FAIL'] = 1  # Includes controller failures without task rows.
        self.assertEqual(result_exit_code(value), 1)

    def test_empty_missing_and_duplicate_evidence_never_passes(self):
        self.assertEqual(result_exit_code({}), 2)
        for rows in ([], [{'id': 'integrity', 'status': 'PASS'}],
                     [{'id': 'integrity', 'status': 'PASS'}] * 2):
            value = report()
            value['tasks'] = rows
            with self.subTest(rows=rows):
                self.assertEqual(result_exit_code(value), 2)


class SaveTriggeredChecks(unittest.TestCase):
    def test_existing_playwright_node_is_found_without_a_system_node(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'driver').mkdir()
            binary = package / 'driver' / ('node.exe' if os.name == 'nt' else 'node')
            binary.write_bytes(b'existing-package-binary')
            with patch.object(dev.shutil, 'which', return_value=None), \
                 patch.object(dev.importlib.util, 'find_spec', return_value=SimpleNamespace(origin=str(package / '__init__.py'))):
                self.assertEqual(dev.find_node(), str(binary))
                binary.unlink()
                self.assertIsNone(dev.find_node())

    def test_outputs_do_not_trigger_a_watch_loop_but_source_edits_do(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.py'
            source.write_text('before', encoding='utf-8')
            initial = dev.snapshot(root)
            for name in ('qualification-reports', '.venv', '__pycache__', 'build', 'dist'):
                folder = root / name
                folder.mkdir()
                (folder / 'output').write_text('ignored', encoding='utf-8')
            self.assertEqual(dev.snapshot(root), initial)
            source.write_text('after an editor save', encoding='utf-8')
            self.assertNotEqual(dev.snapshot(root), initial)
            source.unlink()
            self.assertNotEqual(dev.snapshot(root), initial)

    def test_save_bursts_wait_for_the_last_change_to_settle(self):
        states = iter([{'a': 1}, {'a': 2}, {'a': 2}, {'a': 2}])
        with patch.object(dev, 'snapshot', side_effect=lambda _root: next(states)), \
             patch.object(dev.time, 'sleep') as sleep, \
             patch.object(dev.time, 'monotonic', side_effect=[0, 1, 1, 2, 2, 3]):
            dev.wait_for_change({}, interval=1, settle=1)
        self.assertEqual(sleep.call_count, 3)

    def test_watcher_loads_edited_code_in_a_fresh_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / 'worker.py'
            output = root / 'observed.txt'
            def program(value):
                return ('from pathlib import Path\n'
                        f'with Path({str(output)!r}).open("a", encoding="utf-8") as out:\n'
                        f'    out.write({value!r} + "\\n")\n')
            worker.write_text(program('before edit'), encoding='utf-8')
            stop = threading.Event()
            def save_or_stop(*_args, **_kwargs):
                if not output.read_text(encoding='utf-8').count('\n') == 2:
                    worker.write_text(program('after edit'), encoding='utf-8')
                else:
                    stop.set()
            with patch.object(dev, 'ROOT', root), patch.object(dev, '__file__', str(worker)), \
                 patch.object(dev, 'wait_for_change', side_effect=save_or_stop), redirect_stdout(io.StringIO()):
                self.assertEqual(dev.watch('recommended', True, stop), 130)
            self.assertEqual(output.read_text(encoding='utf-8').splitlines(), ['before edit', 'after edit'])

    def test_stop_while_idle_does_not_start_another_cycle(self):
        stop = threading.Event()
        stop.set()
        with patch.object(dev.time, 'sleep'), patch.object(dev, 'snapshot') as scan:
            self.assertFalse(dev.wait_for_change({}, stop=stop))
        scan.assert_not_called()

    def run_local(self, root, *, result=None, node='node', check=True):
        result = report() if result is None else result
        with patch.object(dev, 'ROOT', root), \
             patch.object(dev, 'find_node', return_value=node), \
             patch.object(dev, '_run', return_value=(0, 'VM checks passed\n', .01)), \
             patch.object(dev, 'next_report_path', return_value=root / 'qualification-reports/SQE-RC14_12-report-0001.zip'), \
             patch.object(dev, 'run_selected', side_effect=result if callable(result) else lambda *_a, **_k: result), \
             redirect_stdout(io.StringIO()):
            return dev.run_cycle('recommended', check=check)

    def test_missing_node_is_blocked_even_if_automatic_test_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, _ = self.run_local(root, node=None)
            self.assertEqual(code, 2)
            latest = json.loads((root / 'qualification-reports/local-latest.json').read_text(encoding='utf-8'))
            self.assertEqual(latest['exit_code'], 2)
            self.assertEqual(latest['steps'][0]['reason'], 'NODE_NOT_INSTALLED')

    def test_edit_during_tests_marks_the_result_incomplete_and_preserves_watch_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'changed.py'
            source.write_text('before', encoding='utf-8')
            def during_run(*_args, **_kwargs):
                source.write_text('edited during test', encoding='utf-8')
                return report()
            code, baseline = self.run_local(root, result=during_run)
            self.assertEqual(code, 2)
            self.assertNotEqual(dev.snapshot(root), baseline)
            latest = json.loads((root / 'qualification-reports/local-latest.json').read_text(encoding='utf-8'))
            self.assertFalse(latest['source_stable'])

    def test_failed_refresh_stops_before_testing_and_replaces_stale_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(dev, 'ROOT', root), \
                 patch.object(dev, '_run', return_value=(1, 'numerical/core changed', .01)), \
                 patch.object(dev, 'run_selected') as selected, redirect_stdout(io.StringIO()):
                self.assertEqual(dev.run_cycle('recommended')[0], 1)
            selected.assert_not_called()
            latest = json.loads((root / 'qualification-reports/local-latest.json').read_text(encoding='utf-8'))
            self.assertEqual(latest['reason'], 'SOFTWARE_FINGERPRINT_REFRESH_FAILED')
            self.assertIsNone(latest['automatic_test_report'])


if __name__ == '__main__':
    unittest.main()
