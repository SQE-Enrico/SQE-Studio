"""Saved-run security and scalar DTO checks; no claimed Palace execution.

Actual VTK analytic checks live in the selectable field_compare native task.
"""
from copy import deepcopy
import hashlib
import http.cookiejar
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

from sqe_studio.contracts import digest
from sqe_studio.eda import upstream_field_compare as p
from sqe_studio.orchestration.artifacts import ArtifactInvalid
from sqe_studio.testing.native_overlap import fixture_model

ROOT=Path(__file__).resolve().parents[2]


def snapshot(root,model,*,revision=None,study='FieldFixture',label='left'):
    """Deliberately non-VTK bytes: only structural/hash tests may use them."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    files={'sqe_em/sqe_em.msh':'SOFTWARE_ONLY_NOT_GMSH '+label,
        'sqe_em/sqe_em.json':json.dumps({'Problem':{'Type':'Eigenmode','Output':'outputFiles'},
            'Model':{'Mesh':'sqe_em.msh','L0':1.},'Solver':{'Eigenmode':{'N':1,'Save':1}}}),
        'sqe_em/outputFiles/eig.csv':'m,Re{f} (GHz),Q\n1,5.9,1000\n',
        'sqe_em/outputFiles/paraview/eigenmode/eigenmode.pvd':'SOFTWARE_ONLY_NOT_VTK'}
    for name,content in files.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding='utf-8')
    project=digest(model);revision=revision or project[:32]
    manifest={'schema':'sqe.artifact.v1','engine':'sqdmetal_palace','kind':'eigenmode',
        'artifact_type':'palace.eigenmodes','engine_version':'SOFTWARE_TEST_ONLY',
        'revision_id':revision,'project_digest':project,'study_id':study,
        'scientific_status':'review_required','fabrication_status':'HOLD','parents':[],
        'provenance':{'used_revision':revision,'used_project_sha256':project},
        'artifacts':[{'name':name,'bytes':(root/name).stat().st_size,
                     'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in files]}
    (root/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    return manifest


def recorded():
    r=p._base(p.RECORDED,'DISCRETE_STATISTIC_ONLY_NOT_MODE_IDENTIFICATION')
    # Retain all dev71 scalar/provenance checks against its legacy DTO.
    r['schema']=p.LEGACY_SCHEMA;r.pop('grid_diagnostics')
    r['sources']=[];r['directions']=[];r['vtk_version']='9.3.1';r['mac_gap']=0.
    for index in (0,1):
        r['sources'].append({'result_manifest_sha256':'a'*64,'revision_id':'b'*32,
            'project_sha256':'c'*64,'study_id':'FieldFixture','mesh_sha256':str(index+1)*64,
            'eig_sha256':'d'*64,'pvd_sha256':'e'*64,'cycle_index':0,'mpi_piece_count':4,
            'piece_sha256':['f'*64]*4,'cell_count':5 if index==0 else 40,'point_count':48,
            'ghost_cells_removed':0,'declared_length_unit_m':1.})
        r['directions'].append({'sampling_mesh':'right' if index else 'left',
            'mac':1.,'relative_phase_rad':.8,'sample_count':5 if index==0 else 40,
            'coverage_fraction':1.,'sampled_volume_m3_assuming_declared_units':1.})
    return r


class ScalarBoundary(unittest.TestCase):
    def test_valid_record_is_bounded_and_science_unresolved(self):
        self.assertIs(p.validate_result(recorded())['field_values_exported'],False)
        self.assertEqual(p.validate_result(p._base())['status'],'BLOCKED')
    def test_no_scientific_promotion(self):
        for key,value in [('physical_mode_identity','VERIFIED'),('mesh_convergence','PASS'),
            ('fabrication','GO'),('em_to_hamiltonian','PASS'),('scientific_qualification','PASS'),
            ('field_values_exported',True),('material_weighting','PERMITTIVITY')]:
            bad=recorded();bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_result(bad)
    def test_no_private_vectors_paths_or_extra_metadata(self):
        for where in ('top','source','direction'):
            bad=recorded();target={'top':bad,'source':bad['sources'][0],'direction':bad['directions'][0]}[where]
            target['coordinates']=[[1,2,3]]
            with self.subTest(where=where),self.assertRaises(ValueError):p.validate_result(bad)
    def test_nonfinite_incomplete_and_out_of_range_statistics_rejected(self):
        for key,value in [('mac',float('nan')),('mac',1.001),('mac',True),
            ('coverage_fraction',.99),('sample_count',True),('relative_phase_rad',4.),
            ('sampled_volume_m3_assuming_declared_units',0.)]:
            bad=recorded();bad['directions'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):p.validate_result(bad)
    def test_mesh_and_source_identity_checks(self):
        for key,value in [('mesh_sha256','2'*64),('cycle_index',True),('mpi_piece_count',17),
                          ('result_manifest_sha256',1),('study_id',True),('declared_length_unit_m',0.)]:
            bad=recorded();bad['sources'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_result(bad)
    def test_directional_gap_cannot_be_forged(self):
        bad=recorded();bad['mac_gap']=.1
        with self.assertRaises(ValueError):p.validate_result(bad)
    def test_blocked_or_failed_output_cannot_contain_numeric_evidence(self):
        for status in ('BLOCKED','FAIL'):
            bad=recorded();bad['status']=status
            with self.subTest(status=status),self.assertRaises(ValueError):p.validate_result(bad)
    def test_undefined_phase_at_zero_correlation(self):
        good=recorded()
        for direction in good['directions']:
            direction.update(mac=0.,relative_phase_rad=None)
        p.validate_result(good)
        good['directions'][0]['relative_phase_rad']=0.
        with self.assertRaises(ValueError):p.validate_result(good)


class ProvenancePreflight(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.roots=(Path(self.temp.name)/'a',Path(self.temp.name)/'b')
        self.models=(fixture_model(1),fixture_model(2))
        self.manifests=[snapshot(r,m,label=str(i)) for i,(r,m) in enumerate(zip(self.roots,self.models))]
        self.assertEqual(self.prepare()['coordinate_assumption'],p.ASSUMPTION)
    def prepare(self,**kwargs):
        return p.prepare_request(self.roots,self.manifests,self.models,('FieldFixture','FieldFixture'),
                                 same_frame=kwargs.pop('same_frame',True),**kwargs)
    def test_explicit_assumption_is_required(self):
        for value in (False,None,1):
            with self.subTest(value=value),self.assertRaisesRegex(p.ComparisonBlocked,'SAME_FRAME'):
                self.prepare(same_frame=value)
    def test_output_indices_cannot_be_boolean_or_negative(self):
        for value in (True,-1,12,'1'):
            with self.subTest(value=value),self.assertRaisesRegex(p.ComparisonBlocked,'CYCLE_SELECTION'):
                self.prepare(cycle_indices=(None,value))
    def test_saved_model_digest_must_match_manifest(self):
        self.models[1]['process']['fixture_only']=False
        with self.assertRaises(ArtifactInvalid):self.prepare()
    def test_full_manifest_hashes_are_checked_before_reader(self):
        (self.roots[0]/'sqe_em/outputFiles/eig.csv').write_text('changed',encoding='utf-8')
        with patch.object(p,'subprocess') as process:
            result=p.compare_verified_fields(self.roots,self.manifests,self.models,('FieldFixture','FieldFixture'),same_frame=True)
        self.assertEqual(result['status'],'FAIL');process.run.assert_not_called()
    def test_disk_manifest_identity_is_not_replaceable_by_supplied_dictionary(self):
        self.manifests[0]['engine_version']='forged'
        with self.assertRaises(ArtifactInvalid):self.prepare()
    def test_oversized_signed_source_is_blocked_before_reading(self):
        self.manifests[0]['artifacts'][0]['bytes']=p.MAX_SOURCE_FILE_BYTES+1
        with self.assertRaisesRegex(p.ComparisonBlocked,'FILE_BUDGET'):self.prepare()
    def test_path_escape_is_rejected(self):
        self.manifests[0]['artifacts'][0]['name']='../outside'
        (self.roots[0]/'RESULT_MANIFEST.json').write_text(json.dumps(self.manifests[0]),encoding='utf-8')
        with self.assertRaises((ArtifactInvalid,ValueError,OSError)):self.prepare()
    def test_worker_timeout_is_bounded_not_an_evidence_success(self):
        with patch.object(p.subprocess,'run',side_effect=subprocess.TimeoutExpired('fixed-worker',90)):
            result=p.compare_verified_fields(self.roots,self.manifests,self.models,('FieldFixture','FieldFixture'),same_frame=True)
        self.assertEqual(result['status'],'BLOCKED');self.assertIn('TIMEOUT',result['reason_code'])
    def test_forged_worker_scientific_result_is_rejected(self):
        bad=recorded();bad['mesh_convergence']='PASS'
        done=subprocess.CompletedProcess([],0,json.dumps(bad))
        with patch.object(p.subprocess,'run',return_value=done):
            result=p.compare_verified_fields(self.roots,self.manifests,self.models,('FieldFixture','FieldFixture'),same_frame=True)
        self.assertEqual(result['status'],'FAIL')
    def test_worker_source_metadata_must_match_verified_parent(self):
        good=recorded()
        for source,manifest,root in zip(good['sources'],self.manifests,self.roots):
            hashes={e['name']:e['sha256'] for e in manifest['artifacts']}
            source.update(result_manifest_sha256=hashlib.sha256((root/'RESULT_MANIFEST.json').read_bytes()).hexdigest(),
                revision_id=manifest['revision_id'],project_sha256=manifest['project_digest'],
                study_id=manifest['study_id'],mesh_sha256=hashes['sqe_em/sqe_em.msh'],
                eig_sha256=hashes['sqe_em/outputFiles/eig.csv'])
        def execute(record):
            with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(record))):
                return p.compare_verified_fields(self.roots,self.manifests,self.models,
                    ('FieldFixture','FieldFixture'),same_frame=True)
        self.assertEqual(execute(good)['status'],p.RECORDED)
        for key,value in [('revision_id','0'*32),('project_sha256','0'*64),('study_id','OtherStudy'),
                          ('mesh_sha256','0'*64),('eig_sha256','0'*64)]:
            bad=deepcopy(good);bad['sources'][0][key]=value
            with self.subTest(key=key):
                self.assertEqual(execute(bad)['reason_code'],'FOREIGN_COMPARISON_SOURCE')
    def test_size_mismatch_is_rejected_before_full_content_reads(self):
        self.manifests[0]['artifacts'][0]['bytes']+=1
        with patch.object(p,'verify_manifest') as verifier:
            with self.assertRaises(ArtifactInvalid):p._check_source(self.roots[0],self.manifests[0])
        verifier.assert_not_called()


def current_recorded():
    result=recorded();result['schema']=p.CELL_SCHEMA;result['grid_diagnostics']=[]
    for index,source in enumerate(result['sources']):
        result['grid_diagnostics'].append({'side':'right' if index else 'left',
            'result_manifest_sha256':source['result_manifest_sha256'],'cycle_index':source['cycle_index'],
            'cell_count':source['cell_count'],'point_count':source['point_count'],
            'nodes_per_cell_min':4,'nodes_per_cell_max':4,'geometry_view':'NATIVE_LINEAR_TETRA',
            'cell_types':[{'vtk_type_id':10,'count':source['cell_count']}]})
    return result


def component_recorded():
    result=current_recorded();result['schema']=p.SCHEMA
    for direction in result['directions']:
        direction['components']=[{'axis':axis,'left_volume_norm_fraction':1. if k==0 else 0.,
            'right_volume_norm_fraction':1. if k==0 else 0.,
            'status':'SAMPLED_COMPONENT_CORRELATION_RECORDED' if k==0 else 'ZERO_OR_UNRESOLVED_COMPONENT_NORM',
            'mac':1. if k==0 else None,'relative_phase_rad':.8 if k==0 else None}
            for k,axis in enumerate(('x','y','z'))]
    return result


class ComponentDiagnosticBoundary(unittest.TestCase):
    def test_v3_bounded_components_keep_all_science_boundaries(self):
        result=p.validate_result(component_recorded())
        self.assertEqual(result['schema'],'sqe.upstream-field-correlation.experimental.v3')
        self.assertEqual(result['physical_mode_identity'],'UNRESOLVED')
        self.assertEqual(result['fabrication'],'HOLD');self.assertFalse(result['field_values_exported'])
    def test_legacy_versions_never_acquire_component_values(self):
        for result in (recorded(),current_recorded()):
            p.validate_result(result);self.assertNotIn('components',result['directions'][0])
            result['directions'][0]['components']=component_recorded()['directions'][0]['components']
            with self.assertRaises(ValueError):p.validate_result(result)
    def test_axes_counts_and_private_extra_fields_are_rejected(self):
        for change in (lambda r:r.pop(),lambda r:r[0].update(axis='y'),
                lambda r:r[0].update(axis='<script>'),lambda r:r[0].update(coordinates=[[1,2,3]])):
            result=component_recorded();change(result['directions'][0]['components'])
            with self.assertRaises(ValueError):p.validate_result(result)
    def test_fractions_are_finite_nonnegative_nonboolean_and_sum_to_one(self):
        for value in (float('nan'),float('inf'),True,-.1,1.1,.8):
            result=component_recorded();result['directions'][0]['components'][0]['left_volume_norm_fraction']=value
            with self.subTest(value=value),self.assertRaises(ValueError):p.validate_result(result)
    def test_zero_norm_must_not_invent_mac_or_phase(self):
        for key,value in (('mac',0.),('relative_phase_rad',0.),('status','SAMPLED_COMPONENT_CORRELATION_RECORDED')):
            result=component_recorded();result['directions'][0]['components'][1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_result(result)
    def test_zero_correlation_with_defined_norm_has_undefined_phase(self):
        result=component_recorded()
        for direction in result['directions']:
            direction.update(mac=0.,relative_phase_rad=None)
            direction['components'][0].update(mac=0.,relative_phase_rad=None)
        p.validate_result(result)
        result['directions'][0]['components'][0]['relative_phase_rad']=0.
        with self.assertRaises(ValueError):p.validate_result(result)
    def cancellation(self):
        result=component_recorded()
        for direction in result['directions']:
            direction.update(mac=0.,relative_phase_rad=None)
            for k,phase in enumerate((0.,math.pi)):
                direction['components'][k].update(left_volume_norm_fraction=.5,right_volume_norm_fraction=.5,
                    status='SAMPLED_COMPONENT_CORRELATION_RECORDED',mac=1.,relative_phase_rad=phase)
        return result
    def test_component_phase_cancellation_is_consistent_with_vector_zero(self):
        result=self.cancellation();p.validate_result(result)
        self.assertEqual([r['mac'] for r in result['directions'][0]['components']],[1.,1.,None])
    def test_components_cannot_disagree_with_original_vector_mac(self):
        result=self.cancellation();result['directions'][0]['components'][1]['relative_phase_rad']=0.
        with self.assertRaisesRegex(ValueError,'disagrees'):p.validate_result(result)
    def test_component_mac_and_phase_bounds_are_strict(self):
        for key,value in (('mac',True),('mac',1.001),('mac',float('nan')),
                ('relative_phase_rad',None),('relative_phase_rad',4.),('relative_phase_rad',float('inf'))):
            result=component_recorded();result['directions'][0]['components'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):p.validate_result(result)
    def test_blocked_v3_has_no_numeric_component_or_direction_data(self):
        self.assertEqual(p.validate_result(p._base())['directions'],[])
        bad=component_recorded();bad['status']='BLOCKED'
        with self.assertRaises(ValueError):p.validate_result(bad)


class FrequencyCriterionSensitivity(unittest.TestCase):
    def setUp(self):
        from sqe_studio.feedback_qualification import _checked_members
        self.reference=ROOT/'tests/fixtures/em/dev74-recorded-reference.zip'
        self.members=_checked_members(self.reference);self.observations=[];self.metrics=[]
        for name in ('native_palace_solve','native_palace_refinement'):
            item=json.loads(self.members['em/native/'+name+'-manifest.json'])
            self.observations.append(item['observation']);self.metrics.append(item['solver_metrics'])
    def test_recorded_frequency_fails_two_and_passes_three_without_physics_go(self):
        from sqe_studio.interop.em_convergence import frequency_tolerance_sensitivity
        result=frequency_tolerance_sensitivity(self.observations,self.metrics,recorded_tolerance=.02,selected_tolerance=.03)
        self.assertEqual([r['last_interval_threshold_met'] for r in result['evaluations']],[False,True])
        self.assertTrue(result['analysis_criterion_differs_from_recorded'])
        self.assertTrue(result['development_may_continue']);self.assertFalse(result['new_native_execution'])
        self.assertEqual(result['mesh_convergence'],'NOT_ESTABLISHED');self.assertEqual(result['fabrication_status'],'HOLD')
    def test_what_if_never_rewrites_original_tolerance_or_report_bytes(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip
        before=self.reference.read_bytes();result=analyze_report_zip(self.reference,frequency_tolerance=.03)
        self.assertEqual(result['relative_tolerance'],.02);self.assertFalse(result['last_step_numeric_threshold_met'])
        self.assertEqual(result['frequency_tolerance_sensitivity']['selected_analysis_relative_tolerance'],.03)
        self.assertEqual(self.reference.read_bytes(),before);self.assertEqual(result['native_execution'],'NOT_RUN')
    def test_invalid_criteria_duplicate_or_excessive_choices_are_rejected(self):
        from sqe_studio.interop.em_convergence import frequency_tolerance_sensitivity, ConvergenceEvidenceError
        for values in ((),(.02,.02),(float('nan'),),(True,),(-.01,),(.21,),tuple(.001*(i+1) for i in range(9))):
            with self.subTest(values=values),self.assertRaises(ConvergenceEvidenceError):
                frequency_tolerance_sensitivity(self.observations,self.metrics,thresholds=values)
        for value in (True,'0.03',float('inf'),0.,.3):
            with self.subTest(value=value),self.assertRaises(ConvergenceEvidenceError):
                frequency_tolerance_sensitivity(self.observations,self.metrics,selected_tolerance=value)
    def test_custom_analysis_criterion_is_added_without_replacing_recorded_one(self):
        from sqe_studio.interop.em_convergence import frequency_tolerance_sensitivity
        result=frequency_tolerance_sensitivity(self.observations,self.metrics,recorded_tolerance=.02,selected_tolerance=.01)
        self.assertEqual([r['relative_tolerance'] for r in result['evaluations']],[.02,.03,.01])
        self.assertEqual(result['recorded_relative_tolerance'],.02)
    def test_inclusive_boundary_reuses_actual_scalar_drift(self):
        from sqe_studio.interop.em_convergence import convergence_series, frequency_tolerance_sensitivity
        actual=convergence_series(self.observations,self.metrics)['adjacent_differences'][0]['relative_difference']
        result=frequency_tolerance_sensitivity(self.observations,self.metrics,
            thresholds=(actual,math.nextafter(actual,0.)))
        self.assertEqual([r['last_interval_threshold_met'] for r in result['evaluations']],[True,False])
    def write(self,members,folder):
        from sqe_studio.testing.runner import _publish
        path=folder/'recorded.zip';_publish(path,{k:v for k,v in members.items() if k!='INTEGRITY.json'});return path
    def test_recorded_tolerance_is_read_instead_of_assumed(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip
        # Deliberately modified software fixture, never an accepted native run.
        members=dict(self.members);name='em/native/convergence-series.json';series=json.loads(members[name])
        series['relative_tolerance']=.03;series['last_step_numeric_threshold_met']=True
        series['adjacent_differences'][0]['numeric_tolerance_met']=True
        members[name]=json.dumps(series).encode()
        with tempfile.TemporaryDirectory() as td:
            result=analyze_report_zip(self.write(members,Path(td)))
        self.assertEqual(result['relative_tolerance'],.03);self.assertTrue(result['last_step_numeric_threshold_met'])
        self.assertEqual(result['native_execution'],'NOT_RUN')
    def test_inconsistent_or_invalid_stored_scalar_declaration_is_rejected(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError
        for edit in (lambda s:s.update(relative_tolerance=None),lambda s:s.update(relative_tolerance=.03),
                lambda s:s['points'][0].update(frequency_GHz=1.),lambda s:s.update(fabrication_status='GO')):
            members=dict(self.members);name='em/native/convergence-series.json';series=json.loads(members[name]);edit(series)
            members[name]=json.dumps(series).encode()
            with tempfile.TemporaryDirectory() as td,self.assertRaises(ConvergenceEvidenceError):
                analyze_report_zip(self.write(members,Path(td)))
    def test_cli_accepts_explicit_three_percent_as_analysis_only(self):
        done=subprocess.run([sys.executable,str(ROOT/'tools/review_em_evidence.py'),str(self.reference),
            '--frequency-tolerance','0.03'],capture_output=True,text=True,timeout=15)
        self.assertEqual(done.returncode,0,done.stderr);result=json.loads(done.stdout)
        self.assertEqual(result['relative_tolerance'],.02)
        self.assertEqual(result['frequency_tolerance_sensitivity']['selected_analysis_relative_tolerance'],.03)
        self.assertEqual(result['native_execution'],'NOT_RUN')
    def test_automatic_collector_labels_frequency_review_as_replay(self):
        from sqe_studio.testing.task_worker import execute
        with tempfile.TemporaryDirectory() as td,patch('sqe_studio.testing.task_worker._run',return_value=(0,'software protocol fixture\nRan 1 test\n\nOK\n',.01)):
            result=execute('targeted',ROOT,Path(td)/'task')
        row=next(s for s in result['substeps'] if s['id']=='recorded_em_frequency_criteria')
        self.assertEqual(result['status'],'PASS');self.assertEqual(row['native_execution'],'NOT_RUN')
        self.assertEqual(row['source_runtime'],'0.1.1.dev74')
        self.assertEqual([r['last_interval_threshold_met'] for r in row['frequency_tolerance_sensitivity']['evaluations']],[False,True])
    def test_missing_recorded_input_is_a_collector_failure_not_an_imagined_pass(self):
        from sqe_studio.testing.task_worker import execute
        with tempfile.TemporaryDirectory() as td,patch('sqe_studio.testing.task_worker._run',return_value=(0,'software protocol fixture\nRan 1 test\n\nOK\n',.01)):
            result=execute('targeted',Path(td),Path(td)/'task')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['substeps'][-1]['native_execution'],'NOT_RUN')


class GridDiagnosticBoundaries(unittest.TestCase):
    def test_legacy_results_have_no_invented_cell_metadata(self):
        result=p.validate_result(recorded());self.assertEqual(result['schema'],p.LEGACY_SCHEMA)
        self.assertNotIn('grid_diagnostics',result)
    def test_v2_native_and_mixed_linear_geometry_records(self):
        result=current_recorded();p.validate_result(result)
        g=result['grid_diagnostics'][0]
        g['cell_types']=[{'vtk_type_id':10,'count':4},{'vtk_type_id':71,'count':1}]
        g['geometry_view']='ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW'
        p.validate_result(result)
    def test_geometry_blocker_retains_only_bounded_categories(self):
        grid=current_recorded()['grid_diagnostics'][0]
        grid.update(nodes_per_cell_min=10,nodes_per_cell_max=10,
            geometry_view='UNSUPPORTED_CELL_GEOMETRY',cell_types=[{'vtk_type_id':71,'count':5}])
        result=p._base('BLOCKED','LINEAR_TETRAHEDRA_REQUIRED',grid_diagnostics=[grid])
        self.assertEqual(p.validate_result(result)['sources'],[])
        self.assertEqual(result['directions'],[])
    def test_linear_view_claims_and_node_ranges_must_be_proved(self):
        for key,value in [('geometry_view','ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW'),
            ('nodes_per_cell_max',10),('nodes_per_cell_min',True),('nodes_per_cell_min',0)]:
            result=current_recorded();result['grid_diagnostics'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_result(result)
    def test_cell_counts_duplicates_and_type_ids_cannot_be_forged(self):
        for types in ([{'vtk_type_id':10,'count':4}],
                      [{'vtk_type_id':10,'count':3},{'vtk_type_id':10,'count':2}],
                      [{'vtk_type_id':256,'count':5}],
                      [{'vtk_type_id':10,'count':True}]):
            result=current_recorded();result['grid_diagnostics'][0]['cell_types']=types
            with self.subTest(types=types),self.assertRaises(ValueError):p.validate_result(result)
    def test_cell_metadata_is_bound_to_the_source_and_side(self):
        for key,value in [('side','right'),('result_manifest_sha256','0'*64),('point_count',49),('cycle_index',1)]:
            result=current_recorded();result['grid_diagnostics'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_result(result)
    def test_grid_metadata_cannot_export_private_fields(self):
        result=current_recorded();result['grid_diagnostics'][0]['coordinates']=[[1,2,3]]
        with self.assertRaises(ValueError):p.validate_result(result)
    def test_legacy_vocabulary_cannot_be_extended_silently(self):
        result=recorded();result['grid_diagnostics']=[]
        with self.assertRaises(ValueError):p.validate_result(result)
    def test_two_grid_records_required_before_numeric_result(self):
        for count in (0,1):
            result=current_recorded();result['grid_diagnostics']=result['grid_diagnostics'][:count]
            with self.subTest(count=count),self.assertRaises(ValueError):p.validate_result(result)




class NativeArrayAPIProtocols(unittest.TestCase):
    def test_current_getter_is_preferred(self):
        marker=object()
        class Current:
            def GetCellTypes(self):return marker
            def GetCellTypesArray(self):raise AssertionError('Retired getter called')
        self.assertIs(p._cell_type_array(Current()),marker)
    def test_old_overload_uses_legacy_array(self):
        marker=object()
        class Older:
            def GetCellTypes(self,distinct_types):raise AssertionError('Wrong overload')
            def GetCellTypesArray(self):return marker
        self.assertIs(p._cell_type_array(Older()),marker)
    def test_absent_or_null_arrays_have_a_fixed_blocker(self):
        class Empty:
            def GetCellTypes(self):return None
            def GetCellTypesArray(self):return None
        for grid in (object(),Empty()):
            with self.subTest(grid=type(grid).__name__),self.assertRaisesRegex(p.ComparisonBlocked,'CELL_TYPES_ARRAY_UNAVAILABLE'):
                p._cell_type_array(grid)
    def test_null_current_getter_can_use_legacy_array(self):
        marker=object()
        class Compatible:
            def GetCellTypes(self):return None
            def GetCellTypesArray(self):return marker
        self.assertIs(p._cell_type_array(Compatible()),marker)
    def test_unexpected_getter_failures_are_not_hidden(self):
        class Failed:
            def GetCellTypes(self):raise RuntimeError('Injected getter failure')
            def GetCellTypesArray(self):raise AssertionError('Unexpected fallback')
        with self.assertRaisesRegex(RuntimeError,'Injected getter failure'):p._cell_type_array(Failed())


class NativeFailurePrivacy(unittest.TestCase):
    def test_diagnostic_drops_exception_text_objects_and_private_paths(self):
        from sqe_studio.testing.native_overlap import _failure_diagnostic
        ns={}
        exec(compile("def fail():\n    raise AttributeError('SECRET_PRIVATE_MESSAGE', name='GetDataType', obj=None)\n",
                     '/private/SECRET_USER/native_overlap.py','exec'),ns)
        try:ns['fail']()
        except AttributeError as exc:result=_failure_diagnostic(exc,'SHARED_GEOMETRY_VIEW')
        text=json.dumps(result)
        self.assertNotIn('SECRET',text);self.assertNotIn('/private',text)
        self.assertEqual(result['attribute'],'GetDataType');self.assertEqual(result['attribute_object_type'],'NoneType')
        self.assertEqual(result['frames'][-1]['file'],'native_overlap.py')
    def test_unknown_attribute_and_stage_use_fixed_categories(self):
        from sqe_studio.testing.native_overlap import _failure_diagnostic
        exc=AttributeError('SECRET_MESSAGE',name='SECRET_ATTRIBUTE',obj=object())
        result=_failure_diagnostic(exc,'/private/SECRET_STAGE')
        self.assertEqual(result['stage'],'UNKNOWN_STAGE');self.assertEqual(result['attribute'],'OTHER_ATTRIBUTE')
        self.assertEqual(result['attribute_object_type'],'OTHER');self.assertNotIn('SECRET',json.dumps(result))
    def test_diagnostic_frames_are_bounded_and_never_export_locals(self):
        from sqe_studio.testing.native_overlap import _failure_diagnostic
        ns={}
        exec(compile("def recurse(n):\n    secret='SECRET_LOCAL'\n    if n: return recurse(n-1)\n    raise AttributeError('SECRET_TEXT', name='GetCellTypesArray')\n",
                     '/private/SECRET_USER/upstream_field_compare.py','exec'),ns)
        try:ns['recurse'](15)
        except AttributeError as exc:result=_failure_diagnostic(exc,'MODERN_METADATA_PROTOCOL')
        self.assertEqual(len(result['frames']),8);self.assertNotIn('SECRET',json.dumps(result))
        self.assertTrue(all(set(f)=={'file','function','line'} for f in result['frames']))
    def test_failed_native_fixture_attaches_context_and_stays_failed(self):
        from sqe_studio.testing import native_overlap as native
        private=type('SECRET_EXCEPTION',(Exception,),{})
        for error in (AttributeError('SECRET',name='GetCellTypesArray'),private('SECRET')):
            with self.subTest(kind=type(error).__name__),patch.object(native.util,'find_spec',return_value=object()), \
                 patch.object(native,'analytic_grid',side_effect=error):result=native.run_workflow()
            self.assertEqual(result['status'],'FAIL');self.assertEqual(result['substeps'],[])
            self.assertEqual(result['failure_diagnostic']['stage'],'ANALYTIC_PAIR')
            if isinstance(error,AttributeError):self.assertEqual(result['failure_diagnostic']['attribute'],'GetCellTypesArray')
            else:self.assertEqual(result['reason'],'UPSTREAM_MAC_FIXTURE_OTHER')
            self.assertEqual(result['native_palace_execution'],'NOT_RUN');self.assertNotIn('SECRET',json.dumps(result))


class NativeEMEvidenceReplay(unittest.TestCase):
    """Recorded report replay and generic software negatives, never new solves."""
    def setUp(self):
        from sqe_studio.feedback_qualification import _checked_members
        self.reference=ROOT/'tests/fixtures/em/dev74-recorded-reference.zip'
        self.original=_checked_members(self.reference)
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name);self.sequence=0
    def write(self, members=None):
        from sqe_studio.testing.runner import _publish
        self.sequence+=1;path=self.folder/('report-'+str(self.sequence)+'.zip')
        _publish(path,{k:v for k,v in (members or self.original).items() if k!='INTEGRITY.json'})
        return path
    def change(self, name, function):
        members=dict(self.original);value=json.loads(members[name]);function(value)
        members[name]=json.dumps(value).encode();return members
    def analyze(self, members=None):
        from sqe_studio.interop.em_convergence import analyze_report_zip
        return analyze_report_zip(self.write(members))
    def pair(self):
        prefix='em/native/';observations=[];metrics=[]
        for name in ('native_palace_solve','native_palace_refinement'):
            item=json.loads(self.original[prefix+name+'-manifest.json'])
            observations.append(item['observation']);metrics.append(item['solver_metrics'])
        return observations,metrics,json.loads(self.original[prefix+'upstream-field-correlation.json'])
    def test_original_reference_is_hash_bound_and_replay_is_not_native_execution(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, FIELD_SCHEMA
        result=analyze_report_zip(self.reference)
        self.assertEqual(result['source_report_sha256'],'56d9dc69b5f5edd3e7e46cda9e51950d5808b054c673994617691606c232f7be')
        self.assertEqual(result['schema'],FIELD_SCHEMA);self.assertEqual(result['source_runtime'],'0.1.1.dev74')
        self.assertEqual(result['native_execution'],'NOT_RUN')
        self.assertEqual(result['source_native_execution'],'RECORDED_PASS')
        self.assertEqual(result['analysis_kind'],'RECORDED_REPORT_REPLAY_NO_NATIVE_EXECUTION')
        self.assertEqual(result['field_evidence_status'],p.RECORDED)
        self.assertEqual(result['field_comparison']['result'],self.pair()[2])
        self.assertFalse(result['last_step_numeric_threshold_met'])
        self.assertEqual(result['mesh_convergence'],'NOT_ESTABLISHED')
    def test_scalar_only_v1_has_no_invented_field_evidence(self):
        from sqe_studio.interop.em_convergence import convergence_series, SCHEMA
        obs,metrics,_=self.pair();result=convergence_series(obs,metrics)
        self.assertEqual(result['schema'],SCHEMA);self.assertNotIn('field_comparison',result)
        self.assertEqual(result['mode_identity'],'UNRESOLVED_no_verified_field_overlap')
    def test_mac_one_and_small_frequency_drift_never_qualify_science(self):
        from sqe_studio.interop.em_convergence import convergence_series
        obs,metrics,corr=self.pair();obs[1]['modes'][0]['frequency_GHz']=obs[0]['modes'][0]['frequency_GHz']*1.001
        for d in corr['directions']:d['mac']=1.
        corr['mac_gap']=0.
        result=convergence_series(obs,metrics,field_correlation=corr)
        self.assertTrue(result['last_step_numeric_threshold_met'])
        self.assertEqual(result['mode_identity'],'UNRESOLVED_PHYSICAL_MODE_REVIEW_REQUIRED')
        self.assertEqual(result['scientific_qualification'],'not_established')
        self.assertEqual(result['fabrication_status'],'HOLD')
        self.assertIn('PHYSICAL_MODE_IDENTITY_UNRESOLVED',result['unresolved_requirements'])
    def test_swapped_or_foreign_field_pair_is_rejected(self):
        from sqe_studio.interop.em_convergence import convergence_series, ConvergenceEvidenceError
        for swapped in (False,True):
            obs,metrics,corr=self.pair()
            if swapped:obs.reverse();metrics.reverse();metrics[0]['mesh_elements_3d']=1
            else:corr['sources'][0]['result_manifest_sha256']='0'*64;corr['grid_diagnostics'][0]['result_manifest_sha256']='0'*64
            with self.subTest(swapped=swapped),self.assertRaises(ConvergenceEvidenceError):
                convergence_series(obs,metrics,field_correlation=corr)
    def test_blocked_or_failed_fields_remain_unavailable_without_numbers(self):
        from sqe_studio.interop.em_convergence import convergence_series
        for status in ('BLOCKED','FAIL'):
            obs,metrics,_=self.pair();result=convergence_series(obs,metrics,field_correlation=p._base(status))
            self.assertEqual(result['field_evidence_status'],status)
            self.assertEqual(result['field_comparison']['result']['directions'],[])
            self.assertIn('SAMPLED_FIELD_COMPARISON_NOT_RECORDED',result['unresolved_requirements'])
    def test_blocked_grid_metadata_cannot_belong_to_a_foreign_pair(self):
        from sqe_studio.interop.em_convergence import convergence_series, ConvergenceEvidenceError
        obs,metrics,corr=self.pair();grid=corr['grid_diagnostics'][0];grid['result_manifest_sha256']='0'*64
        with self.assertRaises(ConvergenceEvidenceError):
            convergence_series(obs,metrics,field_correlation=p._base(grid_diagnostics=[grid]))
    def test_third_scalar_mesh_does_not_expand_first_field_pair_scope(self):
        from sqe_studio.interop.em_convergence import convergence_series
        obs,metrics,corr=self.pair();third=deepcopy(obs[1]);third['manifest_sha256']='f'*64
        third['modes'][0]['frequency_GHz']*=1.001;obs.append(third)
        metrics.append({**metrics[1],'mesh_elements_3d':2*metrics[1]['mesh_elements_3d']})
        result=convergence_series(obs,metrics,field_correlation=corr)
        self.assertEqual(result['field_comparison']['to_point'],2)
        self.assertIn('FIELD_PAIR_DOES_NOT_COVER_LAST_SCALAR_INTERVAL',result['unresolved_requirements'])
    def test_field_evidence_is_copied_and_validator_rejects_promotion_or_private_values(self):
        from sqe_studio.interop.em_convergence import convergence_series, ConvergenceEvidenceError
        obs,metrics,corr=self.pair();result=convergence_series(obs,metrics,field_correlation=corr)
        corr['directions'][0]['mac']=0.;self.assertNotEqual(result['field_comparison']['result']['directions'][0]['mac'],0.)
        for key,value in [('fabrication','GO'),('coordinates',[[1,2,3]]),('scientific_qualification','PASS')]:
            bad=deepcopy(self.pair()[2]);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ConvergenceEvidenceError):
                convergence_series(obs,metrics,field_correlation=bad)
    def test_partial_coverage_and_nonfinite_samples_cannot_enter_series(self):
        from sqe_studio.interop.em_convergence import convergence_series, ConvergenceEvidenceError
        for key,value in [('coverage_fraction',.9),('mac',float('nan'))]:
            obs,metrics,corr=self.pair();corr['directions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ConvergenceEvidenceError):
                convergence_series(obs,metrics,field_correlation=corr)
    def test_standalone_native_envelope_is_still_supported(self):
        members={k[3:]:v for k,v in self.original.items() if k.startswith('em/')}
        result=self.analyze(members)
        self.assertEqual(result['field_evidence_status'],p.RECORDED)
        self.assertIsNone(result['source_runtime']);self.assertEqual(result['native_execution'],'NOT_RUN')
    def test_old_native_report_without_field_comparison_keeps_v1(self):
        members={k[3:]:v for k,v in self.original.items() if k.startswith('em/') and not k.endswith('upstream-field-correlation.json')}
        report=json.loads(members['QUALIFICATION.json'])
        report['stages']=[s for s in report['stages'] if s['id']!='upstream_field_correlation']
        members['QUALIFICATION.json']=json.dumps(report).encode()
        result=self.analyze(members)
        self.assertEqual(result['schema'],'sqe.em-convergence-evidence.v1')
        self.assertNotIn('field_comparison',result)
    def test_rehashed_but_modified_native_deck_or_eigenvalue_bytes_are_rejected(self):
        from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
        for suffix in ('eig.csv','palace-deck.json'):
            members=dict(self.original);name='em/native/native_palace_solve-'+suffix;members[name]+=b' '
            with self.subTest(suffix=suffix),self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_field_sources_must_match_recorded_inventory_and_model(self):
        from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
        for key in ('project_sha256','mesh_sha256','eig_sha256','pvd_sha256','piece_sha256'):
            def edit(corr):corr['sources'][0][key]=['0'*64,'1'*64] if key=='piece_sha256' else '0'*64
            members=self.change('em/native/upstream-field-correlation.json',edit)
            with self.subTest(key=key),self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_recorded_observation_and_manifest_identity_must_agree(self):
        from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
        members=self.change('em/native/native_palace_solve-manifest.json',lambda x:x.update(result_manifest_sha256='0'*64))
        with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_worker_and_field_stage_failures_cannot_be_replayed_as_pass(self):
        from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
        for stage in ('native_palace_solve','upstream_field_correlation'):
            def edit(report):next(s for s in report['stages'] if s['id']==stage).update(status='FAIL')
            members=self.change('em/QUALIFICATION.json',edit)
            with self.subTest(stage=stage),self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_selected_envelope_requires_recorded_native_execution_and_cycle_identity(self):
        from sqe_studio.interop.em_convergence import ConvergenceEvidenceError
        def edit(q):next(t for t in q['tasks'] if t['id']=='em_convergence').update(native_execution='NOT_RUN')
        for members in (self.change('QUALIFICATION.json',edit),
                self.change('CYCLE.json',lambda x:x.update(runtime_version='0.1.1.dev999')),
                self.change('CYCLE.json',lambda x:x.update(plan_sha256='0'*64))):
            with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_missing_second_solve_and_unhashed_extra_are_rejected(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError
        members=dict(self.original);del members['em/native/native_palace_refinement-manifest.json']
        with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
        members=dict(self.original);del members['em/native/upstream-field-correlation.json']
        with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
        path=self.write()
        with zipfile.ZipFile(path,'a') as z:z.writestr('extra.txt','unhashed')
        with self.assertRaises(ConvergenceEvidenceError):analyze_report_zip(path)
    def test_unsafe_names_symlink_entries_and_member_budget_are_rejected(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError
        for name in ('../escape','C:escape','./extra'):
            members=dict(self.original);members[name]=b'unsafe'
            members['INTEGRITY.json']=json.dumps({'files':{k:hashlib.sha256(v).hexdigest()
                for k,v in members.items() if k!='INTEGRITY.json'}}).encode()
            self.sequence+=1;unsafe=self.folder/('unsafe-'+str(self.sequence)+'.zip')
            # Build malicious input directly: the production publisher rejects it.
            with zipfile.ZipFile(unsafe,'w') as z:
                for k,v in members.items():z.writestr(k,v)
            with self.subTest(name=name),self.assertRaises(ConvergenceEvidenceError):analyze_report_zip(unsafe)
        path=self.write()
        with zipfile.ZipFile(path,'a') as z:
            entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=0o120777<<16;z.writestr(entry,'../../private')
        with self.assertRaises(ConvergenceEvidenceError):analyze_report_zip(path)
        members=dict(self.original);members['oversized.txt']=b'x'*512001
        with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
    def test_malformed_json_shape_and_archive_are_normalized_to_evidence_errors(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError
        members=dict(self.original);members['QUALIFICATION.json']=b'[]'
        with self.assertRaises(ConvergenceEvidenceError):self.analyze(members)
        path=self.folder/'broken.zip';path.write_bytes(b'not zip')
        with self.assertRaises(ConvergenceEvidenceError):analyze_report_zip(path)
    def test_archive_change_during_review_is_rejected(self):
        from sqe_studio.interop.em_convergence import analyze_report_zip, ConvergenceEvidenceError
        changed=dict(self.original);changed['SUMMARY.md']=b'changed between reads'
        with patch('sqe_studio.feedback_qualification._checked_members',return_value=changed):
            with self.assertRaises(ConvergenceEvidenceError):analyze_report_zip(self.reference)
    def test_cli_is_create_only_and_never_exports_input_path(self):
        command=[sys.executable,str(ROOT/'tools/review_em_evidence.py'),str(self.reference)]
        done=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertEqual(done.returncode,0,done.stderr);self.assertNotIn(str(ROOT),done.stdout)
        self.assertEqual(json.loads(done.stdout)['native_execution'],'NOT_RUN')
        output=self.folder/'analysis.json'
        done=subprocess.run(command+['--output',str(output)],capture_output=True,text=True,timeout=15)
        self.assertEqual(done.returncode,0,done.stderr);before=output.read_bytes()
        done=subprocess.run(command+['--output',str(output)],capture_output=True,text=True,timeout=15)
        self.assertEqual(done.returncode,2);self.assertEqual(output.read_bytes(),before)
    def test_cli_failure_has_no_private_path_or_native_execution(self):
        private=self.folder/'SECRET_PRIVATE_INPUT.zip';private.write_bytes(b'not a report')
        done=subprocess.run([sys.executable,str(ROOT/'tools/review_em_evidence.py'),str(private)],
            capture_output=True,text=True,timeout=15)
        self.assertEqual(done.returncode,2);self.assertNotIn('SECRET',done.stdout+done.stderr)
        self.assertIn('no native execution',done.stderr)


class SavedRunHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqe_studio.server import make_server
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=make_server(Path(cls.temp.name)/'private',0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
        cls.csrf=''
        cls.request('/api/setup',{'setup_token':cls.server.app.setup_file.read_text(encoding='ascii'),
            'email':'m18@example.invalid','password':'M18LocalTemporaryPassword123'})
        status,auth=cls.request('/api/login',{'email':'m18@example.invalid','password':'M18LocalTemporaryPassword123'})
        assert status==200;cls.csrf=auth['csrf']
        status,created=cls.request('/api/projects',{'name':'M18 metadata test','family':'resonator','template_id':'cpw_resonator_v1'})
        assert status==201
        cls.pid=created['id'];cls.revision=created['head'];cls.model=created['model']
        with cls.server.app.store.conn() as db:
            cls.owner=db.execute('SELECT id FROM accounts').fetchone()['id']
        cls.runids=('a'*32,'b'*32);cls.outputs=[]
        for index,run in enumerate(cls.runids):
            folder=cls.server.app.store.root/'native-runs'/cls.pid/run
            folder.mkdir(parents=True)
            cls.server.app.store.put_run(cls.owner,cls.pid,cls.revision,'ResEigen','sqdmetal_palace',folder)
            cls.server.app.store.set_run(run,'completed')
            out=folder/'output';cls.outputs.append(out)
            snapshot(out,cls.model,revision=cls.revision,study='ResEigen',label=str(index))
            (folder/'snapshot.json').write_text(json.dumps({'revision_id':cls.revision,
                'project_digest':digest(cls.model),'project':cls.model}),encoding='utf-8')
        cls.route=f'/api/projects/{cls.pid}/compare-fields'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=4);cls.temp.cleanup()
    @classmethod
    def request(cls,path,data,*,csrf=True,client=None):
        headers={'Content-Type':'application/json'}
        if csrf and cls.csrf:headers['X-CSRF-Token']=cls.csrf
        payload=None if data is None else json.dumps(data).encode('utf-8')
        req=urllib.request.Request(cls.base+path,data=payload,headers=headers,method='POST')
        try:response=(client or cls.client).open(req,timeout=10)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.status,json.loads(response.read())
    def body(self,**changes):
        return dict(left=self.runids[0],right=self.runids[1],experimental_diagnostic=True,
                    same_frame_assumption=True,**changes)
    def test_success_uses_saved_sources_and_returns_bounded_envelope(self):
        with patch.object(p,'compare_verified_fields',return_value=p._base()) as native:
            status,data=self.request(self.route,self.body())
        self.assertEqual(status,200,data);self.assertEqual(data['left']['run_id'],self.runids[0])
        self.assertEqual(data['right']['revision_id'],self.revision)
        self.assertEqual(data['fabrication'],'HOLD');self.assertEqual(native.call_args.args[0],self.outputs)
        self.assertNotIn(str(self.server.app.store.root),json.dumps(data))
    def test_v3_component_response_uses_the_same_authenticated_saved_run_path(self):
        def compare(roots,manifests,models,studies,**kwargs):
            result=component_recorded()
            for i,manifest in enumerate(manifests):
                source=result['sources'][i]
                source.update(revision_id=manifest['revision_id'],project_sha256=manifest['project_digest'],
                    study_id=manifest['study_id'],result_manifest_sha256=hashlib.sha256((roots[i]/'RESULT_MANIFEST.json').read_bytes()).hexdigest())
                result['grid_diagnostics'][i]['result_manifest_sha256']=source['result_manifest_sha256']
            return p.validate_result(result)
        with patch.object(p,'compare_verified_fields',side_effect=compare) as native:
            status,data=self.request(self.route,self.body())
        self.assertEqual(status,200,data);self.assertEqual(data['diagnostic']['schema'],p.SCHEMA)
        self.assertEqual(data['diagnostic']['sources'][0]['result_manifest_sha256'],data['left']['result_manifest_sha256'])
        self.assertEqual(data['diagnostic']['physical_mode_identity'],'UNRESOLVED');native.assert_called_once()
    def test_auth_and_csrf_are_required(self):
        from sqe_studio.server import Handler
        anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # Credential rejection precedes JSON parsing. Do not race a separate
        # body write against an intentionally early connection-close response.
        with patch.object(p,'compare_verified_fields') as native, \
             patch.object(Handler,'json_body',side_effect=AssertionError('Credential gate parsed JSON')) as parser:
            self.assertEqual(self.request(self.route,None,client=anonymous)[0],401)
            self.assertEqual(self.request(self.route,None,csrf=False)[0],403)
        native.assert_not_called();parser.assert_not_called()
    def test_authenticated_empty_payload_is_not_a_valid_comparison(self):
        with patch.object(p,'compare_verified_fields') as native:
            self.assertEqual(self.request(self.route,None)[0],400)
        native.assert_not_called()
    def test_transport_abort_is_not_retried_or_counted_as_a_rejection(self):
        with patch.object(self.client,'open',side_effect=ConnectionAbortedError(10053,'Injected transport error')) as opened:
            with self.assertRaises(ConnectionAbortedError):self.request(self.route,None)
        opened.assert_called_once()
    def test_invalid_optin_paths_indices_and_duplicate_runs_are_rejected(self):
        for key,value in [('same_frame_assumption',False),('experimental_diagnostic',1),
            ('left',self.runids[1]),('right','../outside'),('left_cycle',True),('right_cycle',12),
            ('command','arbitrary'),('root','private')]:
            body=self.body();body[key]=value
            with self.subTest(key=key),patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,body)[0],422);native.assert_not_called()
    def test_hash_tampering_never_enters_native_reader(self):
        path=self.outputs[0]/'sqe_em/sqe_em.msh';raw=path.read_bytes()
        try:
            path.write_bytes(b'changed')
            with patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],409);native.assert_not_called()
        finally:path.write_bytes(raw)
    def test_missing_run_or_foreign_project_does_not_reveal_output(self):
        with patch.object(p,'compare_verified_fields') as native:
            body=self.body();body['left']='c'*32
            self.assertEqual(self.request(self.route,body)[0],404)
            self.assertEqual(self.request(f'/api/projects/{"d"*32}/compare-fields',self.body())[0],404)
        native.assert_not_called()
    def test_incomplete_run_cannot_be_compared(self):
        self.server.app.store.set_run(self.runids[0],'failed')
        try:
            with patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],404);native.assert_not_called()
        finally:self.server.app.store.set_run(self.runids[0],'completed')
    def test_sweep_output_is_not_silently_treated_as_one_field_run(self):
        marker=self.outputs[0].parent/'SWEEP_MANIFEST.json'
        try:
            marker.write_text('{}',encoding='utf-8')
            with patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],422);native.assert_not_called()
        finally:marker.unlink(missing_ok=True)
    def test_snapshot_revision_tampering_blocks_native_work(self):
        path=self.outputs[0].parent/'snapshot.json';raw=path.read_bytes()
        try:
            data=json.loads(raw);data['project']['name']='tampered snapshot'
            path.write_text(json.dumps(data),encoding='utf-8')
            with patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],409);native.assert_not_called()
        finally:path.write_bytes(raw)
    def test_busy_comparison_cannot_launch_another_native_worker(self):
        self.server.app.field_comparison_lock.acquire()
        try:
            with patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],409);native.assert_not_called()
        finally:self.server.app.field_comparison_lock.release()
    def test_source_byte_budget_precedes_archive_content_verification(self):
        path=self.outputs[0]/'RESULT_MANIFEST.json';raw=path.read_bytes()
        try:
            data=json.loads(raw);data['artifacts'][0]['bytes']=p.MAX_SOURCE_FILE_BYTES+1
            path.write_text(json.dumps(data),encoding='utf-8')
            with patch.object(self.server.app.jobs,'_check_completed_artifacts') as archive, \
                 patch.object(p,'compare_verified_fields') as native:
                self.assertEqual(self.request(self.route,self.body())[0],413)
                archive.assert_not_called();native.assert_not_called()
        finally:path.write_bytes(raw)


if __name__=='__main__':unittest.main()
