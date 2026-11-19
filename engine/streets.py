"""Outdoor footprints use the same surveyed cells as above-ground interiors."""
from collections import defaultdict
from hashlib import sha256

from engine.core import Room
from engine.mapping import VECTORS, layout, room_records
from engine.visual_mapping import room_style


def reserve(world, owner, footprint, *, occupied=None):
    """Translate the entire XY footprint together. Storeys of one building stack."""
    if occupied is None:
        occupied = world._building_tiles
    radius=0
    while True:
        candidates=[(0,0)] if not radius else (
            [(x,-radius) for x in range(-radius,radius+1)]
            + [(radius,y) for y in range(1-radius,radius+1)]
            + [(x,radius) for x in range(radius-1,-radius-1,-1)]
            + [(-radius,y) for y in range(radius-1,-radius,-1)])
        for dx,dy in candidates:
            if all((x+dx,y+dy) not in occupied or occupied[x+dx,y+dy]==owner for x,y in footprint):
                for x,y in footprint:occupied[x+dx,y+dy]=owner
                return dx,dy
        radius+=1


def install(world):
    if hasattr(world, '_street_origins'):
        return
    world._building_tiles = {}
    world._street_origins = origins = {}
    world._street_checks = checks = {}
    details = world.room_details
    membership = {rid: b['id'] for b in world.buildings.values() for rid in b.get('rooms', [])}
    def kind(rid):
        row = details[rid]
        return room_style(dict(row, _visual_building={'id':membership[rid]}) if rid in membership else row)[0]
    building = [rid for rid in world.rooms if rid in details and kind(rid)=='building' and not details[rid].get('property_unit_id')]
    if not building:
        return
    coords = {rid:(r.map_x,r.map_y,r.map_z) for rid,r in world.rooms.items()}
    if any(None in coords[rid] for rid in building):
        coords, _ = layout(room_records(world))
    # Rooms without an authored building record share the indoor component the
    # local map already uses. An outdoor, cave or named-building edge ends it.
    unnamed=set(building)-membership.keys()
    neighbors=defaultdict(set)
    for rid in unnamed:
        for dst in world.rooms[rid].exits.values():
            if dst in unnamed:
                neighbors[rid].add(dst);neighbors[dst].add(rid)
    while unnamed:
        start=unnamed.pop();pending=[start];component=[start]
        while pending:
            for dst in neighbors[pending.pop()] & unnamed:
                unnamed.remove(dst);pending.append(dst);component.append(dst)
        anchor=min(component)
        for rid in component:membership[rid]=anchor
    # A dwelling's first occupied floor can be upstairs. Its front door is at
    # the authored public street, even when the two share only an XY position.
    public_access = {}
    for rid in building:
        street = world.rooms[rid].exits.get('out')
        if street in coords and kind(street) == 'outdoors' and world.rooms[street].exits.get('in') == rid:
            if coords[rid][:2] == coords[street][:2] and coords[rid][2] > coords[street][2]:
                public_access[rid] = street
    # An authored city can have public streets below the global zero datum.
    # Require an actual same-level street connection in the same survey.
    from engine.country_edges import region
    street_levels = set()
    for rid in building:
        z = coords[rid][2]
        if z >= 0:
            continue
        realm = region(details[rid])
        if realm and any(dst in coords and coords[dst][2] == z and kind(dst) == 'outdoors'
                         and region(details[dst]) == realm for dst in world.rooms[rid].exits.values()):
            street_levels.add((membership.get(rid, rid), z, realm))
    cells = {}
    floor = {}
    for rid in building:
        x,y,z = coords[rid]
        key = membership.get(rid,rid)
        if z < 0:
            if (key, z, region(details[rid])) not in street_levels:
                continue
            key = (key, z)
        ground = coords[public_access[rid]][2] if rid in public_access else z
        floor[key] = min(floor.get(key, ground), ground)
        cells.setdefault((key,x,y),[]).append(rid)
    # Preserve uncontested surveyed sites, then move complete conflicting plans.
    # An L-shaped floor never expands into its empty corner.
    by_building=defaultdict(set)
    for bid,x,y in cells:by_building[bid].add((x,y))
    shifts={};conflicts=[]
    below = defaultdict(dict)
    def occupied(bid):
        return below[bid[1]] if isinstance(bid, tuple) else world._building_tiles
    for bid,shape in sorted(by_building.items(), key=lambda pair: str(pair[0])):
        if any(pt in occupied(bid) for pt in shape):conflicts.append(bid)
        else:shifts[bid]=reserve(world,bid,shape,occupied=occupied(bid))
    for bid in conflicts:shifts[bid]=reserve(world,bid,by_building[bid],occupied=occupied(bid))
    for (bid,x,y),rooms in cells.items():
        dx,dy=shifts[bid]
        for rid in rooms:
            z=coords[rid][2]
            coords[rid]=(x+dx,y+dy,z)
            obj=world.rooms[rid]
            obj.map_x,obj.map_y,obj.map_z=coords[rid]
            details[rid].update(map_x=obj.map_x,map_y=obj.map_y,map_z=z)
    cells={(bid,x+shifts[bid][0],y+shifts[bid][1]):rs for (bid,x,y),rs in cells.items()}
    outer = {}
    doors_in = defaultdict(list)
    doors_out = defaultdict(list)
    surfaces={}
    for (bid,x,y), rooms in cells.items():
        rid = min(rooms,key=lambda r:coords[r][2])
        ext = details[rid].get('frontage_key') or 'streetfront_'+sha256(repr((bid,x,y)).encode()).hexdigest()[:20]
        if ext in world.rooms:
            continue
        inside = world.rooms[rid]
        name = 'Outside '+inside.name
        row = {k:v for k,v in details[rid].items() if k in ('group','planet','world_x','world_y','world_region','press_locality')}
        climate = dict(details[rid].get('climate') or {}, sheltered=False)
        description = 'The public frontage of '+inside.name+'.'
        row.update(id=ext,name=name,description=description,environment='road',climate=climate,
                   map_x=x,map_y=y,map_z=floor[bid],exits={},street_front=rid)
        visibility='hidden' if all(world.rooms[r].map_visibility=='hidden' for r in rooms) else 'discovered'
        row['map_visibility']=visibility
        details[ext] = row
        world.add_room(Room(ext,name,description,row['exits'],group=inside.group,map_x=x,map_y=y,map_z=floor[bid],map_visibility=visibility))
        origins[ext] = rid
        surfaces[bid,x,y]=ext
        for r in rooms:
            outer[r] = ext

    def add(src, direction, dst):
        exits=world.rooms[src].exits
        if direction in exits and exits[direction]!=dst:
            direction = 'approach '+world.rooms[dst].name.casefold()
        if direction in exits and exits[direction]!=dst:
            return None
        exits[direction]=dst
        return direction

    for src in list(details):
        if src in origins:
            continue
        for di,dst in list(world.rooms[src].exits.items()):
            if dst not in details or dst in origins or di in ('up','down') or (src not in outer and dst not in outer):
                continue
            a,b=outer.get(src,src),outer.get(dst,dst)
            if a==b or (src not in outer and kind(src)!='outdoors') or (dst not in outer and kind(dst)!='outdoors'):
                continue
            if (src in outer and coords[src][2]!=world.rooms[a].map_z and public_access.get(src)!=dst
                    or dst in outer and coords[dst][2]!=world.rooms[b].map_z and public_access.get(dst)!=src):
                continue
            edge=add(a,di if src in outer else 'approach '+di,b)
            if edge:
                checks[(a,edge)]=[(src,di)]
            if src in outer and dst not in outer:
                doors_out[src].append((src,di))
            if src not in outer and dst in outer:
                doors_in[dst].append((src,di))
    # A person on a doorstep is already outside. Continue along each adjoining
    # public street directly, retaining the original street's locks and hazards.
    for rid, street in public_access.items():
        ext = outer.get(rid)
        if ext is None:
            continue
        doorstep, corner = world.rooms[ext], world.rooms[street]
        if (doorstep.map_x, doorstep.map_y, doorstep.map_z) != coords[street]:
            continue
        for di, target in corner.exits.items():
            vector = VECTORS.get(di)
            if not vector or vector[2] or di in doorstep.exits or target not in coords or kind(target)!='outdoors':
                continue
            if tuple(a+b for a,b in zip(coords[street],vector)) != coords[target]:
                continue
            doorstep.exits[di]=target
            checks[ext,di]=[(street,di)]
    for (bid,x,y),ext in surfaces.items():
        sides=[]
        for di,(dx,dy) in {'north':(0,-1),'south':(0,1),'west':(-1,0),'east':(1,0)}.items():
            adjacent=surfaces.get((bid,x+dx,y+dy))
            if adjacent:
                sides.append(di)
                if di not in world.rooms[ext].exits:add(ext,di,adjacent)
        details[ext]['roof_joins']=sides
    for rid, ext in outer.items():
        if details[rid].get('public_entrance'):
            add(rid, 'out', ext)
            add(rid, 'step outside', ext)
            add(ext, 'enter building', rid)
    for rid in sorted(doors_in.keys()|doors_out.keys()):
        ext=outer[rid]
        for src,di,dst,rules in [(rid,'step outside',ext,doors_out[rid]),(ext,'enter building',rid,doors_in[rid])]:
            if rules:
                edge=add(src,di,dst)
                if edge:checks[(src,edge)]=rules

    for (source, approach), rules in list(checks.items()):
        if not approach.startswith('approach ') or len(rules) != 1:
            continue
        origin, direction = rules[0]
        if origin != source or direction not in VECTORS or VECTORS[direction][2]:
            continue
        exits = world.rooms[source].exits
        interior = exits.get(direction)
        frontage = exits.get(approach)
        if interior in outer and outer[interior] == frontage and world.rooms[frontage].exits.get('enter building') == interior:
            exits[direction] = frontage
            details[source]['exits'][direction] = frontage


def doorways(world, player, visual, blocked):
    """Transitions that a tile tap cannot express geometrically, including stairs."""
    room=world.rooms[player.location]
    rows=world._compiled_map[0]
    shown={t['id'] for t in visual['tiles'] if not t.get('exterior')}
    shell=getattr(world,'_street_origins',{})
    for t in visual['tiles']:
        if t['id'] in shell:
            t['terrain']='building'
            t['roof_joins']=world.room_details[t['id']].get('roof_joins',[])
    roof_cells={(t['x'],t['y'],t['z']) for t in visual['tiles'] if t['id'] in shell}
    visual['tiles']=[t for t in visual['tiles'] if not (t.get('exterior') and (t['x'],t['y'],t['z']) in roof_cells)]
    actions=[]
    inside=visual['context']['kind']=='building' or bool(rows[room.id].get('property_unit_id'))
    # Only a real, drawn compass path can replace a passage button. A named
    # doorway or an exit with nonadjacent coordinates still needs its action,
    # even when its destination also happens to be on the map.
    drawn_paths={e['direction'] for e in visual.get('exits',[])
                 if e.get('kind')=='path' and e.get('target') in shown}
    for di,dst in room.exits.items():
        # The movement command always resolves this alias to the doorstep,
        # regardless of what the original authored `out` edge pointed at.
        if di=='out' and 'step outside' in room.exits:
            continue
        if dst not in rows or world.rooms[dst].map_visibility=='hidden':
            continue
        target=world.rooms[dst].name
        destination_inside=rows[dst]['_visual_style'][0]=='building' or bool(rows[dst].get('property_unit_id'))
        action='passage'
        if di in ('up','down'):
            if dst in shown:
                continue
            action='stairs'
            label='Stairs '+di+' · '+target
        elif inside and not destination_inside:
            # Suppress only an equivalent doorstep choice. Other doors may
            # lead to a different street or have different access rules.
            if (di!='step outside' and room.exits.get('step outside')==dst
                    and (blocked.get(di) or '')==(blocked.get('step outside') or '')):
                continue
            action='exit'
            label='Exit to '+target
        elif inside:
            if di in drawn_paths or dst==room.id:
                continue
            label='Go to '+target
        elif destination_inside:
            if 'approach '+di in room.exits:
                continue
            action='entry'
            label='Enter '+target
        elif dst in shown and dst!=room.id and not di.startswith('approach ') and di in ('north','south','east','west','northeast','southeast','northwest','southwest'):
            from engine.mapping import VECTORS
            positions=world._compiled_map[1]
            expected=tuple(a+b for a,b in zip(positions[room.id],VECTORS[di]))
            if positions[dst]==expected:continue
            label='Walk to '+target
        elif room.id in shell and di=='out' and not destination_inside:
            label='Walk out to '+target
        elif di=='return to parcel':
            label='Return to '+target
        elif di.startswith('approach '):
            label='Walk to '+target
        elif 'approach '+di in room.exits and room.id not in shell:
            continue
        else:
            label='Passage '+di+' · '+target
        actions.append(dict(direction=di,kind=action,label=label,blocked=blocked.get(di) or ''))
    return sorted(actions,key=lambda a:(a['kind'] not in ('exit','entry'),a['label']))


def unit_front(w,u,rid,coords):
    if not hasattr(w,'_building_tiles'):install(w)
    parcel=u['room'];base=w.rooms[parcel]
    if any(type(coords.get(k)) is not int for k in ('map_x','map_y','map_z')):
        if not hasattr(w,'_property_base_layout'):
            w._property_base_layout=layout(room_records(w))[0]
        xyz=w._property_base_layout.get(parcel,(0,0,0))
        coords.update(zip(('map_x','map_y','map_z'),xyz))
    if coords['map_z']<0:return parcel
    preferred=u.get('footprint_tile')
    if isinstance(preferred,list) and len(preferred)==2:
        for ax,ay,bx,by,dx,dy,gate in getattr(w,'rules',{}).get('district_resurvey',[]):
            if ax-4<=preferred[0]<=bx+4 and ay-4<=preferred[1]<=by+4:
                preferred=[preferred[0]+dx,preferred[1]+dy]
                break
    x,y=(preferred if isinstance(preferred,list) and len(preferred)==2 and all(type(n) is int for n in preferred)
         else [coords['map_x'],coords['map_y']])
    dx,dy=reserve(w,rid,{(x,y)})
    coords.update(map_x=x+dx,map_y=y+dy)
    u['footprint_tile']=[x+dx,y+dy]
    if u['footprint_tile']==[base.map_x,base.map_y] or (base.map_x is None and u['footprint_tile']==list(w._property_base_layout[parcel][:2])):
        w._street_origins[parcel]=rid
        return parcel
    ext='front_'+rid
    if ext in w.rooms:raise ValueError('A creator room already uses the reserved property frontage.')
    idx=u['index']+1
    name='Outside '+base.name+' #'+str(idx)
    desc='The public doorstep. The path leads back to '+base.name+'.'
    exits={'enter building':rid,'return to parcel':parcel}
    row={k:v for k,v in w.room_details[parcel].items() if k in ('world_region','press_locality','group')}
    row.update(coords,id=ext,name=name,description=desc,environment='road',street_front=rid,roof_joins=[],exits=exits)
    w.room_details[ext]=row;w.add_room(Room(ext,name,desc,exits,group=base.group,**coords))
    base.exits['approach unit '+str(idx)]=ext
    w._street_origins[ext]=rid
    return ext

def editor_collisions(data,edited=None,value=None):
    """Compare explicit above-ground building claims while editing a floor plan."""
    rooms={r['id']:r for r in data.get('room',[])}
    if edited and edited[0]=='room':
        rid=edited[1];rooms[rid]={**rooms[rid],edited[2]:value}
    claims=defaultdict(set);membership=set()
    for b in data.get('building',[]):
        members=value if edited==('building',b['id'],'rooms') else b.get('rooms',[])
        if not isinstance(members,list):continue
        for rid in members:
            r=rooms.get(rid)
            if r is None:continue
            membership.add(rid)
            if room_style(dict(r,_visual_building=b))[0]=='building':
                point=tuple(r.get(k) for k in ('map_x','map_y','map_z'))
                if all(type(v) is int for v in point) and point[2]>=0:claims[point[:2]].add(b['id'])
    return {(pt,tuple(sorted(owners))) for pt,owners in claims.items() if len(owners)>1}
