"""Opt-in physical locks. Quest gates remain independent; no global lock migration.

Creator room.locks rows are fixed fixtures, not infinitely renewable item bags.
One door definition controls both sides of the same exit pair.
"""
from engine import living
from engine.directions import direction
from collections import Counter
import shlex


def invalidate(world):
    """Call after editing lock definitions/exits in a running Creator world."""
    world._physical_lock_index=None


def index(world, *, cache=True):
    index=getattr(world,'_physical_lock_index',None)
    if index is None:
        index={}
        for origin,details in getattr(world,'room_details',{}).items():
            if origin not in world.rooms:continue
            for row in details.get('locks',[]):
                index.setdefault(origin,[]).append((origin,row))
                if row.get('direction'):
                    target=world.rooms[origin].exits.get(direction(row['direction']))
                    if target in world.rooms and origin in world.rooms[target].exits.values():
                        index.setdefault(target,[]).append((origin,row))
        if cache:world._physical_lock_index=index
    return index


def local(world, room_id):
    return index(world).get(room_id,[])


def saved(world, origin, row):
    return living.state(world).setdefault('physical_locks',{}).setdefault(origin+':'+row['id'],
        {'locked':row.get('locked',True),'contents':list(row.get('contents',[]))})


def has_key(world, actor, row):
    if not actor:return False
    keys=list(actor.inventory)
    if not actor.is_player:keys+=world.npcs.get(actor.source_def,{}).get('lock_keys',[])
    return bool(row.get('key') and row['key'] in keys)


def permitted(world, actor, row):
    return bool(row.get('public') or has_key(world,actor,row) or
        (actor.source_def and actor.source_def==row.get('owner')) or
        (actor.group_id and actor.group_id in row.get('allowed_groups',[])))


def permission_warning(world, actor, row):
    if permitted(world, actor, row):return ''
    if row.get('direction'):
        return 'You do not have permission to alter this lock. Picking it may be reported as lock tampering.'
    return ('Taking items from this container without permission is theft. Witnesses may report it. '
            'Picking the lock or putting items inside without permission may be reported as lock tampering.')


def skill(world, actor):
    default=world.npcs.get(actor.source_def,{}).get('lockpicking',0) if not actor.is_player else world.classes.get(actor.char_class,{}).get('lockpicking',0)
    value=actor.progress.get('skills',{}).get('lockpicking',default)
    return max(0,min(100,value)) if type(value) is int else 0


def door(world, room_id, exit_name, *, lock_index=None):
    destination=world.rooms[room_id].exits.get(direction(exit_name))
    for origin,row in (index(world,cache=False) if lock_index is None else lock_index).get(room_id,[]):
        di=row.get('direction')
        if not di:continue
        target=world.rooms[origin].exits.get(direction(di))
        if {origin,target}=={room_id,destination}:return origin,row
    return None


def blocked(world, room_id, exit_name, actor=None, *, lock_index=None):
    target=door(world,room_id,exit_name,lock_index=lock_index)
    if not target:return ''
    origin,row=target
    current=getattr(world,'living_state',{}).get('physical_locks',{}).get(origin+':'+row['id'],{})
    if not current.get('locked',row.get('locked',True)):return ''
    # NPCs with a real key can use it while travelling. Player interaction is explicit.
    if actor and not actor.is_player and has_key(world,actor,row):return ''
    return row.get('name',row['id'])+' is locked. Use its key or try lockpicking.'


def select(world, actor, query):
    pairs=local(world,actor.location)
    matched=[p for p in pairs if query.casefold()==(p[0]+':'+p[1]['id']).casefold()]
    if not matched:matched=[p for p in pairs if query.casefold() in (p[1]['id'].casefold(),p[1].get('name','').casefold())]
    if len(matched)!=1:raise ValueError('Choose one nearby lock by its name or ID.')
    return matched[0]


def notice(world, actor, row, crime='lock tampering'):
    if permitted(world,actor,row):return ''
    from engine import sleep_movement
    from engine import relationships
    witnesses=[n for n in world.entities_in_room(actor.location) if not n.is_player and n.id!=actor.id and n.alive and relationships.sentient(world,n) and not sleep_movement.asleep(world,n)]
    if not witnesses:return ''
    # This is an event record, not invented omniscient law enforcement.
    events=living.state(world).setdefault('lock_incidents',[])
    events.append({'actor':actor.id,'lock':row['id'],'room':actor.location,'minute':living.state(world)['minute'],'witnesses':[n.id for n in witnesses]})
    del events[:-100]
    from engine import regional_world, mortality
    if regional_world.enabled(world):
        mortality.report_crime(world,actor,crime,row.get('owner') or row['id'],witnesses,
                               source={'kind':'door' if row.get('direction') else 'container',
                                       'id':row['id'],'name':row.get('name',row['id']),
                                       'action':'take' if crime=='theft' else 'tamper'})
    if crime=='theft':
        # One real observer calls out the act immediately. All witnesses still
        # remain in the evidence; do not fill Conversation with a crowd of yells.
        from engine import speech_bubbles
        speaker=next((person for person in witnesses if person.source_def==row.get('owner')),witnesses[0])
        words='Stop! Taking from '+row.get('name',row['id'])+' is theft!'
        speech_bubbles.mark(speaker,actor,'angry',None,('shouts',words,''))
        public=speaker.name+' shouts at '+actor.name+', “'+words+'”'
        style={'role':'npc','emphasis':'shout'}
        entry=(actor.location,public,actor.id if actor.is_player else None,style)
        world.runtime_notifications=(getattr(world,'runtime_notifications',[])+[entry])[-500:]
        if actor.is_player:
            personal=speaker.name+' shouts at you, “'+words+'”'
            world.rest_notifications=(getattr(world,'rest_notifications',[])+[(actor.id,personal,style)])[-500:]
    return ' '+', '.join(n.name for n in witnesses)+(' witnesses the ' if len(witnesses)==1 else ' witness the ')+crime+'.'


def item_choices(world, ids, *, actor=None):
    """Count the real units; unavailable or fixed objects are never transferred."""
    rows=[]
    for iid,count in Counter(ids).items():
        item=world.items.get(iid)
        reason=('Item definition unavailable.' if not item else
                'Fixed in place; cannot be carried.' if item.get('anchored_readable') is True else
                'Unequip this item first.' if actor and iid in actor.equipped.values() else '')
        rows.append(dict(id=iid,name=str((item or {}).get('name') or iid),count=count,
                         movable=not reason,reason=reason))
    return sorted(rows,key=lambda row:(row['name'].casefold(),row['id']))


def transfer_selection(world, actor, query, item_query, quantity, *, putting=False, exact=False):
    """Validate the whole transfer before changing either finite collection."""
    from engine import item_catalog, sleep_movement
    if not actor or not actor.alive or sleep_movement.asleep(world,actor):
        raise ValueError('You must be awake and able to act.')
    origin,row=select(world,actor,query);s=saved(world,origin,row)
    if row.get('direction'):raise ValueError('A door cannot store items. Choose a container.')
    if s['locked']:raise ValueError(row.get('name',row['id'])+' is locked.')
    if putting and row.get('practice'):raise ValueError('Practice locks must stay empty. Choose a storage container.')
    if type(quantity) is not int or quantity<1:raise ValueError('Choose a positive whole item quantity.')
    source=actor.inventory if putting else s['contents']
    missing='That item is no longer in your inventory.' if putting else 'That item is no longer in the container.'
    if not isinstance(item_query,str) or not item_query.strip():raise ValueError('Choose an item to transfer.')
    if exact and (item_query not in source or item_query not in world.items):raise ValueError(missing)
    item=item_catalog.choose(item_catalog.item_rows(world,source),item_query,missing=missing)
    iid=item['id'];count=source.count(iid)
    if exact and iid!=item_query:raise ValueError('That item selection changed. Refresh local actions.')
    if item.get('anchored_readable') is True:raise ValueError('The '+str(item.get('name') or iid)+' is fixed in place and cannot be moved.')
    if putting and iid in actor.equipped.values():raise ValueError('Unequip the '+str(item.get('name') or iid)+' first.')
    if quantity>count:raise ValueError('Only '+str(count)+' of that item '+('remain in your inventory.' if putting else 'remain in the container.'))
    return origin,row,s,iid,count


def transfer(world, actor, query, item_query, quantity=1, *, putting=False):
    origin,row,s,iid,_=transfer_selection(world,actor,query,item_query,quantity,putting=putting)
    source=actor.inventory if putting else s['contents']
    target=s['contents'] if putting else actor.inventory
    remaining=[];remove=quantity
    for entry in source:
        if entry==iid and remove:remove-=1
        else:remaining.append(entry)
    received=target+[iid]*quantity
    warning=notice(world,actor,row,'lock tampering' if putting else 'theft')
    # Both replacements are prepared before the first mutation. Duplicate units
    # retain their counts, and a rejected request never removes a partial stack.
    source[:]=remaining;target[:]=received
    verb='You put ' if putting else 'You take ' if permitted(world,actor,row) else 'You steal '
    return verb+str(quantity)+' × '+str(world.items[iid].get('name') or iid)+(' in ' if putting else ' from ')+row.get('name',row['id'])+'.'+warning


def act(world, actor, action, query, *, item=None, quantity=1):
    from engine import sleep_movement
    if not actor.alive or sleep_movement.asleep(world,actor):return 'You must be awake and able to act.'
    if action in ('take-item','put'):
        return transfer(world,actor,query,item,quantity,putting=action=='put')
    origin,row=select(world,actor,query);s=saved(world,origin,row);name=row.get('name',row['id'])
    if action=='inspect':
        return (name+': '+('locked' if s['locked'] else 'unlocked')+'. '+row.get('description','')+
                ' '+permission_warning(world,actor,row)).strip()
    if action in ('unlock','lock'):
        if not has_key(world,actor,row):return 'You need the matching key.'
        s['locked']=action=='lock';return name+' is now '+('locked.' if s['locked'] else 'unlocked.')
    if action=='pick':
        if not s['locked']:return name+' is already unlocked.'
        if row.get('pickable',True) is False:return 'This lock cannot be picked. Find its key or another way.'
        tools=[i for i in actor.inventory if i=='lockpicks' or world.items.get(i,{}).get('lockpick_tool')]
        if not tools:return 'You need lockpicks.'
        warning=notice(world,actor,row)
        # Deterministic difficulty avoids unlimited reload/reroll successes.
        if skill(world,actor)<row.get('difficulty',25):return 'This lock is beyond your current lockpicking skill.'+warning
        s['locked']=False
        pr=actor.progress;today=living.state(world)['minute']//1500
        learned=pr.setdefault('lock_practice_days',{})
        token=origin+':'+row['id']
        gain=''
        if actor.is_player and learned.get(token)!=today and skill(world,actor)<min(100,row.get('difficulty',25)+5):
            pr.setdefault('skills',{})['lockpicking']=skill(world,actor)+1;learned[token]=today
            gain=' Your lockpicking improves to '+str(skill(world,actor))+'.'
        return 'You pick '+name+'.'+gain+warning
    if action=='reset':
        if not row.get('practice') or not row.get('public') or row.get('direction') or row.get('contents'):return 'Only an empty public practice lock can be reset.'
        s['locked']=True;return name+' is ready to practice again.'
    if action=='open':
        if row.get('direction'):return 'Use the exit to pass through this door.'
        if s['locked']:return name+' is locked.'
        if not s['contents']:return name+' is empty.'
        return name+' contains: '+', '.join(str(i['count'])+' × '+i['name'] for i in item_choices(world,s['contents']))+'.'
    if action=='take':
        if row.get('direction'):return 'A door has no contents.'
        if s['locked']:return name+' is locked.'
        if not s['contents']:return name+' is empty.'
        if any(not item['movable'] for item in item_choices(world,s['contents'])):
            return 'Some contents cannot be moved. Choose a movable item to take separately.'
        warning=notice(world,actor,row,'theft');actor.inventory.extend(s['contents']);s['contents']=[]
        return ('You take' if permitted(world,actor,row) else 'You steal')+' the contents of '+name+'.'+warning
    raise ValueError('Choose inspect, unlock, lock, pick, open, take, take-item, or put.')


def service(world, player, npc, query):
    """Explicit NPC assistance, never spontaneous burglary or remote service."""
    from engine import sleep_movement
    if not player.alive or sleep_movement.asleep(world,player):return 'You must be awake and able to act.'
    if npc.is_player or not npc.alive or npc.location!=player.location or sleep_movement.asleep(world,npc):return 'That locksmith is not available here.'
    definition=world.npcs.get(npc.source_def,{})
    if not definition.get('locksmith'):return npc.name+' does not offer locksmith work.'
    if not on_duty(world,npc):return npc.name+' is off duty. Return during the posted hours.'
    origin,row=select(world,player,query)
    if not permitted(world,player,row):return npc.name+' needs proof that you may open this lock.'
    if not saved(world,origin,row)['locked']:return 'It is already unlocked.'
    if not row.get('pickable',True) or skill(world,npc)<row.get('difficulty',25):return npc.name+' cannot pick this lock.'
    fee=definition.get('locksmith_fee',0)
    if player.gold<fee:return 'The locksmith charges '+str(fee)+' gold.'
    # Payment and unlock happen only after all checks; no failed-service charge.
    player.gold-=fee;npc.gold+=fee;saved(world,origin,row)['locked']=False
    return npc.name+' unlocks '+row.get('name',row['id'])+' for '+str(fee)+' gold.'


def command(ctx,args):
    action,_,target=args.strip().partition(' ')
    if action not in ('','list','inspect','open'):
        ctx.world.dirty_players=getattr(ctx.world,'dirty_players',set())|{ctx.player.id}
    if action in ('take-item','put'):
        try:parts=shlex.split(target)
        except ValueError as exc:raise ValueError('Close quotes around container and item names.') from exc
        if len(parts) not in (2,3):raise ValueError('Use locks '+action+' "<container>" "<item>" [quantity].')
        try:quantity=int(parts[2]) if len(parts)==3 else 1
        except ValueError as exc:raise ValueError('Choose a positive whole item quantity.') from exc
        return act(ctx.world,ctx.player,action,parts[0],item=parts[1],quantity=quantity)
    if action in ('lesson','kit'):
        return teach(ctx.world,ctx.player,find_npc(ctx.world,ctx.player,target),action)
    if action=='service':
        npc_query,sep,lock_query=target.partition(' for ')
        if not sep:raise ValueError('Choose locksmith name for lock name.')
        candidates=[n for n in ctx.world.entities_in_room(ctx.player.location) if not n.is_player and npc_query.casefold() in (n.id.casefold(),n.name.casefold())]
        if len(candidates)!=1:raise ValueError('Choose one locksmith here.')
        return service(ctx.world,ctx.player,candidates[0],lock_query)
    if not action or action=='list':
        return '\n'.join(act(ctx.world,ctx.player,'inspect',origin+':'+row['id']) for origin,row in local(ctx.world,ctx.player.location)) or 'There are no physical locks here.'
    return act(ctx.world,ctx.player,action,target.strip())


def register(registry):
    from engine.commands import Command
    registry.register(Command('locks','Interact with nearby containers and locks','locks list | locks <inspect|unlock|lock|pick|open|take> <name> | locks <take-item|put> "<container>" "<item>" [quantity]',command,example='locks put "storage chest" bread 2'))


def validate(data):
    issues=[];rooms={r['id']:r for r in data.get('room',[])};items={r['id'] for r in data.get('item',[])}
    npcs={r['id'] for r in data.get('npc',[])};groups={r['id'] for r in data.get('group',[])};doors=set()
    for rid,room in rooms.items():
        rows=room.get('locks',[])
        if not isinstance(rows,list):issues.append(rid+': locks must be a list');continue
        seen=set()
        for row in rows:
            if not isinstance(row,dict):issues.append(rid+': lock must be an object');continue
            lid=row.get('id');where=rid+': lock '+str(lid)
            if not isinstance(lid,str) or not lid.strip() or ':' in lid or lid in seen:issues.append(where+': unique nonempty ID without colon required')
            else:seen.add(lid)
            for field in ('locked','pickable','public','practice'):
                if field in row and type(row[field]) is not bool:issues.append(where+': '+field+' must be boolean')
            if type(row.get('difficulty',25)) is not int or not 0<=row.get('difficulty',25)<=100:issues.append(where+': difficulty must be 0-100')
            if row.get('key') and (not isinstance(row['key'],str) or row['key'] not in items):issues.append(where+': key item missing')
            if row.get('owner') and (not isinstance(row['owner'],str) or row['owner'] not in npcs):issues.append(where+': owner NPC missing')
            if not isinstance(row.get('allowed_groups',[]),list) or any(not isinstance(g,str) or g not in groups for g in row.get('allowed_groups',[])):issues.append(where+': invalid allowed groups')
            if not isinstance(row.get('contents',[]),list) or any(not isinstance(i,str) or i not in items for i in row.get('contents',[])):issues.append(where+': invalid contents')
            if row.get('practice') and (not row.get('public') or row.get('contents') or row.get('direction')):issues.append(where+': practice requires an empty public container')
            if row.get('direction'):
                target=room.get('exits',{}).get(direction(str(row['direction'])))
                if not isinstance(target,str):target=None
                pair=frozenset((rid,target))
                if target not in rooms or target==rid:issues.append(where+': door needs an existing different exit destination')
                if pair in doors:issues.append(where+': door pair already has a lock definition')
                doors.add(pair)
                if row.get('contents'):issues.append(where+': doors cannot contain items')
    for kind in ('npc','class'):
        for row in data.get(kind,[]):
            if type(row.get('lockpicking',0)) is not int or not 0<=row.get('lockpicking',0)<=100:issues.append(row['id']+': lockpicking must be 0-100')
            if kind=='npc':
                for flag in ('locksmith','lock_trainer'):
                    if flag in row and type(row[flag]) is not bool:issues.append(row['id']+': '+flag+' must be boolean')
                for field,maximum in (('lock_lesson_fee',100000),('lock_work_start',1499),('lock_work_end',1500)):
                    if field in row and (type(row[field]) is not int or not 0<=row[field]<=maximum):issues.append(row['id']+': invalid '+field)
                start,end=row.get('lock_work_start',0),row.get('lock_work_end',1500)
                if type(start) is int and type(end) is int and start>=end:issues.append(row['id']+': lock work end must follow start')
                if type(row.get('locksmith_fee',0)) is not int or row.get('locksmith_fee',0)<0:issues.append(row['id']+': locksmith_fee must be a nonnegative integer')
                if not isinstance(row.get('lock_keys',[]),list) or any(not isinstance(i,str) or i not in items for i in row.get('lock_keys',[])):issues.append(row['id']+': invalid lock keys')
    return issues


def projection(world, actor):
    """Local interaction packet only; no contents or key IDs behind locked fixtures."""
    result=[];deposits=None
    for origin,row in local(world,actor.location):
        state=saved(world,origin,row)
        view={'id':origin+':'+row['id'],'name':row.get('name',row['id']),
              'kind':'door' if row.get('direction') else 'container',
              'locked':bool(state['locked']),
              'pickable':row.get('pickable',True),'has_key':has_key(world,actor,row),
              'practice':row.get('practice',False),'permitted':permitted(world,actor,row),
              'permission_warning':permission_warning(world,actor,row)}
        if view['kind']=='container' and not view['locked']:
            view['contents']=item_choices(world,state['contents'])
            if deposits is None:deposits=[item for item in item_choices(world,actor.inventory,actor=actor) if item['movable']]
            view['deposit_items']=[] if view['practice'] else deposits
        result.append(view)
    return result


def find_npc(world,player,query):
    rows=[n for n in world.entities_in_room(player.location) if not n.is_player and query.casefold() in (n.id.casefold(),n.name.casefold())]
    if len(rows)!=1:raise ValueError('Choose one locksmith here.')
    return rows[0]


def on_duty(world,npc):
    from engine import sleep_movement
    d=world.npcs.get(npc.source_def,{})
    minute=living.state(world)['minute']%1500
    return npc.alive and not sleep_movement.asleep(world,npc) and d.get('lock_work_start',0)<=minute<d.get('lock_work_end',1500)


def teach(world,player,npc,action):
    from engine import sleep_movement
    d=world.npcs.get(npc.source_def,{})
    if not player.alive or sleep_movement.asleep(world,player):return 'You must be awake and able to act.'
    if npc.location!=player.location or not on_duty(world,npc) or not d.get('lock_trainer'):return 'That instructor is not teaching here now.'
    if action=='kit':
        if player.progress.get('lock_starter_kit'):return 'You already received your introductory toolkit. Keep it, buy another, or forge replacement picks.'
        if any(i=='lockpicks' or world.items.get(i,{}).get('lockpick_tool') for i in player.inventory):return 'You already have picks. Try the practice locks or take a lesson.'
        if 'lockpicks' not in npc.inventory:return 'The donated toolkits have run out. Forge picks from iron ore at a forge.'
        npc.inventory.remove('lockpicks');player.inventory.append('lockpicks');player.progress['lock_starter_kit']=True
        return npc.name+' lends you a toolkit to keep. Start with the empty practice lock; reset it to practice again. Further lessons improve your skill.'
    level=skill(world,player);ceiling=min(100,d.get('lockpicking',0))
    if level>=ceiling:return 'You have learned all this instructor can teach.'
    if not any(i=='lockpicks' or world.items.get(i,{}).get('lockpick_tool') for i in player.inventory):return 'Bring lockpicks or ask for an introductory toolkit.'
    today=living.state(world)['minute']//1500
    if player.progress.get('lock_lesson_day')==today:return 'One lockpicking lesson per world day. Practice or return tomorrow.'
    fee=d.get('lock_lesson_fee',2)
    if player.gold<fee:return 'A lesson costs '+str(fee)+' gold.'
    player.gold-=fee;npc.gold+=fee;player.progress['lock_lesson_day']=today
    player.progress.setdefault('skills',{})['lockpicking']=min(ceiling,level+5)
    return npc.name+' teaches a lesson. Lockpicking is now '+str(skill(world,player))+'.'


def teachers(world,player):
    return [{'id':n.id,'name':n.name,'available':on_duty(world,n),'locksmith':bool(d.get('locksmith')),'trainer':bool(d.get('lock_trainer')),
             'fee':d.get('locksmith_fee',0),'lesson_fee':d.get('lock_lesson_fee',2),
             'hours':f"{d.get('lock_work_start',0)//60:02d}:{d.get('lock_work_start',0)%60:02d}–{d.get('lock_work_end',1500)//60:02d}:{d.get('lock_work_end',1500)%60:02d}"}
            for n in world.entities_in_room(player.location) if not n.is_player
            for d in [world.npcs.get(n.source_def,{})] if d.get('locksmith') or d.get('lock_trainer')]
