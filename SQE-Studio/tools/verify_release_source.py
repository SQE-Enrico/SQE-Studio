#!/usr/bin/env python3
"""Verify the current source inventory, separately from historical foundation admission.

Generated artifacts are excluded, but genuine source, its frozen contracts,
and the expected inventory digest must all agree. This verifier must behave
identically under ordinary Python and ``python -O``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

class SourceInventoryIOError(OSError):
    """Source could not be read/enumerated; never mistaken for clean or changed."""


class SourceInventoryMismatch(ValueError):
    """Readable source differs from the pinned inventory."""


SOURCE_MANIFEST = 'EDA_SOURCE_MANIFEST.json'
# Only top-level directories may be treated as release/build artifacts. A
# nested src/package/wheels/ is application source, not a build output.
ROOT_ARTIFACT_DIRS = {'.git', '.venv', 'studio-data', 'dist', 'build',
                      'release', 'node_modules', 'evidence', 'wheels',
                      'qualification-reports'}
# These caches and Python packaging metadata can occur below any directory.
TRANSIENT_DIRS = {'__pycache__', '.pytest_cache'}


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _ignored_dir(name: str, *, at_root: bool) -> bool:
    return (name in TRANSIENT_DIRS or name.endswith('.egg-info') or
            (at_root and name in ROOT_ARTIFACT_DIRS))


def _source_lstat(path: Path, relative: str) -> os.stat_result:
    """Refuse filesystem aliases *without following* them, including Win11 junctions.

    In Python 3.11 a Windows junction need not satisfy ``is_symlink()``.
    The Win32 reparse-point bit is exposed by the public ``os.lstat`` result;
    a fake, unreadable or exotic source is not a clean inventory.  Never
    silently skip a reparse point below source or frozen contracts.
    """
    try:
        info = path.lstat()
    except OSError as exc:
        raise SourceInventoryIOError('Source metadata unreadable: ' + relative) from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('Symlink inside release source: ' + relative)
    if getattr(info, 'st_file_attributes', 0) & getattr(
            stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
        raise ValueError('Windows reparse point inside release source: ' + relative)
    return info


def inventory(root: Path) -> dict[str, str]:
    """SHA-256 regular source files; reject any symlink inside source scope.

    Prune build directories *before* visiting them. Windows wheel caches and
    virtual environments may contain platform-specific links and need not be
    walked, while links within the actual release source remain forbidden.
    """
    found: dict[str, str] = {}

    if not stat.S_ISDIR(_source_lstat(root, '.').st_mode):
        raise ValueError('Release source root is not a directory')

    def unreadable(exc: OSError) -> None:
        # Without onerror, os.walk silently skips inaccessible source trees,
        # which can turn an unreadable checkout into misleading inventory data.
        raise SourceInventoryIOError('Source inventory enumeration failed') from exc

    for base, dirnames, filenames in os.walk(root, topdown=True,
                                             followlinks=False, onerror=unreadable):
        folder = Path(base)
        at_root = folder == root
        retained = []
        for name in sorted(dirnames):
            if _ignored_dir(name, at_root=at_root):
                continue
            path = folder / name
            relative = path.relative_to(root).as_posix()
            if not stat.S_ISDIR(_source_lstat(path, relative).st_mode):
                raise ValueError('Non-directory release source: ' + relative)
            retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            if name.endswith(('.pyc', '.pyo')):
                continue
            path = folder / name
            relative = path.relative_to(root).as_posix()
            if relative == SOURCE_MANIFEST:
                continue
            if not stat.S_ISREG(_source_lstat(path, relative).st_mode):
                raise ValueError('Non-regular release source: ' + relative)
            try:
                found[relative] = hash_bytes(path.read_bytes())
            except OSError as exc:
                raise SourceInventoryIOError(
                    'Source inventory file unreadable: ' + relative) from exc
    return dict(sorted(found.items()))


def frozen_contract_digest(root: Path) -> str:
    folder = root / 'contracts'
    if not stat.S_ISDIR(_source_lstat(folder, 'contracts').st_mode):
        raise ValueError('Frozen contracts directory missing or linked')
    rows = {}
    def unreadable(exc: OSError) -> None:
        raise SourceInventoryIOError('Frozen contracts enumeration failed') from exc
    for base, dirnames, filenames in os.walk(folder, topdown=True,
                                             followlinks=False, onerror=unreadable):
        for name in sorted(dirnames):
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            if not stat.S_ISDIR(_source_lstat(path, relative).st_mode):
                raise ValueError('Non-directory frozen contract: ' + relative)
        for name in sorted(filenames):
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            if not stat.S_ISREG(_source_lstat(path, relative).st_mode):
                raise ValueError('Non-regular frozen contract: ' + relative)
            try:
                rows[relative] = hash_bytes(path.read_bytes())
            except OSError as exc:
                raise SourceInventoryIOError('Frozen contract file unreadable: ' + relative) from exc
    return hash_bytes(canonical(rows))


def verify(root: Path) -> dict:
    doc = json.loads((root / SOURCE_MANIFEST).read_text(encoding='utf-8'))
    if not isinstance(doc, dict) or doc.get('schema') != 'sqe.eda-source-inventory.v1':
        raise ValueError('Source inventory schema mismatch')
    locked = json.loads((root / 'FOUNDATION_LOCK.json').read_text(encoding='utf-8'))
    if (locked.get('tree_digest') != doc.get('historical_foundation_tree_digest') or
            locked.get('contract_digest') != doc.get('frozen_contract_digest')):
        raise ValueError('Historical foundation lock mismatch')
    if frozen_contract_digest(root) != doc['frozen_contract_digest']:
        raise ValueError('Frozen contract digest mismatch')
    expected = doc.get('files')
    if not isinstance(expected, dict):
        raise ValueError('Source inventory files missing or malformed')
    current = inventory(root)
    if current != expected:
        unexpected = sorted(set(current) - set(expected))
        missing = sorted(set(expected) - set(current))
        changed = sorted(name for name in current.keys() & expected.keys()
                         if current[name] != expected[name])
        # Paths relative to source tree only. Never print user home directories.
        detail = {'added': unexpected[:30], 'missing': missing[:30],
                  'changed': changed[:30],
                  'counts': {'added': len(unexpected), 'missing': len(missing),
                             'changed': len(changed)}}
        raise SourceInventoryMismatch('Source inventory mismatch: ' + json.dumps(detail, sort_keys=True))
    if hash_bytes(canonical(expected)) != doc.get('current_source_inventory_sha256'):
        raise ValueError('Source inventory digest mismatch')
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--write', action='store_true', help='explicitly build source inventory')
    args = parser.parse_args()
    # absolute() retains the last filesystem component, unlike resolve();
    # verifying a junction-root must not silently verify its target instead.
    root = args.root.absolute()
    if args.write:
        lock = json.loads((root / 'FOUNDATION_LOCK.json').read_text(encoding='utf-8'))
        if frozen_contract_digest(root) != lock['contract_digest']:
            parser.error('Frozen contracts changed; source inventory refused')
        files = inventory(root)
        doc = {'schema': 'sqe.eda-source-inventory.v1',
               'historical_foundation_tree_digest': lock['tree_digest'],
               'frozen_contract_digest': lock['contract_digest'],
               'current_source_inventory_sha256': hash_bytes(canonical(files)),
               'files': files,
               'status': 'EXPERIMENTAL_NOT_SCIENTIFICALLY_QUALIFIED',
               'note': 'This is an evolved source inventory. It is not a new FOUNDATION_LOCK.'}
        (root / SOURCE_MANIFEST).write_text(json.dumps(doc, sort_keys=True, indent=2) + '\n',
                                            encoding='utf-8')
    print(json.dumps({'status': 'VERIFIED',
                      'inventory_sha256': verify(root)['current_source_inventory_sha256']},
                     sort_keys=True))


if __name__ == '__main__':
    main()
