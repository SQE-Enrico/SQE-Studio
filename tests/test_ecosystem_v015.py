"""v0.15 topology-independent adapter protocol and non-solver tests.

Optional engines are mocked at public API boundaries; mocks NEVER establish
numerical qualification. The real QuantumLab 1Q reference runs in core CI.
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sqw import ecosystem
from sqw.io import read_json, write_json
from sqw.quantumlab import preset


class EcosystemContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project'
        self.root.mkdir()
        write_json(self.root/'design.json',preset(1))
        self.spec={'schema_version':1,'name':'one-qubit test', 'steps':[
            {'id':'modes','engine':'quantumlab','operation':'modes','source':'design.json'},
            {'id':'julia','engine':'josephsoncircuits','operation':'export','source':'design.json','needs':['modes']} ]}

    def test_real_core_result_and_immutable_records(self):
        output=Path(self.tmp.name)/'out'
        actual=ecosystem.execute(self.spec,self.root,output)
        self.assertEqual(actual['state'],'COMPLETED')
        self.assertIn('result.json',actual['steps']['modes']['artifacts'])
        self.assertEqual(actual['steps']['modes']['state'],'COMPUTED_REDUCED_ORDER')
        self.assertEqual(actual['steps']['julia']['state'],'EXPORTED_NOT_SIMULATED')
        self.assertIn('Lj1',(output/'steps'/'julia'/'circuit.jl').read_text())
        self.assertTrue(ecosystem.verify(output)['verified'])
        with self.assertRaisesRegex(ValueError,'new/empty'):
            ecosystem.execute(self.spec,self.root,output)
        (output/'steps'/'julia'/'circuit.jl').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'Artifact mismatch'):
            ecosystem.verify(output)

    def test_workflow_json_tamper_detection(self):
        output=Path(self.tmp.name)/'out'
        ecosystem.execute(self.spec,self.root,output)
        data=read_json(output/'workflow.json')
        data['name']='tampered'
        write_json(output/'workflow.json',data)
        with self.assertRaisesRegex(ValueError,'tampered'):
            ecosystem.verify(output)

    def test_reject_untrusted_paths_dependencies_and_codes(self):
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['source']='../x.json'
        with self.assertRaises(ValueError):ecosystem.validate(bad)
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['source']='/etc/passwd'
        with self.assertRaises(ValueError):ecosystem.validate(bad)
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['needs']=['julia']
        with self.assertRaises(ValueError):ecosystem.validate(bad)
        bad=json.loads(json.dumps(self.spec));bad['steps'][1]['id']='modes'
        with self.assertRaises(ValueError):ecosystem.validate(bad)
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['engine']='foo'
        with self.assertRaises(ValueError):ecosystem.validate(bad)
        factory=self.root/'design.py'
        factory.write_text("raise RuntimeError('untrusted code executed')")
        with self.assertRaisesRegex(ValueError,'allow-project-code'):
            ecosystem._qdesign(factory,False)

    def test_missing_and_symlink_source_rejected(self):
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['source']='missing.json'
        with self.assertRaisesRegex(ValueError,'Missing source'):
            ecosystem.execute(bad,self.root,Path(self.tmp.name)/'missingout')
        outer=Path(self.tmp.name)/'secret.json'
        outer.write_text('{}')
        (self.root/'link.json').symlink_to(outer)
        bad=json.loads(json.dumps(self.spec));bad['steps'][0]['source']='link.json'
        with self.assertRaisesRegex(ValueError,'escapes'):
            ecosystem.execute(bad,self.root,Path(self.tmp.name)/'linkout')

    def test_failed_optional_step_reports_failure_without_faking_results(self):
        spec={'schema_version':1,'name':'missing external','steps':[{
            'id':'metal','engine':'quantum-metal','operation':'inspect','source':'design.json'}]}
        out=Path(self.tmp.name)/'out'
        with self.assertRaises((ValueError,ImportError,ModuleNotFoundError)):
            ecosystem.execute(spec,self.root,out)
        self.assertEqual(read_json(out/'run.json')['state'],'FAILED')
        with self.assertRaisesRegex(ValueError,'not completed'):
            ecosystem.verify(out)

    def test_scqubits_actual_api_boundary_with_fake_runtime(self):
        class Transmon:
            def __init__(self,**kwargs):
                self.kwargs=kwargs
            def eigenvals(self,evals_count):
                return [5.5 + i*4.0 for i in range(evals_count)]
        fake=types.ModuleType('scqubits');fake.Transmon=Transmon
        write_json(self.root/'model.json',{'model':'Transmon','parameters':{'EJ':18.0,'EC':0.25}})
        spec={'schema_version':1,'name':'scq fake adapter contract', 'steps':[
            {'id':'spectrum','engine':'scqubits','operation':'spectrum','source':'model.json',
             'settings':{'levels':3}}]}
        with patch.dict(sys.modules,{'scqubits':fake}):
            run=ecosystem.execute(spec,self.root,Path(self.tmp.name)/'out')
        spectrum=read_json(Path(self.tmp.name)/'out/steps/spectrum/spectrum.json')
        self.assertAlmostEqual(spectrum['f01_GHz'],4.0)
        self.assertEqual(run['steps']['spectrum']['state'],'COMPUTED_QUANTUM')

    def test_sqdmetal_uses_public_prepare_api_without_solver(self):
        called=[]
        class FakeQDesign:
            components={}
            qgeometry=object()
        class Engine:
            def __init__(self,**kwargs):
                called.append(('init',kwargs))
            def add_metallic(self,layer): called.append(('metal',layer))
            def add_ground_plane(self):called.append(('ground',))
            def prepare_simulation(self):called.append(('prepare',))
            def run(self): called.append(('run',))
        mod=types.ModuleType('SQDMetal')
        palace=types.ModuleType('SQDMetal.PALACE')
        cap=types.ModuleType('SQDMetal.PALACE.Capacitance_Simulation')
        cap.PALACE_Capacitance_Simulation=Engine
        path=self.root/'design.py'
        path.write_text('def build_design():\n    pass\n')
        with patch('sqw.ecosystem._qdesign',return_value=(FakeQDesign(),'user_quantum_metal_factory_unqualified')):
            with patch.dict(sys.modules,{'SQDMetal':mod,'SQDMetal.PALACE':palace,
                                         'SQDMetal.PALACE.Capacitance_Simulation':cap}):
                out=Path(self.tmp.name)/'sqd'
                out.mkdir()
                status, files, _=ecosystem._sqdmetal('palace_capacitance',path,
                    {'metal_layer':1,'add_ground_plane':True,'execute':False},out,True,False)
                self.assertEqual(status,'PREPARED_NOT_SOLVED')
                self.assertEqual([v[0] for v in called],['init','metal','ground','prepare'])
                self.assertIn('adapter.json',files)

    def test_public_trusted_plugin_registration_and_hashes(self):
        class Adapter:
            operations=('analyze',)
            def run(self,operation,source,settings,output,*,allow_solvers):
                self.called=(operation,allow_solvers)
                (output/'plugin.txt').write_text('derived:'+source.name)
                return 'COMPUTED_EXTERNAL',['plugin.txt'],{'kind':'test_double'}
        plugin=Adapter()
        try:
            ecosystem.register_adapter('unit-test-external',plugin)
            spec={'schema_version':1,'name':'plugin test','steps':[
                {'id':'external','engine':'unit-test-external','operation':'analyze',
                 'source':'design.json'}]}
            out=Path(self.tmp.name)/'plugin-run'
            run=ecosystem.execute(spec,self.root,out)
            self.assertTrue(ecosystem.verify(out)['verified'])
            self.assertEqual(plugin.called,('analyze',False))
            self.assertEqual(run['steps']['external']['metadata']['kind'],'test_double')
            snap=out/'inputs/external.json'
            snap.write_text('tampered source snapshot')
            with self.assertRaisesRegex(ValueError,'Input snapshot mismatch'):
                ecosystem.verify(out)
        finally:
            ecosystem.CUSTOM_ADAPTERS.pop('unit-test-external',None)
            ecosystem.OPERATIONS.pop('unit-test-external',None)
            ecosystem.MODULES.pop('unit-test-external',None)

    def test_julia_linear_sweep_command_and_finite_sample_contract_mocked(self):
        # This checks the Julia handoff only. NO Julia numerical results tested.
        from subprocess import CompletedProcess
        source=self.root/'design.json'
        out=Path(self.tmp.name)/'julia-contract'
        def fake_run(command,*,cwd,capture_output,text,timeout,check):
            self.assertEqual(command[-1],'linear_sweep.jl')
            self.assertTrue((cwd/'linear_sweep.jl').exists())
            (cwd/'sparameters.csv').write_text('4.0,1,0\n6.0,0.8,-0.2\n8.0,0.5,-0.1\n')
            return CompletedProcess(command,0,'fake julia output','')
        with patch('sqw.ecosystem.shutil.which',return_value='/usr/bin/julia'):
            with patch('sqw.ecosystem.subprocess.run',side_effect=fake_run):
                state,artifacts,extra=ecosystem._josephson('linear_sweep',source,
                    {'points':3},out,True)
        self.assertEqual(state,'SOLVED_LINEAR_UNQUALIFIED')
        self.assertEqual(extra,{'port_in':1,'port_out':1})
        self.assertIn('sparameters.csv',artifacts)
        self.assertIn('hblinsolve',(out/'linear_sweep.jl').read_text())

    def test_sqdmetal_return_matrix_keeps_unverified_units_mocked(self):
        class Engine:
            def __init__(self,**kwargs): pass
            def add_metallic(self,layer): pass
            def prepare_simulation(self): pass
            def run(self): return [[1e-13,-2e-14],[-2e-14,1e-13]]
        cap=types.ModuleType('SQDMetal.PALACE.Capacitance_Simulation')
        cap.PALACE_Capacitance_Simulation=Engine
        out=Path(self.tmp.name)/'sqd-native-contract';out.mkdir()
        with patch('sqw.ecosystem._qdesign',return_value=(object(),'user_quantum_metal_factory_unqualified')):
            with patch.dict(sys.modules,{'SQDMetal':types.ModuleType('SQDMetal'),
                                         'SQDMetal.PALACE':types.ModuleType('SQDMetal.PALACE'),
                                         'SQDMetal.PALACE.Capacitance_Simulation':cap}):
                state,artifacts,_=ecosystem._sqdmetal('palace_capacitance',self.root/'design.json',
                    {'execute':True},out,True,True)
        self.assertEqual(state,'SOLVED_UNQUALIFIED')
        self.assertIn('native_capacitance_matrix.json',artifacts)
        data=read_json(out/'native_capacitance_matrix.json')
        self.assertEqual(data['unit'],'native_SQDMetal_return_unverified')

    def test_explicit_solver_flag_and_positive_mask_qualification(self):
        path=self.root/'design.json'
        with patch('sqw.ecosystem._qdesign',return_value=(object(),'manifest_positive_metal_only')):
            with self.assertRaisesRegex(ValueError,'positive-mask'):
                ecosystem._sqdmetal('palace_capacitance',path,{'execute':True},
                                   Path(self.tmp.name),False,True)
        with self.assertRaisesRegex(ValueError,'--allow-solvers'):
            ecosystem._josephson('linear_sweep',path,{},Path(self.tmp.name)/'julia',False)


if __name__=='__main__':
    unittest.main()
