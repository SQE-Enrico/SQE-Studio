"""SQLite handles are released before Windows qualification temp cleanup."""
import sqlite3
import pytest
from sqe_studio.store import Store


def test_store_context_releases_connection_after_success(tmp_path):
    store = Store(tmp_path / 'isolated')
    with store.conn() as db:
        assert db.execute('SELECT 1').fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with store.conn() as reader:
        assert reader.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0


def test_store_context_rolls_back_and_releases_on_error(tmp_path):
    store = Store(tmp_path / 'isolated')
    with pytest.raises(RuntimeError, match='abort'):
        with store.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO accounts VALUES (?, ?, ?, ?)',
                       ('u1', 'test@example.invalid', 'a', 'b'))
            raise RuntimeError('abort')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with store.conn() as reader:
        assert reader.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0
