import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

from engine.exchange import export_game
import render_server
from server import bundled_world


class SeedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.worlds = self.root / 'data' / 'worlds'
        self.worlds.mkdir(parents=True)
        source = self.root / 'sources' / 'small'
        source.mkdir(parents=True)
        (source / 'rooms.json').write_text(json.dumps([{'id':'square','name':'Square','description':'Square','exits':{}}]))
        (source / 'metadata.json').write_text(json.dumps({'name':'Test world','start_room':'square'}))
        self.archive = self.root / 'small.expanse'
        ok, note = export_game('small', source.parent, self.archive)
        self.assertTrue(ok, note)
        raw = self.archive.read_bytes()
        self.sha = hashlib.sha256(raw).hexdigest()
        self.parts = [self.root / 'first', self.root / 'last']
        self.parts[0].write_bytes(raw[:16])
        self.parts[1].write_bytes(raw[16:])
        self.cache = self.root / 'deploy-cache'

    def prepare(self):
        return bundled_world.prepare(self.worlds, self.cache, self.parts, self.sha, 'small')

    def test_new_repeat_recovery_and_bad_parts_preserve_player_disk(self):
        unrelated = self.worlds / ('e'*64)
        unrelated.mkdir()
        sentinel = unrelated / 'info.json'
        sentinel.write_bytes(b'old imported entry')
        save = self.worlds.parent / 'players' / 'prior' / 'world.db'
        save.parent.mkdir(parents=True)
        save.write_bytes(b'old private checkpoint')
        cache = self.prepare()
        self.assertEqual(self.archive.read_bytes(), (cache / 'world.expanse').read_bytes())
        stat = (cache / 'world.expanse').stat()
        with patch.object(bundled_world, 'validate_import', side_effect=AssertionError('Re-imported')):
            self.assertEqual(cache, self.prepare())
        self.assertEqual(stat.st_ino, (cache / 'world.expanse').stat().st_ino)
        rooms = cache / 'games/small/rooms.json'
        expected = rooms.read_bytes()
        rooms.write_bytes(b'x'*len(expected))
        self.assertEqual(cache, self.prepare())
        self.assertEqual(expected, rooms.read_bytes())
        shutil.rmtree(cache)
        abandoned = self.cache / ('.building-' + self.sha)
        abandoned.mkdir()
        (abandoned/'partial').write_bytes(b'partial operation')
        self.parts[1].write_bytes(b'bad release')
        with self.assertRaisesRegex(ValueError, 'failed verification'):
            self.prepare()
        self.assertFalse(cache.exists())
        self.assertFalse(abandoned.exists())
        self.assertEqual(list(self.worlds.iterdir()), [unrelated])
        self.assertEqual(sentinel.read_bytes(), b'old imported entry')
        self.assertEqual(save.read_bytes(), b'old private checkpoint')

    def test_existing_verified_owner_import_has_priority_without_duplicate(self):
        existing = self.worlds / self.sha
        existing.mkdir()
        shutil.copyfile(self.archive, existing/'world.expanse')
        bundled_world.validate_import(existing/'world.expanse', existing)
        with patch.object(bundled_world, 'validate_import', side_effect=AssertionError('Duplicated')):
            self.assertEqual(existing, self.prepare())
        self.assertFalse(self.cache.exists())


class SeedGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_authenticated_player_can_download_and_enter_without_import(self):
        with tempfile.TemporaryDirectory(prefix='seed-gateway-') as directory:
            root = Path(directory)
            secret = secrets.token_urlsafe(24)
            origin = 'http://127.0.0.1:9999'
            env = dict(EXPANSE_PUBLIC_URL=origin, EXPANSE_DATA_DIR=str(root/'data'),
                       XDG_CACHE_HOME=str(root/'deployment-cache'), EXPANSE_OWNER_NAME='Owner',
                       EXPANSE_OWNER_PASSWORD=secrets.token_urlsafe(24),
                       EXPANSE_GUESTS_JSON=json.dumps([{'name':'Traveller','password':secret}]))
            with patch.dict(os.environ, env, clear=True):
                application = render_server.make_app()
                async with TestClient(TestServer(application), cookie_jar=CookieJar(unsafe=True)) as client:
                    url = '/world.expanse?game=' + bundled_world.DIGEST
                    self.assertEqual(401, (await client.get(url)).status)
                    login = await client.post('/login',data={'name':'Traveller','password':secret},
                                              headers={'Origin':origin},allow_redirects=False)
                    self.assertEqual(303,login.status)
                    lobby = await (await client.get('/')).text()
                    self.assertIn('Imported world version 1.10.0',lobby)
                    self.assertIn(bundled_world.DIGEST[:12],lobby)
                    self.assertNotIn('<h2>Import a game</h2>',lobby)
                    download = await client.get(url)
                    self.assertEqual(200,download.status)
                    self.assertEqual(bundled_world.DIGEST,hashlib.sha256(await download.read()).hexdigest())
                    for mode, expected in [('mmo',503),('single',303)]:
                        response = await client.post('/enter',data={'game':bundled_world.DIGEST,'mode':mode},
                                                     headers={'Origin':origin},allow_redirects=False)
                        self.assertEqual(expected,response.status,await response.text())
                    options = await (await client.get('/api/character/options')).json()
                    self.assertTrue(options['classless_start'])
                    self.assertEqual(8,len(options['starting_cities']))
                    self.assertEqual([],list((root/'data/worlds').iterdir()))


if __name__ == '__main__':
    unittest.main()
