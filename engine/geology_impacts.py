"""Explicit, bounded geological consequences. All public view queries are pure.

Plans are opt-in per source. No terrain inference, base-world mutation, persistent
ruin, global volcanic climate, inventory loss, or use of the source timing RNG.
"""
from collections import deque
from copy import deepcopy
import hashlib
import math
import weakref
from itertools import islice

from engine.directions import direction, normalize_exits
from engine.worldtime import MINUTES_PER_DAY

VERSION = 1
MAX_TARGETS = 128
MAX_PLAN_TARGETS = 256
MAX_IMPACTS = 2048
MAX_EXPOSURES = 128
MAX_ACTORS = 4096
MAX_OUTCOMES = 256
MAX_CLOSURE = 240
RECOVERY_GRACE = 120
MAX_ROUTE_ROOMS = 512
MAX_ROUTE_STEPS = 64
FIELDS = ('actor_exposure', 'structures', 'routes', 'resources', 'port_routes')
# Derived, non-persisted cache. No query writes to the world or simulation state.
_INDEX_CACHE = weakref.WeakKeyDictionary()


def _number(v, low=0, high=10**15):
    return type(v) in (int, float) and low <= v <= high and math.isfinite(v)


def world_data(world, room_ids=None):
    """Same complete catalogs for runtime and loader validation as the editor."""
    selected = world.rooms.keys() if room_ids is None else room_ids
    return {'room': [dict(getattr(world, 'room_details', {}).get(rid, {}),
                         id=rid, exits=dict(world.rooms[rid].exits)) for rid in selected if rid in world.rooms],
            'building': list(getattr(world, 'buildings', {}).values()),
            'resource': list(getattr(world, 'resources', {}).values())}


def structural_site(row):
    """Actual authored property or facility, never inferred from a room name."""
    plot=row.get('property_plot',{})
    facilities=row.get('facilities',[])
    return ((isinstance(plot,dict) and plot.get('enabled') is True) or
            (isinstance(facilities,list) and bool(facilities) and all(isinstance(v,str) and v for v in facilities)))


def validate_plan(data, plan, event_rooms, where='consequences'):
    issues = []
    def bad(message): issues.append(where + ': ' + message)
    if not isinstance(plan, dict):
        return [where + ': must be an object']
    for key in plan:
        if key not in FIELDS + ('recovery_minutes',): bad('unknown field ' + repr(key))
    recovery = plan.get('recovery_minutes', 120)
    if type(recovery) is not int or not 1 <= recovery <= 1440:
        bad('recovery_minutes must be an integer from 1 to 1440')
    rooms = {r['id']: r for r in data.get('room', []) if isinstance(r, dict) and isinstance(r.get('id'), str)}
    buildings = {r['id']: r for r in data.get('building', []) if isinstance(r, dict) and isinstance(r.get('id'), str)}
    resources = {r['id'] for r in data.get('resource', []) if isinstance(r, dict) and isinstance(r.get('id'), str)}
    local = {r for r in event_rooms if isinstance(r, str)} if isinstance(event_rooms, list) else set()
    count = 0
    for kind in FIELDS:
        rows = plan.get(kind, [])
        if not isinstance(rows, list) or len(rows) > MAX_TARGETS:
            bad(kind + ' must be a list of at most 128 explicit targets')
            continue
        count += len(rows)
        seen = set()
        for index, row in enumerate(rows):
            label = kind + '[' + str(index) + ']'
            if not isinstance(row, dict):
                bad(label + ' must be an object'); continue
            fields = {'actor_exposure': {'room', 'exposure'}, 'structures': {'building', 'room'},
                      'routes': {'source', 'direction', 'destination'}, 'resources': {'room', 'resource'},
                      'port_routes': {'origin', 'destination'}}[kind]
            if set(row) - fields: bad(label + ' contains unknown fields')
            # Canonical keys make alias duplicates visible without coercing malformed input.
            key = repr(sorted(row.items(), key=lambda p: p[0]))
            if key in seen: bad(label + ' duplicates a target')
            seen.add(key)
            def local_room(value):
                return isinstance(value, str) and value in rooms and value in local
            if kind == 'actor_exposure':
                if not local_room(row.get('room')): bad(label + ' room must be an existing event room')
                if not _number(row.get('exposure'), 0, 1): bad(label + ' exposure must be finite from 0 to 1')
                # A room cannot have two contradictory exposure levels.
                if any(isinstance(r, dict) and r.get('room') == row.get('room') for r in rows[:index]):
                    bad(label + ' repeats an exposure room')
            elif kind == 'structures':
                if set(row) not in ({'building'}, {'room'}):
                    bad(label + ' must name exactly one building or property room'); continue
                if 'building' in row:
                    b = buildings.get(row['building']) if isinstance(row['building'], str) else None
                    br = b.get('rooms') if isinstance(b, dict) else None
                    if not isinstance(br, list) or not br or any(not local_room(r) for r in br):
                        bad(label + ' building must exist and all its rooms must be event rooms')
                else:
                    rid = row['room']
                    if not local_room(rid) or not structural_site(rooms[rid]):
                        bad(label + ' must name an enabled property_plot or authored facility in an event room')
            elif kind == 'routes':
                source, dest, di = row.get('source'), row.get('destination'), row.get('direction')
                try:
                    di = direction(di)
                    exits = normalize_exits(rooms.get(source, {}).get('exits', {})) if isinstance(source, str) else {}
                except (ValueError, TypeError): di, exits = None, {}
                if not local_room(source) or not isinstance(dest, str) or dest not in rooms or di is None or exits.get(di) != dest:
                    bad(label + ' must name an exact existing source/direction/destination edge from an event room')
                canonical = (source, di, dest)
                if all(isinstance(v, str) for v in canonical):
                    ck = repr(canonical)
                    if ck in seen: bad(label + ' repeats a canonical route')
                    seen.add(ck)
            elif kind == 'resources':
                rid, resource = row.get('room'), row.get('resource')
                if not local_room(rid) or not isinstance(resource, str) or resource not in resources or resource not in rooms[rid].get('resources', []):
                    bad(label + ' must name an existing room/resource pair in an event room')
            else:
                origin, dest = row.get('origin'), row.get('destination')
                port = rooms.get(origin, {}).get('port', {}) if isinstance(origin, str) else {}
                target = rooms.get(dest, {}).get('port', {}) if isinstance(dest, str) else {}
                if not local_room(origin) or not isinstance(port, dict) or port.get('enabled') is not True or not isinstance(target, dict) or target.get('enabled') is not True or not any(isinstance(r, dict) and r.get('to') == dest for r in port.get('routes', [])):
                    bad(label + ' must name an existing enabled origin/destination port service from an event room')
    if count > MAX_PLAN_TARGETS: bad('at most 256 targets are allowed across the plan')
    return issues


def _now(world):
    s = getattr(world, 'living_state', None)
    value = s.get('minute') if isinstance(s, dict) else None
    return int(value) if _number(value) else None


def _state(world, create=False):
    ls = getattr(world, 'living_state', None)
    if not isinstance(ls, dict): return None
    s = ls.get('geology_impacts')
    if s is None and create:
        s = dict(version=VERSION, last_minute=-1, highwater=0, impacts={}, events=[], actors={}, outcomes=[])
        ls['geology_impacts'] = s
    if not isinstance(s, dict) or type(s.get('version')) is not int or s.get('version') != VERSION: return None
    if not all(isinstance(s.get(k), t) for k, t in (('impacts', dict), ('events', list), ('actors', dict), ('outcomes', list))):
        return None
    return s


def _serial(event):
    ident = event.get('id') if isinstance(event, dict) else None
    if not isinstance(ident, str) or not ident.startswith('geo-') or not ident[4:].isdigit() or len(ident) > 24: return 0
    value = int(ident[4:])
    return value if 0 < value <= 10**15 else 0


def _roll(seed, event_id, target, purpose):
    raw = f'geology-impacts-v1:{seed}:{event_id}:{target}:{purpose}'.encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big') / float(1 << 64)


def _severity(event):
    if event.get('type') == 'quake': return max(0., min(1., (event.get('magnitude', 0) - 3) / 5))
    return max(0., min(1., event.get('intensity', 0)))


def _key(kind, target):
    import json
    return kind + ':' + json.dumps(target, sort_keys=True, separators=(',', ':'))


def _valid_target(world, kind, target):
    if not isinstance(target, dict): return False
    rooms = world.rooms; details = getattr(world, 'room_details', {})
    if kind == 'routes':
        source, di, dest = (target.get(k) for k in ('source', 'direction', 'destination'))
        return all(isinstance(v, str) for v in (source, di, dest)) and source in rooms and dest in rooms and rooms[source].exits.get(di) == dest
    if kind == 'structures':
        if 'building' in target:
            b = getattr(world, 'buildings', {}).get(target['building']) if isinstance(target['building'], str) else None
            br = target.get('rooms')
            return isinstance(b, dict) and isinstance(br, list) and bool(br) and all(isinstance(r, str) and r in rooms for r in br) and b.get('rooms') == br
        rid = target.get('room')
        return isinstance(rid, str) and rid in rooms and structural_site(details.get(rid, {}))
    if kind == 'resources':
        rid, resource = target.get('room'), target.get('resource')
        return isinstance(rid, str) and isinstance(resource, str) and rid in rooms and resource in getattr(world, 'resources', {}) and resource in details.get(rid, {}).get('resources', [])
    if kind == 'port_routes':
        origin, dest = target.get('origin'), target.get('destination')
        if not isinstance(origin, str) or not isinstance(dest, str): return False
        port = details.get(origin, {}).get('port', {})
        return origin in rooms and dest in rooms and port.get('enabled') is True and details.get(dest, {}).get('port', {}).get('enabled') is True and any(r.get('to') == dest for r in port.get('routes', []) if isinstance(r, dict))
    return False


def _valid_record(world, row):
    return (isinstance(row, dict) and row.get('kind') in FIELDS[1:] and
            _valid_target(world, row['kind'], row.get('target')) and
            all(_number(row.get(k)) for k in ('started', 'until', 'grace_until')) and
            row['started'] < row['until'] <= row['started'] + MAX_CLOSURE and
            row['until'] <= row['grace_until'] <= row['until'] + RECOVERY_GRACE and
            _number(row.get('severity'), 0, 1) and _number(row.get('loss', 0), 0, 50) and
            isinstance(row.get('event_id'), str) and row.get('type') in ('quake', 'eruption', 'flood', 'tsunami', 'storm'))


def _records(world, minute=None):
    s = _state(world); now = _now(world) if minute is None else minute
    if s is None or now is None: return []
    return [r for r in islice(s['impacts'].values(), MAX_IMPACTS)
            if _valid_record(world, r) and r['started'] <= now < r['until']]


def _index(world):
    s = _state(world); now = _now(world)
    if s is None or now is None: return {}
    signature = (id(s), id(s['impacts']), id(s['events']), now)
    cached = _INDEX_CACHE.get(world)
    if cached is not None and cached[0] == signature: return cached[1]
    index = {'routes': {}, 'resources': {}, 'structures': {}, 'port_routes': {}, 'local': {}}
    for row in _records(world):
        kind, t = row['kind'], row['target']
        if kind == 'routes': keys = [(t['source'], t['direction'], t['destination'])]; rooms = [t['source']]
        elif kind == 'resources': keys = [(t['room'], t['resource'])]; rooms = [t['room']]
        elif kind == 'port_routes': keys = [(t['origin'], t['destination'])]; rooms = [t['origin']]
        else: keys = rooms = _structure_rooms(row)
        for key in keys: index[kind].setdefault(key, []).append(row)
        for rid in rooms: index['local'].setdefault(rid, []).append(row)
    index['route_sources'] = frozenset(key[0] for key in index['routes'])
    _INDEX_CACHE[world] = (signature, index)
    return index


def _alternate(world, start, goal, blocked):
    """Conservative universal path: no gate, boat, actor permission or new edge."""
    if start not in world.rooms or goal not in world.rooms: return False
    q = deque([(start, 0)]); seen = {start}; details = getattr(world, 'room_details', {})
    while q and len(seen) <= MAX_ROUTE_ROOMS:
        current, depth = q.popleft()
        if current == goal: return True
        if depth >= MAX_ROUTE_STEPS: continue
        rd = details.get(current, {})
        for di, dest in world.rooms[current].exits.items():
            if dest not in world.rooms or dest in seen or (current, di, dest) in blocked: continue
            if rd.get('gates', {}).get(di) or details.get(dest, {}).get('requires_boat'): continue
            seen.add(dest); q.append((dest, depth + 1))
    return False


def _safe_closures(world, records):
    edges = {(r['target']['source'], r['target']['direction'], r['target']['destination']) for r in records if r['kind'] == 'routes'}
    impaired_ports = set()
    for r in records:
        t = r['target']
        if r['kind'] == 'routes' and not _alternate(world, t['source'], t['destination'], edges): return False
        if r['kind'] == 'port_routes' and not _alternate(world, t['origin'], t['destination'], edges): return False
        if r['kind'] == 'structures' and r.get('loss', 0) > 25:
            impaired_ports.update(_structure_rooms(r))
    # Unsafe port structures still need emergency service when a boat is the
    # only way out. Conservative proof includes both incoming and outgoing legs.
    if impaired_ports:
        for origin, rd in getattr(world, 'room_details', {}).items():
            port = rd.get('port', {})
            if not isinstance(port, dict) or not port.get('enabled'): continue
            for leg in port.get('routes', []):
                dest = leg.get('to') if isinstance(leg, dict) else None
                if (origin in impaired_ports or dest in impaired_ports) and not _alternate(world, origin, dest, edges): return False
    return True


def _outcome(s, **values):
    s['outcomes'] = (s['outcomes'] + [values])[-MAX_OUTCOMES:]


def _pause_rent(world, row, minute):
    """Account for real unavailable housing even inside a long clock advance."""
    if row['kind'] != 'structures' or row['loss'] <= 25: return
    # Condition increases linearly; facilities reopen at 75, before full repair.
    end = row['started'] + (row['until'] - row['started']) * (1 - 25 / row['loss'])
    units = getattr(world, 'living_state', {}).get('settlements', {}).get('units', {})
    if not isinstance(units, dict): return
    affected = _structure_rooms(row)
    for unit in units.values():
        if not isinstance(unit, dict) or unit.get('room') not in affected or not unit.get('tenant'): continue
        if not _number(unit.get('due')): continue
        previous = unit.get('geology_rent_pause_until', minute)
        if not _number(previous): previous = minute
        duration = max(0, math.ceil(end - max(minute, previous)))
        if duration:
            unit['due'] += duration
            unit['geology_rent_pause_until'] = max(previous, end)


def on_event(world, event, source_row=None):
    """Consume a newly emitted snapshotted event once, never the visual log.

    on_event does not injure anyone: actor location is known only at the current
    clock hook. Physical overlays are processed at actual event timestamps.
    """
    from engine import geology_events
    now = _now(world)
    if now is None or not geology_events._valid_event(event): return
    plan = event.get('consequences')
    serial = _serial(event)
    if not serial or not isinstance(plan, dict): return  # Legacy saved events stay visual-only.
    referenced = set(event['rooms'])
    for kind in ('routes', 'port_routes'):
        rows = plan.get(kind, [])
        if isinstance(rows, list):
            referenced.update(r['destination'] for r in rows[:MAX_TARGETS] if isinstance(r, dict) and isinstance(r.get('destination'), str))
    if validate_plan(world_data(world, referenced), plan, event['rooms']): return
    if getattr(world, 'realtime', False) and not getattr(world, 'tick_authorized', False): return
    s = _state(world, True)
    if s is None: return
    highwater = s.get('highwater', 0)
    if type(highwater) is not int or not 0 <= highwater <= 10**15: highwater = 0
    if serial <= highwater: return
    s['highwater'] = serial
    minute = event['started_minute']; severity = _severity(event)
    # Current exposures are independent of visual event replacement/expiry.
    s['events'] = [e for e in s['events'] if isinstance(e, dict) and _number(e.get('active_until')) and e['active_until'] > minute]
    seed = getattr(world, 'metadata', {}).get('geology', {}).get('seed', 0)
    s['events'] = (s['events'] + [dict(id=event['id'], serial=serial, type=event['type'],
        started=minute, active_until=event['active_until'], severity=severity, seed=seed,
        plan=deepcopy(plan))])[-MAX_EXPOSURES:]
    # Preserve records through the reopening grace period, never extend forever.
    s['impacts'] = {k: r for k, r in islice(s['impacts'].items(), MAX_IMPACTS) if _valid_record(world, r) and r['grace_until'] > minute}
    if severity < .25: return  # Mild shaking/ash/high water is usually operationally harmless.
    duration = min(MAX_CLOSURE, plan.get('recovery_minutes', 120))
    for kind in FIELDS[1:]:
        for raw in plan.get(kind, []):
            target = deepcopy(raw)
            if kind == 'routes': target['direction'] = direction(target['direction'])
            if kind == 'structures' and 'building' in target:
                target['rooms'] = list(world.buildings[target['building']]['rooms'])
            key = _key(kind, target); old = s['impacts'].get(key)
            if _roll(seed, event['id'], key, 'impairment') >= .35 * severity * severity:
                _outcome(s, event_id=event['id'], target=deepcopy(raw), outcome='unaffected', minute=minute); continue
            if old and old['until'] <= minute < old['grace_until']:
                _outcome(s, event_id=event['id'], target=deepcopy(raw), outcome='recovery_grace', minute=minute); continue
            if old is None and len(s['impacts']) >= MAX_IMPACTS: continue
            start = old['started'] if old else minute
            until = min(start + MAX_CLOSURE, max(old['until'] if old else minute, minute + duration))
            loss = max(old.get('loss', 0) if old else 0, 20 + 30 * severity) if kind == 'structures' else 0
            row = dict(kind=kind, target=target, event_id=event['id'], type=event['type'], started=start,
                       until=until, grace_until=until + RECOVERY_GRACE,
                       severity=max(severity, old['severity'] if old else 0), loss=loss)
            if kind in ('routes', 'port_routes', 'structures'):
                others = [r for k, r in s['impacts'].items() if k != key and r['started'] <= minute < r['until']]
                if not _safe_closures(world, others + [row]):
                    if kind == 'structures':
                        row['loss'] = min(25, row['loss'])  # Emergency port access stays usable.
                    else:
                        _outcome(s, event_id=event['id'], target=deepcopy(raw), outcome='kept_open_for_escape', minute=minute); continue
            s['impacts'][key] = row
            _pause_rent(world, row, minute)
            _outcome(s, event_id=event['id'], target=deepcopy(raw), outcome='impaired', minute=minute)


def _valid_exposure(e):
    return (isinstance(e, dict) and isinstance(e.get('id'), str) and type(e.get('serial')) is int and
            0 < e['serial'] <= 10**15 and e.get('type') in ('quake', 'eruption', 'flood', 'tsunami') and _number(e.get('seed', 0), 0, 2**63-1) and _number(e.get('started')) and _number(e.get('active_until')) and
            0 < e['active_until'] - e['started'] <= 1440 and _number(e.get('severity'), 0, 1) and
            isinstance(e.get('plan'), dict) and isinstance(e['plan'].get('actor_exposure', []), list) and
            len(e['plan'].get('actor_exposure', [])) <= MAX_TARGETS and
            all(isinstance(r, dict) and isinstance(r.get('room'), str) and _number(r.get('exposure'), 0, 1) for r in e['plan'].get('actor_exposure', [])))


def _local_exposures(s, rid, now):
    return [(e, r['exposure']) for e in s['events'][-MAX_EXPOSURES:] if _valid_exposure(e) and e['started'] <= now < e['active_until']
            for r in e['plan'].get('actor_exposure', []) if r['room'] == rid]


def _valid_actor(a):
    return (isinstance(a, dict) and type(a.get('last_event')) is int and a['last_event'] >= 0 and
            _number(a.get('debt')) and _number(a.get('last_seen')) and _number(a.get('safe_credit'), 0, 1) and
            isinstance(a.get('budget'), list) and len(a['budget']) <= 128 and
            all(isinstance(b, list) and len(b) == 2 and _number(b[0]) and _number(b[1]) for b in a['budget']))


def retire_wounds(world, actor, healed_amount):
    """Called AFTER ordinary healing; retire debt without healing a second time."""
    s = _state(world)
    if s is None or not _number(healed_amount) or healed_amount <= 0: return
    a = s['actors'].get(actor.id)
    if _valid_actor(a): a['debt'] = max(0, a['debt'] - healed_amount)


def reconcile(world):
    """Bound/sanitize restored own state; never retrofit plans onto old events."""
    s = _state(world); now = _now(world)
    if s is None or now is None: return
    s['highwater'] = s.get('highwater', 0) if type(s.get('highwater')) is int and 0 <= s['highwater'] <= 10**15 else 0
    s['last_minute'] = s.get('last_minute', -1) if type(s.get('last_minute')) is int and -1 <= s['last_minute'] <= now else now
    s['events'] = [e for e in s['events'][-MAX_EXPOSURES:] if _valid_exposure(e) and e['active_until'] > now]
    s['impacts'] = {k: r for k, r in islice(s['impacts'].items(), MAX_IMPACTS) if isinstance(k, str) and _valid_record(world, r) and r['grace_until'] > now}
    # Storm routes also require the stricter public-detour proof after Creator edits.
    active=_records(world)
    s['impacts']={k:r for k,r in s['impacts'].items() if _storm_route_safe(world,r,active)}
    # A creator edit can remove an alternate path after the closure was accepted.
    # Release those closures rather than stranding anyone under the new graph.
    if not _safe_closures(world, _records(world)):
        s['impacts'] = {k: r for k, r in s['impacts'].items() if r['kind'] not in ('routes', 'port_routes')}
        if not _safe_closures(world, _records(world)):
            for row in s['impacts'].values():
                if row['kind'] == 'structures': row['loss'] = min(25, row['loss'])
    s['actors'] = {k: a for k, a in islice(s['actors'].items(), MAX_ACTORS) if isinstance(k, str) and _valid_actor(a)}
    s['outcomes'] = [r for r in s['outcomes'][-MAX_OUTCOMES:] if isinstance(r, dict)]


def advance(world, minutes=1):
    """One current contact roll per actor, plus recovery even with sources off."""
    now = _now(world); s = _state(world)
    if s is None or now is None or not _number(minutes) or minutes <= 0: return []
    if getattr(world, 'realtime', False) and not getattr(world, 'tick_authorized', False): return []
    reconcile(world)
    if s['last_minute'] >= now: return []
    elapsed = min(60, minutes, now - s['last_minute']) if s['last_minute'] >= 0 else min(60, minutes)
    s['last_minute'] = now
    messages = []
    exposures = {}
    for event in s['events']:
        if _valid_exposure(event) and event['started'] <= now < event['active_until']:
            for row in event['plan'].get('actor_exposure', []):
                exposures.setdefault(row['room'], []).append((event, row['exposure']))
    if not exposures and not s['actors']:return messages  # Physical-only storms need no population scan.
    for actor in list(getattr(world, 'entities', {}).values()):
        if not actor.alive or actor.location not in world.rooms or not _number(actor.max_hp, 1): continue
        local = exposures.get(actor.location, [])
        a = s['actors'].get(actor.id)
        if a is None:
            if not local or len(s['actors']) >= MAX_ACTORS: continue  # Fail safe, no untracked injury.
            a = dict(last_event=0, debt=0, last_seen=now, safe_credit=0., budget=[])
            s['actors'][actor.id] = a
        a['last_seen'] = now
        a['budget'] = [b for b in a['budget'] if b[0] > now - MINUTES_PER_DAY]
        a['debt'] = min(a['debt'], max(0, actor.max_hp - actor.hp), math.floor(actor.max_hp * .25))
        # Recovery pays only the outstanding geological wound, never unrelated HP.
        safe = not any(e['severity'] * exposure > 0 for e, exposure in local)
        if safe and a['debt'] > 0:
            a['safe_credit'] += elapsed * actor.max_hp * .25 / MINUTES_PER_DAY
            healed = min(int(a['safe_credit']), a['debt'], max(0, actor.max_hp - actor.hp))
            if healed > 0:
                actor.hp += healed; a['debt'] -= healed
                if actor.is_player: world.__dict__.setdefault('dirty_players', set()).add(actor.id)
            a['safe_credit'] %= 1
        if not local: continue
        event, exposure = max(local, key=lambda pair: pair[0]['serial'])
        if event['serial'] <= a['last_event']: continue
        a['last_event'] = event['serial']  # Failed/no-risk rolls also consume this opportunity.
        risk = .12 * event['severity'] * exposure
        damage = 0
        safe_until = actor.progress.get('geology_safe_until', 0)
        protected = _number(safe_until) and safe_until > now
        if not protected and _roll(event.get('seed', 0), event['id'], actor.id, 'injury') < risk:
            fraction = (.02 + .08 * _roll(event.get('seed', 0), event['id'], actor.id, 'damage')) * event['severity'] * exposure
            budget = max(0, math.floor(actor.max_hp * .25) - sum(b[1] for b in a['budget']))
            debt_cap = max(0, math.floor(actor.max_hp * .25) - a['debt'])
            # Floor, never round up low HP to an oversized one-point injury.
            damage = int(min(math.floor(actor.max_hp * fraction), math.floor(actor.max_hp * .15), budget, debt_cap))
            if len(a['budget']) >= 128: damage = 0
        actual = 0
        if damage > 0:
            from engine import mortality
            actual = mortality.environmental_damage(world, actor, damage,
                    'geological ' + event['type'], event_id=event['id'])
            actual = max(0, min(damage, actual))
            a['debt'] = a['debt'] + actual if actor.alive else 0
            if actual: a['budget'].append([now, actual])
            if actual: messages.append((actor.location, actor.name + ' suffers ' + str(actual) + ' damage from the ' + event['type'] + '.'))
        _outcome(s, event_id=event['id'], actor=actor.id, room=actor.location,
                 outcome='injury' if actual else 'unharmed', damage=actual, minute=now)
    # Absent identities can age out only after every current exposure and daily
    # budget has elapsed. Outstanding wounds remain until a real heal/death.
    for ident, a in list(s['actors'].items()):
        actor = getattr(world, 'entities', {}).get(ident)
        deaths = getattr(world, 'living_state', {}).get('mortality', {}).get('deaths', {})
        if (actor is not None and not actor.alive) or (actor is None and ident in deaths): a['debt'] = 0
        if ident not in world.entities and a['debt'] <= 0 and now - a['last_seen'] > MINUTES_PER_DAY + 1440:
            del s['actors'][ident]
    return messages


def _reason(row):
    return 'Temporarily closed by ' + row['type'] + ' damage; repairs are underway.'


def route_sources(world):
    """Pure conservative source IDs for pathfinder hot loops."""
    return _index(world).get('route_sources', frozenset())


def has_route_closures(world):
    """Pure conservative fast-path hint; actual edges still use route_blocked."""
    return bool(_index(world).get('routes'))


def _storm_route_safe(world,row,records):
    if row.get('type')!='storm' or row.get('kind')!='routes':return True
    from engine.storm_damage import public_detour
    target=row['target']
    return public_detour(world,target['source'],target['destination'],records)


def route_blocked(world, source, exit_direction, destination=None, actor=None):
    try: di = direction(exit_direction)
    except ValueError: return ''
    if source not in world.rooms: return ''
    dest = world.rooms[source].exits.get(di) if destination is None else destination
    matches = [r for r in _index(world).get('routes', {}).get((source, di, dest), []) if _valid_record(world, r)]
    if not matches: return ''
    records = _records(world)
    matches=[r for r in matches if _storm_route_safe(world,r,records)]
    # Pure fail-open verification also covers topology edited between clock hooks.
    if matches and _safe_closures(world, records): return _reason(matches[0])
    return ''


def _structure_rooms(row):
    t = row['target']
    return t.get('rooms', [t.get('room')])


def _condition(row, now):
    fraction = (row['until'] - now) / max(1, row['until'] - row['started'])
    return round(100 - row.get('loss', 0) * max(0, min(1, fraction)), 1)


def room_unusable(world, rid):
    now = _now(world)
    unusable = now is not None and any(_valid_record(world, r) and _condition(r, now) < 75 for r in _index(world).get('structures', {}).get(rid, []))
    if unusable and getattr(world, 'room_details', {}).get(rid, {}).get('port', {}).get('enabled'):
        return _safe_closures(world, _records(world))
    return unusable


def resource_blocked(world, rid, resource_id):
    for row in _index(world).get('resources', {}).get((rid, resource_id), []):
        if _valid_record(world, row): return _reason(row)
    return ''


def port_blocked(world, origin, destination):
    if room_unusable(world, origin) or room_unusable(world, destination):
        return 'The port service is temporarily closed for hazard repairs.'
    matches = [r for r in _index(world).get('port_routes', {}).get((origin, destination), []) if _valid_record(world, r)]
    if matches and _safe_closures(world, _records(world)): return _reason(matches[0])
    return ''


def room_view(world, rid):
    """Read-only local projection, with no actor/owner/tenant/stock information."""
    result = dict(unusable=False, condition=100, remaining_minutes=0, structures=[], routes=[], resources=[], port_routes=[], effects=[])
    now = _now(world); s = _state(world)
    if s is None or now is None or rid not in world.rooms: return result
    for row in _index(world).get('local', {}).get(rid, []):
        if not _valid_record(world, row): continue
        t = row['target']; kind = row['kind']
        local = (rid in _structure_rooms(row) if kind == 'structures' else
                 t.get('source') == rid if kind == 'routes' else
                 t.get('origin') == rid if kind == 'port_routes' else t.get('room') == rid)
        if not local: continue
        if kind in ('routes', 'port_routes') and (not _safe_closures(world, _records(world)) or not _storm_route_safe(world,row,_records(world))): continue
        item = dict(event_id=row['event_id'], type=row['type'], remaining_minutes=max(0, math.ceil(row['until'] - now)))
        if kind == 'structures':
            condition = _condition(row, now)
            if condition < 75 and getattr(world, 'room_details', {}).get(rid, {}).get('port', {}).get('enabled') and not _safe_closures(world, _records(world)):
                condition = 75
            item.update(kind='structure', target={k:v for k,v in t.items() if k != 'rooms'}, condition=condition, unusable=condition < 75)
            result['condition'] = min(result['condition'], condition)
            result['unusable'] |= item['unusable']
        else: item.update(deepcopy(t))
        result[kind].append(item)
        result['remaining_minutes'] = max(result['remaining_minutes'], item['remaining_minutes'])
    for event, exposure in _local_exposures(s, rid, now):
        item = dict(event_id=event['id'], type=event['type'], exposure=exposure, remaining_minutes=max(0, math.ceil(event['active_until'] - now)))
        result['effects'].append(item)
        result['remaining_minutes'] = max(result['remaining_minutes'], item['remaining_minutes'])
    return result


def apply_weather_damage(world, kind, target, event_id, severity, recovery, detour):
    """Shared physical repairs only: never creates an actor exposure event.

    Weather owns separate keys and never strengthens, extends or replaces any
    existing physical record for the same target, including geological damage.
    """
    now=_now(world)
    if now is None or kind not in ('structures','routes','resources') or not isinstance(target,dict):return False
    if not _number(severity,0,1) or type(recovery) is not int or not 30<=recovery<=240 or not isinstance(event_id,str):return False
    target=deepcopy(target)
    if kind=='structures' and 'building' in target:
        building=getattr(world,'buildings',{}).get(target['building'],{})
        target['rooms']=list(building.get('rooms',[]))
    if not _valid_target(world,kind,target):return False
    s=_state(world,True)
    if s is None:return False
    target=deepcopy(target)
    if kind=='structures' and 'building' in target:target['rooms']=list(world.buildings[target['building']]['rooms'])
    canonical=_key(kind,target)
    site=set(target.get('rooms',[target.get('room')])) if kind=='structures' else set()
    if any(_valid_record(world,r) and r['grace_until']>now and
           (_key(r['kind'],r['target'])==canonical or
            (kind=='structures' and r['kind']=='structures' and site.intersection(_structure_rooms(r))))
           for r in s['impacts'].values()):return False
    if len(s['impacts'])>=MAX_IMPACTS:return False
    recovery=min(MAX_CLOSURE,max(30,int(recovery)))
    row=dict(kind=kind,target=target,event_id=event_id,type='storm',started=now,until=now+recovery,grace_until=now+recovery+RECOVERY_GRACE,severity=severity,loss=20+15*severity if kind=='structures' else 0)
    records=_records(world)+[row]
    if not _safe_closures(world,records):return False
    if kind=='routes' and not detour(world,target['source'],target['destination'],records):return False
    # Replace only the dictionary shell to invalidate the pure derived view cache.
    s['impacts']={**s['impacts'],'weather:'+canonical:row}
    _pause_rent(world,row,now)
    _outcome(s,event_id=event_id,target=deepcopy(target),outcome='storm_impairment',minute=now)
    return True
