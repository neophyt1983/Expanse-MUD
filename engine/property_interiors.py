"""Runtime unit interiors; economic parcels and saved unit identities remain authoritative."""
from hashlib import sha256
from copy import deepcopy
KINDS={'house','rental','business'}

def room_id(uid):return 'property_unit_'+sha256(uid.encode('utf-8')).hexdigest()[:24]

def _registry(w):return (getattr(w,'living_state',{}) or {}).get('settlements',{}).get('units',{})

def is_interior(w,u,rid):
    row=getattr(w,'room_details',{}).get(rid,{})
    return (rid==room_id(u['id']) and rid in getattr(w,'_property_generated_rooms',set())
            and row.get('property_unit_id')==u['id'] and row.get('property_parcel_id')==u['room'])

def occupancy(w,u):
    """Tenure is not a guess that an unowned household is empty."""
    if u.get('tenant'):return 'tenanted'
    if u.get('owner'):return 'owned'
    if u.get('household_id'):return 'household'
    from engine import earned_lodging
    if earned_lodging.reserved(w,u):return 'reserved sponsored lodging'
    if u['room'] in getattr(w,'_property_household_parcels',set()) or any(h.get('home_room')==u['room'] for h in (getattr(w,'living_state',{}) or {}).get('population',{}).get('households',{}).values()):return 'household assignment unknown'
    return 'vacant'

def blocked(w,actor,origin,direction,target):
    detail=getattr(w,'room_details',{}).get(target,{})
    uid=detail.get('property_unit_id')
    if not uid or target not in getattr(w,'_property_generated_rooms',set()):return ''
    u=_registry(w).get(uid)
    if not u or u.get('kind') not in KINDS:return 'This property is no longer available.'
    parcel=(getattr(w,'living_state',{}) or {}).get('settlements',{}).get('parcels',{}).get(u['room'],{})
    if parcel.get('kind',u['kind'])!=u['kind']:return 'This property has changed use and is unavailable.'
    from engine import geology_impacts
    if geology_impacts.room_unusable(w,u['room']):return 'This property is temporarily closed for recovery.'
    if getattr(w,'room_details',{}).get(u['room'],{}).get('property_plot',{}).get('interiors') is False:return 'Individual interiors are disabled for this parcel.'
    if origin!=u['room'] and origin!=detail.get('unit_front'):return 'Enter this property from its public parcel.'
    if target!=room_id(uid):return 'This property entrance is unavailable.'
    controller=u.get('tenant') or u.get('owner')
    if controller:return '' if actor is not None and actor.id==controller else 'This is private property: current tenant or owner only.'
    hid=u.get('household_id')
    if hid:
        household=(getattr(w,'living_state',{}) or {}).get('population',{}).get('households',{}).get(hid,{})
        return '' if actor is not None and actor.id in household.get('members',[]) else 'This is a private household.'
    occupied=occupancy(w,u)
    if occupied=='reserved sponsored lodging':return 'This lodging is reserved for its confirmed starter contract.'
    if occupied!='vacant':return 'This parcel is already used as a household home; no vacant unit has been confirmed.'
    return ''

def ensure(w,units=None):
    """Create only missing derived rooms. Never overwrite authored rooms/exits."""
    from engine.core import Room
    full=units is None
    units=list((units if units is not None else _registry(w).values()))
    if not full and all(room_id(u['id']) in getattr(w,'_property_generated_rooms',set()) and w.room_details.get(room_id(u['id']),{}).get('property_unit_kind')==u.get('kind') for u in units):return getattr(w,'_property_interior_diagnostics',{})
    living=getattr(w,'living_state',{}) or {}
    households=list((getattr(w,'population_manifest',{}) or {}).get('households',{}).values())+list(living.get('population',{}).get('households',{}).values())
    w._property_household_parcels={h.get('home_room') for h in households if h.get('home_room')}
    generated=getattr(w,'_property_generated_rooms',set());w._property_generated_rooms=generated
    diagnostics=getattr(w,'_property_interior_diagnostics',{});w._property_interior_diagnostics=diagnostics
    byparcel=getattr(w,'_property_rooms_by_parcel',{});w._property_rooms_by_parcel=byparcel
    changed=False
    referenced={dest for r in w.rooms.values() for dest in r.exits.values()}
    units.sort(key=lambda u:('footprint_tile' not in u,u.get('room',''),u.get('index',0)))
    for u in units:
        uid=u.get('id');parcel=u.get('room');index=u.get('index')
        if u.get('kind') not in KINDS or not isinstance(uid,str) or type(index)is not int or index<0 or parcel not in w.rooms:continue
        if w.room_details.get(parcel,{}).get('property_plot',{}).get('interiors') is False and not u.get('interior_materialized'):
            diagnostics[uid]='Creator disabled individual interiors for this parcel';continue
        rid=room_id(uid);door='unit '+str(index+1);out=w.rooms[parcel]
        if rid in generated:
            u['interior_materialized']=True
            row=w.room_details.get(rid,{})
            if row.get('property_unit_kind')!=u['kind']:
                row['property_unit_kind']=u['kind']
                row['facilities']=['residential'] if u['kind']!='business' else list(w.room_details.get(parcel,{}).get('land_uses',{}).get(u['kind'],{}).get('facilities',w.room_details.get(parcel,{}).get('facilities',[])))
                row['description']='An enclosed '+('business workspace' if u['kind']=='business' else 'dwelling')+' with a door back to the public parcel.'
                w.rooms[rid].description=row['description'];changed=True
            continue
        if rid in w.rooms or rid in w.room_details or rid in w.buildings or (door in out.exits and out.exits[door]!=rid):
            diagnostics[uid]='Creator room, building or doorway collision; interior not generated';continue
        # An authored dangling reference is not our permission to repair/replace it.
        if rid in referenced:
            diagnostics[uid]='Existing authored reference to reserved interior';continue
        name=out.name+' #'+str(index+1)
        description=('A small business room with a clear working area and shelves. The door leads back to the public parcel.' if u['kind']=='business' else 'A modest dwelling with a sleeping space, a table and room for personal belongings. The door leads back to the public parcel.')
        climate=deepcopy(w.room_details.get(parcel,{}).get('climate',{}));climate['sheltered']=True
        row=dict(id=rid,name=name,description=description,exits={'out':parcel},items=[],environment='interior',climate=climate,group=u.get('group'),property_unit_id=uid,property_unit_kind=u['kind'],property_parcel_id=parcel,facilities=['residential'] if u['kind']!='business' else list(w.room_details.get(parcel,{}).get('land_uses',{}).get(u['kind'],{}).get('facilities',w.room_details.get(parcel,{}).get('facilities',[]))),location=rid)
        coords={key:w.room_details[parcel][key] for key in ('map_x','map_y','map_z') if key in w.room_details[parcel]}
        from engine.streets import unit_front
        front=unit_front(w,u,rid,coords)
        row.update(coords,unit_front=front,exits={'out':front})
        anchor=w.room_details[parcel]
        if all(type(anchor.get(k)) in (int,float) for k in ('world_x','world_y')):
            from math import isfinite
            if all(isfinite(anchor[k]) for k in ('world_x','world_y')):
                row.update({k:anchor[k] for k in ('world_x','world_y')})
                if isinstance(anchor.get('world_region'),str):row['world_region']=anchor['world_region']
        w.room_details[rid]=row;w.add_room(Room(rid,name,description,{'out':front},group=u.get('group'),**coords))
        w.buildings[rid]=dict(id=rid,name=name,rooms=[rid],location=rid,property_unit_id=uid)
        out.exits[door]=rid
        # Runtime copy only: preserve Creator definitions on disk.
        w.room_details[parcel]['exits']=dict(out.exits)
        u['interior_materialized']=True
        generated.add(rid);byparcel.setdefault(parcel,set()).add(rid);changed=True
    if changed:
        for key in ('_compiled_map','_livelihood_locations','_ground_lots'):w.__dict__.pop(key,None)
    if full:
        for actor in w.entities.values():reconcile_home(w,actor)
    return diagnostics

def enter(ctx,u):
    w,p=ctx.world,ctx.player
    if p.location!=u['room']:raise ValueError('Visit the public parcel before entering this property.')
    ensure(w,[u]);rid=room_id(u['id'])
    if rid not in getattr(w,'_property_generated_rooms',set()):raise ValueError('This property has no available interior; ask the host to inspect its entrance.')
    reason=blocked(w,p,p.location,'unit '+str(u['index']+1),rid)
    if reason:raise ValueError(reason)
    from engine.commands import _cmd_go
    return _cmd_go(ctx,'unit '+str(u['index']+1))


def public_row(w,p,u):
    """Current doorway information, never remote ownership/occupancy discovery."""
    rid=room_id(u['id']);inside=is_interior(w,u,p.location);here=p.location==u['room']
    if not (here or inside):return {}
    available=is_interior(w,u,rid) and u['id'] in _registry(w)
    reason=blocked(w,p,u['room'],None,rid) if available else 'No individual interior is available for this property.'
    return dict(interior_available=available,inside=inside,entry_available=here and available and not reason,
                entry_reason=reason,occupancy={'household assignment unknown':'availability unconfirmed','household':'occupied household'}.get(occupancy(w,u),occupancy(w,u)))

def reconcile_home(w,p):
    # Saved residents may still be sleeping at an old street address. A real
    # lease, owned home or separate authored household always takes precedence.
    definition=w.npcs.get(p.source_def,{}) if not p.is_player else {}
    old=definition.get('lodging_previous_room');home=definition.get('home_room')
    if old and home in w.rooms and not p.progress.get('home_property') and not p.progress.get('population'):
        if p.progress.get('home_room')==old:p.progress['home_room']=home
        if p.location==old and str(getattr(p,'activity','')).startswith('sleep') and p.progress.get('home_room',home)==home:
            p.activity='returning home'
    uid=p.progress.get('home_property');u=_registry(w).get(uid)
    if not u or u.get('kind') not in ('house','rental'):return
    rid=room_id(uid)
    # Only migrate the prior economic anchor for this same authoritative home.
    if (u.get('tenant') or u.get('owner'))==p.id and p.progress.get('home_room')==u['room'] and rid in getattr(w,'_property_generated_rooms',set()):
        p.progress['home_room']=rid

def home_shelter(w,p):
    uid=getattr(w,'room_details',{}).get(p.location,{}).get('property_unit_id');u=_registry(w).get(uid)
    if not u or u.get('kind') not in ('house','rental') or not is_interior(w,u,p.location):return False
    return (u.get('tenant') or u.get('owner'))==p.id and not blocked(w,p,u['room'],None,p.location)


def parcel_in_use(w,parcel):
    # Preserve rooms holding actors or real floor possessions during civic reuse.
    return any((w.rooms[rid].entities or w.rooms[rid].items)
               for rid in getattr(w,'_property_rooms_by_parcel',{}).get(parcel,())
               if rid in w.rooms)


def acquisition_problem(w,u, *, ignore_opening_hold=False):
    from engine import earned_lodging
    if not ignore_opening_hold and earned_lodging.reserved(w,u):
        return 'This lodging is reserved and cannot be bought or rented.'
    # Tenure records do not authorize displacement of an independently housed family.
    household_here=u.get('household_id') or u['room'] in getattr(w,'_property_household_parcels',set()) or any(h.get('home_room')==u['room'] for h in (getattr(w,'living_state',{}) or {}).get('population',{}).get('households',{}).values())
    return 'This parcel already houses a household; no vacant unit is confirmed for acquisition.' if household_here else ''

def restored_location(w,actor,rid):
    """Resume never grants stale access to a new household's private room."""
    uid=getattr(w,'room_details',{}).get(rid,{}).get('property_unit_id')
    u=_registry(w).get(uid)
    if not u or not is_interior(w,u,rid):return rid
    controller=u.get('tenant') or u.get('owner')
    if controller:
        allowed=actor.id==controller
    elif u.get('household_id'):
        household=(getattr(w,'living_state',{}) or {}).get('population',{}).get('households',{}).get(u['household_id'],{})
        allowed=actor.id in household.get('members',[])
    else:allowed=occupancy(w,u)=='vacant'
    # Opt-out by itself is not eviction of a previously saved occupant.
    return rid if allowed else u['room']
