"""Opt-in, deterministic resident authoring. Never rebalance or regenerate a save.

Preview is read-only. Install adds editable definitions and an immutable cohort
manifest, either to an Editor's staged content or to a rollback-safe file batch.
All demographic details beyond the cited broad benchmark are fictional choices.
"""
from collections import Counter, deque
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile

from engine import names, worldtime

VERSION = 1
HUMANLIKE_BINS = [dict(min=a, max=b, weight=p) for a,b,p in
    [(0,4,8),(5,9,8),(10,14,9),(15,17,5),(18,24,11),
     (25,44,27),(45,64,22),(65,74,6),(75,84,3),(85,99,1)]]
CAVEATS = [
    'Fine age bins, household mix, education, appearance and health are fictional design choices, not scientific quotas.',
    'UN 2024 broad world benchmark: 24.7% age 0–14, 65.1% age 15–64, 10.2% age 65+. It does not prescribe a settlement.',
    'All ages use local Expanse years (312000 minutes). Housing membership grants no property ownership.',
    'This one-time cohort does not rebalance existing residents or enable autonomous romance, reproduction or mortality.',
]
FILES = dict(room='rooms.json', npc='npcs.json', group='groups.json', race='races.json',
             species='species.json', sex='sexes.json', encounter='encounters.json', item='items.json', building='buildings.json')


class PopulationError(ValueError):
    """Invalid, stale or infeasible population plan; content is unchanged."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _read(path, default):
    if not path.exists():return deepcopy(default)
    return json.loads(path.read_text(encoding='utf-8'))


def _source(target):
    editor = hasattr(target,'data') and hasattr(target,'data_dir')
    folder = Path(target.data_dir if editor else target)
    data = deepcopy(target.data) if editor else {key:_read(folder/name,[]) for key,name in FILES.items()}
    metadata = deepcopy(getattr(target,'metadata',None)) if editor else None
    if metadata is None:metadata = _read(folder/'metadata.json',{})
    manifest = deepcopy(getattr(target,'population_manifest',None)) if editor else None
    if manifest is None:manifest = _read(folder/'population.json',{'version':VERSION,'cohorts':{},'households':{}})
    return folder,data,metadata,manifest


def largest_remainder(total, weights, rng=None):
    """Deterministic seeded tie breaks, exact requested count, no per-row rounding loss."""
    rng = rng or random.Random(0)
    scale=sum(weights)
    raw=[total*(w/scale) for w in weights]
    result=[math.floor(x) for x in raw]
    tie=list(range(len(weights)));rng.shuffle(tie);rank={v:i for i,v in enumerate(tie)}
    order=sorted(range(len(weights)),key=lambda i:(-(raw[i]-result[i]),rank[i]))
    for i in order[:total-sum(result)]:result[i]+=1
    return result


def _integer(value, low, high):return type(value) is int and low<=value<=high



def _validate_bins(bins):
    if not isinstance(bins,list) or not bins:return ['age_bins requires a nonempty list.']
    end=-1
    for row in bins:
        if not isinstance(row,dict) or not _integer(row.get('min'),0,10000) or not _integer(row.get('max'),0,10000) or row['max']<row['min'] or type(row.get('weight')) not in (int,float) or not math.isfinite(row['weight']) or row['weight']<0:
            return ['Each age bin needs bounded integer min/max and a finite nonnegative weight.']
        if row['min']<=end:return ['age_bins must be ordered and nonoverlapping.']
        end=row['max']
    total=sum(r['weight'] for r in bins)
    return [] if math.isfinite(total) and total>0 else ['Age-bin weights must have a finite positive total.']


def _validate(data,metadata,manifest,cfg):
    errors=[]
    if not isinstance(cfg,dict):return ['Population config must be an object.']
    if not metadata.get('living_world'):errors.append('Enable living_world explicitly before creating residents; no settings are enabled automatically.')
    if not isinstance(manifest,dict) or manifest.get('version')!=VERSION or not isinstance(manifest.get('cohorts'),dict) or not isinstance(manifest.get('households'),dict):
        errors.append('population.json must be a supported version-1 manifest with cohort and household objects.')
    if not isinstance(cfg.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',cfg['id']):errors.append('id must start with a lowercase letter, use lowercase letters/digits/underscores, and be at most 48 characters.')
    if not _integer(cfg.get('seed'),0,2**63-1):errors.append('seed must be an integer between 0 and 2^63-1.')
    if not _integer(cfg.get('count'),1,5000):errors.append('count must be an integer from 1 to 5000.')
    for key in ('room','npc','group','race','species','sex','encounter'):
        rows=data.get(key,[])
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in rows):
            errors.append(key+' content must be a list of objects with string IDs.');continue
        if len({r['id'] for r in rows})!=len(rows):errors.append(key+' content has duplicate IDs.')
    if errors:return errors
    rooms={r['id']:r for r in data.get('room',[])}
    races={r['id']:r for r in data.get('race',[])}
    species={r['id']:r for r in data.get('species',[])}
    groups={r['id']:r for r in data.get('group',[])}
    if cfg.get('race') not in races:errors.append('race must name an existing authored race.')
    if not isinstance(cfg.get('species'),str) or not cfg['species']:errors.append('An explicit species is required.')
    if cfg.get('group') and cfg['group'] not in groups:errors.append('group must name an existing authored faction, or be empty.')
    preset=cfg.get('preset')
    if preset=='humanlike_fictional':
        if 'age_bins' in cfg:errors.extend(_validate_bins(cfg['age_bins']))
        if cfg.get('species')!='human':errors.append('Nonhuman species require species_authored bins and life-stage thresholds; human bins are never copied silently.')
    elif preset=='species_authored':
        spec=species.get(cfg.get('species'),{})
        if not isinstance(spec.get('life_stages'),dict) or not isinstance(spec['life_stages'].get('adulthood_years'),(int,float)):
            errors.append('species_authored requires an existing species with explicitly authored life_stages.adulthood_years.')
        errors.extend(_validate_bins(cfg.get('age_bins')))
    else:errors.append('Choose preset humanlike_fictional or species_authored.')
    homes=cfg.get('homes')
    if not isinstance(homes,list) or not homes:errors.append('Explicit authored homes and capacities are required.')
    else:
        seen=set()
        for row in homes:
            if not isinstance(row,dict) or row.get('room') not in rooms or not _integer(row.get('capacity'),1,1000):
                errors.append('Each home needs an existing room and integer capacity from 1 to 1000.');continue
            if row['room'] in seen:errors.append('Home rooms cannot be repeated.')
            seen.add(row['room'])
            if not _safe_room(rooms[row['room']],cfg.get('group'),groups):errors.append('Home '+row['room']+' is unsafe or forbidden to this faction.')
    learning=cfg.get('learning','home')
    if learning not in ('home','school','community'):errors.append('learning must be home, school or community.')
    for field in ('school_rooms','community_learning_rooms','leisure_rooms'):
        rows=cfg.get(field,[])
        if not isinstance(rows,list) or any(not isinstance(r,str) or r not in rooms for r in rows):errors.append(field+' must contain existing room IDs.')
    if learning=='school' and not cfg.get('school_rooms'):errors.append('School learning requires explicitly authored school_rooms.')
    if learning=='community' and not cfg.get('community_learning_rooms'):errors.append('Community learning requires explicitly authored community_learning_rooms.')
    providers=cfg.get('learning_providers',[])
    if not isinstance(providers,list) or any(not isinstance(p,dict) or p.get('room') not in rooms or not isinstance(p.get('npc'),str) or p.get('qualified') is not True for p in providers):errors.append('learning_providers requires objects with existing room, npc ID and qualified:true.')
    jobs=cfg.get('workplaces',[])
    if not isinstance(jobs,list):errors.append('workplaces must be a list.')
    else:
        for j in jobs:
            if not isinstance(j,dict) or j.get('room') not in rooms or not isinstance(j.get('occupation'),str) or not j['occupation'].strip() or not _integer(j.get('slots'),0,5000):errors.append('Each workplace needs an existing room, occupation and integer slots from 0 to 5000.')
    if not isinstance(cfg.get('health',{}),dict):errors.append('health must be an object.')
    if cfg.get('preset')=='species_authored':
        gap=cfg.get('parent_age_gap')
        if not isinstance(gap,dict) or not _integer(gap.get('min'),18,10000) or not _integer(gap.get('max'),18,10000) or gap['min']>gap['max']:
            errors.append('species_authored requires explicit parent_age_gap {min,max} in local years.')
    elif 'parent_age_gap' in cfg:
        gap=cfg['parent_age_gap']
        if not isinstance(gap,dict) or not _integer(gap.get('min'),18,10000) or not _integer(gap.get('max'),18,10000) or gap['min']>gap['max']:
            errors.append('parent_age_gap needs bounded integer min/max, minimum at least18.')
    from engine import life_stages,population_health
    spec=species.get(cfg.get('species'),{})
    errors.extend(life_stages.validate_profile(spec.get('life_stages',{})))
    if not errors and cfg.get('parent_age_gap',{}).get('min',18)<life_stages.resolve_profile(cfg.get('species'),spec)['adulthood_years']:
        errors.append('parent_age_gap minimum cannot be earlier than species adulthood.')
    errors.extend(population_health.validate_profile(cfg.get('health',{})))
    return errors


def _safe_room(room,group,groups):
    if room.get('requires_boat') or room.get('population_unsafe') or room.get('hazardous'):return False
    allowed=room.get('allowed_factions',[]);forbidden=room.get('forbidden_factions',[])
    if group in forbidden or (allowed and group not in allowed):return False
    own=room.get('group')
    if own and group and own!=group:
        from engine.frontiers import relation
        if relation(groups.get(own),group)=='hostile' or relation(groups.get(group),own)=='hostile':return False
    return True


def _routes(data,cfg):
    rooms={r['id']:r for r in data.get('room',[])};groups={r['id']:r for r in data.get('group',[])}
    dangerous={n['id'] for n in data.get('npc',[]) if n.get('aggressive') or n.get('traffic',{}).get('enabled')}
    danger={n.get('spawn_room') for n in data.get('npc',[]) if n['id'] in dangerous}
    encounters={e['id']:e for e in data.get('encounter',[])}
    for rid,room in rooms.items():
        if any(sp.get('npc') in dangerous for sp in room.get('spawners',[])) or any(any(n in dangerous for n in encounters.get(e,{}).get('members',[])) for e in room.get('encounters',[])):danger.add(rid)
    # A route must work without acquiring quest flags, boats, or combat clearance.
    graph={}
    for rid,room in rooms.items():
        if not _safe_room(room,cfg.get('group'),groups) or rid in danger:continue
        graph[rid]=[dest for di,dest in room.get('exits',{}).items() if dest in rooms and not room.get('gates',{}).get(di) and _safe_room(rooms[dest],cfg.get('group'),groups) and dest not in danger]
    cache={}
    def reach(start):
        if start not in cache:
            seen={start};todo=deque([start])
            while todo:
                for dest in graph.get(todo.popleft(),[]):
                    if dest not in seen:seen.add(dest);todo.append(dest)
            cache[start]=seen
        return cache[start]
    return lambda start,end: start in graph and end in reach(start) and start in reach(end)


def _age_people(cfg,species,rng):
    from engine import life_stages
    bins=cfg.get('age_bins',HUMANLIKE_BINS) if cfg['preset']=='humanlike_fictional' else cfg['age_bins']
    counts=largest_remainder(cfg['count'],[r['weight'] for r in bins],rng)
    people=[]
    for row,count in zip(bins,counts):
        ages=list(range(row['min'],row['max']+1));rng.shuffle(ages)
        for i in range(count):people.append({'age_years':ages[i%len(ages)]})
    rng.shuffle(people)
    fractions=list(range(len(people)));rng.shuffle(fractions)
    for i,p in enumerate(people):
        p['age_fraction_minutes']=(fractions[i]*worldtime.MINUTES_PER_YEAR+rng.randrange(worldtime.MINUTES_PER_YEAR))//len(people)
        p['source_id']=f"pop_{cfg['id']}_{i+1:04d}"
        p['stage']=life_stages.classify(dict(age_years=p['age_years'],species=cfg['species'],sentient=True),species)
        p['adult']=p['stage']['adult']
        p['marital_status']='never_married';p['relationship_history']=[]
        p['biological_parent_source_ids']=[];p['guardian_source_ids']=[];p['current_partner_source_id']=None;p['partnership_status']='unpartnered';p['care_role']='none'
    return people,bins,counts


def _households(people,cfg,data,rng):
    from engine import life_stages
    species=next((s for s in data.get('species',[]) if s['id']==cfg['species']),{})
    stages=life_stages.resolve_profile(cfg['species'],species)
    parent_gap=cfg.get('parent_age_gap',{'min':18,'max':55})
    parental_min=parent_gap['min'];parental_max=parent_gap['max'];elder_age=stages['elder_years']
    adults=[p for p in people if p['adult']];dependents=sorted([p for p in people if not p['adult']],key=lambda p:p['age_years'],reverse=True)
    maxsize=max(h['capacity'] for h in cfg['homes']);groups={g['id']:g for g in data.get('group',[])}
    rules=groups.get(cfg.get('group'),{}).get('coupling_rules',{})
    marriage=rules.get('marriage_allowed',True) and cfg.get('group') not in rules.get('forbidden_factions',[]) and (not rules.get('allowed_factions') or cfg.get('group') in rules['allowed_factions'])
    households=[]
    def pair(a,b,kind='married'):
        if not marriage:return
        for own,other in ((a,b),(b,a)):
            own['current_partner_source_id']=other['source_id'];own['marital_status']='married' if kind=='married' else 'never_married';own['partnership_status']=kind
            own['relationship_history'].append(dict(event='initial_partnership',kind=kind,partner_source_id=other['source_id']))
    def take_guardian(children):
        if not adults:raise PopulationError('There are not enough adults for dependent households; revise bins, count or housing.')
        eldest=max(p['age_years'] for p in children)
        # Prioritize plausible parents without claiming every guardian is biological.
        best=min(adults,key=lambda p:(p['age_years']<eldest+parental_min,abs(p['age_years']-(eldest+parental_min+10)),p['source_id']))
        adults.remove(best);return best
    def add(members,kind):
        hid=f"hh_{cfg['id']}_{len(households)+1:04d}"
        has_dependents=any(not p['adult'] for p in members)
        eligible=[p['source_id'] for p in members if p['adult']] if has_dependents else []
        row=dict(id=hid,cohort_id=cfg['id'],type=kind,member_source_ids=[p['source_id'] for p in members],eligible_guardian_source_ids=eligible)
        households.append(row)
        for p in members:p['household_id']=hid;p['guardian_eligible']=p['adult'] and has_dependents
        return row
    index=0
    while dependents:
        if maxsize<2:raise PopulationError('Dependent residents require a home large enough for an adult guardian and dependent together.')
        n=min(len(dependents),max(1,min(maxsize-1,1+index%3)))
        children=dependents[:n];del dependents[:n]
        guardians=[take_guardian(children)]
        # Reserve one guardian per remaining group; do not consume them as spouses.
        reserve=math.ceil(len(dependents)/max(1,min(3,maxsize-1)))
        if index%3!=1 and len(adults)>reserve and n+2<=maxsize:guardians.append(take_guardian(children))
        if len(guardians)==2:pair(*guardians,kind='cohabiting' if index%4==0 else 'married')
        elif guardians[0]['age_years']>=stages['adulthood_years']+12:
            status=('divorced','never_married','separated','widowed')[index%4]
            guardians[0]['marital_status']=status
            if status!='never_married':guardians[0]['relationship_history'].append(dict(event=status,historical=True,previous_partner='not_in_current_population'))
        for child in children:
            child['guardian_source_ids']=[g['source_id'] for g in guardians]
            child['biological_parent_source_ids']=[g['source_id'] for g in guardians if parental_min<=(g['age_years']-child['age_years'])+(g['age_fraction_minutes']-child['age_fraction_minutes'])/worldtime.MINUTES_PER_YEAR<=parental_max]
        if any(not c['stage']['in_school'] for c in children):guardians[0]['care_role']='home_caregiver'
        members=guardians+children;kind='family' if len(guardians)==2 else 'single_guardian'
        elders=[p for p in adults if p['age_years']>=elder_age and p['age_years']>max(g['age_years'] for g in guardians)+parental_min]
        if index%3==0 and elders and len(members)<maxsize and len(adults)>reserve:
            elder=elders[0];adults.remove(elder);members.append(elder);kind='extended'
        add(members,kind);index+=1
    rng.shuffle(adults)
    while adults:
        first=adults.pop();members=[first];kind='solo'
        if index%4 in (0,1) and adults and maxsize>=2:
            second=min(adults,key=lambda p:abs(p['age_years']-first['age_years']));adults.remove(second);members.append(second)
            pair(first,second);kind='couple' if marriage else 'shared'
        elif index%4==2 and adults and maxsize>=2:
            members.append(adults.pop());kind='shared'
            if adults and maxsize>=3:members.append(adults.pop())
        for person in members:
            if not person['current_partner_source_id'] and person['age_years']>=stages['adulthood_years']+12:
                status=('never_married','divorced','separated','widowed')[index%4]
                person['marital_status']=status
                if status!='never_married':person['relationship_history'].append(dict(event=status,historical=True,previous_partner='not_in_current_population'))
        add(members,kind);index+=1
    # Plan complete households before assigning dwellings. Multiple independent
    # households can share one dwelling; neither implies ownership or tenancy.
    occupants=Counter()
    for npc in data.get('npc',[]):
        home=npc.get('population_profile',{}).get('home_room') or npc.get('home_room') or npc.get('spawn_room')
        if home:occupants[home]+=1
    available={h['room']:h['capacity']-occupants[h['room']] for h in cfg['homes']}
    if any(v<0 for v in available.values()):raise PopulationError('A configured home already exceeds its declared capacity.')
    if sum(available.values())<len(people):raise PopulationError('Authored homes have insufficient free capacity after existing residents are counted.')
    for hh in sorted(households,key=lambda h:(-len(h['member_source_ids']),h['id'])):
        choices=[rid for rid,beds in available.items() if beds>=len(hh['member_source_ids'])]
        if not choices:raise PopulationError('Households cannot fit intact into these home capacities; add larger homes or more capacity.')
        home=min(choices,key=lambda rid:(available[rid]-len(hh['member_source_ids']),rid))
        hh['home_room']=home;available[home]-=len(hh['member_source_ids'])
    by_id={h['id']:h for h in households}
    for p in people:p['home_room']=by_id[p['household_id']]['home_room']
    return households


def _education(person,cfg,rng):
    age=person['age_years'];adult=person['adult']
    if not adult:
        stage=person['stage']
        attainment='not_started' if not stage['in_school'] else 'foundational_in_progress'
        literacy='not_yet_reading' if not stage['in_school'] else ('developing' if stage['stage']!='adolescent' else rng.choice(['developing','functional']))
        enrollment='care' if stage['stage']=='infant' else 'early_learning' if not stage['in_school'] else cfg.get('learning','home')
        return dict(enrollment=enrollment,attainment=attainment,literacy=literacy,skills=[],learning_room=person['home_room'],provider_source_ids=[],basis='fictional age-appropriate starting profile; no credential inferred from enrollment')
    attainment=rng.choices(['foundational','practical_training','advanced','limited_formal_schooling'],[42,38,12,8])[0]
    literacy=rng.choices(['functional','developing','limited'],[85,10,5])[0]
    enrollment='continuing_home' if rng.random()<.2 else 'none'
    return dict(enrollment=enrollment,attainment=attainment,literacy=literacy,skills=[],learning_room=person['home_room'] if enrollment!='none' else None,provider_source_ids=[],basis='fictional starting profile; adult learning remains possible')


def _generate(data,cfg):
    from engine import life_stages,population_health
    rng=random.Random(cfg['seed']);spec=next((s for s in data.get('species',[]) if s['id']==cfg['species']),{})
    people,bins,counts=_age_people(cfg,spec,rng)
    households=_households(people,cfg,data,rng);reachable=_routes(data,cfg)
    for home in {p['home_room'] for p in people}:
        if not reachable(home,home):raise PopulationError('Authored home '+home+' contains an unsafe room, aggressive spawn or traffic.')
    for person in people:
        for target in cfg.get('leisure_rooms',[]):
            if not reachable(person['home_room'],target):raise PopulationError('No safe, unlocked, faction-permitted return route from '+person['home_room']+' to leisure room '+target+'.')
    # Allocate only finite authored occupation slots, never new shop stock/wages.
    adults=[p for p in people if p['adult'] and p['care_role']!='home_caregiver' and life_stages.classify(dict(age_years=p['age_years'],sentient=True),spec)['can_work']]
    rng.shuffle(adults)
    for job in cfg.get('workplaces',[]):
        candidates=[p for p in adults if reachable(p['home_room'],job['room'])]
        if len(candidates)<job['slots']:raise PopulationError('Not enough eligible adults with safe return routes for workplace '+job['room']+'.')
        for person in candidates[:job['slots']]:person['job']=job;adults.remove(person)
    used={n.get('name','') for n in data.get('npc',[])}
    groups={g['id']:g for g in data.get('group',[])};pool=groups.get(cfg.get('group'),{}).get('name_pool') or next((g['name_pool'] for g in groups.values() if g.get('name_pool')), {})
    records=[]
    for p in people:
        sex=rng.choice([s['id'] for s in data.get('sex',[])]) if data.get('sex') else None;first,last=names.pick(pool,sex,str(cfg['seed'])+':'+p['source_id'],used)
        used.add(first+' '+last)
        appearance=dict(hair=rng.choice(['dark','brown','auburn','fair','silver','shaved']),eyes=rng.choice(['brown','grey','green','blue','hazel']),dress=rng.choice(['plain woven tunic','patched travel clothes','neat local clothes','layered linen','warm wool']))
        ed=_education(p,cfg,rng);job=p.get('job')
        if job:
            ed['skills']=[job['occupation']]
            if job['occupation']=='teacher':ed.update(attainment='teacher_training',literacy='functional',skills=['teaching'])
        health=population_health.seed_profile(p['age_years']+p['age_fraction_minutes']/worldtime.MINUTES_PER_YEAR,cfg['species'],cfg.get('health',{}),rng)
        pp={key:deepcopy(p[key]) for key in ('age_years','age_fraction_minutes','household_id','home_room','guardian_source_ids','biological_parent_source_ids','current_partner_source_id','marital_status','relationship_history','guardian_eligible','partnership_status','care_role')}
        pp.update(version=VERSION,cohort_id=cfg['id'],species=cfg['species'],education=ed,appearance=appearance,health=health,leisure_rooms=list(cfg.get('leisure_rooms',[])))
        social=dict(age_years=p['age_years'],species=cfg['species'],sentient=True,romance_enabled=False,family_enabled=False,autonomous=False,fertile=False,accepts=['friend','business'] if p['adult'] else ['friend'])
        npc=dict(id=p['source_id'],name=first+' '+last,first_name=first,last_name=last,name_mode='manual',race=cfg['race'],sex=sex,group=cfg.get('group',''),hp=20,attack=1,defense=1,gold=0,spawn_room=p['home_room'],home_room=p['home_room'],combatant=False,aggressive=False,roaming=False,social_profile=social,population_profile=pp,description=first+' wears '+appearance['dress']+'.',work_hours=dict(start=420,duration=600 if job else 0),schedule=[dict(hour=0,room=p['home_room'],activity='sleeping at home'),dict(hour=7,room=job['room'] if job else p['home_room'],activity='working' if job else 'at home'),dict(hour=17,room=(cfg.get('leisure_rooms') or [p['home_room']])[0],activity='leisure'),dict(hour=21,room=p['home_room'],activity='resting at home')])
        if sex is None:npc.pop('sex',None)
        if job:npc.update(occupation=job['occupation'],work_room=job['room'],workplace_room=job['room'])
        records.append(npc)
    combined={n['id']:n for n in data.get('npc',[])+records}
    providers={}
    for n in combined.values():
        sp=n.get('social_profile',{})
        if not sp.get('sentient') or not life_stages.classify(sp,next((s for s in data.get('species',[]) if s['id']==sp.get('species')),{}))['adult']:continue
        if n.get('occupation')=='teacher' or n.get('profession')=='teacher':
            rooms={n.get('work_room'),n.get('workplace_room')}|{s.get('room') for s in n.get('schedule',[]) if 'teach' in s.get('activity','')}
            for rid in rooms:
                if rid:providers.setdefault(rid,[]).append(n['id'])
    for row in cfg.get('learning_providers',[]):
        n=combined.get(row['npc']);sp=n.get('social_profile',{}) if n else {}
        if not n or not sp.get('sentient') or not life_stages.classify(sp,next((s for s in data.get('species',[]) if s['id']==sp.get('species')),{}))['adult']:
            raise PopulationError('Learning provider '+row['npc']+' must be an existing sentient adult.')
        providers.setdefault(row['room'],[]).append(row['npc'])
    learning=cfg.get('learning','home')
    targets=cfg.get('school_rooms',[]) if learning=='school' else cfg.get('community_learning_rooms',[])
    for rid in targets:
        if not providers.get(rid):raise PopulationError('Learning room '+rid+' has no authored adult teacher or explicitly qualified mentor.')
    for npc in records:
        p=npc['population_profile'];ed=p['education']
        ed['learning_mode']=learning
        ed['initial_enrollment']=ed['enrollment']
        ed['phase']='adult' if p['age_years']>=life_stages.resolve_profile(cfg['species'],spec)['adulthood_years'] else 'infant' if ed['enrollment']=='care' else 'preschool' if ed['enrollment']=='early_learning' else 'school'
        if ed['phase']!='adult' and learning in ('school','community'):
            choices=[r for r in targets if reachable(p['home_room'],r)]
            if not choices:raise PopulationError('No safe, unlocked return route from '+p['home_room']+' to staffed '+learning+' learning.')
            ed['school_room']=choices[0];ed['school_provider_source_ids']=list(providers[choices[0]])
        if ed['enrollment'] in ('care','early_learning','home'):
            ed['provider_source_ids']=list(p['guardian_source_ids']);ed['provision']='guardian care' if ed['enrollment']=='care' else 'guardian-led home learning'
        elif ed['enrollment'] in ('school','community'):
            choices=[r for r in targets if reachable(p['home_room'],r)]
            if not choices:raise PopulationError('No safe, unlocked return route from '+p['home_room']+' to staffed '+learning+' learning.')
            ed['learning_room']=choices[0];ed['provider_source_ids']=list(providers[choices[0]]);ed['provision']='authored '+learning+' teaching'
    return records,households,bins,counts


def preview(target,config):
    """Return a JSON-serializable plan/report. No file, Editor or save mutation."""
    result=dict(ok=False,errors=[],warnings=[],installed=False,no_op=False,summary={},plan=None)
    try:
        _,data,metadata,manifest=_source(target);cfg=deepcopy(config)
        result['config_hash']=_digest(cfg)
        result['preview_token']=_digest(dict(data=data,metadata=metadata,manifest=manifest,config=cfg))
        errors=_validate(data,metadata,manifest,cfg)
        if errors:result['errors']=errors;return result
        existing=manifest['cohorts'].get(cfg['id'])
        if existing:
            if existing.get('config_hash')!=result['config_hash']:
                raise PopulationError('This cohort ID was already installed with another config. Existing residents are never regenerated; use a new cohort ID for an additive population.')
            result.update(ok=True,no_op=True,summary=deepcopy(existing.get('summary',{})))
            prior=result['summary'].get('population',{})
            if 'existing' in prior:
                prior['existing_npc_definitions']=prior.pop('existing')
                prior['existing_basis']='authored NPC definitions, including creatures; not a living-resident total'
            result['warnings']=['Already installed. Edited or deleted NPC definitions and saved residents are not restored or regenerated.']
            return result
        records,households,bins,counts=_generate(data,cfg)
        collisions={n['id'] for n in records}&{n['id'] for n in data.get('npc',[])}
        if collisions:raise PopulationError('Generated NPC IDs already exist without this manifest: '+', '.join(sorted(collisions)[:5]))
        summary=dict(count=len(records),population=dict(requested=cfg['count'],generated=len(records),existing_npc_definitions=len(data.get('npc',[])),existing_basis='authored NPC definitions, including creatures; not a living-resident total',denominator='new cohort only'),species=cfg['species'],species_target=cfg['count'],species_actual=len(records),ages=dict(sorted(Counter(str(n['population_profile']['age_years']) for n in records).items(),key=lambda x:int(x[0]))),age_bins=[dict(**b,target_count=c,actual_count=sum(b['min']<=n['population_profile']['age_years']<=b['max'] for n in records)) for b,c in zip(bins,counts)],households=dict(count=len(households),types=dict(Counter(h['type'] for h in households)),target='No statistical target; capacity-constrained fictional composition'),learning=dict(Counter(n['population_profile']['education']['enrollment'] for n in records)),bounds=dict(min_age=min(b['min'] for b in bins),max_age=max(b['max'] for b in bins),minutes_per_year=worldtime.MINUTES_PER_YEAR),caveats=list(CAVEATS))
        updated=deepcopy(manifest)
        updated['cohorts'][cfg['id']]=dict(id=cfg['id'],version=VERSION,config_hash=result['config_hash'],config=cfg,source_ids=[n['id'] for n in records],household_ids=[h['id'] for h in households],summary=summary)
        updated['households'].update({h['id']:h for h in households})
        issues=validate_manifest({**data,'npc':data.get('npc',[])+records},updated)
        if issues:raise PopulationError('; '.join(issues))
        result.update(ok=True,summary=summary,plan=dict(npcs=records,households=households,manifest=updated),warnings=list(CAVEATS))
        return result
    except (ValueError,TypeError,KeyError,OSError) as exc:
        result['errors']=[str(exc)];return result


def atomic_write_files(directory,payloads):
    """Stage all JSON before replacing any destination; roll back a failed batch.

    Rollback uses the original bytes (including absence), not a reserialization.
    A process crash is not a database transaction; backups remain only if rollback
    itself fails, in which case the raised error names those recovery files.
    """
    directory=Path(directory)
    if not directory.is_dir():raise PopulationError('The target world directory must already exist.')
    prepared={};backups={};replaced=[]
    try:
        for name,payload in payloads.items():
            if Path(name).name!=name:raise PopulationError('Only files directly inside the world directory may be written.')
            raw=(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()
            target=directory/name
            if target.is_symlink():raise PopulationError('Refusing to replace a symlinked content file: '+name)
            fd,temp=tempfile.mkstemp(prefix='.'+name+'.stage-',dir=directory)
            with os.fdopen(fd,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
            prepared[name]=Path(temp)
            if target.exists():
                fd,backup=tempfile.mkstemp(prefix='.'+name+'.rollback-',dir=directory)
                with os.fdopen(fd,'wb') as handle:handle.write(target.read_bytes());handle.flush();os.fsync(handle.fileno())
                backups[name]=Path(backup)
            else:backups[name]=None
        for name,temp in prepared.items():os.replace(temp,directory/name);replaced.append(name)
    except Exception as original:
        failures=[]
        for name in reversed(replaced):
            try:
                if backups[name] is None:(directory/name).unlink(missing_ok=True)
                else:os.replace(backups[name],directory/name)
            except OSError as rollback:failures.append(str(backups[name])+': '+str(rollback))
        if failures:raise OSError('Content write failed and rollback needs manual recovery: '+'; '.join(failures)) from original
        raise
    finally:
        for path in list(prepared.values())+list(backups.values()):
            if path is not None and path.exists():
                # Preserve rollback evidence if recovery itself could not finish.
                if 'failures' in locals() and failures and path in backups.values():continue
                path.unlink(missing_ok=True)


def install(target,config,expected_preview=None):
    """Validate again, then stage/add once. Reinstallation never repairs deletions."""
    report=preview(target,config)
    if not report['ok']:raise PopulationError('; '.join(report['errors']))
    if expected_preview is not None and expected_preview!=report['preview_token']:raise PopulationError('Population preview is stale. Preview the current content and config again before applying.')
    if report['no_op']:return report
    folder,data,_,_=_source(target)
    updated=deepcopy(data.get('npc',[]))+deepcopy(report['plan']['npcs'])
    manifest=deepcopy(report['plan']['manifest'])
    if hasattr(target,'data'):
        target.data['npc']=updated;target.population_manifest=manifest
        target.dirty.add('npc');target.population_manifest_dirty=True
    else:atomic_write_files(folder,{'npcs.json':updated,'population.json':manifest})
    report['installed']=True
    return report


def _validate_manifest(data,manifest):
    """Audit active enrolled definitions, allowing deliberate definition deletion.

    Missing sources remain tombstones in the manifest, not regeneration requests.
    Live references must stay within this authored cohort/household graph.
    """
    if not manifest:return []
    errors=[]
    if not isinstance(manifest,dict) or manifest.get('version')!=VERSION or not isinstance(manifest.get('cohorts'),dict) or not isinstance(manifest.get('households'),dict):
        return ['population.json must be a supported version-1 manifest with cohort and household objects.']
    npcs={n.get('id'):n for n in data.get('npc',[]) if isinstance(n,dict)}
    rooms={r.get('id') for r in data.get('room',[]) if isinstance(r,dict)}
    species={r.get('id'):r for r in data.get('species',[]) if isinstance(r,dict)}
    sources={};households=manifest['households']
    def ids(value):return isinstance(value,list) and all(isinstance(i,str) and i for i in value) and len(value)==len(set(value))
    for cid,cohort in manifest['cohorts'].items():
        if not isinstance(cohort,dict) or cohort.get('id')!=cid or cohort.get('version')!=VERSION or not ids(cohort.get('source_ids')) or not ids(cohort.get('household_ids')) or not isinstance(cohort.get('config'),dict):
            errors.append(str(cid)+': malformed cohort manifest.');continue
        for sid in cohort['source_ids']:
            if sid in sources:errors.append(sid+': source belongs to more than one cohort.')
            sources[sid]=cid
        for hid in cohort['household_ids']:
            if hid not in households:errors.append(cid+': household '+hid+' is missing.')
    for room in data.get('room',[]):
        for spawn in room.get('spawners',[]):
            if spawn.get('npc') in sources:errors.append(str(room.get('id'))+': permanent residents cannot be referenced by a room spawner.')
    for encounter in data.get('encounter',[]):
        if any(sid in sources for sid in encounter.get('members',[])):errors.append(str(encounter.get('id'))+': permanent residents cannot be spawned as encounter members.')
    for group in data.get('group',[]):
        if any(sid in sources for sid in group.get('roster',[])):errors.append(str(group.get('id'))+': permanent residents cannot be in a combat spawn roster.')
    membership={}
    for hid,hh in households.items():
        if not isinstance(hh,dict) or hh.get('id')!=hid or hh.get('cohort_id') not in manifest['cohorts'] or not ids(hh.get('member_source_ids')) or not ids(hh.get('eligible_guardian_source_ids')):
            errors.append(str(hid)+': malformed household definition.');continue
        members=hh['member_source_ids'];active=[sid for sid in members if sid in npcs]
        if active and hh.get('home_room') not in rooms:errors.append(hid+': active household home room is missing.')
        if any(i not in members for i in hh['eligible_guardian_source_ids']):errors.append(hid+': eligible guardians must be household members.')
        for sid in members:
            if sources.get(sid)!=hh['cohort_id']:errors.append(hid+': member '+sid+' is not enrolled in this cohort.')
            if sid in membership:errors.append(sid+': belongs to multiple households.')
            membership[sid]=hid
    from engine import life_stages,population_health
    parent_graph={};partners={}
    for sid,cid in sources.items():
        if sid not in npcs:continue
        npc=npcs[sid];pp=npc.get('population_profile')
        if not isinstance(pp,dict) or pp.get('version')!=VERSION or pp.get('cohort_id')!=cid:
            errors.append(sid+': missing or invalid enrolled population_profile.');continue
        hid=pp.get('household_id');hh=households.get(hid,{})
        if membership.get(sid)!=hid or pp.get('home_room')!=hh.get('home_room'):errors.append(sid+': population household/home references disagree with manifest.')
        if npc.get('spawn_managed') or npc.get('aggressive') or npc.get('combatant'):errors.append(sid+': residents cannot be combat-managed respawning actors.')
        if not _integer(pp.get('age_years'),0,10000) or not _integer(pp.get('age_fraction_minutes',0),0,worldtime.MINUTES_PER_YEAR-1):errors.append(sid+': invalid initial local age/birthday.');continue
        sp=npc.get('social_profile',{})
        if not isinstance(sp,dict) or sp.get('sentient') is not True:errors.append(sid+': residents require an explicit sentient social profile.');continue
        errors.extend(life_stages.validate_age(sp,label=sid+'.social_profile'))
        if sp.get('born_minute') is None and sp.get('age_epoch_minute') is None and sp.get('age_years')!=pp['age_years']:errors.append(sid+': social_profile.age_years and population_profile.age_years must match until an explicit birth/age epoch is authored.')
        try:stage=life_stages.classify(dict(age_years=pp['age_years'],sentient=True),species.get(pp.get('species'),{}))
        except ValueError as exc:errors.append(sid+': '+str(exc));continue
        for field in ('guardian_source_ids','biological_parent_source_ids'):
            if not ids(pp.get(field)):errors.append(sid+': '+field+' must be a unique ID list.');continue
            for ref in pp[field]:
                if ref==sid or ref not in sources:errors.append(sid+': invalid '+field+' reference '+ref+'.')
                if ref in npcs:
                    rp=npcs[ref].get('population_profile',{})
                    try:adult=life_stages.classify(dict(age_years=rp.get('age_years',0),sentient=True),species.get(rp.get('species'),{}))['adult']
                    except ValueError:adult=False
                    if not adult:errors.append(sid+': '+field+' reference must be adult.')
                if field=='guardian_source_ids' and ref not in hh.get('eligible_guardian_source_ids',[]):errors.append(sid+': guardian is not an explicitly eligible household adult.')
        if not stage['adult'] and not pp.get('guardian_source_ids'):errors.append(sid+': every dependent requires authored adult guardian links (deletion later becomes a care gap).')
        parent_graph[sid]=pp.get('biological_parent_source_ids',[])
        gap=manifest['cohorts'][cid].get('config',{}).get('parent_age_gap',{'min':18,'max':55})
        for ref in parent_graph[sid]:
            if ref in npcs and isinstance(gap,dict):
                parent=npcs[ref].get('population_profile',{})
                if not gap.get('min',18)<=(parent.get('age_years',0)-pp['age_years'])+(parent.get('age_fraction_minutes',0)-pp.get('age_fraction_minutes',0))/worldtime.MINUTES_PER_YEAR<=gap.get('max',55):errors.append(sid+': biological parent age gap is outside the authored range.')
        partner=pp.get('current_partner_source_id')
        if partner:
            partners[sid]=partner
            if not stage['adult'] or partner==sid or partner not in sources:errors.append(sid+': current partnership requires two enrolled adults.')
            if partner in npcs and npcs[partner].get('population_profile',{}).get('current_partner_source_id')!=sid:errors.append(sid+': partnership must be reciprocal and exclusive.')
        if pp.get('marital_status') not in ('never_married','married','divorced','separated','widowed'):errors.append(sid+': marital_status must describe legal/history status separately from current partnership.')
        ed=pp.get('education')
        if not isinstance(ed,dict) or not isinstance(ed.get('skills'),list) or not ids(ed.get('provider_source_ids',[])):errors.append(sid+': invalid distinct education/enrollment/skill profile.')
        elif ed.get('learning_room') is not None and ed['learning_room'] not in rooms:errors.append(sid+': education room is missing.')
        if not isinstance(pp.get('appearance'),dict) or not isinstance(pp.get('relationship_history'),list):errors.append(sid+': appearance/history must be explicit structured profiles.')
        # Health is a frozen narrative snapshot, not a config to be re-sampled.
        if pp.get('health') is not None and (not isinstance(pp['health'],dict) or pp['health'].get('mechanical_effects') is not False):errors.append(sid+': invalid initial narrative health snapshot.')
    for sid in parent_graph:
        seen=set();todo=list(parent_graph[sid])
        while todo:
            ref=todo.pop()
            if ref==sid:errors.append(sid+': biological parent graph contains a cycle.');break
            if ref not in seen:seen.add(ref);todo.extend(parent_graph.get(ref,[]))
        if partners.get(sid) in seen:errors.append(sid+': current partner cannot be a biological ancestor.')
    return errors


def validate_manifest(data,manifest):
    try:return _validate_manifest(data,manifest)
    except (TypeError,KeyError,AttributeError,ValueError) as exc:return ['Malformed population manifest/profile: '+str(exc)]
