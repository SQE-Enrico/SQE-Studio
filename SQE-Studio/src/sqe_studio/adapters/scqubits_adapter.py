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

from .base import EngineBlocked, EngineFailure, require_module, safe_output

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
# Only the version explicitly selected by the reviewed Windows sidecar
# requirement is admitted. This is a software compatibility pin, *not* a
# physical benchmark, numerical calibration, or a hash-locked wheel.
SCQUBITS_NUMERICAL_PIN = '4.3.1'


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
    # Exclusive creation: a previous result or symlink cannot be replaced by a
    # second job or a concurrent writer. The worker's RESULT_MANIFEST remains
    # the sole admission gate, not a partially written JSON file.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')


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
    if not isinstance(conv, dict) or set(conv) not in ({'enabled'}, {'enabled', 'tolerance_GHz', 'basis_increment'}, {'enabled', 'tolerance_GHz', 'basis_increment', 'steps'}):
        _blocked('convergence requires enabled and, when enabled, tolerance_GHz/basis_increment')
    if type(conv['enabled']) is not bool:
        _blocked('convergence.enabled must be boolean')
    if conv['enabled']:
        if set(conv) not in ({'enabled', 'tolerance_GHz', 'basis_increment'}, {'enabled', 'tolerance_GHz', 'basis_increment', 'steps'}):
            _blocked('enabled convergence requires tolerance_GHz and basis_increment')
        tol = _number(conv['tolerance_GHz'], 'convergence tolerance_GHz')
        if not 0 < tol <= .5:
            _blocked('convergence tolerance_GHz must be in (0, 0.5]')
        _integer(conv['basis_increment'], 'basis_increment', 1, 6)
        steps = _integer(conv.get('steps', 1), 'convergence.steps', 1, 4)
        if steps > 1 and (model == 'Composite' or sweep is not None):
            _blocked('multistep basis curves require a standalone unswept model')
        for group in groups:
            basis = group['parameters']
            cutoff = 'cutoff' if group['model'] == 'Fluxonium' else 'ncut'
            if basis[cutoff] + conv['basis_increment'] * steps > 80:
                _blocked('convergence expansion exceeds native basis cutoff limit 80')
            if steps == 1 and 'truncated_dim' in basis and basis['truncated_dim'] + conv['basis_increment'] > 16:
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


def _scqubits_sparse_matrix_boundary(spectrum_utils):
    """Scoped bridge for scqubits 4.3.x/SciPy sparse-array interoperability.

    scqubits 4.3.1 accepts legacy sparse matrices at the *internal* HilbertSpace
    bare-Hamiltonian conversion boundary, while SciPy may return csc_array.
    Convert only representation, element-for-element, and restore upstream API
    immediately after the worker's composite solve (including failures).
    The isolated worker runs only one native scientific job at a time.
    """
    from contextlib import contextmanager
    from scipy import sparse

    @contextmanager
    def temporary():
        original = spectrum_utils.convert_operator_to_qobj
        def compatible(operator, subsystem, op_in_eigenbasis, evecs):
            # scqubits 4.3.1 first converts a qutip.Qobj to a SciPy sparse
            # representation *inside* convert_operator_to_qobj. With recent
            # qutip/SciPy, that representation can be csc_array, which 4.3.1
            # subsequently rejects. Normalize at both entrances, not just
            # when the caller provides a sparse array directly.
            qobj_type = spectrum_utils.qt.Qobj
            if isinstance(operator, qobj_type):
                operator = spectrum_utils.Qobj_to_scipy_csc_matrix(operator)
            if isinstance(operator, sparse.sparray):
                operator = sparse.csc_matrix(operator)
            return original(operator, subsystem, op_in_eigenbasis, evecs)
        spectrum_utils.convert_operator_to_qobj = compatible
        try:
            yield
        finally:
            spectrum_utils.convert_operator_to_qobj = original
    return temporary()


def _qobj_compatible_operator(bound_method):
    """Convert only scipy sparse *array* to equivalent sparse matrix.

    scqubits 4.3.x checks for scipy.sparse.csc_matrix/csr_matrix and rejects
    newer sparse arrays. No truncation, symmetrization, rescaling or change of
    matrix elements is performed. This is an adapter-local compatibility shim.
    """
    def operator(*args, **kwargs):
        raw = bound_method(*args, **kwargs)
        from scipy import sparse
        if isinstance(raw, sparse.sparray):
            return sparse.csc_matrix(raw)
        return raw
    # Expose the original bound owner for native API inspection and wiring tests.
    # The numerical data still comes exclusively from this exact bound method.
    operator.__self__ = bound_method.__self__
    return operator


def _native_system(scq, spec, changed=None, increment=0, coupled=True, basis_only=False):
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
            if 'truncated_dim' in args and not basis_only:
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
                                   op1=_qobj_compatible_operator(getattr(a, link['operator_left'])),
                                   op2=_qobj_compatible_operator(getattr(b, link['operator_right'])))
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


def _finite_difference(a, b, label):
    # Two native finite energies can still overflow when differenced. Reject
    # rather than emitting a non-JSON energy, difference or false tolerance.
    difference = a - b
    if not math.isfinite(difference):
        _blocked('native ' + label + ' is nonfinite')
    return difference


def _native_transitions(row):
    return [_finite_difference(e, row[0], 'ground-referenced transition')
            for e in row]


def _basis_curve(scq, spec, base_energies):
    """Repeated upstream eigenvals, not a Hamiltonian or diagonalizer.

    Two final adjacent intervals must meet the saved absolute tolerance. This
    stopping diagnostic is not an error bound, state matching or physical signoff.
    """
    conv = spec['convergence']
    group = spec['groups'][0]
    key = 'cutoff' if group['model'] == 'Fluxonium' else 'ncut'
    base = group['parameters'][key]
    rows = []
    previous = None
    for index in range(conv['steps'] + 1):
        cutoff = base + index * conv['basis_increment']
        values = (base_energies if index == 0 else _eigenvalues(
            _native_system(scq, spec, increment=index * conv['basis_increment'],
                           basis_only=True), spec['levels']))
        transitions = _native_transitions(values)[1:]
        delta = (max(abs(_finite_difference(a, b, 'adjacent basis discrepancy'))
                     for a, b in zip(transitions, previous)) if previous is not None else None)
        f01 = _finite_difference(values[1], values[0], 'f01')
        f12 = (_finite_difference(values[2], values[1], 'f12') if len(values) >= 3 else None)
        rows.append({'basis_cutoff': cutoff,
                     'basis_dimension': cutoff if key == 'cutoff' else 2 * cutoff + 1,
                     'transitions_from_ground_GHz': transitions,
                     'f01_GHz': f01, 'f12_GHz': f12,
                     'anharmonicity_GHz': (_finite_difference(f12, f01, 'anharmonicity')
                                          if f12 is not None else None),
                     'max_adjacent_delta_GHz': delta})
        previous = transitions
    final_delta = max(r['max_adjacent_delta_GHz'] for r in rows[-2:])
    return {'point_index': 0, 'sweep_value': None,
            'base_transitions_GHz': rows[0]['transitions_from_ground_GHz'],
            'expanded_transitions_GHz': rows[-1]['transitions_from_ground_GHz'],
            'absolute_transition_deltas_GHz': [
                abs(_finite_difference(a, b, 'base to final basis discrepancy'))
                for a, b in zip(rows[0]['transitions_from_ground_GHz'],
                                rows[-1]['transitions_from_ground_GHz'])],
            'max_delta_GHz': final_delta, 'basis_parameter': key,
            'status': 'checked_passed' if final_delta <= conv['tolerance_GHz'] else 'checked_failed',
            'criterion': 'last_two_adjacent_ground_referenced_transition_deltas',
            'curve': rows}


def _execute(scq, spec):
    points = spec['sweep']['values'] if spec['sweep'] else [None]
    energies, uncoupled, convergence_points = [], [], []
    for point_index, val in enumerate(points):
        changed = ({spec['sweep']['subsystem']: (spec['sweep']['parameter'], val)}
                   if spec['sweep'] else {})
        system = _native_system(scq, spec, changed=changed)
        row = _eigenvalues(system, spec['levels'])
        _native_transitions(row)
        energies.append(row)
        if spec['model'] == 'Composite':
            unlinked = _native_system(scq, spec, changed=changed, coupled=False)
            uncoupled_row = _eigenvalues(unlinked, spec['levels'])
            _native_transitions(uncoupled_row)
            uncoupled.append(uncoupled_row)
        if spec['convergence']['enabled']:
            if spec['convergence'].get('steps', 1) > 1:
                convergence_points.append(_basis_curve(scq, spec, row))
                continue  # Retain valid native output even when the numeric criterion fails.
            larger = _native_system(scq, spec, changed=changed,
                                    increment=spec['convergence']['basis_increment'])
            expanded = _eigenvalues(larger, spec['levels'])
            base_transitions = _native_transitions(row)[1:]
            expanded_transitions = _native_transitions(expanded)[1:]
            differences = [abs(_finite_difference(a, b, 'basis transition discrepancy'))
                           for a, b in zip(base_transitions, expanded_transitions)]
            delta = max(differences)
            # These are two independently executed native basis solves, NOT
            # a claimed mesh convergence, analytical uncertainty or EPR proof.
            convergence_points.append({
                'point_index': point_index, 'sweep_value': val,
                'base_transitions_GHz': base_transitions,
                'expanded_transitions_GHz': expanded_transitions,
                'absolute_transition_deltas_GHz': differences,
                'max_delta_GHz': delta,
            })
            if delta > spec['convergence']['tolerance_GHz']:
                _blocked(f'native basis convergence failed at point {point_index}: '
                         f'max transition delta {delta:.9g} GHz exceeds '
                         f'{spec["convergence"]["tolerance_GHz"]:.9g} GHz')
    return energies, uncoupled, convergence_points


def run(study, project, output_dir):
    """Execute native spectrum; return the frozen adapter ABI result dictionary."""
    started = time.perf_counter()
    if not isinstance(study, dict) or not isinstance(project, dict):
        _blocked('requires study and immutable project snapshot objects')
    # The adapter never interprets a Josephson RF study, arbitrary engine name,
    # or an unsupported analysis as an equivalent eigenvalue calculation.
    if study.get('engine') != 'scqubits' or study.get('kind') not in ('spectrum', 'quantum_spectrum'):
        _blocked('requires scqubits engine and spectrum/quantum_spectrum study kind')
    inputs = study.get('inputs')
    spec = _spec(inputs, project)
    output = safe_output(output_dir)
    # Check every possible output, including a dangling symlink, BEFORE the
    # potentially expensive native solve. Never replay/overwrite a revision's
    # typed results, even when the native package is unavailable.
    expected_files = ('input_snapshot.json', 'spectrum.json', 'series.json', 'coupling.json')
    if any((output / name).exists() or (output / name).is_symlink() for name in expected_files):
        _blocked('output directory already contains scqubits artifacts; refusing overwrite/replay')
    require_module('scqubits', 'scqubits')
    try:
        import scqubits as scq  # fixed, allowlisted native dependency
    except (ImportError, OSError) as exc:
        raise EngineBlocked('scqubits cannot import its native dependencies: ' + str(exc)) from exc
    try:
        version = metadata.version('scqubits')
    except metadata.PackageNotFoundError as exc:
        raise EngineBlocked('scqubits native package distribution/version is unavailable') from exc
    if version != SCQUBITS_NUMERICAL_PIN:
        _blocked(f'native scqubits version {version!r} is not the pinned '
                 f'{SCQUBITS_NUMERICAL_PIN} software compatibility target')
    # scqubits uses frequency energies in its globally configured units.
    # Isolated worker process: explicitly force the intended GHz convention.
    scq.set_units('GHz')
    if scq.get_units() != 'GHz':
        _blocked('native scqubits did not accept GHz units')
    if spec['model'] == 'Composite':
        # Interaction-bound operators are bridged separately above; this covers
        # internal scqubits identity_wrap / diag_hamiltonian sparse arrays.
        from scqubits.utils import spectrum_utils
        with _scqubits_sparse_matrix_boundary(spectrum_utils):
            energies, uncoupled, convergence_points = _execute(scq, spec)
    else:
        energies, uncoupled, convergence_points = _execute(scq, spec)
    elapsed = time.perf_counter() - started
    model = spec['model']
    sweep = spec['sweep']
    axes = {'parameter': sweep['parameter'], 'subsystem': sweep['subsystem'],
            'unit': sweep['unit'], 'values': sweep['values']} if sweep else None
    transitions = [_native_transitions(row) for row in energies]
    native_versions = {'scqubits': version, 'python': sys.version.split()[0],
                       'scqubits_compatibility_pin': SCQUBITS_NUMERICAL_PIN}
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
                      'qualification_scope': 'native numeric software only; not calibrated EM/EPR or device physics',
                      'cross_engine_mapping': {
                          'status': 'blocked',
                          'reason': 'Independently specified Hamiltonian energies are not '
                                    'EM-derived EJ/EC/EL or revision-mapped RF circuit parameters.'},
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
                 'convergence': {'status': ('checked_failed' if any(p.get('status') == 'checked_failed' for p in convergence_points)
                                           else 'checked_passed' if convergence_points else 'not_checked'),
                                 'criterion': ('last two adjacent native basis expansions: max ground-referenced transition delta'
                                               if spec['convergence'].get('steps', 1) > 1 else
                                               'one native basis expansion: max delta of transitions relative to E0'),
                                'max_delta_GHz': max((p['max_delta_GHz'] for p in convergence_points), default=None),
                                'tolerance_GHz': spec['convergence'].get('tolerance_GHz'),
                                'basis_increment': spec['convergence'].get('basis_increment'),
                                'checked_points': len(convergence_points),
                                'points': convergence_points,
                                'scientific_scope': 'single-step sorted-energy-index basis comparison only; '
                                    'no eigenstate-overlap identity or independent scientific qualification'},
                'source': 'native scqubits eigenvals',
                'scientific_status': 'review_required', 'elapsed_seconds': elapsed,
                'input_sha256': input_snapshot['input_sha256']}
    if spec['convergence'].get('steps', 1) > 1:
        spectrum['convergence']['steps'] = spec['convergence']['steps']
        spectrum['convergence']['numeric_status'] = ('NUMERICAL_PASS' if spectrum['convergence']['status'] == 'checked_passed'
                                                      else 'NUMERICAL_FAIL')
        spectrum['convergence']['scientific_scope'] = (
            'Finite cutoff stability of sorted ground-referenced transitions; no rigorous error bound, '
            'eigenstate identity, experimental agreement, EM transfer or physical qualification. '
            'The ordinary spectrum uses the saved base cutoff; the curve records every evaluated cutoff.')
    metadata_series = {'schema': 'sqe.scqubits.series.v1',
                       'artifact_type': 'scqubits.spectrum.series',
                       'axis': axes or {'parameter': 'index', 'unit': '1', 'values': [0]},
                       'series': series, 'source': 'native scqubits eigenvalues',
                       'input_sha256': input_snapshot['input_sha256'],
                       'scientific_status': 'review_required'}
    # Compute all derived native spectra and finite coupled-minus-uncoupled
    # differences BEFORE writing *any* result artifact. Previously overflow in
    # a late coupling difference left plausible spectrum/series files behind.
    coupling = None
    if model == 'Composite':
        coupling = {'schema': 'sqe.scqubits.coupling.v1',
                    'artifact_type': 'scqubits.coupling',
                    'interactions': spec['interactions'],
                    'subsystems': [g['id'] for g in spec['groups']],
                    'uncoupled_native_energy_table_GHz': uncoupled,
                    'coupled_native_energy_table_GHz': energies,
                    'dressed_minus_uncoupled_energy_GHz': [
                        [_finite_difference(a, b, 'dressed-minus-uncoupled energy')
                         for a, b in zip(row, bare)]
                        for row, bare in zip(energies, uncoupled)],
                    'interpretation': 'Native coupled-vs-uncoupled spectral comparison; '
                                      'not measured coupling, an EPR extraction, or fitted g.',
                    'scientific_status': 'review_required'}
    # Validate serialization of the complete set before creating any files.
    # In particular allow_nan=False blocks output of invalid native quantities.
    artifacts = {'input_snapshot.json': input_snapshot, 'spectrum.json': spectrum,
                 'series.json': metadata_series}
    if coupling is not None:
        artifacts['coupling.json'] = coupling
    for document in artifacts.values():
        _canonical(document)
    for filename, document in artifacts.items():
        _write(output / filename, document)
    files = list(artifacts)
    return {'engine_version': version, 'native_files': files,
            'kind': 'quantum_spectrum', 'scientific_status': 'review_required'}


# RC14.10 B08: a callable native benchmark for the one-click A15 runner. It
# uses the same production run() path, never a surrogate eigenvalue solver.
# The curated studies have independent (not EM-extracted) Hamiltonian inputs.
def _b08_native_studies():
    """Bounded exploratory Transmon and Fluxonium sweeps, GHz / Phi0 / 2e."""
    cases = (
        ('transmon', 'Transmon', {'EJ': 15., 'EC': .25, 'ng': 0.,
                                 'ncut': 12, 'truncated_dim': 6},
         'ng', [0., .5, 1.], '2e', 'ncut'),
        ('fluxonium', 'Fluxonium', {'EJ': 8., 'EC': 2., 'EL': .5,
                                   'flux': 0., 'cutoff': 24, 'truncated_dim': 6},
         'flux', [0., .5, 1.], 'Phi0', 'cutoff'),
    )
    for label, model, parameters, field, values, unit, cutoff in cases:
        for step in (0, 2):
            params = dict(parameters)
            params[cutoff] += step
            inputs = {
                'model': model, 'source': 'independent', 'levels': 3,
                'parameters': params,
                'parameter_units': {key: _unit(key) for key in params},
                'sweep': {'subsystem': 'primary', 'parameter': field,
                          'values': values[:], 'unit': unit},
                'convergence': {'enabled': True, 'basis_increment': 2,
                                'tolerance_GHz': .5},
            }
            yield label + '_cutoff_plus_' + str(step), {
                'id': 'A16-B08-' + label + '-' + str(step),
                'engine': 'scqubits', 'kind': 'quantum_spectrum', 'inputs': inputs,
            }



def _b08_cutoff_start_comparison(studies, tolerance_GHz=0.5):
    """Compare independent native transition tables at two initial cutoffs.

    This is a numerical diagnostic, NOT state tracking or convergence proof.
    Inputs must be native result observations gathered by benchmark_b08; tests
    of this helper with invented tables are parser fixtures, not native runs.
    """
    result = {}
    for model in ('transmon', 'fluxonium'):
        base = studies[model + '_cutoff_plus_0']
        expanded = studies[model + '_cutoff_plus_2']
        a = base['sweep_transitions_GHz']
        b = expanded['sweep_transitions_GHz']
        if (base['units'] != expanded['units'] or
                base['sweep_values'] != expanded['sweep_values'] or
                expanded['cutoff'] != base['cutoff'] + 2 or
                len(a) != 3 or len(b) != 3):
            raise EngineFailure('B08 independent cutoff runs are not comparable')
        per_point = []
        for first, second in zip(a, b):
            if len(first) != 2 or len(second) != 2:
                raise EngineFailure('B08 requires exactly two native transitions per sweep point')
            discrepancies = [abs(_finite_difference(x, y, 'B08 cutoff-start transition'))
                             for x, y in zip(first, second)]
            per_point.append(max(discrepancies))
        worst = max(per_point)
        result[model] = {
            'starting_cutoffs': [base['cutoff'], expanded['cutoff']],
            'per_sweep_max_delta_GHz': per_point,
            'max_delta_GHz': worst,
            'diagnostic_tolerance_GHz': tolerance_GHz,
            'numerical_screen': ('within_diagnostic_tolerance_NOT_PROOF' if worst <= tolerance_GHz
                                 else 'BLOCKED_CUTOFF_START_DISAGREEMENT'),
            'qualification': 'BLOCKED_NO_EIGENSTATE_OVERLAP_OR_EM_EPR_REFERENCE',
        }
    return result


def benchmark_b08(output_dir):
    """Run real native B08 spectra in a NEW dedicated directory.

    A15 can invoke this function in an isolated worker and map EngineBlocked to
    BLOCKED, never PASS. A completed benchmark still needs independently
    qualified Hamiltonian provenance, mode and level identity, and metrology.
    There are four native production jobs (two cutoff starts per model), each
    with its own two-basis sorted-transition comparison at three sweep points.
    """
    from pathlib import Path
    from sqe_studio.contracts import fresh_project

    # Probe availability before creating any benchmark artifact.
    require_module('scqubits', 'scqubits')
    try:
        installed = metadata.version('scqubits')
    except metadata.PackageNotFoundError as exc:
        raise EngineBlocked('B08: scqubits distribution/version unavailable') from exc
    if installed != SCQUBITS_NUMERICAL_PIN:
        _blocked('B08 requires pinned native scqubits ' + SCQUBITS_NUMERICAL_PIN)
    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        _blocked('B08 requires a fresh non-existing case directory; refusing replay')
    output.mkdir(parents=True, exist_ok=False)
    observed = {}
    benchmark_started = time.perf_counter()
    for label, study in _b08_native_studies():
        job_started = time.perf_counter()
        cpu_started = time.process_time()
        project = fresh_project('A16 exploratory ' + label, 'transmon' if label.startswith('transmon') else 'fluxonium')
        dest = output / label
        native = run(study, project, dest)
        with (dest / 'spectrum.json').open(encoding='utf-8') as stream:
            spectrum = json.load(stream)
        with (dest / 'input_snapshot.json').open(encoding='utf-8') as stream:
            snapshot = json.load(stream)
        conv = spectrum['convergence']
        native_wall = time.perf_counter() - job_started
        native_cpu = time.process_time() - cpu_started
        if (native['engine_version'] != installed or
                spectrum['scientific_status'] != 'review_required' or
                snapshot['cross_engine_mapping']['status'] != 'blocked' or
                snapshot['input_sha256'] != _sha(study['inputs']) or
                snapshot['project_sha256'] != _sha(project) or
                conv['status'] != 'checked_passed' or conv['checked_points'] != 3 or
                len(spectrum['energy_table']) != 3 or
                spectrum['engine_version'] != installed or
                spectrum['energy_unit'] != 'GHz' or
                spectrum['axis']['values'] != [0., .5, 1.] or
                spectrum['axis']['unit'] != ('2e' if label.startswith('transmon') else 'Phi0') or
                spectrum['basis'][0]['model'] != ('Transmon' if label.startswith('transmon') else 'Fluxonium') or
                spectrum['basis'][0].get('ncut', spectrum['basis'][0].get('cutoff')) !=
                    study['inputs']['parameters'].get('ncut', study['inputs']['parameters'].get('cutoff')) or
                spectrum['elapsed_seconds'] < 0 or not math.isfinite(spectrum['elapsed_seconds'])):
            raise EngineFailure('B08 native result missing required revision/unit/convergence evidence')
        # Periodicity in transition energies, not absolute gauge-dependent E0.
        first, last = ([_finite_difference(e, row[0], 'B08 periodicity transition')
                        for e in row[1:]]
                       for row in (spectrum['energy_table'][0], spectrum['energy_table'][-1]))
        periodicity = max(abs(_finite_difference(a, b, 'B08 periodicity delta'))
                          for a, b in zip(first, last))
        observed[label] = {
            'native_engine_version': installed,
            'study_wall_seconds': native_wall,
            'study_python_cpu_seconds': native_cpu,
            'native_adapter_elapsed_seconds': spectrum['elapsed_seconds'],
            'sweep_values': spectrum['axis']['values'],
            'sweep_transitions_GHz': [
                [_finite_difference(v, row[0], 'B08 native transition') for v in row[1:]]
                for row in spectrum['energy_table']],
            'input_sha256': snapshot['input_sha256'],
            'project_sha256': snapshot['project_sha256'],
            'units': {'energies': 'E/h GHz', 'sweep': spectrum['axis']['unit']},
            'native_result_sha256': {name: hashlib.sha256((dest / name).read_bytes()).hexdigest()
                                     for name in native['native_files']},
            'maximum_basis_delta_GHz': conv['max_delta_GHz'],
            'basis_increment': conv['basis_increment'],
            'cutoff': spectrum['basis'][0].get('ncut', spectrum['basis'][0].get('cutoff')),
            'periodicity_transition_delta_GHz': periodicity,
            'periodicity_screen': 'within_0.05_GHz' if periodicity <= .05 else 'REVIEW_REQUIRED',
            'limits': 'sorted index only; no eigenstate overlap, EM/EPR, physical uncertainty',
        }
    report = {'schema': 'sqe.A16.native-benchmark.v1', 'case_id': 'B08',
              'execution_kind': 'NATIVE_SCQUBITS', 'stage_status': 'BLOCKED_SCIENTIFIC_REVIEW',
              'native_version': installed, 'studies': observed,
              'cutoff_start_comparison': _b08_cutoff_start_comparison(observed),
              'execution_resources': {
                  'native_jobs_completed': len(observed), 'native_jobs_sequential': True,
                  'total_wall_seconds': time.perf_counter() - benchmark_started,
                  'basis_cutoff_max': 80, 'hilbert_dimension_max': MAX_COMPOSITE_DIM,
                  'sweep_points_per_study': 3, 'levels_per_study': 3,
                  'cpu_counter_scope': 'Python worker process; wall includes native scqubits call',
                  'peak_memory_bytes': None, 'peak_memory_status': 'NOT_MEASURED',
                  'hard_deadline_status': 'NOT_ENFORCED_IN_ADAPTER_A15_ISOLATED_WORKER_REQUIRED',
              },
              'limitations': ['independent EJ/EC/EL, not EM extracted',
                              'no numerical independent reference or eigenstate-overlap identity',
                              'single-step basis tests at two cutoff starts are not proof of convergence',
                              'fabrication HOLD']}
    _canonical(report)
    _write(output / 'benchmark_B08.json', report)
    return report
