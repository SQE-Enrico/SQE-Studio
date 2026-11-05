"""Evidence summaries must keep missing, blocked and changed-source runs visible."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('sqe_ci_summary', Path(__file__).with_name('ci_summary.py'))
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class JobSummary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sqe-ci-summary-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'qualification-reports').mkdir()
        self.env = {'GITHUB_REPOSITORY': 'SQE-Enrico/SQE-Studio', 'GITHUB_SHA': 'a' * 40,
                    'GITHUB_RUN_ID': '42', 'SQE_CI_OS': 'windows-latest', 'SQE_CI_PYTHON': '3.11'}

    def write(self, code=0, stable=True):
        data = {'schema': 'sqe.local-development-check.v1', 'exit_code': code,
                'source_stable': stable, 'profile': 'software',
                'automatic_test_report': 'SQE-RC14_12-report-0001.zip',
                'steps': [{'id': 'ui', 'status': 'PASS', 'duration_s': .1}]}
        path = self.root / 'qualification-reports/local-latest.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def test_missing_and_malformed_results_are_incomplete(self):
        self.assertIn('INCOMPLETE', summary.render(self.root, self.env))
        path = self.write()
        path.write_text('not JSON', encoding='utf-8')
        self.assertIn('INCOMPLETE', summary.render(self.root, self.env))

    def test_blocked_and_changed_source_are_not_pass(self):
        for code, stable in ((2, True), (0, False)):
            self.write(code, stable)
            result = summary.render(self.root, self.env)
            self.assertIn('Result: BLOCKED / INCOMPLETE', result)
            self.assertNotIn('Result: PASS', result)

    def test_failed_test_is_visible_and_links_to_its_commit(self):
        self.write(1)
        result = summary.render(self.root, self.env)
        self.assertIn('Result: FAIL', result)
        self.assertIn('/commit/' + 'a' * 40, result)
        self.assertIn('/actions/runs/42#artifacts', result)

    def test_numbered_report_shows_domains_and_excluded_native_families(self):
        self.write()
        details = {'tasks': [
            {'id': 'regression', 'status': 'PASS', 'substeps': [{'log':
                'GROUP fields exit=0 elapsed_s=1.25 passed=9 skipped=2\r\n9 passed, 2 skipped\r\n'}]},
            {'id': 'em', 'status': 'SKIPPED_BY_PLAN'}]}
        path = self.root / 'qualification-reports/SQE-RC14_12-report-0001.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('QUALIFICATION.json', json.dumps(details))
        result = summary.render(self.root, self.env)
        self.assertIn('| fields | 0 | 9 | 2 | 1.25 |', result)
        self.assertIn('| em | SKIPPED_BY_PLAN |', result)
        self.assertIn('Scientific qualification: NOT_ESTABLISHED', result)

    def test_report_path_traversal_and_markdown_injection_are_rejected(self):
        path = self.write()
        data = json.loads(path.read_text(encoding='utf-8'))
        data['automatic_test_report'] = '../../private.zip'
        data['steps'][0]['id'] = '<script>\n| forged'
        path.write_text(json.dumps(data), encoding='utf-8')
        result = summary.render(self.root, self.env)
        self.assertIn('Detailed numbered report unavailable', result)
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt; \\| forged', result)


if __name__ == '__main__':
    unittest.main()
