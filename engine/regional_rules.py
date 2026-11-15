"""Validate optional world-authored safety, encounters and civic institutions."""
import math


def managed_npcs(rules, rooms):
    """References handled by authored encounter pools, galleries or retirement."""
    result = set()
    encounter = rules.get('regional_encounters', {})
    for values in encounter.get('pools', {}).values():
        result.update(values)
    result.update(encounter.get('retired_templates', []))
    for zoo in rules.get('regional_zoos', {}).values():
        result.update(entry['npc'] for entry in zoo.get('displays', []))
    return result


def validate(data, rooms, npcs=None):
    """Reject bad references/tuning at import and export, before play starts."""
    def fail(path, reason):
        raise ValueError('world-rules.json: '+path+' '+reason)

    def obj(value, path):
        if not isinstance(value, dict):
            fail(path, 'must be an object')
        return value

    def block(name):
        return obj(data.get(name, {}), name)

    def boolean(row, field, path):
        if field in row and type(row[field]) is not bool:
            fail(path+'.'+field, 'must be true or false')

    def number(row, field, path, low=0, high=1000000, *, integer=True, required=False):
        if field not in row:
            if required:
                fail(path+'.'+field, 'is required')
            return
        value = row[field]
        good = type(value) is int if integer else type(value) in (int, float)
        if not good or not math.isfinite(value) or not low <= value <= high:
            fail(path+'.'+field, 'must be '+('an integer' if integer else 'a number')+' from '+str(low)+' to '+str(high))

    def text(value, path):
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            fail(path, 'must be nonempty text of at most 256 characters')

    def reference(value, available, path):
        text(value, path)
        if available is not None and value not in available:
            fail(path, 'references a missing record: '+value)

    gameplay = block('regional_gameplay')
    for key in ('enabled', 'encounters', 'courts', 'zoos'):
        boolean(gameplay, key, 'regional_gameplay')
    for key in ('hearing_delay_minutes', 'judge_wait_minutes', 'prison_threshold_minutes'):
        number(gameplay, key, 'regional_gameplay', 1, 1000000)
    sentences = obj(gameplay.get('sentences', {}), 'regional_gameplay.sentences')
    for charge, row in sentences.items():
        path = 'regional_gameplay.sentences.'+charge
        text(charge, path)
        obj(row, path)
        number(row, 'minutes', path, 0, 1000000000, required=True)
        number(row, 'fine', path, 0, 1000000, required=True)
        if row.get('custody', 'auto') not in ('auto', 'jail', 'prison'):
            fail(path+'.custody', 'must be auto, jail or prison')
    if gameplay.get('courts') is True and 'default' not in sentences:
        fail('regional_gameplay.sentences.default', 'is required when courts are enabled')

    starter = block('starter_safety')
    for key in ('enabled', 'include_direct_civic_exits', 'include_frontages'):
        boolean(starter, key, 'starter_safety')
    number(starter, 'conflict_minutes', 'starter_safety', 1, 1000000, required=starter.get('enabled') is True)
    number(starter, 'tutorial_path_steps', 'starter_safety', 0, 32)
    if 'tutorial_category' in starter:
        text(starter['tutorial_category'], 'starter_safety.tutorial_category')

    defense = block('city_defense')
    for key in ('enabled', 'recognize_legacy_watch'):
        boolean(defense, key, 'city_defense')
    stats = obj(defense.get('guard_stats', {}), 'city_defense.guard_stats')
    for key in ('hp', 'attack', 'defense'):
        number(stats, key, 'city_defense.guard_stats', 1 if key == 'hp' else 0)
    for key, low, high in (('initial_responders', 1, 16), ('max_responders', 1, 16),
                           ('reinforcements_per_round', 0, 8), ('incident_budget', 1, 64),
                           ('route_node_budget', 16, 8192), ('route_node_limit', 32, 32768),
                           ('nearby_steps', 1, 16), ('nearby_room_limit', 16, 2048)):
        number(defense, key, 'city_defense', low, high)
    number(defense, 'perimeter_steps', 'city_defense', 0, 8)
    if 'fatal_charge' in defense:
        text(defense['fatal_charge'], 'city_defense.fatal_charge')
        if len(defense['fatal_charge']) > 80:
            fail('city_defense.fatal_charge', 'must contain at most 80 characters')
        if gameplay.get('courts') is True and defense['fatal_charge'] not in sentences:
            fail('city_defense.fatal_charge', 'needs a corresponding authored sentence')
    support = obj(defense.get('military_support', {}), 'city_defense.military_support')
    boolean(support, 'enabled', 'city_defense.military_support')
    if 'flag' in support or support.get('enabled') is True:
        text(support.get('flag'), 'city_defense.military_support.flag')
    for key, low, high in (('escalation_rounds', 1, 1000), ('police_casualties', 1, 64),
                           ('initial_responders', 1, 64), ('max_responders', 1, 64),
                           ('reinforcements_per_round', 0, 16)):
        number(support, key, 'city_defense.military_support', low, high)
    for row, path in ((defense, 'city_defense'), (support, 'city_defense.military_support')):
        if row.get('initial_responders', 0) > row.get('max_responders', 128):
            fail(path, 'initial responders must not exceed its maximum')

    encounters = block('regional_encounters')
    boolean(encounters, 'enabled', 'regional_encounters')
    for key, high in (('revision', 1000000), ('check_interval_minutes', 1000000),
                      ('npc_observer_budget', 64), ('max_active', 64),
                      ('attack_grace_minutes', 1000000), ('attack_interval_minutes', 1000000),
                      ('first_move_minutes', 1000000), ('move_interval_minutes', 1000000),
                      ('road_respawn_minutes', 1000000), ('offroad_respawn_minutes', 1000000),
                      ('despawn_after_minutes', 1000000), ('pursuit_radius', 32)):
        number(encounters, key, 'regional_encounters', 1, high)
    number(encounters, 'move_chance', 'regional_encounters', 0, 1, integer=False)

    def band(row, path):
        obj(row, path)
        number(row, 'chance', path, 0, 1, integer=False, required=True)
        number(row, 'local_cap', path, 0, 64, required=True)

    for key in ('road', 'unknown_distance'):
        if key in encounters:
            band(encounters[key], 'regional_encounters.'+key)
    bands = encounters.get('offroad_bands', [])
    if not isinstance(bands, list) or len(bands) > 32:
        fail('regional_encounters.offroad_bands', 'must be a list of at most 32 distance bands')
    previous = -1
    for index, row in enumerate(bands):
        path = 'regional_encounters.offroad_bands.'+str(index)
        band(row, path)
        if row.get('max_distance') is None:
            if index != len(bands)-1:
                fail(path, 'an open-ended distance band must be last')
        else:
            number(row, 'max_distance', path, 0, 1000000, required=True)
            if row['max_distance'] <= previous:
                fail(path, 'distance bands must increase strictly')
            previous = row['max_distance']
    pools = obj(encounters.get('pools', {}), 'regional_encounters.pools')
    for city, values in pools.items():
        if (not isinstance(values, list) or len(values) > 1024
                or any(not isinstance(value, str) for value in values) or len(set(values)) != len(values)):
            fail('regional_encounters.pools.'+city, 'must be a list of unique NPC identifiers')
        for value in values:
            reference(value, npcs, 'regional_encounters.pools.'+city)
            if isinstance(npcs, dict):
                template = npcs[value]
                if (template.get('regional_generated') is not True or template.get('spawn_managed') is not True
                        or template.get('zoo_exhibit')):
                    fail('regional_encounters.pools.'+city, 'requires an encounter template with regional_generated and spawn_managed enabled: '+value)
    retired = encounters.get('retired_templates', [])
    if not isinstance(retired, list) or any(not isinstance(value, str) for value in retired):
        fail('regional_encounters.retired_templates', 'must be a list of NPC identifiers')
    for ident in retired:
        reference(ident, npcs, 'regional_encounters.retired_templates')
        if any(ident in values for values in pools.values()):
            fail('regional_encounters.retired_templates', 'must not also occur in an active encounter pool')

    courts = block('city_courts')
    for city, row in courts.items():
        path = 'city_courts.'+city
        obj(row, path)
        for key in ('court', 'jail', 'release'):
            reference(row.get(key), rooms, path+'.'+key)
        for key in ('station', 'station_barracks', 'holding', 'prison', 'prison_gate'):
            if key in row:
                reference(row[key], rooms, path+'.'+key)
        reference(row.get('judge'), npcs, path+'.judge')
        text(row.get('authority'), path+'.authority')
        prison_rooms = row.get('prison_rooms', [])
        if not isinstance(prison_rooms, list):
            fail(path+'.prison_rooms', 'must be a list of room identifiers')
        for room in prison_rooms:
            reference(room, rooms, path+'.prison_rooms')
        if any(policy.get('custody') == 'prison' for policy in sentences.values()) and 'prison' not in row:
            fail(path+'.prison', 'is required by an authored prison sentence')

    for city, row in block('city_militaries').items():
        path = 'city_militaries.'+city
        obj(row, path)
        for key in ('base', 'parade', 'command', 'armory', 'infantry_barracks', 'ranged_barracks',
                    'support_barracks', 'infirmary', 'training', 'mess', 'stores'):
            if key in row:
                reference(row[key], rooms, path+'.'+key)
        text(row.get('authority'), path+'.authority')
        number(row, 'personnel', path, 0, 1000000)
        branches = obj(row.get('branches', {}), path+'.branches')
        for key in branches:
            number(branches, key, path+'.branches', 0, 1000000)
        if branches and row.get('personnel') != sum(branches.values()):
            fail(path+'.personnel', 'must equal the declared branch total')

    for city, row in block('regional_zoos').items():
        path = 'regional_zoos.'+city
        obj(row, path)
        reference(row.get('entrance'), rooms, path+'.entrance')
        displays = row.get('displays', [])
        if not isinstance(displays, list) or len(displays) > 10000:
            fail(path+'.displays', 'must be a bounded list of exhibits')
        seen = set()
        for entry in displays:
            obj(entry, path+'.displays')
            reference(entry.get('npc'), npcs, path+'.displays.npc')
            reference(entry.get('room'), rooms, path+'.displays.room')
            taxon = entry.get('taxon')
            text(taxon, path+'.displays.taxon')
            if isinstance(rooms, dict):
                gallery = rooms[entry['room']]
                if entry['npc'] not in gallery.get('zoo_exhibits', []):
                    fail(path+'.displays', 'the assigned gallery does not declare this exhibit: '+entry['npc'])
                if gallery.get('zoo_city') != city:
                    fail(path+'.displays', 'the assigned gallery must declare its matching zoo_city')
                text(gallery.get('zoo_habitat'), path+'.displays.zoo_habitat')
            if isinstance(npcs, dict):
                exhibit = npcs[entry['npc']]
                if (exhibit.get('zoo_exhibit') is not True or exhibit.get('spawn_managed') is not True
                        or exhibit.get('zoo_taxon') != taxon):
                    fail(path+'.displays', 'each managed exhibit needs zoo_exhibit and its matching zoo_taxon: '+entry['npc'])
            if taxon in seen:
                fail(path+'.displays', 'contains a duplicate taxon: '+taxon)
            seen.add(taxon)
        if row.get('display_count', len(displays)) != len(displays):
            fail(path+'.display_count', 'does not match its authored displays')
