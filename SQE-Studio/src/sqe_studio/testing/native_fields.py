"""Actual upstream API/format checks on a tiny, explicitly synthetic VTK fixture.

No Palace solve, measured device, or scientific field qualification is involved.
SQDMetal supplies the viewer/slice API; VTK writes and reads its own format.
"""
from __future__ import annotations

import hashlib
from importlib import import_module, metadata, util
import inspect
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET


def write_fixture(root: Path):
    """Use the upstream writer, never an SQE binary encoder or decoder."""
    import vtk

    base = root/'sqe_em/outputFiles/paraview/eigenmode'
    for index, fields in ((1, True), (2, False)):
        folder = base/f'Cycle{index:06d}'
        folder.mkdir(parents=True)
        points = vtk.vtkPoints()
        for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
            points.InsertNextPoint(*point)
        grid = vtk.vtkUnstructuredGrid(); grid.SetPoints(points)
        cell = vtk.vtkTetra()
        for i in range(4): cell.GetPointIds().SetId(i, i)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
        if fields:
            for name in ('E_real', 'E_imag'):
                array = vtk.vtkDoubleArray(); array.SetName(name)
                array.SetNumberOfComponents(3)
                for _ in range(4): array.InsertNextTuple3(1., 2., 3.)
                grid.GetPointData().AddArray(array)
        else:
            for name, factory in (('Rank', vtk.vtkIntArray), ('Indicator', vtk.vtkDoubleArray)):
                array = factory(); array.SetName(name); array.InsertNextValue(1)
                grid.GetCellData().AddArray(array)
        path = folder/'data.pvtu'
        writer = vtk.vtkXMLPUnstructuredGridWriter()
        writer.SetFileName(str(path)); writer.SetInputData(grid)
        writer.SetNumberOfPieces(1); writer.SetStartPiece(0); writer.SetEndPiece(0)
        writer.SetDataModeToAppended(); writer.EncodeAppendedDataOff()
        if writer.Write() != 1: raise RuntimeError('VTK_FIXTURE_WRITE_FAILED')
        descriptor = ET.parse(path)
        piece = descriptor.find('./PUnstructuredGrid/Piece')
        (folder/piece.attrib['Source']).rename(folder/'proc000000.vtu')
        piece.attrib['Source'] = 'proc000000.vtu'
        descriptor.write(path, encoding='utf-8', xml_declaration=True)
    pvd = base/'eigenmode.pvd'
    doc = ET.Element('VTKFile', type='Collection', version='0.1')
    collection = ET.SubElement(doc, 'Collection')
    for index in (1, 2):
        ET.SubElement(collection, 'DataSet', timestep=str(index),
                      file=f'Cycle{index:06d}/data.pvtu')
    ET.ElementTree(doc).write(pvd, encoding='utf-8', xml_declaration=True)
    artifacts = [{'name': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
                  'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(base.rglob('*')) if p.is_file()]
    manifest = {'engine': 'sqdmetal_palace', 'artifact_type': 'palace.eigenmodes',
                'fixture_only': True, 'artifacts': artifacts}
    (root/'RESULT_MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest, pvd


def run_workflow():
    required = ('vtk', 'pyvista', 'SQDMetal')
    missing = [name for name in required if util.find_spec(name) is None]
    if 'vtk' in missing:
        return {'status': 'BLOCKED', 'reason': 'UPSTREAM_READER_DEPENDENCIES_MISSING',
                'missing_packages': missing, 'execution_kind': 'NOT_RUN',
                'native_palace_execution': 'NOT_RUN'}
    rows = []
    active_step = 'upstream_fixture_setup'
    private_root = ''
    try:
        # This function runs in the catalog's dedicated compatibility process.
        os.environ.update(QT_QPA_PLATFORM='offscreen', PYVISTA_OFF_SCREEN='true',
                          VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN='1')
        from sqe_studio.eda.upstream_vtk_probe import (
            _child_run, diagnostic_summary, probe_verified_run)
        with tempfile.TemporaryDirectory(prefix='sqe-upstream-fixture-') as td:
            root = Path(td)
            private_root = str(root)
            manifest, pvd = write_fixture(root)
            for backend in ('auto', 'vtk'):
                active_step = 'upstream_reader_'+backend
                # Exercise the ordinary bounded Results reader, plus VTK's own
                # parallel reader on this tiny trusted fixture. The enclosing
                # catalog task bounds the entire compatibility process.
                record = (probe_verified_run(root, manifest) if backend == 'auto' else
                          _child_run(root, root/'RESULT_MANIFEST.json',
                                     pvd.relative_to(root).as_posix(), 'vtk'))
                summary = diagnostic_summary(record)
                good = (summary.get('cycle_roles') == ['COMPLEX_E_FIELD', 'AUXILIARY_MESH_DATA'] and
                        summary['status'] == 'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED')
                rows.append({'id': 'upstream_reader_'+backend, 'status': 'PASS' if good else
                             'BLOCKED' if summary['status'] == 'BLOCKED' else 'FAIL',
                             'diagnostic': record})
                if not good:
                    return {'status': rows[-1]['status'], 'reason': 'UPSTREAM_FIXTURE_READER_NOT_ACCEPTED',
                            'execution_kind': 'NATIVE_SOFTWARE_FIXTURE', 'substeps': rows,
                            'native_palace_execution': 'NOT_RUN',
                            'scientific_qualification': 'NOT_ESTABLISHED'}
            active_step = 'sqdmetal_existing_viewer_and_slice'
            if missing:
                rows.append({'id': active_step, 'status': 'BLOCKED',
                             'reason': 'SQDMETAL_VIEWER_DEPENDENCIES_MISSING', 'missing_packages': missing})
            else:
                import numpy as np
                module = import_module('SQDMetal.PALACE.PVDVTU_Viewer')
                # Fixture coordinates use a unit scale of one; avoid mixing the
                # viewer's millimetre default with a plane expressed in raw units.
                viewer = module.PVDVTU_Viewer(str(pvd), units=1.0)
                section = viewer.get_data_slice(0, slice_plane_normal=np.array([0, 0, 1]),
                                               slice_plane_origin=np.array([0., 0., .25]))
                data = np.asarray(section.get_data('E_real'))
                if data.ndim != 2 or data.shape[0] == 0 or data.shape[1] != 3 or not np.isfinite(data).all():
                    raise ValueError('SQDMETAL_SLICE_FIELD_CONTRACT')
                source = Path(inspect.getfile(module.PVDVTU_Viewer))
                module_hash = (hashlib.sha256(source.read_bytes()).hexdigest()
                               if source.is_file() and source.stat().st_size <= 1_000_000 else None)
                rows.append({'id': active_step, 'status': 'PASS',
                             'apis_reused': ['PVDVTU_Viewer', 'get_data_slice', 'PVDVTU_Slice.get_data'],
                             'source_module_sha256': module_hash,
                             'version': metadata.version('SQDMetal'),
                             'rendering_requested': False, 'field_values_exported': False})
        return {'status': 'BLOCKED' if missing else 'PASS', 'execution_kind': 'NATIVE_SOFTWARE_FIXTURE',
                'reason': 'SQDMETAL_VIEWER_DEPENDENCIES_MISSING' if missing else None,
                'substeps': rows, 'scope': 'upstream API and VTK fixture compatibility only',
                'fixture_generator': 'upstream VTK writer, synthetic tetrahedron',
                'native_palace_execution': 'NOT_RUN',
                'scientific_qualification': 'NOT_ESTABLISHED'}
    except Exception as exc:
        from sqe_studio.qualification import _safe_log
        return {'status': 'FAIL', 'reason': 'UPSTREAM_COMPATIBILITY_'+type(exc).__name__,
                'failed_step': active_step,
                'diagnostic_message': _safe_log(str(exc)[:1000], (private_root, str(Path.home()))),
                'execution_kind': 'NATIVE_SOFTWARE_FIXTURE', 'substeps': rows,
                'native_palace_execution': 'NOT_RUN',
                'scientific_qualification': 'NOT_ESTABLISHED'}
