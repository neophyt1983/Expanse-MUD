# Expanse server and game file 1.9.11 on Render

This update contains three coordinated changes: straighter player click routes, separate linked quests for objectives at different destinations, and usable regional containers. **Install both the server update and the new `.expanse` file.** The server provides generic mechanics and controls; the game file contains every authored quest, reward, container placement, item list, and regional difference.

The new authored file is **Expanse-Wild-Lands-1.9.11.expanse**, with full SHA-256 **efd53b9727167463bc276defb2fabdf1acb077a9179f8709f22ffa5169e7f064**. Keep original imported entries and manual saves. Use the compatibility steps below to continue an existing character in its original entry.

The world splits 583 original quests into linked stages, adding 709 quest records for 2576 total. Every stage has one destination. XP and gold are divided equally and each share is rounded up; zero remains zero. Items, consumption, reputation, flags and world outcomes stay at the original final quest. The new world also adds 2,709 finite containers across 1,726 appropriate places in all eight city-states and their surroundings.

The cumulative code retains the prior movement timing, sprite-color, scrolling, map-input, first/last-name, world-version, and playtest-report repairs. No live Render deployment or live repository comparison was performed while preparing this package.

This repository runs the Expanse Python engine and browser player. The complete `.expanse` file supplies the authored world: its rooms, characters, creatures, quests, books, media and gameplay settings. Render runs the simulation and game clock; the browser displays the world and sends player actions over a WebSocket.

The package is cumulative over the published 1.9.6, 1.9.7, 1.9.8, 1.9.9 or 1.9.10 server. It includes the separate character first/last name fix, correct world-version labels, conversation scrolling repair, compact translucent map tooltips, dependable map-click destinations, world-authored faster travel and the first-quest interface guide. Existing imported entries and manual saves retain their identities. An installation older than 1.9.6 needs the previously supplied 1.9.6 foundation update first; this package does not claim to replace that foundation or independently edited main-line files.

The normal deployment, account setup, play and editing workflows use GitHub, Render and the game in your browser. A terminal is optional.

## Absolute authoring rule

**The engine interprets the game file. The `.expanse` file is the game.**

Authored quests, stories, dialogue, named people and places, NPC placements, regional differences, rewards, encounter settings and balance belong in the world file. The editor must be able to read, change, validate and export that complete content. Development scripts can help author a release, but the exported game must contain their finished records and assets; running those scripts must never be a prerequisite for playing it.

Engine changes provide general mechanics that read world definitions. Browser changes provide controls and presentation. If a new authored feature needs a new capability, add a general data-driven capability and its editor support, then put the actual game content in the `.expanse` file. Do not substitute engine literals or startup-generated release content for an updated game file.


Unless a request names a location or clearly describes a local exception, apply it throughout the world. Local implementation still follows the city-state, facilities, inhabitants and terrain. For example, dressers belong in actual lodgings; outdoor stores use appropriate crates or weatherproof chests.

## Update the existing GitHub repository

1. Download and extract the supplied **server update ZIP** on your computer. The 1.9.11 cumulative update applies to an installed 1.9.6, 1.9.7, 1.9.8, 1.9.9 or 1.9.10 server. Keep the original imported entries, saves and world-update pin. Use the deployment repository linked to your existing Render service, keeping this server project separate from the desktop/main-line project.
2. In that GitHub repository, select the branch Render deploys. At the repository root, choose **Add file → Upload files**.
3. Open the extracted release's **`github-upload`** folder and upload its contents, preserving their paths. For example, `render_server.py` and `private_game.py` go at the repository root; a file supplied as `engine/starter_safety.py` goes inside `engine/`; files under `server/`, `web/` and `editor/` keep those folders. Upload the contents of `github-upload`, without adding that enclosing folder, the ZIP, or the release-name folder to the repository.
4. Review the files GitHub will replace and commit the update. Keep the other existing engine files: an update package supplies replacements and additions to the existing application. GitHub's browser uploader accepts up to **100 files per upload**; split larger uploads into batches while preserving their paths. Finish all batches before deploying. If the branch requires a pull request, merge it before deploying that branch.
5. Open the existing Render service and choose **Manual Deploy → Deploy latest commit**. Keep its existing persistent disk. Wait for **Live**, then refresh the game page. Continue with the 1.9.11 game-file import and update-template steps below; the new quests and containers are authored there.

Source code and browser assets belong in this repository. Import the `.expanse` file through the game website. Enter account passwords only in Render's environment settings; keep saves outside GitHub.

Before a code deployment or any Render environment change that restarts the service, every active tester should use **Save & quit**, wait for the saved-game confirmation, then submit or skip the optional questionnaire. Closing a tab or signing out does not publish a checkpoint.

## Planned maintenance and cumulative updates

Major releases are intended for an eventual weekly maintenance window announced by the owner. No day, time or automatic deployment is configured by this package. Changes can accumulate between deployments; the next package states its supported installed versions and whether a game-file import is required.

Record the installed server build, deployed GitHub commit, world File ID and full update-template SHA separately from downloaded releases. A prepared package is not evidence that the live server has received it. Keep the current and previous packages with their release notes.

To control when GitHub changes go live, set Render's **Settings → Auto-Deploy** to **Off** before committing staged changes. During the announced window, have players Save & quit, deploy the complete chosen code update, import/pin a new world only when its instructions require it, then check login, movement, Conversation, a manual save and a resume before announcing reopening. Include the date, time zone, estimated duration and Save & quit instruction in the notice you send to players.

The release also includes **SERVER-TESTING-AND-FEEDBACK.txt**, a short owner guide to testing comfortable player capacity and retrieving testers' questionnaire notes. These operational notes do not add automatic announcements, scheduled deployments or gameplay autosaving.

## First quest: learn the interface

Each city's first lesson now has its own interface quest at the starting inn. Its completion introduces the separate local travel quest. The Welcome Letter and welcome guides explain the two acceptance steps:

1. In **Conversation**, click or tap **Open quest offers**.
2. In the popup, choose **Accept quest & start guide**. The server confirms acceptance before the walkthrough begins. If acceptance fails, the offer remains available to retry.

The walkthrough explains Conversation, the command line, Actions, Quests, Terrain Map, Quest compass, Location, reading, Inventory, Status, Condition, Panels, Help, Save and Save & quit. **Next** acknowledges the current card; it does not perform that action. **Later** hides the guide; **Actions → Interface guide** resumes it or offers replay. Layout, movement, items and saving remain under the player's control.

Finish the guide and complete that introductory quest at the inn, then follow its named local source to accept the next quest. Each destination has a separate quest entry, clear completion, and its own rounded reward. An older accepted First Bearings retains its acceptance and objective baselines; unfinished guide acknowledgements move to the introductory stage. Legacy characters without a required guide remain exempt. Previously completed quests never reopen or pay again merely because the world was updated.

Guide and chain progress remain live until an explicit **Save** or successful **Save & quit**. The Creator exposes ordered interface cards, ordered chain stages, destinations, readable sources and the original-quest migration snapshot. **World files** preserves the complete authored JSON. Text clients can use `interface guide`, `interface next`, `interface later` and `interface resume`.

## Conversation and map readability

Conversation follows the latest text until the player deliberately scrolls back with the mouse wheel, touch, keyboard or scrollbar. A delayed browser scroll after focus or layout changes no longer turns following off. While reading earlier messages, new replies remain counted by **New messages**; choose that button to return to the latest text. Resizing, maximizing, docking and changing phone panels retain the same conversation and command draft.

Map hover summaries are shorter and use translucent backgrounds. Full descriptions and available actions remain accessible through the existing inspection controls. The changed client scripts and styles use a versioned URL so a cached older asset does not mask the update. After deploying, reload the page; use Ctrl+Shift+R if the previous interface remains visible.

## Map destinations and travel pace

A click or tap retains the room the player pressed even when the map recenters before release. The room atlas uses the same coordinate scale for drawing and input. A newly chosen destination replaces the remaining route after the current server-confirmed step; it does not queue several competing walks. Selecting the location just reached stops the previous onward route. Door and stair buttons verify their original room and passage before acting, so a redraw cannot turn a pressed doorway into a different room's stairs.

The player route planner now chooses the fewest legal steps and, among equally short routes, the path closest to the straight line toward the clicked destination. Arbitrary shallow slopes no longer put all horizontal movement before all diagonal movement. Four-direction maps use a balanced staircase through existing exits. Necessary detours remain, and cross-floor, portal or incompatible wrapped-map routes use deterministic shortest routing without a misleading flat line. This preference applies to both ordinary known destinations and viewport clicks. NPC routing is unchanged.

The server still validates every edge. Locks, missing connections, injuries and unconsciousness stop travel normally. Shift-click inspects, dragging pans, and Stop walking cancels the remaining route. A pending route that cannot be confirmed reports that state instead of remaining silently stuck.

The 1.9.11 world retains `metadata.travel_speed_multiplier: 2`. The generic engine halves travel time between locations, and the client shortens walking intervals and map transitions proportionally. Fractional game minutes accumulate across successful moves, so fast travel still advances the world. Terrain and weather retain their relative costs. The setting is editable through **Creator → World rules → Travel pace**, or the complete metadata file. Unconfigured worlds retain normal speed. This setting does not accelerate the shared real-time clock.

At that pace, some moves accumulate half a game minute and the following move advances a whole minute. That whole-minute step also runs the NPC simulation. The retained server 1.9.10 improvements avoid repeating identical physical route searches within one NPC quest plan, repeat geography checks only when their relevant cache changes, and construct fewer temporary relationship profiles. They also avoid doomed sleeping-NPC conversation attempts and share temporary merchant demographic/workshop lookups within one synchronous transfer phase. Stocks, transaction prices and actor order remain live. It still runs the same simulation and validates each route against current permissions. A paired 31-move replay against 1.9.9 preserved complete gameplay state, messages, random-number state, travel-time fractions and explicit Save/resume results.

The map animates confirmed movement over the existing `95 / travel_speed_multiplier` millisecond walking interval. Closely spaced confirmations carry the unfinished displacement without clipping it to one tile; ordinary moves finish before the next scheduled step. Movement is never predicted through a locked or blocked passage. Local timed JavaScript checks cover rapid turns, reversals, late confirmations, resizing, zoom and reduced motion. These checks do not measure the deployed Render host or the player's network; use the separate server-testing notes to assess actual responsiveness.

## Cities, quest progression and books

All eight cities have comparable authored quest catalogues, now with 304–341 quest records each after destination splitting. Choices and class restrictions make those different from simultaneously available jobs; the compatible branch totals are comparable too. The new local casebooks use existing citizens, workplaces, public reading copies and concrete evidence or crafting tasks. NPCs and books introduce work through the normal discovery and prerequisite rules.

Each starting location has a local introduction to navigation, Quests, cooking, food, rest and explicit saving. The interface lesson, separate navigation quest and local practical lessons lead into work in that city. The separate Iven story remains optional; Hearthmere's introduction correctly describes its school as local. Welcome letters and travel notes provide a readable alternative when a tutor is asleep or absent.

Quest handoffs identify subsequent people, places and relevant reading. Subject-matched notes in fiction and nonfiction can reveal a local lead without replacing the original text. Portable casebooks have complete paper-and-ink copying recipes and public sources for recovering their guidance.

City streets, public building approaches and connected intercity tracks are authored in the world. Maintained urban routes and lower-grade rural surfaces remain distinct, and most open land remains off-road. The existing encounter rules read the road classification. Hollowcrown's bathhouse uses its own editable pool-and-pavilion tile and stone forecourt rather than desert terrain.

Population and essential facilities are balanced by authored resident roles and usable services. Police, military, administrators, teachers, food producers, merchants and other local workers keep their existing identities and schedules when retained. Libraries and scriptoriums support reading and copying, and civilian care and supply services are checked as actual gameplay facilities.

The fresh-world census counts living sentient residents assigned to each city-state, including its surrounding settlements and forces. Population can change during play. Quest totals describe the authored catalogue; class choices and prerequisites determine which requests a character can take.

| City-state | Living residents | Watch | Military | Quest records |
|---|---:|---:|---:|---:|
| Dawnwatch | 384 | 42 | 128 | 335 |
| Hollowcrown | 350 | 40 | 128 | 341 |
| Hearthmere | 350 | 40 | 128 | 328 |
| Reedwater | 350 | 40 | 128 | 304 |
| Cinderhold | 350 | 40 | 128 | 309 |
| Glassreach | 350 | 40 | 128 | 312 |
| Pinewatch | 350 | 40 | 128 | 313 |
| Starfall | 350 | 40 | 128 | 334 |

The retained population update adds 204 finite, named civilian residents and assigns 34 previously unreferenced adult residents to needed local jobs. Existing names and home locations survive those job changes; their authored work descriptions and schedules identify their updated workplaces. New households use existing multi-room dwellings with bounded occupancy and short local commutes. Guards and military are retained at their existing counts.

## Linked quests and rounded rewards

The 583 split original quests now have 1292 individual stages and 583 authored continuation books. Required visits, witness alternatives, reading, crafting, combat and original completion conditions are preserved. Optional supply hints remain optional. NPCs and readable sources disclose eligible stages; completing a stage identifies the next source and quest. Original final IDs keep later quest and recipe unlocks intact.

For a reward of 10 XP and 5 gold split into three quests, each quest pays 4 XP and 2 gold. Across all affected original quests, base gold totals rise from 7,276 to 7,552, and base XP from 16,970 to 17,102; those differences are solely whole-number rounding. Repeat-practice XP for split stages also rounds up, subject to the existing cooldown and daily XP budget. Item rewards, consumed goods, reputation, choices and world effects occur once at the original ending.

For an old accepted quest, accomplished steps are credited in memory and the first unfinished stage becomes active. Rewards for credited steps wait until a subsequent explicit successful turn-in; loading itself grants no gold, XP or items and consumes nothing. The old whole-quest acceptance continues to later unfinished stages without making the player revisit an inserted offer desk. Already completed original quests receive no new reward. A manual checkpoint preserves the migrated state; loading and disconnecting do not publish it.

## Containers throughout the world

The world adds **2,709** finite containers in **1,726** appropriate locations. City-state totals range from 329 to 356, plus outlying facilities and established camps. Bedrooms have dressers and drawers, kitchens have pantry and linen storage, healers have medical cabinets, archives have document drawers, workshops have tools/materials, military facilities have controlled stores, and zoos have keeper supplies. Outdoor locations use suitable covered crates or weatherproof chests.

Open **Location → Containers, locks and locksmiths**. Inspect a fixture or look inside; take a chosen item and quantity, take its movable contents, or put an eligible carried item inside. Locked fixtures require their normal access action. Equipped or fixed items cannot be silently stored. Refreshing the map preserves a transfer being typed, and stale quantities are rejected before an item moves.

2,092 new containers have actual NPC custody and 617 are explicitly shared. Existing witnessed-theft and lock rules apply to private contents. Containers do not refill on restart or content update. All 32 previous lock definitions and their saved state are retained. NPC ownership defines access context; this release does not add autonomous cabinet restocking. Creator room lock/container forms and World files expose the complete placements and finite item lists.

## Level-based creature loot

Creature and monster definitions can author a base `combat_level` and a `loot_table`. A successful common-bundle roll gives money plus one relevant weighted item stack. Bonus gear has its own probability; a failed rare roll is never promoted into guaranteed gear. The complete tables, amounts, levels and item choices are in the game file and editable on NPC records.

The released common tiers are:

| Effective creature level | Common bundle chance | Money in that bundle |
|---|---:|---:|
| 1–3 | 85% | 1–3 |
| 4–7 | 88% | 3–7 |
| 8–15 | 90% | 7–14 |
| 16–100 | 92% | 14–28 |

Effective level is the authored base level plus earned advancement above level 1. This metadata does not secretly change creature combat statistics. Existing carried money and fixed quest drops remain available. Player and NPC contributors share one finite reward pool per death; companion contributions retain their existing caregiver credit. Repeated death resolution cannot roll or award the pool again. Zoo exhibits and owned companions receive no supplemental loot bundle.

## Identify the newest imported world

**World & saves** shows a separate card for each imported file. Numbered versions of the same world appear newest first, with **Newest version** and **Older version** labels. The card always shows a short **File ID** so equal-version variants remain distinguishable. Authored `content_revision` takes precedence over an old version suffix in the title: the released file `c54c05978250` displays **Expanse Wild Lands 1.9.6**, even though its original title ends in 1.9.1. Older files already on the persistent disk receive the corrected display automatically; no re-import is needed.

Newest means the highest recognized world version among the imports in that world family. It is not the engine build, upload order or a promise that a newer release does not exist elsewhere. Custom/unrecognized revisions remain visible without a guessed ranking; if such a sibling exists, the label becomes **Newest numbered version**. Equal highest versions are both labeled, with their File IDs distinguishing them.

To continue an existing character, open the same game file you used before. Changing the visible title or order does not move characters or saves. The shelf describes the imported file; the in-game world selector describes the content currently loaded, which may include a supported compatibility update. Only the owner sees **Update template** on the exact imported file selected by `EXPANSE_UPDATE_WORLD_SHA256`. That badge identifies the configured template, not the update status of any particular saved adventure.

## Render service settings

For an existing service, preserve the linked repository, deployed branch and persistent disk. These are the settings supplied by `render.yaml`:

| Setting | Value |
|---|---|
| Service type / runtime | Web Service / Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `python render_server.py` |
| Health check path | `/healthz` |
| Instances | `1` |
| Supplied service plan | `1c-2g` |
| Persistent disk | `expanse-data`, 1 GB |
| Disk mount path | `/var/data/expanse` |
| `EXPANSE_DATA_DIR` | `/var/data/expanse` |
| Automatic deployment | Off in the supplied Blueprint; deploy manually after all uploads are committed |

Review Render's current price and resource choices before creating or changing a paid service. The simultaneous-game limit below controls how many private game processes may run; it does not add RAM to the service.

### First deployment

1. In Render, choose **New → Blueprint**, choose **GitHub**, and connect the repository containing the complete server application. Grant access to that repository if prompted.
2. Select its deployment branch and leave **Blueprint Path** as `render.yaml`. The Blueprint defines one Python web service named `expanse-private` and its persistent disk.
3. Set `EXPANSE_OWNER_NAME` to your owner login name and `EXPANSE_OWNER_PASSWORD` to a new password of **15–128 characters**. Additional accounts default to an empty list. The owner has no expiration unless you set one. Character names are chosen separately after signing in.
4. Review the service and disk settings, then deploy. Wait for **Live** and open the service's HTTPS `onrender.com` address.
5. Sign in as the owner. Under **Import a game**, select **Expanse-Wild-Lands-1.9.11.expanse**, then choose **Import world**. Select **Play Expanse** beside that imported entry and create a character.
6. Use **Save** for a checkpoint while continuing to play, or **Saves → Create save** for a named checkpoint. Use **Save & quit** to save, end the play session and answer or skip the questionnaire.

The sign-in page is public. Imported game data, play and downloads require a provisioned account. Render supplies HTTPS; the WebSocket uses the same public origin and port. Imported worlds, manual saves, owner drafts and playtest records live on the configured persistent disk.

## Upgrade an existing adventure to 1.9.11

Keep the original imported entry and its saves. A different `.expanse` file has a different storage identity even when it contains the same internal world name. Opening the new entry starts a separate adventure; it does not move an old save into that entry.

For this release, the new world also contains the authored compatibility update used by the engine when loading supported older adventures:

1. Have all testers **Save & quit**. Download the original imported world and your manual saves from **World & saves** as a backup. Each tester can download their own saves.
2. Upload the cumulative server code (1.9.11 in this package) to the linked GitHub repository and deploy that commit on the existing Render service as described above. Preserve the disk and account names.
3. Sign in as the owner and **import Expanse-Wild-Lands-1.9.11.expanse**. Leave the original imported entry in place. The newly imported entry supplies the update template; you do not need to create a new character in it to upgrade an old adventure.
4. After that import succeeds, open the existing Render service's **Environment** page and add or update:

   | Key | Value |
   |---|---|
   | `EXPANSE_UPDATE_WORLD_SHA256` | `efd53b9727167463bc276defb2fabdf1acb077a9179f8709f22ffa5169e7f064` |
   | `EXPANSE_MAX_ACTIVE_GAMES` | `1` for initial playtests on the existing one-CPU service |

   This is the **complete SHA-256 of the released Expanse-Wild-Lands-1.9.11.expanse file**. Paste the whole value, not the filename or the shortened identifier shown on the game shelf. The selected file must already be imported before this setting is enabled.

5. Use the dropdown beside **Save only** and choose **Save and deploy** to activate the new value. This restarts the service, so testers must have saved first. **Save only** stores the change for a later deployment; **Restart service** uses the already-deployed environment values.
6. Sign in again. Continue through **Play Expanse on the original imported entry**, then load your existing character or named save. Use the shortened **File ID** on the shelf to identify that original entry, even when a newer version is listed first. Keep using the original entry for that continuing adventure.
7. Check your character, location, inventory and quests, then use **Save** to checkpoint the updated session. Loading the compatibility update does not silently overwrite the existing checkpoint.

The new content revision is applied atomically only when its authored record guards match the supported prior content. A Creator-edited objective, source, container room, colliding new ID or customized XP configuration causes that revision to remain unapplied, preserving the custom content. A cosmetic world title can remain customized. Use a fresh 1.9.11 import or deliberately reconcile a customized world in the editor; never overwrite it just to force a guard to pass. Shared update assets are pinned by SHA-256, and the exported world stays inside the existing import-size limit.

For a completely new adventure, play the newly imported 1.9.11 entry instead. Importing identical file bytes again reuses the existing entry. Importing a different file normally creates an independent entry; the explicit update-template setting above is the supported bridge for this release, not a general save transfer between arbitrary worlds.

For later code-only fixes, upload their source changes and use **Manual Deploy → Deploy latest commit**. A later authored-content change also requires its `.expanse` file and the matching compatibility instructions. A revised export has a different digest; retain the pin to the released file until a compatible replacement is intentionally selected.

## Create tester accounts in Render

Accounts are provisioned in the existing service's **Environment** page. There is no in-game account-creation step.

Add the key **`EXPANSE_GUESTS_JSON`**. Its value is **JSON text pasted directly into the Render environment value box**. You do not create or upload a JSON file, and this value does not belong in GitHub.

For example, provision the next two testers as `pretzel99` and `pretzel100`:

```json
[
  {
    "name": "pretzel99",
    "password": "REPLACE_WITH_UNIQUE_SECRET_FOR_PRETZEL99"
  },
  {
    "name": "pretzel100",
    "password": "REPLACE_WITH_UNIQUE_SECRET_FOR_PRETZEL100",
    "expires_at": "2027-12-31T23:59:59Z"
  }
]
```

Replace both placeholder passwords with unique passwords of **15–128 characters** before saving. Keep the JSON quotes and commas. Add further `pretzel<number>` records to the same array, retaining the records for accounts that should continue to have access.

`expires_at` is optional. Omit it for ongoing access, or supply an ISO timestamp with `Z` or an explicit UTC offset. For the owner, the equivalent optional variable is `EXPANSE_OWNER_EXPIRES_AT`. Login names must be unique after normalization and case folding; keep an existing tester's login name stable to preserve the account's save identity.

The account name, such as `pretzel99`, identifies the login and its private saves. In **Create a character**, choose the character's own first name and optional last name. The supported name characters are letters, digits, spaces, hyphens, apostrophes and underscores; the combined normalized name is limited to 61 characters. Each nonempty name field must contain a letter. Separate accounts may use the same character name because their adventures and saves are isolated. Existing characters retain their current names and IDs. Creating another character does not rename an existing one, and creation remains unsaved until the player explicitly saves.

Choose **Save and deploy** from the Render save dropdown to activate the environment changes. All testers must Save & quit first. A service restart clears browser sign-ins, so everyone signs in again using their own name and password. A sign-in lasts at most 12 hours and never beyond the account's expiration; a new sign-in for the same account replaces that account's previous browser session. Removing or expiring an account does not delete its manual saves.

### Simultaneous private games

`EXPANSE_MAX_ACTIVE_GAMES` is optional. The default is **`2`**; accepted values are integers from **`1` through `8`**.

Each active account/world runs in its own private process and uses its own save directory. Two testers can play at the same time without sharing characters, world changes or checkpoints. These are **independent single-player adventures**, not a shared MMO world. One play tab is supported per account/world.

When all configured slots are occupied, another tester receives a capacity message. The service does not disconnect an active player to make room. Players should finish with **Save & quit** and submit or skip the questionnaire so that their slot is released. An ordinary tab close retains an unsaved running adventure for reconnection and can keep a slot occupied. Signing out ends that account's running workers without adding a checkpoint.

Raise the limit only after checking the service's memory and performance with the intended world and number of testers. The accepted maximum is a configuration bound, not a guarantee that the selected Render plan can run eight large worlds.

### Measured capacity and the initial test limit

For the existing **1-CPU / 2-GB service**, set **`EXPANSE_MAX_ACTIVE_GAMES=1`** for the first invited playtests. This is a conservative recommendation from the measurements below, not a measured single-player latency guarantee. The code default remains 2, so enter 1 explicitly in Render if you follow this recommendation. Add it alongside the world-update setting, then use **Save and deploy** once players have saved.

The prior 1.9.8 local diagnostic ran two complete private worlds on the same CPU, sending one `Look` command to each player every two seconds for 30 seconds. Both worlds saved, reloaded the same character and location, and kept accounts and checkpoints separate. No checkpoint was written before the explicit Save.

| Prior 1.9.8 diagnostic | Median command delay, player 1 / player 2 | Longest observed delay |
|---|---|---:|
| Normal authored start, no clock jump | 0.0043 / 0.0043 seconds | 5.94 seconds |
| Artificial advance to daytime before play | 0.187 / 0.185 seconds | 10.33 seconds |

The normal run's **median combined active-process memory was about 730 MiB**. It peaked at **808 MiB during play** and reached **1,390 MiB across loading, saving and reloading**. These figures exclude Render's proxy and operating-system overhead. Route planning and visible-description work were optimized without reducing the authored population or changing game outcomes in the paired checks, but initial NPC updates can still delay player commands.

These prior-release measurements support an **invited private playtest with a known responsiveness limit**. They are historical 1.9.8 measurements, not a current-build latency guarantee. They do not establish consistently smooth two-player capacity, shared-world multiplayer readiness, or a public-launch load limit. The tests were local, used `Look` only, and did not measure network delay, browser rendering, combat, travel or long-lived population growth. Server 1.9.10 supplied historical movement checks, and 1.9.11 adds route correctness checks. Local timing still does not establish a comfortable live-player count. Try a limit of 2 only as a deliberate live test after the first sessions; do not infer that the accepted maximum of 8 is suitable for this plan. Use the package's **SERVER-TESTING-AND-FEEDBACK.txt** to record a staged test on the actual server and collect players' observations.

## Owner editing: draft, validate and export

From **World & saves**, the owner can choose **Edit a draft** beside an imported world. The editor opens a separate persistent draft. Testers do not have editor access, and editing the draft does not modify a running player's session or saved game.

To edit the complete 1.9.11 content, create that draft from the **new 1.9.11 imported entry**. An older imported entry remains the original source file even when its running adventure receives a supported compatibility update.

1. Use the structured Creator tools for records such as rooms, NPCs, items and quests. Use **World files** to inspect and edit the world's authored JSON, including world settings, and to upload, replace or download supported media.
2. Save your changes explicitly with **Save draft** or the relevant world-file save control. Text left unsaved in a form is not a saved draft. There is no gameplay autosave as a consequence of editing.
3. Choose **Validate** and resolve reported errors before distributing the world.
4. Choose **Export .expanse**. The browser downloads the complete portable world, including its authored JSON and media; a server filesystem path is not required.
5. Return to **World & saves** and import the exported file to add that playable version. A changed export gets a separate entry and save storage. Updating an existing adventure requires an authored compatible update and the deliberate template selection described above.

World content and gameplay settings belong in the `.expanse` file. The Python engine supplies the mechanics. Keep the exported world as the portable deliverable for authored changes, including encounters, city inhabitants and defenses, institutions, creatures, quests and publications.

## Playtest feedback and owner reports

During play, a short notice explains that the service collects semantic actions, places visited, active-time estimates, injuries and recognized errors. It does not collect raw command arguments, conversation transcripts, passwords or authentication tokens in playtest records.

**Save & quit waits for a successful server checkpoint acknowledgement before ending the socket session.** When playtest collection is available, the confirmation opens **Game saved — session feedback**. If collection is unavailable, the client leaves after the successful Save without offering the questionnaire. If Save fails, the session stays open and the questionnaire does not appear. If the acknowledgement is lost, **Check save status** checks that request; it does not automatically send a second Save.

The optional questionnaire asks for enjoyment, clarity and difficulty ratings, what the player liked or disliked, places avoided, reasons for avoiding them and the next intended goal. Players can send feedback, retry after a feedback error, or skip it. A feedback error does not undo the successful gameplay save. The explicit unsaved `quit`/`leave_no_save` commands do not claim that a checkpoint was saved and do not open the saved-session questionnaire.

The owner can open **Playtest reports** from the shelf, or visit **`/playtest`** on the same service. **`/api/playtest/report`** provides the structured report. These routes require the signed-in owner; a tester can submit feedback only for their own saved session.

Reports show actual room changes, visit counts, estimated active and idle time, injuries, deaths, recognized failed actions and interactions with authored sentient NPCs, creatures and monsters. Active time is an estimate from server actions and visible-tab activity, not proof of attention; long unobserved gaps are kept separate. Possible caution or friction appears as an interpretation to review. Unvisited places are not automatically labeled avoided, and the player's direct avoided-place answers remain separate from those interpretations.

The owner report includes the newest **200 eligible sessions**, updated within **30 days**, from currently configured accounts and currently imported worlds. Storage is bounded to **100 sessions per account/world**, **1,500 recent events per session**, **300 detailed places** and **160 interaction targets** per session; retention pruning runs as the private analytics store is opened or new sessions are created. Export the report after each trial and before removing accounts or retention expires. Gameplay checkpoints remain separate. Analytics may be written during play, but it never makes a gameplay Save on the player's behalf. The manual-save download contains gameplay checkpoints, not the analytics database.

## Back up and restore

From **World & saves**, download the **imported world** and **your manual saves**. The world download is the original `.expanse` file for that entry. The save ZIP contains native SQLite and world-state checkpoint files for your account and that imported identity. A save download appears after a manual checkpoint. Finish with Save & quit before downloading.

For an adventure upgraded through a pinned update template, keep both its original imported world and the selected update `.expanse` file with your backups. The original identifies the saved adventure; the update supplies the additional authored content needed to run that updated adventure with the matching engine.

The following restore commands are optional maintenance workflows. Ordinary hosted play, deployment and world import do not require them.

For local Bazzite use, import the same original game file into a compatible Expanse installation and install the matching update template when applicable. Quit the game. Restore into an empty save directory for a separate installation, or move the existing save directory aside using your normal backup procedure. From the deployment source checkout run:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/original-game.expanse --save-dir /path/to/separate-expanse-install/save
```

For self-hosting this web engine, sign in and import the original `.expanse` first, plus the selected update file when applicable. Stop the web service and restore into an unused account/game save directory:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/original-game.expanse --web-data /path/to/web-data --account "pretzel99"
```

The `--account` value is the Render login name that owns the saves. It may differ from every character's name in the archive. The older `--character` option remains a compatible alias for this same login-account value. The helper verifies the exact original world file, checks SQLite integrity and refuses to replace a nonempty save directory. Restore the matching engine and update-template configuration as well; the helper does not select that template for you.

## Verify the deployed service

After deploying, sign in, enter the intended world entry and check the character's location, inventory and quests. Make a manual checkpoint. Use Save & quit and complete or skip the form, then reopen that same entry and load the checkpoint. Repeat after a Render service restart to verify that the deployed disk retains the imported worlds and saves. With two provisioned testers, check that they can play independently and that neither can open the owner editor or reports.

Local checks cover checkpoint ordering and failure handling, save identity, private-worker isolation and capacity, account authorization, owner drafts, feedback and report access. Verify production HTTPS/WebSockets, disk mounting, sustained resource use and physical-device layout on the live Render service. Structural client checks do not replace a rendered mobile-browser test.

### Optional local smoke test

Python 3.12 and the dependencies in `requirements.txt` are sufficient for this server. Run these commands from the repository directory on Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export EXPANSE_PUBLIC_URL=http://127.0.0.1:10000 PORT=10000
export EXPANSE_DATA_DIR="$PWD/data"
read -r -p "Private character name: " EXPANSE_OWNER_NAME
read -r -s -p "Private password: " EXPANSE_OWNER_PASSWORD
echo
export EXPANSE_OWNER_NAME EXPANSE_OWNER_PASSWORD
python render_server.py
```

Visit **http://127.0.0.1:10000**. On Render, the server binds to `0.0.0.0:$PORT`, uses the Render-provided public URL and requires the configured persistent disk mount. The health endpoint is `/healthz`. Private game processes use authenticated loopback connections. Application access logging is disabled; Render has its own platform and service logs.

Render references: [Blueprints](https://render.com/docs/infrastructure-as-code), [persistent disks](https://render.com/docs/disks), [WebSockets](https://render.com/docs/websocket), [current pricing](https://render.com/pricing).
