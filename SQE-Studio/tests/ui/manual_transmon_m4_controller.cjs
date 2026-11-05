'use strict';
// Execute the unmodified production controller in a fake DOM. No scientific solver.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[2]),'../../../scripts/ui_source.cjs'))(process.argv[2]);
assert.match(source,/start\(\);\s*$/);
const elements={};
const ctx=vm.createContext({
 document:{getElementById:id=>elements[id]||null,
  querySelectorAll:q=>q==='[data-manual-transmon]'?['EJ','EC','ng','ncut','levels'].map(key=>elements['manualTransmon'+key]):[]},
 setTimeout,clearTimeout
});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const ev=s=>vm.runInContext(s,ctx);
const identity={id:'a'.repeat(32),head:'b'.repeat(32),model:{family:'transmon',intent:{targets:[],notes:'unrelated'},studies:[
 {id:'palace-old',engine:'sqdmetal_palace',kind:'capacitance',inputs:{screen:{conditional_EC_GHz:200}}},
 {id:'saved',engine:'scqubits',kind:'spectrum',inputs:{model:'Transmon',parameters:{EJ:15,EC:.25,ng:0,ncut:12}}} ]},name:'M4',stages:{}};
ctx.fixture=identity;
ev('project=fixture;step=4;render=()=>{};toast=()=>{};');
const snapshot=JSON.stringify(identity.model);
let html=ev('independentTransmonEditor()');
assert.match(html,/BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION/);
assert.match(html,/Save independent research study \(no run\)<\/button>/);
assert.match(html,/disabled aria-disabled="true" id="manualTransmonServerAction"/);
for(const key of ['EJ','EC','ng','ncut','levels']){
 assert.match(html,new RegExp(`id="manualTransmon${key}"[^>]*value=""`),key);
 assert.equal(ev(`manualTransmonDraft.${key}`),'',key);
}
assert.match(html,/EJ · GHz \(E\/h\)/);
assert.match(html,/EC · GHz \(E\/h\)/);
assert.match(html,/ng · 2e/);
assert.match(html,/statement, <strong>not an attestation/);
assert.doesNotMatch(html, /value="200"|value="15"|value="0\.25"/);
assert.equal(ev('manualTransmonDraft.acknowledged'),false);
assert.equal(ev('typeof manualTransmonDraft.preview'),'object'); // null
for(const key of ['EJ','EC','ng','ncut','levels'])elements['manualTransmon'+key]={dataset:{manualTransmon:key},value:''};
for(const key of ['manualTransmonCheckResult','manualTransmonSummary'])elements[key]={textContent:''};
elements.manualTransmonServerAction={setAttribute(){},disabled:true};
for(const key of ['manualTransmonAcknowledged','manualTransmonReset','manualTransmonCheck'])elements[key]={};
ev('wireIndependentTransmon()');
const edit=(key,val)=>{elements['manualTransmon'+key].value=val;elements['manualTransmon'+key].oninput();};
const consent=value=>elements.manualTransmonAcknowledged.onchange({target:{checked:value}});
const valid={EJ:'15.2',EC:'0.23',ng:'-0.5',ncut:'8',levels:'8'};
for(const [key,val] of Object.entries(valid))edit(key,val);
assert.throws(()=>ev('validateIndependentTransmonLocal(manualTransmonDraft)'),/Confirm explicitly/);
consent(true);
let scalar=ev('validateIndependentTransmonLocal(manualTransmonDraft)');
assert.equal(JSON.stringify(scalar),JSON.stringify({EJ:15.2,EC:.23,ng:-.5,ncut:8,levels:8}));
const reject=(key,value,re)=>{
 const old=elements['manualTransmon'+key].value;
 edit(key,value);
 assert.throws(()=>ev('validateIndependentTransmonLocal(manualTransmonDraft)'),re,`${key}=${value}`);
 edit(key,old);
};
for(const bad of ['', '  ', 'Infinity', 'NaN','0x10','1_000','true','false','1,5','1e309','<svg onload=alert(1)>'])reject('EJ',bad, /EJ/);
for(const bad of ['0','-1','1000.01','1e-999'])reject('EC',bad,/EJ and EC/);
reject('EJ','1001',/EJ and EC/);
for(const bad of ['10.1','-10.01'])reject('ng',bad,/ng/);
for(const bad of ['3.5','3e0','2','81','','<img src=x onerror=alert(1)>'])reject('ncut',bad,/ncut/);
for(const bad of ['2.5','1','13','1e1',''])reject('levels',bad,/levels/);
edit('ncut','3');edit('levels','12');
assert.throws(()=>ev('validateIndependentTransmonLocal(manualTransmonDraft)'),/basis/);
edit('ncut','8');edit('levels','8');
ctx.boolValue=true;ev('manualTransmonDraft.EJ=boolValue');
assert.throws(()=>ev('validateIndependentTransmonLocal(manualTransmonDraft)'),/manually typed/);
edit('EJ',valid.EJ);
const xss='"><img src=x onerror=alert(1)>';
ctx.xss=xss;ev('manualTransmonDraft.EJ=xss');
html=ev('independentTransmonEditor()');
assert.match(html,/&quot;&gt;&lt;img/);
assert.doesNotMatch(html,/<img/);
edit('EJ',valid.EJ);
// Do not permit an acknowledgement to mask an upstream source or verified origin.
assert.match(ev('independentTransmonEditor()'),/not an attestation/);
const requests=[];ctx.requests=requests;
ev(`api=async(path,method,body)=>{requests.push({path,method,body});return {id:fixture.id,head:fixture.head}};`);
(async()=>{
 assert.equal(await ev('checkIndependentTransmonLocal()'),true);
 assert.equal(requests.length,1);
 assert.equal(requests[0].method,undefined);
 assert.equal(requests[0].path,`/api/projects/${identity.id}`);
 assert.equal(requests[0].body,undefined);
 assert.match(elements.manualTransmonCheckResult.textContent,/Not A12 preflight/);
 assert.match(elements.manualTransmonSummary.textContent,/Local syntax only/);
 assert.equal(JSON.stringify(identity.model),snapshot,'must not modify persisted model or saved scqubits study');
 assert.match(ev('independentTransmonEditor()'),/BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION/);
 // Any keyboard change clears stale locally checked preview, without server write.
 edit('EC','0.24');
 assert.equal(elements.manualTransmonSummary.textContent,'');
 edit('EC',valid.EC);
 // In-flight callback is superseded by subsequent input, not allowed to publish stale checks.
 let resolve;
 ctx.promise=new Promise(r=>resolve=r);
 ev('api=async()=>promise');
 const pending=ev('checkIndependentTransmonLocal()');
 edit('ng','0.5');
 resolve({id:identity.id,head:identity.head});
 assert.equal(await pending,false);
 assert.equal(elements.manualTransmonSummary.textContent,'');
 edit('ng',valid.ng);
 // Stale revision returned by server blocks the local check and all subsequent attempts.
 ev(`api=async()=>({id:fixture.id,head:'c'.repeat(32)})`);
 assert.equal(await ev('checkIndependentTransmonLocal()'),false);
 assert.match(elements.manualTransmonCheckResult.textContent,/STALE_REVISION/);
 assert.match(ev('independentTransmonEditor()'),/disabled aria-disabled="true">Check local syntax/);
 // Reset clears every field and consent, no storage or server mutation.
 elements.manualTransmonReset.onclick();
 assert.equal(ev('manualTransmonDraft.EJ'),'');
 assert.equal(ev('manualTransmonDraft.acknowledged'),false);
 ev('manualTransmonDraft.acknowledged=true');
 assert.throws(()=>ev('validateIndependentTransmonLocal(manualTransmonDraft)'),/EJ/);
 // Local identity mismatch immediately blocks another project/head in same browser.
 ev(`manualTransmonDraft.revision='d'.repeat(32)`);
 assert.equal(await ev('checkIndependentTransmonLocal()'),false);
 assert.match(elements.manualTransmonCheckResult.textContent,/STALE_REVISION/);
 ev('manualTransmonDraft=freshIndependentTransmonDraft();');
 for(const [key,val] of Object.entries(valid))ev(`manualTransmonDraft.${key}=${JSON.stringify(val)}`);
 ev('manualTransmonDraft.acknowledged=true;dirty=true');
 assert.equal(await ev('checkIndependentTransmonLocal()'),false);
 assert.match(elements.manualTransmonCheckResult.textContent,/BLOCKED_UNSAVED_PROJECT_CHANGES/);
 ev('dirty=false;api=async()=>{throw Error("network unavailable")};');
 assert.equal(await ev('checkIndependentTransmonLocal()'),false);
 assert.match(elements.manualTransmonCheckResult.textContent,/BLOCKED_REVISION_CHECK_UNAVAILABLE/);
 assert.equal(JSON.stringify(identity.model),snapshot);
 assert.equal(requests.length,1,'no hidden write/read on input or reset');
 assert.match(source,/if\(id==='quantum'\)\{/);
 assert.doesNotMatch(source,/api\/transmon.*preflight/);
 console.log('M4_CONTROLLER_PASS empty defaults, exact units, negative syntax/ranges, consent, XSS, race, stale, isolation, no POST');
})().catch(e=>{console.error(e);process.exitCode=1});
