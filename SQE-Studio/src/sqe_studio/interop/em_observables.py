"""Research-only Palace modal scalar diagnostics; never certify mode identity.

All inputs are hash-verified native EM qualification ZIP members. The tabular
observables are not electromagnetic field vectors on a common spatial mesh;
scalar similarity is NOT a valid substitute for field overlap.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from pathlib import Path
import zipfile

from .em_convergence import analyze_report_zip, ConvergenceEvidenceError

MAX_TABLE = 256_000


def _table(raw: bytes, required: str):
    if not raw or len(raw) > MAX_TABLE:
        raise ConvergenceEvidenceError('Missing or oversized Palace scalar table')
    try:
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    except UnicodeError as exc:
        raise ConvergenceEvidenceError('Invalid UTF-8 in Palace scalar table') from exc
    if not 2 <= len(rows) <= 33 or not 2 <= len(rows[0]) <= 32:
        raise ConvergenceEvidenceError('Malformed Palace scalar table dimensions')
    header = [x.strip() for x in rows[0]]
    if header[0].lower() != 'm' or not any(required in h for h in header[1:]):
        raise ConvergenceEvidenceError('Unexpected Palace scalar columns')
    values = []
    for idx, row in enumerate(rows[1:], 1):
        if len(row) != len(header):
            raise ConvergenceEvidenceError('Malformed Palace scalar table row')
        try:
            numbers = [float(v) for v in row]
        except ValueError as exc:
            raise ConvergenceEvidenceError('Non-numeric Palace scalar table') from exc
        if not all(math.isfinite(v) for v in numbers) or numbers[0] != idx:
            raise ConvergenceEvidenceError('Nonfinite values or unexpected mode index')
        values.append(numbers)
    return header, values


def assess_observables(report_zip: Path) -> dict:
    """Read one or more native solves, with same ZIP integrity enforcement as review.

    Advisory thresholds identify large discontinuities; they are not validated
    physical acceptance tolerances and cannot promote scientific status.
    """
    # analyze_report_zip verifies every ZIP member and the passed worker stages.
    series = analyze_report_zip(report_zip)
    points = series['points']
    results = []
    with zipfile.ZipFile(report_zip) as z:
        for tag in ('native_palace_solve', 'native_palace_refinement', 'native_palace_third')[:len(points)]:
            qname = f'native/{tag}-port-Q.csv'
            ename = f'native/{tag}-domain-E.csv'
            if qname not in z.namelist() or ename not in z.namelist():
                results.append({'point':len(results)+1, 'status':'BLOCKED',
                                'reason':'Native scalar tables unavailable; no field signature'})
                continue
            qheader, qrows = _table(z.read(qname), 'Q_ext')
            eheader, erows = _table(z.read(ename), 'E_elec')
            if len(qrows) != 1 or len(erows) != 1:
                raise ConvergenceEvidenceError('Expected a single-mode research reference')
            qr, er = qrows[0], erows[0]
            qvals = [qr[i] for i, name in enumerate(qheader) if name.startswith('Q_ext')]
            kvals = [qr[i] for i, name in enumerate(qheader) if 'ext' in name.lower() and ('κ' in name or 'kappa' in name.lower())]
            elec = next((er[i] for i, h in enumerate(eheader) if 'E_elec' in h), None)
            mag = next((er[i] for i, h in enumerate(eheader) if 'E_mag' in h), None)
            if not qvals or not kvals or elec is None or mag is None or elec <= 0 or mag <= 0:
                raise ConvergenceEvidenceError('Incomplete native Q/energy table')
            ratio = elec / mag
            results.append({'point':len(results)+1, 'status':'NUMERIC_INDICATORS_ONLY',
                            'q_ext':qvals,'kappa_ext_GHz':kvals,
                            'energy_electric_over_magnetic':ratio,
                            'negative_coupling_columns':sum(k < 0 for k in kvals),
                            'domain_E_sha256':hashlib.sha256(z.read(ename)).hexdigest(),
                            'port_Q_sha256':hashlib.sha256(z.read(qname)).hexdigest()})
    flags = []
    valid = [v for v in results if v['status']=='NUMERIC_INDICATORS_ONLY']
    if valid:
        for row in valid:
            if row['negative_coupling_columns']:
                flags.append({'type':'NEGATIVE_NATIVE_KAPPA', 'point':row['point'],
                              'meaning':'Investigate sign convention and port loss; NOT automatic solver failure'})
            if abs(row['energy_electric_over_magnetic']-1)>0.1:
                flags.append({'type':'ENERGY_BALANCE_SCALAR_DEVIATION','point':row['point'],
                              'meaning':'Expert must review normalization and modeling assumptions'})
        for before, after in zip(valid,valid[1:]):
            if before['point']+1 == after['point']:
                # Relative Q changes are heuristic flags; do not assert physical convergence.
                for i,(q0,q1) in enumerate(zip(before['q_ext'],after['q_ext']),1):
                    if q0 > 0 and q1 > 0 and abs(q1-q0)/max(q0,q1)>0.25:
                        flags.append({'type':'Q_EXT_DRIFT','points':[before['point'],after['point']],
                                      'port':i,'relative_change':abs(q1-q0)/max(q0,q1)})
                if any((a < 0) != (b < 0) for a,b in zip(before['kappa_ext_GHz'],after['kappa_ext_GHz'])):
                    flags.append({'type':'KAPPA_SIGN_CHANGED', 'points':[before['point'],after['point']]})
    return {'schema':'sqe.em-observable-advisory.v1',
            'source_report_sha256':series['source_report_sha256'],
            'source_integrity':'all_member_sha256_checked_by_offline_review',
            'frequency_convergence':'NOT_ESTABLISHED', 'mode_identity':'UNRESOLVED',
            'scalar_proxies_are_not_field_overlap':True,
            'points':results,'advisory_flags':flags,
            'downstream_automatic_optimization':'BLOCKED_REQUIRES_EXPERT_REVIEW',
            'fabrication_status':'HOLD'}
