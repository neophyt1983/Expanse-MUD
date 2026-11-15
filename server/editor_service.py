"""Owner Creator workspace over a persistent copy of one imported world.

HTTP authentication belongs to render_server. This module receives no live game,
player, save directory, worker or caller-selected filesystem path. Existing
Creator tools and portable-file editing share the same isolated draft directory.
"""
import base64
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import tempfile
import threading
from urllib.parse import urlencode

from editor.cli import Editor, FILE_MAP
from engine import exchange, history_templates
from engine.world_package import CONTENT_TYPES
from server.editor_specials import SpecializedEditors

SLUG = re.compile(r'[a-z][a-z0-9_]{0,31}')
FILE_TYPES = {name: kind for kind, name in FILE_MAP.items()}
MAX_MEDIA = 32 * 1024 * 1024


class EditorError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@dataclass
class Reply:
    data: object = None
    status: int = 200
    path: Path = None
    mime: str = None
    download: str = None


class Handler(SpecializedEditors):
    def __init__(self, app, headers):
        self.app = app
        self.headers = headers
        self.reply = None

    def _json(self, value, status=200):
        self.reply = Reply(value, status)
        return self.reply

    def _local_owner(self):
        # The enclosing Render route checks the authenticated owner identity.
        # No Host/IP/header credential is interpreted as authorization here.
        return True


class EditorService:
    def __init__(self, directory, source, bundle_id):
        self.directory = Path(directory)
        self.source = Path(source)
        self.bundle_id = bundle_id
        self.slug = self.source.name
        if not SLUG.fullmatch(self.slug):
            raise EditorError('Invalid imported world name.')
        self.GAMES_DIR = self.directory / 'games'
        self._editors = {}
        self._editors_lock = threading.RLock()
        self._population_previews = {}
        self._history_previews = {}
        self._initialize()

    def _initialize(self):
        """Copy checked authored bytes once; never rewrite the import."""
        if self.directory.is_symlink():
            raise EditorError('Draft folder must not be a symbolic link.')
        if self.directory.exists():
            descriptor = json.loads((self.directory / 'draft.json').read_bytes())
            if descriptor != {'bundle': self.bundle_id, 'slug': self.slug}:
                raise EditorError('Draft identity does not match the imported world.')
            self._root(self.slug)
            return
        template = history_templates.snapshot(self.source)
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.draft-', dir=self.directory.parent))
        try:
            root = temporary / 'games' / self.slug
            root.mkdir(parents=True)
            for name in template['directories']:
                (root / name).mkdir(parents=True, exist_ok=True)
            for name, raw in template['files'].items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            (temporary / 'draft.json').write_text(json.dumps({'bundle': self.bundle_id, 'slug': self.slug}) + '\n')
            os.replace(temporary, self.directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _root(self, slug):
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise EditorError('Invalid draft world.', 404)
        root = self.GAMES_DIR / slug
        if self.GAMES_DIR.is_symlink() or root.is_symlink() or not root.is_dir() or root.resolve().parent != self.GAMES_DIR.resolve():
            raise EditorError('Unknown draft world.', 404)
        return root

    @staticmethod
    def _json(raw, name):
        return history_templates._json(raw, name)

    @staticmethod
    def _check_records(name, raw):
        history_templates._validate_file(name, raw)
        if not name.endswith('.json') and len(raw) > MAX_MEDIA:
            raise EditorError('World media must be at most 32 MiB so the game can serve it.')
        if name in FILE_TYPES:
            rows = history_templates._json(raw, name)
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] for row in rows):
                raise EditorError(name + ' must be an array of records with nonempty text IDs.')
            if len({row['id'] for row in rows}) != len(rows):
                raise EditorError(name + ' contains duplicate record IDs.')

    def get_editor(self, slug):
        with self._editors_lock:
            root = self._root(slug)
            if slug not in self._editors:
                template = history_templates.snapshot(root)
                for name, raw in template['files'].items():
                    if name in FILE_TYPES:
                        self._check_records(name, raw)
                self._editors[slug] = Editor(root)
            return self._editors[slug]

    def games(self):
        rows = []
        for root in sorted(self.GAMES_DIR.iterdir()):
            if not root.is_dir() or not SLUG.fullmatch(root.name):
                continue
            root = self._root(root.name)
            meta = self._json((root / 'metadata.json').read_bytes(), 'metadata.json')
            image = next((name for name in ('images/title.png', 'images/title.jpg', 'images/title.jpeg', 'images/title.webp') if (root / name).is_file()), None)
            rows.append({'slug': root.name, 'name': meta.get('name') or root.name,
                         'image_url': self.url(root.name, 'file-download', name=image) if image else None})
        return {'games': rows, 'running_game': self.slug, 'draft_only': True}

    def url(self, slug, action, **query):
        return '/api/editor/games/' + slug + '/' + action + '?' + urlencode({'editor_game': self.bundle_id, **query})

    def _path(self, slug, name):
        if not isinstance(name, str):
            raise EditorError('Choose a world file.')
        history_templates._allowed(name)
        root = self._root(slug)
        path = root / name
        if any(part.is_symlink() for part in (path, *path.parents) if part == root or root in part.parents):
            raise EditorError('Symbolic links are not world content.')
        if not path.resolve().is_relative_to(root.resolve()):
            raise EditorError('Invalid world file path.')
        return path

    def _read(self, slug, name, missing=False):
        path = self._path(slug, name)
        if not path.exists() and missing:
            return b''
        if not path.is_file():
            raise EditorError('World file not found.', 404)
        with path.open('rb') as stream:
            raw = stream.read(history_templates.MAX_FILE + 1)
        if len(raw) > history_templates.MAX_FILE:
            raise EditorError('World file exceeds the portable file size limit.')
        return raw

    def _pending(self, slug):
        ed = self._editors.get(slug)
        return sorted({FILE_MAP[kind] for kind in ed.dirty} |
                      ({'population.json'} if getattr(ed, 'population_manifest_dirty', False) else set())) if ed else []

    def _save(self, slug):
        ed = self.get_editor(slug)
        payloads = {FILE_MAP[kind]: ed.data[kind] for kind in ed.dirty}
        if getattr(ed, 'population_manifest_dirty', False):
            payloads['population.json'] = ed.population_manifest
        # Large shipped room arrays fit the portable format as compact JSON.
        # Pretty-printing them can exceed its per-file size limit on first Save.
        encoded = {name: (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode()
                   for name, value in payloads.items()}
        for name, raw in encoded.items():
            self._check_records(name, raw)
        if payloads:
            template = history_templates.snapshot(ed.data_dir)
            history_templates.signature({**template['files'], **encoded}, template['directories'])
            self._atomic_files(ed.data_dir, encoded)
            ed.dirty.clear()
            ed.population_manifest_dirty = False
        return 'Draft saved. Export the .expanse file to use this version.' if payloads else 'Draft is already saved.'

    @staticmethod
    def _atomic_files(root, payloads):
        """Stage bytes, retain originals and roll back a failed replacement."""
        prepared, backups, replaced = {}, {}, []
        try:
            for name, raw in payloads.items():
                target = root / name
                if target.is_symlink():
                    raise EditorError('Cannot replace a symbolic link.')
                for label, value in (('stage', raw), ('rollback', target.read_bytes() if target.exists() else None)):
                    collection = prepared if label == 'stage' else backups
                    if value is None:
                        collection[name] = None
                        continue
                    fd, temporary = tempfile.mkstemp(prefix='.' + name + '.' + label + '-', dir=root)
                    collection[name] = Path(temporary)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(value); stream.flush(); os.fsync(stream.fileno())
            for name, temporary in prepared.items():
                os.replace(temporary, root / name); replaced.append(name)
        except Exception as original:
            failures = []
            for name in reversed(replaced):
                try:
                    if backups[name] is None:
                        (root / name).unlink(missing_ok=True)
                    else:
                        os.replace(backups[name], root / name)
                except OSError as exc:
                    failures.append(str(backups[name]) + ': ' + str(exc))
            if failures:
                raise OSError('Draft write failed; recovery backups retained: ' + '; '.join(failures)) from original
            raise
        finally:
            for temporary in [*prepared.values(), *backups.values()]:
                if temporary is not None:
                    if 'failures' in locals() and failures and temporary in backups.values():
                        continue
                    temporary.unlink(missing_ok=True)

    def _write_bytes(self, slug, name, raw, revision):
        if name == 'manifest.json':
            raise EditorError('The export manifest is generated from the draft.')
        if name in self._pending(slug):
            raise EditorError('Save or revert the staged record edits before replacing this file.', 409)
        current = self._read(slug, name, missing=True)
        if revision != hashlib.sha256(current).hexdigest():
            raise EditorError('This file changed after you opened it. Reload and review your edits.', 409)
        self._check_records(name, raw)
        root = self._root(slug)
        template = history_templates.snapshot(root)
        candidate = {**template['files'], name: raw}
        history_templates.signature(candidate, template['directories'])
        path = self._path(slug, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.creator-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(raw); out.flush(); os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        ed = self._editors.get(slug)
        if ed and name in FILE_TYPES:
            ed.data[FILE_TYPES[name]] = self._json(raw, name)
        if ed and name == 'population.json':
            ed.population_manifest = self._json(raw, name)
        return {'ok': True, 'revision': hashlib.sha256(raw).hexdigest(),
                'text': 'Saved ' + name + ' in the draft. Export when ready.'}

    def _file_action(self, slug, action, body, query):
        name = body.get('name') if body is not None else query.get('name')
        if action == 'files' and body is None:
            template = history_templates.snapshot(self._root(slug))
            return Reply({'files': [{'name': name, 'size': len(raw), 'revision': hashlib.sha256(raw).hexdigest(),
                                    'json': name.endswith('.json'), 'readonly': name == 'manifest.json'}
                                   for name, raw in sorted(template['files'].items())],
                          'pending': self._pending(slug), 'max_file_bytes': history_templates.MAX_FILE, 'max_media_bytes': MAX_MEDIA,
                          'supported_json': sorted(set(FILE_MAP.values()) | {'metadata.json'} | history_templates.JSON_SIDECARS | history_templates.DERIVED)})
        if action == 'file' and body is None:
            raw = self._read(slug, name, missing=True)
            result = {'name': name, 'revision': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                      'exists': self._path(slug, name).exists(), 'readonly': name == 'manifest.json',
                      'pending': name in self._pending(slug), 'download_url': self.url(slug, 'file-download', name=name)}
            if name.endswith('.json'):
                result['text'] = raw.decode('utf-8')
            return Reply(result)
        if action in ('file-download', 'art') and body is None:
            self._read(slug, name)
            mime = CONTENT_TYPES.get(PurePosixPath(name).suffix.lower(), 'application/octet-stream')
            return Reply(path=self._path(slug, name), mime=mime,
                         download=PurePosixPath(name).name if action == 'file-download' else None)
        if action in ('file', 'file-upload') and body is not None:
            if action == 'file':
                if not isinstance(body.get('text'), str) or not isinstance(name, str) or not name.endswith('.json'):
                    raise EditorError('Send JSON file contents as text.')
                raw = body['text'].encode('utf-8')
            else:
                data = body.get('data')
                if not isinstance(data, str) or len(data) > (history_templates.MAX_FILE + 2) * 4 // 3 + 256:
                    raise EditorError('Choose a supported file within the portable size limit.')
                raw = base64.b64decode(data.split(',', 1)[-1], validate=True)
            return Reply(self._write_bytes(slug, name, raw, body.get('revision')))
        if action == 'file-delete' and body is not None:
            if name in ('metadata.json', 'rooms.json', 'manifest.json'):
                raise EditorError('Keep the world metadata, room list and generated manifest. Edit their content instead.')
            if name in self._pending(slug):
                raise EditorError('Save or revert staged record edits first.', 409)
            raw = self._read(slug, name)
            if body.get('revision') != hashlib.sha256(raw).hexdigest():
                raise EditorError('This file changed. Reload before deleting it.', 409)
            self._path(slug, name).unlink()
            ed = self._editors.get(slug)
            if ed and name in FILE_TYPES:
                ed.data[FILE_TYPES[name]] = []
            if ed and name == 'population.json':
                ed.population_manifest = {'version': 1, 'cohorts': {}, 'households': {}}
            return Reply({'ok': True, 'text': 'Removed ' + name + ' from the draft.'})
        raise EditorError('Unknown world file action.', 404)

    def _special(self, slug, action, body, headers):
        handler = Handler(self, headers)
        if action in ('geology', 'regional_weather', 'population'):
            getattr(handler, '_editor_' + action)(slug, body)
        elif action == 'pixel-art':
            from engine.pixel_art import load, change
            handler._json(load(self._root(slug)) if body is None else change(self._root(slug), body))
        else:
            if action == 'history':
                from server import history_editor as module
            elif action == 'soundtrack':
                from server import music_editor as module
            else:
                from server import tax_editor as module
            module.handle(handler, slug, body, self)
        return handler.reply or Reply({'error': 'Creator tool returned no result.'}, 500)

    def _metadata(self, slug):
        return self._json(self._read(slug, 'metadata.json'), 'metadata.json')

    def _rules(self, slug, body):
        meta = self._metadata(slug)
        from engine import worldtime, progression
        if body is None:
            return {'player_death': meta.get('player_death', 'revival'), 'max_players': meta.get('max_players', 128),
                    'pvp': meta.get('pvp', True), 'sunrise_minute': meta.get('sunrise_minute', 375),
                    'start_minute': worldtime.initial_minute(meta), 'start_at_dawn': 'start_minute' not in meta,
                    'progression': {'enabled': bool(meta.get('living_world', False)), **meta.get('progression', {})}}
        mode, cap = body.get('player_death', meta.get('player_death', 'revival')), body.get('max_players', meta.get('max_players', 128))
        if mode not in ('revival', 'permanent') or type(cap) is not int or not 1 <= cap <= 128:
            raise EditorError('Choose revival or permanent death, and 1–128 players.')
        pvp = body.get('pvp', meta.get('pvp', True))
        sunrise = body.get('sunrise_minute', meta.get('sunrise_minute', 375))
        start = body.get('start_minute', meta.get('start_minute'))
        if type(pvp) is not bool or type(sunrise) is not int or not 0 <= sunrise < 1500 or (start is not None and (type(start) is not int or not 0 <= start < 1500)):
            raise EditorError('Use valid combat settings and minutes from 00:00 to 24:59.')
        advancement = body.get('progression', meta.get('progression', {}))
        issues = progression.validate_config(advancement)
        if issues:
            raise EditorError('; '.join(issues))
        meta.update(player_death=mode, max_players=cap, pvp=pvp, sunrise_minute=sunrise, progression=advancement)
        if 'start_minute' in body:
            if start is None:
                meta.pop('start_minute', None)
            else:
                meta['start_minute'] = start
        self._write_metadata(slug, meta)
        return {'ok': True, 'text': 'World rules saved in the draft. Export when ready.'}

    def _write_metadata(self, slug, meta):
        raw = self._read(slug, 'metadata.json')
        return self._write_bytes(slug, 'metadata.json', (json.dumps(meta, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode(), hashlib.sha256(raw).hexdigest())

    def _map(self, slug, action, query):
        ed = self.get_editor(slug)
        memberships = {}
        for building in ed.data.get('building', []):
            for rid in building.get('rooms', []):
                memberships.setdefault(rid, {'id': building['id'], 'name': building.get('name', building['id'])})
        rooms = [dict(room, _visual_building=memberships.get(room['id'], {})) for room in ed.data['room']]
        from engine.coordinates import survey_editor
        survey_editor(rooms, ed.data_dir)
        if action == 'map':
            from engine.mapping import render
            return render(rooms, query.get('room', ''), designer=True)
        from engine.mapping import compile_map
        from engine.world_atlas import render
        from engine.pixel_art import decorate_rooms
        packet = render(compile_map(rooms), query.get('room', ''), designer=True)
        packet['pixel_assets'] = decorate_rooms(ed.data_dir, packet.get('rooms', []))
        return packet

    def dispatch(self, method, path, body=None, query=None, headers=None):
        """Return a response for an already-authenticated owner request."""
        with self._editors_lock:
            try:
                return self._dispatch(method, path, body, query or {}, headers or {})
            except EditorError as exc:
                return Reply({'error': str(exc)}, exc.status)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                return Reply({'error': str(exc)}, 400)

    def _dispatch(self, method, path, body, query, headers):
        parts = path.strip('/').split('/')
        if method not in ('GET', 'POST'):
            raise EditorError('Unsupported Creator method.', 405)
        if method == 'POST' and not isinstance(body, dict):
            raise EditorError('Expected a JSON object.')
        if parts == ['games']:
            if method == 'GET':
                return Reply(self.games())
            slug = body.get('slug')
            if not isinstance(slug, str) or not SLUG.fullmatch(slug):
                raise EditorError('Use a lowercase world name beginning with a letter (up to 32 characters).')
            ok, message = Editor.create_game(self.GAMES_DIR, slug, body.get('name'), body.get('template', 'blank'))
            if not ok:
                raise EditorError(message)
            return Reply({'ok': True, 'text': 'Created a separate draft. Export it to create a playable imported version.', **self.games()})
        if parts and parts[0] == 'art' and len(parts) >= 3 and method == 'GET':
            return self._file_action(parts[1], 'art', None, {'name': '/'.join(parts[2:])})
        if len(parts) < 3 or parts[0] != 'games':
            raise EditorError('Unknown Creator route.', 404)
        slug, action, args = parts[1], parts[2], parts[3:]
        self._root(slug)
        if action in ('apply', 'run'):
            raise EditorError('This is an isolated draft. Export its .expanse file, then import that version from World & saves.', 409)
        if action in ('files', 'file', 'file-upload', 'file-delete', 'file-download') and not args:
            return self._file_action(slug, action, body if method == 'POST' else None, query)
        if action in ('geology', 'regional_weather', 'population', 'pixel-art', 'history', 'soundtrack', 'tax-plans') and not args:
            return self._special(slug, action, body if method == 'POST' else None, headers)
        if action == 'world-rules' and not args:
            return Reply(self._rules(slug, body if method == 'POST' else None))
        if action == 'export-download' and method == 'GET' and not args:
            token = query.get('token', '')
            if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
                raise EditorError('Unknown export.', 404)
            target = self.directory / 'exports' / (slug + '-' + token + '.expanse')
            if target.is_symlink() or not target.is_file():
                raise EditorError('Export is unavailable. Export this draft again.', 404)
            return Reply(path=target, mime='application/octet-stream', download=slug + '.expanse')
        if action in ('map', 'world-atlas', 'live-globe') and method == 'GET' and not args:
            return Reply(self._map(slug, action, query))
        ed = self.get_editor(slug)
        if method == 'GET':
            if action == 'entries' and len(args) == 1 and args[0] in ed.data:
                return Reply({'entries': deepcopy(ed.data[args[0]])})
            if action == 'show' and len(args) == 2 and args[0] in ed.data:
                row = ed._find(*args)
                if row is None:
                    raise EditorError('No matching record.', 404)
                return Reply(deepcopy(row))
            if action == 'types' and not args:
                return Reply({'types': ed.item_types()})
            if action == 'record-sets' and not args:
                raw = self._read(slug, 'creator-packs.json', missing=True)
                packs = self._json(raw, 'creator-packs.json') if raw else {}
                return Reply({'sets': [{'key': key, 'title': value.get('title', key)} for key, value in packs.items()]})
            if action == 'validate' and not args:
                return Reply({'text': ed.validate()})
            raise EditorError('Unknown Creator action.', 404)
        if args:
            raise EditorError('Unexpected Creator path arguments.', 404)
        if action in ('new', 'setfield', 'edit', 'delete', 'duplicate'):
            if body.get('type') not in ed.data:
                raise EditorError('Choose a supported record type.')
            for field in ('id', 'source', 'field'):
                if field in body and (not isinstance(body[field], str) or not body[field] or len(body[field]) > 256):
                    raise EditorError('Use a nonempty text ' + field + ' of at most 256 characters.')
        if action == 'new':
            message = ed.new(body['type'], body['id'])
        elif action == 'setfield':
            json.dumps(body['value'], allow_nan=False)
            message = ed.setfield(body['type'], body['id'], body['field'], body['value'])
        elif action == 'edit':
            message = ed.edit(body['type'], body['id'], body['field'], body['value'])
        elif action == 'delete':
            message = ed.delete(body['type'], body['id'])
        elif action == 'duplicate':
            message = ed.copy(body['type'], body['source'], body.get('id'))
        elif action == 'addexit':
            message = ed.addexit(body['room'], body['direction'], body['target'])
        elif action == 'rmexit':
            message = ed.rmexit(body['room'], body['direction'])
        elif action == 'link':
            message = ed.link(body['a'], body['direction'], body['b'])
        elif action in ('placeitem', 'removeitem'):
            message = getattr(ed, action)(body['room'], body['item'])
        elif action == 'room-coordinates':
            from engine.coordinates import set_room_coordinates
            message = set_room_coordinates(ed, body)
        elif action == 'map-place':
            from engine.mapping import layout
            positions, warnings = layout(ed.data['room'])
            for room in ed.data['room']:
                if not all(type(room.get(k)) is int for k in ('map_x', 'map_y', 'map_z')):
                    room.update(zip(('map_x', 'map_y', 'map_z'), positions[room['id']]))
            ed.dirty.add('room')
            message = 'Unplaced room coordinates staged. Save draft when ready. ' + ' '.join(warnings)
        elif action == 'add-record-set':
            packs = self._json(self._read(slug, 'creator-packs.json'), 'creator-packs.json')
            pack = packs.get(body.get('key'))
            if not isinstance(pack, dict):
                raise EditorError('Select a record set included by this world.')
            total = 0
            if not pack.get('installed'):
                for kind, rows in pack['records'].items():
                    if kind not in ed.data:
                        raise EditorError('Unknown record type in world set.')
                    present = {row['id'] for row in ed.data[kind]}
                    additions = [deepcopy(row) for row in rows if row['id'] not in present]
                    if additions:
                        ed.data[kind].extend(additions); ed.dirty.add(kind); total += len(additions)
            message = str(total) + ' records staged. Save draft when ready.'
        elif action in ('living-enable', 'civic-enable'):
            meta = self._metadata(slug)
            meta['living_world'] = True
            if action == 'civic-enable':
                from engine.society import validate
                meta['society'] = True
                issues = validate(ed.data, meta)
                if issues:
                    raise EditorError('Complete the civic references first: ' + '; '.join(issues[:15]))
            self._write_metadata(slug, meta)
            message = 'Rules enabled in this draft. Export when ready.'
        elif action == 'save':
            message = self._save(slug)
        elif action == 'reload':
            self._editors.pop(slug, None)
            ed = self.get_editor(slug)
            message = 'Reloaded saved draft; staged record changes discarded.'
        elif action == 'image':
            ext = str(body.get('ext', 'jpg')).lower()
            if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                raise EditorError('Choose PNG, JPEG or WebP.')
            raw = base64.b64decode(str(body.get('data', '')).split(',', 1)[-1], validate=True)
            if len(raw) > 4 * 1024 * 1024:
                raise EditorError('Title image must be at most 4 MB.')
            name = 'images/title.' + ext
            current = self._read(slug, name, missing=True)
            self._write_bytes(slug, name, raw, hashlib.sha256(current).hexdigest())
            for other in ('jpg', 'jpeg', 'png', 'webp'):
                if other != ext:
                    self._path(slug, 'images/title.' + other).unlink(missing_ok=True)
            message = 'Title image saved in the draft.'
        elif action == 'export':
            if 'path' in body:
                raise EditorError('Export downloads a .expanse file. Server filesystem paths are not accepted.')
            if self._pending(slug):
                raise EditorError('Save draft before exporting its staged record edits.', 409)
            report = ed.validate()
            if not report.startswith('OK'):
                raise EditorError('Fix the draft validation issues before exporting:\n' + report)
            folder = self.directory / 'exports'
            if folder.is_symlink():
                raise EditorError('Export folder must not be a symbolic link.')
            folder.mkdir(exist_ok=True)
            token = secrets.token_hex(16)
            target = folder / (slug + '-' + token + '.expanse')
            ok, message = exchange.export_game(slug, self.GAMES_DIR, target)
            if not ok:
                raise EditorError(message)
            exports = sorted(folder.glob(slug + '-*.expanse'), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in exports[5:]:
                old.unlink()
            return Reply({'ok': True, 'text': 'Export ready. Import this .expanse file from World & saves to add a playable version.',
                          'download_url': self.url(slug, 'export-download', token=token),
                          'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        else:
            raise EditorError('Unknown Creator action.', 404)
        return Reply({'ok': True, 'text': message, 'dirty': sorted(ed.dirty), 'running_game': self.slug, 'draft_only': True})
