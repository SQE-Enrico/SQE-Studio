function goStep(next){clearTimeout(refreshTimer);refreshTimer=null;++runHistoryRequestToken;invalidateComparison();resultRequestToken++;if(step===5&&next!==5)selectedResult=null;step=Math.max(0,Math.min(next,6));render();if(step===5&&project)refreshRuns();window.scrollTo(0,0);$('pageTitle').setAttribute('tabindex','-1');$('pageTitle').focus({preventScroll:true})}
function openDialog(title,html){
 if(!projectCreatePending&&(title==='New project'||title==='Create your first project'))projectCreateReceipt=null;
 if($('overlay').classList.contains('hidden'))dialogReturnFocus=document.activeElement;
 $('dialogTitle').textContent=title;$('dialogBody').innerHTML=html;$('overlay').classList.remove('hidden');
 const first=$('dialogBody').querySelector('input:not([disabled]),button:not([disabled]),select:not([disabled])');
 (first||$('closeDialog')).focus();
}
function closeDialog(){if(projectCreatePending)return;$('overlay').classList.add('hidden');$('dialogBody').innerHTML='';if(dialogReturnFocus?.isConnected)dialogReturnFocus.focus();dialogReturnFocus=null}
function dialogKeys(event){
 if($('overlay').classList.contains('hidden'))return;
 if(event.key==='Escape'){event.preventDefault();closeDialog();return}
 if(event.key!=='Tab')return;
 const choices=[...$('overlay').querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href]')].filter(e=>e.getClientRects().length);
 if(!choices.length)return;
 const first=choices[0],last=choices[choices.length-1];
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
}
function literatureReferenceOverview(){
 const references=UI.scientificReferences||[];
 return `<details class="design-cases"><summary>Scientific reference benchmark library (${references.length})</summary><p class="helper">Numerical tests run on normal verified Results; measurements of published devices are NOT targets for unrelated editable geometries.</p>${references.map(c=>{const doi=c.reference?.doi;const link=doi?'https://doi.org/'+doi:c.reference?.url;const source=esc(c.reference.authors)+' ('+esc(c.reference.year)+')'+(doi?' · DOI '+esc(doi):' · publication');const citation=link?.startsWith('https://')?`<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">${source}</a>`:source;return `<div class="engine-status"><div><strong>${esc(c.id)} · ${esc(c.title)}</strong><br><small>${citation}<br>${esc(c.method)}<br>${esc(c.science_boundary)}</small></div><span class="${c.readiness.startsWith('blocked')?'unavailable':'available'}">${esc(c.readiness)}</span></div>`;}).join('')}</details>`;
}
function useCaseOverview(){return literatureReferenceOverview()+`<details class="design-cases"><summary>Published-method design cases · supported and planned</summary><p class="helper">These are scientific design goals, not separate tools or solver shortcuts. Unavailable transitions are explicitly blocked.</p>${designCases.map(c=>`<div class="engine-status"><div><strong>${esc(c.title)}</strong><br><small>${esc(c.purpose)}<br>Reference: <a href="${esc(c.reference_url)}" target="_blank" rel="noopener noreferrer">${esc(c.reference_title)}</a><br>Acceptance: ${esc(c.acceptance.join(' · '))}</small></div><span class="${c.starter_template?'available':'unavailable'}">${c.starter_template?'Editable starting point':'Blocked edge'}</span></div>${c.next_missing_edge?`<p class="helper">Required before enablement: ${esc(c.next_missing_edge)}</p>`:''}`).join('')}</details>`}
function capabilityOverview(){return `<details class="design-cases"><summary>EDA integration boundaries and missing links</summary><p class="helper">Native available means conditionally supported, never independently qualified.</p>${edaCapabilities.map(e=>`<div class="engine-status"><div><strong>${esc(e.source)} → ${esc(e.destination)}</strong><br><small>Prerequisite: ${esc(e.prerequisite)}<br>Review gate: ${esc(e.scientific_gate)}</small></div><span class="${e.status==='blocked'?'unavailable':'available'}">${esc(e.status.replaceAll('_',' '))}</span></div>`).join('')}</details>`}
function newProjectForm(){return `<p class="helper">Create an editable design. Starter designs use the exact same editor, saved revisions, native study API and validation as blank projects.</p>${field('Project name','newProjectName','My Circuit Design')}
 ${selection('newProjectTemplate','Start from',[['','Blank project'],...designTemplates.map(t=>[t.id,t.title])],'')}
 <p class="helper" id="templateInfo">No example-specific workspace or solver is created.</p>${useCaseOverview()}${capabilityOverview()}
 <label class="form-field"><span>Design family</span><select id="newProjectFamily"><option value="generic">Generic circuit</option><option value="transmon">Transmon</option><option value="fluxonium">Fluxonium</option><option value="resonator">Resonator</option><option value="amplifier">Quantum amplifier</option><option value="multi_qubit">Multi-qubit</option></select></label><button class="primary full" id="confirmNew">Create editable project →</button><p id="projectCreateStatus" class="project-create-status" role="status" aria-live="polite"></p>`}
// Do not close the dialog on a successful POST alone. The revision is visible
// only after the authenticated saved-project GET has completed. On a partial
// failure after POST, retries read the same project; they never POST again.
async function createProjectFromDialog(){
 if(projectCreatePending)return;
 const submit=$('confirmNew'),notice=$('projectCreateStatus');
 if(!submit||!notice)return;
 projectCreatePending=true;submit.disabled=true;
 try{
  if(!projectCreateReceipt){
   const args={name:$('newProjectName').value,family:$('newProjectFamily').value};
   if($('newProjectTemplate').value)args.template_id=$('newProjectTemplate').value;
   notice.textContent='Saving project to the local revision store…';
   const saved=await api('/api/projects','POST',args);
   if(!/^[0-9a-f]{32}$/.test(saved?.id)||!/^[0-9a-f]{32}$/.test(saved?.head))
    throw Error('Server did not return a valid saved project receipt');
   projectCreateReceipt={id:saved.id,head:saved.head};
  }
  notice.textContent='Opening the persisted revision…';
  await loadProject(projectCreateReceipt.id);
  if(project.id!==projectCreateReceipt.id||!/^[0-9a-f]{32}$/.test(project.head)||
     !/^[0-9a-f]{64}$/.test(project.revision_digest))
   throw Error('Saved revision provenance could not be confirmed');
  projects=[...projects.filter(p=>p.id!==project.id),
   {id:project.id,name:project.name,head:project.head}];
  projectCreateReceipt=null;projectCreatePending=false;closeDialog();
  toast('Project created · saved revision '+project.head.slice(0,8));
 }catch(err){
  if(projectCreateReceipt){
   notice.textContent='Project persisted, but opening its revision failed: '+err.message+'. Retry opening; no duplicate project will be created.';
   submit.textContent='Retry opening saved project';
  }else{
   notice.textContent='Creation not confirmed: '+err.message+'. Check Projects before retrying if the connection was interrupted.';
  }
  // A missing POST receipt could mean the connection failed after commit. Never
  // implicitly resubmit on transport errors; that could create a duplicate.
  submit.disabled=!projectCreateReceipt&&!(err.status>=400&&err.status<500);
  projectCreatePending=false;toast(err.message,true);
 }
}
function projectList(){return `<p class="helper">The current project and revision are the source of truth for all engine jobs.</p><button class="primary full" id="createOther">+ New project</button><div class="divider"></div>${projects.map(p=>`<button class="utility" data-open-project="${p.id}">▧ ${esc(p.name)} <span>${esc(p.head.slice(0,6))}</span></button>`).join('')}`}
async function history(){if(!project)return toast('Create a project first',true);const r=await api(`/api/projects/${project.id}/revisions`);
 openDialog('Revision history',`<p class="helper">Immutable snapshots · Open an older revision for inspection without overwriting the current head.</p>${r.revisions.map(v=>`<div class="engine-status"><span><b>${esc(v.id.slice(0,10))}</b><br><small>${new Date(v.created*1000).toLocaleString()}</small></span><button class="secondary mini" data-history="${v.id}">View</button></div>`).join('')}`);
 document.querySelectorAll('[data-history]').forEach(b=>b.onclick=async()=>{const snap=await api(`/api/projects/${project.id}/revisions/${b.dataset.history}`);openDialog('Revision '+snap.revision.slice(0,10),`<div class="callout">Read-only historical revision. Current head: ${esc(snap.head.slice(0,10))}.</div><pre class="pre-scroll">${esc(JSON.stringify(snap.model,null,2))}</pre>`)})}
async function engineDialog(){engines=(await api('/api/engines')).engines;openDialog('Native engine health',`<p class="helper">Detected dependencies are not solver validation. Full stack qualification requires per-engine native smoke, convergence, and benchmark evidence.</p>${engines.map(e=>`<div class="engine-status"><div><strong>${esc(e.name)}</strong><br><small>${esc(e.capability)}</small></div><span class="${engineValidated(e.id)?'available':'unavailable'}">${engineValidated(e.id)?'Detected · native use conditional':e.available?'Detected · mapping blocked':'Missing / blocked'}</span></div><p class="helper">Adapter mode: ${esc(e.mode)}. Installation alone is not validation or scientific qualification.</p>`).join('')}`)}
