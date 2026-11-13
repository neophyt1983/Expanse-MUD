"""A viewport of terrain reached through real same-floor map edges."""
from collections import deque

from engine import frontiers, locks
from engine.mapping import VECTORS
from engine.route_surfaces import descriptor
from engine import geology, facility_landmarks
from engine.visual_mapping import land_use_for
from engine.visual_mapping import crosses_seam


def paint_ground(world, compiled, tile):
    """The same visible ground, whether drawn nearby or in the wider viewport."""
    rid = tile['id']
    row = compiled[0][rid]
    if tile.get('exterior'):
        return
    kind, terrain, _ = row['_visual_style']
    tile['terrain'] = terrain
    if row.get('street_front'):
        tile.update(terrain='building',name=world.rooms[rid].name,roof_joins=row.get('roof_joins', []))
        return
    if kind == 'outdoors':
        route = descriptor(row)
        if route:
            tile['route_surface'] = route
        landmark = facility_landmarks.descriptor(row)
        if landmark:
            tile['facility_landmark'] = landmark
        parcels = ((getattr(world, 'living_state', None) or {}).get('settlements') or {}).get('parcels') or {}
        use = land_use_for(row, parcels.get(rid))
        if use:
            tile['ground_use'] = use
    landform = (row.get('geology') or {}).get('landform')
    if landform in geology.LANDFORMS:
        tile['ground_landform'] = landform


def spatial_index(world, compiled):
    """Index tile identities at their final map positions. Procedural records extend this same index."""
    cached = getattr(world, '_travel_index', None)
    if cached is not None and cached[0] is compiled:
        return cached[1], cached[2]
    from collections import defaultdict
    index = defaultdict(list)
    charts = {}
    rows, positions, _ = compiled
    for rid, (x, y, z) in positions.items():
        row = rows[rid]
        if row.get('map_visibility') == 'hidden':
            continue
        index[x, y, z].append(rid)
        planet = row.get('planet') or {}
        for kind in ('field', 'cell'):
            if planet.get(kind) and row['_visual_style'][0] == 'outdoors':
                charts.setdefault((kind, z), {})[x, y] = rid
    wrapped = {}
    for key, cells in charts.items():
        x0, x1 = min(x for x,y in cells), max(x for x,y in cells)
        y0, y1 = min(y for x,y in cells), max(y for x,y in cells)
        width, height = x1-x0+1, y1-y0+1
        # Wrap only complete authored charts whose outer edges genuinely connect.
        if width < 4 or width % 2 or len(cells) != width*height:
            continue
        if any(world.rooms[cells[x0,y]].exits.get('west') != cells[x1,y] for y in range(y0,y1+1)):
            continue
        poles = all(world.rooms[cells[x,y]].exits.get(direction) == cells[x0+(x-x0+width//2)%width,y]
                    for y,direction in ((y0,'north'),(y1,'south')) for x in range(x0,x1+1))
        wrapped[key] = (cells, x0, y0, width, height, poles)
    world._travel_index = (compiled, index, wrapped)
    return index, wrapped


def survey_tiles(world,compiled,origin,hx,hy):
    rows,positions,_=compiled
    if rows[origin]['_visual_style'][0]!='outdoors':
        return {}
    index, charts = spatial_index(world, compiled)
    ox,oy,z=positions[origin]
    planet=rows[origin].get('planet') or {}
    chart=next((charts[k,z] for k in ('field','cell') if planet.get(k) and (k,z) in charts),None)
    # Older custom room graphs can reuse coordinates for unrelated components.
    # An authored survey or complete planet chart establishes a shared surface.
    from engine import country_edges
    area = country_edges.survey(world,origin)
    shared_grid = bool(getattr(world, 'rules', {}).get('tile_survey'))
    locality = country_edges.region(rows[origin])
    if not chart and not shared_grid and not area and locality is None:
        return {}
    result={}
    for dy in range(-hy,hy+1):
        for dx in range(-hx,hx+1):
            x,y=ox+dx,oy+dy
            if chart:
                cells,x0,y0,width,height,poles=chart
                band,local_y=divmod(y-y0,height)
                if band and not poles:continue
                if band%2:
                    x+=width//2
                    local_y=height-1-local_y
                result[dx,dy]=cells[x0+(x-x0)%width,y0+local_y]
                continue
            ids=index.get((x,y,z),())
            if not shared_grid:
                # A placed street and its public doorsteps are visible even in
                # campaigns without expedition generation or a world-wide grid.
                area_lots = area['lots'].get((x, y), ()) if area else ()
                generated = area['land'].get((x, y)) if area else None
                ids = [rid for rid in ids if rid in area_lots or rid == generated
                       or (locality is not None and country_edges.region(rows[rid]) == locality)]
            choices=[r for r in ids if r in rows and rows[r]['_visual_style'][0]=='outdoors']
            if not choices and z>=0:
                choices=[r for r in ids if r in rows and rows[r]['_visual_style'][0]=='building']
            if choices:
                result[dx,dy]=min(choices,key=lambda r:(not bool(rows[r].get('street_front')),r))
    return result


def complete_outdoor_surface(world, compiled, origin, extent, cells):
    """Keep walk targets while drawing the public surface at each coordinate."""
    from engine import country_edges

    rows, positions, _ = compiled
    ox, oy, z = positions[origin]
    lots, charts = spatial_index(world, compiled)
    shared = bool(world.rules.get('tile_survey'))
    if not shared:
        return
    planet = rows[origin].get('planet') or {}
    if any(planet.get(kind) and (kind, z) in charts for kind in ('field', 'cell')):
        return  # Longitude and pole wrapping already selected the correct cells.
    fallback = (z == 0 and getattr(world, 'expedition_country', False)
                and world.rules.get('open_land') and country_edges.ground_index(world) is not None)
    sources = {}
    hx, hy = extent
    for dy in range(-hy, hy + 1):
        for dx in range(-hx, hx + 1):
            xy = dx, dy
            x, y = ox + dx, oy + dy
            tile = cells.get(xy)
            if tile is not None:
                if tile['terrain'] != 'building' and z >= 0:
                    if any(rows[r]['_visual_style'][0] == 'building' for r in lots.get((x, y, z), ())):
                        tile.update(terrain='building', roof_joins=[])
                continue
            if not fallback:
                continue
            block = x // 8, y // 8
            if block not in sources:
                sources[block] = country_edges.block_sources(world, *block, z)
            if sources[block]:
                terrain = country_edges.tile_source(sources[block], x, y)[3]
                cells[xy] = dict(id=f'@surface/{z}/{x}/{y}', terrain=terrain, name=terrain.capitalize(),
                                 dx=dx, dy=dy, scenery=True)


def window(world, player, compiled, extent, destination=None, *, require_open=False):
    if (not isinstance(extent, list) or len(extent) != 2
            or any(type(n) is not int or not 1 <= n <= 64 for n in extent)):
        raise ValueError('Choose a valid map area.')
    if destination is not None and (not isinstance(destination, str) or not player.alive):
        raise ValueError('Choose a reachable tile while conscious.')
    rows, positions, _ = compiled
    origin = player.location
    kind, _, building = rows[origin]['_visual_style']
    hx, hy = extent
    from engine import country_edges
    if compiled is getattr(world,"_compiled_map",None):country_edges.extend(world,origin,hx,hy)
    # Drawing is a spatial query. A wall or shifted doorway can block the path
    # to a visible roof without changing the ground at that coordinate.
    survey=survey_tiles(world,compiled,origin,hx,hy) if not require_open else {}
    if destination is not None and destination in survey.values():
        # Roofs, their doorsteps and the original public street can share
        # one drawn tile. Include the underlying outdoor rooms for routing.
        area = country_edges.survey(world, origin)
        ox, oy, z = positions[origin]
        index=country_edges.ground_index(world)
        if rows[destination]['_visual_style'][0]!='outdoors':raise ValueError('The roof is above street level. Use the building entrance.')
        allowed = {r for r in survey.values() if rows[r]['_visual_style'][0]=='outdoors'} | {origin}
        for dx, dy in survey:
            for rid in (index.get((ox+dx,oy+dy,z),()) if index is not None else (area or {}).get('lots',{}).get((ox+dx,oy+dy), ())):
                if (rid in rows and rows[rid]['_visual_style'][0]=='outdoors'
                        and world.rooms[rid].map_visibility!='hidden'):
                    allowed.add(rid)
        path=frontiers.path(world,origin,destination,player,allowed=allowed)
        if path is not None:return path
    coordinates = {origin: (0, 0)}
    occupied = {(0, 0)}
    previous = {}
    queue = deque([origin])
    tiles = []
    check_edges = require_open or destination is not None or kind != 'outdoors'
    lock_index = locks.index(world) if check_edges else {}
    from engine import geology_impacts
    hazards=geology_impacts.route_sources(world) if check_edges else set()
    boat=any(world.items.get(item,{}).get('boat') for item in player.inventory)
    while queue:
        rid = queue.popleft()
        x, y = coordinates[rid]
        if destination == rid:
            steps = []
            while rid != origin:
                parent, direction = previous[rid]
                steps.append((parent, direction, rid))
                rid = parent
            return steps[::-1]
        row = rows[rid]
        if destination is None:
            tile = dict(id=rid, dx=x, dy=y, terrain=row['_visual_style'][1])
            if not require_open:
                paint_ground(world, compiled, tile)
            tiles.append(tile)
        for direction, target in world.rooms[rid].exits.items():
            if target in coordinates or target not in rows:
                continue
            bearing = direction.removeprefix('approach ')
            vector = VECTORS.get(bearing)
            if not vector or vector[2]:
                continue
            dx, dy = x + vector[0], y + vector[1]
            if abs(dx) > hx or abs(dy) > hy or (dx, dy) in occupied:
                continue
            other = rows[target]
            target_kind, _, target_building = other['_visual_style']
            if (world.rooms[target].map_visibility == 'hidden' or target_kind != kind
                    or kind != 'outdoors' and target_building.get('id') != building.get('id')):
                continue
            expected = tuple(a + b for a, b in zip(positions[rid], vector))
            if positions[target] != expected and not crosses_seam(row, other, bearing):
                continue
            if check_edges:
                detailed=(bool(lock_index.get(rid)) or rid in hazards or bool(row.get('gates')) or bool(other.get('property_unit_id')))
                if frontiers.path_blocked(world,rid,direction,target,player,detailed,lock_index,hazards,boat):
                    continue
            coordinates[target] = dx, dy
            occupied.add((dx, dy))
            if destination is not None:
                previous[target] = rid, direction
            queue.append(target)
    if destination is not None:
        raise ValueError('There is no open walking route to that tile on this map.')
    if not require_open and kind=='outdoors':
        by_cell={(t['dx'],t['dy']):t for t in tiles}
        for xy,rid in survey.items():
            
            tile=dict(id=rid,dx=xy[0],dy=xy[1])
            if rows[rid]['_visual_style'][0]=='building':
                tile.update(terrain='building',scenery=True,roof_joins=[],name='Roof')
            else:
                paint_ground(world,compiled,tile)
            if xy==(0,0) and rid!=origin:
                tile.update(id=origin,surface_id=rid,name=world.rooms[origin].name)
                tile.pop('scenery',None)
            by_cell[xy]=tile
        source=country_edges.survey(world,origin)
        water=getattr(world,'_country_water',{})
        cover = getattr(world, '_country_cover', {})
        if cover or water or (source and source.get('water')):
            ox,oy,z=positions[origin]
            for dy in range(-hy,hy+1):
                for dx in range(-hx,hx+1):
                    x,y=ox+dx,oy+dy
                    if (dx,dy) in by_cell:
                        continue
                    terrain=cover.get((x,y,z)) or water.get((x,y,z)) or (source and source['water'].get((x,y)))
                    if terrain:
                        by_cell[dx,dy]=dict(id=f'@surface/{z}/{x}/{y}', terrain=terrain,
                                            name=terrain.capitalize(),dx=dx,dy=dy,scenery=True)
        complete_outdoor_surface(world, compiled, origin, extent, by_cell)
        tiles=list(by_cell.values())
    return tiles

def opening(world,player,compiled):
    # Ship a usable first viewport with the ordinary location update. Subsequent
    # client requests only refine the extent after measuring the actual screen.
    return window(world, player, compiled, [5, 9])
