"""Optional sponsored opening lodging using extant Dawnwatch rental units.

Pending holds reserve existing business gold and an exact real unit without
moving the player or crediting a landlord. Paid activation is separate and
requires the rightful player to physically reach the accepted parcel.
"""
from engine import geology_impacts, property_interiors, society, worldtime

FLAG = 'earned_start_lodging_pilot'
VERSION = 'dawnwatch-boarding-week-v1'
KEY = 'earned_lodging_v1'
UNITS = ('ward_dawn_4_5:1','ward_dawn_5_1:1')
CHOICES = dict(zip(('boarding-house','orchard-cottage'),UNITS))
ROOMS = {'ward_dawn_4_5:1':'ward_dawn_4_5', 'ward_dawn_5_1:1':'ward_dawn_5_1'}
WEEK = worldtime.DAYS_PER_WEEK * worldtime.MINUTES_PER_DAY
HOLDING = ('held','ready')
KITCHEN = 'emberhollow_inn_kitchen'
COMMON = tuple(('north', f'fw_dawn_{i}') for i in (33,26,19,12,5))
PATHS = {
    'ward_dawn_4_5': COMMON + (('west','fw_dawn_4'),) + tuple(('north',f'ward_dawn_4_{i}') for i in range(6)),
    'ward_dawn_5_1': COMMON + tuple(('north',f'ward_dawn_5_{i}') for i in range(2)),
}
INVALID = 'Sponsored lodging records need review. No charge or housing change was made.'


def enabled(w):
    return getattr(w,'metadata',{}).get(FLAG)==VERSION


def _rows(w):
    rows=getattr(w,'living_state',{}).get(KEY,{})
    if not isinstance(rows,dict) or len(rows)>len(UNITS):
        raise ValueError(INVALID)
    seen=set()
    for ident,r in rows.items():
        if (not isinstance(ident,str) or not isinstance(r,dict)
                or set(r)!={'unit','owner','rent','phase','remaining'}
                or r['unit'] not in UNITS or r['unit'] in seen
                or not isinstance(r['owner'],str) or type(r['rent']) is not int or not 1<=r['rent']<=1000
                or r['phase'] not in (*HOLDING,'active')
                or type(r['remaining']) is not int or not 0<=r['remaining']<=WEEK
                or (r['phase'] in HOLDING and r['remaining']!=WEEK)):
            raise ValueError(INVALID)
        seen.add(r['unit'])
    return rows


def _units(w):
    return getattr(w,'living_state',{}).get('settlements',{}).get('units',{})


def reserved(w,u):
    """Public market/NPC property gate; malformed records cannot leak a unit."""
    if u.get('id') not in UNITS:
        return False
    try:return any(r['unit']==u['id'] and r['phase'] in HOLDING for r in _rows(w).values())
    except (TypeError,ValueError):return True


def prepaid(w,u):
    """Normal rent/arrears never run for paid protected tenure."""
    if u.get('id') not in UNITS:
        return False
    try:
        return any(r['unit']==u['id'] and r['phase']=='active' for r in _rows(w).values())
    except (TypeError,ValueError):return True


def _eligible(w,p,u,*,own_hold=False):
    uid=u['id']
    rid=ROOMS[uid]
    if (u.get('room')!=rid or rid not in w.rooms or u.get('group')!='good_guys'
            or u.get('kind') not in ('house','rental') or not u.get('listed')
            or u.get('tenant') or u.get('owner')==p.id or u.get('storage')
            or property_interiors.acquisition_problem(w,u,ignore_opening_hold=own_hold)
            or geology_impacts.room_unusable(w,rid) or society.standing(w,p,u['group'])<50):
        return False
    interior=property_interiors.room_id(uid)
    room=w.rooms.get(interior)
    if not room or not property_interiors.is_interior(w,u,interior) or room.entities or room.items:
        return False
    port=w.room_details.get(interior,{}).get('unit_front',rid)
    if port not in w.rooms or room.exits.get('out')!=port:
        return False
    return (type(u.get('rent')) is int and 1<=u['rent']<=1000
            and isinstance(u.get('owner'),str))


def _route_ok(w,p,origin,dest):
    # Verify every authored public approach, not a navigation shortcut.
    from engine import frontiers
    if origin!=KITCHEN or dest not in PATHS:return False
    for direction,target in PATHS[dest]:
        if (target not in w.rooms or w.rooms[origin].exits.get(direction)!=target
                or w.rooms[target].group not in ('good_guys',None)
                or w.room_details.get(target,{}).get('hidden')
                or geology_impacts.room_unusable(w,target)
                or frontiers.blocked(w,origin,direction,p)):
            return False
        origin=target
    return origin==dest

def plan(w,p,pocket,wage,*,requested=None,price=None):
    """Pure preflight: if actual vacancy and capable funds do not exist, refuse."""
    if not enabled(w):
        return None
    if p.progress.get('home_property') or p.progress.get('home_room'):
        raise ValueError('This starter accommodation is for newcomers without a home.')
    rows=_rows(w)
    if p.id in rows:
        raise ValueError('You already have a named opening lodging record.')
    booked={r['unit'] for r in rows.values()}
    candidates=(CHOICES.get(requested),) if requested is not None else UNITS
    for uid in candidates:
        u=_units(w).get(uid)
        if (not u or uid in booked or not _eligible(w,p,u)
                or not _route_ok(w,p,p.location,ROOMS[uid])):
            continue
        rent=u['rent']
        if price is not None and str(rent*worldtime.DAYS_PER_WEEK)!=price:
            raise ValueError('The quoted lodging rate changed. Check startwork status; nothing is reserved.')
        if pocket['gold']<wage+rent*worldtime.DAYS_PER_WEEK:
            continue
        return dict(unit=uid,owner=u['owner'],rent=rent,phase='held',remaining=WEEK)
    if requested is not None:
        raise ValueError('That exact lodging is no longer confirmed or funded. Nothing reserved. Check startwork status for another actual choice.')
    raise ValueError('No reachable vacant week the business can fund is confirmed. No housing, wages or goods have been reserved.')


def cost(row):
    return row['rent'] * worldtime.DAYS_PER_WEEK


def describe(w,row):
    name=w.rooms.get(ROOMS[row['unit']])
    return ((name.name if name else 'The registered room (currently unavailable)') +
            f" for one {worldtime.DAYS_PER_WEEK}-day game week; {cost(row)} existing sponsor gold, no charge to the worker.")


def choices(w,p,pocket,wage):
    offered=[]
    for alias in CHOICES:
        try:row=plan(w,p,pocket,wage,requested=alias)
        except ValueError:continue
        if row:
            offered.append(f'\n{describe(w,row)} Choose it with startwork accept {alias} {cost(row)}.')
    return ''.join(offered)


def hold(w,p,pocket,plan):
    if plan is None:return
    pocket['gold']-=cost(plan)
    w.living_state.setdefault(KEY,{})[p.id]=plan


def refund(w,p,pocket):
    rows=_rows(w);row=rows.get(p.id)
    if row is None:return
    if row['phase'] not in HOLDING:
        raise ValueError('An active paid lodging term cannot be refunded here.')
    pocket['gold']+=cost(row)
    del rows[p.id]


def ready(w,p):
    row=_rows(w).get(p.id)
    if row is None:return ''
    if row['phase']!='held':
        raise ValueError(INVALID)
    row['phase']='ready'
    return ' Sponsored lodging is ready: '+describe(w,row)+' Go to its public parcel and use startwork check-in.'


def check_in(w,p):
    row=_rows(w).get(p.id)
    if not row or row['phase'] not in ('ready','active'):
        raise ValueError('No earned prepaid room is ready. Complete an agreed sponsored job first.')
    if row['phase']=='active':
        return 'Your sponsored week is already active; no additional payment. '+status(w,p)
    u=_units(w).get(row['unit'])
    if (p.location!=ROOMS[row['unit']] or p.progress.get('home_property') or p.progress.get('home_room')
            or not u or not _eligible(w,p,u,own_hold=True)
            or u['owner']!=row['owner'] or u['rent']!=row['rent']):
        raise ValueError('Visit the same eligible available parcel without another home. Your sponsor escrow remains reserved.')
    # At this exact, persisted municipal/private unit, a real landlord or
    # existing treasury receives the quoted gold. Keep the stock/lease actor
    # intrinsic, never infer own authority from a client or reset a clock.
    from engine import settlements
    if not u['owner'] and u['group'] not in getattr(w,'living_state',{}).get('settlements',{}).get('treasuries',{}):
        raise ValueError('The registered payee is unavailable. No charge was made.')
    settlements.credit(w,u['owner'],u['group'],cost(row))
    u.update(tenant=p.id,due=0,arrears=0)
    p.progress.update(home_property=u['id'],home_room=property_interiors.room_id(u['id']))
    row['phase']='active'
    w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
    return 'Checked in once and paid the lawful payee from sponsor escrow. '+status(w,p)


def status(w,p):
    row=_rows(w).get(p.id)
    if not row:return 'No real sponsored lodging is reserved.'
    if row['phase'] in HOLDING:
        return 'Reserved: '+describe(w,row)+(' Check in after the funded job is complete.' if row['phase']=='held' else ' At its public parcel, use startwork check-in.')
    return (f"Prepaid accommodation: {row['remaining']} active game minutes remain. "
            'No charge, time used or arrears while away from play; no automatic renewal.')


def check_book(w,p):
    row=_rows(w).get(p.id)
    if row and row['phase']!='held':
        raise ValueError(INVALID)


def finish(w,p,u,reason):
    rows=_rows(w);rec=rows.get(p.id)
    if (not rec or rec['phase']!='active' or rec['unit']!=u['id'] or u.get('tenant')!=p.id):
        raise ValueError(INVALID)
    from engine import settlements
    p.inventory.extend(u.get('storage',[]));u['storage']=[]
    settlements.clear_home(w,p.id,u)
    u.update(tenant='',due=0,arrears=0)
    settlements.notify(w,p,reason)
    w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
    del rows[p.id]


def tick(w,minutes):
    state=getattr(w,'living_state',{})
    if KEY not in state or type(minutes) is not int or minutes<=0:
        return
    try:rows=_rows(w)
    except (ValueError,TypeError):return  # fail closed; ordinary rent sees prepaid guard
    present=getattr(w,'_earned_lodging_presence',None)
    for ident,r in tuple(rows.items()):
        if r['phase']!='active':continue
        p=w.entities.get(ident)
        u=_units(w).get(r['unit'])
        if (not p or not p.is_player or not p.alive or not u or u.get('tenant')!=ident
                or present is None or not present(ident)
                or geology_impacts.room_unusable(w,u['room'])):
            continue
        r['remaining']=max(0,r['remaining']-minutes)
        if r['remaining']:continue
        finish(w,p,u,'Your prepaid sponsored week ended. No new charge was made; belongings were returned to you.')
