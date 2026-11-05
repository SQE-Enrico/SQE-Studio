"""RC14.4 tests: all synthetic fixtures are structural, never solver validation."""
from __future__ import annotations
import errno
import json
import zipfile
from pathlib import Path
import os
import pytest

from sqe_studio.interop.native_em_evidence import native_em_evidence, NativeEMEvidenceError
from sqe_studio.orchestration.artifacts import safe_file, ArtifactInvalid

PREFIX = 'sqe_em/outputFiles/'


def _run(tmp_path, *, negative=True, probe=False, port=True, energy=True, modes=1):
    root = tmp_path/'run'
    dest = root/'sqe_em'/'outputFiles'
    dest.mkdir(parents=True)
    files = {
        'eig.csv': 'm, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)\n' +
                   ''.join(f'{i}, {5.9+i*.1}, 1e-6, {100000*i}, 1e-9, 1e-8\n' for i in range(1,modes+1)),
    }
    if port:
        files['port-Q.csv'] = 'm,Q_ext[1],κ_ext[1] (GHz),Q_ext[2],κ_ext[2] (GHz)\n' + \
             ''.join(f'{i},2000000,{(-1 if negative else 1)*(5.9+i*.1)/2000000},4000000,{(5.9+i*.1)/4000000}\n' for i in range(1,modes+1))
    if energy:
        files['domain-E.csv'] = 'm,E_elec (J),E_mag (J),E_cap (J)\n' + \
                                   ''.join(f'{i},1.0e-12,1.1e-12,0\n' for i in range(1,modes+1))
    if probe:
        files['probe-E.csv'] = 'm,E_x[1],E_y[1]\n1,0.7,0.4\n'
    entries=[]
    import hashlib
    for name,data in files.items():
        out=dest/name
        out.write_text(data,encoding='utf-8')
        entries.append({'name':PREFIX+name,'bytes':out.stat().st_size,
                        'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
    return root, {'engine':'sqdmetal_palace','kind':'eigenmode','artifacts':entries}


def test_native_results_show_distinct_q_port_and_energy_with_hard_gates(tmp_path):
    root,manifest=_run(tmp_path,modes=2)
    out=native_em_evidence(root,manifest)
    assert out['schema']=='sqe.em-native-results-screen.v1'
    assert out['modes'][0]['frequency_GHz']==pytest.approx(6.0)
    assert out['modes'][0]['q_total']==100000
    assert out['modes'][1]['q_total']==200000
    assert out['modes'][0]['ports'][0]['native_kappa_ext_GHz'] < 0
    assert out['modes'][0]['ports'][0]['advisory']=='REVIEW_NATIVE_KAPPA_SIGN'
    assert out['modes'][0]['electric_to_magnetic_energy_ratio']==pytest.approx(1/1.1)
    assert out['field_acquisition']['status']=='NO_NATIVE_COMPLEX_FIELD_EXPORT'
    assert out['mode_identity']=='UNRESOLVED'
    assert out['em_to_hamiltonian']=='BLOCKED'
    assert out['fabrication']=='HOLD'



def test_native_csv_fixture_explicit_utf8_even_with_cp1252_default(tmp_path, monkeypatch):
    """Windows ANSI CP1252 cannot encode the real Palace kappa column name.

    Force a CP1252 fallback for any unqualified Path.write_text call to
    reproduce the old Windows failure on otherwise UTF-8 Linux hosts.
    """
    original = Path.write_text
    implicit_writes = []

    def windows_default_write(self, data, *args, **kwargs):
        if 'encoding' not in kwargs or kwargs['encoding'] is None:
            implicit_writes.append(self.name)
            kwargs['encoding'] = 'cp1252'
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', windows_default_write)
    root, manifest = _run(tmp_path)
    assert not implicit_writes, 'Fixture text output depends on platform encoding'
    raw = (root/PREFIX/'port-Q.csv').read_bytes()
    assert 'κ_ext[1] (GHz)'.encode('utf-8') in raw
    assert native_em_evidence(root, manifest)['modes'][0]['ports'][0]['native_kappa_ext_GHz'] < 0


def test_optional_tables_do_not_generate_fabricated_results(tmp_path):
    root,manifest=_run(tmp_path,port=False,energy=False)
    out=native_em_evidence(root,manifest)
    assert out['modes'][0]['ports']==[]
    assert out['modes'][0]['electric_to_magnetic_energy_ratio'] is None
    assert not out['scalar_tables']['port_q']
    assert not out['scalar_tables']['domain_energy']


def test_verified_probe_files_never_become_verified_field_overlap(tmp_path):
    root,manifest=_run(tmp_path,probe=True)
    out=native_em_evidence(root,manifest)
    assert out['field_acquisition']['artifact_count']==1
    assert out['field_acquisition']['status'].startswith('NATIVE_FIELD_FILES_PRESENT')
    assert out['field_acquisition']['common_coordinate_domain_verified'] is False
    assert out['field_acquisition']['complex_vector_normalization_verified'] is False
    assert out['mode_identity']=='UNRESOLVED'


@pytest.mark.parametrize('name,body', [
    ('port-Q.csv','m,Q_ext[1],κ_ext[2] (GHz)\n1,100,0.06\n'),
    ('domain-E.csv','m,E_elec (J),E_mag (J)\n1,1e-12,nan\n'),
    ('eig.csv','m,Re{f} (GHz),Im{f} (GHz),Q\n2,5.9,0,1e5\n'),
    ('eig.csv','m,Re{f} (GHz),Im{f} (GHz),Q\n1,5.9,0,-1\n'),
])
def test_reject_malformed_native_observations(tmp_path,name,body):
    root,manifest=_run(tmp_path)
    (root/PREFIX/name).write_text(body,encoding='utf-8')
    with pytest.raises(NativeEMEvidenceError):
        native_em_evidence(root,manifest)


def _create_symlink_or_skip(link: Path, target: Path):
    """Skip only an OS-impossible symlink; never skip separate security checks.

    Standard Windows accounts commonly raise WinError 1314. Distinguish this
    from unrelated failures (such as I/O errors) which must still fail tests.
    """
    try:
        link.symlink_to(target)
    except NotImplementedError:
        pytest.skip('Symlink-only assertion: host Path.symlink_to is unsupported')
    except OSError as exc:
        winerror = getattr(exc, 'winerror', None)
        unsupported = {errno.EPERM, errno.ENOSYS, errno.EOPNOTSUPP}
        if winerror == 1314 or (winerror is None and exc.errno in unsupported):
            pytest.skip('Symlink-only assertion: host lacks symlink privilege/capability '
                        f'(winerror={winerror}, errno={exc.errno})')
        raise


def test_reject_symlink_native_table(tmp_path):
    """A linked Palace CSV must fail closed when symlinks can be created."""
    root, manifest = _run(tmp_path)
    path = root / PREFIX / 'port-Q.csv'
    path.unlink()
    target = tmp_path / 'outside.csv'
    target.write_text('m,Q_ext[1],kappa_ext[1] (GHz)\n1,1e7,1e-6\n', encoding='utf-8')
    _create_symlink_or_skip(path, target)
    with pytest.raises(NativeEMEvidenceError):
        native_em_evidence(root, manifest)
    assert target.read_text(encoding='utf-8').startswith('m,')


def test_reject_oversized_native_table_without_symlink_privilege(tmp_path):
    """Must execute even on Windows hosts incapable of creating links."""
    root, manifest = _run(tmp_path)
    path = root / PREFIX / 'port-Q.csv'
    path.write_bytes(b'x' * 260000)  # > MAX_TABLE_BYTES, < per-artifact bound
    with pytest.raises(NativeEMEvidenceError, match='oversized'):
        native_em_evidence(root, manifest)


@pytest.mark.parametrize('untrusted_name', [
    '../outside.csv', 'sqe_em/outputFiles/../../../outside.csv',
    '/tmp/outside.csv', r'C:\outside.csv', r'..\outside.csv',
])
def test_native_artifact_traversal_rejected_without_symlink_privilege(tmp_path, untrusted_name):
    """The artifact boundary refuses escape names regardless of link privileges."""
    root, _manifest = _run(tmp_path)
    with pytest.raises(ArtifactInvalid):
        safe_file(root, untrusted_name)


def test_symlink_capability_check_never_masks_unrelated_os_errors(tmp_path, monkeypatch):
    """An unexpected failure must not be misclassified as a platform skip."""
    def unexpected_io_error(self, target, target_is_directory=False):
        raise OSError(errno.EIO, 'Injected disk I/O error')
    monkeypatch.setattr(Path, 'symlink_to', unexpected_io_error)
    with pytest.raises(OSError, match='Injected disk I/O error'):
        _create_symlink_or_skip(tmp_path / 'link', tmp_path / 'target')


def test_native_table_invalid_utf8_is_not_silently_decoded_as_ansi(tmp_path):
    """Only actual UTF-8 observations may pass the Palace parser, even on CP1252 Windows."""
    root, manifest = _run(tmp_path)
    port = root / PREFIX / 'port-Q.csv'
    raw = port.read_bytes()
    assert 'κ_ext'.encode('utf-8') in raw
    port.write_bytes(raw.replace('κ_ext'.encode('utf-8'), b'\x80_ext'))
    with pytest.raises(NativeEMEvidenceError, match='unreadable'):
        native_em_evidence(root, manifest)


def test_non_palace_job_does_not_emit_em_diagnostics(tmp_path):
    assert native_em_evidence(tmp_path,{'engine':'scqubits','kind':'spectrum','artifacts':[]}) is None


REPORT=Path(os.environ.get('SQE_TEST_NATIVE_REPORT','tests/fixtures/optional-native-report.zip'))


def test_actual_uploaded_palace_csv_replay_when_explicitly_available(tmp_path):
    """Optional reference bytes from a real solver, not a native solver test."""
    if not REPORT.is_file():
        pytest.skip('User-supplied native evidence not shipped with release')
    root=tmp_path/'native';folder=root/PREFIX;folder.mkdir(parents=True)
    import hashlib
    with zipfile.ZipFile(REPORT) as z:
        artifacts=[]
        for stem in ('eig','port-Q','domain-E'):
            raw=z.read('native/native_palace_third-'+stem+'.csv')
            path=folder/(stem+'.csv');path.write_bytes(raw)
            artifacts.append({'name':PREFIX+stem+'.csv','sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)})
    out=native_em_evidence(root,{'engine':'sqdmetal_palace','kind':'eigenmode','artifacts':artifacts})
    assert out['modes'][0]['frequency_GHz']==pytest.approx(6.082319401119,rel=1e-9)
    assert out['modes'][0]['ports'][0]['native_kappa_ext_GHz']<0
    assert out['mode_identity']=='UNRESOLVED'


def test_native_em_cross_run_numeric_only_and_port_sign_gate(tmp_path):
    from sqe_studio.interop.native_em_evidence import compare_native_em_evidence
    left_root,left_manifest=_run(tmp_path/'left',negative=False)
    right_root,right_manifest=_run(tmp_path/'right',negative=True)
    a=native_em_evidence(left_root,left_manifest)
    b=native_em_evidence(right_root,right_manifest)
    comparison={'status':'native_mode_index_differences_for_expert_review'}
    result=compare_native_em_evidence(a,b,comparison)
    assert result['status']=='NATIVE_INDEX_SCALAR_DIAGNOSTICS_ONLY'
    assert result['rows'][0]['observable']=='Q_total'
    assert result['rows'][1]['observable']=='Q_ext'
    assert result['rows'][1]['sign_changed']
    assert result['mode_identity']=='UNRESOLVED'
    assert result['optimization']=='BLOCKED'
    assert compare_native_em_evidence(a,b,{'status':'not_comparable'})['rows']==[]
    b['modes'][0]['ports'].pop()
    assert compare_native_em_evidence(a,b,comparison)['status']=='BLOCKED'
