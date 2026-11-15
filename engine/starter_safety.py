"""Small, data-derived starting refuges; combat policy is layered separately.

Only the origin identifier belongs in character progress. Derived room sets and
indices live on the World, never alter world records, and never generate land.
"""
from collections import defaultdict, deque

KEY = 'starter_safety_v1'
PATH_ROOMS = 128
AUDIT_ROOMS = 64
WATER = frozenset(('water', 'river', 'lake', 'ocean'))
WILDERNESS = frozenset(('wilderness', 'forest', 'mountain', 'plains', 'coast',
    'desert', 'wetland', 'rainforest', 'valley', 'shore', 'tundra', 'grassland',
    'swamp', 'cave'))
CIVIC = frozenset(('town', 'city', 'street', 'settlement', 'building',
    'inside', 'indoor', 'indoors', 'interior'))


def config(w):
    value = getattr(w, 'rules', {}).get('starter_safety', {})
    return value if isinstance(value, dict) else {}


def enabled(w):
    return config(w).get('enabled') is True


def _details(w, room):
    row = getattr(w, 'room_details', {}).get(room, {})
    return row if isinstance(row, dict) else {}


def _roots(w):
    roots = {getattr(w, 'start_room', None), getattr(w, 'metadata', {}).get('start_room')}
    roots.update(row.get('start_room') for row in getattr(w, 'groups', {}).values()
                 if isinstance(row, dict) and row.get('visibility') == 'playable')
    return tuple(sorted(room for room in roots if isinstance(room, str) and room in w.rooms))


def origin(w, p, actual=None):
    """Remember the actual origin once; faction changes never move a refuge."""
    if not enabled(w):
        return ''
    notes = p.progress.get(KEY)
    if not isinstance(notes, dict):
        notes = {}
        p.progress[KEY] = notes
    saved = notes.get('origin')
    if isinstance(saved, str) and saved:
        return saved
    if actual not in w.rooms:
        group = getattr(w, 'groups', {}).get(p.group_id, {})
        actual = group.get('start_room') if group.get('visibility') == 'playable' else None
    if actual not in w.rooms:
        actual = getattr(w, 'start_room', None) or getattr(w, 'metadata', {}).get('start_room')
    if actual not in w.rooms:
        return ''
    notes['origin'] = actual
    return actual


def invalidate(w):
    """Creator tools may invalidate derived footprints after a bulk edit."""
    w.__dict__.pop('_starter_safety_geography', None)


def _signature(w, room):
    if room not in w.rooms:
        return None
    row = _details(w, room)
    climate, planet, laws = row.get('climate') or {}, row.get('planet') or {}, row.get('laws') or {}
    return (w.rooms[room].group, getattr(w.rooms[room], 'map_visibility', None),
            tuple(sorted(w.rooms[room].exits.items())),
            row.get('environment'), climate.get('terrain'), row.get('truce'),
            row.get('open_country'), row.get('requires_boat'), row.get('property_unit_id'),
            row.get('map_visibility'), row.get('world_region'), row.get('press_locality'),
            planet.get('lat'), planet.get('lon'), laws.get('enabled'), row.get('street_front'))


def _tutorials(w):
    # Only explicit introductory destinations
    # participate in the stamp, including in-place creator edits to a quest.
    category = config(w).get('tutorial_category')
    return tuple(sorted((str(key), row.get('offer_room', ''), row.get('turn_in_room', ''))
                        for key, row in getattr(w, 'quests', {}).items()
                        if isinstance(row, dict) and row.get('category') == category
                        and not row.get('prerequisites')
                        and isinstance(row.get('offer_room'), str)
                        and isinstance(row.get('turn_in_room'), str)))


def _cache(w):
    quests = _tutorials(w)
    stamp = (id(w.rooms), len(w.rooms), id(getattr(w, 'room_details', None)),
             len(getattr(w, 'room_details', {})), _roots(w),
             tuple(sorted(config(w).items())), quests)
    cache = getattr(w, '_starter_safety_geography', None)
    if cache is None or cache['stamp'] != stamp:
        fronts = defaultdict(set)
        anchors = {}
        for rid in w.rooms:
            anchor = _details(w, rid).get('street_front')
            if isinstance(anchor, str) and anchor in w.rooms:
                fronts[anchor].add(rid)
                anchors[rid] = anchor
        cache = dict(stamp=stamp, fronts=fronts, anchors=anchors, entries={},
                     audit=list(w.rooms), offset=0, minute=None,
                     builds=(cache or {}).get('builds', 0)+1)
        w._starter_safety_geography = cache
    minute = int((getattr(w, 'living_state', None) or {}).get('minute', 0))
    if cache['minute'] != minute:
        cache['minute'] = minute
        # Bounded audit catches a previously unrelated room being re-anchored
        # as a frontage without rescanning all rooms on a combat query.
        for _ in range(min(AUDIT_ROOMS, len(cache['audit']))):
            rid = cache['audit'][cache['offset'] % len(cache['audit'])]
            cache['offset'] += 1
            anchor = _details(w, rid).get('street_front')
            anchor = anchor if isinstance(anchor, str) and anchor in w.rooms else None
            if cache['anchors'].get(rid) != anchor:
                invalidate(w)
                return _cache(w)
    return cache


def _eligible(w, root, room):
    if room == root:
        return room in w.rooms
    if room not in w.rooms:
        return False
    row, home = _details(w, room), _details(w, root)
    environment = str(row.get('environment') or '').casefold()
    climate = row.get('climate') or {}
    if (row.get('requires_boat') or environment in WATER | WILDERNESS
            or climate.get('terrain') in WATER or row.get('property_unit_id')
            or row.get('map_visibility') == 'hidden'
            or getattr(w.rooms[room], 'map_visibility', None) == 'hidden'):
        return False
    laws = row.get('laws') or {}
    civic = environment in CIVIC or laws.get('enabled') is True or row.get('truce')
    if row.get('open_country') and not civic:
        return False
    owner, other = w.rooms[root].group, w.rooms[room].group
    if other and other != owner:
        return False
    if not other and owner and not civic and not row.get('street_front'):
        return False
    # Explicit survey/locality boundaries prevent a short portal from turning
    # a distant city of the same kingdom into part of the starting refuge.
    for key in ('world_region', 'press_locality'):
        if home.get(key) and row.get(key) and home[key] != row[key]:
            return False
    a, b = home.get('planet') or {}, row.get('planet') or {}
    if (all(key in a and key in b for key in ('lat', 'lon'))
            and (a['lat'], a['lon']) != (b['lat'], b['lon'])):
        return False
    return True


def _path(w, root, target, watched):
    if not _eligible(w, root, target):
        watched.add(target)
        return ()
    queue = deque([(root, 0)])
    previous = {root: None}
    while queue and len(previous) <= PATH_ROOMS:
        room, depth = queue.popleft()
        watched.add(room)
        if room == target:
            path = []
            while room is not None:
                path.append(room)
                room = previous[room]
            return tuple(reversed(path))
        if depth >= config(w).get('tutorial_path_steps', 0):
            continue
        for destination in w.rooms[room].exits.values():
            watched.add(destination)
            if destination not in previous and _eligible(w, root, destination):
                previous[destination] = room
                queue.append((destination, depth+1))
                if len(previous) >= PATH_ROOMS:
                    break
    return ()


def _footprint(w, root, cache):
    entry = cache['entries'].get(root)
    if entry and all(_signature(w, rid) == sig for rid, sig in entry['watched'].items()):
        return entry['rooms']
    if root not in w.rooms:
        return frozenset()
    watched = {root}
    footprint = {root}
    for dest in (w.rooms[root].exits.values() if config(w).get('include_direct_civic_exits') is True else ()):
        watched.add(dest)
        if _eligible(w, root, dest):
            footprint.add(dest)
    targets = sorted({target for _, offer, target in cache['stamp'][-1] if offer == root})
    for target in targets[:4]:
        footprint.update(_path(w, root, target, watched))
    # One anchored frontage expansion, not a flood through a whole building.
    for anchor in (tuple(footprint) if config(w).get('include_frontages') is True else ()):
        for frontage in cache['fronts'].get(anchor, ()):
            watched.add(frontage)
            if (_details(w, frontage).get('street_front') == anchor
                    and _eligible(w, root, frontage)):
                footprint.add(frontage)
    entry = dict(rooms=frozenset(footprint), watched={rid: _signature(w, rid) for rid in watched})
    cache['entries'][root] = entry
    return entry['rooms']


def rooms(w, p):
    """Return this character's original small refuge, including public exits."""
    if not enabled(w):
        return frozenset()
    start = origin(w, p)
    return _footprint(w, start, _cache(w)) if start in w.rooms else frozenset()


def all_rooms(w):
    """Return all authored starts' refuges without touching any character."""
    if not enabled(w):
        return frozenset()
    roots = _roots(w)
    if not roots:
        return frozenset()
    cache = _cache(w)
    return frozenset(room for root in roots for room in _footprint(w, root, cache))


# Peaceful refuge protection never expires while someone is reading or talking.
# Choosing a fight suspends it; continued real combat extends that suspension.
def _conflict_minutes(w):
    return max(1, int(config(w).get('conflict_minutes', 1)))


def _now(w):
    from engine import living
    return int(living.state(w)['minute'])


def _player(w, actor):
    if actor is None:
        return None
    if getattr(actor, 'is_player', False):
        return actor
    owner = getattr(actor, 'progress', {}).get('companion_owner')
    player = w.entities.get(owner)
    return player if player is not None and player.is_player else None


def protected(w, player):
    if player is None or not player.is_player or not player.alive:
        return False
    if player.location not in rooms(w, player):
        return False
    notes = player.progress[KEY]
    if notes.get('provoked_until', -1) > _now(w):
        return False
    if player.id in (getattr(w, 'living_state', {}).get('mortality', {}).get('wanted', {})):
        return False
    if player.progress.get('court_case'):
        return False
    return True


def blocked(w, attacker, victim):
    """Protect a peaceful player's own refuge, not NPCs or player PvP."""
    if attacker is None or not hasattr(attacker, 'id') or getattr(attacker, 'is_player', False):
        return False
    # A player-controlled pet retains existing PvP/companion permissions.
    if getattr(attacker, 'progress', {}).get('companion_owner'):
        return False
    player = _player(w, victim)
    return bool(player is not None and protected(w, player)
                and victim.location in rooms(w, player))


def _notice(w, player, text):
    w.rest_notifications = (getattr(w, 'rest_notifications', []) + [(player.id, text)])[-500:]


def provoke(w, actor, victim, credit=None, lawful=False):
    """Call only when a valid voluntary attack has committed, not on selection."""
    if not enabled(w) or lawful or actor is victim:
        return
    player = credit if credit is not None and credit.is_player else actor if getattr(actor, 'is_player', False) else None
    if player is None or not player.alive or not origin(w, player):
        return
    now = _now(w)
    notes = player.progress[KEY]
    already = notes.get('provoked_until', -1) > now
    notes['provoked_until'] = now + _conflict_minutes(w)
    if not already and player.location in rooms(w, player):
        _notice(w, player, 'You chose to fight. Starting-area protection is suspended until you have been out of combat for '+str(_conflict_minutes(w))+' game minutes.')


def on_damage(w, attacker, victim, damage):
    if not enabled(w) or damage <= 0:
        return
    now = _now(w)
    for actor in (attacker, victim):
        player = _player(w, actor)
        if player is None:
            continue
        notes = player.progress.get(KEY, {})
        if notes.get('provoked_until', -1) > now:
            notes['provoked_until'] = now + _conflict_minutes(w)


def prevented(w, attacker, victim):
    player = _player(w, victim)
    if player is None:
        return ''
    stamp = (attacker.id, victim.location, _now(w))
    if getattr(player, '_starter_prevented', None) == stamp:
        return ''
    player._starter_prevented = stamp
    return 'Starting-area protection prevents '+attacker.name+' from attacking '+('you' if victim.is_player else victim.name)+'.'


def on_move(w, player, before, after):
    footprint = rooms(w, player)
    previous, current = before in footprint, after in footprint
    seen = getattr(player, '_starter_refuge_notice', None)
    if current and protected(w, player) and (not previous or seen is None):
        _notice(w, player, 'Starting area: you are protected from unprovoked NPC attacks here while peaceful. Choosing to fight suspends that protection.')
    elif previous and not current:
        _notice(w, player, 'You have left your protected starting area. Normal encounters and combat now apply.')
    player._starter_refuge_notice = current
