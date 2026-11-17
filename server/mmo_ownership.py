"""Fail-closed character ownership for a shared hosted Expanse civilization."""
from pathlib import Path
import sqlite3
import time

class MMOOwnership:
    def __init__(self, directory):
        self.path = Path(directory) / "mmo-ownership.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ownership (
                player_id TEXT PRIMARY KEY,
                account TEXT NOT NULL COLLATE NOCASE,
                claimed_at INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS owner_characters ON ownership(account)")

    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @staticmethod
    def _account(account):
        if not isinstance(account, str) or not 3 <= len(account) <= 61:
            raise ValueError("Invalid account.")
        return account.casefold()

    @staticmethod
    def _player(player_id):
        if not isinstance(player_id,str) or not 1 <= len(player_id) <= 150 or any(ord(c)<33 for c in player_id):
            raise ValueError("Invalid character identifier.")
        return player_id

    def claim(self, account, player_id):
        account, player_id = self._account(account), self._player(player_id)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO ownership(player_id,account,claimed_at) VALUES(?,?,?)",
                       (player_id,account,int(time.time())))
            row = db.execute("SELECT account FROM ownership WHERE player_id=?",(player_id,)).fetchone()
        if row[0] != account:
            raise PermissionError("This character belongs to another account.")
        return True

    def owns(self, account, player_id):
        try:
            account, player_id = self._account(account), self._player(player_id)
        except ValueError:
            return False
        with self._db() as db:
            row = db.execute("SELECT account FROM ownership WHERE player_id=?",(player_id,)).fetchone()
        return bool(row and row[0] == account)

    def characters(self, account):
        account = self._account(account)
        with self._db() as db:
            return {row[0] for row in db.execute("SELECT player_id FROM ownership WHERE account=?", (account,))}

    def release(self, account, player_id):
        account, player_id = self._account(account), self._player(player_id)
        with self._db() as db:
            result = db.execute("DELETE FROM ownership WHERE player_id=? AND account=?", (player_id,account))
            return result.rowcount == 1
