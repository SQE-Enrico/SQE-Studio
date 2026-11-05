"""Experimental volume-weighted correlation of upstream visualization samples.

VTK owns decoding, MPI collection, cell geometry and interpolation. This module
binds those operations to saved sources and applies a discrete complex MAC.
It never assigns physical modes or approves convergence, EPR or fabrication.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from . import upstream_vtk_probe as upstream
from ..contracts import digest
from ..orchestration.artifacts import ArtifactInvalid, safe_file, verify_manifest
from ..interop.comparison import compare_palace_modes
from ..interop.native_views import palace_eigenmodes

LEGACY_SCHEMA = 'sqe.upstream-field-correlation.experimental.v1'
CELL_SCHEMA = 'sqe.upstream-field-correlation.experimental.v2'
SCHEMA = 'sqe.upstream-field-correlation.experimental.v3'
METHOD = 'VOLUME_WEIGHTED_CELL_CENTER_COMPLEX_MAC'
ASSUMPTION = 'SAME_UNROTATED_SAVED_MODEL_FRAME_DIAGNOSTIC_ONLY'
RECORDED = 'SAMPLED_FIELD_CORRELATION_RECORDED'
MAX_SOURCE_BYTES = 512 * 1024**2
MAX_PAIR_BYTES = 768 * 1024**2
MAX_SOURCE_FILE_BYTES = 128 * 1024**2
MAX_CELLS = 1_000_000
MAX_POINTS = 2_000_000
TIMEOUT_S = 90
SHA = re.compile(r'[a-f0-9]{64}\Z')
ID = re.compile(r'[a-f0-9]{32}\Z')
STUDY = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
CODE = re.compile(r'[A-Z][A-Z0-9_]{2,79}\Z')


class ComparisonBlocked(ValueError):
    pass


def _base(status='BLOCKED', reason='NATIVE_COMPARISON_UNAVAILABLE', *, grid_diagnostics=None):
    return {'schema': SCHEMA, 'status': status, 'reason_code': reason, 'method': METHOD,
            'coordinate_assumption': ASSUMPTION, 'sources': [], 'directions': [],
            'mac_gap': None, 'vtk_version': None, 'grid_diagnostics': list(grid_diagnostics or []),
            'physical_mode_identity': 'UNRESOLVED', 'mesh_convergence': 'NOT_ESTABLISHED',
            'scientific_qualification': 'NOT_ESTABLISHED', 'material_weighting': 'NONE_VOLUME_ONLY',
            'em_to_hamiltonian': 'BLOCKED', 'fabrication': 'HOLD', 'field_values_exported': False}


def _json(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ComparisonBlocked('INVALID_BOUNDED_SOURCE_JSON')
    return json.loads(path.read_text(encoding='utf-8'))


def enforce_source_budgets(root, manifest):
    """Check signed and actual byte sizes before any full-content verifier."""
    if type(manifest) is not dict:
        raise ComparisonBlocked('INVALID_NATIVE_INVENTORY')
    entries = manifest.get('artifacts')
    if type(entries) is not list or not 1 <= len(entries) <= 128:
        raise ComparisonBlocked('INVALID_NATIVE_INVENTORY')
    sizes = [e.get('bytes') if type(e) is dict else None for e in entries]
    if any(type(n) is not int or not 0 <= n <= MAX_SOURCE_FILE_BYTES for n in sizes):
        raise ComparisonBlocked('SOURCE_FILE_BUDGET')
    if sum(sizes) > MAX_SOURCE_BYTES:
        raise ComparisonBlocked('SOURCE_BYTE_BUDGET')
    for entry in entries:
        if type(entry.get('name')) is not str:
            raise ComparisonBlocked('INVALID_NATIVE_INVENTORY')
        if safe_file(Path(root), entry['name']).stat().st_size != entry['bytes']:
            raise ArtifactInvalid('Actual source size differs from signed inventory')
    return sum(sizes)


def _check_source(root, manifest):
    if (type(manifest) is not dict or manifest.get('engine') != 'sqdmetal_palace' or
            manifest.get('artifact_type') != 'palace.eigenmodes' or
            not ID.fullmatch(str(manifest.get('revision_id', ''))) or
            not SHA.fullmatch(str(manifest.get('project_digest', ''))) or
            not STUDY.fullmatch(str(manifest.get('study_id', '')))):
        raise ComparisonBlocked('VERIFIED_EIGENMODE_SOURCE_REQUIRED')
    total = enforce_source_budgets(root, manifest)
    disk = _json(root/'RESULT_MANIFEST.json', upstream.MAX_MANIFEST_BYTES)
    if disk != manifest:
        raise ArtifactInvalid('Source manifest identity changed')
    ref = verify_manifest(root, revision_id=manifest['revision_id'],
                          project_digest=manifest['project_digest'],
                          study_id=manifest['study_id'], engine='sqdmetal_palace')
    return ref.manifest_sha256, total


def _physics_deck(root, manifest):
    names = {e['name'] for e in manifest['artifacts']}
    required = ('sqe_em/sqe_em.msh', 'sqe_em/sqe_em.json', 'sqe_em/outputFiles/eig.csv')
    if not set(required) <= names:
        raise ComparisonBlocked('MESH_DECK_AND_EIGENMODES_REQUIRED')
    config = _json(safe_file(root, required[1]), 2 * 1024**2)
    l0 = config.get('Model', {}).get('L0')
    if (config.get('Problem', {}).get('Type') != 'Eigenmode' or
            config.get('Model', {}).get('Mesh') != 'sqe_em.msh' or
            type(l0) not in (int, float) or not math.isfinite(l0) or not 1e-12 <= l0 <= 1):
        raise ComparisonBlocked('EXPLICIT_NATIVE_COORDINATE_UNITS_REQUIRED')
    normalized = deepcopy(config)
    normalized['Problem'].pop('Output', None)
    normalized['Model'].pop('Refinement', None)
    hashes = {e['name']: e['sha256'] for e in manifest['artifacts']}
    return float(l0), digest(normalized), {k: hashes[k] for k in required}


def prepare_request(roots, manifests, models, study_ids, *, same_frame=False,
                    cycle_indices=(None, None)):
    """Trusted caller supplies stored models/paths, never frontend paths."""
    if same_frame is not True:
        raise ComparisonBlocked('EXPLICIT_SAME_FRAME_ASSUMPTION_REQUIRED')
    if any(len(items) != 2 for items in (roots, manifests, models, study_ids, cycle_indices)):
        raise ComparisonBlocked('TWO_SAVED_SOURCES_REQUIRED')
    if any(index is not None and (type(index) is not int or not 0 <= index < 12)
           for index in cycle_indices):
        raise ComparisonBlocked('INVALID_OUTPUT_CYCLE_SELECTION')
    roots = [Path(p).resolve(strict=True) for p in roots]
    if roots[0] == roots[1]:
        raise ComparisonBlocked('DISTINCT_SAVED_SOURCES_REQUIRED')
    signatures = []; total = 0; decks = []; tables = []
    for root, manifest, model, study, index in zip(roots, manifests, models, study_ids, cycle_indices):
        if manifest.get('study_id') != study or digest(model) != manifest.get('project_digest'):
            raise ArtifactInvalid('Stored project does not match native result')
        expected, size = _check_source(root, manifest); total += size
        if total > MAX_PAIR_BYTES:
            raise ComparisonBlocked('PAIRED_SOURCE_BYTE_BUDGET')
        decks.append(_physics_deck(root, manifest))
        tables.append(palace_eigenmodes(root, manifest))
        signatures.append({'root': str(root), 'manifest_sha256': expected, 'cycle_index': index})
    comparison = compare_palace_modes(tables[0], tables[1], models[0], models[1], *study_ids)
    if comparison['status'] != 'native_mode_index_differences_for_expert_review':
        raise ComparisonBlocked('SAVED_NONMESH_INPUTS_DIFFER')
    if manifests[0]['engine_version'] != manifests[1]['engine_version']:
        raise ComparisonBlocked('NATIVE_ENGINE_VERSIONS_DIFFER')
    if decks[0][:2] != decks[1][:2]:
        raise ComparisonBlocked('NATIVE_DECK_PHYSICS_OR_UNITS_DIFFER')
    if decks[0][2]['sqe_em/sqe_em.msh'] == decks[1][2]['sqe_em/sqe_em.msh']:
        raise ComparisonBlocked('DISTINCT_NATIVE_MESHES_REQUIRED')
    return {'schema': 'sqe.private-field-comparison-request.v1', 'sources': signatures,
            'coordinate_assumption': ASSUMPTION, 'deck_physics_sha256': decks[0][1]}


def _vtk_grid(root, cycle):
    import vtk
    reader = vtk.vtkXMLPUnstructuredGridReader()
    reader.SetFileName(str(root/cycle['pvtu'])); reader.Update()
    if reader.GetErrorCode() or reader.GetOutput() is None:
        raise ComparisonBlocked('UPSTREAM_PARALLEL_READER_ERROR')
    grid = reader.GetOutput()
    if not 0 < grid.GetNumberOfCells() <= MAX_CELLS or not 0 < grid.GetNumberOfPoints() <= MAX_POINTS:
        raise ComparisonBlocked('NATIVE_GRID_SIZE_BUDGET')
    remove = vtk.vtkRemoveGhosts(); remove.SetInputData(grid); remove.Update()
    cleaned = remove.GetOutput()
    ghost_count = grid.GetNumberOfCells() - cleaned.GetNumberOfCells()
    if cleaned.GetNumberOfCells() <= 0:
        raise ComparisonBlocked('NO_NONGHOST_FIELD_CELLS')
    return cleaned, ghost_count


def _cell_type_array(grid):
    """Prefer the current per-cell getter; retain VTK's older overload API."""
    current=getattr(grid,'GetCellTypes',None)
    array=None
    if callable(current):
        try:array=current()
        except TypeError:pass  # VTK 9.3 GetCellTypes(vtkCellTypes) needs an argument.
    if array is None:
        legacy=getattr(grid,'GetCellTypesArray',None)
        if callable(legacy):array=legacy()
    if array is None:raise ComparisonBlocked('CELL_TYPES_ARRAY_UNAVAILABLE')
    return array


def _metadata_values(array, kind, expected_size):
    """Use native DeepCopy to materialize bounded implicit metadata arrays."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    if array is None:raise ComparisonBlocked('CELL_METADATA_ARRAY_UNAVAILABLE')
    if (type(expected_size) is not int or not 0 < expected_size <= 4*MAX_CELLS+1 or
            array.GetNumberOfComponents()!=1 or array.GetNumberOfTuples()!=expected_size):
        raise ComparisonBlocked('INVALID_CELL_METADATA_SHAPE')
    if kind=='types':
        if array.GetDataType()!=vtk.VTK_UNSIGNED_CHAR:
            raise ComparisonBlocked('INVALID_CELL_TYPE_ARRAY_TYPE')
        materialized=vtk.vtkUnsignedCharArray()
    elif kind=='indices':
        allowed={vtk.VTK_INT,vtk.VTK_UNSIGNED_INT,vtk.VTK_LONG,vtk.VTK_UNSIGNED_LONG,
                 vtk.VTK_LONG_LONG,vtk.VTK_UNSIGNED_LONG_LONG,vtk.VTK_ID_TYPE}
        if array.GetDataType() not in allowed:raise ComparisonBlocked('NONINTEGER_CELL_METADATA')
        materialized=vtk.vtkIdTypeArray()
    else:raise ComparisonBlocked('INVALID_CELL_METADATA_KIND')
    materialized.DeepCopy(array)
    # Independent bounded ownership, including for implicit/constant VTK arrays.
    return vtk_to_numpy(materialized).copy()


def _grid_description(grid):
    """Native array metadata only; never coordinates or field samples."""
    import numpy as np
    count, points = grid.GetNumberOfCells(), grid.GetNumberOfPoints()
    if not 0 < count <= MAX_CELLS or not 0 < points <= MAX_POINTS:
        raise ComparisonBlocked('NATIVE_GRID_SIZE_BUDGET')
    types = _metadata_values(_cell_type_array(grid),'types',count)
    offsets = _metadata_values(grid.GetCells().GetOffsetsArray(),'indices',count+1)
    connectivity = grid.GetCells().GetConnectivityArray()
    if connectivity is None or connectivity.GetNumberOfComponents()!=1:
        raise ComparisonBlocked('CELL_METADATA_ARRAY_UNAVAILABLE')
    slots = connectivity.GetNumberOfTuples()
    if (types.shape != (count,) or offsets.shape != (count+1,) or
            int(offsets[0]) != 0 or int(offsets[-1]) != slots):
        raise ComparisonBlocked('INVALID_NATIVE_CELL_TOPOLOGY')
    nodes = np.diff(offsets)
    if np.any(nodes <= 0) or np.any(nodes > 4096):
        raise ComparisonBlocked('INVALID_NATIVE_CELL_TOPOLOGY')
    unique, counts = np.unique(types, return_counts=True)
    if len(unique) > 16:
        raise ComparisonBlocked('CELL_TYPE_VOCABULARY_BUDGET')
    lower, upper = int(np.min(nodes)), int(np.max(nodes))
    family = {int(t) for t in unique}
    view = ('NATIVE_LINEAR_TETRA' if family == {10} and lower == upper == 4 else
            'ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW' if family <= {10,71} and lower == upper == 4
            else 'UNSUPPORTED_CELL_GEOMETRY')
    if view!='UNSUPPORTED_CELL_GEOMETRY':
        ids=_metadata_values(connectivity,'indices',4*count)
        if np.min(ids)<0 or np.max(ids)>=points:
            raise ComparisonBlocked('INVALID_NATIVE_CELL_TOPOLOGY')
    return {'cell_count':count, 'point_count':points, 'nodes_per_cell_min':lower,
            'nodes_per_cell_max':upper, 'geometry_view':view,
            'cell_types':[{'vtk_type_id':int(t),'count':int(n)} for t,n in zip(unique,counts)]}


def _linear_geometry_view(grid, description=None):
    """Only four-node VTK 10/71 cells have the identical linear geometry.

    VTK/MFEM specify the same vertex ordering for order-one Lagrange cells.
    Preserve every array and connectivity entry; the original grid is probed.
    """
    import vtk
    description = description or _grid_description(grid)
    if description['geometry_view'] == 'UNSUPPORTED_CELL_GEOMETRY':
        raise ComparisonBlocked('LINEAR_TETRAHEDRA_REQUIRED')
    if description['geometry_view'] == 'NATIVE_LINEAR_TETRA':
        return grid
    view = vtk.vtkUnstructuredGrid(); view.ShallowCopy(grid)
    view.SetCells(vtk.VTK_TETRA, grid.GetCells())
    return view


def _prepare_grid(grid, description=None):
    import vtk
    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy
    geometry = _linear_geometry_view(grid, description)
    for name in ('E_real', 'E_imag'):
        array = grid.GetPointData().GetArray(name)
        if (array is None or array.GetNumberOfComponents() != 3 or
                array.GetNumberOfTuples() != grid.GetNumberOfPoints() or
                array.GetDataType() not in (vtk.VTK_FLOAT, vtk.VTK_DOUBLE)):
            raise ComparisonBlocked('COMPLEX_POINTDATA_E_REQUIRED')
        if not np.isfinite(vtk_to_numpy(array)).all():
            raise ComparisonBlocked('NONFINITE_NATIVE_FIELD_VALUES')
    quality = vtk.vtkMeshQuality(); quality.SetInputData(geometry)
    quality.SetTetQualityMeasureToScaledJacobian(); quality.Update()
    values = vtk_to_numpy(quality.GetOutput().GetCellData().GetArray('Quality'))
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ComparisonBlocked('INVALID_OR_INVERTED_TETRAHEDRON')
    sizes = vtk.vtkCellSizeFilter(); sizes.SetInputData(geometry)
    sizes.ComputeVertexCountOff(); sizes.ComputeLengthOff(); sizes.ComputeAreaOff()
    sizes.ComputeVolumeOn(); sizes.SetVolumeArrayName('SQE_CellVolume'); sizes.Update()
    volume = np.array(vtk_to_numpy(sizes.GetOutput().GetCellData().GetArray('SQE_CellVolume')), copy=True)
    if volume.shape != (grid.GetNumberOfCells(),) or not np.isfinite(volume).all() or np.any(volume <= 0):
        raise ComparisonBlocked('INVALID_NATIVE_CELL_VOLUME')
    centers = vtk.vtkCellCenters(); centers.SetInputData(geometry)
    # ResampleWithDataSet also marks cell ghosts. Give every sample a vertex
    # cell: point-only PolyData crashes its ghost-marking path in VTK 9.3.1.
    centers.CopyArraysOff(); centers.VertexCellsOn(); centers.Update()
    if centers.GetOutput().GetNumberOfPoints() != grid.GetNumberOfCells():
        raise ComparisonBlocked('CELL_CENTER_COUNT_MISMATCH')
    return volume, centers.GetOutput()


def _sample(grid, points, tolerance):
    import vtk
    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy
    probe = vtk.vtkResampleWithDataSet(); probe.SetInputData(points); probe.SetSourceData(grid)
    locator = vtk.vtkStaticCellLocator()
    probe.SetCellLocatorPrototype(locator)
    probe.SetComputeTolerance(False); probe.SetTolerance(tolerance)
    probe.SetSnapToCellWithClosestPoint(False)
    probe.PassPointArraysOff(); probe.PassCellArraysOff(); probe.PassFieldArraysOff()
    probe.Update()
    if probe.GetErrorCode():
        raise ComparisonBlocked('UPSTREAM_SAMPLING_ERROR')
    data = probe.GetOutput().GetPointData()
    valid = data.GetArray('vtkValidPointMask')
    if valid is None or valid.GetNumberOfTuples() != points.GetNumberOfPoints() or not np.all(vtk_to_numpy(valid) == 1):
        raise ComparisonBlocked('INCOMPLETE_CROSS_MESH_COVERAGE')
    arrays = [data.GetArray(name) for name in ('E_real', 'E_imag')]
    if any(a is None or a.GetNumberOfComponents() != 3 for a in arrays):
        raise ComparisonBlocked('UPSTREAM_SAMPLED_FIELD_MISSING')
    values = np.asarray(vtk_to_numpy(arrays[0]), dtype=float) + 1j*np.asarray(vtk_to_numpy(arrays[1]), dtype=float)
    if values.shape != (points.GetNumberOfPoints(), 3) or not np.isfinite(values).all():
        raise ComparisonBlocked('NONFINITE_SAMPLED_FIELD_VALUES')
    return values


def weighted_mac(left, right, volume):
    """Published discrete Hermitian MAC with positive volume weights."""
    import numpy as np
    if (left.shape != right.shape or left.ndim != 2 or left.shape[1] != 3 or
            volume.shape != (len(left),) or not np.isfinite(volume).all() or np.any(volume <= 0) or
            not np.isfinite(left).all() or not np.isfinite(right).all()):
        raise ComparisonBlocked('INVALID_WEIGHTED_SAMPLE_ARRAYS')
    scales = [float(np.max(np.abs(x))) for x in (left, right)]
    if any(not math.isfinite(x) or x <= 0 for x in scales):
        raise ComparisonBlocked('ZERO_OR_INVALID_FIELD_NORM')
    total = float(np.sum(volume))
    if not math.isfinite(total) or total <= 0:
        raise ComparisonBlocked('INVALID_TOTAL_VOLUME')
    weights = np.sqrt(volume/total)[:, None]
    a, b = weights*(left/scales[0]), weights*(right/scales[1])
    aa, bb, ab = np.vdot(a, a).real, np.vdot(b, b).real, np.vdot(a, b)
    if not math.isfinite(aa) or not math.isfinite(bb) or aa <= 0 or bb <= 0:
        raise ComparisonBlocked('ZERO_OR_INVALID_FIELD_NORM')
    correlation = ab/math.sqrt(aa*bb)
    squared = float(abs(correlation)**2)
    if not math.isfinite(squared) or squared > 1+1e-10:
        raise ComparisonBlocked('CORRELATION_OUTSIDE_CAUCHY_SCHWARZ_BOUND')
    return min(1., squared), (float(np.angle(correlation)) if abs(correlation)>1e-14 else None)


def component_diagnostics(left, right, volume):
    """Inspect XYZ with the existing MAC; fractions are sample norms, not energy."""
    import numpy as np
    weighted_mac(left, right, volume)  # Reuse the existing complete input guards.
    fractions=[]
    weights=np.sqrt(volume/float(np.sum(volume)))[:,None]
    for field in (left,right):
        scaled=weights*(field/float(np.max(np.abs(field))))
        norms=np.asarray([np.vdot(scaled[:,k],scaled[:,k]).real for k in range(3)])
        fractions.append(norms/float(np.sum(norms)))
    rows=[]
    for k,axis in enumerate(('x','y','z')):
        a,b=(float(f[k]) for f in fractions)
        row={'axis':axis,'left_volume_norm_fraction':a,'right_volume_norm_fraction':b,
             'status':'ZERO_OR_UNRESOLVED_COMPONENT_NORM','mac':None,'relative_phase_rad':None}
        if a>0 and b>0:
            restricted=[np.zeros_like(field) for field in (left,right)]
            restricted[0][:,k]=left[:,k];restricted[1][:,k]=right[:,k]
            value,phase=weighted_mac(*restricted,volume)
            row.update(status='SAMPLED_COMPONENT_CORRELATION_RECORDED',mac=value,relative_phase_rad=phase)
            del restricted
        rows.append(row)
    validate_component_diagnostics(rows)
    return rows


def validate_component_diagnostics(rows):
    """Fixed scalar vocabulary; return reconstructed squared vector correlation."""
    keys={'axis','left_volume_norm_fraction','right_volume_norm_fraction','status','mac','relative_phase_rad'}
    if type(rows) is not list or len(rows)!=3:
        raise ValueError('Three fixed component records required')
    total=[0.,0.];correlation=0j
    def number(v):return type(v) in (int,float) and math.isfinite(v)
    for axis,row in zip(('x','y','z'),rows):
        if type(row) is not dict or set(row)!=keys or row['axis']!=axis:
            raise ValueError('Invalid component vocabulary or frame axis')
        a,b=row['left_volume_norm_fraction'],row['right_volume_norm_fraction']
        if any(not number(v) or not 0<=v<=1 for v in (a,b)):
            raise ValueError('Invalid component sample norm fraction')
        total[0]+=a;total[1]+=b
        if a==0 or b==0:
            if (row['status']!='ZERO_OR_UNRESOLVED_COMPONENT_NORM' or
                    row['mac'] is not None or row['relative_phase_rad'] is not None):
                raise ValueError('Unresolved component norm cannot carry correlation')
        else:
            value,phase=row['mac'],row['relative_phase_rad']
            if (row['status']!='SAMPLED_COMPONENT_CORRELATION_RECORDED' or
                    not number(value) or not 0<=value<=1 or
                    ((value<=1e-28)!=(phase is None)) or
                    phase is not None and (not number(phase) or abs(phase)>math.pi)):
                raise ValueError('Invalid component correlation or phase')
            if phase is not None:
                magnitude=math.sqrt(a*b*value)
                correlation+=magnitude*complex(math.cos(phase),math.sin(phase))
    if any(abs(v-1)>1e-12 for v in total):
        raise ValueError('Component sample norm fractions must sum to one')
    return float(abs(correlation)**2)


def _read_side(item, grid_diagnostics):
    root = Path(item['root']).resolve(strict=True)
    manifest = _json(root/'RESULT_MANIFEST.json', upstream.MAX_MANIFEST_BYTES)
    actual, _ = _check_source(root, manifest)
    if actual != item['manifest_sha256']:
        raise ArtifactInvalid('Manifest changed before field comparison')
    l0, physics, hashes = _physics_deck(root, manifest)
    signed = upstream._signed_inventory(root, root/'RESULT_MANIFEST.json')
    pvds = [name for name in signed if name.endswith('/eigenmode/eigenmode.pvd')]
    if len(pvds) != 1:
        raise ComparisonBlocked('EIGENMODE_PVD_NOT_UNAMBIGUOUS')
    cycles = upstream._references(root, signed, pvds[0])
    backend, details = upstream._vtk_probe(root, cycles)
    categorical = upstream._diagnostic(cycles, backend, details)
    index = item['cycle_index']
    if index is None:
        candidates = [c['cycle_index_not_mode_identity'] for c in categorical['cycles']
                      if c['role'] == 'COMPLEX_E_FIELD']
        if len(candidates) != 1 or any(c['role'] not in ('COMPLEX_E_FIELD', 'AUXILIARY_MESH_DATA')
                                       for c in categorical['cycles']):
            raise ComparisonBlocked('EXPLICIT_FIELD_CYCLE_SELECTION_REQUIRED')
        index = candidates[0]
    if (type(index) is not int or not 0 <= index < len(cycles) or
            categorical['cycles'][index]['role'] != 'COMPLEX_E_FIELD'):
        raise ComparisonBlocked('SELECTED_OUTPUT_IS_NOT_COMPLEX_E')
    grid, ghosts = _vtk_grid(root, cycles[index])
    description = _grid_description(grid)
    grid_diagnostics.append({'side':'left' if not grid_diagnostics else 'right',
        'result_manifest_sha256':actual, 'cycle_index':index, **description})
    volume, centers = _prepare_grid(grid, description)
    source = {'result_manifest_sha256': actual, 'revision_id': manifest['revision_id'],
              'project_sha256': manifest['project_digest'], 'study_id': manifest['study_id'],
              'mesh_sha256': hashes['sqe_em/sqe_em.msh'],
              'eig_sha256': hashes['sqe_em/outputFiles/eig.csv'],
              'pvd_sha256': signed[pvds[0]][1], 'cycle_index': index,
              'mpi_piece_count': cycles[index]['piece_count'],
              'piece_sha256': [signed[name][1] for name in cycles[index]['pieces']],
              'cell_count': grid.GetNumberOfCells(), 'point_count': grid.GetNumberOfPoints(),
              'ghost_cells_removed': ghosts, 'declared_length_unit_m': l0}
    return {'root': root, 'manifest': manifest, 'source': source, 'grid': grid,
            'volume': volume, 'centers': centers, 'physics': physics}


def run_request(request, *, grid_diagnostics=None):
    """Native worker algorithm; request is generated by the trusted parent."""
    import vtk
    import numpy as np
    if (type(request) is not dict or request.get('schema') != 'sqe.private-field-comparison-request.v1' or
            request.get('coordinate_assumption') != ASSUMPTION or
            type(request.get('sources')) is not list or len(request['sources']) != 2):
        raise ComparisonBlocked('INVALID_PRIVATE_COMPARISON_REQUEST')
    vtk.vtkSMPTools.Initialize(1)
    grids = [] if grid_diagnostics is None else grid_diagnostics
    sides = [_read_side(item, grids) for item in request['sources']]
    if any(s['physics'] != request['deck_physics_sha256'] for s in sides):
        raise ArtifactInvalid('Deck physics changed')
    if sides[0]['source']['mesh_sha256'] == sides[1]['source']['mesh_sha256']:
        raise ComparisonBlocked('DISTINCT_NATIVE_MESHES_REQUIRED')
    units = [s['source']['declared_length_unit_m'] for s in sides]
    if units[0] != units[1]:
        raise ComparisonBlocked('NATIVE_COORDINATE_UNITS_DIFFER')
    bounds = [np.asarray(s['grid'].GetBounds(), dtype=float) for s in sides]
    if any(not np.isfinite(b).all() for b in bounds):
        raise ComparisonBlocked('INVALID_NATIVE_COORDINATE_BOUNDS')
    diagonal = float(np.linalg.norm(bounds[0][1::2]-bounds[0][::2]))
    if diagonal <= 0 or not np.allclose(bounds[0], bounds[1], rtol=0, atol=1e-8*diagonal):
        raise ComparisonBlocked('NATIVE_DOMAIN_BOUNDS_DIFFER')
    totals = [float(np.sum(s['volume'])) for s in sides]
    if any(not math.isfinite(v) or v <= 0 for v in totals) or abs(totals[0]-totals[1])/max(totals) > 1e-6:
        raise ComparisonBlocked('NATIVE_DOMAIN_VOLUMES_DIFFER')
    result = _base(RECORDED, 'DISCRETE_STATISTIC_ONLY_NOT_MODE_IDENTIFICATION')
    result['grid_diagnostics'] = list(grids)
    for index, side in enumerate(sides):
        samples = [_sample(s['grid'], side['centers'], 1e-10*diagonal) for s in sides]
        value, phase = weighted_mac(samples[0], samples[1], side['volume'])
        result['directions'].append({'sampling_mesh': 'left' if index == 0 else 'right',
            'mac': value, 'relative_phase_rad': phase,
            'sample_count': len(side['volume']), 'coverage_fraction': 1.,
            'sampled_volume_m3_assuming_declared_units': totals[index]*units[index]**3,
            'components':component_diagnostics(samples[0],samples[1],side['volume'])})
        del samples
    # Full manifests, not merely the sampled field pieces, are checked again.
    for side in sides:
        actual, _ = _check_source(side['root'], side['manifest'])
        if actual != side['source']['result_manifest_sha256']:
            raise ArtifactInvalid('Manifest changed during field comparison')
    result['sources'] = [s['source'] for s in sides]
    result['vtk_version'] = vtk.vtkVersion.GetVTKVersion()
    result['mac_gap'] = abs(result['directions'][0]['mac']-result['directions'][1]['mac'])
    validate_result(result)
    return result


def validate_result(result):
    """Strict bounded, categorical/scalar DTO; no coordinates or vectors."""
    base = _base()
    if type(result) is dict and result.get('schema') == LEGACY_SCHEMA:
        base.pop('grid_diagnostics'); base['schema'] = LEGACY_SCHEMA
    elif type(result) is dict and result.get('schema') == CELL_SCHEMA:
        base['schema'] = CELL_SCHEMA
    if type(result) is not dict or set(result) != set(base):
        raise ValueError('Invalid field-comparison response vocabulary')
    for key in ('schema', 'method', 'coordinate_assumption', 'physical_mode_identity',
                'mesh_convergence', 'scientific_qualification', 'material_weighting',
                'em_to_hamiltonian', 'fabrication', 'field_values_exported'):
        if type(result[key]) is not type(base[key]) or result[key] != base[key]:
            raise ValueError('Invalid field-comparison science boundary')
    if result['status'] not in (RECORDED, 'BLOCKED', 'FAIL') or not CODE.fullmatch(str(result['reason_code'])):
        raise ValueError('Invalid comparison status')
    if 'grid_diagnostics' in result:
        validate_grid_diagnostics(result['grid_diagnostics'],
                                  sources=result['sources'] if result['status']==RECORDED else None)
    if result['status'] != RECORDED:
        if result['sources'] != [] or result['directions'] != [] or result['mac_gap'] is not None or result['vtk_version'] is not None:
            raise ValueError('Blocked comparison cannot contain numerical evidence')
        return result
    if (type(result['sources']) is not list or len(result['sources']) != 2 or
            type(result['directions']) is not list or len(result['directions']) != 2 or
            type(result['vtk_version']) is not str or not re.fullmatch(r'[0-9A-Za-z_.+-]{1,32}',result['vtk_version'])):
        raise ValueError('Invalid numerical comparison dimensions')
    source_keys = {'result_manifest_sha256','revision_id','project_sha256','study_id',
                   'mesh_sha256','eig_sha256','pvd_sha256','cycle_index','mpi_piece_count',
                   'piece_sha256','cell_count','point_count','ghost_cells_removed','declared_length_unit_m'}
    def number(x): return type(x) in (float,int) and math.isfinite(x)
    for s in result['sources']:
        if type(s) is not dict or set(s) != source_keys:
            raise ValueError('Invalid comparison source')
        if any(type(s[k]) is not str or not SHA.fullmatch(s[k]) for k in ('result_manifest_sha256','project_sha256','mesh_sha256','eig_sha256','pvd_sha256')):
            raise ValueError('Invalid comparison source hash')
        if (type(s['revision_id']) is not str or not ID.fullmatch(s['revision_id']) or
                type(s['study_id']) is not str or not STUDY.fullmatch(s['study_id'])):
            raise ValueError('Invalid source revision/study')
        for key,lo,hi in (('cycle_index',0,11),('mpi_piece_count',1,16),('cell_count',1,MAX_CELLS),
                          ('point_count',1,MAX_POINTS),('ghost_cells_removed',0,MAX_CELLS)):
            if type(s[key]) is not int or not lo <= s[key] <= hi:
                raise ValueError('Invalid source dimensions')
        if (type(s['piece_sha256']) is not list or len(s['piece_sha256']) != s['mpi_piece_count'] or
                any(type(h) is not str or not SHA.fullmatch(h) for h in s['piece_sha256']) or
                not number(s['declared_length_unit_m']) or not 1e-12 <= s['declared_length_unit_m'] <= 1):
            raise ValueError('Invalid source pieces/units')
    if (result['sources'][0]['mesh_sha256'] == result['sources'][1]['mesh_sha256'] or
            result['sources'][0]['declared_length_unit_m'] != result['sources'][1]['declared_length_unit_m']):
        raise ValueError('Invalid distinct-mesh coordinate preflight')
    for i,d in enumerate(result['directions']):
        direction_keys={'sampling_mesh','mac','relative_phase_rad','sample_count',
                'coverage_fraction','sampled_volume_m3_assuming_declared_units'}
        if result['schema']==SCHEMA:direction_keys.add('components')
        if type(d) is not dict or set(d) != direction_keys:
            raise ValueError('Invalid sampled statistic')
        if (d['sampling_mesh'] != ('left' if i == 0 else 'right') or
                type(d['sample_count']) is not int or d['sample_count'] != result['sources'][i]['cell_count'] or
                not number(d['coverage_fraction']) or d['coverage_fraction'] != 1 or
                not number(d['mac']) or not 0 <= d['mac'] <= 1 or
                (d['relative_phase_rad'] is not None and
                 (not number(d['relative_phase_rad']) or abs(d['relative_phase_rad']) > math.pi)) or
                ((d['mac']<=1e-28) != (d['relative_phase_rad'] is None)) or
                not number(d['sampled_volume_m3_assuming_declared_units']) or d['sampled_volume_m3_assuming_declared_units'] <= 0):
            raise ValueError('Invalid or incomplete sampled field evidence')
        if result['schema']==SCHEMA:
            reconstructed=validate_component_diagnostics(d['components'])
            if abs(reconstructed-d['mac'])>1e-10:
                raise ValueError('Component evidence disagrees with vector MAC')
    gap = abs(result['directions'][0]['mac']-result['directions'][1]['mac'])
    if not number(result['mac_gap']) or abs(result['mac_gap']-gap) > 1e-12:
        raise ValueError('Invalid bidirectional statistic difference')
    return result


def validate_grid_diagnostics(grids, *, sources=None):
    keys={'side','result_manifest_sha256','cycle_index','cell_count','point_count',
          'nodes_per_cell_min','nodes_per_cell_max','geometry_view','cell_types'}
    if type(grids) is not list or len(grids)>2 or (sources is not None and len(grids)!=2):
        raise ValueError('Invalid grid diagnostic dimensions')
    if sources is not None and (type(sources) is not list or len(sources)!=2 or
            any(type(s) is not dict or not {'result_manifest_sha256','cycle_index','cell_count','point_count'} <= set(s)
                for s in sources)):
        raise ValueError('Invalid numerical grid diagnostic sources')
    for index,g in enumerate(grids):
        if (type(g) is not dict or set(g)!=keys or g['side']!=('right' if index else 'left') or
                type(g['result_manifest_sha256']) is not str or not SHA.fullmatch(g['result_manifest_sha256'])):
            raise ValueError('Invalid grid diagnostic source')
        for key,lo,hi in (('cycle_index',0,11),('cell_count',1,MAX_CELLS),('point_count',1,MAX_POINTS),
                          ('nodes_per_cell_min',1,4096),('nodes_per_cell_max',1,4096)):
            if type(g[key]) is not int or not lo <= g[key] <= hi:
                raise ValueError('Invalid grid diagnostic count')
        if (g['nodes_per_cell_min']>g['nodes_per_cell_max'] or
                type(g['cell_types']) is not list or not 1 <= len(g['cell_types']) <= 16):
            raise ValueError('Invalid cell diagnostic topology')
        types=[];total=0
        for item in g['cell_types']:
            if (type(item) is not dict or set(item)!={'vtk_type_id','count'} or
                    type(item['vtk_type_id']) is not int or not 0 <= item['vtk_type_id'] <= 255 or
                    type(item['count']) is not int or not 1 <= item['count'] <= MAX_CELLS):
                raise ValueError('Invalid native cell-type count')
            types.append(item['vtk_type_id']);total+=item['count']
        if types != sorted(set(types)) or total != g['cell_count']:
            raise ValueError('Inconsistent native cell-type counts')
        family=set(types);linear=g['nodes_per_cell_min']==g['nodes_per_cell_max']==4
        expected=('NATIVE_LINEAR_TETRA' if family=={10} and linear else
                  'ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW' if family <= {10,71} and linear
                  else 'UNSUPPORTED_CELL_GEOMETRY')
        if g['geometry_view']!=expected:
            raise ValueError('Unproved linear geometry view')
        if sources is not None:
            s=sources[index]
            if (expected=='UNSUPPORTED_CELL_GEOMETRY' or any(g[k]!=s[k] for k in
                    ('result_manifest_sha256','cycle_index','cell_count','point_count'))):
                raise ValueError('Grid diagnostic differs from numerical source')
    return grids


def compare_verified_fields(roots, manifests, models, study_ids, *, same_frame=False,
                            cycle_indices=(None,None)):
    """Run a bounded native worker after the caller's normal saved-run checks."""
    try:
        request = prepare_request(roots, manifests, models, study_ids,
                                  same_frame=same_frame, cycle_indices=cycle_indices)
        with tempfile.TemporaryDirectory(prefix='sqe-field-correlation-') as td:
            path = Path(td)/'request.json'
            path.write_text(json.dumps(request),encoding='utf-8')
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
                       OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
            done = subprocess.run([sys.executable,'-m',__name__,'--request',str(path)],
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=TIMEOUT_S,
                check=False,text=True,encoding='utf-8',env=env)
            if done.returncode != 0:
                return _base('FAIL','NATIVE_FIELD_WORKER_EXITED')
            if len(done.stdout) > 128*1024:
                return _base('FAIL','COMPARISON_OUTPUT_BUDGET')
            result = validate_result(json.loads(done.stdout))
            for expected,grid in zip(request['sources'],result.get('grid_diagnostics',[])):
                if (grid['result_manifest_sha256'] != expected['manifest_sha256'] or
                        expected['cycle_index'] is not None and grid['cycle_index'] != expected['cycle_index']):
                    return _base('FAIL','FOREIGN_COMPARISON_SOURCE')
            if result['status'] == RECORDED:
                for expected,actual,manifest in zip(request['sources'],result['sources'],manifests):
                    hashes = {e['name']:e['sha256'] for e in manifest['artifacts']}
                    if (expected['manifest_sha256'] != actual['result_manifest_sha256'] or
                            actual['revision_id'] != manifest['revision_id'] or
                            actual['project_sha256'] != manifest['project_digest'] or
                            actual['study_id'] != manifest['study_id'] or
                            actual['mesh_sha256'] != hashes['sqe_em/sqe_em.msh'] or
                            actual['eig_sha256'] != hashes['sqe_em/outputFiles/eig.csv'] or
                            expected['cycle_index'] is not None and expected['cycle_index'] != actual['cycle_index']):
                        return _base('FAIL','FOREIGN_COMPARISON_SOURCE')
            return result
    except ComparisonBlocked as exc:
        return _base('BLOCKED',str(exc))
    except upstream.ProbeBlocked as exc:
        return _base('BLOCKED',exc.code)
    except ArtifactInvalid:
        return _base('FAIL','SOURCE_CONTENT_OR_REVISION_INVALID')
    except subprocess.TimeoutExpired:
        return _base('BLOCKED','NATIVE_FIELD_COMPARISON_TIMEOUT')
    except (OSError,ValueError,TypeError,KeyError):
        return _base('FAIL','NATIVE_FIELD_COMPARISON_INVALID')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True)
    args=parser.parse_args()
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(TIMEOUT_S+3,TIMEOUT_S+5))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    grids=[]
    try:
        result=run_request(_json(args.request,16000),grid_diagnostics=grids)
    except ImportError:
        result=_base('BLOCKED','UPSTREAM_VTK_OR_NUMPY_NOT_INSTALLED')
    except (ComparisonBlocked,upstream.ProbeBlocked) as exc:
        result=_base('BLOCKED',str(exc),grid_diagnostics=grids)
    except ArtifactInvalid:
        result=_base('FAIL','SOURCE_CHANGED_DURING_COMPARISON')
    except Exception:
        result=_base('FAIL','UPSTREAM_FIELD_COMPARISON_FAILED')
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__ == '__main__':
    main()
