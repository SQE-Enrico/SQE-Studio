import copy
import struct
import tempfile
import unittest
from pathlib import Path

from sqw import cad, config, em, geometry, workflow
from sqw.io import read_json, sha256, write_json


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.validate({})
        self.geo = geometry.build(self.cfg)

    def test_configuration_rejects_typos_and_bad_units(self):
        for data in [{'layout':{'pad_wdith_um':200}}, {'circuit':{'EJ_GHz':-10}},
                     {'device':{'temperature_mK':float('nan')}},
                     {'experiment':{'shots':1.5}}, {'targets':{'f01_GHz':50}},
                     {'layout':{'junction_mask_qualified':'true'}}]:
            with self.assertRaises(ValueError):
                config.validate(data)

    def test_connected_and_isolated_geometry(self):
        self.assertTrue(all(n==1 for n in self.geo['connectivity_components'].values()))
        self.assertAlmostEqual(sum(abs(a[0]-b[0])+abs(a[1]-b[1])
                                   for a,b in zip(self.geo['resonator_path'],self.geo['resonator_path'][1:])),8300)

    def test_overlap_and_small_die_rejected(self):
        for section,key,value in [('layout','feed_y_um',1000.),('layout','chip_size_um',3000.)]:
            cfg = copy.deepcopy(self.cfg)
            cfg[section][key] = value
            with self.assertRaises(ValueError):
                geometry.build(cfg)

    def test_gds_units_coordinates_and_repeatability(self):
        with tempfile.TemporaryDirectory() as d:
            a,b = Path(d)/'a.gds',Path(d)/'b.gds'
            cad.write_gds(self.geo,a)
            cad.write_gds(self.geo,b)
            self.assertEqual(sha256(a),sha256(b))
            info = cad.inspect_gds(a)
            self.assertEqual(info['layers'],[1,90,91,99])
            raw,offset = a.read_bytes(),0
            while offset<len(raw):
                size,kind,dtype = struct.unpack('>HBB',raw[offset:offset+4])
                if kind==3:
                    def decode(blob):
                        return int.from_bytes(blob[1:],'big')/(1<<56)*16**((blob[0]&127)-64)
                    self.assertAlmostEqual(decode(raw[offset+4:offset+12]),1e-3)
                    self.assertAlmostEqual(decode(raw[offset+12:offset+20]),1e-9)
                if kind==16:
                    coords = struct.unpack('>'+('i'*((size-4)//4)),raw[offset+4:offset+size])
                    self.assertEqual(coords[:2],coords[-2:])
                offset += size

    def test_palace_capacitance_contract(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'terminal-C.csv'
            p.write_text('i,C[i][1] (F),C[i][2] (F),C[i][3] (F),C[i][4] (F)\n'
                         '1,1e-13,-1e-14,0,0\n2,-1e-14,1e-13,0,0\n'
                         '3,0,0,1e-12,0\n4,0,0,0,1e-12\n')
            c = em.read_palace_capacitance(p)
            self.assertAlmostEqual(c[0,0],100)
            p.write_text(p.read_text().replace('(F)','(pF)'))
            with self.assertRaises(ValueError):
                em.read_palace_capacitance(p)

    def test_palace_mode_contract(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'eig.csv'
            p.write_text('i,Re{f} (GHz),Im{f} (GHz)\n1,4.2,0\n2,7.1,0\n')
            self.assertEqual(em.read_eigenfrequency(p,2),7.1)
            with self.assertRaises(ValueError):
                em.read_eigenfrequency(p,3)

    def test_boundary_map_and_junction(self):
        with tempfile.TemporaryDirectory() as d:
            em.export_configs(self.cfg,self.geo,d)
            electro = read_json(Path(d)/'electrostatic.json')
            self.assertEqual([x['Attributes'] for x in electro['Boundaries']['Terminal']],[[11],[12],[13],[14]])
            bare = read_json(Path(d)/'eigenmode.json')
            full = read_json(Path(d)/'linearized.json')
            self.assertEqual(len(bare['Boundaries']['LumpedPort']),2)
            self.assertEqual(full['Boundaries']['LumpedPort'][-1]['Attributes'],[21])
            self.assertNotIn('L',bare['Boundaries']['LumpedPort'][0])

    def test_fem_import_requires_successful_native_solve_records(self):
        with tempfile.TemporaryDirectory() as d:
            em.export_configs(self.cfg,self.geo,d)
            with self.assertRaises(FileNotFoundError):
                em.import_results(d,self.geo,2)

    def test_different_config_cannot_reuse_run(self):
        with tempfile.TemporaryDirectory() as d:
            workflow.stage('spec',self.cfg,d)
            different = copy.deepcopy(self.cfg)
            different['circuit']['EJ_GHz'] += 1
            with self.assertRaises(ValueError):
                workflow.stage('spec',different,d)

    def test_pipeline_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            workflow.run(self.cfg,d)
            out = Path(d)
            state = read_json(out/'run.json')
            self.assertEqual(state['physics_source'],'analytic_surrogate')
            self.assertTrue(all(x=='completed' for x in state['stages'].values()))
            for rel,expected in read_json(out/'manifest.json')['sha256'].items():
                self.assertEqual(sha256(out/rel),expected)
            self.assertTrue((out/'report.html').exists())
            with self.assertRaises(ValueError):
                workflow.run(self.cfg,d)

    def test_stale_extraction_and_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            workflow.stage('layout',self.cfg,d)
            bad = {'node_order':['pad_a','pad_b','resonator','feedline'],
                   'source':'palace_fem','geometry_sha256':'bad'}
            p = Path(d)/'wrong.json'
            write_json(p,bad)
            with self.assertRaises(ValueError):
                workflow.stage('quantize',self.cfg,d,extraction=p)
            geo_path = Path(d)/'layout/geometry.json'
            data = read_json(geo_path)
            data['resonator_length_um'] += 1
            write_json(geo_path,data)
            with self.assertRaises(ValueError):
                workflow.stage('em-export',self.cfg,d)


if __name__ == '__main__':
    unittest.main()
