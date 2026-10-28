'use strict';
const app=document.getElementById('app');
const safe=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const s={csrf:null,user:null,catalog:null,selected:'native-1q',preview:null,run:null,error:null,busy:false,codeConsent:false,solverConsent:false};
async function api(path,method='GET',body=null,binary=false){
 const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:method==='GET'?{}:{'X-CSRF-Token':s.csrf,...(binary?{'Content-Type':'application/zip'}:{'Content-Type':'application/json'})},body:method==='GET'?undefined:binary?body:JSON.stringify(body||{})});
 const result=await response.json();if(!response.ok)throw Error(result.error||`HTTP ${response.status}`);return result;
}
function date(v){if(!v)return 'Not finished';const d=new Date(v);return isNaN(d.getTime())?'Unknown date':d.toLocaleString();}
function render(){
 if(!s.user){app.innerHTML=`<section class="intro"><div class="eyebrow">RESEARCH EXPERIMENTS</div><h1>Sign in to run experiments</h1><p>Open the main workspace and sign in as a local administrator.</p><a class="button primary" href="/">Open sign-in</a></section>`;return;}
 const projects=s.catalog?.projects||[],preview=s.preview,run=s.run;
 const active=s.catalog?.runs?.some(r=>['queued','running'].includes(r.state));
 const opts=projects.map(p=>`<option value="${safe(p.id)}" ${p.id===s.selected?'selected':''}>${safe(p.name)} (${safe(p.type)})</option>`).join('');
 const steps=preview?.plan?.steps||[],engines=s.catalog?.engines||{};
 app.innerHTML=`<section class="intro"><div class="eyebrow">LOCAL ADMINISTRATOR · RELEASE 0.16.0</div><h1>Research Experiments</h1><p>Select a bundled project or import your own workflow ZIP. Run tests and multi-engine experiments entirely from the browser, then download one support archive for review or troubleshooting.</p></section>
 ${s.error?`<div class="notice error" role="alert">${safe(s.error)}</div>`:''}
 <div class="experiment-layout"><div>
 <section class="panel"><h2>1. Select a research project</h2><label class="field-label" for="project">Workflow project</label><select id="project">${opts}</select>
 <div class="buttons"><button id="import">Import project ZIP</button><input type="file" accept=".zip,application/zip" id="project-upload"><a class="button" href="/control.html">Software and Palace test suites</a></div>
 <p class="experiment-info">Imported ZIPs must include workflow.json and their referenced JSON, YAML or CSV source files. Executable Python is not accepted. Project imports remain on this workstation.</p>
 <h3>Execution plan</h3><ol class="workflow-steps">${steps.map((p,i)=>`<li><strong>${i+1}. ${safe(p.id)} · ${safe(p.adapter)}</strong><small>${safe(p.available?'Adapter available':'Adapter dependency is missing')} · ${safe(p.dependencies?.join(', ')||'No dependencies')}</small><div class="experiment-info">Input: ${safe(typeof p.source==='string'?p.source:JSON.stringify(p.source))}</div></li>`).join('')||'<li>Select a project to see its plan.</li>'}</ol>
 <label class="inline-control"><input id="python-consent" type="checkbox" ${s.codeConsent?'checked':''} ${preview?.trusted_python_factory?'':'disabled'}>Allow trusted bundled Quantum Metal Python factory</label>
 <label class="inline-control"><input id="solver-consent" type="checkbox" ${s.solverConsent?'checked':''}>Allow external Julia / Palace solvers (opt-in)</label>
 <div class="notice">External execution is optional and can be resource-intensive. Reports identify generated data, exports and unvalidated numerical results separately. The web server does not install missing libraries.</div>
 <div class="buttons"><button id="run" class="primary" ${active||s.busy||!preview?'disabled':''}>${active?'A run is active':'Run selected workflow'}</button><button id="reload">Refresh status</button></div>
 </section>
 ${run?`<section class="panel"><div class="status-title"><h2>2. Run ${safe(run.id.slice(0,8))}</h2><span class="pill ${safe(run.state)}">${safe(run.state)}</span></div>
 <p>${safe(run.project)} · Started: ${safe(date(run.created_utc))} · Completed: ${safe(date(run.completed_utc))}</p>
 ${run.error?`<div class="notice error">${safe(run.error)}</div>`:''}
 ${run.result?.steps?`<h3>Step results</h3><div class="results">${Object.entries(run.result.steps).map(([id,r])=>`<div class="check"><strong>${safe(id)} · ${safe(r.state)}</strong><p>${safe(r.adapter||r.error||'No additional details')} · ${Object.keys(r.artifacts||{}).length} artifacts</p></div>`).join('')}</div>`:''}
 <h3>Worker log</h3><pre class="log-output">${safe(run.log_tail||'No log output yet.')}</pre>
 <div class="buttons">${run.bundle_ready?`<a class="button primary" download href="/api/system/ecosystem/runs/${safe(run.id)}/bundle">Download support ZIP</a>`:''}
 ${['queued','running'].includes(run.state)?'<button id="cancel">Cancel run</button>':''}<button id="delete" ${run.bundle_ready?'':'disabled'}>Delete local run</button></div>
 <p class="experiment-info">The ZIP includes manifest.json, checksums, logs, workflow input snapshots and generated output. Review it before sharing. Integrity verification is not numerical or experimental validation.</p>
 </section>`:''}</div><div>
 <section class="panel"><h2>Engine availability</h2><p>Installed dependencies are detected here. Availability is not proof of correct results.</p><div class="engine-grid">${Object.entries(engines).map(([name,d])=>`<div class="engine"><strong><span class="indicator ${d.available?'ready':''}"></span>${safe(name)}</strong><small>${safe(d.available?'Detected':'Not detected')}${d.version?' · '+safe(d.version):''}</small></div>`).join('')}</div></section>
 <section class="panel"><h2>Recent experiments</h2><div class="history">${(s.catalog?.runs||[]).map(r=>`<button data-run="${safe(r.id)}" class="${run?.id===r.id?'selected':''}"><span><strong>${safe(r.project)}</strong><small>${safe(date(r.created_utc))} · ${safe(r.state)}</small></span><span class="pill">${safe(r.summary||r.state)}</span></button>`).join('')||'<p class="muted">No experiments yet.</p>'}</div></section>
 <section class="panel"><h2>One ZIP per issue</h2><p>Each experiment has a single <strong>Download support ZIP</strong> action after completion or failure. For legacy Studio jobs use the <strong>Download job ZIP</strong> button in the project Jobs view. For Palace and regression tests use Tests &amp; Diagnostics.</p></section>
 </div></div>`;
 document.getElementById('project')?.addEventListener('change',async e=>{s.selected=e.target.value;s.codeConsent=false;s.solverConsent=false;await loadPreview();});
 document.getElementById('import')?.addEventListener('click',()=>document.getElementById('project-upload').click());
 document.getElementById('project-upload')?.addEventListener('change',importZip);
 document.getElementById('python-consent')?.addEventListener('change',e=>s.codeConsent=e.target.checked);
 document.getElementById('solver-consent')?.addEventListener('change',e=>s.solverConsent=e.target.checked);
 document.getElementById('run')?.addEventListener('click',start);
 document.getElementById('reload')?.addEventListener('click',()=>refresh(true));
 document.getElementById('cancel')?.addEventListener('click',cancel);
 document.getElementById('delete')?.addEventListener('click',remove);
 document.querySelectorAll('[data-run]').forEach(b=>b.addEventListener('click',()=>select(b.dataset.run)));
}
async function loadPreview(){try{s.preview=await api('/system/ecosystem/preview?project='+encodeURIComponent(s.selected));s.error=null;}catch(e){s.preview=null;s.error=e.message;}render();}
async function refresh(loud=false){try{s.catalog=await api('/system/ecosystem');if(s.run)s.run=await api('/system/ecosystem/runs/'+s.run.id);if(loud)s.error=null;}catch(e){s.error=e.message;}render();}
async function select(id){try{s.run=await api('/system/ecosystem/runs/'+id);s.error=null;}catch(e){s.error=e.message;}render();}
async function start(){try{s.busy=true;render();const run=await api('/system/ecosystem/runs','POST',{project:s.selected,allow_project_code:s.codeConsent,allow_solvers:s.solverConsent});await select(run.id);await refresh();}catch(e){s.error=e.message;render();}finally{s.busy=false;render();}}
async function importZip(e){const file=e.target.files?.[0];if(!file)return;try{if(file.size>24*1024*1024)throw Error('ZIP exceeds the 24 MiB limit.');s.busy=true;render();const project=await api('/system/ecosystem/import','POST',await file.arrayBuffer(),true);s.catalog=await api('/system/ecosystem');s.selected=project.id;s.codeConsent=false;s.solverConsent=false;await loadPreview();}catch(error){s.error=error.message;render();}finally{s.busy=false;render();}}
async function cancel(){if(!s.run||!confirm('Stop this experiment and its external processes?'))return;try{await api('/system/ecosystem/runs/'+s.run.id+'/cancel','POST');await refresh();}catch(e){s.error=e.message;render();}}
async function remove(){if(!s.run||!confirm('Permanently delete this local run? Download the support ZIP first.'))return;try{await api('/system/ecosystem/runs/'+s.run.id,'DELETE');s.run=null;await refresh();}catch(e){s.error=e.message;render();}}
async function boot(){try{const session=await api('/auth/session');if(session.user?.role!=='admin')throw Error('Only workstation administrators can execute research workflows.');s.user=session.user;s.csrf=session.csrf;document.getElementById('connection').textContent='Local administrator · connected';s.catalog=await api('/system/ecosystem');if(!s.catalog.projects.some(p=>p.id===s.selected))s.selected=s.catalog.projects[0]?.id||'';if(s.catalog.runs.length)s.run=await api('/system/ecosystem/runs/'+s.catalog.runs[0].id);await loadPreview();}catch(e){s.error=e.message;document.getElementById('connection').textContent='Sign-in or local access required';render();}}
setInterval(()=>{if(s.user&&s.catalog?.runs.some(r=>['queued','running'].includes(r.state)))refresh();},2500);
boot();
