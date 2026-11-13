"""Opt-in bounded goodwill evolution; not war, troop or conquest simulation.

Saved scores project into in-memory group relations AND diplomacy bases, so the
existing combat/trade/dialogue policies see one effective value. Content files
are never rewritten. Locks and bounds remain creator-owned.
"""
from copy import deepcopy
from hashlib import sha256
import json
from engine.worldtime import MINUTES_PER_DAY, MINUTES_PER_YEAR

KEY='dynamic_diplomacy'


def validate(config,groups):
    if not isinstance(config,dict):raise ValueError('Dynamic diplomacy must be an object')
    if config.get('enabled',False) is not True:return
    seed=config.get('seed',0);interval=config.get('interval_minutes',MINUTES_PER_YEAR)
    if type(seed) is not int or not 0<=seed<2**63:raise ValueError('Invalid diplomacy seed')
    if type(interval) is not int or not MINUTES_PER_DAY<=interval<=10*MINUTES_PER_YEAR:raise ValueError('Diplomacy interval must be one day to ten local years')
    pairs=config.get('pairs',[])
    if not isinstance(pairs,list) or len(pairs)>64:raise ValueError('At most 64 diplomatic pairs')
    seen=set()
    for p in pairs:
        if not isinstance(p,dict) or p.get('a') not in groups or p.get('b') not in groups or p['a']==p['b']:raise ValueError('Invalid diplomatic parties')
        key=tuple(sorted((p['a'],p['b'])))
        if key in seen:raise ValueError('Duplicate diplomatic pair')
        seen.add(key)
        from engine import diplomacy
        for a,b in ((p['a'],p['b']),(p['b'],p['a'])):
            lo,hi,_=diplomacy.bounds(groups[a],a,b)
            if type(lo) is not int or type(hi) is not int or not 0<=lo<=hi<=100:
                raise ValueError('Dynamic diplomacy requires whole-number authored bounds within 0..100')
        for k,default in [('minimum',25),('maximum',100),('initial_score',50),('change',3)]:
            v=p.get(k,default)
            if type(v) is not int or not 0<=v<=100:raise ValueError('Invalid diplomatic '+k)
        if not p.get('minimum',25)<=p.get('initial_score',50)<=p.get('maximum',100):raise ValueError('Diplomacy initial score outside bounds')
        if p.get('change',3)>10:raise ValueError('Maximum goodwill change is 10 per turn')
        if type(p.get('locked',False)) is not bool:raise ValueError('Diplomacy lock must be boolean')


def _state(world):
    from engine import living
    s=living.state(world).setdefault(KEY,{'version':1,'pairs':{},'events':[]})
    if not isinstance(s,dict) or s.get('version')!=1 or not isinstance(s.get('pairs'),dict) or not isinstance(s.get('events'),list):raise ValueError('Invalid saved dynamic diplomacy')
    if len(s['pairs'])>64 or len(s['events'])>32:raise ValueError('Saved diplomacy exceeds bounds')
    for value in s['pairs'].values():
        if not isinstance(value,dict) or type(value.get('score')) is not int or not 0<=value['score']<=100 or type(value.get('turn')) is not int or value['turn']<0:raise ValueError('Invalid saved diplomatic score/turn')
    return s


def ensure(world,advance=False):
    cfg=world.metadata.get(KEY,{})
    baseline=getattr(world,'_diplomacy_authored',None)
    if baseline is None:
        if cfg.get('enabled') is not True:return
        baseline={k:deepcopy(v) for k,v in world.groups.items()};world._diplomacy_authored=baseline
    # Restore only fields projected by this subsystem; retain unrelated edits.
    for gid in getattr(world,'_diplomacy_projected',set()):
        for field in ('relations','diplomacy'):
            if field in baseline[gid]:world.groups[gid][field]=deepcopy(baseline[gid][field])
            else:world.groups[gid].pop(field,None)
    world._diplomacy_projected=set()
    if cfg.get('enabled') is not True:return
    validate(cfg,baseline)
    state=_state(world)
    from engine import living,diplomacy
    now=int(living.state(world)['minute']);interval=cfg.get('interval_minutes',MINUTES_PER_YEAR);current=now//interval
    configured=set()
    for rule in cfg.get('pairs',[]):
        a,b=rule['a'],rule['b'];key=json.dumps(sorted((a,b)),separators=(',',':'));configured.add(key)
        if rule.get('locked'):
            if key in state['pairs']:state['pairs'][key]['turn']=current
            continue
        low=rule.get('minimum',25);high=rule.get('maximum',100)
        for source,target in ((a,b),(b,a)):
            l,h,_=diplomacy.bounds(baseline[source],source,target);low=max(low,l);high=min(high,h)
        if low>high:raise ValueError('Conflicting creator diplomacy bounds')
        p=state['pairs'].setdefault(key,{'score':rule.get('initial_score',50),'turn':current})
        p['score']=max(low,min(high,p['score']))
        # Fast-forward old intervals without unbounded catch-up. Up to 64 turns
        # are explicitly simulated; omitted count is recorded, not invented.
        if advance and current>p['turn']:
            start=max(p['turn']+1,current-63)
            if start>p['turn']+1:state['events'].append({'kind':'catchup_limited','pair':[a,b],'omitted_turns':start-p['turn']-1,'at':now})
            for turn in range(start,current+1):
                digest=sha256(f"{cfg.get('seed',0)}:{key}:{turn}".encode()).digest()
                direction=(-1,0,1)[digest[0]%3];change=direction*rule.get('change',3)
                p['score']=max(low,min(high,p['score']+change))
                if change:state['events'].append({'kind':'dispute' if change<0 else 'cooperation','pair':[a,b],'at':turn*interval,'score':p['score']})
            p['turn']=current
        score=p['score'];relation='hostile' if score<25 else 'allied' if score>=80 else 'tolerated' if score>=55 else 'neutral'
        for source,target in ((a,b),(b,a)):
            group=world.groups[source];group.setdefault('relations',{})[target]=relation
            old=group.setdefault('diplomacy',{}).get(target,{})
            group['diplomacy'][target]={**old,'base':score}
            world._diplomacy_projected.add(source)
    state['pairs']={k:v for k,v in state['pairs'].items() if k in configured}
    state['events']=state['events'][-32:]
