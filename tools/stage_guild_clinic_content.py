#!/usr/bin/env python3
"""Compose task guilds and staffed care into the supplied 1.9.16 world.

``apply(data, metadata)`` mutates plural in-memory catalogs and returns a report.
The CLI always copies to a new staging directory. Original worlds are inputs,
never outputs. Applying twice is idempotent and never replenishes a live save.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PATCH = 'task_guilds_clinics_v1'
HOSPITAL = {
    'guild_dawn_hospital_reception': (-2, -5, 1, 'Dawnwatch Hospital Reception'),
    'guild_dawn_hospital_treatment': (-1, -5, 1, 'Dawnwatch Hospital Treatment Room'),
    'guild_dawn_hospital_ward': (-2, -4, 1, 'Dawnwatch Hospital Recovery Ward'),
    'guild_dawn_hospital_dispensary': (-1, -4, 1, 'Dawnwatch Hospital Dispensary'),
}


def _unique(values):
    return list(dict.fromkeys(values))


def apply(data, metadata):
    markers = metadata.get('content_patches', {})
    if markers.get(PATCH):
        return {'patch': PATCH, 'already_applied': True}
    by = {kind: {row['id']: row for row in data.setdefault(kind, [])}
          for kind in ('groups', 'quests', 'items', 'npcs', 'rooms', 'recipes', 'resources', 'buildings')}
    required = ('fw_dawn_11', 'fw_dawn_0', 'lw_hearth_garden', 'fw_dawn_17', 'fw_dawn_25',
                'fw_dawn_19', 'fw_dawn_18', 'sx_good_guys_1_10', 'sx_good_guys_4_5')
    missing = [ident for ident in required if ident not in by['rooms']]
    if missing:
        raise ValueError('This staging patch requires the supplied world rooms: ' + ', '.join(missing))
    report = {'patch': PATCH, 'guilds': [], 'quests': [], 'clinics': [], 'new_rooms': [],
              'new_npcs': [], 'npc_plans': [], 'sources': []}

    def add(kind, row):
        if row['id'] in by[kind]:
            raise ValueError('Staging ID already exists: ' + row['id'])
        data[kind].append(row)
        by[kind][row['id']] = row
        return row

    def task(npc, name, level):
        row = by['npcs'][npc]
        row.setdefault('task_skills', {})[name] = max(level, row.get('task_skills', {}).get(name, 0))

    def source(room, guild, quests, text, *, recipes=(), rooms=()):
        ident = 'guild_notice_' + guild + '_' + room
        allowed_recipes = [value for value in recipes if value in by['recipes']]
        record = {'id': ident, 'name': by['groups'][guild]['name'] + ' work ledger',
                  'description': 'An anchored local ledger of actual work and finite supply requests.',
                  'type': 'book', 'anchored_readable': True, 'read_text': text,
                  'knowledge': {'quests': quests, 'recipes': allowed_recipes,
                                'rooms': _unique([room] + [value for value in rooms if value in by['rooms']])},
                  'location': room, 'creation_method': 'Authored task-guild ledger; no automatic quest completion.'}
        add('items', record)
        by['rooms'][room].setdefault('items', []).append(ident)
        report['sources'].append(ident)
        return ident

    def group(ident, name, tasks, services):
        # These are professional memberships, not replacement political factions.
        record = {'id': ident, 'name': name, 'description': 'A professional association for actual local work.',
                  'relations': {}, 'visibility': 'hidden', 'location': services[0][0],
                  'creation_method': 'Authored task guild using existing service places and residents.',
                  'guild': {'enabled': True, 'tasks': tasks, 'rooms': _unique([room for room, _ in services]),
                            'join_fee': 0, 'lessons': []}}
        for room, instructor in services:
            for skill in tasks:
                task(instructor, skill, 45)
                for suffix, low, high, gain, cost in [('foundation', 0, 20, 2, 2), ('practice', 20, 60, 3, 4)]:
                    record['guild']['lessons'].append({'id': room + '_' + skill + '_' + suffix,
                        'name': skill.replace('_', ' ').title() + ' ' + suffix,
                        'skill': skill, 'min_level': low, 'max_level': high, 'gain': gain, 'cost': cost,
                        'trainer': instructor})
        add('groups', record)
        report['guilds'].append(ident)

    def stock(guild, room, fixture, item, target, *, difficulty=0, skill=None, recipes=(), known_rooms=()):
        storage = next(row for row in by['rooms'][room].get('locks', []) if row['id'] == fixture)
        recipient = storage['owner']
        ident = 'guild_need_' + guild + '_' + room + '_' + item
        item_name = by['items'][item]['name']
        quest = {'id': ident, 'name': item_name + ' for ' + by['groups'][guild]['name'],
                 'description': ('Keep ' + storage['name'] + ' at ' + str(target) + ' ' + item_name +
                     '. Deliver only what is currently missing to ' + by['npcs'][recipient]['name'] +
                     ' at ' + by['rooms'][room]['name'] + '. Payment comes from that representative’s actual purse. '
                     'The request closes when stocked and returns only when these supplies are actually used.'),
                 'offer_room': room, 'turn_in_room': room, 'progress_scope': 'accepted',
                 'category': 'guild work', 'reward_gold': 0,
                 'guild': {'id': guild, 'skill': skill or by['groups'][guild]['guild']['tasks'][0],
                           'difficulty': difficulty, 'need': {'kind': 'stock', 'room': room,
                           'container': fixture, 'item': item, 'target': target, 'batch': 2,
                           'recipient': recipient, 'gold_per_unit': 1}}}
        add('quests', quest)
        by['npcs'][recipient].setdefault('knowledge', {}).setdefault('quests', []).append(ident)
        report['quests'].append(ident)
        return ident

    # Existing workrooms and actual owners support ordinary professional guilds.
    specs = [
        ('guild_farmers', 'Farmers Guild', ['farming'], [('fw_dawn_0', 'fw_dawn_citizen_13'), ('lw_hearth_garden', 'pop198_hearth_resident_008')]),
        ('guild_market', 'Market Guild', ['trading'], [('fw_dawn_4', 'fw_dawn_merchant_4')]),
        ('guild_news', 'News and Correspondents Guild', ['journalism'], [('fw_dawn_17', 'fw_dawn_citizen_74')]),
        ('guild_magic', 'Spellwrights Guild', ['spellcraft'], [('fw_dawn_19', 'fw_dawn_citizen_40')]),
        ('guild_fighting', 'Fighters Guild', ['fighting'], [('fw_dawn_21', 'fw_dawn_guard_21')]),
        ('guild_thieves', 'Thieves Guild', ['burglary', 'observation', 'lockpicking'], [('locks_fw_hollow_18_workshop', 'locks_fw_hollow_18_tutor')]),
        ('guild_assassins', 'Silent Watch Assassins Guild', ['assassination', 'observation'], [('civic_hollowcrown_base_training', 'civic_army_hollowcrown_scout_2')]),
        ('guild_brewers', 'Brewers Guild', ['brewing'], [('sx_good_guys_4_5', 'sx_good_guys_worker_4')]),
        ('guild_ranchers', 'Ranchers Guild', ['ranching'], [('sx_good_guys_1_10', 'sx_good_guys_1_10_keeper')]),
        ('guild_adventurers', 'Adventurers Guild', ['fieldcraft'], [('fw_dawn_18', 'fw_dawn_citizen_22')]),
        ('guild_poets', 'Poets Guild', ['poetry'], [('fw_dawn_17', 'music112_dawnwatch_elf')]),
        ('guild_painters', 'Painters Guild', ['painting'], [('fw_dawn_17', 'fw_dawn_citizen_76')]),
        ('guild_sculptors', 'Sculptors Guild', ['sculpture'], [('fw_dawn_25', 'music112_dawnwatch_dwarf')]),
        ('guild_architects', 'Architects Guild', ['architecture'], [('fw_dawn_25', 'fw_dawn_citizen_32')]),
    ]
    for ident, name, tasks, services in specs:
        group(ident, name, tasks, services)
    # Physical skill fallback is authored in its existing dedicated field.
    by['npcs']['locks_fw_hollow_18_tutor']['burglary'] = 45
    by['npcs']['locks_fw_hollow_18_tutor']['observation'] = 50

    requests = [
        ('guild_farmers', 'fw_dawn_0', 'furn111_farm_1', 'lw_carrot', 4, 0, [], ['fw_dawn_0']),
        ('guild_farmers', 'lw_hearth_garden', 'furn111_farm_1', 'lw_carrot', 4, 0, [], ['lw_hearth_garden']),
        ('guild_market', 'fw_dawn_4', 'furn111_pantry_1', 'lw_apple', 4, 0, [], ['fw_dawn_0']),
        ('guild_news', 'fw_dawn_17', 'furn111_library_1', 'sx_paper', 4, 0, ['make_sx_paper'], ['sx_good_guys_7_5']),
        ('guild_magic', 'fw_dawn_19', 'furn111_school_1', 'sx_ink', 3, 0, ['make_sx_ink'], ['sx_good_guys_0_5']),
        ('guild_brewers', 'sx_good_guys_4_5', 'furn111_pantry_1', 'ale', 3, 0, ['sx_make_ale'], []),
        ('guild_ranchers', 'sx_good_guys_1_10', 'furn111_animals_1', 'eco_forage', 4, 0, [], ['sx_good_guys_1_10']),
        ('guild_adventurers', 'fw_dawn_18', 'furn111_school_1', 'lw_cloth', 3, 0, ['lw_cloth'], []),
        ('guild_poets', 'fw_dawn_17', 'furn111_library_1', 'sx_ink', 3, 0, ['make_sx_ink'], ['sx_good_guys_0_5']),
        ('guild_painters', 'fw_dawn_17', 'furn111_library_2', 'lw_cloth', 3, 0, ['lw_cloth'], []),
        ('guild_sculptors', 'fw_dawn_25', 'furn111_forge_1', 'lw_wood', 4, 0, [], []),
        ('guild_architects', 'fw_dawn_25', 'furn111_forge_1', 'sx_paper', 4, 0, ['make_sx_paper'], ['sx_good_guys_7_5']),
    ]
    offered = {}
    for guild, room, fixture, item, target, difficulty, recipes, rooms in requests:
        ident = stock(guild, room, fixture, item, target, difficulty=difficulty)
        offered.setdefault((guild, room), {'quests': [], 'recipes': [], 'rooms': []})
        row = offered[(guild, room)]
        row['quests'].append(ident);row['recipes'].extend(recipes);row['rooms'].extend(rooms)

    # Real reading/conversation exercises do not invent a victim or completion.
    for guild in ('guild_fighting', 'guild_thieves', 'guild_assassins'):
        cfg = by['groups'][guild]['guild'];room = cfg['rooms'][0];instructor = cfg['lessons'][0]['trainer']
        manual = 'guild_manual_' + guild
        add('items', {'id': manual, 'name': by['groups'][guild]['name'] + ' practice register',
            'type': 'book', 'anchored_readable': True, 'location': room,
            'description': 'A supervised training register.',
            'read_text': 'Observe the practice room, read its rules, and discuss a supervised exercise with the instructor. '
                         'No civilian is designated as a target; real locks and combat still use their own rules.'})
        by['rooms'][room].setdefault('items', []).append(manual)
        ident = 'guild_study_' + guild
        add('quests', {'id': ident, 'name': 'Supervised foundations',
            'description': 'After accepting, read the practice register and speak with the actual instructor here.',
            'offer_room': room, 'turn_in_room': room, 'progress_scope': 'accepted', 'category': 'guild study',
            'actions': {'read:' + manual: 1}, 'talk_to': [instructor], 'reward_gold': 0,
            'guild': {'id': guild, 'skill': cfg['tasks'][0], 'difficulty': 0}})
        offered[(guild, room)] = {'quests': [ident], 'recipes': [], 'rooms': []}
        by['npcs'][instructor].setdefault('knowledge', {}).setdefault('quests', []).append(ident)
        report['quests'].append(ident)

    # Turn existing civilian healing places into explicitly staffed small clinics.
    clinic_rooms = [row for row in by['rooms'].values()
                    if row.get('services', {}).get('treatment') is not None and
                    any(lock.get('id') == 'furn111_medical_1' for lock in row.get('locks', []))]
    clinic_services = []
    for room in clinic_rooms:
        staff = [npc for npc in by['npcs'].values() if npc.get('work_room') == room['id'] and
                 'care-supplies attendant' in npc.get('title', '')]
        cabinet = next(lock for lock in room['locks'] if lock['id'] == 'furn111_medical_1')
        owner = by['npcs'][cabinet['owner']]
        if owner not in staff:staff.append(owner)
        for npc in staff:
            task(npc['id'], 'healing', 35)
            npc['title'] = npc.get('title', 'Clinical') .replace('care-supplies attendant', 'clinical practitioner')
        room['clinical_services'] = {'enabled': True, 'staff': [npc['id'] for npc in staff],
            'container': cabinet['id'], 'supplies': {'lw_bandage': 1, 'lw_herb': 1, 'sx_water': 1}, 'min_skill': 20}
        room['facilities'] = _unique(room.get('facilities', []) + ['clinic'])
        clinic_services.append((room['id'], owner['id']))
        report['clinics'].append(room['id'])

    # A real upstairs hospital expands an existing clinic, with four distinct tiles.
    house = by['rooms']['fw_dawn_11']
    if house.get('exits', {}).get('up'):
        raise ValueError('Healing House upstairs exit is already occupied.')
    occupied = {(r.get('map_x'), r.get('map_y'), r.get('map_z', 0)) for r in by['rooms'].values()}
    for ident, (x, y, z, name) in HOSPITAL.items():
        if (x, y, z) in occupied:raise ValueError('Hospital map position is already occupied: ' + str((x, y, z)))
        descriptions = {
            'guild_dawn_hospital_reception': 'A broad stair opens into the hospital reception. Benches face a desk where visitors can ask for care, and a passage leads to the treatment room.',
            'guild_dawn_hospital_treatment': 'Bright lamps illuminate clean worktables and a well-used care cabinet. The hospital practitioners treat patients here when staff and supplies are available.',
            'guild_dawn_hospital_ward': 'Curtained beds line this quiet recovery ward. A screened corner gives the off-duty practitioner a place to sleep between shifts.',
            'guild_dawn_hospital_dispensary': 'Labeled shelves, measuring cups and folded linens surround the dispensary counter. An inventory slate records supplies needed by the treatment room.',
        }
        add('rooms', {'id': ident, 'name': name,
            'description': descriptions[ident],
            'exits': {}, 'items': [], 'map_x': x, 'map_y': y, 'map_z': z, 'map_symbol': '.',
            'environment': 'interior', 'group': house.get('group'), 'truce': True, 'campable': False,
            'facilities': ['hospital', 'infirmary', 'hand'], 'weather_shelter': True,
            'climate': {**deepcopy(house.get('climate', {})), 'sheltered': True},
            'planet': deepcopy(house.get('planet', {})), 'laws': deepcopy(house.get('laws', {})),
            'opening_hours': {'start': 0, 'duration': 1500}, 'location': ident,
            'creation_method': 'Authored civilian hospital wing; one room per map tile.'})
        report['new_rooms'].append(ident)
    a,b,c,d = HOSPITAL
    house['exits']['up'] = a
    by['rooms'][a]['exits'] = {'down': 'fw_dawn_11', 'east': b, 'south': c}
    by['rooms'][b]['exits'] = {'west': a, 'south': d}
    by['rooms'][c]['exits'] = {'north': a, 'east': d}
    by['rooms'][d]['exits'] = {'north': b, 'west': c}
    existing = next((building for building in by['buildings'].values() if 'fw_dawn_11' in building.get('rooms', [])), None)
    if existing:
        existing['rooms'] = _unique(existing['rooms'] + list(HOSPITAL))
        existing['street_level'] = 0
    else:
        existing = add('buildings', {'id': 'guild_dawn_civil_hospital', 'name': 'Dawnwatch Civil Hospital',
            'rooms': ['fw_dawn_11', *HOSPITAL], 'street_level': 0, 'location': 'fw_dawn_11',
            'description': 'The Healing House and its four-room upstairs civilian hospital wing.'})
    report['hospital_building'] = existing['id']
    staff_ids = []
    for suffix, name, start in [('day', 'Maren Bellweather', 0), ('night', 'Tomas Reedmere', 750)]:
        ident = 'guild_dawn_hospital_' + suffix + '_practitioner';staff_ids.append(ident)
        add('npcs', {'id': ident, 'name': name, 'title': suffix.title() + ' hospital physician',
            'description': (name + ' tends patients during the ' + suffix + ' shift, checks the care cabinet, '
                            'and teaches careful preparation of hospital supplies.'),
            'hp': 35, 'attack': 3, 'defense': 3, 'gold': 20, 'group': house.get('group'),
            'location': b if start == 0 else c, 'spawn_room': b if start == 0 else c,
            'home_room': c, 'work_room': b, 'leisure_room': a, 'occupation': 'healer',
            'profession': 'healer', 'task_skills': {'healing': 55},
            'work_hours': {'start': start, 'duration': 750},
            'schedule': [{'hour': start // 60, 'minute': start % 60, 'room': b, 'activity': 'working'},
                         {'hour': ((start + 750) % 1500) // 60, 'minute': ((start + 750) % 1500) % 60,
                          'room': c, 'activity': 'sleeping'}],
            'social_profile': {'sentient': True, 'species': 'human', 'age_years': 38,
                'maturity_years': 18, 'autonomous': True, 'accepts': ['friend', 'business']},
            'creation_method': 'A finite named civilian hospital staff member; no repeating spawn generator.'})
        report['new_npcs'].append(ident)
    treatment = by['rooms'][b]
    treatment['services'] = {'treatment': 8}
    treatment['locks'] = [{'id': 'hospital_care_cabinet', 'name': 'Hospital care cabinet',
        'owner': staff_ids[0], 'locked': False, 'public': False, 'pickable': True, 'difficulty': 25,
        'contents': ['lw_bandage'] * 2 + ['lw_herb'] * 2 + ['sx_water'] * 2}]
    treatment['clinical_services'] = {'enabled': True, 'staff': staff_ids,
        'container': 'hospital_care_cabinet', 'supplies': {'lw_bandage': 1, 'lw_herb': 1, 'sx_water': 1}, 'min_skill': 30}
    clinic_services.append((b, staff_ids[0]));report['clinics'].append(b)
    group('guild_healers', 'Healers Guild', ['healing'], clinic_services)
    for room, owner in clinic_services:
        cabinet = by['rooms'][room]['clinical_services']['container']
        ids = [stock('guild_healers', room, cabinet, item, 4, difficulty=20 if item == 'lw_bandage' else 0)
               for item in ('lw_bandage', 'lw_herb', 'sx_water')]
        offered[('guild_healers', room)] = {'quests': ids, 'recipes': ['lw_bandage'], 'rooms': ['fw_dawn_0'] if 'dawn' in room else []}

    for (guild, room), rows in offered.items():
        text = by['groups'][guild]['name'] + ': read this ledger before accepting local work. '
        text += '\n\n'.join(by['quests'][ident]['description'] for ident in rows['quests'])
        if rows['rooms']:
            text += '\nKnown supply places: ' + ', '.join(by['rooms'][ident]['name'] for ident in rows['rooms']) + '. Follow actual streets; the ledger is not a route survey.'
        source(room, guild, rows['quests'], text, recipes=_unique(rows['recipes']), rooms=_unique(rows['rooms']))

    # Two existing growers can pursue actual local work, with no new global AI.
    for ident in ('fw_dawn_citizen_49', 'pop198_hearth_resident_009'):
        by['npcs'][ident]['guild_plan'] = {'enabled': True, 'guilds': ['guild_farmers'],
                                         'learn': False, 'quests': True, 'explore': False}
        report['npc_plans'].append(ident)
    metadata.setdefault('content_patches', {})[PATCH] = 1
    return report


def stage(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents or destination.exists():
        raise ValueError('Choose a new staging directory outside the input world.')
    data = {path.stem: json.loads(path.read_text()) for path in source.glob('*.json') if path.stem != 'metadata'}
    metadata = json.loads((source / 'metadata.json').read_text())
    report = apply(data, metadata)
    from engine import guilds, clinical_services
    singular = {kind.rstrip('s') if kind != 'npcs' else 'npc': rows for kind, rows in data.items() if isinstance(rows, list)}
    singular['class'] = data.get('classes', [])
    errors = guilds.validate(singular) + clinical_services.validate(singular)
    if errors:raise ValueError('\n'.join(errors))
    shutil.copytree(source, destination)
    for kind in ('groups', 'quests', 'items', 'npcs', 'rooms', 'buildings'):
        (destination / (kind + '.json')).write_text(json.dumps(data[kind], indent=2, ensure_ascii=False) + '\n')
    (destination / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n')
    (destination / 'guild-clinic-staging-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.input, args.output), indent=2))
