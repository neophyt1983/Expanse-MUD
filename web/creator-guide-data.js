window.ExpanseCreatorGuideData=[
  {
    "id": "overview",
    "title": "Start here: build safely",
    "paragraphs": [
      "This handbook describes the Creator tools present in the contribution/tax release (v13), with a clearly labeled note for newer fresh-clock controls. It is a reference, not a script: the guide itself never edits your world, runs an example, charges anyone, generates residents or advances time. Normal field-finish handlers may still stage a field when focus leaves it.",
      "Use a separate practice world for your first changes. Keep a known-good whole-world export and a separate game save. A world definition, an active adventure/save, a local editor draft and a Pixel Studio draft are different things.",
      "First exercise: create a starter world; select Rooms; change a room description; finish editing the field; Save; Validate; then deliberately Run that world. Walk through your change, save the adventure and reopen it. Only then expand the design.",
      "Use the topic list or Find guide text. Examples use fictional IDs that you must create or replace with IDs in your own world. Follow validation errors instead of forcing an example onto unrelated content."
    ]
  },
  {
    "id": "create",
    "title": "Create or choose a world",
    "paragraphs": [
      "Open Creator, then choose a game in the Library. + New Game asks for a unique slug (lowercase letters, digits and underscores, beginning with a letter), a display name and starter content. In this prompt OK means the starter village; Cancel means a blank world, not cancellation of the earlier name prompts.",
      "The starter template includes Village Square, an inn, a cellar with a giant rat, bread and a blade. Blank starts with one empty starting room. These are not copies of the entire Expanse campaign. Use a separate export/import workflow or World history when you need to preserve an existing authored template.",
      "Example: choose slug my_first_valley and display name My First Valley. Start with the village template. Do not reuse a live world slug to experiment. Select your new game before making any records.",
      "In newer startup interfaces, New Adventure and Continue choose a fresh adventure versus existing save state. They are not a substitute for creating or editing the underlying world definition."
    ]
  },
  {
    "id": "workflow",
    "title": "Stage, Save, Validate, Apply and Revert",
    "paragraphs": [
      "Many Inspector controls stage their changes when you finish the field or leave it. Some structured or JSON controls have a dedicated save/stage button. A staged field is not necessarily written to disk. Watch the status line and fix rejected values before navigating.",
      "The main Creator Save writes staged content. Validate checks the selected world and reports missing references and invalid values. Apply to running game explicitly refreshes the active world. If you selected another world, the toolbar offers Run that world instead; this can move connected players into that world.",
      "Revert asks to discard unsaved Creator changes. It is not an undo for changes already saved or applied. Duplicate makes a new record under a new ID. Delete removes the selected definition; check references from rooms, recipes, quests and other definitions before saving.",
      "The game’s Save command checkpoints the adventure. It is not the Pixel Studio save button. Tax plans, geological settings and weather settings have separate saves; population stages ordinary Editor records; World history creates a different world. Their chapters explain the differences.",
      "If a save or validation fails, keep the original draft and read the error. Do not repeatedly Apply, force an import, or delete referenced data to make the warning disappear."
    ]
  },
  {
    "id": "search",
    "title": "Find headings, entries and Inspector fields",
    "paragraphs": [
      "Find content headings narrows categories such as Rooms, NPCs or Quests. Find entries by name or ID searches the selected type; switch Entry search scope to All types in this world to search already-loaded records across the selected world. Results show both a readable name and stable ID.",
      "Lists show at most 100 entries per page. Previous entries and Next entries move through matches. The result count and selected-entry reminder remain visible even when a filter excludes the selected record. A query changes what you see, not the world.",
      "Find within selected Inspector matches field labels and current values, including nested controls and selected choices. It does not search every unused option in a reference dropdown. Nonmatching field groups are hidden, not recreated, so local text and widget state survive filtering.",
      "Clear the search, or press Escape inside it, to restore the full list or Inspector. Tab reaches search boxes and results; Enter activates a focused result. Failed or unfinished edits can block changing selection: correct/stage the field or explicitly Revert rather than losing it."
    ]
  },
  {
    "id": "rooms",
    "title": "Rooms: a two-room exercise",
    "paragraphs": [
      "A room is a playable location. Its ID is a stable reference; name and description explain it to players. Exits reference other room IDs. An exit is not implied by rooms being adjacent on the map.",
      "Example: create Rooms valley_inn and valley_garden. Give them names Valley Inn and Kitchen Garden. Set valley_inn’s east exit to valley_garden and valley_garden’s west exit to valley_inn. Save and Validate. Run the practice world and verify both directions, not just one.",
      "Use facilities, resources, encounters, campable, environment, services and other room controls for actual mechanics. A description saying “you can rest here” does not itself add an inn facility; drawing a river does not create a fishing source.",
      "Use readable descriptions to explain visible actions and restrictions. If you add gates or requirements, give the player a discoverable clue and an alternative way to obtain what is required."
    ]
  },
  {
    "id": "maps",
    "title": "World Map, coordinates and terrain",
    "paragraphs": [
      "Room map_x/map_y/map_z describe layout: east is positive X, south is positive Y, and Z is a layout level. The optional World position fields use east-positive X and north-positive Y. These are distinct coordinate systems; neither is a latitude/longitude/altitude editor.",
      "To place a world position, fill both coordinates and use Stage world position, then the normal Save/Apply workflow. Clear world position removes the saved coordinates. A single missing coordinate is invalid. Setting coordinates alone does not add exits, move a coastline or generate terrain.",
      "Refresh preview redraws the selected world map; it is not Apply. Auto-place unmapped rooms stages layout coordinates for rooms missing integer map coordinates and leaves already mapped rooms alone. Save those staged coordinates when satisfied. Open complete host atlas is a creator/host view, not a way to reveal unexplored locations to ordinary players.",
      "World Map selects and inspects authored rooms. Use actual exit links and terrain rules to make movement work. Visual adjacency, a map symbol or a custom tile does not make a route passable.",
      "The shipped atlas/local map and the separate planetary globe work are not interchangeable promises. This guide does not claim a new spherical globe, automatic geographic simulation or fully generated continents are installed. Test the actual map offered by your build."
    ]
  },
  {
    "id": "buildings",
    "title": "Buildings and believable interiors",
    "paragraphs": [
      "Buildings group explicit room IDs. Add the interior rooms first, then include them in the building’s rooms list. Define ordinary horizontal exits between rooms and stairs/up/down only where appropriate.",
      "Example: create inn_common, inn_kitchen and inn_bedroom. Connect common room east to kitchen and north to bedroom, with return exits. Describe doors, furnishings and purpose. Add all three to the inn building.",
      "The room list does not automatically generate a floor plan, add doors or convert an exterior tile into an interior. Ensure the outside entrance and interior exit are linked, then walk the complete route in a test adventure."
    ]
  },
  {
    "id": "items",
    "title": "Items, equipment and ammunition",
    "paragraphs": [
      "Items define usable objects: type, value, description and the relevant equipment/tool/consumable fields. Equipment uses a slot and appropriate bonuses. A picture alone does not grant armor, weapon damage, ammunition or a recipe.",
      "Example: duplicate an existing compatible bow into practice_bow, change its name and description, retain its supported weapon slot and ammunition reference, then validate. If creating ammunition, ensure the referenced item exists and a shop, resource or recipe actually supplies it.",
      "Use the location/placement controls to place an item or give it through an appropriate inventory, stock, recipe or reward. Merely creating an item definition does not put one in a player’s pack.",
      "Use Pixel Studio for registered equipment appearance after the item works mechanically. Identical item copies may share definition-based condition rather than independent per-copy serial state; do not promise unique wear history for every duplicate."
    ]
  },
  {
    "id": "npcs",
    "title": "NPCs, schedules, shops and companions",
    "paragraphs": [
      "Create the NPC definition, select a real location or appropriate spawner, and set its role, disposition, dialogue and relevant inventory/stock. Test that the NPC appears at the expected time. A shop description is not saleable stock.",
      "Schedules use Expanse hours 0–24, minutes 0–59 and weekdays 1–9. Give workers compatible home, work and leisure locations and travel opportunities. Use staggered hours for availability rather than making every NPC work continuously.",
      "Example: duplicate a working merchant, choose a saved shop room, add an existing item to its stock with quantity and price, and test while the merchant is working. Also test off-duty behavior, faction refusal, insufficient funds and selling a suitable item.",
      "For a tameable NPC, configure the supported tameable/food/companion fields and a reachable source for the food. A quest or readable guide should explain the requirements. Do not create a companion that can only be acquired by knowing an undocumented ID.",
      "Social, needs, life and health data describe simulation state, not player-visible omniscience. Players should learn through observable behavior and dialogue rather than being shown private numeric motives."
    ]
  },
  {
    "id": "factions",
    "title": "Factions, relationships and law",
    "paragraphs": [
      "Faction records include membership/relationships and related settings. Player standing toward a faction and a relationship between two factions are different relationships. Inspect the relevant field before changing it.",
      "Use explicit bounds and locks where supported. A hostile relationship should not leave all players without any way to obtain basic supplies or improve standing. Test a neutral or disliked character as well as a favored one.",
      "Room law/authority/arrest settings reference actual factions and rooms. A written law in a description is not an automatically enforced rule. Tax-plan exemptions and collection notes are also not executable law.",
      "World history can generate bounded relationships into a new world, and optional live diplomacy adjusts configured goodwill. It does not create a complete military campaign or automatically conquer territory."
    ]
  },
  {
    "id": "quests",
    "title": "Quests, prerequisites and rewards",
    "paragraphs": [
      "Choose Quests and create or duplicate a small working quest. Give it a clear name and description, an offer location, completion location and supported goals such as visit_rooms, required_items, talk_to, kills or actions. Every referenced ID must exist.",
      "Example: make a garden visit quest offered and completed at valley_inn, with valley_garden in visit_rooms and a modest reward_gold. Describe how to reach the garden and where to return. Save/Validate and test accepting, making the visit and completing it.",
      "prerequisites are other quest IDs that must already be completed. exclusive_with prevents incompatible choices; character flags and other requirements can add conditions. Avoid cycles or requirements that no available quest can satisfy.",
      "For several destinations, author one quest per destination. In quest_chain, enable Quest stages and enter the same ordered stage IDs on every quest, ending with the final quest ID. Choose that final ID as the chain ID. The editor computes this quest’s stage index from its position in the list. Select its destination, and use the same room in turn_in_room. Keep the original published quest ID on the final stage so existing references remain meaningful.",
      "Put the preceding quest ID in each later stage’s prerequisites. At the preceding destination, provide an NPC offer or an anchored, readable continuation book whose knowledge.quests includes the next stage. Select that book in source_item when used. Give each stage a clear account of where to go and how to continue. Verify that later stages remain unavailable until their prerequisites are complete.",
      "When splitting an existing quest into N stages, give every stage ceil(original reward_gold / N) gold and ceil(original reward_xp / N) XP. Zero stays zero; if XP originally came from World rules, resolve that amount before splitting. Edit the stage rewards explicitly. Keep original item rewards, reputation, flags and other completion effects on the final stage so they are awarded once.",
      "On a converted final quest, quest_split_migration preserves the complete original quest for existing saves. Keep its version, revision, original snapshot and any resolved reward values. Avoid changing or removing this snapshot casually: it protects characters who already accepted or completed the older quest. The advanced field and World files can edit this metadata; opening the editor or saving quest_chain never rewrites it.",
      "Save quest chain stages only the selected quest’s chain field. Save draft and Validate the whole chain after updating its quests, prerequisites and sources, then export the complete .expanse file. World files preserves complete authored JSON, including fields not represented by a specialized control. Import an exported copy and test both a fresh character and an existing saved character before publishing.",
      "Item goals require an obtainable source, not just an item definition. Rewards must be affordable for your balance and refer to real item IDs. Test fresh players with little money, no ammunition and low faction standing. Do not assume the presence of a quest record automatically adds a particular NPC source button in every version."
    ]
  },
  {
    "id": "recipes",
    "title": "Recipes and crafting stations",
    "paragraphs": [
      "Recipes reference existing ingredient and output items, quantities, a supported station, kind and duration. Use a working recipe as a pattern rather than inventing a station label.",
      "Example: duplicate a simple hand recipe into practice_bundle. Use two units of a reachable material as ingredients and one practice item as output. Ensure the material can actually be gathered or bought, then test crafting with and without enough ingredients.",
      "If a recipe needs a forge or kitchen, place the required facility in a reachable room and explain the location to players. The word “forge” in room prose is not sufficient by itself.",
      "Workshops, staffing, stock and production are related but separate from a player recipe. Do not promise unlimited stock or production without present workers and input materials."
    ]
  },
  {
    "id": "resources",
    "title": "Resources, encounters and ecology",
    "paragraphs": [
      "A resource definition names a local source and its yields. Place it in a real room using the supported location/resource controls. Configure required tools and renewal settings deliberately. Players gather from the source available in their current location, not from any item name anywhere in the world.",
      "Example: create a resource named Garden Beds that yields an existing vegetable item, place it in valley_garden, and describe that source in the room. Test the exact local source name, its yield, renewal and any tool/season restriction.",
      "Encounters associate defenders or creatures with a source and possible harvesting behavior. Harvesting and destroying a source are different outcomes. Test that a destroyed or exhausted source does not falsely remain renewable.",
      "Species records support ecology and life-stage information. Use the offered species categories and compatible prey/diet/source references. Fantasy ages and health profiles are authored rules; mage is ordinarily a class or occupation, not automatically a biological species."
    ]
  },
  {
    "id": "interactions",
    "title": "Interactions, abilities and character options",
    "paragraphs": [
      "Interactions describe supported combinations of tools, consumed components, targets and effects. The documented effect operators include damage, repair, heal and create. Prefer a working interaction as a template, then validate every referenced tool/material/target.",
      "Abilities define supported effects, costs and training/use behavior. A new name or description does not implement a new effect operator. Test availability, cost, valid targets and failure messages.",
      "Races, Classes and Sexes provide character-creation options and starting configuration. Check starting equipment, abilities and faction/species references. Test creating a fresh character with the new option; changing a definition does not necessarily rebuild an existing saved character.",
      "Example: duplicate a supported class, change its readable name and description, replace one starting item with a valid compatible item, then create a new test character. Retain unknown custom fields rather than replacing a whole object just to change one property."
    ]
  },
  {
    "id": "rules",
    "title": "World rules, living rules and content packs",
    "paragraphs": [
      "World rules includes capacity, mortality, player combat and dawn. Read each control and use Save world rules. Apply afterward when you intend the running world to use those saved settings. Permanent deaths already recorded are not undone by selecting a different mortality rule.",
      "Enable living rules and Enable civic rules are explicit changes, not help buttons. Civic enabling validates references and material creation paths; fix missing sources instead of assuming the button will invent a functioning economy.",
      "Add 20-item content pack is another content-creation action in the map area, not a preview or an automatic source for every item you design. Inspect its added records before saving and applying.",
      "Add Road Casebooks and Add rotating markets add authored content through their specific tools. They are not previews. Use a practice copy, inspect the result and retain your own changes. Do not repeatedly add packs as a substitute for diagnosing a missing local source.",
      "Where Experience and leveling controls are present, first accomplishments and repeat practice have separate awards, cooldowns and limits. Waiting alone gives no XP; changing thresholds does not mean earned history is erased. These controls are build-specific, so use the fields actually shown."
    ]
  },
  {
    "id": "clock",
    "title": "Expanse time, dawn and fresh-start clock",
    "paragraphs": [
      "Expanse uses 25 hours per day, 9 days per week, 26 days per month and 8 months per year: 208 days/year, 52 days/season, 1,500 minutes/day and 312,000 minutes/year. Clock hours run 00–24. Default dawn is 06:15; daylight lasts 12.5 hours.",
      "World rules lets you edit dawn. This is different from setting the current adventure clock. Existing saved world time takes precedence when you continue an adventure.",
      "Newer builds may also show New-world start hour/minute and a start-at-dawn option inside World rules. If those controls are present, they affect only a fresh adventure/world, not an existing save or running session. Example: choose a fresh-start 08:00 for your practice world, save its rules and begin a genuinely new adventure. If the controls are absent, this UI workflow is not available in that build.",
      "The Player Calendar is a separate real-world, 24-hour scheduling tool using time zones. An Expanse-time note is not a real-world reminder or an offline alarm. Do not mix its dates with the world calendar."
    ]
  },
  {
    "id": "population",
    "title": "Resident population: preview before adding people",
    "paragraphs": [
      "Select the intended world and choose Resident population. Author the seed, cohort ID, size, age bins, species/race/faction, explicit homes and capacities, learning provision, workplaces and leisure rooms. The tool does not invent housing or enable living/health rules for you.",
      "Preview cohort is read-only and uses current Editor content, including staged room definitions. Inspect target/actual ages, household composition, education, health caveats and the available reference list. The reported denominator is this new cohort, not a universal “healthy” population statistic.",
      "After review, check the confirmation box and choose Apply preview to Editor draft. This stages NPC definitions and their population manifest. Use main Save, then Apply to running game or Run the selected world. Preview alone does not add NPCs.",
      "Example: create and stage several home rooms with sufficient capacity, choose a small cohort such as 12 residents, and start with health disabled. Review every household before applying. Health presets are fictional and opt-in; age does not guarantee illness.",
      "A cohort has 1–5,000 residents. The same cohort ID and same configuration reuse its result rather than regenerating it; a changed configuration under that ID is rejected. A new ID is an intentionally additional cohort, not a retry button. A lost Apply response should be retried with the same unchanged preview. Previews expire and invalidate when relevant content changes."
    ]
  },
  {
    "id": "geology",
    "title": "Geology settings and consequences",
    "paragraphs": [
      "First Save any new or edited rooms with the main Creator Save. Open Geology settings. It edits metadata.geology, not every room’s static geological fields. Validate draft checks saved references. Save geology writes these settings only. Then separately Apply to running game or Run the selected world.",
      "Events also require living rules. Opening the dialog, editing a draft or copying its example does not enable them. Keep enabled false while learning. Replace every placeholder room ID in an example before validation.",
      "Example of an intentionally disabled, empty configuration:\n{\"enabled\":false,\"seed\":17,\"faults\":[],\"volcanoes\":[],\"basins\":[]}",
      "Faults, volcanoes and basins have explicit locations, rates, bounded intensity and duration/recovery fields. Start small. Consequence targets for actors, structures, routes and resources must be deliberately authored; empty target lists do not mean “damage everything.”",
      "Cancel discards an unsaved dialog draft. Reload saved replaces it after confirmation. A successful Save geology is not undone by closing. If another save invalidates the revision, reload and review rather than overwriting the newer configuration."
    ]
  },
  {
    "id": "weather",
    "title": "Weather settings, climate and shelters",
    "paragraphs": [
      "Per-room climate and the optional regional weather configuration are different layers. Save room edits first. Open Weather settings, edit the JSON, Validate draft, Save weather, then separately Apply or Run. Living rules must be enabled separately.",
      "Example of an intentionally disabled configuration:\n{\"version\":1,\"enabled\":false,\"seed\":17,\"regions\":[]}",
      "Use real saved region-room IDs, authored outdoor exposure and public indoor shelters with reachable routes. Do not merely write “storm cellar” in prose and expect evacuation behavior. Explicit severe-weather targets and refuge configuration matter.",
      "The editor examples and range reference describe supported fronts, warning windows and cooldowns. They are fictional gameplay parameters, not meteorological forecasts. No moving tornado funnel or general structural storm-damage simulator is promised by this configuration. Geological basin linkage is explicit, not inferred from a picture of a river."
    ]
  },
  {
    "id": "history",
    "title": "World history: make a separate new world",
    "paragraphs": [
      "Choose World history for the intended source world. Pick a new, unused world slug. Edit the displayed configuration, use Available NPC, faction and room IDs, and consult Rule settings and ranges. Do not paste an isolated example fragment over the entire configuration.",
      "Preview is read-only. Inspect summary/limits, timeline, faction state, individual actors and preserved-template file hashes. Only after a successful unchanged preview does Create new world become available. It creates a separate world; it does not overwrite the source or rewrite the current adventure.",
      "Selection references sentient NPCs with explicit ages. generated_fields is explicit permission to replace authored gold, health, life_profile or birth_epoch; leave it empty if you want authored values to win. generated_relation separately allows replacement of an authored faction relationship.",
      "Example edit to an existing selected actor: annual_income 20, annual_expenses 10, accident_probability 0, generated_fields []. Use that actor’s real source_id and retain all other required configuration. Preview before creating the new world.",
      "Optional live_diplomacy is off by default and changes bounded goodwill through configured cooperation/disputes. Locks and bounds still apply. History models bounded annual development and dated events, not full ancestry, reproduction, armies, conquest or new geological terrain. Unsupported template entries stop publication instead of silently dropping your content."
    ]
  },
  {
    "id": "tax",
    "title": "Tax plans: authoring only, not active taxation",
    "paragraphs": [
      "Choose Tax plans. Save new rooms, factions and NPC definitions with the main Creator Save first, then reopen Tax plans so its references include them. New plan adds a design entry; Remove plan removes one from this draft.",
      "Each plan has a unique ID/name, assessment basis, rate/amount, collection interval in world days, jurisdiction rooms, recipient faction, optional collector, and written exemptions/procedure notes. Select several rooms with the platform’s multi-select controls. Percentages are 0–100; fixed gold is 0–1,000,000; interval is 1–10,000 days; maximum 100 plans.",
      "Example: a plan called Market maintenance with Income, rate 5, interval 30, selected saved market rooms and a recipient faction. An assessed income of 100 gold would imply 5 gold in this design. This is an illustrative plan, not an active charge.",
      "Save plans writes only creator-tax-plans.json. It does not save unrelated Creator edits. Closing without saving discards this dialog’s changes. A stale revision requires close/reopen and review.",
      "No taxes are collected. No income/property assessment runs, no collector is paid or dispatched, no prices/treasury/debt/fines change and nothing runs on the clock. Exemptions are notes, not executable conditions. There is no activation or Collect control."
    ]
  },
  {
    "id": "pixels",
    "title": "Pixel Art Studio: draw and retain editable work",
    "paragraphs": [
      "Choose a world and open Pixel Art Studio. Terrain tiles are exactly 24×24 pixels; character and equipment grids are 16×16. Zoom changes display size, not asset dimensions. Click or drag to paint; use the eraser for transparency.",
      "Choose a color/palette, select a layer, and use Visible, Add layer, Layer forward/backward, Delete layer, Undo and Redo. Each asset has 1–8 layers; undo history is bounded. Hidden layers remain in editable artwork but do not render into a flattened PNG.",
      "Name the artwork and record author/license information. Save new revision stores an immutable version in the selected world’s asset library. Loading an earlier revision and saving a new one retains the earlier revision. The library is bounded to 256 revisions and 8 MB, with no automatic cleanup.",
      "Save layered file exports editable .expanse-art.json. Export PNG flattens visible layers and cannot preserve editable layers. Import accepts supported layered-art data, not arbitrary image sheets or executable code. Complete the native Save dialog; cancellation does not save the draft.",
      "Game Save is not an art save. Save a library revision or layered file before leaving the application. A changed draft remains unsaved even if an earlier export finishes. PNG export does not mark layered work safely saved."
    ]
  },
  {
    "id": "bindings",
    "title": "Bind tiles, NPC sprites, player bases and gear",
    "paragraphs": [
      "First make or load a saved artwork revision. Select the intended Creator record, then use the Studio’s explicit binding control. A room uses a tile; an NPC can use a complete character sprite. Restore default removes the binding, not the saved artwork.",
      "Player bases bind to races and equipment artwork to items. Choose the exact humanoid stature/build registration, and for equipment choose the correct slot. Nine humanoid stature/build combinations are supported. The 16×16 grid is full-body registration, not a separately scaled picture for each slot.",
      "Use Registered paperdoll preview to check alignment. Equipment follows the existing renderer’s layer order. Wrong anatomy or slot falls back to existing art. Custom non-humanoid player/equipment fitting is not implemented.",
      "Example: select a practice room, draw a 24×24 grass tile, Save new revision, bind it to that room and inspect the authorized local/detailed map. The artwork does not change climate, terrain passability, exits or geology. Whole-world exports retain the asset library and bindings."
    ]
  },
  {
    "id": "exchange",
    "title": "Import, export and preserve your world",
    "paragraphs": [
      "The Creator Export/Import tools work with whole-world .expanse bundles using their displayed file-path workflow. This is different from a game save and different from a single Pixel Studio layered-art file.",
      "Export a known-good world before substantial changes. Keep the resulting archive outside the source world folder, and retain the original. The v13 Import dialog asks only for an archive path and uses the archive’s own world slug; it does not offer a rename field. For experiments, use a separate test installation or an archive whose slug is unused. Validation failures should leave the destination unchanged.",
      "Force is not permission to discard incompatible custom art. Import over a world with different artwork revisions can be refused to preserve history. Unknown/unsupported content may also be rejected rather than silently omitted. Read the actual error instead of repeatedly forcing the same file.",
      "Example: export your practice world to a separate exports directory. Test importing that archive in a separate installation where its world slug is unused; do not assume the Import dialog can rename it. Inspect rooms, NPCs, history and art bindings before using it for play. Never replace your only good copy just to test the archive."
    ]
  },
  {
    "id": "testing",
    "title": "Test your adventure as a new player",
    "paragraphs": [
      "After Save and Validate, run the practice world with a fresh character. Check a complete loop: get directions, leave the starting area, acquire essential gear, accept a quest, obtain its requirements, return, earn a reward, rest and continue.",
      "Test daylight and darkness, with and without a lantern. Test both directions through doors, stairs and region boundaries. A visible map tile and a valid movement route are different facts.",
      "Test NPCs on and off duty; friendly and disliked factions; empty and stocked shops; low funds; insufficient materials; missing tools; depleted sources; and quest prerequisites before and after completion.",
      "Check game-save continuation separately from starting a new adventure. Check that custom art can be edited and rendered after a world export/import. Keep logs or exact error messages and the build label when reporting a defect."
    ]
  },
  {
    "id": "singing",
    "title": "Singing, songbooks and instrument production",
    "paragraphs": [
      "All traditions, lyrics, voice choices, scores and instruments belong to the world file. In a race record’s singing field, author a tradition ID, style, starting songbook item IDs, preferred instrument tags and a pool of voices. Each voice has a stable ID, a readable label and an integer transpose from −36 to 36 semitones. An individual’s stable voice choice is independent of sex or gender. Any race may learn another tradition’s song by reading its songbook; preferred instruments do not restrict who may use them.",
      "In an NPC’s singing field, optionally select a voice ID from that person’s race pool and add songbook IDs. Select work, leisure or performance contexts only when spontaneous singing is wanted. interval_minutes is an optional whole number from 1 to 1500. Willing to answer or pass along a known song opts that NPC into responses and relays; an actual participant must be local, awake, alive, available, cooperative and familiar with the song. The engine never makes another player sing automatically.",
      "A songbook is an ordinary readable item with its normal name, read_text, publication and physical location, plus a song field. Author a tradition/style, the form and 1–16 verses. Each verse’s call is a lead line of 1–240 characters. Solo uses only that call; call_response requires a response of 1–240 characters in each verse; relay uses 1–3 successor lines, each at most 240 characters, in the relay array. Each successor needs a different real willing NPC. Missing participants truncate the relay; a lone singer invites an answer without impersonating anyone. Changing form intentionally removes incompatible response/relay fields only when Save songbook is chosen.",
      "The optional score produces a short synthesized musical cue. These sounds are musical tones, not natural recordings of people singing the lyrics. The sung words appear in Conversation. Music volume and mute control the cue; leaving the room, losing an actual participant, hiding the page or leaving the game stops it. A map refresh does not replay it. Actions → Songs lists accessible songs; Sing chooses the next one, while the command sing followed by an accessible title or item ID selects a song. No play command is added because that name is already used by companion interactions.",
      "Score JSON uses version: 1, tempo from 40 to 240 and tracks. It supports at most 8 tracks, 128 total notes and 20 seconds including releases. Each note is [midi, start_beats, duration_beats, velocity]: integer MIDI 24–108, a nonnegative start, a positive duration and velocity 0–1. Each track has role lead, response, relay or accompaniment, gain 0–1, notes and envelope. Relay also requires participant 1–3; response tracks need call_response form and relay tracks need that successor in every verse. Voice notes are shifted by the actual participant’s voice transpose. Validate rejects scores that exceed the pitch bounds for any authored learnable voice, instead of silently altering the melody.",
      "Lead, response and relay tracks use timbre periodic with harmonics: 1–16 amplitudes from 0 to 1, at least one positive. Accompaniment requires an instrument tag and may use periodic or noise. Every envelope specifies attack 0–1 seconds, decay 0–2 seconds, sustain 0–1 and release 0–2 seconds. The client contains no named racial timbre or instrument preset. Score JSON is preserved completely, including additional metadata; leaving it blank gives text-only performances. A score example is {\"version\":1,\"tempo\":100,\"tracks\":[{\"role\":\"lead\",\"timbre\":\"periodic\",\"gain\":0.18,\"harmonics\":[1,0.35,0.12],\"envelope\":{\"attack\":0.03,\"decay\":0.1,\"sustain\":0.7,\"release\":0.12},\"notes\":[[60,0,1,0.8]]}]}. This is a schema example, not automatically authored game content.",
      "An instrument item’s instrument field has the tag used by an accompaniment track. The performer or an actual response/relay participant must carry a real matching item; unavailable accompaniment is omitted. Use existing recipe ingredients and outputs, a supported station, workshop recipes, finite initial_stock and producer staff at a real work location to manufacture instruments. NPC purchase_targets can acquire available stock with actual gold. Singing creates no instruments, currency, XP, supplies or production loop, and it never refills old saved inventories from an NPC template.",
      "Edit metadata.singing in World files to enable the system. Use version: 1 and enabled: true, with optional npc_interval_minutes (default 60, range 1–1500), room_interval_minutes (default 15, range 1–1500), and player_interval_seconds (default 5, range 1–60). Optional wordless contains an authored title and optional score, without lyrics or a cultural style. Without an authored score it is text only. Leave the singing configuration absent or disabled in worlds that do not use it; their Actions menu hides Songs and Sing.",
      "The Inspector’s Save singing/songbook/instrument button stages only that field. Main Save writes the draft; Validate checks types, ranges, references and cross-record compatibility, then export the complete .expanse file. Complete World files editing preserves all JSON, including unknown extension fields and score metadata. Import the exported copy for verification. Runtime singing only changes in-memory activity and a small verse/voice progression record; the player’s explicit Save remains the durable checkpoint."
    ]
  },
  {
    "id": "troubleshooting",
    "title": "Common problems and where to look",
    "paragraphs": [
      "“No matching object”: inspect the current room’s actual resource or object list. An item definition or a quest description is not a local gathering source. Travel to the authored source first.",
      "Cannot change Inspector selection: finish/stage or correct the field, wait for its save result, or explicitly Revert. A failed write should not be solved by closing the application and hoping the draft survived.",
      "Invalid reference or station: use an existing ID or offered supported station value, save prerequisite records where the dialog requires saved references, then validate again. Display names are not always stable IDs.",
      "New rules do not affect play: confirm the selected world, whether the change is staged or saved, whether Apply is still required, and whether it affects only fresh adventures. Tax plans deliberately do not affect play at all.",
      "New sprite is invisible: confirm the selected target, saved revision, native dimensions, binding kind, registration and equipment slot. Check visibility/knowledge and whether another sprite occupies the same location. Do not change game mechanics merely to make art appear.",
      "History/Population preview becomes stale: inspect changes, preview again and review the new result. Do not substitute a new cohort ID or force an old token to bypass the protection."
    ]
  },
  {
    "id": "ide",
    "title": "Structured JSON editing assistance",
    "paragraphs": [
      "In builds with the JSON help line beneath an advanced Inspector field, Ctrl+Space requests known completions at the caret. Type a key prefix to narrow suggestions; use Up/Down and Enter, or choose a suggestion with the mouse. Escape dismisses the popup. Ordinary descriptions are prose and are not treated as code.",
      "This first editing-assistance slice covers explicitly tagged structured Inspector fields, not every JSON dialog or a full programming IDE. Known keys come from shipped field defaults, with additional engine-backed life-stage keys, selected enum/boolean choices and explicitly supported reference locations. Unknown custom structures receive syntax help without invented completions.",
      "Example: in a practice species life_stages field, edit an existing key to a partial spelling such as school, place the caret inside that quoted key and request completion. Choose school_start_years, retain its intended numeric value and preserve the other properties. Do not replace the entire object to try a single suggestion.",
      "For supported reference positions such as a workshop recipes array, suggestions use existing IDs in the selected world’s authorized cache. Choosing an ID does not create the recipe or prove all its requirements work. Unsupported reference positions do not guess a list.",
      "Completion changes only the local draft; it does not Save, Apply or call an AI service. JSON syntax feedback identifies malformed text while retaining it. Syntax valid is not the same as valid field types, ranges, references or gameplay: use Save field and Creator Validate for those checks.",
      "Keep the caret in the intended token. If the selection/world changes or the draft changes while suggestions are open, request suggestions again rather than applying a stale replacement. Large/deep drafts have bounded assistance; their text is retained. Specialized World history, population, geology and weather JSON dialogs still use their own validation workflows unless the JSON help control is actually shown."
    ]
  },
  {
    "id": "reference",
    "title": "Field and tool reference: where details live",
    "paragraphs": [
      "Use the Inspector’s field hints and typed controls for the selected record. Structured widgets expose their supported choices; fields not implemented by the engine are not made functional by adding prose. Preserve unfamiliar custom fields unless you intentionally understand and change them.",
      "The specialized dialogs include their own schemas, examples or references: Geology settings and Weather settings validate their settings; Resident population exposes cohort/reference information; World history lists rule ranges and template/actor results; Tax plans uses constrained fields; Pixel Studio enforces native dimensions and registration.",
      "The repository docs folder contains focused system guides, including GEOLOGY-CREATOR-SETTINGS.txt, POPULATION-CREATOR.md, POPULATION-HEALTH.md, REGIONAL-WEATHER.txt, ROTATING-MARKETS.md and connected quest guidance. Some historical release notes describe earlier interfaces; prefer this guide and the actual labels/validation in your installed build.",
      "Coverage is tool-level instructions and worked examples, not a promise that every numerical field is self-explanatory. If a control still lacks enough explanation to author safely, keep the working value and identify that exact field for a follow-up help entry."
    ]
  }
];
