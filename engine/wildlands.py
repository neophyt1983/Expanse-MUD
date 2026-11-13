"""Expedition country and the people who live along its borders."""
from types import SimpleNamespace
from engine.core import Room, Entity
from engine import quest_progress, gazette

CHUNK = 8
STEPS = {'north': (0,-1), 'south': (0,1), 'east': (1,0), 'west': (-1,0),
         'northeast': (1,-1), 'northwest': (-1,-1), 'southeast': (1,1), 'southwest': (-1,1)}

def tile(w,i,x,y):
    return f'{w.field_regions[i].prefix}_{x}_{y}'

def cell(w,rid):
    if not isinstance(rid,str):return None
    try:
        prefix,x,y=rid.rsplit('_',2)
        i=w.field_prefixes[prefix]
        region=w.field_regions[i]
        x,y=int(x),int(y)
    except (ValueError,KeyError,AttributeError):return None
    return (i,x,y) if 0<=x<region.width and 0<=y<region.height else None

def role(w,actor):
    return w.npcs.get(actor.source_def,{}).get('expedition_role')

def enabled(w):
    return getattr(w,'expedition_country',False)

def record(w,rid,name,description,group,x,y,z,**detail):
    room=Room(rid,name,description,group=group,map_x=x,map_y=y,map_z=z)
    w.add_room(room)
    w.room_details[rid]=dict(id=rid,name=name,description=description,group=group,map_x=x,map_y=y,map_z=z,exits=room.exits,_generated_ground=True,**detail)
    if getattr(w,'_ground_lots',None) is not None:w._ground_lots[x,y,z].append(rid)
    cached=getattr(w,'_compiled_map',None)
    if cached or getattr(w, '_tile_survey_ready', False):
        from engine.coordinates import surveyed_position
        surveyed_position(w,w.room_details[rid],(x,y,z))
    if cached:
        from engine.visual_mapping import room_style
        row=dict(w.room_details[rid]);row['_visual_style']=room_style(row)
        cached[0][rid]=row;cached[1][rid]=(x,y,z)
        travel_index=getattr(w,'_travel_index',None)
        if travel_index and travel_index[0] is cached:
            travel_index[1][x,y,z].append(rid)
        ground=getattr(w,'_atlas_ground',None)
        if ground and ground['compiled'] is cached:
            from engine.world_atlas import terrain_cell
            terrain_cell(ground,row,(x,y,z))
    return room

def link(w,source,direction,target):
    room=w.rooms[source]
    room.exits[direction]=target
    if getattr(w,'_compiled_map',None):
        w._compiled_map[0][source]['exits'][direction]=target

def chunk(w,i,cx,cy):
    region=w.field_regions[i]
    if not (0<=cx*CHUNK<region.width and 0<=cy*CHUNK<region.height):return
    key=(i,cx,cy)
    if key in w.field_chunks:return
    w.field_chunks.add(key)
    region=w.field_regions[i];group=w.rooms[region.gate].group
    for y in range(cy*CHUNK,min((cy+1)*CHUNK,region.height)):
        for x in range(cx*CHUNK,min((cx+1)*CHUNK,region.width)):
            rid=tile(w,i,x,y)
            name=region.landmark if (x,y)==(region.landmark_x,region.trail_y) else region.name+' Trailhead' if (x,y)==(0,region.trail_y) else region.name+' · '+str(x+1)+' east, '+str(y+1)+' south'
            desc=(region.hazards[0]+' '+(region.trail_note if y==region.trail_y else 'The marked expedition trail lies '+('south.' if y<region.trail_y else 'north.')))
            if rid in w.rooms or region.grid[y][x] == ".":continue
            record(w,rid,name,desc,group,region.origin[0]+x,region.origin[1]+y,region.origin[2],
                   climate={'terrain':region.palette[ord(region.grid[y][x])-65],'sheltered':region.underground,'latitude':region.latitude,'elevation_m':region.elevation},route_surface=({'kind':'trail','axis':'east_west'} if y==region.trail_y else {}),environment='cave' if region.underground else 'wilderness',
                   world_region=region.name,open_country=True,campable=True,press_locality=w.room_details[region.gate].get('press_locality'))
    for y in range(cy*CHUNK,min((cy+1)*CHUNK,region.height)):
        for x in range(cx*CHUNK,min((cx+1)*CHUNK,region.width)):
            rid=tile(w,i,x,y)
            if rid not in w.rooms:continue
            for d,(dx,dy) in STEPS.items():
                dest=tile(w,i,x+dx,y+dy)
                if dest in w.rooms:
                    link(w,rid,d,dest)
                    if not(cx*CHUNK<=x+dx<(cx+1)*CHUNK and cy*CHUNK<=y+dy<(cy+1)*CHUNK):
                        back=next(k for k,v in STEPS.items() if v==(-dx,-dy))
                        link(w,dest,back,rid)

def surround(w,where,hx=6,hy=8):
    pos=cell(w,where)
    if not pos or not enabled(w):return
    i,x,y=pos
    for cy in range(max(0,y-hy)//CHUNK,min(w.field_regions[i].height-1,y+hy)//CHUNK+1):
        for cx in range(max(0,x-hx)//CHUNK,min(w.field_regions[i].width-1,x+hx)//CHUNK+1):chunk(w,i,cx,cy)

def survey_rectangle(w, origin, hx, hy):
    room = w.rooms[origin]
    if room.map_x is None or room.map_y is None:
        return
    for i, region in enumerate(w.field_regions):
        rx, ry, z = region.origin
        if z != room.map_z:
            continue
        left, right = max(0, room.map_x-hx-rx), min(region.width-1, room.map_x+hx-rx)
        top, bottom = max(0, room.map_y-hy-ry), min(region.height-1, room.map_y+hy-ry)
        if left > right or top > bottom:
            continue
        for cy in range(top//CHUNK, bottom//CHUNK+1):
            for cx in range(left//CHUNK, right//CHUNK+1):
                chunk(w, i, cx, cy)


def restore(w,state):
    if enabled(w):
        for sector in list(state.get('field_sectors',[])):
            try:i,sx,sy=map(int,sector.split('/'))
            except (AttributeError,ValueError):continue
            if 0<=i<len(getattr(w,"field_regions",())):populate_sector(w,i,sx,sy,restoring=True)
        for key in state.get('expedition_chunks',[]):
            if isinstance(key,list) and len(key)==3 and all(type(k) is int for k in key) and 0<=key[0]<len(getattr(w,"field_regions",())):
                chunk(w,*key)

def definition(w,ident,name,room,role,*,human=True,hp=28,attack=4,defense=2,**extra):
    w.npcs[ident]=dict(id=ident,name=name,description=role,spawn_room=room,role=role,group=w.rooms[room].group,
                       hp=hp,attack=attack,defense=defense,social_profile={'sentient':human,'species':'human' if human else 'expedition_wildlife'},**extra)

def install(w):
    config = getattr(w, 'rules', {})
    regions = config.get('regions', [])
    if not regions:
        return
    w.field_regions = [SimpleNamespace(**row) for row in regions]
    w.field_prefixes = {region.prefix:i for i,region in enumerate(w.field_regions)}
    for region in w.field_regions:
        region.width=len(region.grid[0]);region.height=len(region.grid)
    w.expedition_country = True
    w.field_chunks = set()
    w._field_sectors = set()
    w._field_travellers = set()

def check(actor,now,region,threat):
    from hashlib import blake2s
    score=actor.progress.get('expedition_sanity',100)
    roll=int.from_bytes(blake2s(f'{actor.id}/{now}/{region}/{threat}'.encode(),digest_size=2).digest(),'big')%100
    fortitude=actor.progress.get('npc_life',{}).get('fortitude',actor.stats.get('fortitude',50))
    passed=roll<max(15,min(85,score-12+(fortitude-50)//5))
    actor.progress['expedition_sanity']=max(0,score-(2 if passed else 8))
    return passed

def summon(w,i,now):
    key=w.field_regions[i].threat;eid='npc:'+key
    if eid in w.entities and w.entities[eid].alive:return False
    summoner=w.entities.get('npc:'+w.field_regions[i].summoner)
    if not summoner or not summoner.alive:return False
    state=w.living_state.setdefault('field_summons',{})
    if now-state.get(key,-9999)<180:return False
    d=w.npcs[key]
    if eid in w.entities:
        old=w.entities[eid];room=w.rooms[old.location]
        if eid in room.entities:room.entities.remove(eid)
    creature=Entity(eid,d['name'],d['hp'],d['hp'],d['attack'],d['defense'],source_def=key)
    w.killed_npcs.discard(key)
    w.add_entity(creature,summoner.location);state[key]=now
    summoner.activity='calling '+creature.name
    return True

def entered(w,actor,old):
    if not enabled(w):return
    here,prev=cell(w,actor.location),cell(w,old)
    if here:
        if here[1]>=w.field_regions[here[0]].landmark_x or abs(here[2]-w.field_regions[here[0]].trail_y)>=24:actor.progress['field_witness']=True
        w._field_travellers.add(actor.id)
        if actor.is_player:
            surround(w,actor.location)
            populate_sector(w,here[0],here[1]//16,here[2]//16)
    if not here:w._field_travellers.discard(actor.id)
    if prev and (not here or prev[0]!=here[0]):
        actor.progress.pop('field_minutes',None)
        if actor.progress.pop('field_witness',False):
            actor.progress.setdefault('expedition_memories',{})[w.field_regions[prev[0]].name]=w.field_regions[prev[0]].memory

def advance(w,before,now):
    if not enabled(w):return
    from engine import ward_life
    ward_life.advance(w,before,now)
    # Index only the expedition cast and PCs. Distant mountains cost no per-tile simulation.
    respawns=w.living_state.get('field_hunts',{})
    for source,due in list(respawns.items()):
        if now<due or source not in w.npcs:continue
        d=w.npcs[source];ident='npc:'+source;previous=w.entities.get(ident)
        if previous and previous.alive:continue
        if previous and ident in w.rooms[previous.location].entities:w.rooms[previous.location].entities.remove(ident)
        replacement=Entity(ident,d['name'],d['hp'],d['hp'],d['attack'],d['defense'],source_def=source)
        w.killed_npcs.discard(source);w.add_entity(replacement,d['spawn_room']);del respawns[source]
    cast=[a for a in w.entities.values() if a.is_player or a.id in w._field_travellers or role(w,a) or 'expedition_sanity' in a.progress or cell(w,a.location)]
    for a in cast:
        if not a.alive:continue
        pos=cell(w,a.location)
        if not pos:
            if 'expedition_sanity' in a.progress and now//15>before//15:
                a.progress['expedition_sanity']=min(100,a.progress['expedition_sanity']+2*(now//15-before//15))
            continue
        i,x,y=pos
        predator=role(w,a) in ('quarry','predator') and not w.npcs.get(a.source_def,{}).get('social_profile',{}).get('sentient')
        if now//10>before//10 and predator:
            hunger=min(100,a.progress.get('field_hunger',52)+6);a.progress['field_hunger']=hunger
            a.activity='tracking a meal' if hunger>=50 else 'digesting a meal'
            if hunger>=50:
                paths=w.rooms[a.location].exits
                targets=[p for p in cast if p.alive and (p.is_player or role(w,p)=='quarry') and p is not a and cell(w,p.location) and cell(w,p.location)[0]==i]
                prey=min(targets,key=lambda p:abs(cell(w,p.location)[1]-x)+abs(cell(w,p.location)[2]-y),default=None)
                if prey and prey.location==a.location:
                    prey.take_damage(a.attack);a.progress['field_hunger']=25;a.activity='feeding after a strike'
                    if not prey.alive and role(w,prey)=='quarry':
                        w.living_state.setdefault('field_hunts',{})[prey.source_def]=now+360
                elif prey and max(abs(cell(w,prey.location)[1]-x),abs(cell(w,prey.location)[2]-y))<=4:
                    px,py=cell(w,prey.location)[1:];dest=tile(w,i,x+(px>x)-(px<x),y+(py>y)-(py<y))
                    if dest in paths.values():w.move_entity(a.id,dest)
        if not (a.is_player or w.npcs.get(a.source_def,{}).get('social_profile',{}).get('sentient')):continue
        if x==0:continue
        if role(w,a)=='survivor' and now//60>before//60:
            a.progress.setdefault('expedition_memories',{})[w.field_regions[i].name]=w.field_regions[i].memory
        prior=a.progress.get('field_minutes',0);elapsed=prior+now-before;a.progress['field_minutes']=elapsed
        if a.is_player and elapsed//30>prior//30:quest_progress.action(a,'endure '+w.field_regions[i].name)
        if now//15>before//15 and (x>=20 or y!=w.field_regions[i].trail_y) and a.progress.get('field_shelter_until',0)<now:
            if (now//15)%3==2:a.take_damage(w.field_regions[i].hazard_damage)
            if not a.alive:continue
            if not check(a,now,i,'field'):
                a.progress['field_witness']=True;a.take_damage(1)
            a.activity='taking shelter from '+('the passage hazard' if w.field_regions[i].underground else 'the weather')
        if x>=w.field_regions[i].landmark_x-2 and now//20>before//20:summon(w,i,now)

def command(ctx,args):
    w,a=ctx.world,ctx.player;pos=cell(w,a.location);now=w.living_state.get('minute',375)
    memories=a.progress.get('expedition_memories',{})
    if ctx.raw.split()[0].lower()=='sanity':
        return 'Sanity '+str(a.progress.get('expedition_sanity',100))+'/100. '+(' '.join('Since returning from '+k+', you '+v+'.' for k,v in memories.items()) or 'No memories of the deep country yet.')
    args=args.strip().lower()
    if not pos:
        for i,r in enumerate(w.field_regions):
            if a.location==r.gate:
                if args in ('enter','trail'):
                    w.move_entity(a.id,tile(w,i,0,r.trail_y));return 'You follow the trail into '+r.name+'.'
                return 'Expedition to '+r.name+'. Speak with '+r.guide+' or the expedition captain. Choose Enter trail.'
        return '\n'.join(r.name+' — '+w.rooms[r.gate].name for r in w.field_regions)
    i,x,y=pos;r=w.field_regions[i]
    if args=='return' and (x,y)==(0,r.trail_y):
        w.move_entity(a.id,r.gate);return 'You return to '+w.rooms[r.gate].name+'.'
    if args=='shelter':
        a.progress['field_shelter_until']=now+20
        return 'You find a protected place to wait through the next hazard.'
    if args=='search' and (x,y)==(r.landmark_x,r.trail_y):
        relic=w.room_details[a.location]['search_reward']
        if relic in a.inventory:return 'You already carry '+r.relic+'.'
        a.inventory.append(relic)
        return 'You recover '+r.relic+'.'
    if args=='face' and (x,y)==(r.landmark_x,r.trail_y):
        if now<a.progress.get('field_retry',0):return 'Take a breath. You can face the vigil again at the next game minute.'
        a.progress['field_retry']=now+1
        summon(w,i,now);a.progress['field_witness']=True
        if check(a,now,i,'vigil'):
            quest_progress.action(a,'face '+r.name);return 'The vigil answers. You hold your gaze.'
        return 'The vigil answers. Your nerve breaks. You can retreat and recover in town.'
    return r.name+'. '+r.hazards[(now//15)%len(r.hazards)]+' '+('The return path to town is here.' if x==0 and y==r.trail_y else 'The trailhead is at the western end of the marked trail.')

def weather(w,i,minute,base):
    phases = w.field_regions[i].weather
    return {**base, **phases[(minute//15) % len(phases)]}

def populate_sector(w,i,sx,sy,*,restoring=False):
    if not 0<=sx*16<w.field_regions[i].width or not 0<=sy*16<w.field_regions[i].height:return
    key=f'{i}/{sx}/{sy}'
    seen=w.living_state.setdefault('field_sectors',[])
    if key in w._field_sectors:return
    w._field_sectors.add(key)
    if key not in seen:seen.append(key)
    record = w.field_regions[i].sectors.get(f'{sx}/{sy}')
    if not record:
        return
    ident = record['id']
    site = record['spawn_room']
    _, x, y = cell(w, site)
    chunk(w,i,x//CHUNK,y//CHUNK)
    w.npcs[ident] = record
    name = record['name']
    human = record['social_profile']['sentient']
    if not restoring and ident not in w.killed_npcs:
        d=w.npcs[ident];e=Entity('npc:'+ident,name,d['hp'],d['hp'],d['attack'],d['defense'],source_def=ident)
        w.add_entity(e,site)
        if human:e.progress.setdefault('expedition_memories',{})[w.field_regions[i].name]=w.field_regions[i].memory
