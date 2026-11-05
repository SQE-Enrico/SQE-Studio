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
 return `<div class="stacked-workflow">${process}${study}${transmonSelectionEditor()}</div>`;
}
function changeEmSettings(){const s=selectedEMStudy();if(!s)throw Error('Create an EM study first');const em=s.inputs.em;
 const id=readText('emID');if(!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(id)||activeModel().studies.some(x=>x!==s&&x.id===id))throw Error('Study ID invalid or duplicated');
 s.id=id;emSelectedId=id;s.kind=readText('emKind');em.execution=readText('emExecution');em.ground={...em.ground,kind:'qdesign_ground_plane',layer:readNumber('emGround',{integer:true,min:1,max:255}),verified:$('emGroundCheck').value==='true'};
 for(const k of Object.keys(em.boundaries).filter(x=>x!=='farfield'))em.boundaries[k]=readNumber('em_'+k,{min:0});
 em.boundaries.farfield=$('emFarfield').value;em.mesh={min_um:readNumber('emMeshMin',{min:0.01}),max_um:readNumber('emMeshMax',{min:0.01}),relative_tolerance:readNumber('emMeshTol',{min:0.00000001,max:0.25}),refinement_levels:$('emMeshLevels').value.split(',').map(Number)};
 const solver={order:readNumber('emSolver_order',{integer:true,min:1,max:4}),tolerance:readNumber('emSolver_tolerance',{min:1e-15,max:1e-2}),max_iterations:readNumber('emSolver_max_iterations',{integer:true,min:1,max:1000}),num_cpus:readNumber('emSolver_num_cpus',{integer:true,min:1,max:16})};
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
 <div class="row">${selection('portGeometry','Named pad (capacitance only)',[['','Whole component / legacy'],['pad_bot','pad_bot'],['pad_top','pad_top']],old.qgeometry||'')}${field('Conductor label','portLabel',old.label||'')}${numeric('portNativeIndex','Original native terminal index',old.native_terminal_index??'')}</div>
 <p class="helper">Identify the exact physical pin, named pad and native conductor tags after inspecting QDesign. SQE checks declared identities and blocks mismatches.</p><button class="primary full" id="confirmPort">${index<0?'Add':'Update'} physical mapping</button>`;
 openDialog('Physical port mapping',form);
 $('confirmPort').onclick=()=>{try{
  const kind=readText('portKind'),component=readText('portComponent');let p={index:index<0?e.ports.length+1:index+1,kind,component};
  if(kind==='conductor'){
   p.native_attributes=readText('portTags').split(',').map(v=>{const n=Number(v.trim());if(!Number.isInteger(n)||n<1)throw Error('Positive integer native conductor tags required');return n});
   const geometry=readText('portGeometry');
   if(geometry){p.qgeometry=geometry;p.label=readText('portLabel');p.native_terminal_index=readNumber('portNativeIndex',{integer:true,min:1,max:3});if(!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(p.label))throw Error('Explicit ASCII conductor label required')}
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
 if(study.kind==='extracted_transmon_research')return [];
 const result=[];
 const scan=(o,path,depth)=>{if(depth>3)return;for(const [key,val] of Object.entries(o||{})){
  if(!/^[A-Za-z][A-Za-z0-9_]*$/.test(key))continue;
  const next=path?[path,key].join('.'):key;
  if(typeof val==='number'&&Number.isFinite(val))result.push([next,val]);
  else if(val&&typeof val==='object'&&!Array.isArray(val))scan(val,next,depth+1);
 }};
 scan(study.inputs,'',0);return result;
}
