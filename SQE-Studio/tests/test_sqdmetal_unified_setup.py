"""Regression of the single scientific-environment setup path (no network/solver calls)."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workstation_setup', ROOT/'workstation_setup.py')
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


def upstream(tmp_path):
    p = tmp_path/'reviewed-upstream'
    (p/'SQDMetal'/'PALACE').mkdir(parents=True)
    (p/'SQDMetal'/'PALACE'/'Eigenmode_Simulation.py').write_text('fixture',encoding='utf-8')
    (p/'pyproject.toml').write_text('[project]\nname="SQDMetal"\n',encoding='utf-8')
    return p


def fake_venv(tmp_path, monkeypatch):
    project = tmp_path/'sqe-project'
    base = tmp_path/'local'
    loc = ws.managed_root(project,base=base)
    py = loc/'venv'/'Scripts'/'python.exe'
    py.parent.mkdir(parents=True)
    py.write_bytes(b'fake interpreter')
    (loc/'ready.json').write_text(__import__('json').dumps({
        'schema':'sqe.local-python-runtime.v1', 'python_version':'3.11',
        'source_path_sha256':ws._project_digest(project)}),encoding='utf-8')
    return project, base, py


def test_single_panel_exposes_sqdmetal_alongside_other_engines():
    keys = [key for key,_ in ws.SETUP_OPTIONS]
    assert keys == ['test_tools','scqubits','gmsh','quantum_metal','sqdmetal','browser']
    assert 'sqdmetal' in ws.INSTALL_GROUPS
    assert 'sqdmetal' not in ws.PACKAGES  # no PyPI fallback
    launcher = (ROOT/'Launch SQE Studio.pyw').read_text(encoding='utf-8')
    assert "text='Prepare scientific environment'" in launcher
    assert "text='Connect SQDMetal source (native EM bridge)'" not in launcher


def test_invalid_local_source_preflight_prevents_any_package_install(tmp_path):
    project, base, py = fake_venv(tmp_path, None)
    calls=[]
    def run(*args, **kwargs):
        calls.append(args)
        raise AssertionError('No installation permitted before source validation')
    with pytest.raises(ValueError,match='upstream source'):
        ws.install_selected(project,['gmsh','sqdmetal'],lambda *_:None,base=base,run=run,sqdmetal_source=tmp_path)
    assert calls == []


def test_sqdmetal_and_gmsh_use_same_prepared_interpreter_without_shell(tmp_path):
    project,base,py = fake_venv(tmp_path,None)
    source=upstream(tmp_path)
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='installed',stderr='')
    out = ws.install_selected(project,['gmsh','sqdmetal'],lambda *_:None,
                              base=base,run=run,sqdmetal_source=source)
    assert list(out['groups'])==['gmsh','sqdmetal']
    assert out['groups']['gmsh']['status']=='INSTALLED_UNVERIFIED'
    assert out['groups']['sqdmetal']['status']=='INSTALLED_UNQUALIFIED'
    assert out['activated']
    assert len(calls)==2
    assert all(cmd[0]==str(py) and kwargs['shell'] is False for cmd,kwargs in calls)
    assert 'gmsh==4.15.2' in calls[0][0]
    assert calls[1][0][-1]==str(source)
    assert all('https://github.com' not in ' '.join(cmd) for cmd,_ in calls)


def test_failure_retained_as_failed_group_without_false_success(tmp_path):
    project,base,_ = fake_venv(tmp_path,None)
    source=upstream(tmp_path)
    def failure(args,**kwargs):
        return SimpleNamespace(returncode=1,stdout='',stderr='incompatible dependency')
    seen=[]
    out=ws.install_selected(project,['sqdmetal'],seen.append,base=base,run=failure,sqdmetal_source=source)
    assert out['groups']['sqdmetal']['status']=='FAILED'
    assert 'incompatible dependency' in '\n'.join(seen)
    assert out['activated']  # older environment still valid; solver not qualified


def test_new_environment_can_bootstrap_then_install_source(tmp_path):
    project=tmp_path/'project';base=tmp_path/'local';source=upstream(tmp_path)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if 'venv' in args:
            py = Path(args[-1])/'Scripts'/'python.exe'
            py.parent.mkdir(parents=True,exist_ok=True)
            py.write_bytes(b'fixture')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    out=ws.install_selected(project,['test_tools','sqdmetal'],lambda _:None,
                            base=base,run=run,python_311=['py','-3.11'],sqdmetal_source=source)
    assert out['groups']['sqdmetal']['status']=='INSTALLED_UNQUALIFIED'
    assert out['activated']
    assert len(calls)==3
