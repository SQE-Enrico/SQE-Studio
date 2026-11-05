"""RC14 scientific triage (fixtures only; NOT a native Palace qualification)."""
import hashlib
import json
import zipfile
from pathlib import Path
import pytest
from sqe_studio.interop.em_convergence import (
    ConvergenceEvidenceError, analyze_report_zip, convergence_series,
    palace_log_metrics, third_mesh_preflight)
from sqe_studio.native_em_qualification import _option_check
from sqe_studio.interop.native_views import palace_eigenmodes


def _native_observation(mode, index):
    return {'geometry_and_stack_sha256':'a'*64, 'manifest_sha256':str(index)*64,
            'modes':[{'mode_index':1,'frequency_GHz':mode}]}


def test_solver_log_metrics_are_native_diagnostics_not_qualification():
    text='''Parallel Mesh Stats:
 elements  78926 78945 78964 157890
 Estimated peak per-node memory usage is: Min. 2.8G, Max. 2.8G, Avg. 2.8G, Total 2.8G
  Total 141.622 141.622 141.622
 Linear eigensolve converged (1 eigenpair) due to CONVERGED_TOL; iterations 1'''
    stats=palace_log_metrics(text)
    assert stats=={'mesh_elements_3d':157890,'peak_memory_GB':2.8,
                   'solver_elapsed_seconds':141.622,'solver_converged_tol_in_log':True}


def test_numeric_two_mesh_drift_stays_scientifically_blocked():
    obs=[_native_observation(5.904978100716,1),_native_observation(6.031211562548,2)]
    stats=[{'mesh_elements_3d':157890,'peak_memory_GB':2.8,'solver_elapsed_seconds':141.622},
           {'mesh_elements_3d':370113,'peak_memory_GB':6.8,'solver_elapsed_seconds':322.614}]
    result=convergence_series(obs,stats)
    assert result['mode_identity'].startswith('UNRESOLVED')
    assert result['mesh_convergence']=='NOT_ESTABLISHED'
    assert result['last_step_numeric_threshold_met'] is False
    assert result['adjacent_differences'][0]['relative_difference']==pytest.approx(0.0209300338)
    assert not third_mesh_preflight(*stats,memory_limit_gb=8,time_limit_seconds=840)['allow']
    assert third_mesh_preflight(*stats,memory_limit_gb=16,time_limit_seconds=840)['allow']
    with pytest.raises(ConvergenceEvidenceError,match='Geometry or material'):
        convergence_series([obs[0],{**obs[1],'geometry_and_stack_sha256':'b'*64}],stats)


def test_third_mesh_opt_in_requires_prior_two_solves():
    with pytest.raises(ValueError,match='Third mesh'):
        _option_check('Expert',True,True,False,third_mesh=True)
    with pytest.raises(ValueError,match='budget'):
        _option_check('Expert',True,True,True,third_mesh=True,memory_budget_gb=2)


def _example_zip(path: Path):
    reports={'schema':'sqe.native-em-qualification.v1',
             'stages':[{'id':x,'status':'PASS'} for x in ('native_palace_solve','native_palace_refinement')]}
    data={'QUALIFICATION.json':json.dumps(reports).encode()}
    for i,name in enumerate(('native_palace_solve','native_palace_refinement'),1):
        observation=_native_observation(5.9+0.1*i,i)
        data[f'native/{name}-manifest.json']=json.dumps({'artifact_type':'palace.eigenmodes','observation':observation,'artifacts':[{'name':'sqe_em/sqe_em.json','sha256':'f'*64}]}).encode()
        data[f'logs/{name}.txt']=(f'elements 1 1 1 {i*10000}\nEstimated peak per-node memory usage is: Min. 1.0G, Max. 1.0G, Avg. 1.0G, Total {i}.0G\nTotal {i*100}.0 {i*100}.0 {i*100}.0\n').encode()
    integrity={'schema':'sqe.qualification-file-hashes.v1',
               'files':{n:hashlib.sha256(b).hexdigest() for n,b in data.items()}}
    data['INTEGRITY.json']=json.dumps(integrity).encode()
    with zipfile.ZipFile(path,'w') as z:
        for n,b in data.items():z.writestr(n,b)


def test_offline_review_requires_hashes_and_native_pass(tmp_path):
    path=tmp_path/'native.zip'
    _example_zip(path)
    a=analyze_report_zip(path)
    assert a['points'][0]['mesh_elements_3d']==10000
    assert a['source_report_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert a['mode_identity'].startswith('UNRESOLVED')
    with zipfile.ZipFile(path,'a') as z:
        z.writestr('EXTRA.txt','unhashed')
    with pytest.raises(ConvergenceEvidenceError,match='does not bind'):
        analyze_report_zip(path)


def test_generic_palace_result_inspection_accepts_official_scientific_mode_label(tmp_path):
    folder=tmp_path/'native';folder.mkdir()
    output=folder/'sqe_em'/'outputFiles';output.mkdir(parents=True)
    (output/'eig.csv').write_text('Mode,Frequency (GHz)\n1.00e+00,6.0312\n',encoding='utf-8')
    manifest={'engine':'sqdmetal_palace','kind':'eigenmode',
              'artifacts':[{'name':'sqe_em/outputFiles/eig.csv'}]}
    display=palace_eigenmodes(folder,manifest)
    assert display['modes']==[{'mode_index':1,'frequency_GHz':6.0312}]
    assert display['convergence']=='not_established'


def test_saved_run_palace_comparison_requires_identical_nonmesh_physical_inputs():
    from copy import deepcopy
    from sqe_studio.interop.comparison import compare_palace_modes
    from sqe_studio.interop.laptop_benchmark import resonator_project
    a=resonator_project(mesh_min_um=12,mesh_max_um=120)
    b=resonator_project(mesh_min_um=8,mesh_max_um=80)
    modes=lambda f:{'source':'palace.native_eig.csv','units':'GHz',
                     'modes':[{'mode_index':1,'frequency_GHz':f}]}
    r=compare_palace_modes(modes(5.9),modes(6.0),a,b,'ResEigen','ResEigen')
    assert r['rows'][0]['delta_GHz']==pytest.approx(0.1)
    assert r['mode_identity'].startswith('unverified')
    assert not r['convergence_verified']
    c=deepcopy(b);c['process']['stack'][0]['relative_permittivity']=12
    assert compare_palace_modes(modes(5.9),modes(6),a,c,'ResEigen','ResEigen')['status']=='not_comparable'


def test_offline_report_rejects_symlink_zip_entry(tmp_path):
    path=tmp_path/'symlink.zip';_example_zip(path)
    with zipfile.ZipFile(path,'a') as z:
        entry=zipfile.ZipInfo('native/link');entry.create_system=3
        entry.external_attr=(0o120777<<16)
        z.writestr(entry,'../../private')
    with pytest.raises(ConvergenceEvidenceError):
        analyze_report_zip(path)
