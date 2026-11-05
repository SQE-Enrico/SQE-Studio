function conditionalExtractionStudies(){
 const studies=(activeModel()?.studies||[]).filter(s=>s.engine==='scqubits'&&s.kind==='extracted_transmon_research');
 if(!studies.length)return pane('Capacitance extraction → quantization','Conditional single-mode research workflow',
  '<p>Prepare a capacitance study and save its explicit conductor/ground selection before the Palace run. Open its completed Results to preview and quantize the extracted capacitance with declared junction assumptions.</p>');
 return pane('Saved conditional quantization studies','Derived parameters retain their source capacitance run',
  `<ul>${studies.map(s=>`<li><strong>${esc(s.id)}</strong> · source ${esc(s.inputs?.source?.run_id)} · ${esc(s.inputs?.assumptions?.josephson?.quantity)} declared, EC derived. Physical validation NOT_ESTABLISHED.</li>`).join('')}</ul><button class="secondary" id="viewExtractionRuns" type="button">Open quantization jobs and results</button><p class="helper">These source-bound studies are retained when editing independent Hamiltonian inputs above. Change the conditional assumptions through the source Results action.</p>`);
}
function conditionalExtractionValid(data){
 if(!data||data.schema!=='sqe.conditional-transmon-extraction.m19.v1'||
    data.status!=='CONDITIONAL_RESEARCH_MODEL_READY'||
    data.parameter_origin!=='EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS'||
    data.scientific_qualification!=='NOT_ESTABLISHED'||data.reviewed_A01_transfer!=='BLOCKED'||
    data.fabrication!=='HOLD')return false;
 const p=data.parameters,c=data.capacitances;
 return !!(p&&c&&[p.EJ,p.EC,data.EJ_over_EC,c.matrix_effective_F,c.additional_junction_F,c.total_F].every(v=>typeof v==='number'&&Number.isFinite(v))&&p.EJ>0&&p.EC>0&&c.matrix_effective_F>0&&c.additional_junction_F>=0&&c.total_F>0&&
  /^[a-f0-9]{32}$/.test(data.source?.run_id)&&/^[a-f0-9]{32}$/.test(data.source?.revision_id)&&
  /^[a-f0-9]{64}$/.test(data.extraction_sha256));
}
function conditionalExtractionView(data){
 if(!conditionalExtractionValid(data))return '<div class="callout warn">Conditional extraction unavailable: invalid provenance or model status.</div>';
 const p=data.parameters,c=data.capacitances;
 const rows=[['C matrix effective',c.matrix_effective_F*1e15,'fF'],['C junction additional',c.additional_junction_F*1e15,'fF'],['C total',c.total_F*1e15,'fF'],['EC / h',p.EC,'GHz'],['EJ / h',p.EJ,'GHz'],['EJ / EC',data.EJ_over_EC,'1']];
 const diag=data.spectrum_diagnostics;
 return pane('Extraction → conditional quantization','Native capacitance plus explicit junction assumptions',
  `<div class="callout warn">Conditional research model · physical validation NOT_ESTABLISHED · fabrication HOLD. ${data.source_result_metadata?.execution_kind==='SOFTWARE_FIXTURE'?'The EM source is a constructed software fixture; no Palace simulation or measured device.':''}</div>`+
  `<p>Source run <code>${esc(data.source?.run_id)}</code>, revision <code>${esc(data.source?.revision_id)}</code>. ${esc(data.source_result_metadata?.engine_version||'')}</p>`+
  `<div class="table-wrap"><table class="data-table"><thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead><tbody>${rows.map(([name,value,unit])=>`<tr><td>${esc(name)}</td><td>${esc(value.toPrecision(10))}</td><td>${esc(unit)}</td></tr>`).join('')}</tbody></table></div>`+
  `<p class="helper">C total = reduced Maxwell capacitance + additional C_J. EC/h = e²/(2hC total). E_J is declared separately, or converted from declared L_J; it is not inferred from PEC geometry. Other terminals keep the saved fixed/floating policy.</p>`+
  `<p>C_J: ${esc(data.assumptions?.junction_reference)}. Josephson: ${esc(data.assumptions?.josephson?.reference)}.</p>`+
  (diag?`<h3>Koch transmon asymptote · ${esc(diag.status)}</h3><p class="helper">Approximation f01 ≈ √(8EJ EC) − EC; α ≈ −EC. Applies for EJ/EC ≥ 40. This compares the computed Hamiltonian with a literature approximation; device agreement remains unestablished.</p><table class="data-table"><thead><tr><th>Quantity</th><th>Native · GHz</th><th>Approx. · GHz</th><th>Relative error</th></tr></thead><tbody>${(diag.checks||[]).map(row=>`<tr><td>${esc(row.quantity)}</td><td>${esc(row.actual)}</td><td>${esc(row.reference)}</td><td>${esc((row.relative_error*100).toFixed(3))}%</td></tr>`).join('')}</tbody></table>`:'')+
  `<details class="config-details"><summary>Unresolved model assumptions and source hashes</summary><ul>${(data.unresolved||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><pre>${esc(JSON.stringify(data.native_source_hashes,null,2))}</pre></details>`);
}
function conditionalExtractionLauncher(job,screen){
 if(job.engine!=='sqdmetal_palace'||screen?.status!=='NUMERICAL_SCREEN_ONLY')return '';
 return pane('Quantize this capacitance result · research','Save a separate conditional scqubits study',
  `<p>The saved conductor and ground selection supplies the reduced Maxwell capacitance. Declare the junction properties below; the result will retain its EM origin and all unresolved physical assumptions.</p>`+
  `<div class="form-grid">${numeric('extractionCj','Additional junction C_J · fF','')}${field('C_J provenance / assumption','extractionCjRef','','text')}${selection('extractionJType','Josephson quantity',[['EJ_over_h','EJ / h · GHz'],['LJ','LJ · nH']],'EJ_over_h')}${numeric('extractionJValue','Josephson value','')}${field('Josephson provenance / assumption','extractionJRef','','text')}${numeric('extractionNg','ng · 2e',0)}${numeric('extractionNcut','Initial ncut',15)}${numeric('extractionLevels','Eigenlevels',4)}</div>`+
  `<label class="helper"><input id="extractionAck" type="checkbox"> I declare C_J additional to the Maxwell matrix and accept this as a conditional single-mode research model. Zero C_J also requires an explicit assumption.</label>`+
  `<p class="helper">Four native scqubits cutoffs: ncut, ncut+5, +10, +15; final two intervals checked at 10 kHz. This does not establish electrostatic convergence or physical validation.</p>`+
  `<div class="row"><button id="extractionPreview" class="secondary" type="button" ${dirty?'disabled':''}>Preview extracted parameters</button><button id="extractionExecute" type="button" disabled>Save and run conditional quantization</button></div><div id="extractionFeedback" role="status" aria-live="polite"></div>`);
}
function readConditionalExtractionDeclaration(){
 const quantity=readText('extractionJType');
 return {schema:'sqe.conditional-transmon-assumptions.m19.v1',
  junction_capacitance_fF:readNumber('extractionCj',{min:0,max:1000}),
  junction_capacitance_convention:'ADDITIONAL_LUMPED_CJ_NOT_IN_MAXWELL_MATRIX',
  junction_reference:readText('extractionCjRef'),
  josephson:{quantity,value:readNumber('extractionJValue',{min:1e-6,max:1000}),unit:quantity==='LJ'?'nH':'GHz',reference:readText('extractionJRef')},
  ng:readNumber('extractionNg',{min:-10,max:10}),ncut:readNumber('extractionNcut',{min:6,max:60,integer:true}),
  levels:readNumber('extractionLevels',{min:3,max:6,integer:true}),acknowledged:$('extractionAck')?.checked===true};
}
function bindConditionalExtraction(job){
 const previewButton=$('extractionPreview'),executeButton=$('extractionExecute'),target=$('extractionFeedback');
 if(!previewButton||!executeButton||!target)return;
 const pid=project.id,revision=project.head;let savedPreview=null,token=0;
 const current=()=>project?.id===pid&&project.head===revision&&!dirty&&target.isConnected&&selectedResult?.id===job.id;
 const invalidate=()=>{savedPreview=null;++token;executeButton.disabled=true;target.textContent='Inputs changed; preview again before execution.'};
 for(const id of ['extractionCj','extractionCjRef','extractionJType','extractionJValue','extractionJRef','extractionNg','extractionNcut','extractionLevels','extractionAck'])$(id)?.addEventListener('input',invalidate);
 previewButton.onclick=async()=>{
  const localToken=++token;savedPreview=null;executeButton.disabled=true;
  try{
   if(!current())throw Error('Save or reload the current project revision first');
   const declaration=readConditionalExtractionDeclaration();
   if(!declaration.acknowledged)throw Error('Acknowledge the conditional junction and circuit assumptions');
   previewButton.disabled=true;target.textContent='Verifying saved capacitance, source hashes and conductor reduction…';
   const result=await api(`/api/projects/${pid}/runs/${job.id}/extraction`,'POST',{expected_revision:revision,action:'preview',declaration});
   if(!current()||localToken!==token)return;
   if(result.schema!=='sqe.extraction-preview.m19.v1'||result.expected_revision!==revision||result.solver_execution!=='NOT_EXECUTED'||!conditionalExtractionValid(result.extraction)||result.extraction.source.run_id!==job.id)throw Error('Unexpected extraction preview provenance');
   target.innerHTML=conditionalExtractionView(result.extraction);savedPreview=JSON.stringify(declaration);executeButton.disabled=false;
  }catch(error){if(target.isConnected)target.textContent='Extraction blocked: '+error.message;}
  finally{if(previewButton.isConnected)previewButton.disabled=!current();}
 };
 executeButton.onclick=async()=>{
  try{
   if(!current())throw Error('Project revision changed; reload and preview again');
   const declaration=readConditionalExtractionDeclaration();
   if(!savedPreview||JSON.stringify(declaration)!==savedPreview)throw Error('Assumptions changed; preview again');
   executeButton.disabled=true;previewButton.disabled=true;
   const result=await api(`/api/projects/${pid}/runs/${job.id}/extraction`,'POST',{expected_revision:revision,action:'execute',declaration});
   if(!current())return;
   if(result.schema!=='sqe.extraction-execution.m19.v1'||result.fabrication!=='HOLD'||!result.revision)throw Error('Unexpected extraction job acknowledgment');
   toast(result.run_id?'Conditional quantization queued: '+result.run_id.slice(0,8):'Study saved; job not queued: '+(result.reason||''),!result.run_id);
   step=5;await loadProject(pid);setTimeout(refreshRuns,1600);
  }catch(error){if(target.isConnected)target.textContent='Conditional quantization blocked: '+error.message;}
  finally{if(previewButton.isConnected)previewButton.disabled=!current();}
 };
}
