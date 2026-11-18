# Reproducing the application-shell cache trace

This procedure tests the HTTP cache for application JavaScript/CSS. It does not
test gameplay, world-media IndexedDB storage, native seed reuse, or the shipped
desktop application's current `NoCache` setting.

## Repeatable HTTP/body measurement

From this repository, choose a new output filename:

```sh
python tools/probe_versioned_app_assets.py --baseline-ref 447efd6 --output app-shell-http-trace.json
python -m unittest discover -s tests -p test_versioned_app_assets.py -v
```

The probe reads the prechange Render adapter from the named Git commit, then
gives both adapters the same disposable copy of the candidate web files. This
isolates cache policy/compression from unrelated code changes. It uses a dummy
local owner and save sentinel, starts no game worker, and exports sizes and
safe headers rather than credentials or response bodies. Its fresh-cache warm
case is explicitly modeled; forced conditional `304` responses are measured.

## Actual browser navigation

Use the same disposable fixture boundaries as the HTTP probe: the real
`make_app`, `/play`, and `/app-assets/` handlers; a dummy local owner; an inert
`Service.active_client`; and fixture-only API/WebSocket replies. Never point the
fixture at real saves or account data. Count `/play` and `/app-assets/` responses
through `app.on_response_prepare`, recording status, `Content-Length`,
`Content-Encoding`, and `Cache-Control`. Count bodies as zero for `HEAD`/`304`.

1. Start with a new, private browser profile and a single local origin. Leave
   ordinary HTTP caching enabled; disable developer tools' “Disable cache”.
2. Sign in with the fixture owner and navigate normally to `/play?probe=cold`.
   Wait for document completion and all direct script/stylesheet resources.
3. Navigate normally to `/play?probe=warm` at the same origin. Do not use hard
   reload, `cache: reload`, a new profile, or a different port/origin.
4. Close the browser gracefully. Start another browser process using the same
   profile, sign in again if needed, and navigate to `/play?probe=restart`.
5. For each phase, compare server asset requests/body counts with resource
   timing. A retained fresh asset should create no server request and have zero
   `transferSize`. HTML remains a network request with `no-store`.

Collect the same-origin resource timings in each document:

```js
performance.getEntriesByType('resource')
  .filter(row => new URL(row.name).pathname.startsWith('/app-assets/'))
  .map(row => ({
    path: new URL(row.name).pathname,
    transferSize: row.transferSize,
    encodedBodySize: row.encodedBodySize,
    decodedBodySize: row.decodedBodySize
  }));
```

The recorded offscreen run used 3D Slicer 5.10's `qSlicerWebWidget`, QtWebEngine
5.15.2/Chromium 83, private persistent `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`,
`XDG_DATA_HOME`, and `TMPDIR` directories, `QT_QPA_PLATFORM=offscreen`, and
`QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`. `evalJS`/`evalResult` collected the
timings; graceful application exit preserved the default profile for restart.
An ordinary current browser can use the same navigation/counting procedure.

Report only aggregates and relative resource paths. Browser resource timing is
not a Render billing counter. Server response-body lengths exclude HTTP
headers, requests, TLS, and proxy behavior. Record the application's
`X-Expanse-App-Release`/registry release ID and source hashes beside each trace.
