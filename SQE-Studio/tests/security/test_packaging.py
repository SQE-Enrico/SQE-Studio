"""Static safety checks for off-line wheelhouse installer policy."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_wheel_assets_remain_declared_in_frozen_metadata():
    metadata=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
    assert 'sqe_studio = ["web/*.html", "web/*.css", "web/*.js"]' in metadata
    for a in ('index.html','app.js','style.css'):
        assert (ROOT/'src'/'sqe_studio'/'web'/a).is_file()

def test_installer_offline_no_native_binary_fetch_or_silent_overwrite():
    install=(ROOT/'scripts'/'Install-Windows11.ps1').read_text(encoding='utf-8')
    build=(ROOT/'scripts'/'Build-Windows11Wheel.ps1').read_text(encoding='utf-8')
    assert '--no-index --no-deps' in install
    assert 'Get-FileHash -Algorithm SHA256' in install
    assert 'Existing install:' in install
    assert '--no-index --find-links' in build
    assert 'SOURCE_DATE_EPOCH' in build
    assert 'verify_wheel.py' in install
    assert not any(x in install.lower() for x in ('invoke-webrequest','curl ','wget ','pip install quantum','pip install sqdmetal'))
