"""M13 format failures remain actionable, private and scientifically BLOCKED.

Synthetic VTK/XML is a software contract fixture, NOT a Palace solve.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sqe_studio.eda.field_lineage import (SCHEMA,
    inspect_verified_run_field_lineage, _diagnostic_for_native_error)
from sqe_studio.interop.native_field import NativeFieldEvidenceError


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _native_fixture(root: Path, *, corruption: str | None = None):
    files = {
        'sqe_em/sqe_em.json': json.dumps({
            'Problem': {'Type': 'Eigenmode', 'Output': 'outputFiles'},
            'Model': {'Mesh': 'sqe_em.msh', 'L0': 0.001},
            'Solver': {'Eigenmode': {'Save': 1, 'N': 1}}}).encode(),
        'sqe_em/sqe_em.msh': b'software-fixture-not-a-physical-mesh',
        'sqe_em/outputFiles/eig.csv': b'm,Re{f} (GHz),Im{f} (GHz),Q\n1,5.9,0.0,359000\n',
    }
    prefix = 'sqe_em/outputFiles/paraview/eigenmode/'
    files[prefix+'eigenmode.pvd'] = (b'<VTKFile type="Collection"><Collection>'
        b'<DataSet timestep="0" file="Cycle000001/data.pvtu"/>'
        b'<DataSet timestep="1" file="Cycle000002/data.pvtu"/>'
        b'</Collection></VTKFile>')
    for cycle in ('Cycle000001', 'Cycle000002'):
        files[prefix+cycle+'/data.pvtu'] = (
            b'<VTKFile type="PUnstructuredGrid"><PUnstructuredGrid>'
            b'<Piece Source="proc000000.vtu"/><Piece Source="proc000001.vtu"/>'
            b'</PUnstructuredGrid></VTKFile>')
        for idx in range(2):
            files[prefix+cycle+f'/proc{idx:06d}.vtu'] = (
                b'<VTKFile type="UnstructuredGrid"><UnstructuredGrid>'
                b'<Piece NumberOfPoints="4" NumberOfCells="1"><PointData>'
                b'<DataArray Name="E_real" NumberOfComponents="3" type="Float64"/>'
                b'<DataArray Name="E_imag" NumberOfComponents="3" type="Float64"/>'
                b'</PointData></Piece></UnstructuredGrid>'
                b'<AppendedData encoding="raw">_\x00\xff\x01\x02</AppendedData></VTKFile>')
    for path, blob in files.items():
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    artifact_list = [{'name': path, 'sha256': _sha(blob), 'bytes': len(blob)}
                     for path,blob in files.items()]
    if corruption == 'tamper_vtu':
        (root/(prefix+'Cycle000001/proc000000.vtu')).write_bytes(b'changed-after-signing')
    elif corruption == 'missing_complex_e':
        path = prefix+'Cycle000001/proc000000.vtu'
        files[path] = files[path].replace(b'Name="E_imag"',b'Name="E_xxxx"')
        (root/path).write_bytes(files[path])
        artifact_list = [{'name': path, 'sha256': _sha(blob), 'bytes': len(blob)}
                         for path,blob in files.items()]
    elif corruption == 'pvd_xml_invalid':
        path = prefix+'eigenmode.pvd'
        files[path] = b'<VTKFile type="Collection"><Collection>'
        (root/path).write_bytes(files[path])
        artifact_list = [{'name': path, 'sha256': _sha(blob), 'bytes': len(blob)}
                         for path,blob in files.items()]
    elif corruption == 'missing_mpi_piece':
        path = prefix+'Cycle000001/data.pvtu'
        files[path] = files[path].replace(b'proc000001.vtu',b'proc000099.vtu')
        (root/path).write_bytes(files[path])
        artifact_list = [{'name': path, 'sha256': _sha(blob), 'bytes': len(blob)}
                         for path,blob in files.items()]
    return {'engine': 'sqdmetal_palace', 'artifact_type':'palace.eigenmodes',
            'artifacts': artifact_list}


def test_realistic_multicycle_mpi_header_inspection_is_format_only(tmp_path):
    manifest = _native_fixture(tmp_path)
    result = inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status'] == 'VERIFIED_FORMAT_LINEAGE_ONLY'
    assert result['field_sample_count'] == 2
    assert result['mpi_piece_count_by_sample'] == [2,2]
    assert result['output_cycles_not_physical_modes'] == ['Cycle000001','Cycle000002']
    assert result['physical_mode_identity'] == 'UNRESOLVED'
    assert result['mesh_convergence'] == 'NOT_ESTABLISHED'
    assert result['fabrication'] == 'HOLD'
    assert 'diagnostic_code' not in result


@pytest.mark.parametrize(('corruption','code','phase'),[
    ('tamper_vtu', 'ARTIFACT_HASH_MISMATCH', 'inventory'),
    ('missing_complex_e', 'VTU_COMPLEX_E_MISSING', 'piece'),
    ('pvd_xml_invalid', 'PVD_XML_INVALID', 'collection'),
    ('missing_mpi_piece', 'PVTU_UNSIGNED_VTU', 'parallel'),
])
def test_source_failure_code_is_stable_private_and_nonphysics(tmp_path, corruption, code, phase):
    result = inspect_verified_run_field_lineage(tmp_path, _native_fixture(tmp_path, corruption=corruption))
    assert result['schema'] == SCHEMA
    assert result['status'] == 'BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['diagnostic_code'] == code
    assert result['diagnostic_phase'] == phase
    assert result['fabrication'] == 'HOLD'
    assert result['physical_mode_identity'] == 'UNRESOLVED'
    assert result['field_sample_count'] == 0
    assert str(tmp_path) not in json.dumps(result)
    assert '.vtu' not in result['recommended_action'] or 'path' not in result


def test_unexpected_message_does_not_become_untrusted_http_diagnostics():
    secret = 'SENSITIVE_HOST_PATH_OR_FIELD_DATA'
    code,phase,action = _diagnostic_for_native_error(NativeFieldEvidenceError(secret))
    assert code == 'OTHER_NATIVE_FIELD_CONTRACT'
    assert phase == 'inspection'
    assert secret not in action
    code,phase,action = _diagnostic_for_native_error(RuntimeError(secret))
    assert code == 'UNEXPECTED_INSPECTION_EXCEPTION'
    assert secret not in action
