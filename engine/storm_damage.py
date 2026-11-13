"""Explicit weather infrastructure targets, using the shared hazard repair state.

No actor damage, topology edits, crop deletion, or retroactive offline events.
"""
from copy import deepcopy
from collections import deque
from engine import geology_impacts as impacts

MAX_TARGETS = 8
KINDS = ('structures', 'routes', 'resources')


def validate(data, region):
    cfg=region.get('damage')
    if cfg is None:return []
    where='weather region '+str(region.get('id'))+' damage'
    if not isinstance(cfg,dict):return [where+': must be an object']
    errors=[]
    if set(cfg)-set(KINDS)-{'enabled','chance','max_targets','recovery_minutes'}:errors.append(where+': unknown fields')
    if type(cfg.get('enabled',False)) is not bool:errors.append(where+': enabled must be boolean')
    if not impacts._number(cfg.get('chance',.1),0,.25):errors.append(where+': chance must be 0 to 0.25')
    if type(cfg.get('max_targets',2)) is not int or not 1<=cfg.get('max_targets',2)<=4:errors.append(where+': max_targets must be 1 to 4')
    if type(cfg.get('recovery_minutes',120)) is not int or not 30<=cfg.get('recovery_minutes',120)<=240:errors.append(where+': recovery_minutes must be 30 to 240')
    if any(not isinstance(cfg.get(kind,[]),list) or len(cfg.get(kind,[]))>MAX_TARGETS for kind in KINDS):return errors+[where+': targets must be lists of at most eight entries']
    plan={kind:cfg.get(kind,[]) for kind in KINDS}
    plan['recovery_minutes']=cfg.get('recovery_minutes',120)
    errors+=impacts.validate_plan(data,plan,region.get('rooms',[]),where)
    if sum(len(v) for v in plan.values() if isinstance(v,list))>MAX_TARGETS:errors.append(where+': at most eight explicit targets')
    shelters={s for s in region.get('shelters',[]) if isinstance(s,str)} if isinstance(region.get('shelters',[]),list) else set();buildings={b['id']:b for b in data.get('building',[]) if isinstance(b,dict) and 'id' in b}
    for row in cfg.get('structures',[]) if isinstance(cfg.get('structures',[]),list) else []:
        if isinstance(row,dict) and ((isinstance(row.get('room'),str) and row.get('room') in shelters) or (isinstance(row.get('building'),str) and shelters.intersection(buildings.get(row.get('building'),{}).get('rooms',[]) if isinstance(buildings.get(row.get('building'),{}).get('rooms',[]),list) else []))):errors.append(where+': public refuges cannot be damage targets')
    for row in cfg.get('routes',[]) if isinstance(cfg.get('routes',[]),list) else []:
        if isinstance(row,dict) and ((isinstance(row.get('source'),str) and row.get('source') in shelters) or (isinstance(row.get('destination'),str) and row.get('destination') in shelters)):errors.append(where+': refuge entrances cannot be obstructed')
    return errors


def public_detour(world,source,destination,records):
    """Conservative public route proof; no gated/private/boat/child-only shortcut."""
    edges={(r['target']['source'],r['target']['direction'],r['target']['destination']) for r in records if r['kind']=='routes'}
    details=getattr(world,'room_details',{})
    queue=deque([(source,0)]);seen={source}
    while queue and len(seen)<=128:
        here,depth=queue.popleft()
        if here==destination:return True
        if depth>=12:continue
        row=details.get(here,{})
        for di,dest in world.rooms[here].exits.items():
            target=details.get(dest,{})
            if dest not in world.rooms or dest in seen or (here,di,dest) in edges:continue
            if row.get('gates',{}).get(di) or target.get('requires_boat') or target.get('property_plot') or target.get('land_uses'):continue
            if target.get('group') not in (None,'',details.get(source,{}).get('group')) or target.get('faction') or target.get('required_quest') or target.get('requires_quest'):continue
            if impacts.room_unusable(world,dest):continue
            # Indoor alternatives may carry hours/permission rules; do not infer access.
            from engine.regional_weather import indoor
            if indoor(target):continue
            seen.add(dest);queue.append((dest,depth+1))
    return False


def advance(world, config):
    cfg,regions,_=config
    now=impacts._now(world)
    if now is None or (getattr(world,'realtime',False) and not getattr(world,'tick_authorized',False)):return
    saved=getattr(world,'living_state',{}).get('regional_weather',{})
    for ident,region in regions.items():
        enabled=region.get('damage',{})
        if not isinstance(enabled,dict) or enabled.get('enabled') is not True:continue
        row=saved.get('regions',{}).get(ident,{})
        if not isinstance(row,dict):continue
        front=row.get('front',{})
        from engine.regional_weather import _valid_front
        if (not _valid_front(front) or not front['id'] or len(front['id'])>128
                or front['region']!=ident or front['serial']!=row.get('serial')):continue
        if front.get('weather') not in ('severe thunderstorm','tornado') or not front.get('warning_until',now+1)<=now<front.get('active_until',0):continue
        damage=front.get('damage_plan')
        if not isinstance(damage,dict) or damage.get('enabled') is not True:continue
        if row.get('damage_front_id')==front.get('id'):continue
        # Never retrofit damage onto a long-elapsed front after load or config enable.
        if now-front['warning_until']>60:continue
        data=impacts.world_data(world,set(region.get('rooms',[]))|{r.get('destination') for r in (damage.get('routes',[]) if isinstance(damage.get('routes',[]),list) else []) if isinstance(r,dict) and isinstance(r.get('destination'),str)})
        if validate(data,dict(region,damage=damage)):continue
        row['damage_front_id']=front.get('id')
        severity=max(0,min(1,front.get('intensity',0)))
        targets=[(kind,deepcopy(target)) for kind in KINDS for target in damage.get(kind,[])]
        for kind,target in targets:
            if kind=='routes':target['direction']=impacts.direction(target['direction'])
        # Fixed deterministic random priority avoids permanently favoring first authored row.
        targets.sort(key=lambda pair:impacts._roll(cfg['seed'],front['id'],impacts._key(*pair),'storm-order'))
        applied=0
        for kind,target in targets:
            if applied>=damage.get('max_targets',2):break
            # A tornado multiplier only applies within its explicitly authored footprint.
            rooms=([target['source']] if kind=='routes' else [target['room']] if 'room' in target else world.buildings[target['building']]['rooms'])
            local_severity=severity if front['weather']!='tornado' or any(r in front.get('tornado_rooms',[]) for r in rooms) else min(.75,severity)
            chance=damage.get('chance',.1)*local_severity**2
            if impacts._roll(cfg['seed'],front['id'],impacts._key(kind,target),'storm-damage')>=chance:continue
            applied+=bool(impacts.apply_weather_damage(world,kind,target,front['id'],local_severity,damage.get('recovery_minutes',120),public_detour))
