"""M14: oversized VTU header handling is bounded and not physical evidence.

These are synthetic software-format fixtures, NOT real Palace fields or solves.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sqe_studio.eda.field_lineage import inspect_verified_run_field_lineage
from sqe_studio.interop.native_field import MAX_VTU_HEADER_BYTES, _vtu_header


def _vtu(*, gap=0, appended=True, corrupt=False):
    data = (b'<VTKFile type="UnstructuredGrid"><UnstructuredGrid>'
            b'<Piece NumberOfPoints="4" NumberOfCells="1"><PointData>'
            b'<DataArray Name="E_real" NumberOfComponents="3" type="Float64"/>'
            b'<DataArray Name="E_imag" NumberOfComponents="3" type="Float64"/>'
            b'</PointData></Piece></UnstructuredGrid>')
    if corrupt:
        data = data.replace(b'</UnstructuredGrid>', b'</WrongGrid>')
    return (data + b' ' * gap +
            (b'<AppendedData encoding="raw">_\x00\xff\x01\x02</AppendedData>' if appended else b'') +
            b'</VTKFile>')


def _saved_run(root: Path, vtu: bytes):
    base='sqe_em/outputFiles/paraview/eigenmode/'
    files={
        'sqe_em/sqe_em.json': json.dumps({
            'Problem': {'Type': 'Eigenmode', 'OutputFormats': {'Paraview': True}},
            'Model': {'Mesh':'sqe_em.msh','L0':0.001},
            'Solver': {'Eigenmode': {'Save': 1,'N': 1}}}).encode(),
        'sqe_em/sqe_em.msh': b'nonphysical-m14-mesh-fixture',
        'sqe_em/outputFiles/eig.csv': b'm,f (GHz),Im(f) (GHz),Q\n1,5.9,0.0,359000\n',
        base+'eigenmode.pvd': (b'<VTKFile type="Collection"><Collection>'
             b'<DataSet file="Cycle000001/data.pvtu"/></Collection></VTKFile>'),
        base+'Cycle000001/data.pvtu': (b'<VTKFile type="PUnstructuredGrid">'
             b'<PUnstructuredGrid><Piece Source="proc000000.vtu"/>'
             b'</PUnstructuredGrid></VTKFile>'),
        base+'Cycle000001/proc000000.vtu': vtu,
    }
    artifacts=[]
    for name, data in files.items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        artifacts.append({'name':name,'bytes':len(data),
                          'sha256':hashlib.sha256(data).hexdigest()})
    return {'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes',
            'artifacts':artifacts}


def test_native_sized_header_crosses_old_two_megabyte_limit_without_field_decode(tmp_path):
    blob=_vtu(gap=2_300_000)
    assert len(blob)>2_000_000
    result=inspect_verified_run_field_lineage(tmp_path,_saved_run(tmp_path,blob))
    assert result['status']=='VERIFIED_FORMAT_LINEAGE_ONLY'
    assert result['field_sample_count']==1
    assert result['physical_mode_identity']=='UNRESOLVED'
    assert result['mesh_convergence']=='NOT_ESTABLISHED'
    assert result['vector_norm_and_phase']=='NOT_ESTABLISHED'
    assert result['fabrication']=='HOLD'


def test_delimiter_straddling_stream_read_boundary_is_found(tmp_path):
    offset=_vtu(gap=0).index(b'<AppendedData')
    gap=512*1024-offset-5
    f=tmp_path/'edge.vtu'
    f.write_bytes(_vtu(gap=gap))
    assert _vtu_header(f)['B_complex_declared'] is False


def test_header_over_explicit_budget_stays_blocked_and_private(tmp_path):
    result=inspect_verified_run_field_lineage(
        tmp_path,_saved_run(tmp_path,_vtu(gap=MAX_VTU_HEADER_BYTES)))
    assert result['status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['diagnostic_code']=='VTU_HEADER_BUDGET'
    assert result['diagnostic_phase']=='piece'
    assert result['field_sample_count']==0
    assert str(tmp_path) not in json.dumps(result)
    assert result['physical_mode_identity']=='UNRESOLVED'


@pytest.mark.parametrize('mutation,code',[
    ('bad_xml','VTU_XML_HEADER_INVALID'),
    ('truncated_binary','VTU_RAW_PAYLOAD_TRUNCATED'),
    ('no_complex_E','VTU_COMPLEX_E_MISSING'),
    ('sha_tamper','ARTIFACT_HASH_MISMATCH'),
])
def test_larger_header_does_not_bypass_existing_security(tmp_path,mutation,code):
    vtu=_vtu(gap=2_200_000,corrupt=mutation=='bad_xml')
    if mutation=='truncated_binary':
        vtu=vtu.replace(b'</AppendedData>',b'')
    if mutation=='no_complex_E':
        vtu=vtu.replace(b'Name="E_imag"',b'Name="E_missing"')
    manifest=_saved_run(tmp_path,vtu)
    if mutation=='sha_tamper':
        path=tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
        with path.open('ab') as f:f.write(b'tampered')
    result=inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['diagnostic_code']==code
    assert result['fabrication']=='HOLD'
    assert str(tmp_path) not in json.dumps(result)


def test_real_report_piece_sizes_remain_inside_bounded_scan_budget():
    # M13 Windows B02 SHA manifest published these byte counts, not payloads.
    # This only establishes budget capacity, NOT an executed Palace decode.
    assert MAX_VTU_HEADER_BYTES>10_546_226
