#!/usr/bin/env python3
"""Measure the Render app-shell cache policy locally without touching game data.

The prechange adapter is read from Git HEAD and receives the same temporary copy
of candidate web files as the current adapter. This isolates HTTP policy and
compression, not unrelated web-code edits. Aiohttp does not have a browser cache:
fresh-cache reuse is modeled explicitly; conditional 304 bodies are measured.
"""
import argparse
import asyncio
from contextlib import ExitStack
import gzip
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import render_server


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def service_of(app):
    for resource in app.router.resources():
        for route in resource:
            if getattr(route.handler, '__name__', '') == 'landing':
                return route.handler.__self__
    raise RuntimeError('Landing service handler not found.')


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        value = values.get('src') if tag == 'script' else values.get('href') if tag == 'link' and 'stylesheet' in values.get('rel', '').split() else None
        if value:
            url = urlsplit(value)
            if not url.scheme and not url.netloc and value not in self.urls:
                self.urls.append(value)


def decoded(raw, encoding):
    if encoding == 'gzip':
        return gzip.decompress(raw)
    if encoding == 'identity':
        return raw
    raise RuntimeError('Unexpected local transfer encoding: ' + encoding)


async def response_row(client, url, headers=None, expected=None):
    response = await client.get(url, headers=headers or {'Accept-Encoding': 'gzip'}, auto_decompress=False)
    raw = await response.read()
    encoding = response.headers.get('Content-Encoding', 'identity')
    row = {'url': url, 'status': response.status, 'encoded_body_bytes': len(raw),
           'content_encoding': encoding, 'cache_control': response.headers.get('Cache-Control'),
           'etag': response.headers.get('ETag'), 'vary': response.headers.get('Vary')}
    if expected is not None and response.status == 200:
        if decoded(raw, encoding) != expected:
            raise AssertionError('Delivered bytes differ from the copied source: ' + url)
    return row, raw


async def measure(baseline_ref='HEAD'):
    from aiohttp import CookieJar
    from aiohttp.test_utils import TestClient, TestServer

    parent_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    baseline_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--verify', '--end-of-options', baseline_ref + '^{commit}'], text=True).strip()
    before_source = subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline_commit + ':render_server.py'])
    if b'AppAssets' in before_source:
        raise ValueError('Baseline already contains AppAssets; select a prechange --baseline-ref.')
    baseline = types.ModuleType('_expanse_prechange_asset_probe')
    baseline.__file__ = str(ROOT / 'render_server.py')
    sys.modules[baseline.__name__] = baseline
    try:
        exec(compile(before_source, baseline.__file__, 'exec'), baseline.__dict__)
        with tempfile.TemporaryDirectory(prefix='expanse-versioned-app-probe-') as temporary, ExitStack() as patches:
            root = Path(temporary)
            shutil.copytree(ROOT / 'web', root / 'web', symlinks=True)
            data = root / 'temporary-user-data'
            data.mkdir()
            sentinel = data / 'save-sentinel.json'
            sentinel.write_bytes(b'{"preserve":"existing manual save"}')
            sentinel_before = sha256(sentinel.read_bytes())
            settings = {'EXPANSE_PUBLIC_URL': 'http://127.0.0.1:10000', 'EXPANSE_DATA_DIR': str(data),
                        'EXPANSE_GUESTS_JSON': '[]', 'EXPANSE_OWNER_NAME': 'Asset Probe',
                        'EXPANSE_OWNER_PASSWORD': 'temporary-app-asset-probe-password'}
            patches.enter_context(patch.dict(os.environ, settings, clear=True))
            patches.enter_context(patch.object(render_server, 'ROOT', root))
            baseline.ROOT = root
            clients = []

            async def create(module):
                app = module.make_app()
                service = service_of(app)
                service.active_client = lambda request: object()
                service.editor_service = AsyncMock(return_value=None)
                client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
                await client.start_server()
                clients.append(client)
                return client, service

            async def login(client):
                response = await client.post('/login', data={'name': 'Asset Probe', 'password': settings['EXPANSE_OWNER_PASSWORD']},
                                             headers={'Origin': settings['EXPANSE_PUBLIC_URL']}, allow_redirects=False)
                if response.status != 303:
                    raise AssertionError('Temporary local login failed.')

            async def page(client):
                row, raw = await response_row(client, '/play')
                if row['status'] != 200 or row['cache_control'] != 'no-store':
                    raise AssertionError('Play HTML must succeed and stay no-store.')
                references = References()
                references.feed(decoded(raw, row['content_encoding']).decode('utf-8'))
                return row, references.urls

            async def assets(client, urls):
                rows = []
                for url in urls:
                    name = Path(urlsplit(url).path).name
                    row, _ = await response_row(client, url, expected=(root / 'web' / name).read_bytes())
                    if row['status'] != 200:
                        raise AssertionError('Asset request failed: ' + url)
                    rows.append(row)
                return rows

            try:
                old, old_service = await create(baseline)
                await login(old)
                old_html, old_urls = await page(old)
                old_rows = await assets(old, old_urls)
                old_repeat = await assets(old, old_urls)

                new, new_service = await create(render_server)
                known_url = new_service.app_assets.url('world-assets.js')
                unauthenticated, _ = await response_row(new, known_url)
                await login(new)
                new_html, new_urls = await page(new)
                new_rows = await assets(new, new_urls)
                identity_rows = []
                validation_rows = []
                for row in new_rows:
                    identity, _ = await response_row(new, row['url'], {'Accept-Encoding': 'identity'})
                    identity_rows.append(identity)
                    validation, _ = await response_row(new, row['url'], {'Accept-Encoding': 'gzip', 'If-None-Match': row['etag']})
                    if validation['status'] != 304 or validation['encoded_body_bytes'] != 0:
                        raise AssertionError('Explicit validation must return an empty 304.')
                    validation_rows.append(validation)
                repeat_html, _ = await page(new)
                legacy, _ = await response_row(new, '/world-assets.js')
                legacy_conditional, _ = await response_row(new, '/world-assets.js', {'If-None-Match': legacy['etag']})
                unknown, _ = await response_row(new, '/app-assets/' + '0' * 64 + '/world-assets.js')
                unacceptable, _ = await response_row(new, known_url, {'Accept-Encoding': 'identity;q=0,gzip;q=0'})
                mmo = await new.post('/enter', data={'mode': 'mmo'}, headers={'Origin': settings['EXPANSE_PUBLIC_URL']}, allow_redirects=False)

                changed_file = root / 'web' / 'world-assets.js'
                changed_file.write_bytes(changed_file.read_bytes() + b'\n/* changed-file measurement fixture; not product source */\n')
                changed, changed_service = await create(render_server)
                await login(changed)
                changed_html, changed_urls = await page(changed)
                old_by_name = {Path(urlsplit(url).path).name: url for url in new_urls}
                changed_by_name = {Path(urlsplit(url).path).name: url for url in changed_urls}
                downloads = [url for name, url in changed_by_name.items() if old_by_name.get(name) != url]
                changed_rows = await assets(changed, downloads)
                old_snapshot, old_snapshot_bytes = await response_row(new, known_url)
                if decoded(old_snapshot_bytes, old_snapshot['content_encoding']) != (ROOT / 'web' / 'world-assets.js').read_bytes():
                    raise AssertionError('Startup immutable snapshot changed after copied source edit.')
                old_hash_after_restart, _ = await response_row(changed, known_url)
                preserved = sha256(sentinel.read_bytes()) == sentinel_before
                if not preserved or old_service.workers or new_service.workers or changed_service.workers:
                    raise AssertionError('A user-data sentinel changed or a simulation worker was started.')

                body_sum = lambda rows: sum(row['encoded_body_bytes'] for row in rows)
                return {
                    'schema_version': 1,
                    'scope': 'local Render app-shell only; prechange adapter and current adapter receive identical copied candidate web bytes',
                    'baseline_adapter_commit': baseline_commit, 'candidate_parent_commit': parent_commit,
                    'runtime_source_sha256': {name: sha256((ROOT / name).read_bytes()) for name in ('render_server.py', 'server/app_assets.py')},
                    'candidate_web_release': new_service.app_assets.release,
                    'authentication': 'temporary local owner; credentials/cookies not exported',
                    'prechange_measured': {'html': old_html, 'direct_static_requests': len(old_rows),
                        'direct_static_encoded_body_bytes': body_sum(old_rows), 'repeat_direct_static_encoded_body_bytes': body_sum(old_repeat),
                        'page_encoded_body_bytes': old_html['encoded_body_bytes'] + body_sum(old_rows),
                        'asset_cache_controls': sorted({row['cache_control'] for row in old_rows}),
                        'asset_content_encodings': sorted({row['content_encoding'] for row in old_rows})},
                    'candidate_cold_measured': {'html': new_html, 'direct_static_requests': len(new_rows),
                        'direct_static_identity_body_bytes': body_sum(identity_rows), 'direct_static_encoded_body_bytes': body_sum(new_rows),
                        'page_encoded_body_bytes': new_html['encoded_body_bytes'] + body_sum(new_rows),
                        'asset_cache_controls': sorted({row['cache_control'] for row in new_rows}),
                        'asset_content_encodings': sorted({row['content_encoding'] for row in new_rows})},
                    'candidate_explicit_revalidation_measured': {'html_body_bytes': repeat_html['encoded_body_bytes'],
                        'static_requests': len(validation_rows), 'static_response_body_bytes': body_sum(validation_rows),
                        'static_statuses': sorted({row['status'] for row in validation_rows})},
                    'candidate_fresh_warm_cache_modeled': {'html_body_bytes': repeat_html['encoded_body_bytes'],
                        'static_requests': 0, 'static_response_body_bytes': 0,
                        'page_body_bytes': repeat_html['encoded_body_bytes'],
                        'assumptions': 'A conforming ordinary browser retains all same-origin private immutable assets, honors freshness, and does not force reload or clear/evict its cache. No browser cache was exercised by this aiohttp probe.'},
                    'candidate_one_file_change': {'changed_filename': 'world-assets.js', 'changed_urls': len(downloads),
                        'unchanged_direct_urls': sum(old_by_name.get(name) == url for name, url in changed_by_name.items()),
                        'measured_changed_asset_requests': len(changed_rows), 'measured_changed_asset_encoded_body_bytes': body_sum(changed_rows),
                        'measured_new_html_body_bytes': changed_html['encoded_body_bytes'],
                        'modeled_warm_page_body_bytes': changed_html['encoded_body_bytes'] + body_sum(changed_rows),
                        'old_startup_snapshot_still_correct': True,
                        'old_hash_status_after_release_restart': old_hash_after_restart['status']},
                    'boundaries': {'unauthenticated_versioned_asset': unauthenticated,
                        'unknown_hash': unknown, 'no_acceptable_encoding': unacceptable,
                        'legacy_asset': legacy, 'legacy_explicit_revalidation': legacy_conditional,
                        'mmo_enter_status': mmo.status, 'mmo_cache_control': mmo.headers.get('Cache-Control'),
                        'user_save_sentinel_preserved': preserved, 'simulation_workers_started': 0},
                    'limitations': ['No production Render request, deployment, bill or host setting changed.',
                        'Body bytes exclude HTTP headers, requests, TLS framing, proxy behavior and Render billing accounting.',
                        'Fresh warm-cache reuse is a header-based model; explicit conditional 304 requests are the measured warm diagnostic.',
                        'Changed-file scenario appends a marker only inside a disposable copied web tree.',
                        'This measures application shell HTTP delivery, not world assets, browser/Qt persistence, native seed reuse or gameplay WebSocket traffic.'],
                }
            finally:
                for client in reversed(clients):
                    await client.close()
    finally:
        sys.modules.pop(baseline.__name__, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='HEAD', help='Explicit prechange Git commit/ref; needed once HEAD contains AppAssets.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError('Existing files are never replaced; choose a new report path.')
    report = asyncio.run(measure(args.baseline_ref))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(str(args.output))


if __name__ == '__main__':
    main()
