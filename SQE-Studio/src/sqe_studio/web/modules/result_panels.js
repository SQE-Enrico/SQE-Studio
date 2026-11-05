function nativeRFResultsView(screen){
 if(screen.schema!=='sqe.rf-native-results-screen.v1'||screen.engine!=='josephson_circuits'||
    screen.artifact_type!=='josephson.sparameters'||screen.fabrication!=='HOLD'||
    screen.physical_validation!=='NOT_ESTABLISHED'||screen.cross_engine_mapping!=='BLOCKED_REQUIRES_REVIEWED_PORT_IDENTITY'||
    !Array.isArray(screen.samples)||screen.samples.length!==screen.sample_count||
    screen.samples.length>1024||!Array.isArray(screen.ports)||screen.ports.length>4)
    throw Error('Native RF evidence provenance or validation gates failed');
 const point=screen.samples.slice(0,64);
 if(point.some(r=>[r.frequency_hz,r.real,r.imag,r.magnitude,r.phase_rad].some(v=>typeof v!=='number'||!Number.isFinite(v))))
   throw Error('Malformed native RF numeric sample');
 const diag=screen.matrix_diagnostics;
 if(!diag||diag.physical_validation!=='NOT_ESTABLISHED'||!Array.isArray(diag.rows)||diag.rows.length>64||
    !['NUMERIC_LINEAR_S_MATRIX_SCREEN_ONLY','NOT_APPLICABLE_PUMPED_CHANNELS_NOT_EXPORTED'].includes(diag.status))
   throw Error('Unverified RF matrix diagnostics');
 if(diag.status==='NOT_APPLICABLE_PUMPED_CHANNELS_NOT_EXPORTED'&&diag.rows.length)
   throw Error('Pumped RF diagnostics must not imply power balance');
 if(diag.rows.some(r=>typeof r.frequency_hz!=='number'||!Number.isFinite(r.frequency_hz)||
       !Array.isArray(r.outgoing_power_by_input)||r.outgoing_power_by_input.length!==screen.ports.length||
       r.outgoing_power_by_input.some(p=>typeof p.outgoing_power_sum!=='number'||!Number.isFinite(p.outgoing_power_sum)||p.outgoing_power_sum<0||
          typeof p.above_unity_numeric!=='boolean')||
       (r.max_pairwise_reciprocity_difference!==null&&
       (typeof r.max_pairwise_reciprocity_difference!=='number'||!Number.isFinite(r.max_pairwise_reciprocity_difference)||r.max_pairwise_reciprocity_difference<0))))
   throw Error('Malformed numerical RF matrix screen');
 const matrixView=diag.status==='NOT_APPLICABLE_PUMPED_CHANNELS_NOT_EXPORTED'?
  '<p class="helper">Pumped harmonic-balance study: signal-only S matrix excludes idler channels. No power-balance or reciprocity screening is offered.</p>':
  `<div class="table-wrap"><table class="data-table"><thead><tr><th>Hz</th><th>Input port</th><th>Σ |S(out,in)|²</th><th>Numerically &gt; 1</th><th>Max |Sij - Sji|</th></tr></thead><tbody>${diag.rows.flatMap(r=>r.outgoing_power_by_input.map(p=>`<tr><td>${esc(r.frequency_hz)}</td><td>${esc(p.input_port)}</td><td>${esc(p.outgoing_power_sum)}</td><td>${esc(p.above_unity_numeric?'YES':'NO')}</td><td>${esc(r.max_pairwise_reciprocity_difference??'n/a')}</td></tr>`)).join('')}</tbody></table></div><p class="helper">Numeric linear S-matrix screening only. Values above unity or asymmetry warrant expert review; neither indicates an independently validated passive/reciprocal physical device.</p>`;
 return `<section class="scientific-review" aria-label="Native complex RF scattering results"><h3>Native RF scattering · ${esc(screen.analysis)}</h3>
 <p class="helper">Native JosephsonCircuits complex power-wave S amplitudes (0→0 signal channel). Frequencies are in Hz; phase is in radians. Port numbers and reference impedances belong to the saved circuit, not to a verified EM mapping.</p>
 <div class="gate-list">${[['Samples',screen.sample_count],['Port references',screen.ports.map(p=>'P'+p.number+' · '+p.reference_impedance_ohm+' Ω').join('; ')],['HB residual',screen.harmonic_balance_residual],['EM port correspondence','BLOCKED'],['Physical validation','NOT ESTABLISHED']].map(([k,v])=>`<div class="gate-row"><span>${esc(k)}</span><strong class="gate-hold">${esc(v)}</strong></div>`).join('')}</div>
 <div class="table-wrap"><table class="data-table"><thead><tr><th>Hz</th><th>S (out,in)</th><th>Re</th><th>Im</th><th>|S|</th><th>Phase (rad)</th></tr></thead><tbody>${point.map(r=>`<tr><td>${esc(r.frequency_hz)}</td><td>${esc(r.output_port)},${esc(r.input_port)}</td><td>${esc(r.real)}</td><td>${esc(r.imag)}</td><td>${esc(r.magnitude)}</td><td>${esc(r.phase_rad)}</td></tr>`).join('')}</tbody></table></div>
 ${screen.samples.length>point.length?`<p class="helper">Showing first ${point.length} samples. Download the SHA-checked run ZIP for all native samples.</p>`:''}
 <h4>RF scattering matrix · numerical checks</h4>${matrixView}
 <div class="callout warn">Numerical RF display only: no idler/pump gain certification, HB residual, EM port identity or fabrication approval.</div></section>`;
}
function goalComparison(data,job){
 const screen=data?.design_target_screen;
 if(!screen)return '';
 if(screen.schema!=='sqe.native-design-target-screen.v1'||
    screen.revision_id!==job.revision_id||screen.project_digest!==data.manifest.project_digest||
    screen.fabrication!=='HOLD'||screen.automatic_optimization!=='BLOCKED')
    throw Error('Target feedback provenance / scientific gates failed');
 if(!Array.isArray(screen.rows))throw Error('Malformed native target screen');
 const rows=screen.rows;
 let html=`<h3>Design intent → native observation</h3><p class="helper">Targets are taken from the exact saved revision of this run. Differences and tolerances are NUMERIC ONLY; native EM mode indices are not physical mode identification. No automatic optimization, EM→Hamiltonian transfer or fabrication approval.</p>`;
 if(!rows.length)return html+'<p class="helper">No design targets saved in this run revision. Add targets under Specifications, save, and run a native study to evaluate them.</p>';
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Saved target</th><th>Goal</th><th>Native observation</th><th>Signed delta</th><th>Numerical screen</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.target??'—')} ${esc(r.unit)} (±${esc(r.tolerance??'not defined')})</td><td>${esc(r.observed??'—')} ${esc(r.observed===null?'':r.unit)}</td><td>${esc(r.signed_delta??'—')}</td><td>${esc(r.numeric_status)} · ${esc(r.scientific_note)}</td></tr>`).join('')}</tbody></table></div>`;
 if(screen.truncated)html+='<div class="callout warn">Target list exceeds the bounded numerical screen; some targets were not evaluated.</div>';
 return html;
}
function sweepView(data){
 if(data.schema!=='sqe.sweep-view.v1')throw Error('Unknown native sweep response');
 let html=`<div class="callout warn">${esc(data.status)} · No mode matching, scientific qualification, or automatic optimization. Review each point's physical meaning.</div>`;
 html+=`<div class="table-wrap"><table class="data-table"><thead><tr><th>Point</th><th>Changed native input(s)</th><th>Engine</th><th>Native output</th></tr></thead><tbody>${data.points.map(p=>{
  const v=p.eigenmodes?.modes?.map(m=>'Mode '+m.mode_index+': '+m.frequency_GHz+' GHz').join('; ')||(p.spectrum?.source==='native scqubits eigenvals'&&p.spectrum?.units==='GHz'&&p.spectrum?.levels?.length>=2?'Native eigenlevels 0/1: '+p.spectrum.levels[0]+' / '+p.spectrum.levels[1]+' GHz':'Artifact available in ZIP');
  return `<tr><td>${esc(p.index)}</td><td>${esc((p.coordinates||[]).map(x=>x.join(' = ')).join('; '))}</td><td>${esc(p.engine_version)}</td><td>${esc(v)}</td></tr>`}).join('')}</tbody></table></div>`;
 return pane('Parametric exploration · native outputs','Data are never interpolated or treated as equivalent between different solver settings.',html);
}
function nativeSpectrum(data){
 const values=data.levels;
 if(data.schema!=='sqe.scqubits.spectrum.v1'||data.engine!=='scqubits'||data.source!=='native scqubits eigenvals'||data.units!=='GHz'||!Array.isArray(values)||values.length<2||values.length>12||values.some(v=>typeof v!=='number'||!Number.isFinite(v)))return '<div class="callout warn">Spectrum artifact is missing or malformed. No chart can be rendered.</div>';
 const lo=Math.min(...values),hi=Math.max(...values),range=hi-lo||1;
 const pts=values.map((v,i)=>{const x=50+i*(420/Math.max(values.length-1,1)),y=168-(v-lo)/range*120;return `<path d="M ${x} 170 V ${y}" stroke="#73dacc" stroke-width="2"/><circle cx="${x}" cy="${y}" r="5" fill="#78ebd6"/><text x="${x}" y="189" font-size="11" text-anchor="middle" fill="#dae7f5">${i}</text><title>Level ${i}: ${esc(v)}</title>`}).join('');
 return `<h3>scqubits native eigenvalues · ${esc(data.units)}</h3><svg class="spectrum-chart" viewBox="0 0 520 218" role="img" aria-label="Native spectrum from scqubits with ${values.length} eigenvalue levels"><path d="M 32 28 V 170 H 500" stroke="#a9c5d8" fill="none"/>${pts}<text x="258" y="209" font-size="11" fill="#c5d9e9" text-anchor="middle">Energy level index · native returned eigenvalues only</text><text x="39" y="24" font-size="11" fill="#c5d9e9">${esc(hi.toPrecision(4))}</text><text x="39" y="164" font-size="11" fill="#c5d9e9">${esc(lo.toPrecision(4))}</text></svg><p class="chart-caption">Source: ${esc(data.source)}. Values displayed without extrapolation or convergence claims.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Level</th><th>Native eigenvalue</th></tr></thead><tbody>${values.map((v,i)=>`<tr><td>${i}</td><td>${esc(v)} ${esc(data.units)}</td></tr>`).join('')}</tbody></table></div>`;
}
function basisConvergenceView(data){
 const c=data?.convergence;if(!(c?.steps>1))return '';
 const rows=c.points?.[0]?.curve,parameter=c.points?.[0]?.basis_parameter;
 const number=v=>typeof v==='number'&&Number.isFinite(v);
 if(!Number.isInteger(c.steps)||c.steps<2||c.steps>4||!Array.isArray(rows)||rows.length!==c.steps+1||!['ncut','cutoff'].includes(parameter)||!number(c.tolerance_GHz)||c.tolerance_GHz<=0||!['checked_passed','checked_failed'].includes(c.status)||rows.some((r,i)=>!Number.isInteger(r.basis_cutoff)||r.basis_cutoff<1||r.basis_cutoff>80||!number(r.f01_GHz)||!Array.isArray(r.transitions_from_ground_GHz)||r.transitions_from_ground_GHz.some(v=>!number(v))||(i>0&&(!number(r.max_adjacent_delta_GHz)||r.max_adjacent_delta_GHz<0||r.basis_cutoff<=rows[i-1].basis_cutoff))))return '<div class="callout warn">Invalid native basis curve; numerical status unavailable.</div>';
 const lo=Math.min(...rows.map(r=>r.f01_GHz)),hi=Math.max(...rows.map(r=>r.f01_GHz)),span=hi-lo||Math.max(Math.abs(hi)*1e-9,1e-9);
 const x=i=>60+i*400/(rows.length-1),y=v=>155-(v-lo)*110/span;
 const points=rows.map((r,i)=>`${x(i)},${y(r.f01_GHz)}`).join(' ');
 const svg=`<svg class="spectrum-chart" viewBox="0 0 520 220" role="img" aria-label="Native f01 versus basis cutoff"><path d="M 45 30 V 170 H 485" fill="none" stroke="#a9c5d8"/><polyline points="${points}" fill="none" stroke="#78ebd6" stroke-width="2"/>${rows.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r.f01_GHz)}" r="4" fill="#78ebd6"><title>${esc(parameter)}=${r.basis_cutoff}: ${esc(r.f01_GHz)} GHz</title></circle><text x="${x(i)}" y="188" text-anchor="middle" fill="#c5d9e9" font-size="11">${r.basis_cutoff}</text>`).join('')}<text x="45" y="22" fill="#c5d9e9" font-size="11">f01 · GHz (${esc(lo.toPrecision(8))} to ${esc(hi.toPrecision(8))})</text><text x="260" y="211" text-anchor="middle" fill="#c5d9e9" font-size="11">Native ${esc(parameter)} · ${rows.length} independently evaluated bases</text></svg>`;
 const numericStatus=c.status==='checked_passed'?'NUMERICAL_PASS':'NUMERICAL_FAIL';
 return pane('Native basis convergence',`${numericStatus} · last two adjacent intervals ≤ ${c.tolerance_GHz} GHz`,svg+`<div class="table-wrap"><table class="data-table"><thead><tr><th>${esc(parameter)}</th><th>Basis dimension</th><th>f01 · GHz</th><th>Anharmonicity · GHz</th><th>Max adjacent transition drift · kHz</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.basis_cutoff}</td><td>${esc(r.basis_dimension)}</td><td>${esc(r.f01_GHz.toPrecision(10))}</td><td>${esc(r.anharmonicity_GHz)}</td><td>${r.max_adjacent_delta_GHz===null?'Baseline':esc((r.max_adjacent_delta_GHz*1e6).toPrecision(5))}</td></tr>`).join('')}</tbody></table></div><p class="helper">Both final intervals must meet the saved tolerance. The ordinary spectrum uses the saved base cutoff; this curve shows every evaluated cutoff. A failed criterion preserves the native data.</p><p class="helper">Finite-basis stability is separate from the literature approximation shown above, eigenstate identification, experimental validation and EM-to-Hamiltonian transfer.</p>`);
}
