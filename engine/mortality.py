"""Local traffic hazards, witnessed crime, guards and persistent mortality."""
import random
from engine import living, society

LAWS = dict(enabled=False, authority='', arrest_room='', fine=5,
            guard_radius=1, traffic_reduction=0.8)
TRAFFIC = dict(enabled=False, accident_chance=0.01, damage=12,
               warning='Traffic passes here; watch for horses and carriages.')


def state(w):
    return living.state(w).setdefault('mortality', dict(deaths={}, incidents=[], wanted={}, last=-1))


def player_death_mode(w):
    return w.metadata.get('player_death', 'revival')


def record_death(w, e, cause='injury', attacker=None):
    if e.alive: return
    from engine import spell_life
    if spell_life.magical(e):
        spell_life.retire(w,e.id)
        return
    s=state(w)
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.death(w,e,cause,attacker)
    # Each permanent identity dies once; revived players can die again later.
    if e.progress.get('death_recorded'): return
    e.progress['death_recorded']=True
    owner=w.entities.get(e.progress.get('companion_owner'))
    from engine import companion_union
    if not companion_union.preserve_death(w,e) and owner:owner.progress['companions']=[c for c in owner.progress.get('companions',[]) if c['id']!=e.id]
    s['deaths'][e.id]=dict(id=e.id,name=e.name,location=e.location,
        minute=living.state(w)['minute'],cause=cause,attacker=attacker.id if attacker else None)
    if e.is_player and player_death_mode(w)=='permanent': e.progress['permanently_dead']=True
    from engine import relationships as rel
    rs=rel.state(w)
    rs['pregnancies'].pop(e.id,None)
    rs['proposals']={k:v for k,v in rs['proposals'].items() if e.id not in (v['from'],v['to'])}
    for row in rs['bonds'].values():
        if e.id in row['participants']:
            row.setdefault('deceased',[])
            if e.id not in row['deceased']:row['deceased'].append(e.id)
            row['history'].append(dict(action='death',actor=e.id,minute=living.state(w)['minute']))
            rel.event(w,e.name+' died. Their shared history is retained.',row['participants'])
    from engine import population
    population.on_death(w,e)


def environmental_damage(w,actor,amount,cause,event_id=None):
    """Apply environmental injury without inventing an attacker or combat rewards.

    Zero bypasses Entity.take_damage's intentional combat minimum. NPC identity,
    encounter and spawner cleanup happens once, including in non-society worlds.
    """
    if not actor.alive or amount<=0:return 0
    amount=int(amount)
    if amount<=0:return 0
    before=actor.hp
    actor.take_damage(amount,defense=0,cause=cause,kind='environment')
    damage=before-actor.hp
    if not damage:return 0
    now=living.state(w)['minute']
    actor.progress['geology_last_hit_minute']=now
    if actor.is_player:w.dirty_players=getattr(w,'dirty_players',set())|{actor.id}
    text=actor.name+' suffers '+str(damage)+' damage from '+str(cause)+'.'
    if not actor.alive:
        record_death(w,actor,cause)
        text+=' '+actor.name+' dies.'
        if not actor.is_player and not actor.progress.get('_environmental_death_resolved'):
            actor.progress['_environmental_death_resolved']=True
            from engine import commands as cmd
            from engine import spell_life
            if actor.source_def and not actor.spawner_key and not spell_life.magical(actor):w.killed_npcs.add(actor.source_def)
            room=w.rooms.get(actor.location)
            if room:
                cmd._on_npc_death(w,room,actor,defer=True)
                mode=cmd._corpse_mode_for(w,actor)
                if mode=='disappear':cmd._remove_entity(w,room,actor.id)
                elif mode=='timed':
                    import time
                    actor.corpse_expires_at=time.monotonic()+cmd._corpse_ttl(w,actor)
    w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(actor.location,text)])[-500:]
    return damage


def guards(w, room):
    from engine import livelihoods, city_defense
    cfg={**LAWS,**living.details(w,room).get('laws',{})}
    if not cfg['enabled']:return []
    radius=min(1,max(0,cfg['guard_radius']))
    locations={room}|(set(w.rooms[room].exits.values()) if radius else set())
    return [e for rid in locations if rid in w.rooms for e in w.entities_in_room(rid)
            if not e.is_player and (city_defense.is_guard(w,e) if city_defense.enabled(w) else w.npcs.get(e.source_def,{}).get('profession')=='guard') and livelihoods.on_shift(w,e)
            and (not cfg['authority'] or e.group_id==cfg['authority'])]


def assault(w, actor, victim):
    if not society.enabled(w):return
    room=actor.location;cfg={**LAWS,**living.details(w,room).get('laws',{})}
    witnesses=guards(w,room)
    if not witnesses:return  # No omniscient policing.
    victim_definition=w.npcs.get(victim.source_def,{})
    from engine import relationships
    if victim_definition.get('aggressive') and not relationships.sentient(w,victim):return
    if any(society.friendliness(w,actor,g)>=50 for g in witnesses) and (society.friendliness(w,actor,victim)<25 or victim_definition.get('aggressive')):return
    # A guard defending against an existing wanted attacker is not a new crime.
    wanted=state(w)['wanted']
    if victim.id in wanted:return
    # Lawful guards can defend their jurisdiction from hostile invaders.
    if not actor.is_player and w.npcs.get(actor.source_def,{}).get('profession')=='guard' and society.friendliness(w,actor,victim)<25:return
    report_crime(w,actor,'assault',victim.id,witnesses)


def report_crime(w,actor,kind,victim,witnesses,*,source=None):
    """Retain an actual witnessed act for later judicial review."""
    from engine import relationships
    if not society.enabled(w) or not relationships.sentient(w,actor):return
    cfg={**LAWS,**living.details(w,actor.location).get('laws',{})}
    witnesses=[e for e in witnesses if e.alive and e.id!=actor.id and relationships.sentient(w,e)]
    if not cfg['enabled'] or not witnesses:return
    minute=living.state(w)['minute'];ids=[e.id for e in witnesses]
    evidence=dict(kind=kind,actor=actor.id,victim=victim,room=actor.location,minute=minute,witnesses=ids)
    if isinstance(source,dict):
        from copy import deepcopy
        evidence['source']=deepcopy(source)
    current=state(w)['wanted'].get(actor.id,{})
    previous=current.get('evidence',[]) if current.get('authority')==cfg['authority'] else []
    state(w)['wanted'][actor.id]=dict(room=actor.location,authority=cfg['authority'],victim=victim,
        reported=minute,kind=kind,witnesses=ids,evidence=(previous+[evidence])[-8:])
    state(w)['incidents']=(state(w)['incidents']+[evidence])[-500:]


def advance(w, rng=random.random):
    if not society.enabled(w):return []
    s=state(w);now=living.state(w)['minute'];messages=[]
    if s['last']==now:return messages
    s['last']=now
    # Local guards intervene only where they can reach and witness a suspect.
    for pid, report in list(s['wanted'].items()):
        suspect=w.entities.get(pid)
        if suspect is None or not suspect.alive:continue
        from engine import regional_world, relationships
        if regional_world.enabled(w) and not relationships.sentient(w,suspect):
            del s['wanted'][pid]
            continue
        cfg={**LAWS,**living.details(w,suspect.location).get('laws',{})}
        officers=[g for g in guards(w,suspect.location) if g.id!=pid and g.group_id==report['authority']]
        if not officers:continue
        guard=officers[0];origin=suspect.location
        if guard.location!=origin:
            from engine import npc_attention
            if npc_attention.paused(w,guard):continue
            from engine import frontiers
            route=frontiers.path(w,guard.location,origin)
            if not route or len(route)>1:continue
            w.move_entity(guard.id,origin)
        # Arrest is an attempt, not guaranteed protection or an instant death.
        chance=max(.1,min(.95,(guard.attack+guard.defense+1)/(guard.attack+guard.defense+suspect.attack+suspect.defense+2)))
        if rng()>=chance:
            messages.append((origin,guard.name+' tries to restrain '+suspect.name+', but fails.'));continue
        from engine import regional_world, city_justice
        already_confined = regional_world.enabled(w) and city_justice.confined(w,suspect)
        if regional_world.enabled(w) and city_justice.apprehend(w,suspect,guard,report):
            del s['wanted'][pid]
            if not already_confined:
                messages.append((origin,guard.name+' takes '+suspect.name+' into custody pending a magistrate hearing. No verdict has been issued.'))
            continue
        fine=min(suspect.gold,max(0,cfg['fine']));suspect.gold-=fine;guard.gold+=fine
        if cfg['arrest_room'] in w.rooms:w.move_entity(suspect.id,cfg['arrest_room'],forced=True)
        suspect.progress['restrained_until']=now+2
        del s['wanted'][pid]
        from engine import gazette
        gazette.record(w,origin,'Watch',guard.name+' made an arrest and collected a fine of '+str(fine)+' gold.',byline='Watch desk')
        messages.append((origin,guard.name+' restrains '+suspect.name+f' and collects a {fine}-gold fine.'))
    # An actual traffic actor must be present; quiet rooms have no traffic roll.
    for vehicle in list(w.entities.values()):
        if vehicle.is_player or not vehicle.alive:continue
        from engine import civic_program
        if civic_program.carriage_stop(w,vehicle)==vehicle.location:continue
        hazard={**TRAFFIC,**w.npcs.get(vehicle.source_def,{}).get('traffic',{})}
        if not hazard['enabled']:continue
        room=vehicle.location;cfg={**LAWS,**living.details(w,room).get('laws',{})}
        chance=hazard['accident_chance']
        if guards(w,room):chance*=1-cfg['traffic_reduction']
        bystanders=[e for e in w.entities_in_room(room) if e.id!=vehicle.id and not w.npcs.get(e.source_def,{}).get('traffic',{}).get('enabled')]
        if not bystanders or rng()>=chance:continue
        victim=bystanders[min(len(bystanders)-1,int(rng()*len(bystanders)))]
        damage=victim.take_damage(hazard['damage'],defense=0,source=vehicle,cause='traffic collision',kind='collision')
        living.progress(victim)['injury']=min(100,living.progress(victim)['injury']+damage)
        from engine import gazette
        gazette.record(w, room, 'Public safety', f'{vehicle.name} struck {victim.name} at {w.rooms[room].name}. '+('The collision caused an injury.' if victim.alive else 'The collision was fatal.'))
        messages.append((room,vehicle.name+' runs into '+victim.name+f', causing {damage} damage.'))
        s['incidents']=(s['incidents']+[dict(kind='traffic',actor=vehicle.id,victim=victim.id,room=room,minute=now)])[-500:]
        if not victim.alive:
            record_death(w,victim,'traffic collision',vehicle)
            if not victim.is_player:
                from engine.commands import _on_npc_death
                _on_npc_death(w,w.rooms[room],victim)
                from engine import spell_life
                if victim.source_def and not victim.spawner_key and not spell_life.magical(victim):w.killed_npcs.add(victim.source_def)
    for e in list(w.entities.values()):
        if not e.alive:record_death(w,e)
    return messages


def validate(data, meta):
    errors=[];rooms={r['id'] for r in data.get('room',[])};groups={g['id'] for g in data.get('group',[])}
    if meta.get('player_death','revival') not in ('permanent','revival'):errors.append('player_death must be permanent or revival')
    for kind,field,defaults in (('room','laws',LAWS),('npc','traffic',TRAFFIC)):
        for row in data.get(kind,[]):
            value=row.get(field,{})
            if not isinstance(value,dict):errors.append(row['id']+': invalid '+field);continue
            cfg={**defaults,**value}
            for k,default in defaults.items():
                v=cfg[k]
                ok=isinstance(v,(int,float)) and not isinstance(v,bool) if isinstance(default,float) else type(v) is type(default)
                if not ok:errors.append(row['id']+': invalid '+k)
            if field=='laws':
                if cfg['authority'] and cfg['authority'] not in groups:errors.append(row['id']+': unknown law authority')
                if cfg['arrest_room'] and cfg['arrest_room'] not in rooms:errors.append(row['id']+': unknown guard post')
                for key,lo,hi in [('fine',0,1000000),('guard_radius',0,1),('traffic_reduction',0,1)]:
                    if isinstance(cfg[key],(int,float)) and not lo<=cfg[key]<=hi:errors.append(row['id']+': invalid '+key)
            else:
                for key,lo,hi in [('accident_chance',0,1),('damage',1,1000000)]:
                    if isinstance(cfg[key],(int,float)) and not lo<=cfg[key]<=hi:errors.append(row['id']+': invalid '+key)
    return errors
