#!/usr/bin/env python3
"""Read-only local asset baseline; this does not implement or enable caching.

Run from a checkout, optionally supplying a named .expanse archive. HTTP probes
use a temporary local account/data directory and never contact Render. Gzip and
optional Brotli sizes are compression opportunities, not observed wire bytes.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit
from zipfile import ZipFile

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))
from engine.world_package import CHUNK, CONTENT_TYPES, media
from engine.history_templates import MAX_FILES as MAX_ARCHIVE_FILES, MAX_TOTAL as MAX_ARCHIVE_BYTES

STATIC_SUFFIXES = {'.css', '.js', '.svg', '.ico'}
MAX_ASSET_BYTES = 32 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sizes(raw):
    row = {'raw_bytes': len(raw), 'gzip_opportunity_bytes': len(gzip.compress(raw, mtime=0))}
    # Brotli is optional; do not install dependencies or equate a local encoded
    # size with the transfer coding selected by the host/proxy/browser.
    if importlib.util.find_spec('brotli'):
        import brotli
        row['brotli_opportunity_bytes'] = len(brotli.compress(raw))
    else:
        row['brotli_opportunity_bytes'] = None
    return row


def total(rows):
    return {'files': len(rows), **{
        key: (sum(row[key] for row in rows) if all(row.get(key) is not None for row in rows) else None)
        for key in ('raw_bytes', 'gzip_opportunity_bytes', 'brotli_opportunity_bytes')
    }}


def combined_totals(*groups):
    return {'files': sum(group['files'] for group in groups), **{
        key: (sum(group[key] for group in groups) if all(group.get(key) is not None for group in groups) else None)
        for key in ('raw_bytes', 'gzip_opportunity_bytes', 'brotli_opportunity_bytes')
    }}


class PageReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        value = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split() else None
        if value:
            url = urlsplit(value)
            if not url.netloc and not url.scheme:
                self.paths.add(url.path.lstrip('/'))


def static_inventory(repo):
    repo = Path(repo)
    rows = []
    for path in sorted((repo / 'web').iterdir()):
        if path.suffix not in STATIC_SUFFIXES or not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Static inventory refuses linked files: ' + str(path))
        raw = path.read_bytes()
        rows.append({'path': 'web/' + path.name, 'url': '/' + path.name, 'sha256': digest(raw), **sizes(raw)})
    page = repo / 'web' / 'index.html'
    raw = page.read_bytes()
    references = PageReferences()
    references.feed(raw.decode('utf-8'))
    initial = [row for row in rows if Path(row['path']).name in references.paths]
    available = {Path(row['path']).name for row in rows}
    html_sizes = sizes(raw)
    return {
        'served_static_allowlist': total(rows),
        'play_html': {'path': 'web/index.html', **html_sizes},
        'play_html_direct_static_references': total(initial),
        'play_html_and_direct_static_references': combined_totals({'files': 1, **html_sizes}, total(initial)),
        'unresolved_local_references': sorted(references.paths - available),
        'files': rows,
    }


def category(name):
    if name.startswith('assets/updates/'):
        return 'server_update_payload_excluded_from_presentation_cache'
    if name.startswith(('assets/audio/', 'assets/terrain/', 'assets/sprites/', 'images/')):
        return 'presentation_candidate_pending_host_authorization'
    return 'other_transport_eligible_requires_review'


def websocket_model(name, length):
    """Current uncompressed JSON bodies with request_id=1; excludes framing/TLS.

    This is not network usage: negotiated WebSocket compression and activity
    decide actual transferred bytes. The browser asks for one asset at a time.
    """
    response_bytes = request_bytes = 0
    chunks = max(1, math.ceil(length / CHUNK))
    mime = CONTENT_TYPES[Path(name).suffix.lower()]
    for offset in range(0, max(length, 1), CHUNK):
        count = min(CHUNK, length - offset)
        response = dict(type='world_asset', name=name, offset=offset, size=length, mime=mime, data='', request_id=1)
        response_bytes += len(json.dumps(response).encode('utf-8')) + 4 * math.ceil(count / 3)
        request = dict(command='world asset', name=name, offset=offset, request_id=1)
        request_bytes += len(json.dumps(request, separators=(',', ':')).encode('utf-8'))
    return {'chunks': chunks, 'uncompressed_response_json_bytes': response_bytes,
            'uncompressed_request_json_bytes': request_bytes}


def world_inventory(archive):
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file():
        raise ValueError('Use the explicit regular .expanse archive file.')
    rows = []
    with ZipFile(archive) as bundle:
        infos = bundle.infolist()
        # Inspect central-directory limits before opening any member, including
        # members outside the media allowlist. Match the import/snapshot budget.
        if len(infos) > MAX_ARCHIVE_FILES or sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise ValueError('Archive size/count budget exceeded before decompression.')
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive paths refused.')
        for info in infos:
            if not media(info.filename):
                continue
            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in (0, stat.S_IFREG):
                raise ValueError('Non-regular media archive entry refused.')
            row = {'path': info.filename, 'category': category(info.filename),
                   'raw_bytes': info.file_size, 'archive_compressed_bytes': info.compress_size,
                   'transport_readable_with_32_mib_limit': info.file_size <= MAX_ASSET_BYTES}
            if info.file_size <= MAX_ASSET_BYTES:
                with bundle.open(info) as stream:
                    raw = stream.read(MAX_ASSET_BYTES + 1)
                if len(raw) != info.file_size:
                    raise ValueError('Media size mismatch: ' + info.filename)
                row.update(sha256=digest(raw), **sizes(raw), **websocket_model(info.filename, len(raw)))
            rows.append(row)
    groups = {}
    for key in sorted({row['category'] for row in rows}):
        selected = [row for row in rows if row['category'] == key]
        groups[key] = {**total(selected), 'archive_compressed_bytes': sum(row['archive_compressed_bytes'] for row in selected),
                       'uncompressed_response_json_bytes': sum(row.get('uncompressed_response_json_bytes', 0) for row in selected),
                       'uncompressed_request_json_bytes': sum(row.get('uncompressed_request_json_bytes', 0) for row in selected)}
    return {'archive': archive.name, 'archive_bytes': archive.stat().st_size,
            'archive_sha256': digest(archive.read_bytes()),
            'transport_eligible_media': total(rows), 'categories': groups, 'files': rows,
            'websocket_model_assumptions': {'request_id': 1, 'request_id_scope': 'fixed integer placeholder for every asset/chunk',
                                          'response_json': 'Python json.dumps defaults',
                                          'request_json': 'compact JSON',
                                          'observed_network_or_billable_bytes': False},
            'limits': ['Inventory is not a session trace or permission grant.',
                       'Presentation candidates still require explicit host allowlisting.',
                       'Update payloads are not presentation cache candidates.',
                       'JSON byte model excludes WebSocket compression, framing, TLS and unrelated gameplay.']}


def presentation_comparison(before, after):
    eligible = 'presentation_candidate_pending_host_authorization'
    old = {row['path']: row for row in before['files'] if row['category'] == eligible}
    new = {row['path']: row for row in after['files'] if row['category'] == eligible}
    for row in [*old.values(), *new.values()]:
        sha = row.get('sha256')
        if (row.get('transport_readable_with_32_mib_limit') is False or not isinstance(sha, str)
                or len(sha) != 64 or any(character not in '0123456789abcdef' for character in sha)):
            raise ValueError('Presentation asset lacks a verified SHA-256 or exceeds the 32 MiB transport bound; '
                             'comparison refused: ' + row['path'])
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    changed = sorted(name for name in old.keys() & new.keys() if old[name].get('sha256') != new[name].get('sha256'))
    unchanged = sorted((old.keys() & new.keys()) - set(changed))
    fetched = [new[name] for name in added + changed]
    return {
        'baseline_archive': before['archive'], 'baseline_archive_sha256': before['archive_sha256'],
        'candidate_archive': after['archive'], 'candidate_archive_sha256': after['archive_sha256'],
        'candidate_archive_bytes': after['archive_bytes'],
        'candidate_transport_eligible_media': after['transport_eligible_media'],
        'candidate_categories': after['categories'],
        'presentation_files_unchanged': len(unchanged), 'presentation_files_added': len(added),
        'presentation_files_changed': len(changed), 'presentation_files_removed': len(removed),
        'ideal_warm_cache_missing_or_changed_raw_bytes': sum(row['raw_bytes'] for row in fetched),
        'added': added, 'removed': removed, 'changed': changed, 'unchanged': unchanged,
        'limits': ['Per-file SHA-256 comparison of explicit presentation candidates only.',
                   'Ideal warm-cache transfer assumes all unchanged objects already exist and verify; it is not current client behavior.',
                   'A host-supplied authorized manifest, network headers and any application update still require separate transfer.'],
    }


async def local_http_probe(repo):
    """Exercise the real checkout server without opening any game or user saves."""
    from aiohttp import CookieJar
    from aiohttp.test_utils import TestClient, TestServer
    import render_server
    root = Path(repo).resolve()
    rows = []
    with tempfile.TemporaryDirectory(prefix='expanse-assets-probe-') as temporary:
        settings = {'EXPANSE_PUBLIC_URL': 'http://127.0.0.1:10000', 'EXPANSE_DATA_DIR': temporary,
                    'EXPANSE_GUESTS_JSON': '[]', 'EXPANSE_OWNER_NAME': 'Asset Probe',
                    'EXPANSE_OWNER_PASSWORD': 'temporary-asset-probe-password'}
        with patch.dict(os.environ, settings, clear=True), patch.object(render_server, 'ROOT', root):
            app = render_server.make_app()
            async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
                anonymous = await client.get('/world-assets.js')
                anonymous_status = anonymous.status
                await anonymous.read()
                response = await client.post('/login', data={'name': settings['EXPANSE_OWNER_NAME'], 'password': settings['EXPANSE_OWNER_PASSWORD']},
                                             headers={'Origin': settings['EXPANSE_PUBLIC_URL']}, allow_redirects=False)
                if response.status != 303:
                    raise RuntimeError('Local temporary owner login failed.')
                gated = await client.post('/enter', data={'mode': 'mmo'},
                                          headers={'Origin': settings['EXPANSE_PUBLIC_URL']}, allow_redirects=False)
                mmo_status = gated.status
                await gated.read()
                for path in sorted((root / 'web').iterdir()):
                    if path.suffix not in STATIC_SUFFIXES or not path.is_file():
                        continue
                    url = '/' + path.name
                    first = await client.get(url, headers={'Accept-Encoding': 'gzip, deflate, br'}, auto_decompress=False)
                    raw = await first.read()
                    repeated = await client.get(url, headers={'Accept-Encoding': 'gzip, deflate, br'}, auto_decompress=False)
                    repeat_raw = await repeated.read()
                    row = {'url': url, 'status': first.status, 'response_body_bytes': len(raw),
                           'cache_control': first.headers.get('Cache-Control'),
                           'content_encoding': first.headers.get('Content-Encoding', 'identity'),
                           'etag_present': bool(first.headers.get('ETag')),
                           'repeat_without_validator_status': repeated.status,
                           'repeat_without_validator_body_bytes': len(repeat_raw)}
                    if path.name == 'world-assets.js' and first.headers.get('ETag'):
                        conditional = await client.get(url, headers={'If-None-Match': first.headers['ETag']}, auto_decompress=False)
                        row['explicit_conditional_status'] = conditional.status
                        row['explicit_conditional_body_bytes'] = len(await conditional.read())
                    rows.append(row)
    return {'scope': 'local checkout only; temporary owner; no worker/game started',
            'unauthenticated_static_status': anonymous_status,
            'mmo_enter_status': mmo_status,
            'files': rows, 'response_body_bytes': sum(row['response_body_bytes'] for row in rows),
            'repeat_without_validator_body_bytes': sum(row['repeat_without_validator_body_bytes'] for row in rows),
            'limits': ['No live Render traffic, proxy compression, TLS bytes, browser cache trace or billing was measured.',
                       'Explicit conditional request is a diagnostic; it is not evidence browsers reuse no-store responses.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=REPOSITORY)
    parser.add_argument('--world', type=Path, help='Explicit .expanse archive; label its version in the resulting report.')
    parser.add_argument('--compare-world', type=Path, help='Compare presentation hashes with a second archive; requires --world.')
    parser.add_argument('--probe-local-http', action='store_true', help='Probe an ephemeral local Render adapter with dummy credentials.')
    parser.add_argument('--output', type=Path, help='Optional new JSON report path; existing files are never replaced.')
    args = parser.parse_args(argv)
    if args.compare_world and not args.world:
        parser.error('--compare-world requires --world')
    repo = args.repo.resolve()
    result = {'schema_version': 1, 'scope': 'read-only local asset measurement; caching and MMO remain unchanged',
              'source_commit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
              'static': static_inventory(repo)}
    if args.world:
        result['world'] = world_inventory(args.world)
        if args.compare_world:
            result['presentation_comparison'] = presentation_comparison(result['world'], world_inventory(args.compare_world))
    if args.probe_local_http:
        result['local_http'] = asyncio.run(local_http_probe(repo))
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        # Saving a measurement must never overwrite a save, account DB, world,
        # prior report, or any other existing user file.
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
        print(str(args.output.resolve()))
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
