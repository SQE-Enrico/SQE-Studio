"""Revision-bound native Palace electrostatic observations for the generic EDA Results UI.

Caller MUST first verify_manifest() for the exact saved revision and study.  These
observations are *not* an authorized electrostatic-to-Hamiltonian transfer.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, localcontext
import json
import math
from pathlib import Path
import re

from ..orchestration.artifacts import ArtifactInvalid, safe_file

SCHEMA = 'sqe.native-capacitance-screen.v1'
_MAX_BYTES = 128 * 1024
_H = Decimal('6.62607015e-34')
_E = Decimal('1.602176634e-19')
_PALACE_COL = re.compile(r'C\[i\]\[(\d+)\] \((F|fF)\)')
_LEGACY_COL = re.compile(r'C(\d+) \((F|fF)\)')


class NativeCapacitanceEvidenceError(ValueError):
    """Do not display matrix entries when their unit, tags or lineage are ambiguous."""


def parse_native_capacitance_table(path: Path, *, count: int, expected_unit: str | None = None):
    """Parse either documented Palace terminal-C.csv or the older SQE review fixture.

    Palace produces ``i,C[i][1] (F),...`` and scientific-notation row indices.
    The source *header*, not a caller-selected unit, determines the scaling.
    """
    if type(count) is not int or not 2 <= count <= 16 or expected_unit not in (None, 'F', 'fF'):
        raise NativeCapacitanceEvidenceError('Explicit 2-16 ordered terminals and supported units required')
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= _MAX_BYTES:
        raise NativeCapacitanceEvidenceError('Missing, linked, empty or oversized native terminal-C.csv')
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise NativeCapacitanceEvidenceError('Unreadable native capacitance CSV') from exc
    if len(rows) != count + 1 or any(len(r) != count + 1 for r in rows):
        raise NativeCapacitanceEvidenceError('Native matrix is incomplete or not square')
    head = [h.strip() for h in rows[0]]
    palace = head[0] == 'i'
    if not palace and head[0].lower() not in ('terminal', 'conductor'):
        raise NativeCapacitanceEvidenceError('Native conductor label convention unidentified')
    pattern = _PALACE_COL if palace else _LEGACY_COL
    matched = [pattern.fullmatch(h) for h in head[1:]]
    if any(m is None for m in matched):
        raise NativeCapacitanceEvidenceError('Native capacitance columns require explicit units')
    indices = [int(m.group(1)) for m in matched]
    units = {m.group(2) for m in matched}
    if indices != list(range(1, count + 1)) or len(units) != 1:
        raise NativeCapacitanceEvidenceError('Native column order/units are ambiguous')
    unit = units.pop()
    if expected_unit is not None and expected_unit != unit:
        raise NativeCapacitanceEvidenceError('Caller and native CSV capacitance units disagree')
    scale = Decimal('1e-15') if unit == 'fF' else Decimal(1)
    matrix = []
    for i, row in enumerate(rows[1:], 1):
        try:
            ordinal = Decimal(row[0].strip())
            values = [Decimal(v.strip()) * scale for v in row[1:]]
        except (InvalidOperation, ValueError) as exc:
            raise NativeCapacitanceEvidenceError('Nonnumeric native capacitance entry') from exc
        if (not ordinal.is_finite() or ordinal != i or
                any(not v.is_finite() or abs(v) > Decimal('1e-6') for v in values)):
            raise NativeCapacitanceEvidenceError('Nonfinite, implausible or reordered native capacitance values')
        matrix.append(values)
    return matrix, unit


def _object(folder: Path, name: str, declared: set[str]):
    if name not in declared:
        raise NativeCapacitanceEvidenceError('Native provenance artifact is not declared: ' + name)
    try:
        p = safe_file(folder, name)
        if not 0 < p.stat().st_size <= _MAX_BYTES:
            raise NativeCapacitanceEvidenceError('Native provenance file size is unsupported')
        obj = json.loads(p.read_text(encoding='utf-8'))
    except (ArtifactInvalid, UnicodeError, ValueError, OSError) as exc:
        raise NativeCapacitanceEvidenceError('Unusable native electrostatic provenance') from exc
    if type(obj) is not dict:
        raise NativeCapacitanceEvidenceError('Invalid native electrostatic provenance object')
    return obj


def native_capacitance_evidence(folder: Path, manifest: dict, project: dict) -> dict | None:
    """Screen native Maxwell terminal coefficients after authenticated SHA verification.

    CONDITIONAL E_C/h entries assume *all other modeled terminals held at zero
    voltage* and C_ii as the complete island capacitance.  In particular these
    are not floating-transmon or Josephson-capacitance reductions and may not
    be fed automatically to scqubits.
    """
    if manifest.get('engine') != 'sqdmetal_palace' or manifest.get('artifact_type') != 'palace.capacitance_matrix':
        return None
    if (manifest.get('kind') != 'capacitance' or project.get('revision_digest') != manifest.get('project_digest') or
            project.get('revision', project.get('head')) != manifest.get('revision_id')):
        raise NativeCapacitanceEvidenceError('Native capacitance requires an exact saved design revision')
    model = project.get('model')
    if (not isinstance(model, dict) or not isinstance(model.get('process'), dict) or
            model['process'].get('source') != 'reviewed'):
        raise NativeCapacitanceEvidenceError('Electrostatic material/stack source must be reviewed')
    studies = [s for s in model.get('studies', []) if s.get('id') == manifest.get('study_id') and
               s.get('engine') == 'sqdmetal_palace' and s.get('kind') == 'capacitance']
    if len(studies) != 1:
        raise NativeCapacitanceEvidenceError('Saved electrostatic study not found or ambiguous')
    inputs = studies[0].get('inputs')
    em = inputs.get('em') if isinstance(inputs, dict) else None
    if not isinstance(em, dict):
        raise NativeCapacitanceEvidenceError('Saved electrostatic study inputs are invalid')
    ports = em.get('ports')
    if (type(ports) is not list or not 2 <= len(ports) <= 16 or
            any(type(p) is not dict or p.get('kind') != 'conductor' or p.get('index') != i or
                not isinstance(p.get('component'), str) or not p['component'] or
                type(p.get('native_attributes')) is not list or not p['native_attributes']
                for i, p in enumerate(ports, 1)) or
            len({p['component'] for p in ports}) != len(ports)):
        raise NativeCapacitanceEvidenceError('Reviewed conductor order/components are ambiguous')
    declared = {a['name'] for a in manifest.get('artifacts', [])}
    required = ('sqe_em/outputFiles/terminal-C.csv', 'sqe_em/sqe_em.json',
                'sqe_em/sqe_em.msh', 'sqe_em/palace-native.log', 'a03-native-artifacts.json')
    if not all(x in declared for x in required):
        raise NativeCapacitanceEvidenceError('Incomplete native Palace electrostatic artifacts')
    sidecar = _object(folder, 'a03-native-artifacts.json', declared)
    deck = _object(folder, 'sqe_em/sqe_em.json', declared)
    completion = sidecar.get('native_completion')
    versions = sidecar.get('versions')
    port_convention = sidecar.get('port_convention')
    if (sidecar.get('schema') != 'sqe.a03.native-artifacts.v1' or sidecar.get('execution') != 'solve' or
            not isinstance(completion, dict) or type(completion.get('exit_code')) is not int or
            completion['exit_code'] != 0 or not isinstance(versions, dict) or
            not versions.get('palace') or not isinstance(port_convention, dict) or
            port_convention.get('index_base') != 1 or
            port_convention.get('ordering') != 'reviewed SQDMetal creation order' or
            port_convention.get('ports') != ports):
        raise NativeCapacitanceEvidenceError('Native Palace completion/terminal lineage not demonstrated')
    boundaries = deck.get('Boundaries')
    if not isinstance(boundaries, dict) or not isinstance(deck.get('Problem'), dict):
        raise NativeCapacitanceEvidenceError('Invalid native Palace electrostatic deck')
    terminals = boundaries.get('Terminal')
    ground = boundaries.get('Ground')
    if (deck.get('Problem', {}).get('Type') != 'Electrostatic' or
            not isinstance(terminals, list) or len(terminals) != len(ports) or
            not isinstance(ground, dict) or type(ground.get('Attributes')) is not list or
            not ground['Attributes']):
        raise NativeCapacitanceEvidenceError('Native deck lacks explicit grounded electrostatic terminals')
    used = set()
    for attributes in [ground['Attributes'], *(p['native_attributes'] for p in ports)]:
        if (any(type(a) is not int or not 1 <= a <= 65535 for a in attributes) or
                len(set(attributes)) != len(attributes) or not used.isdisjoint(attributes)):
            raise NativeCapacitanceEvidenceError('Native terminal/ground physical groups overlap')
        used.update(attributes)
    for i, (port, terminal) in enumerate(zip(ports, terminals), 1):
        if type(terminal) is not dict or terminal.get('Index') != i or terminal.get('Attributes') != port['native_attributes']:
            raise NativeCapacitanceEvidenceError('Native deck terminal index does not match reviewed order')
    try:
        path = safe_file(folder, required[0])
        matrix, unit = parse_native_capacitance_table(path, count=len(ports))
    except ArtifactInvalid as exc:
        raise NativeCapacitanceEvidenceError('Unsafe native capacitance matrix path') from exc
    maximum = max(abs(v) for row in matrix for v in row)
    if maximum <= 0:
        raise NativeCapacitanceEvidenceError('Empty/zero native electrostatic matrix')
    skew = max(abs(matrix[i][j] - matrix[j][i]) for i in range(len(matrix)) for j in range(len(matrix)))
    relative_skew = skew / maximum
    tolerance = Decimal('0.001')
    if relative_skew > tolerance:
        raise NativeCapacitanceEvidenceError('Maxwell symmetry/reciprocity residual too large')
    for i, row in enumerate(matrix):
        if (row[i] <= tolerance * maximum or
                any(v > tolerance * maximum for j, v in enumerate(row) if i != j) or
                row[i] + tolerance * maximum < sum((-min(Decimal(0), v) for j, v in enumerate(row) if i != j), Decimal(0))):
            raise NativeCapacitanceEvidenceError('Maxwell sign or diagonal dominance screening failed')
    with localcontext() as ctx:
        ctx.prec = 50
        # This is a bounded, conditional numerical indicator, NOT active EC.
        indicators = [float(_E * _E / (2 * _H * row[i]) / Decimal('1e9')) for i, row in enumerate(matrix)]
    if any(not math.isfinite(x) or x <= 0 for x in indicators):
        raise NativeCapacitanceEvidenceError('Invalid conditional charging-energy indicator')
    native_sha = next(a['sha256'] for a in manifest['artifacts'] if a['name'] == required[0])
    return {'schema': SCHEMA, 'status': 'NATIVE_MAXWELL_MATRIX_SCREENED',
            'revision_id': manifest['revision_id'], 'project_digest': manifest['project_digest'],
            'native_matrix_sha256': native_sha, 'native_source_unit': unit,
            'conductor_order': [p['component'] for p in ports],
            'terminal_surface_tags': [p['native_attributes'] for p in ports],
            'reference_ground_surface_tags': list(ground['Attributes']),
            'capacitance_matrix_F': [[float(v) for v in row] for row in matrix],
            'symmetry_relative_residual': float(relative_skew),
            'conditional_island_indicators': [
                {'terminal_index': i, 'component': p['component'],
                 'C_ii_F': float(matrix[i - 1][i - 1]), 'conditional_EC_over_h_GHz': indicators[i - 1]}
                for i, p in enumerate(ports, 1)],
            'conditional_assumption': 'ALL_OTHER_MODELED_TERMINALS_AT_ZERO_VOLTAGE_CII_ONLY',
            'required_reviews': ['physical_conductor_to_layout_registration',
                                 'grounded_or_floating_node_reduction', 'junction_and_parasitic_capacitance',
                                 'electrostatic_mesh_convergence', 'independent_quantization_review'],
            'scqubits_EC_transfer': 'BLOCKED_REQUIRES_REVIEWED_CAPACITANCE_REDUCTION',
            'cross_engine_model': 'NOT_ESTABLISHED',
            'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
