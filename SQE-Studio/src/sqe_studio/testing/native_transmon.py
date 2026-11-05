"""Real saved Palace capacitance -> existing reduction -> genuine scqubits."""
from copy import deepcopy
import importlib.util
from importlib import metadata
import json
import os
from pathlib import Path
import time

from .http_session import HttpSession


def configure_solver(root):
    """Reuse operator bindings; never infer executable paths or install a backend."""
    if not (os.environ.get('SQE_PALACE_BINARY') or os.environ.get('SQE_PALACE_WSL_BINARY')):
        path = Path(root) / 'solver_setup.py'
        spec = importlib.util.spec_from_file_location('sqe_transmon_solver_settings', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        settings = module.load_settings()
        if settings['backend'] != 'none':
            module.apply_settings(settings)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('MPLBACKEND', 'Agg')


def reference_declaration():
    """Explicit, unmeasured research inputs; not inferred from the PEC layout."""
    return {
        'schema': 'sqe.conditional-transmon-assumptions.m19.v1',
        'junction_capacitance_fF': 2.,
        'junction_capacitance_convention': 'ADDITIONAL_LUMPED_CJ_NOT_IN_MAXWELL_MATRIX',
        'junction_reference': 'Native workflow reference assumption: additional C_J=2 fF, unmeasured.',
        'josephson': {'quantity': 'EJ_over_h', 'value': 15., 'unit': 'GHz',
                     'reference': 'Native workflow reference assumption: E_J/h=15 GHz, unmeasured.'},
        'ng': 0., 'ncut': 15, 'levels': 4, 'acknowledged': True}


def run_http_chain(session, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    project = session.request(f'/api/projects/{session.pid}')
    model = deepcopy(project['model'])
    # Test-only acknowledgement of explicitly listed research inputs.
    model['process']['source'] = 'reviewed'
    model['studies'][0]['inputs']['em']['ground']['verified'] = True
    revision = session.request(f'/api/projects/{session.pid}/commit',
        {'expected_revision': project['head'], 'model': model})['revision']
    queued = session.request(f'/api/projects/{session.pid}/runs',
        {'revision': revision, 'study_id': 'TransmonCapacitance'})
    source_run = queued['run_id']
    print('NATIVE_TRANSMON_STAGE saved_capacitance_queued ' + source_run, flush=True)
    capacitance = session.wait(source_run, time.monotonic() + 1000)
    if capacitance['manifest']['artifact_type'] != 'palace.capacitance_matrix':
        raise ValueError('NATIVE_CAPACITANCE_RESULT_REQUIRED')
    artifacts = {item['name'] for item in capacitance['manifest']['artifacts']}
    if not {'sqe_em/capacitance-identity.json', 'sqe_em/capacitance-origin.json'} <= artifacts:
        raise ValueError('NATIVE_CONDUCTOR_IDENTITY_EVIDENCE_REQUIRED')
    current = session.request(f'/api/projects/{session.pid}')
    payload = {'expected_revision': current['head'], 'action': 'preview',
               'declaration': reference_declaration()}
    extraction_url = f'/api/projects/{session.pid}/runs/{source_run}/extraction'
    preview = session.request(extraction_url, payload)
    if (preview['solver_execution'] != 'NOT_EXECUTED'
            or preview['extraction']['source_result_metadata']['execution_kind'] == 'SOFTWARE_FIXTURE'):
        raise ValueError('SOURCE_MUST_BE_THE_REAL_SAVED_PALACE_RUN')
    queued = session.request(extraction_url, {**payload, 'action': 'execute'})
    if queued['status'] != 'CONDITIONAL_NATIVE_JOB_QUEUED':
        raise ValueError('NATIVE_QUANTIZATION_NOT_QUEUED')
    quantum_run = queued['run_id']
    print('NATIVE_TRANSMON_STAGE saved_quantization_queued ' + quantum_run, flush=True)
    quantum = session.wait(quantum_run, time.monotonic() + 200)
    extraction, spectrum = quantum['conditional_extraction'], quantum['spectrum']
    if (extraction['source']['run_id'] != source_run
            or extraction['extraction_sha256'] != preview['extraction']['extraction_sha256']
            or spectrum['extraction_sha256'] != extraction['extraction_sha256']
            or quantum['manifest']['revision_id'] != queued['revision']
            or spectrum['convergence']['numeric_status'] != 'NUMERICAL_PASS'
            or extraction['spectrum_diagnostics']['status'] != 'NUMERICAL_PASS'):
        raise ValueError('NATIVE_QUANTUM_LINEAGE_OR_NUMERICAL_CHECK_FAILED')
    (folder / 'capacitance-result.json').write_text(json.dumps(capacitance, indent=2), encoding='utf-8')
    (folder / 'quantum-result.json').write_text(json.dumps(quantum, indent=2), encoding='utf-8')
    levels = spectrum['levels']
    result = {'status': 'PASS', 'execution_kind': 'NATIVE_PALACE_SCQUBITS_AUTHENTICATED_HTTP',
        'native_palace_execution': 'PASS', 'native_quantum_execution': 'PASS',
        'real_browser': 'NOT_RUN', 'source_run_id': source_run, 'quantum_run_id': quantum_run,
        'source_revision': revision, 'quantum_revision': queued['revision'],
        'parameters': extraction['parameters'], 'capacitances': extraction['capacitances'],
        'f01_GHz': levels[1] - levels[0],
        'anharmonicity_GHz': levels[2] - 2*levels[1] + levels[0],
        'basis_convergence': spectrum['convergence'],
        'approximation_comparison': extraction['spectrum_diagnostics'],
        'source': extraction['source'], 'native_source_hashes': extraction['native_source_hashes'],
        'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    session.source_run = source_run
    session.quantum_run = quantum_run
    session.extraction_url = extraction_url
    return result


def run_workflow(root, folder):
    """All required native stages must pass; never fall back to the EM fixture."""
    missing = [name for name in ('SQDMetal', 'qiskit_metal', 'gmsh', 'scqubits', 'playwright')
               if importlib.util.find_spec(name) is None]
    if missing:
        return {'status': 'BLOCKED', 'reason': 'NATIVE_TRANSMON_TOOLS_MISSING',
                'missing_tools': missing, 'native_palace_execution': 'NOT_RUN',
                'native_quantum_execution': 'NOT_RUN', 'real_browser': 'NOT_RUN',
                'em_source_kind': 'NO_FIXTURE_FALLBACK', 'scientific_qualification': 'NOT_ESTABLISHED'}
    from ..adapters.base import EngineBlocked
    from ..adapters.sqdmetal_palace_adapter import _palace_readiness
    from ..adapters.scqubits_adapter import SCQUBITS_NUMERICAL_PIN
    if metadata.version('scqubits') != SCQUBITS_NUMERICAL_PIN:
        return {'status': 'BLOCKED', 'reason': 'SCQUBITS_COMPATIBILITY_PIN_MISMATCH',
                'native_palace_execution': 'NOT_RUN', 'native_quantum_execution': 'NOT_RUN'}
    stages = {}
    began = time.monotonic()
    try:
        configure_solver(root)
        _palace_readiness()
    except (EngineBlocked, OSError, ValueError) as error:
        return {'status': 'BLOCKED', 'reason': 'PALACE_BACKEND_UNAVAILABLE',
                'diagnostic': str(error)[:1500], 'native_palace_execution': 'NOT_RUN',
                'native_quantum_execution': 'NOT_RUN', 'real_browser': 'NOT_RUN',
                'scientific_qualification': 'NOT_ESTABLISHED'}
    from .palace_reference import run_reference
    from .transmon_browser import run_browser_chain, NativeBrowserUnavailable
    from .transmon_evidence import package_evidence
    from .transmon_guards import verify_guards
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        stages['reference'] = run_reference(root, folder / 'reference')
        if stages['reference']['status'] != 'PASS':
            return {'status': 'FAIL', 'reason': 'OFFICIAL_ELECTROSTATIC_REFERENCE_FAILED', **stages}
        with HttpSession(folder / 'workspace') as session:
            stages['http'] = run_http_chain(session, folder / 'workflow')
            stages['browser'] = run_browser_chain(session, root, folder / 'workflow')
            stages['guards'] = verify_guards(session)
            sensitivity = (stages['browser']['parameters']['EC'] < stages['http']['parameters']['EC']
                           and stages['browser']['f01_GHz'] < stages['http']['f01_GHz'])
            if not sensitivity:
                raise ValueError('ADDITIONAL_JUNCTION_CAPACITANCE_SENSITIVITY_FAILED')
            result = {'status': 'PASS', 'execution_kind': 'NATIVE_PALACE_SCQUBITS_HTTP_AND_REAL_BROWSER',
                'em_source_kind': 'FRESH_SAVED_NATIVE_PALACE_SOLVE', **stages,
                'native_palace_execution': 'PASS', 'native_quantum_execution': 'PASS',
                'real_browser': 'PASS', 'additional_CJ_sensitivity': 'PASS',
                'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD',
                'duration_s': round(time.monotonic() - began, 3)}
            runs = [stages['http']['source_run_id'], stages['http']['quantum_run_id'],
                    stages['browser']['source_run_id'], stages['browser']['quantum_run_id']]
            result['native_evidence'] = package_evidence(session, folder, runs, result)
            return result
    except NativeBrowserUnavailable as error:
        return {'status': 'BLOCKED', 'reason': str(error), **stages,
                'real_browser': 'NOT_RUN', 'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    except TimeoutError as error:
        return {'status': 'TIMEOUT', 'reason': str(error)[:1000], **stages,
                'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    except Exception as error:
        return {'status': 'FAIL', 'reason': type(error).__name__, 'diagnostic': str(error)[-12000:],
                **stages, 'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
