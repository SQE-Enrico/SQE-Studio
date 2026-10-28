"""Bounded, deterministic support archives for browser-operated research jobs.

The bundle is a snapshot for sharing with a collaborator, not a scientific
validation certificate. Only allowlisted files are included; credentials,
project databases, and arbitrary user attachments are deliberately excluded.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

from .auth import Problem

MAX_FILES = 300
MAX_TOTAL = 24 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
SAFE_EXT = {'.json', '.txt', '.log', '.csv', '.md', '.html', '.yaml', '.yml',
            '.jl', '.png', '.jpg', '.jpeg', '.pdf', '.gds'} | {f'.s{i}p' for i in range(1, 9)}
SAFE_NAME = re.compile(r'^[a-zA-Z0-9_.-]+$')


def create_support_bundle(destination: Path, folder: Path, *, category: str, job: dict,
                          include_inputs: bool = False) -> Path:
    """Create an atomic ZIP with traceable checksums and explicit omissions.

    The caller performs authorization before calling this helper. The folder
    must be an application-owned run folder, never an arbitrary user path.
    """
    root = folder.resolve()
    if not folder.is_dir() or folder.is_symlink() or not root.is_dir():
        raise Problem('The run has no output directory yet', 409)
    destination.parent.mkdir(parents=True, exist_ok=True)
    items = []
    skipped = []
    total = 0
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        relative = path.relative_to(folder).as_posix()
        parts = Path(relative).parts
        if any(not SAFE_NAME.fullmatch(part) or part.startswith('.') for part in parts):
            skipped.append({'file': relative, 'reason': 'Unsafe name'})
            continue
        if not include_inputs and parts[0] == 'inputs':
            skipped.append({'file': relative, 'reason': 'Source snapshot omitted'})
            continue
        if path.suffix.lower() not in SAFE_EXT:
            skipped.append({'file': relative, 'reason': 'File type excluded'})
            continue
        length = path.stat().st_size
        if length > MAX_FILE or total + length > MAX_TOTAL or len(items) >= MAX_FILES:
            skipped.append({'file': relative, 'reason': 'Support bundle size limit'})
            continue
        content = path.read_bytes()
        if len(content) != length:
            skipped.append({'file': relative, 'reason': 'File changed during export'})
            continue
        items.append((relative, content))
        total += length
    manifest = {
        'schema_version': 1,
        'category': category,
        'run': {k: v for k, v in job.items() if k in
                ('id', 'state', 'mode', 'target', 'stage', 'created', 'started',
                 'finished', 'error', 'summary', 'created_utc', 'completed_utc')},
        'checksums_sha256': {name: hashlib.sha256(content).hexdigest() for name, content in items},
        'excluded': skipped,
        'verified_solver_accuracy': False,
        'privacy_warning': 'Review files before sharing. Logs and source data may reveal project details.',
    }
    readme = (
        'SQE Studio support bundle\n'
        '=========================\n'
        'Share this single ZIP when reporting a reproducibility or solver issue.\n'
        'manifest.json contains file checksums and a list of excluded files.\n'
        'Files in artifacts/ are untrusted solver outputs and may contain sensitive data.\n'
        'A completed run is not proof of physical accuracy or fabrication readiness.\n'
        'The archive is not automatically uploaded anywhere.\n'
    )
    temporary = destination.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=False) as archive:
            archive.writestr('README.txt', readme)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2, default=str) + '\n')
            for name, content in items:
                archive.writestr('artifacts/' + name, content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
