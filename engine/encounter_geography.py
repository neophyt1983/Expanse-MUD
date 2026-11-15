"""Read-only encounter geography over the rooms that already exist.

Distances count real exit steps to the nearest settlement footprint, regardless
of faction. Display coordinates are deliberately not a distance model: the
official pack mixes regional, planet and expedition coordinate charts. The
ephemeral index grows with materialized rooms; it never generates terrain or
writes a save. ``invalidate`` is available to callers applying bulk edits.
"""
from collections import deque
import math

OUTDOORS = frozenset(('wilderness', 'outdoors', 'outdoor', 'forest', 'mountain',
    'plains', 'coast', 'desert', 'wetland', 'rainforest', 'valley', 'shore',
    'tundra', 'grassland', 'swamp', 'cave'))
INTERIORS = frozenset(('building', 'inside', 'indoor', 'indoors', 'interior'))
TOWNS = frozenset(('town', 'city', 'street', 'settlement'))
WATER = frozenset(('water', 'river', 'lake', 'ocean'))
SANCTUARIES = frozenset(('inn', 'temple', 'school', 'library', 'kitchen',
    'hospital', 'court', 'jail', 'husbandry', 'residential'))
AUDIT_PER_MINUTE = 128


def invalidate(w):
    """Discard derived geometry only; authored/runtime game state is untouched."""
    w.__dict__.pop('_encounter_geography', None)


def _details(w, room):
    value = getattr(w, 'room_details', {}).get(room, {})
    return value if isinstance(value, dict) else {}


def _cities(w):
    rows = getattr(w, 'metadata', {}).get('press_editions', [])
    return sorted((row for row in rows if isinstance(row, dict)
                   and row.get('kind') in ('city', 'town')
                   and row.get('home') in w.rooms), key=lambda row: (str(row.get('name', '')), row['home']))


def _local(w, room, homes, starts):
    d = _details(w, room)
    climate = d.get('climate') or {}
    environment = str(d.get('environment') or '').casefold()
    habitat = str(climate.get('terrain') or environment or 'plains').casefold()
    facilities = set(d.get('facilities') or ())
    laws = d.get('laws') or {}
    plot = d.get('property_plot') or {}
    land = d.get('active_land_use') or plot.get('kind')
    settled = (room in homes or environment in TOWNS or laws.get('enabled') is True
               or (plot.get('enabled') and land in ('house', 'rental', 'business'))
               or 'residential' in facilities)
    reason = None
    if room in starts:
        reason = 'starting place'
    elif d.get('zoo_city') or d.get('zoo_exhibits') or d.get('justice_city'):
        reason = 'protected civic place'
    elif d.get('truce'):
        reason = 'authored sanctuary'
    elif d.get('property_unit_id') or environment in INTERIORS:
        reason = 'interior'
    elif d.get('requires_boat') or environment in WATER or habitat in WATER:
        reason = 'water'
    elif facilities & SANCTUARIES:
        reason = 'protected facility'
    elif d.get('map_visibility') == 'hidden':
        reason = 'hidden location'
    elif environment not in OUTDOORS | TOWNS | {'road'} and (
            d.get('building') or d.get('_visual_building') or climate.get('sheltered') is True):
        reason = 'interior or sheltered location'
    if reason:
        return 'protected', reason, habitat, bool(settled)
    if settled:
        return 'town', 'settlement footprint', habitat, True
    route = d.get('route_surface') or {}
    if ((isinstance(route, dict) and route.get('kind') in ('road', 'trail'))
            or environment == 'road' or habitat == 'road'):
        return 'road', 'marked road or trail', habitat, False
    if d.get('open_country') or environment in OUTDOORS:
        return 'outdoor', 'open country', habitat, False
    # Missing environment/shelter data never turns an ambiguous room into a
    # hostile spawning site merely because its name or faction resembles land.
    return 'protected', 'unclassified location', habitat, False


def _signature(w, room, cache):
    return (_local(w, room, cache['homes'], cache['starts']),
            tuple(sorted(set(w.rooms[room].exits.values()))),
            w.rooms[room].group, _details(w, room).get('press_locality'))


def _point(w, room):
    row = _details(w, room)
    point = row.get('tile_position') or row.get('planet') or {}
    lat, lon = point.get('lat'), point.get('lon')
    if (type(lat) in (int, float) and type(lon) in (int, float)
            and math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        return math.radians(lat), math.radians(lon)
    return None


def _geographic_owner(w, room, cache):
    point = _point(w, room)
    if point is None:
        return None
    lat, lon = point
    choices = []
    for i, city in enumerate(cache['cities']):
        target = _point(w, city['home'])
        if target is None:
            continue
        other_lat, other_lon = target
        distance = (math.sin((lat - other_lat) / 2) ** 2
                    + math.cos(lat) * math.cos(other_lat) * math.sin((lon - other_lon) / 2) ** 2)
        choices.append((distance, i))
    return min(choices)[1] if choices else None


def _owner(w, room, cache):
    """Associate a footprint with its authored town, then its nearest home."""
    if room in cache['homes']:
        return cache['homes'][room]
    row = _details(w, room)
    name = row.get('press_locality')
    if name in cache['names']:
        return cache['names'][name]
    group = w.rooms[room].group
    same_group = [i for i, city in enumerate(cache['cities']) if group and city.get('group') == group]
    if len(same_group) == 1:
        return same_group[0]
    nearest = cache['home_distance'].get(room)
    if nearest is not None:
        return nearest[1]
    geographical = _geographic_owner(w, room, cache)
    return geographical if geographical is not None else -1


def _relax(table, adjacency, starting):
    """Propagate only improved unit-edge distances from supplied endpoints."""
    queue = deque(sorted(room for room in set(starting) if room in table))
    queued = set(queue)
    changed = set()
    while queue:
        room = queue.popleft()
        queued.discard(room)
        distance, owner = table[room]
        following = (distance + 1, owner)
        for target in adjacency.get(room, ()):
            old = table.get(target)
            if old is None or following < old:
                table[target] = following
                changed.add(target)
                if target not in queued:
                    queue.append(target)
                    queued.add(target)
    return changed


def _seed_owners(w, cache, rooms):
    changed = []
    for room in rooms:
        if not cache['signatures'][room][0][3]:
            continue
        value = (0, _owner(w, room, cache))
        old = cache['distance'].get(room)
        if old != value:
            cache['distance'][room] = value
            changed.append(room)
        cache['settled'].add(room)
    return changed


def _build(w, stamp, cities, starts):
    cache = {'stamp': stamp, 'cities': cities, 'starts': starts,
             'homes': {city['home']: i for i, city in enumerate(cities)},
             'names': {city.get('name'): i for i, city in enumerate(cities)},
             'ids': set(w.rooms), 'adjacency': {room: set() for room in w.rooms},
             'signatures': {}, 'home_distance': {}, 'distance': {}, 'settled': set(),
             'audit_rooms': list(w.rooms), 'audit_offset': 0, 'audit_minute': None,
             'builds': getattr(w, '_encounter_geography', {}).get('builds', 0) + 1,
             'increments': 0}
    for room in w.rooms:
        cache['signatures'][room] = _signature(w, room, cache)
        for target in w.rooms[room].exits.values():
            if target in w.rooms:
                # Physical proximity is symmetric even for a one-way authored
                # entrance. This graph is not used to route a character.
                cache['adjacency'][room].add(target)
                cache['adjacency'][target].add(room)
    cache['home_distance'] = {room: (0, owner) for room, owner in cache['homes'].items()}
    _relax(cache['home_distance'], cache['adjacency'], cache['homes'])
    seeds = _seed_owners(w, cache, w.rooms)
    _relax(cache['distance'], cache['adjacency'], seeds)
    w._encounter_geography = cache
    return cache


def _extend(w, cache):
    new = w.rooms.keys() - cache['ids']
    affected = set(new)
    for room in new:
        cache['adjacency'].setdefault(room, set())
        cache['signatures'][room] = _signature(w, room, cache)
        for target in w.rooms[room].exits.values():
            if target in w.rooms:
                affected.add(target)
                cache['adjacency'][room].add(target)
                cache['adjacency'].setdefault(target, set()).add(room)
    for room in affected - new:
        prior = cache['signatures'][room]
        current = _signature(w, room, cache)
        # Bidirectional lazy terrain links are ordinary additions. Removals,
        # reclassification or an unrelated old-to-old edge require a rebuild.
        if (prior[0] != current[0] or prior[2:] != current[2:]
                or not set(prior[1]) <= set(current[1])
                or (set(current[1]) - set(prior[1])) - new):
            return False
        cache['signatures'][room] = current
        for target in w.rooms[room].exits.values():
            if target in w.rooms:
                cache['adjacency'][room].add(target)
                cache['adjacency'].setdefault(target, set()).add(room)
    cache['ids'].update(new)
    cache['audit_rooms'].extend(sorted(new))
    homes_changed = _relax(cache['home_distance'], cache['adjacency'], affected)
    # A new shortcut can change which town owns an ambiguous old settlement.
    # Such rare topology changes get a complete solve instead of stale labels.
    if any(_owner(w, room, cache) != cache['distance'][room][1]
           for room in homes_changed & cache['settled']):
        return False
    seeds = _seed_owners(w, cache, new)
    _relax(cache['distance'], cache['adjacency'], affected | set(seeds))
    cache['increments'] += 1
    return True


def _cache(w, room):
    cities = _cities(w)
    starts = {getattr(w, 'start_room', None)} | {
        row.get('start_room') for row in getattr(w, 'groups', {}).values() if isinstance(row, dict)}
    stamp = (id(w.rooms), id(getattr(w, 'room_details', None)),
             tuple((city.get('name'), city['home'], city.get('group')) for city in cities),
             frozenset(starts))
    cache = getattr(w, '_encounter_geography', None)
    if (cache is None or cache['stamp'] != stamp or len(w.rooms) < len(cache['ids'])
            or room not in w.rooms):
        return _build(w, stamp, cities, starts)
    if len(w.rooms) != len(cache['ids']):
        if not cache['ids'] <= w.rooms.keys() or not _extend(w, cache):
            return _build(w, stamp, cities, starts)
    local = {room} | {rid for rid in w.rooms[room].exits.values() if rid in w.rooms}
    if any(cache['signatures'].get(rid) != _signature(w, rid, cache) for rid in local):
        return _build(w, stamp, cities, starts)
    minute = int((getattr(w, 'living_state', None) or {}).get('minute', 0))
    if cache['audit_minute'] != minute:
        cache['audit_minute'] = minute
        rows = cache['audit_rooms']
        for _ in range(min(AUDIT_PER_MINUTE, len(rows))):
            rid = rows[cache['audit_offset'] % len(rows)]
            cache['audit_offset'] += 1
            if rid not in w.rooms or cache['signatures'].get(rid) != _signature(w, rid, cache):
                return _build(w, stamp, cities, starts)
    return cache


def describe(w, room):
    """Return zone, nearest-footprint steps, source city, habitat and reason.

    ``distance=None`` means no materialized connection to a known settlement,
    not a claim that a disconnected coordinate chart is infinitely remote.
    Geographic/gate fallbacks choose a regional creature pool only; they never
    invent distance steps or instantiate unvisited terrain.
    """
    if room not in w.rooms:
        return dict(zone='protected', distance=None, city=None, habitat='unknown', reason='missing location')
    cache = _cache(w, room)
    zone, reason, habitat, _ = cache['signatures'][room][0]
    nearest = cache['distance'].get(room)
    owner = nearest[1] if nearest else -1
    if owner < 0:
        home = cache['home_distance'].get(room)
        owner = home[1] if home else _geographic_owner(w, room, cache)
    if owner is None or owner < 0:
        from engine import wildlands
        position = wildlands.cell(w, room)
        if position:
            gate = w.field_regions[position[0]].gate
            at_gate = cache['home_distance'].get(gate)
            owner = at_gate[1] if at_gate else _geographic_owner(w, gate, cache)
    city = cache['cities'][owner] if owner is not None and 0 <= owner < len(cache['cities']) else None
    return dict(zone=zone, distance=nearest[0] if nearest else None,
                city=city, habitat=habitat, reason=reason)
