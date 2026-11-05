"""Execute the licensed, unmodified upstream benchmark against published values."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

from ..adapters.sqdmetal_palace_adapter import _palace_readiness, _run_palace
from ..interop.native_capacitance_evidence import parse_native_capacitance_table

_INPUTS = {
    'spheres.json': 'cb60f7e015277808123fa3f845635afbc795e78e72b1f5024cb6acfcb34819d5',
    'mesh/spheres.msh': '0c1612c70c4644db8085c72a2f6dbaf739a59971cba10bc5423f984e7b6a9988',
}
_REFERENCE = [[1.230518e-12, -.4945668e-12], [-.4945668e-12, 2.431543e-12]]
_TOLERANCE = .05


def verify_inputs(source):
    source = Path(source)
    for name, expected in _INPUTS.items():
        path = source / name
        if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('OFFICIAL_SPHERES_INPUT_CHANGED: ' + name)
    reference = json.loads((source / 'REFERENCE.json').read_bytes())
    if (reference.get('analytic_matrix_F') != _REFERENCE
            or reference.get('entry_relative_tolerance') != _TOLERANCE
            or reference.get('expected_palace_git_prefix') != '869ee5c'):
        raise ValueError('OFFICIAL_SPHERES_REFERENCE_OR_PREDECLARED_TOLERANCE_CHANGED')
    return reference


def run_reference(root, folder):
    source = Path(root) / 'tests/fixtures/palace_spheres_0_16'
    reference = verify_inputs(source)
    folder = Path(folder)
    shutil.copytree(source, folder)
    print('NATIVE_TRANSMON_STAGE official_spheres_before_solve tolerance=0.05', flush=True)
    completion = _run_palace(_palace_readiness(), folder, 'spheres.json', 1)
    metadata = json.loads((folder / 'postpro/palace.json').read_bytes())
    git_tag = metadata.get('GitTag')
    if type(git_tag) is not str or not git_tag.startswith(reference['expected_palace_git_prefix']):
        raise ValueError('PALACE_RUNTIME_DOES_NOT_MATCH_PINNED_UPSTREAM_EXAMPLE')
    matrix, unit = parse_native_capacitance_table(folder / 'postpro/terminal-C.csv', count=2, expected_unit='F')
    observed = [[float(value) for value in row] for row in matrix]
    errors = [[abs(observed[i][j] / _REFERENCE[i][j] - 1) for j in range(2)] for i in range(2)]
    okay = all(error <= _TOLERANCE for row in errors for error in row)
    result = {'status': 'PASS' if okay else 'FAIL', 'execution_kind': 'NATIVE_PALACE',
        'reference': reference['upstream_reference'], 'palace_git_tag': git_tag,
        'native_execution': completion, 'matrix_F': observed, 'analytic_matrix_F': _REFERENCE,
        'relative_errors': errors, 'entry_relative_tolerance': _TOLERANCE,
        'input_sha256': dict(_INPUTS), 'scientific_qualification': 'NOT_ESTABLISHED',
        'fabrication': 'HOLD'}
    (folder / 'benchmark-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
