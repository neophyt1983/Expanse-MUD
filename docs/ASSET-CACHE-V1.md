# Expanse asset cache v1

The host continues to choose the world, run the simulation and authorize each player. A browser can now reuse the playing interface and selected public artwork or sound across visits. An installed Qt client can also use a matching file already distributed with the game once the desktop update includes the bridge. [Issue #10](https://github.com/neophyt1983/Expanse-MUD/issues/10) tracks the rollout.

## What a player downloads

| Resource | First use | Repeat use or update |
| --- | --- | --- |
| Render playing and owner-editor pages | Authenticated HTML identifies the current application files. The shell and private APIs use `no-store`. | Fetch fresh HTML on navigation. Each unchanged script or stylesheet keeps its SHA-256 URL. A changed file gets a new one. |
| Render application files | The gateway snapshots trusted `web/` resources on startup. It negotiates gzip or identity with separate ETags and serves authenticated successful responses with `private, max-age=31536000, immutable`. | An ordinary fresh browser cache can skip the request. Explicit revalidation returns 304 for the matching representation. Old clients can still request mutable filenames. An expired release URL returns 404 and instructs the player to reload. |
| Approved world media | A joined client asks the current host about one logical path over the existing WebSocket. The host checks the selected world's bytes and returns a size, MIME type and SHA-256 for an approved version. | The client checks origin-local IndexedDB, then the optional native bundle, then requests chunks from this host. It verifies the full digest before use. A reconnect requires fresh host approval even if the bytes are already on disk. |
| Other playable media | The existing WebSocket transfer supplies the requested media to joined players. | New or edited files without an approved digest remain transient. The server withholds update transactions and chronicle source files from the media transport. |

Version 1 covers 15 Wild Lands files totalling **2,937,600 bytes**. These include the terrain sheet and index, body and gear artwork, activities, the street cue and thunder. The [wire protocol and reviewed inventory](PUBLIC-MEDIA-PROTOCOL.md) specify the exact files. To add a release, review its actual presentation data and update the registry. Media downloaded on demand never grants permission to see a hidden location, control a character, edit a world or open a save.

Active downloads share a two-job queue. Audio keeps its object URL until playback stops or the track changes. Sprites and terrain release theirs after decoding. The in-memory cache can evict old blobs while active consumers finish using them.

The browser stores only approved blobs in its own IndexedDB database, capped at 64 MiB and 256 entries. Quota denial, unavailable IndexedDB and a missing native bridge fall back to host delivery. An insecure LAN browser without WebCrypto uses transient media. Changing world, character or connection invalidates in-flight work. Localhost, LAN hosts, different ports and Render have separate origin storage. The game does not clear preferences, character tokens or other website storage.

## Desktop update packaging

The desktop supplement owns the Qt window. The shared source supplies the media registry, browser and `server/desktop_asset_seed.py`. When assembling the next update to the existing installation, export the shared runtime, apply the desktop supplement, then run these commands from a clean staging checkout. Here `stage_bundle` contains `app/server/display_preferences.py` and `source_repo` is the absolute path to this repository.

```sh
git -C "$stage_bundle" apply --check "$source_repo/desktop/qt-bundled-media-1.9.17.1.patch"
git -C "$stage_bundle" apply "$source_repo/desktop/qt-bundled-media-1.9.17.1.patch"
```

Continue with the supplement's normal manifest generation and in-place installer build. The adapter accepts only a digest. It reads the exact Wild Lands 1.9.15 archive distributed by the installer and verifies its size and full release hash before opening members. If the archive is missing or modified, the host supplies the bytes. A new approved asset absent from an older verified bundle leaves other matching files reusable. User-created worlds, saves, accounts, exports, settings and backups are outside the seed lookup.

An offscreen Linux test applied this patch to the official desktop source and used the pinned PySide6/Qt 6.10.3 runtime with a temporary profile. Through the actual QWebChannel, the browser retrieved the bundled 119,423-byte terrain sheet, verified its hash and decoded it as a 1,176 × 408 bitmap. A second request reused the bundled bytes, and an unknown digest returned a miss. The 1.9.17.1 Windows and Linux installers already distributed require a later package to gain this native bridge. Their existing Qt profiles disable ordinary HTTP caching. The browser's IndexedDB media path and the native bundle lookup are independent of that setting. Android and physical desktop verification remain separate release work.

## Verification and rollout

The [original inventory](ASSET-DELIVERY.md) and [follow-up baseline](ASSET-DELIVERY-FOLLOWUP.md) record previous behavior. The [local HTTP comparison](measurements/versioned-app-assets-local-20261118.json), [embedded-browser shell trace](measurements/versioned-app-assets-browser-20261118.json) and [world-media browser trace](measurements/world-media-real-browser-20261118.json) identify the tested code and distinguish static requests, asset bytes, metadata and gameplay traffic.

| Local test | First visit | Return visit |
| --- | --- | --- |
| Source-identical interface under previous HTTP policy | 875,482 bytes for 86 external resources and 99,114 bytes of HTML | Same external body bytes when requested again |
| Versioned shell in an embedded Chromium browser with HTTP caching enabled | 298,455 gzip bytes for the 86 resources and 105,436 bytes of HTML | No static requests on normal navigation or process restart with the same profile. The 105,436-byte HTML shell was fetched each time. |
| All 15 approved media files in the world-media fixture | 2,937,600 decoded asset bytes | Fresh version checks, zero asset chunks on reload and after browser restart |

The controlled one-file shell update changed one URL. The other 85 URLs retained their versions. A corrupt 467-byte terrain index triggered a download of that file alone. A second origin fetched its own media. These measurements exclude HTTP headers, WebSocket framing, negotiated compression on the WebSocket and TLS. A normal session can request fewer than 15 files.

On a disposable instance of the actual Render gateway and private-worker subprocess, a player signed in, imported released Wild Lands 1.9.15, entered Single Player, created a character and resumed it over the proxied WebSocket. Before joining, the socket received no digest. After joining, the host advertised v1 and supplied the 119,423-byte terrain PNG in two chunks. Its SHA-256 matched the host announcement. A manually created named checkpoint database and its catalogue matched before and after the media requests. The checkpoint reopened with the same character at the same location, and the original archive retained its SHA-256. The public MMO entry returned HTTP 503.

The shared-host work in [draft PR #14](https://github.com/neophyt1983/Expanse-MUD/pull/14) remains separate. The source combined cleanly with staging commit `44e75a6`. All 99 combined Python tests and 27 JavaScript tests passed. A separate real WebSocket run used two authenticated accounts and the released world. Both players saw the same host-selected terrain version. The staging host rejected a cross-account resume and closed a revoked session, then recovered the accounts' separate character catalogues after restart. Single Player keeps manual saving. MMO staging checkpoints on exit, disconnect and timeout. The existing shared-world, account isolation, editor authorization, persistence and multiplayer release gates still apply.

To reproduce the automated regressions on a checkout with the repository dependencies installed:

```sh
python -m unittest discover -s tests
node --test tests/test_world_assets.cjs tests/test_media_consumers.cjs tests/test_player_lists.cjs
PYTHONPATH=. python tests/test_multi_player_isolation.py
```

Set `EXPANSE_TEST_WORLD` to the extracted released Wild Lands 1.9.15 directory and `EXPANSE_TEST_WORLD_ARCHIVE` to the original archive to include the authored-world checks. For the baseline comparison, use `python tools/probe_versioned_app_assets.py --baseline-ref 447efd6 --output /new/path/report.json`.

Production measurements require the active Render service and workspace billing period. Compare equivalent cold and warm sessions, record HTTP and WebSocket traffic separately where available and reconcile totals with the workspace allowance. Browser-local bytes and fixed simulation compute have different billing implications. This implementation introduces no migration, paid delivery service or automatic MMO activation.
