"""Structural RF Results tests: fixture samples are NOT native solver evidence."""
from __future__ import annotations
from sqe_studio.web_assets import javascript_bundle

import copy
import hashlib
import json
from pathlib import Path

import pytest

from sqe_studio.interop.native_rf_evidence import native_rf_evidence, NativeRFEvidenceError
from sqe_studio.orchestration.artifacts import verify_manifest, ArtifactInvalid

REV = 'a' * 32
DIGEST = 'b' * 64


def fixture_rf(tmp_path, *, pumped=False):
    root = tmp_path / 'output'
    root.mkdir(parents=True)
    data = {
        'josephson_request.tsv': b'fixture request\n',
        'josephson_fixed_worker.jl': b'fixture julia source\n',
        'josephson_native_metadata.tsv': b'fixture metadata\n',
        'josephson_native_stdout.log': b'fixture stdout\n',
        'josephson_native_stderr.log': b'',
    }
    points = [4e9, 5e9]
    rows = ['frequency_hz\toutput_port\tinput_port\treal\timag']
    for f in points:
        for po in [1, 2]:
            for pi in [1, 2]:
                rows.append(f'{f:.17g}\t{po}\t{pi}\t0.5\t-0.25')
    data['josephson_native_sparameters.tsv'] = ('\n'.join(rows) + '\n').encode()
    for name, raw in data.items():
        (root / name).write_bytes(raw)
    side = {
        'schema': 'sqe.josephson-port-contract.v1',
        'analysis': 'rf_harmonic_balance' if pumped else 'rf_linear',
        'native_process_exit_code': 0, 'scientific_status': 'review_required',
        'frequency_unit': 'Hz', 'native_frequency_input_unit': 'rad/s',
        'mode': '(0,)->(0,) signal-only; nonlinear idler S not exported',
        'observable': {'quantity':'complex_scattering_amplitude', 'unit':'1',
                       'representation':'real_and_imaginary', 'wave_convention':'native_power_wave',
                       'port_reference_plane':'explicit_schematic_node_to_ground_0'},
        's_parameter_order': 'frequency-major, output_port-major, input_port-minor',
        's_parameter_unit': 'dimensionless_complex_native_power_wave',
        'artifact_sha256': {name:hashlib.sha256(raw).hexdigest() for name,raw in data.items()},
        'ports': [{'number':n,'node':node,'positive_terminal':node,
                   'negative_terminal':'0','reference_impedance_ohm':50.}
                  for n,node in [(1,'in'),(2,'out')]],
        'port_order': [1,2], 'frequency_points_hz': points,
        'native_engine_version': 'fixture-not-solver',
    }
    (root / 'josephson_ports.json').write_text(json.dumps(side), encoding='utf-8')
    manifest = {
        'schema':'sqe.artifact.v1', 'engine':'josephson_circuits',
        'engine_version':'fixture-not-solver', 'artifact_type':'josephson.sparameters',
        'scientific_status':'review_required','fabrication_status':'HOLD',
        'revision_id':REV,'project_digest':DIGEST,'study_id':'RF1',
        'provenance':{'used_revision':REV,'used_project_sha256':DIGEST},'parents':[],
        'artifacts':[{'name':p.name,'bytes':p.stat().st_size,
                      'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in sorted(root.iterdir())]
    }
    (root / 'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    return root,manifest


def test_bounded_complex_rf_view_is_revision_verified_and_not_physics_approval(tmp_path):
    root, manifest=fixture_rf(tmp_path)
    verify_manifest(root,revision_id=REV,project_digest=DIGEST,study_id='RF1',engine='josephson_circuits')
    out=native_rf_evidence(root,manifest)
    assert out['schema']=='sqe.rf-native-results-screen.v1'
    assert out['sample_count']==8
    assert out['samples'][0]['magnitude']==pytest.approx(0.559016994)
    assert out['samples'][0]['phase_rad']<0
    assert out['ports'][0]['reference_impedance_ohm']==50
    assert out['cross_engine_mapping'].startswith('BLOCKED')
    assert out['physical_validation']=='NOT_ESTABLISHED'
    assert out['fabrication']=='HOLD'
    assert out['harmonic_balance_residual']=='NOT_APPLICABLE'


def test_linear_rf_matrix_sums_and_symmetry_are_only_numeric(tmp_path):
    root,manifest=fixture_rf(tmp_path)
    screen=native_rf_evidence(root,manifest)
    diagnostics=screen['matrix_diagnostics']
    assert diagnostics['status']=='NUMERIC_LINEAR_S_MATRIX_SCREEN_ONLY'
    assert diagnostics['physical_validation']=='NOT_ESTABLISHED'
    assert len(diagnostics['rows'])==2
    for row in diagnostics['rows']:
        assert row['outgoing_power_by_input'][0]['outgoing_power_sum']==pytest.approx(.625)
        assert row['outgoing_power_by_input'][1]['outgoing_power_sum']==pytest.approx(.625)
        assert row['outgoing_power_by_input'][0]['above_unity_numeric'] is False
        assert row['max_pairwise_reciprocity_difference']==0


def test_numeric_rf_unity_exceedance_is_not_scientific_approval(tmp_path):
    root,manifest=fixture_rf(tmp_path)
    from sqe_studio.interop.native_rf_evidence import _linear_s_matrix_diagnostics
    points=[{'frequency_hz':5e9,'output_port':po,'input_port':pi,
             'real':1.2 if po==pi else 0,'imag':0}
            for po in (1,2) for pi in (1,2)]
    out=_linear_s_matrix_diagnostics(points,[5e9],[1,2],'rf_linear')
    assert all(p['above_unity_numeric'] for p in out['rows'][0]['outgoing_power_by_input'])
    assert out['physical_validation']=='NOT_ESTABLISHED'
    assert out['rows'][0]['max_pairwise_reciprocity_difference']==0


def test_pumped_hb_never_promotes_idler_gain_or_residual(tmp_path):
    root,manifest=fixture_rf(tmp_path,pumped=True)
    out=native_rf_evidence(root,manifest)
    assert out['signal_mode']=='0_to_0_only'
    assert out['harmonic_balance_residual']=='NOT_EXPORTED'
    assert out['numeric_status']=='NATIVE_RF_OBSERVATIONS_ONLY'
    assert out['matrix_diagnostics']['status']=='NOT_APPLICABLE_PUMPED_CHANNELS_NOT_EXPORTED'
    assert out['matrix_diagnostics']['rows']==[]


@pytest.mark.parametrize('change', [
    lambda side: side.update({'port_order':[2,1]}),
    lambda side: side.update({'frequency_unit':'GHz'}),
    lambda side: side.update({'native_process_exit_code':1}),
    lambda side: side.update({'artifact_sha256':{}}),
    lambda side: side['ports'][0].update({'reference_impedance_ohm':-50}),
    lambda side: side['observable'].update({'wave_convention':'unknown'}),
    lambda side: side.update({'mode':'idler channels validated'}),
])
def test_invalid_sidecar_fails_closed(tmp_path,change):
    root,manifest=fixture_rf(tmp_path)
    sidefile=root/'josephson_ports.json'
    side=json.loads(sidefile.read_text())
    change(side)
    sidefile.write_text(json.dumps(side),encoding='utf-8')
    with pytest.raises(NativeRFEvidenceError):
        native_rf_evidence(root,manifest)
    with pytest.raises(ArtifactInvalid):
        verify_manifest(root,revision_id=REV,project_digest=DIGEST,study_id='RF1',engine='josephson_circuits')


@pytest.mark.parametrize('alter', [
    '4000000000\t1\t1\t0.5\tnan',
    '4000000000\t2\t1\t0.5\t-0.25',
    '4000000000\t1\t1\t1e309\t0',
    '4000000000\t1\t1\t0.5\t-0.25\tEXTRA',
])
def test_corrupt_sample_never_appears_as_verified_native_rf(tmp_path,alter):
    root,manifest=fixture_rf(tmp_path)
    name='josephson_native_sparameters.tsv'
    tsv=root/name
    contents=tsv.read_text().splitlines()
    contents[1]=alter
    tsv.write_text('\n'.join(contents)+'\n')
    with pytest.raises(NativeRFEvidenceError):
        native_rf_evidence(root,manifest)
    with pytest.raises(ArtifactInvalid):
        verify_manifest(root,revision_id=REV,project_digest=DIGEST,study_id='RF1',engine='josephson_circuits')


def test_rf_reader_ignores_other_engines(tmp_path):
    root,m=fixture_rf(tmp_path)
    assert native_rf_evidence(root,{**m,'engine':'scqubits'}) is None
    assert native_rf_evidence(root,{**m,'artifact_type':'palace.eigenmodes'}) is None


def test_web_app_and_server_use_shared_generic_results(tmp_path):
    source=Path(__file__).resolve().parents[2]/'src'/'sqe_studio'
    js=javascript_bundle((source/'web'/'app.js').parent).decode('utf-8')
    server=(source/'http_api/results.py').read_text(encoding='utf-8')
    assert 'function nativeRFResultsView(screen)' in js
    assert 'if(r.rf_evidence)view+=nativeRFResultsView(r.rf_evidence)' in js
    assert 'result[\'rf_evidence\']=native_rf_evidence(folder/\'output\',manifest)' in server
    assert server.index('verify_manifest(folder/\'output\'') < server.index("result['rf_evidence']=native_rf_evidence")


def test_authenticated_results_uses_real_verification_before_rf_view(tmp_path):
    """HTTP/ACL/hash behavior exercised with clearly synthetic RF table bytes."""
    import http.cookiejar
    import shutil
    import threading
    import urllib.error
    import urllib.request
    from sqe_studio.server import make_server

    server=make_server(tmp_path/'app-data',port=0)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    base=f'http://127.0.0.1:{server.server_port}'
    client=urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.ProxyHandler({}))
    csrf=''
    def req(path,method='GET',body=None):
        headers={'Content-Type':'application/json'}
        if csrf: headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,headers=headers,method=method,
                                       data=json.dumps(body).encode() if body is not None else None)
        try: response=client.open(request,timeout=7)
        except urllib.error.HTTPError as error: response=error
        with response:
            return response.status, json.loads(response.read())
    try:
        assert req('/api/projects')[0]==401
        token=server.app.setup_file.read_text(encoding='ascii')
        assert req('/api/setup','POST',{'email':'rf@test.invalid',
                'password':'rf-review-test-password','setup_token':token})[0]==200
        code,auth=req('/api/login','POST',{'email':'rf@test.invalid',
                                         'password':'rf-review-test-password'})
        assert code==200
        csrf=auth['csrf']
        code,created=req('/api/projects','POST',{'name':'RF test only','family':'transmon'})
        assert code==201
        pid, base_rev = created['id'], created['head']
        saved = copy.deepcopy(created['model'])
        saved['intent']['targets'] = [
            {'name':'rf_S21_mag_at_5GHz','unit':'1','value':0.56,'tolerance':0.02},
            {'name':'rf_S21_dB_at_5GHz','unit':'dB','value':-5.,'tolerance':0.1}]
        status, commit = req(f'/api/projects/{pid}/commit','POST',
                             {'expected_revision':base_rev,'model':saved})
        assert status == 200, commit
        rev = commit['revision']
        # A newer revision must never change goals displayed for an older job.
        latest = copy.deepcopy(saved)
        latest['intent']['targets'][0]['value'] = 100.
        status, _ = req(f'/api/projects/{pid}/commit','POST',
                        {'expected_revision':rev,'model':latest})
        assert status == 200
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        digest=server.app.store.project(owner,pid,rev)['revision_digest']
        run='e'*32
        folder=server.app.store.root/'native-runs'/pid/run
        folder.mkdir(parents=True)
        src,manifest=fixture_rf(tmp_path/'fixture')
        out=folder/'output'
        shutil.copytree(src,out)
        manifest.update(revision_id=rev,project_digest=digest,
                        provenance={'used_revision':rev,'used_project_sha256':digest})
        (out/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
        server.app.store.put_run(owner,pid,rev,'RF1','josephson_circuits',folder)
        server.app.store.set_run(run,'completed')
        url=f'/api/projects/{pid}/runs/{run}/result'
        code,result=req(url)
        assert code==200,result
        rf=result['rf_evidence']
        assert rf['sample_count']==8
        assert rf['samples'][0]['frequency_hz']==4e9
        assert rf['fabrication']=='HOLD'
        assert result['design_target_screen']['revision_id']==rev
        assert result['design_target_screen']['rows'][0]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
        assert result['design_target_screen']['rows'][0]['target']==0.56
        assert result['design_target_screen']['rows'][1]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
        assert result['design_target_screen']['rows'][1]['observed']==pytest.approx(20*__import__('math').log10((.5**2+.25**2)**.5))
        (out/'josephson_native_sparameters.tsv').write_text('tampered',encoding='utf-8')
        assert req(url)[0]==409
        assert req('/api/logout','POST',{})[0]==200
        assert req(url)[0]==401
    finally:
        server.shutdown();server.server_close();worker.join(timeout=4)


def test_revision_bound_rf_targets_use_only_exact_native_frequency(tmp_path):
    """Synthetic S samples test the real numeric feedback path, NOT RF physics."""
    import math
    from sqe_studio.interop.design_targets import evaluate_design_targets
    root, manifest = fixture_rf(tmp_path)
    screen = native_rf_evidence(root, manifest)
    magnitude = math.hypot(0.5, -0.25)
    goals = [
        {'name':'rf_S21_mag_at_5GHz','unit':'1','value':0.56,'tolerance':0.01},
        {'name':'rf_S21_dB_at_5GHz','unit':'dB','value':-5.0,'tolerance':0.1},
        {'name':'rf_S11_mag_at_4GHz','unit':'dB','value':0.5,'tolerance':0.01},
        {'name':'rf_S21_mag_at_4.5GHz','unit':'1','value':0.5,'tolerance':0.01},
        {'name':'rf_S31_mag_at_5GHz','unit':'1','value':0.5,'tolerance':0.01},
        {'name':'rf_S21_mag_at_5GHz','unit':'1','value':0.5,'tolerance':0.01},
    ]
    project = {'revision':REV,'revision_digest':DIGEST,
               'model':{'intent':{'targets':goals}}}
    out = evaluate_design_targets(project=project,manifest=manifest,rf_evidence=screen)
    rows = out['rows']
    assert rows[0]['numeric_status']=='AMBIGUOUS_TARGET_NAME'
    assert rows[1]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
    assert rows[1]['observed']==pytest.approx(20*math.log10(magnitude))
    assert rows[2]['numeric_status']=='UNIT_MISMATCH'
    assert rows[3]['numeric_status']=='NO_EXACT_NATIVE_FREQUENCY_POINT'
    assert rows[4]['numeric_status']=='NO_NATIVE_PORT_FOR_TARGET'
    assert rows[5]['numeric_status']=='AMBIGUOUS_TARGET_NAME'
    assert all(r['physical_status']=='NOT_QUALIFIED' for r in rows)
    assert out['automatic_optimization']=='BLOCKED' and out['fabrication']=='HOLD'


def test_rf_feedback_never_interpolates_or_certifies_pumped_gain(tmp_path):
    from sqe_studio.interop.design_targets import evaluate_design_targets
    root, manifest = fixture_rf(tmp_path,pumped=True)
    screen = native_rf_evidence(root,manifest)
    targets = [{'name':'rf_S21_mag_at_5GHz','unit':'1','value':0.55,'tolerance':0.02}]
    project = {'revision':REV,'revision_digest':DIGEST,
               'model':{'intent':{'targets':targets}}}
    a = evaluate_design_targets(project=project,manifest=manifest,rf_evidence=screen)
    assert a['rows'][0]['numeric_status']=='WITHIN_NUMERIC_TOLERANCE'
    assert a['rows'][0]['scientific_note']=='NATIVE_SIGNAL_S_AMPLITUDE_ONLY_NO_EM_OR_GAIN_VALIDATION'
    assert a['cross_engine_parameter_transfer'].startswith('BLOCKED')
    # Samples cannot substitute for a verified RF screen or another engine's run.
    invalid = {**screen,'physical_validation':'APPROVED'}
    assert evaluate_design_targets(project=project,manifest=manifest,
                rf_evidence=invalid)['rows'][0]['numeric_status']=='NO_VERIFIED_RF_EVIDENCE'
    assert evaluate_design_targets(project=project,manifest={**manifest,'engine':'scqubits'},
                rf_evidence=screen)['rows'][0]['numeric_status']=='NO_NATIVE_OBSERVATION_FOR_THIS_RUN'
    # A zero-amplitude exact native sample has no finite dB value.
    screen_zero=copy.deepcopy(screen)
    screen_zero['samples'][7]['magnitude']=0.
    project['model']['intent']['targets']=[{'name':'rf_S22_dB_at_5GHz','unit':'dB','value':-20}]
    assert evaluate_design_targets(project=project,manifest=manifest,
                rf_evidence=screen_zero)['rows'][0]['numeric_status']=='UNDEFINED_LOG_MAGNITUDE'
