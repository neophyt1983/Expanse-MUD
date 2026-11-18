#!/usr/bin/env python3
"""Supplement the canonical asset audit with explicit public GET/header probes.

Uses the existing measurement tool for optional local authenticated checks.
No production login, worker, configuration change or client cache is performed.
Only aggregate sizes and selected headers are exported, not response bodies.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.measure_asset_delivery import local_http_probe

HEADERS = {'cache-control', 'etag', 'last-modified', 'content-length',
           'content-encoding', 'content-type', 'vary', 'age',
           'cf-cache-status', 'x-expanse-server-build'}


def public_probe(origin):
    parsed = urllib.parse.urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None):
        raise ValueError('Use an HTTPS origin without credentials, path or query.')
    rows = []
    for path in ('/healthz', '/', '/world-assets.js', '/visual-map.js'):
        request = urllib.request.Request(origin.rstrip('/') + path,
            headers={'Accept-Encoding': 'identity', 'User-Agent': 'Expanse-read-only-bandwidth-audit/1'})
        try:
            response = urllib.request.urlopen(request, timeout=25)
        except urllib.error.HTTPError as exc:
            response = exc
        except OSError as exc:
            rows.append({'path': path, 'unavailable': type(exc).__name__})
            continue
        with response:
            raw = response.read(1024 * 1024 + 1)
            rows.append({'path': path, 'status': response.code, 'body_bytes': len(raw),
                'truncated': len(raw) > 1024 * 1024,
                'headers': {k.lower(): v for k, v in response.headers.items() if k.lower() in HEADERS}})
    return {'origin': origin, 'requests': rows, 'authenticated': False,
            'scope': 'read-only public probes; no account, session or private-world requests'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-origin', help='Explicit HTTPS origin for unauthenticated GET probes')
    parser.add_argument('--local-http', action='store_true', help='Use canonical temporary local HTTP probe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.public_origin and not args.local_http:
        parser.error('Choose an explicit public origin, local probe, or both.')
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError('Choose a new report path; existing files are never replaced.')
    report = {'schema_version': 1, 'measured_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'runtime_caching_changed': False, 'mmo_gate_changed': False}
    if args.public_origin:
        report['public_probe'] = public_probe(args.public_origin)
    if args.local_http:
        report['local_http'] = asyncio.run(local_http_probe(ROOT))
    report['limitations'] = ['No authenticated live Render session or billing access',
        'No browser cold/warm trace, compression/frame measurement or actual monthly charge',
        'The local gate check does not certify a shared-world release or identify the deployed commit']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(str(args.output))


if __name__ == '__main__':
    main()
