# Animal activity, funded employment and shared rest

This document describes the implementation and local verification on the `feature/burglary-observation-20261119` branch. It does not certify a production deployment or import into an existing save. The original Wild Lands 1.9.16 input remains unchanged; staging scripts compose a separate candidate world.

## Animal behavior and ownership

[`engine/animal_life.py`](../engine/animal_life.py) advances actual, living, non-sentient animals. It neither creates a population nor infers ownership from a name. Explicit species classification supplies the animal category; players, sentient residents, magical creatures, monsters, undead actors and public carriage fixtures are excluded.

Animals consume real food from carried items, ground items, eligible managed stores or a shared resource harvest. A harvested batch has real availability and renewal state; any unused yield remains as physical stock. Predation uses the existing wildlife ecology rules and real prey and drops. Protected exhibits, owned herds and companions keep their existing protections.

Wild adults alternate bounded nearby exploration with rest. A hungry animal can search permitted neighboring habitat for food; a satiated animal can inspect its territory before resting. This is not a global resource search. Paths use ordinary visible, permitted exits and normal movement. Hidden routes, locked doors, barriers and indoor walls remain effective. Bad weather, flight exhaustion, a pen, a caregiver's order, handling, sleep and unavailable food produce a readable activity reason rather than unexplained stillness.

State is stored on the actual actor under `progress.animal_life_v1`: hunger, action times, resting state, explored local trail and flight budget survive normal snapshots. A same-minute repeat or a rewound clock cannot produce another meal or action. Public activity projection exposes the action and reason, not a private keeper ID.

### Species configuration

Species may author `animal_behavior`:

```json
{
  "enabled": true,
  "awake_start": 360,
  "awake_minutes": 960,
  "action_minutes": 5,
  "explore_minutes": 30,
  "rest_minutes": 10,
  "territory_steps": 3,
  "habitats": []
}
```

These values are the defaults. Time uses the world's 1,500-minute day. `habitats` can list up to eight terrain or environment names; an empty list uses the animal's home habitat. Territory is limited to six route steps and searches to 64 rooms. Setting `enabled` to false leaves that species with its prior behavior.

Birds are flightless unless they have a usable explicit `flight` profile:

```json
{
  "mode": "short",
  "endurance_steps": 2,
  "range_steps": 1,
  "recovery_minutes": 20
}
```

`mode` is `flightless`, `short` or `sustained`. Short flight permits at most four endurance steps and two range steps; sustained flight permits at most 256 and 16 respectively. Every real outdoor edge costs endurance. These are game balance units, not measured biological distances. Flight changes how an animal traverses an allowed route; it creates no new route.

### Actual livestock and keeper work

Ownership can be authored on an individual NPC definition or, preferably for reused animal templates, its actual room spawner:

```json
{
  "npc": "local_goat",
  "count": 2,
  "livestock": {
    "owner": "local_keeper",
    "home": "farm_pen",
    "rooms": ["farm_pen", "farm_barn"],
    "escape_chance": 0.02
  }
}
```

The owner is an NPC definition ID. The home and up to 16 enclosure rooms must exist. Spawner ownership applies only to actors from that exact spawner; another farm using the same animal template does not inherit it. Actual offspring inherit their parent's holding.

Escapes are a persisted, bounded daily opportunity and require an open ordinary exit. A keeper can notice an owned stray locally or through one accessible neighboring edge, walk to it and lead it back. A distant animal's saved ID is not a location report. Successful real recovery practices Ranching once for the action. A room can explicitly author `animal_shelter: true`; this does not alter its doors or access permissions.

### Reviewed animal content patch

[`tools/author_animal_profiles.py`](../tools/author_animal_profiles.py) produces a before-value-guarded JSON patch and can apply it only to a separate staging directory:

```sh
python tools/author_animal_profiles.py \
  --world /path/to/read-only-world-1.9.16 \
  --patch-output /path/to/animal-profiles-patch.json \
  --apply-to /path/to/separate-staging-world
```

On the reviewed original 1.9.16 data it proposes 27 explicit bird flight profiles, 1,067 existing spawner ownership records and 38 already-sheltered holdings. Ownership is grounded in a unique existing feed-store owner who is explicitly described as the local caretaker and actually works and spawns there. It skips 74 holdings without that evidence. It adds no animals, stock, cash or enclosure rooms and refuses changed spawner identities or conflicting prior values.

## Paid work uses real stock and wages

[`engine/employment.py`](../engine/employment.py) provides local assignments for both players and explicitly opted-in NPCs. Applying alone pays nothing. Starting work reserves one recipe's actual ingredients and the wage from the existing workshop treasury. Completed work goes through the normal crafting authority, adds the exact output to the workplace and pays the reserved wage once. Ordinary crafting supplies the task practice; employment does not award duplicate practice.

Before reserving anything, the service checks the actual local employer, worker eligibility and safety, custody and restraint, opening hours, workshop station, recipe reading source, required abilities, task level, carried tool, quest prerequisites, local ecology, material stock, treasury and unmet output demand. Existing work reservations count toward the stock target. Missing inputs or funds produce an explicit blocked reason.

Leaving, resting, injury, a changed work order, a clock discontinuity or an ended player session cancels the current batch and returns its actual reserved material and wages once. It retains the assignment so the worker can resume with `job work`. A player batch cannot finish while disconnected or after reload without its live session token. An NPC batch can continue through normal authoritative ticks. There is no background elapsed-time catch-up.

The assignment itself remains until `job leave`; a stopped batch does not automatically surrender the worker's place. No autonomous recruitment is enabled for unrelated residents.

### Room and NPC authoring

An existing workshop may post up to eight vacancies:

```json
{
  "employment": [
    {
      "id": "kitchen_helper",
      "title": "Kitchen helper",
      "employer": "market_trader",
      "recipe": "vegetable_stew",
      "wage": 3,
      "slots": 2,
      "target_stock": 12,
      "min_skill": 0
    }
  ]
}
```

The recipe must be listed in that room's actual workshop and have finite real inputs and outputs. Wages range from 1 to 1,000 gold, slots from 1 to 16, target stock from 1 to 1,000 and minimum task level from 0 to 100. Recipe duration is bounded to 1–120 game minutes. Artistic projects use their separate timed art service rather than this stock-production entry point.

An NPC can explicitly opt into a local vacancy:

```json
{
  "employment_plan": {
    "enabled": true,
    "room": "market_room",
    "vacancy": "kitchen_helper"
  }
}
```

The plan does not move or teleport the NPC. The actor must actually arrive by its ordinary schedule and be on duty. Existing caregiving, population, safety and clinical priorities run before a new job attempt. Attempts are bounded; absent a plan, legacy residents do not apply. An active worker is excluded from the old workshop producer pass to prevent duplicate goods and wages.

### Commands and UI contract

| Command | Effect |
| --- | --- |
| `jobs` or `job status` | Read local offers and the current assignment. |
| `job apply <id>` | Accept an available local assignment. |
| `job work` | Reserve and start one actual timed batch. Repeats do not restart it. |
| `job stop` | Return an active batch's escrow and retain the assignment. |
| `job leave` | Return escrow if needed and release the assignment. |

Inspection commands leave active work alone. In solo play, ordinary `wait` can advance already committed work through the shared simulation; it cannot create an assignment or wages by itself. In a host session, the authoritative lifecycle advances work. There is no private work clock or blocking production loop.

`employment.view(world, actor)` is a pure local projection. The host composes these terms into the common work-services cards. Graphical actions carry the authenticated actor and room, an opaque host offer ID and revision, plus request ID and sequence. They do not carry a client-selected wage, stock quantity, healing amount or production result. The server rechecks the current offer when acting.

Movement and valid rest interrupt employment and pause art. A paused art project retains its materials and time and does not prevent taking paid work. An active art project must first be paused or finished.

### Existing market staging

[`tools/stage_market_employment.py`](../tools/stage_market_employment.py) exposes `apply(data, metadata)` for plural in-memory catalogs and a standalone staging command:

```sh
python tools/stage_market_employment.py \
  --input /path/to/read-only-world-1.9.16 \
  --output /path/to/new-staging-world
```

It uses the existing Dawnwatch Produce Market (`fw_dawn_4`) and its Provision Counter. Aster Brightwell is the existing local employer and pantry owner. Two kitchen-helper places pay 3 gold per five-minute stew batch while stock is below 12. The reviewed source already has 240 treasury gold, 20 carrots, 20 onions, 20 potatoes and eight stew; the patch adds none of these. Existing provision trader Eris Reed receives an explicit local work plan using the existing schedule. Fixed grocery and hiring signs are added to the produce and fish markets; no duplicate building or NPC is created.

The script checks the actual room, ownership, worker schedule, recipe, money and supplies before editing, marks the applied patch and is idempotent. Reapplying does not restock a save. The original 1.9.16 data passed this staging validation without a source-file change.

## Faster sleep and rest

The host formerly disabled accelerated rest unconditionally. The current server allows it only when every active connected player is safely resting or sleeping. An awake participant, join, wake command, damage, danger, invalid token, movement or the earliest completed rest ends acceleration.

Each lifecycle pass can simulate up to six quanta of at most five game minutes, stopping after its adaptive CPU budget. Every quantum runs the same needs, NPC, weather, custody and other world systems. The server yields between lifecycle passes. A heavy populated world may complete fewer quanta; status text describes that limitation rather than promising a fixed rate. All participants share the same authoritative clock.

## Verification and evidence

Relevant regression files are executable without the production world or accounts:

| Test file | Verified area |
| --- | --- |
| `tests/test_animal_life.py` | 22 cases: real food and harvest, barriers, rest and exploration, flight budgets, keeper recovery, companions, exhibits, births, clock replay, late spawns and same-ID replacements. |
| `tests/test_animal_authoring.py` | Five cases: grounded ownership, before-value guards, idempotence and unchanged source files. |
| `tests/test_employment.py` | 20 cases: finite escrow, timed completion, interruption and replay, offline/reload behavior, pure projections, source/skill/tool prerequisites, NPC priorities and paused art. |
| `tests/test_market_employment_staging.py` | Five cases: no invented supplies or cash, reviewed source guards, idempotence, separate staging and actual player/NPC use of one treasury. |
| `tests/test_rest_acceleration.py` | 13 cases: host and solo acceleration, all-player eligibility, exact completion, damage and joins, clock validation, offline sessions and CPU bounds. |
| `tests/test_publications.py` | 12 cases for the related source/edition ledger, real reads, finite copies, preserved evidence roots and unchanged older text. |
| `tests/test_work_services_actions.cjs` | Seven cases: host-only action selection, pending/replay behavior, changed quotes, scope isolation, disconnection, timeouts and literal text rendering. |

The real Qt 6.12.0 task-actions probe passed **24/24** geometry checks across desktop 100%, 150% and 200% display sizes, 390×844 and 320×568 phone layouts, and 844×390 landscape. It checks the final guild prerequisite, final work button and complete disabled reason, theft controls, and final Skills knowledge/Close controls. The 320×568 work reason ended at 561.91 pixels inside a panel ending at 567; at 200% desktop it ended at 887.59 inside a panel ending at 898.

```sh
QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
python tools/probe_task_actions_layout.py
```

Use a Python environment containing PySide6/QtWebEngine. The unchanged 20-second watchdog now reports partial results and its pending stage if it expires. The successful measured run took 6.985 seconds without optional screenshots. Repeated offscreen screenshot readback was separately observed to exceed the global watchdog in this environment; the geometry assertions and timeout were not relaxed.

[`tools/profile_populated_world.py`](../tools/profile_populated_world.py) profiles an isolated real server world. On the original 5,205-entity fixture, eliminating the duplicate animal pass reduced `animal_life.step` and `config` calls from 10,410 to 5,205 per warm tick. The late wildlife phase still handles actual newly spawned or replaced actors. Cumulative animal-step time changed from 0.2657 to 0.1758 seconds in that measurement; wall-clock timing is load-sensitive, while the one-pass call count is deterministic. Enabled composed-content timing is recorded separately because it performs additional real animal behavior.
