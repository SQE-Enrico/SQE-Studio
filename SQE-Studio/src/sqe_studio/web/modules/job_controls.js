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
async function refreshRuns(){
 if(!project||step!==5)return;
 const pid=project.id,requestToken=++runHistoryRequestToken;
 clearTimeout(refreshTimer);refreshTimer=null;
 try{
  const next=(await api(`/api/projects/${pid}/runs`)).runs;
  // Out-of-order HTTP completion must not overwrite newer job states or clear
  // the disconnected-history warning from a more recent failed request.
  if(requestToken!==runHistoryRequestToken||!project||project.id!==pid||step!==5)return;
  const previousError=runHistoryError;runHistoryError='';
  const changed=JSON.stringify(next)!==JSON.stringify(runs);
  runs=next;
  if(changed||previousError)invalidateComparison();
  if(selectedResult&&!runs.some(r=>sameSafeRun(r,selectedResult.job))){
   selectedResult=null;resultRequestToken++;if($('resultView'))$('resultView').textContent='Selected job provenance changed; inspect and re-verify the current safe run.';
  }else if(changed&&!selectedResult){
   // An inspection still loading from the old history must be retried.
   resultRequestToken++;if($('resultView'))$('resultView').textContent='Job history changed. Inspect a completed safe run to re-verify evidence.';
  }
  if(changed||previousError){
   if($('runMetrics'))$('runMetrics').innerHTML=runCountsView();
   if($('runList'))$('runList').innerHTML=runRows(filteredRuns());
   wireRunControls();
   // Even if completed counts match, replacement IDs/revisions need fresh selectors.
   if($('compareSection')){
    $('compareSection').innerHTML=compareControls();
    if($('compareRuns'))wireCompareControls();
   }
  }
  if(runs.some(x=>x.state==='running'||x.state==='queued'))refreshTimer=setTimeout(refreshRuns,1700);
 }catch(err){
  if(requestToken!==runHistoryRequestToken||project?.id!==pid||step!==5)return;
  if(project?.id===pid&&step===5){
   runHistoryError='Job history unavailable ('+err.message+'). Retry Refresh job states; no native evidence is implied.';
   // An unavailable history cannot authorize an old inspection or in-flight GET.
   selectedResult=null;resultRequestToken++;
   if($('resultView'))$('resultView').textContent='Native evidence hidden: job history unavailable. Refresh job states before re-inspection.';
   invalidateComparison();
   if($('runMetrics'))$('runMetrics').innerHTML=runCountsView();
   if($('runList'))$('runList').innerHTML=runRows([]);
   if($('compareSection'))$('compareSection').innerHTML=compareControls();
  }
  toast(err.message,true);
 }
}
function scientificReferenceView(data){
 if(data?.schema!=='sqe.scientific-reference-diagnostics.m8.v1'||!Array.isArray(data.evaluations)||data.fabrication!=='HOLD')
  return '<div class="callout warn">Scientific references unavailable or unverified.</div>';
 const applicable=data.evaluations.filter(r=>r.status!=='NOT_APPLICABLE');
 let html='<p class="helper">Literature-informed numerical diagnostics on these hash-verified native results. NUMERICAL_PASS is not physical validation.</p>';
 html+='<div class="table-wrap"><table class="data-table"><thead><tr><th>Case</th><th>Diagnostic status</th><th>Measured vs reference / tolerance</th></tr></thead><tbody>';
 for(const r of applicable){
  const details=(r.checks||[]).map(c=>`${esc(c.quantity)}: ${esc(c.actual)} vs ${esc(c.reference)} ${esc(c.unit)} · relative error ${esc((100*c.relative_error).toFixed(3))}% / tolerance ${esc((100*c.relative_tolerance).toFixed(2))}%`).join(' · ')||esc(r.reason);
  html+=`<tr><td>${esc(r.case_id)}</td><td>${esc(r.status)}<br><small>Basis: ${esc(r.basis_convergence)}</small></td><td>${details}</td></tr>`;
 }
 html+='</tbody></table></div><div class="callout warn">CPW literature measurements require equivalent geometry and verified mode identity. JPA/EPR bridges remain blocked. No fabrication or Hamiltonian transfer approval.</div>';
 return pane('Scientific reference diagnostics','Generic read-only checks integrated with the ordinary Results workflow.',html);
}
function showResultEvidence(id,html,job){
 selectedResult={projectId:project.id,id,job:{...job},html};
 if($('resultView')){
  $('resultView').innerHTML=html;
  $('resultView').focus({preventScroll:true});
 }else openDialog('Native result evidence',html);
}
// Bounded, strictly escaped, read-only review checklist from authenticated Store evidence.
// Its presence is NOT approval, solver re-execution or EC-to-scqubits authorization.
function capacitanceReviewDossierView(d){
 if(d?.schema!=='sqe.capacitance-review-dossier.v1'||d.scientific_status!=='BLOCKED'||d.fabrication!=='HOLD'||d.review?.status!=='NOT_APPROVED'||!Array.isArray(d.review.checklist))
  return '<div class="callout warn">Unrecognized capacitance review dossier; physical review remains blocked.</div>';
 const terminals=Array.isArray(d.terminals)?d.terminals:[];
 const checks=d.review.checklist.slice(0,20);
 return `<section class="pane"><h3>Palace capacitance · independent review dossier</h3>`+
  `<div class="callout warn">NOT APPROVED · ${esc(d.b04_native_review)} · EM→scqubits ${esc(d.em_to_scqubits_transfer)} · fabrication HOLD. This is a file/provenance checklist, not a verified physical mapping.</div>`+
  `<p class="helper">Revision ${esc(d.source?.revision_id)} · native evidence ${esc(d.source?.manifest_sha256)} · matrix ${esc(d.capacitance?.terminal_count)} terminals (${esc(d.capacitance?.matrix_entry_unit)}).</p>`+
  `<div class="table-wrap"><table class="data-table"><thead><tr><th>Terminal</th><th>Role (proposed)</th><th>Native physical groups</th></tr></thead><tbody>${terminals.map(p=>`<tr><td>${esc(p.terminal_index)} · ${esc(p.component)}</td><td>${esc(p.proposed_role)}</td><td>${esc((p.native_group_ids||[]).join(', '))}</td></tr>`).join('')}</tbody></table></div>`+
  `<details class="config-details"><summary>Ten outstanding independent-review gates (${esc(checks.length)})</summary><ol>${checks.map(c=>`<li><strong>${esc(c.id)}</strong>: ${esc(c.required_evidence)} · ${esc(c.status)}</li>`).join('')}</ol></details></section>`;
}
