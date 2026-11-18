"""Exact reviewed world-media negotiation, independent of live host access."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from engine import loader, persistence, public_media
from server import game_server
from test_player_list_transport import fixture, Socket


NAME = 'assets/terrain/tiles.png'
BODY = b'reviewed presentation fixture'
REVIEWED = {NAME: (len(BODY), hashlib.sha256(BODY).hexdigest(), 'image/png')}


class MediaSnapshot(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='expanse-public-media-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / NAME
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(BODY)
        self.registry = public_media.PublicMedia(self.root)
        self.native_descriptors = public_media._directory_descriptors()
        self.patch = patch.object(public_media, 'PUBLIC_PRESENTATION', REVIEWED)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_exact_reviewed_bytes_and_unchanged_identity_avoid_rehash(self):
        with patch.object(public_media.os, 'scandir', side_effect=AssertionError('Media directory scan')):
            result = self.registry.info(NAME)
        self.assertEqual({'scope': 'public-presentation', 'sha256': REVIEWED[NAME][1],
                          'size': len(BODY), 'mime': 'image/png'}, result)
        if self.native_descriptors:
            with patch.object(public_media.os, 'read', side_effect=AssertionError('Unexpected rehash')):
                self.assertEqual(result, self.registry.info(NAME))
        else:
            # Portable hosts cannot trust Windows creation timestamps as file
            # versions, so every negotiation must verify the bytes again.
            with patch.object(public_media.hashlib, 'sha256', wraps=hashlib.sha256) as checksum:
                self.assertEqual(result, self.registry.info(NAME))
                checksum.assert_called_once()
        self.assertEqual(1, len(self.registry._checked))

    def test_same_size_changed_bytes_and_new_files_never_auto_publish(self):
        self.assertIsNotNone(self.registry.info(NAME))
        before = self.path.stat()
        self.path.write_bytes(b'X' * len(BODY))
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertIsNone(self.registry.info(NAME))
        unrelated = self.root / 'assets/terrain/new.png'
        unrelated.write_bytes(BODY)
        with patch.object(public_media.os, 'open', side_effect=AssertionError('Unknown path was opened')):
            for name in ('assets/terrain/new.png', '../secret.json', '/etc/passwd',
                         'assets/updates/private.json', ['not', 'text'], None):
                self.assertIsNone(self.registry.info(name))
        self.assertEqual(1, len(self.registry._checked))

    def test_oversized_file_is_rejected_without_reading(self):
        self.path.write_bytes(BODY + b'additional unreviewed bytes')
        with patch.object(public_media.os, 'read', side_effect=AssertionError('Oversized file was read')):
            self.assertIsNone(self.registry.info(NAME))

    def test_symlink_file_directory_and_root_are_transient_on_both_access_paths(self):
        def link(path, target, *, directory=False):
            try:
                path.symlink_to(target, target_is_directory=directory)
            except OSError as error:
                self.skipTest('Creating symbolic links is unavailable: ' + str(error))

        access_paths = (False, True) if self.native_descriptors else (True,)
        original = self.root / 'original.png'
        self.path.rename(original)
        link(self.path, original)
        for portable in access_paths:
            with patch.object(public_media, '_directory_descriptors', return_value=not portable):
                self.assertIsNone(self.registry.info(NAME))
        self.path.unlink()
        self.path.write_bytes(BODY)
        target = self.root / 'alternate'
        self.path.parent.rename(target)
        link(self.path.parent, target, directory=True)
        for portable in access_paths:
            with patch.object(public_media, '_directory_descriptors', return_value=not portable):
                self.assertIsNone(self.registry.info(NAME))
        linked_root = self.root / 'linked-world'
        link(linked_root, self.root, directory=True)
        with patch.object(public_media, '_directory_descriptors', return_value=False):
            self.assertIsNone(public_media.PublicMedia(linked_root).info(NAME))

    def test_portable_access_rechecks_bytes_on_negotiation_and_rejects_reparse_points(self):
        with patch.object(public_media, '_directory_descriptors', return_value=False):
            self.assertIsNotNone(self.registry.info(NAME))
            with patch.object(public_media.hashlib, 'sha256', wraps=hashlib.sha256) as checksum:
                self.assertIsNotNone(self.registry.info(NAME))
                checksum.assert_called_once()
            original = public_media._linked
            with patch.object(public_media, '_linked', side_effect=lambda info: True if info.st_ino == self.path.parent.stat().st_ino else original(info)):
                self.assertIsNone(self.registry.info(NAME))
        class Reparse:
            st_mode = 0
            st_file_attributes = 0x400
        self.assertTrue(public_media._linked(Reparse()))

    def test_file_changed_during_snapshot_is_rejected(self):
        read = os.read
        access_paths = (False, True) if self.native_descriptors else (True,)
        for portable in access_paths:
            self.path.write_bytes(BODY)
            attempted = denied = False

            def replace(descriptor, size):
                nonlocal attempted, denied
                raw = read(descriptor, size)
                if not attempted:
                    attempted = True
                    try:
                        self.path.write_bytes(b'X' * len(BODY))
                    except PermissionError:
                        # Some Windows file-sharing modes deny replacement or
                        # writes while the verified descriptor remains open.
                        denied = True
                return raw

            registry = public_media.PublicMedia(self.root)
            with patch.object(public_media, '_directory_descriptors', return_value=not portable), \
                 patch.object(public_media.os, 'read', side_effect=replace):
                result = registry.info(NAME)
            self.assertTrue(attempted)
            if denied:
                self.assertEqual(self.path.read_bytes(), BODY)
                self.assertTrue(result is None or result['sha256'] == REVIEWED[NAME][1])
            else:
                self.assertEqual(self.path.read_bytes(), b'X' * len(BODY))
                self.assertIsNone(result)

    def test_correlation_is_bounded(self):
        self.assertEqual(12, public_media.correlation(12))
        self.assertEqual('request', public_media.correlation('request'))
        for value in (True, [], {}, 'x' * 101, 2**53, 1.2):
            self.assertIsNone(public_media.correlation(value))

    def test_world_folder_and_explicit_publication_invalidate_runtime_media_identity(self):
        world = SimpleNamespace(game_dir=self.root)
        first = public_media.session(world)
        world._public_media = self.registry
        self.assertEqual(first, public_media.session(world))
        self.assertIs(self.registry, world._public_media)
        world.game_dir = self.root / 'published'
        second = public_media.session(world)
        self.assertNotEqual(first, second)
        self.assertIsNone(world._public_media)
        self.assertEqual(second, public_media.session(world))
        self.assertNotEqual(second, public_media.invalidate(world))


class MediaTransport(unittest.IsolatedAsyncioTestCase):
    async def session(self, packets, *, joined=True, sentinels=False):
        with tempfile.TemporaryDirectory(prefix='expanse-public-media-route-') as temporary:
            root = Path(temporary)
            world, player = fixture(root)
            path = world.game_dir / NAME
            path.parent.mkdir(parents=True)
            path.write_bytes(BODY)
            if sentinels:
                for name in ('assets/updates/private.json', 'assets/chronicles/private.json'):
                    private = world.game_dir / name
                    private.parent.mkdir(parents=True)
                    private.write_text('{"private":"must never be delivered"}')
            with ExitStack() as stack:
                for target, attribute, value in (
                    (game_server, 'build_world', world),
                    (game_server, 'SAVE_DIR', root / 'save'),
                    (game_server, 'WORLD_STATE_PATH', root / 'state.json'),
                    (loader, 'GAMES_DIR', root / 'games'),
                    (persistence, 'DB_PATH', root / 'world.db'),
                    (public_media, 'PUBLIC_PRESENTATION', REVIEWED),
                ):
                    stack.enter_context(patch.object(target, attribute, return_value=value)
                                        if attribute == 'build_world' else patch.object(target, attribute, value))
                server = game_server.GameServer(mode='single')
                commands = ([{'command': 'resume traveller'}] if joined else []) + packets
                socket = Socket(server, player, commands)
                try:
                    await server.handle(socket)
                    self.assertFalse((root / 'world.db').exists())
                    self.assertFalse((root / 'state.json').exists())
                    return socket
                finally:
                    server.db.close()
                    server.checkpoint_db.close()

    async def test_joined_map_capability_and_exact_host_negotiation_preserve_legacy_chunks(self):
        loop_thread = threading.get_ident()
        worker_threads = []
        info = public_media.PublicMedia.info
        def checked(registry, name):
            worker_threads.append(threading.get_ident())
            return info(registry, name)
        with patch.object(public_media.PublicMedia, 'info', checked):
            socket = await self.session([
                {'command': 'map'},
                {'command': 'world asset info', 'name': NAME, 'request_id': 'version'},
                {'command': 'world asset', 'name': NAME, 'offset': 0, 'request_id': 7},
                {'command': 'world asset info', 'name': 'assets/private.json', 'request_id': 8},
            ])
        maps = [row for row in socket.packets if row['type'] == 'map']
        self.assertTrue(maps)
        self.assertEqual(1, maps[0]['media_protocol'])
        self.assertIsInstance(maps[0]['media_world'], str)
        self.assertNotIn('public_media', maps[0])
        replies = [row for row in socket.packets if row['type'] == 'world_asset_info']
        self.assertEqual('public-presentation', replies[0]['scope'])
        self.assertEqual(REVIEWED[NAME][1], replies[0]['sha256'])
        self.assertEqual('version', replies[0]['request_id'])
        self.assertEqual({'type': 'world_asset_info', 'name': 'assets/private.json',
                          'request_id': 8, 'scope': 'transient'}, replies[1])
        chunk = next(row for row in socket.packets if row['type'] == 'world_asset')
        self.assertEqual(len(BODY), chunk['size'])
        self.assertEqual(7, chunk['request_id'])
        self.assertNotIn('sha256', chunk)
        self.assertTrue(worker_threads)
        self.assertTrue(all(ident != loop_thread for ident in worker_threads))

    async def test_unjoined_socket_discloses_no_existence_or_hash_even_for_reviewed_name(self):
        with patch.object(public_media.PublicMedia, 'info', side_effect=AssertionError('Unauthorized read')):
            socket = await self.session([
                {'command': 'world asset info', 'name': NAME, 'request_id': 1},
                {'command': 'world asset info', 'name': 'assets/private.json', 'request_id': 2},
                {'command': 'world asset info', 'name': 'x' * 513, 'request_id': ['unbounded']},
            ], joined=False)
        replies = [row for row in socket.packets if row['type'] == 'world_asset_info']
        self.assertEqual(3, len(replies))
        for row in replies:
            self.assertEqual({'type', 'name', 'request_id', 'scope'}, set(row))
            self.assertEqual('transient', row['scope'])
        self.assertIsNone(replies[-1]['name'])
        self.assertIsNone(replies[-1]['request_id'])

    async def test_map_and_legacy_chunks_do_not_build_or_hash_the_public_registry(self):
        with patch.object(public_media.PublicMedia, 'info', side_effect=AssertionError('Map/chunk rehash')):
            socket = await self.session([
                {'command': 'map'},
                {'command': 'world asset', 'name': NAME, 'request_id': 'legacy'},
            ])
        self.assertTrue(any(row['type'] == 'map' for row in socket.packets))
        self.assertTrue(any(row['type'] == 'world_asset' and row.get('data') for row in socket.packets))

    async def test_snapshot_result_is_discarded_if_the_host_world_changed_while_awaiting_it(self):
        with tempfile.TemporaryDirectory(prefix='expanse-media-world-switch-') as temporary:
            root = Path(temporary)
            world, player = fixture(root)
            server = game_server.GameServer.__new__(game_server.GameServer)
            server.world = world
            socket = Socket(server, player, [])
            server.clients = {socket: player.id}
            async def changed(callback, name):
                server.world = object()
                return {'scope': 'public-presentation', 'sha256': REVIEWED[NAME][1],
                        'size': len(BODY), 'mime': 'image/png'}
            with patch.object(game_server.asyncio, 'to_thread', side_effect=changed):
                await server.world_asset_info(socket, player.id, {'name': NAME, 'request_id': 3})
            self.assertEqual({'type': 'world_asset_info', 'name': NAME,
                              'request_id': 3, 'scope': 'transient'}, socket.packets[-1])

    async def test_legacy_chunks_require_a_joined_actor_and_source_namespaces_are_not_delivered(self):
        socket = await self.session([{'command': 'world asset', 'name': NAME, 'request_id': 1}], joined=False)
        chunk = next(row for row in socket.packets if row['type'] == 'world_asset')
        self.assertTrue(chunk['missing'])
        self.assertNotIn('size', chunk)
        self.assertNotIn('data', chunk)
        # Use actual present sentinels: denial must not depend on nonexistence.
        with patch.object(game_server.asyncio, 'to_thread', side_effect=AssertionError('Private source read')):
            socket = await self.session([
                {'command': 'world asset', 'name': 'assets/updates/private.json', 'request_id': 2},
                {'command': 'world asset', 'name': 'assets/chronicles/private.json', 'request_id': 3},
            ], sentinels=True)
        denied = [row for row in socket.packets if row['type'] == 'world_asset']
        self.assertEqual(2, len(denied))
        for row in denied:
            self.assertTrue(row['missing'])
            self.assertNotIn('data', row)
        from engine.world_package import media
        self.assertTrue(media('assets/updates/private.json'), 'Archive eligibility must remain unchanged.')


class ReleasedInventory(unittest.TestCase):
    def test_registry_is_exactly_the_reviewed_rendering_subset(self):
        self.assertEqual(15, len(public_media.PUBLIC_PRESENTATION))
        self.assertEqual(2937600, sum(row[0] for row in public_media.PUBLIC_PRESENTATION.values()))
        archive = os.environ.get('EXPANSE_TEST_WORLD_ARCHIVE')
        archive = Path(archive) if archive else Path(__file__).resolve().parents[2] / 'test-world/Expanse-Wild-Lands-1.9.15.expanse'
        if not archive.is_file():
            self.skipTest('Set EXPANSE_TEST_WORLD_ARCHIVE to the released Wild Lands 1.9.15 archive.')
        with ZipFile(archive) as world:
            for name, (size, digest, mime) in public_media.PUBLIC_PRESENTATION.items():
                raw = world.read(name)
                self.assertEqual(size, len(raw), name)
                self.assertEqual(digest, hashlib.sha256(raw).hexdigest(), name)
                self.assertLessEqual(size, public_media.MAX_SIZE)
                self.assertIn(mime, ('application/json', 'image/png', 'audio/ogg'))
                self.assertNotIn('wildlife', name)
                self.assertNotIn('updates', name)
                self.assertNotIn('chronicles', name)


if __name__ == '__main__':
    unittest.main()
