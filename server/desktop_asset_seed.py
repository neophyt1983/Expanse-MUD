"""Read-only public presentation seeds from one exact released desktop world.

There is deliberately no API accepting a path, origin or world identifier.
Unknown hashes never touch the filesystem. The installed portable archive is
size/hash pinned before ZIP parsing; only the reviewed public registry's fixed
entries can be returned. This is optional acceleration, never world authority.
"""
import base64
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import stat
from threading import Lock
from zipfile import BadZipFile, ZipFile

from engine.public_media import PUBLIC_PRESENTATION


APPLICATION_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = 'Expanse-Wild-Lands-1.9.15.expanse'
ARCHIVE_SIZE = 12_454_900
ARCHIVE_SHA256 = 'b4ceb676d0eebcce77d0394e6375cd5e65800eab5c0b8a44c1356cabfe5c76c6'
MAX_SEED_BYTES = 512 * 1024
MAX_TOTAL_SEED_BYTES = 8 * 1024 * 1024
MAX_SEEDS = 32


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _checked(path, *, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Linked installation seed refused.')
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('Unexpected installation seed type.')
    return info


def _released_archive():
    root = Path(APPLICATION_ROOT)
    worlds = root / 'worlds'
    archive = worlds / ARCHIVE_NAME
    parents = [(path, _identity(_checked(path, directory=True))) for path in (root, worlds)]
    before = _checked(archive)
    if before.st_size != ARCHIVE_SIZE:
        raise ValueError('Released seed size mismatch.')
    with archive.open('rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ValueError('Released seed changed while opening.')
        raw = stream.read(ARCHIVE_SIZE + 1)
        after = os.fstat(stream.fileno())
    if (len(raw) != ARCHIVE_SIZE or _identity(after) != _identity(before) or
            _identity(_checked(archive)) != _identity(before)):
        raise ValueError('Released seed changed while reading.')
    if any(_identity(_checked(path, directory=True)) != previous for path, previous in parents):
        raise ValueError('Released seed directory changed.')
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Released seed digest mismatch.')
    return raw


class BundledAssetSeed:
    """Return only approved hash -> base64 bytes, or an empty cache miss."""
    def __init__(self):
        self._approved = {}
        total = 0
        for name, (size, digest, _mime) in PUBLIC_PRESENTATION.items():
            # This is a fixed reviewed registry, not a caller-controlled path.
            if (not isinstance(name, str) or not name.startswith(('assets/', 'images/')) or
                    any(part in ('', '.', '..') for part in name.split('/')) or '\\' in name or
                    type(size) is not int or not 0 <= size <= MAX_SEED_BYTES or
                    not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                continue
            total += size
            if len(self._approved) >= MAX_SEEDS or total > MAX_TOTAL_SEED_BYTES:
                self._approved.clear()
                break
            self._approved[digest] = (name, size)
        self._loaded = False
        self._blobs = {}
        self._lock = Lock()

    def _load(self):
        # Validate the complete released bytes before allowing ZipFile to parse
        # its central directory. Never enumerate or extract archive members.
        raw = _released_archive()
        blobs = {}
        with ZipFile(BytesIO(raw)) as archive:
            for digest, (name, size) in self._approved.items():
                # A newer registry may approve additional or changed media
                # that this older, authentic release does not contain. Those
                # entries miss independently; unchanged reviewed bytes remain
                # useful. The archive itself has already passed its full pin.
                try:
                    info = archive.getinfo(name)
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    if info.file_size != size or kind not in (0, stat.S_IFREG):
                        continue
                    with archive.open(info) as stream:
                        value = stream.read(size + 1)
                    if len(value) != size or hashlib.sha256(value).hexdigest() != digest:
                        continue
                except (OSError, ValueError, KeyError, BadZipFile, RuntimeError, NotImplementedError):
                    continue
                blobs[digest] = base64.b64encode(value).decode('ascii')
        self._blobs = blobs

    def get(self, digest):
        if not isinstance(digest, str) or len(digest) != 64 or digest not in self._approved:
            return ''
        with self._lock:
            if not self._loaded:
                self._loaded = True
                try:
                    self._load()
                except (OSError, ValueError, KeyError, BadZipFile, RuntimeError, NotImplementedError):
                    self._blobs.clear()
            return self._blobs.get(digest, '')
