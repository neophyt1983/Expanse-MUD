# Shared-host staging and release directions

Updated November 18, 2026. This is a development and acceptance runbook. **The public MMO remains disabled.** Signing in as Admin does not enable it. The intended online model is one authoritative host on a player's computer or Render; clients do not run independent authoritative copies of the simulation.

**Current save direction:** MMO saves automatically when a player exits or times out. The isolated shared staging runtime implements that policy for exits/disconnects, revoked sessions and idle expiry. Single Player keeps its existing manual **Save / Save & quit** behavior. This does not enable the shared public gateway or change existing production saves.

Use this alongside [the MMO gate](../MMO-MODES-REVIEW.md), [work coordination](../EXPANSE-COORDINATION.md), and [the asset-delivery contract](ASSET-DELIVERY.md). A successful policy unit test, a draft pull request, or a working Single Player session does not satisfy the shared-world release gate.

Recorded local validation: **62 Python tests pass on both Python 3.12.14 and 3.14.10**, with the separately supplied authored-world tutorial suite explicitly skipped. This includes 27 shared-host checks, nine of them real HTTP/WebSocket integration tests, and a four-client fixture. Nine existing browser player-list regressions and the separate private-account isolation script also pass. See [the source hashes, fixture hashes, save policy and remaining limitations](measurements/shared-host-staging-20261118.json). No production service was deployed or changed by these checks.

## 1. Preserve the working installation

No live deployment or paid resource change is required to run the local checks below.

1. Keep using the existing [game](https://expanse-mud.onrender.com/). Leave its MMO switch closed.
2. Open the existing service in the [Render Dashboard](https://dashboard.render.com/). Record the deployed commit from **Deploys**, Python version, start/build commands, persistent-disk mount, and configured world/update identity. Keep secrets in Render; do not put them in an issue, screenshot or GitHub file.
3. Check **Settings → Auto-Deploy** is **Off** before merging development work. This lets the owner select a tested commit deliberately. [Render deploy controls](https://render.com/docs/deploys).
4. Before any later restart/deployment, every active player must use **Save & quit** and wait for confirmation. From **World & saves**, download the original imported world and that account's manual saves. Keep the selected compatible update `.expanse` too. Each player downloads their own checkpoint. Owner drafts must be exported separately through the Creator. [Existing backup and restore instructions](../RENDER-SETUP.md#back-up-and-restore).
5. A production cutover also needs a consistent backup and verified restore of the complete data directory: accounts, roles, ownership, imported worlds, drafts, save slots and other persistent stores. The current manual-save download is **not** this administrative backup. Do not copy a changing SQLite database as an ordinary file and assume it is consistent. Do not delete or repurpose the existing disk while preparing staging.

## 2. Review and run the code without touching saves

Use the [repository](https://github.com/neophyt1983/Expanse-MUD) and the implementation pull request's **Files changed** and **Checks** tabs. The permission groundwork is tracked in [PR #13](https://github.com/neophyt1983/Expanse-MUD/pull/13). Preserve current main-line engine fixes and the asset-measurement documents when integrating it.

Download the implementation branch through GitHub's **Code → Download ZIP**, or clone that branch into a new directory. This public repository download needs no terminal GitHub login. Open a terminal inside its extracted directory. Run tests in this **separate checkout**, never against `/var/data/expanse` or the existing Bazzite save directory. A Python virtual environment changes only this checkout; no `dnf` or operating-system replacement is needed.

Existing permission and private-isolation checks can be run from that checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_mmo_access.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_mmo_modes_roles.py' -v
PYTHONPATH="$PWD" .venv/bin/python tests/test_multi_player_isolation.py
.venv/bin/python -m unittest discover -s tests -p 'test_shared_authority.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_shared_host_persistence.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_shared_host_transport.py' -v
```

The candidate is checked on Python 3.12 and the target Python 3.14 runtime. Use Python 3.14 when it is available. These commands exercise temporary fixtures, not the live service or the full authored game. The authored-world tutorial suite needs its separately supplied compatible game directory; it is explicitly skipped when that file is absent.

The lower-level generic host checkpoint tests still verify that the engine itself does not invent saves on ordinary disconnect. The shared staging service adds the MMO-specific automatic checkpoint policy around that engine. Test both layers; a generic host-only pass does not prove MMO exit/timeout saving.

### Optional local browser trial

The isolated staging entry point is `python -m server.shared_staging`. It binds only to `127.0.0.1`; it is not a public Render or LAN entry point. It requires the explicit `EXPANSE_SHARED_STAGING=1` opt-in and a dedicated runtime directory. It accepts a `.expanse` file or an authored world directory and copies/imports it into that isolated directory. It does not import production account databases or alter the public gateway's MMO switch. Sessions must be signed into again after restarting staging.

First create a separate trial parent. Save the printed path if you want to reopen this trial later. Enter the full path to a current, compatible `.expanse` file when prompted:

```bash
expanse_trial_root=$(mktemp -d "$HOME/Games/text-rpg/Expanse-Shared-Trial.XXXXXX")
export EXPANSE_TRIAL_ROOT="$expanse_trial_root"
printf 'Trial directory: %s\n' "$EXPANSE_TRIAL_ROOT"
read -r -p "Current .expanse file, full path: " EXPANSE_TRIAL_ARCHIVE
export EXPANSE_TRIAL_ARCHIVE
```

The startup command below uses the existing validated importer for `.expanse` archives and places no worlds in the development checkout. If it reports a validation error, stop and review that message; do not extract an unvalidated archive over existing game files.

Configure a disposable staging owner. Use different credentials from your real game account. The password is 15–128 characters and the terminal hides it:

```bash
read -r -p "Staging owner name: " EXPANSE_OWNER_NAME
read -r -s -p "Staging owner password: " EXPANSE_OWNER_PASSWORD
printf '\n'
export EXPANSE_OWNER_NAME EXPANSE_OWNER_PASSWORD
export EXPANSE_GUESTS_JSON='[]'
EXPANSE_SHARED_STAGING=1 .venv/bin/python -m server.shared_staging \
  --world "$EXPANSE_TRIAL_ARCHIVE" \
  --directory "$EXPANSE_TRIAL_ROOT/runtime" --port 8870 --idle-timeout 900
```

Open [the local trial](http://127.0.0.1:8870/) in your browser. Sign in with those staging credentials. Use the controls actually supplied by the candidate; unsupported editor/publication/moderation operations remain closed. Ctrl+C stops only this staging process. To resume the same trial later, set `EXPANSE_TRIAL_ROOT` to its printed directory and `EXPANSE_TRIAL_ARCHIVE` to the same source file, configure the same test-account names and run the same command. Do not make a new trial directory when testing checkpoint restart recovery.

The idle timeout defaults to 900 seconds (15 minutes without an incoming command). `--idle-timeout` accepts seconds for a shorter disposable test. In this shared runtime, exit commands—including legacy `leave_no_save`/`quit` requests—save shared progress rather than discard it; a socket disconnect or session revocation also invokes an automatic checkpoint. A forced process kill or power failure is not a clean player exit and must not be presented as guaranteed saved progress. Test successful checkpoint confirmation and failure reporting separately.

Additional configured test accounts use the existing `EXPANSE_GUESTS_JSON` array of objects with `name` and `password` fields; never paste real account passwords into a committed file. Automated multi-client integration tests provision their own temporary identities. A later manual multi-device trial needs the production-ready authenticated network adapter; this loopback entry deliberately does not open your computer to remote players.

## 3. Prove the shared-world and access boundaries

Use separate test accounts, separate browser profiles/devices, and one dedicated test-world identity. Do not use two tabs sharing the same login cookie to represent independent players.

| Check | Required result |
| --- | --- |
| Two concurrent players | Both join the same host/world, have different server-owned character IDs, see one another and receive server-confirmed movement. |
| Four concurrent players | All four remain in that same world while moving, chatting and interacting; no additional private worker is substituted. Record actual resource use. |
| Finite interactions | A pickup/trade changes authoritative inventory once and is reflected to affected clients. Competing requests cannot duplicate goods or rewards. |
| Character ownership | Account B cannot resume, load, save, delete, transfer or trade as account A, even by copying IDs or adding a forged account/role field. |
| Session lifecycle | Logging A out or revoking its session immediately blocks further protected messages without disconnecting B. Reconnecting restores only the caller's own character. |
| No_Edit | Direct editor, import/export, mutation and moderation calls are denied, regardless of visible buttons. |
| Full_Edit | Only the supported creator operations are permitted; kick/ban/DM/moderation remains denied. |
| Admin | Supported editing and moderation are allowed; another account's character is not impersonated. Only the configured owner assigns roles. |
| Live downgrade | Removing a role takes effect on the next protected operation from an already-open connection. |
| Shared persistence | Explicit Save and automatic MMO exit/timeout checkpoints record a coherent world-and-character snapshot; restart recovers it. A failed checkpoint leaves the previous checkpoint loadable and is not reported as successful. |
| MMO exit and timeout saving | Test normal exit, legacy `leave_no_save`/`quit`, socket disconnect, revoked session and idle timeout; each automatically saves the shared world's authoritative progress. Rejoin after restarting the staging process and verify it. |
| Single Player manual saves | Existing Single Player movement, disconnect, refresh and logout still do not publish gameplay checkpoints. Save and Save & quit remain the deliberate checkpoint controls. |
| Private-world regression | Existing Single Player accounts, original imported identities, saves, settings and owner drafts remain separate and usable. |

Record each command/test name, candidate commit, target Python version, fixture/world hash, result and remaining limitation. A mock socket test is not a physical-device test; a small fixture is not a full-world capacity measurement. Unsupported operations must remain denied and listed as pending.

## 4. Finish the gateway and editor integration

The public gateway must authenticate MMO requests and route all authorized players to one dedicated shared worker, while preserving existing per-account Single Player routing. The shared worker must receive trusted server-side identity rather than browser-provided account names. It must enforce the permission/ownership policy on actual commands, not just in a separate unused helper.

Complete all existing Creator/API/DM boundaries and current-session revocation checks. Keep drafts distinct from live-world publication. Verify process startup, only-one-worker ownership, shutdown, empty-host behavior, clock progression, capacity rejection and explicit recovery after failure. The current private-worker process limit is not a shared-player capacity limit.

**Do not remove the public 503 gate as a shortcut.** Local staging evidence permits further review, not public activation.

## 5. Measure the current host before adding caching

1. In Render open **Expanse-MUD → Metrics**. Capture the same trial window's CPU, memory, disk use and outbound HTTP/WebSocket traffic. Note the player count, activity and deployment commit. [Service Metrics](https://render.com/docs/service-metrics).
2. Open the workspace's **Billing** page and record the current bandwidth allowance, used amount, billing period and actual rates. The compute size does not identify the workspace plan. [Outbound bandwidth](https://render.com/docs/outbound-bandwidth).
3. Use the existing [measurement directions](ASSET-DELIVERY-FOLLOWUP.md#reproduce-and-collect-the-missing-evidence) for comparable cold/warm/reconnect samples. The tools write new reports and avoid dumping account tokens or private gameplay bodies. HTTP resource timing does not include WebSocket frames.
4. Implement the approved sequence: hashed application assets; host-selected approved media manifest; integrity-checked missing/changed downloads; bounded browser/native storage; compatibility fallback. Keep accounts, HTML/bootstrap, saves, private APIs and editor state uncached. Android and installed-client storage need their own verification.
5. Repeat equal-activity measurements before claiming savings. Cache tests must cover one changed file, corrupted/partial downloads, eviction, offline/storage failure, old clients, world switch, logout/account switch and role revocation. Cache cleanup must preserve saves, settings, authored worlds and application identity.

Render's current outbound chart uses hourly windows and can appear about an hour after a window ends; do not interpret an immediate zero as no traffic. Asset reuse does not eliminate authoritative simulation traffic or the existing compute/disk cost. No new paid CDN or cache service is required for this investigation.

## 6. Validate on Render only after the local milestone

Do this only after gateway/editor/persistence code is implemented and reviewed. A separate Render staging service or persistent disk may cost money; the owner must choose and approve it before creation. Local staging is the no-new-resource starting point.

1. Use an isolated staging account store, shared-world directory and test-world copy. Do not attach production saves, reuse production passwords or point two running services at one writable database.
2. Pin the reviewed candidate commit, use the supported Python version and matching world, then deploy that staging candidate. Record the exact source SHA. Keep public production MMO disabled.
3. Verify `/healthz`, HTTPS/WebSockets, authenticated login, two then four players, role changes, account isolation, editor denials and the complete MMO automatic-exit/timeout-save, explicit-save, restart and failure matrix on the actual resources. Verify Single Player still requires manual saving.
4. Place persistent state beneath the staging disk's mount path and keep one writer instance. Render disks are runtime-only; builds, pre-deploy commands and other service instances cannot access them. Disk-backed deployments include downtime. [Persistent disk behavior](https://render.com/docs/disks).
5. Repeat on desktop and mobile browsers plus supported installed clients; check holds/taps, reconnect/background return, layout, conversation, quest completion and Save & quit. Record actual devices/browser versions.
6. Test rollback using staging data first. A Render code rollback retains the disk's current data, so database compatibility and a verified data restore must be part of the plan. [Render rollbacks](https://render.com/docs/rollbacks).

## 7. Open the public shared world only after acceptance

Publish the test evidence and limitations with the candidate release and coordinate the same engine/protocol revision across this work and the deployment work. All five gates—shared world, account isolation, editor authorization, persistence and multiplayer—must pass on the intended runtime. Until then the public MMO remains unavailable and Single Player continues normally.

Once the owner approves that concrete tested release, announce maintenance, have players Save & quit, verify backups, and deploy the exact approved commit through **Manual Deploy → Deploy a specific commit**. Recheck the existing solo save before reopening and then admit a small invited shared-world cohort. Expand measured capacity gradually; no 128-player claim follows from a four-client trial.

Keep the previous working release and recovery procedure available. Do not import a replacement world over an existing adventure merely to activate networking, change application identity or recreate users. Introduce MMO exit/timeout saving deliberately as the shared-mode policy; do not apply it to Single Player.
