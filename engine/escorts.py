"""Physical, identity-bound escort objectives for accepted quests."""
from engine import frontiers, sleep_movement


def choices(w,p):
    return [w.quests[q] for q,status in p.progress.get('quests',{}).items()
            if status=='active' and w.quests.get(q,{}).get('escort')
            and not p.progress.get('escort_arrivals',{}).get(q)]


def pair(w,p):
    run=p.progress.get('escort_party') or {}
    n=w.entities.get(run.get('npc'))
    q=w.quests.get(run.get('quest'),{})
    if n and n.alive and n.progress.get('escort_owner')==p.id and p.progress.get('quests',{}).get(q.get('id'))=='active' and q.get('escort',{}).get('npc')==n.source_def:
        return n,q
    return None,None


def start_room(w,q):
    return q.get('offer_room') or w.npcs.get(q['escort']['npc'],{}).get('spawn_room')


def return_to_start(w,p,q,reset=True):
    n=companion(w,p,q)
    if reset:p.progress.get('escort_arrivals',{}).pop(q['id'],None)
    if p.progress.get('escort_party',{}).get('quest')==q['id']:
        p.progress.pop('escort_party',None)
    if not n:return
    booking=n.progress.get('escort_booking')
    if booking and booking!=[p.id,q['id']]:return
    if n.progress.get('escort_owner') not in (None,p.id):return
    n.progress.pop('escort_booking',None)
    n.progress.pop('escort_owner',None)
    home=start_room(w,q)
    if home in w.rooms:
        n.progress['escort_post']=home
        n.activity='waiting at the meeting place' if n.location==home else 'returning to '+w.rooms[home].name
        record(w,p,n,n.name+' is due back at '+w.rooms[home].name+'.')


def service_move(w,n,target):
    n._escort_step=True
    try:return w.move_entity(n.id,target)
    finally:del n._escort_step


def step_toward(w,n,target):
    if n.location==target:return
    path=frontiers.path(w,n.location,target,n)
    if path:service_move(w,n,path[0][2])


def meet(w,p,q):
    from engine import navigation
    if q['id'] not in navigation.selected(w,p):return False
    assigned,job=pair(w,p)
    if assigned:
        if job['id']==q['id']:
            assigned.progress.update(escort_booking=[p.id,q['id']],escort_post=start_room(w,q))
            return True
        return False
    n=companion(w,p,q);home=start_room(w,q)
    if not n or home not in w.rooms or n.progress.get('escort_owner') not in (None,p.id):return False
    booking=n.progress.get('escort_booking')
    if booking and booking!=[p.id,q['id']]:return False
    n.progress['escort_booking']=[p.id,q['id']]
    arrived=p.progress.get('escort_arrivals',{}).get(q['id'])
    meeting=q['escort']['destination'] if arrived else home
    n.progress['escort_post']=meeting
    if n.location!=meeting or (p.location!=meeting and not arrived):return False
    if sleep_movement.asleep(w,n):sleep_movement.wake(w,n,'your guiding appointment')
    p.progress['escort_party']={'npc':n.id,'quest':q['id']}
    n.progress['escort_owner']=p.id
    n.activity='waiting for the report' if arrived else 'guiding '+p.name if q['escort']['mode']=='follow' else 'following '+p.name
    record(w,p,n,n.name+' is '+n.activity+' at '+w.rooms[meeting].name+'.')
    return True


def prepare(w,p):
    from engine import navigation
    actor,job=pair(w,p)
    if actor:
        if job['id'] in navigation.selected(w,p):
            meet(w,p,job)
            return
        return_to_start(w,p,job)
    for qid in navigation.selected(w,p):
        q=w.quests[qid]
        if q.get('escort') and meet(w,p,q):break


def advance(w):
    for p in tuple(w.entities.values()):
        if p.is_player and p.alive:prepare(w,p)
    # Only guides with a posted appointment are moved. Other residents keep their schedules.
    for source in guide_sources(w):
        n=w.entities.get('npc:'+source)
        if not n or not n.alive:continue
        post=n.progress.get('escort_post')
        if post not in w.rooms:continue
        owner=w.entities.get(n.progress.get('escort_owner'))
        if owner:
            guide,job=pair(w,owner)
            if guide is n:
                arrived=owner.progress.get('escort_arrivals',{}).get(job['id'])
                target=job['escort']['destination'] if arrived else owner.location
                if target in w.rooms:step_toward(w,n,target)
                continue
            n.progress.pop('escort_owner',None)
        if sleep_movement.asleep(w,n):sleep_movement.wake(w,n,'your guiding appointment')
        step_toward(w,n,post)
        n.activity='waiting at the meeting place' if n.location==post else 'returning to '+w.rooms[post].name
        if n.location==post and not n.progress.get('escort_booking'):
            n.progress.pop('escort_post',None)
            from engine import npc_attention
            npc_attention.begin(w,n)


def guide_sources(w):
    if not hasattr(w,'_guide_sources'):w._guide_sources={q['escort']['npc'] for q in w.quests.values() if q.get('escort')}
    return w._guide_sources


def companion(w,p,q):
    source=q['escort']['npc']
    assigned,job=pair(w,p)
    if assigned and job['id']==q['id']:return assigned
    actor=w.entities.get('npc:'+source)
    if actor and actor.alive and actor.location in w.rooms:return actor
    return next((n for n in w.entities.values() if n.source_def==source and n.alive and n.location in w.rooms),None)


def report(w,p,q):
    actor=companion(w,p,q)
    if not actor:return 'No living guide is currently available.'
    assigned,job=pair(w,p)
    if p.progress.get('escort_arrivals',{}).get(q['id']):
        role='Waiting for your report' if p.progress.get('quests',{}).get(q['id'])=='active' else actor.name
    elif assigned is actor and job['id']==q['id']:
        role='Following you' if q['escort']['mode']=='lead' else 'Guiding you'
    else:
        home=start_room(w,q)
        booking=actor.progress.get('escort_booking',[])
        if booking and booking[0]!=p.id:return actor.name+' is guiding another traveller. Your meeting place is '+w.rooms[home].name+'.'
        if home in w.rooms and actor.location!=home:
            return actor.name+' is at '+w.rooms[actor.location].name+'. Meet at '+w.rooms[home].name+'.'
        role='Meet '+actor.name
    return role+' at '+w.rooms[actor.location].name+'.'


def record(w,p,n,text):
    from engine import resident_watch
    resident_watch.note(w,[n.id,p.id],text)
    # Preserve unwatched travel too, without duplicating live observations.
    if not resident_watch._entry(w,n.id):
        events=n.progress.setdefault('unseen_escort_events',[])
        events.append([w.living_state['minute'],w.rooms[n.location].name,text.replace(p.name,'a visiting adventurer')])
        del events[:-128]


def command(ctx,args,mode):
    w,p=ctx.world,ctx.player
    from engine import navigation
    if args.strip().casefold()=='stop':
        _,job=pair(w,p)
        return navigation.command(ctx,job['id'],remove=True) if job else 'You have no travelling companion.'
    query=args.strip().casefold()
    matches=[q for q in choices(w,p) if q['escort']['mode']==mode and
             (not query or query in (q['id'].casefold(),q['name'].casefold(),w.npcs[q['escort']['npc']]['name'].casefold()))]
    if len(matches)!=1:return 'Choose the named guide for an accepted quest in your journal.'
    q=matches[0]
    if q['id'] not in navigation.selected(w,p):
        navigation.command(ctx,q['id'])
    current,other=pair(w,p)
    if current and other['id']!=q['id']:return 'Finish or untrack '+other['name']+' before starting this journey.'
    meet(w,p,q)
    return report(w,p,q)



def advice(w,p):
    n,q=pair(w,p)
    if not n:return None
    return dict(mode=q['escort']['mode'],name=n.name,destination=w.rooms[q['escort']['destination']].name,
                paused=bool(p.progress['escort_party'].get('paused')))


def next_direction(w,p,n,q):
    if p.location!=n.location:return None
    dest=q['escort']['destination']
    steps=frontiers.path(w,n.location,dest,n)
    return steps[0][1] if steps else None


def check(w,p,di,target):
    prepare(w,p)
    if not p.progress.get('escort_party'):return ''
    n,q=pair(w,p)
    if not n:
        p.progress.pop('escort_party',None);return 'Your companion is unavailable. Check the journal for the meeting place.'
    if p.progress.get('escort_arrivals',{}).get(q['id']):return ''
    if n.location!=p.location:return 'Your companion is on the way to you.'
    if sleep_movement.asleep(w,n):return n.name+' is sleeping.'
    reason=frontiers.blocked(w,n.location,di,n)
    if reason:return n.name+' cannot pass. '+reason
    if q['escort']['mode']=='follow' and di!=next_direction(w,p,n,q):
        return 'Your guide is taking a different route. Use follow stop to leave the party.'
    return ''


def accompany(w,p,origin,di):
    n,q=pair(w,p)
    if not n or p.progress.get('escort_arrivals',{}).get(q['id']) or n.location!=origin or p.location==origin or w.rooms[origin].exits.get(di)!=p.location:return ''
    if not service_move(w,n,p.location):return n.name+' could not follow you.'
    record(w,p,n,n.name+(' guided ' if q['escort']['mode']=='follow' else ' followed ')+p.name+' to '+w.rooms[n.location].name+'.')
    if n.location!=q['escort']['destination']:return ''
    p.progress.setdefault('escort_arrivals',{})[q['id']]=n.id
    n.activity='waiting for the report'
    record(w,p,n,n.name+' is waiting at '+w.rooms[n.location].name+' for the report.')
    return n.name+' arrived with you at '+w.rooms[p.location].name+'.'


def validate(data):
    rooms={r['id'] for r in data.get('room',[])};npcs={n['id'] for n in data.get('npc',[])};issues=[]
    for q in data.get('quest',[]):
        e=q.get('escort')
        if not e:continue
        if (not isinstance(e,dict) or e.get('mode') not in ('follow','lead') or e.get('npc') not in npcs or e.get('destination') not in rooms):
            issues.append(q['id']+': choose an escort mode, an existing NPC and a destination room')
    return issues
