"""Per-release, single-button evidence workflow. Administrative Tk caller only.

Never call this from untrusted web endpoints. Full run always executes current
production tests and native solvers; prior ZIPs inform prioritization only.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
import importlib.util
import sys
from pathlib import Path, PurePosixPath
import re
import threading
import time
import tempfile
import zipfile

NAME_PATTERN = re.compile(r'^SQE-RC14_12-report-(\d{4})\.zip$')
REPORT_FOLDER = 'qualification-reports'



class _ProgressEvidence:
    """Bounded stage/heartbeat evidence; never persists arbitrary logs or local paths.

    A heartbeat indicates that the qualification controller is responsive, NOT
    solver convergence or proof that a native subprocess is still making progress.
    """
    _EVENT = re.compile(r'^(PHASE_START|PHASE_END|STAGE_START|STAGE_END) '
                        r'(software|native_em|science)(?: ([a-zA-Z0-9_]{1,80}))?'
                        r'(?: (PASS|FAIL|BLOCKED))?$')

    def __init__(self, notify=None, interval=15.0):
        self.notify_callback = notify or (lambda message: None)
        self.interval = interval
        self.begin = time.monotonic()
        self.started_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.lock = threading.Lock()
        self.stop_signal = threading.Event()
        self.phase = 'preparation'
        self.stage = None
        self.last_activity = self.begin
        self.phases_done = 0
        self.stages_done = {'software': 0, 'native_em': 0, 'science': 0}
        self.status_counts = {'PASS': 0, 'FAIL': 0, 'BLOCKED': 0}
        self.heartbeats = 0
        self.events = []
        self.thread = None

    def _forward(self, line):
        try:
            self.notify_callback(line)
        except Exception:
            # GUI event handlers must not break the scientific workflow.
            pass

    def notify(self, message):
        line = str(message)
        match = self._EVENT.fullmatch(line)
        if match:
            action, phase, token, status = match.groups()
            with self.lock:
                now = time.monotonic()
                self.last_activity = now
                if action == 'PHASE_START':
                    self.phase, self.stage = phase, None
                elif action == 'PHASE_END':
                    self.phases_done += 1
                    self.stage = None
                elif action == 'STAGE_START':
                    self.phase, self.stage = phase, token
                elif action == 'STAGE_END':
                    self.stages_done[phase] += 1
                    self.status_counts[status] += 1
                    if self.phase == phase and self.stage == token:
                        self.stage = None
                # Structured identifiers and statuses only; no raw stdout.
                if len(self.events) < 900:
                    self.events.append({'elapsed_seconds': round(now-self.begin, 1),
                                    'event': action, 'phase': phase,
                                    **({'stage': token} if token else {}),
                                    **({'status': status} if status else {})})
        self._forward(line)

    def start(self):
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True,
                                       name='sqe-qualification-heartbeat')
        self.thread.start()

    def _heartbeat_loop(self):
        while not self.stop_signal.wait(self.interval):
            with self.lock:
                now = time.monotonic()
                self.heartbeats += 1
                elapsed = int(now-self.begin)
                since_activity = int(now-self.last_activity)
                phase, stage = self.phase, self.stage or 'phase_checks'
                # Max 240 ticks at 15s for a 60m goal; bounded storage on overruns.
                if len(self.events) < 900:
                    self.events.append({'event': 'HEARTBEAT',
                                        'elapsed_seconds': elapsed,
                                        'seconds_since_stage_event': since_activity,
                                        'phase': phase, 'stage': stage})
            self._forward(f'HEARTBEAT: phase={phase} stage={stage} '
                          f'elapsed={elapsed}s last_stage_event={since_activity}s')

    def finish(self, outcome):
        self.stop_signal.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        with self.lock:
            return {'schema': 'sqe.qualification-progress.v1',
                    'started_utc': self.started_utc,
                    'finished_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'duration_seconds': round(time.monotonic()-self.begin, 2),
                    'outcome': outcome, 'phases_completed': self.phases_done,
                    'phase_count': 3, 'stages_completed_by_phase': dict(self.stages_done),
                    'gate_event_counts': dict(self.status_counts),
                    'heartbeat_count': self.heartbeats,
                    'heartbeat_is_not_solver_convergence': True,
                    'events': list(self.events)}


# The authoritative case matrix is a dispatch SPEC, never evidence of execution.
_CASE_IDS = tuple(f'B{i:02d}' for i in range(12))
_CASE_FIELDS = ('case_id', 'stage_status', 'execution_kind', 'provenance',
                'solver_version', 'input_sha256', 'geometry_revision_sha256',
                'material_bc_mesh_hashes', 'units', 'measurements',
                'numerical_tolerances', 'solver_exit_code', 'duration_s',
                'scientific_limitations', 'failure_reason', 'log_sha256')
_SHA256 = re.compile(r'[a-f0-9]{64}\Z')


def _read_science_matrix(root: Path) -> tuple[dict, str]:
    """Read the dispatch's exact, bounded B00-B11 plan, without changing it."""
    file = root / 'config/scientific_benchmarks.json'
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 100_000:
        raise ValueError('Scientific benchmark matrix missing or unsafe')
    body = file.read_bytes()
    doc = json.loads(body)
    cases = doc.get('benchmark_cases')
    policy = doc.get('execution_policy')
    if (doc.get('schema') != 'sqe.scientific-benchmark-dispatch.v1' or
        doc.get('target_release') != 'RC14.12' or
        not isinstance(cases, list) or len(cases) != 12 or
        {case.get('id') for case in cases if isinstance(case, dict)} != set(_CASE_IDS) or
        not isinstance(policy, dict) or
        policy.get('target_wall_seconds') != 3600 or
        policy.get('priority_order') != [_CASE_IDS[i] for i in (0,1,2,3,4,6,8,9,10,5,7,11)] or
        policy.get('user_selectable_parameters') is not False or
        doc.get('per_case_report_fields') != list(_CASE_FIELDS) or
        any(type(case.get('budget_s')) is not int or
            not 0 < case['budget_s'] <= 900 for case in cases)):
        raise ValueError('Scientific case matrix violates fixed dispatch contract')
    return doc, sha256(body).hexdigest()


def _case_record(case_id: str, *, status='BLOCKED', reason='BLOCKED_NOT_IMPLEMENTED',
                 execution='NOT_RUN', **extra) -> dict:
    """Unknown/unverified material is NULL, never an apparent native result."""
    record = {'case_id':case_id, 'stage_status':status,
              'execution_kind':execution, 'provenance':None,
              'solver_version':None, 'input_sha256':None,
              'geometry_revision_sha256':None,
              'material_bc_mesh_hashes':None, 'units':None,
              'measurements':None, 'numerical_tolerances':None,
              'solver_exit_code':None, 'duration_s':0,
              'scientific_limitations':'Not a physical, mode identity, EPR or foundry approval',
              'failure_reason':reason, 'log_sha256':None}
    record.update(extra)
    return record


def _case_from_software(members: dict[str, bytes], case_id: str) -> dict:
    """B00 uses only current-run, integrity-checked software subreport evidence."""
    body = members.get('software/QUALIFICATION.json')
    if not body:
        return _case_record(case_id, reason='BLOCKED_NO_CURRENT_SOFTWARE_SUBREPORT')
    try:
        doc = json.loads(body)
        gates = doc['gates']
        if not isinstance(gates, list) or len(gates) > 150:
            raise ValueError('Invalid software gate collection')
        observed = {}
        for gate in gates:
            if (not isinstance(gate, dict) or
                not isinstance(gate.get('id'), str) or
                gate.get('id') in observed or
                gate.get('status') not in ('PASS', 'FAIL', 'BLOCKED')):
                raise ValueError('Duplicated or malformed software gate')
            observed[gate['id']] = gate
    except (ValueError, TypeError, KeyError):
        return _case_record(case_id, status='FAIL', reason='MALFORMED_SOFTWARE_EVIDENCE')
    required = ('source_integrity', 'python_compile', 'javascript_syntax',
                'integrated_regression', 'browser_real_http', 'browser_deep_acceptance',
                'source_wheel_build', 'installed_wheel', 'installed_assets')
    statuses = {name:observed[name]['status'] if name in observed else 'BLOCKED'
                for name in required}
    if any(item['status'] == 'FAIL' for item in observed.values()):
        status, reason = 'FAIL', 'REAL_SOFTWARE_GATE_FAILED'
    elif all(value == 'PASS' for value in statuses.values()):
        status, reason = 'PASS', None
    else:
        status, reason = 'BLOCKED', 'REQUIRED_SOFTWARE_GATE_NOT_PASSED'
    return _case_record(case_id, status=status, reason=reason,
        execution='NATIVE', provenance='CURRENT_RUN_SOFTWARE_SUBREPORT_SHA256_VERIFIED',
        solver_version={'python':sys.version.split()[0]},
        measurements={'actual_software_gate_status':statuses},
        duration_s=round(sum(float(observed[n].get('duration_seconds',0) or 0)
                             for n in required if n in observed),2),
        log_sha256=sha256(body).hexdigest())


def _case_from_native_cad_gate(members: dict[str, bytes], case_id: str, root: Path | None = None) -> dict:
    """Report a real QDesign subtest without inventing a GDS-to-Gmsh bridge.

    This is explicitly a partial B01 observation. The complete benchmark must
    stay BLOCKED until a revision/units/physical-group verified native GDS and
    mesh is produced within the same run. A fixture PASS is never promoted.
    """
    body = members.get('software/QUALIFICATION.json')
    if not body:
        return _case_record(case_id, reason='BLOCKED_NO_SOFTWARE_EVIDENCE')
    try:
        gates = json.loads(body)['gates']
        if not isinstance(gates,list) or len(gates)>150:
            raise ValueError('Malformed software gates')
        indexed = {g['id']:g for g in gates if isinstance(g,dict) and isinstance(g.get('id'),str)}
        if len(indexed)!=len(gates):
            raise ValueError('Duplicate software gates')
        source = indexed.get('source_integrity',{}).get('status')
        cad = indexed.get('native_quantum_metal',{})
        safe_legacy_only = (source == 'FAIL' and root is not None and
                            _trusted_release_with_legacy_tests(root))
        if (source != 'PASS' and not safe_legacy_only) or cad.get('status') != 'PASS':
            return _case_record(case_id, reason='BLOCKED_NATIVE_CAD_OR_SOURCE_NOT_VERIFIED')
        count = cad.get('counts',{}).get('passed')
        if type(count) is not int or count<1 or count>100:
            raise ValueError('Missing real native CAD count')
    except (ValueError,TypeError,KeyError):
        return _case_record(case_id,status='FAIL',reason='INVALID_NATIVE_CAD_GATE_EVIDENCE')
    return _case_record(case_id,execution='NATIVE',
                        reason='NATIVE_QDESIGN_TESTED_GDS_GMSH_LINEAGE_NOT_QUALIFIED',
                        provenance='CURRENT_RUN_SHA_VERIFIED_SOFTWARE_SUBREPORT',
                        solver_version='Quantum Metal; see version in software subreport',
                        measurements={'native_qdesign_tests_passed':count,
                                      'host_source_integrity':source,
                                      'gds_mesh_physical_mapping':'BLOCKED_NOT_ESTABLISHED'},
                        log_sha256=sha256(body).hexdigest())


def _screened_native_em_observables(members: dict[str, bytes]) -> dict:
    """Attach only bounded, *current-run* Palace scalar evidence to B02.

    The current report's Results screen must be verified against the native
    manifest and included Palace scalar CSV bytes. This is not an eigenmode
    matching, convergence, H(curl) overlap, or experimental-physics validator.
    """
    base = 'em/native/native_palace_solve-'
    screen_bytes = members.get(base + 'results-screen.json')
    manifest_bytes = members.get(base + 'manifest.json')
    if not screen_bytes or not manifest_bytes or max(len(screen_bytes),len(manifest_bytes)) > 100_000:
        raise ValueError('Missing or oversized current-run native screen/manifest')
    screen = json.loads(screen_bytes)
    manifest = json.loads(manifest_bytes)
    if (screen.get('schema') != 'sqe.em-native-results-screen.v1' or
        screen.get('source') != 'revision_and_sha256_verified_native_run' or
        screen.get('mode_identity') != 'UNRESOLVED' or
        screen.get('mesh_convergence') != 'NOT_ESTABLISHED' or
        manifest.get('artifact_type') != 'palace.eigenmodes' or
        not isinstance(manifest.get('artifacts'),list) or
        not 1 <= len(manifest['artifacts']) <= 200):
        raise ValueError('Native Results screen does not meet physical gate')
    artifacts = {}
    for a in manifest['artifacts']:
        if (not isinstance(a,dict) or not isinstance(a.get('name'),str) or
            a['name'] in artifacts or not isinstance(a.get('sha256'),str) or
            not _SHA256.fullmatch(a['sha256'])):
            raise ValueError('Invalid native manifest artifact')
        artifacts[a['name']] = a['sha256']
    for filename, exported in (
        ('eig.csv','eig.csv'), ('port-Q.csv','port-Q.csv'),
        ('domain-E.csv','domain-E.csv')):
        expected = artifacts.get('sqe_em/outputFiles/' + filename)
        actual = members.get(base + exported)
        if expected is None or actual is None or sha256(actual).hexdigest() != expected:
            raise ValueError('Native Palace scalar table lineage mismatch')
    # Recompute the numerical observables from the actual native CSV. Checking
    # file hashes alone is insufficient if a JSON screen was mis-associated
    # with the right table or a stale cached screen was submitted.
    from .interop.em_observables import _table
    from .interop.em_convergence import ConvergenceEvidenceError
    try:
        eig_header, eig_rows = _table(members[base+'eig.csv'], 'Re{f}')
        port_header, port_rows = _table(members[base+'port-Q.csv'], 'Q_ext')
        energy_header, energy_rows = _table(members[base+'domain-E.csv'], 'E_elec')
    except (ConvergenceEvidenceError,KeyError) as exc:
        raise ValueError('Invalid native numerical CSV content') from exc
    if len(eig_rows) != len(port_rows) or len(eig_rows) != len(energy_rows):
        raise ValueError('Native numerical table mode counts differ')
    def col(h, name):
        if name not in h: raise ValueError('Native scalar column missing')
        return h.index(name)
    f_idx, q_idx = col(eig_header,'Re{f} (GHz)'), col(eig_header,'Q')
    elec_idx, mag_idx = col(energy_header,'E_elec (J)'), col(energy_header,'E_mag (J)')
    def equal(a,b):
        if not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-16):
            raise ValueError('Native Results screen does not match CSV observation')
    def finite(value, *, positive=False):
        if (type(value) not in (int,float) or not math.isfinite(value) or
            (positive and value <= 0)):
            raise ValueError('Invalid native scalar')
        return value
    modes = screen.get('modes')
    if not isinstance(modes,list) or not 1 <= len(modes) <= 16:
        raise ValueError('Invalid native mode list')
    observations = []
    unique_modes = set()
    for m in modes:
        index=m.get('native_mode_index')
        if type(index) is not int or index < 1 or index in unique_modes:
            raise ValueError('Ambiguous native mode index')
        unique_modes.add(index)
        ports=m.get('ports')
        if not isinstance(ports,list) or len(ports)>16:
            raise ValueError('Invalid native port table')
        port_indices=set()
        screened_ports=[]
        for port in ports:
            number=port.get('port_index')
            if type(number) is not int or number<1 or number in port_indices:
                raise ValueError('Invalid native port identity')
            port_indices.add(number)
            screened_ports.append({'port_index':number,
                'q_ext':finite(port.get('q_ext'),positive=True),
                # A negative native coupling is preserved, never rectified.
                'native_kappa_ext_GHz':finite(port.get('native_kappa_ext_GHz'))})
        row_ix=index-1
        if row_ix>=len(eig_rows) or eig_rows[row_ix][0]!=index or port_rows[row_ix][0]!=index or energy_rows[row_ix][0]!=index:
            raise ValueError('Native Results mode order cannot be matched to CSV')
        observed_f=finite(m.get('frequency_GHz'),positive=True)
        observed_q=finite(m.get('q_total'),positive=True)
        observed_energy=finite(m.get('electric_to_magnetic_energy_ratio'),positive=True)
        equal(observed_f,eig_rows[row_ix][f_idx])
        equal(observed_q,eig_rows[row_ix][q_idx])
        elec,mag=energy_rows[row_ix][elec_idx],energy_rows[row_ix][mag_idx]
        if elec<=0 or mag<=0: raise ValueError('Unphysical scalar energy ratio')
        equal(observed_energy,elec/mag)
        native_port_indices={int(x) for x in
            (re.fullmatch(r'Q_ext\[(\d+)\]',header).group(1)
             for header in port_header if re.fullmatch(r'Q_ext\[(\d+)\]',header))}
        if native_port_indices!=port_indices:
            raise ValueError('Native port set differs from CSV')
        for port in screened_ports:
            num=port['port_index']
            equal(port['q_ext'],port_rows[row_ix][col(port_header,f'Q_ext[{num}]')])
            kheader=next((h for h in port_header if
                h in (f'κ_ext[{num}] (GHz)',f'kappa_ext[{num}] (GHz)')),None)
            if kheader is None: raise ValueError('Native coupling column missing')
            equal(port['native_kappa_ext_GHz'],port_rows[row_ix][col(port_header,kheader)])
        observations.append({'native_mode_index':index,
            'frequency_GHz':observed_f,'q_total':observed_q,
            'electric_to_magnetic_energy_ratio':observed_energy,
            'ports':screened_ports})
    fields=screen.get('field_acquisition')
    if not isinstance(fields,dict) or type(fields.get('artifact_count')) is not int or fields['artifact_count']<0:
        raise ValueError('Invalid native field inventory')
    # M11 native-field evidence is a checked diagnostic, NEVER scientific
    # mode identity. Historical reports can lack it; do not claim a PASS.
    field_lineage = screen.get('field_lineage')
    field_status = 'NOT_REPORTED'
    saved_samples = 0
    if field_lineage is not None:
        if (not isinstance(field_lineage, dict) or
                field_lineage.get('schema') != 'sqe.palace-verified-field-lineage.m11.v1' or
                field_lineage.get('physical_mode_identity') != 'UNRESOLVED' or
                field_lineage.get('mesh_convergence') != 'NOT_ESTABLISHED' or
                field_lineage.get('fabrication') != 'HOLD'):
            raise ValueError('Invalid source field-lineage scientific gate')
        field_status = field_lineage.get('status')
        field_diagnostic = field_lineage.get('diagnostic_code')
        if field_diagnostic is not None and (type(field_diagnostic) is not str or
                re.fullmatch(r'[A-Z][A-Z0-9_]{3,63}', field_diagnostic) is None or
                field_status == 'VERIFIED_FORMAT_LINEAGE_ONLY'):
            raise ValueError('Invalid source native field diagnostic code')
        if (not isinstance(field_status, str) or not
                (field_status == 'VERIFIED_FORMAT_LINEAGE_ONLY' or
                 field_status.startswith('BLOCKED_'))):
            raise ValueError('Unexpected native field-lineage readiness')
        # M15: a portable field-declaration diagnostic can be included only
        # for a blocked vector contract, with strictly whitelisted names and
        # categorical states. No arbitrary VTK arrays or raw data are exported.
        declaration = field_lineage.get('field_declaration_diagnostic')
        if declaration is not None:
            expected_field_names = {'E_real', 'E_imag', 'E'}
            states = {'NO_ASSOCIATION', 'ABSENT', 'DUPLICATE', 'NON_FLOAT',
                      'WRONG_COMPONENT_COUNT', 'FLOAT_VECTOR_3'}
            if (field_status != 'BLOCKED_INVALID_NATIVE_FIELD_LINEAGE' or
                field_diagnostic not in {'VTU_POINT_DATA_MISSING', 'VTU_COMPLEX_E_MISSING'} or
                type(declaration) is not dict or
                set(declaration) != {'schema', 'point', 'cell', 'parallel_point',
                                     'field_values_exported', 'physical_mode_identity'} or
                declaration['schema'] != 'sqe.vtu-e-field-declaration.m15.v1' or
                declaration['field_values_exported'] is not False or
                declaration['physical_mode_identity'] != 'UNRESOLVED' or
                any(type(declaration[k]) is not dict or
                    set(declaration[k]) != expected_field_names or
                    any(type(v) is not str or v not in states
                        for v in declaration[k].values())
                    for k in ('point', 'cell', 'parallel_point'))):
                raise ValueError('Invalid private or untrusted VTU declaration diagnostic')
        if field_status == 'VERIFIED_FORMAT_LINEAGE_ONLY':
            if (any(field_lineage.get(key) != artifacts.get(path) for key,path in (
                    ('mesh_sha256','sqe_em/sqe_em.msh'),
                    ('deck_sha256','sqe_em/sqe_em.json'),
                    ('native_eig_sha256','sqe_em/outputFiles/eig.csv'))) or
                    type(field_lineage.get('field_sample_count')) is not int or
                    not 1 <= field_lineage['field_sample_count'] <= 12 or
                    field_lineage.get('saved_mode_ordinals_unverified') !=
                    list(range(1,field_lineage['field_sample_count']+1))):
                raise ValueError('Field-readiness claimed incompatible native artifacts')
            saved_samples = field_lineage['field_sample_count']
    # M16 opt-in upstream-reader diagnostic: separate from scientific B02
    # status and checked against the original per-run signed screen and its
    # independently zipped JSON. No raw field values or foreign metadata.
    upstream = screen.get('upstream_field_probe')
    safe_upstream = None
    if upstream is not None:
        packaged = members.get(base+'upstream-field-probe.json')
        if not packaged or len(packaged) > 120_000:
            raise ValueError('Missing bounded upstream native diagnostic')
        if json.loads(packaged) != upstream:
            raise ValueError('Upstream diagnostic does not match saved native screen')
        from .eda.upstream_vtk_probe import SCHEMA as CYCLE_SCHEMA, diagnostic_summary
        if type(upstream) is dict and upstream.get('schema') == CYCLE_SCHEMA:
            safe_upstream = diagnostic_summary(upstream)
        elif (type(upstream) is not dict or
                upstream.get('schema') != 'sqe.m16.upstream-vtk-declarations.experimental.v1' or
                upstream.get('status') not in ('BLOCKED',
                    'UPSTREAM_COMPLEX_E_DECLARATIONS_OBSERVED',
                    'UPSTREAM_COMPLEX_E_NOT_ESTABLISHED') or
                upstream.get('physical_mode_identity') != 'NOT_ESTABLISHED' or
                upstream.get('mesh_convergence') != 'NOT_ESTABLISHED' or
                upstream.get('field_values_in_report') is not False):
            raise ValueError('Invalid upstream diagnostic science gate')
        elif upstream['status'] == 'BLOCKED':
            code = upstream.get('reason_code')
            if (type(code) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{2,63}',code)
                or 'cycles' in upstream):
                raise ValueError('Unsafe upstream diagnostic blocked state')
            safe_upstream = {'status': 'BLOCKED','reason_code':code}
        else:
            allowed_states = {'ABSENT','FLOAT_VECTOR_3','WRONG_TYPE_OR_COMPONENTS'}
            cycles=upstream.get('cycles')
            backend=upstream.get('backend')
            ver=upstream.get('backend_version')
            if (backend not in ('VTK','PyVista') or type(ver) is not str or len(ver)>32
                or not isinstance(cycles,list) or not 1<=len(cycles)<=12 or
                upstream.get('pvd_cycle_count') != len(cycles)):
                raise ValueError('Invalid upstream diagnostic dimensions')
            flags=[]
            for idx,cycle in enumerate(cycles):
                if (type(cycle) is not dict or
                        cycle.get('cycle_index_not_mode_identity') != idx or
                        type(cycle.get('mpi_piece_count')) is not int or
                        not 1<=cycle['mpi_piece_count']<=16 or
                        type(cycle.get('complex_e_declared')) is not bool or
                        not isinstance(cycle.get('blocks'),list) or
                        not 1<=len(cycle['blocks'])<=64):
                    raise ValueError('Invalid upstream field cycle declaration')
                for block in cycle['blocks']:
                    if (type(block) is not dict or set(block) != {'point','cell'} or
                        any(type(block[k]) is not dict or
                            set(block[k]) != {'E_real','E_imag','E','B_real','B_imag'} or
                            any(v not in allowed_states for v in block[k].values())
                            for k in ('point','cell'))):
                        raise ValueError('Unsafe upstream field arrays')
                flags.append(cycle['complex_e_declared'])
            safe_upstream = {'status':upstream['status'],
                            'backend':backend,'backend_version':ver,
                            'pvd_cycle_count':len(cycles),
                            'complex_E_declared_by_cycle':flags}
    # Absence is permitted in historical reports; it is never a scientific PASS.
    return {
        'native_mode_observations':observations,
        'complex_field_artifact_count':min(fields['artifact_count'],10000),
        'complex_field_export_lineage_status': field_status,
        'complex_field_export_diagnostic_code': (
            field_lineage.get('diagnostic_code') if isinstance(field_lineage, dict) else None),
        'complex_field_export_diagnostic_phase': (
            field_lineage.get('diagnostic_phase') if isinstance(field_lineage, dict) else None),
        'complex_field_declaration_diagnostic': (
            field_lineage.get('field_declaration_diagnostic')
            if isinstance(field_lineage, dict) else None),
        'complex_field_saved_collection_samples': saved_samples,
        'upstream_vtk_diagnostic':safe_upstream,
        'complex_field_common_domain_verified':fields.get('common_coordinate_domain_verified') is True,
        'complex_field_normalization_verified':fields.get('complex_vector_normalization_verified') is True,
        'mode_identity':'UNRESOLVED','mesh_convergence':'NOT_ESTABLISHED',
        'source_model_digest':manifest.get('model_digest'),
        'solver_reported_version':manifest.get('native_solver_version'),
        'source_screen_sha256':sha256(screen_bytes).hexdigest(),
        'source_native_manifest_sha256':sha256(manifest_bytes).hexdigest(),
        'source_scalar_csv_sha256':{
            filename:artifacts['sqe_em/outputFiles/'+filename]
            for filename in ('eig.csv','port-Q.csv','domain-E.csv')},
    }


def _case_from_em(members: dict[str, bytes], case_id: str) -> dict:
    """B02 records real Palace numbers without granting physics approval."""
    body = members.get('em/QUALIFICATION.json')
    if not body:
        return _case_record(case_id, reason='BLOCKED_NO_CURRENT_NATIVE_SUBREPORT')
    try:
        doc = json.loads(body)
        stages = doc['stages']
        if not isinstance(stages,list) or len(stages)>50:
            raise ValueError('Invalid native stage list')
        statuses = {s['id']:s['status'] for s in stages if isinstance(s,dict)
                    and s.get('status') in ('PASS','BLOCKED','FAIL')}
        if len(statuses)!=len(stages):
            raise ValueError('Duplicate or malformed native stage')
    except (ValueError, KeyError, TypeError):
        return _case_record(case_id, status='FAIL', reason='MALFORMED_NATIVE_EVIDENCE')
    solver = statuses.get('native_palace_solve')
    status = 'FAIL' if solver == 'FAIL' else 'BLOCKED'
    measurements = {'existing_gate_status':statuses}
    version = None
    provenance='CURRENT_RUN_NATIVE_SUBREPORT_SHA256_VERIFIED'
    if solver == 'PASS' and statuses.get('results_screen_native_palace_solve') == 'PASS':
        try:
            observations = _screened_native_em_observables(members)
        except (ValueError,TypeError,KeyError,AttributeError):
            return _case_record(case_id,status='FAIL',reason='INVALID_NATIVE_SCALAR_EVIDENCE',
                execution='NATIVE',log_sha256=sha256(body).hexdigest())
        measurements.update(observations)
        version = observations['solver_reported_version']
        provenance='CURRENT_RUN_RESULTS_AND_MANIFEST_AND_SCALAR_CSV_SHA256_VERIFIED'
    return _case_record(case_id, status=status,
        reason='NATIVE_SOLVE_FAILED' if status == 'FAIL' else 'BLOCKED_EXPANDED_PHYSICS_CHECKS',
        execution='NATIVE' if solver in ('PASS','FAIL') else 'NOT_RUN',
        provenance=provenance,solver_version=version,
        units={'frequency':'GHz','native_kappa_ext':'GHz','quality_factors':'dimensionless'}
            if version is not None else None,
        measurements=measurements,log_sha256=sha256(body).hexdigest())


def _case_command(root: Path, case_id: str, command: list[str], budget_s: int,
                  notify) -> dict:
    """Bounded, supervised A99-provided native command interface.

    Trusted integration may supply a fixed argv list; last arg is a temporary
    result JSON path. No command shell, stdout import or fixture PASS is allowed.
    Native adapters own physical validation, artifact generation and versioning.
    """
    from .qualification import _run, _safe_log
    if (not isinstance(command,list) or not command or len(command)>25 or
        any(not isinstance(arg,str) or not arg or len(arg)>1024 for arg in command)):
        return _case_record(case_id,status='FAIL',reason='INVALID_NATIVE_ADAPTER_COMMAND')
    with tempfile.TemporaryDirectory(prefix='sqe-case-') as temp:
        file = Path(temp)/'case-result.json'
        environment = os.environ.copy()
        for key in ('PYTHONPATH','PYTHONHOME','PIP_CONFIG_FILE','PIP_TARGET'):
            environment.pop(key,None)
        notify('Running bounded native adapter '+case_id)
        code, log, elapsed = _run([*command,str(file)],root,environment,budget_s)
        # Only the temporary trusted adapter process is inspected. Record a
        # bounded redacted tail if it fails, plus a hash of complete output.
        # No shell commands, user environment values or solver private trees.
        failure_detail = {'diagnostic_output_sha256':sha256(log.encode('utf-8','replace')).hexdigest(),
                          'diagnostic_excerpt':_safe_log(log[-7000:],
                              (str(root),str(Path.home()),str(temp),
                               os.environ.get('USERPROFILE','')))[-5000:]}
        if code != 0:
            return _case_record(case_id,status='FAIL' if code is not None else 'BLOCKED',
                                reason='ADAPTER_FAILED' if code is not None else 'BLOCKED_ADAPTER_TIMEOUT_OR_SPAWN',
                                execution='NATIVE',solver_exit_code=code,duration_s=elapsed,
                                **failure_detail)
        if file.is_symlink() or not file.is_file() or file.stat().st_size>32_000:
            return _case_record(case_id,status='FAIL',reason='INVALID_NATIVE_ADAPTER_REPORT',
                                execution='NATIVE',solver_exit_code=code,duration_s=elapsed,
                                **failure_detail)
        try:
            record=json.loads(file.read_bytes())
            # Domain adapters are trusted for running, not for disclosing
            # arbitrary user paths, credentials or unverified native outputs.
            serialized=json.dumps(record,allow_nan=False,sort_keys=True)
            plain=serialized.replace('\\\\', '\\')
            if (len(serialized)>30000 or
                any(private and private in plain for private in
                    (str(root),str(Path.home()),os.environ.get('USERPROFILE',''))) or
                re.search(r'(?i)([a-z]:[/\\]users[/\\]|/(?:home|users)/[^/\\ ]+[/\\]|(?:password|token|secret)\s*[:=])',plain)):
                raise ValueError('Unsafe private path or token in native case evidence')
            if (not isinstance(record,dict) or set(record)!=set(_CASE_FIELDS) or
                record['case_id'] != case_id or
                record['stage_status'] not in ('PASS','FAIL','BLOCKED') or
                record['execution_kind'] not in ('NATIVE','NOT_RUN') or
                (record['execution_kind']=='NOT_RUN' and record['stage_status']!='BLOCKED') or
                (record['stage_status']=='PASS' and record['execution_kind']!='NATIVE') or
                (record['execution_kind']=='NATIVE' and record['solver_exit_code'] not in (0,1)) or
                (record['execution_kind']=='NOT_RUN' and record['solver_exit_code'] is not None) or
                not isinstance(record['duration_s'],(int,float)) or record['duration_s']<0 or
                record['duration_s'] > budget_s or
                record['stage_status']=='PASS' and not (
                    isinstance(record['solver_version'],str) and record['solver_version'] and
                    all(isinstance(record[h],str) and _SHA256.fullmatch(record[h])
                        for h in ('input_sha256','geometry_revision_sha256','log_sha256')) and
                    isinstance(record['material_bc_mesh_hashes'],dict) and record['material_bc_mesh_hashes'] and
                    all(isinstance(v,str) and _SHA256.fullmatch(v)
                        for v in record['material_bc_mesh_hashes'].values()) and
                    isinstance(record['units'],dict) and record['units'] and
                    isinstance(record['measurements'],dict) and record['measurements'] and
                    isinstance(record['numerical_tolerances'],dict) and record['numerical_tolerances'] and
                    isinstance(record['provenance'],dict) and record['provenance'].get('native_run') is True and
                    isinstance(record['provenance'].get('native_artifacts'),list) and
                    0 < len(record['provenance']['native_artifacts']) <= 8 and
                    isinstance(record['scientific_limitations'],str) and record['scientific_limitations']
                )):
                raise ValueError('Incomplete native report or fixture-based PASS')
            # Even when physical qualification stays BLOCKED, a claimed real
            # native run must be anchored to an actual current-run artifact.
            # The controller validates these inside the bounded private worker
            # directory; missing or forged hashes are FAIL, not numerical evidence.
            if record['execution_kind']=='NATIVE' and record['solver_exit_code']==0:
                if (not isinstance(record['provenance'], dict) or
                    record['provenance'].get('native_run') is not True or
                    not isinstance(record['provenance'].get('native_artifacts'), list) or
                    not record['provenance']['native_artifacts']):
                    raise ValueError('Unbacked native numerical case')
            if (record['stage_status']=='PASS' or
                record['execution_kind']=='NATIVE' and record['solver_exit_code']==0):
                for artifact in record['provenance']['native_artifacts']:
                    if (not isinstance(artifact,dict) or set(artifact) != {'path','sha256'} or
                        not isinstance(artifact['path'],str) or len(artifact['path'])>160 or
                        not isinstance(artifact['sha256'],str) or
                        not _SHA256.fullmatch(artifact['sha256'])):
                        raise ValueError('Invalid native artifact manifest')
                    rel=PurePosixPath(artifact['path'])
                    if (rel.is_absolute() or rel.as_posix()!=artifact['path'] or
                        any(x in ('','.','..') for x in artifact['path'].split('/')) or
                        ':' in artifact['path'] or '\\' in artifact['path']):
                        raise ValueError('Unsafe native artifact path')
                    actual=Path(temp)/artifact['path']
                    if (actual.is_symlink() or not actual.is_file() or
                        not actual.resolve().is_relative_to(Path(temp).resolve()) or
                        not 0 < actual.stat().st_size <= 12_000_000 or
                        sha256(actual.read_bytes()).hexdigest()!=artifact['sha256']):
                        raise ValueError('Native artifact absent or altered')
        except (ValueError, TypeError, KeyError) as exc:
            return _case_record(case_id,status='FAIL',reason='UNVERIFIED_NATIVE_ADAPTER_REPORT',
                                execution='NATIVE',solver_exit_code=code,duration_s=elapsed,
                                validation_error_type=type(exc).__name__,
                                validation_error=_safe_log(str(exc)[:350],
                                  (str(root),str(Path.home()),str(temp),
                                   os.environ.get('USERPROFILE',''))),
                                **failure_detail)
        # Never save an adapter's arbitrary stdout or local filenames.
        record['duration_s']=round(elapsed,2)
        return record


# Historical installation pollution is not a trusted source modification.
# ONLY the three known obsolete test files may be present in addition to an
# otherwise bit-identical release. Never mark the host integrity gate PASS.
_LEGACY_TESTS = frozenset({
    'tests/integration/test_rc14_8_a99_release.py',
    'tests/integration/test_rc14_9_a99_release.py',
    'tests/integration/test_rc14_10_a99_release.py',
})


def _trusted_release_with_legacy_tests(root: Path) -> bool:
    """Bounded source attestation for *numerical diagnostic* adapters only.

    The host inventory mismatch remains FAIL and is disclosed in the same
    report. Any changed/missing source, unexpected extra, linked source file,
    or altered frozen contract fails closed. Old tests are never imported by
    native_case_bridge. This does not authorize a release or source PASS.
    """
    try:
        root = Path(root).resolve(strict=True)
        inventory_file = root/'EDA_SOURCE_MANIFEST.json'
        manifest = json.loads(inventory_file.read_text(encoding='utf-8'))
        expected = manifest['files']
        tool = root/'tools/verify_release_source.py'
        relative = 'tools/verify_release_source.py'
        if (manifest.get('schema') != 'sqe.eda-source-inventory.v1' or
            not isinstance(expected, dict) or relative not in expected or
            tool.is_symlink() or not tool.is_file() or
            sha256(tool.read_bytes()).hexdigest() != expected[relative]):
            return False
        spec = importlib.util.spec_from_file_location('_sqe_source_inventory_check', tool)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # This uses the SAME strict lstat/reparse, ignored build dirs, and
        # contract attestation as the source gate, not a weak path whitelist.
        if module.frozen_contract_digest(root) != manifest['frozen_contract_digest']:
            return False
        locked = json.loads((root/'FOUNDATION_LOCK.json').read_text(encoding='utf-8'))
        if (manifest['frozen_contract_digest'] != locked['contract_digest'] or
            manifest['historical_foundation_tree_digest'] != locked['tree_digest'] or
            module.hash_bytes(module.canonical(expected)) != manifest['current_source_inventory_sha256']):
            return False
        actual = module.inventory(root)
        extras = set(actual)-set(expected)
        return bool(extras) and extras <= _LEGACY_TESTS and all(
            actual.get(name) == digest for name,digest in expected.items())
    except (OSError, ValueError, TypeError, KeyError, ImportError, AttributeError):
        return False


def _trusted_case_commands(root: Path, members: dict[str, bytes]) -> dict[str,list[str]]:
    """Only launch reviewed built-in code, after passing the active source-integrity gate.

    B01 has no native GDS/mesh registration bridge and remains blocked.
    B05/B09 run real JosephsonCircuits, B08 real scqubits. A PASS source gate
    or exact full inventory plus ONLY known legacy-test extras is mandatory.
    A contaminated host source gate still FAILS; physical gates remain BLOCKED.
    """
    try:
        gates=json.loads(members['software/QUALIFICATION.json'])['gates']
        integrity=[g for g in gates if g.get('id')=='source_integrity']
        if len(integrity)!=1:
            return {}
        if integrity[0].get('status')!='PASS' and not _trusted_release_with_legacy_tests(root):
            return {}
    except (KeyError,TypeError,ValueError):
        return {}
    bridge=root/'src/sqe_studio/native_case_bridge.py'
    if bridge.is_symlink() or not bridge.is_file():
        return {}
    return {case:[sys.executable,'-I',str(bridge),case] for case in ('B05','B08','B09')}


def run_scientific_case_matrix(root: Path, members: dict[str, bytes], *, notify=None,
                               elapsed_s: float = 0, commands: dict | None = None) -> dict:
    """Fixed one-button priority/budget plan with per-case fail-closed evidence.

    A99 may wire trusted native case commands from other domain owners. The
    B05/B08/B09 use trusted production numerical adapters; absent native engines
    are BLOCKED/NOT_RUN. The remaining cases require further physical wiring.
    """
    root=Path(root)
    say=notify or (lambda message:None)
    matrix,digest=_read_science_matrix(root)
    cases={item['id']:item for item in matrix['benchmark_cases']}
    budget=matrix['execution_policy']['target_wall_seconds']
    order=matrix['execution_policy']['priority_order']
    reserve=300  # time for diagnostics, ZIP hashing and atomic publication
    began=time.monotonic()
    outputs=[]
    say('PHASE_START science')
    for case_id in order:
        spec=cases[case_id]
        say('STAGE_START science '+case_id)
        remaining = max(0, budget-reserve-elapsed_s-(time.monotonic()-began))
        if case_id=='B00':
            result=_case_from_software(members,case_id)
        elif case_id=='B01':
            result=_case_from_native_cad_gate(members,case_id,root)
        elif commands and case_id in commands and remaining >= spec['budget_s']:
            result=_case_command(root,case_id,commands[case_id],min(spec['budget_s'],int(remaining)),say)
        elif commands and case_id in commands:
            result=_case_record(case_id,reason='BLOCKED_TIME_BUDGET')
        elif case_id=='B02':
            result=_case_from_em(members,case_id)
        else:
            result=_case_record(case_id,reason='BLOCKED_NOT_IMPLEMENTED')
        result['allocated_budget_s']=spec['budget_s']
        result['priority']=spec['priority']
        outputs.append(result)
        say('STAGE_END science '+case_id+' '+result['stage_status'])
    say('PHASE_END science')
    return {'schema':'sqe.scientific-benchmark-evidence.v1',
            'matrix_sha256':digest,'dispatch_release':matrix['target_release'],
            'application_runtime_release':'RC14.12',
            'budget_s':budget,'packaging_reserve_s':reserve,
            'existing_qualification_elapsed_s':round(elapsed_s,2),
            'cases':outputs,'case_count':len(outputs),
            'execution_attestation':'Only current-run SHA-verified subreports and supervised trusted adapters; no historical science reuse',
            'qualification':'NOT_ESTABLISHED','mode_identity':'UNRESOLVED',
            'em_to_hamiltonian':'BLOCKED','fabrication':'HOLD'}


def _read_plan(root: Path) -> dict:
    path = root / 'qualification_plan.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32000:
        raise ValueError('Release qualification plan missing or unsafe')
    plan = json.loads(path.read_text(encoding='utf-8'))
    if (plan.get('schema') != 'sqe.release-qualification-plan.v1' or
        plan.get('release') != 'RC14.12' or plan.get('profile') != 'eda_feedback' or
        plan.get('research_protocol') != 'fixed_release_exploratory_only_not_human_physics_approval' or
        plan.get('input_data_policy') != 'temporary reference geometry; never personal projects' or
        plan.get('prior_report_policy') != 'verify checksum and compare metadata only; native results never silently reused' or
        plan.get('test_duration_soft_ceiling_minutes') != 60 or
        plan.get('scientific_gates') != {
            'em_to_hamiltonian': 'BLOCKED_UNTIL_VALIDATED',
            'fabrication': 'HOLD', 'mode_identity': 'BLOCKED_UNTIL_COMPLEX_OVERLAP'}):
        raise ValueError('Release qualification plan does not match this software version')
    allowed = {'solve':True,'refine':False,'third_mesh':False,'mpi_ranks':'auto',
               'memory_budget_gb':8.0,'time_budget_seconds':840}
    if (plan.get('native_execution_purpose') != 'single_mesh_native_smoke_only_not_convergence_assessment' or
        plan.get('diagnostic_mode') != 'verbose_sanitized_per_test_windows_isolation_and_regression'):
        raise ValueError('Diagnostic and single-mesh release policy changed')
    if plan.get('native') != allowed:
        raise ValueError('Native protocol parameters changed without a new release')
    return plan


def _report_folder(root: Path) -> Path:
    folder = root / REPORT_FOLDER
    if folder.is_symlink():
        raise ValueError('Report folder must not be a symlink')
    folder.mkdir(mode=0o700,exist_ok=True)
    if folder.resolve() != (root.resolve() / REPORT_FOLDER):
        raise ValueError('Report folder escapes release')
    return folder


def next_report_path(root: Path) -> Path:
    """No file picker. Monotone run identifier; existing evidence is not overwritten."""
    root = Path(root).resolve(strict=True)
    _read_plan(root)
    folder = _report_folder(root)
    # Any matching name (including a dangling symlink or directory) reserves its
    # sequence. Never follow or overwrite an adversarial previous entry.
    seen = []
    for f in folder.iterdir():
        name = f.name
        # Reserve identifiers for active or interrupted qualifications as well.
        for suffix in ('', '.running', '.partial'):
            if suffix and not name.endswith(suffix):
                continue
            base = name[:-len(suffix)] if suffix else name
            match = NAME_PATTERN.fullmatch(base)
            if match:
                seen.append(int(match.group(1)))
                break
    # Launcher admits a single run at a time; O_EXCL in actual writing prevents
    # overwriting if two instances happen to choose the same next filename.
    following = 1 + max(seen,default=0)
    if following > 9999:
        raise ValueError('Maximum release report sequence exhausted')
    return folder / f'SQE-RC14_12-report-{following:04d}.zip'


def _previous(root: Path, output: Path) -> dict | None:
    """Admit only intact, same-release prior metadata; never recycle solver data."""
    from .feedback_qualification import _checked_members
    folder = _report_folder(root)
    candidates = []
    for path in folder.iterdir():
        match = NAME_PATTERN.fullmatch(path.name)
        if match and path != output:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        return None
    n, path = max(candidates)
    if path.is_symlink() or not path.is_file():
        return {'prior_sequence': n, 'status': 'REJECTED_NONREGULAR_NO_REUSE'}
    if path.stat().st_size > 48_000_000:
        return {'prior_sequence': n, 'status': 'REJECTED_OVERSIZE'}
    try:
        content = _checked_members(path)
        doc = json.loads(content['QUALIFICATION.json'])
        cycle = json.loads(content['CYCLE.json'])
        if (cycle.get('schema') != 'sqe.agent-cycle-feedback.v1' or
            cycle.get('release') != 'RC14.12' or
            cycle.get('report_sequence') != n or
            cycle.get('unchanged_native_runs_reused') is not False or
            cycle.get('plan_sha256') != sha256((root/'qualification_plan.json').read_bytes()).hexdigest() or
            cycle.get('baseline_source_sha256') != sha256((root/'EDA_SOURCE_MANIFEST.json').read_bytes()).hexdigest()):
            return {'prior_sequence': n, 'status': 'REJECTED_PROVENANCE_MISMATCH_NO_REUSE'}
        counts = doc.get('counts')
        if (not isinstance(counts, dict) or set(counts) != {'PASS', 'FAIL', 'BLOCKED'} or
            any(type(counts[k]) is not int or not 0 <= counts[k] <= 100000 for k in counts)):
            return {'prior_sequence': n, 'status': 'REJECTED_INVALID_COUNTS_NO_REUSE'}
        # The archive itself is SHA-256 identified; no prior tests or solver
        # artifacts are imported into the current result.
        return {'prior_sequence': n, 'prior_sha256': sha256(path.read_bytes()).hexdigest(),
                'prior_counts': counts, 'prior_release': cycle['release'],
                'status': 'HASH_VERIFIED_METADATA_ONLY_NO_SOLVER_CACHE'}
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        return {'prior_sequence': n, 'status': 'REJECTED_INVALID_NO_REUSE'}


def _blocker_hints(members: dict[str, bytes]) -> list[dict]:
    """Current-run FAIL/BLOCKED IDs only; no paths, logs or project contents."""
    hints = []
    for filename, field, phase in (('software/QUALIFICATION.json', 'gates', 'software'),
                                   ('em/QUALIFICATION.json', 'stages', 'native_em'),
                                   ('QUALIFICATION.json', 'stages', 'cycle')):
        if filename not in members:
            continue
        document = json.loads(members[filename])
        for stage in document.get(field, []):
            if not isinstance(stage, dict):
                continue
            status, identifier = stage.get('status'), stage.get('id')
            if (status in ('FAIL', 'BLOCKED') and isinstance(identifier, str) and
                re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', identifier)):
                hints.append({'phase': phase, 'gate': identifier, 'status': status})
    return hints[:100]


def _finalize_report(raw: Path, destination: Path, plan: dict, previous: dict | None,
                     progress: dict | None = None,
                     science: dict | None = None) -> dict:
    from .feedback_qualification import _checked_members
    from .qualification import _safe_log
    members = _checked_members(raw)
    root_record = json.loads(members['QUALIFICATION.json'])
    members.pop('INTEGRITY.json')
    if science is not None:
        members['BENCHMARK_CASE_MATRIX.json'] = (json.dumps(science,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if progress is not None:
        members['PROGRESS.json'] = (json.dumps(progress,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    # Compact top-level navigation across the full, SHA-verified per-phase logs.
    # Detailed stdout remains in software/logs/ and em/logs/; this file groups
    # the next debugging decisions, never promotes a numerical run to physics.
    def read_doc(name):
        try:
            return json.loads(members[name]) if name in members else {}
        except (ValueError, TypeError):
            return {}
    soft=read_doc('software/QUALIFICATION.json')
    em=read_doc('em/QUALIFICATION.json')
    soft_detail=read_doc('software/DIAGNOSTICS.json')
    native_stages = em.get('stages', []) if isinstance(em.get('stages'),list) else []
    diagnostic={'schema':'sqe.automatic-test-consolidated-diagnostics.v1',
        'release':plan['release'],'mode':'SINGLE_MESH_EM_SMOKE',
        'mesh_comparison_executed':False,
        'mesh_identity_and_convergence':'NOT_ESTABLISHED',
        'physical_approval':'BLOCKED',
        'software_counts':soft.get('counts'),
        'native_stage_results':[{'id':stage['id'],'status':stage['status'],
               'reason':_safe_log(str(stage.get('reason',''))[:400],
                  (str(destination.parent.parent),str(Path.home()),
                   os.environ.get('USERPROFILE',''))),
               **({'seconds':stage['seconds']} if 'seconds' in stage else {})}
              for stage in native_stages if isinstance(stage,dict)
              and isinstance(stage.get('id'),str)
              and stage.get('status') in ('PASS','FAIL','BLOCKED')][:50],
        'regression_group_events':soft_detail.get('regression_group_events',[]),
        'regression_failure_ids':soft_detail.get('regression_failure_ids',[]),
        'science_case_results':[{'id':case.get('case_id'),
              'status':case.get('stage_status'),
              'execution':case.get('execution_kind'),
              'reason':_safe_log(str(case.get('failure_reason',''))[:400],
                  (str(destination.parent.parent),str(Path.home()),
                   os.environ.get('USERPROFILE',''))),
              **({'diagnostic_excerpt':case['diagnostic_excerpt']}
                 if 'diagnostic_excerpt' in case else {})}
                for case in (science.get('cases',[]) if isinstance(science,dict) else [])],
        'detailed_logs':{'software':'software/logs/',
                         'windows_isolation':'software/logs/integrated_regression.txt',
                         'native_worker':'em/logs/',
                         'software_diagnostic_index':'software/DIAGNOSTICS.json'},
        'notes':['All reports are current-run and hash-verified',
                 'Missing/unsafe native data is BLOCKED, not PASS',
                 'Inspect logs before sharing; redaction is best-effort']}
    members['AUTOMATIC_TEST_DIAGNOSTICS.json'] = (
        json.dumps(diagnostic,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    record = {'schema':'sqe.agent-cycle-feedback.v1','release':plan['release'],
              'report_sequence':int(NAME_PATTERN.fullmatch(destination.name).group(1)),
              'finished_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'plan_sha256':sha256((destination.parent.parent/'qualification_plan.json').read_bytes()).hexdigest(),
              'baseline_source_sha256':sha256((destination.parent.parent/'EDA_SOURCE_MANIFEST.json').read_bytes()).hexdigest(),
              'research_protocol':plan['research_protocol'],
              'unchanged_native_runs_reused':False,
              'native_qualification_mode': 'SINGLE_MESH_SMOKE_NO_CONVERGENCE',
              'progress_evidence':'PROGRESS.json' if progress is not None else None,
              'benchmark_case_evidence':'BENCHMARK_CASE_MATRIX.json' if science is not None else None,
              'prior_report':previous,
              'agent_feedback':{'baseline_run':'RC14.12',
                                'analysis_contract':'software PASS/FAIL/BLOCKED separate from native and physical validation',
                                'unresolved': ['complex field and mesh identity', 'EM to quantum EPR bridge',
                                               'physical convergence', 'foundry qualification'],
                                'current_run_fail_and_blocked_gates': _blocker_hints(members)}}
    members['CYCLE.json'] = (json.dumps(record,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    members['INTEGRITY.json'] = (json.dumps({'schema':'sqe.qualification-file-hashes.v1',
        'files':{n:sha256(b).hexdigest() for n,b in sorted(members.items())}},sort_keys=True,indent=2)+'\n').encode()
    temp = destination.with_name(destination.name + '.partial')
    if destination.exists() or temp.exists():
        raise FileExistsError('Report sequence exists; never overwrite previous test evidence')
    try:
        with zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
            for name,data in sorted(members.items()):
                z.writestr(name,data)
        _checked_members(temp)
        if destination.exists():
            raise FileExistsError('Report path already exists')
        # Hard-link publishes verified bytes atomically without replacing an
        # existing name (also safe against a second launcher racing this one).
        os.link(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return root_record


def run_release_qualification(root: Path, destination: Path, *, notify=None,
                              case_commands: dict | None = None,
                              selection=None, cancel=None) -> dict:
    """Run current-release comprehensive and real-native QA, never a fixture substitute."""
    if selection is not None:
        if case_commands is not None:
            raise ValueError('Selected plans accept trusted catalog tasks only')
        from .testing.runner import run_selected
        return run_selected(root, destination, selection, notify=notify, cancel=cancel)
    root = Path(root).resolve(strict=True)
    plan = _read_plan(root)
    folder = _report_folder(root)
    destination = Path(destination).absolute()
    if destination.parent != folder or not NAME_PATTERN.fullmatch(destination.name):
        raise ValueError('Report must use an incremental release-local filename')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('An earlier report already owns this number')
    reservation = destination.with_name(destination.name + '.running')
    # Cross-process O_EXCL reservation; the GUI also guards in-process runs.
    # An interrupted reservation remains visible to the next-number allocator.
    handle = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(handle)
    try:
        # Preserve the original monkeypatch/extension contract for callers
        # that provide only the historical notify argument.
        if case_commands is None:
            return _run_reserved_qualification(root, destination, plan, notify=notify)
        return _run_reserved_qualification(root, destination, plan, notify=notify,
                                           case_commands=case_commands)
    finally:
        reservation.unlink(missing_ok=True)


def _run_reserved_qualification(root: Path, destination: Path, plan: dict, *, notify=None,
                                case_commands: dict | None = None) -> dict:
    from .feedback_qualification import qualify_eda_feedback
    from .qualification import _safe_log

    progress = _ProgressEvidence(notify)
    progress.start()
    previous = None
    try:
        previous = _previous(root, destination)
        progress.notify('Previous reports: '+('none' if previous is None else str(previous['status']))+
             '. Never reusing solver output as a fresh scientific result.')
        with tempfile.TemporaryDirectory(prefix='sqe-release-cycle-') as scratch:
            raw = Path(scratch)/'unified.zip'
            # One-click release-only benchmark, NOT physical or foundry approval.
            options = dict(plan['native'])
            options.update(reviewer='SQEFixedProtocol', acknowledged=True)
            qualify_eda_feedback(root, raw, em_options=options, notify=progress.notify)
            from .feedback_qualification import _checked_members
            raw_members=_checked_members(raw)
            selected_commands = (case_commands if case_commands is not None
                                 else _trusted_case_commands(root, raw_members))
            science=run_scientific_case_matrix(root,raw_members,notify=progress.notify,
                  elapsed_s=time.monotonic()-progress.begin,commands=selected_commands)
            progress.notify('Report validation: integrity checks and atomic create-only publication')
            evidence = progress.finish('REPORT_READY_NOT_SCIENTIFICALLY_APPROVED')
            result = _finalize_report(raw, destination, plan, previous, evidence, science)
    except Exception as exc:
        # Preserve a smaller numbered diagnostic ZIP when any phase or packaging
        # unexpectedly fails. No fabricated PASS or native solver completion.
        safe = _safe_log(type(exc).__name__+': '+str(exc)[:1200],
              (str(root),str(Path.home()),os.environ.get('USERPROFILE','')))
        progress.notify('FAIL: release_qualification_exception - writing minimal diagnostic ZIP')
        try:
            # A controller crash must still disclose missing/unexecuted science.
            science=run_scientific_case_matrix(root,{},notify=progress.notify,
                  elapsed_s=time.monotonic()-progress.begin)
        except Exception:
            science={'schema':'sqe.scientific-benchmark-evidence.v1',
                     'cases':[_case_record(i,reason='BLOCKED_CONTROLLER_OR_MATRIX_FAILURE')
                              for i in _CASE_IDS],
                     'qualification':'NOT_ESTABLISHED','mode_identity':'UNRESOLVED',
                     'em_to_hamiltonian':'BLOCKED','fabrication':'HOLD'}
        evidence = progress.finish('FAIL_DIAGNOSTIC_NOT_SCIENTIFICALLY_APPROVED')
        with tempfile.TemporaryDirectory(prefix='sqe-release-error-') as scratch:
            raw=Path(scratch)/'failed.zip'
            payload={'QUALIFICATION.json':json.dumps({
                     'schema':'sqe.failed-release-qualification.v1',
                     'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE',
                     'profile':'eda_feedback',
                     'counts':{'PASS':0,'FAIL':1,'BLOCKED':0},
                     'stages':[{'id':'release_qualification_exception','status':'FAIL',
                                'reason':safe}],
                     'scientific_qualification':'NOT_ESTABLISHED',
                     'fabrication':'HOLD'},sort_keys=True).encode(),
                     'SUMMARY.md':('# Release qualification failed\n\n'+safe+'\n'
                       +'No solver result or release acceptance is claimed.\n').encode()}
            payload['INTEGRITY.json']=json.dumps({'schema':'sqe.qualification-file-hashes.v1',
                'files':{k:sha256(v).hexdigest() for k,v in payload.items()}}).encode()
            with zipfile.ZipFile(raw,'w',zipfile.ZIP_DEFLATED) as z:
                for name,value in payload.items():z.writestr(name,value)
            result=_finalize_report(raw,destination,plan,previous,evidence,science)
    progress.notify('SHA-256 checked, release-local report ready: '+destination.name)
    return result
