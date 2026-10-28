"""Regression of true SQE/Palace interface contracts (solver itself is optional)."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sqw import em
from sqw.config import validate
from sqw.geometry import build
from sqw.io import digest, read_json, sha256, write_json
from sqw.palace_bridge import backend, command, distro, readiness, wsl_path
from sqw.qmetal_interop import manifest, to_qdesign
from sqw.studio.catalog import FEM, plan, blockers
from sqw.studio.process import document, resolve
from sqw.studio.server import Application
from sqw.studio.settings import Settings


class MetalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.doc=document()
        self.cfg,_=resolve(self.doc)
        self.geom=build(self.cfg)

    def test_geometry_exchange_exact_coordinates_and_checksum(self):
        m=manifest(self.cfg)
        self.assertEqual(m['geometry_sha256'],self.geom['geometry_sha256'])
        self.assertEqual(m['format'],'sqe-quantum-metal-positive-mask-v1')
        self.assertEqual(len(m['components']),5)
        self.assertEqual(len(m['ports']),3)
        self.assertEqual(m['manifest_sha256'],digest({k:v for k,v in m.items() if k!='manifest_sha256'}))
        for net in m['components']:
            actual=self.geom['metal'][net['name']]
            self.assertEqual(len(actual),len(net['rectangles_mm']))
            for rect,orig in zip(net['rectangles_mm'],actual):
                self.assertEqual(rect,[orig[k]/1000 for k in ('x0','y0','x1','y1')])
            self.assertFalse(net['subtract'])
        self.assertEqual(self.geom['chip']['x1']-self.geom['chip']['x0'],m['chip']['width_mm']*1000)

    def test_malformed_manifest_is_rejected_before_loading_qmetal(self):
        # Test wrapper via stub modules, not actual heavy external QDesign package.
        import types
        fake=types.ModuleType('qiskit_metal'); designs=types.ModuleType('qiskit_metal.designs')
        core=types.ModuleType('qiskit_metal.qlibrary.core'); lib=types.ModuleType('qiskit_metal.qlibrary')
        designs.DesignPlanar=lambda enable_renderers: object()
        core.QComponent=type('QComponent',(),{})
        modules={'qiskit_metal':fake,'qiskit_metal.designs':designs,
                 'qiskit_metal.qlibrary':lib,'qiskit_metal.qlibrary.core':core}
        m=manifest(self.cfg);m['components'][0]['rectangles_mm'][0][0]+=0.123
        with patch.dict(sys.modules,modules):
            with self.assertRaisesRegex(ValueError,'checksum'):
                to_qdesign(m)

    def test_qmetal_headless_sidecar_creates_real_qgeometry_calls_with_mock_design(self):
        # This isolates the QComponent integration path without installing QMetal.
        import types
        fake=types.ModuleType('qiskit_metal')
        designs=types.ModuleType('qiskit_metal.designs')
        core=types.ModuleType('qiskit_metal.qlibrary.core')
        lib=types.ModuleType('qiskit_metal.qlibrary')
        class FakeDesign:
            def __init__(self,enable_renderers):
                self.components={};self.enable_renderers=enable_renderers
        class FakeQComponent:
            def __init__(self,design,name):
                self.design=design;self.name=name
                design.components[name]=self;self.make()
            def add_qgeometry(self,kind,polygons,layer,subtract):
                self.qgeometry=(kind,polygons,layer,subtract)
        designs.DesignPlanar=FakeDesign
        core.QComponent=FakeQComponent
        modules={'qiskit_metal':fake,'qiskit_metal.designs':designs,
                 'qiskit_metal.qlibrary':lib,'qiskit_metal.qlibrary.core':core}
        with patch.dict(sys.modules,modules):
            design=to_qdesign(manifest(self.cfg))
        self.assertFalse(design.enable_renderers)
        self.assertEqual(set(design.components),set(self.geom['metal']))
        for name,component in design.components.items():
            kind,polys,layer,subtract=component.qgeometry
            self.assertEqual(kind,'poly')
            self.assertEqual(layer,1)
            self.assertFalse(subtract)
            self.assertEqual(len(polys),len(self.geom['metal'][name]))
            self.assertTrue(all(poly.area>0 for poly in polys.values()))

    def test_palace_contracts_and_two_port_driven(self):
        with tempfile.TemporaryDirectory() as tmp:
            em.export_configs(self.cfg,self.geom,tmp)
            cfgs={x:read_json(Path(tmp)/f'{x}.json') for x in
                  ('electrostatic','eigenmode','linearized','driven')}
            for typ,pr in [('Electrostatic','electrostatic'),('Eigenmode','eigenmode'),('Eigenmode','linearized'),('Driven','driven')]:
                self.assertEqual(cfgs[pr]['Problem']['Type'],typ)
                self.assertEqual(cfgs[pr]['Model']['L0'],1e-6)
                self.assertEqual(cfgs[pr]['Model']['Mesh'],'device.msh')
            d=cfgs['driven']
            self.assertEqual([p['Excitation'] for p in d['Boundaries']['LumpedPort']],[1,0])
            self.assertEqual([p['Excitation'] for p in read_json(Path(tmp)/'driven-p2.json')['Boundaries']['LumpedPort']],[0,1])
            sample=d['Solver']['Driven']['Samples'][0]
            self.assertEqual(sample['Type'],'Linear')
            self.assertEqual(sample['NSample'],61)
            self.assertLess(sample['MinFreq'],sample['MaxFreq'])
            self.assertNotIn('Eigenmode',d['Solver'])
            self.assertEqual(len(cfgs['linearized']['Boundaries']['LumpedPort']),3)
            self.assertIn('geometry_sha256',read_json(Path(tmp)/'contract.json'))

    def test_fem_plans_have_correct_prerequisites(self):
        for target in ('solve:electrostatic','solve:eigenmode','solve:linearized','solve:driven'):
            self.assertIn(target,FEM)
            self.assertEqual(plan(target,'fem'),['layout','em-export','mesh',target])
            with self.assertRaises(ValueError):plan(target,'demo')

    def test_native_and_windows_wsl_launch_command_escaping(self):
        with patch.dict(os.environ,{'SQE_PALACE_BACKEND':'native'}):
            self.assertEqual(backend(),'native')
            with patch('sqw.palace_bridge.shutil.which',return_value='/opt/palace/palace'):
                actual,identity=command('/tmp/output','driven',3)
                self.assertEqual(actual,['/opt/palace/palace','-np','3','driven.json'])
                self.assertEqual(identity,'/opt/palace/palace')
        import sqw.palace_bridge as pb
        fake=lambda args,**kw: subprocess.CompletedProcess(args,0,stdout='/mnt/c/Experiments With Spaces/job\n')
        with patch.dict(os.environ,{'SQE_PALACE_BACKEND':'wsl','SQE_WSL_DISTRO':'Ubuntu-24.04'}):
            with patch.object(pb,'os',__import__('types').SimpleNamespace(name='nt',getenv=os.getenv)):
                with patch('sqw.palace_bridge.shutil.which',return_value='C:\\Windows\\System32\\wsl.exe'):
                    cmd,identity=command('/tmp/example','driven',2,invoke=fake)
                    self.assertEqual(cmd[:5],['wsl.exe','-d','Ubuntu-24.04','--','bash'])
                    self.assertEqual(cmd[-3:],['/mnt/c/Experiments With Spaces/job','driven.json','2'])
                    self.assertIn('WSL2:Ubuntu-24.04',identity)
        with patch.dict(os.environ,{'SQE_WSL_DISTRO':'bad/distro'}):
            with self.assertRaises(ValueError):distro()

    def test_wsl_runner_stages_and_repatriates_output_fake_solver(self):
        # The *runner* is exercised using a fake command; no Palace accuracy claimed.
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            home=base/'home'; exe=home/'.sqe/palace/bin/palace';exe.parent.mkdir(parents=True)
            exe.write_text('#!/usr/bin/env python3\nimport json,os,sys,pathlib\n'
                           'config=json.loads(pathlib.Path(sys.argv[-1]).read_text())\n'
                           'out=pathlib.Path(config["Problem"]["Output"]);out.mkdir()\n'
                           '(out/"port-S.csv").write_text("f (GHz), |S[1][1]|\\n4,0.1\\n")\n')
            exe.chmod(0o755)
            src=base/'Source with spaces';src.mkdir()
            (src/'device.msh').write_text('mock mesh')
            (src/'driven.json').write_text(json.dumps({'Problem':{'Output':'driven'}}))
            root=Path(__file__).resolve().parents[1]
            runner=root/'scripts'/'palace-wsl-run.sh'
            proc=subprocess.run(['bash',str(runner),str(src),'driven.json','1'],
                                env={**os.environ,'HOME':str(home)},capture_output=True,text=True,timeout=20)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn('f (GHz)',(src/'driven/port-S.csv').read_text())
            proc2=subprocess.run(['bash',str(runner),str(src),'driven.json','1'],
                                env={**os.environ,'HOME':str(home)},capture_output=True,text=True,timeout=20)
            self.assertNotEqual(proc2.returncode,0)
            self.assertIn('Destination already exists',proc2.stderr)

    def test_record_integrity_and_fake_solver_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);em.export_configs(self.cfg,self.geom,tmp)
            (base/'device.msh').write_bytes(b'fake gmsh mesh')
            write_json(base/'mesh.json',{'geometry_sha256':self.geom['geometry_sha256'],
                                        'mesh_sha256':sha256(base/'device.msh')})
            fake=base/'fake-palace.py'
            fake.write_text('import json,pathlib,sys\n'
                            'cfg=json.load(open(sys.argv[1]))\n'
                            'd=pathlib.Path(cfg["Problem"]["Output"]);d.mkdir()\n'
                            '(d/"port-S.csv").write_text("f (GHz), |S[1][1]|\\n4,0.1\\n")\n')
            with patch('sqw.palace_bridge.command',side_effect=lambda out,problem,ranks,exe: ([sys.executable,str(fake),problem+'.json'],str(fake))):
                em.run_palace(base,'driven')
            em.validate_solve_record(base,'driven')
            self.assertEqual(read_json(base/'solve-driven.json')['status'],'completed')
            (base/'driven/port-S.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):
                em.validate_solve_record(base,'driven')


class MetalAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Application(Settings(root=Path(self.temp.name)))
        token=self.app.auth.setup_token()
        self.app.auth.setup(token,'owner@example.org','Owner','correct horse battery staple')
        self.session,self.csrf,self.user=self.app.auth.login('owner@example.org','correct horse battery staple','local')
        self.project=self.app.projects.create(self.user,'Transmon EM test')

    def tearDown(self):self.temp.cleanup()

    def call(self,path,authenticated=True):
        env={'REQUEST_METHOD':'GET','PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1:8000',
             'CONTENT_TYPE':'application/json','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()}
        if authenticated:env.update(HTTP_COOKIE='sqe_session='+self.session,HTTP_X_CSRF_TOKEN=self.csrf)
        r={}
        def start(status,headers):r.update(code=int(status.split()[0]),headers=dict(headers))
        response=self.app(env,start);r['raw']=b''.join(response)
        if hasattr(response,'close'):response.close()
        if r['headers']['Content-Type'].startswith('application/json'):r['json']=json.loads(r['raw'])
        return r

    def test_api_visibility_and_correct_design_identity(self):
        for path in ('/api/palace/status',f'/api/projects/{self.project}/palace/preview',
                     f'/api/projects/{self.project}/quantum-metal/manifest'):
            self.assertEqual(self.call(path,authenticated=False)['code'],401)
        with patch('sqw.palace_bridge.readiness',return_value={'installed':False,'backend':'native','qualified':False}):
            status=self.call('/api/palace/status')
        self.assertEqual(status['code'],200)
        self.assertFalse(status['json']['qualified'])
        preview=self.call(f'/api/projects/{self.project}/palace/preview')
        export=self.call(f'/api/projects/{self.project}/quantum-metal/manifest')
        self.assertEqual(preview['code'],200,preview)
        self.assertEqual(export['code'],200,export)
        self.assertEqual(preview['json']['geometry']['geometry_sha256'],export['json']['geometry_sha256'])
        self.assertTrue(preview['json']['separate_from_quantum_lab_netlist'])
        self.assertIn('attachment;',export['headers']['Content-Disposition'])
        self.assertEqual(export['json']['manifest_sha256'],digest({k:v for k,v in export['json'].items() if k!='manifest_sha256'}))

if __name__=='__main__':unittest.main()
