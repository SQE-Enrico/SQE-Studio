function fieldCorrelationView(d){
 if(!fieldCorrelationValid(d))throw Error('Invalid field correlation evidence');
 let html=`<p class="helper">${esc(d.status)} · ${esc(d.reason_code)}</p>`;
 if(d.grid_diagnostics?.length){
  const label={NATIVE_LINEAR_TETRA:'Native linear tetrahedra',ORDER1_LAGRANGE_LINEAR_GEOMETRY_VIEW:'Order-one Lagrange: shared linear geometry view',
   UNSUPPORTED_CELL_GEOMETRY:'Unsupported geometry; comparison blocked'};
  html+=`<h3>Native cell geometry</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Source</th><th>Observed VTK types / counts</th><th>Nodes per cell</th><th>Geometry handling</th></tr></thead><tbody>${d.grid_diagnostics.map(g=>`<tr><td>${esc(g.side)} · output ${esc(g.cycle_index+1)}</td><td>${g.cell_types.map(t=>`VTK ${esc(t.vtk_type_id)}: ${esc(t.count)}`).join(' / ')}</td><td>${esc(g.nodes_per_cell_min)}–${esc(g.nodes_per_cell_max)}</td><td>${esc(label[g.geometry_view])}</td></tr>`).join('')}</tbody></table></div>`;
 }
 if(d.status==='SAMPLED_FIELD_CORRELATION_RECORDED'){
  html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Sampling mesh</th><th>MAC (|correlation|²)</th><th>Phase (rad)</th><th>Samples / coverage</th></tr></thead><tbody>${d.directions.map(v=>`<tr><td>${esc(v.sampling_mesh)}</td><td>${esc(v.mac.toPrecision(8))}</td><td>${v.relative_phase_rad===null?'Undefined at zero correlation':esc(v.relative_phase_rad.toPrecision(8))}</td><td>${esc(v.sample_count)} / 100%</td></tr>`).join('')}</tbody></table></div>`;
  html+=`<p class="helper">Difference between sampling directions: ${esc(d.mac_gap.toPrecision(6))}. VTK ${esc(d.vtk_version)}. Positive cell-volume weights; no material weighting.</p>`;
  if(d.schema==='sqe.upstream-field-correlation.experimental.v3'){
   html+='<h3>XYZ component diagnostics</h3><p class="helper">Common model frame. Fractions are volume-weighted sample norms, not energy or EPR. Component MACs must not be averaged.</p>';
   html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Sampling mesh</th><th>Axis</th><th>Left / right sample norm share</th><th>Component MAC</th><th>Phase (rad)</th></tr></thead><tbody>${d.directions.map(v=>v.components.map(c=>`<tr><td>${esc(v.sampling_mesh)}</td><td>${esc(c.axis.toUpperCase())}</td><td>${esc((100*c.left_volume_norm_fraction).toPrecision(5))}% / ${esc((100*c.right_volume_norm_fraction).toPrecision(5))}%</td><td>${c.mac===null?'Undefined: zero or unresolved norm':esc(c.mac.toPrecision(8))}</td><td>${c.mac===null?'Undefined: norm unavailable':c.relative_phase_rad===null?'Undefined at zero correlation':esc(c.relative_phase_rad.toPrecision(8))}</td></tr>`).join('')).join('')}</tbody></table></div>`;
  }
  html+=`<details><summary>Verified source identities</summary>${d.sources.map((s,i)=>`<p class="helper">${i?'Right':'Left'} · output ${esc(s.cycle_index+1)} (not a mode), ${esc(s.mpi_piece_count)} MPI pieces; ${esc(s.cell_count)} cells, ${esc(s.ghost_cells_removed)} ghost cells removed. Mesh SHA-256: ${esc(s.mesh_sha256)}. Result manifest SHA-256: ${esc(s.result_manifest_sha256)}.</p>`).join('')}</details>`;
 }
 html+='<p class="helper">A high MAC (|correlation|²) alone does not establish physical mode correspondence. Coordinate frame is assumed; no rotation or registration is inferred. This statistic uses visualization point fields, not a material-weighted H(curl) integral. Mesh convergence and EM-to-Hamiltonian transfer remain unresolved. Fabrication HOLD.</p>';
 return pane('Experimental sampled-field comparison','Complex E sampled at native cell centers on both meshes.',html);
}
async function compareSavedFields(){
 const pid=project?.id,head=project?.head,historyToken=runHistoryRequestToken,requestToken=++comparisonRequestToken;
 const leftId=$('compareLeft')?.value,rightId=$('compareRight')?.value;
 const leftCycle=$('compareFieldsLeftCycle')?.value||'',rightCycle=$('compareFieldsRightCycle')?.value||'';
 const current=()=>requestToken===comparisonRequestToken&&historyToken===runHistoryRequestToken&&
  project?.id===pid&&project.head===head&&step===5&&$('compareLeft')?.value===leftId&&$('compareRight')?.value===rightId&&
  ($('compareFieldsLeftCycle')?.value||'')===leftCycle&&($('compareFieldsRightCycle')?.value||'')===rightCycle&&
  $('compareFieldsFrame')?.checked&&comparisonRunEligible(leftId)&&comparisonRunEligible(rightId);
 try{
  const left=comparisonRunEligible(leftId),right=comparisonRunEligible(rightId);
  if(!pid||step!==5||!left||!right||leftId===rightId||left.engine!=='sqdmetal_palace'||right.engine!=='sqdmetal_palace')throw Error('Choose two distinct completed Palace runs');
  if(!$('compareFieldsFrame')?.checked)throw Error('Acknowledge the same-frame assumption before sampling fields');
  const cycle=v=>{if(v==='')return null;const n=Number(v);if(!Number.isInteger(n)||n<1||n>12)throw Error('Output numbers must be integers from 1 to 12');return n-1;};
  const body={left:leftId,right:rightId,experimental_diagnostic:true,same_frame_assumption:true,
   left_cycle:cycle(leftCycle),right_cycle:cycle(rightCycle)};
  if($('fieldComparisonView'))$('fieldComparisonView').textContent='Sampling verified fields with VTK…';
  const data=await api(`/api/projects/${pid}/compare-fields`,'POST',body);
  if(!current())return;
  if(!fieldCorrelationEnvelopeValid(data,left,right))throw Error('Field comparison provenance failed verification');
  if($('fieldComparisonView'))$('fieldComparisonView').innerHTML=fieldCorrelationView(data.diagnostic);
 }catch(err){if(requestToken===comparisonRequestToken&&project?.id===pid&&step===5){
  if($('fieldComparisonView'))$('fieldComparisonView').replaceChildren();toast(err.message,true);
 }}
}
function compareControls(){
 if(runHistoryError)return pane('Expert cross-run comparison','Verified native histories required before comparing results.','<p class="helper">Job history is unavailable. No run is eligible for scientific comparison until server retrieval succeeds.</p>');
 const done=runs.filter(r=>r.state==='completed'&&!r.is_sweep&&!r.unsafe_location);
 if(done.length<2)return pane('Expert cross-run comparison','Requires two completed native jobs; the comparison endpoint independently verifies both source revisions and file hashes. Failed jobs have diagnostics only.','<p class="helper">Run at least two native studies to compare evidence and saved engineering inputs.</p>');
 const opts=done.map(r=>`<option value="${esc(r.id)}">${esc(r.engine)} / ${esc(r.study_id)} / ${esc(r.revision_id.slice(0,8))}</option>`).join('');
 return pane('Expert cross-run comparison','Read-only evidence side by side; numerical deltas for compatible native spectra, eigenmode tables or B04 Maxwell matrices; no physical approval.',`<div class="form-grid"><label class="form-field"><span>Left verified native run (coarse)</span><select id="compareLeft">${opts}</select></label><label class="form-field"><span>Right verified native run (medium)</span><select id="compareRight">${opts}</select></label><label class="form-field"><span>Third verified run (fine, optional)</span><select id="compareFine"><option value="">No third run · pairwise comparison</option>${opts}</select></label></div><button type="button" class="secondary" id="compareRuns">Compare runs</button><div class="form-grid"><label class="form-field"><span><input type="checkbox" id="compareFieldsFrame"> Assume the same unrotated saved-model coordinate frame for this diagnostic</span></label><label class="form-field"><span>Left output number (optional; not a mode)</span><input id="compareFieldsLeftCycle" type="number" min="1" max="12" step="1" placeholder="Auto: one complex E output"></label><label class="form-field"><span>Right output number (optional; not a mode)</span><input id="compareFieldsRightCycle" type="number" min="1" max="12" step="1" placeholder="Auto: one complex E output"></label></div><button type="button" class="secondary" id="compareFields">Compare sampled E fields · experimental</button><div id="fieldComparisonView" aria-live="polite"></div><p class="helper">Uses the selected left and right Palace runs only. VTK samples complex E on both meshes; volume-weighted MAC (|correlation|²) is a visualization statistic. Coordinate registration and physical mode identity remain unresolved.</p><p class="helper">Three Palace eigenmode runs with identical physical inputs but progressively smaller saved mesh settings enable numerical drift screening. Different engines, mode indices or mesh settings do not prove physical mode correspondence or convergence.</p>`);
}
