"""Real HTTP/WebSocket shared-host acceptance on disposable authored content.

These tests use four actual account cookies and the production loader/command
path. They are loopback integration tests, not full-world capacity measurements
or evidence that the still-closed public Render gateway is ready to open.
"""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, CookieJar, WSMsgType, WSServerHandshakeError
from aiohttp.test_utils import TestServer

from engine import loader, persistence
from render_server import Accounts
from server import game_server, shared_staging
from server.mmo_roles import ADMIN, FULL_EDIT, NO_EDIT


class SharedHostTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='expanse-shared-http-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'authored-world'
        self.source.mkdir()
        content = {
            'metadata.json': {'name': 'Shared transport fixture', 'start_room': 'inn',
                              'start_minute': 375, 'living_world': True,
                              'society': False, 'max_players': 4},
            'rooms.json': [
                {'id': 'inn', 'name': 'Travellers Inn', 'description': 'A common room.',
                 'exits': {'out': 'square'}, 'items': ['carrot'], 'map_x': 0, 'map_y': 0},
                {'id': 'square', 'name': 'Civic Square', 'description': 'A public square.',
                 'exits': {'in': 'inn'}, 'map_x': 1, 'map_y': 0},
            ],
            'items.json': [{'id': 'carrot', 'name': 'Garden carrot', 'type': 'food', 'value': 1}],
            'races.json': [{'id': 'human', 'name': 'Human'}],
            'classes.json': [{'id': 'fighter', 'name': 'Fighter'}],
            'sexes.json': [{'id': 'unspecified', 'name': 'Unspecified'}],
        }
        for filename, data in content.items():
            (self.source / filename).write_text(json.dumps(data), encoding='utf-8')
        self.source_bytes = self.files(self.source)
        self.runtime = self.root / 'runtime'
        self.credentials = {name: 'disposable-test-password-' + name
                            for name in ('Owner', 'Alpha', 'Beta', 'Gamma')}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict('os.environ', {
            'EXPANSE_SHARED_STAGING': '1', 'EXPANSE_OWNER_NAME': 'Owner',
            'EXPANSE_OWNER_PASSWORD': self.credentials['Owner'],
            'EXPANSE_OWNER_EXPIRES_AT': '',
            'EXPANSE_GUESTS_JSON': json.dumps([
                {'name': name, 'password': password}
                for name, password in self.credentials.items() if name != 'Owner']),
        }))
        for owner, attr in ((loader, 'GAME_DIR'), (loader, 'DATA_DIR'),
                            (loader, 'GAMES_DIR'), (loader, 'WORLD_UPDATE_TEMPLATES'),
                            (persistence, 'DB_PATH'), (game_server, 'SAVE_DIR'),
                            (game_server, 'WORLD_STATE_PATH')):
            self.stack.enter_context(patch.object(owner, attr, getattr(owner, attr)))
        self.clients = []
        self.websockets = []
        self.http = None
        await self.start()

    @staticmethod
    def files(directory):
        return {str(path.relative_to(directory)): path.read_bytes()
                for path in directory.rglob('*') if path.is_file()}

    async def start(self):
        self.auth = Accounts()
        self.app = shared_staging.make_app(self.source, self.runtime, auth=self.auth)
        self.service = self.app[shared_staging.STATE]
        self.http = TestServer(self.app)
        await self.http.start_server()
        self.origin = str(self.http.make_url('')).rstrip('/')
        self.service.origin = self.origin
        self.service.server.http_port = self.http.port

    async def stop(self):
        for socket in self.websockets:
            await socket.close()
        self.websockets.clear()
        for client in self.clients:
            await client.close()
        self.clients.clear()
        if self.http:
            await self.http.close()
            self.http = None

    async def asyncTearDown(self):
        await self.stop()
        self.assertEqual(self.source_bytes, self.files(self.source),
                         'The authored source must remain byte-identical.')

    async def login(self, name):
        client = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.clients.append(client)
        response = await client.post(self.origin + '/login',
            data={'name': name, 'password': self.credentials[name]},
            headers={'Origin': self.origin}, allow_redirects=False)
        self.assertEqual(303, response.status, await response.text())
        return client

    async def create(self, client, name):
        response = await client.post(self.origin + '/api/character/create',
            json={'first_name': name, 'race': 'human', 'class': 'fighter'},
            headers={'Origin': self.origin})
        self.assertEqual(200, response.status, await response.text())
        return (await response.json())['player_id']

    async def receive(self, socket, predicate):
        for _ in range(80):
            message = await socket.receive(timeout=4)
            self.assertEqual(WSMsgType.TEXT, message.type, message)
            packet = json.loads(message.data)
            if predicate(packet):
                return packet
        self.fail('Expected websocket response was not received.')

    async def connect(self, client, pid=None):
        socket = await client.ws_connect(self.origin + '/ws', headers={'Origin': self.origin})
        self.websockets.append(socket)
        await self.receive(socket, lambda packet: packet.get('type') == 'welcome')
        if pid:
            await socket.send_json({'command': 'resume', 'player_id': pid})
            await self.receive(socket, lambda packet: packet.get('event') == 'character_entered')
        return socket

    async def command(self, socket, command, **fields):
        await socket.send_json({'command': command, **fields})
        return await self.receive(socket, lambda packet: packet.get('type') in
                                  ('response', 'error', 'dm_result', 'dm_error', 'save_slots', 'saved_exit'))

    async def eventually(self, predicate):
        # Yield to actual socket/lifecycle tasks, with a bounded diagnostic wait.
        deadline = asyncio.get_running_loop().time() + 4
        while not predicate():
            if asyncio.get_running_loop().time() >= deadline:
                self.fail('The shared host did not finish the expected lifecycle transition.')
            await asyncio.sleep(0.01)

    async def test_four_accounts_share_one_world_with_finite_pickup_chat_and_movement(self):
        clients = [await self.login(name) for name in self.credentials]
        pids = [await self.create(client, 'Traveller ' + str(index))
                for index, client in enumerate(clients)]
        sockets = [await self.connect(client, pid) for client, pid in zip(clients, pids)]
        self.assertEqual(4, len(self.service.server.clients))
        self.assertEqual(set(pids), set(self.service.server.clients.values()))
        replies = await asyncio.gather(*(self.command(socket, 'get carrot') for socket in sockets))
        inventories = [self.service.server.world.entities[pid].inventory for pid in pids]
        self.assertEqual(1, sum(items.count('carrot') for items in inventories), replies)
        self.assertEqual([], self.service.server.world.rooms['inn'].items)
        await sockets[0].send_json({'command': 'chat shared-world-proof'})
        for socket in sockets:
            reply = await self.receive(socket, lambda packet: 'shared-world-proof' in packet.get('text', ''))
            self.assertIn('Traveller 0', reply['text'])
        await self.command(sockets[1], 'go out')
        self.assertEqual('square', self.service.server.world.entities[pids[1]].location)
        reply = await self.command(sockets[0], 'look')
        self.assertNotIn('Traveller 1', reply['text'])

    async def test_cross_account_load_and_resume_are_denied_and_body_actor_is_ignored(self):
        alpha, beta, owner = await self.login('Alpha'), await self.login('Beta'), await self.login('Owner')
        alpha_id, beta_id = await self.create(alpha, 'Alpha traveller'), await self.create(beta, 'Beta traveller')
        for client in (beta, owner):
            response = await client.post(self.origin + '/api/character/load',
                json={'player_id': alpha_id, 'account': 'Alpha', 'role': 'Admin'},
                headers={'Origin': self.origin})
            self.assertEqual(403, response.status)
            socket = await self.connect(client)
            reply = await self.command(socket, 'resume', player_id=alpha_id,
                                       account='Alpha', role='Admin')
            self.assertEqual('error', reply['type'])
            self.assertNotIn(alpha_id, self.service.server.clients.values())
        socket = await self.connect(beta, beta_id)
        await self.command(socket, 'go out', player_id=alpha_id, account='Alpha')
        self.assertEqual('square', self.service.server.world.entities[beta_id].location)
        self.assertEqual('inn', self.service.server.world.entities[alpha_id].location)
        response = await beta.get(self.origin + '/api/character/saves')
        self.assertEqual([beta_id], [row['id'] for row in (await response.json())['characters']])

    async def test_live_role_downgrade_and_full_edit_do_not_keep_moderation(self):
        alpha = await self.login('Alpha')
        pid = await self.create(alpha, 'Role tester')
        socket = await self.connect(alpha, pid)
        registered = list(self.credentials)
        self.service.roles.assign('Owner', 'Alpha', ADMIN, registered)
        reply = await self.command(socket, 'dm', operation='roster', request_id='admin')
        self.assertEqual('dm_result', reply['type'])
        for role in (NO_EDIT, FULL_EDIT):
            self.service.roles.assign('Owner', 'Alpha', role, registered)
            reply = await self.command(socket, 'dm', operation='roster', request_id=role)
            self.assertEqual('dm_error', reply['type'])
            self.assertNotIn('players', reply)
        self.assertEqual(set(), self.service.server.host_sockets)
        for command in ('host_auth', 'promote someone', 'hostmap', 'save slots'):
            reply = await self.command(socket, command, request_id='blocked')
            self.assertIn(reply['type'], ('error', 'save_slots'))
            self.assertEqual('blocked', reply['request_id'])

    async def test_revoked_old_session_saves_without_closing_new_session_or_other_players(self):
        alpha, beta = await self.login('Alpha'), await self.login('Beta')
        alpha_id, beta_id = await self.create(alpha, 'Alpha traveller'), await self.create(beta, 'Beta traveller')
        old_socket, beta_socket = await self.connect(alpha, alpha_id), await self.connect(beta, beta_id)
        await self.command(old_socket, 'go out')
        replacement = await self.login('Alpha')  # Real Accounts login revokes Alpha's old cookie.
        new_socket = await self.connect(replacement)
        await self.eventually(lambda: alpha_id not in self.service.server.clients.values())
        self.assertTrue((self.runtime / 'save' / 'world.db').is_file())
        await new_socket.send_json({'command': 'resume', 'player_id': alpha_id})
        await self.receive(new_socket, lambda packet: packet.get('event') == 'character_entered')
        reply = await self.command(new_socket, 'look')
        self.assertIn('Civic Square', reply['text'])
        reply = await self.command(beta_socket, 'look')
        self.assertIn('Travellers Inn', reply['text'])
        self.assertEqual({alpha_id, beta_id}, set(self.service.server.clients.values()))

    async def test_exit_and_idle_timeout_save_and_restart_recovers_owned_character(self):
        alpha = await self.login('Alpha')
        pid = await self.create(alpha, 'Restart traveller')
        socket = await self.connect(alpha, pid)
        await self.command(socket, 'go out')
        reply = await self.command(socket, 'quit')
        self.assertTrue(reply.get('checkpoint_saved'), reply)
        self.assertIn((await socket.receive(timeout=4)).type,
                      (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING))
        await self.eventually(lambda: not self.service.server.clients)
        await self.stop()
        await self.start()
        alpha = await self.login('Alpha')
        response = await alpha.get(self.origin + '/api/character/saves')
        self.assertEqual([pid], [row['id'] for row in (await response.json())['characters']])
        socket = await self.connect(alpha, pid)
        reply = await self.command(socket, 'look')
        self.assertIn('Civic Square', reply['text'])
        await self.command(socket, 'go in')
        adapter = next(ws for ws, actor in self.service.server.clients.items() if actor == pid)
        self.service.server.mmo_activity[adapter] = time.monotonic() - 901
        await self.eventually(lambda: pid not in self.service.server.clients.values())
        durable = persistence.init_db(self.runtime / 'save' / 'world.db', memory=True)
        try:
            self.assertEqual('inn', persistence.load_player(durable, pid, 'host').location)
        finally:
            durable.close()

    async def test_graceful_host_stop_saves_connected_players_before_database_close(self):
        alpha, beta = await self.login('Alpha'), await self.login('Beta')
        alpha_id = await self.create(alpha, 'Shutdown alpha')
        beta_id = await self.create(beta, 'Shutdown beta')
        alpha_socket = await self.connect(alpha, alpha_id)
        beta_socket = await self.connect(beta, beta_id)
        await self.command(alpha_socket, 'go out')
        await self.command(beta_socket, 'get carrot')
        self.assertEqual(2, len(self.service.server.clients))

        async def finish_handshake(socket):
            while True:
                message = await socket.receive(timeout=4)
                if message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING):
                    return
                self.assertEqual(WSMsgType.TEXT, message.type, message)

        # Stop the actual HTTP host while both players are still connected.
        # Reading the close frames completes the real WebSocket handshakes;
        # this deliberately does not call stop(), which closes clients first.
        await asyncio.wait_for(asyncio.gather(self.http.close(),
            finish_handshake(alpha_socket), finish_handshake(beta_socket)), timeout=5)
        self.http = None
        self.assertEqual({}, self.service.server.clients)
        self.assertEqual(set(), self.service.play_tasks)
        durable = persistence.init_db(self.runtime / 'save' / 'world.db', memory=True)
        try:
            self.assertEqual('square', persistence.load_player(durable, alpha_id, 'host').location)
            self.assertEqual(['carrot'], persistence.load_player(durable, beta_id, 'host').inventory)
        finally:
            durable.close()
        await self.stop()  # Only now release the already-closed client objects.
        await self.start()
        for name, pid in (('Alpha', alpha_id), ('Beta', beta_id)):
            client = await self.login(name)
            response = await client.get(self.origin + '/api/character/saves')
            self.assertEqual([pid], [row['id'] for row in (await response.json())['characters']])
            await self.connect(client, pid)
        self.assertEqual([], self.service.server.world.rooms['inn'].items)
        self.assertEqual('square', self.service.server.world.entities[alpha_id].location)
        self.assertEqual(['carrot'], self.service.server.world.entities[beta_id].inventory)

    async def test_http_origin_identity_editor_and_role_boundaries_are_closed(self):
        anonymous = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.clients.append(anonymous)
        response = await anonymous.get(self.origin + '/api/config')
        self.assertEqual(403, response.status)
        alpha = await self.login('Alpha')
        response = await alpha.post(self.origin + '/api/character/create',
            json={'first_name': 'Forged origin'}, headers={'Origin': 'https://other.invalid'})
        self.assertEqual(403, response.status)
        with self.assertRaises(WSServerHandshakeError) as denied:
            await alpha.ws_connect(self.origin + '/ws', headers={'Origin': 'https://other.invalid'})
        self.assertEqual(403, denied.exception.status)
        for role in (NO_EDIT, FULL_EDIT, ADMIN):
            self.service.roles.assign('Owner', 'Alpha', role, list(self.credentials))
            for path in ('/api/editor/games', '/api/save-slots/open', '/api/character/delete'):
                response = await alpha.post(self.origin + path, json={}, headers={'Origin': self.origin})
                self.assertEqual(403, response.status, (role, path))
            response = await alpha.post(self.origin + '/roles',
                data={'name': 'Beta', 'role': ADMIN}, headers={'Origin': self.origin})
            self.assertEqual(403, response.status)
        response = await alpha.get(self.origin + '/healthz')
        self.assertIs((await response.json())['public_mmo'], False)
        self.service.server.mmo_pending_saves = {'failed-exit-checkpoint'}
        response = await alpha.get(self.origin + '/healthz')
        self.assertEqual(503, response.status)
        self.assertEqual({'status': 'save-degraded', 'public_mmo': False,
                          'pending_exit_saves': 1}, await response.json())
        self.service.server.mmo_pending_saves.clear()

    async def test_staging_requires_opt_in_empty_data_and_single_writer(self):
        with patch.dict('os.environ', {'EXPANSE_SHARED_STAGING': ''}):
            with self.assertRaisesRegex(ValueError, 'opt into'):
                shared_staging.make_app(self.source, self.root / 'other', auth=self.auth)
        populated = self.root / 'existing-save'
        populated.mkdir()
        sentinel = populated / 'world.db'
        sentinel.write_bytes(b'KEEP EXISTING SAVE')
        with self.assertRaisesRegex(ValueError, 'existing data'):
            shared_staging.make_app(self.source, populated, auth=self.auth)
        self.assertEqual(b'KEEP EXISTING SAVE', sentinel.read_bytes())
        with self.assertRaises(Exception):
            shared_staging.make_app(self.source, self.runtime, auth=self.auth)
        client = await self.login('Alpha')
        pid = await self.create(client, 'Still running')
        await self.command(await self.connect(client, pid), 'look')

    async def test_marked_runtime_symlinks_are_refused_before_opening_external_data(self):
        await self.stop()
        outside = self.root / 'outside-save'
        outside.mkdir()
        sentinel = outside / 'world.db'
        sentinel.write_bytes(b'NEVER OPEN THIS DATABASE')
        (self.runtime / 'save').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            shared_staging.make_app(self.source, self.runtime, auth=self.auth)
        self.assertEqual(b'NEVER OPEN THIS DATABASE', sentinel.read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
