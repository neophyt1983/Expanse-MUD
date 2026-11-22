"""Build a reproducible municipal opening from the pinned Wild Lands civic preview."""
import argparse
import hashlib
import json
import random
import tempfile
import zipfile
from pathlib import Path

CITIES = {
    'Dawnwatch': ('dawn', 'Orchard', 'fruit grower'),
    'Hollowcrown': ('hollow', 'Lantern', 'lamp maker'),
    'Hearthmere': ('hearth', 'Hearth', 'gardener'),
    'Reedwater': ('reed', 'Towpath', 'boatwright'),
    'Cinderhold': ('cinder', 'Kiln', 'potter'),
    'Glassreach': ('glass', 'Glazier', 'glassworker'),
    'Pinewatch': ('pine', 'Timber', 'carpenter'),
    'Starfall': ('star', 'Survey', 'surveyor'),
}
TARGET = 3000
YEAR = 208
DAY_MINUTES = 1500


def packed(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write_member(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 22, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def home_city(room, short, city, inn):
    return isinstance(room, str) and (room == inn or room.startswith((
        'ward_'+short+'_', 'fw_'+short+'_', 'civic_'+city.lower()+'_',
    )) or (room.startswith('lw_'+short+'_') and not room.startswith((
        'lw_'+short+'_wild_', 'lw_'+short+'_archive_',
    ))) or (short == 'dawn' and room in ('emberhollow_square','emberhollow_inn_kitchen')))


def generate(source, output, seed):
    with zipfile.ZipFile(source) as src:
        read = lambda name: json.loads(src.read(name+'.json'))
        meta, manifest = read('metadata'), read('manifest')
        if meta.get('municipal_genesis') or meta.get('civic_opening_release') != '1.10.0-rc1':
            raise ValueError('Select the original Civic Opening Preview world')
        rooms, people, items, buildings = map(read, ('rooms','npcs','items','buildings'))
        room_index = {r['id']:r for r in rooms}
        facilities = meta['city_population_198']['facilities']
        if set(facilities) != set(CITIES):
            raise ValueError('Municipal facility list differs from the Wild Lands input')
        archive = {}
        report = {}
        registry = set()
        for city, (short, district_name, trade) in CITIES.items():
            rng = random.Random(f'genesis-v1/{seed}/{city}')
            f = facilities[city]
            if not all(f[k] in room_index for k in ('garden','workshop','market','inn','library')):
                raise ValueError(f'{city} lacks an opening facility')
            natives = sorted((p for p in people if p.get('social_profile',{}).get('sentient') is True
                              and p.get('home_room') in room_index
                              and home_city(p.get('home_room'),short,city,f['inn'])),key=lambda p:p['id'])
            if not 1 <= len(natives) < TARGET:
                raise ValueError(f'{city} needs an audited founding cohort')
            rng.shuffle(natives)
            pool = meta['name_pool']
            records, history = [], []
            # A charter grants land and communal labor, not spendable currency.
            # Settlement pace and the founding date are derived together so the
            # last already-scheduled admission falls on the common opening day.
            intervals = [rng.randint(2,8) for _ in range(TARGET-1)]
            day = -sum(intervals)
            founding = day
            # Generated charter reserves are expressed in frame kits. A city
            # exhausts its grant if plots are expanded beyond its surveyed land.
            reserve = 720
            last_build_day = day
            households = {}
            used = set()
            lanes = []
            capacity = 0
            material = 0
            production = 0
            consumed = 0
            anchor = f['market']
            for i in range(TARGET):
                if i:
                    day += intervals[i-1]
                if i < len(natives):
                    n = natives[i]
                    rec = dict(id=n['id'],name=n['name'],home=n['home_room'],
                               work=n.get('workplace_room') or f['market'],
                               occupation=n.get('occupation') or 'resident',authored=True)
                else:
                    index = i-len(natives)
                    if index == capacity:
                        # New frontage is surveyed and built before admission.
                        # Materials are measured in house-frame kits assembled
                        # from in-kind deliveries by the construction cooperative.
                        plots = 16
                        kits = plots
                        foreperson = records[rng.randrange(len(records))]['id']
                        if reserve < kits or day-last_build_day < plots:
                            raise ValueError(f'{city} lacks time or material for its next court')
                        reserve -= kits
                        last_build_day = day
                        material += kits
                        production += kits
                        number = len(lanes)+1
                        rid = f'gen_{short}_lane_{number}'
                        if rid in room_index:
                            raise ValueError(f'Generated room collision: {rid}')
                        parent = room_index[anchor]
                        direction = 'housing lane' if not lanes else 'onward'
                        if direction in parent['exits']:
                            raise ValueError(f'Occupied frontage at {anchor}')
                        parent['exits'][direction] = rid
                        lane = dict(id=rid,name=f'{city} {district_name} Court {number}',
                                    description=f'Sixteen row houses face a shared courtyard. Read the Court Roll for names and door numbers. Use knock followed by a door number to meet a household member.',
                                    exits={'back':anchor},items=[],spawners=[],facilities=[],
                                    group=room_index[f['market']].get('group'),location=rid)
                        rooms.append(lane);room_index[rid]=lane
                        name = f'{district_name} housing cooperative'
                        history.append(dict(day=day,kind='construction',site=rid,builder=foreperson,
                                            institution=name,source='in-kind house-frame delivery',
                                            kits_received=kits,kits_used=plots,reserve_remaining=reserve,beds_added=plots*4))
                        material -= plots
                        consumed += plots
                        buildings.append(dict(id=rid+'_homes',name=lane['name']+' Row Houses',
                                              rooms=[rid],location=rid,description=lane['description']))
                        lanes.append(lane)
                        anchor=rid
                        capacity+=plots*4
                    house=index//4
                    uid=f'gen_{short}_person_{index+1}'
                    family = pool['family'][house%len(pool['family'])]
                    given=rng.choice(pool[rng.choice(('male','female','neutral'))])
                    name=f'{given} {family}'
                    relatives=households.get(f'{short}_house_{house+1}',[])
                    occupied={member['name'] for member in relatives}
                    if name in occupied:
                        name=next(f'{given} {middle} {family}' for middle in pool['neutral']
                                  if f'{given} {middle} {family}' not in occupied)
                    work,occupation=rng.choice(((f['garden'],'grower'),(f['workshop'],trade),
                                                (f['market'],'market porter'),(f['inn'],'kitchen worker')))
                    rec=dict(id=uid,name=name,home=lanes[-1]['id'],door=house%16+1,
                             household=f'{short}_house_{house+1}',work=work,occupation=occupation,authored=False)
                    if index%64==0:
                        # One ordinary game NPC at the first occupied house on
                        # each court lets visitors speak to a real local resident.
                        people.append(dict(id=uid,name=name,hp=22,attack=2,defense=1,gold=0,
                                           occupation=occupation,location=rec['home'],home_room=rec['home'],spawn_room=rec['home'],
                                           workplace_room=work,group=lanes[-1]['group'],inventory=[],
                                           social_profile=dict(sentient=True),description=f'{name} works as a {occupation} in {city}.',
                                           greetings={lanes[-1]['group']:f'My household lives here. You can read the court roll to find our neighbors.'}))
                if rec['id'] in registry:
                    raise ValueError(f'Duplicate municipal identity {rec["id"]}')
                registry.add(rec['id']);used.add(rec['id'])
                rec['entry_day']=day
                rec['entry_kind']='founder' if not records else 'immigration'
                if not rec['authored']:
                    household=households.setdefault(rec['household'],[])
                    if len(household)>=2 and rng.random()<0.55:
                        rec['entry_kind']='birth'
                        rec['parents']=[household[0]['id'],household[1]['id']]
                    household.append(rec)
                records.append(rec)
            if len(used)!=TARGET or day!=0 or material or production!=consumed:
                raise ValueError(f'{city} failed publication checks')
            for lane in lanes:
                local=[r for r in records if r['home']==lane['id']]
                archive['assets/chronicles/'+lane['id']+'.json']=packed(local)
                bid=lane['id']+'_roll'
                lane['items'].append(bid)
                items.append(dict(id=bid,name='Court Roll',type='book',value=0,location=lane['id'],
                                  description='A door-by-door roll of this court at the opening census.',
                                  read_text='\n'.join(f"Door {r['door']}: {r['name']}, {r['occupation']}." for r in local)))
            book='gen_'+short+'_chronicle'
            room_index[f['library']].setdefault('items',[]).append(book)
            items.append(dict(id=book,name=city+' Founding Register',type='book',value=0,location=f['library'],
                              description='A record of settlement and construction.',
                              read_text=f'{city} opened its register {abs(founding)} days before the common census. '
                                        f'At 06:15 it counted {len(records):,} residents.\n'+'\n'.join(
                                            f"{abs(e['day'])} days before opening: {room_index[e['site']]['name']} completed."
                                            for e in history)))
            archive[f'assets/chronicles/genesis-{short}.json']=packed(dict(city=city,seed=seed,
                opening_minute=375,founding_day=founding,residents=records,construction=history))
            report[city]=dict(residents=len(records),authored=len(natives),courts=len(lanes),
                              occupied_new_houses=(TARGET-len(natives)+3)//4,founding_day=founding)
        meta.update(name='Wild Lands — Founding Cities',start_minute=375,municipal_genesis=dict(version=1,seed=seed,cities=report))
        manifest.update(name=meta['name'],slug='wild_lands_genesis')
        for key,rows in [('rooms',rooms),('npcs',people),('items',items),('buildings',buildings)]:
            manifest['counts'][key]=len(rows)
            archive[key+'.json']=packed(rows)
        archive.update({'manifest.json':packed(manifest),'metadata.json':packed(meta)})
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as temp:
            tmp=Path(temp.name)
        try:
            with zipfile.ZipFile(tmp,'w') as dst:
                for name in sorted(set(src.namelist())|archive.keys()):
                    write_member(dst,name,archive[name] if name in archive else src.read(name))
            tmp.replace(output)
        finally:
            tmp.unlink(missing_ok=True)
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--seed',type=int,default=20261122)
    args=parser.parse_args()
    if args.source.resolve()==args.output.resolve():parser.error('Choose a separate output archive')
    print(json.dumps(generate(args.source,args.output,args.seed),indent=2))
