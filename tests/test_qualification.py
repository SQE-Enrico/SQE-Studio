import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.constants import c

from sqw import em, qualification
from sqw.io import read_json, sha256, write_json


class QualificationTests(unittest.TestCase):
    def test_conformal_positive_tetrahedra_and_outward_boundary(self):
        lengths = np.array([120.,80.,50.])
        nodes,tets,triangles = qualification.box_mesh(lengths,(3,2,1))
        determinants = np.array([np.linalg.det(nodes[t[1:]]-nodes[t[0]]) for t in tets])
        self.assertTrue(np.all(determinants>0))
        self.assertAlmostEqual(determinants.sum()/6,np.prod(lengths),places=7)
        self.assertEqual(len(triangles),4*(3*2+3*1+2*1))
        for face in triangles:
            p = nodes[face]
            self.assertGreater(np.dot(np.cross(p[1]-p[0],p[2]-p[0]),p.mean(axis=0)-lengths/2),0)

    def test_fem_capacitor_agrees_with_known_linear_potential(self):
        nodes,tets,_ = qualification.box_mesh((1000.,800.,500.),(4,3,2))
        ref = qualification.capacitor_reference(nodes,tets,11.45)
        self.assertLess(abs(ref['capacitance_F']/1.62208720576e-13-1),1e-7)
        self.assertLess(ref['maximum_potential_error_V'],1e-12)
        self.assertLess(ref['relative_error'],1e-12)

    def test_box_mode_multiplicity_and_analytic_limit(self):
        modes = qualification.cavity_frequencies((10000.,10000.,10000.),5)
        np.testing.assert_allclose(modes[:3],c/(np.sqrt(2)*.01)/1e9,rtol=1e-12)
        np.testing.assert_allclose(modes[3:],c*np.sqrt(3)/(2*.01)/1e9,rtol=1e-12)

    def test_preparation_does_not_claim_palace_was_run(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'suite'
            result = qualification.qualify(out)
            self.assertEqual(result['independent_capacitor_fem'],'passed')
            self.assertEqual(result['palace'],'not_run')
            self.assertIn('$MeshFormat',(out/'cavity/device.msh').read_text())
            with self.assertRaises(ValueError):
                qualification.qualify(out)

    def test_solver_raw_output_change_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            qualification.prepare(out/'suite')
            case = out/'suite/capacitor'
            raw = case/'electrostatic/terminal-C.csv'
            raw.parent.mkdir()
            # Software contract fixture; no native solver invocation is implied.
            raw.write_text('i,C[i][1] (F)\n1,1.62207560532e-13\n')
            record = {'status':'completed','mesh_sha256':sha256(case/'device.msh'),
                      'configuration_sha256':sha256(case/'electrostatic.json'),
                      'contract_sha256':sha256(case/'contract.json'),
                      'raw_sha256':{'electrostatic/terminal-C.csv':sha256(raw)}}
            write_json(case/'solve-electrostatic.json',record)
            em.validate_solve_record(case,'electrostatic')
            raw.write_text('i,C[i][1] (F)\n1,9.9e-13\n')
            with self.assertRaisesRegex(ValueError,'raw output was changed'):
                em.validate_solve_record(case,'electrostatic')

    def test_capacitor_parser_and_duplicate_mode_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'c.csv'
            p.write_text('i,C[i][1] (F)\n1,1.62207560532e-13\n')
            self.assertAlmostEqual(em.read_palace_capacitance(p,1)[0,0],162.207560532)
            p.write_text('i,Re{f} (GHz)\n1,5.0\n1,7.0\n')
            with self.assertRaises(ValueError):
                em.read_eigenfrequency(p,1)
            p.write_text('i,Re{f} (GHz)\n1.5,5.0\n')
            with self.assertRaises(ValueError):
                em.read_eigenfrequency(p,1)


if __name__ == '__main__':
    unittest.main()
