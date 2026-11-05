"""A99 regression controller cannot hide unexecuted or failing test groups."""
from importlib import util
from pathlib import Path
from types import SimpleNamespace
import subprocess
import json

ROOT=Path(__file__).resolve().parents[2]
spec=util.spec_from_file_location('rc1411_regression',ROOT/'scripts/portable_regression.py')
driver=util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_fixed_driver_covers_every_test_file_including_browser_and_new_tests():
    actual={p for p in json.loads((ROOT/'EDA_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files']
            if p.startswith('tests/') and p.endswith('.py') and Path(p).name.startswith('test_')}
    assigned=set()
    for _, paths in driver.GROUPS:
        for path in paths:
            p=ROOT/path
            assigned.update({f.relative_to(ROOT).as_posix() for f in
                            (p.rglob('test_*.py') if p.is_dir() else [p] if p.is_file() else [])})
    assert actual==assigned
    assert 'tests/ui/test_browser.py' in assigned
    assert 'tests/integration/test_rc14_11_regression_driver.py' in assigned
    assert all(name not in assigned for name in driver.LEGACY_UNTRACKED)


def test_nonzero_or_missing_summary_never_promoted_to_pass(monkeypatch):
    monkeypatch.setattr(driver.subprocess,'run',lambda *_args,**_kwargs:
                         SimpleNamespace(returncode=1,stdout=b'10 passed'))
    assert driver.run_group('probe',['tests/ui/test_static.py']) is None
    monkeypatch.setattr(driver.subprocess,'run',lambda *_args,**_kwargs:
                         SimpleNamespace(returncode=0,stdout=b'no trustworthy summary'))
    assert driver.run_group('probe',['tests/ui/test_static.py']) is None


def test_timeout_never_promoted_to_pass(monkeypatch):
    def expire(*_args,**_kwargs):
        raise subprocess.TimeoutExpired('pytest',95)
    monkeypatch.setattr(driver.subprocess,'run',expire)
    assert driver.run_group('probe',['tests/ui/test_static.py']) is None


def test_regression_continues_independent_groups_after_failure(monkeypatch, capsys):
    """Keep collecting release evidence without promoting a failed group."""
    monkeypatch.setattr(driver, '_release_test_files', lambda: {
        'tests/adapters/test_a.py', 'tests/integration/test_b.py'})
    monkeypatch.setattr(driver, 'GROUPS', (
        ('adapters', ('tests/adapters',)),
        ('integration', ('tests/integration',))))
    seen=[]
    def fake_run(label, files):
        seen.append(label)
        return None if label == 'adapters' else (3, 1)
    monkeypatch.setattr(driver, 'run_group', fake_run)
    assert driver.main() == 1
    assert seen == ['adapters', 'integration']
    output=capsys.readouterr().out
    assert 'REGRESSION_GROUP_FAILED_CONTINUING adapters' in output
    assert 'REGRESSION_FAIL groups=adapters' in output
    assert 'SPLIT_PROCESS_REGRESSION_COMPLETE' not in output


def test_group_browser_capture_and_nested_temp_are_external_and_cleaned(monkeypatch, tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setattr(driver, 'ROOT', root)
    observed = {}
    def run(_command, **options):
        env = options['env']
        work = Path(env['TEMP'])
        capture = Path(env['SQE_BROWSER_CAPTURE_DIR'])
        assert work.is_dir()
        assert not work.is_relative_to(root)
        assert capture.parent == work
        assert env['TMPDIR'] == env['TMP'] == str(work)
        observed['work'] = work
        return SimpleNamespace(returncode=0, stdout=b'1 passed')
    monkeypatch.setattr(driver.subprocess, 'run', run)
    result = driver._run_group_process(['test-process'], 'ui', 5)
    assert result.returncode == 0
    assert not observed['work'].exists()
