"""M11 signed saved-field readiness. Synthetic XML is a format fixture, NOT a Palace solve."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import http.cookiejar
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from sqe_studio.eda.field_lineage import (inspect_verified_run_field_lineage,
    compare_verified_field_lineages, PAIR_SCHEMA, SCHEMA)
from sqe_studio.eda.scientific_references import list_reference_cases
from sqe_studio.design_library import instantiate
from sqe_studio.server import make_server


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _field_artifacts(root: Path, *, variant: bytes=b'A', include=True):
    """Small descriptor-only files; an intentional unphysical software fixture."""
    paths = {
        'sqe_em/sqe_em.json': json.dumps({
            'Problem': {'Type': 'Eigenmode','OutputFormats':{'Paraview':True}},
            'Model': {'Mesh':'sqe_em.msh','L0':0.001},
            'Solver': {'Eigenmode':{'N':1,'Save':1}}}).encode(),
        'sqe_em/sqe_em.msh': b'non-physical-mesh-fixture-' + variant,
        'sqe_em/outputFiles/eig.csv': b'm,f (GHz),Im(f) (GHz),Q\n1,5.9,0,359000\n',
    }
    pvd_base = 'sqe_em/outputFiles/paraview/solution/'
    if include:
        paths[pvd_base+'solution.pvd'] = (b'<VTKFile type="Collection"><Collection>'
            b'<DataSet file="Cycle000001/data.pvtu"/></Collection></VTKFile>')
        paths[pvd_base+'Cycle000001/data.pvtu'] = (b'<VTKFile type="PUnstructuredGrid">'
            b'<PUnstructuredGrid><Piece Source="piece.vtu"/>'
            b'</PUnstructuredGrid></VTKFile>')
        paths[pvd_base+'Cycle000001/piece.vtu'] = (b'<VTKFile type="UnstructuredGrid">'
            b'<UnstructuredGrid><Piece NumberOfPoints="4" NumberOfCells="1"><PointData>'
            b'<DataArray Name="E_real" NumberOfComponents="3" type="Float64"/>'
            b'<DataArray Name="E_imag" NumberOfComponents="3" type="Float64"/>'
            b'</PointData></Piece></UnstructuredGrid></VTKFile>')
    for name, data in paths.items():
        path=root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return [{'name':name,'sha256':_sha(data),'bytes':len(data)} for name,data in paths.items()]


def _manifest(artifacts):
    return {'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes',
            'artifacts':artifacts}


def test_verified_saved_palace_field_descriptor_lineage_is_only_format_evidence(tmp_path):
    manifest = _manifest(_field_artifacts(tmp_path))
    result = inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['schema']==SCHEMA
    assert result['status']=='VERIFIED_FORMAT_LINEAGE_ONLY'
    assert result['field_sample_count']==1
    assert result['saved_mode_ordinals_unverified']==[1]
    assert result['vtk_piece_count']==1
    assert result['all_pieces_declare_complex_E']
    assert result['mesh_sha256']==manifest['artifacts'][1]['sha256']
    assert result['coordinate_registration']=='NOT_ESTABLISHED'
    assert result['physical_mode_identity']=='UNRESOLVED'
    assert result['mesh_convergence']=='NOT_ESTABLISHED'
    assert result['fabrication']=='HOLD'


def test_missing_field_remains_blocked_without_fabricating_overlap(tmp_path):
    manifest=_manifest(_field_artifacts(tmp_path,include=False))
    result=inspect_verified_run_field_lineage(tmp_path,manifest)
    assert result['status']=='BLOCKED_NO_PARAVIEW_EXPORT'
    assert compare_verified_field_lineages([result,result])['status']=='BLOCKED_MISSING_OR_INVALID_FIELD_EXPORT'


@pytest.mark.parametrize('mutation', ['tamper_piece','missing_piece','injected_reference','invalid_E'])
def test_untrusted_field_chain_is_never_promoted(tmp_path, mutation):
    entries = _field_artifacts(tmp_path)
    piece=tmp_path/'sqe_em/outputFiles/paraview/solution/Cycle000001/piece.vtu'
    pvtu=tmp_path/'sqe_em/outputFiles/paraview/solution/Cycle000001/data.pvtu'
    if mutation=='tamper_piece':piece.write_bytes(b'not-declared-sha')
    elif mutation=='missing_piece':entries=[a for a in entries if not a['name'].endswith('piece.vtu')]
    elif mutation=='injected_reference':
        raw=pvtu.read_bytes().replace(b'piece.vtu',b'../outside.vtu')
        pvtu.write_bytes(raw)
        next(a for a in entries if a['name'].endswith('data.pvtu'))['sha256']=_sha(raw)
        next(a for a in entries if a['name'].endswith('data.pvtu'))['bytes']=len(raw)
    else:
        raw=piece.read_bytes().replace(b'E_imag',b'P_imag')
        piece.write_bytes(raw)
        next(a for a in entries if a['name'].endswith('piece.vtu'))['sha256']=_sha(raw)
    result=inspect_verified_run_field_lineage(tmp_path,_manifest(entries))
    assert result['status'].startswith('BLOCKED_')
    assert result['physical_mode_identity']=='UNRESOLVED'


def test_cross_mesh_readiness_is_not_a_mac_or_scientific_pass(tmp_path):
    records=[]
    for suffix in ('a','b','c'):
        root=tmp_path/suffix
        records.append(inspect_verified_run_field_lineage(root,
            _manifest(_field_artifacts(root,variant=suffix.encode()))))
    r=compare_verified_field_lineages(records,verified_mesh_screen={
        'status':'NUMERICAL_INDEX_TREND_ONLY','same_nonmesh_inputs':True})
    assert r['schema']==PAIR_SCHEMA
    assert r['status']=='FIELD_EXPORTS_READY_FOR_INDEPENDENT_REGISTRATION_REVIEW'
    assert r['native_mesh_hashes_distinct']
    assert r['complex_overlap']=='NOT_COMPUTED'
    assert r['physical_mode_identity']=='UNRESOLVED'
    assert r['mesh_convergence']=='NOT_ESTABLISHED'
    assert compare_verified_field_lineages(records)['status']=='BLOCKED_UNVERIFIED_NONMESH_INPUTS'
    pair=compare_verified_field_lineages(records[:2], verified_pairwise_screen={
        'status':'native_mode_index_differences_for_expert_review'})
    assert pair['status']=='FIELD_EXPORTS_READY_FOR_INDEPENDENT_REGISTRATION_REVIEW'
    assert compare_verified_field_lineages(records[:2])['status']=='BLOCKED_UNVERIFIED_NONMESH_INPUTS'
    records[2]=deepcopy(records[0])
    assert compare_verified_field_lineages(records)['status']=='BLOCKED_SAME_NATIVE_MESH_BYTES'


def test_catalog_registers_generic_field_readiness_without_tolerance_claim():
    case={x['id']:x for x in list_reference_cases()}['R04_PALACE_COMPLEX_FIELD_LINEAGE']
    assert case['tolerances'] is None
    assert case['oracle_kind']=='FIELD_EXPORT_LINEAGE_AND_REGISTRATION_READINESS'
    assert 'H(curl)' in case['science_boundary']


def test_http_saved_results_and_pairwise_field_readiness_sha_verified(tmp_path):
    """Actual HTTP auth+revision gate with fixture descriptor graph, not an EM run."""
    server=make_server(tmp_path/'private',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.ProxyHandler({}))
    base=f'http://127.0.0.1:{server.server_port}'
    csrf=''
    def req(path,method='GET',data=None):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if method=='POST' and csrf:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=headers,
                      data=json.dumps(data).encode() if data is not None else None)
        try:response=opener.open(request,timeout=8)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            raw=response.read()
            return response.status,(json.loads(raw) if response.headers.get('content-type','').startswith('application/json') else raw)
    try:
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'m11@local.test',
                   'password':'local-test-long-password','setup_token':token})[0]==200
        rc,auth=req('/api/login','POST',{'email':'m11@local.test','password':'local-test-long-password'})
        assert rc==200
        csrf=auth['csrf']
        rc,created=req('/api/projects','POST',{'name':'Field Auditing','family':'resonator',
                                             'template_id':'cpw_resonator_v1'})
        assert rc==201
        pid=created['id']; rid=created['head']
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        ids=['a'*32,'b'*32]
        target=None
        for i,runid in enumerate(ids):
            model=deepcopy(created['model'])
            model['studies'][0]['inputs']['em']['mesh']['max_um']=(120-i*40)
            rc,commit=req(f'/api/projects/{pid}/commit','POST',
                          {'expected_revision':rid,'model':model})
            assert rc==200,commit
            rid=commit['revision']
            folder=server.app.store.root/'native-runs'/pid/runid
            folder.mkdir(parents=True)
            server.app.store.put_run(owner,pid,rid,'ResEigen','sqdmetal_palace',folder)
            server.app.store.set_run(runid,'completed')
            output=folder/'output'
            artifacts=_field_artifacts(output,variant=str(i).encode())
            project=server.app.store.project(owner,pid,rid)
            manifest={'schema':'sqe.artifact.v1','engine':'sqdmetal_palace',
                'engine_version':'metadata_fixture_only','kind':'eigenmode',
                'artifact_type':'palace.eigenmodes','scientific_status':'review_required',
                'fabrication_status':'HOLD','revision_id':rid,
                'project_digest':project['revision_digest'],'study_id':'ResEigen',
                'parents':[],'provenance':{'used_revision':rid,
                  'used_project_sha256':project['revision_digest']},
                'artifacts':artifacts}
            (output/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
            target=output/'sqe_em/outputFiles/paraview/solution/Cycle000001/piece.vtu'
        rc,result=req(f'/api/projects/{pid}/runs/{ids[0]}/result')
        assert rc==200,result
        assert result['field_lineage']['status']=='VERIFIED_FORMAT_LINEAGE_ONLY'
        path=f'/api/projects/{pid}/compare?left={ids[0]}&right={ids[1]}'
        rc,result=req(path)
        assert rc==200,result
        assert result['field_lineage_comparison']['status']=='FIELD_EXPORTS_READY_FOR_INDEPENDENT_REGISTRATION_REVIEW'
        assert result['field_lineage_comparison']['complex_overlap']=='NOT_COMPUTED'
        assert len(result['field_lineage_by_run'])==2
        assert result['cross_mesh_visualization_review']['status']=='BLOCKED_NATIVE_VISUALIZATION_PRECONDITIONS'
        assert result['cross_mesh_visualization_review']['physical_mode_identity']=='UNRESOLVED'
        target.write_bytes(b'modified after manifest signed')
        assert req(path)[0]==409
        assert req('/api/logout','POST',{})[0]==200
        assert req(path)[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_realistic_palace_multiple_pvd_cycles_with_one_saved_mode(tmp_path):
    """Palace Save=1 can export Cycle000001/2; cycles are not mode IDs.

    Two-cycle pattern and eig.csv columns are taken from a real Windows Palace
    qualification report; all VTK files here are descriptor-only test fixtures.
    """
    artifacts=_field_artifacts(tmp_path)
    base=tmp_path/'sqe_em/outputFiles/paraview/solution'
    # Retain only the data shapes from the native report, not private mesh data.
    eig=tmp_path/'sqe_em/outputFiles/eig.csv'
    eig.write_text('        m,                Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)\n'
                   ' 1.00e+00, +5.904977748367e+00, +8.2e-06, +3.6e+05, +1.27e-12, +5.81e-06\n')
    second=base/'Cycle000002';second.mkdir()
    for filename in ('data.pvtu','piece.vtu'):
        (second/filename).write_bytes((base/'Cycle000001'/filename).read_bytes())
    pvd=base/'solution.pvd'
    pvd.write_text('<VTKFile type="Collection"><Collection>'
                   '<DataSet file="Cycle000001/data.pvtu"/>'
                   '<DataSet file="Cycle000002/data.pvtu"/>'
                   '</Collection></VTKFile>')
    from sqe_studio.interop.native_field import inspect_palace_field_export
    config=json.loads((tmp_path/'sqe_em/sqe_em.json').read_text())
    entries=[{'name':f.relative_to(tmp_path).as_posix(),
              'sha256':_sha(f.read_bytes()),'bytes':f.stat().st_size}
             for f in tmp_path.rglob('*') if f.is_file()]
    export=inspect_palace_field_export(tmp_path,config,entries)
    assert export['requested_native_modes']==1
    assert export['pvd_cycle_count']==2
    assert export['pvd_cycles_not_physical_modes']==['Cycle000001','Cycle000002']
    result=inspect_verified_run_field_lineage(tmp_path,_manifest(entries))
    assert result['status']=='VERIFIED_FORMAT_LINEAGE_ONLY'
    assert result['field_sample_count']==2
    assert result['output_cycles_not_physical_modes']==['Cycle000001','Cycle000002']
    assert result['physical_mode_identity']=='UNRESOLVED'
    assert result['mesh_convergence']=='NOT_ESTABLISHED'

def test_palace_repeated_cycle_rejected_even_if_sha_declared(tmp_path):
    entries=_field_artifacts(tmp_path)
    path=tmp_path/'sqe_em/outputFiles/paraview/solution/solution.pvd'
    path.write_text('<VTKFile type="Collection"><Collection>'
                    '<DataSet file="Cycle000001/data.pvtu"/>'
                    '<DataSet file="Cycle000001/data.pvtu"/>'
                    '</Collection></VTKFile>')
    entries=[{'name':f.relative_to(tmp_path).as_posix(),
              'sha256':_sha(f.read_bytes()),'bytes':f.stat().st_size}
             for f in tmp_path.rglob('*') if f.is_file()]
    result=inspect_verified_run_field_lineage(tmp_path,_manifest(entries))
    assert result['status']=='BLOCKED_INVALID_NATIVE_FIELD_LINEAGE'
    assert result['physical_mode_identity']=='UNRESOLVED'


def test_m12_catalog_registers_diagnostic_not_fake_scientific_pass():
    case={x['id']:x for x in list_reference_cases()}[
        'R05_PALACE_CROSS_MESH_VISUALIZATION_DIAGNOSTIC']
    assert case['tolerances'] is None
    assert case['oracle_kind']=='BOUNDED_CROSS_MESH_VISUALIZATION_L2_DIAGNOSTIC'
    assert 'H(curl)' in case['science_boundary']
