# Public presentation media, protocol 1

The application static snapshot and this world-media protocol have separate
registries. Static files are trusted application code under `web/`; world media
comes from the current host's selected world. This protocol never shares saved
games, player state or a whole world catalogue.

An actual joined player's map advertises `media_protocol: 1` alongside its
existing opaque `media_world` runtime identity. The client may ask:

```json
{"command":"world asset info","name":"assets/terrain/tiles.png","request_id":1}
```

Only an exact reviewed file in the current host world returns:

```json
{"type":"world_asset_info","name":"assets/terrain/tiles.png","request_id":1,"scope":"public-presentation","sha256":"6c83564024cd3f4ce6f602c6405d52ee4d4478a5cefde61363bcb02401b5b84b","size":119423,"mime":"image/png"}
```

Unknown, modified, missing, linked or unsafe files, and requests without an
actual joined actor, receive `scope: "transient"` without digest, size or MIME.
The server does not reveal whether a denied file exists. The legacy chunk
transport remains available to joined players. `assets/updates/` and
`assets/chronicles/` contain migration/source data and cannot be downloaded
through that transport; their archive import/export eligibility is unchanged.
Legacy rendering JSON is limited to the exact terrain index and sprite atlas
names used by the current browser renderers (including the transient wildlife
atlas). Other JSON files are source data, even when stored beside media.
Requests use portable path components, and all delivery paths reject linked or
reparse-point media. Ordinary authored image/audio files and edited rendering
atlases retain transient legacy delivery.

The public registry is the exact immutable `PUBLIC_PRESENTATION` mapping in
`engine/public_media.py`. Its 15 files total 2,937,600 uncompressed bytes:

| Exact path | Bytes | MIME |
| --- | ---: | --- |
| assets/terrain/index.json | 467 | application/json |
| assets/terrain/tiles.png | 119423 | image/png |
| assets/sprites/sprite-bodies.json | 6561 | application/json |
| assets/sprites/sprite-activities.json | 1576 | application/json |
| assets/sprites/sprite-gear-short-slim.json | 300768 | application/json |
| assets/sprites/sprite-gear-short-average.json | 301248 | application/json |
| assets/sprites/sprite-gear-short-broad.json | 302792 | application/json |
| assets/sprites/sprite-gear-average-slim.json | 309896 | application/json |
| assets/sprites/sprite-gear-average-average.json | 311600 | application/json |
| assets/sprites/sprite-gear-average-broad.json | 312716 | application/json |
| assets/sprites/sprite-gear-tall-slim.json | 317156 | application/json |
| assets/sprites/sprite-gear-tall-average.json | 318564 | application/json |
| assets/sprites/sprite-gear-tall-broad.json | 318636 | application/json |
| assets/audio/cue_street.ogg | 5070 | audio/ogg |
| assets/audio/thunder.ogg | 11127 | audio/ogg |

The source was the released Wild Lands 1.9.15 archive, SHA-256
`b4ceb676d0eebcce77d0394e6375cd5e65800eab5c0b8a44c1356cabfe5c76c6`.
All 15 entries also match the staged 1.9.16 archive exactly. Rendering JSON was
inspected for generic terrain keys or PNG/rendering fields, without private
records. Regional/mood soundtracks, wildlife subject lists, chronicles and
update payloads are excluded. A new or changed file needs a deliberate review
and registry update before persistent caching is permitted.

Verification runs off the event loop, reads only the requested allowlisted
path, and has bounded file/cache sizes. It never enumerates media directories.
Linux uses no-follow directory descriptors and reuses an unchanged file's
identity check. The portable Windows path checks file/directory identities
before and after reading and rejects reparse points; it rehashes on each small
version negotiation because Windows creation timestamps do not reliably detect
all edits. Neither path hashes files during map or chunk construction.

Folder publication and explicit world reload invalidate the runtime identity
and host verification cache. Render's editor edits a separate draft; applying a
desktop world reload constructs a new world. Out-of-band filesystem edits are
not polled each tick. A client must verify the complete received bytes against
the negotiated size and digest before using persistent bytes, since files can
change after negotiation. Timeout, unsupported protocol, cache failure or
transient scope must preserve legacy delivery.

Protocol 1 does not enable the shared MMO mode or change its deployment gate.
