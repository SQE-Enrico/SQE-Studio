"""Regression: browser evidence must never mutate the release source tree.

Real browser playback uses a temporary directory, or the qualification-owned
external capture directory. Neither case weakens the source attestation.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_browser_case_does_not_create_untracked_release_files(monkeypatch, tmp_path):
    pytest.importorskip('playwright')
    monkeypatch.delenv('SQE_BROWSER_CAPTURE_DIR', raising=False)
    # The browser viewport path test writes a synthetic capture. It requires
    # neither the browser binary nor a scientific runtime.
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               'tests/ui/test_browser.py::test_viewport_capture_outside_project_tree',
               'tests/ui/test_browser.py::test_capture_destination_is_not_release_source',
               '--basetemp=' + str(tmp_path / 'isolated-pytest')]
    env = os.environ.copy()
    env.pop('SQE_BROWSER_CAPTURE_DIR', None)
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=55)
    assert proc.returncode == 0, proc.stdout + '\n' + proc.stderr
    spec = importlib.util.spec_from_file_location(
        'release_source_verifier_isolation', ROOT/'tools/verify_release_source.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    assert verifier.verify(ROOT)['schema'] == 'sqe.eda-source-inventory.v1'
    assert not (ROOT/'reports/agents/A07/screenshots').exists()


def test_browser_capture_is_configured_before_portable_regression():
    source = (ROOT/'src/sqe_studio/qualification.py').read_text(encoding='utf-8')
    # If this ordering changes, a clean source tree may become dirty before
    # deep browser acceptance, even though the later browser gate is isolated.
    setup = source.index("env['SQE_BROWSER_CAPTURE_DIR'] = str(work/'browser-captures')")
    regression = source.index("invoke('integrated_regression'")
    assert setup < regression
