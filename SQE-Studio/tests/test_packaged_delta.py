"""Frozen tool parity and installed-entrypoint implementation smoke."""
from pathlib import Path
from sqe_studio import agent_delta


def test_packaged_delta_parity_with_frozen_tool():
    root = Path(__file__).resolve().parents[1]
    assert Path(agent_delta.__file__).read_bytes() == (root / 'tools' / 'delta.py').read_bytes()
    assert callable(agent_delta.main)
