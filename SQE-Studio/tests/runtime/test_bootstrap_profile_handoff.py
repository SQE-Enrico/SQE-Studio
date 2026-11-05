"""A15 Windows nested-venv bootstrap profile handoff regression."""
from __future__ import annotations
import runpy
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / 'scripts/portable_regression.py'


def test_a15_native_profile_only_for_a15_on_windows():
    helper = runpy.run_path(str(RUNNER))['_group_environment']
    data = {'HOME': 'synthetic-home', 'USERPROFILE': 'synthetic-profile',
            'SQE_A15_BOOTSTRAP_HOME': 'real-home',
            'SQE_A15_BOOTSTRAP_USERPROFILE': 'real-profile',
            'SQE_A15_BOOTSTRAP_HOMEDRIVE': 'X:',
            'SQE_A15_BOOTSTRAP_HOMEPATH': r'\Users\account',
            'PYTHONNOUSERSITE': '1', 'PIP_NO_INDEX': '1'}
    child = helper('runtime', data, windows=True)
    assert child['HOME'] == 'real-home'
    assert child['USERPROFILE'] == 'real-profile'
    assert child['PYTHONNOUSERSITE'] == '1'
    assert child['PIP_NO_INDEX'] == '1'
    assert not any(k.startswith('SQE_A15_BOOTSTRAP_') for k in child)
    other = helper('security', data, windows=True)
    assert other['HOME'] == 'synthetic-home'
    assert other['USERPROFILE'] == 'synthetic-profile'
    assert not any(k.startswith('SQE_A15_BOOTSTRAP_') for k in other)
    unix = helper('runtime', data, windows=False)
    assert unix['HOME'] == 'synthetic-home'


def test_no_host_profile_handoff_fails_closed_to_synthetic_profile():
    helper = runpy.run_path(str(RUNNER))['_group_environment']
    result = helper('runtime', {'HOME':'synthetic'}, windows=True)
    assert result['HOME'] == 'synthetic'
    assert 'USERPROFILE' not in result
