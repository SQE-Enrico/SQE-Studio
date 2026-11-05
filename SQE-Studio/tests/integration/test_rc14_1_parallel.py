"""RC14.1 resource-aware MPI and fail-closed bounded Palace evidence."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from sqe_studio.interop.palace_parallel import mpi_plan
from sqe_studio.interop.laptop_benchmark import resonator_project
from sqe_studio.native_em_qualification import _option_check
from sqe_studio.adapters import sqdmetal_palace_adapter as em


def test_auto_scales_conservatively_with_wsl_free_memory():
    def res(gb):
        return {'source':'test_WSL_probe','logical_cpus':14,'memory_available_gb':gb}
    assert [mpi_plan('auto',res(gb))['mpi_ranks'] for gb in (8,16,24,32)] == [2,4,6,8]
    assert mpi_plan('auto',res(50))['omp_threads'] == 1
    assert mpi_plan('auto',res(50))['mpi_ranks'] <= 14
    assert mpi_plan('auto',{'logical_cpus':None,'memory_available_gb':None})['mpi_ranks'] == 2


@pytest.mark.parametrize('ranks', [True, False, 0, -1, 17, 2.0, '14', None])
def test_invalid_parallel_counts_fail_closed(ranks):
    with pytest.raises(ValueError):
        mpi_plan(ranks,{'logical_cpus':14,'memory_available_gb':64})
    with pytest.raises(ValueError):
        _option_check('Expert',True,True,False, mpi_ranks=ranks)


def test_explicit_ranks_must_not_exceed_wsl_cpu_visibility():
    with pytest.raises(ValueError,match='visible'):
        mpi_plan(14,{'logical_cpus':6,'memory_available_gb':32})
    assert mpi_plan(14,{'logical_cpus':14,'memory_available_gb':32})['mpi_ranks'] == 14
    assert resonator_project(execution='solve',mpi_ranks=14)['studies'][0]['inputs']['em']['solver']['num_cpus'] == 14


def test_wsl_resource_probe_is_bounded_and_distribution_selected(monkeypatch):
    from sqe_studio.interop import palace_parallel as pp
    monkeypatch.setattr(pp.platform,'system', lambda:'Windows')
    monkeypatch.setattr(pp.shutil,'which', lambda value:'C:/Windows/System32/wsl.exe')
    monkeypatch.setenv('SQE_PALACE_BACKEND','wsl')
    monkeypatch.setenv('SQE_PALACE_WSL_DISTRO','Ubuntu')
    calls=[]
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs['timeout']==8 and kwargs['check'] is False
        return SimpleNamespace(returncode=0,stdout='14\n' if '/usr/bin/nproc' in cmd else 'MemTotal: 32768000 kB\nMemAvailable: 25165824 kB\n')
    monkeypatch.setattr(pp.subprocess,'run',fake_run)
    result=pp._resource_probe()
    assert result['logical_cpus']==14 and result['memory_available_gb']==24
    assert all(cmd[1:4]==['-d','Ubuntu','--exec'] for cmd in calls)


def test_palace_wsl_timeout_wrapper_and_phase_evidence(monkeypatch,tmp_path):
    folder=tmp_path/'job';folder.mkdir()
    commands=[]
    def fake_run(argv,**kwargs):
        commands.append(argv)
        if 'wslpath' in argv:
            return SimpleNamespace(returncode=0,stdout='/mnt/c/job\n',stderr='')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(em.subprocess,'run',fake_run)
    ready={'backend':'wsl','command':['wsl.exe','-d','Ubuntu','--exec','/opt/palace/bin/palace']}
    result=em._run_palace(ready,folder,'sqe_em.json',6)
    assert result['mpi_ranks']==6
    assert commands[-1][-7:] == ['810s','/opt/palace/bin/palace','-np','6','-nt','1','sqe_em.json']
    phases=json.loads((folder/'palace-phases.json').read_text())
    assert [x['phase'] for x in phases['events']] == ['solver_spawn_requested','solver_process_returned']
    em._phase_checkpoint(folder,'required_csv_validated')
    assert json.loads((folder/'palace-phases.json').read_text())['events'][-1]['phase']=='required_csv_validated'


def test_em_study_allows_fourteen_mpi_ranks_without_changing_physics():
    from tests.adapters.test_sqdmetal_gate import physical_case
    study, project=physical_case()
    study['inputs']['em']['solver']['num_cpus']=14
    assert em.preflight(study,project) is study['inputs']['em']
    study['inputs']['em']['solver']['num_cpus']=17
    with pytest.raises(em.EngineBlocked):
        em.preflight(study,project)


def test_solve_omits_expensive_redundant_deck_worker(tmp_path, monkeypatch):
    import sqe_studio.native_em_qualification as q
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(q.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setattr(q, 'mpi_plan', lambda requested: {'mpi_ranks':4,'omp_threads':1, 'requested':requested})
    monkeypatch.setenv('SQE_PALACE_WSL_BINARY', '/opt/palace/bin/palace')
    calls=[]
    def fake_worker(argv,*args):
        calls.append(argv)
        return 1, 'No native solver fixture; worker failure expected', 0.1
    monkeypatch.setattr(q,'_run',fake_worker)
    result=q.qualify_native_em(root,tmp_path/'native.zip',reviewer='Expert', acknowledged=True,solve=True)
    assert len(calls)==1
    assert any(x['id']=='native_palace_solve' and x['status']=='FAIL' for x in result['stages'])
    assert any(x['id']=='mesh_and_deck' and x['status']=='BLOCKED' for x in result['stages'])
    assert result['rc_status']=='BLOCKED_NOT_RELEASE_CANDIDATE'
