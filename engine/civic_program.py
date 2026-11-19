"""The town paper, public meeting places and scheduled passenger service."""
from hashlib import sha256
from engine import gazette, worldtime, relationships, sleep_movement

DAY = worldtime.MINUTES_PER_DAY
# Times are local world-clock minutes. Each event lasts one game hour.
FARE = 2


def cities(w):
    return [e for e in gazette.editions(w) if e.get('kind') in ('city','town') and e.get('home') in w.rooms]


def stop(w,rid):
    return next((e for e in cities(w) if e['home']==rid),None)


def carriage_stop(w,actor):
    """The existing carriage body at a public stop is a parked service fixture.

    Other carts, drivers and carriage encounters keep their authored routines.
    The source identity is the same convention used by costumes.subject; the
    stand must also be an actual authored city/town passenger-service stop.
    """
    if not actor or actor.is_player:return None
    definition=w.npcs.get(actor.source_def,{})
    if not str(definition.get('id',actor.source_def) or '').endswith('_carriage'):return None
    home=definition.get('spawn_room')
    return home if home in w.rooms and stop(w,home) else None


def hold_carriage(w,actor):
    home=carriage_stop(w,actor)
    if not home or not actor.alive:return False
    # Recover older runtime saves in which the stand's carriage patrolled away.
    # This moves only that fixture, never a passenger or a driver NPC.
    if actor.location!=home:w.move_entity(actor.id,home,forced=True)
    getattr(w,'_commute_routes',{}).pop(actor.id,None)
    actor.activity='waiting at the carriage stand'
    return True


def clock(t):
    t=int(t)%DAY
    return f'{t//60:02d}:{t%60:02d}'


def departure(now):
    day,minute=divmod(int(now),DAY)
    hour=max(7,minute//60+1)
    return day*DAY+hour*60 if hour<=20 else (day+1)*DAY+420


def state(w):
    return w.living_state.setdefault('public_program_v1',{'participants':{},'results':{},'tickets':{}})


def key(day,venue,kind):
    return f'{day}/{venue}/{kind}'


def entries(w,place,day):
    now=int(w.living_state['minute'])
    area=place['home']
    for kind,title,start,detail in w.metadata.get('public_program',()):
        begin=day*DAY+start
        yield {'id':key(day,area,kind),'kind':kind,'title':title,'venue':area,'name':w.rooms[area].name,
               'begin':begin,'end':begin+60,'detail':detail,'open':begin<=now<begin+60}


def journey_detail(w,source,dest,due,now):
    wait=max(0,int(due)-int(now));unit='minute' if wait==1 else 'minutes'
    return (f"Departs {w.rooms[source].name} at {clock(due)} (in {wait} game {unit}). "
            f"Arrive directly at {w.rooms[dest].name} at departure. "
            f"Stay at the stand; leaving cancels the booking. Fare: {FARE} gold.")


def paper(w,areas,day,venues=None):
    if not getattr(w,'living_state',None):return []
    saved=w.living_state.get('public_program_v1',{}).get('results',{})
    lines=[]
    for place in cities(w):
        if place['name'] not in areas:continue
        for e in entries(w,place,day):
            result=saved.get(e['id']);now=w.living_state['minute']
            if e['end']<=now and result is None:continue
            label='Result' if result is not None else 'Happening now' if e['open'] else 'Coming up'
            lines.append(f"{label} · {clock(e['begin'])}–{clock(e['end'])} · {e['title']}\n{place['name']} · {e['name']}\n"+(result if result is not None else e['detail']))
            if venues is not None and result is None:venues[lines[-1]] = e['venue']
    return lines


def view(w,p):
    town=stop(w,p.location)
    if not town:return []
    now=int(w.living_state['minute']);day=now//DAY;s=state(w)
    rows=[]
    ticket=s['tickets'].get(p.id)
    if ticket and ticket['from']==p.location:
        dest=w.rooms.get(ticket['to'])
        if dest:rows.append(dict(id='ticket',label='Carriage to '+dest.name,detail=journey_detail(w,ticket['from'],ticket['to'],ticket['time'],now),command='carriage cancel',action='Cancel booking'))
    else:
        for dest in cities(w):
            if dest['home']==p.location:continue
            rows.append(dict(id='coach-'+dest['home'],label=dest['name'],detail=journey_detail(w,p.location,dest['home'],departure(now),now),
                             command='carriage '+dest['name'],action='Book carriage',disabled=p.gold<FARE))
    for e in entries(w,town,day):
        if not e['open']:continue
        joined=p.id in s['participants'].get(e['id'],{})
        rows.append(dict(id=e['id'],label=e['title'],detail=e['detail']+' Ends at '+clock(e['end']),command='attend '+e['kind'],action='Attending' if joined else 'Attend',disabled=joined))
    return rows


def command(ctx,args,verb):
    w,p=ctx.world,ctx.player;s=state(w);now=int(w.living_state['minute'])
    if verb=='carriage' and args.casefold()=='cancel':
        return 'Carriage booking cancelled.' if s['tickets'].pop(p.id,None) else 'You have no carriage booking.'
    place=stop(w,p.location)
    if not place:return 'Visit a city carriage stand or public venue. The local newspaper lists the meeting place.'
    if verb=='attend':
        event=next((e for e in entries(w,place,now//DAY) if e['open'] and args.casefold() in (e['kind'],e['title'].casefold())),None)
        if not event:return 'That event is not in session here. Check the newspaper for the time and venue.'
        people=s['participants'].setdefault(event['id'],{})
        if p.id in people:return 'You have already joined this event.'
        people[p.id]=p.name
        if event['kind']=='class':
            from engine import task_skills
            gained=task_skills.practice(w,p,'fieldcraft',difficulty=10,effort=10,event_id='class:'+event['id'])
            return ('You compare two trail bearings and trace your route back to the square. You gain fieldcraft practice.'+
                    (' Fieldcraft reaches '+str(task_skills.level(w,p,'fieldcraft'))+'.' if gained else ''))
        if event['kind']=='speech':
            return f"The council opens the floor at {w.rooms[p.location].name}. A speaker explains the carriage fare of {FARE} gold and the last departure at 20:00."
        return 'You join the '+event['title']+'. '+event['detail']
    destinations=[e for e in cities(w) if e['home']!=p.location]
    dest=next((e for e in destinations if args.casefold()==e['name'].casefold()),None)
    if not dest:return 'Carriages from '+place['name']+': '+', '.join(e['name'] for e in destinations)+'.'
    if p.id in s['tickets']:return 'You already have a carriage booking.'
    if p.gold<FARE:return f'The fare is {FARE} gold.'
    due=departure(now);s['tickets'][p.id]={'from':p.location,'to':dest['home'],'time':due}
    return 'Carriage booked to '+dest['name']+'. '+journey_detail(w,p.location,dest['home'],due,now)+' The fare is collected only when the trip succeeds.'


def eligible(w,p):
    return p.alive and not sleep_movement.asleep(w,p) and not p.progress.get('permanently_dead') and p.progress.get('restrained_until',0)<=w.living_state['minute']


def ride(w,p,source,dest):
    from engine import geology_impacts
    if (not p or p.location!=source or dest not in w.rooms or p.gold<FARE or not eligible(w,p)
        or geology_impacts.room_unusable(w,source) or geology_impacts.room_unusable(w,dest)):
        return False
    if not w.move_entity(p.id,dest):return False
    p.gold-=FARE
    if p.is_player:
        if dest not in p.explored_rooms:p.explored_rooms.append(dest)
        w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
    else:p.activity='arriving by carriage'
    return True


def advance(w,before,now):
    towns=cities(w)
    if not towns or now<=before:return
    s=state(w)
    for aid,ticket in list(s['tickets'].items()):
        if ticket['time']>now:continue
        s['tickets'].pop(aid)
        actor=w.entities.get(aid)
        arrived=ride(w,actor,ticket['from'],ticket['to'])
        if actor and actor.is_player:
            text=('The carriage departs '+w.rooms[ticket['from']].name+' and reaches '+w.rooms[actor.location].name+f'. You paid {FARE} gold.' if arrived else 'The carriage could not carry you. No fare was collected.')
            w.rest_notifications=getattr(w,'rest_notifications',[])+[(aid,text)]
    for day in range(max(int(before)//DAY,int(now)//DAY-8),int(now)//DAY+1):
        for place in towns:
            venue=place['home']
            for e in entries(w,place,day):
                if not before<e['end']<=now or e['id'] in s['results']:continue
                names=s['participants'].pop(e['id'],{})
                from engine import livelihoods
                for a in w.entities_in_room(venue):
                    if not a.is_player and eligible(w,a) and relationships.sentient(w,a) and not livelihoods.on_shift(w,a):
                        names.setdefault(a.id,a.name)
                n=len(names)
                if not n:outcome='The session closed without attendees.'
                elif e['kind']=='contest':
                    def score(aid):
                        return 1+int.from_bytes(sha256((e['id']+aid).encode()).digest()[:4],'big')%100
                    winner=max(sorted(names),key=score)
                    outcome=f'{names[winner]} took first place with {score(winner)} points among {n} entrants.'
                else:outcome=(f'{n} attended the fieldcraft lesson on trails and bearings.' if e['kind']=='class' else f'{n} attended the public council discussion.')
                s['results'][e['id']]=outcome
    if departure(before)<=now:
        # Residents who actually need to reach a different town can use the same service.
        from engine import livelihoods, gazette
        for place in towns:
            for a in list(w.entities_in_room(place['home'])):
                if a.is_player or carriage_stop(w,a) or not eligible(w,a) or not relationships.sentient(w,a) or a.progress.get('companion_owner'):continue
                profile=livelihoods.definition(w,a)
                dest=profile.get('work_room') if livelihoods.on_shift(w,a) else a.progress.get('home_room') or profile.get('home_room')
                wanted=gazette.local(w,dest)
                if wanted in towns and wanted!=place:ride(w,a,place['home'],wanted['home'])
    if int(before)//DAY!=int(now)//DAY:
        cutoff=int(now)//DAY-8
        for table in ('results','participants'):
            for k in list(s[table]):
                if int(k.split('/',1)[0])<cutoff:del s[table][k]

