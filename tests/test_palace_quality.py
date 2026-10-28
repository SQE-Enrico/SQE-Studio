"""No actual Palace solver or Julia invocation: deterministic contract tests."""
import copy
import csv
import tempfile
import unittest
from pathlib import Path

from sqw.io import read_json, sha256, write_json
from sqw.palace_quality import prepare, summarize, eigen_frequencies
from sqw.josephson_bridge import export_design
from sqw import quantumlab


class PalaceConvergenceContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        (self.out/'device.msh').write_text('TEST_ONLY_NO_MESH',encoding='ascii')
        self.geometry='a'*64
        write_json(self.out/'contract.json',{'geometry_sha256':self.geometry,
            'palace_configs':['eigenmode','electrostatic'],'terminal_order':['A','B']})
        write_json(self.out/'mesh.json',{'geometry_sha256':self.geometry,
            'mesh_sha256':sha256(self.out/'device.msh')})
        for problem in ('eigenmode','electrostatic'):
            write_json(self.out/(problem+'.json'),{'Problem':{
                'Type':'Eigenmode' if problem=='eigenmode' else 'Electrostatic',
                'Output':problem},'Model':{'Mesh':'device.msh','L0':1e-6},
                'Solver':{'Order':2}})

    def write_simulated_case(self,name,kind,values,identity='Palace-TEST-DOUBLE'):
        # Simulated data is isolated to tests and cannot pass for real FEM.
        path=self.out/name;path.mkdir()
        if kind=='eigenmode':
            with (path/'eig.csv').open('w',newline='') as f:
                writer=csv.writer(f)
                writer.writerow(['m','Re{f} (GHz)','Im{f} (GHz)'])
                for i,v in enumerate(values,1):writer.writerow([i,v,0.0])
            source=path/'eig.csv'
        else:
            with (path/'terminal-C.csv').open('w',newline='') as f:
                writer=csv.writer(f);writer.writerow(['i','C[i][1] (F)','C[i][2] (F)'])
                for i,row in enumerate(values,1):writer.writerow([i]+[v*1e-15 for v in row])
            source=path/'terminal-C.csv'
        write_json(self.out/('solve-'+name+'.json'),{
          'status':'completed', 'mesh_sha256':sha256(self.out/'device.msh'),
          'configuration_sha256':sha256(self.out/(name+'.json')),
          'geometry_sha256':self.geometry,'solver_identity':identity,
          'outputs_sha256':{str(source.relative_to(self.out)):sha256(source)}})

    def test_prepare_clone_uniform_refinement_without_touching_baseline(self):
        original=sha256(self.out/'eigenmode.json')
        names=prepare(self.out,'eigenmode')
        self.assertEqual(len(names),3)
        self.assertEqual([read_json(self.out/(n+'.json'))['Model']['Refinement']['UniformLevels'] for n in names],[0,1,2])
        self.assertEqual(sha256(self.out/'eigenmode.json'),original)
        self.assertEqual(len(read_json(self.out/'contract.json')['palace_configs']),5)
        with self.assertRaisesRegex(ValueError,'already exists'):prepare(self.out,'eigenmode')

    def test_verified_eigenmode_convergence_is_not_full_qualification(self):
        names=prepare(self.out,'eigenmode')
        for name,vals in zip(names,[[5.0,6.0],[5.0004,6.0003],[5.0005,6.0004]]):
            self.write_simulated_case(name,'eigenmode',vals)
        result=summarize(self.out,'eigenmode',names)
        self.assertTrue(result['numerically_converged'])
        self.assertFalse(result['scientifically_qualified'])
        self.assertEqual(result['assessment'],'PASS_NUMERICAL_ONLY')
        self.assertTrue((self.out/'convergence-eigenmode-report.json').is_file())
        (self.out/names[-1]/'eig.csv').write_text('TAMPER\n',encoding='ascii')
        with self.assertRaisesRegex(ValueError,'Changed Palace output'):summarize(self.out,'eigenmode',names)

    def test_capacitance_gate_with_real_provenance_contract_and_3_levels(self):
        names=prepare(self.out,'electrostatic')
        mats=[[[100,-1],[-1,90]],[[100.2,-1.02],[-1.02,90.16]],[[100.21,-1.021],[-1.021,90.17]]]
        for name,m in zip(names,mats):self.write_simulated_case(name,'electrostatic',m)
        result=summarize(self.out,'electrostatic',names)
        self.assertTrue(result['numerically_converged'])
        self.assertFalse(result['scientifically_qualified'])
        self.assertEqual(len(result['values']),3)
        # This is only the quality gate's scientific-qualification indicator,
        # which must not imply material/process validation.
        self.assertIn('not validation of EM',result['limitations'][0])

    def test_no_degraded_pass_on_nonconvergence_or_mixed_solver(self):
        names=prepare(self.out,'eigenmode',levels=(0,1))
        self.write_simulated_case(names[0],'eigenmode',[4,7])
        self.write_simulated_case(names[1],'eigenmode',[5,8])
        self.assertFalse(summarize(self.out,'eigenmode',names)['numerically_converged'])
        record=read_json(self.out/('solve-'+names[1]+'.json'))
        record['solver_identity']='OTHER_INSTALLATION'
        write_json(self.out/('solve-'+names[1]+'.json'),record)
        with self.assertRaisesRegex(ValueError,'same solver'):summarize(self.out,'eigenmode',names)

    def test_bad_header_rejected_and_mesh_hash_checked(self):
        self.assertRaisesRegex(ValueError,'Mesh',self._tamper_mesh_and_prepare)
        p=self.out/'bad-eig.csv'
        p.write_text('m,f (MHz)\n1,5000\n')
        with self.assertRaisesRegex(ValueError,'GHz'):eigen_frequencies(p)

    def _tamper_mesh_and_prepare(self):
        (self.out/'device.msh').write_text('changed')
        prepare(self.out,'electrostatic')


class JosephsonExportTests(unittest.TestCase):
    def test_exports_nonlinear_junctions_and_coupling_caps_in_si(self):
        design=quantumlab.preset(1)
        with tempfile.TemporaryDirectory() as d:
            contract=export_design(design,d)
            source=(Path(d)/'circuit.jl').read_text()
            self.assertIn('"Lj1"',source)
            self.assertIn('"P1"',source)
            self.assertIn('"P2"',source)
            self.assertEqual(contract['state'],'EXPORTED_NOT_SIMULATED')
            self.assertEqual(len([x for x in contract['elements'] if x['type']=='P']),2)
            self.assertIn('julia_component',contract['elements'][0])
            self.assertTrue((Path(d)/'josephsoncircuits-contract.json').exists())

    def test_refuse_squid_collapse(self):
        design=quantumlab.preset(1)
        jj=next(x for x in design['elements'] if x['kind']=='JJ')
        jj.update(kind='SQUID',asymmetry=.1,flux_phi0=.2)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'explicit loop'):
                export_design(design,d)
            self.assertFalse((Path(d)/'circuit.jl').exists())


if __name__=='__main__':unittest.main()
