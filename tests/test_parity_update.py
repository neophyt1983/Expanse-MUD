"""Regression coverage for portable templates and the Render parity update.

Run: python -m unittest discover -s tests -p 'test_parity_update.py'
"""
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

import render_server
from engine import history_templates, living
from engine.world_history import HistoryError


class TemplatePortabilityTests(unittest.TestCase):
    def test_portable_snapshot_preserves_content_media_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'metadata.json').write_text('{"name":"Portable world"}', encoding='utf-8')
            (root / 'rooms.json').write_text('[]', encoding='utf-8')
            (root / 'assets' / 'empty').mkdir(parents=True)
            Image.new('RGB', (2, 2), 'navy').save(root / 'assets' / 'sky.png')
            expected_files = {
                name: (root / name).read_bytes()
                for name in ('metadata.json', 'rooms.json', 'assets/sky.png')
            }
            native = history_templates.snapshot(root)
            # A platform without directory descriptors must preserve the same
            # exportable content and signatures, including empty media folders.
            with patch.object(history_templates, 'os', types.SimpleNamespace(scandir=os.scandir)):
                portable = history_templates.snapshot(root)
            self.assertEqual(portable, native)
            self.assertEqual(portable['files'], expected_files)
            self.assertEqual(set(portable['directories']), {'assets', 'assets/empty'})

    def test_portable_snapshot_refuses_a_linked_definition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'world'
            root.mkdir()
            outside = Path(temporary) / 'outside.json'
            outside.write_text('{}', encoding='utf-8')
            try:
                (root / 'metadata.json').symlink_to(outside)
            except OSError as error:
                self.skipTest('Creating symbolic links is unavailable: ' + str(error))
            with patch.object(history_templates, 'os', types.SimpleNamespace(scandir=os.scandir)):
                with self.assertRaisesRegex(HistoryError, '[Ll]ink'):
                    history_templates.snapshot(root)
            self.assertEqual(outside.read_text(encoding='utf-8'), '{}')

    def test_oversized_definition_is_rejected_by_both_snapshot_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # A reduced budget exercises the boundary without allocating a
            # production-size world just for this regression.
            (root / 'metadata.json').write_bytes(b'{}' + b' ' * 63)
            with patch.object(history_templates, 'MAX_FILE', 64):
                with self.assertRaisesRegex(HistoryError, 'budget'):
                    history_templates.snapshot(root)
                with patch.object(history_templates, 'os', types.SimpleNamespace(scandir=os.scandir)):
                    with self.assertRaisesRegex(HistoryError, 'budget'):
                        history_templates.snapshot(root)


class RuntimeClockTests(unittest.TestCase):
    def test_existing_runtime_minute_does_not_recalculate_or_reset_dawn(self):
        world = types.SimpleNamespace(metadata={})
        with patch.object(living.worldtime, 'initial_minute', return_value=375) as dawn:
            self.assertEqual(living.state(world)['minute'], 375)
            world.living_state['minute'] = 421
            # Re-reading authored configuration in the hot path could become
            # expensive or fail after the runtime world has already started.
            dawn.side_effect = AssertionError('Authored dawn recalculated')
            self.assertEqual(living.state(world)['minute'], 421)
            dawn.assert_called_once()


class RenderParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_marker_and_authenticated_icon_without_starting_a_world(self):
        origin = 'http://127.0.0.1:10000'
        password = 'parity-owner-test-password'
        with tempfile.TemporaryDirectory() as temporary:
            settings = {
                'EXPANSE_PUBLIC_URL': origin,
                'EXPANSE_DATA_DIR': temporary,
                'EXPANSE_GUESTS_JSON': '[]',
                'EXPANSE_OWNER_NAME': 'Parity Owner',
                'EXPANSE_OWNER_PASSWORD': password,
            }
            with patch.dict(os.environ, settings, clear=True):
                client = TestClient(TestServer(render_server.make_app()), cookie_jar=CookieJar(unsafe=True))
                async with client:
                    health = await client.get('/healthz')
                    self.assertEqual(health.status, 200)
                    self.assertEqual(await health.text(), 'ok')
                    self.assertEqual(health.headers['X-Expanse-Server-Build'], render_server.RENDER_SERVER_BUILD)
                    self.assertEqual((await client.get('/expanse.ico')).status, 401)
                    login = await client.post('/login', data={'name': 'Parity Owner', 'password': password},
                                              headers={'Origin': origin}, allow_redirects=False)
                    self.assertEqual(login.status, 303)
                    icon = await client.get('/expanse.ico')
                    self.assertEqual(icon.status, 200)
                    self.assertEqual(await icon.read(), (render_server.ROOT / 'web' / 'expanse.ico').read_bytes())


if __name__ == '__main__':
    unittest.main()
