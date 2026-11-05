function wireGlobal(){
 $('authForm').onsubmit=e=>{e.preventDefault();authenticate()};
 $('saveButton').onclick=save;$('prevButton').onclick=()=>goStep(step-1);$('nextButton').onclick=()=>goStep(step+1);
 $('projectChooser').onclick=()=>openDialog('Projects',projectList());
 $('enginesButton').onclick=engineDialog;$('railEngines').onclick=engineDialog;$('historyButton').onclick=history;$('railHistory').onclick=history;
 $('expertButton').onclick=()=>{expert=!expert;render();toast(expert?'Expert controls enabled where supported':'Guided mode enabled')};
 $('inspectorButton').onclick=()=>{inspector=!inspector;render()};$('closeInspector').onclick=()=>{inspector=false;render()};
 $('signOutButton').onclick=async()=>{clearTimeout(refreshTimer);refreshTimer=null;++runHistoryRequestToken;invalidateComparison();resultRequestToken++;await api('/api/logout','POST',{});csrf='';project=null;selectedResult=null;manualTransmonDraft=null;++manualTransmonCheckToken;setupView()};
 $('closeDialog').onclick=closeDialog;document.addEventListener('keydown',e=>{dialogKeys(e);if(!$('overlay').classList.contains('hidden')||e.altKey===false||e.ctrlKey||e.metaKey||e.target.closest('input,textarea,select'))return;if(/^[1-7]$/.test(e.key)){e.preventDefault();goStep(Number(e.key)-1)}});$('overlay').onclick=e=>{if(e.target===$('overlay'))closeDialog()};
 document.addEventListener('change',e=>{
  if(e.target?.id==='newProjectTemplate'){
   const t=designTemplates.find(t=>t.id===e.target.value);if(t){$('newProjectFamily').value=t.family;$('templateInfo').textContent=t.description+' Source: '+t.reference+'; not scientifically qualified.'}
   else $('templateInfo').textContent='Blank design · all engine and material mappings start unverified.';
  }
 });
 document.addEventListener('click',async e=>{
  if(e.target?.id==='confirmNew')await createProjectFromDialog();
  if(e.target?.id==='createOther')openDialog('New project',newProjectForm());
  const b=e.target.closest('[data-open-project]');if(b){closeDialog();await loadProject(b.dataset.openProject)}
 });
}
async function start(){wireGlobal();try{const me=await api('/api/me');csrf=me.csrf;$('application').classList.remove('hidden');await reload()}catch{setupView()}}
start();
