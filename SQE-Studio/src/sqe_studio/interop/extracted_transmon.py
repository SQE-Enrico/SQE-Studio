"""M19: authenticated native capacitance -> explicitly conditional scqubits.

This separate research interface NEVER labels extracted EC as independent input
or approves the frozen A01/A12 physical transfer. Store resolves the source;
the isolated worker reopens and verifies its immutable native artifacts.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import re
import sys
import time

from ..contracts import digest, validate_project
from ..orchestration.artifacts import MAX_MANIFEST_BYTES, safe_file, valid_sha, verify_manifest
from .transmon_workflow import inspect_saved_transmon_screen

KIND = 'extracted_transmon_research'
INPUT_SCHEMA = 'sqe.extracted-transmon-input.m19.v1'
DECLARATION_SCHEMA = 'sqe.conditional-transmon-assumptions.m19.v1'
CONTEXT_SCHEMA = 'sqe.extraction-worker-context.m19.v1'
RESULT_SCHEMA = 'sqe.conditional-transmon-extraction.m19.v1'
CONVENTION = 'ADDITIONAL_LUMPED_CJ_NOT_IN_MAXWELL_MATRIX'
_ID = re.compile(r'[0-9a-f]{32}\Z')
_SOURCE_KEYS = {'run_id', 'revision_id', 'project_digest', 'manifest_sha256', 'study_id'}
_E = 1.602176634e-19
_H = 6.62607015e-34


class ExtractionBlocked(ValueError):
    pass


def _require(test, message):
    if not test:
        raise ExtractionBlocked(message)


def _number(value, label, low, high):
    _require(type(value) in (int, float), label + ': finite number required')
    try:
        okay = math.isfinite(value) and low <= value <= high
    except (ValueError, OverflowError):
        okay = False
    _require(okay, label + ': outside finite bounds')
    return float(value)


def _reference(value, label):
    _require(type(value) is str and 3 <= len(value.strip()) <= 400 and
             all(ord(c) >= 32 for c in value), label + ': explicit designer provenance required')
    return value.strip()


def validate_declaration(raw):
    keys = {'schema', 'junction_capacitance_fF', 'junction_capacitance_convention',
            'junction_reference', 'josephson', 'ng', 'ncut', 'levels', 'acknowledged'}
    _require(type(raw) is dict and set(raw) == keys and
             raw.get('schema') == DECLARATION_SCHEMA and raw.get('acknowledged') is True,
             'Exact conditional model declaration and acknowledgment required')
    _require(raw['junction_capacitance_convention'] == CONVENTION,
             'C_J must be additional to the electrostatic matrix; double counting is unsupported')
    cj = _number(raw['junction_capacitance_fF'], 'C_J / fF', 0, 1000)
    ref = _reference(raw['junction_reference'], 'C_J provenance')
    jj = raw['josephson']
    _require(type(jj) is dict and set(jj) == {'quantity', 'value', 'unit', 'reference'},
             'Declare E_J/h or L_J with its own unit and provenance')
    q = jj['quantity']
    _require((q, jj['unit']) in (('EJ_over_h', 'GHz'), ('LJ', 'nH')),
             'Josephson input must be E_J/h in GHz or L_J in nH')
    value = _number(jj['value'], q, 1e-6, 1000)
    ej = value if q == 'EJ_over_h' else (_H/(16*math.pi**2*_E**2))/(value*1e-9)/1e9
    # EJ = (Phi0 / 2pi)^2 / LJ; Phi0 = h / 2e. Energies are E/h.
    _require(math.isfinite(ej) and 0 < ej <= 1000, 'Josephson energy exceeds native GHz bounds')
    jref = _reference(jj['reference'], 'Josephson provenance')
    ng = _number(raw['ng'], 'ng / 2e', -10, 10)
    _require(type(raw['ncut']) is int and 6 <= raw['ncut'] <= 60,
             'ncut must be an integer in [6,60]')
    _require(type(raw['levels']) is int and 3 <= raw['levels'] <= 6,
             'levels must be an integer in [3,6]')
    return {'schema': DECLARATION_SCHEMA, 'junction_capacitance_fF': cj,
            'junction_capacitance_convention': CONVENTION, 'junction_reference': ref,
            'josephson': {'quantity': q, 'value': value, 'unit': jj['unit'], 'reference': jref},
            'ng': ng, 'ncut': raw['ncut'], 'levels': raw['levels'], 'acknowledged': True}, ej


def validate_inputs(inputs):
    _require(type(inputs) is dict and set(inputs) == {'schema', 'source', 'assumptions'} and
             inputs.get('schema') == INPUT_SCHEMA, 'Exact M19 extraction input schema required')
    source = inputs['source']
    _require(type(source) is dict and set(source) == _SOURCE_KEYS,
             'Only a server-bound capacitance source selector is accepted')
    _require(all(type(source[k]) is str and _ID.fullmatch(source[k]) for k in ('run_id','revision_id'))
             and all(valid_sha(source[k]) for k in ('project_digest','manifest_sha256'))
             and type(source['study_id']) is str and 1 <= len(source['study_id']) <= 128,
             'Invalid saved source identity or SHA-256')
    declaration, ej = validate_declaration(inputs['assumptions'])
    _require(inputs['assumptions'] == declaration, 'Save normalized assumptions before execution')
    return source, declaration, ej


def _context_projection(model, study_id):
    studies = [s for s in model['studies'] if s['id'] == study_id]
    _require(len(studies) == 1 and studies[0]['engine'] == 'sqdmetal_palace' and
             studies[0]['kind'] == 'capacitance', 'Original capacitance study is missing or changed')
    return {**{k: model[k] for k in ('family','schematic','process','layout')},
            'selection': model['intent'].get('transmon_capacitance_selection'),
            'source_study': studies[0]}


def resolve_source(store, owner, project_id, project, run_id):
    """Only Store-authenticated run IDs, never client-supplied paths or matrices."""
    _require(type(run_id) is str and _ID.fullmatch(run_id), 'Invalid source run ID')
    info = store.run(owner, project_id, run_id)
    _require(info['state'] == 'completed' and info['engine'] == 'sqdmetal_palace',
             'Source must be a completed Palace capacitance run')
    folder = Path(info['path'])
    expected = store.root/'native-runs'/project_id/run_id
    _require(folder.absolute() == expected.absolute() and not folder.is_symlink() and
             expected.resolve().is_relative_to(store.root.resolve()) and
             all(not p.is_symlink() for p in (expected.parent, expected.parent.parent, folder/'output')),
             'Source run path is outside the authenticated native workspace')
    source_project = store.project(owner, project_id, info['revision_id'])
    output = folder/'output'
    manifest_file = safe_file(output, 'RESULT_MANIFEST.json')
    _require(manifest_file.stat().st_size<=MAX_MANIFEST_BYTES,'Source manifest exceeds bounded inspection limit')
    source = {'run_id': run_id, 'revision_id': source_project['revision'],
              'project_digest': source_project['revision_digest'], 'study_id': info['study_id'],
              'manifest_sha256': hashlib.sha256(manifest_file.read_bytes()).hexdigest()}
    context = {'schema': CONTEXT_SCHEMA, 'source': source,
               'source_project': {k: source_project[k] for k in ('revision','revision_digest','model')},
               'source_output': str(output.absolute())}
    # Verify before any cache hit or study creation, not just in the worker.
    inspect_source(project['model'], source, context)
    return context


def inspect_source(current_model, expected_source, context):
    _require(type(context) is dict and set(context) ==
             {'schema','source','source_project','source_output'} and
             context.get('schema') == CONTEXT_SCHEMA and context.get('source') == expected_source,
             'Missing or mismatched trusted extraction worker context')
    saved = context['source_project']
    _require(type(saved) is dict and set(saved) == {'revision','revision_digest','model'},
             'Immutable source project snapshot required')
    validate_project(saved['model'])
    _require(saved['revision'] == expected_source['revision_id'] and
             saved['revision_digest'] == expected_source['project_digest'] == digest(saved['model']),
             'Source revision content digest mismatch')
    sid = expected_source['study_id']
    _require(_context_projection(current_model,sid) == _context_projection(saved['model'],sid),
             'STALE_EXTRACTION_CONTEXT: layout, process, circuit, selection or EM study changed')
    output = Path(context['source_output'])
    _require(output.is_absolute() and not output.is_symlink(), 'Unsafe extraction source folder')
    mf = safe_file(output, 'RESULT_MANIFEST.json')
    _require(mf.stat().st_size<=MAX_MANIFEST_BYTES,'Source manifest exceeds bounded inspection limit')
    _require(hashlib.sha256(mf.read_bytes()).hexdigest() == expected_source['manifest_sha256'],
             'Capacitance source manifest changed')
    verify_manifest(output, revision_id=saved['revision'], project_digest=saved['revision_digest'],
                    study_id=sid, engine='sqdmetal_palace')
    manifest = json.loads(mf.read_text(encoding='utf-8'))
    _require(manifest.get('artifact_type') == 'palace.capacitance_matrix',
             'Eigenmode/deck-only results cannot supply a capacitance extraction')
    screen = inspect_saved_transmon_screen(output, manifest, saved)
    _require(isinstance(screen,dict) and screen.get('status') == 'NUMERICAL_SCREEN_ONLY',
             'Save explicit conductor selection in the source revision before its Palace run')
    screen['source_result_metadata'] = {'engine_version':manifest['engine_version'],
        'execution_kind':manifest.get('provenance',{}).get('execution_kind','NATIVE_ARTIFACT_READBACK_UNREVIEWED'),
        'new_palace_solve':'NOT_RUN'}
    return screen


def build_extraction(inputs, current_model, context):
    source, declaration, ej = validate_inputs(inputs)
    screen = inspect_source(current_model, source, context)
    preview = screen['reduction']['numerical_preview']
    cm = float(preview['effective_capacitance_f'])
    cj = declaration['junction_capacitance_fF']*1e-15
    total = cm+cj
    ec = _E**2/(2*_H*total)/1e9
    from ..adapters.scqubits_adapter import _parameters
    parameters = _parameters('Transmon', {'EJ':ej,'EC':ec,'ng':declaration['ng'],
                             'ncut':declaration['ncut'],'truncated_dim':max(6,declaration['levels'])},
                             None, 'conditional extracted Transmon')
    result = {'schema': RESULT_SCHEMA, 'status':'CONDITIONAL_RESEARCH_MODEL_READY',
              'parameter_origin':'EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS',
              'source':deepcopy(source), 'native_source_hashes':screen['native_topology']['source'],
              'source_result_metadata':screen['source_result_metadata'],
              'saved_selection':deepcopy(context['source_project']['model']['intent']['transmon_capacitance_selection']),
              'matrix_reduction':deepcopy(preview), 'assumptions':declaration,
              'capacitances':{'matrix_effective_F':cm,'additional_junction_F':cj,'total_F':total},
              'parameters':parameters, 'parameter_units':{'EJ':'GHz','EC':'GHz','ng':'2e','ncut':'1','truncated_dim':'1'},
              'EJ_over_EC':ej/ec, 'input_sha256':digest(inputs),
              'formulas':{'C_total':'C_matrix_effective + C_J (additional only)',
                          'EC_over_h':'e^2 / (2 h C_total)',
                          'EJ_over_h_from_LJ':'(h/(2e)/(2pi))^2 / (h L_J)',
                          'constants_SI':{'e_C':_E,'h_J_s':_H}},
              'basis_policy':{'enabled':True,'basis_increment':5,'steps':3,'tolerance_GHz':1e-5},
              'unresolved':['Independent QDesign-to-Gmsh conductor/ground registration',
                            'Electrostatic mesh and domain convergence / material uncertainty',
                            'Physical validity of the static single-mode circuit reduction',
                            'Junction C_J and E_J/L_J designer assumptions, not measured here',
                            'Dynamical coupling, multimode EPR, losses, Purcell and experimental validation'],
              'scientific_qualification':'NOT_ESTABLISHED','reviewed_A01_transfer':'BLOCKED',
              'fabrication':'HOLD'}
    result['extraction_sha256'] = digest(result)
    return result


def study_template(context, declaration):
    declaration, _ = validate_declaration(declaration)
    return {'engine':'scqubits','kind':KIND,
            'inputs':{'schema':INPUT_SCHEMA,'source':deepcopy(context['source']),'assumptions':declaration}}


def validate_saved_result(extraction, spectrum, study):
    """Structural binding after the Results API rehashes every native file."""
    _require(study.get('engine')=='scqubits' and study.get('kind')==KIND,
             'Conditional output must belong to its saved research study')
    source, assumptions, _ = validate_inputs(study['inputs'])
    _require(isinstance(extraction,dict) and isinstance(spectrum,dict) and
             extraction.get('schema')==RESULT_SCHEMA and extraction.get('source')==source and
             extraction.get('assumptions')==assumptions and
             extraction.get('input_sha256')==spectrum.get('input_sha256')==digest(study['inputs']) and
             extraction.get('scientific_qualification')=='NOT_ESTABLISHED' and
             extraction.get('reviewed_A01_transfer')=='BLOCKED' and extraction.get('fabrication')=='HOLD' and
             extraction.get('parameter_origin')==spectrum.get('parameter_origin')==
                'EM_DERIVED_WITH_DECLARED_JUNCTION_ASSUMPTIONS',
             'Conditional spectrum, saved inputs and extraction provenance disagree')
    body={k:v for k,v in extraction.items() if k not in
          ('extraction_sha256','spectrum_diagnostics','solver_execution')}
    _require(extraction.get('extraction_sha256')==spectrum.get('extraction_sha256')==digest(body),
             'Conditional model hash mismatch')
    return extraction


def run(study, model, output_dir, context):
    """Separate v2 worker dispatch; same upstream Transmon and basis machinery."""
    from ..adapters import scqubits_adapter as native
    from ..adapters.base import EngineBlocked, require_module, safe_output
    _require(study.get('engine') == 'scqubits' and study.get('kind') == KIND,
             'Wrong extraction study engine/kind')
    started = time.perf_counter()
    extraction = build_extraction(study['inputs'],model,context)
    output = safe_output(output_dir)
    names = ('input_snapshot.json','extraction.json','spectrum.json')
    _require(all(not (output/n).exists() and not (output/n).is_symlink() for n in names),
             'Refusing to overwrite conditional quantization results')
    require_module('scqubits','scqubits')
    try:
        import scqubits as scq
        version = metadata.version('scqubits')
    except (ImportError,OSError,metadata.PackageNotFoundError) as exc:
        raise EngineBlocked('Native scqubits unavailable: '+type(exc).__name__) from exc
    _require(version == native.SCQUBITS_NUMERICAL_PIN,'Unsupported native scqubits version')
    scq.set_units('GHz')
    _require(scq.get_units() == 'GHz','Native scqubits GHz convention unavailable')
    spec = {'model':'Transmon','groups':[{'id':'primary','model':'Transmon','parameters':extraction['parameters']}],
            'interactions':[],'levels':study['inputs']['assumptions']['levels'], 'sweep':None,
            'convergence':extraction['basis_policy'],
            'source':'conditional_extracted_research','context_sha256':digest(_context_projection(model,context['source']['study_id'])),
            'composite_dim':None}
    energies, _, curves = native._execute(scq,spec)
    # Catch source mutations during native quantization before publishing.
    inspect_source(model,study['inputs']['source'],context)
    curve = curves[0]
    passed = curve['status'] == 'checked_passed'
    convergence = {**extraction['basis_policy'], 'status':curve['status'],
                   'numeric_status':'NUMERICAL_PASS' if passed else 'NUMERICAL_FAIL',
                   'max_delta_GHz':curve['max_delta_GHz'], 'criterion':curve['criterion'],
                   'checked_points':1,'points':curves,
                   'scientific_scope':'Finite cutoff stability only; no EM or physical model qualification'}
    spectrum = {'schema':'sqe.scqubits.spectrum.v1','artifact_type':'scqubits.spectrum',
                'engine':'scqubits','engine_version':version,'model':'Transmon',
                'energy_unit':'GHz','units':'GHz','axis':None,'levels':energies[0],
                'energy_table':energies,'preview_point_index':0,'convergence':convergence,
                'source':'native scqubits eigenvals', 'parameter_origin':extraction['parameter_origin'],
                'input_sha256':digest(study['inputs']),'extraction_sha256':extraction['extraction_sha256'],
                'scientific_status':'review_required','elapsed_seconds':time.perf_counter()-started}
    from ..eda.scientific_references import compare_transmon_asymptote
    extraction['spectrum_diagnostics'] = compare_transmon_asymptote(
        extraction['parameters']['EJ'],extraction['parameters']['EC'],energies[0])
    extraction['solver_execution'] = 'NATIVE_SCQUBITS'
    snapshot = {'schema':'sqe.extracted-transmon-native-input.m19.v1',
                'study_sha256':digest(study),'project_sha256':digest(model),
                'extraction_sha256':spectrum['extraction_sha256'],'input':deepcopy(study['inputs']),
                'resolved_parameters':extraction['parameters'],
                'native_versions':{'scqubits':version,'python':sys.version.split()[0]}}
    for package in ('numpy','scipy','qutip'):
        try:
            snapshot['native_versions'][package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            snapshot['native_versions'][package] = 'not-reported'
    documents = dict(zip(names,(snapshot,extraction,spectrum)))
    for document in documents.values():
        native._canonical(document)
    for name,document in documents.items():
        native._write(output/name,document)
    return {'engine_version':version,'native_files':list(names),'kind':KIND,
            'artifact_type':'scqubits.spectrum','scientific_status':'review_required'}
