"""Small, character-owned memories of conversations and public routes."""
from collections import deque

from engine import frontiers, knowledge, living, locks, npc_attention, relationships, society

# A resident keeps a local notebook. Nothing here polls distant residents.
CONTACT_LIMIT = 64
ROAD_LIMIT = 96
VOICES = {
    'hurt': ('calls out', 'Need a healer!', 'Coming!'),
    'danger': ('yells', 'Look out!', 'Behind you!'),
    'temper': ('raises their voice', 'Enough already!', 'Easy now.'),
    'rest': ('murmurs', 'Long day.', 'Rest awhile.'),
    'home': ('says softly', 'Home at last.', 'Sit with me.'),
    'work': ('says', 'Busy shift.', 'Need a hand?'),
    'family': ('says softly', 'Missed you.', 'Me too.'),
    'hunger': ('says', 'Lunch yet?', 'Soon, I hope.'),
    'paid': ('says', 'Pay came in.', 'About time.'),
}


def notebook(person):
    return person.progress.setdefault('town_talk', {'contacts': {}, 'roads': {}})


def remember(table, key, value, limit):
    table.pop(key, None)
    table[key] = value
    if len(table) > limit:
        del table[next(iter(table))]


def contacts_for(world, person):
    notes = notebook(person)
    contacts = notes['contacts']
    # Old saves already have relationships. Recover the names from those bonds
    # without looking up a distant person's current room or appearance.
    if not notes.get('introduced_family'):
        index = getattr(world, '_town_known_bonds', None)
        if index is None:
            index = {}
            for row in relationships.state(world)['bonds'].values():
                if not row['kinds']: continue
                people = list(zip(row['participants'], row['names']))
                if len(people) == 2:
                    for (left, _), (right, name) in (people, people[::-1]):
                        index.setdefault(left, {})[right] = name
            world._town_known_bonds = index
        for ident, name in index.get(person.id, {}).items():
            if ident not in contacts and ident in world.entities and not world.entities[ident].is_player:
                remember(contacts,ident,dict(name=name, met=True, source='', at=-1, place='', look=''),CONTACT_LIMIT)
        if person.is_player:
            for ident,row in list(person.progress.get('chronicle_contacts',{}).items())[-CONTACT_LIMIT:]:
                if ident not in contacts and row.get('name'):
                    remember(contacts,ident,dict(name=row['name'],met=True,source='',at=-1,place='',look=''),CONTACT_LIMIT)
        if not person.is_player and not (person.spawner_key or '').startswith('birth:'):
            profile=world.npcs.get(person.source_def,{}).get('founding_profile',{})
            for tie in profile.get('feelings',[]):
                other=world.entities.get('npc:'+tie['person'])
                if other and other.id not in contacts:
                    remember(contacts,other.id,dict(name=other.name,met=True,source='',at=-1,place='',look=''),CONTACT_LIMIT)
        notes['introduced_family'] = True
    return contacts


def public(world, room):
    return room in world.rooms and not getattr(world, 'room_details', {}).get(room, {}).get('property_unit_id')


def travel(world, person, start, end):
    if (not society.enabled(world) or not relationships.sentient(world, person)
            or not public(world, start) or not public(world, end)):
        return
    roads = notebook(person)['roads']
    for origin, dest in ((start, end), (end, start)):
        for direction, target in world.rooms[origin].exits.items():
            if target == dest:
                remember(roads, origin, {**roads.get(origin, {}), direction: dest}, ROAD_LIMIT)
                break


def visible_feature(world, person):
    from engine.costumes import npc_doll
    from engine.visual_mapping import appearance_for, _player_equipment
    row = world.npcs.get(person.source_def, {})
    race = person.race or row.get('race', '')
    role = person.char_class or row.get('char_class', '')
    appearance = appearance_for(world, person, row, race, role, {}, False)
    doll = npc_doll(world, person, row, appearance, _player_equipment(world, person))
    body = next((piece for piece in doll['equipment'] if piece['layer'] == 'body'), {})
    garment = body.get('color', '') + ' ' + body.get('kind', '').replace('_', ' ')
    if garment.strip():
        return garment.strip()
    traits = doll['characteristics']
    return 'shaved head' if traits.get('hair_style') == 'bald' else traits['hair_color']+' hair'


def meet(world, a, b):
    now = living.state(world)['minute']
    for observer, subject in ((a, b), (b, a)):
        if subject.is_player or not relationships.sentient(world, subject) or observer.location!=subject.location:
            continue
        person = {'name': subject.name, 'met': True, 'source': '', 'at': now,
                  'place': subject.location if public(world, subject.location) else '',
                  'look': visible_feature(world, subject)}
        remember(notebook(observer)['contacts'], subject.id, person, CONTACT_LIMIT)


def hearsay(listener, speaker, key, fact):
    contacts = notebook(listener)['contacts']
    existing = contacts.get(key, {})
    if key == listener.id or (existing and existing.get('at', -1) >= fact['at']):
        return False
    remember(contacts, key, {**fact, 'met': existing.get('met', False), 'source': speaker.name}, CONTACT_LIMIT)
    return True


def local_roads(world, person):
    roads = notebook(person)['roads']
    # A posted sign is evidence for its immediate exit only.
    from engine.trail_guidance import signs
    here = person.location
    if public(world, here):
        adjacent = dict(roads.get(here, {}))
        for sign in signs(world, person):
            dest = world.rooms[here].exits.get(sign['direction'])
            if not sign['closed'] and public(world, dest):
                adjacent[sign['direction']] = dest
        if adjacent:
            remember(roads, here, adjacent, ROAD_LIMIT)
    return roads


def directions(world, guide, listener, destination):
    roads = local_roads(world, guide)
    start = guide.location
    previous = {start: None}
    pending = deque([start])
    lock_index = locks.index(world, cache=True)
    while pending and destination not in previous:
        src = pending.popleft()
        for direction, dest in roads.get(src, {}).items():
            if (dest in previous or not public(world, dest) or not public(world, src)
                    or world.rooms[src].exits.get(direction) != dest
                    or frontiers.blocked(world, src, direction, listener, lock_index=lock_index)):
                continue
            previous[dest] = (src, direction)
            pending.append(dest)
    if destination not in previous:
        return []
    route = []
    dest = destination
    while dest != start:
        src, direction = previous[dest]
        route.append((src, direction, dest))
        dest = src
    return route[::-1]


def pass_route(world, listener, path):
    if listener.is_player:
        knowledge.teach(world, listener, {'rooms': [dest for _, _, dest in path]})
    roads = notebook(listener)['roads']
    for src, direction, dest in path:
        remember(roads, src, {**roads.get(src, {}), direction: dest}, ROAD_LIMIT)


def match(options, query):
    key = query.strip().casefold()
    exact = [ident for ident, name in options.items() if name.casefold() == key]
    found = exact or [ident for ident, name in options.items() if key and name.casefold().startswith(key)]
    if len(found) > 1:
        raise ValueError('Please use a more specific name. I know more than one match.')
    return next(iter(found), None)


def local_places(world, guide):
    roads = local_roads(world, guide)
    places = {rid for exits in roads.values() for rid in exits.values()} | {guide.location}
    return {rid: world.rooms[rid].name for rid in sorted(places) if public(world, rid)}


def ask(world, player, guide, action, query):
    from engine import social
    social.gate(world, player, guide)
    if guide.is_player or not relationships.sentient(world, guide):
        raise ValueError('Ask a nearby resident.')
    if society.friendliness(world, guide, player) < 50:
        raise ValueError(guide.name+' declines to talk.')
    npc_attention.begin(world, player, guide)
    meet(world, player, guide)
    notes = notebook(guide)
    contacts = contacts_for(world, guide)
    names = {key: fact['name'] for key, fact in contacts.items() if key != player.id}
    prefix = guide.name+' says, '
    if action in ('people','work','activities','plans','creatures','localnews'):
        from engine import resident_discussion
        return prefix+'“'+resident_discussion.discuss(world,guide,action)+'”'
    if action=='memories':
        profile = world.npcs.get(guide.source_def,{}).get('founding_profile',{})
        if (guide.spawner_key or '').startswith('birth:'):profile={}
        memories=[profile['event']] if profile.get('event') else []
        memories.extend('I was '+str(e['age'])+'. '+e['title']+'. '+e['text'] for e in profile.get('influences',[]))
        if not memories:return prefix+'“I have no story to share today.”'
        index=notes.get('last_shared_memory',-1)+1
        notes['last_shared_memory']=index%len(memories)
        memory=memories[index%len(memories)]
        if memory.startswith('I '):return prefix+'“'+memory+'”'
        return guide.name+' shares a memory. '+memory
    if action == 'tell':
        facts = contacts_for(world, player)
        choices = {key: f['name'] for key, f in facts.items() if key != guide.id}
        if not query:
            return 'People you can talk about: '+(', '.join(list(choices.values())[-6:]) or 'none yet')+'.'
        who = match(choices, query)
        if not who:
            return 'You haven’t learned anything about that person yet.'
        if not hearsay(guide,player,who,facts[who]):
            return prefix+'“I already heard that.”'
        return 'You tell '+guide.name+' about '+choices[who]+'.'
    if action == 'showroute':
        places = local_places(world,player)
        if not query:
            return 'Places you can describe: '+(', '.join(name for rid,name in places.items() if rid != player.location) or 'none yet')+'.'
        dest = match(places,query)
        route = directions(world,player,guide,dest) if dest else []
        if not route: return 'You do not know an open route there from here.'
        pass_route(world,guide,route)
        return 'You explain the way to '+places[dest]+' to '+guide.name+'.'
    if action == 'headline':
        headlines = getattr(player,'_read_news',{})
        if query not in headlines:
            return 'Read the edition and select a dispatch first.'
        reports = notes.setdefault('news',{})
        if query in reports:
            return prefix+'“I’ve heard that one.”'
        remember(reports,query,headlines[query],8)
        return 'You share the report with '+guide.name+'.'
    if action == 'about':
        if not query:
            return prefix+('“Ask me about '+', '.join(list(names.values())[-4:])+'.'+'”' if names else '“No introductions yet.”')
        key = match(names, query)
        if key is None:
            return prefix+'“I don’t know that name.”'
        fact = contacts[key]
        hearsay(player, guide, key, fact)
        words = ('I know '+fact['name']+'. ' if fact['met'] else 'I’ve only heard of '+fact['name']+'. ')
        if fact['source']:
            words += fact['source']+' told me.'
        elif fact['look']:
            words += 'I remember the '+fact['look']+'.'
        if public(world, fact['place']):
            words += ' Last sighting was at '+world.rooms[fact['place']].name+'.'
            knowledge.teach(world, player, {'rooms': [fact['place']]})
        return prefix+'“'+words.strip()+'”'
    places = local_places(world, guide)
    target_name, separator, recipient = query.rpartition(' for ') if action == 'relay' else ('', '', '')
    if action == 'relay' and not separator:
        raise ValueError('Give a place and the name of the person to tell.')
    if not query:
        choices = [name for key, name in places.items() if key != guide.location][:5]
        return prefix+('“I know the way to '+', '.join(choices)+'.'+'”' if choices else '“I haven’t learned a route from here yet.”')
    dest = match(places, target_name if action == 'relay' else query)
    if dest == guide.location:
        return prefix+'“You’re already here.”'
    path = directions(world, guide, player, dest) if dest else []
    if not path:
        return prefix+'“I don’t know an open route from here.”'
    if action == 'relay':
        who = match(names, recipient)
        if not who or not contacts[who]['met']:
            return prefix+'“I’d need an introduction first.”'
        errands = notes.setdefault('errands', {})
        if who not in errands and len(errands) >= 4:
            return prefix+'“I have messages to deliver first.”'
        if who in errands and errands[who] != dest:
            return prefix+'“I already have directions to pass on to '+names[who]+'.'+'”'
        errands[who] = dest
        return prefix+'“I’ll tell '+names[who]+' the way to '+places[dest]+' when we meet.”'
    pass_route(world, player, path)
    return prefix+'“'+ ' Then '.join(direction.capitalize()+' to '+world.rooms[end].name+'.' for _, direction, end in path)+'”'


def everyday(world, speaker, listener, turn):
    from engine import resident_discussion
    return resident_discussion.everyday(world,speaker,listener,turn)


def exchange(world, speaker, listener, turn):
    # Keep ordinary greetings in the rotation. An addressed message wins the next meeting.
    notes = notebook(speaker)
    if min(society.friendliness(world, speaker, listener),society.friendliness(world, listener, speaker)) < 50:
        return None
    errands = notes.get('errands', {})
    dest = errands.get(listener.id)
    if dest and dest in world.rooms:
        if dest == speaker.location:
            del errands[listener.id]
            return 'says', 'Right here.', 'Found it.'
        route = directions(world, speaker, listener, dest)
        if route:
            pass_route(world, listener, route)
            del errands[listener.id]
            return 'says', route[0][1].capitalize()+' first.', 'Got it.'
    daily = everyday(world, speaker, listener, turn)
    if daily and daily[0] in ('yells','calls out'):
        return daily
    if turn % 7 == 0:
        facts = [(key, f) for key, f in contacts_for(world, speaker).items() if key not in (speaker.id, listener.id)]
        for key, fact in reversed(facts):
            if hearsay(listener, speaker, key, fact):
                words='I know '+fact['name']+'.' if fact.get('met') else 'I have heard about '+fact['name']+'.'
                if fact.get('look'):words+=' I remember the '+fact['look']+'.'
                if fact.get('source'):words+=' '+fact['source']+' was the one who told me.'
                if public(world,fact.get('place')):words+=' My last sighting was at '+world.rooms[fact['place']].name+'.'
                return 'says',words,'Thank you. That is useful to know, though they may have moved on since then.'
    if turn % 7 == 1:
        places = [key for key in local_places(world, speaker) if key != speaker.location]
        if places:
            end = places[(turn//7) % len(places)]
            route = directions(world, speaker, listener, end)
            if route and any(notebook(listener)['roads'].get(src, {}).get(d) != dst for src, d, dst in route):
                pass_route(world, listener, route)
                return 'says','If you are heading to '+world.rooms[end].name+', start '+route[0][1]+' from here. I can describe the route I know if you need more directions.','Thank you. I would rather ask someone who knows the road than guess.'
    return daily
