"""Recoverable commit across SQLite player rows and the world JSON file.

The journal contains both complete JSON generations. A marker committed in the
same SQLite transaction as the players selects the generation after a crash.
Never overwrite or discard an unreadable journal: recovery must stop instead.
"""
import json
import os
import uuid
import sqlite3
from pathlib import Path


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    if hasattr(os, "O_DIRECTORY"):
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)


def recover(db, path):
    path = Path(path)
    db.execute('CREATE TABLE IF NOT EXISTS world_save_generations (path TEXT PRIMARY KEY, generation TEXT NOT NULL)')
    journal = path.with_name(path.name + '.save-journal')
    if not journal.exists():
        return
    data = json.loads(journal.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'generation', 'before', 'after'} or not isinstance(data['generation'], str) or data['after'] is not None and not isinstance(data['after'], str) or data['before'] is not None and not isinstance(data['before'], str):
        raise ValueError('Invalid world save recovery journal; original files preserved.')
    row = db.execute('SELECT generation FROM world_save_generations WHERE generation=?', (data['generation'],)).fetchone()
    chosen = data['after'] if row and row[0] == data['generation'] else data['before']
    if chosen is None:
        path.unlink(missing_ok=True)
    else:
        json.loads(chosen)  # Do not install invalid recovery data.
        write_atomic(path, chosen)
    journal.unlink()


def commit(db, path, data):
    """Commit any pending player writes together with this world generation."""
    _commit_text(db, path, json.dumps(data, separators=(',', ':')))


def restore_checkpoint(db, checkpoint, path, state_bytes):
    """Discard to a whole SQLite checkpoint and JSON generation recoverably."""
    copy=sqlite3.connect(':memory:')
    try:
        checkpoint.backup(copy)
        _commit_text(db, path, state_bytes.decode('utf-8') if state_bytes is not None else None, checkpoint=copy)
    finally:copy.close()


def _commit_text(db, path, after, checkpoint=None):
    path = Path(path)
    journal = path.with_name(path.name + '.save-journal')
    # Recovery runs before mutation at server startup. A leftover successful
    # journal must be retired before starting another transaction.
    if journal.exists():
        recover(db, path)
    before = path.read_text(encoding='utf-8') if path.exists() else None
    generation = uuid.uuid4().hex
    try:
        write_atomic(journal, json.dumps(dict(generation=generation, before=before, after=after)))
        target=checkpoint if checkpoint is not None else db
        target.execute('CREATE TABLE IF NOT EXISTS world_save_generations (path TEXT PRIMARY KEY, generation TEXT NOT NULL)')
        target.execute('INSERT OR REPLACE INTO world_save_generations(path,generation) VALUES (?,?)', (str(path.resolve()), generation))
        if after is None:path.unlink(missing_ok=True)
        else:write_atomic(path, after)
        if checkpoint is not None:
            checkpoint.commit()
            checkpoint.backup(db)
        else:db.commit()
    except Exception:
        db.rollback()
        # Restore the old generation. If recovery itself fails, leave the
        # journal intact so the next startup cannot silently load mixed data.
        if journal.exists():
            recover(db, path)
        raise
    try:
        journal.unlink()
    except OSError:
        pass  # Commit succeeded; startup/next save will finalize its journal.
