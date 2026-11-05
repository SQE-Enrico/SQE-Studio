"""M4 A99 production controller with manual-only POST boundary."""
from pathlib import Path
import shutil
import subprocess
import pytest

def test_m4_research_post_controller():
    node=shutil.which('node')
    if not node:pytest.skip('Node not installed')
    root=Path(__file__).resolve().parents[2]
    cmd=[node,str(Path(__file__).with_name('m4_manual_transmon_http_controller.cjs')),
         str(root/'src/sqe_studio/web/app.js')]
    completed=subprocess.run(cmd,text=True,capture_output=True,timeout=25)
    assert completed.returncode==0,(completed.stdout,completed.stderr)
