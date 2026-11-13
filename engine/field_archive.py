"""Compile creator-authored natural history and civic registers for the chronicle reader."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random

from engine import worldtime

FILE = Path('assets/chronicles/field-survey.json')
SECTIONS = ('natural', 'monstorium', 'knowledge', 'sources')


def volume(folder):
    folder = Path(folder)
    def read(base):
        path = base / FILE
        if (not path.is_file() or path.is_symlink() or path.parent.is_symlink() or
                path.parent.parent.is_symlink() or path.stat().st_size > 4_000_000):
            return {}
        book = json.loads(path.read_bytes())
        return book if isinstance(book, dict) and book.get('version') == 1 else {}
    direct = read(folder)
    if direct:
        return direct
    # Older adventures retain their own foundation. A supplement may explicitly
    # name the exact rules signature it accompanies. No name-based world matching.
    from engine import loader
    rules = folder/'world-rules.json'
    if not rules.is_file() or not Path(loader.GAMES_DIR).is_dir():
        return {}
    signature = sha256(json.dumps(json.loads(rules.read_bytes()),sort_keys=True,
                                  separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    for source in sorted(Path(loader.GAMES_DIR).iterdir()):
        if source == folder or source.is_symlink() or source.name.startswith(('.', 'adventure_')):
            continue
        candidate = read(source)
        if signature in candidate.get('compatible_rules', []):
            return candidate
    return {}


def family_seed(seed, key):
    return random.Random(sha256(f'{seed}/civil-register/{key}'.encode()).digest())


def registered_relatives(seed, npc, register):
    """These are historical register entries, separate from current simulated actors."""
    if not register or not npc.get('social_profile',{}).get('sentient'):
        return []
    rng = family_seed(seed, npc['id'])
    first = rng.sample(register['names'],10)
    wards = rng.sample(register['surnames'],4)
    occupation = rng.sample(register['trades'],10)
    names = [f'{given} {wards[house]}' for given,house in
             zip(first,[0,1,0,2,1,3,0,1,0,1])]
    kinds = ['Parent','Parent','Grandparent','Grandparent','Grandparent','Grandparent',
             'Aunt','Uncle','Cousin','Cousin']
    links = [[2,3],[4,5],[],[],[],[],[2,3],[4,5],[6],[7]]
    offsets = [rng.randint(21,35),rng.randint(21,35)]
    offsets += [offsets[i]+rng.randint(20,37) for i in (0,0,1,1)]
    offsets += [offsets[0]+rng.randint(-5,5), offsets[1]+rng.randint(-5,5)]
    offsets += [offsets[6]-rng.randint(20,30),offsets[7]-rng.randint(20,30)]
    age = (npc.get('social_profile') or {}).get('age_years')
    return [dict(kin=kinds[i],name=names[i],trade=occupation[i],parents=[names[p] for p in links[i]],
                 years_before=(int(age)+offsets[i] if type(age) in (int,float) else None),
                 trace=register['memories'][rng.randrange(len(register['memories']))])
            for i in range(10) if type(age) not in (int,float) or int(age)+offsets[i]>=0]


def compile_volume(archive, book, rooms, npcs, groups, species, races, items, encounters):
    if not book or archive.get('field_edition') == book.get('edition'):
        return
    records = defaultdict(list)
    def add(section, title, text, date='Survey record', url=None):
        row=dict(name=title,text=text,date=date)
        if url:row['url']=url
        records[section].append(row)
    sites={r['id']:r for r in rooms}
    visible={rid:r.get('name',rid) for rid,r in sites.items() if r.get('map_visibility')!='hidden'}
    item_names={r['id']:r['name'] for r in items}
    archive['events']=[e for e in archive['events'] if not e.get('survey_edition')]
    for e in book.get('eras',[]):
        archive['events'].append(dict(domain='geology',at=archive['present']-e['years']*worldtime.MINUTES_PER_YEAR,
                                      text=e['text'],heading=e['name'],survey_edition=True))
    by_land=defaultdict(list)
    for row in rooms:
        geo=row.get('geology') or {}
        if row['id'] in visible and geo.get('landform'):
            area=row.get('atlas_region') or row.get('world_region') or 'Regional survey'
            by_land[area,geo['landform']].append(row)
    for (area,land),rows in sorted(by_land.items()):
        example=sorted(rows,key=lambda r:r['id'])[0];geo=example['geology']
        text=f"{len(rows):,} surveyed sites record {land.replace('_',' ')}. At {example['name']} the rock register gives {str(geo.get('rock') or 'unclassified rock').replace('_',' ')}. "+str(geo.get('notes') or '')
        archive['events'].append(dict(domain='geology',at=archive['present'],text=text,heading=f'{area} · {land.replace("_"," ")}',survey_edition=True))
    for group in groups:
        entry=book.get('states',{}).get(group['id'])
        if entry:
            # Position the early material before, and records after, the founding date.
            times=[e['at'] for e in archive['events'] if e['domain']=='civilization' and
                   (e.get('place')==group.get('start_room') or group['name'] in e['text'])]
            anchor=min(times,default=archive['present']-100*worldtime.MINUTES_PER_YEAR)
            for at,text,title in [(anchor-35*worldtime.MINUTES_PER_YEAR,entry['history'],entry['title']),
                                  (archive['present'],entry['debate'],'The present debate')]:
                archive['events'].append(dict(domain='civilization',at=at,heading=group['name']+' · '+title,text=text,survey_edition=True))
    group_names = {g['id']: g['name'] for g in groups}
    for years, a, b, title, account in book.get('treaties', []):
        if a in group_names and b in group_names:
            archive['events'].append(dict(
                domain='civilization', at=archive['present']-years*worldtime.MINUTES_PER_YEAR,
                heading=title+' · '+group_names[a]+' and '+group_names[b],
                text=account, survey_edition=True))
    for gid, entry in book.get('founding_residents',{}).get('local',{}).items():
        if gid not in group_names:continue
        for ago,heading,account in [(3,entry[0],entry[1]),(8,'A public reading of the household rolls',book['states'][gid]['debate'])]:
            archive['events'].append(dict(domain='civilization',at=archive['present']-ago*worldtime.MINUTES_PER_YEAR,
                heading=group_names[gid]+' · '+heading,text=account,survey_edition=True))
    for race in races:
        entry=book.get('cultures',{}).get(race['id'])
        if entry:
            add('natural',race['name']+' · '+entry[0],race['description']+' '+entry[1],'People and oral history')
            if (race.get('social_profile') or {}).get('undead'):
                add('monstorium',race['name']+' · '+entry[0],entry[1],'Testimony of the Returned')
    for sp in sorted(species,key=lambda r:r['name']):
        entry=book.get('species',{}).get(sp['id'])
        if not entry:continue
        cat=sp['category'];notes=[entry['note'],book.get('lineages',{}).get(cat,'')]
        foods=[item_names[x] for x in sp.get('diet',[]) if x in item_names]
        notes.append(f"The local register places it in {sp.get('habitat','unrecorded habitat')}.")
        if foods:notes.append('Recorded foods include '+', '.join(foods)+'.')
        if sp.get('breeding_seasons'):notes.append('Recorded breeding season: '+', '.join(sp['breeding_seasons'])+'.')
        if sp.get('location') in visible:notes.append('Filed at '+visible[sp['location']]+'.')
        add('natural',sp['name'],' '.join(filter(None,notes)),'Field history · '+book['witnesses'].get(cat,'field observations'))
        src=entry.get('reading',{})
        if src:add('sources',sp['name'],src['title'],'Comparative natural history',src['url'])
    for src in book.get('sources',[]):add('sources',src['title'],'Earth reference used by the creators.','Research bibliography',src['url'])
    monsters=book.get('monsters',{});members={r for enc in encounters for r in enc.get('members',[])}
    locales=defaultdict(list)
    for r in rooms:
        if r['id'] in visible:
            for encounter in r.get('encounters',[]):locales[encounter].append(r['name'])
    encounters_by_npc=defaultdict(list)
    for enc in encounters:
        for rid in enc.get('members',[]):encounters_by_npc[rid].extend(locales.get(enc['id'],[]))
    for n in sorted(npcs,key=lambda r:r['name']):
        entry=monsters.get(n['id'])
        if not (entry or n['id'] in members or n.get('expedition_role') in ('predator','quarry') or
                n.get('social_profile',{}).get('sentient') is False):continue
        places=sorted(set(encounters_by_npc.get(n['id'],[])))
        site=visible.get(n.get('spawn_room')) or visible.get(n.get('location'))
        if site and site not in places:places.append(site)
        text=n.get('description','')
        if entry:text+=' '+entry['text']
        if places:text+=' Documented sites include '+', '.join(places[:4])+'.'
        elif not entry:text+=' The current survey gives no public sighting site.'
        add('monstorium',n['name'],text,entry['range']+' · '+entry['title'] if entry else 'Field identification')
    for title,txt in book.get('frontier',[]):add('knowledge',title,txt,'State of knowledge')
    archive['field_edition']=book['edition'];archive['volumes']=dict(records)
    archive['events'].sort(key=lambda e:e['at'])
    archive['register_rules']=book.get('register',{})
    archive['ambient_dialogue']=book.get('founding_residents',{}).get('ambient_lines',[])
    # Friends in the founding register share an actual workplace. Pair once, reciprocally.
    workers=defaultdict(list)
    for n in npcs:
        if n.get('work_room') in visible and n.get('social_profile',{}).get('sentient'):
            workers[n['work_room']].append(n['id'])
    friends={}
    for workplace,ids in sorted(workers.items()):
        ids.sort();family_seed(archive.get('population_seed',archive['seed']),workplace).shuffle(ids)
        for a,b in zip(ids[::2],ids[1::2]):friends[a]=b;friends[b]=a
    archive['founding_friends']=friends


def attach_book(archive,folder,rooms,npcs,groups,species,races,items,encounters):
    book=volume(folder)
    compile_volume(archive,book,rooms,npcs,groups,species,races,items,encounters)


def personal(world, player, archive, contacts, query):
    text_rows=[];rules=archive.get('register_rules')
    if not rules:return text_rows
    def put(name,title,txt):
        if query.casefold() in (name+' '+title+' '+txt).casefold():
            text_rows.append(dict(date=title,name=name,text=txt))
    relations=(getattr(world,'living_state',{}) or {}).get('relationships',{})
    parents={row['id']:row.get('parents',[]) for row in relations.get('children',[]) if row.get('id')}
    actors_by_source = {actor.source_def: actor.id for actor in world.entities.values()
                        if actor.source_def and not (actor.spawner_key or '').startswith('birth:')}
    for source, npc in world.npcs.items():
        authored = ((npc.get('founding_profile') or {}).get('parents') or
                    (npc.get('population_profile') or {}).get('biological_parent_source_ids') or [])
        if authored:
            actor_id = actors_by_source.get(source, 'npc:'+source)
            parents.setdefault(actor_id, [actors_by_source.get(k, 'npc:'+k) for k in authored])
    def who(ident):
        actor=world.entities.get(ident)
        if actor:return actor.name
        if ident in parents:return 'An untraced relative'
        n=world.npcs.get(str(ident).removeprefix('npc:'),{})
        return n.get('name','An untraced relative')
    by_bond=defaultdict(list)
    for bond in relations.get('bonds',{}).values():
        if not bond.get('kinds'):continue
        for a in bond.get('participants',[]):by_bond[a].append(bond)
    children=defaultdict(set)
    for child,ps in parents.items():
        for parent in ps:children[parent].add(child)
    for ident,record in contacts.items():
        key=record['source'];n=world.npcs.get(key,{});name=record['name']
        if not n.get('social_profile',{}).get('sentient'):continue
        actor=world.entities.get(ident)
        born_now=record.get('born') is not None or (actor and (actor.spawner_key or '').startswith('birth:'))
        first=parents.get(ident,[])
        if ident.startswith('template:'):
            first=parents.get('npc:'+key, first)
        # An authored biological link outranks a generated parish pedigree.
        authored=n.get('population_profile',{}).get('biological_parent_source_ids') or []
        if not first and authored:first=['npc:'+k for k in authored]
        if first:
            grandparents={g for a in first for g in parents.get(a,[])}
            kin={x for g in grandparents for x in children.get(g,())}-set(first)
            cousins={x for a in kin for x in children.get(a,())}
            for label,ids in [('Parents',first),('Grandparents',grandparents),('Aunts and uncles',kin),('Cousins',cousins)]:
                if ids:put(name,'Family register · '+label,', '.join(sorted(who(i) for i in ids))+'.')
            # A child born in play can trace back into a parent's earlier register.
            for parent_id in first:
                if parents.get(parent_id):
                    continue
                parent_actor = world.entities.get(parent_id)
                parent_key = parent_actor.source_def if parent_actor else str(parent_id).removeprefix('npc:')
                if parent_key not in world.npcs or (parent_actor and (parent_actor.spawner_key or '').startswith('birth:')):
                    continue
                kin_rows = registered_relatives(archive.get('population_seed',archive['seed']),world.npcs[parent_key],rules)
                for rel in kin_rows:
                    if rel['kin'] == 'Parent':
                        put(name,'Family register · Grandparent',rel['name']+' was '+rel['trade']+' and '+rel['trace']+'. Recorded through '+who(parent_id)+'.')
        elif not born_now:
            for person in registered_relatives(archive.get('population_seed',archive['seed']),n,rules):
                details=person['name']+' was '+person['trade']+' and '+person['trace']+'.'
                if person['years_before'] is not None:details+=' Born '+str(person['years_before'])+' world years before the founding survey.'
                if person['parents']:details+=' Recorded parentage: '+', '.join(person['parents'])+'.'
                put(name,'Founding family register · '+person['kin'],details)
        own=children.get('npc:'+key if ident.startswith('template:') else ident,())
        put(name,'Children in the register',', '.join(sorted(who(i) for i in own))+'.' if own else 'No child is recorded for this resident in the current civil register.')
        profile=n.get('founding_profile') or {}
        if profile and not born_now:
            put(name,('Age '+str(profile['age_at'])+' · ' if profile.get('age_at') is not None else 'Date unknown · ')+'Personal history',profile['event'])
            if profile.get('ambition'):put(name,'Hopes at the founding',profile['ambition'])
            for tie in profile.get('feelings',[]):
                other=world.npcs.get(tie['person'])
                if other:
                    label='Loved at the founding' if tie['kind']=='love' else 'Disliked at the founding'
                    put(name,label,other['name']+' ('+tie['relationship']+') '+tie['why']+'.')
            for influence in profile.get('influences',[]):
                title=influence['scope']+' history · Age '+str(influence['age'])
                put(name,title,influence['title']+'. '+influence['text'])
        occupation=n.get('occupation') or n.get('role')
        home=world.rooms.get(n.get('home_room'));work=world.rooms.get(n.get('work_room'))
        parts=[str(occupation).replace('_',' ').capitalize()+'.'] if occupation else []
        if home and home.map_visibility!='hidden':parts.append('Registered home: '+home.name+'.')
        if work and work.map_visibility!='hidden':parts.append('Place of work: '+work.name+'.')
        prefs=n.get('gift_preferences') or {}
        for field,label in [('wanted_items','Favours'),('disliked_items','Dislikes')]:
            names=[world.items[i]['name'] for i in prefs.get(field,[]) if i in world.items]
            if names:parts.append(label+' '+', '.join(names)+'.')
        if parts:put(name,'Work, household and tastes',' '.join(parts))
        testimony=family_seed(archive.get('population_seed',archive['seed']),ident if born_now else key)
        age=n.get('social_profile',{}).get('age_years')
        if not born_now and isinstance(age,(int,float)) and age>=18:
            opinions=testimony.choice(rules['opinions']);put(name,'Recorded personal opinion',opinions[0]+' and '+opinions[1]+'.')
        friend=archive.get('founding_friends',{}).get(key)
        if friend in world.npcs and not born_now:
            put(name,'Friendship at the founding',world.npcs[friend]['name']+' and '+name+' '+family_seed(archive.get('population_seed',archive['seed']),'/'.join(sorted((key,friend)))).choice(rules['ties'])+'.')
        for bond in by_bond.get(ident,[]):
            others=[who(i) for i in bond['participants'] if i!=ident]
            if others:put(name,'Current relationships',', '.join(others)+' · '+', '.join(bond['kinds'])+'.')
    return text_rows


def diplomatic_rows(world):
    rows=[]
    for group in world.groups.values():
        relations=group.get('relations') or {}
        if not group.get('start_room') or not relations:continue
        text=' '.join(world.groups[k]['name']+' — '+str(v)+'.' for k,v in relations.items() if k in world.groups)
        if text:rows.append(dict(name=group['name'],date='Current diplomatic register',text=text))
    return rows
