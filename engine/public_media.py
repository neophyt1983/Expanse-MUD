"""Reviewed public presentation bytes, negotiated by a joined player on demand.

The 15 exact Wild Lands 1.9.15 files below were inspected: terrain index and
tiles; body/activity and nine gear atlases (PNG plus generic rendering fields);
the common street cue and thunder sound. No room/item/NPC catalogue, wildlife
subject list, regional/mood soundtrack, chronicle or update data is published.
New/edited files stay transient until their exact bytes receive a code review.

This is separate from the application's static-file snapshot. It never scans a
world, copies a world catalogue, or hashes media during map/chunk construction.
Negotiation runs in a worker thread; unchanged file identities reuse a bounded
verification result. The browser must verify the complete downloaded digest,
because a world editor can change files after negotiation.
"""
from contextlib import contextmanager
import base64
import hashlib
import os
from pathlib import Path
import stat
from threading import Lock
from types import MappingProxyType
from uuid import uuid4


PROTOCOL = 1
MAX_SIZE = 16 * 1024 * 1024
# These are source/migration documents, never a player's rendering payload.
# This delivery rule does not alter archive import/export preservation rules.
PRIVATE_NAMESPACES = ('assets/updates/', 'assets/chronicles/')
_UNSAFE_COMPONENT_CHARACTERS = frozenset('<>:"\\|?*')
_DEVICE_NAMES = frozenset(('con', 'prn', 'aux', 'nul', 'clock$', 'conin$', 'conout$',
                           *(f'com{i}' for i in range(1, 10)),
                           *(f'lpt{i}' for i in range(1, 10)),
                           *(f'{prefix}{digit}' for prefix in ('com', 'lpt') for digit in '¹²³')))
# path: (exact byte size, lowercase SHA-256, MIME type)
PUBLIC_PRESENTATION = MappingProxyType({
    'assets/terrain/index.json': (467, 'd29a031366502384ba4998848ae99e615b8d14d0c4c68813ef8d290e3e7bab34', 'application/json'),
    'assets/terrain/tiles.png': (119423, '6c83564024cd3f4ce6f602c6405d52ee4d4478a5cefde61363bcb02401b5b84b', 'image/png'),
    'assets/sprites/sprite-bodies.json': (6561, '4edd4dfc69d5656ca501dd1d70fa1e8ca86f91889ac6305ed658cfb78e148987', 'application/json'),
    'assets/sprites/sprite-activities.json': (1576, '7f8d0353bad17546a41407cd1b31eac2504c162609109bb320f076332ba6bfbb', 'application/json'),
    'assets/sprites/sprite-gear-short-slim.json': (300768, 'd8ff5a9b46d9a01fa067849e346eb064be21af0f08dad361fe0fbace52f11756', 'application/json'),
    'assets/sprites/sprite-gear-short-average.json': (301248, 'a6907dcc8484bd6858b7ed7d5ae43b9d4fce99523c18375b200a672f81c0ee93', 'application/json'),
    'assets/sprites/sprite-gear-short-broad.json': (302792, 'c70ce5bb97bafdb9d9d7d5d2f76bc709a2653dcacd6fad6aedaf15ac8885b12e', 'application/json'),
    'assets/sprites/sprite-gear-average-slim.json': (309896, '56fb821ab51a2c1a6074ded4f99e33ea6bce0f6aa7f868cece49c4a52efc03e3', 'application/json'),
    'assets/sprites/sprite-gear-average-average.json': (311600, '1e3eb16d19a7cc4c94db2db984af5e93f6a9d205cbd44c022e3c643038aa1c23', 'application/json'),
    'assets/sprites/sprite-gear-average-broad.json': (312716, 'd965a5f5efe335302e536a3f53f06f33e979ebf66490242463d06e26b245c3c0', 'application/json'),
    'assets/sprites/sprite-gear-tall-slim.json': (317156, '48db61e4b4078b77b62f58c63144cf93fb8397d6c446b1948b723675e01f4392', 'application/json'),
    'assets/sprites/sprite-gear-tall-average.json': (318564, '7d8abe25a1c8abcb4b609c0bd483ae7510a4ddbffb76db1b90b3f57e91f25d61', 'application/json'),
    'assets/sprites/sprite-gear-tall-broad.json': (318636, 'd0ba778f85b7fc79f1783fc81c716fb5abbd0a92b5272b01bfe55ab3639139b9', 'application/json'),
    'assets/audio/cue_street.ogg': (5070, '45ac36087ab17e3e0c20744c9ef7a337f7e8cf09d2e1452e6a178c0f1bc0ca16', 'audio/ogg'),
    'assets/audio/thunder.ogg': (11127, 'd26a720aa0095d29d779c74aa7882138f76f81371b800472bb4962ffacf3ebad', 'audio/ogg'),
})
# The current renderers consume only these JSON documents. Their edited bytes
# may be transported transiently; no other authored JSON becomes player media.
RENDER_JSON = frozenset(name for name, row in PUBLIC_PRESENTATION.items()
                        if row[2] == 'application/json') | {'assets/sprites/sprite-wildlife.json'}


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _file_identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size


def _windows_filesystem():
    return os.name == 'nt'


def _unaliased(root, name):
    if not _windows_filesystem():
        return
    # Resolve the trusted host root first: Windows may itself provide a short
    # TEMP/install root. Only requested relative components need exact spelling.
    canonical_root = os.path.realpath(root, strict=True)
    requested = os.path.abspath(os.path.join(canonical_root, *name.split('/')))
    canonical = os.path.realpath(requested, strict=True)
    if os.path.normcase(requested) != os.path.normcase(canonical):
        raise OSError('Aliased media path refused.')


def _windows_readonly(path):
    """Own a no-reparse read handle that excludes concurrent writes/deletes."""
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class AttributeTagInfo(ctypes.Structure):
        _fields_ = [('attributes', wintypes.DWORD), ('reparse_tag', wintypes.DWORD)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    information = kernel.GetFileInformationByHandleEx
    information.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    information.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    # GENERIC_READ, FILE_SHARE_READ only, OPEN_EXISTING, and
    # FILE_FLAG_OPEN_REPARSE_POINT. Existing writers are incompatible too.
    handle = create(os.fspath(path), 0x80000000, 0x00000001, None,
                    3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = True
    try:
        attributes = AttributeTagInfo()
        if not information(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
            raise ctypes.WinError(ctypes.get_last_error())
        if attributes.attributes & (0x400 | 0x10):
            raise OSError('Media handle must be a regular file without reparse attributes.')
        # The descriptor takes ownership only after open_osfhandle succeeds.
        # _portable_regular closes it on every successful/exceptional exit.
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        owned = False
        return descriptor
    finally:
        if owned:
            close(handle)


def _portable_descriptor(path):
    if _windows_filesystem():
        return _windows_readonly(path)
    return os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                   | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))


def _linked(info):
    if os.name == 'nt' and not hasattr(info, 'st_file_attributes'):
        raise OSError('Reparse point detection is unavailable.')
    return stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400


def _directory_descriptors():
    return (all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
            and os.open in os.supports_dir_fd)


@contextmanager
def _portable_regular(root, name):
    _unaliased(root, name)
    paths = [Path(root)]
    for part in name.split('/'):
        paths.append(paths[-1] / part)
    before = [path.lstat() for path in paths]
    if any(_linked(info) for info in before):
        raise OSError('Linked media path refused.')
    if not all(stat.S_ISDIR(info.st_mode) for info in before[:-1]) or not stat.S_ISREG(before[-1].st_mode):
        raise OSError('Expected a regular media path.')
    descriptor = _portable_descriptor(paths[-1])
    try:
        opened = os.fstat(descriptor)
        if _linked(opened) or _file_identity(opened) != _file_identity(before[-1]):
            raise OSError('Media changed before verification.')
        # Windows ctime can be creation time. Rehash on each *negotiation* in
        # this fallback rather than trusting timestamps restored by an editor.
        # Maps and chunk delivery still never hash a file.
        yield descriptor, opened, False
        after = [path.lstat() for path in paths]
        # Windows pathname metadata and descriptor metadata can expose different
        # timestamps immediately after rewriting a closed file. Compare path
        # identities across all stages, and content revisions fstat-to-fstat.
        if (any(_linked(info) for info in after)
                or [_identity(info) for info in before[:-1]] != [_identity(info) for info in after[:-1]]
                or _file_identity(after[-1]) != _file_identity(opened)
                or _identity(os.fstat(descriptor)) != _identity(opened)):
            raise OSError('Media changed during verification.')
    finally:
        os.close(descriptor)


@contextmanager
def _open_regular(root, name):
    if not _directory_descriptors():
        with _portable_regular(root, name) as opened:
            yield opened
        return
    descriptors = []
    try:
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        parts = name.split('/')
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(parent)
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        descriptors.append(leaf)
        info = os.fstat(leaf)
        if not stat.S_ISREG(info.st_mode):
            raise OSError('Expected a regular media file.')
        yield leaf, info, True
        # Check the currently named path as well as the open file. A concurrent
        # rename or symlink replacement must not authorize a different file.
        current = Path(root)
        for part in ('', *parts):
            if part:
                current = current / part
            now = current.lstat()
            if _linked(now):
                raise OSError('Linked media path refused.')
        if _identity(os.fstat(leaf)) != _identity(info) or _identity(now) != _identity(info):
            raise OSError('Media changed during verification.')
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


class PublicMedia:
    """A world-scoped, at most 15-entry cache of exact reviewed-byte checks."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self._checked = {}
        self._lock = Lock()

    def info(self, name):
        expected = PUBLIC_PRESENTATION.get(name) if isinstance(name, str) else None
        if expected is None:
            return None
        size, digest, mime = expected
        if not 0 <= size <= MAX_SIZE:
            return None
        try:
            with self._lock, _open_regular(self.folder, name) as (descriptor, before, reusable):
                identity = _identity(before)
                cached = self._checked.get(name)
                if reusable and cached and cached[0] == identity:
                    approved = cached[1]
                else:
                    approved = False
                    if before.st_size == size:
                        checksum = hashlib.sha256()
                        remaining = size
                        while remaining:
                            raw = os.read(descriptor, min(64 * 1024, remaining))
                            if not raw:
                                break
                            checksum.update(raw)
                            remaining -= len(raw)
                        approved = remaining == 0 and not os.read(descriptor, 1) and checksum.hexdigest() == digest
                    self._checked[name] = (identity, approved)
            return {'scope': 'public-presentation', 'sha256': digest, 'size': size, 'mime': mime} if approved else None
        except (OSError, ValueError):
            self._checked.pop(name, None)
            return None


def correlation(value):
    if isinstance(value, str) and len(value) <= 100:
        return value
    if type(value) is int and abs(value) <= 2**53 - 1:
        return value
    return None


def legacy_presentation(name):
    from engine.world_package import media
    if not media(name):
        return False
    parts = name.split('/')
    # A single portable spelling prevents local Windows path aliases from
    # changing the scope of a reviewed media request. This is a delivery rule,
    # not an archive filename/import validation change.
    if any(part.startswith('.')
           or any(character in _UNSAFE_COMPONENT_CHARACTERS for character in part)
           or part.endswith((' ', '.'))
           or part.split('.', 1)[0].rstrip(' ').casefold() in _DEVICE_NAMES
           for part in parts):
        return False
    if name.casefold().startswith(PRIVATE_NAMESPACES):
        return False
    return not name.casefold().endswith('.json') or name in RENDER_JSON


def presentation_packet(folder, name, offset):
    """Bounded legacy chunks with the same portable scope and link policy."""
    from engine.world_package import CHUNK, CONTENT_TYPES
    if not isinstance(name, str) or len(name) > 512:
        name = None
    if type(offset) is not int or not 0 <= offset <= 32 * 1024 * 1024:
        offset = None
    reply = {'type': 'world_asset', 'name': name, 'offset': offset}
    if not legacy_presentation(name) or type(offset) is not int or not 0 <= offset <= 32 * 1024 * 1024:
        return {**reply, 'missing': True}
    try:
        with _open_regular(folder, name) as (descriptor, info, _):
            if not 0 <= offset <= info.st_size <= 32 * 1024 * 1024:
                return {**reply, 'missing': True}
            os.lseek(descriptor, offset, os.SEEK_SET)
            raw = os.read(descriptor, CHUNK)
            result = {**reply, 'size': info.st_size,
                      'mime': CONTENT_TYPES[Path(name).suffix.lower()],
                      'data': base64.b64encode(raw).decode('ascii')}
        return result
    except (OSError, ValueError):
        return {**reply, 'missing': True}


def invalidate(world):
    """Invalidate browser and host state after an explicit world publication."""
    world.media_session = uuid4().hex
    world._media_folder = str(Path(world.game_dir))
    world._public_media = None
    return world.media_session


def session(world):
    # A first manual save may publish the same world object into a new folder.
    # This is an in-memory comparison only; never poll or hash on every map.
    if (not getattr(world, 'media_session', None)
            or getattr(world, '_media_folder', None) != str(Path(world.game_dir))):
        return invalidate(world)
    return world.media_session
