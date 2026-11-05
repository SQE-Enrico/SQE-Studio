"""Direct hotfix regression: source attestation never upgrades a dirty host gate."""
import json
import shutil
from pathlib import Path

from sqe_studio import cycle_qualification as cycle

ROOT = Path(__file__).resolve().parents[2]


def _clone(tmp_path):
    def ignore(_folder, names):
        return set(names) & {'__pycache__', '.pytest_cache', 'qualification-reports', '.venv', 'build'}
    destination = tmp_path/'release'
    shutil.copytree(ROOT, destination, ignore=ignore)
    return destination


def _failed_gate():
    return {'software/QUALIFICATION.json': json.dumps({'gates': [
        {'id': 'source_integrity', 'status': 'FAIL'}]}).encode()}


def test_no_bypass_on_clean_root_or_unrelated_extra(tmp_path):
    source = _clone(tmp_path)
    assert not cycle._trusted_release_with_legacy_tests(source)
    assert cycle._trusted_case_commands(source, _failed_gate()) == {}
    (source/'tests/integration/untrusted.py').write_text('bad', encoding='utf-8')
    assert not cycle._trusted_release_with_legacy_tests(source)
    assert cycle._trusted_case_commands(source, _failed_gate()) == {}


def test_only_known_stale_test_files_can_be_attested_for_native_diagnostics(tmp_path):
    source = _clone(tmp_path)
    (source/'tests/integration/test_rc14_8_a99_release.py').write_text(
        'historical test, never imported', encoding='utf-8')
    assert cycle._trusted_release_with_legacy_tests(source)
    assert set(cycle._trusted_case_commands(source, _failed_gate())) == {'B05', 'B08', 'B09'}
    # A single byte changed in a tracked file revokes numerical execution.
    with (source/'src/sqe_studio/server.py').open('ab') as stream:
        stream.write(b'\n# altered\n')
    assert not cycle._trusted_release_with_legacy_tests(source)
    assert cycle._trusted_case_commands(source, _failed_gate()) == {}


def test_frozen_contract_change_blocks_native_diagnostics(tmp_path):
    source = _clone(tmp_path)
    (source/'tests/integration/test_rc14_10_a99_release.py').write_text(
        'historical test', encoding='utf-8')
    assert cycle._trusted_release_with_legacy_tests(source)
    contract = next((source/'contracts').rglob('*.json'))
    with contract.open('ab') as stream:
        stream.write(b' ')
    assert not cycle._trusted_release_with_legacy_tests(source)
