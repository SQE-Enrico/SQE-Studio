"""Pure, fail-closed Maxwell capacitance reduction for *numerical screening*.

Input is exactly ``sqe.capacitance-topology.v1`` (the frozen M1 A11/A12
contract). No native bytes are opened here: ``expected_source`` must be
provided by an independently authenticating caller. Matching user-supplied
hash strings is NOT source authentication. Nor is a typed review declaration
proof of independent review. This module NEVER returns an authorized E_C for
scqubits, E_J, or a scientifically qualified transmon parameter.

For charge-neutral floating terminals F, solve C_FF V_F = -C_FR V_R;
C_eff = C_RR - C_RF solve(C_FF, C_FR). Fixed-zero nodes are eliminated by
Dirichlet voltage, NOT Schur elimination. The native reference ground is
already eliminated and MUST NOT be listed as a floating terminal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import math
import re
from typing import Mapping

SCHEMA = 'sqe.capacitance-topology.v1'
_SCREEN = 'NUMERICAL_SCREEN_ONLY'
_E = Decimal('1.602176634e-19')  # exact SI elementary charge, coulomb
_H = Decimal('6.62607015e-34')  # exact SI Planck constant, J s
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_SOURCE_KEYS = frozenset({'revision_digest', 'study_id', 'manifest_sha256',
                          'terminal_csv_sha256', 'deck_sha256', 'mesh_sha256'})
_KEYS = frozenset({'schema', 'scientific_status', 'source', 'terminal_labels',
                   'maxwell_matrix_f', 'reference_ground', 'proposed_pair',
                   'other_terminal_policy', 'review'})
_MAX_N = 32
# Dimensionless numerical screens are deliberately conservative; not
# material/convergence uncertainty bounds or physical authority.
_MAX_CONDITION = 1.0e10
_SYMMETRY_RTOL = 1.0e-9
_ROWSUM_RTOL = 1.0e-9
_MIN_CAP_F = 1.0e-24
_MAX_CAP_F = 1.0e-6
_JUNCTION_ASSUMPTION = 'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'


class ReductionBlocked(ValueError):
    """Typed *expected* failure: no numerical/physical transfer on rejection."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReviewedTopologyDeclaration:
    """Caller *declaration*, never authenticates a reviewer or permits transfer.

    Required only when the frozen payload claims APPROVED/REVIEWED_TOPOLOGY.
    A99 must authenticate the underlying bytes, independent reviewer, circuit
    and junction before any future, separately designed transfer interface.
    """

    record_sha256: str
    revision_digest: str
    manifest_sha256: str
    terminal_labels: tuple[str, ...]
    native_ground_group_ids: tuple[int, ...]
    circuit_convention: str


@dataclass(frozen=True, slots=True)
class CapacitanceDecision:
    status: str
    reason: str
    source: dict[str, str] | None
    numerical_preview: dict[str, object] | None
    transfer_status: str = 'BLOCKED_NO_INDEPENDENT_PHYSICAL_AUTHORIZATION'

    def as_dict(self) -> dict[str, object]:
        return {'schema': 'sqe.capacitance-reduction-decision.a12.v1',
                'status': self.status, 'reason': self.reason,
                'source': dict(self.source) if self.source is not None else None,
                'numerical_preview': self.numerical_preview,
                'transfer_status': self.transfer_status,
                'scqubits_parameter': None, 'ej_over_h_hz': None}


def _block(code: str, reason: str) -> None:
    raise ReductionBlocked(code, reason)


def _mapping(value: object, keys: frozenset[str], name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _block('BLOCKED_INVALID_INPUT', f'{name} requires exactly {sorted(keys)}')
    return value


def _digest(v: object, name: str) -> str:
    if not isinstance(v, str) or _SHA.fullmatch(v) is None:
        _block('BLOCKED_INVALID_INPUT', f'{name} must be a lowercase SHA-256 digest')
    return v


def _labels(v: object, name: str, *, minimum: int = 0) -> tuple[str, ...]:
    if (not isinstance(v, (list, tuple)) or len(v) < minimum or len(v) > _MAX_N or
            any(not isinstance(x, str) or not x or x != x.strip() or
                len(x) > 128 or any(ord(c) < 32 for c in x) for x in v)):
        _block('BLOCKED_TOPOLOGY', f'{name} requires ordered, nonempty terminal labels')
    if len(v) != len(set(v)):
        _block('BLOCKED_TOPOLOGY', f'Duplicate {name} identities')
    return tuple(v)


def _groups(value: object) -> tuple[int, ...]:
    if (not isinstance(value, (list, tuple)) or not value or len(value) > _MAX_N or
            any(type(v) is not int or not 1 <= v <= 65535 for v in value) or
            len(set(value)) != len(value)):
        _block('BLOCKED_TOPOLOGY', 'Explicit distinct native reference-ground group IDs required')
    return tuple(value)


def _source(value: object) -> dict[str, str]:
    src = _mapping(value, _SOURCE_KEYS, 'source')
    study = src['study_id']
    if (not isinstance(study, str) or not study or study != study.strip() or
            len(study) > 128 or any(ord(c) < 32 for c in study)):
        _block('BLOCKED_INVALID_INPUT', 'Exact nonempty saved study_id required')
    d = {k: _digest(src[k], k) for k in _SOURCE_KEYS if k != 'study_id'}
    if len(set(d.values())) != len(d):
        _block('BLOCKED_INVALID_INPUT', 'Aliased source digests do not identify distinct artifacts')
    d['study_id'] = study
    return {k: d[k] for k in sorted(_SOURCE_KEYS)}


def _matrix(value: object, n: int) -> tuple[list[list[float]], float]:
    if not isinstance(value, (list, tuple)) or len(value) != n:
        _block('BLOCKED_INVALID_INPUT', 'Full square ordered Maxwell matrix in farads required')
    rows: list[list[float]] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != n:
            _block('BLOCKED_INVALID_INPUT', 'Incomplete Maxwell terminal list or matrix shape')
        vals = []
        for x in row:
            if type(x) not in (float, int, Decimal):
                _block('BLOCKED_INVALID_INPUT', 'Capacitance entries must be numeric SI farads, not strings/bools')
            try:
                y = float(x)
            except (OverflowError, ValueError):
                _block('BLOCKED_INVALID_INPUT', 'Unrepresentable capacitance entry')
            if not math.isfinite(y):
                _block('BLOCKED_INVALID_INPUT', 'Nonfinite capacitance entry')
            if type(x) is Decimal and x != 0 and y == 0:
                _block('BLOCKED_NUMERICS', 'Underflow converting exact SI capacitance to a float')
            vals.append(y)
        rows.append(vals)
    scale = max(rows[i][i] for i in range(n))
    if not _MIN_CAP_F <= scale <= _MAX_CAP_F:
        _block('BLOCKED_NUMERICS', 'Maxwell diagonal magnitude incompatible with SI-F screening bounds')
    for i in range(n):
        if rows[i][i] <= 0:
            _block('BLOCKED_NUMERICS', 'Nonpositive Maxwell self capacitance')
        for j in range(n):
            if i != j and rows[i][j] > 0:
                _block('BLOCKED_NUMERICS', 'Positive Maxwell off-diagonal: wrong signs/convention')
            if abs(rows[i][j] - rows[j][i]) > _SYMMETRY_RTOL * scale:
                _block('BLOCKED_NUMERICS', 'Nonsymmetric Maxwell capacitance matrix')
        if math.fsum(rows[i]) < -_ROWSUM_RTOL * scale:
            _block('BLOCKED_NUMERICS', 'Negative capacitance to the reference ground / incomplete topology')
    # Normalize near 1 to avoid squaring SI ~1e-15 terms, determinant overflow,
    # or comparing an unscaled pivot to an arbitrary absolute epsilon.
    return [[((rows[i][j] + rows[j][i]) / 2) / scale for j in range(n)]
            for i in range(n)], scale


def _cholesky(a: list[list[float]], name: str) -> list[list[float]]:
    n = len(a)
    l = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            pivot = a[i][j] - math.fsum(l[i][k] * l[j][k] for k in range(j))
            if i == j:
                if not math.isfinite(pivot) or pivot <= 0:
                    _block('BLOCKED_NUMERICS', f'{name} not SPD (singular/gauge/negative energy)')
                l[i][j] = math.sqrt(pivot)
            else:
                l[i][j] = pivot / l[j][j]
    return l


def _solve(l: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(l)
    y = [0.0] * n
    for i in range(n):
        y[i] = (rhs[i] - math.fsum(l[i][j] * y[j] for j in range(i))) / l[i][i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (y[i] - math.fsum(l[j][i] * x[j] for j in range(i + 1, n))) / l[i][i]
    if any(not math.isfinite(v) for v in x):
        _block('BLOCKED_NUMERICS', 'Nonfinite linear solution')
    return x


def _checked_spd(a: list[list[float]], name: str) -> list[list[float]]:
    l = _cholesky(a, name)
    # Bounded 32x32 Cholesky solves estimate infinity-norm condition without
    # forming a matrix inverse or using a pseudoinverse. Do not regularize.
    n = len(a)
    norm_a = max(math.fsum(abs(x) for x in row) for row in a)
    row_sums = [0.0] * n
    for col in range(n):
        unit = [1.0 if i == col else 0.0 for i in range(n)]
        solution = _solve(l, unit)
        for i, item in enumerate(solution):
            row_sums[i] += abs(item)
    condition = norm_a * max(row_sums)
    if not math.isfinite(condition) or condition > _MAX_CONDITION:
        _block('BLOCKED_NUMERICS', f'{name} ill-conditioned (estimated condition > 1e10)')
    return l


def _schur(a: list[list[float]], r: tuple[int, ...], floating: tuple[int, ...]) -> list[list[float]]:
    if not floating:
        return [[a[i][j] for j in r] for i in r]
    ff = [[a[i][j] for j in floating] for i in floating]
    ff_factor = _checked_spd(ff, 'Floating-node C_FF')
    solved = [_solve(ff_factor, [a[f][j] for f in floating]) for j in r]
    eff = [[a[i][j] - math.fsum(a[i][f] * solved[col][k]
                                     for k, f in enumerate(floating))
            for col, j in enumerate(r)] for i in r]
    # Minor roundoff is harmless, but significant Schur asymmetry means the
    # source data / numeric elimination cannot safely be used.
    asymmetry = max(abs(eff[i][j] - eff[j][i]) for i in range(len(r)) for j in range(len(r)))
    if asymmetry > _SYMMETRY_RTOL:
        _block('BLOCKED_NUMERICS', 'Asymmetric floating-node Schur result')
    return [[(eff[i][j] + eff[j][i]) / 2 for j in range(len(r))]
            for i in range(len(r))]


def _ec_hz(c_f: float) -> float:
    if not math.isfinite(c_f) or c_f <= 0:
        _block('BLOCKED_NUMERICS', 'Nonpositive differential capacitance')
    with localcontext() as ctx:
        ctx.prec = 45
        return float(_E * _E / (Decimal(2) * _H * Decimal(str(c_f))))


def _review(payload: Mapping[str, object], src: dict[str, str],
            labels: tuple[str, ...], groups: tuple[int, ...],
            claim: ReviewedTopologyDeclaration | None, convention: str) -> str:
    review = _mapping(payload['review'], frozenset({'status', 'record_sha256'}), 'review')
    scientific_status = payload['scientific_status']
    if scientific_status not in ('UNREVIEWED_TOPOLOGY', 'REVIEWED_TOPOLOGY'):
        _block('BLOCKED_TOPOLOGY', 'Unsupported topology scientific status')
    if review['status'] == 'NOT_APPROVED' and review['record_sha256'] is None:
        if claim is not None or scientific_status != 'UNREVIEWED_TOPOLOGY':
            _block('BLOCKED_NOT_REVIEWED', 'Unapproved topology cannot carry a reviewed declaration')
        return 'NOT_APPROVED'
    if review['status'] != 'APPROVED' or scientific_status != 'REVIEWED_TOPOLOGY':
        _block('BLOCKED_NOT_REVIEWED', 'Conflicting topology/review claims')
    record = _digest(review['record_sha256'], 'review record_sha256')
    if (type(claim) is not ReviewedTopologyDeclaration or
            record != claim.record_sha256 or src['revision_digest'] != claim.revision_digest or
            src['manifest_sha256'] != claim.manifest_sha256 or labels != claim.terminal_labels or
            groups != claim.native_ground_group_ids or claim.circuit_convention != convention):
        _block('BLOCKED_NOT_REVIEWED', 'Review claim not bound to exact revision, manifest, conductors, ground and circuit')
    # A caller's declaration does not attest any bytes or reviewer authority.
    return 'DECLARED_NOT_INDEPENDENTLY_AUTHENTICATED'


def assess_transmon_capacitance(
    topology: object, *, expected_source: Mapping[str, str] | None = None,
    expected_terminal_labels: tuple[str, ...] | None = None,
    expected_ground_group_ids: tuple[int, ...] | None = None,
    configuration: str = 'TWO_ISLAND_CHARGE_TRANSFER',
    junction_capacitance_assumption: str | None = None,
    reviewed_topology: ReviewedTopologyDeclaration | None = None,
) -> CapacitanceDecision:
    """Screen an explicitly selected pair; never authorize quantum transfer.

    ``configuration`` specifies either two-island transfer q=(+e,-e) or a
    grounded single island a with island b *held at zero voltage* (not a
    floating island). All other terminals must be exhaustively classified.
    ``expected_source``, ``expected_terminal_labels`` and
    ``expected_ground_group_ids`` are authenticated by A99/A11 *before*
    calling; this pure function only compares declarations, not native bytes.
    Explicit junction treatment is M1's matrix-ONLY assumption, not a claim
    that Josephson shunt capacitance is physically zero or already present.
    """
    trusted_source = None
    try:
        inp = _mapping(topology, _KEYS, 'sqe.capacitance-topology.v1')
        if inp['schema'] != SCHEMA:
            _block('BLOCKED_INVALID_INPUT', 'Unsupported capacitance topology schema')
        src = _source(inp['source'])
        expected = _source(expected_source)
        if src != expected:
            _block('BLOCKED_STALE_SOURCE', 'Source revision/study/manifest/CSV/deck/mesh mismatch')
        trusted_source = src  # equality only, not external authentication
        labels = _labels(inp['terminal_labels'], 'terminal_labels', minimum=2)
        if (not isinstance(expected_terminal_labels, tuple) or
                labels != _labels(expected_terminal_labels, 'expected_terminal_labels', minimum=2)):
            _block('BLOCKED_STALE_SOURCE', 'Terminal labels/order disagree with independently expected native order')
        pair = _mapping(inp['proposed_pair'], frozenset({'island_a', 'island_b'}), 'proposed_pair')
        a, b = pair['island_a'], pair['island_b']
        if not isinstance(a, str) or not isinstance(b, str) or a == b or a not in labels or b not in labels:
            _block('BLOCKED_TOPOLOGY', 'Two distinct explicitly saved proposed islands must match terminal labels')
        policy = _mapping(inp['other_terminal_policy'],
                          frozenset({'fixed_zero', 'floating_zero_charge'}), 'other_terminal_policy')
        fixed = _labels(policy['fixed_zero'], 'fixed_zero')
        floating = _labels(policy['floating_zero_charge'], 'floating_zero_charge')
        other = set(labels) - {a, b}
        if (set(fixed) & set(floating) or set(fixed) | set(floating) != other or
                set(fixed) & {a, b} or set(floating) & {a, b}):
            _block('BLOCKED_TOPOLOGY', 'Every non-island terminal must appear in exactly one boundary class')
        ground = _mapping(inp['reference_ground'], frozenset({'status', 'native_group_ids'}),
                          'reference_ground')
        if ground['status'] not in ('UNREVIEWED', 'NATIVE_VERIFIED', 'REVIEWED'):
            _block('BLOCKED_TOPOLOGY', 'Unknown native reference-ground status')
        native_ground_groups = _groups(ground['native_group_ids'])
        if (not isinstance(expected_ground_group_ids, tuple) or
                native_ground_groups != _groups(expected_ground_group_ids)):
            _block('BLOCKED_STALE_SOURCE', 'Native reference-ground mapping mismatches expected groups')
        if configuration not in ('TWO_ISLAND_CHARGE_TRANSFER', 'GROUNDED_SINGLE_ISLAND'):
            _block('BLOCKED_TOPOLOGY', 'Explicit circuit charge convention required')
        declared_review = _review(inp, src, labels, native_ground_groups,
                                  reviewed_topology, configuration)
        if junction_capacitance_assumption != _JUNCTION_ASSUMPTION:
            _block('BLOCKED_JUNCTION_MODEL', 'Declare matrix-only exclusion of unverified junction shunt; no implicit shunt/JJ model')
        matrix, scale = _matrix(inp['maxwell_matrix_f'], len(labels))
        # Full matrix must be anchored; a 0-energy gauge mode must not be
        # treated as an electrostatic reference merely by fixing other nodes.
        _checked_spd(matrix, 'Full grounded Maxwell matrix')
        index = {name: i for i, name in enumerate(labels)}
        if configuration == 'TWO_ISLAND_CHARGE_TRANSFER':
            retained = (index[a], index[b])
            charge_vector = (1.0, -1.0)
            fixed_names = fixed
        else:
            retained = (index[a],)
            charge_vector = (1.0,)
            fixed_names = (*fixed, b)
        eff = _schur(matrix, retained, tuple(index[x] for x in floating))
        eff_factor = _checked_spd(eff, 'Reduced C_eff')
        solved = _solve(eff_factor, list(charge_vector))
        qsolve = math.fsum(u * w for u, w in zip(charge_vector, solved))
        if qsolve <= 0 or not math.isfinite(qsolve):
            _block('BLOCKED_NUMERICS', 'Nonpositive transfer-mode charging energy')
        # C is dimensionless after matrix normalization, so Cdiff = scale / qsolve.
        c_f = scale / qsolve
        preview: dict[str, object] = {
            'configuration': configuration,
            'retained_terminal_labels': [labels[i] for i in retained],
            'charge_vector_in_units_of_e': list(charge_vector),
            'fixed_zero': list(fixed_names),
            'floating_zero_charge': list(floating),
            'reference_ground_native_group_ids': list(native_ground_groups),
            'reference_ground_status': ground['status'],
            'review_declaration': declared_review,
            'junction_capacitance_assumption': junction_capacitance_assumption,
            'effective_matrix_f': [[entry * scale for entry in row] for row in eff],
            'effective_capacitance_f': c_f,
            'ec_over_h_hz_matrix_only': _ec_hz(c_f),
            'formula': ('Cdiff=1/(v^T Ceff^-1 v); EC/h=e^2/(2*h*Cdiff)'
                        if len(retained) == 2 else 'Csingle=Ceff[0,0]; EC/h=e^2/(2*h*Csingle)'),
            'constants_exact_si': {'e_coulomb': str(_E), 'h_joule_second': str(_H)},
            'uncertainty_status': 'NOT_ESTABLISHED',
            'scientific_claim': 'MATRIX_ONLY_NUMERICAL_SCREEN_NOT_A_TRANSMON_HAMILTONIAN',
        }
        return CapacitanceDecision(_SCREEN,
            'Conditional matrix-only numerical screen; independent topology, junction, source and Hamiltonian authorization absent',
            src, preview)
    except ReductionBlocked as exc:
        return CapacitanceDecision(exc.code, str(exc), trusted_source, None)
