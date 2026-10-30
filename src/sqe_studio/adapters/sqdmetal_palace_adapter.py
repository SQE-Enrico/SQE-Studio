"""Fail-closed, revision-snapshot SQDMetal -> Gmsh -> Palace adapter.

No SQE-owned geometry/EM solver is used. Physical inputs must be reviewed;
SQDMetal creates the actual 3D mesh and Palace configuration. In particular,
this module does not interpret an arbitrary user-supplied Palace JSON as safe.
The frozen adapter ABI provides no revision ID: the worker binds immutable
revision provenance to the returned native files.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

from .base import EngineBlocked, EngineFailure, require_module, safe_output

KINDS = {'capacitance': 'Electrostatic', 'eigenmode': 'Eigenmode',
         'sparameters': 'Driven'}
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,39}$')
MAX_NATIVE_BYTES = 128 * 1024 * 1024


def _blocked(condition, reason):
    if not condition:
        raise EngineBlocked(reason)


def _mapping(obj, keys, name):
    _blocked(isinstance(obj, dict) and set(obj) == set(keys),
             f'{name}: expected exactly {", ".join(sorted(keys))}')


def _number(value, name, low, high, *, inclusive_low=False):
    _blocked(type(value) in (int, float) and math.isfinite(value)
             and (value >= low if inclusive_low else value > low) and value <= high,
             f'{name}: expected finite value in {"[" if inclusive_low else "("}{low}, {high}]')
    return float(value)


def _positive_int(value, name, maximum):
    _blocked(type(value) is int and 1 <= value <= maximum,
             f'{name}: expected integer from 1 to {maximum}')
    return value


def _material_check(stack, chip):
    _blocked(isinstance(stack, list) and len(stack) == 3,
             'Missing full material stack: require substrate, metal, superstrate')
    substrate, metal, cap = stack
    _mapping(substrate, ('role', 'material', 'thickness_um', 'relative_permittivity',
                         'loss_tangent'), 'substrate')
    _mapping(metal, ('role', 'material', 'layer', 'thickness_nm', 'em_model'), 'metal')
    _mapping(cap, ('role', 'material', 'height_um', 'relative_permittivity',
                   'loss_tangent'), 'superstrate')
    _blocked(substrate['role'] == 'substrate' and substrate['material'] in ('silicon', 'sapphire'),
             'Substrate material must be explicitly silicon or sapphire (SQDMetal single-substrate model)')
    _blocked(metal['role'] == 'metal' and metal['material'] == 'aluminium'
             and metal['em_model'] == 'PEC' and type(metal['layer']) is int and metal['layer'] >= 1,
             'Metal layer must be explicit aluminium PEC on a positive QGeometry layer')
    _blocked(cap['role'] == 'superstrate' and cap['material'] == 'vacuum',
             'Superstrate must be explicitly vacuum; other stacks require reviewed native mapping')
    thickness = _number(substrate['thickness_um'], 'substrate thickness_um', 0, 1e6)
    _number(metal['thickness_nm'], 'metal thickness_nm', 0, 1e6)
    _number(cap['height_um'], 'superstrate height_um', 0, 1e6)
    for region, label in ((substrate, 'substrate'), (cap, 'superstrate')):
        _number(region['relative_permittivity'], label + ' relative_permittivity', 0, 1e5)
        _number(region['loss_tangent'], label + ' loss_tangent', 0, 1, inclusive_low=True)
    _blocked(cap['relative_permittivity'] == 1.0 and cap['loss_tangent'] == 0.0,
             'Vacuum permittivity/loss must be explicitly 1.0/0.0')
    _blocked(isinstance(chip, dict) and type(chip.get('thickness_um')) in (float, int)
             and math.isfinite(chip['thickness_um']) and math.isclose(thickness, chip['thickness_um'], rel_tol=1e-9),
             'Substrate thickness must match the A02 QDesign chip thickness in um')
    return substrate, metal, cap


def preflight(study, project):
    """Pure validation: raises *before* any native import or directory creation.

    Study.inputs['em'] is an A03-local, explicit physical mapping. It is not a
    substitute for a versioned A01 shared interoperability schema.
    """
    _blocked(isinstance(study, dict) and study.get('kind') in KINDS,
             'Unsupported EM kind; SQDMetal requires capacitance, eigenmode or sparameters')
    _blocked(isinstance(project, dict) and isinstance(project.get('process'), dict),
             'Missing project process/stack')
    proc = project['process']
    _blocked(proc.get('source') == 'reviewed', 'Process source must be reviewed (not unverified)')
    layout = project.get('layout')
    _blocked(isinstance(layout, dict) and layout.get('engine') == 'quantum_metal',
             'A02 Quantum Metal QDesign recipe is mandatory')
    chip = layout.get('chip')
    _blocked(isinstance(chip, dict) and isinstance(layout.get('components'), list)
             and bool(layout['components']), 'Missing A02 chip/components for physical EM geometry')
    substrate, metal, cap = _material_check(proc.get('stack'), chip)
    inputs = study.get('inputs')
    _blocked(isinstance(inputs, dict) and set(inputs) == {'em'} and isinstance(inputs['em'], dict),
             'Missing reviewed study.inputs.em physical mapping or unexpected input fields')
    em = inputs['em']
    _mapping(em, ('ground', 'boundaries', 'ports', 'mesh', 'execution', 'solver'), 'em')
    ground = em['ground']
    _mapping(ground, ('kind', 'layer', 'verified'), 'ground')
    _blocked(ground['kind'] == 'qdesign_ground_plane' and ground['verified'] is True
             and type(ground['layer']) is int and ground['layer'] == metal['layer'],
             'Missing reviewed, layer-matched QDesign ground plane')
    bounds = em['boundaries']
    _mapping(bounds, ('x_neg_um', 'x_pos_um', 'y_neg_um', 'y_pos_um',
                      'z_neg_um', 'z_pos_um', 'farfield'), 'boundaries')
    for axis in ('x_neg_um', 'x_pos_um', 'y_neg_um', 'y_pos_um', 'z_neg_um', 'z_pos_um'):
        _number(bounds[axis], 'boundary ' + axis, 0, 1e6, inclusive_low=True)
    _blocked(bounds['z_pos_um'] >= cap['height_um'],
             'Upper boundary must contain the full superstrate height')
    _blocked(bounds['farfield'] == ('ground' if study['kind'] == 'capacitance' else 'pec'),
             'Explicit farfield must be ground for capacitance or pec for RF/eigenmode')
    mesh = em['mesh']
    _mapping(mesh, ('min_um', 'max_um', 'refinement_levels', 'relative_tolerance'), 'mesh plan')
    min_um = _number(mesh['min_um'], 'mesh minimum um', 0, 1e4)
    max_um = _number(mesh['max_um'], 'mesh maximum um', min_um, 1e5)
    _blocked(isinstance(mesh['refinement_levels'], list)
             and mesh['refinement_levels'] in ([0, 1], [0, 1, 2]),
             'Mesh convergence plan requires ordered native refinement levels [0,1] or [0,1,2]')
    _number(mesh['relative_tolerance'], 'convergence tolerance', 0, 0.25)
    _blocked(em['execution'] in ('deck_only', 'solve'), 'execution must be deck_only or solve')
    solver = em['solver']
    mandatory = ('order', 'tolerance', 'max_iterations', 'num_cpus')
    extra = ('start_hz', 'modes') if study['kind'] == 'eigenmode' else (
        ('frequencies_hz', 'excited_port') if study['kind'] == 'sparameters' else ())
    _mapping(solver, mandatory + extra, 'solver')
    _positive_int(solver['order'], 'solver order', 4)
    _number(solver['tolerance'], 'solver tolerance', 0, 1e-2)
    _positive_int(solver['max_iterations'], 'solver max_iterations', 1000)
    _positive_int(solver['num_cpus'], 'solver num_cpus', 8)
    if study['kind'] == 'eigenmode':
        _number(solver['start_hz'], 'start frequency Hz', 1e6, 100e9)
        _positive_int(solver['modes'], 'number of eigenmodes', 12)
    if study['kind'] == 'sparameters':
        freqs = solver['frequencies_hz']
        _blocked(isinstance(freqs, list) and 2 <= len(freqs) <= 201,
                 'Driven study requires 2-201 explicit increasing frequencies in Hz')
        for freq in freqs:
            _number(freq, 'frequency Hz', 1e6, 100e9)
        _blocked(all(a < b for a, b in zip(freqs, freqs[1:])),
                 'Driven frequency axis must be strictly increasing in Hz')
        step = freqs[1] - freqs[0]
        _blocked(all(math.isclose(b - a, step, rel_tol=1e-9) for a, b in zip(freqs, freqs[1:])),
                 'SQDMetal native driven solver requires uniform start/stop/step frequency grid')
    ports = em['ports']
    _blocked(isinstance(ports, list) and 1 <= len(ports) <= 16,
             'Missing physical ports or capacitance terminals (1-16 required)')
    names = {c.get('name') for c in layout['components'] if isinstance(c, dict)}
    _blocked(all(isinstance(x, str) and NAME.fullmatch(x) for x in names),
             'Invalid QDesign component identity in layout')
    seen = set()
    for index, p in enumerate(ports, 1):
        _blocked(isinstance(p, dict), f'port {index} must be an object')
        _blocked(p.get('index') == index and type(p.get('index')) is int,
                 'Port numbering must be contiguous 1-based, in native creation order')
        _blocked(p.get('component') in names and isinstance(p.get('component'), str),
                 f'Port {index} refers to a missing QDesign component')
        key = (p.get('component'), p.get('kind'), p.get('pin'))
        _blocked(key not in seen, 'Duplicate physical port/pin mapping')
        seen.add(key)
        if study['kind'] == 'capacitance':
            _mapping(p, ('index', 'kind', 'component', 'native_attributes'), f'terminal {index}')
            _blocked(p['kind'] == 'conductor' and isinstance(p['native_attributes'], list)
                     and bool(p['native_attributes']) and all(type(a) is int and a > 0 for a in p['native_attributes']),
                     'Capacitance terminal requires reviewed conductor and explicit native physical tags')
        else:
            _blocked(p.get('kind') in ('cpw_launcher', 'cpw_route', 'junction'),
                     'Port kind must be cpw_launcher, cpw_route or junction')
            if p['kind'] == 'junction':
                _mapping(p, ('index', 'kind', 'component', 'L_nH', 'C_fF'), f'junction {index}')
                _number(p['L_nH'], 'Josephson inductance nH', 0, 1e6)
                _number(p['C_fF'], 'Josephson capacitance fF', 0, 1e6, inclusive_low=True)
                _blocked(study['kind'] == 'eigenmode',
                         'Junction inductive ports cannot be treated as driven S-parameter reference ports')
            else:
                required = ('index', 'kind', 'component', 'length_um', 'impedance_ohm')
                if p['kind'] == 'cpw_route':
                    required += ('pin',)
                _mapping(p, required, f'CPW port {index}')
                _number(p['length_um'], 'CPW port length um', 0, 1e5)
                _number(p['impedance_ohm'], 'CPW reference impedance ohm', 0, 1e6)
                if p['kind'] == 'cpw_route':
                    _blocked(p['pin'] in ('start', 'end'), 'CPW route pin must be start or end')
    if study['kind'] == 'sparameters':
        _blocked(type(solver['excited_port']) is int and 1 <= solver['excited_port'] <= len(ports),
                 'Driven excitation must reference an existing 1-based native port index')
    return em


def _version(distribution):
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return 'not-reported'


def _native_imports():
    for mod, label in (('SQDMetal', 'SQDMetal'), ('gmsh', 'Gmsh'),
                       ('qiskit_metal', 'Quantum Metal')):
        require_module(mod, label)
    from . import quantum_metal_adapter as a02
    _blocked(callable(getattr(a02, 'build_qdesign', None)),
             'A02 native QDesign builder is unavailable; do not reconstruct geometry in A03.')
    return a02


def _palace_readiness():
    """Only deployment-controlled environment variables, never study shell/path input."""
    backend = os.environ.get('SQE_PALACE_BACKEND', 'native')
    _blocked(backend in ('native', 'wsl'), 'Operator Palace backend must be native or wsl')
    binary = os.environ.get('SQE_PALACE_BINARY' if backend == 'native'
                            else 'SQE_PALACE_WSL_BINARY', '')
    if backend == 'native':
        _blocked(bool(binary) and Path(binary).is_absolute() and Path(binary).is_file()
                 and os.access(binary, os.X_OK),
                 'Palace native binary missing or non-executable; configure SQE_PALACE_BINARY absolute path')
        command = [str(Path(binary).resolve())]
        hash_value = _hash(Path(binary))
        _blocked(platform.system() != 'Windows' or not binary.lower().endswith('.sh'),
                 'Windows Palace must be a native executable, not an untrusted shell wrapper')
    else:
        _blocked(platform.system() == 'Windows', 'WSL Palace backend only supported on Windows 11 host')
        _blocked(binary.startswith('/') and '..' not in Path(binary).parts
                 and '\x00' not in binary and '\n' not in binary,
                 'WSL Palace requires an absolute Linux executable path in SQE_PALACE_WSL_BINARY')
        launcher = shutil.which('wsl.exe')
        _blocked(bool(launcher), 'wsl.exe unavailable; install and configure Windows Subsystem for Linux')
        probe = subprocess.run([launcher, '--exec', '/usr/bin/test', '-x', binary],
                               capture_output=True, text=True, timeout=15, check=False)
        _blocked(probe.returncode == 0, 'WSL Palace executable not accessible in default distribution')
        command = [launcher, '--exec', binary]
        hash_value = None  # cannot truthfully hash WSL binary from Windows Python
    try:
        version = subprocess.run(command + ['--version'], capture_output=True,
                                 text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineBlocked(f'Palace binary version probe failed: {type(exc).__name__}') from exc
    raw = (version.stdout + '\n' + version.stderr).strip()[:1000]
    _blocked(version.returncode == 0 and re.search(r'palace', raw, re.I),
             'Palace --version did not verify a Palace binary and version; solver blocked')
    return {'backend': backend, 'command': command,
            'version': raw.splitlines()[0][:200], 'binary_sha256': hash_value}


def _hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _checked_qdesign(project, a02):
    """A02/A03 integration: validate the exact saved layout, not the whole project.

    A02 owns native geometry. A03 only unwraps its verified QDesignBuild and
    binds it to the requested layout recipe. No fallback QGeometry or mock.
    """
    layout = project.get('layout') if type(project) is dict else None
    a02.validate_recipe(layout)
    built = a02.build_qdesign(layout)
    from hashlib import sha256
    expected = sha256(json.dumps(layout, sort_keys=True, separators=(',', ':'),
                                 allow_nan=False).encode()).hexdigest()
    _blocked(isinstance(built, a02.QDesignBuild),
             'A02 did not provide the reviewed QDesignBuild interface')
    _blocked(built.recipe_sha256 == expected,
             'A02 QDesign recipe digest differs from saved project layout')
    _blocked(set(built.component_names) == {c['name'] for c in layout['components']},
             'A02 native component identity differs from saved layout')
    design = built.design
    _blocked(design is not None and hasattr(design, 'components') and hasattr(design, 'qgeometry'),
             'A02 builder did not provide native Quantum Metal QDesign/QGeometry')
    return design


def _make_native(study, project, em, a02, root):
    from SQDMetal.PALACE.Capacitance_Simulation import PALACE_Capacitance_Simulation
    from SQDMetal.PALACE.Eigenmode_Simulation import PALACE_Eigenmode_Simulation
    if study['kind'] == 'sparameters':
        from SQDMetal.PALACE.Frequency_Driven_Simulation import PALACE_Driven_Simulation
        cls = PALACE_Driven_Simulation
    else:
        cls = (PALACE_Capacitance_Simulation if study['kind'] == 'capacitance'
               else PALACE_Eigenmode_Simulation)
    design = _checked_qdesign(project, a02)
    options = em['solver']
    substrate, metal, cap = project['process']['stack']
    settings = {
        'dielectric_material': substrate['material'], 'topping_material': cap['material'],
        'mesh_min': em['mesh']['min_um'] * 1e-6,
        'mesh_max': em['mesh']['max_um'] * 1e-6,
        'palace_dir': '', 'palace_mode': 'local',
        'mesh_refinement': 0, 'solver_order': options['order'],
        'solver_tol': options['tolerance'], 'solver_maxits': options['max_iterations'],
        'num_cpus': options['num_cpus'], 'gmsh_verbosity': 1,
    }
    if study['kind'] == 'eigenmode':
        settings.update(starting_freq=options['start_hz'], number_of_freqs=options['modes'],
                        solns_to_save=0)
    sim = cls(name='sqe_em', metal_design=design, sim_parent_directory=str(root) + '/',
              mode='simPC', meshing='GMSH', user_options=settings,
              view_design_gmsh_gui=False, create_files=True)
    sim.add_metallic(metal['layer'])
    sim.add_ground_plane()
    sim.enforce_full_3D_simulation(metal_thickness=metal['thickness_nm'] * 1e-9,
                                   substrate_trenching=0.0)
    boundaries = em['boundaries']
    for axis in ('x', 'y', 'z'):
        getattr(sim, f'set_{axis}Boundary_as_absolute')(
            boundaries[f'{axis}_neg_um'] * 1e-6, boundaries[f'{axis}_pos_um'] * 1e-6)
    if study['kind'] != 'capacitance':
        # PEC is explicit rather than accepting SQDMetal's implicit farfield default.
        sim.set_farfield(ff_type='pec')
        for p in em['ports']:
            if p['kind'] == 'junction':
                sim.create_port_JosephsonJunction(p['component'],
                                                 L_J=p['L_nH'] * 1e-9, C_J=p['C_fF'] * 1e-15)
            elif p['kind'] == 'cpw_launcher':
                sim.create_port_CPW_on_Launcher(p['component'], p['length_um'] * 1e-6,
                                                impedance_R=p['impedance_ohm'])
            else:
                sim.create_port_CPW_on_Route(p['component'], p['pin'], p['length_um'] * 1e-6,
                                             impedance_R=p['impedance_ohm'])
        if study['kind'] == 'sparameters':
            # Fixed, explicitly declared, single excitation (one S-matrix column).
            sim.set_port_excitation(options['excited_port'])
            freqs = options['frequencies_hz']
            sim.set_freq_values(freqs[0], freqs[-1], freqs[1] - freqs[0])
    # Meshing sizes explicitly refer to real QDesign components, never generated polygons.
    sim.fine_mesh_components([c['name'] for c in project['layout']['components']],
                             min_size=em['mesh']['min_um'] * 1e-6,
                             max_size=em['mesh']['max_um'] * 1e-6,
                             taper_dist_min=em['mesh']['min_um'] * 1e-6, metals_only=True)
    sim.prepare_simulation()  # Real SQDMetal geometry and gmsh meshing, not a fixture.
    return sim


def _physical_ids(gmsh, mesh):
    """Read native Gmsh mesh rather than trusting free-form deck tag numbers."""
    started = bool(gmsh.isInitialized())
    if not started:
        gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.open(str(mesh))
        types, tags, _ = gmsh.model.mesh.getElements(3)
        _blocked(bool(types) and sum(len(x) for x in tags) > 0,
                 'Gmsh mesh contains no native volume elements (not an explicit 3D mesh)')
        volumes = {tag for dim, tag in gmsh.model.getPhysicalGroups(3) if dim == 3}
        surfaces = {tag for dim, tag in gmsh.model.getPhysicalGroups(2) if dim == 2}
        _blocked(bool(volumes) and bool(surfaces),
                 'Gmsh mesh lacks 3D material or 2D boundary physical groups')
        return volumes, surfaces
    finally:
        gmsh.clear()
        if not started:
            gmsh.finalize()


def _attr_set(obj, label, allowed):
    _blocked(isinstance(obj, list) and bool(obj) and all(type(x) is int for x in obj)
             and set(obj) <= allowed, f'{label}: missing/invalid native Gmsh physical attributes')
    return set(obj)


def _validate_deck(config, em, study, volumes, surfaces):
    """Ensure SQDMetal emitted the declared geometry/physics, not default tags."""
    _blocked(isinstance(config, dict) and config.get('Problem', {}).get('Type') == KINDS[study['kind']],
             'Native Palace deck problem type mismatch')
    model = config.get('Model', {})
    _blocked(model.get('L0') == 1e-3 and isinstance(model.get('Mesh'), str)
             and Path(model['Mesh']).name == 'sqe_em.msh',
             'Palace deck mesh scale/path mismatch: expected metre geometry represented in mm (L0=1e-3)')
    _blocked(isinstance(config.get('Solver'), dict)
             and config['Solver'].get('Order') == em['solver']['order'],
             'Palace native solver order does not match reviewed study')
    mats = config.get('Domains', {}).get('Materials', [])
    _blocked(isinstance(mats, list) and len(mats) == 2,
             'SQDMetal single-substrate/air model must generate exactly two material domains')
    substrate, _, cap = study['_stack_for_validation']
    for item, expected, label in zip(mats, (cap, substrate), ('vacuum', 'substrate')):
        _attr_set(item.get('Attributes'), label + ' volume', volumes)
        _blocked(_numeric_equal(item.get('Permittivity'), expected['relative_permittivity'])
                 and _numeric_equal(item.get('LossTan', 0), expected['loss_tangent']),
                 f'Palace {label} material permittivity/loss differs from reviewed physical stack')
    _blocked(not (set(mats[0]['Attributes']) & set(mats[1]['Attributes'])),
             'Palace volume material assignments overlap')
    _blocked(set(mats[0]['Attributes']) | set(mats[1]['Attributes']) == volumes,
             'Palace material map does not cover every Gmsh 3D physical volume')
    bc = config.get('Boundaries', {})
    if study['kind'] == 'capacitance':
        _attr_set(bc.get('Ground', {}).get('Attributes'), 'electrostatic ground', surfaces)
        terminals = bc.get('Terminal', [])
        _blocked(isinstance(terminals, list) and len(terminals) == len(em['ports']),
                 'Capacitance terminal count differs from reviewed conductor list')
        for p, terminal in zip(em['ports'], terminals):
            _blocked(terminal.get('Index') == p['index'] and
                     set(terminal.get('Attributes', [])) == set(p['native_attributes']),
                     'Capacitance conductor numbering/mesh attributes differ from reviewed mapping')
            _attr_set(terminal['Attributes'], 'terminal ' + str(p['index']), surfaces)
        _blocked(not (set(bc['Ground']['Attributes']) &
                      {a for t in terminals for a in t['Attributes']}),
                 'Palace ground and capacitance terminal physical tags overlap')
    else:
        _attr_set(bc.get('PEC', {}).get('Attributes'), 'PEC ground/metal', surfaces)
        native_ports = bc.get('LumpedPort', [])
        _blocked(isinstance(native_ports, list) and len(native_ports) == len(em['ports'])
                 and not bc.get('WavePort'),
                 'Port geometry/count requires one lumped native port per reviewed port, no implicit waveports')
        for i, entry in enumerate(native_ports, 1):
            _blocked(entry.get('Index') == i, 'Palace lumped port numbering/order mismatch')
            attrs = entry.get('Attributes', [])
            if 'Elements' in entry:
                attrs = [a for elem in entry['Elements'] for a in elem.get('Attributes', [])]
            _attr_set(attrs, f'port {i}', surfaces)
    if study['kind'] == 'sparameters':
        driven = config['Solver'].get('Driven', {})
        fs = em['solver']['frequencies_hz']
        _blocked(_numeric_equal(driven.get('MinFreq'), fs[0] / 1e9)
                 and _numeric_equal(driven.get('MaxFreq'), fs[-1] / 1e9)
                 and _numeric_equal(driven.get('FreqStep'), (fs[1] - fs[0]) / 1e9),
                 'Palace native driven frequency sweep does not match reviewed Hz axis')
        _blocked(sum(p.get('Excitation') is True for p in native_ports) == 1
                 and native_ports[em['solver']['excited_port'] - 1].get('Excitation') is True,
                 'Palace native driven excitation does not match reviewed port index')
    elif study['kind'] == 'eigenmode':
        eigen = config['Solver'].get('Eigenmode', {})
        _blocked(eigen.get('N') == em['solver']['modes']
                 and _numeric_equal(eigen.get('Target'), em['solver']['start_hz'] / 1e9),
                 'Palace eigenmode target/mode count mismatch')


def _numeric_equal(actual, expected):
    return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(
        float(actual), float(expected), rel_tol=1e-7, abs_tol=1e-12)


def _csv_frequency(path, requested):
    """Validate native driven CSV axis only; preserve raw S data without conversion."""
    with path.open('r', newline='', encoding='utf-8-sig') as fd:
        rows = list(csv.reader(fd))
    _blocked(len(rows) >= 2 and bool(rows[0]), 'Native port-S.csv has no frequency header/data')
    label = rows[0][0].strip().lower()
    _blocked('freq' in label or 'f (' in label, 'Native S-parameter CSV has no frequency label')
    if 'ghz' in label:
        scale = 1e9
    elif 'mhz' in label:
        scale = 1e6
    elif 'hz' in label:
        scale = 1.0
    else:
        raise EngineBlocked('Native S-parameter frequency unit is ambiguous')
    _blocked(len(rows) - 1 == len(requested) and len(rows[0]) >= 2,
             'Native S-parameter frequency row count/columns mismatch')
    values = []
    for row in rows[1:]:
        _blocked(len(row) == len(rows[0]), 'Malformed native port-S.csv row')
        try:
            f = float(row[0]) * scale
        except ValueError as exc:
            raise EngineBlocked('Invalid native S-parameter frequency value') from exc
        _blocked(math.isfinite(f) and f > 0, 'Nonfinite/invalid Palace frequency')
        values.append(f)
    _blocked(all(math.isclose(x, y, rel_tol=1e-6) for x, y in zip(values, requested)),
             'Native S-parameter frequency axis does not match requested sweep (Hz)')
    return values


def _native_result_csv(path):
    _blocked(path.is_file() and 0 < path.stat().st_size <= MAX_NATIVE_BYTES,
             'Palace required native CSV is missing/empty/oversize: ' + path.name)
    with path.open('r', encoding='utf-8-sig', newline='') as fd:
        rows = list(csv.reader(fd))
    _blocked(len(rows) >= 2 and any(any(cell.strip() for cell in row) for row in rows[1:]),
             'Palace required native CSV has no data: ' + path.name)
    return rows


def _run_palace(readiness, folder, config_name, cpus):
    command = readiness['command'][:]
    if readiness['backend'] == 'wsl':
        launcher = command[0]
        translated = subprocess.run([launcher, '--exec', 'wslpath', '-a', '-u', str(folder)],
                                    capture_output=True, text=True, timeout=15, check=False)
        _blocked(translated.returncode == 0 and translated.stdout.strip().startswith('/'),
                 'Windows workspace cannot be safely translated to a WSL mount')
        command = [launcher, '--cd', translated.stdout.strip(), '--exec', command[-1]]
    command += ['-np', str(cpus), '-nt', '1', config_name]
    started = time.perf_counter()
    with (folder / 'palace-native.log').open('wb') as stream:
        try:
            completed = subprocess.run(command, cwd=folder, stdout=stream,
                                       stderr=subprocess.STDOUT, timeout=120, check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise EngineFailure(f'Palace native execution failed: {type(exc).__name__}') from exc
    _blocked(completed.returncode == 0,
             f'Palace native solver exited {completed.returncode}; inspect palace-native.log')
    return {'exit_code': completed.returncode,
            'elapsed_seconds': round(time.perf_counter() - started, 3)}


def run(study, project, output_dir):
    """Return only actual native mesh/deck/solver files and typed provenance sidecars."""
    em = preflight(study, project)
    a02 = _native_imports()
    readiness = _palace_readiness() if em['execution'] == 'solve' else None
    gmsh = importlib.import_module('gmsh')
    output = safe_output(output_dir)
    # This is never an arbitrary user-provided directory or shell command.
    folder = output / 'sqe_em'
    _blocked(not folder.exists(), 'A03 native output directory already exists; cannot overwrite a native run')
    folder.mkdir()
    sim = _make_native(study, project, em, a02, output)
    mesh = folder / 'sqe_em.msh'
    deck = folder / 'sqe_em.json'
    _blocked(mesh.is_file() and deck.is_file() and mesh.stat().st_size > 0,
             'SQDMetal/Gmsh did not generate native .msh and Palace .json deck')
    _blocked(mesh.stat().st_size <= MAX_NATIVE_BYTES and deck.stat().st_size <= MAX_NATIVE_BYTES,
             'Native mesh/deck exceeds artifact size budget')
    config = json.loads(deck.read_text(encoding='utf-8'))
    volumes, surfaces = _physical_ids(gmsh, mesh)
    # Validation context is local-only, not propagated into project or study.
    checked = {'kind': study['kind'], '_stack_for_validation': project['process']['stack']}
    _validate_deck(config, em, checked, volumes, surfaces)
    # Explicit solver output directory, limited to this checked workspace.
    _blocked(config['Problem'].get('Output') == 'outputFiles'
             and config['Model']['Mesh'] == 'sqe_em.msh',
             'SQDMetal deck has unsafe or unexpected relative input/output locations')
    native = ['sqe_em/sqe_em.msh', 'sqe_em/sqe_em.json']
    version = {'sqdmetal': _version('SQDMetal'), 'gmsh': str(getattr(gmsh, '__version__', 'not-reported')),
               'quantum_metal': _version('quantum-metal'),
               'palace': readiness['version'] if readiness else None}
    completion = None
    frequency_hz = None
    if em['execution'] == 'solve':
        completion = _run_palace(readiness, folder, deck.name, em['solver']['num_cpus'])
        native.append('sqe_em/palace-native.log')
        csv_name = {'capacitance': 'terminal-C.csv', 'eigenmode': 'eig.csv',
                    'sparameters': 'port-S.csv'}[study['kind']]
        result = folder / 'outputFiles' / csv_name
        _native_result_csv(result)
        if study['kind'] == 'sparameters':
            frequency_hz = _csv_frequency(result, em['solver']['frequencies_hz'])
        native.append('sqe_em/outputFiles/' + csv_name)
        if study['kind'] == 'eigenmode':
            # Palace itself exports these optional raw EPR/loss tables. Retain
            # them as native evidence; never infer Hamiltonian terms from them.
            # They may be absent depending on the Palace version and port setup.
            for extra in ('port-EPR.csv', 'port-Q.csv', 'domain-E.csv'):
                candidate = folder / 'outputFiles' / extra
                if candidate.exists():
                    _blocked(candidate.is_file() and not candidate.is_symlink()
                             and 0 < candidate.stat().st_size <= MAX_NATIVE_BYTES,
                             'Unsafe optional Palace native EPR/loss table: ' + extra)
                    _native_result_csv(candidate)
                    native.append('sqe_em/outputFiles/' + extra)
    # Real Palace/SQDMetal versions may produce further diagnostic CSVs, field
    # visualizations and resolved JSON alongside eig.csv. The worker refuses
    # undeclared files: explicitly inventory only bounded native data formats,
    # reject executable/script material, and preserve every observed byte.
    permitted_extensions = {'.csv', '.json', '.msh', '.log', '.vtu', '.pvtu',
                            '.pvd', '.vtk', '.txt', '.dat', '.geo', '.msh2'}
    declared = set(native)
    for candidate in sorted(folder.rglob('*')):
        _blocked(not candidate.is_symlink(),
                 'Native SQDMetal/Palace output includes a symbolic link')
        if candidate.is_dir():
            continue
        _blocked(candidate.is_file() and candidate.suffix.lower() in permitted_extensions,
                 'Unrecognized native output extension; fail closed: ' + candidate.name)
        _blocked(0 < candidate.stat().st_size <= MAX_NATIVE_BYTES,
                 'Unsafe native output size: ' + candidate.name)
        name = candidate.relative_to(output).as_posix()
        if name not in declared:
            native.append(name)
            declared.add(name)
        _blocked(len(declared) <= 128, 'Too many native output files for laptop budget')
    artefacts = []
    for name in native:
        path = (output / name).resolve()
        _blocked(path.is_file() and not path.is_symlink() and path.is_relative_to(output.resolve())
                 and 0 < path.stat().st_size <= MAX_NATIVE_BYTES, 'Unsafe native artifact: ' + name)
        artefacts.append({'name': name, 'sha256': _hash(path), 'bytes': path.stat().st_size,
                          'type': ('gmsh.mesh' if name.endswith('.msh') else 'palace.deck'
                                   if name.endswith('.json') else 'palace.native_log'
                                   if name.endswith('.log') else 'palace.native_field_or_auxiliary'
                                   if not name.endswith('.csv') else {'capacitance':'palace.capacitance_matrix',
                                   'eigenmode':'palace.eigenmodes',
                                   'sparameters':'palace.sparameters'}[study['kind']])})
    report = {
        'schema': 'sqe.a03.native-artifacts.v1', 'engine': 'sqdmetal_palace',
        'versions': version, 'execution': em['execution'], 'native_solver': readiness and
        {k: v for k, v in readiness.items() if k != 'command'},
        'native_completion': completion, 'artifacts': artefacts,
        'geometry_source': 'A02.build_qdesign(project.layout) verified QDesignBuild; SQDMetal Gmsh full 3D',
        'units': {'mesh_length': 'mm', 'model_L0': 'm/mm', 'frequency_axis': 'Hz',
                  'conductor_thickness': 'nm', 'capacitance': 'native Palace CSV'},
        'port_convention': {'index_base': 1, 'ordering': 'reviewed SQDMetal creation order',
                            'ports': em['ports'], 'excited_port': em['solver'].get('excited_port'),
                            'note': 'Driven port-S.csv is only the native excited-column output, not a fabricated full S matrix'},
        'frequency_hz': frequency_hz,
        'native_epr_tables': [name for name in native if name.endswith(('port-EPR.csv', 'port-Q.csv', 'domain-E.csv'))],
        'epr_quantization': 'not_performed_requires_reviewed_mode_normalization_and_external_validation',
        'mesh_convergence': {'planned_native_refinement_levels': em['mesh']['refinement_levels'],
                             'requested_relative_tolerance': em['mesh']['relative_tolerance'],
                             'convergence_observed': False},
        'validation_status': 'native_files_checked_not_scientifically_qualified',
        'source_revision': 'worker_result_manifest_only',
    }
    (output / 'a03-native-artifacts.json').write_text(json.dumps(report, indent=2,
                                                               sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    native.append('a03-native-artifacts.json')
    # The frozen worker ABI demands an explicit registered output type; there
    # is no default RESULT_TYPES entry for the SQDMetal/Palace engine.
    result_type = ({'capacitance': 'palace.capacitance_matrix',
                    'eigenmode': 'palace.eigenmodes',
                    'sparameters': 'palace.sparameters'}[study['kind']]
                   if em['execution'] == 'solve' else 'palace.deck')
    return {'engine_version': 'SQDMetal ' + version['sqdmetal'] + '; Gmsh ' + version['gmsh']
            + '; Palace ' + str(version['palace'] or 'deck-only'),
            'native_files': native, 'kind': study['kind'],
            'artifact_type': result_type, 'scientific_status': 'review_required'}
