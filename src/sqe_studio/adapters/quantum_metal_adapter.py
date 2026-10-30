"""Reviewed declarative Quantum Metal QDesign builder and native HOLD-only GDS.

This module neither constructs geometry directly nor writes GDSII. QComponents,
QGeometry, routing/net connectivity and GDS output are owned by installed
Quantum Metal. No arbitrary component imports, expressions or file paths.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module, metadata
from numbers import Integral
import json
import math
from pathlib import Path
import re
import struct
from typing import Any

from .base import EngineBlocked, require_module, safe_output

# All import targets are reviewed literals, never paths supplied by a project.
COMPONENTS = {
    'TransmonPocket': ('qiskit_metal.qlibrary.qubits.transmon_pocket', 'TransmonPocket'),
    'TransmonCross': ('qiskit_metal.qlibrary.qubits.transmon_cross', 'TransmonCross'),
    'ResonatorLumped': ('qiskit_metal.qlibrary.resonators.resonator_lumped', 'ResonatorLumped'),
    'ReadoutResFC': ('qiskit_metal.qlibrary.resonators.readoutres_fc', 'ReadoutResFC'),
    'LaunchpadWirebond': ('qiskit_metal.qlibrary.terminations.launchpad_wb', 'LaunchpadWirebond'),
    'OpenToGround': ('qiskit_metal.qlibrary.terminations.open_to_ground', 'OpenToGround'),
    'ShortToGround': ('qiskit_metal.qlibrary.terminations.short_to_ground', 'ShortToGround'),
    'RouteStraight': ('qiskit_metal.qlibrary.tlines.straight_path', 'RouteStraight'),
    'RouteMeander': ('qiskit_metal.qlibrary.tlines.meandered', 'RouteMeander'),
    'RouteAnchors': ('qiskit_metal.qlibrary.tlines.anchored_path', 'RouteAnchors'),
    'RoutePathfinder': ('qiskit_metal.qlibrary.tlines.pathfinder', 'RoutePathfinder'),
}
ROUTES = frozenset({'RouteStraight', 'RouteMeander', 'RouteAnchors', 'RoutePathfinder'})
JUNCTION_COMPONENTS = frozenset({'TransmonPocket', 'TransmonCross'})
# Keys in the recipe describe micrometres, not free-form Quantum Metal expressions.
DIMENSIONS = {
    'TransmonPocket': frozenset({'pad_gap', 'inductor_width', 'pad_width', 'pad_height', 'pocket_width', 'pocket_height'}),
    'TransmonCross': frozenset({'cross_width', 'cross_length', 'cross_gap'}),
    'ResonatorLumped': frozenset({'box_width', 'box_height', 'perimeter_thickness', 'res_width', 'initial', 'turn_radius', 'inner_space', 'outer_space', 'final', 'break_width'}),
    'ReadoutResFC': frozenset({'readout_cpw_gap', 'readout_cpw_turnradius', 'readout_cpw_width', 'readout_l1', 'readout_l2', 'readout_l3', 'readout_l4', 'readout_l5', 'readout_radius', 'arc_step'}),
    'LaunchpadWirebond': frozenset({'trace_width', 'trace_gap', 'lead_length', 'pad_width', 'pad_height', 'pad_gap', 'taper_height'}),
    'OpenToGround': frozenset({'width', 'gap', 'termination_gap'}),
    'ShortToGround': frozenset({'width'}),
}
POCKET_PAD_LENGTHS = frozenset({'pad_gap', 'pad_width', 'pad_height', 'pad_cpw_shift',
    'pad_cpw_extent', 'cpw_width', 'cpw_gap', 'cpw_extend', 'pocket_extent', 'pocket_rise'})
CROSS_PAD_LENGTHS = frozenset({'claw_length', 'ground_spacing', 'ground_spacing_back',
    'claw_width', 'claw_width_back', 'claw_gap', 'claw_cpw_length', 'claw_cpw_width'})
IDENT = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,39}\Z', re.ASCII)
CELL_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,31}\Z', re.ASCII)


def _reject(message: str) -> None:
    raise EngineBlocked('Quantum Metal recipe: ' + message)


def _keys(data: Any, required: set[str], optional: set[str], label: str) -> dict:
    if type(data) is not dict or not required <= data.keys() or data.keys() - (required | optional):
        _reject(f'{label}: required={sorted(required)}, allowed={sorted(required | optional)}')
    return data


def _name(value: Any, context: str) -> str:
    if type(value) is not str or not IDENT.fullmatch(value):
        _reject(f'{context} must be an ASCII identifier (1-40 characters)')
    return value


def _number(value: Any, label: str, lo: float, hi: float) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        _reject(f'{label} must be a finite number in [{lo}, {hi}]')
    return float(value)


def _integer(value: Any, label: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        _reject(f'{label} must be an integer in [{lo}, {hi}]')
    return value


def _unit(value: float, suffix: str) -> str:
    return f'{value:.12g}{suffix}'


def _dimension_options(value: Any, allowed: frozenset[str], label: str) -> dict:
    if type(value) is not dict or not set(value) <= {k + '_um' for k in allowed}:
        _reject(f'{label} has an unsupported Quantum Metal option')
    return {k[:-3]: _unit(_number(v, f'{label}.{k}', 0.01, 100000), 'um')
            for k, v in sorted(value.items())}


def _pads(kind: str, pads: Any, label: str) -> dict:
    if kind not in JUNCTION_COMPONENTS:
        _reject(f'{label}: connection pads only supported for reviewed transmons')
    if type(pads) is not dict or len(pads) > 8:
        _reject(f'{label}: connection_pads must be a mapping of at most 8 pins')
    result = {}
    for pin, options in sorted(pads.items()):
        _name(pin, f'{label} connection pad name')
        if type(options) is not dict:
            _reject(f'{label}.{pin}: connection pad options must be an object')
        allowed = POCKET_PAD_LENGTHS if kind == 'TransmonPocket' else CROSS_PAD_LENGTHS
        special = {'loc_W', 'loc_H'} if kind == 'TransmonPocket' else {'connector_type', 'connector_location'}
        if set(options) - ({v + '_um' for v in allowed} | special):
            _reject(f'{label}.{pin}: unsupported connection pad option')
        config = _dimension_options({k: v for k, v in options.items() if k.endswith('_um')}, allowed, label)
        for key in sorted(special & options.keys()):
            val = options[key]
            if kind == 'TransmonPocket':
                if type(val) is not int or val not in (-1, 1):
                    _reject(f'{label}.{pin}.{key} must be -1 or 1')
            elif key == 'connector_type':
                if type(val) is not int or val not in (0, 1):
                    _reject(f'{label}.{pin}.connector_type must be 0 or 1')
            elif type(val) is not int or val not in (0, 90, 180, 270):
                _reject(f'{label}.{pin}.connector_location must be 0, 90, 180 or 270')
            config[key] = str(val)
        result[pin] = config
    return result


def _endpoint(obj: Any, label: str) -> tuple[str, str]:
    _keys(obj, {'component', 'pin'}, set(), label)
    return _name(obj['component'], label + '.component'), _name(obj['pin'], label + '.pin')


def _route_options(component: dict, label: str) -> tuple[dict, tuple[tuple[str, str], tuple[str, str]]]:
    start = _endpoint(component['start'], label + '.start')
    end = _endpoint(component['end'], label + '.end')
    if start == end or start[0] == end[0]:
        _reject(f'{label}: route endpoints must be distinct component pins')
    opts = {'pin_inputs': {'start_pin': {'component': start[0], 'pin': start[1]},
                           'end_pin': {'component': end[0], 'pin': end[1]}}}
    if 'trace_width_um' in component:
        opts['trace_width'] = _unit(_number(component['trace_width_um'], label + '.trace_width_um', 0.01, 1000), 'um')
    if 'trace_gap_um' in component:
        opts['trace_gap'] = _unit(_number(component['trace_gap_um'], label + '.trace_gap_um', 0.01, 1000), 'um')
    if 'fillet_um' in component:
        opts['fillet'] = _unit(_number(component['fillet_um'], label + '.fillet_um', 0, 1000), 'um')
    if 'total_length_mm' in component:
        if component['kind'] != 'RouteMeander':
            _reject(f'{label}: total_length_mm only belongs to RouteMeander')
        opts['total_length'] = _unit(_number(component['total_length_mm'], label + '.total_length_mm', 0.01, 100), 'mm')
    if 'anchors' in component:
        if component['kind'] not in {'RouteAnchors', 'RoutePathfinder'}:
            _reject(f'{label}: anchors unsupported for this route')
        anchors = component['anchors']
        if type(anchors) is not list or not 1 <= len(anchors) <= 32:
            _reject(f'{label}: anchors requires 1-32 ordered coordinate pairs')
        opts['anchors'] = OrderedDict()
        for i, point in enumerate(anchors):
            _keys(point, {'x_mm', 'y_mm'}, set(), label + '.anchors')
            opts['anchors'][i] = (_number(point['x_mm'], label + '.anchor.x_mm', -100, 100),
                                  _number(point['y_mm'], label + '.anchor.y_mm', -100, 100))
    if 'constraints' in component:
        if component['kind'] != 'RoutePathfinder':
            _reject(f'{label}: reviewed constraints are only supported for RoutePathfinder')
        rules = _keys(component['constraints'], {'avoid_collision'}, set(), label + '.constraints')
        if type(rules['avoid_collision']) is not bool or not rules['avoid_collision']:
            _reject(f'{label}: pathfinder requires avoid_collision=true; no unsafe override')
        opts['advanced'] = {'avoid_collision': 'true'}
    if component['kind'] == 'RoutePathfinder':
        if 'step_size_um' in component:
            opts['step_size'] = _unit(_number(component['step_size_um'], label + '.step_size_um', 1, 1000), 'um')
        opts.setdefault('advanced', {'avoid_collision': 'true'})
    elif 'step_size_um' in component:
        _reject(f'{label}: step_size_um is only for RoutePathfinder')
    if component['kind'] == 'RouteMeander' and 'meander' in component:
        m = _keys(component['meander'], {'spacing_um'}, {'asymmetry_um'}, label + '.meander')
        opts['meander'] = {'spacing': _unit(_number(m['spacing_um'], label + '.spacing_um', 1, 10000), 'um')}
        if 'asymmetry_um' in m:
            opts['meander']['asymmetry'] = _unit(_number(m['asymmetry_um'], label + '.asymmetry_um', -10000, 10000), 'um')
    elif 'meander' in component:
        _reject(f'{label}: meander settings only belong to RouteMeander')
    return opts, (start, end)


@dataclass(frozen=True)
class PlannedComponent:
    name: str
    kind: str
    layer: int
    options: dict
    endpoints: tuple[tuple[str, str], tuple[str, str]] | None = None
    net: str | None = None
    junction_cell: str | None = None


@dataclass(frozen=True)
class QDesignBuild:
    """Native in-process A03 interface; consumers must not mutate/reinterpret it."""
    design: Any
    recipe_sha256: str
    component_names: tuple[str, ...]
    pin_identities: tuple[tuple[str, str], ...]
    routes: tuple[tuple[str, str, tuple[str, str], tuple[str, str]], ...]
    layers: tuple[int, ...]
    junction_cells: tuple[str, ...]
    junction_layers: tuple[int, ...]


def validate_recipe(layout: Any) -> tuple[list[PlannedComponent], dict]:
    """Validate a saved project layout without importing or executing an engine."""
    _keys(layout, {'engine', 'chip', 'components'}, {'gds'}, 'layout')
    if layout['engine'] != 'quantum_metal':
        _reject('layout.engine must be quantum_metal')
    chip = _keys(layout['chip'], {'width_mm', 'height_mm', 'thickness_um'}, set(), 'chip')
    for key in ('width_mm', 'height_mm'):
        _number(chip[key], 'chip.' + key, 0.1, 1000)
    _number(chip['thickness_um'], 'chip.thickness_um', 0.1, 1000)
    components = layout['components']
    if type(components) is not list or not 1 <= len(components) <= 32:
        _reject('components must be a list with 1-32 entries')
    names = set()
    nets = set()
    prepared = []
    for c in components:
        if type(c) is not dict or c.get('kind') not in COMPONENTS:
            _reject('illegal QComponent kind; only reviewed allowlist is supported')
        kind = c['kind']
        label = _name(c.get('name'), 'component.name')
        if label in names:
            _reject(f'duplicate QComponent name {label}')
        names.add(label)
        if kind in ROUTES:
            _keys(c, {'kind', 'name', 'start', 'end', 'net'},
                  {'layer', 'trace_width_um', 'trace_gap_um', 'fillet_um', 'total_length_mm', 'anchors', 'constraints', 'step_size_um', 'meander'}, label)
            net = _name(c['net'], label + '.net')
            if net in nets:
                _reject(f'duplicate route net identity {net}; multi-segment networks require a reviewed graph schema')
            nets.add(net)
            options, endpoints = _route_options(c, label)
            prepared.append(PlannedComponent(label, kind, _integer(c.get('layer', 1), label + '.layer', 1, 255),
                                             options, endpoints, net))
        else:
            _keys(c, {'kind', 'name', 'x_mm', 'y_mm'},
                  {'orientation_deg', 'layer', 'options', 'connection_pads', 'junction_cell', 'n_turns', 'subtract_layer'}, label)
            if 'n_turns' in c and kind != 'ResonatorLumped':
                _reject(f'{label}: n_turns only supported for ResonatorLumped')
            if 'subtract_layer' in c and kind != 'ReadoutResFC':
                _reject(f'{label}: subtract_layer only supported for ReadoutResFC')
            layer = _integer(c.get('layer', 1), label + '.layer', 1, 255)
            options = {'pos_x': _unit(_number(c['x_mm'], label + '.x_mm', -100, 100), 'mm'),
                       'pos_y': _unit(_number(c['y_mm'], label + '.y_mm', -100, 100), 'mm'),
                       'orientation': _unit(_number(c.get('orientation_deg', 0), label + '.orientation_deg', -360, 360), ''),
                       'layer': str(layer), 'chip': 'main'}
            options.update(_dimension_options(c.get('options', {}), DIMENSIONS[kind], label + '.options'))
            if kind == 'ReadoutResFC':
                if 'subtract_layer' not in c:
                    _reject(f'{label}: ReadoutResFC requires explicit subtract_layer')
                options['layer_subtract'] = str(_integer(c['subtract_layer'], label + '.subtract_layer', 1, 255))
            if kind == 'ResonatorLumped' and 'n_turns' in c:
                options['n_turns'] = str(_integer(c['n_turns'], label + '.n_turns', 1, 100))
            if 'connection_pads' in c:
                options['connection_pads'] = _pads(kind, c['connection_pads'], label)
            cell = None
            if 'junction_cell' in c:
                if kind not in JUNCTION_COMPONENTS or type(c['junction_cell']) is not str or not CELL_IDENT.fullmatch(c['junction_cell']):
                    _reject(f'{label}: invalid junction cell identity')
                cell = c['junction_cell']
                options['gds_cell_name'] = cell
            prepared.append(PlannedComponent(label, kind, layer, options, junction_cell=cell))
    terminals = {p.name: p for p in prepared if p.kind not in ROUTES}
    used_pins = set()
    for p in prepared:
        if p.kind in ROUTES:
            for endpoint in p.endpoints:
                if endpoint[0] not in terminals:
                    _reject(f'{p.name}: missing terminal component {endpoint[0]}')
                if endpoint in used_pins:
                    _reject(f'{p.name}: terminal pin {endpoint} used by another route')
                used_pins.add(endpoint)
                if terminals[endpoint[0]].layer != p.layer:
                    _reject(f'{p.name}: route layer does not match {endpoint[0]} layer')
    return sorted(prepared, key=lambda p: (p.kind in ROUTES, p.name)), chip


def _qgeometry_layers(design) -> tuple[set[int], set[int]]:
    observed, junction_layers = set(), set()
    for typ in ('poly', 'path', 'junction'):
        table = design.qgeometry.tables[typ]
        for layer in table['layer'].tolist():
            if isinstance(layer, bool) or type(layer) not in (int, float) and not str(layer).isdigit() or float(layer) != int(float(layer)) or not 1 <= int(float(layer)) <= 255:
                _reject(f'native QGeometry {typ} has invalid layer {layer!r}')
            observed.add(int(layer))
            if typ == 'junction':
                junction_layers.add(int(layer))
    return observed, junction_layers


def build_qdesign(layout: dict) -> QDesignBuild:
    """Build a deterministic native QDesign from the exact saved layout recipe.

    No side effects on the saved recipe; no generated connections beyond explicit
    routes. Unavailable API, unbuilt pins, empty QGeometry and broken nets block.
    """
    planned, chip = validate_recipe(layout)
    require_module('qiskit_metal', 'Quantum Metal')
    from qiskit_metal.designs import DesignPlanar

    design = DesignPlanar(enable_renderers=False)
    design.overwrite_enabled = False
    design.chips.main.size.size_x = _unit(float(chip['width_mm']), 'mm')
    design.chips.main.size.size_y = _unit(float(chip['height_mm']), 'mm')
    design.chips.main.size.size_z = _unit(-float(chip['thickness_um']), 'um')
    pins = []
    routes = []
    for p in planned:
        module, symbol = COMPONENTS[p.kind]
        if p.endpoints:
            for owner, pin in p.endpoints:
                if pin not in design.components[owner].pins:
                    _reject(f'{p.name}: declared pin {owner}.{pin} absent from native QDesign')
        try:
            native = getattr(import_module(module), symbol)
            instance = native(design, name=p.name, options=p.options)
        except Exception as exc:
            raise EngineBlocked(f'Native Quantum Metal component {p.name} ({p.kind}) failed: {type(exc).__name__}: {exc}') from exc
        if p.name not in design.components or design.components[p.name] is not instance:
            _reject(f'native Quantum Metal did not register component {p.name}')
        if p.kind in ROUTES:
            start, end = p.endpoints
            if not {'start', 'end'} <= set(instance.pins):
                _reject(f'{p.name}: native route lacks start/end pins')
            ids = [design.components[name].pins[pin]['net_id'] for name, pin in (start, end)]
            if any(not isinstance(v, Integral) or isinstance(v, bool) or v <= 0 for v in ids) or ids[0] != ids[1]:
                _reject(f'{p.name}: native route did not connect both declared pins to the same net')
            routes.append((p.net, p.name, start, end))
        else:
            for name in sorted(instance.pins):
                _name(name, f'{p.name} native pin')
                pins.append((p.name, name))
        tables = design.qgeometry.get_component(p.name)
        if not any(len(t) for t in tables.values()) and not (p.kind == 'ShortToGround' and instance.pins):
            _reject(f'{p.name}: native component has no QGeometry')
    declared_layers = {p.layer for p in planned}
    declared_layers.update(int(p.options['layer_subtract']) for p in planned if 'layer_subtract' in p.options)
    observed_layers, junction_layers = _qgeometry_layers(design)
    if not observed_layers or not observed_layers <= declared_layers:
        _reject(f'native QGeometry layers {sorted(observed_layers)} differ from declared {sorted(declared_layers)}')
    if any(p.kind in JUNCTION_COMPONENTS for p in planned) and not junction_layers:
        _reject('transmon junction QGeometry absent')
    recipe_hash = sha256(json.dumps(layout, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return QDesignBuild(design, recipe_hash, tuple(p.name for p in planned), tuple(pins),
                        tuple(routes), tuple(sorted(observed_layers)),
                        tuple(sorted({p.junction_cell for p in planned if p.junction_cell})),
                        tuple(sorted(junction_layers)))


def _inspect_native_gds(path: Path, expected_layers: set[int], required_cells: set[str],
                        allowed_layers: set[int] | None = None) -> dict:
    """Bounded *read-only* structural inspection of the native GDSII file.

    This is NOT a GDS writer or renderer. The native renderer alone serializes
    mask geometry. Scan only record lengths/tags, layer numbers and cell names;
    no geometry construction, numeric interpretation or process qualification.
    """
    try:
        size = path.stat().st_size
        if not 32 <= size <= 128 * 1024 * 1024:
            _reject('GDS is empty or exceeds per-artifact size limit')
        data = path.read_bytes()
    except OSError as exc:
        raise EngineBlocked(f'Could not inspect native GDS file: {exc}') from exc
    pos, cells, layers = 0, set(), set()
    started, finished, in_structure, shape_count = False, False, False, 0
    seen_header = seen_bgnlib = seen_units = False
    while pos < size:
        if size - pos < 4:
            _reject('truncated native GDSII record header')
        length, tag, dtype = struct.unpack_from('>HBB', data, pos)
        if length < 4 or length % 2 or pos + length > size:
            _reject('malformed/truncated native GDSII record length')
        payload = data[pos + 4:pos + length]
        if finished:
            _reject('unexpected data after GDSII ENDLIB')
        if tag == 0x00:  # HEADER
            seen_header = length == 6 and dtype == 2
        elif tag == 0x01:  # BGNLIB
            seen_bgnlib = True
        elif tag == 0x03:  # UNITS
            seen_units = length == 20 and dtype == 5
        elif tag == 0x05:  # BGNSTR
            if in_structure:
                _reject('nested GDSII structures')
            started, in_structure = True, True
        elif tag == 0x06:  # STRNAME
            if not in_structure or dtype != 6:
                _reject('GDSII cell name outside structure')
            try:
                name = payload.rstrip(b'\0').decode('ascii')
            except UnicodeDecodeError:
                _reject('non-ASCII GDSII cell name')
            if not name or len(name) > 32 or name in cells:
                _reject('invalid/duplicate native GDSII cell identity')
            cells.add(name)
        elif tag == 0x07:  # ENDSTR
            if not in_structure:
                _reject('GDSII structure end without beginning')
            in_structure = False
        elif tag in (0x08, 0x09):  # BOUNDARY or PATH
            if not in_structure:
                _reject('GDSII geometry outside structure')
            shape_count += 1
        elif tag == 0x0D:  # LAYER
            if not in_structure or dtype != 2 or length != 6:
                _reject('malformed native GDSII layer record')
            layers.add(struct.unpack('>H', payload)[0])
        elif tag == 0x04:  # ENDLIB
            if in_structure:
                _reject('unclosed native GDSII structure')
            finished = True
        pos += length
    if not (seen_header and seen_bgnlib and seen_units and started and finished and cells and shape_count):
        _reject('native GDSII missing mandatory library, structure or shape records')
    if not expected_layers <= layers:
        _reject(f'GDS layers {sorted(layers)} omit required QGeometry layers {sorted(expected_layers)}')
    if allowed_layers is not None and not layers <= allowed_layers:
        _reject(f'GDS contains unmapped layers {sorted(layers - allowed_layers)}')
    if not required_cells <= cells:
        _reject(f'GDS missing required junction cells {sorted(required_cells - cells)}')
    return {'cells': sorted(cells), 'layers': sorted(layers), 'geometry_records': shape_count,
            'inspection': 'read_only_gdsii_record_scan'}


def run(study: dict, project: dict, output_dir: str | Path) -> dict:
    """Generate only a native, unqualified draft and mandatory HOLD evidence."""
    if type(study) is not dict or study.get('kind') != 'gds_draft' or study.get('engine') not in (None, 'quantum_metal'):
        raise EngineBlocked('Only Quantum Metal native gds_draft is permitted')
    layout = project.get('layout') if type(project) is dict else None
    planned, _ = validate_recipe(layout)
    gds = layout.get('gds')
    _keys(gds, {'layer_map', 'negative_layers'}, set(), 'layout.gds')
    mapping = _keys(gds['layer_map'], {'main'}, set(), 'layout.gds.layer_map')
    mapped = mapping['main']
    if type(mapped) is not list or not mapped or len(mapped) != len(set(str(x) for x in mapped)):
        _reject('gds.layer_map.main must be a nonempty unique layer list')
    layer_set = {_integer(x, 'gds.layer_map.main layer', 1, 255) for x in mapped}
    actual_set = {p.layer for p in planned}
    actual_set.update(int(p.options['layer_subtract']) for p in planned if 'layer_subtract' in p.options)
    if not actual_set <= layer_set:
        _reject(f'GDS layer map omits component layers {sorted(actual_set - layer_set)}')
    negatives = gds['negative_layers']
    if type(negatives) is not list or len(negatives) != len(set(str(x) for x in negatives)):
        _reject('GDS negative_layers must be a unique list')
    negative_set = {_integer(x, 'negative layer', 1, 255) for x in negatives}
    if not negative_set <= layer_set:
        _reject('negative mask layers not present in layer map')
    # Worker has no authenticated, hash-checked junction asset staging yet.
    # Never silently render a transmon's junction placeholder into a mask.
    if any(p.kind in JUNCTION_COMPONENTS for p in planned):
        missing = [p.name for p in planned if p.kind in JUNCTION_COMPONENTS and p.junction_cell is None]
        if missing:
            _reject('explicit junction_cell required for ' + ', '.join(missing))
        raise EngineBlocked('Native junction library staging with content hash and verified cell/layer map is not present in frozen project/worker contract; no GDS emitted')
    build = build_qdesign(layout)
    if not set(build.layers) <= layer_set:
        _reject('native QGeometry has layer absent from GDS layer map')
    from qiskit_metal.renderers.renderer_gds.gds_renderer import QGDSRenderer
    from qiskit_metal import Dict
    output = safe_output(output_dir)
    filename = 'quantum_metal_unqualified.gds'
    target = output / filename
    try:
        renderer = QGDSRenderer(design=build.design)
        renderer.options['fabricate'] = 'False'
        renderer.options['path_filename'] = None
        renderer.options['negative_mask'] = Dict(main=sorted(negative_set))
        ok = renderer.export_to_gds(str(target), highlight_qcomponents=[])
        if ok != 1 or not target.is_file() or target.stat().st_size < 32:
            raise EngineBlocked('native QGDSRenderer did not produce a valid GDS file')
        inspection = _inspect_native_gds(target, set(build.layers), set(), layer_set)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    try:
        version = metadata.version('quantum-metal')
    except metadata.PackageNotFoundError:
        version = 'unknown: installed qiskit_metal without quantum-metal distribution metadata'
    (output / 'gds_hold.json').write_text(json.dumps({
        'fabrication_status': 'HOLD', 'source': 'Quantum Metal QGDSRenderer',
        'engine_version': version, 'recipe_sha256': build.recipe_sha256,
        'layers_declared': sorted(layer_set), 'qgeometry_layers': list(build.layers),
        'negative_mask_layers': sorted(negative_set), 'gds_structure': inspection,
        'junction_cells': [], 'reason': 'No approved PDK, DRC/LVS, mask polarity approval, or foundry signoff',
    }, sort_keys=True, indent=2) + '\n', encoding='utf8')
    return {'engine_version': version, 'native_files': [filename, 'gds_hold.json'],
            'kind': 'gds_draft', 'scientific_status': 'review_required'}
