"""Account-owned text drafts for the explicitly enabled loopback staging host."""
import hashlib
import json
import os
import re
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from aiohttp import web

DRAFT_FLAG = 'EXPANSE_PRIVATE_MMO_DRAFT'
DRAFT_PATH = '/api/creator-proof'

def verify_archive(source, revision):
    if os.environ.get(DRAFT_FLAG) != '1':
        raise ValueError('Set EXPANSE_PRIVATE_MMO_DRAFT=1 to enable staging drafts.')
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
        raise ValueError('Supply the reviewed archive SHA-256 to enable staging drafts.')
    if source.is_symlink() or source.suffix != '.expanse' or not source.is_file():
        raise ValueError('Staging drafts require a reviewed .expanse archive.')
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != revision:
            raise ValueError('The staging archive differs from the reviewed SHA-256.')


class StageDraft:
    def __init__(self, source, directory, revision, world, account_for_request):
        self.root = directory / 'creator-proof' / revision
        self.revision = revision
        self.account_for_request = account_for_request
        # Only one immutable authored record. No engine references or paths
        # supplied by a client, no need for broad legacy editor capabilities.
        with source.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != revision:
                raise ValueError('The staging archive changed during import.')
            stream.seek(0)
            with ZipFile(stream) as archive:
                manifest = archive.read('manifest.json')
                rooms = archive.read('rooms.json')
        if (manifest != (world / 'manifest.json').read_bytes()
                or rooms != (world / 'rooms.json').read_bytes()):
            raise ValueError('The staged authored rooms do not match the reviewed archive.')
        metadata = json.loads(manifest)
        self.world = metadata['slug']
        ident = metadata['start_room']
        record = next((room for room in json.loads(rooms) if room['id'] == ident), None)
        if record is None:
            raise ValueError('The reviewed archive has no authored starting room.')
        self.room = {k: record[k] for k in ('id', 'name', 'description')}

    def _account(self, request):
        action = 'editor_draft' if request.method == 'POST' else 'editor_view'
        account = self.account_for_request(request, action)
        if request.query:
            raise ValueError('The draft scope is fixed by the staging session.')
        # The authorizer returns the canonical registered name. It rejects
        # separators and periods and also supports multiword owner names.
        return account

    def _read(self, target):
        if target.is_symlink() or any(p.is_symlink() for p in (self.root, self.root.parent)):
            raise web.HTTPConflict(text='Draft storage is unavailable.')
        if not target.exists():
            return dict(world=self.world, revision=self.revision, version=0, room=self.room.copy())
        try:
            obj = json.loads(target.read_bytes())
            if (obj.get('world') != self.world or obj.get('revision') != self.revision
                    or type(obj.get('version')) is not int or obj.get('version') < 1
                    or not isinstance(obj.get('room'), dict) or obj['room'].get('id') != self.room['id']):
                raise ValueError()
            return obj
        except (ValueError, AttributeError, OSError) as exc:
            raise web.HTTPConflict(text='Existing draft was not changed.') from exc

    @staticmethod
    def _text(value, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or re.search(r'[\x00-\x1f\x7f]', value):
            raise ValueError('Enter plain text on one line within the field limit.')
        return value.strip()

    async def handle(self, request):
        account = self._account(request)
        body = None
        if request.method == 'POST':
            if request.content_type != 'application/json' or request.content_length is None or request.content_length > 8192:
                raise web.HTTPBadRequest(text='Use a small draft JSON object.')
            try:
                body = await request.json()
            except Exception as exc:
                if isinstance(exc, web.HTTPException): raise
                raise ValueError('Invalid draft JSON.') from exc
            # Reading request data may yield; role/revocation can change while
            # waiting. No async break after this check up to the atomic write.
            if self._account(request) != account:
                raise PermissionError('The staging account changed.')
        target = self.root / (account + '.json')
        current = self._read(target)
        if request.method == 'GET':
            return web.json_response(current)
        if not isinstance(body, dict) or set(body) != {'world', 'revision', 'version', 'room', 'name', 'description'}:
            raise ValueError('Expected only the draft version, scope, and two editable text fields.')
        if (body['world'] != self.world or body['revision'] != self.revision
                or body['room'] != self.room['id'] or type(body['version']) is not int
                or body['version'] != current['version']):
            raise web.HTTPConflict(text='Reload your own current draft before editing.')
        result = dict(world=self.world, revision=self.revision, version=current['version'] + 1,
                      room=dict(id=self.room['id'], name=self._text(body['name'], 120),
                                description=self._text(body['description'], 1500)))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        filename = None
        try:
            with NamedTemporaryFile(mode='wb', dir=self.root, delete=False) as stream:
                filename = stream.name
                stream.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, target)
            dir_fd = os.open(self.root, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if filename and os.path.exists(filename):
                os.unlink(filename)
        return web.json_response(result)
