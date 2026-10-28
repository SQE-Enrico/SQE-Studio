"""Server-side sessions, PBKDF2 passwords, one-use invitations and CSRF tokens."""
import hashlib
import hmac
import re
import secrets
import time

from .db import uid

ITERATIONS = 600_000


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise Problem('Use a password of 12–256 characters')
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${key.hex()}'


def verify_password(password, encoded):
    try:
        _, count, salt, expected = encoded.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex()
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError, TypeError):
        return False


def email(value):
    value = str(value).strip().lower()
    if not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,150}\.[^\s@]{2,30}', value):
        raise Problem('Enter a valid email address')
    return value


class Auth:
    def __init__(self, store):
        self.store = store

    def setup_token(self):
        path = self.store.root/'setup-token'
        if self.store.one('SELECT id FROM users LIMIT 1'):
            return None
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            import os
            token = secrets.token_urlsafe(32)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(token)
            except FileExistsError:
                token = path.read_text().strip()
            return token

    def setup(self, token, user_email, name, password):
        expected = self.setup_token()
        if not expected or len(expected)<32 or not hmac.compare_digest(str(token), expected):
            raise Problem('Invalid or already used setup token', 403)
        hashed = password_hash(password)
        user_email = email(user_email)
        user_id = uid()
        with self.store.connect(True) as db:
            if db.execute('SELECT id FROM users LIMIT 1').fetchone():
                raise Problem('Initial setup is already complete', 409)
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                       (user_id, user_email, str(name)[:100], hashed, 'admin', 1, time.time()))
        (self.store.root/'setup-token').unlink(missing_ok=True)
        return user_id

    def login(self, user_email, password, address):
        key = token_hash(address + ':' + str(user_email).lower())
        now = time.time()
        with self.store.connect(True) as db:
            row = db.execute('SELECT * FROM attempts WHERE key=?', (key,)).fetchone()
            if row and now-row['first'] < 900 and row['count'] >= 10:
                raise Problem('Too many attempts; try again in 15 minutes', 429)
            if not row or now-row['first'] >= 900:
                db.execute('INSERT OR REPLACE INTO attempts VALUES(?,1,?)', (key, now))
            else:
                db.execute('UPDATE attempts SET count=count+1 WHERE key=?', (key,))
        user = self.store.one('SELECT * FROM users WHERE email=? AND active=1', (str(user_email).lower().strip(),))
        if not user:
            # Comparable PBKDF work for an unknown identity.
            hashlib.pbkdf2_hmac('sha256', str(password).encode(), b'unknown-user-salt', ITERATIONS)
            raise Problem('Invalid email or password', 401)
        if not verify_password(str(password), user['password']):
            raise Problem('Invalid email or password', 401)
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.store.connect(True) as db:
            db.execute('DELETE FROM attempts WHERE key=?', (key,))
            db.execute('DELETE FROM sessions WHERE expires<?', (now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                       (token_hash(raw), user['id'], csrf, now+self.store.settings.session_hours*3600))
        return raw, csrf, self.public_user(user)

    @staticmethod
    def public_user(user):
        return {key: user[key] for key in ('id', 'email', 'name', 'role')}

    def session(self, raw):
        row = self.store.one('SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id '
                             'WHERE s.token=? AND s.expires>? AND u.active=1', (token_hash(raw), time.time()))
        if not row:
            raise Problem('Please sign in', 401)
        return self.public_user(row), row['csrf']

    def logout(self, raw):
        with self.store.connect(True) as db:
            db.execute('DELETE FROM sessions WHERE token=?', (token_hash(raw),))

    def invite(self, actor, user_email, name, role='researcher'):
        if actor['role'] != 'admin':
            raise Problem('Administrator access required', 403)
        if role not in ('admin', 'researcher', 'viewer'):
            raise Problem('Invalid role')
        user_email = email(user_email)
        if self.store.one('SELECT id FROM users WHERE email=?', (user_email,)):
            raise Problem('This email already has an account', 409)
        raw, user_id = secrets.token_urlsafe(32), uid()
        with self.store.connect(True) as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                       (user_id, user_email, str(name)[:100], None, role, 1, time.time()))
            db.execute('INSERT INTO invitations VALUES(?,?,?)', (token_hash(raw), user_id, time.time()+72*3600))
        self.store.audit(actor['id'], None, 'invite_user', {'user': user_id, 'role': role})
        return {'user_id': user_id, 'activation_url': self.store.settings.origin+'/#activate='+raw}

    def activate(self, raw, password):
        hashed = password_hash(password)
        with self.store.connect(True) as db:
            invite = db.execute('SELECT * FROM invitations WHERE token=? AND expires>?',
                                (token_hash(raw), time.time())).fetchone()
            if not invite:
                raise Problem('Invitation is expired or already used', 403)
            db.execute('UPDATE users SET password=? WHERE id=?', (hashed, invite['user_id']))
            db.execute('DELETE FROM invitations WHERE token=?', (token_hash(raw),))
