"""Desktop settings, not engine fixtures or scientific output."""
from pathlib import Path
import json
import pytest
import solver_setup as setup


def test_defaults_are_inert(tmp_path, monkeypatch):
    monkeypatch.delenv('JULIA_PROJECT',raising=False)
    current = setup.load_settings(base=tmp_path)
    assert current['backend']=='none'
    setup.apply_settings(current)
    assert 'SQE_PALACE_BACKEND' not in __import__('os').environ


def test_save_explicit_wsl_and_julia_project(tmp_path,monkeypatch):
    project=tmp_path/'julia-project'; project.mkdir()
    (project/'Project.toml').write_text('name = "test-only"\n', encoding='utf8')
    doc=dict(schema=setup.SCHEMA,backend='wsl',palace_binary='/opt/palace/bin/palace',
             wsl_distro='Ubuntu-24.04',julia_project=str(project))
    setup.save_settings(doc,base=tmp_path)
    assert setup.load_settings(base=tmp_path)==doc
    setup.apply_settings(doc)
    import os
    assert os.environ['SQE_PALACE_WSL_BINARY']=='/opt/palace/bin/palace'
    assert os.environ['SQE_PALACE_WSL_DISTRO']=='Ubuntu-24.04'
    assert os.environ['JULIA_PROJECT']==str(project)
    assert os.environ['SQE_PALACE_BACKEND']=='wsl'


@pytest.mark.parametrize('path', ['/opt/../palace','relative/palace','/a\\b','/bad\npath'])
def test_rejects_unsafe_wsl_binary(path):
    with pytest.raises(ValueError):
        setup.validate(dict(schema=setup.SCHEMA,backend='wsl',palace_binary=path,
                            wsl_distro='',julia_project=''))


def test_rejects_unreviewed_environment_keys():
    with pytest.raises(ValueError):
        setup.validate(dict(**setup.defaults(),shell='powershell'))


def test_wsl_path_is_not_a_shell(monkeypatch):
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    from types import SimpleNamespace
    import subprocess
    monkeypatch.setattr(em.platform,'system',lambda:'Windows')
    monkeypatch.setenv('SQE_PALACE_BACKEND','wsl')
    monkeypatch.setenv('SQE_PALACE_WSL_BINARY','/usr/local/bin/palace')
    monkeypatch.setenv('SQE_PALACE_WSL_DISTRO','Ubuntu-24.04')
    monkeypatch.setattr(em.shutil,'which',lambda _: 'wsl.exe')
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0,stdout='Palace version 1.0',stderr='')
    monkeypatch.setattr(em.subprocess,'run',run)
    state=em._palace_readiness()
    assert state['backend']=='wsl' and state['binary_sha256'] is None
    assert state['identity_probe']=='--version' and state['version_verified']
    assert calls[0]==['wsl.exe','-d','Ubuntu-24.04','--exec','/usr/bin/test','-x','/usr/local/bin/palace']
    assert calls[1]==['wsl.exe','-d','Ubuntu-24.04','--exec','/usr/local/bin/palace','--version']


def test_qualification_preserves_original_julia_depot(tmp_path,monkeypatch):
    from sqe_studio.qualification import qualify
    from sqe_studio import qualification as q
    # This is a test-only fixture verifying child environment, not an engine.
    root=tmp_path/'source'; (root/'src/sqe_studio').mkdir(parents=True)
    (root/'pyproject.toml').write_text('test')
    (root/'src/sqe_studio/server.py').write_text('test')
    (root/'EDA_SOURCE_MANIFEST.json').write_text(json.dumps({'current_source_inventory_sha256':'a'*64}))
    monkeypatch.setattr(q.shutil,'which',lambda name: 'julia' if name=='julia' else None)
    monkeypatch.setattr(q,'available',lambda _:False)
    monkeypatch.setenv('JULIA_DEPOT_PATH',str(tmp_path/'installed-julia-depot'))
    seen=[]
    def fake_run(argv,cwd,env,timeout):
        seen.append(dict(env))
        return 0,'test-only success',0.01
    monkeypatch.setattr(q,'_run',fake_run)
    qualify(root,tmp_path/'report.zip',profile='quick')
    assert all(e['JULIA_DEPOT_PATH']==str(tmp_path/'installed-julia-depot') for e in seen)
    assert all(e['HOME']!=__import__('os').environ.get('HOME') for e in seen)


def test_wsl_distro_used_for_mesh_path_and_solver(monkeypatch,tmp_path):
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    from types import SimpleNamespace
    folder=tmp_path/'mesh';folder.mkdir()
    (folder/'sqe_em.json').write_text('{}')
    commands=[]
    def fake_run(argv,**kwargs):
        commands.append(argv)
        if 'wslpath' in argv:
            return SimpleNamespace(returncode=0,stdout='/mnt/c/mesh\n',stderr='')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(em.subprocess,'run',fake_run)
    ready={'backend':'wsl','command':['wsl.exe','-d','Ubuntu-24.04','--exec','/usr/local/bin/palace']}
    info=em._run_palace(ready,folder,'sqe_em.json',2)
    assert info['exit_code']==0
    assert commands[0][:4]==['wsl.exe','-d','Ubuntu-24.04','--exec']
    assert commands[1]==['wsl.exe','-d','Ubuntu-24.04','--cd','/mnt/c/mesh','--exec','/usr/local/bin/palace','-np','2','-nt','1','sqe_em.json']


def test_julia_install_is_opt_in_and_isolated(tmp_path):
    from types import SimpleNamespace
    calls=[]
    def fake_run(args,**kwargs):
        calls.append((args,kwargs))
        assert kwargs['shell'] is False
        assert 'Pkg.add("JosephsonCircuits")' in args[-1]
        folder=tmp_path/'SQE-Studio'/'julia-project'
        (folder/'Project.toml').write_text('name = "SQEJulia"\n', encoding='utf8')
        return SimpleNamespace(returncode=0, stdout='fixture only',stderr='')
    project=setup.install_isolated_julia_package(base=tmp_path,runner=fake_run,julia='julia.exe')
    assert project==tmp_path/'SQE-Studio'/'julia-project'
    assert setup.load_settings(base=tmp_path)['julia_project']==str(project)
    assert calls[0][0][0]=='julia.exe' and '--project='+str(project) in calls[0][0]


def test_palace_016_spack_wrapper_help_fallback(monkeypatch):
    """Palace 0.16 wrapper has --help but not --version; no EM solve is implied."""
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    from types import SimpleNamespace
    monkeypatch.setattr(em.platform,'system',lambda:'Windows')
    monkeypatch.setenv('SQE_PALACE_BACKEND','wsl')
    monkeypatch.setenv('SQE_PALACE_WSL_BINARY','/home/test/.sqe/spack/opt/spack/palace/bin/palace')
    monkeypatch.delenv('SQE_PALACE_WSL_DISTRO',raising=False)
    monkeypatch.setattr(em.shutil,'which',lambda _: 'wsl.exe')
    calls=[]
    def run(argv,**kw):
        calls.append(argv)
        if argv[-1]=='--version':
            return SimpleNamespace(returncode=1,stdout='',stderr='unknown option --version')
        if argv[-1]=='--help':
            return SimpleNamespace(returncode=0,stdout=(
                'Usage: palace [OPTIONS] CONFIG_FILE\n'
                'Wrapper for launching Palace using MPI\nOptions:\n'),stderr='')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(em.subprocess,'run',run)
    ready=em._palace_readiness()
    assert ready['identity_probe']=='--help' and ready['version_verified'] is False
    assert ready['version']=='unreported by CLI'
    assert calls[-2][-1]=='--version' and calls[-1][-1]=='--help'


def test_palace_help_not_accepted_as_version_or_simulation(monkeypatch):
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    from types import SimpleNamespace
    monkeypatch.setattr(em.platform,'system',lambda:'Windows')
    monkeypatch.setenv('SQE_PALACE_BACKEND','wsl')
    monkeypatch.setenv('SQE_PALACE_WSL_BINARY','/tmp/palace')
    monkeypatch.setattr(em.shutil,'which',lambda _: 'wsl.exe')
    def run(argv,**kw):
        if argv[-1]=='--version':return SimpleNamespace(returncode=1,stdout='Palace version error',stderr='')
        if argv[-1]=='--help':return SimpleNamespace(returncode=0,stdout='not the palace CLI',stderr='')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(em.subprocess,'run',run)
    with pytest.raises(em.EngineBlocked):
        em._palace_readiness()
