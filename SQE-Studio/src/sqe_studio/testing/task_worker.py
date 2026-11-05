"""Fixed allowlisted task process. Never called with an arbitrary command."""
from __future__ import annotations

from importlib import util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqe_studio.testing.catalog import BY_ID
from sqe_studio.qualification import _run, _pytest_result


def _em_reference(root: Path, folder: Path, *, refine: bool):
    """Respect the existing qualifier's external-report contract.

    The selector's collector may be inside qualification-reports/, which is
    deliberately excluded from source inventory. The native qualifier has the
    stricter rule that its destination must be outside the entire source tree.
    Keep that rule and collect only the completed, verified, bounded report.
    """
    from sqe_studio.native_em_qualification import qualify_native_em
    from sqe_studio.feedback_qualification import _checked_members

    root = root.resolve(strict=True)
    collected = folder/'em.zip'
    if collected.exists() or collected.is_symlink():
        raise FileExistsError('Native EM report collection already exists')
    with tempfile.TemporaryDirectory(prefix='.sqe-em-report-', dir=root.parent) as td:
        native_report = Path(td)/'em.zip'
        result = qualify_native_em(root, native_report, reviewer='SQEFixedProtocol',
            acknowledged=True, solve=True, refine=refine, third_mesh=False,
            memory_budget_gb=8., time_budget_seconds=840, mpi_ranks='auto', notify=print)
        payload = _checked_members(native_report)
        if json.loads(payload['QUALIFICATION.json']) != result:
            raise ValueError('Native EM return value differs from the verified report')
        with native_report.open('rb') as source, collected.open('xb') as target:
            shutil.copyfileobj(source, target)
        _checked_members(collected)
    statuses = {row['id']: row['status'] for row in result.get('stages', [])}
    status = ('FAIL' if result['counts']['FAIL'] else
              'BLOCKED' if result['counts']['BLOCKED'] else 'PASS')
    return {'status': status, 'execution_kind': 'NATIVE_QUALIFICATION',
            'subreport': 'em.zip', 'substeps': result.get('stages', []),
            'native_execution': statuses.get('native_palace_solve', 'NOT_RUN'),
            'reason': 'NATIVE_EM_SUBSTEP_'+status if status != 'PASS' else None,
            'scientific_qualification': 'NOT_ESTABLISHED'}


def execute(task, root, folder):
    root, folder = Path(root), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PIP_NO_INDEX='1')
    env['SQE_BROWSER_CAPTURE_DIR'] = str(folder / 'browser-captures')
    steps = []
    def command(name, args, limit=120, *, pytest=False, native=False):
        code, log, seconds = _run(args, root, env, limit)
        status = 'TIMEOUT' if code is None else 'PASS' if code == 0 else 'FAIL'
        if pytest:
            status, counts = _pytest_result(code, log)
            if native and (counts.get('skipped') or not counts.get('passed')):
                status = 'BLOCKED'
        row = {'id': name, 'status': status, 'duration_s': seconds,
               'execution_kind': 'NATIVE' if native else 'SOFTWARE',
               'exit_code': code, 'log': log[-140000:]}
        steps.append(row)
        return row
    if task == 'integrity':
        command('source_integrity', [sys.executable, str(root/'tools/verify_release_source.py'), str(root)], 20)
        command('development_scope', [sys.executable, str(root/'tools/science_first_gate.py'), str(root)], 20)
    elif task == 'targeted':
        for name,folder,pattern,limit in (
                ('quantum_basis_references','quantum','test_basis_references.py',150),
                ('native_reader_contracts','fields','test_reader_contracts.py',150),
                ('field_comparison_contracts','fields','test_field_comparison.py',180),
                ('conditional_extraction','extraction','test_conditional_transmon.py',150),
                ('current_architecture','core','test_current_*.py',150)):
            row=command(name,[sys.executable,'-m','unittest','discover','-s',
                             str(root/'tests'/folder),'-p',pattern,'-v'],limit)
            if row['status']=='PASS' and not re.search(r'Ran [1-9]\d* tests?\b',row['log']):
                row.update(status='FAIL',reason='EMPTY_OR_MISSING_UNITTEST_RESULT')
        if all(s['status']=='PASS' for s in steps):
            from sqe_studio.interop.em_convergence import analyze_report_zip
            try:
                recorded=analyze_report_zip(root/'tests/fixtures/em/dev74-recorded-reference.zip')
                steps.append({'id':'recorded_em_frequency_criteria','status':'PASS',
                    'execution_kind':'RECORDED_REPORT_REPLAY','native_execution':'NOT_RUN',
                    'source_report_sha256':recorded['source_report_sha256'],
                    'source_runtime':recorded['source_runtime'],
                    'frequency_tolerance_sensitivity':recorded['frequency_tolerance_sensitivity']})
                print('Recorded dev74 criteria: 2% and 3% evaluated; no new native execution or physical mode qualification.')
            except (ValueError,OSError):
                steps.append({'id':'recorded_em_frequency_criteria','status':'FAIL',
                    'execution_kind':'RECORDED_REPORT_REPLAY','native_execution':'NOT_RUN',
                    'reason':'RECORDED_EM_CRITERION_REVIEW_INVALID'})
    elif task == 'http':
        command('source_http_workflow', [sys.executable, str(root/'scripts/qualification_installed_smoke.py')], 35)
    elif task == 'regression':
        if util.find_spec('pytest') is None:
            return {'status': 'BLOCKED', 'reason': 'PYTEST_NOT_INSTALLED'}
        command('full_portable_regression', [sys.executable, str(root/'scripts/portable_regression.py')], 1750, pytest=True)
    elif task == 'browser':
        if util.find_spec('playwright') is None:
            return {'status': 'BLOCKED', 'reason': 'PLAYWRIGHT_NOT_INSTALLED'}
        row = command('browser_real_http', [sys.executable, str(root/'scripts/browser_local_smoke.py'),
                      '--installed-python', sys.executable], 130)
        if 'BROWSER_UNAVAILABLE:' in row['log']:
            row['status'] = 'BLOCKED'
    elif task == 'cad':
        if util.find_spec('qiskit_metal') is None or util.find_spec('pytest') is None:
            return {'status': 'BLOCKED', 'reason': 'QUANTUM_METAL_OR_PYTEST_NOT_INSTALLED'}
        command('native_qdesign_gds', [sys.executable, '-m', 'pytest', '-q', '-ra', '-p',
                'no:cacheprovider', str(root/'tests/adapters/test_quantum_metal_native.py')],
                220, pytest=True, native=True)
    elif task == 'quantum':
        from sqe_studio.testing.native_quantum import run_workflow
        return run_workflow()
    elif task == 'extraction':
        from sqe_studio.testing.native_extraction import run_workflow
        return run_workflow(folder)
    elif task == 'fields':
        from sqe_studio.testing.native_fields import run_workflow
        return run_workflow()
    elif task == 'field_compare':
        from sqe_studio.testing.native_overlap import run_workflow
        return run_workflow()
    elif task == 'rf':
        from sqe_studio.native_case_bridge import execute as native
        for case in ('B05', 'B09'):
            record = native(case, folder/(case + '.json'))
            record['status'] = ('PASS' if record['execution_kind'] == 'NATIVE' and record['solver_exit_code'] == 0
                                else 'FAIL' if record['stage_status'] == 'FAIL' else 'BLOCKED')
            record['id'] = case
            record['numerical_qualification'] = record['stage_status']
            steps.append(record)
    elif task in ('em', 'em_convergence'):
        return _em_reference(root, folder, refine=task == 'em_convergence')
    elif task == 'packaging':
        wheels = folder/'wheels'; wheels.mkdir()
        built = command('fresh_wheel', [sys.executable, '-m', 'pip', 'wheel', '--no-deps',
            '--no-index', '--no-build-isolation', '--wheel-dir', str(wheels), str(root)], 100)
        if built['status'] == 'PASS':
            candidates = list(wheels.glob('sqe_studio_product_foundation-*.whl'))
            if len(candidates) != 1:
                return {'status': 'FAIL', 'reason': 'FRESH_WHEEL_MISSING_OR_AMBIGUOUS', 'substeps': steps}
            venv = folder/'installed'
            setup = command('isolated_venv', [sys.executable, '-m', 'venv', str(venv)], 45)
            if setup['status'] == 'PASS':
                py = venv/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
                installed = command('offline_install', [str(py), '-I', '-m', 'pip', 'install', '--no-index',
                    '--no-deps', str(candidates[0])], 35)
                if installed['status'] == 'PASS':
                    command('installed_identity', [str(py), '-I', str(root/'scripts/verify_installed_wheel.py'), str(candidates[0])], 20)
                    command('installed_http', [str(py), '-I', str(root/'scripts/qualification_installed_smoke.py')], 30)
    else:
        raise ValueError('Unknown task')
    statuses = [s['status'] for s in steps]
    status = next((s for s in ('FAIL', 'TIMEOUT', 'BLOCKED') if s in statuses), 'PASS')
    return {'status': status, 'substeps': steps,
            'scope': 'native execution and numerical/physical qualification are distinct'}


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in BY_ID:
        raise SystemExit(2)
    task, source, output = sys.argv[1:]
    target = Path(output)
    try:
        result = execute(task, Path(source).resolve(strict=True), target.parent/task)
    except Exception as exc:
        result = {'status': 'FAIL', 'reason': 'TASK_EXCEPTION_' + type(exc).__name__,
                  'diagnostic_message': str(exc)[:1000],
                  'execution_kind': 'NOT_ESTABLISHED'}
        print(type(exc).__name__ + ': ' + str(exc)[:1000])
    target.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
