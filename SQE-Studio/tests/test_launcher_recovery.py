"""Startup recovery without calling solver installers or modifying real environments."""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader('sqe_desktop_launcher', str(ROOT / 'Launch SQE Studio.pyw'))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
launcher = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(launcher)


def test_managed_launch_is_explicitly_supervised():
    calls = []
    def mock_run(args, **kw):
        calls.append((args, kw))
        return SimpleNamespace(returncode=1, stderr='ImportError: missing Tk support')
    ok, detail = launcher._run_managed_python(Path('python.exe'), Path('Launch SQE Studio.pyw'), runner=mock_run)
    assert not ok
    assert 'ImportError: missing Tk support' in detail
    args, kw = calls[0]
    assert args == ['python.exe', 'Launch SQE Studio.pyw']
    assert kw['env']['SQE_MANAGED_REEXEC'] == '1'
    assert kw['shell'] is False
    assert kw['check'] is False


def test_managed_launch_non_crash_and_spawn_failure():
    ok, detail = launcher._run_managed_python(Path('python.exe'), Path('launcher.pyw'),
                                               runner=lambda *a, **k: SimpleNamespace(returncode=0, stderr=''))
    assert ok and detail == ''
    def raising(*a, **k):
        raise OSError('interpreter missing')
    ok, detail = launcher._run_managed_python(Path('python.exe'), Path('launcher.pyw'), runner=raising)
    assert not ok and 'interpreter missing' in detail


def test_launcher_diagnostic_log_stays_local(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    log = launcher._launcher_log('test failure')
    assert log == tmp_path / 'SQE-Studio' / 'launcher-errors.log'
    assert 'test failure' in log.read_text(encoding='utf-8')
    assert not (ROOT / 'launcher-errors.log').exists()
