"""Explicit native QGeometry identities for an isolated two-pad TransmonPocket.

This validates declared pairs with upstream Shapely predicates. It never searches
for a closest geometry, infers pads from component names, or computes capacitance.
The original SQDMetal deck is retained before grounding its reference conductor.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from ..contracts import digest
from ..adapters.base import EngineBlocked
from ..orchestration.artifacts import safe_file

SCHEMA = 'sqe.native-capacitance-identity.v1'
IDENTITY_FILE = 'sqe_em/capacitance-identity.json'
ORIGIN_FILE = 'sqe_em/capacitance-origin.json'
TOLERANCE_MM = 1e-12
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z', re.ASCII)
_PORT_KEYS = {'index', 'kind', 'component', 'qgeometry', 'label',
              'native_attributes', 'native_terminal_index'}
_METHOD = 'DECLARED_NATIVE_INDICES_AND_SHAPELY_EQUALS_EXACT_NO_GEOMETRY_SEARCH'
_RECORD_KEYS = {'schema', 'status', 'method', 'tolerance_mm', 'layout_sha256',
                'process_sha256', 'mesh_sha256', 'origin_deck_sha256', 'deck_sha256',
                'ordered_conductors', 'ground', 'scientific_qualification', 'fabrication'}


def named_terminals(em):
    ports = em.get('ports') if type(em) is dict else None
    return type(ports) is list and any(type(port) is dict and 'qgeometry' in port for port in ports)


def terminal_label(port):
    return port.get('label', port['component'])


def _require(condition, message):
    if not condition:
        raise EngineBlocked('Native capacitance identity: ' + message)


def validate_named_terminals(em, layout):
    """Keep this first native case bounded to one isolated TransmonPocket."""
    ports, ground = em['ports'], em['ground']
    _require(len(ports) == 2 and all(set(port) == _PORT_KEYS for port in ports),
             'exactly two explicitly named pad terminals required')
    components = layout['components']
    _require(len(components) == 1 and components[0].get('kind') == 'TransmonPocket'
             and not components[0].get('connection_pads'),
             'named terminals currently support one isolated TransmonPocket')
    _require({port['component'] for port in ports} == {components[0]['name']}
             and {port['qgeometry'] for port in ports} == {'pad_top', 'pad_bot'},
             'declare the native pad_top and pad_bot QGeometry rows')
    labels = [terminal_label(port) for port in ports]
    _require(all(type(label) is str and _NAME.fullmatch(label) for label in labels)
             and len(set(labels)) == 2, 'distinct ASCII conductor labels required')
    selectors = [ground, *ports]
    _require(all(type(item.get('native_terminal_index')) is int
                 and 1 <= item['native_terminal_index'] <= 3 for item in selectors)
             and {item['native_terminal_index'] for item in selectors} == {1, 2, 3},
             'classify each original SQDMetal terminal once, including ground')
    used = set()
    for item in selectors:
        attrs = item.get('native_attributes')
        _require(type(attrs) is list and bool(attrs)
                 and all(type(tag) is int and 1 <= tag <= 65535 for tag in attrs)
                 and len(set(attrs)) == len(attrs) and used.isdisjoint(attrs),
                 'ground and pad physical groups must be explicit and disjoint')
        used.update(attrs)


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _same_geometry(native, declared):
    _require(native.is_valid and declared.is_valid and not native.is_empty and not declared.is_empty,
             'empty or invalid native geometry')
    _require(native.normalize().equals_exact(declared.normalize(), TOLERANCE_MM),
             'declared QGeometry differs from the selected native conductor')
    return {'native_geometry_sha256': sha256(native.wkb).hexdigest(),
            'declared_geometry_sha256': sha256(declared.wkb).hexdigest()}


def bind_native_terminals(sim, design, model, em, output, gmsh_api):
    """Bind declared native indices, then place the verified chip conductor at 0 V."""
    validate_named_terminals(em, model['layout'])
    output = Path(output)
    deck_file = output / 'sqe_em/sqe_em.json'
    raw = deck_file.read_bytes()
    origin = json.loads(raw)
    _require(origin['Problem']['Type'] == 'Electrostatic' and origin['Model']['L0'] == 1e-3,
             'unsupported native deck type or length units')
    original = origin['Boundaries']['Terminal']
    shapes = sim._cur_cap_terminals
    _require(len(original) == len(shapes) == 3
             and [item['Index'] for item in original] == [1, 2, 3],
             'unexpected upstream conductor count/order')
    rows = list(design.qgeometry.tables['poly'].iterrows())
    ordered = []
    for port in em['ports']:
        component = design.components[port['component']]
        selected = [row for _, row in rows if row['component'] == component.id
                    and row['name'] == port['qgeometry'] and not row['subtract']
                    and int(row['layer']) == em['ground']['layer']]
        _require(len(selected) == 1, 'named QGeometry is missing, duplicated, or on another layer')
        index = port['native_terminal_index']
        _require(original[index-1]['Attributes'] == port['native_attributes'],
                 'declared physical groups differ from the upstream terminal')
        geometry = _same_geometry(shapes[index-1], selected[0]['geometry'])
        for tag in port['native_attributes']:
            _require(gmsh_api.model.getPhysicalName(2, tag) == f'metal_{index-1}',
                     'native physical-group name differs from upstream conductor identity')
        ordered.append({**deepcopy(port), **geometry})
    options = sim.user_options
    reference, _ = sim._geom_processor.process_layers([], sim._ground_plane,
        unit_conv=1e-3, fuse_threshold=options['fuse_threshold'],
        threshold=options['threshold'], fillet_resolution=options['fillet_resolution'],
        simplify_edge_min_angle_deg=options['simplify_edge_min_angle_deg'])
    ground = em['ground']
    ground_index = ground['native_terminal_index']
    _require(len(reference) == 1 and original[ground_index-1]['Attributes'] == ground['native_attributes'],
             'reference conductor differs from the upstream ground plane')
    ground_geometry = _same_geometry(shapes[ground_index-1], reference[0])
    for tag in ground['native_attributes']:
        _require(gmsh_api.model.getPhysicalName(2, tag) == f'metal_{ground_index-1}',
                 'ground physical-group identity differs from the native mesh')
    final = deepcopy(origin)
    farfield = origin['Boundaries']['Ground']['Attributes']
    _require(set(farfield).isdisjoint(tag for port in em['ports'] for tag in port['native_attributes']),
             'farfield and pad groups overlap')
    final['Boundaries']['Ground']['Attributes'] = sorted(set(farfield + ground['native_attributes']))
    final['Boundaries']['Terminal'] = [
        {'Index': port['index'], 'Attributes': list(port['native_attributes'])} for port in em['ports']]
    final['Boundaries'].setdefault('Postprocessing', {})['SurfaceFlux'] = [
        {'Index': port['index'], 'Attributes': list(port['native_attributes']), 'Type': 'Electric'}
        for port in em['ports']]
    final['Solver']['Electrostatic']['Save'] = len(em['ports'])
    origin_file = output / ORIGIN_FILE
    identity_file = output / IDENTITY_FILE
    _require(not origin_file.exists() and not identity_file.exists(), 'identity files already exist')
    origin_file.write_bytes(raw)
    deck_file.write_text(json.dumps(final, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    identity = {'schema': SCHEMA, 'status': 'NATIVE_QGEOMETRY_IDENTITIES_CHECKED',
        'method': _METHOD,
        'tolerance_mm': TOLERANCE_MM, 'layout_sha256': digest(model['layout']),
        'process_sha256': digest(model['process']), 'mesh_sha256': _hash(output / 'sqe_em/sqe_em.msh'),
        'origin_deck_sha256': _hash(origin_file), 'deck_sha256': _hash(deck_file),
        'ordered_conductors': ordered,
        'ground': {**deepcopy(ground), **ground_geometry,
                   'final_ground_attributes': final['Boundaries']['Ground']['Attributes']},
        'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    identity_file.write_text(json.dumps(identity, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return identity


def verify_saved_identity(folder, manifest, model, em):
    """Rehash the original deck and exact saved layout/process before readback."""
    if not named_terminals(em):
        return None
    validate_named_terminals(em, model['layout'])
    declared = {item['name'] for item in manifest['artifacts']}
    _require({IDENTITY_FILE, ORIGIN_FILE} <= declared, 'native identity artifacts are missing')
    identity_path = safe_file(folder, IDENTITY_FILE)
    _require(identity_path.stat().st_size <= 128 * 1024, 'identity record exceeds size limit')
    identity = json.loads(identity_path.read_bytes())
    _require(type(identity) is dict and set(identity) == _RECORD_KEYS, 'invalid identity record fields')
    _require(identity.get('schema') == SCHEMA and identity.get('method') == _METHOD
             and identity.get('tolerance_mm') == TOLERANCE_MM
             and identity.get('status') == 'NATIVE_QGEOMETRY_IDENTITIES_CHECKED'
             and identity.get('scientific_qualification') == 'NOT_ESTABLISHED'
             and identity.get('fabrication') == 'HOLD'
             and identity.get('layout_sha256') == digest(model['layout'])
             and identity.get('process_sha256') == digest(model['process']),
             'saved geometry identity, process or scientific status changed')
    for key, name in (('mesh_sha256', 'sqe_em/sqe_em.msh'),
                      ('deck_sha256', 'sqe_em/sqe_em.json'), ('origin_deck_sha256', ORIGIN_FILE)):
        _require(identity.get(key) == _hash(safe_file(folder, name)), 'native identity source bytes changed')
    ordered = identity.get('ordered_conductors')
    _require(type(ordered) is list and len(ordered) == 2 and
             all(type(item) is dict and
                 set(item) == _PORT_KEYS | {'native_geometry_sha256', 'declared_geometry_sha256'}
                 and {key: item.get(key) for key in _PORT_KEYS} == port
                 for item, port in zip(ordered, em['ports'])),
             'saved named conductor selection changed')
    _require(type(identity.get('ground')) is dict
             and all(identity['ground'].get(key) == value for key, value in em['ground'].items()),
             'saved ground selection changed')
    return identity
