# Local populated-world profile — 19 November 2026

## What was measured

The original measurements below use the supplied **Expanse Wild Lands 1.9.16** directory
as read-only input and the current feature working tree. A separate measurement
uses the composed review world with the new content enabled. They instantiate the
real `GameServer(mode='single')`, with a temporary database, save directory,
world-state path and games root. They do not launch a network server, load a
user save, modify the input world, or touch Render.

This initialization produces **35,733 runtime rooms and 5,205 entities**. A
simpler `build_world` + `spawn_npcs` benchmark produced only 2,555 entities and
was discarded as a comparison for the real server. `GameServer` also installs
streets, initializes settlements/population and calls frontier population.

The script uses Python 3.12.14 and a fixed random seed of 119. It measures constructor wall
time, then one-minute living ticks. A separate cProfile tick is explicitly
identified so instrumentation overhead is never presented as ordinary latency.
The process peak resident set comes from `resource.getrusage`; it includes the
loaded world and profiler overhead, not a live deployment's total memory.

```bash
python tools/profile_populated_world.py \
  --world /path/to/read-only/world-1.9.16 \
  --ticks 3 \
  --profile-path /tmp/server-warm.prof

python tools/profile_populated_world.py \
  --world /path/to/read-only/world-1.9.16 \
  --ticks 3 --profile-first \
  --profile-path /tmp/server-cold.prof
```

The default profiles tick 4 after timing ticks 1–3 without profiling. The second
command profiles the first tick and then times ticks 2–4. The clock starts at
world minute 375 in this input.

## Results and limits

The workspace was shared with other development and browser-verification
processes. Constructor times varied markedly, and the unprofiled end-to-end
measurements do **not** establish a production speed-up.

| Real server run | Constructor | Tick1 | Tick2 | Tick3 | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before the contact-appearance change | 4.019s | 2.150s | 1.019s | 0.306s | 345.89MiB |
| After the contact-appearance change | 4.856s | 2.478s | 1.055s | 0.302s | 345.91MiB |

The first ticks do real cold initialization, establish relationships, process
scheduled production/social work and populate caches. They are not comparable
to a later warm tick as if the difference were a code optimization. A separate
warm profiled tick was 1.287s before and 1.390s after, with the same 2,639,793 calls.
The targeted contact work was not scheduled on that warm tick.

### Cold-tick attribution

The pre-change first tick made 11,229,473 function calls and took 6.651s under
cProfile. Cumulative totals overlap, so the rows below must not be added.

| Path | Calls | Cumulative profiled time |
| --- | ---: | ---: |
| `livelihoods.routine` | 2,870 | 1.674s |
| `relationships.advance` | 1 | 1.317s |
| `town_talk.meet` | 1,295 | 1.176s |
| `town_talk.visible_feature` | 2,590 | 1.138s |
| Full equipment generation within contact looks | 2,590 | 0.672s |
| `social.advance` | 1 | 0.812s |
| `settlements.advance` | 1 | 0.759s |
| `animal_life.step` | 10,410 | 0.561s |
| `needs_market.advance` | 1 | 0.394s |

The warm profile's largest paths were needs processing, animal processing,
regional encounters and ordinary livelihoods. The observer selection pass
already uses actual awake local travelers and a bounded encounter budget;
removing its permission/visibility checks would change game behavior.

## Implemented safe optimization

Contact memories store a visible garment description, usually the first
equipped body layer. Previously `town_talk.visible_feature` built the full
equipment sprite packet for every observed character, even when the first
garment already determined the final text. This meant parsing unrelated boots,
weapons and other equipment thousands of times in a social burst.

`visual_mapping._equipment_rows` now yields the same ordered rows lazily.
`_player_equipment` still returns the complete list for map/UI consumers.
`visible_feature` stops after the exact same first body garment; when there is
no body garment it consumes the whole sequence and uses the original generated
workwear/hair fallback. There is no persistent cache and no stale appearance
state to invalidate.

| Same cold-tick contact workload | Before | After |
| --- | ---: | ---: |
| Contact meetings | 1,295 | 1,295 |
| Contact lookups | 2,590 | 2,590 |
| `visible_feature` cumulative time | 1.138s | 0.608s |
| Equipment rendering cumulative time | 0.672s | 0.155s |
| Total cold-tick function calls | 11,229,473 | 10,318,664 |
| Total cold-tick cProfile time | 6.651s | 6.163s |

The targeted contact-look work was about 47% lower in this profile and removed
about 0.91 million calls from the cold tick. The wall-time table above is included
to make clear that this is evidence of reduced work in one path, not a claim
that every game tick or Render response is 47% faster.

Three focused differential tests cover the exact former full-packet label,
authored and legacy garments, shields, missing item definitions, unusual slots,
generated workwear, unchanged full packets and immediate appearance edits.
They also verify that unrelated later equipment is not read once the visible
body garment has been found.

```bash
python -m unittest discover -s tests -p 'test_conversation_appearance.py' -v
```

## New-service scaling and follow-up

On the original input, guild/art/clinical content is not yet opted in. Its
2,870 clinical checks cost about 9ms in the profiled cold tick; the empty art
clock hook took less than 0.1ms. These measurements are only the opt-out cost,
not a performance claim for enabled content.

The new routines are deliberately scoped: clinical care examines people in
the actual room; artistic advancement iterates active projects; NPC guild/art
executors run only for explicit plans and use bounded remembered routes and
genuine local sources. They do not add a catalog-wide target search for each
resident. Source-text recognition still checks catalog labels when an actual
read or conversation happens; its measured cost is detailed below.

The profile also identified **two animal passes per tick**: the main living
loop and `wildlife.advance → animal_life.advance` each invoked the routine for
5,205 entities. In the warm profile these 10,410 calls used 0.266s of 1.287s,
including repeated species/configuration checks for sentient residents. This
was handed to the animal-system owner for a scheduler-safe fix and independent
regressions; this document's before/after contact comparison predates that
change.

Further work should prioritize measured cold social/occupational bursts and
the duplicate animal work. It should retain actual stock transfers, local
knowledge, permission checks, finite encounter budgets and authoritative game
time. These local measurements do not establish Render request latency,
network behavior, concurrency limits or hosting-instance capacity.

## Composed review world with content enabled

The staged input is `Expanse-Wild-Lands-1.9.16-review`, manifest slug
`expanse-wild-lands-review-20261119`, schema 8, explicitly marked
`review_only: true`. Its manifest contains 32,426 source rooms, 259 buildings,
3,782 NPC definitions, 5,128 item definitions, 2,650 quests and 24 groups. The
recipe catalog contains 4,026 records. This is a separate copied world; the
original input remains untouched.

Its `content_patches` metadata includes version 1 of `task_guilds_clinics_v1`,
`artistic_work_v1`, `market_employment_v1` and `review_20261119`. The version-1
`bounded_knowledge_literature_v1` patch records 51 initial books, 23 works and
2,860 newly initialized founders. The review metadata states
`live_imported: false`.

```bash
python tools/profile_populated_world.py \
  --world /path/to/Expanse-Wild-Lands-1.9.16-review \
  --ticks 3 --profile-first \
  --profile-path /tmp/server-enabled-cold.prof
```

Both runs used the same seed and isolation method after desktop probes
had ended. They include both the appearance optimization and the animal owner's
duplicate-pass fix, so it is **not** a controlled one-change comparison against
the original world. The runtime contained **35,741 rooms and 5,207 entities**;
the entity count stayed constant through minute 379.

| Measurement | Before source-loop change | After source-loop change |
| --- | ---: | ---: |
| Constructor wall time | 8.382s | 4.654s |
| Unprofiled tick 2 | 1.347s | 1.286s |
| Unprofiled tick 3 | 0.353s | 0.333s |
| Unprofiled tick 4 | 0.355s | 0.287s |
| Process peak RSS | 363.63MiB | 364.05MiB |
| Profiled cold tick 1 | 9.163s | 6.215s |
| Cold-tick function calls | 12,656,524 | 10,886,678 |

The profile verifies that these enabled NPC hooks were actually invoked. It does
not establish that every staged quest, commission or clinical course completed
during the four-minute observation window.

| Enabled cold-tick path | Calls before / after | Before cumulative | After cumulative |
| --- | ---: | ---: | ---: |
| Genuine guild/art source acquisition | 6 / 6 | 1.740s | 0.422s |
| `knowledge.from_text` within those operations | 6 / 6 | 1.726s | 0.411s |
| Opted artistic NPC step | 4 / 4 | 0.895s | 0.223s |
| Opted guild NPC step | 2 / 2 | 0.847s | 0.200s |
| Animal step | 5,207 / 5,207 | 0.539s | 0.456s |
| Animal keeper step | 2,872 / 2,872 | 0.231s | 0.192s |
| Clinical local step | 2,872 / 2,872 | 0.014s | 0.010s |
| Active employment lookup | 5,161 / 5,166 | 0.018s | 0.014s |

These cumulative times overlap. Source acquisition initially dominated the enabled
guild/art cost: five actual local conversations and one actual reading used
`knowledge.from_text`, whose former two catalog passes recognize exact IDs and unique
names. This is a concrete scaling concern even with only six opted workers;
it must not be described as negligible opt-in overhead. The source processing
preserves qualified mentions and genuine disclosure, so an optimization must
retain those boundaries and duplicate-name behavior.

A follow-up changes only the recognition loop in `knowledge.from_text`. It
walks each catalog once and counts duplicate names only when their case-folded
form occurs in the actual source text. Candidate matches retain catalog order;
the existing exact-ID, whole-name, minimum-length and uniqueness rules still
decide disclosure. The later provenance and qualified-mention logic is
unchanged. No persistent index or cache is introduced, so edits, renames and
new ambiguous names are reflected on the next real read or conversation.

Three differential tests compare the former matching rule across punctuation,
case, overlapping IDs, short names, Unicode and duplicate labels; verify one
catalog walk and immediate live edits; and retain the boundary between explicit
room/recipe grants and merely rumored names.

```bash
python -m unittest discover -s tests -p 'test_knowledge_text_matching.py' -v
```

In the final repeat, the same six source-processing calls took 0.411s rather
than 1.726s under cProfile, about 76% less cumulative time for that function in
this pair. The full cold tick made about 1.77 million fewer calls. Unrelated
paths also ran faster and constructor time changed substantially, so neither
the whole-tick reduction nor the constructor difference can be attributed
solely to this optimization. The reliable structural change is one catalog
walk per source instead of two, with allocation and matching work restricted
to candidate mentions.

The final affected regression run passed 44 tests across source recognition,
knowledge boundaries, genuine NPC guild execution, artistic work, authenticated
work/care transport and conversation appearance. No further profiles were run.

The animal step count is now one pass per initial entity rather than two. Its
time includes newly enabled animal behavior, making it unsuitable as a direct
timing comparison to the original opt-out input. Ordinary livelihoods,
relationships, settlement work and needs processing remain other major cold
paths.

## Input identity

The source Git checkpoint was `b84b2c4`, with the shared feature working tree
applied. Source input SHA-256 values:

| Input | SHA-256 |
| --- | --- |
| metadata.json | `1b70a3c952092a121dff783d37d044d4dac72c5c7343e346ae6ac865eea3afcc` |
| rooms.json | `79bf0fd0bb1942a0ca97ae4cf3f284d1e17d75f5f35177666472733a4d447c07` |
| npcs.json | `ca04d5292073d09137b0352e362fd4e65b7d88b0071251490ec94dca8d2e6e62` |

Composed review input SHA-256 values:

| Input | SHA-256 |
| --- | --- |
| manifest.json | `5784367eb6a3f035f3bf144b48d03e82f4c265b92c1160d3b838ae6df50afe6c` |
| metadata.json | `5532ad19d48b66ddbd24bbb9c935ceeffb292e19a2d0b74fc67488fe8b1486d6` |
| rooms.json | `6bd723091333b8af52baa6694df87a50dc85855dac495c35d453b793f94f3161` |
| npcs.json | `8e2266feb95f1249766cf768b3ce6fa64badce2c9513fd3a214facb3a2363a45` |
| items.json | `c2a26b41044ecf5a5b58ddd88cafee94b5c98850eb3b1a0287cf9a8a5c71b456` |
| recipes.json | `1ac90fb05e6b5c967602a3d28ed1a7994c72c779632b94b88df6aff7c74614e0` |
| quests.json | `498c6c9f8271b4e1d5678e2720c1a739175d99386fff67a09be78406617d2e96` |
| groups.json | `de23254201f44662e7c4aa30c7677ba31c15478e35469b9c47deee9768a547e0` |
| buildings.json | `dbfcea87ef57070231178ec2382c299b7e7a587a8e80c838775efa4bc0c8a368` |
