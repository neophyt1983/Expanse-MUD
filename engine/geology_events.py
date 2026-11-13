"""Optional, bounded geological events, driven only by the living-world clock.

This is a game simulation, not an earthquake forecast. Explicit authored sources
and room lists determine all effects. Sources without explicit consequences stay
visual-only. Consequences use separate bounded state and RNG; source timing and
causality remain unchanged. Both survive the normal living snapshot.
"""
from copy import deepcopy
from engine.worldtime import initial_minute
import hashlib
import math
import re

MAX_SOURCES = 32                 # Per source category.
MAX_ROOMS = 128                  # Per source / coastal-target list.
MAX_CATCHUP_MINUTES = 360         # Drop older missed simulation, never replay it.
MAX_EVENTS = 128
MAX_LOG = 128
MAX_DURATION = 1440
MAX_RECOVERY = 10080
_MASK = (1 << 64) - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_KINDS = ('faults', 'volcanoes', 'basins')
_EVENT_TYPES = ('quake', 'eruption', 'flood', 'tsunami')
_COMMON_SOURCE_FIELDS = {'id', 'rooms', 'duration_minutes', 'recovery_minutes', 'consequences'}
_SOURCE_FIELDS = {
    'faults': _COMMON_SOURCE_FIELDS | {
        'initial_tension', 'tension_rate', 'quake_rate', 'magnitude_b',
        'min_magnitude', 'max_magnitude', 'tsunami'},
    'volcanoes': _COMMON_SOURCE_FIELDS | {
        'rate', 'fault_id', 'fault_boost', 'min_intensity', 'max_intensity'},
    'basins': _COMMON_SOURCE_FIELDS | {
        'source', 'storm_rate', 'flood_chance', 'initial_snowpack', 'weather_region',
        'min_intensity', 'max_intensity'},
}
_TSUNAMI_FIELDS = {'source', 'min_magnitude', 'chance', 'coastal_rooms',
                   'duration_minutes', 'recovery_minutes', 'consequences'}


def _number(value, low, high):
    # Reject bool, numeric strings, NaN, infinity and huge JSON integers.
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def enabled(world):
    meta = getattr(world, 'metadata', {})
    cfg = meta.get('geology') if isinstance(meta, dict) else None
    return isinstance(cfg, dict) and cfg.get('enabled') is True


def validate(data, metadata):
    """Return creator-facing issues; malformed optional configuration never throws."""
    if not isinstance(metadata, dict):
        return ['metadata must be an object']
    if 'geology' not in metadata:
        return []
    cfg = metadata['geology']
    if not isinstance(cfg, dict):
        return ['metadata.geology must be an object']
    issues = []
    for key in cfg:
        if key not in ('enabled', 'seed', 'faults', 'volcanoes', 'basins'):
            issues.append(f'metadata.geology: unknown field {key!r}')
    rooms = {r['id'] for r in data.get('room', [])
             if isinstance(r, dict) and isinstance(r.get('id'), str)}
    def issue(where, text):
        issues.append(where + ': ' + text)
    def allowed_fields(row, allowed, where):
        for key in row:
            if key not in allowed:
                issue(where, f'unknown field {key!r}; allowed fields: ' + ', '.join(sorted(allowed)))
    def number(row, field, default, low, high, where, integer=False):
        value = row.get(field, default)
        if (integer and type(value) is not int) or not _number(value, low, high):
            issue(where, f'{field} must be a finite {"integer" if integer else "number"} from {low} to {high}')
    def room_list(row, field, where):
        value = row.get(field)
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_ROOMS:
            issue(where, f'{field} must list 1–{MAX_ROOMS} explicit room IDs')
            return
        seen = set()
        for rid in value:
            if not isinstance(rid, str) or rid not in rooms:
                issue(where, f'{field} references an unknown room {rid!r}')
            elif rid in seen:
                issue(where, f'{field} contains duplicate room {rid!r}')
            else:
                seen.add(rid)
    def durations(row, where):
        number(row, 'duration_minutes', 5, 1, MAX_DURATION, where, True)
        number(row, 'recovery_minutes', 30, 0, MAX_RECOVERY, where, True)
    def intensity(row, where):
        number(row, 'min_intensity', .2, 0, 1, where)
        number(row, 'max_intensity', .9, 0, 1, where)
        lo, hi = row.get('min_intensity', .2), row.get('max_intensity', .9)
        if _number(lo, 0, 1) and _number(hi, 0, 1) and lo > hi:
            issue(where, 'min_intensity must not exceed max_intensity')
    if type(cfg.get('enabled', False)) is not bool:
        issue('metadata.geology', 'enabled must be a boolean')
    number(cfg, 'seed', 0, 0, (1 << 63) - 1, 'metadata.geology', True)
    ids = set()
    fault_ids = set()
    links = []
    for kind in _KINDS:
        rows = cfg.get(kind, [])
        if not isinstance(rows, list) or len(rows) > MAX_SOURCES:
            issue('metadata.geology', f'{kind} must be a list of at most {MAX_SOURCES} sources')
            continue
        for index, row in enumerate(rows):
            where = f'metadata.geology.{kind}[{index}]'
            if not isinstance(row, dict):
                issue(where, 'source must be an object')
                continue
            allowed_fields(row, _SOURCE_FIELDS[kind], where)
            ident = row.get('id')
            if not isinstance(ident, str) or not _ID.fullmatch(ident):
                issue(where, 'id must be 1–64 letters, digits, underscores or hyphens, beginning with a letter or digit')
            else:
                if ident in ids:
                    issue(where, f'duplicate geological source ID {ident!r}')
                ids.add(ident)
                if kind == 'faults':
                    fault_ids.add(ident)
            room_list(row, 'rooms', where)
            durations(row, where)
            if 'consequences' in row:
                from engine.geology_impacts import validate_plan
                issues.extend(validate_plan(data, row['consequences'], row.get('rooms'), where + '.consequences'))
            if kind == 'faults':
                number(row, 'initial_tension', .1, 0, 1, where)
                number(row, 'tension_rate', .005, 0, 1, where)
                number(row, 'quake_rate', .01, 0, 1, where)
                number(row, 'magnitude_b', 1, .1, 3, where)
                number(row, 'min_magnitude', 2, 0, 9.9, where)
                number(row, 'max_magnitude', 6, 0, 9.9, where)
                lo, hi = row.get('min_magnitude', 2), row.get('max_magnitude', 6)
                if _number(lo, 0, 9.9) and _number(hi, 0, 9.9) and lo > hi:
                    issue(where, 'min_magnitude must not exceed max_magnitude')
                if 'tsunami' in row:
                    tsunami = row['tsunami']
                    target = where + '.tsunami'
                    if not isinstance(tsunami, dict):
                        issue(target, 'must be an object')
                    else:
                        allowed_fields(tsunami, _TSUNAMI_FIELDS, target)
                        if tsunami.get('source') not in ('offshore_displacement', 'seafloor_displacement'):
                            issue(target, 'source must explicitly declare offshore_displacement or seafloor_displacement')
                        room_list(tsunami, 'coastal_rooms', target)
                        # Threshold and chance must be deliberately authored, not inferred.
                        number(tsunami, 'min_magnitude', None, 0, 9.9, target)
                        number(tsunami, 'chance', None, 0, 1, target)
                        durations(tsunami, target)
                        if 'consequences' in tsunami:
                            from engine.geology_impacts import validate_plan
                            issues.extend(validate_plan(data, tsunami['consequences'], tsunami.get('coastal_rooms'), target + '.consequences'))
            elif kind == 'volcanoes':
                number(row, 'rate', .005, 0, 1, where)
                number(row, 'fault_boost', 1, 0, 4, where)
                if 'fault_id' in row:
                    links.append((where, row['fault_id']))
                intensity(row, where)
            else:
                if row.get('source') not in ('heavy_rain', 'river_overflow', 'snowmelt'):
                    issue(where, 'source must explicitly declare heavy_rain, river_overflow or snowmelt')
                if 'weather_region' in row:
                    weather_cfg=metadata.get('regional_weather',{})
                    regions=weather_cfg.get('regions',[]) if isinstance(weather_cfg,dict) else []
                    ids={r.get('id') for r in regions if isinstance(r,dict) and isinstance(r.get('id'),str)} if isinstance(regions,list) else set()
                    if row.get('source')!='heavy_rain' or not isinstance(row['weather_region'],str) or row['weather_region'] not in ids:
                        issue(where, 'weather_region requires heavy_rain and an explicitly configured weather region')
                number(row, 'initial_snowpack', 0, 0, 1, where)
                number(row, 'storm_rate', .01, 0, 1, where)
                number(row, 'flood_chance', .4, 0, 1, where)
                intensity(row, where)
    for where, ident in links:
        if not isinstance(ident, str) or ident not in fault_ids:
            issue(where, f'fault_id references an unknown fault {ident!r}')
    return issues


class _Rng:
    """SplitMix64: fixed portable 64-bit state, with 53-bit uniform outputs."""
    def __init__(self, value):
        self.value = value & _MASK

    def random(self):
        self.value = (self.value + 0x9E3779B97F4A7C15) & _MASK
        z = self.value
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        z ^= z >> 31
        return (z >> 11) / float(1 << 53)

    def uniform(self, low, high):
        return low + (high - low) * self.random()

    def magnitude(self, low, high, b):
        # Truncated Gutenberg–Richter-like tail: many small events, few large.
        # b is a game tuning parameter; this is not a forecast or fitted model.
        if low == high:
            return low
        beta = math.log(10) * b
        mass = -math.expm1(-beta * (high - low))
        return low - math.log1p(-self.random() * mass) / beta


def _seed(seed, key):
    return int.from_bytes(hashlib.sha256(f'geology-v1:{seed}:{key}'.encode()).digest()[:8], 'big')


def _probability(rate):
    # No finite risk/tension creates a guaranteed event on the next minute.
    return min(.95, -math.expm1(-rate))


def _valid_event(event):
    if not isinstance(event, dict) or event.get('type') not in _EVENT_TYPES:
        return False
    if not isinstance(event.get('source_id'), str) or not isinstance(event.get('id'), str):
        return False
    rooms = event.get('rooms')
    if not isinstance(rooms, list) or not 1 <= len(rooms) <= MAX_ROOMS or any(not isinstance(r, str) for r in rooms):
        return False
    times = [event.get(k) for k in ('started_minute', 'active_until', 'recovery_until')]
    if any(not _number(t, 0, 10**15) for t in times) or not times[0] < times[1] <= times[2]:
        return False
    key, limit = ('magnitude', 9.9) if event['type'] == 'quake' else ('intensity', 1)
    return _number(event.get(key), 0, limit)


def _emit(world, state, row, kind, minute, **values):
    state['counter'] += 1
    event = dict(id=f'geo-{state["counter"]}', type=kind, source_id=row['id'],
                 rooms=list(row['rooms']), started_minute=minute,
                 active_until=minute + row.get('duration_minutes', 5),
                 recovery_until=minute + row.get('duration_minutes', 5) + row.get('recovery_minutes', 30),
                 **values)
    if 'consequences' in row:
        event['consequences'] = deepcopy(row['consequences'])
        from engine import geology_impacts
        geology_impacts.on_event(world, event, row)
    # A new event replaces its source's earlier recovery visuals, not its history.
    state['events'] = [e for e in state['events'] if (e['source_id'], e['type']) != (row['id'], kind)]
    state['events'] = (state['events'] + [event])[-MAX_EVENTS:]
    state['log'] = (state['log'] + [dict(event, rooms=list(event['rooms']))])[-MAX_LOG:]
    from engine import gazette
    gazette.geological_dispatch(world, event)
    return event


def _busy(state, kind, ident, minute):
    return any(e['type'] == kind and e['source_id'] == ident and e['active_until'] > minute
               for e in state['events'])


def advance(world, minutes=1):
    """Clock hook. Only living.advance calls this; all visual queries are pure.

    Long gaps simulate only the most recent six hours and record skipped_minutes.
    No events are fabricated for the skipped interval. Existing events expire by
    absolute world time, including when all source rates have been set to zero.
    """
    if not enabled(world) or not _number(minutes, 0, 10**15) or minutes <= 0:
        return
    if getattr(world, 'realtime', False) and not getattr(world, 'tick_authorized', False):
        return
    living_state = getattr(world, 'living_state', None)
    if not isinstance(living_state, dict):
        return
    now = living_state.get('minute')
    if not _number(now, 0, 10**15):
        return
    cfg = world.metadata['geology']
    from engine.geology_impacts import world_data
    if validate(world_data(world), world.metadata):
        return  # Creator validation explains errors; malformed content is inert.
    end = math.floor(now)
    old = living_state.get('geology', {})
    if not isinstance(old, dict) or old.get('version') != 1:
        old = {}
    last = old.get('last_minute', max(0, math.floor(now - minutes)))
    if type(last) is not int or not 0 <= last <= end:
        last = max(0, math.floor(now - minutes))
    # Repeated zero-time clock hooks must not sample the same minute again.
    if last >= end:
        return
    start = max(last, end - MAX_CATCHUP_MINUTES)
    sources = old.get('sources', {})
    if not isinstance(sources, dict):
        sources = {}
    state = dict(version=1, last_minute=end, sources={}, events=[], log=[],
                 counter=old.get('counter', 0), skipped_minutes=old.get('skipped_minutes', 0),
                 drivers=[], driver_counter=old.get('driver_counter', 0))
    for field in ('counter', 'skipped_minutes', 'driver_counter'):
        if type(state[field]) is not int or not 0 <= state[field] <= 10**15:
            state[field] = 0
    state['skipped_minutes'] += start - last
    for field, limit in (('events', MAX_EVENTS), ('log', MAX_LOG)):
        rows = old.get(field, [])
        if isinstance(rows, list):
            state[field] = [dict(e, rooms=list(e['rooms'])) for e in rows[-limit:]
                            if _valid_event(e) and (field == 'log' or e['recovery_until'] > start)]
    old_drivers = old.get('drivers', [])
    if isinstance(old_drivers, list):
        state['drivers'] = [dict(d) for d in old_drivers[-MAX_LOG:]
                            if isinstance(d, dict) and isinstance(d.get('id'), str)
                            and d.get('type') in ('rainstorm', 'upstream_storm', 'thaw')
                            and _number(d.get('minute'), 0, 10**15)]
    rngs = {}
    for kind in _KINDS:
        for row in cfg.get(kind, []):
            key = kind + ':' + row['id']
            source = sources.get(key, {})
            if not isinstance(source, dict):
                source = {}
            value = source.get('rng', _seed(cfg.get('seed', 0), key))
            if type(value) is not int or not 0 <= value <= _MASK:
                value = _seed(cfg.get('seed', 0), key)
            rngs[key] = _Rng(value)
            record = dict(rng=value)
            if kind == 'faults':
                tension = source.get('tension', row.get('initial_tension', .1))
                record['tension'] = tension if _number(tension, 0, 1) else row.get('initial_tension', .1)
            if kind == 'basins' and row['source'] == 'snowmelt':
                snowpack = source.get('snowpack', row.get('initial_snowpack', 0))
                record['snowpack'] = snowpack if _number(snowpack, 0, 1) else 0
            if kind=='basins' and isinstance(source.get('last_weather_front'),str):record['last_weather_front']=source['last_weather_front']
            state['sources'][key] = record
    for minute in range(start + 1, end + 1):
        state['events'] = [e for e in state['events'] if e['recovery_until'] > minute]
        shocks = {}
        for row in cfg.get('faults', []):
            key = 'faults:' + row['id']
            rng, source = rngs[key], state['sources'][key]
            tension = min(1, source['tension'] + row.get('tension_rate', .005))
            source['tension'] = tension
            if _busy(state, 'quake', row['id'], minute):
                continue
            if rng.random() >= _probability(row.get('quake_rate', .01) * (1 + 4 * tension)):
                continue
            low, high = row.get('min_magnitude', 2), row.get('max_magnitude', 6)
            effective_b = row.get('magnitude_b', 1) * (1 - .3 * tension)
            magnitude = min(high, max(low, round(rng.magnitude(low, high, effective_b), 3)))
            quake = _emit(world, state, row, 'quake', minute, magnitude=magnitude, tension=round(tension, 4))
            source['tension'] *= rng.uniform(.05, .35)
            shocks[row['id']] = magnitude / max(.1, high)
            tsunami = row.get('tsunami')
            if tsunami and magnitude >= tsunami['min_magnitude'] and rng.random() < tsunami['chance']:
                coast = dict(tsunami, id=row['id'], rooms=tsunami['coastal_rooms'])
                _emit(world, state, coast, 'tsunami', minute, intensity=round(min(1, magnitude / 9.9), 3),
                      cause=tsunami['source'], cause_event_id=quake['id'], cause_magnitude=magnitude)
        for row in cfg.get('volcanoes', []):
            key = 'volcanoes:' + row['id']
            rng = rngs[key]
            if _busy(state, 'eruption', row['id'], minute):
                continue
            boost = shocks.get(row.get('fault_id'), 0) * row.get('fault_boost', 1)
            if rng.random() < _probability(row.get('rate', .005) * (1 + boost)):
                _emit(world, state, row, 'eruption', minute,
                      intensity=min(row.get('max_intensity', .9), max(row.get('min_intensity', .2),
                                    round(rng.uniform(row.get('min_intensity', .2), row.get('max_intensity', .9)), 3))),
                      cause='volcanic_activity', fault_influence=bool(boost))
        for row in cfg.get('basins', []):
            key = 'basins:' + row['id']
            rng = rngs[key]
            source = state['sources'][key]
            driver = {'heavy_rain': 'rainstorm', 'river_overflow': 'upstream_storm', 'snowmelt': 'thaw'}[row['source']]
            snowpack_before = source.get('snowpack', 0)
            if driver == 'thaw':
                # Authored snow cover or modeled snowfall is needed before thaw.
                # Explicit minute prevents climate.conditions initializing state.
                from engine import climate
                try:
                    conditions = climate.conditions(world, row['rooms'][0], minute=minute)
                except (TypeError, ValueError, KeyError, OverflowError):
                    continue
                if conditions['weather'] == 'snow' or conditions.get('precipitation') == 'snow':
                    source['snowpack'] = min(1, source['snowpack'] + .01)
                if conditions['temperature_c'] <= 0 or source['snowpack'] <= 0:
                    continue
                snowpack_before = source['snowpack']
                source['snowpack'] = max(0, source['snowpack'] - .002)
            if _busy(state, 'flood', row['id'], minute):
                continue
            weather_driver=None
            if 'weather_region' in row:
                from engine import regional_weather
                weather_driver=regional_weather.rainfall(world,row['weather_region'],minute)
                if not weather_driver or source.get('last_weather_front')==weather_driver['id']:continue
                source['last_weather_front']=weather_driver['id']
            elif rng.random() >= _probability(row.get('storm_rate', .01)):
                continue
            # Store an actual stochastic catchment driver, even if it causes no flood.
            state['driver_counter'] += 1
            driver_record = dict(id=f'geo-driver-{state["driver_counter"]}', type=driver,
                                 source_id=row['id'], minute=minute)
            if weather_driver:
                driver_record['weather_front_id']=weather_driver['id']
                driver_record['rain_mm_h']=weather_driver['rain_mm_h']
            if driver == 'thaw':
                driver_record['snowpack_before'] = round(snowpack_before, 4)
            state['drivers'] = (state['drivers'] + [driver_record])[-MAX_LOG:]
            if rng.random() < row.get('flood_chance', .4):
                _emit(world, state, row, 'flood', minute,
                      intensity=min(row.get('max_intensity', .9), max(row.get('min_intensity', .2),
                                    round(rng.uniform(row.get('min_intensity', .2), row.get('max_intensity', .9)), 3))),
                      cause=row['source'], cause_driver_id=driver_record['id'], cause_driver_type=driver)
    for key, rng in rngs.items():
        state['sources'][key]['rng'] = rng.value
    living_state['geology'] = state


def room_effects(world, rid, minute=None):
    """Fresh local event dicts with recovery info; never creates/changes state/RNG."""
    if not enabled(world) or not isinstance(rid, str) or rid not in world.rooms:
        return []
    living_state = getattr(world, 'living_state', None)
    if not isinstance(living_state, dict):
        return []
    now = living_state.get('minute', initial_minute(world.metadata)) if minute is None else minute
    if not _number(now, 0, 10**15):
        return []
    state = living_state.get('geology')
    if not isinstance(state, dict) or not isinstance(state.get('events'), list):
        return []
    result = []
    for event in state['events'][-MAX_EVENTS:]:
        if not _valid_event(event) or rid not in event['rooms'] or not event['started_minute'] <= now < event['recovery_until']:
            continue
        recovering = now >= event['active_until']
        duration = event['recovery_until'] - event['active_until']
        effect = {key: value for key, value in event.items()
                  if key in ('id', 'type', 'source_id', 'started_minute', 'active_until',
                             'recovery_until', 'magnitude', 'intensity', 'tension', 'cause',
                             'cause_event_id', 'cause_magnitude', 'fault_influence',
                             'cause_driver_id', 'cause_driver_type')
                  and type(value) in (str, int, float, bool)}
        effect.update(phase='recovering' if recovering else 'active',
                      remaining_minutes=max(0, event['recovery_until'] - now),
                      recovery_fraction=round((now - event['active_until']) / duration, 4) if recovering and duration else 0)
        result.append(effect)
    return result
