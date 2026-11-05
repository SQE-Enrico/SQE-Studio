function renderStages(){
 const statuses=project?.stages||{};
 $('stages').innerHTML=STEPS.map(([id,name],i)=>`<button type="button" class="${i===step?'active':''}" data-step="${i}" ${i===step?'aria-current="step"':''} title="${esc(name)}"><span class="stage-num">${String(i+1).padStart(2,'0')}</span><span>${esc(name)}</span><i aria-hidden="true" class="step-state ${statuses[id]==='draft_saved'?'saved':''}"></i></button>`).join('');
 const glyphs=['◎','⌁','▦','≋','◈','▥','⬡'];
 $('railStages').innerHTML=STEPS.map(([,name],i)=>`<button type="button" class="rail-button ${i===step?'active':''}" data-step="${i}" aria-label="${esc(name)}" ${i===step?'aria-current="step"':''} title="${esc(name)} (Alt+${i+1})">${glyphs[i]}</button>`).join('');
 document.querySelectorAll('[data-step]').forEach(e=>e.onclick=()=>goStep(Number(e.dataset.step)));
}
function setupView(){
 $('auth').classList.remove('hidden');$('application').classList.add('hidden');
 api('/api/status').then(s=>{UI.setup=!!s.setup_required;$('authTitle').textContent=UI.setup?'Create administrator':'Your integrated design workspace';$('authCaption').textContent=UI.setup?'Private first-run account · Keep your setup token secret.':'Sign in to your local workspace.';$('setupTokenLabel').classList.toggle('hidden',!UI.setup);$('authSubmit').textContent=UI.setup?'Create local account →':'Sign in →'}).catch(err=>$('authError').textContent=err.message);
}
async function authenticate(){try{
 $('authError').textContent='';const data={email:$('email').value,password:$('password').value};
 if(UI.setup){await api('/api/setup','POST',{...data,setup_token:$('setupToken').value});UI.setup=false;}
 const auth=await api('/api/login','POST',data);csrf=auth.csrf;
 $('auth').classList.add('hidden');$('application').classList.remove('hidden');await reload();
 }catch(err){$('authError').textContent=err.message}}
// Project read is the authoritative workspace state. A transient engine/catalog
// discovery failure must not erase a revision which the server has persisted.
async function reload(){
 const listing=await api('/api/projects');projects=listing.projects;
 const failed=[];
 for(const [path,key,field] of [
  ['/api/engines','engines','engines'],
  ['/api/design/templates','designTemplates','templates'],
  ['/api/design/use-cases','designCases','cases'],
  ['/api/design/scientific-references','scientificReferences','cases'],
  ['/api/design/capabilities','edaCapabilities','edges'],
  ['/api/design/components','componentCatalog','components']]){
  try{const result=await api(path);UI[key]=result[field];}
  catch(error){UI[key]=[];failed.push(path);}
 }
 engines=UI.engines;designTemplates=UI.designTemplates;designCases=UI.designCases;
 edaCapabilities=UI.edaCapabilities;componentCatalog=UI.componentCatalog;
 if(project&&projects.some(x=>x.id===project.id))await loadProject(project.id);
 else if(projects.length)await loadProject(projects[0].id);
 else{project=null;step=0;render();openDialog('Create your first project',newProjectForm())}
 if(failed.length)toast('Native engine or design catalog discovery unavailable; dependent actions remain blocked until refreshed.',true);
}
async function loadProject(id){
 // Multiple project reads may overlap during navigation and persisted revision saves.
 // Only the newest request may publish a project or its job history.
 const loadToken=++projectLoadToken;
 ++runHistoryRequestToken;invalidateComparison();
 clearTimeout(refreshTimer);refreshTimer=null;selectedResult=null;resultRequestToken++;
 const loaded=await api(`/api/projects/${id}`);
 // Run-list retrieval is independent of persisted project revision verification.
 // A failed run GET must never be represented as an empty verified history.
 let listed;
 try{listed=await api(`/api/projects/${id}/runs`);if(loadToken===projectLoadToken)runHistoryError='';}
 catch(error){if(loadToken===projectLoadToken)runHistoryError='Job history unavailable ('+error.message+'). Retry Refresh job states; no native evidence is implied.';}
 if(loadToken!==projectLoadToken)return false;
 project=loaded;runs=listed?.runs||[];dirty=false;selectedCanvasItem=null;emSelectedId='';runFilter='all';transmonDraft=null;transmonDraftIdentity='';transmonConflict=false;transmonSaveMessage='';manualTransmonDraft=null;++manualTransmonCheckToken;render();
 return true;
}
function currentStudy(engine){return activeModel()?.studies.find(s=>s.engine===engine&&(engine!=='scqubits'||s.kind!=='extracted_transmon_research'))||null}
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
    <div class="callout">Target mapping in Results: <code>f01</code> (GHz, native scqubits); <code>em_mode_1</code> (GHz, native Palace mode index); <code>em_Q_mode_1</code> (unit 1, native total Q). Mode indexes are not physical mode IDs. For a saved JosephsonCircuits RF run, use <code>rf_S21_mag_at_5GHz</code> (unit 1) or <code>rf_S21_dB_at_5GHz</code> (unit dB): only a matching sampled 5 GHz point is used, without interpolation. S21 means output port 2 / input port 1 on the schematic reference planes; it is not independently validated gain. Other names remain design intent until a reviewed mapping exists. Targets never set a Hamiltonian.</div>`)}</div>`;
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
  <div class="row"><label class="form-field"><span>Basis check</span><select id="qConvMode"><option value="off" ${!s?.inputs?.convergence?.enabled?'selected':''}>Disabled</option><option value="single" ${s?.inputs?.convergence?.enabled&&!(s.inputs.convergence.steps>1)?'selected':''}>One expansion</option><option value="curve" ${s?.inputs?.convergence?.steps>1?'selected':''}>Convergence curve</option></select></label>${field('Cutoff increment · 1–6','qConvIncrement',s?.inputs?.convergence?.basis_increment??5,'number')}${field('Expansions · 2–4 for curve','qConvSteps',s?.inputs?.convergence?.steps??3,'number')}${field('Absolute tolerance · GHz','qConvTolerance',s?.inputs?.convergence?.tolerance_GHz??0.00001,'number')}</div>
  <p class="helper">A curve evaluates successive native cutoffs and checks the last two intervals. 0.00001 GHz = 10 kHz. This numerical target is editable; it is not an experimental accuracy claim. Curves use a standalone model without a flux sweep.</p>
  <div class="row"><button class="secondary" id="addQuantumStudy">Apply study to draft</button><button class="primary" id="quantumRun" ${canRun('scqubits')?'':'disabled'}>Run saved study →</button></div><div class="callout">Engine inputs are independent explicit Hamiltonian parameters. No EM-to-Hamiltonian extraction is assumed until a verified mapping is available.</div>`)}
  ${pane('JosephsonCircuits.jl','Native nonlinear/RF circuit analysis must use its own verified port/netlist mapping.',`${engineInfo('josephson_circuits')}<div class="callout warn">No SQE numerical replacement. A qualified Julia adapter and reviewed RF port/netlist correspondence are required before execution.</div>`)}</div>${conditionalExtractionStudies()}${independentTransmonEditor()}`;
 }
 if(id==='results')return `${resultsOverview()}${transmonResultsContext()}${designExplorationControls()}${pane('Native solver output','Revision-bound jobs; a completed state is not evidence verification.',runsTable(true))}<div id="compareSection">${compareControls()}</div><section id="resultView" role="region" aria-label="Selected native run evidence" tabindex="-1">${!runHistoryError&&selectedResult?.projectId===project.id&&runs.some(r=>sameSafeRun(r,selectedResult.job))?selectedResult.html:''}</section><div id="comparisonView" aria-live="polite"></div>`;
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
