/* SQE Studio single workspace. View-controller only: NO physical computations. */
'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STEPS=[['intent','Specifications','Define targets, units and design criteria.'],['schematic','Schematic','Specify topology, elements and electrical ports.'],['layout','Layout','Generate geometry through Quantum Metal.'],['em','EM analysis','Configure full-wave studies via SQDMetal / Gmsh / Palace.'],['quantum','Quantum models','Run explicit quantum and circuit models with native engines.'],['results','Results','Inspect traceable native outputs and compare revisions.'],['fabrication','Fabrication','Export Quantum Metal GDSII under a clear HOLD gate.']];
let csrf='',project=null,projects=[],engines=[],step=0,expert=false,inspector=false,runs=[],dirty=false;
let dialogReturnFocus=null, toastTimer=null, selectedCanvasItem=null;
let designTemplates=[],designCases=[],edaCapabilities=[],componentCatalog=[],emSelectedId='',explorationStudyId='';
const UI={};
async function api(path,method='GET',body){
 const response=await fetch(path,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':csrf}:{})},body:body?JSON.stringify(body):undefined});
 const typ=response.headers.get('content-type')||'';const obj=typ.includes('json')?await response.json():null;
 if(!response.ok){const error=Error((obj&&obj.error)||`HTTP ${response.status}`);error.status=response.status;throw error}return obj;
}
function toast(msg,error=false){const e=$('toast');clearTimeout(toastTimer);e.textContent=msg;e.className='toast'+(error?' error':'');toastTimer=setTimeout(()=>e.classList.add('hidden'),5200)}
function field(label,id,value,type='text',help=''){return `<label class="form-field"><span>${esc(label)}</span><input id="${id}" type="${type}" ${type==='number'?'step="any"':''} value="${esc(value)}">${help?`<small>${esc(help)}</small>`:''}</label>`}
function textarea(label,id,value,placeholder=''){return `<label class="form-field"><span>${esc(label)}</span><textarea id="${id}" placeholder="${esc(placeholder)}">${esc(value)}</textarea></label>`}
function pane(title,subtitle,content){return `<section class="pane"><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}${content}</section>`}
function empty(title,body){return `<div class="empty"><strong>${esc(title)}</strong><span>${esc(body)}</span></div>`}
function labelStatus(status){return status==='draft_saved'?'Draft saved':status==='not_started'?'Not started':status}
function activeModel(){return project?.model||null}
function renderStages(){
 const statuses=project?.stages||{};
 $('stages').innerHTML=STEPS.map(([id,name],i)=>`<button type="button" class="${i===step?'active':''}" data-step="${i}" ${i===step?'aria-current="step"':''} title="${esc(name)}"><span class="stage-num">${String(i+1).padStart(2,'0')}</span><span>${esc(name)}</span><i aria-hidden="true" class="step-state ${statuses[id]==='draft_saved'?'saved':''}"></i></button>`).join('');
 const glyphs=['◎','⌁','▦','≋','◈','▥','⬡'];
 $('railStages').innerHTML=STEPS.map(([,name],i)=>`<button type="button" class="rail-button ${i===step?'active':''}" data-step="${i}" aria-label="${esc(name)}" ${i===step?'aria-current="step"':''} title="${esc(name)} (Alt+${i+1})">${glyphs[i]}</button>`).join('');
 document.querySelectorAll('[data-step]').forEach(e=>e.onclick=()=>goStep(Number(e.dataset.step)));
}
function setupView(){
 $('auth').classList.remove('hidden');$('application').classList.add('hidden');
 api('/api/status').then(s=>{UI.setup=!!s.setup_required;$('authTitle').textContent=UI.setup?'Create administrator':'Your quantum design workspace';$('authCaption').textContent=UI.setup?'Private first-run account · Keep your setup token secret.':'Sign in to your local workspace.';$('setupTokenLabel').classList.toggle('hidden',!UI.setup);$('authSubmit').textContent=UI.setup?'Create local account →':'Sign in →'}).catch(err=>$('authError').textContent=err.message);
}
async function authenticate(){try{
 $('authError').textContent='';const data={email:$('email').value,password:$('password').value};
 if(UI.setup){await api('/api/setup','POST',{...data,setup_token:$('setupToken').value});UI.setup=false;}
 const auth=await api('/api/login','POST',data);csrf=auth.csrf;
 $('auth').classList.add('hidden');$('application').classList.remove('hidden');await reload();
 }catch(err){$('authError').textContent=err.message}}
async function reload(){const p=await api('/api/projects');projects=p.projects;engines=(await api('/api/engines')).engines;
 designTemplates=(await api('/api/design/templates')).templates;designCases=(await api('/api/design/use-cases')).cases;edaCapabilities=(await api('/api/design/capabilities')).edges;componentCatalog=(await api('/api/design/components')).components;
 if(project&&projects.some(x=>x.id===project.id))await loadProject(project.id);
 else if(projects.length)await loadProject(projects[0].id);
 else{project=null;step=0;render();openDialog('Create your first project',newProjectForm())}
}
async function loadProject(id){project=await api(`/api/projects/${id}`);runs=(await api(`/api/projects/${id}/runs`)).runs;dirty=false;selectedCanvasItem=null;emSelectedId='';render()}
function currentStudy(engine){return activeModel()?.studies.find(s=>s.engine===engine)||null}
function render(){renderStages();
 let [id,name,description]=STEPS[step];$('pageNumber').textContent=`${String(step+1).padStart(2,'0')} / 07 · SINGLE DESIGN FLOW`;
 $('pageTitle').textContent=name;$('pageDescription').textContent=description;
 $('currentProjectName').textContent=project?.name||'Create a project';$('crumbProject').textContent=project?.name||'Workspace';$('crumbStage').textContent=name;
 $('revisionLabel').textContent=project?'REV '+project.head.slice(0,8):'No revision';$('revisionLabel').title=project?'Revision: '+project.head+' | SHA-256: '+project.revision_digest:'No saved revision';$('saveButton').disabled=!project;$('saveButton').textContent=dirty?'● Save changes':'↧ Save revision';
 $('stageBadge').textContent=dirty?'Unsaved draft':project?labelStatus(project.stages[id]):'Create a project';$('stageBadge').className='status '+(dirty?'warn':project?.stages[id]==='draft_saved'?'saved':'');$('progressFill').style.width=((step+1)/STEPS.length*100)+'%';
 $('prevButton').disabled=step===0;$('nextButton').disabled=step===STEPS.length-1;
 $('expertButton').textContent=expert?'Guided mode':'Expert mode';$('expertButton').setAttribute('aria-pressed',String(expert));$('inspector').classList.toggle('hidden',!inspector);$('application').classList.toggle('inspector-open',inspector);$('inspectorButton').setAttribute('aria-expanded',String(inspector));$('inspectorBody').innerHTML=renderInspector();
 $('workspaceBody').innerHTML=project?(renderStep(id)+renderExpert()):pane('Start a project','Every design, engine job and result is revision bound.',`<button class="primary" id="newStart">+ New project</button>`);
 if(!project){$('newStart').onclick=()=>openDialog('New project',newProjectForm());return}
 wireStep(id);
}
function renderInspector(){if(!project)return '<p>Create a project to begin.</p>';
 const stages=Object.entries(project.stages).map(([s,v])=>`<div class="engine-status"><span>${esc(s)}</span><span>${esc(labelStatus(v))}</span></div>`).join('');
 return `<h3>Current project</h3><p><b>${esc(project.name)}</b><br>Revision ${esc(project.head.slice(0,12))}<br>Family: ${esc(project.model.family)}</p>
 <h3>Draft stages</h3>${stages}<h3>Scientific integrity</h3><p>Saving a design intent does not qualify science. Native jobs must provide their own results and convergence evidence.</p><div class="callout warn">No automatic foundry signoff. Native GDSII remains HOLD until external DRC/LVS and PDK verification.</div>`}
function renderExpert(){return expert && project?pane('Expert · declarative project model','Advanced schema view of this same project. Changes remain local until saved; server validation is authoritative.',`<div class="callout warn">Only supported declarative project fields. No code, shell commands, imports, or unreviewed engine mappings.</div><label class="form-field"><span>Project JSON (schema sqe.project.v1)</span><textarea id="expertJson" spellcheck="false" class="expert-editor">${esc(JSON.stringify(activeModel(),null,2))}</textarea></label><button class="secondary" id="applyExpert">Apply to local draft</button>`):''}
function renderStep(id){const m=activeModel();
 if(id==='intent'){
  const rows=(m.intent.targets||[]).map((t,i)=>`<tr><td>${esc(t.name)}</td><td>${esc(t.value)}</td><td>${esc(t.unit)}</td><td>${esc(t.tolerance??'—')}</td><td><button class="secondary mini" data-remove-target="${i}">Remove</button></td></tr>`).join('');
  return `<div class="grid-two">${pane('Design targets','State your performance goals before solver configuration.',`
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Parameter</th><th>Target</th><th>Unit</th><th>Tolerance</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="5">No targets defined yet.</td></tr>'}</tbody></table></div><div class="divider"></div>
    <div class="row">${field('Parameter','targetName','f01')}${field('Goal','targetValue',5.1,'number')}${field('Units','targetUnit','GHz')}${field('± Tolerance','targetTolerance',0.05,'number')}</div><button class="secondary" id="addTarget">+ Add target</button>`)}
    ${pane('Design policy','The same project revision is consumed by every native engine.',`<div class="metric-cards"><div class="metric"><strong>1</strong><span>Project</span></div><div class="metric"><strong>7</strong><span>Workflow steps</span></div><div class="metric"><strong>${runs.length}</strong><span>Native runs</span></div></div>
    ${textarea('Design notes','intentNotes',m.intent.notes||'','Describe interfaces, limits and known assumptions')}
    <div class="callout">Targets are design intent, not measured or calculated results. They never automatically set a verified Hamiltonian.</div>`)}</div>`;
 }
 if(id==='schematic'){
  const elems=m.schematic.elements;
  return `<div class="grid-two">${pane('Schematic editor','Connections are an editable graph of declarative circuit intent, not an LVS-verified netlist.',`${schematicCanvas(m.schematic)}
     <div class="table-wrap"><table class="data-table"><thead><tr><th>Component</th><th>Type</th><th>Node A</th><th>Node B</th><th>Value</th></tr></thead><tbody>${elems.map(e=>`<tr><td>${esc(e.id)}</td><td>${esc(e.type)}</td><td>${esc(e.a)}</td><td>${esc(e.b)}</td><td>${esc(e.value)} ${esc(e.unit)}</td></tr>`).join('')||'<tr><td colspan="5">No components added.</td></tr>'}</tbody></table></div><div class="divider"></div>
     <div class="row">${field('ID','elementId','C1')}${field('Node A','nodeA','q')}${field('Node B','nodeB','gnd')}</div><div class="row"><label class="form-field"><span>Kind</span><select id="elementType"><option>Capacitor</option><option>Inductor</option><option>JosephsonJunction</option><option>Resistor</option></select></label>${field('Value','elementValue','1','number')}${field('Unit','elementUnit','fF')}</div><button class="secondary" id="addElement">+ Add component</button>`)}
    ${pane('Netlist readiness','Review connectivity and explicitly record evidence before any netlist-to-geometry mapping.',`<div class="metric-cards"><div class="metric"><strong>${elems.length}</strong><span>Elements</span></div><div class="metric"><strong>${m.schematic.nodes.length}</strong><span>Declared nodes</span></div><div class="metric"><strong>${m.schematic.ports.length}</strong><span>Ports</span></div></div><div class="callout warn">A layout-to-netlist LVS map has not been established. Solver studies cannot assume this netlist matches QGeometry.</div>`)}</div>`;
 }
 if(id==='layout'){
  const chip=m.layout.chip; 
  return `<div class="grid-two">${pane('Quantum Metal layout planner','Position reviewed Quantum Metal primitives. This canvas shows placement intent, not rendered QGeometry.',`${layoutCanvas(m.layout)}
  <div class="row">${field('Chip width · mm','chipWidth',chip.width_mm,'number')}${field('Chip height · mm','chipHeight',chip.height_mm,'number')}${field('Substrate thickness · µm','chipThickness',chip.thickness_um,'number')}</div>
  <div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>QComponent</th><th>Placement / net</th><th>Properties</th><th></th></tr></thead><tbody>${m.layout.components.map((c,i)=>`<tr><td>${esc(c.name)}</td><td>${esc(c.kind)}</td><td>${isRoute(c.kind)?esc(c.net):esc(c.x_mm+' / '+c.y_mm+' mm')}</td><td><button class="secondary mini" data-edit-component="${i}">Edit</button></td><td><button class="secondary mini" data-remove-component="${i}">Remove</button></td></tr>`).join('')||'<tr><td colspan="5">No QComponents yet.</td></tr>'}</tbody></table></div><div class="divider"></div>
  <div class="row">${selection('newComponentKind','Reviewed primitive',componentCatalog.map(c=>c.kind),'TransmonPocket')}<button class="secondary" id="addComponent">+ Add QComponent / Route</button></div>
  <div class="row"><button class="secondary" type="button" id="checkLayout">Check layout recipe</button></div><div id="layoutCheckResult" aria-live="polite"></div>
  <div class="callout">Components are generated by installed Quantum Metal, not redrawn by SQE Studio. Only reviewed parametric primitives are enabled.</div>`)}
  ${pane('QGDSRenderer handoff','Native GDS can only be requested for a saved, revision-bound layout.',`${engineInfo('quantum_metal')}
  <div class="gate-list">${gateRow('Layout primitive',m.layout.components.length>0,'Defined','Missing')}${gateRow('Native package',engineInstalled('quantum_metal'),'Installed','Missing')}${gateRow('Chip/placement bounds',layoutInputsValid(),'Within chip','Check dimensions and coordinates')}${gateRow('Saved study',!!currentStudy('quantum_metal')&&!dirty,'Saved','Prepare and save')}</div><div class="button-stack"><button class="secondary" id="prepareGDS" ${m.layout.components.length?'':'disabled'}>Prepare GDS study</button><button class="primary" id="gdsRun" ${canRun('quantum_metal')?'':'disabled'}>Run saved GDS study →</button></div><div class="callout warn">Output remains HOLD. No approved layer mapping, junction cell, DRC/LVS, mask signoff or foundry release.</div>`)}</div>`;
 }
 if(id==='em')return emEditor();
 if(id==='quantum'){
  const s=currentStudy('scqubits');const val=s?.inputs?.parameters||{EJ:15,EC:0.25,ng:0,ncut:25};const model=s?.inputs?.model||'Transmon';
  return `<div class="grid-two">${pane('Quantum spectrum · scqubits','Use a real installed Hamiltonian solver on explicit model values.',`${engineInfo('scqubits')}
  <label class="form-field"><span>Device model</span><select id="qModel"><option ${model==='Transmon'?'selected':''}>Transmon</option><option ${model==='Fluxonium'?'selected':''}>Fluxonium</option><option ${model==='TunableTransmon'?'selected':''}>TunableTransmon</option></select></label>
  <div class="row">${field('EJ · GHz','qEJ',val.EJ??15,'number')}${field('EC · GHz','qEC',val.EC??0.25,'number')}${field('ng','qNg',val.ng??0,'number')}${field('ncut','qNcut',val.ncut??25,'number')}</div>
  <div class="row">${field('EL · GHz (Fluxonium)','qEL',val.EL??0.5,'number')}${field('Flux','qFlux',val.flux??0.5,'number')}${field('Cutoff (Fluxonium)','qCutoff',val.cutoff??30,'number')}</div>
  <div class="row">${field('EJmax (Tunable)','qEJmax',val.EJmax??20,'number')}${field('Asymmetry d (Tunable)','qD',val.d??0.15,'number')}</div>
  ${model==='Fluxonium'||model==='TunableTransmon'?field('Native flux sweep · Phi0 (comma-separated, optional)','qFluxValues',s?.inputs?.sweep?.parameter==='flux'?s.inputs.sweep.values.join(', '):'','text','2–21 finite points between 0 and 1; applies to the native scqubits study'):''}
  <div class="row"><button class="secondary" id="addQuantumStudy">Apply study to draft</button><button class="primary" id="quantumRun" ${canRun('scqubits')?'':'disabled'}>Run saved study →</button></div><div class="callout">Engine inputs are independent explicit Hamiltonian parameters. No EM-to-Hamiltonian extraction is assumed until a verified mapping is available.</div>`)}
  ${pane('JosephsonCircuits.jl','Native nonlinear/RF circuit analysis must use its own verified port/netlist mapping.',`${engineInfo('josephson_circuits')}<div class="callout warn">No SQE numerical replacement. Agent A05 must complete the reviewed Julia adapter before execution is enabled.</div>`)}</div>`;
 }
 if(id==='results')return `${designExplorationControls()}${pane('Native solver output','Revision-bound physical outputs, not an experiment notebook.',runsTable())}${compareControls()}<div id="resultView"></div><div id="comparisonView" aria-live="polite"></div>`;
 if(id==='fabrication')return `<div class="grid-two">${pane('Fabrication handoff · HOLD','Only Quantum Metal QGDSRenderer may author native GDSII.',`${engineInfo('quantum_metal')}<div class="gate-list">${gateRow('Native QGDSRenderer',engineInstalled('quantum_metal'),'Installed','Unavailable')}${gateRow('Foundry PDK mapping',false,'','Unverified')}${gateRow('Junction cells / polarity',false,'','Unverified')}${gateRow('Independent DRC / LVS',false,'','Not supplied')}${gateRow('Foundry signoff',false,'','Not authorized')}</div><button class="secondary" id="fabricationRun" disabled aria-disabled="true">Fabrication release unavailable · HOLD</button><div class="callout warn">HOLD — native GDS can be generated for CAD review from the Layout step, but is not a foundry-approved fabrication release. PDK, DRC/LVS and independent signoff are required.</div>`)}
  ${pane('Available native artifacts','A GDS file is an output of a successful revision-bound engine job.',runsTable())}</div>`;
 return '';
}
function engineInstalled(id){return !!engines.find(x=>x.id===id)?.available}
function engineValidated(id){const e=engines.find(x=>x.id===id);return !!(e?.available && ((e.mode==='native'&&(id==='quantum_metal'||id==='scqubits'))||(e.mode==='native_conditional'&&id==='sqdmetal_palace')))}
function layoutInputsValid(){
 const l=activeModel()?.layout;if(!l)return false;
 const {width_mm:w,height_mm:h,thickness_um:t}=l.chip||{};
 return [w,h,t].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=.1&&n<=1000)&&
   l.components.length>0&&l.components.every(c=>isRoute(c.kind)||Number.isFinite(c.x_mm)&&Number.isFinite(c.y_mm)&&Math.abs(c.x_mm)<=w/2&&Math.abs(c.y_mm)<=h/2);
}
function canRun(id){return !!(project&&!dirty&&currentStudy(id)&&engineValidated(id)&&(id!=='quantum_metal'||layoutInputsValid()))}
function gateRow(name,ok,yes,no){return `<div class="gate-row"><span>${esc(name)}</span><span class="${ok?'passed':''}">${esc(ok?yes:no)}</span></div>`}
function engineInfo(id){const e=engines.find(x=>x.id===id);const ready=engineValidated(id);return `<div class="engine-status"><span>${esc(e?.name||id)}</span><span class="${ready?'available':'unavailable'}">${ready?'Dependencies detected · review needed':'Blocked / missing'} · ${esc(e?.mode||'not detected')}</span></div>`}
function runsTable(){if(!runs.length)return empty('No native job history','Apply a supported study, save the revision, then explicitly request native execution. No results have been generated.');
 return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Engine / study</th><th>Revision</th><th>Job state</th><th>Evidence</th></tr></thead><tbody>${runs.map(r=>{const done=!['queued','running'].includes(r.state);return `<tr><td>${esc(r.engine)}<br><small>${esc(r.study_id)}${r.is_sweep?' · parameter sweep':''}</small></td><td title="${esc(r.revision_id)}">${esc(r.revision_id.slice(0,8))}</td><td><span class="${r.state==='completed'?'available':'danger'}">${esc(r.state)}</span></td><td><div class="button-stack"><button class="secondary mini" data-get-result="${esc(r.id)}">${r.state==='completed'?'Inspect':'View status'}</button><button class="secondary mini" data-download="${esc(r.id)}" ${done?'':'disabled'} aria-label="Download archive for ${esc(r.engine)} ${esc(r.state)} job">ZIP ↓</button></div></td></tr>`}).join('')}</tbody></table></div>`}
function compareControls(){
 const done=runs.filter(r=>r.state==='completed'&&!r.is_sweep&&!r.unsafe_location);
 if(done.length<2)return pane('Expert cross-run comparison','Requires two completed, hash-verified native runs. Failed runs have diagnostics but no scientific result.','<p class="helper">Run at least two native studies to compare evidence and saved engineering inputs.</p>');
 const opts=done.map(r=>`<option value="${esc(r.id)}">${esc(r.engine)} / ${esc(r.study_id)} / ${esc(r.revision_id.slice(0,8))}</option>`).join('');
 return pane('Expert cross-run comparison','Read-only evidence side by side; numerical deltas only for semantically compatible native scqubits spectra.',`<div class="form-grid"><label class="form-field"><span>Left verified native run</span><select id="compareLeft">${opts}</select></label><label class="form-field"><span>Right verified native run</span><select id="compareRight">${opts}</select></label></div><button type="button" class="secondary" id="compareRuns">Compare runs</button><p class="helper">Different physics engines do not imply equivalent ports, materials, modes or extracted quantities.</p>`);
}
function comparisonView(data){
 const left=data.left,right=data.right,changes=data.design_input_changes,n=data.numerical_comparison;
 const val=v=>v===null?'—':typeof v==='object'?'[structured]':String(v);
 let html=`<div class="callout warn">${esc(data.status)} · ${esc(data.same_revision?'Same revision':'Different revisions')} · ${esc(data.same_output_type?'Same artifact type':'Different artifact types; no numeric comparison inferred')}</div>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Evidence</th><th>Left native run</th><th>Right native run</th></tr></thead><tbody>${[['Engine',left.engine,right.engine],['Study',left.study_id,right.study_id],['Revision',left.revision_id,right.revision_id],['Project SHA-256',left.project_sha256,right.project_sha256],['Native version',left.native_version,right.native_version],['Output type',left.artifact_type,right.artifact_type],['Scientific status',left.scientific_status,right.scientific_status],['Fabrication',left.fabrication_status,right.fabrication_status]].map(([k,a,b])=>`<tr><td>${esc(k)}</td><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</tbody></table></div>`;
 html+=`<h3>Changed saved engineering inputs (${changes.total})</h3><p class="helper">These are revisions of design intent, not measured physics.</p>`;
 html+=changes.shown.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Left</th><th>Right</th></tr></thead><tbody>${changes.shown.map(r=>`<tr><td>${esc(r.field)}</td><td>${esc(val(r.left))}</td><td>${esc(val(r.right))}</td></tr>`).join('')}</tbody></table></div>`:'<p class="helper">No differences in the selected engineering input fields.</p>';
 if(changes.truncated)html+='<div class="callout warn">Only the first 64 changes are displayed.</div>';
 html+=`<h3>Native numerical comparison</h3><p class="helper">${esc(n.status)} · ${esc(n.reason||n.method)}</p>`;
 if(n.rows?.length){html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Transition</th><th>Left (GHz)</th><th>Right (GHz)</th><th>Difference (GHz)</th></tr></thead><tbody>${n.rows.map(r=>`<tr><td>${esc(r.transition)}</td><td>${esc(r.left_GHz)}</td><td>${esc(r.right_GHz)}</td><td>${esc(r.delta_GHz)}</td></tr>`).join('')}</tbody></table></div>`;if(!n.convergence_verified)html+='<div class="callout warn">One or both native spectra lack convergence evidence; differences are for expert review only.</div>';}
 html+=`<p class="helper">${data.caveats.map(esc).join(' · ')}</p>`;
 return pane('Read-only comparison · no automatic scientific equivalence','Native bytes checked against recorded SHA-256 before comparison.',html);
}
async function compareSavedRuns(){
 try{
  const left=$('compareLeft').value,right=$('compareRight').value;
  if(left===right)throw Error('Choose two different runs');
  const data=await api(`/api/projects/${project.id}/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`);
  if($('comparisonView'))$('comparisonView').innerHTML=comparisonView(data);
 }catch(err){toast(err.message,true)}
}
/* Graphs visualize the saved declarative model only; NOT a QGeometry or LVS result. */
function gridLines(){return Array.from({length:17},(_,i)=>`<path class="canvas-grid" d="M ${i*32} 0 V 300"/>`).join('')+Array.from({length:10},(_,i)=>`<path class="canvas-grid" d="M 0 ${i*32} H 520"/>`).join('')}
function svgFrame(label,body,caption){return `<div class="canvas-shell"><div class="canvas-toolbar"><strong>${esc(label)}</strong><span>DECLARATIVE PREVIEW · NOT VERIFIED</span></div><svg class="design-canvas" viewBox="0 0 520 300" role="group" aria-label="${esc(label)}. ${esc(caption)}" xmlns="http://www.w3.org/2000/svg">${gridLines()}${body}</svg><p class="canvas-caption">${esc(caption)}</p></div><div id="canvasDetail" class="canvas-detail" aria-live="polite">Select a visual item for its exact model values. Keyboard: Tab then Enter or Space.</div>`}
function schematicCanvas(schematic){
 const nodes=[...new Set([...(schematic.nodes||[]),...schematic.elements.flatMap(e=>[e.a,e.b])])].slice(0,9);
 if(!schematic.elements.length)return svgFrame('Schematic connectivity',`<text class="canvas-empty" x="260" y="150" text-anchor="middle">No circuit elements defined</text>`,'Add a circuit element to preview logical connectivity. No electrical equivalence is inferred.');
 const coords=new Map(nodes.map((n,i)=>[n,{x:65+(i%3)*194,y:61+Math.floor(i/3)*93}]));
 const elems=schematic.elements.slice(0,12);
 const wires=elems.map((e,i)=>{
  const a=coords.get(e.a),b=coords.get(e.b);if(!a||!b)return '';
  const x=(a.x+b.x)/2,y=(a.y+b.y)/2+(i%3-1)*12;
  return `<path class="canvas-wire" d="M ${a.x} ${a.y} L ${b.x} ${b.y}"/><g class="canvas-action" role="button" tabindex="0" data-canvas="element" data-index="${i}" aria-label="Inspect ${esc(e.id)}, ${esc(e.type)}"><rect class="canvas-part" x="${x-28}" y="${y-14}" width="56" height="28" rx="6"/><text class="canvas-part-label" text-anchor="middle" x="${x}" y="${y+4}">${esc(e.id.slice(0,7))}</text></g>`;
 }).join('');
 const circles=nodes.map(n=>{const p=coords.get(n);return `<circle class="canvas-node" cx="${p.x}" cy="${p.y}" r="7"/><text class="canvas-node-label" x="${p.x+12}" y="${p.y-10}">${esc(n.slice(0,17))}</text>`}).join('');
 const extra=schematic.elements.length>12||[...new Set([...(schematic.nodes||[]),...schematic.elements.flatMap(e=>[e.a,e.b])])].length>9;
 return svgFrame('Schematic connectivity',wires+circles+(extra?`<text class="canvas-key" x="16" y="286">Subset shown · see table for full model</text>`:''),'Schematic node/element intent only. Lines are logical connections; no routing, netlist validation, LVS or electrical solving.');
}
function layoutCanvas(layout){
 const chip=layout.chip||{},w=Number(chip.width_mm),h=Number(chip.height_mm);
 const valid=Number.isFinite(w)&&Number.isFinite(h)&&w>0&&h>0;
 if(!valid)return svgFrame('Quantum Metal placement',`<text class="canvas-empty" x="260" y="150" text-anchor="middle">Enter positive chip dimensions</text>`,'Cannot preview an invalid chip. No native Quantum Metal geometry exists here.');
 const scale=Math.min(348/w,218/h),cw=w*scale,ch=h*scale,x0=260-cw/2,y0=152-ch/2;
 const chipShape=`<rect class="canvas-chip" x="${x0}" y="${y0}" width="${cw}" height="${ch}" rx="3"/><text class="canvas-title" x="${x0}" y="${Math.max(14,y0-12)}">${esc(w)} × ${esc(h)} mm · chip outline</text>`;
 const componentByName=new Map(layout.components.filter(c=>!isRoute(c.kind)).map(c=>[c.name,c]));
 const routes=layout.components.filter(c=>isRoute(c.kind)).slice(0,32).map(c=>{
  const a=componentByName.get(c.start?.component),b=componentByName.get(c.end?.component);
  if(!a||!b)return '';
  const x1=x0+cw/2+a.x_mm*scale,y1=y0+ch/2-a.y_mm*scale;
  const x2=x0+cw/2+b.x_mm*scale,y2=y0+ch/2-b.y_mm*scale;
  return `<g><path d="M ${x1} ${y1} L ${x2} ${y2}" class="canvas-route-intent"/><text x="${(x1+x2)/2}" y="${(y1+y2)/2-8}" class="canvas-key" text-anchor="middle">${esc(c.name)}</text></g>`;
 }).join('');
 const markers=layout.components.map((c,i)=>({c,i})).filter(x=>!isRoute(x.c.kind)).slice(0,32).map(({c,i})=>{
  const x=x0+cw/2+Number(c.x_mm)*scale,y=y0+ch/2-Number(c.y_mm)*scale;
  if(!Number.isFinite(x)||!Number.isFinite(y))return '';
  const px=Math.max(16,Math.min(502,x)),py=Math.max(20,Math.min(282,y));
  return `<g class="canvas-action" role="button" tabindex="0" data-canvas="layout" data-index="${i}" aria-label="Inspect ${esc(c.name)} placement"><circle class="canvas-part" cx="${px}" cy="${py}" r="10"/><path class="canvas-wire" d="M ${px-4} ${py} h 8 M ${px} ${py-4} v 8"/><text class="canvas-part-label" x="${px+14}" y="${py-12}">${esc(c.name.slice(0,12))}</text></g>`;
 }).join('');
 const extra=layout.components.length>32?`<text class="canvas-key" x="14" y="286">First 32 placements shown</text>`:'';
 return svgFrame('Quantum Metal placement intent',chipShape+routes+markers+extra,'Symbols and dashed lines denote connectivity/placement intent only — not native QGeometry, routed bends, dimensions, DRC, or GDS.');
}
function wireCanvas(){document.querySelectorAll('[data-canvas]').forEach(el=>{
  const activate=()=>{const index=Number(el.dataset.index);const data=el.dataset.canvas==='element'?activeModel().schematic.elements[index]:activeModel().layout.components[index];if(!data)return;
   document.querySelectorAll('[data-canvas] .canvas-part').forEach(p=>p.classList.remove('selected'));
   el.querySelector('.canvas-part')?.classList.add('selected');$('canvasDetail').textContent=`${el.dataset.canvas==='element'?'Electrical intent':'Placement intent'} · ${Object.entries(data).map(([k,v])=>k+': '+String(v)).join('  |  ')} · NOT VERIFIED`;};
  el.addEventListener('click',activate);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}});
 })}
function palaceModeTable(data){
 if(!data||data.source!=='palace.native_eig.csv'||data.units!=='GHz'||!Array.isArray(data.modes))return '';
 return `<h3>Palace native eigenfrequency table</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Native mode index</th><th>Frequency</th><th>Mode identity</th></tr></thead><tbody>${data.modes.map(m=>`<tr><td>${esc(m.mode_index)}</td><td>${esc(m.frequency_GHz)} GHz</td><td>Not verified across runs</td></tr>`).join('')}</tbody></table></div><div class="callout warn">No EPR/Hamiltonian extraction, mode matching or convergence is inferred. Eigenmodes are shown in the solver's native order.</div>`;
}
function goalComparison(data){
 const targets=activeModel().intent.targets||[];const results=[];
 if(data?.spectrum?.source==='scqubits.eigenvals'&&data.spectrum.units==='GHz'&&data.spectrum.levels?.length>=2){
  const t=targets.find(x=>x.name==='f01'&&x.unit==='GHz');if(t){const observed=data.spectrum.levels[1]-data.spectrum.levels[0];if(Number.isFinite(observed))results.push(['f01 (scqubits)',t,observed])}
 }
 if(data?.eigenmodes?.source==='palace.native_eig.csv')for(const mode of data.eigenmodes.modes){
  const t=targets.find(x=>x.name==='em_mode_'+mode.mode_index&&x.unit==='GHz');if(t)results.push(['EM mode '+mode.mode_index+' (identity unverified)',t,mode.frequency_GHz]);
 }
 if(!results.length)return '';
 return `<h3>Design targets versus native results</h3><p class="helper">Deltas are arithmetic differences, not mode identification or optimization proof. Tolerances are user-defined goals.</p>
 <div class="table-wrap"><table class="data-table"><thead><tr><th>Observable</th><th>Target · GHz</th><th>Native · GHz</th><th>Error · GHz</th><th>Within goal</th></tr></thead><tbody>${results.map(([label,t,obs])=>`<tr><td>${esc(label)}</td><td>${esc(t.value)}</td><td>${esc(obs)}</td><td>${esc(obs-t.value)}</td><td>${typeof t.tolerance==='number'&&Number.isFinite(t.tolerance)?esc(Math.abs(obs-t.value)<=t.tolerance?'Yes (numeric only)':'No'):'Not specified'}</td></tr>`).join('')}</tbody></table></div>`;
}
function sweepView(data){
 if(data.schema!=='sqe.sweep-view.v1')throw Error('Unknown native sweep response');
 let html=`<div class="callout warn">${esc(data.status)} · No mode matching, scientific qualification, or automatic optimization. Review each point's physical meaning.</div>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Point</th><th>Changed native input(s)</th><th>Engine</th><th>Native output</th></tr></thead><tbody>${data.points.map(p=>{
  const v=p.eigenmodes?.modes?.map(m=>'Mode '+m.mode_index+': '+m.frequency_GHz+' GHz').join('; ')||(p.spectrum?.source==='scqubits.eigenvals'&&p.spectrum?.levels?.length>=2?'f01: '+(p.spectrum.levels[1]-p.spectrum.levels[0])+' '+p.spectrum.units:'Artifact available in ZIP');
  return `<tr><td>${esc(p.index)}</td><td>${esc((p.coordinates||[]).map(x=>x.join(' = ')).join('; '))}</td><td>${esc(p.engine_version)}</td><td>${esc(v)}</td></tr>`}).join('')}</tbody></table></div>`;
 return pane('Parametric exploration · native outputs','Data are never interpolated or treated as equivalent between different solver settings.',html);
}
function nativeSpectrum(data){
 const values=data.levels;
 if(data.source!=='scqubits.eigenvals'||!Array.isArray(values)||values.length<2||values.length>12||values.some(v=>typeof v!=='number'||!Number.isFinite(v)))return '<div class="callout warn">Spectrum artifact is missing or malformed. No chart can be rendered.</div>';
 const lo=Math.min(...values),hi=Math.max(...values),range=hi-lo||1;
 const pts=values.map((v,i)=>{const x=50+i*(420/Math.max(values.length-1,1)),y=168-(v-lo)/range*120;return `<path d="M ${x} 170 V ${y}" stroke="#73dacc" stroke-width="2"/><circle cx="${x}" cy="${y}" r="5" fill="#78ebd6"/><text x="${x}" y="189" font-size="11" text-anchor="middle" fill="#dae7f5">${i}</text><title>Level ${i}: ${esc(v)}</title>`}).join('');
 return `<h3>scqubits native eigenvalues · ${esc(data.units)}</h3><svg class="spectrum-chart" viewBox="0 0 520 218" role="img" aria-label="Native spectrum from scqubits with ${values.length} eigenvalue levels"><path d="M 32 28 V 170 H 500" stroke="#a9c5d8" fill="none"/>${pts}<text x="258" y="209" font-size="11" fill="#c5d9e9" text-anchor="middle">Energy level index · native returned eigenvalues only</text><text x="39" y="24" font-size="11" fill="#c5d9e9">${esc(hi.toPrecision(4))}</text><text x="39" y="164" font-size="11" fill="#c5d9e9">${esc(lo.toPrecision(4))}</text></svg><p class="chart-caption">Source: ${esc(data.source)}. Values displayed without extrapolation or convergence claims.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Level</th><th>Native eigenvalue</th></tr></thead><tbody>${values.map((v,i)=>`<tr><td>${i}</td><td>${esc(v)} ${esc(data.units)}</td></tr>`).join('')}</tbody></table></div>`;
}
/* Generic property inspectors for the SAME project. No simulator or preview geometry here. */
const numeric=(id,description,number)=>field(description,id,number===undefined?'':number,'number');
const selection=(id,label,items,value)=>`<label class="form-field"><span>${esc(label)}</span><select id="${id}">${items.map(item=>{const [v,t]=Array.isArray(item)?item:[item,item];return `<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`}).join('')}</select></label>`;
const optionalNumber=(id,label,value)=>numeric(id,label,value);
const readNumber=(id,{optional=false,integer=false,min=-Infinity,max=Infinity}={})=>{
 const raw=$(id)?.value.trim();if(raw===''&&optional)return undefined;
 if(raw==='')throw Error(`${id}: enter a number`);
 const v=Number(raw);if(!Number.isFinite(v)||v<min||v>max||(integer&&!Number.isInteger(v)))throw Error(`${id}: invalid numeric value`);return v;
};
const readText=(id,required=true)=>{const text=$(id)?.value.trim()||'';if(required&&!text)throw Error(`${id}: required`);return text};
const componentInfo=kind=>componentCatalog.find(c=>c.kind===kind);
const isRoute=kind=>!!componentInfo(kind)?.route;
function componentDialog(index,kind){
 const c=index>=0?activeModel().layout.components[index]:{kind,name:'',x_mm:0,y_mm:0};kind=c.kind||kind;
 const info=componentInfo(kind);if(!info)return toast('Unknown reviewed component type',true);
 const base=`<p class="helper">${esc(kind)} · Quantum Metal will generate the actual geometry from this validated, declarative recipe.</p>
 <div class="row">${field('Component ID','editPartName',c.name||'')}${numeric('editPartLayer','QGeometry layer',c.layer??1)}</div>`;
 let form;
 if(isRoute(kind)){
 const endpoint=(label,prefix,value)=>`<div class="row">${selection(prefix+'Component',label+' component',activeModel().layout.components.filter(p=>!isRoute(p.kind)).map(p=>p.name),value?.component)}${field(label+' pin',prefix+'Pin',value?.pin||'')}</div>`;
 form=`${base}${field('Net identity','editPartNet',c.net||'')}${endpoint('Start','editPartStart',c.start)}${endpoint('End','editPartEnd',c.end)}
 <div class="row">${optionalNumber('editPartTraceWidth','Trace width · µm',c.trace_width_um)}${optionalNumber('editPartTraceGap','Trace gap · µm',c.trace_gap_um)}${optionalNumber('editPartFillet','Fillet · µm',c.fillet_um)}</div>
 ${kind==='RouteMeander'?`<div class="row">${optionalNumber('editPartLength','Total length · mm',c.total_length_mm)}${optionalNumber('editPartSpacing','Meander spacing · µm',c.meander?.spacing_um)}</div>`:''}
 ${kind==='RouteAnchors'||kind==='RoutePathfinder'?textarea('Anchors · one x_mm,y_mm per line','editPartAnchors',(c.anchors||[]).map(a=>a.x_mm+','+a.y_mm).join('\n')):''}
 ${kind==='RoutePathfinder'?optionalNumber('editPartStep','Route step · µm',c.step_size_um):''}`;
 } else {
  form=`${base}<div class="row">${numeric('editPartX','X · mm',c.x_mm)}${numeric('editPartY','Y · mm',c.y_mm)}${numeric('editPartAngle','Rotation · degrees',c.orientation_deg??0)}</div>
  ${(info.options||[]).length?`<details class="config-details" open><summary>Parametric QComponent dimensions · µm</summary><div class="form-grid">${info.options.map(o=>optionalNumber('partOpt_'+o,o.replaceAll('_',' '),c.options?.[o+'_um'])).join('')}</div></details>`:''}
  ${info.requires_subtract_layer?numeric('editPartSubtract','Subtraction layer',c.subtract_layer??2):''}`;
 }
 openDialog(index>=0?'Edit QComponent':'Add QComponent',`${form}<p class="helper">Review the pin identities and physical distances in the installed Quantum Metal geometry before any EM analysis. These controls do not imply GDS/DRC approval.</p><button class="primary full" id="confirmPart">${index>=0?'Update component':'Add component'}</button>`);
 $('confirmPart').onclick=()=>{try{
  const name=readText('editPartName');if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(name))throw Error('Use an ASCII QComponent ID (1–40 characters)');
  if(activeModel().layout.components.some((x,i)=>x.name===name&&i!==index))throw Error('Duplicate QComponent ID');
  const out={kind,name};const layer=readNumber('editPartLayer',{integer:true,min:1,max:255});if(layer!==1||c.layer!==undefined)out.layer=layer;
  if(isRoute(kind)){
   out.net=readText('editPartNet');out.start={component:readText('editPartStartComponent'),pin:readText('editPartStartPin')};out.end={component:readText('editPartEndComponent'),pin:readText('editPartEndPin')};
   for(const [id,key] of [['editPartTraceWidth','trace_width_um'],['editPartTraceGap','trace_gap_um'],['editPartFillet','fillet_um']]){const v=readNumber(id,{optional:true,min:0});if(v!==undefined)out[key]=v}
   if(kind==='RouteMeander'){
    const length=readNumber('editPartLength',{optional:true,min:0.01});if(length!==undefined)out.total_length_mm=length;
    const spacing=readNumber('editPartSpacing',{optional:true,min:1});if(spacing!==undefined)out.meander={spacing_um:spacing};
   }
   if(kind==='RouteAnchors'||kind==='RoutePathfinder'){
    const raw=readText('editPartAnchors',false);if(raw){out.anchors=raw.split(/\n/).map(line=>{const parts=line.split(',');if(parts.length!==2||parts.some(s=>!s.trim()||!Number.isFinite(Number(s))))throw Error('Anchors require one numeric x,y pair per line');return {x_mm:Number(parts[0]),y_mm:Number(parts[1])}})}
   }
   if(kind==='RoutePathfinder'){
    out.constraints={avoid_collision:true};const size=readNumber('editPartStep',{optional:true,min:1});if(size!==undefined)out.step_size_um=size;
   }
  }else{
   out.x_mm=readNumber('editPartX',{min:-100,max:100});out.y_mm=readNumber('editPartY',{min:-100,max:100});
   const orientation=readNumber('editPartAngle',{min:-360,max:360});if(orientation)out.orientation_deg=orientation;
   const options={};for(const o of info.options){const value=readNumber('partOpt_'+o,{optional:true,min:0.01,max:100000});if(value!==undefined)options[o+'_um']=value};if(Object.keys(options).length)out.options=options;
   if(info.requires_subtract_layer)out.subtract_layer=readNumber('editPartSubtract',{integer:true,min:1,max:255});
   // Retain reviewed advanced pad/junction configuration until explicitly edited in expert schema.
   for(const key of ['connection_pads','junction_cell','n_turns'])if(c[key]!==undefined)out[key]=c[key];
  }
  if(index>=0)activeModel().layout.components[index]=out;else activeModel().layout.components.push(out);
  clearPhysicalReview();markDirty();closeDialog();render();
 }catch(e){toast(e.message,true)}};
}
function clearPhysicalReview(){if(activeModel().process?.source==='reviewed'){
 activeModel().process.source='unverified';delete activeModel().process.rules?.gui_review;
}}
function blankEMStudy(){return {id:'EM1',engine:'sqdmetal_palace',kind:'eigenmode',inputs:{em:{
 ground:{kind:'qdesign_ground_plane',layer:1,verified:false},
 boundaries:{x_neg_um:300,x_pos_um:300,y_neg_um:300,y_pos_um:300,z_neg_um:0,z_pos_um:500,farfield:'pec'},
 ports:[],mesh:{min_um:12,max_um:120,refinement_levels:[0,1],relative_tolerance:0.02},
 execution:'deck_only',solver:{order:1,tolerance:1e-7,max_iterations:100,num_cpus:2,start_hz:5e9,modes:1}
 }}}}
function selectedEMStudy(){return activeModel().studies.find(s=>s.engine==='sqdmetal_palace'&&s.id===emSelectedId&&s.inputs?.em?.ground)||activeModel().studies.find(s=>s.engine==='sqdmetal_palace'&&s.inputs?.em?.ground)||null}
function emEditor(){const m=activeModel(),s=selectedEMStudy(),e=s?.inputs?.em,stack=m.process.stack||[];
 const [sub,metal,air]=stack.length===3?stack:[{material:'silicon',thickness_um:m.layout.chip.thickness_um,relative_permittivity:11.7,loss_tangent:0},{material:'aluminium',layer:1,thickness_nm:100,em_model:'PEC'},{material:'vacuum',height_um:500,relative_permittivity:1,loss_tangent:0}];
 const review=m.process.rules?.gui_review;
 const process=pane('Material and superconducting model','Model assumptions remain unverified until an expert explicitly accepts and documents them.',`
  <div class="row">${selection('matSubstrate','Substrate',[['silicon','Silicon'],['sapphire','Sapphire']],sub.material)}${numeric('matThickness','Substrate · µm',sub.thickness_um)}${numeric('matEps','Relative permittivity',sub.relative_permittivity)}${numeric('matLoss','Loss tangent',sub.loss_tangent)}</div>
  <div class="row">${numeric('matMetalLayer','Metal layer',metal.layer)}${numeric('matMetalThickness','Al thickness · nm',metal.thickness_nm)}${numeric('matAir','Vacuum height · µm',air.height_um)}</div>
  <p class="helper">Native A03 currently requires aluminium PEC. Kinetic inductance needs separate reviewed Gmsh surfaces and a Palace sheet-impedance model; changing thickness here alone does NOT simulate it.</p>
  <button type="button" class="secondary" id="applyMaterials">Apply material inputs</button>
  <div class="callout ${m.process.source==='reviewed'?'':'warn'}">Material assumptions: ${esc(m.process.source)}${review?.reviewer?' · '+esc(review.reviewer):''}. Not independently validated.</div>
  <div class="row">${field('Reviewer ID','matReviewer',review?.reviewer||'')}${field('Source URL','matSource',review?.source_url||'')}</div>
  ${textarea('Review rationale / expected validity','matRationale',review?.rationale||'')}
  <label class="review-check"><input type="checkbox" id="matConfirm"><span>I reviewed the exact material assumptions above; this is not foundry or experimental approval.</span></label>
  <button type="button" class="secondary" id="reviewMaterials">Record explicit physical assumption review</button>`);
 const all=m.studies.filter(x=>x.engine==='sqdmetal_palace'&&x.inputs?.em?.ground);
 const study=pane('Native EM study configuration','Define mesh, boundaries and explicitly mapped physical ports for any supported Quantum Metal design.',`
 <div class="row">${selection('emStudy','EM study',all.map(x=>[x.id,x.id+' · '+x.kind]),s?.id)}<button class="secondary" type="button" id="newEMStudy">+ New study</button><button class="secondary" type="button" id="cloneEMStudy" ${s?'':'disabled'}>Duplicate</button></div>
 ${!s?'<div class="callout warn">Add a study. Any legacy placeholder EM request remains unchanged until explicitly removed using the Expert JSON editor. A native solver is never run on inferred port/material assumptions.</div>':`
 <div class="row">${field('Study ID','emID',s.id)}${selection('emKind','Analysis', ['eigenmode','capacitance','sparameters'],s.kind)}${selection('emExecution','Execution',[['deck_only','Native mesh + deck'],['solve','Native Palace solve']],e?.execution)}</div>
 <div class="row">${numeric('emGround','Ground plane layer',e?.ground.layer)}${selection('emGroundCheck','Ground plane inspected',[['false','Not verified'],['true','I verified QDesign ground plane']],String(e?.ground.verified===true))}${selection('emFarfield','Farfield',[['pec','PEC'],['ground','Ground']],e?.boundaries.farfield)}</div>
 <details class="config-details" open><summary>Boundaries and mesh</summary>
 <div class="form-grid">${Object.keys(e.boundaries).filter(x=>x!=='farfield').map(k=>numeric('em_'+k,k.replaceAll('_',' ')+' · µm',e.boundaries[k])).join('')}</div>
 <div class="row">${numeric('emMeshMin','Min element · µm',e.mesh.min_um)}${numeric('emMeshMax','Max element · µm',e.mesh.max_um)}${numeric('emMeshTol','Convergence tolerance',e.mesh.relative_tolerance)}</div>
 ${selection('emMeshLevels','Refinement levels',[['0,1','0 → 1'],['0,1,2','0 → 1 → 2']],e.mesh.refinement_levels.join(','))}</details>
 <details class="config-details" open><summary>Solver options</summary><div class="form-grid">${[['order','Polynomial order'],['tolerance','Solver tolerance'],['max_iterations','Max iterations'],['num_cpus','CPU cores']].map(([k,l])=>numeric('emSolver_'+k,l,e.solver[k])).join('')}</div>
 <div class="row">${numeric('emStartHz','Eigenmode start · Hz',e.solver.start_hz??5e9)}${numeric('emModes','Eigenmode count',e.solver.modes??1)}</div>
 <div class="row">${numeric('emFreqMin','Driven start · Hz',e.solver.frequencies_hz?.[0]??4e9)}${numeric('emFreqMax','Driven stop · Hz',e.solver.frequencies_hz?.at(-1)??7e9)}${numeric('emFreqPoints','Driven points',e.solver.frequencies_hz?.length??11)}${numeric('emExcite','Excited port index',e.solver.excited_port??1)}</div></details>
 <div class="table-wrap"><table class="data-table"><thead><tr><th>Port</th><th>Kind</th><th>Component</th><th>Pin / impedance</th><th></th></tr></thead><tbody>${e.ports.map((p,i)=>`<tr><td>${p.index}</td><td>${esc(p.kind)}</td><td>${esc(p.component)}</td><td>${esc(p.pin||p.impedance_ohm||p.native_attributes||'—')}</td><td><button class="secondary mini" type="button" data-edit-port="${i}">Edit</button><button class="secondary mini" type="button" data-delete-port="${i}">×</button></td></tr>`).join('')||'<tr><td colspan="5">Add at least one reviewed physical port/terminal.</td></tr>'}</tbody></table></div>
 <div class="button-stack"><button class="secondary" type="button" id="addEMPort">+ Add physical port</button><button class="secondary" id="saveEMSettings">Apply study settings</button><button class="secondary" id="deleteEMStudy">Remove study</button></div>
 <div class="divider"></div><div class="button-stack"><button class="secondary" id="checkEM">Check draft mapping</button><button class="primary" id="runEM" ${dirty||!engineInstalled('sqdmetal_palace')?'disabled':''}>Run saved EM study</button></div>
 <div id="emCheckResult" aria-live="polite"><p class="helper">Draft validation is not a native solver or convergence test. Save before execution. Reviewed Palace eigenmode solves have a 15-minute job budget; native mesh/deck-only is the first step. No result implies automatic mesh convergence.</p></div>`}`);
 return `<div class="stacked-workflow">${process}${study}</div>`;
}
function changeEmSettings(){const s=selectedEMStudy();if(!s)throw Error('Create an EM study first');const em=s.inputs.em;
 const id=readText('emID');if(!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(id)||activeModel().studies.some(x=>x!==s&&x.id===id))throw Error('Study ID invalid or duplicated');
 s.id=id;emSelectedId=id;s.kind=readText('emKind');em.execution=readText('emExecution');em.ground={kind:'qdesign_ground_plane',layer:readNumber('emGround',{integer:true,min:1,max:255}),verified:$('emGroundCheck').value==='true'};
 for(const k of Object.keys(em.boundaries).filter(x=>x!=='farfield'))em.boundaries[k]=readNumber('em_'+k,{min:0});
 em.boundaries.farfield=$('emFarfield').value;em.mesh={min_um:readNumber('emMeshMin',{min:0.01}),max_um:readNumber('emMeshMax',{min:0.01}),relative_tolerance:readNumber('emMeshTol',{min:0.00000001,max:0.25}),refinement_levels:$('emMeshLevels').value.split(',').map(Number)};
 const solver={order:readNumber('emSolver_order',{integer:true,min:1,max:4}),tolerance:readNumber('emSolver_tolerance',{min:1e-15,max:1e-2}),max_iterations:readNumber('emSolver_max_iterations',{integer:true,min:1,max:1000}),num_cpus:readNumber('emSolver_num_cpus',{integer:true,min:1,max:8})};
 if(s.kind==='eigenmode'){solver.start_hz=readNumber('emStartHz',{min:1e6,max:1e11});solver.modes=readNumber('emModes',{integer:true,min:1,max:12})}
 if(s.kind==='sparameters'){
  const lo=readNumber('emFreqMin',{min:1e6,max:1e11}),hi=readNumber('emFreqMax',{min:1e6,max:1e11}),n=readNumber('emFreqPoints',{min:2,max:201,integer:true});if(hi<=lo)throw Error('Frequency stop must exceed start');
  solver.frequencies_hz=Array.from({length:n},(_,i)=>lo+(hi-lo)*i/(n-1));solver.excited_port=readNumber('emExcite',{min:1,max:16,integer:true});
 }
 em.solver=solver;if(s.kind==='capacitance')em.boundaries.farfield='ground';else em.boundaries.farfield='pec';
 markDirty();render();
}
function editEMPort(index){const s=selectedEMStudy();if(!s)return;const e=s.inputs.em;const old=index<0?{}:e.ports[index];
 const chosen=old.kind|| (s.kind==='capacitance'?'conductor':'cpw_launcher');
 const kinds=s.kind==='capacitance'?['conductor']:s.kind==='eigenmode'?['cpw_launcher','cpw_route','junction']:['cpw_launcher','cpw_route'];
 const form=`${selection('portKind','Physical port kind',kinds,chosen)}
 ${selection('portComponent','QComponent',activeModel().layout.components.filter(c=>!isRoute(c.kind)||c.kind==='RouteStraight'||c.kind==='RouteMeander').map(c=>c.name),old.component)}
 <div class="row">${field('Route pin (start/end)','portPin',old.pin||'start')}${numeric('portLength','Port length · µm',old.length_um??20)}${numeric('portImpedance','Reference impedance · Ω',old.impedance_ohm??50)}</div>
 <div class="row">${numeric('portL','Junction L · nH',old.L_nH??4.3)}${numeric('portC','Junction C · fF',old.C_fF??10)}${field('Conductor tag(s), comma separated','portTags',(old.native_attributes||[1]).join(','))}</div>
 <p class="helper">Identify the exact physical pin, port and native conductor tags after inspecting QDesign. SQE does not guess correspondences.</p><button class="primary full" id="confirmPort">${index<0?'Add':'Update'} physical mapping</button>`;
 openDialog('Physical port mapping',form);
 $('confirmPort').onclick=()=>{try{
  const kind=readText('portKind'),component=readText('portComponent');let p={index:index<0?e.ports.length+1:index+1,kind,component};
  if(kind==='conductor'){
   p.native_attributes=readText('portTags').split(',').map(v=>{const n=Number(v.trim());if(!Number.isInteger(n)||n<1)throw Error('Positive integer native conductor tags required');return n});
  }else if(kind==='junction'){p.L_nH=readNumber('portL',{min:0.001});p.C_fF=readNumber('portC',{min:0})}
  else{p.length_um=readNumber('portLength',{min:0.001});p.impedance_ohm=readNumber('portImpedance',{min:0.001});if(kind==='cpw_route')p.pin=readText('portPin')}
  if(index<0)e.ports.push(p);else e.ports[index]=p;
  markDirty();closeDialog();render();
 }catch(err){toast(err.message,true)}};
}
function wireEM(){
 $('applyMaterials').onclick=()=>{try{
  const m=activeModel(),thick=readNumber('matThickness',{min:0.01,max:1000});
  m.process.stack=[{role:'substrate',material:readText('matSubstrate'),thickness_um:thick,relative_permittivity:readNumber('matEps',{min:0.00001}),loss_tangent:readNumber('matLoss',{min:0,max:1})},
    {role:'metal',material:'aluminium',layer:readNumber('matMetalLayer',{min:1,max:255,integer:true}),thickness_nm:readNumber('matMetalThickness',{min:0.01}),em_model:'PEC'},
    {role:'superstrate',material:'vacuum',height_um:readNumber('matAir',{min:0.01}),relative_permittivity:1,loss_tangent:0}];
  m.layout.chip.thickness_um=thick;clearPhysicalReview();markDirty();render();toast('Material inputs changed; expert review invalidated.');
 }catch(err){toast(err.message,true)}};
 $('reviewMaterials').onclick=()=>{try{
  const reviewer=readText('matReviewer'),url=readText('matSource'),rationale=readText('matRationale');
  if(!/^[A-Za-z][A-Za-z0-9_]{2,47}$/.test(reviewer)||!/^https:\/\/[^\s]{4,240}$/.test(url)||rationale.length<20||!$('matConfirm').checked)throw Error('Reviewer ID, HTTPS source, ≥20-character rationale and explicit acknowledgement required');
  if(activeModel().process.stack.length!==3)throw Error('Apply a complete material stack first');
  activeModel().process.rules.gui_review={reviewer,source_url:url,rationale,status:'assumption_review_only'};
  activeModel().process.source='reviewed';markDirty();render();toast('Expert assumption review recorded, not independently validated');
 }catch(err){toast(err.message,true)}};
 if($('newEMStudy'))$('newEMStudy').onclick=()=>{
  const s=blankEMStudy(),existing=new Set(activeModel().studies.map(x=>x.id));let n=1;while(existing.has('EM'+n))n++;s.id='EM'+n;
  activeModel().studies.push(s);emSelectedId=s.id;markDirty();render();
 };
 if(!$('emStudy'))return;
 $('emStudy').onchange=e=>{emSelectedId=e.target.value;render()};
 // The selector exists even when the project has zero native EM studies.
 // The remaining controls only exist for a selected study; do not dereference null.
 if(!selectedEMStudy())return;
 $('saveEMSettings').onclick=()=>{try{changeEmSettings();toast('Native study settings added to design draft')}catch(e){toast(e.message,true)}};
 $('cloneEMStudy').onclick=()=>{try{
  const source=selectedEMStudy(),copy=JSON.parse(JSON.stringify(source));const ids=new Set(activeModel().studies.map(s=>s.id));let n=1;while(ids.has(source.id+'_'+n))n++;copy.id=source.id+'_'+n;
  if(copy.id.length>48||activeModel().studies.length>=30)throw Error('Study limit reached; rename or remove a study');
  activeModel().studies.push(copy);emSelectedId=copy.id;markDirty();render();
 }catch(e){toast(e.message,true)}};
 $('deleteEMStudy').onclick=()=>{const s=selectedEMStudy();activeModel().studies=activeModel().studies.filter(x=>x!==s);emSelectedId='';markDirty();render()};
 $('addEMPort').onclick=()=>editEMPort(-1);
 document.querySelectorAll('[data-edit-port]').forEach(b=>b.onclick=()=>editEMPort(Number(b.dataset.editPort)));
 document.querySelectorAll('[data-delete-port]').forEach(b=>b.onclick=()=>{const e=selectedEMStudy().inputs.em;e.ports.splice(Number(b.dataset.deletePort),1);e.ports.forEach((p,i)=>p.index=i+1);markDirty();render()});
 $('checkEM').onclick=async()=>{try{
  const result=await api('/api/design/check','POST',{model:activeModel()});
  const em=result.em.find(r=>r.study_id===selectedEMStudy()?.id),el=$('emCheckResult');
  el.innerHTML=`<div class="callout ${result.layout.ready&&em?.ready?'':'warn'}">Layout: ${esc(result.layout.message||'Unknown')}. EM: ${esc(em?.message||'No study')}.</div><p class="helper">Review and native execution are separate. This check cannot establish convergence.</p>`;
 }catch(e){toast(e.message,true)}};
 $('runEM').onclick=()=>runSavedStudy('sqdmetal_palace',selectedEMStudy()?.id);
}

/* Native parametric exploration: only numeric INPUTS already in a saved engine study. */
function sweepableInputs(study){
 const result=[];
 const scan=(o,path,depth)=>{if(depth>3)return;for(const [key,val] of Object.entries(o||{})){
  if(!/^[A-Za-z][A-Za-z0-9_]*$/.test(key))continue;
  const next=path?[path,key].join('.'):key;
  if(typeof val==='number'&&Number.isFinite(val))result.push([next,val]);
  else if(val&&typeof val==='object'&&!Array.isArray(val))scan(val,next,depth+1);
 }};
 scan(study.inputs,'',0);return result;
}
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
 document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>{if(!b.disabled)window.location.assign(`/api/projects/${project.id}/runs/${encodeURIComponent(b.dataset.download)}/download`)});
 document.querySelectorAll('[data-get-result]').forEach(b=>b.onclick=()=>inspectResult(b.dataset.getResult));
 if($('compareRuns')){const done=runs.filter(r=>r.state==='completed'&&!r.is_sweep&&!r.unsafe_location);$('compareRight').value=done[1].id;$('compareRuns').onclick=compareSavedRuns;}
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
 if(id==='em')wireEM();
 if(id==='quantum'){
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
 if(prior?.model===model&&prior.convergence)inputs.convergence=prior.convergence;
 if((model==='Fluxonium'||model==='TunableTransmon')&&$('qFluxValues')?.value.trim()){
  const raw=$('qFluxValues').value.split(',').map(x=>x.trim());
  if(raw.length<2||raw.length>21||raw.some(x=>x===''||!Number.isFinite(Number(x))||Number(x)<0||Number(x)>1))throw Error('Flux sweep requires 2–21 finite values between 0 and 1 Phi0');
  inputs.sweep={subsystem:'primary',parameter:'flux',values:raw.map(Number),unit:'Phi0'};
 }
 // Applying edited inputs never changes the scientific source to EM-derived.
 setStudy('scqubits','spectrum',inputs);
}
function setStudy(engine,kind,inputs){const m=activeModel();let index=m.studies.findIndex(s=>s.engine===engine);
 const study={id:engine+'_primary',engine,kind,inputs};if(index>=0)m.studies[index]=study;else m.studies.push(study);markDirty()}
function markDirty(){dirty=true;$('saveButton').textContent='● Save changes';$('stageBadge').textContent='Unsaved draft';$('stageBadge').className='status warn'}
async function save(){if(!project)return false;if(!dirty){toast('No unsaved changes');return true}try{const obj=await api(`/api/projects/${project.id}/commit`,'POST',{expected_revision:project.head,model:activeModel()});await loadProject(project.id);toast('Revision saved · '+obj.revision.slice(0,8));return true}catch(err){toast(err.message,true);return false}}
async function runSavedStudy(engine,studyId=null){
 try{
  if(!engineValidated(engine))throw Error('Native engine is unavailable or its input mapping remains blocked. Check Engine health.');
  if(dirty)throw Error('Save the current revision before running any native engine');
  const s=studyId?activeModel().studies.find(x=>x.engine===engine&&x.id===studyId):currentStudy(engine);if(!s)throw Error('Prepare and save a supported study before execution');
  if(engine==='quantum_metal'&&!layoutInputsValid())throw Error('Chip dimensions and placement bounds must be valid before native export');
  const result=await api(`/api/projects/${project.id}/runs`,'POST',{revision:project.head,study_id:s.id});
  toast('Revision-bound native job queued: '+result.run_id.slice(0,8));step=5;await loadProject(project.id);setTimeout(refreshRuns,1600);
 }catch(err){toast(err.message,true)}
}
async function refreshRuns(){if(!project)return;try{runs=(await api(`/api/projects/${project.id}/runs`)).runs;render();if(runs.some(x=>x.state==='running'||x.state==='queued'))setTimeout(refreshRuns,1700)}catch(err){toast(err.message,true)}}
async function inspectResult(id){const job=runs.find(x=>x.id===id);if(!job)return toast('Unknown job',true);if(job.unsafe_location)return toast('Unsafe native run path; inspection blocked',true);if(job.state!=='completed'){openDialog('Job status · '+job.state,`<div class="callout warn">${esc(job.engine)} / ${esc(job.study_id)}: ${esc(job.state)}. No native result manifest is available. ${['failed','timed_out'].includes(job.state)?'Download the run ZIP for FAILURE.json and engine.log evidence.':'The job has not produced a result.'}</div><p class="helper">Source revision ${esc(job.revision_id)}. No scientific outputs are inferred from failure.</p><button class="secondary" id="downloadFailure" ${['queued','running'].includes(job.state)?'disabled':''}>Download diagnostic ZIP</button>`);$('downloadFailure').onclick=()=>window.location.assign(`/api/projects/${project.id}/runs/${encodeURIComponent(id)}/download`);return;}try{let r;try{if(job.is_sweep){const sweep=await api(`/api/projects/${project.id}/runs/${id}/sweep`);if($('resultView'))$('resultView').innerHTML=sweepView(sweep);else openDialog('Native parametric exploration',sweepView(sweep));return;}r=await api(`/api/projects/${project.id}/runs/${id}/result`)}catch(error){if(error.status!==404)throw error;const sweep=await api(`/api/projects/${project.id}/runs/${id}/sweep`);if($('resultView'))$('resultView').innerHTML=sweepView(sweep);else openDialog('Native parametric exploration',sweepView(sweep));return;}
 const m=r.manifest;if(m.revision_id!==job.revision_id||m.engine!==job.engine||m.study_id!==job.study_id||m.schema!=='sqe.artifact.v1')throw Error('Result manifest provenance does not match the requested run');let view=`<div class="kicker">Native engine artifact · not independently qualified</div><div class="row align between"><h2>${esc(m.engine)}</h2><span class="pill">${esc(m.scientific_status)}</span></div><div class="engine-status"><span>Revision</span><span>${esc(m.revision_id)}</span></div><div class="engine-status"><span>Project SHA-256</span><span>${esc(m.project_digest)}</span></div><div class="engine-status"><span>Engine version</span><span>${esc(m.engine_version)}</span></div><div class="engine-status"><span>Fabrication status</span><span>${esc(m.fabrication_status)}</span></div><div class="muted-label">Native file checksums</div>${(m.artifacts||[]).map(a=>`<div class="engine-status"><span>${esc(a.name)}</span><small title="${esc(a.sha256)}">${esc(String(a.sha256).slice(0,16))}… · ${esc(a.bytes)} bytes</small></div>`).join('')}`;
 if(r.spectrum)view+=nativeSpectrum(r.spectrum);
 if(r.eigenmodes)view+=palaceModeTable(r.eigenmodes);
 view+=goalComparison(r);
 view+=`<div class="callout warn">Native result only. Independent convergence, scientific qualification, and fabrication approval are not established.</div>`;
 if($('resultView'))$('resultView').innerHTML=pane('Result inspection','Native files remain in the immutable run archive.',view);
 else openDialog('Native result',view);
 }catch(err){toast(err.message,true)}}
function goStep(next){step=Math.max(0,Math.min(next,6));render();if(step===5&&project)refreshRuns();window.scrollTo(0,0);$('pageTitle').setAttribute('tabindex','-1');$('pageTitle').focus({preventScroll:true})}
function openDialog(title,html){
 if($('overlay').classList.contains('hidden'))dialogReturnFocus=document.activeElement;
 $('dialogTitle').textContent=title;$('dialogBody').innerHTML=html;$('overlay').classList.remove('hidden');
 const first=$('dialogBody').querySelector('input:not([disabled]),button:not([disabled]),select:not([disabled])');
 (first||$('closeDialog')).focus();
}
function closeDialog(){$('overlay').classList.add('hidden');$('dialogBody').innerHTML='';if(dialogReturnFocus?.isConnected)dialogReturnFocus.focus();dialogReturnFocus=null}
function dialogKeys(event){
 if($('overlay').classList.contains('hidden'))return;
 if(event.key==='Escape'){event.preventDefault();closeDialog();return}
 if(event.key!=='Tab')return;
 const choices=[...$('overlay').querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href]')].filter(e=>e.getClientRects().length);
 if(!choices.length)return;
 const first=choices[0],last=choices[choices.length-1];
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
}
function useCaseOverview(){return `<details class="design-cases"><summary>Published-method design cases · supported and planned</summary><p class="helper">These are scientific design goals, not separate tools or solver shortcuts. Unavailable transitions are explicitly blocked.</p>${designCases.map(c=>`<div class="engine-status"><div><strong>${esc(c.title)}</strong><br><small>${esc(c.purpose)}<br>Reference: <a href="${esc(c.reference_url)}" target="_blank" rel="noopener noreferrer">${esc(c.reference_title)}</a><br>Acceptance: ${esc(c.acceptance.join(' · '))}</small></div><span class="${c.starter_template?'available':'unavailable'}">${c.starter_template?'Editable starting point':'Blocked edge'}</span></div>${c.next_missing_edge?`<p class="helper">Required before enablement: ${esc(c.next_missing_edge)}</p>`:''}`).join('')}</details>`}
function capabilityOverview(){return `<details class="design-cases"><summary>EDA integration boundaries and missing links</summary><p class="helper">Native available means conditionally supported, never independently qualified.</p>${edaCapabilities.map(e=>`<div class="engine-status"><div><strong>${esc(e.source)} → ${esc(e.destination)}</strong><br><small>${esc(e.scientific_gate)}</small></div><span class="${e.status==='blocked'?'unavailable':'available'}">${esc(e.status.replaceAll('_',' '))}</span></div>`).join('')}</details>`}
function newProjectForm(){return `<p class="helper">Create an editable design. Starter designs use the exact same editor, saved revisions, native study API and validation as blank projects.</p>${field('Project name','newProjectName','My Quantum Circuit')}
 ${selection('newProjectTemplate','Start from',[['','Blank project'],...designTemplates.map(t=>[t.id,t.title])],'')}
 <p class="helper" id="templateInfo">No example-specific workspace or solver is created.</p>${useCaseOverview()}${capabilityOverview()}
 <label class="form-field"><span>Design family</span><select id="newProjectFamily"><option value="generic">Generic circuit</option><option value="transmon">Transmon</option><option value="fluxonium">Fluxonium</option><option value="resonator">Resonator</option><option value="amplifier">Quantum amplifier</option><option value="multi_qubit">Multi-qubit</option></select></label><button class="primary full" id="confirmNew">Create editable project →</button>`}
function projectList(){return `<p class="helper">The current project and revision are the source of truth for all engine jobs.</p><button class="primary full" id="createOther">+ New project</button><div class="divider"></div>${projects.map(p=>`<button class="utility" data-open-project="${p.id}">▧ ${esc(p.name)} <span>${esc(p.head.slice(0,6))}</span></button>`).join('')}`}
async function history(){if(!project)return toast('Create a project first',true);const r=await api(`/api/projects/${project.id}/revisions`);
 openDialog('Revision history',`<p class="helper">Immutable snapshots · Open an older revision for inspection without overwriting the current head.</p>${r.revisions.map(v=>`<div class="engine-status"><span><b>${esc(v.id.slice(0,10))}</b><br><small>${new Date(v.created*1000).toLocaleString()}</small></span><button class="secondary mini" data-history="${v.id}">View</button></div>`).join('')}`);
 document.querySelectorAll('[data-history]').forEach(b=>b.onclick=async()=>{const snap=await api(`/api/projects/${project.id}/revisions/${b.dataset.history}`);openDialog('Revision '+snap.revision.slice(0,10),`<div class="callout">Read-only historical revision. Current head: ${esc(snap.head.slice(0,10))}.</div><pre class="pre-scroll">${esc(JSON.stringify(snap.model,null,2))}</pre>`)})}
async function engineDialog(){engines=(await api('/api/engines')).engines;openDialog('Native engine health',`<p class="helper">Detected dependencies are not solver validation. Full stack qualification requires per-engine native smoke, convergence, and benchmark evidence.</p>${engines.map(e=>`<div class="engine-status"><div><strong>${esc(e.name)}</strong><br><small>${esc(e.capability)}</small></div><span class="${engineValidated(e.id)?'available':'unavailable'}">${engineValidated(e.id)?'Installed · limited native port':e.available?'Installed · mapping blocked':'Missing / blocked'}</span></div><p class="helper">Adapter mode: ${esc(e.mode)}. Installation alone is not validation or scientific qualification.</p>`).join('')}`)}
function wireGlobal(){
 $('authForm').onsubmit=e=>{e.preventDefault();authenticate()};
 $('saveButton').onclick=save;$('prevButton').onclick=()=>goStep(step-1);$('nextButton').onclick=()=>goStep(step+1);
 $('projectChooser').onclick=()=>openDialog('Projects',projectList());
 $('enginesButton').onclick=engineDialog;$('railEngines').onclick=engineDialog;$('historyButton').onclick=history;$('railHistory').onclick=history;
 $('expertButton').onclick=()=>{expert=!expert;render();toast(expert?'Expert controls enabled where supported':'Guided mode enabled')};
 $('inspectorButton').onclick=()=>{inspector=!inspector;render()};$('closeInspector').onclick=()=>{inspector=false;render()};
 $('signOutButton').onclick=async()=>{await api('/api/logout','POST',{});csrf='';project=null;setupView()};
 $('closeDialog').onclick=closeDialog;document.addEventListener('keydown',e=>{dialogKeys(e);if(!$('overlay').classList.contains('hidden')||e.altKey===false||e.ctrlKey||e.metaKey||e.target.closest('input,textarea,select'))return;if(/^[1-7]$/.test(e.key)){e.preventDefault();goStep(Number(e.key)-1)}});$('overlay').onclick=e=>{if(e.target===$('overlay'))closeDialog()};
 document.addEventListener('change',e=>{
  if(e.target?.id==='newProjectTemplate'){
   const t=designTemplates.find(t=>t.id===e.target.value);if(t){$('newProjectFamily').value=t.family;$('templateInfo').textContent=t.description+' Source: '+t.reference+'; not scientifically qualified.'}
   else $('templateInfo').textContent='Blank design · all engine and material mappings start unverified.';
  }
 });
 document.addEventListener('click',async e=>{
  if(e.target?.id==='confirmNew'){try{const args={name:$('newProjectName').value,family:$('newProjectFamily').value};if($('newProjectTemplate').value)args.template_id=$('newProjectTemplate').value;const p=await api('/api/projects','POST',args);project=p;closeDialog();await reload();toast('Project created')}catch(err){toast(err.message,true)}}
  if(e.target?.id==='createOther')openDialog('New project',newProjectForm());
  const b=e.target.closest('[data-open-project]');if(b){closeDialog();await loadProject(b.dataset.openProject)}
 });
}
async function start(){wireGlobal();try{const me=await api('/api/me');csrf=me.csrf;$('application').classList.remove('hidden');await reload()}catch{setupView()}}
start();
