/* Production renderer/request guards in a JS VM; no real-browser claim. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const code=require('./ui_source.cjs')(path.join(__dirname,'../src/sqe_studio/web/app.js'));
new vm.Script(code);
const start=code.indexOf('function fieldCorrelationValid(d)'),end=code.indexOf('function compareControls()',start);
assert(start>0&&end>start);
function diagnostic(){
 const d={schema:'sqe.upstream-field-correlation.experimental.v1',method:'VOLUME_WEIGHTED_CELL_CENTER_COMPLEX_MAC',
  coordinate_assumption:'SAME_UNROTATED_SAVED_MODEL_FRAME_DIAGNOSTIC_ONLY',physical_mode_identity:'UNRESOLVED',
  mesh_convergence:'NOT_ESTABLISHED',scientific_qualification:'NOT_ESTABLISHED',material_weighting:'NONE_VOLUME_ONLY',
  em_to_hamiltonian:'BLOCKED',fabrication:'HOLD',field_values_exported:false,
  status:'SAMPLED_FIELD_CORRELATION_RECORDED',reason_code:'DISCRETE_STATISTIC_ONLY_NOT_MODE_IDENTIFICATION',
  sources:[],directions:[],mac_gap:0,vtk_version:'9.3.1'};
 for(let i=0;i<2;i++){
  d.sources.push({result_manifest_sha256:'a'.repeat(64),project_sha256:'b'.repeat(64),revision_id:'c'.repeat(32),
   mesh_sha256:String(i+1).repeat(64),eig_sha256:'d'.repeat(64),pvd_sha256:'e'.repeat(64),study_id:'ResEigen',
   cycle_index:0,mpi_piece_count:4,piece_sha256:Array(4).fill('f'.repeat(64)),cell_count:i?40:5,point_count:48,
   ghost_cells_removed:0,declared_length_unit_m:1});
  d.directions.push({sampling_mesh:i?'right':'left',mac:1,relative_phase_rad:.8,sample_count:i?40:5,
   coverage_fraction:1,sampled_volume_m3_assuming_declared_units:1});
 }
 return d;
}
const jobs=['1','2'].map(i=>({id:i.repeat(32),revision_id:'c'.repeat(32),study_id:'ResEigen',engine:'sqdmetal_palace'}));
function envelope(d=diagnostic()){
 const side=i=>({run_id:jobs[i].id,revision_id:jobs[i].revision_id,study_id:'ResEigen',
  project_sha256:'b'.repeat(64),result_manifest_sha256:'a'.repeat(64)});
 return {schema:'sqe.upstream-field-comparison-response.v1',left:side(0),right:side(1),diagnostic:d,
  scientific_approval:'NOT_ESTABLISHED',fabrication:'HOLD'};
}
function diagnosticV2(){
 const d=diagnostic();d.schema='sqe.upstream-field-correlation.experimental.v2';
 d.grid_diagnostics=d.sources.map((s,i)=>({side:i?'right':'left',result_manifest_sha256:s.result_manifest_sha256,
  cycle_index:s.cycle_index,cell_count:s.cell_count,point_count:s.point_count,nodes_per_cell_min:4,nodes_per_cell_max:4,
  geometry_view:'ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW',cell_types:[{vtk_type_id:71,count:s.cell_count}]}));
 return d;
}
function blockedGeometry(){
 const d=diagnosticV2();Object.assign(d,{status:'BLOCKED',reason_code:'LINEAR_TETRAHEDRA_REQUIRED',
  directions:[],sources:[],mac_gap:null,vtk_version:null});
 d.grid_diagnostics=d.grid_diagnostics.slice(0,1);
 Object.assign(d.grid_diagnostics[0],{nodes_per_cell_min:10,nodes_per_cell_max:10,geometry_view:'UNSUPPORTED_CELL_GEOMETRY'});
 return d;
}
function diagnosticV3(){
 const d=diagnosticV2();d.schema='sqe.upstream-field-correlation.experimental.v3';
 d.directions.forEach(v=>{v.components=['x','y','z'].map((axis,k)=>({axis,
  left_volume_norm_fraction:k?0:1,right_volume_norm_fraction:k?0:1,
  status:k?'ZERO_OR_UNRESOLVED_COMPONENT_NORM':'SAMPLED_COMPONENT_CORRELATION_RECORDED',
  mac:k?null:1,relative_phase_rad:k?null:.8}));});
 return d;
}
function cancellationV3(){
 const d=diagnosticV3();d.directions.forEach(v=>{
  v.mac=0;v.relative_phase_rad=null;
  for(let k=0;k<2;k++)Object.assign(v.components[k],{left_volume_norm_fraction:.5,right_volume_norm_fraction:.5,
   status:'SAMPLED_COMPONENT_CORRELATION_RECORDED',mac:1,relative_phase_rad:k?Math.PI:0});
 });return d;
}
function context(){
 const elements={compareLeft:{value:jobs[0].id},compareRight:{value:jobs[1].id},
  compareFieldsLeftCycle:{value:''},compareFieldsRightCycle:{value:''},compareFieldsFrame:{checked:true},
  fieldComparisonView:{innerHTML:'',textContent:'',replaceChildren(){this.innerHTML='';this.textContent='';}}};
 const ctx=vm.createContext({elements,project:{id:'9'.repeat(32),head:'c'.repeat(32)},step:5,
  runHistoryRequestToken:2,comparisonRequestToken:0,$:id=>elements[id],
  comparisonRunEligible:id=>jobs.find(j=>j.id===id),
  esc:x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  pane:(title,subtitle,body)=>`<section><h3>${title}</h3><p>${subtitle}</p>${body}</section>`,
  toast:(...args)=>{ctx.lastToast=args;},api:async(...args)=>{ctx.lastRequest=args;return envelope();}});
 vm.runInContext(code.slice(start,end),ctx);return ctx;
}
let passed=0;
async function test(name,run){await run();passed++;console.log('PASS '+name);}
(async()=>{
 await test('renders two directions and scientific limits',()=>{
  const c=context(),html=c.fieldCorrelationView(diagnostic());
  assert(html.includes('MAC (|correlation|²)')&&html.includes('100%')&&html.includes('Physical')===false);
  assert(html.includes('physical mode correspondence')&&html.includes('Fabrication HOLD'));
  assert(html.includes('output 1 (not a mode)')&&html.includes('4 MPI pieces'));
 });
 await test('zero-correlation phase is explicitly undefined',()=>{
  const d=diagnostic();d.directions.forEach(v=>{v.mac=0;v.relative_phase_rad=null;});
  assert(context().fieldCorrelationView(d).includes('Undefined at zero correlation'));
 });
 await test('blocked and failed results expose the reason',()=>{
  for(const status of ['BLOCKED','FAIL']){
   const d=diagnostic();Object.assign(d,{status,reason_code:'INCOMPLETE_CROSS_MESH_COVERAGE',sources:[],directions:[],mac_gap:null,vtk_version:null});
   assert(context().fieldCorrelationView(d).includes('INCOMPLETE_CROSS_MESH_COVERAGE'));
  }
 });
 await test('scientific promotion is rejected',()=>{
  for(const [k,v] of [['mesh_convergence','PASS'],['fabrication','GO'],['field_values_exported',true],['physical_mode_identity','VERIFIED']]){
   const d=diagnostic();d[k]=v;assert.throws(()=>context().fieldCorrelationView(d));
  }
 });
 await test('nonfinite statistics and partial coverage rejected',()=>{
  for(const [k,v] of [['mac',NaN],['mac',1.01],['coverage_fraction',.9],['sample_count',true]]){
   const d=diagnostic();d.directions[0][k]=v;assert.equal(context().fieldCorrelationValid(d),false);
  }
 });
 await test('forged source hash or run identity rejected',()=>{
  for(const field of ['run_id','revision_id','project_sha256','result_manifest_sha256']){
   const e=envelope();e.right[field]='0'.repeat(field.includes('sha256')?64:32);
   assert.equal(context().fieldCorrelationEnvelopeValid(e,...jobs),false);
  }
 });
 await test('POST carries normal API arguments and output number conversion',async()=>{
  const c=context();c.elements.compareFieldsLeftCycle.value='2';
  await c.compareSavedFields();
  assert.equal(c.lastRequest[1],'POST');assert.equal(c.lastRequest[2].left_cycle,1);
  assert.equal(c.lastRequest[2].right_cycle,null);assert.equal(c.lastRequest[2].same_frame_assumption,true);
  assert(c.elements.fieldComparisonView.innerHTML.includes('MAC (|correlation|²)'));
 });
 await test('no field request without explicit coordinate assumption',async()=>{
  const c=context();c.elements.compareFieldsFrame.checked=false;await c.compareSavedFields();
  assert(!c.lastRequest);assert(c.lastToast[0].includes('same-frame'));
 });
 await test('invalid output numbers fail before requesting native work',async()=>{
  for(const v of ['0','13','1.5','bad']){
   const c=context();c.elements.compareFieldsRightCycle.value=v;await c.compareSavedFields();assert(!c.lastRequest);
  }
 });
 for(const [label,change] of [
  ['project',c=>c.project.id='8'.repeat(32)],['revision',c=>c.project.head='0'.repeat(32)],
  ['step',c=>c.step=3],['history',c=>c.runHistoryRequestToken++],
  ['selection',c=>c.elements.compareRight.value=jobs[0].id],
  ['output',c=>c.elements.compareFieldsLeftCycle.value='2'],['assumption',c=>c.elements.compareFieldsFrame.checked=false]
 ])await test('stale '+label+' response does not repaint',async()=>{
  const c=context();let resolve;c.api=()=>new Promise(r=>{resolve=r;});
  const pending=c.compareSavedFields();change(c);resolve(envelope());await pending;
  assert.equal(c.elements.fieldComparisonView.innerHTML,'');
 });
 await test('server provenance failure clears output',async()=>{
  const c=context(),bad=envelope();bad.diagnostic.sources[1].project_sha256='0'.repeat(64);
  c.api=async()=>bad;await c.compareSavedFields();assert.equal(c.elements.fieldComparisonView.innerHTML,'');
  assert(c.lastToast[0].includes('provenance'));
 });
 await test('version two shows actual Lagrange type and four-node proof',()=>{
  const html=context().fieldCorrelationView(diagnosticV2());
  assert(html.includes('Native cell geometry')&&html.includes('VTK 71')&&html.includes('4–4'));
  assert(html.includes('shared linear geometry view'));
 });
 await test('mixed first-order representations remain explicit',()=>{
  const d=diagnosticV2();d.grid_diagnostics[0].cell_types=[{vtk_type_id:10,count:4},{vtk_type_id:71,count:1}];
  assert(context().fieldCorrelationView(d).includes('VTK 10: 4 / VTK 71: 1'));
 });
 await test('blocked geometry keeps observed node counts without numeric evidence',()=>{
  const html=context().fieldCorrelationView(blockedGeometry());
  assert(html.includes('10–10')&&html.includes('comparison blocked')&&html.includes('LINEAR_TETRAHEDRA_REQUIRED'));
  assert(!html.includes('<th>MAC'));
 });
 await test('categorical counts and linear-view claims cannot be forged',()=>{
  for(const alter of [g=>g.cell_types[0].count--,g=>g.geometry_view='NATIVE_LINEAR_TETRA',
    g=>g.nodes_per_cell_max=10,g=>g.coordinates=[[1,2,3]],g=>g.cell_types[0].vtk_type_id='<script>']){
   const d=diagnosticV2();alter(d.grid_diagnostics[0]);assert.equal(context().fieldCorrelationValid(d),false);
  }
 });
 await test('legacy schema cannot silently carry new metadata',()=>{
  const d=diagnostic();d.grid_diagnostics=[];assert.equal(context().fieldCorrelationValid(d),false);
 });
 await test('blocked grid metadata still binds to requested manifest',()=>{
  const e=envelope(blockedGeometry());e.diagnostic.grid_diagnostics[0].result_manifest_sha256='0'.repeat(64);
  assert.equal(context().fieldCorrelationEnvelopeValid(e,...jobs),false);
 });
 await test('unsupported geometry cannot accompany recorded numeric values',()=>{
  const d=diagnosticV2();Object.assign(d.grid_diagnostics[0],
   {nodes_per_cell_min:10,nodes_per_cell_max:10,geometry_view:'UNSUPPORTED_CELL_GEOMETRY'});
  assert.equal(context().fieldCorrelationValid(d),false);
 });
 await test('v3 renders XYZ norms and explicit zero norm availability',()=>{
  const html=context().fieldCorrelationView(diagnosticV3());
  assert(html.includes('XYZ component diagnostics')&&html.includes('Undefined: zero or unresolved norm'));
  assert(html.includes('not energy or EPR')&&html.includes('must not be averaged'));
 });
 await test('component cancellation preserves vector zero and component ones',()=>{
  const d=cancellationV3();assert(context().fieldCorrelationValid(d));
  assert(context().fieldCorrelationView(d).includes('XYZ component diagnostics'));
 });
 await test('component vocabulary axes fractions and extra private data are rejected',()=>{
  for(const alter of [r=>r.pop(),r=>r[0].axis='y',r=>r[0].coordinates=[[1,2,3]],
   r=>r[0].left_volume_norm_fraction=.8,r=>r[0].left_volume_norm_fraction=true,
   r=>r[0].axis='<script>',r=>r[0].mac=NaN]){
   const d=diagnosticV3();alter(d.directions[0].components);assert.equal(context().fieldCorrelationValid(d),false);
  }
 });
 await test('component norm absence cannot invent MAC or phase',()=>{
  for(const [key,value] of [['mac',0],['relative_phase_rad',0],['status','SAMPLED_COMPONENT_CORRELATION_RECORDED']]){
   const d=diagnosticV3();d.directions[0].components[1][key]=value;assert.equal(context().fieldCorrelationValid(d),false);
  }
 });
 await test('component phases must reconstruct vector MAC',()=>{
  const d=cancellationV3();d.directions[0].components[1].relative_phase_rad=0;
  assert.equal(context().fieldCorrelationValid(d),false);
 });
 await test('legacy versions cannot silently carry v3 component fields',()=>{
  for(const d of [diagnostic(),diagnosticV2()]){
   d.directions[0].components=diagnosticV3().directions[0].components;
   assert.equal(context().fieldCorrelationValid(d),false);
  }
 });
 await test('normal saved-run request accepts a provenance-bound v3 response',async()=>{
  const c=context();c.api=async()=>envelope(diagnosticV3());await c.compareSavedFields();
  assert(c.elements.fieldComparisonView.innerHTML.includes('XYZ component diagnostics'));
 });
 await test('v3 scientific flags remain fixed',()=>{
  const d=diagnosticV3();d.mesh_convergence='PASS';assert.equal(context().fieldCorrelationValid(d),false);
 });
 console.log(JSON.stringify({renderer_and_request_tests_passed:passed,execution_kind:'SOFTWARE_FIXTURE',real_browser:'NOT_RUN'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
