"""Revision-bound, display-only native Palace modal evidence for generic Results.

Call ONLY after orchestration.artifacts.verify_manifest has rehashed all artifacts.
No mode tracking, negative-kappa correction, convergence, or field interpolation.
This module never reads arbitrary project paths or creates native solver output.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
import re

from ..orchestration.artifacts import safe_file, ArtifactInvalid

SCHEMA = 'sqe.em-native-results-screen.v1'
MAX_TABLE_BYTES = 256_000
MAX_MODES = 32
MAX_COLUMNS = 80
PORT_Q = re.compile(r'^Q_ext\[(\d+)\]$')
PORT_K = re.compile(r'^(?:κ|kappa)_ext\[(\d+)\]\s*\(GHz\)$', re.I)

class NativeEMEvidenceError(ValueError):
    pass


def _table(folder: Path, name: str, declared: set[str], *, mandatory=False):
    if name not in declared:
        if mandatory:
            raise NativeEMEvidenceError('Required native Palace eigenmode table is not declared')
        return None
    try:
        path = safe_file(folder, name)
        if not 0 < path.stat().st_size <= MAX_TABLE_BYTES:
            raise NativeEMEvidenceError('Native Palace scalar table is empty or oversized')
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            raw = list(csv.reader(handle))
    except (OSError, UnicodeError, ArtifactInvalid, csv.Error) as exc:
        raise NativeEMEvidenceError('Unsafe or unreadable native Palace scalar table') from exc
    if not 2 <= len(raw) <= MAX_MODES + 1 or not 2 <= len(raw[0]) <= MAX_COLUMNS:
        raise NativeEMEvidenceError('Invalid native Palace scalar table shape')
    headers = [h.strip() for h in raw[0]]
    if headers[0] != 'm' or len(set(headers)) != len(headers):
        raise NativeEMEvidenceError('Invalid or ambiguous Palace scalar table headings')
    rows = []
    for index, row in enumerate(raw[1:], 1):
        if len(row) != len(headers):
            raise NativeEMEvidenceError('Incomplete native Palace scalar row')
        try:
            values = [Decimal(cell.strip()) for cell in row]
        except (InvalidOperation, ValueError) as exc:
            raise NativeEMEvidenceError('Non-numeric Palace scalar row') from exc
        if not all(n.is_finite() for n in values) or values[0] != index:
            raise NativeEMEvidenceError('Nonfinite values or inconsistent Palace mode indices')
        floats = [float(n) for n in values]
        if not all(math.isfinite(v) for v in floats):
            raise NativeEMEvidenceError('Unrepresentable Palace scalar values')
        rows.append(floats)
    return headers, rows


def native_em_evidence(folder: Path, manifest: dict) -> dict | None:
    """Extract optional native Q/port/energy observations without physical promotion.

    Caller MUST check revision and content hashes (verify_manifest) *before* this
    reader. The declared artifact names are not a substitute for hash checking.
    """
    if manifest.get('engine') != 'sqdmetal_palace' or (
        manifest.get('artifact_type') != 'palace.eigenmodes'
        if 'artifact_type' in manifest else manifest.get('kind') != 'eigenmode'):
        return None
    declared = {a['name'] for a in manifest['artifacts']}
    prefix = 'sqe_em/outputFiles/'
    eig = _table(folder, prefix + 'eig.csv', declared, mandatory=True)
    assert eig is not None
    headers, eigen = eig
    if len(headers) < 4 or 'ghz' not in headers[1].lower() or headers[3] != 'Q':
        raise NativeEMEvidenceError('Unsupported native eigenfrequency/Q columns')
    qtable = _table(folder, prefix + 'port-Q.csv', declared)
    energy = _table(folder, prefix + 'domain-E.csv', declared)
    for tab in (qtable, energy):
        if tab is not None and len(tab[1]) != len(eigen):
            raise NativeEMEvidenceError('Palace scalar outputs have different mode counts')
    q_fields = []
    if qtable:
        qhead = qtable[0]
        q_indices = {int(m.group(1)): i for i,h in enumerate(qhead) if (m := PORT_Q.fullmatch(h))}
        k_indices = {int(m.group(1)): i for i,h in enumerate(qhead) if (m := PORT_K.fullmatch(h))}
        if (not q_indices or q_indices.keys() != k_indices.keys() or
            any(x < 1 or x > 32 for x in q_indices) or
            len(q_indices) * 2 != len(qhead) - 1):
            raise NativeEMEvidenceError('Ambiguous native Palace Q/kappa port pairing')
        q_fields = [(port, q_indices[port], k_indices[port]) for port in sorted(q_indices)]
    e_fields = None
    if energy:
        ehead = energy[0]
        if 'E_elec (J)' not in ehead or 'E_mag (J)' not in ehead:
            raise NativeEMEvidenceError('Unsupported Palace energy units/columns')
        e_fields = (ehead.index('E_elec (J)'), ehead.index('E_mag (J)'))
    modes = []
    for i, eigrow in enumerate(eigen):
        freq, qtotal = eigrow[1], eigrow[3]
        if not 0 < freq <= 1_000 or not qtotal > 0:
            raise NativeEMEvidenceError('Nonphysical native Palace reported frequency/Q')
        ports = []
        if qtable:
            for port, qix, kix in q_fields:
                qval, kval = qtable[1][i][qix], qtable[1][i][kix]
                if not qval > 0:
                    raise NativeEMEvidenceError('Nonpositive Palace external Q')
                expected = freq / qval
                mismatch = abs(abs(kval) - expected) / expected
                ports.append({'port_index':port, 'q_ext':qval,
                              'native_kappa_ext_GHz':kval,
                              'abs_kappa_vs_frequency_over_q_relative_difference':mismatch,
                              'advisory': ('REVIEW_NATIVE_KAPPA_SIGN' if kval < 0 else
                                           'REVIEW_KAPPA_MAGNITUDE' if mismatch > 0.02 else
                                           'MAGNITUDE_NUMERICALLY_CONSISTENT_ONLY')})
        ratio = None
        if energy:
            elec, mag = energy[1][i][e_fields[0]], energy[1][i][e_fields[1]]
            if elec <= 0 or mag <= 0:
                raise NativeEMEvidenceError('Nonpositive native electric/magnetic energies')
            ratio = elec / mag
        modes.append({'native_mode_index':i+1, 'frequency_GHz':freq,
                      'q_total':qtotal, 'ports':ports,
                      'electric_to_magnetic_energy_ratio':ratio})
    probes = [a for a in manifest['artifacts'] if a['name'] in
              (prefix + 'probe-E.csv', prefix + 'probe-B.csv')]
    vector = [a for a in manifest['artifacts'] if a['name'].startswith('sqe_em/outputFiles/paraview/')
              or a['name'].startswith('sqe_em/outputFiles/gridfunction/')]
    status = ('NATIVE_FIELD_FILES_PRESENT_COORDINATES_AND_PHASE_UNREVIEWED'
              if probes or vector else 'NO_NATIVE_COMPLEX_FIELD_EXPORT')
    return {'schema':SCHEMA, 'source':'revision_and_sha256_verified_native_run',
            'modes':modes,
            'scalar_tables':{'port_q':bool(qtable), 'domain_energy':bool(energy)},
            'field_acquisition':{'status':status,
                                 'artifact_names':[a['name'] for a in (probes+vector)[:24]],
                                 'artifact_count':len(probes)+len(vector),
                                 'common_coordinate_domain_verified':False,
                                 'complex_vector_normalization_verified':False},
            'mode_identity':'UNRESOLVED',
            'mesh_convergence':'NOT_ESTABLISHED',
            'em_to_hamiltonian':'BLOCKED',
            'automatic_geometry_optimization':'BLOCKED',
            'fabrication':'HOLD',
            'limitations':['Native Q and port values are display-only; no independent loss model validation',
                           'Negative native coupling signs are preserved for physical convention review',
                           'Native mode index, frequency and scalar energies are not field-overlap evidence',
                           'Common-domain complex field sampling and expert review are mandatory for mode identity']}


def compare_native_em_evidence(left: dict | None, right: dict | None,
                               frequency_comparison: dict) -> dict:
    """Numerical-only Q and port deltas for already comparable physical inputs.

    Never promotes same mode *index* to same physical mode. Delta rows are
    diagnostic flags; geometric optimization and convergence remain blocked.
    """
    blocked=lambda reason:{'status':'BLOCKED','reason':reason,'rows':[],
                           'mode_identity':'UNRESOLVED','physical_convergence':'NOT_ESTABLISHED'}
    if frequency_comparison.get('status')!='native_mode_index_differences_for_expert_review':
        return blocked('Geometry, materials, EM study or eigenfrequency comparison not compatible')
    if (not isinstance(left,dict) or not isinstance(right,dict) or
        left.get('schema')!=SCHEMA or right.get('schema')!=SCHEMA):
        return blocked('Both native runs must provide verified Palace modal observations')
    lm,rm=left.get('modes'),right.get('modes')
    if not isinstance(lm,list) or not isinstance(rm,list) or len(lm)!=len(rm):
        return blocked('Different native mode counts')
    rows=[]
    for i,(a,b) in enumerate(zip(lm,rm),1):
        if a['native_mode_index']!=i or b['native_mode_index']!=i:
            return blocked('Nonmatching native mode indexes')
        qa,qb=a['q_total'],b['q_total']
        ports_a={p['port_index']:p for p in a['ports']}
        ports_b={p['port_index']:p for p in b['ports']}
        # Do not compare wrong ports or fill them with invented zeros.
        if ports_a.keys()!=ports_b.keys():
            return blocked('Native port identity/count differs; expert map required')
        def delta(x,y):
            return abs(y-x)/max(abs(x),abs(y))
        rows.append({'native_mode_index':i,'observable':'Q_total', 'port_index':None,
                     'left':qa,'right':qb,'relative_change':delta(qa,qb),
                     'sign_changed':False})
        for p in sorted(ports_a):
            ap,bp=ports_a[p],ports_b[p]
            rows.append({'native_mode_index':i,'observable':'Q_ext','port_index':p,
                         'left':ap['q_ext'],'right':bp['q_ext'],
                         'relative_change':delta(ap['q_ext'],bp['q_ext']),
                         'sign_changed':(ap['native_kappa_ext_GHz'] < 0) !=
                                        (bp['native_kappa_ext_GHz'] < 0)})
    return {'status':'NATIVE_INDEX_SCALAR_DIAGNOSTICS_ONLY',
            'reason':'Same physical settings except mesh; native mode and port identities are not independently tracked',
            'rows':rows, 'mode_identity':'UNRESOLVED',
            'physical_convergence':'NOT_ESTABLISHED',
            'port_loss_validation':'NOT_ESTABLISHED',
            'optimization':'BLOCKED'}
