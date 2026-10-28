"""v0.14 QPU refinement contract tests (fixtures are NOT Palace solver runs)."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sqw import qpu_validation as qv, diagnostics
from sqw.io import sha256, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


class QPUConvergenceTests(unittest.TestCase):
    def test_profiles_are_opt_in_and_bounded(self):
        self.assertEqual([x[0] for x in diagnostics.profile_cases('qpu')],
                         ['geometry', 'mesh', 'qpu_cap_prepare', 'qpu_cap_L0', 'qpu_cap_L1','qpu_cap_assess'])
        self.assertEqual([x[0] for x in diagnostics.profile_cases('qpu_modes')],
                         ['geometry','mesh','qpu_mode_prepare','qpu_mode_L0','qpu_mode_L1','qpu_mode_assess'])
        self.assertTrue(all(0 < limit <= 1200 for _,limit in diagnostics.profile_cases('qpu_modes')))

    def fixture(self, root, kind='electrostatic', *, stable=True):
        root = Path(root)
        (root/'device.msh').write_text('MESH INPUT TEST FIXTURE', encoding='utf-8')
        geometry = 'fixture-sha-geometry'
        write_json(root/'mesh.json', {'mesh_sha256':sha256(root/'device.msh'), 'geometry_sha256': geometry})
        terminals = ['Q0.pad_a','Q0.pad_b','Q0.resonator','input']
        write_json(root/'contract.json', {'geometry_sha256':geometry,
           'terminal_order':terminals,'junction_order':['JJ0'], 'palace_configs':[kind]})
        write_json(root/f'{kind}.json',{'Problem':{'Type':'Electrostatic' if kind == 'electrostatic' else 'Eigenmode','Output':kind},
                   'Model':{'Mesh':'device.msh'}, 'Solver':{'Electrostatic' if kind=='electrostatic' else 'Eigenmode':{'Save':0}}})
        qv.prepare(root,kind)
        self.assertTrue(read_json(root/f'convergence-{kind}-L0.json')['Problem']['OutputFormats']['Paraview'])
        for level in (0, 1):
            name = f'convergence-{kind}-L{level}'
            output = root/name
            output.mkdir()
            if kind == 'electrostatic':
                matrix = np.array([[100.,-10.,-4.,0.],[-10.,90.,-3.,0.],[-4.,-3.,75.,0.],[0.,0.,0.,40.]])
                matrix *= (1 + ((.003 if stable else .3) if level == 0 else 0))
                source=output/'terminal-C.csv'
                with source.open('w',newline='') as file:
                    writer=csv.writer(file);writer.writerow(['i']+[f'C[i][{i}] (F)' for i in range(1,5)])
                    for i,row in enumerate(matrix):writer.writerow([i+1]+[v*1e-15 for v in row])
            else:
                source=output/'eig.csv'
                source.write_text('m,Re{f} (GHz)\n1,5.0\n2,6.0\n' if level else 'm,Re{f} (GHz)\n1,5.01\n2,6.01\n')
            write_json(root/f'solve-{name}.json',{'status':'completed', 'mesh_sha256':sha256(root/'device.msh'),
                 'configuration_sha256':sha256(root/f'{name}.json'), 'geometry_sha256':geometry,
                 'solver_identity':'MOCK_TEST_FIXTURE_NOT_PALACE',
                 'outputs_sha256':{f'{name}/{source.name}':sha256(source)}})
        return root

    def test_paired_capacitance_contains_full_numeric_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.fixture(tmp)
            data = qv.assess(root, 'electrostatic')
            self.assertTrue(data['numerically_converged'])
            self.assertTrue(data['acceptance_pass'])
            self.assertFalse(data['scientific_qualification'])
            self.assertEqual(len(data['qpu_capacitance']['levels']),2)
            self.assertEqual(data['qpu_capacitance']['unit'],'fF')
            self.assertGreater(data['qpu_capacitance']['min_eigenvalue_fF'][0],0)
            source = root/'convergence-electrostatic-L1'/'terminal-C.csv'
            source.write_text(source.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Changed Palace output'):
                qv.assess(root,'electrostatic')

    def test_failed_convergence_keeps_observed_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp, stable=False)
            data=qv.assess(root,'electrostatic')
            self.assertFalse(data['acceptance_pass'])
            self.assertTrue(data['last_relative_change']>0.1)
            self.assertTrue((root/'qpu-electrostatic-convergence-summary.json').is_file())

    def test_mode_comparison_is_not_mode_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp,'eigenmode')
            data=qv.assess(root,'eigenmode')
            self.assertTrue(data['acceptance_pass']) # data were extracted, not mode identity
            self.assertFalse(data['scientific_qualification'])
            self.assertFalse(data['field_overlap_mode_identification'])
            self.assertEqual(data['mode_tracking'],'INDEX_ONLY_NOT_FIELD_OVERLAP')

    def test_energy_csv_requires_solver_hash_and_exposes_only_compact_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            name='convergence-electrostatic-L0'
            energy=root/name/'domain-E.csv'
            energy.write_text('i,U_e (J), U_m (J)\n1,1.23e-19,0.0\n', encoding='utf-8')
            rec=root/f'solve-{name}.json'
            obj=read_json(rec)
            obj['outputs_sha256'][f'{name}/domain-E.csv']=sha256(energy)
            write_json(rec,obj)
            found=qv.assess(root,'electrostatic')['energy_and_field_inventory']
            self.assertEqual(found[0]['file'],'domain-E.csv')
            self.assertAlmostEqual(found[0]['last_numeric_row'][1]['value'],1.23e-19)
            energy.write_text(energy.read_text()+'2,99,99\n')
            with self.assertRaisesRegex(ValueError,'Changed Palace output'):
                qv.assess(root,'electrostatic')

    def test_no_old_or_missing_provenance_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp)
            rec=root/'solve-convergence-electrostatic-L1.json'
            obj=read_json(rec);obj['status']='failed';write_json(rec,obj)
            with self.assertRaisesRegex(ValueError,'provenance'):
                qv.assess(root,'electrostatic')

    def test_mode_stage_is_warn_not_qualified_even_if_solver_returns_data(self):
        from sqw.palace_bridge import readiness
        fake=(0, False, .01, 'isolated fixture', {'acceptance_pass':True})
        with patch('sqw.diagnostics.versions',return_value={'gmsh':'4.15'}), \
             patch('sqw.palace_bridge.readiness',return_value={'installed':True}), \
             patch('sqw.diagnostics._isolated_case',return_value=fake):
            checks, _ = diagnostics.scientific_workflow(ROOT, profile='qpu_modes')
        self.assertEqual(checks[-1]['status'],'WARN')
        self.assertEqual(checks[-1]['code'],'MODE_IDENTITY_UNVERIFIED')

    def test_failed_level_zero_skips_expensive_level_one(self):
        with patch('sqw.diagnostics.versions',return_value={'gmsh':'4.15'}), \
             patch('sqw.palace_bridge.readiness',return_value={'installed':True}), \
             patch('sqw.diagnostics._isolated_case',side_effect=[(0,False,.1,'',{}),
                 (0,False,.1,'',{}),(0,False,.1,'',{}),(1,False,.1,'failure',None)]) as probe:
            checks, _ = diagnostics.scientific_workflow(ROOT, profile='qpu')
        self.assertEqual(probe.call_count, 4)
        self.assertEqual([c['status'] for c in checks[-3:]],['FAIL','SKIP','SKIP'])

    def test_wsl_runner_whitelists_refinement_configs_without_shell_expansion(self):
        script=(ROOT/'scripts/palace-wsl-run.sh').read_text()
        self.assertIn('convergence-(electrostatic|eigenmode)-L[0-3]',script)
        self.assertIn('^(',script)
        self.assertIn('\\.json$',script)

    def test_ui_has_both_profiles_and_field_disclosure(self):
        js=(ROOT/'src/sqw/studio/static/control.js').read_text()
        self.assertIn('value="qpu"',js)
        self.assertIn('value="qpu_modes"',js)
        self.assertIn('Field / energy output inventory',js)
        self.assertIn('two', (ROOT/'src/sqw/qpu_validation.py').read_text().lower())


if __name__ == '__main__':unittest.main()
