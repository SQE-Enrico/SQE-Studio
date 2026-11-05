/* These counts are JOB states, not verified outcomes or physical measurements. */
function runCountsView(){
 if(runHistoryError)return ['Completed jobs','Active native jobs','Failed / timed out'].map(label=>`<div class="metric"><strong>—</strong><span>${label} · unavailable</span></div>`).join('');
 const completed=runs.filter(r=>r.state==='completed').length;
 const active=runs.filter(r=>['queued','running'].includes(r.state)).length;
 const failed=runs.filter(r=>['failed','timed_out'].includes(r.state)).length;
 return `<div class="metric"><strong>${completed}</strong><span>Completed jobs · inspect to verify</span></div><div class="metric"><strong>${active}</strong><span>Active native jobs</span></div><div class="metric"><strong>${failed}</strong><span>Failed / timed out · diagnostics</span></div>`;
}
function resultsOverview(){
 return pane('Evidence review · scientific gates','A single Results workbench for all project families and native engines.',`
  <div id="runMetrics" class="metric-cards">${runCountsView()}</div>
  <div class="callout warn">A completed job is not a scientifically accepted result. Inspection re-verifies revision and artifact hashes on the server. Complex field overlap, mode identity, EM-to-Hamiltonian mapping, and foundry approval remain separate gates.</div>
  ${capabilityOverview()}`);
}
function filteredRuns(){return runs.filter(r=>runFilter==='all'||(runFilter==='current'&&r.revision_id===project?.head)||(runFilter==='attention'&&(r.unsafe_location||['failed','timed_out'].includes(r.state))))}
function runRows(items){
 if(runHistoryError)return `<div class="callout warn" role="alert">${esc(runHistoryError)}</div>`;
 if(!items.length)return empty(runs.length?'No jobs match this filter':'No native job history',runs.length?'Change the filter to inspect other revisions or job states.':'Apply a supported study, save the revision, then explicitly request native execution. No result is inferred.');
 return `<div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Engine / study</th><th scope="col">Revision</th><th scope="col">Job state</th><th scope="col">Evidence</th></tr></thead><tbody>${items.map(r=>{
  const done=!['queued','running'].includes(r.state),safe=!r.unsafe_location;
  const state=r.unsafe_location?'Unsafe run location · blocked':r.state==='completed'?'Completed · inspection required':r.state;
  return `<tr><td>${esc(r.engine)}<br><small>${esc(r.study_id)}${r.is_sweep?' · parameter sweep':''}</small></td><td title="${esc(r.revision_id)}">${esc(r.revision_id.slice(0,8))}${r.revision_id===project?.head?' · current':' · historical'}</td><td><span class="${r.state==='completed'&&!r.unsafe_location?'neutral-run':'danger'}">${esc(state)}</span></td><td><div class="button-stack"><button type="button" class="secondary mini" data-get-result="${esc(r.id)}" ${safe?'':'disabled'}>${r.state==='completed'?'Inspect verified source':'View status'}</button><button type="button" class="secondary mini" data-download="${esc(r.id)}" ${done&&safe?'':'disabled'} aria-label="Download archive for ${esc(r.engine)} ${esc(r.state)} job">ZIP ↓</button></div></td></tr>`}).join('')}</tbody></table></div>`;
}
function runsTable(withFilter=false){
 if(!withFilter)return runRows(runs);
 return `<div class="run-list-tools"><label for="runFilter">Show jobs</label><select id="runFilter"><option value="all" ${runFilter==='all'?'selected':''}>All revisions</option><option value="current" ${runFilter==='current'?'selected':''}>Current revision</option><option value="attention" ${runFilter==='attention'?'selected':''}>Failures / blocked</option></select><button type="button" class="secondary mini" id="refreshJobs">Refresh job states</button></div><div id="runList">${runRows(filteredRuns())}</div>`;
}
function wireRunControls(){
 document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>{if(!b.disabled)window.location.assign(`/api/projects/${project.id}/runs/${encodeURIComponent(b.dataset.download)}/download`)});
 document.querySelectorAll('[data-get-result]').forEach(b=>b.onclick=()=>inspectResult(b.dataset.getResult));
 if($('runFilter'))$('runFilter').onchange=e=>{runFilter=e.target.value;$('runList').innerHTML=runRows(filteredRuns());wireRunControls()};
 if($('refreshJobs'))$('refreshJobs').onclick=()=>refreshRuns();
}
// A comparison is a verified, read-only snapshot of TWO server-side artifacts.
// Never preserve a former response across project/revision/history changes.
function invalidateComparison(){
 ++comparisonRequestToken;
 if($('comparisonView'))$('comparisonView').replaceChildren();
}
// A completed state alone does not authorize retaining previously inspected evidence.
// Bind inspection to the exact server-listed run provenance, not just its run ID.
function sameSafeRun(now,previous){
 return !!(now&&previous&&now.id===previous.id&&now.state==='completed'&&!now.unsafe_location&&
  now.revision_id===previous.revision_id&&now.engine===previous.engine&&
  now.study_id===previous.study_id&&!!now.is_sweep===!!previous.is_sweep);
}
function comparisonRunEligible(id){
 return !runHistoryError&&runs.find(r=>r.id===id&&r.state==='completed'&&!r.is_sweep&&!r.unsafe_location);
}
function comparisonProvenanceValid(data,left,right,fine=null){
 const validSide=(side,job)=>side&&side.run_id===job.id&&side.revision_id===job.revision_id&&
  side.engine===job.engine&&side.study_id===job.study_id&&side.fabrication_status==='HOLD'&&
  /^[0-9a-f]{64}$/.test(side.project_sha256);
 return !!(data?.schema==='sqe.expert-comparison.v1'&&
  data.status==='read_only_expert_review_not_scientifically_qualified'&&
  validSide(data.left,left)&&validSide(data.right,right)&&
  (fine?validSide(data.fine,fine)&&data.mesh_refinement_series?.schema==='sqe.native-mesh-three-run.m10.v1':!data.fine)&&
  data.same_revision===(left.revision_id===right.revision_id)&&
  Array.isArray(data.caveats)&&data.numerical_comparison&&data.design_input_changes);
}
