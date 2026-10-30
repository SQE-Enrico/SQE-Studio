"""Private SQLite storage with immutable revisions and revocable hashed sessions.

Database schema is the foundation v1 schema. No implicit project/schema migration.
Only the password hash *value* evolves; 250k-round legacy values still verify.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from .contracts import fresh_project, validate_project, digest

class Conflict(ValueError): pass
class NotFound(ValueError): pass

# PBKDF2 is provided by Python's standard library: no alternative password
# verifier is needed during installation or a disconnected upgrade.
KDF_ITERATIONS = 600_000
LEGACY_ITERATIONS = 250_000
MAX_PASSWORD_CHARS = 1024

class Store:
    def __init__(self,root):
        root=Path(root).absolute()
        if root.is_symlink():
            raise ValueError('Data root must not be a symbolic link')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=root.resolve()
        if not self.root.is_dir():
            raise ValueError('Data root must be a directory')
        if os.name=='posix':
            # Existing permissive databases must be fixed by the owner, not
            # made publicly readable during a backup or repair operation.
            self.root.chmod(self.root.stat().st_mode & 0o700)
        self.db=self.root/'studio.sqlite3'
        if self.db.is_symlink():
            raise ValueError('Database must not be a symbolic link')
        with self.conn() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS sessions(token_sha TEXT PRIMARY KEY, user_id TEXT NOT NULL, csrf TEXT NOT NULL, until REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, head TEXT NOT NULL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent TEXT, snapshot TEXT NOT NULL, digest TEXT NOT NULL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision_id TEXT NOT NULL, study_id TEXT NOT NULL, engine TEXT NOT NULL, state TEXT NOT NULL, path TEXT NOT NULL, created REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(until);
              CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner);
              CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id);
              CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
            ''')
        if os.name=='posix': self.db.chmod(0o600)
    def conn(self):
        db=sqlite3.connect(str(self.db),timeout=20)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=20000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        return db
    @staticmethod
    def _valid_password(password):
        return (isinstance(password,str) and 12<=len(password)<=MAX_PASSWORD_CHARS
                and not any(ord(ch)<32 or ord(ch)==127 for ch in password))
    @staticmethod
    def _key(password,salt,iterations=KDF_ITERATIONS):
        hashed=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),iterations).hex()
        return f'pbkdf2_sha256${iterations}${hashed}'
    @classmethod
    def _matches(cls,password,salt,stored):
        if not isinstance(stored,str):return False
        if stored.startswith('pbkdf2_sha256$'):
            try:
                method,count,hexdigest=stored.split('$')
                count=int(count)
                if method!='pbkdf2_sha256' or not (LEGACY_ITERATIONS<=count<=2_000_000):return False
            except ValueError:return False
            return hmac.compare_digest(cls._key(password,salt,count),stored)
        # Only support the exact previous foundation encoding.
        if len(stored)!=64 or any(c not in '0123456789abcdef' for c in stored):return False
        return hmac.compare_digest(cls._key(password,salt,LEGACY_ITERATIONS).split('$')[-1],stored)
    @staticmethod
    def _email(value):
        if not isinstance(value,str):return None
        email=value.strip().lower()
        if not 4<=len(email)<=200 or email.count('@')!=1 or any(c.isspace() or ord(c)<33 for c in email):return None
        return email
    def has_account(self):
        with self.conn() as db: return bool(db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone())
    def setup(self,email,password):
        normalized=self._email(email)
        if not normalized or not self._valid_password(password):
            raise ValueError('Use a valid email and password of 12 to 1024 characters without control characters')
        with self.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM accounts').fetchone(): raise Conflict('Administrator already configured')
            salt=secrets.token_hex(16);uid=uuid.uuid4().hex
            db.execute('INSERT INTO accounts VALUES (?,?,?,?)',(uid,normalized,salt,self._key(password,salt)))
            db.commit()
    def login(self,email,password):
        normalized=self._email(email)
        if not normalized or not self._valid_password(password):return None
        with self.conn() as db:
            rec=db.execute('SELECT * FROM accounts WHERE email=?',(normalized,)).fetchone()
            # Keep unknown-user password verification comparable to a valid user.
            if not rec:
                self._key(password,'00'*16)
                return None
            if not self._matches(password,rec['salt'],rec['password_hash']):return None
            token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
            db.execute('BEGIN IMMEDIATE')
            if not rec['password_hash'].startswith('pbkdf2_sha256$'):
                db.execute('UPDATE accounts SET password_hash=? WHERE id=? AND password_hash=?',
                           (self._key(password,rec['salt']),rec['id'],rec['password_hash']))
            db.execute('DELETE FROM sessions WHERE until<=?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (hashlib.sha256(token.encode('ascii')).hexdigest(),rec['id'],csrf,time.time()+8*3600))
            db.commit()
        return token,csrf
    def change_password(self,user_id,current,new):
        if not self._valid_password(new):
            raise ValueError('New password must be 12 to 1024 characters without control characters')
        if not isinstance(current,str) or len(current)>MAX_PASSWORD_CHARS:return False
        with self.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            rec=db.execute('SELECT salt,password_hash FROM accounts WHERE id=?',(user_id,)).fetchone()
            if not rec or not self._matches(current,rec['salt'],rec['password_hash']):return False
            salt=secrets.token_hex(16)
            db.execute('UPDATE accounts SET salt=?,password_hash=? WHERE id=?',(salt,self._key(new,salt),user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            db.commit()
        return True
    def session(self,token):
        if not isinstance(token,str) or not (40<=len(token)<=128):return None
        with self.conn() as db:
            row=db.execute('SELECT user_id, csrf FROM sessions WHERE token_sha=? AND until>?',
                           (hashlib.sha256(token.encode('utf-8')).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None
    def logout(self,token):
        if not token:return
        with self.conn() as db:
            db.execute('DELETE FROM sessions WHERE token_sha=?',(hashlib.sha256(token.encode('utf-8')).hexdigest(),))
            db.commit()
    def create(self,owner,name,family,model=None):
        model=validate_project(model if model is not None else fresh_project(name,family));pid=uuid.uuid4().hex;rid=uuid.uuid4().hex
        raw=json.dumps(model,sort_keys=True,allow_nan=False)
        with self.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO projects VALUES (?,?,?,?,?)',(pid,owner,model['name'],rid,time.time()))
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',(rid,pid,None,raw,digest(model),time.time()))
            db.commit()
        return {'id':pid,'head':rid,'model':model}
    def list_projects(self,owner):
        with self.conn() as db:
            rows=db.execute('SELECT id,name,head,created FROM projects WHERE owner=? ORDER BY created DESC',(owner,)).fetchall()
            return [dict(r) for r in rows]
    def project(self,owner,pid,rid=None):
        with self.conn() as db:
            p=db.execute('SELECT * FROM projects WHERE id=? AND owner=?',(pid,owner)).fetchone()
            if not p: raise NotFound('Project not found')
            r=db.execute('SELECT * FROM revisions WHERE project_id=? AND id=?',(pid,rid or p['head'])).fetchone()
            if not r: raise NotFound('Revision not found')
            return {'id':pid,'name':p['name'],'head':p['head'],'revision':r['id'],'parent':r['parent'],
                    'revision_digest':r['digest'],'model':json.loads(r['snapshot'])}
    def revisions(self,owner,pid):
        self.project(owner,pid)
        with self.conn() as db:
            return [dict(r) for r in db.execute('SELECT id,parent,digest,created FROM revisions WHERE project_id=? ORDER BY created DESC',(pid,))]
    def commit(self,owner,pid,expected,model):
        validate_project(model)
        rid=uuid.uuid4().hex;raw=json.dumps(model,sort_keys=True,allow_nan=False)
        if len(raw.encode('utf-8'))>256*1024:raise ValueError('Project exceeds 256 KiB cap')
        with self.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            p=db.execute('SELECT head FROM projects WHERE id=? AND owner=?',(pid,owner)).fetchone()
            if not p: raise NotFound('Project not found')
            if p['head']!=expected: raise Conflict('Revision conflict: reload the latest project before saving')
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',(rid,pid,expected,raw,digest(model),time.time()))
            db.execute('UPDATE projects SET head=?,name=? WHERE id=?',(rid,model['name'],pid))
            db.commit()
        return rid
    def put_run(self,owner,pid,rid,study,engine,folder):
        # The revision MUST exist within this owner-scoped project.
        self.project(owner,pid,rid)
        run_id=folder.name
        with self.conn() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(run_id,pid,rid,study,engine,'queued',str(folder),time.time()))
            db.commit()
        return run_id
    def set_run(self,run_id,status):
        with self.conn() as db:
            db.execute('UPDATE runs SET state=? WHERE id=?',(status,run_id));db.commit()
    def runs(self,owner,pid):
        self.project(owner,pid)
        with self.conn() as db:
            return [dict(r) for r in db.execute('SELECT id,revision_id,study_id,engine,state,created FROM runs WHERE project_id=? ORDER BY created DESC',(pid,))]
    def run(self,owner,pid,run_id):
        self.project(owner,pid)
        with self.conn() as db:
            row=db.execute('SELECT * FROM runs WHERE id=? AND project_id=?',(run_id,pid)).fetchone()
            if not row: raise NotFound('Run not found')
            return dict(row)
