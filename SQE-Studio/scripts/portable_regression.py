#!/usr/bin/env python3
"""Fixed RC14.12 portable regression in bounded, isolated pytest processes.

Avoid shared plugin/fixture shutdown between unrelated domains. This is NOT a
selector or test exclusion: domain groups cover the entire tests/ tree;
individual real-browser skips remain visible and run again under browser gate.
Never report a PASS for a group with nonzero exit, missing summary or timeout.
"""
from __future__ import annotations
from pathlib import Path
import os
import json
import re
import subprocess
import sys
import time
import platform
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sqe_studio.testing.process_temp import process_workspace

GROUPS=tuple((folder.name,(folder.relative_to(ROOT).as_posix(),))
             for folder in sorted((ROOT/'tests').iterdir()) if folder.is_dir()
             and any(folder.rglob('test_*.py')))+(('top_level',tuple(
                 p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'tests').glob('test_*.py')))),)
SUMMARY = re.compile(r'(?<!\d)(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) xfailed)?')


LEGACY_UNTRACKED = frozenset()


def _release_test_files():
    """Select exactly release-signed pytest sources, not host-local additions.

    This does NOT waive source integrity: the separate source gate reports
    every added file as FAIL, and unexpected extras fail this runner as well.
    """
    manifest = json.loads((ROOT/'EDA_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    listed = manifest['files']
    expected = {name for name in listed
                if name.startswith('tests/') and Path(name).name.startswith('test_')
                and name.endswith('.py')}
    if expected & LEGACY_UNTRACKED:
        raise RuntimeError('Obsolete test was signed in the current release inventory')
    for name in expected:
        path = ROOT/name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Expected release test is missing or linked: '+name)
        import hashlib
        if hashlib.sha256(path.read_bytes()).hexdigest() != listed[name]:
            raise RuntimeError('Release test hash differs from inventory: '+name)
    on_disk = {p.relative_to(ROOT).as_posix()
               for p in (ROOT/'tests').rglob('test_*.py')}
    extras = on_disk - expected
    if extras - LEGACY_UNTRACKED:
        raise RuntimeError('Unknown untracked test files detected: '+str(len(extras-LEGACY_UNTRACKED)))
    if extras:
        print('UNTRACKED_LEGACY_TESTS_SOURCE_INTEGRITY_REMAINS_FAIL '+str(len(extras)),flush=True)
    return expected


def _a15_host_facts():
    """Non-identifying interpreter relationships, never host paths or env values."""
    def same(a, b):
        try:
            return os.path.samefile(a, b)
        except (OSError, ValueError):
            return False
    cfg = Path(sys.prefix) / 'pyvenv.cfg'
    return {
        'schema': 'sqe.a15-host-relations.v1',
        'os': os.name,
        'python_version': platform.python_version(),
        'active_is_base_prefix': same(sys.prefix, sys.base_prefix),
        'active_equals_base_prefix_text': os.path.normcase(sys.prefix) == os.path.normcase(sys.base_prefix),
        'active_has_venv_config': cfg.is_file(),
        'active_executable_exists': Path(sys.executable).is_file(),
        'active_executable_symlink': Path(sys.executable).is_symlink(),
        'base_executable_exists': Path(getattr(sys, '_base_executable', sys.executable)).is_file(),
        'base_executable_samefile_active': same(getattr(sys, '_base_executable', sys.executable), sys.executable),
        'active_executable_is_under_active_prefix': Path(sys.executable).absolute().is_relative_to(Path(sys.prefix).absolute()),
        'isolated_flag': bool(sys.flags.isolated),
        'no_user_site_flag': bool(sys.flags.no_user_site),
        'pythonhome_present': bool(os.environ.get('PYTHONHOME')),
        'pythonpath_present': bool(os.environ.get('PYTHONPATH')),
        'virtual_env_present': bool(os.environ.get('VIRTUAL_ENV')),
        'home_override_present': bool(os.environ.get('HOME')),
        'userprofile_override_present': bool(os.environ.get('USERPROFILE')),
    }


def _write_a15_case_report(cases):
    """Write current-run evidence only inside the qualification-owned temp dir.

    The parent process redacts before packaging and never trusts this as
    scientific solver evidence or an isolation-success assertion.
    """
    directory = os.environ.get('SQE_QUALIFICATION_DIAGNOSTIC_DIR')
    if not directory:
        return
    target = Path(directory)
    try:
        if not target.is_dir() or target.is_symlink():
            return
        payload = {'schema': 'sqe.a15-detailed-test-evidence.v1',
                   'host_relationships': _a15_host_facts(),
                   'cases': cases[:120],
                   'note': 'Current run only; original traceback will be redacted by parent.'}
        (target / 'A15_CASES.json').write_text(
            json.dumps(payload, sort_keys=True, indent=2), encoding='utf-8')
    except (OSError, ValueError, TypeError):
        pass  # Diagnostic collection can never change acceptance or exit codes.



_BOOTSTRAP_PROFILE_KEYS = ('HOME', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH')


def _group_environment(label, source=None, *, windows=None):
    """Use the genuine Windows profile only for A15 CPython venv bootstrap.

    Test/code stdout and diagnostic reports never print profile values. The
    other ten independent groups retain the synthetic private profile.
    Explicitly discard the profile handoff variables from *all* children;
    they are a one-way context handoff, not a persistent program setting.
    """
    values = dict(os.environ if source is None else source)
    native = {}
    for name in _BOOTSTRAP_PROFILE_KEYS:
        secret = values.pop('SQE_A15_BOOTSTRAP_' + name, '')
        if secret:
            native[name] = secret
    if windows is None:
        windows = os.name == 'nt'
    if label == 'runtime' and windows:
        values.update(native)
    return values


def _run_group_process(command, label, limit):
    # Browser tests (including nested integration subprocesses) deliberately
    # require captures outside the entire source root. Use short POSIX paths
    # so Chromium can also create its bounded-length Unix IPC sockets.
    with process_workspace(ROOT) as workspace:
        work = str(workspace)
        env = _group_environment(label)
        env.update(TMPDIR=work, TEMP=work, TMP=work,
                   SQE_BROWSER_CAPTURE_DIR=str(Path(work) / 'browser-captures'))
        return subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=limit, check=False)


def run_group(label, paths):
    # The A15 group is the known Windows virtualenv issue: keep individual
    # test outcomes and long traceback on failure, without recording host paths
    # in the structured diagnostic metadata. All other groups stay compact.
    detail = label == 'runtime'
    xml = None
    junit_dir = None
    if detail:
        import tempfile
        junit_dir = Path(tempfile.mkdtemp(prefix='sqe-a15-junit-'))
        xml = junit_dir / 'current-run.xml'
    command = [sys.executable, '-m', 'pytest', '-vv' if detail else '-q', '-ra',
               '--tb=short', '--durations=12',
               '-p', 'no:cacheprovider', *(['--junitxml='+str(xml)] if xml else []), *paths]
    begin = time.monotonic()
    print(f'GROUP_START {label} mode={"detailed" if detail else "standard"} '
          f'file_count={len(paths)}', flush=True)
    limit = 540 if label in ('adapters', 'integration') else 360
    try:
        result = _run_group_process(command, label, limit)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'GROUP {label} exit=BLOCKED_TIMEOUT_OR_SPAWN {type(exc).__name__} '
              f'elapsed_s={round(time.monotonic()-begin,2)} limit_s={limit}', flush=True)
        if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout:
            tail = exc.stdout.decode('utf8','replace')[-18000:] if isinstance(exc.stdout,bytes) else str(exc.stdout)[-18000:]
            print('GROUP_TIMEOUT_LAST_OUTPUT '+label+' '+repr(tail), flush=True)
        if junit_dir is not None:
            import shutil
            shutil.rmtree(junit_dir, ignore_errors=True)
        return None
    text = result.stdout.decode('utf8','replace')
    match = SUMMARY.search(text)
    print(f'GROUP {label} exit={result.returncode} elapsed_s={round(time.monotonic()-begin,2)} '
          f'passed={match.group(1) if match else "NONE"} '
          f'skipped={match.group(2) if match and match.group(2) else "0"}', flush=True)
    if xml is not None:
        try:
            report_xml = ET.parse(xml).getroot()
            failed_cases = []
            cases = []
            for case in report_xml.iter('testcase'):
                issue = next((child for child in case if child.tag in ('failure','error')), None)
                skipped = any(child.tag == 'skipped' for child in case)
                node = (case.get('classname','') + '::' + case.get('name',''))[:240]
                status = issue.tag.upper() if issue is not None else ('SKIP' if skipped else 'PASS')
                row = {'test': node, 'status': status,
                       'duration_s': float(case.get('time', '0') or 0)}
                if issue is not None:
                    # Capture both the short assertion and the real JUnit
                    # traceback, rather than discarding everything after 700
                    # characters. Sanitization is done before ZIP export.
                    row['diagnostic'] = (issue.get('message', '') or '')[:4000]
                    row['traceback'] = (issue.text or '')[-12000:]
                    failed_cases.append({'test':node, 'diagnostic': row['diagnostic'][:700]})
                cases.append(row)
            _write_a15_case_report(cases)
            if failed_cases:
                print('GROUP_A15_STRUCTURED_FAILURES '+json.dumps(failed_cases[:40], sort_keys=True),flush=True)
        except (OSError, ET.ParseError):
            print('GROUP_A15_STRUCTURED_FAILURES unavailable',flush=True)
        finally:
            import shutil
            shutil.rmtree(junit_dir, ignore_errors=True)
    if result.returncode != 0 or not match:
        # Report bounded last lines, so the enclosing qualification retains
        # actionable failure evidence. The parent scrubs private host paths.
        print('GROUP_FAIL_DETAIL_BEGIN '+label,flush=True)
        print(text[-20000:] if detail else text[-8000:],flush=True)
        print('GROUP_FAIL_DETAIL_END '+label,flush=True)
        return None
    if detail:
        # Preserve per-test outcomes in the parent report, not only pass counts.
        # Full subprocess output is scrubbed by qualification._safe_log.
        print('GROUP_A15_TEST_OUTCOMES_BEGIN',flush=True)
        print(text[-18000:],flush=True)
        print('GROUP_A15_TEST_OUTCOMES_END',flush=True)
    return int(match.group(1)),int(match.group(2) or 0)


def main():
    expected = _release_test_files()
    seen=set()
    for label, paths in GROUPS:
        for path in paths:
            if path in seen: raise RuntimeError('Duplicate test source in fixed driver: '+path)
            seen.add(path)
    # Expand groups from signed inventory only. No machine-local stale tests
    # can enter pytest collection or influence unrelated release test results.
    selected = []
    intended=set()
    for label, paths in GROUPS:
        files=set()
        for name in paths:
            if name.endswith('.py'):
                if name in expected: files.add(name)
            else:
                files.update(item for item in expected if item.startswith(name.rstrip('/')+'/'))
        selected.append((label,tuple(sorted(files))))
        intended.update(files)
    if intended != expected:
        print('GROUP COVERAGE_MISMATCH missing='+str(len(expected-intended))+
              ' extra='+str(len(intended-expected)),flush=True)
        return 1
    passed=skipped=0
    failures=[]
    for label, paths in selected:
        result=run_group(label,paths)
        if result is None:
            # Continue independent groups, so one Windows-only fixture cannot
            # suppress all subsequent EDA/security/browser diagnostics. The
            # final exit remains nonzero, and failed groups never count PASS.
            failures.append(label)
            print('REGRESSION_GROUP_FAILED_CONTINUING '+label,flush=True)
            continue
        passed+=result[0];skipped+=result[1]
    if failures:
        print('REGRESSION_FAIL groups='+','.join(failures),flush=True)
        print(f'REGRESSION_PARTIAL_SUCCESS {passed} passed, {skipped} skipped '
              '(failed groups excluded from pass totals)',flush=True)
        return 1
    print(f'{passed} passed, {skipped} skipped',flush=True)
    print('SPLIT_PROCESS_REGRESSION_COMPLETE all_groups_exit_zero',flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
