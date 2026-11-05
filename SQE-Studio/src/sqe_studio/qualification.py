"""Isolated laptop qualification for the integrated EDA product.

This is test infrastructure, never an engine, optimizer or production HTTP API.
No online installation, project-home access, user design mutation or mock scientific
output. Every external process is bounded and executes with a private temp HOME.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from importlib import metadata
import json
import os
import platform
import re
import secrets
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA = 'sqe.laptop-eda-qualification.v1'
MAX_LOG = 160000
DEFAULT_TIMEOUT = 240


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_log(text: str, substitutions: tuple[str, ...]) -> str:
    """Best-effort output minimization; test data only, no private projects read."""
    for value in sorted((s for s in substitutions if s), key=len, reverse=True):
        text = text.replace(value, '[local-path]')
    text = re.sub(r'(?i)(token|password|secret|authorization|cookie|csrf)(\s*[:=]\s*)(\S+)',
                  r'\1\2[REDACTED]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[email]', text)
    text = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]', text)
    # Subprocesses sometimes print canonical rather than configured Windows
    # profile path spellings. Never ship user/profile names in verbose logs.
    # Windows subprocess output may escape each backslash once or twice.
    # Match the entire user-name component in both spellings without copying
    # account names into support logs. Redact even when the temporary-root
    # path was printed using an alternate spelling.
    text = re.sub(r"(?i)[A-Z]:[/\\]+(?:Users|Documents and Settings)[/\\]+[^/\\\s\"'`,;:]+",
                  "[user-home]", text)
    text = re.sub(r"/(?:home|Users)/[^/\s\"']+", "[user-home]", text)
    if len(text) > MAX_LOG:
        text = text[:MAX_LOG//2] + '\n[LOG TRUNCATED]\n' + text[-MAX_LOG//2:]
    return text


def _isolated_test_diagnostics(work: Path, label: str, substitutions: tuple[str, ...]) -> str:
    """Capture bounded failure diagnostics from THIS run's synthetic test workspace.

    Never inspect project/user folders, only the qualification temp directory.
    Stderr may contain filesystem paths; sanitize before adding to report.
    """
    directory = work / ('pytest-' + label)
    if not directory.is_dir():
        return ''
    allowed = {'LIFECYCLE_FAILURE.json', 'VALIDATION_FAILURE.json',
               'FAILURE.json', 'engine.log', 'josephson_native_stderr.log',
               'josephson_native_stdout.log'}
    entries = []
    for file in sorted(directory.rglob('*')):
        if len(entries) >= 24:
            break
        if file.name not in allowed or file.is_symlink() or not file.is_file():
            continue
        if not file.resolve().is_relative_to(directory.resolve()):
            continue
        try:
            if file.stat().st_size > 8192:
                content = '[File larger than 8 KiB; diagnostic omitted]'
            else:
                content = file.read_bytes().decode('utf-8', 'replace')
        except OSError:
            continue
        entries.append(f'[{file.name} sha256={sha(file.read_bytes()) if file.stat().st_size <= 8192 else "large"}]\n'+content)
    if not entries:
        return ''
    return '\nISOLATED NATIVE/WORKER FAILURE FILES (not solver acceptance):\n' + _safe_log('\n'.join(entries), substitutions)


def available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _package_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except (metadata.PackageNotFoundError, ValueError):
        return None


def _run(command: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int | None, str, float]:
    """Bound entire descendant process group (browser/solver may spawn children).

    Prevents a timed-out Playwright/Julia subprocess retaining stdout pipes and
    trapping the GUI test runner indefinitely after the parent is terminated.
    """
    start = time.monotonic()
    process = None
    try:
        options = {'cwd':str(cwd), 'env':env, 'stdout':subprocess.PIPE,
                   'stderr':subprocess.STDOUT, 'stdin':subprocess.DEVNULL}
        if os.name == 'nt':
            options['creationflags'] = getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        else:
            options['start_new_session'] = True
        process = subprocess.Popen(command, **options)
        try:
            out, _ = process.communicate(timeout=timeout)
            return process.returncode, out.decode('utf-8','replace'), round(time.monotonic()-start,2)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                try:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL, timeout=8,check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            else:
                try:os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:pass
            # Windows taskkill can already reap the process tree; a second
            # kill may raise ProcessLookupError and must not erase timeout evidence.
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:out,_ = process.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                if process.stdout:process.stdout.close()
                out=b''
            return None, out.decode('utf-8','replace')+'\nTIMEOUT: child process tree deadline exceeded',round(time.monotonic()-start,2)
    except OSError as error:
        return None, 'SPAWN FAILED: '+type(error).__name__+': '+str(error),round(time.monotonic()-start,2)



def _isolated_venv_probe(python: Path, environment: Path, cwd: Path,
                         env: dict) -> tuple[int | None, str, float]:
    """Prove the *executed* interpreter belongs to the fresh private venv.

    CPython on Windows may report a redirected ``sys.executable`` or a short
    AppData spelling. File-identity/lexical equality can then reject a real
    isolated environment. A fresh random file *inside the expected prefix*
    proves prefix identity without trusting spelling or weakening isolation.

    The child still checks -I/no user site, a separate base prefix, and the
    actual private ``pyvenv.cfg``. An unrelated Python or copied marker cannot
    pass. No local paths or random marker contents enter portable logs.
    """
    if environment.is_symlink():
        return 1, 'ISOLATION_FAILED: LINKED_PRIVATE_ENV', 0.0
    config = environment / 'pyvenv.cfg'
    if config.is_symlink():
        return 1, 'ISOLATION_FAILED: LINKED_PRIVATE_VENV_CONFIG', 0.0
    if config.is_file():
        try:
            settings = dict(line.split('=', 1) for line in config.read_text(
                encoding='utf-8-sig').splitlines() if '=' in line)
            system_site = next((v.strip().lower() for k,v in settings.items()
                                if k.strip().lower() == 'include-system-site-packages'), None)
        except (OSError, UnicodeError):
            return 1, 'ISOLATION_FAILED: UNREADABLE_PRIVATE_VENV_CONFIG', 0.0
        if system_site != 'false':
            return 1, 'ISOLATION_FAILED: SYSTEM_SITE_ENABLED_OR_UNKNOWN', 0.0
    # The marker is created ONLY after a real venv config exists. Mocked
    # subprocess tests with no filesystem venv still exercise their fake _run.
    marker = environment / '.sqe-private-venv-probe'
    token = secrets.token_hex(32)
    marked = False
    if config.is_file():
        try:
            if marker.is_symlink() or marker.exists():
                return 1, 'ISOLATION_FAILED: EXISTING_PRIVATE_MARKER', 0.0
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w', encoding='ascii') as stream:
                stream.write(token)
            marked = True
        except OSError:
            return 1, 'ISOLATION_FAILED: PRIVATE_MARKER_WRITE_FAILED', 0.0
    # The expected path, even if a redirected spelling, is required to have
    # exactly the same unpredictable content as the executed prefix path.
    # The marker never substitutes for the actual CPython isolation checks.
    check = (
        'import os,sys,hmac,json; '
        'same=lambda a,b: os.path.samefile(a,b) if os.path.exists(a) and os.path.exists(b) else False; '
        'reasons=[]; '
        'cfg=os.path.join(sys.prefix,"pyvenv.cfg"); '
        'expected_cfg=os.path.join(sys.argv[1],"pyvenv.cfg"); '
        'reasons.extend(["MISSING_PRIVATE_VENV_CONFIG"] if not os.path.isfile(cfg) or not os.path.isfile(expected_cfg) else []); '
        'reasons.extend(["INTERPRETER_FLAGS"] if not (sys.flags.isolated and sys.flags.no_user_site) else []); '
        'reasons.extend(["BASE_PREFIX_REUSED"] if sys.prefix==sys.base_prefix or same(sys.prefix,sys.base_prefix) else []); '
        'read=lambda p: open(p,"rb").read(128) if os.path.isfile(p) else b""; '
        'marker=".sqe-private-venv-probe"; '
        'valid=lambda b: bool(b) and hmac.compare_digest(b,sys.argv[3].encode("ascii")); '
        'prefix_valid=valid(read(os.path.join(sys.prefix,marker))) and valid(read(os.path.join(sys.argv[1],marker))); '
        'reasons.extend(["PREFIX_MISMATCH"] if not (same(sys.prefix,sys.argv[1]) or prefix_valid) else []); '
        'reasons.extend(["EXECUTABLE_MISMATCH"] if not (same(sys.executable,sys.argv[2]) or (os.name=="nt" and prefix_valid and os.path.basename(sys.executable).lower()=="python.exe")) else []); '
        'print("ISOLATION_FAILED: "+",".join(reasons) if reasons else "ISOLATED_VENV_OK"); '
        'print("SQE_ISOLATION_FLAGS="+json.dumps({"os":os.name,'
        '"isolated":bool(sys.flags.isolated),"no_user_site":bool(sys.flags.no_user_site),'
        '"prefix_eq_base":sys.prefix==sys.base_prefix,'
        '"expected_prefix_samefile":same(sys.prefix,sys.argv[1]),'
        '"interpreter_samefile":same(sys.executable,sys.argv[2]),'
        '"marker_matches_both_prefixes":prefix_valid,'
        '"expected_pyvenv_cfg":os.path.isfile(expected_cfg),'
        '"active_pyvenv_cfg":os.path.isfile(cfg),'
        '"interpreter_name":os.path.basename(sys.executable)},sort_keys=True)) if reasons else None; '
        'print("SQE_ISOLATION_PATH_RELATIONS="+json.dumps({'
        '"prefix_normcase_eq_expected":os.path.normcase(os.path.abspath(sys.prefix))==os.path.normcase(os.path.abspath(sys.argv[1])),'
        '"prefix_realpath_eq_expected":os.path.normcase(os.path.realpath(sys.prefix))==os.path.normcase(os.path.realpath(sys.argv[1])),'
        '"interpreter_normcase_eq_requested":os.path.normcase(os.path.abspath(sys.executable))==os.path.normcase(os.path.abspath(sys.argv[2])),'
        '"interpreter_realpath_eq_requested":os.path.normcase(os.path.realpath(sys.executable))==os.path.normcase(os.path.realpath(sys.argv[2])),'
        '"prefix_marker_present":os.path.isfile(os.path.join(sys.prefix,marker)),'
        '"expected_marker_present":os.path.isfile(os.path.join(sys.argv[1],marker)),'
        '"active_prefix_is_link":os.path.islink(sys.prefix),'
        '"expected_prefix_is_link":os.path.islink(sys.argv[1]),'
        '"active_executable_is_link":os.path.islink(sys.executable),'
        '"active_cfg_samefile_expected_cfg":same(cfg,expected_cfg),'
        '"cwd_in_expected_prefix":os.path.normcase(os.path.abspath(os.getcwd())).startswith(os.path.normcase(os.path.abspath(sys.argv[1]))+os.sep),'
        '"pythonhome_present":bool(os.environ.get("PYTHONHOME")),'
        '"pythonpath_present":bool(os.environ.get("PYTHONPATH")),'
        '"virtual_env_present":bool(os.environ.get("VIRTUAL_ENV")),'
        '"venv_executable_exists":os.path.isfile(sys.argv[2]),'
        '"expected_prefix_exists":os.path.isdir(sys.argv[1])},sort_keys=True)) if reasons else None; '
        'sys.exit(bool(reasons))'
    )
    try:
        return _run([str(python), '-I', '-c', check, str(environment),
                     str(python), token], cwd, env, 20)
    finally:
        if marked:
            try:
                marker.unlink()
            except OSError:
                pass


def _private_wheel_environment(requested: dict[str, str], *,
                               windows: bool | None = None,
                               host: dict[str, str] | None = None) -> dict[str, str]:
    """Isolate pip while preserving the real Windows profile for CPython venv.

    Automatic Test runs with a synthetic HOME/USERPROFILE. On some managed
    Windows 3.11 installations the CPython venv redirector resolves its child
    through that synthetic profile, causing the child to run in the *parent*
    scientific venv. The probe correctly rejects that child. Preserve the
    native host-profile variables only for the separate wheel bootstrap.

    Pip still has no index, no cache, no user site/config, no inherited Python
    import path, and all installation targets remain explicitly private.
    This never converts a failed interpreter identity into PASS.
    """
    result = requested.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PYTHONSTARTUP',
                'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER', 'PIP_REQUIRE_VIRTUALENV'):
        result.pop(key, None)
    if windows if windows is not None else os.name == 'nt':
        actual = os.environ if host is None else host
        for key in ('HOME', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH'):
            # Do not invent a synthetic profile when the host has none.
            if actual.get(key):
                result[key] = actual[key]
            else:
                result.pop(key, None)
    result.update({'PIP_CONFIG_FILE': os.devnull, 'PIP_NO_INDEX': '1',
                   'PIP_NO_CACHE_DIR': '1', 'PYTHONNOUSERSITE': '1',
                   'PIP_DISABLE_PIP_VERSION_CHECK': '1'})
    return result


def _isolated_wheel_install(root: Path, wheel: Path, work: Path,
                            env: dict) -> tuple[bool, Path | None, list[tuple[str, int | None, str, float]], bool]:
    """Try stdlib venv, then a no-ensurepip bootstrap if venv provisioning fails.

    The fallback uses the *active* interpreter's pip `--python` facility to
    install into a separate no-pip venv. It never installs into base Python or
    uses a site/user directory. Both routes require the SAME independent wheel
    hash/import checker in the final private interpreter. Broken installs and
    provenance mismatches remain FAIL; fallback is only for bootstrap failure.
    """
    private_env = _private_wheel_environment(env)
    steps: list[tuple[str, int | None, str, float]] = []
    current = work/'install-env'
    current_python = current/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    # A Windows venv redirector is not a safe parent for nested venv
    # provisioning: it can resolve a child back into the managed scientific
    # venv and copy/link the managed Scripts contents. Prefer the actual
    # CPython installation declared by sys.base_prefix, if present. The
    # *child*, not this path choice, still has to pass the full isolation
    # probe and independent wheel hash/import verification.
    base_python = Path(sys.base_prefix) / ('python.exe' if os.name == 'nt' else 'bin/python')
    primary_python = base_python if os.name == 'nt' and base_python.is_file() else Path(sys.executable)
    code, log, duration = _run([str(primary_python), '-m', 'venv', '--copies', str(current)], work, private_env, 75)
    steps.append(('isolated venv with pip', code, log, duration))
    if code == 0:
        probe, probe_log, probe_time = _isolated_venv_probe(current_python, current, work, private_env)
        steps.append(('venv interpreter/prefix identity', probe, probe_log, probe_time))
        if probe == 0:
            install, install_log, install_time = _run(
                [str(current_python), '-I', '-m', 'pip', '--isolated', 'install',
                 '--force-reinstall', '--no-index', '--no-deps', '--no-cache-dir', str(wheel)],
                work, private_env, 110)
            steps.append(('offline isolated wheel installation', install, install_log, install_time))
            if install == 0:
                verify, verified_log, verified_time = _run(
                    [str(current_python), '-I', str(root/'scripts/verify_installed_wheel.py'), str(wheel)],
                    work, private_env, 35)
                steps.append(('independent installed wheel hash/import verification', verify, verified_log, verified_time))
                return verify == 0, current_python if verify == 0 else None, steps, False
            # A failing wheel installation is NOT silently retried elsewhere.
            # Only an absent pip bootstrap qualifies for a second venv route.
            if 'No module named pip' not in install_log:
                return False, None, steps, False
        # If the venv exists but has an unexpected interpreter/prefix, never
        # run its pip. The independent fallback may still work safely.
    # Windows can fail in ensurepip after creating the environment. A separate
    # --without-pip environment avoids that step; install via pip --python,
    # explicitly directing pip into this new private interpreter.
    # Retry independent candidates without accepting a failed identity probe.
    # A separate active-interpreter route matters on Windows when a launcher
    # redirector and sys._base_executable point at different Python installs.
    # These routes are all fresh, private, WITHOUT pip and must be probed.
    host_python = Path(getattr(sys, '_base_executable', sys.executable))
    if not host_python.is_file():
        host_python = Path(sys.executable)
    # The native base executable is a separate bootstrap candidate if a
    # managed Python reports a redirected _base_executable. Never use the
    # base interpreter for wheel installation or verification itself.
    candidates = [
        (host_python, '--copies', 'install-env-no-pip',
         'fallback venv without ensurepip'),
        (host_python, '--symlinks', 'install-env-symlink',
         'alternate no-pip symlink venv'),
    ]
    if (os.name == 'nt' and base_python.is_file() and
            os.path.normcase(os.path.abspath(base_python)) !=
            os.path.normcase(os.path.abspath(host_python))):
        candidates.insert(1, (base_python, '--copies', 'install-env-native-base',
                              'native base no-pip venv'))
    active_python = Path(sys.executable)
    if os.path.normcase(os.path.abspath(host_python)) != os.path.normcase(os.path.abspath(active_python)):
        candidates.append((active_python, '--copies', 'install-env-active',
                           'alternate active-interpreter no-pip venv'))
    fallback = None
    fallback_python = None
    previous_identity_failed = False
    for executable, strategy, dirname, label in candidates:
        candidate = work.resolve()/dirname
        interpreter = candidate/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        # Preserve the historic fallback label for downstream diagnostic tools.
        if strategy == '--symlinks' and previous_identity_failed:
            label = 'alternate after invalid copied venv identity'
        code, log, duration = _run(
            [str(executable), '-m', 'venv', strategy, '--without-pip', str(candidate)],
            work, private_env, 75)
        steps.append((label, code, log, duration))
        if code != 0:
            continue
        probe, probe_log, probe_time = _isolated_venv_probe(interpreter, candidate, work, private_env)
        probe_label = ('fallback interpreter/prefix identity' if dirname == 'install-env-no-pip'
                       else 'alternate interpreter/prefix identity')
        steps.append((probe_label, probe, probe_log, probe_time))
        if probe == 0:
            fallback, fallback_python = candidate, interpreter
            break
        previous_identity_failed = True
    if fallback_python is None:
        # Explicitly distinguish private venv provisioning from a wheel failure.
        return False, None, steps, True
    # Pip --python is allowed only with an explicitly named venv and verified
    # candidate interpreter. It does not qualify the install by itself.
    install, install_log, install_time = _run(
        [sys.executable, '-I', '-m', 'pip', '--python', str(fallback_python),
         '--isolated', 'install', '--force-reinstall', '--no-index',
         '--no-deps', '--no-cache-dir', str(wheel)], work, private_env, 110)
    steps.append(('fallback pip into private interpreter', install, install_log, install_time))
    if install != 0:
        return False, None, steps, True
    verify, verified_log, verified_time = _run(
        [str(fallback_python), '-I', str(root/'scripts/verify_installed_wheel.py'), str(wheel)],
        work, private_env, 35)
    steps.append(('fallback independent installed wheel hash/import verification', verify, verified_log, verified_time))
    return verify == 0, fallback_python if verify == 0 else None, steps, True

def _stale_release_tests(root: Path) -> tuple[str, ...]:
    """Report legacy A99 tests absent from the signed release inventory.

    Files are never removed, excluded from source integrity, or executed.
    Explicitly include RC14.10: Windows report 0004 found this third
    untracked test even though older diagnostics only named 14.8 and 14.9.
    """
    folder = Path(root) / 'tests/integration'
    names = ('test_rc14_8_a99_release.py', 'test_rc14_9_a99_release.py',
             'test_rc14_10_a99_release.py')
    return tuple(name for name in names
                 if (folder/name).exists() or (folder/name).is_symlink())


def _stale_release_test_present(root: Path) -> bool:
    """Compatibility boolean used by prior source-contamination checks."""
    return bool(_stale_release_tests(root))


def _pytest_result(code, output):
    matches = dict((kind, int(n)) for n, kind in re.findall(r'(\d+) (passed|failed|skipped|error|errors|xfailed|xpassed)', output))
    if code == 0 and matches.get('passed',0):
        return 'PASS', matches
    return 'FAIL', matches


def qualify(source: Path, output: Path, *, profile: str = 'comprehensive',
            notify: Callable[[str], None] | None = None, em_options: dict | None = None) -> dict:
    """Generate a portable, minimized test-evidence ZIP, with no user data.

    `profile=quick` runs integrity, static checks, software tests and HTTP smoke.
    `comprehensive` also runs real-browser, native-engine and package probes.
    Works from an extracted source archive; installed native engines are optional.
    """
    if profile == 'eda_feedback':
        from .feedback_qualification import qualify_eda_feedback
        return qualify_eda_feedback(source, output, em_options=em_options, notify=notify)
    if profile == 'native_em':
        if not isinstance(em_options, dict) or not {'reviewer', 'acknowledged', 'solve', 'refine'} <= set(em_options) or not set(em_options) <= {'reviewer','acknowledged','solve','refine','third_mesh','memory_budget_gb','time_budget_seconds','mpi_ranks'}:
            raise ValueError('Native EM qualification requires explicit review and execution settings')
        from .native_em_qualification import qualify_native_em
        return qualify_native_em(source, output, notify=notify, **em_options)
    if profile not in ('quick', 'comprehensive'):
        raise ValueError('Unknown qualification profile')
    root = Path(source).resolve(strict=True)
    if not (root/'pyproject.toml').is_file() or not (root/'src/sqe_studio/server.py').is_file():
        raise ValueError('SQE Studio source root is required')
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != '.zip' or output.is_symlink():
        raise ValueError('Report destination must be a regular .zip path')
    if output.is_relative_to(root):
        raise ValueError('Report cannot be written into source tree')
    output.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    report = {
        'schema': SCHEMA, 'purpose': 'integrated_eda_release_candidate_evidence',
        'started_utc': started, 'profile': profile,
        'source_inventory_sha256': None,
        'environment': {'os': platform.system(), 'os_release': platform.release(),
                        'python': platform.python_version(), 'architecture': platform.machine(),
                        'scientific_python_311': sys.version_info[:2] == (3,11)},
        'toolchain': {
            'python_modules': {name: {'detected':available(name),
                                      'distribution_version':_package_version(dist)}
                for name, dist in (('pytest','pytest'),('playwright','playwright'),
                    ('qiskit_metal','quantum-metal'),('scqubits','scqubits'),
                    ('SQDMetal','SQDMetal'),('gmsh','gmsh'))},
            'commands_present': {name:bool(shutil.which(name)) for name in
                ('node','julia','gmsh','palace','chromium','chromium-browser','google-chrome')},
            'palace_configured_externally':bool(os.environ.get('SQE_PALACE_BINARY') or os.environ.get('SQE_PALACE_WSL_BINARY')),
        },
        'gates': [], 'scientific_boundaries': [
            'No user project or home workspace is inspected.',
            'Installed module does not imply native solver completion or correctness.',
            'Fixture tests cannot qualify scientific observables.',
            'EM-to-Hamiltonian, kinetic sheet adapter, RF cross-engine mapping and geometry optimization are not qualified.',
            'Independent measurement, PDK, DRC/LVS and foundry approval are not established.']}
    # Metadata-only upstream source provenance. Avoid including user-local paths
    # in the shareable qualification ZIP or equating a saved commit with a native run.
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        try:
            from sqdmetal_source import _read_pin
            cache = Path(os.environ['LOCALAPPDATA'])/'SQE-Studio'/'sources'/'sqdmetal'
            pin = _read_pin(cache)
            report['toolchain']['sqdmetal_source'] = (
                {'origin':'official GitHub sqdlab/SQDMetal',
                 'commit':pin['commit'],'archive_sha256':pin['archive_sha256'],
                 'cache_present':(cache/(pin['commit']+'.zip')).is_file(),
                 'status':'PINNED_SOURCE_NOT_NATIVE_QUALIFICATION'}
                if pin else {'status':'NO_VALID_OFFICIAL_SOURCE_PIN'})
        except (ImportError, OSError, ValueError):
            report['toolchain']['sqdmetal_source'] = {'status':'PIN_METADATA_UNAVAILABLE'}
    # Detection is metadata-only; it cannot execute an unknown Python runtime.
    # Do not mistake an unbound old environment for an absent installation.
    if os.name == 'nt':
        try:
            from workstation_setup import environment_inventory
            state = environment_inventory(root)
            report['environment']['managed_runtime'] = {
                'connected':state['managed_selected'],
                'ready_count':sum(int(x['ready']) for x in state['candidates']),
                'partial_count':sum(int(not x['ready']) for x in state['candidates'])}
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            report['environment']['managed_runtime'] = {'status':'unavailable','reason':type(exc).__name__}
    logs = {}
    def emit(msg):
        if notify: notify(msg)
    with tempfile.TemporaryDirectory(prefix='sqe-qualification-') as temporary:
        work = Path(temporary)
        substitutions = (str(root), str(work), str(Path.home()), os.environ.get('USERPROFILE',''))
        env = os.environ.copy()
        env.update({'HOME': str(work/'home'), 'USERPROFILE': str(work/'home'),
                    'XDG_CACHE_HOME':str(work/'cache'), 'XDG_CONFIG_HOME':str(work/'config'),
                    'PYTHONDONTWRITEBYTECODE':'1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
                    'PYTHONPATH':str(root/'src'), 'PIP_NO_INDEX':'1',
                    'PIP_DISABLE_PIP_VERSION_CHECK':'1', 'PYTHONNOUSERSITE':'1'})
        (work/'home').mkdir()
        # Independent A15 evidence does not compete with the huge combined
        # regression stdout. All writes remain under this synthetic temp root.
        diagnostic_dir = work/'regression-diagnostics'
        diagnostic_dir.mkdir(mode=0o700)
        env['SQE_QUALIFICATION_DIAGNOSTIC_DIR'] = str(diagnostic_dir)
        # Both the portable regression (which includes browser tests) and the
        # subsequent deep browser gate MUST use the same private capture root.
        # Setting this only after regression contaminates source with A07 PNGs,
        # fails the release inventory, and cascades into unrelated delta tests.
        env['SQE_BROWSER_CAPTURE_DIR'] = str(work/'browser-captures')
        # A15 creates a *nested* CPython venv. Windows Store/managed Python
        # redirectors can resolve that nested interpreter back into the
        # scientific parent when HOME/USERPROFILE have been replaced with the
        # synthetic qualification profile. Capture host values before the
        # regression subprocess; only the A15 child receives them. Other
        # regression groups retain the private qualification profile. Never
        # inherit externally supplied SQE_A15_BOOTSTRAP_* overrides.
        for name in ('HOME', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH'):
            variable = 'SQE_A15_BOOTSTRAP_' + name
            env.pop(variable, None)
            if os.name == 'nt' and os.environ.get(name):
                env[variable] = os.environ[name]
        wheel_step_evidence = []
        # Do not accidentally hide the *installed Julia package environment* by
        # overriding HOME/USERPROFILE for Python and browser test isolation.
        # Julia's depot is a dependency cache, not a user's SQE design workspace.
        # Never copy its files into the qualification archive.
        if shutil.which('julia'):
            if os.environ.get('JULIA_DEPOT_PATH'):
                env['JULIA_DEPOT_PATH'] = os.environ['JULIA_DEPOT_PATH']
            else:
                original_home = os.environ.get('USERPROFILE') if os.name == 'nt' else os.environ.get('HOME')
                if original_home:
                    env['JULIA_DEPOT_PATH'] = str(Path(original_home) / '.julia')
        # JULIA_PROJECT, when explicitly selected by the desktop operator,
        # already propagates from os.environ. Avoid defaulting to temp HOME.
        started_gates=set()
        def begin_gate(key):
            if key not in started_gates:
                started_gates.add(key)
                emit(f'STAGE_START software {key}')
        def gate(key, status, description, *, log='', seconds=0, counts=None, reason='', kind='software', bootstrap_fallback=False):
            if status not in ('PASS', 'FAIL', 'BLOCKED'):
                raise ValueError('Invalid gate status')
            begin_gate(key)
            logname = f'logs/{key}.txt'
            logs[logname] = _safe_log(log or (reason or status), substitutions).encode('utf-8', 'replace')
            record = {'id': key, 'category': kind, 'status': status, 'description': description,
                      'duration_seconds': seconds, 'log': logname,
                      'log_sha256': sha(logs[logname])}
            if reason: record['reason'] = reason
            if counts: record['counts'] = counts
            if bootstrap_fallback: record['bootstrap_fallback_used'] = True
            report['gates'].append(record)
            emit(f'STAGE_END software {key} {status}')
            emit(f'{status}: {description}')
        def invoke(key, description, args, *, timeout=DEFAULT_TIMEOUT, kind='software', pytest=False):
            begin_gate(key)
            emit(f'Running: {description}')
            if pytest:
                args = [*args, '--basetemp='+str(work/('pytest-'+key))]
            code, out, seconds = _run(args, root, env, timeout)
            if pytest and code != 0:
                out += _isolated_test_diagnostics(work, key, substitutions)
            if pytest:
                status, counts = _pytest_result(code, out)
                gate(key, status, description, log=out, seconds=seconds, counts=counts, kind=kind,
                     reason=('Process timed out or could not start' if code is None else
                             'Pytest returned a failing exit code' if code != 0 else ''))
            else:
                status = 'PASS' if code == 0 else 'FAIL'
                gate(key, status, description, log=out, seconds=seconds, kind=kind,
                     reason=('Timed out or process could not start' if code is None else
                             f'Exit code {code}' if code else ''))
            return code, out
        # Explicitly diagnose a stale file that is NOT in the signed release.
        # Do not delete, whitelist, bypass, or silently run a contaminated tree.
        for stale_test in _stale_release_tests(root):
            old = stale_test.split('_a99_release.py')[0].removeprefix('test_')
            gate('obsolete_'+old+'_test', 'FAIL',
                 'Unexpected obsolete release test in source tree',
                 reason='UNTRACKED_STALE_RELEASE_TEST_CLEAN_STAGING_REQUIRED')
        # Source inventory: first line of defense against modified/distorted artifacts.
        inventory = root/'EDA_SOURCE_MANIFEST.json'
        if inventory.is_file():
            try:
                original = json.loads(inventory.read_text(encoding='utf-8'))
                report['source_inventory_sha256'] = original['current_source_inventory_sha256']
                invoke('source_integrity', 'Evolved source inventory and frozen contract check',
                       [sys.executable, str(root/'tools/verify_release_source.py'), str(root)], timeout=35)
            except (ValueError, KeyError, OSError) as exc:
                gate('source_integrity', 'FAIL', 'Evolved source inventory and frozen contract check',
                     reason=type(exc).__name__)
        else:
            gate('source_integrity', 'FAIL', 'Evolved source inventory and frozen contract check',
                 reason='Source manifest absent')
        invoke('python_compile', 'Compile production Python sources and desktop launcher (syntax only)',
               [sys.executable, '-c',
                'import pathlib,ast; root=pathlib.Path("src/sqe_studio"); '
                '[ast.parse(p.read_text(encoding="utf-8"), filename=str(p)) for p in root.rglob("*.py")]; '
                'launcher=pathlib.Path("Launch SQE Studio.pyw"); '
                'ast.parse(launcher.read_text(encoding="utf-8"),filename=str(launcher)); '
                'print("production and desktop launcher AST parsed")'], timeout=30)
        if shutil.which('node'):
            invoke('javascript_syntax', 'Validate bundled application JavaScript syntax',
                   ['node','--check', str(root/'src/sqe_studio/web/app.js')], timeout=25)
        else:
            gate('javascript_syntax','BLOCKED','Validate bundled application JavaScript syntax',reason='Node.js unavailable')
        if available('pytest'):
            invoke('integrated_regression', 'Integrated EDA, security, contracts and HTTP regression suite',
                   [sys.executable, str(root/'scripts/portable_regression.py')],
                   timeout=2700 if profile == 'comprehensive' else 540, pytest=True)
        else:
            gate('integrated_regression','BLOCKED','Integrated EDA, security, contracts and HTTP regression suite',
                 reason='pytest unavailable; no dependency installation attempted')
        # Real browser uses installed Chromium/Playwright and an actual loopback service.
        browser_passed = False
        if profile == 'comprehensive':
            if available('playwright'):
                begin_gate('browser_real_http')
                code, out, seconds = _run([sys.executable, str(root/'scripts/browser_local_smoke.py'),
                    '--installed-python',sys.executable],root,env,115)
                if code == 0:
                    browser_passed = True
                    gate('browser_real_http','PASS','Real browser/authenticated installed-assets GUI smoke',log=out,seconds=seconds,kind='browser')
                elif 'BROWSER_UNAVAILABLE:' in out:
                    gate('browser_real_http','BLOCKED','Real browser/authenticated installed-assets GUI smoke',
                         log=out,seconds=seconds,kind='browser',reason='Browser startup/policy unavailable')
                else:
                    gate('browser_real_http','FAIL','Real browser/authenticated installed-assets GUI smoke',
                         log=out,seconds=seconds,kind='browser',reason=f'Exit code {code}; browser did not complete')
            else:
                gate('browser_real_http','BLOCKED','Real browser/authenticated installed-assets GUI smoke',
                     kind='browser',reason='Python Playwright unavailable; no browser test executed')
        else:
            gate('browser_real_http','BLOCKED','Real browser/authenticated installed-assets GUI smoke',
                 kind='browser',reason='Not executed in Quick profile')
        if browser_passed and available('pytest'):
            begin_gate('browser_deep_acceptance')
            emit('Running: deep browser acceptance of GUI, security and design navigation')
            code, out, seconds = _run([sys.executable,'-m','pytest','-q','-ra',
                       '-p','no:cacheprovider','tests/ui/test_browser.py',
                       '--basetemp='+str(work/'pytest-browser')],root,env,220)
            if code != 0:
                out += _isolated_test_diagnostics(work,'browser', substitutions)
            status, counts = _pytest_result(code,out)
            if status == 'PASS' and counts.get('skipped',0): status = 'BLOCKED'
            gate('browser_deep_acceptance',status,
                 'Full browser keyboard/revision/security/fail-closed workflow and responsive layout',
                 log=out,seconds=seconds,counts=counts,kind='browser',
                 reason='Browser subtests skipped: no full acceptance' if status=='BLOCKED' else
                        'Browser acceptance failed' if status=='FAIL' else '')
        else:
            gate('browser_deep_acceptance','BLOCKED',
                 'Full browser keyboard/revision/security/fail-closed workflow and responsive layout',
                 kind='browser',reason='Browser smoke not passed, pytest unavailable or Quick profile')
        # Production installed-package check: no internet, fresh interpreter and HTTP service.
        # Prefer a built wheel matching THIS source; do not claim old bundled wheel as provenance proof.
        if profile == 'comprehensive':
            wheel_dir = work/'wheels';wheel_dir.mkdir()
            if _package_version('build') is not None:
                args = [sys.executable,'-m','build','--wheel','--no-isolation','--outdir',str(wheel_dir)]
            else:
                args = [sys.executable,'-m','pip','wheel','--no-index','--no-deps',
                        '--no-build-isolation','--wheel-dir',str(wheel_dir), str(root)]
            begin_gate('source_wheel_build')
            # Modern setuptools ships bdist_wheel even when the standalone
            # 'wheel' distribution is absent. Attempt the offline build first.
            if not available('setuptools.build_meta'):
                code, out, seconds = None, ('The Python build backend setuptools.build_meta is absent. '
                     'This is an environment prerequisite, not a failed scientific solver. '
                     'Use Prepare scientific environment with Python 3.11 and Build + pytest.'), 0
            else:
                code, out, seconds = _run(args,root,env,160)
            wheels = list(wheel_dir.glob('*.whl'))
            if code == 0 and len(wheels)==1:
                gate('source_wheel_build','PASS','Build installable wheel from current source offline',log=out,
                     seconds=seconds,kind='packaging')
                begin_gate('installed_wheel')
                installed_env = env.copy()
                installed_env.pop('PYTHONPATH', None)
                ready, installed_python, steps, fallback_used = _isolated_wheel_install(
                    root, wheels[0], work, installed_env)
                # Record EVERY failed first bootstrap, fallback and verification
                # exit; no false PASS just because a command created a venv.
                step_log='\n'.join(f'[{name}: exit={code if code is not None else "TIMEOUT_OR_SPAWN_ERROR"}]\n{log}'
                                   for name, code, log, _ in steps)
                wheel_step_evidence = [
                    {'step': name, 'exit_code': code, 'duration_s': duration,
                     'isolation_failure_codes': sorted(set(re.findall(
                         r'\b(?:PREFIX_MISMATCH|EXECUTABLE_MISMATCH|BASE_PREFIX_REUSED|INTERPRETER_FLAGS|MISSING_PRIVATE_VENV_CONFIG|SYSTEM_SITE_ENABLED_OR_UNKNOWN|PRIVATE_MARKER_WRITE_FAILED)\b', log))),
                     'diagnostic_excerpt': _safe_log(log[-4500:], substitutions)}
                    for name, code, log, duration in steps]
                gate('installed_wheel', 'PASS' if ready else 'FAIL',
                     'Offline isolated wheel installation and byte-verified package import',
                     log=step_log, seconds=sum(t for _,_,_,t in steps), kind='packaging',
                     bootstrap_fallback=fallback_used,
                     reason='' if ready else 'Private interpreter/install/provenance failed; see all recorded attempts')
                if ready:
                    begin_gate('installed_assets')
                    # The smoke is *also* isolated: environment import hooks and
                    # user-site packages are ignored by the wheel interpreter.
                    code4, out4, t4 = _run([str(installed_python), '-I',
                        str(root/'scripts/qualification_installed_smoke.py')], work, installed_env, 75)
                    gate('installed_assets', 'PASS' if code4==0 else 'FAIL',
                         'Installed HTTP/auth/revision/UI catalog smoke',
                         log=f'[installed HTTP smoke: exit={code4 if code4 is not None else "TIMEOUT_OR_SPAWN_ERROR"}]\n'+out4,
                         seconds=t4, kind='packaging',
                         reason='' if code4==0 else 'Installed wheel HTTP acceptance failed; see captured stdout/stderr')
                else:
                    gate('installed_assets','BLOCKED','Installed HTTP/auth/revision/UI catalog smoke',
                         kind='packaging',reason='Isolated wheel verification did not complete')
            else:
                gate('source_wheel_build','BLOCKED' if code is None or ('No module named' in out or 'invalid command' in out or 'not installed' in out.lower() or 'BackendUnavailable' in out) else 'FAIL',
                     'Build installable wheel from current source offline',log=out,seconds=seconds,
                     kind='packaging',reason=('Missing Python build backend; use Prepare scientific environment (Python 3.11)'
                                  if code is None else 'Offline wheel build prerequisite missing or build failed'))
                gate('installed_wheel','BLOCKED','Offline isolated wheel installation and package/UI import',
                     kind='packaging',reason='No newly built wheel from current source')
                gate('installed_assets','BLOCKED','Installed HTTP/auth/revision/UI catalog smoke',
                     kind='packaging',reason='No newly built wheel from current source')
        else:
            for key,description in [('source_wheel_build','Build installable wheel from current source offline'),
                                    ('installed_wheel','Offline isolated wheel installation and package/UI import'),
                                    ('installed_assets','Installed HTTP/auth/revision/UI catalog smoke')]:
                gate(key,'BLOCKED',description,kind='packaging',reason='Not executed in Quick profile')
        # Installed tools: observed availability and native tests, no simulated data.
        engines = [
            ('quantum_metal','qiskit_metal', 'tests/adapters/test_quantum_metal_native.py'),
            ('scqubits','scqubits','tests/adapters/test_scqubits_native.py'),
            ('josephson_circuits','julia','tests/adapters/test_josephson_adapter.py'),
        ]
        for key, module, test_file in engines:
            detected = bool(shutil.which('julia')) if module=='julia' else available(module)
            desc = f'Native {key} engine execution checks (not a mock)'
            if profile!='comprehensive':
                gate('native_'+key,'BLOCKED',desc,kind='native',reason='Not executed in Quick profile')
            elif not detected:
                gate('native_'+key,'BLOCKED',desc,kind='native',reason=f'{module} not available in active Python/toolchain')
            elif not available('pytest'):
                gate('native_'+key,'BLOCKED',desc,kind='native',reason='pytest unavailable')
            else:
                begin_gate('native_'+key)
                emit('Running: '+desc)
                code,out,seconds = _run([sys.executable,'-m','pytest','-q','-ra',
                    '-p','no:cacheprovider',test_file,
                    '--basetemp='+str(work/('pytest-native_'+key))],root,env,240)
                if code != 0:
                    out += _isolated_test_diagnostics(work,'native_'+key, substitutions)
                status,counts = _pytest_result(code,out)
                if status=='PASS' and counts.get('skipped'):
                    status='BLOCKED'
                gate('native_'+key,status,desc,log=out,seconds=seconds,counts=counts,kind='native',
                     reason='Native test skipped or incomplete' if status=='BLOCKED' else
                            'Native test failure or timeout' if status=='FAIL' else '')
        # Julia itself and JosephsonCircuits.jl are different dependencies.
        # Probe the SAME depot/project used by native test workers; print no
        # local package path, just the presence marker and Julia version.
        if profile != 'comprehensive':
            gate('julia_package_runtime','BLOCKED',
                 'Julia runtime and JosephsonCircuits.jl package discovery',
                 kind='native',reason='Not executed in Quick profile')
        elif not shutil.which('julia'):
            gate('julia_package_runtime','BLOCKED',
                 'Julia runtime and JosephsonCircuits.jl package discovery',
                 kind='native',reason='Julia executable unavailable in active runtime')
        else:
            probe = ('print("JULIA_VERSION=" * string(VERSION) * "\n" * '
                     '(Base.find_package("JosephsonCircuits") === nothing ? '
                     '"MISSING" : "PRESENT"))')
            code, probe_output, elapsed = _run(['julia','--startup-file=no','--history-file=no',
                                                   '-e',probe],root,env,45)
            marker_found = probe_output.strip().splitlines()[-1:] == ['PRESENT']
            if code == 0 and marker_found:
                status, reason = 'PASS', ''
            elif code == 0 and probe_output.strip().splitlines()[-1:] == ['MISSING']:
                status, reason = 'BLOCKED', 'Julia exists; JosephsonCircuits.jl missing in selected Julia project/depot'
            else:
                status, reason = 'FAIL', 'Julia package environment probe failed; inspect error'
            gate('julia_package_runtime',status,
                 'Julia runtime and JosephsonCircuits.jl package discovery',
                 kind='native',log=probe_output,seconds=elapsed,reason=reason)
        # Palace executable qualification is separate from the scientific EM
        # model/run gate. Verifying --version NEVER counts as a solved field.
        if profile == 'comprehensive':
            if not (os.environ.get('SQE_PALACE_BINARY') or os.environ.get('SQE_PALACE_WSL_BINARY')):
                gate('native_palace_runtime', 'BLOCKED',
                     'Operator-configured Palace executable handshake (version when supported)',
                     kind='native', reason='Palace location not configured. Use Configure installed solvers in desktop launcher.')
            else:
                try:
                    from sqe_studio.adapters.sqdmetal_palace_adapter import _palace_readiness
                    state = _palace_readiness()  # native --version; WSL exec test + --version
                    gate('native_palace_runtime', 'PASS',
                         'Operator-configured Palace executable handshake (version when supported)',
                         kind='native', log=json.dumps({'backend':state['backend'],
                                   'identity_probe':state['identity_probe'],
                                   'version':state['version'], 'version_verified':state['version_verified'],
                                   'binary_hash_available':bool(state['binary_sha256'])}),
                         reason=('Palace 0.16.x CLI verified using --help; version not verified by the binary; no EM solve executed'
                                 if not state['version_verified'] else ''))
                except Exception as exc:
                    gate('native_palace_runtime', 'FAIL',
                         'Operator-configured Palace executable handshake (version when supported)',
                         kind='native', reason='Configured Palace failed version/path verification',
                         log=type(exc).__name__+': '+str(exc))
        else:
            gate('native_palace_runtime', 'BLOCKED',
                 'Operator-configured Palace executable handshake (version when supported)',
                 kind='native', reason='Not executed in Quick profile')
        # Inspect actual third-party SQDMetal Python APIs in a child process.
        # This is a toolchain handshake, NOT a prepared mesh, Palace run,
        # convergence result, EPR extraction or experimentally checked physics.
        if profile != 'comprehensive':
            gate('native_sqdmetal_api', 'BLOCKED',
                 'Native SQDMetal/Gmsh/Quantum Metal API compatibility handshake',
                 kind='native', reason='Not executed in Quick profile')
        elif not available('SQDMetal'):
            gate('native_sqdmetal_api', 'BLOCKED',
                 'Native SQDMetal/Gmsh/Quantum Metal API compatibility handshake',
                 kind='native', reason='SQDMetal not installed in active scientific Python 3.11; use desktop Prepare scientific environment -> SQDMetal')
        else:
            begin_gate('native_sqdmetal_api')
            emit('Running: native SQDMetal/Gmsh/Quantum Metal API compatibility handshake')
            snippet = ('import json;from sqe_studio.adapters.sqdmetal_palace_adapter '
                       'import probe_sqdmetal_toolchain;print("SQE_EM_PROBE="+'
                       'json.dumps(probe_sqdmetal_toolchain(),sort_keys=True))')
            code, probe_output, elapsed = _run([sys.executable, '-c', snippet], root, env, 90)
            found = next((line[len('SQE_EM_PROBE='):] for line in probe_output.splitlines()
                          if line.startswith('SQE_EM_PROBE=')), None)
            ok = False
            if code == 0 and found:
                try:
                    ok = json.loads(found).get('state') == 'NATIVE_API_IMPORTS_VERIFIED_NO_SIMULATION'
                except (ValueError, TypeError):
                    pass
            gate('native_sqdmetal_api', 'PASS' if ok else 'FAIL',
                 'Native SQDMetal/Gmsh/Quantum Metal API compatibility handshake',
                 kind='native', log=probe_output, seconds=elapsed,
                 reason=('API import or signature error; inspect child process log' if not ok else
                         'Actual imports passed; no physical geometry, mesh or Palace solve executed'))
        # A toolchain may be installed without an operator-approved EM model.
        toolchain = {'qiskit_metal':available('qiskit_metal'),'SQDMetal':available('SQDMetal'),
                     'gmsh':available('gmsh'),'palace_executable': bool(shutil.which('palace') or os.environ.get('SQE_PALACE_BINARY') or os.environ.get('SQE_PALACE_WSL_BINARY'))}
        gate('native_em_design_loop','BLOCKED','Reviewed native QDesign→mesh→Palace solve and convergence',
             kind='native',log=json.dumps(toolchain,sort_keys=True),
             reason='Automated unattended convergence cannot waive physical material/port/mesh reviews; attach completed revision-bound runs for expert assessment')
        gate('em_quantum_bridge','BLOCKED','Typed EM→EPR→Hamiltonian→quantum closed design loop',
             kind='scientific',reason='Versioned reviewed EPR quantization edge is not implemented')
        gate('geometry_optimization','BLOCKED','Native objective-driven geometry optimization',
             kind='scientific',reason='General multi-engine geometry feedback optimization not implemented')
        gate('foundry_release','BLOCKED','Independent physical validation, DRC/LVS, foundry qualification',
             kind='scientific',reason='Independent validation and foundry signoff not provided')
        report['finished_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        report['counts'] = {label:sum(x['status']==label for x in report['gates']) for label in ('PASS','FAIL','BLOCKED')}
        report['rc_status'] = 'BLOCKED_NOT_RELEASE_CANDIDATE'
        report['rc_reason'] = ('Software failures need correction; native and independent scientific gates are incomplete.'
                               if report['counts']['FAIL'] else
                               'Native/cross-engine scientific, platform or external evidence is incomplete.')
        summary = ['# SQE Studio — laptop integrated EDA qualification', '',
                   f'**Result: {report["rc_status"]}**',
                   f'Profile: {profile}. PASS {report["counts"]["PASS"]} · FAIL {report["counts"]["FAIL"]} · BLOCKED {report["counts"]["BLOCKED"]}.',
                   'This report is local test evidence, not an independent scientific certification.', '',
                   '## Python environment',
                   'Active interpreter: '+report['environment']['python'],
                   'Managed scientific interpreter connected: '+str(report['environment']['scientific_python_311']),
                   'Ready environments found: '+str(report['environment'].get('managed_runtime',{}).get('ready_count','unknown')),
                   'Incomplete environments found: '+str(report['environment'].get('managed_runtime',{}).get('partial_count','unknown')),
                   'If an earlier installation exists but is not connected, use the desktop Reconnect button.','',
                   '| Gate | Result | Why / next step |', '|---|---|---|']
        for x in report['gates']:
            msg = x.get('reason','See sanitized log')
            summary.append('| '+x['id']+' | '+x['status']+' | '+msg.replace('|','/')+' |')
        summary += ['', '## Interpretation',
                    'PASS = test really executed and its stated software/native assertion passed.',
                    'BLOCKED = missing dependency, omitted profile, unavailable acceptance, or unimplemented scientific edge; NOT a pass.',
                    'FAIL = an executed test, build or verification reported a problem.',
                    'Native calculation alone does not imply experimental validation. No fixture values are presented as real EM output.',
                    'User project data, stored tokens, cookies, native designs and home workspace were not collected.',
                    'Logs are size-limited and best-effort redacted; inspect the archive before sharing.',
                    '', '## Path to RC',
                    'Clear FAIL gates, then reproduce real QDesign/GDS, Palace mesh/deck/solve and convergence on reviewed physical studies,',
                    'verify real browser installation on the target OS, qualify EM→quantum and RF interfaces,',
                    'and obtain independent validation and release approvals. Fabrication remains HOLD.', '']
        data = {'QUALIFICATION.json':(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode(),
                'SUMMARY.md': ('\n'.join(summary)+'\n').encode()}
        data.update(logs)
        # Detailed A15 JUnit evidence survives even when the aggregate pytest
        # transcript is truncated. Do not export the raw subprocess file: it
        # may contain host-specific profile paths and test exception values.
        a15_file = diagnostic_dir/'A15_CASES.json'
        if a15_file.is_file() and not a15_file.is_symlink() and a15_file.stat().st_size <= 1_500_000:
            try:
                a15_doc = json.loads(a15_file.read_text(encoding='utf-8'))
                if a15_doc.get('schema') == 'sqe.a15-detailed-test-evidence.v1':
                    a15_doc['cases'] = [dict(row, **{
                        field: _safe_log(str(row[field]), substitutions)
                        for field in ('diagnostic', 'traceback') if field in row})
                        for row in a15_doc.get('cases', [])[:120] if isinstance(row, dict)]
                    data['diagnostics/A15_CASES.json'] = (
                        json.dumps(a15_doc,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
            except (OSError, ValueError, TypeError, KeyError):
                pass
        data['diagnostics/WHEEL_ISOLATION_STEPS.json'] = (
            json.dumps({'schema':'sqe.wheel-isolation-attempts.v1',
                        'steps':wheel_step_evidence,
                        'note':'Only actual production-path attempts; not a proof of Windows acceptance'},
                       indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
        # Structured diagnostic index for the next development iteration. Every
        # source is this-run output; no user projects, shell environment values,
        # absolute interpreter paths or subprocess command lines are stored.
        regression_log = logs.get('logs/integrated_regression.txt', b'').decode('utf-8','replace')
        group_lines = [line[:300] for line in regression_log.splitlines()
                       if re.match(r'^GROUP(?:_START|_TIMEOUT_LAST_OUTPUT)? [a-zA-Z0-9_]+ ', line)][:100]
        failures = re.findall(r'(?m)^FAILED (tests/[^\s]{1,200}::[^\s]{1,200})', regression_log)
        failures += re.findall(r'(?m)^_+ (test_[a-zA-Z0-9_]{1,150}) _+', regression_log)
        # A15 can emit a bounded JUnit-derived list even when the verbose
        # traceback is dominated by failed Windows script symlinks.
        a15_failures = []
        for line in regression_log.splitlines():
            if line.startswith('GROUP_A15_STRUCTURED_FAILURES '):
                try:
                    rows = json.loads(line.split(' ', 1)[1])
                    if isinstance(rows, list):
                        for item in rows[:40]:
                            if isinstance(item, dict) and isinstance(item.get('test'), str):
                                a15_failures.append({'test': item['test'][:240],
                                    'diagnostic': str(item.get('diagnostic', ''))[:700]})
                except (ValueError, TypeError):
                    pass
        failures.extend(item['test'] for item in a15_failures)
        # This index identifies the original gate logs, which retain the
        # sanitized traceback and per-test detail in a larger bounded window.
        diagnostic = {
          'schema':'sqe.auto-test-diagnostics.v1',
          'note':'Sanitized current-run diagnostics; inspect ZIP before sharing',
          'native_scope':'SINGLE_MESH_ONLY_NO_CONVERGENCE_CLAIM',
          'python': {'version':platform.python_version(), 'platform':platform.system(),
                     'architecture':platform.machine(),
                     'isolated_flag':bool(sys.flags.isolated),
                     'active_equals_base_prefix':sys.prefix==sys.base_prefix,
                     'venv_config_present':(Path(sys.prefix)/'pyvenv.cfg').is_file()},
          'release_inventory_verified_by_gate':next((g['status'] for g in report['gates']
                                     if g['id']=='source_integrity'), 'NOT_RUN'),
          'regression_group_events':group_lines,
          'regression_failure_ids':sorted(set(failures))[:75],
          'gates':[{'id':g['id'],'status':g['status'],
                    'elapsed_s':g.get('duration_seconds',0),
                    'reason':g.get('reason',''), 'log':g['log'],
                    'log_sha256':g['log_sha256'],
                    **({'counts':g['counts']} if 'counts' in g else {})}
                   for g in report['gates']],
          'human_review_required_for_physical_qualification':True,
        }
        data['DIAGNOSTICS.json'] = (json.dumps(diagnostic,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
        # Only synthetic acceptance screenshots from this run; no real project data.
        capture_root = work/'browser-captures'
        if capture_root.is_dir():
            images = sorted(capture_root.glob('*.png'))[:16]
            for capture in images:
                if capture.is_file() and not capture.is_symlink() and capture.stat().st_size <= 2_000_000:
                    data['captures/'+capture.name] = capture.read_bytes()
        data['INTEGRITY.json'] = (json.dumps({'schema':'sqe.qualification-file-hashes.v1',
                    'files':{k:sha(v) for k,v in sorted(data.items())}},indent=2,sort_keys=True)+'\n').encode()
        # Atomic output: do not clobber a previous valid report on zip failure.
        temp_output = output.with_name(output.name+'.partial')
        try:
            with zipfile.ZipFile(temp_output,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as bundle:
                for name, payload in sorted(data.items()):
                    bundle.writestr(name,payload)
            with zipfile.ZipFile(temp_output) as bundle:
                if bundle.testzip() is not None:raise RuntimeError('Generated report failed ZIP integrity')
            os.replace(temp_output,output)
        finally:
            temp_output.unlink(missing_ok=True)
    emit('Saved: qualification report ZIP. Scientific release status remains blocked.')
    return report


def main():
    parser=argparse.ArgumentParser(description='Developer automation; GUI users use the desktop launcher.')
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--profile',choices=('quick','comprehensive'),default='comprehensive')
    args=parser.parse_args()
    result=qualify(args.source,args.report,profile=args.profile,notify=print)
    print(json.dumps({'rc_status':result['rc_status'],'counts':result['counts']},sort_keys=True))
    return 1 if result['counts']['FAIL'] else 0


if __name__=='__main__':raise SystemExit(main())
