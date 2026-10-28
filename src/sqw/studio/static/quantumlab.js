'use strict';
// Zero build-system dependencies: native DOM, SVG, authenticated SQE Studio API.
const $=q=>document.querySelector(q);
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const fmt=(v,n=3)=>Number.isFinite(Number(v))?Number(v).toFixed(n):'—';
const NAV=[['schematic','Schematic','01'],['layout','Layout / GDS','02'],['modes','Modes / EPR','03'],['sparameters','RF / S-param','04'],['flux','SQUID / flux','05'],['dynamics','Dynamics','06'],['duffing','Nonlinearity','07'],['yield','Yield Monte Carlo','08'],['optimize','Optimization','09'],['loss_budget','Loss budget','10'],['design_checks','Design check','11'],['unified','Unified physical QPU','12'],['palace','Palace / FEM 3D','13'],['history','Jobs / results','14'],['roadmap','Backend / roadmap','15']];
const INFO={
 modes:['Eigenmodes and χ matrix','Eigenvalues of the linearized LC network, Josephson inductive participation, Kerr estimates and qubit-mode assignment. This is not electromagnetic FEM eigenmode/EPR.'],
 sparameters:['Small-signal RF analysis','Up to 8-port network response: S(f), magnitude, phase and Touchstone. Lumped elements only, not a 3D MoM/FEM solver.'],
 flux:['SQUID spectroscopy','External flux sweep, effective EJ and modes. A circuit SQUID branch can be converted from a JJ in the schematic.'],
 dynamics:['Time-domain experiments','Ideal Rabi, Ramsey, echo and T1 sequences: Bloch equations with T1/T2, without pulse distortions or leakage.'],
 duffing:['Reduced nonlinear response','Single-Kerr-mode cubic nonlinear response. Not a multi-Josephson harmonic balance or JTWPA solver.'],
 yield:['Variability and yield','Monte Carlo on capacitances and Josephson energies. Estimates frequency target compliance, not foundry manufacturing yield.'],
 optimize:['Target-driven tuning','Constrained EJ tuning for one qubit. Produces a manually applicable proposal; never silently modifies the design.'],
 loss_budget:['Loss budget and T1','T1=Q/ω estimate from user-supplied Q factors. No field-derived interface participation.'],
 design_checks:['Design checks','Connectivity, target frequencies and crowding. Preliminary electrical checks, not geometric DRC sign-off.']};
const DEFAULT_OPTIONS={modes:{},sparameters:{start_ghz:3,stop_ghz:10,points:201},flux:{start:0,stop:1,points:101},dynamics:{sequence:'rabi',duration_us:2,rabi_mhz:4,detuning_mhz:0.5,t1_us:30,t2_us:20,points:201},duffing:{linewidth_mhz:2,drive_mhz:0.1,points:201},yield:{count:120,seed:7,ej_sigma_pct:1,c_sigma_pct:1},optimize:{min_ej_ghz:4,max_ej_ghz:28},loss_budget:{dielectric_q:1e6,conductor_q:2e7,radiation_q:1e8,quasiparticle_q:1e8},design_checks:{}};
let S={csrf:'',user:null,projects:[],project:null,doc:null,design:null,view:'schematic',selection:0,dirty:false,saving:null,editVersion:0,
       job:null,result:null,resultJobId:null,options:structuredClone(DEFAULT_OPTIONS),busy:false,
       palaceStatus:null,femPreview:null,femError:null,femJobFiles:[],femCsv:null,palaceRanks:1,unifiedPreview:null,unifiedError:null,unifiedJobFiles:[],physicalResult:null};
let saveTimer=null,noticeTimer=null;
function notify(message){const el=$('#notice');el.textContent=message;el.style.display='block';clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{el.style.display='none'},7500);}
async function api(path,method='GET',data){const options={method,credentials:'same-origin',headers:{}};
 if(method!=='GET'){options.headers['Content-Type']='application/json';options.headers['X-CSRF-Token']=S.csrf;options.body=JSON.stringify(data||{});}
 const r=await fetch('/api'+path,options);const json=await r.json();if(!r.ok)throw Error(json.error||`HTTP ${r.status}`);return json;}
function projectLabel(p){return `${p.name} · ${p.id.slice(0,7)}`;}
async function loadProject(id){S.project=await api('/projects/'+id);S.doc=S.project.document;S.design=structuredClone(S.doc.quantum_lab||await api('/quantumlab/preset?size=1'));
 S.dirty=false;S.editVersion=0;S.result=null;S.job=null;S.resultJobId=null;S.femPreview=null;S.femError=null;S.femJobFiles=[];S.unifiedPreview=null;S.physicalResult=null;S.unifiedJobFiles=[];
 const last=S.project.jobs.find(j=>j.mode==='lab'&&j.state==='succeeded');
 if(last){S.view=last.target.split(':')[1];try{await loadJob(last.id,false)}catch(e){notify(e.message);}}else S.view='schematic';
 render();}
async function init(){try{const session=await api('/auth/session');S.user=session.user;S.csrf=session.csrf;
 S.projects=await api('/projects');if(!S.projects.length){$('#workspace').innerHTML=`<section class="card"><h1>New QPU lab</h1><p>Create a project in Studio to store designs and calculations with immutable revisions.</p><button class="primary" data-act="new-project">Create research project</button> <a class="button" href="/">Open Studio</a></section>`;return;}
 await loadProject(S.projects[0].id);
 }catch(e){$('#workspace').innerHTML=`<section class="card"><h1>Studio sign-in required</h1><p>The lab shares Studio authentication, roles, database and job queue. Sign in and reopen the lab.</p><a href="/" class="button">Go to SQE Studio</a><p class="hint">${esc(e.message)}</p></section>`;}}
function isViewer(){return S.user?.role==='viewer'||S.project?.access_role==='viewer';}
function setDirty(){S.dirty=true;S.editVersion++;const el=$('#save-state');if(el)el.textContent='Unsaved changes';clearTimeout(saveTimer);saveTimer=setTimeout(()=>save().catch(e=>notify(e.message)),1000);}
async function save(){if(!S.dirty||!S.project)return;
 if(S.saving){await S.saving;return save();}
 const version=S.editVersion;S.doc.quantum_lab=structuredClone(S.design);
 const snapshot=structuredClone(S.doc);const id=S.project.id;
 S.saving=api(`/projects/${id}`,'PUT',{document:snapshot,draft_version:S.project.draft_version});
 try{const r=await S.saving;if(S.project?.id===id){S.project.draft_version=r.draft_version;S.dirty=S.editVersion!==version;const x=$('#save-state');if(x)x.textContent=S.dirty?'Unsaved changes':'Draft saved';}}
 finally{S.saving=null;}
 if(S.dirty)await save();}
function workspaceHeader(title,sub){return `<div class="hero"><div><div class="overline">QPU ENGINEERING / ${esc(S.design.name||'DESIGN')}</div><h1>${esc(title)}</h1><p class="muted">${esc(sub||'')}</p><p class="status-line"><span id="save-state">${S.dirty?'Unsaved changes':'Draft saved'}</span> · ${S.project.revisions.length} revisions · ${S.design.qubits.length} qubit · ${S.design.elements.length} elements</p></div><div class="actions"><button data-act="save-revision">Checkpoint</button><button data-act="export">Export project</button><button class="primary" data-act="save">Save</button></div></div>`;}
function render(){if(!S.project)return;
 $('#project-choice').innerHTML=S.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===S.project.id?'selected':''}>${esc(projectLabel(p))}</option>`).join('');
 $('#lab-nav').innerHTML=NAV.map(([id,name,n])=>`<button class="${id===S.view?'active':''}" data-act="section" data-id="${id}">${esc(name)}<span>${n}</span></button>`).join('');
 let content='';if(S.view==='schematic')content=schematic();else if(S.view==='layout')content=layoutView();else if(INFO[S.view])content=analysisView(S.view);else if(S.view==='unified')content=unifiedView();else if(S.view==='palace')content=palaceView();else if(S.view==='history')content=historyView();else content=roadmapView();
 $('#workspace').innerHTML=workspaceHeader(S.view==='schematic'?'Circuit schematic':S.view==='layout'?'Concept layout and GDS':S.view==='unified'?'QPU · unified physical model':S.view==='palace'?'Palace · Workbench FEM 3D':INFO[S.view]?.[0]|| (S.view==='history'?'Job history':'Solvers and infrastructure'),
 S.view==='schematic'?'Lumped netlist editor: components, nodes, junctions and ports.':S.view==='unified'?'Schematic, layout, masks, QGeometry and FEM from one parametrized design.':S.view==='palace'?'Physical geometry is distinct from the multi-qubit reduced netlist · Gmsh · Palace (native or WSL2).':INFO[S.view]?.[1]||'')+content;
 if(isViewer())document.querySelectorAll('[data-act="save"],[data-act="save-revision"],[data-act="preset"],[data-act="add-element"],[data-act="remove-element"],[data-act="run"],[data-act="run-fem"],[data-act="run-physical"],[data-act="physical-preset"],[data-act="param-create"],[data-act="param-preset"],[data-act="param-add"],[data-act="param-remove"],[data-act="param-json-apply"],[data-act="adopt-physical"],[data-act="apply-proposal"],[data-act="convert-squid"],[data-act="add-port"]').forEach(b=>b.disabled=true);
}
function paramsOf(el){if(el.kind==='JJ')return `EJ/h ${fmt(el.ej_ghz,2)} GHz`;if(el.kind==='SQUID')return `EJ/h ${fmt(el.ej_ghz,2)} GHz · Φ ${fmt(el.flux_phi0,2)}`;const unit={C:'fF',L:'nH',R:'Ω'}[el.kind];return `${fmt(el.value,2)} ${unit}`;}
function nodelist(){return [...new Set(S.design.elements.flatMap(e=>[e.a,e.b]).filter(x=>x!=='0'))].sort();}
function getPos(node){const p=S.design.positions?.[node];if(Array.isArray(p)&&p.length===2&&p.every(Number.isFinite))return p;
 const i=nodelist().indexOf(node);return [110+(i%6)*170,110+Math.floor(i/6)*150];}
function circuitSvg(){const elements=S.design.elements,nodes=nodelist(),positions=nodes.map(getPos);
 const mx=Math.max(720,...positions.map(x=>x[0]+80)),my=Math.max(410,...positions.map(x=>x[1]+100));
 let lines=''; const grouped=new Map();
 for(const el of elements){let key=[el.a,el.b].sort().join('|');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(el);}
 for(const es of grouped.values()){
  const a=es[0].a,b=es[0].b,x=getPos(a==='0'?b:a),y=b==='0'||a==='0'?[x[0],x[1]+55]:getPos(b);
  const ex=(x[0]+y[0])/2,ey=(x[1]+y[1])/2;
  lines+=`<g><line class="edge" x1="${x[0]}" y1="${x[1]}" x2="${y[0]}" y2="${y[1]}"></line>`;
  if(a==='0'||b==='0')lines+=`<path d="M${y[0]-13} ${y[1]}h26 m-21 5h16 m-11 5h6" stroke="#86abc1" fill="none" stroke-width="1.5"/>`;
  lines+=`<text class="edgelabel" x="${ex+8}" y="${ey-6}">${esc(es.map(e=>e.id).join(' · '))}</text></g>`;
 }
 const dots=nodes.map(node=>{const [x,y]=getPos(node);return `<g class="node ${node.startsWith('r')?'readout':''}" data-node="${esc(node)}" transform="translate(${x},${y})"><circle r="22"></circle><text dy="5">${esc(node)}</text></g>`;}).join('');
 return `<svg class="graph" id="circuit-graph" viewBox="0 0 ${mx} ${my}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Interactive topological view of circuit nodes and components"><defs><pattern id="labgrid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M 30 0 L 0 0 0 30" fill="none" stroke="#27465b" stroke-width=".5"/></pattern></defs><rect width="100%" height="100%" fill="url(#labgrid)"/>${lines}${dots}</svg>`;}
function field(label,id,value,min=null,step='any'){return `<label class="field"><span>${esc(label)}</span><input data-value="${esc(id)}" type="number" step="${step}" ${min!=null?`min="${min}"`:''} value="${esc(value??'')}"></label>`;}
function schematic(){const d=S.design,selected=d.elements[S.selection]||d.elements[0];
 const details=selected?`<div class="card"><h2>Properties of ${esc(selected.id)}</h2><div class="fields"><label class="field"><span>ID</span><input data-element="id" value="${esc(selected.id)}"></label><label class="field"><span>Type</span><select data-element="kind">${['C','L','R','JJ','SQUID'].map(x=>`<option ${selected.kind===x?'selected':''}>${x}</option>`).join('')}</select></label><label class="field"><span>Nodo A</span><input data-element="a" value="${esc(selected.a)}"></label><label class="field"><span>Nodo B</span><input data-element="b" value="${esc(selected.b)}"></label>${selected.kind==='JJ'||selected.kind==='SQUID'?field('EJ/h (GHz)','ej_ghz',selected.ej_ghz,0):field(selected.kind==='C'?'C (fF)':selected.kind==='L'?'L (nH)':'R (Ω)','value',selected.value,0)}${selected.kind==='SQUID'?field('Asimmetria','asymmetry',selected.asymmetry,0)+field('Flux Φ / Φ₀','flux_phi0',selected.flux_phi0):''}</div><div class="actions" style="margin-top:14px"><button data-act="remove-element" class="warn">Elimina elemento</button>${selected.kind==='JJ'?'<button data-act="convert-squid">Converti in SQUID</button>':''}</div></div>`:'';
 return `<div class="card"><div class="actions"><b>Template QPU</b>${[1,4,9,16].map(n=>`<button data-act="preset" data-size="${n}">${n} qubit</button>`).join('')}<button data-act="add-element">+ Add element</button><button data-act="add-port">+ RF port</button></div><div class="alert info">Electrical schematic, not mask layout. Drag nodes to rearrange the graph; positions do not alter circuit parameters.</div>${circuitSvg()}<p class="hint">Circles represent equipotential nodes. Multiple edges between two nodes represent parallel branches.</p></div>
 <div class="grid"><section><div class="card"><h2>Elements and nodes</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Type</th><th>Nodes</th><th>Parameter</th><th></th></tr></thead><tbody>${d.elements.map((e,i)=>`<tr><td>${esc(e.id)}</td><td><span class="pill plain">${e.kind}</span></td><td>${esc(e.a)} ↔ ${esc(e.b)}</td><td>${esc(paramsOf(e))}</td><td><button class="mini-btn" data-act="select-element" data-index="${i}">${i===S.selection?'Select':'Edit'}</button></td></tr>`).join('')}</tbody></table></div></div>${details}</section><section><div class="card"><h2>Qubit assignments</h2>${d.qubits.map((q,i)=>`<div class="metric" style="margin-bottom:11px"><b>${esc(q.id)} · ${esc(q.junction)}</b><div class="fields" style="margin-top:9px">${field('Target GHz',`qubit.${i}.target_ghz`,q.target_ghz,0)}${field('Tolerance MHz',`qubit.${i}.tolerance_mhz`,q.tolerance_mhz,0)}</div></div>`).join('')}</div><div class="card"><h2>RF ports</h2>${d.ports.map((p,i)=>`<div class="metric" style="margin-bottom:10px"><b>${esc(p.id)} · ${esc(p.node)}</b><div class="fields" style="margin-top:9px">${field('Z₀ (Ω)',`port.${i}.z0_ohm`,p.z0_ohm,0)}${field('Coupling C (fF)',`port.${i}.coupling_ff`,p.coupling_ff,0)}</div><button class="mini-btn warn" data-act="remove-port" data-index="${i}">Remove port</button></div>`).join('')}</div><div class="card"><h2>Netlist JSON</h2><p class="hint">The complete source model is exportable with the project and editable offline; validation occurs before execution.</p><button data-act="download-netlist">Export schematic JSON</button></div></section></div>`;
}
function layoutView(){const c=S.design.chip||{};
 return `<div class="grid"><section><div class="card"><h2>Conceptual chip placement</h2>${circuitSvg()}<p class="hint">This is a parametric schematic graph. GDS export is an interchange demonstration: pads, meanders and markers without complete routing, ground plane or a qualified junction model.</p></div><div class="card"><h2>Flow toward a verifiable physical layout</h2><p>The original Studio workflow supports a two-pad transmon, native GDSII/QPDK, process rules, Gmsh and Palace. The conceptual multi-QPU GDS here is neither claimed equivalent to the netlist nor used to extract capacitance.</p><a class="button" href="/">Open the Studio FEM workflow</a></div></section>
 <section><div class="card"><h2>Chip and layers</h2><div class="fields">${field('Chip width (µm)','chip.width_um',c.width_um,400)}${field('Chip height (µm)','chip.height_um',c.height_um,400)}${field('Metal layer','chip.metal_layer',c.metal_layer,0)}${field('Layer JJ marker','chip.junction_layer',c.junction_layer,0)}${field('Required minimum gap (µm)','chip.min_gap_um',c.min_gap_um,0)}</div><div class="alert">Candidate GDS, NOT fabrication-ready: no full DRC, no parametrized pad-ring or complete interconnect, and no equivalent EM-qualified layout.</div><button class="primary" data-act="download-gds">Export concept-only GDSII</button></div></section></div>`;}
function optionFields(analysis){const values=S.options[analysis]||{};
 return Object.entries(values).map(([key,v])=>{
  if(key==='sequence')return `<label class="field"><span>Experiment</span><select data-opt="${analysis}:sequence">${['rabi','ramsey','echo','t1'].map(x=>`<option ${v===x?'selected':''} value="${x}">${x.toUpperCase()}</option>`).join('')}</select></label>`;
  return `<label class="field"><span>${esc(key.replaceAll('_',' '))}</span><input data-opt="${analysis}:${key}" type="number" step="any" value="${esc(v)}"></label>`;
 }).join('');}
function analysisView(a){const info=INFO[a];const labjobs=S.project.jobs.filter(j=>j.target==='lab:'+a);
 const q=S.design.qubits;
 return `<div class="grid"><section><div class="card"><div class="actions" style="justify-content:space-between"><h2>Simulation setup · ${esc(a)}</h2><span class="pill">Worker computation</span></div><div class="fields">${optionFields(a)}${['dynamics','duffing','optimize'].includes(a)&&q.length?`<label class="field"><span>Qubit</span><select data-opt="${a}:qubit"><option value="">First qubit</option>${q.map(x=>`<option value="${esc(x.id)}" ${S.options[a].qubit===x.id?'selected':''}>${esc(x.id)}</option>`).join('')}</select></label>`:''}</div><div class="actions" style="margin-top:16px"><button data-act="run" class="primary" data-analysis="${a}" ${S.busy?'disabled':''}>▶ Run ${esc(a)}</button>${labjobs.length?`<span class="hint">${labjobs.length} previous jobs</span>`:''}</div><p class="hint">The simulation saves an immutable revision and runs on the worker. JSON and optional Touchstone outputs are saved in the project.</p></div>
 ${renderResult(a)}</section><section><div class="card"><h2>Model and limitations</h2><div class="pill wait">REDUCED MODEL</div><p>${esc(info[1])}</p><div class="alert">Circuit predictions are not QPU validation without an EM solver, measured calibration data, verified materials and boundary conditions.</div></div>${labjobs.length?`<div class="card"><h2>Recent simulations</h2>${labjobs.slice(0,7).map(j=>`<div class="row" style="justify-content:space-between;margin:10px 0"><span>${new Date(j.created*1000).toLocaleString('en-US')} · <span class="pill ${j.state==='succeeded'?'':j.state==='failed'?'error':'wait'}">${esc(j.state)}</span></span><button class="mini-btn" data-act="view-job" data-id="${esc(j.id)}">Open</button></div>`).join('')}</div>`:''}</section></div>`;}
const COLORS=['#60ded0','#f8c878','#9eaaff','#e792a7','#7de5a6','#faac68','#7ed0eb','#dbb5ff'];
function plotSeries(title,x,sets,xLabel='',yLabel=''){if(!x?.length||!sets?.length)return '<p class="hint">No data points to display.</p>';
 const width=820,height=340,pad={l:64,r:24,t:34,b:52};const points=sets.flatMap(s=>s.data).filter(Number.isFinite);if(!points.length)return '';
 let ymin=Math.min(...points),ymax=Math.max(...points);if(ymax-ymin<1e-10){ymin-=1;ymax+=1;}const margin=(ymax-ymin)*.06;ymin-=margin;ymax+=margin;
 const xmin=Number(x[0]),xmax=Number(x.at(-1)),sx=v=>pad.l+(v-xmin)/Math.max(1e-10,xmax-xmin)*(width-pad.l-pad.r),sy=v=>pad.t+(ymax-v)/(ymax-ymin)*(height-pad.t-pad.b);
 let marks='';for(let i=0;i<=5;i++){const yy=pad.t+i*(height-pad.t-pad.b)/5;const value=ymax-(ymax-ymin)*i/5;marks+=`<line x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}" stroke="#24425c" stroke-width="1"/><text x="${pad.l-8}" y="${yy+4}" text-anchor="end">${fmt(value,2)}</text>`;}
 for(let i=0;i<=5;i++){const xx=pad.l+i*(width-pad.l-pad.r)/5;marks+=`<text x="${xx}" y="${height-24}" text-anchor="middle">${fmt(xmin+(xmax-xmin)*i/5,2)}</text>`;}
 const paths=sets.map((s,i)=>{const stride=Math.max(1,Math.floor(x.length/700));const path=x.map((v,i)=>({v,i})).filter(p=>p.i%stride===0||p.i===x.length-1).map((p,k)=>{const v=p.v,val=s.data[p.i];return `${k===0?'M':'L'}${sx(Number(v)).toFixed(2)} ${sy(Number(val)).toFixed(2)}`}).join(' ');return `<path d="${path}" fill="none" stroke="${COLORS[i%COLORS.length]}" stroke-width="2"/>`;}).join('');
 return `<svg class="plot" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><text x="18" y="19">${esc(yLabel)}</text>${marks}${paths}<text x="${width/2}" y="${height-5}" text-anchor="middle">${esc(xLabel)}</text></svg><div class="legend" style="margin-top:12px">${sets.map((s,i)=>`<span><i class="dot" style="background:${COLORS[i%COLORS.length]}"></i>${esc(s.name)}</span>`).join('')}</div>`;
}
function resultSummary(r){switch(r.analysis){case'modes':return `<div class="grid three">${r.modes.slice(0,3).map(m=>`<div class="metric"><strong>${fmt(m.frequency_ghz,4)} GHz</strong><small>Mode ${m.index} · α ${fmt(m.anharmonicity_mhz,2)} MHz</small></div>`).join('')}</div><div class="card"><h3>Eigenfrequencies and branch participation</h3><div class="scroll"><table><tr><th>Mode</th><th>GHz</th><th>α (MHz)</th><th>JJ participation</th></tr>${r.modes.map(m=>`<tr><td>${m.index}</td><td>${fmt(m.frequency_ghz,5)}</td><td>${fmt(m.anharmonicity_mhz,2)}</td><td>${Object.entries(m.junction_participation).map(([k,v])=>`${esc(k)}: ${fmt(v*100,1)}%`).join(' · ')}</td></tr>`).join('')}</table></div></div><div class="card"><h3>Qubit assignments</h3>${Object.entries(r.qubit_assignments).map(([id,q])=>`<p><b>${esc(id)}</b> → mode ${q.mode_index} · ${fmt(q.frequency_ghz,4)} GHz · α ${fmt(q.anharmonicity_mhz,2)} MHz</p>`).join('')}</div><div class="card"><h3>χ matrix (MHz) · diagonal = α</h3>${matrixHeat(r.chi_mhz)}</div>`;
 case'sparameters':return plotSeries('S-parameters',r.frequency_ghz,r.curves.map(c=>({name:c.name,data:c.db})),'Frequency (GHz)','dB')+ (r.touchstone_file?`<p><button data-act="touchstone">Download ${esc(r.touchstone_file)}</button></p>`:'');
 case'flux':return plotSeries('Flux',r.flux_phi0,r.frequency_ghz[0].map((_,i)=>({name:`Mode ${i}`,data:r.frequency_ghz.map(row=>row[i])})).slice(0,8),'Flux Φ / Φ₀','GHz');
 case'dynamics':return plotSeries('Dynamics',r.time_us,[{name:`P(e) ${r.qubit} · ${r.sequence}`,data:r.p_excited}],'Time (µs)','P(e)');
 case'duffing':return plotSeries('Duffing',r.frequency_ghz,[{name:'photons · low branch',data:r.photon_number_low_branch}],'Frequency (GHz)','n')+`<p class="hint">${r.real_root_count.filter(x=>x>1).length} points with multiple real roots; stability not verified.</p>`;
 case'yield':return `<div class="metric"><strong>${fmt(r.yield_fraction*100,2)}%</strong><small>Frequency yield: ${r.samples} samples, seed ${r.seed}</small></div><div class="card"><h3>Distribution by qubit</h3><div class="scroll"><table><tr><th>Qubit</th><th>Mean GHz</th><th>σ MHz</th><th>P05</th><th>P95</th></tr>${Object.entries(r.qubit_statistics).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${fmt(v.mean_ghz,4)}</td><td>${fmt(v.sigma_mhz,2)}</td><td>${fmt(v.p05_ghz,4)}</td><td>${fmt(v.p95_ghz,4)}</td></tr>`).join('')}</table></div></div>`;
 case'optimize':return `<div class="grid three"><div class="metric"><strong>${fmt(r.original_ej_ghz,3)} GHz</strong><small>Initial EJ</small></div><div class="metric"><strong>${fmt(r.proposed_ej_ghz,3)} GHz</strong><small>Proposed EJ</small></div><div class="metric"><strong>${fmt(r.after_error_mhz,3)} MHz</strong><small>Residual error</small></div></div><p>Qubit ${esc(r.qubit)}: f target ${fmt(r.target_ghz,4)} GHz, prediction ${fmt(r.predicted_ghz,4)} GHz.</p><button data-act="apply-proposal" class="primary">Apply proposal to draft (not layout)</button>`;
 case'loss_budget':return `<div class="scroll"><table><tr><th>Mode</th><th>GHz</th><th>Assumed Q</th><th>Estimated T1 (µs)</th></tr>${r.modes.map(m=>`<tr><td>${m.mode_index}</td><td>${fmt(m.frequency_ghz,4)}</td><td>${fmt(m.assumed_loaded_q,0)}</td><td>${fmt(m.estimated_t1_us,3)}</td></tr>`).join('')}</table></div>`;
 case'design_checks':return `<h3>${r.pass?'Checks completed':'Checks reported issues'}</h3>${r.issues.length?r.issues.map(x=>`<p class="alert"><b>${esc(x.severity)}</b> · ${esc(x.item)}: ${esc(x.message)}</p>`).join(''):'<div class="alert info">No warnings detected in the simplified electrical model.</div>'}`;
 default:return `<pre>${esc(JSON.stringify(r,null,2))}</pre>`;}}
function matrixHeat(matrix){if(!matrix||!matrix.length)return '';
 const max=Math.max(1,...matrix.flat().map(x=>Math.abs(x))),n=matrix.length;
 return `<div class="heatmap" style="--count:${n}"><div class="head">χ</div>${matrix.map((_,j)=>`<div class="head">${j}</div>`).join('')}${matrix.map((row,i)=>`<div class="head">${i}</div>${row.map((v,j)=>`<div style="background:rgba(96,222,208,${(Math.abs(v)/max*.65+.06).toFixed(3)})" title="χ ${i},${j}"><b>${fmt(v,2)}</b></div>`).join('')}`).join('')}</div>`;}
function renderResult(a){if(!S.result||S.result.analysis!==a){const active=S.project.jobs.find(j=>j.target==='lab:'+a&&['queued','running','cancel_requested'].includes(j.state));return `<div class="card"><h2>Results</h2>${active?`<div class="pill wait">${esc(active.state)}</div> <button data-act="view-job" data-id="${esc(active.id)}">Open job</button>`:'<p class="muted">Run an analysis or open an earlier job.</p>'}</div>`;}
 const r=S.result;return `<div class="card"><div class="row" style="justify-content:space-between"><h2>Results · ${esc(r.fidelity)}</h2><button data-act="download-result">↓ JSON</button></div><p class="hint">Job ${esc(S.resultJobId||'')} · Scientific data with explicitly declared model</p>${resultSummary(r)}<details style="margin-top:20px"><summary>Model assumptions and limitations</summary><ul>${(r.assumptions||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details></div>`;}
async function refreshUnified(){
 if(!S.project)return;
 const id=S.project.id;
 try{const r=await api(`/projects/${id}/physical/preview`);if(S.project?.id!==id)return;
  S.unifiedPreview=r;S.unifiedError=null;}
 catch(e){S.unifiedError=e.message;S.unifiedPreview=null;}
 if(S.view==='unified')render();
}
function unifiedSvg(){const g=S.unifiedPreview?.geometry;if(!g)return `<div class="alert">${esc(S.unifiedError||'Load the physical model preview.')}</div>`;
 const c=g.chip,w=c.x1-c.x0,h=c.y1-c.y0;
 let rects='';for(const [name,list] of Object.entries(g.metal)){
  const color=name==='ground'?'#98acc1':name.endsWith('.pad_a')?'#15b6ab':name.endsWith('.pad_b')?'#5489e8':name.endsWith('.resonator')?'#efb568':'#ab80ed';
  for(const r of list)rects+=`<rect x="${r.x0}" y="${-r.y1}" width="${r.x1-r.x0}" height="${r.y1-r.y0}" fill="${color}"/>`;
 }
 for(const [name,r] of Object.entries(g.ports))rects+=`<rect x="${r.x0}" y="${-r.y1}" width="${r.x1-r.x0}" height="${r.y1-r.y0}" fill="none" stroke="${name.endsWith('junction')?'#ff475f':'#f4d575'}" stroke-width="15"/>`;
 return `<svg viewBox="${c.x0} ${-c.y1} ${w} ${h}" role="img" aria-label="Unified parametric QPU geometry" style="width:100%;max-height:580px;background:#0e1c2d;border:1px solid #34516d;border-radius:10px">${rects}</svg><p class="hint">Gray ground, green/blue islands, gold resonators, purple lines; ports and junctions marked. SHA ${esc(g.geometry_sha256.slice(0,16))}…</p>`;
}
// Parametric physical design controls: all fields stay inside the versioned document.
const pJSON = path => esc(JSON.stringify(path));
function pField(title,path,value,kind='number',opts=null){
 let attr=`data-param-field="${pJSON(path)}"`;
 let element=opts?`<select ${attr}>${opts.map(o=>`<option value="${esc(o)}" ${o===value?'selected':''}>${esc(o)}</option>`).join('')}</select>`:
 (kind==='textarea'?`<textarea rows="2" ${attr} data-param-json="1">${esc(JSON.stringify(value))}</textarea>`:
 `<input ${attr} type="${kind==='number'?'number':'text'}" ${kind==='number'?'step="any"':''} value="${esc(value)}">`);
 return `<label class="field"><span>${esc(title)}</span>${element}</label>`;
}
const pRow=(name,id,html,kind,remove=true)=>`<div class="metric" style="margin-bottom:10px"><div class="row" style="justify-content:space-between"><b>${esc(name)}</b>${remove?`<button class="mini-btn warn" data-act="param-remove" data-kind="${kind}" data-index="${esc(id)}">Remove</button>`:''}</div><div class="fields">${html}</div></div>`;
function convergenceNotice(result){
 if(!result||typeof result.numerically_converged!=='boolean')return '';
 const state=result.numerically_converged?'Numerical change below tolerance':'Numerical convergence NOT achieved';
 return `<p class="alert info"><b>${state}</b> · A completed job does not prove mesh or boundary-condition validity. No automatic scientific qualification.</p>`;
}
function parametricView(){
 const s=S.doc.physical_qpu||S.unifiedPreview?.spec,g=S.unifiedPreview?.geometry,status=S.palaceStatus||{};
 const physicalJobs=S.project.jobs.filter(j=>j.mode==='physical');
 const jobs=physicalJobs.slice(0,7).map(j=>`<div class="row" style="justify-content:space-between;gap:10px;margin:7px 0"><span>${esc(j.target)} · ${esc(j.state)}</span><button class="mini-btn" data-act="view-job" data-id="${esc(j.id)}">Open</button></div>`).join('');
 const notes=`<p class="hint">Materials and thicknesses are parametric. The current Palace mesher supports one conducting sheet at z=0 with contiguous dielectrics below; other stack-ups remain exportable but are blocked before solving. Dolan/Manhattan masks describe process intent only, not verified shadow evaporation.</p>`;
 const layerNames=s.stack.filter(l=>l.role==='conductor').map(l=>l.id),materials=Object.keys(s.materials),qubitNames=s.qubits.map(q=>q.id);
 return `<div class="alert info"><b>Parametric source v0.7</b> · stack-up, materials, qubit geometries, physical couplers and CPW routes share one specification. Capacitances and couplings are <b>declared nominal values</b> until Palace extraction. Planar DRC is preliminary, not foundry sign-off.</div>
 <div class="actions">${!S.doc.physical_qpu?`<button data-act="param-create">Initialize model in project</button>`:''}${[1,2,4,9,16].map(n=>`<button data-act="param-preset" data-size="${n}">${n} Q</button>`).join('')}<button data-act="param-download-json">Specifica JSON</button><button data-act="param-raw-toggle">Editor JSON avanzato</button></div>
 <div class="grid"><section>
 <div class="card"><h2>2D layout / geometry checks</h2>${unifiedSvg()}<p>${g?`${g.components.length} qubit · ${g.couplers.length} coupler · ${g.routes.length} route · SHA ${esc(g.geometry_sha256.slice(0,16))}`:esc(S.unifiedError||'Preview not available')}</p><div class="actions"><button data-act="refresh-unified">Rebuild and validate</button><button data-act="physical-manifest" ${!g?'disabled':''}>QGeometry</button><button data-act="physical-gds" ${!g?'disabled':''}>GDS HOLD</button></div></div>
 <div class="card"><h2>Chip e regole</h2><div class="fields">${['width_um','height_um','edge_clearance_um'].map(k=>pField('Chip · '+k,['chip',k],s.chip[k])).join('')}${Object.entries(s.design_rules).map(([k,v])=>pField('Regola · '+k,['design_rules',k],v)).join('')}</div></div>
 <div class="card"><h2>Materiali</h2><div class="actions"><button data-act="param-add" data-kind="material">+ Materiale</button></div>${Object.entries(s.materials).map(([id,m])=>pRow(id,id,pField('Categoria',['materials',id,'kind'],m.kind,'text',['dielectric','superconductor','normal_metal'])+Object.entries(m).filter(([k])=>k!=='kind').map(([k,v])=>pField(k,['materials',id,k],v)).join(''),'material')).join('')}</div>
 <div class="card"><h2>Stack-up multilayer</h2><div class="actions"><button data-act="param-add" data-kind="layer">+ Layer</button></div>${s.stack.map((l,i)=>pRow(l.id,i,pField('Ruolo',['stack',i,'role'],l.role,'text',['dielectric','conductor','junction_mask'])+pField('Materiale',['stack',i,'material'],l.material,'text',materials)+pField('z0 µm',['stack',i,'z0_um'],l.z0_um)+pField('Spessore µm',['stack',i,'thickness_um'],l.thickness_um)+(['conductor','junction_mask'].includes(l.role)?pField('GDS layer',['stack',i,'gds_layer'],l.gds_layer):''),'layer')).join('')}${notes}</div>
 <div class="card"><h2>Josephson process</h2><div class="fields">${pField('Method',['junction_process','method'],s.junction_process.method,'text',['dolan','manhattan','generic'])}${pField('JJ layer',['junction_process','junction_layer_id'],s.junction_process.junction_layer_id,'text',s.stack.filter(l=>l.role==='junction_mask').map(l=>l.id))}${['orientation_deg','linewidth_um','overlap_um','undercut_um','lead_extension_um'].map(k=>pField(k,['junction_process',k],s.junction_process[k])).join('')}</div><p class="hint">The junction mask is a CAD process-intent marker. Evaporation angles, shadow overlap and contact resistance must be calibrated to the actual fabrication process.</p></div>
 </section><section>
 <div class="card"><h2>Qubit components</h2><div class="actions"><button data-act="param-add" data-kind="qubit">+ Qubit</button></div>${s.qubits.map((q,i)=>pRow(q.id,i,pField('Topology',['qubits',i,'family'],q.family,'text',['floating','cross','pocket',...Object.keys(s.libraries?.qubit_shapes||{})])+['x_um','y_um','width_um','height_um','rotation_deg','ej_ghz','cj_ff'].map(k=>pField(k,['qubits',i,k],q[k])).join(''),'qubit')).join('')}</div>
 <div class="card"><h2>Couplers / interqubit graph</h2><div class="actions"><button data-act="param-add" data-kind="coupler">+ Coupler</button></div>${s.couplers.map((c,i)=>pRow(c.id,i,pField('Type',['couplers',i,'kind'],c.kind,'text',['capacitive_pad','interdigitated','bus_cpw','tunable_squid','custom_rects'])+pField('Terminal A',['couplers',i,'a'],c.a,'text',qubitNames.flatMap(x=>['east','west','north','south'].map(y=>x+'.'+y)))+pField('Terminal B',['couplers',i,'b'],c.b,'text',qubitNames.flatMap(x=>['east','west','north','south'].map(y=>x+'.'+y)))+['gap_um','finger_width_um','nominal_c_ff'].map(k=>pField(k,['couplers',i,k],c[k])).join('')+(c.kind==='tunable_squid'?pField('EJ GHz',['couplers',i,'ej_ghz'],c.ej_ghz||8):''),'coupler')).join('')}<p class="hint">Capacitive coupling is geometric; bus_cpw creates a separate isolated conductor. Use CPW routing for other lines. A tunable SQUID is represented by a linear branch/marker, not a fabrication-qualified loop. Custom couplers and shape libraries can be defined in the advanced JSON editor.</p></div>
 <div class="card"><h2>Routing CPW</h2><div class="actions"><button data-act="param-add" data-kind="route">+ CPW</button></div>${s.routes.map((r,i)=>pRow(r.id,i,pField('Net',['routes',i,'net'],r.net,'text')+pField('Layer',['routes',i,'layer'],r.layer,'text',layerNames)+pField('Style',['routes',i,'style'],r.style,'text',['straight','manhattan','waypoints','meander'])+pField('Start [x,y]',['routes',i,'start_um'],r.start_um,'textarea')+pField('End [x,y]',['routes',i,'end_um'],r.end_um,'textarea')+pField('Waypoints [[x,y]]',['routes',i,'waypoints_um'],r.waypoints_um,'textarea')+pField('Bend preference',['routes',i,'bend_preference'],r.bend_preference,'text',['horizontal','vertical'])+['width_um','gap_um','meander_pitch_um','meander_depth_um'].map(k=>pField(k,['routes',i,k],r[k])).join(''),'route')).join('')}<p class="hint">Routes are defined per net and layer, with waypoints, orthogonal meanders, ground gaps and short-circuit DRC. Automatic A* routing and bridge/via routing are not yet supported.</p></div>
 <div class="card"><h2>Nominal circuit model</h2><p class="hint">Nominal values, not FEM-extracted. The graph includes explicitly declared coupler branches.</p><div class="fields">${Object.entries(s.nominal).map(([k,v])=>pField(k,['nominal',k],v)).join('')}</div><button data-act="adopt-physical" ${!g?'disabled':''}>Importa netlist nominale</button></div>
 <div class="card"><h2>Gmsh → Palace</h2><p class="hint">Gmsh ${status.gmsh_available?'available':'missing'} · Palace ${status.installed?'detected':'not detected'}. Unsupported stack-ups stop with explicit errors; no synthetic FEM results are substituted.</p>
 ${[['package','Parametric exports'],['mesh','Planar 3D mesh'],['electrostatic','Palace capacitance'],['capacitance','C-matrix CSV + checks'],['eigenmode','Eigenmodes'],['driven','S-parameters per port'],['convergence-eigenmode','FEM mode convergence (3 levels; intensive)'],['convergence-electrostatic','FEM capacitance convergence (3 levels; intensive)']].map(([stage,label])=>`<div class="row" style="justify-content:space-between;margin:9px 0"><span>${label}</span><button class="mini-btn" data-act="run-physical" data-stage="${stage}" ${S.busy||isViewer()||(stage!=='package'&&!status.gmsh_available)||(!['package','mesh'].includes(stage)&&!status.installed)?'disabled':''}>Job</button></div>`).join('')}
 </div><div class="card"><h2>Job history</h2>${jobs||'No jobs yet'}${S.job?.mode==='physical'?`<div class="metric">${esc(S.job.state)} · ${esc(S.job.target)}${S.physicalResult?`${convergenceNotice(S.physicalResult)}<pre>${esc(JSON.stringify(S.physicalResult,null,2))}</pre>`:''}</div>`:''}</div>
 </section></div><div id="param-json-editor" class="card" style="display:none"><h2>Specifica completa modificabile</h2><textarea id="param-json-source" rows="24" style="width:100%;font-family:monospace">${esc(JSON.stringify(s,null,2))}</textarea><div class="actions"><button data-act="param-json-apply">Applica JSON</button></div></div>`;
}
function unifiedView(){const g=S.unifiedPreview?.geometry,s=S.doc.physical_qpu||S.unifiedPreview?.spec,physicalJobs=S.project.jobs.filter(j=>j.mode==='physical');
 if(s?.schema_version===2)return parametricView();
 const initiated=Boolean(S.doc.physical_qpu);
 const nominal=S.unifiedPreview?.nominal_circuit;
 let fields='';
 if(initiated&&s){
  fields=`<div class="fields">${[['nominal_cq_ff','Initial Cq (fF)'],['nominal_cr_ff','Initial Cr (fF)'],['nominal_lr_nh','Initial Lr (nH)'],['nominal_cqr_ff','Initial Cqr (fF)'],['nominal_port_c_ff','RF port C (fF)'],['nominal_readout_qc','Nominal Qc']].map(([key,label])=>`<label class="field"><span>${label}</span><input type="number" step="any" min="0.0001" value="${Number(s[key])}" data-unified-num="${key}" ${isViewer()?'disabled':''}></label>`).join('')}</div>
    <h3>Giunzioni Josephson</h3><div class="fields">${s.junction_ej_ghz.map((x,i)=>`<label class="field"><span>Q${i} · EJ/h (GHz)</span><input data-unified-jj="ej:${i}" type="number" step="0.01" min="0.0001" value="${Number(x)}"></label><label class="field"><span>Q${i} · Cj (fF)</span><input data-unified-jj="cj:${i}" type="number" step="0.01" min="0.0001" value="${Number(s.junction_cj_ff[i])}"></label>`).join('')}</div>`;
 }
 const status=S.palaceStatus||{};
 const files=S.unifiedJobFiles||[];
 const links=files.filter(f=>f.startsWith('physical/')&&!f.includes('..')).slice(0,50).map(f=>`<a href="/api/projects/${encodeURIComponent(S.project.id)}/jobs/${encodeURIComponent(S.job?.id||'')}/files/${f.split('/').map(encodeURIComponent).join('/')}?download=1">${esc(f)}</a>`).join(' · ');
 return `<div class="alert info"><b>Unified physical source v0.6:</b> component parameters → positive metal geometry → annotated GDS → QGeometry → Gmsh/Palace groups → nominal circuit <b>with documented limitations</b>. The FEM model cannot infer C, g or losses without solver data: capacitance extraction requires a verified Palace job. The legacy 2/4-cell prototypes do not contain designed physical interqubit couplers.</div>
 <div class="actions"><button data-act="param-create">New parametric model v0.7 (materials, stack, couplers and CPW)</button></div><div class="grid"><section><div class="card"><h2>Parametric layout from a single specification</h2>${unifiedSvg()}
 <div class="actions"><button data-act="refresh-unified">Rebuild and validate model</button><button data-act="physical-manifest" ${!g?'disabled':''}>QGeometry JSON</button><button data-act="physical-gds" ${!g?'disabled':''}>Prototype GDS (HOLD)</button></div>
 <p class="hint">One geometry hash identifies GDS, net names, ports and physical groups. GDS does not include a qualified junction process geometry.</p></div>
 <div class="card"><h2>Reduced circuit from physical source</h2><p>Differential Q nodes and resonators correspond to geometry elements. The initial C/L values below are <b>user-declared, not FEM-extracted</b>.</p>
 ${nominal?`<p class="metric">${nominal.qubits.length} giunzioni · ${nominal.elements.length} elements · ${nominal.ports.length} RF ports</p>`:''}
 <button data-act="adopt-physical" ${!nominal||isViewer()?'disabled':''}>Copia circuito nominale nel Lab</button>
 <p class="hint">This is a one-way snapshot: subsequent edits to the conventional netlist do not update physical layout. FEM jobs operate on the versioned physical project.</p></div></section>
 <section><div class="card"><h2>Physical setup</h2><p>Select a prototype and edit junction properties; geometry and solver inputs will be regenerated.</p>
 <div class="actions">${[1,2,4].map(n=>`<button data-act="physical-preset" data-size="${n}" ${isViewer()?'disabled':''}>${n} transmon</button>`).join('')}</div>
 ${initiated?`<p class="hint">Active source · ${s.size} cells · ${g?.terminals.length||'?'} terminals · ${g?.feed_ports.length||'?'} RF ports</p>${fields}`:'<p class="alert">Create a physical specification by selecting the number of transmons. The existing netlist remains independent until explicitly imported.</p>'}
 </div><div class="card"><h2>Palace · pipeline da singola sorgente</h2>
 <p class="hint">Gmsh Python: ${status.gmsh_available?'available':'not installed'} · Palace: ${status.installed?'detected, not qualified':'not installed'} · backend ${esc(status.backend||'…')}. On Windows the setup is <code>WINDOWS-PALACE-SETUP.cmd</code>.</p>
 ${[['package','GDS + QGeometry + circuit + Palace JSON'],['mesh','Generate 3D FEM mesh'],['electrostatic','Palace: Maxwell Cij'],['capacitance','Palace: Cij + differential projection'],['eigenmode','Palace: linearized JJ modes + raw EPR'],['driven','Palace: one solve per RF excitation'],['convergence-eigenmode','FEM eigenmode convergence · 3 levels'],['convergence-electrostatic','FEM capacitance convergence · 3 levels']].map(([stage,label])=>`<div class="row" style="justify-content:space-between;gap:8px;margin-top:12px"><span>${esc(label)}</span><button class="mini-btn" data-act="run-physical" data-stage="${stage}" ${S.busy||!initiated||isViewer()||(stage!=='package'&&!status.gmsh_available)||( !['package','mesh'].includes(stage)&&!status.installed)?'disabled':''}>▶ Job</button></div>`).join('')}
 <p class="hint">Full-wave multi-cell simulations may be resource-intensive. No simulation is launched automatically by the Web UI.</p></div>
 <div class="card"><h2>Persistent results</h2>${physicalJobs.length?physicalJobs.slice(0,7).map(j=>`<div class="row" style="justify-content:space-between;gap:10px;margin:7px 0"><span>${esc(j.target)} · ${esc(j.state)}</span><button class="mini-btn" data-act="view-job" data-id="${esc(j.id)}">Open</button></div>`).join(''):'<p>No physical-model jobs have been run yet.</p>'}
 ${S.job?.mode==='physical'?`<div class="metric"><b>${esc(S.job.state)}</b> · ${esc(S.job.target)} · ${esc(S.job.error||'')}</div>${S.physicalResult?`${convergenceNotice(S.physicalResult)}<pre style="white-space:pre-wrap;max-height:300px;overflow:auto">${esc(JSON.stringify(S.physicalResult,null,2))}</pre>`:''}${links?`<div class="scroll" style="max-height:140px;overflow:auto">${links}</div>`:''}`:''}</div></section></div>`;
}

const FEM_ACTIONS=[['mesh','Gmsh: generate 3D mesh'],['solve:electrostatic','Palace: capacitance (Cij)'],['solve:eigenmode','Palace: 3D eigenmodes'],['solve:linearized','Palace: modes with linearized JJ'],['solve:driven','Palace: S(f) and RF fields']];
const FEM_FIELDS=[
 ['layout','pad_width_um','Pad larghezza µm'],['layout','pad_height_um','Pad altezza µm'],
 ['layout','pad_gap_um','Gap tra pad µm'],['layout','moat_um','Moat attorno al transmon µm'],
 ['layout','cpw_width_um','CPW larghezza µm'],['layout','cpw_gap_um','CPW gap µm'],
 ['layout','qubit_coupler_gap_um','Gap accoppiamento µm'],['layout','readout_length_um','Readout lunghezza µm'],
 ['em','mesh_min_um','Mesh edge min µm'],['em','mesh_max_um','Mesh max µm'],
 ['em','eigen_target_GHz','Eigen target GHz'],['em','modes','Numero eigenmode'],
 ['em','air_height_um','Altezza air box µm'],['em','kinetic_Ls_pH_per_square','Lk sheet pH/sq'] ];
async function refreshPalace(){if(!S.project)return;
 const project=S.project.id;
 const requests=await Promise.allSettled([api('/palace/status'),api(`/projects/${project}/palace/preview`)]);
 if(S.project?.id!==project)return;
 S.palaceStatus=requests[0].status==='fulfilled'?requests[0].value:null;
 S.femPreview=requests[1].status==='fulfilled'?requests[1].value:null;
 S.femError=requests[1].status==='rejected'?requests[1].reason.message:null;
 if(S.view==='palace')render();
}
function physicalSvg(){const g=S.femPreview?.geometry;if(!g)return `<div class="alert">${esc(S.femError||'Select Refresh preview and checks to verify the geometry.')}</div>`;
 const c=g.chip,w=c.x1-c.x0,h=c.y1-c.y0;const fill={ground:'#a7b8ce',pad_a:'#36c8b6',pad_b:'#668fea',resonator:'#ecb35c',feedline:'#c99fe8'};
 let rects='';for(const [net,boxes] of Object.entries(g.metal))for(const r of boxes){rects+=`<rect x="${r.x0}" y="${-r.y1}" width="${r.x1-r.x0}" height="${r.y1-r.y0}" fill="${fill[net]||'#fff'}"/>`;}
 for(const [name,r] of Object.entries(g.ports)){rects+=`<rect x="${r.x0}" y="${-r.y1}" width="${r.x1-r.x0}" height="${r.y1-r.y0}" fill="none" stroke="#ff4654" stroke-width="9"/>`;}
 return `<svg role="img" aria-label="Parametric physical metal geometry for FEM" viewBox="${c.x0} ${-c.y1} ${w} ${h}" style="width:100%;max-height:460px;background:#0c1d30;border-radius:12px;border:1px solid #34516d">${rects}</svg><div class="row" style="flex-wrap:wrap;gap:11px"><small>■ GND · ■ Q pads · ■ resonator · ■ feedline · red = ports</small><small>SHA ${esc(g.geometry_sha256.slice(0,13))}...</small></div>`;
}
function palaceCsvView(){const input=S.femCsv;
 if(!input||!input.rows?.length)return '';
 const labels=input.header;
 const all=input.rows.slice(0,8).map(row=>`<tr>${row.map(cell=>`<td>${esc(cell)}</td>`).join('')}</tr>`).join('');
 const table=`<div class="scroll"><table><tr>${labels.map(x=>`<th>${esc(x)}</th>`).join('')}</tr>${all}</table></div>`;
 const indices=labels.map((name,i)=>name.includes('S[')?i:-1).filter(i=>i>0).slice(0,4);
 let svg='';
 if(indices.length&&input.rows.length>2){
  const samples=input.rows.map(row=>row.map(Number)).filter(row=>Number.isFinite(row[0]));
  const available=indices.filter(i=>samples.every(x=>Number.isFinite(x[i])));
  if(samples.length>2&&available.length){
   const xs=samples.map(x=>x[0]),ys=samples.flatMap(x=>available.map(i=>x[i]));
   const lo=Math.min(...ys),hi=Math.max(...ys),xmin=Math.min(...xs),xmax=Math.max(...xs);
   const yspan=(hi-lo)||1,xspan=(xmax-xmin)||1;
   const colors=['#40c4bb','#f5b34c','#93a7f7','#ee8bcb'];
   svg=`<svg viewBox="0 0 600 245" role="img" aria-label="Grafico dati S calcolati da Palace, valori e unita come nel CSV originale" style="width:100%;max-height:260px;background:#0a192c;border-radius:8px">`+
    available.map((i,n)=>`<polyline fill="none" stroke="${colors[n]}" stroke-width="2" points="${samples.map(row=>`${(42+(row[0]-xmin)/xspan*535).toFixed(1)},${(215-(row[i]-lo)/yspan*184).toFixed(1)}`).join(' ')}"/>`).join('')+
    `<text x="4" y="12" fill="#d0d9ef" font-size="11">${esc(hi.toPrecision(4))}</text><text x="4" y="220" fill="#d0d9ef" font-size="11">${esc(lo.toPrecision(4))}</text><text x="40" y="239" fill="#d0d9ef" font-size="11">${esc(xmin.toPrecision(5))}</text><text x="515" y="239" fill="#d0d9ef" font-size="11">${esc(xmax.toPrecision(5))}</text></svg><p class="hint">${available.map((i,n)=>`<span style="color:${colors[n]}">${esc(labels[i])}</span>`).join(' · ')} · scala originale Palace, none conversione in dB implicita.</p>`;
  }
 }
 return `<div class="card"><h2>Solver FEM data · ${esc(input.file)}</h2>${svg}${table}<p class="hint">Preview of first ${Math.min(8,input.rows.length)} rows out of ${input.rows.length}. For quantitative analysis, download the original CSV and verify the Palace log.</p></div>`;
}
async function loadFemCsv(job){S.femCsv=null;
 if(job.state!=='succeeded')return;
 const kind=job.target.startsWith('solve:')?job.target.slice(6):null;
 const expected={electrostatic:'terminal-C.csv',eigenmode:'eig.csv',linearized:'eig.csv',driven:'port-S.csv'}[kind];
 if(!expected)return;
 const path=`run/em/${kind}/${expected}`;
 try{
  const r=await fetch(`/api/projects/${S.project.id}/jobs/${job.id}/files/${path.split('/').map(encodeURIComponent).join('/')}`,{credentials:'same-origin'});
  if(!r.ok)return;
  const csv=await r.text();
  const lines=csv.trim().split(/\r?\n/).filter(Boolean).slice(0,1501).map(line=>line.split(',').map(x=>x.trim().replace(/^"|"$/g,'')));
  if(lines.length<2||lines[0].length<2)return;
  S.femCsv={file:path,header:lines[0],rows:lines.slice(1).filter(row=>row.length===lines[0].length)};
 }catch(err){console.warn('Palace CSV preview:',err.message);}
}
function palaceView(){const status=S.palaceStatus||{};const cfg=S.doc.config||{};
 const femjobs=S.project.jobs.filter(j=>j.mode==='fem');const loading=!S.palaceStatus?'Backend status not yet queried':status.message||'Unknown status';
 const editable=!isViewer();let form=FEM_FIELDS.map(([section,key,label])=>`<label class="field"><span>${esc(label)}</span><input data-fem="${section}.${key}" type="number" step="any" ${editable?'':'disabled'} value="${esc(cfg[section]?.[key]??'')}"></label>`).join('');
 const files=S.femJobFiles.filter(x=>x.startsWith('run/em/')||x.startsWith('run/layout/')).slice(0,80);
 return `<div class="alert"><b>MODEL LIMITATION:</b> the multi-qubit Quantum Lab circuit and this single-transmon FEM geometry are <b>distinct models</b>. They are not automatically synchronized. The mask remains in fabrication HOLD pending DRC, EM correlation and process qualification.</div>
 <div class="grid"><section><div class="card"><h2>Shared parametric geometry · QComponent-style</h2>${physicalSvg()}<p class="hint">FEM and physical GDS share the layout generator and net labels. This geometry represents the original SQE single-transmon prototype.</p><button data-act="refresh-palace">Refresh preview and checks</button></div>
 <div class="card"><h2>Dimensions and stack-up · source of truth</h2><p class="muted">These parameters update the versioned physical specification, not the nominal multi-QPU schematic values.</p><div class="fields">${form}</div><p class="hint">Edit substrate, materials and process settings in Studio. Palace configurations are regenerated per job from immutable revisions.</p><button data-act="refresh-palace">Verify after saving</button></div></section>
 <section><div class="card"><h2>Runtime Palace</h2><span class="pill ${status.installed?'':'wait'}">${status.installed?'DETECTED · UNQUALIFIED':'NOT DETECTED'}</span><p>${esc(loading)}</p><div class="metric">Backend: <b>${esc(status.backend||'...')}</b> · distro: <b>${esc(status.configured_distro||'...')}</b><br>Gmsh Python: <b>${status.gmsh_available?'available':'missing'}</b> · Quantum Metal: <b>${status.quantum_metal_available?'in Web environment':'separate optional environment'}</b></div><p class="hint">On Windows: run <code>WINDOWS-PALACE-SETUP.cmd</code> from the extracted folder. Web controls do not install software or run privileged commands.</p><div class="actions"><button data-act="refresh-palace">Recheck</button><a href="https://awslabs.github.io/palace/stable/install/" target="_blank" rel="noopener">Official Palace manual</a></div></div>
 <div class="card"><h2>EM workflow · persistent jobs</h2><div class="fields"><label class="field"><span>MPI ranks (1–16)</span><input data-palace-ranks="1" type="number" min="1" max="16" value="${S.palaceRanks}"></label></div>${FEM_ACTIONS.map(([a,label])=>`<div class="row" style="justify-content:space-between;margin-top:12px;gap:8px"><span>${esc(label)}</span><button class="mini-btn" data-act="run-fem" data-stage="${esc(a)}" ${S.busy||!editable||(!status.gmsh_available)|| (a!=='mesh'&&!status.installed)?'disabled':''}>▶ Start</button></div>`).join('')}<p class="hint">Dependent stages automatically generate layout, mesh and JSON inputs. Queued jobs need a running worker; mesh generation can be resource-intensive. If a job stays queued, open System & Diagnostics to inspect queue health. Eigenmode and driven analyses require functioning Gmsh and Palace installations.</p></div>
 <div class="card"><h2>FEM jobs and result files</h2>${femjobs.slice(0,9).map(j=>`<div class="row" style="justify-content:space-between;margin:9px 0"><span>${esc(j.target)} · ${Math.round(Math.max(0,Date.now()/1000-j.created))}s elapsed · <span class="pill ${j.state==='succeeded'?'':'wait'}">${esc(j.state)}</span></span><button class="mini-btn" data-act="view-job" data-id="${esc(j.id)}">Open</button></div>`).join('')||'<p class="hint">No jobs yet FEM avviato.</p>'}${S.job?.mode==='fem'?`<p class="hint">Job ${esc(S.job.id.slice(0,12))}: ${esc(S.job.state)} · stage ${esc(S.job.stage||'not started')} · ${esc(S.job.error||'')}</p><button class="mini-btn" data-act="fem-logs">View worker / solver log</button>${['queued','running','cancel_requested'].includes(S.job.state)?`<button class="mini-btn" data-act="cancel-fem">Cancel job</button>`:''}${S.femLog?`<pre style="max-height:230px;overflow:auto">${esc(S.femLog)}</pre>`:''}`:''}${files.length?`<div class="scroll"><table>${files.map(f=>`<tr><td><code>${esc(f)}</code></td><td><a href="/api/projects/${encodeURIComponent(S.project.id)}/jobs/${encodeURIComponent(S.job.id)}/files/${f.split('/').map(encodeURIComponent).join('/')}?download=1">Download</a></td></tr>`).join('')}</table></div>`:''}</div>
 ${palaceCsvView()}
 <div class="card"><h2>Quantum Metal interoperability</h2><p>Workflow compatible in concept with <b>QDesign / QComponent</b>: named components, shared geometry, layers, ports, parameters and GDS. Quantum Metal is optional in <code>.venv-metal</code>, installed using <code>WINDOWS-QUANTUM-METAL-SETUP.cmd</code>. This is not a native Quantum Metal-to-Palace renderer.</p><div class="actions"><button data-act="download-metal-manifest">Export QGeometry JSON</button><a href="https://qiskit-community.github.io/qiskit-metal/installation.html" target="_blank" rel="noopener">Quantum Metal · installation</a></div><p class="hint">Run <code>.venv-metal\Scripts\python.exe scripts\quantum_metal_bridge.py sqe-qmetal-qgeometry.json</code>. Exports named positive-metal polygons, not fully routed pins or Palace meshes.</p></div></section></div>`;
}
function historyView(){const jobs=S.project.jobs.filter(j=>j.mode==='lab');return `<div class="card"><h2>Revisions and persistent jobs</h2><p class="muted">Jobs are linked to immutable revisions. Files remain available after closing the browser. The job queue moves with the compute installation.</p><div class="scroll"><table><tr><th>Date</th><th>Job</th><th>Analysis</th><th>Status</th><th>Revision</th><th>Details</th></tr>${jobs.map(j=>`<tr><td>${new Date(j.created*1000).toLocaleString('en-US')}</td><td><code>${j.id.slice(0,9)}</code></td><td>${esc(j.target.replace('lab:',''))}</td><td><span class="pill ${j.state==='succeeded'?'':'wait'}">${esc(j.state)}</span></td><td><code>${esc(j.revision_id.slice(0,9))}</code></td><td><button class="mini-btn" data-act="view-job" data-id="${esc(j.id)}">Open</button></td></tr>`).join('')}</table></div>${S.job&&S.job.state!=='succeeded'?`<h3>Job status</h3><pre>${esc(JSON.stringify({id:S.job.id,state:S.job.state,stage:S.job.stage,error:S.job.error},null,2))}</pre>`:''}</div>`;}
function roadmapView(){return `<div class="grid"><div><div class="card"><h2>Available components</h2><ul><li>SPICE-like netlist of C, L, R, JJ, SQUID and capacitive ports.</li><li>Reduced-order electromagnetic analysis, eigenvalues, JJ branch participation, χ and Kerr.</li><li>S-parameter scattering, Touchstone export, flux sweep, Bloch Rabi/Ramsey/echo/T1.</li><li>One-mode Duffing, Q budget, yield and EJ optimization.</li><li>Revisions, audit, users, persistent jobs, project capsules and GDSII <em>concept-only</em>.</li><li>Original workflow: Gmsh → external Palace FEM, electrostatics/eigenmodes in a separate pipeline.</li></ul></div><div class="card"><h2>Planned advanced integrations</h2><ul><li>Connected QPDK/Quantum Metal geometries and verified CPW routing.</li><li>Package-aware 3D mesh with multilayer stack-up and flip-chip, bumps e vias.</li><li>FEM/PBC/S-parameters solver, qualified open-source MoM and openEMS FDTD adapter.</li><li>Black-box quantization from EM Y/Z and EPR participation extracted from field energy.</li><li>Multi-harmonic-balance Newton solver for Josephson networks, JTWPA, SNAIL and snake circuits.</li><li>Material calibration, Lk(T), TLS/Purcell losses, correlated variation, DRC and foundry rule decks.</li><li>Remote multi-node workers, SLURM/PBS, shared/object storage and PostgreSQL.</li></ul></div></div><section><div class="card"><h2>Deployment model</h2><pre>Browser Windows → SQE Studio API / SQLite WAL / job queue
       │                              │
       ├── Local preview ───────────┴── SciPy / NumPy
       │
       └── Worker locale → future Linux HPC worker
                                ├── Gmsh / Palace FEM
                                ├── Quantum Metal / QPDK
                                └── QuTiP / scqubits
</pre><p>The current queue is single-host. Moving the whole service to a server preserves the UI; dispatching work across hosts requires an additional scheduler/database adapter.</p></div></section></div>`;}
async function run(analysis){if(isViewer())throw Error('Read-only access');await save();const revision=await api(`/projects/${S.project.id}/revisions`,'POST',{
 note:'Quantum Lab / '+analysis,draft_version:S.project.draft_version});
 S.project.revisions.unshift({id:revision.id});
 const created=await api(`/projects/${S.project.id}/jobs`,'POST',{revision_id:revision.id,target:'lab:'+analysis,
 mode:'lab',cpus:1,memory_gb:2,options:{analysis_options:S.options[analysis]||{}}});
 S.result=null;S.resultJobId=null;S.job={id:created.id,state:'queued',target:'lab:'+analysis};S.busy=true;
 S.project.jobs.unshift({id:created.id,target:'lab:'+analysis,mode:'lab',state:'queued',created:Date.now()/1000,revision_id:revision.id});
 render();notify('Job '+created.id.slice(0,8)+' queued. Results will remain available in the project.');}
async function loadJob(id,shouldRender=true){const job=await api(`/projects/${S.project.id}/jobs/${id}`);S.job=job.job;
 if(S.job.mode==='physical'){S.view='unified';S.unifiedJobFiles=job.files||[];S.physicalResult=null;
  if(S.job.state==='succeeded'){const f=await fetch(`/api/projects/${S.project.id}/jobs/${id}/files/physical/result.json`,{credentials:'same-origin'});if(f.ok)S.physicalResult=await f.json();}
  if(!S.unifiedPreview)await refreshUnified();}
 if(S.job.mode==='fem'){S.view='palace';S.femJobFiles=job.files||[];await loadFemCsv(S.job);if(!S.palaceStatus)await refreshPalace();}
 if(S.job.mode==='lab'){const a=S.job.target.split(':')[1];if(INFO[a])S.view=a;
 if(S.job.state==='succeeded'){
 const r=await fetch(`/api/projects/${S.project.id}/jobs/${id}/files/lab/result.json`,{credentials:'same-origin'});
 if(!r.ok)throw Error('Result is not available yet: HTTP '+r.status);S.result=await r.json();S.resultJobId=id;
 }else{S.result=null;S.resultJobId=null;}}
 if(shouldRender)render();}
async function poll(){if(!S.project||!S.user)return;
 const live=S.project.jobs.filter(j=>['queued','running','cancel_requested'].includes(j.state));
 if(!live.length){if(S.busy){S.busy=false;render();}return;}
 try{const detail=await api('/projects/'+S.project.id);S.project.jobs=detail.jobs;S.project.revisions=detail.revisions;
 if(S.job){const updated=S.project.jobs.find(j=>j.id===S.job.id);if(updated){S.job=updated;if(['succeeded','failed','cancelled','interrupted'].includes(updated.state))await loadJob(updated.id,false);}}
 S.busy=S.project.jobs.some(j=>['lab','fem','physical'].includes(j.mode)&&['running','queued','cancel_requested'].includes(j.state));
 if(document.activeElement?.tagName!=='INPUT'&&document.activeElement?.tagName!=='TEXTAREA'&&document.activeElement?.tagName!=='SELECT')render();
 }catch(e){console.warn('Lab job refresh:',e.message);}}
function downloadText(name,contents,type='application/json'){const blob=new Blob([contents],{type});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),5000);}
function setNested(path,value){const keys=path.split('.');let obj=S.design;
 if(keys[0]==='port'){obj=S.design.ports[Number(keys[1])];keys.splice(0,2)}
 else if(keys[0]==='qubit'){obj=S.design.qubits[Number(keys[1])];keys.splice(0,2)}
 for(const key of keys.slice(0,-1))obj=obj[key]??={};obj[keys.at(-1)]=value;
}
document.addEventListener('change',async e=>{if(!S.project)return;
 try{const n=e.target;if(n.id==='project-choice'){await save();await loadProject(n.value);return;}
 if(n.dataset.paramField){
  if(isViewer())throw Error('Read-only access');
  if(!S.doc.physical_qpu || S.doc.physical_qpu.schema_version!==2)throw Error('Create a parametric model first');
  const path=JSON.parse(n.dataset.paramField),v=n.dataset.paramJson==='1'?JSON.parse(n.value):n.type==='number'?Number(n.value):n.value;
  if(typeof v==='number'&&!Number.isFinite(v))throw Error('Valore numerico non valido');
  let target=S.doc.physical_qpu;for(const key of path.slice(0,-1))target=target[key];
  target[path.at(-1)]=v;setDirty();return;
 }
 if(n.dataset.unifiedNum){if(isViewer()||!S.doc.physical_qpu)return;const value=Number(n.value);if(!Number.isFinite(value)||value<=0)throw Error('Parameter fisico deve essere positivo');S.doc.physical_qpu[n.dataset.unifiedNum]=value;setDirty();return;}
 if(n.dataset.unifiedJj){if(isViewer()||!S.doc.physical_qpu)return;const [kind,idx]=n.dataset.unifiedJj.split(':');const v=Number(n.value);if(!Number.isFinite(v)||v<=0)throw Error('JJ EJ/Cj deve essere positivo');S.doc.physical_qpu[kind==='ej'?'junction_ej_ghz':'junction_cj_ff'][Number(idx)]=v;setDirty();return;}
 if(n.dataset.palaceRanks){const nval=Number(n.value);if(!Number.isInteger(nval)||nval<1||nval>16)throw Error('MPI ranks: 1–16');S.palaceRanks=nval;return;}
 if(n.dataset.fem){if(isViewer())return;const [sec,key]=n.dataset.fem.split('.');const value=Number(n.value);if(!Number.isFinite(value))throw Error('Parameter numerico non valido');S.doc.config[sec][key]=value;setDirty();return;}
 if(n.dataset.opt){const [analysis,key]=n.dataset.opt.split(':');const v=n.type==='number'?Number(n.value):n.value;S.options[analysis][key]=v;return;}
 if(isViewer())return;
 if(n.dataset.element){const el=S.design.elements[S.selection];const k=n.dataset.element,v=n.value;
 el[k]=v;if(k==='kind'){delete el.value;delete el.ej_ghz;delete el.asymmetry;delete el.flux_phi0;
 if(v==='JJ'||v==='SQUID'){el.ej_ghz=13;if(v==='SQUID'){el.asymmetry=.12;el.flux_phi0=0;}}else el.value=v==='C'?70:v==='L'?8:50;}
 setDirty();render();return;}
 if(n.dataset.value){setNested(n.dataset.value,Number(n.value));setDirty();return;}
 }catch(err){notify(err.message);}});
document.addEventListener('click',async e=>{const button=e.target.closest('[data-act]');if(!button)return;
 try{const action=button.dataset.act;
 if(action==='section'){await save();S.view=button.dataset.id;render();if(S.view==='palace')await refreshPalace();if(S.view==='unified'){await refreshUnified();S.palaceStatus=await api('/palace/status');render();}}
 else if(action==='new-project'){const r=await api('/projects','POST',{name:'Quantum Lab / QPU design'});S.projects=await api('/projects');await loadProject(r.id);}
 else if(action==='preset'){if(isViewer())return;if(!confirm('Replace the current netlist with a QPU template? Save a checkpoint first if needed.'))return;
 S.design=await api('/quantumlab/preset?size='+button.dataset.size);S.selection=0;setDirty();render();}
 else if(action==='select-element'){S.selection=Number(button.dataset.index);render();}
 else if(action==='add-element'){const base=S.design.elements[0];const id='Cextra'+Date.now().toString(36).slice(-5);
 S.design.elements.push({id,kind:'C',a:base.a,b:base.b==='0'?(nodelist().find(x=>x!==base.a)||'0'):base.b,value:.5});S.selection=S.design.elements.length-1;setDirty();render();}
 else if(action==='remove-element'){const el=S.design.elements[S.selection];if(S.design.qubits.some(q=>q.junction===el.id))throw Error('A junction assigned to a qubit cannot be deleted');if(S.design.elements.length===1)throw Error('At least one element is required');S.design.elements.splice(S.selection,1);S.selection=0;setDirty();render();}
 else if(action==='convert-squid'){const el=S.design.elements[S.selection];el.kind='SQUID';el.asymmetry=.10;el.flux_phi0=0;setDirty();render();}
 else if(action==='add-port'){if(S.design.ports.length>=8)throw Error('Maximum of eight ports');S.design.ports.push({id:'P'+(S.design.ports.length+1),node:nodelist()[0],z0_ohm:50,coupling_ff:1.5});setDirty();render();}
 else if(action==='remove-port'){S.design.ports.splice(Number(button.dataset.index),1);setDirty();render();}
 else if(action==='save'){await save();notify('Project draft saved');}
 else if(action==='save-revision'){await save();const rev=await api(`/projects/${S.project.id}/revisions`,'POST',{note:prompt('Revision note','Design QPU')||'Design QPU',draft_version:S.project.draft_version});S.project.revisions.unshift({id:rev.id});notify('Checkpoint created: '+rev.id.slice(0,8));render();}
 else if(action==='export'){await save();location.href=`/api/projects/${S.project.id}/export`;}
 else if(action==='run'){await run(button.dataset.analysis);}
 else if(action==='param-create'){
  if(isViewer())throw Error('Read-only access');
  if(S.doc.physical_qpu && !confirm('Create a new parametric model? This replaces the current physical model. Save a revision first.'))return;
  S.doc.physical_qpu=await api('/quantumlab/parametric-preset?size=2');setDirty();await save();await refreshUnified();render();
 }
 else if(action==='param-preset'){
  if(isViewer())throw Error('Read-only access');
  if(!confirm('Replace the current parametric topology with a new template?'))return;
  const sz=Number(button.dataset.size);S.doc.physical_qpu=await api('/quantumlab/parametric-preset?size='+sz);
  setDirty();await save();await refreshUnified();render();
 }
 else if(action==='param-download-json')downloadText('sqe-physical-v07.json',JSON.stringify(S.doc.physical_qpu,null,2));
 else if(action==='param-raw-toggle'){const el=$('#param-json-editor');el.style.display=el.style.display==='none'?'block':'none';}
 else if(action==='param-json-apply'){
  if(isViewer())throw Error('Read-only access');
  const candidate=JSON.parse($('#param-json-source').value);
  if(candidate.schema_version!==2)throw Error('The JSON specification requires schema_version=2');
  S.doc.physical_qpu=candidate;setDirty();await save();await refreshUnified();render();
 }
 else if(action==='param-add'){
  if(isViewer())throw Error('Read-only access');const x=S.doc.physical_qpu,k=button.dataset.kind;
  const id=prompt('ID for new '+k, k+String(Date.now()).slice(-4));if(!id)return;
  if(k==='material'){x.materials[id]={kind:'dielectric',epsilon_r:4,loss_tangent:0};}
  else if(k==='layer'){x.stack.push({id,role:'dielectric',material:Object.keys(x.materials).find(k=>x.materials[k].kind==='dielectric'),z0_um:-525,thickness_um:1});}
  else if(k==='qubit'){
   const q=structuredClone(x.qubits[0]);Object.assign(q,{id,junction_id:'J'+id,x_um:q.x_um+1800,y_um:q.y_um});x.qubits.push(q);
  }
  else if(k==='coupler'){
   if(x.qubits.length<2)throw Error('Add at least two qubits');
   x.couplers.push({id,kind:'capacitive_pad',a:x.qubits[0].id+'.east',b:x.qubits[1].id+'.west',gap_um:20,finger_width_um:38,nominal_c_ff:.35});
  }
  else if(k==='route'){
   const layer=x.stack.find(l=>l.role==='conductor').id;
   x.routes.push({id,net:id,layer,style:'manhattan',start_um:[-1200,-1000],end_um:[1200,-1000],waypoints_um:[],width_um:12,gap_um:7,bend_preference:'horizontal',meander_pitch_um:180,meander_depth_um:120});
  }
  setDirty();render();
 }
 else if(action==='param-remove'){
  if(isViewer())throw Error('Read-only access');const x=S.doc.physical_qpu,k=button.dataset.kind,i=button.dataset.index;
  if(!confirm('Delete '+k+' '+i+'?? Any dependent references must also be updated.'))return;
  if(k==='material')delete x.materials[i];else x[k==='layer'?'stack':k+'s'].splice(Number(i),1);
  setDirty();render();
 }
 else if(action==='physical-preset'){
  if(isViewer())throw Error('Read-only');
  const size=Number(button.dataset.size);if(![1,2,4].includes(size))throw Error('Unsupported QPU size');
  const base=structuredClone(S.doc.physical_qpu||S.unifiedPreview?.spec);
  if(!base)throw Error('Preview is not available yet');
  base.size=size;const ej=base.junction_ej_ghz[0]||14.5,cj=base.junction_cj_ff[0]||2.5;
  base.junction_ej_ghz=Array.from({length:size},(_,i)=>base.junction_ej_ghz[i]||ej+i*0.25);
  base.junction_cj_ff=Array.from({length:size},(_,i)=>base.junction_cj_ff[i]||cj);
  S.doc.physical_qpu=base;setDirty();await save();await refreshUnified();notify('Physical specification: '+size+' transmons saved');
 }
 else if(action==='refresh-unified'){await save();await refreshUnified();notify(S.unifiedError||'The physical model was regenerated from the current revision');}
 else if(action==='physical-manifest'){await save();location.href=`/api/projects/${S.project.id}/physical/manifest`;}
 else if(action==='physical-gds'){await save();location.href=`/api/projects/${S.project.id}/physical/gds`;notify('Review-only GDS: not a fabrication-qualified mask set.');}
 else if(action==='adopt-physical'){if(isViewer())throw Error('Read-only');await save();await refreshUnified();S.design=structuredClone(S.unifiedPreview.nominal_circuit);setDirty();await save();notify('NOMINAL circuit derived from geometry/JJ. Capacitances and inductances have not been extracted from FEM.');}
 else if(action==='run-physical'){
  if(isViewer()||S.busy)throw Error('A job is already running or the project is read-only');await save();
  const stage=button.dataset.stage;
  if(!['package','mesh','electrostatic','capacitance','eigenmode','driven'].includes(stage))throw Error('Unsupported stage');
  const revision=await api(`/projects/${S.project.id}/revisions`,'POST',{note:'Unified physical QPU / '+stage,draft_version:S.project.draft_version});
  S.project.revisions.unshift({id:revision.id});
  const r=await api(`/projects/${S.project.id}/jobs`,'POST',{revision_id:revision.id,target:'physical:'+stage,mode:'physical',cpus:S.palaceRanks,memory_gb:2,options:{ranks:S.palaceRanks}});
  S.job={id:r.id,mode:'physical',target:'physical:'+stage,state:'queued'};S.busy=true;S.unifiedJobFiles=[];S.physicalResult=null;
  S.project.jobs.unshift({id:r.id,target:'physical:'+stage,mode:'physical',state:'queued',created:Date.now()/1000,revision_id:revision.id});
  render();notify('Physical job queued: '+r.id.slice(0,8));
 }
 else if(action==='refresh-palace'){await save();await refreshPalace();notify(S.femError||'Geometry validated / backend status updated');}
 else if(action==='run-fem'){
   if(isViewer())throw Error('Read-only access');if(S.busy)throw Error('Wait for the previous job');
   await save();const stage=button.dataset.stage;
   if(!FEM_ACTIONS.some(x=>x[0]===stage))throw Error('Invalid workflow stage');
   const revision=await api(`/projects/${S.project.id}/revisions`,'POST',{note:'FEM Palace / '+stage,draft_version:S.project.draft_version});
   S.project.revisions.unshift({id:revision.id});
   const r=await api(`/projects/${S.project.id}/jobs`,'POST',{revision_id:revision.id,target:stage,mode:'fem',cpus:S.palaceRanks,memory_gb:2,
    options:{ranks:S.palaceRanks}});
   S.job={id:r.id,mode:'fem',target:stage,state:'queued'};S.femLog=null;S.femJobFiles=[];S.femCsv=null;S.busy=true;
   S.project.jobs.unshift({id:r.id,target:stage,mode:'fem',state:'queued',created:Date.now()/1000,revision_id:revision.id});
   render();notify('Palace FEM job '+r.id.slice(0,8)+' queued; monitor the status and results below.');
 }
 else if(action==='cancel-fem'){if(S.job?.id&&confirm('Request cancellation of this FEM job?')){await api(`/jobs/${S.job.id}/cancel`,'POST',{});notify('Cancellation requested.');}}
 else if(action==='fem-logs'){if(S.job?.id){const r=await api(`/projects/${S.project.id}/jobs/${S.job.id}/logs`);S.femLog=r.text;render();}}
 else if(action==='view-job'){await loadJob(button.dataset.id);}
 else if(action==='download-result'){if(S.result)downloadText('quantumlab-'+S.result.analysis+'.json',JSON.stringify(S.result,null,2));}
 else if(action==='download-netlist'){downloadText('qpu-netlist.json',JSON.stringify(S.design,null,2));}
 else if(action==='download-metal-manifest'){await save();location.href=`/api/projects/${S.project.id}/quantum-metal/manifest`;notify('QGeometry manifest exported from FEM layout, not the multi-QPU netlist');}
 else if(action==='download-gds'){await save();location.href=`/api/projects/${S.project.id}/quantumlab/gds`;notify('Concept-only GDS: not for fabrication without full layout, DRC and qualification');}
 else if(action==='touchstone'){if(S.result?.touchstone_file&&S.resultJobId)location.href=`/api/projects/${S.project.id}/jobs/${S.resultJobId}/files/lab/${S.result.touchstone_file}?download=1`;}
 else if(action==='apply-proposal'){if(!S.result?.proposed_design||!confirm('Apply optimized EJ to the draft netlist only?'))return;S.design=structuredClone(S.result.proposed_design);setDirty();render();notify('Proposal applied to the electrical draft, not the layout');}
 }catch(err){notify(err.message);}});
let dragging=null;
document.addEventListener('pointerdown',e=>{if(isViewer()||S.view!=='schematic'&&S.view!=='layout')return;
 const node=e.target.closest('.node[data-node]');if(!node)return;
 const svg=node.closest('svg');if(!svg)return;
 dragging={svg,node,name:node.dataset.node};node.setPointerCapture(e.pointerId);});
document.addEventListener('pointermove',e=>{if(!dragging)return;
 const svg=dragging.svg;if(!svg.isConnected){dragging=null;return;}
 const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const inv=svg.getScreenCTM()?.inverse();if(!inv)return;
 const at=p.matrixTransform(inv);const x=Math.max(30,Math.min(svg.viewBox.baseVal.width-30,at.x)),y=Math.max(30,Math.min(svg.viewBox.baseVal.height-30,at.y));
 S.design.positions??={};S.design.positions[dragging.name]=[Math.round(x),Math.round(y)];dragging.node.setAttribute('transform',`translate(${x},${y})`);});
document.addEventListener('pointerup',()=>{if(!dragging)return;dragging=null;setDirty();render();});
window.addEventListener('beforeunload',e=>{if(S.dirty){e.preventDefault();e.returnValue='';}});
setInterval(poll,2200);init();
