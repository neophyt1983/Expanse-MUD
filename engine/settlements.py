"""Persistent property registry, finite civic construction and port logistics."""
from collections import Counter
from engine import living,society,relationships,geology_impacts
DAY=1500
KINDS=('house','rental','business','farm','ranch','recreation','hunting','reserve')

def enabled(w):return bool(w.metadata.get('settlements'))
def state(w):
    state=living.state(w)
    if 'settlements' not in state:state['settlements']=dict(parcels={},units={},treasuries={},credits={},last=-DAY,ships={},cargo=[],log=[])
    return state['settlements']
def init(w):
    s=state(w)
    if getattr(w,'_settlements_ready',False):return s
    for gid,g in w.groups.items():
        if g.get('development'):s['treasuries'].setdefault(gid,g['development'].get('capital',5000))
    for rid,rd in list(getattr(w,'room_details',{}).items()):
        c=rd.get('property_plot',{})
        if c.get('enabled') and rid not in s['parcels']:
            s['parcels'][rid]={'kind':c.get('kind','reserve'),'changed':living.state(w)['minute']}
            for index in range(c.get('initial_units',0)):new_unit(w,rid,index)
        if rd.get('port',{}).get('enabled'):s['ships'].setdefault(rid,rd['port'].get('initial_ships',1))
    for rid in s['parcels']:apply_land(w,rid)
    from engine import property_interiors
    property_interiors.ensure(w)
    w._settlements_ready=True
    return s

def apply_land(w,rid,previous_kind=None):
    from copy import deepcopy
    rd=living.details(w,rid);kind=state(w)['parcels'][rid]['kind'];plan=rd.get('land_uses',{}).get(kind,{})
    for field in ('resources','facilities','workshop','spawners'):
        if field in plan:rd[field]=deepcopy(plan[field])
    if 'spawners' in plan:
        w.rooms[rid].spawners=deepcopy(plan['spawners'])
        w.index_spawners(w.rooms[rid])
    rd['active_land_use']=kind
    w.rooms[rid].description=rd.get('description','')+' Current land use: '+kind+'.'
    if previous_kind is not None and previous_kind!='farm' and kind=='farm':
        from engine import resource_nodes
        resource_nodes.plant_conversion(w,rid)
    # A changed parcel must not remain a cached NPC harvesting destination.
    if previous_kind is not None:w.__dict__.pop('_livelihood_locations',None)


def new_unit(w,rid,index=None):
    s=state(w);c=living.details(w,rid)['property_plot'];kind=s['parcels'][rid]['kind']
    index=index if index is not None else 1+max([u['index'] for u in s['units'].values() if u['room']==rid],default=-1)
    uid=rid+':'+str(index+1)
    s['units'][uid]=dict(id=uid,index=index,room=rid,group=w.rooms[rid].group,kind=kind,owner='',tenant='',rent=c.get('rent',3),listed=True,due=0,arrears=0,storage=[],price=c.get('price',80))
    if getattr(w,'_settlements_ready',False):
        from engine import property_interiors
        property_interiors.ensure(w,[s['units'][uid]])
    return s['units'][uid]

def notify(w,p,text):
    p.progress['property_notices']=(p.progress.get('property_notices',[])+[text])[-10:]
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[p.id],text)
def credit(w,owner,gid,amount):
    s=state(w)
    if not owner:s['treasuries'][gid]=s['treasuries'].get(gid,0)+amount
    elif owner in w.entities:w.entities[owner].gold+=amount
    else:s['credits'][owner]=s['credits'].get(owner,0)+amount

def claim(w,p):
    amount=state(w)['credits'].pop(p.id,0)
    if amount:p.gold+=amount;notify(w,p,'Collected '+str(amount)+' gold in property income.')

def permitted(w,p,u):
    if not p.alive:raise ValueError('You must be alive to manage property.')
    if society.standing(w,p,u['group'])<50:raise ValueError('This region does not permit your faction to acquire property.')
    from engine import property_interiors
    if p.location!=u['room'] and not property_interiors.is_interior(w,u,p.location):raise ValueError('Visit the property before completing this transaction.')

def set_home(w,p,u):
    if u['kind'] not in ('house','rental'):raise ValueError('Choose a residential property.')
    if p.id != (u['tenant'] or u['owner']):raise ValueError('You do not control this home while another tenant occupies it.')
    from engine import property_interiors
    property_interiors.ensure(w,[u])
    p.progress['home_room']=property_interiors.room_id(u['id']) if property_interiors.room_id(u['id']) in getattr(w,'_property_generated_rooms',set()) else u['room']
    p.progress['home_property']=u['id']

def clear_home(w,ident,u):
    p=w.entities.get(ident)
    if p and p.progress.get('home_property')==u['id']:
        p.progress.pop('home_property',None);p.progress.pop('home_room',None)

def register_work_property(w, p, u, action):
    if u['kind'] not in ('business', 'farm', 'ranch'):
        return
    from engine import gazette
    p.progress['job_property'] = u['id']
    label = {'business': 'business premises', 'farm': 'farmland', 'ranch': 'ranch land'}[u['kind']]
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[p.id],f'{p.name} {action} {label} at {unit_name(w,u)}.')
    gazette.record(w, u['room'], 'Commerce', f'{p.name} {action} {label} at {unit_name(w, u)}.',
                   byline='Property register')


def buy(w,p,u):
    from engine import property_interiors
    reason=property_interiors.acquisition_problem(w,u)
    if reason:raise ValueError(reason)
    if geology_impacts.room_unusable(w,u['room']):raise ValueError('This property is temporarily closed for recovery.')
    permitted(w,p,u);claim(w,p)
    if u['owner'] or u['tenant']:raise ValueError('This property is not vacant municipal property for sale.')
    if p.gold<u['price']:raise ValueError('Purchase costs '+str(u['price'])+' gold.')
    p.gold-=u['price'];credit(w,'',u['group'],u['price']);u['owner']=p.id;u['listed']=False
    if u['kind'] in ('house','rental') and not p.progress.get('home_property'):set_home(w,p,u)
    register_work_property(w, p, u, 'bought')

def rent(w,p,u):
    from engine import property_interiors
    reason=property_interiors.acquisition_problem(w,u)
    if reason:raise ValueError(reason)
    if geology_impacts.room_unusable(w,u['room']):raise ValueError('This property is temporarily closed for recovery.')
    permitted(w,p,u);claim(w,p)
    if not u['listed'] or u['tenant'] or u['owner']==p.id:raise ValueError('This property is not available to rent.')
    if u['kind'] in ('house','rental') and p.progress.get('home_property'):raise ValueError('Leave or change your current home before renting another.')
    if p.gold<u['rent']:raise ValueError('You need the first day’s rent: '+str(u['rent'])+' gold.')
    p.gold-=u['rent'];credit(w,u['owner'],u['group'],u['rent']);u.update(tenant=p.id,due=living.state(w)['minute']+DAY,arrears=0)
    if u['kind'] in ('house','rental'):set_home(w,p,u)
    register_work_property(w, p, u, 'leased')

def units(w,gid=None):return [u for u in init(w)['units'].values() if gid is None or u['group']==gid]

def unit_name(w,u):return w.rooms[u['room']].name+' #'+str(u['index']+1)

def known_units(w,p):
    rows=units(w,w.rooms[p.location].group)
    try:
        from engine import knowledge
    except ImportError:return rows
    known=knowledge.ids(w,p,'rooms')
    return [u for u in rows if u['room'] in known or p.id in (u['owner'],u['tenant'])]

def named_arguments(w,p,verb,rest):
    import shlex
    from engine.player_names import pick
    try:parts=shlex.split(rest)
    except ValueError:raise ValueError('Close the quotation marks around each name.') from None
    tail=2 if verb in ('supply','withdraw','store','take') else 1 if verb in ('fund','collect','lease') else 0
    if len(parts)<=tail:raise ValueError('Choose a property by name; quote names when supplying an item or amount.')
    query=' '.join(parts[:-tail] if tail else parts)
    rows=known_units(w,p)
    row=pick([dict(id=u['id'],name=unit_name(w,u)) for u in rows],query,'property')
    return [row['id']]+(parts[-tail:] if tail else [])

def view(w,p):
    if not enabled(w):return {}
    s=init(w);gid=w.rooms[p.location].group;claim(w,p)
    rows=[]
    for u in known_units(w,p):
        rows.append(dict(**{k:u[k] for k in ('id','room','kind','price','rent','listed','owner','tenant')},name=unit_name(w,u),here=u['room']==p.location,mine=u['owner']==p.id,rented=u['tenant']==p.id,stored=Counter(u['storage']) if u['tenant']==p.id or not u['tenant'] and u['owner']==p.id else {}))
    from engine import property_interiors
    for row in rows:
        row.update(property_interiors.public_row(w,p,s['units'][row['id']]))
        row['stored_items']=[dict(id=i,name=w.items.get(i,{}).get('name','Unknown stored item'),quantity=n) for i,n in row['stored'].items()]
        if row['here'] or row['mine'] or row['rented']:
            row['unavailable']=geology_impacts.room_unusable(w,row['room'])
            impact=geology_impacts.room_view(w,row['room'])
            if impact['structures']:
                row['geology_impact']={'condition':impact['condition'],'unusable':impact['unusable'],'remaining_minutes':max(part['remaining_minutes'] for part in impact['structures'])}
    port=living.details(w,p.location).get('port',{})
    from engine.local_visibility import blind
    dark=p.is_player and blind(w,p)
    routes=[]
    for r in port.get('routes',[]):
        row={**r,'name':w.rooms[r['to']].name}
        if not dark:
            reason=geology_impacts.port_blocked(w,p.location,r['to'])
            row.update(unavailable=bool(reason),closure_reason=reason)
        routes.append(row)
    return dict(properties=rows,notices=p.progress.get('property_notices',[]),port={**port,'routes':routes},ships=s['ships'].get(p.location,0),population=s.get('population',{}).get(gid,0),land=Counter(v['kind'] for rid,v in s['parcels'].items() if w.rooms[rid].group==gid))

def command(ctx,args):
    w,p=ctx.world,ctx.player;init(w);claim(w,p)
    verb,_,rest=args.partition(' ');bits=rest.split();s=state(w)
    if verb in ('','list'):
        rows=known_units(w,p)
        return '\n'.join(unit_name(w,u)+' | '+u['kind']+' | '+w.rooms[u['room']].name+' | '+('owned' if u['owner'] else 'buy '+str(u['price']))+' | '+('occupied' if u['tenant'] else 'rent '+str(u['rent'])+'/day' if u['listed'] else 'not for rent') for u in rows) or 'No registered properties here.'
    bits=named_arguments(w,p,verb,rest);uid=bits[0];u=s['units'][uid]
    if verb=='route':
        from engine import frontiers
        return frontiers.route(w,p,u['room'])
    if verb=='enter':
        from engine import property_interiors
        return property_interiors.enter(ctx,u)
    permitted(w,p,u)
    if verb=='buy':buy(w,p,u);return 'Purchased '+unit_name(w,u)+'.'
    if verb=='rent':rent(w,p,u);return 'Rented '+unit_name(w,u)+' for '+str(u['rent'])+' gold per 25-hour day.'
    if verb=='home':set_home(w,p,u);return 'Home set to '+w.rooms[u['room']].name+'.'
    if verb=='leave':
        if u['tenant']!=p.id:raise ValueError('You are not the tenant.')
        if u['storage']:raise ValueError('Remove stored belongings before leaving.')
        clear_home(w,p.id,u);u.update(tenant='',due=0,arrears=0);return 'Rental ended.'
    if verb in ('supply','withdraw'):
        if (u['tenant'] or u['owner'])!=p.id:raise ValueError('Only the workplace operator can move its stock.')
        if len(bits)!=3 or not bits[2].isdigit() or not 1<=int(bits[2])<=1000:raise ValueError('Use property supply/withdraw "property name" "item name" <quantity>.')
        qty=int(bits[2]);_,stock=society.shop(w,u['room'])
        from engine.player_names import item
        iid=item(w,bits[1],p.inventory if verb=='supply' else stock['stock'])
        if iid not in w.items:raise ValueError('Unknown item.')
        if verb=='supply':
            if p.inventory.count(iid)<qty or iid in p.equipped.values():raise ValueError('Not enough unequipped items.')
            for _ in range(qty):p.inventory.remove(iid)
            stock['stock'][iid]=stock['stock'].get(iid,0)+qty
        else:
            if stock['stock'].get(iid,0)<qty:raise ValueError('Not enough workplace stock.')
            stock['stock'][iid]-=qty;p.inventory.extend([iid]*qty)
        return 'Transferred workplace stock.'
    if verb in ('store','take'):
        if p.id not in (u['owner'],u['tenant']):raise ValueError('You do not have access to this property storage.')
        if u['tenant'] and u['tenant']!=p.id:raise ValueError('The tenant controls storage while renting.')
        if len(bits)!=3 or not bits[2].isdigit() or not 1<=int(bits[2])<=1000:raise ValueError('Use property store/take "property name" "item name" <quantity>.')
        qty=int(bits[2]);source=p.inventory if verb=='store' else u['storage'];dest=u['storage'] if verb=='store' else p.inventory
        from engine.player_names import item
        iid=item(w,bits[1],source)
        if source.count(iid)<qty or (verb=='store' and iid in p.equipped.values()):raise ValueError('Not enough unequipped items available.')
        for _ in range(qty):source.remove(iid);dest.append(iid)
        return 'Moved '+str(qty)+' '+w.items[iid]['name']+'.'
    if verb in ('fund','collect'):
        if (u['tenant'] or u['owner'])!=p.id:raise ValueError('Only the current workplace operator can manage its funds.')
        if not living.details(w,u['room']).get('workshop'):raise ValueError('This property has no workplace treasury.')
        if len(bits)!=2 or not bits[1].isdigit() or int(bits[1])<1:raise ValueError('Specify an amount of gold.')
        amount=int(bits[1]);_,stock=society.shop(w,u['room'])
        if verb=='fund':
            if p.gold<amount:raise ValueError('Not enough gold.')
            p.gold-=amount;stock['gold']+=amount
        else:
            if stock['gold']<amount:raise ValueError('The workplace has insufficient earnings.')
            stock['gold']-=amount;p.gold+=amount
        return 'Transferred '+str(amount)+' gold.'
    if u['owner']!=p.id:raise ValueError('Only the owner can do that.')
    if verb=='lease':
        if len(bits)!=2 or not bits[1].isdigit() or not 1<=int(bits[1])<=1000:raise ValueError('Use property lease "property name" <daily-gold>.')
        if u['tenant'] or u['storage'] or p.progress.get('home_property')==uid:raise ValueError('Vacate the home and clear storage before offering a lease.')
        u.update(rent=int(bits[1]),listed=True);return 'Property offered for rent.'
    if verb=='unlist':u['listed']=False;return 'Future rentals disabled; any current lease is retained.'
    if verb=='vacate':clear_home(w,p.id,u);return 'This is no longer your designated home.'
    if verb=='sell':
        if living.details(w,u['room']).get('workshop'):
            _,stock=society.shop(w,u['room'])
            if stock['gold'] or any(stock['stock'].values()):raise ValueError('Clear the workplace funds and stock before selling it back.')
        if u['tenant'] or u['storage']:raise ValueError('Only vacant properties with empty storage can be sold back.')
        amount=u['price']*4//5
        if s['treasuries'].get(u['group'],0)<amount:raise ValueError('The municipal treasury cannot afford the buyback.')
        clear_home(w,p.id,u);s['treasuries'][u['group']]-=amount;p.gold+=amount;u.update(owner='',listed=True);return 'Sold back for '+str(amount)+' gold.'
    raise ValueError('Use property list, route, buy, rent, home, leave, store, take, lease, unlist, vacate or sell.')

def spend_material(w,gid,iid):
    cfg=w.groups[gid].get('development',{});rid=cfg.get('depot');s=state(w)
    if rid not in w.rooms or geology_impacts.room_unusable(w,rid):return False
    _,stock=society.shop(w,rid)
    worker=next((e for e in w.entities_in_room(rid) if e.alive and not e.is_player and w.npcs.get(e.source_def,{}).get('profession')=='producer'),None)
    cost=max(1,w.items.get(iid,{}).get('value',1))
    if not worker or stock['stock'].get(iid,0)<1 or s['treasuries'].get(gid,0)<cost:return False
    stock['stock'][iid]-=1;stock['gold']+=cost;s['treasuries'][gid]-=cost;return True

def adapt_land(w,gid,pop):
    s=state(w);cfg=w.groups[gid]['development'];lots=[rid for rid in s['parcels'] if w.rooms[rid].group==gid]
    # Absence for school/work does not make a civilian household's home vacant.
    # This reservation grants no legal title and ends when no enrolled member
    # remains alive. Explicit property actions and disaster rules are unchanged.
    households=getattr(w,'living_state',{}).get('population',{}).get('households',{})
    resident_homes={h.get('home_room') for h in households.values()
                    if any((person:=w.entities.get(eid)) is not None and person.alive
                           and person.progress.get('population') for eid in h.get('members',[]))}
    wanted={kind:max(minimum,(pop+cfg.get('people_per_'+kind,ratio)-1)//cfg.get('people_per_'+kind,ratio)) for kind,ratio,minimum in [('farm',10,2),('ranch',30,1),('business',10,2),('recreation',25,1),('hunting',20,2)]}
    wanted={'farm':wanted['farm'],'ranch':wanted['ranch'],'house':max(4,(pop*cfg.get('housing_percent',125)+99)//100),**{k:v for k,v in wanted.items() if k not in ('farm','ranch')}}
    current=Counter('house' if u['kind']=='rental' else u['kind'] for u in units(w,gid) if u['kind'] in ('house','rental','business'))
    for rid in lots:
        kind=s['parcels'][rid]['kind']
        if kind in ('farm','ranch','recreation','hunting'):current[kind]+=1
    for kind,amount in wanted.items():
        if current[kind]>=amount:continue
        options=[]
        for rid in lots:
            if geology_impacts.room_unusable(w,rid):continue
            c=living.details(w,rid)['property_plot'];old=s['parcels'][rid]['kind'];us=[u for u in units(w,gid) if u['room']==rid]
            from engine import property_interiors
            protected=rid in resident_homes or property_interiors.parcel_in_use(w,rid) or any(u['owner'] or u['tenant'] or u['storage'] for u in us)
            if old=='reserve' and not protected and not w.entities_in_room(rid) and not w.rooms[rid].items and kind in c.get('allowed',KINDS):options.append(rid)
            elif kind=='house' and old in ('house','rental') and len(us)<c.get('max_units',4):options.insert(0,rid)
            elif current.get('house',0)>wanted['house']+cfg.get('surplus_buffer',8) and old in ('house','rental') and not protected and not w.rooms[rid].items and not w.entities_in_room(rid):options.append(rid)
        if not options:continue
        rid=options[0]
        if not spend_material(w,gid,cfg.get('construction_item','civic_building_kit')):break
        old=s['parcels'][rid]['kind']
        if old not in ('house','rental') or kind!='house':
            for uid in [u['id'] for u in units(w,gid) if u['room']==rid]:del s['units'][uid]
            s['parcels'][rid]['kind']=kind
        if kind!='reserve':new_unit(w,rid)
        s['parcels'][rid]['changed']=living.state(w)['minute'];current[kind]+=1;apply_land(w,rid,previous_kind=old)
        from engine import gazette
        gazette.record(w,rid,'Civic works','The local builders completed a '+kind.replace('_',' ')+' project.')
        s['log']=(s['log']+[dict(action='construction',room=rid,kind=kind,minute=living.state(w)['minute'])])[-200:]
        # One construction project per region per daily planning cycle.
        break

def advance(w):
    if not enabled(w):return
    s=init(w);now=living.state(w)['minute']
    ports_arrive(w)
    for u in list(s['units'].values()):
        # Preserve title, leases, belongings and existing arrears during recovery.
        # Postpone billing instead of accumulating disaster-related debt.
        if u['tenant'] and geology_impacts.room_unusable(w,u['room']):
            u['due']=max(u['due'],now+DAY)
            continue
        if not u['tenant'] or now<u['due']:continue
        tenant=w.entities.get(u['tenant'])
        # Offline player leases accrue no new charge until their character is present.
        if tenant is None:continue
        if tenant.alive and tenant.gold>=u['rent']:
            tenant.gold-=u['rent'];credit(w,u['owner'],u['group'],u['rent']);u.update(due=now+DAY,arrears=0)
        else:
            u['arrears']+=1;u['due']=now+DAY;notify(w,tenant,'Rent unpaid at '+unit_name(w,u)+'; '+str(max(0,3-u['arrears']))+' grace days remain.')
            if u['arrears']>=3:
                tenant.inventory.extend(u['storage']);u['storage']=[]
                notify(w,tenant,'Rental ended after three unpaid days; stored belongings were returned to your inventory.')
                clear_home(w,tenant.id,u);u.update(tenant='',arrears=0,due=0)
    if now-s['last']<DAY:return
    s['last']=now
    by_group={gid:[] for gid,g in w.groups.items() if g.get('development')}
    for e in w.entities.values():
        if e.alive and e.group_id in by_group and relationships.profile(w,e)['sentient']:by_group[e.group_id].append(e)
    s['population']={gid:len(es) for gid,es in by_group.items()}
    from engine import property_interiors
    for gid,people in by_group.items():
        adapt_land(w,gid,len(people));available=[u for u in units(w,gid) if u['kind'] in ('house','rental') and not geology_impacts.room_unusable(w,u['room']) and not u['tenant'] and (not u['owner'] or u['listed']) and not property_interiors.acquisition_problem(w,u)];available.sort(key=lambda u:(not bool(u['owner']),u['rent']))
        # Keep a small explicit vacancy reserve for joining players.
        assigned=0
        for p in people:
            if p.is_player:claim(w,p);continue
            # Cohort home membership is not a purchase/lease instruction.
            # Keep its authored household together; explicit property actions
            # and existing leases still use their normal rules.
            if p.progress.get('population'):continue
            if assigned>=3:continue
            if p.progress.get('home_property'):
                if w.npcs.get(p.source_def,{}).get('profession')=='producer' and not p.progress.get('job_property'):
                    business=next((u for u in units(w,gid) if u['kind'] in ('business','farm','ranch') and not geology_impacts.room_unusable(w,u['room']) and not u['owner'] and not u['tenant'] and not property_interiors.acquisition_problem(w,u) and p.gold>=u['price']+50),None)
                    if business:p.progress['housing_target']=business['id'];assigned+=1
                continue
            if len(available)<=w.groups[gid]['development'].get('vacancy_reserve',4):continue
            u=available.pop(0)
            # NPCs travel to view/acquire housing, never teleport to purchase it.
            p.progress['housing_target']=u['id'];assigned+=1
            if p.location!=u['room']:continue
            try:
                if not u['owner'] and p.gold>=u['price']+20:buy(w,p,u)
                elif p.gold>=u['rent']+10:rent(w,p,u)
                else:continue
                p.progress.pop('housing_target',None)
            except ValueError:continue
    ports_advance(w)

def housing_step(w,p):
    if not enabled(w):return False
    if not p.is_player and p.progress.get('population'):return False
    s=init(w);uid=p.progress.get('housing_target');u=s['units'].get(uid)
    if not u:return False
    from engine import property_interiors
    if property_interiors.acquisition_problem(w,u):p.progress.pop('housing_target',None);return False
    if geology_impacts.room_unusable(w,u['room']):p.progress.pop('housing_target',None);return False
    if u['tenant'] or u['owner'] and not u['listed']:p.progress.pop('housing_target',None);return False
    if p.gold<u['rent']+10:return False
    if p.location==u['room']:
        try:
            if not u['owner'] and p.gold>=u['price']+20:buy(w,p,u)
            else:rent(w,p,u)
        except ValueError:return False
        p.progress.pop('housing_target',None);return False
    step=living.next_step(w,p.location,u['room'],p)
    if step:w.move_entity(p.id,step);p.activity='viewing a home';return True
    return False

def sail(ctx,args):
    from engine import livelihoods
    if not livelihoods.room_open(ctx.world,ctx.player.location):raise ValueError('The harbour service is closed. Return during opening hours.')
    w,p=ctx.world,ctx.player;s=init(w);port=living.details(w,p.location).get('port',{})
    routes=port.get('routes',[])
    if not port.get('enabled'):raise ValueError('Visit a port to board a boat.')
    if not args:return '\n'.join(w.rooms[r['to']].name+' | fare '+str(r.get('fare',3)) for r in routes)
    from engine.player_names import pick
    dest=pick([dict(id=r['to'],name=w.rooms[r['to']].name) for r in routes],args,'port destination')['id']
    r=next(r for r in routes if r['to']==dest)
    reason=geology_impacts.port_blocked(w,p.location,r['to'])
    if reason:raise ValueError(reason)
    if not livelihoods.room_open(w,r['to']):raise ValueError('The destination harbour service is closed.')
    if not p.alive:raise ValueError('You must be alive to travel.')
    if society.standing(w,p,w.rooms[r['to']].group)<50:raise ValueError('The destination port refuses your faction passage.')
    own=any(w.items.get(i,{}).get('boat') for i in p.inventory)
    if not own and s['ships'].get(p.location,0)-sum(c['origin']==p.location for c in s['cargo'])<1:raise ValueError('No boat is available; the shipyard must build one.')
    fare=0 if own else r.get('fare',3)
    if p.gold<fare:raise ValueError('Passage costs '+str(fare)+' gold.')
    p.gold-=fare;credit(w,'',w.rooms[p.location].group,fare);w.move_entity(p.id,r['to'])
    return 'You arrive by boat at '+w.rooms[r['to']].name+'.'+living.on_entry(w,p)

def ports_arrive(w):
    s=state(w);now=living.state(w)['minute'];economy=society.economy(w)
    for shipment in list(s['cargo']):
        if shipment['arrival']>now:continue
        # Paid cargo remains aboard its reserved ship until the passage reopens.
        if geology_impacts.room_unusable(w,shipment['origin']) or geology_impacts.room_unusable(w,shipment['to']):continue
        if shipment['to'] not in w.rooms or geology_impacts.port_blocked(w,shipment['origin'],shipment['to']):continue
        if shipment['to'] in w.rooms:
            _,stock=society.shop(w,shipment['to']);i=shipment['item'];stock['stock'][i]=stock['stock'].get(i,0)+shipment['quantity']
            from engine import gazette
            gazette.record(w,shipment['to'],'Harbour','The harbour received '+str(shipment['quantity'])+' × '+w.items.get(i,{}).get('name','cargo')+' from '+w.rooms[shipment['origin']].name+'.')
            s['log']=(s['log']+[dict(action='cargo_arrived',**shipment)])[-200:]
        s['cargo'].remove(shipment)

def ports_advance(w):
    s=state(w);now=living.state(w)['minute'];economy=society.economy(w)
    for rid,rd in w.room_details.items():
        port=rd.get('port',{})
        from engine import livelihoods
        if not port.get('enabled') or not livelihoods.room_open(w,rid):continue
        _,dock=society.shop(w,rid)
        if s['ships'].get(rid,0)<port.get('berths',3) and dock['stock'].get('civic_boat',0)>0:
            dock['stock']['civic_boat']-=1;s['ships'][rid]=s['ships'].get(rid,0)+1
        if s['ships'].get(rid,0)<1:continue
        for route in port.get('routes',[]):
            if s['ships'].get(rid,0)-sum(c['origin']==rid for c in s['cargo'])<=1:break
            dest=route['to'];gid=w.rooms[rid].group;othergid=w.rooms[dest].group
            if geology_impacts.port_blocked(w,rid,dest) or not livelihoods.room_open(w,dest):continue
            if min(society.bounds(w,gid,othergid)[2],society.bounds(w,othergid,gid)[2])<50:continue
            _,buyer=society.shop(w,dest)
            # Import regional production shortfalls; each voyage has finite capacity.
            for iid in port.get('cargo_items',[]):
                if buyer['stock'].get(iid,0)>=port.get('import_target',6):continue
                source=next((stock for room,stock in economy['shops'].items() if room!=dest and w.rooms[room].group==gid and livelihoods.room_open(w,room) and stock['stock'].get(iid,0)>8),None)
                if not source:continue
                cost=max(1,w.items[iid].get('value',1));qty=min(route.get('capacity',4),source['stock'][iid]-8,buyer['gold']//cost)
                if qty<1:continue
                source['stock'][iid]-=qty;buyer['gold']-=qty*cost;source['gold']+=qty*cost
                s['cargo'].append(dict(origin=rid,to=dest,item=iid,quantity=qty,arrival=now+route.get('travel_minutes',60)))
                break

def register(reg):
    from engine.commands import Command
    reg.register(Command('property','Buy, rent and manage property','property <action>',command,available=lambda ctx:enabled(ctx.world),example='property list'))
    reg.register(Command('sail','Board a port boat','sail <port name>',sail,available=lambda ctx:enabled(ctx.world),example='sail'))

def validate(data):
    errors=[];rooms={r['id'] for r in data['room']};items={i['id'] for i in data['item']}
    for g in data.get('group',[]):
        cfg=g.get('development',{})
        if cfg and (cfg.get('depot') not in rooms or cfg.get('construction_item') not in items):errors.append(g['id']+': invalid development depot or material')
    for r in data['room']:
        c=r.get('property_plot',{})
        if c.get('enabled'):
            if c.get('kind') not in KINDS:errors.append(r['id']+': invalid land use')
            if type(c.get('max_units')) is not int or not 1<=c['max_units']<=20:errors.append(r['id']+': invalid property capacity')
            if type(c.get('initial_units')) is not int or not 0<=c['initial_units']<=c.get('max_units',0):errors.append(r['id']+': invalid initial units')
            if any(k not in KINDS for k in c.get('allowed',[])):errors.append(r['id']+': invalid permitted land use')
            for k in ('price','rent'):
                if type(c.get(k)) is not int or c[k]<1:errors.append(r['id']+': invalid '+k)
        port=r.get('port',{})
        if port.get('enabled'):
            if not r.get('workshop'):errors.append(r['id']+': port needs a cargo depot')
            for route in port.get('routes',[]):
                if type(route.get('fare')) is not int or route['fare']<0:errors.append(r['id']+': invalid fare')
                if route.get('to') not in rooms:errors.append(r['id']+': unknown port route')
                if any(type(route.get(k)) is not int or route[k]<1 for k in ('capacity','travel_minutes')):errors.append(r['id']+': invalid voyage limits')
            if any(i not in items for i in port.get('cargo_items',[])):errors.append(r['id']+': unknown cargo item')
    return errors
