"""Register the signed-in gateway's immutable packaged world without spending player-disk space."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from zipfile import ZipFile

PARTS = tuple(Path(__file__).resolve().parents[1] / 'bundled-worlds' /
              ('Wild-Lands-Founding-Cities-1.10.0.expanse.part' + str(n)) for n in (1, 2))
DIGEST = '85a89a2f94017bcf988803fbc29d18a79b0b441abf35a0281ca42004a492ec72'
SLUG = 'wild_lands_genesis_1100'


def validate_import(archive, stage):
    """Use the normal template importer and write its catalogue entry in the staging area."""
    from engine.exchange import import_game
    ok, note = import_game(archive, stage / 'games')
    if not ok:
        raise ValueError(note)
    game = next(path for path in (stage / 'games').iterdir() if not path.name.startswith('.'))
    meta = json.loads((game / 'metadata.json').read_bytes())
    info = {'slug': game.name, 'name': meta.get('name') or game.name}
    (stage / 'info.json').write_text(json.dumps(info), encoding='utf-8')
    return info


def matches(bundle, source, slug):
    """Compare an existing import to every archived member before sharing it with workers."""
    try:
        if bundle.is_symlink() or not bundle.is_dir():
            return False
        info = bundle / 'info.json'
        game = bundle / 'games' / slug
        if (info.is_symlink() or (bundle / 'games').is_symlink() or game.is_symlink()
                or json.loads(info.read_bytes()).get('slug') != slug):
            return False
        with ZipFile(source) as archive:
            entries = archive.infolist()
            members = set()
            for path in game.rglob('*'):
                if path.is_symlink():
                    return False
                if path.is_file():
                    members.add(path.relative_to(game).as_posix())
            if members != {entry.filename for entry in entries}:
                return False
            for entry in entries:
                path = game / entry.filename
                if path.stat().st_size != entry.file_size:
                    return False
                with archive.open(entry) as original, path.open('rb') as stored:
                    while chunk := original.read(1024 * 1024):
                        if stored.read(len(chunk)) != chunk:
                            return False
        return True
    except (OSError, ValueError, AttributeError):
        return False


def verified_bundle(bundle, digest, slug):
    archive = bundle / 'world.expanse'
    if archive.is_symlink() or not archive.is_file():
        return False
    with archive.open('rb') as stream:
        valid = hashlib.file_digest(stream, 'sha256').hexdigest() == digest
    return valid and matches(bundle, archive, slug)


def prepare(worlds, cache, parts=PARTS, digest=DIGEST, slug=SLUG):
    """Reuse a valid owner import, otherwise atomically build an application-cache copy."""
    existing = worlds / digest
    if verified_bundle(existing, digest, slug):
        return existing

    cache.mkdir(mode=0o700, exist_ok=True, parents=True)
    target = cache / digest
    # Serialize cold starts and interrupted-build recovery across gateway processes.
    with closing(sqlite3.connect(cache / 'prepare.sqlite3', timeout=180)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        if verified_bundle(target, digest, slug):
            return target
        stage = cache / ('.building-' + digest)
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(mode=0o700)
        try:
            archive = stage / 'world.expanse'
            assembled = hashlib.sha256()
            with archive.open('xb') as out:
                for part in parts:
                    with part.open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            out.write(chunk)
                            assembled.update(chunk)
            if assembled.hexdigest() != digest:
                raise ValueError('The packaged Founding Cities archive failed verification.')
            info = validate_import(archive, stage)
            if info['slug'] != slug or not matches(stage, archive, slug):
                raise ValueError('The imported package differs from the released Founding Cities world.')
            if target.exists():
                # Only this private cache is replaceable. Owner imports and player data live elsewhere.
                shutil.rmtree(target)
            stage.rename(target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return target


def cache_path():
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'expanse' / 'bundled-worlds'
