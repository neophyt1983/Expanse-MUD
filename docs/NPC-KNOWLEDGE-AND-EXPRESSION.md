# NPC experience, knowledge and expression

This update separates a character’s learned experience from the Creator’s
complete catalogs. NPCs can retain mixed feelings, improve through actual
practice, know some local subjects well, and repeat a remote rumor without
turning it into verified knowledge.

## Founding a resident

`engine/npc_backgrounds.py` accepts optional version 1 `npc.background` source
parameters. It runs at fresh spawn, or at saved-life restoration only when the
Creator explicitly enables `migrate_existing`. A persisted background record
always wins; loading again never resamples it. `founding_residents.make` writes
conservative home/workplace parameters into a new adventure’s saved roster.

Sources can include a real home, an actual workplace, an associated caregiver
or instructor, posted workplace designs, and up to four books physically
available at home/work or carried during initial setup. A teacher’s actual
authored skill caps instruction. Workplace starter practice requires an
explicit corresponding occupation. Authored higher skill defaults and already
learned saved skills are retained.

Initial grants are capped at 12 places, 24 items and eight recipes. Nearby
places must be real, public and directly connected by an ungated exit. Dangerous
nearby places receive at most a private mention; they do not become explored
rooms or known routes. Reading grants use the book’s explicit knowledge table,
not a scan of the world. No inventory, money, completed action, accepted quest,
quest source, or successful objective is manufactured.

An optional `experiences` list can identify support, a strained interaction,
or help/harm from an actual associated authority. These sources seed bounded
lifetime associations, not a fresh emotional incident. Empty legacy histories
do not acquire an invented childhood. `interests(world, actor)` is a pure map
of task weights; guild behavior can use it to prioritize only already permitted
choices.

## Bounded knowledge for existing residents

`knowledge.known_ids(world, actor, kind)` is a read-only view of saved knowledge,
explicit NPC grants and actual current/home/work possessions and places.
`knowledge.ids` no longer returns the complete room/item/recipe catalog for an
NPC. Creator callers may still deliberately use `actor=None` for an unscoped
catalog. Ordinary NPC projections do not initialize history or grant practice.

Exact names in read prose establish a mention. They do not supply a complete
recipe or verify a remote place. Explicit `knowledge` grants and actual authored
quest leads retain their prior disclosure behavior. A fiction mention is an
opinion; a source explicitly marked rumor stays a rumor after repeated reading.

`knowledge_sources` keeps at most 192 recent subject records, four source
references per subject, eight evidence roots, and 128 replay tokens. Repeated
actual exposure can move familiarity from *mention* to *familiar* to *studied*.
It never converts a rumor/opinion into observation. Reprints inherit evidence
roots, so multiple copies are not independent corroboration. Evicting an old
familiarity index entry does not erase the character’s learned facts.

Action hooks are explicit:

- `knowledge.read_source` requires a real readable copy in the room or inventory,
  records the publication snapshot, and gives reading practice at most once per
  edition/game minute. Recalling a journal does not call it.
- `knowledge.observe_room` runs after an actual look/arrival. It remembers local
  objects/creature identities and the place observed. Map rendering does not
  call it.
- `town_talk.travel` records committed travel. Shared directions keep their
  source’s evidence roots where known; the listener does not gain a new first
  person observation merely by hearing them.
- NPC reading of local news occurs through the existing actual venue reading
  action, with bounded article memory and replay-safe practice.

`knowledge.learn_local_recipes` teaches designs posted at the actual current
workshop, or explicitly located there. Ingredient-name inference is restricted
to recipes explicitly marked `knowledge_scope: public`. Private designs need
an actual posted/read/shared source. New copy recipes use `requires_reading`;
`recipe_source_ready(actor, recipe)` is the pure check used before copying.
Actual publication memories, old reading journals, read-action history and
validated founding reading records satisfy that requirement.

## Literature and the field archive

Generated field entries no longer turn spawn rooms, encounter tables or
regional ranges into published sightings. Explicit authored public survey
entries remain available and keep their attribution. Catalog-derived creature
entries require a present/remembered encounter and provide limited
identification; a single sighting does not establish diet, breeding or range.
Local geological notes require knowledge of their own place. Archive projection
does not train familiarity.

`tools/stage_knowledge_content.py` provides `apply(data, metadata) -> report`
with plural catalog keys. It composes with the guild/clinic and art staging
tools. Its CLI requires a new output directory outside the original world:

```sh
python tools/stage_knowledge_content.py \
  --input /path/to/original-world \
  --output /path/to/new-review-world \
  --report /path/to/knowledge-report.json
```

Against the supplied 1.9.16 world it creates 23 works and 51 finite initial
copies: four shared everyday manuals, eight selections from actual local
cookbooks, three qualified ruler biographies, and eight local verse indexes.
The five shared designs cover paper, ink, cloth, a smith hammer and bread.
Each later copy consumes two paper and one ink at a scriptorium and requires
reading the source. New volumes are ordinary movable books; they do not use
automatic fixed-display restoration. Existing 1,144 publication records and
their prose remain intact.

The rulers’ available public profiles do not establish detailed childhoods,
birth/accession dates or moral verdicts. Their new biographies therefore keep
sourced profile claims separate from sympathetic and critical opinions.
They do not fabricate crimes, achievements, private memories or dated events.
Poetry indexes point to the original complete verses and distinguish a poem’s
speaker from the author or a current performer.

Publication circulation, lineage, immutable source snapshots and later claim
corrections are implemented separately in `engine/publications.py`. Older
physical copies remain readable. A correction is a new attributed claim,
not a rewrite of the older book’s text.

## Emotional expression and singing

`npc_emotions.project` combines current mood, actual needs, recent events,
bounded lifetime associations, known relationships and actual conversation or
performance context. Positive and negative feelings can coexist. An undetected
theft does not inform its victim; theft reactions come only from authoritative
actual detectors. Lifetime authority experiences can alter later trust/anxiety
without retaining every individual event forever.

Talk and Nearby render the complete mixture. Map bubbles retain the full
expression in their accessible description. Ordinary NPC speech is no longer
clipped to three lines: complete short ideas fit, longer speech can scroll,
and long turns receive more reading time.

Singing style is performance guidance, separate from literal authored verses.
Each actual performance snapshots its emotional mixture, audience context and
delivery variation. Refreshing a map never rerolls it. Dynamics vary within
bounded score parameters while authored pitches, timings, tempo, instrument
ownership and intentional lyrics remain intact. Each actual performer earns
singing practice with the unique event token. Legacy saves remain compatible.

The 1.9.16 `festival` context is distinct from ordinary performance. It requires
the singer’s assigned actual venue, weekday and time interval. Both unchanged
1.9.15 and 1.9.16 archives load successfully. This change does not add festival
travel or override an NPC’s other safety/availability constraints.

## Supply audit

`tools/audit_supply_chains.py` is Creator tooling only. It follows actual
floor/container/inventory/finite shop/workshop stock, placed resources and
encounters, explicit landmark search rewards, quest gates, and discoverable
recipe sources. A catalog entry or `item.location` alone does not count as
stock. It distinguishes renewable chains, finite initial supplies, finite
obtainable outputs, gated sources and bootstrap cycles. It reports first-batch
clinic/job shortages separately from general material reachability.

```sh
python tools/audit_supply_chains.py \
  --input /path/to/review-world \
  --output /path/outside/world/supply-audit.json
```

The audit does not simulate competing claims on a finite pile, travel
permissions, wages, trained skill, seasonal timing or a live save’s remaining
stock. Runtime actions continue to enforce those actual conditions. It never
adds an infinite source or publishes hidden origins to clients.

Expedition landmark searches also have finite sources. The persisted
`expedition_recoveries_v1` ledger remembers each room/reward pair independently
of who now carries the relic. Dropping, transferring, turning it in or reloading
does not refill that source. Only a successful first recovery grants observation
practice. Existing copies and ordinary item claims are preserved.

At startup/restore/Creator reload, old saves without this ledger are reconciled
from retained copies, positive claims or recorded required-item turn-ins.
Offline player evidence is restricted to the current world and game mode. The
database is not queried on each search. Migration does not infer recovery from
a visit, an accepted quest, or an item with ambiguous alternate sources. An old
relic that disappeared without any retained evidence cannot be reconstructed;
all subsequent recoveries are recorded explicitly. The ledger also survives
snapshots of Creator worlds with the living simulation disabled.

## Regression checks

Focused tests cover creation/save/restore, source validation, old-save retention,
knowledge boundaries, rumor/copy provenance, finite staged books, recipe source
requirements, archive filtering, complete speech, emotions and singing.
`tools/probe_npc_expression_layout.py` exercises Talk/Nearby in Qt WebEngine.
`tools/probe_speech_bubble_layout.py` renders the real map at desktop/phone/zoom
sizes and verifies the full final sentence and scrollable long-text ending.
