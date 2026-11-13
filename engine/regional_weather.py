"""Opt-in regional weather, driven only by the canonical living clock.

A small fictional weather simulation, not a forecast. All affected geography
and public shelters are authored. Read-only local projections never advance RNG.
"""
from collections import deque
from copy import deepcopy
import hashlib
import json
import math
import re
from engine import worldtime

VERSION=1
MAX_REGIONS=32
MAX_ROOMS=256
MAX_CATCHUP=360
MAX_LOG=128
MAX_ROUTE=12
STATES=('sunny','partly cloudy','rain','wind','thunderstorm')
DIRECTIONS=('north','northeast','east','southeast','south','southwest','west','northwest')
SEVERE=('severe thunderstorm','tornado')
DEFAULT_WEIGHTS={
 'spring':{'sunny':30,'partly cloudy':30,'rain':25,'wind':10,'thunderstorm':5},
 'summer':{'sunny':45,'partly cloudy':25,'rain':15,'wind':10,'thunderstorm':5},
 'autumn':{'sunny':25,'partly cloudy':30,'rain':30,'wind':12,'thunderstorm':3},
 'winter':{'sunny':20,'partly cloudy':35,'rain':35,'wind':9,'thunderstorm':1}}
REGION_FIELDS={'id','name','rooms','shelters','seasonal_weights','duration_minutes','warning_minutes',
 'severe_chance','tornado_chance','severe_cooldown_minutes','consequences','exposure','tornado_rooms','latitude','damage'}


def number(value,low,high):return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def indoor(row):
    c=row.get('climate',{});c=c if isinstance(c,dict) else {}
    return (c.get('sheltered') is True or c.get('terrain')=='cave' or
            row.get('environment') in ('inside','indoor','indoors','interior','building','cave'))


def validate(data,metadata):
    preference_issues=[]
    for row in data.get('room',[]):
        if row.get('weather_shelter_kind','public_hall') not in ('public_hall','reinforced','cellar'):
            preference_issues.append(str(row.get('id'))+': invalid weather_shelter_kind')
    for row in data.get('npc',[]):
        if row.get('weather_refuge_preference','auto') not in ('auto','nearest','reinforced','cellar'):
            preference_issues.append(str(row.get('id'))+': invalid weather_refuge_preference')
        detour=row.get('weather_refuge_detour',2)
        if type(detour) is not int or not 0<=detour<=3:
            preference_issues.append(str(row.get('id'))+': weather_refuge_detour must be 0–3')
    if 'regional_weather' not in metadata:return preference_issues
    cfg=metadata['regional_weather'];issues=list(preference_issues)
    if not isinstance(cfg,dict):return ['regional_weather must be an object']
    if set(cfg)-{'version','enabled','seed','regions'}:issues.append('regional_weather has unknown fields')
    if cfg.get('version')!=VERSION or type(cfg.get('version')) is not int:issues.append('regional_weather.version must be 1')
    if type(cfg.get('enabled')) is not bool:issues.append('regional_weather.enabled must be boolean')
    if type(cfg.get('seed')) is not int or not 0<=cfg['seed']<2**63:issues.append('regional_weather.seed must be an integer from 0 to 2^63−1')
    regions=cfg.get('regions',[])
    if not isinstance(regions,list) or len(regions)>MAX_REGIONS:return issues+['regional_weather.regions must list at most 32 regions']
    rooms={r['id']:r for r in data.get('room',[]) if isinstance(r,dict) and isinstance(r.get('id'),str)}
    region_ids=set();assigned=set()
    for region in regions:
        if not isinstance(region,dict):issues.append('weather region must be an object');continue
        rid=region.get('id');where='weather region '+str(rid)
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',rid):issues.append(where+': invalid ID')
        elif rid in region_ids:issues.append(where+': duplicate ID')
        else:region_ids.add(rid)
        if set(region)-REGION_FIELDS:issues.append(where+': unknown fields')
        from engine import storm_damage
        issues.extend(storm_damage.validate(data,region))
        if not isinstance(region.get('name'),str) or not 1<=len(region['name'])<=100:issues.append(where+': name must have 1–100 characters')
        listed=region.get('rooms',[])
        if not isinstance(listed,list) or not 1<=len(listed)<=MAX_ROOMS or any(not isinstance(r,str) or r not in rooms for r in listed):
            issues.append(where+': rooms must list 1–256 existing room IDs');continue
        if len(set(listed))!=len(listed) or assigned.intersection(listed):issues.append(where+': rooms must be unique and belong to only one weather region')
        assigned.update(listed)
        for field,default,low,high in [('latitude',35,-90,90),('severe_chance',.03,0,.1),('tornado_chance',.01,0,.05)]:
            if not number(region.get(field,default),low,high):issues.append(where+': invalid '+field)
        for field,default,low,high in [('warning_minutes',20,15,60),('severe_cooldown_minutes',3000,1500,30000)]:
            val=region.get(field,default)
            if type(val) is not int or not low<=val<=high:issues.append(where+': invalid '+field)
        if type(region.get('consequences',True)) is not bool:issues.append(where+': consequences must be boolean')
        durations=region.get('duration_minutes',[60,240])
        if not isinstance(durations,list) or len(durations)!=2 or any(type(v) is not int or not 30<=v<=360 for v in durations) or durations[0]>durations[1]:issues.append(where+': duration_minutes must be [min,max] from 30–360')
        weights=region.get('seasonal_weights',DEFAULT_WEIGHTS)
        if not isinstance(weights,dict) or set(weights)!=set(worldtime.SEASONS):issues.append(where+': seasonal_weights must contain all four seasons')
        else:
            for season,row in weights.items():
                if not isinstance(row,dict) or set(row)-set(STATES) or not row or any(not number(v,0,100) for v in row.values()) or sum(row.values())<=0:issues.append(where+': invalid weights for '+season)
        exposure=region.get('exposure',{})
        if not isinstance(exposure,dict) or any(key not in listed or not number(val,0,1) for key,val in exposure.items()):issues.append(where+': exposure must map listed rooms to 0–1')
        shelters=region.get('shelters',[])
        if not isinstance(shelters,list) or len(shelters)>32 or any(s not in listed for s in shelters if isinstance(s,str)) or any(not isinstance(s,str) for s in shelters):
            issues.append(where+': shelters must list at most 32 rooms in the region');continue
        for shelter in shelters:
            row=rooms.get(shelter,{})
            if not indoor(row) or row.get('weather_shelter') is not True:issues.append(where+': each shelter must be a real indoor room explicitly marked weather_shelter=true')
            if row.get('land_uses') or row.get('property_plot') or row.get('land_use') in ('house','business'):issues.append(where+': rentable/private land cannot be designated public shelter')
        tornado=region.get('tornado_rooms',[])
        if not isinstance(tornado,list) or len(tornado)>8 or any(not isinstance(r,str) or r not in listed or indoor(rooms.get(r,{})) for r in tornado):issues.append(where+': tornado_rooms must list at most eight outdoor rooms in the region')
        if number(region.get('severe_chance',.03),0,.1) and region.get('severe_chance',.03)>0:
            if not shelters:issues.append(where+': severe-prone regions need actual reachable public shelters')
            # Two bounded traversals per refuge, rather than per outdoor room.
            covered=_static_refuge_coverage(rooms,listed,shelters)
            for start in listed:
                if not indoor(rooms[start]) and start not in covered:
                    issues.append(where+': '+start+' needs public shelter and return routes within 12 steps')
    return issues


def _static_refuge_coverage(rooms,listed,shelters):
    allowed=set(listed);safe=set(shelters)
    reverse={rid:[] for rid in listed};return_edges={rid:[] for rid in listed}
    for source in listed:
        for dest in rooms[source].get('exits',{}).values():
            if dest not in allowed or (indoor(rooms[dest]) and dest not in safe):continue
            return_edges[source].append(dest)
            if not rooms[dest].get('land_uses') and rooms[dest].get('land_use') not in ('house','business'):
                reverse[dest].append(source)
    def reachable(graph,start):
        seen={start};pending=deque([(start,0)])
        while pending:
            here,depth=pending.popleft()
            if depth>=MAX_ROUTE:continue
            for dest in graph[here]:
                if dest not in seen:seen.add(dest);pending.append((dest,depth+1))
        return seen
    covered=set()
    for shelter in shelters:
        covered.update(reachable(reverse,shelter)&reachable(return_edges,shelter))
    return covered


def _configuration(w):
    cfg=getattr(w,'metadata',{}).get('regional_weather')
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True:return None
    # Cache only a validated content signature. Nested Creator edits and graph
    # changes are included; no mutable world/actor results are cached.
    ids=set()
    for r in cfg.get('regions',[]) if isinstance(cfg.get('regions'),list) else []:
        if isinstance(r,dict) and isinstance(r.get('rooms'),list):ids.update(x for x in r['rooms'] if isinstance(x,str))
    rows=[dict(getattr(w,'room_details',{}).get(rid,{}),id=rid,exits=dict(w.rooms[rid].exits)) for rid in sorted(ids) if rid in w.rooms]
    damage=[r.get('damage',{}) for r in (cfg.get('regions',[]) if isinstance(cfg.get('regions',[]),list) else []) if isinstance(r,dict) and isinstance(r.get('damage',{}),dict)]
    def target_ids(kind,key):
        return {t[key] for d in damage for t in (d.get(kind,[]) if isinstance(d.get(kind,[]),list) else []) if isinstance(t,dict) and isinstance(t.get(key),str)}
    building_ids=target_ids('structures','building')
    resource_ids=target_ids('resources','resource')
    destinations=target_ids('routes','destination')
    rows.extend(dict(getattr(w,'room_details',{}).get(rid,{}),id=rid,exits=dict(w.rooms[rid].exits)) for rid in sorted(x for x in destinations if isinstance(x,str) and x not in ids and x in w.rooms))
    data={'room':rows,'building':[v for k,v in getattr(w,'buildings',{}).items() if k in building_ids], 'resource':[v for k,v in getattr(w,'resources',{}).items() if k in resource_ids]}
    try:signature=hashlib.sha256(json.dumps([cfg,data],sort_keys=True,allow_nan=False).encode()).digest()
    except (TypeError,ValueError):return None
    cached=getattr(w,'_regional_weather_config',None)
    if cached and cached[0]==signature:return cached[1]
    if validate(data,w.metadata):return None
    resolved={r['id']:r for r in cfg.get('regions',[])}
    byroom={rid:r['id'] for r in resolved.values() for rid in r['rooms']}
    result=(cfg,resolved,byroom)
    w._regional_weather_config=(signature,result)
    return result


def _rng(value):
    # Portable SplitMix64, saved as one unsigned integer per region.
    mask=(1<<64)-1;value=(value+0x9E3779B97F4A7C15)&mask;z=value
    z=((z^(z>>30))*0xBF58476D1CE4E5B9)&mask;z=((z^(z>>27))*0x94D049BB133111EB)&mask;z^=z>>31
    return value,(z>>11)/float(1<<53)


def _seed(seed,region):return int.from_bytes(hashlib.sha256(f'weather-v1:{seed}:{region}'.encode()).digest()[:8],'big')


def _roll(*values):return int.from_bytes(hashlib.sha256(':'.join(map(str,values)).encode()).digest()[:8],'big')/2**64


def _new_front(cfg,region,row,minute):
    def draw():
        row['rng'],value=_rng(row['rng']);return value
    season=worldtime.season(minute,region.get('latitude',35));weights=region.get('seasonal_weights',DEFAULT_WEIGHTS)[season]
    sample=draw()*sum(weights.values());kind=STATES[0]
    for candidate in STATES:
        sample-=weights.get(candidate,0)
        if sample<0:kind=candidate;break
    severe=kind=='thunderstorm' and minute>=row.get('severe_after',0) and draw()<region.get('severe_chance',.03)
    if severe:
        kind='tornado' if region.get('tornado_rooms') and draw()<region.get('tornado_chance',.01) else 'severe thunderstorm'
        row['severe_after']=minute+region.get('severe_cooldown_minutes',3000)
    lo,hi=region.get('duration_minutes',[60,240]);duration=lo+int(draw()*(hi-lo+1))
    if severe:duration=min(duration,60)  # No all-day tornadoes.
    warning=region.get('warning_minutes',20) if severe else 0
    intensity=(.65+.35*draw()) if kind=='tornado' else (.35+.4*draw()) if severe else (.1+.3*draw())
    wind=(120+60*draw()) if kind=='tornado' else (65+40*draw()) if severe else (25+25*draw()) if kind=='wind' else (15+30*draw()) if kind=='thunderstorm' else 5+15*draw()
    row['serial']=row.get('serial',0)+1
    front=dict(id=region['id']+':'+str(row['serial']),serial=row['serial'],region=region['id'],weather=kind,
               started=minute,warning_until=minute+warning,active_until=minute+warning+duration,
               intensity=round(intensity,3),wind_kph=round(wind,1),wind_direction=DIRECTIONS[int(draw()*8)],
               rain_mm_h=round((20+30*draw()) if severe else (8+18*draw()) if kind=='thunderstorm' else (1+8*draw()) if kind=='rain' else 0,1),
               tornado_rooms=list(region.get('tornado_rooms',[])) if kind=='tornado' else [])
    if isinstance(region.get('damage'),dict) and region['damage'].get('enabled') is True:
        front['damage_plan']=deepcopy(region['damage'])
    row['front']=front;return front


def _valid_front(f):
    return (isinstance(f,dict) and isinstance(f.get('id'),str) and isinstance(f.get('region'),str)
        and f.get('weather') in STATES+SEVERE and type(f.get('serial')) is int and 0<f['serial']<10**12
        and all(number(f.get(k),0,10**15) for k in ('started','warning_until','active_until'))
        and f['started']<=f['warning_until']<f['active_until']
        and number(f.get('intensity'),0,1) and number(f.get('wind_kph'),0,180)
        and number(f.get('rain_mm_h'),0,50) and f.get('wind_direction') in DIRECTIONS
        and isinstance(f.get('tornado_rooms'),list) and len(f['tornado_rooms'])<=8
        and all(isinstance(r,str) for r in f['tornado_rooms']))


def advance(w,minutes=1):
    if not number(minutes,0,10**15) or minutes<=0:return
    if getattr(w,'realtime',False) and not getattr(w,'tick_authorized',False):return
    config=_configuration(w)
    if not config:return
    cfg,regions,_=config;s=getattr(w,'living_state',None)
    if not isinstance(s,dict) or not number(s.get('minute'),0,10**15):return
    now=int(s['minute']);saved=s.get('regional_weather',{})
    if saved and (not isinstance(saved,dict) or saved.get('version')!=VERSION):return
    if saved and (not isinstance(saved.get('regions'),dict) or not isinstance(saved.get('log'),list)):return
    if not saved:saved={'version':VERSION,'last_minute':max(0,int(now-minutes)),'regions':{},'log':[],'skipped_minutes':0}
    last=saved.get('last_minute',now)
    if type(last) is not int or last>now or last<0:last=now
    if last==now and saved.get('regions'):return
    start=max(last,now-MAX_CATCHUP);saved['skipped_minutes']=min(10**15,(saved.get('skipped_minutes',0) if type(saved.get('skipped_minutes',0)) is int else 0)+start-last)
    for rid,region in regions.items():
        row=saved.setdefault('regions',{}).get(rid)
        if not isinstance(row,dict) or type(row.get('rng')) is not int or not 0<=row['rng']<2**64:
            row={'rng':_seed(cfg['seed'],rid),'serial':0,'severe_after':now+worldtime.MINUTES_PER_DAY}
        front=row.get('front')
        if front is not None and not _valid_front(front):continue
        if type(row.get('serial',0)) is not int or not 0<=row.get('serial',0)<10**12:continue
        if not number(row.get('severe_after',0),0,10**15):continue
        cursor=max(start,front.get('active_until',start)) if isinstance(front,dict) else start
        # A skipped offline interval does not deliver old injury or destruction.
        for _ in range(14):
            if isinstance(row.get('front'),dict) and row['front'].get('active_until',0)>now:break
            front=_new_front(cfg,region,row,cursor)
            saved['log']=(saved.setdefault('log',[])+[dict(front)])[-MAX_LOG:]
            cursor=front['active_until']
        saved['regions'][rid]=row
    saved['regions']={rid:row for rid,row in saved['regions'].items() if rid in regions}
    saved['last_minute']=now;s['regional_weather']=saved
    from engine import storm_damage
    storm_damage.advance(w,config)


def _local(w,rid):
    # Hot read path uses the index prepared by the clock hook; no config/RNG mutation.
    cfg=getattr(w,'metadata',{}).get('regional_weather',{})
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True:return None
    cached=getattr(w,'_regional_weather_config',None)
    if not cached:
        config=_configuration(w)
        if not config:return None
        cached=getattr(w,'_regional_weather_config')
    _,regions,byroom=cached[1];region=regions.get(byroom.get(rid))
    if not region:return None
    saved=getattr(w,'living_state',{}).get('regional_weather',{})
    if not isinstance(saved,dict) or saved.get('version')!=VERSION or not isinstance(saved.get('regions'),dict):return None
    row=saved['regions'].get(region['id'],{})
    if not isinstance(row,dict):return None
    front=row.get('front');now=getattr(w,'living_state',{}).get('minute',0)
    if not _valid_front(front) or not front['started']<=now<front['active_until']:return None
    return region,front


def overlay(w,rid,base,minute=None):
    local=_local(w,rid)
    if not local:return base
    region,front=local;now=getattr(w,'living_state',{}).get('minute',0) if minute is None else minute
    if not front['started']<=now<front['active_until']:return base
    result=dict(base);kind=front['weather'];warning=now<front['warning_until']
    if kind=='tornado' and rid not in front['tornado_rooms']:kind='severe thunderstorm'
    if warning:kind='thunderstorm'
    if kind=='rain' and base['temperature_c']<=0:kind='snow'
    sheltered=indoor(getattr(w,'room_details',{}).get(rid,{}))
    frozen=front['rain_mm_h']>0 and base['temperature_c']<=0
    precipitation='none' if sheltered or front['rain_mm_h']<=0 else 'snow' if frozen else 'rain'
    result.update(precipitation=precipitation,weather='sheltered' if sheltered else kind,weather_region=region['name'],weather_front_id=front['id'],
        wind_kph=0 if sheltered else min(front['wind_kph'],100 if kind!='tornado' else 180),wind_direction=front['wind_direction'],
        weather_intensity=0 if sheltered else min(front['intensity'],.75) if front['weather']=='tornado' and kind!='tornado' else front['intensity'],rain_mm_h=0 if sheltered or frozen else front['rain_mm_h'],
        weather_warning=(('Severe weather approaching outside. Remain sheltered.' if sheltered else 'Severe weather approaching. Seek a marked public shelter.') if warning else ''),
        weather_active_until=front['active_until'],weather_phase='warning' if warning else 'active')
    if sheltered:result.update(temperature_c=max(10,base['temperature_c']),travel_minutes=1)
    else:result['travel_minutes']=1+int(base.get('terrain') in ('mountain','valley','desert'))+int(kind in ('snow','severe thunderstorm','tornado'))
    return result


def rainfall(w,region_id,minute):
    """Pure catchment input for an explicitly linked heavy-rain geological basin."""
    cfg=getattr(w,'metadata',{}).get('regional_weather',{})
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True:return None
    saved=getattr(w,'living_state',{}).get('regional_weather',{})
    if not isinstance(saved,dict) or saved.get('version')!=VERSION or not isinstance(saved.get('regions'),dict):return None
    row=saved['regions'].get(region_id,{})
    if not isinstance(row,dict):return None
    front=row.get('front')
    if not _valid_front(front) or not front['warning_until']<=minute<front['active_until']:return None
    if front.get('rain_mm_h',0)<10:return None
    cached=getattr(w,'_regional_weather_config',None)
    config=cached[1] if cached else _configuration(w)
    if not config or region_id not in config[1]:return None
    from engine import climate
    # Rain must be liquid somewhere in the explicitly authored catchment region.
    region=config[1][region_id]
    outside=next((rid for rid in region['rooms'] if not indoor(w.room_details.get(rid,{}))),None)
    if outside is None or climate.conditions(w,outside,minute=minute)['temperature_c']<=0:return None
    return dict(id=front['id'],rain_mm_h=front['rain_mm_h'],intensity=front['intensity'])


def _refuge_safe(w,rid):
    from engine import livelihoods,geology_impacts,geology_events
    row=getattr(w,'room_details',{}).get(rid,{})
    if row.get('weather_shelter') is not True or not indoor(row):return False
    if row.get('land_uses') or row.get('property_plot') or row.get('land_use') in ('house','business'):return False
    if not livelihoods.room_open(w,rid) or geology_impacts.room_unusable(w,rid):return False
    if any(e.get('type') in ('flood','tsunami') for e in geology_events.room_effects(w,rid)):return False
    if row.get('weather_shelter_kind')=='cellar':
        climate=row.get('climate',{})
        if climate.get('coastal') or climate.get('terrain') in ('wetland','ocean','coast'):return False
        # An explicitly authored flood catchment is known unsafe for a cellar;
        # never infer safe subterranean refuge from a place name.
        geo=getattr(w,'metadata',{}).get('geology',{})
        if isinstance(geo,dict):
            if any(rid in b.get('rooms',[]) for b in geo.get('basins',[]) if isinstance(b,dict)):return False
            if any(rid in f.get('tsunami',{}).get('coastal_rooms',[]) for f in geo.get('faults',[]) if isinstance(f,dict) and isinstance(f.get('tsunami',{}),dict)):return False
    return True


def _shelter_step(w,actor,region,front=None):
    """Bounded live BFS; preference may add <=3 safe steps during a warning only."""
    from engine import frontiers,livelihoods,geology_impacts
    allowed=set(region['rooms']);destinations=set(region.get('shelters',[]))
    pending=deque([(actor.location,None,0)]);seen={actor.location};choices=[]
    while pending:
        rid,first,depth=pending.popleft()
        if rid in destinations and _refuge_safe(w,rid):choices.append((depth,rid,first or rid))
        if depth>=MAX_ROUTE:continue
        for di,dest in w.rooms[rid].exits.items():
            if dest not in allowed or dest in seen or frontiers.blocked(w,rid,di,actor):continue
            group=w.rooms[dest].group
            if group and frontiers.relation(w.groups.get(group),actor.group_id)=='hostile':continue
            target=getattr(w,'room_details',{}).get(dest,{})
            if indoor(target) and dest not in destinations:continue
            if target.get('land_uses') or target.get('property_plot') or target.get('land_use') in ('house','business'):continue
            if (indoor(target) and not livelihoods.room_open(w,dest)) or geology_impacts.room_unusable(w,dest):continue
            if dest in destinations and not _refuge_safe(w,dest):continue
            seen.add(dest);pending.append((dest,first or dest,depth+1))
    if not choices:return None
    definition=getattr(w,'npcs',{}).get(actor.source_def,{})
    preference=definition.get('weather_refuge_preference','auto')
    if preference not in ('auto','nearest','reinforced','cellar'):preference='auto'
    if preference=='auto':preference='cellar' if front and front.get('weather')=='tornado' else 'reinforced'
    detour=definition.get('weather_refuge_detour',2)
    if type(detour) is not int or not 0<=detour<=3:detour=2
    nearest=min(x[0] for x in choices);now=getattr(w,'living_state',{}).get('minute',0)
    warning_left=max(0,(front or {}).get('warning_until',now)-now)
    eligible=[x for x in choices if x[0]==nearest or (preference!='nearest' and x[0]<=nearest+detour and x[0]+2<=warning_left)]
    def rank(choice):
        depth,rid,_=choice;kind=w.room_details.get(rid,{}).get('weather_shelter_kind','public_hall')
        order=(0 if kind==preference else 1 if kind in ('cellar','reinforced') else 2) if preference!='nearest' else 0
        return order,depth,rid
    return min(eligible,key=rank)[2]


def actor_step(w,actor,minutes=1):
    """Called within the existing actor loop. True means NPC shelter routine owns this step."""
    if not actor.alive or actor.location not in w.rooms:return False
    local=_local(w,actor.location)
    if not local:
        actor.progress.pop('weather_refuge',None);return False
    region,front=local;now=w.living_state['minute'];severe=front['weather'] in SEVERE
    if not severe:
        actor.progress.pop('weather_refuge',None);return False
    row=getattr(w,'room_details',{}).get(actor.location,{})
    sheltered=indoor(row)
    # One contact roll per front, saved on each actor. Reentry never rerolls.
    mark=actor.progress.setdefault('weather_exposure',{'fronts':[],'budget':[]})
    if not isinstance(mark,dict) or not isinstance(mark.get('fronts'),list) or not isinstance(mark.get('budget'),list):return False
    mark['fronts']=mark.get('fronts',[])[-64:];mark['budget']=[r for r in mark.get('budget',[]) if isinstance(r,list) and len(r)==2 and number(r[0],0,now) and r[0]>now-worldtime.MINUTES_PER_DAY and number(r[1],0,actor.max_hp)]
    if not sheltered and now>=front['warning_until'] and front['id'] not in mark['fronts']:
        mark['fronts'].append(front['id'])
        exposure=0 if sheltered else region.get('exposure',{}).get(actor.location,1)
        in_tornado=front['weather']=='tornado' and actor.location in front['tornado_rooms']
        strength=front['intensity'] if front['weather']!='tornado' or in_tornado else min(front['intensity'],.75)
        risk=.08*strength*exposure
        if in_tornado:risk*=1.5
        if region.get('consequences',True) and _roll(w.metadata['regional_weather']['seed'],front['id'],actor.id,'injury')<risk:
            damage=min(math.floor(actor.max_hp*.12*strength*exposure),max(0,math.floor(actor.max_hp*.2)-sum(r[1] for r in mark['budget'])))
            if damage>0:
                from engine import mortality
                actual=mortality.environmental_damage(w,actor,damage,'severe weather',front['id'])
                mark['budget'].append([now,actual])
        if actor.is_player:w.__dict__.setdefault('dirty_players',set()).add(actor.id)
    if actor.is_player or not actor.alive:return False
    from engine import relationships,life_stages
    profile=relationships.profile(w,actor)
    if not profile.get('sentient'):return False
    if sheltered and (row.get('weather_shelter') is not True or _refuge_safe(w,actor.location)):
        actor.activity='sheltering from severe weather';actor.progress['weather_refuge']=front['id'];return True
    if not life_stages.is_adult(profile,getattr(w,'species',{}).get(profile.get('species'),{}),now):
        actor.activity='waiting for a guardian during severe weather'
        return True
    step=_shelter_step(w,actor,region,front)
    if step and step!=actor.location:
        from engine import frontiers
        origin=actor.location
        direction=next((d for d,r in w.rooms[origin].exits.items() if r==step),None)
        dependents=[]
        for child in w.entities_in_room(origin):
            if child.is_player or actor.id not in child.progress.get('population',{}).get('guardian_ids',[]):continue
            cp=relationships.profile(w,child)
            if life_stages.is_adult(cp,getattr(w,'species',{}).get(cp.get('species'),{}),now):continue
            if not frontiers.blocked(w,origin,direction,child):dependents.append(child)
        from engine import sleep_movement
        if sleep_movement.asleep(w,actor):sleep_movement.wake(w,actor,"severe weather woke you")
        w.move_entity(actor.id,step)
        for child in dependents:
            if sleep_movement.asleep(w,child):sleep_movement.wake(w,child,"your guardian woke you for shelter")
            w.move_entity(child.id,step);child.activity='accompanying guardian to weather shelter';child.progress['weather_refuge']=front['id']
        actor.activity='seeking public weather shelter';actor.progress['weather_refuge']=front['id'];return True
    return False
