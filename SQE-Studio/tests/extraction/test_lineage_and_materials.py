"""A17 fail-closed provenance/kinetic fixtures; NO native engine executed.

These deliberately constructed GDS/mesh bytes test file validation only.
They are not production worker outputs or scientific acceptance evidence.
"""
import json
from hashlib import sha256
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from sqe_studio.adapters.quantum_metal_adapter import _inspect_native_gds, validate_recipe
from sqe_studio.contracts import digest
from sqe_studio.interop import laptop_benchmark as lb


def _sha(data):
    return sha256(data).hexdigest()


def _record(tag, dtype=0, payload=b''):
    assert len(payload) % 2 == 0
    return struct.pack('>HBB', len(payload) + 4, tag, dtype) + payload


def _real8(value):
    """Fixture GDSII base-16 float encoder, never used by production."""
    assert value > 0
    exponent = 64
    while value < 1 / 16:
        value *= 16
        exponent -= 1
    while value >= 1:
        value /= 16
        exponent += 1
    return bytes([exponent]) + round(value * (1 << 56)).to_bytes(7, 'big')


def _structural_gds():
    """Minimal structural inspection fixture; not a native QGDS run."""
    xy = struct.pack('>' + 'i'*10, 0, 0, 1000, 0, 1000, 1000, 0, 1000, 0, 0)
    return b''.join([
        _record(0x00, 2, struct.pack('>H', 600)),
        _record(0x01, 2, b'\x00' * 24),
        _record(0x02, 6, b'TEST'),
        _record(0x03, 5, _real8(.001) + _real8(1e-9)),
        _record(0x05, 2, b'\x00' * 24),
        _record(0x06, 6, b'TOP\x00'),
        _record(0x08),
        _record(0x0D, 2, struct.pack('>H', 1)),
        _record(0x0E, 2, struct.pack('>H', 0)),
        _record(0x10, 3, xy),
        _record(0x11), _record(0x07), _record(0x04),
    ])


def _write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = data if isinstance(data, bytes) else json.dumps(data, sort_keys=True).encode()
    path.write_bytes(content)
    return {'name': name, 'sha256': _sha(content), 'bytes': len(content)}


def _manifest(root, model, *, engine, kind, artifact_type, entries, revision='c'*32):
    d = digest(model)
    _write(root, 'RESULT_MANIFEST.json', {
        'schema': 'sqe.artifact.v1', 'engine': engine, 'engine_version': 'fixture 0.1',
        'revision_id': revision, 'project_digest': d, 'study_id': 'GDS' if engine == 'quantum_metal' else 'ResEigen',
        'kind': kind, 'artifact_type': artifact_type, 'scientific_status': 'review_required',
        'fabrication_status': 'HOLD',
        'provenance': {'used_revision': revision, 'used_project_sha256': d},
        'artifacts': entries, 'parents': [],
    })


def _paired_artifacts(tmp_path):
    model = lb.resonator_project()
    model['layout']['gds'] = {'layer_map': {'main': [1]}, 'negative_layers': []}
    gds_root, em_root = tmp_path/'gds', tmp_path/'mesh'
    gds_blob = _structural_gds()
    gds = _write(gds_root, 'quantum_metal_unqualified.gds', gds_blob)
    inspection = _inspect_native_gds(gds_root/gds['name'], {1}, set(), {1})
    planned, _ = validate_recipe(model['layout'])
    hold = {
        'source': 'Quantum Metal QGDSRenderer', 'fabrication_status': 'HOLD',
        'recipe_sha256': digest(model['layout']), 'gds_sha256': gds['sha256'],
        'gds_to_mesh_registration': 'not_established_requires_native_mesh_and_independent_geometry_review',
        'gds_structure': inspection, 'qgeometry_layers': [1], 'layers_declared': [1],
        'negative_mask_layers': [],
        'component_names': [x.name for x in planned],
        'route_net_names': [x.net for x in planned if x.net],
    }
    gh = _write(gds_root, 'gds_hold.json', hold)
    _manifest(gds_root, model, engine='quantum_metal', kind='gds_draft',
              artifact_type='quantum_metal.gdsii', entries=[gds, gh])
    mesh = _write(em_root, 'sqe_em/sqe_em.msh', b'fixture mesh bytes - not native Gmsh')
    deck = _write(em_root, 'sqe_em/sqe_em.json', {
        'Problem': {'Type': 'Eigenmode'},
        'Boundaries': {'PEC': {'Attributes': [3, 4]},
                       'LumpedPort': [{'Index': 1, 'Attributes': [9]},
                                      {'Index': 2, 'Attributes': [10]}]},
    })
    sidecar = _write(em_root, 'a03-native-artifacts.json', {
        'schema': 'sqe.a03.native-artifacts.v1', 'engine': 'sqdmetal_palace',
        'geometry_source': 'A02.build_qdesign(project.layout) verified QDesignBuild; SQDMetal Gmsh full 3D',
        'units': {'mesh_length': 'mm'},
        'port_convention': {
            'index_base': 1, 'ordering': 'reviewed SQDMetal creation order',
            'ports': model['studies'][0]['inputs']['em']['ports'], 'excited_port': None},
        'validation_status': 'native_files_checked_not_scientifically_qualified'})
    _manifest(em_root, model, engine='sqdmetal_palace', kind='eigenmode',
              artifact_type='palace.deck', entries=[mesh, deck, sidecar])
    return model, gds_root, em_root


def test_lineage_binds_exact_layout_revision_two_native_manifests(tmp_path):
    model, gds, mesh = _paired_artifacts(tmp_path)
    result = lb.trace_gds_mesh_lineage(model, gds, mesh)
    assert result['layout_recipe_sha256'] == digest(model['layout'])
    assert result['declared_chip_dimensions'] == {'width_mm': 4.8, 'height_mm': 2.4,
                                                   'thickness_um': 500}
    assert result['declared_gds_layers'] == [1]
    assert result['negative_mask_layers_not_process_qualified'] == []
    assert result['revision_id'] == 'c'*32
    assert result['native_gds_sha256'] == _sha((gds/'quantum_metal_unqualified.gds').read_bytes())
    assert result['native_gmsh_mesh_sha256'] == _sha((mesh/'sqe_em/sqe_em.msh').read_bytes())
    assert result['gds_database_unit_m'] == pytest.approx(1e-9)
    assert result['gds_cell_local_xy_bounds_um_by_layer'] == {'1': [0.0, 0.0, 1.0, 1.0]}
    assert result['em_declared_port_convention']['ports'] == model['studies'][0]['inputs']['em']['ports']
    assert result['palace_native_port_surface_tags'] == {'1': [9], '2': [10]}
    assert result['palace_native_ground_surface_tags'] == [3, 4]
    assert result['native_port_to_gds_or_mesh_surface_registration'].startswith('BLOCKED')
    assert result['shared_revision_and_declared_qdesign_recipe'] is True
    assert result['spatial_polygon_to_mesh_surface_registration'].startswith('BLOCKED')
    assert result['fabrication_status'] == 'HOLD'
    assert result['scientific_qualification'] == 'not_established'


@pytest.mark.parametrize('mutation', ['stale_revision', 'gds_changed', 'mesh_changed',
                                      'review_changed', 'qdesign_names', 'layout_changed'])
def test_lineage_rejects_stale_or_unverified_sources(tmp_path, mutation):
    model, gds, mesh = _paired_artifacts(tmp_path)
    if mutation == 'stale_revision':
        p = mesh/'RESULT_MANIFEST.json'
        data = json.loads(p.read_text())
        data['revision_id'] = 'd'*32
        data['provenance']['used_revision'] = 'd'*32
        p.write_text(json.dumps(data))
    elif mutation == 'gds_changed':
        (gds/'quantum_metal_unqualified.gds').write_bytes(b'forged GDS')
    elif mutation == 'mesh_changed':
        (mesh/'sqe_em/sqe_em.msh').write_bytes(b'forged mesh')
    elif mutation in ('review_changed', 'qdesign_names'):
        p = gds/'gds_hold.json'
        d = json.loads(p.read_text())
        if mutation == 'review_changed':
            d['gds_sha256'] = '0'*64
        else:
            d['component_names'] = ['Other']
        p.write_text(json.dumps(d))
        # Resign only fixture manifest to ensure internal evidence also fails.
        manifest = gds/'RESULT_MANIFEST.json'
        info = json.loads(manifest.read_text())
        content = p.read_bytes()
        info['artifacts'][1].update(sha256=_sha(content), bytes=len(content))
        manifest.write_text(json.dumps(info))
    else:
        model['layout']['components'][0]['x_mm'] += 0.01
    with pytest.raises(lb.BenchmarkBlocked):
        lb.trace_gds_mesh_lineage(model, gds, mesh)


def _kinetic_inputs(tmp_path):
    experiment = tmp_path/'experimental'
    experiment.mkdir()
    mesh = _write(experiment, 'sqe_em.msh', b'mesh groups fixture')
    review = {
        'schema': 'sqe.research-metal-surfaces.v1', 'basis': 'manual_gmsh_physical_group_review',
        'reviewer': 'Physicist', 'source_deck_sha256': 'a'*64,
        'source_mesh_sha256': mesh['sha256'],
        'conductor_attributes': [1, 2], 'excluded_attributes': [3, 4],
    }
    r = _write(experiment, 'SURFACE_REVIEW.json', review)
    deck = {'Problem': {'Type': 'Eigenmode', 'Output': 'outputFiles_kinetic'},
            'Model': {'Mesh': 'sqe_em.msh'},
            'Boundaries': {'PEC': {'Attributes': [3, 4]},
                           'Impedance': [{'Attributes': [1, 2], 'Ls': 2e-12, 'Crack': False}],
                           'LumpedPort': [{'Attributes': [9], 'Index': 1}]}}
    _write(experiment, 'sqe_em_kinetic.json', deck)
    meta = {'schema': 'sqe.research-kinetic-deck.v1', 'reviewer': 'Physicist',
            'source_palace_deck_sha256': 'a'*64, 'source_gmsh_mesh_sha256': mesh['sha256'],
            'surface_review_sha256': r['sha256'], 'surface_attributes': [1, 2],
            'sheet_inductance_H_per_square': 2e-12,
            'surface_domain_evidence': 'manual_only_native_mesh_group_presence_unverified',
            'thickness_nm': 20,
            'penetration_depth_nm': 120, 'regime': 'thin'}
    meta['generated_deck_sha256'] = _sha((experiment/'sqe_em_kinetic.json').read_bytes())
    _write(experiment, 'KINETIC_REVIEW.json', meta)
    return experiment, meta


def test_kinetic_boundaries_are_reviewed_on_reinspection(tmp_path):
    experiment, meta = _kinetic_inputs(tmp_path)
    lb._verify_prepared_kinetic_deck(experiment, meta,
                                      experiment/'sqe_em_kinetic.json', experiment/'sqe_em.msh')


@pytest.mark.parametrize('tamper', ['inductance', 'crack', 'pec', 'port_overlap', 'thin_regime',
                                    'metal_classification', 'mesh_hash'])
def test_kinetic_deck_fails_closed_on_unreviewed_material_or_surface(tmp_path, tamper):
    experiment, meta = _kinetic_inputs(tmp_path)
    deck_file = experiment/'sqe_em_kinetic.json'
    d = json.loads(deck_file.read_text())
    if tamper == 'inductance':
        d['Boundaries']['Impedance'][0]['Ls'] = 7e-12
    elif tamper == 'crack':
        d['Boundaries']['Impedance'][0]['Crack'] = True
    elif tamper == 'pec':
        d['Boundaries']['PEC']['Attributes'].remove(3)
    elif tamper == 'port_overlap':
        d['Boundaries']['LumpedPort'][0]['Attributes'].append(1)
    elif tamper == 'thin_regime':
        meta['thickness_nm'] = 1000
    elif tamper == 'metal_classification':
        review_file = experiment/'SURFACE_REVIEW.json'
        review = json.loads(review_file.read_text())
        review['conductor_attributes'] = [2, 3]
        review_file.write_text(json.dumps(review))
        meta['surface_review_sha256'] = _sha(review_file.read_bytes())
    else:
        (experiment/'sqe_em.msh').write_bytes(b'tampered mesh')
    if tamper in ('inductance', 'crack', 'pec', 'port_overlap'):
        deck_file.write_text(json.dumps(d))
        meta['generated_deck_sha256'] = _sha(deck_file.read_bytes())
    with pytest.raises(lb.BenchmarkBlocked):
        lb._verify_prepared_kinetic_deck(experiment, meta, deck_file, experiment/'sqe_em.msh')


def test_surface_group_audit_observes_native_api_but_not_material_identity(tmp_path, monkeypatch):
    mesh = tmp_path/'real-mesh-not-required-for_api_fixture.msh'
    mesh.write_bytes(b'fixture-only')
    calls = []
    fake = SimpleNamespace(
        initialize=lambda: calls.append('init'),
        open=lambda path: calls.append(('open', path)),
        finalize=lambda: calls.append('finalize'),
        model=SimpleNamespace(getPhysicalGroups=lambda dim: [(2, 1), (2, 2), (2, 3), (2, 4)],
                              getEntitiesForPhysicalGroup=lambda dim, tag: [tag * 10]),
    )
    original_import = lb.import_module
    monkeypatch.setattr(lb, 'import_module', lambda name: fake if name == 'gmsh' else original_import(name))
    observed = lb.inspect_native_mesh_surface_groups(mesh)
    assert observed['mesh_sha256'] == _sha(mesh.read_bytes())
    assert observed['surface_entities_by_physical_tag'] == {
        '1': [10], '2': [20], '3': [30], '4': [40]}
    assert 'unverified' in observed['meaning']
    assert calls[0] == 'init' and calls[-1] == 'finalize'


def test_surface_group_audit_missing_dependency_is_blocked(tmp_path, monkeypatch):
    p = tmp_path/'msh'
    p.write_text('fixture')
    def missing(name):
        raise ImportError('Native Gmsh not installed')
    monkeypatch.setattr(lb, 'import_module', missing)
    with pytest.raises(lb.BenchmarkBlocked, match='Native Gmsh required'):
        lb.inspect_native_mesh_surface_groups(p)


def test_gmsh_physical_group_audit_is_bound_to_exact_reviewed_mesh(tmp_path, monkeypatch):
    experiment, meta = _kinetic_inputs(tmp_path)
    active = {1, 2, 3, 4}
    fake = SimpleNamespace(
        initialize=lambda: None, finalize=lambda: None, open=lambda path: None,
        model=SimpleNamespace(getPhysicalGroups=lambda dim: [(2, tag) for tag in sorted(active)],
                              getEntitiesForPhysicalGroup=lambda dim, tag: [tag * 10]),
    )
    original_import = lb.import_module
    monkeypatch.setattr(lb, 'import_module', lambda name: fake if name == 'gmsh' else original_import(name))
    review_file = experiment/'SURFACE_REVIEW.json'
    review = json.loads(review_file.read_text())
    review['native_gmsh_surface_audit'] = lb.inspect_native_mesh_surface_groups(experiment/'sqe_em.msh')
    review_file.write_text(json.dumps(review))
    meta['surface_review_sha256'] = _sha(review_file.read_bytes())
    meta['surface_domain_evidence'] = 'native_gmsh_groups_present_operator_classification_unverified'
    lb._verify_prepared_kinetic_deck(experiment, meta,
                                      experiment/'sqe_em_kinetic.json', experiment/'sqe_em.msh')
    active.remove(1)
    with pytest.raises(lb.BenchmarkBlocked, match='2D Gmsh surface tags'):
        lb._verify_prepared_kinetic_deck(experiment, meta,
                                          experiment/'sqe_em_kinetic.json', experiment/'sqe_em.msh')


def test_native_kinetic_cannot_run_if_material_metadata_forged(tmp_path):
    import sys
    experiment, meta = _kinetic_inputs(tmp_path)
    meta['sheet_inductance_H_per_square'] = 1e-12  # copied deck still says 2e-12
    (experiment/'KINETIC_REVIEW.json').write_text(json.dumps(meta))
    with pytest.raises(lb.BenchmarkBlocked, match='assignment differs'):
        lb.run_kinetic_native(experiment, Path(sys.executable))
    assert not (experiment/'KINETIC_RUN_MANIFEST.json').exists()
    assert not (experiment/'palace-exec.log').exists()


@pytest.mark.parametrize('mutation', ['zero_units', 'zero_xy', 'missing_endel',
                                      'nonclosing_polygon', 'unexpected_geometry_layer'])
def test_gds_readback_rejects_untrustworthy_native_lengths_and_geometry(tmp_path, mutation):
    original = _structural_gds()
    if mutation == 'zero_units':
        original = original.replace(_real8(.001) + _real8(1e-9), b'\0' * 16)
    elif mutation == 'zero_xy':
        xy = _record(0x10, 3, struct.pack('>' + 'i'*10, 0, 0, 1000, 0,
                                           1000, 1000, 0, 1000, 0, 0))
        original = original.replace(xy, _record(0x10, 3, b''))
    elif mutation == 'missing_endel':
        original = original.replace(_record(0x11), b'')
    elif mutation == 'nonclosing_polygon':
        xy = _record(0x10, 3, struct.pack('>' + 'i'*10, 0, 0, 1000, 0,
                                           1000, 1000, 0, 1000, 0, 0))
        changed_xy = _record(0x10, 3, struct.pack('>' + 'i'*10, 0, 0, 1000, 0,
                                           1000, 1000, 0, 1000, 1, 0))
        original = original.replace(xy, changed_xy)
    else:
        original = original.replace(_record(0x0d, 2, struct.pack('>H', 1)),
                                    _record(0x0d, 2, struct.pack('>H', 99)))
    gds = tmp_path / 'draft.gds'
    gds.write_bytes(original)
    from sqe_studio.adapters.base import EngineBlocked
    with pytest.raises(EngineBlocked):
        _inspect_native_gds(gds, {1}, set(), {1})


@pytest.mark.parametrize('mutation', ['omitted_ports', 'forged_impedance',
                                      'wrong_order', 'wrong_study'])
def test_lineage_refuses_unreviewed_a03_native_port_order(tmp_path, mutation):
    model, gds, mesh = _paired_artifacts(tmp_path)
    sidecar = mesh/'a03-native-artifacts.json'
    data = json.loads(sidecar.read_text())
    if mutation == 'omitted_ports':
        del data['port_convention']
    elif mutation == 'forged_impedance':
        data['port_convention']['ports'][0]['impedance_ohm'] = 55
    elif mutation == 'wrong_order':
        data['port_convention']['ports'].reverse()
    else:
        manifest = mesh/'RESULT_MANIFEST.json'
        m = json.loads(manifest.read_text())
        m['study_id'] = 'UnrelatedStudy'
        manifest.write_text(json.dumps(m))
    if mutation != 'wrong_study':
        sidecar.write_text(json.dumps(data))
        manifest = mesh/'RESULT_MANIFEST.json'
        m = json.loads(manifest.read_text())
        row = next(x for x in m['artifacts'] if x['name'] == 'a03-native-artifacts.json')
        row['sha256'] = _sha(sidecar.read_bytes())
        row['bytes'] = len(sidecar.read_bytes())
        manifest.write_text(json.dumps(m))
    with pytest.raises(lb.BenchmarkBlocked, match='port convention|unique revision-bound'):
        lb.trace_gds_mesh_lineage(model, gds, mesh)


@pytest.mark.parametrize('tamper', ['port_order', 'overlap', 'missing', 'unmapped', 'waveport'])
def test_lineage_rejects_native_palace_port_surface_inconsistency(tmp_path, tamper):
    model, gds, mesh = _paired_artifacts(tmp_path)
    path = mesh/'sqe_em/sqe_em.json'
    d = json.loads(path.read_text())
    ports = d['Boundaries']['LumpedPort']
    if tamper == 'port_order':
        ports[1]['Index'] = 1
    elif tamper == 'overlap':
        ports[0]['Attributes'] = [3]
    elif tamper == 'missing':
        ports[0]['Attributes'] = []
    elif tamper == 'unmapped':
        ports[1]['Attributes'] = [9]
    else:
        d['Boundaries']['WavePort'] = [{'Index': 1, 'Attributes': [11]}]
    path.write_text(json.dumps(d))
    manifest = mesh/'RESULT_MANIFEST.json'
    m = json.loads(manifest.read_text())
    row = next(r for r in m['artifacts'] if r['name'] == 'sqe_em/sqe_em.json')
    row['sha256'] = _sha(path.read_bytes()); row['bytes'] = len(path.read_bytes())
    manifest.write_text(json.dumps(m))
    with pytest.raises(lb.BenchmarkBlocked, match='Native Palace port'):
        lb.trace_gds_mesh_lineage(model, gds, mesh)


@pytest.mark.parametrize('tamper', ['layer_polarity', 'declared_layer', 'qgeometry'])
def test_lineage_rejects_resigned_gds_hold_layer_or_polarity_tampering(tmp_path, tamper):
    model, gds, mesh = _paired_artifacts(tmp_path)
    path = gds/'gds_hold.json'
    hold = json.loads(path.read_text())
    if tamper == 'layer_polarity':
        hold['negative_mask_layers'] = [1]
    elif tamper == 'declared_layer':
        hold['layers_declared'] = [1, 2]
    else:
        hold['qgeometry_layers'] = []
    path.write_text(json.dumps(hold))
    manifest = gds/'RESULT_MANIFEST.json'
    m = json.loads(manifest.read_text())
    row = next(r for r in m['artifacts'] if r['name'] == 'gds_hold.json')
    row['sha256'] = _sha(path.read_bytes()); row['bytes'] = len(path.read_bytes())
    manifest.write_text(json.dumps(m))
    with pytest.raises(lb.BenchmarkBlocked, match='GDS layer mapping/polarity'):
        lb.trace_gds_mesh_lineage(model, gds, mesh)


def _fake_gmsh_groups(monkeypatch, groups):
    """API stand-in ONLY: the mesh bytes in this suite are not native Gmsh."""
    calls = []
    gmsh = SimpleNamespace(
        initialize=lambda: calls.append('initialize'),
        open=lambda path: calls.append(('open', path)),
        finalize=lambda: calls.append('finalize'),
        model=SimpleNamespace(
            getPhysicalGroups=lambda dim: [(2, tag) for tag in sorted(groups)],
            getEntitiesForPhysicalGroup=lambda dim, tag: list(groups[tag])),
    )
    actual_import = lb.import_module
    monkeypatch.setattr(lb, 'import_module',
                        lambda name: gmsh if name == 'gmsh' else actual_import(name))
    return calls


def test_lineage_opt_in_native_tag_membership_is_not_spatial_registration(tmp_path, monkeypatch):
    model, gds, em = _paired_artifacts(tmp_path)
    groups = {3: [300], 4: [400], 9: [900], 10: [1000], 31: [3100]}
    calls = _fake_gmsh_groups(monkeypatch, groups)
    observed = lb.trace_gds_mesh_lineage(model, gds, em, require_native_mesh_audit=True)
    assert observed['native_surface_group_membership'].startswith('2d_tags_and_')
    assert observed['native_mesh_surface_group_audit']['mesh_sha256'] == _sha(
        (em/'sqe_em/sqe_em.msh').read_bytes())
    assert observed['native_mesh_surface_group_audit']['surface_entities_by_physical_tag']['9'] == [900]
    assert observed['declared_metal_process_layers'] == [1]
    assert observed['declared_process_stack_sha256'] == digest(model['process']['stack'])
    assert observed['spatial_polygon_to_mesh_surface_registration'].startswith('BLOCKED')
    assert observed['metal_stack_to_mesh_material_registration'].startswith('BLOCKED')
    assert observed['native_port_to_gds_or_mesh_surface_registration'].startswith('BLOCKED')
    assert observed['scientific_qualification'] == 'not_established'
    assert calls[0] == 'initialize' and calls[-1] == 'finalize'
    # Non-native mode must not silently report a group membership audit.
    unqualified = lb.trace_gds_mesh_lineage(model, gds, em)
    assert unqualified['native_mesh_surface_group_audit'] is None
    assert unqualified['native_surface_group_membership'].startswith('BLOCKED')


@pytest.mark.parametrize('mutation', ['missing_port', 'missing_ground', 'shared_port_face',
                                      'shared_ground_face', 'duplicate_group', 'malformed_group'])
def test_lineage_native_mesh_audit_rejects_missing_or_aliased_faces(tmp_path, monkeypatch, mutation):
    model, gds, em = _paired_artifacts(tmp_path)
    groups = {3: [300], 4: [400], 9: [900], 10: [1000]}
    if mutation == 'missing_port':
        del groups[9]
    elif mutation == 'missing_ground':
        del groups[4]
    elif mutation == 'shared_port_face':
        groups[10] = [900]
    elif mutation == 'shared_ground_face':
        groups[3] = [900]
    elif mutation == 'duplicate_group':
        groups = {3: [300], 4: [400], 9: [900], 10: [1000, 1000]}
    else:
        groups = {3: [300], 4: [400], 9: [900], 10: [0]}
    calls = _fake_gmsh_groups(monkeypatch, groups)
    with pytest.raises(lb.BenchmarkBlocked, match='Gmsh|surface tags|surface group'):
        lb.trace_gds_mesh_lineage(model, gds, em, require_native_mesh_audit=True)
    assert calls[-1] == 'finalize'


def test_lineage_requested_native_audit_absent_runtime_is_blocked(tmp_path, monkeypatch):
    model, gds, em = _paired_artifacts(tmp_path)
    monkeypatch.setattr(lb, 'import_module', lambda module: (_ for _ in ()).throw(ImportError('unavailable')))
    with pytest.raises(lb.BenchmarkBlocked, match='Native Gmsh required'):
        lb.trace_gds_mesh_lineage(model, gds, em, require_native_mesh_audit=True)
    with pytest.raises(lb.BenchmarkBlocked, match='explicit boolean'):
        lb.trace_gds_mesh_lineage(model, gds, em, require_native_mesh_audit=1)


def test_gds_geometry_layer_inventory_ignores_unbound_layer_records(tmp_path):
    # A GDSII LAYER record without a physical BOUNDARY/PATH/BOX must not
    # masquerade as native mask geometry on that layer.
    blob = _structural_gds()
    phantom = _record(0x0D, 2, struct.pack('>H', 2))
    blob = blob.replace(_record(0x07), phantom + _record(0x07))
    p = tmp_path/'local_cell_not_native.gds'
    p.write_bytes(blob)
    inspection = _inspect_native_gds(p, {1}, set(), {1})
    assert inspection['layers'] == [1]
    assert inspection['user_unit_m'] == pytest.approx(1e-6)
    from sqe_studio.adapters.base import EngineBlocked
    with pytest.raises(EngineBlocked, match='omit required QGeometry layers'):
        _inspect_native_gds(p, {1, 2}, set(), {1, 2})


def test_b01_gds_polygon_area_is_cell_local_screen_only(tmp_path):
    path = tmp_path / 'quad.gds'
    path.write_bytes(_structural_gds())
    scanned = _inspect_native_gds(path, {1}, set(), {1})
    assert scanned['polygon_primitive_counts_by_layer'] == {'1': 1}
    assert scanned['polygon_primitive_area_um2_by_layer']['1'] == pytest.approx(1.0)
    assert 'no_boolean_union_hierarchy_or_paths' in scanned['area_scope']


def test_b01_invalid_zero_area_polygon_blocks(tmp_path):
    blob = _structural_gds()
    good = struct.pack('>' + 'i'*10, 0, 0, 1000, 0, 1000, 1000, 0, 1000, 0, 0)
    bad = struct.pack('>' + 'i'*10, 0, 0, 1000, 0, 500, 0, 1000, 0, 0, 0)
    path = tmp_path / 'degenerate.gds'
    path.write_bytes(blob.replace(good, bad))
    with pytest.raises(Exception, match='Degenerate'):
        _inspect_native_gds(path, {1}, set(), {1})


def _gds_with_cell_reference(*, target='CHILD', add_child=True, child_to_top=False):
    """Hand-encoded *test* cell graph, not a native GDS renderer output."""
    sref = (_record(0x0a) + _record(0x12, 6, target.encode('ascii').ljust(6, b'\0'))
            + _record(0x10, 3, struct.pack('>ii', 0, 0)) + _record(0x11))
    result = _structural_gds().replace(_record(0x07) + _record(0x04),
                                       sref + _record(0x07) + _record(0x04))
    if add_child:
        child = (_record(0x05, 2, b'\0' * 24) + _record(0x06, 6, b'CHILD\0')
                 + (_record(0x0a) + _record(0x12, 6, b'TOP\0')
                    + _record(0x10, 3, struct.pack('>ii', 0, 0)) + _record(0x11)
                    if child_to_top else b'') + _record(0x07))
        result = result[:-4] + child + _record(0x04)
    return result


def test_b01_gds_cell_references_must_resolve_without_implying_spatial_mapping(tmp_path):
    path = tmp_path / 'references_fixture.gds'
    path.write_bytes(_gds_with_cell_reference())
    inspected = _inspect_native_gds(path, {1}, set(), {1})
    assert inspected['cells'] == ['CHILD', 'TOP']
    assert inspected['sref_aref_records'] == 1
    assert inspected['referenced_cells'] == ['CHILD']
    assert 'no_cell_placement_or_transforms' in inspected['hierarchy_scope']
    assert inspected['area_scope'].startswith('sum_of_cell_local')


@pytest.mark.parametrize('mutation', ['undefined', 'cycle', 'missing_sname',
                                      'unfinished_ref', 'duplicate_cell_name'])
def test_b01_gds_unqualified_or_corrupt_hierarchy_is_fail_closed(tmp_path, mutation):
    blob = _gds_with_cell_reference(add_child=mutation != 'undefined',
                                    child_to_top=mutation == 'cycle')
    if mutation == 'missing_sname':
        blob = blob.replace(_record(0x12, 6, b'CHILD\0'), b'', 1)
    elif mutation == 'unfinished_ref':
        # Deleting the reference's ENDEL leaves an active ref at ENDSTR.
        blob = blob.replace(_record(0x10, 3, struct.pack('>ii', 0, 0)) + _record(0x11),
                            _record(0x10, 3, struct.pack('>ii', 0, 0)), 1)
    elif mutation == 'duplicate_cell_name':
        blob = blob.replace(_record(0x06, 6, b'CHILD\0'), _record(0x06, 6, b'TOP\0'), 1)
    path = tmp_path / 'invalid_fixture.gds'
    path.write_bytes(blob)
    from sqe_studio.adapters.base import EngineBlocked
    with pytest.raises(EngineBlocked):
        _inspect_native_gds(path, {1}, set(), {1})


def test_b01_valid_aref_is_counted_but_not_expanded_or_area_qualified(tmp_path):
    blob = _gds_with_cell_reference()
    sref = (_record(0x0a) + _record(0x12, 6, b'CHILD\0')
            + _record(0x10, 3, struct.pack('>ii', 0, 0)) + _record(0x11))
    aref = (_record(0x0b) + _record(0x12, 6, b'CHILD\0')
            + _record(0x13, 2, struct.pack('>HH', 2, 3))
            + _record(0x10, 3, struct.pack('>iiiiii', 0, 0, 2000, 0, 0, 3000))
            + _record(0x11))
    path = tmp_path / 'aref_fixture.gds'
    path.write_bytes(blob.replace(sref, aref, 1))
    result = _inspect_native_gds(path, {1}, set(), {1})
    assert result['sref_aref_records'] == 1
    assert result['referenced_cells'] == ['CHILD']
    assert result['polygon_primitive_area_um2_by_layer'] == {'1': 1.0}
    assert 'no_cell_placement_or_transforms' in result['hierarchy_scope']


@pytest.mark.parametrize('mutation', ['missing_aref_colrow', 'invalid_aref_colrow',
                                      'invalid_aref_xy', 'invalid_sref_xy'])
def test_b01_rejects_bad_sref_aref_placement_records(tmp_path, mutation):
    original = _gds_with_cell_reference()
    sref = (_record(0x0a) + _record(0x12, 6, b'CHILD\0')
            + _record(0x10, 3, struct.pack('>ii', 0, 0)) + _record(0x11))
    aref = (_record(0x0b) + _record(0x12, 6, b'CHILD\0')
            + _record(0x13, 2, struct.pack('>HH', 2, 3))
            + _record(0x10, 3, struct.pack('>iiiiii', 0, 0, 2000, 0, 0, 3000))
            + _record(0x11))
    if mutation == 'invalid_sref_xy':
        changed = sref.replace(_record(0x10, 3, struct.pack('>ii', 0, 0)),
                               _record(0x10, 3, struct.pack('>iiii', 0, 0, 1, 2)))
        blob = original.replace(sref, changed, 1)
    else:
        if mutation == 'missing_aref_colrow':
            changed = aref.replace(_record(0x13, 2, struct.pack('>HH', 2, 3)), b'')
        elif mutation == 'invalid_aref_colrow':
            changed = aref.replace(_record(0x13, 2, struct.pack('>HH', 2, 3)),
                                   _record(0x13, 2, struct.pack('>HH', 0, 3)))
        else:
            changed = aref.replace(_record(0x10, 3, struct.pack('>iiiiii', 0, 0, 2000, 0, 0, 3000)),
                                   _record(0x10, 3, struct.pack('>ii', 0, 0)))
        blob = original.replace(sref, changed, 1)
    path = tmp_path / 'bad_ref_fixture.gds'
    path.write_bytes(blob)
    from sqe_studio.adapters.base import EngineBlocked
    with pytest.raises(EngineBlocked):
        _inspect_native_gds(path, {1}, set(), {1})
