"""Bounded feeding and habitat recovery; no sentient or owned hunting targets."""
from collections import defaultdict
from engine import living,relationships,ecology,society

def species(w,e):
    if e.is_player:return {}
    p=relationships.profile(w,e)
    if p['sentient'] or p['undead']:return {}
    return getattr(w,'species',{}).get(p['species'],{})

def can_eat(w,e,iid):
    s=species(w,e);item=w.items.get(iid,{})
    return iid in s.get('diet',[]) and item.get('food_origin') in ({'plant'} if s.get('consumption')=='herbivore' else {'animal'} if s.get('consumption')=='carnivore' else {'plant','animal'})

def recovery_allowed(w,room,spawner,index):
    cfg=spawner.get('recovery',{})
    if not cfg.get('enabled'):return True
    # Habitat-specific minimum counts include offspring, but not owned companions.
    sid=w.npcs.get(spawner.get('npc'),{}).get('social_profile',{}).get('species')
    count=sum(e.alive and not e.is_player and not e.progress.get('companion_owner') and e.source_def==spawner.get('npc') for e in w.entities_in_room(room.id))
    return count<cfg.get('minimum',1)

def advance(w, *, stepped_entities=()):
    from engine import animal_life
    animal_life.advance(w,stepped_entities=stepped_entities)
    if not w.metadata.get('wildlife_ecology'):return
    now=living.state(w)['minute'];stats=living.state(w).setdefault('wildlife',{'last':-100000,'forage':{},'meals':0,'hunts':0})
    if now-stats['last']<30:return
    stats['last']=now
    animals={e.id:species(w,e) for e in w.entities.values() if e.alive and not e.is_player and not e.progress.get('zoo_exhibit') and not animal_life.config(w,e)}
    for e in list(w.entities.values()):
        s=animals.get(e.id,{})
        if not s or not e.alive or s.get('consumption') not in ('herbivore','omnivore','carnivore'):continue
        feeding=e.progress.setdefault('feeding',{'last_meal':now-60})
        if now-feeding['last_meal']<s.get('feeding_interval',180):continue
        from engine import npc_attention
        if npc_attention.paused(w,e):continue
        def ate():feeding['last_meal']=now;stats['meals']+=1;e.activity='feeding'
        # Carried food, then finite supplies at managed holdings, then ground food.
        sources=[e.inventory]
        from engine import geology_impacts
        shop=None if geology_impacts.room_unusable(w,e.location) else society.economy(w)['shops'].get(e.location)
        for inv in sources:
            meal=next((i for i in inv if can_eat(w,e,i)),None)
            if meal:inv.remove(meal);ate();break
        else:
            meal=next((i for i,n in (shop or {}).get('stock',{}).items() if n>0 and can_eat(w,e,i)),None)
            if meal:shop['stock'][meal]-=1;ate();continue
            meal=next((i for i in w.rooms[e.location].items if can_eat(w,e,i)),None)
            if meal:w.rooms[e.location].items.remove(meal);ate();continue
            # Owned animals and managed enclosures never autonomously hunt livestock.
            if e.progress.get('companion_owner') or 'husbandry' in living.details(w,e.location).get('facilities',[]):continue
            if s['consumption'] in ('herbivore','omnivore'):
                for rid in living.details(w,e.location).get('resources',[]):
                    r=getattr(w,'resources',{}).get(rid,{})
                    food=next((i for i in r.get('yields',{}) if can_eat(w,e,i)),None)
                    key=e.location+':'+rid
                    if food and not geology_impacts.resource_blocked(w,e.location,rid) and not geology_impacts.room_unusable(w,e.location) and ecology.in_season(w,r,e.location) and now-stats['forage'].get(key,-100000)>=r.get('renewal_minutes',60):
                        stats['forage'][key]=now;ate();break
                else:food=None
                if food:continue
            if s['consumption'] in ('carnivore','omnivore') and not living.details(w,e.location).get('truce'):
                prey=next((v for v in w.entities_in_room(e.location) if v.alive and v.id!=e.id and not v.is_player and not v.progress.get('companion_owner') and animals.get(v.id,{}).get('id') in s.get('prey_species',[])),None)
                if prey:
                    from engine import combat
                    prey_species=animals[prey.id]
                    text=combat.strike(w,e,prey,counter=True)
                    w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(e.location,text)])[-500:]
                    if not prey.alive:
                        if not prey.progress.get('wildlife_drops_released'):
                            prey.progress['wildlife_drops_released']=True
                            if not prey.progress.get('combat_drops_distributed'):
                                w.rooms[e.location].items.extend(i for i in w.npcs.get(prey.source_def,{}).get('drops',[]) if i in w.items)
                        # Consume one actual edible drop, leaving other remains for scavengers.
                        source=e.inventory
                        meal=next((i for i in source if can_eat(w,e,i)),None)
                        if not meal:
                            source=w.rooms[e.location].items
                            meal=next((i for i in source if can_eat(w,e,i)),None)
                        if meal:source.remove(meal);ate();stats['hunts']+=1
                    continue
            # Look only one exit away for authored forage or prey: bounded local search.
            if s.get('forage_roaming',True):
                from engine import frontiers
                for di,dest in w.rooms[e.location].exits.items():
                    if dest not in w.rooms or frontiers.blocked(w,e.location,di,e):continue
                    rd=living.details(w,dest)
                    if 'husbandry' in rd.get('facilities',[]) or rd.get('truce'):continue
                    prey_here=any(v.alive and not v.is_player and not v.progress.get('companion_owner') and animals.get(v.id,{}).get('id') in s.get('prey_species',[]) for v in w.entities_in_room(dest))
                    plants_here=s['consumption']!='carnivore' and any(any(can_eat(w,e,i) for i in getattr(w,'resources',{}).get(r,{}).get('yields',{})) for r in rd.get('resources',[]) if not geology_impacts.resource_blocked(w,dest,r) and not geology_impacts.room_unusable(w,dest))
                    if prey_here or plants_here:w.move_entity(e.id,dest);e.activity='foraging';break

def validate(data):
    out=[];ids={s['id'] for s in data.get('species',[])};items={i['id'] for i in data.get('item',[])}
    origins={i['id']:i.get('food_origin') for i in data.get('item',[])}
    for s in data.get('species',[]):
        if 'consumption' not in s:continue
        if s['consumption'] not in ('producer','herbivore','omnivore','carnivore'):out.append(s['id']+': invalid consumption type')
        if any(i not in items for i in s.get('diet',[])):out.append(s['id']+': unknown diet item')
        if any(i not in ids for i in s.get('prey_species',[])):out.append(s['id']+': unknown prey species')
        if type(s.get('feeding_interval',180)) is not int or s.get('feeding_interval',180)<30:out.append(s['id']+': feeding interval must be at least 30 minutes')
        if s['consumption']=='herbivore' and any(origins.get(i)=='animal' for i in s.get('diet',[])):out.append(s['id']+': herbivore diet includes animal food')
        if s['consumption']=='carnivore' and any(origins.get(i)=='plant' for i in s.get('diet',[])):out.append(s['id']+': carnivore diet includes plant food')
        if s['consumption'] in ('producer','herbivore') and s.get('prey_species'):out.append(s['id']+': plant eaters cannot have animal prey')
    for r in data.get('room',[]):
        for sp in r.get('spawners',[]):
            c=sp.get('recovery',{})
            if c.get('enabled') and (type(c.get('minimum')) is not int or not 1<=c['minimum']<=sp.get('count',1)):out.append(r['id']+': invalid recovery minimum')
    from engine import animal_life
    return out+animal_life.validate(data)
