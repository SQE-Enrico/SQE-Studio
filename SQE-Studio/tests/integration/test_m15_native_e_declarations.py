"""M15: safe header-only field metadata, not synthetic solver evidence.

No fixture here is a physical Palace solve. Signatures must remain limited to
fixed published field names, must never leak private arrays or values, and
must leave scientific acceptance gates closed.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from sqe_studio.eda.field_lineage import inspect_verified_run_field_lineage
from sqe_studio.cycle_qualification import _case_from_em
from sqe_studio.interop.native_field import NativeFieldVectorContractError, _vtu_header


def _fixture(root, *, point=True, cell=False, imag=True, kind='Float64', components=3,
             pvtu=True, inject_private=False):
    fields=lambda: (f'<DataArray Name="E_real" type="{kind}" NumberOfComponents="{components}"/>'
                    + ('<DataArray Name="E_imag" type="Float64" NumberOfComponents="3"/>' if imag else '')
                    + ('<DataArray Name="SECRET_HOST_DOCUMENT" type="Float64"/>' if inject_private else ''))
    metadata = (('<PointData>'+fields()+'</PointData>') if point else '<PointData/>')
    if cell:
        metadata += '<CellData>'+fields()+'</CellData>'
    vtu = ('<VTKFile type="UnstructuredGrid"><UnstructuredGrid>'
           '<Piece NumberOfPoints="4" NumberOfCells="1">'+metadata+
           '</Piece></UnstructuredGrid><AppendedData encoding="raw">_').encode()+ (
               b'\x00\xff\x13\x20') + b'</AppendedData></VTKFile>'
    prefix='sqe_em/outputFiles/paraview/eigenmode/'
    pdata = ('<PPointData><PDataArray Name="E_real" type="Float64" NumberOfComponents="3"/>'
             '<PDataArray Name="E_imag" type="Float64" NumberOfComponents="3"/>'
             '</PPointData>') if pvtu else ''
    files={
      'sqe_em/sqe_em.json':json.dumps({'Problem':{'Type':'Eigenmode'},'Model':{'Mesh':'sqe_em.msh','L0':.001},'Solver':{'Eigenmode':{'N':1,'Save':1}}}).encode(),
      'sqe_em/sqe_em.msh':b'non-physical synthetic fixture',
      'sqe_em/outputFiles/eig.csv':b'm,f (GHz)\n1,5.9\n',
      prefix+'eigenmode.pvd':b'<VTKFile type="Collection"><Collection><DataSet file="Cycle000001/data.pvtu"/></Collection></VTKFile>',
      prefix+'Cycle000001/data.pvtu': ('<VTKFile type="PUnstructuredGrid"><PUnstructuredGrid>'+pdata+'<Piece Source="proc000000.vtu"/></PUnstructuredGrid></VTKFile>').encode(),
      prefix+'Cycle000001/proc000000.vtu':vtu,
    }
    artifacts=[]
    for name,blob in files.items():
        f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(blob)
        artifacts.append({'name':name,'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)})
    return {'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes','artifacts':artifacts}


@pytest.mark.parametrize('edit,expected_point,expected_cell',[
    ({'imag':False},'ABSENT','NO_ASSOCIATION'),
    ({'point':False,'cell':True},'ABSENT','FLOAT_VECTOR_3'),
    ({'kind':'Int32'},'NON_FLOAT','NO_ASSOCIATION'),
    ({'components':1},'WRONG_COMPONENT_COUNT','NO_ASSOCIATION'),
    ({'imag':False,'inject_private':True},'ABSENT','NO_ASSOCIATION'),
])
def test_e_declaration_blocker_has_only_fixed_categorical_evidence(tmp_path,edit,expected_point,expected_cell):
    manifest=_fixture(tmp_path, **edit)
    result=inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['diagnostic_code']=='VTU_COMPLEX_E_MISSING'
    d=result['field_declaration_diagnostic']
    assert d['schema']=='sqe.vtu-e-field-declaration.m15.v1'
    observed = d['point']['E_real'] if ('kind' in edit or 'components' in edit) else d['point']['E_imag']
    assert observed == expected_point
    assert d['cell']['E_real']==expected_cell
    assert d['parallel_point']['E_real']=='FLOAT_VECTOR_3'
    assert d['field_values_exported'] is False
    assert d['physical_mode_identity']=='UNRESOLVED'
    assert set(d['point'])=={'E_real','E_imag','E'}
    assert 'SECRET_HOST_DOCUMENT' not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
    assert result['mesh_convergence']=='NOT_ESTABLISHED'
    assert result['fabrication']=='HOLD'


def test_declared_canonical_complex_vectors_still_only_pass_format(tmp_path):
    manifest=_fixture(tmp_path)
    result=inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status']=='VERIFIED_FORMAT_LINEAGE_ONLY'
    assert 'field_declaration_diagnostic' not in result
    assert result['physical_mode_identity']=='UNRESOLVED'
    assert result['fabrication']=='HOLD'


def test_manifest_tamper_rejected_before_metadata_is_reported(tmp_path):
    manifest=_fixture(tmp_path,imag=False)
    (tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu').write_bytes(b'tamper')
    result=inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['diagnostic_code']=='ARTIFACT_HASH_MISMATCH'
    assert 'field_declaration_diagnostic' not in result


def test_raw_vtu_parser_does_not_copy_private_data_into_exception(tmp_path):
    manifest=_fixture(tmp_path,imag=False,inject_private=True)
    path=tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    with pytest.raises(NativeFieldVectorContractError) as info:
        _vtu_header(path)
    assert 'SECRET_HOST_DOCUMENT' not in str(info.value)
    assert 'SECRET_HOST_DOCUMENT' not in json.dumps(info.value.declaration_diagnostic)
    assert 'field_values_exported' in info.value.declaration_diagnostic
