"""A11 offline *constructed* VTK/Palace-format fixtures, never native solver PASS."""
from __future__ import annotations

import errno
import hashlib
import json
from pathlib import Path

import pytest

from sqe_studio.interop.native_field import (
    NativeFieldEvidenceError, compare_same_mesh_fields, inspect_palace_field_export,
    inspect_local_palace_field_values)
from sqe_studio.adapters import sqdmetal_palace_adapter as a03
from sqe_studio.interop.scientific_review import screen_native_field_pair
from sqe_studio.interop.laptop_benchmark import resonator_project


def deck(save=1):
    return {'Problem': {'Type': 'Eigenmode', 'Output': 'outputFiles',
                        'OutputFormats': {'Paraview': True}},
            'Model': {'Mesh': 'sqe_em.msh', 'L0': 0.001},
            'Solver': {'Eigenmode': {'Save': save, 'N': 1}}}


def manifest(root):
    return [{'name': f.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'bytes': f.stat().st_size}
            for f in sorted(root.rglob('*')) if f.is_file()]


def base_files(root):
    (root / 'sqe_em').mkdir(parents=True)
    (root / 'sqe_em' / 'sqe_em.msh').write_bytes(b'NOT A REAL GMSH MESH - UNIT TEST ONLY')
    (root / 'sqe_em' / 'sqe_em.json').write_text(json.dumps(deck()) + '\n', encoding='utf8')
    result = root/'sqe_em/outputFiles'
    result.mkdir()
    (result/'eig.csv').write_text('m, Re{f} (GHz), Im{f} (GHz), Q\n1.00e+00, 5.9, 0, 1000\n', encoding='utf8')


def vtk_fixture(root, real=(1., 0., 0.), imag=(0., 0., 0.), tweak=0., b=None):
    vtk = pytest.importorskip('vtkmodules')
    from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkTetra, vtkUnstructuredGrid
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter

    base_files(root)
    vtu = root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001'
    vtu.mkdir(parents=True)
    grid = vtkUnstructuredGrid()
    points = vtkPoints()
    for xyz in ((0,0,0), (1+tweak,0,0), (0,1,0), (0,0,1)):
        points.InsertNextPoint(*xyz)
    grid.SetPoints(points)
    cell = vtkTetra()
    for i in range(4):
        cell.GetPointIds().SetId(i,i)
    grid.InsertNextCell(cell.GetCellType(),cell.GetPointIds())
    components = [('E_real', real), ('E_imag', imag)]
    if b is not None:
        components += [('B_real', b[0]), ('B_imag', b[1])]
    for name, direction in components:
        arr = vtkDoubleArray()
        arr.SetName(name)
        arr.SetNumberOfComponents(3)
        for _ in range(4):
            arr.InsertNextTuple3(*direction)
        grid.GetPointData().AddArray(arr)
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(vtu/'proc000000.vtu'))
    writer.SetInputData(grid)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()  # Palace uses raw-appended VTK XML
    assert writer.Write() == 1
    (vtu/'data.pvtu').write_text(
        '<?xml version="1.0"?><VTKFile type="PUnstructuredGrid" version="0.1">'
        '<PUnstructuredGrid><Piece Source="proc000000.vtu"/></PUnstructuredGrid></VTKFile>', encoding='utf8')
    (root/'sqe_em/outputFiles/paraview/eigenmode/eigenmode.pvd').write_text(
        '<?xml version="1.0"?><VTKFile type="Collection" version="0.1">'
        '<Collection><DataSet timestep="1" file="Cycle000001/data.pvtu"/></Collection>'
        '</VTKFile>', encoding='utf8')
    return manifest(root)


def test_save_zero_does_not_create_or_assume_fields(tmp_path):
    base_files(tmp_path)
    r = inspect_palace_field_export(tmp_path, deck(save=0), manifest(tmp_path))
    assert r['status'] == 'BLOCKED_NO_NATIVE_COMPLEX_FIELD_EXPORT'
    assert r['complex_overlap'] == 'NOT_COMPUTED'
    assert r['mode_identity'] == 'UNRESOLVED'
    with pytest.raises(NativeFieldEvidenceError, match='Verified complex native exports'):
        compare_same_mesh_fields(tmp_path, manifest(tmp_path), r,
                                 tmp_path, manifest(tmp_path), r)


def test_requested_export_missing_fails_closed_without_inventing_fields(tmp_path):
    base_files(tmp_path)
    r = inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))
    assert r['status'] == 'BLOCKED_NO_NATIVE_COMPLEX_FIELD_EXPORT'
    assert 'missing' in r['reason']


def test_native_vtu_raw_appended_declared_complex_vectors_are_hashed(tmp_path):
    files = vtk_fixture(tmp_path)
    r = inspect_palace_field_export(tmp_path, deck(), files)
    assert r['status'] == 'VERIFIED_NATIVE_COMPLEX_FIELD_EXPORT_FORMAT_ONLY'
    assert r['field_unit'] == 'V/m'
    assert r['first_saved_native_mode_index'] == 1
    assert r['first_saved_mode_frequency_GHz'] == pytest.approx(5.9)
    assert r['metres_per_mesh_unit'] == 0.001
    assert r['complex_overlap'] == 'NOT_COMPUTED'
    assert r['mode_identity'] == 'UNRESOLVED'
    assert len(r['field_samples']) == 1
    assert r['field_samples'][0]['vtk_pieces'][0]['name'].endswith('proc000000.vtu')


def test_complex_phase_invariant_overlap_same_linear_tetra_only(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fa = vtk_fixture(a, real=(1., 0., 0.))
    fb = vtk_fixture(b, real=(0., 0., 0.), imag=(1., 0., 0.))
    ea = inspect_palace_field_export(a, deck(), fa)
    eb = inspect_palace_field_export(b, deck(), fb)
    result = compare_same_mesh_fields(a, fa, ea, b, fb, eb)
    assert result['status'] == 'DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH'
    assert result['phase_invariant_overlap_magnitude'] == pytest.approx(1)
    assert result['complex_overlap_im'] == pytest.approx(1)
    assert result['relative_phase_rad'] == pytest.approx(1.5707963267948966)
    assert result['integrated_mesh_volume_m3'] == pytest.approx(1e-9/6)
    assert result['mode_identity'].startswith('UNRESOLVED')
    assert result['em_to_hamiltonian'] == 'BLOCKED'


def test_refinement_and_coordinate_mismatch_never_proxy_as_overlap(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fa = vtk_fixture(a)
    fb = vtk_fixture(b, tweak=0.05)
    ea = inspect_palace_field_export(a, deck(), fa)
    eb = inspect_palace_field_export(b, deck(), fb)
    with pytest.raises(NativeFieldEvidenceError, match='point coordinates differ'):
        compare_same_mesh_fields(a, fa, ea, b, fb, eb)
    (b/'sqe_em/sqe_em.msh').write_bytes(b'CHANGED MESH - UNIT TEST ONLY')
    fb = manifest(b)
    eb = inspect_palace_field_export(b, deck(), fb)
    with pytest.raises(NativeFieldEvidenceError, match='Different mesh'):
        compare_same_mesh_fields(a, fa, ea, b, fb, eb)


def test_declared_artifact_tamper_and_missing_complex_components_rejected(tmp_path):
    fa = vtk_fixture(tmp_path)
    path = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    path.write_bytes(path.read_bytes() + b'corrupted')
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        inspect_palace_field_export(tmp_path, deck(), fa)
    # A spoofed unverified VTU with no vectors must not be admitted as field data.
    path.write_text('<VTKFile type="UnstructuredGrid"><UnstructuredGrid>'
                    '<Piece><PointData/></Piece></UnstructuredGrid></VTKFile>', encoding='utf8')
    with pytest.raises(NativeFieldEvidenceError, match='point-sampled fields|complex E'):
        inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))


def test_pvd_path_traversal_is_rejected_unconditionally(tmp_path):
    files = vtk_fixture(tmp_path)
    pvd = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/eigenmode.pvd'
    pvd.write_text('<VTKFile type="Collection"><Collection>'
                   '<DataSet file="../../private/data.pvtu"/>'
                   '</Collection></VTKFile>', encoding='utf8')
    with pytest.raises(NativeFieldEvidenceError, match='Unsafe Palace PVD'):
        inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))


def test_pvd_symlink_is_rejected_when_os_permits_creation(tmp_path):
    vtk_fixture(tmp_path)
    pvd = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/eigenmode.pvd'
    pvd.unlink()
    try:
        pvd.symlink_to(tmp_path/'sqe_em/sqe_em.json')
    except OSError as exc:
        # Windows account without SeCreateSymbolicLinkPrivilege: WinError 1314.
        # Do not skip traversal or any other non-symlink test.
        if getattr(exc, 'winerror', None) == 1314 or exc.errno in (errno.EPERM, errno.EACCES, errno.ENOTSUP):
            pytest.skip(f'OS denied test symlink creation: {type(exc).__name__} ({exc.errno})')
        raise
    with pytest.raises(NativeFieldEvidenceError, match='symlink'):
        inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))


def test_production_validator_rejects_solve_without_explicit_palace_field_save():
    project = resonator_project(execution='solve')
    study = project['studies'][0]
    em = study['inputs']['em']
    config = {'Problem': {'Type': 'Eigenmode'},
              'Model': {'L0': 1e-3, 'Mesh':'sqe_em.msh'},
              'Solver': {'Order': em['solver']['order'], 'Eigenmode': {'N': em['solver']['modes'], 'Target': em['solver']['start_hz']/1e9, 'Save': 0}},
              'Domains': {'Materials': [{'Attributes':[2], 'Permittivity':1.0, 'LossTan':0.0},
                                        {'Attributes':[1], 'Permittivity':project['process']['stack'][0]['relative_permittivity'], 'LossTan':project['process']['stack'][0]['loss_tangent']}]},
              'Boundaries': {'PEC': {'Attributes':[5]}, 'WavePort':[],
                             'LumpedPort':[{'Index':i, 'Attributes':[5+i]} for i in range(1,len(em['ports'])+1)]}}
    with pytest.raises(a03.EngineBlocked, match='field export'):
        a03._validate_deck(config, em, {'kind':'eigenmode',
                       '_stack_for_validation':project['process']['stack']}, {1,2}, {5,6,7})
    config['Solver']['Eigenmode']['Save'] = 1
    a03._validate_deck(config, em, {'kind':'eigenmode',
                      '_stack_for_validation':project['process']['stack']}, {1,2}, {5,6,7})


def test_scientific_mode_screen_refuses_missing_fields_and_never_auto_identifies(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fa = vtk_fixture(a, real=(1., 0., 0.))
    fb = vtk_fixture(b, real=(0., 0., 0.), imag=(1., 0., 0.))
    screened = screen_native_field_pair(a, deck(), fa, b, deck(), fb)
    assert screened['field_overlap']['phase_invariant_overlap_magnitude'] == pytest.approx(1)
    assert screened['mode_identity'].startswith('UNRESOLVED')
    assert screened['physical_convergence'] == 'NOT_ESTABLISHED'
    assert screened['em_to_hamiltonian'] == 'BLOCKED'
    with pytest.raises(NativeFieldEvidenceError, match='missing'):
        screen_native_field_pair(a, deck(save=0), fa, b, deck(), fb)


def test_sqdmetal_option_requests_native_field_only_for_real_solve(tmp_path, monkeypatch):
    """Mocks the SQDMetal *constructor*, never claims a solver was executed."""
    import sys
    from types import ModuleType

    seen = []
    class FakeSimulation:
        def __init__(self, **kwargs):
            seen.append(kwargs['user_options'])
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    for module in ('SQDMetal', 'SQDMetal.PALACE', 'SQDMetal.Utilities'):
        pkg = ModuleType(module)
        pkg.__path__ = []
        monkeypatch.setitem(sys.modules, module, pkg)
    for module, symbol, value in (
        ('SQDMetal.PALACE.Capacitance_Simulation','PALACE_Capacitance_Simulation',FakeSimulation),
        ('SQDMetal.PALACE.Eigenmode_Simulation','PALACE_Eigenmode_Simulation',FakeSimulation),
        ('SQDMetal.Utilities.Materials','Material',object)):
        pkg = ModuleType(module)
        setattr(pkg, symbol, value)
        monkeypatch.setitem(sys.modules, module, pkg)
    monkeypatch.setattr(a03, '_checked_qdesign', lambda *_: object())
    monkeypatch.setattr(a03, '_check_native_material_catalogue', lambda *_: None)

    project = resonator_project(execution='deck_only')
    study = project['studies'][0]
    a03._make_native(study, project, study['inputs']['em'], None, tmp_path)
    assert seen[-1]['solns_to_save'] == 0
    study['inputs']['em']['execution'] = 'solve'
    a03._make_native(study, project, study['inputs']['em'], None, tmp_path)
    assert seen[-1]['solns_to_save'] == 1
    assert seen[-1]['number_of_freqs'] == study['inputs']['em']['solver']['modes']


def test_local_vtk_decode_reports_complex_E_and_B_hashes_not_H_or_mode_id(tmp_path):
    files = vtk_fixture(tmp_path, b=((0.0, 2.0, 0.0), (0.0, 0.0, 3.0)))
    evidence = inspect_palace_field_export(tmp_path, deck(), files)
    assert evidence['B_field_status'] == 'DECLARED_COMPLEX_B_FLUX_DENSITY_FORMAT_ONLY'
    assert evidence['H_field_status'].startswith('BLOCKED_')
    local = inspect_local_palace_field_values(tmp_path, deck(), files)
    assert local['status'] == 'VERIFIED_LOCAL_VTK_SAMPLES_DIAGNOSTIC_ONLY'
    assert local['complex_components']['E']['unit'] == 'V/m'
    assert local['complex_components']['B']['unit'] == 'T'
    assert local['complex_components']['B']['point_tuple_count'] == 4
    assert len(local['complex_components']['B']['imag_values_sha256']) == 64
    assert local['coordinate_bounds_m']['max'] == pytest.approx([.001, .001, .001])
    assert len(local['geometry_sha256']) == 64
    assert local['H_field_status'].startswith('BLOCKED_')
    assert local['surface_tag_status'].startswith('BLOCKED_')
    assert local['mode_identity'] == 'UNRESOLVED'
    assert 'field_samples' not in local  # No raw full-field data enters a report


def test_local_decode_rejects_field_tamper_and_bad_mode_ordinal(tmp_path):
    files = vtk_fixture(tmp_path)
    assert 'B' not in inspect_local_palace_field_values(tmp_path, deck(), files)['complex_components']
    with pytest.raises(NativeFieldEvidenceError, match='ordinal|mode'):
        inspect_local_palace_field_values(tmp_path, deck(), files, saved_ordinal=2)
    path = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    path.write_bytes(path.read_bytes() + b'X')
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        inspect_local_palace_field_values(tmp_path, deck(), files)


def test_half_complex_B_native_declaration_rejected(tmp_path):
    vtk_fixture(tmp_path, b=((0., 2., 0.), (0., 0., 3.)))
    path = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    raw = path.read_bytes()
    assert b'Name="B_imag"' in raw
    path.write_bytes(raw.replace(b'Name="B_imag"', b'Name="X_imag"', 1))
    with pytest.raises(NativeFieldEvidenceError, match='Incomplete native complex B'):
        inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))


def test_root_symlink_untrusted_even_when_target_is_valid(tmp_path):
    target = tmp_path/'target'
    vtk_fixture(target)
    link = tmp_path/'linked-root'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314 or exc.errno in (errno.EPERM, errno.EACCES, errno.ENOTSUP):
            pytest.skip(f'OS denied directory symlink: {type(exc).__name__} ({exc.errno})')
        raise
    with pytest.raises(NativeFieldEvidenceError, match='workspace root'):
        inspect_palace_field_export(link, deck(), manifest(target))


def test_B_complex_overlap_is_independent_diagnostic_never_H_or_mode_identity(tmp_path):
    left, right = tmp_path/'left', tmp_path/'right'
    x = ((0., 1., 0.), (0., 0., 0.))
    y = ((0., 0., 0.), (0., 1., 0.))
    la = vtk_fixture(left, b=x)
    rb = vtk_fixture(right, imag=(1., 0., 0.), real=(0., 0., 0.), b=y)
    ea = inspect_palace_field_export(left, deck(), la)
    eb = inspect_palace_field_export(right, deck(), rb)
    result = compare_same_mesh_fields(left, la, ea, right, rb, eb)
    assert result['B_field_status'] == 'DIAGNOSTIC_UNWEIGHTED_B_NOT_H'
    assert result['B_phase_invariant_overlap_magnitude'] == pytest.approx(1.)
    assert result['B_complex_overlap_im'] == pytest.approx(1.)
    assert result['H_field_status'].startswith('BLOCKED_')
    assert result['mode_identity'].startswith('UNRESOLVED')
    screened = screen_native_field_pair(left, deck(), la, right, deck(), rb)
    assert screened['local_sample_evidence']['left']['complex_components']['B']['unit'] == 'T'
    assert screened['surface_registration'].startswith('BLOCKED_')
    assert screened['em_to_hamiltonian'] == 'BLOCKED'


def test_incompatible_E_B_field_representations_fail_closed(tmp_path):
    left, right = tmp_path/'left', tmp_path/'right'
    la = vtk_fixture(left, b=((0., 1., 0.), (0., 0., 0.)))
    rb = vtk_fixture(right)
    ea = inspect_palace_field_export(left, deck(), la)
    eb = inspect_palace_field_export(right, deck(), rb)
    with pytest.raises(NativeFieldEvidenceError, match='incompatible magnetic B'):
        compare_same_mesh_fields(left, la, ea, right, rb, eb)


def test_windows_1314_skip_is_confined_to_symlink_case(monkeypatch, tmp_path):
    """Simulates Windows standard-user privilege on the Linux CI host."""
    def refuse_symlink(*_args, **_kwargs):
        error = OSError(errno.EPERM, 'simulated standard account')
        error.winerror = 1314
        raise error
    monkeypatch.setattr(Path, 'symlink_to', refuse_symlink)
    with pytest.raises(pytest.skip.Exception, match='OS denied test symlink creation'):
        test_pvd_symlink_is_rejected_when_os_permits_creation(tmp_path/'symlink')
    # Traversal is not part of that skip: a distinct test executes normally.
    test_pvd_path_traversal_is_rejected_unconditionally(tmp_path/'traversal')


def v2_ascii_gmsh():
    """Constructed small tagged mesh; NEVER host-generated Palace evidence."""
    return (b'$MeshFormat\n2.2 0 8\n$EndMeshFormat\n'
            b'$Nodes\n4\n1 0 0 0\n2 1 0 0\n3 0 1 0\n4 0 0 1\n$EndNodes\n'
            b'$Elements\n2\n1 2 2 5 1 1 2 3\n2 4 2 2 1 1 2 3 4\n$EndElements\n')


def mpi_piece_fixture(root, *, mismatch=False, ghost=False, missing_b=False):
    """Two SHA-bound VTU tetra pieces share a face, not fabricated solver data."""
    vtk = pytest.importorskip('vtkmodules')
    from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkTetra, vtkUnstructuredGrid
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter

    vtk_fixture(root, b=((0., 1., 0.), (0., 0., 1.)))
    folder = root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001'
    grid = vtkUnstructuredGrid()
    points = vtkPoints()
    if ghost:
        coords = ((0,0,0), (1,0,0), (0,1,0), (0,0,1))
    else:
        coords = ((1,0,0), (0,1,0), (0,0,1), (1,1,1))
    for c in coords:
        points.InsertNextPoint(*c)
    grid.SetPoints(points)
    cell = vtkTetra()
    for i in range(4):
        cell.GetPointIds().SetId(i, i)
    grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    for key, coords in [('E_real', (1,0,0)), ('E_imag', (0,0,0)),
                        ('B_real', (0,1,0)), ('B_imag', (0,0,1))]:
        if missing_b and key.startswith('B'):
            continue
        arr = vtkDoubleArray()
        arr.SetName(key)
        arr.SetNumberOfComponents(3)
        for i in range(4):
            direction = (7,0,0) if mismatch and i == 0 and key == 'E_real' else coords
            arr.InsertNextTuple3(*direction)
        grid.GetPointData().AddArray(arr)
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(folder/'proc000001.vtu'))
    writer.SetInputData(grid)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()
    assert writer.Write() == 1
    (folder/'data.pvtu').write_text(
        '<?xml version="1.0"?><VTKFile type="PUnstructuredGrid"><PUnstructuredGrid>'
        '<Piece Source="proc000000.vtu"/><Piece Source="proc000001.vtu"/>'
        '</PUnstructuredGrid></VTKFile>', encoding='utf8')
    return manifest(root)


def test_mpi_exact_seam_assembly_digest_and_tag_gate(tmp_path):
    files = mpi_piece_fixture(tmp_path)
    exported = inspect_palace_field_export(tmp_path, deck(), files)
    assert exported['mpi_piece_status'].startswith('FORMAT_REFERENCES_')
    local = inspect_local_palace_field_values(tmp_path, deck(), files)
    assert local['mpi_piece_count'] == 2
    assert local['vtk_point_count'] == 5  # exact union of three face points
    assert local['vtk_tetra_count'] == 2
    assert local['complex_components']['E']['point_tuple_count'] == 5
    assert local['complex_components']['B']['unit'] == 'T'
    assert len(local['mpi_piece_sha256']) == 2
    assert local['mode_identity'] == 'UNRESOLVED'
    assert local['gmsh_physical_tags']['status'].startswith('BLOCKED')
    assert local['surface_tag_status'].startswith('BLOCKED')
    assert 'field_samples' not in local


@pytest.mark.parametrize(('mutant', 'message'), [
    ({'mismatch': True}, 'Inconsistent shared MPI'),
    ({'ghost': True}, 'Duplicate/ghost tetra'),
    ({'missing_b': True}, 'MPI pieces disagree')])
def test_mpi_seam_conflict_ghost_and_mixed_B_fail_closed(tmp_path, mutant, message):
    files = mpi_piece_fixture(tmp_path, **mutant)
    with pytest.raises(NativeFieldEvidenceError, match=message):
        inspect_local_palace_field_values(tmp_path, deck(), files)


def test_mpi_duplicate_manifested_pvtu_piece_rejected(tmp_path):
    mpi_piece_fixture(tmp_path)
    pvtu = tmp_path/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/data.pvtu'
    pvtu.write_text(pvtu.read_text().replace('proc000001.vtu','proc000000.vtu'))
    with pytest.raises(NativeFieldEvidenceError, match='Duplicate VTU reference'):
        inspect_palace_field_export(tmp_path, deck(), manifest(tmp_path))


def test_gmsh_physical_tag_inventory_only_and_source_tamper(tmp_path):
    from sqe_studio.interop.native_field import inspect_gmsh_physical_tags
    base_files(tmp_path)
    path = tmp_path/'sqe_em/sqe_em.msh'
    path.write_bytes(v2_ascii_gmsh())
    files = manifest(tmp_path)
    with_deck = {**deck(), 'Domains': {'Materials': [{'Attributes': [2]}]},
                 'Boundaries': {'PEC': {'Attributes': [5]}}}
    info = inspect_gmsh_physical_tags(tmp_path, files, config=with_deck)
    assert info['status'] == 'VERIFIED_GMSH_V2_ASCII_PHYSICAL_TAG_PRESENCE_ONLY'
    assert info['volume_physical_tags'] == [2]
    assert info['surface_physical_tags'] == [5]
    assert info['verified_mesh_node_count'] == 4
    assert info['vtk_to_gmsh_registration'].startswith('BLOCKED_')
    with_deck['Boundaries']['PEC']['Attributes'] = [17]
    assert inspect_gmsh_physical_tags(tmp_path, files, config=with_deck)['status'] == 'BLOCKED_GMSH_TAGS_NOT_ALIGNED_WITH_PALACE_DECK'
    path.write_bytes(v2_ascii_gmsh().replace(b'4 0 0 1', b'4 0 0 0'))
    assert inspect_gmsh_physical_tags(tmp_path, manifest(tmp_path))['status'] == 'BLOCKED_DEGENERATE_GMSH_TETRA'
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        inspect_gmsh_physical_tags(tmp_path, files)


def test_gmsh_binary_and_v4_are_blocked_not_accepted(tmp_path):
    from sqe_studio.interop.native_field import inspect_gmsh_physical_tags
    base_files(tmp_path)
    path = tmp_path/'sqe_em/sqe_em.msh'
    path.write_bytes(b'$MeshFormat\n4.1 1 8\n\x00')
    assert inspect_gmsh_physical_tags(tmp_path, manifest(tmp_path))['status'].startswith('BLOCKED_GMSH_BINARY')
    path.write_bytes(b'$MeshFormat\n4.1 0 8\n$EndMeshFormat\n')
    assert inspect_gmsh_physical_tags(tmp_path, manifest(tmp_path))['status'].startswith('BLOCKED_')


def test_screen_mpi_reports_blocked_overlap_but_preserves_local_e_b_hashes(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fa, fb = mpi_piece_fixture(a), mpi_piece_fixture(b)
    result = screen_native_field_pair(a, deck(), fa, b, deck(), fb)
    assert result['field_overlap']['status'].startswith('BLOCKED_MPI_')
    assert result['local_sample_evidence']['left']['mpi_piece_count'] == 2
    assert result['mode_identity'].startswith('UNRESOLVED')
    assert result['em_to_hamiltonian'] == 'BLOCKED'
    assert result['fabrication'] == 'HOLD'

# RC14.10 expanded cases: constructed, SHA-bound format fixtures only.

def driven_deck(excited=1):
    return {'Problem': {'Type': 'Driven'},
            'Model': {'Mesh': 'sqe_em.msh', 'L0': .001},
            'Solver': {'Driven': {'MinFreq': 4., 'MaxFreq': 5., 'FreqStep': .5}},
            'Boundaries': {'LumpedPort': [
                {'Index': n, 'Excitation': n == excited, 'Attributes': [n + 5]}
                for n in (1, 2)], 'WavePort': []}}


def driven_fixture(root, *, csv_text=None, excited=1):
    from sqe_studio.interop.native_field import inspect_palace_driven_sparameters
    config = driven_deck(excited)
    (root / 'sqe_em/outputFiles').mkdir(parents=True)
    (root / 'sqe_em/sqe_em.msh').write_bytes(b'CONSTRUCTED-ONLY-MESH')
    (root / 'sqe_em/sqe_em.json').write_text(json.dumps(config), encoding='utf8')
    if csv_text is None:
        csv_text = ('Frequency (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg),'
                    '|S[2][1]| (dB),arg(S[2][1]) (deg)\n'
                    '4.0,-6,0,-6,90\n4.5,-10,180,-1,0\n5.0,-3,-90,-9,45\n')
    (root / 'sqe_em/outputFiles/port-S.csv').write_text(csv_text, encoding='utf8')
    return inspect_palace_driven_sparameters, config, manifest(root)


def test_b05_two_port_sha_bound_complex_column_is_only_numeric_diagnostic(tmp_path):
    fn, config, items = driven_fixture(tmp_path)
    r = fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    assert r['status'] == 'VERIFIED_NATIVE_COMPLEX_DRIVEN_COLUMN_DIAGNOSTIC_ONLY'
    assert r['number_of_samples'] == 3
    assert r['samples'][0]['excited_column']['S21']['real'] == pytest.approx(0, abs=1e-15)
    assert r['samples'][0]['excited_column']['S21']['imag'] == pytest.approx(10**(-6/20))
    assert r['port_reference'].startswith('BLOCKED')
    assert r['passivity'].startswith('BLOCKED')
    assert r['reciprocity'].startswith('BLOCKED')
    assert r['mode_identity'] == 'UNRESOLVED' and r['fabrication'] == 'HOLD'
    assert not any('S12' in sample['excited_column'] for sample in r['samples'])
    assert r['port_s_sha256'] == items[-1]['sha256'] or len(r['port_s_sha256']) == 64


def test_b05_missing_complex_transmission_is_blocked_not_synthesized(tmp_path):
    text = ('Frequency (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg)\n'
            '4,-6,0\n4.5,-10,0\n5,-3,0\n')
    fn, config, items = driven_fixture(tmp_path, csv_text=text)
    r = fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    assert r['status'] == 'BLOCKED_INCOMPLETE_TWO_PORT_COMPLEX_COLUMN'
    assert r['samples'] == []
    assert r['passivity'].startswith('BLOCKED')


def test_b05_phase_pair_duplicate_and_tamper_rejected(tmp_path):
    fn, config, items = driven_fixture(tmp_path)
    wrong = dict(config)
    wrong['Boundaries'] = {'LumpedPort': config['Boundaries']['LumpedPort'][::-1], 'WavePort': []}
    with pytest.raises(NativeFieldEvidenceError, match='ordered native lumped ports'):
        fn(tmp_path, wrong, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    with pytest.raises(NativeFieldEvidenceError, match='frequency'):
        fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5.5e9], excited_port=1)
    csv_path = tmp_path/'sqe_em/outputFiles/port-S.csv'
    csv_path.write_text(csv_path.read_text() + '\n', encoding='utf8')
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)


def test_b05_incomplete_phase_and_nonfinite_samples_are_rejected(tmp_path):
    fn, config, items = driven_fixture(tmp_path, csv_text=(
        'Frequency (GHz),|S[1][1]| (dB),|S[2][1]| (dB),arg(S[2][1]) (deg)\n'
        '4,-6,-6,90\n4.5,-10,-1,0\n5,-3,-9,45\n'))
    with pytest.raises(NativeFieldEvidenceError, match='incomplete'):
        fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    fn, config, items = driven_fixture(tmp_path/'nonfinite', csv_text=(
        'Frequency (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg),'
        '|S[2][1]| (dB),arg(S[2][1]) (deg)\n'
        '4,-6,0,-6,90\n4.5,nan,180,-1,0\n5,-3,-90,-9,45\n'))
    with pytest.raises(NativeFieldEvidenceError, match='nonfinite'):
        fn(tmp_path/'nonfinite', config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)


def test_b05_exact_excitation_order_is_required_not_conjugated(tmp_path):
    fn, config, items = driven_fixture(tmp_path, excited=2)
    with pytest.raises(NativeFieldEvidenceError, match='excitation'):
        fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    r = fn(tmp_path, config, items, frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=2)
    assert r['status'] == 'BLOCKED_MISSING_COMPLEX_S_COLUMNS'
    assert r['samples'] == []


def test_b02_b03_b06_b07_b11_production_screen_preserves_physical_holds(tmp_path):
    from sqe_studio.interop.scientific_review import screen_native_em_benchmark_cases
    fa = vtk_fixture(tmp_path, b=((0, 1, 0), (0, 0, 1)))
    r = screen_native_em_benchmark_cases(tmp_path, deck(), fa, kind='eigenmode', solve_completed=True)
    assert r['execution_kind'] == 'NATIVE'  # Caller contract; fixture is not a solver execution.
    assert r['cases']['B02']['stage_status'] == 'NATIVE_FIELD_VALUES_SCREENED_SCIENCE_BLOCKED'
    assert r['cases']['B02']['field_sample_metadata']['H_field_status'].startswith('BLOCKED')
    assert r['cases']['B03']['stage_status'].startswith('BLOCKED')
    assert r['cases']['B06']['stage_status'].startswith('BLOCKED')
    assert r['cases']['B07']['stage_status'].startswith('BLOCKED')
    assert r['cases']['B11']['stage_status'].startswith('NOT_IMPLEMENTED')
    assert r['mode_identity'] == 'UNRESOLVED' and r['fabrication'] == 'HOLD'
    not_run = screen_native_em_benchmark_cases(tmp_path, deck(), fa, kind='eigenmode', solve_completed=False)
    assert not_run['execution_kind'] == 'NOT_RUN'
    assert all(case['stage_status'] == 'NOT_RUN' for case in not_run['cases'].values())


def test_b05_native_benchmark_integration_requires_review_for_two_port(tmp_path):
    from sqe_studio.interop.scientific_review import screen_native_em_benchmark_cases
    fn, config, items = driven_fixture(tmp_path)
    evidence = screen_native_em_benchmark_cases(
        tmp_path, config, items, kind='sparameters', solve_completed=True,
        requested_frequencies_hz=[4e9, 4.5e9, 5e9], excited_port=1)
    assert evidence['cases']['B05']['stage_status'] == 'NATIVE_COMPLEX_COLUMN_SCREENED_SCIENCE_BLOCKED'
    assert evidence['cases']['B05']['native_driven_evidence']['number_of_samples'] == 3
    assert evidence['cases']['B02']['stage_status'] == 'NOT_RUN'
    assert evidence['cases']['B11']['stage_status'].startswith('NOT_IMPLEMENTED')


def test_b03_two_refined_meshes_retain_sha_evidence_but_no_interpolation(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fa = vtk_fixture(a)
    fb = vtk_fixture(b, tweak=0.01)
    (b/'sqe_em/sqe_em.msh').write_bytes(b'DIFFERENT-CONSTRUCTED-MESH')
    fb = manifest(b)
    outcome = screen_native_field_pair(a, deck(), fa, b, deck(), fb)
    assert outcome['field_overlap']['status'] == 'BLOCKED_CROSS_MESH_HCURL_REGISTRATION_NOT_REVIEWED'
    assert outcome['field_overlap']['left_mesh_sha256'] != outcome['field_overlap']['right_mesh_sha256']
    assert outcome['local_sample_evidence']['left']['complex_components']['E']['real_values_sha256']
    assert outcome['mode_identity'].startswith('UNRESOLVED')
    assert outcome['fabrication'] == 'HOLD'


def test_b02_optional_native_signed_kappa_keeps_negative_and_refuses_unknown(tmp_path):
    from sqe_studio.interop.native_field import inspect_palace_signed_port_kappa
    vtk_fixture(tmp_path)
    path = tmp_path/'sqe_em/outputFiles/port-Q.csv'
    empty = inspect_palace_signed_port_kappa(tmp_path, manifest(tmp_path))
    assert empty['status'] == 'BLOCKED_NATIVE_PORT_Q_NOT_EMITTED'
    path.write_text('m,Q_ext[1],kappa_ext[1] (GHz)\n1,1000000,-0.000001\n', encoding='utf8')
    evidence = inspect_palace_signed_port_kappa(tmp_path, manifest(tmp_path))
    assert evidence['status'] == 'VERIFIED_NATIVE_SIGNED_KAPPA_NUMERIC_SCREEN_ONLY'
    port = evidence['modes'][0]['ports'][0]
    assert port['signed_kappa_ext_GHz'] == pytest.approx(-1e-6)
    assert port['negative_kappa_requires_sign_convention_review'] is True
    assert evidence['mode_identity'] == 'UNRESOLVED'
    path.write_text('m,Q_ext[1],kappa_ext[1] (GHz)\n1,1000000,nan\n', encoding='utf8')
    assert inspect_palace_signed_port_kappa(tmp_path, manifest(tmp_path))['status'] == 'BLOCKED_UNRECOGNIZED_NATIVE_PORT_Q_FORMAT'
    good_manifest = manifest(tmp_path)
    path.write_text('m,Q_ext[1],kappa_ext[1] (GHz)\n1,1000000,-5e-6\n', encoding='utf8')
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        inspect_palace_signed_port_kappa(tmp_path, good_manifest)


def refined_cross_mesh_fixture(root, *, real=(0., 1., 0.), imag=(0., 0., 0.),
                               b=None, changed_bounds=False):
    """Construct *non-native* conforming four-tetra subdivision for B03 tests."""
    vtk = pytest.importorskip('vtkmodules')
    import numpy as np
    from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkTetra, vtkUnstructuredGrid
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter

    vtk_fixture(root, real=real, imag=imag, b=b)
    grid = vtkUnstructuredGrid()
    points = vtkPoints()
    coords = [(0., 0., 0.), (1.05 if changed_bounds else 1., 0., 0.),
              (0., 1., 0.), (0., 0., 1.), (.25, .25, .25)]
    for point in coords:
        points.InsertNextPoint(*point)
    grid.SetPoints(points)
    for face in ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1)):
        cell_ids = (4, *face)
        p = np.asarray([coords[i] for i in cell_ids])
        if np.linalg.det(np.stack((p[1]-p[0], p[2]-p[0], p[3]-p[0]), axis=-1)) < 0:
            cell_ids = (4, face[0], face[2], face[1])
        cell = vtkTetra()
        for i, index in enumerate(cell_ids):
            cell.GetPointIds().SetId(i, index)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    fields = [('E_real', real), ('E_imag', imag)]
    if b is not None:
        fields.extend((('B_real', b[0]), ('B_imag', b[1])))
    for name, vec in fields:
        arr = vtkDoubleArray()
        arr.SetName(name)
        arr.SetNumberOfComponents(3)
        for _ in coords:
            arr.InsertNextTuple3(*vec)
        grid.GetPointData().AddArray(arr)
    path = root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()
    assert writer.Write() == 1
    # The intentionally different mesh is a *constructed* independent input.
    (root/'sqe_em/sqe_em.msh').write_bytes(b'CONSTRUCTED FOUR-TETRA TEST MESH ONLY')
    return manifest(root)


def test_b03_bidirectional_barycentric_screen_is_phase_invariant_but_never_mode_id(tmp_path):
    from sqe_studio.interop.native_field import screen_cross_mesh_visualization_overlap
    left, right = tmp_path/'coarse', tmp_path/'fine'
    a = vtk_fixture(left, real=(1., 0., 0.), b=((0., 0., 1.), (0., 0., 0.)))
    b = refined_cross_mesh_fixture(right, real=(0., 0., 0.), imag=(1., 0., 0.),
                                    b=((0., 0., 0.), (0., 0., 1.)))
    x = inspect_palace_field_export(left, deck(), a)
    y = inspect_palace_field_export(right, deck(), b)
    result = screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
        coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')
    assert result['status'] == 'DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH'
    assert result['E_forward_overlap_magnitude'] == pytest.approx(1.)
    assert result['E_backward_overlap_magnitude'] == pytest.approx(1.)
    assert result['left_field_vtu_sha256'] == x['field_samples'][0]['vtk_pieces'][0]['sha256']
    assert result['right_field_vtu_sha256'] == y['field_samples'][0]['vtk_pieces'][0]['sha256']
    assert result['E_unit'] == 'V/m'
    assert result['B_unit_if_present'].startswith('T (')
    assert result['E_forward_relative_phase_rad'] == pytest.approx(1.5707963267948966)
    assert result['E_bidirectional_overlap_disagreement'] == pytest.approx(0.)
    assert result['B_forward_overlap_magnitude'] == pytest.approx(1.)
    assert result['B_field_status'] == 'DIAGNOSTIC_B_FLUX_DENSITY_NOT_H'
    assert result['interpolation_error'].startswith('UNBOUNDED')
    assert result['mode_identity'].startswith('UNRESOLVED')
    assert result['physical_convergence'] == 'NOT_ESTABLISHED'
    assert result['em_to_hamiltonian'] == 'BLOCKED'
    assert result['fabrication'] == 'HOLD'


def test_b03_cross_mesh_screen_rejects_unreviewed_assumption_and_different_frames(tmp_path):
    from sqe_studio.interop.native_field import screen_cross_mesh_visualization_overlap
    left, right = tmp_path/'coarse', tmp_path/'fine'
    a = vtk_fixture(left)
    b = refined_cross_mesh_fixture(right, changed_bounds=True)
    x = inspect_palace_field_export(left, deck(), a)
    y = inspect_palace_field_export(right, deck(), b)
    with pytest.raises(NativeFieldEvidenceError, match='explicit diagnostic-only assumption'):
        screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
                                                coordinate_assumption='')
    with pytest.raises(NativeFieldEvidenceError, match='coordinate bounds'):
        screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
            coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')


def test_b03_cross_mesh_screen_rejects_field_tamper_and_incompatible_B(tmp_path):
    from sqe_studio.interop.native_field import screen_cross_mesh_visualization_overlap
    left, right = tmp_path/'coarse', tmp_path/'fine'
    a = vtk_fixture(left, b=((0., 1., 0.), (0., 0., 0.)))
    b = refined_cross_mesh_fixture(right)
    x = inspect_palace_field_export(left, deck(), a)
    y = inspect_palace_field_export(right, deck(), b)
    with pytest.raises(NativeFieldEvidenceError, match='complex B representations'):
        screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
            coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')
    p = right/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    p.write_bytes(p.read_bytes() + b'forged')
    with pytest.raises(NativeFieldEvidenceError, match='digest/size'):
        screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
            coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')


def test_b03_cross_mesh_screen_rejects_unrelated_material_deck(tmp_path):
    from sqe_studio.interop.native_field import screen_cross_mesh_visualization_overlap
    left, right = tmp_path/'coarse', tmp_path/'fine'
    a = vtk_fixture(left)
    b = refined_cross_mesh_fixture(right)
    modified = deck()
    modified['Domains'] = {'unreviewed_material': [12]}
    (right/'sqe_em/sqe_em.json').write_text(json.dumps(modified), encoding='utf8')
    b = manifest(right)
    x = inspect_palace_field_export(left, deck(), a)
    y = inspect_palace_field_export(right, modified, b)
    with pytest.raises(NativeFieldEvidenceError, match='material or boundary'):
        screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
            coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')


def affine_complex_field_fixture(root, *, pure_imag=False):
    """Rewrite a constructed VTK with a spatially affine exact vector field."""
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader, vtkXMLUnstructuredGridWriter
    path = root/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    assert reader.GetErrorCode() == 0
    grid = reader.GetOutput()
    for index in range(grid.GetNumberOfPoints()):
        x, y, z = grid.GetPoint(index)
        sample = (2 + x, 3 + y, 4 + z)
        grid.GetPointData().GetArray('E_real').SetTuple3(
            index, *((0., 0., 0.) if pure_imag else sample))
        grid.GetPointData().GetArray('E_imag').SetTuple3(
            index, *(sample if pure_imag else (0., 0., 0.)))
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()
    assert writer.Write() == 1
    return manifest(root)


def test_b03_cross_mesh_affine_complex_field_quadrature_not_index_matching(tmp_path):
    from sqe_studio.interop.native_field import screen_cross_mesh_visualization_overlap
    left, right = tmp_path/'a', tmp_path/'b'
    vtk_fixture(left)
    refined_cross_mesh_fixture(right)
    a = affine_complex_field_fixture(left)
    b = affine_complex_field_fixture(right, pure_imag=True)
    x = inspect_palace_field_export(left, deck(), a)
    y = inspect_palace_field_export(right, deck(), b)
    result = screen_cross_mesh_visualization_overlap(left, a, x, right, b, y,
        coordinate_assumption='SAME_UNROTATED_PALACE_MESH_FRAME_DIAGNOSTIC_ONLY')
    assert result['E_forward_overlap_magnitude'] == pytest.approx(1.)
    assert result['E_backward_overlap_magnitude'] == pytest.approx(1.)
    assert result['E_bidirectional_overlap_disagreement'] == pytest.approx(0., abs=1e-12)
    assert result['E_forward_relative_phase_rad'] == pytest.approx(1.57079632679)
    assert result['physical_coordinate_registration'].startswith('BLOCKED')
    assert result['material_weighting'].startswith('BLOCKED')


def test_m12_saved_cross_mesh_diagnostic_uses_real_vtk_fixture_not_frequency_proxy(tmp_path):
    from sqe_studio.eda.field_lineage import (
        inspect_verified_run_field_lineage, screen_verified_saved_pair_overlap)
    left, right = tmp_path/'a', tmp_path/'b'
    vtk_fixture(left)
    refined_cross_mesh_fixture(right)
    a = affine_complex_field_fixture(left)
    b = affine_complex_field_fixture(right, pure_imag=True)
    manifests = tuple({'engine':'sqdmetal_palace', 'artifact_type':'palace.eigenmodes',
                       'artifacts': rows} for rows in (a,b))
    rows=[inspect_verified_run_field_lineage(root, signed)
          for root,signed in zip((left,right),manifests)]
    numerical=screen_verified_saved_pair_overlap((left,right),manifests,rows,
        {'status':'native_mode_index_differences_for_expert_review'})
    assert numerical['status']=='VISUALIZATION_OVERLAP_DIAGNOSTIC_ONLY'
    assert numerical['overlap']['E_forward_overlap_magnitude']==pytest.approx(1.)
    assert numerical['overlap']['E_backward_overlap_magnitude']==pytest.approx(1.)
    assert numerical['overlap']['E_forward_relative_phase_rad']==pytest.approx(1.57079632679)
    assert numerical['physical_mode_identity']=='UNRESOLVED'
    assert numerical['mesh_convergence']=='NOT_ESTABLISHED'
    assert numerical['fabrication']=='HOLD'
    # Changing data after signing removes both source integrity and diagnostics.
    field=right/'sqe_em/outputFiles/paraview/eigenmode/Cycle000001/proc000000.vtu'
    field.write_bytes(field.read_bytes()+b'tampered')
    rows[1]=inspect_verified_run_field_lineage(right,manifests[1])
    blocked=screen_verified_saved_pair_overlap((left,right),manifests,rows,
        {'status':'native_mode_index_differences_for_expert_review'})
    assert blocked['status']=='BLOCKED_UNVERIFIED_SOURCE'
    assert blocked['overlap'] is None
