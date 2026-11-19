# Task guilds, artistic work and staffed care

These services use the shared living world for players and NPCs. All writes go
through normal authoritative commands. A map refresh is a read: it does not
teach a recipe, accept work, create stock, advance time, or pay a reward.

## Persistent guild work

`engine.guilds.projection(world, actor)` returns local guild memberships,
lessons, and genuinely disclosed work. `guilds.act` rechecks the real actor,
room, membership, task skill, source, objective, receiving container and payer.
The canonical command is:

```text
guild
guild join "guild-id"
guild learn "guild-id" "lesson-id"
guild accept "guild-id" "quest-id" [revision]
guild complete "guild-id" "quest-id" [revision]
```

Membership is stored separately from the character's political faction.
Ordinary story quests retain their existing objective and reward machinery.
Guild skill prerequisites use task levels, not overall character level.

An optional `group.guild` declares `enabled`, `tasks`, actual service `rooms`,
`join_fee`, optional skill/quest `requirements`, and `lessons`. Every lesson
names an actual instructor source and a skill belonging to that guild. The
instructor must really be present, awake and willing. Lesson fees transfer to
the instructor. A lesson is taken once per character, and no character takes
more than one guild lesson in a game day. Clock rewind cannot reset this cap.

The lesson's `gain` (1–5) is **practice intensity in novice-equivalent units**,
not a guaranteed number of levels. `task_skills.training` applies the shared
increasing practice threshold. `min_level`, `max_level` and quest prerequisites
still govern eligibility. Higher skill levels require more actual practice.

Example group configuration:

```json
{
  "guild": {
    "enabled": true,
    "tasks": ["farming"],
    "rooms": ["actual-garden-room"],
    "join_fee": 0,
    "lessons": [{
      "id": "garden-foundations",
      "name": "Garden foundations",
      "skill": "farming",
      "min_level": 0,
      "max_level": 20,
      "gain": 2,
      "cost": 2,
      "trainer": "actual-grower-source"
    }]
  }
}
```

A need-backed quest has an ordinary stable quest ID, `progress_scope` set to
`accepted`, local offer/turn-in rooms, an actual NPC/book source, and:

```json
{
  "guild": {
    "id": "guild-farmers",
    "skill": "farming",
    "difficulty": 0,
    "need": {
      "kind": "stock",
      "room": "actual-garden-room",
      "container": "actual-owned-container",
      "item": "actual-carrot-item",
      "target": 4,
      "batch": 2,
      "recipient": "actual-grower-source",
      "gold_per_unit": 1
    }
  }
}
```

The need is the current difference between the target and that physical
container's actual stock. Contributions are capped by this deficit, the batch
size, carried unequipped goods and the representative's actual purse. Both
players and NPCs reduce the same demand. The transfer conserves items and
money. A nonzero delivery earns progressive practice under a durable unique
contribution ID.

There is no daily refresh or timer-based reopening. Time passing does not
change a fulfilled need. Actual consumption can reopen the same request.
Changing the target, stock or payer state changes its numeric revision, so a
stale GUI action cannot duplicate payment. The ledger persists in
`living_state.guild_needs_v1`; character membership, lessons and contributions
persist in `progress.guilds_v1`.

### What an opted NPC actually does

An explicit `npc.guild_plan` selects a finite list of guild IDs and whether
the resident may learn, take quests and explore. No profession automatically
opts everyone in. The executor:

1. Reads a real book or talks with an actual eligible local person.
2. Remembers the disclosed request, ingredients and named destinations.
3. Learns route edges only from rooms physically visited.
4. Uses normal movement checks, real timed gathering/crafting and finite
   inventory transfers.
5. Rechecks objectives and live shared demand at hand-in.

The background interest helper may rank the explicitly allowed guilds; it
does not grant goals or routes. An NPC who lacks information can read, ask or
explore visible open routes. They cannot find moved people by consulting the
world's live entity table. A known destination is not a known path. Hidden,
locked and private routes retain their ordinary restrictions.

The executor supports supply, delivery, gathering/crafting, reading, talking
and visiting. Unsupported combat, escort or specialized story objectives stay
pending. Accepting a request never completes its steps. One operation per game
minute and saved timestamps prevent replay or clock rewind from inventing work.

## Clinical services

The existing `service treatment` command delegates to `clinical_services.treat`
only when the room has an enabled `clinical_services` object. Unauthored legacy
services retain their prior behavior.

```json
{
  "services": {"treatment": 8},
  "clinical_services": {
    "enabled": true,
    "staff": ["actual-doctor-source"],
    "container": "actual-care-cabinet",
    "supplies": {"bandage": 1, "herb": 1, "water": 1},
    "min_skill": 20
  }
}
```

An actual awake, qualified, willing practitioner must be in the room. The
clinic must be open and have every required item in its actual care cabinet.
The patient must have an injury or disease and enough money. Treatment consumes
supplies, transfers the fee to the practitioner and clears the game's existing
injury/disease conditions. It does not invent HP effects or a new medical model.
The practitioner gains progressive Healing practice. A healthy repeat request
does not charge or train. Missing staff, supplies or funds leave the condition
unresolved. Local NPC patients use the same service.

Supply consumption creates a real stock deficit in the same cabinet used by
the Healers Guild. There is no emergency restock. The cabinet request remains
until it is actually supplied; treatment fees can fund later replenishment.

## Artistic work and commissions

`recipe.artwork` adds an individually made work to the existing recipe model:
finite `ingredients`, a real `station` and game `minutes`. It declares `kind`
(`poetry`, `painting`, `sculpture`, `architecture`), `style`, title/description,
task difficulty, optional skill minimum and, for architecture, a real building
ID. Ordinary recipe outputs must be empty: this process creates one unique
physical item. Architectural work requires physically visiting the subject's
rooms and produces a plan; it does not instantiate a building.

Both `art begin` and the `craft` bridge enforce the recipe's actual required
reading, carried tool, canonical task-skill threshold, abilities and prerequisite
quests before consuming materials. Knowing a plan does not satisfy a separately
required book read or replace its tools and training.

```text
art
art begin "artistic-plan-id" ["title"]
art finish
art resume
art cancel
art accept "patron-entity-id" "offer-id" [revision]
art deliver "patron-entity-id" "offer-id" "work-item-id" [revision]
art decline "patron-entity-id" "offer-id" [revision]
```

Starting reserves no imaginary stock: carried unequipped materials are used
immediately. Work time counts only while awake at the actual station under the
authoritative game clock. Offline players, sleeping actors, absent workers,
paused jobs and simultaneous committed work do not progress. A cancelled
project does not refund materials already used. Finishing creates exactly one
unique item and awards task practice. Higher skill cannot yield lower quality
under the same server roll; the formula is a game-balance choice.

The item records its creator's stable identity and name, creation time/place,
plan, style and quality. The source is retained after the creator dies. Old
authored works can say `attributed` or `uncertain`; missing identity or dates
remain unknown. Poetry also uses the shared publication/edition schema. A
default workshop verse is explicitly a study after an authored form, while a
player-supplied verse is recorded as original text.

An NPC's `art_commissions` declares finite one-off offers: ID, name, enabled
state, plan, price, minimum quality and minimum personal appreciation. An
`art_taste` object supplies bounded preferences for styles/kinds. The actual
awake local patron must be willing and able to fund the work. Acceptance does
not pay. A commission requires the accepting maker's own work, begun after
acceptance. On delivery the piece transfers to the patron and the exact fee
transfers from their purse to the maker. A completed commission never renews
because time passes.

Craft quality and the patron's judgment are distinct. Judgment combines the
work, authored tastes, current public emotional expression and bounded personal
artistic experience. The response explicitly calls this a personal opinion.
Each patron/work judgment is retained; repeatedly clicking delivery cannot
reroll it. Rejected works remain with the maker and earn no payment.

Opted `npc.art_plan` residents must actually encounter a configured patron,
learn the plan from a genuine book or conversation, and obtain materials over
remembered routes. They perform the same timed work and delivery API as
players. A rejected work waits for a new decision instead of causing endless
automatic replacement production.

### Backend contract

```python
artworks.projection(world, actor)                 # pure
artworks.begin(world, actor, recipe_id, title=None, text=None)
artworks.advance(world, minutes)                  # authoritative clock hook
artworks.finish(world, actor, rng=None)
artworks.active(world, actor)
artworks.interrupt(world, actor, reason)           # idempotent pause
artworks.resume(world, actor)
artworks.act(world, actor, patron_id, offer_id, action,
             work_id=None, expected_revision=None)
artworks.restore(world)                          # before inventory/floor filtering
```

The map projection contains only known plans, own work, own active project and
actual local patron offers. No private patron inventory or hidden taste scores
are serialized. The unique catalog, jobs, commission receipts and judgments
persist in `living_state.artworks_v1`.

## Reproducible authored-world additions

The original supplied worlds are read-only inputs. Both tools expose
`apply(data, metadata) -> report` for plural in-memory catalogs; the parent
staging process can compose them with knowledge and map migrations:

1. `tools.stage_guild_clinic_content.apply`
2. `tools.stage_art_content.apply`

The guild/clinic patch adds 15 professional guilds at existing places, 66
physical requests or supervised exercises, 32 anchored ledgers and two opted
existing growers. It staffs 16 existing treatment sites, including alchemy
care counters, and adds a four-room upstairs Dawnwatch hospital with two finite
named practitioners. The four new rooms occupy distinct unused coordinates:

| Room | x | y | z |
| --- | ---: | ---: | ---: |
| guild_dawn_hospital_reception | -2 | -5 | 1 |
| guild_dawn_hospital_treatment | -1 | -5 | 1 |
| guild_dawn_hospital_ward | -2 | -4 | 1 |
| guild_dawn_hospital_dispensary | -1 | -4 | 1 |

Reciprocal stairs connect the existing Healing House. The building has explicit
`street_level: 0`; the four interior rooms are real upstairs rooms. The existing
ground-floor Healing House belongs to the same building family. Any existing
authored building ID is preserved, so the stairs and upstairs footprint cannot
drift into a different structure during map layout.

The art patch adds four plans, four local studio sources, four finite patron
orders and four explicitly opted existing artists. Initial materials are
transferred from existing workshop stock into those artists' inventory, with
exact subtraction recorded in the report. It creates no new artist NPCs and
does not add recurring gifts or restocks. Existing paper, ink, cloth, wood,
water and herb supply chains remain the source of later work.

Both patches validate against actual referenced catalogs and are idempotent
through metadata markers. Neither is a live-save refill operation.
