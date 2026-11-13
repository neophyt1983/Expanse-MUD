"""Discover and inspect only sources in the player's current room."""
from math import ceil

from engine import climate, ecology, geology_impacts, hand_resources, living, resource_nodes, worldtime


def sources(world, room):
    resources = getattr(world,'resources',{})
    encounters = getattr(world,'encounters',{})
    return ([('gather',resources[key]) for key in dict.fromkeys(resource_nodes.active_resources(world,room)) if key in resources]
            + [('harvest',encounters[key]) for key in dict.fromkeys(living.details(world,room).get('encounters',[]))
               if key in encounters and encounters[key].get('harvest')])


def goods(world, outputs):
    from engine.item_catalog import goods_amount
    return ', '.join(goods_amount(world.items.get(i,{'name':'Unknown item'}),n) for i,n in outputs.items()) or 'No products recorded.'

def renewal(now, due):
    day = int(due)//1500-int(now)//1500
    when = ('today' if day==0 else 'tomorrow' if day==1 else f'in {day} days')
    clock=int(ceil(due))%1500
    return f'Ready {when} at {clock//60:02d}:{clock%60:02d} ({ceil(due-now)} game minutes).'


def encounter_state(world, room, source):
    state=living.state(world);record=state['encounters'].get(room+':'+source['id'])
    if geology_impacts.room_unusable(world,room):return 'This location is temporarily unusable while hazard damage is repaired.'
    if not record or not record.get('active') or record.get('cleared'):return 'The encounter is absent or has been permanently cleared.'
    needed=source.get('harvest_source')
    if needed and not any(e and e.alive and e.location==room and e.source_def==needed
                          for e in (world.entities.get(i) for i in record.get('members',[]))):
        return 'The harvest source has been destroyed or is no longer here.'
    due=record['last_harvest']+source.get('harvest_minutes',120)
    if due>state['minute']:return 'There is not enough to harvest yet. '+renewal(state['minute'],due)
    return ''


def prerequisite(world,player,source):
    skill=source.get('required_skill')
    if skill and skill not in player.abilities and player.progress.get('skills',{}).get(skill,0)<source.get('required_skill_level',1):
        return 'Learn '+getattr(world,'abilities',{}).get(skill,{}).get('name',skill.replace('_',' '))+'.'
    return ''


def resource_state(world, player, room, source):
    state=living.state(world);now=state['minute'];key=room+':'+source['id']
    problems=[reason] if (reason:=prerequisite(world,player,source)) else []
    blocked=geology_impacts.resource_blocked(world,room,source['id'])
    if blocked or geology_impacts.room_unusable(world,room):problems.append(blocked or 'This site is closed for repairs.')
    if not ecology.in_season(world,source,room):
        local=climate.conditions(world,room)
        seasons=source.get('seasons',[])
        if seasons and local['season'] not in seasons:problems.append('Harvest in '+', '.join(seasons)+'. It is '+local['season']+' here.')
        if source.get('species') and not source.get('temperature_min_c',0)<=local['temperature_c']<=source.get('temperature_max_c',45):
            problems.append(f"Requires {source.get('temperature_min_c',0)}–{source.get('temperature_max_c',45)} °C. It is {local['temperature_c']} °C here.")
    if not blocked and not geology_impacts.room_unusable(world,room) and not ecology.available(world,room,source):
        problems.append('The required wildlife or local supplies are missing.')
    tool=source.get('tool')
    if tool and tool not in player.inventory:problems.append('Bring '+world.items.get(tool,{}).get('name','the required tool')+'.')
    if hand_resources.configured(source):
        detail=hand_resources.describe(world,room,source)
        if 'ready to collect.' not in detail:problems.append(detail)
    elif resource_nodes.managed(source,world.items):
        if resource_nodes.exhausted(world,room,source):problems.append('Permanently exhausted.')
        else:
            last,planted=resource_nodes._history(world,key)
            start=max((v for v in (last,planted) if v is not None),default=None)
            if start is not None and start+source.get('renewal_minutes',60)>now:
                problems.append(renewal(now,start+source.get('renewal_minutes',60)))
            elif not problems and not resource_nodes.available(world,room,source):problems.append('Unavailable here.')
    else:
        ledger=state.get('shared_resource_times',{}) if source.get('shared_renewal') else state['nodes']
        due=ledger.get(key,-100000)+source.get('renewal_minutes',60)
        if due>now:problems.append(renewal(now,due))
    return ' '.join(problems)


def listing(world, player):
    rows=[]
    for action,source in sources(world,player.location):
        encounter=action=='harvest'
        blocked=encounter_state(world,player.location,source) if encounter else resource_state(world,player,player.location,source)
        if encounter:
            tool=source.get('tool')
            if tool and tool not in player.inventory:blocked='Bring '+world.items.get(tool,{}).get('name','the required tool')+'.'
            blocked=prerequisite(world,player,source) or blocked
        outputs=source.get('harvest' if encounter else 'yields',{})
        detail=goods(world,outputs)+' · '+(blocked or 'Ready now.')
        if encounter and source.get('harvest_damage',0):detail+=f" Collecting costs {source['harvest_damage']} HP. The source survives."
        rows.append(dict(id=action+':'+source['id'],label=source['name'],detail=detail,
                         group='Unavailable here' if blocked else 'Ready to gather',
                         actions=[dict(label='Gather '+source['name'],command=action+' '+source['id'],disabled=bool(blocked),reason=blocked)]))
    return rows


def identify(world, entries, query):
    from engine import item_catalog
    needle=query.strip().casefold()
    exact=[pair for pair in entries if pair[1]['id']==query.strip() or pair[1]['id'].casefold()==needle or pair[1]['name'].casefold()==needle]
    if len(exact)==1:return exact[0]
    choices=exact or [pair for pair in entries if needle in pair[1]['name'].casefold() or any(
        needle in world.items.get(i,{}).get('name','').casefold() for i in (pair[1].get('harvest') or pair[1].get('yields',{})))]
    if len(choices)==1:return choices[0]
    if choices:raise ValueError(item_catalog.ambiguity([row for _,row in choices]))
    raise ValueError('No local source matches that name. Type gather to see what is here.')
