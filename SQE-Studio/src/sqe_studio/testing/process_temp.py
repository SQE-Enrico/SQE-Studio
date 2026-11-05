"""Private subprocess work outside source, with short paths for browser IPC."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def process_workspace(root, *, parents=None):
    """Prefer short POSIX temp paths; retain the writable source-parent fallback.

    The report collector has a separate lifetime and location. Children inherit
    this directory through TMPDIR/TEMP/TMP so Chromium's Unix sockets fit their
    platform limit even when the checkout or report path is long.
    """
    root = Path(root).resolve(strict=True)
    if parents is None:
        parents = (Path('/tmp'), Path('/var/tmp'), root.parent) if os.name == 'posix' else (root.parent,)
    last_error = None
    for parent in parents:
        try:
            parent = Path(parent).resolve(strict=True)
            if parent.is_relative_to(root):
                continue
            workspace = tempfile.TemporaryDirectory(prefix='.sqe-regression-', dir=parent)
        except OSError as exc:
            last_error = exc
            continue
        with workspace as directory:
            yield Path(directory)
        return
    raise OSError('No writable temporary directory outside source root') from last_error
