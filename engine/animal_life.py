"""Local animal needs, authored flight limits and actual livestock recovery.

No animal is spawned here. Food comes from real inventory, floor supplies or a
shared harvest batch. All movement follows existing visible, permitted exits.
Flight describes how an animal uses those edges; it never creates an air route.
"""
from collections import deque
from copy import deepcopy
from hashlib import sha256
import math

from engine import living, worldtime

KEY = 'animal_life_v1'
ANIMALS = {'bird', 'fish', 'mammal', 'insect', 'arachnid', 'crustacean', 'reptile', 'mollusk'}
DEFAULTS = {'enabled': True, 'awake_start': 360, 'awake_minutes': 960, 'action_minutes': 5,
            'explore_minutes': 30, 'rest_minutes': 10, 'territory_steps': 3, 'habitats': []}
RANGES = (('awake_start', 0, 1499), ('awake_minutes', 1, 1500), ('action_minutes', 1, 60),
          ('explore_minutes', 1, 300), ('rest_minutes', 1, 120), ('territory_steps', 1, 6))
MAX_SEARCH = 64


def species(world, actor):
    if actor.is_player:
        return {}
    from engine import relationships
    if relationships.sentient(world, actor):
        return {}
    definition = world.npcs.get(actor.source_def, {})
    if str(definition.get('id', actor.source_def)).endswith('_carriage'):
        return {}
    from engine import spell_life
    profile = actor.progress.get('social_profile', {})
    authored = definition.get('social_profile', {})
    sid = profile.get('species') or definition.get('species') or authored.get('species')
    row = getattr(world, 'species', {}).get(sid, {})
    if (row.get('category') not in ANIMALS
            or profile.get('undead', authored.get('undead', False))
            or definition.get('creature_kind') == 'monster' or spell_life.magical(actor)):
        return {}
    return row


def config(world, actor):
    row = species(world, actor)
    if not row:
        return None
    raw = row.get('animal_behavior', {})
    if not isinstance(raw, dict) or raw.get('enabled', True) is not True:
        return None
    for key, low, high in RANGES:
        value = raw.get(key, DEFAULTS[key])
        if type(value) is not int or not low <= value <= high:return None
    habitats = raw.get('habitats', [])
    if (not isinstance(habitats, list) or len(habitats) > 8
            or any(not isinstance(value, str) or not value.strip() or len(value) > 40 for value in habitats)):
        return None
    return {**DEFAULTS, **raw}


def flight(world, actor):
    row = species(world, actor)
    raw = row.get('flight', {})
    if (row.get('category') != 'bird' or not isinstance(raw, dict)
            or raw.get('mode') not in ('short', 'sustained')
            or type(raw.get('endurance_steps')) is not int
            or not 1 <= raw['endurance_steps'] <= 256
            or type(raw.get('recovery_minutes')) is not int
            or not 1 <= raw['recovery_minutes'] <= worldtime.MINUTES_PER_DAY
            or type(raw.get('range_steps', 1)) is not int
            or not 1 <= raw.get('range_steps', 1) <= 16
            or raw.get('mode') == 'short' and (raw['endurance_steps'] > 4 or raw.get('range_steps', 1) > 2)):
        return {'mode': 'flightless', 'endurance_steps': 0, 'range_steps': 1, 'recovery_minutes': 0}
    return {**raw, 'range_steps': raw.get('range_steps', 1)}


def livestock(world, actor):
    raw = actor.progress.get('livestock') or world.npcs.get(actor.source_def, {}).get('livestock', {})
    if not raw and isinstance(actor.spawner_key, str):
        # Reused animal templates may belong to different real holdings. Only
        # this individual's actual authored spawner can supply its local owner.
        room_id, _, index = actor.spawner_key.rpartition(':')
        spawners = world.rooms[room_id].spawners if room_id in world.rooms else []
        if index.isdigit() and int(index) < len(spawners):
            spawner = spawners[int(index)]
            if spawner.get('npc') == actor.source_def:raw = spawner.get('livestock', {})
    if not isinstance(raw, dict) or not raw or raw.get('home') not in world.rooms:
        return None
    rooms = raw.get('rooms', [raw['home']])
    if (not isinstance(rooms, list) or not rooms or len(rooms) > 16
            or raw['home'] not in rooms or any(rid not in world.rooms for rid in rooms)
            or not isinstance(raw.get('owner'), str) or raw['owner'] not in world.npcs):
        return None
    return {**raw, 'rooms': rooms}


def owned(world, actor):
    return bool(actor.progress.get('companion_owner') or livestock(world, actor))


def inherit(world, parent, child):
    """A real birth retains its actual parent's authored livestock ownership."""
    cfg = livestock(world, parent)
    if cfg:
        child.progress['livestock'] = deepcopy(cfg)


def _now(world):
    return int(living.state(world)['minute'])


def _state(world, actor):
    now = _now(world)
    row = actor.progress.get(KEY)
    if row is None:
        meal = actor.progress.get('feeding', {}).get('last_meal')
        hunger = min(3000, max(0, now-meal)) if type(meal) is int else 0
        row = actor.progress.setdefault(KEY, {'minute': now, 'hunger_minutes': hunger,
              'last_action': now-DEFAULTS['action_minutes'], 'rest_until': 0,
              'flight_left': flight(world, actor)['endurance_steps'], 'last_escape_day': -1,
              'territory_home': actor.location, 'recent_rooms': [actor.location],
              'last_explore': now, 'explore_rest_until': 0})
    return row if isinstance(row, dict) else None


def _activity(actor, row, kind, reason):
    row['kind'] = kind;row['reason'] = reason
    row['last_action'] = row['minute']
    actor.activity = reason


def view(world, actor):
    """Read-only public action and reason; never expose keeper IDs or plans."""
    row = actor.progress.get(KEY)
    if not isinstance(row, dict) or not config(world, actor):
        return None
    return {'kind': row.get('kind', 'idle'), 'label': row.get('reason', 'Observing its surroundings')}


def _edge(world, actor, source, destination, *, flying=False):
    if source not in world.rooms or destination not in world.rooms:
        return False
    if world.rooms[destination].map_visibility == 'hidden':
        return False
    from engine import frontiers, regional_weather
    if flying and (regional_weather.indoor(living.details(world, source))
                   or regional_weather.indoor(living.details(world, destination))):
        return False
    return any(target == destination and not frontiers.blocked(world, source, direction, actor)
               for direction, target in world.rooms[source].exits.items())


def _path(world, actor, destinations, *, radius=1, allowed=None, flying=False):
    queue = deque([(actor.location, [])]);seen = {actor.location}
    while queue and len(seen) <= MAX_SEARCH:
        here, path = queue.popleft()
        if path and here in destinations:
            return path
        if len(path) >= radius:
            continue
        for target in world.rooms[here].exits.values():
            if target in seen or allowed is not None and target not in allowed:
                continue
            if _edge(world, actor, here, target, flying=flying):
                seen.add(target);queue.append((target, path+[target]))
                if len(seen) >= MAX_SEARCH:
                    break
    return None


def _move(world, actor, row, destination, *, flying=False, reason='foraging for nearby food'):
    if not _edge(world, actor, actor.location, destination, flying=flying):
        return False
    if flying and row.get('flight_left', 0) <= 0:
        return False
    if not world.move_entity(actor.id, destination):
        return False
    recent = row.get('recent_rooms', [])
    row['recent_rooms'] = ([rid for rid in recent if isinstance(rid, str)] + [destination])[-16:] if isinstance(recent, list) else [destination]
    if flying:
        row['flight_left'] -= 1
        row['last_flight'] = _now(world)
        reason = 'travelling by flight; '+reason
        if row['flight_left'] == 0:
            row['rest_until'] = _now(world)+flight(world, actor)['recovery_minutes']
    row['last_action'] = _now(world)
    _activity(actor, row, 'walk', reason)
    return True


def _edible(world, actor, iid):
    row = species(world, actor);item = world.items.get(iid, {})
    allowed = {'plant'} if row.get('consumption') == 'herbivore' else {'animal'} if row.get('consumption') == 'carnivore' else {'plant', 'animal'}
    return iid in row.get('diet', []) and item.get('food_origin') in allowed


def _resources(world, rid):
    from engine import resource_nodes
    return [getattr(world, 'resources', {}).get(ident, {}) for ident in resource_nodes.active_resources(world, rid)]


def _food_here(world, actor, rid):
    from engine import ecology, geology_impacts, resource_nodes
    if geology_impacts.room_unusable(world, rid):
        return False
    if any(_edible(world, actor, iid) for iid in world.rooms[rid].items):
        return True
    return any(any(_edible(world, actor, iid) for iid in resource.get('yields', {}))
               and not resource.get('tool') and ecology.in_season(world, resource, rid)
               and not geology_impacts.resource_blocked(world, rid, resource.get('id'))
               and resource_nodes.available(world, rid, resource) for resource in _resources(world, rid))


def _eat(world, actor, row):
    from engine import ecology, geology_impacts, resource_nodes, society
    here = actor.location
    if geology_impacts.room_unusable(world, here):
        return False
    for source in (actor.inventory, world.rooms[here].items):
        meal = next((iid for iid in source if _edible(world, actor, iid)
                     and iid not in actor.equipped.values()), None)
        if meal:
            source.remove(meal);break
    else:
        meal = None
        if 'husbandry' in living.details(world, here).get('facilities', []):
            shop = society.economy(world)['shops'].get(here, {})
            meal = next((iid for iid, count in shop.get('stock', {}).items()
                         if count > 0 and _edible(world, actor, iid)), None)
            if meal:
                shop['stock'][meal] -= 1
        if not meal:
            for resource in _resources(world, here):
                meal = next((iid for iid in resource.get('yields', {}) if _edible(world, actor, iid)), None)
                yields = resource.get('yields', {})
                valid = bool(yields) and all(iid in world.items and type(count) is int and 1 <= count <= 10000 for iid, count in yields.items()) and sum(yields.values()) <= 10000
                if (not meal or resource.get('tool') or not ecology.in_season(world, resource, here)
                        or not valid
                        or geology_impacts.resource_blocked(world, here, resource.get('id'))
                        or not resource_nodes.harvest(world, here, resource, actor)):
                    meal = None;continue
                # A shared real batch was consumed. Leave unconsumed yields on
                # the ground, so animal feeding never duplicates player stock.
                for iid, count in resource.get('yields', {}).items():
                    if iid in world.items and type(count) is int and count > 0:
                        world.rooms[here].items.extend([iid]*count)
                world.rooms[here].items.remove(meal)
                break
        if not meal:
            return False
    actor.progress.setdefault('feeding', {})['last_meal'] = _now(world)
    row['hunger_minutes'] = 0;row['last_action'] = _now(world)
    stats = living.state(world).setdefault('wildlife', {'last': -1, 'forage': {}, 'meals': 0, 'hunts': 0})
    stats['meals'] = stats.get('meals', 0)+1
    _activity(actor, row, 'meal', 'feeding on available food')
    return True


def _hunt(world, actor, row, spec):
    if (not world.metadata.get('wildlife_ecology') or owned(world, actor)
            or actor.progress.get('zoo_exhibit') or living.details(world, actor.location).get('truce')
            or 'husbandry' in living.details(world, actor.location).get('facilities', [])):
        return False
    prey = next((person for person in world.entities_in_room(actor.location)
                 if person is not actor and person.alive and not person.is_player and not owned(world, person)
                 and not person.progress.get('zoo_exhibit')
                 and species(world, person)
                 and species(world, person).get('id') in spec.get('prey_species', [])), None)
    if prey is None:
        return False
    from engine import combat
    text = combat.strike(world, actor, prey, counter=True)
    world.runtime_notifications = (getattr(world, 'runtime_notifications', [])+[(actor.location, text)])[-500:]
    row['last_action'] = _now(world);_activity(actor, row, 'hunt', 'hunting nearby wild prey')
    if not prey.alive:
        if not prey.progress.get('wildlife_drops_released'):
            prey.progress['wildlife_drops_released'] = True
            if not prey.progress.get('combat_drops_distributed'):
                world.rooms[actor.location].items.extend(iid for iid in world.npcs.get(prey.source_def, {}).get('drops', []) if iid in world.items)
        if _eat(world, actor, row):
            living.state(world)['wildlife']['hunts'] += 1
    return True


def _shelter(world, actor):
    from engine import regional_weather
    rd = living.details(world, actor.location)
    return regional_weather.indoor(rd) or rd.get('animal_shelter') is True


def _weather_bad(world, actor):
    from engine import climate
    weather = climate.conditions(world, actor.location)
    return weather.get('weather') in ('rain', 'snow', 'thunderstorm', 'severe thunderstorm', 'tornado') or weather.get('wind_kph', 0) >= 40


def _escape(world, actor, row, cfg):
    day = _now(world)//worldtime.MINUTES_PER_DAY
    if day <= row.get('last_escape_day', -1):
        return False
    row['last_escape_day'] = day
    chance = cfg.get('escape_chance', 0)
    if type(chance) not in (int, float) or not 0 < chance <= .25:
        return False
    draw = int.from_bytes(sha256((actor.id+':'+str(day)+':escape').encode()).digest()[:8], 'big')/2**64
    if draw >= chance:
        return False
    target = next((target for target in world.rooms[actor.location].exits.values()
                   if target not in cfg['rooms'] and _edge(world, actor, actor.location, target)), None)
    if target and _move(world, actor, row, target, reason='strayed through an open enclosure exit'):
        row['strayed'] = True
        return True
    return False


def _habitat(world, room):
    data = living.details(world, room)
    return str(data.get('climate', {}).get('terrain') or data.get('environment') or '').casefold()


def _explore(world, actor, row, cfg, *, hungry, flying):
    """Explore one actual neighboring habitat, then rest; never use a world index.

    A fixed small home range and recent-room memory keep an adult wild animal
    moving purposefully without sending it on an unbounded random walk.
    """
    now = _now(world)
    if now-row.setdefault('last_explore', now) < cfg['explore_minutes']:
        return False
    from engine import relationships, regional_weather
    profile = relationships.profile(world, actor)
    if profile['age_years'] < profile['maturity_years']:
        return False
    origin = row.setdefault('territory_home', actor.location)
    if origin not in world.rooms:
        return False
    habitats = {value.casefold() for value in cfg['habitats']} or {_habitat(world, origin)}
    aquatic = species(world, actor).get('category') == 'fish'
    water = {'water', 'river', 'lake', 'ocean', 'sea', 'stream'}

    def suitable(rid):
        data = living.details(world, rid);habitat = _habitat(world, rid)
        return (not regional_weather.indoor(data) and habitat in habitats
                and (habitat in water) == aquatic and 'husbandry' not in data.get('facilities', []))

    # Only the immediate habitat around the animal's actual first location is
    # considered. Six edges and 64 rooms are hard limits even on authored maps.
    territory = {origin};queue = deque([(origin, 0)])
    while queue and len(territory) < MAX_SEARCH:
        here, depth = queue.popleft()
        if depth >= cfg['territory_steps']:continue
        for dest in world.rooms[here].exits.values():
            if dest in territory or dest not in world.rooms or not suitable(dest):continue
            if _edge(world, actor, here, dest, flying=flying):
                territory.add(dest);queue.append((dest, depth+1))
                if len(territory) >= MAX_SEARCH:break
    candidates = [dest for dest in world.rooms[actor.location].exits.values()
                  if dest in territory and suitable(dest) and _edge(world, actor, actor.location, dest, flying=flying)]
    row['last_explore'] = now  # No repeated attempts or elapsed-clock replay.
    if not candidates:return False
    recent = row.get('recent_rooms', [])
    recent = recent if isinstance(recent, list) else []
    def priority(rid):
        visited = max((index for index, value in enumerate(recent) if value == rid), default=-1)
        return visited, sha256((actor.id+':'+rid).encode()).digest()
    destination = min(candidates, key=priority)
    reason = 'searching another part of its habitat for food' if hungry else 'checking its nearby habitat before resting'
    if not _move(world, actor, row, destination, flying=flying, reason=reason):return False
    row['explore_rest_until'] = now+cfg['rest_minutes']
    return True


def step(world, actor):
    """One bounded animal decision per authorized game minute; no elapsed replay."""
    cfg = config(world, actor)
    if not living.enabled(world) or not cfg or not actor.alive or actor.location not in world.rooms:
        return False
    row = _state(world, actor)
    now = _now(world)
    if row is None or any(type(row.get(key)) is not int for key in ('minute', 'hunger_minutes', 'last_action', 'rest_until', 'flight_left', 'last_escape_day')) or now < row['minute']:
        return True
    if row.get('processed') == now:
        return True
    elapsed = min(worldtime.MINUTES_PER_DAY, now-row['minute'])
    row['minute'] = now;row['processed'] = now
    row['hunger_minutes'] = min(3000, row.get('hunger_minutes', 0)+elapsed)
    from engine import npc_attention, community_quests, sleep_movement
    if npc_attention.paused(world, actor) or community_quests.frozen(world, actor):
        _activity(actor, row, 'idle', 'waiting during handling or an assigned herd task');return True
    if sleep_movement.asleep(world, actor) and not row.get('sleeping'):
        _activity(actor, row, 'sleep', 'sleeping after being settled here');return True
    spec = species(world, actor);penned = livestock(world, actor)
    exhibit = actor.progress.get('zoo_exhibit');fly = flight(world, actor)
    row['flight_left'] = min(max(0, row['flight_left']), fly['endurance_steps'])
    awake = (now-cfg['awake_start']) % worldtime.MINUTES_PER_DAY < cfg['awake_minutes']
    if not awake:
        row['sleeping'] = True
        row['flight_left'] = min(fly['endurance_steps'], row.get('flight_left', 0)+elapsed)
        _activity(actor, row, 'sleep', 'sleeping in its enclosure' if penned or exhibit else 'sleeping in shelter' if _shelter(world, actor) else 'sleeping at its resting place')
        return True
    if row.pop('sleeping', False):
        actor.activity = 'awake';row['kind'] = 'idle';row['reason'] = 'awake and observing its surroundings'
    if actor.progress.get('companion_owner'):
        from engine import companions
        before = actor.location;companions.follow(world, actor)
        _activity(actor, row, 'walk' if actor.location != before else 'idle',
                  'following its caregiver' if actor.location != before else 'waiting with its caregiver' if actor.progress.get('companion_order', 'follow') == 'follow' else 'waiting on its caregiver’s stay order')
        if row['hunger_minutes'] >= species(world, actor).get('feeding_interval', 180):
            _eat(world, actor, row)
        return True
    hungry = row['hunger_minutes'] >= spec.get('feeding_interval', 180)
    if hungry and _eat(world, actor, row):
        return True
    if row.get('rest_until', 0) > now:
        _activity(actor, row, 'rest', 'resting its wings after reaching its flight limit');return True
    if row.get('rest_until', 0):
        row['flight_left'] = fly['endurance_steps'];row['rest_until'] = 0
    elif type(row.get('last_flight')) is int and now-row['last_flight'] >= fly['recovery_minutes']:
        row['flight_left'] = fly['endurance_steps']
    if now-row.get('last_action', now) < cfg['action_minutes']:
        return True
    allowed = set(penned['rooms']) if penned and actor.location in penned['rooms'] else None
    if exhibit:
        _activity(actor, row, 'harvest' if hungry else 'rest', 'searching its protected enclosure for food' if hungry else 'resting in its protected enclosure');return True
    if _weather_bad(world, actor):
        if _shelter(world, actor):
            _activity(actor, row, 'rest', 'sheltering from the weather');return True
        shelters = {rid for rid in world.rooms[actor.location].exits.values() if rid in world.rooms
                    and (living.details(world, rid).get('animal_shelter') is True
                         or rid in (penned or {}).get('rooms', []) and living.details(world, rid).get('environment') in ('inside', 'indoor', 'indoors'))}
        path = _path(world, actor, shelters, allowed=allowed)
        if path and _move(world, actor, row, path[0], reason='seeking nearby shelter'):
            return True
        _activity(actor, row, 'rest', 'hunkering down; no accessible shelter nearby');return True
    if penned:
        if actor.location not in penned['rooms']:
            _activity(actor, row, 'idle', 'strayed from its enclosure; waiting for its keeper');return True
        if _escape(world, actor, row, penned):
            return True
    elif type(row.get('explore_rest_until')) is int and row['explore_rest_until'] > now:
        _activity(actor, row, 'rest', 'resting after exploring its nearby habitat');return True
    flying = fly['mode'] != 'flightless' and row.get('flight_left', 0) > 0
    if hungry:
        if _hunt(world, actor, row, spec):
            return True
        radius = min(fly['range_steps'], row.get('flight_left', 0)) if flying else 1
        # Search only a bounded neighborhood, never a global food directory.
        queue = deque([(actor.location, 0)]);seen = {actor.location};food = set()
        while queue and len(seen) < MAX_SEARCH:
            here, depth = queue.popleft()
            if here != actor.location and _food_here(world, actor, here):food.add(here)
            if depth >= radius:continue
            for dest in world.rooms[here].exits.values():
                if dest not in seen and (allowed is None or dest in allowed) and _edge(world, actor, here, dest, flying=flying):
                    seen.add(dest);queue.append((dest, depth+1))
                    if len(seen) >= MAX_SEARCH:break
        path = _path(world, actor, food, radius=radius, allowed=allowed, flying=flying)
        if path and _move(world, actor, row, path[0], flying=flying):return True
        if not penned and _explore(world, actor, row, cfg, hungry=True, flying=flying):return True
        _activity(actor, row, 'harvest', 'foraging in its enclosure; no accessible food yet' if penned else 'foraging; no accessible food nearby')
    else:
        if not penned and _explore(world, actor, row, cfg, hungry=False, flying=flying):return True
        _activity(actor, row, 'rest', 'resting in its enclosure; food is not yet needed' if penned else 'resting and watching its surroundings; food is not yet needed')
    return True


def advance(world, *, stepped_entities=()):
    if not living.enabled(world):return
    # The ordinary living loop already visits its current actors. Preserve the
    # standalone wildlife entry point and handle later spawns, without repeating
    # species/configuration checks for every resident in the same tick. Compare
    # actual objects so replacing an entity with the same saved ID is safe.
    seen={actor.id:actor for actor in stepped_entities}
    for actor in list(world.entities.values()):
        if seen.get(actor.id) is not actor:step(world, actor)


def _keepers(world):
    now = _now(world)
    stamp, by_owner = getattr(world, '_animal_keepers', (None, {}))
    if stamp != now:
        by_source = {};by_owner = {}
        for person in world.entities.values():
            if person.alive and not person.is_player:by_source.setdefault(person.source_def, []).append(person)
        for animal in world.entities.values():
            cfg = livestock(world, animal)
            if not cfg or not animal.alive or not config(world, animal):continue
            keepers = by_source.get(cfg['owner'], [])
            if len(keepers) == 1:by_owner.setdefault(keepers[0].id, []).append(animal.id)
        world._animal_keepers = (now, by_owner)
    return by_owner


def is_keeper(world, actor):
    return actor.id in _keepers(world)


def owner_step(world, owner):
    """A real keeper can recover one actual, nearby owned stray over open edges."""
    if owner.is_player or not owner.alive:return False
    now = _now(world)
    last = owner.progress.get('animal_keeper_v1', {}).get('minute')
    if type(last) is int and now <= last:return False
    from engine import city_justice, npc_attention, sleep_movement, community_quests, relationships
    if (owner.progress.get('restrained_until', 0) > now or city_justice.confined(world, owner)
            or npc_attention.paused(world, owner) or sleep_movement.asleep(world, owner)
            or community_quests.frozen(world, owner) or not relationships.sentient(world, owner)):return False
    by_owner = _keepers(world)
    for ident in by_owner.get(owner.id, []):
        animal = world.entities.get(ident)
        if not animal or not animal.alive or animal.progress.get('companion_owner'):continue
        cfg = livestock(world, animal);row = _state(world, animal)
        if not cfg or row is None or animal.location in cfg['rooms']:continue
        # Seeing the actual animal here or through an ordinary open neighboring
        # edge is required. Its saved ID does not reveal a distant position.
        if owner.location != animal.location:
            if _edge(world, owner, owner.location, animal.location) and world.move_entity(owner.id, animal.location):
                owner.progress['animal_keeper_v1'] = {'minute': now}
                owner.activity = 'approaching a nearby stray from the owned herd';return True
            continue
        if npc_attention.paused(world, animal) or community_quests.frozen(world, animal) or sleep_movement.asleep(world, animal):continue
        destinations = {rid for rid in cfg['rooms'] if _edge(world, animal, animal.location, rid) and _edge(world, owner, owner.location, rid)}
        if not destinations:continue
        destination = cfg['home'] if cfg['home'] in destinations else sorted(destinations)[0]
        if world.move_entity(owner.id, destination) and world.move_entity(animal.id, destination):
            owner.progress['animal_keeper_v1'] = {'minute': now}
            row['strayed'] = False;row['last_action'] = now;row['processed'] = now;row['minute'] = now
            owner.activity = 'returning an owned stray to its enclosure'
            _activity(animal, row, 'walk', 'being led back to its enclosure')
            from engine import task_skills
            task_skills.practice(world,owner,'ranching',event_id=f'herd:{animal.id}:{now}')
            return True
    return False


def validate(data):
    issues = [];rooms = {r['id'] for r in data.get('room', [])};npcs = {n['id'] for n in data.get('npc', [])}
    for spec in data.get('species', []):
        cfg = spec.get('animal_behavior', {})
        if not isinstance(cfg, dict) or set(cfg)-set(DEFAULTS):
            issues.append(spec['id']+': invalid animal_behavior object')
        else:
            if 'enabled' in cfg and type(cfg['enabled']) is not bool:issues.append(spec['id']+': animal enabled must be boolean')
            for key, low, high in RANGES:
                if key in cfg and (type(cfg[key]) is not int or not low <= cfg[key] <= high):issues.append(spec['id']+': invalid '+key)
            habitats = cfg.get('habitats', [])
            if not isinstance(habitats, list) or len(habitats) > 8 or any(not isinstance(value, str) or not value.strip() or len(value) > 40 for value in habitats):
                issues.append(spec['id']+': habitats must list at most 8 terrain or environment names')
        cfg = spec.get('flight', {})
        if not isinstance(cfg, dict):issues.append(spec['id']+': flight must be an object');continue
        if not cfg:continue
        if set(cfg)-{'mode', 'endurance_steps', 'recovery_minutes', 'range_steps'} or cfg.get('mode') not in ('flightless', 'short', 'sustained'):
            issues.append(spec['id']+': invalid flight profile');continue
        if cfg['mode'] != 'flightless':
            if spec.get('category') != 'bird':issues.append(spec['id']+': flight profile requires bird category')
            for key, high in (('endurance_steps', 256), ('recovery_minutes', 1500), ('range_steps', 16)):
                val = cfg.get(key, 1 if key == 'range_steps' else None)
                if type(val) is not int or not 1 <= val <= high:issues.append(spec['id']+': invalid flight '+key)
            if cfg['mode'] == 'short' and (type(cfg.get('endurance_steps')) is int and cfg['endurance_steps'] > 4 or type(cfg.get('range_steps', 1)) is int and cfg.get('range_steps', 1) > 2):
                issues.append(spec['id']+': short flight is limited to 4 endurance steps and 2 range steps')
    def holding(label,cfg):
        if not isinstance(cfg, dict):issues.append(label+': livestock must be an object');return
        if not cfg:return
        if set(cfg)-{'owner', 'home', 'rooms', 'escape_chance'}:issues.append(label+': unknown livestock field')
        if cfg.get('owner') not in npcs:issues.append(label+': livestock owner NPC is missing')
        if cfg.get('home') not in rooms:issues.append(label+': livestock home room is missing')
        allowed = cfg.get('rooms', [cfg.get('home')])
        if not isinstance(allowed, list) or not 1 <= len(allowed) <= 16 or any(rid not in rooms for rid in allowed) or cfg.get('home') not in allowed:
            issues.append(label+': livestock rooms must include home and at most 16 real rooms')
        chance = cfg.get('escape_chance', 0)
        if type(chance) not in (int, float) or not math.isfinite(chance) or not 0 <= chance <= .25:
            issues.append(label+': escape_chance must be 0–0.25 per day')
    for room in data.get('room', []):
        if 'animal_shelter' in room and type(room['animal_shelter']) is not bool:issues.append(room['id']+': animal_shelter must be boolean')
        for index,spawner in enumerate(room.get('spawners', [])):
            holding(room['id']+':spawner:'+str(index),spawner.get('livestock', {}))
    for npc in data.get('npc', []):holding(npc['id'],npc.get('livestock', {}))
    return issues
