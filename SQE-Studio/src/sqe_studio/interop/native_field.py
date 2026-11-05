"""Palace ParaView complex-field provenance and conservative overlap diagnostics.

This module NEVER infers a field from eigenfrequency, Q, energy or a mode ordinal.
Palace's eigenmode export PVD/PVTU/VTU contains E_real/E_imag (V/m),
and may contain B_real/B_imag (T). B is flux density, NOT H in A/m.
VTU may contain raw appended binary, not CSV or plain XML.
A verified artifact inventory does not imply comparable meshes or phases.

The optional VTK reader provides bounded local E/B digest and MPI seam
checks. Same-mesh linear tetra visualizations support an exact nodal-mass
diagnostic; a separate explicitly assumed common-frame, bounded two-mesh
barycentric quadrature diagnostic remains physically BLOCKED. High-order cells,
missing arrays and unsupported readers fail closed. Pointwise visualization
data are not the underlying H(curl) finite-element solution.
"""
from __future__ import annotations

import cmath
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET

SCHEMA = 'sqe.palace-complex-field-evidence.v1'
MAX_XML_BYTES = 2_000_000
# Native VTU metadata may precede multi-MB arrays. Unlike PVD/PVTU,
# VTU headers get a separate bounded streaming scan, never the field payload.
MAX_VTU_HEADER_BYTES = 16 * 1024 * 1024
MAX_FIELD_BYTES = 128 * 1024 * 1024
MAX_CELLS = 250_000
MAX_ASSEMBLED_POINTS = 1_000_000
MAX_MPI_TOTAL_FIELD_BYTES = 256 * 1024 * 1024
MAX_MESH_TAG_SCAN_BYTES = 64 * 1024 * 1024


class NativeFieldEvidenceError(ValueError):
    """A field-format, origin, geometry or physical-comparison gate is unmet."""


class NativeFieldVectorContractError(NativeFieldEvidenceError):
    """A VTK E-vector blocker with safe, fixed-vocabulary header evidence.

    Never include source array names beyond Palace's published E/B identifiers,
    user geometry, private paths, or raw field values in a portable report.
    """
    def __init__(self, reason: str, declaration_diagnostic: dict):
        super().__init__(reason)
        self.declaration_diagnostic = declaration_diagnostic


def _array_declaration_state(container: ET.Element | None, name: str, *, parallel=False) -> str:
    """Classify one *known* Palace field without copying arbitrary array names."""
    if container is None:
        return 'NO_ASSOCIATION'
    tag = 'PDataArray' if parallel else 'DataArray'
    declarations = [node for node in container.findall(tag) if node.get('Name') == name]
    if not declarations:
        return 'ABSENT'
    if len(declarations) > 1:
        return 'DUPLICATE'
    node = declarations[0]
    kind = node.get('type')
    if kind not in ('Float32', 'Float64'):
        return 'NON_FLOAT'
    components = node.get('NumberOfComponents', '1')
    if components != '3':
        return 'WRONG_COMPONENT_COUNT'
    return 'FLOAT_VECTOR_3'


def _bounded_e_declaration_diagnostic(piece: ET.Element, parallel: ET.Element | None = None) -> dict:
    """Pure structural evidence from signed VTK metadata, never payload data."""
    point = piece.find('PointData')
    cell = piece.find('CellData')
    par = parallel.find('./PUnstructuredGrid/PPointData') if parallel is not None else None
    fields = ('E_real', 'E_imag', 'E')
    result = {'schema': 'sqe.vtu-e-field-declaration.m15.v1',
              'point': {key: _array_declaration_state(point, key) for key in fields},
              'cell': {key: _array_declaration_state(cell, key) for key in fields},
              'parallel_point': {key: _array_declaration_state(par, key, parallel=True) for key in fields},
              'field_values_exported': False,
              'physical_mode_identity': 'UNRESOLVED'}
    return result


def _checked_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
        raise NativeFieldEvidenceError('Invalid native field artifact path')
    parts = PurePosixPath(relative)
    if (parts.is_absolute() or '..' in parts.parts or '.' in parts.parts
            or len(parts.parts) < 1 or ':' in parts.parts[0]):
        raise NativeFieldEvidenceError('Native field path escapes the worker output')
    if root.is_symlink() or not root.is_dir():
        raise NativeFieldEvidenceError('Native workspace root must be a real directory')
    path = root.joinpath(*parts.parts)
    if any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
        raise NativeFieldEvidenceError('Native field symlink is not authorized')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise NativeFieldEvidenceError('Native field artifact missing or outside workspace')
    if not 0 < path.stat().st_size <= MAX_FIELD_BYTES:
        raise NativeFieldEvidenceError('Native field artifact exceeds size budget')
    return path


def _sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def _native_inventory(root: Path, artifacts: list[dict]) -> dict[str, Path]:
    inventory = {}
    if type(artifacts) is not list or len(artifacts) > 128:
        raise NativeFieldEvidenceError('Invalid native manifest artifact inventory')
    for entry in artifacts:
        if type(entry) is not dict or not isinstance(entry.get('name'), str):
            raise NativeFieldEvidenceError('Invalid native field artifact declaration')
        name = entry['name']
        if name in inventory or not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('sha256', ''))):
            raise NativeFieldEvidenceError('Duplicate artifact or invalid SHA-256')
        path = _checked_path(root, name)
        if _sha(path) != entry['sha256'] or (entry.get('bytes') is not None and entry['bytes'] != path.stat().st_size):
            raise NativeFieldEvidenceError('Native field artifact digest/size differs from worker manifest')
        inventory[name] = path
    return inventory


def _xml_file(path: Path, kind: str) -> ET.Element:
    if path.stat().st_size > MAX_XML_BYTES:
        raise NativeFieldEvidenceError('Oversized Palace '+kind+' descriptor')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise NativeFieldEvidenceError('Unsupported XML entity declaration')
    try:
        doc = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise NativeFieldEvidenceError('Invalid Palace '+kind+' descriptor') from exc
    if doc.tag != 'VTKFile' or doc.get('type') != kind:
        raise NativeFieldEvidenceError('Unexpected native VTK collection type')
    return doc


def _vtu_header(path: Path, parallel_descriptor: ET.Element | None = None) -> dict:
    """Inspect signed Palace VTU metadata without reading full field payloads.

    Palace emits raw-appended VTK XML. The old 2 MB fixed prefix could
    classify otherwise intact exports as VTU_HEADER_BUDGET. Scan in bounded
    chunks for the raw-appended delimiter, retaining no raw binary payload;
    the PVD/PVTU XML descriptor limit remains unchanged. No field decoding,
    mode pairing or physical validation is performed here.
    """
    size = path.stat().st_size
    limit = min(size, MAX_VTU_HEADER_BYTES)
    prefix = bytearray()
    marker = None
    # Limit both bytes retained and read operations. Headers over this bound
    # remain blocked; never relax the overall signed-artifact size budget.
    with path.open('rb') as stream:
        while len(prefix) < limit:
            block = stream.read(min(512 * 1024, limit - len(prefix)))
            if not block:
                break
            prefix.extend(block)
            # The '<AppendedData ...>_' delimiter can cross a chunk boundary.
            marker = re.search(rb'<AppendedData\b[^>]*>\s*_', prefix)
            if marker is not None:
                break
    if marker is not None:
        # Binary following '_' is not XML and can contain arbitrary '<'.
        # Only confirm the bounded end tags; NEVER parse appended field bytes.
        with path.open('rb') as stream:
            stream.seek(max(0, size - 4096))
            trailer = stream.read()
        if not re.search(rb'</AppendedData>\s*</VTKFile>\s*$', trailer):
            raise NativeFieldEvidenceError('Truncated raw-appended native VTU payload')
        head = bytes(prefix[:marker.start()]) + b'</VTKFile>'
    elif len(prefix) < size:
        raise NativeFieldEvidenceError('VTU has no bounded XML/AppendedData header')
    else:
        # Small complete XML VTU fixtures were supported previously.
        # Never treat this as native complex-payload validation.
        head = bytes(prefix)
    if b'<!DOCTYPE' in head.upper() or b'<!ENTITY' in head.upper():
        raise NativeFieldEvidenceError('Unsupported VTU XML entity')
    try:
        doc = ET.fromstring(head)
    except ET.ParseError as exc:
        raise NativeFieldEvidenceError('Invalid Palace VTU metadata') from exc
    if doc.tag != 'VTKFile' or doc.get('type') != 'UnstructuredGrid':
        raise NativeFieldEvidenceError('Unsupported native VTU file kind')
    piece = doc.find('./UnstructuredGrid/Piece')
    if piece is None:
        raise NativeFieldEvidenceError('Native VTU has no unstructured grid piece')
    point_data = piece.find('PointData')
    declaration = _bounded_e_declaration_diagnostic(piece, parallel_descriptor)
    if point_data is None:
        raise NativeFieldVectorContractError('Native VTU lacks point-sampled fields', declaration)
    attributes = {a.get('Name'): a for a in point_data.findall('DataArray')}
    for name in ('E_real', 'E_imag'):
        arr = attributes.get(name)
        if arr is None or arr.get('NumberOfComponents') != '3' or arr.get('type') not in ('Float32', 'Float64'):
            raise NativeFieldVectorContractError('Native VTU lacks complex E vector components', declaration)
    # Palace exports B (T), not H; no permeability model is presumed.
    b_present = [key in attributes for key in ('B_real', 'B_imag')]
    if b_present[0] != b_present[1]:
        raise NativeFieldEvidenceError('Incomplete native complex B components')
    if b_present[0]:
        for name in ('B_real', 'B_imag'):
            arr = attributes[name]
            if arr.get('NumberOfComponents') != '3' or arr.get('type') not in ('Float32', 'Float64'):
                raise NativeFieldEvidenceError('Invalid native complex B vector components')
    return {'B_complex_declared': b_present[0],
            'point_count_declared': piece.get('NumberOfPoints'),
            'cell_count_declared': piece.get('NumberOfCells'),
            'representation': 'VTK PointData 3-vector real/imag floats'}


def inspect_palace_field_export(root: Path, config: dict, artifacts: list[dict]) -> dict:
    """SHA-check actual Palace field exports and map all PVD->PVTU->VTU edges.

    No fake export is constructed if Save=0 or files are absent. This evidence
    is strictly a *format/lineage* statement, not a field overlap or a mode ID.
    """
    root = Path(root)
    problem = config.get('Problem', {})
    model = config.get('Model', {})
    eigen = config.get('Solver', {}).get('Eigenmode', {})
    length = model.get('L0')
    if (problem.get('Type') != 'Eigenmode' or type(length) not in (int, float)
            or not math.isfinite(length) or length <= 0 or model.get('Mesh') != 'sqe_em.msh'):
        raise NativeFieldEvidenceError('Unverified Palace eigenmode/model coordinate contract')
    requested = eigen.get('Save', 0)
    if type(requested) is not int or requested < 0 or requested > 12:
        raise NativeFieldEvidenceError('Unverified Palace eigenmode field-save count')
    record = {'schema': SCHEMA, 'status': 'BLOCKED_NO_NATIVE_COMPLEX_FIELD_EXPORT',
              'mode_identity': 'UNRESOLVED', 'complex_overlap': 'NOT_COMPUTED',
              'field_kind': 'E_real/E_imag', 'field_unit': 'V/m',
              'magnetic_field_kind': 'B_real/B_imag (T), if present; NOT H',
              'H_field_status': 'BLOCKED_REQUIRES_REVIEWED_CONSTITUTIVE_MU',
              'coordinate_frame': 'Palace mesh coordinates; no geometric registration inferred',
              'mesh_coordinate_unit': 'native mesh units', 'metres_per_mesh_unit': float(length),
              'requested_native_modes': requested,
              'solver_mode_index_basis': '1-based Palace eig.csv m; not physical mode identity',
              'normalization': 'Palace native unit-norm eigenmodes; numerical norm/phase not independently checked',
              'phase_convention': 'Palace native mean phase positive real per solver documentation; not independently checked or cross-run aligned',
              'field_samples': [], 'limitations': ['ParaView field samples are not the native H(curl) basis',
                 'Unregistered meshes and unreviewed material weights cannot establish physical mode identity']}
    if not requested:
        return record
    inventory = _native_inventory(root, artifacts)
    decks = [name for name in inventory if name == 'sqe_em/sqe_em.json']
    meshes = [name for name in inventory if name == 'sqe_em/sqe_em.msh']
    spectra = [name for name in inventory if name == 'sqe_em/outputFiles/eig.csv']
    if len(decks) != 1 or len(meshes) != 1 or len(spectra) != 1:
        raise NativeFieldEvidenceError('Native field export missing SHA-bound Palace deck/mesh/eigenmode spectrum')
    try:
        if json.loads(inventory[decks[0]].read_text(encoding='utf-8')) != config:
            raise NativeFieldEvidenceError('Field export deck differs from SHA-bound native config')
    except (ValueError, UnicodeError) as exc:
        raise NativeFieldEvidenceError('Invalid SHA-bound Palace field-export deck') from exc
    if config.get('Problem', {}).get('OutputFormats', {}).get('Paraview') is False:
        raise NativeFieldEvidenceError('Palace configured without ParaView field output')
    if type(eigen.get('N')) is not int or not 1 <= requested <= eigen['N'] <= 12:
        raise NativeFieldEvidenceError('Saved field count exceeds native Palace solved modes')
    try:
        with inventory[spectra[0]].open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        if not 2 <= len(rows) <= 13 or len(rows) != eigen['N'] + 1:
            raise ValueError('Native eigenmode count disagrees with reviewed solver deck')
        if len(rows[0]) < 2 or rows[0][0].strip() != 'm' or 'ghz' not in rows[0][1].lower():
            raise ValueError('Unrecognized native Palace eigenfrequency units')
        for n, row in enumerate(rows[1:], 1):
            if len(row) != len(rows[0]) or float(row[0]) != n or not (math.isfinite(float(row[1])) and float(row[1]) > 0):
                raise ValueError('Invalid mode ordering/frequency')
        frequency_ghz = float(rows[1][1])
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise NativeFieldEvidenceError('Native Palace mode ordinal/frequency cannot be verified') from exc
    pvd_names = [n for n in inventory if re.fullmatch(r'sqe_em/outputFiles/paraview/[^/]+/[^/]+\.pvd', n)
                 and not n.endswith('_boundary.pvd')]
    if len(pvd_names) != 1:
        return {**record, 'reason': 'Palace ParaView eigenmode collection missing or ambiguous'}
    pvd = _xml_file(inventory[pvd_names[0]], 'Collection')
    data = pvd.findall('./Collection/DataSet')
    # Palace ParaView PVD DataSet entries are output *cycles*, not guaranteed
    # one-to-one eigenmodes.  In particular Eigenmode.Save=1 can emit several
    # Cycle00000x exports for the same saved solution (observed in a real
    # four-rank solver run).  Do not compare this count with Eigenmode.Save.
    # The cycle ordinal is never promoted to a physical mode identity.
    if not data or len(data) > 12:
        raise NativeFieldEvidenceError('Unbounded or missing Palace PVD output cycles')
    samples = []
    collection = PurePosixPath(pvd_names[0]).parent
    cycles_seen = set()
    for ordinal, dataset in enumerate(data, 1):
        rel = dataset.get('file')
        if not rel or not re.fullmatch(r'Cycle[0-9]{6}/data\.pvtu', rel):
            raise NativeFieldEvidenceError('Unsafe Palace PVD dataset reference')
        if rel in cycles_seen:
            raise NativeFieldEvidenceError('Duplicate Palace PVD output cycle')
        cycles_seen.add(rel)
        pvtu_name = str(collection / rel)
        if pvtu_name not in inventory:
            raise NativeFieldEvidenceError('PVD references an unverified PVTU file')
        pvtu = _xml_file(inventory[pvtu_name], 'PUnstructuredGrid')
        pieces = pvtu.findall('./PUnstructuredGrid/Piece')
        if not pieces or len(pieces) > 16:
            raise NativeFieldEvidenceError('Native field has no bounded MPI piece inventory')
        piece_names = []
        seen_piece_names = set()
        for piece in pieces:
            source = piece.get('Source')
            if not source or '/' in source.replace('\\', '/') or not source.endswith('.vtu'):
                raise NativeFieldEvidenceError('Unsafe Palace VTU MPI piece reference')
            vtu_name = str(PurePosixPath(pvtu_name).parent / source)
            if vtu_name not in inventory:
                raise NativeFieldEvidenceError('PVTU references an unverified VTU piece')
            if vtu_name in seen_piece_names:
                raise NativeFieldEvidenceError('Duplicate VTU reference in MPI piece collection')
            seen_piece_names.add(vtu_name)
            header = _vtu_header(inventory[vtu_name], parallel_descriptor=pvtu)
            piece_names.append({'name': vtu_name, 'sha256': _sha(inventory[vtu_name]), **header})
        samples.append({'saved_collection_ordinal_not_mode_identity': ordinal,
                        'native_output_cycle_not_mode_identity': rel.split('/')[0],
                        'pvtu': pvtu_name, 'vtk_pieces': piece_names})
    record['status'] = 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY'
    record['reason'] = ('SHA-bound Palace PVD/PVTU/VTU lineage and E/B vector declarations checked; '
                        'payloads/physical surface tags not verified by metadata inspection')
    record['mesh_sha256'] = _sha(inventory[meshes[0]])
    record['deck_sha256'] = _sha(inventory[decks[0]])
    record['native_eig_sha256'] = _sha(inventory[spectra[0]])
    record['pvd_cycles_not_physical_modes'] = [s['native_output_cycle_not_mode_identity'] for s in samples]
    record['pvd_cycle_count'] = len(samples)
    record['first_saved_native_mode_index'] = 1
    record['first_saved_mode_frequency_GHz'] = frequency_ghz
    record['first_saved_mode_lineage'] = 'Palace Eigenmode.Save first mode corresponds to native eig.csv m=1; not Maxwell mode identity'
    record['pvd_name'] = pvd_names[0]
    record['field_samples'] = samples
    b_presence = [p['B_complex_declared'] for sample in samples for p in sample['vtk_pieces']]
    record['B_field_status'] = ('DECLARED_COMPLEX_B_FLUX_DENSITY_FORMAT_ONLY' if all(b_presence)
                                else 'BLOCKED_MISSING_OR_MIXED_COMPLEX_B_COMPONENTS')
    record['mpi_piece_status'] = ('FORMAT_REFERENCES_VERIFIED_PAYLOAD_ASSEMBLY_NOT_CHECKED'
                                  if any(len(s['vtk_pieces']) > 1 for s in samples)
                                  else 'SINGLE_PIECE_FORMAT_REFERENCES_VERIFIED')
    # Source files may mutate after initial inventory hashing; recheck every
    # descriptor/data edge at the end of metadata inspection, not just at entry.
    declared_digests = {entry['name']: entry['sha256'] for entry in artifacts}
    for name in (decks + meshes + spectra + pvd_names +
                 [s['pvtu'] for s in samples] +
                 [p['name'] for sample in samples for p in sample['vtk_pieces']]):
        if _sha(inventory[name]) != declared_digests[name]:
            raise NativeFieldEvidenceError('Palace field lineage mutated during inspection')
    record['surface_tag_status'] = 'BLOCKED_NO_VERIFIED_VTK_TO_GMSH_SURFACE_REGISTRATION'
    return record

def _read_local_vtu(path: Path, declared: dict):
    """Read one SHA-bound linear-tetra VTK piece; never return unbounded raw export."""
    try:
        import numpy as np
        from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader
        from vtkmodules.util.numpy_support import vtk_to_numpy
    except ImportError as exc:
        raise NativeFieldEvidenceError('VTK/numpy unavailable for local field decode') from exc
    if _sha(path) != declared['sha256']:
        raise NativeFieldEvidenceError('Native VTU changed since inspection')
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    try:
        reader.Update()
    except Exception as exc:
        raise NativeFieldEvidenceError('Unable to decode native VTU field') from exc
    if reader.GetErrorCode():
        raise NativeFieldEvidenceError('VTK reader returned a native VTU parse error')
    mesh = reader.GetOutput()
    n, m = mesh.GetNumberOfPoints(), mesh.GetNumberOfCells()
    if not 0 < n <= MAX_ASSEMBLED_POINTS or not 0 < m <= MAX_CELLS:
        raise NativeFieldEvidenceError('Empty or oversized VTK geometry')
    for field, value in (('point_count_declared', n), ('cell_count_declared', m)):
        count = declared.get(field)
        if count is not None and (not count.isdecimal() or int(count) != value):
            raise NativeFieldEvidenceError('VTK decoded counts disagree with field header')
    points = mesh.GetPoints()
    if points is None or points.GetData() is None:
        raise NativeFieldEvidenceError('Native VTU lacks mesh coordinates')
    xyz = vtk_to_numpy(points.GetData())
    if xyz.shape != (n, 3) or not bool(np.isfinite(xyz).all()):
        raise NativeFieldEvidenceError('Nonfinite or malformed native mesh coordinates')
    topology = hashlib.sha256()
    topology.update(np.ascontiguousarray(xyz, dtype='<f8').tobytes())
    for index in range(m):
        cell = mesh.GetCell(index)
        if cell is None or cell.GetCellType() != 10 or cell.GetNumberOfPoints() != 4:
            raise NativeFieldEvidenceError('Only first-order tetra VTK samples supported')
        ids = [cell.GetPointId(i) for i in range(4)]
        if len(set(ids)) != 4 or any(i < 0 or i >= n for i in ids):
            raise NativeFieldEvidenceError('Invalid VTK tetra index')
        p = xyz[ids].astype('float64')
        edges = (p[1:] - p[0])
        determinant = float(np.linalg.det(edges))
        size = float(np.max(np.abs(edges)))
        if not math.isfinite(determinant) or size <= 0 or abs(determinant) <= 1e-12 * size**3:
            raise NativeFieldEvidenceError('Degenerate or near-coplanar native VTK tetrahedron')
        topology.update(','.join(map(str, ids)).encode('ascii') + b';')
    vectors = {}
    for kind in ('E', 'B'):
        fields = [mesh.GetPointData().GetArray(kind + suffix) for suffix in ('_real', '_imag')]
        if any(x is None for x in fields):
            if kind == 'E' or any(x is not None for x in fields) or declared['B_complex_declared']:
                raise NativeFieldEvidenceError('Incomplete complex vector in native field payload')
            continue
        if kind == 'B' and not declared['B_complex_declared']:
            raise NativeFieldEvidenceError('Native B payload disagrees with header')
        pair = []
        for field in fields:
            if field.GetNumberOfComponents() != 3 or field.GetNumberOfTuples() != n:
                raise NativeFieldEvidenceError('Invalid decoded complex vector dimensions')
            array = vtk_to_numpy(field)
            if array.shape != (n, 3) or not bool(np.isfinite(array).all()):
                raise NativeFieldEvidenceError('Nonfinite native complex field samples')
            pair.append(array)
        vectors[kind] = pair
    if _sha(path) != declared['sha256']:
        raise NativeFieldEvidenceError('VTU modified during local field decode')
    return mesh, xyz, vectors, topology.hexdigest()

def _assemble_local_vtk_pieces(root: Path, inventory: dict[str, Path], pieces: list[dict]):
    """Strictly join SHA-checked MPI *visualization* pieces by exact coordinates.

    We intentionally reject conflicting shared-point vectors and duplicate tetra
    (including ghost cells). No tolerance-based welding, interpolation, or mesh
    equivalence is inferred. Returned arrays never leave this process in a report.
    """
    import numpy as np

    if sum(inventory[p['name']].stat().st_size for p in pieces) > MAX_MPI_TOTAL_FIELD_BYTES:
        raise NativeFieldEvidenceError('MPI VTU source size exceeds bounded decoder budget')
    unique: dict[tuple[float, float, float], int] = {}
    positions = []
    values = {'E': ([], []), 'B': ([], [])}
    cells: set[tuple[int, int, int, int]] = set()
    b_presence = {piece['B_complex_declared'] for piece in pieces}
    if len(b_presence) != 1:
        raise NativeFieldEvidenceError('MPI pieces disagree about complex B availability')
    magnetic = b_presence.pop()
    piece_evidence = []
    for piece in pieces:
        mesh, xyz, vectors, topology_sha = _read_local_vtu(inventory[piece['name']], piece)
        if ('B' in vectors) != magnetic:
            raise NativeFieldEvidenceError('MPI decoded complex B availability differs')
        if len(xyz) > MAX_ASSEMBLED_POINTS:
            raise NativeFieldEvidenceError('MPI piece exceeds bounded point budget')
        remap = []
        for local_i, point in enumerate(xyz):
            # Exact coordinates are required; negative zeros normalize in tuple.
            key = tuple(float(c) for c in point)
            existing = unique.get(key)
            if existing is None:
                existing = len(positions)
                if existing >= MAX_ASSEMBLED_POINTS:
                    raise NativeFieldEvidenceError('MPI assembled unique-point budget exceeded')
                unique[key] = existing
                positions.append(key)
                for kind in ('E', 'B'):
                    if kind in vectors:
                        for k in (0, 1):
                            values[kind][k].append(np.array(vectors[kind][k][local_i], copy=True))
            else:
                for kind in ('E', 'B'):
                    if kind in vectors:
                        for k in (0, 1):
                            if not np.array_equal(values[kind][k][existing], vectors[kind][k][local_i]):
                                raise NativeFieldEvidenceError('Inconsistent shared MPI point complex field values')
            remap.append(existing)
        for cell_i in range(mesh.GetNumberOfCells()):
            cell = mesh.GetCell(cell_i)
            ids = tuple(remap[cell.GetPointId(i)] for i in range(4))
            if len(set(ids)) != 4:
                raise NativeFieldEvidenceError('MPI tetra has repeated global coordinate')
            canonical = tuple(sorted(ids))
            if canonical in cells:
                raise NativeFieldEvidenceError('Duplicate/ghost tetra in MPI piece assembly')
            if len(cells) >= MAX_CELLS:
                raise NativeFieldEvidenceError('MPI assembled tetra budget exceeded')
            cells.add(canonical)
        piece_evidence.append({'vtu_sha256': piece['sha256'],
                               'vtk_points': int(mesh.GetNumberOfPoints()),
                               'vtk_tetra': int(mesh.GetNumberOfCells()),
                               'piece_geometry_sha256': topology_sha})
    xyz = np.asarray(positions, dtype=np.float64)
    assembled = {}
    for kind in ('E', 'B'):
        if kind == 'B' and not magnetic:
            continue
        pair = [np.asarray(values[kind][k], dtype=np.float64) for k in (0, 1)]
        field = pair[0] + 1j * pair[1]
        norm = float(np.linalg.norm(field))
        if not math.isfinite(norm) or norm <= 0:
            raise NativeFieldEvidenceError('Complex field norm invalid or zero')
        assembled[kind] = {'unit': 'V/m' if kind == 'E' else 'T',
                           'sampling': 'VTK PointData complex 3-vector; exact MPI point union',
                           'point_tuple_count': len(positions),
                           'real_values_sha256': hashlib.sha256(np.ascontiguousarray(pair[0], dtype='<f8').tobytes()).hexdigest(),
                           'imag_values_sha256': hashlib.sha256(np.ascontiguousarray(pair[1], dtype='<f8').tobytes()).hexdigest(),
                           'unweighted_discrete_norm': norm}
    topology = hashlib.sha256()
    topology.update(np.ascontiguousarray(xyz, dtype='<f8').tobytes())
    for ids in sorted(cells):
        topology.update(','.join(map(str, ids)).encode('ascii') + b';')
    return xyz, len(cells), assembled, topology.hexdigest(), piece_evidence


def inspect_gmsh_physical_tags(root: Path, artifacts: list[dict], *,
                               config: dict | None = None) -> dict:
    """Inspect an SHA-bound Gmsh 2.x ASCII tag inventory, never a VTK tag map.

    The Python-only bounded parser deliberately returns BLOCKED on binary, v4,
    missing, or unsupported formats. It is not a substitute for A17's vetted
    coordinate/entity/face correspondence or an imported native mesh reader.
    """
    inventory = _native_inventory(Path(root), artifacts)
    path = inventory.get('sqe_em/sqe_em.msh')
    if path is None:
        raise NativeFieldEvidenceError('Missing SHA-bound Gmsh mesh')
    record = {'schema': 'sqe.gmsh-tags-format-screen.v1',
              'mesh_sha256': _sha(path),
              'status': 'BLOCKED_UNSUPPORTED_OR_UNTAGGED_GMSH_MESH',
              'vtk_to_gmsh_registration': 'BLOCKED_NO_REVIEWED_COORDINATE_FACE_MAP',
              'physical_mode_identity': 'UNRESOLVED'}
    if path.stat().st_size > MAX_MESH_TAG_SCAN_BYTES:
        return {**record, 'status': 'BLOCKED_GMSH_EXCEEDS_BOUNDED_PARSER_BUDGET'}
    try:
        raw = path.read_bytes()
        if _sha(path) != record['mesh_sha256']:
            raise NativeFieldEvidenceError('SHA-bound Gmsh source mutated during tag inspection')
        if b'\x00' in raw:
            return {**record, 'status': 'BLOCKED_GMSH_BINARY_REQUIRES_NATIVE_REVIEWED_READER'}
        lines = raw.decode('utf-8').splitlines()
        if len(lines) > 1_000_000 or len(lines) < 5:
            return record
        if lines[0].strip() != '$MeshFormat' or lines[1].split()[:2] != ['2.2', '0']:
            return record
        end = lines.index('$EndMeshFormat')
        if end != 2:
            return record
        if '$Nodes' not in lines or '$Elements' not in lines:
            return record
        ni = lines.index('$Nodes')
        n_nodes = int(lines[ni+1].strip())
        if not 4 <= n_nodes <= MAX_ASSEMBLED_POINTS or ni+2+n_nodes >= len(lines) or lines[ni+2+n_nodes].strip() != '$EndNodes':
            return record
        nodes = {}
        for line in lines[ni+2:ni+2+n_nodes]:
            columns = line.split()
            if len(columns) != 4:
                return record
            nid = int(columns[0])
            coords = tuple(float(x) for x in columns[1:])
            if nid <= 0 or nid in nodes or not all(math.isfinite(x) for x in coords):
                return record
            nodes[nid] = coords
        i = lines.index('$Elements')
        count = int(lines[i+1].strip())
        if not 0 < count <= 1_000_000 or i+2+count >= len(lines) or lines[i+2+count].strip() != '$EndElements':
            return record
        volume, surfaces = set(), set()
        volume_count = surface_count = 0
        for row in lines[i+2:i+2+count]:
            columns = row.split()
            if len(columns) < 4:
                return record
            cell_type, ntags = int(columns[1]), int(columns[2])
            if ntags < 1 or len(columns) < 3+ntags+1:
                return record
            tag = int(columns[3])
            if tag <= 0:
                return record
            ids = [int(x) for x in columns[3+ntags:]]
            if not ids or len(set(ids)) != len(ids) or any(idx not in nodes for idx in ids):
                return record
            if cell_type == 4:  # Gmsh linear tetra
                if len(columns) != 3+ntags+4:
                    return record
                p0, p1, p2, p3 = [nodes[idx] for idx in ids]
                a, b, c = ([p1[i]-p0[i] for i in range(3)],
                           [p2[i]-p0[i] for i in range(3)],
                           [p3[i]-p0[i] for i in range(3)])
                triple = (a[0] * (b[1]*c[2]-b[2]*c[1])
                          -a[1] * (b[0]*c[2]-b[2]*c[0])
                          +a[2] * (b[0]*c[1]-b[1]*c[0]))
                if not math.isfinite(triple) or abs(triple) < 1e-30:
                    return {**record, 'status': 'BLOCKED_DEGENERATE_GMSH_TETRA'}
                volume.add(tag); volume_count += 1
            elif cell_type == 2:  # Gmsh linear face triangle
                if len(columns) != 3+ntags+3:
                    return record
                surfaces.add(tag); surface_count += 1
        if not volume or not surfaces:
            return {**record, 'status': 'BLOCKED_GMSH_VOLUME_OR_SURFACE_TAGS_MISSING'}
        expected_v = {v for material in (config or {}).get('Domains', {}).get('Materials', [])
                      for v in material.get('Attributes', [])}
        bounds = (config or {}).get('Boundaries', {})
        expected_s = {v for key in ('PEC', 'PMC') for v in bounds.get(key, {}).get('Attributes', [])}
        for key in ('LumpedPort', 'WavePort'):
            expected_s.update(v for port in bounds.get(key, []) for v in port.get('Attributes', []))
        if (expected_v and not expected_v <= volume) or (expected_s and not expected_s <= surfaces):
            return {**record, 'status': 'BLOCKED_GMSH_TAGS_NOT_ALIGNED_WITH_PALACE_DECK',
                    'volume_physical_tags': sorted(volume), 'surface_physical_tags': sorted(surfaces)}
        return {**record, 'status': 'VERIFIED_GMSH_V2_ASCII_PHYSICAL_TAG_PRESENCE_ONLY',
                'volume_physical_tags': sorted(volume), 'surface_physical_tags': sorted(surfaces),
                'tagged_tetra_count': volume_count, 'tagged_triangle_count': surface_count,
                'verified_mesh_node_count': n_nodes,
                'limitations': ['Physical IDs in Gmsh elements are not VTK per-point/per-cell material tags',
                                'No face orientation, material constitutive map or spatial registration proven']}
    except (UnicodeError, ValueError, IndexError, TypeError, AttributeError):
        return record


def inspect_local_palace_field_values(root: Path, config: dict, artifacts: list[dict],
                                     *, saved_ordinal: int = 1) -> dict:
    """Bounded read-only VTK E/B diagnostics, including conservative MPI assembly.

    Digests, tag-presence and bounds only; no raw private field arrays, B->H
    conversion, remesh registration, or automatic physical mode comparison.
    """
    if type(saved_ordinal) is not int or not 1 <= saved_ordinal <= 12:
        raise NativeFieldEvidenceError('Invalid saved mode ordinal')
    export = inspect_palace_field_export(root, config, artifacts)
    if export['status'] != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY':
        raise NativeFieldEvidenceError('Verified native field export required for local decoding')
    if saved_ordinal > len(export['field_samples']):
        raise NativeFieldEvidenceError('Requested saved mode is not present')
    sample = export['field_samples'][saved_ordinal - 1]
    inventory = _native_inventory(Path(root), artifacts)
    xyz, ncells, fields, topology_sha, piece_evidence = _assemble_local_vtk_pieces(
        Path(root), inventory, sample['vtk_pieces'])
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    l0 = export['metres_per_mesh_unit']
    tag_evidence = inspect_gmsh_physical_tags(root, artifacts, config=config)
    result = {'schema': 'sqe.palace-local-field-diagnostic.v1',
            'status': 'VERIFIED_LOCAL_VTK_SAMPLES_DIAGNOSTIC_ONLY',
            'saved_collection_ordinal_not_mode_identity': saved_ordinal,
            'vtu_sha256': piece_evidence[0]['vtu_sha256'] if len(piece_evidence) == 1 else None,
            'mpi_piece_sha256': [p['vtu_sha256'] for p in piece_evidence],
            'mpi_piece_count': len(piece_evidence),
            'mpi_piece_assembly': 'EXACT_SHARED_COORDINATE_AND_VECTOR_UNION_DIAGNOSTIC_ONLY',
            'mpi_piece_geometry': piece_evidence,
            'mesh_sha256': export['mesh_sha256'],
            'deck_sha256': export['deck_sha256'], 'eig_sha256': export['native_eig_sha256'],
            'geometry_sha256': topology_sha,
            'vtk_point_count': int(len(xyz)), 'vtk_tetra_count': int(ncells),
            'coordinate_bounds_m': {'min': [float(v) * l0 for v in lo],
                                    'max': [float(v) * l0 for v in hi]},
            'complex_components': fields, 'gmsh_physical_tags': tag_evidence,
            'H_field_status': 'BLOCKED_REQUIRES_REVIEWED_CONSTITUTIVE_MU',
            'surface_tag_status': 'BLOCKED_NO_VERIFIED_VTK_TO_GMSH_SURFACE_REGISTRATION',
            'phase': 'Native real/imag samples decoded, cross-run reference uncalibrated',
            'mode_identity': 'UNRESOLVED', 'em_to_hamiltonian': 'BLOCKED'}
    return result



def screen_cross_mesh_visualization_overlap(left_root: Path, left_artifacts: list[dict],
        left_export: dict, right_root: Path, right_artifacts: list[dict],
        right_export: dict, *, coordinate_assumption: str) -> dict:
    """Read-only B03 *numerical screening*, never physical registration or mode identity.

    Integrate two directions with a degree-2 tetrahedron quadrature rule. Each
    quadrature point is barycentrically interpolated in the *other* grid, not
    paired by node index or frequency. Missing/overlapping coverage, material
    differences, wrong units and stale hashes fail closed. This limited linear
    VTK PointData diagnostic does NOT measure Nedelec/H(curl) mode overlap or
    give a certified interpolation-error bound; A12/A17 review is required.

    An explicit same-frame assumption is necessary but does NOT prove that two
    meshing operations used the same CAD revision or physical surface tags.
    No geometrical transforms, automatic mode mapping or private field tuples
    are exposed. The deliberately small cell budget bounds the search cost.
    """
    if coordinate_assumption != 'SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY':
        raise NativeFieldEvidenceError('Cross-mesh coordinate frame is unreviewed; explicit diagnostic-only assumption required')
    for export in (left_export, right_export):
        if (export.get('schema') != SCHEMA or
                export.get('status') != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY' or
                export.get('field_unit') != 'V/m' or
                len(export.get('field_samples', [])) != 1 or
                len(export['field_samples'][0].get('vtk_pieces', [])) != 1):
            raise NativeFieldEvidenceError('Cross-mesh diagnostic needs one verified complex single-piece eigenfield per run')
    if (left_export['mesh_sha256'] == right_export['mesh_sha256'] or
            left_export['metres_per_mesh_unit'] != right_export['metres_per_mesh_unit']):
        raise NativeFieldEvidenceError('Cross-mesh comparison requires different meshes and identical physical coordinate units')
    import numpy as np
    sides = []
    for root, artifacts, export in ((left_root, left_artifacts, left_export),
                                    (right_root, right_artifacts, right_export)):
        inventory = _native_inventory(Path(root), artifacts)
        deck = inventory.get('sqe_em/sqe_em.json')
        meshfile = inventory.get('sqe_em/sqe_em.msh')
        if (deck is None or meshfile is None or _sha(deck) != export.get('deck_sha256')
                or _sha(meshfile) != export.get('mesh_sha256')):
            raise NativeFieldEvidenceError('Cross-mesh deck/mesh hashes do not match native evidence')
        try:
            config = json.loads(deck.read_text(encoding='utf-8'))
        except (UnicodeError, ValueError) as exc:
            raise NativeFieldEvidenceError('Invalid native cross-mesh deck') from exc
        if inspect_palace_field_export(root, config, artifacts) != export:
            raise NativeFieldEvidenceError('Stale cross-mesh native field-export lineage')
        piece = export['field_samples'][0]['vtk_pieces'][0]
        mesh, xyz, vectors, geometry_sha = _read_local_vtu(inventory[piece['name']], piece)
        if not 0 < mesh.GetNumberOfCells() <= 256:
            raise NativeFieldEvidenceError('Cross-mesh diagnostic exceeds bounded 256-tetra budget')
        cells = np.asarray([[mesh.GetCell(i).GetPointId(j) for j in range(4)]
                            for i in range(mesh.GetNumberOfCells())], dtype=np.int64)
        sides.append({'config': config, 'source_inventory': inventory, 'source_artifacts': artifacts,
                      'xyz': xyz.astype(np.float64), 'cells': cells,
                      'vectors': {key: value[0] + 1j * value[1] for key, value in vectors.items()},
                      'geometry_sha256': geometry_sha, 'export': export})
    for setting in ('Domains', 'Boundaries'):
        if sides[0]['config'].get(setting) != sides[1]['config'].get(setting):
            raise NativeFieldEvidenceError('Cross-mesh material or boundary definitions differ')
    if (sides[0]['config'].get('Solver', {}).get('Order') !=
            sides[1]['config'].get('Solver', {}).get('Order')):
        raise NativeFieldEvidenceError('Cross-mesh finite-element orders differ')
    if ('B' in sides[0]['vectors']) != ('B' in sides[1]['vectors']):
        raise NativeFieldEvidenceError('Cross-mesh complex B representations disagree')
    span = max(1.0, *(float(np.ptp(s['xyz'], axis=0).max()) for s in sides))
    tolerance = span * 1e-10
    if not (np.allclose(sides[0]['xyz'].min(axis=0), sides[1]['xyz'].min(axis=0), rtol=0, atol=tolerance)
            and np.allclose(sides[0]['xyz'].max(axis=0), sides[1]['xyz'].max(axis=0), rtol=0, atol=tolerance)):
        raise NativeFieldEvidenceError('Cross-mesh coordinate bounds disagree; no registration')
    for side in sides:
        corners = side['xyz'][side['cells']]
        edges = np.stack((corners[:, 1]-corners[:, 0], corners[:, 2]-corners[:, 0],
                          corners[:, 3]-corners[:, 0]), axis=-1)
        determinants = np.linalg.det(edges)
        if not np.all(np.isfinite(determinants)) or np.any(determinants <= 1e-12 * span**3):
            raise NativeFieldEvidenceError('Cross-mesh tetra orientation or geometry invalid')
        side['corners'] = corners
        side['inverse'] = np.linalg.inv(edges)
        side['volume'] = determinants / 6.0
        side['bounds_lo'] = corners.min(axis=1)
        side['bounds_hi'] = corners.max(axis=1)
    volume_left, volume_right = (float(side['volume'].sum()) for side in sides)
    if not math.isclose(volume_left, volume_right, rel_tol=1e-8, abs_tol=0):
        raise NativeFieldEvidenceError('Cross-mesh domains have different integrated tetra volumes')

    # Symmetric 4-point degree-2 quadrature for first-order tetrahedra. This
    # rule is not exact when a target tetra interface cuts a source tetra;
    # two-direction disagreement is an *indicator*, not an error certificate.
    small = (5.0 - math.sqrt(5.0)) / 20.0
    large = 1.0 - 3.0 * small
    barycentric = np.array([[large if i == j else small for i in range(4)]
                            for j in range(4)])
    kinds = ('E', 'B') if 'B' in sides[0]['vectors'] else ('E',)

    def lookup(target: dict, point):
        mask = np.all((target['bounds_lo'] - tolerance <= point) &
                      (point <= target['bounds_hi'] + tolerance), axis=1)
        matching = []
        for index in np.flatnonzero(mask):
            abc = target['inverse'][index] @ (point - target['corners'][index, 0])
            weights = np.array([1.0 - abc.sum(), *abc])
            if np.all(weights >= -1e-9) and np.all(weights <= 1+1e-9):
                matching.append((int(index), weights))
        if not matching:
            raise NativeFieldEvidenceError('Cross-mesh interpolation has an uncovered quadrature point')
        values = []
        for i, weights in matching:
            values.append({kind: weights @ target['vectors'][kind][target['cells'][i]]
                           for kind in kinds})
        if len(values) > 1:
            for kind in kinds:
                for candidate in values[1:]:
                    if not np.allclose(candidate[kind], values[0][kind], atol=1e-9, rtol=1e-8):
                        raise NativeFieldEvidenceError('Ambiguous overlap/discontinuous field at target tetra interface')
        return values[0]

    directional = []
    for source, target, reverse in ((sides[0], sides[1], False), (sides[1], sides[0], True)):
        total = {kind: [0j, 0j, 0j] for kind in kinds}
        for cell_index, indices in enumerate(source['cells']):
            corners = source['corners'][cell_index]
            nodal = {kind: source['vectors'][kind][indices] for kind in kinds}
            for weights in barycentric:
                point = weights @ corners
                other = lookup(target, point)
                for kind in kinds:
                    current = weights @ nodal[kind]
                    left, right = (other[kind], current) if reverse else (current, other[kind])
                    weight = source['volume'][cell_index] / 4
                    total[kind][0] += weight * np.vdot(left, left)
                    total[kind][1] += weight * np.vdot(right, right)
                    total[kind][2] += weight * np.vdot(left, right)
        result = {}
        for kind, (aa, bb, ab) in total.items():
            if (not math.isfinite(aa.real) or not math.isfinite(bb.real) or aa.real <= 0 or bb.real <= 0
                    or abs(aa.imag) > 1e-9 * aa.real or abs(bb.imag) > 1e-9 * bb.real):
                raise NativeFieldEvidenceError('Cross-mesh field norm invalid')
            overlap = ab / math.sqrt(aa.real * bb.real)
            if not math.isfinite(abs(overlap)) or abs(overlap) > 1 + 1e-8:
                raise NativeFieldEvidenceError('Cross-mesh diagnostic violates Cauchy-Schwarz bound')
            result[kind] = overlap
        directional.append(result)
    result = {'schema': 'sqe.cross-mesh-visualization-screen.v1',
              'status': 'DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH',
              'coordinate_assumption': coordinate_assumption,
              'left_mesh_sha256': left_export['mesh_sha256'],
              'right_mesh_sha256': right_export['mesh_sha256'],
              'left_deck_sha256': left_export['deck_sha256'],
              'right_deck_sha256': right_export['deck_sha256'],
              'left_eig_sha256': left_export['native_eig_sha256'],
              'right_eig_sha256': right_export['native_eig_sha256'],
              'left_field_vtu_sha256': left_export['field_samples'][0]['vtk_pieces'][0]['sha256'],
              'right_field_vtu_sha256': right_export['field_samples'][0]['vtk_pieces'][0]['sha256'],
              'E_unit': 'V/m', 'B_unit_if_present': 'T (magnetic flux density, NOT H)',
              'left_geometry_sha256': sides[0]['geometry_sha256'],
              'right_geometry_sha256': sides[1]['geometry_sha256'],
              'integrated_volume_m3': volume_left * left_export['metres_per_mesh_unit']**3,
              'quadrature': 'degree-2 four-point tetra; bidirectional barycentric visualization interpolation',
              'interpolation_error': 'UNBOUNDED_NO_VERIFIED_FE_ERROR_ESTIMATE',
              'physical_coordinate_registration': 'BLOCKED_REQUIRES_REVIEWED_CAD_GMSH_TO_VTK_MAP',
              'material_weighting': 'BLOCKED_NO_REVIEWED_PERMITTIVITY_PERMEABILITY',
              'mode_identity': 'UNRESOLVED_REQUIRES_EXPERT_MODE_LABEL',
              'physical_convergence': 'NOT_ESTABLISHED', 'H_field': 'BLOCKED_NO_REVIEWED_B_TO_H',
              'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD'}
    for kind in kinds:
        forward, backward = directional[0][kind], directional[1][kind]
        result[kind + '_forward_overlap_magnitude'] = min(1.0, abs(forward))
        result[kind + '_backward_overlap_magnitude'] = min(1.0, abs(backward))
        result[kind + '_bidirectional_overlap_disagreement'] = abs(forward-backward)
        result[kind + '_forward_relative_phase_rad'] = cmath.phase(forward)
        result[kind + '_backward_relative_phase_rad'] = cmath.phase(backward)
    result['B_field_status'] = ('DIAGNOSTIC_B_FLUX_DENSITY_NOT_H' if 'B' in kinds
                                else 'BLOCKED_NO_PAIRED_COMPLEX_B')
    # Recheck the *entire* worker manifest after interpolation, not only the
    # initial VTK read: concurrent native output mutation is not evidence.
    for side in sides:
        for declared in side['source_artifacts']:
            if _sha(side['source_inventory'][declared['name']]) != declared['sha256']:
                raise NativeFieldEvidenceError('Native cross-mesh artifact changed during interpolation')
    return result

def compare_same_mesh_fields(left_root: Path, left_artifacts: list[dict], left_export: dict,
                             right_root: Path, right_artifacts: list[dict], right_export: dict) -> dict:
    """Compute phase-invariant *diagnostic* overlap on identical linear tetra cells.

    Deliberately rejects refined/remeshed inputs, unsupported FE visualizations,
    and mixed materials (material-weighted H(curl) overlap requires a distinct
    reviewed sampling/interpolation protocol). No automatic mode identification.
    """
    if any(x.get('schema') != SCHEMA or x.get('status') != 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY'
           for x in (left_export, right_export)):
        raise NativeFieldEvidenceError('Verified complex native exports are required')
    if (left_export.get('mesh_sha256') != right_export.get('mesh_sha256')
            or left_export.get('metres_per_mesh_unit') != right_export.get('metres_per_mesh_unit')
            or left_export.get('field_unit') != 'V/m' or right_export.get('field_unit') != 'V/m'):
        raise NativeFieldEvidenceError('Different mesh/coordinate frame or field units; no common-domain overlap')
    for export in (left_export, right_export):
        if len(export['field_samples']) != 1 or len(export['field_samples'][0]['vtk_pieces']) != 1:
            raise NativeFieldEvidenceError('Single-mode, single-piece VTK overlap only; MPI assembly not reviewed')
    left_files = _native_inventory(Path(left_root), left_artifacts)
    right_files = _native_inventory(Path(right_root), right_artifacts)
    for export, inventory, root, artifacts in (
            (left_export, left_files, left_root, left_artifacts),
            (right_export, right_files, right_root, right_artifacts)):
        deck = inventory.get('sqe_em/sqe_em.json')
        mesh = inventory.get('sqe_em/sqe_em.msh')
        if (deck is None or mesh is None or _sha(mesh) != export.get('mesh_sha256')
                or _sha(deck) != export.get('deck_sha256')):
            raise NativeFieldEvidenceError('Complex field source mesh/deck provenance mismatch')
        try:
            config = json.loads(deck.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise NativeFieldEvidenceError('Invalid native Palace field-export deck') from exc
        if inspect_palace_field_export(root, config, artifacts) != export:
            raise NativeFieldEvidenceError('Field-export evidence is stale or not independently reproducible')
    # Shared mesh is insufficient when physical boundaries/materials/solver
    # order differ. No automatic comparison across unreviewed physics inputs.
    configs = [json.loads(left_files['sqe_em/sqe_em.json'].read_text(encoding='utf-8')),
               json.loads(right_files['sqe_em/sqe_em.json'].read_text(encoding='utf-8'))]
    for key in ('Domains', 'Boundaries'):
        if configs[0].get(key) != configs[1].get(key):
            raise NativeFieldEvidenceError('Native material/boundary definitions differ')
    if configs[0].get('Solver', {}).get('Order') != configs[1].get('Solver', {}).get('Order'):
        raise NativeFieldEvidenceError('Native finite-element solver orders differ')
    try:
        import numpy as np
    except ImportError as exc:
        raise NativeFieldEvidenceError('Numpy unavailable; no complex overlap calculated') from exc
    arrays = []
    for export, inventory in ((left_export, left_files), (right_export, right_files)):
        piece = export['field_samples'][0]['vtk_pieces'][0]
        if piece['name'] not in inventory:
            raise NativeFieldEvidenceError('Field data changed since export inspection')
        arrays.append(_read_local_vtu(inventory[piece['name']], piece))
    a, b = arrays
    ma, mb = a[0], b[0]
    if ma.GetNumberOfPoints() != mb.GetNumberOfPoints() or ma.GetNumberOfCells() != mb.GetNumberOfCells():
        raise NativeFieldEvidenceError('Native visualization grids do not match')
    xyz_a, xyz_b = a[1], b[1]
    if not np.array_equal(xyz_a, xyz_b):
        raise NativeFieldEvidenceError('Native VTK point coordinates differ')
    ea = a[2]['E'][0] + 1j*a[2]['E'][1]
    eb = b[2]['E'][0] + 1j*b[2]['E'][1]
    if ('B' in a[2]) != ('B' in b[2]):
        raise NativeFieldEvidenceError('Runs have incompatible magnetic B field representations')
    magnetic = 'B' in a[2]
    if magnetic:
        ba_field = a[2]['B'][0] + 1j*a[2]['B'][1]
        bb_field = b[2]['B'][0] + 1j*b[2]['B'][1]
    # Consistent linear tetra nodal mass matrix: diag V/10, off-diag V/20.
    # Only valid for the *same* piecewise linear tetra tessellation.
    aa = bb = ab = 0j
    ba = bnorm = bab = 0j
    volume = 0.0
    for cell_index in range(ma.GetNumberOfCells()):
        ca, cb = ma.GetCell(cell_index), mb.GetCell(cell_index)
        if ca.GetCellType() != 10 or cb.GetCellType() != 10:  # VTK_TETRA, not high-order/nonconformal
            raise NativeFieldEvidenceError('Only identical linear tetra visualization elements supported')
        indices = [ca.GetPointId(i) for i in range(4)]
        if indices != [cb.GetPointId(i) for i in range(4)]:
            raise NativeFieldEvidenceError('Native tetra topology mismatch')
        p = xyz_a[indices]
        v = abs(float(np.linalg.det(np.vstack((p[1]-p[0], p[2]-p[0], p[3]-p[0]))))) / 6
        if not math.isfinite(v) or v <= 0:
            raise NativeFieldEvidenceError('Degenerate/invalid native tetrahedron')
        volume += v
        x, y = ea[indices], eb[indices]
        aa += v / 20 * (np.vdot(x, x) + np.vdot(x.sum(axis=0), x.sum(axis=0)))
        bb += v / 20 * (np.vdot(y, y) + np.vdot(y.sum(axis=0), y.sum(axis=0)))
        ab += v / 20 * (np.vdot(x, y) + np.vdot(x.sum(axis=0), y.sum(axis=0)))
        if magnetic:
            u, w = ba_field[indices], bb_field[indices]
            ba += v / 20 * (np.vdot(u, u) + np.vdot(u.sum(axis=0), u.sum(axis=0)))
            bnorm += v / 20 * (np.vdot(w, w) + np.vdot(w.sum(axis=0), w.sum(axis=0)))
            bab += v / 20 * (np.vdot(u, w) + np.vdot(u.sum(axis=0), w.sum(axis=0)))
    if aa.real <= 0 or bb.real <= 0 or abs(aa.imag) > aa.real * 1e-10 or abs(bb.imag) > bb.real * 1e-10:
        raise NativeFieldEvidenceError('Invalid field norm; no overlap')
    norm = math.sqrt(aa.real * bb.real)
    overlap = ab / norm
    if abs(overlap) > 1 + 1e-8 or not math.isfinite(abs(overlap)):
        raise NativeFieldEvidenceError('Complex field overlap outside Cauchy-Schwarz bound')
    b_overlap = None
    if magnetic:
        if (ba.real <= 0 or bnorm.real <= 0 or abs(ba.imag) > ba.real * 1e-10
                or abs(bnorm.imag) > bnorm.real * 1e-10):
            raise NativeFieldEvidenceError('Invalid B field norm; no magnetic overlap')
        b_overlap = bab / math.sqrt(ba.real * bnorm.real)
        if not math.isfinite(abs(b_overlap)) or abs(b_overlap) > 1 + 1e-8:
            raise NativeFieldEvidenceError('B complex overlap violates Cauchy-Schwarz bound')
    return {'schema': 'sqe.complex-field-overlap-screen.v1',
            'status': 'DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH',
            'complex_overlap_re': float(overlap.real), 'complex_overlap_im': float(overlap.imag),
            'phase_invariant_overlap_magnitude': min(1.0, abs(overlap)),
            'relative_phase_rad': cmath.phase(overlap), 'normalization': 'L2(V/m) over identical linear tetra visualisation mesh',
            'integrated_mesh_volume_m3': volume * left_export['metres_per_mesh_unit'] ** 3,
            'mesh_sha256': left_export['mesh_sha256'],
            'B_field_status': ('DIAGNOSTIC_UNWEIGHTED_B_NOT_H' if magnetic
                               else 'BLOCKED_NOT_AVAILABLE_IN_BOTH_RUNS'),
            'B_complex_overlap_re': float(b_overlap.real) if magnetic else None,
            'B_complex_overlap_im': float(b_overlap.imag) if magnetic else None,
            'B_phase_invariant_overlap_magnitude': min(1.0, abs(b_overlap)) if magnetic else None,
            'H_field_status': 'BLOCKED_REQUIRES_REVIEWED_CONSTITUTIVE_MU',
            'surface_tag_status': 'BLOCKED_NO_VERIFIED_VTK_TO_GMSH_SURFACE_REGISTRATION',
            'mode_identity': 'UNRESOLVED_REQUIRES_EXPERT_SCIENTIFIC_REVIEW',
            'mesh_convergence': 'NOT_ESTABLISHED', 'em_to_hamiltonian': 'BLOCKED',
            'limitations': ['Visualization-point overlap is NOT native H(curl) mass-matrix overlap',
                            'Only identical meshes; different mesh refinements require reviewed projection',
                            'No epsilon/mu weighting, loss-model validation, or expert mode-label acceptance']}


def inspect_palace_driven_sparameters(root: Path, config: dict, artifacts: list[dict],
                                     *, frequencies_hz: list[float], excited_port: int) -> dict:
    """Screen the authentic SHA-bound Palace two-port driven *excited column*.

    Complex S is reconstructed only when both native dB magnitude and degrees
    phase columns are present. The result is bounded *numeric evidence*, not
    an independently validated port impedance, de-embedding, reciprocity or
    resonator/eigenmode identity. Unexcited columns are NEVER synthesized.
    """
    if (type(excited_port) is not int or excited_port not in (1, 2)
            or type(frequencies_hz) is not list or not 2 <= len(frequencies_hz) <= 201
            or any(type(f) not in (float, int) or not math.isfinite(f) or f <= 0
                   for f in frequencies_hz)
            or any(a >= b for a, b in zip(frequencies_hz, frequencies_hz[1:]))):
        raise NativeFieldEvidenceError('Invalid reviewed driven frequency/port request')
    if (config.get('Problem', {}).get('Type') != 'Driven'
            or config.get('Model', {}).get('Mesh') != 'sqe_em.msh'):
        raise NativeFieldEvidenceError('Palace driven problem/deck is not reviewed')
    ports = config.get('Boundaries', {}).get('LumpedPort')
    if (type(ports) is not list or len(ports) != 2
            or config.get('Boundaries', {}).get('WavePort') not in (None, [])
            or any(type(p) is not dict or p.get('Index') != i
                   or type(p.get('Excitation')) is not bool
                   for i, p in enumerate(ports, 1))
            or [i for i, p in enumerate(ports, 1) if p['Excitation']] != [excited_port]):
        raise NativeFieldEvidenceError('Two ordered native lumped ports and exact single excitation required')
    driven = config.get('Solver', {}).get('Driven', {})
    for key, target in (('MinFreq', frequencies_hz[0]/1e9),
                        ('MaxFreq', frequencies_hz[-1]/1e9),
                        ('FreqStep', (frequencies_hz[1]-frequencies_hz[0])/1e9)):
        val = driven.get(key)
        if type(val) not in (float, int) or not math.isfinite(val) or not math.isclose(val, target, rel_tol=1e-7, abs_tol=1e-12):
            raise NativeFieldEvidenceError('Native driven deck does not match reviewed frequency sweep')
    inventory = _native_inventory(Path(root), artifacts)
    deck = inventory.get('sqe_em/sqe_em.json')
    mesh = inventory.get('sqe_em/sqe_em.msh')
    csv_path = inventory.get('sqe_em/outputFiles/port-S.csv')
    if deck is None or mesh is None or csv_path is None:
        raise NativeFieldEvidenceError('Missing SHA-bound driven deck/mesh/port-S.csv')
    if csv_path.stat().st_size > 2_000_000:
        raise NativeFieldEvidenceError('Native port-S.csv exceeds screen budget')
    try:
        if json.loads(deck.read_text(encoding='utf-8')) != config:
            raise NativeFieldEvidenceError('Driven deck differs from SHA-bound original')
        with csv_path.open(encoding='utf-8-sig', newline='') as fd:
            rows = list(csv.reader(fd))
    except (OSError, UnicodeError, ValueError) as exc:
        raise NativeFieldEvidenceError('Native driven CSV/deck unreadable') from exc
    if len(rows) != len(frequencies_hz)+1 or not 2 <= len(rows[0]) <= 64:
        raise NativeFieldEvidenceError('Native driven CSV shape differs from reviewed frequency sweep')
    header = [h.strip() for h in rows[0]]
    freq_label = header[0].lower()
    if 'freq' not in freq_label and 'f (' not in freq_label:
        raise NativeFieldEvidenceError('Unrecognized native driven frequency header')
    if 'ghz' in freq_label:
        scale = 1e9
    elif 'mhz' in freq_label:
        scale = 1e6
    elif 'khz' in freq_label:
        scale = 1e3
    elif 'hz' in freq_label:
        scale = 1.0
    else:
        raise NativeFieldEvidenceError('Ambiguous driven frequency unit')
    # This matches an actual public Palace CSV naming convention, but other
    # versions must be explicitly reviewed rather than guessed.
    pair = {}
    for output_port in (1, 2):
        tag = re.escape(f'S[{output_port}][{excited_port}]')
        mag_re = re.compile(r'^\|'+tag+r'\|\s*\(dB\)$', re.IGNORECASE)
        phase_re = re.compile(r'^arg\('+tag+r'\)\s*\(deg\)$', re.IGNORECASE)
        magnitudes = [i for i, h in enumerate(header) if mag_re.fullmatch(h)]
        phases = [i for i, h in enumerate(header) if phase_re.fullmatch(h)]
        if len(magnitudes) > 1 or len(phases) > 1 or bool(magnitudes) != bool(phases):
            raise NativeFieldEvidenceError('Ambiguous or incomplete native complex S columns')
        if magnitudes:
            pair[output_port] = (magnitudes[0], phases[0])
    evidence = {'schema': 'sqe.palace-driven-two-port-screen.v1',
                'case_id': 'B05', 'mode_identity': 'UNRESOLVED',
                'deck_sha256': _sha(deck), 'mesh_sha256': _sha(mesh),
                'port_s_sha256': _sha(csv_path), 'excited_port': excited_port,
                'native_port_count': 2, 'frequency_unit': 'Hz', 's_parameter_unit': 'dimensionless',
                'csv_encoding': 'magnitude dB + phase degrees',
                'port_reference': 'BLOCKED_UNREVIEWED_IMPEDANCE_AND_DEEMBEDDING',
                'passivity': 'BLOCKED_UNREVIEWED_REFERENCE_AND_PORT_POWER_NORMALIZATION',
                'reciprocity': 'BLOCKED_ONLY_ONE_EXCITATION_COLUMN',
                'eigenmode_resonance_comparison': 'BLOCKED_NO_REVIEWED_SAME_GEOMETRY_MODE_IDENTITY',
                'fabrication': 'HOLD'}
    if set(pair) != {1, 2}:
        if any(pair):
            return {**evidence, 'status': 'BLOCKED_INCOMPLETE_TWO_PORT_COMPLEX_COLUMN',
                    'observed_output_ports': sorted(pair), 'samples': []}
        return {**evidence, 'status': 'BLOCKED_MISSING_COMPLEX_S_COLUMNS', 'samples': []}
    samples = []
    for row, requested in zip(rows[1:], frequencies_hz):
        if len(row) != len(header):
            raise NativeFieldEvidenceError('Malformed native driven CSV row width')
        try:
            measured = float(row[0])*scale
            values = {}
            for output_port, (mag_i, phase_i) in pair.items():
                db, phase_deg = float(row[mag_i]), float(row[phase_i])
                if not all(math.isfinite(x) for x in (db, phase_deg)) or not -400 <= db <= 400:
                    raise ValueError('Unbounded driven complex value')
                magnitude = 10 ** (db/20)
                angle = math.radians(math.remainder(phase_deg, 360))
                values[f'S{output_port}{excited_port}'] = {
                    'real': magnitude*math.cos(angle), 'imag': magnitude*math.sin(angle),
                    'magnitude': magnitude, 'native_db': db, 'native_phase_deg': phase_deg}
        except (ValueError, OverflowError) as exc:
            raise NativeFieldEvidenceError('Malformed/nonfinite native complex driven data') from exc
        if not math.isfinite(measured) or not math.isclose(measured, requested, rel_tol=1e-6):
            raise NativeFieldEvidenceError('Native driven frequency differs from reviewed sweep')
        power = sum(v['magnitude']**2 for v in values.values())
        samples.append({'frequency_hz': measured, 'excited_column': values,
                        'numeric_column_power_sum_not_passivity_proof': power,
                        'numeric_power_above_unity': power > 1.000001})
    # Bounded CSV inspection is subject to time-of-check/time-of-use races.
    for name, path in (('sqe_em/sqe_em.json', deck), ('sqe_em/sqe_em.msh', mesh),
                       ('sqe_em/outputFiles/port-S.csv', csv_path)):
        if _sha(path) != next(x['sha256'] for x in artifacts if x['name'] == name):
            raise NativeFieldEvidenceError('Native driven artifact changed during decode')
    return {**evidence, 'status': 'VERIFIED_NATIVE_COMPLEX_DRIVEN_COLUMN_DIAGNOSTIC_ONLY',
            'number_of_samples': len(samples), 'samples': samples,
            'scientific_limitations': ['No port impedance, reference planes, calibration or excitation-power validation',
                                     'Only one driven excitation: S12/S22 cannot be inferred from S11/S21',
                                     'Pointwise power screens are not proof of passivity or reciprocity']}


def inspect_palace_signed_port_kappa(root: Path, artifacts: list[dict]) -> dict:
    """Preserve optional real native port-Q.csv signed linewidths, not |kappa|.

    Port-Q format varies by Palace version. Only paired, identified GHz
    kappa/Q columns are admitted; absent/unknown tables stay BLOCKED. This
    numeric readout is never a mode-match, linewidth calibration or loss proof.
    """
    inventory = _native_inventory(Path(root), artifacts)
    name = 'sqe_em/outputFiles/port-Q.csv'
    source = inventory.get(name)
    base = {'schema': 'sqe.palace-signed-port-kappa-screen.v1',
            'mode_identity': 'UNRESOLVED', 'physical_loss_validation': 'BLOCKED'}
    if source is None:
        return {**base, 'status': 'BLOCKED_NATIVE_PORT_Q_NOT_EMITTED'}
    if source.stat().st_size > 262_144:
        return {**base, 'status': 'BLOCKED_PORT_Q_TOO_LARGE'}
    try:
        with source.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        head = [h.strip() for h in rows[0]]
        if not 2 <= len(rows) <= 13 or len(head) > 64 or head[0] != 'm':
            raise ValueError('Unsupported table size/heading')
        qmap, kmap = {}, {}
        for index, h in enumerate(head):
            qmatch = re.fullmatch(r'Q_ext\[(\d{1,2})\]', h, flags=re.IGNORECASE)
            kmatch = re.fullmatch(r'kappa_ext\[(\d{1,2})\]\s*\(GHz\)', h, flags=re.IGNORECASE)
            if qmatch:
                port = int(qmatch.group(1))
                if port in qmap:
                    raise ValueError('Repeated port Q')
                qmap[port] = index
            if kmatch:
                port = int(kmatch.group(1))
                if port in kmap:
                    raise ValueError('Repeated port kappa')
                kmap[port] = index
        if not qmap or set(qmap) != set(kmap) or len(qmap) > 16 or set(qmap) != set(range(1, len(qmap)+1)):
            raise ValueError('Missing or unpaired signed port linewidth/Q columns')
        evidence = []
        for ordinal, row in enumerate(rows[1:], 1):
            if len(row) != len(head) or float(row[0]) != ordinal:
                raise ValueError('Inconsistent native mode index or row length')
            ports = []
            for port in sorted(qmap):
                q, k = float(row[qmap[port]]), float(row[kmap[port]])
                if not math.isfinite(q) or q <= 0 or not math.isfinite(k):
                    raise ValueError('Invalid native signed linewidth/quality')
                ports.append({'port_index': port, 'q_ext': q, 'signed_kappa_ext_GHz': k,
                              'negative_kappa_requires_sign_convention_review': k < 0})
            evidence.append({'palace_mode_ordinal_not_identity': ordinal, 'ports': ports})
    except (OSError, UnicodeError, ValueError, IndexError):
        return {**base, 'status': 'BLOCKED_UNRECOGNIZED_NATIVE_PORT_Q_FORMAT'}
    declared_sha = next(x['sha256'] for x in artifacts if x['name'] == name)
    if _sha(source) != declared_sha:
        raise NativeFieldEvidenceError('Native port-Q.csv changed during signed kappa inspection')
    return {**base, 'status': 'VERIFIED_NATIVE_SIGNED_KAPPA_NUMERIC_SCREEN_ONLY',
            'port_q_sha256': declared_sha, 'modes': evidence,
            'limitations': ['Negative native linewidth sign is preserved verbatim, not abs() or clipped',
                            'Port model/calibration and physical mode identity remain unreviewed']}
