"""HTTP/cache boundaries for the Render application shell, without game workers."""
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

import render_server


def service_of(app):
    for resource in app.router.resources():
        for route in resource:
            if getattr(route.handler, '__name__', '') == 'landing':
                return route.handler.__self__
    raise AssertionError('Landing service handler not found')


class ShellReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == 'script' and values.get('src'):
            self.urls.append(values['src'])
        if tag == 'link' and 'stylesheet' in values.get('rel', '').split() and values.get('href'):
            self.urls.append(values['href'])


class VersionedAppAssetsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='expanse-versioned-assets-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.web = self.root / 'web'
        self.web.mkdir()
        self.script = b'window.fixture = "original application bytes";\n' * 400
        self.style = b'body { color: navy; background: ivory; }\n' * 100
        (self.web / 'app.js').write_bytes(self.script)
        (self.web / 'app.css').write_bytes(self.style)
        (self.web / 'private.json').write_text('{"not_an_application_asset":true}')
        (self.web / 'index.html').write_text(
            '<!doctype html><script src="/app.js?v=old"></script>'
            '<link rel="stylesheet" href="/app.css">'
            '<script src="https://example.invalid/external.js"></script>', encoding='utf-8')
        self.data = self.root / 'user-data'
        self.data.mkdir()
        self.save = self.data / 'existing-save.json'
        self.save.write_bytes(b'preserve existing user save bytes')
        self.origin = 'http://127.0.0.1:10000'
        self.settings = {
            'EXPANSE_PUBLIC_URL': self.origin, 'EXPANSE_DATA_DIR': str(self.data),
            'EXPANSE_GUESTS_JSON': '[]', 'EXPANSE_OWNER_NAME': 'Asset Owner',
            'EXPANSE_OWNER_PASSWORD': 'temporary-asset-owner-password',
        }
        self.environment = patch.dict(os.environ, self.settings, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.root_patch = patch.object(render_server, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.client, self.service = await self.new_client()

    async def new_client(self):
        app = render_server.make_app()
        service = service_of(app)
        # Shell delivery needs authentication but no simulation, world import,
        # editor draft, account migration or live player to be exercised.
        service.active_client = lambda request: object()
        service.editor_service = AsyncMock(return_value=None)
        client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client, service

    async def login(self, client=None):
        client = client or self.client
        response = await client.post('/login', data={'name': 'Asset Owner', 'password': self.settings['EXPANSE_OWNER_PASSWORD']},
                                     headers={'Origin': self.origin}, allow_redirects=False)
        self.assertEqual(response.status, 303)

    def assert_no_store(self, response):
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertNotIn('immutable', response.headers.get('Cache-Control', ''))

    def assert_immutable_private(self, response):
        policy = response.headers.get('Cache-Control', '')
        self.assertIn('private', policy)
        self.assertIn('max-age=31536000', policy)
        self.assertIn('immutable', policy)
        self.assertNotIn('public', policy)
        self.assertIn('accept-encoding', response.headers.get('Vary', '').lower())
        self.assertNotIn('Set-Cookie', response.headers)

    async def test_shells_reference_verified_immutable_assets_and_keep_html_uncacheable(self):
        await self.login()
        for endpoint in ('/play', '/editor?game=fixture'):
            response = await self.client.get(endpoint)
            self.assertEqual(response.status, 200)
            self.assert_no_store(response)
            parser = ShellReferences()
            parser.feed(await response.text())
            self.assertIn(self.service.app_assets.url('app.js'), parser.urls)
            self.assertIn(self.service.app_assets.url('app.css'), parser.urls)
            self.assertIn('https://example.invalid/external.js', parser.urls)
            self.assertNotIn('/app.js?v=old', parser.urls)
        expected = hashlib.sha256(self.script).hexdigest()
        self.assertIn(expected, self.service.app_assets.url('app.js'))
        self.assertEqual(self.save.read_bytes(), b'preserve existing user save bytes')

    async def test_versioned_assets_require_authentication_and_failures_are_not_cached(self):
        url = self.service.app_assets.url('app.js')
        denied = await self.client.get(url)
        self.assertEqual(denied.status, 401)
        self.assert_no_store(denied)
        await self.login()
        for invalid in ('/app-assets/' + '0' * 64 + '/app.js',
                        '/app-assets/' + hashlib.sha256(b'private').hexdigest() + '/private.json',
                        '/app-assets/not-a-content-hash/app.js'):
            response = await self.client.get(invalid)
            self.assertEqual(response.status, 404)
            self.assert_no_store(response)
        logout = await self.client.post('/logout', headers={'Origin': self.origin}, allow_redirects=False)
        self.assertEqual(logout.status, 303)
        self.assert_no_store(logout)
        denied_again = await self.client.get(url)
        self.assertEqual(denied_again.status, 401)
        self.assert_no_store(denied_again)

    async def test_compressed_variants_have_correct_bytes_etags_and_explicit_revalidation(self):
        import gzip
        await self.login()
        url = self.service.app_assets.url('app.js')
        identity = await self.client.get(url, headers={'Accept-Encoding': 'identity'}, auto_decompress=False)
        self.assertEqual(identity.status, 200)
        self.assert_immutable_private(identity)
        self.assertEqual(await identity.read(), self.script)
        self.assertNotIn('Content-Encoding', identity.headers)
        compressed = await self.client.get(url, headers={'Accept-Encoding': 'gzip, identity;q=0'}, auto_decompress=False)
        self.assertEqual(compressed.status, 200)
        self.assert_immutable_private(compressed)
        self.assertEqual(compressed.headers.get('Content-Encoding'), 'gzip')
        encoded = await compressed.read()
        self.assertEqual(gzip.decompress(encoded), self.script)
        self.assertLess(len(encoded), len(self.script))
        self.assertNotEqual(identity.headers['ETag'], compressed.headers['ETag'])
        warm_validation = await self.client.get(url, headers={'Accept-Encoding': 'gzip', 'If-None-Match': compressed.headers['ETag']}, auto_decompress=False)
        self.assertEqual(warm_validation.status, 304)
        self.assertEqual(await warm_validation.read(), b'')
        self.assert_immutable_private(warm_validation)
        # An identity representation's strong validator must not validate a
        # different gzip representation merely because their source is equal.
        other_variant = await self.client.get(url, headers={'Accept-Encoding': 'gzip', 'If-None-Match': identity.headers['ETag']}, auto_decompress=False)
        self.assertEqual(other_variant.status, 200)
        self.assertEqual(gzip.decompress(await other_variant.read()), self.script)

    async def test_quality_values_reject_forbidden_encodings_without_caching_errors(self):
        await self.login()
        url = self.service.app_assets.url('app.js')
        response = await self.client.get(url, headers={'Accept-Encoding': 'gzip;q=0, identity;q=1'}, auto_decompress=False)
        self.assertEqual(response.status, 200)
        self.assertNotIn('Content-Encoding', response.headers)
        self.assertEqual(await response.read(), self.script)
        refused = await self.client.get(url, headers={'Accept-Encoding': 'gzip;q=0, identity;q=0'}, auto_decompress=False)
        self.assertEqual(refused.status, 406)
        self.assert_no_store(refused)

    async def test_legacy_and_authenticated_state_endpoints_remain_no_store_and_mmo_closed(self):
        await self.login()
        first = await self.client.get('/app.js', headers={'Accept-Encoding': 'identity'}, auto_decompress=False)
        self.assertEqual(first.status, 200)
        self.assert_no_store(first)
        self.assertEqual(await first.read(), self.script)
        conditional = await self.client.get('/app.js', headers={'If-None-Match': first.headers['ETag']}, auto_decompress=False)
        self.assertEqual(conditional.status, 304)
        self.assert_no_store(conditional)
        for endpoint in ('/', '/healthz', '/mmo', '/api/playtest/report'):
            response = await self.client.get(endpoint)
            self.assertEqual(response.status, 200)
            self.assert_no_store(response)
        mmo = await self.client.post('/enter', data={'mode': 'mmo'}, headers={'Origin': self.origin}, allow_redirects=False)
        self.assertEqual(mmo.status, 503)
        self.assert_no_store(mmo)
        self.assertFalse(self.service.workers)

    async def test_content_changes_only_change_affected_urls_and_cannot_rewrite_old_snapshot_bytes(self):
        await self.login()
        old_script_url = self.service.app_assets.url('app.js')
        old_style_url = self.service.app_assets.url('app.css')
        replacement = b'window.fixture = "new release bytes";\n' * 401
        (self.web / 'app.js').write_bytes(replacement)
        old = await self.client.get(old_script_url, headers={'Accept-Encoding': 'identity'}, auto_decompress=False)
        self.assertEqual(old.status, 200)
        self.assertEqual(await old.read(), self.script)
        second, next_service = await self.new_client()
        await self.login(second)
        new_script_url = next_service.app_assets.url('app.js')
        self.assertNotEqual(new_script_url, old_script_url)
        self.assertEqual(next_service.app_assets.url('app.css'), old_style_url)
        updated = await second.get(new_script_url, headers={'Accept-Encoding': 'identity'}, auto_decompress=False)
        self.assertEqual(updated.status, 200)
        self.assertEqual(await updated.read(), replacement)
        self.assertEqual(self.save.read_bytes(), b'preserve existing user save bytes')


if __name__ == '__main__':
    unittest.main()
