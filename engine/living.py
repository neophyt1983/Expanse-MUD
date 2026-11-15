"""Data-driven living-world rules. No external AI service is required."""
from engine.item_catalog import counted, goods_amount
import random
from engine import worldtime
from engine.directions import direction
from collections import Counter, deque

CATALOGS=('recipes','resources','encounters')

def state(world):
    if not hasattr(world,'living_state'):world.living_state={}
    s=world.living_state
    s.setdefault('minute',worldtime.initial_minute(world.metadata))
    for key in ('nodes','encounters','camps'):
        if key not in s:s[key]={}
    return s

def progress(p):
    for k,v in {'mana':20,'max_mana':20,'intoxication':0,'injury':0,'disease':0,'companions':[],'quests':{},'kills':{},'enchants':{},'skills':{},'hair':'natural','ward':0,'ward_turns':0}.items():p.progress.setdefault(k,v)
    return p.progress

def details(world,room):return getattr(world,'room_details',{}).get(room,{})
def catalog(world,name):return getattr(world,name,{})
def enabled(world):return bool(world.metadata.get('living_world',False))

def choose(rows,query):
    from engine.item_catalog import choose as select
    return select(rows,query)

def consume(p,ingredients,world=None):
    counts=Counter(p.inventory)
    missing=[goods_amount(world.items[i],n-counts[i]) if world and i in world.items else f'{n-counts[i]} {i}' for i,n in ingredients.items() if counts[i]<n]
    if missing:raise ValueError('Missing ingredients: '+', '.join(missing))
    for i,n in ingredients.items():
        for _ in range(n):p.inventory.remove(i)
    p.equipped={k:v for k,v in p.equipped.items() if v in p.inventory}

def next_step(world,start,target,actor=None):
    from engine import frontiers
    steps=frontiers.path(world,start,target,actor)
    return (steps[0][2] if steps else start) if steps is not None else None


def heal(world,actor,amount):
    """Ordinary healing retires geological debt, without reviving a dead actor."""
    if not actor.alive or amount<=0:return 0
    before=actor.hp;actor.hp+=max(0,min(amount,actor.max_hp-actor.hp))
    restored=actor.hp-before
    from engine import geology_impacts
    geology_impacts.retire_wounds(world,actor,restored)
    if actor.is_player and restored:
        world.dirty_players=getattr(world,'dirty_players',set())|{actor.id}
    return restored


def advance(world,minutes=1):
    if getattr(world,"_community_simulating",False):return
    if not enabled(world):return
    if getattr(world,'realtime',False) and not getattr(world,'tick_authorized',False):return
    if not hasattr(world,'commute_budget'):
        # The existing FIFO route planner keeps a large city from calculating
        # hundreds of new routes before the server can send injury messages.
        budget=world.metadata.get('npc_commute_budget',16)
        world.commute_budget=budget if type(budget) is int and 1<=budget<=128 else 16
    from engine import population
    population.ensure(world)
    s=state(world);s['minute']+=minutes;now=s['minute'];clock=now%worldtime.MINUTES_PER_DAY;hour=clock//60
    from engine import escorts
    escorts.advance(world)
    from engine import civic_program
    civic_program.advance(world,now-minutes,now)
    from engine import wildlands
    wildlands.advance(world,now-minutes,now)
    from engine import regional_world
    regional_world.advance(world)
    from engine import dynamic_diplomacy, family_life
    family_life.advance(world)
    dynamic_diplomacy.ensure(world,advance=True)
    from engine import political_map
    political_map.advance(world)
    from engine import regional_weather
    regional_weather.advance(world,minutes)
    from engine import geology_events
    geology_events.advance(world,minutes)
    from engine import geology_impacts
    geology_impacts.advance(world,minutes)
    from engine import needs_market
    needs_market.advance(world,minutes)
    from engine import settlements
    settlements.advance(world)
    from engine import npc_life
    from engine import community_quests
    community_quests.advance(world)
    for e in list(world.entities.values()):
        if e.progress.get('zoo_exhibit'):
            continue
        from engine import sleep_movement
        sleep_movement.scheduled_wake(world,e)
        npc_life.step(world,e,now)
        sheltering=regional_weather.actor_step(world,e,minutes)
        if e.is_player:
            pr=progress(e);pr['intoxication']=max(0,pr['intoxication']-minutes)
            continue
        if not e.alive or sheltering or sleep_movement.asleep(world,e):continue
        from engine import npc_attention
        if npc_attention.paused(world,e):continue
        if community_quests.assignment(world,e):continue
        template=world.npcs.get(e.source_def,{})
        if template.get('city_perimeter') and not e.progress.get('escort_post') and community_quests.perimeter(world,e):continue
        if template.get('expedition_role') or template.get('district_resident'):continue
        if e.progress.get('companion_owner'):
            from engine import companions
            companions.follow(world,e)
            continue
        if family_life.care_shift(world,e) or population.routine(world,e):continue
        if e.progress.get('retired'):
            from engine import livelihoods
            home=e.progress.get('home_room') or livelihoods.definition(world,e).get('home_room')
            if home in world.rooms:livelihoods.move_towards(world,e,home)
            e.activity='enjoying retirement' if e.location==home or not home else 'walking home'
            continue
        from engine import livelihoods
        if livelihoods.routine(world,e):continue
        if needs_market.act(world,e,minutes):continue
        if settlements.housing_step(world,e):continue
        definition=world.npcs.get(e.source_def,{})
        schedule=definition.get('schedule',[])
        if schedule:
            weekday=worldtime.date(now)['weekday']
            ordered=sorted([a for a in schedule if not a.get('weekdays') or weekday in a['weekdays']],key=lambda a:a['hour']*60+a.get('minute',0))
            if not ordered:continue
            current=next((a for a in reversed(ordered) if a['hour']*60+a.get('minute',0)<=clock),ordered[-1])
            target=current['room']
            if e.progress.get('home_room') in world.rooms and any(k in current.get('activity','') for k in ('sleep','home')):target=e.progress['home_room']
            job=settlements.state(world)['units'].get(e.progress.get('job_property')) if settlements.enabled(world) else None
            if job and e.id in (job['owner'],job['tenant']) and current.get('activity')=='working':target=job['room']
            if target in world.rooms:
                step=next_step(world,e.location,target,e)
                if step and step!=e.location:world.move_entity(e.id,step)
            e.activity=current.get('activity','resting') if e.location==target else 'travelling to '+current.get('activity','resting')
        elif definition.get('patrol_route'):
            route=[rid for rid in definition['patrol_route'] if rid in world.rooms]
            if route:
                index=e.progress.get('patrol_index',route.index(e.location) if e.location in route else 0)%len(route)
                if e.location==route[index]:index=(index+1)%len(route)
                e.progress['patrol_index']=index
                target=route[index]
                step=next_step(world,e.location,target,e)
                if step and step!=e.location:world.move_entity(e.id,step)
        elif definition.get('roaming') and random.random()<.2:
            from engine import frontiers
            exits=[rid for di,rid in world.rooms[e.location].exits.items() if rid in world.rooms and not frontiers.blocked(world,e.location,di,e)]
            if exits:world.move_entity(e.id,random.choice(exits))

    from engine import society
    society.produce(world)
    from engine import market_shifts
    market_shifts.advance(world)
    from engine import wildlife
    wildlife.advance(world)
    if society.enabled(world):
        from engine import relationships, mortality
        messages=mortality.advance(world)
        world.runtime_notifications=getattr(world,"runtime_notifications",[])+messages
        relationships.advance(world)
        from engine import social
        social.advance(world)

    from engine import resting
    resting.advance(world,minutes)
    if getattr(world,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.sample(world)

def on_entry(world,p):
    if not enabled(world):return ''
    s=state(world);r=details(world,p.location);lines=[]
    for traffic in world.entities_in_room(p.location):
        hazard=world.npcs.get(traffic.source_def,{}).get('traffic',{})
        if hazard.get('enabled'):lines.append(hazard.get('warning','Watch for passing traffic.'))
    for encounter_id in r.get('encounters',[]):
        definition=catalog(world,'encounters').get(encounter_id)
        if not definition:continue
        key=p.location+':'+encounter_id
        current=s['encounters'].setdefault(key,{'active':False,'cleared':False,'members':[],'last_harvest':-100000})
        current['members']=[i for i in current['members'] if i in world.entities and world.entities[i].alive]
        if current['cleared'] or current['active']:continue
        if random.random()>=definition.get('chance',1):continue
        from engine.commands import _spawn_npc_instance
        for npc in definition.get('members',[]):
            e=_spawn_npc_instance(world,world.rooms[p.location],npc,spawner_key='encounter:'+key)
            if e:current['members'].append(e.id)
        current['active']=True;lines.append(definition.get('description','An encounter begins.'))
    for enemy in world.entities_in_room(p.location):
        if enemy.is_player or enemy.progress.get('companion_owner'):continue
        definition=world.npcs.get(enemy.source_def,{})
        from engine import city_defense
        if city_defense.enabled(world) and city_defense.is_defender(world,enemy):continue
        # Regional threats use their own warning and attack clock; entry must
        # not grant a second, immediate attack outside that scheduler.
        if enemy.progress.get('regional_encounter') and definition.get('regional_generated'):continue
        if definition.get('aggressive') and random.random()<definition.get('aggression_chance',.25):
            from engine import combat
            if details(world,p.location).get('truce'):continue
            try:text=combat.npc_attack(world,enemy,p,counter=False)
            except ValueError:continue
            lines.append(text)
            if not p.alive:break
    return '\n'.join(lines)

def on_kill(world,p,target,*,grant_drops=True):
    if not enabled(world):return
    if world.npcs.get(target.source_def,{}).get('expedition_role')=='quarry':
        state(world).setdefault('field_hunts',{})[target.source_def]=state(world)['minute']+360
    pr=progress(p);pr['kills'][target.source_def]=pr['kills'].get(target.source_def,0)+1
    for item in (world.npcs.get(target.source_def,{}).get('drops',[]) if grant_drops else []):
        if item in world.items:p.inventory.append(item)
    key=getattr(target,'spawner_key',None)
    if key and key.startswith('encounter:'):
        rec=state(world)['encounters'].get(key[len('encounter:'):])
        if rec:
            rec['members']=[eid for eid in rec['members'] if eid!=target.id and eid in world.entities and world.entities[eid].alive]
            if not rec['members']:rec['cleared']=True

def attack_bonus(p):
    pr=progress(p)
    return sum(pr['enchants'].get(i,{}).get('attack',0) for i in p.equipped.values()) + sum(c.get('attack',0) for c in pr['companions'] if not c.get('source_def')) - pr['intoxication']//25 - pr['injury']//20

def defense_bonus(p):return sum(progress(p)['enchants'].get(i,{}).get('defense',0) for i in p.equipped.values()) + (progress(p)['ward'] if progress(p)['ward_turns']>0 else 0)

def on_use(world,p,item):
    pr=progress(p)
    pr['intoxication']=min(100,pr['intoxication']+item.get('alcohol',0))
    pr['injury']=max(0,pr['injury']-item.get('cure_injury',0))
    pr['disease']=max(0,pr['disease']-item.get('cure_disease',0))
    if item.get('raw_risk') and random.random()<item['raw_risk']:pr['disease']=min(100,pr['disease']+20)
    if item.get('learn_ability') in world.abilities and item['learn_ability'] not in p.abilities:p.abilities.append(item['learn_ability'])

COMMANDS={
 'invoke':('Use a prepared spell scroll once without learning it','invoke <scroll> at <target>'),
 'time':('Show world time','time'), 'survey':('Inspect local resources and facilities','survey'),
 'fish':('Fish at a local resource with a carried rod','fish [site name]'),
 'gather':('Harvest a local resource','gather meadow herbs'), 'harvest':('Harvest an encounter without destroying it','harvest bee colony'),
 'recipes':('List recipes and ingredients','recipes'), 'craft':('Craft at a suitable station','craft iron helm'),
 'carriage':('Book a public carriage at a city stand','carriage <town name>'), 'attend':('Join a public event at its venue','attend class'),
 'cook':('Cook food at a kitchen or lit campfire','cook vegetable stew'), 'camp':('Pitch or pack your tent','camp pitch'),
 'fire':('Light or extinguish your campfire','fire light'), 'rest':('Recover at an inn or camp over elapsed time','rest [1-60 minutes]'),
 'sleep':('Sleep safely at an inn or camp','sleep [1-60 minutes]'),
 'condition':('Inspect health conditions and companions','condition'), 'tame':('Befriend a tameable creature','tame woodland fox'),
 'companions':('List pets and familiars','companions'), 'dismiss':('Dismiss a companion','dismiss woodland fox'),
 'spells':('List learned abilities','spells'), 'cast':('Use a learned ability','cast firebolt at wolf'),
 'enchant':('Enchant equipment at an enchanting desk','enchant iron sword with flame sigil'),
 'services':('List local services','services'), 'service':('Buy a local service','service haircut'),
 'study':('Train an ability at a school','study arcane ward'), 'quests':('List available quests','quests'),
 'accept':('Accept a quest','accept village supplies'), 'complete':('Turn in a completed quest','complete village supplies'),
 'sell':('Sell an item to a nearby merchant','sell iron sword'), 'inspect':('Read a person or object description','inspect woodland fox'),
 'hunt':('Attack local wildlife','hunt deer'), 'wait':('Advance simulation by up to 60 minutes','wait 10'),
}

def command(ctx,args,name):
    w,p,r=ctx.world,ctx.player,ctx.room
    if not enabled(w):return 'Living-world rules are not enabled for this world.'
    pr=progress(p);s=state(w);rd=details(w,r.id);now=s['minute']
    from engine import geology_impacts
    impaired=geology_impacts.room_unusable(w,r.id)
    facilities=[] if impaired else rd.get('facilities',[])
    if name in ('carriage','attend'):
        from engine import civic_program
        return civic_program.command(ctx,args,name)
    if name=='time':
        from engine import climate
        return worldtime.describe(now,w.metadata.get('sunrise_minute',375))+'\n'+climate.describe(w,p.location)
    if name=='wait':
        try:n=int(args or '10')
        except ValueError:return 'Use wait <1-60 minutes>.'
        if not 1<=n<=60:return 'Wait between 1 and 60 minutes.'
        if getattr(w,'realtime',False):
            from engine import resting
            return 'The shared world clock cannot be skipped. It continues while you are connected. '+(resting.status(w,p) if resting.active(p) else 'Use rest or sleep at an inn or your pitched tent to recover over elapsed time.')
        advance(w,n);return command(ctx,'','time')
    if name=='survey':
        from engine import gathering,resource_nodes
        lines=[rd.get('environment','settlement').title()+' | Facilities: '+(', '.join(facilities) or 'none')]
        for i in resource_nodes.active_resources(w,r.id):
            d=catalog(w,'resources').get(i,{})
            from engine import knowledge, hand_resources
            knowledge.teach(w,p,d.get('knowledge',{}))
            lines.append('Gather: '+d.get('name',i)+' — '+d.get('description',''))
            if d.get('yields'):lines.append('Per successful gathering: '+', '.join(str(n)+' '+w.items.get(iid,{}).get('name',iid) for iid,n in d['yields'].items()))
            required=d.get('tool')
            if required:lines.append('Required tool: '+w.items.get(required,{}).get('name',required)+(' (carried).' if required in p.inventory else ' (not carried). Learn a supplier or a crafting recipe before setting out.'))
            if hand_resources.configured(d):lines.append(hand_resources.describe(w,r.id,d))
            from engine import fishing
            tool=w.items.get(d.get('tool'),{})
            if fishing.is_rod(tool):
                lines.append('Fishing: '+d.get('name',i)+' — carry '+tool['name']+" in your inventory, then use fish. No equipment slot is needed.")
        for i in rd.get('encounters',[]):
            d=catalog(w,'encounters').get(i,{})
            lines.append('Encounter: '+d.get('name',i)+' — '+d.get('description',''))
        for row in gathering.listing(w,p):
            lines.append(row['label']+' — '+row['detail'])
        return '\n'.join(lines)
    if name=='inspect':
        rows=[dict(id=e.id,name=e.name,description=w.npcs.get(e.source_def,{}).get('description',''),activity=getattr(e,'activity','')) for e in w.entities_in_room(r.id) if not e.is_player]
        rows += [w.items[i] for i in dict.fromkeys(p.inventory+r.items) if i in w.items]
        obj=choose(rows,args);return obj.get('description','No further details.')+' Location: '+r.name+'.'+(' Activity: '+obj['activity'] if obj.get('activity') else '')
    if name=='fish':
        from engine import fishing
        return fishing.fish(ctx,args)
    if name=='gather':
        from engine import gathering
        if not args.strip() or args.strip().casefold() in ('list','?'):
            ctx.time_accounted=True
            rows=gathering.listing(w,p)
            if not rows:return 'Nothing can be gathered at '+r.name+'.'
            return 'Gathering at '+r.name+'\n'+'\n'.join(row['label']+' — '+row['detail'] for row in rows)+'\nUse gather followed by the source or item name.'
        obj=catalog(w,'resources')[args]
        missing=gathering.prerequisite(w,p,obj)
        if missing:return missing
        from engine import ecology,resource_nodes
        reason=geology_impacts.resource_blocked(w,r.id,obj['id'])
        if reason:return reason
        if impaired:return 'This location is temporarily unusable while hazard damage is repaired.'
        if not ecology.in_season(w,obj,r.id):return 'This plant is outside its harvest season.'
        if not ecology.available(w,r.id,obj):return 'The required living, mature wildlife is not present here.'
        from engine import hand_resources
        manual=hand_resources.configured(obj)
        if manual:ctx.time_accounted=True
        configured=resource_nodes.managed(obj,w.items)
        key=r.id+':'+obj['id']
        ledger=s.setdefault('shared_resource_times',{}) if obj.get('shared_renewal') else s['nodes']
        last=ledger.get(key,-100000)
        if configured and resource_nodes.exhausted(w,r.id,obj):return 'This mineral deposit is permanently exhausted.'
        tool=obj.get('tool')
        if tool and tool not in p.inventory:return 'You need '+w.items[tool]['name']+'.'
        if (configured and not resource_nodes.available(w,r.id,obj)) or (not configured and not manual and now-last<obj.get('renewal_minutes',60)):
            if configured and resource_nodes.request_manual_turn(w,r.id,obj,p):
                return ('This resource needs time to replenish. Try gathering again in '+counted(resource_nodes.manual_turn_delay(w,r.id,obj,p),'game minute')+'. Stay here for a five-minute gathering opportunity after renewal. Hazards and competition still apply.')
            return 'This resource needs time to replenish.'

        if manual:
            reason=hand_resources.claim(w,r.id,obj,p)
            if reason:return reason
        if configured and not resource_nodes.harvest(w,r.id,obj,p):return 'This resource cannot be gathered here right now.'
        for iid,n in obj.get('yields',{}).items():p.inventory.extend([iid]*n)
        if manual:advance(w,obj['gather_minutes'])
        elif not configured:ledger[key]=now
        from engine import quest_progress
        quest_progress.action(p, 'gather:' + obj['id'])
        from engine import community_quests
        community_quests.performed(w,p,'gather',obj['id'])
        from engine import progression
        advancement=progression.award(w,p,'gather',obj['id'])
        return 'Gathered: '+', '.join(goods_amount(w.items[i],n) for i,n in obj.get('yields',{}).items())+('\n'+advancement if advancement else '')
    if name=='harvest':
        if impaired:return 'This location is temporarily unusable while hazard damage is repaired.'
        obj=choose([catalog(w,'encounters')[i] for i in rd.get('encounters',[]) if i in catalog(w,'encounters')],args)
        key=r.id+':'+obj['id'];rec=s['encounters'].get(key)
        from engine import gathering
        if not obj.get('harvest'):return 'This encounter has no nonlethal harvest.'
        reason=gathering.prerequisite(w,p,obj) or gathering.encounter_state(w,r.id,obj)
        if obj.get('tool') and obj['tool'] not in p.inventory:return 'Bring '+w.items.get(obj['tool'],{}).get('name','the required tool')+'.'
        if reason:return reason
        for iid,n in obj['harvest'].items():p.inventory.extend([iid]*n)
        rec['last_harvest']=now
        damage=obj.get('harvest_damage',0)
        if damage:
            damage=p.take_damage(damage,defense=0,cause='harvesting '+obj.get('name',obj['id']),kind='harvest')
            from engine import gazette,relationships
            if any(not e.is_player and relationships.sentient(w,e) for e in w.entities_in_room(r.id)):
                product=next(iter(obj['harvest']))
                headline=p.name+' was hurt collecting '+w.items[product]['name']+' at '+r.name+'.'
                gazette.record(w,r.id,'Public safety',headline,key='harvest:'+r.id+':'+obj['id']+':'+p.id,once=True)
        from engine import progression
        advancement=progression.award(w,p,'gather','encounter:'+obj['id'])
        return 'Harvested without destroying the source: '+gathering.goods(w,obj['harvest'])+(f'. Suffered {damage} damage.' if damage else '.')+('\n'+advancement if advancement else '')
    if name=='recipes':
        from engine.item_catalog import browse
        return browse(w,args,recipe=True,player=p)
    if name in ('craft','cook'):
        if impaired:return 'This workshop is temporarily unusable while hazard damage is repaired.'
        from engine import knowledge
        obj=knowledge.crafting_choice(w,p,args)
        if any(i not in p.abilities for i in obj.get('required_abilities',[])):return 'Learn the required ability before preparing this recipe: '+', '.join(w.abilities.get(i,{}).get('name',i) for i in obj.get('required_abilities',[]))
        if name=='cook' and obj.get('kind')!='cooking':return 'Use craft for this recipe.'
        from engine.quest_progress import status as quest_status
        if any(quest_status(w,p,qid)!='complete' for qid in obj.get('prerequisites',[])):return 'Complete this recipe’s prerequisite quests first.'
        station=obj.get('station','hand');camp=s['camps'].get(p.id,{})
        available=station=='hand' or station in facilities or (station=='kitchen' and camp.get('room')==r.id and camp.get('fire'))
        if not available:return 'You need a '+station+'.'
        from engine import ecology
        if not ecology.available(w,r.id,obj):return 'This activity needs a living, mature population of the required species here.'
        consume(p,obj['ingredients'],w)
        for iid,n in obj['outputs'].items():p.inventory.extend([iid]*n)
        skill=obj.get('kind','crafting');pr['skills'][skill]=pr['skills'].get(skill,0)+1
        advance(w,obj.get('minutes',5))
        from engine import quest_progress
        quest_progress.action(p, name + ':' + obj['id'])
        from engine import community_quests
        community_quests.performed(w,p,name,obj['id'])
        from engine import progression
        advancement=progression.award(w,p,'craft',obj['id'])
        return 'Created: '+', '.join(goods_amount(w.items[k],v) for k,v in obj['outputs'].items())+('\n'+advancement if advancement else '')
    if name=='camp':
        if args.strip()=='pack':
            camp=s['camps'].get(p.id)
            if not camp or camp['room']!=r.id:return 'Your tent is not here.'
            p.inventory.append(camp['tent']);del s['camps'][p.id];return 'Tent packed; fire extinguished.'
        if args.strip()!='pitch':return 'Use camp pitch or camp pack.'
        if not rd.get('campable'):return 'Camping is not allowed here.'
        if p.id in s['camps']:return 'Pack your existing tent first.'
        tent=next((i for i in p.inventory if w.items.get(i,{}).get('camp_tent')),None)
        if not tent:return 'You need a tent in your inventory.'
        p.inventory.remove(tent);s['camps'][p.id]={'room':r.id,'fire':False,'tent':tent};return 'Your tent is pitched.'
    if name=='fire':
        camp=s['camps'].get(p.id)
        if not camp or camp['room']!=r.id:return 'Pitch your tent here first.'
        if args.strip()=='out':camp['fire']=False;return 'Fire extinguished.'
        if args.strip()!='light':return 'Use fire light or fire out.'
        if camp['fire']:return 'Your campfire is already burning.'
        fuel=next((i for i in p.inventory if w.items.get(i,{}).get('fuel')),None)
        if not fuel:return 'You need firewood.'
        p.inventory.remove(fuel);camp['fire']=True;return 'Your campfire is lit. You can cook here.'
    if name in ('rest','sleep'):
        from engine import resting
        return resting.command(w,p,args,name)
    if name in ('condition','companions'):
        if name=='companions':return '\n'.join(c['name']+' ('+c['kind']+')' for c in pr['companions']) or 'No companions.'
        return f'Mana {pr["mana"]}/{pr["max_mana"]}; intoxication {pr["intoxication"]}/100; injury {pr["injury"]}/100; disease {pr["disease"]}/100. Hair: {pr["hair"]}.'
    if name=='tame':
        from engine import taming, society, relationships
        if not args.strip():return taming.advice(w,p)
        entities=[e for e in w.entities_in_room(r.id) if not e.is_player and w.npcs.get(e.source_def,{}).get('tameable')]
        obj=choose([dict(id=e.id,name=e.name) for e in entities],args);e=w.entities[obj['id']];d=w.npcs[e.source_def]
        bait=taming.requirement(w,p,e)
        if bait:consume(p,{bait:1},w)
        if society.enabled(w):
            e.progress.update(companion_owner=p.id,companion_order='follow',companion_mode='defend')
            pr['companions'].append(dict(id=e.id,source_def=e.source_def,name=e.name,kind=d.get('companion_kind','pet'),attack=d.get('companion_attack',1),description=d.get('description','')))
            relationships.establish(w,p,e,'companion')
            from engine import quest_progress
            quest_progress.action(p,'tame')
            return e.name+' joins you as a living companion and assists in combat.'
        pr['companions'].append(dict(id=e.source_def,name=e.name,kind=d.get('companion_kind','pet'),attack=d.get('companion_attack',1),description=d.get('description','')))
        r.entities.remove(e.id);del w.entities[e.id]
        if not e.spawner_key:w.killed_npcs.add(e.source_def)
        from engine import quest_progress
        quest_progress.action(p,'tame')
        return e.name+' joins you and assists in combat.'
    if name=='dismiss':
        from engine import society,companions
        if society.enabled(w):return companions.command(ctx,'dismiss '+args)
        obj=choose(pr['companions'],args);pr['companions'].remove(obj)
        companion=w.entities.get(obj['id'])
        if companion:
            companion.progress.pop('companion_owner',None)
            from engine import relationships
            bond=relationships.bond(w,p,companion)
            if 'companion' in bond['kinds']:bond['kinds'].remove('companion')
        return obj['name']+' leaves your company.'
    if name=='invoke':
        from engine import ability_rules
        return ability_rules.invoke(w,p,args)
    if name=='spells':return '\n'.join(w.abilities[i]['name']+' — '+w.abilities[i].get('description','') for i in p.abilities if i in w.abilities) or 'No learned abilities.'
    if name=='cast':
        spell,_,target=args.partition(' at ');a=choose([w.abilities[i] for i in p.abilities if i in w.abilities],spell)
        from engine import ability_rules
        if ability_rules.config(a):return ability_rules.cast(w,p,a,target)
        cost=a.get('cost_mp',0)
        if pr['mana']<cost:return 'Not enough mana. Rest at an inn or camp.'
        effect=a.get('effect')
        if effect=='heal':heal(w,p,a.get('power',5));pr['mana']-=cost;return 'Healing magic restores you.'
        if effect=='ward':pr['ward']=a.get('power',3);pr['ward_turns']=5;pr['mana']-=cost;return 'A protective ward strengthens your defence for five incoming hits.'
        if effect=='group_heal':
            for e in w.entities_in_room(r.id):
                if e.is_player:heal(w,e,a.get('power',10))
            pr['mana']-=cost;return 'Your song restores health to the players gathered here.'
        if effect=='tame':return command(ctx,target,'tame')
        if effect=='escape':
            from engine import frontiers
            destination=frontiers.home(w,p)
            if destination is None:return 'No safe recovery location is available yet. Wait for repairs to finish.'
            pr['mana']-=cost;w.move_entity(p.id,destination);return 'You slip away and return to a safe settlement.'
        if effect=='enchant':return command(ctx,target,'enchant')
        if effect=='disenchant':
            obj=choose([w.items[i] for i in p.inventory if i in pr['enchants']],target)
            del pr['enchants'][obj['id']];return 'The enchantment is removed; the sigil is not recovered.'
        if effect!='damage':return 'This ability has no implemented effect. Ask the creator to choose an effect.'
        from engine import combat
        e=combat.target(w,p,target)
        combat.validate(w,p,e)
        pr['mana']-=cost
        return a['name']+': '+combat.strike(w,p,e,power=a.get('power',5),ignore_defense=True,wear=False)
    if name=='enchant':
        if 'enchanting' not in facilities:return 'Use an enchanting desk.'
        target,sep,sigil=args.partition(' with ')
        if not sep:return 'enchant <item> with <sigil>'
        item=choose([w.items[i] for i in dict.fromkeys(p.inventory) if i in w.items],target)
        stone=choose([w.items[i] for i in dict.fromkeys(p.inventory) if w.items.get(i,{}).get('enchant_attack') or w.items.get(i,{}).get('enchant_defense')],sigil)
        if not item.get('slot') and item.get('type') not in ('weapon','armor'):return 'Only equipment can be enchanted.'
        if item['id'] in pr['enchants']:return 'This item type is already enchanted for your character.'
        p.inventory.remove(stone['id']);pr['enchants'][item['id']]={'attack':stone.get('enchant_attack',0),'defense':stone.get('enchant_defense',0)}
        return 'Enchantment applied. It affects your equipment of this type; item instances are not yet separate.'
    if name=='services':return ', '.join(rd.get('services',{})) or 'No services offered here.'
    if name=='service':
        from engine import livelihoods
        if not livelihoods.room_open(w,r.id):return 'This business is closed. Return during opening hours.'
        name_service=args.strip().lower();fee=rd.get('services',{}).get(name_service)
        if fee is None:return 'Available services: '+command(ctx,'','services')
        if p.gold<fee:return 'Not enough gold.'
        if name_service=='haircut':pr['hair']='neatly trimmed'
        elif name_service=='treatment':pr['injury']=0;pr['disease']=0
        else:return 'Unknown service.'
        p.gold-=fee;return name_service.title()+' completed.'
    if name=='study':
        from engine import livelihoods
        if not livelihoods.room_open(w,r.id):return 'This school is closed. Return during opening hours.'
        if 'school' not in facilities:return 'Visit an adventurers school or magical college.'
        a=choose(list(w.abilities.values()),args)
        if a['id'] in p.abilities:return 'You already know that ability.'
        from engine import ability_rules
        ability_rules.lesson_check(w,p,a)
        fee=a.get('training_cost',20)
        if p.gold<fee:return f'Training costs {fee} gold.'
        p.gold-=fee;p.abilities.append(a['id']);return 'Learned '+a['name']+'.'
    if name=='quests':return '\n'.join(q['id']+' ['+pr['quests'].get(q['id'],'available')+'] '+q.get('description','') for q in w.quests.values()) or 'No quests.'
    if name in ('accept','complete'):
        q=choose(list(w.quests.values()),args);qid=q['id']
        if pr['quests'].get(qid)=='complete':return 'Already completed.'
        if name=='accept':pr['quests'][qid]='active';return 'Quest accepted.'
        if pr['quests'].get(qid)!='active':return 'Accept the quest first.'
        if q.get('turn_in_room') and q['turn_in_room']!=r.id:return 'Visit '+w.rooms[q['turn_in_room']].name+' to turn this in.'
        if any(pr['kills'].get(i,0)<n for i,n in q.get('kills',{}).items()):return 'Combat objectives are incomplete.'
        if any(i not in p.explored_rooms for i in q.get('visit_rooms',[])):return 'Exploration objectives are incomplete.'
        consume(p,q.get('required_items',{}),w);p.gold+=q.get('reward_gold',0)
        p.inventory.extend(q.get('reward_items',[]));pr['quests'][qid]='complete';return 'Quest complete. Rewards received.'
    if name=='sell':
        from engine.commands import _is_merchant
        if not any(_is_merchant(w,e) for e in w.entities_in_room(r.id) if not e.is_player):return 'Find a merchant.'
        obj=choose([w.items[i] for i in dict.fromkeys(p.inventory) if i in w.items],args)
        if obj['id'] in p.equipped.values():return 'Unequip it first.'
        p.inventory.remove(obj['id']);value=max(0,obj.get('value',0)//2);p.gold+=value;return f'Sold for {value} gold.'
    if name=='hunt':
        from engine.commands import _cmd_attack
        return _cmd_attack(ctx,args)
    return 'Unknown living-world action.'

# Construction and shipyard are authored by the settlement migration. Older
# worlds can already contain them even when the installed engine predates it.
CRAFTING_STATIONS = (
    'hand', 'forge', 'kitchen', 'enchanting', 'loom', 'workbench',
    'alchemy', 'scriptorium', 'husbandry', 'construction', 'shipyard',
)


def validate(data):
    issues=[]
    ids={k:{o['id'] for o in rows} for k,rows in data.items() if isinstance(rows,list)}
    def ref(kind,value,where):
        if value and value not in ids.get(kind,set()):issues.append(where+': missing '+kind+' '+str(value))
    def counts(value,where):
        if not isinstance(value,dict):issues.append(where+': expected item/count rows');return
        for iid,n in value.items():
            ref('item',iid,where)
            if type(n) is not int or n<1:issues.append(where+': quantity must be a positive integer')
    for r in data.get('room',[]):
        for field,kind in [('resources','resource'),('encounters','encounter')]:
            for key in r.get(field,[]):ref(kind,key,r['id'])
    for d in data.get('recipe',[]):
        counts(d.get('ingredients',{}),d['id']);counts(d.get('outputs',{}),d['id'])
        if d.get('station','hand') not in CRAFTING_STATIONS:
            issues.append(f"{d['id']}: invalid station {d.get('station')!r}; "
                          f"expected one of: {', '.join(CRAFTING_STATIONS)} (recipes.json)")
    for d in data.get('resource',[]):counts(d.get('yields',{}),d['id']);ref('item',d.get('tool'),d['id'])
    for d in data.get('encounter',[]):
        for n in d.get('members',[]):ref('npc',n,d['id'])
        counts(d.get('harvest',{}),d['id'])
    for d in data.get('npc',[]):
        for row in d.get('schedule',[]):
            ref('room',row.get('room'),d['id'])
            if type(row.get('minute',0)) is not int or not 0<=row.get('minute',0)<=59:issues.append(d['id']+': schedule minute must be 0-59')
            if not isinstance(row.get('weekdays',[]),list) or any(type(day) is not int or not 1<=day<=9 for day in row.get('weekdays',[])):issues.append(d['id']+': schedule weekdays must be 1-9')
            if type(row.get('hour')) is not int or not 0<=row['hour']<=24:issues.append(d['id']+': schedule hour must be 0-24')
        for iid in d.get('drops',[]):ref('item',iid,d['id'])
        ref('item',d.get('tame_item'),d['id'])
    for d in data.get('quest',[]):
        counts(d.get('required_items',{}),d['id']);ref('room',d.get('turn_in_room'),d['id'])
        for rid in d.get('visit_rooms',[]):ref('room',rid,d['id'])
        for iid in d.get('reward_items',[]):ref('item',iid,d['id'])
    from engine import resource_nodes
    from engine import escorts
    return issues+resource_nodes.validate(data)+escorts.validate(data)


def on_hit(world,p,attacker,damage):
    pr=progress(p)
    pr['ward_turns']=max(0,pr['ward_turns']-1)
    if damage>=5:pr['injury']=min(100,pr['injury']+2)
    if world.npcs.get(attacker.source_def,{}).get('disease_chance',0)>random.random():pr['disease']=min(100,pr['disease']+10)
    from engine import society,companions
    if society.enabled(world):companions.defend(world,p,attacker)

def snapshot(world):
    if not enabled(world):
        # Real-world player appointments are not a simulation feature.
        retained={k:v for k,v in getattr(world,'living_state',{}).items() if k in ('player_calendar','physical_locks','lock_incidents','resident_watches')}
        return {'state':retained} if retained else {}
    from engine import population
    population.ensure(world)
    from engine import npc_life
    for actor in world.entities.values():
        npc_life.ensure(world,actor)
    from engine.entity_snapshot import snapshot as snapshot_entity
    from engine.frontiers import capture_spawners
    if getattr(world,"expedition_country",False):
        from engine import country_edges
        state(world)["country_surveys"]=country_edges.snapshot(world)
        state(world)["expedition_chunks"]=[list(k) for k in sorted(world.field_chunks)]
    return dict(spawners=capture_spawners(world), migration=world.metadata.get("spawner_migration",0), state=state(world), npcs=[dict(snapshot_entity(e), sleeping=str(getattr(e,'activity','')).startswith('sleeping')) for e in world.entities.values() if not e.is_player and e.alive], floors={r.id:r.items for r in world.rooms.values()})

def restore(world,saved):
    if not saved:return
    if not enabled(world):
        for key in ('player_calendar','physical_locks','lock_incidents','resident_watches'):
            if key in saved.get('state',{}):
                if not hasattr(world,'living_state'):world.living_state={}
                world.living_state[key]=saved['state'][key]
        return
    from engine.core import Entity
    world.living_state=saved.get('state',{})
    from engine import wildlands
    wildlands.restore(world,world.living_state)
    from engine import country_edges
    country_edges.restore(world,world.living_state.get("country_surveys",[]))
    world._settlements_ready=False
    world._population_ready=False
    from engine import settlements
    if settlements.enabled(world):settlements.init(world)
    from engine.frontiers import restore_spawners
    if saved.get('migration',0)==world.metadata.get('spawner_migration',0):restore_spawners(world,saved.get('spawners',{}))
    # Replace only definitions represented in the saved world; new content still spawns.
    old_defs={d['source_def'] for d in saved.get('npcs',[])} | {d['source_def'] for d in state(world).get('companion_reserve',{}).values()} | world.killed_npcs
    for e in list(world.entities.values()):
        if not e.is_player and e.source_def in old_defs:
            if e.id in world.rooms[e.location].entities:world.rooms[e.location].entities.remove(e.id)
            del world.entities[e.id]
    for d in saved.get('npcs',[]):
        d['location']=country_edges.saved_room(world,d.get('location'))
        if saved.get('migration',0)<world.metadata.get('spawner_migration',0) and world.npcs.get(d.get('source_def'),{}).get('spawn_managed') and not d.get('progress',{}).get('companion_owner'):continue
        if d.get('source_def') not in world.npcs or d.get('location') not in world.rooms:continue
        if d.get('source_def') in world.killed_npcs and not d.get('spawner_key') and not d.get('progress',{}).get('companion_owner'):continue
        ent=Entity(**{k:v for k,v in d.items() if k in Entity.__dataclass_fields__})
        from engine import names
        names.migrate_saved(world,ent)
        if d.get('sleeping') is True:ent.activity='sleeping'
        world.add_entity(ent,ent.location)
    for rid,items in saved.get('floors',{}).items():
        rid=country_edges.saved_room(world,rid)
        if rid in world.rooms:world.rooms[rid].items=[i for i in items if i in world.items]
    from engine.quest_discovery import restore_public_reading
    restore_public_reading(world)
    from engine import dynamic_diplomacy
    dynamic_diplomacy.ensure(world)
    for qid in state(world).get('completed_world',[]):
        q=world.quests.get(qid,{})
        apply_effects(world,q)
    from engine import geology_impacts
    geology_impacts.reconcile(world)
    from engine import population
    population.ensure(world)
    # Reconcile temporary generated threats in memory, with no checkpoint write
    # and no kill rewards or healing while restoring a saved world.
    from engine import regional_world, regional_encounters, city_defense
    if regional_world.enabled(world):
        regional_encounters.reconcile(world)
        city_defense.reconcile(world)

def apply_effects(world,q):
    changed = False
    for effect in q.get('world_effects',[]):
        room=world.rooms.get(effect.get('room'))
        if not room:continue
        if effect.get('rehouse_npc'):
            # A ruling affects the disputed lodging only. A subsequent purchase
            # or independent move continues to govern the resident's address.
            for person in world.entities.values():
                if person.is_player or person.source_def!=effect['rehouse_npc'] or person.progress.get('home_property'):continue
                home=person.progress.get('home_room') or world.npcs.get(person.source_def,{}).get('home_room')
                if home==effect.get('from_room'):
                    person.progress['home_room']=room.id
                    if str(getattr(person,'activity','')).startswith('sleep'):person.activity='returning home'
        if effect.get('description'):room.description=effect['description'];changed=True
        if effect.get('exit') and effect.get('target') in world.rooms:room.exits[direction(effect['exit'])]=effect['target'];changed=True
        if effect.get('remove_exit'):room.exits.pop(effect['remove_exit'],None);changed=True
    if changed and hasattr(world,'_compiled_map'):del world._compiled_map


def quest_blocked(world,player,quest):
    """One eligibility rule for acceptance, turn-in, and quest browsers."""
    from engine import quest_progress as qp
    def completed(qid):return qp.status(world,player,qid)=='complete'
    q=quest;p=player;pr=progress(p);s=state(world)
    if any(not completed(i) for i in q.get('prerequisites',[])):return 'Complete the prerequisite quests first.'
    if any(completed(i) for i in q.get('exclusive_with',[])):return 'Another outcome has already been chosen.'
    if any(s.get('flags',{}).get(k)!=v for k,v in q.get('requires_world_flags',{}).items()):return 'World conditions do not permit this quest yet.'
    if q.get('class') and q['class']!=p.char_class:return 'This quest belongs to another class.'
    if q.get('race') and q['race']!=p.race:return 'This quest belongs to another race.'
    if any(pr.get('flags',{}).get(k)!=v for k,v in q.get('requires_character_flags',{}).items()):return 'Your earlier choices do not permit this quest.'
    return ''


def quest_command(ctx,args,name):
    w,p,r=ctx.world,ctx.player,ctx.room;pr=progress(p);s=state(w)
    from engine import quest_progress as qp, knowledge
    def goal(q,kind,key):return qp.count(p,q,kind,key)
    def blocked(q):return quest_blocked(w,p,q)
    if name in ('quests','journal'):
        import re
        rows=[];inventory_counts=Counter(p.inventory)
        query=args.strip().lower();page=1
        page_match=re.search(r'(?:^|\s)page\s+(\d+)$',query)
        if page_match:
            page=max(1,int(page_match.group(1)));query=query[:page_match.start()].strip()
        def matches(q):
            status=qp.status(w,p,q['id'])
            if status=='available' and not any(pair.startswith(q['id']+'|') for pair in p.progress.get('bond_quests',{})):return False
            if query=='here':return (q.get('offer_room') or q.get('turn_in_room'))==r.id
            if query=='active':return status=='active'
            if query=='available':return status=='available' and not blocked(q)
            return not query or query in (q['id']+' '+q['name']+' '+q.get('category','')+' '+q.get('arc_id','')+' '+q.get('region','')).lower()
        matched=[q for q in w.quests.values() if matches(q)]
        start=(page-1)*50
        if len(matched)>50 or page>1:
            rows.append(f'Showing {start+1 if start<len(matched) else 0}–{min(start+50,len(matched))} of {len(matched)} quests. Use {name} '+(query+' ' if query else '')+f'page {page+1} for more; filter by here, active, region, arc or name.')
        for q in matched[start:start+50]:
            if q.get('relationship_quest',{}).get('enabled'):
                for pair,row in p.progress.get('bond_quests',{}).items():
                    if pair.startswith(q['id']+'|'):rows.append(q['name']+' — '+row['status']+' with '+(w.entities[row['target']].name if row.get('target') in w.entities else row['name']))
                if name=='quests':rows.append(q['name']+' — use the NPC Social panel; '+q.get('description',''))
                continue
            status=qp.status(w,p,q['id'])
            why=blocked(q)
            rows.append(f"{q['name']} — {status}"+(' (locked)' if why else '')+'\n'+q.get('description',''))
            if status=='active' or query:
                rows.append('Objectives: '+', '.join([f"{w.items.get(i,{}).get('name',i)} {inventory_counts[i]}/{n}" for i,n in q.get('required_items',{}).items()]+[f"{w.npcs.get(i,{}).get('name',i)} defeated {goal(q,'kills',i)}/{n}" for i,n in q.get('kills',{}).items()]+[w.rooms[i].name+(' [visited]' if goal(q,'visits',i) else ' [unvisited]') for i in q.get('visit_rooms',[])]+[f'{knowledge.action_label(w,k)} {goal(q,"actions",k)}/{v}' for k,v in q.get('actions',{}).items()]))
                if q.get('escort'):
                    from engine import escorts
                    if not pr.get('escort_arrivals',{}).get(q['id']):rows.append(escorts.report(w,p,q))
                    e=q['escort'];rows.append(e['mode'].title()+' '+w.npcs[e['npc']]['name']+' to '+w.rooms[e['destination']].name+(' [arrived]' if pr.get('escort_arrivals',{}).get(q['id']) else ' [waiting]'))
                if q.get('talk_to'):rows.append('Speak to: '+', '.join((w.npcs[i].get('title') or w.npcs[i]['name'])+(' [spoken]' if goal(q,'talks',i) else ' [waiting]') for i in q['talk_to']))
                for witness in q.get('witnesses',[]):
                    npc=w.npcs.get(witness['npc'],{});item=w.items.get(witness['read_item'],{})
                    rows.append('Witness: dialogue '+(npc.get('title') or npc.get('name',witness['npc']))+' OR read '+item.get('name',witness['read_item'])+(' [recorded]' if qp.witnessed(p,q,witness) else ' [waiting]'))
                if q.get('turn_in_room'):rows.append('Turn in: '+w.rooms[q['turn_in_room']].name)
                if q.get('prerequisites'):rows.append('Requires: '+', '.join(w.quests[i]['name'] for i in q['prerequisites'] if i in pr['quests'] and i in w.quests))
                if q.get('consequence'):rows.append('Consequence: '+q['consequence']+' ('+q.get('scope','character')+')')
                reward_items=[w.items.get(i,{}).get('name',i) for i in q.get('reward_items',[])]
                rewards=([str(q['reward_gold'])+' gold'] if q.get('reward_gold') else [])+reward_items+[w.groups.get(g,{}).get('name',g)+' standing '+str(n) for g,n in q.get('reputation',{}).items()]
                from engine import progression
                if progression.config(w)['enabled']:rewards.append(str(q.get('reward_xp',progression.config(w)['quest_xp']))+' XP on first completion'+('; repeat XP requires fresh objectives or supplied goods' if q.get('repeatable') else ''))
                rows.append('Rewards: '+(', '.join(rewards) or 'completion recorded'))
        return '\n'.join(rows) or 'No matching quests.'
    from engine import knowledge
    allowed=knowledge.accepted(w,p) | ({q['id'] for q in knowledge.local_offers(w,p)} if name=='accept' else set())
    q=choose([w.quests[i] for i in allowed],args);qid=q['id'];why=blocked(q)
    if q.get('relationship_quest',{}).get('enabled'):return 'Choose an NPC in the Social panel, then accept or complete this relationship quest with that individual.'
    if why:return why
    if q.get('scope')=='world' and qid in s.get('completed_world',[]):return 'This shared-world outcome has already been completed.'
    if name=='accept':
        if pr['quests'].get(qid)=='active':return 'Already active. Review your journal.'
        if pr['quests'].get(qid)=='complete' and not q.get('repeatable'):return 'Already completed.'
        if s['minute']-pr.get('quest_times',{}).get(qid,-100000)<q.get('cooldown_minutes',worldtime.MINUTES_PER_DAY):return 'This work is not available again yet.'
        if q.get('offer_room') and q['offer_room']!=r.id:return 'Accept this quest at '+w.rooms[q['offer_room']].name+'.'
        if q.get('escort'):
            pr.get('escort_arrivals',{}).pop(qid,None)
            knowledge.teach(w,p,{'rooms':[q['escort']['destination']]})
        qp.start(p,q)
        pr['quests'][qid]='active'
        if q.get('escort'):
            from engine import navigation,escorts
            if 'selected_quests' in pr and qid not in pr['selected_quests'] and len(navigation.selected(w,p))<navigation.MAX_SELECTED:pr['selected_quests'].append(qid)
            escorts.meet(w,p,q)
        return 'Quest accepted. '+q.get('description','')
    if pr['quests'].get(qid)!='active':return 'Accept the quest first.'
    if q.get('turn_in_room') and q['turn_in_room']!=r.id:return 'Turn this in at '+w.rooms[q['turn_in_room']].name+'.'
    if any(goal(q,'kills',i)<n for i,n in q.get('kills',{}).items()):return 'Combat objectives are incomplete.'
    if any(not goal(q,'visits',i) for i in q.get('visit_rooms',[])):return 'Exploration objectives are incomplete.'
    if any(goal(q,'actions',k)<n for k,n in q.get('actions',{}).items()):return 'Activity objectives are incomplete.'
    if any(not goal(q,'talks',i) for i in q.get('talk_to',[])):return 'Speak to the required witnesses first.'
    if any(not qp.witnessed(p,q,row) for row in q.get('witnesses',[])):return 'Record the required witnesses or read their filed statements first.'
    if q.get('escort') and not pr.get('escort_arrivals',{}).get(qid):return 'Arrive together with your quest companion first.'
    consume(p,q.get('required_items',{}),w);p.gold+=q.get('reward_gold',0);p.inventory.extend(q.get('reward_items',[]))
    if q.get('escort'):
        from engine import escorts
        escorts.return_to_start(w,p,q,reset=False)
    pr['quests'][qid]='complete';pr.setdefault('quest_times',{})[qid]=s['minute']
    from engine import society
    for group,amount in q.get('reputation',{}).items():
        if society.enabled(w):society.award(w,p,group,amount)
        else:p.reputation[group]=p.reputation.get(group,0)+amount
    pr.setdefault('flags',{}).update(q.get('character_flags',{}))
    if q.get('scope')=='world':
        s.setdefault('completed_world',[]).append(qid);s.setdefault('flags',{}).update(q.get('world_flags',{}));apply_effects(w,q)
    from engine import progression
    advancement=progression.quest(w,p,q)
    return 'Quest complete. '+q.get('completion_text','Your contribution is recorded.').replace('Nearby quest offers','Local people and request ledgers')+' Rewards received.'+('\n'+advancement if advancement else '')

# One dispatcher also records successful activities for demonstration and profession quests.
_base_command=command
def command(ctx,args,name):
    if not enabled(ctx.world):return 'Living-world rules are not enabled for this world.'
    if name in ('quests','journal','accept','complete'):return quest_command(ctx,args,name)
    if name=='adventures':
        from engine.quest_journal import adventures
        return adventures(ctx,args)
    if name in ('market','marketbuy'):
        from engine import market_shifts
        return market_shifts.command(ctx,args,name)
    if name=='revive':
        if ctx.player.progress.get('permanently_dead'):return 'This world uses permanent death. Create a new character; this character remains in its history.'
        if ctx.player.alive:return 'You are still conscious.'
        from engine import frontiers
        destination=frontiers.home(ctx.world,ctx.player)
        if destination is None:return 'No safe recovery location is available yet. Wait for repairs to finish.'
        ctx.player.progress.pop('death_recorded',None)
        from engine import relationships
        for bond in relationships.state(ctx.world)['bonds'].values():
            if ctx.player.id in bond.get('deceased',[]):bond['deceased'].remove(ctx.player.id)
        from engine.loader import start_room_for
        p=ctx.player;p.hp=max(1,p.max_hp//2);p.gold=max(0,p.gold-5);progress(p)['injury']=min(100,progress(p)['injury']+10)
        from engine import geology_impacts
        geology_impacts.retire_wounds(ctx.world,p,p.max_hp)
        ctx.world.move_entity(p.id,destination,forced=True);return 'Rescuers bring you home. Recovery costs up to 5 gold; seek treatment for your injuries.'
    if name=='route':
        from engine.navigation import route_text
        return route_text(ctx.world,ctx.player,args)
    if name=='guide':
        return 'Use the map and movement controls to explore. Speak with people or read letters and books to find quests. Accept requests through their conversation or readable source; your Quests panel keeps accepted objectives and directions. Survey shows local resources and facilities; Inventory and Crafting show items and learned recipes. Use Help for controls.'
    if name=='gather' and args.strip() and args.strip().casefold() not in ('list','?'):
        from engine import gathering
        name,obj=gathering.identify(ctx.world,gathering.sources(ctx.world,ctx.room.id),args)
        args=obj['id']
    result=_base_command(ctx,args,name)
    if name in ('rest','sleep'):return result  # Recorded on actual completion, not response prose.
    success=('Gathered:', 'Harvested without', 'Created:', 'Your tent is pitched.', 'Your campfire is lit.', 'You rest for', 'Enchantment applied.', 'Learned ', 'Sold for ', 'Haircut completed.', 'Treatment completed.')
    if result.startswith(success):
        actions=progress(ctx.player).setdefault('actions',{});actions[name]=actions.get(name,0)+1
        if name=='harvest':
            enc=choose([catalog(ctx.world,'encounters')[i] for i in details(ctx.world,ctx.room.id).get('encounters',[])],args)
            key='harvest:'+enc['id'];actions[key]=actions.get(key,0)+1
    return result
COMMANDS.update(adventures=('Browse long story adventures by region','adventures [region] [page 2]'),market=('Find reachable rotating provision counters','market [item]'),marketbuy=('Buy from a local staffed provision counter','marketbuy <item>'),journal=('Review quest objectives','journal'), route=('Find the next direction to a named place','route adventurers school'),guide=('Read the demonstration guide','guide'),revive=('Recover after defeat','revive'))


def material_index(world,query='',selected_ids=None):
    """Build live reverse source/use references in one pass, not item × world.

    selected_ids bounds interactive lookup; callers needing a complete reference
    can still request all rows. Nothing derived is stored on the world or saved.
    """
    selected=set(selected_ids) if selected_ids is not None else None
    rows={iid:dict(id=iid,name=item['name'],sources=[],uses=[])
          for iid,item in world.items.items()
          if (selected is None or iid in selected)
          and (not query or query.lower() in (iid+' '+item.get('name','')).lower())}
    def add(iid,field,text):
        if iid in rows:rows[iid][field].append(text)
    for room in world.rooms.values():
        for iid in dict.fromkeys(room.items):add(iid,'sources','floor: '+room.name)
    for npc in world.npcs.values():
        name=npc.get('name',npc.get('id','NPC'))
        for iid in dict.fromkeys(x.get('item') for x in npc.get('stock',[])):add(iid,'sources','shop: '+name)
        for iid in dict.fromkeys(npc.get('drops',[])):add(iid,'sources','drop: '+name)
        add(npc.get('tame_item'),'uses','befriend '+name)
    for node in catalog(world,'resources').values():
        for iid in node.get('yields',{}):add(iid,'sources','gather: '+node['name'])
        add(node.get('tool'),'uses','tool for '+node['name'])
    for enc in catalog(world,'encounters').values():
        for iid in enc.get('harvest',{}):add(iid,'sources','harvest: '+enc['name'])
    for rid,recipe in catalog(world,'recipes').items():
        name=recipe.get('name',rid)
        for iid in recipe.get('outputs',{}):add(iid,'sources','make: '+name)
        for iid in recipe.get('ingredients',{}):add(iid,'uses','recipe: '+name)
    for cls in world.classes.values():
        for iid in dict.fromkeys(cls.get('starting_equipment',[])):add(iid,'sources','starting kit: '+cls['name'])
    for iid,row in rows.items():
        item=world.items[iid];uses=row['uses']
        if item.get('slot') or item.get('type') in ('weapon','armor'):uses.append('equip')
        if item.get('type')=='consumable':uses.append('use')
        if item.get('read_text'):uses.append('read')
        if item.get('camp_tent'):uses.append('camp pitch')
        if item.get('fuel'):uses.append('fire light')
        if item.get('enchant_attack') or item.get('enchant_defense'):uses.append('enchant')
    return list(rows.values())

_previous_command=command
def command(ctx,args,name):
    if name=='materials':
        from engine import knowledge, item_catalog
        selected,total,request=item_catalog.page(ctx.world,args,player=ctx.player)
        known_rooms=knowledge.ids(ctx.world,ctx.player,'rooms');known_recipes=knowledge.ids(ctx.world,ctx.player,'recipes')
        lines=[item_catalog.header('Known materials',total,request)]
        for item in selected:
            lines.append(item['name'])
            sources=[r.name for rid,r in ctx.world.rooms.items() if rid in known_rooms and item['id'] in getattr(ctx.world,'room_details',{}).get(rid,{}).get('items',[])]
            uses=[r['name'] for rid,r in getattr(ctx.world,'recipes',{}).items() if rid in known_recipes and item['id'] in r.get('ingredients',{})]
            lines.append('Known authored floor sources (availability unconfirmed): '+(', '.join(sources[:8]) or 'None recorded.'))
            lines.append('Known recipe uses: '+((', '.join(uses[:8])+ (f'; +{len(uses)-8} more' if len(uses)>8 else '')) or 'None learned.'))
            making=[r for rid,r in getattr(ctx.world,'recipes',{}).items() if rid in known_recipes and item['id'] in r.get('outputs',{})]
            if making:lines.append('Known ways to make it: '+ '; '.join(r['name']+' ('+r.get('station','hand')+'): '+', '.join(str(n)+' '+ctx.world.items.get(i,{}).get('name',i) for i,n in r.get('ingredients',{}).items()) for r in making[:8]))
            places={}
            for res in getattr(ctx.world,'room_details',{}).get(ctx.player.location,{}).get('resources',[]):
                resource=getattr(ctx.world,'resources',{}).get(res,{})
                if item['id'] in resource.get('yields',{}):places[(ctx.player.location,res)]=ctx.world.rooms[ctx.player.location].name+' — '+resource.get('name',res)+' (survey here)'
            for qid in knowledge.accepted(ctx.world,ctx.player):
                for entry in ctx.world.quests[qid].get('navigation_supply_sources',{}).get(item['id'],[]):
                    rid=entry.get('room')
                    if rid in known_rooms and rid in ctx.world.rooms:places[(rid,entry.get('label',''))]=ctx.world.rooms[rid].name+(' — '+entry['label'] if entry.get('label') else '')
            if places:lines.append('Local or explicitly taught supply locations (availability unconfirmed): '+ '; '.join(list(places.values())[:8]))

        return '\n'.join(lines)
    return _previous_command(ctx,args,name)
COMMANDS['materials']=('Find item sources and practical uses','materials honey')

_base_validate=validate
def validate(data):
    # Reject malformed creator structures before any nested iteration.
    from engine.living_schema import DEFAULTS
    issues=[]
    for kind,defaults in DEFAULTS.items():
        for obj in data.get(kind,[]):
            for key,default in defaults.items():
                if key not in obj:continue
                value=obj[key]
                if isinstance(default,(dict,list,bool)) and type(value) is not type(default):
                    issues.append(obj['id']+': '+key+' has the wrong value type')
            for field in ('schedule','world_effects'):
                if field in obj and isinstance(obj[field],list) and any(not isinstance(x,dict) for x in obj[field]):issues.append(obj['id']+': '+field+' requires rows of objects')
    if issues:return issues
    issues=_base_validate(data)
    by={k:{r['id']:r for r in v if isinstance(r,dict) and 'id'in r} for k,v in data.items() if isinstance(v,list)}
    def ref(kind,key,where):
        if key and key not in by.get(kind,{}):issues.append(f'{where}: missing {kind} {key}')
    def nonnegative(obj,key):
        if key in obj and (type(obj[key]) not in (int,float) or obj[key]<0):issues.append(obj['id']+': '+key+' must be nonnegative')
    for kind in ('item','ability','quest','recipe','resource','encounter','npc','class'):
        for obj in data.get(kind,[]):
            for key in ('reward_gold','starting_gold','cooldown_minutes','minutes','renewal_minutes','harvest_minutes','harvest_damage','cost_mp','power','companion_attack','training_cost','alcohol','cure_injury','cure_disease','enchant_attack','enchant_defense'):nonnegative(obj,key)
            for key in ('chance','raw_risk','disease_chance','aggression_chance'):
                if key in obj and (type(obj[key]) not in (int,float) or not 0<=obj[key]<=1):issues.append(obj['id']+': '+key+' must be 0–1')
    for recipe in data.get('recipe',[]):
        for qid in recipe.get('prerequisites',[]):ref('quest',qid,recipe['id'])
    for q in data.get('quest',[]):
        if q.get('progress_scope','lifetime') not in ('lifetime','accepted'):issues.append(q['id']+': progress_scope must be lifetime or accepted')
        if type(q.get('chapter',0)) is not int or q.get('chapter',0)<0:issues.append(q['id']+': chapter must be a nonnegative whole number')
        for field in ('arc_id','region'):
            if not isinstance(q.get(field,''),str):issues.append(q['id']+': '+field+' must be text')
        for witness in q.get('witnesses',[]):
            if not isinstance(witness,dict) or not isinstance(witness.get('npc'),str) or not witness.get('npc') or not isinstance(witness.get('read_item'),str) or not witness.get('read_item'):
                issues.append(q['id']+': witnesses require npc and read_item IDs');continue
            ref('npc',witness['npc'],q['id']);ref('item',witness['read_item'],q['id'])
            item=by.get('item',{}).get(witness['read_item'])
            if item is not None and not item.get('read_text'):issues.append(q['id']+': witness statement must have read_text')
        for key in q.get('actions',{}):
            verb,separator,target=key.partition(':')
            kind={'read':'item','craft':'recipe','cook':'recipe','gather':'resource','harvest':'encounter'}.get(verb)
            if separator and kind:
                ref(kind,target,q['id'])
                if not target:issues.append(q['id']+': targeted action requires an ID')
                if verb=='cook' and target in by.get('recipe',{}) and by['recipe'][target].get('kind')!='cooking':issues.append(q['id']+': cook action requires a cooking recipe')
        for field in ('prerequisites','exclusive_with'):
            for key in q.get(field,[]):ref('quest',key,q['id'])
        for nid in q.get('talk_to',[]):ref('npc',nid,q['id'])
        ref('room',q.get('offer_room'),q['id']);ref('class',q.get('class'),q['id']);ref('race',q.get('race'),q['id'])
        if q.get('scope','character') not in ('character','world'):issues.append(q['id']+': scope must be character or world')
        if (q.get('world_effects') or q.get('world_flags')) and q.get('scope')!='world':issues.append(q['id']+': world effects require world scope')
        for effect in q.get('world_effects',[]):
            ref('room',effect.get('room'),q['id']);ref('room',effect.get('target'),q['id'])
            from engine.directions import direction as normalize_direction
            for key in ('exit','remove_exit'):
                if effect.get(key):
                    try:normalize_direction(effect[key])
                    except ValueError:issues.append(q['id']+': invalid effect direction')
        for nid in q.get('kills',{}):ref('npc',nid,q['id'])
        for field in ('kills','actions'):
            for key,n in q.get(field,{}).items():
                if type(n) is not int or n<1:issues.append(q['id']+': '+field+' requires positive whole counts')
    for encounter in data.get('encounter',[]):
        ref('npc',encounter.get('harvest_source'),encounter['id'])
        if encounter.get('harvest_source') and encounter['harvest_source'] not in encounter.get('members',[]):issues.append(encounter['id']+': harvest source must be an encounter member')
    visiting=set();visited=set()
    def visit(qid):
        if qid in visiting:issues.append(qid+': cyclic quest prerequisite');return
        if qid in visited:return
        visiting.add(qid)
        for key in by.get('quest',{}).get(qid,{}).get('prerequisites',[]):visit(key)
        visiting.remove(qid);visited.add(qid)
    for qid in by.get('quest',{}):visit(qid)
    from engine import market_shifts
    return issues+market_shifts.validate(data)

# Explicit knowledge references are creator-editable and validated without mutation.
_knowledge_validate=validate
def validate(data):
    from engine import knowledge
    from engine import progression
    from engine import ability_rules
    return _knowledge_validate(data)+knowledge.validate(data)+progression.validate(data)+ability_rules.validate(data)
