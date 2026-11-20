"""Public community lookups coexist with private game routes."""
import os
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from community.app import text_html
from render_server import make_app


class PlayerCommunityTests(IsolatedAsyncioTestCase):
    async def test_guest_navigation(self):
        with TemporaryDirectory() as data, patch.dict(os.environ, {
            'EXPANSE_DATA_DIR': data, 'EXPANSE_PUBLIC_URL': 'http://127.0.0.1:8461',
            'EXPANSE_GUESTS_JSON': '[]', 'EXPANSE_OWNER_NAME': 'testowner',
            'EXPANSE_OWNER_PASSWORD': 'temporary-test-owner-password',
            'EXPANSE_REQUIRE_DISK': '0',
        }):
            async with TestClient(TestServer(make_app())) as client:
                home = await (await client.get('/')).text()
                for destination in ('/wiki/index.html', '/forum/login', '/forum/register'):
                    self.assertIn(destination, home)
                for path in ('/wiki/index.html', '/wiki/multiplayer.html', '/assets/wiki.css'):
                    self.assertEqual((await client.get(path)).status, 200)
                self.assertEqual((await client.get('/api/character/saves')).status, 401)

    def test_forum_reactions_keep_unknown_glyphs_and_text(self):
        markup = text_html('👋🏾 :wave: :NPC_bow_pose: 🐘 <hello> :unknown:')
        self.assertEqual(markup.count('class="expanse-emote e-wave"'), 2)
        self.assertIn('e-npc_bow_pose', markup)
        self.assertIn('🐘 &lt;hello&gt; :unknown:', markup)
