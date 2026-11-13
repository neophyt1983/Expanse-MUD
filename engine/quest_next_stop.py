"""Resolve authored, learned intermediate stops without scanning unseen content.

No new knowledge is taught here. Inventory/progress and explicitly disclosed
quest sources are enough; live remote NPC positions/stock are never inspected.
"""
from collections import Counter



def next_stop(world,player,q):
    learned=player.progress.get('knowledge',{})
    known=set(learned.get('rooms',[]))|{player.location};carried=Counter(player.inventory)
    recipes=getattr(world,'recipes',{})
    allowed=[recipes[r] for r in q.get('knowledge',{}).get('recipes',[]) if r in recipes and r in learned.get('recipes',[])]
    sources=q.get('navigation_supply_sources',{})
    def count(kind,key):
        current=player.progress.get(kind,{}).get(key,0)
        if q.get('progress_scope','lifetime')!='accepted':return current
        run=player.progress.get('quest_runs',{}).get(q['id'])
        return max(0,current-run.get(kind,{}).get(key,current)) if run else 0
    def source(iid,amount,seen=()):
        if carried[iid]>=amount:return None
        if iid in seen or len(seen)>=8:return ([], 'Review the journal for a known supply source.')
        missing=amount-carried[iid]
        choices=[r for r in allowed if r.get('outputs',{}).get(iid,0)>0]
        if choices:
            import math
            recipe=choices[0];batches=math.ceil(missing/recipe['outputs'][iid])
            for ingredient,n in recipe.get('ingredients',{}).items():
                if carried[ingredient]<n*batches:
                    found=source(ingredient,n*batches,seen+(iid,))
                    if found:return found
            station=recipe.get('station','hand')
            if station=='hand':return ([player.location], 'Make '+recipe.get('name','the required item')+' with your carried materials.')
            locations=q.get('navigation_recipe_stations',{}).get(recipe['id'],[])
            return ([rid for rid in locations if rid in known and rid in world.rooms], 'Make '+recipe.get('name','the required item')+' at the indicated workshop.')
        entries=sources.get(iid,[]) if isinstance(sources,dict) else []
        places=[entry['room'] for entry in entries if isinstance(entry,dict) and entry.get('room') in known and entry['room'] in world.rooms]
        label=next((entry.get('label') for entry in entries if isinstance(entry,dict) and entry.get('room') in places and entry.get('label')),None)
        return (places,label or 'Find '+world.items.get(iid,{}).get('name','the required supply')+' using the journal’s known sources.')
    for iid,n in q.get('required_items',{}).items():
        if carried[iid]<n:
            result=source(iid,n)
            if result and result[0]:return result
            # No guessed location: fall through to other disclosed objectives.
    for hint in q.get('navigation_hints',[]):
        if not isinstance(hint,dict):continue
        action=hint.get('action')
        kills=hint.get('kills',{})
        if action and count('actions',action)>=q.get('actions',{}).get(action,1):continue
        if kills and all(count('kills',i)>=n for i,n in kills.items()):continue
        if not action and not kills:continue
        camp=getattr(world,'living_state',{}).get('camps',{}).get(player.id,{})
        for iid,n in hint.get('materials',{}).items():
            if camp and hint.get('own_camp') and world.items.get(iid,{}).get('camp_tent'):continue
            if carried[iid]<n:
                result=source(iid,n)
                if result:return result
        rid=(camp.get('room') if hint.get('own_camp') and camp else player.location if hint.get('here') else hint.get('room'))
        if rid in known and rid in world.rooms:return ([rid],hint.get('label','Continue the current objective.'))
    return None


def validate(data):
    issues=[];rooms={r['id'] for r in data.get('room',[])};items={i['id'] for i in data.get('item',[])};recipes={r['id'] for r in data.get('recipe',[])}
    for q in data.get('quest',[]):
        prefix=q['id']+': next-stop '
        sources=q.get('navigation_supply_sources',{})
        if not isinstance(sources,dict):issues.append(prefix+'sources must be an object');continue
        for iid,entries in sources.items():
            if iid not in items or not isinstance(entries,list) or len(entries)>8:
                issues.append(prefix+'source must name an item and at most eight places');continue
            for entry in entries:
                if not isinstance(entry,dict) or entry.get('room') not in rooms or not isinstance(entry.get('label',''),str) or len(entry.get('label',''))>240:
                    issues.append(prefix+'source requires an existing room and a short label')
        stations=q.get('navigation_recipe_stations',{})
        if not isinstance(stations,dict):issues.append(prefix+'stations must be an object')
        else:
            for rid,places in stations.items():
                if rid not in recipes or not isinstance(places,list) or len(places)>8 or any(p not in rooms for p in places):issues.append(prefix+'station mapping must name a recipe and existing rooms')
        hints=q.get('navigation_hints',[])
        if not isinstance(hints,list) or len(hints)>32:issues.append(prefix+'hints must be a list of at most 32 entries');continue
        for hint in hints:
            if not isinstance(hint,dict):issues.append(prefix+'hint must be an object');continue
            if hint.get('room') not in rooms and hint.get('here') is not True:issues.append(prefix+'hint needs an existing room or here=true')
            if not isinstance(hint.get('label',''),str) or len(hint.get('label',''))>240:issues.append(prefix+'hint label must be short text')
            action=hint.get('action');kills=hint.get('kills',{})
            if not isinstance(kills,dict) or any(type(n) is not int or n<1 or q.get('kills',{}).get(i)!=n for i,n in kills.items()):issues.append(prefix+'kill hint must match its quest objectives')
            if action not in q.get('actions',{}) and not kills:issues.append(prefix+'hint must match a quest action or kills')
            materials=hint.get('materials',{})
            if not isinstance(materials,dict) or any(i not in items or type(n) is not int or not 1<=n<=100000 for i,n in materials.items()):issues.append(prefix+'materials must name existing items and positive bounded counts')
    return issues
