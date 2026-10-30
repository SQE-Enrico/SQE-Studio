"""Local environment reconnection: no real interpreter is launched or installed."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('workstation_setup_reconnect', ROOT/'workstation_setup.py')
ws = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ws)


def _existing(tmp_path):
    old = tmp_path/'SQE-old'/'SQE-Studio'
    new = tmp_path/'SQE-new'/'SQE-Studio'
    base = tmp_path/'local'
    loc = ws.managed_root(old, base=base)
    (loc/'venv'/'Scripts').mkdir(parents=True)
    (loc/'venv'/'Scripts'/'python.exe').write_text('fixture - not executable')
    marker = {'schema':'sqe.local-python-runtime.v1','python_version':'3.11',
              'source_path_sha256':hashlib.sha256(str(old.resolve()).casefold().encode()).hexdigest()}
    (loc/'ready.json').write_text(json.dumps(marker))
    return old,new,base,loc


def test_reconnection_preserves_venv_and_old_binding(tmp_path):
    old,new,base,loc = _existing(tmp_path)
    assert ws.managed_python(old,base=base) == loc/'venv'/'Scripts'/'python.exe'
    assert ws.managed_python(new,base=base) is None
    d = ws.environment_inventory(new,base=base)
    assert len(d['candidates']) == 1 and d['candidates'][0]['ready']
    calls = []
    def probe(args,**kw):
        calls.append((args,kw))
        return SimpleNamespace(returncode=0,stdout='{"version":[3,11],"bits":64}',stderr='')
    path = ws.bind_existing_environment(new,loc.name,base=base,probe=probe)
    assert path == ws.managed_python(new,base=base)
    assert ws.managed_python(old,base=base) == path
    assert len(calls) == 1 and calls[0][0][1:3] == ['-I','-c']
    assert calls[0][1]['timeout'] <= 20 and calls[0][1]['check'] is False
    assert json.loads((loc/'ready.json').read_text())['source_path_sha256'] == ws._project_digest(old)
    assert d['candidates'][0]['id'] == loc.name


def test_reconnection_rejects_incomplete_and_wrong_python(tmp_path):
    old,new,base,loc = _existing(tmp_path)
    with pytest.raises(ValueError):
        ws.bind_existing_environment(new, '../escape', base=base)
    probe = lambda *args, **kw: SimpleNamespace(returncode=0,stdout='{"version":[3,15],"bits":64}',stderr='')
    with pytest.raises(ValueError,match='Cannot validate'):
        ws.bind_existing_environment(new,loc.name,base=base,probe=probe)
    assert ws.managed_python(new,base=base) is None
    (loc/'ready.json').unlink()
    state = ws.environment_inventory(new,base=base)
    assert not state['candidates'][0]['ready'] and state['candidates'][0]['python_exists']
    with pytest.raises(ValueError,match='ready marker'):
        ws.bind_existing_environment(new,loc.name,base=base,probe=probe)


def test_corrupt_binding_never_runs_unknown_runtime(tmp_path):
    old,new,base,loc = _existing(tmp_path)
    bind = ws._bind_file(new,base)
    bind.parent.mkdir(parents=True)
    bind.write_text('{"schema":"sqe.local-runtime-binding.v1","environment_id":"../../bad"}')
    assert ws.managed_python(new,base=base) is None
    assert ws.managed_root(new,base=base) != loc


def test_install_with_explicit_binding_does_not_destroy_old_ready_marker(tmp_path):
    old,new,base,loc = _existing(tmp_path)
    probe = lambda *args, **kw: SimpleNamespace(returncode=0,stdout='{"version":[3,11],"bits":64}',stderr='')
    ws.bind_existing_environment(new,loc.name,base=base,probe=probe)
    def mock_run(*args,**kw):
        return SimpleNamespace(returncode=0,stdout='installed',stderr='')
    result = ws.install_selected(new,['test_tools'],lambda _:None,
                 base=base, python_311=['py','-3.11'],run=mock_run)
    assert result['activated']
    assert json.loads((loc/'ready.json').read_text())['source_path_sha256'] == ws._project_digest(old)



def test_integrity_checker_provides_relative_differences(tmp_path, monkeypatch):
    source = ROOT/'tools'/'verify_release_source.py'
    spec = importlib.util.spec_from_file_location('verify_source_diagnostic', source)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    lock={'tree_digest':'a'*64,'contract_digest':'f'*64}
    (tmp_path/'FOUNDATION_LOCK.json').write_text(json.dumps(lock))
    (tmp_path/'file-a.txt').write_text('original')
    monkeypatch.setattr(verifier,'frozen_contract_digest',lambda _:lock['contract_digest'])
    files = verifier.inventory(tmp_path)
    manifest={'schema':'sqe.eda-source-inventory.v1',
              'historical_foundation_tree_digest':lock['tree_digest'],
              'frozen_contract_digest':lock['contract_digest'],
              'files':files,
              'current_source_inventory_sha256':verifier.hash_bytes(verifier.canonical(files))}
    (tmp_path/'EDA_SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    assert verifier.verify(tmp_path)['files'] == files
    (tmp_path/'file-a.txt').write_text('tampered')
    (tmp_path/'extra.txt').write_text('untracked')
    with pytest.raises(ValueError,match='Source inventory mismatch') as exc:
        verifier.verify(tmp_path)
    diagnostic = json.loads(str(exc.value).split('Source inventory mismatch: ',1)[1])
    assert diagnostic['added'] == ['extra.txt']
    assert diagnostic['changed'] == ['file-a.txt']
    assert diagnostic['counts']['missing'] == 0
    assert str(tmp_path) not in str(exc.value)
