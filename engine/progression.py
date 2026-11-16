"""Server-authoritative, solo-friendly advancement from meaningful accomplishments.

A ledger prevents duplicate milestones; bounded practice keeps professions viable.
Stored level growth is additive: old saves and creator base values are retained.
"""
DEFAULTS = dict(enabled=True, level_cap=20, threshold_step=100,
                discovery_xp=2, quest_xp=50, social_xp=20,
                craft_xp=12, gather_xp=8, combat_xp=20, social_partners=5,
                repeat_percent=50, repeat_floor_percent=25,
                repeat_cooldown_minutes=5, repeat_daily_xp=200)


def config(w):
    raw=w.metadata.get('progression', {})
    result=dict(DEFAULTS)
    result['enabled']=bool(w.metadata.get('living_world',False))
    if isinstance(raw,dict):
        for key,default in DEFAULTS.items():
            value=raw.get(key,result[key])
            if key=='enabled':result[key]=value if type(value) is bool else result[key]
            elif type(value) is int and 0<=value<=10000:result[key]=value
    result['level_cap']=max(1,min(100,result['level_cap']))
    result['threshold_step']=max(1,result['threshold_step'])
    result['social_partners']=min(20,result['social_partners'])
    return result


def threshold(level, step):return step*level*(level-1)//2


def state(p):
    return p.progress.setdefault('advancement_v1',dict(xp=0,level=1,earned={},sources={},recent=[]))


def view(w,p):
    cfg=config(w)
    if not cfg['enabled']:return None
    row=p.progress.get('advancement_v1',{})
    level=row.get('level',1);xp=row.get('xp',0)
    return dict(level=level,xp=xp,next_xp=threshold(level+1,cfg['threshold_step']) if level<cfg['level_cap'] else None,
                level_cap=cfg['level_cap'],recent=row.get('recent',[])[:5],
                sources=dict(row.get('sources',{})),practice=practice_view(w,p))


def summary(w,p):
    row=view(w,p)
    if row is None:return ''
    return f"Level {row['level']} · XP {row['xp']}"+(f" / {row['next_xp']}" if row['next_xp'] else ' · Level cap reached')


def growth(w,p):
    primary=w.classes.get(p.char_class,{}).get('primary_stat')
    defaults=dict(hp=3 if primary=='str' else 2,mana=3 if primary=='int' else 1,
                  attack_every=4,defense_every=5)
    overrides=w.classes.get(p.char_class,{}).get('level_growth',{})
    if isinstance(overrides,dict):
        for key in defaults:
            if type(overrides.get(key)) is int and 0<=overrides[key]<=20:defaults[key]=overrides[key]
    return defaults


def practice_view(w,p):
    from engine import living,worldtime
    row=p.progress.get('advancement_v1',{}).get('practice',{})
    day=int(living.state(w)['minute'])//worldtime.MINUTES_PER_DAY
    used=row.get('used',0) if day<=row.get('day',day) else 0
    return dict(used=used,limit=config(w)['repeat_daily_xp'],cooldown_minutes=config(w)['repeat_cooldown_minutes'])


def award(w,p,kind,key,amount=None,repeat=None,*,round_up=False):
    cfg=config(w)
    if (not p.is_player and kind!='combat') or not p.alive or not cfg['enabled'] or p.progress.get('zoo_exhibit'):return ''
    from engine import living,worldtime
    row=state(p);ident=kind+':'+str(key)
    amount=cfg.get(kind+'_xp',0) if amount is None else amount
    if type(amount) is not int or amount<=0:return ''
    amount=min(amount,10000)
    now=int(living.state(w)['minute']);day=now//worldtime.MINUTES_PER_DAY
    repeated=ident in row['earned']
    last=row.setdefault('practice_last',{})
    if repeat is None:repeat=kind in ('craft','gather','combat')
    if row['level']>=cfg['level_cap']:
        if not repeated:
            row['earned'][ident]=True
            if repeat:last[ident]=now
            if p.is_player:
                if not hasattr(w,'dirty_players'):w.dirty_players=set()
                w.dirty_players.add(p.id)
        return ''
    if repeated:
        if not repeat or not cfg['repeat_daily_xp'] or not cfg['repeat_percent']:return ''
        # Old saved milestone records receive no retrospective credit. Their
        # first new real success is eligible; backdated clocks cannot reset it.
        if now-last.get(ident,now-cfg['repeat_cooldown_minutes'])<cfg['repeat_cooldown_minutes']:return ''
        practice=row.setdefault('practice',dict(day=day,used=0,counts={}))
        if day>practice['day']:practice.update(day=day,used=0,counts={})
        if practice['used']>=cfg['repeat_daily_xp']:return 'Practice XP budget used for this day; it renews tomorrow. Your work still succeeds.'
        count=practice['counts'].get(ident,0)
        percent=max(min(cfg['repeat_floor_percent'],cfg['repeat_percent']),cfg['repeat_percent']*2//(count+2))
        scaled=(amount*percent+99)//100 if round_up else amount*percent//100
        amount=min(max(1,scaled),cfg['repeat_daily_xp']-practice['used'])
        practice['used']+=amount;practice['counts'][ident]=count+1
    row['earned'][ident]=True
    if repeat:last[ident]=now
    if p.is_player:
        if not hasattr(w,'dirty_players'):w.dirty_players=set()
        w.dirty_players.add(p.id)
    if row['level']>=cfg['level_cap']:return ''
    row['xp']+=amount;row['sources'][kind]=row['sources'].get(kind,0)+amount
    old=row['level'];g=growth(w,p);pr=living.progress(p)
    before=(p.max_hp,pr['max_mana'],p.attack,p.defense)
    while row['level']<cfg['level_cap'] and row['xp']>=threshold(row['level']+1,cfg['threshold_step']):
        row['level']+=1;n=row['level']
        p.max_hp+=g['hp'];pr['max_mana']+=g['mana']
        if g['attack_every'] and (n-1)%g['attack_every']==0:p.attack+=1
        if g['defense_every'] and (n-1)%g['defense_every']==0:p.defense+=1
    message=f'+{amount} XP ({kind}'+('; practice' if repeated else '')+').'
    if row['level']>old:
        after=(p.max_hp,pr['max_mana'],p.attack,p.defense)
        gains=[f'+{b-a} {label}' for a,b,label in zip(before,after,('maximum health','maximum mana','attack','defense')) if b>a]
        message+=f" Level {row['level']} reached! "+(', '.join(gains)+'. Rest to recover increased capacity.' if gains else 'Your creator-defined growth rules are unchanged.')
    row['recent']=[message]+row['recent'][:4]
    return message


def quest(w,p,q):
    # Preserve old lifetime-objective completion semantics, but don't mint
    # practice for repeatedly handing in the same already-counted history.
    consumed=any(type(n) is int and n>0 for n in q.get('required_items',{}).values())
    fresh_objectives=any(q.get(k) for k in ('visit_rooms','talk_to','witnesses')) or any(type(n) is int and n>0 for k in ('kills','actions') for n in q.get(k,{}).values())
    fresh=q.get('progress_scope')=='accepted' and fresh_objectives
    repeat=bool(q.get('repeatable') and (consumed or fresh))
    from engine.quest_chains import definition
    return award(w,p,'quest',q['id'],q.get('reward_xp',config(w)['quest_xp']),repeat=repeat,
                 round_up=bool(definition(q)))


def social(w,p,q,npc):
    if not p.is_player or not p.alive or not config(w)['enabled']:return ''
    # Relationship lessons apply to a few distinct people, not thousands of
    # interchangeable greeting quests. Ordinary relationships remain unrestricted.
    row=state(p);prefix='social:'+q['id']+'|'
    if sum(k.startswith(prefix) for k in row['earned'])>=config(w)['social_partners']:return ''
    return award(w,p,'social',q['id']+'|'+npc.id,q.get('reward_xp',config(w)['social_xp']))


def discovery(w,p,rid):
    if rid in p.explored_rooms:return ''
    return award(w,p,'discovery',rid)


def combat(w,p,target):
    from engine import loot_tables
    definition=w.npcs.get(target.source_def,{})
    if (target.is_player or target.progress.get('companion_owner') or target.progress.get('zoo_exhibit')
            or definition.get('zoo_exhibit')
            or not (definition.get('aggressive') or loot_tables.configured(definition))):return ''
    return award(w,p,'combat',target.source_def,definition.get('reward_xp',config(w)['combat_xp']))


def validate(data):
    issues=[]
    for kind in ('quest','class'):
        for row in data.get(kind,[]):
            if 'reward_xp' in row and (type(row['reward_xp']) is not int or not 0<=row['reward_xp']<=10000):issues.append(row['id']+': reward_xp must be an integer from 0 to 10000')
            if 'level_growth' in row:
                g=row['level_growth']
                if not isinstance(g,dict) or any(k not in ('hp','mana','attack_every','defense_every') or type(v) is not int or not 0<=v<=20 for k,v in g.items()):issues.append(row['id']+': invalid level_growth')
    return issues


def validate_config(raw):
    if not isinstance(raw,dict):return ['progression must be an object']
    issues=[]
    for key,value in raw.items():
        if key not in DEFAULTS:issues.append('Unknown progression setting: '+str(key));continue
        if key=='enabled':
            if type(value) is not bool:issues.append('progression enabled must be true or false')
        elif type(value) is not int or not 0<=value<=10000:issues.append('progression '+key+' must be an integer from 0 to 10000')
        elif key=='level_cap' and not 1<=value<=100:issues.append('progression level_cap must be 1–100')
        elif key=='threshold_step' and value<1:issues.append('progression threshold_step must be positive')
        elif key=='social_partners' and value>20:issues.append('progression social_partners must be 0–20')
        elif key in ('repeat_percent','repeat_floor_percent') and value>100:issues.append('progression '+key+' must be 0–100')
    percent=raw.get('repeat_percent',DEFAULTS['repeat_percent']);floor=raw.get('repeat_floor_percent',DEFAULTS['repeat_floor_percent'])
    if type(percent) is int and type(floor) is int and percent>0 and floor>percent:issues.append('repeat_floor_percent must not exceed repeat_percent')
    return issues
