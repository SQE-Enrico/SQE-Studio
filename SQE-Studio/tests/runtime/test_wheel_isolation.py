"""A15 wheel bootstrap regression: real venv identity and simulated Windows failure.

No test substitutes fixture acceptance for a native solver or for host Windows.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import sys
import tempfile

import pytest

from sqe_studio import qualification as q

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def private_tmp_path():
    """Use the same stdlib-managed private workspace as Automatic Test.

    pytest's ``tmp_path`` on some Windows hosts is beneath a long-name
    profile redirector, while ``tempfile.TemporaryDirectory`` (used by the
    real qualification runner) resolves to a different, working spelling.
    A positive *real interpreter* test must reproduce the actual production
    provisioning context; it must still run the exact isolation proof.
    All files are removed after the test; no project or user data is read.
    """
    with tempfile.TemporaryDirectory(prefix='sqe-a15-private-') as directory:
        yield Path(directory)


def test_windows_bootstrap_preserves_real_profile_but_not_python_or_pip_leaks():
    """A synthetic qualification profile must not redirect CPython's venv."""
    requested = {'HOME': r'C:\qualification\home',
                 'USERPROFILE': r'C:\qualification\home',
                 'PYTHONPATH': 'injected', 'PYTHONHOME': 'injected',
                 'VIRTUAL_ENV': 'injected', 'PIP_USER': 'yes',
                 'PIP_CONFIG_FILE': r'C:\untrusted\pip.ini',
                 'KEEP_QUALIFICATION_CONTEXT': 'safe'}
    original = {'HOME': r'C:\Users\RealProfile',
                'USERPROFILE': r'C:\Users\RealProfile',
                'HOMEDRIVE': 'C:', 'HOMEPATH': r'\Users\RealProfile'}
    result = q._private_wheel_environment(requested, windows=True, host=original)
    assert result['USERPROFILE'] == original['USERPROFILE']
    assert result['HOME'] == original['HOME']
    assert result['HOMEDRIVE'] == 'C:'
    assert result['KEEP_QUALIFICATION_CONTEXT'] == 'safe'
    assert not {'PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','PIP_USER'} & result.keys()
    assert result['PIP_NO_INDEX'] == result['PYTHONNOUSERSITE'] == '1'
    assert result['PIP_NO_CACHE_DIR'] == '1'
    assert result['PIP_CONFIG_FILE'] == os.devnull


def test_non_windows_bootstrap_keeps_private_test_home():
    requested = {'HOME': '/tmp/sqe-test/home', 'USERPROFILE': 'private',
                 'PYTHONPATH': 'unsafe'}
    result = q._private_wheel_environment(requested, windows=False,
                                          host={'HOME': '/real/home'})
    assert result['HOME'] == '/tmp/sqe-test/home'
    assert result['USERPROFILE'] == 'private'
    assert 'PYTHONPATH' not in result


def _native_venv_host() -> Path:
    """Use the actual CPython base executable, not a Windows venv redirector.

    This mirrors the working production no-pip fallback seen in the Windows
    Automatic Test.  The original tests used sys.executable (an already
    managed venv redirector), whose nested-venv path may point elsewhere.
    This does NOT relax the probe: its freshly created child's -I prefix,
    executable and nonce marker must still be validated independently.
    """
    base = Path(getattr(sys, '_base_executable', sys.executable))
    return base if base.is_file() else Path(sys.executable)


def _native_venv_env(work: Path) -> dict[str, str]:
    """Mirror qualify()'s private *process* context, including profile paths.

    On managed Windows installs the environment passed to venv matters as much
    as the selected executable. Tests must not compare a default user profile
    against a separately redirected, production-only profile: that recreates
    the older PREFIX_MISMATCH false negative.
    """
    home = work / 'home'
    home.mkdir(exist_ok=True)
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'PYTHONSTARTUP',
                'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER', 'PIP_REQUIRE_VIRTUALENV'):
        env.pop(key, None)
    env.update({'HOME': str(home), 'USERPROFILE': str(home),
                'XDG_CACHE_HOME': str(work / 'cache'),
                'XDG_CONFIG_HOME': str(work / 'config'),
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                'PYTHONNOUSERSITE': '1', 'PIP_CONFIG_FILE': os.devnull,
                'PIP_NO_INDEX': '1', 'PIP_NO_CACHE_DIR': '1',
                'PIP_DISABLE_PIP_VERSION_CHECK': '1'})
    return env


@pytest.fixture(scope='module')
def verified_production_private_venv():
    """Share one *real* private install made by the production code path.

    The previous helper used base-Python ``-m venv --without-pip`` while the
    real wheel gate successfully used ``_isolated_wheel_install``. Windows
    managed scientific interpreters can bootstrap those two paths differently,
    creating a false negative in four tests. Exercise the actual production
    provisioning, which must verify interpreter identity and installed wheel
    provenance. A failed identity proof is a hard test failure, not a skip.
    """
    if not q.available('setuptools.build_meta'):
        pytest.skip('Offline package backend unavailable for production venv test')
    with tempfile.TemporaryDirectory(prefix='sqe-a15-production-') as directory:
        work = Path(directory)
        wheels = work / 'wheels'
        wheels.mkdir()
        env = _native_venv_env(work)
        code, log, _ = q._run(
            [sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps',
             '--no-build-isolation', '--wheel-dir', str(wheels), str(ROOT)],
            work, env, 120)
        assert code == 0, 'Offline source wheel build failed: ' + log[-1200:]
        wheel_files = list(wheels.glob('*.whl'))
        assert len(wheel_files) == 1
        # No monkeypatch of _run, and no synthetic acceptance of a venv.
        ready, interpreter, steps, _fallback = q._isolated_wheel_install(
            ROOT, wheel_files[0], work, env)
        assert ready and interpreter is not None, (
            'Production fresh private install and identity proof failed: ' +
            repr([(name, code, output[-900:]) for name, code, output, _ in steps]))
        private = interpreter.parent.parent
        assert private != Path(sys.prefix)
        assert (private / 'pyvenv.cfg').is_file()
        yield private, interpreter, env, work


def _create_verified_private_venv(production):
    """Use the same verified private interpreter as installed_wheel gate."""
    private, interpreter, clean, work = production
    code, log, _ = q._isolated_venv_probe(interpreter, private, work, clean)
    assert code == 0 and log.strip() == 'ISOLATED_VENV_OK', log
    return private, interpreter, clean, work


@pytest.mark.skipif(os.name != 'nt', reason='Windows base executable selection')
def test_windows_base_executable_is_used_before_managed_redirector(tmp_path, monkeypatch):
    """On Windows a managed venv redirector must not bootstrap another venv."""
    wheel=tmp_path/'fixture.whl';wheel.write_bytes(b'fixture only: no real install')
    base=tmp_path/'native-python.exe';base.write_bytes(b'fake')
    calls=[]
    monkeypatch.setattr(q.sys, 'base_prefix', str(tmp_path), raising=False)
    # The mocked base lives in the expected Windows base location.
    native=tmp_path/'python.exe';native.write_bytes(b'fixture')
    monkeypatch.setattr(q.sys, 'executable', str(tmp_path/'managed-venv'/'python.exe'))
    def child(command, cwd, env, timeout):
        calls.append(command)
        return 1,'provisioning was refused (synthetic)',0.1
    monkeypatch.setattr(q,'_run',child)
    ok, python, steps, fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert not ok and python is None and fallback
    assert calls[0][0] == str(native)
    assert calls[0][1:4] == ['-m','venv','--copies']


def test_venv_probe_does_not_accept_parent_interpreter(tmp_path):
    code, log, _ = q._isolated_venv_probe(Path(sys.executable), tmp_path,
                                           tmp_path, os.environ.copy())
    assert code != 0
    assert 'ISOLATION_FAILED' in log


def test_windows_style_venv_create_failure_uses_separate_verified_fallback(tmp_path, monkeypatch):
    """WinError 2 at ensurepip may not imply the base installation is broken."""
    wheel = tmp_path/'newly-built.whl'
    wheel.write_bytes(b'fixture; stubbed _run never installs this')
    history = []
    def child(command, cwd, env, timeout):
        history.append(command)
        if command[1:3] == ['-m', 'venv'] and '--without-pip' not in command:
            return 1, 'WinError 2: virtualenv script redirection', 1.0
        if command[1:3] == ['-m', 'venv']:
            return 0, '', 1.0
        if '--python' in command:
            assert '--no-index' in command and '--no-deps' in command
            assert '--isolated' in command and '-I' in command
            assert str(wheel) in command
            return 0, 'Successfully installed', 1.0
        if any('verify_installed_wheel.py' in str(arg) for arg in command):
            assert command[1] == '-I'
            return 0, '{"venv_isolation":true,"status":"PASS"}', 1.0
        raise AssertionError(command)
    monkeypatch.setattr(q, '_run', child)
    monkeypatch.setattr(q, '_isolated_venv_probe', lambda *args: (0, 'ISOLATED_VENV_OK', 0.1))
    ok, python, steps, retry = q._isolated_wheel_install(ROOT, wheel, tmp_path, os.environ.copy())
    assert ok is True and python is not None and retry is True
    assert steps[0][1] == 1 and 'WinError 2' in steps[0][2]
    assert any('without ensurepip' in label and code == 0 for label,code,_,_ in steps)
    assert any('hash/import' in label and code == 0 for label,code,_,_ in steps)
    assert history[1][-2] == '--without-pip'
    assert 'install-env-no-pip' in str(python)


def test_fallback_cannot_promote_wheel_with_bad_provenance(tmp_path, monkeypatch):
    wheel = tmp_path/'built.whl';wheel.write_bytes(b'fixture')
    def child(command, cwd, env, timeout):
        if command[1:3] == ['-m', 'venv']:
            return (1, 'WinError 2', 0.1) if '--without-pip' not in command else (0,'',0.1)
        if '--python' in command:
            return 0,'pip succeeded',0.1
        if any('verify_installed_wheel.py' in str(arg) for arg in command):
            return 1,'Installed server.py does not match the fresh wheel',0.1
        raise AssertionError(command)
    monkeypatch.setattr(q, '_run', child)
    monkeypatch.setattr(q, '_isolated_venv_probe',lambda *args:(0,'ISOLATED_VENV_OK',0.1))
    ok, python, steps, retry = q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert ok is False and python is None and retry is True
    assert steps[-1][1] == 1
    assert 'does not match' in steps[-1][2]


def test_wheel_install_failure_does_not_retry_unrelated_failure(tmp_path, monkeypatch):
    wheel=tmp_path/'built.whl';wheel.write_bytes(b'fixture')
    history=[]
    def child(command,cwd,env,timeout):
        history.append(command)
        if command[1:3] == ['-m','venv']:
            return 0,'',0.1
        if 'install' in command:
            return 1,'corrupt wheel hash/metadata',0.1
        raise AssertionError(command)
    monkeypatch.setattr(q,'_run',child)
    monkeypatch.setattr(q,'_isolated_venv_probe',lambda *args:(0,'ISOLATED_VENV_OK',0.1))
    ok, python, steps, retry=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert not ok and python is None and not retry
    assert steps[-1][1] == 1
    assert not any('--without-pip' in c for c in history)


def test_isolated_private_fallback_real_install_and_provenance(private_tmp_path, monkeypatch):
    """Offline real pip wheel -> forced fallback -> byte-verified installed import.

    This is software packaging evidence only and is not Windows/Palace proof.
    """
    if not q.available('setuptools.build_meta'):
        pytest.skip('Offline wheel build backend absent')
    # Production puts the private venv directly beneath the same temporary
    # qualification root as its HOME and wheels; avoid an extra nested stage
    # that behaves differently with Windows profile redirectors.
    wheels=private_tmp_path/'wheel';wheels.mkdir()
    stage=private_tmp_path
    env = _native_venv_env(private_tmp_path)
    code,output,_=q._run([sys.executable,'-m','pip','wheel','--no-index',
                          '--no-deps','--no-build-isolation','--wheel-dir',str(wheels),
                          str(ROOT)],private_tmp_path,env,90)
    assert code == 0, output[-2000:]
    wheel, = list(wheels.glob('*.whl'))
    actual = q._run
    def fail_first(command,cwd,env,timeout):
        if command[1:3] == ['-m','venv'] and '--without-pip' not in command:
            return 1,'synthetic WinError 2: first bootstrap failed',0.1
        return actual(command,cwd,env,timeout)
    monkeypatch.setattr(q,'_run',fail_first)
    ok, python, steps, fallback=q._isolated_wheel_install(ROOT,wheel,stage,env)
    assert fallback and ok and python is not None, steps
    assert steps[0][1] == 1
    assert steps[-1][1] == 0 and 'venv_isolation' in steps[-1][2]
    code,log,_=actual([str(python),'-I',str(ROOT/'scripts/qualification_installed_smoke.py')],stage,env,75)
    assert code == 0, log[-2000:]
    assert 'No native EM solve' in log


def test_unified_diagnostic_summary_is_not_physical_approval(tmp_path, monkeypatch):
    """Report coverage is derived from checked subreports, never old Palace output."""
    import hashlib
    import json
    import zipfile
    from sqe_studio.feedback_qualification import qualify_eda_feedback, _checked_members
    from sqe_studio import qualification as qual

    source = tmp_path/'srcroot'
    (source/'src/sqe_studio').mkdir(parents=True)
    (source/'src/sqe_studio/server.py').touch()
    (source/'src/sqe_studio/worker.py').touch()
    def synthetic_subreport(root, dest, *, profile, **kwargs):
        if profile == 'comprehensive':
            doc={'schema':'synthetic.software.v1','profile':profile,
                 'gates':[{'id':'installed_wheel','status':'FAIL'},
                          {'id':'installed_assets','status':'BLOCKED'}],
                 'counts':{'PASS':0,'FAIL':1,'BLOCKED':1},
                 'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}
        else:
            doc={'schema':'synthetic.native.v1','profile':profile,
                 'stages':[{'id':'native_palace_solve','status':'BLOCKED'}],
                 'counts':{'PASS':0,'FAIL':0,'BLOCKED':1},
                 'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE'}
        content={'QUALIFICATION.json':json.dumps(doc).encode(), 'SUMMARY.md':b'fixture only'}
        content['INTEGRITY.json']=json.dumps({'files':{
            name:hashlib.sha256(raw).hexdigest() for name,raw in content.items()}}).encode()
        with zipfile.ZipFile(dest,'w') as archive:
            for name,raw in content.items():archive.writestr(name,raw)
        return doc
    monkeypatch.setattr(qual,'qualify',synthetic_subreport)
    path=tmp_path/'feedback.zip'
    result=qualify_eda_feedback(source,path,em_options={
        'reviewer':'SQEFixedProtocol','acknowledged':True,'solve':True,'refine':True})
    coverage=result['diagnostic_coverage']
    assert coverage['installed_wheel']=='FAIL'
    assert coverage['installed_assets']=='BLOCKED'
    assert coverage['native_palace_solve']=='BLOCKED'
    assert coverage['complex_field_mode_identity']=='BLOCKED'
    assert coverage['fabrication']=='HOLD'
    assert coverage['native_palace_refinement']=='NOT_REPORTED'
    assert 'NOT a physics approval' in _checked_members(path)['SUMMARY.md'].decode()
    assert result['scientific_qualification']=='NOT_ESTABLISHED'


def test_windows_missing_copied_redirector_attempts_independent_symlink_venv(tmp_path, monkeypatch):
    """A second WinError 2 cannot justify using base Python as wheel evidence."""
    wheel=tmp_path/'verified.whl';wheel.write_bytes(b'fixture: mock only')
    history=[]
    def child(command,cwd,env,timeout):
        history.append(command)
        if command[1:3]==['-m','venv']:
            if '--symlinks' in command:
                return 0,'alternate created',0.1
            return 1,'WinError 2: missing copied launcher',0.1
        if '--python' in command:
            assert 'install-env-symlink' in ' '.join(command)
            return 0,'installer returned',0.1
        if any('verify_installed_wheel.py' in str(a) for a in command):
            return 0,'verified expected hash/import',0.1
        raise AssertionError(command)
    monkeypatch.setattr(q,'_run',child)
    monkeypatch.setattr(q,'_isolated_venv_probe',lambda *args:(0,'ISOLATED_VENV_OK',0.1))
    ok,python,steps,fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert ok and fallback and python is not None and 'install-env-symlink' in str(python)
    assert len([x for x in history if '--symlinks' in x])==1
    assert any('alternate no-pip symlink' in label for label, *_ in steps)


def test_cannot_claim_install_when_both_fallback_venvs_fail(tmp_path,monkeypatch):
    wheel=tmp_path/'verified.whl';wheel.write_bytes(b'fixture: mock only')
    monkeypatch.setattr(q,'_run', lambda *args:(1,'WinError 2: missing executable',0.1))
    ok,python,steps,fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert not ok and python is None and fallback
    assert all(code==1 for _,code,_,_ in steps)
    assert len(steps) >= 3  # third route when base and active launchers differ
    assert not any('fallback pip into' in name for name, *_ in steps)


def test_windows_no_pip_venv_claims_wrong_prefix_uses_alternate_then_verifies(tmp_path,monkeypatch):
    wheel=tmp_path/'verified.whl';wheel.write_bytes(b'fixture: mock only')
    history=[]
    def child(command,cwd,env,timeout):
        history.append(command)
        if command[1:3] == ['-m','venv'] and '--without-pip' not in command:
            return 1,'WinError 2: initial ensurepip',0.1
        if command[1:3] == ['-m','venv']:
            return 0,'venv created',0.1
        if '--python' in command:
            return 0,'installed',0.1
        if any('verify_installed_wheel.py' in str(a) for a in command):
            return 0,'{"status":"PASS"}',0.1
        raise AssertionError(command)
    def probe(python,env,*args):
        if 'install-env-no-pip' in str(python):
            return 1,'ISOLATION_FAILED: sys.prefix points to base',0.1
        return 0,'ISOLATED_VENV_OK',0.1
    monkeypatch.setattr(q,'_run',child)
    monkeypatch.setattr(q,'_isolated_venv_probe',probe)
    ok,python,steps,fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert ok and fallback and python is not None
    assert any(label=='alternate interpreter/prefix identity' and code==0
               for label,code,_,_ in steps)
    assert python.parent.parent.name in ('install-env-symlink', 'install-env-native-base')
    assert any(label=='fallback interpreter/prefix identity' and code==1
               for label,code,_,_ in steps)


def test_neither_fallback_interpreter_identity_is_good_never_pip(tmp_path,monkeypatch):
    wheel=tmp_path/'fixture.whl';wheel.write_bytes(b'fixture')
    invocations=[]
    def cmd(command,cwd,env,timeout):
        invocations.append(command)
        return (1,'WinError 2',0.1) if '--without-pip' not in command else (0,'',0.1)
    monkeypatch.setattr(q,'_run',cmd)
    monkeypatch.setattr(q,'_isolated_venv_probe',lambda *args:(1,'ISOLATION_FAILED',0.1))
    ok,python,steps,fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert not ok and python is None and fallback
    assert not any('--python' in cmdline for cmdline in invocations)
    assert any('alternate after invalid copied venv identity'==s[0] for s in steps)


def test_stale_rc14_8_release_test_detected_but_never_modified(tmp_path):
    legacy = tmp_path/'tests/integration/test_rc14_8_a99_release.py'
    legacy.parent.mkdir(parents=True)
    assert not q._stale_release_test_present(tmp_path)
    legacy.write_bytes(b'old personal test: must not be deleted or ignored')
    assert q._stale_release_test_present(tmp_path)
    assert legacy.read_bytes() == b'old personal test: must not be deleted or ignored'
    assert 'tests/integration/test_rc14_8_a99_release.py' not in json.loads((ROOT/'EDA_SOURCE_MANIFEST.json').read_text())['files']


def test_isolation_probe_rejects_system_site_configuration_before_execution(tmp_path, monkeypatch):
    private = tmp_path/'private';private.mkdir()
    (private/'pyvenv.cfg').write_text('include-system-site-packages = true\n')
    monkeypatch.setattr(q,'_run',lambda *args:pytest.fail('must reject unsafe config before launch'))
    code,log,_ = q._isolated_venv_probe(Path(sys.executable),private,tmp_path,os.environ.copy())
    assert code == 1 and log == 'ISOLATION_FAILED: SYSTEM_SITE_ENABLED_OR_UNKNOWN'


def test_real_no_pip_environment_has_verified_private_prefix(verified_production_private_venv):
    env, python, clean, work = _create_verified_private_venv(verified_production_private_venv)
    code, log, _ = q._isolated_venv_probe(python, env, work, clean)
    assert code == 0 and log.strip() == 'ISOLATED_VENV_OK', log
    assert str(work) not in log


def test_windows_redirector_active_interpreter_recovery_requires_verified_isolation(tmp_path,monkeypatch):
    wheel=tmp_path/'fixture.whl';wheel.write_bytes(b'fixture; mock-only')
    separate_base=tmp_path/'base-python';separate_base.write_bytes(b'fake')
    monkeypatch.setattr(q.sys,'_base_executable',str(separate_base),raising=False)
    calls=[]
    def command(argv,cwd,env,timeout):
        calls.append(argv)
        if argv[1:3]==['-m','venv']:
            return (1,'simulated WinError 2: first path',0.1) if '--without-pip' not in argv else (0,'created',0.1)
        if '--python' in argv:
            assert 'install-env-active' in ' '.join(argv)
            return 0,'isolated pip installed',0.1
        if any('verify_installed_wheel.py' in item for item in argv):
            return 0,'verified installed file hashes',0.1
        raise AssertionError(argv)
    def probe(python,environment,*args):
        if environment.name != 'install-env-active':
            return 1,'ISOLATION_FAILED: PREFIX_MISMATCH',0.1
        return 0,'ISOLATED_VENV_OK',0.1
    monkeypatch.setattr(q,'_run',command)
    monkeypatch.setattr(q,'_isolated_venv_probe',probe)
    ok,python,steps,fallback=q._isolated_wheel_install(ROOT,wheel,tmp_path,os.environ.copy())
    assert ok and fallback and python.parent.parent.name == 'install-env-active'
    assert any(label=='alternate active-interpreter no-pip venv' for label,*_ in steps)
    assert sum(1 for label,code,_,_ in steps if 'identity' in label and code==1)>=2
    assert not any('--python' in argv for argv in calls[:-2])


def test_both_stale_release_files_detected_without_mutation(tmp_path):
    folder=tmp_path/'tests/integration';folder.mkdir(parents=True)
    expected={}
    for old in ('8','9','10'):
        filename=f'test_rc14_{old}_a99_release.py'
        body=f'legacy release test {old}'.encode()
        (folder/filename).write_bytes(body)
        expected[filename]=body
    assert set(q._stale_release_tests(tmp_path))==set(expected)
    assert all((folder/name).read_bytes()==data for name,data in expected.items())
    assert not set('tests/integration/' + name for name in q._stale_release_tests(ROOT)) & set(json.loads((ROOT/'EDA_SOURCE_MANIFEST.json').read_text())['files'])


def test_private_venv_marker_is_ephemeral_and_non_disclosing(verified_production_private_venv):
    """A *verified* real no-pip environment never retains its private nonce."""
    env, python, clean, work = _create_verified_private_venv(verified_production_private_venv)
    code, log, _ = q._isolated_venv_probe(python, env, work, clean)
    assert code == 0 and log.strip() == 'ISOLATED_VENV_OK', log
    assert not (env / '.sqe-private-venv-probe').exists()
    assert str(work) not in log


def test_private_venv_probe_rejects_unrelated_python_even_with_expected_marker(verified_production_private_venv, monkeypatch):
    """An unrelated interpreter cannot impersonate the private prefix."""
    env, interpreter, clean, work = _create_verified_private_venv(verified_production_private_venv)
    actual = q._run

    def redirected_to_base(argv, cwd, child_env, timeout):
        if len(argv) > 3 and argv[1:3] == ['-I', '-c']:
            return actual([str(_native_venv_host()), *argv[1:]], cwd, child_env, timeout)
        return actual(argv, cwd, child_env, timeout)

    monkeypatch.setattr(q, '_run', redirected_to_base)
    code, log, _ = q._isolated_venv_probe(interpreter, env, work, clean)
    assert code == 1
    assert 'ISOLATION_FAILED:' in log
    assert 'PREFIX_MISMATCH' in log
    assert not (env / '.sqe-private-venv-probe').exists()
    assert str(work) not in log


def test_private_marker_allows_windows_redirected_spelling_only_after_proof(verified_production_private_venv, monkeypatch):
    """After real prefix proof, an alias of a path is not an isolation failure."""
    env, interpreter, clean, work = _create_verified_private_venv(verified_production_private_venv)
    original = q._run

    def fake_windows_alias(argv, cwd, child_env, timeout):
        if len(argv) > 3 and argv[1:3] == ['-I', '-c']:
            argv = list(argv)
            argv[3] = argv[3].replace(
                'same=lambda a,b: os.path.samefile(a,b) if os.path.exists(a) and os.path.exists(b) else False; ',
                'same=lambda a,b: False; os.name="nt"; ')
            argv[3] = argv[3].replace(
                'os.path.basename(sys.executable).lower()=="python.exe"',
                'os.path.basename(sys.executable).lower().startswith("python")')
        return original(argv, cwd, child_env, timeout)

    monkeypatch.setattr(q, '_run', fake_windows_alias)
    code, log, _ = q._isolated_venv_probe(interpreter, env, work, clean)
    assert code == 0, log
    assert log.strip() == 'ISOLATED_VENV_OK'
    assert not (env / '.sqe-private-venv-probe').exists()
