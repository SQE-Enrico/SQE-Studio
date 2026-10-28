import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.constants import e, h

from sqw import circuit, config, em, experiment, geometry


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.validate({})
        self.geo = geometry.build(self.cfg)

    def test_charge_basis_convergence(self):
        v,_ = circuit.transmon(15,.25,ncut=30)
        w,_ = circuit.transmon(15,.25,ncut=45)
        np.testing.assert_allclose(v,w,atol=1e-10)

    def test_transmon_asymptote(self):
        v,n = circuit.transmon(20,.20)
        self.assertLess(abs(v[1]-(np.sqrt(8*20*.20)-.20)),.02)
        self.assertLess(abs((v[2]-2*v[1])+.20),.03)
        self.assertGreater(abs(n[0,1]),.5)

    def test_target_inverse(self):
        target = circuit.synthesize(self.cfg)
        v,_ = circuit.transmon(target['EJ_GHz'],target['EC_GHz'])
        self.assertAlmostEqual(v[1],5,places=7)
        self.assertAlmostEqual((v[2]-2*v[1])*1000,-250,places=5)
        self.assertAlmostEqual(e**2/(2*h*target['EC_GHz']*1e9)*1e15,target['C_total_target_fF'])

    def test_floating_two_equal_pads(self):
        # Two 100 fF pads to ground and 10 fF mutual -> differential C = 60 fF.
        c = np.diag([110.,110.,1000.,2000.])
        c[0,1] = c[1,0] = -10
        red,kinv = circuit.reduce_floating(c)
        self.assertAlmostEqual(1/kinv[0,0]*1e15,60)
        self.assertAlmostEqual(red[1,1]*1e15,500)  # half-wave mode ground C

    def test_floating_junction_C_added_once(self):
        c = np.diag([100.,100.,1000.,2000.])
        _,kinv = circuit.reduce_floating(c,2)
        self.assertAlmostEqual(1/kinv[0,0]*1e15,52)

    def test_capacitance_rejects_nonphysical(self):
        for c in [np.zeros((4,4)),np.eye(3),np.eye(4)*-1,np.full((4,4),np.nan)]:
            with self.assertRaises(ValueError):
                circuit.validate_capacitance(c)
        c = np.eye(4)
        c[0,1] = .1
        with self.assertRaises(ValueError):
            circuit.validate_capacitance(c)

    def test_zero_coupling_and_dispersive_sign(self):
        v,n = circuit.transmon(14.5,.25)
        p = circuit.coupled_spectrum(v,n,7.2,0)
        self.assertAlmostEqual(p['f01_dressed_GHz'],v[1],places=10)
        self.assertAlmostEqual(p['chi_exact_MHz'],0,places=9)
        p = circuit.coupled_spectrum(v,n,7.2,.04)
        self.assertLess(p['chi_exact_MHz'],0)
        self.assertGreater(p['minimum_label_overlap'],.95)

    def test_EPR_single_junction_limit(self):
        # p=1 gives alpha=-f^2/(8 EJ); transmon harmonic f^2=8 EJ EC -> -EC.
        result = em.epr_kerr([5],[12.5],[[1]])
        self.assertAlmostEqual(result['anharmonicity_MHz'][0],-250)
        with self.assertRaises(ValueError):
            em.epr_kerr([5],[12.5],[[1.1]])

    def test_thermal_and_coherence(self):
        p = circuit.parameters(self.cfg,circuit.surrogate(self.cfg,self.geo))
        self.assertLess(p['thermal_excited_probability'],1e-4)
        self.assertAlmostEqual(sum(p['thermal_populations']),1,places=12)
        with tempfile.TemporaryDirectory() as d:
            result = experiment.simulate(self.cfg,p,d)
            self.assertLessEqual(result['T2_us'],2*result['T1_effective_us'])
            data = np.genfromtxt(Path(d)/'t1.csv',delimiter=',',names=True)
            self.assertAlmostEqual(data['p1_ideal'][0],1)
            self.assertLess(data['p1_ideal'][-1],.01)
            for name in ['t1','rabi','ramsey']:
                a = np.genfromtxt(Path(d)/f'{name}.csv',delimiter=',',names=True)
                self.assertTrue(np.all((a['p1_observed']>=0)&(a['p1_observed']<=1)))

    def test_bloch_unitary_limit(self):
        t = np.linspace(0,1,101)
        p = experiment.bloch(t,2,0,0,0,0)
        np.testing.assert_allclose(p,np.sin(np.pi*2*t)**2,atol=1e-12)

    def test_bloch_rejects_nonuniform_time_grid(self):
        with self.assertRaises(ValueError):
            experiment.bloch([0,.1,.4],2,0,.01,.01,0)

    def test_geometry_change_propagates(self):
        p1 = circuit.parameters(self.cfg,circuit.surrogate(self.cfg,self.geo))
        cfg2 = copy.deepcopy(self.cfg)
        cfg2['layout']['pad_width_um'] += 30
        geo2 = geometry.build(cfg2)
        p2 = circuit.parameters(cfg2,circuit.surrogate(cfg2,geo2))
        self.assertNotEqual(self.geo['geometry_sha256'],geo2['geometry_sha256'])
        self.assertLess(p2['f01_GHz'],p1['f01_GHz'])


if __name__ == '__main__':
    unittest.main()
