"""A14 RC14.11: exercise production Results controller with out-of-order I/O.

Synthetic API payloads below exercise UI race handling only. They are NOT
solver runs, scientific verification, a browser acceptance pass or foundry proof.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'web' / 'app.js'


def _run_node(body: str) -> None:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js missing: production controller race checks BLOCKED')
    result = subprocess.run([node, '-e', body, str(JS)], capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, (result.stdout, result.stderr)
    print(result.stdout.strip())


def test_result_inspection_invalidated_by_changed_job_lineage_or_history_failure():
    _run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const pid='a'.repeat(32),rid='b'.repeat(32),id='c'.repeat(32),sha='d'.repeat(64);
const elements={resultView:{innerHTML:'',textContent:'',focus(){},},
 runMetrics:{innerHTML:''},runList:{innerHTML:''},compareSection:{innerHTML:''}};
const ctx=vm.createContext({document:{getElementById:key=>elements[key],querySelectorAll:()=>[]},
 setTimeout,clearTimeout});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const job={id,revision_id:rid,engine:'scqubits',study_id:'T1',state:'completed',is_sweep:false};
const manifest={schema:'sqe.artifact.v1',revision_id:rid,engine:'scqubits',study_id:'T1',
 project_digest:sha,fabrication_status:'HOLD',scientific_status:'review_required',artifacts:[]};
vm.runInContext(`project={id:'${pid}',head:'${rid}',revision_digest:'${sha}',model:{studies:[],intent:{targets:[]}}};step=5;`,ctx);
ctx.job=job;vm.runInContext('runs=[job];toast=()=>{}',ctx);
const pending=[];ctx.pending=pending;
vm.runInContext('api=path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject}))',ctx);
(async()=>{
 const first=vm.runInContext('inspectResult(job.id)',ctx);
 assert.equal(pending[0].path,`/api/projects/${pid}/runs/${id}/result`);
 // Same run ID now points to different revision: old evidence must be discarded.
 const change=vm.runInContext('refreshRuns()',ctx);
 pending[1].resolve({runs:[{...job,revision_id:'e'.repeat(32)}]});await change;
 pending[0].resolve({manifest});await first;
 assert.doesNotMatch(elements.resultView.innerHTML,/Native result inspection/);
 assert.match(elements.resultView.textContent,/history changed/);
 // A fresh known job and actual reply from the stub API are still inspectable.
 vm.runInContext('runs=[job]',ctx);
 const fresh=vm.runInContext('inspectResult(job.id)',ctx);
 pending[2].resolve({manifest});await fresh;
 assert.match(elements.resultView.innerHTML,/Scientific review/);
 assert.equal(vm.runInContext('selectedResult.job.revision_id',ctx),rid);
 // A history outage must immediately hide already inspected evidence.
 const unavailable=vm.runInContext('refreshRuns()',ctx);
 pending[3].reject(Error('HTTP 503 offline'));await unavailable;
 assert.equal(vm.runInContext('selectedResult',ctx),null);
 assert.match(elements.resultView.textContent,/history unavailable/);
 const before=pending.length;
 await vm.runInContext('inspectResult(job.id)',ctx);
 assert.equal(pending.length,before,'inspection denied while history is disconnected');
 // Even if the same run ID returns, a changed engine/study cannot retain old HTML.
 const recovery=vm.runInContext('refreshRuns()',ctx);
 pending[4].resolve({runs:[{...job,engine:'sqdmetal_palace'}]});await recovery;
 assert.equal(vm.runInContext('runHistoryError',ctx),'');
 assert.equal(vm.runInContext('selectedResult',ctx),null);
 // No stale evidence can survive a normal render even with a same-ID run.
 vm.runInContext('selectedResult={projectId:project.id,id:job.id,job,html:"OLD_VERIFIED_HTML"}',ctx);
 assert.doesNotMatch(vm.runInContext('renderStep("results")',ctx),/OLD_VERIFIED_HTML/);
 console.log('RC1411_UI_INSPECTION_RACES_PASS changed provenance, stale GET, disconnect and recovery fail closed');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_out_of_order_project_load_cannot_publish_stale_revision_or_history():
    _run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const pending=[],elements={comparisonView:{replaceChildren(){}}};
const ctx=vm.createContext({document:{getElementById:k=>elements[k]},setTimeout,clearTimeout});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
ctx.pending=pending;ctx.renderCalls=[];
vm.runInContext('render=()=>renderCalls.push(project.id);api=path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject}))',ctx);
const a='a'.repeat(32),b='b'.repeat(32);
(async()=>{
 const first=vm.runInContext(`loadProject('${a}')`,ctx);
 const second=vm.runInContext(`loadProject('${b}')`,ctx);
 assert.equal(pending.length,2);
 pending[1].resolve({id:b,head:b});await Promise.resolve();
 assert.equal(pending[2].path,`/api/projects/${b}/runs`);
 pending[2].resolve({runs:[{id:b,state:'completed'}]});await second;
 pending[0].resolve({id:a,head:a});await Promise.resolve();
 assert.equal(pending[3].path,`/api/projects/${a}/runs`);
 pending[3].reject(Error('older history unavailable'));
 assert.equal(await first,false);
 assert.equal(vm.runInContext('project.id',ctx),b);
 assert.equal(vm.runInContext('runs[0].id',ctx),b);
 assert.equal(vm.runInContext('runHistoryError',ctx),'');
 assert.deepEqual(ctx.renderCalls,[b]);
 console.log('RC1411_UI_PROJECT_ORDER_PASS stale project/history cannot overwrite newer revision');
})().catch(e=>{console.error(e);process.exitCode=1});
''')
