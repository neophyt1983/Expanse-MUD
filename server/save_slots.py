"""Manual named checkpoints. Each slot update commits metadata, players and world together."""
import io
import json
import sqlite3
import tempfile
import uuid
import zipfile
import zlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from engine import history_templates, living, loader
from server import adventures

META = 'slot,revision,name,saved_at,world,world_name,mode,player,character,place'
DB = 'named-saves.sqlite3'


def _open(root, write=False):
    path = Path(root) / DB
    if path.is_symlink():
        raise ValueError('Invalid save catalogue path.')
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=20)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                slot TEXT PRIMARY KEY, revision TEXT NOT NULL, name TEXT NOT NULL, saved_at TEXT NOT NULL,
                world TEXT NOT NULL, world_name TEXT NOT NULL, mode TEXT NOT NULL, player TEXT NOT NULL,
                character TEXT NOT NULL, place TEXT NOT NULL, payload BLOB NOT NULL, foundation TEXT);
            CREATE TABLE IF NOT EXISTS foundations (digest TEXT PRIMARY KEY, archive BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS legacy_removed (slot TEXT PRIMARY KEY);
        """)
    else:
        conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def legacy_key(entry):
    return uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(
        ['expanse-save', entry['world'], entry['mode'], entry['id']])).hex


def catalogue(root, characters=(), player=None):
    path = Path(root)/DB
    slots, removed = [], set()
    if path.exists():
        with closing(_open(root)) as db:
            slots = [dict(r) for r in db.execute('SELECT '+META+' FROM slots')]
            removed = {r[0] for r in db.execute('SELECT slot FROM legacy_removed')}
    for entry in characters:
        key = legacy_key(entry)
        if key not in removed:
            slots.append({**entry, 'slot':key, 'legacy':True, 'player':entry['id'],
                          'character':entry['name'], 'place':entry['location'],
                          'revision':entry.get('saved_at') or 'undated'})
    return sorted((s for s in slots if player is None or s['player']==player),
                  key=lambda s:s.get('saved_at') or '', reverse=True)


def _check(db, ident, revision, player, owner, legacy):
    row = db.execute('SELECT revision,player FROM slots WHERE slot=?',(ident,)).fetchone()
    if not row and legacy and not db.execute('SELECT 1 FROM legacy_removed WHERE slot=?',(ident,)).fetchone():
        row = (legacy['revision'], legacy['player'])
    if not row or row[0] != revision:
        raise ValueError('This save changed or was deleted. Refresh the list and choose again.')
    if not owner and row[1] != player:
        raise ValueError('You can only change your own saves.')


def _prune(db):
    db.execute('DELETE FROM foundations WHERE NOT EXISTS (SELECT 1 FROM slots WHERE foundation=digest)')


def delete_many(root, entries, *, player, owner):
    with closing(_open(root, True)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        for entry in entries:
            _check(db,entry['slot'],entry['revision'],player,owner,entry if entry.get('legacy') else None)
            if entry.get('legacy'):
                # The legacy DB row also belongs to a live actor in a shared world.
                db.execute('INSERT INTO legacy_removed VALUES(?)',(entry['slot'],))
            db.execute('DELETE FROM slots WHERE slot=?',(entry['slot'],))
        _prune(db)


def lookup(root, packet, legacy_loader, player=None):
    ident=packet.get('slot')
    if not isinstance(ident,str) or not adventures.ID.fullmatch(ident):
        raise ValueError('Choose a save from the list.')
    if (Path(root)/DB).exists():
        with closing(_open(root)) as db:
            row=db.execute('SELECT '+META+' FROM slots WHERE slot=?',(ident,)).fetchone()
        if row:return resolve(root,[dict(row)],packet,player)
    return resolve(root,catalogue(root,legacy_loader()),packet,player)


def chosen(root, packet, legacy_loader, player=None):
    refs=packet.get('entries',[packet])
    if not isinstance(refs,list) or not refs or any(not isinstance(r,dict) for r in refs):
        raise ValueError('Select one or more saves.')
    if len({r.get('slot') for r in refs if isinstance(r.get('slot'),str)}) != len(refs):
        raise ValueError('Invalid save selection.')
    cached=None
    def legacy():
        nonlocal cached
        if cached is None:cached=legacy_loader()
        return cached
    return [lookup(root,ref,legacy,player) for ref in refs]


def world_data(world):
    from engine import resident_watch
    resident_watch.sample(world)
    return {'killed_npcs':list(world.killed_npcs), 'item_claims':world.item_claims,
            'shop_state':world.shop_state, 'living':living.snapshot(world)}


def player_rows(db, mode, slug):
    cursor = db.execute('SELECT * FROM players WHERE game_mode=?',(mode,))
    keys = [col[0] for col in cursor.description]
    for row in cursor:
        record = dict(zip(keys,row))
        if json.loads(record['progress'] or '{}').get('world_slug','default') == slug:
            yield record


def apply_players(db, records, mode, slug):
    columns = {r[1] for r in db.execute('PRAGMA table_info(players)')}
    with db:
        old = list(player_rows(db, mode, slug))
        db.executemany('DELETE FROM players WHERE id=?',[(p['id'],) for p in old])
        for r in records:
            keys = [k for k in r if k in columns]
            quoted = ','.join('"'+k.replace('"','""')+'"' for k in keys)
            db.execute('INSERT INTO players ('+quoted+') VALUES ('+','.join('?' for _ in keys)+')', [r[k] for k in keys])


def _pending_archive(server, root):
    slug = Path(server.world.game_dir).name
    row = next((r for r in adventures.session_rows(root) if r['world']==slug),None)
    if not row:
        return None,None,None
    # A large fresh foundation is identical across most consecutive saves.
    # Content edits replace or rewrite a file and invalidate this session cache.
    source=Path(server.world.game_dir)
    fingerprint=[]
    for path in sorted(source.rglob('*')):
        info=path.lstat()
        fingerprint.append((str(path.relative_to(source)),info.st_mode,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns))
    cached=getattr(server,'_slot_foundation',None)
    if cached and fingerprint==cached[0]:
        return row,cached[1],cached[2]
    bundle = history_templates.snapshot(source)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as out:
        for folder in bundle['directories']:
            out.writestr(folder+'/',b'')
        for name,data in bundle['files'].items():
            out.writestr(name,data)
    server._slot_foundation=(fingerprint,bundle['signature'],stream.getvalue())
    return row,server._slot_foundation[1],server._slot_foundation[2]


def write(server, root, player, name, *, entry=None, owner=False):
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Give this save a name of 1 to 80 characters.')
    actor = server.world.entities.get(player)
    server._stage_players_and_world()
    from engine.persistence import load_player
    actor = actor or load_player(server.db,player,server.mode)
    slug = Path(server.world.game_dir).name
    if not actor or not actor.is_player or actor.progress.get('world_slug','default')!=slug:
        raise ValueError('Enter the world with a character before saving.')
    room = server.world.rooms.get(actor.location)
    stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    players = list(player_rows(server.db,server.mode,slug))
    for p in players:
        p['saved_at'] = stamp
    row,digest,archive = _pending_archive(server,root)
    data = {'players':players,'world':world_data(server.world),'adventure':row}
    payload = zlib.compress(json.dumps(data,separators=(',',':')).encode(),1)
    ident = entry['slot'] if entry else uuid.uuid4().hex
    revision = uuid.uuid4().hex
    values = (ident,revision,name.strip(),stamp,slug,server.world.metadata.get('name') or slug,
              server.mode,player,actor.name,room.name if room else actor.location)
    with closing(_open(root,True)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if entry:
            _check(db,ident,entry['revision'],player,owner,entry if entry.get('legacy') else None)
            if entry.get('legacy'):
                db.execute('INSERT INTO legacy_removed VALUES(?)',(ident,))
        if digest:
            db.execute('INSERT OR IGNORE INTO foundations VALUES(?,?)',(digest,archive))
        db.execute('INSERT OR REPLACE INTO slots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(*values,payload,digest))
        _prune(db)
    return dict(zip(META.split(','),values))


def read(root, ident, revision):
    if not (Path(root)/DB).is_file():
        raise ValueError('This save no longer exists.')
    with closing(_open(root)) as db:
        row = db.execute('SELECT '+META+',payload,archive FROM slots LEFT JOIN foundations ON foundation=digest WHERE slot=? AND revision=?',(ident,revision)).fetchone()
        if not row:
            raise ValueError('This save changed or was deleted. Refresh the list.')
        meta={k:row[k] for k in META.split(',')}
        data=json.loads(zlib.decompress(row['payload']))
        from server.game_server import GameServer
        GameServer._validate_saved_world(data['world'])
        return meta,data,row['archive']


def prepare_source(games, root, meta, data, archive):
    """Prefer current authored content; reconstruct a never-published fresh world before switching."""
    source=Path(games)/meta['world']
    if source.is_symlink():
        raise ValueError('Invalid saved world path.')
    if source.is_dir():
        return source,None
    row=data.get('adventure')
    if not row or row['world']!=meta['world'] or not adventures.ID.fullmatch(row['id']) or row['world']!='adventure_'+row['id'] or archive is None:
        raise ValueError('The authored world for this save is unavailable.')
    temporary=tempfile.TemporaryDirectory(prefix='expanse-loaded-')
    path=Path(temporary.name)/row['world']
    path.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for item in bundle.infolist():
                relative=item.filename.rstrip('/')
                target=(path/relative).resolve()
                if path not in target.parents:
                    raise ValueError('Invalid saved world asset.')
                if item.is_dir():target.mkdir(parents=True,exist_ok=True)
                else:
                    history_templates._allowed(relative)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(bundle.read(item))
        return path,{'row':row,'path':path,'temporary':temporary}
    except Exception:
        temporary.cleanup()
        raise


def legacy_records(root, games):
    from engine import persistence
    entries=[]
    databases=[(Path(persistence.DB_PATH),None)]
    for row in adventures.registry(root)['adventures']:
        folder=Path(root)/'adventures'/row['id']
        adventures._validate_storage(folder)
        databases.append((folder/'world.db',row))
    for path,row in databases:
        if path.is_file():
            # A modern catalogue needs only the indexed database's player rows.
            # Older schemas still go through the existing in-memory migration.
            slug=row['world'] if row else None
            try:
                with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                    batch=persistence.list_saves(db,world_slug=slug)
            except sqlite3.OperationalError as exc:
                if 'no such column' not in str(exc) and 'no such table' not in str(exc):raise
                with closing(persistence.init_db(path,memory=True)) as db:
                    batch=persistence.list_saves(db,world_slug=slug)
            if row:
                for c in batch:
                    c.update(adventure_id=row['id'],world_name=row['name'])
            entries.extend(batch)
    return entries


def resolve(root, entries, packet, player=None):
    if not isinstance(packet.get('slot'),str) or not isinstance(packet.get('revision'),str):
        raise ValueError('Choose a save from the list.')
    entry=next((s for s in entries if s['slot']==packet['slot'] and s['revision']==packet['revision']),None)
    if not entry or (player is not None and entry['player']!=player):
        raise ValueError('This save is unavailable or has changed. Refresh the list.')
    return entry


async def handle(server, socket, player, packet):
    from server.game_server import SAVE_DIR
    owner=socket in server.host_sockets
    action=packet.get('action')
    try:
        if not player:raise ValueError('Enter the world with a character before managing saves.')
        allowed_player=None if owner else player
        def legacy():
            rows=legacy_records(SAVE_DIR,loader.GAMES_DIR)
            return rows if owner else [r for r in rows if r['world']==Path(server.world.game_dir).name and r['mode']==server.mode and r['id']==player]
        if action=='list':
            entries=catalogue(SAVE_DIR,legacy(),allowed_player)
            current=server.selected_slots.get(player,{}).get('slot')
            if not current:
                current=next((e['slot'] for e in entries if e.get('legacy') and e['player']==player and e['world']==Path(server.world.game_dir).name and e['mode']==server.mode),None)
            result={'slots':entries,'current':current}
        elif action in ('create','overwrite','delete'):
            entry=lookup(SAVE_DIR,packet,legacy,allowed_player) if action=='overwrite' else None
            if action=='delete':
                selection=chosen(SAVE_DIR,packet,legacy,allowed_player)
                delete_many(SAVE_DIR,selection,player=player,owner=owner)
                for deleted in selection:detach(server,deleted)
                result={'text':'Deleted “'+selection[0]['name']+'”.' if len(selection)==1 else f'Deleted {len(selection)} saves.'}
            else:
                saved=write(server,SAVE_DIR,player,entry['name'] if entry else packet.get('name'),entry=entry,owner=owner)
                server.selected_slots[player]=saved
                if owner:server.local_save_player=player
                server.detached_players.discard(player)
                result={'text':'Saved “'+saved['name']+'”.','saved_slot':saved['slot']}
        else:raise ValueError('Unknown save action.')
    except (ValueError,OSError,sqlite3.Error) as exc:
        result={'error':str(exc)}
    import json
    await socket.send(json.dumps({'type':'save_slots','request_id':packet.get('request_id'),**result}))


def visible_characters(root, characters):
    if not (Path(root)/DB).is_file():
        return characters
    with closing(_open(root)) as conn:
        hidden={r[0] for r in conn.execute('SELECT slot FROM legacy_removed')}
    return [p for p in characters if legacy_key(p) not in hidden]


def detach(server, entry):
    for pid,current in list(server.selected_slots.items()):
        if current['slot']==entry['slot']:
            server.selected_slots.pop(pid)
            server.detached_players.add(pid)
    if entry.get('legacy') and entry['world']==Path(server.world.game_dir).name and entry['mode']==server.mode:
        server.detached_players.add(entry['player'])


async def delete_from_title(server,root,entries):
    delete_many(root,entries,player=None,owner=True)
    for entry in entries:detach(server,entry)
