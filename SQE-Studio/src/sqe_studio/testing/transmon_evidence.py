"""Package only the test-owned reference inputs, verified outputs and UI proof."""
from hashlib import sha256
from importlib import metadata, util
import json
from pathlib import Path
import zipfile

from ..orchestration.artifacts import safe_file, verify_manifest


def runtime_sources():
    records = {}
    for package in ('SQDMetal', 'quantum-metal', 'gmsh', 'scqubits', 'shapely'):
        try:
            records[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            records[package] = None
    spec = util.find_spec('SQDMetal')
    if spec is not None and spec.origin:
        base = Path(spec.origin).parent
        records['sqdmetal_source_sha256'] = {
            name: sha256((base / name).read_bytes()).hexdigest() for name in (
                'PALACE/Capacitance_Simulation.py',
                'PALACE/Utilities/GMSH_Geometry_Builder.py',
                'Utilities/GeometryProcessors/GeomQiskitMetal.py')}
    return records


def package_evidence(session, folder, runs, result):
    folder = Path(folder)
    target = folder / 'native-evidence.zip'
    if target.exists() or target.is_symlink():
        raise FileExistsError('Native reference evidence already exists')
    sources = runtime_sources()
    total = 0
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for run_id in sorted(set(runs)):
            run = session.server.app.store.run(session.owner, session.pid, run_id)
            if run['state'] != 'completed':
                raise ValueError('ONLY_COMPLETED_NATIVE_REFERENCE_RUNS_CAN_BE_PACKAGED')
            project = session.server.app.store.project(session.owner, session.pid, run['revision_id'])
            output = Path(run['path']) / 'output'
            ref = verify_manifest(output, revision_id=run['revision_id'],
                project_digest=project['revision_digest'], study_id=run['study_id'], engine=run['engine'])
            manifest_file = safe_file(output, 'RESULT_MANIFEST.json')
            manifest = json.loads(manifest_file.read_bytes())
            if sha256(manifest_file.read_bytes()).hexdigest() != ref.manifest_sha256:
                raise ValueError('NATIVE_REFERENCE_MANIFEST_CHANGED_DURING_EXPORT')
            prefix = 'runs/' + run_id + '/'
            archive.writestr(prefix + 'project.json', json.dumps({
                key: project[key] for key in ('revision', 'revision_digest', 'model')}, indent=2))
            for name in ['RESULT_MANIFEST.json', *(item['name'] for item in manifest['artifacts'])]:
                path = safe_file(output, name)
                total += path.stat().st_size
                if total > 100_000_000:
                    raise ValueError('NATIVE_REFERENCE_ARCHIVE_INPUT_BUDGET')
                archive.write(path, prefix + 'output/' + name)
        for subfolder in ('reference', 'workflow'):
            base = folder / subfolder
            for path in sorted(base.rglob('*')):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
                    if total > 100_000_000:
                        raise ValueError('NATIVE_REFERENCE_ARCHIVE_INPUT_BUDGET')
                    archive.write(path, path.relative_to(folder).as_posix())
        archive.writestr('RUNTIME_SOURCES.json', json.dumps(sources, indent=2))
        archive.writestr('WORKFLOW_RESULT.json', json.dumps(result, indent=2))
    if target.stat().st_size > 40_000_000:
        raise ValueError('NATIVE_REFERENCE_ARCHIVE_COMPRESSED_BUDGET')
    return {'name': target.name, 'sha256': sha256(target.read_bytes()).hexdigest(),
            'bytes': target.stat().st_size, 'runtime_sources': sources,
            'scope': 'Fresh test-owned reference project only; no accounts, credentials or user projects'}
