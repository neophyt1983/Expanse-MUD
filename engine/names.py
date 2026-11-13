"""Persistent personal names from creator-authored faction and gender pools."""
from hashlib import sha256
from copy import deepcopy
import re

FIELDS=('male','female','neutral','family')
ROLE=re.compile(r'\b(guard|officer|foreworker|worker|citizen|resident|teacher|merchant|trader|adventurer|courier|bandit|scout|child|keeper|boatwright|student|scholar|healer|caravaner|patrol|publican|catcher|blacksmith|smith|farmer|soldier|captain|sailor|miner|baker|tailor|priest|priestess|ranger|sentry|cook|chef|alchemist|apprentice|laborer|labourer|fisher|fisherman|hunter|noble|king|queen)\b',re.I)

def generic_label(name):
    name=(name or '').strip()
    return bool(ROLE.search(name) and (any(c.isdigit() for c in name) or ROLE.fullmatch(name)))

def personal_candidate(definition,name):
    return definition.get('social_profile',{}).get('sentient') is not False and (generic_label(name) or name in definition.get('legacy_names',[]))

def pick(pool,gender,seed,used):
    category='male' if gender=='male' else 'female' if gender=='female' else 'neutral'
    given=pool.get(category) or pool.get('neutral') or [];family=pool.get('family',[])
    start=int(sha256(seed.encode()).hexdigest(),16)
    total=len(given)*len(family)
    for i in range(total):
        index=(start+i)%total;first=given[index%len(given)];last=family[index//len(given)]
        if first+' '+last not in used:return first,last
    # A larger population gets a second personal name, never a numeric suffix.
    for middle in pool.get('neutral',[]):
        for i in range(total):
            index=(start+i)%total;first=given[index%len(given)]+' '+middle;last=family[index//len(given)]
            if first+' '+last not in used:return first,last
    raise ValueError('Expand this faction’s name pool; all personal-name combinations are in use.')

def assign(w,e,force=False):
    if e.is_player:return
    definition=w.npcs.get(e.source_def,{})
    generic=personal_candidate(definition,e.name)
    if definition.get('name_mode')!='faction' and not force and not generic:return
    if e.progress.get('personal_name_assigned') and not generic:return
    if generic and not definition.get('title'):
        definition['title']=re.sub(r'[\d#()]+','',e.name).strip()
    from engine import living
    pool=w.groups.get(e.group_id,{}).get('name_pool') or w.metadata.get("name_pool",{})
    if not pool:return
    used={x.name for x in w.entities.values() if x.id!=e.id}
    used.update(x['name'] for x in living.state(w).get('companion_reserve',{}).values())
    if not e.sex:e.sex=definition.get('sex') or definition.get('gender')
    gender=e.sex
    e.first_name,e.last_name=pick(pool,gender,e.id,used)
    e.name=e.first_name+' '+e.last_name
    e.progress['personal_name_assigned']=True

def migrate_saved(w,e):
    definition=w.npcs.get(e.source_def,{})
    # Preserve custom saved names and names already assigned to an individual.
    if e.is_player:return
    if personal_candidate(definition,e.name) or e.name in definition.get('legacy_names',[]) or e.name==definition.get('name'):
        assign(w,e)
        from engine import living
        state=living.state(w).get('relationships',{})
        for row in state.get('bonds',{}).values():
            if e.id in row['participants']:row['names'][row['participants'].index(e.id)]=e.name
        for row in state.get('proposals',{}).values():
            if row['from']==e.id:row['sender']=e.name
        for row in state.get('pregnancies',{}).values():
            if e.id in row['parents']:row['names'][row['parents'].index(e.id)]=e.name

def validate(data):
    issues=[]
    for g in data.get('group',[]):
        pool=g.get('name_pool')
        if pool is None:continue
        if not isinstance(pool,dict):issues.append(g['id']+': name_pool must be an object');continue
        for field in FIELDS:
            values=pool.get(field)
            if not isinstance(values,list) or not values or any(not isinstance(v,str) or not v.strip() or any(c.isdigit() for c in v) for v in values):issues.append(g['id']+': invalid '+field+' name list')
    for n in data.get('npc',[]):
        if n.get('name_mode','manual') not in ('manual','faction'):issues.append(n['id']+': invalid name mode')
    return issues
