"""Only archive-boundary checks; files below are non-scientific fixtures."""
import io
import json
import zipfile
from pathlib import Path
import pytest
from sqe_studio.jobs import Jobs
from sqe_studio.store import Store


def test_export_zip_excludes_symlinks_and_has_no_traversal(tmp_path):
    store=Store(tmp_path/'private')
    store.setup('user@example.test','ProperPassword_123')
    uid=store.conn().execute('SELECT id FROM accounts').fetchone()['id']
    p=store.create(uid,'Fixture only','transmon')
    folder=store.root/'native-runs'/p['id']/('f'*32)
    folder.mkdir(parents=True)
    store.put_run(uid,p['id'],p['head'],'not_a_solver_study','scqubits',folder)
    store.set_run(folder.name,'failed')
    (folder/'log.txt').write_text('not a scientific result',encoding='utf-8')
    outside=tmp_path/'private-note';outside.write_text('Never package outside bytes')
    try:
        (folder/'leak.txt').symlink_to(outside)
    except (OSError,NotImplementedError):
        pytest.skip('No symlink permissions')
    # An untrusted symlink in a native workspace is a hard failure, never
    # silently filtered into a seemingly clean diagnostic archive.
    with pytest.raises(ValueError, match='Linked files'):
        Jobs(store).archive(uid,p['id'],folder.name)
    (folder/'leak.txt').unlink()
    data=Jobs(store).archive(uid,p['id'],folder.name)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist()==['log.txt']
        assert z.read('log.txt')==b'not a scientific result'
        assert all('..' not in Path(name).parts and not name.startswith('/') for name in z.namelist())


def test_symlink_database_root_refused(tmp_path):
    real=tmp_path/'real';real.mkdir()
    link=tmp_path/'linked'
    try:link.symlink_to(real, target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip('No symlink permissions')
    with pytest.raises(ValueError,match='symbolic link'):Store(link)
    assert not (real/'studio.sqlite3').exists()
