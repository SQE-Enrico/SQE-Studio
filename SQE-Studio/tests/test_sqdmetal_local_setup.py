"""No real third-party source installation or downloads in unit tests."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workstation_setup', ROOT/'workstation_setup.py')
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


def source(tmp_path):
    folder = tmp_path / 'downloaded-SQDMetal'
    (folder/'SQDMetal/PALACE').mkdir(parents=True, exist_ok=True)
    (folder/'SQDMetal/PALACE/Eigenmode_Simulation.py').write_text('dummy fixture')
    (folder/'pyproject.toml').write_text('[project]\nname = "SQDMetal"\n')
    return folder


def test_sqdmetal_local_source_validation_without_pip(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, 'managed_python', lambda project, base=None: None)
    with pytest.raises(ValueError, match='Connect a prepared'):
        ws.install_local_sqdmetal(tmp_path, source(tmp_path), print)
    monkeypatch.setattr(ws, 'managed_python', lambda project, base=None: tmp_path/'python.exe')
    with pytest.raises(ValueError, match='upstream source'):
        ws.install_local_sqdmetal(tmp_path, tmp_path, print)
    f=source(tmp_path)
    (f/'pyproject.toml').write_text('[project]\nname = "Unrelated"\n')
    with pytest.raises(ValueError, match='SQDMetal distribution'):
        ws.install_local_sqdmetal(tmp_path, f, print)


def test_sqdmetal_install_uses_only_selected_source_without_shell(tmp_path, monkeypatch):
    folder=source(tmp_path)
    py=tmp_path/'python.exe'
    monkeypatch.setattr(ws,'managed_python',lambda project,base=None: py)
    calls=[]
    def run(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return SimpleNamespace(returncode=0,stdout='installed',stderr='')
    result=ws.install_local_sqdmetal(tmp_path/'application',folder,lambda _:None,run=run)
    assert result['status']=='INSTALLED_UNQUALIFIED'
    assert len(calls)==1
    cmd,kw=calls[0]
    assert cmd[0]==str(py) and cmd[-1]==str(folder)
    assert cmd[1:4]==['-m','pip','install'] and kw['shell'] is False
    assert kw['timeout']==1200
    assert 'SQE_PALACE_WSL_BINARY' not in ' '.join(cmd)
    def failed(*args,**kwargs):return SimpleNamespace(returncode=1,stdout='',stderr='dependency failure')
    assert ws.install_local_sqdmetal(tmp_path/'application',folder,lambda _:None,run=failed)['status']=='FAILED'
