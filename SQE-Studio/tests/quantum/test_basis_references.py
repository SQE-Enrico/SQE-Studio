"""M17 contract, numerical-diagnostic, report and security tests.

Standard unittest keeps focused development checks usable without pytest.
Fake eigenvalues below are software fixtures, never native scientific evidence.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import zipfile

from sqe_studio.adapters import scqubits_adapter as a
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.contracts import fresh_project, digest
from sqe_studio.testing.catalog import TASKS, PROFILES, resolve_selection, load_plan
from sqe_studio.testing.runner import compare_tasks, _publish
from sqe_studio.feedback_qualification import _checked_members

ROOT = Path(__file__).resolve().parents[2]


def inputs(model='Transmon', **conv):
    values = {'model': model, 'source': 'independent', 'levels': 4,
              'parameters': {'EJ': 15., 'EC': .25, 'ng': 0., 'ncut': 15},
              'parameter_units': {'EJ': 'GHz', 'EC': 'GHz', 'ng': '2e', 'ncut': '1'},
              'convergence': {'enabled': True, 'tolerance_GHz': .01, 'basis_increment': 5, 'steps': 3, **conv}}
    if model == 'Fluxonium':
        values['parameters'] = {'EJ': 8., 'EC': 2., 'EL': .5, 'flux': .5, 'cutoff': 40}
        values['parameter_units'] = {'EJ': 'GHz', 'EC': 'GHz', 'EL': 'GHz', 'flux': 'Phi0', 'cutoff': '1'}
    return values


class FakeQubit:
    calls = []
    def __init__(self, **params):
        self.params = params
        self.calls.append(params.copy())
    def eigenvals(self, evals_count):
        cutoff = self.params.get('ncut', self.params.get('cutoff'))
        residual = cutoff ** -4
        return [0., 5.+residual, 9.7+2*residual, 14.+3*residual][:evals_count]


class BasisDiagnostics(unittest.TestCase):
    def setUp(self):
        FakeQubit.calls = []
        self.scq = types.SimpleNamespace(Transmon=FakeQubit, Fluxonium=FakeQubit)
        self.project = fresh_project('M17 fixture', 'transmon')
    def spec(self, **kw):
        return a._spec(inputs(**kw), self.project)
    def test_four_native_calls_and_fixed_output_truncation(self):
        energies, _, rows = a._execute(self.scq, self.spec())
        self.assertEqual([r['ncut'] for r in FakeQubit.calls], [15,20,25,30])
        self.assertEqual([r['truncated_dim'] for r in FakeQubit.calls], [6]*4)
        self.assertEqual(len(energies), 1)
        self.assertEqual(rows[0]['status'], 'checked_passed')
        self.assertEqual([r['basis_dimension'] for r in rows[0]['curve']], [31,41,51,61])
    def test_nonconvergence_is_retained_instead_of_engine_exception(self):
        _, _, rows = a._execute(self.scq, self.spec(tolerance_GHz=1e-15))
        self.assertEqual(rows[0]['status'], 'checked_failed')
        self.assertEqual(len(rows[0]['curve']), 4)
    def test_fluxonium_counts_oscillator_states(self):
        _, _, rows = a._execute(self.scq, self.spec(model='Fluxonium'))
        self.assertEqual(rows[0]['basis_parameter'], 'cutoff')
        self.assertEqual([r['basis_dimension'] for r in rows[0]['curve']], [40,45,50,55])
    def test_last_two_intervals_define_reported_maximum(self):
        _, _, points = a._execute(self.scq, self.spec())
        r = points[0]
        self.assertEqual(r['max_delta_GHz'], max(x['max_adjacent_delta_GHz'] for x in r['curve'][-2:]))
    def test_legacy_one_step_preserves_raising_behavior(self):
        spec = self.spec(tolerance_GHz=1e-15)
        spec['convergence'].pop('steps')
        with self.assertRaisesRegex(EngineBlocked, 'native basis convergence failed'):
            a._execute(self.scq, spec)
        self.assertEqual(len(FakeQubit.calls), 2)
    def test_rejects_invalid_step_counts(self):
        for steps in (0,5,True,2.5,'3'):
            with self.subTest(steps=steps), self.assertRaises(EngineBlocked):
                self.spec(steps=steps)
    def test_checks_final_cutoff_before_importing_native_library(self):
        v=inputs();v['parameters']['ncut']=70
        with self.assertRaisesRegex(EngineBlocked, 'cutoff limit 80'):
            a._spec(v,self.project)
    def test_sweep_cannot_accidentally_multiply_curve_cost(self):
        v=inputs();v['sweep']={'subsystem':'primary','parameter':'ng','values':[0.,.5],'unit':'2e'}
        with self.assertRaisesRegex(EngineBlocked, 'standalone unswept'):
            a._spec(v,self.project)
    def test_invalid_units_are_still_rejected(self):
        v=inputs();v['parameter_units']['EC']='MHz'
        with self.assertRaises(EngineBlocked):a._spec(v,self.project)
    def test_all_curve_data_serializes_and_failed_numeric_status_is_saved(self):
        fake=types.ModuleType('scqubits');fake.Transmon=FakeQubit
        fake.set_units=lambda unit:None;fake.get_units=lambda:'GHz'
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules,scqubits=fake), \
             patch.object(a,'require_module'), patch.object(a.metadata,'version',return_value='4.3.1'):
            study={'id':'Q','engine':'scqubits','kind':'spectrum','inputs':inputs(tolerance_GHz=1e-15)}
            result=a.run(study,self.project,td)
            spectrum=json.loads((Path(td)/'spectrum.json').read_text())
            self.assertEqual(spectrum['convergence']['numeric_status'],'NUMERICAL_FAIL')
            self.assertEqual(spectrum['convergence']['checked_points'],1)
            self.assertEqual(len(spectrum['convergence']['points'][0]['curve']),4)
            self.assertIn('spectrum.json',result['native_files'])
            self.assertEqual(spectrum['scientific_status'],'review_required')
    def test_nonfinite_native_values_never_become_a_curve(self):
        class Bad(FakeQubit):
            def eigenvals(self,evals_count):return [0.,1.,float('nan'),4.]
        with self.assertRaises(EngineBlocked):
            a._execute(types.SimpleNamespace(Transmon=Bad),self.spec())
    def test_non_ordered_native_values_are_rejected(self):
        class Bad(FakeQubit):
            def eigenvals(self,evals_count):return [0.,2.,1.,4.]
        with self.assertRaises(EngineBlocked):
            a._execute(types.SimpleNamespace(Transmon=Bad),self.spec())
    def test_a_single_good_interval_does_not_pass(self):
        class Plateau(FakeQubit):
            def eigenvals(self,evals_count):
                n=self.params['ncut'];e={15:1.,20:.1,25:.001,30:.001}[n]
                return [0.,5.+e,10.+e,15.+e]
        _,_,r=a._execute(types.SimpleNamespace(Transmon=Plateau),self.spec(tolerance_GHz=.01))
        self.assertEqual(r[0]['curve'][-1]['max_adjacent_delta_GHz'],0.)
        self.assertEqual(r[0]['status'],'checked_failed')


class PlansAndReports(unittest.TestCase):
    def test_all_profiles_have_valid_dependency_closure(self):
        for profile, selection in PROFILES.items():
            with self.subTest(profile=profile):
                plan=resolve_selection(selection)
                self.assertEqual(plan['resolved'][0],'integrity')
                self.assertEqual(len(plan['resolved']),len(set(plan['resolved'])))
                for task in TASKS:
                    if task.id in plan['resolved']:
                        for parent in task.dependencies:
                            self.assertLess(plan['resolved'].index(parent),plan['resolved'].index(task.id))
    def test_unknown_duplicate_and_empty_selections_rejected(self):
        for selection in ([],['unknown'],['quantum','quantum'],['../../private'],'quantum',[True]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):resolve_selection(selection)
    def test_two_mesh_task_subsumes_single_mesh(self):
        plan=resolve_selection(['em','em_convergence'])
        self.assertNotIn('em',plan['resolved'])
        self.assertEqual(plan['superseded'],['em'])
    def test_release_plan_matches_runtime(self):
        plan,digest=load_plan(ROOT)
        self.assertEqual(plan['native_concurrency'],1)
        self.assertEqual(len(digest),64)
    def test_modified_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'automatic_test_plan.json';doc,_=load_plan(ROOT)
            doc['wall_budget_s']=86400;p.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):load_plan(Path(td))
    def test_smaller_selection_never_implies_progress(self):
        old={'selection_sha256':'a','tasks':[{'id':'quantum','status':'FAIL','scope_sha256':'s'},
                                           {'id':'rf','status':'FAIL','scope_sha256':'r'}]}
        new={'selection_sha256':'b','tasks':[{'id':'quantum','status':'PASS','scope_sha256':'s'},
                                           {'id':'rf','status':'SKIPPED_BY_PLAN'}]}
        c=compare_tasks(old,new)
        self.assertFalse(c['same_selection']);self.assertFalse(c['count_delta_is_progress'])
        self.assertEqual(len(c['common_tasks']),1)
    def test_changed_case_is_not_comparable(self):
        a0={'tasks':[{'id':'quantum','status':'PASS','scope_sha256':'a'}]}
        b0={'tasks':[{'id':'quantum','status':'FAIL','scope_sha256':'b'}]}
        self.assertEqual(compare_tasks(a0,b0)['common_tasks'][0]['status'],'NOT_COMPARABLE_SCOPE_CHANGED')
    def test_atomic_report_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.zip';_publish(p,{'SUMMARY.md':b'original'})
            self.assertEqual(_checked_members(p)['SUMMARY.md'],b'original')
            before=p.read_bytes()
            with self.assertRaises(FileExistsError):_publish(p,{'SUMMARY.md':b'changed'})
            self.assertEqual(p.read_bytes(),before)
    def test_tampered_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.zip';_publish(p,{'SUMMARY.md':b'original'})
            with zipfile.ZipFile(p,'a') as z:z.writestr('extra.txt',b'unsigned')
            with self.assertRaises(ValueError):_checked_members(p)
    def test_existing_partial_from_another_run_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.zip';partial=Path(td)/'report.zip.partial'
            partial.write_bytes(b'other interrupted run')
            with self.assertRaises(FileExistsError):_publish(p,{'SUMMARY.md':b'new'})
            self.assertEqual(partial.read_bytes(),b'other interrupted run')
    def test_full_legacy_api_rejects_arbitrary_commands_in_selected_mode(self):
        from sqe_studio.cycle_qualification import run_release_qualification
        with self.assertRaisesRegex(ValueError,'trusted catalog'):
            run_release_qualification(ROOT,ROOT/'qualification-reports/unused.zip',selection=['http'],case_commands={})
    def test_native_quantum_missing_dependency_is_blocked(self):
        from sqe_studio.testing.native_quantum import run_workflow
        with patch('sqe_studio.testing.native_quantum.util.find_spec',return_value=None):
            self.assertEqual(run_workflow()['execution_kind'],'NOT_RUN')
    def test_native_quantum_wrong_pin_is_blocked(self):
        from sqe_studio.testing.native_quantum import run_workflow
        with patch('sqe_studio.testing.native_quantum.util.find_spec',return_value=object()), \
             patch('sqe_studio.testing.native_quantum.metadata.version',return_value='4.9'):
            self.assertEqual(run_workflow()['status'],'BLOCKED')



class SchedulerIntegration(unittest.TestCase):
    def fixture(self, folder):
        root=Path(folder)
        for name in ['src/sqe_studio/testing/task_worker.py','src/sqe_studio/testing/catalog.py','src/sqe_studio/testing/native_quantum.py','src/sqe_studio/adapters/scqubits_adapter.py']:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# fixture only\n')
        shutil.copyfile(ROOT/'automatic_test_plan.json',root/'automatic_test_plan.json')
        (root/'EDA_SOURCE_MANIFEST.json').write_text('{}')
        return root,root/'qualification-reports/SQE-RC14_12-report-0001.zip'
    def test_selected_run_has_signed_partial_scope_and_explicit_exclusions(self):
        from sqe_studio.testing.runner import run_selected
        def worker(args,*unused):
            Path(args[-1]).write_text(json.dumps({'status':'PASS','execution_kind':'SOFTWARE_FIXTURE'}))
            return 0,'software fixture only',.01
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run',side_effect=worker):
            root,path=self.fixture(td);report=run_selected(root,path,['http'])
            self.assertEqual(report['counts']['PASS'],2)
            self.assertEqual(report['execution_counts']['SKIPPED_BY_PLAN'],len(TASKS)-2)
            files=_checked_members(path)
            self.assertIn('TEST_SELECTION.json',files)
            cases=json.loads(files['BENCHMARK_CASE_MATRIX.json'])['cases']
            self.assertTrue(all(r['stage_status']!='PASS' for r in cases))
    def test_failed_integrity_blocks_all_dependent_code(self):
        from sqe_studio.testing.runner import run_selected
        calls=[]
        def worker(args,*unused):
            calls.append(args[2]);Path(args[-1]).write_text('{"status":"FAIL"}');return 0,'fixture',.01
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run',side_effect=worker):
            root,path=self.fixture(td);report=run_selected(root,path,['quantum'])
            self.assertEqual(calls,['integrity'])
            self.assertEqual(report['counts']['FAIL'],1)
            self.assertEqual(report['counts']['BLOCKED'],3)
    def test_cancel_before_start_runs_no_test_and_still_packages(self):
        from sqe_studio.testing.runner import run_selected
        stop=threading.Event();stop.set()
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run') as worker:
            root,path=self.fixture(td);report=run_selected(root,path,['http'],cancel=stop)
            worker.assert_not_called();self.assertEqual(report['execution_counts']['CANCELLED'],2)
            self.assertIn('SUMMARY.md',_checked_members(path))
    def test_timeout_blocks_dependencies_and_is_not_pass(self):
        from sqe_studio.testing.runner import run_selected
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run',return_value=(None,'timeout',.01)):
            root,path=self.fixture(td);report=run_selected(root,path,['http'])
            self.assertEqual(report['execution_counts']['TIMEOUT'],1)
            self.assertEqual(report['counts']['PASS'],0)
    def test_bad_plan_publishes_failure_without_running_code(self):
        from sqe_studio.testing.runner import run_selected
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run') as worker:
            root,path=self.fixture(td);(root/'automatic_test_plan.json').write_text('{}')
            report=run_selected(root,path,['http']);worker.assert_not_called()
            self.assertEqual(report['counts']['FAIL'],1)
            self.assertIn('QUALIFICATION.json',_checked_members(path))
    def test_controller_exception_preserves_diagnostic_zip(self):
        from sqe_studio.testing.runner import run_selected
        with tempfile.TemporaryDirectory() as td, patch('sqe_studio.qualification._run',side_effect=OSError('fixture')):
            root,path=self.fixture(td);report=run_selected(root,path,['http'])
            self.assertEqual(report['counts']['FAIL'],1)
            self.assertIn('CYCLE.json',_checked_members(path))



class NativeEMReportCollection(unittest.TestCase):
    """Use the real qualifier with unavailable backends, never simulated solves."""
    def fixture(self, td):
        root=Path(td)/'source'
        worker=root/'src/sqe_studio/worker.py'
        worker.parent.mkdir(parents=True);worker.write_text('# unreachable software fixture\n')
        folder=root/'qualification-reports/.test-work/em'
        folder.mkdir(parents=True)
        return root,folder

    def test_both_em_profiles_collect_real_blocked_qualifier_outside_source(self):
        from sqe_studio import native_em_qualification as native
        from sqe_studio.testing.task_worker import execute
        original=native.qualify_native_em
        for task,refine in (('em',False),('em_convergence',True)):
            with self.subTest(task=task), tempfile.TemporaryDirectory() as td:
                root,folder=self.fixture(td);destinations=[]
                def observe(source,destination,**kwargs):
                    destinations.append(destination)
                    self.assertFalse(destination.is_relative_to(root))
                    self.assertEqual(kwargs['refine'],refine)
                    self.assertFalse(kwargs['third_mesh'])
                    self.assertEqual(kwargs['time_budget_seconds'],840)
                    kwargs['notify']=None  # Keep fixture stage messages out of real task progress.
                    return original(source,destination,**kwargs)
                with patch.object(native,'qualify_native_em',side_effect=observe), \
                     patch.object(native.importlib.util,'find_spec',return_value=None), \
                     patch.object(native,'mpi_plan',return_value={'mpi_ranks':1,'omp_threads':1}), \
                     patch.object(native,'_run') as solver:
                    result=execute(task,root,folder)
                    solver.assert_not_called()
                self.assertEqual(result['status'],'BLOCKED')
                self.assertEqual(result['native_execution'],'BLOCKED')
                self.assertEqual(result['reason'],'NATIVE_EM_SUBSTEP_BLOCKED')
                self.assertEqual(len(destinations),1)
                self.assertFalse(destinations[0].parent.exists())
                files=_checked_members(folder/'em.zip')
                report=json.loads(files['QUALIFICATION.json'])
                self.assertEqual(result['substeps'],report['stages'])
                self.assertEqual(report['counts']['FAIL'],0)
                self.assertEqual(report['review']['reviewer_id'],'SQEFixedProtocol')
                self.assertEqual(report['review']['review_basis'],
                                 'fixed_release_research_protocol_not_human_review')

    def test_native_qualifier_still_rejects_internal_destination(self):
        from sqe_studio.native_em_qualification import qualify_native_em
        with tempfile.TemporaryDirectory() as td:
            root,folder=self.fixture(td)
            with self.assertRaisesRegex(ValueError,'outside the SQE source tree'):
                qualify_native_em(root,folder/'forbidden.zip',reviewer='SQEFixedProtocol',
                                  acknowledged=True,solve=True)
            self.assertFalse((folder/'forbidden.zip').exists())

    def test_existing_collected_report_is_preserved_without_native_execution(self):
        from sqe_studio.testing.task_worker import execute
        with tempfile.TemporaryDirectory() as td:
            root,folder=self.fixture(td);report=folder/'em.zip';report.write_bytes(b'previous')
            with patch('sqe_studio.native_em_qualification.qualify_native_em') as native:
                with self.assertRaises(FileExistsError):execute('em',root,folder)
                native.assert_not_called()
            self.assertEqual(report.read_bytes(),b'previous')

    def test_bad_native_report_is_rejected_and_temporary_directory_removed(self):
        from sqe_studio.testing.task_worker import execute
        for kind in ('tampered','return_mismatch'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                root,folder=self.fixture(td);destinations=[]
                def native(source,destination,**kwargs):
                    destinations.append(destination)
                    _publish(destination,{'QUALIFICATION.json':b'{"fixture":true}'})
                    if kind=='tampered':
                        with zipfile.ZipFile(destination,'a') as z:z.writestr('unsigned.txt',b'fixture')
                    return {'fixture':False}
                with patch('sqe_studio.native_em_qualification.qualify_native_em',side_effect=native):
                    with self.assertRaises(ValueError):execute('em',root,folder)
                self.assertFalse((folder/'em.zip').exists())
                self.assertFalse(destinations[0].parent.exists())


class TransmonReferenceApplicability(unittest.TestCase):
    """Classification fixtures only; no new eigenvalue or literature evidence."""
    def compare(self,model='Fluxonium',*,spectrum_update=None,input_update=None):
        from sqe_studio.eda.scientific_references import CASES, _transmon
        values=inputs(model=model)
        if input_update:values.update(input_update)
        spectrum={'schema':'sqe.scqubits.spectrum.v1','model':model,
                  'input_sha256':digest(values)}
        if spectrum_update:spectrum.update(spectrum_update)
        project={'model':{'studies':[{'id':'Q','engine':'scqubits','inputs':values}]}}
        manifest={'artifact_type':'scqubits.spectrum','engine':'scqubits','study_id':'Q'}
        return _transmon(CASES[0],project,manifest,spectrum)

    def test_verified_other_models_do_not_claim_transmon_comparison(self):
        for model in ('Fluxonium','TunableTransmon','Composite'):
            with self.subTest(model=model):
                result=self.compare(model)
                self.assertEqual(result['status'],'NOT_APPLICABLE')
                self.assertEqual(result['checks'],[])
                self.assertEqual(result['physical_validation'],'NOT_ESTABLISHED')

    def test_wrong_digest_remains_blocked_for_nonapplicable_model(self):
        self.assertEqual(self.compare(spectrum_update={'input_sha256':'0'*64})['status'],'BLOCKED')

    def test_wrong_model_or_schema_remains_blocked(self):
        for values in ({'model':'Transmon'},{'schema':'untrusted.spectrum.v0'}):
            with self.subTest(values=values):
                self.assertEqual(self.compare(spectrum_update=values)['status'],'BLOCKED')

    def test_derived_or_unknown_models_remain_blocked(self):
        self.assertEqual(self.compare(input_update={'source':'em_derived'})['status'],'BLOCKED')
        self.assertEqual(self.compare(model='Unknown')['status'],'BLOCKED')

    def test_transmon_keeps_existing_units_regime_and_tolerances(self):
        spectrum={'units':'GHz','energy_unit':'GHz','preview_point_index':0,
                  'levels':[0.,5.214,10.145]}
        result=self.compare('Transmon',spectrum_update=spectrum)
        self.assertEqual(result['status'],'NUMERICAL_PASS')
        self.assertEqual([c['relative_tolerance'] for c in result['checks']],[.05,.20])
        self.assertEqual(self.compare('Transmon',spectrum_update=dict(spectrum,units='MHz'))['status'],'BLOCKED')




if __name__ == '__main__':
    unittest.main()
