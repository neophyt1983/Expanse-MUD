"""Create one resident roster for a new adventure and replay that roster on load."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random

from engine import names


def make(folder, seed):
    folder = Path(folder)
    def read(file, default):
        path = folder / file
        return json.loads(path.read_bytes()) if path.is_file() else default
    people = read('npcs.json', [])
    groups = read('groups.json', [])
    rooms = {r['id']:r for r in read('rooms.json', [])}
    metadata = read('metadata.json', {})
    sexes=[row['id'] for row in read('sexes.json',[]) if row.get('id')]
    book = read('assets/chronicles/field-survey.json', {})
    material = book.get('founding_residents', {})
    items = {r['id'] for r in read('items.json', [])}
    rng = random.Random(int(seed))
    changes = {}
    additions = []
    used = {p.get('name', '') for p in people}
    by_group = defaultdict(list)
    pools = {g['id']:g.get('name_pool') for g in groups}
    seed_text = format(seed,'x')

    def new_name(pool, gender, key):
        first, last = names.pick(pool, gender, seed_text+'/'+key, used)
        used.add(first+' '+last)
        return dict(name=first+' '+last,first_name=first,last_name=last,name_mode='manual')

    def memories(age, home, job, place):
        if age is None:
            return dict(age_at=None,event='The register gives '+home+' as home. The date of the household entry is unknown.',ambition='',favourites=[],dislikes=[])
        if age<4:
            return dict(age_at=age,event='A caregiver at '+home+' recorded familiar faces and the sounds that drew the child’s attention.',ambition='',favourites=[],dislikes=[])
        if material:
            stage = 'youth' if age < 18 else 'elder' if age >= 60 else 'adult'
            episode, interest, dislike = rng.choice(material[stage])
            age_at = rng.randint(min(4,age),min(13,age)) if stage=='youth' else rng.randint(14,max(14,age-1))
            memory = episode.format(home=home,place=place)
            ambition = rng.choice(material['ambitions'][stage])
        else:
            age_at = max(0, age-2)
            memory = 'Was recorded in the household roll at '+home+'.'
            interest = dislike = None
            ambition = ''
        return dict(age_at=age_at,event=memory,ambition=ambition,
                    favourites=[interest] if interest in items else [],
                    dislikes=[dislike] if dislike in items else [])

    def experience(profile):
        bits = [profile['event'],profile['ambition']]
        account=' '.join(x for x in bits if x)
        return '“'+account+'”' if account.startswith('I ') else account
    for person in sorted(people,key=lambda row:row['id']):
        if person.get('social_profile',{}).get('sentient') is not True:
            continue
        group = person.get('group','')
        if person.get('home_room') in rooms and person.get('work_room') in rooms:
            by_group[group].append(person)
        pool = pools.get(group) or metadata.get('name_pool')
        if not pool or person.get('name_mode')!='faction':
            continue
        fields = new_name(pool, person.get('sex'),person['id'])
        age=person['social_profile'].get('age_years')
        age = max(0,int(age)) if isinstance(age,(int,float)) else None
        home=rooms.get(person.get('home_room')) or rooms.get(person.get('spawn_room')) or {}
        work=rooms.get(person.get('work_room')) or home
        bio=memories(age, home.get('name','the household'),person.get('occupation',''),work.get('name','the workplace'))
        fields['founding_profile']=bio
        if person.get('description'):
            fields['description']=person['description'].replace(person['name'],fields['name'])+' '+experience(bio)
        changes[person['id']]=fields
    for group in sorted(groups,key=lambda g:g['id']):
        gid=group['id']
        if group.get('start_room') not in rooms:continue
        pool=pools.get(gid) or metadata.get('name_pool')
        locals_=by_group[gid]
        if not pool or not locals_:continue
        household=rng.choice(locals_)
        home=household['home_room']
        mentor=rng.choice(locals_); work=mentor['work_room']
        family_id=sha256((seed_text+'/'+gid).encode()).hexdigest()[:16]
        # Founders span different generations. The pedigree is shared by all three biographies.
        shape=rng.randrange(3)
        middle=rng.randint(29,40)
        ages=([middle,middle+rng.randint(-3,5),rng.randint(7,13)] if shape==0 else
              [middle+rng.randint(24,35),middle,rng.randint(7,13)] if shape==1 else
              [middle+4,rng.randint(12,16),rng.randint(5,10)])
        parents=[[],[],[0,1]] if shape==0 else [[],[0],[1]] if shape==1 else [[],[0],[0]]
        ids=['resident_'+family_id+'_'+str(i) for i in range(3)]
        for index,(age,kin) in enumerate(zip(ages,parents)):
            uid=ids[index]
            sex=rng.choice(sexes) if sexes else None
            fields=new_name(pool, sex,uid)
            if sex:fields['sex']=sex
            place=home if age<18 else work
            job='student' if age<18 else mentor.get('occupation','worker')
            bio=memories(age,rooms[home]['name'],job,rooms[place]['name'])
            bio['parents']=[ids[i] for i in kin]
            # Family records use identifiers and allow new children during play.
            description=experience(bio)
            schedule=[dict(hour=0,room=home,activity='sleeping'),dict(hour=7,room=place,activity='learning' if age<18 else 'working'),
                      dict(hour=18,room=home,activity='spending time with family')]
            resident=dict(id=uid,**fields,role='resident',occupation=job,group=gid,
                          description=description,home_room=home,work_room=place,spawn_room=home,
                          location=home,disposition='friendly',hp=20,attack=2,defense=2,gold=0 if age<18 else rng.randint(3,15),
                          social_profile=dict(sentient=True,age_years=age,autonomous=age>=3),schedule=schedule,founding_profile=bio,
                          gift_preferences=dict(wanted_items=bio['favourites'],disliked_items=bio['dislikes']))
            if mentor.get('race'):resident['race']=mentor['race']
            additions.append(resident)
    if material.get('ties'):
        # Name people once, then link biographies to real, contemporary neighbours.
        # Family ties may extend across a generation. Other ties require a shared place.
        roster = {n['id']:{**n,**changes.get(n['id'],{})} for n in [*people,*additions]
                  if n.get('social_profile',{}).get('sentient')}
        home_members = defaultdict(list)
        coworkers = defaultdict(list)
        relatives = defaultdict(list)
        for uid, n in roster.items():
            if n.get('home_room'):home_members[n['home_room']].append(uid)
            if n.get('work_room'):coworkers[n['work_room']].append(uid)
            for parent in n.get('founding_profile',{}).get('parents',[]):
                relatives[parent].append(uid)
                relatives[uid].append(parent)
        def years_old(n):
            age=n.get('social_profile',{}).get('age_years')
            return int(age) if isinstance(age,(int,float)) and age>=0 else None
        additions_ids={n['id'] for n in additions}
        addition_rows={n['id']:n for n in additions}
        for uid,n in sorted(roster.items()):
            age=years_old(n)
            place=rooms.get(n.get('home_room')) or rooms.get(n.get('location')) or {}
            work=rooms.get(n.get('work_room')) or place
            profile=n.get('founding_profile')
            if not profile:
                profile=memories(age,place.get('name','home'),n.get('occupation',''),work.get('name','work'))
            contacts=list(dict.fromkeys([*home_members[n.get('home_room')],*coworkers[n.get('work_room')]]))
            contacts=[v for v in contacts if v!=uid]
            loves=relatives[uid] or contacts
            loved=rng.choice(loves) if loves else None
            likes=[]
            def tie(kind,other):
                why,line=rng.choice(material['ties'][kind])
                family=other in relatives[uid]
                # Very young children have attachments, with memories reported by a caregiver.
                if age is not None and age<4:why='has been a familiar presence at home';line='{first} is here.'
                return dict(kind=kind,person=other,why=why,line=line,
                            relationship='family' if family else 'personal affection' if kind=='love' else 'personal grievance')
            if loved:likes.append(tie('love',loved))
            others=[i for i in contacts if i!=loved and i not in relatives[uid]]
            if age is not None and age>=5 and others:likes.append(tie('dislike',rng.choice(others)))
            profile['feelings']=likes
            influence=[];gid=n.get('group');here=material.get('local',{}).get(gid)
            if here and age is not None and age>=3:
                since=3;then=age-since
                if then>=3:
                    influence.append(dict(scope='Local',years=since,age=then,title=here[0],text=here[1]+' '+here[2],voice=here[2]))
            if age is not None and age>=7:
                for scope,available in [
                    ('National',[(8,'A public reading of the household rolls',book['states'][gid]['debate'])] if gid in book.get('states',{}) else []),
                    ('International',[(years,title,account) for years,a,b,title,account in book.get('treaties',[]) if gid in (a,b)])]:
                    eligible=[e for e in available if age-e[0]>=7]
                    if not eligible:continue
                    years,title,account=rng.choice(eligible);then=age-years
                    stage='child' if then<12 else 'adolescent' if then<18 else 'adult'
                    reaction=rng.choice(material['civic_responses'][stage])
                    influence.append(dict(scope=scope,years=years,age=then,title=title,text=account+' '+reaction,voice=reaction))
            profile['influences']=influence
            if uid in additions_ids:addition_rows[uid]['founding_profile']=profile
            else:changes.setdefault(uid,{})['founding_profile']=profile
    return dict(version=1,seed=seed_text,changes=changes,additions=additions)


def apply(folder, roster):
    folder=Path(folder)
    path=folder/'npcs.json'
    people=json.loads(path.read_bytes()) if path.is_file() else []
    ids={n['id'] for n in people}
    for person in people:
        change=roster['changes'].get(person['id'])
        if not change:continue
        person.update(change)
        prefs=person.setdefault('gift_preferences',{})
        profile=change['founding_profile']
        for key,source in [('wanted_items','favourites'),('disliked_items','dislikes')]:
            prefs[key]=list(dict.fromkeys([*prefs.get(key,[]),*profile[source]]))
        prefs['disliked_items']=[i for i in prefs['disliked_items'] if i not in prefs['wanted_items']]
    people.extend(n for n in roster['additions'] if n['id'] not in ids)
    if roster['changes'] or roster['additions']:
        path.write_text(json.dumps(people,ensure_ascii=False,separators=(',',':'))+'\n')
    index_path=folder/'assets/chronicles/resident-references.json'
    if index_path.is_file():
        import re
        index=json.loads(index_path.read_bytes())
        for catalog,entries in index.items():
            if catalog not in ('quests','items','recipes','npcs','rooms','resources','interactions','encounters','abilities','species'):continue
            source=folder/(catalog+'.json')
            if not source.is_file():continue
            rows=json.loads(source.read_bytes())
            for record in rows:
                for key,refs in entries.get(record['id'],{}).items():
                    if not isinstance(record.get(key),str):continue
                    replacements={old:roster['changes'][uid]['name'] for old,uid in refs.items() if roster['changes'].get(uid,{}).get('name')}
                    if replacements:
                        pattern=r'(?<!\w)(?:'+'|'.join(map(re.escape,sorted(replacements,key=len,reverse=True)))+r')(?!\w)'
                        record[key]=re.sub(pattern,lambda match:replacements[match[0]],record[key])
            source.write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n')
    meta_path=folder/'metadata.json'
    metadata=json.loads(meta_path.read_bytes())
    metadata['resident_seed']=roster['seed']
    meta_path.write_text(json.dumps(metadata,ensure_ascii=False,separators=(',',':'))+'\n')
