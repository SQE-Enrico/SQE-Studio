"""Offline, read-only verification that a fresh venv imports the freshly built wheel.

The source checkout is deliberately not on PYTHONPATH. Only the wheel path is
provided by the qualification runner, never by a user design.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
from email.parser import BytesParser
from email.policy import default
import json
from pathlib import Path
import sys
import zipfile


def main(wheel: Path) -> int:
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Not running in an isolated virtual environment')
    if not wheel.is_file() or wheel.suffix != '.whl':
        raise RuntimeError('New wheel is missing')
    root = Path(sys.prefix).resolve()
    dist = metadata.distribution('sqe-studio-product-foundation')
    installed = Path(dist.locate_file('')).resolve()
    if not installed.is_relative_to(root):
        raise RuntimeError('Installed distribution is outside isolated environment')
    import sqe_studio
    package = Path(sqe_studio.__file__).resolve().parent
    if not package.is_relative_to(root) or package != installed/'sqe_studio':
        raise RuntimeError('Imported package is not the newly installed distribution')
    with zipfile.ZipFile(wheel) as archive:
        name = 'sqe_studio/server.py'
        expected = hashlib.sha256(archive.read(name)).hexdigest()
        wheel_metadata = BytesParser(policy=default).parsebytes(archive.read(next(
            n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
        # Compare parsed Core Metadata fields rather than line endings: installed
        # Windows metadata may contain CRLF, while a wheel normally stores LF.
        if (wheel_metadata.get('Version') != dist.version or
                (wheel_metadata.get('Name') or '').lower().replace('_','-')
                != 'sqe-studio-product-foundation'):
            raise RuntimeError('Wheel/distribution metadata mismatch')
    actual = hashlib.sha256((package/'server.py').read_bytes()).hexdigest()
    if expected != actual:
        raise RuntimeError('Installed server.py does not match the fresh wheel')
    print(json.dumps({'status':'PASS', 'venv_isolation':True,
                      'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
                      'installed_server_sha256':actual,
                      'distribution_version':dist.version},sort_keys=True))
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Expected exactly one wheel path')
    raise SystemExit(main(Path(sys.argv[1])))
