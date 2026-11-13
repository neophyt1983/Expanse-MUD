"""Explicit authored geological landforms, independent of climate/biome.

Geography is never inferred from names, race, faction, weather or nearby actors.
These descriptors do not grant ore, create rooms or imply an eruption.
"""
LANDFORMS = ('collision_range', 'eroded_range', 'volcano', 'lava_field',
             'cooled_lava', 'lava_tube', 'kimberlite_pipe', 'lamproite_pipe', 'alluvial')
ROCKS = ('basalt', 'granite', 'gneiss', 'schist', 'limestone', 'sandstone',
         'kimberlite', 'lamproite', 'alluvium')


def room_geology(world, room):
    return descriptor(getattr(world, 'room_details', {}).get(room, {}).get('geology', {}))


def descriptor(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('landform'), str) or raw['landform'] not in LANDFORMS:
        return {}
    result = {'landform': raw['landform']}
    if isinstance(raw.get('rock'), str) and raw['rock'] in ROCKS:
        result['rock'] = raw['rock']
    if isinstance(raw.get('notes'), str) and len(raw['notes']) <= 2000:
        result['notes'] = raw['notes']
    return result


def validate(data):
    issues = []
    for room in data.get('room', []):
        raw = room.get('geology', {})
        if raw == {}:
            continue
        label = room['id'] + ': geology '
        if not isinstance(raw, dict):
            issues.append(label + 'must be an object (rooms.json)');continue
        if set(raw) - {'landform', 'rock', 'notes'}:
            issues.append(label + 'has unknown fields; use landform, rock and notes (rooms.json)')
        if not isinstance(raw.get('landform'), str) or raw['landform'] not in LANDFORMS:
            issues.append(label + 'landform must be one of: ' + ', '.join(LANDFORMS))
        if 'rock' in raw and (not isinstance(raw['rock'], str) or raw['rock'] not in ROCKS):
            issues.append(label + 'rock must be one of: ' + ', '.join(ROCKS))
        if 'notes' in raw and (not isinstance(raw['notes'], str) or len(raw['notes']) > 2000):
            issues.append(label + 'notes must be at most 2000 characters')
        # Lava tubes are drained basalt conduits, not diamond-bearing pipes.
        if raw.get('landform') == 'lava_tube' and raw.get('rock') in ('kimberlite', 'lamproite'):
            issues.append(label + 'lava_tube is not a kimberlite/lamproite pipe; choose a matching landform')
    return issues
