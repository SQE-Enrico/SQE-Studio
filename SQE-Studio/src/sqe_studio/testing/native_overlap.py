"""Actual VTK sampling/MAC checks with analytic fields, never a Palace solve."""
from __future__ import annotations

import hashlib
from importlib import util
import json
import math
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

ERROR_STAGES=frozenset(('PREREQUISITES','ANALYTIC_PAIR','BOUNDED_SUBPROCESS','HERMITIAN_PRODUCT',
    'COVERAGE_GUARD','SHARED_GEOMETRY_VIEW','HIGHER_ORDER_METADATA','UNSUPPORTED_CELL_TYPES',
    'INVALID_CELL_FIXTURES','MODERN_METADATA_PROTOCOL','METADATA_ARRAY_BOUNDS','COMPONENT_DIAGNOSTICS'))


def _failure_diagnostic(exc, stage):
    """Bounded failure context; never exception text, objects or full paths."""
    classes={'AttributeError','TypeError','ValueError','AssertionError','RuntimeError','OSError',
             'ComparisonBlocked','ArtifactInvalid','ImportError','ModuleNotFoundError'}
    attributes={'GetCellTypesArray','GetCellTypes','GetDataType','GetNumberOfComponents',
        'GetNumberOfTuples','GetNumberOfValues','GetOffsetsArray','GetConnectivityArray',
        'GetPoints','GetData','GetCells','GetCellType','SetCells','SetData','SetCellOrder',
        'SetBlocksDimensions','GetOutput','DeepCopy','ShallowCopy','Modified','GetArray',
        'GetPointData','GetCellDataArraySelection','SetStrategy','Update'}
    name=getattr(exc,'name',None) if isinstance(exc,AttributeError) else None
    attribute=name if type(name) is str and name in attributes else ('OTHER_ATTRIBUTE' if name is not None else None)
    object_type=None
    if isinstance(exc,AttributeError):
        kind=type(getattr(exc,'obj',None)).__name__
        object_type=kind if (kind in {'NoneType','ndarray','str','dict','list','tuple','int'} or
            kind.startswith('vtk') and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',kind)) else 'OTHER'
    frames=[];tb=exc.__traceback__
    while tb is not None:
        filename=Path(tb.tb_frame.f_code.co_filename).name
        function=tb.tb_frame.f_code.co_name
        if (filename in {'native_overlap.py','upstream_field_compare.py','numpy_support.py'} and
                re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',function) and 0 < tb.tb_lineno < 100000):
            frames.append({'file':filename,'function':function,'line':tb.tb_lineno})
        tb=tb.tb_next
    return {'schema':'sqe.native-software-fixture-error.v1',
        'stage':stage if type(stage) is str and stage in ERROR_STAGES else 'UNKNOWN_STAGE',
        'exception_type':type(exc).__name__ if type(exc).__name__ in classes else 'OTHER',
        'attribute':attribute,'attribute_object_type':object_type,'frames':frames[-8:],
        'private_paths_exported':False,'field_values_exported':False}


def analytic_grid(resolution, kind='constant', *, phase=0., scale=1., shift=0.):
    import vtk
    import numpy as np
    from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    image=vtk.vtkImageData();image.SetDimensions(*([resolution+1]*3))
    image.SetOrigin(shift,0,0);image.SetSpacing(*([1./resolution]*3))
    tetra=vtk.vtkDataSetTriangleFilter();tetra.SetInputData(image)
    tetra.SetTetrahedraOnly(True);tetra.Update()
    grid=vtk.vtkUnstructuredGrid();grid.DeepCopy(tetra.GetOutput())
    xyz=vtk_to_numpy(grid.GetPoints().GetData())
    vector=np.zeros((len(xyz),3),dtype=float)
    if kind=='constant':vector[:,0]=1.
    elif kind=='orthogonal':vector[:,1]=1.
    elif kind=='linear_x':vector[:,0]=xyz[:,0]-shift
    elif kind=='zero':pass
    elif kind=='nonfinite':vector[:,0]=float('nan')
    else:raise ValueError('Unknown fixed analytic fixture')
    for name,values in (('E_real',scale*math.cos(phase)*vector),('E_imag',scale*math.sin(phase)*vector)):
        array=numpy_to_vtk(values,deep=True);array.SetName(name);grid.GetPointData().AddArray(array)
    return grid


def fixture_model(resolution):
    # Deliberately an algorithm fixture, not a claimed CAD/Palace simulation.
    return {'layout':{'fixture':'unit_cube'},'process':{'fixture_only':True},
            'schematic':{},'studies':[{'id':'FieldFixture','engine':'sqdmetal_palace',
            'kind':'eigenmode','inputs':{'em':{'mesh':{'fixture_resolution':resolution},
            'fixture_protocol':'ANALYTIC_FIELDS_NO_MAXWELL_SOLVE'}}}]}


def encoded_grid(grid, encoding):
    """Native test data representations; no production mesh conversion."""
    import vtk
    import numpy as np
    from vtk.util.numpy_support import numpy_to_vtk
    if encoding=='linear':return grid
    result=vtk.vtkUnstructuredGrid();result.ShallowCopy(grid)
    if encoding=='lagrange':result.SetCells(vtk.VTK_LAGRANGE_TETRAHEDRON,grid.GetCells())
    elif encoding=='mixed':
        types=np.full(grid.GetNumberOfCells(),vtk.VTK_TETRA,dtype=np.uint8)
        types[::2]=vtk.VTK_LAGRANGE_TETRAHEDRON
        result.SetCells(numpy_to_vtk(types,deep=True),grid.GetCells())
    else:raise ValueError('Unknown fixed fixture encoding')
    return result


def write_snapshot(root, grid, model, *, pieces=4, include_auxiliary=True):
    """Standard upstream writers encode each disjoint fixture piece."""
    import vtk
    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy
    from sqe_studio.contracts import digest
    root=Path(root);folder=root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001'
    folder.mkdir(parents=True)
    chunks=np.array_split(np.arange(grid.GetNumberOfCells()),pieces)
    for index,chunk in enumerate(chunks):
        ids=vtk.vtkIdList()
        for cell in chunk:ids.InsertNextId(int(cell))
        extract=vtk.vtkExtractCells();extract.SetInputData(grid);extract.SetCellList(ids);extract.Update()
        writer=vtk.vtkXMLUnstructuredGridWriter()
        writer.SetFileName(str(folder/f'proc{index:06d}.vtu'))
        writer.SetInputData(extract.GetOutput());writer.SetDataModeToAppended();writer.EncodeAppendedDataOff()
        if writer.Write()!=1:raise RuntimeError('UPSTREAM_FIXTURE_WRITE_FAILED')
        if index==0:
            template=vtk.vtkXMLPUnstructuredGridWriter()
            template.SetFileName(str(folder/'data.pvtu'));template.SetInputData(extract.GetOutput())
            template.SetNumberOfPieces(1);template.SetStartPiece(0);template.SetEndPiece(0)
            template.SetDataModeToAppended();template.EncodeAppendedDataOff()
            if template.Write()!=1:raise RuntimeError('UPSTREAM_DESCRIPTOR_WRITE_FAILED')
    descriptor=ET.parse(folder/'data.pvtu');container=descriptor.find('./PUnstructuredGrid')
    for child in container.findall('Piece'):
        generated=folder/child.attrib['Source']
        if generated.name not in {f'proc{i:06d}.vtu' for i in range(pieces)}:generated.unlink()
        container.remove(child)
    for index in range(pieces):ET.SubElement(container,'Piece',Source=f'proc{index:06d}.vtu')
    descriptor.write(folder/'data.pvtu',encoding='utf-8',xml_declaration=True)
    pvd=ET.Element('VTKFile',type='Collection',version='0.1');collection=ET.SubElement(pvd,'Collection')
    ET.SubElement(collection,'DataSet',timestep='1',file='Cycle000001/data.pvtu')
    if include_auxiliary:
        auxfolder=folder.parent/'Cycle000002';auxfolder.mkdir()
        auxiliary=vtk.vtkUnstructuredGrid();auxiliary.DeepCopy(grid)
        auxiliary.GetPointData().RemoveArray('E_real');auxiliary.GetPointData().RemoveArray('E_imag')
        marker=vtk.vtkDoubleArray();marker.SetName('Indicator');marker.SetNumberOfTuples(grid.GetNumberOfCells())
        marker.FillComponent(0,1.);auxiliary.GetCellData().AddArray(marker)
        writer=vtk.vtkXMLPUnstructuredGridWriter();writer.SetInputData(auxiliary)
        writer.SetFileName(str(auxfolder/'data.pvtu'));writer.SetNumberOfPieces(1)
        writer.SetStartPiece(0);writer.SetEndPiece(0);writer.SetDataModeToAppended();writer.EncodeAppendedDataOff()
        if writer.Write()!=1:raise RuntimeError('UPSTREAM_AUXILIARY_WRITE_FAILED')
        d=ET.parse(auxfolder/'data.pvtu');piece=d.find('./PUnstructuredGrid/Piece')
        (auxfolder/piece.attrib['Source']).rename(auxfolder/'proc000000.vtu')
        piece.attrib['Source']='proc000000.vtu';d.write(auxfolder/'data.pvtu',encoding='utf-8',xml_declaration=True)
        ET.SubElement(collection,'DataSet',timestep='2',file='Cycle000002/data.pvtu')
    ET.ElementTree(pvd).write(folder.parent/'eigenmode.pvd',encoding='utf-8',xml_declaration=True)
    geometry=hashlib.sha256(vtk_to_numpy(grid.GetPoints().GetData()).tobytes()+
        vtk_to_numpy(grid.GetCells().GetConnectivityArray()).tobytes()).hexdigest()
    (root/'sqe_em/sqe_em.msh').write_text('SOFTWARE_FIXTURE_NOT_GMSH\n'+geometry+'\n',encoding='utf-8')
    deck={'Problem':{'Type':'Eigenmode','Output':'outputFiles'},
          'Model':{'Mesh':'sqe_em.msh','L0':1.},'Domains':{'fixture_only':True},
          'Boundaries':{'fixture_only':True},'Solver':{'Eigenmode':{'N':1,'Save':1}}}
    (root/'sqe_em/sqe_em.json').write_text(json.dumps(deck),encoding='utf-8')
    (root/'sqe_em/outputFiles/eig.csv').write_text('m,Re{f} (GHz),Q\n1,5.9,1000\n',encoding='utf-8')
    artifacts=[{'name':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'bytes':p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file()]
    model_sha=digest(model);revision=model_sha[:32]
    manifest={'schema':'sqe.artifact.v1','engine':'sqdmetal_palace','kind':'eigenmode',
        'artifact_type':'palace.eigenmodes','engine_version':'ANALYTIC_VTK_FIXTURE_NOT_PALACE',
        'scientific_status':'review_required','fabrication_status':'HOLD','revision_id':revision,
        'project_digest':model_sha,'study_id':model['studies'][0]['id'],'parents':[],
        'provenance':{'used_revision':revision,'used_project_sha256':model_sha},'artifacts':artifacts}
    (root/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    return manifest


def run_workflow():
    if any(util.find_spec(name) is None for name in ('vtk','numpy')):
        return {'status':'BLOCKED','reason':'UPSTREAM_VTK_OR_NUMPY_NOT_INSTALLED','execution_kind':'NOT_RUN'}
    from sqe_studio.eda import upstream_field_compare as comparison
    rows=[];active_stage='PREREQUISITES'
    def calculate(base,label,left_n,right_n,kind='constant',phase=0.,scale=1.,shift=0.,cycles=(None,None),
                  encoding='linear',right_encoding=None,isolated=False):
        nonlocal active_stage
        active_stage='ANALYTIC_PAIR'
        roots=(base/(label+'-left'),base/(label+'-right'))
        models=(fixture_model(left_n),fixture_model(right_n))
        grids=(encoded_grid(analytic_grid(left_n),encoding),
               encoded_grid(analytic_grid(right_n,kind,phase=phase,scale=scale,shift=shift),right_encoding or encoding))
        manifests=tuple(write_snapshot(root,g,m) for root,g,m in zip(roots,grids,models))
        if isolated:return comparison.compare_verified_fields(roots,manifests,models,
            ('FieldFixture','FieldFixture'),same_frame=True,cycle_indices=cycles)
        request=comparison.prepare_request(roots,manifests,models,('FieldFixture','FieldFixture'),
                                          same_frame=True,cycle_indices=cycles)
        return comparison.run_request(request)
    try:
        with tempfile.TemporaryDirectory(prefix='sqe-m18-analytic-') as td:
            base=Path(td)
            result=calculate(base,'phase',1,2,phase=.8,scale=3.)
            assert all(abs(d['mac']-1.)<1e-10 and abs(d['relative_phase_rad']-.8)<1e-10
                       for d in result['directions'])
            rows.append({'id':'complex_phase_scale_and_four_piece_read','status':'PASS',
                         'reference_mac':1.,'reference_phase_rad':.8,'result':result})
            roots=(base/'phase-left',base/'phase-right')
            active_stage='BOUNDED_SUBPROCESS'
            manifests=[json.loads((r/'RESULT_MANIFEST.json').read_text(encoding='utf-8')) for r in roots]
            isolated=comparison.compare_verified_fields(roots,manifests,
                (fixture_model(1),fixture_model(2)),('FieldFixture','FieldFixture'),same_frame=True)
            assert isolated['status']==comparison.RECORDED,isolated['reason_code']
            assert all(abs(d['mac']-1.)<1e-10 for d in isolated['directions'])
            rows.append({'id':'bounded_native_subprocess_roundtrip','status':'PASS','result':isolated})
            import numpy as np
            active_stage='HERMITIAN_PRODUCT'
            complex_a=np.array([[1,1j,0],[1j,0,1]],dtype=complex)
            complex_b=np.conjugate(complex_a)
            mac,phase=comparison.weighted_mac(complex_a,complex_b,np.array([1.,3.]))
            assert abs(mac)<1e-12 and phase is None
            rows.append({'id':'hermitian_conjugation_not_bilinear_dot','status':'PASS',
                         'reference_mac':0.,'actual_mac':mac})
            result=calculate(base,'orthogonal',1,2,kind='orthogonal')
            assert all(abs(d['mac'])<1e-12 for d in result['directions'])
            rows.append({'id':'orthogonal_analytic_vectors','status':'PASS','reference_mac':0.,
                         'result':result})
            trend=[]
            for n in (1,2,4):
                result=calculate(base,'linear'+str(n),n,2*n,kind='linear_x')
                values=[d['mac'] for d in result['directions']]
                trend.append({'left_resolution':n,'right_resolution':2*n,'mac':values,
                              'max_error_from_continuum':max(abs(v-.75) for v in values)})
            assert all(b['max_error_from_continuum']<a['max_error_from_continuum'] for a,b in zip(trend,trend[1:]))
            assert trend[-1]['max_error_from_continuum']<.01
            rows.append({'id':'refined_sampling_approaches_analytic_limit','status':'PASS',
                         'reference_continuum_mac':.75,'max_final_absolute_error':.01,'trend':trend})
            import vtk
            active_stage='COVERAGE_GUARD'
            source=analytic_grid(2)
            ids=vtk.vtkIdList();ids.InsertNextId(0)
            extract=vtk.vtkExtractCells();extract.SetInputData(source);extract.SetCellList(ids);extract.Update()
            _,centers=comparison._prepare_grid(source)
            try:
                comparison._sample(extract.GetOutput(),centers,1e-10)
            except comparison.ComparisonBlocked as exc:
                assert str(exc)=='INCOMPLETE_CROSS_MESH_COVERAGE'
            else:raise AssertionError('Uncovered points were silently accepted')
            rows.append({'id':'reject_uncovered_samples_without_nearest_cell_snap','status':'PASS',
                         'expected_blocker':'INCOMPLETE_CROSS_MESH_COVERAGE'})
            for label,kwargs,expected in (
                ('shifted',{'shift':.1},'NATIVE_DOMAIN_BOUNDS_DIFFER'),
                ('zero',{'kind':'zero'},'ZERO_OR_INVALID_FIELD_NORM'),
                ('nan',{'kind':'nonfinite'},'NONFINITE_NATIVE_FIELD_VALUES'),
                ('auxiliary',{'cycles':(None,1)},'SELECTED_OUTPUT_IS_NOT_COMPLEX_E')):
                try:
                    calculate(base,label,1,2,**kwargs)
                except comparison.ComparisonBlocked as exc:
                    assert str(exc)==expected,(label,str(exc))
                else:raise AssertionError('Invalid source was accepted: '+label)
                rows.append({'id':'reject_'+label,'status':'PASS','expected_blocker':expected})
            result=calculate(base,'lagrange',1,2,phase=.8,scale=3.,encoding='lagrange',isolated=True)
            assert result['status']==comparison.RECORDED,result['reason_code']
            assert all(abs(d['mac']-1.)<1e-10 and abs(d['relative_phase_rad']-.8)<1e-10 for d in result['directions'])
            assert all(g['cell_types'][0]['vtk_type_id']==71 and g['nodes_per_cell_max']==4 and
                       g['geometry_view']=='ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW' for g in result['grid_diagnostics'])
            rows.append({'id':'order_one_lagrange_four_piece_native_subprocess','status':'PASS','result':result})
            result=calculate(base,'mixed',1,2,encoding='mixed',right_encoding='linear')
            assert all(abs(d['mac']-1.)<1e-10 for d in result['directions'])
            assert [t['vtk_type_id'] for t in result['grid_diagnostics'][0]['cell_types']]==[10,71]
            rows.append({'id':'mixed_four_node_native_representations','status':'PASS','result':result})
            from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
            active_stage='SHARED_GEOMETRY_VIEW'
            lagrange=encoded_grid(analytic_grid(2,kind='linear_x'),'lagrange')
            view=comparison._linear_geometry_view(lagrange)
            assert view.GetCells()==lagrange.GetCells() and view.GetPoints()==lagrange.GetPoints()
            assert lagrange.GetCellType(0)==71 and view.GetCellType(0)==10
            for name in ('E_real','E_imag'):
                assert view.GetPointData().GetArray(name)==lagrange.GetPointData().GetArray(name)
            volume,centers=comparison._prepare_grid(lagrange)
            assert abs(sum(volume)-1.)<1e-12
            expected_x=vtk_to_numpy(centers.GetPoints().GetData())[:,0]
            assert np.allclose(comparison._sample(lagrange,centers,1e-10)[:,0],expected_x,rtol=0,atol=1e-12)
            rows.append({'id':'geometry_view_shares_arrays_and_probes_original_grid','status':'PASS'})
            active_stage='HIGHER_ORDER_METADATA'
            higher=vtk.vtkCellTypeSource();higher.SetCellType(vtk.VTK_LAGRANGE_TETRAHEDRON)
            higher.SetCellOrder(2);higher.SetBlocksDimensions(1,1,1);higher.Update()
            highgrid=higher.GetOutput()
            for name in ('E_real','E_imag'):
                data=np.zeros((highgrid.GetNumberOfPoints(),3))
                if name=='E_real':data[:,0]=1.
                array=numpy_to_vtk(data,deep=True);array.SetName(name);highgrid.GetPointData().AddArray(array)
            roots=(base/'higher-left',base/'higher-right');models=(fixture_model(1),fixture_model(2))
            manifests=[write_snapshot(root,g,m) for root,g,m in zip(roots,(analytic_grid(1),highgrid),models)]
            blocked=comparison.compare_verified_fields(roots,manifests,models,('FieldFixture','FieldFixture'),same_frame=True)
            assert blocked['status']=='BLOCKED' and blocked['reason_code']=='LINEAR_TETRAHEDRA_REQUIRED'
            assert len(blocked['grid_diagnostics'])==2 and blocked['grid_diagnostics'][1]['nodes_per_cell_min']==10
            assert blocked['grid_diagnostics'][1]['geometry_view']=='UNSUPPORTED_CELL_GEOMETRY'
            assert blocked['directions']==[] and blocked['sources']==[]
            rows.append({'id':'higher_order_blocker_retains_bounded_cell_metadata','status':'PASS','result':blocked})
            active_stage='UNSUPPORTED_CELL_TYPES'
            for label,celltype in (('non_tetra',vtk.VTK_HEXAHEDRON),('legacy_quadratic',vtk.VTK_QUADRATIC_TETRA)):
                source=vtk.vtkCellTypeSource();source.SetCellType(celltype);source.SetBlocksDimensions(1,1,1)
                source.Update()
                try:comparison._prepare_grid(source.GetOutput())
                except comparison.ComparisonBlocked as exc:assert str(exc)=='LINEAR_TETRAHEDRA_REQUIRED'
                else:raise AssertionError('Unsupported cell family accepted')
                rows.append({'id':'reject_'+label,'status':'PASS','expected_blocker':'LINEAR_TETRAHEDRA_REQUIRED'})
            active_stage='INVALID_CELL_FIXTURES'
            for label in ('inverted_lagrange','invalid_connectivity'):
                bad=vtk.vtkUnstructuredGrid();bad.DeepCopy(lagrange)
                native=vtk.vtkIdTypeArray();native.DeepCopy(bad.GetCells().GetConnectivityArray())
                offsets=vtk.vtkIdTypeArray();offsets.DeepCopy(bad.GetCells().GetOffsetsArray())
                ids=vtk_to_numpy(native)
                if label=='inverted_lagrange':ids[0],ids[1]=int(ids[1]),int(ids[0])
                else:ids[0]=bad.GetNumberOfPoints()+1
                native.Modified()
                cells=vtk.vtkCellArray();cells.SetData(offsets,native);bad.SetCells(vtk.VTK_LAGRANGE_TETRAHEDRON,cells)
                expected='INVALID_OR_INVERTED_TETRAHEDRON' if label=='inverted_lagrange' else 'INVALID_NATIVE_CELL_TOPOLOGY'
                try:comparison._prepare_grid(bad)
                except comparison.ComparisonBlocked as exc:assert str(exc)==expected,(label,str(exc))
                else:raise AssertionError('Invalid cell geometry accepted')
                rows.append({'id':'reject_'+label,'status':'PASS','expected_blocker':expected})
            active_stage='MODERN_METADATA_PROTOCOL'
            array=vtk.vtkUnsignedCharArray();array.SetName('FixtureCellTypes')
            array.SetNumberOfTuples(lagrange.GetNumberOfCells());array.FillComponent(0,71)
            lagrange.GetCellData().AddArray(array)
            implicit=vtk.vtkToImplicitArrayFilter();implicit.SetInputData(lagrange)
            implicit.SetStrategy(vtk.vtkToConstantArrayStrategy())
            implicit.GetCellDataArraySelection().EnableArray('FixtureCellTypes');implicit.Update()
            native_types=implicit.GetOutput().GetCellData().GetArray('FixtureCellTypes')
            assert native_types is not None and native_types.GetClassName()!='vtkUnsignedCharArray'
            class ModernGridProtocol:
                def __getattr__(self,name):return getattr(lagrange,name)
                def GetCellTypes(self):return native_types
                def GetCellTypesArray(self):raise AssertionError('Legacy getter must not be used')
            described=comparison._grid_description(ModernGridProtocol())
            assert described['cell_types']==[{'vtk_type_id':71,'count':lagrange.GetNumberOfCells()}]
            assert described['nodes_per_cell_min']==described['nodes_per_cell_max']==4
            rows.append({'id':'modern_getter_with_native_implicit_metadata','status':'PASS',
                'execution_kind':'SOFTWARE_API_PROTOCOL_SHIM_WITH_NATIVE_ARRAYS',
                'native_array_was_implicit':'vtkUnsignedCharArray'!=native_types.GetClassName()})
            active_stage='METADATA_ARRAY_BOUNDS'
            values=comparison._metadata_values(native_types,'types',lagrange.GetNumberOfCells())
            assert np.all(values==71)
            try:comparison._metadata_values(native_types,'types',lagrange.GetNumberOfCells()+1)
            except comparison.ComparisonBlocked as exc:assert str(exc)=='INVALID_CELL_METADATA_SHAPE'
            else:raise AssertionError('Incorrect metadata shape accepted')
            wrong=vtk.vtkDoubleArray();wrong.SetNumberOfTuples(lagrange.GetNumberOfCells())
            for kind,expected in (('types','INVALID_CELL_TYPE_ARRAY_TYPE'),('indices','NONINTEGER_CELL_METADATA')):
                try:comparison._metadata_values(wrong,kind,lagrange.GetNumberOfCells())
                except comparison.ComparisonBlocked as exc:assert str(exc)==expected
                else:raise AssertionError('Noninteger metadata accepted')
            rows.append({'id':'native_metadata_materialization_preserves_values_and_bounds','status':'PASS'})
            active_stage='COMPONENT_DIAGNOSTICS'
            # Analytic reductions through the same production MAC, no EM solve.
            a=np.tile(np.array([1.,2j,3.]),(2,1));w=np.array([1.,3.])
            parts=comparison.component_diagnostics(a,3*np.exp(.8j)*a,w)
            assert all(abs(c['mac']-1)<1e-12 and abs(c['relative_phase_rad']-.8)<1e-12 for c in parts)
            assert np.allclose([c['left_volume_norm_fraction'] for c in parts],[1/14,4/14,9/14],rtol=0,atol=1e-12)
            rows.append({'id':'component_phase_scale_and_analytic_norm_shares','status':'PASS','components':parts})
            a=np.array([[1.,1.,0.],[1.,1.,0.]])+0j;b=a.copy();b[:,1]*=-1
            parts=comparison.component_diagnostics(a,b,w);vector,_=comparison.weighted_mac(a,b,w)
            assert vector<1e-12 and all(abs(c['mac']-1)<1e-12 for c in parts[:2]) and parts[2]['mac'] is None
            assert abs(parts[0]['relative_phase_rad'])<1e-12 and abs(abs(parts[1]['relative_phase_rad'])-math.pi)<1e-12
            assert comparison.validate_component_diagnostics(parts)<1e-12
            rows.append({'id':'component_phase_cancellation_cannot_be_averaged','status':'PASS',
                'vector_mac':vector,'components':parts})
            a=np.array([[1.,0.,0.],[0.,2.,0.]])+0j
            parts=comparison.component_diagnostics(a,a,w)
            assert abs(parts[0]['left_volume_norm_fraction']-1/13)<1e-12
            assert abs(parts[1]['left_volume_norm_fraction']-12/13)<1e-12
            rows.append({'id':'component_unequal_volume_weight_fractions','status':'PASS','components':parts})
            a=np.tile(np.array([1.,0.,0.]),(2,1));b=np.tile(np.array([0.,1.,0.]),(2,1))
            parts=comparison.component_diagnostics(a,b,w)
            assert all(c['mac'] is None and c['relative_phase_rad'] is None for c in parts)
            assert comparison.validate_component_diagnostics(parts)==0
            rows.append({'id':'component_missing_norm_is_not_a_zero_mac','status':'PASS','components':parts})
            a=np.tile(np.array([1.,2j,3.]),(2,1))
            parts=comparison.component_diagnostics(1e-150*a,1e150*np.exp(.8j)*a,w)
            assert all(abs(c['mac']-1)<1e-12 and abs(c['relative_phase_rad']-.8)<1e-12 for c in parts)
            rows.append({'id':'component_extreme_finite_global_scaling','status':'PASS'})
            a=np.tile(np.array([1.,1e-300,0.]),(2,1))
            parts=comparison.component_diagnostics(a,a,w)
            assert parts[1]['left_volume_norm_fraction']==0 and parts[1]['mac'] is None
            assert parts[1]['status']=='ZERO_OR_UNRESOLVED_COMPONENT_NORM'
            rows.append({'id':'component_norm_underflow_is_explicitly_unresolved','status':'PASS','components':parts})
            roots=(base/'xyz-left',base/'xyz-right');models=(fixture_model(1),fixture_model(2));native=[]
            for n,phase,scale in ((1,0.,1.),(2,.8,3.)):
                grid=analytic_grid(n);xyz=vtk_to_numpy(grid.GetPoints().GetData())
                values=xyz+np.array([1.,2.,3.])
                for name,factor in (('E_real',scale*math.cos(phase)),('E_imag',scale*math.sin(phase))):
                    grid.GetPointData().RemoveArray(name)
                    array=numpy_to_vtk(factor*values,deep=True);array.SetName(name);grid.GetPointData().AddArray(array)
                native.append(grid)
            manifests=[write_snapshot(root,grid,model) for root,grid,model in zip(roots,native,models)]
            xyz_result=comparison.compare_verified_fields(roots,manifests,models,
                ('FieldFixture','FieldFixture'),same_frame=True)
            assert xyz_result['status']==comparison.RECORDED and xyz_result['schema']==comparison.SCHEMA
            for direction in xyz_result['directions']:
                assert abs(direction['mac']-1)<1e-10
                assert all(abs(c['mac']-1)<1e-10 and abs(c['relative_phase_rad']-.8)<1e-10 for c in direction['components'])
            rows.append({'id':'xyz_affine_native_four_piece_subprocess','status':'PASS','result':xyz_result})
        return {'status':'PASS','execution_kind':'NATIVE_SOFTWARE_FIXTURE','substeps':rows,
                'reference_method':'Allemang complex MAC; positive volume weighting of visualization samples',
                'reference_type':'ANALYTIC_DERIVED_SOFTWARE_CROSSCHECK',
                'native_palace_execution':'NOT_RUN','scientific_qualification':'NOT_ESTABLISHED'}
    except Exception as exc:
        diagnostic=_failure_diagnostic(exc,active_stage)
        return {'status':'FAIL','reason':'UPSTREAM_MAC_FIXTURE_'+diagnostic['exception_type'],
                'execution_kind':'NATIVE_SOFTWARE_FIXTURE','substeps':rows,
                'failure_diagnostic':diagnostic,
                'native_palace_execution':'NOT_RUN','scientific_qualification':'NOT_ESTABLISHED'}
