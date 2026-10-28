import copy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from contextlib import redirect_stdout

from sqw import cad, circuit, geometry
from sqw.io import read_json
from sqw.studio.auth import Problem
from sqw.studio.catalog import signature
from sqw.studio.jobs import Scheduler
from sqw.studio.process import document,wafer_positions,resolve
from sqw.studio.runner import execute
from sqw.studio.server import Application
from sqw.studio.settings import Settings

PASSWORD='correct horse battery staple'


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.app=Application(Settings(self.root))
        self.app.auth.setup(self.app.auth.setup_token(),'owner@example.org','Owner',PASSWORD)
        self.token,self.csrf,self.owner=self.app.auth.login('owner@example.org',PASSWORD,'local')
        self.project=self.app.projects.create(self.owner,'Quantum device')

    def tearDown(self): self.tmp.cleanup()

    def call(self,path,method='GET',data=None,token=None,csrf=None,origin='http://127.0.0.1:8000'):
        raw=json.dumps(data or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1:8000',
             'REMOTE_ADDR':'local','HTTP_ORIGIN':origin,'CONTENT_TYPE':'application/json',
             'CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)}
        if token: env['HTTP_COOKIE']='sqe_session='+token
        if csrf: env['HTTP_X_CSRF_TOKEN']=csrf
        response={}
        def start(status,headers): response.update(status=int(status.split()[0]),headers=dict(headers))
        body=self.app(env,start)
        payload=b''.join(body)
        if hasattr(body,'close'): body.close()
        response['body']=payload
        if response['headers'].get('Content-Type','').startswith('application/json'):
            response['json']=json.loads(payload)
        return response

    def login_user(self,email='other@example.org',role='researcher'):
        result=self.app.auth.invite(self.owner,email,'Other',role)
        raw=result['activation_url'].split('=')[-1]
        self.app.auth.activate(raw,PASSWORD)
        return self.app.auth.login(email,PASSWORD,'local')

    def run_job(self,target='report',baseline=None):
        revision=self.app.projects.revise(self.owner,self.project,'Test revision')
        job=self.app.jobs.enqueue(self.owner,self.project,revision,target,baseline_id=baseline)
        with redirect_stdout(io.StringIO()): execute(self.app.store,job)
        result=self.app.store.one('SELECT * FROM jobs WHERE id=?',(job,))
        self.assertEqual(result['state'],'succeeded',result['error'])
        return job

    def test_login_session_cookie_csrf_and_origin(self):
        r=self.call('/api/auth/login','POST',{'email':'owner@example.org','password':PASSWORD})
        self.assertEqual(r['status'],200)
        self.assertIn('HttpOnly',r['headers']['Set-Cookie'])
        self.assertIn('SameSite=Strict',r['headers']['Set-Cookie'])
        self.assertEqual(self.call('/api/projects')['status'],401)
        self.assertEqual(self.call('/api/projects','POST',{'name':'X'},self.token)['status'],403)
        self.assertEqual(self.call('/api/projects','POST',{'name':'X'},self.token,self.csrf,'https://foreign.invalid')['status'],403)
        self.assertEqual(self.call('/api/projects','POST',{'name':'X'},self.token,self.csrf)['status'],200)

    def test_setup_and_activation_are_one_use(self):
        with self.assertRaises(Problem): self.app.auth.setup('wrong','again@example.org','Again',PASSWORD)
        result=self.app.auth.invite(self.owner,'new@example.org','New')
        token=result['activation_url'].split('=')[-1]
        self.app.auth.activate(token,PASSWORD)
        with self.assertRaises(Problem): self.app.auth.activate(token,PASSWORD)
        stored=self.app.store.one('SELECT password FROM users WHERE email=?',('new@example.org',))['password']
        self.assertNotIn(PASSWORD,stored)

    def test_project_permissions_and_viewer_restrictions(self):
        _,_,other=self.login_user()
        with self.assertRaises(Problem): self.app.projects.access(other,self.project)
        self.app.projects.share(self.owner,self.project,other['email'],'viewer')
        self.app.projects.access(other,self.project)
        with self.assertRaises(Problem): self.app.projects.save(other,self.project,document(),1)
        self.app.projects.share(self.owner,self.project,other['email'],'editor')
        self.app.projects.save(other,self.project,document(),1)
        with self.assertRaises(Problem): self.app.projects.share(other,self.project,self.owner['email'],'viewer')

    def test_partial_draft_persistence_and_edit_conflict(self):
        doc=document(); doc['process']['chip_width_um']=None
        result=self.app.projects.save(self.owner,self.project,doc,1)
        self.assertEqual(result['draft_version'],2)
        with self.assertRaises(Problem): self.app.projects.save(self.owner,self.project,document(),1)
        reopened=Application(Settings(self.root)).projects.detail(self.owner,self.project)
        self.assertIsNone(reopened['document']['process']['chip_width_um'])
        self.assertTrue(self.app.jobs.readiness(self.owner,self.project)[0]['blockers'])
        with self.assertRaises(Problem):
            self.app.projects.revise(self.owner,self.project,'Conflicting snapshot',expected_version=1)
        revision=self.app.projects.revise(self.owner,self.project,'Incomplete but saved',expected_version=2)
        with self.assertRaises(Problem): self.app.jobs.enqueue(self.owner,self.project,revision,'report')

    def test_revision_restore_preserves_history(self):
        revision=self.app.projects.revise(self.owner,self.project,'Initial')
        doc=document(); doc['notes']='Changed'
        self.app.projects.save(self.owner,self.project,doc,1)
        self.app.projects.restore(self.owner,self.project,revision)
        self.assertEqual(self.app.projects.detail(self.owner,self.project)['document']['notes'],'')
        self.assertIsNotNone(self.app.store.one('SELECT id FROM revisions WHERE id=?',(revision,)))

    def test_real_worker_pipeline_and_changed_experiment_checkpoint(self):
        first=self.run_job()
        self.app.jobs.consolidate(self.owner,first,'quantize','Checked spectrum')
        doc=self.app.projects.detail(self.owner,self.project)['document']
        doc['config']['experiment']['T1_intrinsic_us']=25.
        self.app.projects.save(self.owner,self.project,doc,1)
        second=self.run_job(baseline=first)
        reused={r['stage']:r['reused_from'] for r in self.app.store.rows('SELECT * FROM results WHERE job_id=?',(second,))}
        self.assertEqual(reused['layout'],first)
        self.assertEqual(reused['quantize'],first)
        self.assertIsNone(reused['experiment'])
        old=read_json(self.root/'jobs'/first/'run/experiment/model.json')
        new=read_json(self.root/'jobs'/second/'run/experiment/model.json')
        self.assertLess(new['T1_effective_us'],old['T1_effective_us'])
        self.assertTrue((self.root/'jobs'/first/'run/report.html').exists())
        response=self.call(f'/api/projects/{self.project}/jobs/{first}/files/run/report.html',token=self.token)
        self.assertEqual(response['status'],200)
        self.assertIn('sandbox allow-same-origin',response['headers']['Content-Security-Policy'])
        self.assertNotIn('allow-scripts',response['headers']['Content-Security-Policy'])

    def test_junction_geometry_drives_the_forward_circuit(self):
        doc=document()
        cfg,_=resolve(doc)
        first=circuit.junction(cfg)
        doc['process']['junction_overlap_nm']=300.
        changed,_=resolve(doc)
        second=circuit.junction(changed)
        self.assertAlmostEqual(second['Ic_nA']/first['Ic_nA'],300/240)
        self.assertAlmostEqual(second['Cj_fF']/first['Cj_fF'],300/240)
        self.assertAlmostEqual(changed['circuit']['EJ_GHz']/cfg['circuit']['EJ_GHz'],300/240)
        a=circuit.parameters(cfg,circuit.surrogate(cfg,geometry.build(cfg)))
        b=circuit.parameters(changed,circuit.surrogate(changed,geometry.build(changed)))
        self.assertGreater(b['f01_GHz'],a['f01_GHz'])
        doc['process'].update(junction_kind='lab_gds',junction_declared_Ic_nA=50.,junction_declared_Cj_fF=8.)
        lab,_=resolve(doc)
        self.assertAlmostEqual(circuit.junction(lab)['Ic_nA'],50.)
        self.assertAlmostEqual(circuit.junction(lab)['Cj_fF'],8.)

    def test_process_chip_wafer_candidates_and_lithography_rules(self):
        job=self.run_job('fabrication')
        out=self.root/'jobs'/job/'fabrication'
        self.assertIn(2,cad.inspect_gds(out/'chip_candidate.gds')['layers'])
        self.assertIn(3,cad.inspect_gds(out/'chip_candidate.gds')['layers'])
        result=read_json(out/'process_review.json')
        self.assertEqual(result['status'],'PROCESS_REVIEW_REQUIRED')
        self.assertGreater(result['die_count'],1)
        p=document()['process']
        for d in wafer_positions(p):
            import math
            radius=(p['wafer_diameter_mm']/2-p['wafer_edge_exclusion_mm'])*1000
            self.assertLessEqual(math.hypot(abs(d['x_um'])+(p['chip_width_um']+p['dicing_street_um'])/2,
                                            abs(d['y_um'])+(p['chip_height_um']+p['dicing_street_um'])/2),radius)
        doc=document(); doc['process']['min_metal_width_um']=20
        with self.assertRaises(ValueError): resolve(doc)

    def test_capsule_roundtrip_draft_results_and_asset_ids(self):
        from PIL import Image
        image=io.BytesIO(); Image.new('RGB',(8,8),'black').save(image,format='PNG')
        asset=self.app.projects.asset(self.owner,self.project,'logo.png','logo',image.getvalue())
        doc=document(); doc['process']['logo_asset_id']=asset; doc['notes']='Partial project notes'
        self.app.projects.save(self.owner,self.project,doc,1)
        self.run_job('quantize')
        path=self.app.projects.export(self.owner,self.project)
        clone=self.app.projects.import_capsule(self.owner,path.read_bytes())
        imported=self.app.projects.detail(self.owner,clone)
        self.assertEqual(imported['document']['notes'],'Partial project notes')
        self.assertNotEqual(imported['document']['process']['logo_asset_id'],asset)
        self.assertEqual(len(imported['jobs']),1)
        self.assertTrue(imported['assets'])
        self.assertTrue((self.root/'jobs'/imported['jobs'][0]['id']/'run/parameters.json').exists())

    def test_archive_path_traversal_rejected(self):
        z=io.BytesIO()
        with zipfile.ZipFile(z,'w') as archive: archive.writestr('../escape','bad')
        with self.assertRaises(Problem): self.app.projects.import_capsule(self.owner,z.getvalue())

    def test_macro_review_permissions_and_proposed_document(self):
        _,_,researcher=self.login_user()
        with self.assertRaises(Problem): self.app.jobs.save_macro(researcher,'Unsafe','def apply(project): return project')
        macro=self.app.jobs.save_macro(self.owner,'Set target','def apply(project):\n from pathlib import Path\n (Path(ARTIFACTS_DIR)/"analysis.txt").write_text("custom analysis")\n project["config"]["targets"]["f01_GHz"]=5.3\n return project\n')
        revision=self.app.projects.revise(self.owner,self.project,'Before macro')
        with self.assertRaises(Problem): self.app.jobs.enqueue(self.owner,self.project,revision,'macro:'+macro)
        self.app.jobs.approve_macro(self.owner,macro)
        job=self.app.jobs.enqueue(self.owner,self.project,revision,'macro:'+macro)
        with redirect_stdout(io.StringIO()): execute(self.app.store,job)
        result=read_json(self.root/'jobs'/job/'macro_result.json')
        self.assertEqual(result['config']['targets']['f01_GHz'],5.3)
        self.assertEqual((self.root/'jobs'/job/'macro_artifacts/analysis.txt').read_text(),'custom analysis')
        self.assertEqual(self.app.projects.detail(self.owner,self.project)['document']['config']['targets']['f01_GHz'],5.)

    def test_queue_cancellation_and_resource_overbooking(self):
        revision=self.app.projects.revise(self.owner,self.project,'Queue')
        job=self.app.jobs.enqueue(self.owner,self.project,revision,'spec',cpus=4,memory_gb=8)
        self.app.jobs.cancel(self.owner,job)
        self.assertEqual(self.app.store.one('SELECT state FROM jobs WHERE id=?',(job,))['state'],'cancelled')
        with self.assertRaises(Problem): self.app.jobs.enqueue(self.owner,self.project,revision,'spec',cpus=5)
        first=self.app.jobs.enqueue(self.owner,self.project,revision,'spec',cpus=4,memory_gb=8)
        second=self.app.jobs.enqueue(self.owner,self.project,revision,'spec')
        with self.app.store.connect(True) as db:
            db.execute("UPDATE jobs SET state='running',started=?,heartbeat=? WHERE id=?",(time.time(),time.time(),first))
        self.assertIsNone(Scheduler(self.app.store).tick())
        self.assertEqual(self.app.store.one('SELECT state FROM jobs WHERE id=?',(second,))['state'],'queued')

    def test_corrupt_capsule_leaves_no_partial_project(self):
        self.app.projects.asset(self.owner,self.project,'reference.txt','data',b'original research data')
        capsule=self.app.projects.export(self.owner,self.project)
        buffer=io.BytesIO()
        with zipfile.ZipFile(capsule) as source,zipfile.ZipFile(buffer,'w') as target:
            for member in source.infolist():
                payload=source.read(member)
                if member.filename.startswith('assets/'): payload=b'changed research data!'
                target.writestr(member.filename,payload)
        before=self.app.projects.list(self.owner)
        with self.assertRaises(Problem): self.app.projects.import_capsule(self.owner,buffer.getvalue())
        self.assertEqual(self.app.projects.list(self.owner),before)

    def test_capsule_upload_is_read_in_bounded_chunks(self):
        capsule=self.app.projects.export(self.owner,self.project)
        class BoundedInput(io.BytesIO):
            def read(self,n=-1):
                if n<0 or n>1024**2: raise AssertionError('Unbounded capsule upload read')
                return super().read(n)
        raw=capsule.read_bytes()
        env={'REQUEST_METHOD':'POST','PATH_INFO':'/api/projects/import','QUERY_STRING':'',
             'HTTP_HOST':'127.0.0.1:8000','REMOTE_ADDR':'local','HTTP_ORIGIN':'http://127.0.0.1:8000',
             'CONTENT_TYPE':'application/octet-stream','CONTENT_LENGTH':str(len(raw)),
             'HTTP_COOKIE':'sqe_session='+self.token,'HTTP_X_CSRF_TOKEN':self.csrf,'wsgi.input':BoundedInput(raw)}
        response={}
        def start(status,headers): response['status']=int(status.split()[0])
        payload=json.loads(b''.join(self.app(env,start)))
        self.assertEqual(response['status'],200,payload)
        self.assertEqual(self.app.projects.detail(self.owner,payload['id'])['name'],'Quantum device (imported)')

    def test_source_and_artifact_access_do_not_cross_projects(self):
        first=self.run_job('spec')
        _,_,other=self.login_user()
        token,csrf,_=self.app.auth.login(other['email'],PASSWORD,'second')
        r=self.call(f'/api/projects/{self.project}/jobs/{first}',token=token)
        self.assertEqual(r['status'],403)
        r=self.call(f'/api/projects/{self.project}/jobs/{first}/files/../../studio.sqlite3',token=self.token)
        self.assertEqual(r['status'],404)
        r=self.call('/api/source/../../studio.sqlite3',token=self.token)
        self.assertEqual(r['status'],404)
        self.assertEqual(self.call('/api/source/circuit',token=self.token)['status'],200)


if __name__=='__main__': unittest.main()
