"""Persistent username/password accounts for Expanse's public alpha.

Maintains a separate SQLite registry from legacy passwordless `pretzel` users.
Passwords use salted scrypt (memory hard) and recovery/login tokens are stored
only as SHA-256 digests. Never log secret tokens or recovery credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path


class RegistrationError(ValueError):
    pass


class RegisteredPlayers:
    def __init__(self, directory, max_players, legacy_guests=None):
        self.path = Path(directory) / 'registered-players.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_players = max_players
        self.legacy = legacy_guests
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS registered_players (
                name TEXT NOT NULL PRIMARY KEY COLLATE NOCASE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                session_hash TEXT NOT NULL UNIQUE,
                session_until INTEGER NOT NULL,
                recovery_hash TEXT NOT NULL UNIQUE,
                email TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                pending_email TEXT,
                verify_hash TEXT,
                verify_expires INTEGER,
                reset_hash TEXT,
                reset_expires INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS rp_enabled ON registered_players(enabled)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS rp_verified_email ON registered_players(email) WHERE email IS NOT NULL')

    def _db(self):
        return sqlite3.connect(str(self.path), timeout=5)

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    @staticmethod
    def _password_hash(password, salt):
        return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32,
                              maxmem=128*1024*1024).hex()

    @staticmethod
    def valid_name(name):
        return isinstance(name, str) and bool(re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{2,23}', name))

    @staticmethod
    def valid_password(password):
        return isinstance(password, str) and 12 <= len(password) <= 128 and not password.isspace() and '\x00' not in password

    @staticmethod
    def valid_email(email):
        return isinstance(email, str) and len(email) <= 254 and bool(re.fullmatch(
            r'[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', email))

    def registered_names(self):
        with self._db() as db:
            return [row[0] for row in db.execute('SELECT name FROM registered_players')]

    def count(self):
        with self._db() as db:
            return db.execute('SELECT COUNT(*) FROM registered_players WHERE enabled=1').fetchone()[0]

    def rows(self):
        with self._db() as db:
            return db.execute('SELECT name, enabled, created_at, email_verified FROM registered_players ORDER BY created_at DESC').fetchall()

    @staticmethod
    def fresh_tokens():
        return 'u.' + secrets.token_urlsafe(32), 'r.' + secrets.token_urlsafe(32)

    def register(self, name, password, reserved_names=()):
        if not self.valid_name(name):
            raise RegistrationError('Choose 3–24 characters: letters, numbers and underscores, starting with a letter.')
        if not self.valid_password(password):
            raise RegistrationError('Choose a password of 12–128 characters.')
        name = name.casefold()
        if name in {str(n).casefold() for n in reserved_names}:
            raise RegistrationError('This username is unavailable.')
        salt = secrets.token_bytes(16)
        encoded = self._password_hash(password, salt)
        token, recovery = self.fresh_tokens()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute('SELECT COUNT(*) FROM registered_players WHERE enabled=1').fetchone()[0]
            legacy_count = self.legacy.count() if self.legacy is not None else 0
            if active + legacy_count >= self.max_players:
                raise RegistrationError('Registration is currently full. Please check back later.')
            try:
                db.execute('''INSERT INTO registered_players(name,salt,password_hash,session_hash,session_until,recovery_hash,created_at)
                    VALUES(?,?,?,?,?,?,?)''', (name, salt.hex(), encoded, self._digest(token),
                    int(time.time()) + 90*86400,self._digest(recovery), int(time.time())))
            except sqlite3.IntegrityError:
                raise RegistrationError('This username is unavailable.') from None
        return name, token, recovery

    def authenticate(self, name, password):
        if not self.valid_name(name) or not isinstance(password, str) or len(password) > 128:
            return None
        with self._db() as db:
            row = db.execute('SELECT name,salt,password_hash FROM registered_players WHERE name=? AND enabled=1',
                             (name.casefold(),)).fetchone()
        # A dummy expensive hash reduces the difference between a known and unknown username.
        salt = bytes.fromhex(row[1]) if row else b'\x00'*16
        candidate = self._password_hash(password, salt)
        if not row or not hmac.compare_digest(candidate, row[2]):
            return None
        token = 'u.' + secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute('UPDATE registered_players SET session_hash=?, session_until=? WHERE name=? AND enabled=1',
                       (self._digest(token),int(time.time())+90*86400,row[0]))
        return token

    def lookup(self, token):
        if not isinstance(token, str) or not token.startswith('u.') or not 40 <= len(token) <= 100:
            return None
        with self._db() as db:
            row = db.execute('SELECT name FROM registered_players WHERE session_hash=? AND session_until>? AND enabled=1',
                             (self._digest(token),int(time.time()))).fetchone()
        return row[0].casefold() if row else None

    def invalidate(self, token):
        if isinstance(token, str) and token.startswith('u.'):
            with self._db() as db:
                db.execute('UPDATE registered_players SET session_hash=?,session_until=? WHERE session_hash=?',
                           (self._digest('u.'+secrets.token_urlsafe(32)),int(time.time()), self._digest(token)))

    def reset_with_code(self, name, recovery, password):
        if not self.valid_name(name) or not self.valid_password(password) or not isinstance(recovery, str):
            return None
        if not recovery.startswith('r.') or not 40 <= len(recovery) <= 100:
            return None
        salt = secrets.token_bytes(16)
        hashed = self._password_hash(password, salt)
        token, next_recovery = self.fresh_tokens()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT name FROM registered_players WHERE name=? AND recovery_hash=? AND enabled=1',
                             (name.casefold(), self._digest(recovery))).fetchone()
            if not row:
                return None
            db.execute('''UPDATE registered_players SET salt=?,password_hash=?,session_hash=?,session_until=?,recovery_hash=?,
                          reset_hash=NULL,reset_expires=NULL WHERE name=?''',
                       (salt.hex(),hashed,self._digest(token),int(time.time())+90*86400,self._digest(next_recovery),row[0]))
        return row[0], token, next_recovery

    def change_password(self, name, old, new):
        if not self.valid_name(name) or not self.valid_password(new):
            return None
        with self._db() as db:
            row = db.execute('SELECT salt,password_hash FROM registered_players WHERE name=? AND enabled=1',
                             (name.casefold(),)).fetchone()
        if not row or not hmac.compare_digest(self._password_hash(old,bytes.fromhex(row[0])),row[1]):
            return None
        salt = secrets.token_bytes(16)
        hashed = self._password_hash(new,salt)
        token, new_recovery = self.fresh_tokens()
        with self._db() as db:
            db.execute('''UPDATE registered_players SET salt=?,password_hash=?,session_hash=?,session_until=?,recovery_hash=?,
                          reset_hash=NULL,reset_expires=NULL WHERE name=? AND enabled=1''',
                       (salt.hex(),hashed,self._digest(token),int(time.time())+90*86400,self._digest(new_recovery),name.casefold()))
        return token, new_recovery

    def set_enabled(self,name,enabled):
        if not isinstance(name,str):
            return False
        with self._db() as db:
            row=db.execute('SELECT enabled FROM registered_players WHERE name=?',(name.casefold(),)).fetchone()
            if not row:
                return False
            if enabled and not row[0] and self.count() + (self.legacy.count() if self.legacy else 0)>=self.max_players:
                raise RegistrationError('Registration quota is full. Increase the quota or disable another account.')
            db.execute('UPDATE registered_players SET enabled=? WHERE name=?',(int(bool(enabled)),name.casefold()))
        return True

    def start_email_verification(self,name,email):
        if not self.valid_email(email):
            raise RegistrationError('Enter a valid email address.')
        email=email.strip().lower()
        token='v.'+secrets.token_urlsafe(32)
        with self._db() as db:
            row=db.execute('SELECT name FROM registered_players WHERE name=? AND enabled=1',(name.casefold(),)).fetchone()
            if not row:
                raise RegistrationError('Account unavailable.')
            db.execute('''UPDATE registered_players SET pending_email=?,verify_hash=?,verify_expires=? WHERE name=?''',
                       (email,self._digest(token),int(time.time())+86400,row[0]))
        return token

    def verify_email(self,token):
        if not isinstance(token,str) or not token.startswith('v.') or len(token)>100:
            return None
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT name,pending_email FROM registered_players WHERE verify_hash=? AND
                    verify_expires>? AND enabled=1''',(self._digest(token),int(time.time()))).fetchone()
            if not row:
                return None
            try:
                db.execute('''UPDATE registered_players SET email=?,email_verified=1,pending_email=NULL,
                    verify_hash=NULL,verify_expires=NULL WHERE name=?''',(row[1],row[0]))
            except sqlite3.IntegrityError:
                raise RegistrationError('This email address is already verified for another account.') from None
        return row

    def email_for(self,name):
        with self._db() as db:
            row=db.execute('SELECT email FROM registered_players WHERE name=? AND enabled=1 AND email_verified=1',
                           (name.casefold(),)).fetchone()
        return row[0] if row else None

    def start_email_reset(self,name):
        if not self.valid_name(name):
            return None
        token='p.'+secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT email FROM registered_players WHERE name=? AND enabled=1
                         AND email_verified=1 AND email IS NOT NULL''',(name.casefold(),)).fetchone()
            if not row:
                return None
            db.execute('UPDATE registered_players SET reset_hash=?,reset_expires=? WHERE name=?',
                       (self._digest(token),int(time.time())+30*60,name.casefold()))
        return row[0],token

    def reset_with_email_token(self,token,password):
        if not isinstance(token,str) or not token.startswith('p.') or len(token)>100 or not self.valid_password(password):
            return None
        salt=secrets.token_bytes(16)
        hashed=self._password_hash(password,salt)
        session,new_recovery=self.fresh_tokens()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT name,email FROM registered_players WHERE reset_hash=? AND
                      reset_expires>? AND enabled=1''',(self._digest(token),int(time.time()))).fetchone()
            if not row:
                return None
            db.execute('''UPDATE registered_players SET salt=?,password_hash=?,session_hash=?,session_until=?,recovery_hash=?,
                reset_hash=NULL,reset_expires=NULL WHERE name=?''',
                (salt.hex(),hashed,self._digest(session),int(time.time())+90*86400,self._digest(new_recovery),row[0]))
        return row[0],session,new_recovery,row[1]
