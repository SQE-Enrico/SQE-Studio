from pathlib import Path
import pytest
from importlib.machinery import SourceFileLoader

def _delta():
    return SourceFileLoader('delta',str(Path(__file__).resolve().parents[1]/'tools/delta.py')).load_module()

def test_agent_delta_roundtrip_and_owned_paths(tmp_path):
    import shutil
    d=_delta();src=tmp_path/'base';src.mkdir();(src/'contracts').mkdir();(src/'src').mkdir();(src/'src'/'sqe_studio').mkdir(parents=True)
    (src/'src'/'sqe_studio'/'interop').mkdir()
    (src/'contracts'/'ownership.json').write_text('{"agents":{"A01":{"paths":["src/sqe_studio/interop/"]}},"frozen_paths":["contracts/"]}')
    d.lock(src);assert d.baseline(src)
    modified=tmp_path/'modified';shutil.copytree(src,modified)
    (modified/'src'/'sqe_studio'/'interop'/'model.py').write_text('x = 1\n')
    log=tmp_path/'test.log';log.write_text('1 passed\n');archive=tmp_path/'A01-delta.zip'
    assert d.add_delta(src,modified,'A01',archive,[str(log)],0)['changes'][0]['op']=='put'
    assert d.read_delta(src,archive)['agent_id']=='A01'
    (modified/'contracts'/'ownership.json').write_text('malicious')
    with pytest.raises(ValueError,match='outside'):d.add_delta(src,modified,'A01',tmp_path/'bad.zip',[str(log)],0)

def test_unknown_agents_rejected(tmp_path):
    d=_delta()
    with pytest.raises(ValueError):d.valid_path('../unsafe.txt')
    with pytest.raises(ValueError):d.valid_path('C:\\Windows\\unsafe')
