"""Restore a downloaded Expanse checkpoint into an unused save directory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing

from server.accounts import name_key


def restore(archive,world,dest):
    dest=Path(dest).resolve()
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise ValueError('Choose a new or empty save directory. Existing saves are preserved.')
    with zipfile.ZipFile(world) as foundation:
        slug=json.loads(foundation.read('manifest.json'))['slug']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',slug):
        raise ValueError('Invalid world identity.')
    with Path(world).open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    state='world_state_single.json' if slug=='default' else 'world_state_'+slug+'_single.json'
    allowed={'save/world.db','save/named-saves.sqlite3','save/'+state,'save/'+state+'.save-journal','WORLD.txt'}
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)-allowed or 'WORLD.txt' not in names:
            raise ValueError('Choose a manual save export.')
        if z.read('WORLD.txt').decode().splitlines()!=[slug,digest]:
            raise ValueError('This checkpoint belongs to a different .expanse file.')
        if ('save/named-saves.sqlite3' not in names and not {'save/world.db','save/'+state}<=set(names)):
            raise ValueError('The archive contains no complete checkpoint.')
        stage=Path(tmp)/'save'
        stage.mkdir()
        for name in set(names)-{'WORLD.txt'}:
            local=stage/Path(name).name
            with z.open(name) as src,local.open('xb') as out:
                shutil.copyfileobj(src,out)
            if local.suffix in ('.db','.sqlite3'):
                with closing(sqlite3.connect(local.as_uri()+'?mode=ro',uri=True)) as conn:
                    if conn.execute('PRAGMA quick_check').fetchone()!=('ok',):
                        raise ValueError('Invalid checkpoint database.')
            else:
                json.loads(local.read_bytes())
        stage.replace(dest)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('world',type=Path)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--save-dir',type=Path)
    group.add_argument('--web-data',type=Path)
    parser.add_argument('--character')
    args=parser.parse_args()
    if args.web_data:
        if not args.character:parser.error('--web-data needs --character')
        with args.world.open('rb') as f:
            game_id=hashlib.file_digest(f,'sha256').hexdigest()
        if not (args.web_data/'worlds'/game_id/'info.json').is_file():
            parser.error('Import this world into the web engine first.')
        args.save_dir=args.web_data/'players'/hashlib.sha256(name_key(args.character).encode()).hexdigest()/game_id
    try:
        restore(args.archive,args.world,args.save_dir)
    except (OSError,ValueError,KeyError,sqlite3.Error,zipfile.BadZipFile) as exc:
        parser.exit(1,str(exc)+'\n')
    print('Restored manual saves to',args.save_dir)
