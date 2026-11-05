/* SQE Studio single workspace. View-controller only: NO physical computations. */
'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STEPS=[['intent','Specifications','Define targets, units and design criteria.'],['schematic','Schematic','Specify topology, elements and electrical ports.'],['layout','Layout','Generate geometry through Quantum Metal.'],['em','EM analysis','Configure full-wave studies via SQDMetal / Gmsh / Palace.'],['quantum','Quantum models','Run explicit quantum and circuit models with native engines.'],['results','Results','Inspect traceable native outputs and compare revisions.'],['fabrication','Fabrication','Export Quantum Metal GDSII under a clear HOLD gate.']];
let csrf='',project=null,projects=[],engines=[],step=0,expert=false,inspector=false,runs=[],dirty=false;
let dialogReturnFocus=null, toastTimer=null, selectedCanvasItem=null;
let designTemplates=[],designCases=[],edaCapabilities=[],componentCatalog=[],emSelectedId='',explorationStudyId='';
let runFilter='all',selectedResult=null,refreshTimer=null,resultRequestToken=0;
let runHistoryError='',runHistoryRequestToken=0,comparisonRequestToken=0,projectLoadToken=0,projectCreatePending=false,projectCreateReceipt=null;
const UI={};
// Guided transmon mapping is a local FORM until its own authenticated revision commit.
// It never supplies data directly to Results, a native run, or a quantum solver.
const TRANSMON_SCHEMA='sqe.saved-transmon-capacitance-selection.v1';
const TRANSMON_JUNCTION='MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED';
const TRANSMON_CONFIGS=['TWO_ISLAND_CHARGE_TRANSFER','GROUNDED_SINGLE_ISLAND'];
let transmonDraft=null,transmonDraftIdentity='',transmonSavePending=false,transmonConflict=false,transmonSaveMessage='';
// M4: RAM-only designer entry. This is NOT a saved model, a study, A12 approval,
// an attestation of origin, or an EM-to-Hamiltonian transfer. No POST route exists.
const MANUAL_TRANSMON_BLOCK='BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION';
let manualTransmonDraft=null,manualTransmonCheckToken=0;

async function api(path,method='GET',body){
 const response=await fetch(path,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':csrf}:{})},body:body?JSON.stringify(body):undefined});
 const typ=response.headers.get('content-type')||'';const obj=typ.includes('json')?await response.json():null;
 if(!response.ok){const error=Error((obj&&obj.error)||`HTTP ${response.status}`);error.status=response.status;throw error}return obj;
}
function toast(msg,error=false){const e=$('toast');clearTimeout(toastTimer);e.textContent=msg;e.className='toast'+(error?' error':'');toastTimer=setTimeout(()=>e.classList.add('hidden'),5200)}
function field(label,id,value,type='text',help=''){return `<label class="form-field"><span>${esc(label)}</span><input id="${id}" type="${type}" ${type==='number'?'step="any"':''} value="${esc(value)}">${help?`<small>${esc(help)}</small>`:''}</label>`}
function textarea(label,id,value,placeholder=''){return `<label class="form-field"><span>${esc(label)}</span><textarea id="${id}" placeholder="${esc(placeholder)}">${esc(value)}</textarea></label>`}
function pane(title,subtitle,content){return `<section class="pane"><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}${content}</section>`}
function empty(title,body){return `<div class="empty"><strong>${esc(title)}</strong><span>${esc(body)}</span></div>`}
function labelStatus(status){return status==='draft_saved'?'Draft saved':status==='not_started'?'Not started':status}
function activeModel(){return project?.model||null}
