"""Shared location, diplomacy and finite-stock production rules."""
import hashlib,math
from collections import Counter
from engine import living

def enabled(w):return bool(w.metadata.get('society'))

def bounds(w,source,target):
    from engine import diplomacy
    return diplomacy.bounds(w.groups.get(source,{}),source,target)


def standing(w,p,target):
    low,high,base=bounds(w,p.group_id,target)
    return max(low,min(high,base+p.reputation.get(target,0)))

def award(w,p,target,amount):
    low,high,base=bounds(w,p.group_id,target)
    p.reputation[target]=max(low,min(high,base+p.reputation.get(target,0)+amount))-base

def friendliness(w,a,b):
    if a.group_id and a.group_id==b.group_id:return 100
    forward,reverse=standing(w,a,b.group_id),standing(w,b,a.group_id)
    # A player's earned reputation is a personal contribution recognised by
    # members of that faction, not a rewrite of its global diplomacy. Keep
    # both authored caps, initial relations and existing saved-award meaning.
    # Player-player consent and NPC-NPC relationships remain mutual as before.
    if bool(a.is_player) != bool(b.is_player):
        player,npc=(a,b) if a.is_player else (b,a)
        low,high,_=bounds(w,npc.group_id,player.group_id)
        personal=player.reputation.get(npc.group_id,0)
        reciprocal=max(low,min(high,standing(w,npc,player.group_id)+personal))
        return min(standing(w,player,npc.group_id),reciprocal)
    return min(forward,reverse)

def speech(text,score):
    if score>=50:return text
    # Stable per word, never exposes a hidden plaintext copy in the packet.
    fraction=max(0,score)/50
    return ' '.join(word if int(hashlib.sha256((str(i)+word).encode()).hexdigest()[:8],16)/0xffffffff<fraction else ''.join('?' if c.isalnum() else c for c in word) for i,word in enumerate(text.split()))

def economy(w):
    state=living.state(w)
    if 'economy' not in state:state['economy']={'shops':{},'minute':-1,'log':[]}
    return state['economy']

def shop(w,rid):
    data=economy(w);cfg=w.room_details.get(rid,{}).get('workshop')
    if not cfg:raise ValueError('Visit a workshop, factory or repair shop.')
    shops=data['shops']
    if rid not in shops:shops[rid]={'gold':cfg.get('capital',500),'stock':dict(cfg.get('initial_stock',{})),'last':-1,'workers':[]}
    return cfg,shops[rid]

def price(w,iid,buying=True,rid=None):
    value=max(1,int(w.items[iid].get('value',1)))
    from engine import needs_market
    if rid and needs_market.enabled(w):
        cfg,s=shop(w,rid);value=needs_market.quote(w,iid,s['stock'].get(iid,0),cfg.get('stock_limit',40),value,w.rooms[rid].group)
    return value if buying else max(1,value//2)

def produce(w):
    if not enabled(w):return
    now=living.state(w)['minute'];e=economy(w)
    if now==e['minute']:return
    e['minute']=now
    from engine import livelihoods
    # A production phase does not advance time or change opening rules/structure
    # damage. Keep this cache local so creator edits and later hazards are fresh.
    open_rooms={}
    def is_open(rid):
        if rid not in open_rooms:open_rooms[rid]=livelihoods.room_open(w,rid)
        return open_rooms[rid]
    for rid,rd in w.room_details.items():
        cfg=rd.get('workshop')
        if not cfg:continue
        cfg,s=shop(w,rid)
        from engine import livelihoods
        workers=[n for n in w.entities_in_room(rid) if not n.is_player and n.alive and livelihoods.definition(w,n).get('profession')=='producer' and livelihoods.on_shift(w,n) and is_open(rid)]
        s['workers']=[n.name for n in workers]
        if not workers or now-s['last']<cfg.get('interval',30):continue
        s['last']=now
        # Workers share local batches and cooldowns, including finite reserves.
        for resource_id in rd.get('resources',[]):
            res=getattr(w,'resources',{}).get(resource_id,{})
            from engine import hand_resources
            if hand_resources.configured(res):continue
            from engine import ecology,resource_nodes,geology_impacts
            if geology_impacts.resource_blocked(w,rid,resource_id):continue
            if not ecology.in_season(w,res,rid) or not ecology.available(w,rid,res):continue
            if resource_nodes.managed(res,w.items):
                eligible=[worker for worker in workers if worker.group_id==w.rooms[rid].group and (not res.get('tool') or res['tool'] in worker.inventory)]
                if 'reserve_batches' in res and resource_nodes.visual_config(res,w.items) is not None:
                    # Never spend a finite mixed batch unless every yield fits.
                    # Renewable resources retain their existing capped stock.
                    if any(type(s['stock'].get(iid,0)) is not int or not 0<=s['stock'].get(iid,0)<=200-count for iid,count in res['yields'].items()):continue
                if eligible and resource_nodes.harvest(w,rid,res,eligible[0]):
                    for iid,n in res.get('yields',{}).items():s['stock'][iid]=min(200,s['stock'].get(iid,0)+n)
                continue
            # Shared wildlife collection leaves a due batch available to others
            # while this workshop already holds one batch of each output.
            if res.get('shared_renewal') and all(s['stock'].get(i,0)>=n for i,n in res.get('yields',{}).items()):continue
            key=rid+':'+resource_id
            ledger=living.state(w).setdefault('shared_resource_times',{}) if res.get('shared_renewal') else e.setdefault('harvest_times',{})
            due=ledger.get(key,-100000)
            if now-due<res.get('renewal_minutes',60):continue
            ledger[key]=now
            for iid,n in res.get('yields',{}).items():s['stock'][iid]=min(200,s['stock'].get(iid,0)+n*(1 if res.get('shared_renewal') else len(workers)))
        for recipe_id in cfg.get('recipes',[]):
            rec=getattr(w,'recipes',{}).get(recipe_id,{})
            ingredients=rec.get('ingredients',{});outputs=rec.get('outputs',{})
            if not ingredients or not outputs:continue
            from engine import ecology
            if not ecology.available(w,rid,rec):continue
            # One bounded batch per staffed shift; inputs are actually consumed.
            if any(s['stock'].get(i,0)<n for i,n in ingredients.items()):continue
            if any(s['stock'].get(i,0)>=cfg.get('stock_limit',40) for i in outputs):continue
            for i,n in ingredients.items():s['stock'][i]-=n
            for i,n in outputs.items():s['stock'][i]=s['stock'].get(i,0)+n
            if s['gold']>0:
                s['gold']-=1;workers[0].gold+=1
                from engine import npc_life
                npc_life.earned(w,workers[0],1)
            wear(workers[0])
            for iid in workers[0].inventory:
                if durability(workers[0],iid)<75 and s['stock'].get('sx_repair_kit',0)>0 and workers[0].gold>=2:
                    workers[0].gold-=2;s['gold']+=2;s['stock']['sx_repair_kit']-=1;workers[0].progress.setdefault('durability',{})[iid]=100
            from engine import gazette
            products=', '.join(f"{n} × {w.items.get(i,{}).get('name',i)}" for i,n in outputs.items())
            from engine.npc_activity import note
            note(workers[0],'work','Finished '+products)
            if getattr(w,'living_state',{}).get('resident_watches'):
                from engine import resident_watch
                resident_watch.note(w,[workers[0].id],'Finished '+products+'.')
            gazette.record(w,rid,'Trade',workers[0].name+' completed '+products+'.',key=rid+':'+recipe_id+':'+workers[0].name)
            e['log']=(e['log']+[{'minute':now,'room':rid,'recipe':recipe_id,'worker':workers[0].name}])[-200:]
        # Regional logistics remains abstract (not road-routed); both endpoints must be open.
        # Buy required material from another workshop's surplus.
        for recid in cfg.get('recipes',[])+(['__repair__'] if cfg.get('repair') else []):
            rec={'ingredients':{'sx_repair_kit':1}} if recid=='__repair__' else getattr(w,'recipes',{}).get(recid,{})
            for iid,amount in rec.get('ingredients',{}).items():
                if s['stock'].get(iid,0)>=amount:continue
                for origin,other in list(e['shops'].items()):
                    if origin==rid or w.rooms[origin].group!=w.rooms[rid].group or other['stock'].get(iid,0)<amount*2:continue
                    if not is_open(origin):continue
                    cost=price(w,iid,False)*amount
                    if s['gold']>=cost:
                        other['stock'][iid]-=amount;s['stock'][iid]=s['stock'].get(iid,0)+amount
                        s['gold']-=cost;other['gold']+=cost;break

def durability(p,iid):return p.progress.setdefault('durability',{}).get(iid,100)

def wear(p):
    for iid in p.equipped.values():p.progress.setdefault('durability',{})[iid]=max(0,durability(p,iid)-1)

def locate(w,p,iid):
    places=[]
    if iid in p.inventory:places.append('Carried by '+p.name+' in '+w.rooms[p.location].name)
    if iid in w.rooms[p.location].items:places.append('On the ground in '+w.rooms[p.location].name)
    return '; '.join(places) or 'Designated origin: '+w.rooms.get(w.items.get(iid,{}).get('location'),w.rooms[p.location]).name

def command(ctx,args,name):
    w,p=ctx.world,ctx.player
    from engine import player_names
    if name=='standing':return '\n'.join(g['name']+': '+str(standing(w,p,gid))+'% (limits '+str(bounds(w,p.group_id,gid)[:2])+')' for gid,g in w.groups.items())
    if name=='place':
        iid,_,target=args.partition(' at ')
        if iid not in p.inventory:raise ValueError('Choose an item you carry.')
        if target!=p.location:raise ValueError('You may place carried objects only at your current location.')
        if iid in p.equipped.values():raise ValueError('Unequip it first.')
        p.inventory.remove(iid);w.rooms[target].items.append(iid)
        return 'Placed '+w.items[iid]['name']+' in '+w.rooms[target].name+'.'
    if name=='barter':
        from engine import barter
        give,sep,rest=args.partition(' for ');take,with_sep,target=rest.partition(' with ')
        if not sep or not with_sep:raise ValueError('Use barter <your item> for <their item> with <person>.')
        npc=player_names.nearby(w,p,target)
        barter.eligible(w,p,npc)
        return barter.swap(w,p,npc,player_names.item(w,give,p.inventory),player_names.item(w,take,npc.inventory))
    if name=='sell':
        from engine import needs_market
        if not needs_market.enabled(w):raise ValueError('Enable the needs economy to sell finished goods.')
        query,sep,target=args.partition(' to ');iid=player_names.item(w,query,p.inventory)
        if sep:
            from engine import barter
            npc=player_names.nearby(w,p,target)
            return barter.sale(w,p,npc,iid)
        if iid not in p.inventory:raise ValueError('Choose an item you carry by name.')
        if iid in p.equipped.values():raise ValueError('Unequip it first.')
        needs_market.ensure(w)
        choices=[m for m in w.entities_in_room(p.location) if not m.is_player and m.alive and friendliness(w,p,m)>=50 and any(s.get('item')==iid for s in w.npcs.get(m.source_def,{}).get('stock',[]))]
        if len(choices)!=1:raise ValueError('Find one nearby merchant who stocks this item; workshops buy their needed raw materials with supply.')
        from engine import livelihoods
        livelihoods.require_service(w,choices[0])
        from engine import trade_view
        return trade_view.shop_sale(w,p,choices[0],iid)
    if name=='workshop':
        cfg,s=shop(w,p.location)
        lines=[cfg.get('name','Workshop')+' | Location: '+w.rooms[p.location].name,'Workers: '+(', '.join(s['workers']) or 'Off shift'),'Treasury: '+str(s['gold'])+' gold','Stock:']
        lines.extend(f'{w.items[i]["name"]}: {n}; buy {price(w,i,rid=p.location)} / sell {price(w,i,False,rid=p.location)} gold' for i,n in s['stock'].items())
        needs={i for rid in cfg.get('recipes',[]) for i in getattr(w,'recipes',{}).get(rid,{}).get('ingredients',{})}
        try:
            from engine import knowledge
            knowledge.teach(w,p,{'items':list(s['stock'])+list(needs)})
        except ImportError:pass
        return '\n'.join(lines+['Buying materials: '+', '.join(w.items[i]['name'] for i in sorted(needs) if i in w.items),'Use order <item name> / supply <item name> / repair <item name>.'])
    if name in ('order','supply','repair','mend'):
        candidates=p.inventory
        if name=='order':
            _,available_stock=shop(w,p.location);candidates=available_stock['stock']
        iid=player_names.item(w,args,candidates)
        if name=='mend':
            if 'sx_repair_kit' not in p.inventory:raise ValueError('You need a crafted repair kit.')
            if iid not in p.inventory:raise ValueError('You do not carry that item.')
            if w.items[iid].get('type') not in ('weapon','armor'):raise ValueError('Only equipment can be repaired.')
            p.inventory.remove('sx_repair_kit');p.progress.setdefault('durability',{})[iid]=100
            return 'Repaired using one repair kit.'
        cfg,s=shop(w,p.location)
        from engine import livelihoods
        if not livelihoods.room_open(w,p.location):raise ValueError('This workplace is closed. Check its opening hours.')
        if name=='repair':
            if not cfg.get('repair'):raise ValueError('This workshop does not offer repairs.')
            if iid not in p.inventory:raise ValueError('Bring the equipment with you.')
            if w.items[iid].get('type') not in ('weapon','armor'):raise ValueError('Only equipment can be repaired.')
            if durability(p,iid)==100:return 'No repair is needed.'
            cost=max(1,math.ceil(price(w,iid)*(100-durability(p,iid))/200))
            if s['stock'].get('sx_repair_kit',0)<1:raise ValueError('The repair shop needs a repair kit. Supply materials or return after production.')
            if p.gold<cost:raise ValueError('Repair costs '+str(cost)+' gold.')
            s['stock']['sx_repair_kit']-=1;p.gold-=cost;s['gold']+=cost;p.progress.setdefault('durability',{})[iid]=100
            return 'Repaired for '+str(cost)+' gold.'
        if name=='order':
            if s['stock'].get(iid,0)<1:raise ValueError('Out of stock; production needs workers and materials.')
            cost=price(w,iid,rid=p.location)
            if p.gold<cost:raise ValueError('Not enough gold.')
            p.gold-=cost;s['gold']+=cost;s['stock'][iid]-=1;p.inventory.append(iid)
            return 'Purchased '+w.items[iid]['name']+'.'
        needs={i for rid in cfg.get('recipes',[]) for i in getattr(w,'recipes',{}).get(rid,{}).get('ingredients',{})}
        if iid not in needs:raise ValueError('This workplace does not need that material.')
        if iid not in p.inventory:raise ValueError('You do not carry that material.')
        if iid in p.equipped.values():raise ValueError('Unequip it first.')
        cost=price(w,iid,False,rid=p.location)
        if s['gold']<cost:raise ValueError('The workshop cannot afford this material yet.')
        p.inventory.remove(iid);s['stock'][iid]=s['stock'].get(iid,0)+1;p.gold+=cost;s['gold']-=cost
        return 'Sold material for '+str(cost)+' gold.'
    if name=='provenance':
        iid=player_names.item(w,args,player_names.known_items(w,p));obj=w.items[iid]
        try:
            from engine import knowledge
            known_recipes=knowledge.ids(w,p,'recipes');known_rooms=knowledge.ids(w,p,'rooms')
        except ImportError:known_recipes=set();known_rooms=set(p.explored_rooms)|{p.location}
        rec=[r for r in getattr(w,'recipes',{}).values() if r['id'] in known_recipes and obj['id'] in r.get('outputs',{})]
        origin=obj.get('location');place=w.rooms[origin].name if origin in known_rooms and origin in w.rooms else 'Origin not yet learned'
        return obj['name']+'\nOrigin: '+place+'\n'+obj.get('description','')+'\nKnown creation: '+('; '.join(r['name']+': '+', '.join(str(n)+' '+w.items.get(i,{}).get('name','Unknown ingredient') for i,n in r['ingredients'].items()) for r in rec) or 'No recipe learned yet.')
    raise ValueError('Unknown society command.')

COMMANDS={'barter':'Trade a wanted item with a nearby NPC','sell':'Sell one carried item back to a merchant who stocks it','standing':'View faction percentages','place':'Place a carried item at your location','workshop':'View workplace stock, demand and workers','order':'Buy from a workplace','supply':'Sell needed materials to a workplace','repair':'Pay a repair workshop','mend':'Use a crafted repair kit','provenance':'Inspect an item and how it is made'}

def register(reg):
    from engine.commands import Command
    from engine import household_provisions
    reg.register(Command("provisions", "Read a city co-operative's daily food account", "provisions [city]",
                         household_provisions.report, available=lambda ctx: bool(household_provisions.config(ctx.world)),
                         example="provisions Dawnwatch"))
    for name,desc in COMMANDS.items():
        reg.register(Command(name,desc,name+' <item name>',lambda ctx,args,n=name:command(ctx,args,n),available=lambda ctx:enabled(ctx.world),example=name))

def validate(data,meta):
    issues=[];rooms={r['id'] for r in data['room']};groups={g['id'] for g in data['group']};items={i['id'] for i in data['item']};recipes={r['id'] for r in data.get('recipe',[])}
    if type(meta.get('max_players')) is not int or not 1<=meta['max_players']<=128:issues.append('max_players must be 1–128')
    for kind,rows in data.items():
        for row in rows:
            if row.get('location') not in rooms:issues.append(kind+' '+row['id']+': choose a designated location')
    for group in data['group']:
        for target,rule in group.get('diplomacy',{}).items():
            if target not in groups:issues.append('Unknown diplomacy target '+target)
            try:
                if not 0<=rule['minimum']<=rule['base']<=rule['maximum']<=100:issues.append(group['id']+': diplomacy requires 0 <= minimum <= base <= maximum <= 100')
            except (KeyError,TypeError):issues.append(group['id']+': incomplete diplomacy rule')
    for r in data['room']:
        cfg=r.get('workshop')
        if not cfg:continue
        if any(i not in items or type(n) is not int or n<0 for i,n in cfg.get('initial_stock',{}).items()):issues.append(r['id']+': invalid initial workshop stock')
        if any(i not in recipes for i in cfg.get('recipes',[])):issues.append(r['id']+': unknown production recipe')
        if cfg.get('capital',0)<0 or cfg.get('interval',1)<1:issues.append(r['id']+': capital/interval invalid')
    for rule in data.get('interaction',[]):
        if rule.get('tool') and rule['tool'] not in items:issues.append(rule['id']+': unknown interaction tool')
        if rule.get('interaction_effect') not in ('damage','repair','heal','create'):issues.append(rule['id']+': invalid interaction effect')
        for field in ('components','outputs'):
            if any(i not in items or type(n) is not int or n<1 for i,n in rule.get(field,{}).items()):issues.append(rule['id']+': invalid '+field)
    obtainable={i for r in data.get('resource',[]) for i in r.get('yields',{})}|{i for e in data.get('encounter',[]) for i in e.get('harvest',{})}
    obtainable.update(r['search_reward'] for r in data['room'] if r.get('search_reward') in items)
    obtainable.update(i for row in data['room'] for i in row.get('items',[]) if i in items)
    obtainable.update(s.get('item') for n in data['npc'] for s in n.get('stock',[]) if s.get('qty',1)>0)
    obtainable.update(i for n in data.get('npc',[]) for i in n.get('drops',[]))
    from engine import loot_tables
    obtainable.update(i for n in data.get('npc',[]) for i in loot_tables.possible_items(n))
    for _ in range(len(items)):
        old=len(obtainable)
        for rec in data.get('recipe',[]):
            if rec.get('ingredients') and set(rec['ingredients'])<=obtainable:obtainable.update(rec.get('outputs',{}))
        if len(obtainable)==old:break
    for iid in sorted(items-obtainable):issues.append(iid+': no complete raw-material creation chain')
    from engine import relationships
    from engine import mortality, ecology, climate
    from engine import social,companions,names
    from engine import needs_market
    from engine import settlements
    return issues + settlements.validate(data) + needs_market.validate(data) + names.validate(data) + social.validate(data) + companions.validate(data) + relationships.validate(data) + mortality.validate(data,meta) + ecology.validate(data) + climate.validate(data,meta)

_previous_validate=validate
def validate(data,meta):
    from engine import livelihoods
    from engine import household_provisions
    issues = _previous_validate(data,meta) + livelihoods.validate(data)
    if 'household_provisions' in meta:
        rooms = {room['id'] for room in data.get('room', [])}
        items = {item['id'] for item in data.get('item', [])}
        recipes = {recipe['id']: recipe for recipe in data.get('recipe', [])}
        issues.extend(household_provisions.validate(meta['household_provisions'], rooms, items, recipes))
    return issues
