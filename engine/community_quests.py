"""Local, funded contracts built from the loaded world's people, sites and designs."""
from collections import Counter, defaultdict, OrderedDict
from math import ceil

from engine import ecology, frontiers, gathering, geology_impacts, knowledge, life_stages
from engine import livelihoods, living, quest_progress, relationships, resource_nodes, sleep_movement, society, town_talk

LABELS = {'find':'Find a person or animal','gather':'Gather supplies','make':'Make something',
          'watch':'Watch children','herd':'Herd animals'}
PUBLIC = {'inn','tavern','market','school','recreation','guild','port'}


def ledger(w):
    book=living.state(w).setdefault('community_jobs', {'next':1,'jobs':{},'deliveries':{},'credits':{}})
    book.setdefault('recent',[])
    return book


def now(w):
    return living.state(w)['minute']


def available(w):
    return living.enabled(w) and w.metadata.get('community_requests',True)


def human(w,e):
    return e.is_player or relationships.sentient(w,e)


def child(w,e):
    return not e.is_player and human(w,e) and not life_stages.for_entity(w,e)['adult']


def animal(w,e):
    if e.is_player or human(w,e) or e.progress.get('escort_post') or e.progress.get('companion_owner'):return False
    species=relationships.profile(w,e)['species']
    return species in getattr(w,'species',{}) and not w.npcs.get(e.source_def,{}).get('expedition_role')


def board(w,r):
    d=living.details(w,r)
    return bool(set(d.get('facilities',())) & PUBLIC or d.get('quest_board') or
                any(w.items.get(i,{}).get('quest_offers') for i in w.rooms[r].items))


def meet(w,p):
    seen=p.progress.setdefault('community_contacts',{})
    for other in w.entities_in_room(p.location):
        if other.alive and other.id!=p.id:seen[other.id]=other.name
    return seen


def contacts(w,p):
    return set(meet(w,p)) | set(town_talk.contacts_for(w,p))


def catalog(w,p):
    people=sorted((w.entities[k] for k in contacts(w,p) if k in w.entities and w.entities[k].alive and k!=p.id),key=lambda x:x.name)
    k=knowledge.sync(w,p,observe=True)
    if p.is_player:
        knowledge.learn_local_recipes(w,p)
    rid=p.location
    def rows(table,ids):
        return sorted(([i,table[i]['name']] for i in ids if i in table),key=lambda pair:pair[1])
    return dict(tasks=LABELS,find=[[e.id,e.name] for e in people if human(w,e) or animal(w,e)],
                watch=[[e.id,e.name] for e in people if child(w,e)],herd=[[e.id,e.name] for e in people if animal(w,e)],
                gather=rows(w.items,k['items']),make=rows(w.recipes,k['recipes']),
                places=sorted(([r,w.rooms[r].name] for r in set(k['rooms'])|{rid} if r in w.rooms),key=lambda row:row[1]),
                nearby=[[e.id,e.name] for e in people if human(w,e) and e.location==rid],
                board=board(w,rid),room=w.rooms[rid].name)


def sites(w):
    cached=getattr(w,'_community_sites',None)
    if cached is not None:return cached
    sources=defaultdict(list);stations=defaultdict(list)
    for rid,rd in w.room_details.items():
        if rid not in w.rooms:continue
        for key in rd.get('resources',()):
            for iid,qty in w.resources.get(key,{}).get('yields',{}).items():
                if qty>0:sources[iid].append((rid,key))
        for station in rd.get('facilities',()):stations[station].append(rid)
    w._community_sites=sources,stations
    return w._community_sites


def distance(w,actor,origin,dest):
    if origin==dest:return 0
    route=frontiers.path(w,origin,dest,actor)
    return len(route) if route else None


def nearest(w,origin,rid):
    a,b=w.rooms[origin],w.rooms[rid]
    return (rid!=origin,a.group!=b.group,abs((a.map_x or 0)-(b.map_x or 0))+abs((a.map_y or 0)-(b.map_y or 0)))


def checked_subjects(w,spec):
    people=[w.entities.get(i) for i in spec['targets']]
    if not all(e and e.alive and e.location in w.rooms for e in people):raise ValueError('A requested person or animal is no longer available.')
    kind=spec['kind']
    if kind=='herd' and not all(animal(w,e) for e in people):raise ValueError('Choose available animals for herding.')
    if kind=='watch' and not all(child(w,e) for e in people):raise ValueError('Choose children for supervision.')
    if kind in ('watch','herd') and len({e.location for e in people})!=1:raise ValueError('The group must be together before this request can start.')
    return people


def plan(w,actor,spec):
    """Prove a route and a source for every step, including the return."""
    origin=actor.location
    steps=[];minutes=0;used=set()
    def step(room,action,key='',length=1):
        nonlocal origin,minutes
        route=[] if origin==room else frontiers.path(w,origin,room,actor)
        if route is None:raise ValueError('No open route to '+w.rooms[room].name+'.')
        minutes+=len(route)+length;origin=room
        steps.append(dict(room=room,action=action,key=key,length=length,route=route,route_index=0))
    def harvest(iid,qty):
        nonlocal minutes
        repeats=[]
        # Prefer ready harvests before scheduling renewable or remaining finite batches.
        candidates=sorted(sites(w)[0].get(iid,()),key=lambda x:nearest(w,origin,x[0]))
        for room,key in candidates:
            src=w.resources[key]
            if not actor.is_player and 'manual_batches' in src:continue
            if (room,key) in used or key not in resource_nodes.active_resources(w,room):continue
            if gathering.resource_state(w,actor,room,src) or distance(w,actor,origin,room) is None:continue
            used.add((room,key))
            step(room,'gather',key,max(1,src.get('gather_minutes',1)));qty-=src['yields'][iid]
            if qty<=0:return
            if 'manual_batches' in src:
                saved=living.state(w).get('manual_resources',{}).get(room+':'+key,{})
                batches=saved.get('remaining',src['manual_batches'])-1
            elif 'reserve_batches' in src:
                batches=src['reserve_batches']-resource_nodes._extracted(w,room+':'+key,src['reserve_batches'])-1
            else:batches=qty
            repeats.append((room,key,max(0,batches)))
        for room,key,batches in repeats:
            src=w.resources[key]
            for _ in range(min(batches,ceil(qty/src['yields'][iid]))):
                step(room,'gather',key,max(1,src.get('gather_minutes',1)))
                steps[-1]['renewal']=src.get('renewal_minutes',60)
                minutes+=steps[-1]['renewal'];qty-=src['yields'][iid]
                if qty<=0:return
        raise ValueError('No reachable, ready source covers the required '+w.items[iid]['name']+' with the available tools and skills.')
    kind=spec['kind'];qty=spec['qty'];key=spec['targets'][0]
    if kind=='gather':harvest(key,qty)
    elif kind=='make':
        rec=w.recipes.get(key)
        if not rec or not rec.get('outputs'):raise ValueError('That design has no usable output.')
        if not set(rec.get('required_abilities',()))<=set(actor.abilities) or any(quest_progress.status(w,actor,q)!='complete' for q in rec.get('prerequisites',())):
            raise ValueError('The worker lacks a prerequisite for this design.')
        for iid,n in rec['ingredients'].items():
            missing=qty*n-actor.inventory.count(iid)
            if missing>0:harvest(iid,missing)
        station=rec.get('station','hand')
        candidates=[origin] if station=='hand' else sorted(sites(w)[1].get(station,()),key=lambda r:nearest(w,origin,r))
        room=next((r for r in candidates if ecology.available(w,r,rec) and not geology_impacts.room_unusable(w,r) and distance(w,actor,origin,r) is not None),None)
        if room is None:raise ValueError('No reachable working station has the facilities and living animals this design needs.')
        for _ in range(qty):step(room,'make',key,max(1,rec.get('minutes',5)))
    else:
        crew=checked_subjects(w,spec)
        if actor.id in spec['targets']:raise ValueError('The worker cannot be the subject of this request.')
        step(crew[0].location,kind,key,qty if kind=='watch' else 1)
        if kind=='herd':
            dest=spec['dest']
            if dest==origin:raise ValueError('Choose a different pasture or destination.')
            if any(distance(w,e,origin,dest) is None for e in crew):raise ValueError('An animal cannot reach that destination.')
            step(dest,'arrive')
    step(spec['home'],'deliver')
    return steps,minutes


def spec_for(w,p,data):
    kind=data.get('kind')
    if not isinstance(kind,str) or kind not in LABELS:raise ValueError('Choose a task.')
    targets=data.get('targets');qty=data.get('qty',1);dest=data.get('dest')
    if not isinstance(targets,list) or not 1<=len(targets)<=8 or any(not isinstance(t,str) for t in targets) or len(set(targets))!=len(targets):
        raise ValueError('Choose one or more distinct targets.')
    if kind not in ('watch','herd') and len(targets)!=1:raise ValueError('Choose one target.')
    if type(qty)!=int or not 1<=qty<=(120 if kind=='watch' else 12):raise ValueError('Choose a valid amount or duration.')
    if kind in ('find','herd'):qty=1
    choices=catalog(w,p)
    if not set(targets)<={i for i,_ in choices[kind]}:raise ValueError('Choose a target this character knows.')
    if kind=='herd' and (not isinstance(dest,str) or dest not in dict(choices['places'])):raise ValueError('Choose a known destination.')
    names=dict(choices[kind])
    return dict(kind=kind,targets=targets,qty=qty,dest=dest if kind=='herd' else None,home=p.location,
                title=LABELS[kind]+' · '+', '.join(names[i] for i in targets))


def reward(w,spec,minutes):
    key=spec['targets'][0];kind=spec['kind'];qty=spec['qty']
    material=w.items[key].get('value',1)*qty if kind=='gather' else 0
    if kind=='make':material=sum(max(1,w.items[i].get('value',1))*n*qty for i,n in w.recipes[key]['outputs'].items())
    return max(2,2+ceil(minutes/5)+int(material)+(len(spec['targets']) if kind in ('herd','watch') else 0))


def message(w,p,text):
    if p and p.is_player:
        w.rest_notifications=getattr(w,'rest_notifications',[])+[(p.id,text)]


def note(w,j,text):
    j['note']=text
    j['history']=(j.get('history',[])+[text])[-12:]
    message(w,w.entities.get(j['issuer']),text)


def announce(w,j,text):
    """Witnessed local activity, not a global quest reveal or a newspaper feed."""
    giver=w.entities.get(j['issuer'])
    room=j['home'] if j['mode']=='board' else giver.location if giver else j['home']
    if room in w.rooms:
        excluded=j['issuer'] if giver and giver.is_player else None
        w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(room,text,excluded)])[-500:]


def offer_plan(w,p,spec,recipient=None):
    # A commissioner can hire a specialist who has equipment or skills they lack.
    candidates=[p]
    if recipient is not None:
        if not isinstance(recipient,str):raise ValueError('Choose a recipient here.')
        other=w.entities.get(recipient)
        if not other or not other.alive or other.location!=p.location or other.id==p.id or not human(w,other):
            raise ValueError('That recipient is no longer here.')
        candidates=[other]
    else:
        candidates.extend(e for e in w.entities_in_room(p.location) if e.alive and human(w,e) and e.id!=p.id and e.id not in spec['targets'])
    first_error=None
    for candidate in candidates:
        try:return plan(w,candidate,spec)
        except ValueError as exc:
            if first_error is None:first_error=exc
    raise first_error or ValueError('No eligible worker can complete this request.')


def post(w,p,spec,mode,to=None,expected_pay=None):
    if mode not in ('board','ask'):raise ValueError('Choose a noticeboard or a personal offer.')
    if mode=='board' and not board(w,p.location):raise ValueError('Post at a tavern or another local gathering place.')
    if mode=='board':to=None
    if to and (not isinstance(to,str) or not any(e.id==to and e.id!=p.id and e.alive and human(w,e) for e in w.entities_in_room(p.location))):
        raise ValueError('That recipient is no longer here.')
    book=ledger(w)
    if sum(j['issuer']==p.id for j in book['jobs'].values())>=8:raise ValueError('Finish or withdraw an existing request first.')
    steps,minutes=offer_plan(w,p,spec,to);pay=reward(w,spec,minutes)
    if expected_pay is not None and (type(expected_pay)!=int or expected_pay!=pay):raise ValueError('The route or reward changed. Check the reward again before posting.')
    if p.gold<pay:raise ValueError(f'This request needs {pay} gold. You have {p.gold}.')
    ident=str(book['next']);book['next']+=1;p.gold-=pay
    j=dict(spec,id=ident,issuer=p.id,name=p.name,pay=pay,status='open',mode=mode,to=to,worker=None,estimate=minutes,
           note='Reward deposited.',created=now(w),history=[],declined={})
    book['jobs'][ident]=j
    if to:message(w,w.entities[to],p.name+' offers '+j['title']+'. Open Local quests to respond.')
    if not p.is_player:
        announce(w,j,p.name+' '+('posts a local quest' if mode=='board' else 'asks for help')+': '+j['title']+f' ({pay} gold).')
    return j


def visible(w,p,j):
    if p.id in (j['issuer'],j['worker']):return True
    if j['mode']=='board':return p.location==j['home'] and j['status'] in ('open','active','completed')
    if j['status']!='open':return False
    giver=w.entities.get(j['issuer'])
    return giver and giver.location==p.location and (not j['to'] or j['to']==p.id)


def duties(w):
    book=ledger(w);stamp=(id(book),book.get('revision',0))
    if getattr(w,'_community_stamp',None)!=stamp:
        workers={};covers={};groups={}
        for j in book['jobs'].values():
            if j['status']!='active':continue
            workers[j['worker']]=j
            if j.get('cover'):covers[j['cover']]=j
            if j.get('bound'):
                for k in j['targets']:groups[k]=j
        w._community_duties=workers,covers,groups;w._community_stamp=stamp
    return w._community_duties


def changed(w):
    book=ledger(w);book['revision']=book.get('revision',0)+1


def busy(w,e):
    return any(e.id in (j.get('worker'),j.get('cover')) or (j.get('bound') and e.id in j['targets']) for j in ledger(w)['jobs'].values() if j['status']=='active')


def shift_overlap(w,e,minutes):
    cfg=livelihoods.definition(w,e)
    if not cfg.get('occupation') or e.progress.get('retired'):return 0
    start,duration=livelihoods.hours(w,e)
    t=now(w);end=t+minutes
    return sum(max(0,min(end,day*1500+start+duration)-max(t,day*1500+start)) for day in range(t//1500-1,end//1500+1))


def leave(w,e,j,minutes):
    lost=shift_overlap(w,e,minutes)
    if lost<=5:return '',None
    site=livelihoods.workplace(w,e);role=livelihoods.definition(w,e).get('occupation','')
    if j['pay']<max(3,ceil(lost/4)):raise ValueError(f'{e.name} declined. The reward would not cover {lost} minutes of missed work.')
    coworkers=[n for n in w.entities.values() if not n.is_player and n.alive and n.id!=e.id and w.npcs.get(n.source_def,{}).get('work_room')==site]
    # An authored reporting line or the registered proprietor takes precedence.
    cfg=livelihoods.definition(w,e);boss_id=cfg.get('employer') or cfg.get('supervisor')
    unit=living.state(w).get('settlements',{}).get('units',{}).get(e.progress.get('job_property'),{})
    boss=w.entities.get(boss_id) or w.entities.get('npc:'+str(boss_id)) or w.entities.get(unit.get('owner'))
    if not boss and boss_id:boss=next((n for n in w.entities.values() if n.source_def==boss_id and n.alive),None)
    boss=boss or next((n for n in coworkers if livelihoods.definition(w,n).get('occupation') in ('manager','foreman','owner','captain')),None)
    label=boss.name if boss and boss.id!=e.id else w.rooms[site].name+' duty office'
    policy=livelihoods.definition(w,boss).get('leave_policy','') if boss and not boss.is_player else ''
    if policy=='deny' or geology_impacts.room_unusable(w,site) or (role=='guard' and any(w.npcs.get(n.source_def,{}).get('aggressive') for n in w.entities_in_room(site) if n.alive)):raise ValueError(label+' refused leave because the workplace needs '+e.name+'.')
    if role=='guard' and cfg.get('city_perimeter'):
        coworkers=[n for n in w.entities.values() if not n.is_player and n.alive and n.id!=e.id and n.group_id==e.group_id and livelihoods.definition(w,n).get('city_perimeter')]
    qualified=[n for n in coworkers if livelihoods.definition(w,n).get('occupation')==role and livelihoods.work_eligible(w,n) and not busy(w,n) and n.id!=j['issuer'] and n.id not in j['targets']]
    if policy!='cover' and role!='guard' and any(shift_overlap(w,n,minutes)>=lost for n in qualified):
        return label+' approved leave with the shift already staffed.',None
    for n in qualified:
        if shift_overlap(w,n,minutes)>0 or not livelihoods.awake(w,n) or n.progress.get('escort_post') or sleep_movement.asleep(w,n):continue
        reach=distance(w,n,n.location,e.location if cfg.get('city_perimeter') else site)
        if reach is not None and reach<=5:return label+' approved leave. '+n.name+' agreed to cover for '+e.name+'.',n.id
    raise ValueError(label+' required a replacement for '+e.name+'. No qualified coworker was free and close enough to cover the shift.')


def accept(w,e,j):
    if j['status']!='open' or e.id==j['issuer'] or not visible(w,e,j):raise ValueError('This offer is unavailable here.')
    if busy(w,e) or e.progress.get('escort_post'):raise ValueError('This character already has a commitment.')
    steps,minutes=plan(w,e,j)
    if (j['kind'] in ('watch','herd') and any(other['status']=='active' and other['kind'] in ('watch','herd') and set(other['targets']) & set(j['targets']) for other in ledger(w)['jobs'].values())) or any(busy(w,w.entities[k]) for k in j['targets'] if k in w.entities):raise ValueError('Someone needed for this request is already committed.')
    if not e.is_player and not livelihoods.awake(w,e):raise ValueError(e.name+' is off duty and asleep.')
    reason,cover=('',None) if e.is_player else leave(w,e,j,minutes)
    j.update(status='active',worker=e.id,worker_name=e.name,steps=steps,index=0,bound=False,cover=cover,until=now(w)+minutes+5)
    # The accepted route belongs to this task, not the ordinary commuter FIFO.
    getattr(w,'_commute_routes',{}).pop(e.id,None)
    getattr(w,'_pending_commutes',{}).pop(e.id,None)
    changed(w)
    note(w,j,e.name+' accepted. '+reason)
    announce(w,j,e.name+' accepts '+j['name']+'’s local quest: '+j['title']+'.')


def release(w,j,reason):
    j.update(status='returned',worker=None,cover=None,bound=False,to=None)
    changed(w)
    j.pop('ready_at',None);j.pop('watch_since',None)
    note(w,j,reason)


def output(w,j):
    if j['kind']=='gather':return {j['targets'][0]:j['qty']}
    if j['kind']=='make':return {i:n*j['qty'] for i,n in w.recipes[j['targets'][0]]['outputs'].items()}
    return {}


def settle(w,e,j):
    goods=output(w,j);book=ledger(w)
    if any(e.inventory.count(i)<n for i,n in goods.items()):raise ValueError('Bring the finished goods to the handover point.')
    living.consume(e,goods,w);e.gold+=j['pay']
    provider=w.entities.get(j['issuer'])
    for i,n in goods.items():
        if provider:provider.inventory.extend([i]*n)
        else:
            box=book['deliveries'].setdefault(j['issuer'],{})
            box[i]=box.get(i,0)+n
    if provider:provider.progress['community_receipt']=e.name+' completed '+j['title']+' for '+str(j['pay'])+' gold.'
    note(w,j,e.name+' completed '+j['title']+'.')
    announce(w,j,e.name+' completes '+j['title']+' and receives '+str(j['pay'])+' gold from '+j['name']+'.')
    book['recent']=(book['recent']+[dict(id=j['id'],title=j['title'],issuer=j['issuer'],name=j['name'],
        worker=e.id,worker_name=e.name,pay=j['pay'],home=j['home'],mode=j['mode'],status='completed',
        note=j['note'],history=list(j['history']),completed=now(w),to=j.get('to'))])[-48:]
    from engine import npc_life
    npc_life.earned(w,e,j['pay'])
    npc_life.event(w,e,'completed a local quest',3,source=j['issuer'])
    if provider:npc_life.event(w,provider,'received help with a local quest',3,source=e.id)
    del book['jobs'][j['id']]
    changed(w)


def _route_slot(w,e):
    """At most four changed task routes per game minute, with FIFO fairness."""
    minute=now(w)
    pending=getattr(w,'_community_route_queue',None)
    if pending is None:pending=w._community_route_queue=OrderedDict()
    if getattr(w,'_community_route_minute',None)!=minute:
        w._community_route_minute=minute
        w._community_route_slots=set()
        for _ in range(min(4,len(pending))):
            ident,_=pending.popitem(last=False);w._community_route_slots.add(ident)
        w._community_route_free=4-len(w._community_route_slots)
    if e.id in w._community_route_slots:w._community_route_slots.remove(e.id)
    elif w._community_route_free>0:w._community_route_free-=1
    else:
        pending[e.id]=None
        return False
    pending.pop(e.id,None)
    return True


def _move_step(w,e,j,step):
    """Reuse proved paths, validating every live edge before moving one tile."""
    target=step['room'];route=step.get('route',[]);index=step.get('route_index',0)
    def usable():
        if not isinstance(route,(list,tuple)) or not isinstance(index,int) or not 0<=index<len(route):return False
        edge=route[index]
        if not isinstance(edge,(list,tuple)) or len(edge)!=3 or not all(isinstance(x,str) for x in edge):return False
        if not isinstance(route[-1],(list,tuple)) or len(route[-1])!=3 or route[-1][2]!=target:return False
        origin,direction,destination=edge
        return (origin==e.location and origin in w.rooms and destination in w.rooms
                and w.rooms[origin].exits.get(direction)==destination
                and not frontiers.blocked(w,origin,direction,e))
    if not usable():
        if now(w)<step.get('route_retry_at',-1):return False
        if not _route_slot(w,e):
            # Queue delay is not work the resident failed to perform.
            if j.get('route_waited_at')!=now(w):
                j['until']+=1;j['route_waited_at']=now(w)
            return False
        route=frontiers.path(w,e.location,target,e)
        if route is None:
            step.update(route=[],route_index=0,route_retry_at=now(w)+4)
            return False
        index=0;step.update(route=route,route_index=0)
        step.pop('route_retry_at',None)
        if not route:return e.location==target
        if not usable():return False
    _,_,destination=route[index]
    moved=w.move_entity(e.id,destination)
    if moved:step['route_index']=index+1
    return bool(moved)


def work(w,e,j,automatic=False):
    if j['status']!='active' or j['worker']!=e.id:raise ValueError('Accept this request before working on it.')
    step=j['steps'][j['index']];action=step['action'];room=step['room']
    if action in ('find','herd','watch'):
        try:crew=checked_subjects(w,j)
        except ValueError as exc:
            release(w,j,str(exc));return
        room=crew[0].location;step['room']=room
    if e.location!=room:
        if automatic:
            _move_step(w,e,j,step)
            if e.location!=room:
                e.activity='travelling to '+w.rooms[room].name+' for '+j['title']
                return
            # Arrival is an observation now. Waiting for another tick could
            # miss a moving person/animal who leaves later in this same tick.
        else:raise ValueError('Go to '+w.rooms[room].name+' for the next step.')
    if action in ('gather','make'):
        if automatic:
            label=(w.resources if action=='gather' else w.recipes).get(step['key'],{}).get('name',step['key'])
            e.activity=('gathering ' if action=='gather' else 'making ')+label+' for '+j['name']+'’s local quest'
        if step.get('renewal') and action=='gather':
            reason=gathering.resource_state(w,e,room,w.resources[step['key']])
            if reason and ('Ready ' in reason or 'minute' in reason or 'replenish' in reason):
                if automatic:e.activity='waiting for '+w.resources[step['key']]['name']+' to replenish';return
                raise ValueError(reason)
        if automatic:
            if 'ready_at' not in j:j['ready_at']=now(w)+step['length'];return
            if now(w)<j['ready_at']:return
        from engine.commands import CommandContext
        iid=step['key'];verb='craft' if action=='make' else 'gather'
        counter=verb+':'+iid;before=e.progress.get('actions',{}).get(counter,0)
        if action=='make':knowledge.teach(w,e,{'recipes':[iid]})
        w._community_acting=True
        w._community_simulating=automatic
        try:reason=living.command(CommandContext(w,e,w.rooms[room]),iid,verb)
        finally:w._community_acting=False;w._community_simulating=False
        if e.progress.get('actions',{}).get(counter,0)<=before:raise ValueError(reason)
        j.pop('ready_at',None)
    elif action=='watch':
        if sleep_movement.asleep(w,e):raise ValueError('The caregiver must be awake.')
        if not j['bound']:j['bound']=True;changed(w)
        since=j.setdefault('watch_since',now(w))
        if now(w)-since<j['qty']:
            e.activity='watching '+', '.join(a.name for a in crew);return
        j['bound']=False;changed(w)
    elif action=='herd':
        if not j['bound']:j['bound']=True;changed(w)
    elif action=='arrive':
        if any(w.entities.get(t) is None or w.entities[t].location!=room for t in j['targets']):raise ValueError('The whole herd must arrive together.')
        j['bound']=False;changed(w)
    elif action=='deliver':
        settle(w,e,j);return
    j['index']+=1


def movement(w,e,old,new):
    if 'community_jobs' not in getattr(w,'living_state',{}):return
    j=duties(w)[0].get(e.id)
    for j in ([j] if j else []):
        if j['worker']!=e.id or not j.get('bound'):continue
        if j['kind']=='watch':
            j.pop('watch_since',None);j['bound']=False;changed(w);continue
        for key in j['targets']:
            n=w.entities.get(key)
            if not n or not n.alive or n.location!=old or not any(dst==new and not frontiers.blocked(w,old,di,n) for di,dst in w.rooms[old].exits.items()):
                release(w,j,'The herd could not follow through that passage.');break
            n._herding=True
            try:moved=w.move_entity(n.id,new)
            finally:del n._herding
            if not moved:
                release(w,j,n.name+' could not follow through that passage.');break


def frozen(w,e):
    return 'community_jobs' in getattr(w,'living_state',{}) and e.id in duties(w)[2]


def ask_or_return(w,e,j):
    try:accept(w,e,j)
    except ValueError as exc:
        text=str(exc);j['declined'][e.id]=now(w)+120
        # A public offer remains open when one worker cannot obtain shift cover.
        # Only an offer addressed specifically to this person is returned.
        if j.get('to')==e.id:
            release(w,j,e.name+' could not take the request. '+text)
        else:note(w,j,e.name+' declined. '+text)


def propose(w,giver,turn):
    """Choose actual local needs or acquaintances. No random global target lookup."""
    seen=[e for e in w.entities_in_room(giver.location) if e.alive and e.id!=giver.id]
    options=[]
    rd=living.details(w,giver.location)
    for key in rd.get('resources',()):
        for item in w.resources.get(key,{}).get('yields',{}):
            if item in w.items:options.append(('gather',[item],1,None))
    stock=livelihoods.job_needs(w,giver)
    for item in stock:
        if item in sites(w)[0]:options.append(('gather',[item],1,None))
    for recipe in rd.get('workshop',{}).get('recipes',())[:3]:
        if recipe in w.recipes:options.append(('make',[recipe],1,None))
    for e in seen:
        if child(w,e):options.append(('watch',[e.id],20,None))
        if animal(w,e):
            pasture=next((v for v in w.rooms[giver.location].exits.values() if v in w.rooms and set(living.details(w,v).get('facilities',())) & {'farm','husbandry'}),None)
            if pasture:options.append(('herd',[e.id],1,pasture))
    familiar=sorted(contacts(w,giver))
    for ident in familiar:
        e=w.entities.get(ident)
        if e and e.alive and e.location!=giver.location and (human(w,e) or animal(w,e)) and e.group_id==giver.group_id:
            options.append(('find',[ident],1,None));break
    if not options and seen:
        other=next((e for e in seen if human(w,e) or animal(w,e)),None)
        if other:options.append(('find',[other.id],1,None))
    if not options:return
    kind,targets,qty,dest=options[turn%len(options)]
    name=(w.items if kind=='gather' else w.recipes).get(targets[0],{}).get('name') if kind in ('make','gather') else w.entities[targets[0]].name
    spec=dict(kind=kind,targets=targets,qty=qty,dest=dest,home=giver.location,title=LABELS[kind]+' · '+name)
    mode='board' if board(w,giver.location) and turn%3 else 'ask'
    try:
        return post(w,giver,spec,mode,next((e.id for e in seen if is_eligible(w,e) and e.id not in targets),None) if mode=='ask' and turn%2 else None)
    except ValueError as exc:
        giver.progress['community_offer_reason']=str(exc)
        return None


def is_eligible(w,e):
    return (not e.is_player and human(w,e) and e.alive and livelihoods.work_eligible(w,e)
            and livelihoods.awake(w,e) and not sleep_movement.asleep(w,e) and not e.progress.get('escort_post'))


def recruit(w,j):
    giver=w.entities.get(j['issuer'])
    if not giver and j['mode']=='ask':return
    room=j['home'] if j['mode']=='board' else giver.location
    people=w.entities_in_room(room)
    if j['mode']=='ask' and giver and not giver.is_player:
        for p in people:
            if p.is_player and (not j['to'] or j['to']==p.id):
                message(w,p,giver.name+' asks for help: '+j['title']+f" ({j['pay']} gold). Open Local quests.")
        if not j.get('to') and (not livelihoods.definition(w,giver).get('occupation') or not livelihoods.on_shift(w,giver)) and not busy(w,giver) and not sleep_movement.asleep(w,giver):
            roads=[(di,r) for di,r in w.rooms[room].exits.items() if r in w.rooms and w.rooms[r].group==w.rooms[room].group and di in ('north','east','south','west') and not frontiers.blocked(w,room,di,giver)]
            if roads and not any(e.id!=giver.id and e.id not in j['targets'] and (e.is_player or is_eligible(w,e)) and j['declined'].get(e.id,-1)<=now(w) for e in people):
                w.move_entity(giver.id,roads[(now(w)//12)%len(roads)][1]);giver.activity='asking around for help';return
    candidates=[e for e in people if e.id!=j['issuer'] and e.id not in j['targets'] and
                (not j['to'] or e.id==j['to']) and is_eligible(w,e) and not busy(w,e) and j['declined'].get(e.id,-1)<=now(w)
                and (not giver or min(society.friendliness(w,giver,e),society.friendliness(w,e,giver))>=50)]
    for candidate in candidates[:3]:
        ask_or_return(w,candidate,j)
        if j['status']!='open':break


def advance(w):
    if not available(w):return
    book=ledger(w);minute=now(w)
    book['recent'][:]=[j for j in book['recent'] if minute-j.get('completed',0)<1500]
    for j in list(book['jobs'].values()):
        if j['status']!='active':continue
        e=w.entities.get(j['worker'])
        if not e:continue  # A disconnected player may resume later.
        if not e.alive:release(w,j,e.name+' was incapacitated.');continue
        if j['kind'] in ('find','watch','herd') and any(k not in w.entities or not w.entities[k].alive for k in j['targets']):
            release(w,j,'A requested person or animal is no longer available.');continue
        if j.get('cover') and (j['cover'] not in w.entities or not w.entities[j['cover']].alive):
            release(w,j,'The agreed replacement is no longer available.');continue
        if not e.is_player and minute>j['until'] and shift_overlap(w,e,6)>5:
            release(w,j,e.name+' returned the request because the agreed leave ended and the next shift needs them.');continue
        if not e.is_player and (minute>j['until']+max(20,j['estimate']) or (sleep_movement.asleep(w,e) and shift_overlap(w,e,5))):
            release(w,j,e.name+' could not finish within the agreed time.');continue
        if e.is_player and j.get('watch_since') is not None and sleep_movement.asleep(w,e):
            j.pop('watch_since',None);j['bound']=False;changed(w)
    if minute>=book.get('next_recruit',0):
        book['next_recruit']=minute+12
        for j in list(book['jobs'].values()):
            if j['status']=='open':recruit(w,j)
    for j in list(book['jobs'].values()):
        if j['status']=='active' or j.get('player_post') or minute-j['created']<600:continue
        giver=w.entities.get(j['issuer'])
        if giver:giver.gold+=j['pay']
        del book['jobs'][j['id']]
    if minute<book.get('next_offer',0):return
    book['next_offer']=minute+10
    # Rotate through a bounded sample. Do not plan work for the entire population every tick.
    roster=getattr(w,'_community_roster',None)
    if not roster or minute>=getattr(w,'_community_recount',0):
        roster=[e.id for e in w.entities.values() if not e.is_player and e.alive and human(w,e)]
        w._community_roster=roster;w._community_recount=minute+1500
    turn=book.get('turn',0);book['turn']=turn+1
    if not roster:return
    occupied={j['issuer'] for j in book['jobs'].values()}
    if sum(not j.get('player_post') for j in book['jobs'].values())>=24:return
    # Alternate a local sample with the global rotation. A large population
    # must not starve the room the player can actually observe. No teleporting,
    # free rewards, whole-world route planning, or unseen offer disclosure.
    local=[]
    if turn%2==0:
        rooms={e.location for e in w.entities.values() if e.is_player and e.alive}
        for room in sorted(rooms):
            local.extend(e.id for e in w.entities_in_room(room) if not e.is_player)
        if local:
            offset=(turn//2)%len(local);local=local[offset:]+local[:offset]
    sample=list(dict.fromkeys(local[:12]+[roster[(turn*13+off)%len(roster)] for off in range(min(12,len(roster)))]))
    attempts=0
    for ident in sample:
        e=w.entities.get(ident)
        if (e and e.gold>=3 and e.id not in occupied and is_eligible(w,e) and not busy(w,e)
                and minute>=e.progress.get('community_offer_after',0)):
            attempts+=1
            job=propose(w,e,turn)
            e.progress['community_offer_after']=minute+(120 if job else 30)
            if job or attempts>=3:break


def assignment(w,e):
    if 'community_jobs' not in getattr(w,'living_state',{}):return False
    workers,covers,groups=duties(w)
    job=workers.get(e.id) or covers.get(e.id) or groups.get(e.id)
    for j in ([job] if job else []):
        if j['status']!='active':continue
        if j.get('cover')==e.id:
            worker=w.entities[j['worker']];cfg=livelihoods.definition(w,worker)
            if cfg.get('city_perimeter'):
                perimeter(w,e,cfg,relief=True)
            else:
                room=livelihoods.workplace(w,worker)
                if e.location!=room:
                    step=j.setdefault('cover_step',dict(room=room))
                    step['room']=room
                    _move_step(w,e,j,step)
            e.activity='covering the shift for '+worker.name;return True
        if j['worker']==e.id:
            try:work(w,e,j,automatic=True)
            except ValueError as exc:release(w,j,e.name+' returned the request. '+str(exc))
            return True
        if j.get('bound') and e.id in j['targets']:return True
    return False


def patrol_route(w,cfg):
    cache=getattr(w,'_community_patrols',None)
    if cache is None:w._community_patrols=cache={}
    key=cfg['id']
    if key not in cache:
        # Imported buildings gain public frontage tiles after the world loads.
        route=[]
        for rid in cfg.get('patrol_route',[]):
            if rid not in w.rooms:continue
            outside=w.rooms[rid].exits.get('step outside')
            tile=outside if outside in getattr(w,'_street_origins',{}) else rid
            if not route or route[-1]!=tile:route.append(tile)
        cache[key]=route
    return cache[key]


def perimeter(w,e,cfg=None,relief=False):
    cfg=cfg or livelihoods.definition(w,e)
    if not cfg.get('city_perimeter') or (not relief and not livelihoods.on_shift(w,e)):return False
    route=patrol_route(w,cfg)
    if not route:return False
    # When entering duty, join the circuit at the nearest post.
    index=e.progress.get('perimeter_post')
    if not isinstance(index,int):
        index=min(range(len(route)),key=lambda i:nearest(w,e.location,route[i]))
    index%=len(route)
    if e.location==route[index]:index=(index+1)%len(route)
    e.progress['perimeter_post']=index;destination=route[index]
    if destination in w.rooms[e.location].exits.values():
        direction=next((d for d,r in w.rooms[e.location].exits.items() if r==destination and not frontiers.blocked(w,e.location,d,e)),None)
        if direction:w.move_entity(e.id,destination)
        else:livelihoods.move_towards(w,e,destination)
    else:livelihoods.move_towards(w,e,destination)
    e.activity='patrolling the city perimeter toward '+w.rooms[destination].name
    livelihoods.public_wage(w,e);return True


def view(w,p):
    book=ledger(w)
    for iid,n in book['deliveries'].pop(p.id,{}).items():p.inventory.extend([iid]*n)
    rows=[]
    for j in list(book['jobs'].values())+list(reversed(book['recent'])):
        if not visible(w,p,j):continue
        mine=j['issuer']==p.id;assigned=j['worker']==p.id and j['status']=='active'
        # Completed history is read-only, including for the former issuer.
        if j['status']=='completed':mine=False
        row=dict(id=j['id'],title=j['title'],issuer=j['name'],pay=j['pay'],status=j['status'],
                 personal=j.get('to')==p.id,where=w.rooms[j['home']].name,note=j['note'],mine=mine,assigned=assigned,history=j['history'],worker=j.get('worker_name',''))
        if assigned:
            step=j['steps'][j['index']];rid=step['room'];key=step['key']
            if step['action'] in ('find','herd','watch') and key in w.entities:rid=w.entities[key].location
            label={'arrive':'Bring the whole herd','deliver':'Hand over and collect payment','make':'Make','watch':'Supervise','herd':'Gather the herd','find':'Identify','gather':'Gather'}[step['action']]
            name=w.resources.get(key,{}).get('name') if step['action']=='gather' else w.recipes.get(key,{}).get('name') if step['action']=='make' else ''
            row.update(step=label+(' '+name if name else ''),room=w.rooms[rid].name,here=p.location==rid)
            if j.get('watch_since') is not None:row['remaining']=max(0,j['qty']-(now(w)-j['watch_since']))
        rows.append(row)
    return dict(rows=rows,gold=p.gold,nearby=[[e.id,e.name] for e in w.entities_in_room(p.location) if e.id!=p.id and e.alive and human(w,e)],receipt=p.progress.get('community_receipt',''))


def handle(w,p,data):
    if not available(w):raise ValueError('This world has local requests turned off.')
    action=data.get('action','list')
    if not p or not p.alive or p.location not in w.rooms:raise ValueError('Enter the world with a living character.')
    if action=='catalog':return dict(catalog=catalog(w,p))
    if action=='list':return view(w,p)
    if sleep_movement.asleep(w,p):raise ValueError('Wake up before working on a request.')
    if action in ('quote','post'):
        spec=spec_for(w,p,data)
        if action=='quote':
            steps,minutes=offer_plan(w,p,spec,data.get('to') if data.get('mode')=='ask' else None);return dict(pay=reward(w,spec,minutes),funds=p.gold,minutes=minutes,route=[w.rooms[x['room']].name for x in steps])
        j=post(w,p,spec,data.get('mode'),data.get('to'),data.get('expected_pay'));j['player_post']=True
        return view(w,p)
    rid=data.get('job')
    j=ledger(w)['jobs'].get(rid) if isinstance(rid,str) else None
    if not j or not visible(w,p,j):raise ValueError('This request is no longer available here.')
    if action=='accept':accept(w,p,j)
    elif action=='work':work(w,p,j)
    elif action=='return' and p.id==j['worker']:release(w,j,p.name+' cancelled the assignment.')
    elif action=='withdraw' and p.id==j['issuer'] and j['status']!='active':
        p.gold+=j['pay'];del ledger(w)['jobs'][rid]
    elif action=='repost' and p.id==j['issuer'] and j['status']=='returned':
        offer_plan(w,p,j)
        if j['mode']=='board' and p.location!=j['home']:raise ValueError('Return to the original noticeboard to repost.')
        j.update(status='open',declined={},to=None,created=now(w));note(w,j,'Offered again.')
    elif action=='offer' and p.id==j['issuer'] and j['status'] in ('open','returned'):
        target=data.get('to')
        if not isinstance(target,str) or not any(e.id==target and e.id!=p.id and e.alive and human(w,e) for e in w.entities_in_room(p.location)):raise ValueError('Choose someone here.')
        offer_plan(w,p,j,target);j.update(status='open',mode='ask',to=target,declined={})
        message(w,w.entities[target],p.name+' has offered you a local quest.')
    elif action=='decline' and j['to']==p.id and j['status']=='open':release(w,j,p.name+' declined the personal offer.')
    else:raise ValueError('That action is unavailable for this request.')
    return view(w,p)

def performed(w,e,verb,key):
    if getattr(w,'_community_acting',False) or 'community_jobs' not in getattr(w,'living_state',{}):return
    job=duties(w)[0].get(e.id)
    if not job:return
    step=job['steps'][job['index']]
    if step['room']==e.location and step['action']=={'gather':'gather','craft':'make','cook':'make'}.get(verb) and step['key']==key:
        job['index']+=1
