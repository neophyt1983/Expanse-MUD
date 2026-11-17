# engine/exchange.py
"""Export and import .expanse game bundles.

An .expanse file is a zip archive with this layout at the root:

    manifest.json    <- metadata about the bundle
    metadata.json    <- game metadata (name, start_room)
    rooms.json
    items.json
    npcs.json
    quests.json
    shortcuts.json

Whole-game bundles (kind="game") are the only supported kind in this
version. Content-only bundles (kind="content") are planned for a later
round.

Safety rules enforced on import:

  - all archive members must be flat filenames (no subdirectories)
  - no "../" or absolute paths
  - no duplicate entry names
  - manifest must exist, be valid JSON, and declare kind="game"
  - schema_version must be <= MANIFEST_SCHEMA_VERSION
  - slug in manifest must match ^[a-z][a-z0-9_]{0,31}$
  - extracted content must pass Editor.validate()
"""

import json
import re
import shutil
import stat
import os
import uuid
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


CONTENT_FILES = (
    "metadata.json",
    "pixel-art-library.json",
    "rooms.json",
    "items.json",
    "npcs.json",
    "quests.json",
    "buildings.json",
    "groups.json",
    "shortcuts.json",
    "races.json", "classes.json", "sexes.json", "abilities.json",
    "species.json", "population.json",
    "recipes.json", "resources.json", "encounters.json", "interactions.json",
)

MANIFEST_SCHEMA_VERSION = 8
HISTORY_FILES = ("history.json", "history-rules.json", "chronicles.json")
ENGINE_VERSION = "0.1.0"
MANIFEST_FILENAME = "manifest.json"
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_safe_flat_name(name: str) -> bool:
    if not name:
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    normalized = name.replace("\\", "/")
    if "/" in normalized:
        return False
    if normalized in (".", ".."):
        return False
    return True


def _count_entries(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return 0
        data = json.loads(text)
        return len(data) if isinstance(data, list) else 0
    except (json.JSONDecodeError, OSError):
        return 0


def export_game(slug: str, games_dir: Path, output_path: Path) -> Tuple[bool, str]:
    """Package games/<slug>/ into an .expanse zip at output_path."""
    if not isinstance(slug,str) or not SLUG_RE.fullmatch(slug):return False,'Export slug must use lowercase letters/digits/underscores, start with a letter, and be at most 32 characters'
    game_dir = Path(games_dir) / slug
    if not game_dir.is_dir():
        return False, f"game '{slug}' not found at {game_dir}"

    if Path(output_path).resolve().is_relative_to(game_dir.resolve()) or Path(os.path.abspath(output_path)).is_relative_to(Path(os.path.abspath(game_dir))):
        return False,'Export output must be outside the source game folder'
    from engine import history_templates
    try:
        template=history_templates.snapshot(game_dir)
        files=template['files']
        from editor.cli import FILE_MAP
        checked={kind:history_templates._json(files[name],name) if name in files else [] for kind,name in FILE_MAP.items()}
        with tempfile.TemporaryDirectory(prefix='expanse-export-check-') as tmp:
            for name,raw in files.items():
                target=Path(tmp,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            history_templates.validate_staged(tmp,checked,history_templates.extras(template))
        metadata=history_templates._json(files['metadata.json'],'metadata.json') if 'metadata.json' in files else {}
    except (ValueError,TypeError,OSError,KeyError) as exc:return False,'Invalid or unsupported template: '+str(exc)
    counts={name:len(checked[kind]) if isinstance(checked[kind],list) else 0 for name,kind in [('rooms','room'),('items','item'),('npcs','npc'),('quests','quest'),('buildings','building'),('groups','group')]}

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "kind": "game",
        "slug": slug,
        "name": metadata.get("name", slug),
        "start_room": metadata.get("start_room"),
        "created_at": _now_iso(),
        "counts": counts,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary=None;durability_note=''
    try:
        handle,temporary=tempfile.mkstemp(prefix='.'+output_path.name+'.tmp-',dir=output_path.parent)
        os.close(handle)
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2) + "\n")
            for fname in sorted((set(CONTENT_FILES) | set(files)) - {MANIFEST_FILENAME}):
                if fname in files:zf.writestr(fname, files[fname])
                else:
                    default = "{}" if fname in ("metadata.json", "shortcuts.json") else "[]"
                    if fname == "pixel-art-library.json":default=json.dumps({"version":1,"assets":{},"bindings":{}})
                    if fname == "population.json":default=json.dumps({"version":1,"cohorts":{},"households":{}})
                    zf.writestr(fname,default+"\n")
        with zipfile.ZipFile(temporary) as check:
            if check.testzip() is not None:raise OSError('Archive verification failed')
        with open(temporary,'rb') as stream:os.fsync(stream.fileno())
        os.replace(temporary,output_path)
        temporary=None
        try:
            fd=os.open(output_path.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
        except OSError as exc:durability_note=' Archive was written, but directory durability could not be confirmed: '+str(exc)
    except (OSError,ValueError,zipfile.BadZipFile,RuntimeError) as exc:
        return False,'Export failed; previous archive preserved: '+str(exc)
    finally:
        if temporary is not None:
            try:Path(temporary).unlink()
            except FileNotFoundError:pass

    return True, (
        f"Exported '{slug}' to {output_path} "
        f"({counts['rooms']} rooms, {counts['items']} items, "
        f"{counts['npcs']} npcs, {counts['quests']} quests, "
        f"{output_path.stat().st_size} bytes)"+durability_note
    )


def import_game(source_path: Path, games_dir: Path,
                force: bool = False, as_slug: Optional[str] = None
                ) -> Tuple[bool, str]:
    """Extract an .expanse zip into games/<slug>/."""
    source_path = Path(source_path)
    if not source_path.is_file():
        return False, f"file not found: {source_path}"

    try:
        zf = zipfile.ZipFile(source_path, "r")
    except zipfile.BadZipFile as e:
        return False, f"not a valid .expanse archive: {e}"

    with zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            return False, "archive contains duplicate entries"

        from engine import history_templates
        infos=zf.infolist()
        # Enforce every budget/name before decompressing even the manifest.
        if len(infos)>history_templates.MAX_FILES or sum(i.file_size for i in infos)>history_templates.MAX_TOTAL:
            return False,'Bundle size/count budget exceeded'
        for info in infos:
            member=info.filename
            if not _is_safe_flat_name(member):
                from engine.world_package import media
                if not media(member):return False,f'unsafe path in archive: {member!r}'
            if info.file_size>history_templates.MAX_FILE:return False,'Bundle member exceeds size limit'
            mode=stat.S_IFMT(info.external_attr>>16)
            if mode not in (0,stat.S_IFREG):return False,'Non-regular archive member refused'
            try:history_templates._allowed(member)
            except ValueError as exc:return False,'Unsupported archive entry: '+str(exc)

        try:
            manifest_data = zf.read(MANIFEST_FILENAME)
        except KeyError:
            return False, f"missing {MANIFEST_FILENAME} in archive"
        except (zipfile.BadZipFile,RuntimeError,OSError) as exc:return False,'Invalid manifest archive data: '+str(exc)

        try:
            manifest = history_templates._json(manifest_data,'manifest.json')
        except ValueError as e:
            return False, f"manifest.json is not valid JSON: {e}"
        if not isinstance(manifest,dict):return False,'manifest.json must be an object'

        schema = manifest.get("schema_version")
        if type(schema) is not int or not 1 <= schema <= MANIFEST_SCHEMA_VERSION:
            return False, (
                f"bundle schema version {schema!r} is newer than this game "
                f"supports ({MANIFEST_SCHEMA_VERSION})"
            )

        if manifest.get("kind") != "game":
            return False, (
                f"unsupported bundle kind: {manifest.get('kind')!r} "
                f"(this version only imports whole games)"
            )

        if not manifest.get("engine_version"):
            return False, "manifest missing engine_version"

        slug = as_slug if as_slug else manifest.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            return False, f"slug is invalid: {slug!r}"

        dest = Path(games_dir) / slug
        existing_signature=None;existing_identity=None
        if dest.is_symlink():return False,"Destination must not be a symlink"
        if dest.exists() and not force:
            return False, (
                f"game '{slug}' already exists at {dest} — "
                f"delete it, import with --force, or import as a "
                f"different slug"
            )

        from engine import history_templates
        if len(names)>history_templates.MAX_FILES or sum(i.file_size for i in zf.infolist())>history_templates.MAX_TOTAL:
            return False,'Bundle size/count budget exceeded'
        for name in HISTORY_FILES:
            if name in names:
                if zf.getinfo(name).file_size>history_templates.MAX_FILE:return False,'History sidecar exceeds size limit'
                try:
                    if not isinstance(history_templates._json(zf.read(name),name),dict):return False,'History sidecar must be an object'
                except (ValueError,OSError,zipfile.BadZipFile,RuntimeError) as exc:return False,'Invalid history sidecar: '+str(exc)
            existing=dest/name
            if existing.is_symlink():return False,'Existing history is a symlink; import under a new slug to preserve creator data'
            if existing.exists() and (name not in names or existing.read_bytes()!=zf.read(name)):
                return False,'Existing history differs; import under a new slug to preserve creator history'
        if dest.exists():
            try:
                current_template = history_templates.snapshot(dest)
                existing_signature = current_template['signature']
                for name in current_template['files']:
                    if name.startswith(('assets/', 'images/')) and name not in names:
                        return False, 'This update omits existing media; import a separate copy to preserve creator assets'
                del current_template
                existing_identity=(dest.stat().st_dev,dest.stat().st_ino)
            except (ValueError,OSError,TypeError) as exc:return False,'Existing template has unsupported data; import under a new slug to preserve it: '+str(exc)
        Path(games_dir).mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".expanse-import-",dir=games_dir) as tmp:
            tmp_path = Path(tmp)
            try:
                for member in names:
                    if member=='pixel-art-library.json' and zf.getinfo(member).file_size>8_000_000:return False,'Pixel art library exceeds 8 MB'
                    (tmp_path/member).parent.mkdir(parents=True,exist_ok=True)
                    with (tmp_path/member).open('xb') as stream:
                        stream.write(zf.read(member));stream.flush();os.fsync(stream.fileno())
                checked_template=history_templates.snapshot(tmp_path)
                from editor.cli import FILE_MAP
                checked_data={kind:history_templates._json(checked_template['files'][name],name) if name in checked_template['files'] else [] for kind,name in FILE_MAP.items()}
                if any(not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows) for rows in checked_data.values()):
                    return False,'Content tables must be lists of objects'
                history_templates.validate_staged(tmp_path,checked_data,history_templates.extras(checked_template))
            except (ValueError,TypeError,KeyError,OSError,zipfile.BadZipFile,RuntimeError) as exc:return False,'Invalid bundle content: '+str(exc)
            from engine.pixel_art import load as load_pixel_art
            try:
                incoming=load_pixel_art(tmp_path)
                if dest.exists():
                    current=load_pixel_art(dest)
                    if (dest/'pixel-art-library.json').exists() and ((tmp_path/'pixel-art-library.json').read_bytes() if (tmp_path/'pixel-art-library.json').exists() else None)!=(dest/'pixel-art-library.json').read_bytes():return False,'Existing pixel art differs; import under a new slug to preserve creator revisions'
            except (ValueError,TypeError,OSError) as exc:return False,f'Invalid pixel art library: {exc}'

            from editor.cli import Editor
            try:
                ed = Editor(tmp_path)
                report = ed.validate()
            except (ValueError, TypeError, KeyError) as exc:
                return False, f"bundle failed validation: {exc}"
            if not report.startswith("OK"):
                return False, f"bundle failed validation:\n{report}"

            backup=None;committed=False
            try:
                if hasattr(os, "O_DIRECTORY"):
                    fd=os.open(tmp_path,os.O_RDONLY | os.O_DIRECTORY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                # Never delete the existing world. Keep a sibling recovery copy
                # even after successful Force; failed commit restores it.
                if dest.is_symlink():return False,'Destination became a symlink; import refused'
                if dest.exists():
                    if not force:return False,'Destination appeared during import; choose a new slug'
                    if existing_signature is None or (dest.stat().st_dev,dest.stat().st_ino)!=existing_identity or history_templates.snapshot(dest)['signature']!=existing_signature:
                        return False,'Destination changed during import; original content preserved. Retry after reviewing it.'
                    backup=dest.with_name('.expanse-backup-'+slug+'-'+uuid.uuid4().hex)
                    os.rename(dest,backup)
                os.rename(tmp_path,dest);committed=True
                if hasattr(os, "O_DIRECTORY"):
                    fd=os.open(games_dir,os.O_RDONLY | os.O_DIRECTORY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
            except (OSError,ValueError) as exc:
                if committed:return False,'World was installed at '+str(dest)+' but directory durability could not be confirmed. Original backup: '+str(backup)+'. '+str(exc)
                if backup is not None and backup.exists():
                    if not dest.exists():
                        try:os.rename(backup,dest)
                        except OSError as rollback:return False,'Import commit failed; original world is preserved at '+str(backup)+': '+str(rollback)
                    else:return False,'Import commit failed; original world is preserved at '+str(backup)
                return False,'Import commit failed; existing world preserved: '+str(exc)
            backup_note=(' Backup retained at '+str(backup)+'.') if backup is not None else ''

    return True, (
        f"Imported '{slug}' ({manifest.get('name', slug)}) into {dest}"+backup_note
    )
