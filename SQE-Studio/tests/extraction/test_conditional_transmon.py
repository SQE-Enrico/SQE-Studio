"""Constructed source / HTTP / provenance tests. No claimed native EM or quantum."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

from sqe_studio.contracts import digest
from sqe_studio.interop import extracted_transmon as bridge
from sqe_studio.testing.extraction_fixture import source_fixture, declaration
from sqe_studio.testing.native_extraction import FixtureSession

ROOT=Path(__file__).resolve().parents[2]


class ReductionAndAssumptions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='sqe-m19-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.folder,self.manifest,self.project=source_fixture(Path(self.temp.name))
        self.source={'run_id':'1'*32,'revision_id':self.project['revision'],
            'project_digest':self.project['revision_digest'],'study_id':self.manifest['study_id'],
            'manifest_sha256':hashlib.sha256((self.folder/'RESULT_MANIFEST.json').read_bytes()).hexdigest()}
        self.context={'schema':bridge.CONTEXT_SCHEMA,'source':self.source,
                      'source_project':self.project,'source_output':str(self.folder)}
        self.study={'id':'Extracted1',**bridge.study_template(self.context,declaration())}

    def extract(self):
        return bridge.build_extraction(self.study['inputs'],self.project['model'],self.context)

    def test_existing_reducer_retains_floating_differential_charge_convention(self):
        out=self.extract()
        expected=(150*160-50**2)/(150+160-2*50)*1e-15
        self.assertAlmostEqual(out['capacitances']['matrix_effective_F']/expected,1,places=13)
        self.assertEqual(out['matrix_reduction']['charge_vector_in_units_of_e'],[1,-1])
        self.assertEqual(out['matrix_reduction']['configuration'],'TWO_ISLAND_CHARGE_TRANSFER')

    def test_additional_cj_and_exact_si_ec(self):
        out=self.extract();total=out['capacitances']['total_F']
        self.assertAlmostEqual(total/(out['capacitances']['matrix_effective_F']+2e-15),1,places=14)
        expected=1.602176634e-19**2/(2*6.62607015e-34*total)/1e9
        self.assertAlmostEqual(out['parameters']['EC'],expected,places=14)

    def test_zero_cj_is_explicit_and_does_not_create_a_junction_from_pec(self):
        self.study['inputs']['assumptions']['junction_capacitance_fF']=0.0
        out=self.extract()
        self.assertEqual(out['capacitances']['additional_junction_F'],0.0)
        self.assertEqual(out['parameters']['EJ'],15.0)
        self.assertIn('not measured here',' '.join(out['unresolved']))

    def test_increasing_cj_lowers_ec_without_changing_ej(self):
        first=self.extract()
        self.study['inputs']['assumptions']['junction_capacitance_fF']=20.0
        second=self.extract()
        self.assertLess(second['parameters']['EC'],first['parameters']['EC'])
        self.assertEqual(second['parameters']['EJ'],first['parameters']['EJ'])
        self.assertNotEqual(second['extraction_sha256'],first['extraction_sha256'])

    def test_lj_conversion_uses_phi0_over_2pi_and_h(self):
        raw=declaration();raw['josephson'].update(quantity='LJ',value=10.,unit='nH')
        _,ej=bridge.validate_declaration(raw)
        phi0=6.62607015e-34/(2*1.602176634e-19)
        expected=(phi0/(2*math.pi))**2/(6.62607015e-34*10e-9)/1e9
        self.assertAlmostEqual(ej,expected,places=12)
        self.assertTrue(16.3<ej<16.4)

    def test_fixture_origin_and_unresolved_physics_are_visible(self):
        out=self.extract()
        self.assertEqual(out['source_result_metadata']['execution_kind'],'SOFTWARE_FIXTURE')
        self.assertEqual(out['source_result_metadata']['new_palace_solve'],'NOT_RUN')
        self.assertEqual(out['parameter_origin'],'EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS')
        self.assertEqual(out['reviewed_A01_transfer'],'BLOCKED')
        self.assertEqual(out['scientific_qualification'],'NOT_ESTABLISHED')
        self.assertEqual(out['fabrication'],'HOLD')

    def test_self_described_matrices_paths_and_ec_are_not_input_fields(self):
        for key in ('EC','parameters','maxwell_matrix_f','source_output','verified_em','review'):
            with self.subTest(key=key):
                bad=deepcopy(self.study['inputs']);bad[key]='self-authorized'
                with self.assertRaises(bridge.ExtractionBlocked):bridge.validate_inputs(bad)

    def test_bad_declaration_never_reaches_native_code(self):
        for field,value in (
                ('acknowledged',False),('junction_capacitance_convention','ALREADY_INCLUDED'),
                ('junction_capacitance_fF',-1),('junction_capacitance_fF',True),
                ('junction_capacitance_fF',float('nan')),('junction_capacitance_fF',10**1000),
                ('junction_reference',''),('junction_reference','injected\nline'),
                ('ng',float('inf')),('ncut',61),('ncut',True),('levels',2)):
            with self.subTest(field=field,value_type=type(value).__name__):
                raw=declaration();raw[field]=value
                with self.assertRaises(bridge.ExtractionBlocked):bridge.validate_declaration(raw)

    def test_josephson_unit_quantity_and_source_are_explicit(self):
        for changes in ({'unit':'Hz'},{'quantity':'Ic'},{'value':0.0},{'value':True},
                        {'quantity':'LJ','unit':'nH','value':1e-6},{'reference':'  '}):
            with self.subTest(changes=changes):
                raw=declaration();raw['josephson'].update(changes)
                with self.assertRaises(bridge.ExtractionBlocked):bridge.validate_declaration(raw)

    def test_no_trusted_context_no_quantization(self):
        for context in (None,{}, {'schema':bridge.CONTEXT_SCHEMA},
                        {**self.context,'client_reviewed':True}):
            with self.subTest(context_type=type(context).__name__):
                with self.assertRaises(bridge.ExtractionBlocked):
                    bridge.build_extraction(self.study['inputs'],self.project['model'],context)

    def test_manifest_or_any_native_byte_tampering_blocks(self):
        for name in ('RESULT_MANIFEST.json','sqe_em/outputFiles/terminal-C.csv',
                     'sqe_em/sqe_em.msh','sqe_em/sqe_em.json','sqe_em/palace-native.log'):
            with self.subTest(name=name):
                path=self.folder/name;original=path.read_bytes();path.write_bytes(original+b'\nTAMPER')
                try:
                    with self.assertRaises(ValueError):self.extract()
                finally:path.write_bytes(original)

    def test_independent_adapter_still_rejects_extracted_inputs(self):
        from sqe_studio.adapters.scqubits_adapter import _source
        for source in ('conditional_extracted_research','em','verified_em'):
            with self.subTest(source=source):
                with self.assertRaises(Exception):_source({'source':source})

    def test_four_native_basis_policy_and_model_hash(self):
        out=self.extract()
        self.assertEqual(out['basis_policy'],{'enabled':True,'basis_increment':5,'steps':3,'tolerance_GHz':1e-5})
        self.assertEqual(out['extraction_sha256'],digest({k:v for k,v in out.items() if k!='extraction_sha256'}))

    def test_koch_shared_comparator_does_not_claim_device_agreement(self):
        from sqe_studio.eda.scientific_references import compare_transmon_asymptote
        p=self.extract()['parameters'];f=math.sqrt(8*p['EJ']*p['EC'])-p['EC']
        result=compare_transmon_asymptote(p['EJ'],p['EC'],[0.,f,2*f-p['EC']])
        self.assertEqual(result['status'],'NUMERICAL_PASS')
        self.assertEqual(result['physical_validation'],'NOT_ESTABLISHED')
        self.assertEqual(compare_transmon_asymptote(1.,1.,[0.,1.,2.])['status'],'NOT_APPLICABLE')

    def _provider_fixture(self, changed=None):
        """Serialization/dispatch fixture only: never a native eigenvalue test."""
        def execute(scq,spec):
            self.assertEqual(spec['source'],'conditional_extracted_research')
            self.assertAlmostEqual(spec['groups'][0]['parameters']['EC'],self.extract()['parameters']['EC'])
            if changed:
                changed()
            return [[-14.,-9.5,-5.2,-1.2]],[],[{
                'status':'checked_passed','max_delta_GHz':0.,'criterion':'last_two_adjacent_ground_referenced_transition_deltas',
                'basis_parameter':'ncut','point_index':0,'sweep_value':None,'curve':[
                    {'basis_cutoff':n,'basis_dimension':2*n+1,'f01_GHz':4.5,'f12_GHz':4.3,
                     'anharmonicity_GHz':-.2,'transitions_from_ground_GHz':[4.5,8.8,12.8],
                     'max_adjacent_delta_GHz':None if n==15 else 0.} for n in (15,20,25,30)]}]
        scq=types.SimpleNamespace(set_units=lambda value:None,get_units=lambda:'GHz')
        return scq,execute

    def test_worker_writes_hash_bound_conditional_result_with_injected_provider_only(self):
        from sqe_studio import worker
        from sqe_studio.orchestration.artifacts import verify_manifest
        model=deepcopy(self.project['model']);model['studies'].append(self.study)
        snapshot={'project':model,'project_digest':digest(model),'revision_id':'d'*32,
                  'study':self.study,'parents':[],'extraction_context':self.context}
        snap=Path(self.temp.name)/'snapshot.json';snap.write_text(json.dumps(snapshot),encoding='utf-8')
        output=Path(self.temp.name)/'research-output'
        scq,provider=self._provider_fixture()
        with patch.dict('sys.modules',{'scqubits':scq}),patch('sqe_studio.adapters.base.require_module'),\
             patch.object(bridge.metadata,'version',return_value='4.3.1'),\
             patch('sqe_studio.adapters.scqubits_adapter._execute',side_effect=provider) as executed:
            self.assertEqual(worker.run(snap,output),0)
        executed.assert_called_once()
        verified=verify_manifest(output,revision_id='d'*32,project_digest=digest(model),
                                 study_id=self.study['id'],engine='scqubits')
        extraction=json.loads((output/'extraction.json').read_text(encoding='utf-8'))
        spectrum=json.loads((output/'spectrum.json').read_text(encoding='utf-8'))
        bridge.validate_saved_result(extraction,spectrum,self.study)
        self.assertEqual(verified.artifact_type,'scqubits.spectrum')
        self.assertEqual(extraction['source_result_metadata']['execution_kind'],'SOFTWARE_FIXTURE')
        for field in ('input_sha256','extraction_sha256','parameter_origin'):
            broken=deepcopy(extraction);broken[field]='forged'
            with self.subTest(field=field),self.assertRaises(bridge.ExtractionBlocked):
                bridge.validate_saved_result(broken,spectrum,self.study)

    def test_source_mutation_during_provider_run_does_not_publish_spectrum(self):
        output=Path(self.temp.name)/'mutating-output'
        scq,provider=self._provider_fixture(lambda:
            (self.folder/'sqe_em/outputFiles/terminal-C.csv').write_text('mutation during solve',encoding='utf-8'))
        with patch.dict('sys.modules',{'scqubits':scq}),patch('sqe_studio.adapters.base.require_module'),\
             patch.object(bridge.metadata,'version',return_value='4.3.1'),\
             patch('sqe_studio.adapters.scqubits_adapter._execute',side_effect=provider):
            with self.assertRaises(ValueError):bridge.run(self.study,self.project['model'],output,self.context)
        self.assertFalse((output/'spectrum.json').exists())
        self.assertFalse((output/'extraction.json').exists())

    def test_missing_worker_context_blocks_before_native_execution(self):
        with patch('sqe_studio.adapters.scqubits_adapter._execute') as executed:
            with self.assertRaises(bridge.ExtractionBlocked):
                bridge.run(self.study,self.project['model'],Path(self.temp.name)/'no-context',None)
        executed.assert_not_called()

    def test_result_model_cannot_be_relabelled_as_independent_for_target_feedback(self):
        from sqe_studio.interop.design_targets import _observations
        spectrum={'schema':'sqe.scqubits.spectrum.v1','artifact_type':'scqubits.spectrum',
            'engine':'scqubits','source':'native scqubits eigenvals','units':'GHz',
            'energy_unit':'GHz','levels':[-14.,-9.5,-5.2],
            'parameter_origin':'EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS'}
        observed=_observations({'engine':'scqubits'},spectrum,None)
        self.assertEqual(observed['f01'][2],'CONDITIONAL_EM_DERIVED_JUNCTION_MODEL')


class SavedSourceHTTP(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='sqe-m19-http-');self.addCleanup(temp.cleanup)
        self.s=FixtureSession(temp.name).__enter__();self.addCleanup(self.s.__exit__,None,None,None)
        self.payload={'expected_revision':self.s.project['head'],'action':'preview','declaration':declaration()}

    def test_authenticated_preview_does_not_commit_run_or_change_manual_study(self):
        before=self.s.request(f'/api/projects/{self.s.pid}')
        result=self.s.request(self.s.url,self.payload)
        after=self.s.request(f'/api/projects/{self.s.pid}')
        self.assertEqual(result['schema'],'sqe.extraction-preview.m19.v1')
        self.assertEqual(result['solver_execution'],'NOT_EXECUTED')
        self.assertEqual(after,before)
        self.assertEqual(len(self.s.request(f'/api/projects/{self.s.pid}/runs')['runs']),1)

    def test_csrf_required(self):
        status,_=self.s.response(self.s.url,self.payload,csrf=False)
        self.assertEqual(status,403)

    def test_stale_head_rejected(self):
        status,_=self.s.response(self.s.url,{**self.payload,'expected_revision':'0'*32})
        self.assertEqual(status,409)

    def test_unowned_or_unknown_source_rejected(self):
        other=self.s.request('/api/projects',{'name':'Different project','family':'transmon'})
        status,_=self.s.response(f'/api/projects/{other["id"]}/runs/{self.s.run_id}/extraction',
            {**self.payload,'expected_revision':other['head']})
        self.assertEqual(status,409)

    def test_mutated_source_cannot_be_previewed(self):
        (self.s.output/'sqe_em/outputFiles/terminal-C.csv').write_text('mutated',encoding='utf-8')
        status,_=self.s.response(self.s.url,self.payload)
        self.assertEqual(status,409)

    def test_layout_or_material_or_selection_changes_block_historical_source(self):
        original=deepcopy(self.s.project['model'])
        revision=self.payload['expected_revision']
        for part in ('layout','process','selection','study'):
            with self.subTest(part=part):
                model=deepcopy(original)
                if part=='layout':model['layout']['components'][0]['x_mm']+=.001
                elif part=='process':model['process']['stack'][0]['relative_permittivity']+=.01
                elif part=='selection':model['intent']['transmon_capacitance_selection']['island_a']='LP2'
                else:model['studies'][0]['inputs']['em']['mesh']['max_um']+=1
                revision=self.s.request(f'/api/projects/{self.s.pid}/commit',
                    {'expected_revision':revision,'model':model})['revision']
                status,_=self.s.response(self.s.url,{**self.payload,'expected_revision':revision})
                self.assertEqual(status,409)

    def test_study_only_revision_can_reuse_exact_verified_source(self):
        model=deepcopy(self.s.project['model']);model['notes']+=' study-only note'
        revision=self.s.request(f'/api/projects/{self.s.pid}/commit',
            {'expected_revision':self.payload['expected_revision'],'model':model})['revision']
        out=self.s.request(self.s.url,{**self.payload,'expected_revision':revision})
        self.assertEqual(out['extraction']['source']['revision_id'],self.s.project['revision'])
        self.assertEqual(out['expected_revision'],revision)

    def test_execute_creates_typed_study_and_trusted_worker_context(self):
        with patch.object(self.s.server.app.jobs,'_work'):
            answer=self.s.request(self.s.url,{**self.payload,'action':'execute'})
        self.addCleanup(self.s.server.app.jobs._release_slot)
        current=self.s.request(f'/api/projects/{self.s.pid}')
        saved=next(x for x in current['model']['studies'] if x['id']==answer['study_id'])
        self.assertEqual(saved['kind'],bridge.KIND)
        self.assertEqual(saved['inputs']['schema'],bridge.INPUT_SCHEMA)
        self.assertNotIn('EC',saved['inputs'])
        self.assertNotIn('source_output',saved['inputs'])
        info=self.s.server.app.store.run(self.s.owner,self.s.pid,answer['run_id'])
        snap=json.loads((Path(info['path'])/'snapshot.json').read_text(encoding='utf-8'))
        self.assertEqual(snap['extraction_context']['schema'],bridge.CONTEXT_SCHEMA)
        self.assertEqual(snap['extraction_context']['source']['revision_id'],self.s.project['revision'])
        self.assertEqual(snap['parents'],[])

    def test_generic_sweep_cannot_modify_extracted_ec_or_source(self):
        from sqe_studio.interop.extracted_transmon import resolve_source,study_template
        c=resolve_source(self.s.server.app.store,self.s.owner,self.s.pid,self.s.project,self.s.run_id)
        model=deepcopy(self.s.project['model'])
        model['studies'].append({'id':'Research1',**study_template(c,declaration())})
        rev=self.s.server.app.store.commit(self.s.owner,self.s.pid,self.s.project['head'],model)
        with self.assertRaises(ValueError):
            self.s.server.app.jobs._submit(self.s.owner,self.s.pid,rev,'Research1',points=[object()])

    def test_jobs_rechecks_source_before_native_cache_lookup(self):
        c=bridge.resolve_source(self.s.server.app.store,self.s.owner,self.s.pid,self.s.project,self.s.run_id)
        model=deepcopy(self.s.project['model'])
        model['studies'].append({'id':'Research1',**bridge.study_template(c,declaration())})
        rev=self.s.server.app.store.commit(self.s.owner,self.s.pid,self.s.project['head'],model)
        (self.s.output/'sqe_em/palace-native.log').write_text('changed',encoding='utf-8')
        with patch.object(self.s.server.app.jobs,'_candidate_cache') as cache:
            with self.assertRaises(ValueError):self.s.server.app.jobs.start(self.s.owner,self.s.pid,rev,'Research1')
            cache.assert_not_called()

    def test_reserved_research_id_cannot_be_relabelled_independent(self):
        model=deepcopy(self.s.project['model'])
        model['studies'].append({'id':'extracted_transmon_01','engine':'scqubits','kind':'spectrum',
            'inputs':{'model':'Transmon','source':'independent','parameters':{'EJ':15.,'EC':.2,'ng':0.,'ncut':15}}})
        revision=self.s.server.app.store.commit(self.s.owner,self.s.pid,self.s.project['head'],model)
        with self.assertRaisesRegex(ValueError,'relabeled'):
            self.s.server.app.jobs.start(self.s.owner,self.s.pid,revision,'extracted_transmon_01')


class FixtureConnectionLifetime(unittest.TestCase):
    """Real SQLite handles held strongly: no dependence on GC or host unlink rules."""
    def check_session(self, *, fail_after_owner_lookup=False):
        import sqlite3
        import threading
        from sqe_studio import store
        created=[]
        original=store._ClosingConnection
        class TrackedConnection(original):
            def __init__(connection,*args,**kwargs):
                super().__init__(*args,**kwargs)
                connection.test_closed=False
                connection.test_thread_id=threading.get_ident()
                created.append(connection)  # Deliberately prevent implicit GC closure.
            def close(connection):
                result=super().close()
                connection.test_closed=True
                return result
        with tempfile.TemporaryDirectory(prefix='sqe-m19-connection-lifetime-') as td:
            try:
                with patch.object(store,'_ClosingConnection',TrackedConnection):
                    if fail_after_owner_lookup:
                        with patch.object(store.Store,'put_run',side_effect=RuntimeError('injected registration failure')):
                            with self.assertRaisesRegex(RuntimeError,'injected registration failure'):
                                FixtureSession(td).__enter__()
                    else:
                        with FixtureSession(td) as session:
                            self.assertGreater(len(created),5)
                            self.assertEqual([i for i,c in enumerate(created) if not c.test_closed],[],
                                             'Fixture creation left SQLite handles open before any native execution')
                            session.request(f'/api/projects/{session.pid}')
                    self.assertGreater(len(created),5)
                    self.assertEqual([i for i,c in enumerate(created) if not c.test_closed],[],
                                     'Fixture teardown must release all SQLite handles without garbage collection')
                    for connection in created:
                        if connection.test_thread_id==threading.get_ident():
                            with self.assertRaisesRegex(sqlite3.ProgrammingError,'closed database'):
                                connection.execute('SELECT 1')
            finally:
                # A deliberately failing regression must not itself leak handles
                # or replace its assertion with a Windows temp-cleanup exception.
                for connection in created:
                    if not connection.test_closed:connection.close()

    def test_fixture_closes_every_real_sqlite_connection_before_native_execution(self):
        self.check_session()

    def test_fixture_error_path_closes_owner_connection_before_cleanup(self):
        self.check_session(fail_after_owner_lookup=True)






if __name__=='__main__':
    unittest.main()
