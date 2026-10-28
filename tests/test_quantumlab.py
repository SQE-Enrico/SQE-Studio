"""Scientific regression and actual Studio API/worker contract for Quantum Design Lab."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from sqw import cad
from sqw.lab_layout import candidate
from sqw.quantumlab import analyze, preset, validate
from sqw.studio.server import Application
from sqw.studio.settings import Settings
from sqw.studio.runner import execute


class QuantumLabScientificTests(unittest.TestCase):
    def test_presets_have_expected_circuit_dimensions(self):
        for count in (1,4,9,16):
            d=preset(count)
            self.assertEqual(len(d['qubits']),count)
            self.assertEqual(len(validate(d)),count*2)
            result=analyze(d,'modes')
            self.assertEqual(len(result['modes']),count*2)
            self.assertEqual(len(result['qubit_assignments']),count)
            self.assertLess(result['modes'][0]['frequency_ghz'],result['modes'][-1]['frequency_ghz'])
            self.assertTrue(all(m['frequency_ghz']>0 for m in result['modes']))

    def test_single_transmon_is_physically_plausible(self):
        m=analyze(preset(1),'modes')
        q=m['qubit_assignments']['Q0']
        self.assertTrue(4.5<q['frequency_ghz']<5.5)
        self.assertTrue(-400<q['anharmonicity_mhz']<-100)
        self.assertTrue(.95<q['junction_participation']<=1)
        self.assertAlmostEqual(m['chi_mhz'][0][0],q['anharmonicity_mhz'],places=3)
        self.assertAlmostEqual(m['chi_mhz'][0][1],m['chi_mhz'][1][0],places=8)

    def test_lc_analytic_solution_and_zero_cross_kerr(self):
        d={'elements':[{'id':'C1','kind':'C','a':'x','b':'0','value':100.},
                       {'id':'L1','kind':'L','a':'x','b':'0','value':10.}], 'ports':[], 'qubits':[]}
        m=analyze(d,'modes')
        self.assertAlmostEqual(m['modes'][0]['frequency_ghz'],1/(2*np.pi*np.sqrt(10e-9*100e-15))/1e9,places=8)
        self.assertAlmostEqual(m['chi_mhz'][0][0],0)

    def test_s_parameters_are_reciprocal_and_passive(self):
        r=analyze(preset(1),'sparameters',{'start_ghz':4,'stop_ghz':7,'points':81})
        self.assertEqual(len(r['curves']),4)
        a={x['name']:x for x in r['curves']}
        self.assertTrue(np.allclose(a['S12']['db'],a['S21']['db'],atol=1e-4))
        self.assertTrue(all(max(x['db'])<1e-3 for x in r['curves']))
        self.assertIn('# GHZ S RI',r['touchstone'])
        self.assertEqual(len(r['touchstone'].splitlines()),83)

    def test_squid_flux_and_dynamics_limits(self):
        d=preset(1);el=next(e for e in d['elements'] if e['id']=='J0')
        el.update(kind='SQUID',asymmetry=.12,flux_phi0=0)
        f=analyze(d,'flux',{'points':21})
        self.assertEqual(len(f['flux_phi0']),21)
        self.assertLess(f['frequency_ghz'][10][0],f['frequency_ghz'][0][0])
        self.assertAlmostEqual(f['frequency_ghz'][-1][0],f['frequency_ghz'][0][0],places=5)
        t=analyze(d,'dynamics',{'sequence':'t1','points':51,'duration_us':10,'t1_us':10,'t2_us':10})
        self.assertAlmostEqual(t['p_excited'][0],1.0)
        self.assertAlmostEqual(t['p_excited'][-1],np.exp(-1),places=4)
        r=analyze(d,'dynamics',{'sequence':'ramsey','points':51,'duration_us':1,'t1_us':30,'t2_us':20})
        self.assertTrue(all(0<=p<=1 for p in r['p_excited']))

    def test_seeded_yield_optimizing_and_loss_budget(self):
        d=preset(4)
        r1=analyze(d,'yield',{'count':20,'seed':123})
        r2=analyze(d,'yield',{'count':20,'seed':123})
        self.assertEqual(r1,r2)
        self.assertTrue(0<=r1['yield_fraction']<=1)
        opt=analyze(d,'optimize')
        self.assertLess(opt['after_error_mhz'],opt['before_error_mhz'])
        self.assertEqual(d['elements'][1]['ej_ghz'],13) # no mutation of source
        q=analyze(d,'loss_budget')
        self.assertGreater(q['modes'][0]['estimated_t1_us'],0)

    def test_validation_rejects_malformed_designs(self):
        d=preset(1); d['elements'].append(copy.deepcopy(d['elements'][0]))
        with self.assertRaisesRegex(ValueError,'distinct'): validate(d)
        d=preset(1); d['elements'][0]['value']=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'):validate(d)
        d=preset(1); d['ports'][0]['node']='nonexistent'
        with self.assertRaisesRegex(ValueError,'unknown node'):validate(d)
        with self.assertRaises(ValueError):analyze(preset(1),'run_shell',{})
        with self.assertRaises(ValueError):analyze(preset(1),'modes',{'arbitrary':'bad'})

    def test_gds_is_valid_and_explicitly_concept_only(self):
        with tempfile.TemporaryDirectory() as temp:
            for n in (1,4,16):
                p=Path(temp)/f'concept{n}.gds'
                result=candidate(preset(n),p)
                self.assertIn('CONCEPT_ONLY',result['quality'])
                self.assertIn(91,cad.inspect_gds(p)['layers'])
                self.assertTrue(p.stat().st_size>100)


class QuantumLabIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.app=Application(Settings(self.root))
        token=self.app.auth.setup_token()
        self.app.auth.setup(token,'owner@example.org','Owner','correct horse battery staple')
        self.session,self.csrf,self.user=self.app.auth.login('owner@example.org','correct horse battery staple','local')
        self.project=self.app.projects.create(self.user,'QPU lab integration')
        p=self.app.projects.detail(self.user,self.project)
        doc=p['document'];doc['quantum_lab']=preset(4)
        self.app.projects.save(self.user,self.project,doc,1)

    def tearDown(self):self.folder.cleanup()

    def call(self,path,method='GET',data=None,authenticated=True):
        raw=json.dumps(data or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1:8000',
             'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)}
        if authenticated:env.update(HTTP_COOKIE='sqe_session='+self.session,HTTP_X_CSRF_TOKEN=self.csrf)
        response={}
        def start(status,headers):response.update(status=int(status.split()[0]),headers=dict(headers))
        value=self.app(env,start)
        content=b''.join(value)
        if hasattr(value,'close'):value.close()
        response['body']=content
        if response['headers']['Content-Type'].startswith('application/json'):response['json']=json.loads(content)
        return response

    def test_presets_protected_and_static_page_delivered(self):
        self.assertEqual(self.call('/api/quantumlab/preset',authenticated=False)['status'],401)
        r=self.call('/api/quantumlab/preset')
        self.assertEqual(r['status'],200)
        self.assertEqual(len(r['json']['qubits']),1)
        for f in ('quantumlab.html','quantumlab.js','quantumlab.css'):
            self.assertEqual(self.call('/'+f,authenticated=False)['status'],200)
        self.assertEqual(self.call('/secrets.txt',authenticated=False)['status'],404)

    def test_job_revision_execution_artifacts_and_capsule(self):
        revision=self.app.projects.revise(self.user,self.project,'Lab checkpoint')
        result=self.call('/api/projects/'+self.project+'/jobs','POST',{'revision_id':revision,'target':'lab:sparameters','mode':'lab','cpus':1,'memory_gb':2,'options':{'analysis_options':{'points':11}}})
        self.assertEqual(result['status'],200,result.get('json'))
        job=result['json']['id']
        execute(self.app.store,job)
        info=self.call(f'/api/projects/{self.project}/jobs/{job}')
        self.assertEqual(info['json']['job']['state'],'succeeded')
        self.assertIn('lab/result.json',info['json']['files'])
        self.assertFalse(any('\\' in f for f in info['json']['files']),
                         'Job API paths must be POSIX-style on every operating system')
        self.assertIn('lab/network.s2p',info['json']['files'])
        self.assertEqual(self.call(f'/api/projects/{self.project}/jobs/{job}/files/lab/result.json')['json']['analysis'],'sparameters')
        self.app.jobs.consolidate(self.user,job,'lab:sparameters','reviewed')
        capsule=self.app.projects.export(self.user,self.project)
        with __import__('zipfile').ZipFile(capsule) as archive:
            paths=archive.namelist()
            self.assertTrue(any(n.endswith('/lab/result.json') for n in paths))
            self.assertFalse(any('\\' in n for n in paths))

    def test_unrecognized_simulations_cannot_be_enqueued(self):
        revision=self.app.projects.revise(self.user,self.project,'Checkpoint')
        invalid=self.call('/api/projects/'+self.project+'/jobs','POST',{'revision_id':revision,'target':'lab:dangerous','mode':'lab','cpus':1,'memory_gb':2})
        self.assertEqual(invalid['status'],400)
        self.assertEqual(self.call(f'/api/projects/{self.project}/quantumlab/gds',authenticated=False)['status'],401)
        gds=self.call(f'/api/projects/{self.project}/quantumlab/gds')
        self.assertEqual(gds['status'],200)
        self.assertEqual(gds['headers']['X-Design-Status'],'concept-only-not-mask-qualified')
        self.assertGreater(len(gds['body']),100)


if __name__=='__main__':unittest.main()
