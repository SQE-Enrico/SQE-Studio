import tempfile
import unittest
from pathlib import Path

from sqw import circuit, config, geometry, provenance, workflow
from sqw.io import read_json, write_json


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.validate({})

    def test_rerun_invalidates_downstream_and_report_cannot_use_it(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            workflow.run(self.cfg,out)
            provenance.verify(out)
            workflow.stage('quantize',self.cfg,out)
            state = read_json(out/'run.json')
            self.assertEqual(state['stages']['experiment'],'stale')
            self.assertEqual(state['stages']['report'],'stale')
            with self.assertRaises(ValueError):
                workflow.stage('report',self.cfg,out)
            with self.assertRaises(ValueError):
                provenance.verify(out)
            workflow.stage('experiment',self.cfg,out)
            workflow.stage('report',self.cfg,out)
            self.assertEqual(provenance.verify(out)['status'],'passed')

    def test_default_quantize_preserves_imported_source(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'run'
            data = circuit.surrogate(self.cfg,geometry.build(self.cfg))
            data['source'] = 'synthetic_fixture'
            external = Path(d)/'input.json'
            write_json(external,data)
            workflow.stage('layout',self.cfg,out)
            workflow.stage('quantize',self.cfg,out,extraction=external)
            workflow.stage('quantize',self.cfg,out)
            self.assertEqual(read_json(out/'parameters.json')['source'],'synthetic_fixture')
            workflow.stage('quantize',self.cfg,out,force_surrogate=True)
            self.assertEqual(read_json(out/'parameters.json')['source'],'analytic_surrogate')

    def test_external_parameter_input_change_is_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'run'
            external = Path(d)/'input.json'
            data = circuit.surrogate(self.cfg,geometry.build(self.cfg))
            data['source'] = 'synthetic_fixture'
            write_json(external,data)
            workflow.stage('layout',self.cfg,out)
            workflow.stage('quantize',self.cfg,out,extraction=external)
            data['matrix_fF'][0][0] += 5
            write_json(external,data)
            with self.assertRaisesRegex(ValueError,'quantize input'):
                workflow.stage('experiment',self.cfg,out)

    def test_changed_configuration_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            workflow.stage('spec',self.cfg,d)
            snapshot = read_json(Path(d)/'resolved_config.json')
            snapshot['circuit']['EJ_GHz'] += 1
            write_json(Path(d)/'resolved_config.json',snapshot)
            with self.assertRaises(ValueError):
                workflow.stage('layout',self.cfg,d)


if __name__ == '__main__':
    unittest.main()
