"""An immutable, startup snapshot of the trusted application's static files.

This registry never reads worlds, saves or account data. Legacy URLs remain the
server's responsibility; only URLs returned here identify cacheable snapshots.
"""
from dataclasses import dataclass
import gzip
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from urllib.parse import urlsplit


PREFIX = '/app-assets/'
CACHE_CONTROL = 'private, max-age=31536000, immutable'
CONTENT_TYPES = {
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.svg': 'image/svg+xml; charset=utf-8',
    '.ico': 'image/vnd.microsoft.icon',
}
MAX_FILES = 256
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Asset:
    name: str
    digest: str
    body: bytes
    gzip_body: bytes
    gzip_digest: str
    content_type: str

    def representation(self, encoding):
        body = self.gzip_body if encoding == 'gzip' else self.body
        digest = self.gzip_digest if encoding == 'gzip' else self.digest
        return body, '"' + digest + '"'


def accepted_encoding(header):
    """Choose an offered representation, or None when both are forbidden."""
    qualities = {}
    for item in (header or '').split(','):
        parts = [part.strip() for part in item.split(';')]
        coding = parts[0].lower()
        if not coding:
            continue
        quality = 1.0
        for option in parts[1:]:
            key, separator, value = option.partition('=')
            if separator and key.strip().lower() == 'q':
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 0.0
                if not 0 <= quality <= 1:
                    quality = 0.0
        qualities[coding] = quality
    compressed = qualities.get('gzip', qualities.get('*', 0.0))
    # Identity is acceptable by default, except an explicit identity or wildcard
    # exclusion. A positive wildcard does not lower identity's default quality.
    identity = qualities.get('identity', 0.0 if qualities.get('*') == 0 else 1.0)
    if compressed > 0 and compressed >= identity:
        return 'gzip'
    return 'identity' if identity > 0 else None


def _read(path):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise ValueError('Application asset must be a regular file: ' + path.name)
    if before.st_size > MAX_FILE_BYTES:
        raise ValueError('Application asset exceeds size budget: ' + path.name)
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('Application asset changed during snapshot: ' + path.name)
        body = stream.read(MAX_FILE_BYTES + 1)
    after = path.lstat()
    if (len(body) > MAX_FILE_BYTES or
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError('Application asset changed during snapshot: ' + path.name)
    return body


class _ShellReferences(HTMLParser):
    """Replace only actual resource attributes, preserving inline code verbatim."""
    def __init__(self, source, registry):
        super().__init__(convert_charrefs=False)
        self.registry = registry
        self.changes = []
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        key = 'src' if tag == 'script' else 'href' if (
            tag == 'link' and set((attributes.get('rel') or '').lower().split()) &
            {'stylesheet', 'icon'}) else None
        if key is None or not attributes.get(key):
            return
        parsed = urlsplit(attributes[key])
        if parsed.scheme or parsed.netloc:
            return
        name = parsed.path.lstrip('/')
        if name not in self.registry.assets:
            return
        raw = self.get_starttag_text()
        match = re.search(r'\b' + key + r'''\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)''', raw, re.I)
        if match is None:
            return
        url = self.registry.url(name)
        if parsed.fragment:
            url += '#' + parsed.fragment
        line, column = self.getpos()
        start = self.offsets[line - 1] + column
        self.changes.append((start + match.start(1), start + match.end(1),
                             '"' + escape(url, quote=True) + '"'))


class AppAssets:
    def __init__(self, web_root):
        root = Path(web_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Application web directory must be a real directory.')
        assets = {}
        total = 0
        for path in sorted(root.iterdir()):
            if path.suffix not in CONTENT_TYPES:
                continue
            body = _read(path)
            total += len(body)
            if len(assets) >= MAX_FILES or total > MAX_TOTAL_BYTES:
                raise ValueError('Application snapshot exceeds size/count budget.')
            digest = hashlib.sha256(body).hexdigest()
            compressed = gzip.compress(body, compresslevel=6, mtime=0)
            assets[path.name] = Asset(path.name, digest, body,
                                      compressed, hashlib.sha256(compressed).hexdigest(),
                                      CONTENT_TYPES[path.suffix])
        self.assets = MappingProxyType(assets)
        source = _read(root / 'index.html').decode('utf-8')
        parser = _ShellReferences(source, self)
        parser.feed(source)
        parser.close()
        for start, end, replacement in reversed(parser.changes):
            source = source[:start] + replacement + source[end:]
        self._shell = source.encode('utf-8')
        self.release = hashlib.sha256(json.dumps(
            {'shell': hashlib.sha256(self._shell).hexdigest(),
             'assets': [(name, asset.digest) for name, asset in assets.items()]},
            separators=(',', ':')).encode()).hexdigest()

    def url(self, name):
        asset = self.assets[name]
        return PREFIX + asset.digest + '/' + asset.name

    def get(self, digest, name):
        asset = self.assets.get(name)
        return asset if asset is not None and asset.digest == digest else None

    def shell(self):
        return self._shell
