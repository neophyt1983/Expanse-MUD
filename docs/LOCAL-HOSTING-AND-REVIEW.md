# Local hosting and the November 19 world review

## Recommended development direction

Use a **PC as the authoritative development host**, with the existing local
desktop client and an Android client connecting to the same engine. Keep a
cloud deployment as an optional, later host for a world that must remain
available while the owner's PC is off. Defer Apple-specific packaging and
claims until there is a machine on which to test them.

This is a deployment direction, not a second game implementation. A shared
world still needs one authority for time, stock, NPC decisions, permission
checks, quests and saves. A local solo game can put that authority on the same
PC as its interface. A hosted session puts the authority on one host and sends
each client only its permitted view. Two independent devices cannot safely
resolve the same theft, resource harvest or last shop item by separately
editing inventories and merging afterward.

Android is the client priority in this phase. Android limits background
execution, and work is not guaranteed to continue after the app leaves the
foreground. A phone can be a later offline-play target, but it should not be
the first always-on host for everyone else's persistent world. See Android's
[background task guidance](https://developer.android.com/develop/background-work/background-tasks).

| Choice | Useful now | Constraint |
| --- | --- | --- |
| PC host + local desktop client | Rapid debugging, profiling, local solo saves and host testing | The PC must remain available during a hosted session |
| PC host + Android client | Test touch layout, reconnects, asset reuse and latency against the same rules | Native Android packaging/device behavior still requires actual Android testing |
| Render host + PC/Android/browser clients | Public address and a world independent of a player's PC | Recurring compute cost and a finite CPU/memory budget |
| Independent peer simulations | Possible future research | Host migration, conflicting transactions and shared save authority are not implemented by this update |

The public MMO gate remains closed. Existing local/shared-host staging and its
account-isolation, persistence and concurrency gates remain in force; see
[MMO-MODES-REVIEW.md](../MMO-MODES-REVIEW.md). This review does not claim tested
MMO capacity or seamless host migration.

## What the Render inspection establishes

The checked-in `render.yaml` requests one `1c-2g` instance, a persistent disk and
the `/healthz` endpoint, with automatic deployment off. Render documents
`1c-2g` as one CPU and 2 GB of memory; this is a source configuration, **not a
verification of the live plan or the user's bill**. See
[Render compute plans](https://render.com/docs/compute-plans) and its
[pricing page](https://render.com/pricing).

`render_server.py` launches a `private_game.py` process for each active private
adventure. `EXPANSE_MAX_ACTIVE_GAMES` defaults to two and can be configured
between one and eight. Each private process loads and simulates its own world.
Consequently, multiple private adventures multiply CPU and memory work; they
are not merely extra views onto one simulation.

The reported production crash is not diagnosed. The successful build log from
the user demonstrates that dependencies installed and a deployment became
live at that time. It does not contain the later crash exception, exit code,
memory event or health-check history. The connected Render account required a
confirmed workspace before service logs and metrics could be read. No private
crash evidence was obtained, and no service was restarted, scaled, suspended
or redeployed in this review.

Before any infrastructure change, obtain the failure event, process logs and
CPU/memory trace for the same time window. An out-of-memory termination, an
application exception and a long synchronous simulation update require
different fixes. Increasing the instance size without that evidence would
not establish that the underlying defect was resolved. Render's
[health-check documentation](https://render.com/docs/health-checks) explains
its restart behavior; it is not evidence that a health-check failure occurred
on this service.

## Performance work included

The [populated-world profile](POPULATED-WORLD-PROFILE.md) uses the real
`GameServer` constructor with temporary saves and read-only world inputs.
It separates the expensive first simulation update from subsequent ticks and
distinguishes cProfile timing from ordinary elapsed time. These measurements
describe this development environment, not a Render latency benchmark.

The profile led to concrete reductions in redundant work. Conversation contact
descriptions can stop rendering equipment after finding the same visible
body garment as before. Animals are processed once per tick, with a second
pass reserved for creatures actually spawned or replaced later in that tick.
Neither change skips inventory, permission, visibility or time rules. The
profile document records exact call counts, timing variance and any remaining
enabled-content hotspots.

## Implemented engine and interface changes

The feature branch builds on the separate building-navigation, panel,
custody, theft-feedback and carriage fix. It adds the following behavior:

| Area | Implemented behavior |
| --- | --- |
| Theft and observation | Task-specific Burgling, independent Observation contests, bounded haul quality, exact removal from real inventories/containers, witnessed shouts and existing justice handling |
| Task progression | Real successful and valid failed work credits saved fractional practice; each higher task level needs more practice; paid lessons respect the same curve and instructor ceiling |
| Skills interface | A character can see their own levels, practice progress, learned recipes/techniques and reading records |
| NPC knowledge | Saved bounded founding knowledge, actual observation/reading/conversation, qualified sources and no global private-catalog shortcut for quest workers |
| Emotion and expression | Mixed emotional state, associations from experience, contextual discussion, varied emotional singing, complete speech bubbles and explicit conversation roles/emphasis |
| Animals | Purposeful movement, feeding/rest/shelter, finite feed use, explicit real livestock owners/enclosures, escape/recovery and authored bird flight ranges |
| Guilds and quests | Local lessons and persistent need-based requests; opted NPCs physically read, ask, travel and perform their tasks; actual shared stock determines outstanding demand |
| Medical care | Present qualified staff, actual clinic supplies, finite payment, visible treatment availability and reasons |
| Paid market work | Actual vacancies and employers, reserved materials/wages, timed work, finite output, payment once, interruption/refund and no offline player work |
| Art | Known material-consuming projects, timed work, maker/date provenance, finite patron commissions and personal appreciation affected by taste/mood/history |
| Books | Whole physical copies, source-gated material-consuming copying, source lineage, excerpts, revisions, reading history and qualified claims |
| Supply rules | Real local gathering sources, ingredient/tool/skill/read-source checks, no production or work reward without actual inputs, and reported production shortages |
| Rest | Faster advancement through the same authoritative clock when connected players are safely resting, with interruptions and per-pass budgets |
| Map | One distinct cell per actual room on its floor, stacked true storeys, open courtyards, named adjacent doors, stale geometry rejection and removal of decorative phantom houses |

Graphical work, treatment, art, guild and theft actions are authenticated to
the selected character and room. The host rechecks availability after awaits;
the UI uses correlated requests and does not automatically retry an unknown
result. Passive map/panel refreshes do not create work, knowledge practice,
goods or rewards.

## Separate authored review world

`tools/stage_world_update.py` composes all content changes into a **new**
directory and optional archive. The original 1.9.16 files are hashed before
and after; they must remain unchanged. The staged world preserves existing
room/item/NPC identities and carries a separate review name/slug. No live
world import or saved-character reset is part of staging.

The composed review contains 32,426 authored rooms, 259 building definitions,
3,782 NPC definitions, 5,128 items, 4,026 recipes and 2,650 quests. Added content
includes 15 task guilds, 66 requests/exercises, 17 staffed care sites, a four-room
upstairs hospital linked to its existing downstairs Healing House, four
artistic plans and patron orders, 23 sourced publications with 51 initial
copies, and an existing market's two-slot paid kitchen job. Those are authored
definitions and placements, not a promise that all actors are simultaneously
spawned or known to a character.

The map repair corrects 232 legacy civic rooms in 40 complexes. Their old
artificial high layers are replaced by the actual local street level and
internal stair relationships. Genuine multi-floor structures remain stacked.
The map audit checks all authored building members, room coordinates, exits,
runtime roofs and per-floor room/cell counts. The combined world has no
structural map-audit issues or loader validation errors; the existing loader
still reports 27 warnings, retained in the staging report.

Use `tools/audit_supply_chains.py` as a creator-side audit. It traces initial
physical stock, placed resources, finite/conditional recoveries and supported
recipe chains. Its full report includes hidden world data and must never be
sent as player knowledge. A source that exists somewhere is not proof that
an NPC knows it, can reach it safely, can obtain it in the current season, or
can afford it; runtime checks and actual routes still apply.

```bash
python tools/stage_world_update.py \
  --input /path/to/read-only/world-1.9.16 \
  --output /path/to/new-review-world \
  --archive /path/to/new-review-world.expanse \
  --report /path/to/staging-report.json
```

The review world requires the matching engine feature branch. A world archive
does not install new Python/JavaScript engine code into an older app.

## Remaining release and design work

The final local suite ran 410 Python tests with 409 passes and one documented
Windows-native sharing-semantics skip. Both actual 1.9.15 source/archive gates
were enabled. All 114 JavaScript tests passed. Real Qt WebEngine 6.12.0 checks
passed 117/117: Location & Inventory 27, passages 6, custody 12, conversation
28, emotional expression 8, complete speech 12, and task/work actions 24.
The compact world, source-chain and layout evidence is in
[world-review-20261119.json](measurements/world-review-20261119.json).

This is a source/content review, not a released Windows installer, Android APK,
Apple build or deployed Render update. Actual PC and Android device tests are
still needed for installation, in-place updates, resume/reconnect and long
play sessions. The existing engine/app update contract preserves accounts,
saved worlds, characters, settings, exports and backups.

The [climate and seasons research](CLIMATE-SEASONS-RESEARCH.md) is a design and
data audit. The expanded latitude/elevation/ocean/rain-shadow seasonal model,
winter storage planning, warm clothing and clean-water survival balance have
not all been implemented by this review. Existing clocks/weather continue to
operate; the document must not be described as a completed climate release.

Initial NPC background records are bounded founding histories and instruction,
not a claim to have simulated every minute of an entire prior lifetime.
Patron-funded architectural work currently produces a real plan for an actual
known building; it does not autonomously construct a new building. Existing
regional workshop logistics retains its abstract transfer model; NPC guild
and artistic tasks use actual local actions and bounded known routes.

Run the regression workflow on the exact review commit and keep the existing
public-MMO and deployment gates. Cloud billing and crash resolution remain
unverified until the actual service evidence is available.
