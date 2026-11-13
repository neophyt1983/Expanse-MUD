"""Explicit fresh campaigns: authored-content snapshots, never copies of saves."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import threading
from functools import wraps
from datetime import datetime, timezone
from engine import history_templates, official_foundation

SLUG = re.compile(r'[A-Za-z0-9_-]{1,64}')
ID = re.compile(r'[0-9a-f]{32}')
MAX_ADVENTURES = 100

# Pending adventures exist only in this process. Their authored working copies
# live in a TemporaryDirectory, outside games/ and save/. They are not saves.
_PENDING = {}
_RETIRED = {}
_LOCK = threading.RLock()

def _locked(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        with _LOCK:return fn(*args,**kwargs)
    return call

def _key(save_root):
    return str(Path(save_root).resolve())

@_locked
def session_rows(save_root):
    return [v['row'] for (root, _), v in _PENDING.items() if root == _key(save_root)]

@_locked
def all_rows(save_root):
    return registry(save_root)['adventures'] + session_rows(save_root)

@_locked
def resolve_world_path(games_root, save_root, slug):
    if not isinstance(slug,str) or not SLUG.fullmatch(slug):
        raise ValueError('Invalid world identifier')
    pending = _PENDING.get((_key(save_root), slug))
    return pending['path'] if pending else Path(games_root)/slug

@_locked
def discard_pending(save_root, slug):
    pending = _PENDING.pop((_key(save_root), slug), None)
    if pending: pending['temporary'].cleanup()
    retired=_RETIRED.pop((_key(save_root),slug),None)
    if retired:retired.cleanup()

@_locked
def discard_all_pending(save_root):
    slugs={r['world'] for r in session_rows(save_root)} | {slug for root,slug in _RETIRED if root==_key(save_root)}
    for slug in slugs:discard_pending(save_root,slug)



@_locked
def registry(save_root):
    folder=Path(save_root)/'adventures'
    if folder.is_symlink():raise ValueError('Adventure registry directory must not be a symlink')
    path=folder/'registry.json'
    if not path.exists():return {'version':1,'adventures':[]}
    if path.is_symlink() or path.stat().st_size>1024*1024:raise ValueError('Invalid adventure registry; existing saves were not changed.')
    obj=json.loads(path.read_text())
    if not isinstance(obj,dict) or obj.get('version')!=1 or not isinstance(obj.get('adventures'),list):raise ValueError('Invalid adventure registry')
    seen=set()
    for row in obj['adventures']:
        if (not isinstance(row,dict) or not ID.fullmatch(str(row.get('id',''))) or row.get('world')!='adventure_'+row['id'] or row['id'] in seen or row.get('mode') not in ('single','host')):raise ValueError('Invalid adventure record')
        seen.add(row['id'])
    return obj


def _validate_storage(folder):
    if folder.parent.is_symlink() or folder.is_symlink():raise ValueError('Adventure directories must not be symlinks')
    for name in ('world.db','world.db-wal','world.db-shm','world_state.json','world_state.json.save-journal','publish-intent.json'):
        if (folder/name).is_symlink():raise ValueError('Adventure save files must not be symlinks')


def storage_dir(game_dir,save_root,games_root):
    path=Path(game_dir)
    # Only the registry owns namespaces. Imported game metadata cannot choose a DB.
    pending = _PENDING.get((_key(save_root), path.name))
    if pending and pending['path'].resolve()==path.resolve():
        folder=Path(save_root)/'adventures'/pending['row']['id']
        _validate_storage(folder)
        return folder
    if path.parent.resolve()!=Path(games_root).resolve():return None
    for row in registry(save_root)['adventures']:
        if row['world']==path.name:
            folder=Path(save_root)/'adventures'/row['id']
            if path.is_symlink() or folder.is_symlink():raise ValueError('Adventure directories must not be symlinks')
            for name in ('world.db','world.db-wal','world.db-shm','world_state.json','world_state.json.save-journal'):
                if (folder/name).is_symlink():raise ValueError('Adventure save files must not be symlinks')
            return folder
    if path.name.startswith("adventure_"):raise ValueError("Adventure registration is missing. Existing saves were not opened.")
    return None


@_locked
def catalog(games_root,save_root):
    recover_publications(games_root,save_root)
    root=Path(games_root);rows=all_rows(save_root);owned={r['world'] for r in rows}
    templates=[]
    for p in sorted(root.iterdir()):
        if p.name==official_foundation.TEMPLATE_ID or p.name in owned or p.name.startswith('adventure_') or p.is_symlink() or not p.is_dir() or not SLUG.fullmatch(p.name):continue
        if not (p/'metadata.json').is_file():continue
        try:meta=json.loads((p/'metadata.json').read_text())
        except (OSError,ValueError):continue
        templates.append({'id':p.name,'name':str(meta.get('name') or p.name)})
    return {'templates':templates,'adventures':[{k:r[k] for k in ('id','world','name','mode','template','created_at')} | {'saved':not ((_key(save_root),r['world']) in _PENDING)} for r in rows if resolve_world_path(root,save_root,r['world']).is_dir()]}


@_locked
def create(games_root,save_root,body):
    root=Path(games_root);template=body.get('template');name=body.get('name');mode=body.get('mode');request=body.get('request_id')
    if not isinstance(template,str) or not SLUG.fullmatch(template):raise ValueError('Choose a valid authored world')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('Name this adventure (1–80 characters)')
    if mode not in ('single','host'):raise ValueError('Choose Single player or Host')
    if not isinstance(request,str) or not ID.fullmatch(request):raise ValueError('Invalid creation request')
    is_official=template==official_foundation.TEMPLATE_ID
    source=official_foundation.directory(root) if is_official else root/template
    if source.is_symlink() or not source.is_dir():raise ValueError('Authored world is unavailable')
    obj=registry(save_root)
    request_hash=hashlib.sha256(json.dumps([template,name.strip(),mode]).encode()).hexdigest()
    for row in obj['adventures'] + session_rows(save_root):
        if row.get('request_id')==request:
            if row.get('request_hash')!=request_hash:raise ValueError('Creation request changed; start a new request')
            return row
    if len(obj['adventures']) + len(session_rows(save_root))>=MAX_ADVENTURES:raise ValueError('Adventure limit reached; existing adventures remain available')
    if template.startswith('adventure_') or template in {r['world'] for r in all_rows(save_root)}:raise ValueError('Choose an authored world, not another adventure')
    # Existing preservation contract rejects unknown files, state snapshots and symlinks.
    bundle=official_foundation.snapshot(root) if is_official else history_templates.snapshot(source)
    ident=uuid.uuid4().hex;slug='adventure_'+ident;destination=root/slug
    row={'id':ident,'world':slug,'name':name.strip(),'mode':mode,'template':template,'created_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'request_id':request,'request_hash':request_hash}
    if is_official:row['foundation_revision']=official_foundation.REVISION;row['foundation_signature']=bundle['source_signature']
    temporary=tempfile.TemporaryDirectory(prefix='expanse-unsaved-')
    pending=Path(temporary.name)/slug
    pending.mkdir()
    try:
        for d in bundle['directories']:(pending/d).mkdir(parents=True,exist_ok=True)
        for relative,raw in bundle['files'].items():
            p=pending/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        metadata=json.loads((pending/'metadata.json').read_text())
        metadata['name']=name.strip()
        if is_official:
            metadata['start_minute'] = 6 * 60 + 15
        (pending/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        from engine import founding_residents
        resident_seed=int(ident,16)
        founding_residents.apply(pending,founding_residents.make(pending,resident_seed))
        from editor.cli import Editor
        report=Editor(pending).validate()
        if not report.startswith('OK'):raise ValueError('Authored world needs correction before a fresh adventure: '+report)
        from engine import chronicles
        chronicles.create(pending,int(ident[:16],16))
        _PENDING[(_key(save_root),slug)]={'row':row,'path':pending,'temporary':temporary}
        return row
    except Exception:
        temporary.cleanup()
        raise


def _publication_paths(games_root, save_root, row):
    ident=row.get('id');slug=row.get('world')
    if not isinstance(ident,str) or not ID.fullmatch(ident) or slug!='adventure_'+ident:
        raise ValueError('Invalid pending publication')
    if row.get('mode') not in ('single','host'):raise ValueError('Invalid pending mode')
    destination=Path(games_root)/slug
    folder=Path(save_root)/'adventures'/ident
    if destination.is_symlink() or folder.is_symlink():raise ValueError('Symlink publication refused')
    _validate_storage(folder)
    return destination, folder


def _complete_publication(games_root,save_root,row,signature):
    """Finish only an already committed explicit Save, including after a crash."""
    destination,folder=_publication_paths(games_root,save_root,row)
    dbpath=folder/'world.db';statepath=folder/'world_state.json'
    for path in (dbpath,statepath,folder/'publish-intent.json'):
        if path.is_symlink():raise ValueError('Symlink publication refused')
    if not dbpath.exists():return False
    from engine.persistence import init_db
    from engine import save_transaction
    connection=init_db(dbpath)
    try:
        save_transaction.recover(connection,statepath)
        marker=connection.execute('SELECT generation FROM world_save_generations WHERE path=?',(str(statepath.resolve()),)).fetchone()
        if not marker or not statepath.exists():return False
        json.loads(statepath.read_text())
    finally:connection.close()
    if history_templates.snapshot(destination)['source_signature']!=signature:
        raise ValueError('Saved foundation changed during publication; original checkpoint preserved')
    obj=registry(save_root)
    if not any(r['id']==row['id'] for r in obj['adventures']):
        obj['adventures'].append(row)
        save_transaction.write_atomic(Path(save_root)/'adventures'/'registry.json',json.dumps(obj,indent=2)+'\n')
    (folder/'publish-intent.json').unlink(missing_ok=True)
    return True


@_locked
def recover_publications(games_root,save_root):
    folder=Path(save_root)/'adventures'
    if not folder.exists():return
    if folder.is_symlink():raise ValueError('Symlink registry refused')
    for child in folder.iterdir():
        if not ID.fullmatch(child.name) or not child.is_dir():continue
        if child.is_symlink():raise ValueError('Symlink publication refused')
        intent=child/'publish-intent.json'
        if not intent.exists():continue
        if intent.is_symlink() or intent.stat().st_size>16384:raise ValueError('Invalid publication intent')
        data=json.loads(intent.read_text())
        if not isinstance(data,dict) or set(data)!={'row','signature'} or data['row'].get('id')!=child.name:
            raise ValueError('Invalid publication intent')
        if _complete_publication(games_root,save_root,data['row'],data['signature']):
            finish_publish(save_root,data['row']['world'])



def _sync_directory(path):
    # POSIX directory fsync orders publication names after their file contents.
    # Windows has no O_DIRECTORY; file fsync still applies there.
    if hasattr(os, 'O_DIRECTORY'):
        fd=os.open(path,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


def _durable_tree(path):
    directories=[path]
    for child in path.rglob('*'):
        if child.is_dir():directories.append(child)
        else:
            with child.open('rb') as stream:os.fsync(stream.fileno())
    for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):
        _sync_directory(directory)


def _durable_mkdir(path):
    missing=[];current=path
    while not current.exists():missing.append(current);current=current.parent
    path.mkdir(parents=True,exist_ok=True)
    for directory in reversed(missing):
        _sync_directory(directory)
        _sync_directory(directory.parent)

@_locked
def publish_pending(games_root,save_root,slug,commit_save):
    """Publish a pending working world only during an explicit Save.

    A small intent makes an interrupted successful checkpoint discoverable on
    the next launch. Registration follows the paired DB/world transaction.
    """
    entry=_PENDING.get((_key(save_root),slug))
    if entry is None:
        commit_save()
        return resolve_world_path(games_root,save_root,slug)
    root=Path(games_root);destination,folder=_publication_paths(root,save_root,entry['row'])
    bundle=history_templates.snapshot(entry['path'])
    signature=bundle['source_signature']
    intent=folder/'publish-intent.json'
    from engine.save_transaction import write_atomic
    if destination.exists():
        if not intent.exists() or history_templates.snapshot(destination)['source_signature']!=signature:
            raise ValueError('Adventure destination already exists; refusing replacement')
    else:
        staging=Path(tempfile.mkdtemp(prefix='.save-adventure-',dir=root))
        try:
            for d in bundle['directories']:(staging/d).mkdir(parents=True,exist_ok=True)
            for name,raw in bundle['files'].items():
                path=staging/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            _durable_tree(staging)
            _durable_mkdir(folder)
            write_atomic(intent,json.dumps({'row':entry['row'],'signature':signature}))
            os.rename(staging,destination)
            _sync_directory(root)
        finally:
            if staging.exists():shutil.rmtree(staging)
    _durable_tree(destination)
    _sync_directory(root)
    commit_save()
    if not _complete_publication(root,save_root,entry['row'],signature):
        raise OSError('Explicit save did not commit; working session retained')
    return destination


@_locked
def finish_publish(save_root,slug):
    entry=_PENDING.pop((_key(save_root),slug),None)
    if entry:_RETIRED[(_key(save_root),slug)]=entry['temporary']


@_locked
def attach_pending(save_root, entry):
    _PENDING[(_key(save_root), entry['row']['world'])] = entry


def open_adventure(app,body):
    """Owner-only caller holds the launcher mode lock. Existing servers stop without saving after explicit switch confirmation."""
    ident=body.get('id');rows=all_rows(app.PROJECT_ROOT/'save')
    if ident=='legacy':
        slug=body.get('template');mode=body.get('mode')
        if not isinstance(slug,str) or not SLUG.fullmatch(slug) or mode not in ('single','host'):raise ValueError('Choose an authored world and mode')
        if slug in {r['world'] for r in rows}:raise ValueError('Choose this adventure from Continue adventure')
    else:
        row=next((r for r in rows if r['id']==ident),None)
        if row is None:raise ValueError('Adventure not found')
        slug,mode=row['world'],row['mode']
    target=resolve_world_path(app.GAMES_DIR,app.PROJECT_ROOT/'save',slug)
    if target.is_symlink() or not target.is_dir():raise ValueError('World is unavailable')
    from editor.cli import Editor
    if not Editor(target).validate().startswith('OK'):raise ValueError('World validation failed; current world remains running')
    old=app._game_server
    thread=getattr(app,'_ws_thread',None)
    if old is None and thread is not None and thread.is_alive() and (getattr(app,'RUNNING_GAME',None)!=slug or getattr(app,'_ws_start_mode',None)!=mode):raise ValueError('A world is still starting. Wait for startup to finish before switching adventures.')
    if old is not None:
        if Path(old.world.game_dir).resolve()==target.resolve() and old.mode==mode:
            if mode=='host':app.set_lan_http(True)
            app._set_mode(mode)
            return {'ok':True,'redirect':'/?host='+app._lan_ip() if mode=='host' else '/','world':slug}
        if old.clients:raise ValueError('Every player must return to Start (save first to keep progress) before changing adventures. The current world is still running.')
        if body.get('confirm_switch') is not True:raise ValueError('Confirm stopping the current world without saving before switching adventures')
        app.stop_game_server(require_empty=True)  # Atomic loop admission check; current progress is deliberately not saved.
    app.set_lan_http(False)
    app.engine_loader.set_game_dir(target);app._set_running_game(slug)
    if not app._start_ws_server('0.0.0.0' if mode=='host' else '127.0.0.1',mode):
        if getattr(app,'_ws_thread',None) is not None and app._ws_thread.is_alive() and not getattr(app,'_ws_error',None):return {'starting':True}
        raise ValueError('Could not start this adventure. Prior saves remain intact; choose Continue adventure to retry. '+app._startup_message(mode))
    if mode=='host':
        try:app.set_lan_http(True)
        except OSError:
            app.stop_game_server();raise
    app._set_mode(mode)
    return {'ok':True,'redirect':'/?host='+app._lan_ip() if mode=='host' else '/','world':slug}


def mode_for(game_dir,save_root,games_root):
    path=Path(game_dir)
    pending=_PENDING.get((_key(save_root),path.name))
    if pending and pending['path'].resolve()==path.resolve():return pending['row']['mode']
    if path.parent.resolve()!=Path(games_root).resolve():return None
    return next((r['mode'] for r in registry(save_root)['adventures'] if r['world']==path.name),None)
