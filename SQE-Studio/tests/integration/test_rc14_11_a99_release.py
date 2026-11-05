"""A99 release-boundary regressions: no stage promotion by a name change."""
import json
import re
import tomllib
from pathlib import Path
from sqe_studio import __version__
from sqe_studio.cycle_qualification import next_report_path, _read_plan

ROOT=Path(__file__).resolve().parents[2]

def test_rc1411_stable_identity_and_scientific_hold(tmp_path):
    # Match the actual packaged version, rather than a historical developer build.
    # A release-number bump must not bypass the RC14.12 scientific HOLD gates.
    packaged = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    assert re.fullmatch(r'0\.1\.1\.dev[1-9][0-9]*', packaged)
    assert __version__ == packaged
    p=_read_plan(ROOT)
    assert p['release']=='RC14.12'
    assert p['scientific_gates']=={'mode_identity':'BLOCKED_UNTIL_COMPLEX_OVERLAP',
        'em_to_hamiltonian':'BLOCKED_UNTIL_VALIDATED','fabrication':'HOLD'}
    (tmp_path/'qualification_plan.json').write_bytes((ROOT/'qualification_plan.json').read_bytes())
    first=next_report_path(tmp_path)
    assert first.name=='SQE-RC14_12-report-0001.zip'
    first.write_bytes(b'old report must remain untouched')
    assert next_report_path(tmp_path).name=='SQE-RC14_12-report-0002.zip'
    assert first.read_bytes()==b'old report must remain untouched'

def test_automatic_test_launcher_single_click_and_production_gui():
    launcher=(ROOT/'Launch SQE Studio.pyw').read_text(encoding='utf-8')
    desktop=(ROOT/'src/sqe_studio/testing/desktop.py').read_text(encoding='utf-8')
    assert 'install_controls(root,' in launcher
    assert "text='Automatic Test'" in desktop
    assert 'threading.Thread(target=worker' in desktop
    assert 'run_release_qualification(source, destination' in desktop
    assert 'text="Run qualification"' not in launcher
    assert 'webbrowser.open_new_tab(url)' in launcher

def test_frozen_science_and_no_old_report_acceptance():
    src=(ROOT/'src/sqe_studio/cycle_qualification.py').read_text()
    assert 'RC14_7-report-' not in src
    assert "cycle.get('release') != 'RC14.12'" in src
    assert "'unchanged_native_runs_reused':False" in src

def test_current_operator_docs_do_not_require_second_run():
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    laptop=(ROOT/'docs/TESTING.md').read_text(encoding='utf-8')
    assert 'Press the **only test button**' not in readme
    assert 'Click **Automatic Test** once' in laptop
    assert 'SQE-RC14_12-report-0001.zip' in laptop
