"""Deterministic JS scheduling tests for the persisted-revision/UI race.

Test doubles cover browser scheduling and interrupted GET only; these tests do
NOT pretend to be native engine, real browser, or HTTP-security qualifications.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_create_waits_for_revision_readback_and_retries_without_duplicate_post():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: deterministic production-JS controller test blocked')
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
assert.match(source,/start\(\);\s*$/);
const id='1'.repeat(32),head='2'.repeat(32),sha='3'.repeat(64);
const detail={id,head,revision_digest:sha,name:'test-only design',stages:{},
 model:{family:'generic',studies:[],intent:{targets:[]}}};
const elements={confirmNew:{disabled:false,textContent:'Create editable project'},
 newProjectName:{value:'test-only design'},newProjectFamily:{value:'generic'},
 newProjectTemplate:{value:''},projectCreateStatus:{textContent:''}};
const log=[];
const ctx=vm.createContext({document:{getElementById:key=>elements[key]},
 setTimeout,clearTimeout,log,detail,id,head,sha});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
vm.runInContext(`render=()=>log.push('render');closeDialog=()=>log.push('closed');
 toast=(msg)=>log.push('toast');`,ctx);
let releasePost;
const waiting=new Promise(resolve=>releasePost=resolve);
ctx.responses=waiting;
vm.runInContext(`api=async(path,method)=>{
 log.push((method||'GET')+' '+path);
 if(path==='/api/projects' && method==='POST')return await responses;
 if(path==='/api/projects/'+id)return detail;
 if(path==='/api/projects/'+id+'/runs')return {runs:[]};
 throw Error('Unexpected HTTP request '+path);
}`,ctx);
(async()=>{
 const task=vm.runInContext('createProjectFromDialog()',ctx);
 assert.equal(elements.confirmNew.disabled,true);
 assert.equal(log.includes('closed'),false);
 // Rapid second click is ignored while POST is pending.
 await vm.runInContext('createProjectFromDialog()',ctx);
 assert.equal(log.filter(x=>x==='POST /api/projects').length,1);
 releasePost({id,head}); await task;
 assert.deepEqual(log.filter(x=>x.startsWith('GET ')),
   ['GET /api/projects/'+id,'GET /api/projects/'+id+'/runs']);
 assert.equal(log.includes('closed'),true);
 assert.equal(vm.runInContext('project.head',ctx),head);
 assert.equal(vm.runInContext('projects[0].head',ctx),head);
 assert.equal(vm.runInContext('projectCreateReceipt',ctx),null);
 assert.equal(vm.runInContext('runHistoryError',ctx),'');
 // Simulate a transient project-detail HTTP failure AFTER a successful POST.
 // Retry must use GET, not create another project.
 const log2=[];ctx.log2=log2;
 vm.runInContext(`projectCreateReceipt=null;project=null;projectCreatePending=false;`,ctx);
 let first=true;ctx.getFirst=()=>{if(first){first=false;throw Error('GET aborted')}return detail};
 vm.runInContext(`api=async(path,method)=>{
 log2.push((method||'GET')+' '+path);
 if(path==='/api/projects' && method==='POST')return {id,head};
 if(path==='/api/projects/'+id)return getFirst();
 if(path==='/api/projects/'+id+'/runs')return {runs:[]};
 throw Error('Unexpected request '+path);
 }`,ctx);
 await vm.runInContext('createProjectFromDialog()',ctx);
 assert.equal(log2.filter(x=>x==='POST /api/projects').length,1);
 assert.equal(log2.includes('GET /api/projects/'+id),true);
 assert.equal(vm.runInContext('projectCreateReceipt.id',ctx),id);
 assert.equal(log2.includes('POST /api/engines'),false);
 assert.equal(elements.confirmNew.textContent,'Retry opening saved project');
 await vm.runInContext('createProjectFromDialog()',ctx);
 assert.equal(log2.filter(x=>x==='POST /api/projects').length,1);
 assert.equal(vm.runInContext('project.head',ctx),head);
 // An aborted catalog/engine GET cannot mask an already persisted project.
 vm.runInContext(`api=async(path)=>{
  if(path==='/api/projects')return {projects:[{id,head}]};
  if(path==='/api/engines')throw Error('Engine HTTP aborted');
  if(path==='/api/design/templates')return {templates:[]};
  if(path==='/api/design/use-cases')return {cases:[]};
  if(path==='/api/design/capabilities')return {edges:[]};
  if(path==='/api/design/components')return {components:[]};
  if(path==='/api/projects/'+id)return detail;
  if(path==='/api/projects/'+id+'/runs')throw Error('Runs HTTP aborted');
  throw Error('Unexpected '+path);
 }`,ctx);
 await vm.runInContext('reload()',ctx);
 assert.equal(vm.runInContext('project.head',ctx),head);
 assert.equal(vm.runInContext('engines.length',ctx),0);
 assert.equal(vm.runInContext('engineValidated("scqubits")',ctx),false);
 assert.match(vm.runInContext('runRows([])',ctx),/Job history unavailable/);
 assert.doesNotMatch(vm.runInContext('runRows([])',ctx),/No native job history/);
 assert.match(vm.runInContext('compareControls()',ctx),/Job history is unavailable/);
 console.log('UI_RACE_PASS POST gated until revision readback; retry GET-only; engine/runs abort fail closed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    completed = subprocess.run([node, '-e', script, str(ROOT / 'src/sqe_studio/web/app.js')],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    print(completed.stdout.strip())


def test_out_of_order_authenticated_job_history_never_revives_stale_states():
    """Execute production refresh controller with adversarial GET completion order.

    This tests asynchronous UI state, not a real browser or native solver.
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: asynchronous controller order check BLOCKED')
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const elements={runMetrics:{innerHTML:''},runList:{innerHTML:''},compareSection:{innerHTML:''}};
const ctx=vm.createContext({document:{getElementById:k=>elements[k],querySelectorAll:()=>[]},
  setTimeout,clearTimeout});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const pid='a'.repeat(32),rid='b'.repeat(32);
vm.runInContext(`project={id:'${pid}',head:'${rid}'};step=5;runs=[];`,ctx);
vm.runInContext(`toast=()=>{};`,ctx);
const pending=[];
ctx.responses=pending;
vm.runInContext(`api=async(path)=>new Promise((resolve,reject)=>responses.push({resolve,reject,path}));`,ctx);
(async()=>{
 const older=vm.runInContext('refreshRuns()',ctx);
 const newer=vm.runInContext('refreshRuns()',ctx);
 assert.equal(pending.length,2);
 assert.equal(pending[0].path,'/api/projects/'+pid+'/runs');
 pending[1].reject(Error('HTTP history disconnected'));
 await newer;
 assert.match(vm.runInContext('runHistoryError',ctx),/history disconnected/);
 assert.match(elements.runList.innerHTML,/Job history unavailable/);
 assert.match(elements.compareSection.innerHTML,/Job history is unavailable/);
 pending[0].resolve({runs:[{id:'c'.repeat(32),revision_id:rid,engine:'scqubits',study_id:'T1',state:'completed'}]});
 await older;
 assert.equal(vm.runInContext('runs.length',ctx),0);
 assert.match(vm.runInContext('runHistoryError',ctx),/history disconnected/);
 const recovered=vm.runInContext('refreshRuns()',ctx);
 pending[2].resolve({runs:[{id:'d'.repeat(32),revision_id:rid,engine:'scqubits',study_id:'T1',state:'failed'}]});
 await recovered;
 assert.equal(vm.runInContext('runHistoryError',ctx),'');
 assert.equal(vm.runInContext('runs[0].state',ctx),'failed');
 assert.match(elements.runList.innerHTML,/failed/);
 assert.doesNotMatch(elements.runList.innerHTML,/Job history unavailable/);
 const stale=vm.runInContext('refreshRuns()',ctx);
 vm.runInContext('step=0;runHistoryRequestToken++;',ctx);
 pending[3].resolve({runs:[]});await stale;
 assert.equal(vm.runInContext('runs[0].state',ctx),'failed');
 console.log('UI_HISTORY_ORDER_PASS stale success cannot erase disconnect, recovery requires fresh GET');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    completed = subprocess.run([node, '-e', script, str(ROOT / 'src/sqe_studio/web/app.js')],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    print(completed.stdout.strip())
