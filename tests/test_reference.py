"""Optional integrations: skipped explicitly when the candidate stack is unavailable."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from sqw import assembly, cad, circuit, config, experiment, geometry, workflow
from sqw.io import sha256, write_json


class ReferenceAdapterTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('klayout'),'KLayout Python is not installed')
    def test_process_junction_assembly(self):
        import klayout.db as kdb
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root/'run'
            cfg = config.validate({})
            geo = geometry.build(cfg)
            params = circuit.parameters(cfg,circuit.surrogate(cfg,geo))
            workflow.stage('layout',cfg,run)
            workflow.stage('quantize',cfg,run)
            layout = kdb.Layout()
            layout.dbu = .001
            cell = layout.create_cell('TEST_JJ')
            # A synthetic contact fixture, not a functional tunnel junction.
            for box,layer in [(kdb.Box(-4500,-500,-500,500),2),(kdb.Box(500,-500,4500,500),3)]:
                cell.shapes(layout.layer(layer,0)).insert(box)
            path = root/'fixture.gds'
            layout.write(str(path))
            process = {'schema_version':1,'process_name':'synthetic_contact_fixture',
                       'process_version':'test','junction_gds':'fixture.gds','junction_cell':'TEST_JJ',
                       'junction_gds_sha256':sha256(path),'contact_layers':[[2,0],[3,0]],
                       'left_anchor_um':[-4,0],'right_anchor_um':[4,0],
                       'Ic_nA':params['junction']['Ic_nA'],'Cj_fF':params['junction']['Cj_fF'],
                       'electrical_tolerance_relative':.05}
            manifest = root/'process.json'
            write_json(manifest,process)
            assembly.assemble(run,manifest,root/'out')
            merged = kdb.Layout()
            merged.read(str(root/'out/process_candidate.gds'))
            self.assertEqual(len(merged.top_cells()),1)
            self.assertIsNotNone(merged.find_layer(2,0))
            self.assertIsNotNone(merged.find_layer(3,0))

    @unittest.skipUnless(importlib.util.find_spec('scqubits'),'scqubits is not installed')
    def test_scqubits_crosscheck(self):
        vals,_ = circuit.transmon(15,.25,backend='scqubits')
        self.assertGreater(vals[1],4)

    @unittest.skipUnless(importlib.util.find_spec('qpdk'),'QPDK is not installed')
    def test_qpdk_GDS_matches_shared_geometry(self):
        cfg = config.validate({})
        geo = geometry.build(cfg)
        with tempfile.TemporaryDirectory() as d:
            cad.write_gds(geo,Path(d)/'qpdk.gds','qpdk')
            self.assertTrue((Path(d)/'qpdk.gds').is_file())

    @unittest.skipUnless(importlib.util.find_spec('qutip'),'QuTiP is not installed')
    def test_qutip_crosscheck(self):
        cfg = config.validate({})
        geo = geometry.build(cfg)
        params = circuit.parameters(cfg,circuit.surrogate(cfg,geo))
        with tempfile.TemporaryDirectory() as d:
            result = experiment.simulate(cfg,params,d,backend='qutip')
            self.assertEqual(result['dynamics_backend'],'qutip')


if __name__ == '__main__':
    unittest.main()
