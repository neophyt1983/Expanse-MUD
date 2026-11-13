"""Public surface surveys and the territorial history of governments on that survey."""
from collections import Counter,deque
from hashlib import sha256
from engine import worldtime

KEY='territorial_history'
PALETTE=['#c88463','#9583bc','#d5ad64','#66a99b','#b86e77','#89acc4','#98b980','#b799c5']


def cell(lon,lat):
    x=int(((lon+180)%360)//7.5)
    y=min(23,max(0,int((90-lat)//7.5)))
    return f'planet_{x}_{y}'


def geography(w):
    if hasattr(w,'_public_survey'):return w._public_survey
    rows=getattr(w,'room_details',{})
    places={};neighbors={}
    # The public survey is a geographic overlay. It carries no occupants,
    # urban interiors, hidden exits, resources, or player discoveries.
    for y in range(24):
        for x in range(48):
            rid=f'planet_{x}_{y}';r=rows.get(rid,{})
            if not r.get('planet',{}).get('cell') or r.get('map_visibility')=='hidden':continue
            kind=r.get('climate',{}).get('terrain') or r.get('environment','unknown')
            places[rid]=dict(id=rid,name=r['name'],planet=r['planet'],terrain=kind,publicChart=True,
                             elevation_m=r.get('climate',{}).get('elevation_m',0))
    for rid,r in places.items():
        if r['terrain']=='ocean':continue
        neighbors[rid]=tuple(t for di,t in w.rooms[rid].exits.items()
                             if di in ('north','south','east','west') and t in places and places[t]['terrain']!='ocean')
    w._public_survey=(places,neighbors)
    return w._public_survey


def state(w):
    places,land=geography(w)
    if not land:return None
    data=w.living_state.get(KEY)
    if data:return data
    owners={};countries={};front=deque()
    for gid,group in w.groups.items():
        room=getattr(w,'room_details',{}).get(group.get('start_room'),{})
        pos=room.get('planet')
        if not pos:continue
        seat=cell(pos['lon'],pos['lat'])
        if seat not in land or seat in owners:continue
        countries[gid]=dict(name=group['name'],color=PALETTE[len(countries)%len(PALETTE)],seat=seat)
        owners[seat]=gid;front.append((seat,gid,0))
    while front:
        rid,gid,steps=front.popleft()
        if steps>=2:continue
        for other in land[rid]:
            if other not in owners:
                owners[other]=gid;front.append((other,gid,steps+1))
    turn=w.living_state['minute']//interval(w)
    data=dict(countries=countries,owners=owners,events=[],turn=turn)
    w.living_state[KEY]=data
    return data


def interval(w):
    v=w.metadata.get('political_turn_minutes',375)
    return v if type(v) is int and v>0 else 375


def change(w,s,rid,new,minute,reason):
    old=s['owners'].get(rid)
    if old==new:return
    if new:s['owners'][rid]=new
    else:s['owners'].pop(rid,None)
    place=geography(w)[0][rid]['name']
    if reason=='charter':text=s['countries'][new]['name']+' received an independent charter at '+place+'.'
    elif not new:text=s['countries'][old]['name']+' withdrew from '+place+'.'
    elif old:text=place+' changed allegiance from '+s['countries'][old]['name']+' to '+s['countries'][new]['name']+'.'
    else:text=s['countries'][new]['name']+' extended its jurisdiction to '+place+'.'
    if old and old not in s['owners'].values():text+=' '+s['countries'][old]['name']+' lost its last territory and dissolved.'
    s['events'].append(dict(minute=minute,cell=rid,old=old,new=new,text=text))


def advance(w):
    if w.metadata.get('political_turn_minutes')==0:return
    s=state(w)
    if not s or not s['countries']:return
    tick=w.living_state['minute']//interval(w)
    if tick<=s['turn']:return
    places,land=geography(w);owners=s['owners']
    for n in range(s['turn']+1,tick+1):
        if not owners:break
        stamp=n*interval(w);border=[];vacant=[];fringe=[]
        for a,g in owners.items():
            near=land.get(a,())
            allies=sum(owners.get(b)==g for b in near)
            if s['countries'][g]['seat']!=a and allies<=2:fringe.append((a,g))
            for b in near:
                neighbor=owners.get(b)
                if not neighbor:vacant.append((b,g))
                elif neighbor!=g:border.append((a,neighbor))
        salt=str(w.metadata.get('name',''))+'|'+str(n)
        def choose(seq):
            return min(seq,key=lambda pair:sha256((salt+'|'+pair[0]+'|'+pair[1]).encode()).digest())
        if n%11==0 and fringe:
            rid,parent=choose(fringe);gid='charter_'+str(n)
            region=places[rid]['name'].split(' (')[0]
            ordinal=sum(x.get('region')==region for x in s['countries'].values())+1
            name=region+' Free Council'+(' '+str(ordinal) if ordinal>1 else '')
            s['countries'][gid]=dict(name=name,region=region,color=f'hsl({(n*137)%360} 45% 61%)',seat=rid)
            change(w,s,rid,gid,stamp,'charter')
        elif n%3==0 and border:
            # A territory with few supporting neighbours can cede to its strongest neighbour.
            margin=lambda c:sum(owners.get(x)==c[1] for x in land[c[0]])-sum(owners.get(x)==owners[c[0]] for x in land[c[0]])
            best=max(map(margin,border))
            if best>=0:
                rid,gid=choose([c for c in border if margin(c)==best]);change(w,s,rid,gid,stamp,'cession')
        elif n%7==0 and fringe:
            rid,_=choose(fringe);change(w,s,rid,None,stamp,'withdrawal')
        elif vacant:
            rid,gid=choose(vacant);change(w,s,rid,gid,stamp,'claim')
    s['turn']=tick


def publication(w,revision=None,include_surface=False):
    from engine import living
    living.state(w)
    places,_=geography(w);s=state(w)
    result={'type':'public_chart','revision':len(s['events']) if s else 0}
    if include_surface:result['surface']=list(places.values())
    if s and (include_surface or revision!=result['revision']):
        result.update(countries=s['countries'],owners=s['owners'],events=s['events'][-32:])
    return result


def weather_chart(world, last):
    from engine import climate,living
    minute=living.state(world)['minute']
    if last==minute:return {}
    cache=getattr(world,'_surface_weather',None)
    if not cache or cache[0]!=minute:
        rows={}
        for rid in geography(world)[0]:
            current=climate.conditions(world,rid,minute)
            rows[rid]={k:current[k] for k in ('weather','wind_kph','wind_direction','temperature_c','weather_warning') if k in current}
        cache=(minute,rows);world._surface_weather=cache
    return {'weather_minute':minute,'sky':cache[1]}
