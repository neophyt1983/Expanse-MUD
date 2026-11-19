#!/usr/bin/env python3
"""Compose four real artistic trades and finite commissions into 1.9.16.

Use ``apply(data, metadata)`` alongside the guild/clinic and knowledge patches.
This changes authored initial content only and never restocks running saves.
"""
from copy import deepcopy

PATCH = 'artistic_work_v1'


def apply(data, metadata):
    if metadata.get('content_patches', {}).get(PATCH):
        return {'patch': PATCH, 'already_applied': True}
    by = {kind: {row['id']: row for row in data.setdefault(kind, [])}
          for kind in ('rooms', 'npcs', 'items', 'recipes', 'buildings')}
    for room in ('fw_dawn_17', 'fw_dawn_25'):
        if room not in by['rooms']:raise ValueError('Art staging requires the supplied Dawnwatch rooms.')
    report = {'patch': PATCH, 'recipes': [], 'artists': [], 'patrons': [], 'sources': [], 'material_allocations': []}

    def add(kind, record):
        if record['id'] in by[kind]:raise ValueError('Art staging ID already exists: ' + record['id'])
        by[kind][record['id']] = record;data[kind].append(record)

    specs = [
        ('art119_pastoral_poem', 'Write a pastoral poem', 'poetry', 'pastoral', 'A Bell Above the Garden',
         'A short pastoral poem describing the change from working daylight to evening.',
         'The last barrow rests beside the gate.\nA bell crosses the garden,\nAnd every rain-dark leaf holds\nA little of the remaining light.',
         {'sx_paper': 1, 'sx_ink': 1}, 'scriptorium', 15, 'fw_dawn_17', 'music112_dawnwatch_elf', 'fw_dawn_citizen_74'),
        ('art119_orchard_painting', 'Paint an orchard study', 'painting', 'landscape', 'Orchard in Rain',
         'An ink wash on cloth studying the orchard’s shapes and changing light.', '',
         {'lw_cloth': 1, 'sx_ink': 1}, 'workbench', 20, 'fw_dawn_17', 'fw_dawn_citizen_76', 'music112_dawnwatch_elf'),
        ('art119_carved_bird', 'Carve a wooden bird', 'sculpture', 'naturalistic', 'A Bird at Rest',
         'A small hand-finished wooden study whose surface retains the grain of its actual material.', '',
         {'lw_wood': 2}, 'workbench', 25, 'fw_dawn_25', 'music112_dawnwatch_dwarf', 'fw_dawn_merchant_25'),
        ('art119_library_plan', 'Survey the library and draw its plan', 'architecture', 'measured', 'Dawnwatch Library Survey',
         'A measured plan of the existing public library. It proposes maintenance work; it creates no new rooms or building.', '',
         {'sx_paper': 1, 'sx_ink': 1}, 'workbench', 20, 'fw_dawn_25', 'fw_dawn_citizen_32', 'music112_dawnwatch_dwarf'),
    ]
    for ident, name, kind, style, title, description, verse, ingredients, station, minutes, room, artist, patron in specs:
        for item in ingredients:
            if item not in by['items']:raise ValueError('Artistic material is missing: ' + item)
        config = dict(kind=kind, style=style, title=title, description=description, difficulty=20, min_skill=0)
        if verse:config['text'] = verse
        if kind == 'architecture':
            building = 'public_reading_hall_fw_dawn_17'
            if building not in by['buildings']:raise ValueError('The actual library building is missing.')
            config['building'] = building
        add('recipes', {'id': ident, 'name': name, 'description': description,
            'ingredients': ingredients, 'outputs': {}, 'station': station, 'kind': 'crafting',
            'minutes': minutes, 'artwork': config, 'location': room,
            'creation_method': 'An authored artistic form; every produced work has a separate creator and date.'})
        report['recipes'].append(ident)
        npc = by['npcs'][artist]
        npc.setdefault('task_skills', {})[kind] = max(npc.get('task_skills', {}).get(kind, 0), 35)
        npc['art_plan'] = {'enabled': True, 'recipes': [ident], 'patrons': [patron], 'explore': True}
        if artist not in report['artists']:report['artists'].append(artist)
        buyer = by['npcs'][patron]
        buyer.setdefault('art_commissions', []).append({'id': ident + '_order',
            'name': title + ' for ' + buyer['name'], 'enabled': True, 'recipe': ident,
            'price': 3, 'min_quality': 15, 'min_appreciation': 20})
        buyer.setdefault('art_taste', {}).setdefault('styles', {})[style] = 8 if kind in ('poetry', 'sculpture') else 3
        if patron not in report['patrons']:report['patrons'].append(patron)
        # Initial commissions receive actual existing workshop materials. The
        # donor stock is reduced by precisely the amount the artist carries.
        for item, quantity in ingredients.items():
            donor = 'fw_dawn_25' if item in ('lw_cloth', 'lw_wood') else 'fw_dawn_17'
            stock = by['rooms'][donor].get('workshop', {}).get('initial_stock', {})
            if stock.get(item, 0) < quantity:raise ValueError('The authored studio cannot allocate nonexistent ' + item)
            stock[item] -= quantity
            npc.setdefault('inventory', []).extend([item] * quantity)
            report['material_allocations'].append(dict(from_room=donor, to_npc=artist, item=item, quantity=quantity))
        manual = ident + '_manual'
        learned = [ident, 'make_sx_paper', 'make_sx_ink', 'lw_cloth']
        add('items', {'id': manual, 'name': name + ': studio notes', 'type': 'book', 'anchored_readable': True,
            'description': 'A local studio manual and an actual current commission notice.',
            'read_text': description + '\nMaterials: ' + ', '.join(str(count) + ' ' + by['items'][item]['name'] for item, count in ingredients.items()) +
                         '.\n' + buyer['name'] + ' is seeking one work and offers 3 gold while this order is unfilled and funded. '
                         'Speak with the actual patron; taste is personal and payment is not guaranteed for a rejected piece. '
                         'The library paper-and-ink desk and the joinery workshop use finite stock. '
                         'Learn real supply routes or ask people when a material is missing.',
            'knowledge': {'recipes': [recipe for recipe in learned if recipe in by['recipes']],
                          'rooms': ['fw_dawn_17', 'fw_dawn_25']},
            'publication': {'kind': 'technical', 'genre': 'arts', 'author': npc['name'],
                            'work_id': manual, 'edition_id': manual + ':1', 'claims': []},
            'location': room, 'creation_method': 'An authored public studio manual, read in the actual room.'})
        by['rooms'][room].setdefault('items', []).append(manual);report['sources'].append(manual)
        buyer.setdefault('knowledge', {}).setdefault('recipes', []).append(ident)
        # The patron can disclose the commissioned plan in real conversation;
        # the artist is not granted remote knowledge merely by opting in.

    # A public architectural plaque preserves genuine uncertainty; no invented
    # living/dead author, completion date, or historical commission is asserted.
    plaque = {'id': 'art119_library_uncertain_plaque', 'name': 'Library masonry attribution plaque',
        'description': 'The surviving plaque does not identify the original designer or construction date.',
        'read_text': 'Designer unrecorded. Date uncertain. Later measured plans must be attributed to their actual surveyors.',
        'type': 'artwork', 'anchored_readable': True, 'location': 'fw_dawn_17',
        'artwork': {'version': 1, 'kind': 'architecture', 'style': 'vernacular',
            'attribution': 'uncertain', 'creator': {'name': 'unrecorded designer', 'status': 'unknown'},
            'created_minute': None, 'building': 'public_reading_hall_fw_dawn_17'}}
    add('items', plaque);by['rooms']['fw_dawn_17'].setdefault('items', []).append(plaque['id'])
    metadata.setdefault('content_patches', {})[PATCH] = 1
    return report
