"""Fabrication handoff never implies a foundry-approved release."""
from pathlib import Path


def test_fabrication_hold_disabled_without_disabling_layout_gds():
    src = (Path(__file__).resolve().parents[2] / 'src' / 'sqe_studio' / 'web' / 'app.js').read_text(encoding='utf-8')
    assert 'id="fabricationRun" disabled aria-disabled="true"' in src
    assert "$('fabricationRun').onclick" not in src
    assert 'id="gdsRun"' in src
    assert "runSavedStudy('quantum_metal')" in src
