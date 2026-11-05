"""M19 selectable HTTP -> verified EM FIXTURE -> genuine native scqubits test.

The EM matrix/mesh are constructed protocol fixtures. No Palace solve, geometry
verification or reproduced literature-device result is claimed by this task.
"""
from __future__ import annotations

from copy import deepcopy
import http.cookiejar
from importlib import util, metadata
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .extraction_fixture import source_fixture, declaration


class FixtureSession:
    """Temporary loopback service and explicit, local test-only source injection."""
    def __init__(self, root):
        self.root=Path(root)
        self.csrf=''

    def __enter__(self):
        from ..server import make_server
        self.server=make_server(self.root/'data',0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.client=urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
        try:
            self.request('/api/setup',{'setup_token':self.server.app.setup_file.read_text(encoding='utf-8'),
                'email':'extraction@example.invalid','password':'TemporaryM19Workflow123!'})
            self.csrf=self.request('/api/login',{'email':'extraction@example.invalid',
                'password':'TemporaryM19Workflow123!'})['csrf']
            p=self.request('/api/projects',{'name':'M19 SOFTWARE EM FIXTURE','family':'transmon'})
            self.pid=p['id']
            folder,manifest,source=source_fixture(self.root/'fixture')
            revision=self.request(f'/api/projects/{self.pid}/commit',
                {'expected_revision':p['head'],'model':source['model']})['revision']
            with self.server.app.store.conn() as db:
                self.owner=db.execute('SELECT id FROM accounts').fetchone()['id']
            self.project=self.server.app.store.project(self.owner,self.pid,revision)
            output=self.server.app.store.root/'native-runs'/self.pid/('b'*32)/'output'
            shutil.copytree(folder,output)
            manifest.update(revision_id=revision,project_digest=self.project['revision_digest'])
            manifest['provenance'].update(used_revision=revision,
                used_project_sha256=self.project['revision_digest'],execution_kind='SOFTWARE_FIXTURE')
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
            self.run_id=self.server.app.store.put_run(self.owner,self.pid,revision,
                manifest['study_id'],'sqdmetal_palace',output.parent)
            self.server.app.store.set_run(self.run_id,'completed')
            self.output=output
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def response(self,path,body=None,*,csrf=True):
        headers={'Content-Type':'application/json'}
        if csrf:
            headers['X-CSRF-Token']=self.csrf
        request=urllib.request.Request(self.base+path,headers=headers,
            data=json.dumps(body,allow_nan=False).encode() if body is not None else None)
        try:
            response=self.client.open(request,timeout=20)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:
                raise ValueError('EXTRACTION_HTTP_RESPONSE_LIMIT')
            return response.status,json.loads(raw)

    def request(self,path,body=None):
        code,result=self.response(path,body)
        if code>=400:
            raise ValueError('HTTP_'+str(code)+': '+str(result)[:600])
        return result

    @property
    def url(self):
        return f'/api/projects/{self.pid}/runs/{self.run_id}/extraction'


def run_workflow(folder=None):
    if util.find_spec('scqubits') is None:
        return {'status':'BLOCKED','reason':'SCQUBITS_NOT_INSTALLED',
                'native_quantum_execution':'NOT_RUN','native_palace_execution':'NOT_RUN',
                'em_source_kind':'SOFTWARE_FIXTURE','scientific_qualification':'NOT_ESTABLISHED'}
    from ..adapters.scqubits_adapter import SCQUBITS_NUMERICAL_PIN
    try:
        version=metadata.version('scqubits')
    except metadata.PackageNotFoundError:
        version=None
    if version!=SCQUBITS_NUMERICAL_PIN:
        return {'status':'BLOCKED','reason':'SCQUBITS_COMPATIBILITY_PIN_MISMATCH',
                'observed_version':version,'required_version':SCQUBITS_NUMERICAL_PIN,
                'native_quantum_execution':'NOT_RUN','native_palace_execution':'NOT_RUN',
                'em_source_kind':'SOFTWARE_FIXTURE','scientific_qualification':'NOT_ESTABLISHED'}
    rows=[]
    began=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='sqe-m19-native-') as td:
        with FixtureSession(td) as session:
            for label,cj,quantity,value,unit in (
                    ('additional_2fF_declared_EJ',2.0,'EJ_over_h',15.,'GHz'),
                    ('additional_12fF_declared_LJ',12.0,'LJ',10.897434187118746,'nH')):
                current=session.request(f'/api/projects/{session.pid}')
                assumptions=declaration()
                assumptions['junction_capacitance_fF']=cj
                assumptions['junction_reference']=f'Designer software-test assumption: {cj} fF additional, unmeasured'
                assumptions['josephson'].update(quantity=quantity,value=value,unit=unit,
                    reference='Designer software-test Josephson assumption, not extracted from PEC')
                payload={'expected_revision':current['head'],'action':'preview','declaration':assumptions}
                preview=session.request(session.url,payload)
                if preview['solver_execution']!='NOT_EXECUTED':
                    raise ValueError('PREVIEW_MUST_NOT_EXECUTE_SOLVER')
                queued=session.request(session.url,{**payload,'action':'execute'})
                if queued['status']!='CONDITIONAL_NATIVE_JOB_QUEUED':
                    raise ValueError('NATIVE_EXTRACTION_JOB_NOT_QUEUED')
                run_id=queued['run_id']
                while True:
                    jobs=session.request(f'/api/projects/{session.pid}/runs')['runs']
                    job=next(j for j in jobs if j['id']==run_id)
                    if job['state'] not in ('queued','running'):
                        break
                    if time.monotonic()-began>195:
                        session.server.app.jobs.cancel(session.owner,session.pid,run_id)
                        return {'status':'TIMEOUT','reason':'NATIVE_EXTRACTION_BUDGET',
                                'models':rows,'em_source_kind':'SOFTWARE_FIXTURE','native_palace_execution':'NOT_RUN'}
                    time.sleep(.2)
                if job['state']!='completed':
                    info=session.server.app.store.run(session.owner,session.pid,run_id)
                    log=Path(info['path'])/'engine.log'
                    return {'status':'FAIL','reason':'NATIVE_EXTRACTION_JOB_'+job['state'].upper(),
                            'models':rows,'diagnostic':log.read_text(encoding='utf-8',errors='replace')[-12000:] if log.exists() else '',
                            'em_source_kind':'SOFTWARE_FIXTURE','native_palace_execution':'NOT_RUN'}
                result=session.request(f'/api/projects/{session.pid}/runs/{run_id}/result')
                extraction=result['conditional_extraction'];spectrum=result['spectrum']
                manifest=result['manifest']
                expected=preview['extraction']['extraction_sha256']
                if (extraction['extraction_sha256']!=expected or spectrum['extraction_sha256']!=expected or
                        extraction['source_result_metadata']['execution_kind']!='SOFTWARE_FIXTURE' or
                        manifest['revision_id']!=queued['revision']):
                    raise ValueError('NATIVE_EXTRACTION_LINEAGE_MISMATCH')
                okay=(spectrum['convergence']['numeric_status']=='NUMERICAL_PASS' and
                      extraction['spectrum_diagnostics']['status']=='NUMERICAL_PASS')
                levels=spectrum['levels']
                rows.append({'id':label,'status':'PASS' if okay else 'FAIL',
                    'native_quantum_execution':'PASS','native_palace_execution':'NOT_RUN',
                    'em_source_kind':'SOFTWARE_FIXTURE','source':extraction['source'],
                    'parameters':extraction['parameters'],'capacitances':extraction['capacitances'],
                    'f01_GHz':levels[1]-levels[0],'anharmonicity_GHz':levels[2]-2*levels[1]+levels[0],
                    'basis_convergence':spectrum['convergence'],'literature_comparison':extraction['spectrum_diagnostics'],
                    'native_versions':manifest['engine_version'],'native_artifacts':manifest['artifacts'],
                    'research_revision':queued['revision'],'extraction_sha256':expected,
                    'physical_validation':'NOT_ESTABLISHED','fabrication':'HOLD'})
                if folder is not None:
                    target=Path(folder)/'extraction';target.mkdir(parents=True,exist_ok=True)
                    with (target/(label+'.json')).open('x',encoding='utf-8') as out:
                        json.dump({'extraction':extraction,'spectrum':spectrum,'manifest':manifest},out,indent=2,allow_nan=False)
            sensitivity=rows[1]['parameters']['EC']<rows[0]['parameters']['EC'] and rows[1]['f01_GHz']<rows[0]['f01_GHz']
    return {'status':'PASS' if sensitivity and all(r['status']=='PASS' for r in rows) else 'FAIL',
            'execution_kind':'NATIVE_SCQUBITS_FROM_EXPLICIT_SOFTWARE_EM_FIXTURE',
            'native_quantum_execution':'PASS','native_palace_execution':'NOT_RUN',
            'em_source_kind':'SOFTWARE_FIXTURE','models':rows,
            'additional_CJ_sensitivity':'PASS' if sensitivity else 'FAIL',
            'workflow':'authenticated_saved_capacitance_readback_to_conditional_native_quantization',
            'scientific_qualification':'NOT_ESTABLISHED','fabrication':'HOLD'}
