import copy
import pytest
from sqe_studio.contracts import fresh_project,validate_project,stage_status,ValidationError,digest
from sqe_studio.store import Store,Conflict,NotFound

def test_one_canonical_model_and_stages():
    m=fresh_project('Test Quantum Device','transmon')
    assert validate_project(m) is m
    assert stage_status(m)['layout']=='draft_saved'
    assert stage_status(m)['em']=='not_started'
    assert stage_status(m)['fabrication']=='not_started'
    assert digest(m)==digest(copy.deepcopy(m))

def test_no_nan_scripts_or_unknown_fields():
    m=fresh_project('Test Circuit','generic')
    m['intent']['targets']=[{'name':'S21','value':float('nan')}]
    with pytest.raises(ValidationError):validate_project(m)
    m=fresh_project('Test Circuit','generic');m['unexpected']='unsafe'
    with pytest.raises(ValidationError):validate_project(m)
    m=fresh_project('Test Circuit','generic');m['studies']=[{'id':'evil','engine':'exec_python','kind':'anything','inputs':{}}]
    with pytest.raises(ValidationError):validate_project(m)

def test_revision_cas_and_scope(tmp_path):
    s=Store(tmp_path);s.setup('user@example.org','GoodPassword1234567')
    with pytest.raises(Conflict):s.setup('other@example.org','GoodPassword1234567')
    token,csrf=s.login('user@example.org','GoodPassword1234567')
    uid=s.session(token)['user_id']
    assert len(csrf)>20
    p=s.create(uid,'Test Circuit','generic')
    m=p['model'];m['intent']['targets']=[{'name':'f01','value':5.1,'unit':'GHz'}]
    next_id=s.commit(uid,p['id'],p['head'],m)
    assert s.project(uid,p['id'])['revision']==next_id
    assert s.project(uid,p['id'],p['head'])['model']['intent']['targets']==[]
    with pytest.raises(Conflict):s.commit(uid,p['id'],p['head'],m)
    with pytest.raises(NotFound):s.project('unrelated_user',p['id'])
    s.logout(token)
    assert s.session(token) is None

def test_worker_fail_closed_without_external_engines(tmp_path):
    from sqe_studio.worker import run
    import json
    m=fresh_project('A Fluxonium','fluxonium')
    for eng in ('sqdmetal_palace','josephson_circuits'):
        inp=tmp_path / (eng+'.json');out=tmp_path / (eng+'-out')
        study={'id':'study1','engine':eng,'kind':'native','inputs':{}}
        inp.write_text(json.dumps({'project':m,'project_digest':digest(m),'revision_id':'r1','study':study}))
        try:run(inp,out)
        except Exception as exc:assert 'requires' in str(exc).lower() or 'awaits' in str(exc).lower()
        else:raise AssertionError('Unsafe engine unexpectedly accepted empty physical inputs')
        assert not any(out.glob('*.gds'))

def test_engine_job_without_installed_native_engine_is_not_faked(tmp_path):
    import time
    from sqe_studio.jobs import Jobs
    s=Store(tmp_path);s.setup('engine@example.org','LongSecretPassword56789')
    token,_=s.login('engine@example.org','LongSecretPassword56789');uid=s.session(token)['user_id']
    p=s.create(uid,'Native Only','generic')
    m=p['model'];m['studies']=[{'id':'quantum_primary','engine':'scqubits','kind':'spectrum',
        'inputs':{'model':'Transmon','parameters':{'EJ':15.,'EC':.25,'ng':0.,'ncut':25},'levels':5}}]
    rev=s.commit(uid,p['id'],p['head'],m)
    j=Jobs(s);rid=j.start(uid,p['id'],rev,'quantum_primary')
    # Windows may spend several seconds importing native scqubits.
    deadline=time.monotonic()+55
    while True:
        info=s.run(uid,p['id'],rid)
        if info['state'] not in ('queued','running') or time.monotonic()>=deadline:break
        time.sleep(.15)
    if info['state'] in ('queued','running'):
        j.cancel(uid,p['id'],rid)
        pytest.fail('Native worker did not reach a terminal state within 55 seconds; '
                    'cancelled test job. Last state: '+repr(info['state']))
    from pathlib import Path
    from sqe_studio.orchestration.artifacts import verify_manifest
    folder=Path(info['path'])/'output'
    if info['state']=='completed':
        # Native scqubits may be installed on the target laptop. Completion
        # is acceptable ONLY if the worker wrote revision-bound real evidence.
        reference=verify_manifest(folder, revision_id=rev,
                                  project_digest=digest(m),
                                  study_id='quantum_primary', engine='scqubits')
        assert reference.engine_version and reference.engine_version != 'TEST-FIXTURE-ONLY'
        assert (folder/'spectrum.json').is_file()
    else:
        assert info['state']=='failed', info
        assert (folder/'FAILURE.json').is_file() or (Path(info['path'])/'LIFECYCLE_FAILURE.json').is_file()
        assert not (folder/'RESULT_MANIFEST.json').exists()
    assert not list(folder.glob('*.gds'))
