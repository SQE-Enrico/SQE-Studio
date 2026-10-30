"""Immutable content-addressed provenance for native, never synthetic, files.

The run directory is trusted application storage. Callers must authorize the
project/run through Store *before* handing a directory to this module.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
from typing import Mapping
from ..contracts import digest

MAX_NATIVE_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
HEX = set('0123456789abcdef')
ARTIFACT_TYPES = {
    'quantum_metal': frozenset({'quantum_metal.qdesign_recipe', 'quantum_metal.gdsii'}),
    'sqdmetal_palace': frozenset({'gmsh.mesh', 'palace.deck', 'palace.eigenmodes',
                                  'palace.sparameters', 'palace.capacitance_matrix'}),
    'scqubits': frozenset({'scqubits.spectrum'}),
    'josephson_circuits': frozenset({'josephson.sparameters'}),
}
RESULT_TYPES = {'quantum_metal': 'quantum_metal.gdsii',
                'scqubits': 'scqubits.spectrum',
                'josephson_circuits': 'josephson.sparameters'}
DISTRIBUTIONS = {'quantum_metal': ('quantum-metal', 'qiskit-metal'),
                 'sqdmetal_palace': ('SQDMetal',), 'scqubits': ('scqubits',)}


class ArtifactInvalid(ValueError):
    """An input/output cannot be trusted as a current native artifact."""


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def safe_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or len(name) > 240 or '\\' in name or ':' in name:
        raise ArtifactInvalid('Invalid native artifact path')
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ('.', '..', '') for part in name.split('/')) or name.startswith('/'):
        raise ArtifactInvalid('Native artifact path escapes output folder')
    path = root.joinpath(*p.parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ArtifactInvalid('Missing, linked or external native artifact')
    if path.stat().st_size > MAX_NATIVE_BYTES:
        raise ArtifactInvalid('Native artifact exceeds 128 MiB limit')
    return path


def engine_version(engine: str) -> str | None:
    """No native runtime import or executable spawning for cache discovery."""
    for candidate in DISTRIBUTIONS.get(engine, ()):
        try:
            version = metadata.version(candidate)
            if version:
                return version
        except metadata.PackageNotFoundError:
            continue
    return None


def adapter_digest(engine: str) -> str:
    """Hash installed allowlisted adapter source; never accept import paths."""
    from ..adapters.registry import REGISTRY
    if engine not in REGISTRY:
        raise ArtifactInvalid('Unrecognized engine')
    source = Path(REGISTRY[engine].__code__.co_filename)
    if not source.is_file():
        raise ArtifactInvalid('Native adapter source not available')
    return sha_bytes(source.read_bytes())


def fingerprint(*, revision_id: str, project_digest: str, study: Mapping,
                native_version: str, adapter_sha256: str, parent_sha256: tuple[str, ...] = ()) -> str:
    if (not revision_id or not valid_sha(project_digest) or not native_version or
            not valid_sha(adapter_sha256) or any(not valid_sha(p) for p in parent_sha256)):
        raise ArtifactInvalid('Incomplete cache fingerprint provenance')
    return digest({'schema': 'sqe.cache.v1', 'revision': revision_id,
                   'source_sha256': project_digest, 'engine': study['engine'],
                   'study': study, 'native_version': native_version,
                   'adapter_sha256': adapter_sha256, 'parents': list(parent_sha256)})


@dataclass(frozen=True)
class ArtifactRef:
    artifact_type: str
    engine: str
    engine_version: str
    revision_id: str
    project_digest: str
    scientific_status: str
    manifest_sha256: str
    content_sha256: tuple[str, ...]
    cache_fingerprint: str | None

    def as_parent(self) -> dict:
        return {'artifact_type': self.artifact_type, 'engine': self.engine,
                'engine_version': self.engine_version, 'revision_id': self.revision_id,
                'project_digest': self.project_digest, 'scientific_status': self.scientific_status,
                'manifest_sha256': self.manifest_sha256,
                'content_sha256': list(self.content_sha256)}


def verify_manifest(output: Path, *, revision_id: str, project_digest: str,
                    study_id: str | None = None, engine: str | None = None,
                    cache_fingerprint: str | None = None) -> ArtifactRef:
    """Re-hash *every* recorded native file before accepting a result/cache hit."""
    root = Path(output).resolve()
    manifest_file = safe_file(root, 'RESULT_MANIFEST.json')
    if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
        raise ArtifactInvalid('Oversize native result manifest')
    raw = manifest_file.read_bytes()
    try:
        m = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ArtifactInvalid('Malformed native result manifest') from exc
    if not isinstance(m, dict) or m.get('schema') != 'sqe.artifact.v1':
        raise ArtifactInvalid('Unknown result manifest schema')
    if m.get('revision_id') != revision_id or m.get('project_digest') != project_digest:
        raise ArtifactInvalid('Artifact is from an old or different revision')
    if engine is not None and m.get('engine') != engine:
        raise ArtifactInvalid('Wrong native engine')
    if study_id is not None and m.get('study_id') != study_id:
        raise ArtifactInvalid('Wrong saved study identity')
    if cache_fingerprint is not None and m.get('cache_fingerprint') != cache_fingerprint:
        raise ArtifactInvalid('Stale fingerprint; cached output cannot validate current inputs')
    kind = m.get('artifact_type')
    if kind not in ARTIFACT_TYPES.get(m.get('engine'), ()):
        raise ArtifactInvalid('Unrecognized engine artifact type')
    if m.get('scientific_status') not in ('review_required', 'reviewed'):
        raise ArtifactInvalid('Native output lacks an explicit review status')
    if not isinstance(m.get('engine_version'), str) or not m['engine_version']:
        raise ArtifactInvalid('Unknown engine version')
    if m.get('fabrication_status') != 'HOLD':
        raise ArtifactInvalid('Output incorrectly promotes fabrication status')
    entries = m.get('artifacts')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        raise ArtifactInvalid('Result has no declared native files')
    hashes, names = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'name', 'sha256', 'bytes'}:
            raise ArtifactInvalid('Malformed native file record')
        if entry['name'] in names or not valid_sha(entry['sha256']):
            raise ArtifactInvalid('Duplicate or unhashable artifact')
        names.add(entry['name'])
        path = safe_file(root, entry['name'])
        if path.stat().st_size != entry['bytes'] or sha_bytes(path.read_bytes()) != entry['sha256']:
            raise ArtifactInvalid('Native output contents changed after generation')
        hashes.append(entry['sha256'])
    if not isinstance(m.get('provenance'), dict) or m['provenance'].get('used_revision') != revision_id or m['provenance'].get('used_project_sha256') != project_digest:
        raise ArtifactInvalid('Incomplete revision provenance')
    if m.get('cache_fingerprint') is not None and not valid_sha(m['cache_fingerprint']):
        raise ArtifactInvalid('Invalid result fingerprint')
    parents = m.get('parents', [])
    if not isinstance(parents, list) or len(parents) > 32:
        raise ArtifactInvalid('Invalid upstream artifact chain')
    for p in parents:
        if not isinstance(p, dict) or p.get('revision_id') != revision_id or p.get('project_digest') != project_digest or not valid_sha(p.get('manifest_sha256')):
            raise ArtifactInvalid('Unverifiable or stale upstream artifact')
    return ArtifactRef(kind, m['engine'], m['engine_version'], revision_id, project_digest,
                       m['scientific_status'], sha_bytes(raw), tuple(hashes), m.get('cache_fingerprint'))


def parent_for_run(store, owner: str, project: str, run_id: str, *, revision_id: str,
                   project_digest: str) -> ArtifactRef:
    """Only a Store-authorized completed run can serve as an upstream parent."""
    run = store.run(owner, project, run_id)
    if run['state'] != 'completed' or run['revision_id'] != revision_id:
        raise ArtifactInvalid('Upstream run incomplete or from another revision')
    output = Path(run['path']) / 'output'
    return verify_manifest(output, revision_id=revision_id, project_digest=project_digest,
                           study_id=run['study_id'], engine=run['engine'])
