function freshIndependentTransmonDraft(){
 return {projectId:project?.id||'',revision:project?.head||'',
  EJ:'',EC:'',ng:'',ncut:'',levels:'',acknowledged:false,
  preview:null,message:'',stale:false,saving:false};
}
function ensureIndependentTransmonDraft(){
 if(!manualTransmonDraft)manualTransmonDraft=freshIndependentTransmonDraft();
 return manualTransmonDraft;
}
function independentTransmonStale(d){
 return !project||d.projectId!==project.id||d.revision!==project.head||d.stale;
}
// Only local syntax/range feedback. A12 remains authoritative and has no
// authenticated preflight/save API in this dispatch.
function parseIndependentTransmonScalar(raw,name,integer=false){
 if(typeof raw!=='string')throw Error(name+': expected manually typed text');
 const value=raw.trim();
 const syntax=integer?/^[+-]?\d+$/:/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
 if(!value||value.length>48||!syntax.test(value))throw Error(name+': enter an explicit '+(integer?'integer':'finite decimal')+' value');
 const n=Number(value);
 if(!Number.isFinite(n)||(integer&&!Number.isSafeInteger(n)))throw Error(name+': value must be finite'+(integer?' and an integer':''));
 return n;
}
function validateIndependentTransmonLocal(d){
 if(!d||!d.acknowledged)throw Error('Confirm explicitly that values were entered independently and remain unverified');
 const EJ=parseIndependentTransmonScalar(d.EJ,'EJ'),EC=parseIndependentTransmonScalar(d.EC,'EC');
 const ng=parseIndependentTransmonScalar(d.ng,'ng');
 const ncut=parseIndependentTransmonScalar(d.ncut,'ncut',true);
 const levels=parseIndependentTransmonScalar(d.levels,'levels',true);
 if(!(EJ>0&&EJ<=1000&&EC>0&&EC<=1000))throw Error('EJ and EC must be > 0 and <= 1000 GHz (E/h)');
 if(ng< -10||ng>10)throw Error('ng must be in [-10, 10] (2e)');
 if(ncut<3||ncut>80)throw Error('ncut must be an integer in [3, 80]');
 if(levels<2||levels>12)throw Error('levels must be an integer in [2, 12]');
 if(Math.max(6,levels)>2*ncut+1)throw Error('levels exceed the available Transmon charge basis');
 // Allowlist typed copies; no EM/study/provenance/revision objects enter here.
 return {EJ,EC,ng,ncut,levels};
}
function b04CaseReadinessView(d){
 if(!d||d.schema!=='sqe.native-capacitance-case-readiness.v1'||d.decision!=='BLOCKED'||d.ec_to_scqubits!=='BLOCKED'||d.fabrication!=='HOLD')return '<div class="callout warn">B04 readiness record invalid · no physics approval.</div>';
 return `<section class="scientific-review" aria-label="Native B04 electrostatic case readiness"><h3>B04 · Palace electrostatic case readiness (not qualification)</h3>
 <p class="helper">Current saved revision ${esc(d.source?.revision_id)} · ${esc(d.capacitance?.terminal_count)} terminal(s) · native matrix unit ${esc(d.capacitance?.normalized_unit)} · software screen only.</p>
 <div class="callout warn">Native execution: ${esc(d.native_execution)}. Physical decision: ${esc(d.decision)}. E_C→scqubits: ${esc(d.ec_to_scqubits)}. Fabrication: HOLD. Hash matching is not independent scientific review.</div>
 <h4>Independent evidence still needed</h4><ul class="artifact-list">${(d.missing_physical_evidence||[]).map(g=>`<li>${esc(g.id)} · ${esc(g.required)}</li>`).join('')}</ul></section>`;
}
function independentTransmonEditor(){
 if(!project)return '';
 const d=ensureIndependentTransmonDraft(),stale=independentTransmonStale(d);
 const inputs=[
  ['EJ','EJ · GHz (E/h)','decimal','0 < EJ <= 1000 GHz'],
  ['EC','EC · GHz (E/h)','decimal','0 < EC <= 1000 GHz'],
  ['ng','ng · 2e','decimal','-10 <= ng <= 10'],
  ['ncut','ncut · 1 (integer)','numeric','integer 3–80'],
  ['levels','levels · 1 (integer)','numeric','integer 2–12; basis constraint applies']
 ].map(([key,label,mode,help])=>`<label class="form-field" for="manualTransmon${key}"><span>${esc(label)}</span>
  <input id="manualTransmon${key}" data-manual-transmon="${key}" type="text" inputmode="${mode}" autocomplete="off" spellcheck="false" maxlength="48" value="${esc(d[key])}" aria-describedby="manualTransmonHelp${key}">
  <small id="manualTransmonHelp${key}">${esc(help)}</small></label>`).join('');
 const saved=(project.model?.studies||[]).filter(s=>/^independent_transmon_(0[1-9]|[12][0-9]|30)$/.test(s.id)&&s.engine==='scqubits'&&s.kind==='quantum_spectrum');
 const savedList=saved.length?`<div class="manual-transmon-saved"><h3>Saved independent studies · explicit native execution</h3><p class="helper">Each request is rechecked on the server against the current immutable revision and the private M4 manual-creation record. Existing studies created before M5 may lack the required record and will remain blocked. No EM data is transferred.</p>${saved.map(s=>`<div class="row align between"><code>${esc(s.id)}</code><button type="button" class="secondary" data-execute-manual="${esc(s.id)}" ${dirty||stale?'disabled aria-disabled="true"':''}>Run native scqubits · unreviewed</button></div>`).join('')}</div>`:'';
 const summary=d.preview&&!stale?`<div class="manual-transmon-summary" id="manualTransmonSummary">Local syntax only · unsaved: EJ ${esc(d.preview.EJ)} GHz, EC ${esc(d.preview.EC)} GHz (E/h); ng ${esc(d.preview.ng)} (2e); ncut ${esc(d.preview.ncut)}; levels ${esc(d.preview.levels)}. No server scientific preflight or spectrum.</div>`:'<div class="manual-transmon-summary" id="manualTransmonSummary"></div>';
 return `<section class="pane manual-transmon" aria-labelledby="manualTransmonTitle" aria-describedby="manualTransmonBoundary">
  <h2 id="manualTransmonTitle">Independent Transmon · manual designer declaration (unsaved)</h2>
  <p id="manualTransmonBoundary">Independent research entry only. Type values manually, without borrowing Palace, Results or extracted E_C. EJ and EC are E/h in GHz, not joules. A saved manual study is NOT physically reviewed or EM-derived and never runs automatically.</p>
  <div class="manual-transmon-fields">${inputs}</div>
  <label class="review-check manual-transmon-ack" for="manualTransmonAcknowledged"><input id="manualTransmonAcknowledged" type="checkbox" ${d.acknowledged?'checked':''}>
   <span>I declare that I manually entered EJ, EC, ng, ncut and levels independently of any Palace/Results EC extraction, and understand these numbers are unverified research inputs. My checkbox is a statement, <strong>not an attestation of their real provenance or physical authorization.</strong></span></label>
  <div class="button-stack"><button type="button" class="secondary" id="manualTransmonCheck" ${stale?'disabled aria-disabled="true"':''}>Check local syntax only</button>
   <button type="button" class="secondary" id="manualTransmonReset">Clear manual form</button>
   <button type="button" class="primary" ${(!d.preview||stale||d.saving||!d.acknowledged||dirty)?'disabled aria-disabled="true"':''} id="manualTransmonServerAction">Save independent research study (no run)</button></div>
  <p class="manual-transmon-status" id="manualTransmonGate" role="status" aria-live="polite">${MANUAL_TRANSMON_BLOCK}</p>
  <p id="manualTransmonCheckResult" role="status" aria-live="polite">${esc(stale?'STALE_REVISION: reload this project before checking inputs.':d.message)}</p>
  ${summary}${savedList}<div class="callout warn">A12 parameter syntax preflight and server revision checks cannot attest independent origin. A saved study is an unverified research declaration, not an EM→Hamiltonian transfer, a native solver result, a scientific approval, or fabrication permission. Fabrication: HOLD. Existing scqubits study editor is separate.</div>
 </section>`;
}
function independentTransmonFeedback(){
 const d=manualTransmonDraft;
 if(!d)return;
 const state=$('manualTransmonCheckResult'),summary=$('manualTransmonSummary');
 if(state)state.textContent=independentTransmonStale(d)?'STALE_REVISION: reload this project before checking inputs.':d.message;
 const action=$('manualTransmonServerAction');
 if(action){action.disabled=!!(!d.preview||independentTransmonStale(d)||d.saving||!d.acknowledged||dirty);action.setAttribute('aria-disabled',String(action.disabled));}
 if(summary)summary.textContent=d.preview&&!independentTransmonStale(d)?
  `Local syntax only · unsaved: EJ ${d.preview.EJ} GHz, EC ${d.preview.EC} GHz (E/h); ng ${d.preview.ng} (2e); ncut ${d.preview.ncut}; levels ${d.preview.levels}. No server scientific preflight or spectrum.`:'';
}
function wireIndependentTransmon(){
 const d=ensureIndependentTransmonDraft();
 document.querySelectorAll('[data-manual-transmon]').forEach(el=>el.oninput=()=>{
  d[el.dataset.manualTransmon]=el.value;d.preview=null;d.message='';++manualTransmonCheckToken;independentTransmonFeedback();
 });
 $('manualTransmonAcknowledged').onchange=e=>{d.acknowledged=e.target.checked;d.preview=null;d.message='';++manualTransmonCheckToken;independentTransmonFeedback()};
 $('manualTransmonReset').onclick=()=>{++manualTransmonCheckToken;manualTransmonDraft=freshIndependentTransmonDraft();render();};
 $('manualTransmonCheck').onclick=checkIndependentTransmonLocal;
 document.querySelectorAll('[data-execute-manual]').forEach(el=>el.onclick=()=>runIndependentTransmonSaved(el.dataset.executeManual));
}
async function checkIndependentTransmonLocal(){
 const d=ensureIndependentTransmonDraft(),token=++manualTransmonCheckToken;
 d.preview=null;d.message='';
 if(independentTransmonStale(d)){d.stale=true;d.message='STALE_REVISION: reload project before re-entering values';independentTransmonFeedback();return false;}
 if(dirty){d.message='BLOCKED_UNSAVED_PROJECT_CHANGES: save unrelated design changes first (this form is never saved)';independentTransmonFeedback();return false;}
 let values;
 try{values=validateIndependentTransmonLocal(d)}catch(e){d.message=e.message;independentTransmonFeedback();return false;}
 try{
  // Read-only authenticated HEAD comparison via the EXISTING project GET.
  // There is deliberately no POST and no A12 preflight endpoint guess.
  const latest=await api(`/api/projects/${encodeURIComponent(d.projectId)}`);
  if(token!==manualTransmonCheckToken||d!==manualTransmonDraft)return false;
  if(dirty){d.message='BLOCKED_UNSAVED_PROJECT_CHANGES: local project draft changed during revision check';independentTransmonFeedback();return false;}
  if(!latest||latest.id!==d.projectId||latest.head!==d.revision||
     !project||project.id!==d.projectId||project.head!==d.revision){
   d.stale=true;d.message='STALE_REVISION: project head changed; reload and re-enter manually';
   independentTransmonFeedback();return false;
  }
  d.preview=values;
  d.message='Local syntax checked against the current project head. Not A12 preflight; never saved or scientifically approved.';
  independentTransmonFeedback();return true;
 }catch(e){
  if(token!==manualTransmonCheckToken||d!==manualTransmonDraft)return false;
  d.message='BLOCKED_REVISION_CHECK_UNAVAILABLE: '+e.message;
  independentTransmonFeedback();return false;
 }
}
// Dedicated A99 endpoint. No EM output is read or copied here. The user must
// explicitly check a revision-bound manual draft and then request a new study.
async function saveIndependentTransmonResearch(){
 const d=ensureIndependentTransmonDraft();
 if(!d.preview||d.saving||independentTransmonStale(d)||dirty)return false;
 let values;
 try{values=validateIndependentTransmonLocal(d)}catch(e){d.message=e.message;independentTransmonFeedback();return false;}
 if(['EJ','EC','ng','ncut','levels'].some(k=>values[k]!==d.preview[k])){
  d.message='BLOCKED_CHANGED_MANUAL_VALUES: recheck the declaration';independentTransmonFeedback();return false;
 }
 const token=++manualTransmonCheckToken,originalId=d.projectId,originalHead=d.revision;
 d.saving=true;render();
 const declaration={schema:'sqe.independent-transmon-declaration.a12.v1',source:'independent',model:'Transmon',
  parameters:{EJ:values.EJ,EC:values.EC,ng:values.ng,ncut:values.ncut},
  parameter_units:{EJ:'GHz',EC:'GHz',ng:'2e',ncut:'1'},levels:values.levels};
 try{
  const saved=await api(`/api/projects/${encodeURIComponent(originalId)}/independent-transmon`,'POST',
   {expected_revision:originalHead,declaration,acknowledged:true});
  if(token!==manualTransmonCheckToken||d!==manualTransmonDraft||!project||project.id!==originalId)return false;
  if(saved.status!=='SAVED_UNVERIFIED_INDEPENDENT_RESEARCH_STUDY'||saved.em_ec_transfer!=='BLOCKED'||
     saved.fabrication!=='HOLD'||!saved.revision)throw Error('Unexpected server research acknowledgment');
  d.saving=false;manualTransmonDraft=null;++manualTransmonCheckToken;
  await loadProject(originalId);
  toast('Independent research study saved · '+saved.study_id+' · no solver run, physical review BLOCKED');
  return true;
 }catch(err){
  if(token!==manualTransmonCheckToken||d!==manualTransmonDraft)return false;
  d.saving=false;d.preview=null;d.message='Research save BLOCKED: '+err.message;
  if(/409|revision/i.test(err.message))d.stale=true;
  render();return false;
 }
}
// M5 explicitly invokes a saved independent study; the backend never
// accepts EJ/EC scalars here. This is an actual native job request, not an
// EM-to-Hamiltonian bridge or a physics approval.
async function runIndependentTransmonSaved(studyId){
 const pid=project?.id,revision=project?.head;
 try{
  if(!pid||!revision||dirty)throw Error('Save the project before requesting a native spectrum');
  if(!engineValidated('scqubits'))throw Error('Native scqubits environment is unavailable');
  if(!project.model.studies.some(s=>s.id===studyId&&s.engine==='scqubits'&&s.kind==='quantum_spectrum'))throw Error('Saved independent study is missing');
  const request={schema:'sqe.independent-transmon-execution-request.a12.v1',
    project_id:pid,expected_revision:revision,study_id:studyId};
  const preflight=await api(`/api/projects/${encodeURIComponent(pid)}/independent-transmon/preflight`,'POST',request);
  if(!project||project.id!==pid||project.head!==revision||dirty)throw Error('Project changed during native preflight');
  if(preflight.status!=='READY_FOR_SOFTWARE_EXECUTION_ONLY'||preflight.em_ec_transfer!=='BLOCKED'||preflight.fabrication!=='HOLD')throw Error('Scientific gate mismatch: manual run blocked');
  const queued=await api(`/api/projects/${encodeURIComponent(pid)}/independent-transmon/execute`,'POST',request);
  if(queued.scientific_authorization!=='BLOCKED'||queued.em_ec_transfer!=='BLOCKED'||queued.fabrication!=='HOLD'||!queued.run_id)throw Error('Unexpected native job acknowledgment');
  toast('Unreviewed independent scqubits job: '+queued.run_id.slice(0,8));
  step=5;await loadProject(pid);setTimeout(refreshRuns,1600);
 }catch(e){toast('Independent Transmon native run BLOCKED: '+e.message,true)}
}
