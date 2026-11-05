"""B04 software/provenance fixtures only; no QDesign, Gmsh or Palace was run."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from sqe_studio.contracts import digest, validate_project
from sqe_studio.interop.laptop_benchmark import (
    BenchmarkBlocked, _native_terminal_matrix, assess_native_capacitance_matrix,
    resonator_project,
)


def _write(root, name, blob):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    b = blob if isinstance(blob, bytes) else json.dumps(blob, sort_keys=True).encode()
    file.write_bytes(b)
    return {'name': name, 'sha256': sha256(b).hexdigest(), 'bytes': len(b)}


def _capacitance_fixture(tmp_path):
    model = resonator_project(execution='solve')
    model['process']['source'] = 'reviewed'  # Fixture assumption; not real expert approval.
    study = model['studies'][0]
    study['kind'] = 'capacitance'
    em = study['inputs']['em']
    em['ports'] = [
        {'index': 1, 'kind': 'conductor', 'component': 'LP1', 'native_attributes': [9]},
        {'index': 2, 'kind': 'conductor', 'component': 'LP2', 'native_attributes': [10]},
    ]
    em['boundaries']['farfield'] = 'ground'
    em['solver'] = {k: v for k, v in em['solver'].items() if k not in ('start_hz', 'modes')}
    validate_project(model)
    native = tmp_path / 'native'
    entries = [
        _write(native, 'sqe_em/outputFiles/terminal-C.csv',
               b'Terminal,C1 (fF),C2 (fF)\n1,150,-50\n2,-50,160\n'),
        _write(native, 'sqe_em/sqe_em.msh', b'mock mesh, not native'),
        _write(native, 'sqe_em/sqe_em.json', {
            'Problem': {'Type': 'Electrostatic'},
            'Boundaries': {'Ground': {'Attributes': [3, 4]},
                           'Terminal': [{'Index': 1, 'Attributes': [9]},
                                        {'Index': 2, 'Attributes': [10]}]}}),
        _write(native, 'sqe_em/palace-native.log', b'fixture log, no solver ran'),
        _write(native, 'a03-native-artifacts.json', {
            'schema': 'sqe.a03.native-artifacts.v1', 'execution': 'solve',
            'native_completion': {'exit_code': 0}, 'versions': {'palace': 'Palace 0.16'},
            'port_convention': {'ordering': 'reviewed SQDMetal creation order',
                                'index_base': 1, 'ports': em['ports']}}),
    ]
    revision = 'c' * 32
    manifest = {
        'schema': 'sqe.artifact.v1', 'engine': 'sqdmetal_palace',
        'engine_version': 'SQDMetal 0.7; Gmsh 4; Palace 0.16',
        'revision_id': revision, 'project_digest': digest(model),
        'study_id': study['id'], 'kind': 'capacitance',
        'artifact_type': 'palace.capacitance_matrix',
        'fabrication_status': 'HOLD', 'scientific_status': 'review_required',
        'provenance': {'used_revision': revision, 'used_project_sha256': digest(model)},
        'artifacts': entries, 'parents': [],
    }
    _write(native, 'RESULT_MANIFEST.json', manifest)
    evidence = tmp_path / 'review.md'
    evidence.write_text('Fixture: no physical conductor review and no actual solver execution.')
    return model, native, evidence


def test_b04_read_only_review_reports_explicit_unit_provenance_and_scientific_hold(tmp_path):
    model, native, evidence = _capacitance_fixture(tmp_path)
    result = assess_native_capacitance_matrix(model, native, unit='fF',
                                              reviewer='PhysicsReviewer', evidence_file=evidence)
    assert result['capacitance_matrix_F'][0][0] == pytest.approx(150e-15)
    assert result['symmetry_relative_residual'] == 0
    assert result['native_terminal_surface_tags'] == [[9], [10]]
    assert result['Csum_and_EC_transfer'].startswith('BLOCKED')
    assert result['conductor_to_gmsh_spatial_registration'] == 'BLOCKED'
    assert result['fabrication_status'] == 'HOLD'
    assert result['execution_mode'] == 'NATIVE_ARTIFACT_READBACK_NOT_NEW_SOLVER_RUN'


@pytest.mark.parametrize('mutation', [
    'missing_units', 'reversed_columns', 'asymmetric', 'positive_mutual', 'negative_diagonal',
    'nonfinite', 'non_numeric', 'zero', 'bad_row', 'wrong_review_unit',
])
def test_b04_rejects_unreviewed_csv_units_conductor_order_and_nonphysical_matrix(tmp_path, mutation):
    model, native, evidence = _capacitance_fixture(tmp_path)
    csv_file = native / 'sqe_em/outputFiles/terminal-C.csv'
    values = {
        'missing_units': 'Terminal,C1,C2\n1,150,-50\n2,-50,160\n',
        'reversed_columns': 'Terminal,C2 (fF),C1 (fF)\n1,150,-50\n2,-50,160\n',
        'asymmetric': 'Terminal,C1 (fF),C2 (fF)\n1,150,-50\n2,-5,160\n',
        'positive_mutual': 'Terminal,C1 (fF),C2 (fF)\n1,150,50\n2,50,160\n',
        'negative_diagonal': 'Terminal,C1 (fF),C2 (fF)\n1,-150,-50\n2,-50,160\n',
        'nonfinite': 'Terminal,C1 (fF),C2 (fF)\n1,nan,-50\n2,-50,160\n',
        'non_numeric': 'Terminal,C1 (fF),C2 (fF)\n1,spam,-50\n2,-50,160\n',
        'zero': 'Terminal,C1 (fF),C2 (fF)\n1,0,0\n2,0,0\n',
        'bad_row': 'Terminal,C1 (fF),C2 (fF)\n2,150,-50\n1,-50,160\n',
        'wrong_review_unit': 'Terminal,C1 (fF),C2 (fF)\n1,150,-50\n2,-50,160\n',
    }
    csv_file.write_text(values[mutation])
    if mutation in ('asymmetric', 'positive_mutual', 'negative_diagonal', 'zero'):
        # Format is valid but physical gate must reject even after the
        # fixture's hash inventory has been intentionally regenerated.
        manifest_file = native / 'RESULT_MANIFEST.json'
        manifest = json.loads(manifest_file.read_text())
        manifest['artifacts'][0]['sha256'] = sha256(csv_file.read_bytes()).hexdigest()
        manifest['artifacts'][0]['bytes'] = csv_file.stat().st_size
        manifest_file.write_text(json.dumps(manifest))
        with pytest.raises(BenchmarkBlocked):
            assess_native_capacitance_matrix(model, native, unit='fF',
                                             reviewer='PhysicsReviewer', evidence_file=evidence)
    else:
        with pytest.raises(BenchmarkBlocked):
            _native_terminal_matrix(csv_file,
                                    unit='F' if mutation == 'wrong_review_unit' else 'fF',
                                    count=2)


@pytest.mark.parametrize('mutation', [
    'mutated_csv', 'mutated_port', 'bad_solver_exit', 'wrong_project_revision',
    'unreviewed_process', 'changed_model', 'missing_review',
])
def test_b04_requires_exact_source_manifest_and_review(tmp_path, mutation):
    model, native, evidence = _capacitance_fixture(tmp_path)
    if mutation == 'mutated_csv':
        (native / 'sqe_em/outputFiles/terminal-C.csv').write_text(
            'Terminal,C1 (fF),C2 (fF)\n1,151,-50\n2,-50,160\n')
    elif mutation == 'mutated_port':
        deck = native / 'sqe_em/sqe_em.json'
        record = json.loads(deck.read_text())
        record['Boundaries']['Terminal'][0]['Attributes'] = [8]
        deck.write_text(json.dumps(record))
    elif mutation == 'bad_solver_exit':
        sidecar = native / 'a03-native-artifacts.json'
        record = json.loads(sidecar.read_text())
        record['native_completion']['exit_code'] = 1
        sidecar.write_text(json.dumps(record))
    elif mutation == 'wrong_project_revision':
        manifest = native / 'RESULT_MANIFEST.json'
        record = json.loads(manifest.read_text())
        record['revision_id'] = 'a' * 32
        manifest.write_text(json.dumps(record))
    elif mutation == 'unreviewed_process':
        model['process']['source'] = 'unverified'
    elif mutation == 'changed_model':
        model['layout']['components'][0]['x_mm'] += 0.1
    elif mutation == 'missing_review':
        evidence.unlink()
    with pytest.raises(BenchmarkBlocked):
        assess_native_capacitance_matrix(model, native, unit='fF',
                                         reviewer='PhysicsReviewer', evidence_file=evidence)


@pytest.mark.parametrize('mutation', ['different_thickness', 'unreviewed_stack', 'non_pec_stack'])
def test_b07_same_film_gate_blocks_mismatched_pec_vs_kinetic_material(mutation):
    from sqe_studio.interop.laptop_benchmark import _check_kinetic_same_film_stack
    model = resonator_project()
    model['process']['source'] = 'reviewed'
    meta = {'thickness_nm': 100.0, 'sheet_inductance_H_per_square': 2e-12}
    _check_kinetic_same_film_stack(model, meta)
    if mutation == 'different_thickness':
        meta['thickness_nm'] = 120.0
    elif mutation == 'unreviewed_stack':
        model['process']['source'] = 'unverified'
    else:
        model['process']['stack'][1]['em_model'] = 'SurfaceInductance'
    with pytest.raises((BenchmarkBlocked, ValueError)):
        _check_kinetic_same_film_stack(model, meta)


@pytest.mark.parametrize('mutation', ['bool_exit_code', 'duplicate_ground_tag', 'terminal_index_bool', 'sidecar_array'])
def test_b04_bounded_native_metadata_is_strictly_typed(tmp_path, mutation):
    model, native, evidence = _capacitance_fixture(tmp_path)
    manifest_file = native / 'RESULT_MANIFEST.json'
    manifest = json.loads(manifest_file.read_text())
    if mutation in ('bool_exit_code', 'sidecar_array'):
        relative = 'a03-native-artifacts.json'
        file = native / relative
        obj = json.loads(file.read_text())
        if mutation == 'bool_exit_code':
            obj['native_completion']['exit_code'] = False
        else:
            obj = []
    else:
        relative = 'sqe_em/sqe_em.json'
        file = native / relative
        obj = json.loads(file.read_text())
        if mutation == 'duplicate_ground_tag':
            obj['Boundaries']['Ground']['Attributes'] = [3, 3]
        else:
            obj['Boundaries']['Terminal'][0]['Index'] = True
    file.write_text(json.dumps(obj))
    item = next(a for a in manifest['artifacts'] if a['name'] == relative)
    item['sha256'] = sha256(file.read_bytes()).hexdigest()
    item['bytes'] = file.stat().st_size
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(BenchmarkBlocked):
        assess_native_capacitance_matrix(model, native, unit='fF',
                                         reviewer='PhysicsReviewer', evidence_file=evidence)


def test_b04_opt_in_gmsh_group_presence_does_not_qualify_physical_conductors(tmp_path, monkeypatch):
    from sqe_studio.interop import laptop_benchmark as lb
    model, native, evidence = _capacitance_fixture(tmp_path)
    mesh = native / 'sqe_em/sqe_em.msh'
    def fixture_groups(observed_mesh):
        assert observed_mesh == mesh
        return {'mesh_sha256': sha256(mesh.read_bytes()).hexdigest(),
                'surface_entities_by_physical_tag': {
                    '3': [100], '4': [101], '9': [201], '10': [202]},
                'meaning': 'fixture_only_not_native'}
    monkeypatch.setattr(lb, 'inspect_native_mesh_surface_groups', fixture_groups)
    observed = assess_native_capacitance_matrix(
        model, native, unit='fF', reviewer='PhysicsReviewer', evidence_file=evidence,
        require_native_mesh_audit=True)
    assert observed['native_mesh_surface_group_audit']['mesh_sha256'] == sha256(mesh.read_bytes()).hexdigest()
    assert observed['native_surface_group_membership'].startswith('2d_tags_and_')
    assert observed['conductor_to_gmsh_spatial_registration'] == 'BLOCKED'
    assert observed['Csum_and_EC_transfer'].startswith('BLOCKED')
    assert observed['fabrication_status'] == 'HOLD'


@pytest.mark.parametrize('mutation', ['missing_terminal', 'missing_ground', 'shared_faces',
                                      'no_native_runtime', 'invalid_option'])
def test_b04_requested_gmsh_audit_blocks_missing_runtime_and_mismatched_faces(
        tmp_path, monkeypatch, mutation):
    from sqe_studio.interop import laptop_benchmark as lb
    model, native, evidence = _capacitance_fixture(tmp_path)
    groups = {'3': [100], '4': [101], '9': [201], '10': [202]}
    if mutation == 'missing_terminal':
        groups.pop('9')
    elif mutation == 'missing_ground':
        groups.pop('3')
    elif mutation == 'shared_faces':
        groups['9'] = [100]
    elif mutation == 'no_native_runtime':
        def native_unavailable(_):
            raise BenchmarkBlocked('Native Gmsh required')
        monkeypatch.setattr(lb, 'inspect_native_mesh_surface_groups', native_unavailable)
    if mutation not in ('no_native_runtime', 'invalid_option'):
        monkeypatch.setattr(lb, 'inspect_native_mesh_surface_groups', lambda _: {
            'surface_entities_by_physical_tag': groups})
    with pytest.raises(BenchmarkBlocked):
        assess_native_capacitance_matrix(
            model, native, unit='fF', reviewer='PhysicsReviewer', evidence_file=evidence,
            require_native_mesh_audit=1 if mutation == 'invalid_option' else True)
