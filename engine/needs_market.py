"""Creator-editable needs priorities and conservation-based regional trade."""
import math
from collections import Counter
from copy import deepcopy
from engine import living,relationships,society
KEYS=('hunger','thirst','rest','safety','belonging','esteem','fulfillment')
PROFILE={'enabled':True,'threshold':35,'urgent':75,'rates':dict(hunger=45,thirst=60,rest=40,safety=12,belonging=20,esteem=10,fulfillment=8)}

def enabled(w):return bool(w.metadata.get('needs_economy'))
def applies(w,e):return enabled(w) and not e.is_player and e.alive and relationships.sentient(w,e) and w.npcs.get(e.source_def,{}).get('needs_profile',{}).get('enabled',True)
def cfg(w,e):return {**PROFILE,'rates':dict(PROFILE['rates']),**w.npcs.get(e.source_def,{}).get('needs_profile',{})}
def state(e):return e.progress.setdefault('needs',{k:20.0 for k in KEYS})
def effects(w,iid):return w.items.get(iid,{}).get('need_effects',{})
def priority(w,e):
    n=state(e);threshold=cfg(w,e)['threshold']
    physical=max(KEYS[:3],key=lambda k:n[k])
    return physical if n[physical]>=threshold else next((k for k in KEYS[3:] if n[k]>=threshold),max(KEYS,key=lambda k:n[k]))
def relieve(e,key,amount):state(e)[key]=max(0,state(e)[key]-amount)
def _active_needs(w,e):
    n=state(e);threshold=cfg(w,e)['threshold'];key=priority(w,e)
    keys=KEYS[:3] if key in KEYS[:3] else (key,)
    return tuple(k for k in keys if n[k]>=threshold)

def _wanted_for_keys(w,keys):
    if not keys:return []
    return [iid for iid,item in w.items.items()
            if (eff:=item.get('need_effects')) and any(eff.get(k,0)>0 for k in keys)]

def wanted_items(w,e):
    """Evaluate the NPC once, then inspect item effects without repeated profiles."""
    if not applies(w,e):return []
    return _wanted_for_keys(w,_active_needs(w,e))

def market_demand(w):
    """Count identical need sets once, preserving one demand unit per NPC/item.

    Request-local memoization has at most eleven nonempty need combinations.
    It cannot survive Creator edits, item deletion or a reload.
    """
    groups={}
    for e in w.entities.values():
        if applies(w,e):
            counts=groups.setdefault(str(e.group_id),Counter())
            counts[_active_needs(w,e)]+=1
    wanted={}
    demand={}
    for group,counts in groups.items():
        demand[group]={}
        for keys,count in counts.items():
            if keys not in wanted:wanted[keys]=_wanted_for_keys(w,keys)
            for iid in wanted[keys]:demand[group][iid]=demand[group].get(iid,0)+count
    return demand

def wants(w,e,iid):
    if not applies(w,e):return False
    key=priority(w,e);n=state(e);threshold=cfg(w,e)['threshold']
    keys=KEYS[:3] if key in KEYS[:3] else (key,)
    return any(n[k]>=threshold and effects(w,iid).get(k,0)>0 for k in keys)

def use(w,e,iid):
    if not wants(w,e,iid) or iid not in e.inventory:return False
    for k,v in effects(w,iid).items():relieve(e,k,v)
    if w.items[iid].get('need_consumable',False):
        e.inventory.remove(iid)
        if effects(w,iid).get('safety'):
            from engine import geology_impacts
            before=e.hp
            e.hp=min(e.max_hp,e.hp+max(w.items[iid].get('heal',0),effects(w,iid)['safety']))
            geology_impacts.retire_wounds(w,e,e.hp-before)
    return True

def describe(w,e):
    if not applies(w,e):return ''
    key=priority(w,e);useful=[w.items[i]['name'] for i in wanted_items(w,e)]
    return 'Current need: '+key+' ('+str(round(state(e)[key]))+'/100). Useful items: '+(', '.join(useful[:8]) or 'none needed now')+'.'

def target(w,definition,iid,demographics=None):
    configured=definition.get('market',{}).get('target_stock',{}).get(iid)
    if configured is not None:return max(1,int(configured))
    cache=getattr(w,'_need_targets',None)
    if cache is None:w._need_targets={};cache=w._need_targets
    cache_key=(definition.get('id',id(definition)),iid)
    if cache_key in cache:return cache[cache_key]
    group=definition.get('group')
    if demographics is None:
        population=sum(1 for n in w.npcs.values() if n.get('group')==group and n.get('social_profile',{}).get('sentient'))
        sellers=sum(any((s.get('item') if isinstance(s,dict) else s)==iid for s in n.get('stock',[])) for n in w.npcs.values() if n.get('group')==group)
    else:
        # A transfer pass supplies a lazy census. Explicit targets and existing
        # cached targets return above without evaluating it.
        populations,vendors=demographics() if callable(demographics) else demographics
        population=populations[group];sellers=vendors[group,iid]
    relief=max(effects(w,iid).values(),default=0)
    demand=population*(30/max(1,relief) if relief else .08)
    result=max(2,min(40,math.ceil(demand/max(1,sellers)*definition.get('market',{}).get('reserve_days',2))))
    cache[cache_key]=result
    return result

def _demographics(w):
    """One read-only definition census; callers own its short-lived scope."""
    populations=Counter();vendors=Counter()
    for definition in w.npcs.values():
        group=definition.get('group')
        if definition.get('social_profile',{}).get('sentient'):populations[group]+=1
        for iid in {(entry.get('item') if isinstance(entry,dict) else entry) for entry in definition.get('stock',[])}:vendors[group,iid]+=1
    return populations,vendors

def ensure(w):
    if not enabled(w) or getattr(w,'_finite_ready',False):return
    w._finite_ready=True
    econ=society.economy(w);seen=econ.setdefault('finite_merchants',[])
    # One census for initial finite-stock setup, rather than one per item
    # per merchant. This index exists only for this synchronous setup call.
    demographics=_demographics(w)
    for ident,d in w.npcs.items():
        if not d.get('stock'):continue
        stock=w.shop_state.setdefault(ident,{})
        for entry in d['stock']:
            iid=entry['item']
            if iid not in w.items:continue
            initial=int(entry.get('qty',0))
            if ident not in seen and (iid not in stock or initial<=0 or (entry.get('legacy_unlimited') and stock.get(iid)==0)):
                stock[iid]=target(w,d,iid,demographics) if initial<=0 else initial
            stock[iid]=max(0,int(stock.get(iid,0)))
        if ident not in seen:seen.append(ident)

def quote(w,iid,stock,target_stock,base=None,group=None):
    base=max(1,int(base if base is not None else w.items[iid].get('value',1)))
    if not enabled(w):return base
    demand=society.economy(w).get('demand',{}).get(str(group),{}).get(iid,0)
    ratio=target_stock/(max(0,stock)+target_stock)
    factor=min(3,max(.5,.65+.9*ratio+.45*min(2,demand/max(1,target_stock))))
    return max(1,math.ceil(base*factor))

def merchant_price(w,ident,iid,base):
    d=w.npcs[ident]
    return quote(w,iid,w.shop_state[ident].get(iid,0),target(w,d,iid),base,d.get('group'))

def advance(w,minutes):
    if not enabled(w):return
    ensure(w)
    for e in list(w.entities.values()):
        if not applies(w,e):continue
        if not e.progress.get('needs_budget_assigned'):
            e.gold+=w.npcs.get(e.source_def,{}).get('needs_starting_gold',0);e.progress['needs_budget_assigned']=True
        n=state(e);c=cfg(w,e)
        for k in KEYS:n[k]=min(100,n[k]+c['rates'].get(k,0)*minutes/1500)
        if e.hp<e.max_hp:n['safety']=max(n['safety'],100*(1-e.hp/e.max_hp))
        activity=(getattr(e,'activity','') or '').lower()
        if 'sleep' in activity or 'rest' in activity:relieve(e,'rest',minutes*.8)
        if any(x in activity for x in ('work','craft','teach','production')):relieve(e,'esteem',minutes*.25)
        if any(x in activity for x in ('study','learn','school','train')):relieve(e,'fulfillment',minutes*.3)
        if living.details(w,e.location).get('truce'):relieve(e,'safety',minutes*.3)
        from engine import geology_impacts
        if not geology_impacts.room_unusable(w,e.location) and 'recreation' in living.details(w,e.location).get('facilities',[]):
            relieve(e,'rest',minutes*.2);relieve(e,'belonging',minutes*.3)
        for iid in list(dict.fromkeys(e.inventory)):
            if use(w,e,iid):break
    now=living.state(w)['minute'];econ=society.economy(w)
    if now-econ.get('market_minute',-10000)<30:return
    econ['market_minute']=now
    econ['demand']=market_demand(w)
    # Abstract regional transfers are not road-routed; both endpoints must be open.
    # Merchants buy finite goods already produced in their own region.
    paid=set()
    from engine import livelihoods
    demographics=None
    sources_by_group={}
    openness={}
    # This synchronous phase changes only needs-independent stock, money and
    # logs. Keep ordered source rows and live stock dictionaries, but share its
    # unchanged definition census and room-opening answers until it returns.
    def census():
        nonlocal demographics
        if demographics is None:demographics=_demographics(w)
        return demographics
    def room_open(rid):
        if rid not in openness:openness[rid]=livelihoods.room_open(w,rid)
        return openness[rid]
    def sources(group):
        if group not in sources_by_group:
            sources_by_group[group]=[(rid,row) for rid,row in econ['shops'].items()
                                     if rid in w.rooms and w.rooms[rid].group==group]
        return sources_by_group[group]
    for m in w.entities.values():
        if not m.alive or m.is_player or not w.npcs.get(m.source_def,{}).get('stock') or m.source_def in paid:continue
        if not room_open(m.location):continue
        paid.add(m.source_def);d=w.npcs[m.source_def];stock=w.shop_state[m.source_def]
        for entry in d['stock']:
            iid=entry['item']
            if iid not in w.items:continue
            needed=max(0,target(w,d,iid,census)-stock.get(iid,0))
            for rid,other in sources(m.group_id):
                if not needed:break
                if not room_open(rid):continue
                available=other['stock'].get(iid,0)
                cost=max(1,merchant_price(w,m.source_def,iid,entry.get('price',w.items[iid].get('value',1)))//2)
                qty=min(needed,available,max(0,m.gold)//cost)
                if qty:
                    other['stock'][iid]-=qty;stock[iid]=stock.get(iid,0)+qty;m.gold-=qty*cost;other['gold']+=qty*cost;needed-=qty
                    econ['log']=(econ['log']+[{'minute':now,'merchant':m.id,'item':iid,'quantity':qty,'source':rid}])[-200:]

def act(w,e,minutes):
    if not applies(w,e):return False
    key=priority(w,e);n=state(e)
    if n[key]<cfg(w,e)['threshold']:return False
    if key=='rest' and n[key]>=cfg(w,e)['urgent']:
        e.activity='resting';relieve(e,'rest',minutes*.8);return True
    threshold=cfg(w,e)['threshold']
    keys=KEYS[:3] if key in KEYS[:3] else (key,)
    active=tuple(k for k in keys if n[k]>=threshold)
    # Only stocked goods can be purchased. Inspect each distinct offer at most
    # once in this action; thousands of unstocked wardrobe designs cost nothing.
    wanted={}
    def useful(iid):
        if iid not in wanted:
            eff=effects(w,iid)
            wanted[iid]=any(eff.get(k,0)>0 for k in active)
        return wanted[iid]
    candidates=[]
    for m in w.entities.values():
        if m.is_player or not m.alive or m.group_id!=e.group_id:continue
        d=w.npcs.get(m.source_def,{})
        if not d.get('stock'):continue
        from engine import livelihoods
        if not livelihoods.service_open(w,m):continue
        for entry in d.get('stock',[]):
            iid=entry['item']
            if w.shop_state.get(m.source_def,{}).get(iid,0)<1 or not useful(iid):continue
            cost=merchant_price(w,m.source_def,iid,entry.get('price',1))
            if e.gold>=cost:candidates.append((m,cost,iid))
    candidates.sort(key=lambda x:effects(w,x[2]).get(key,0),reverse=True)
    for m,cost,iid in candidates:
        if m.location!=e.location:continue
        from engine import npc_attention
        npc_attention.begin(w,e,m)
        e.gold-=cost;m.gold+=cost;w.shop_state[m.source_def][iid]-=1;e.inventory.append(iid);use(w,e,iid)
        society.economy(w)['npc_purchases']=society.economy(w).get('npc_purchases',0)+1
        e.activity='buying '+w.items[iid]['name'];return True
    # Raw essentials (especially well water) can be bought directly at production sites.
    workshops=[]
    for rid,stock in society.economy(w)['shops'].items():
        from engine import livelihoods
        if rid not in w.rooms or w.rooms[rid].group!=e.group_id or not livelihoods.room_open(w,rid):continue
        for iid,quantity in stock['stock'].items():
            if quantity<1 or not useful(iid):continue
            cost=society.price(w,iid,rid=rid)
            if e.gold<cost:continue
            if rid==e.location:
                e.gold-=cost;stock['gold']+=cost;stock['stock'][iid]-=1;e.inventory.append(iid);use(w,e,iid)
                society.economy(w)['npc_purchases']=society.economy(w).get('npc_purchases',0)+1
                e.activity='buying '+w.items[iid]['name'];return True
            workshops.append(rid)
    if n[key]>=cfg(w,e)['urgent'] and not candidates and workshops:
        step=living.next_step(w,e.location,workshops[0],e)
        if step:w.move_entity(e.id,step);e.activity='seeking '+key;return True
    if n[key]>=cfg(w,e)['urgent'] and candidates:
        step=living.next_step(w,e.location,candidates[0][0].location,e)
        if step:w.move_entity(e.id,step);e.activity='seeking '+key;return True
    return False

def validate(data):
    issues=[]
    for item in data.get('item',[]):
        eff=item.get('need_effects',{})
        if not isinstance(eff,dict) or any(k not in KEYS or type(v) not in (int,float) or not 0<=v<=100 for k,v in eff.items()):issues.append(item['id']+': invalid need effects')
        if not isinstance(item.get('need_consumable',False),bool):issues.append(item['id']+': need_consumable must be boolean')
    for n in data.get('npc',[]):
        market=n.get('market',{})
        if not isinstance(market,dict):issues.append(n['id']+': invalid market');market={}
        targets=market.get('target_stock',{})
        if not isinstance(targets,dict) or any(i not in {x['id'] for x in data.get('item',[])} or type(v) is not int or v<1 or v>10000 for i,v in targets.items()):issues.append(n['id']+': invalid target stock')
        days=market.get('reserve_days',2)
        if type(days) not in (int,float) or not 0<days<=30:issues.append(n['id']+': reserve days must be 0–30')
        if type(n.get('needs_starting_gold',0)) is not int or not 0<=n.get('needs_starting_gold',0)<=100000:issues.append(n['id']+': invalid needs starting gold')
        c=n.get('needs_profile',{})
        if not isinstance(c,dict):issues.append(n['id']+': invalid needs profile');continue
        for k in ('threshold','urgent'):
            if type(c.get(k,PROFILE[k])) not in (int,float) or not 1<=c.get(k,PROFILE[k])<=100:issues.append(n['id']+': invalid need '+k)
        rates=c.get('rates',PROFILE['rates'])
        if not isinstance(rates,dict) or any(k not in KEYS or type(v) not in (int,float) or not 0<=v<=100 for k,v in rates.items()):issues.append(n['id']+': invalid need rates')
    return issues
