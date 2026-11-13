"""Selected quest compass: next legal exit, never a guessed compass bearing."""
from engine import knowledge, quest_progress, frontiers, local_visibility

MAX_SELECTED = 8


def selected(world, player):
    active=player.progress.get('quests',{})
    source=player.progress.get('selected_quests',[qid for qid,status in active.items() if status=='active'])
    return [qid for qid in dict.fromkeys(source)
            if qid in world.quests and player.progress.get('quests', {}).get(qid) == 'active'][:MAX_SELECTED]


def command(ctx, args, remove=False):
    from engine.item_catalog import choose
    w,p=ctx.world,ctx.player
    if remove and args.strip().lower()=='all':
        chosen=selected(w,p)
        p.progress['selected_quests']=[]
        from engine import escorts
        for key in chosen:
            if w.quests[key].get('escort'):escorts.return_to_start(w,p,w.quests[key])
        return 'Quest compass cleared.'
    pool=selected(w,p) if remove else [qid for qid in knowledge.accepted(w,p) if p.progress['quests'][qid]=='active']
    q=choose([w.quests[i] for i in pool],args,missing='Choose an accepted, active quest from your journal.')
    chosen=selected(w,p)
    if remove: chosen.remove(q['id'])
    elif q['id'] not in chosen:
        if len(chosen)>=MAX_SELECTED:return 'Track at most eight quests. Untrack one first.'
        chosen.append(q['id'])
    p.progress['selected_quests']=chosen
    if q.get('escort'):
        from engine import escorts
        if remove:escorts.return_to_start(w,p,q)
        else:escorts.meet(w,p,q)
    return ('Stopped tracking ' if remove else 'Tracking ')+q['name']+'.'


def waypoint(ctx, args):
    from engine.item_catalog import choose
    world, player = ctx.world, ctx.player
    if args.strip().casefold()=='clear':
        player.progress.pop('globe_destination',None)
        return 'Globe destination cleared.'
    places=knowledge.ids(world,player,'rooms')
    target=choose([{'id':rid,'name':world.rooms[rid].name} for rid in places if rid in world.rooms], args,
                  missing='Select a location you have explored or learned about.')
    player.progress.pop('selected_travel_pin',None)
    player.progress['globe_destination']=target['id']
    return 'Compass destination set. '+route_text(world,player,target['id'])


def targets(world, player, q):
    from engine.quest_next_stop import next_stop
    if q.get('escort') and not player.progress.get('escort_arrivals',{}).get(q['id']):
        from engine import escorts
        actor=escorts.companion(world,player,q)
        joined=player.progress.get('escort_party',{}).get('quest')==q['id']
        target=q['escort']['destination'] if joined else escorts.start_room(world,q)
        if target:knowledge.teach(world,player,{'rooms':[target]})
        return [target] if target in world.rooms else []
    objective=next_stop(world,player,q)
    if objective:return objective[0]
    pending=[rid for rid in q.get('visit_rooms', []) if rid in world.rooms and not quest_progress.count(player,q,'visits',rid)]
    if pending:return pending
    # A witness's current remote position is never exposed. Only an explicitly
    # disclosed authored location can be used; other objectives stay in journal.
    for nid in q.get('talk_to', []):
        if quest_progress.count(player,q,'talks',nid):continue
        rid=world.npcs.get(nid,{}).get('location')
        if rid in knowledge.ids(world,player,'rooms'):return [rid]
        return []
    known=knowledge.ids(world,player,'rooms')
    for witness in q.get('witnesses',[]):
        if quest_progress.witnessed(player,q,witness):continue
        if not quest_progress.count(player,q,'actions','read:'+witness['read_item']):
            rid=world.items.get(witness['read_item'],{}).get('location')
        else:rid=world.npcs.get(witness['npc'],{}).get('location')
        if rid in known:return [rid]
    for action,n in q.get('actions',{}).items():
        if quest_progress.count(player,q,'actions',action)>=n:continue
        verb,_,target=action.partition(':')
        table={'read':world.items,'gather':getattr(world,'resources',{}),'cook':getattr(world,'recipes',{}),'craft':getattr(world,'recipes',{})}.get(verb,{})
        rid=table.get(target,{}).get('location')
        if rid in known:return [rid]
    for nid,n in q.get('kills',{}).items():
        if quest_progress.count(player,q,'kills',nid)>=n:continue
        spawner=world.npcs.get(nid,{})
        rid=spawner.get('spawn_room') or spawner.get('location')
        if rid in known:return [rid]
    from collections import Counter
    carried=Counter(player.inventory)
    if (any(carried[i]<n for i,n in q.get('required_items',{}).items())
        or any(quest_progress.count(player,q,'kills',i)<n for i,n in q.get('kills',{}).items())
        or any(quest_progress.count(player,q,'actions',i)<n for i,n in q.get('actions',{}).items())
        or any(not quest_progress.witnessed(player,q,row) for row in q.get('witnesses',[]))):
        return []
    rid=q.get('turn_in_room')
    return [rid] if rid in world.rooms else []


def _first_steps(world, player, targets):
    """One actor-aware search; prefer trails only among equally short legal routes."""
    from heapq import heappop, heappush
    from itertools import count
    from engine import geology_impacts, locks, trail_guidance
    start=player.location
    if start not in world.rooms or not targets:return {}
    todo=set(targets);answers={};serial=count()
    pending=[(0,0,next(serial),start,None)];best={start:(0,0)}
    details=getattr(world,'room_details',{})
    hazards=geology_impacts.route_sources(world)
    lock_index=locks.index(world)
    boat=any(world.items.get(i,{}).get('boat') for i in player.inventory)
    while pending and todo:
        distance,off_trail,_,rid,first=heappop(pending)
        if best[rid]!=(distance,off_trail):continue
        if rid in todo:
            answers[rid]=(first,distance);todo.remove(rid)
            if not todo:break
        check=(bool(details.get(rid,{}).get('gates')) or rid in hazards
               or bool(lock_index.get(rid))
               or any(details.get(dest,{}).get('property_unit_id') for dest in world.rooms[rid].exits.values()))
        for di,dest in world.rooms[rid].exits.items():
            if dest not in world.rooms:continue
            if frontiers.path_blocked(world,rid,di,dest,player,check,lock_index,hazards,boat):continue
            score=(distance+1,off_trail+int(not trail_guidance.marked(details,rid,di,dest)))
            if dest in best and best[dest]<=score:continue
            best[dest]=score
            heappush(pending,(*score,next(serial),dest,di if first is None else first))
    return answers


def guidance(world, player):
    knowledge.sync(world,player)
    quests=[world.quests[qid] for qid in selected(world,player)]
    from engine.quest_next_stop import next_stop
    objectives={q['id']:next_stop(world,player,q) for q in quests}
    destinations={q['id']:(objectives[q['id']][0] if objectives[q['id']] else targets(world,player,q)) for q in quests}
    dark=local_visibility.blind(world,player)
    places={rid for values in destinations.values() for rid in values}
    waypoint=player.progress.get('globe_destination')
    if waypoint not in knowledge.ids(world,player,'rooms') or waypoint not in world.rooms:waypoint=None
    if waypoint:places.add(waypoint)
    steps={} if dark else _first_steps(world,player,places)
    rows=[]
    for q in quests:
        wanted=destinations[q['id']]
        row=dict(id=q['id'],name=q['name'],target=None,direction=None,status='journal')
        if q.get('escort') and not player.progress.get('escort_arrivals',{}).get(q['id']):
            from engine import escorts
            row['objective']=escorts.report(world,player,q)
            companion,party=escorts.pair(world,player)
            if companion and party['id']==q['id'] and q['escort']['mode']=='follow':
                di=escorts.next_direction(world,player,companion,q)
                if di:
                    rid=q['escort']['destination']
                    row.update(status='travel',direction=di,target={'id':rid,'name':world.rooms[rid].name})
                    rows.append(row);continue
        if objectives[q['id']]:row['objective']=objectives[q['id']][1]
        if wanted:
            if dark:
                rid=player.location if player.location in wanted else wanted[0]
                row['target']={'id':rid,'name':world.rooms[rid].name}
                row['status']='here' if rid==player.location else 'dark'
                rows.append(row)
                continue
            reachable=[rid for rid in wanted if rid in steps]
            rid=min(reachable,key=lambda rid:steps[rid][1]) if reachable else wanted[0]
            row['target']={'id':rid,'name':world.rooms[rid].name}
            row['status']='blocked' if rid not in steps else 'here' if steps[rid][1]==0 else 'travel'
            if rid in steps:row['direction']=steps[rid][0]
        rows.append(row)
    if player.progress.get('selected_travel_pin'):
        from engine import travel_pins
        saved=travel_pins.records(world,player)
        guidance=travel_pins.guidance(world,player,travel_pins._selected(player,saved))
        if guidance:rows.append(dict(**guidance,travel_pin=True))
    if waypoint:
        step=steps.get(waypoint)
        status='here' if waypoint==player.location else 'dark' if dark else 'travel' if step else 'blocked'
        rows.append(dict(waypoint=True,name='Globe destination',target={'id':waypoint,'name':world.rooms[waypoint].name},
                         direction=step[0] if step else None,status=status))
    return rows


def pin(world, player, rid, _known=None):
    if rid not in (_known if _known is not None else knowledge.ids(world,player,'rooms')):raise ValueError('That location has not been learned.')
    from engine.coordinates import project
    room=world.rooms[rid];details=getattr(world,'room_details',{}).get(rid,{})
    # No layout inference from secret rooms: a learned pin may have missing anchors.
    xyz=tuple(getattr(room,k,None) for k in ('map_x','map_y','map_z'))
    local=all(type(v) is int for v in xyz)
    coordinates=project(details,xyz if local else (0,0,0))
    survey=details.get('tile_position')
    if survey and coordinates['world'] is None:
        coordinates['world']=dict(x=survey['x'],y=survey['y'],z=survey['z'],units='m')
    if not local:coordinates['local']=None
    return dict(id=rid,name=room.name,x=xyz[0] if local else None,y=xyz[1] if local else None,
                z=xyz[2] if local else None,coordinates=coordinates,**({'planet':{k:(survey or details['planet'])[k] for k in ('lat','lon')}} if survey or details.get('planet') else {}),tile_position=survey,visited=rid in player.explored_rooms or rid==player.location)


def packet(world, player):
    k=knowledge.sync(world,player)
    unvisited=set(k['rooms'])-set(player.explored_rooms)-{player.location}
    return dict(type='player_navigation',selected=selected(world,player),quests=guidance(world,player),
                pins=[pin(world,player,rid,_known=set(k['rooms'])) for rid in sorted(unvisited) if rid in world.rooms],
                note=('Darkness conceals routes. Known destinations are retained; try a direction or use a working lantern.' if local_visibility.blind(world,player) else 'Learned markers do not reveal unexplored terrain. Compass shows the next traversable exit, not a straight-line bearing.'))


def route_text(world, player, query):
    from engine.item_catalog import choose
    known=knowledge.ids(world,player,'rooms')
    target=choose([dict(id=rid,name=world.rooms[rid].name) for rid in known],query,
                  missing='That place has not been learned. Ask a nearby person or review accepted quests.')
    if local_visibility.blind(world,player):
        if target['id']==player.location:return 'You have arrived at '+target['name']+'.'
        return 'Darkness conceals the next step toward '+target['name']+'. Try a direction or use a working lantern.'
    step=_first_steps(world,player,{target['id']}).get(target['id'])
    if step is None:return 'No traversable route to '+target['name']+' is currently available.'
    if not step[1]:return 'You have arrived at '+target['name']+'.'
    return 'Next step toward '+target['name']+': go '+step[0].capitalize()+'.'
