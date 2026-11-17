"""Persistent, owner-assigned permissions for the shared Expanse world.

No new player is privileged. A role supplied by a browser is never authoritative.
"""
from __future__ import annotations
from pathlib import Path
from server.accounts import name_key
import re
import sqlite3
import time

NO_EDIT = "No_Edit"
ADMIN = "Admin"
FULL_EDIT = "Full_Edit"
ROLES = (NO_EDIT, ADMIN, FULL_EDIT)
VALID_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,23}\Z")


class MMORoles:
    def __init__(self, data_dir, owner):
        self.path = Path(data_dir) / "mmo-roles.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.owner = name_key(owner) if owner else ""
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS roles (
                account TEXT PRIMARY KEY COLLATE NOCASE,
                role TEXT NOT NULL CHECK(role IN ('No_Edit','Admin','Full_Edit')),
                changed_by TEXT NOT NULL,
                changed_at INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS role_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                previous_role TEXT NOT NULL,
                new_role TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                changed_at INTEGER NOT NULL
            )""")

    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @staticmethod
    def account_key(account):
        if not isinstance(account, str) or not VALID_NAME.fullmatch(account):
            raise ValueError("Invalid registered account name.")
        return account.casefold()

    def get(self, account):
        key = name_key(account)
        if self.owner and key == self.owner:
            return ADMIN
        with self._db() as db:
            row = db.execute("SELECT role FROM roles WHERE account=?", (key,)).fetchone()
        return row[0] if row and row[0] in ROLES else NO_EDIT

    def can_edit(self, account):
        return self.get(account) in (ADMIN, FULL_EDIT)

    def can_moderate(self, account):
        return self.get(account) == ADMIN

    def assign(self, actor, account, role, registered_accounts):
        who = name_key(actor)
        target = self.account_key(account)
        if not self.owner or who != self.owner:
            raise PermissionError("Only the Expanse owner assigns MMO classifications.")
        if target == self.owner:
            raise PermissionError("Owner permissions cannot be changed here.")
        if role not in ROLES:
            raise ValueError("Unknown classification.")
        known = {self.account_key(a) for a in registered_accounts}
        if target not in known:
            raise ValueError("Only registered player accounts may receive MMO privileges.")
        previous = self.get(target)
        if previous == role:
            return previous
        now = int(time.time())
        with self._db() as db:
            db.execute("INSERT INTO roles(account,role,changed_by,changed_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(account) DO UPDATE SET role=excluded.role,changed_by=excluded.changed_by,"
                       "changed_at=excluded.changed_at", (target,role,who,now))
            db.execute("INSERT INTO role_audit(account,previous_role,new_role,changed_by,changed_at) "
                       "VALUES(?,?,?,?,?)", (target,previous,role,who,now))
        return role

    def history(self, limit=100):
        with self._db() as db:
            return db.execute("SELECT account,previous_role,new_role,changed_by,changed_at "
                              "FROM role_audit ORDER BY id DESC LIMIT ?",(max(1,min(limit,500)),)).fetchall()
