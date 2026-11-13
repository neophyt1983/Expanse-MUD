"""Join the open land around older, narrow campaign surveys to the walking graph.

An authored lot, wall, door, water crossing or exit always wins its coordinate.
Only the official outdoor surveys grow a margin. New ground has persistent
coordinates, four walking exits and the biome of the nearest surveyed land.
"""
from collections import defaultdict
from engine import wildlands
from engine.visual_mapping import room_style

DIRECTIONS={'west':(-1,0,'east'),'east':(1,0,'west'),'north':(0,-1,'south'),'south':(0,1,'north')}

def region(row):
    if row.get('world_region'):return ('survey',row['world_region'])
    planet=row.get('planet') or {}
    if planet.get('cell') or planet.get('field'):return None
    if 'lat' in planet and 'lon' in planet:return ('regional',row.get('group'),planet.get('lat'),planet.get('lon'))
    if row.get('press_locality'):
        return ('locality', row.get('group'), row['press_locality'])
    return None

def ground_index(world):
    if not getattr(world,'rules',{}).get('tile_survey'):
        return None
    index=getattr(world,'_ground_lots',None)
    if index is None:
        from engine.coordinates import prepare_survey
        prepare_survey(world)
        index=world._ground_lots=defaultdict(list)
        biomes=world._natural_biomes=defaultdict(list)
        open_biomes=world._surveyed_open_biomes=defaultdict(list)
        for rid,room in world.rooms.items():
            x,y,z=room.map_x,room.map_y,room.map_z
            index[x,y,z].append(rid)
            row=world.room_details.get(rid,{})
            terrain=(row.get('climate') or {}).get('terrain')
            if (x is not None and y is not None and terrain and not row.get('_generated_ground')
                    and row.get('map_visibility')!='hidden' and room_style(row)[0]=='outdoors'):
                source=open_biomes if row.get('open_country') else biomes
                source[x//8,y//8,z].append((x,y,rid,terrain))
    return index


def survey(w,origin):
    if not wildlands.enabled(w) or wildlands.cell(w,origin):return
    if origin in getattr(w,'_country_patches',{}):return w._country_patches[origin]
    row=w.room_details[origin];realm=region(row)
    if realm is None:return
    cache=getattr(w,'_country_surveys',None)
    if cache is None:cache=w._country_surveys={}
    layer=w.rooms[origin].map_z
    if (realm,layer) not in cache:
        lots=defaultdict(list);biomes={};group=w.rooms[origin].group
        for rid,r in w.room_details.items():
            room=w.rooms[rid]
            if region(r)!=realm or room.map_z!=layer or room.map_x is None or room.map_y is None:continue
            xy=(room.map_x,room.map_y);lots[xy].append(rid)
            t=r.get('climate',{}).get('terrain')
            if t and t not in ('floor','building','road','unknown'):biomes[xy]=t
        if not lots:return
        old=[rid for ids in lots.values() for rid in ids if w.room_details[rid].get('planet',{}).get('regional')]
        anchor=min(old or [rid for ids in lots.values() for rid in ids]) if realm[0]=='regional' else min(rid for ids in lots.values() for rid in ids)
        cache[realm,layer]=dict(lots=lots,biomes=biomes,anchor=anchor,group=group,layer=layer,land={},blocks=set(),water={})
    return cache[realm,layer]

def safe(w,rid):
    r=w.room_details[rid];room=w.rooms[rid]
    cached=getattr(w,'_compiled_map',None)
    style=cached[0][rid]['_visual_style'] if cached and rid in cached[0] else room_style(r)
    return (style[0]=='outdoors' and room.map_visibility!='hidden' and not r.get('gates') and not r.get('requires_boat')
            and not r.get('property_unit_id') and not r.get('street_front') and not r.get('physical_locks')
            and not r.get('building') and r.get('environment')!='ocean')

def block_sources(w, bx, by, z):
    """Use the same authored biome samples for a public map and a walking block."""
    cx, cy = bx * 8 + 4, by * 8 + 4
    def rank(sample):
        return (abs(cx - sample[0]) + abs(cy - sample[1]), sample)
    for index in (w._natural_biomes, w._surveyed_open_biomes):
        samples = []
        for yy in range(by - 4, by + 5):
            for xx in range(bx - 4, bx + 5):
                batch = index.get((xx, yy, z), ())
                if index is w._surveyed_open_biomes:
                    batch = (s for s in batch if max(abs(cx-s[0]), abs(cy-s[1])) <= 28)
                samples.extend(batch)
        nearest = sorted(samples, key=rank)[:12]
        if any(max(abs(cx-s[0]), abs(cy-s[1])) <= 28 for s in nearest):
            return nearest
    return ()


def tile_source(sources, x, y):
    return min(sources, key=lambda a: (abs(x-a[0]) + abs(y-a[1]), a))


def block(w,s,bx,by):
    if (bx,by) in s['blocks']:return
    s['blocks'].add((bx,by));lots=s['lots'];land=s['land']
    index=ground_index(w)
    sources=()
    if index is not None:
        sources=block_sources(w,bx,by,s['layer'])
        if not sources:return
    else:
        cx,cy=bx*8+4,by*8+4
        nearest=sorted(s['biomes'],key=lambda xy:(abs(cx-xy[0])+abs(cy-xy[1]),xy))[:12]
        if not nearest or min(max(abs(cx-x),abs(cy-y)) for x,y in nearest)>28:return
    made=[]
    for y in range(by*8,by*8+8):
        for x in range(bx*8,bx*8+8):
            reserved = (index.get((x, y, s['layer']), ()) if index is not None else lots.get((x, y), ()))
            if reserved:
                compiled = getattr(w, '_compiled_map', None)
                def visible_surface(rid):
                    row = w.room_details[rid]
                    style = compiled[0][rid]['_visual_style'] if compiled and rid in compiled[0] else room_style(row)
                    return w.rooms[rid].map_visibility != 'hidden' and (style[0] == 'outdoors' or
                            (style[0] == 'building' and s['layer'] >= 0))
                if any(visible_surface(rid) for rid in reserved):
                    continue
            if sources:
                src=tile_source(sources,x,y)
                t=src[3]
            else:
                closest=min(nearest,key=lambda xy:(abs(x-xy[0])+abs(y-xy[1]),xy))
                t=s['biomes'][closest]
            if reserved:
                # The lot is occupied underground or private. Display only the public survey.
                xyz = (x, y, s['layer'])
                if not hasattr(w, '_country_cover'):
                    w._country_cover = {}
                w._country_cover[xyz] = t
                atlas = getattr(w, '_atlas_ground', None)
                if atlas:
                    from engine.world_atlas import terrain_value
                    terrain_value(atlas, xyz, (False, t))
                continue
            # Never create a dry-land bypass along an authored water feature.
            if t in ('river','lake','ocean','water'):
                s['water'][x,y]=t
                if index is not None:
                    if not hasattr(w,'_country_water'):
                        w._country_water={}
                    w._country_water[x,y,s['layer']]=t
                    atlas=getattr(w,'_atlas_ground',None)
                    if atlas:
                        from engine.world_atlas import terrain_value
                        terrain_value(atlas,(x,y,s['layer']),(False,t))
                continue
            rid=f"open_grid_{s['layer']}_{x}_{y}" if index is not None else f"open_{s['anchor']}_{x}_{y}"
            if rid in w.rooms:continue
            land_spec=w.rules.get('open_land')
            if not land_spec:return
            name=land_spec['names'].get(t,land_spec['default'])
            author=w.room_details[src[2]] if sources else {}
            group=author.get('group') if sources else s['group']
            geo={}
            if author.get('planet'):
                geo['planet']=dict(author['planet'])
            if author.get('tile_position'):
                point=author['tile_position']
                geo['survey_from']=[point['lat'],point['lon'],src[0],src[1]]
            wildlands.record(w,rid,name,land_spec['description'],group,x,y,s['layer'],**geo,
                             climate={'terrain':t,'sheltered':False,'elevation_m':(author.get('climate') or {}).get('elevation_m',0)},environment='wilderness',open_country=True,campable=True)
            land[x,y]=rid;w._country_patches[rid]=s;made.append((x,y,rid))
    for x,y,rid in made:
        for direction,(dx,dy,back) in DIRECTIONS.items():
            pos=(x+dx,y+dy);target=land.get(pos)
            if not target:
                choices=(index.get((*pos,s['layer']),()) if index is not None else lots.get(pos,()))
                available=sorted(r for r in choices if safe(w,r) and back not in w.rooms[r].exits)
                if not available:continue
                target=available[0]
            if back in w.rooms[target].exits or direction in w.rooms[rid].exits:continue
            wildlands.link(w,rid,direction,target);wildlands.link(w,target,back,rid)

def extend(w,origin,hx,hy):
    if not wildlands.enabled(w):return
    wildlands.survey_rectangle(w,origin,hx,hy)
    if wildlands.cell(w,origin):
        return
    if not hasattr(w,'_country_patches'):w._country_patches={}
    base=w.rooms[origin]
    if base.map_x is None or base.map_y is None:return
    row=w.room_details[origin]
    if room_style(row)[0]!='outdoors':return
    s=survey(w,origin)
    if not s:return
    for by in range((base.map_y-hy)//8,(base.map_y+hy)//8+1):
        for bx in range((base.map_x-hx)//8,(base.map_x+hx)//8+1):block(w,s,bx,by)

def snapshot(w):
    return [[s['anchor'],sorted(s['blocks'])] for s in getattr(w,'_country_surveys',{}).values() if s['land']]

def restore(w,saved):
    if not wildlands.enabled(w):return
    w._country_patches={}
    for anchor,blocks in saved:
        if anchor not in w.rooms:continue
        s=survey(w,anchor)
        if s:
            for bx,by in blocks:
                move=next((r for r in w.rules.get('district_resurvey',[]) if r[0]-35<=bx*8<=r[2]+35 and r[1]-35<=by*8<=r[3]+35),None)
                if move is None:
                    block(w,s,bx,by)
                    continue
                dx,dy=move[4:6]
                for y in range((by*8+dy)//8,(by*8+7+dy)//8+1):
                    for x in range((bx*8+dx)//8,(bx*8+7+dx)//8+1):
                        block(w,s,x,y)


def saved_room(w,rid):
    if rid in w.rooms or not isinstance(rid,str) or not rid.startswith('open_'):
        return rid
    try:
        anchor,x,y=rid[5:].rsplit('_',2)
        x,y=int(x),int(y)
    except ValueError:
        return rid
    for ax,ay,bx,by,dx,dy,gate in w.rules.get('district_resurvey',[]):
        if not (ax-35<=x<=bx+35 and ay-35<=y<=by+35):
            continue
        layer=w.rooms[gate].map_z
        picks=(ground_index(w) or {}).get((x+dx,y+dy,layer),[])
        found=next((key for key in sorted(picks) if safe(w,key)),None)
        return found or gate
    if w.rules.get('tile_survey'):
        return next((key for key in (ground_index(w) or {}).get((x,y,0),[]) if safe(w,key)),rid)
    return rid
