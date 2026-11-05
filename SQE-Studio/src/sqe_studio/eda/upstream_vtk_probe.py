#!/usr/bin/env python3
"""M16 EXPERIMENTAL: SHA-bound, bounded upstream VTK/PyVista diagnostics.

Opt-in diagnostic of normal saved Palace runs and native Automatic Test.
No field values, mesh coordinates, physical identification or convergence
claims are emitted. Experimental UI integration is owner-authorized for testing,
NOT independently reviewed or approved for scientific release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

LEGACY_SCHEMA = 'sqe.m16.upstream-vtk-declarations.experimental.v1'
SCHEMA = 'sqe.upstream-vtk-cycles.experimental.v2'
SHA_PATTERN = re.compile(r'^[a-f0-9]{64}$')
PVD_PATTERN = re.compile(r'^sqe_em/outputFiles/paraview/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.pvd$')
CYCLE_PATTERN = re.compile(r'^Cycle[0-9]{6}/data\.pvtu$')
PIECE_PATTERN = re.compile(r'^proc[0-9]{6}\.vtu$')
FIELDS = ('E_real', 'E_imag', 'E', 'B_real', 'B_imag')
AUXILIARY = ('Rank', 'Indicator')
ROLES = ('COMPLEX_E_FIELD', 'AUXILIARY_MESH_DATA',
         'INCOMPLETE_OR_UNSUPPORTED_FIELD', 'UNCLASSIFIED')
MAX_MANIFEST_BYTES = 256 * 1024
MAX_DESC_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 128
MAX_CYCLES = 12
MAX_PIECES = 16
MAX_REFERENCED_BYTES = 256 * 1024 * 1024
MAX_SINGLE_BYTES = 64 * 1024 * 1024


class ProbeBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _safe_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or len(name) > 256 or '\\' in name or '\x00' in name:
        raise ProbeBlocked('UNSAFE_ARTIFACT_PATH')
    posix = PurePosixPath(name)
    if (posix.is_absolute() or '..' in posix.parts or '.' in posix.parts or
            not posix.parts or ':' in name):
        raise ProbeBlocked('UNSAFE_ARTIFACT_PATH')
    path = root.joinpath(*posix.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ProbeBlocked('UNSAFE_ARTIFACT_PATH')
    for child in (path, *path.parents):
        if child == root.parent:
            break
        if child.is_symlink():
            raise ProbeBlocked('UNSAFE_ARTIFACT_PATH')
    if not path.is_file():
        raise ProbeBlocked('MISSING_SIGNED_ARTIFACT')
    return path


def _signed_inventory(root: Path, manifest: Path) -> dict:
    if not manifest.is_file() or manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise ProbeBlocked('INVALID_MANIFEST')
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError):
        raise ProbeBlocked('INVALID_MANIFEST') from None
    records = data.get('artifacts') if type(data) is dict else None
    if type(records) is not list or len(records) > MAX_MEMBERS:
        raise ProbeBlocked('INVALID_MANIFEST')
    found = {}
    folded = set()
    for item in records:
        if type(item) is not dict:
            raise ProbeBlocked('INVALID_MANIFEST')
        name = item.get('name')
        digest = item.get('sha256')
        size = item.get('bytes')
        if (type(name) is not str or not SHA_PATTERN.fullmatch(str(digest)) or
                type(size) is not int or size <= 0 or size > MAX_SINGLE_BYTES):
            # Other signed artifacts can be large: the native reader probe only
            # needs field descriptors and pieces, not the mesh/deck/log files.
            if (type(name) is str and not name.endswith(('.pvd','.pvtu','.vtu'))
                    and type(size) is int and size >= 0 and SHA_PATTERN.fullmatch(str(digest))):
                continue
            raise ProbeBlocked('INVALID_MANIFEST')
        if name.lower() in folded:
            raise ProbeBlocked('DUPLICATE_ARTIFACT')
        folded.add(name.lower())
        if name.endswith(('.pvd','.pvtu','.vtu')):
            path = _safe_file(root, name)
            if path.stat().st_size != size or _hash(path) != digest:
                raise ProbeBlocked('ARTIFACT_HASH_MISMATCH')
            found[name] = (path, digest, size)
    return found


def _read_descriptor(path: Path, expected: str) -> ET.Element:
    if path.stat().st_size > MAX_DESC_BYTES:
        raise ProbeBlocked('DESCRIPTOR_TOO_LARGE')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ProbeBlocked('UNSAFE_XML_DESCRIPTOR')
    try:
        doc = ET.fromstring(raw)
    except ET.ParseError:
        raise ProbeBlocked('INVALID_XML_DESCRIPTOR') from None
    if doc.tag != 'VTKFile' or doc.get('type') != expected:
        raise ProbeBlocked('INVALID_VTK_DESCRIPTOR_TYPE')
    return doc


def _references(root: Path, signed: dict, pvd_name: str) -> list[dict]:
    if pvd_name not in signed or not PVD_PATTERN.fullmatch(pvd_name):
        raise ProbeBlocked('UNSIGNED_PVD')
    doc = _read_descriptor(signed[pvd_name][0], 'Collection')
    entries = doc.findall('./Collection/DataSet')
    if not 1 <= len(entries) <= MAX_CYCLES:
        raise ProbeBlocked('INVALID_PVD_CYCLE_COUNT')
    seen = set()
    result = []
    for index, item in enumerate(entries):
        rel = item.get('file')
        if type(rel) is not str or not CYCLE_PATTERN.fullmatch(rel) or rel in seen:
            raise ProbeBlocked('UNSAFE_PVD_REFERENCE')
        seen.add(rel)
        pvtu_name = str(PurePosixPath(pvd_name).parent / rel)
        if pvtu_name not in signed:
            raise ProbeBlocked('UNSIGNED_PVTU')
        pvtu = _read_descriptor(signed[pvtu_name][0], 'PUnstructuredGrid')
        pieces = pvtu.findall('./PUnstructuredGrid/Piece')
        if not 1 <= len(pieces) <= MAX_PIECES:
            raise ProbeBlocked('INVALID_MPI_PIECE_COUNT')
        names = set()
        for p in pieces:
            source = p.get('Source')
            if type(source) is not str or not PIECE_PATTERN.fullmatch(source) or source in names:
                raise ProbeBlocked('UNSAFE_PIECE_REFERENCE')
            names.add(source)
            piece_name = str(PurePosixPath(pvtu_name).parent / source)
            if piece_name not in signed:
                raise ProbeBlocked('UNSIGNED_VTU_PIECE')
        result.append({'index': index, 'pvtu': pvtu_name, 'piece_count': len(pieces),
                       'pieces': [str(PurePosixPath(pvtu_name).parent / n) for n in sorted(names)]})
    total = sum(v[2] for v in signed.values())
    if total > MAX_REFERENCED_BYTES:
        raise ProbeBlocked('FIELD_READ_BUDGET')
    return result


def _status_for_arrays(arrays: dict) -> dict:
    # Input is names -> (dtype kind, component_count); return no values/names
    # beyond the fixed, documented Palace field vocabulary.
    return {name: ('ABSENT' if name not in arrays else
                   'FLOAT_VECTOR_3' if name in FIELDS and arrays[name] == ('f', 3) else
                   'NUMERIC_SCALAR' if name in AUXILIARY and
                       arrays[name][0] in ('f', 'i', 'u') and arrays[name][1] == 1 else
                   'WRONG_TYPE_OR_COMPONENTS') for name in (*FIELDS, *AUXILIARY)}


def classify_cycle(blocks: list[dict]) -> str:
    """Classify upstream declarations, never a physical mode or field payload.

    No cycle ordinal, frequency, geometry or expected array value is involved.
    Auxiliary markers cannot hide incomplete or malformed field declarations.
    """
    if not blocks:
        return 'UNCLASSIFIED'
    associations = [block[assoc] for block in blocks for assoc in ('point', 'cell')]
    has_fields = any(a[name] != 'ABSENT' for a in associations for name in FIELDS)
    if has_fields:
        if any(a[name] == 'WRONG_TYPE_OR_COMPONENTS' for a in associations for name in FIELDS):
            return 'INCOMPLETE_OR_UNSUPPORTED_FIELD'
        for a in associations:
            for pair in (('E_real', 'E_imag'), ('B_real', 'B_imag')):
                if (a[pair[0]] == 'ABSENT') != (a[pair[1]] == 'ABSENT'):
                    return 'INCOMPLETE_OR_UNSUPPORTED_FIELD'
        complete = any(all(all(block[assoc][key] == 'FLOAT_VECTOR_3'
                              for key in ('E_real', 'E_imag')) for block in blocks)
                       for assoc in ('point', 'cell'))
        return 'COMPLEX_E_FIELD' if complete else 'INCOMPLETE_OR_UNSUPPORTED_FIELD'
    auxiliary = all(any(block[assoc][name] == 'NUMERIC_SCALAR'
                        for assoc in ('point', 'cell') for name in AUXILIARY)
                    for block in blocks)
    malformed = any(a[name] == 'WRONG_TYPE_OR_COMPONENTS'
                    for a in associations for name in AUXILIARY)
    return 'AUXILIARY_MESH_DATA' if auxiliary and not malformed else 'UNCLASSIFIED'


def diagnostic_summary(record: dict) -> dict:
    """Validate the v2 public DTO and return only bounded report metadata."""
    if (type(record) is not dict or record.get('schema') != SCHEMA or
            record.get('physical_mode_identity') != 'NOT_ESTABLISHED' or
            record.get('mesh_convergence') != 'NOT_ESTABLISHED' or
            record.get('field_values_in_report') is not False):
        raise ValueError('Invalid upstream diagnostic science boundary')
    common = {'schema', 'status', 'physical_mode_identity', 'mesh_convergence',
              'field_values_in_report'}
    if record.get('status') == 'BLOCKED':
        code = record.get('reason_code')
        if (set(record) != common | {'reason_code'} or type(code) is not str or
                not re.fullmatch(r'[A-Z][A-Z0-9_]{2,63}', code)):
            raise ValueError('Invalid upstream diagnostic blocker')
        return {'status': 'BLOCKED', 'reason_code': code}
    expected = common | {'backend', 'backend_version', 'pvd_cycle_count', 'cycles',
                         'cycle_role_counts', 'note'}
    cycles = record.get('cycles')
    version = record.get('backend_version')
    if (set(record) != expected or record.get('backend') not in ('VTK', 'PyVista') or
            type(version) is not str or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,32}', version) or
            type(cycles) is not list or not 1 <= len(cycles) <= MAX_CYCLES or
            type(record.get('pvd_cycle_count')) is not int or record['pvd_cycle_count'] != len(cycles) or
            record.get('note') != 'Upstream declarations only; no field payload, mode identity, convergence or EPR validation.'):
        raise ValueError('Invalid upstream diagnostic dimensions')
    roles = []; flags = []
    for index, cycle in enumerate(cycles):
        if (type(cycle) is not dict or set(cycle) != {'cycle_index_not_mode_identity',
                'mpi_piece_count', 'blocks', 'complex_e_declared', 'role'} or
                type(cycle.get('cycle_index_not_mode_identity')) is not int or
                cycle['cycle_index_not_mode_identity'] != index or
                type(cycle.get('mpi_piece_count')) is not int or
                not 1 <= cycle['mpi_piece_count'] <= MAX_PIECES or
                type(cycle.get('blocks')) is not list or not 1 <= len(cycle['blocks']) <= 64 or
                type(cycle.get('complex_e_declared')) is not bool):
            raise ValueError('Invalid upstream cycle declaration')
        for block in cycle['blocks']:
            if type(block) is not dict or set(block) != {'point', 'cell'}:
                raise ValueError('Invalid upstream array association')
            for association in block.values():
                if type(association) is not dict or set(association) != set((*FIELDS, *AUXILIARY)):
                    raise ValueError('Invalid upstream array vocabulary')
                for name, state in association.items():
                    allowed = {'ABSENT', 'WRONG_TYPE_OR_COMPONENTS',
                               'FLOAT_VECTOR_3' if name in FIELDS else 'NUMERIC_SCALAR'}
                    if type(state) is not str or state not in allowed:
                        raise ValueError('Invalid upstream array type')
        role = classify_cycle(cycle['blocks'])
        flag = role == 'COMPLEX_E_FIELD'
        if cycle.get('role') != role or cycle['complex_e_declared'] != flag:
            raise ValueError('Upstream role does not match declarations')
        roles.append(role); flags.append(flag)
    counts = {role: roles.count(role) for role in ROLES}
    status = ('UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED' if counts['COMPLEX_E_FIELD'] and
              not counts['UNCLASSIFIED'] and not counts['INCOMPLETE_OR_UNSUPPORTED_FIELD']
              else 'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED')
    if (type(record.get('cycle_role_counts')) is not dict or
            any(type(v) is not int for v in record['cycle_role_counts'].values()) or
            record['cycle_role_counts'] != counts or record.get('status') != status):
        raise ValueError('Upstream aggregate does not match cycle evidence')
    return {'status': status, 'backend': record['backend'], 'backend_version': version,
            'pvd_cycle_count': len(cycles), 'complex_E_declared_by_cycle': flags,
            'cycle_roles': roles, 'cycle_role_counts': counts, 'schema': SCHEMA}


def _pyvista_probe(pvd_path: Path, num_cycles: int) -> tuple[str, list[dict]]:
    import pyvista as pv
    reader = pv.get_reader(str(pvd_path))
    if len(getattr(reader, 'time_values', [])) != num_cycles:
        # Multiple entries can share a time step. Never infer output cycle
        # or physical mode identity from a collapsed PyVista time index.
        raise ProbeBlocked('PVD_TIME_CYCLE_AMBIGUITY')
    if not hasattr(reader, 'set_active_time_point'):
        raise ProbeBlocked('PVD_READER_UNSUPPORTED')
    result = []
    for index in range(num_cycles):
        reader.set_active_time_point(index)
        data = reader.read()
        leaves = []
        def collect(obj):
            if isinstance(obj, pv.MultiBlock):
                for sub in obj:
                    if sub is not None:
                        collect(sub)
                return
            def convert(association):
                return {key: (getattr(association[key].dtype, 'kind', ''),
                              association[key].shape[-1] if len(association[key].shape) == 2 else 1)
                        for key in (*FIELDS, *AUXILIARY) if key in association}
            leaves.append({'point': _status_for_arrays(convert(obj.point_data)),
                           'cell': _status_for_arrays(convert(obj.cell_data))})
        collect(data)
        if not leaves or len(leaves) > MAX_PIECES * 4:
            raise ProbeBlocked('UNSUPPORTED_UPSTREAM_DATASET')
        result.append({'index': index, 'blocks': leaves})
    return 'PyVista', result


def _vtk_probe(root: Path, cycles: list[dict]) -> tuple[str, list[dict]]:
    # Equivalent general upstream VTK readers for cases where PyVista is absent;
    # no implementation of raw-appended VTK decoding is introduced by SQE.
    import vtk
    result = []
    for cycle in cycles:
        reader = vtk.vtkXMLPUnstructuredGridReader()
        reader.SetFileName(str(root / cycle['pvtu']))
        reader.Update()
        if reader.GetErrorCode() != 0:
            raise ProbeBlocked('VTK_UPSTREAM_READER_ERROR')
        grid = reader.GetOutput()
        if grid is None:
            raise ProbeBlocked('VTK_UPSTREAM_READER_ERROR')
        def convert(data):
            out = {}
            if data is not None:
                for name in (*FIELDS, *AUXILIARY):
                    a = data.GetArray(name)
                    if a is not None:
                        out[name] = ('f' if a.GetDataType() in (vtk.VTK_FLOAT, vtk.VTK_DOUBLE) else 'i',
                                     a.GetNumberOfComponents())
            return out
        result.append({'index': cycle['index'], 'blocks': [
            {'point': _status_for_arrays(convert(grid.GetPointData())),
             'cell': _status_for_arrays(convert(grid.GetCellData()))}]})
    return 'VTK', result


def _diagnostic(cycles: list[dict], backend: str, details: list[dict]) -> dict:
    if not cycles or len(cycles) != len(details):
        raise ProbeBlocked('UPSTREAM_CYCLE_COUNT_MISMATCH')
    checks = []
    for cycle, info in zip(cycles, details):
        if info.get('index') != cycle['index']:
            raise ProbeBlocked('UPSTREAM_CYCLE_ORDER_MISMATCH')
        role = classify_cycle(info['blocks'])
        checks.append({'cycle_index_not_mode_identity': cycle['index'],
                       'mpi_piece_count': cycle['piece_count'],
                       'blocks': info['blocks'],
                       'complex_e_declared': role == 'COMPLEX_E_FIELD', 'role': role})
    counts = {role: sum(c['role'] == role for c in checks) for role in ROLES}
    observed = (counts['COMPLEX_E_FIELD'] > 0 and not counts['UNCLASSIFIED'] and
                not counts['INCOMPLETE_OR_UNSUPPORTED_FIELD'])
    try:
        from importlib.metadata import version
        backend_version = version('pyvista' if backend == 'PyVista' else 'vtk')
    except Exception:
        backend_version = 'UNKNOWN'
    result = {'schema': SCHEMA, 'backend_version': backend_version,
            'status': ('UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED' if observed
                       else 'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED'),
            'backend': backend, 'pvd_cycle_count': len(checks),
            'cycles': checks, 'cycle_role_counts': counts,
            'physical_mode_identity': 'NOT_ESTABLISHED',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'field_values_in_report': False,
            'note': 'Upstream declarations only; no field payload, mode identity, convergence or EPR validation.'}
    diagnostic_summary(result)
    return result


def _child_run(root: Path, manifest: Path, pvd: str, backend: str) -> dict:
    signed = _signed_inventory(root, manifest)
    cycles = _references(root, signed, pvd)
    try:
        if backend == 'pyvista':
            source, details = _pyvista_probe(signed[pvd][0], len(cycles))
        elif backend == 'vtk':
            source, details = _vtk_probe(root, cycles)
        else:
            try:
                source, details = _pyvista_probe(signed[pvd][0], len(cycles))
            except ImportError:
                source, details = _vtk_probe(root, cycles)
    except ImportError:
        raise ProbeBlocked('UPSTREAM_READER_NOT_INSTALLED') from None
    except ProbeBlocked:
        raise
    except Exception:
        # Do not expose VTK exception text, file names or private geometry.
        raise ProbeBlocked('UPSTREAM_READER_FAILED') from None
    # Recheck every signed native field artifact after reader work.
    for path, digest, size in signed.values():
        checked = _safe_file(root, path.relative_to(root).as_posix())
        if checked.stat().st_size != size or _hash(checked) != digest:
            raise ProbeBlocked('ARTIFACT_CHANGED_DURING_PROBE')
    return _diagnostic(cycles, source, details)


def _public_result(code: str) -> dict:
    return {'schema': SCHEMA, 'status': 'BLOCKED', 'reason_code': code,
            'physical_mode_identity': 'NOT_ESTABLISHED',
            'mesh_convergence': 'NOT_ESTABLISHED',
            'field_values_in_report': False}



def probe_verified_run(workspace: Path, manifest: dict, *, timeout: int = 25) -> dict:
    """Run upstream reader in a bounded independent process on SHA-verified output.

    The caller MUST check the ordinary completed RESULT_MANIFEST before this
    routine. We verify the declared native file hashes again in the child.
    Only fixed categorical metadata is returned, never private paths or arrays.
    No frontend-provided path, backend choice or timeout is accepted.
    """
    if type(manifest) is not dict or manifest.get('artifact_type') != 'palace.eigenmodes' or manifest.get('engine') != 'sqdmetal_palace':
        return _public_result('NOT_APPLICABLE')
    workspace = Path(workspace).resolve()
    filename = workspace/'RESULT_MANIFEST.json'
    if not filename.is_file() or filename.is_symlink():
        return _public_result('MISSING_NATIVE_MANIFEST')
    # Exact manifest identity, not merely a name match.
    try:
        disk = json.loads(filename.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError):
        return _public_result('INVALID_MANIFEST')
    if disk != manifest:
        return _public_result('MANIFEST_IDENTITY_MISMATCH')
    names = [a.get('name') for a in manifest.get('artifacts', ()) if type(a) is dict]
    pvds = [n for n in names if type(n) is str and PVD_PATTERN.fullmatch(n)
            and n.endswith('/eigenmode/eigenmode.pvd')]
    if len(pvds) != 1:
        return _public_result('EIGENMODE_PVD_NOT_UNAMBIGUOUS')
    cmd = [sys.executable, '-m', 'sqe_studio.eda.upstream_vtk_probe',
           '--child', '--workspace', str(workspace), '--manifest', str(filename),
           '--pvd', pvds[0], '--backend', 'auto', '--out', 'unused']
    env = dict(os.environ)
    env.update({'PYVISTA_OFF_SCREEN': 'true',
                'VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN': '1',
                'PYTHONDONTWRITEBYTECODE': '1'})
    # On POSIX, place a hard virtual-memory/CPU cap on the untrusted native
    # reader. Windows has no equivalent via stdlib: bounded bytes + timeout
    # remain essential; exceeding the stated budget returns BLOCKED.
    preexec = None
    if os.name == 'posix':
        def _limits():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (min(timeout+3, 35), min(timeout+5, 40)))
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        preexec = _limits
    try:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=timeout, env=env, check=False,
                                   text=True, preexec_fn=preexec)
        if len(completed.stdout) > 128 * 1024:
            return _public_result('OUTPUT_BUDGET')
        record = json.loads(completed.stdout)
        diagnostic_summary(record)
        return record
    except subprocess.TimeoutExpired:
        return _public_result('UPSTREAM_READER_TIMEOUT')
    except (OSError, ValueError, TypeError):
        return _public_result('UPSTREAM_WORKER_ERROR')

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Actual native worker workspace, never a report ZIP')
    parser.add_argument('--manifest', type=Path, required=True,
                        help='Actual SHA-256 native manifest JSON (local only)')
    parser.add_argument('--pvd', required=True, help='Signed workspace-relative PVD artifact')
    parser.add_argument('--backend', choices=['auto','pyvista','vtk'], default='auto')
    parser.add_argument('--out', type=Path, required=True, help='Write bounded JSON outside workspace')
    parser.add_argument('--timeout', type=int, default=35)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        try:
            result = _child_run(args.workspace.resolve(), args.manifest, args.pvd, args.backend)
        except ProbeBlocked as exc:
            result = _public_result(exc.code)
        except Exception:
            result = _public_result('PROBE_UNEXPECTED_ERROR')
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0 if result['status'] != 'BLOCKED' else 2
    if not 1 <= args.timeout <= 90:
        parser.error('--timeout must be in [1,90]')
    cmd = [sys.executable, str(Path(__file__).resolve()), '--child', '--workspace',
           str(args.workspace), '--manifest', str(args.manifest), '--pvd',
           args.pvd, '--backend', args.backend, '--out', str(args.out)]
    env = dict(os.environ)
    env['PYVISTA_OFF_SCREEN'] = 'true'
    env['VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN'] = '1'
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=args.timeout, check=False, env=env, text=True)
        result = json.loads(proc.stdout) if len(proc.stdout) <= 128 * 1024 else _public_result('OUTPUT_BUDGET')
        if type(result) is not dict or result.get('schema') != SCHEMA:
            result = _public_result('INVALID_CHILD_RESPONSE')
    except subprocess.TimeoutExpired:
        result = _public_result('UPSTREAM_READER_TIMEOUT')
    except (ValueError, OSError):
        result = _public_result('UPSTREAM_WORKER_ERROR')
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(args.workspace.resolve()) or out.parent.is_symlink():
        parser.error('Output must be new and outside the native workspace')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('status=' + result['status'] + '; output=' + str(out))
    return 0 if result['status'] != 'BLOCKED' else 2


if __name__ == '__main__':
    sys.exit(main())
