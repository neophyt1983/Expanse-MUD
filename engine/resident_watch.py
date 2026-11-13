"""A player's observation of one resident, independent of the player's position."""
from collections import Counter
from engine import chronicles, living, life_stages, npc_activity, relationships, worldtime

KEY='resident_watches'


def records(world):
    return getattr(world,'living_state',{}).get(KEY,{})


def _entry(world, ident):
    row=records(world).get(ident)
    return row if row and row['observers'] else None


def note(world, participants, text):
    participants=set(participants)
    for ident in participants:
        actor=world.entities.get(ident)
        if actor and actor.is_player:text=text.replace(actor.name,'a visiting adventurer')
    for ident in participants:
        row=_entry(world,ident)
        if row:
            actor=world.entities.get(ident)
            room=world.rooms.get(actor.location) if actor else None
            row['events'].append([living.state(world)['minute'],room.name if room else row['state']['place'],text])


def _state(world, actor):
    d=world.npcs.get(actor.source_def,{})
    profile=relationships.profile(world,actor)
    phase=life_stages.for_entity(world,actor,profile)
    home=world.rooms.get(actor.progress.get('home_room') or d.get('home_room'))
    room=world.rooms.get(actor.location)
    items=Counter(world.items.get(i,{}).get('name','an item') for i in actor.inventory)
    return dict(place=room.name if room else '',activity=npc_activity.activity(world,actor)['label'],
                hp=actor.hp,gold=actor.gold,age=int(phase['age_years']),stage=phase['stage'],
                occupation=d.get('occupation','').replace('_',' '),home=home.name if home else '',
                sanity=actor.progress.get('expedition_sanity'),expedition_memories=list(actor.progress.get('expedition_memories',{}).values()),
                alive=actor.alive,items=dict(items),injury=actor.progress.get('injury',0),
                disease=actor.progress.get('disease',0),retired=bool(actor.progress.get('retired')))


def sample(world):
    for ident,row in records(world).items():
        if not row['observers'] or row.get('ended'):continue
        actor=world.entities.get(ident)
        before=row['state']
        if not actor:
            if not row.get('absent'):
                note(world,[ident],'No longer present in the world.')
                row['absent']=True
            continue
        row.pop('absent',None)
        after=_state(world,actor)
        if after==before:continue
        if before['alive'] and not after['alive']:
            death(world,actor,'',None)
        for key,label in [('activity','Activity'),('home','Home'),('occupation','Occupation'),('stage','Life stage'),
                          ('age','Age in world years'),('hp','Health'),('injury','Injury'),('disease','Illness')]:
            if before[key]!=after[key]:note(world,[ident],f'{label} changed from {before[key] or "none"} to {after[key]}.')
        delta=after['gold']-before['gold']
        if delta:note(world,[ident],('Received ' if delta>0 else 'Spent or lost ')+str(abs(delta))+' gold.')
        for item in sorted(before['items'].keys()|after['items'].keys()):
            count=after['items'].get(item,0)-before['items'].get(item,0)
            if count:note(world,[ident],('Acquired ' if count>0 else 'Parted with ')+f'{abs(count)} × {item}.')
        if after['retired'] and not before['retired']:note(world,[ident],'Retired from work.')
        row['state']=after


def death(world,actor,cause,attacker):
    row=_entry(world,actor.id)
    if row and not row.get('ended'):
        reason=(' in combat with '+attacker.name) if attacker else (' from '+cause if cause else '')
        note(world,[actor.id],'Died'+reason+'.')
        row['ended']=True
        row['state']=_state(world,actor)
        row['state']['alive']=False


def stop(world,player):
    ident=player.progress.pop('resident_watch',None)
    row=records(world).get(ident)
    if row and player.id in row['observers']:row['observers'].remove(player.id)


def start(world, player, ident):
    actor=world.entities.get(ident)
    contacts=player.progress.get('chronicle_contacts',{})
    own=player.progress.get('observed_residents',{})
    if actor and actor.is_player:raise ValueError('Choose a resident, not a player character.')
    if not actor or (actor.location!=player.location and ident not in contacts and ident not in own):
        raise ValueError('Choose someone you have met.')
    if not actor.alive:raise ValueError('This resident has died. Open their recorded life instead.')
    book=living.state(world).setdefault(KEY,{})
    if player.progress.get('resident_watch')==ident and player.id in book.get(ident,{}).get('observers',[]):return
    stop(world,player)
    if ident not in book:
        row=book[ident]=dict(name=actor.name,events=[],observers=[],state=_state(world,actor))
        archive=chronicles.attach(world) or {}
        born=actor.progress.get('social_profile',{}).get('born_minute')
        if born is not None and (actor.spawner_key or '').startswith('birth:'):
            row['events'].append([born,'','Was born.'])
        else:
            for event in archive.get('people',{}).get(actor.source_def,[]):
                row['events'].append([event['at'],'',event['text']])
        for event in getattr(world,'living_state',{}).get('relationships',{}).get('events',[]):
            if ident not in event['participants']:continue
            text=event['text']
            for who in event['participants']:
                bystander=world.entities.get(who)
                if bystander and bystander.is_player:text=text.replace(bystander.name,'a visiting adventurer')
            row['events'].append([event['minute'],'',text])
        row['events'].sort(key=lambda x:x[0] if isinstance(x[0],int) else -10**15)
    row=book[ident]
    if not row['observers']:
        row['events'].extend(actor.progress.pop('unseen_escort_events',[]))
        row['events'].sort(key=lambda x:x[0] if isinstance(x[0],int) else -10**15)
        row['state']=_state(world,actor)
        row['events'].append([living.state(world)['minute'],row['state']['place'],'Observation began. '+row['state']['activity']+'.'])
    row['observers'].append(player.id);player.progress['resident_watch']=ident
    player.progress.setdefault('observed_residents',{})[ident]=actor.name


def view(world, player, packet):
    action=packet.get('action','view')
    ident=packet.get('resident')
    if ident is not None and (not isinstance(ident,str) or len(ident)>200):raise ValueError('Invalid resident.')
    if action=='start':start(world,player,ident)
    elif action=='stop':stop(world,player)
    elif action!='view':raise ValueError('Unknown observation action.')
    selected=player.progress.get('resident_watch')
    known=dict(player.progress.get('observed_residents',{}))
    choices=dict(known)
    for key,person in player.progress.get('chronicle_contacts',{}).items():
        if key in world.entities:choices[key]=person['name']
    for actor in world.entities_in_room(player.location):
        if not actor.is_player:choices[actor.id]=actor.name
    target=ident or selected
    row=records(world).get(target) if target in known else None
    result=dict(type='resident_watch',choices=sorted(choices.items(),key=lambda p:p[1]),selected=selected,
                resident=target if row else None,events=[],before=0)
    if row:
        sample(world)
        cursor=packet.get('before')
        if cursor is not None and type(cursor) is not int:raise ValueError('Invalid page.')
        end=len(row['events']) if cursor is None else min(max(0,cursor),len(row['events']))
        offset=max(0,end-40)
        result.update(name=row['name'],state=row['state'],ended=row.get('ended',False),
                      absent=row.get('absent',False),before=offset,total=len(row['events']))
        actor=world.entities.get(target)
        if actor and actor.alive and not row.get('ended') and target==selected and player.id in row['observers']:
            from engine.visual_mapping import actor_portrait
            result['portrait']=actor_portrait(world,actor,player.id)
            if actor.location in world.rooms:result['scene']=scene(world,player,actor,result['portrait'])
        for minute,place,text in reversed(row['events'][offset:end]):
            if minute is None or minute<0:stamp=chronicles.date_text(minute,worldtime.initial_minute(world.metadata)) if minute is not None else 'Date unrecorded'
            else:
                d=worldtime.date(minute);stamp=f"Y{d['year']} · M{d['month']} · D{d['day']} · {d['hour']:02d}:{d['minute']:02d}"
            result['events'].append([stamp,place,text])
    return result


def scene(world, player, actor, portrait):
    from engine import local_visibility, mapping, pixel_art, visual_mapping
    from engine.describe import resolve_description
    if not hasattr(world,'_compiled_map'):
        world._compiled_map=mapping.compile_map(mapping.room_records(world))
    compiled=world._compiled_map
    sight=local_visibility.sight(world,actor,compiled)
    center=actor.location
    nearby=sight['rooms']|{center}
    byid,positions,_=compiled
    visual=visual_mapping.render_visual({rid:byid[rid] for rid in nearby},positions,center,nearby,radius=1,visited={center})
    visual_mapping.apply_world_surfaces(world,visual)
    people=[n for n in world.entities_in_room(center) if not n.is_player and n.id!=actor.id]
    people.sort(key=lambda n:(n.name,n.id))
    visual['actors']=[portrait]+[visual_mapping.actor_portrait(world,n,player.id) for n in people[:4]]
    pixel_art.apply(world,visual)
    from engine import climate
    room=world.rooms[center]
    result=dict(weather=climate.conditions(world,center),center=center,name=room.name,description=resolve_description(room,world,actor),
                context=visual['context']['label'],floor=visual['floor'],tiles=visual['tiles'],
                actors=visual['actors'],others=[n.name for n in people[:8]],other_count=len(people),
                daylight=sight['daylight'],lit=sight['light_source'],pixel_assets=visual.get('pixel_assets',{}))
    commute=getattr(world,'_commute_routes',{}).get(actor.id)
    if commute and commute[1] and commute[1][0][0]==center and commute[0] in world.rooms:
        result['heading_to']=world.rooms[commute[0]].name
    return result
