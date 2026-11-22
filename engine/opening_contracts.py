"""Finite first commissions offered at actual Founding Cities kitchens and markets."""
from engine import earned_lodging as lodging
from engine import worldtime
from engine import ecology, frontiers, geology_impacts, livelihoods, living, sleep_movement, society

MARK = 'founding_cities_work_v1'
BOOK = 'opening_commissions_v1'
DONE = 'opening_commission_paid_v1'
DECLINED = 'opening_commission_declined_v1'
BATCH = 6
WAGE = 30
STEW = 'lw_stew'
VEGETABLES = {'lw_carrot': 1, 'lw_onion': 1, 'lw_potato': 1}
# The counter commissions one tray when meals fall six below its service target.
# A supplier must retain two servings for its own counter.
TARGET = 18
RESERVE = 2


def enabled(w):
    m=getattr(w,'metadata',{})
    return (isinstance(m.get('municipal_genesis'),dict) and m['municipal_genesis'].get('version') == 1
            and m['municipal_genesis'].get('seed') == 20261122
            and m.get('civic_opening_release') in ('1.10.0-rc1', '1.10.0')
            and lodging.enabled(w) and living.enabled(w) and society.enabled(w))


def facilities(w):
    return w.metadata.get('city_population_198',{}).get('facilities',{})


def kitchen(f):
    return 'emberhollow_inn_kitchen' if f['inn']=='emberhollow_inn' else f['inn']


def local(w,room):
    return next(((city,f) for city,f in facilities(w).items()
                 if city in lodging.CITY_UNITS and room in (f['inn'],kitchen(f),f['market'])),None)


def staff(w,city,f,job,room):
    if job=='cook':
        ident={'Dawnwatch':'chef_ragnar','Hollowcrown':'Vile'}.get(city,f['inn']+'_merchant')
    else:
        market=f['market']
        ident=(market.replace('_4','_merchant_4') if city in ('Dawnwatch','Hollowcrown') else market+'_merchant')
    return next((n for n in w.entities_in_room(room) if n.source_def==ident and n.alive
                 and not n.is_player and livelihoods.service_open(w,n)),None)


def route(w,p,dest):
    path=frontiers.path(w,p.location,dest,p)
    if path is None:
        raise ValueError('There is no open walking route to '+w.rooms[dest].name+'.')
    return ', '.join(step[1] for step in path)


def business(w,site):
    shop=living.state(w).get('economy',{}).get('shops',{}).get(site)
    if not shop or not isinstance(shop.get('stock'),dict) or type(shop.get('gold')) is not int:
        raise ValueError('The business has not opened its stock and cash ledger yet.')
    return shop


def planning(w,p,city,f,job):
    source=f['inn']
    dest=source if job=='cook' else f['market']
    site=kitchen(f) if job=='cook' else dest
    counters=(site,source) if job=='cook' else (site,)
    if p.location not in counters:
        raise ValueError('Ask in person at '+w.rooms[site].name+'.')
    sponsor=staff(w,city,f,job,p.location)
    if not sponsor:
        for counter in set(counters)-{p.location}:
            present=staff(w,city,f,job,counter)
            if present:
                raise ValueError('Ask '+present.name+' in person at '+w.rooms[counter].name+'.')
        schedule=w.room_details[site].get('opening_hours',{})
        start=schedule.get('start',420)
        raise ValueError(f'{w.rooms[site].name} has no hiring staff on duty here. Posted opening {start//60:02}:{start%60:02}.')
    if geology_impacts.room_unusable(w,source) or geology_impacts.room_unusable(w,dest):
        raise ValueError('One of the contracted businesses is closed.')
    if job=='cook' and p.location!=site:
        route(w,p,site)
    if job=='deliver':
        route(w,p,source)
        if frontiers.path(w,source,dest,p) is None:
            raise ValueError('The return delivery route is closed.')
    src=business(w,source)
    buyer=business(w,dest)
    cookbook=w.recipes.get(STEW,{})
    if (job=='cook' and
        (STEW not in w.room_details[source].get('workshop',{}).get('recipes',())
         or 'kitchen' not in living.details(w,site).get('facilities',())
         or cookbook.get('ingredients')!=VEGETABLES or cookbook.get('outputs')!={STEW:1}
         or type(cookbook.get('minutes')) is not int or not 1<=cookbook['minutes']<=60
         or cookbook.get('prerequisites') or cookbook.get('required_abilities')
         or not ecology.available(w,site,cookbook))):
        raise ValueError('The kitchen cannot make its published stew recipe here.')
    assigned=sum(BATCH for order in living.state(w).get(BOOK,{}).values() if order['dest']==dest)
    limit=w.room_details[dest].get('workshop',{}).get('stock_limit',0)
    if buyer['stock'].get(STEW,0)+assigned+BATCH>min(TARGET,limit):
        raise ValueError('There is enough stew on the shelf or on order. No work is posted.')
    materials=({item:n*BATCH for item,n in VEGETABLES.items()} if job=='cook' else {STEW:BATCH})
    for item,count in materials.items():
        if src['stock'].get(item,0) < count+(RESERVE if job=='deliver' else 0):
            raise ValueError('The supplier has insufficient unreserved stock for this order.')
    invoice=BATCH*society.price(w,STEW,False) if job=='deliver' else 0
    if buyer['gold'] < WAGE+invoice:
        raise ValueError('The employer cannot fund wages and supplies.')
    return dict(job=job,city=city,source=source,dest=dest,site=site,materials=materials,
                invoice=invoice,minutes=BATCH*cookbook['minutes'] if job=='cook' else 0,
                phase='reserved',employer=sponsor.name)


def rooms(w,p,order):
    buyer=business(w,order['dest'])
    used={row['unit'] for row in lodging._rows(w).values()}
    for uid in lodging.CITY_UNITS[order['city']]:
        unit=lodging._units(w).get(uid)
        if (uid in used or not unit or not lodging._eligible(w,p,unit)
                or buyer['gold']<WAGE+order['invoice']+unit['rent']*worldtime.DAYS_PER_WEEK
                or frontiers.path(w,p.location,unit['room'],p) is None):
            continue
        yield dict(unit=uid,owner=unit['owner'],rent=unit['rent'],phase='held',remaining=lodging.WEEK)


def instruction(w,p,o):
    if o['phase']=='reserved':
        dest=o['site'] if o['job']=='cook' else o['source']
        verb='cook' if o['job']=='cook' else 'collect'
    elif o['phase']=='preparing':
        return f"Preparing six portions: {o['minutes']} active game minutes remain. Stay awake in {w.rooms[o['site']].name}."
    else:
        dest=o['site'] if o['job']=='cook' else o['dest']
        verb='deliver'
    where=w.rooms[dest].name
    if p.location!=dest:
        return f"Go to {where} ({route(w,p,dest)}), then use startwork {verb}."
    return f"At {where}, use startwork {verb}."


def tick(w,minutes):
    state=getattr(w,'living_state',{})
    if not state.get(BOOK) or type(minutes) is not int or minutes<=0:
        return
    present=getattr(w,'_earned_lodging_presence',None)
    for ident,o in state[BOOK].items():
        p=w.entities.get(ident)
        if (o['phase']!='preparing' or not p or not p.alive or p.location!=o['site']
                or not present or not present(ident) or sleep_movement.asleep(w,p)
                or geology_impacts.room_unusable(w,p.location)):
            continue
        o['minutes']=max(0,o['minutes']-minutes)
        if o['minutes']==0:o['phase']='prepared'


def command(ctx,args):
    w,p=ctx.world,ctx.player
    words=args.casefold().split() or ['status']
    verb=words[0]
    ctx.time_accounted=True
    state=living.state(w)
    jobs=state.get(BOOK,{})
    o=jobs.get(p.id)
    if verb=='lodging':
        return lodging.status(w,p)
    if verb=='check-in':
        return lodging.check_in(w,p)
    if not o and (p.progress.get(DONE) or p.progress.get(DECLINED)):
        return lodging.status(w,p) if p.progress.get(DONE) else 'You declined the opening offer. You can explore and trade normally.'
    if verb in ('decline','cancel'):
        if o:
            if o['phase']=='collected' and p.location!=o['source']:
                raise ValueError('Return the sealed delivery to '+w.rooms[o['source']].name+' before cancelling.')
            cancel(state,p.id)
        if verb=='decline':p.progress[DECLINED]=True
        return 'No wage paid. Any reserved funds, remaining goods and lodging have been returned.'
    if o:
        if verb in ('status','accept'):return instruction(w,p,o)
        if verb=='cook' and o['job']=='cook' and o['phase']=='reserved' and p.location==o['site']:
            if sleep_movement.asleep(w,p) or geology_impacts.room_unusable(w,p.location):
                raise ValueError('The cook and kitchen both need to be available.')
            o['phase']='preparing'
            ctx.time_accounted=False
            return instruction(w,p,o)
        if verb=='collect' and o['job']=='deliver' and o['phase']=='reserved' and p.location==o['source']:
            if geology_impacts.room_unusable(w,p.location):raise ValueError('The supplier is closed.')
            o['phase']='collected'
            return 'You collect six sealed servings. '+instruction(w,p,o)
        if verb=='deliver' and o['phase'] in ('collected','prepared') and p.location==o['site']:
            if geology_impacts.room_unusable(w,p.location):raise ValueError('The delivery counter is closed.')
            if not stock_fits(w,o):raise ValueError('The agreed shelf is full. Your pay and delivery are reserved. You may cancel.')
            shelf=business(w,o['dest']);source=business(w,o['source'])
            room=lodging._rows(w).get(p.id)
            if not room or room['phase']!='held':
                raise ValueError('The lodging hold requires review. Your delivery and pay remain reserved.')
            shelf['stock'][STEW]=shelf['stock'].get(STEW,0)+BATCH
            source['gold']+=o['invoice']
            p.gold+=WAGE
            p.progress[DONE]=o['dest']
            del jobs[p.id]
            w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
            msg=lodging.ready(w,p)
            return 'Six servings delivered. You received 30 gold in labour wages.'+msg
        return instruction(w,p,o)
    if p.progress.get('home_property') or p.progress.get('home_room') or p.id in lodging._rows(w):
        raise ValueError('These sponsored contracts are available to newcomers without lodging.')
    place=local(w,p.location)
    if not place:
        return 'Ask at a city inn kitchen about cooking, or a city food market about deliveries.'
    city,f=place
    if verb=='status':
        lines=[]
        for job in ('cook','deliver'):
            try:
                order=planning(w,p,city,f,job)
                choices=list(rooms(w,p,order))
                if not choices:raise ValueError('No accessible vacant room and funded week are available for this offer.')
                detail=(f"Prepare six servings of Vegetable Stew over {order['minutes']} active game minutes."
                        if job=='cook' else f"Collect six existing servings from {w.rooms[f['inn']].name} and return them to this market.")
                lines.append(f"{order['employer']} offers 30 gold total for this job. {detail} The business supplies the goods and prepays a week of lodging separately.")
                for row in choices:
                    lines.append(f"{lodging.describe(w,row)} Use startwork accept {job} {row['unit']} {lodging.cost(row)}.")
            except ValueError as exc:lines.append(str(exc))
        return '\n'.join(lines)
    if verb!='accept' or len(words)!=4 or words[1] not in ('cook','deliver'):
        raise ValueError('Use startwork status for current offers, or startwork decline to explore normally.')
    job,uid,quoted=words[1:]
    order=planning(w,p,city,f,job)
    row=next((r for r in rooms(w,p,order) if r['unit']==uid and str(lodging.cost(r))==quoted),None)
    if row is None:raise ValueError('That room or quote is no longer available. Check startwork status.')
    buyer=business(w,order['dest'])
    supplier=business(w,order['source'])
    # No await or request boundary between the checks and these finite reservations.
    for item,count in order['materials'].items():supplier['stock'][item]-=count
    buyer['gold']-=WAGE+order['invoice']
    lodging.hold(w,p,buyer,row)
    state.setdefault(BOOK,{})[p.id]=order
    return 'Order accepted. '+instruction(w,p,order)


def stock_fits(w,order):
    dest=order['dest']
    return business(w,dest)['stock'].get(STEW,0)+BATCH<=w.room_details[dest]['workshop']['stock_limit']


def cancel(state,ident):
    """Release only the identified commission in either an active or saved world."""
    order=state.get(BOOK,{}).get(ident)
    if not order:return
    shops=state['economy']['shops']
    buyer=shops[order['dest']]
    src=shops[order['source']]
    lodging_book=state[lodging.KEY]
    room=lodging_book[ident]
    if room['phase']!='held':raise ValueError('The accommodation and order require review.')
    goods={STEW:BATCH} if order['phase']=='prepared' else order['materials']
    for item,count in goods.items():src['stock'][item]=src['stock'].get(item,0)+count
    buyer['gold']+=WAGE+order['invoice']+lodging.cost(room)
    del lodging_book[ident]
    del state[BOOK][ident]


def relinquish(state,ident,progress):
    """Permanently removed characters release their outstanding business obligations."""
    if not progress.get(MARK):
        return
    if ident in state.get(BOOK,{}):
        cancel(state,ident)
        return
    sponsor=progress.get(DONE)
    row=state.get(lodging.KEY,{}).get(ident)
    if not row or not sponsor:
        return
    if row['phase']=='ready':
        state['economy']['shops'][sponsor]['gold']+=lodging.cost(row)
    elif row['phase']=='active':
        unit=state.get('settlements',{}).get('units',{}).get(row['unit'])
        if unit and unit.get('tenant')==ident:
            unit.update(tenant='',due=0,arrears=0)
    else:
        raise ValueError('The accommodation account requires review.')
    del state[lodging.KEY][ident]
