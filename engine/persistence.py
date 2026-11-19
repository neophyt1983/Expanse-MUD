# engine/persistence.py
import sqlite3
import json
from pathlib import Path
from engine.core import Entity

DB_PATH = Path(__file__).parent.parent / "save" / "world.db"

# Additive migrations preserve old columns and custom metadata.
PLAYER_COLUMNS = {
    'name': "TEXT DEFAULT ''", 'first_name': "TEXT DEFAULT ''",
    'last_name': "TEXT DEFAULT ''", 'race': 'TEXT', 'char_class': 'TEXT',
    'sex': 'TEXT', 'description': "TEXT DEFAULT ''",
    'hp': 'INT DEFAULT 30', 'max_hp': 'INT DEFAULT 30',
    'attack': 'INT DEFAULT 5', 'defense': 'INT DEFAULT 0', 'gold': 'INT DEFAULT 0',
    'inventory': "TEXT DEFAULT '[]'", 'equipped': "TEXT DEFAULT '{}'",
    'stats': "TEXT DEFAULT '{}'", 'abilities': "TEXT DEFAULT '[]'",
    'reputation': "TEXT DEFAULT '{}'", 'location': 'TEXT', 'group_id': 'TEXT',
    'game_mode': "TEXT DEFAULT 'single'", 'explored_rooms': "TEXT DEFAULT '[]'",
    'progress': "TEXT DEFAULT '{}'", 'saved_at': 'TEXT',
}
LEGACY_ALIASES = {'char_class': ('class', 'character_class')}
JSON_FIELDS = ('inventory', 'equipped', 'stats', 'abilities', 'reputation',
               'explored_rooms', 'progress')

def init_db(path=None, *, memory=False):
    database = Path(path) if path is not None else DB_PATH
    if memory:
        conn = sqlite3.connect(':memory:')
        if database.exists():
            source = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
            try: source.backup(conn)
            finally: source.close()
    else:
        database.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(database)
    try:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
        if columns and 'id' not in columns:
            raise RuntimeError('Unsupported save database: players has no id column. Save data was not changed.')
        missing = set(PLAYER_COLUMNS) - columns
        if columns and missing and not memory:
            # SQLite backup includes committed WAL data, unlike a plain file copy.
            import uuid
            backup = database.with_name(database.name + '.before-schema-' + uuid.uuid4().hex + '.bak')
            with sqlite3.connect(backup) as destination:
                conn.backup(destination)
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if not columns:
                definitions = ', '.join('"' + k + '" ' + v for k, v in PLAYER_COLUMNS.items())
                conn.execute('CREATE TABLE players (id TEXT PRIMARY KEY, ' + definitions + ')')
            else:
                # Re-read after acquiring the write lock in case another opener migrated.
                columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
                for name, definition in PLAYER_COLUMNS.items():
                    if name in columns:
                        continue
                    conn.execute('ALTER TABLE players ADD COLUMN "' + name + '" ' + definition)
                    for alias in LEGACY_ALIASES.get(name, ()):
                        if alias in columns:
                            conn.execute('UPDATE players SET "' + name + '" = "' + alias + '" WHERE "' + name + '" IS NULL')
            conn.execute("UPDATE players SET game_mode='single' WHERE game_mode IS NULL OR game_mode=''")
        return conn
    except Exception:
        conn.close()
        raise

def save_player(conn, entity, mode="single", commit=True, *, mark_saved=True):
    values = {name: getattr(entity, name) for name in PLAYER_COLUMNS if name not in ('game_mode', 'saved_at')}
    from datetime import datetime, timezone
    values.update(id=entity.id, game_mode=mode)
    if mark_saved:values['saved_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    for field in JSON_FIELDS:
        values[field] = json.dumps(values[field])
    columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
    for current, aliases in LEGACY_ALIASES.items():
        for alias in aliases:
            if alias in columns:
                values[alias] = values[current]
    # Update in place: INSERT OR REPLACE would erase unknown legacy columns.
    names = list(values)
    quoted = ['"' + name + '"' for name in names]
    assignments = ', '.join(q + '=?' for q in quoted if q != '"id"')
    updated = conn.execute('UPDATE players SET ' + assignments + ' WHERE id=?',
                           [values[n] for n in names if n != 'id'] + [entity.id])
    if not updated.rowcount:
        conn.execute('INSERT INTO players (' + ', '.join(quoted) + ') VALUES (' +
                     ', '.join('?' for _ in names) + ')', [values[n] for n in names])
    if commit:
        conn.commit()

def load_player(conn, player_id: str, mode="single"):
    cur = conn.execute("SELECT * FROM players WHERE id = ? AND game_mode = ?", (player_id, mode))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    data = dict(zip(cols, row))

    ent = Entity(
        id=data["id"], name=data["name"],
        first_name=data["first_name"], last_name=data["last_name"],
        race=data["race"], char_class=data["char_class"],
        sex=data["sex"], description=data["description"],
        hp=data["hp"], max_hp=data["max_hp"],
        attack=data["attack"], defense=data["defense"],
        gold=data["gold"], location=data["location"],
        group_id=data["group_id"], is_player=True
    )
    
    for field in ("inventory", "equipped", "stats", "abilities", "reputation", "explored_rooms", "progress"):
        val = data.get(field)
        if val:
            try:
                setattr(ent, field, json.loads(val))
            except json.JSONDecodeError:
                pass
    from engine import task_skills
    task_skills.validate_saved(ent.progress)
    return ent


def list_saves(conn, mode=None, world_slug=None):
    rows = conn.execute('SELECT id,name,race,char_class,location,progress,first_name,game_mode,saved_at FROM players ORDER BY saved_at DESC, name').fetchall()
    result=[]
    for pid,name,race,cls,location,raw,first,saved_mode,saved_at in rows:
        if mode is not None and saved_mode != mode: continue
        try: progress=json.loads(raw or '{}')
        except (ValueError,TypeError): continue
        if not isinstance(progress,dict): continue
        world=progress.get('world_slug','default')
        if world_slug is not None and world != world_slug: continue
        if name=='Adventurer' and not first: continue
        result.append(dict(id=pid,name=name,race=race,char_class=cls,location=location,
                           world=world,mode=saved_mode,saved_at=saved_at,
                           mode_label='Single-player' if saved_mode=='single' else 'Online (hosted)'))
    return result
