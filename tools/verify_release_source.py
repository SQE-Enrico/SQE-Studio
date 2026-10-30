#!/usr/bin/env python3
"""Integrity check for an intentionally extended source tree, not A09 baseline admission.

The frozen foundation lock remains immutable as historical provenance. Unlike
`delta.py verify`, this verifies the declared *current* source inventory and
frozen contract digest without pretending the evolved tree equals foundation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_MANIFEST = 'EDA_SOURCE_MANIFEST.json'
EXCLUDE_DIRS = {'.git', '.venv', 'studio-data', '__pycache__', '.pytest_cache',
                'dist', 'build', 'node_modules', 'evidence'}


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode()


def inventory(root: Path) -> dict[str, str]:
    found = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink inside release source: ' + str(path))
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if (relative.as_posix() == SOURCE_MANIFEST or
                any(part in EXCLUDE_DIRS or part.endswith('.egg-info') for part in relative.parts) or
                path.suffix in ('.pyc', '.pyo')):
            continue
        found[relative.as_posix()] = hash_bytes(path.read_bytes())
    return found


def frozen_contract_digest(root: Path) -> str:
    rows = {p.relative_to(root).as_posix(): hash_bytes(p.read_bytes())
            for p in (root/'contracts').rglob('*') if p.is_file()}
    return hash_bytes(canonical(rows))


def verify(root: Path):
    doc = json.loads((root/SOURCE_MANIFEST).read_text(encoding='utf-8'))
    assert doc['schema'] == 'sqe.eda-source-inventory.v1'
    locked = json.loads((root/'FOUNDATION_LOCK.json').read_text())
    assert locked['tree_digest'] == doc['historical_foundation_tree_digest']
    assert locked['contract_digest'] == doc['frozen_contract_digest']
    assert frozen_contract_digest(root) == doc['frozen_contract_digest']
    assert inventory(root) == doc['files'], 'Source files differ from release manifest'
    assert hash_bytes(canonical(doc['files'])) == doc['current_source_inventory_sha256']
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--write', action='store_true', help='explicitly build source inventory')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write:
        lock = json.loads((root/'FOUNDATION_LOCK.json').read_text())
        if frozen_contract_digest(root) != lock['contract_digest']:
            parser.error('Frozen contracts changed; source inventory refused')
        files = inventory(root)
        doc = {'schema':'sqe.eda-source-inventory.v1',
               'historical_foundation_tree_digest':lock['tree_digest'],
               'frozen_contract_digest':lock['contract_digest'],
               'current_source_inventory_sha256':hash_bytes(canonical(files)),
               'files':files,
               'status':'EXPERIMENTAL_NOT_SCIENTIFICALLY_QUALIFIED',
               'note':'This is an evolved source inventory. It is not a new FOUNDATION_LOCK.'}
        (root/SOURCE_MANIFEST).write_text(json.dumps(doc, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status':'VERIFIED','inventory_sha256':verify(root)['current_source_inventory_sha256']},
                     sort_keys=True))


if __name__ == '__main__':
    main()
