function fieldCorrelationValid(d){
 const fixed={method:'VOLUME_WEIGHTED_CELL_CENTER_COMPLEX_MAC',
  coordinate_assumption:'SAME_UNROTATED_SAVED_MODEL_FRAME_DIAGNOSTIC_ONLY',physical_mode_identity:'UNRESOLVED',
  mesh_convergence:'NOT_ESTABLISHED',scientific_qualification:'NOT_ESTABLISHED',material_weighting:'NONE_VOLUME_ONLY',
  em_to_hamiltonian:'BLOCKED',fabrication:'HOLD',field_values_exported:false};
 if(!d||!['sqe.upstream-field-correlation.experimental.v1','sqe.upstream-field-correlation.experimental.v2',
    'sqe.upstream-field-correlation.experimental.v3'].includes(d.schema)||
    Object.entries(fixed).some(([k,v])=>d[k]!==v)||
    !['SAMPLED_FIELD_CORRELATION_RECORDED','BLOCKED','FAIL'].includes(d.status)||
    typeof d.reason_code!=='string'||!/^\b[A-Z][A-Z0-9_]{2,79}$/.test(d.reason_code))return false;
 if(d.schema!=='sqe.upstream-field-correlation.experimental.v1'&&!fieldGridDiagnosticsValid(d))return false;
 if(d.schema==='sqe.upstream-field-correlation.experimental.v1'&&'grid_diagnostics' in d)return false;
 if(d.status!=='SAMPLED_FIELD_CORRELATION_RECORDED')return Array.isArray(d.sources)&&d.sources.length===0&&
  Array.isArray(d.directions)&&d.directions.length===0&&d.mac_gap===null&&d.vtk_version===null;
 const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
 if(!Array.isArray(d.sources)||d.sources.length!==2||!Array.isArray(d.directions)||d.directions.length!==2||
    typeof d.vtk_version!=='string'||!/^[0-9A-Za-z_.+-]{1,32}$/.test(d.vtk_version))return false;
 for(let i=0;i<2;i++){
  const s=d.sources[i],v=d.directions[i];
  const directionKeys=['sampling_mesh','mac','relative_phase_rad','sample_count','coverage_fraction',
   'sampled_volume_m3_assuming_declared_units'];
  if(d.schema==='sqe.upstream-field-correlation.experimental.v3')directionKeys.push('components');
  if(!v||Object.keys(v).length!==directionKeys.length||!directionKeys.every(k=>Object.hasOwn(v,k)))return false;
  if(!s||!v||!['result_manifest_sha256','project_sha256','mesh_sha256','eig_sha256','pvd_sha256'].every(k=>hash(s[k]))||
     typeof s.revision_id!=='string'||!/^[a-f0-9]{32}$/.test(s.revision_id)||
     typeof s.study_id!=='string'||!/^[A-Za-z0-9_.-]{1,64}$/.test(s.study_id)||
     !Number.isInteger(s.cycle_index)||s.cycle_index<0||s.cycle_index>11||
     !Number.isInteger(s.mpi_piece_count)||s.mpi_piece_count<1||s.mpi_piece_count>16||
     !Array.isArray(s.piece_sha256)||s.piece_sha256.length!==s.mpi_piece_count||!s.piece_sha256.every(hash)||
     !Number.isInteger(s.cell_count)||s.cell_count<1||s.cell_count>1000000||
     !Number.isInteger(s.point_count)||s.point_count<1||s.point_count>2000000||
     !Number.isInteger(s.ghost_cells_removed)||s.ghost_cells_removed<0||s.ghost_cells_removed>1000000||
     !Number.isFinite(s.declared_length_unit_m)||s.declared_length_unit_m<1e-12||s.declared_length_unit_m>1||
     v.sampling_mesh!==(i?'right':'left')||v.sample_count!==s.cell_count||v.coverage_fraction!==1||
     !Number.isFinite(v.mac)||v.mac<0||v.mac>1||
     (v.relative_phase_rad!==null&&(!Number.isFinite(v.relative_phase_rad)||Math.abs(v.relative_phase_rad)>Math.PI))||
     ((v.mac<=1e-28)!==(v.relative_phase_rad===null))||
     !Number.isFinite(v.sampled_volume_m3_assuming_declared_units)||v.sampled_volume_m3_assuming_declared_units<=0)return false;
  if(d.schema==='sqe.upstream-field-correlation.experimental.v3'&&!fieldComponentDiagnosticsValid(v.components,v.mac))return false;
 }
 return d.sources[0].mesh_sha256!==d.sources[1].mesh_sha256&&
  d.sources[0].declared_length_unit_m===d.sources[1].declared_length_unit_m&&Number.isFinite(d.mac_gap)&&
  Math.abs(d.mac_gap-Math.abs(d.directions[0].mac-d.directions[1].mac))<=1e-12;
}
function fieldComponentDiagnosticsValid(rows,vectorMac){
 const keys=['axis','left_volume_norm_fraction','right_volume_norm_fraction','status','mac','relative_phase_rad'];
 if(!Array.isArray(rows)||rows.length!==3)return false;
 let leftTotal=0,rightTotal=0,re=0,im=0;
 for(let k=0;k<3;k++){
  const r=rows[k];
  if(!r||Object.keys(r).length!==keys.length||!keys.every(key=>Object.hasOwn(r,key))||r.axis!==['x','y','z'][k])return false;
  const a=r.left_volume_norm_fraction,b=r.right_volume_norm_fraction;
  if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<0||a>1||b>1)return false;
  leftTotal+=a;rightTotal+=b;
  if(a===0||b===0){
   if(r.status!=='ZERO_OR_UNRESOLVED_COMPONENT_NORM'||r.mac!==null||r.relative_phase_rad!==null)return false;
  }else{
   if(r.status!=='SAMPLED_COMPONENT_CORRELATION_RECORDED'||!Number.isFinite(r.mac)||r.mac<0||r.mac>1||
      ((r.mac<=1e-28)!==(r.relative_phase_rad===null))||
      (r.relative_phase_rad!==null&&(!Number.isFinite(r.relative_phase_rad)||Math.abs(r.relative_phase_rad)>Math.PI)))return false;
   if(r.relative_phase_rad!==null){const magnitude=Math.sqrt(a*b*r.mac);
    re+=magnitude*Math.cos(r.relative_phase_rad);im+=magnitude*Math.sin(r.relative_phase_rad);}
  }
 }
 return Math.abs(leftTotal-1)<=1e-12&&Math.abs(rightTotal-1)<=1e-12&&Math.abs(re*re+im*im-vectorMac)<=1e-10;
}
function fieldGridDiagnosticsValid(d){
 const grids=d.grid_diagnostics,recorded=d.status==='SAMPLED_FIELD_CORRELATION_RECORDED';
 if(!Array.isArray(grids)||grids.length>2||(recorded&&grids.length!==2))return false;
 const keys=['side','result_manifest_sha256','cycle_index','cell_count','point_count',
  'nodes_per_cell_min','nodes_per_cell_max','geometry_view','cell_types'];
 for(let i=0;i<grids.length;i++){
  const g=grids[i];
  if(!g||Object.keys(g).length!==keys.length||!keys.every(k=>Object.hasOwn(g,k))||g.side!==(i?'right':'left')||
     typeof g.result_manifest_sha256!=='string'||!/^[a-f0-9]{64}$/.test(g.result_manifest_sha256))return false;
  for(const [k,lo,hi] of [['cycle_index',0,11],['cell_count',1,1000000],['point_count',1,2000000],
   ['nodes_per_cell_min',1,4096],['nodes_per_cell_max',1,4096]]){
   if(!Number.isInteger(g[k])||g[k]<lo||g[k]>hi)return false;
  }
  if(g.nodes_per_cell_min>g.nodes_per_cell_max||!Array.isArray(g.cell_types)||g.cell_types.length<1||g.cell_types.length>16)return false;
  let total=0,last=-1;
  for(const t of g.cell_types){
   if(!t||Object.keys(t).length!==2||!Number.isInteger(t.vtk_type_id)||t.vtk_type_id<=last||t.vtk_type_id>255||
      !Number.isInteger(t.count)||t.count<1||t.count>1000000)return false;
   total+=t.count;last=t.vtk_type_id;
  }
  if(total!==g.cell_count)return false;
  const linear=g.nodes_per_cell_min===4&&g.nodes_per_cell_max===4;
  const expected=g.cell_types.length===1&&g.cell_types[0].vtk_type_id===10&&linear?'NATIVE_LINEAR_TETRA':
   g.cell_types.every(t=>[10,71].includes(t.vtk_type_id))&&linear?'ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW':'UNSUPPORTED_CELL_GEOMETRY';
  if(g.geometry_view!==expected)return false;
  if(recorded){const s=d.sources?.[i];if(!s||expected==='UNSUPPORTED_CELL_GEOMETRY'||
   ['result_manifest_sha256','cycle_index','cell_count','point_count'].some(k=>g[k]!==s[k]))return false;}
 }
 return true;
}
function fieldCorrelationEnvelopeValid(data,left,right){
 if(data?.schema!=='sqe.upstream-field-comparison-response.v1'||data.scientific_approval!=='NOT_ESTABLISHED'||
    data.fabrication!=='HOLD'||!fieldCorrelationValid(data.diagnostic))return false;
 return [left,right].every((job,i)=>{
  const side=i?data.right:data.left;
  if(!side||side.run_id!==job.id||side.revision_id!==job.revision_id||side.study_id!==job.study_id||
     !/^[a-f0-9]{64}$/.test(side.project_sha256)||!/^[a-f0-9]{64}$/.test(side.result_manifest_sha256))return false;
  const native=data.diagnostic.sources[i];
  const grid=data.diagnostic.grid_diagnostics?.[i];
  return (!grid||grid.result_manifest_sha256===side.result_manifest_sha256)&&
   (!native||['revision_id','study_id','project_sha256','result_manifest_sha256'].every(k=>native[k]===side[k]));
 });
}
