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


def test_only_isolated_test_failure_files_collected_and_redacted(tmp_path):
    run = tmp_path / 'pytest-native_josephson_circuits' / 'case_0'
    run.mkdir(parents=True)
    (run / 'josephson_native_stderr.log').write_text(
        'ERROR: Package JosephsonCircuits not found in '+str(Path.home())+'\n', encoding='utf-8')
    (run / 'unrelated-project.json').write_text('must not appear', encoding='utf-8')
    diagnostics = q._isolated_test_diagnostics(tmp_path, 'native_josephson_circuits',
                                               (str(tmp_path),str(Path.home())))
    assert 'Package JosephsonCircuits not found' in diagnostics
    assert 'must not appear' not in diagnostics
    assert str(Path.home()) not in diagnostics
    assert q._isolated_test_diagnostics(tmp_path,'not-a-real-run',()) == ''


def test_wheel_gate_truthful_when_installed_http_smoke_fails(tmp_path,monkeypatch):
    """Packaging provenance PASS must not mask a separate HTTP FAIL."""
    root=source_stub(tmp_path)
    monkeypatch.setattr(q,'available',lambda x:x in ('setuptools.build_meta',))
    monkeypatch.setattr(q.shutil,'which',lambda _:None)
    monkeypatch.setattr(q,'_package_version',lambda x:'1.0' if x=='build' else None)
    def run(args,cwd,env,timeout):
        if '--outdir' in args:
            (Path(args[args.index('--outdir')+1])/'new-build.whl').write_bytes(b'test-only-wheel')
            return 0,'fixture-only build',0.01
        if args[-1].endswith('qualification_installed_smoke.py'):
            return 1,'fixture: authenticated local HTTP failed on Windows',0.01
        return 0,'fixture-only success',0.01
    monkeypatch.setattr(q,'_run',run)
    report=q.qualify(root,tmp_path/'packaging-evidence.zip',profile='comprehensive')
    gates={x['id']:x for x in report['gates']}
    assert gates['source_wheel_build']['status']=='PASS'
    assert gates['installed_wheel']['status']=='PASS'
    assert gates['installed_assets']['status']=='FAIL'
    with zipfile.ZipFile(tmp_path/'packaging-evidence.zip') as zip_file:
        log=zip_file.read('logs/installed_assets.txt').decode('utf8')
        assert 'authenticated local HTTP failed' in log
        assert 'exit=1' in log
        assert 'fixture-only' not in zip_file.read('logs/installed_wheel.txt').decode() or 'wheel' in zip_file.read('logs/installed_wheel.txt').decode()


def test_comprehensive_julia_probe_cannot_overwrite_report_destination(tmp_path,monkeypatch):
    """Regression for the RC9 Windows 'str has no attribute with_name' crash."""
    root=source_stub(tmp_path)
    monkeypatch.setattr(q,'available',lambda _:False)
    monkeypatch.setattr(q.shutil,'which',lambda cmd: 'julia' if cmd=='julia' else None)
    def child(args,cwd,env,timeout):
        if args and args[0]=='julia':
            return 0, 'JULIA_VERSION=1.11.0\nPRESENT', 0.01
        return 1, 'fixture-only BLOCKED', 0.01
    monkeypatch.setattr(q,'_run',child)
    dest=tmp_path/'report-from-julia.zip'
    result=q.qualify(root,dest,profile='comprehensive')
    assert dest.is_file()
    assert {x['id']:x['status'] for x in result['gates']}['julia_package_runtime']=='PASS'
    with zipfile.ZipFile(dest) as evidence:
        assert evidence.testzip() is None
        assert json.loads(evidence.read('QUALIFICATION.json'))['profile']=='comprehensive'
