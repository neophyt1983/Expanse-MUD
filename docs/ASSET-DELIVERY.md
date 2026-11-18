# Expanse asset delivery: audit and implementation contract

Status: **investigated and measured locally; persistent host-versioned caching is proposed, not implemented.** Recorded November 18, 2026. Code audited: [`bbbe023`](https://github.com/neophyt1983/Expanse-MUD/commit/bbbe023ab78f5378603805e2819fd47d81516e60). This document and the measurement tool do not enable MMO or change delivery, deployments, saves or accounts.

## Shared direction

For online MMO/MUD play, every client joins the host's authoritative shared world. That host can be a player's computer or Render. The host owns simulation, characters, permissions, interactions and persistence. Cached client files supply presentation bytes; they never become the authority for game rules or state.

This is the intended online architecture. Render currently runs a separate single-player worker per account/world. **Shared MMO remains unavailable until shared-world, account-isolation, editor-authorization, persistence and multiplayer integration tests pass.** See [the existing gate](../MMO-MODES-REVIEW.md) and [the coordinated work assignments](../EXPANSE-COORDINATION.md).

## What already exists

| Area | Verified behavior | Evidence |
| --- | --- | --- |
| Render web shell | Authenticated top-level CSS/JS/SVG/ICO files use `FileResponse`; every response receives `Cache-Control: no-store`. ETag/Last-Modified exist, but this is not ordinary persistent browser reuse. | [`render_server.py`](../render_server.py), `Service.assets`, `make_app.prepare`, `asset` |
| World images/audio/catalogues | `world asset` WebSocket commands request sequential 96 KiB chunks, encoded as base64 inside JSON. Client verifies offsets/size, not a content hash. | [`world_package.py`](../engine/world_package.py), `asset_packet`; [`game_server.py`](../server/game_server.py), world-asset command |
| Browser world cache | A `Map` retains promises and Blob URLs in page memory. A changed runtime `media_session` UUID clears it. No persistent Cache API, IndexedDB, service worker or host asset manifest was found. | [`world-assets.js`](../web/world-assets.js); `GameServer.map_for` |
| Pixel art | Authorized map/atlas projections contain flattened public pixels; browser memory caches them by revision. Full editor layers are deliberately excluded. | [`pixel_art.py`](../engine/pixel_art.py), [`visual-map.js`](../web/visual-map.js) |
| Installed desktop 1.9.17.1 | Qt uses a named profile with `NoCache`; local HTTP responses also use `no-store`. Bundled local assets exist, but remote joins use the host's WebSocket media path. Dependency-download caching is separate. | Installer payload `app/server/desktop.py`, `app/server/launcher.py`; see package evidence below |
| Desktop updates | The complete installer embeds code and world; its owned-file manifest updates the existing installation with backups and preserves user data. This is not a host-driven, per-file asset downloader. | `install.py`, installer manifests and build sources |

Inspection did not verify an Android client's native cache configuration. Existing browser memory reuse must not be advertised as automatic cross-session missing/changed-only synchronization.

## Measured baseline

Reproducible inventories and local authenticated HTTP probes are in [the JSON baseline](measurements/asset-delivery-baseline-20261118.json). Gzip figures are local compression opportunities, **not observed Render transfer coding**. All sizes below are bytes; decimal GB means 1,000,000,000 bytes.

| Measurement | Result | Scope |
| --- | ---: | --- |
| All served web static files | 93 files; 1,017,457 bytes | Actual local HTTP response bodies: same total again on repeat without validators; identity encoding and `no-store` |
| `/play` HTML plus 86 directly referenced static files | 962,846 bytes | Source inventory; excludes later dynamic fetches, gameplay, HTTP/TLS overhead |
| Same `/play` resource set, gzip opportunity | 318,966 bytes | Estimated per-file compression; live proxy/browser compression unmeasured |
| Wild Lands 1.9.15 presentation candidates | 49 files; 7,271,850 bytes | Audio, terrain, sprites and images; candidates still require host authorization/schema review |
| Staged Wild Lands 1.9.16 presentation candidates | Same 49 files, bytes and SHA-256 hashes | A future fully populated verified cache would download zero changed presentation bytes for this transition, plus manifest/application traffic |
| 1.9.15 `assets/updates/` payloads | 61,394,663 bytes | Server/content update data; exclude from presentation caching and public manifests |
| 1.9.16 `assets/updates/` payloads | 83,630,385 bytes | Also excluded; do not download the whole `assets/` tree as a client cache |
| Other transport-eligible world JSON | 134,679 bytes per world | Requires review; broad current `media()` eligibility is not a public-cache policy |
| Fetching all 49 candidate files once through current WS format | 109 request/response turns; 9,712,558 response JSON bytes | Model from exact 1.9.15 files with fixed `request_id=1`; excludes framing, TLS, negotiated WS compression and unrelated gameplay; not a session trace |

The current loader is lazy: a player does not necessarily request all candidate files. Existing sprite catalogues also embed PNG bytes as base64 inside JSON, then acquire another base64 layer in the WS transport. Separating verified image blobs from catalogue metadata is a later optimization to measure, not an implemented feature.

The locally probed `FileResponse` supports an explicit `If-None-Match` request (304, empty body). That diagnostic does not show that a browser retains a `no-store` response. The local process did not compress responses despite `Accept-Encoding`; Render's proxy may behave differently.

### Cost interpretation

Render currently counts both public HTTP and WebSocket responses as outbound bandwidth. Its documented public overage rate is **$0.15/GB**, with workspace allowances of Hobby 5 GB, Pro 25 GB and Scale 1 TB per month. Compute instance size does not establish the workspace plan. Verify actual account/legacy terms before budgeting. [Render bandwidth and pricing](https://render.com/docs/outbound-bandwidth).

For public traffic only, estimate the bill as `max(0, workspace_outbound_GB - included_GB) * price_per_GB`. Compare the whole-workspace bill before/after, not just this service's hypothetical bytes. An avoided GB inside unused allowance saves no immediate bandwidth charge. Avoiding 10,000 full raw `/play` resource-set downloads would avoid about 9.63 GB, worth at most about $1.44 at the documented marginal rate, before allowance and actual compression. This is a scenario, not current usage or proven savings.

Caching can reduce repeated transfer/encoding and loading time. It does not reduce the fixed Render compute price or remove host simulation work. A Render edge cache may reduce origin load; public delivery still counts as outbound traffic, so do not equate a CDN hit with free egress. [Render edge-cache behavior](https://render.com/docs/web-service-caching).

No authenticated live Render service usage, billing total, production cache-hit rate, latency or compression negotiation was available in this audit. The dashboard required sign-in and the Render connection was unavailable. Record those from [service Metrics and workspace Billing](https://render.com/docs/service-metrics) before making a dollar-savings claim. No production account or service setting was changed.

## Proposed host/client contract

### 1. Separate release, world and runtime identities

Negotiate a versioned capability such as `asset_protocol: 1`, retaining the existing WS path for older clients. Distinguish application release, original imported-world identity, asset generation and live gameplay session. A reconnect UUID must not force unchanged files to download again.

Preserve imported archive IDs and their save ownership. Do not re-import or rewrite a world's File ID merely to introduce a cache. An asset revision may advance while an existing world/save identity stays unchanged.

The host advertises only approved/revealed presentation resources, through an authenticated manifest or scoped announcements. Proposed record shape (not a current endpoint):

```json
{
  "schema_version": 1,
  "world_id": "original-import-identity",
  "asset_revision": "host-selected-generation",
  "asset_protocol": 1,
  "assets": [
    {
      "id": "approved-resource-id",
      "sha256": "64-lowercase-hex-digits",
      "size_bytes": 12345,
      "mime": "image/png",
      "cache_scope": "public-presentation",
      "url": "/asset-blobs/content-hash/resource.png"
    }
  ]
}
```

These are illustrative fields/placeholders, not valid release hashes. Validate schema, counts, sizes, MIME, allowed origins and hash formats before use. Discover/reveal private art on demand; a full directory manifest must not enumerate hidden maps, unrevealed layers, world definitions, migration JSON, drafts or private files. Sprite JSON requires a specific public-presentation schema; `.json` or an `assets/` prefix alone is insufficient.

### 2. Fetch missing or changed verified blobs

Map each logical resource to its SHA-256. Reuse an existing verified matching blob; otherwise fetch that resource and verify its exact size/hash before use. Immutable blob URLs must never serve different bytes later. Publish a new complete manifest atomically, pin an active session's generation, and retain still-needed older blobs during transition.

Use binary HTTP for new media delivery where practical; keep WS fallback. Range/resume for large audio is optional and must retain final whole-file verification. Hashing proves byte integrity, not server trust: manifests come from the selected trusted host over its authenticated connection. A claimed local hash never grants access, changes rules or authorizes a character/editor operation. A protected cache hit also requires current host-authorized scope; stale manifests or stored bytes cannot bypass account switching or role revocation. Start persistent storage with explicitly public presentation assets; leave protected assets uncached until that extra permission layer is tested. Do not send cached credentials to a new asset origin.

Fix transient-failure retry: the existing promise cache can retain a failed/null result until world reset. Add bounded downloads, cancellation, timeouts, hash/length mismatch handling, quota failure fallback and LRU storage limits. Hash off the gameplay hot path; invalidate only changed approved assets after Creator edits.

### 3. Browser adapter

Start with versioned/content-hashed application asset URLs and ordinary HTTP caching. Keep authenticated HTML, config, accounts, saves, API responses, editor drafts and gameplay state `no-store`. Do not apply `immutable` to today's mutable `/file.js` URLs. Choose `private` caching for authenticated assets; use `public, max-age=31536000, immutable` only for explicitly public, cookie-free immutable bytes. A public manifest may revalidate by ETag; a protected manifest remains authenticated and uncacheable by default. [HTTP caching guidance](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).

If measurements justify persistent media storage, add a dedicated versioned Cache API/IndexedDB namespace with verified blobs and bounded eviction. A service worker is optional. Cache API storage does not honor HTTP cache directives automatically, so explicitly allowlist each eligible response. Never blanket-cache all requests. [Cache API behavior](https://developer.mozilla.org/en-US/docs/Web/API/Cache).

Browsers scope storage by origin: Render, localhost, LAN hostnames and different ports do not automatically share a cache. A common public asset origin is a separate design decision. Private assets need host/world/account authorization boundaries; logout/revocation must remove that account's disposable protected cache where applicable. Cache cleanup must not use `localStorage.clear()`, `indexedDB` blanket deletion or broad `Clear-Site-Data`: existing browser storage includes settings, character IDs and deletion tokens. Eviction/corruption must trigger safe re-download, never save loss. [Storage scope and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria).

Negotiate storage and crypto capabilities in browsers, Qt and LAN-hosted clients. Some advanced APIs require a secure context; retain uncached online/WS fallback when unavailable. Reject unexpected cross-origin asset redirects and never forward authentication secrets to another origin. Revocation can prevent future authorized use/fetches, but cannot guarantee erasure of bytes already delivered to an untrusted client.

### 4. Installed-client adapter

Use the same host manifest and hashes. A native cache can index verified public blobs already supplied by an installer and reuse them when the connected host advertises matching content. The host still chooses the world and allowed versions. Do not run an independent local simulation as the online authority.

Store disposable blobs separately from `save/`, authored/custom worlds, exported `.expanse` files, accounts, settings, runtime dependencies and update backups. Keep the existing application identity/folder and in-place update protections. The installer dependency cache is not this asset cache. Do not blindly enable Qt's HTTP cache for every current response; apply the same resource classification and auth exclusions first.

Installed engine/launcher auto-updates are a separate signed/trusted release-update problem. This asset protocol must not execute downloaded code or silently replace engine modules. Preserve offline single-player availability and user-owned content.

## Implementation order and acceptance tests

1. **Baseline (this change):** inventory and local HTTP evidence; classify presentation vs update/private data; publish this common contract. Obtain production HTTP/WS totals and workspace allowance.
2. **Application cache:** hashed release URLs, safe cache headers and measured compression; lazy-load editor resources where useful. Maintain an uncacheable authenticated bootstrap and release compatibility.
3. **World media:** shared asset registry, scoped manifest and integrity checks. The smallest shared first implementation can retain existing WS chunks while identifying stable content hashes. Add binary HTTP adapters and sprite catalogue/image separation only when measured transfer/encoding savings justify them.
4. **Persistent browser/native caches:** bounded storage, local bundled-blob indexing, retry/eviction/recovery; update only changed hashes. Share protocol fixtures across desktop and Render adapters. Apply the same manifest rules regardless of WS or binary HTTP transport.
5. **Production comparison:** same player activity and resource set, cold/warm/restart/reconnect, one changed file, world switch, quota refusal, corrupt/partial download, old client, account switch/logout, denied private/editor asset, interrupted manifest update, cache clear and downgrade. Record requested bytes, delivered HTTP/WS bytes, cache hits/misses, 200/304 responses, encodings, p50/p95 loading and host CPU/RAM.

Keep asset metrics free of account names, tokens, chat, raw private paths and save contents. `PerformanceResourceTiming` can help, but its transfer size is not an exact Render billing counter, and zero can reflect cross-origin timing restrictions. Reconcile client/server counters with Render service metrics and workspace totals. [Resource timing](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize).

Release acceptance also requires byte-for-byte preservation of existing saves/user worlds/accounts/settings, in-place installer upgrade and rollback checks, no hidden-content enumeration, permission checks on every protected fetch and cache hit, and no app/engine version mismatch. Test account A to B and role revocation with an already populated cache and stale scoped manifest. **The separate MMO gate remains mandatory even if all cache tests pass.**

## Reproduce and coordinate

Run `python tools/measure_asset_delivery.py --world /path/to/World.expanse --compare-world /path/to/Next-World.expanse --probe-local-http --output /new/path/report.json`. Omit `--compare-world` for a single-world inventory. `--output` creates a new file exclusively and refuses to overwrite an existing file. The probe uses temporary local credentials/data and never starts a game worker or contacts Render. Run `python -m unittest discover -s tests -p 'test_asset_measurement.py'` for the tool's checks.

Desktop evidence: `Expanse-Linux-1.9.17.1.run` is 29,657,381 bytes, SHA-256 `99f125a3571aae0893660b60221460b5e37a4484b9685496c3430f10931b282c`; its embedded payload and owned-file manifest were inspected without running the installer. It bundles Wild Lands 1.9.15, archive SHA-256 `b4ceb676d0eebcce77d0394e6375cd5e65800eab5c0b8a44c1356cabfe5c76c6`. The desktop verification report names shared engine commit `bbbe023` and two declared platform overrides. Windows-native execution and Android cache behavior were not tested here.

The separate `Expanse-Observable-Festivals-1.9.18.md` handoff says its 1.9.18 code and 1.9.16 world are staged, with matching code required before importing that world. The 1.9.16 archive was inspected for assets only, not imported into current runtime. Preserve those release prerequisites and merge shared engine changes deliberately. The asset hash comparison is not a game-version compatibility approval.
