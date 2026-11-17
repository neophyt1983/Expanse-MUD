"""Durable passwordless guest identities for Expanse's public playtest.

The cookie is an unguessable bearer credential; store only its digest on disk.
A recovery code is shown once and can rotate the bearer cookie. Neither is
used as a gameplay autosave. The configured owner retains separate admin auth.
"""
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path


class GuestLimit(Exception):
    pass


class PublicGuests:
    def __init__(self, directory, max_players):
        self.path = Path(directory) / 'public-guests.sqlite3'
        self.max_players = max_players
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS public_guests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              cookie_hash TEXT NOT NULL UNIQUE,
              recovery_hash TEXT NOT NULL UNIQUE,
              enabled INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS public_guests_enabled ON public_guests(enabled)')

    def _db(self):
        return sqlite3.connect(str(self.path), timeout=5)

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def count(self):
        with self._db() as db:
            return db.execute('SELECT COUNT(*) FROM public_guests WHERE enabled=1').fetchone()[0]

    def rows(self):
        with self._db() as db:
            return db.execute('SELECT name, enabled, created_at FROM public_guests ORDER BY id').fetchall()

    def registered_names(self):
        with self._db() as db:
            return [row[0] for row in db.execute('SELECT name FROM public_guests')]

    def create(self, reserved_names):
        # BEGIN IMMEDIATE serializes the quota check with registration.
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute('SELECT COUNT(*) FROM public_guests WHERE enabled=1').fetchone()[0]
            if active >= self.max_players:
                raise GuestLimit('Public registration is full. Please try again after the owner opens more places.')
            next_id = db.execute('SELECT COALESCE(MAX(id),0)+1 FROM public_guests').fetchone()[0]
            # The suffix is never reused, even if older players were disabled.
            name = f'pretzel{next_id}'
            while name.casefold() in reserved_names:
                next_id += 1
                name = f'pretzel{next_id}'
            cookie = 'g.' + secrets.token_urlsafe(32)
            recovery = 'r.' + secrets.token_urlsafe(32)
            db.execute('INSERT INTO public_guests(name,cookie_hash,recovery_hash,enabled,created_at) VALUES(?,?,?,?,?)',
                       (name,self._digest(cookie),self._digest(recovery),1,int(time.time())))
            return name,cookie,recovery

    def lookup(self, cookie):
        if not isinstance(cookie, str) or not cookie.startswith('g.') or not 40 <= len(cookie) <= 100:
            return None
        with self._db() as db:
            row = db.execute('SELECT name FROM public_guests WHERE cookie_hash=? AND enabled=1',
                             (self._digest(cookie),)).fetchone()
            return row[0].casefold() if row else None

    def recover(self, recovery):
        if not isinstance(recovery, str) or not recovery.startswith('r.') or not 40 <= len(recovery) <= 100:
            return None
        new_cookie = 'g.' + secrets.token_urlsafe(32)
        with self._db() as db:
            row = db.execute('SELECT name FROM public_guests WHERE recovery_hash=? AND enabled=1',
                             (self._digest(recovery),)).fetchone()
            if not row:
                return None
            db.execute('UPDATE public_guests SET cookie_hash=? WHERE name=?',
                       (self._digest(new_cookie),row[0]))
            return row[0],new_cookie

    def invalidate(self, cookie):
        if isinstance(cookie, str) and cookie.startswith('g.'):
            with self._db() as db:
                # Rotating the stored digest invalidates an old browser token.
                db.execute('UPDATE public_guests SET cookie_hash=? WHERE cookie_hash=?',
                           (self._digest('g.'+secrets.token_urlsafe(32)), self._digest(cookie)))

    def set_enabled(self, name, enabled):
        if not isinstance(name, str):
            return False
        # Count and update in one write transaction.  The previous separate
        # connection allowed concurrent re-enables to exceed the player quota.
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT enabled FROM public_guests WHERE name=?',(name,)).fetchone()
            if not row:
                return False
            if enabled and not row[0]:
                active = db.execute('SELECT COUNT(*) FROM public_guests WHERE enabled=1').fetchone()[0]
                if active >= self.max_players:
                    raise GuestLimit('Public registration is full. Disable another account first or increase the quota.')
            db.execute('UPDATE public_guests SET enabled=? WHERE name=?',(int(bool(enabled)),name))
            return True
