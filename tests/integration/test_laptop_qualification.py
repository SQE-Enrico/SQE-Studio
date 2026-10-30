"""Qualification runner is test infrastructure: mocked subprocesses are fixtures,
NOT solver results and NOT acceptable as real laptop qualification evidence.
"""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqe_studio import qualification as q


def source_stub(tmp_path):
    root=tmp_path/'source'
    (root/'src/sqe_studio').mkdir(parents=True)
    (root/'pyproject.toml').write_text('stub\n')
    (root/'src/sqe_studio/server.py').write_text('stub\n')
    (root/'EDA_SOURCE_MANIFEST.json').write_text(json.dumps({'current_source_inventory_sha256':'a'*64}))
    return root


def test_report_is_integrity_checked_sanitized_and_explicitly_blocked(tmp_path, monkeypatch):
    root=source_stub(tmp_path)
    monkeypatch.setattr(q,'available',lambda x: x=='pytest')
    monkeypatch.setattr(q.shutil,'which',lambda _:None)
    # Test-only fake subprocess statuses; never scientific engine output.
    def child(args,cwd,env,timeout):
        if 'pytest' in args:return 0, '239 passed, 13 skipped', 0.1
        if 'wheel' in args: return None, 'No module named wheel', 0.1
        return 0, 'PASS email wheel@example.invalid path '+str(Path.home()), 0.1
    monkeypatch.setattr(q,'_run',child)
    dest=tmp_path/'share.zip'
    report=q.qualify(root,dest,profile='comprehensive')
    assert report['schema']==q.SCHEMA
    assert report['rc_status']=='BLOCKED_NOT_RELEASE_CANDIDATE'
    assert report['counts']['BLOCKED']>0
    checks={g['id']:g for g in report['gates']}
    assert checks['source_integrity']['status']=='PASS'
    assert checks['integrated_regression']['counts']['skipped']==13
    assert checks['native_scqubits']['status']=='BLOCKED'
    assert checks['source_wheel_build']['status']=='BLOCKED'
    assert checks['native_em_design_loop']['status']=='BLOCKED'
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        table=json.loads(z.read('INTEGRITY.json'))['files']
        assert set(table)==set(z.namelist())-{'INTEGRITY.json'}
        for name, expected in table.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==expected
        text=z.read('logs/source_integrity.txt').decode()
        assert 'wheel@example.invalid' not in text
        assert str(Path.home()) not in text
        assert 'Release' in z.read('SUMMARY.md').decode() or 'release' in z.read('SUMMARY.md').decode()
        assert not any(x.startswith('sqe-studio-local') for x in z.namelist())


def test_failing_test_does_not_become_a_pass(tmp_path,monkeypatch):
    root=source_stub(tmp_path)
    monkeypatch.setattr(q,'available',lambda x:x=='pytest')
    monkeypatch.setattr(q.shutil,'which',lambda _:None)
    monkeypatch.setattr(q,'_run',lambda args,cwd,env,timeout: (1, '1 failed, 2 passed', 0.3))
    report=q.qualify(root,tmp_path/'failure.zip',profile='quick')
    gates={g['id']:g for g in report['gates']}
    assert gates['source_integrity']['status']=='FAIL'
    assert gates['integrated_regression']['status']=='FAIL'
    assert report['counts']['FAIL']>=2
    assert gates['browser_real_http']['status']=='BLOCKED'


def test_rejects_source_output_and_invalid_profile(tmp_path):
    root=source_stub(tmp_path)
    with pytest.raises(ValueError,match='source tree'):
        q.qualify(root,root/'internal.zip')
    with pytest.raises(ValueError,match='profile'):
        q.qualify(root,tmp_path/'report.zip',profile='unreviewed')


def test_log_minimization_and_timeout(tmp_path):
    data=q._safe_log('token=abc email hello@example.org /private/path\n'+'Z'*100000,('/private/path',))
    assert 'token=abc' not in data
    assert 'hello@example.org' not in data
    assert '/private/path' not in data
    assert len(data)<q.MAX_LOG+500
    assert q._pytest_result(0,'8 passed, 3 skipped')[1]=={'passed':8,'skipped':3}
    assert q._pytest_result(1,'1 failed, 7 passed')[0]=='FAIL'


def test_subprocess_timeout_is_bounded(tmp_path):
    import os
    import sys
    import time
    begin=time.monotonic()
    status,log,elapsed=q._run([sys.executable,'-c','import time; time.sleep(25)'],
                              tmp_path,os.environ.copy(),1)
    assert status is None and 'TIMEOUT' in log
    assert elapsed<8 and time.monotonic()-begin<8
