/* Actual M19 renderers and event handlers in a JS VM; no browser/native claim. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const code=require('./ui_source.cjs')(path.join(__dirname,'../src/sqe_studio/web/app.js'));
new vm.Script(code);
const start=code.indexOf('function conditionalExtractionValid('),end=code.indexOf('async function inspectResult(',start);
assert(start>0&&end>start);
const job={id:'b'.repeat(32),engine:'sqdmetal_palace',revision_id:'c'.repeat(32)};
function extraction(){return {schema:'sqe.conditional-transmon-extraction.m19.v1',status:'CONDITIONAL_RESEARCH_MODEL_READY',
 parameter_origin:'EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS',scientific_qualification:'NOT_ESTABLISHED',
 reviewed_A01_transfer:'BLOCKED',fabrication:'HOLD',parameters:{EJ:15,EC:.2},EJ_over_EC:75,
 capacitances:{matrix_effective_F:95e-15,additional_junction_F:2e-15,total_F:97e-15},
 source:{run_id:job.id,revision_id:job.revision_id},source_result_metadata:{engine_version:'SOFTWARE_FIXTURE_ONLY',execution_kind:'SOFTWARE_FIXTURE'},
 extraction_sha256:'a'.repeat(64),assumptions:{junction_reference:'<script>fake</script>',josephson:{reference:'designer assumption'}},
 unresolved:['Mesh convergence unresolved'],native_source_hashes:{mesh_sha256:'d'.repeat(64)}};}
function envelope(){return {schema:'sqe.extraction-preview.m19.v1',expected_revision:'c'.repeat(32),solver_execution:'NOT_EXECUTED',extraction:extraction()};}
function context(){
 const elements={};
 const values={extractionCj:'2',extractionCjRef:'Test designer Cj assumption',extractionJType:'EJ_over_h',extractionJValue:'15',
  extractionJRef:'Test designer Josephson assumption',extractionNg:'0',extractionNcut:'15',extractionLevels:'4'};
 for(const [id,value] of Object.entries(values))elements[id]={value,isConnected:true,addEventListener(name,fn){this.listener=fn;}};
 for(const id of ['extractionAck','extractionPreview','extractionExecute','extractionFeedback'])elements[id]={checked:true,disabled:id==='extractionExecute',isConnected:true,textContent:'',innerHTML:'',addEventListener(name,fn){this.listener=fn;}};
 const ctx=vm.createContext({elements,$:id=>elements[id],project:{id:'9'.repeat(32),head:'c'.repeat(32)},
  selectedResult:{id:job.id},dirty:false,step:5,
  esc:x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  pane:(title,subtitle,body)=>`<section><h3>${title}</h3><p>${subtitle}</p>${body}</section>`,
  field:(description,id,value)=>`<label>${description}<input id="${id}" value="${value}"></label>`,
  toast:(...args)=>{ctx.lastToast=args},setTimeout:()=>{},refreshRuns:()=>{},
  loadProject:async id=>{ctx.loaded=id;ctx.project.head='e'.repeat(32)},
  api:async(...args)=>{ctx.lastRequest=args;return envelope()}});
 const utilities=code.slice(code.indexOf('const numeric='),code.indexOf('const componentInfo='));
 vm.runInContext(utilities+'\n'+code.slice(start,end),ctx);
 ctx.bindConditionalExtraction(job);return ctx;
}
let passed=0;
async function test(name,run){await run();passed++;console.log('PASS '+name);}
(async()=>{
 await test('renders actual extracted units and conditional status',()=>{
  const html=context().conditionalExtractionView(extraction());
  assert(html.includes('EC / h')&&html.includes('C total')&&html.includes('NOT_ESTABLISHED')&&html.includes('HOLD'));
  assert(html.includes('constructed software fixture')&&html.includes('no Palace'));
 });
 await test('designer provenance is escaped',()=>{
  const html=context().conditionalExtractionView(extraction());assert(!html.includes('<script>fake'));
  assert(html.includes('&lt;script&gt;fake'));
 });
 await test('scientific promotion and malformed scalars are rejected',()=>{
  for(const [field,value] of [['fabrication','GO'],['scientific_qualification','PASS'],['reviewed_A01_transfer','APPROVED'],['EJ_over_EC',NaN]]){
   const e=extraction();e[field]=value;assert.equal(context().conditionalExtractionValid(e),false);
  }
  const e=extraction();e.parameters.EC=-1;assert.equal(context().conditionalExtractionValid(e),false);
 });
 await test('zero additional Cj remains valid and visible',()=>{
  const e=extraction();e.capacitances.additional_junction_F=0;assert(context().conditionalExtractionValid(e));
 });
 await test('launcher requires actual screened capacitance result',()=>{
  const c=context();assert(c.conditionalExtractionLauncher(job,{status:'NUMERICAL_SCREEN_ONLY'}).includes('extractionCj'));
  assert.equal(c.conditionalExtractionLauncher({...job,engine:'scqubits'},{status:'NUMERICAL_SCREEN_ONLY'}),'');
  assert.equal(c.conditionalExtractionLauncher(job,{status:'BLOCKED_NO_SAVED_SELECTION'}),'');
 });
 await test('junction physical values are not prefilled',()=>{
  const html=context().conditionalExtractionLauncher(job,{status:'NUMERICAL_SCREEN_ONLY'});
  assert(html.includes('id="extractionCj" value=""')&&html.includes('id="extractionJValue" value=""'));
 });
 await test('LJ quantity uses nH with explicit provenance',()=>{
  const c=context();c.elements.extractionJType.value='LJ';const d=c.readConditionalExtractionDeclaration();
  assert.equal(d.josephson.unit,'nH');assert.equal(d.josephson.quantity,'LJ');assert.equal(d.junction_capacitance_fF,2);
 });
 await test('no preview request without acknowledgment',async()=>{
  const c=context();c.elements.extractionAck.checked=false;await c.elements.extractionPreview.onclick();
  assert.equal(c.lastRequest,undefined);assert(c.elements.extractionExecute.disabled);
 });
 await test('dirty project blocks request',async()=>{
  const c=context();c.dirty=true;await c.elements.extractionPreview.onclick();assert.equal(c.lastRequest,undefined);
 });
 await test('preview sends identities and assumptions without copied EC/matrix',async()=>{
  const c=context();await c.elements.extractionPreview.onclick();const [url,method,body]=c.lastRequest;
  assert.equal(method,'POST');assert(url.endsWith('/'+job.id+'/extraction'));
  assert.equal(body.expected_revision,'c'.repeat(32));assert.equal(body.action,'preview');
  assert.deepEqual(Object.keys(body).sort(),['action','declaration','expected_revision']);
  assert(!JSON.stringify(body).includes('maxwell_matrix'));assert.equal(c.elements.extractionExecute.disabled,false);
 });
 await test('changed assumptions invalidate prior preview',async()=>{
  const c=context();await c.elements.extractionPreview.onclick();c.elements.extractionCj.value='3';c.elements.extractionCj.listener();
  assert(c.elements.extractionExecute.disabled);
  c.lastRequest=null;await c.elements.extractionExecute.onclick();assert.equal(c.lastRequest,null);
 });
 await test('mismatched source cannot enable execution',async()=>{
  const c=context();c.api=async()=>{const e=envelope();e.extraction.source.run_id='f'.repeat(32);return e};
  await c.elements.extractionPreview.onclick();assert(c.elements.extractionExecute.disabled);
 });
 await test('stale async preview is ignored',async()=>{
  const c=context();let resolve;c.api=()=>new Promise(r=>{resolve=r});
  const pending=c.elements.extractionPreview.onclick();c.project.head='f'.repeat(32);resolve(envelope());await pending;
  assert(c.elements.extractionExecute.disabled);assert.equal(c.elements.extractionFeedback.innerHTML,'');
 });
 await test('typing during async preview keeps execution disabled',async()=>{
  const c=context();let resolve;c.api=()=>new Promise(r=>{resolve=r});const pending=c.elements.extractionPreview.onclick();
  c.elements.extractionNg.listener();resolve(envelope());await pending;assert(c.elements.extractionExecute.disabled);
 });
 await test('queue uses previewed assumptions and reloads new revision',async()=>{
  const c=context();await c.elements.extractionPreview.onclick();
  c.api=async(...args)=>{c.lastRequest=args;return {schema:'sqe.extraction-execution.m19.v1',fabrication:'HOLD',revision:'e'.repeat(32),run_id:'f'.repeat(32)}};
  await c.elements.extractionExecute.onclick();assert.equal(c.lastRequest[2].action,'execute');
  assert.equal(c.loaded,'9'.repeat(32));assert.equal(c.step,5);
 });
 await test('Koch diagnostics show approximation rather than a measured target',()=>{
  const e=extraction();e.spectrum_diagnostics={status:'NUMERICAL_PASS',checks:[{quantity:'f01',actual:4.7,reference:4.69,relative_error:.002}]};
  const html=context().conditionalExtractionView(e);assert(html.includes('Koch')&&html.includes('device agreement remains unestablished'));
 });
 await test('independent editor does not read derived study inputs',()=>{
  const c=context(),model={studies:[{id:'extracted_transmon_01',engine:'scqubits',kind:'extracted_transmon_research',inputs:{}}]};
  c.activeModel=()=>model;
  vm.runInContext(code.slice(code.indexOf('function currentStudy('),code.indexOf('\n',code.indexOf('function currentStudy('))),c);
  assert.equal(c.currentStudy('scqubits'),null);
 });
 await test('applying independent parameters preserves derived research studies',()=>{
  const c=context(),derived={id:'extracted_transmon_01',engine:'scqubits',kind:'extracted_transmon_research',inputs:{schema:'typed-derived'}};
  const model={studies:[derived]};c.activeModel=()=>model;c.markDirty=()=>{};
  vm.runInContext(code.slice(code.indexOf('function setStudy('),code.indexOf('function markDirty(',code.indexOf('function setStudy('))),c);
  c.setStudy('scqubits','spectrum',{source:'independent'});
  assert.equal(model.studies.length,2);assert.equal(model.studies[0],derived);assert.equal(model.studies[1].inputs.source,'independent');
 });
 await test('generic parameter exploration excludes source-bound research',()=>{
  const c=context();vm.runInContext(code.slice(code.indexOf('function sweepableInputs('),code.indexOf('function designExplorationControls(')),c);
  assert.equal(c.sweepableInputs({kind:'extracted_transmon_research',inputs:{assumptions:{EC:.2}}}).length,0);
  assert.equal(c.sweepableInputs({kind:'spectrum',inputs:{parameters:{EC:.2}}}).length,1);
 });
 await test('Quantum page exposes the saved research source',()=>{
  const c=context();c.activeModel=()=>({studies:[{id:'extracted_transmon_01',engine:'scqubits',kind:'extracted_transmon_research',inputs:{source:{run_id:job.id},assumptions:{josephson:{quantity:'LJ'}}}}]});
  vm.runInContext(code.slice(code.indexOf('function conditionalExtractionStudies('),code.indexOf('function conditionalExtractionValid(')),c);
  const html=c.conditionalExtractionStudies();assert(html.includes(job.id)&&html.includes('extracted_transmon_01')&&html.includes('viewExtractionRuns'));
 });
 console.log(JSON.stringify({framework:'JS_VM_ACTUAL_PRODUCTION_FUNCTIONS',renderer_and_request_tests_passed:passed,
  browser_execution:'NOT_RUN',native_execution:'NOT_RUN'}));
})().catch(error=>{console.error(error);process.exitCode=1});
