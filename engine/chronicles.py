"""An adventure's founding archive and its read-only, viewer-scoped timelines."""
import hashlib
import json
import random
from pathlib import Path
from engine import geology, history_templates, world_history, worldtime

ARCHIVE = 'chronicles.json'
YEAR = worldtime.MINUTES_PER_YEAR
LABELS = {'geology':'Geology · Deep time','civilization':'Civilization · Medium time','individual':'Individuals · Recent time', 'natural':'Natural history and peoples', 'monstorium':'Monstorium', 'knowledge':'Frontiers of knowledge', 'sources':'Research bibliography'}
STRATA = {
    'collision_range':(8_000_000, 100_000_000, 'Colliding plates raised a mountain belt.'),
    'eroded_range':(2_000_000, 40_000_000, 'Erosion wore down an older mountain range, leaving exposed ridges.'),
    'volcano':(80_000, 1_200_000, 'Successive eruptions built a volcanic summit.'),
    'lava_field':(20_000, 160_000, 'Lava spread across the low ground and hardened into a field of rock.'),
    'cooled_lava':(10_000, 120_000, 'A lava flow cooled into a new bed of rock.'),
    'lava_tube':(5_000, 100_000, 'A cooling lava flow drained beneath its crust, leaving a passage.'),
    'kimberlite_pipe':(10_000_000, 140_000_000, 'An eruption carried kimberlite upward through a volcanic pipe.'),
    'lamproite_pipe':(10_000_000, 140_000_000, 'An eruption opened a lamproite pipe through older rock.'),
    'alluvial':(8_000, 280_000, 'Running water laid down successive beds of gravel, sand, and silt.'),
}
LIFE = {'birth':'Was born.', 'infancy_ended':'Reached early childhood.', 'adolescence':'Entered adolescence.',
        'adulthood':'Reached adulthood.', 'elder_life_stage':'Entered elder life.', 'child_born':'Became a parent.',
        'work_started':'Began working.', 'campaign_start':'Was living here when the adventure began.',
        'experienced_world_event':'Witnessed a recorded historical event.'}
CIVIC = {'trade':'opened trade', 'dispute':'entered a dispute', 'treaty':'signed a treaty',
         'war_started':'went to war', 'war_ended':'made peace'}


def read_object(folder, name):
    path=Path(folder)/name
    if not path.exists():return {}
    if path.is_symlink() or path.stat().st_size>history_templates.MAX_FILE:
        raise ValueError('Invalid history file: '+name)
    data=history_templates._json(path.read_bytes(),name)
    if not isinstance(data,dict):raise ValueError('Expected an object in '+name)
    return data


def generate(rooms, npcs, groups, species, metadata, seed, rules, published):
    plan=rules.get('history_plan') or {}
    now=plan.get('present_minute',worldtime.initial_minute(metadata))
    seed=plan.get('seed',seed)
    declared=list(plan.get('events',[]))
    events=[]
    def add(domain,at,text,place=None):
        events.append(dict(domain=domain,at=at,text=text,place=place))
    def rng(key):
        return random.Random(hashlib.sha256(f'{seed}/{key}'.encode()).digest())
    group_names={g['id']:g.get('name',g['id']) for g in groups}
    room_ids={r['id'] for r in rooms}
    for e in declared:
        if e.get('domain') not in ('geology','civilization'):continue
        place=next(iter(e.get('rooms',[])),None)
        title=e.get('description') or e.get('title') or e.get('name') or e['kind'].replace('_',' ').capitalize()+'.'
        if e.get('group') in group_names:title=group_names[e['group']]+' — '+title
        add(e['domain'],e['at'],title,place)
    if not any(e['domain']=='geology' for e in events):
        strata={}
        for room in rooms:
            land=geology.descriptor(room.get('geology',{})).get('landform')
            if land:
                key=(land, room.get('world_region') or '')
                strata.setdefault(key,[]).append(room['id'])
        for (land,region),places in sorted(strata.items()):
            low,high,story=STRATA[land]
            stream=rng(land+region)
            add('geology',now-stream.randint(low,high)*YEAR,story,stream.choice(sorted(places)))
    for e in published.get('events',[]):
        if e.get('kind') in CIVIC and e.get('parties') and all(g in group_names for g in e['parties']):
            add('civilization',e['at'],' and '.join(group_names[g] for g in e['parties'])+' '+CIVIC[e['kind']]+'.')
    if not any(e['domain']=='civilization' for e in events):
        for group in groups:
            hall=group.get('start_room')
            if hall not in room_ids or group.get('visibility') in ('hidden','npc_only'):continue
            stream=rng(group['id'])
            name=group_names[group['id']]
            add('civilization',now-stream.randint(90,480)*YEAR,f'{name} established a permanent settlement.',hall)
            milestone=stream.choice(('commissioned a survey of its settled lands.',
                                     'established an archive for its civic records.',
                                     'adopted a common calendar for its settlements.'))
            add('civilization',now-stream.randint(12,75)*YEAR,name+' '+milestone,hall)
    # Reuse the age and kinship compiler. No generated proposals change a playing character.
    data={'room':[{'id':r['id']} for r in rooms],'npc':npcs,'group':groups,'species':species}
    try:
        compiled=world_history.compile_history(data,dict(seed=seed,present_minute=now,events=declared))
        people=compiled['actors']
    except world_history.HistoryError:
        # A playable Creator world may not have compatible parent epochs. Retain
        # its dated records without making unresolved family links historical facts.
        people={}
        for n in npcs:
            entry={**n,'population_profile':{**(n.get('population_profile') or {}),'biological_parent_source_ids':[],'current_partner_source_id':None}}
            try:
                one=world_history.compile_history({'npc':[entry],'species':species},dict(seed=seed,present_minute=now,events=[]))
            except world_history.HistoryError:continue
            people.update(one['actors'])
    life={}
    for key,profile in people.items():
        if not isinstance(profile,dict):continue
        for e in profile.get('events',[]):
            if not isinstance(e,dict) or type(e.get('at')) is not int:continue
            if e.get('private') or e.get('public') is False:continue
            # Creator-written biographies are private unless a milestone is public.
            label=LIFE.get(e.get('kind'))
            if e.get('public') is True:label=e.get('description') or e.get('title') or label
            if label:
                life.setdefault(key,[]).append({'at':e['at'],'text':label})
    published_workers={e.get('actor') for e in published.get('events',[]) if e.get('kind')=='work_started'}
    for npc in npcs:
        key=npc['id'];bio=people.get(key,{})
        born=bio.get('born_minute') if isinstance(bio,dict) else None
        if type(born) is not int or key in published_workers or not npc.get('occupation') or not npc.get('work_room'):continue
        from engine import life_stages
        sp=(npc.get('social_profile') or {}).get('species')
        limits=life_stages.resolve_profile(sp,next((r for r in species if r['id']==sp),None))
        earliest=born+round(limits['work_start_years']*YEAR)
        if earliest<=now:
            at=rng('work/'+key).randint(earliest,now)
            life.setdefault(key,[]).append({'at':at,'text':'Began working in the settlement ('+npc['occupation'].replace('_',' ')+').'})
    for e in published.get('events',[]):
        if e.get('kind')=='work_started' and e.get('actor') in people:
            life.setdefault(e['actor'],[]).append({'at':e['at'],'text':LIFE['work_started']})
    return {'version':1,'seed':seed,'present':now,'events':sorted(events,key=lambda e:e['at']),'people':life}


def create(pending, seed):
    if (pending/ARCHIVE).exists():
        archived=read_object(pending,ARCHIVE)
        seed_text=read_object(pending,'metadata.json').get('resident_seed')
        if seed_text and archived.get('population_seed')!=seed_text:
            archived['population_seed']=seed_text
            archived.pop('field_edition',None)
            (pending/ARCHIVE).write_text(json.dumps(archived,ensure_ascii=False,separators=(',',':'))+'\n')
        return
    from editor.cli import FILE_MAP
    def rows(kind):
        path=pending/FILE_MAP[kind]
        return json.loads(path.read_text()) if path.exists() else []
    records=generate(rows('room'),rows('npc'),rows('group'),rows('species'),read_object(pending,'metadata.json'),seed,read_object(pending,'history-rules.json'),read_object(pending,'history.json'))
    from engine import field_archive
    records['population_seed']=read_object(pending,'metadata.json').get('resident_seed',records['seed'])
    field_archive.attach_book(records,pending,rows('room'),rows('npc'),rows('group'),rows('species'),rows('race'),rows('item'),rows('encounter'))
    (pending/ARCHIVE).write_text(json.dumps(records,ensure_ascii=False,separators=(',',':'))+'\n')


def legacy_seed(name):
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8],'big')


def attach(w):
    if hasattr(w,'chronicles'):return w.chronicles
    folder=getattr(w,'game_dir',None)
    if not folder:return {}
    archive=read_object(folder,ARCHIVE)
    if archive and archive.get('version')!=1:raise ValueError('Unsupported world chronicle version.')
    if not archive:
        seed=legacy_seed(Path(folder).name)
        archive=generate(list(w.room_details.values()),list(w.npcs.values()),list(w.groups.values()),
                         list(getattr(w,'species',{}).values()),w.metadata,seed,read_object(folder,'history-rules.json'),read_object(folder,'history.json'))
        archive['reconstructed']=True
    from engine import field_archive
    if getattr(w,'game_dir',None):
        field_archive.attach_book(archive,folder,list(w.room_details.values()),list(w.npcs.values()),
                                  list(w.groups.values()),list(getattr(w,'species',{}).values()),
                                  list(getattr(w,'races',{}).values()),list(w.items.values()),list(getattr(w,'encounters',{}).values()))
    w.chronicles=archive
    return archive


def meet(w,p):
    known=p.progress.setdefault('chronicle_contacts',{})
    for e in w.entities_in_room(p.location):
        if e.is_player or not e.source_def:continue
        source=w.npcs.get(e.source_def,{})
        if not (source.get('social_profile',{}).get('sentient') or source.get('history_profile')):continue
        born=e.progress.get('social_profile',{}).get('born_minute') if (e.spawner_key or '').startswith('birth:') else None
        known[e.id]=dict(name=e.name,source=e.source_def,born=born)
    return known


def date_text(at,now):
    if at<now:
        years=(now-at)//YEAR
        if years:return f'{years:,} world year'+('s' if years!=1 else '')+' before the start'
        days=(now-at)//worldtime.MINUTES_PER_DAY
        return f'{days} day'+('s' if days!=1 else '')+' before the start' if days else 'Before the start'
    d=worldtime.date(at)
    return f"Year {d['year']}, month {d['month']}, day {d['day']}"


def page(w,p,section='geology',query='',number=1,*,all_people=False):
    if section not in LABELS:raise ValueError('Choose a section from World chronicles.')
    archive=attach(w)
    now=archive.get('present',worldtime.initial_minute(w.metadata))
    known=set(p.explored_rooms)|{p.location}|set(p.progress.get('knowledge',{}).get('rooms',[]))
    from engine import field_archive
    if section in field_archive.SECTIONS:
        entries=[r for r in archive.get('volumes',{}).get(section,()) if query.casefold() in (r['name']+' '+r['text']+' '+r['date']).casefold()]
        return paginate(section,archive,entries,number,4 if section!='sources' else 12)
    rows=[]
    def row(at,name,text):
        if query.casefold() in (name+' '+text).casefold():rows.append((at,name,text))
    if section=='individual':
        contacts=dict(meet(w,p));sources={item['source'] for item in contacts.values()}
        if all_people:
            for e in w.entities.values():
                if e.is_player or not e.source_def:continue
                born=e.progress.get('social_profile',{}).get('born_minute') if (e.spawner_key or '').startswith('birth:') else None
                contacts[e.id]=dict(name=e.name,source=e.source_def,born=born);sources.add(e.source_def)
            for key in archive.get('people',{}):
                if key in w.npcs and key not in sources:
                    contacts['template:'+key]=dict(name=w.npcs[key]['name'],source=key,born=None)
        for person in contacts.values():
            if person.get('born') is not None:
                row(person['born'],person['name'],'Was born during this adventure.')
            else:
                for e in archive.get('people',{}).get(person['source'],[]):
                    row(e['at'],person['name'],e['text'])
        rows.sort(key=lambda r:(r[1].casefold(),r[0]))
    else:
        for e in archive.get('events',[]):
            if e['domain']!=section:continue
            rid=e.get('place')
            place=w.rooms[rid].name if rid in w.rooms and (all_people or rid in known) else ''
            row(e['at'],e.get('heading') or place,e['text'])
        if section=='civilization':
            places=getattr(w,'room_details',{})
            for rid in (places.keys() if all_people else known):
                story=places.get(rid,{}).get('city_tradition')
                if isinstance(story,str) and story and rid in w.rooms:
                    row(None,w.rooms[rid].name,story)
        rows.sort(key=lambda r:(r[0] is None,r[0] or 0,r[1]))
    entries=[dict(date='Local tradition · date unrecorded' if at is None else date_text(at,now),name=name,text=text) for at,name,text in rows]
    if section=='individual':
        extra=field_archive.personal(w,p,archive,contacts,query)
        entries=sorted(entries+extra,key=lambda r:r['name'].casefold())
    if section=='civilization' and archive.get('field_edition'):
        entries.extend(r for r in field_archive.diplomatic_rows(w) if query.casefold() in (r['name']+' '+r['text']).casefold())
    return paginate(section,archive,entries,number,4 if archive.get('field_edition') else 12)


def paginate(section,archive,entries,number,size):
    total=max(1,(len(entries)+size-1)//size);number=max(1,min(total,number))
    return dict(section=section,title=LABELS[section],page=number,pages=total,total=len(entries),
                origin=archive.get('field_edition') or ('Reconstructed prehistory' if archive.get('reconstructed') else 'Founding archive'),
                editions=list(LABELS) if archive.get('field_edition') else ['geology','civilization','individual'],
                entries=entries[(number-1)*size:number*size])


def command(ctx,args):
    words=args.strip().split()
    if not words:return 'World histories · history geology · history civilization · history individual [name] · history natural [species] · history monstorium [creature] · history knowledge · history sources. Open Chronicles in the Conversation commands to browse.'
    section=words.pop(0).casefold()
    number=int(words.pop()) if words and words[-1].isascii() and words[-1].isdigit() and len(words[-1])<=6 else 1
    data=page(ctx.world,ctx.player,section,' '.join(words),number)
    lines=[data['title']+' · '+data['origin']]
    for e in data['entries']:lines.append(' · '.join(x for x in (e['date'],e['name'],e['text']) if x))
    if not data['entries']:lines.append('No matching records. Meet a resident to discover their history.' if section=='individual' else 'No matching records in this world.')
    lines.append(f"Page {data['page']} of {data['pages']}")
    return '\n'.join(lines)
