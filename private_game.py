"""One private player process. Its listener is inherited on loopback."""
import argparse
import asyncio
import contextlib
import json
import os
import socket
import secrets
from pathlib import Path

from aiohttp import web, WSMsgType
from engine import loader, persistence
from engine.build_info import BUILD
from engine.character_style import choices, class_accents
from server import game_server, save_slots, playtest_telemetry, world_catalogue
from server.accounts import display_name


class PlayerSocket:
    def __init__(self, websocket, telemetry=None):
        self.socket = websocket
        self.remote_address = None
        self.telemetry = telemetry

    async def send(self, message):
        if not self.socket.closed:
            if self.telemetry:
                message = self.telemetry.safely('packet', message) or message
            await self.socket.send_str(message)

    async def close(self, code=1000, reason=''):
        await self.socket.close(code=code, message=reason.encode())

    async def __aiter__(self):
        async for message in self.socket:
            if message.type != WSMsgType.TEXT:
                break
            if self.telemetry:
                self.telemetry.safely('before', message.data)
            try:
                yield message.data
            finally:
                if self.telemetry:
                    self.telemetry.safely('after')


class Game:
    def __init__(self, world, directory, name, update_templates=()):
        self.path = Path(world)
        self.directory = Path(directory)
        self.name = name
        self.slug = self.path.name
        self.directory.mkdir(parents=True, exist_ok=True)
        loader.GAMES_DIR = self.path.parent
        loader.WORLD_UPDATE_TEMPLATES = tuple(Path(path) for path in update_templates)
        loader.set_game_dir(self.path)
        persistence.DB_PATH = self.directory / 'world.db'
        game_server.SAVE_DIR = self.directory
        self.server = game_server.GameServer(mode='single')
        self.telemetry = playtest_telemetry.open_collector(self.server, self.directory, self.slug)
        self.socket = None
        self.play_task = None

    async def play(self, request):
        if self.play_task:
            raise web.HTTPConflict(text='This game is already open in another tab.')
        ws = web.WebSocketResponse(max_msg_size=65536)
        await ws.prepare(request)
        self.socket = ws
        self.play_task = asyncio.current_task()
        timer = asyncio.create_task(self.server.lifecycle_loop())
        try:
            await self.server.handle(PlayerSocket(ws, self.telemetry))
        finally:
            self.telemetry.safely('finish', 'disconnected')
            timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timer
            self.socket = self.play_task = None
        return ws

    async def api(self, req):
        action = req.path.removeprefix('/api/')
        body = await req.json() if req.method == 'POST' else {}
        if not isinstance(body, dict):
            raise ValueError('Expected a form.')
        if action == 'config':
            result = dict(mode='single', running_game=self.slug, title='Expanse',
                          build=BUILD, render_web=True, account_name=self.name,
                          character_name='', character_name_locked=False,
                          can_manage_server=False, editor_enabled=False, game_status='ready',
                          playtest=self.telemetry.configuration())
        elif action == 'playtest/status':
            result = self.telemetry.status()
        elif action == 'playtest/activity':
            result = self.telemetry.activity(body)
        elif action == 'playtest/feedback':
            result = self.telemetry.store.feedback(body)
        elif action == 'games':
            info = world_catalogue.display_info({'slug':self.slug}, self.server.world.metadata)
            result = {'games':[{'slug':self.slug,'name':info['display_name']}]}
        elif action == 'character/options':
            w = self.server.world
            result = dict(races=[dict(choices(r, {}), id=r['id'], name=r.get('name',r['id'])) for r in w.races.values()],
                          classes=[dict(id=r['id'],name=r.get('name',r['id']),accents=class_accents(r)) for r in w.classes.values()],
                          sexes=[dict(id=r['id'],name=r.get('name',r['id'])) for r in w.sexes.values()],
                          factions=[dict(id=r['id'],name=r.get('name',r['id'])) for r in w.groups.values() if r.get('visibility')=='playable'])
        elif action == 'character/saves':
            rows = await self.server.saved_characters(self.slug)
            result = dict(characters=save_slots.visible_characters(self.directory, rows), world=self.slug, mode='single')
        elif action == 'character/create':
            first = body.get('first_name', '')
            last = body.get('last_name', '')
            if not isinstance(first, str) or not first.strip():
                raise ValueError('First name is required and must be text.')
            if not isinstance(last, str):
                raise ValueError('Last name must be text, or leave it empty.')
            if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in first + last):
                raise ValueError('Character names cannot contain control characters.')
            # Account ownership is established by the authenticated private
            # worker and its save directory. Character names are display data.
            # Normalize the fields separately so multiword given names stay intact.
            first = display_name(first)
            last = display_name(last) if last.strip() else ''
            combined = ' '.join(filter(None, (first, last)))
            if len(combined) > 61:
                raise ValueError('First and last names together must be at most 61 characters.')
            display_name(combined)
            result = await self.server.create_character(dict(body, first_name=first,last_name=last,game_slug=self.slug))
        elif action == 'character/load':
            if not any(r['id']==body.get('player_id') for r in await self.server.saved_characters(self.slug)):
                raise ValueError('No matching character in this game.')
            result = dict(player_id=body['player_id'],world=self.slug)
        elif action == 'character/delete':
            result = await self.server.delete_character(body['player_id'],self.slug,owner=True)
        elif action == 'application/saves':
            result = dict(slots=save_slots.catalogue(self.directory,self.legacy()))
        elif action == 'save-slots/delete':
            entries = save_slots.chosen(self.directory,body,self.legacy)
            save_slots.delete_many(self.directory,entries,player=None,owner=True)
            for entry in entries:
                save_slots.detach(self.server,entry)
            result = dict(text='Deleted selected saves.')
        elif action == 'save-slots/open':
            entry = save_slots.lookup(self.directory,body,self.legacy)
            initial = None
            if not entry.get('legacy'):
                meta,data,_ = save_slots.read(self.directory,entry['slot'],entry['revision'])
                initial = (meta,data)
            if self.socket:
                await self.socket.close()
                if self.play_task:
                    await self.play_task
            self.server.db.close()
            self.server.checkpoint_db.close()
            self.server = game_server.GameServer(mode='single', initial_slot=initial)
            self.telemetry.server = self.server
            result = dict(redirect='/play')
        else:
            raise web.HTTPNotFound()
        return web.json_response(result)

    def legacy(self):
        return save_slots.legacy_records(self.directory,loader.GAMES_DIR)


@web.middleware
async def handle_errors(request, handler):
    try:
        return await handler(request)
    except playtest_telemetry.UnavailableError as exc:
        return web.json_response({'error':str(exc),'playtest_unavailable':True},status=503)
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({'error':str(exc)},status=400)


def make_app(world, directory, name, update_templates=()):
    game = Game(world,directory,name,update_templates)
    token = os.environ.pop('EXPANSE_WORKER_TOKEN')
    @web.middleware
    async def private(req,handler):
        if not secrets.compare_digest(req.headers.get('X-Worker-Key',''),token):
            raise web.HTTPForbidden()
        return await handler(req)
    app = web.Application(middlewares=[private,handle_errors],client_max_size=65536)
    app.router.add_get('/ws',game.play)
    for path in ('config','games','character/options','character/saves','application/saves','playtest/status'):
        app.router.add_get('/api/'+path,game.api)
    for path in ('character/create','character/load','character/delete','save-slots/open','save-slots/delete',
                 'playtest/activity','playtest/feedback'):
        app.router.add_post('/api/'+path,game.api)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('world','directory','fd','name'):
        parser.add_argument('--'+key,required=True)
    parser.add_argument('--update-template',action='append',default=[])
    args = parser.parse_args()
    web.run_app(make_app(args.world,args.directory,args.name,args.update_template),sock=socket.socket(fileno=int(args.fd)),print=None,access_log=None)
