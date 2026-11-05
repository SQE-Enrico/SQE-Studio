// Actual production JS controller, mocked authenticated boundary only.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[2]),'../../../scripts/ui_source.cjs'))(process.argv[2]);
const dom={manualTransmonCheckResult:{textContent:''},manualTransmonSummary:{textContent:''},manualTransmonServerAction:{disabled:true,setAttribute(){}}};
const scope=vm.createContext({document:{getElementById:id=>dom[id]||null,querySelectorAll:()=>[]},setTimeout,clearTimeout});
vm.runInContext(source.replace(/start\(\);\s*$/,''),scope);
const ev=x=>vm.runInContext(x,scope);
const project={id:'a'.repeat(32),head:'b'.repeat(32),model:{family:'transmon',studies:[],intent:{targets:[]}}};
scope.current=project;scope.history=[];
ev('project=current;render=()=>{};toast=()=>{};loadProject=async(id)=>{history.push(id);};');
const preset={EJ:'14',EC:'0.22',ng:'0',ncut:'20',levels:'5'};
scope.preset=preset;ev('manualTransmonDraft=freshIndependentTransmonDraft();Object.assign(manualTransmonDraft,preset);manualTransmonDraft.acknowledged=true;manualTransmonDraft.preview=validateIndependentTransmonLocal(manualTransmonDraft);');
const baseline=JSON.stringify(project.model);
scope.calls=[];
ev(`api=async(path,method,body)=>{calls.push({path,method,body});return {status:'SAVED_UNVERIFIED_INDEPENDENT_RESEARCH_STUDY',revision:'c'.repeat(32),study_id:'independent_transmon_01',em_ec_transfer:'BLOCKED',fabrication:'HOLD'};}`);
(async()=>{
 assert.equal(await ev('saveIndependentTransmonResearch()'),true);
 assert.equal(scope.calls.length,1);
 const req=scope.calls[0];
 assert.equal(req.path,'/api/projects/'+project.id+'/independent-transmon');
 assert.equal(req.method,'POST');
 assert.equal(req.body.expected_revision,project.head);
 assert.equal(req.body.acknowledged,true);
 assert.deepEqual(JSON.parse(JSON.stringify(req.body.declaration.parameters)),{EJ:14,EC:0.22,ng:0,ncut:20});
 assert.equal(req.body.declaration.source,'independent');
 assert.equal(req.body.declaration.parameter_units.EC,'GHz');
 assert.equal(JSON.stringify(project.model),baseline);
 assert.equal(scope.history.length,1);
 assert.equal(ev('manualTransmonDraft'),null);
 // A changed input cannot be silently saved with a stale local preview.
 ev('manualTransmonDraft=freshIndependentTransmonDraft();Object.assign(manualTransmonDraft,preset);manualTransmonDraft.acknowledged=true;manualTransmonDraft.preview=validateIndependentTransmonLocal(manualTransmonDraft);manualTransmonDraft.EC="0.23";');
 assert.equal(await ev('saveIndependentTransmonResearch()'),false);
 assert.equal(scope.calls.length,1);
 ev('manualTransmonDraft=freshIndependentTransmonDraft();Object.assign(manualTransmonDraft,preset);manualTransmonDraft.acknowledged=true;manualTransmonDraft.preview=validateIndependentTransmonLocal(manualTransmonDraft);dirty=true;');
 assert.equal(await ev('saveIndependentTransmonResearch()'),false);
 assert.equal(scope.calls.length,1);
 console.log('A99_M4_CONTROLLER_PASS manual-only POST, unchanged model, stale/dirty blocked');
})().catch(e=>{console.error(e);process.exitCode=1});
