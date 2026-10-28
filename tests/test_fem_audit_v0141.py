"""v0.14.1 read-only FEM audit tests (synthetic fixtures, never called Palace)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqw import fem_audit, qpu_validation, diagnostics
from sqw.io import sha256, write_json, read_json


def fixture(root):
    root=Path(root)
    order=['Q0.pad_a','Q0.pad_b','Q0.resonator','Q0.feedline']
    tags={'air':1,'silicon':2,'ground':10,'outer':99}
    tags.update({name:100+i for i,name in enumerate(order)})
    names={name:(3 if name in ('air','silicon') else 2, tag) for name,tag in tags.items()}
    mesh=['$MeshFormat','2.2 0 8','$EndMeshFormat','$PhysicalNames',str(len(names))]
    mesh.extend(f'{dim} {tag} "{name}"' for name,(dim,tag) in names.items())
    mesh.extend(['$EndPhysicalNames','$Elements',str(len(names))])
    for i,(name,(dim,tag)) in enumerate(names.items()):
        mesh.append(f'{i+1} {4 if dim==3 else 2} 2 {tag} {i+1} '+ ('1 2 3 4' if dim==3 else '1 2 3'))
    mesh+=['$EndElements']
    (root/'device.msh').write_text('\n'.join(mesh)+'\n')
    write_json(root/'geometry.json',{'geometry_sha256':'G','physical_tags':tags,'terminals':order})
    write_json(root/'mesh.json',{'geometry_sha256':'G','mesh_sha256':sha256(root/'device.msh')})
    write_json(root/'contract.json',{'geometry_sha256':'G','terminal_order':order,'palace_configs':['electrostatic'],'junction_order':['JJ0']})
    write_json(root/'electrostatic.json',{'Problem':{'Type':'Electrostatic','Output':'electrostatic'},
        'Model':{'Mesh':'device.msh'},'Domains':{'Materials':[{'Attributes':[1]},{'Attributes':[2]}]},
        'Boundaries':{'Ground':{'Attributes':[10,99]},'Terminal':[{'Index':i+1,'Attributes':[tags[name]]} for i,name in enumerate(order)]}})
    return root


class FEMAuditTests(unittest.TestCase):
    def test_physical_mesh_attributes_and_terminal_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture(tmp)
            result=fem_audit.geometry_boundary_audit(path)
            self.assertTrue(result['preflight_pass'])
            self.assertEqual(result['terminal_count'],4)
            self.assertEqual(len(result['surface_groups']),8)
            self.assertTrue((path/'geometry-boundary-audit.json').is_file())

    def test_missing_boundary_and_incorrect_terminal_tag_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture(tmp)
            cfg=read_json(path/'electrostatic.json')
            cfg['Boundaries']['Terminal'][0]['Attributes']=[99]
            write_json(path/'electrostatic.json',cfg)
            result=fem_audit.geometry_boundary_audit(path)
            self.assertFalse(result['preflight_pass'])
            self.assertTrue(any('terminal' in x.lower() for x in result['failures']))

    def test_modified_mesh_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture(tmp)
            with (path/'device.msh').open('a') as stream:stream.write('# changed\n')
            with self.assertRaisesRegex(ValueError,'integrity'):
                fem_audit.geometry_boundary_audit(path)

    def test_amr_requires_preflight_and_limits_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture(tmp)
            with self.assertRaises(FileNotFoundError):qpu_validation.prepare_amr(path)
            fem_audit.geometry_boundary_audit(path)
            result=qpu_validation.prepare_amr(path)
            config=read_json(path/'convergence-electrostatic-L2.json')
            refinement=config['Model']['Refinement']
            self.assertEqual(refinement['MaxIts'],1)
            self.assertEqual(refinement['MaxSize'],150000)
            self.assertFalse(result['scientific_qualification'])
            self.assertEqual(read_json(path/'contract.json')['palace_configs'][-1], 'convergence-electrostatic-L2')

    def test_energy_contract_verified_and_mismatch_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture(tmp)
            name='electrostatic'; output=path/name;output.mkdir()
            f=output/'domain-E.csv'
            f.write_text('i,E_elec (J),E_mag (J)\n1,5e-14,0\n2,6e-14,0\n3,7e-14,0\n4,8e-14,0\n')
            write_json(path/'solve-electrostatic.json',{
                'status':'completed','mesh_sha256':sha256(path/'device.msh'),
                'configuration_sha256':sha256(path/'electrostatic.json'),
                'geometry_sha256':'G','outputs_sha256':{f'{name}/domain-E.csv':sha256(f)}})
            matrix=[[100,0,0,0],[0,120,0,0],[0,0,140,0],[0,0,0,160]]
            result=fem_audit.energy_consistency(path,name,matrix)
            self.assertEqual(result['status'],'CONSISTENT')
            self.assertAlmostEqual(result['max_relative_difference'],0)
            result=fem_audit.energy_consistency(path,name,[[200,0,0,0],[0,120,0,0],[0,0,140,0],[0,0,0,160]])
            self.assertEqual(result['status'],'MISMATCH_REQUIRES_INVESTIGATION')
            f.write_text(f.read_text()+'5,7e-14,0\n')
            with self.assertRaisesRegex(ValueError,'Changed Palace output'):
                fem_audit.energy_consistency(path,name,matrix)

    def test_new_profiles_are_explicit_and_dont_default_to_amr(self):
        self.assertEqual([x[0] for x in diagnostics.profile_cases('qpu_audit')],
                         ['geometry','mesh','qpu_mesh_audit'])
        self.assertEqual([x[0] for x in diagnostics.profile_cases('qpu_amr')][-1], 'qpu_amr_assess')
        self.assertNotIn('qpu_amr_run',[case for case,_ in diagnostics.profile_cases('qpu')])

    def test_support_bundle_evidence_is_allowlisted_and_hashed(self):
        from test_qpu_convergence_v014 import QPUConvergenceTests
        with tempfile.TemporaryDirectory() as tmp:
            output = {}
            def fake_probe(root, workspace, case, timeout, profile):
                if case == 'geometry':
                    QPUConvergenceTests().fixture(workspace)
                    (workspace/'geometry-boundary-audit.json').write_text('{"preflight_pass":true}')
                return 0, False, 0.01, 'synthetic fixture only', {'acceptance_pass':True}
            with patch('sqw.diagnostics.versions',return_value={'gmsh':'4.15'}), \
                 patch('sqw.palace_bridge.readiness',return_value={'installed':True}), \
                 patch('sqw.diagnostics._isolated_case',side_effect=fake_probe):
                checks,_=diagnostics.scientific_workflow(Path(tmp),profile='qpu',evidence_sink=output)
            self.assertTrue(output)
            self.assertIn('evidence/convergence-electrostatic-L0/terminal-C.csv',output)
            self.assertNotIn('evidence/device.msh',output)
            self.assertTrue(all(len(x) <= 65536 for x in output.values()))
            self.assertTrue(all(k.startswith('evidence/') for k in output))
            self.assertFalse(any('user-project' in k for k in output))

    def test_ui_discloses_experimental_amr(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'src/sqw/studio/static/control.js').read_text()
        self.assertIn('value="qpu_audit"',text)
        self.assertIn('value="qpu_amr"',text)
        self.assertIn('experimental, slow',text)

if __name__ == '__main__':unittest.main()
