"""Extended product provenance is separate from the unchanged historical foundation lock."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest


def test_extended_source_inventory_and_frozen_contracts():
    root = Path(__file__).resolve().parents[2]
    tool = root/'tools/verify_release_source.py'
    spec = importlib.util.spec_from_file_location('verify_extended_release_source', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.verify(root)
    assert manifest['status'] == 'EXPERIMENTAL_NOT_SCIENTIFICALLY_QUALIFIED'
    assert 'src/sqe_studio/eda/use_cases.py' in manifest['files']
    assert 'docs/DEVELOPMENT.md' in manifest['files']
    assert 'src/sqe_studio/eda/capabilities.py' in manifest['files']
    assert 'docs/LITERATURE_WORKFLOW_LAPTOP.md' not in manifest['files']
    assert 'scripts/laptop_resonator.py' not in manifest['files']


# A10 synthetic verifier fixtures: no native scientific qualification.

TOOL = Path(__file__).resolve().parents[2] / 'tools' / 'verify_release_source.py'
spec = importlib.util.spec_from_file_location('a10_release_verifier', TOOL)
verifier = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(verifier)


def _fixture(root: Path) -> Path:
    (root / 'contracts').mkdir(parents=True)
    (root / 'contracts' / 'schema.json').write_text('{"kind":"frozen"}\n', encoding='utf-8')
    (root / 'src' / 'package').mkdir(parents=True)
    (root / 'src' / 'package' / 'feature.py').write_text('ENABLED = True\n', encoding='utf-8')
    contract_hash = verifier.frozen_contract_digest(root)
    (root / 'FOUNDATION_LOCK.json').write_text(json.dumps({
        'tree_digest': 'historical-tree', 'contract_digest': contract_hash,
    }), encoding='utf-8')
    files = verifier.inventory(root)
    (root / 'EDA_SOURCE_MANIFEST.json').write_text(json.dumps({
        'schema': 'sqe.eda-source-inventory.v1',
        'historical_foundation_tree_digest': 'historical-tree',
        'frozen_contract_digest': contract_hash,
        'current_source_inventory_sha256': verifier.hash_bytes(verifier.canonical(files)),
        'files': files,
    }), encoding='utf-8')
    assert verifier.verify(root)
    return root


def test_optimized_python_still_rejects_fake_frozen_contract_digest(tmp_path):
    """-O must not erase an authority check by disabling an assert."""
    root = _fixture(tmp_path / 'release')
    lock_path = root / 'FOUNDATION_LOCK.json'
    document_path = root / 'EDA_SOURCE_MANIFEST.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    doc = json.loads(document_path.read_text(encoding='utf-8'))
    fake = '0' * 64
    lock['contract_digest'] = fake
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    doc['frozen_contract_digest'] = fake
    # Inventory hashes match the mutated file exactly. Only the frozen
    # contract check can catch this attempted historical-lock forgery.
    doc['files'] = verifier.inventory(root)
    doc['current_source_inventory_sha256'] = verifier.hash_bytes(verifier.canonical(doc['files']))
    document_path.write_text(json.dumps(doc), encoding='utf-8')
    result = subprocess.run([sys.executable, '-O', str(TOOL), str(root)],
                            capture_output=True, text=True, check=False, timeout=15)
    assert result.returncode != 0, result.stdout
    assert 'Frozen contract' in result.stderr or 'frozen contract' in result.stderr


def test_root_build_wheel_symlinks_do_not_invalidate_source_inventory(tmp_path):
    """Installed/build outputs are not part of the distributed source identity."""
    root = _fixture(tmp_path / 'release')
    wheel_dir = root / 'wheels'
    wheel_dir.mkdir()
    (wheel_dir / 'old.whl').write_bytes(b'old build artifact')
    try:
        (wheel_dir / 'platform-link.whl').symlink_to(wheel_dir / 'old.whl')
    except (OSError, NotImplementedError):
        pytest.skip('Host does not permit symlink creation')
    assert verifier.verify(root)
    assert not any(name.startswith('wheels/') for name in verifier.inventory(root))


def test_a_nested_build_named_path_is_still_tracked_source(tmp_path):
    """An attacker may not hide release source under a nested 'wheels' folder."""
    root = _fixture(tmp_path / 'release')
    nested = root / 'src' / 'package' / 'wheels'
    nested.mkdir()
    (nested / 'new.py').write_text('INJECTED = True\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Source inventory mismatch') as exc:
        verifier.verify(root)
    assert 'src/package/wheels/new.py' in str(exc.value)


def test_real_source_tamper_and_link_are_never_ignored(tmp_path):
    root = _fixture(tmp_path / 'release')
    source = root / 'src' / 'package' / 'feature.py'
    source.write_text('ENABLED = False\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Source inventory mismatch') as exc:
        verifier.verify(root)
    assert 'src/package/feature.py' in str(exc.value)
    source.write_text('ENABLED = True\n', encoding='utf-8')
    try:
        (root / 'src' / 'package' / 'linked.py').symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip('Host does not permit symlink creation')
    with pytest.raises(ValueError, match='Symlink inside release source'):
        verifier.inventory(root)


def test_orphan_rc14_8_test_file_is_genuine_source_contamination(tmp_path):
    """The stale Windows working-tree fixture is absent from the dispatch;
    never silently exclude it or misdiagnose it as frozen-lock corruption.
    """
    root = _fixture(tmp_path / 'release')
    stale = root / 'tests/integration/test_rc14_8_a99_release.py'
    stale.parent.mkdir(parents=True)
    stale.write_text('def test_obsolete_rc148(): assert False\n', encoding='utf-8')
    with pytest.raises(verifier.SourceInventoryMismatch, match='Source inventory mismatch') as exc:
        verifier.verify(root)
    detail = json.loads(str(exc.value).split('Source inventory mismatch: ', 1)[1])
    assert detail['added'] == ['tests/integration/test_rc14_8_a99_release.py']
    assert detail['counts']['changed'] == 0
    assert detail['counts']['missing'] == 0


@pytest.mark.parametrize('orphan', [
    'tests/integration/test_rc14_8_a99_release.py',
    'tests/integration/test_rc14_9_a99_release.py',
    'tests/integration/test_rc14_10_a99_release.py',
])
def test_rc1410_windows_stale_release_tests_are_never_ignored(tmp_path, orphan):
    """Windows-report contaminants from RC14.8/9/10 are source, not caches."""
    root = _fixture(tmp_path / 'release')
    assert not (root / orphan).exists()
    file = root / orphan
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('def test_stale(): assert False\n', encoding='utf-8')
    with pytest.raises(verifier.SourceInventoryMismatch) as caught:
        verifier.verify(root)
    changed = json.loads(str(caught.value).split('Source inventory mismatch: ', 1)[1])
    assert changed['added'] == [orphan]
    assert changed['counts'] == {'added': 1, 'changed': 0, 'missing': 0}


@pytest.mark.parametrize('relative', [
    '.', 'src/package', 'src/package/feature.py',
    'contracts', 'contracts/schema.json',
])
def test_win311_reparse_junction_metadata_fails_closed(monkeypatch, tmp_path, relative):
    """Win32 junctions are not reliably Path.is_symlink() on Python 3.11.

    Portable simulation of the public st_file_attributes reparse-point bit;
    this test does NOT claim execution on a Windows host.
    """
    root = _fixture(tmp_path / 'release')
    blocked = root if relative == '.' else root / relative
    real_lstat = Path.lstat

    def marked_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if path == blocked:
            return SimpleNamespace(st_mode=info.st_mode,
                                   st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, 'lstat', marked_lstat)
    with pytest.raises(ValueError, match='Windows reparse point'):
        verifier.verify(root)


def test_windows_file_metadata_access_denied_is_io_not_tamper(monkeypatch, tmp_path):
    root = _fixture(tmp_path / 'release')
    blocked = root / 'src/package/feature.py'
    real_lstat = Path.lstat

    def denied_lstat(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError(13, 'WinError 5 simulated')
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', denied_lstat)
    with pytest.raises(verifier.SourceInventoryIOError, match='metadata unreadable'):
        verifier.verify(root)


def test_directory_enumeration_error_is_not_reported_as_tamper(monkeypatch, tmp_path):
    root = _fixture(tmp_path / 'release')

    def inaccessible_walk(*_args, **kwargs):
        kwargs['onerror'](PermissionError('unreadable directory'))
        yield  # makes this a lazy generator, just like os.walk

    monkeypatch.setattr(verifier.os, 'walk', inaccessible_walk)
    with pytest.raises(verifier.SourceInventoryIOError, match='enumeration failed'):
        verifier.verify(root)


def test_source_file_read_error_is_not_inventory_mismatch(monkeypatch, tmp_path):
    root = _fixture(tmp_path / 'release')
    real_read_bytes = Path.read_bytes

    def blocked_read(path):
        if path.name == 'feature.py':
            raise PermissionError('simulated Windows access denied')
        return real_read_bytes(path)

    monkeypatch.setattr(Path, 'read_bytes', blocked_read)
    with pytest.raises(verifier.SourceInventoryIOError, match='file unreadable') as exc:
        verifier.verify(root)
    assert 'src/package/feature.py' in str(exc.value)
