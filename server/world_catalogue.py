"""Read-only display and version ordering for imported worlds.

These helpers do not read files, alter authored metadata, or choose save paths.
Returned text is plain text; an HTML caller must escape it when rendering.
"""
from collections.abc import Mapping
import json
import re


_VERSION = re.compile(
    r'[vV]?(?P<core>(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*)'
    r'(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z'
)
_TITLE_SUFFIXES = (
    re.compile(r'(?P<base>.+?)\s+\((?P<version>[vV]?[0-9][0-9A-Za-z.+-]*)\)\Z'),
    re.compile(r'(?P<base>.+?)\s+\[(?P<version>[vV]?[0-9][0-9A-Za-z.+-]*)\]\Z'),
    re.compile(r'(?P<base>.+?)\s+(?P<version>[vV]?[0-9][0-9A-Za-z.+-]*)\Z'),
)


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _version_key(value):
    """Numeric release precedence; prereleases precede their final release.

    Accept dotted numeric versions, optional v, SemVer prereleases and build
    metadata. Build labels do not affect precedence. Missing trailing numeric
    zeroes compare equally, so 1.9 and 1.9.0 are the same release level.
    Unrecognised schemes remain unranked instead of being guessed.
    """
    value = _text(value)
    if not value or len(value) > 128:
        return None
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    core = tuple(int(part) for part in match['core'].split('.'))
    while len(core) > 1 and core[-1] == 0:
        core = core[:-1]
    pre = match['pre']
    if pre is None:
        return core, 1, ()
    identifiers = []
    for part in pre.split('.'):
        if part.isascii() and part.isdecimal():
            if len(part) > 1 and part[0] == '0':
                return None
            identifiers.append((0, int(part)))
        else:
            identifiers.append((1, part))
    return core, 0, tuple(identifiers)


def _title_parts(title):
    for pattern in _TITLE_SUFFIXES:
        match = pattern.fullmatch(title)
        if match is None or _version_key(match['version']) is None:
            continue
        token = match['version']
        # A bare story-title number ("Voyage 2") is not a version suffix.
        if '.' not in token.split('-', 1)[0].split('+', 1)[0] and token[:1].lower() != 'v':
            continue
        base = match['base'].rstrip()
        if base.endswith((' -', ' –', ' —')):
            base = base[:-2].rstrip()
        if base:
            return base, token, match.span('version')
    return title, None, None


def display_info(info, metadata=None, manifest=None):
    """Copy an import record and enrich its display fields from authored data.

    Precedence is metadata/manifest content_revision, metadata/manifest
    world_version, metadata.version, then a recognised trailing title version.
    A present explicit revision with invalid/custom syntax is authoritative but
    unranked; it cannot accidentally fall back to an obsolete title version.
    Manifest version, schema_version and engine_version are never world versions.

    Families use an explicitly authored world_id, otherwise slug plus the title
    without a recognised version suffix. This keeps same-slug, renamed forks
    separate without relying on archive hashes or import order.
    """
    info, metadata, manifest = _mapping(info), _mapping(metadata), _mapping(manifest)
    result = dict(info)
    slug = _text(info.get('slug')) or _text(manifest.get('slug')) or _text(metadata.get('slug'))
    title = next((text for source in (metadata, manifest, info)
                  for field in ('name', 'title') if (text := _text(source.get(field)))), slug or 'Untitled world')
    base, suffix, span = _title_parts(title)
    version, provenance = suffix, 'title' if suffix else None
    for source_name, source, field in (
        ('metadata', metadata, 'content_revision'),
        ('manifest', manifest, 'content_revision'),
        ('metadata', metadata, 'world_version'),
        ('manifest', manifest, 'world_version'),
        ('metadata', metadata, 'version'),
    ):
        if field in source:
            raw = source[field]
            version = str(raw) if type(raw) is int else _text(raw) or None
            provenance = source_name + '.' + field
            break
    display = title
    if span is not None and version is not None:
        display = title[:span[0]] + version + title[span[1]:]
    world_id = _text(metadata.get('world_id')) or _text(manifest.get('world_id'))
    family = (['id', world_id] if world_id else
              ['title', slug.casefold(), ' '.join(base.split()).casefold()])
    result.update(
        display_name=display, base_name=base, version=version,
        version_source=provenance, version_comparable=_version_key(version) is not None,
        family=json.dumps(family, ensure_ascii=False, separators=(',', ':')),
    )
    return result


def annotate_latest(rows):
    """Copy/sort ``(archive_id, display_info(...))`` rows and mark newest versions.

    Each family is ordered by descending numeric/prerelease precedence, then
    stable archive ID for ties; unranked records follow numbered records.
    Every equally newest variant is marked, including differing build labels.
    Unknown versions never become newest or older by inference from their dates.
    unranked_in_family lets a UI qualify its badge as 'Newest numbered version'.
    """
    groups = {}
    for ident, info in rows:
        item = dict(_mapping(info))
        if not isinstance(item.get('family'), str):
            item = display_info(item)
        groups.setdefault(item['family'], []).append((ident, item))
    result = []
    ordered_families = sorted(groups, key=lambda family: (
        min(_text(item.get('base_name')).casefold() for _, item in groups[family]), family))
    for family in ordered_families:
        members = sorted(groups[family], key=lambda row: str(row[0]))
        members.sort(key=lambda row: _version_key(row[1].get('version')) or ((), -1, ()), reverse=True)
        keys = [_version_key(item.get('version')) for _, item in members]
        newest = next((key for key in keys if key is not None), None)
        latest_version = next((item.get('version') for (_, item), key in zip(members, keys)
                               if newest is not None and key == newest), None)
        unranked = any(key is None for key in keys)
        for (ident, item), key in zip(members, keys):
            item.update(
                is_latest=key is not None and key == newest,
                is_older=key is not None and newest is not None and key < newest,
                latest_version=latest_version, unranked_in_family=unranked,
            )
            result.append((ident, item))
    return result
