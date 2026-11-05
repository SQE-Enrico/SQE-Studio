async function inspectResult(id){
 const job=runs.find(x=>x.id===id);
 if(runHistoryError)return toast('Job history unavailable; refresh before inspecting native evidence',true);
 if(!job)return toast('Unknown job',true);
 if(job.unsafe_location)return toast('Unsafe native run path; inspection blocked',true);
 const pid=project.id,originStep=step,requestToken=++resultRequestToken;
 if(job.state!=='completed'){
  openDialog('Job status · '+job.state,`<div class="callout warn">${esc(job.engine)} / ${esc(job.study_id)}: ${esc(job.state)}. No native result manifest is available. ${['failed','timed_out'].includes(job.state)?'Download the run ZIP for FAILURE.json and engine.log evidence.':'The job has not produced a result.'}</div><p class="helper">Source revision ${esc(job.revision_id)}. No scientific outputs are inferred from failure.</p><button class="secondary" id="downloadFailure" ${['queued','running'].includes(job.state)?'disabled':''}>Download diagnostic ZIP</button>`);
  $('downloadFailure').onclick=()=>window.location.assign(`/api/projects/${pid}/runs/${encodeURIComponent(id)}/download`);
  return;
 }
 selectedResult=null;
 if($('resultView'))$('resultView').textContent='Verifying native file hashes and revision on the server…';
 try{
  let html;
  if(job.is_sweep){
   const sweep=await api(`/api/projects/${pid}/runs/${id}/sweep`);
   if(sweep.revision_id!==job.revision_id||sweep.engine!==job.engine||sweep.study_id!==job.study_id)throw Error('Native sweep provenance does not match job');
   html=sweepView(sweep);
  }else{
   let r;
   try{r=await api(`/api/projects/${pid}/runs/${id}/result`)}
   catch(error){
    // A completed sweep may have been listed before its sweep marker was visible.
    // Only a genuine, schema-checked sweep endpoint can supply a replacement.
    if(error.status!==404)throw error;
    const sweep=await api(`/api/projects/${pid}/runs/${id}/sweep`);
    if(sweep.revision_id!==job.revision_id||sweep.engine!==job.engine||sweep.study_id!==job.study_id)throw Error('Native sweep provenance does not match job');
    html=sweepView(sweep);
   }
   if(r){
    const m=r.manifest;
    if(m.revision_id!==job.revision_id||m.engine!==job.engine||m.study_id!==job.study_id||m.schema!=='sqe.artifact.v1')throw Error('Result manifest provenance does not match the requested run');
    let view=`<div class="kicker">Native engine artifact · not independently qualified</div><div class="row align between"><h2>${esc(m.engine)}</h2><span class="pill">${esc(m.scientific_status)}</span></div>`;
    view+=scientificReview(m,job,r);
    view+=nativeCADLineageView(m,job);
    view+=`<details class="config-details"><summary>Run provenance and verified native artifact inventory</summary><dl class="provenance-list"><dt>Artifact type</dt><dd>${esc(m.artifact_type)}</dd><dt>Revision ID</dt><dd>${esc(m.revision_id)}</dd><dt>Project SHA-256</dt><dd>${esc(m.project_digest)}</dd><dt>Engine version</dt><dd>${esc(m.engine_version)}</dd><dt>Fabrication status</dt><dd>${esc(m.fabrication_status)}</dd></dl><h3>Native file checksums</h3><ul class="artifact-list">${(m.artifacts||[]).map(a=>`<li><code>${esc(a.name)}</code> · SHA-256 <code>${esc(a.sha256)}</code> · ${esc(a.bytes)} bytes</li>`).join('')}</ul></details>`;
    if(r.scientific_references)view+=scientificReferenceView(r.scientific_references);
    if(r.conditional_extraction)view+=conditionalExtractionView(r.conditional_extraction);
    if(r.spectrum)view+=nativeSpectrum(r.spectrum)+basisConvergenceView(r.spectrum);
    if(r.eigenmodes)view+=palaceModeTable(r.eigenmodes);
    if(r.em_evidence)view+=nativeEMEvidenceView(r.em_evidence);
    if(r.field_lineage)view+=nativeFieldLineageView(r.field_lineage);
    if(r.field_lineage && m.artifact_type==='palace.eigenmodes')view+=`<section class="pane"><h3>Upstream field outputs · experimental</h3><p class="helper">Inspect this saved Palace result with PyVista/VTK, the reader family used by SQDMetal. The table distinguishes electric-field declarations, auxiliary mesh data and unresolved outputs. It may take up to 25 seconds. Field values and coordinates remain local. Presence of fields does not establish mode identity, convergence or EPR.</p><button id="upstreamFieldProbe" class="secondary" type="button">Inspect field outputs with VTK/PyVista</button><div id="upstreamFieldProbeResult" role="status" aria-live="polite"></div></section>`;
    if(r.capacitance_evidence)view+=nativeCapacitanceView(r.capacitance_evidence);
    if(r.transmon_capacitance_screen)view+=transmonCapacitanceView(r.transmon_capacitance_screen);
    view+=conditionalExtractionLauncher(job,r.transmon_capacitance_screen);
    if(r.capacitance_review_dossier)view+=capacitanceReviewDossierView(r.capacitance_review_dossier);
    if(r.b04_case_readiness)view+=b04CaseReadinessView(r.b04_case_readiness);
    if(r.b04_case_readiness_status)view+=`<div class="callout warn">B04 case readiness: ${esc(r.b04_case_readiness_status)} · no scientific approval.</div>`;
    if(r.capacitance_review_dossier_status)view+=`<div class="callout warn">Independent capacitance review dossier: ${esc(r.capacitance_review_dossier_status)}. Historical results remain available; no physical approval is inferred.</div>`;
    if(r.rf_evidence)view+=nativeRFResultsView(r.rf_evidence);
    // Server evaluates only goals saved with this run's own revision, including historical runs.
    view+=goalComparison(r,job);
    view+='<div class="callout warn">Independent convergence, mode identity and physical/foundry signoff are not established by verified file integrity.</div>';
    html=pane('Native result inspection · scientific review','Native bytes are verified by the authenticated Results API; evidence stays bound to its saved revision.',view);
   }
  }
  if(!project||project.id!==pid||step!==originStep||requestToken!==resultRequestToken||
     runHistoryError||!runs.some(x=>sameSafeRun(x,job)))return;
  showResultEvidence(id,html,job);
  bindConditionalExtraction(job);
  if($('upstreamFieldProbe'))$('upstreamFieldProbe').onclick=async()=>{
   const button=$('upstreamFieldProbe'),target=$('upstreamFieldProbeResult');
   if(!button||!target)return;
   button.disabled=true;target.textContent='Running SHA-bound upstream reader (no field values exported)…';
   try{
    const result=await api(`/api/projects/${pid}/runs/${encodeURIComponent(id)}/upstream-field-probe`,
      'POST',{experimental_diagnostic:true});
    if(!selectedResult||selectedResult.projectId!==pid||selectedResult.id!==id||!target.isConnected)return;
    const diag=result.diagnostic;
    if(result.fabrication!=='HOLD'||result.scientific_approval!=='NOT_ESTABLISHED')throw Error('Unrecognized field-probe response');
    target.innerHTML=upstreamFieldDiagnosticView(diag);
   }catch(error){if(target.isConnected)target.textContent='Diagnostic unavailable: '+error.message+' · scientific status remains BLOCKED.';}
   finally{if(button.isConnected)button.disabled=false;}
  };
 }catch(err){
  if(project?.id===pid&&step===originStep&&requestToken===resultRequestToken&&$('resultView'))$('resultView').innerHTML=`<div class="callout warn" role="alert">Native evidence unavailable: ${esc(err.message)}. No scientific result has been displayed.</div>`;
  toast(err.message,true);
 }
}
function upstreamFieldDiagnosticView(diag){
 const legacy=diag?.schema==='sqe.m16.upstream-vtk-declarations.experimental.v1';
 if((!legacy&&diag?.schema!=='sqe.upstream-vtk-cycles.experimental.v2')||
    diag.physical_mode_identity!=='NOT_ESTABLISHED'||diag.mesh_convergence!=='NOT_ESTABLISHED'||diag.field_values_in_report!==false||
    !['BLOCKED','UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED','UPSTREAM_COMPLEX_E_NOT_ESTABLISHED'].includes(diag.status))throw Error('Unrecognized field-probe response');
 const labels={COMPLEX_E_FIELD:'Complex E field declarations',AUXILIARY_MESH_DATA:'Auxiliary mesh data (Rank / Indicator)',
   INCOMPLETE_OR_UNSUPPORTED_FIELD:'Incomplete or unsupported field',UNCLASSIFIED:'Unclassified output'};
 const rows=diag.cycles??[];
 if(!Array.isArray(rows)||rows.length>12)throw Error('Invalid output cycles');
 let body='';
 for(const [index,cycle] of rows.entries()){
  if(cycle?.cycle_index_not_mode_identity!==index||!Number.isInteger(cycle.mpi_piece_count)||cycle.mpi_piece_count<1||cycle.mpi_piece_count>16||
     (!legacy&&!Object.hasOwn(labels,cycle.role))||!Array.isArray(cycle.blocks)||cycle.blocks.length>64)throw Error('Invalid output classification');
  const declarations=cycle.blocks.map(block=>`Point [${esc(block?.point?.E_real)}, ${esc(block?.point?.E_imag)}]; Cell [${esc(block?.cell?.E_real)}, ${esc(block?.cell?.E_imag)}]`).join('<br>');
  const auxiliary=legacy?'not recorded':cycle.blocks.map(block=>['point','cell'].map(assoc=>
    ['Rank','Indicator'].filter(key=>block?.[assoc]?.[key]==='NUMERIC_SCALAR').map(key=>`${key} (${assoc})`).join(', ')).filter(Boolean).join('; ')).filter(Boolean).join('; ');
  body+=`<tr><td>${index+1}</td><td>${cycle.mpi_piece_count}</td><td>${legacy?'Legacy observation; role unclassified':labels[cycle.role]}</td><td>${declarations}</td><td>${auxiliary||'none observed'}</td></tr>`;
 }
 return `<div class="callout warn"><strong>Experimental declarations only</strong><p>Series: ${esc(diag.status)} · Reader: ${esc(diag.backend??'unavailable')} ${esc(diag.backend_version??'')} · ${esc(diag.reason_code??'')}</p></div>`+
  (rows.length?`<table><thead><tr><th>Output cycle (not a mode)</th><th>MPI pieces</th><th>Output role</th><th>E_real / E_imag</th><th>Auxiliary declarations</th></tr></thead><tbody>${body}</tbody></table>`:'')+
  '<p>Field values, physical mode identity, mesh convergence and EPR remain unvalidated. Fabrication HOLD.</p>';
}
