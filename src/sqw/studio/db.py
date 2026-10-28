"""Short SQLite WAL transactions on a single local disk; never share this DB over NFS."""
from contextlib import contextmanager
import json
import sqlite3
import time
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,
 password TEXT,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,first REAL NOT NULL);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,owner_id TEXT NOT NULL REFERENCES users(id),
 draft TEXT NOT NULL,draft_version INTEGER NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS members(project_id TEXT NOT NULL REFERENCES projects(id),user_id TEXT NOT NULL REFERENCES users(id),
 role TEXT NOT NULL,PRIMARY KEY(project_id,user_id));
CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),
 parent_id TEXT,document TEXT NOT NULL,note TEXT NOT NULL,author_id TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),revision_id TEXT NOT NULL REFERENCES revisions(id),
 author_id TEXT NOT NULL,target TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,cpus INTEGER NOT NULL,memory_gb INTEGER NOT NULL,
 baseline_id TEXT,options TEXT NOT NULL,progress REAL NOT NULL DEFAULT 0,stage TEXT,error TEXT,pid INTEGER,created REAL NOT NULL,
 started REAL,finished REAL,heartbeat REAL);
CREATE TABLE IF NOT EXISTS results(job_id TEXT NOT NULL REFERENCES jobs(id),stage TEXT NOT NULL,signature TEXT NOT NULL,
 reused_from TEXT,consolidated_by TEXT,consolidated_at REAL,notes TEXT NOT NULL DEFAULT '',PRIMARY KEY(job_id,stage));
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),name TEXT NOT NULL,
 kind TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS macros(id TEXT PRIMARY KEY,name TEXT NOT NULL,code TEXT NOT NULL,sha256 TEXT NOT NULL,
 author_id TEXT NOT NULL,approved_by TEXT,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,project_id TEXT,
 action TEXT NOT NULL,detail TEXT NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(state,created);
CREATE INDEX IF NOT EXISTS revisions_project ON revisions(project_id,created);
'''


def uid():
    return uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


class Store:
    def __init__(self, settings):
        settings.validate()
        self.settings = settings
        self.root = settings.root
        self.path = self.root/'studio.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES('schema','1')")

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def audit(self, user, project, action, detail):
        with self.connect(True) as db:
            db.execute('INSERT INTO audit(user_id,project_id,action,detail,created) VALUES(?,?,?,?,?)',
                       (user, project, action, dumps(detail), time.time()))
