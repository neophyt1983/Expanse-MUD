"""Weak countryside encounters bounded by geography, observers and game time."""
import random
from hashlib import sha256
from engine import living, regional_world

KEY = 'regional_encounters_v1'
REVISION = 2
# Gameplay values and creature pools belong to world-rules.json and npcs.json.
# Limits here bound computational work and malformed inputs, not world content.
def config(w):
    value = getattr(w, 'rules', {}).get('regional_encounters', {})
    return value if isinstance(value, dict) else {}


def setting(w, name, fallback):
    return config(w).get(name, fallback)


def state(w):
    s = living.state(w).setdefault(KEY, {})
    for name, default in (('last', -1), ('checks', {}), ('observer_checks', {}),
                          ('cooldowns', {}), ('spawned', 0), ('npc_cursor', 0)):
        s.setdefault(name, default)
    if s.get('revision') != REVISION:
        s['checks'] = {}  # Old checks used player IDs; new checks share one room budget.
        s['observer_checks'] = {}
        s['revision'] = REVISION
    return s


def install(w):
    """Creature definitions are authored records; loading never creates them."""
    return None


def policy(w, room, *, _refuges=None):
    """One geography-based roll per observed location, not per character."""
    from engine import encounter_geography, starter_safety
    refuges = starter_safety.all_rooms(w) if _refuges is None else _refuges
    if room in refuges:
        return None
    area = encounter_geography.describe(w, room)
    if not area or area['zone'] not in ('road', 'outdoor'):
        return None
    cfg = config(w)
    if cfg.get('enabled') is not True:
        return None
    distance = area.get('distance')
    if area['zone'] == 'road':
        band = cfg.get('road', {})
    elif distance is None:
        band = cfg.get('unknown_distance', {})
    else:
        band = next((row for row in cfg.get('offroad_bands', [])
                     if row.get('max_distance') is None or distance <= row['max_distance']), {})
    chance, cap = band.get('chance', 0), band.get('local_cap', 0)
    if not chance or not cap:
        return None
    return {**area, 'chance': chance, 'interval': max(1, cfg.get('check_interval_minutes', 6)),
            'local_cap': cap}


def zone(w, room):
    area = policy(w, room)
    return area['zone'] if area else None


def nearby(w, source, reach=2):
    if source not in w.rooms:
        return set()
    found, frontier = {source}, {source}
    for _ in range(reach):
        new = {dest for rid in frontier for dest in w.rooms[rid].exits.values() if dest in w.rooms} - found
        found.update(new)
        frontier = new
        if not frontier:
            break
    return found


def managed(w, actor):
    return bool(not actor.is_player and actor.progress.get('regional_encounter')
                and w.npcs.get(actor.source_def, {}).get('regional_generated')
                and not actor.progress.get('zoo_exhibit') and not actor.progress.get('companion_owner'))


def reconcile(w):
    """Migrate only temporary generated threats, in memory, without kill rewards."""
    disabled = regional_world.config(w, 'encounters', True) is False
    from engine.commands import _remove_entity
    for actor in list(w.entities.values()):
        if not actor.alive or not managed(w, actor):
            continue
        record = actor.progress['regional_encounter']
        area = None if disabled else policy(w, actor.location)
        if not area or record.get('zone') != area['zone']:
            if actor.location in w.rooms:
                _remove_entity(w, w.rooms[actor.location], actor.id)
            else:
                w.entities.pop(actor.id, None)
            continue
        if record.get('revision') != REVISION:
            definition = w.npcs[actor.source_def]
            # Cap old stats without healing any wounds or undoing a debuff.
            actor.max_hp = min(actor.max_hp, definition['hp'])
            actor.hp = min(actor.hp, actor.max_hp)
            actor.attack = min(actor.attack, definition['attack'])
            actor.defense = min(actor.defense, definition['defense'])
            record['revision'] = REVISION
            record['next_attack'] = max(record.get('next_attack', 0), int(living.state(w)['minute'])+setting(w,'attack_grace_minutes',2))


def occupied(w, room):
    from engine import relationships
    return any(e.alive and (e.is_player or relationships.sentient(w, e)) for e in w.entities_in_room(room))


def template_city(w, area, fallback=None):
    """Unknown disconnected terrain uses a known weak habitat pool, not a tier boost."""
    if area.get('city'):
        return area['city']
    rows = sorted(regional_world.cities(w), key=lambda row: row['name'])
    if fallback and fallback in rows:
        return fallback
    return next((city for city in rows
                 if living.details(w, city['home']).get('climate', {}).get('terrain') == area.get('habitat')),
                rows[0] if rows else None)


def spawn(w, room, city, which, now, *, rng=random.random):
    """Appear off the observer's tile, with a warning and a later attack clock."""
    area = policy(w, room)
    if not area or area['zone'] != which or occupied(w, room):
        return None
    city = template_city(w, area, city)
    if not city:
        return None
    s = state(w)
    if now < s['cooldowns'].get(room, -1):
        return None
    local = nearby(w, room)
    if sum(bool(e.alive and managed(w, e)) for rid in local for e in w.entities_in_room(rid)) >= area['local_cap']:
        return None
    pool = [ident for ident in config(w).get('pools', {}).get(city['name'], [])
            if ident in w.npcs and w.npcs[ident].get('regional_generated')
            and not w.npcs[ident].get('zoo_exhibit')]
    if not pool:
        return None
    ident = pool[min(len(pool)-1, int(max(0, min(.99999, rng()))*len(pool)))]
    from engine.commands import _spawn_npc_instance
    actor = _spawn_npc_instance(w, w.rooms[room], ident, spawner_key='regional:'+room+':'+str(now))
    if not actor:
        return None
    actor.progress['regional_encounter'] = dict(city=city['name'], zone=which, home=room,
        spawned=now, next_move=now+setting(w,'first_move_minutes',3),
        next_attack=now+setting(w,'attack_grace_minutes',2), revision=REVISION)
    actor.activity = 'prowling nearby'
    s['cooldowns'][room] = now + setting(w, 'road_respawn_minutes' if which == 'road' else 'offroad_respawn_minutes', 60)
    s['spawned'] += 1
    text = actor.name+' emerges near '+w.rooms[room].name+'. Its movements look dangerous.'
    w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(rid, text) for rid in local])[-500:]
    from engine import encounter_stories
    encounter_stories.observe(w, actor)
    return actor


def npc_observers(w, s):
    """Rotate a small budget through actual awake countryside travelers."""
    from engine import relationships, sleep_movement, livelihoods, starter_safety
    prior = getattr(w, '_regional_npc_positions', {})
    positions, travelers = {}, []
    # Reading the job ledger must not execute assignment(), which advances work.
    fieldworkers = set()
    jobs = getattr(w, 'living_state', {}).get('community_jobs', {}).get('jobs', {})
    for job in jobs.values():
        if job.get('status') == 'active':
            fieldworkers.update(key for key in (job.get('worker'), job.get('cover')) if key)
            if job.get('bound'):
                fieldworkers.update(job.get('targets', []))
    verbs = ('travelling', 'traveling', 'walking', 'patrolling', 'exploring', 'gathering', 'hunting', 'delivering')
    # Selection only reads geography. Share these derived answers within this
    # pass, then discard them before encounters can move or spawn anything.
    refuges, areas = None, {}
    geography = getattr(w, '_encounter_geography', None)
    for actor in w.entities.values():
        if (not actor.alive or actor.is_player or actor.progress.get('companion_owner')
                or actor.progress.get('zoo_exhibit') or actor.progress.get('court_case')
                or not relationships.sentient(w, actor) or sleep_movement.asleep(w, actor)
                or not livelihoods.awake(w, actor)):
            continue
        positions[actor.id] = actor.location
        moving = prior.get(actor.id, actor.location) != actor.location
        fieldwork = actor.id in fieldworkers
        if not (moving or fieldwork or any(verb in str(getattr(actor, 'activity', '')).casefold() for verb in verbs)):
            continue
        if refuges is None:
            refuges = starter_safety.all_rooms(w)
        if actor.location not in areas:
            area = policy(w, actor.location, _refuges=refuges)
            current_geography = getattr(w, '_encounter_geography', None)
            if current_geography is not geography:
                # A lazy topology audit can rebuild distances during this pass.
                areas.clear()
                geography = current_geography
            areas[actor.location] = area
        if areas[actor.location]:
            travelers.append(actor)
    w._regional_npc_positions = positions  # Ephemeral; no persisted position history.
    if not travelers:
        return [], []
    travelers.sort(key=lambda actor: actor.id)
    cursor = int(s['npc_cursor']) % len(travelers)
    selected = [travelers[(cursor+i) % len(travelers)] for i in range(min(min(64, max(1, setting(w,'npc_observer_budget',8))), len(travelers)))]
    s['npc_cursor'] = (cursor+len(selected)) % len(travelers)
    return selected, travelers


def advance(w, rng=random.random):
    reconcile(w)
    if regional_world.config(w, 'encounters', True) is False:
        return
    s = state(w)
    now = int(living.state(w)['minute'])
    if s['last'] == now:
        return
    s['last'] = now
    actors = [e for e in w.entities.values() if e.alive and managed(w, e)]
    players = [e for e in w.entities.values() if e.is_player and e.alive]
    selected, travelers = npc_observers(w, s)
    locations = {}
    for observer in players[:128]+selected:
        locations.setdefault(observer.location, []).append(observer)
    relevant_rooms = {e.location for e in players+travelers}
    try:
        cap = max(1, min(64, int(setting(w, 'max_active', 24))))
    except (TypeError, ValueError):
        cap = 24
    for location, present in locations.items():
        area = policy(w, location)
        if area is None:
            for observer in present:
                s['observer_checks'].pop(observer.id, None)
            continue
        if len(actors) >= cap:
            continue
        for observer in present:
            s['observer_checks'].setdefault(observer.id, now+area['interval'])
        if not any(s['observer_checks'][observer.id] <= now for observer in present):
            continue
        old = s['checks'].get(location)
        if old is not None and now-old < area['interval']:
            continue
        # A candidate-centered cap alone can put one threat on each side of
        # the same traveler. Apply the origin's nearby spawn budget as well.
        local = nearby(w, location)
        if sum(actor.alive and actor.location in local for actor in actors) >= area['local_cap']:
            continue
        s['checks'][location] = now
        # Readiness follows a moving traveler, while the location clock prevents
        # a crowd or successive arrivals from multiplying the roll frequency.
        for observer in present:
            s['observer_checks'][observer.id] = now+area['interval']
        if rng() >= area['chance']:
            continue
        places = sorted(rid for rid in nearby(w, location)
                        if rid != location and zone(w, rid) == area['zone'] and not occupied(w, rid))
        if places:
            offset = int.from_bytes(sha256((location+str(now)).encode()).digest()[:2], 'big') % len(places)
            actor = spawn(w, places[offset], area.get('city'), area['zone'], now, rng=rng)
            if actor:
                actors.append(actor)
    targeted = set()
    from engine import frontiers, combat, relationships, encounter_stories
    for actor in actors:
        rec = actor.progress['regional_encounter']
        if not actor.alive or actor.id not in w.entities:
            continue
        close = nearby(w, actor.location, 5)
        if now-rec['spawned'] >= setting(w,'despawn_after_minutes',60) and not relevant_rooms & close:
            from engine.commands import _remove_entity
            encounter_stories.departed(w, actor)
            _remove_entity(w, w.rooms[actor.location], actor.id)
            continue
        if zone(w, actor.location) != rec['zone']:
            continue
        victims = [e for e in w.entities_in_room(actor.location) if e.id != actor.id and e.id not in targeted
                   and e.alive and (e.is_player or (relationships.sentient(w, e) and not e.progress.get('zoo_exhibit')))]
        if victims and now >= rec.get('next_attack', now):
            rec['next_attack'] = now+setting(w,'attack_interval_minutes',5)
            target = sorted(victims, key=lambda e: (not e.is_player, e.id))[0]
            try:
                combat.validate(w, actor, target)
                text = combat.strike(w, actor, target, counter=True)
            except ValueError:
                continue
            targeted.add(target.id)
            w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(actor.location, text)])[-500:]
        elif now >= rec.get('next_move', now):
            rec['next_move'] = now+setting(w,'move_interval_minutes',4)
            home = nearby(w, rec['home'], setting(w,'pursuit_radius',3))
            places = [(di, rid) for di, rid in w.rooms[actor.location].exits.items()
                      if zone(w, rid) == rec['zone'] and rid in home
                      and not frontiers.blocked(w, actor.location, di, actor)]
            if places and rng() < setting(w,'move_chance',.6):
                _, destination = places[min(len(places)-1, int(max(0, min(.99999, rng()))*len(places)))]
                if w.move_entity(actor.id, destination):
                    rec['next_attack'] = max(rec['next_attack'], now+setting(w,'attack_grace_minutes',2))
                    encounter_stories.observe(w, actor)
    s['checks'] = dict(sorted(((key, value) for key, value in s['checks'].items()
                              if now-value <= 360), key=lambda pair: pair[1], reverse=True)[:512])
    s['observer_checks'] = dict(sorted(((key, value) for key, value in s['observer_checks'].items()
                                       if key in w.entities and now-value <= 360),
                                      key=lambda pair: pair[1], reverse=True)[:512])
    if len(s['cooldowns']) > 256:
        s['cooldowns'] = {key: value for key, value in s['cooldowns'].items() if value > now}
