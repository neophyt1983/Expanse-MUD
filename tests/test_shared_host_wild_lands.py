"""Opt-in real Wild Lands shared-host integration, always using temporary saves."""
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
from engine import exchange, loader, persistence
from server import game_server, shared_staging
import test_shared_host_transport as transport

WORLD_VAR = 'EXPANSE_MMO_TEST_WILD_LANDS'
WORLD_HASH = '65ebebbe5bae932464ab2490c8ee87defc5c01178ef4d51fae79f2bfb3b6660c'

def file_hash(path):
    with path.open('rb') as data:
        return hashlib.file_digest(data, 'sha256').hexdigest()


class ArchiveStagingTests(unittest.TestCase):
    def test_archive_import_uses_compatible_id_without_renaming_legacy_world(self):
        with tempfile.TemporaryDirectory(prefix='expanse-staging-archive-') as tmp:
            root = Path(tmp)
            game = root / 'source' / 'minimal'
            game.mkdir(parents=True)
            room = {'id': 'inn', 'name': 'Inn', 'description': 'An inn.', 'exits': {}}
            (game / 'metadata.json').write_text(json.dumps({'name':'Minimal', 'start_room':'inn'}))
            (game / 'rooms.json').write_text(json.dumps([room]))
            archive = root / 'minimal.expanse'
            ok, note = exchange.export_game(game.name, game.parent, archive)
            self.assertTrue(ok, note)
            source_digest = file_hash(archive)
            runtime = root / 'runtime'
            runtime.mkdir()
            fresh = shared_staging.copy_world(archive, runtime)
            self.assertEqual('shared_staging', fresh.name)
            self.assertEqual(fresh, shared_staging.copy_world(archive, runtime))
            legacy = root / 'legacy' / 'games' / 'shared-staging'
            legacy.mkdir(parents=True)
            sentinel = json.dumps([room]).encode()
            (legacy / 'rooms.json').write_bytes(sentinel)
            self.assertEqual(legacy, shared_staging.copy_world(archive, legacy.parent.parent))
            self.assertEqual(sentinel, (legacy / 'rooms.json').read_bytes())
            self.assertFalse((legacy.parent / 'shared_staging').exists())
            self.assertEqual(source_digest, file_hash(archive))


@unittest.skipUnless(os.environ.get(WORLD_VAR), f'Set {WORLD_VAR} to the released Wild Lands 1.9.16 archive.')
class WildLandsTransportTests(unittest.IsolatedAsyncioTestCase):
    # Use the same real requests and lifecycle as the synthetic fixture.
    start = transport.SharedHostTransportTests.start
    stop = transport.SharedHostTransportTests.stop
    login = transport.SharedHostTransportTests.login
    connect = transport.SharedHostTransportTests.connect
    command = transport.SharedHostTransportTests.command

    async def receive(self, socket, predicate):
        for _ in range(120):
            message = await socket.receive(timeout=25)
            self.assertEqual(WSMsgType.TEXT, message.type, message)
            packet = json.loads(message.data)
            if predicate(packet):
                return packet
        self.fail('Expected WebSocket reply did not arrive.')

    async def asyncSetUp(self):
        self.source = Path(os.environ[WORLD_VAR]).resolve(strict=True)
        self.assertEqual(WORLD_HASH, file_hash(self.source))
        tmp = tempfile.TemporaryDirectory(prefix='expanse-shared-wild-lands-')
        self.addCleanup(tmp.cleanup)
        self.runtime = Path(tmp.name) / 'runtime'
        self.credentials = {name: 'disposable-wild-lands-' + name for name in ('Owner', 'Alpha', 'Beta')}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict('os.environ', {
            'EXPANSE_SHARED_STAGING': '1',
            'EXPANSE_OWNER_NAME': 'Owner',
            'EXPANSE_OWNER_PASSWORD': self.credentials['Owner'],
            'EXPANSE_OWNER_EXPIRES_AT': '',
            'EXPANSE_GUESTS_JSON': json.dumps([
                {'name': name, 'password': password}
                for name, password in self.credentials.items() if name != 'Owner']),
        }))
        for obj, attr in ((loader, 'GAME_DIR'), (loader, 'DATA_DIR'),
                          (loader, 'GAMES_DIR'), (loader, 'WORLD_UPDATE_TEMPLATES'),
                          (persistence, 'DB_PATH'), (game_server, 'SAVE_DIR'),
                          (game_server, 'WORLD_STATE_PATH')):
            stack.enter_context(patch.object(obj, attr, getattr(obj, attr)))
        self.clients, self.websockets, self.http = [], [], None
        self.addAsyncCleanup(self.stop)
        await self.start()

    async def create(self, client, name):
        async with client.post(self.origin + '/api/character/create',
            json={'first_name': name, 'race': 'human', 'class': 'fighter',
                  'sex': 'male', 'faction': 'good_guys'},
            headers={'Origin': self.origin}) as response:
            self.assertEqual(200, response.status, await response.text())
            return (await response.json())['player_id']

    async def test_two_real_world_accounts_trade_move_and_resume_after_automatic_checkpoint(self):
        alpha, beta = await self.login('Alpha'), await self.login('Beta')
        a = await self.create(alpha, 'Alphatest')
        b = await self.create(beta, 'Betatest')
        sa, sb = await self.connect(alpha, a), await self.connect(beta, b)
        w = self.service.server.world
        self.assertIn('Wild Lands', w.metadata['name'])
        self.assertGreater(len(w.rooms), 32000)
        self.assertEqual('emberhollow_inn', w.entities[a].location)
        self.assertEqual(w.entities[a].location, w.entities[b].location)
        await sa.send_json({'command':'map'})
        packet = await self.receive(sa, lambda msg:msg.get('type') == 'map')
        self.assertIn('Betatest', json.dumps(packet['location']['players']))
        await sa.send_json({'command': 'chat wild-lands-shared-proof'})
        told = await self.receive(sb, lambda msg: 'wild-lands-shared-proof' in msg.get('text', ''))
        self.assertIn('Alphatest', told['text'])
        item = 'lw_ration'
        before = tuple(w.entities[pid].inventory.count(item) for pid in (a,b))
        self.assertGreater(before[0],0)
        await sa.send_json({'command': f'offer {b} {item} 1 0'})
        offer = await self.receive(sb, lambda msg:msg.get('type') == 'trade_offer')
        reply = await self.command(sb, 'accept_offer ' + offer['id'])
        self.assertIn('Exchange completed.',reply.get('text',''),reply)
        expected = (before[0]-1,before[1]+1)
        self.assertEqual(expected, tuple(w.entities[pid].inventory.count(item) for pid in (a,b)))
        async with beta.post(self.origin + '/api/character/load',
            json={'player_id': a},headers={'Origin':self.origin}) as denied:
            self.assertEqual(403,denied.status)
        await sa.send_json({'command':'go south','movement_id':'fixture-alpha-south'})
        response = await self.receive(sa,lambda msg:msg.get('movement_id')=='fixture-alpha-south')
        self.assertEqual('emberhollow_square',w.entities[a].location,response)
        await sb.send_json({'command':'map'})
        after = await self.receive(sb,lambda msg:msg.get('type')=='map'
            and 'Alphatest' not in json.dumps(msg['location']['players']))
        self.assertEqual('emberhollow_inn',after['location']['id'])
        await sa.send_json({'command':'quit'})
        ack = await self.receive(sa,lambda msg:msg.get('type')=='saved_exit')
        self.assertTrue(ack.get('checkpoint_saved'),ack)
        # Move Beta *after* Alpha's checkpoint so idle persistence cannot pass
        # merely because Alpha already saved both characters' old positions.
        await sb.send_json({'command':'go south','movement_id':'fixture-beta-south'})
        moved = await self.receive(sb,lambda msg:msg.get('movement_id')=='fixture-beta-south')
        self.assertEqual('emberhollow_square',w.entities[b].location,moved)
        # Simulate elapsed idle time in the disposable test, then wait for actual lifecycle close.
        adapter = next(s for s,pid in self.service.server.clients.items() if pid == b)
        self.service.server.mmo_activity[adapter] = time.monotonic() - 901
        while True:
            message = await sb.receive(timeout=25)
            if message.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                break
        db = persistence.init_db(self.runtime / 'save' / 'world.db', memory=True)
        try:
            saved = [persistence.load_player(db,pid,'host') for pid in (a,b)]
            self.assertEqual(['emberhollow_square']*2,[p.location for p in saved])
            self.assertEqual(expected,tuple(p.inventory.count(item) for p in saved))
        finally:
            db.close()
        await self.stop()
        await self.start()
        for name,pid,room,count in zip(('Alpha','Beta'),(a,b),
                ('emberhollow_square',)*2,expected):
            client = await self.login(name)
            await self.connect(client,pid)
            restored = self.service.server.world.entities[pid]
            self.assertEqual(room,restored.location)
            self.assertEqual(count,restored.inventory.count(item))
        self.assertEqual(WORLD_HASH,file_hash(self.source))
