"""Real Palace Results -> B02 reporting is numerical-only and provenance bound."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest
from sqe_studio.cycle_qualification import _case_from_em


def _evidence():
    outputs={
        'eig.csv':b'm,Re{f} (GHz),Q\n1,5.904977748367,359871.24\n',
        'port-Q.csv':'m,Q_ext[1],κ_ext[1] (GHz)\n1,34921608.3,-1.6909237e-7\n'.encode(),
        'domain-E.csv':b'm,E_elec (J),E_mag (J)\n1,0.99999999,1\n',
    }
    base='em/native/native_palace_solve-'
    screen={
        'schema':'sqe.em-native-results-screen.v1',
        'source':'revision_and_sha256_verified_native_run',
        'mode_identity':'UNRESOLVED',
        'mesh_convergence':'NOT_ESTABLISHED',
        'field_acquisition':{
            'artifact_count':17,'common_coordinate_domain_verified':False,
            'complex_vector_normalization_verified':False,
        },
        'modes':[{'native_mode_index':1,'frequency_GHz':5.904977748367,
            'q_total':359871.24,'electric_to_magnetic_energy_ratio':0.99999999,
            'ports':[{'port_index':1,'q_ext':34921608.3,
                      'native_kappa_ext_GHz':-1.6909237e-7}]}],
    }
    manifest={
        'artifact_type':'palace.eigenmodes','model_digest':'a'*64,
        'native_solver_version':'SQDMetal/Gmsh/Palace native',
        'artifacts':[{'name':'sqe_em/outputFiles/'+k,
                      'sha256':hashlib.sha256(v).hexdigest()} for k,v in outputs.items()],
    }
    gates={'stages':[
        {'id':'native_palace_solve','status':'PASS'},
        {'id':'results_screen_native_palace_solve','status':'PASS'},
        {'id':'mesh_convergence','status':'BLOCKED'}]}
    result={base+k:v for k,v in outputs.items()}
    result[base+'results-screen.json']=json.dumps(screen).encode()
    result[base+'manifest.json']=json.dumps(manifest).encode()
    result['em/QUALIFICATION.json']=json.dumps(gates).encode()
    return result


def test_current_native_results_appear_in_b02_without_physical_approval():
    b02=_case_from_em(_evidence(),'B02')
    assert b02['stage_status']=='BLOCKED'
    assert b02['failure_reason']=='BLOCKED_EXPANDED_PHYSICS_CHECKS'
    assert b02['execution_kind']=='NATIVE'
    assert b02['provenance'].endswith('SCALAR_CSV_SHA256_VERIFIED')
    m=b02['measurements']
    assert m['native_mode_observations'][0]['frequency_GHz']==5.904977748367
    assert m['native_mode_observations'][0]['ports'][0]['native_kappa_ext_GHz']<0
    assert m['complex_field_artifact_count']==17
    assert m['complex_field_export_lineage_status']=='NOT_REPORTED'
    assert m['complex_field_common_domain_verified'] is False
    assert m['mode_identity']=='UNRESOLVED'
    assert m['mesh_convergence']=='NOT_ESTABLISHED'
    assert b02['units']['frequency']=='GHz'


@pytest.mark.parametrize('mutation',[
    'missing_table','tampered_table','nonfinite','duplicate_mode','unverified_identity',
    'missing_source','negative_q','duplicate_port','mismatched_screen_frequency',
    'fabricated_field_readiness'])
def test_forged_or_incomplete_native_scalar_screen_fails_closed(mutation):
    data=_evidence()
    base='em/native/native_palace_solve-'
    if mutation=='missing_table':
        del data[base+'port-Q.csv']
    elif mutation=='tampered_table':
        data[base+'eig.csv']=b'replaced'
    else:
        screen=json.loads(data[base+'results-screen.json'])
        mode=screen['modes'][0]
        if mutation=='nonfinite': mode['frequency_GHz']=float('nan')
        if mutation=='duplicate_mode': screen['modes'].append(dict(mode))
        if mutation=='unverified_identity': screen['mode_identity']='VERIFIED'
        if mutation=='missing_source': screen['source']='fixture'
        if mutation=='negative_q': mode['q_total']=-1
        if mutation=='duplicate_port': mode['ports'].append(dict(mode['ports'][0]))
        if mutation=='mismatched_screen_frequency': mode['frequency_GHz']=6.01
        if mutation=='fabricated_field_readiness': screen['field_lineage']={'schema':'sqe.palace-verified-field-lineage.m11.v1','status':'VERIFIED_FORMAT_LINEAGE_ONLY','physical_mode_identity':'UNRESOLVED','mesh_convergence':'NOT_ESTABLISHED','fabrication':'HOLD','field_sample_count':1,'saved_mode_ordinals_unverified':[1], 'mesh_sha256':'0'*64, 'deck_sha256':'0'*64, 'native_eig_sha256':'0'*64}
        data[base+'results-screen.json']=json.dumps(screen).encode()
    result=_case_from_em(data,'B02')
    assert result['stage_status']=='FAIL'
    assert result['failure_reason']=='INVALID_NATIVE_SCALAR_EVIDENCE'
    assert 'native_mode_observations' not in (result.get('measurements') or {})


def test_native_qualification_without_results_screen_is_not_promoted():
    data=_evidence()
    data.pop('em/native/native_palace_solve-results-screen.json')
    q=json.loads(data['em/QUALIFICATION.json'])
    q['stages'][1]['status']='BLOCKED'
    data['em/QUALIFICATION.json']=json.dumps(q).encode()
    result=_case_from_em(data,'B02')
    assert result['stage_status']=='BLOCKED'
    assert 'native_mode_observations' not in (result.get('measurements') or {})


def test_m13_native_field_format_blocker_propagates_without_physics_approval():
    data=_evidence()
    base='em/native/native_palace_solve-'
    screen=json.loads(data[base+'results-screen.json'])
    screen['field_lineage']={
        'schema':'sqe.palace-verified-field-lineage.m11.v1',
        'status':'BLOCKED_INVALID_NATIVE_FIELD_LINEAGE',
        'diagnostic_code':'VTU_COMPLEX_E_MISSING',
        'diagnostic_phase':'piece',
        'physical_mode_identity':'UNRESOLVED',
        'mesh_convergence':'NOT_ESTABLISHED',
        'fabrication':'HOLD'}
    data[base+'results-screen.json']=json.dumps(screen).encode()
    row=_case_from_em(data,'B02')
    assert row['stage_status']=='BLOCKED'
    assert row['measurements']['complex_field_export_lineage_status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert row['measurements']['complex_field_export_diagnostic_code']=='VTU_COMPLEX_E_MISSING'
    assert row['measurements']['complex_field_export_diagnostic_phase']=='piece'
    assert row['measurements']['mode_identity']=='UNRESOLVED'
    assert row['measurements']['mesh_convergence']=='NOT_ESTABLISHED'
    assert row['scientific_limitations']


def test_m15_categorical_vtu_header_evidence_is_preserved_in_b02_without_approval():
    data=_evidence()
    base='em/native/native_palace_solve-'
    screen=json.loads(data[base+'results-screen.json'])
    declared={name:'ABSENT' for name in ('E_real','E_imag','E')}
    signature={'schema':'sqe.vtu-e-field-declaration.m15.v1',
               'point':declared,'cell':dict(declared),
               'parallel_point':dict(declared),
               'field_values_exported':False,
               'physical_mode_identity':'UNRESOLVED'}
    screen['field_lineage']={
        'schema':'sqe.palace-verified-field-lineage.m11.v1',
        'status':'BLOCKED_INVALID_NATIVE_FIELD_LINEAGE',
        'diagnostic_code':'VTU_COMPLEX_E_MISSING',
        'diagnostic_phase':'piece',
        'field_declaration_diagnostic':signature,
        'physical_mode_identity':'UNRESOLVED',
        'mesh_convergence':'NOT_ESTABLISHED',
        'fabrication':'HOLD'}
    data[base+'results-screen.json']=json.dumps(screen).encode()
    b02=_case_from_em(data,'B02')
    assert b02['stage_status']=='BLOCKED'
    assert b02['measurements']['complex_field_declaration_diagnostic']==signature
    assert b02['measurements']['mode_identity']=='UNRESOLVED'
    assert b02['measurements']['mesh_convergence']=='NOT_ESTABLISHED'
    assert b02['fabrication_status']=='HOLD' if 'fabrication_status' in b02 else b02['scientific_limitations']

    # Forged raw/private VTK identifiers are rejected from portable evidence.
    for mutation in ('extra', 'mode', 'status'):
        tampered=json.loads(data[base+'results-screen.json'])
        sig=tampered['field_lineage']['field_declaration_diagnostic']
        if mutation=='extra': sig['point']['secret_user_array']='FLOAT_VECTOR_3'
        if mutation=='mode': sig['physical_mode_identity']='VERIFIED'
        if mutation=='status': sig['point']['E_real']='SUPPLIED_BY_USER'
        bad=dict(data)
        bad[base+'results-screen.json']=json.dumps(tampered).encode()
        result=_case_from_em(bad,'B02')
        assert result['stage_status']=='FAIL'
        assert result['failure_reason']=='INVALID_NATIVE_SCALAR_EVIDENCE'
