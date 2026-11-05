"""RC14.10 A14: execute production UI logic without forging native results.

Node tests are controller/UI assertions, never substitutes for real Playwright,
HTTP content verification, native CAD, physical mode identity or optimization.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'web' / 'app.js'


def _node(script: str):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable: production JS controller verification BLOCKED')
    result = subprocess.run([node, '-e', script, str(WEB)], capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, (result.stdout, result.stderr)
    print(result.stdout.strip())


def test_cad_lineage_signed_ports_and_review_gates():
    _node(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const ctx=vm.createContext({});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const hash='f'.repeat(64),id='a'.repeat(32),rev='b'.repeat(32);
const cad=vm.runInContext('nativeCADLineageView',ctx)({engine:'quantum_metal',project_digest:hash,
 artifacts:[{name:'real.gds',sha256:hash},{name:'<svg onload=alert(1)>.gds',sha256:hash}]},{id,revision_id:rev});
assert.match(cad,/2 file\(s\) recorded/);
assert.match(cad,/GDS → Gmsh mapping/);
assert.match(cad,/BLOCKED/);
assert.match(cad,/HOLD/);
assert.doesNotMatch(cad,/<svg/);
assert.equal(vm.runInContext('nativeCADLineageView',ctx)({engine:'scqubits'}, {id,revision_id:rev}), '');
const em={schema:'sqe.em-native-results-screen.v1',mode_identity:'UNRESOLVED',
 em_to_hamiltonian:'BLOCKED',automatic_geometry_optimization:'BLOCKED',fabrication:'HOLD',
 field_acquisition:{status:'NOT_EXPORTED',artifact_count:0,common_coordinate_domain_verified:false,
 complex_vector_normalization_verified:false},limitations:[],modes:[{
 native_mode_index:1,frequency_GHz:6,q_total:123,ports:[
 {port_index:1,q_ext:14,native_kappa_ext_GHz:-0.02,advisory:'Review signed convention'}]}]};
const rendered=vm.runInContext('nativeEMEvidenceView',ctx)(em);
assert.match(rendered,/-0.02/);
assert.match(rendered,/Signed κ review required/);
assert.match(rendered,/without absolute-value conversion/);
assert.match(rendered,/NOT VERIFIED/);
assert.doesNotMatch(rendered,/mode matching confirmed|convergence passed/);
console.log('B01_UI_REVIEW_PASS CAD hashes displayed without physical lineage approval; native port sign preserved');
''')


def test_comparison_binding_invalidates_stale_or_unverified_responses():
    _node(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=require(require('path').resolve(require('path').dirname(process.argv[1]),'../../../scripts/ui_source.cjs'))(process.argv[1]);
const l='a'.repeat(32),r='b'.repeat(32),pid='c'.repeat(32),rev='d'.repeat(32),sha='e'.repeat(64);
const elements={compareLeft:{value:l},compareRight:{value:r},comparisonView:{innerHTML:'stale',
 replaceChildren(){this.innerHTML='';}}};
const ctx=vm.createContext({document:{getElementById:key=>elements[key]},setTimeout,clearTimeout});
vm.runInContext(source.replace(/start\(\);\s*$/,''),ctx);
const notices=[];ctx.notices=notices;vm.runInContext('toast=(s)=>notices.push(s)',ctx);
vm.runInContext(`project={id:'${pid}',head:'${rev}'};step=5;runs=[
 {id:'${l}',revision_id:'${rev}',engine:'scqubits',study_id:'T1',state:'completed'},
 {id:'${r}',revision_id:'${rev}',engine:'scqubits',study_id:'T1',state:'completed'}];runHistoryError='';`,ctx);
const makeSide=id=>({run_id:id,revision_id:rev,engine:'scqubits',study_id:'T1',
 project_sha256:sha,fabrication_status:'HOLD',native_version:'test-only',artifact_type:'scqubits.spectrum',scientific_status:'review_required'});
const response={schema:'sqe.expert-comparison.v1',status:'read_only_expert_review_not_scientifically_qualified',
 left:makeSide(l),right:makeSide(r),same_revision:true,same_output_type:true,
 design_input_changes:{total:0,shown:[],truncated:false},
 numerical_comparison:{status:'not_comparable',reason:'fixture only',rows:[]},caveats:['fixture cannot verify science']};
assert.equal(vm.runInContext('comparisonProvenanceValid',ctx)(response,
 {id:l,revision_id:rev,engine:'scqubits',study_id:'T1'},
 {id:r,revision_id:rev,engine:'scqubits',study_id:'T1'}),true);
assert.equal(vm.runInContext('comparisonProvenanceValid',ctx)({...response,left:{...response.left,run_id:r}},
 {id:l,revision_id:rev,engine:'scqubits',study_id:'T1'},
 {id:r,revision_id:rev,engine:'scqubits',study_id:'T1'}),false);
const pending=[];ctx.pending=pending;
vm.runInContext('api=async()=>new Promise((resolve,reject)=>pending.push({resolve,reject}))',ctx);
(async()=>{
 // A stale completed compare must never revive when history goes offline.
 const old=vm.runInContext('compareSavedRuns()',ctx);
 assert.equal(elements.comparisonView.innerHTML,'');
 vm.runInContext("runHistoryError='connection aborted';invalidateComparison()",ctx);
 pending[0].resolve(response);await old;
 assert.equal(elements.comparisonView.innerHTML,'');
 // A reconnect allows a fresh, provenance-bound compare.
 vm.runInContext("runHistoryError=''",ctx);
 const good=vm.runInContext('compareSavedRuns()',ctx);
 pending[1].resolve(response);await good;
 assert.match(elements.comparisonView.innerHTML,/Design iteration gate/);
 assert.match(elements.comparisonView.innerHTML,/fixture cannot verify science/);
 // User switches project while another response is in flight.
 const stale=vm.runInContext('compareSavedRuns()',ctx);
 vm.runInContext("project={id:'f'.repeat(32),head:'0'.repeat(32)};invalidateComparison()",ctx);
 pending[2].resolve(response);await stale;
 assert.equal(elements.comparisonView.innerHTML,'');
 // A server 409 must erase formerly displayed comparison, not leave old evidence.
 vm.runInContext(`project={id:'${pid}',head:'${rev}'}`,ctx);
 const invalid=vm.runInContext('compareSavedRuns()',ctx);
 pending[3].reject(Object.assign(Error('HTTP 409 source rejected'),{status:409}));await invalid;
 assert.equal(elements.comparisonView.innerHTML,'');
 assert.match(notices.at(-1),/409/);
 console.log('B10_UI_COMPARE_PASS stale/history/project/409 responses fail closed; real server verification remains required');
})().catch(e=>{console.error(e);process.exitCode=1});
''')
