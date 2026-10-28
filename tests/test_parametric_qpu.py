"""v0.7 deterministic checks of actual mask connectivity and the FEM contract.

Native gmsh/palace are not mocked as successful physics in this file.
"""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import types
import sys

from shapely.geometry import box
from shapely.ops import unary_union

from sqw import cad, physical_qpu as legacy, parametric_qpu as p
from sqw.io import digest,read_json
from sqw.studio.process import resolve,document


class ParametricDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cfg,_=resolve(document())

    def spec(self,n=2):return p.default_spec(self.cfg,n)

    def test_topologies_sizes_and_explicit_graph(self):
        for n in (1,2,4,9,16):
            with self.subTest(n=n):
                s=self.spec(n);g=legacy.build(self.cfg,s);net=legacy.circuit(self.cfg,s)
                self.assertEqual(g['schema_version'],3)
                self.assertEqual(g['designed_interqubit_couplers'],len(s['couplers']))
                self.assertEqual(len(g['components']),n)
                self.assertEqual(len(g['junctions']),n)
                self.assertEqual(len(net['qubits']),n)
                self.assertEqual(len([e for e in net['elements'] if e['id'].startswith('K_')]),len(s['couplers']))
                self.assertEqual(len(g['process_features']),2*n)
                self.assertEqual(set(g['physical_tags']),set(g['metal'])|set(g['ports'])|{'air','outer','substrate'})
                self.assertEqual(g['design_spec_sha256'],digest(s))

    def test_dolan_manhattan_angles_and_mask_checksum(self):
        s=self.spec(2);s['junction_process']['orientation_deg']=32.5
        g1=p.build(self.cfg,s)
        s['junction_process']['method']='manhattan'
        g2=p.build(self.cfg,s)
        self.assertNotEqual(g1['geometry_sha256'],g2['geometry_sha256'])
        self.assertIn('second_evaporation_intent',[v['feature'] for v in g2['process_features']])
        with tempfile.TemporaryDirectory() as d:
            p.export_gds(g2,Path(d)/'mask.gds')
            self.assertIn(91,cad.inspect_gds(Path(d)/'mask.gds')['layers'])

    def test_substrate_and_material_changes_propagate_to_palace(self):
        s=self.spec();s['materials']['sapphire']={'kind':'dielectric','epsilon_r':9.4,'loss_tangent':1e-6}
        s['stack'][0]['material']='sapphire';s['stack'][0]['thickness_um']=430.;s['stack'][0]['z0_um']=-430.
        s['stack'].insert(0,{'id':'buffer','role':'dielectric','material':'silicon',
                              'z0_um':-450.,'thickness_um':20.})
        g=p.build(self.cfg,s);cfg=p.palace_configs(self.cfg,s,g)
        self.assertEqual(set(g['physical_tags']) & {'buffer','substrate'},{'buffer','substrate'})
        eps=sorted(v['Permittivity'] for v in cfg['eigenmode']['Domains']['Materials'])
        self.assertEqual(eps,[1.,9.4,11.7])
        with tempfile.TemporaryDirectory() as d:
            out=p.export_package(self.cfg,s,d)
            self.assertEqual(read_json(Path(d)/'stackup.json'),s['stack'])
            self.assertEqual(read_json(Path(d)/'contract.json')['stack_sha256'],digest(s['stack']))
            self.assertEqual(out['geometry']['geometry_sha256'],g['geometry_sha256'])

    def test_cross_pocket_meander_and_manual_waypoints(self):
        s=self.spec(2)
        s['qubits'][0]['family']='cross';s['qubits'][1]['family']='pocket'
        # routes independent of qubit islands; same-net waypoints are supported.
        s['routes'][0]['style']='waypoints';s['routes'][0]['waypoints_um']=[[0,-1400]]
        s['routes'][0]['start_um']=[-1400,-1400];s['routes'][0]['end_um']=[1400,-1400]
        self.assertGreater(p.build(self.cfg,s)['routes'][0]['length_um'],0)
        s['routes'][0]['style']='meander';s['routes'][0]['waypoints_um']=[]
        s['routes'][0]['meander_depth_um']=70
        self.assertGreater(p.build(self.cfg,s)['routes'][0]['length_um'],2800)

    def test_user_defined_qubit_library_and_custom_coupler_geometry(self):
        s=self.spec(2)
        s['libraries']={'qubit_shapes':{
            'custom_twinpad':{
                'electrodes':{'pad_a':[[-252,-155,-12,155]],'pad_b':[[12,-155,252,155]]},
                'pins':{
                    'west':{'xy_um':[-180,0],'island':'pad_a'},
                    'east':{'xy_um':[180,0],'island':'pad_b'},
                    'north':{'xy_um':[0,155],'island':'pad_a'},
                    'south':{'xy_um':[0,-155],'island':'pad_a'}}}}}
        s['qubits'][0]['family']='custom_twinpad'
        s['couplers'][0]['kind']='custom_rects'
        s['couplers'][0]['electrodes']={
            'a':[[-720,-18,-10,18]], 'b':[[10,-18,720,18]]}
        g=p.build(self.cfg,s)
        self.assertEqual(g['components'][0]['family'],'custom_twinpad')
        self.assertEqual(g['couplers'][0]['kind'],'custom_rects')
        self.assertEqual(g['couplers'][0]['islands'],['Q0.pad_b','Q1.pad_a'])
        self.assertEqual(len(p.circuit(self.cfg,s)['qubits']),2)
        with tempfile.TemporaryDirectory() as d:
            p.export_package(self.cfg,s,d)
            self.assertEqual(read_json(Path(d)/'physical_spec.json')['libraries'],s['libraries'])
            self.assertGreater((Path(d)/'physical_HOLD.gds').stat().st_size,100)

    def test_custom_coupler_disconnected_or_short_fails_drc(self):
        s=self.spec(2);c=s['couplers'][0]
        c['kind']='custom_rects';c['electrodes']={
            'a':[[-80,-18,-10,18]], 'b':[[10,-18,80,18]]}
        with self.assertRaisesRegex(ValueError,'physically connect'):
            p.build(self.cfg,s)
        c['electrodes']={'a':[[-720,-18,25,18]], 'b':[[-25,-18,720,18]]}
        with self.assertRaisesRegex(ValueError,'DRC short'):
            p.build(self.cfg,s)

    def test_true_interdigitated_comb_and_squid_marker(self):
        s=self.spec();s['couplers'][0]['kind']='interdigitated';s['couplers'][0]['fingers']=4
        g=p.build(self.cfg,s)
        self.assertGreater(len(g['metal']['Q0.pad_b']),2)
        s['couplers'][0]['kind']='tunable_squid';s['couplers'][0]['ej_ghz']=8.3
        g=p.build(self.cfg,s)
        self.assertIn('K0_1.junction',g['ports'])
        self.assertIn(300,p.palace_configs(self.cfg,s,g)['eigenmode']['Boundaries']['LumpedPort'][-1].values())
        net=p.circuit(self.cfg,s)
        self.assertEqual(next(x for x in net['elements'] if x['id']=='K_K0_1')['kind'],'SQUID')

    def test_ground_is_actual_boolean_subtract_without_short(self):
        g=p.build(self.cfg,self.spec(4))
        ground=unary_union([box(r['x0'],r['y0'],r['x1'],r['y1']) for r in g['metal']['ground']])
        for name,rectangles in g['metal'].items():
            if name!='ground':
                shape=unary_union([box(r['x0'],r['y0'],r['x1'],r['y1']) for r in rectangles])
                self.assertGreater(shape.distance(ground),2.9)

    def test_bus_cpw_is_physically_isolated_and_not_a_direct_capacitor(self):
        s=self.spec();s['couplers'][0]['kind']='bus_cpw'
        g=p.build(self.cfg,s)
        self.assertIn('K0_1.bus',g['metal'])
        self.assertIn('K0_1.bus',g['terminals'])
        self.assertEqual(g['couplers'][0]['bus_net'],'K0_1.bus')
        net=p.circuit(self.cfg,s)
        parts=[e for e in net['elements'] if e['id'].startswith('K_K0_1')]
        self.assertEqual(len(parts),4)
        self.assertEqual({e['kind'] for e in parts},{'C','L'})
        self.assertFalse(any(e['id']=='K_K0_1' for e in net['elements']))

    def test_drc_short_and_invalid_topology_fail_closed(self):
        s=self.spec()
        s['routes'].append({**copy.deepcopy(s['routes'][0]),'id':'short','net':'short',
                            'start_um':list(s['routes'][0]['start_um']),'end_um':list(s['routes'][0]['end_um'])})
        with self.assertRaisesRegex(ValueError,'DRC short'):p.build(self.cfg,s)
        s=self.spec();s['couplers'][0]['b']='MISSING.west'
        with self.assertRaisesRegex(ValueError,'endpoints'):p.validate_spec(s)
        s=self.spec();s['stack'][0]['material']='aluminum'
        with self.assertRaisesRegex(ValueError,'dielectric material'):p.validate_spec(s)
        s=self.spec();s['stack'].append({**s['stack'][0],'id':'overlap','z0_um':-200,'thickness_um':150})
        with self.assertRaisesRegex(ValueError,'overlap'):p.validate_spec(s)

    def test_unsupported_multilayer_mesh_is_explicit_blocker(self):
        s=self.spec();s['stack'].append({'id':'top','role':'conductor','material':'aluminum',
                                        'z0_um':20,'thickness_um':.1,'gds_layer':6})
        g=p.build(self.cfg,s)
        # Place gmsh module stub to exercise preflight without external dependency.
        with patch.dict(sys.modules,{'gmsh':types.ModuleType('gmsh')}):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(ValueError,'one planar conductor'):
                    p.mesh(self.cfg,g,d)

    def test_palace_driven_one_excitation_per_case(self):
        s=self.spec(2);g=p.build(self.cfg,s);cfg=legacy.palace_configs(self.cfg,s,g)
        self.assertEqual(len([k for k in cfg if k.startswith('driven-')]),2)
        for k,c in cfg.items():
            self.assertEqual(c['Model']['Mesh'],'device.msh')
            if k.startswith('driven-'):
                self.assertEqual(sum(x.get('Excitation',0) for x in c['Boundaries']['LumpedPort']),1)

    def test_quantum_metal_sidecar_accepts_v2_manifest(self):
        from sqw.qmetal_interop import to_qdesign
        s=self.spec();manifest=p.qmetal_manifest(p.build(self.cfg,s))
        fake=types.ModuleType('qiskit_metal');designs=types.ModuleType('qiskit_metal.designs')
        core=types.ModuleType('qiskit_metal.qlibrary.core')
        lib=types.ModuleType('qiskit_metal.qlibrary')
        class Design:
            def __init__(self,enable_renderers):self.components={}
        class Component:
            def __init__(self,design,name):self.design=design;self.name=name;design.components[name]=self;self.make()
            def add_qgeometry(self,kind,shapes,layer,subtract):self.shapes=(shapes,layer)
        designs.DesignPlanar=Design;core.QComponent=Component
        with patch.dict(sys.modules,{'qiskit_metal':fake,'qiskit_metal.designs':designs,
           'qiskit_metal.qlibrary':lib,'qiskit_metal.qlibrary.core':core}):
            result=to_qdesign(manifest)
        self.assertEqual(set(result.components),{name for name in p.build(self.cfg,s)['metal']})


if __name__=='__main__':unittest.main()


class ParametricStudioIntegration(unittest.TestCase):
    def setUp(self):
        import io
        from sqw.studio.server import Application
        from sqw.studio.settings import Settings
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Application(Settings(Path(self.tmp.name)))
        self.app.auth.setup(self.app.auth.setup_token(),'tester@example.org','Tester','correct horse battery staple')
        self.token,self.csrf,self.user=self.app.auth.login('tester@example.org','correct horse battery staple','local')
        self.project=self.app.projects.create(self.user,'Flexible 2Q')

    def tearDown(self):self.tmp.cleanup()

    def request(self,path,authenticated=True):
        import io,json
        env={'REQUEST_METHOD':'GET','PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1:8000',
             'CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()}
        if authenticated:env['HTTP_COOKIE']='sqe_session='+self.token
        state={}
        def respond(status,headers):state.update(status=int(status.split()[0]),headers=dict(headers))
        body=self.app(env,respond);raw=b''.join(body)
        if hasattr(body,'close'):body.close()
        if dict(state['headers']).get('Content-Type','').startswith('application/json'):
            state['json']=json.loads(raw)
        state['raw']=raw
        return state

    def test_preview_endpoints_and_unauthorized(self):
        cfg,_=resolve(self.app.projects.detail(self.user,self.project)['document'])
        spec=p.default_spec(cfg,2)
        doc=self.app.projects.detail(self.user,self.project)['document']
        doc['physical_qpu']=spec
        self.app.projects.save(self.user,self.project,doc,1)
        prefix=f'/api/projects/{self.project}/physical'
        self.assertEqual(self.request(prefix+'/preview',False)['status'],401)
        view=self.request(prefix+'/preview')['json'];m=self.request(prefix+'/manifest')['json']
        self.assertEqual(view['geometry']['schema_version'],3)
        self.assertEqual(view['geometry']['geometry_sha256'],m['geometry_sha256'])
        self.assertEqual(self.request(prefix+'/gds')['status'],200)
        self.assertEqual(self.request('/api/quantumlab/parametric-preset')['json']['schema_version'],2)

    def test_persistent_package_job_references_revision(self):
        from contextlib import redirect_stdout
        import io
        from sqw.studio.runner import execute
        cfg,_=resolve(self.app.projects.detail(self.user,self.project)['document'])
        doc=self.app.projects.detail(self.user,self.project)['document']
        doc['physical_qpu']=p.default_spec(cfg,2)
        self.app.projects.save(self.user,self.project,doc,1)
        rev=self.app.projects.revise(self.user,self.project,'v0.7 source graph')
        job=self.app.jobs.enqueue(self.user,self.project,rev,'physical:package',mode='physical')
        with redirect_stdout(io.StringIO()):execute(self.app.store,job)
        final=self.app.store.one('SELECT * FROM jobs WHERE id=?',(job,))
        self.assertEqual(final['state'],'succeeded',final['error'])
        contract=read_json(self.app.store.root/'jobs'/job/'physical'/'contract.json')
        self.assertEqual(contract['schema_version'],3)
        self.assertEqual(len(contract['port_order']),2)
