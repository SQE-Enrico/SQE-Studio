function transmonFamily(model){return model&&['transmon','multi_qubit'].includes(model.family)}
function transmonStudies(model){return Array.isArray(model?.studies)?model.studies.filter(s=>s?.engine==='sqdmetal_palace'&&s.kind==='capacitance'):[]}
function transmonPortLabel(port){return port&&Object.hasOwn(port,'qgeometry')?port.label:port?.component}
function transmonInventory(study){
 if(!study||study.engine!=='sqdmetal_palace'||study.kind!=='capacitance')return {ok:false,reason:'Select an explicit Palace capacitance study.'};
 const ports=study.inputs?.em?.ports;
 if(!Array.isArray(ports)||ports.length<2)return {ok:false,reason:'The study must provide at least two explicit conductor ports.'};
 const names=[],seen=new Set(),tags=new Set();
 for(const p of ports){
  const label=transmonPortLabel(p);
  if(!p||p.kind!=='conductor'||typeof p.component!=='string'||!p.component||typeof label!=='string'||!label||label!==label.trim()||seen.has(label))
   return {ok:false,reason:'Port components must be distinct nonempty exact conductor IDs; duplicates are blocked.'};
  if(Object.hasOwn(p,'qgeometry')&&(!['pad_top','pad_bot'].includes(p.qgeometry)||!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(label)||!Number.isSafeInteger(p.native_terminal_index)))
   return {ok:false,reason:'Named pad terminals require explicit QGeometry, conductor labels and native indices.'};
  if(!Array.isArray(p.native_attributes)||!p.native_attributes.length||p.native_attributes.some(t=>!Number.isSafeInteger(t)||t<=0||tags.has(t))||
     new Set(p.native_attributes).size!==p.native_attributes.length)
   return {ok:false,reason:'Each conductor must have its own explicit positive native physical tags.'};
  seen.add(label);names.push(label);p.native_attributes.forEach(t=>tags.add(t));
 }
 return {ok:true,names};
}
function newTransmonDraft(){return {study_id:'',island_a:'',island_b:'',policy:Object.create(null),configuration:'',junctionAccepted:false,savedInvalid:false}}
function transmonDraftFromSaved(saved){
 const draft=newTransmonDraft();
 if(saved&&typeof saved==='object'&&!Array.isArray(saved)){
  draft.study_id=typeof saved.study_id==='string'?saved.study_id:'';
  draft.island_a=typeof saved.island_a==='string'?saved.island_a:'';
  draft.island_b=typeof saved.island_b==='string'?saved.island_b:'';
  draft.configuration=typeof saved.configuration==='string'?saved.configuration:'';
  draft.junctionAccepted=saved.junction_capacitance_assumption===TRANSMON_JUNCTION;
  const policy=saved.other_terminal_policy;
  for(const type of ['fixed_zero','floating_zero_charge'])if(Array.isArray(policy?.[type]))for(const id of policy[type]){
   if(typeof id==='string'&&!Object.hasOwn(draft.policy,id))draft.policy[id]=type;
  }
 }
 return draft;
}
function ensureTransmonDraft(){
 const identity=project?.id+'@'+project?.head;
 if(transmonDraft!==null&&transmonDraftIdentity===identity)return transmonDraft;
 transmonDraftIdentity=identity;
 const saved=activeModel()?.intent?.transmon_capacitance_selection;
 const draft=transmonDraftFromSaved(saved);
 if(saved){
  try{if(!sameTransmonSelection(saved,validatedTransmonSelection(activeModel(),draft)))draft.savedInvalid=true}
  catch{draft.savedInvalid=true}
 }
 transmonDraft=draft;return draft;
}
function validatedTransmonSelection(model,draft){
 if(!transmonFamily(model))throw Error('Selection is only available for transmon and multi_qubit projects');
 const studies=transmonStudies(model),matches=studies.filter(s=>s.id===draft?.study_id);
 if(matches.length!==1)throw Error('Choose one exact existing Palace capacitance study');
 const inventory=transmonInventory(matches[0]);if(!inventory.ok)throw Error(inventory.reason);
 const names=inventory.names;
 if(!names.includes(draft.island_a)||!names.includes(draft.island_b)||draft.island_a===draft.island_b)
  throw Error('Choose two distinct island component IDs from this study');
 const rest=names.filter(id=>id!==draft.island_a&&id!==draft.island_b);
 const fixed=[],floating=[];
 for(const id of rest){
  if(!Object.hasOwn(draft.policy,id)||!['fixed_zero','floating_zero_charge'].includes(draft.policy[id]))
   throw Error('Classify every other conductor exactly once as fixed_zero or floating_zero_charge');
  (draft.policy[id]==='fixed_zero'?fixed:floating).push(id);
 }
 if(Object.keys(draft.policy).some(id=>!rest.includes(id)))throw Error('Unknown or duplicated island/policy conductors: reset the mapping');
 if(!TRANSMON_CONFIGS.includes(draft.configuration))throw Error('Choose an explicit charge-transfer convention');
 if(draft.junctionAccepted!==true)throw Error('Acknowledge the matrix-only, unestablished junction-shunt assumption');
 return {schema:TRANSMON_SCHEMA,study_id:draft.study_id,island_a:draft.island_a,island_b:draft.island_b,
  other_terminal_policy:{fixed_zero:fixed,floating_zero_charge:floating},configuration:draft.configuration,
  junction_capacitance_assumption:TRANSMON_JUNCTION};
}
function transmonSelectionEditor(){
 const model=activeModel();if(!transmonFamily(model))return '';
 const studies=transmonStudies(model),draft=ensureTransmonDraft();
 const selected=studies.filter(s=>s.id===draft.study_id),inv=selected.length===1?transmonInventory(selected[0]):{ok:false,reason:'Select a Palace capacitance study; no default is inferred.'};
 let status='BLOCKED',reason='';
 try{validatedTransmonSelection(model,draft);status='READY_TO_SAVE'}catch(e){reason=e.message}
 if(draft.savedInvalid){status='BLOCKED_INVALID_SAVED_SELECTION';reason='Saved mapping fails exact schema or exhaustive conductor validation; reset the form and explicitly remap.'}
 if(transmonConflict){status='BLOCKED_CONFLICT';reason='Revision conflict. Reload the authoritative project before mapping again.'}
 if(dirty){status='BLOCKED_UNSAVED_CHANGES';reason='Save or discard other design changes before committing this selection to avoid an implicit combined revision.'}
 if(transmonSavePending){status='SAVING';reason='Committing an authenticated revision and reading it back.'}
 const opts=(id,items,value)=>`<select id="${id}"><option value="">Choose explicitly…</option>${items.map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(v)}</option>`).join('')}</select>`;
 const islands=inv.ok?inv.names:[];
 const remaining=inv.ok?inv.names.filter(x=>x!==draft.island_a&&x!==draft.island_b):[];
 const policyRows=remaining.map((id,i)=>`<tr><th scope="row"><code>${esc(id)}</code></th><td><select data-transmon-terminal="${i}" aria-label="Policy for ${esc(id)}"><option value="">Classify explicitly…</option><option value="fixed_zero" ${draft.policy[id]==='fixed_zero'?'selected':''}>fixed_zero (potential 0)</option><option value="floating_zero_charge" ${draft.policy[id]==='floating_zero_charge'?'selected':''}>floating_zero_charge (net charge 0)</option></select></td></tr>`).join('');
 const saved=model.intent?.transmon_capacitance_selection;
 return pane('Transmon capacitance · saved terminal selection','For transmon / multi-qubit designs only. Select exact study-port component IDs before a new revision is committed.',`
 <div class="callout warn">M1 is a NUMERICAL_SCREEN_ONLY, not a physically qualified transmon. The reference ground is external to the terminal matrix; it is never a floating conductor. No E_J, automatic E_C → scqubits transfer, Hamiltonian update, physical approval or fabrication authorization. Fabrication HOLD.</div>
 <div class="transmon-grid"><label class="form-field"><span>Native Palace capacitance study ID</span>${opts('transmonStudy',studies.map(s=>s.id),draft.study_id)}</label>
 <div class="transmon-source">Saved revision <code>${esc(project.head.slice(0,12))}</code><br>Current saved mapping: <strong>${saved?'Present (verify against ports)':'BLOCKED_NO_SAVED_SELECTION'}</strong><br>Source: <code>studies[].inputs.em.ports[].component</code>, not numerical matrix order.</div></div>
 ${!studies.length?'<div class="callout warn">BLOCKED: create and save a Palace study with kind=capacitance and at least two reviewed conductor ports in EM analysis.</div>':''}
 ${!inv.ok?`<div class="callout warn">BLOCKED: ${esc(inv.reason)}</div>`:`
 <p class="helper">Exact conductor component IDs in the selected study (${inv.names.length}), with physical tags from its saved input:</p>
 <div class="transmon-terminals">${selected[0].inputs.em.ports.map(p=>`<div><code>${esc(transmonPortLabel(p))}</code><small>${p.qgeometry?' CAD: '+esc(p.component)+'.'+esc(p.qgeometry)+' ·':''} Physical tags: ${esc(p.native_attributes.join(', '))}</small></div>`).join('')}</div>
 <div class="row"><label class="form-field"><span>Island A · component ID</span>${opts('transmonIslandA',islands,draft.island_a)}</label><label class="form-field"><span>Island B · distinct component ID</span>${opts('transmonIslandB',islands,draft.island_b)}</label></div>
 <h3>Remaining modeled conductors · exhaustive partition</h3>
 <p class="helper">Every remaining conductor must be assigned exactly one boundary condition. No other conductor is automatically grounded or floated.</p>
 ${remaining.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Component ID</th><th>Explicit treatment</th></tr></thead><tbody>${policyRows}</tbody></table></div>`:'<p class="helper">No remaining terminals after both islands are selected, or the island pair is incomplete.</p>'}
 <label class="form-field"><span>Charge convention</span>${opts('transmonConfiguration',TRANSMON_CONFIGS,draft.configuration)}</label>
 <p class="helper">TWO_ISLAND_CHARGE_TRANSFER transfers charge between A/B. GROUNDED_SINGLE_ISLAND holds B at zero; it does not float B.</p>
 <label class="review-check"><input type="checkbox" id="transmonJunctionConfirm" ${draft.junctionAccepted?'checked':''}><span>I explicitly assume <code>${TRANSMON_JUNCTION}</code>. Junction shunt capacitance is not established by this matrix; no silent zero shunt or inferred E_J.</span></label>`}
 <div id="transmonState" class="callout ${status==='READY_TO_SAVE'?'':'warn'}" role="status" aria-live="polite"><strong>${esc(status)}</strong>${reason?` · ${esc(reason)}`:''}</div>
 ${transmonSaveMessage?`<p class="helper" id="transmonSaveMessage" role="alert">${esc(transmonSaveMessage)}</p>`:''}
 <div class="button-stack"><button type="button" class="primary" id="commitTransmonSelection" ${status==='READY_TO_SAVE'?'':'disabled'}>Save transmon selection · new revision</button><button type="button" class="secondary" id="resetTransmonSelection" ${transmonSavePending?'disabled':''}>Reset form (no commit)</button>${saved?'<button type="button" class="secondary" id="clearSavedTransmonSelection" '+(transmonSavePending?'disabled':'')+'>Clear saved selection in design draft</button>':''}${transmonConflict?'<button type="button" class="secondary" id="reloadTransmonRevision">Reload current project</button>':''}</div>
 <p class="helper">Only the selection field in <code>model.intent</code> is replaced. Other targets, studies and independent quantum inputs are preserved; historic native runs stay bound to their original revisions. The server checks expected_revision and CSRF.</p>`);
}
function wireTransmonSelection(){
 if(!$('transmonStudy'))return;
 const change=(id,fn)=>{if($(id))$(id).onchange=e=>{fn(e.target);transmonSaveMessage='';render()}};
 change('transmonStudy',e=>{transmonDraft=newTransmonDraft();transmonDraft.study_id=e.value});
 change('transmonIslandA',e=>{transmonDraft.island_a=e.value;transmonDraft.policy=Object.create(null)});
 change('transmonIslandB',e=>{transmonDraft.island_b=e.value;transmonDraft.policy=Object.create(null)});
 change('transmonConfiguration',e=>{transmonDraft.configuration=e.value});
 change('transmonJunctionConfirm',e=>{transmonDraft.junctionAccepted=e.checked});
 const inv=transmonInventory(transmonStudies(activeModel()).find(s=>s.id===transmonDraft.study_id));
 const remaining=inv.ok?inv.names.filter(x=>x!==transmonDraft.island_a&&x!==transmonDraft.island_b):[];
 document.querySelectorAll('[data-transmon-terminal]').forEach(e=>e.onchange=()=>{
  const id=remaining[Number(e.dataset.transmonTerminal)];if(id===undefined)return;
  if(e.value==='fixed_zero'||e.value==='floating_zero_charge')transmonDraft.policy[id]=e.value;
  else delete transmonDraft.policy[id];transmonSaveMessage='';render();
 });
 $('resetTransmonSelection').onclick=()=>{transmonDraft=newTransmonDraft();transmonSaveMessage='';render()};
 if($('clearSavedTransmonSelection'))$('clearSavedTransmonSelection').onclick=()=>{
  delete activeModel().intent.transmon_capacitance_selection;transmonDraft=newTransmonDraft();markDirty();render();
  toast('Saved mapping removed from local design draft; save the revision to persist the removal.');
 };
 if($('reloadTransmonRevision'))$('reloadTransmonRevision').onclick=()=>loadProject(project.id).catch(e=>toast(e.message,true));
 $('commitTransmonSelection').onclick=commitTransmonSelection;
}
function sameTransmonSelection(a,b){
 if(!a||typeof a!=='object'||Object.keys(a).length!==7)return false;
 const expected=['schema','study_id','island_a','island_b','other_terminal_policy','configuration','junction_capacitance_assumption'];
 if(expected.some(k=>!Object.hasOwn(a,k)||!Object.hasOwn(b,k)))return false;
 if(expected.filter(k=>k!=='other_terminal_policy').some(k=>a[k]!==b[k]))return false;
 return a.other_terminal_policy&&typeof a.other_terminal_policy==='object'&&
  Object.keys(a.other_terminal_policy).length===2&&
  ['fixed_zero','floating_zero_charge'].every(k=>Array.isArray(a.other_terminal_policy[k])&&
    JSON.stringify(a.other_terminal_policy[k])===JSON.stringify(b.other_terminal_policy[k]));
}
async function commitTransmonSelection(){
 if(transmonSavePending||transmonConflict||dirty||!project)return false;
 if(ensureTransmonDraft().savedInvalid){transmonSaveMessage='Reset and explicitly rebuild the invalid saved selection first';render();return false}
 const pid=project.id,expected=project.head;
 let selection;
 try{selection=validatedTransmonSelection(activeModel(),ensureTransmonDraft())}
 catch(e){transmonSaveMessage=e.message;render();return false}
 // Copy precisely the currently read revision; do not mutate global draft intent,
 // studies, targets, scqubits inputs, or the old immutable revision.
 const next=JSON.parse(JSON.stringify(activeModel()));
 next.intent={...next.intent,transmon_capacitance_selection:selection};
 transmonSavePending=true;transmonSaveMessage='';render();
 try{
  const receipt=await api(`/api/projects/${pid}/commit`,'POST',{expected_revision:expected,model:next});
  if(!receipt||typeof receipt.revision!=='string'||!receipt.revision)throw Error('Commit receipt is missing; reload before another attempt');
  if(project?.id!==pid)return false;
  const loaded=await loadProject(pid);
  if(!loaded||project.head!==receipt.revision||!sameTransmonSelection(project.model.intent?.transmon_capacitance_selection,selection))
   throw Error('Saved revision readback did not match selection; reload authoritative project');
  toast('Transmon selection saved in revision '+receipt.revision.slice(0,8)+'; old native results remain historical');
  return true;
 }catch(e){
  if(project?.id===pid){transmonSaveMessage=e.message+'; inspect the current revision before retrying.';transmonConflict=e.status===409;toast(transmonSaveMessage,true)}
  return false;
 }finally{transmonSavePending=false;if(project?.id===pid&&step===3)render()}
}
function transmonResultsContext(){
 const model=activeModel(),selection=model?.intent?.transmon_capacitance_selection;
 if(!transmonFamily(model)||!selection)return '';
 const current=runs.filter(r=>r.revision_id===project.head),historical=runs.filter(r=>r.revision_id!==project.head);
 return pane('Transmon revision lineage','A saved selection never changes previously completed native evidence.',`
 <p>Current revision <code>${esc(project.head.slice(0,12))}</code> · saved study <code>${esc(selection.study_id)}</code> · ${runHistoryError?'job history unavailable':current.length+' current-revision job(s), '+historical.length+' historical job(s)'}.</p>
 <div class="callout warn">Previously completed jobs are still inspected against their own immutable run revisions; old runs without a saved selection stay BLOCKED_NO_SAVED_SELECTION. A new native Palace job is an explicit separate action, never triggered by this editor. M1 remains NUMERICAL_SCREEN_ONLY; fabrication HOLD.</div>`);
}
