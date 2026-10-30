"""Scheduler status-file robustness, not a native scientific calculation."""
import json
from pathlib import Path

import pytest
import sqe_studio.jobs as jobs


def sharing_error():
    error = PermissionError(5, 'Windows sharing violation')
    error.winerror = 5
    return error


def test_status_write_retries_transient_windows_sharing_violation(tmp_path, monkeypatch):
    path = tmp_path / 'PROGRESS.json'
    path.write_text('{"prior":true}', encoding='utf-8')
    real = jobs.os.replace
    attempts = []

    def replace(source, target):
        attempts.append((source, target))
        if len(attempts) <= 2:
            # The prior committed JSON must remain valid until the replacement.
            assert json.loads(path.read_text(encoding='utf-8')) == {'prior': True}
            raise sharing_error()
        return real(source, target)

    monkeypatch.setattr(jobs.os, 'replace', replace)
    monkeypatch.setattr(jobs.time, 'sleep', lambda *_: None)
    jobs._atomic_json(path, {'phase': 'running'})
    assert len(attempts) == 3
    assert json.loads(path.read_text(encoding='utf-8')) == {'phase': 'running'}
    assert not list(tmp_path.glob('*.tmp'))


def test_status_write_never_truncates_on_persistent_windows_lock(tmp_path, monkeypatch):
    path = tmp_path / 'PROGRESS.json'
    path.write_text('{"prior":true}', encoding='utf-8')
    monkeypatch.setattr(jobs.os, 'replace', lambda *args: (_ for _ in ()).throw(sharing_error()))
    monkeypatch.setattr(jobs.time, 'sleep', lambda *_: None)
    with pytest.raises(PermissionError):
        jobs._atomic_json(path, {'phase': 'blocked'})
    assert json.loads(path.read_text(encoding='utf-8')) == {'prior': True}
    assert not list(tmp_path.glob('*.tmp'))
