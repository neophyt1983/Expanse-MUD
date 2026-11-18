# Asset-delivery follow-up: cache behavior and gameplay packets

This supplements the existing [asset-delivery audit/contract](ASSET-DELIVERY.md) and [work coordination](../EXPANSE-COORDINATION.md); it does not introduce a competing protocol or implementation plan. The other work published that canonical handoff at `a783ddd9f8215934c0d607851cd76a09739c05d6` while this investigation was running. This follow-up was integrated onto that commit. Runtime engine, web and server code remain identical to the earlier audited `bbbe023`.

**Persistent synchronization is still proposed. No runtime caching or deployment changes were made; the MMO gate remains closed.** The staged festival 1.9.18/game 1.9.16 release prerequisites in the canonical handoff remain in force. No staged world was imported or approved here.

## Additional measured evidence

| Probe | Observed result | Limit |
|---|---|---|
| Current served `world-assets.js`, isolated JS contexts | Two same-page calls share one request; a new page downloads again; a changed host session refetches. A changed file under the same path/session remains the old cached result. | Protocol/JS fixture, not a browser persistence or disk-cache test. |
| Published desktop 1.9.17.1 build-source supplement | `desktop.py:47` selects `QWebEngineProfile.NoCache`; `launcher.py:260` sends no-store. The configured cache path alone does not enable caching. | Source inspection, not a Windows or Android trace. |
| Expanded canonical local HTTP probe | Anonymous static request: 401; authenticated `/enter` with `mode=mmo`: 503. The existing no-store behavior and explicit diagnostic 304 response remain. | Disposable owner/data, no worker or shared world started; not a production access check. |
| Public Render GETs | `/healthz`: 200/2 bytes; `/`: 200/5,993 bytes; `/world-assets.js` and `/visual-map.js`: 401/27 bytes each. All observed responses had no-store. | No login/cookies or private session used. No deployed source SHA was disclosed. Billing and authenticated production usage are still unavailable. |
| Real single-player game-server packet generation on a disposable world copy | Initial constructed map: 77,476 JSON bytes. One actual tagged movement delivered a 122,333-byte map and 1,984-byte response. | Four-command fixture, no lifecycle timer, real network, framing, wire compression or manual Save. Scene-dependent, not a per-action guarantee or a rate. |

The gameplay sample asserts that a real move occurred and a map was delivered. `{}` accounted for just two bytes in that map's `pixel_assets` field, so this scene's large map body cannot be attributed to downloaded terrain/audio files. Future profiling should count dynamic map/state traffic alongside presentation downloads. Artwork caching will not eliminate authoritative state updates, and this sample cannot establish a session/hour or monthly invoice.

The independently inspected desktop source supplement has SHA-256 `96c9f782decc59988588255da41db876ff77a136a6a688ae1ec9eee1cc82e135`. Its module hashes and relevant source lines are retained in the evidence below. No installed app, browser profile or user save was modified.

## Reconciling bandwidth and cost scopes

The canonical baseline's **962,846 bytes** for the directly referenced playing-page set includes the **98,845-byte HTML shell**. The external JS/CSS/icon subset is **864,001 bytes across 86 referenced URLs**. The larger all-served-static inventory is 93 files/1,017,457 bytes. These are different resource sets, not conflicting measurements.

The HTML/bootstrap remains uncached/fresh under the proposed design. A hypothetical 10,000 repeated downloads of the unchanged external subset would avoid **8.64001 decimal GB** before compression, worth about **$1.296 only if already above the included bandwidth allowance** at the published $0.15/GB rate. This excludes HTML, API, gameplay, manifest requests, first-time clients, updates and eviction. It is not an observed user count or bill saving. The canonical full-resource-set scenario is an upper inventory model, not a claim that protected HTML should be cached.

Both investigations agree on the current game's 49 presentation candidates: **7,271,850 raw bytes** and **9,712,558 current base64/JSON response bytes** (33.56% application-body overhead). A normal visit need not download the entire catalogue. The offline compressed UI size is an opportunity, not evidence of Render's negotiated encoding. A Render edge/CDN hit still uses outbound bandwidth.[1][2]

For monthly total `B` bytes, avoided bytes `S`, actual allowance `A` GB and marginal price `r`, use:

`charge(B) = max(0, B / 1,000,000,000 - A) * r`

`saving = charge(B) - charge(max(0, B-S))`

Saving bytes inside unused allowance does not save a bandwidth charge. Local assets do not move NPC/world simulation off the host or reduce the fixed compute/disk bill automatically. The deployment work still needs the actual workspace plan, billing period, HTTP/WS/service-initiated totals and equal-activity client traces. No new paid delivery service is justified by this fixture alone.

## Reproduce and collect the missing evidence

Use the existing [canonical inventory tool](../tools/measure_asset_delivery.py) and its archive-comparison tests; this follow-up reuses that code instead of adding a second inventory or asset schema. The new explicit public probe is separate and opt-in:

```bash
python tools/probe_asset_delivery.py --local-http --public-origin https://your-host.example --output new-probe.json
node tools/probe_current_asset_cache.cjs
python tools/sample_game_bandwidth.py --world /path/to/extracted-authored-world --output new-packet-sample.json
python -m unittest discover -s tests -p 'test_asset_measurement.py' -v
python -m unittest discover -s tests -p 'test_asset_delivery_followup.py' -v
```

Both new Python probe commands refuse to overwrite an existing report or user file. The game probe copies the world into its own temporary directory and uses single-player only; it does not touch a real save or run the shared host. Outputs contain counts, sizes, hashes and selected headers, never tokens, account/character IDs, chat or response bodies.

For an authenticated browser/device session, [browser_bandwidth_snapshot.js](../tools/browser_bandwidth_snapshot.js) is an optional read-only DevTools snippet that aggregates Resource Timing without exporting URLs or credentials. Capture clean cold/warm visits with consistent cache settings, reconnect and later one changed host asset. Do not distribute a credential-bearing HAR. Zero transfer is not proof of a cache hit; timing privacy restrictions and buffer eviction can affect readings. Resource Timing does not measure WS frames; obtain those totals from the host/provider. No real browser cold/warm or Android caching test has been claimed here.

Additional measurements: [public/local headers](measurements/asset-delivery-followup-20261118.json), [JS cache probe](measurements/current-cache-probe-20261118.json), [desktop source inspection](measurements/desktop-cache-source-20261118.json), [game packet sample](measurements/game-packets-20261118.json).

## Shared implementation details to retain

Follow the canonical host manifest, compatibility and permission contract. Do not simply enable broad caching or use the runtime session UUID as the durable asset version. Hash/revise approved assets at import/publication boundaries, never on every tick. Keep protocol fixtures identical across local hosting, Render and installed clients, and preserve the old transfer path for unsupported clients.

For UI changes, pin a complete release until its replacement is ready; do not mix old/new scripts. For binary HTTP, define manifest hashes over decoded logical bytes so content encoding cannot change identity. A reconstructed cached response must not replay Set-Cookie or an incorrect Content-Encoding/Content-Length header. Native cache writes must be atomic, bounded and traversal/symlink-safe; changing loopback ports must not accidentally choose another host's manifest. Cache corruption/cleanup must only remove Expanse-owned disposable cache entries.

Existing engine/app updates still occur **in place** and preserve application identity, saves, authored worlds, local accounts, settings, exports and backups. The asset protocol must not import a different game, force character recreation, execute replacement engine code or introduce gameplay autosaves. Android needs a shell/secure-context/storage audit; keep a memory/current-protocol fallback.

The tests here verify measurement safety, anonymous denial and the closed local MMO entry. Existing solo-isolation and role-registry checks also pass. **These do not satisfy the shared-world, account-isolation, editor-authorization, persistence and multiplayer release gate.** No cache stage may auto-open it.

1. [Render outbound bandwidth](https://render.com/docs/outbound-bandwidth), [pricing](https://render.com/pricing) and [edge caching](https://render.com/docs/web-service-caching), checked for this investigation. Actual account terms remain unverified.
2. [Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache), [HTTP Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control) and [Qt profile caching](https://doc.qt.io/qtwebengine/qwebengineprofile.html) document the separate storage and policy layers.
