"""Bounded local file access, including Windows paths without directory fds."""
from contextlib import contextmanager
from pathlib import Path
import os
import secrets
import stat


def checked(path, *, directory=False):
    path = Path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Linked paths are not supported: ' + str(path))
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid:
        raise ValueError('Unexpected file type: ' + str(path))
    return info


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def read_path(path, limit):
    path = Path(path)
    parent = checked(path.parent, directory=True)
    before = checked(path)
    if before.st_size > limit:
        raise ValueError('File exceeds limit: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if identity(before) != identity(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError('File changed during read: ' + str(path))
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or identity(before) != identity(after) or identity(before) != identity(checked(path)):
        raise ValueError('File changed or exceeds limit: ' + str(path))
    if identity(parent) != identity(checked(path.parent, directory=True)):
        raise ValueError('Directory changed during read')
    return raw


@contextmanager
def world_directory(parent, slug):
    if hasattr(os, 'O_DIRECTORY'):
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fd = os.open(slug, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        try:
            yield fd
        finally:
            os.close(fd)
    else:
        checked(parent, directory=True)
        folder = Path(parent) / slug
        checked(folder, directory=True)
        yield folder


def read(directory, name, limit):
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('Expected a filename')
    try:
        if isinstance(directory, Path):
            return read_path(directory / name, limit)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Expected a regular file: ' + name)
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('File exceeds limit: ' + name)
        return raw


def write(directory, name, raw):
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('Expected a filename')
    temp = '.edit-' + secrets.token_hex(12)
    portable = isinstance(directory, Path)
    if portable:
        before = checked(directory, directory=True)
    path = directory / temp if portable else temp
    kwargs = {} if portable else {'dir_fd': directory}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600, **kwargs)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if portable:
            after = checked(directory, directory=True)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError('Directory changed during write')
            os.replace(path, directory / name)
        else:
            os.replace(temp, name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(path, **kwargs)
        except FileNotFoundError:
            pass
