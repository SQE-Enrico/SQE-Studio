'use strict';
// Exercises the actual production browser controller in a Node VM (NO native physics).
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[2]),'../../../scripts/ui_source.cjs'))(process.argv[2]);
assert.match(source,/start\(\);\s*$/);
const elements={};let lastHtml='';
const ctx=vm.createContext({
 document:{getElementById:id=>elements[id]||null,querySelectorAll:q=>q==='[data-transmon-terminal]'?[]:[]},
 setTimeout,clearTimeout
});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const evaluate=code=>vm.runInContext(code,ctx);
const port=(component,i)=>({kind:'conductor',component,index:i,native_attributes:[i+10]});
const xss='<img src=x onerror=alert(1)>';
const model={schema:'sqe.project.v1',name:'M2 test',family:'transmon',intent:{notes:'keep notes',targets:[{name:'f01',value:5.2,unit:'GHz',tolerance:.1}],independent_mapping:{keep:1}},
 studies:[{id:'CStudy',engine:'sqdmetal_palace',kind:'capacitance',inputs:{em:{ports:[port('Q_A',1),port('Q_B',2),port('Guard',3),port('Floating',4)]}}},
 {id:'spectrum',engine:'scqubits',kind:'spectrum',inputs:{parameters:{EJ:13.3,EC:.24},source:'independent'}}],
 layout:{components:[]},schematic:{nodes:[],elements:[],ports:[]},process:{},notes:''};
const identity={id:'a'.repeat(32),head:'b'.repeat(32),revision_digest:'c'.repeat(64),name:'M2 test',model,stages:{}};
ctx.fixture=identity;
evaluate('project=fixture;step=3;render=()=>{};toast=()=>{};');
let inv=evaluate('transmonInventory(project.model.studies[0])');
assert.equal(inv.ok,true);
assert.equal(evaluate('transmonSelectionEditor()').includes('BLOCKED_NO_SAVED_SELECTION'),true);
assert.match(evaluate('transmonSelectionEditor()'),/Choose explicitly/);
assert.match(evaluate('transmonSelectionEditor()'),/disabled>Save transmon selection/);
assert.equal(evaluate('transmonDraft.study_id'),''); // no inferred default
for(const family of ['generic','resonator','amplifier']){
 evaluate(`project.model.family='${family}'`);
 assert.equal(evaluate('transmonSelectionEditor()'),'');
}evaluate('project.model.family="multi_qubit"');
assert.match(evaluate('transmonSelectionEditor()'),/saved terminal selection/);
evaluate('project.model.family="transmon"');
ctx.xss=xss;
evaluate(`project.model.studies[0].inputs.em.ports[3].component=xss`);
let escaped=evaluate('transmonInventory(project.model.studies[0])');assert.equal(escaped.ok,true);
evaluate(`transmonDraft.study_id='CStudy'`);
const html=evaluate('transmonSelectionEditor()');
assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
evaluate(`project.model.studies[0].inputs.em.ports[3].component='Floating'`);
evaluate(`transmonDraft.study_id='CStudy';transmonDraft.island_a='Q_A';transmonDraft.island_b='Q_B';transmonDraft.configuration='TWO_ISLAND_CHARGE_TRANSFER';transmonDraft.junctionAccepted=true`);
assert.throws(()=>evaluate('validatedTransmonSelection(project.model,transmonDraft)'),/Classify every other/);
evaluate(`transmonDraft.policy.Guard='fixed_zero';transmonDraft.policy.Floating='floating_zero_charge'`);
let exact=evaluate('validatedTransmonSelection(project.model,transmonDraft)');
assert.equal(exact.schema,'sqe.saved-transmon-capacitance-selection.v1');
assert.equal(exact.junction_capacitance_assumption,'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED');
assert.equal(Object.keys(exact).length,7);
assert.equal(JSON.stringify(exact.other_terminal_policy),'{"fixed_zero":["Guard"],"floating_zero_charge":["Floating"]}');
assert.match(evaluate('transmonSelectionEditor()'),/READY_TO_SAVE/);
assert.doesNotMatch(evaluate('transmonSelectionEditor()'),/disabled>Save transmon selection/);
const rejected=[
 ['same islands', `transmonDraft.island_b='Q_A'`,/distinct/],
 ['unknown island',`transmonDraft.island_b='MISSING'`,/distinct/],
 ['unclassified terminal',`delete transmonDraft.policy.Guard`,/Classify/],
 ['unknown remaining terminal',`transmonDraft.policy.Unknown='fixed_zero'`,/Unknown/],
 ['explicit convention',`transmonDraft.configuration=''`,/convention/],
 ['explicit junction',`transmonDraft.junctionAccepted=false`,/junction/],
];
for(const [label,mutation,error] of rejected){
 evaluate(mutation);assert.throws(()=>evaluate('validatedTransmonSelection(project.model,transmonDraft)'),error,label);
 evaluate(`transmonDraft.island_a='Q_A';transmonDraft.island_b='Q_B';transmonDraft.configuration='TWO_ISLAND_CHARGE_TRANSFER';transmonDraft.junctionAccepted=true;
 transmonDraft.policy=Object.create(null);transmonDraft.policy.Guard='fixed_zero';transmonDraft.policy.Floating='floating_zero_charge'`);
}
evaluate('project.model.studies[0].inputs.em.ports[1].component="Q_A"');
assert.match(evaluate('transmonInventory(project.model.studies[0]).reason'),/duplicates/);
evaluate('project.model.studies[0].inputs.em.ports[1].component="Q_B"');
evaluate('project.model.studies[0].inputs.em.ports[1].native_attributes=[11]');
assert.equal(evaluate('transmonInventory(project.model.studies[0]).ok'),false);
evaluate('project.model.studies[0].inputs.em.ports[1].native_attributes=[12]');
evaluate('project.model.studies[0].inputs.em.ports[1].kind="cpw_launcher"');
assert.equal(evaluate('transmonInventory(project.model.studies[0]).ok'),false);
evaluate('project.model.studies[0].inputs.em.ports[1].kind="conductor"');
evaluate('dirty=true');assert.match(evaluate('transmonSelectionEditor()'),/BLOCKED_UNSAVED_CHANGES/);
evaluate('dirty=false');
// Controller interactions really call the production event callbacks.
for(const id of ['transmonStudy','transmonIslandA','transmonIslandB','transmonConfiguration','transmonJunctionConfirm','resetTransmonSelection','commitTransmonSelection'])elements[id]={};
evaluate('wireTransmonSelection()');
elements.transmonStudy.onchange({target:{value:'CStudy'}});
assert.equal(evaluate('transmonDraft.island_a'),'');assert.equal(evaluate('transmonDraft.junctionAccepted'),false);
elements.transmonIslandA.onchange({target:{value:'Q_A'}});
elements.transmonIslandB.onchange({target:{value:'Q_B'}});
elements.transmonConfiguration.onchange({target:{value:'GROUNDED_SINGLE_ISLAND'}});
elements.transmonJunctionConfirm.onchange({target:{checked:true}});
evaluate(`transmonDraft.policy.Guard='fixed_zero';transmonDraft.policy.Floating='floating_zero_charge'`);
assert.equal(evaluate('validatedTransmonSelection(project.model,transmonDraft).configuration'),'GROUNDED_SINGLE_ISLAND');
// Put a prior job in the history: it is not rewritten by the selection commit.
const original=JSON.stringify(model);
const requests=[];ctx.requests=requests;
evaluate(`api=async(path,method,body)=>{requests.push({path,method,body});return {revision:'d'.repeat(32)}};
loadProject=async(id)=>{project={...project,head:'d'.repeat(32),model:JSON.parse(JSON.stringify(requests[0].body.model))};
transmonDraft=null;transmonDraftIdentity='';return true;}`);
(async()=>{
 assert.equal(await evaluate('commitTransmonSelection()'),true);
 assert.equal(requests.length,1);
 assert.equal(requests[0].method,'POST');
 assert.equal(requests[0].path,'/api/projects/'+identity.id+'/commit');
 assert.equal(requests[0].body.expected_revision,identity.head);
 assert.equal(JSON.stringify(requests[0].body.model.intent.targets),JSON.stringify(model.intent.targets));
 assert.equal(JSON.stringify(requests[0].body.model.intent.independent_mapping),JSON.stringify(model.intent.independent_mapping));
 assert.equal(JSON.stringify(requests[0].body.model.studies),JSON.stringify(model.studies));
 assert.equal(requests[0].body.model.studies[1].inputs.parameters.EJ,13.3);
 assert.equal(JSON.stringify(model),original); // immutable input untouched
 assert.equal(requests[0].body.model.intent.transmon_capacitance_selection.configuration,'GROUNDED_SINGLE_ISLAND');
 assert.equal(requests[0].body.model.intent.transmon_capacitance_selection.revision_id,undefined);
 assert.equal(requests[0].body.model.intent.transmon_capacitance_selection.revision_digest,undefined);
 assert.match(evaluate('transmonResultsContext()'),/immutable run revisions/);
 // Real server JSON serialization sorts model keys, including selection keys.
 const saved=JSON.parse(JSON.stringify(requests[0].body.model.intent.transmon_capacitance_selection));
 ctx.saved=Object.fromEntries(Object.entries(saved).sort(([a],[b])=>a.localeCompare(b)));
 assert.equal(evaluate('sameTransmonSelection(saved,project.model.intent.transmon_capacitance_selection)'),true);
 // A malformed persisted selection cannot be silently normalized into READY.
 const goodModel=evaluate('project.model');
 const malformed=JSON.parse(JSON.stringify(goodModel));
 malformed.intent.transmon_capacitance_selection.other_terminal_policy.fixed_zero=['Guard','Guard'];
 ctx.malformed=malformed;
 evaluate('project.model=malformed;transmonDraft=null;transmonDraftIdentity=""');
 assert.match(evaluate('transmonSelectionEditor()'),/BLOCKED_INVALID_SAVED_SELECTION/);
 assert.match(evaluate('transmonSelectionEditor()'),/disabled>Save transmon selection/);
 assert.equal(await evaluate('commitTransmonSelection()'),false);
 const forbidden=[];ctx.forbidden=forbidden;
 evaluate('dirty=true;api=async()=>{forbidden.push("POST");return {revision:"x"}}');
 assert.equal(await evaluate('save()'),false);
 assert.equal(forbidden.length,0);
 evaluate('dirty=false;project.model=fixture.model;transmonDraft=null;transmonDraftIdentity=""');
 // A 409 must not overwrite the stale project, nor retry automatically.
 evaluate(`transmonDraft=newTransmonDraft();transmonDraftIdentity=project.id+'@'+project.head;
 transmonDraft.study_id='CStudy';transmonDraft.island_a='Q_A';transmonDraft.island_b='Q_B';
 transmonDraft.policy.Guard='fixed_zero';transmonDraft.policy.Floating='floating_zero_charge';
 transmonDraft.configuration='TWO_ISLAND_CHARGE_TRANSFER';transmonDraft.junctionAccepted=true;`);
 const calls=[];ctx.calls=calls;
 evaluate(`api=async(path,method,body)=>{calls.push({path,method,body});let err=Error('Revision conflict');err.status=409;throw err}`);
 assert.equal(await evaluate('commitTransmonSelection()'),false);
 assert.equal(evaluate('transmonConflict'),true);
 assert.match(evaluate('transmonSelectionEditor()'),/BLOCKED_CONFLICT/);
 assert.equal(await evaluate('commitTransmonSelection()'),false);
 assert.equal(calls.length,1);
 // Two native pad geometries inside one CAD component remain distinct conductors.
 const named=JSON.parse(JSON.stringify(model));
 named.studies[0].inputs.em.ports=[
  {...port('Q1',1),qgeometry:'pad_bot',label:'Q1_pad_bot',native_terminal_index:2},
  {...port('Q1',2),qgeometry:'pad_top',label:'Q1_pad_top',native_terminal_index:3}
 ];
 ctx.named=named;
 evaluate('project.model=named;transmonDraft=null;transmonDraftIdentity=""');
 assert.equal(evaluate('transmonInventory(project.model.studies[0]).ok'),true);
 assert.equal(JSON.stringify(evaluate('transmonInventory(project.model.studies[0]).names')),
  '["Q1_pad_bot","Q1_pad_top"]');
 evaluate(`transmonDraft=newTransmonDraft();transmonDraft.study_id='CStudy';
 transmonDraft.island_a='Q1_pad_bot';transmonDraft.island_b='Q1_pad_top';
 transmonDraft.configuration='TWO_ISLAND_CHARGE_TRANSFER';transmonDraft.junctionAccepted=true;`);
 assert.equal(evaluate('validatedTransmonSelection(project.model,transmonDraft).island_b'),'Q1_pad_top');
 evaluate("project.model.studies[0].inputs.em.ports[1].label='Q1_pad_bot'");
 assert.equal(evaluate('transmonInventory(project.model.studies[0]).ok'),false);
 evaluate("project.model.studies[0].inputs.em.ports[1].label='Q1_pad_top';project.model.studies[0].inputs.em.ports[1].qgeometry='unknown'");
 assert.equal(evaluate('transmonInventory(project.model.studies[0]).ok'),false);
 console.log('M2_CONTROLLER_PASS exact ports, named pads, exhaustive policy, XSS, blocked states, preserved model, optimistic POST, readback, conflict');
})().catch(e=>{console.error(e);process.exitCode=1});
