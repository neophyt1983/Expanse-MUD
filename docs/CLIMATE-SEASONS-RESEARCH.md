# Climate, seasons and seasonal needs

Research and implementation direction, 19 November 2026.

This document records the requested next phase. It does not claim that a new climate model, food spoilage, winter provisioning or water-quality simulation has been deployed. The current code already supplies calendar seasons and some climate effects; the work below extends that foundation.

## Decisions from the game direction

- Preserve Expanse's established calendar and authoritative world clock.
- Support the requested snowy winter, rainier spring, hot and relatively dry summer, and cooler, drier autumn as an authored regional pattern.
- Give other locations appropriate regional patterns. Geography determines which seasonal profile applies.
- Make food, clothing, shelter and clean-water preparation affect actual finite supplies and persistent work requests.
- Let NPCs prepare from their background, experience, observations, reading and conversations. They do not know future weather, distant shortages or the location of undiscovered supplies automatically.
- Keep quests while their underlying need exists. Player and NPC deliveries reduce the same outstanding need. A calendar rollover alone does not replenish rewards or recreate completed demand.
- Keep animal activity connected to real habitat, food, water, shelter, species and ownership.

## Research findings

### Location and season are separate inputs

On Earth, axial tilt changes the sunlight received by each hemisphere over the year. The hemispheres have opposing seasons. Expanse can retain its own year length while using that relationship. The particular planetary assumptions remain design choices, rather than an assertion that Expanse is Earth. [NASA: seasons](https://science.nasa.gov/helio-and-you-seasons-on-earth-mars-and-beyond/)

Climate describes the expected distribution of conditions; weather is the particular event occurring now. A regional normal should therefore influence the likelihood and intensity of weather, with continuing events and occasional departures from normal. It should not force identical weather on every day of a season. [NWS: climate and weather](https://www.weather.gov/climateservices/CvW)

Temperature and precipitation are both needed to characterize a climate. Latitude alone cannot select a complete climate profile. Ocean influence, continental location and topography help explain differences between locations at similar latitudes. [Met Office: climate zones](https://weather.metoffice.gov.uk/climate/climate-explained/climate-zones)

### Useful regional families

The table gives a small game-oriented set of profiles. Its preparation column is a proposed game mechanic, not a scientific forecast. Köppen-style categories are descriptive labels for long-term temperature and rainfall patterns; the engine should store those patterns directly.

| Profile | General seasonal character | Proposed preparation and work |
| --- | --- | --- |
| Equatorial rainforest | Warm throughout the year; frequent rainfall without a strong dry season. | Protect stored goods from damp, maintain drainage and protect drinking-water stores. |
| Tropical wet–dry / monsoon | A pronounced wet season and a drier interval. | Store water for dry periods; protect crops, roads and stores during heavy rain. |
| Desert / steppe | Persistent water deficit; hot and cold variants exist. | Secure reliable water sources and drought reserves; adapt travel and clothing to the local temperature range. |
| Maritime temperate | Moderate seasonal temperatures, with precipitation possible throughout the year. | Keep fuel and clothing dry; maintain shelters and transport during storms. |
| Continental temperate | Greater seasonal temperature range, with cold winters and warm or hot summers. | Preserve food and fodder, repair winter clothing, prepare fuel and accessible water. |
| Mediterranean | Dry summers and wetter winters. | Prioritize summer water storage and irrigation, then winter drainage and shelter maintenance. |
| Subarctic / tundra | Long cold periods and a short warmer interval. | Plan a longer reserve period, a narrow production window and reliable transport. |
| Mountain / highland | Conditions change with elevation and exposure; neighboring slopes can differ. | Store for pass closures, route around hazards and exploit suitable local growing areas. |

Classification basis: [NOAA: climate zones](https://www.noaa.gov/jetstream/global/climate-zones) and [NOAA: climate subdivisions](https://www.noaa.gov/jetstream/global/climate-zones/jetstream-max-addition-k-ppen-geiger-climate-subdivisions). These families are broad guides; local profiles still need authored seasonal values.

### Rainfall cannot be one global four-season rule

Large-scale circulation helps produce wet equatorial belts, subtropical dry belts and stormier mid-latitude regions. Land and oceans disrupt a simple symmetric arrangement. This supports broad procedural geography with regional overrides, rather than identical stripes around the globe. [NOAA: global atmospheric circulation](https://www.noaa.gov/jetstream/global/global-atmospheric-circulations)

The tropical convergence zone shifts through the year, helping create wet and dry seasons. Some locations have two rainfall peaks; others have one main wet period. For the game, wet-season phase should be a separate profile parameter rather than being derived solely from the word “summer.” [NOAA: tropical convergence zone](https://www.noaa.gov/jetstream/tropical/convergence-zone)

Moist air rising over mountains can produce cloud and precipitation on the windward side. Descending air on the leeward side can produce a rain shadow. Mountains therefore need a relationship to moisture-bearing winds, not an unconditional “all mountains are dry” rule. [WMO: orographic influences](https://cloudatlas.wmo.int/en/orographic-influences-on-the-windward-side.html)

Snow is also delayed water storage: accumulated snow can melt and supply lower-elevation landscapes during warmer periods. This provides a physical connection between winter snowfall and later river or reservoir supply. [USGS: snow, ice and permafrost](https://www.usgs.gov/science/science-explorer/climate/snow-ice-and-permafrost)

## What exists in the code

This audit describes the checkout, not an inspected live world archive.

| Existing source | Present behavior | Gap for this phase |
| --- | --- | --- |
| [worldtime.py](../engine/worldtime.py) | 25-hour days, 9-day weeks, 26-day months, 8-month / 208-day years; four 52-day seasons; southern latitudes offset by two seasons. Daylight is explicitly fixed at 750 minutes. | Keep the calendar. Variable day length would be a separate, explicit compatibility change. |
| [climate.py](../engine/climate.py) | Uses room latitude, elevation, coast, terrain, shelter and rain-shadow fields; calculates temperature, moisture, precipitation and travel cost. | Temperature changes in coarse season steps. Most rainfall uses static moisture. Coast handling applies a blanket warmth adjustment; rainfall does not resolve windward geography. |
| [regional_weather.py](../engine/regional_weather.py) | Optional saved regional fronts, season-specific state weights, duration, warnings, storms, shelter and exposure; simulation uses the authoritative clock. | Default seasonal weights are shared across climates. No full regional climate-profile or snow-water store is established here. |
| [wildlands.py](../engine/wildlands.py) | Expedition weather can override base conditions with authored 15-minute phases. | Preserve intentional authored scenes, but make the override contract explicit so it cannot accidentally erase seasonal consequences. |
| [coordinates.py](../engine/coordinates.py) | Separates layout coordinates, world units, planet latitude/longitude and surveyed metric positions. | Climate needs a documented geographic-source priority. A room's displayed globe position and its default climate latitude must not silently disagree. |
| [ecology.py](../engine/ecology.py), [gathering.py](../engine/gathering.py), [resource_nodes.py](../engine/resource_nodes.py) | Harvest availability already respects configured seasons and temperature limits. | Production, preservation, consumption and storage must share the same local conditions. |
| [needs_market.py](../engine/needs_market.py) | NPC hunger/thirst/rest and other needs; consumable relief, finite merchant stock and demand. | Winter reserve planning, spoilage, accessible water and explicit clothing protection require additional state and rules. |

The actual imported world must be inspected before assigning profiles to named settlements. A screenshot coordinate or a settlement name is insufficient to infer its elevation, ocean currents, rain shadow or monthly rainfall.

## Recommended implementation

### 1. Resolve real geography consistently

Create one validated location resolver for climate. Preserve explicit authored climate overrides; otherwise obtain latitude and elevation from the authoritative geographic record or assigned region. Layout X/Y is not latitude. Rooms inside a building inherit the exterior's regional weather context, with shelter and heating modifying exposure locally. Unknown geography should be labeled as a fallback, not presented as surveyed data.

Keep longitude as placement within continents, coasts and circulation patterns. Do not turn east/west position into a direct universal temperature formula. Store ocean moderation and current influence independently so a coast is not automatically warmer and wetter.

### 2. Store profiles over Expanse's own year

Use eight authored seasonal/monthly control points for temperature, precipitation tendency, humidity and wind, or a comparably bounded annual curve. Interpolate smoothly around the year. Flip the seasonal phase where appropriate for southern latitudes; do not copy Gregorian month numbers into Expanse.

A first profile should include:

- Mean temperature and normal seasonal range.
- Rainfall likelihood and intensity by annual phase.
- Coastal moderation and regional warm/cold-current influence.
- Prevailing moisture-bearing wind and rain-shadow exposure.
- Elevation and optional local shelter/microclimate modifiers.
- Limits on exceptional heat, cold, drought and severe events.

Treat Earth-based patterns as tuning guidance. Expanse's fixed daylight contract and fictional geography may deliberately simplify them. Keep explicit fantasy exceptions visible in Creator data.

### 3. Generate persistent regional weather

Extend the existing front system rather than creating a second weather clock. Select fronts using local climate profiles, persist their seed and state, and transition smoothly between them. Neighboring rooms share a regional front and receive local terrain/exposure adjustments. Reading a map must not roll new weather or advance a hazard.

Compute precipitation phase from the final temperature model after nighttime and elevation adjustments. The first game model can use a bounded rain/snow transition range and document that simplification; a surface-temperature threshold is not a full atmospheric snow forecast.

### 4. Track physical consequences

Persist snow cover and water equivalent separately from “snowing now.” Melt should transfer stored water into the relevant basin or store, and drainage should carry it onward; a change of weather label should not delete accumulated snow. Track frozen or blocked access separately from the physical existence of a water supply.

Use actual snow, ice, wetness, heat and wind exposure to modify travel, shelter value, clothing needs, animal forage and resource production. Finite storage needs capacity, contents, condition, protection and access permissions. Food lots need a bounded preservation/spoilage model before winter sufficiency is claimed. Water quantity and water quality need distinct fields: a full reservoir is not automatically a clean drinking-water supply.

### 5. Let households and guilds plan ahead

A useful first game rule is:

`reserve gap = expected consumption until the next reliable supply + contingency reserve - usable stock - credible incoming deliveries`

This is a proposed planning rule, not a calibrated nutrition or hydrology model. Calculate food, fodder, clothing, fuel and water needs separately. Count only stock that the planner knows about and can access. Discount uncertain deliveries, expected spoilage and supplies promised elsewhere.

NPCs can know typical local seasons from their starting background and learn from later years. A farmer may read a forecast or talk to a traveler; those reports can be stale or incomplete. Their belief about the coming season can differ from the authoritative simulation's actual future events. Training, observation, experience and social connections should improve decisions without granting world-wide knowledge.

Stable guild requests can respond to those gaps. For example, one store's grain request keeps its identity while contributions reduce its deficit; it closes when supplied and can reopen when real consumption or changed reserve requirements create a new deficit. Finite payment and physical delivery still apply. Harvest, preservation, hauling, repairs, water treatment and animal care can provide different tasks and difficulties around the same underlying need.

## Acceptance conditions for the seasonal phase

1. Northern and southern seasonal phase is correct without changing the calendar or silently changing day length.
2. Nearby rooms use consistent geographic data and region weather; private map data remains private.
3. At least one example each distinguishes continental winter, maritime moderation, summer-dry climate, tropical wet/dry seasons and mountain rain shadow.
4. Map refresh and save/reload do not reroll fronts, snowpack, stock, reserve calculations or NPC history.
5. Weather is persistent and variable within a season; neither every winter day snows nor every summer day is clear.
6. Snow accumulation, melt, consumption, delivery and spoilage conserve the modeled quantities except for explicit production, loss and drainage terms.
7. Players and NPCs use the same shared need; concurrent or stale contribution attempts cannot overfill it or pay twice.
8. NPC planning uses actual learned information. Unknown sources and blocked routes do not become magically available.
9. Accelerated rest advances the same simulation in interruptible bounded steps, with no private future for one participant.
10. Old worlds preserve their current behavior until the new profile and stock systems are explicitly enabled and validated.
