"""SQE 0.6: independent physical, schematic, GDS, mesh/config and provenance checks.

No real Palace/Gmsh is asserted here; solver-boundary tests use a clearly fake
binary with exact test fixtures. All outputs remain labelled laboratory data.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from sqw import cad, physical_qpu as pu
from sqw.io import digest, read_json, sha256, write_json
from sqw.studio.process import document,resolve
from sqw.studio.server import Application
from sqw.studio.runner import execute
from sqw.studio.settings import Settings


class PhysicalContractTests(unittest.TestCase):
    def setUp(self):self.cfg,_=resolve(document())

    def test_sizes_tiling_identifiers_ports_and_fixed_unit_hash(self):
        for n in (1,2,4):
            with self.subTest(n=n):
                s=pu.default_spec(self.cfg,n)
                g=pu.build(self.cfg,s)
                self.assertEqual(len(g['terminals']),4*n)
                self.assertEqual(len(g['feed_ports']),2*n)
                self.assertEqual(len(g['junctions']),n)
                self.assertEqual(len(g['ports']),3*n)
                self.assertEqual(g['designed_interqubit_couplers'],0)
                self.assertEqual(len(set(g['physical_tags'].values())),len(g['physical_tags']))
                self.assertEqual(len(g['metal']),1+4*n)
                self.assertEqual(g['fabrication_status'],'HOLD')
                self.assertEqual(len(set(g['terminals'])),4*n)
                self.assertEqual(set(g['physical_tags']),set(g['metal'])|set(g['ports'])|{'air','silicon','outer'})
                m=pu.qmetal_manifest(g)
                self.assertEqual(m['geometry_sha256'],g['geometry_sha256'])
                self.assertEqual(len(m['components']),len(g['metal']))
                self.assertEqual(m['manifest_sha256'],digest({k:v for k,v in m.items() if k!='manifest_sha256'}))
                self.assertEqual(g['chip']['x1']-g['chip']['x0'],
                                 self.cfg['layout']['chip_size_um']*(2 if n>1 else 1))

    def test_junction_energy_changes_spec_but_not_positive_mask(self):
        a=pu.default_spec(self.cfg,2)
        b=copy.deepcopy(a);b['junction_ej_ghz'][0]+=3
        ga,gb=pu.build(self.cfg,a),pu.build(self.cfg,b)
        self.assertEqual(ga['geometry_sha256'],gb['geometry_sha256'])
        self.assertNotEqual(ga['design_spec_sha256'],gb['design_spec_sha256'])
        self.assertNotEqual(pu.palace_configs(self.cfg,a,ga)['eigenmode'],
                            pu.palace_configs(self.cfg,b,gb)['eigenmode'])

    def test_nominal_netlist_from_source_no_invented_interqubit_coupling(self):
        for n in (1,2,4):
            s=pu.default_spec(self.cfg,n)
            s['junction_ej_ghz']=[10+i for i in range(n)]
            s['nominal_cqr_ff']=4.321
            d=pu.circuit(self.cfg,s)
            self.assertEqual(len(d['qubits']),n)
            self.assertEqual(len(d['ports']),2*n)
            self.assertEqual(len(d['elements']),5*n)
            self.assertEqual([x['ej_ghz'] for x in d['elements'] if x['kind']=='JJ'],s['junction_ej_ghz'])
            self.assertEqual([x['value'] for x in d['elements'] if x['id'].startswith('Cqr')],[4.321]*n)
            self.assertNotIn('Cg0_1',[x['id'] for x in d['elements']])
            self.assertIn('user_declared_nominal',d['model'])

    def test_json_palace_contract_single_excitation_per_run(self):
        for n in (1,2,4):
            s=pu.default_spec(self.cfg,n);g=pu.build(self.cfg,s)
            c=pu.palace_configs(self.cfg,s,g)
            self.assertEqual(len([k for k in c if k.startswith('driven-')]),2*n)
            self.assertEqual([x['Index'] for x in c['electrostatic']['Boundaries']['Terminal']],list(range(1,4*n+1)))
            for j in range(2*n):
                conf=c[f'driven-{j+1}']
                excitations=[p['Index'] for p in conf['Boundaries']['LumpedPort'] if p.get('Excitation')]
                self.assertEqual(excitations,[j+1])
                self.assertEqual(conf['Problem']['Output'],f'driven-{j+1}')
                self.assertEqual(conf['Model']['Mesh'],'device.msh')
            self.assertEqual(len([p for p in c['eigenmode']['Boundaries']['LumpedPort'] if 'L' in p]),n)
            self.assertFalse(set(c['electrostatic']['Boundaries']['Ground']['Attributes']) &
                             {a for p in c['electrostatic']['Boundaries']['Terminal'] for a in p['Attributes']})

    def test_bad_specs_and_geometric_changes_fail_closed(self):
        s=pu.default_spec(self.cfg,1)
        for update in ({'size':16},{'junction_ej_ghz':[]},{'nominal_cq_ff':0},
                       {'topology':'unknown'},{'new_hidden_command':'rm -rf /'},
                       {'junction_cj_ff':[float('nan')]}):
            with self.subTest(update=update):
                bad={**s,**update}
                with self.assertRaises(ValueError):pu.validate_spec(bad)
        c=copy.deepcopy(self.cfg);c['layout']['cpw_gap_um']=7
        self.assertNotEqual(pu.build(self.cfg,s)['geometry_sha256'],pu.build(c,s)['geometry_sha256'])

    def test_gds_package_writes_exact_source_pieces_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=pu.default_spec(self.cfg,4)
            data=pu.export_package(self.cfg,s,tmp)
            base=Path(tmp)
            gds=base/'physical_HOLD.gds'
            self.assertGreater(gds.stat().st_size,1000)
            records=cad.inspect_gds(gds)
            self.assertGreater(records['polygons'],100)
            self.assertIn(91,records['layers'])
            self.assertIn(92,records['layers'])
            self.assertIn(99,records['layers'])
            c=read_json(base/'contract.json')
            self.assertEqual(c['geometry_sha256'],data['geometry']['geometry_sha256'])
            self.assertEqual(c['mask_status'],'HOLD')
            self.assertEqual(c['electromagnetic_status'],'NOT_SOLVED')
            self.assertEqual(read_json(base/'qmetal.json')['geometry_sha256'],c['geometry_sha256'])
            self.assertEqual(read_json(base/'nominal_circuit.json')['model'],
                             'differential_island_reduction__user_declared_nominal_C_and_L')

    def test_epr_analytical_and_user_supplied_loss_budget(self):
        out=pu.epr_from_table([5,6.5],[14,15],[[0.12,0.02],[0.04,0.1]])
        self.assertEqual(len(out['cross_kerr_signed_mhz']),2)
        self.assertLess(out['cross_kerr_signed_mhz'][0][1],0)
        self.assertLess(out['anharmonicity_mhz'][0],0)
        with self.assertRaises(ValueError):pu.epr_from_table([5],[14],[[1.1]])
        with self.assertRaises(ValueError):pu.purcell_estimate(5,5.2,100,12000)
        est=pu.purcell_estimate(5,7,50,12000)
        self.assertGreater(est['t1_us'],0)
        loss=pu.dielectric_loss_budget(5,{'substrate':.13,'interfaces':.02},
                                       {'substrate':2e-6,'interfaces':1e-3})
        self.assertAlmostEqual(loss['inverse_q'],.13*2e-6+.02*1e-3)
        self.assertGreater(loss['q_dielectric'],0)
        with self.assertRaises(ValueError):pu.dielectric_loss_budget(5,{'a':1.1},{'a':1e-4})

    def test_fake_palace_solver_provenance_and_capacitance_projection(self):
        """One numerical smoke test; fake output is never bundled as a solver result."""
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);s=pu.default_spec(self.cfg,1)
            pu.export_package(self.cfg,s,base)
            (base/'device.msh').write_bytes(b'gmsh TEST ONLY')
            write_json(base/'mesh.json',{'geometry_sha256':read_json(base/'contract.json')['geometry_sha256'],
                                         'mesh_sha256':sha256(base/'device.msh')})
            fake=base/'fake.py'
            fake.write_text('import csv,json,pathlib,sys\n'
                'cfg=json.loads(pathlib.Path(sys.argv[1]).read_text())\n'
                'name=cfg["Problem"]["Output"]; d=pathlib.Path(name);d.mkdir()\n'
                'kind=cfg["Problem"]["Type"]\n'
                'if kind=="Electrostatic":\n'
                ' f=(d/"terminal-C.csv").open("w",newline="");w=csv.writer(f)\n'
                ' w.writerow(["i"]+[f"C[i][{j}] (F)" for j in range(1,5)])\n'
                ' C=[[1.0e-13,-1.0e-14,0,0],[-1.0e-14,1.0e-13,0,0],[0,0,8e-14,0],[0,0,0,2e-14]]\n'
                ' for i,row in enumerate(C,1):w.writerow([i]+row)\n'
                ' f.close()\n'
                'elif kind=="Eigenmode":\n'
                ' (d/"eig.csv").write_text("i, f (GHz)\\n1, 5.05\\n")\n'
                ' (d/"port-EPR.csv").write_text("i,p[100]\\n1,0.1\\n")\n'
                'elif kind=="Driven":\n'
                ' (d/"port-S.csv").write_text("f (GHz), |S[1][1]|\\n5,0.1\\n")\n')
            with patch('sqw.palace_bridge.command',side_effect=lambda out,problem,ranks,executable:
                       ([sys.executable,str(fake),problem+'.json'],str(fake))):
                results=pu.solve(base,['electrostatic','eigenmode','driven-1','driven-2'])
            self.assertEqual(len(results),4)
            got=pu.extract_capacitance(base)
            self.assertEqual(got['source'],'verified_palace_electrostatic')
            self.assertAlmostEqual(got['projected_maxwell_c_ff'][0][0],55.0,places=5)
            self.assertEqual(len(got['differential_coordinate_order']),2)
            epr=pu.epr_from_palace_mapped(base,'i',{'J0':'p[100]'})
            self.assertEqual(epr['source'],'verified_palace_eigenmode_csv_mapped')
            self.assertEqual(epr['frequencies_ghz'],[5.05])
            with self.assertRaises(ValueError):pu.epr_from_palace_mapped(base,'i',{'J0':'bad-col'})
            (base/'eigenmode'/'port-EPR.csv').write_text('tampered')
            with self.assertRaises(ValueError):pu.epr_from_palace_mapped(base,'i',{'J0':'p[100]'})
            (base/'electrostatic'/'terminal-C.csv').write_text('tampered')
            with self.assertRaises(ValueError):pu.extract_capacitance(base)


class PhysicalStudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Application(Settings(Path(self.tmp.name)))
        self.app.auth.setup(self.app.auth.setup_token(),'owner@example.org','Owner','correct horse battery staple')
        self.token,self.csrf,self.user=self.app.auth.login('owner@example.org','correct horse battery staple','local')
        self.project=self.app.projects.create(self.user,'Physical SQE')

    def tearDown(self):self.tmp.cleanup()

    def get(self,path,auth=True):
        env={'REQUEST_METHOD':'GET','PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1:8000',
             'CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()}
        if auth:env.update(HTTP_COOKIE='sqe_session='+self.token)
        state={}
        def respond(status,headers):state.update(status=int(status.split()[0]),headers=dict(headers))
        body=self.app(env,respond);raw=b''.join(body)
        if hasattr(body,'close'):body.close()
        if state['headers'].get('Content-Type','').startswith('application/json'):
            state['json']=json.loads(raw)
        state['raw']=raw
        return state

    def test_permissions_endpoints_and_checksum(self):
        prefix=f'/api/projects/{self.project}/physical'
        for suffix in ('preview','manifest','gds'):
            self.assertEqual(self.get(prefix+'/'+suffix,False)['status'],401)
            self.assertEqual(self.get(prefix+'/'+suffix)['status'],200)
        preview=self.get(prefix+'/preview')['json']
        manifest=self.get(prefix+'/manifest')['json']
        self.assertEqual(preview['geometry']['geometry_sha256'],manifest['geometry_sha256'])
        self.assertEqual(preview['fabrication_status'],'HOLD')
        self.assertIn(b'SQE_PHYSICAL_HOLD',self.get(prefix+'/gds')['raw'])

    def test_physical_job_package_persistent_and_invalid_spec(self):
        doc=self.app.projects.detail(self.user,self.project)['document']
        cfg,_=resolve(doc)
        doc['physical_qpu']=pu.default_spec(cfg,2)
        self.app.projects.save(self.user,self.project,doc,1)
        revision=self.app.projects.revise(self.user,self.project,'Unified 2Q test')
        ident=self.app.jobs.enqueue(self.user,self.project,revision,'physical:package',mode='physical')
        with redirect_stdout(io.StringIO()):execute(self.app.store,ident)
        job=self.app.store.one('SELECT * FROM jobs WHERE id=?',(ident,))
        self.assertEqual(job['state'],'succeeded',job['error'])
        out=self.app.store.root/'jobs'/ident/'physical'
        self.assertEqual(read_json(out/'result.json')['fabrication_status'],'HOLD')
        self.assertEqual(sha256(out/'result.json'),(out/'result.sha256').read_text().strip())
        self.app.jobs.consolidate(self.user,ident,'physical:package','Reviewed contract only')
        with self.assertRaises(Exception):self.app.jobs.enqueue(self.user,self.project,revision,'physical:bad',mode='physical')


if __name__=='__main__':unittest.main()
