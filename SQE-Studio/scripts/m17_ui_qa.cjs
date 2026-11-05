/* Software-fixture tests of the production renderer; no native physics claim. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const code = require('./ui_source.cjs')(path.join(root, 'src/sqe_studio/web/app.js'));
new vm.Script(code); // Whole application syntax, without running browser initialization.
const start = code.indexOf('function nativeSpectrum(data)');
const end = code.indexOf('/* Generic property inspectors', start);
assert(start > 0 && end > start);
const context = vm.createContext({
  esc: x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  pane: (title, subtitle, body) => `<section><h3>${title}</h3><p>${subtitle}</p>${body}</section>`
});
vm.runInContext(code.slice(start, end), context);
const fixture = {
  convergence: {steps:3,status:'checked_passed',tolerance_GHz:1e-5,points:[{
    basis_parameter:'ncut',curve:[15,20,25,30].map((n,i)=>({
      basis_cutoff:n,basis_dimension:2*n+1,f01_GHz:5+(.01/(i+1)),
      anharmonicity_GHz:-.25,transitions_from_ground_GHz:[5,9.75,14.25],
      max_adjacent_delta_GHz:i?1e-6:null
    }))}]
  }
};
let passed = 0;
const test = (name, run) => {run(); passed++; console.log('PASS '+name);};
test('renders all four basis rows and numeric status',()=>{
  const html=context.basisConvergenceView(fixture);
  assert(html.includes('NUMERICAL_PASS'));
  assert(html.includes('15</td>')&&html.includes('30</td>'));
  assert(html.includes('Max adjacent transition drift · kHz'));
  assert(!html.includes('NaN')&&!html.includes('Infinity'));
});
test('nonconvergence remains visible with the curve',()=>{
  const bad=JSON.parse(JSON.stringify(fixture));bad.convergence.status='checked_failed';
  assert(context.basisConvergenceView(bad).includes('NUMERICAL_FAIL'));
});
test('malformed cutoff or field cannot produce a chart',()=>{
  const bad=JSON.parse(JSON.stringify(fixture));bad.convergence.points[0].basis_parameter='<script>';
  const html=context.basisConvergenceView(bad);assert(html.includes('Invalid native basis curve'));assert(!html.includes('<svg'));
});
test('nonfinite values are rejected before SVG coordinates',()=>{
  const bad=JSON.parse(JSON.stringify(fixture));bad.convergence.points[0].curve[2].f01_GHz=Infinity;
  assert(!context.basisConvergenceView(bad).includes('<svg'));
});
test('legacy spectrum has no invented curve',()=>assert.equal(context.basisConvergenceView({convergence:{status:'not_checked'}}),''));
const fieldStart=code.indexOf('function upstreamFieldDiagnosticView(diag)');
const fieldEnd=code.indexOf('function goStep(next)',fieldStart);
assert(fieldStart>0&&fieldEnd>fieldStart);
vm.runInContext(code.slice(fieldStart,fieldEnd),context);
const fields={schema:'sqe.upstream-vtk-cycles.experimental.v2',status:'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED',
 physical_mode_identity:'NOT_ESTABLISHED',mesh_convergence:'NOT_ESTABLISHED',field_values_in_report:false,
 backend:'PyVista',backend_version:'0.49.2',cycles:[
 {cycle_index_not_mode_identity:0,mpi_piece_count:4,role:'COMPLEX_E_FIELD',blocks:[{point:{E_real:'FLOAT_VECTOR_3',E_imag:'FLOAT_VECTOR_3'},cell:{}}]},
 {cycle_index_not_mode_identity:1,mpi_piece_count:4,role:'AUXILIARY_MESH_DATA',blocks:[{point:{},cell:{Rank:'NUMERIC_SCALAR',Indicator:'NUMERIC_SCALAR'}}]}]};
test('field and auxiliary outputs are visibly distinct',()=>{
 const html=context.upstreamFieldDiagnosticView(fields);
 assert(html.includes('Complex E field declarations')&&html.includes('Auxiliary mesh data'));
 assert(html.includes('Rank (cell)')&&html.includes('Output cycle (not a mode)'));
 assert(html.includes('remain unvalidated'));
});
test('unclassified or incomplete outputs stay visible',()=>{
 const bad=JSON.parse(JSON.stringify(fields));bad.status='UPSTREAM_COMPLEX_E_NOT_ESTABLISHED';bad.cycles[1].role='UNCLASSIFIED';
 assert(context.upstreamFieldDiagnosticView(bad).includes('Unclassified output'));
 bad.cycles[1].role='INCOMPLETE_OR_UNSUPPORTED_FIELD';
 assert(context.upstreamFieldDiagnosticView(bad).includes('Incomplete or unsupported field'));
});
test('old diagnostic is shown without invented cycle roles',()=>{
 const old=JSON.parse(JSON.stringify(fields));old.schema='sqe.m16.upstream-vtk-declarations.experimental.v1';
 const html=context.upstreamFieldDiagnosticView(old);
 assert(html.includes('Legacy observation; role unclassified'));assert(!html.includes('Complex E field declarations'));
});
test('diagnostic strings are escaped and unknown roles rejected',()=>{
 const bad=JSON.parse(JSON.stringify(fields));bad.backend='<img src=x onerror=alert(1)>';
 const html=context.upstreamFieldDiagnosticView(bad);assert(!html.includes('<img'));assert(html.includes('&lt;img'));
 bad.cycles[0].role='<script>';assert.throws(()=>context.upstreamFieldDiagnosticView(bad));
});
test('scientific promotion in a response is rejected',()=>{
 const bad=JSON.parse(JSON.stringify(fields));bad.mesh_convergence='PASS';
 assert.throws(()=>context.upstreamFieldDiagnosticView(bad));
});
console.log(JSON.stringify({renderer_tests_passed:passed,execution_kind:'SOFTWARE_FIXTURE',real_browser:'NOT_RUN',native_scientific_validation:'NOT_RUN'}));
