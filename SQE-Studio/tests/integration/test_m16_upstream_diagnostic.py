"""M16 operator-authorized test-only VTK integration.

Tiny VTK fixtures exercise software, not genuine Palace scientific accuracy.
No fixture can qualify B02, mode identity, EPR or mesh convergence.
"""
from __future__ import annotations
import hashlib
import http.cookiejar
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from sqe_studio.eda.upstream_vtk_probe import (
    SCHEMA, LEGACY_SCHEMA, _public_result, probe_verified_run)
from sqe_studio.server import make_server


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _native_piece(root, *, complex_e=True):
    vtk = pytest.importorskip('vtk')
    folder=root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001'
    folder.mkdir(parents=True)
    pts=vtk.vtkPoints()
    for point in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
        pts.InsertNextPoint(*point)
    grid=vtk.vtkUnstructuredGrid();grid.SetPoints(pts)
    tetra=vtk.vtkTetra()
    for i in range(4):tetra.GetPointIds().SetId(i,i)
    grid.InsertNextCell(tetra.GetCellType(),tetra.GetPointIds())
    for name in (('E_real','E_imag') if complex_e else ('A_real','A_imag')):
        arr=vtk.vtkDoubleArray();arr.SetName(name);arr.SetNumberOfComponents(3)
        for i in range(4):arr.InsertNextTuple3(1+i,2+i,3+i)
        grid.GetPointData().AddArray(arr)
    writer=vtk.vtkXMLPUnstructuredGridWriter()
    writer.SetFileName(str(folder/'data.pvtu'))
    writer.SetInputData(grid);writer.SetNumberOfPieces(1)
    writer.SetStartPiece(0);writer.SetEndPiece(0)
    writer.SetDataModeToAppended();writer.EncodeAppendedDataOff()
    assert writer.Write()==1
    import xml.etree.ElementTree as ET
    pvtu=folder/'data.pvtu'
    tree=ET.parse(pvtu);piece=tree.find('./PUnstructuredGrid/Piece')
    (folder/piece.attrib['Source']).rename(folder/'proc000000.vtu')
    piece.attrib['Source']='proc000000.vtu'
    tree.write(pvtu,encoding='utf-8',xml_declaration=True)
    pvd=folder.parent/'eigenmode.pvd'
    pvd.write_text('<VTKFile type="Collection"><Collection><DataSet '
                   'timestep="1" file="Cycle000001/data.pvtu"/>'
                   '</Collection></VTKFile>')
    files=[pvd,pvtu,folder/'proc000000.vtu']
    artifacts=[{'name':str(f.relative_to(root)).replace('\\','/'),
                'bytes':f.stat().st_size,'sha256':_sha(f.read_bytes())} for f in files]
    manifest={'engine':'sqdmetal_palace','artifact_type':'palace.eigenmodes',
              'artifacts':artifacts}
    (root/'RESULT_MANIFEST.json').write_text(json.dumps(manifest))
    return manifest, folder/'proc000000.vtu'


def test_live_upstream_vtk_raw_appended_and_safe_report(tmp_path):
    manifest,piece=_native_piece(tmp_path)
    record=probe_verified_run(tmp_path,manifest,timeout=20)
    assert record['schema']==SCHEMA
    assert record['status']=='UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED',record
    assert record['physical_mode_identity']=='NOT_ESTABLISHED'
    assert record['mesh_convergence']=='NOT_ESTABLISHED'
    assert record['cycles'][0]['blocks'][0]['point']['E_imag']=='FLOAT_VECTOR_3'
    assert 'coordinates' not in json.dumps(record)
    assert str(tmp_path) not in json.dumps(record)
    piece.write_bytes(b'changed since manifest')
    result=probe_verified_run(tmp_path,manifest,timeout=20)
    assert result['status']=='BLOCKED'
    assert result['reason_code']=='ARTIFACT_HASH_MISMATCH'


def test_live_reader_missing_complex_e_is_not_physics_pass(tmp_path):
    manifest,_=_native_piece(tmp_path,complex_e=False)
    record=probe_verified_run(tmp_path,manifest,timeout=20)
    assert record['status']=='UPSTREAM_COMPLEX_E_NOT_ESTABLISHED',record
    assert not record['cycles'][0]['complex_e_declared']
    assert record['mesh_convergence']=='NOT_ESTABLISHED'


def test_rejects_manifest_mismatch_and_no_pvd(tmp_path):
    manifest,_=_native_piece(tmp_path)
    changed=dict(manifest, engine='tampered')
    assert probe_verified_run(tmp_path,changed)['reason_code']=='NOT_APPLICABLE'
    changed=dict(manifest, artifacts=[])
    assert probe_verified_run(tmp_path,changed)['reason_code']=='MANIFEST_IDENTITY_MISMATCH'
    assert _public_result('PROBE_ERROR')['field_values_in_report'] is False


def test_authenticated_probed_run_requires_csrf_and_explicit_optin(tmp_path,monkeypatch):
    """The real HTTP server must honor auth, CSRF, revision and output hashes."""
    from sqe_studio.design_library import instantiate
    from sqe_studio.eda import upstream_vtk_probe
    from sqe_studio.orchestration.artifacts import verify_manifest
    from copy import deepcopy
    server=make_server(tmp_path/'private',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       urllib.request.ProxyHandler({}))
    base=f'http://127.0.0.1:{server.server_port}'
    csrf=''
    def req(path,method='GET',data=None,with_csrf=True):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if method=='POST' and csrf and with_csrf:headers['X-CSRF-Token']=csrf
        request=urllib.request.Request(base+path,method=method,headers=headers,
              data=json.dumps(data).encode() if data is not None else None)
        try:response=opener.open(request,timeout=15)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            raw=response.read()
            return response.status,(json.loads(raw) if response.headers.get('content-type','').startswith('application/json') else raw)
    try:
        path=f'/api/projects/{"a"*32}/runs/{"b"*32}/upstream-field-probe'
        assert req(path,'POST',{'experimental_diagnostic':True})[0]==401
        token=server.app.setup_file.read_text()
        assert req('/api/setup','POST',{'email':'m16@local.test',
             'password':'long-local-m16-test-password','setup_token':token})[0]==200
        status,auth=req('/api/login','POST',{'email':'m16@local.test','password':'long-local-m16-test-password'})
        assert status==200
        csrf=auth['csrf']
        assert req(path,'POST',{'experimental_diagnostic':True},with_csrf=False)[0]==403
        status,created=req('/api/projects','POST',{'name':'Palace Test Diagnostic',
              'family':'resonator','template_id':'cpw_resonator_v1'})
        assert status==201,created
        pid=created['id'];rid=created['head']; runid='f'*32
        owner=server.app.store.conn().execute('SELECT id FROM accounts').fetchone()['id']
        folder=server.app.store.root/'native-runs'/pid/runid
        folder.mkdir(parents=True)
        server.app.store.put_run(owner,pid,rid,'ResEigen','sqdmetal_palace',folder)
        server.app.store.set_run(runid,'completed')
        output=folder/'output';output.mkdir()
        native_manifest,piece=_native_piece(output)
        project=server.app.store.project(owner,pid,rid)
        native_manifest.update({'schema':'sqe.artifact.v1','engine_version':'test-metadata',
            'kind':'eigenmode','scientific_status':'review_required',
            'fabrication_status':'HOLD','revision_id':rid,
            'project_digest':project['revision_digest'],'study_id':'ResEigen',
            'parents':[],'provenance':{'used_revision':rid,
              'used_project_sha256':project['revision_digest']}})
        (output/'RESULT_MANIFEST.json').write_text(json.dumps(native_manifest))
        from sqe_studio.contracts import digest
        (folder/'snapshot.json').write_text(json.dumps({'revision_id':rid,
            'project_digest':project['revision_digest'], 'project':project['model']}))
        route=f'/api/projects/{pid}/runs/{runid}/upstream-field-probe'
        assert req(route,'POST',{})[0]==422
        calls=[]
        def stub(out,manifest,timeout=25):
            calls.append(out)
            return _public_result('TEST_FIXTURE_ONLY')
        monkeypatch.setattr(upstream_vtk_probe,'probe_verified_run',stub)
        status,response=req(route,'POST',{'experimental_diagnostic':True})
        assert status==200,response
        assert response['diagnostic']['reason_code']=='TEST_FIXTURE_ONLY'
        assert response['scientific_approval']=='NOT_ESTABLISHED'
        assert calls==[output]
        piece.write_bytes(b'changed')
        assert req(route,'POST',{'experimental_diagnostic':True})[0]==409
        assert len(calls)==1
        assert req('/api/logout','POST',{})[0]==200
        assert req(route,'POST',{'experimental_diagnostic':True})[0]==401
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_b02_upstream_diagnostic_is_categorical_and_never_scientific_pass():
    import importlib.util
    other=Path(__file__).with_name('test_native_scalar_qualification_link.py')
    spec=importlib.util.spec_from_file_location('native_case_fixture',other)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from sqe_studio.cycle_qualification import _case_from_em
    data=module._evidence()
    base='em/native/native_palace_solve-'
    doc=json.loads(data[base+'results-screen.json'])
    states={name:('FLOAT_VECTOR_3' if name in ('E_real','E_imag') else 'ABSENT')
            for name in ('E_real','E_imag','E','B_real','B_imag')}
    empty={name:'ABSENT' for name in states}
    diagnostic={'schema':LEGACY_SCHEMA,'backend':'VTK','backend_version':'9.6.2',
        'status':'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED',
        'pvd_cycle_count':1,'cycles':[{'cycle_index_not_mode_identity':0,
        'mpi_piece_count':1,'blocks':[{'point':states,'cell':empty}],
        'complex_e_declared':True}],
        'physical_mode_identity':'NOT_ESTABLISHED','mesh_convergence':'NOT_ESTABLISHED',
        'field_values_in_report':False}
    doc['upstream_field_probe']=diagnostic
    data[base+'results-screen.json']=json.dumps(doc).encode()
    data[base+'upstream-field-probe.json']=json.dumps(diagnostic).encode()
    result=_case_from_em(data,'B02')
    assert result['stage_status']=='BLOCKED'
    assert result['measurements']['upstream_vtk_diagnostic']['status']==diagnostic['status']
    assert result['measurements']['upstream_vtk_diagnostic']['complex_E_declared_by_cycle']==[True]
    assert result['measurements']['mesh_convergence']=='NOT_ESTABLISHED'
    # Replacing the standalone evidence without updating the screen is a FAIL.
    altered=dict(data)
    altered[base+'upstream-field-probe.json']=json.dumps(_public_result('TAMPERED')).encode()
    bad=_case_from_em(altered,'B02')
    assert bad['stage_status']=='FAIL'
    assert bad['failure_reason']=='INVALID_NATIVE_SCALAR_EVIDENCE'


def test_b02_rejects_upstream_probe_private_arrays_or_fake_physics():
    import importlib.util
    other=Path(__file__).with_name('test_native_scalar_qualification_link.py')
    spec=importlib.util.spec_from_file_location('native_case_fixture2',other)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from sqe_studio.cycle_qualification import _case_from_em
    base='em/native/native_palace_solve-'
    for injected in ({'schema':SCHEMA,'status':'BLOCKED','reason_code':'UNKNOWN',
                      'physical_mode_identity':'VERIFIED','mesh_convergence':'NOT_ESTABLISHED',
                      'field_values_in_report':False},
                     {'schema':SCHEMA,'status':'BLOCKED','reason_code':'PRIVATE_/home/test',
                      'physical_mode_identity':'NOT_ESTABLISHED','mesh_convergence':'NOT_ESTABLISHED',
                      'field_values_in_report':False}):
        data=module._evidence()
        doc=json.loads(data[base+'results-screen.json'])
        doc['upstream_field_probe']=injected
        data[base+'results-screen.json']=json.dumps(doc).encode()
        data[base+'upstream-field-probe.json']=json.dumps(injected).encode()
        bad=_case_from_em(data,'B02')
        assert bad['stage_status']=='FAIL'
