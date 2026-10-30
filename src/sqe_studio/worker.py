"""Bounded native adapter worker; never derives scientific numbers itself."""
from __future__ import annotations
import json
import math
import re
from copy import deepcopy
import sys
from pathlib import Path
from .adapters.registry import REGISTRY
from .contracts import digest, validate_project
from .orchestration.artifacts import (ARTIFACT_TYPES, RESULT_TYPES, MAX_NATIVE_BYTES,
                                      adapter_digest, fingerprint, safe_file, sha_bytes,
                                      valid_sha, ArtifactInvalid)


def write(path, obj):
    path = Path(path)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf8')


def _validated_snapshot(snap):
    if not isinstance(snap, dict) or not isinstance(snap.get('project'), dict):
        raise ValueError('Native worker requires a saved project snapshot')
    model = validate_project(snap['project'])
    if not valid_sha(snap.get('project_digest')) or digest(model) != snap['project_digest']:
        raise ValueError('Project content digest does not match the revision snapshot')
    if not isinstance(snap.get('revision_id'), str) or not snap['revision_id']:
        raise ValueError('Missing immutable revision ID')
    study = snap.get('study')
    if not isinstance(study, dict) or study.get('engine') not in REGISTRY:
        raise ValueError('Unknown native engine')
    saved = [s for s in model['studies'] if s['id'] == study.get('id')]
    if len(saved) != 1 or saved[0]['engine'] != study['engine']:
        raise ValueError('Worker requires a study saved in the immutable revision')
    sweep = snap.get('sweep_point')
    if sweep is None:
        if study != saved[0]:
            raise ValueError('Worker study differs from saved revision')
    else:
        if not isinstance(sweep, dict) or sweep.get('mode') not in ('manual', 'automatic') or not isinstance(sweep.get('index'), int) or sweep['index'] < 0 or not valid_sha(sweep.get('options_digest')):
            raise ValueError('Invalid saved-revision sweep derivation')
        coords = sweep.get('coordinates')
        if (not isinstance(coords, list) or not 1 <= len(coords) <= 3 or
                len({c[0] for c in coords if isinstance(c, list) and len(c) == 2}) != len(coords)):
            raise ValueError('Sweep coordinate list is invalid')
        reconstructed = deepcopy(saved[0])
        for item in coords:
            if (not isinstance(item, list) or len(item) != 2 or
                    not isinstance(item[0], str) or
                    not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){0,3}', item[0]) or
                    type(item[1]) not in (int, float) or not math.isfinite(item[1])):
                raise ValueError('Unsafe sweep coordinate')
            path = item[0].split('.')
            target = reconstructed['inputs']
            for segment in path[:-1]:
                if not isinstance(target, dict) or segment not in target:
                    raise ValueError('Sweep path is absent from saved study')
                target = target[segment]
            if (not isinstance(target, dict) or path[-1] not in target or
                    type(target[path[-1]]) not in (int, float)):
                raise ValueError('Sweep can only vary numeric saved study inputs')
            target[path[-1]] = item[1]
        if study != reconstructed:
            raise ValueError('Sweep may alter only recorded numeric inputs')
        if digest({'study': study, 'coordinates': coords}) != sweep['options_digest']:
            raise ValueError('Sweep point option digest mismatch')
    parents = snap.get('parents', [])
    if not isinstance(parents, list) or len(parents) > 32:
        raise ValueError('Invalid parent chain')
    for parent in parents:
        if (not isinstance(parent, dict) or parent.get('revision_id') != snap['revision_id'] or
                parent.get('project_digest') != snap['project_digest'] or
                not valid_sha(parent.get('manifest_sha256')) or
                parent.get('artifact_type') not in ARTIFACT_TYPES.get(parent.get('engine'), ()) or
                parent.get('scientific_status') not in ('review_required', 'reviewed') or
                not isinstance(parent.get('content_sha256'), list) or
                not parent['content_sha256'] or any(not valid_sha(h) for h in parent['content_sha256'])):
            raise ValueError('Unverified or stale upstream manifest reference')
    return model, study, parents


def run(snapshot_path, root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    snap = json.loads(Path(snapshot_path).read_text(encoding='utf8'))
    model, study, parents = _validated_snapshot(snap)
    engine = study['engine']
    adapter_sha = adapter_digest(engine)
    if snap.get('expected_adapter_sha256') and snap['expected_adapter_sha256'] != adapter_sha:
        raise ArtifactInvalid('Native adapter source changed since job submission')
    result = REGISTRY[engine](study, model, root)
    if not isinstance(result, dict) or not isinstance(result.get('engine_version'), str) or not result['engine_version'] or result['engine_version'] == 'unavailable':
        raise ArtifactInvalid('Native engine did not report a verifiable version')
    if snap.get('expected_engine_version') and result['engine_version'] != snap['expected_engine_version']:
        raise ArtifactInvalid('Native engine version changed after job submission')
    kind = result.get('artifact_type', RESULT_TYPES.get(engine))
    if kind not in ARTIFACT_TYPES[engine]:
        raise ArtifactInvalid('Native adapter returned an unrecognized output type')
    names = result.get('native_files')
    if not isinstance(names, list) or not 1 <= len(names) <= 128 or len(set(names)) != len(names):
        raise ArtifactInvalid('Native adapter did not declare bounded output files')
    artifacts = []
    for name in names:
        file = safe_file(root, name)
        if file.stat().st_size > MAX_NATIVE_BYTES:
            raise ArtifactInvalid('Native file exceeds laptop limit')
        artifacts.append({'name': name, 'sha256': sha_bytes(file.read_bytes()), 'bytes': file.stat().st_size})
    # Files omitted by a native adapter may not quietly enter the artifact ZIP.
    declared = {str(safe_file(root, name).relative_to(root)) for name in names}
    other = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if other != declared:
        raise ArtifactInvalid('Native adapter emitted undeclared files')
    cache_key = fingerprint(revision_id=snap['revision_id'], project_digest=snap['project_digest'],
                            study=study, native_version=result['engine_version'],
                            adapter_sha256=adapter_sha,
                            parent_sha256=tuple(p['manifest_sha256'] for p in parents))
    manifest = {'schema': 'sqe.artifact.v1', 'engine': engine,
                'engine_version': result['engine_version'], 'adapter_sha256': adapter_sha,
                'kind': result['kind'], 'artifact_type': kind,
                'scientific_status': 'review_required', 'fabrication_status': 'HOLD',
                'revision_id': snap['revision_id'], 'project_digest': snap['project_digest'],
                'study_id': study['id'], 'cache_fingerprint': cache_key,
                'parents': parents, 'artifacts': artifacts,
                'provenance': {'used_revision': snap['revision_id'],
                               'used_project_sha256': snap['project_digest'],
                               'was_generated_by': engine, 'native_version': result['engine_version'],
                               'adapter_sha256': adapter_sha},
                'limitations': ['No independent native solver benchmark validation',
                                'No approved PDK / DRC / LVS / foundry signoff']}
    if 'sweep_point' in snap:
        manifest['sweep_point'] = snap['sweep_point']
    write(root / 'RESULT_MANIFEST.json', manifest)
    return 0


def main():
    if len(sys.argv) != 3:
        print('Expected snapshot and native output directory', file=sys.stderr)
        return 2
    snapshot, folder = sys.argv[1:3]
    try:
        return run(snapshot, folder)
    except Exception as exc:
        Path(folder).mkdir(parents=True, exist_ok=True)
        write(Path(folder) / 'FAILURE.json', {'status': 'failed',
                                            'error': type(exc).__name__ + ': ' + str(exc)[:600]})
        print(type(exc).__name__ + ': ' + str(exc)[:600], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
