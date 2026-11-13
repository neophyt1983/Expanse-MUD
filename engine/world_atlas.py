"""Discovery-filtered whole-room atlas, never inferred continent geography."""
from engine.coordinates import project
from engine.geology import descriptor as geology_descriptor
from engine.visual_mapping import room_style
from engine.route_surfaces import descriptor as route_descriptor


def remember(player, observed, compiled):
    """Keep seen surface locations separate from visits and quest knowledge."""
    seen = player.progress.setdefault('atlas_seen', {})
    for rid in observed:
        row = compiled[0].get(rid)
        if row and row['_visual_style'][0] == 'outdoors' and row.get('map_visibility') != 'hidden':
            seen[rid] = True
    return seen


def terrain_cell(atlas, row, xyz):
    kind, terrain, _ = row['_visual_style']
    if (kind != 'outdoors' and (kind!='building' or xyz[2]<0)) or row.get('map_visibility') == 'hidden':
        return
    roof = bool(row.get('street_front')) or kind=='building'
    terrain_value(atlas, xyz, (roof, 'building' if roof else terrain))


def terrain_value(atlas, xyz, value):
    x, y, z = xyz
    line = atlas['lines'].setdefault((z, y), {})
    previous = line.get(x)
    if previous is not None and previous >= value:
        return
    line[x] = value
    if previous is not None and previous[1] == value[1]:
        return
    atlas['version'] += 1
    atlas['changed'][z, y] = atlas['version']

def terrain_runs(cells):
    runs = []
    for x, terrain in sorted(cells.items()):
        if runs and runs[-1][2] == terrain and runs[-1][0] + runs[-1][1] == x:
            runs[-1][1] += 1
        else:
            runs.append([x, 1, terrain])
    return runs


def public_ground(world, authored):
    """Read public terrain without spawning rooms or revealing discoveries."""
    from engine import country_edges
    background = {}
    for region in getattr(world, 'field_regions', ()):
        if region.underground:
            continue
        ox, oy, z = region.origin
        for dy, row in enumerate(region.grid):
            cells = background.setdefault((z, oy+dy), {})
            for dx, symbol in enumerate(row):
                if symbol != '.':
                    cells[ox+dx] = region.palette[ord(symbol)-65]

    if (getattr(world, 'expedition_country', False) and world.rules.get('open_land')
            and country_edges.ground_index(world) is not None):
        # Only ground-floor blocks within reach of a real biome sample can
        # produce open country. Upper floors and underground passages stay local.
        buckets = world._natural_biomes.keys() | world._surveyed_open_biomes.keys()
        blocks = {(bx+dx, by+dy) for bx, by, z in buckets if z == 0
                  for dx in range(-4, 5) for dy in range(-4, 5)}
        for bx, by in blocks:
            missing = []
            for y in range(by*8, by*8+8):
                rooms = authored.get((0, y), {})
                fields = background.get((0, y), {})
                missing.extend((x, y) for x in range(bx*8, bx*8+8) if x not in rooms and x not in fields)
            if not missing:
                continue
            sources = country_edges.block_sources(world, bx, by, 0)
            if not sources:
                continue
            common = sources[0][3] if all(s[3] == sources[0][3] for s in sources) else None
            for x, y in missing:
                background.setdefault((0, y), {})[x] = common or country_edges.tile_source(sources, x, y)[3]
    return {key: terrain_runs(line) for key, line in background.items() if line}


def terrain_map(world, compiled, since=-1):
    """Compact public surface geometry. No room names, IDs, people or objects."""
    atlas = getattr(world, '_atlas_ground', None)
    if atlas is None or atlas['compiled'] is not compiled:
        atlas = world._atlas_ground = dict(compiled=compiled, lines={}, changed={}, encoded={}, version=0)
        for rid, row in compiled[0].items():
            terrain_cell(atlas, row, compiled[1][rid])
        for xyz, land in getattr(world, '_country_cover', {}).items():
            terrain_value(atlas, xyz, (False, land))
        for xyz, water in getattr(world, '_country_water', {}).items():
            terrain_value(atlas, xyz, (False, water))
        atlas['background'] = public_ground(world, atlas['lines'])
        if atlas['background']:
            atlas['version'] += 1
            for key in atlas['background']:
                atlas['changed'][key] = atlas['version']
        since = -1
    lines = []
    for (z, y), version in atlas['changed'].items():
        if version <= since:
            continue
        cached = atlas['encoded'].get((z, y))
        if cached and cached[0] == version:
            runs = cached[1]
        else:
            base = atlas['background'].get((z, y), ())
            cells = {x: terrain for start, count, terrain in base for x in range(start, start+count)}
            cells.update((x, value[1]) for x, value in atlas['lines'].get((z, y), {}).items())
            runs = terrain_runs(cells)
            atlas['encoded'][z, y] = (version, runs)
        lines.append([z, y, runs])
    return dict(terrain_rows=lines, terrain_version=atlas['version'])


def render(compiled, center, explored=(), designer=False, nearby=()):
    """Serialize only allowed rooms; no hidden counts, extents or connections."""
    byid, positions, _warnings = compiled
    if designer:
        visible = set(byid)
        if center not in byid:
            center = next(iter(byid), None)
    else:
        visible = set(explored) & set(byid)
        if center in byid:
            visible.add(center)
        else:
            center = None
    visited=set(visible)
    if not designer:visible.update(set(nearby)&set(byid))
    rooms = []
    placed = 0
    for rid in sorted(visible):
        room = byid[rid]
        kind, terrain, _building = room.get('_visual_style') or room_style(room)
        x, y, z = positions[rid]
        coordinates = project(room, (x, y, z))
        placed += coordinates['world'] is not None
        rooms.append(dict(id=rid, name=room.get('name', rid), x=x, y=y, z=z,
                          terrain=terrain, kind=kind, coordinates=coordinates,
                          current=rid == center, visited=rid in visited, visibility='visited' if rid in visited else 'visible'))
        if room.get('tile_position'):
            point=room['tile_position']
            rooms[-1]['tile_position']=point
            if coordinates['world'] is None:
                coordinates['world']=dict(x=point['x'],y=point['y'],z=point['z'],units='m')
                placed+=1
        if designer or rid in visited:
            region=room.get('atlas_region')
            if not region and room.get('world_region')=='Three Watersheds survey':
                if room.get('world_y',0)<-5:region='Southwater Lowlands'
                elif room.get('world_x',0)<=70:region='Westflow Basin'
                elif room.get('world_x',0)>=96:region='Eastflow Basin'
                else:region='Three Passes Range'
            if not region and room.get('creation_method')=='Six Roads open terrain expansion v1.':region='Six Roads'
            if isinstance(region,str) and region.strip():rooms[-1]['atlas_region']=region[:80]
        if room.get('planet') and (designer or rid in visited):
            rooms[-1]['planet'] = dict(room['planet'])
            elevation=room.get('climate',{}).get('elevation_m')
            if type(elevation) in (int,float):rooms[-1]['elevation_m']=elevation
            geology=geology_descriptor(room.get('geology'))
            if geology:rooms[-1]['geology']=geology
            water=room.get('environment')
            channel=room.get('waterway')
            if (water in ('river','water','ocean','lake','stream','wetland','shore','coast')
                    or isinstance(channel,dict) and channel.get('kind') not in (None, 'dry')):
                rooms[-1]['water']={'kind':water,'requires_boat':room.get('requires_boat') is True}
                downstream=room.get('_downstream')
                if downstream and (designer or downstream in visited):rooms[-1]['water']['downstream']=downstream
                if isinstance(channel,dict):
                    for key in ('name','kind','outlet','flow'):
                        if isinstance(channel.get(key),str):rooms[-1]['water'][key]=channel[key][:100]

        if room.get('tile_position') and (designer or rid in visited):
            point=room['tile_position']
            rooms[-1]['planet']={**rooms[-1].get('planet',{}),'lat':point['lat'],'lon':point['lon']}
            rooms[-1]['elevation_m']=point['alt']
        from engine.facility_landmarks import descriptor as facility_descriptor
        landmark=facility_descriptor(room)
        if landmark and kind=='outdoors':rooms[-1]['facility_landmark']=landmark
        route = route_descriptor(room)
        if route and kind == 'outdoors':
            rooms[-1]['route_surface'] = route
    return dict(type='world_atlas', version=1,
                scope='complete' if designer else 'explored', center=center,
                rooms=rooms, floors=sorted({r['z'] for r in rooms}),
                counts=dict(visible=len(rooms), placed=placed),
                note=('Complete host room atlas. Selected room is not a player location. '
                      if designer else
                      'Visited locations are remembered; currently visible nearby terrain is marked unvisited. Distant unexplored locations are not disclosed. ')
                     + 'Room layout is not a geographic continent. World positions appear only where explicitly authored.')


def conceal_routes(packet):
    """Ordinary dark atlas retains visited geography, not live route markings.

    Apply to full or delta packets before sending. The server must send a full
    replacement on a lighting transition, retracting any previously sent axes.
    Explicit designer/host complete views are not player sight projections.
    """
    if packet.get('scope') == 'complete':return packet
    for row in packet.get('rooms',[]):
        row.pop('route_surface',None)
    packet['blind_navigation']=True
    packet['note']='Remembered locations remain visible. Darkness conceals current routes; try a direction or use a working lantern. Room layout is not a geographic continent.'
    return packet
