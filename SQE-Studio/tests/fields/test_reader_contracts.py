"""Categorical software fixtures and provenance negatives; no native physics.

Actual SQDMetal/VTK execution is a separate selectable task, never mocked PASS.
"""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

from sqe_studio.eda import upstream_vtk_probe as p

ROOT = Path(__file__).resolve().parents[2]


def block(*, point=None, cell=None):
    return {'point':p._status_for_arrays(point or {}), 'cell':p._status_for_arrays(cell or {})}


def field(association='point'):
    return block(**{association:{'E_real':('f',3),'E_imag':('f',3)}})


def auxiliary():
    return block(cell={'Rank':('i',1),'Indicator':('f',1)})


def record(*blocks):
    return p._diagnostic([{'index':i,'piece_count':4} for i in range(len(blocks))],
                        'PyVista',[{'index':i,'blocks':b} for i,b in enumerate(blocks)])


class CycleRoles(unittest.TestCase):
    def test_field_plus_auxiliary_does_not_require_e_in_auxiliary_cycle(self):
        r=record([field()],[auxiliary()])
        self.assertEqual(r['status'],'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED')
        self.assertEqual(p.diagnostic_summary(r)['cycle_roles'],['COMPLEX_E_FIELD','AUXILIARY_MESH_DATA'])
        self.assertEqual([c['complex_e_declared'] for c in r['cycles']],[True,False])
        self.assertFalse(r['field_values_in_report'])
        self.assertEqual(r['physical_mode_identity'],'NOT_ESTABLISHED')
    def test_role_does_not_depend_on_cycle_ordinal(self):
        r=record([auxiliary()],[field()])
        self.assertEqual([c['role'] for c in r['cycles']],['AUXILIARY_MESH_DATA','COMPLEX_E_FIELD'])
        self.assertEqual(r['status'],'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED')
    def test_cell_fields_use_explicit_same_association(self):
        self.assertEqual(record([field('cell')])['cycles'][0]['role'],'COMPLEX_E_FIELD')
    def test_split_real_imag_associations_cannot_form_a_field(self):
        b=block(point={'E_real':('f',3)},cell={'E_imag':('f',3)})
        self.assertEqual(record([b])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_good_block_cannot_hide_missing_fields_in_another_block(self):
        self.assertNotEqual(record([field(),block()])['status'],'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED')
    def test_mixed_block_associations_remain_unresolved(self):
        self.assertEqual(record([field(),field('cell')])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_auxiliary_marker_cannot_hide_malformed_e(self):
        b=block(point={'E_real':('f',2),'E_imag':('f',3)},cell={'Rank':('i',1)})
        self.assertEqual(record([b])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_partial_e_pair_cannot_be_discarded_as_auxiliary(self):
        b=block(point={'E_real':('f',3)},cell={'Indicator':('f',1)})
        self.assertEqual(record([field()],[b])['status'],'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED')
    def test_partial_b_pair_prevents_a_complete_field_declaration(self):
        b=field();b['point']['B_real']='FLOAT_VECTOR_3'
        self.assertEqual(record([b])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_unknown_cycle_is_preserved_instead_of_silently_skipped(self):
        r=record([field()],[block()])
        self.assertEqual(r['cycles'][1]['role'],'UNCLASSIFIED')
        self.assertEqual(r['status'],'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED')
    def test_auxiliary_only_is_never_field_success(self):
        self.assertEqual(record([auxiliary()])['status'],'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED')
    def test_wrong_auxiliary_components_remain_unclassified(self):
        self.assertEqual(record([block(cell={'Indicator':('f',3)})])['cycles'][0]['role'],'UNCLASSIFIED')
    def test_integer_e_is_not_a_float_vector(self):
        b=block(point={'E_real':('i',3),'E_imag':('i',3)})
        self.assertEqual(record([b])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_b_only_is_not_complex_e(self):
        b=block(point={'B_real':('f',3),'B_imag':('f',3)})
        self.assertEqual(record([b])['cycles'][0]['role'],'INCOMPLETE_OR_UNSUPPORTED_FIELD')
    def test_truncated_or_reordered_reader_results_are_rejected(self):
        for details in ([],[{'index':1,'blocks':[field()]}]):
            with self.subTest(details=details), self.assertRaises(p.ProbeBlocked):
                p._diagnostic([{'index':0,'piece_count':1}],'VTK',details)


class DiagnosticBoundaries(unittest.TestCase):
    def test_rejects_forged_role_counts_status_and_flags(self):
        good=record([field()],[auxiliary()])
        cases=[]
        bad=deepcopy(good);bad['cycles'][1]['role']='COMPLEX_E_FIELD';cases.append(bad)
        bad=deepcopy(good);bad['cycle_role_counts']['COMPLEX_E_FIELD']=2;cases.append(bad)
        bad=deepcopy(good);bad['cycles'][1]['complex_e_declared']=True;cases.append(bad)
        bad=deepcopy(good);bad['status']='UPSTREAM_COMPLEX_E_NOT_ESTABLISHED';cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):p.diagnostic_summary(bad)
    def test_private_or_foreign_metadata_is_not_accepted(self):
        for where in ('top','association','cycle','block'):
            bad=record([field()])
            target={'top':bad,'cycle':bad['cycles'][0],'block':bad['cycles'][0]['blocks'][0],
                    'association':bad['cycles'][0]['blocks'][0]['point']}[where]
            target['private_path']='not_exportable'
            with self.subTest(where=where), self.assertRaises(ValueError):p.diagnostic_summary(bad)
    def test_physics_flags_cannot_be_promoted(self):
        for name,value in (('physical_mode_identity','VERIFIED'),('mesh_convergence','PASS'),('field_values_in_report',True)):
            bad=record([field()]);bad[name]=value
            with self.subTest(name=name), self.assertRaises(ValueError):p.diagnostic_summary(bad)
    def test_resource_and_scalar_type_limits_are_enforced(self):
        for name,value in (('mpi_piece_count',17),('mpi_piece_count',True),('cycle_index_not_mode_identity',True)):
            bad=record([field()]);bad['cycles'][0][name]=value
            with self.subTest(name=name,value=value), self.assertRaises(ValueError):p.diagnostic_summary(bad)
    def test_wrong_or_foreign_array_states_are_rejected(self):
        for name,value in (('Rank','FLOAT_VECTOR_3'),('E_real','NUMERIC_SCALAR'),('E_imag',['ABSENT'])):
            bad=record([field()]);bad['cycles'][0]['blocks'][0]['point'][name]=value
            with self.subTest(name=name), self.assertRaises(ValueError):p.diagnostic_summary(bad)
    def test_blocked_result_accepts_only_fixed_metadata(self):
        r=p._public_result('UPSTREAM_READER_NOT_INSTALLED')
        self.assertEqual(p.diagnostic_summary(r)['status'],'BLOCKED')
        for extras in ({'cycles':[]},{'reason_code':'/private/path'}):
            with self.subTest(extras=extras), self.assertRaises(ValueError):p.diagnostic_summary(dict(r,**extras))


class SignedReaderWorkflow(unittest.TestCase):
    def fixture(self, td):
        root=Path(td);base=root/'sqe_em/outputFiles/paraview/eigenmode';d=base/'Cycle000001'
        d.mkdir(parents=True)
        (d/'proc000000.vtu').write_bytes(b'SOFTWARE_FIXTURE_ONLY')
        (d/'data.pvtu').write_text('<VTKFile type="PUnstructuredGrid"><PUnstructuredGrid><Piece Source="proc000000.vtu"/></PUnstructuredGrid></VTKFile>')
        (base/'eigenmode.pvd').write_text('<VTKFile type="Collection"><Collection><DataSet timestep="1" file="Cycle000001/data.pvtu"/></Collection></VTKFile>')
        entries=[{'name':f.relative_to(root).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in base.rglob('*') if f.is_file()]
        manifest=root/'RESULT_MANIFEST.json';manifest.write_text(json.dumps({'artifacts':entries}))
        return root,manifest,(base/'eigenmode.pvd').relative_to(root).as_posix(),d/'proc000000.vtu'
    def test_unchanged_provenance_flow_with_reader_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root,m,pvd,piece=self.fixture(td)
            with patch.object(p,'_pyvista_probe',return_value=('PyVista',[{'index':0,'blocks':[field()]}])):
                r=p._child_run(root,m,pvd,'pyvista')
            self.assertEqual(r['cycles'][0]['role'],'COMPLEX_E_FIELD')
            self.assertNotIn(str(root),json.dumps(r))
    def test_tamper_before_read_never_calls_backend(self):
        with tempfile.TemporaryDirectory() as td:
            root,m,pvd,piece=self.fixture(td);piece.write_bytes(b'changed')
            with patch.object(p,'_pyvista_probe') as reader:
                with self.assertRaisesRegex(p.ProbeBlocked,'ARTIFACT_HASH_MISMATCH'):p._child_run(root,m,pvd,'pyvista')
                reader.assert_not_called()
    def test_tamper_during_read_is_detected_after_upstream_returns(self):
        with tempfile.TemporaryDirectory() as td:
            root,m,pvd,piece=self.fixture(td)
            def reader(*args):
                piece.write_bytes(b'changed')
                return 'PyVista',[{'index':0,'blocks':[field()]}]
            with patch.object(p,'_pyvista_probe',side_effect=reader):
                with self.assertRaisesRegex(p.ProbeBlocked,'ARTIFACT_CHANGED_DURING_PROBE'):p._child_run(root,m,pvd,'pyvista')
    def test_missing_upstream_package_is_blocked_without_solver(self):
        from sqe_studio.testing.native_fields import run_workflow
        with patch('sqe_studio.testing.native_fields.util.find_spec',return_value=None), \
             patch('sqe_studio.qualification._run') as solver:
            r=run_workflow();solver.assert_not_called()
        self.assertEqual(r['status'],'BLOCKED')
        self.assertEqual(r['execution_kind'],'NOT_RUN')
        self.assertEqual(r['missing_packages'],['vtk','pyvista','SQDMetal'])
    def test_fields_profile_has_no_palace_or_quantum_dependency(self):
        from sqe_studio.testing.catalog import PROFILES,resolve_selection
        self.assertEqual(resolve_selection(PROFILES['fields'])['resolved'],['integrity','targeted','fields'])


class ReportCompatibility(unittest.TestCase):
    def evidence(self, diagnostic):
        # Reuse the existing scalar software fixture without importing pytest.
        source=ROOT/'tests/integration/test_native_scalar_qualification_link.py'
        node=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='_evidence')
        env={'hashlib':hashlib,'json':json}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
        data=env['_evidence']();base='em/native/native_palace_solve-'
        from sqe_studio.cycle_qualification import _case_from_em
        self.assertEqual(_case_from_em(data,'B02')['stage_status'],'BLOCKED',
                         'Shared scalar fixture must be valid before diagnostic mutations')
        screen=json.loads(data[base+'results-screen.json']);screen['upstream_field_probe']=diagnostic
        data[base+'results-screen.json']=json.dumps(screen).encode()
        data[base+'upstream-field-probe.json']=json.dumps(diagnostic).encode()
        return data
    def test_v2_field_and_auxiliary_metadata_never_qualifies_b02(self):
        from sqe_studio.cycle_qualification import _case_from_em
        r=_case_from_em(self.evidence(record([field()],[auxiliary()])),'B02')
        self.assertEqual(r['stage_status'],'BLOCKED')
        self.assertEqual(r['measurements']['upstream_vtk_diagnostic']['cycle_roles'],['COMPLEX_E_FIELD','AUXILIARY_MESH_DATA'])
        self.assertEqual(r['measurements']['mesh_convergence'],'NOT_ESTABLISHED')
    def test_v2_forged_classification_is_a_report_failure(self):
        from sqe_studio.cycle_qualification import _case_from_em
        bad=record([field()],[auxiliary()]);bad['cycles'][1]['role']='COMPLEX_E_FIELD'
        self.assertEqual(_case_from_em(self.evidence(bad),'B02')['stage_status'],'FAIL')
    def test_v2_mismatched_packaged_diagnostic_is_a_report_failure(self):
        from sqe_studio.cycle_qualification import _case_from_em
        data=self.evidence(record([field()],[auxiliary()]))
        data['em/native/native_palace_solve-upstream-field-probe.json']=json.dumps(p._public_result('TAMPERED')).encode()
        self.assertEqual(_case_from_em(data,'B02')['stage_status'],'FAIL')
    def test_legacy_v1_report_remains_readable(self):
        from sqe_studio.cycle_qualification import _case_from_em
        r=record([field()]);r['schema']=p.LEGACY_SCHEMA
        r.pop('cycle_role_counts');r['cycles'][0].pop('role')
        for assoc in r['cycles'][0]['blocks'][0].values():
            for key in p.AUXILIARY:assoc.pop(key)
        case=_case_from_em(self.evidence(r),'B02')
        self.assertEqual(case['stage_status'],'BLOCKED')
        self.assertEqual(case['measurements']['upstream_vtk_diagnostic']['complex_E_declared_by_cycle'],[True])
    def test_fixture_round_trip_under_windows_default_encoding(self):
        from sqe_studio.cycle_qualification import _case_from_em
        diagnostic=record([field()],[auxiliary()])
        original=Path.read_text
        def windows_default(path,encoding=None,errors=None):
            return original(path,encoding=encoding or 'cp1252',errors=errors)
        with patch.object(Path,'read_text',new=windows_default):
            data=self.evidence(diagnostic)
            self.assertIn('\u03ba_ext[1]',data['em/native/native_palace_solve-port-Q.csv'].decode('utf-8'))
            self.assertEqual(_case_from_em(data,'B02')['stage_status'],'BLOCKED')
    def test_corrupt_kappa_header_fails_even_with_matching_inventory_hash(self):
        from sqe_studio.cycle_qualification import _case_from_em
        data=self.evidence(record([field()],[auxiliary()]))
        name='em/native/native_palace_solve-port-Q.csv'
        data[name]=data[name].decode('utf-8').replace('\u03ba','\u00ce\u00ba').encode('utf-8')
        manifest_name='em/native/native_palace_solve-manifest.json'
        manifest=json.loads(data[manifest_name])
        port=next(row for row in manifest['artifacts'] if row['name'].endswith('/port-Q.csv'))
        port['sha256']=hashlib.sha256(data[name]).hexdigest()
        data[manifest_name]=json.dumps(manifest).encode('utf-8')
        result=_case_from_em(data,'B02')
        self.assertEqual(result['stage_status'],'FAIL')
        self.assertEqual(result['failure_reason'],'INVALID_NATIVE_SCALAR_EVIDENCE')




if __name__ == '__main__':
    unittest.main()
