"""Separate authored world placement from the room-layout grid.

World X/Y are abstract Cartesian world units: east/right and north/up are
positive. They are not latitude/longitude, distances, exits or a new movement
model. Omitted coordinates mean unplaced, never (0, 0). Multiple rooms may
share a world point (for example a building's floors).
"""
import math

LIMIT = 1_000_000


def number(value):
    return type(value) in (int, float) and abs(value) <= LIMIT and math.isfinite(value)


def issues(room):
    errors = []
    if 'planet' in room:
        pos = room['planet']
        if (not isinstance(pos,dict) or not number(pos.get('lat')) or abs(pos['lat'])>90
            or not number(pos.get('lon')) or abs(pos['lon'])>180
            or type(pos.get('cell',False)) is not bool):
            errors.append(f"{room.get('id','?')}: invalid planet latitude or longitude")
    present = [key in room for key in ('world_x', 'world_y')]
    if any(present) and (not all(present) or not all(number(room.get(key)) for key in ('world_x', 'world_y'))):
        errors.append(f"{room.get('id', '?')}: world_x and world_y must both be finite numbers between -1000000 and 1000000, or both omitted")
    if 'world_region' in room:
        region = room['world_region']
        if not isinstance(region, str) or len(region) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in region):
            errors.append(f"{room.get('id', '?')}: world_region must be text of at most 80 characters without control characters")
    return errors


def project(room, position):
    """Called only for an already-visible room; never follows hidden anchors."""
    local = dict(zip(('x', 'y', 'z'), position))
    local['source'] = 'authored' if all(type(room.get(k)) is int for k in ('map_x', 'map_y', 'map_z')) else 'layout'
    world = None
    if not issues(room) and all(k in room for k in ('world_x', 'world_y')):
        world = dict(x=room['world_x'], y=room['world_y'],
                     region=room.get('world_region', ''), units='world units')
    result=dict(local=local, world=world)
    if room.get('tile_position'):
        point = room['tile_position']
        result['tile'] = point
        result['world'] = dict(x=point['x'], y=point['y'], z=point['z'],
                               region=room.get('world_region', ''), units='m')
    return result


def describe(coordinates):
    if coordinates.get('tile'):
        p = coordinates['tile']
        return (f"Tile X {p['x']} m, Y {p['y']} m, Z {p['z']} m. "
                f"Latitude {p['lat']:.8f}°, longitude {p['lon']:.8f}°, altitude {p['alt']} m.")
    local = coordinates['local']
    text = f"Room layout: X {local['x']}, Y {local['y']}, level {local['z']} (+X east, +Y south)."
    if local.get('source') == 'layout':
        text += ' Automatically laid out; not an authored geographic position.'
    world = coordinates.get('world')
    if world is None:
        return text + '\nWorld position: not placed.'
    text += f"\nWorld position: X {world['x']}, Y {world['y']} world units (+X east, +Y north)."
    if world.get('region'):
        text += ' Region: ' + world['region'] + '.'
    return text


def set_room_coordinates(ed, body):
    """Atomically stage a pair, never save or modify the active runtime world."""
    if not isinstance(body, dict) or not isinstance(body.get('id'), str):
        raise ValueError('Room id and a coordinate pair are required.')
    if not all(key in body for key in ('world_x', 'world_y')):
        raise ValueError('Provide both world_x and world_y; use two nulls to clear the position.')
    room = next((r for r in ed.data['room'] if r['id'] == body['id']), None)
    if room is None:
        raise ValueError('Unknown room.')
    draft = dict(room)
    if body['world_x'] is None and body['world_y'] is None:
        draft.pop('world_x', None)
        draft.pop('world_y', None)
    else:
        draft.update(world_x=body['world_x'], world_y=body['world_y'])
    if 'world_region' in body:
        draft['world_region'] = body['world_region']
    errors = issues(draft)
    if errors:
        raise ValueError('; '.join(errors))
    if draft.get('world_region') == '':
        draft.pop('world_region', None)
    if draft != room:
        room.clear()
        room.update(draft)
        ed.dirty.add('room')
    return 'World coordinates staged. Save and Apply when ready. Room layout and exits are unchanged.'

def prepare_survey(world):
    if getattr(world, '_tile_survey_ready', False) or not getattr(world, 'rules', {}).get('tile_survey'):
        return
    for ident in sorted(world.rooms):
        room = world.rooms[ident]
        row = world.room_details.get(ident)
        if row is not None and 'tile_position' not in row:
            surveyed_position(world, row, (room.map_x, room.map_y, room.map_z))
    world._tile_survey_ready = True


def surveyed_position(world, row, xyz):
    """Project a room's survey point into the world's metric grid and geographic chart."""
    survey = getattr(world, 'rules', {}).get('tile_survey')
    if not survey:
        return
    x, y, level = xyz
    if any(type(n) is not int for n in xyz):
        return
    default_lat, default_lon, base_x, base_y = survey['origin']
    geographic = row.get('planet') or {}
    lat, lon = geographic.get('lat', default_lat), geographic.get('lon', default_lon)
    reference = survey['anchors'].get(str(lat)+','+str(lon))
    if row.get('survey_from'):
        lat,lon,base_x,base_y=row['survey_from']
        reference=[base_x,base_y]
    pitch = survey['tile_m']
    degrees = 180 / (math.pi * survey['radius_m'])
    if row.get('survey_from') or not geographic or (reference and not geographic.get('cell') and not geographic.get('field')):
        if reference:
            base_x, base_y = reference
        elif not geographic:
            region = next((r for r in getattr(world, 'field_regions', ()) if r.name==row.get('world_region')), None)
            if region:
                gate = world.room_details[region.gate]
                point = gate.get('planet') or {}
                lat, lon = point.get('lat',lat), point.get('lon',lon)
                base_x, base_y = region.origin[0], region.origin[1]+region.trail_y
        lon += (x-base_x)*pitch*degrees / max(.01, math.cos(math.radians(lat)))
        lat -= (y-base_y)*pitch*degrees
    altitude = round((row.get('climate') or {}).get('elevation_m', 0) + level*survey['floor_m'], 2)
    # A doorstep and a floor can occupy one footprint. Survey the doorway
    # at its threshold. Keep tied points distinct within the same tile.
    if row.get('street_front'):
        lon += pitch*.25*degrees / max(.01,math.cos(math.radians(lat)))
    if not hasattr(world,'_tile_survey_used'):world._tile_survey_used=set()
    used = world._tile_survey_used
    lat = round(lat,8)
    lon = round((lon+180)%360-180,8)
    while (lat,lon,altitude) in used:
        lon=round(lon+.0000001,8)
    used.add((lat,lon,altitude))
    row['tile_position'] = dict(lat=lat, lon=lon, alt=altitude,
        x=round(lon/degrees,3), y=round(lat/degrees,3), z=altitude)

def survey_editor(rooms, folder):
    import json
    from types import SimpleNamespace
    path=folder/'world-rules.json'
    if not path.is_file():
        return
    rules=json.loads(path.read_bytes())
    if not rules.get('tile_survey'):
        return
    context=SimpleNamespace(rules=rules,_tile_survey_used=set(),room_details={r['id']:r for r in rooms})
    for row in sorted(rooms, key=lambda r: r['id']):
        surveyed_position(context,row,tuple(row.get(k) for k in ('map_x','map_y','map_z')))
