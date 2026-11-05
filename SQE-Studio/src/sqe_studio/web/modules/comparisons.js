function comparisonView(data){
 const left=data.left,right=data.right,changes=data.design_input_changes,n=data.numerical_comparison;
 const val=v=>v===null?'—':typeof v==='object'?'[structured]':String(v);
 let html=`<div class="callout warn">${esc(data.status)} · ${esc(data.same_revision?'Same revision':'Different revisions')} · ${esc(data.same_output_type?'Same artifact type':'Different artifact types; no numeric comparison inferred')}</div>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Evidence</th><th>Left native run</th><th>Right native run</th></tr></thead><tbody>${[['Engine',left.engine,right.engine],['Study',left.study_id,right.study_id],['Revision',left.revision_id,right.revision_id],['Project SHA-256',left.project_sha256,right.project_sha256],['Native version',left.native_version,right.native_version],['Output type',left.artifact_type,right.artifact_type],['Scientific status',left.scientific_status,right.scientific_status],['Fabrication',left.fabrication_status,right.fabrication_status]].map(([k,a,b])=>`<tr><td>${esc(k)}</td><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</tbody></table></div>`;
 html+=`<h3>Changed saved engineering inputs (${changes.total})</h3><p class="helper">These are revisions of design intent, not measured physics.</p>`;
 html+=changes.shown.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Left</th><th>Right</th></tr></thead><tbody>${changes.shown.map(r=>`<tr><td>${esc(r.field)}</td><td>${esc(val(r.left))}</td><td>${esc(val(r.right))}</td></tr>`).join('')}</tbody></table></div>`:'<p class="helper">No differences in the selected engineering input fields.</p>';
 if(changes.truncated)html+='<div class="callout warn">Only the first 64 changes are displayed.</div>';
 html+=`<h3>Native numerical comparison</h3><p class="helper">${esc(n.status)} · ${esc(n.reason||n.method)}</p>`;
 if(n.rows?.length&&n.status!=='native_maxwell_matrix_differences_for_expert_review'){html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Observable / native label</th><th>Left (GHz)</th><th>Right (GHz)</th><th>Difference (GHz)</th></tr></thead><tbody>${n.rows.map(r=>`<tr><td>${esc(r.transition)}</td><td>${esc(r.left_GHz)}</td><td>${esc(r.right_GHz)}</td><td>${esc(r.delta_GHz)}</td></tr>`).join('')}</tbody></table></div>`;if(!n.convergence_verified)html+='<div class="callout warn">One or both native spectra lack convergence evidence; differences are for expert review only.</div>';}
 if(n.status==='native_maxwell_matrix_differences_for_expert_review'){
  html+=`<h3>B04 · Verified Maxwell capacitance matrix drift</h3><p class="helper">${esc(n.method)}. Maximum absolute entry change: ${esc(n.max_abs_delta_fF)} fF. Mesh convergence: ${esc(n.mesh_convergence)}. Terminal identity by native tag/order alone: ${esc(n.terminal_physical_identity)}.</p>`;
  if(n.same_native_matrix_sha256)html+='<div class="callout warn">Both runs contain exactly the same native matrix bytes; this is not independent refinement evidence.</div>';
  html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Terminals</th><th>Coefficient</th><th>Left (fF)</th><th>Right (fF)</th><th>Δ (fF)</th><th>Relative |Δ|</th></tr></thead><tbody>${n.rows.map(r=>`<tr><td>${esc(r.terminal_a)} / ${esc(r.terminal_b)}</td><td>${esc(r.kind)}</td><td>${esc(r.left_fF)}</td><td>${esc(r.right_fF)}</td><td>${esc(r.delta_fF)}</td><td>${r.relative_difference===null?'Near-zero reference':esc((100*r.relative_difference).toFixed(3))+'%'}</td></tr>`).join('')}</tbody></table></div>`;
  html+='<div class="callout warn">B04 numbers are terminal-coefficient diagnostics only; no electrostatic mesh convergence, capacitance reduction, E_C transfer or fabrication approval is established.</div>';
 }
 const cpw=data.cpw_length_scaling_reference;
 if(cpw?.schema==='sqe.cpw-length-scaling.m9.v1'&&cpw.fabrication==='HOLD'){
  html+='<h3>M9 · CPW length-frequency scientific reference</h3>';
  html+=`<p class="helper">${esc(cpw.status)} · ${esc(cpw.reason)} · DOI ${esc(cpw.reference_doi)}</p>`;
  if(cpw.checks?.length){
   const c=cpw.checks[0];
   html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Route</th><th>Lengths (mm)</th><th>Native f (GHz)</th><th>f ratio: native / reference</th><th>Relative deviation / provisional tolerance</th></tr></thead><tbody><tr><td>${esc(cpw.route_name)}</td><td>${esc(cpw.lengths_mm.left)} / ${esc(cpw.lengths_mm.right)}</td><td>${esc(cpw.frequencies_GHz.left_native)} / ${esc(cpw.frequencies_GHz.right_native)}</td><td>${esc(c.actual)} / ${esc(c.reference)}</td><td>${esc((100*c.relative_error).toFixed(3))}% / ${esc((100*c.relative_tolerance).toFixed(1))}%</td></tr></tbody></table></div>`;
  }
  html+='<div class="callout warn">CPW scaling is a numerical screening only. Neither physical eigenmode identity nor mesh convergence is established; this does not prove reproduction of the published device.</div>';
 }
 const mesh=data.mesh_refinement_series;
 if(mesh?.schema==='sqe.native-mesh-three-run.m10.v1'){
  html+='<h3>M10 · Three-mesh native eigenfrequency screening</h3>';
  html+=`<p class="helper">${esc(mesh.status)} · ${esc(mesh.reason)}. Mode identity: ${esc(mesh.mode_identity)}. Mesh convergence: ${esc(mesh.mesh_convergence)}.</p>`;
  if(mesh.mesh_sizes_um?.length===3){
   html+=`<p class="helper">Nominal mesh max (µm): ${mesh.mesh_sizes_um.map(x=>esc(x.max_um)).join(' / ')} · min (µm): ${mesh.mesh_sizes_um.map(x=>esc(x.min_um)).join(' / ')}</p>`;
  }
  if(mesh.rows?.length){
   html+='<div class="table-wrap"><table class="data-table"><thead><tr><th>Native index (not matched mode)</th><th>Coarse / medium / fine (GHz)</th><th>Δ coarse→medium (GHz)</th><th>Δ medium→fine (GHz)</th><th>Last relative drift</th><th>Drift ratio / trend</th></tr></thead><tbody>';
   html+=mesh.rows.map(r=>`<tr><td>${esc(r.native_mode_index_unverified)}</td><td>${esc(r.coarse_GHz)} / ${esc(r.medium_GHz)} / ${esc(r.fine_GHz)}</td><td>${esc(r.coarse_to_medium_abs_GHz)}</td><td>${esc(r.medium_to_fine_abs_GHz)}</td><td>${esc((100*r.last_relative_drift).toFixed(4))}%</td><td>${r.step_drift_ratio===null?'Indeterminate':esc(r.step_drift_ratio.toFixed(4))} · ${esc(r.trend)}</td></tr>`).join('');
   html+='</tbody></table></div>';
  }
  html+='<div class="callout warn">Numerical drift only. Three scalar tables do not establish field-overlap mode identity, formal mesh convergence, Richardson order, GCI, calibrated EPR, or fabrication approval.</div>';
 }
 const fields=data.field_lineage_comparison;
 if(fields?.schema==='sqe.palace-field-readiness-series.m11.v1'&&fields.fabrication==='HOLD'){
  html+='<h3>M11 · Complex-field provenance and mode-registration readiness</h3>';
  html+=`<p class="helper">${esc(fields.status)} · ${esc(fields.run_count)} SHA-verified saved Palace runs. Field lineage: ${fields.run_statuses.map(esc).join(' / ')}. Saved collection counts: ${fields.sample_counts.map(esc).join(' / ')}.</p>`;
  html+=`<p class="helper">Independent mesh files: ${esc(fields.native_mesh_hashes_distinct===null?'NOT CHECKED':fields.native_mesh_hashes_distinct?'YES':'NO')}; coordinate units: ${esc(fields.palace_coordinate_units_identical===null?'NOT CHECKED':fields.palace_coordinate_units_identical?'IDENTICAL':'INCOMPATIBLE')}. Common frame: ${esc(fields.coordinate_registration)}. Overlap: ${esc(fields.complex_overlap)}. Mode identity: ${esc(fields.physical_mode_identity)}.</p>`;
  if(fields.required_next_evidence?.length)html+=`<details class="config-details"><summary>Evidence required before physical eigenmode matching</summary><ul class="artifact-list">${fields.required_next_evidence.map(v=>`<li>${esc(v)}</li>`).join('')}</ul></details>`;
  html+='<div class="callout warn">Format and source hashes are not field data registration. No automatic physical mode assignment, H(curl) overlap, scientific convergence or EPR authorization. Fabrication HOLD.</div>';
 }
 const overlap=data.cross_mesh_visualization_review;
 if(overlap?.schema==='sqe.palace-cross-mesh-visualization-review.m12.v1'&&overlap.fabrication==='HOLD'){
  html+='<h3>M12 · Cross-mesh complex-field diagnostic</h3>';
  html+=`<p class="helper">${esc(overlap.status)} · ${esc(overlap.reason)}. Mode identity: ${esc(overlap.physical_mode_identity)}; convergence: ${esc(overlap.mesh_convergence)}.</p>`;
  if(overlap.output_cycles_not_physical_modes){
   html+=`<p class="helper">Native PVD cycles (NOT mode identifiers): ${overlap.output_cycles_not_physical_modes.map(x=>x.map(esc).join(' / ')).join(' vs. ')}.</p>`;
  }
  if(overlap.status==='VISUALIZATION_OVERLAP_DIAGNOSTIC_ONLY'&&overlap.overlap){
   const o=overlap.overlap;
   html+=`<p class="helper">E visualization overlap |forward| / |reverse|: ${esc(o.E_forward_overlap_magnitude)} / ${esc(o.E_backward_overlap_magnitude)}. Bidirectional disagreement: ${esc(o.E_bidirectional_overlap_disagreement)}. Phase (rad): ${esc(o.E_forward_relative_phase_rad)} / ${esc(o.E_backward_relative_phase_rad)}.</p>`;
   if(o.B_forward_overlap_magnitude!==undefined)html+=`<p class="helper">B flux-density overlap |forward| / |reverse|: ${esc(o.B_forward_overlap_magnitude)} / ${esc(o.B_backward_overlap_magnitude)}; B is NOT H.</p>`;
  }
  html+='<div class="callout warn">Visualization interpolation is diagnostic only. No reviewed CAD/mesh material registration, H(curl) overlap, mode assignment, scientific convergence, EPR transfer or fabrication authorization.</div>';
 }
 const tr=data.transmon_reduction_comparison;
 if(tr?.status==='conditional_transmon_matrix_reduction_drift_for_expert_review'){
  html+=`<h3>M7 · Conditional transmon capacitance drift</h3><p class="helper">${esc(tr.method)} · ${esc(tr.configuration)} · retained conductors: ${esc(tr.retained_terminal_labels.join(' / '))}.</p>`;
  html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Conditional observable</th><th>Left</th><th>Right</th><th>Δ (right−left)</th><th>Relative |Δ|</th></tr></thead><tbody>`;
  html+=`<tr><td>Effective C (fF)</td><td>${esc(tr.left_effective_capacitance_fF)}</td><td>${esc(tr.right_effective_capacitance_fF)}</td><td>${esc(tr.delta_effective_capacitance_fF)}</td><td>${esc((100*tr.relative_effective_capacitance_change).toFixed(3))}%</td></tr>`;
  html+=`<tr><td>Matrix-only E_C/h (MHz)</td><td>${esc(tr.left_ec_over_h_MHz_matrix_only)}</td><td>${esc(tr.right_ec_over_h_MHz_matrix_only)}</td><td>${esc(tr.delta_ec_over_h_MHz_matrix_only)}</td><td>${esc((100*tr.relative_ec_over_h_change).toFixed(3))}%</td></tr></tbody></table></div>`;
  if(tr.same_native_matrix_sha256)html+='<div class="callout warn">Same native matrix bytes: this is not independent mesh-refinement evidence.</div>';
  html+='<div class="callout warn">Conditional numbers only, with saved fixed/floating nodes. Physical conductor registration, electrostatic convergence, junction shunt, uncertainty and E_C→scqubits authorization remain unresolved. Fabrication HOLD.</div>';
 }else if(tr?.status==='not_comparable')html+=`<div class="callout warn">M7 conditional transmon reduction unavailable: ${esc(tr.reason)}</div>`;
 html+=`<div class="callout warn">Design iteration gate: input differences are revision-bound. Numeric deltas are NOT a fitness score, physical mode match, EM-to-Hamiltonian calibration, or authorization to apply an optimized geometry.</div>`;
 const em=data.em_observables;
 if(em?.status==='NATIVE_INDEX_SCALAR_DIAGNOSTICS_ONLY'){
  html+=`<h3>Native EM loss / port comparison</h3><p class="helper">${esc(em.reason)}. Q and external-Q deltas are numeric screens across native mode INDEX, not field-matched physical modes. Sign changes always require expert review.</p>`;
  html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Native mode / observable</th><th>Left</th><th>Right</th><th>Relative change</th><th>κ sign</th></tr></thead><tbody>${em.rows.map(r=>`<tr><td>${esc(r.native_mode_index)} / ${esc(r.observable)}${r.port_index?' · port '+esc(r.port_index):''}</td><td>${esc(r.left)}</td><td>${esc(r.right)}</td><td>${typeof r.relative_change==='number'&&Number.isFinite(r.relative_change)?esc((100*r.relative_change).toFixed(2))+'%':'Not comparable'}</td><td>${esc(r.sign_changed?'CHANGED · review':'No detected change')}</td></tr>`).join('')}</tbody></table></div>`;
 }else if(em && n.status==='native_mode_index_differences_for_expert_review')html+=`<div class="callout warn">Native Q/port comparison unavailable: ${esc(em.reason)}.</div>`;
 html+=`<p class="helper">${data.caveats.map(esc).join(' · ')}</p>`;
 return pane('Read-only comparison · no automatic scientific equivalence','Native bytes checked against recorded SHA-256 before comparison.',html);
}
function wireCompareControls(){
 const done=runs.filter(r=>r.state==='completed'&&!r.is_sweep&&!r.unsafe_location);
 if(done.length<2||!$('compareRuns'))return;
 $('compareRight').value=done[1].id;
 $('compareRuns').onclick=compareSavedRuns;
 $('compareFields').onclick=compareSavedFields;
}
async function compareSavedRuns(){
 const pid=project?.id,head=project?.head,historyToken=runHistoryRequestToken;
 const requestToken=++comparisonRequestToken;
 const out=$('comparisonView');if(out)out.replaceChildren();
 try{
  const leftId=$('compareLeft')?.value,rightId=$('compareRight')?.value,fineId=$('compareFine')?.value||'';
  if(leftId===rightId||(fineId&&(fineId===leftId||fineId===rightId)))throw Error('Choose two or three distinct completed runs');
  const left=comparisonRunEligible(leftId),right=comparisonRunEligible(rightId),fine=fineId?comparisonRunEligible(fineId):null;
  if(!pid||step!==5||!left||!right||(fineId&&!fine))throw Error('Verified job history is required to compare completed safe runs');
  const data=await api(`/api/projects/${pid}/compare?left=${encodeURIComponent(leftId)}&right=${encodeURIComponent(rightId)}${fineId?'&fine='+encodeURIComponent(fineId):''}`);
  // A stale GET must not repaint results after a different revision, job-history
  // generation, step or project. The server still checks native content hashes.
  if(requestToken!==comparisonRequestToken||historyToken!==runHistoryRequestToken||
     project?.id!==pid||project.head!==head||step!==5||
     !comparisonRunEligible(leftId)||!comparisonRunEligible(rightId)||(fineId&&!comparisonRunEligible(fineId)))return;
  if(!comparisonProvenanceValid(data,left,right,fine))throw Error('Comparison source provenance failed verification');
  if($('comparisonView'))$('comparisonView').innerHTML=comparisonView(data);
 }catch(err){
  if(requestToken===comparisonRequestToken&&project?.id===pid&&step===5){
   if($('comparisonView'))$('comparisonView').replaceChildren();
   toast(err.message,true);
  }
 }
}
