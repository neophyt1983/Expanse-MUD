"""Finite occupational demand, opening hours, supply requests and off-duty life."""
from engine import living, society, relationships, needs_market, life_stages
DAY=1500
WAKE_MINUTES=30
POPULATION_WAKE_START=420
POPULATION_WAKE_END=1260

def enabled(w):return bool(w.metadata.get('daily_life'))
def definition(w,n):
    definition = w.npcs.get(n.source_def,{})
    member = n.progress.get('population', {})
    if member.get('born_resident') and member.get('education', {}).get('phase') == 'adult':
        return {**definition, **member.get('vocation', {})}
    return definition
def applies(w,n):return enabled(w) and not n.is_player and n.alive and relationships.sentient(w,n)
def hours(w,n):
    c=definition(w,n).get('work_hours',{})
    return int(c.get('start',420))%DAY,max(0,min(750,int(c.get('duration',600))))
def work_eligible(w,n):
    p=relationships.profile(w,n)
    return not p['sentient'] or life_stages.can_work(p,getattr(w,'species',{}).get(p['species']),living.state(w)['minute'])

def on_shift(w,n):
    if n.progress.get('retired'):return False
    p=relationships.profile(w,n)
    now=living.state(w)['minute']
    if p['sentient'] and not life_stages.can_work(p,getattr(w,'species',{}).get(p['species']),now):return False
    if not enabled(w):return True
    if n.is_player or not n.alive or not p['sentient']:return False
    start,duration=hours(w,n)
    return (now-start)%DAY<duration

def population_member(n):
    return not n.is_player and n.alive and bool(n.progress.get('population'))

def scheduled_awake(w,n):
    # Enrolled residents have an authored waking day, independent of whether
    # they have a job or whether the optional occupational economy is enabled.
    if population_member(n):
        now=living.state(w)['minute']
        if POPULATION_WAKE_START<=now%DAY<POPULATION_WAKE_END:return True
        # A Creator-authored night shift is real waking time, not an inferred
        # job for every resident. Home supervision still takes precedence.
        cfg=definition(w,n)
        if (n.progress['population'].get('care_role')=='home_caregiver' or
                not cfg.get('occupation') or cfg.get('work_room') not in w.rooms):return False
        start,duration=hours(w,n)
        if not duration or (now-start)%DAY>=duration:return False
        p=relationships.profile(w,n)
        return life_stages.can_work(p,getattr(w,'species',{}).get(p['species']),now)
    if not applies(w,n):return True
    start,duration=hours(w,n)
    return (living.state(w)['minute']-start)%DAY<min(DAY,duration+300)

def roused(w,n):
    return (population_member(n) or applies(w,n)) and living.state(w)['minute']<n.progress.get('awakened_until',-1)

def awake(w,n):return scheduled_awake(w,n) or roused(w,n)

def wake_available(w,viewer=None):
    if enabled(w):return True
    # Do not expose another world's residents or change legacy availability.
    # Enrolled sleepers can still be deliberately woken without daily_life.
    return bool(viewer and viewer.location in w.rooms and any(
        population_member(n) and relationships.profile(w,n)['sentient']
        for n in w.entities_in_room(viewer.location)))

def room_open(w,rid):
    from engine import geology_impacts
    if geology_impacts.room_unusable(w,rid):return False
    if not enabled(w):return True
    c=w.room_details.get(rid,{}).get('opening_hours')
    return not c or (living.state(w)['minute']-c.get('start',420))%DAY<c.get('duration',600)

def service_open(w,n):
    if not room_open(w,n.location):return False
    p=relationships.profile(w,n);now=living.state(w)['minute']
    if not p['sentient']:return True
    if not life_stages.can_work(p,getattr(w,'species',{}).get(p['species']),now):return False
    if not enabled(w) or n.is_player or not n.alive:return True
    start,duration=hours(w,n)
    return (now-start)%DAY<duration
def require_service(w,n):
    if not service_open(w,n):raise ValueError(n.name+' is off duty or the business is closed. '+hours_text(w,n))
def hours_text(w,n):
    start,duration=hours(w,n);end=(start+duration)%DAY
    return f'Work: {start//60:02d}:{start%60:02d}–{end//60:02d}:{end%60:02d} (25-hour day).'

def workplace(w,n):
    from engine import settlements
    unit=settlements.state(w)['units'].get(n.progress.get('job_property')) if settlements.enabled(w) else None
    if unit and n.id in (unit.get('owner'),unit.get('tenant')):return unit['room']
    return definition(w,n).get('work_room') or next((s['room'] for s in definition(w,n).get('schedule',[]) if any(k in s.get('activity','') for k in ('work','teach','guard','hunt','farm'))),n.location)

def job_needs(w,n):
    if not applies(w,n):return {}
    rid=workplace(w,n);cfg=w.room_details.get(rid,{}).get('workshop',{});stock=society.shop(w,rid)[1]['stock'] if cfg else {}
    desired={}
    if on_shift(w,n):
        for recid in cfg.get('recipes',[]):
            for iid,count in getattr(w,'recipes',{}).get(recid,{}).get('ingredients',{}).items():desired[iid]=max(desired.get(iid,0),count*2)
        if cfg.get('repair'):desired['sx_repair_kit']=2
    for iid,count in definition(w,n).get('purchase_targets',{}).items():desired[iid]=max(desired.get(iid,0),count)
    return {i:max(0,int(q)-n.inventory.count(i)-stock.get(i,0)) for i,q in desired.items() if i in w.items and q>n.inventory.count(i)+stock.get(i,0)}

def reasons(w,n):
    if not applies(w,n) or not awake(w,n):return {}
    from engine import social
    cfg=social.prefs(w,n,include_needs=False);out={}
    for iid,item in (w.items.items() if cfg['wanted_items'] or cfg['wanted_types'] else ()):
        if iid in cfg['disliked_items']:continue
        if (iid in cfg['wanted_items'] or item.get('type') in cfg['wanted_types']) and n.inventory.count(iid)<cfg['gift_limit']:out[iid]='personal interest'
    for iid in needs_market.wanted_items(w,n):
        if iid not in cfg['disliked_items']:out[iid]='current '+needs_market.priority(w,n)+' need'
    job=job_needs(w,n)
    for iid,q in job.items():
        if iid not in cfg['disliked_items']:out[iid]=f'work supplies: {q} needed'
    for iid,item in (w.items.items() if job else ()):
        recover={i:q for i,q in item.get('salvage',{}).items() if i in job and q>0}
        if recover and iid not in cfg['disliked_items']:out.setdefault(iid,'recover '+', '.join(w.items[i]['name'] for i in recover))
    return dict(sorted(out.items(),key=lambda row:0 if row[1].startswith(('work','recover')) else 1))

def receive(w,n,iid):
    if not applies(w,n):return
    # Items without need effects cannot relieve needs; avoid expensive
    # NPC-profile/threshold evaluation for every tool and ingredient.
    if w.items.get(iid,{}).get('need_effects'):
        needs_market.use(w,n,iid)
    rid=workplace(w,n)
    if not on_shift(w,n) or n.location!=rid or not room_open(w,rid) or not w.room_details.get(rid,{}).get('workshop'):return
    needed=job_needs(w,n);cfg,stock=society.shop(w,rid)
    ingredients={i for r in cfg.get('recipes',[]) for i in getattr(w,'recipes',{}).get(r,{}).get('ingredients',{})}
    if iid not in n.inventory or iid in n.equipped.values():return
    if iid in ingredients or iid=='sx_repair_kit' and cfg.get('repair'):
        n.inventory.remove(iid);stock['stock'][iid]=stock['stock'].get(iid,0)+1;return
    outputs=w.items.get(iid,{}).get('salvage',{})
    if any(i in needed for i in outputs):
        n.inventory.remove(iid)
        for i,q in outputs.items():stock['stock'][i]=stock['stock'].get(i,0)+q

def summary(w,n):
    if not applies(w,n):return ''
    demand=reasons(w,n);names=[w.items[i]['name']+' ('+why+')' for i,why in list(demand.items())[:16]]
    return definition(w,n).get('occupation','Resident')+'. '+hours_text(w,n)+' '+('On duty. ' if on_shift(w,n) else 'Off duty. ')+('Looking for: '+ '; '.join(names) if names else 'No purchases needed now.')

def move_towards(w,n,target):
    if target not in w.rooms:return False
    if n.location==target:return True
    from engine import frontiers
    from collections import deque
    cache=getattr(w,'_commute_routes',None)
    if cache is None:cache={};w._commute_routes=cache
    entry=cache.get(n.id);steps=entry[1] if entry and entry[0]==target else None
    if steps:
        origin,direction,destination=steps[0]
        if origin!=n.location or w.rooms[origin].exits.get(direction)!=destination or frontiers.blocked(w,origin,direction,n):steps=None
    if not steps:
        budget=getattr(w,'commute_budget',None)
        if budget is not None:
            # FIFO across ticks: the first scheduled residents cannot monopolize searches.
            from collections import OrderedDict
            pending=getattr(w,'_pending_commutes',None)
            if pending is None:pending=w._pending_commutes=OrderedDict()
            minute=getattr(w,'living_state',{}).get('minute',0)
            if minute!=getattr(w,'_commute_minute',None):
                w._commute_minute=minute
                w._route_slots=set()
                for _ in range(min(budget,len(pending))):
                    who,_=pending.popitem(last=False);w._route_slots.add(who)
                w._new_route_slots=budget-len(w._route_slots)
            if n.id in w._route_slots:w._route_slots.remove(n.id)
            elif w._new_route_slots>0:w._new_route_slots-=1
            else:
                pending[n.id]=None
                return False
            pending.pop(n.id,None)
        path=frontiers.path(w,n.location,target,n)
        if not path:return False
        steps=deque(path);cache[n.id]=(target,steps)
    _,_,destination=steps.popleft();w.move_entity(n.id,destination)
    if not steps:cache.pop(n.id,None)
    return True


def locations(w):
    stamp=int(living.state(w)['minute']//30)
    cached=getattr(w,'_livelihood_locations',None)
    if cached and cached[0]==stamp:return cached[1]
    index={}
    for rid,rd in w.room_details.items():
        group=index.setdefault(w.rooms[rid].group,dict(shops=[],resources={}))
        if rd.get('workshop'):group['shops'].append(rid)
        for resource_id in rd.get('resources',[]):
            from engine import hand_resources
            if hand_resources.configured(getattr(w,'resources',{}).get(resource_id,{})):continue
            for iid in getattr(w,'resources',{}).get(resource_id,{}).get('yields',{}):group['resources'].setdefault(iid,[]).append((rid,resource_id))
    w._livelihood_locations=(stamp,index)
    return index

def supplies(w,n):
    """Ask once per cooldown; actively seek finite supplies between requests."""
    if not applies(w,n) or not awake(w,n):return False
    now=living.state(w)['minute'];cfg=definition(w,n);state=n.progress.setdefault('supply_search',{})
    # Reconsider candidates at a bounded cadence, independent of network refreshes.
    target=state.get('target')
    if target and target!=n.location and now<state.get('next_search',-1) and (on_shift(w,n) or not state.get('work_search')):
        move_towards(w,n,target);n.activity='seeking supplies';return True
    arrived=bool(target and target==n.location)
    state.pop('target',None)
    if not arrived and now<state.get('next_search',-1):return False
    state['next_search']=now+15
    working=on_shift(w,n)
    job=job_needs(w,n) if working else {}
    work=workplace(w,n) if working else None
    wants=dict(job)
    for iid in needs_market.wanted_items(w,n):wants.setdefault(iid,1)
    if not wants:return False
    iid=next(iter(wants));price=max(1,society.price(w,iid,False))
    if now>=state.get('next_request',-1) and n.gold>=price:
        players=[p for p in w.entities_in_room(n.location) if p.is_player and p.alive and society.friendliness(w,p,n)>50]
        if players:
            text=n.name+' is looking to buy '+w.items[iid]['name']+'. Open Talk to see current offers; they will also look elsewhere.'
            w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(n.location,text,None)])[-500:]
            state['next_request']=now+max(60,int(cfg.get('request_cooldown_minutes',180)))
    regional=locations(w).get(n.group_id,{'shops':[],'resources':{}})
    for rid in regional['shops']:
        # Existing workplace stock already counts toward occupational demand.
        # Do not pay to withdraw it and immediately put it back.
        if working and rid==work and iid in job:continue
        if not room_open(w,rid):continue
        _,stock=society.shop(w,rid)
        if stock['stock'].get(iid,0)<1:continue
        cost=society.price(w,iid,rid=rid)
        if n.gold<cost:continue
        if rid==n.location:
            n.gold-=cost;stock['gold']+=cost;stock['stock'][iid]-=1;n.inventory.append(iid);receive(w,n,iid)
        else:
            state.update(target=rid,work_search=working);move_towards(w,n,rid)
        n.activity='seeking '+w.items[iid]['name'];return True
    # No vendor stock: travel to authored resource locations; harvest while on duty.
    if working:
        for rid,resource_id in regional['resources'].get(iid,[]):
            r=getattr(w,'resources',{}).get(resource_id,{})
            from engine import hand_resources
            if hand_resources.configured(r):continue
            from engine import ecology,resource_nodes,geology_impacts
            if not room_open(w,rid) or geology_impacts.resource_blocked(w,rid,resource_id):continue
            if not ecology.in_season(w,r,rid) or not ecology.available(w,rid,r):continue
            configured=resource_nodes.managed(r,w.items)
            if configured:
                if not room_open(w,rid) or (r.get('tool') and r['tool'] not in n.inventory):continue
                if not resource_nodes.available(w,rid,r):continue
            if rid!=n.location:
                state.update(target=rid,work_search=True);move_towards(w,n,rid);n.activity='gathering supplies';return True
            if configured:
                if resource_nodes.harvest(w,rid,r,n):
                    for item,count in r['yields'].items():n.inventory.extend([item]*count)
                    n.activity='harvesting';return True
                continue
            key=rid+':'+resource_id;times=living.state(w).setdefault('shared_resource_times',{}) if r.get('shared_renewal') else society.economy(w).setdefault('harvest_times',{})
            if now-times.get(key,-100000)>=r.get('renewal_minutes',60):
                times[key]=now
                for item,count in r['yields'].items():n.inventory.extend([item]*count)
                n.activity='harvesting';return True
    return False

def public_wage(w,n):
    if not work_eligible(w,n):return
    from engine import settlements
    now=living.state(w)['minute']
    if settlements.enabled(w) and now>=n.progress.get('next_public_wage',0):
        n.progress['next_public_wage']=now+30
        treasury=settlements.state(w)['treasuries']
        if treasury.get(n.group_id,0)>0:treasury[n.group_id]-=1;n.gold+=1

def work_activity(w,n):
    if not work_eligible(w,n):return False
    role=definition(w,n).get('occupation','');now=living.state(w)['minute']
    if role in ('driver','guard') and definition(w,n).get('patrol_route'):
        route=[r for r in definition(w,n)['patrol_route'] if r in w.rooms]
        if route:
            idx=n.progress.get('driving_stop',0)%len(route)
            if n.location==route[idx]:idx=(idx+1)%len(route)
            n.progress['driving_stop']=idx;move_towards(w,n,route[idx]);n.activity='driving' if role=='driver' else 'patrolling';public_wage(w,n);return True
    if role=='guard':move_towards(w,n,workplace(w,n));n.activity='guarding';public_wage(w,n);return True
    if role=='hunter':
        target=workplace(w,n);move_towards(w,n,target);n.activity='hunting'
        if len(n.inventory)<8 and n.location==target and now>=n.progress.get('next_hunt',0) and not living.details(w,target).get('truce'):
            n.progress['next_hunt']=now+30
            from engine import wildlife,combat
            prey=next((p for p in w.entities_in_room(target) if p.id!=n.id and p.alive and not p.is_player and not p.progress.get('companion_owner') and not p.progress.get('zoo_exhibit') and not relationships.profile(w,p)['sentient'] and wildlife.species(w,p)),None)
            if prey:
                text=combat.strike(w,n,prey,counter=True)
                w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(target,text)])[-500:]
                if not prey.alive and not prey.progress.get('wildlife_drops_released'):
                    prey.progress['wildlife_drops_released']=True
                    if not prey.progress.get('combat_drops_distributed'):
                        n.inventory.extend(i for i in definition(w,prey).get('drops',[]) if i in w.items)
        return True
    if role not in ('entertainer','teacher'):return False
    festival = None
    if role == 'entertainer':
        from engine import singing
        festival = singing.festival_for(w,n)
    target = festival['room'] if festival else workplace(w,n)
    if not room_open(w,target):return False
    move_towards(w,n,target)
    n.activity = ('attending ' + festival['name'] if festival and n.location == target
                  else 'travelling to ' + festival['name'] if festival else
                  'performing' if role == 'entertainer' else 'teaching')
    if role=='entertainer' and n.location==target:
        singing.npc_step(w,n,'festival' if festival else 'performance')
    if n.location==target and now>=n.progress.get('next_public_service',0):
        n.progress['next_public_service']=now+30
        attendees=[p for p in w.entities_in_room(target) if p.id!=n.id and p.alive and relationships.profile(w,p)['sentient'] and society.friendliness(w,p,n)>50]
        if attendees:
            from engine import gazette
            action = 'gave a performance' if role == 'entertainer' else 'taught a class'
            section = 'Culture' if role == 'entertainer' else 'Education'
            headline = f'{n.name} {action} at {w.rooms[target].name} with {len(attendees)} in attendance.'
            gazette.record(w, target, section, headline, key=f'{role}:{n.id}:{target}', once=True)
        for person in attendees:needs_market.relieve(person,'fulfillment',10);needs_market.relieve(person,'belonging',5)
        from engine import settlements
        if attendees and settlements.enabled(w):
            treasury=settlements.state(w)['treasuries']
            if treasury.get(n.group_id,0)>0:treasury[n.group_id]-=1;n.gold+=1
    return True

def routine(w,n):
    if not applies(w,n):return False
    from engine import sleep_movement
    sleep_movement.scheduled_wake(w,n)
    if sleep_movement.asleep(w,n):return True
    # A deliberate interruption does not start another shift or a shopping trip.
    # The absolute game-time deadline also survives save/load and midnight.
    if roused(w,n) and not scheduled_awake(w,n):
        n.activity='awake after being disturbed';return True
    profile=relationships.profile(w,n)
    stage=life_stages.for_entity(w,n,profile)
    if not stage['can_work']:
        start,duration=hours(w,n)
        # A work room is not a school. Only explicitly authored school rooms
        # receive students; infants and unenrolled children remain at home.
        school=definition(w,n).get('school_room')
        study=stage['in_school'] and school in w.rooms and (living.state(w)['minute']-start)%DAY<duration
        target=school if study else n.progress.get('home_room') or definition(w,n).get('home_room',n.location)
        move_towards(w,n,target)
        n.activity=('studying' if study else 'resting at home') if n.location==target else ('walking to school' if study else 'returning home')
        return True
    from engine import market_shifts
    if market_shifts.routine(w,n):return True
    if on_shift(w,n):
        for iid in list(n.inventory):receive(w,n,iid)
        if supplies(w,n):return True
        if work_activity(w,n):return True
        # Return occupational workers to the authored workplace, independent of old overlong schedules.
        if definition(w,n).get('profession')=='producer':
            target=workplace(w,n);move_towards(w,n,target);n.activity='working'
            if n.location==target:
                from engine import singing
                singing.npc_step(w,n,'work')
            return True
        return False
    # Festival guests are actual residents travelling after work, never spawned
    # crowds or instant teleports. Only authored participants take this detour.
    from engine import singing
    festival = singing.festival_for(w,n)
    if festival and awake(w,n) and room_open(w,festival['room']):
        target = festival['room']
        move_towards(w,n,target)
        n.activity = ('attending ' + festival['name'] if n.location == target
                      else 'travelling to ' + festival['name'])
        if n.location == target:
            singing.npc_step(w,n,'festival')
        return True
    if awake(w,n):
        from engine import settlements
        if settlements.housing_step(w,n):return True
        if supplies(w,n) or needs_market.act(w,n,1):return True
    start,duration=hours(w,n);elapsed=(living.state(w)['minute']-start)%DAY
    home=n.progress.get('home_room') or definition(w,n).get('home_room') or next((s['room'] for s in definition(w,n).get('schedule',[]) if 'sleep' in s.get('activity','')),n.location)
    if elapsed<duration+150:
        venue=definition(w,n).get('leisure_room')
        if venue and room_open(w,venue):
            move_towards(w,n,venue)
            n.activity='enjoying entertainment' if n.location==venue else 'travelling to entertainment'
            if n.location==venue:
                needs_market.relieve(n,'fulfillment',2)
                from engine import singing
                singing.npc_step(w,n,'leisure')
            return True
    move_towards(w,n,home)
    if n.location!=home:n.activity='returning home';return True
    if elapsed<duration+300:
        nearby=w.entities_in_room(n.location)
        pet=next((p for p in nearby if p.progress.get('companion_owner')==n.id),None)
        family=any(n.id in b.get('participants',[]) and any(k in b.get('kinds',[]) for k in ('married','parent')) and any(p.id in b['participants'] and p.id!=n.id for p in nearby) for b in relationships.state(w)['bonds'].values())
        n.activity='playing with pet' if pet else 'spending time with family' if family else 'relaxing at home'
        needs_market.relieve(n,'belonging',2)
    else:n.activity='sleeping'
    return True

def validate(data):
    issues=[];items={i['id'] for i in data.get('item',[])};rooms={r['id'] for r in data.get('room',[])}
    for kind,field in [('npc','work_hours'),('room','opening_hours')]:
        for row in data.get(kind,[]):
            c=row.get(field)
            if not c:continue
            limit=750 if kind=='npc' else DAY
            if not isinstance(c,dict) or type(c.get('start')) is not int or not 0<=c['start']<DAY or type(c.get('duration')) is not int or not 0<=c['duration']<=limit:issues.append(row['id']+': invalid '+field)
    for n in data.get('npc',[]):
        for field in ('work_room','home_room','leisure_room'):
            if n.get(field) and n[field] not in rooms:issues.append(n['id']+': unknown '+field)
        if type(n.get('request_cooldown_minutes',180)) is not int or n.get('request_cooldown_minutes',180)<60:issues.append(n['id']+': request cooldown must be at least 60 minutes')
        if any(i not in items or type(q) is not int or not 0<=q<=100 for i,q in n.get('purchase_targets',{}).items()):issues.append(n['id']+': invalid purchase targets')
    for item in data.get('item',[]):
        if any(i not in items or i==item['id'] or type(q) is not int or not 1<=q<=100 for i,q in item.get('salvage',{}).items()):issues.append(item['id']+': invalid salvage components')
    return issues
