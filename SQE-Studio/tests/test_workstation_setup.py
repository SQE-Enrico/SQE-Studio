"""Offline tests: no package downloads or Python installs are executed."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('workstation_setup', ROOT/'workstation_setup.py')
ws = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ws)


def test_environment_identity_is_path_bound(tmp_path):
    base=tmp_path/'local'
    a=tmp_path/'one'
    b=tmp_path/'two'
    assert ws.managed_root(a,base=base)!=ws.managed_root(b,base=base)
    assert ws.managed_python(a,base=base) is None


def test_refuses_arbitrary_package_input(tmp_path):
    with pytest.raises(ValueError):
        ws.install_selected(tmp_path,['shell_command'],lambda _:None,base=tmp_path/'local',python_311=['python'])
    with pytest.raises(ValueError):
        ws.install_selected(tmp_path,[],lambda _:None,base=tmp_path/'local',python_311=['python'])


def test_mocked_setup_only_explicit_packages(tmp_path):
    project=tmp_path/'source'
    base=tmp_path/'local'
    calls=[]
    def fake_run(args,**kwargs):
        calls.append(args)
        if args[-2:] == ['-m','venv']:
            raise AssertionError('unexpected')
        if '-m' in args and 'venv' in args:
            location=Path(args[-1])/'Scripts'
            location.mkdir(parents=True)
            (location/'python.exe').write_text('mock',encoding='ascii')
        return SimpleNamespace(returncode=0,stdout='okay',stderr='')
    messages=[]
    result=ws.install_selected(project,['test_tools','scqubits'],messages.append,
               run=fake_run,python_311=['py','-3.11'],base=base)
    assert result['activated']
    assert len(calls)==3
    assert calls[0][:2]==['py','-3.11']
    assert 'scqubits==4.3.1' in calls[-1]
    assert not any('quantum-metal' in str(c) or 'playwright' in str(c) for c in calls)
    assert ws.managed_python(tmp_path/'elsewhere',base=base) is None
    marker=ws.managed_root(project,base=base)/'ready.json'
    assert json.loads(marker.read_text())['python_version']=='3.11'


def test_failed_bootstrap_never_activates_environment(tmp_path):
    def fake_run(args,**kwargs):
        if 'venv' in args:
            p=Path(args[-1])/'Scripts';p.mkdir(parents=True)
            (p/'python.exe').write_text('mock')
        if 'venv' in args:
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        return SimpleNamespace(returncode=1,stdout='',stderr='network unavailable')
    result=ws.install_selected(tmp_path/'project',['test_tools'],lambda _:None,
                    run=fake_run,python_311=['py','-3.11'],base=tmp_path/'local')
    assert not result['activated']
    assert result['groups']['test_tools']['status']=='FAILED'
