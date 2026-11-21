import base64
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
import test_community as existing
from app import Store, mount_forum, _emote_labels


class Composer(HTMLParser):
    def __init__(self, doc):
        super().__init__()
        self.scripts, self.buttons, self.fallback, self.forms = [], [], [], []
        self.script, self.code = None, None
        self.feed(doc)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.script = ''
        if tag == 'button' and 'data-emote' in attrs:
            self.buttons.append(attrs)
        if tag == 'code' and 'data-emote-fallback' in attrs:
            self.code = ''
        if tag == 'form':
            self.forms.append(attrs.get('action'))

    def handle_data(self, data):
        if self.script is not None:
            self.script += data
        if self.code is not None:
            self.code += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.scripts.append(self.script)
            self.script = None
        if tag == 'code' and self.code is not None:
            self.fallback.append(self.code)
            self.code = None


class EmojiPickerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = existing.ForumTests.asyncSetUp
    asyncTearDown = existing.ForumTests.asyncTearDown
    login_admin = existing.ForumTests.login_admin
    create_member = existing.ForumTests.create_member

    async def assert_palette(self, response, expected_action):
        self.assertEqual(200, response.status)
        html = await response.text()
        layout = Composer(html)
        self.assertIn(expected_action, layout.forms)
        self.assertEqual(1, len(layout.scripts))
        content = layout.scripts[0]
        expected = (Path(__file__).resolve().parents[1] / 'static/emote-picker.js').read_text()
        self.assertEqual(expected, content)
        h = base64.b64encode(sha256(content.encode()).digest()).decode()
        csp = response.headers['Content-Security-Policy']
        self.assertIn(f"script-src 'sha256-{h}';", csp)
        self.assertNotIn("script-src 'self'", csp)
        self.assertNotIn('unsafe-inline', csp)
        self.assertEqual(64, len(layout.buttons))
        want = [f':{name}:' for name in _emote_labels]
        self.assertEqual(want, [row['data-emote'] for row in layout.buttons])
        self.assertEqual(want, layout.fallback)
        self.assertTrue(all(x['type'] == 'button' and 'hidden' in x for x in layout.buttons))
        return html

    async def test_both_composers_and_signed_out_and_locked_states(self):
        admin_csrf, member_csrf = await self.create_member()
        await self.assert_palette(await self.visitor.get('/new'), '/new')
        response = await self.visitor.post('/new', data={'category': 'discussion', 'title': 'Emoji test topic',
                                                            'body': 'The town says :wave:', 'csrf': member_csrf}, allow_redirects=False)
        self.assertEqual(303, response.status)
        href = response.headers['Location']
        self.assertIn('e-wave', await self.assert_palette(await self.visitor.get(href), '/reply'))
        tid = int(href.rsplit('/', 1)[-1])
        await self.admin.post('/moderate', data={'topic_id': tid, 'action': 'lock', 'csrf': admin_csrf}, allow_redirects=False)
        response = await self.visitor.get(href)
        self.assertIn("script-src 'none';", response.headers['Content-Security-Policy'])
        self.assertNotIn('data-forum-emotes', await response.text())
        for route in ['/', '/login', '/register']:
            response = await self.visitor.get(route)
            self.assertIn("script-src 'none';", response.headers['Content-Security-Policy'])
        public = TestClient(self.server)
        await public.start_server()
        try:
            response = await public.get(href)
            html = await response.text()
            self.assertIn('e-wave', html)
            self.assertNotIn('data-forum-emotes', html)
            self.assertIn("script-src 'none';", response.headers['Content-Security-Policy'])
        finally:
            await public.close()

    async def test_topic_and_reply_store_plain_text_and_render_existing_palette_safely(self):
        _, csrf = await self.create_member()
        text = 'Meet :wave: <b>friend</b> & guests. :NOT_A_CODE:'
        r = await self.visitor.post('/new', data={'category':'discussion','title':'Testing prose','body':text,'csrf':csrf}, allow_redirects=False)
        self.assertEqual(303, r.status)
        href = r.headers['Location']; tid = int(href.rsplit('/', 1)[-1])
        reply = 'Ready :magic: and 👋!'
        r = await self.visitor.post('/reply', data={'topic_id': tid, 'body': reply, 'csrf': csrf}, allow_redirects=False)
        self.assertEqual(303, r.status)
        with Store(self.db).db() as db:
            self.assertEqual(text, db.execute('SELECT body FROM topics WHERE id=?',(tid,)).fetchone()[0])
            self.assertEqual(reply, db.execute('SELECT body FROM replies WHERE topic_id=?',(tid,)).fetchone()[0])
        html = await (await self.visitor.get(href)).text()
        self.assertIn('&lt;b&gt;friend&lt;/b&gt; &amp; guests. :NOT_A_CODE:', html)
        self.assertIn('class="expanse-emote e-magic" role="img"', html)
        self.assertGreaterEqual(html.count('class="expanse-emote e-wave" role="img"'), 2)

    async def test_mounted_forum_keeps_relative_assets_and_hash(self):
        game=web.Application()
        data=Path(self.work.name) / 'mounted'
        data.mkdir()
        with patch('app.os.path.ismount', return_value=True):
            mount_forum(game, data, bootstrap=('owner','correct-long-password-123'))
        async with TestClient(TestServer(game), cookie_jar=CookieJar(unsafe=True)) as client:
            r = await client.post('/forum/login', data={'username':'owner','password':'correct-long-password-123'}, allow_redirects=False)
            self.assertEqual(303, r.status)
            token = r.cookies['expanse_forum']
            self.assertEqual('/forum', token['path'])
            # The mounted route requires a Secure cookie; the isolated fixture uses HTTP.
            html = await self.assert_palette(await client.get('/forum/new', headers={'Cookie': 'expanse_forum=' + token.value}), '/forum/new')
            self.assertIn('href="/forum/emotes.css"', html)
            self.assertIn('href="/forum/style.css"', html)
            art = await (await client.get('/forum/emotes.css')).text()
            self.assertIn('data:image/png;base64,', art)
            self.assertIn('.expanse-emote.e-wave', art)
