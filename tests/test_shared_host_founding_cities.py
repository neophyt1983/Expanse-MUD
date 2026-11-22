"""Local-only HTTP/WebSocket acceptance on a pinned Founding Cities archive.

Set EXPANSE_TEST_FOUNDING_CITIES to the extracted .expanse file inside the
world download. All accounts, mutable game state and saves are temporary.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from aiohttp import WSMsgType
from engine import loader, persistence
from server import game_server
import test_shared_host_transport as transport

WORLD_VAR = 'EXPANSE_TEST_FOUNDING_CITIES'
WORLD_HASHES = {
    'f14377c737e936fb8341bee563e0a94b40a9ec63d07c19f9d3035e8292f6ede8',  # RC2/RC3
    'dd83185c01a160f0b661a877ee11af15be6b993047f2477d1cc01ea3bb8797b9',  # RC4
    '85a89a2f94017bcf988803fbc29d18a79b0b441abf35a0281ca42004a492ec72',  # 1.10.0
}


@unittest.skipUnless(os.environ.get(WORLD_VAR), 'Set EXPANSE_TEST_FOUNDING_CITIES to the Founding Cities archive.')
class FoundingCitiesTransport(unittest.IsolatedAsyncioTestCase):
    start = transport.SharedHostTransportTests.start
    stop = transport.SharedHostTransportTests.stop
    login = transport.SharedHostTransportTests.login
    connect = transport.SharedHostTransportTests.connect
    command = transport.SharedHostTransportTests.command

    async def receive(self, socket, predicate):
        for _ in range(120):
            message = await socket.receive(timeout=30)
            self.assertEqual(WSMsgType.TEXT, message.type, message)
            packet = json.loads(message.data)
            if predicate(packet):
                return packet
        self.fail('Expected WebSocket reply did not arrive.')

    def archive_digest(self):
        with self.source.open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()

    async def asyncSetUp(self):
        self.source = Path(os.environ[WORLD_VAR]).resolve(strict=True)
        self.expected_digest = self.archive_digest()
        self.assertIn(self.expected_digest, WORLD_HASHES)
        temporary = tempfile.TemporaryDirectory(prefix='expanse-founding-cities-')
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name) / 'runtime'
        self.credentials = {name: 'private-qa-' + name for name in ('Owner', 'Alpha', 'Beta')}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {
            'EXPANSE_SHARED_STAGING': '1',
            'EXPANSE_OWNER_NAME': 'Owner',
            'EXPANSE_OWNER_PASSWORD': self.credentials['Owner'],
            'EXPANSE_OWNER_EXPIRES_AT': '',
            'EXPANSE_GUESTS_JSON': json.dumps([
                {'name': name, 'password': self.credentials[name]} for name in ('Alpha', 'Beta')]),
        }))
        for module, attr in (
            (loader, 'GAME_DIR'), (loader, 'DATA_DIR'), (loader, 'GAMES_DIR'),
            (loader, 'WORLD_UPDATE_TEMPLATES'), (persistence, 'DB_PATH'),
            (game_server, 'SAVE_DIR'), (game_server, 'WORLD_STATE_PATH'),
        ):
            stack.enter_context(patch.object(module, attr, getattr(module, attr)))
        self.clients, self.websockets, self.http = [], [], None
        self.addAsyncCleanup(self.stop)
        await self.start()

    async def create(self, client, first):
        payload = dict(first_name=first, race='human', sex='male',
                       faction='roadkeepers', starting_city='dawnwatch')
        async with client.post(self.origin + '/api/character/create', json=payload,
                               headers={'Origin': self.origin}) as response:
            self.assertEqual(200, response.status, await response.text())
            created = await response.json()
        self.assertEqual('dawnwatch', created['starting_city'])
        self.assertEqual('emberhollow_inn', created['start_room'])
        self.assertIsNone(created['class'])
        return created['player_id']

    async def move_to_square(self, socket, pid):
        await socket.send_json({'command': 'go south', 'movement_id': pid})
        reply = await self.receive(socket, lambda msg: msg.get('movement_id') == pid)
        self.assertEqual('emberhollow_square', self.service.server.world.entities[pid].location, reply)

    async def test_classless_arrival_finite_trade_and_durable_reconnect(self):
        alpha, beta = await self.login('Alpha'), await self.login('Beta')
        async with alpha.get(self.origin + '/api/character/options') as response:
            self.assertEqual(200, response.status)
            options = await response.json()
        self.assertTrue(options['classless_start'])
        self.assertEqual([], options['classes'])
        self.assertTrue(options['choose_starting_city'])
        self.assertEqual(8, len({city['id'] for city in options['starting_cities']}))
        a, b = await self.create(alpha, 'Alphatest'), await self.create(beta, 'Betatest')
        # Alpha's socket can queue a map as soon as it joins. Admit the peer first.
        sb = await self.connect(beta, b)
        sa = await self.connect(alpha, a)
        w = self.service.server.world
        self.assertEqual('Wild Lands — Founding Cities', w.metadata['name'])
        await sa.send_json({'command': 'map'})
        room_map = await self.receive(sa, lambda msg: msg.get('type') == 'map')
        self.assertIn('Betatest', json.dumps(room_map['location']['players']))
        await sa.send_json({'command': 'chat founding-cities-proof'})
        broadcast = await self.receive(sb, lambda msg: 'founding-cities-proof' in msg.get('text', ''))
        self.assertIn('Alphatest', broadcast['text'])

        item = 'bread'
        room = w.rooms['emberhollow_inn']
        before = [w.entities[pid].inventory.count(item) for pid in (a, b)]
        floor_before = room.items.count(item)
        self.assertGreater(floor_before, 0)
        await sa.send_json({'command': 'get bread'})
        pickup = await self.receive(sa, lambda msg: 'source_quests' in msg or msg.get('type') == 'error')
        self.assertEqual(before[0] + 1, w.entities[a].inventory.count(item), pickup)
        self.assertEqual(floor_before - 1, room.items.count(item))
        await sa.send_json({'command': f'offer {b} {item} 1 0'})
        offer = await self.receive(sb, lambda msg: msg.get('type') == 'trade_offer')
        await sb.send_json({'command': 'accept_offer ' + offer['id']})
        reply = await self.receive(sb, lambda msg: 'Exchange completed.' in msg.get('text', '') or msg.get('type') == 'error')
        self.assertIn('Exchange completed.', reply.get('text', ''), reply)
        expected = (before[0], before[1] + 1)
        self.assertEqual(expected, tuple(w.entities[pid].inventory.count(item) for pid in (a, b)))

        async with beta.post(self.origin + '/api/character/load', json={'player_id': a},
                             headers={'Origin': self.origin}) as denied:
            self.assertEqual(403, denied.status)
        await self.move_to_square(sa, a)
        await sa.send_json({'command': 'quit'})
        saved = await self.receive(sa, lambda msg: msg.get('type') == 'saved_exit')
        self.assertTrue(saved.get('checkpoint_saved'), saved)
        await self.move_to_square(sb, b)
        adapter = next(sock for sock, pid in self.service.server.clients.items() if pid == b)
        self.service.server.mmo_activity[adapter] = time.monotonic() - 901
        while (await sb.receive(timeout=30)).type not in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            pass
        await self.stop()
        await self.start()
        for account, pid, count in zip(('Alpha', 'Beta'), (a, b), expected):
            client = await self.login(account)
            await self.connect(client, pid)
            player = self.service.server.world.entities[pid]
            self.assertEqual('emberhollow_square', player.location)
            self.assertEqual(count, player.inventory.count(item))
        self.assertEqual(floor_before - 1, self.service.server.world.rooms['emberhollow_inn'].items.count(item))
        self.assertEqual(self.expected_digest, self.archive_digest())
