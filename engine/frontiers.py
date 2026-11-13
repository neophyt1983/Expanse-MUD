"""Faction diplomacy, gate-aware travel, and persistent automatic populations."""
import time
from collections import Counter, deque
from engine.directions import direction


def active(world):return bool(world.metadata.get('frontiers'))

from engine.diplomacy import relation


def hostile(world,actor,target):
    if not actor.group_id:return False
    room=getattr(world,'room_details',{}).get(actor.location,{})
    if room.get('truce'):return False
    from engine import society
    if society.enabled(world):return society.friendliness(world,actor,target)<25
    return relation(world.groups.get(actor.group_id),target.group_id)=='hostile'

DIAGONALS = {ns+ew:(ns,ew) for ns in ('north','south') for ew in ('east','west')}


def diagonal_blocked(world,source,direction,destination,actor,lock_index=None,hazards=None,boat=None):
    """An open-country diagonal needs both unobstructed sides of its corner."""
    details=getattr(world,'room_details',{})
    for first,second in (DIAGONALS[direction],DIAGONALS[direction][::-1]):
        via=world.rooms[source].exits.get(first)
        if via not in world.rooms or world.rooms[via].exits.get(second)!=destination:
            return 'There is no clear diagonal passage here.'
        for rid,di,target in ((source,first,via),(via,second,destination)):
            if boat is False and details.get(target,{}).get('requires_boat'):
                return 'Open water cuts across this diagonal. You need a boat.'
            if hazards is not None and rid not in hazards and not lock_index.get(rid) and not details.get(rid,{}).get('gates') and not details.get(target,{}).get('property_unit_id'):
                continue
            reason=blocked(world,rid,di,actor,lock_index=lock_index)
            if reason:return reason
    return ''


def path_blocked(world,source,direction,target,player,check,lock_index,hazards,boat):
    details=getattr(world,'room_details',{})
    if not boat and details.get(target,{}).get('requires_boat'):return True
    if check or (source,direction) in getattr(world,"_street_checks",{}):return bool(blocked(world,source,direction,player,lock_index=lock_index))
    if direction in DIAGONALS and details.get(source,{}).get('open_country'):
        return bool(diagonal_blocked(world,source,direction,target,player,lock_index,hazards,boat))
    return False


def blocked(world,room_id,exit_name,player=None,*,lock_index=None):
    from engine import geology_impacts
    di=direction(exit_name)
    from engine import locks
    rules=getattr(world,"_street_checks",{}).get((room_id,di))
    if rules:
        reasons=[blocked(world,src,edge,player,lock_index=lock_index) for src,edge in rules]
        if all(reasons):return reasons[0]
    physical=locks.blocked(world,room_id,di,player,lock_index=lock_index)
    if physical:return physical
    reason=geology_impacts.route_blocked(world,room_id,di,actor=player)
    if reason:return reason
    destination=world.rooms.get(room_id).exits.get(di) if room_id in world.rooms else None
    if destination and getattr(world,'room_details',{}).get(destination,{}).get('requires_boat'):
        if player is None or not any(world.items.get(i,{}).get('boat') for i in player.inventory):
            return 'You need a boat to enter open water.'
    if destination and di in DIAGONALS and getattr(world,'room_details',{}).get(room_id,{}).get('open_country'):
        reason=diagonal_blocked(world,room_id,di,destination,player,lock_index=lock_index)
        if reason:return reason
    from engine import property_interiors
    reason=property_interiors.blocked(world,player,room_id,di,destination)
    if reason:return reason
    gate=getattr(world,'room_details',{}).get(room_id,{}).get('gates',{}).get(di)
    if not gate:return ''
    from engine.living import state,progress
    flags=state(world).get('flags',{})
    if gate.get('world_flag') and flags.get(gate['world_flag'])==gate.get('value',True):return ''
    if gate.get('quest') and player and progress(player)['quests'].get(gate['quest'])=='complete':return ''
    if gate.get('guard_npc'):
        guard=next((n for n in world.entities_in_room(room_id) if n.source_def==gate['guard_npc'] and n is not player),None)
        if not guard:return ''
        return gate.get('message') or guard.name+' blocks the way.'
    return gate.get('message','This passage is locked.')

def path(world,start,target,player=None,include_locked=False,*,allowed=None):
    if start not in world.rooms or target not in world.rooms:return None
    q=deque([start]);previous={start:None}
    rooms=world.rooms;details=getattr(world,'room_details',{})
    from engine import geology_impacts
    hazard_sources=geology_impacts.route_sources(world) if not include_locked else frozenset()
    boat=player is not None and any(world.items.get(i,{}).get('boat') for i in player.inventory)
    from engine import locks
    lock_index=locks.index(world) if not include_locked else {}
    while q:
        current=q.popleft()
        if current==target:
            steps=[]
            while previous[current] is not None:
                before,di=previous[current];steps.append((before,di,current));current=before
            return list(reversed(steps))
        check_passages=bool(details.get(current,{}).get('gates')) or current in hazard_sources or any(details.get(dest,{}).get('property_unit_id') for dest in rooms[current].exits.values())
        check_passages=check_passages or bool(lock_index.get(current))
        for di,dest in rooms[current].exits.items():
            if dest not in rooms or dest in previous or (allowed is not None and dest not in allowed):continue
            if not include_locked and path_blocked(world,current,di,dest,player,check_passages,lock_index,hazard_sources,boat):continue
            previous[dest]=(current,di);q.append(dest)
            # The first discovery fixes this destination's BFS predecessor.
            # No remaining node can improve it or change the tie-breaking.
            if dest==target:
                q.clear();q.append(dest);break
    return None

def route(world,player,query):
    if player.is_player:
        from engine.navigation import route_text
        return route_text(world,player,query)
    from engine.living import choose
    try:obj=choose([dict(id=r.id,name=r.name) for r in world.rooms.values()],query)
    except ValueError:
        obj=choose([dict(id=e.location,name=e.name) for e in world.entities.values() if e.alive and not e.is_player],query)
    target=obj['id'];steps=path(world,player.location,target,player)
    if steps==[]:return 'You are already here.'
    if steps:return f"Next step toward {obj['name']}: go {steps[0][1]}. ({len(steps)} steps remaining.)"
    planned=path(world,player.location,target,player,True)
    if planned:
        gate=next((s for s in planned if blocked(world,s[0],s[1],player)),None)
        if gate:
            why=blocked(world,gate[0],gate[1],player)
            return f"Route to {obj['name']} is locked at {world.rooms[gate[0]].name}, {gate[1]}: {why}"
        return 'No traversable route is available.'
    return 'No route is defined. This is a creator topology error.'

def population(world):
    if not active(world):return []
    from engine.commands import _try_spawn
    # Ephemeral counts include roaming NPCs and are rebuilt after deaths, births,
    # or restored saves. Successful spawns update this same refresh snapshot.
    alive_counts=Counter(e.spawner_key for e in world.entities.values()
                         if e.alive and not e.is_player and e.spawner_key)
    messages=[]
    for room in getattr(world,"spawner_rooms",world.rooms).values():
        for index,spawner in enumerate(room.spawners):
            if not spawner.get('automatic'):continue
            # One refresh can fill the initial population, with later births respecting cooldown.
            for _ in range(max(1,int(spawner.get('count',1)))):
                e=_try_spawn(world,room,spawner,index,trigger='entry', alive_counts=alive_counts)
                if not e:break
                messages.append((room.id,e.name+' arrives.'))
    return messages

def fight(world):
    if not active(world):return []
    from engine.commands import effective_attack,effective_defense,_on_npc_death,_remove_entity
    from engine.living import on_hit
    now=time.monotonic()
    if now<getattr(world,'next_faction_fight',0):return []
    world.next_faction_fight=now+5;messages=[]
    # One aggressor per victim per round, giving players time to retreat.
    targeted=set()
    for actor in list(world.entities.values()):
        if not actor.alive or actor.is_player or actor.progress.get('companion_owner') or not world.npcs.get(actor.source_def,{}).get('combatant'):continue
        from engine import mortality, living, society
        if actor.progress.get('restrained_until',0)>living.state(world)['minute']:continue
        candidates=[e for e in world.entities_in_room(actor.location) if e.id!=actor.id and e.id not in targeted and hostile(world,actor,e)]
        if not candidates:continue
        target=candidates[0];targeted.add(target.id)
        from engine import combat
        try:combat.validate(world,actor,target);combat.ammunition(world,actor)
        except ValueError:continue
        messages.append((actor.location,combat.strike(world,actor,target,counter=False)))
    return messages

def capture_spawners(world):
    now=time.monotonic();result={}
    for key,s in world.spawner_state.items():
        result[key]={**s,'elapsed':None if s.get('last_spawn_at') is None else max(0,now-s['last_spawn_at'])}
        result[key].pop('last_spawn_at',None)
    return result

def restore_spawners(world,saved):
    now=time.monotonic()
    for key,s in saved.items():
        try:rid,index=key.rsplit(':',1);spec=world.rooms[rid].spawners[int(index)]
        except (ValueError,KeyError,IndexError):continue
        elapsed=s.get('elapsed');world.spawner_state[key]={**s,'last_spawn_at':None if elapsed is None else now-max(0,elapsed)}

def audit(data,metadata):
    from engine.living import validate
    rooms={r['id']:r for r in data['room']};issues=[]
    for r in rooms.values():
        for di,g in r.get('gates',{}).items():
            if di not in r.get('exits',{}):issues.append(r['id']+': gate has no physical exit '+di)
            if g.get('guard_npc') and g['guard_npc'] not in {n['id'] for n in data.get('npc',[])}:issues.append(r['id']+': unknown gate guard')
            if not (g.get('world_flag') or g.get('quest') or g.get('guard_npc')):issues.append(r['id']+': gate needs an unlock condition')
    group_ids={g['id'] for g in data.get('group',[])}
    quest_ids={q['id'] for q in data.get('quest',[])}
    for group in data.get('group',[]):
        for other,value in group.get('relations',{}).items():
            if other not in group_ids|{'unaffiliated','*'}:issues.append(group['id']+': unknown relationship faction '+other)
            if value not in ('allied','tolerated','neutral','hostile'):issues.append(group['id']+': unknown relationship state '+str(value))
    managed={s.get('npc') for r in rooms.values() for s in r.get('spawners',[])}
    for npc in data.get('npc',[]):
        if npc.get('spawn_managed') and npc['id'] not in managed and not any(n.get('summons')==npc['id'] for n in data.get('npc',[])):issues.append(npc['id']+': managed NPC has no spawner')
        for rid in npc.get('patrol_route',[]):
            if rid not in rooms:issues.append(npc['id']+': patrol room missing '+rid)
    for r in rooms.values():
        for gate in r.get('gates',{}).values():
            if gate.get('quest') and gate['quest'] not in quest_ids:issues.append(r['id']+': gate quest missing '+gate['quest'])
    # A route must exist in the physical graph even for a presently locked destination.
    roots=[metadata.get('start_room')]+[g.get('start_room') for g in data.get('group',[]) if g.get('visibility')=='playable']
    for root in filter(None,roots):
        if root not in rooms:continue
        reached={root};q=deque([root])
        while q:
            for dest in rooms[q.popleft()].get('exits',{}).values():
                if dest in rooms and dest not in reached:reached.add(dest);q.append(dest)
        missing=set(rooms)-reached
        if missing:issues.append(f'{root}: unreachable destinations: '+', '.join(sorted(missing)))
    return issues


def home(world,player):
    from engine.loader import start_room_for
    from engine import settlements, geology_impacts
    candidates=[]
    if settlements.enabled(world):
        u=settlements.init(world)['units'].get(player.progress.get('home_property'))
        if u and player.id == (u['tenant'] or u['owner']):
            from engine import property_interiors
            rid=property_interiors.room_id(u['id'])
            if rid in getattr(world,'_property_generated_rooms',set()) and not property_interiors.blocked(world,player,u['room'],None,rid):candidates.append(rid)
            if not geology_impacts.room_unusable(world,u['room']):candidates.append(u['room'])
    candidates.extend([world.groups.get(player.group_id,{}).get('start_room'),start_room_for(world),player.location])
    # Recovery is deliberate relocation, but must never place someone in an unusable building.
    candidates.extend(world.rooms)
    return next((rid for rid in candidates if rid in world.rooms and not geology_impacts.room_unusable(world,rid)),None)
