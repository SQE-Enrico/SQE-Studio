"""Private M5 creation-path record for a manually saved, unreviewed Transmon.

This records only that SQE's dedicated authenticated M4 entry path created
this exact saved study. It does NOT attest the physical origin of typed EJ/EC.
No database migration and no acceptance of user-provided origin assertions.
The record is a conservative fail-closed sidecar in the private Store root;
missing/tampered/linked records must deny the M5 execution path.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..contracts import digest
from ..store import Store

_HEX = re.compile(r"[0-9a-f]{32}\Z")
_STUDY = re.compile(r"independent_transmon_(?:0[1-9]|[12][0-9]|30)\Z")
_SCHEMA = 'sqe.manual-transmon-creation-path.a99.v1'


class ManualOriginBlocked(ValueError):
    pass


def _safe_dir(store: Store, project_id: str) -> Path:
    if type(store) is not Store or type(project_id) is not str or not _HEX.fullmatch(project_id):
        raise ManualOriginBlocked('Invalid private Store/project identity')
    root = store.root
    parent = root / 'manual-transmon-creation'
    child = parent / project_id
    for path in (root, parent, child):
        if path.exists() and (path.is_symlink() or getattr(path, 'is_junction', lambda: False)()):
            raise ManualOriginBlocked('Linked origin evidence directory')
    parent.mkdir(mode=0o700, exist_ok=True)
    child.mkdir(mode=0o700, exist_ok=True)
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)() for path in (parent, child)):
        raise ManualOriginBlocked('Linked origin evidence directory')
    if not child.resolve().is_relative_to(root.resolve()):
        raise ManualOriginBlocked('Origin path outside private Store')
    return child


def _record_path(store: Store, pid: str, revision: str, study_id: str) -> Path:
    if (type(revision) is not str or not _HEX.fullmatch(revision) or
        type(study_id) is not str or not _STUDY.fullmatch(study_id)):
        raise ManualOriginBlocked('Invalid saved study identity')
    return _safe_dir(store, pid) / (revision + '-' + study_id + '.json')


def _payload(project: dict, study_id: str) -> dict:
    studies = [s for s in project['model']['studies'] if s['id'] == study_id]
    if len(studies) != 1 or studies[0]['engine'] != 'scqubits' or studies[0]['kind'] != 'quantum_spectrum':
        raise ManualOriginBlocked('Saved manual study not found')
    return {'schema': _SCHEMA, 'project_id': project['id'],
            'revision': project['revision'], 'revision_digest': project['revision_digest'],
            'study_id': study_id, 'inputs_sha256': digest(studies[0]['inputs']),
            'creation_path': 'DEDICATED_AUTHENTICATED_MANUAL_ENTRY_M4',
            'scientific_authorization': 'BLOCKED', 'fabrication': 'HOLD'}


def record_manual_study_creation(store: Store, owner: str, pid: str, revision: str, study_id: str) -> None:
    """Only the server manual-entry handler calls this immediately after commit.

    An I/O failure leaves the study unavailable to the new execution route;
    it never creates evidence retrospectively for older or generic commits.
    """
    project = store.project(owner, pid)
    if project['head'] != revision or project['revision'] != revision:
        raise ManualOriginBlocked('Saved manual study is not current head')
    path = _record_path(store, pid, revision, study_id)
    payload = (json.dumps(_payload(project, study_id), sort_keys=True,
                          separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError as exc:
        raise ManualOriginBlocked('Manual creation record already exists') from exc


def require_manual_study_creation(store: Store, owner: str, pid: str, revision: str, study_id: str) -> dict:
    """Check creation-path provenance through an immutable saved-study ancestry.

    A manual study remains eligible after later project revisions only if it
    exists with identical native inputs at EVERY intervening immutable revision.
    A study inserted through generic commit has no M4 creation record, while a
    modified-and-restored study fails its continuity check. A99 still requires
    the current, owner-scoped head and a fresh A12 exact-revision preflight.
    """
    current = store.project(owner, pid)
    if current['head'] != revision or current['revision'] != revision:
        raise ManualOriginBlocked('Stale manual origin or revision')
    original = _payload(current, study_id)
    value_hash = original['inputs_sha256']
    cursor = current
    for _ in range(128):  # bounded ancestry, fail closed on longer histories
        if (cursor['id'] != pid or cursor['revision_digest'] != digest(cursor['model']) or
                _payload(cursor, study_id)['inputs_sha256'] != value_hash):
            raise ManualOriginBlocked('Manual study changed along saved revision ancestry')
        path = _record_path(store, pid, cursor['revision'], study_id)
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ManualOriginBlocked('Linked creation-path record')
        if path.exists():
            if (not path.is_file() or path.stat().st_size > 2048 or
                    not path.resolve().is_relative_to(store.root.resolve())):
                raise ManualOriginBlocked('Invalid private origin record')
            try:
                stored = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError, OSError) as exc:
                raise ManualOriginBlocked('Malformed origin record') from exc
            if stored != _payload(cursor, study_id):
                raise ManualOriginBlocked('Saved manual creation-path record mismatch')
            return current
        if cursor['parent'] is None:
            break
        cursor = store.project(owner, pid, cursor['parent'])
    raise ManualOriginBlocked('No trusted M4 creation record in immutable study ancestry')
