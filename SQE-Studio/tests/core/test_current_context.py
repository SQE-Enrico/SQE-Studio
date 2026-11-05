"""Bounded source navigation and task coverage for context-efficient changes."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sqe_studio.testing.catalog import BY_ID,PROFILES,load_plan,resolve_selection
from sqe_studio.testing.scopes import scope_files

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sqe_context_tool',ROOT/'tools/context.py')
context=importlib.util.module_from_spec(spec);spec.loader.exec_module(context)


class ContextNavigation(unittest.TestCase):
    def test_areas_resolve_current_source(self):
        mapping=json.loads((ROOT/'PROJECT_MAP.json').read_text())
        for area in mapping['areas']:
            data=context.area_context(ROOT,area)
            self.assertTrue(data['files'],area)
            for item in data['files']:self.assertTrue((ROOT/item['file']).is_file())

    def test_exact_http_symbol_is_small_and_contains_the_real_source(self):
        data=context.symbol_context(ROOT,'sqe_studio.http_api.extraction:extract',12)
        self.assertTrue(data['truncated'])
        self.assertIn('self.json_body()',data['source'])
        self.assertLessEqual(len(data['source'].splitlines()),12)

    def test_python_method_and_javascript_feature_symbols_can_be_selected(self):
        method=context.symbol_context(ROOT,'sqe_studio.http_api.handler:Handler.security',100)
        self.assertIn('Cross-origin',method['source'])
        ui=context.symbol_context(ROOT,'web/modules/extraction.js:conditionalExtractionValid',100)
        self.assertIn('NOT_ESTABLISHED',ui['source'])

    def test_unknown_symbols_and_paths_are_explicit_errors(self):
        for selector in ('../secrets:name','sqe_studio.server:missing','web/../../outside.js:test'):
            with self.subTest(selector=selector),self.assertRaises(ValueError):context.symbol_context(ROOT,selector)

    def test_context_output_is_bounded_without_silent_truncation(self):
        output=context.bounded_json({'source':'x'*20000})
        data=json.loads(output)
        self.assertEqual(data['status'],'CONTEXT_TOO_LARGE')
        self.assertLess(len(output),1000)

    def test_http_scope_tracks_moved_routes_and_all_shipped_modules(self):
        files={p.relative_to(ROOT).as_posix() for p in scope_files(ROOT,'http')}
        self.assertIn('src/sqe_studio/http_api/extraction.py',files)
        self.assertIn('src/sqe_studio/web/modules/extraction.js',files)
        self.assertIn('src/sqe_studio/web_assets.py',files)
        self.assertTrue(all(scope_files(ROOT,task) for task in BY_ID))

    def test_scope_order_is_portable_under_windows_path_comparison(self):
        with patch.object(Path,'__lt__',new=lambda left,right:str(left).casefold()<str(right).casefold()):
            files=scope_files(ROOT,'integrity')
        names=[path.relative_to(ROOT).as_posix() for path in files]
        self.assertIn('DEVELOPMENT_POLICY.json',names)
        self.assertEqual(names,sorted(names))

    def test_refactor_profile_is_software_only_and_native_profiles_remain_available(self):
        selected=resolve_selection(PROFILES['recommended'])['resolved']
        self.assertEqual(selected,['integrity','targeted','http'])
        self.assertIn('extraction',PROFILES['extraction'])
        self.assertEqual(load_plan(ROOT)[0]['wall_budget_s'],3600)

    def test_moved_suite_cannot_silently_pass_with_zero_collected_tests(self):
        from sqe_studio.testing.task_worker import execute
        import tempfile
        with tempfile.TemporaryDirectory(prefix='sqe-empty-suite-') as folder,\
             patch('sqe_studio.testing.task_worker._run',return_value=(0,'Ran 0 tests\n\nOK\n',.01)):
            result=execute('targeted',ROOT,Path(folder))
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(all(row.get('reason')=='EMPTY_OR_MISSING_UNITTEST_RESULT'
                            for row in result['substeps']))


if __name__=='__main__':unittest.main()
