"""Bounded native scqubits spectra with explicit Hamiltonian provenance.

Only allowlisted native objects/operators are constructed.  In particular this
adapter does *not* turn EM data into a Hamiltonian: that requires an A01 trusted
lineage/quantization contract, which the frozen v1 worker ABI cannot convey.
"""
from __future__ import annotations

import hashlib
import json
import math
import numbers
import sys
import time
from importlib import metadata

from .base import EngineBlocked, require_module, safe_output

# These are parameter names on the scqubits 4.x constructors, not inferred CAD
# quantities. Energy parameters are frequencies E/h in GHz, never Joules.
MODELS = {
    'Transmon': {'required': {'EJ', 'EC', 'ng', 'ncut'},
                 'allowed': {'EJ', 'EC', 'ng', 'ncut', 'truncated_dim'}},
    'Fluxonium': {'required': {'EJ', 'EC', 'EL', 'flux', 'cutoff'},
                  'allowed': {'EJ', 'EC', 'EL', 'flux', 'cutoff', 'truncated_dim'}},
    'TunableTransmon': {'required': {'EJmax', 'EC', 'd', 'flux', 'ng', 'ncut'},
                        'allowed': {'EJmax', 'EC', 'd', 'flux', 'ng', 'ncut', 'truncated_dim'}},
}
ENERGIES = {'EJ', 'EC', 'EL', 'EJmax', 'E_osc', 'g'}
DIMENSIONS = {'ncut', 'cutoff', 'truncated_dim'}
SWEEPABLE = {
    'Transmon': {'EJ', 'EC', 'ng'},
    'Fluxonium': {'EJ', 'EC', 'EL', 'flux'},
    'TunableTransmon': {'EJmax', 'EC', 'flux', 'ng', 'd'},
}
OPERATORS = {'n_operator'}  # hermitian charge-charge interaction, no expressions
MAX_POINTS = 21
MAX_COMPOSITE_DIM = 144
MAX_LEVELS = 12


def _blocked(reason):
    raise EngineBlocked('scqubits input blocked: ' + reason)


def _number(value, name):
    if type(value) not in (int, float):
        _blocked(name + ' must be a finite number (not a boolean)')
    try:
        if not math.isfinite(value):
            _blocked(name + ' must be finite')
        return float(value)
    except (OverflowError, ValueError):
        _blocked(name + ' exceeds the finite numeric range')


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        _blocked(f'{name} must be an integer in [{minimum}, {maximum}]')
    return value


def _canonical(obj):
    try:
        return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, OverflowError) as exc:
        _blocked('non-JSON or nonfinite input: ' + type(exc).__name__)


def _sha(obj):
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n',
                    encoding='utf-8')


def _unit(field):
    if field in ENERGIES:
        return 'GHz'
    if field == 'flux':
        return 'Phi0'
    if field == 'ng':
        return '2e'
    return '1'


def _check_unit(field, unit, name):
    if type(unit) is not str or unit != _unit(field):
        _blocked(f'{name} must use explicit unit {_unit(field)!r}; no silent conversions')


def _parameters(model, values, units, name, composite=False):
    if type(model) is not str or model not in MODELS:
        _blocked(f'{name} has unsupported model {model!r}')
    fields = MODELS[model]
    if not isinstance(values, dict) or not fields['required'] <= set(values) or set(values) - fields['allowed']:
        _blocked(f'{name} requires {sorted(fields["required"])} and no unsupported parameters')
    if units is not None:
        if not isinstance(units, dict) or set(units) != set(values):
            _blocked(f'{name}.parameter_units must name exactly the supplied parameters')
        for key, unit in units.items():
            _check_unit(key, unit, name + '.' + key)
    result = {}
    for key, raw in values.items():
        if key in DIMENSIONS:
            result[key] = _integer(raw, name + '.' + key, 3 if key != 'truncated_dim' else 2,
                                   80 if key != 'truncated_dim' else 16)
        else:
            val = _number(raw, name + '.' + key)
            if key in ENERGIES and not 0 < val <= 1000:
                _blocked(name + '.' + key + ' must be positive and <= 1000 GHz')
            if key == 'flux' and not 0 <= val <= 1:
                _blocked(name + '.flux must be normalized to the range [0, 1] Phi0')
            if key == 'd' and not 0 <= val < 1:
                _blocked(name + '.d must be in [0, 1)')
            if key == 'ng' and not -10 <= val <= 10:
                _blocked(name + '.ng outside bounded offset-charge range [-10, 10]')
            result[key] = val
    if model == 'Fluxonium' and 'truncated_dim' in result and result['truncated_dim'] > result['cutoff']:
        _blocked(name + '.truncated_dim cannot exceed Fluxonium cutoff')
    if model != 'Fluxonium' and 'truncated_dim' in result and result['truncated_dim'] > 2 * result['ncut'] + 1:
        _blocked(name + '.truncated_dim exceeds charge basis dimension')
    if composite and 'truncated_dim' not in result:
        _blocked(name + ': composite subsystems require explicit truncated_dim')
    return result


def _check_stale(inputs, project):
    # The project context digest intentionally excludes studies, so the binding
    # does not contain its own hash. It does not claim revision authentication;
    # the immutable revision binding remains the responsibility of Jobs/worker.
    context = {key: project[key] for key in ('schematic', 'layout', 'process')}
    observed = _sha(context)
    expected = inputs.get('context_sha256')
    if expected is not None and (type(expected) is not str or expected != observed):
        _blocked('stale schematic/layout/process context_sha256; resave reviewed inputs')
    snapshot_expected = inputs.get('input_sha256')
    if snapshot_expected is not None:
        actual = _sha({k: v for k, v in inputs.items() if k != 'input_sha256'})
        if type(snapshot_expected) is not str or snapshot_expected != actual:
            _blocked('stale input_sha256; the saved Hamiltonian input changed')
    return observed


def _source(inputs):
    source = inputs.get('source', 'independent')
    if source != 'independent':
        _blocked('EM-derived/engine-derived parameters require trusted A01 verified '
                 'quantity lineage, units and revision proof; unavailable in frozen v1 ABI')
    # A manually supplied statement of verification is not a trusted A01 proof.
    for suspicious in ('em_artifact', 'lineage', 'extraction', 'verified_em',
                       'em_quantity', 'derived_from', 'quantity_evidence'):
        if suspicious in inputs:
            _blocked(suspicious + ' cannot self-certify derived Hamiltonian inputs')
    return source


def _spec(inputs, project):
    if not isinstance(inputs, dict):
        _blocked('inputs must be a declarative object')
    allowed = {'model', 'parameters', 'parameter_units', 'levels', 'source',
               'subsystems', 'interactions', 'sweep', 'convergence',
               'context_sha256', 'input_sha256'}
    if set(inputs) - allowed:
        _blocked('unknown input keys: ' + repr(sorted(set(inputs) - allowed)))
    source = _source(inputs)
    context_sha = _check_stale(inputs, project)
    levels = _integer(inputs.get('levels', 5), 'levels', 2, MAX_LEVELS)
    model = inputs.get('model')
    if model == 'Composite':
        if 'parameters' in inputs or 'parameter_units' in inputs:
            _blocked('Composite uses only subsystems (not top-level parameters)')
        raw_subsystems = inputs.get('subsystems')
        if not isinstance(raw_subsystems, list) or not 2 <= len(raw_subsystems) <= 3:
            _blocked('Composite requires two or three explicit subsystems')
        subsystems = []
        for index, row in enumerate(raw_subsystems):
            if not isinstance(row, dict) or set(row) != {'id', 'model', 'parameters', 'parameter_units'}:
                _blocked('each Composite subsystem needs id, model, parameters, parameter_units')
            ident = row['id']
            if (type(ident) is not str or not ident.isascii() or len(ident) > 32 or
                    not ident or not ident[0].isalpha() or
                    not all(c.isalnum() or c == '_' for c in ident)):
                _blocked('subsystem ids must be short ASCII identifiers')
            if ident in [r['id'] for r in subsystems]:
                _blocked('duplicate subsystem id: ' + ident)
            params = _parameters(row['model'], row['parameters'], row['parameter_units'],
                                 f'subsystems[{index}]', composite=True)
            subsystems.append({'id': ident, 'model': row['model'], 'parameters': params})
        dim = math.prod(s['parameters']['truncated_dim'] for s in subsystems)
        if dim > MAX_COMPOSITE_DIM or levels > dim:
            _blocked(f'composite dimension {dim} exceeds bound {MAX_COMPOSITE_DIM} or levels')
        interactions = inputs.get('interactions')
        if not isinstance(interactions, list) or not 1 <= len(interactions) <= 3:
            _blocked('Composite requires one to three explicitly defined interactions')
        links = []
        ids = {s['id'] for s in subsystems}
        for idx, item in enumerate(interactions):
            expected = {'left', 'right', 'operator_left', 'operator_right', 'g', 'unit'}
            if not isinstance(item, dict) or set(item) != expected:
                _blocked('interaction requires left, right, operator_left, operator_right, g, unit')
            if (type(item['left']) is not str or type(item['right']) is not str or
                    item['left'] not in ids or item['right'] not in ids or item['left'] == item['right']):
                _blocked('interaction refers to unknown or identical subsystems')
            if (type(item['operator_left']) is not str or type(item['operator_right']) is not str or
                    item['operator_left'] not in OPERATORS or item['operator_right'] not in OPERATORS):
                _blocked('only allowlisted charge n_operator x n_operator coupling is supported')
            _check_unit('g', item['unit'], f'interactions[{idx}].unit')
            g = _number(item['g'], 'interaction.g')
            if not -100 <= g <= 100:
                _blocked('interaction.g exceeds +/-100 GHz bound')
            links.append({**item, 'g': g})
        groups = subsystems
    else:
        if 'subsystems' in inputs or 'interactions' in inputs:
            _blocked('standalone models cannot declare composite subsystems/interactions')
        parameters = _parameters(model, inputs.get('parameters'),
                                 inputs.get('parameter_units'), 'parameters')
        # The standalone legacy shape omits truncated_dim. Resolve a safe,
        # deterministic basis (scqubits commonly defaults to 6); record it in
        # the typed result, never mistake the implicit basis for a user choice.
        if 'truncated_dim' not in parameters:
            parameters['truncated_dim'] = max(6, levels)
        available = (parameters['cutoff'] if model == 'Fluxonium'
                     else 2 * parameters['ncut'] + 1)
        if parameters['truncated_dim'] > available or levels > parameters['truncated_dim']:
            _blocked('requested levels/truncated_dim exceed native basis dimension')
        groups = [{'id': 'primary', 'model': model, 'parameters': parameters}]
        links = []
        dim = None
    sweep = inputs.get('sweep')
    if sweep is not None:
        if not isinstance(sweep, dict) or set(sweep) != {'subsystem', 'parameter', 'values', 'unit'}:
            _blocked('sweep must contain subsystem, parameter, values and unit')
        match = [g for g in groups if g['id'] == sweep['subsystem']]
        if (len(match) != 1 or type(sweep['parameter']) is not str or
                sweep['parameter'] not in SWEEPABLE[match[0]['model']]):
            _blocked('sweep target/model parameter is not supported')
        field = sweep['parameter']
        _check_unit(field, sweep['unit'], 'sweep.unit')
        if not isinstance(sweep['values'], list) or not 2 <= len(sweep['values']) <= MAX_POINTS:
            _blocked('sweep must have 2 to 21 explicitly saved values')
        values = []
        for val in sweep['values']:
            v = _number(val, 'sweep value')
            # Same parameter constraints and type checks as the initial model.
            trial = dict(match[0]['parameters'], **{field: v})
            _parameters(match[0]['model'], trial, None, 'sweep point')
            values.append(v)
        sweep = {'subsystem': sweep['subsystem'], 'parameter': field,
                 'unit': sweep['unit'], 'values': values}
    conv = inputs.get('convergence', {'enabled': False})
    if not isinstance(conv, dict) or set(conv) not in ({'enabled'}, {'enabled', 'tolerance_GHz', 'basis_increment'}):
        _blocked('convergence requires enabled and, when enabled, tolerance_GHz/basis_increment')
    if type(conv['enabled']) is not bool:
        _blocked('convergence.enabled must be boolean')
    if conv['enabled']:
        if set(conv) != {'enabled', 'tolerance_GHz', 'basis_increment'}:
            _blocked('enabled convergence requires tolerance_GHz and basis_increment')
        tol = _number(conv['tolerance_GHz'], 'convergence tolerance_GHz')
        if not 0 < tol <= .5:
            _blocked('convergence tolerance_GHz must be in (0, 0.5]')
        _integer(conv['basis_increment'], 'basis_increment', 1, 6)
        for group in groups:
            basis = group['parameters']
            cutoff = 'cutoff' if group['model'] == 'Fluxonium' else 'ncut'
            if basis[cutoff] + conv['basis_increment'] > 80:
                _blocked('convergence expansion exceeds native basis cutoff limit 80')
            if 'truncated_dim' in basis and basis['truncated_dim'] + conv['basis_increment'] > 16:
                _blocked('convergence expansion exceeds truncated_dim 16')
        if model == 'Composite':
            expanded = math.prod(g['parameters']['truncated_dim'] + conv['basis_increment'] for g in groups)
            if expanded > MAX_COMPOSITE_DIM:
                _blocked('convergence expansion exceeds composite Hilbert dimension budget')
    elif set(conv) != {'enabled'}:
        _blocked('disabled convergence accepts only enabled:false')
    return {'model': model, 'groups': groups, 'interactions': links, 'levels': levels,
            'sweep': sweep, 'convergence': conv, 'source': source,
            'context_sha256': context_sha, 'composite_dim': dim}


def _native_system(scq, spec, changed=None, increment=0, coupled=True):
    """Construct allowlisted native objects; no evaluated code or user import paths."""
    changed = changed or {}
    native = {}
    for group in spec['groups']:
        args = dict(group['parameters'])
        if group['id'] in changed:
            key, val = changed[group['id']]
            args[key] = val
        if increment:
            cutoff = 'cutoff' if group['model'] == 'Fluxonium' else 'ncut'
            args[cutoff] += increment
            if 'truncated_dim' in args:
                args['truncated_dim'] += increment
        native[group['id']] = getattr(scq, group['model'])(**args)
    if spec['model'] != 'Composite':
        return native['primary']
    system = scq.HilbertSpace([native[g['id']] for g in spec['groups']])
    if coupled:
        for link in spec['interactions']:
            a, b = native[link['left']], native[link['right']]
            # Callable native bound methods avoid expression-string evaluation.
            system.add_interaction(g=link['g'],
                                   op1=getattr(a, link['operator_left']),
                                   op2=getattr(b, link['operator_right']))
    return system


def _eigenvalues(system, count):
    result = []
    for energy in system.eigenvals(evals_count=count):
        # Native arrays often contain numpy.float32/64 scalars rather than Python
        # floats. Accept Real, but reject complex eigenvalues and nonfinite output.
        if not isinstance(energy, numbers.Real) or isinstance(energy, (bool,)):
            _blocked('native scqubits eigenenergy is not real')
        try:
            value = float(energy)
        except (TypeError, OverflowError, ValueError):
            _blocked('native scqubits eigenenergy cannot be represented as float')
        if not math.isfinite(value):
            _blocked('native scqubits returned nonfinite eigenenergy')
        result.append(value)
    if len(result) != count or any(result[i] > result[i + 1] for i in range(len(result) - 1)):
        _blocked('native scqubits returned wrong eigenvalue count or unordered energies')
    return result


def _execute(scq, spec):
    points = spec['sweep']['values'] if spec['sweep'] else [None]
    energies, uncoupled, convergence_deltas = [], [], []
    for val in points:
        changed = ({spec['sweep']['subsystem']: (spec['sweep']['parameter'], val)}
                   if spec['sweep'] else {})
        system = _native_system(scq, spec, changed=changed)
        row = _eigenvalues(system, spec['levels'])
        energies.append(row)
        if spec['model'] == 'Composite':
            unlinked = _native_system(scq, spec, changed=changed, coupled=False)
            uncoupled.append(_eigenvalues(unlinked, spec['levels']))
        if spec['convergence']['enabled']:
            larger = _native_system(scq, spec, changed=changed,
                                    increment=spec['convergence']['basis_increment'])
            expanded = _eigenvalues(larger, spec['levels'])
            delta = max(abs((row[i] - row[0]) - (expanded[i] - expanded[0]))
                        for i in range(1, spec['levels']))
            convergence_deltas.append(delta)
            if delta > spec['convergence']['tolerance_GHz']:
                _blocked(f'native basis convergence failed at point {len(energies) - 1}: '
                         f'max transition delta {delta:.9g} GHz exceeds '
                         f'{spec["convergence"]["tolerance_GHz"]:.9g} GHz')
    return energies, uncoupled, convergence_deltas


def run(study, project, output_dir):
    """Execute native spectrum; return the frozen adapter ABI result dictionary."""
    started = time.perf_counter()
    if not isinstance(study, dict) or not isinstance(project, dict):
        _blocked('requires study and immutable project snapshot objects')
    inputs = study.get('inputs')
    spec = _spec(inputs, project)
    require_module('scqubits', 'scqubits')
    try:
        import scqubits as scq  # fixed, allowlisted native dependency
    except (ImportError, OSError) as exc:
        raise EngineBlocked('scqubits cannot import its native dependencies: ' + str(exc)) from exc
    version = metadata.version('scqubits')
    try:
        major, minor = (int(part) for part in version.split('.')[:2])
    except (ValueError, TypeError):
        _blocked('cannot parse native scqubits version ' + repr(version))
    if major != 4 or minor < 3:
        _blocked(f'native scqubits version {version} is outside the supported >=4.3,<5 range')
    # scqubits uses frequency energies in its globally configured units.
    # Isolated worker process: explicitly force the intended GHz convention.
    scq.set_units('GHz')
    if scq.get_units() != 'GHz':
        _blocked('native scqubits did not accept GHz units')
    energies, uncoupled, deltas = _execute(scq, spec)
    elapsed = time.perf_counter() - started
    model = spec['model']
    sweep = spec['sweep']
    axes = {'parameter': sweep['parameter'], 'subsystem': sweep['subsystem'],
            'unit': sweep['unit'], 'values': sweep['values']} if sweep else None
    transitions = [[e - row[0] for e in row] for row in energies]
    native_versions = {'scqubits': version, 'python': sys.version.split()[0]}
    for package in ('numpy', 'scipy', 'qutip'):
        try:
            native_versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            native_versions[package] = 'distribution-metadata-unavailable'
    input_snapshot = {'schema': 'sqe.scqubits.input-snapshot.v1',
                      'native_versions': native_versions,
                      'study_id': study.get('id'), 'study_sha256': _sha(study),
                      'project_sha256': _sha(project),
                      'context_sha256': spec['context_sha256'],
                      'input_sha256': _sha(inputs),
                      'source': spec['source'], 'unit_convention': 'E/h in GHz',
                      'parameter_units_explicit': ('parameter_units' in inputs if model != 'Composite' else True),
                      'input': inputs,
                      'resolved_basis': [
                          {'id': g['id'], **{k: v for k, v in g['parameters'].items()
                                           if k in DIMENSIONS}} for g in spec['groups']]}
    series = [{'id': f'E{i}', 'quantity': 'absolute_eigenenergy', 'unit': 'GHz',
               'values': [row[i] for row in energies]}
              for i in range(spec['levels'])]
    series += [{'id': f'f0{i}', 'quantity': 'transition_from_ground', 'unit': 'GHz',
                'values': [row[i] for row in transitions]}
               for i in range(1, spec['levels'])]
    spectrum = {'schema': 'sqe.scqubits.spectrum.v1', 'artifact_type': 'scqubits.spectrum',
                'engine': 'scqubits', 'engine_version': version,
                'model': model, 'energy_unit': 'GHz', 'units': 'GHz', 'axis': axes,
                'basis': [{**{'id': g['id'], 'model': g['model']},
                           **{k: v for k, v in g['parameters'].items() if k in DIMENSIONS}}
                          for g in spec['groups']],
                'levels': energies[0],  # foundation UI previews point zero only
                'preview_point_index': 0,
                'energy_table': energies,
                'convergence': {'status': 'checked_passed' if deltas else 'not_checked',
                                'criterion': 'max delta of transitions relative to E0',
                                'max_delta_GHz': max(deltas) if deltas else None,
                                'tolerance_GHz': spec['convergence'].get('tolerance_GHz'),
                                'basis_increment': spec['convergence'].get('basis_increment'),
                                'checked_points': len(deltas)},
                'source': 'native scqubits eigenvals',
                'scientific_status': 'review_required', 'elapsed_seconds': elapsed,
                'input_sha256': input_snapshot['input_sha256']}
    metadata_series = {'schema': 'sqe.scqubits.series.v1',
                       'artifact_type': 'scqubits.spectrum.series',
                       'axis': axes or {'parameter': 'index', 'unit': '1', 'values': [0]},
                       'series': series, 'source': 'native scqubits eigenvalues',
                       'input_sha256': input_snapshot['input_sha256'],
                       'scientific_status': 'review_required'}
    output = safe_output(output_dir)
    _write(output / 'input_snapshot.json', input_snapshot)
    _write(output / 'spectrum.json', spectrum)
    _write(output / 'series.json', metadata_series)
    files = ['input_snapshot.json', 'spectrum.json', 'series.json']
    if model == 'Composite':
        coupling = {'schema': 'sqe.scqubits.coupling.v1',
                    'artifact_type': 'scqubits.coupling',
                    'interactions': spec['interactions'],
                    'subsystems': [g['id'] for g in spec['groups']],
                    'uncoupled_native_energy_table_GHz': uncoupled,
                    'coupled_native_energy_table_GHz': energies,
                    'dressed_minus_uncoupled_energy_GHz': [
                        [a - b for a, b in zip(row, bare)]
                        for row, bare in zip(energies, uncoupled)],
                    'interpretation': 'Native coupled-vs-uncoupled spectral comparison; '
                                      'not measured coupling, an EPR extraction, or fitted g.',
                    'scientific_status': 'review_required'}
        _write(output / 'coupling.json', coupling)
        files.append('coupling.json')
    return {'engine_version': version, 'native_files': files,
            'kind': 'quantum_spectrum', 'scientific_status': 'review_required'}
