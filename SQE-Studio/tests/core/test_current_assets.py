"""Module assembly and invalid-package boundaries, no browser/native claim."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sqe_studio.web_assets import WEB_ROOT,javascript_bundle,javascript_sources,read_asset


class ModuleAssets(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='sqe-ui-modules-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'web';shutil.copytree(WEB_ROOT,self.root)

    def change_manifest(self,mutate):
        path=self.root/'modules.json';data=json.loads(path.read_text());mutate(data)
        path.write_text(json.dumps(data))

    def test_single_response_contains_ordered_core_and_feature_symbols(self):
        source=read_asset('app.js').decode('utf-8')
        self.assertLess(source.index('let csrf='),source.index('function conditionalExtractionValid('))
        self.assertLess(source.index('function conditionalExtractionValid('),source.index('async function start('))
        self.assertIn('function fieldCorrelationValid(',source)
        self.assertIn('function validatedTransmonSelection(',source)

    def test_missing_module_fails_instead_of_serving_an_incomplete_application(self):
        javascript_sources(self.root)[-1].unlink()
        with self.assertRaises(ValueError):javascript_bundle(self.root)

    def test_duplicate_or_reordered_entry_is_rejected(self):
        self.change_manifest(lambda d:d['scripts'].append('app.js'))
        with self.assertRaises(ValueError):javascript_sources(self.root)

    def test_manifest_paths_cannot_escape_the_asset_tree(self):
        self.change_manifest(lambda d:d['scripts'].append('../other.js'))
        with self.assertRaises(ValueError):javascript_sources(self.root)

    def test_unknown_schema_or_nonobject_manifest_is_rejected(self):
        for raw in ('[]','{"schema":"unknown","scripts":["app.js","other.js"]}'):
            (self.root/'modules.json').write_text(raw)
            with self.subTest(raw=raw),self.assertRaises(ValueError):javascript_sources(self.root)

    def test_linked_module_is_not_followed(self):
        path=javascript_sources(self.root)[-1];data=path.read_bytes();path.unlink()
        outside=self.root.parent/'outside.js';outside.write_bytes(data)
        try:path.symlink_to(outside)
        except OSError:self.skipTest('Platform does not permit creating a symlink')
        with self.assertRaises(ValueError):javascript_sources(self.root)

    def test_unknown_http_asset_is_rejected(self):
        for name in ('../DEVELOPMENT_POLICY.json','modules.json','modules/extraction.js'):
            with self.subTest(name=name),self.assertRaises(ValueError):read_asset(name)


if __name__=='__main__':unittest.main()
