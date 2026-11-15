#!/usr/bin/env python3
"""Read-only overwrite check for the named files in this Expanse update.

This guard prevents known overwrite clashes. It is not a full compatibility,
security, or live-service certification, and it cannot protect edits made after
the check. No repository file is changed, extracted, imported, or executed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from zipfile import BadZipFile, ZipFile


MAX_SOURCE_BYTES = 2 * 1024 * 1024
ANCHOR = 'engine/build_info.py'
HASH = re.compile(r'[0-9a-f]{64}\Z')


class InvalidInput(ValueError):
    pass


def relative_name(value, *, directory=False):
    if not isinstance(value, str) or not value:
        raise InvalidInput('A file path is missing or invalid.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise InvalidInput('Control characters are not allowed in file paths.')
    if '\\' in value or ':' in value or '\x00' in value:
        raise InvalidInput('A file path uses an unsafe separator or drive prefix.')
    name = value[:-1] if directory and value.endswith('/') else value
    if not name or any(part in ('', '.', '..') for part in name.split('/')):
        raise InvalidInput('Absolute paths and path traversal are not allowed.')
    return name


def regular_file(root, name, *, optional=False):
    """Read a known relative file without following a symlink out of the tree."""
    name = relative_name(name)
    current = root
    parts = name.split('/')
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if optional:
                return None
            raise InvalidInput('Missing required file: ' + name) from None
        if stat.S_ISLNK(info.st_mode):
            raise InvalidInput('Symbolic links are not accepted for source paths: ' + name)
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise InvalidInput('A parent path is not a directory: ' + name)
    if not stat.S_ISREG(info.st_mode):
        raise InvalidInput('Expected a regular source file: ' + name)
    if not current.resolve().is_relative_to(root.resolve()):
        raise InvalidInput('A source file is outside the selected directory: ' + name)
    if info.st_size > MAX_SOURCE_BYTES:
        raise InvalidInput('Source exceeds the 2 MiB limit: ' + name)
    with current.open('rb') as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    after = current.lstat()
    if len(data) > MAX_SOURCE_BYTES:
        raise InvalidInput('Source exceeds the 2 MiB limit: ' + name)
    if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise InvalidInput('File changed during inspection; run the check again: ' + name)
    return data


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput('RELEASE.json contains a duplicate field: ' + key)
        result[key] = value
    return result


def manifest(package):
    raw = regular_file(package, 'RELEASE.json')
    value = json.loads(raw, object_pairs_hook=unique_json)
    records = value.get('source_files') if isinstance(value, dict) else None
    if not isinstance(records, list) or not records:
        raise InvalidInput('RELEASE.json needs a nonempty source_files list.')
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise InvalidInput('Invalid source record in RELEASE.json.')
        name = relative_name(record.get('path'))
        if name in seen:
            raise InvalidInput('Duplicate source target in RELEASE.json: ' + name)
        seen.add(name)
        if not isinstance(record.get('updated_sha256'), str) or not HASH.fullmatch(record['updated_sha256']):
            raise InvalidInput('Invalid updated SHA-256 for ' + name)
        accepted = record.get('accepted_before_upload_sha256')
        if not isinstance(accepted, list) or any(not isinstance(item, str) or not HASH.fullmatch(item) for item in accepted):
            raise InvalidInput('Invalid accepted SHA-256 list for ' + name)
        if type(record.get('may_be_absent')) is not bool:
            raise InvalidInput('may_be_absent must be true or false for ' + name)
    return records


def verify_payload(package, records):
    payload = package / 'github-upload'
    if payload.is_symlink() or not payload.is_dir():
        raise InvalidInput('The update needs a real github-upload directory beside RELEASE.json.')
    expected = {record['path'] for record in records}
    actual = set()
    for directory, folders, files in os.walk(payload, followlinks=False):
        folder = Path(directory)
        for name in folders + files:
            path = folder / name
            if path.is_symlink():
                raise InvalidInput('Symbolic links are not accepted in github-upload.')
        for name in files:
            actual.add((folder / name).relative_to(payload).as_posix())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = (' Missing: ' + ', '.join(missing) + '.') if missing else ''
        if extra:
            detail += ' Unexpected: ' + ', '.join(extra) + '.'
        raise InvalidInput('github-upload does not match RELEASE.json.' + detail)
    for record in records:
        data = regular_file(payload, record['path'])
        if hashlib.sha256(data).hexdigest() != record['updated_sha256']:
            raise InvalidInput('Update package integrity failed: ' + record['path'])


def directory_sources(source, records):
    if source.is_symlink():
        raise InvalidInput('Use the repository directory itself, not a symbolic link.')
    # The folder argument names the repository root, not its containing folder.
    regular_file(source, ANCHOR)
    return {record['path']: regular_file(source, record['path'], optional=record['may_be_absent'])
            for record in records}


def zip_sources(source, records):
    if source.is_symlink():
        raise InvalidInput('Use the repository ZIP itself, not a symbolic link.')
    with ZipFile(source) as archive:
        infos = archive.infolist()
        raw_names = [info.orig_filename for info in infos]
        if len(raw_names) != len(set(raw_names)):
            raise InvalidInput('The repository ZIP contains duplicate paths.')
        entries = {}
        nodes = {}
        for info in infos:
            name = relative_name(info.orig_filename, directory=info.is_dir())
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode):
                raise InvalidInput('The repository ZIP contains a symbolic link: ' + name)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise InvalidInput('The repository ZIP contains a special filesystem entry: ' + name)
            if name in nodes:
                raise InvalidInput('The repository ZIP contains a file/directory path collision: ' + name)
            nodes[name] = info.is_dir()
            if not info.is_dir():
                entries[name] = info
        for name in nodes:
            parts = name.split('/')
            if any(nodes.get('/'.join(parts[:index])) is False for index in range(1, len(parts))):
                raise InvalidInput('A file is used as a directory in the repository ZIP: ' + name)
        prefixes = {name[:-len(ANCHOR)] for name in entries
                    if name == ANCHOR or name.endswith('/' + ANCHOR)}
        if len(prefixes) > 1:
            raise InvalidInput('The repository ZIP contains ambiguous repository roots.')
        if len(prefixes) == 1:
            prefix = next(iter(prefixes))
        else:
            raise InvalidInput('Cannot find a repository root containing ' + ANCHOR + '.')
        result = {}
        for record in records:
            name = record['path']
            info = entries.get(prefix + name)
            if info is None:
                if prefix + name in nodes:
                    raise InvalidInput('Expected a source file but found a directory: ' + name)
                if record['may_be_absent']:
                    result[name] = None
                    continue
                raise InvalidInput('Missing required file in repository ZIP: ' + name)
            if info.file_size > MAX_SOURCE_BYTES:
                raise InvalidInput('Source exceeds the 2 MiB limit: ' + name)
            with archive.open(info) as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise InvalidInput('Source exceeds the 2 MiB limit: ' + name)
            result[name] = data
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Repository root folder or a fresh GitHub Download ZIP')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    records = manifest(package)
    verify_payload(package, records)
    print(f'Update package integrity verified: {len(records)} files.')
    source = args.source.expanduser()
    sources = directory_sources(source, records) if source.is_dir() else zip_sources(source, records)
    unknown = []
    for record in records:
        name = record['path']
        data = sources[name]
        if data is None:
            print('NEW: ' + name + ' — absent from repository as allowed')
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != record['updated_sha256'] and digest not in record['accepted_before_upload_sha256']:
            unknown.append(name)
            print('DIFFERENT: ' + name + ' (' + digest[:12] + ')')
        else:
            label = 'update already present' if digest == record['updated_sha256'] else 'recognized source'
            print('OK: ' + name + ' — ' + label)
    if unknown:
        print('\nSTOP: these targets contain unrecognized edits. Keep them and merge the update before uploading.')
        print('This check changed no files.')
        return 1
    print('\nPASS: all named update targets are recognized or allowed to be new.')
    print('Upload the CONTENTS of github-upload to the repository root together.')
    print('This read-only check covers named targets only; it does not certify other files, full compatibility, or the live service.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, BadZipFile, RuntimeError, NotImplementedError) as error:
        print('STOP: check could not complete: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
