"""Host/manual and MMO/automatic checkpoints in disposable storage.

These checks exercise GameServer's real RAM staging and paired DB/world save
code. They neither read nor write a player's installed game or Render data.
Run: python -m unittest discover -s tests -p 'test_shared_host_persistence.py'
"""
from contextlib import ExitStack, suppress
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from engine import living, loader, persistence, save_transaction
from engine.core import Entity, Room, World
from server import game_server
from server.mmo_access import MMOAuthorizer
from server.mmo_ownership import MMOOwnership
from server.mmo_roles import MMORoles


class RecordedSocket:
    """Drive the real disconnect cleanup without requiring a network listener."""

    remote_address = ('127.0.0.1', 12345)

    def __init__(self, packets):
        self.requests = packets
        self.replies = []
        self.closed = False

    async def send(self, raw):
        self.replies.append(json.loads(raw))

    async def close(self, **kwargs):
        self.closed = True

    async def __aiter__(self):
        for packet in self.requests:
            yield json.dumps(packet)


class SharedHostPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='expanse-shared-save-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / 'shared-staging'
        self.games = self.root / 'games'
        self.content = self.games / 'fixture'
        self.content.mkdir(parents=True)
        self.database = self.root / 'world.db'
        self.state_file = self.root / 'world_state_host.json'
        self.production = self.directory / 'existing-installation'
        for relative, content in {
            'accounts/accounts.sqlite3': b'Existing account data: do not migrate',
            'solo/save/world.db': b'Existing solo database: do not touch',
            'solo/save/world_state_single.json': b'{"minute":1234}',
            'settings.json': b'{"tile_size":24}',
        }.items():
            target = self.production / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.original_production = self.production_bytes()
        self.servers = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for owner, name, value in (
            (game_server, 'build_world', self.new_world),
            (game_server, 'SAVE_DIR', self.root),
            (game_server, 'WORLD_STATE_PATH', self.state_file),
            (loader, 'GAMES_DIR', self.games),
            (loader, 'DATA_DIR', self.content),
            (loader, 'GAME_DIR', self.content),
            (persistence, 'DB_PATH', self.database),
        ):
            self.stack.enter_context(patch.object(owner, name, value))
        self.addCleanup(self.close_servers)

    def production_bytes(self):
        return {str(path.relative_to(self.production)): path.read_bytes()
                for path in self.production.rglob('*') if path.is_file()}

    def tearDown(self):
        self.assertEqual(self.original_production, self.production_bytes(),
                         'Shared staging must leave existing accounts, solo saves and settings untouched.')

    def close_servers(self):
        for server in self.servers:
            for name in ('db', 'checkpoint_db'):
                with suppress(sqlite3.Error):
                    getattr(server, name).close()

    def new_world(self):
        world = World()
        world.metadata = {'living_world': True, 'society': False,
                          'start_room': 'inn', 'start_minute': 375,
                          'max_players': 4}
        world.rules = {}
        world.start_room = 'inn'
        world.game_dir = self.content
        world.room_details = {'inn': {'id': 'inn'}, 'square': {'id': 'square'}}
        world.add_room(Room('inn', 'Travellers Inn', 'A public meeting place.',
                            exits={'out': 'square'}, items=['carrot']))
        world.add_room(Room('square', 'Civic Square', 'A public square.',
                            exits={'in': 'inn'}))
        world.items = {'carrot': {'id': 'carrot', 'name': 'Garden carrot', 'type': 'food'}}
        return world

    def server(self, mode='host'):
        server = game_server.GameServer(mode=mode)
        self.servers.append(server)
        return server

    def players(self, server):
        result = []
        for index, ident in enumerate(('alpha', 'beta'), 1):
            player = Entity(ident, ident.title(), 30, 30, 2, 1,
                            gold=index * 10, is_player=True,
                            progress={'world_slug': 'fixture'})
            server.world.add_entity(player, 'inn')
            result.append(player)
        return result

    def assert_no_checkpoint(self):
        self.assertFalse(self.database.exists(), 'Routine activity must not publish a player checkpoint.')
        self.assertFalse(self.state_file.exists(), 'Routine activity must not publish a world checkpoint.')

    def authenticate_mmo(self, server, socket):
        """Model server-issued sessions and persistent ownership, never packet names."""
        sessions = {'session-alpha': 'PlayerAlpha', 'session-beta': 'PlayerBeta'}
        roles = MMORoles(self.root, 'MMOOwner')
        ownership = MMOOwnership(self.root)
        ownership.claim('PlayerAlpha', 'alpha')
        ownership.claim('PlayerBeta', 'beta')
        server.mmo_authorizer = MMOAuthorizer(sessions.get, roles, ownership, owner='MMOOwner')
        server.mmo_sessions = {socket: 'session-alpha'}
        server.mmo_save_on_exit = True
        return sessions

    def test_explicit_save_publishes_every_player_and_matching_world_for_restart(self):
        server = self.server()
        alpha, beta = self.players(server)
        alpha.inventory.append('carrot')
        server.world.rooms['inn'].items.remove('carrot')
        server.world.item_claims = {'inn': {'carrot': 1}}
        server.world.shop_state = {'merchant': {'carrot': 2}}
        server.world.killed_npcs.add('fallen-bandit')
        living.state(server.world)['minute'] = 417
        server.world.move_entity(beta.id, 'square')

        server._save_players_and_world(alpha.id)
        self.assertTrue(self.database.is_file())
        self.assertTrue(self.state_file.is_file())
        restarted = self.server()
        saved_alpha = persistence.load_player(restarted.db, alpha.id, 'host')
        saved_beta = persistence.load_player(restarted.db, beta.id, 'host')
        self.assertEqual(['carrot'], saved_alpha.inventory)
        self.assertEqual('square', saved_beta.location)
        self.assertEqual(20, saved_beta.gold)
        self.assertEqual([], restarted.world.rooms['inn'].items)
        self.assertEqual({'inn': {'carrot': 1}}, restarted.world.item_claims)
        self.assertEqual({'merchant': {'carrot': 2}}, restarted.world.shop_state)
        self.assertEqual({'fallen-bandit'}, restarted.world.killed_npcs)
        self.assertEqual(417, living.state(restarted.world)['minute'])
        self.assertEqual({'alpha', 'beta'}, {row[0] for row in restarted.db.execute(
            'SELECT id FROM players WHERE saved_at IS NOT NULL')})

    def test_routine_stage_and_host_tick_are_memory_only_and_restart_discards_them(self):
        server = self.server()
        alpha, beta = self.players(server)
        server.clients[object()] = alpha.id
        server._stage_players_and_world()
        beta.gold = 999
        living.state(server.world)['minute'] = 999
        server._autosave_host_tick()
        self.assertEqual(999, persistence.load_player(server.db, beta.id, 'host').gold)
        self.assert_no_checkpoint()
        restarted = self.server()
        self.assertIsNone(persistence.load_player(restarted.db, alpha.id, 'host'))
        self.assertIsNone(persistence.load_player(restarted.db, beta.id, 'host'))
        self.assertNotEqual(999, living.state(restarted.world)['minute'])
        self.assert_no_checkpoint()

    async def test_real_disconnect_stages_without_publishing_a_manual_save(self):
        server = self.server()
        alpha, beta = self.players(server)
        token = 'disposable-test-character-token'
        alpha.progress['delete_token_hash'] = hashlib.sha256(token.encode()).hexdigest()
        server._stage_players_and_world()
        socket = RecordedSocket([{'command': 'resume alpha', 'auth_token': token},
                                 {'command': 'go out'}])
        await server.handle(socket)
        self.assertTrue(any(packet.get('event') == 'character_entered'
                            and packet.get('player_id') == alpha.id
                            for packet in socket.replies), socket.replies)
        self.assertNotIn(socket, server.clients)
        self.assertNotIn(alpha.id, server.world.entities)
        self.assertEqual('square', persistence.load_player(server.db, alpha.id, 'host').location)
        self.assert_no_checkpoint()

    async def test_single_player_disconnect_remains_manual(self):
        server = self.server(mode='single')
        alpha, beta = self.players(server)
        server._stage_players_and_world()
        socket = RecordedSocket([{'command': 'resume alpha'}, {'command': 'go out'}])
        await server.handle(socket)
        self.assertTrue(any(packet.get('event') == 'character_entered'
                            for packet in socket.replies), socket.replies)
        self.assertEqual('square', persistence.load_player(server.db, alpha.id, 'single').location)
        self.assert_no_checkpoint()

    async def test_authenticated_mmo_disconnect_saves_both_players_and_shared_world(self):
        server = self.server()
        alpha, beta = self.players(server)
        beta.gold = 47
        alpha.inventory.append('carrot')
        server.world.rooms['inn'].items.clear()
        server.world.item_claims = {'inn': {'carrot': 1}}
        living.state(server.world)['minute'] = 417
        socket = RecordedSocket([{'command': 'resume alpha'}, {'command': 'go out'}])
        self.authenticate_mmo(server, socket)

        await server.handle(socket)
        self.assertNotIn(alpha.id, server.world.entities)
        self.assertTrue(self.database.is_file(), 'MMO disconnect must publish a shared checkpoint.')
        self.assertTrue(self.state_file.is_file())
        restarted = self.server()
        saved_alpha = persistence.load_player(restarted.db, alpha.id, 'host')
        saved_beta = persistence.load_player(restarted.db, beta.id, 'host')
        self.assertEqual('square', saved_alpha.location)
        self.assertEqual(['carrot'], saved_alpha.inventory)
        self.assertEqual(47, saved_beta.gold)
        self.assertEqual([], restarted.world.rooms['inn'].items)
        self.assertEqual({'inn': {'carrot': 1}}, restarted.world.item_claims)
        self.assertEqual(417, living.state(restarted.world)['minute'])

    async def test_expired_mmo_session_still_saves_its_previously_authenticated_actor(self):
        server = self.server()
        alpha, beta = self.players(server)

        class ExpiringSocket(RecordedSocket):
            async def __aiter__(socket):
                yield json.dumps({'command': 'resume alpha'})
                yield json.dumps({'command': 'go out'})
                sessions.pop('session-alpha')
                yield json.dumps({'command': 'look'})

        socket = ExpiringSocket([])
        sessions = self.authenticate_mmo(server, socket)
        await server.handle(socket)
        self.assertTrue(socket.closed, 'A revoked session must be disconnected.')
        self.assertNotIn(socket, server.clients)
        restarted = self.server()
        self.assertEqual('square', persistence.load_player(restarted.db, alpha.id, 'host').location)
        self.assertIsNotNone(persistence.load_player(restarted.db, beta.id, 'host'))

    async def test_explicit_mmo_quit_saves_once_before_acknowledging_exit(self):
        server = self.server()
        alpha, beta = self.players(server)
        socket = RecordedSocket([{'command': 'resume alpha'}, {'command': 'go out'},
                                 {'command': 'quit'}])
        self.authenticate_mmo(server, socket)
        with patch.object(server, '_save_players_and_world', wraps=server._save_players_and_world) as publish:
            await server.handle(socket)
        self.assertTrue(socket.closed)
        self.assertTrue(self.database.is_file())
        self.assertEqual(1, publish.call_count, 'Successful explicit MMO exit must not double-save in cleanup.')
        self.assertTrue(any(packet['type'] == 'saved_exit' for packet in socket.replies), socket.replies)
        restarted = self.server()
        self.assertEqual('square', persistence.load_player(restarted.db, alpha.id, 'host').location)

    async def test_failed_mmo_exit_save_retains_unsaved_actor_and_previous_checkpoint(self):
        server = self.server()
        alpha, beta = self.players(server)
        server._save_players_and_world(alpha.id)
        original_database = self.database.read_bytes()
        original_state = self.state_file.read_bytes()
        socket = RecordedSocket([{'command': 'resume alpha'}, {'command': 'go out'}])
        self.authenticate_mmo(server, socket)
        real_write = save_transaction.write_atomic

        def failed_write(path, text):
            if Path(path) == self.state_file and not failed_write.failed:
                failed_write.failed = True
                raise OSError('Injected MMO exit publication failure')
            return real_write(path, text)

        failed_write.failed = False
        with patch.object(save_transaction, 'write_atomic', failed_write):
            with patch('sys.stdout', new=io.StringIO()):
                await server.handle(socket)
        self.assertIn(alpha.id, server.world.entities,
                      'Failed MMO exit saves must retain unsaved gameplay for recovery.')
        self.assertEqual('square', server.world.entities[alpha.id].location)
        self.assertEqual(original_database, self.database.read_bytes())
        self.assertEqual(original_state, self.state_file.read_bytes())
        restarted = self.server()
        self.assertEqual('inn', persistence.load_player(restarted.db, alpha.id, 'host').location)

    def test_failed_world_publish_preserves_paired_checkpoint_and_restart(self):
        server = self.server()
        alpha, beta = self.players(server)
        living.state(server.world)['minute'] = 417
        server._save_players_and_world(alpha.id)
        original_database = self.database.read_bytes()
        original_state = self.state_file.read_bytes()
        alpha.gold = 999
        beta.inventory.append('carrot')
        server.world.rooms['inn'].items.clear()
        living.state(server.world)['minute'] = 888
        real_write = save_transaction.write_atomic

        def failed_write(path, text):
            # Fail the new world write once. Recovery must still be able to
            # restore the preceding generation from the transaction journal.
            if Path(path) == self.state_file and not failed_write.failed:
                failed_write.failed = True
                raise OSError('Injected world publication failure')
            return real_write(path, text)

        failed_write.failed = False
        with patch.object(save_transaction, 'write_atomic', failed_write):
            with patch('sys.stdout', new=io.StringIO()):
                with self.assertRaisesRegex(OSError, 'previous save preserved'):
                    server._save_players_and_world(alpha.id)
        self.assertEqual(original_database, self.database.read_bytes())
        self.assertEqual(original_state, self.state_file.read_bytes())
        restarted = self.server()
        self.assertEqual(10, persistence.load_player(restarted.db, alpha.id, 'host').gold)
        self.assertEqual([], persistence.load_player(restarted.db, beta.id, 'host').inventory)
        self.assertEqual(['carrot'], restarted.world.rooms['inn'].items)
        self.assertEqual(417, living.state(restarted.world)['minute'])

    def test_corrupt_recovery_journal_refuses_startup_and_preserves_all_files(self):
        server = self.server()
        alpha, beta = self.players(server)
        server._save_players_and_world(alpha.id)
        journal = self.state_file.with_name(self.state_file.name + '.save-journal')
        journal.write_bytes(b'{"invalid": "incomplete journal"}')
        before = {path: path.read_bytes() for path in (self.database, self.state_file, journal)}
        with self.assertRaisesRegex(ValueError, 'recovery journal'):
            self.server()
        self.assertEqual(before, {path: path.read_bytes() for path in before})


if __name__ == '__main__':
    unittest.main()
