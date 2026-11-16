"""Mortal city watches responding to actual assaults, including gate approaches.

Alarms name an observed act, never a faction score. Officers travel over real
open exits; route searches continue within a shared per-tick work budget.
Only an explicit save persists the ordinary living-state records used here.
"""
from collections import deque
import math
import random
import re
from engine import living, regional_world

KEY = 'city_defense_v1'
def settings(w):
    value = getattr(w, 'rules', {}).get('city_defense', {})
    return value if isinstance(value, dict) else {}


def number(w, field, default, low, high):
    value = settings(w).get(field, default)
    return max(low, min(high, value)) if type(value) is int else default


def _stat_floors(w):
    stats = settings(w).get('guard_stats', {})
    if not isinstance(stats, dict):
        return {}
    return {field: value for field, value in stats.items()
            if field in ('hp', 'attack', 'defense') and type(value) is int and 0 < value <= 1000000}


def military_settings(w):
    value = settings(w).get('military_support', {})
    return value if isinstance(value, dict) else {}


def _military_number(w, field, default, low, high):
    value = military_settings(w).get(field, default)
    return max(low, min(high, value)) if type(value) is int else default


def enabled(w):
    return regional_world.enabled(w) and settings(w).get('enabled') is True


def _guard_definition(w, d):
    if 'city_guard' in d:
        return d['city_guard'] is True
    if any(d.get(field) == 'guard' for field in ('profession', 'occupation', 'role')):
        return True
    # Some authored watches predate profession/occupation. A bare name is not
    # a job: the legacy record must also have a combatant civic posting.
    return bool(settings(w).get('recognize_legacy_watch') is True and d.get('combatant')
                and re.search(r'\bwatch\b', str(d.get('title', '')), re.I)
                and (d.get('patrol_route') or d.get('guard_room') or d.get('work_room')))


def is_guard(w, actor):
    if actor is None or actor.is_player or actor.progress.get('companion_owner') or actor.progress.get('zoo_exhibit'):
        return False
    from engine import livelihoods
    return _guard_definition(w, livelihoods.definition(w, actor))


def is_military(w, actor):
    """Explicit world-authored military membership, separate from police jobs."""
    flag = military_settings(w).get('flag')
    if not isinstance(flag, str) or not flag or actor is None or actor.is_player:
        return False
    if actor.progress.get('companion_owner') or actor.progress.get('zoo_exhibit'):
        return False
    return w.npcs.get(actor.source_def, {}).get(flag) is True


def is_defender(w, actor):
    return is_guard(w, actor) or is_military(w, actor)


def state(w):
    saved = living.state(w).setdefault(KEY, {})
    for field, value in (('incidents', {}), ('history', []), ('last', -1), ('cursor', 0)):
        saved.setdefault(field, value)
    return saved


def install(w):
    if not enabled(w):
        return
    floors = _stat_floors(w)
    for definition in w.npcs.values():
        if not _guard_definition(w, definition):
            continue
        for field, value in floors.items():
            definition[field] = max(value, definition.get(field, 0))
    reconcile(w)


def reconcile(w):
    """Upgrade saved officers once, preserving injury fraction and death."""
    if not enabled(w):
        return []
    guards = []
    floors = _stat_floors(w)
    stamp = [floors.get(field, 0) for field in ('hp', 'attack', 'defense')]
    for actor in w.entities.values():
        if not is_guard(w, actor):
            continue
        guards.append(actor)
        if not floors or actor.progress.get(KEY) == stamp:
            continue
        old_max = max(1, actor.max_hp)
        new_max = max(floors.get('hp', 0), old_max)
        actor.hp = (max(1, math.ceil(min(actor.hp, old_max) * new_max / old_max))
                    if actor.alive else 0)
        actor.max_hp = new_max
        actor.attack = max(floors.get('attack', 0), actor.attack)
        actor.defense = max(floors.get('defense', 0), actor.defense)
        actor.progress[KEY] = stamp
    return guards


def _local_law(w, room):
    """Explicit frontage choices win; otherwise inherit its actual interior."""
    details = getattr(w, 'room_details', {})
    seen = set()
    current = room
    while current in w.rooms and current not in seen and len(seen) < 4:
        seen.add(current)
        row = details.get(current, {})
        if 'laws' in row:
            laws = row['laws'] if isinstance(row['laws'], dict) else {}
            authority = laws.get('authority')
            return (dict(authority=authority, anchor=current, distance=0)
                    if laws.get('enabled') is True and authority else False)
        current = row.get('street_front') or getattr(w, '_street_origins', {}).get(current)
    return None


def jurisdiction(w, room, cache=None):
    """Return witnessed city authority or its authored exterior patrol radius."""
    if cache is not None and room in cache:
        return cache[room]
    answer = None
    if room in w.rooms:
        local = _local_law(w, room)
        if local is not None:
            answer = local or None
        else:
            row = getattr(w, 'room_details', {}).get(room, {})
            if row.get('requires_boat') or row.get('environment') in ('water', 'river', 'lake', 'ocean'):
                if cache is not None:
                    cache[room] = None
                return None
            group = w.rooms[room].group
            queue = deque([(room, 0)])
            seen = {room}
            while queue and len(seen) <= 96:
                current, distance = queue.popleft()
                if current != room:
                    law = _local_law(w, current)
                    if law:
                        if not group or law['authority'] == group:
                            answer = {**law, 'distance': distance}
                            break
                        continue
                    if law is False:
                        continue
                if distance == number(w, 'perimeter_steps', 1, 0, 8):
                    continue
                for target in w.rooms[current].exits.values():
                    if target not in w.rooms or target in seen:
                        continue
                    other = w.rooms[target].group
                    if group and other and other != group:
                        continue
                    seen.add(target)
                    queue.append((target, distance + 1))
    if cache is not None:
        cache[room] = answer
    return answer


def _protected_actor(w, actor):
    return bool(actor.progress.get('companion_owner') or actor.progress.get('zoo_exhibit')
                or w.npcs.get(actor.source_def, {}).get('zoo_exhibit') or actor.progress.get('court_case'))


def _release(w, incident):
    routes = getattr(w, '_city_defense_routes', {})
    for ident in incident.get('guards', []) + incident.get('military', []):
        guard = w.entities.get(ident)
        if guard and guard.progress.get('city_defense_target') == incident['actor']:
            from engine import npc_spellcasting
            npc_spellcasting.engage(w,guard)
            guard.progress.pop('city_defense_target', None)
            if str(getattr(guard, 'activity', '')).startswith(('responding to ', 'restraining ')):
                guard.activity = 'returning to watch duties'
        routes.pop((ident, incident['actor']), None)
    incident['guards'] = []
    incident['military'] = []


def _record(w, attacker, victim, *, attempted=False, fatal=False):
    if not enabled(w) or attacker is None or victim is None or attacker is victim or attacker.is_player:
        return
    if not attacker.alive or attacker.location != victim.location or _protected_actor(w, attacker):
        return
    if victim.progress.get('zoo_exhibit') or victim.progress.get('court_case'):
        return
    from engine import relationships
    if not (victim.is_player or victim.progress.get('companion_owner') or relationships.sentient(w, victim)):
        return
    if getattr(w, '_city_defense_lawful', None) == (attacker.id, victim.id):
        return
    jurisdiction_row = jurisdiction(w, attacker.location)
    if not jurisdiction_row:
        return
    s = state(w)
    # A victim resisting their recorded attacker is defending themselves.
    prior = s['incidents'].get(victim.id)
    if prior and attacker.id in prior.get('victims', []):
        return
    now = int(living.state(w)['minute'])
    incident = s['incidents'].get(attacker.id)
    if incident and incident['authority'] != jurisdiction_row['authority']:
        _release(w, incident)
        incident = None
    fresh = incident is None
    if fresh:
        incident = dict(actor=attacker.id, name=attacker.name, authority=jurisdiction_row['authority'],
                        first=now, rounds=0, guards=[], victims=[], evidence=[], status='alarm')
        s['incidents'][attacker.id] = incident
    incident.update(room=attacker.location, anchor=jurisdiction_row['anchor'], last=now)
    if victim.id not in incident['victims']:
        incident['victims'] = (incident['victims'] + [victim.id])[-8:]
    witnesses = [victim.id]  # The actual victim's alarm is evidence of this act.
    witnesses.extend(e.id for e in w.entities_in_room(attacker.location)
                     if e.id not in (attacker.id, victim.id) and e.alive and relationships.sentient(w, e))
    charge = settings(w).get('fatal_charge', 'assault') if fatal else 'assault'
    if not isinstance(charge, str) or not charge.strip() or len(charge) > 80:
        charge = 'assault'
    evidence = dict(kind=charge, actor=attacker.id, victim=victim.id, room=attacker.location,
                    minute=now, witnesses=list(dict.fromkeys(witnesses))[:16], attempted=attempted, fatal=fatal)
    if not incident['evidence'] or incident['evidence'][-1] != evidence:
        incident['evidence'] = (incident['evidence'] + [evidence])[-8:]
    if fatal:
        # A later nonfatal hit cannot overwrite the fatal act's charge,
        # victim or witnesses before the court reviews the accusation.
        incident['fatal_evidence'] = dict(evidence)
    # Keep the existing court's evidence format and authority; guards cannot
    # sentence anyone merely because an alarm has been raised.
    if relationships.sentient(w, attacker):
        from engine import mortality
        mortality.state(w)['wanted'][attacker.id] = _report(incident)
    if fresh:
        text = 'A watch alarm is raised: ' + attacker.name + ' attacks ' + victim.name + ' at ' + w.rooms[attacker.location].name + '. Officers are responding.'
        w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(attacker.location, text)])[-500:]


def _report(incident):
    evidence = incident.get('fatal_evidence') or incident['evidence'][-1]
    retained = [row for row in incident['evidence'] if row != evidence] + [evidence]
    return dict(room=incident['anchor'], incident_room=incident['room'], authority=incident['authority'],
                victim=evidence['victim'], reported=incident['last'], kind=evidence['kind'],
                witnesses=evidence['witnesses'], evidence=retained[-8:])


def on_damage(w, attacker, victim, damage, *, cause=None, kind='combat'):
    if damage > 0 and kind == 'combat' and cause != 'counterattack':
        _record(w, attacker, victim, fatal=not victim.alive)


def note_attempt(w, attacker, victim):
    """A committed hostile attempt blocked by newcomer safety still alerts watch."""
    _record(w, attacker, victim, attempted=True)


def _available(w, guard, authority, now):
    from engine import livelihoods
    return bool(guard.alive and guard.group_id == authority and not _protected_actor(w, guard)
                and not guard.progress.get('retired') and guard.progress.get('restrained_until', 0) <= now
                and livelihoods.awake(w, guard) and livelihoods.work_eligible(w, guard)
                and not str(getattr(guard, 'activity', '')).casefold().startswith('sleep'))


def _nearby(w, room):
    distance = {room: 0}
    queue = deque([room])
    room_limit = number(w, 'nearby_room_limit', 128, 16, 2048)
    steps = number(w, 'nearby_steps', 4, 1, 16)
    while queue and len(distance) < room_limit:
        current = queue.popleft()
        if distance[current] == steps:
            continue
        for target in w.rooms[current].exits.values():
            if target in w.rooms and target not in distance:
                distance[target] = distance[current] + 1
                queue.append(target)
                if len(distance) >= room_limit:
                    break
    return distance


def _next_step(w, guard, target, authority, budget, law_cache, passage_context):
    """Incremental physical BFS; no teleport, terrain generation or full-map scan."""
    from engine import frontiers
    lock_index, hazards = passage_context
    details = getattr(w, 'room_details', {})
    boat = any(w.items.get(item, {}).get('boat') for item in guard.inventory)
    node_limit = number(w, 'route_node_limit', 4096, 32, 32768)
    routes = getattr(w, '_city_defense_routes', None)
    if routes is None:
        routes = w._city_defense_routes = {}
    key = (guard.id, target.id)
    route = routes.get(key)
    if not route or route['origin'] != guard.location or route['target'] != target.location:
        route = dict(origin=guard.location, target=target.location,
                     queue=deque([guard.location]), previous={guard.location: None}, path=None)
        routes[key] = route
    if route['path'] is None:
        while route['queue'] and budget[0] > 0 and len(route['previous']) < node_limit:
            current = route['queue'].popleft()
            budget[0] -= 1
            if current == target.location:
                path = []
                while route['previous'][current] is not None:
                    before, direction = route['previous'][current]
                    path.append((before, direction, current))
                    current = before
                route['path'] = list(reversed(path))
                route['previous'] = {}
                route['queue'].clear()
                break
            check_passages = bool(details.get(current, {}).get('gates')) or current in hazards or bool(lock_index.get(current))
            check_passages = check_passages or any(details.get(dest, {}).get('property_unit_id') for dest in w.rooms[current].exits.values())
            for direction, destination in w.rooms[current].exits.items():
                if destination not in w.rooms or destination in route['previous']:
                    continue
                law = jurisdiction(w, destination, law_cache)
                if not law or law['authority'] != authority:
                    continue
                if frontiers.path_blocked(w, current, direction, destination, guard,
                                          check_passages, lock_index, hazards, boat):
                    continue
                route['previous'][destination] = (current, direction)
                route['queue'].append(destination)
        if route['path'] is None:
            if not route['queue'] or len(route['previous']) >= node_limit:
                routes.pop(key, None)
            return None
    if not route['path']:
        return None
    source, direction, destination = route['path'][0]
    if source != guard.location or w.rooms[source].exits.get(direction) != destination or frontiers.blocked(w, source, direction, guard, lock_index=lock_index):
        routes.pop(key, None)
        return None
    route['path'].pop(0)
    route['origin'] = destination
    return destination


def _finish(w, s, incident, outcome, now):
    _release(w, incident)
    s['history'] = (s['history'] + [dict(actor=incident['actor'], name=incident['name'],
                                      outcome=outcome, minute=now, room=incident['room'])])[-64:]
    s['incidents'].pop(incident['actor'], None)


def _assign(w, incident, available, key, wanted, distances):
    valid = {actor.id: actor for actor in available}
    assigned = []
    ident = incident['actor']
    for gid in incident.get(key, []):
        officer = w.entities.get(gid)
        if gid in valid and officer.progress.get('city_defense_target') == ident:
            assigned.append(gid)
        else:
            if officer and officer.progress.get('city_defense_target') == ident:
                officer.progress.pop('city_defense_target', None)
            getattr(w, '_city_defense_routes', {}).pop((gid, ident), None)
    candidates = sorted((actor for actor in available if not actor.progress.get('city_defense_target')),
                        key=lambda actor: (distances.get(actor.location, 999), actor.id))
    for actor in candidates[:max(0, wanted - len(assigned))]:
        from engine import npc_spellcasting
        npc_spellcasting.engage(w,actor)
        actor.progress['city_defense_target'] = ident
        assigned.append(actor.id)
    incident[key] = assigned
    return valid


def advance(w, rng=random.random):
    if not enabled(w):
        return
    s = state(w)
    now = int(living.state(w)['minute'])
    if s['last'] == now:
        return
    s['last'] = now
    guards = reconcile(w)
    incidents = list(s['incidents'])
    if not incidents:
        return
    military = ([actor for actor in w.entities.values() if is_military(w, actor) and not is_guard(w, actor)]
                if military_settings(w).get('enabled') is True else [])
    start = s['cursor'] % len(incidents)
    selected = (incidents[start:] + incidents[:start])[:number(w, 'incident_budget', 8, 1, 64)]
    s['cursor'] = (start + len(selected)) % len(incidents)
    law_cache = {}
    budget = [number(w, 'route_node_budget', 512, 16, 8192)]
    acted = set()
    from engine import city_justice, relationships, combat, npc_attention, mortality
    from engine import locks, geology_impacts
    passage_context = (locks.index(w), geology_impacts.route_sources(w))
    for ident in selected:
        incident = s['incidents'].get(ident)
        target = w.entities.get(ident)
        if target is None or not target.alive:
            _finish(w, s, incident, 'defeated' if target else 'unavailable', now)
            continue
        if target.progress.get('court_case') or city_justice.confined(w, target):
            _finish(w, s, incident, 'in court custody', now)
            continue
        law = jurisdiction(w, target.location, law_cache)
        if not law or law['authority'] != incident['authority']:
            _release(w, incident)
            incident['status'] = 'beyond patrol boundary'
            continue
        incident['status'] = 'responding'
        incident['room'] = target.location
        deaths = mortality.state(w)['deaths']
        casualties = set(incident.get('police_casualties', []))
        for gid in incident.get('guards', []):
            officer = w.entities.get(gid)
            if (officer is not None and not officer.alive) or gid in deaths:
                casualties.add(gid)
        incident['police_casualties'] = sorted(casualties)
        available = [g for g in guards if g.id != ident and _available(w, g, incident['authority'], now)]
        maximum = number(w, 'max_responders', 4, 1, 16)
        initial = min(maximum, number(w, 'initial_responders', 1, 1, 16))
        reinforcement = number(w, 'reinforcements_per_round', 1, 0, 8)
        wanted = min(maximum, initial + incident['rounds'] * reinforcement)
        distances = _nearby(w, target.location)
        valid = _assign(w, incident, available, 'guards', wanted, distances)
        incident['rounds'] = min(65535, incident['rounds'] + 1)
        if military and (incident['rounds'] >= _military_number(w, 'escalation_rounds', 4, 1, 1000)
                         or len(casualties) >= _military_number(w, 'police_casualties', 1, 1, 64)):
            available_army = [actor for actor in military if actor.id != ident and _available(w, actor, incident['authority'], now)]
            army_max = _military_number(w, 'max_responders', 8, 1, 64)
            army_first = min(army_max, _military_number(w, 'initial_responders', 2, 1, 64))
            army_step = _military_number(w, 'reinforcements_per_round', 2, 0, 16)
            army_wanted = min(army_max, army_first + incident.get('military_rounds', 0) * army_step)
            valid.update(_assign(w, incident, available_army, 'military', army_wanted, distances))
            incident['military_rounds'] = min(65535, incident.get('military_rounds', 0) + 1)
        for gid in list(incident['guards']) + list(incident.get('military', [])):
            if gid not in valid:
                continue
            guard = valid[gid]
            if gid in acted:
                continue
            acted.add(gid)
            from engine import npc_spellcasting
            npc_spellcasting.engage(w,guard)
            npc_attention.begin(w, guard)
            guard.activity = 'responding to the alarm about ' + target.name
            if guard.location != target.location:
                step = _next_step(w, guard, target, incident['authority'], budget, law_cache, passage_context)
                if step:
                    w.move_entity(guard.id, step)
                continue
            if target.progress.get('restrained_until', 0) > now:
                continue
            sentient = relationships.sentient(w, target)
            if sentient:
                report = _report(incident)
                mortality.state(w)['wanted'][ident] = report
                chance = max(.1, min(.95, (guard.attack + guard.defense + 1) /
                             (guard.attack + guard.defense + target.attack + target.defense + 2)))
                if rng() < chance and city_justice.apprehend(w, target, guard, report):
                    mortality.state(w)['wanted'].pop(ident, None)
                    text = guard.name + ' restrains ' + target.name + ' and takes them into custody pending a magistrate hearing.'
                    w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(guard.location, text)])[-500:]
                    _finish(w, s, incident, 'in court custody', now)
                    break
            try:
                combat.validate(w, guard, target)
                w._city_defense_lawful = (guard.id, target.id)
                helpers=[valid[eid] for eid in list(incident['guards'])+list(incident.get('military',[])) if eid in valid]
                text=npc_spellcasting.try_cast(w,guard,target,counter=True,lawful=True,allies=helpers)
                if text is None:
                    combat.ammunition(w, guard)
                    text = combat.strike(w, guard, target, counter=True, lawful=True)
            except ValueError:
                continue
            finally:
                w.__dict__.pop('_city_defense_lawful', None)
            w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(guard.location, text)])[-500:]
            if not target.alive:
                _finish(w, s, incident, 'defeated', now)
                break
