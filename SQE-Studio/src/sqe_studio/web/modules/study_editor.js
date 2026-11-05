function designExplorationControls(){
 const studies=activeModel().studies.filter(s=>engineValidated(s.engine)&&sweepableInputs(s).length);
 if(!studies.length)return pane('Parametric design exploration','Vary saved physical model inputs using installed native engines; no reduced-order optimizer or inferred solution.',
  '<p class="helper">Create a validated native study in EM or Quantum models to enable a sequential laptop sweep. Existing design targets remain distinct from solver measurements.</p>');
 const selected=studies.find(s=>s.id===explorationStudyId)||studies[0],axes=sweepableInputs(selected);
 return pane('Native parametric exploration','Explore physical design choices against targets; use the same revision-bound native solver with sequential execution.',`
  <div class="row">${selection('exploreStudy','Saved native study',studies.map(s=>[s.id,s.id+' · '+s.engine]),selected.id)}${selection('exploreAxis','Numerical input',axes.map(([k,v])=>[k,k+' (currently '+v+')']),axes[0]?.[0])}</div>
  <div class="row">${field('Sweep values · comma separated','exploreValues',axes[0]?[axes[0][1]*0.95,axes[0][1],axes[0][1]*1.05].map(x=>Number(x.toPrecision(8))).join(', '):'')}${selection('exploreMode','Execution',[['automatic','Sequential native sweep'],['manual','One explicitly selected point']],'automatic')}${numeric('exploreIndex','Manual point index (0-based)',0)}</div>
  <div class="button-stack"><button class="primary" id="startExploration" ${dirty?'disabled':''}>Run native variation →</button></div>
  <p class="helper">Up to 24 points, 1–3 numeric axes (this editor offers one). Only existing study.inputs values may vary. Geometry changes require a new project revision; no automatic mode matching, fitness score or scientific validation.</p>`);
}
async function runExploration(){try{
 if(dirty)throw Error('Save the revision first');
 const studyId=readText('exploreStudy');const s=activeModel().studies.find(s=>s.id===studyId);if(!s||!engineValidated(s.engine))throw Error('Native engine unavailable');
 const axis=readText('exploreAxis'),values=readText('exploreValues').split(',').map(v=>{if(!v.trim()||!Number.isFinite(Number(v)))throw Error('Sweep requires finite numeric points');return Number(v)});
 if(values.length>24||!values.length)throw Error('Sweep must have 1–24 values');
 const mode=readText('exploreMode'),body={revision:project.head,study_id:s.id,axes:{[axis]:values},mode};
 if(mode==='manual')body.selected=readNumber('exploreIndex',{integer:true,min:0,max:values.length-1});
 const answer=await api(`/api/projects/${project.id}/sweeps`,'POST',body);
 toast('Native parameter exploration queued: '+answer.run_id.slice(0,8));await loadProject(project.id);setTimeout(refreshRuns,1600);
 }catch(e){toast(e.message,true)}}

function wireStep(id){
 if(expert && $('applyExpert'))$('applyExpert').onclick=()=>{try{const data=JSON.parse($('expertJson').value);if(data.schema!=='sqe.project.v1'||Object.keys(data).sort().join(',')!=='family,intent,layout,name,notes,process,schema,schematic,studies')throw Error('Unsupported project schema or extra fields');project.model=data;markDirty();render();toast('Advanced draft applied; save to validate on server')}catch(err){toast(err.message,true)}};
 document.querySelectorAll('[data-remove-target]').forEach(b=>b.onclick=()=>{activeModel().intent.targets.splice(Number(b.dataset.removeTarget),1);markDirty();render()});
 document.querySelectorAll('[data-remove-component]').forEach(b=>b.onclick=()=>{activeModel().layout.components.splice(Number(b.dataset.removeComponent),1);clearPhysicalReview();markDirty();render()});
 wireRunControls();
 if($('compareRuns'))wireCompareControls();
 if(id==='intent'){
  $('addTarget').onclick=()=>{let t={name:$('targetName').value,value:Number($('targetValue').value),unit:$('targetUnit').value,tolerance:Number($('targetTolerance').value)};
   if(!t.name||!t.unit||!Number.isFinite(t.value)||t.tolerance<0) return toast('Enter a valid target and tolerance',true);activeModel().intent.targets.push(t);markDirty();render()};
  $('intentNotes').oninput=e=>{activeModel().intent.notes=e.target.value;markDirty()};
 }
 if(id==='schematic'){wireCanvas();$('addElement').onclick=()=>{
  const e={id:$('elementId').value,type:$('elementType').value,a:$('nodeA').value,b:$('nodeB').value,value:Number($('elementValue').value),unit:$('elementUnit').value};
  if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(e.id)||!e.a||!e.b||e.a===e.b||!Number.isFinite(e.value)||e.value<=0||activeModel().schematic.elements.some(x=>x.id===e.id))return toast('Invalid component, duplicate ID, or coincident terminals',true);
  activeModel().schematic.elements.push(e);activeModel().schematic.nodes=[...new Set([...activeModel().schematic.nodes,e.a,e.b])];markDirty();render()};}
 if(id==='layout'){
  wireCanvas();
  for(const [input,model] of [['chipWidth','width_mm'],['chipHeight','height_mm'],['chipThickness','thickness_um']])$(input).oninput=e=>{activeModel().layout.chip[model]=Number(e.target.value);clearPhysicalReview();markDirty()};
  for(const input of ['chipWidth','chipHeight','chipThickness'])$(input).onchange=()=>render();
  $('addComponent').onclick=()=>componentDialog(-1,$('newComponentKind').value);
  document.querySelectorAll('[data-edit-component]').forEach(b=>b.onclick=()=>componentDialog(Number(b.dataset.editComponent)));
  $('checkLayout').onclick=async()=>{try{const r=await api('/api/design/check','POST',{model:activeModel()});$('layoutCheckResult').innerHTML=`<div class="callout ${r.layout.ready?'':'warn'}">${esc(r.layout.message)}</div>`}catch(e){toast(e.message,true)}};
  $('prepareGDS').onclick=()=>{setStudy('quantum_metal','gds_draft',{source:'project.layout'});render();toast('GDS study prepared. Save this revision, then explicitly run it.')};
  $('gdsRun').onclick=()=>runSavedStudy('quantum_metal');
 }
 if(id==='em'){wireEM();wireTransmonSelection()}
 if(id==='quantum'){
  wireIndependentTransmon();
  if($('viewExtractionRuns'))$('viewExtractionRuns').onclick=()=>goStep(5);
  $('addQuantumStudy').onclick=()=>{try{applyQuantum();toast('Study added to draft. Save revision before running.')}catch(err){toast(err.message,true)}};
  $('quantumRun').onclick=async()=>{try{if(dirty)throw Error('Save this revision first, then run its exact saved study');if(!currentStudy('scqubits'))throw Error('Apply and save an explicit scqubits study first');await runSavedStudy('scqubits')}catch(err){toast(err.message,true)}};
 }
 if(id==='results'&&$('exploreStudy')){
  $('exploreStudy').onchange=e=>{explorationStudyId=e.target.value;render()};
  $('exploreAxis').onchange=e=>{const study=activeModel().studies.find(s=>s.id===$('exploreStudy').value);const a=sweepableInputs(study).find(([key])=>key===e.target.value);if(a)$('exploreValues').value=[a[1]*.95,a[1],a[1]*1.05].map(v=>Number(v.toPrecision(8))).join(', ')};
  $('startExploration').onclick=runExploration;
 }
 // Fabrication is a read-only HOLD handoff until independently qualified.
}
function applyQuantum(){const model=$('qModel').value;
 const val=key=>Number($(key).value),prior=currentStudy('scqubits')?.inputs;
 let params=model==='Transmon'?{EJ:val('qEJ'),EC:val('qEC'),ng:val('qNg'),ncut:val('qNcut')}:model==='Fluxonium'?{EJ:val('qEJ'),EC:val('qEC'),EL:val('qEL'),flux:val('qFlux'),cutoff:val('qCutoff')}:{EJmax:val('qEJmax'),EC:val('qEC'),d:val('qD'),flux:val('qFlux'),ng:val('qNg'),ncut:val('qNcut')};
 if(prior?.model===model&&Number.isInteger(prior.parameters?.truncated_dim))params.truncated_dim=prior.parameters.truncated_dim;
 if(Object.values(params).some(v=>!Number.isFinite(v)))throw Error('Parameters must be finite numbers');
 for(const k of ['ncut','cutoff','truncated_dim'])if(k in params&&!Number.isInteger(params[k]))throw Error('Basis cutoff must be integer');
 const units={};for(const key of Object.keys(params))units[key]=['EJ','EC','EL','EJmax'].includes(key)?'GHz':key==='flux'?'Phi0':key==='ng'?'2e':'1';
 const inputs={model,parameters:params,parameter_units:units,source:'independent',levels:prior?.model===model?prior.levels:4};
 const convMode=$('qConvMode')?.value||'off';
 if(convMode!=='off'){
  const basis_increment=readNumber('qConvIncrement',{integer:true,min:1,max:6}),tolerance_GHz=readNumber('qConvTolerance',{min:Number.MIN_VALUE,max:0.5});
  inputs.convergence={enabled:true,basis_increment,tolerance_GHz};
  if(convMode==='curve')inputs.convergence.steps=readNumber('qConvSteps',{integer:true,min:2,max:4});
  if((params.cutoff??params.ncut)+basis_increment*(inputs.convergence.steps||1)>80)throw Error('Final native cutoff must not exceed 80; lower the base or increment');
 }else inputs.convergence={enabled:false};
 if((model==='Fluxonium'||model==='TunableTransmon')&&$('qFluxValues')?.value.trim()){
  const raw=$('qFluxValues').value.split(',').map(x=>x.trim());
  if(raw.length<2||raw.length>21||raw.some(x=>x===''||!Number.isFinite(Number(x))||Number(x)<0||Number(x)>1))throw Error('Flux sweep requires 2–21 finite values between 0 and 1 Phi0');
  inputs.sweep={subsystem:'primary',parameter:'flux',values:raw.map(Number),unit:'Phi0'};
 }
 if(inputs.sweep&&inputs.convergence?.steps>1)throw Error('Use one expansion for a flux sweep, or clear the sweep to run a basis curve');
 // Applying edited inputs never changes the scientific source to EM-derived.
 setStudy('scqubits','spectrum',inputs);
}
function setStudy(engine,kind,inputs){const m=activeModel();let index=m.studies.findIndex(s=>s.engine===engine&&(engine!=='scqubits'||s.kind!=='extracted_transmon_research'));
 const study={id:engine+'_primary',engine,kind,inputs};if(index>=0)m.studies[index]=study;else m.studies.push(study);markDirty()}
function markDirty(){dirty=true;$('saveButton').textContent='● Save changes';$('stageBadge').textContent='Unsaved draft';$('stageBadge').className='status warn'}
async function save(){if(!project)return false;if(!dirty){toast('No unsaved changes');return true}try{
 const saved=activeModel().intent?.transmon_capacitance_selection;
 if(transmonFamily(activeModel())&&saved){
  const checked=validatedTransmonSelection(activeModel(),transmonDraftFromSaved(saved));
  if(!sameTransmonSelection(saved,checked))throw Error('Saved transmon selection is stale or invalid; clear it in EM analysis before committing changed conductors');
 }
 const obj=await api(`/api/projects/${project.id}/commit`,'POST',{expected_revision:project.head,model:activeModel()});await loadProject(project.id);toast('Revision saved · '+obj.revision.slice(0,8));return true}catch(err){toast(err.message,true);return false}}
// The independent manual form is intentionally not wired to setStudy, save,
// runSavedStudy, EM, Results, or a conjectured A12 HTTP endpoint.
