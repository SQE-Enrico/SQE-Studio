function palaceModeTable(data){
 if(!data||data.source!=='palace.native_eig.csv'||data.units!=='GHz'||!Array.isArray(data.modes))return '';
 return `<h3>Palace native eigenfrequency table</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Native mode index</th><th>Frequency</th><th>Mode identity</th></tr></thead><tbody>${data.modes.map(m=>`<tr><td>${esc(m.mode_index)}</td><td>${esc(m.frequency_GHz)} GHz</td><td>Not verified across runs</td></tr>`).join('')}</tbody></table></div><div class="callout warn">No EPR/Hamiltonian extraction, mode matching or convergence is inferred. Eigenmodes are shown in the solver's native order.</div>`;
}
function scientificReview(m,job,result){
 const em=result.em_evidence;
 if(em && em.schema!=='sqe.em-native-results-screen.v1')throw Error('Unsupported native EM evidence schema');
 if(m.fabrication_status!=='HOLD')throw Error('Fabrication status failed closed verification');
 const same=job.revision_id===project.head;
 const gates=[
  ['Artifact integrity','Revision and native file SHA-256 checked by the authenticated Results API',true],
  ['Revision scope',same?'Same as current saved design':'Historical revision · never apply to current design without a new run',same],
  ['Scientific review',m.scientific_status==='reviewed'?'Review recorded; independent qualification is not implied':m.scientific_status,false],
  ['EM mode identity',em?.mode_identity||'Not established by this artifact',false],
  ['Mesh / basis convergence',em?.mesh_convergence||'Not independently established by this display',false],
  ['EM → Hamiltonian',result.conditional_extraction?'Conditional capacitance model executed; physical transfer not qualified':em?.em_to_hamiltonian||'No verified extraction in this artifact',false],
  ['Fabrication authorization',m.fabrication_status,false]
 ];
 return `<section class="scientific-review" aria-label="Scientific evidence and approval gates"><h3>Scientific review · read-only gate register</h3><p class="helper">File integrity is not a physical acceptance test. All blocking gates require independently reviewed evidence; this screen cannot approve them.</p><div class="gate-list">${gates.map(([name,status,pass])=>`<div class="gate-row"><span>${esc(name)}</span><strong class="${pass?'passed':'gate-hold'}">${esc(status)}</strong></div>`).join('')}</div></section>`;
}
function nativeEMEvidenceView(data){
 if(!data||data.schema!=='sqe.em-native-results-screen.v1')return '';
 let html=`<h3>Native EM · physical observations (screening only)</h3><p class="helper">Read from the saved revision-bound, SHA-256 checked native run. Solver mode indices do not establish correspondence across mesh refinements. Port signs are preserved.</p>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Mode</th><th>f (GHz)</th><th>Total Q</th><th>Electric / magnetic energy</th></tr></thead><tbody>${data.modes.map(m=>`<tr><td>${esc(m.native_mode_index)}</td><td>${esc(m.frequency_GHz)}</td><td>${esc(m.q_total)}</td><td>${esc(m.electric_to_magnetic_energy_ratio??'Not exported')}</td></tr>`).join('')}</tbody></table></div>`;
 const ports=data.modes.flatMap(m=>(m.ports||[]).map(p=>({...p,mode:m.native_mode_index})));
 const negative=ports.filter(p=>typeof p.native_kappa_ext_GHz==='number'&&p.native_kappa_ext_GHz<0);
 if(ports.length)html+=`<h3>Native external ports</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Mode / port</th><th>Q ext</th><th>Native κ ext (GHz)</th><th>Advisory</th></tr></thead><tbody>${ports.map(p=>`<tr><td>${esc(p.mode)} / ${esc(p.port_index)}</td><td>${esc(p.q_ext)}</td><td>${esc(p.native_kappa_ext_GHz)}</td><td>${esc(p.advisory)}</td></tr>`).join('')}</tbody></table></div>`;
 else html+='<p class="helper">No declared native port-Q table. No coupling estimates inferred.</p>';
 if(negative.length)html+=`<div class="callout warn" role="note">Signed κ review required: ${esc(negative.length)} native port value(s) are negative. Values above are preserved without absolute-value conversion. Physical port orientation, energy normalization and signed coupling interpretation remain UNVERIFIED.</div>`;
 const field=data.field_acquisition;
 html+=`<div class="callout warn">Field acquisition: ${esc(field.status)}. Native field files: ${esc(field.artifact_count)}. Common coordinate domain: ${esc(field.common_coordinate_domain_verified?'Recorded by reader · independent review needed':'NOT VERIFIED')}. Complex vector normalization: ${esc(field.complex_vector_normalization_verified?'Recorded by reader · independent review needed':'NOT VERIFIED')}. Mode identity: ${esc(data.mode_identity)}. EM→Hamiltonian: ${esc(data.em_to_hamiltonian)}. Native geometry optimization: ${esc(data.automatic_geometry_optimization)}. Fabrication: ${esc(data.fabrication)}.</div>`;
 if(field.artifact_names?.length)html+=`<details class="config-details"><summary>Native field artifact inventory · not an overlap visualization</summary><ul class="artifact-list">${field.artifact_names.map(name=>`<li><code>${esc(name)}</code></li>`).join('')}</ul></details>`;
 if(data.limitations?.length)html+=`<details class="config-details"><summary>Scientific limitations of this native observation</summary><ul class="artifact-list">${data.limitations.map(text=>`<li>${esc(text)}</li>`).join('')}</ul></details>`;
 return html;
}
function nativeFieldLineageView(data){
 if(!data||data.schema!=='sqe.palace-verified-field-lineage.m11.v1'||data.fabrication!=='HOLD')return '';
 let html=`<h3>M15 · Palace complex-field source verification</h3><p class="helper">${esc(data.status)} · ${esc(data.reason)}.</p>`;
 if(data.diagnostic_code)html+=`<div class="callout warn"><strong>Native field preflight blocker:</strong> ${esc(data.diagnostic_code)} · stage ${esc(data.diagnostic_phase)}. ${esc(data.recommended_action)}</div>`;
 const decl=data.field_declaration_diagnostic;
 if(decl?.schema==='sqe.vtu-e-field-declaration.m15.v1'){
   const fields=['E_real','E_imag','E'];
   const assoc=[['point','PointData'],['cell','CellData'],['parallel_point','PVTU PPointData']];
   html+=`<details class="config-details"><summary>Signed native VTK declarations · format diagnosis only</summary><p class="helper">Only published Palace E field names and categorical metadata are shown; no field values or mesh are exported.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Association</th>${fields.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${assoc.map(([key,title])=>`<tr><td>${esc(title)}</td>${fields.map(field=>`<td>${esc(decl[key]?.[field]??'UNAVAILABLE')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
 }
 html+=`<p class="helper">Verified saved collection ordinals (NOT matched physical modes): ${data.saved_mode_ordinals_unverified?.length?data.saved_mode_ordinals_unverified.map(esc).join(' / '):'None'}. VTK pieces: ${esc(data.vtk_piece_count??'Not available')}. Physical mode identity: ${esc(data.physical_mode_identity)}. Mesh convergence: ${esc(data.mesh_convergence)}.</p>`;
 if(data.output_cycles_not_physical_modes)html+=`<p class="helper">Palace output cycles, not physical mode labels: ${data.output_cycles_not_physical_modes.map(esc).join(' / ')}; configured Save: ${esc(data.native_requested_mode_save_count)}.</p>`;
 if(data.mesh_sha256)html+=`<details class="config-details"><summary>Field provenance hashes</summary><p>Native mesh SHA-256: <code>${esc(data.mesh_sha256)}</code></p><p>Palace deck SHA-256: <code>${esc(data.deck_sha256)}</code></p><p>Native eigenmode table SHA-256: <code>${esc(data.native_eig_sha256)}</code></p></details>`;
 html+='<div class="callout warn">VTK format and lineage do not establish common-domain field registration, complex phase/norm, physical eigenmode identity, convergence or permission to transfer EPR parameters.</div>';
 return html;
}
function nativeCapacitanceView(data){
 if(!data||data.schema!=='sqe.native-capacitance-screen.v1'||
    data.status!=='NATIVE_MAXWELL_MATRIX_SCREENED'||
    !Array.isArray(data.conductor_order)||!Array.isArray(data.capacitance_matrix_F)||
    data.capacitance_matrix_F.length!==data.conductor_order.length||
    data.conductor_order.length>16||data.fabrication!=='HOLD')return '';
 const n=data.conductor_order.length;
 const matrixRows=data.capacitance_matrix_F.map((row,i)=>`<tr><th>${esc(data.conductor_order[i])}</th>${row.map(v=>`<td>${esc(Number(v)*1e15)}</td>`).join('')}</tr>`).join('');
 let html=`<h3>Palace electrostatic Maxwell matrix · native evidence</h3><p class="helper">Verified native terminal-C.csv in the saved design revision. Conductors follow the solver's reviewed terminal order. Values in fF; symmetry residual ${esc(data.symmetry_relative_residual)}. This is not a floating-transmon extraction or a quantum parameter mapping.</p>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Terminal</th>${data.conductor_order.map((name,i)=>`<th>${esc(i+1)} · ${esc(name)}</th>`).join('')}</tr></thead><tbody>${matrixRows}</tbody></table></div>`;
 html+=`<h3>Conditional charging-energy indicators · not scqubits inputs</h3><p class="helper">Each indicator uses only Cii with every other modeled terminal fixed at zero voltage: E_C/h = e²/(2h Cii). Other grounded/floating terminals, junction capacitance and parasitics require separate physical review.</p>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Terminal</th><th>Component</th><th>Cii (fF)</th><th>Conditional E_C/h (GHz)</th></tr></thead><tbody>${(data.conditional_island_indicators||[]).map(t=>`<tr><td>${esc(t.terminal_index)}</td><td>${esc(t.component)}</td><td>${esc(Number(t.C_ii_F)*1e15)}</td><td>${esc(t.conditional_EC_over_h_GHz)}</td></tr>`).join('')}</tbody></table></div>`;
 html+=`<div class="callout warn">C → E_C → scqubits: ${esc(data.scqubits_EC_transfer)}. Independent conductor/ground and floating-node review, electrostatic convergence, and an approved quantization model are required before modifying the active Hamiltonian. This panel never changes a quantum study. Fabrication: HOLD.</div>`;
 return html;
}
function transmonCapacitanceView(data){
 if(!data)return '';
 if(data.schema!=='sqe.transmon-integration-screen.m1.v1'||data.fabrication!=='HOLD'||
    data.scqubits_EC_transfer!=='BLOCKED_NOT_REVIEWED')
   throw Error('Transmon reduction release gate mismatch');
 if(data.status==='BLOCKED_NO_SAVED_SELECTION')
   return '<section class="scientific-review"><h3>Transmon topology and charging energy</h3><div class="callout warn">BLOCKED: Save the explicit island pair, native electrostatic study, and fixed/floating classification in the same project revision before running Palace. This is not inferred from matrix column order.</div></section>';
 if(data.status!=='NUMERICAL_SCREEN_ONLY'||!data.native_topology||!data.native_mapping||
    !data.reduction||data.reduction.status!=='NUMERICAL_SCREEN_ONLY'||
    data.reduction.transfer_status!=='BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION'||
    data.native_topology.scientific_status!=='UNREVIEWED_TOPOLOGY'||
    data.native_mapping.geometry_registration!=='BLOCKED_NO_INDEPENDENT_QDESIGN_TO_GMSH_FACE_REGISTRATION')
   throw Error('Incomplete or promoted transmon scientific evidence');
 const p=data.reduction.numerical_preview, t=data.native_topology;
 if(!p||typeof p.effective_capacitance_f!=='number'||!Number.isFinite(p.effective_capacitance_f)||
    typeof p.ec_over_h_hz_matrix_only!=='number'||!Number.isFinite(p.ec_over_h_hz_matrix_only)||
    p.effective_capacitance_f<=0||p.ec_over_h_hz_matrix_only<=0)
   throw Error('Invalid transmon capacitance numerical preview');
 return `<section class="scientific-review"><h3>Saved transmon charge mode · conditional numerical screen</h3>
 <p class="helper">Saved pair ${esc(t.proposed_pair.island_a)} / ${esc(t.proposed_pair.island_b)} · ${esc(p.configuration)}. Effective capacitance from the authenticated Maxwell matrix and explicit fixed/floating terminal assumptions, not an authorized qubit parameter.</p>
 <div class="gate-list">${[['C effective (fF)',p.effective_capacitance_f*1e15],
 ['Conditional E_C/h (GHz)',p.ec_over_h_hz_matrix_only/1e9],
 ['Floating nodes',p.floating_zero_charge.join(', ')||'none'],
 ['Held at zero',p.fixed_zero.join(', ')||'none'],
 ['Topology review',t.review.status],['QDesign → Gmsh registration','BLOCKED'],
 ['scqubits E_C transfer',data.scqubits_EC_transfer],['Fabrication',data.fabrication]].map(([k,v])=>`<div class="gate-row"><span>${esc(k)}</span><strong class="gate-hold">${esc(v)}</strong></div>`).join('')}</div>
 <div class="callout warn">Junction shunt/E_J, electrostatic convergence, topology registration, circuit convention and uncertainty NOT ESTABLISHED. This numerical preview is NEVER written into a scqubits Hamiltonian.</div></section>`;
}
// The native CAD manifest proves file integrity, not layer/pin/mesh equivalence.
// B01 cannot pass until the physical lineage is independently established.
function nativeCADLineageView(m,job){
 if(m.engine!=='quantum_metal')return '';
 const files=(m.artifacts||[]).filter(a=>typeof a.name==='string');
 const gds=files.filter(a=>/\.(gds|gdsii)$/i.test(a.name));
 return `<section class="scientific-review" aria-label="CAD and GDS physical lineage review">
  <h3>CAD / GDS physical lineage · review required</h3>
  <p class="helper">Authenticated native artifact inventory for job ${esc(job.id)}; recorded files are SHA-256 checked by the Results API. No geometry equivalence inferred.</p>
  <div class="gate-list">
  ${[['Design revision',job.revision_id],['Project SHA-256',m.project_digest],
  ['Native GDS members',gds.length+' file(s) recorded · geometry not independently checked'],
  ['GDS → Gmsh mapping','BLOCKED · layer/port/physical-tag correspondence unverified'],
  ['Physical dimensions and units','BLOCKED · independent geometry/area inspection missing'],
  ['Foundry DRC/LVS/PDK','HOLD · not authorized']].map(([k,v])=>`<div class="gate-row"><span>${esc(k)}</span><strong class="gate-hold">${esc(v)}</strong></div>`).join('')}
  </div></section>`;
}
