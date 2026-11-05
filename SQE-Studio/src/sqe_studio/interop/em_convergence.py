"""Conservative diagnostics for native Palace eigenmode mesh studies.

Only compares already verified native observations. Solver index is not a modal
identity; normalized field overlaps or a separately reviewed physical mode map
are required before a convergence claim. Never fits a limiting frequency.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path

SCHEMA = 'sqe.em-convergence-evidence.v1'
FIELD_SCHEMA = 'sqe.em-convergence-evidence.v2'
MAX_ZIP_MEMBER = 512_000
MAX_ZIP_BYTES = 8_000_000


class ConvergenceEvidenceError(ValueError):
    pass


def palace_log_metrics(log: str) -> dict:
    """Read solver diagnostics from the bounded, actual Palace log, not a mesh estimate."""
    if not isinstance(log, str):
        raise ConvergenceEvidenceError('Palace log must be UTF-8 text')
    # Use the last occurrence if the user report repeats a log as head/tail.
    elements = re.findall(r'^\s*elements\s+\d+\s+\d+\s+\d+\s+(\d+)\s*$', log, re.M)
    memory = re.findall(r'^\s*Estimated peak per-node memory usage is:.*?Total\s+([0-9]+(?:\.[0-9]+)?)([KMG])\s*$', log, re.M)
    elapsed = re.findall(r'^\s*Total\s+([0-9]+(?:\.[0-9]+)?)\s+[0-9.]+\s+[0-9.]+\s*$', log, re.M)
    convergence = bool(re.search(r'Linear eigensolve converged .*?CONVERGED_TOL', log))
    def finite(value):
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    output = {'mesh_elements_3d': int(elements[-1]) if elements else None,
              'peak_memory_GB': None,
              'solver_elapsed_seconds': finite(elapsed[-1]) if elapsed else None,
              'solver_converged_tol_in_log': convergence}
    if memory:
        number, unit = memory[-1]
        multiplier = {'K': 1e-6, 'M': 1e-3, 'G': 1.0}[unit]
        output['peak_memory_GB'] = finite(number)
        if output['peak_memory_GB'] is not None:
            output['peak_memory_GB'] *= multiplier
    return output


def convergence_series(observations: list[dict], metrics: list[dict], *, tolerance: float = 0.02,
                       field_correlation: dict | None = None) -> dict:
    """Compute observations-only numerical drift, with identity explicitly UNRESOLVED."""
    if len(observations) not in (2, 3) or len(metrics) != len(observations):
        raise ConvergenceEvidenceError('Two or three native observations with matching metrics required')
    if type(tolerance) is not float or not math.isfinite(tolerance) or not 0 < tolerance <= 0.2:
        raise ConvergenceEvidenceError('Invalid numeric threshold')
    geometry = observations[0].get('geometry_and_stack_sha256')
    if not isinstance(geometry, str) or len(geometry) != 64:
        raise ConvergenceEvidenceError('Missing native geometry/material digest')
    if any(o.get('geometry_and_stack_sha256') != geometry for o in observations):
        raise ConvergenceEvidenceError('Geometry or material differs between meshes')
    if len({o.get('manifest_sha256') for o in observations}) != len(observations):
        raise ConvergenceEvidenceError('Repeated or missing native manifest digest')
    rows = []
    for i, (obs, log) in enumerate(zip(observations, metrics), 1):
        modes = obs.get('modes')
        if type(modes) is not list or not modes:
            raise ConvergenceEvidenceError('No native modes')
        if modes[0].get('mode_index') != 1:
            raise ConvergenceEvidenceError('Expected first native mode at index 1')
        freq = modes[0].get('frequency_GHz')
        if type(freq) not in (int, float) or not math.isfinite(freq) or freq <= 0:
            raise ConvergenceEvidenceError('Native frequency missing or invalid')
        n = log.get('mesh_elements_3d')
        if n is not None and (type(n) is not int or n <= 0 or (rows and rows[-1]['mesh_elements_3d'] is not None and n <= rows[-1]['mesh_elements_3d'])):
            raise ConvergenceEvidenceError('Mesh count must strictly increase if available')
        rows.append({'point':i, 'native_mode_index':1, 'frequency_GHz':float(freq),
                     'mesh_elements_3d':n, 'peak_memory_GB':log.get('peak_memory_GB'),
                     'solver_elapsed_seconds':log.get('solver_elapsed_seconds'),
                     'solver_converged_tol_in_log':log.get('solver_converged_tol_in_log'),
                     'result_manifest_sha256':obs['manifest_sha256']})
    adjacent = []
    for left, right in zip(rows, rows[1:]):
        delta = right['frequency_GHz']-left['frequency_GHz']
        relative = abs(delta)/max(left['frequency_GHz'],right['frequency_GHz'])
        adjacent.append({'from_point':left['point'],'to_point':right['point'],
                         'delta_MHz':delta*1000,'relative_difference':relative,
                         'numeric_tolerance_met':relative <= tolerance})
    result = {'schema':SCHEMA, 'status':'numerical_indicators_only_mode_identity_unresolved',
            'method':'consecutive native mode-1 frequency differences, not field overlap',
            'geometry_material_digest':geometry,'relative_tolerance':tolerance,
            'points':rows,'adjacent_differences':adjacent,
            'last_step_numeric_threshold_met':adjacent[-1]['numeric_tolerance_met'],
            'mode_identity':'UNRESOLVED_no_verified_field_overlap',
            'mesh_convergence':'NOT_ESTABLISHED',
            'limitations':['An equal native eigenvalue index is not proof of the same physical mode',
                           'Two or three levels cannot establish an asymptotic error estimate without additional assumptions',
                           'Solver CONVERGED_TOL is not mesh convergence',
                           'Mode-shape/field-overlap comparison and expert review still required'],
            'fabrication_status':'HOLD','scientific_qualification':'not_established'}
    return _with_field_diagnostic(result, field_correlation) if field_correlation is not None else result


def _with_field_diagnostic(series: dict, correlation: dict) -> dict:
    """Link the existing bounded visualization DTO, never assign physical modes."""
    from ..eda.upstream_field_compare import validate_result, RECORDED
    try:
        validate_result(correlation)
    except (ValueError, KeyError, TypeError) as exc:
        raise ConvergenceEvidenceError('Invalid sampled-field evidence') from exc
    pair = series['points'][:2]
    available = correlation['status'] == RECORDED
    sources = correlation['sources'] if available else correlation.get('grid_diagnostics', [])
    for point, source in zip(pair, sources):
        if source['result_manifest_sha256'] != point['result_manifest_sha256']:
            raise ConvergenceEvidenceError('Sampled-field evidence belongs to a different ordered native pair')
    result = deepcopy(series)
    result['schema'] = FIELD_SCHEMA
    result['mode_identity'] = 'UNRESOLVED_PHYSICAL_MODE_REVIEW_REQUIRED'
    result['field_evidence_status'] = correlation['status']
    result['field_comparison'] = {'from_point': 1, 'to_point': 2,
        'scope': 'FIRST_NATIVE_PAIR_ONLY', 'result': deepcopy(correlation)}
    result['limitations'][-1] = (
        'Recorded visualization-sample correlation is not a verified physical mode map or FE energy overlap'
        if available else 'Sampled-field comparison unavailable; physical mode review still required')
    result['unresolved_requirements'] = ['PHYSICAL_MODE_IDENTITY_UNRESOLVED',
        'ASYMPTOTIC_MESH_ERROR_NOT_ESTABLISHED', 'VISUALIZATION_METRIC_NOT_FE_ENERGY']
    if not result['last_step_numeric_threshold_met']:
        result['unresolved_requirements'].insert(0, 'LAST_FREQUENCY_THRESHOLD_NOT_MET')
    if not available:
        result['unresolved_requirements'].append('SAMPLED_FIELD_COMPARISON_NOT_RECORDED')
    if len(result['points']) > 2:
        result['unresolved_requirements'].append('FIELD_PAIR_DOES_NOT_COVER_LAST_SCALAR_INTERVAL')
    return result


def frequency_tolerance_sensitivity(observations, metrics, *, thresholds=(0.02,0.03),
                                    recorded_tolerance=None, selected_tolerance=None):
    """Reevaluate the existing scalar criterion, without a new solve or science GO."""
    def valid(value):
        return type(value) in (int,float) and math.isfinite(value) and 0<value<=0.2
    if (type(thresholds) not in (tuple,list) or not 1<=len(thresholds)<=8 or
            any(not valid(t) for t in thresholds) or len(set(thresholds))!=len(thresholds) or
            recorded_tolerance is not None and not valid(recorded_tolerance) or
            selected_tolerance is not None and not valid(selected_tolerance)):
        raise ConvergenceEvidenceError('Invalid bounded frequency criteria')
    criteria=[float(t) for t in thresholds]
    for extra in (recorded_tolerance,selected_tolerance):
        if extra is not None and float(extra) not in criteria:criteria.append(float(extra))
    if len(criteria)>8:raise ConvergenceEvidenceError('Too many frequency criteria')
    evaluations=[];series=None
    for tolerance in criteria:
        series=convergence_series(observations,metrics,tolerance=tolerance)
        evaluations.append({'relative_tolerance':tolerance,
            'last_interval_threshold_met':series['last_step_numeric_threshold_met'],
            'all_intervals_threshold_met':all(d['numeric_tolerance_met'] for d in series['adjacent_differences']),
            'intervals':deepcopy(series['adjacent_differences'])})
    hashes=[p['result_manifest_sha256'] for p in series['points']]
    if any(type(h) is not str or not re.fullmatch(r'[a-f0-9]{64}',h) for h in hashes):
        raise ConvergenceEvidenceError('Invalid frequency analysis source hash')
    return {'schema':'sqe.frequency-tolerance-sensitivity.v1',
        'scope':'ADJACENT_EIGENFREQUENCY_DRIFT_ONLY','source_native_manifest_sha256':hashes,
        'recorded_relative_tolerance':recorded_tolerance,
        'selected_analysis_relative_tolerance':selected_tolerance,
        'analysis_criterion_differs_from_recorded':(None if recorded_tolerance is None or selected_tolerance is None
            else selected_tolerance!=recorded_tolerance),
        'evaluations':evaluations,'new_native_execution':False,
        'development_may_continue':True,'physical_mode_identity':'UNRESOLVED',
        'mesh_convergence':'NOT_ESTABLISHED','scientific_qualification':'not_established','fabrication_status':'HOLD'}


def third_mesh_preflight(coarse: dict, fine: dict, *, memory_limit_gb: float,
                         time_limit_seconds: int) -> dict:
    """Conservative *estimate* only; does NOT impose an OS-level WSL memory limit."""
    if type(memory_limit_gb) not in (int, float) or not math.isfinite(memory_limit_gb) or not 4 <= memory_limit_gb <= 128:
        raise ValueError('Third-mesh memory budget must be 4-128 GB')
    if type(time_limit_seconds) is not int or not 300 <= time_limit_seconds <= 840:
        raise ValueError('Native Palace hard timeout bounds third-mesh budget to 300-840 seconds')
    n1, n2 = coarse.get('mesh_elements_3d'), fine.get('mesh_elements_3d')
    mem2, elapsed2 = fine.get('peak_memory_GB'), fine.get('solver_elapsed_seconds')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (n1,n2,mem2,elapsed2)) or n2 <= n1:
        return {'allow':False,'reason':'Verified mesh elements, solver memory and elapsed time missing; no third solve',
                'type':'insufficient_native_resource_evidence'}
    # Third mesh 7.5/75 um after the 8/80 um level. Use conservative 1.3x
    # slack on volume scaling (8/7.5)^3; this is not a memory predictor.
    factor=(8.0/7.5)**3 * 1.30
    projected_mem=round(mem2*factor,2)
    projected_time=round(elapsed2*factor,1)
    allowed=projected_mem <= float(memory_limit_gb) and projected_time <= time_limit_seconds
    return {'allow':allowed,'reason':('Estimated resource budget admits an OPT-IN third solve' if allowed else
             'Conservative estimate exceeds selected budget; third solve skipped'),
            'type':'heuristic_preflight_not_hard_limit',
            'estimated_peak_memory_GB':projected_mem,'estimated_solver_seconds':projected_time,
            'memory_budget_GB':float(memory_limit_gb),'time_budget_seconds':time_limit_seconds,
            'estimate_not_os_enforced':True,'native_solver_hard_timeout_seconds':840}


def analyze_report_zip(path: Path, *, frequency_tolerance=None) -> dict:
    """Offline analysis of a prior SQE native EM report. Never runs a solver.

    Fail closed on any modified evidence and do not trust unvalidated JSON as a
    successful native solve; source semantics are limited to recorded evidence.
    """
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12_000_000:
        raise ConvergenceEvidenceError('Expected a bounded regular SQE evidence ZIP')
    try:
        with path.open('rb') as source:
            archive_bytes=source.read(12_000_001)
        if len(archive_bytes)>12_000_000:
            raise ConvergenceEvidenceError('Evidence archive exceeds byte budget')
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
            entries=bundle.infolist()
            names=[x.filename for x in entries]
            if len(names)>90 or len(names)!=len(set(names)) or any(
                x.file_size > MAX_ZIP_MEMBER or x.flag_bits & 0x1 or
                ((x.external_attr >> 16) & 0o170000) == 0o120000 or
                x.filename.startswith('/') or '\\' in x.filename or '..' in x.filename.split('/')
                for x in entries):
                raise ConvergenceEvidenceError('Unsafe or oversized evidence members')
            if sum(x.file_size for x in entries)>MAX_ZIP_BYTES:
                raise ConvergenceEvidenceError('Evidence ZIP exceeds decompressed budget')
            integrity=json.loads(bundle.read('INTEGRITY.json'))
            declared=integrity.get('files')
            if not isinstance(declared,dict) or set(declared)!=(set(names)-{'INTEGRITY.json'}):
                raise ConvergenceEvidenceError('Evidence manifest does not bind every file')
            for name, expected in declared.items():
                if not isinstance(expected,str) or len(expected)!=64 or hashlib.sha256(bundle.read(name)).hexdigest()!=expected:
                    raise ConvergenceEvidenceError('Modified evidence: '+name[:60])
            # Also reuse the ordinary feedback reader's stricter path/hash guards.
            from ..feedback_qualification import _checked_members
            payload = _checked_members(path)
            if payload != {name: bundle.read(name) for name in names}:
                raise ConvergenceEvidenceError('Evidence changed during review')
            envelope = json.loads(payload['QUALIFICATION.json'])
            selected = envelope.get('schema') == 'sqe.selected-development-feedback.v2'
            prefix = 'em/' if selected else ''
            report = json.loads(payload[prefix+'QUALIFICATION.json'])
            if report.get('schema') not in ('sqe.native-em-qualification.v1','sqe.native-em-qualification.v2'):
                raise ConvergenceEvidenceError('Unsupported native EM report')
            cycle = None
            if selected:
                cycle = json.loads(payload['CYCLE.json'])
                if (cycle.get('runtime_version') != envelope.get('runtime_version') or
                        cycle.get('plan_sha256') != envelope.get('plan_sha256') or
                        not isinstance(cycle.get('runtime_version'), str) or
                        not re.fullmatch(r'[0-9A-Za-z_.+-]{1,48}', cycle['runtime_version']) or
                        not all(isinstance(cycle.get(k), str) and re.fullmatch(r'[a-f0-9]{64}', cycle[k])
                            for k in ('plan_sha256', 'baseline_source_sha256')) or
                        not any(t.get('id') == 'em_convergence' and t.get('native_execution') == 'PASS'
                            and t.get('status') != 'FAIL' for t in envelope.get('tasks', []))):
                    raise ConvergenceEvidenceError('Selected report lacks consistent recorded native execution')
            ids=[p for p in ('native_palace_solve','native_palace_refinement','native_palace_third')
                 if prefix+'native/'+p+'-manifest.json' in declared]
            if len(ids)<2:
                raise ConvergenceEvidenceError('At least two verified native solve summaries required')
            observations=[];metrics=[];deck_hashes=[];summaries=[]
            for name in ids:
                item=json.loads(payload[prefix+'native/'+name+'-manifest.json'])
                if item.get('artifact_type')!='palace.eigenmodes' or not isinstance(item.get('observation'),dict):
                    raise ConvergenceEvidenceError('Missing native eigenmode observation')
                if not any(s.get('id')==name and s.get('status')=='PASS' for s in report.get('stages',[])):
                    raise ConvergenceEvidenceError('Native solve was not a qualified passed worker stage')
                deck=next((a.get('sha256') for a in item.get('artifacts', [])
                           if a.get('name')=='sqe_em/sqe_em.json'),None)
                if not isinstance(deck,str) or len(deck)!=64:
                    raise ConvergenceEvidenceError('Missing native Palace deck hash')
                deck_hashes.append(deck)
                observations.append(item['observation'])
                summaries.append(item)
                log_name=prefix+'logs/'+name+'.txt'
                if log_name not in declared:
                    raise ConvergenceEvidenceError('Missing native solver log')
                metrics.append(palace_log_metrics(payload[log_name].decode('utf-8','replace')))
                if selected:
                    inventory={a['name']:a for a in item['artifacts']}
                    if (len(inventory) != len(item['artifacts']) or
                            item.get('result_manifest_sha256') != item['observation'].get('manifest_sha256')):
                        raise ConvergenceEvidenceError('Inconsistent recorded native manifest identity')
                    for suffix, relative in (('eig.csv','sqe_em/outputFiles/eig.csv'),
                                              ('palace-deck.json','sqe_em/sqe_em.json')):
                        raw=payload[prefix+'native/'+name+'-'+suffix]
                        expected=inventory[relative]
                        if hashlib.sha256(raw).hexdigest()!=expected['sha256'] or len(raw)!=expected['bytes']:
                            raise ConvergenceEvidenceError('Recorded native artifact bytes differ from inventory')
            if len(set(deck_hashes))!=1:
                raise ConvergenceEvidenceError('Solver deck changed during nominal mesh-only refinement')
            field_name=prefix+'native/upstream-field-correlation.json'
            if field_name not in payload and any(s.get('id')=='upstream_field_correlation' and
                    s.get('status')=='PASS' for s in report.get('stages',[])):
                raise ConvergenceEvidenceError('Recorded passed field stage is missing its result')
            correlation=json.loads(payload[field_name]) if field_name in payload else None
            series_name=prefix+'native/convergence-series.json'
            stored_series=json.loads(payload[series_name]) if series_name in payload else None
            recorded_tolerance=None
            if stored_series is not None:
                if (type(stored_series) is not dict or stored_series.get('schema') not in (SCHEMA,FIELD_SCHEMA) or
                        stored_series.get('fabrication_status')!='HOLD' or
                        stored_series.get('scientific_qualification')!='not_established'):
                    raise ConvergenceEvidenceError('Invalid recorded convergence declaration')
                recorded_tolerance=stored_series['relative_tolerance']
            result=convergence_series(observations,metrics,
                tolerance=recorded_tolerance if stored_series is not None else 0.02,
                field_correlation=correlation)
            if stored_series is not None and any(stored_series.get(k)!=result[k] for k in
                    ('points','adjacent_differences','last_step_numeric_threshold_met','geometry_material_digest')):
                raise ConvergenceEvidenceError('Stored scalar evidence differs from native observations')
            result['frequency_tolerance_sensitivity']=frequency_tolerance_sensitivity(observations,metrics,
                recorded_tolerance=recorded_tolerance,selected_tolerance=frequency_tolerance)
            if correlation is not None:
                from ..eda.upstream_field_compare import RECORDED
                expected='PASS' if correlation['status']==RECORDED else correlation['status']
                if not any(s.get('id')=='upstream_field_correlation' and s.get('status')==expected
                           for s in report.get('stages',[])):
                    raise ConvergenceEvidenceError('Recorded field stage and result disagree')
                if selected and correlation['status']==RECORDED:
                    for source, item, name in zip(correlation['sources'],summaries[:2],ids[:2]):
                        artifacts=item['artifacts'];inventory={a['name']:a['sha256'] for a in artifacts}
                        deck=json.loads(payload[prefix+'native/'+name+'-palace-deck.json'])
                        if (source['project_sha256']!=item['model_digest'] or
                                source['mesh_sha256']!=inventory['sqe_em/sqe_em.msh'] or
                                source['eig_sha256']!=inventory['sqe_em/outputFiles/eig.csv'] or
                                source['declared_length_unit_m']!=deck['Model']['L0'] or
                                source['pvd_sha256'] not in {v for k,v in inventory.items() if k.endswith('.pvd')} or
                                not set(source['piece_sha256']) <= {v for k,v in inventory.items() if k.endswith('.vtu')}):
                            raise ConvergenceEvidenceError('Recorded field sources differ from native inventory')
            result['source_report_sha256']=hashlib.sha256(archive_bytes).hexdigest()
            result['source_report_schema']=report['schema']
            result['source_envelope_schema']=envelope['schema']
            result['source_runtime']=cycle['runtime_version'] if cycle else None
            result['source_code_manifest_sha256']=cycle['baseline_source_sha256'] if cycle else None
            result['analysis_kind']='RECORDED_REPORT_REPLAY_NO_NATIVE_EXECUTION'
            result['native_execution']='NOT_RUN'
            result['source_native_execution']='RECORDED_PASS'
            result['verification']='Archive hashes and recorded evidence links verified; source PASS is recorded, not re-executed or author-authenticated'
            return result
    except (KeyError,ValueError,zipfile.BadZipFile,UnicodeDecodeError,TypeError,AttributeError,IndexError) as exc:
        if isinstance(exc,ConvergenceEvidenceError):
            raise
        raise ConvergenceEvidenceError('Unusable/unsafe native EM evidence report') from exc
