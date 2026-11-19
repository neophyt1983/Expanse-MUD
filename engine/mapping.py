from engine.directions import normalize_exits
"""ASCII room maps shared by player and creator views."""
from collections import deque, defaultdict

VECTORS = {'north': (0,-1,0), 'south': (0,1,0), 'east': (1,0,0), 'west': (-1,0,0), 'northeast': (1,-1,0), 'northwest': (-1,-1,0), 'southeast': (1,1,0), 'southwest': (-1,1,0), 'up': (0,0,1), 'down': (0,0,-1)}
RESERVED = '@*?123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

def issues(rooms):
    from engine.coordinates import issues as coordinate_issues
    out, used = [], {}
    for r in rooms:
        out.extend(coordinate_issues(r))
        coords = [r.get(k) for k in ('map_x','map_y','map_z')]
        if any(v is not None for v in coords):
            if any(type(v) is not int or abs(v) > 10000 for v in coords):
                out.append(r['id'] + ': map coordinates need three integers between -10000 and 10000')
            elif tuple(coords) in used:
                out.append(r['id'] + ': map coordinates overlap ' + used[tuple(coords)])
            else: used[tuple(coords)] = r['id']
        sym = r.get('map_symbol', '.')
        if not isinstance(sym, str) or len(sym) != 1 or not 33 <= ord(sym) <= 126 or sym in RESERVED:
            out.append(r['id'] + ': choose one ASCII punctuation symbol; player markers are reserved')
        if r.get('map_visibility', 'discovered') not in ('public','discovered','hidden'):
            out.append(r['id'] + ': invalid map visibility')
    return out

def layout(rooms,*,normalized=False):
    if not normalized:
        rooms = [dict(r, exits=normalize_exits(r.get('exits',{}))) for r in rooms]
    byid = {r['id']:r for r in rooms}; positions = {}; warnings = []
    for rid,r in byid.items():
        coords = [r.get(k) for k in ('map_x','map_y','map_z')]
        if all(type(v) is int for v in coords): positions[rid] = tuple(coords)
    visited = set()
    occupied = set(positions.values())
    max_x = max((p[0] for p in positions.values()), default=-4)
    for seed in list(positions) + list(byid):
        if seed in visited: continue
        if seed not in positions:
            max_x += 4
            positions[seed] = (max_x,0,0)
            occupied.add(positions[seed])
        queue = deque([seed]); visited.add(seed)
        while queue:
            rid = queue.popleft(); p = positions[rid]
            for direction,target in byid[rid].get('exits',{}).items():
                if target not in byid or direction not in VECTORS: continue
                v = VECTORS[direction]; expected = tuple(p[i]+v[i] for i in range(3))
                if target not in positions:
                    if expected in occupied:
                        warnings.append(f'{rid}.{direction}: automatic layout overlaps another room; set coordinates in Rooms')
                        expected = (max_x+2, p[1],p[2])
                    positions[target] = expected
                    occupied.add(expected)
                    max_x = max(max_x, expected[0])
                elif positions[target] != expected:
                    warnings.append(f'{rid}.{direction}: connection is not a straight compass step; listed in exits')
                if target not in visited: visited.add(target); queue.append(target)
    return positions, list(dict.fromkeys(warnings))

def room_records(world):
    records = []
    buildings = {}
    for building in world.buildings.values():
        for rid in building.get("rooms", []):
            buildings.setdefault(rid, building)
    # Fix each survey point once. Existing coordinates survive map refreshes.
    survey = getattr(world,'rules',{}).get('tile_survey')
    if survey:
        from engine.coordinates import prepare_survey
        prepare_survey(world)
    for r in world.rooms.values():
        details = getattr(world, 'room_details', {}).get(r.id, {})
        if survey and 'tile_position' not in details:
            from engine.coordinates import surveyed_position
            surveyed_position(world,details,(r.map_x,r.map_y,r.map_z))
        record = dict(details, id=r.id, name=r.name, exits=r.exits, **{k:getattr(r,k) for k in ('map_x','map_y','map_z','map_symbol','map_visibility')})
        building = buildings.get(r.id)
        if building:
            record['_visual_building'] = {'id': building['id'], 'name': building.get('name', building['id'])}
        records.append(record)
    return records

def compile_map(rooms):
    rooms=[dict(r,exits=normalize_exits(r.get('exits',{}))) for r in rooms]
    from engine import drainage
    drainage.chart(rooms)
    positions,warnings=layout(rooms,normalized=True)
    from engine.visual_mapping import room_style
    for room in rooms:
        room['_visual_style'] = room_style(room)
    return {r['id']:r for r in rooms},positions,warnings


def adjacent_step(rows, positions, source, direction, target):
    """A real exit's surveyed same-floor step, including a named doorway.

    A compass label with inconsistent coordinates remains a portal. A named
    door may use its actual adjacent displacement, but never invents an edge,
    collapses a long passage, changes floors or crosses an unplaced gap.
    """
    if source not in positions or target not in positions:
        return None
    bearing = direction.removeprefix('approach ')
    vector = VECTORS.get(bearing)
    if vector:
        if vector[2]:
            return None
        expected = tuple(a + b for a, b in zip(positions[source], vector))
        from engine.visual_mapping import crosses_seam
        return vector if positions[target] == expected or crosses_seam(rows[source], rows[target], bearing) else None
    delta = tuple(b - a for a, b in zip(positions[source], positions[target]))
    return delta if len(delta) == 3 and not delta[2] and delta in VECTORS.values() else None


def geometry_revision(world, compiled):
    """Session revision for a rebuilt survey; no player discovery or save data."""
    if getattr(world, '_map_revision_source', None) is not compiled:
        world._map_revision_source = compiled
        world._map_geometry_revision = getattr(world, '_map_geometry_revision', 0) + 1
    return world._map_geometry_revision

def render(rooms, center, player=None, players=(), explored=(), designer=False, compiled=None, strict=False, local_visible=None, local_positions=None):
    if not rooms and not compiled:return {'text':'No rooms.','cells':[],'legend':[],'warnings':[]}
    byid,pos,warnings=compiled or compile_map(rooms)
    center=center if center in byid else next(iter(byid));cx,cy,cz=pos[center]
    if local_visible is not None and not designer:
        visible={r for r in local_visible if r in byid}|{center}
    else:
        visible=set(byid) if designer else (set(explored)&set(byid))|{center} if strict else {rid for rid,r in byid.items() if rid==center or r.get('map_visibility','discovered')=='public' or (r.get('map_visibility','discovered')=='discovered' and rid in explored)}
    visited=set(byid) if designer else set(explored)|{center}
    width,height = 49,19
    canvas = [[' ']*width for _ in range(height)]; cells = {}; screen = {}
    for rid in visible:
        x,y,z = pos[rid]; sx,sy = (x-cx)*4+24,(y-cy)*2+9
        if z == cz and 0 <= sx < width and 0 <= sy < height: screen[rid]=(sx,sy)
    for rid,(sx,sy) in screen.items():
        if rid not in visited:continue
        for direction,target in byid[rid].get('exits',{}).items():
            if target not in screen or direction not in VECTORS: continue
            v=VECTORS[direction]
            if v[2] or pos[target] != tuple(pos[rid][i]+v[i] for i in range(3)): continue
            tx,ty=screen[target]
            # Only draw horizontal / vertical connections; diagonal destinations remain visible.
            if sy == ty:
                for x in range(min(sx,tx)+1,max(sx,tx)): canvas[sy][x]='-'
            elif sx == tx:
                for y in range(min(sy,ty)+1,max(sy,ty)): canvas[y][sx]='|'
    occupants=defaultdict(list)
    for p in players:
        if p['location'] in visible: occupants[p['location']].append(p)
    legend=[]
    for rid,(sx,sy) in screen.items():
        r=byid[rid]; char=r.get('map_symbol','.') if rid in visited else '.'
        if not isinstance(char,str) or len(char)!=1: char='.'
        if char == '.' and rid in visited:
            if 'up' in r.get('exits',{}): char='<'
            elif 'down' in r.get('exits',{}): char='>'
        ps=occupants[rid]
        if rid==center and player: char='@'
        elif len(ps)>1: char='*'
        elif ps: char=ps[0]['marker']
        canvas[sy][sx]=char; cells[(sx,sy)]=rid
        if ps: legend.append(f'{char} {r.get("name",rid)}: '+', '.join(('YOU ' if p['id']==player else '')+p['name']+' ['+p['marker']+']' for p in ps))
    exits=[]
    for direction,target in byid[center].get('exits',{}).items():
        label=byid.get(target,{}).get('name',target) if target in visible else '? unexplored'
        exits.append(direction+' -> '+label)
    from engine.visual_mapping import render_visual
    visual = render_visual(byid, pos, center, visible, visited=visited, local_positions=local_positions)
    return dict(visual=visual, coordinates=visual['coordinates'], text='\n'.join(''.join(row).rstrip() for row in canvas), cells=[dict(x=x,y=y,room=rid) for (x,y),rid in cells.items()], legend=legend, exits=exits, floor=cz, center=center, position=dict(x=cx,y=cy,z=cz), rooms=[{'id':rid,'name':byid[rid].get('name',rid)} for rid in sorted(visible)] if designer else [], warnings=warnings if designer else [], caption='@ you | digits/letters other players | * shared room | . room | < up | > down | - and | connections. Exit list defines movement. View follows your current room.')
