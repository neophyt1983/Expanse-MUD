"""Opt-in, loopback-only integration host; never a public MMO deployment.

Run in its own process: the engine's loader and save paths are process globals.
Only a new, explicitly marked staging directory is accepted. Existing Render
account directories, solo saves and authored source content are never opened for
writing. The production Render gateway deliberately remains closed to MMO play.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from urllib.parse import urlsplit

from aiohttp import web

from engine import classless, loader, persistence, starting_cities
from private_game import PlayerSocket
from render_server import Accounts
from server import game_server
from server.accounts import display_name, name_key
from server.mmo_access import MMOAuthorizer
from server.mmo_ownership import MMOOwnership
from server.mmo_roles import MMORoles, ROLES
from server.stage_creator_draft import DRAFT_PATH, StageDraft, verify_archive

COOKIE = 'expanse_shared_staging'
ROOT = Path(__file__).resolve().parent.parent
STATE = web.AppKey('shared_staging')


def staging_directory(source, directory):
    """Refuse accidental use of a populated or mismatched data directory."""
    source, directory = Path(source).resolve(), Path(directory).absolute()
    if directory.is_symlink():
        raise ValueError('The staging directory must not be a symlink.')
    if not (source.is_dir() or (source.is_file() and source.suffix == '.expanse')):
        raise ValueError('Choose an authored world directory or a .expanse game file.')
    if directory.resolve() == source or source in directory.resolve().parents:
        raise ValueError('Use a separate staging data directory outside the source world.')
    marker = directory / 'SHARED-STAGING.json'
    expected = {'format': 1, 'source': str(source)}
    if directory.exists() and any(directory.iterdir()):
        if any(path.is_symlink() for path in directory.rglob('*')):
            raise ValueError('Staging data must not contain symlinks.')
        if marker.is_symlink() or not marker.is_file():
            raise ValueError('Refusing existing data: use a NEW empty staging directory.')
        if json.loads(marker.read_text(encoding='utf-8')) != expected:
            raise ValueError('Staging world or directory does not match its marker.')
    else:
        directory.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(expected) + '\n', encoding='utf-8')
    return source, directory.resolve()


def copy_world(source, directory):
    """Import once into the isolated directory, preserving source content."""
    games = directory / 'games'
    # The validated archive importer accepts underscores, not hyphens.
    # Keep existing directory-based staging worlds at their legacy identity
    # so their character/save namespaces do not change on restart.
    legacy = games / 'shared-staging'
    world = legacy if legacy.exists() else games / 'shared_staging'
    if world.exists():
        if world.is_symlink() or not (world / 'rooms.json').is_file():
            raise ValueError('The staging world is incomplete. Do not overwrite it.')
        return world
    games.mkdir(exist_ok=True)
    if source.is_file():
        from engine.exchange import import_game
        ok, note = import_game(source, games, as_slug=world.name)
        if not ok:
            raise ValueError(note)
    else:
        if not (source / 'rooms.json').is_file():
            raise ValueError('The authored world directory needs rooms.json.')
        if any(path.is_symlink() for path in source.rglob('*')):
            raise ValueError('Staging source worlds must not contain symlinks.')
        shutil.copytree(source, world)
    return world


class SharedPlayerSocket(PlayerSocket):
    def __init__(self, socket, server):
        super().__init__(socket)
        self.server = server

    async def __aiter__(self):
        async for raw in super().__aiter__():
            self.server.mmo_activity[self] = time.monotonic()
            yield raw


class SharedStaging:
    def __init__(self, source, directory, origin, auth=None, idle_timeout=900, creator_draft_sha256=None):
        if os.environ.get('EXPANSE_SHARED_STAGING') != '1':
            raise ValueError('Set EXPANSE_SHARED_STAGING=1 to opt into local testing.')
        parsed = urlsplit(origin)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or parsed.path or parsed.query or parsed.fragment or parsed.username
                or parsed.password or not parsed.port):
            raise ValueError('Staging must use http://127.0.0.1:<port>.')
        self.origin = origin
        if not isinstance(idle_timeout,(int,float)) or isinstance(idle_timeout,bool) or idle_timeout<=0:
            raise ValueError('The idle timeout must be positive seconds.')
        if creator_draft_sha256 is not None:
            verify_archive(Path(source), creator_draft_sha256)
        source, self.directory = staging_directory(source, directory)
        # A second process must not operate the same mutable shared world.
        self.lock = sqlite3.connect(self.directory / 'runtime-lock.sqlite3', timeout=0)
        try:
            self.lock.execute('CREATE TABLE IF NOT EXISTS runtime_lock (id INTEGER)')
            self.lock.commit()
            self.lock.execute('BEGIN EXCLUSIVE')
            self.auth = auth if auth is not None else Accounts()
            if not self.auth.owner:
                raise ValueError('Staging requires a protected owner account.')
            self.roles = MMORoles(self.directory, self.auth.owner)
            self.ownership = MMOOwnership(self.directory)
            self.policy = MMOAuthorizer(self.auth.lookup, self.roles, self.ownership,
                                        owner=self.auth.owner)
            self.world = copy_world(source, self.directory)
            self.creator_draft = None
            if creator_draft_sha256 is not None:
                self.creator_draft = StageDraft(source, self.directory, creator_draft_sha256,
                                               self.world, self.account)
            loader.GAMES_DIR = self.world.parent
            loader.WORLD_UPDATE_TEMPLATES = ()
            loader.set_game_dir(self.world)
            persistence.DB_PATH = self.directory / 'save' / 'world.db'
            game_server.SAVE_DIR = self.directory / 'save'
            game_server.WORLD_STATE_PATH = self.directory / 'save' / 'world_state_host.json'
            self.server = game_server.GameServer(mode='host')
            self.server.http_port = parsed.port
            self.server.mmo_authorizer = self.policy
            self.server.mmo_sessions = {}
            self.server.mmo_save_on_exit = True
            self.server.mmo_idle_timeout = idle_timeout
            self.server.mmo_activity = {}
            self.sockets = set()
            self.play_tasks = set()
        except BaseException:
            self.lock.close()
            raise

    def session(self, request):
        return request.cookies.get(COOKIE, '')

    def account(self, request, action='play', **kwargs):
        return self.policy.authorize(self.session(request), action, **kwargs)

    def page(self, content):
        return web.Response(text=(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Expanse local shared staging</title><body>'
            '<h1>Expanse — local shared staging</h1>'
            '<p>This is a separate test world. The public MMO remains disabled. '
            'MMO progress saves on exit, disconnect or idle timeout. '
            'An explicit Save also commits the shared world for everyone. '
            'Single Player keeps its manual-save policy.</p>'
            + content + '</body></html>'), content_type='text/html')

    async def landing(self, request):
        account = self.auth.lookup(self.session(request))
        if not account:
            return self.page('<form method="post" action="/login">'
                '<label>Account <input name="name" autocomplete="username" required></label>'
                '<label>Password <input name="password" type="password" '
                'autocomplete="current-password" required></label><button>Sign in</button></form>')
        content = '<p>Signed in as ' + escape(account) + '. Role: ' + escape(self.roles.get(account)) + '.</p>'
        content += '<p><a href="/play">Play in the shared test world</a></p>'
        if account == self.auth.owner:
            content += '<p><a href="/roles">Staging account roles</a></p>'
        return self.page(content + '<form method="post" action="/logout"><button>Sign out</button></form>')

    async def login(self, request):
        form = await request.post()
        password = form.get('password', '')
        if not isinstance(password, str):
            raise ValueError('Enter a password.')
        token = self.auth.authenticate(form.get('name', ''), password)
        if not token:
            return web.json_response({'error': 'Invalid or expired credentials.'}, status=401)
        reply = web.HTTPSeeOther('/')
        reply.set_cookie(COOKIE, token, httponly=True, samesite='Strict', path='/')
        raise reply

    async def logout(self, request):
        self.auth.sessions.pop(self.session(request), None)
        reply = web.HTTPSeeOther('/')
        reply.del_cookie(COOKIE, path='/')
        raise reply

    async def role_page(self, request):
        self.account(request, 'assign_role')
        if request.method == 'POST':
            form = await request.post()
            self.roles.assign(self.account(request, 'assign_role'), form.get('name'),
                              form.get('role'), [row[0] for row in self.auth.records.values()])
            raise web.HTTPSeeOther('/roles')
        content = '<p>These assignments apply only to this staging directory.</p>'
        if self.creator_draft:
            content += '<p>Admin and Full_Edit accounts can save their own starting-room text drafts.</p>'
        for key, (name, _, _) in self.auth.records.items():
            if key == self.auth.owner:
                continue
            content += '<form method="post"><input type="hidden" name="name" value="'+escape(name, quote=True)+'">'
            content += escape(name) + ' <select name="role">'
            for role in ROLES:
                content += '<option'+(' selected' if role == self.roles.get(key) else '')+'>'+role+'</option>'
            content += '</select><button>Assign staging role</button></form>'
        return self.page(content + '<p><a href="/">Back</a></p>')

    async def play(self, request):
        self.account(request)
        return web.FileResponse(ROOT / 'web' / 'index.html')

    async def api(self, request):
        account = self.account(request)
        path = request.path.removeprefix('/api/')
        body = await request.json() if request.method == 'POST' else {}
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object.')
        server = self.server
        if path == 'config' and request.method == 'GET':
            from engine.build_info import BUILD
            return web.json_response(dict(mode='host', running_game=self.world.name,
                title='Expanse local shared staging', build=BUILD, render_web=True,
                internet_accounts=True, account_name=account, can_manage_server=False,
                editor_enabled=False, editor_reason='shared_staging_closed',
                game_status='ready', shared_staging=True, mmo_role=self.roles.get(account),
                save_on_exit=True, idle_timeout=self.server.mmo_idle_timeout))
        if path == 'games' and request.method == 'GET':
            return web.json_response({'games': [{'slug': self.world.name,
                'name': server.world.metadata.get('name', 'Shared staging world')}]})
        if path == 'character/options' and request.method == 'GET':
            world = server.world
            return web.json_response({
                **classless.options(world),
                **starting_cities.option_fields(world, supported=True),
            })
        if path == 'character/saves' and request.method == 'GET':
            self.account(request, 'list_characters')
            from engine.persistence import list_saves
            owned = self.ownership.characters(account)
            rows = [row for row in list_saves(server.db, 'host', self.world.name) if row['id'] in owned]
            # Include unsaved characters so reconnecting never creates another character.
            for row in rows:
                row['unsaved'] = not bool(row.get('saved_at'))
            return web.json_response(dict(characters=rows, world=self.world.name, mode='host'))
        if path == 'character/create' and request.method == 'POST':
            self.account(request, 'create_character')
            first, last = body.get('first_name'), body.get('last_name', '')
            if not isinstance(first, str) or not isinstance(last, str):
                raise ValueError('First and last names must be text.')
            first, last = display_name(first), display_name(last) if last.strip() else ''
            combined = display_name(' '.join(filter(None, (first, last))))
            for field in ('race', 'class', 'sex', 'faction', 'starting_city', 'description'):
                value = body.get(field, '')
                if not isinstance(value, str) or len(value) > (2000 if field == 'description' else 100):
                    raise ValueError('Invalid ' + field + '.')
            for _, name in server.db.execute('SELECT id,name FROM players WHERE game_mode=?', ('host',)):
                if name_key(name) == name_key(combined):
                    raise ValueError('That character name is already in use in this shared world.')
            result = await server.create_character(
                {**body, 'first_name': first, 'last_name': last}, supports_city_choice=True)
            try:
                self.policy.claim_created(self.session(request), result['player_id'])
            except BaseException:
                await server.delete_character(result['player_id'], self.world.name, owner=True)
                raise
            return web.json_response(result)
        if path == 'character/load' and request.method == 'POST':
            pid = body.get('player_id')
            self.account(request, 'load_character', character_id=pid)
            if not server.db.execute('SELECT 1 FROM players WHERE id=? AND game_mode=?', (pid, 'host')).fetchone():
                raise ValueError('That character has no remaining saved or running state.')
            return web.json_response(dict(player_id=pid, world=self.world.name))
        # In particular, deny Creator, arbitrary world imports/deletes, global
        # save-slot rewinds and application-control endpoints, for EVERY role.
        raise web.HTTPForbidden(text='This endpoint is closed in shared staging.')

    async def socket(self, request):
        self.account(request)
        socket = web.WebSocketResponse(max_msg_size=65536, heartbeat=20)
        await socket.prepare(request)
        adapter = SharedPlayerSocket(socket,self.server)
        adapter.request = request
        adapter.remote_address = request.transport.get_extra_info('peername')
        adapter.local_address = request.transport.get_extra_info('sockname')
        self.server.mmo_sessions[adapter] = self.session(request)
        self.server.mmo_activity[adapter] = time.monotonic()
        self.sockets.add(socket)
        task = asyncio.current_task()
        self.play_tasks.add(task)
        try:
            await self.server.handle(adapter)
        finally:
            self.server.mmo_sessions.pop(adapter, None)
            self.server.mmo_activity.pop(adapter, None)
            self.sockets.discard(socket)
            self.play_tasks.discard(task)
            await socket.close()
        return socket

    async def lifecycle(self, app):
        timer = asyncio.create_task(self.server.lifecycle_loop())
        yield
        self.server.closing = True
        timer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await timer
        await self.shutdown(app)
        # A graceful host stop must preserve disconnected/created characters
        # too. A hard process kill is not a clean exit and cannot promise this.
        try:
            if self.server.db.execute('SELECT 1 FROM players LIMIT 1').fetchone():
                self.server._save_players_and_world()
        finally:
            self.server.db.close()
            self.server.checkpoint_db.close()
            self.lock.close()

    async def shutdown(self, app):
        # aiohttp calls on_shutdown BEFORE waiting for active handlers. Closing
        # sockets here lets each handler finish its exit checkpoint promptly.
        self.server.closing = True
        await asyncio.gather(*(ws.close() for ws in list(self.sockets)))
        if self.play_tasks:
            await asyncio.gather(*list(self.play_tasks),return_exceptions=True)


def make_app(source, directory, origin='http://127.0.0.1:8870', *, auth=None,idle_timeout=900,
             creator_draft_sha256=None):
    service = SharedStaging(source, directory, origin, auth, idle_timeout, creator_draft_sha256)

    @web.middleware
    async def guard(request, handler):
        if request.host != urlsplit(service.origin).netloc:
            raise web.HTTPForbidden(text='Use this staging host\'s loopback address.')
        if request.method != 'GET' or request.path == '/ws':
            if request.headers.get('Origin') != service.origin:
                raise web.HTTPForbidden(text='Open the configured local staging address.')
        try:
            return await handler(request)
        except PermissionError as exc:
            return web.json_response({'error': str(exc)}, status=403)
        except (ValueError, KeyError, TypeError) as exc:
            return web.json_response({'error': str(exc)}, status=400)

    app = web.Application(middlewares=[guard], client_max_size=65536)
    app[STATE] = service
    app.cleanup_ctx.append(service.lifecycle)
    app.on_shutdown.append(service.shutdown)

    async def headers(request, response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin'})
    app.on_response_prepare.append(headers)

    async def health(request):
        pending=len(getattr(service.server,'mmo_pending_saves',()))
        return web.json_response(dict(status='save-degraded' if pending else 'local-staging-only',
            public_mmo=False,pending_exit_saves=pending),status=503 if pending else 200)

    assets = {path.name: path for path in (ROOT / 'web').iterdir() if path.is_file()
              and path.suffix in ('.js', '.css', '.svg', '.ico', '.png')}

    async def asset(request):
        service.account(request)
        path = assets.get(request.match_info['filename'])
        if path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    if service.creator_draft:
        app.add_routes([web.get(DRAFT_PATH, service.creator_draft.handle, allow_head=False),
                        web.post(DRAFT_PATH, service.creator_draft.handle)])

    app.add_routes([web.get('/', service.landing), web.get('/mode.html', service.landing),
        web.get('/healthz', health), web.post('/login', service.login), web.post('/logout', service.logout),
        web.get('/roles', service.role_page), web.post('/roles', service.role_page),
        web.get('/play', service.play), web.get('/ws', service.socket),
        web.get('/api/{path:.*}', service.api), web.post('/api/{path:.*}', service.api),
        web.get('/{filename}', asset)])
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', required=True, help='Authored world directory or .expanse game file')
    parser.add_argument('--directory', required=True, help='NEW empty, dedicated staging data directory')
    parser.add_argument('--port', type=int, default=8870)
    parser.add_argument('--creator-draft-sha256',
                        help='Enable per-account staging drafts for this reviewed .expanse SHA-256. '
                             'Also requires EXPANSE_PRIVATE_MMO_DRAFT=1.')
    parser.add_argument('--idle-timeout',type=int,default=900,help='Idle disconnect/save timeout in seconds (default: 900)')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a local port from 1024 to 65535.')
    os.umask(0o077)
    origin = f'http://127.0.0.1:{args.port}'
    app = make_app(args.world, args.directory, origin, idle_timeout=args.idle_timeout,
                   creator_draft_sha256=args.creator_draft_sha256)
    print('LOCAL TEST ONLY. Public MMO remains closed. Open ' + origin)
    web.run_app(app, host='127.0.0.1', port=args.port, access_log=None)


if __name__ == '__main__':
    main()
