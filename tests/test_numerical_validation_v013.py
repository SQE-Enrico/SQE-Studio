"""Numerical validation contracts; mocked Palace output never counted as a real solve."""
from pathlib import Path
from unittest.mock import patch
import csv
import json
import tempfile
import unittest

from sqw import numerical_validation as nv, diagnostics, qualification
from sqw.io import read_json, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]


class NumericalValidationTests(unittest.TestCase):
    def test_numerical_profile_stages_are_bounded_and_distinct(self):
        items=diagnostics.profile_cases('numerical')
        self.assertEqual([x[0] for x in items], ['reference_prepare', 'reference_cap_L1',
                         'reference_cap_L2', 'reference_cap_compare', 'reference_eigenmode'])
        self.assertTrue(all(20<=limit<=360 for _,limit in items))

    def test_reference_inputs_have_explicit_physical_attributes_and_analytical_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            report=nv.prepare(out)
            self.assertFalse(report['scientific_qualification'])
            for level in (1,2):
                folder=out/'numerical-reference'/f'L{level}'/'capacitor'
                self.assertTrue((folder/'device.msh').is_file())
                self.assertEqual(read_json(folder/'electrostatic.json')['Problem']['Type'], 'Electrostatic')
                self.assertEqual(read_json(folder/'mesh.json')['mesh_sha256'],sha256(folder/'device.msh'))
                self.assertTrue(read_json(folder/'reference.json')['pass'])
            self.assertIn('PEC',read_json(out/'numerical-reference'/'L1'/'cavity'/'eigenmode.json')['Boundaries'])
            with self.assertRaises(ValueError): nv.prepare(out)

    def _inject_fixture(self, folder, kind, values):
        # This fixture tests ONLY parsing and provenance checks; no real Palace call.
        name='electrostatic' if kind=='capacitor' else 'eigenmode'
        target=folder/name
        target.mkdir()
        if kind=='capacitor':
            file=target/'terminal-C.csv'
            file.write_text('i,C[i][1] (F)\n1,'+str(values)+'\n',encoding='utf-8')
        else:
            file=target/'eig.csv'
            file.write_text('m,Re{f} (GHz)\n1,'+str(values)+'\n',encoding='utf-8')
        write_json(folder/'solver-record.json',{
            'status':'completed','solver_identity':'MOCK_FIXTURE_NOT_A_SOLVER',
            'mesh_sha256':sha256(folder/'device.msh'),
            'configuration_sha256':sha256(folder/f'{name}.json'),
            'output_sha256':sha256(file)})
        return file

    def test_analytical_patch_test_reports_values_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            nv.prepare(out)
            for level in (1,2):
                folder=out/'numerical-reference'/f'L{level}'/'capacitor'
                target=read_json(folder/'reference.json')['analytic_capacitance_F']
                self._inject_fixture(folder,'capacitor',target*(1.01 if level==1 else 1.005))
            result=nv.capacitance_assessment(out)
            self.assertTrue(result['numerical_reference_pass'])
            self.assertFalse(result['scientific_qualification'])
            self.assertEqual(len(result['levels']),2)
            file=out/'numerical-reference'/'L2'/'capacitor'/'electrostatic'/'terminal-C.csv'
            file.write_text(file.read_text()+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'provenance'):nv.capacitance_assessment(out)

    def test_failed_acceptance_retains_numeric_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            nv.prepare(out)
            for level in (1,2):
                folder=out/'numerical-reference'/f'L{level}'/'capacitor'
                exact=read_json(folder/'reference.json')['analytic_capacitance_F']
                self._inject_fixture(folder,'capacitor',exact*(1.3 if level==1 else 1.4))
            result=nv.capacitance_assessment(out)
            self.assertFalse(result['acceptance_pass'])
            self.assertTrue(result['max_relative_error']>0.3)
            self.assertEqual(result['units'],'F')

    def test_cavity_analytical_frequency_and_fixture_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            nv.prepare(out)
            folder=out/'numerical-reference'/'L1'/'cavity'
            exact=read_json(folder/'reference.json')['frequencies_GHz'][0]
            self._inject_fixture(folder,'cavity',exact*1.02)
            result=nv.eigenmode_assessment(out)
            self.assertTrue(result['acceptance_pass'])
            self.assertAlmostEqual(result['relative_error'],0.02,places=8)
            self.assertFalse(result['scientific_qualification'])

    def test_matrix_view_checks_eigenvalues_and_units(self):
        source={'differential_coordinate_order':['qubit','resonator'],
                'terminal_order':['a','b'],
                'projected_maxwell_c_ff':[[85,-8],[-8,71]],
                'conductor_maxwell_c_ff':[[85,-8],[-8,71]],'raw_sha256':'abc'}
        good=nv.matrix_summary(source)
        self.assertEqual(good['unit'],'fF')
        self.assertTrue(good['minimum_eigenvalue_fF']>0)
        source['projected_maxwell_c_ff']=[[0,0],[0,1]]
        with self.assertRaises(ValueError):nv.matrix_summary(source)

    def test_reference_solver_failure_is_not_reported_as_real_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);nv.prepare(out)
            with patch('sqw.numerical_validation.command',return_value=(['bad-palace-binary'], 'MOCK')):
                with self.assertRaises(FileNotFoundError):
                    nv.execute(out,'capacitor',1,timeout=20)
            self.assertFalse((out/'numerical-reference'/'L1'/'capacitor'/'electrostatic'/'terminal-C.csv').exists())

    def test_web_ui_and_bundle_contract(self):
        js=(ROOT/'src/sqw/studio/static/control.js').read_text(encoding='utf-8')
        self.assertIn('value="numerical"',js)
        self.assertIn('Raw Maxwell matrix',js)
        self.assertIn('scientific_results',js)
        self.assertIn('scientific-results.json',(ROOT/'src/sqw/diagnostics.py').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
