"""Fail-closed native Palace terminal/ground/Gmsh provenance for M1.

This is an *unreviewed* circuit topology candidate, never a transmon approval.
The caller must authorize the saved project/run and selection before invoking us;
we also independently reverify the complete local worker artifact manifest.
No solver, Gmsh import, circuit reduction or scqubits call is made here.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import math
from pathlib import Path

from ..contracts import digest
from ..orchestration.artifacts import ArtifactInvalid, safe_file, verify_manifest
from ..adapters.sqdmetal_palace_adapter import EngineBlocked, preflight
from .native_capacitance_evidence import (
    NativeCapacitanceEvidenceError, native_capacitance_evidence,
)

SCHEMA = 'sqe.capacitance-topology.v1'
MAX_MESH_SCAN_BYTES = 32 * 1024 * 1024
MAX_MESH_ELEMENTS = 250_000
# Gmsh documented linear/quadratic triangles and tetrahedra; first 3/4
# vertices are sufficient for a strictly limited physical-ID presence screen.
_ELEMENT_VERTICES = {15: (1, 1), 1: (2, 2), 8: (3, 2),
                     2: (3, 3), 9: (6, 3), 21: (10, 3),
                     4: (4, 4), 11: (10, 4), 29: (20, 4)}
_REQUIRED = ('sqe_em/outputFiles/terminal-C.csv', 'sqe_em/sqe_em.json',
             'sqe_em/sqe_em.msh', 'sqe_em/palace-native.log',
             'a03-native-artifacts.json')


class CapacitanceTopologyBlocked(ValueError):
    """Proof or explicit saved conductor classification is incomplete."""


def _require(condition: bool, reason: str):
    if not condition:
        raise CapacitanceTopologyBlocked(reason)


def _groups(value, label):
    _require(type(value) is list and bool(value) and len(value) <= 128 and
             all(type(x) is int and 0 < x <= 65535 for x in value) and
             len(set(value)) == len(value), label + ' lacks unique native physical IDs')
    return set(value)


def _read_mesh_groups(path: Path) -> tuple[set[int], set[int], str, dict[int, int]]:
    """Bounded Gmsh ASCII v2.2/v4.1 *physical-element* presence, not CAD registration.

    v4 entity blocks map entity tags to physical groups through $Entities,
    unlike v2 where an element's first tag directly identifies its group.
    Binary/unknown/high-order types are blocked rather than guessed.
    """
    _require(not path.is_symlink() and path.is_file() and
             0 < path.stat().st_size <= MAX_MESH_SCAN_BYTES,
             'Gmsh mesh missing, linked or beyond bounded ASCII inspection budget')
    raw = path.read_bytes()
    _require(b'\x00' not in raw, 'Gmsh binary mesh requires an independently qualified native reader')
    try:
        lines = raw.decode('utf-8').splitlines()
    except UnicodeError as exc:
        raise CapacitanceTopologyBlocked('Unrecognized Gmsh mesh encoding') from exc
    _require(len(lines) <= 1_000_000 and lines[:1] == ['$MeshFormat'] and
             '$EndMeshFormat' in lines, 'Missing Gmsh mesh format')
    fmt = lines[1].split()
    _require(len(fmt) == 3 and fmt[1] == '0' and fmt[0] in ('2.2', '4.1'),
             'Only explicitly parsed Gmsh 2.2/4.1 ASCII supported')
    _require(lines[2] == '$EndMeshFormat', 'Bad Gmsh MeshFormat framing')

    def section(name):
        marker, end = '$' + name, '$End' + name
        _require(lines.count(marker) == 1 and lines.count(end) == 1,
                 'Gmsh ' + name + ' section missing or duplicated')
        begin, finish = lines.index(marker), lines.index(end)
        _require(finish > begin + 1, 'Empty Gmsh ' + name + ' section')
        return lines[begin + 1:finish]

    entity_groups = {}
    if fmt[0] == '4.1':
        rows = section('Entities')
        try:
            counts = [int(x) for x in rows[0].split()]
            _require(len(counts) == 4 and all(0 <= n <= MAX_MESH_ELEMENTS for n in counts)
                     and len(rows) == 1 + sum(counts), 'Gmsh entity count mismatch')
            at = 1
            for dim, count in enumerate(counts):
                for row in rows[at:at + count]:
                    items = row.split()
                    offset = 4 if dim == 0 else 7
                    _require(len(items) > offset, 'Short Gmsh entity')
                    tag, nphys = int(items[0]), int(items[offset])
                    _require(tag > 0 and nphys >= 0 and len(items) >= offset + 1 + nphys,
                             'Invalid Gmsh entity physical-group declaration')
                    physical = [int(x) for x in items[offset + 1:offset + 1 + nphys]]
                    _require(all(x > 0 for x in physical) and len(set(physical)) == len(physical),
                             'Invalid or duplicate Gmsh physical IDs')
                    _require((dim, tag) not in entity_groups, 'Duplicate Gmsh entity')
                    entity_groups[dim, tag] = tuple(physical)
                at += count
        except (ValueError, IndexError) as exc:
            raise CapacitanceTopologyBlocked('Invalid Gmsh Entities block') from exc

    # Native Gmsh can include optional Nodes in v2/v4. Require it to avoid
    # accepting an invented list of element tags without any geometry nodes.
    rows = section('Nodes')
    nodes: dict[int, tuple[float, float, float]] = {}
    try:
        if fmt[0] == '2.2':
            count = int(rows[0]); _require(4 <= count <= MAX_MESH_ELEMENTS and len(rows) == count + 1,
                                           'Invalid Gmsh node count')
            for row in rows[1:]:
                values = row.split()
                _require(len(values) == 4, 'Invalid Gmsh node record')
                index = int(values[0])
                _require(index > 0 and index not in nodes and
                         all(math.isfinite(float(x)) for x in values[1:]), 'Invalid Gmsh node')
                nodes[index] = tuple(float(x) for x in values[1:])
        else:
            # Gmsh v4 block node tags may span multiple lines. Coordinates
            # may have parametric dimensions when the block declares them.
            tokens = iter(' '.join(rows).split())
            blocks, total, _, _ = (int(next(tokens)) for _ in range(4))
            _require(0 < blocks <= MAX_MESH_ELEMENTS and 4 <= total <= MAX_MESH_ELEMENTS,
                     'Invalid Gmsh v4 node budget')
            for _ in range(blocks):
                dim, entity, parametric, count = (int(next(tokens)) for _ in range(4))
                _require(0 <= dim <= 3 and entity > 0 and parametric in (0, 1)
                         and 0 < count <= total, 'Invalid Gmsh node block')
                tags = [int(next(tokens)) for _ in range(count)]
                for tag in tags:
                    _require(tag > 0 and tag not in nodes, 'Duplicate Gmsh node')
                for tag in tags:
                    coords = [float(next(tokens)) for _ in range(3 + (dim if parametric else 0))]
                    _require(all(math.isfinite(x) for x in coords), 'Nonfinite Gmsh coordinates')
                    nodes[tag] = tuple(coords[:3])
            _require(len(nodes) == total, 'Incomplete Gmsh v4 nodes')
            _require(next(tokens, None) is None, 'Extra Gmsh v4 nodes')
    except (ValueError, IndexError, StopIteration, OverflowError) as exc:
        raise CapacitanceTopologyBlocked('Invalid Gmsh Nodes section') from exc

    rows = section('Elements')
    seen_elements = set()
    surface_counts, volume_counts = Counter(), Counter()

    def record(eid, element_type, ids, physical):
        _require(eid > 0 and eid not in seen_elements, 'Duplicate/invalid Gmsh element')
        seen_elements.add(eid)
        _require(element_type in _ELEMENT_VERTICES,
                 'Unsupported Gmsh element type in geometry provenance')
        expected, vertex_count = _ELEMENT_VERTICES[element_type]
        _require(len(ids) == expected and len(set(ids)) == expected and all(n in nodes for n in ids),
                 'Gmsh elements lack complete physical mesh nodes')
        # 0D/1D auxiliary mesh entities do not enter electrostatic physical
        # conductor/ground groups, though their node references are checked.
        if vertex_count < 3:
            return
        _require(len(physical) == 1 and physical[0] > 0,
                 'Gmsh element has missing/ambiguous physical group')
        def vec(a, b):
            return tuple(nodes[b][k] - nodes[a][k] for k in range(3))
        a, b = vec(ids[0], ids[1]), vec(ids[0], ids[2])
        cross = (a[1] * b[2] - a[2] * b[1],
                 a[2] * b[0] - a[0] * b[2],
                 a[0] * b[1] - a[1] * b[0])
        _require(sum(x * x for x in cross) > 1e-40,
                 'Degenerate Gmsh physical surface')
        if vertex_count == 4:
            c = vec(ids[0], ids[3])
            _require(abs(sum(c[k] * cross[k] for k in range(3))) > 1e-30,
                     'Degenerate Gmsh material tetrahedron')
        if vertex_count == 3:
            surface_counts[physical[0]] += 1
        else:
            volume_counts[physical[0]] += 1

    try:
        if fmt[0] == '2.2':
            count = int(rows[0])
            _require(0 < count <= MAX_MESH_ELEMENTS and len(rows) == count + 1,
                     'Gmsh v2 element count mismatch')
            for row in rows[1:]:
                values = [int(x) for x in row.split()]
                _require(len(values) >= 3 and 0 <= values[2] <= 32 and
                         len(values) >= 3 + values[2], 'Invalid Gmsh v2 element tags')
                record(values[0], values[1], values[3 + values[2]:],
                       [values[3]] if values[2] else [])
        else:
            header = [int(x) for x in rows[0].split()]
            _require(len(header) == 4, 'Bad Gmsh v4 element header')
            blocks, count = header[:2]
            _require(0 < blocks <= MAX_MESH_ELEMENTS and 0 < count <= MAX_MESH_ELEMENTS,
                     'Gmsh v4 element budget exceeded')
            at = 1
            for _ in range(blocks):
                part = [int(x) for x in rows[at].split()]; at += 1
                _require(len(part) == 4, 'Invalid Gmsh v4 element block')
                dim, entity, element_type, n = part
                _require(dim in (0, 1, 2, 3) and entity > 0 and 0 < n <= count and
                         (dim, entity) in entity_groups, 'Unknown Gmsh v4 physical entity')
                physical = entity_groups[dim, entity]
                for row in rows[at:at + n]:
                    values = [int(x) for x in row.split()]
                    expected_dim = (0 if element_type == 15 else
                                    1 if element_type in (1, 8) else
                                    2 if element_type in (2, 9, 21) else
                                    3 if element_type in (4, 11, 29) else -1)
                    _require(bool(values) and dim == expected_dim,
                             'Gmsh element dimension mismatch')
                    record(values[0], element_type, values[1:], physical)
                at += n
            _require(at == len(rows) and len(seen_elements) == count,
                     'Gmsh v4 elements incomplete or unexpected')
    except (ValueError, IndexError) as exc:
        raise CapacitanceTopologyBlocked('Invalid Gmsh Elements section') from exc
    _require(bool(surface_counts) and bool(volume_counts),
             'Gmsh lacks tagged 2D boundaries or 3D volumes')
    _require(sha256(path.read_bytes()).digest() == sha256(raw).digest(),
             'Gmsh mesh changed during physical tag inspection')
    return set(surface_counts), set(volume_counts), fmt[0], dict(surface_counts)


def _spd(matrix):
    """Reject singular/indefinite Maxwell matrices; physical approval remains separate."""
    with localcontext() as ctx:
        ctx.prec = 50
        n = len(matrix)
        maxdiag = max(matrix[i][i] for i in range(n))
        _require(maxdiag > 0, 'Invalid Maxwell matrix scale')
        a = [[(matrix[i][j] + matrix[j][i]) / 2 for j in range(n)] for i in range(n)]
        lower = [[Decimal(0)] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1):
                d = a[i][j] - sum((lower[i][k] * lower[j][k] for k in range(j)), Decimal(0))
                if i == j:
                    _require(d > maxdiag * Decimal('1e-12'),
                             'Maxwell matrix not sufficiently positive definite')
                    lower[i][j] = d.sqrt()
                else:
                    lower[i][j] = d / lower[j][j]


def build_native_capacitance_topology(folder: Path, manifest: dict, project: dict, *,
                                      saved_selection: dict) -> dict:
    """Return ONLY frozen v1 data with an explicitly supplied saved selection.

    The host must authenticate the saved selection and authorized completed run;
    the returned status is always UNREVIEWED, even for a real native solve.
    A99 must not treat this function as a review, geometry registration, or
    permission to transfer capacitance into a Hamiltonian.
    """
    folder = Path(folder)
    _require(type(manifest) is dict and type(project) is dict and
             type(saved_selection) is dict, 'Explicit native provenance and saved selection required')
    revision = project.get('revision', project.get('head'))
    model = project.get('model')
    _require(type(model) is dict and isinstance(revision, str) and
             project.get('revision_digest') == digest(model),
             'Saved project revision/digest do not match the immutable model')
    _require(manifest.get('revision_id') == revision and
             manifest.get('project_digest') == project['revision_digest'] and
             manifest.get('kind') == 'capacitance' and
             manifest.get('artifact_type') == 'palace.capacitance_matrix',
             'Native artifact is not this saved electrostatic revision')
    try:
        ref = verify_manifest(folder, revision_id=revision,
                              project_digest=project['revision_digest'],
                              study_id=manifest.get('study_id'), engine='sqdmetal_palace')
        native_manifest = json.loads(safe_file(folder, 'RESULT_MANIFEST.json').read_bytes())
        _require(manifest == native_manifest and
                 ref.artifact_type == 'palace.capacitance_matrix',
                 'Caller manifest differs from independently verified native manifest')
        rows = [s for s in model.get('studies', []) if type(s) is dict and
                s.get('id') == manifest['study_id'] and s.get('engine') == 'sqdmetal_palace'
                and s.get('kind') == 'capacitance']
        _require(len(rows) == 1, 'Missing/ambiguous saved electrostatic study')
        try:
            em = preflight(rows[0], model)
        except EngineBlocked as exc:
            raise CapacitanceTopologyBlocked('Saved process, terminal or boundary inputs fail native preflight') from exc
        _require(em['execution'] == 'solve' and em['ground']['verified'] is True and
                 em['boundaries']['farfield'] == 'ground',
                 'Saved study does not prove a solved electrostatic ground')
        _require(all(name in {x['name'] for x in manifest['artifacts']} for name in _REQUIRED),
                 'Required native electrostatic files missing')
        source = native_capacitance_evidence(folder, manifest, project)
        _require(type(source) is dict, 'Native capacitance source not screened')
        deck = json.loads(safe_file(folder, 'sqe_em/sqe_em.json').read_bytes())
        _require(deck.get('Problem', {}).get('Type') == 'Electrostatic' and
                 deck.get('Problem', {}).get('Output') == 'outputFiles' and
                 deck.get('Model', {}).get('L0') == 1e-3 and
                 deck['Model'].get('Mesh') == 'sqe_em.msh' and
                 deck.get('Solver', {}).get('Order') == em['solver']['order'],
                 'Palace native deck mesh units/order/output incompatible with saved study')
        ground = _groups(deck['Boundaries']['Ground']['Attributes'], 'Reference ground')
        _require(len(deck['Boundaries']['Terminal']) == len(em['ports']),
                 'Native terminal count inconsistent with saved study')
        names = [p['component'] for p in em['ports']]
        _require(len(set(names)) == len(names), 'Duplicate native conductor identity')
        used = set(ground)
        for i, (p, t) in enumerate(zip(em['ports'], deck['Boundaries']['Terminal']), 1):
            tags = _groups(p['native_attributes'], 'Saved terminal')
            _require(type(t) is dict and type(t.get('Index')) is int and t['Index'] == i and
                     t.get('Attributes') == p['native_attributes'] and used.isdisjoint(tags),
                     'Native conductor order or electrode physical IDs are swapped/duplicated')
            used.update(tags)
        surface, volume, format_version, surface_counts = _read_mesh_groups(
            safe_file(folder, 'sqe_em/sqe_em.msh'))
        _require(used <= surface and all(surface_counts[t] > 0 for t in used),
                 'Native Gmsh mesh lacks mapped terminal or grounded surface elements')
        material = deck.get('Domains', {}).get('Materials')
        _require(type(material) is list and len(material) == 2,
                 'Missing explicit Palace material volume assignments')
        volume_sets = [_groups(v.get('Attributes'), 'Palace material') for v in material]
        _require(not (volume_sets[0] & volume_sets[1]) and
                 volume_sets[0] | volume_sets[1] == volume,
                 'Native Gmsh volume/material physical tags mismatch')
        expected = [model['process']['stack'][2], model['process']['stack'][0]]
        for entry, material_model in zip(material, expected):
            _require(type(entry) is dict and type(entry.get('Permittivity')) in (int, float) and
                     math.isclose(entry['Permittivity'], material_model['relative_permittivity'], rel_tol=1e-9) and
                     math.isclose(entry.get('LossTan', 0), material_model['loss_tangent'], abs_tol=1e-12),
                     'Native electrostatic material properties disagree with saved process')
        # Selection MUST come from an authenticated saved design record supplied
        # by the caller. This function can verify exact revision/identity/classes,
        # but cannot independently prove a store write or expert intent.
        _require(set(saved_selection) == {'revision_id', 'revision_digest', 'study_id',
                                           'island_a', 'island_b', 'other_terminal_policy'},
                 'Incomplete/unknown saved selection fields')
        _require(saved_selection['revision_id'] == revision and
                 saved_selection['revision_digest'] == project['revision_digest'] and
                 saved_selection['study_id'] == manifest['study_id'],
                 'Stale saved conductor selection')
        pair = [saved_selection['island_a'], saved_selection['island_b']]
        _require(all(type(s) is str and s in names for s in pair) and pair[0] != pair[1],
                 'Proposed islands must be distinct explicitly mapped conductors')
        policy = saved_selection['other_terminal_policy']
        _require(type(policy) is dict and set(policy) == {'fixed_zero', 'floating_zero_charge'} and
                 all(type(policy[k]) is list and all(type(t) is str for t in policy[k])
                     for k in ('fixed_zero', 'floating_zero_charge')),
                 'Incomplete fixed/floating conductor policy')
        rest = policy['fixed_zero'] + policy['floating_zero_charge']
        _require(len(rest) == len(set(rest)) and set(rest) == set(names) - set(pair),
                 'Unknown, duplicated or unclassified remaining conductors')
        # Ground is NOT an ordinary terminal in the Maxwell matrix.
        _spd([[Decimal(str(x)) for x in row] for row in source['capacitance_matrix_F']])
        _require(source['conductor_order'] == names and
                 source['native_source_unit'] in ('F', 'fF'),
                 'Native matrix terminal index order/units are unproven')
        # One more full rehash closes the file-mutated-during-inspection gap.
        _require(verify_manifest(folder, revision_id=revision,
                                 project_digest=project['revision_digest'],
                                 study_id=manifest['study_id'], engine='sqdmetal_palace').manifest_sha256 ==
                 ref.manifest_sha256, 'Native source changed while verifying topology')
    except (ArtifactInvalid, NativeCapacitanceEvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, CapacitanceTopologyBlocked):
            raise
        raise CapacitanceTopologyBlocked('Native topology provenance incomplete or invalid: ' +
                                         type(exc).__name__) from exc

    entries = {e['name']: e['sha256'] for e in manifest['artifacts']}
    return {
        'schema': SCHEMA,
        'scientific_status': 'UNREVIEWED_TOPOLOGY',
        'source': {'revision_digest': project['revision_digest'],
                   'study_id': manifest['study_id'],
                   'manifest_sha256': ref.manifest_sha256,
                   'terminal_csv_sha256': entries[_REQUIRED[0]],
                   'deck_sha256': entries[_REQUIRED[1]],
                   'mesh_sha256': entries[_REQUIRED[2]]},
        'terminal_labels': names,
        'maxwell_matrix_f': source['capacitance_matrix_F'],
        'reference_ground': {'status': 'UNREVIEWED', 'native_group_ids': sorted(ground)},
        'proposed_pair': {'island_a': pair[0], 'island_b': pair[1]},
        'other_terminal_policy': {'fixed_zero': list(policy['fixed_zero']),
                                  'floating_zero_charge': list(policy['floating_zero_charge'])},
        'review': {'status': 'NOT_APPROVED', 'record_sha256': None},
    }


def inspect_native_capacitance_mapping(folder: Path, manifest: dict, project: dict, *,
                                       saved_selection: dict) -> dict:
    """Separate evidence for A99; does NOT add fields to A12's frozen v1 input.

    Preserves exact 1-based Palace index -> saved component -> Gmsh physical
    group correspondence. Gmsh tag *presence* alone cannot prove that SQDMetal
    really meshed the intended QDesign component or PEC conductor surfaces.
    """
    candidate = build_native_capacitance_topology(
        folder, manifest, project, saved_selection=saved_selection)
    study_id = candidate['source']['study_id']
    rows = [s for s in project['model']['studies'] if s.get('id') == study_id]
    _require(len(rows) == 1, 'Ambiguous saved study for mapping evidence')
    ports = rows[0]['inputs']['em']['ports']
    return {
        'schema': 'sqe.native-capacitance-mapping.v1',
        'status': 'VERIFIED_NATIVE_TAG_PRESENCE_ONLY_NOT_PHYSICAL_REGISTRATION',
        'source': dict(candidate['source']),
        'ordered_conductors': [
            {'terminal_index': i, 'component': port['component'],
             'native_group_ids': list(port['native_attributes'])}
            for i, port in enumerate(ports, 1)],
        'reference_ground_group_ids': candidate['reference_ground']['native_group_ids'],
        'native_ground_bc': 'Palace Electrostatic Ground',
        'geometry_registration': 'BLOCKED_NO_INDEPENDENT_QDESIGN_TO_GMSH_FACE_REGISTRATION',
        'scientific_status': 'UNREVIEWED_TOPOLOGY',
        'scqubits_EC_transfer': 'BLOCKED_NOT_REVIEWED',
        'fabrication': 'HOLD',
    }
