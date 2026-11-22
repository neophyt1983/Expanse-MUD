"""Author eight city co-operatives from the exact Founding Cities register."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

BASE = 'f14377c737e936fb8341bee563e0a94b40a9ec63d07c19f9d3035e8292f6ede8'
ROLES = {'grower': 'growers', 'kitchen worker': 'cooks', 'market porter': 'porters'}


def build(source, destination):
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE:
        raise ValueError("Select the original Founding Cities release world.")
    with ZipFile(source) as archive:
        def read(name):
            return json.loads(archive.read(name + '.json'))
        metadata, manifest, rooms, items = map(read, ('metadata', 'manifest', 'rooms', 'items'))
        by_room = {r['id']: r for r in rooms}
        facilities = metadata['city_population_198']['facilities']
        cities = {}
        for name in sorted(n for n in archive.namelist() if n.startswith('assets/chronicles/genesis-')):
            register = json.loads(archive.read(name))
            city = register['city']
            prefix = 'gen_' + name.rsplit('-', 1)[1].split('.')[0]
            member_prefix = prefix + '_person_'
            register_rows = [r for r in register['residents'] if not r['authored']]
            if {r['id'] for r in register_rows} != {member_prefix + str(i) for i in range(1, len(register_rows) + 1)}:
                raise ValueError('Register IDs changed in ' + city)
            jobs = {role: [] for role in ROLES.values()}
            for r in register_rows:
                role = ROLES.get(r['occupation'])
                if role and (r['entry_kind'] != 'birth' or -r['entry_day'] >= 18 * 208):
                    jobs[role].append(int(r['id'][len(member_prefix):]))
            f = facilities[city]
            garden = by_room[f['garden']]
            field = prefix + '_allotments'
            if field in by_room or 'allotments' in garden['exits']:
                raise ValueError('Allotment route already exists in ' + city)
            garden['exits']['allotments'] = field
            sign = prefix + '_provision_board'
            room = dict(id=field, name=city + ' Co-operative Allotments', group=garden['group'],
                        location=field, exits={'back': f['garden']}, items=[sign], facilities=['farm'],
                        description="Long strips of carrots, onions and potatoes surround the packing shed. "
                                    "Numbered beds belong to the household co-operative. Read the provision board "
                                    "or type provisions to see the latest harvest, meals and market deliveries.")
            for key in ('planet', 'climate'):
                if key in garden:
                    room[key] = garden[key]
            rooms.append(room)
            items.append(dict(id=sign, name='Provision Board', type='book', value=0, location=field,
                              description='The co-operative posts its daily accounts here.',
                              read_text="Households collect two portions per resident at 15:00 each game day. "
                                        "Growers rotate the beds, cooks turn the crop into stew, and market porters "
                                        "distribute the portions. Type provisions to read the current account."))
            cities[city] = dict(field=field, kitchen=f['inn'], market=f['market'], garden=f['garden'],
                                member_prefix=member_prefix, member_count=len(register_rows), workforce=jobs,
                                planting_beds=64*len(jobs['growers']), beds_per_grower=64, rotation_days=4,
                                seasonal_yield_percent={'spring': 100, 'summer': 100, 'autumn': 100, 'winter': 75},
                                crop_batch={'lw_carrot': 1, 'lw_onion': 1, 'lw_potato': 1},
                                recipe='lw_stew', meal_item='lw_stew', batches_per_cook=16,
                                servings_per_porter=16, daily_portions=2, store_days=4)
        metadata['household_provisions'] = dict(version=1, issue_minute=900, cities=cities)
        metadata['content_revision'] = manifest['content_revision'] = '1.10.0-rc4'
        manifest['slug'] = 'wild_lands_genesis_rc4'
        manifest['counts'].update(rooms=len(rooms), items=len(items))
        new = {n+'.json': json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
               for n, v in [('metadata',metadata),('manifest',manifest),('rooms',rooms),('items',items)]}
        with ZipFile(destination, 'w') as out:
            for name in sorted(archive.namelist()):
                info = ZipInfo(name, date_time=(2026,11,22,0,0,0))
                info.compress_type = ZIP_DEFLATED
                out.writestr(info, new[name] if name in new else archive.read(name))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
