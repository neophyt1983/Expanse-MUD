#!/usr/bin/env python3
"""Read-only Creator audit of authored starting supplies and material chains.

Catalog membership and an item's location field are not physical stock. This
report follows real floor/container/inventory/shop placements, placed gathering
and encounter sources, and discoverable recipe instructions. It never sends
hidden origins to a player, creates stock, or changes the source world.
"""
import argparse
from collections import Counter, defaultdict, deque
import json
from pathlib import Path


def _positive(table):
    return {key:value for key,value in (table or {}).items() if type(value) is int and value>0}


def _components(graph):
    """Iterative strongly connected components, including long recipe chains."""
    reverse=defaultdict(set)
    for node,edges in graph.items():
        for other in edges:reverse[other].add(node)
    seen=set();order=[]
    for start in graph:
        if start in seen:continue
        pending=[(start,False)]
        while pending:
            node,expanded=pending.pop()
            if expanded:order.append(node);continue
            if node in seen:continue
            seen.add(node);pending.append((node,True))
            pending.extend((other,False) for other in graph.get(node,()) if other not in seen)
    seen=set();result=[]
    for start in reversed(order):
        if start in seen:continue
        members=[];pending=[start];seen.add(start)
        while pending:
            node=pending.pop();members.append(node)
            for other in reverse.get(node,()):
                if other not in seen:seen.add(other);pending.append(other)
        if len(members)>1 or start in graph.get(start,()):result.append(sorted(members))
    return sorted(result)


def audit(data,metadata):
    by={kind:{row['id']:row for row in data.get(kind,[]) if isinstance(row,dict) and isinstance(row.get('id'),str)}
        for kind in ('items','rooms','npcs','recipes','resources','encounters','buildings','groups','quests')}
    items,rooms,npcs,recipes=by['items'],by['rooms'],by['npcs'],by['recipes']
    starts={metadata.get('start_room')}
    starts.update(row.get('start_room') for row in by['groups'].values() if row.get('visibility')=='playable')
    starts={room for room in starts if room in rooms};reachable=set(starts);pending=deque(starts)
    while pending:
        for target in rooms[pending.popleft()].get('exits',{}).values():
            if isinstance(target,str) and target in rooms and target not in reachable:
                reachable.add(target);pending.append(target)
    sources=defaultdict(list);source_counts=Counter();initial=Counter();renewable=set();available=set();gated=set()
    invalid=[];resource_sources=[];recipe_sources=defaultdict(list);producers=defaultdict(list);legacy_unlimited=[]

    def add(item,kind,ident,room=None,*,quantity=0,repeats=False,condition=None):
        if item not in items:
            invalid.append({'item':item,'source':ident,'kind':kind});return
        row={'kind':kind,'id':ident}
        if room:row['room']=room
        if quantity:row['initial_quantity']=quantity;initial[item]+=quantity
        if condition:row['condition']=condition
        source_counts[item]+=1
        if len(sources[item])<8:sources[item].append(row)
        available.add(item)
        if repeats:renewable.add(item)

    def conditional(item,kind,ident,reason):
        if item not in items:
            invalid.append({'item':item,'source':ident,'kind':kind});return
        gated.add(item);source_counts[item]+=1
        if len(sources[item])<8:sources[item].append({'kind':kind,'id':ident,'condition':reason})

    def npc_location(row):
        for key in ('spawn_room','workplace_room','guard_room'):
            if row.get(key) in rooms:return row[key]
        for key in ('workplace_building','guard_building'):
            places=by['buildings'].get(row.get(key),{}).get('rooms',[])
            if places and places[0] in rooms:return places[0]
        return None

    active_npcs={ident:npc_location(row) for ident,row in npcs.items()
                 if not row.get('spawn_managed') and npc_location(row) in reachable}
    conditional_npcs={}
    facilities={'hand'}
    for rid in sorted(reachable):
        room=rooms[rid];facilities.update(room.get('facilities',[]))
        for iid,count in Counter(room.get('items',[])).items():add(iid,'floor',rid,rid,quantity=count)
        if room.get('search_reward'):
            conditional(room['search_reward'],'landmark_search',rid,
                        'Requires the configured expedition search at this real landmark; not initial floor stock.')
        for fixture in room.get('locks',[]):
            for iid,count in Counter(fixture.get('contents',[])).items():
                add(iid,'container',rid+':'+str(fixture.get('id')),rid,quantity=count,condition='Container access may be restricted.')
        workshop=room.get('workshop',{}) or {}
        for iid,count in _positive(workshop.get('initial_stock',{})).items():add(iid,'workshop_stock',rid,rid,quantity=count)
        for recipe in workshop.get('recipes',[]):recipe_sources[recipe].append({'kind':'posted_workshop','id':rid})
        for resource in room.get('resources',[]):
            definition=by['resources'].get(resource)
            if definition:resource_sources.append((rid,definition,'resource'))
        for encounter in room.get('encounters',[]):
            definition=by['encounters'].get(encounter,{})
            if definition.get('chance',1)<=0:continue
            for ident in definition.get('members',[]):
                if ident in npcs:conditional_npcs.setdefault(ident,rid)
            if definition.get('harvest'):resource_sources.append((rid,definition,'encounter_harvest'))
        for spawner in room.get('spawners',[]):
            if (isinstance(spawner,dict) and spawner.get('count',1)>0 and spawner.get('chance',1)>0
                    and spawner.get('npc') in npcs):conditional_npcs.setdefault(spawner['npc'],rid)

    for ident,rid in {**conditional_npcs,**active_npcs}.items():
        row=npcs[ident];condition=None if ident in active_npcs else 'Requires the authored encounter/spawner to appear.'
        for iid,count in Counter(row.get('inventory',[])).items():
            add(iid,'npc_inventory',ident,rid,quantity=count if ident in active_npcs else 0,condition=condition or 'Held by an NPC; trade, permission or another actual transfer is required.')
        for stock in row.get('stock',[]) or []:
            if not stock.get('item'):continue
            quantity=stock.get('qty',1)
            if type(quantity) is int and quantity>0:add(stock.get('item'),'merchant_stock',ident,rid,quantity=quantity,condition=condition)
            elif type(quantity) is int and quantity<0:
                legacy_unlimited.append({'npc':ident,'item':stock.get('item')})
                add(stock.get('item'),'legacy_unlimited_merchant',ident,rid,condition='Legacy unlimited stock; requires separate author review.')
        for iid in row.get('drops',[]):add(iid,'fixed_loot',ident,rid,condition='Requires an actual death and released loot.')
        for tier in (row.get('loot_table',{}) or {}).get('tiers',[]):
            for entry in (tier.get('items',[]) if tier.get('chance',0)>0 else []):
                if entry.get('weight',0)>0 and entry.get('max',0)>0:add(entry.get('item'),'rolled_loot',ident,rid,condition='Probabilistic combat loot at an eligible tier.')
            for entry in tier.get('bonus',[]):
                if entry.get('chance',0)>0 and entry.get('max',0)>0:add(entry.get('item'),'rolled_loot',ident,rid,condition='Probabilistic bonus loot.')
        for recipe in row.get('knowledge',{}).get('recipes',[]):recipe_sources[recipe].append({'kind':'npc_instruction','id':ident})

    for qid,quest in by['quests'].items():
        reward=quest.get('reward_items',[])
        for iid in (reward.keys() if isinstance(reward,dict) else reward):
            conditional(iid,'quest_reward',qid,'Requires the real quest source, prerequisites and completion; not initial stock.')

    readable_sources=defaultdict(list)
    for iid,item in items.items():
        if item.get('read_text'):
            for recipe in item.get('knowledge',{}).get('recipes',[]):readable_sources[recipe].append(iid)
    station_missing={};blocked_recipes={};gated_recipes=set();done_resources=set();done_recipes=set()

    def recipe_tools(recipe):
        result=set(recipe.get('required_tools',[]) or [])
        if recipe.get('tool'):result.add(recipe['tool'])
        return result

    def instruction(recipe,pool=None):
        pool=available if pool is None else pool
        ident=recipe['id']
        if any(iid in pool for iid in readable_sources[ident]):return True
        if recipe_sources[ident]:return True
        if recipe.get('knowledge_scope')=='public':return True
        return recipe.get('knowledge_scope')!='private' and recipe.get('location') in reachable

    for rid,recipe in recipes.items():
        for iid in _positive(recipe.get('outputs',{})):producers[iid].append(rid)
        if recipe.get('station','hand') not in facilities:station_missing[rid]=recipe.get('station','hand')
        if recipe.get('prerequisites') or recipe.get('required_abilities'):
            gated_recipes.add(rid)
            gated.update(_positive(recipe.get('outputs',{})))

    changed=True
    while changed:
        changed=False
        for index,(room,resource,kind) in enumerate(resource_sources):
            if index in done_resources:continue
            outputs=_positive(resource.get('yields' if kind=='resource' else 'harvest',{}))
            tool=resource.get('tool')
            if tool and tool not in available:continue
            if resource.get('requires_species') or resource.get('requires_resources'):
                # A live herd/installed subresource requires a separate current
                # site check, not a catalog-level promise of renewable output.
                for iid in outputs:conditional(iid,kind,resource['id'],'Requires an actual suitable live herd or installed source at this site.')
                done_resources.add(index)
                continue
            if index not in done_resources:
                for iid,quantity in outputs.items():
                    finite=resource.get('reserve_batches')
                    add(iid,kind,resource['id'],room,repeats=not finite,
                        condition='Finite reserve of '+str(finite)+' batches.' if finite else
                        'Renewal, seasons, labor and continued source survival still apply.')
                done_resources.add(index);changed=True
        for rid,recipe in recipes.items():
            if rid in gated_recipes or rid in station_missing:continue
            inputs=set(_positive(recipe.get('ingredients',{})))
            if not inputs<=available or not recipe_tools(recipe)<=available:continue
            if not set(recipe.get('requires_reading',[]))<=available or not instruction(recipe):continue
            if recipe.get('requires_species') or recipe.get('requires_resources'):
                gated.update(_positive(recipe.get('outputs',{})));continue
            outputs=_positive(recipe.get('outputs',{}))
            repeats=bool(inputs) and inputs<=renewable
            if rid not in done_recipes:
                for iid in outputs:add(iid,'recipe',rid,repeats=repeats,condition='Consumes the specified inputs for each batch.')
                done_recipes.add(rid);changed=True
            elif repeats and not set(outputs)<=renewable:
                renewable.update(outputs);changed=True

    # An unknown downstream product is conditional, rather than source-less,
    # when all its missing materials ultimately come from a real gated source.
    possible=available|gated;changed=True
    while changed:
        changed=False
        for rid,recipe in recipes.items():
            needs=set(_positive(recipe.get('ingredients',{})))|recipe_tools(recipe)|set(recipe.get('requires_reading',[]))
            outputs=set(_positive(recipe.get('outputs',{})))
            if (rid not in station_missing and needs<=possible and instruction(recipe,possible)
                    and not outputs<=possible):
                fresh=outputs-possible;possible.update(fresh);gated.update(fresh);changed=True
        for _,resource,kind in resource_sources:
            if resource.get('tool') and resource['tool'] not in possible:continue
            outputs=set(_positive(resource.get('yields' if kind=='resource' else 'harvest',{})))
            if not outputs<=possible:possible.update(outputs);gated.update(outputs);changed=True

    unavailable=set(items)-available
    graph={iid:set() for iid in unavailable}
    for rid,recipe in recipes.items():
        blockers=[]
        missing=sorted((set(_positive(recipe.get('ingredients',{})))|recipe_tools(recipe)|set(recipe.get('requires_reading',[])))-available)
        if missing:blockers.append({'missing_items':missing})
        if not instruction(recipe):blockers.append({'missing_instruction':True})
        if rid in station_missing:blockers.append({'missing_station':station_missing[rid]})
        if rid in gated_recipes:blockers.append({'quest_or_ability_gate':True})
        if recipe.get('requires_species') or recipe.get('requires_resources'):blockers.append({'live_site_dependency':True})
        if blockers:blocked_recipes[rid]=blockers
        dependencies=set(missing)
        if not instruction(recipe):dependencies.update(readable_sources[rid])
        for iid in _positive(recipe.get('outputs',{})):
            if iid in graph:graph[iid].update(dependencies&unavailable)
    for _,resource,kind in resource_sources:
        if resource.get('tool') in unavailable:
            for iid in resource.get('yields' if kind=='resource' else 'harvest',{}):
                if iid in graph:graph[iid].add(resource['tool'])
    cycles=_components(graph);circular={iid for component in cycles for iid in component}
    statuses={iid:('renewable' if iid in renewable else 'finite_initial' if initial[iid] else
                    'obtainable' if iid in available else 'gated' if iid in gated else
                    'bootstrap_cycle' if iid in circular else 'unavailable') for iid in items}

    tasks=[]
    def task(kind,ident,room,requirements,stock=None,recipe=None):
        required=_positive(requirements);missing=[iid for iid in required if iid not in available]
        blockers=list(blocked_recipes.get(recipe,[])) if recipe else []
        row={'kind':kind,'id':ident,'room':room,'room_reachable':room in reachable,'requirements':required,'unavailable':missing,
             'material_chain_ready':not missing,'recipe_blockers':blockers,
             'renewable_inputs':all(iid in renewable for iid in required)}
        if stock is not None:
            row['initial_shortfall']={iid:max(0,count-stock.get(iid,0)) for iid,count in required.items() if stock.get(iid,0)<count}
            row['initial_batch_supplied']=not row['initial_shortfall']
        tasks.append(row)
    for rid,room in rooms.items():
        cfg=room.get('clinical_services',{}) or {}
        if cfg.get('enabled'):
            cabinet=next((row for row in room.get('locks',[]) if row.get('id')==cfg.get('container')),{})
            task('clinic',rid,rid,cfg.get('supplies',{}),Counter(cabinet.get('contents',[])))
        for job in room.get('employment',[]) or []:
            recipe=recipes.get(job.get('recipe'),{})
            task('employment',job.get('id'),rid,recipe.get('ingredients',{}),
                 (room.get('workshop',{}) or {}).get('initial_stock',{}),recipe.get('id'))
    for rid,recipe in recipes.items():
        if recipe.get('artwork'):task('artwork',rid,recipe.get('location'),recipe.get('ingredients',{}),recipe=rid)

    rows=[{'id':iid,'name':items[iid].get('name',iid),'status':statuses[iid],
           'initial_units':initial[iid],'source_count':source_counts[iid],'sources':sources[iid],
           'recipe_outputs':producers[iid][:12]} for iid in sorted(items)]
    return {'scope':'Creator-only authored starting-world supply audit; no live save or player knowledge is changed.',
            'method':'Structural source/material reachability. Initial quantities are counted; concurrent demand, wages, travel access, skill, seasons and actual remaining stock still require runtime checks.',
            'summary':{'items':len(items),'rooms':len(rooms),'structurally_reachable_rooms':len(reachable),
                       'starting_rooms':sorted(starts),'statuses':dict(Counter(statuses.values())),
                       'blocked_recipes':len(blocked_recipes),'bootstrap_components':len(cycles),
                       'service_tasks':len(tasks),'tasks_with_unavailable_inputs':sum(bool(row['unavailable']) for row in tasks)},
            'items':rows,'blocked_recipes':blocked_recipes,'bootstrap_cycles':cycles,'tasks':tasks,
            'invalid_references':invalid,'legacy_unlimited_stocks':legacy_unlimited,
            'recipes_without_consumable_inputs':[rid for rid,recipe in recipes.items() if recipe.get('outputs')
                and not _positive(recipe.get('ingredients',{})) and not recipe.get('requires_species')
                and not recipe.get('requires_resources')]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.input.resolve();target=args.output.resolve()
    if target.is_relative_to(source):parser.error('Write the report outside the read-only source world.')
    data={path.stem:json.loads(path.read_text()) for path in source.glob('*.json')
          if path.stem in ('items','rooms','npcs','recipes','resources','encounters','buildings','groups','quests')}
    metadata=json.loads((source/'metadata.json').read_text());report=audit(data,metadata)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
