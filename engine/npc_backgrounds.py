"""Bounded founding instruction from real homes, people and reading sources.

Only a creation hook (or explicit authored migration) initializes a background.
Saved learned skills and knowledge win. No inventory, action counter, explored
room, quest source or quest completion is manufactured. Individual sampling
uses a stable seed, so reloads and map projections cannot reroll a life.
"""
from copy import deepcopy
from hashlib import sha256

from engine import knowledge, relationships, worldtime

KEY = 'npc_background_v1'
LIMITS = dict(rooms=12, items=24, recipes=8)
MAX_TRAINING = 8
MAX_SOURCES = 24
EXPERIENCES = ('support received', 'strained interaction', 'authority helped', 'authority harmed')
OCCUPATIONS = {
    'farmer': ('farming', 'fieldcraft'), 'rancher': ('ranching',), 'shepherd': ('ranching', 'fieldcraft'),
    'merchant': ('trading',), 'trader': ('trading',), 'cook': ('cooking',), 'chef': ('cooking',),
    'brewer': ('brewing',), 'artisan': ('crafting',), 'producer': ('crafting',),
    'smith': ('crafting',), 'carpenter': ('crafting',), 'guard': ('fighting', 'observation'),
    'soldier': ('fighting', 'observation'), 'journalist': ('journalism',),
    'reporter': ('journalism',), 'mage': ('spellcraft',), 'locksmith': ('lockpicking',),
    'poet': ('poetry', 'writing'), 'painter': ('painting',), 'sculptor': ('sculpture',),
    'architect': ('architecture',), 'singer': ('singing',), 'musician': ('singing',),
    'entertainer': ('singing',), 'scribe': ('reading', 'writing'), 'teacher': ('reading',),
    'scholar': ('reading',), 'miner': ('mining',), 'fisher': ('fishing',),
    'healer': ('healing',), 'doctor': ('healing',),
}


def _tasks():
    from engine.task_skills import NAMES
    return NAMES


def _range(value, low=0, high=100):
    return type(value) is int and low <= value <= high


def _minute(world):
    value = getattr(world, 'living_state', {}).get('minute')
    return value if value is not None else worldtime.initial_minute(world.metadata)


def _config(person):
    return person.get('background', {})


def _home(definition, config):
    return config.get('home_room') or definition.get('home_room') or definition.get('population_profile', {}).get('home_room')


def _work(definition):
    return definition.get('work_room') or definition.get('workplace_room')


def _local_person(npcs, source, home, work):
    row = npcs.get(source, {})
    return bool(row and row.get('social_profile', {}).get('sentient') is True
                and {home, work} - {None, ''} &
                {row.get('home_room'), _work(row), row.get('population_profile', {}).get('home_room')})


def _level(definition, task):
    value = definition.get(task, 0) if task in ('burglary', 'observation', 'lockpicking') else definition.get('task_skills', {}).get(task, 0)
    return value if _range(value) else 0


def _source_ceiling(npcs, definition, home, work, source, task):
    if source.get('kind') == 'workplace' and source.get('id') == work:
        role = definition.get('occupation') or definition.get('profession')
        # An explicitly authored occupation establishes a place for elementary
        # prior practice. It grants no present tools, job, guild or permissions.
        return 35 if task in OCCUPATIONS.get(role, ()) else 0
    if source.get('kind') == 'npc' and _local_person(npcs, source.get('id'), home, work):
        return _level(npcs[source['id']], task)
    return 0


def validate(data):
    return _validate_catalogs({row['id']: row for row in data.get('npc', [])},
                              {row['id'] for row in data.get('room', [])},
                              {row['id'] for row in data.get('item', [])})


def _validate_catalogs(npcs, rooms, items, selected=None):
    issues = []
    fields = {'version', 'enabled', 'migrate_existing', 'home_room', 'nearby_limit', 'caregivers',
              'training', 'reading', 'experiences', 'interests'}
    for ident, definition in ([(selected, npcs[selected])] if selected else npcs.items()):
        config = _config(definition)
        if config == {}:
            continue
        label = ident + ': background '
        if not isinstance(config, dict) or set(config) - fields:
            issues.append(label + 'must be an object with supported source fields'); continue
        if config.get('version') != 1 or type(config.get('version')) is not int:
            issues.append(label + 'requires version 1')
        if type(config.get('enabled')) is not bool or type(config.get('migrate_existing', False)) is not bool:
            issues.append(label + 'enabled and migrate_existing must be boolean')
        if not config.get('enabled'):
            continue
        home, work = _home(definition, config), _work(definition)
        if not isinstance(home, str) or home not in rooms:
            issues.append(label + 'needs a real home room')
            continue
        if not _range(config.get('nearby_limit', 3), 0, 8):
            issues.append(label + 'nearby_limit must be 0–8')
        caregivers = config.get('caregivers', [])
        if (not isinstance(caregivers, list) or len(caregivers) > 4
                or any(not isinstance(source, str) or source == ident
                       or not _local_person(npcs, source, home, None) for source in caregivers)):
            issues.append(label + 'caregivers must name at most four real people associated with this home')
        training = config.get('training', [])
        if not isinstance(training, list) or len(training) > MAX_TRAINING:
            issues.append(label + 'training must contain at most eight source-backed lessons'); training = []
        for lesson in training:
            if not isinstance(lesson, dict):
                issues.append(label + 'training entries must be objects'); continue
            task, source = lesson.get('skill'), lesson.get('source', {})
            if (not isinstance(task, str) or task not in _tasks() or not isinstance(source, dict) or set(source) != {'kind', 'id'}
                    or not isinstance(source.get('kind'), str) or not isinstance(source.get('id'), str)):
                issues.append(label + 'training needs a supported task and an exact source'); continue
            low, high = lesson.get('minimum', 0), lesson.get('maximum', 0)
            ceiling = _source_ceiling(npcs, definition, home, work, source, task)
            if (set(lesson) - {'skill', 'source', 'minimum', 'maximum'} or not _range(low)
                    or not _range(high) or low > high or high > ceiling or not ceiling):
                issues.append(label + 'training range exceeds the local teacher or workplace instruction')
        reading = config.get('reading', [])
        if (not isinstance(reading, list) or len(reading) > 4
                or any(not isinstance(ident, str) or ident not in items for ident in reading)):
            issues.append(label + 'reading must name at most four real items')
        experiences = config.get('experiences', [])
        if not isinstance(experiences, list) or len(experiences) > 8:
            issues.append(label + 'experiences must contain at most eight sourced interactions'); experiences = []
        for event in experiences:
            if (not isinstance(event, dict) or set(event) != {'kind', 'source'} or event.get('kind') not in EXPERIENCES
                    or not isinstance(event.get('source'), str)
                    or not _local_person(npcs, event.get('source'), home, work)):
                issues.append(label + 'experience needs a supported interaction and associated real person'); continue
            source = npcs[event['source']]
            if event['kind'].startswith('authority ') and not (source.get('city_guard') is True
                    or any(source.get(key) == 'guard' for key in ('occupation', 'profession', 'role'))):
                issues.append(label + 'authority experience must name an authored officer')
        interests = config.get('interests', {})
        if (not isinstance(interests, dict) or any(task not in _tasks() or not _range(weight)
                                                  for task, weight in interests.items())):
            issues.append(label + 'interests must map supported tasks to 0–100 weights')
    return issues


def validate_saved(progress):
    if KEY not in progress:
        return
    saved = progress[KEY]
    if (not isinstance(saved, dict) or type(saved.get('version')) is not int or saved['version'] != 1
            or not isinstance(saved.get('seed'), str) or len(saved['seed']) != 64
            or any(value not in '0123456789abcdef' for value in saved['seed'])
            or saved.get('origin') not in ('founding', 'authored_migration')
            or not isinstance(saved.get('home_room'), str)
            or not _range(saved.get('initialized_at'), 0, 10**15)
            or not isinstance(saved.get('interests'), dict)
            or any(task not in _tasks() or not _range(value) for task, value in saved['interests'].items())
            or not isinstance(saved.get('sources'), list) or len(saved['sources']) > MAX_SOURCES
            or not isinstance(saved.get('training'), list) or len(saved['training']) > MAX_TRAINING
            or not isinstance(saved.get('rumors', []), list) or len(saved.get('rumors', [])) > 8
            or not isinstance(saved.get('experiences', []), list) or len(saved.get('experiences', [])) > 8):
        raise ValueError('Invalid saved NPC founding background.')
    for lesson in saved['training']:
        source = lesson.get('source') if isinstance(lesson, dict) else None
        if (not isinstance(lesson, dict) or not isinstance(lesson.get('skill'), str) or lesson['skill'] not in _tasks()
                or not _range(lesson.get('level')) or not isinstance(source, dict)
                or source.get('kind') not in ('npc', 'workplace') or not isinstance(source.get('id'), str)):
            raise ValueError('Invalid saved NPC founding instruction.')
    for row in saved['sources']:
        if (not isinstance(row, dict) or row.get('kind') not in ('home', 'workplace', 'workshop', 'local_walk', 'caregiver', 'item')
                or not isinstance(row.get('id'), str) or row.get('familiarity') not in ('sourced', 'familiar')
                or not isinstance(row.get('knowledge'), dict)):
            raise ValueError('Invalid saved NPC founding source.')
        for kind, values in row['knowledge'].items():
            if (kind not in LIMITS or not isinstance(values, list) or len(values) > LIMITS[kind]
                    or any(not isinstance(value, str) for value in values)):
                raise ValueError('Invalid saved NPC founding knowledge.')
    for row in saved.get('rumors', []):
        if (not isinstance(row, dict) or not isinstance(row.get('room'), str)
                or not isinstance(row.get('source'), str) or row.get('familiarity') != 'mention'):
            raise ValueError('Invalid saved NPC founding rumor.')
    for row in saved.get('experiences', []):
        if (not isinstance(row, dict) or row.get('kind') not in EXPERIENCES or not isinstance(row.get('source'), str)):
            raise ValueError('Invalid saved NPC founding experience.')


def _saved_inputs(actor):
    """Never replace malformed learned records while adding a background."""
    for key in ('knowledge', 'skills', 'town_talk'):
        if key in actor.progress and not isinstance(actor.progress[key], dict):
            raise ValueError('Saved NPC ' + key + ' must be an object before founding migration.')
    known = actor.progress.get('knowledge', {})
    if any(not isinstance(known[key], list) or any(not isinstance(value, str) for value in known[key])
           for key in knowledge.KINDS if key in known):
        raise ValueError('Saved NPC knowledge must contain identifier lists before founding migration.')
    notes = actor.progress.get('town_talk', {})
    if any(key in notes and not isinstance(notes[key], dict) for key in ('contacts', 'roads')):
        raise ValueError('Saved NPC local notebook must contain objects before founding migration.')
    if any(not isinstance(exits, dict) for exits in notes.get('roads', {}).values()):
        raise ValueError('Saved NPC roads must contain direction objects before founding migration.')


def _public(world, room):
    definition = getattr(world, 'room_details', {}).get(room, {})
    return (room in world.rooms and world.rooms[room].map_visibility != 'hidden'
            and not definition.get('property_unit_id') and not definition.get('secret'))


def _open_edge(world, room, direction):
    row = getattr(world, 'room_details', {}).get(room, {})
    if direction in row.get('gates', {}):
        return False
    return not any(lock.get('direction') == direction for lock in row.get('locks', []))


def _dangerous(world, room):
    row = getattr(world, 'room_details', {}).get(room, {})
    return bool(row.get('encounters') or row.get('hazard') or row.get('dangerous'))


def initialize(world, actor, *, fresh=False):
    """Use only at actual creation or an explicit additive migration boundary."""
    if actor.is_player or not actor.alive or not relationships.sentient(world, actor):
        return False
    if KEY in actor.progress:
        validate_saved(actor.progress)
        return False
    definition = world.npcs.get(actor.source_def, {})
    config = _config(definition)
    if not isinstance(config, dict) or config.get('enabled') is not True:
        return False
    if not fresh and config.get('migrate_existing') is not True:
        return False
    # Validate the selected record, with its actual source catalogs, before a
    # single skill or fact is written. Source definitions are not instantiated.
    errors = _validate_catalogs(world.npcs, world.rooms, world.items, actor.source_def)
    if errors:
        raise ValueError('; '.join(errors))
    _saved_inputs(actor)
    home, work = _home(definition, config), _work(definition)
    seed = sha256(repr((world.metadata.get('resident_seed', world.metadata.get('seed', '')),
                       actor.source_def, actor.id)).encode()).hexdigest()

    def rank(value):
        return sha256((seed + ':' + value).encode()).hexdigest()

    pending = {key: [] for key in LIMITS}
    sources, rumors, roads = [], [], {}

    def teach(table, kind, ident, familiarity='sourced'):
        if len(sources) >= MAX_SOURCES:
            return
        learned = {}
        for key, limit in LIMITS.items():
            catalog = getattr(world, key, {})
            values = table.get(key, [])
            if not isinstance(values, (list, tuple)):
                continue
            for value in values[:limit]:
                if not isinstance(value, str) or value not in catalog or value in pending[key]:
                    continue
                if len(pending[key]) >= limit:
                    break
                pending[key].append(value); learned.setdefault(key, []).append(value)
        if learned and len(sources) < MAX_SOURCES:
            sources.append(dict(kind=kind, id=ident, familiarity=familiarity, knowledge=learned))

    places = [room for room in (home, work) if room in world.rooms]
    for room in dict.fromkeys(places):
        teach({'rooms': [room]}, 'home' if room == home else 'workplace', room, 'familiar')
    candidates = []
    for room in dict.fromkeys(places):
        for direction, destination in world.rooms[room].exits.items():
            if _public(world, destination) and _open_edge(world, room, direction):
                candidates.append((room, direction, destination))
    for room, direction, destination in sorted(candidates, key=lambda row: rank(repr(row)))[:config.get('nearby_limit', 3)]:
        if _dangerous(world, destination):
            if not any(row['room'] == destination for row in rumors):
                rumors.append(dict(room=destination, source=room, familiarity='mention'))
            continue
        teach({'rooms': [destination]}, 'local_walk', room, 'familiar')
        roads.setdefault(room, {})[direction] = destination
    scope = set(pending['rooms'])
    skills = actor.progress.get('skills', {})
    if not isinstance(skills, dict):
        raise ValueError('Saved NPC skills must be an object before founding migration.')
    training, interests = [], dict(config.get('interests', {}))
    for index, lesson in enumerate(config.get('training', [])):
        low, high = lesson.get('minimum', 0), lesson.get('maximum', 0)
        level = low + int(rank('training:' + str(index)), 16) % (high - low + 1)
        task = lesson['skill']
        training.append(dict(skill=task, level=level, source=deepcopy(lesson['source'])))
        interests.setdefault(task, min(100, 25 + level + int(rank('interest:' + task), 16) % 16))
    for source in config.get('caregivers', []):
        if len(sources) < MAX_SOURCES:
            sources.append(dict(kind='caregiver', id=source, familiarity='familiar', knowledge={}))
    # Posted designs at a real authored workplace are a source of elementary
    # prior instruction. Do not infer every recipe from a shared ingredient.
    workshop = getattr(world, 'room_details', {}).get(work, {}).get('workshop', {})
    posted = workshop.get('recipes', []) if isinstance(workshop, dict) else []
    for recipe_id in sorted(posted, key=lambda value: rank('design:' + str(value)))[:LIMITS['recipes']]:
        recipe = getattr(world, 'recipes', {}).get(recipe_id, {})
        names = [name for name in (*recipe.get('ingredients', {}), *recipe.get('outputs', {})) if name in world.items]
        if recipe and len(set([*pending['items'], *names])) <= LIMITS['items']:
            teach({'recipes': [recipe_id], 'items': names}, 'workshop', work)
    for ident in config.get('reading', []):
        physical = ident in actor.inventory or any(ident in world.rooms[room].items for room in places)
        item = world.items.get(ident, {})
        if not physical or not isinstance(item.get('read_text'), str) or not item['read_text'].strip():
            continue
        table = item.get('knowledge', {})
        if not isinstance(table, dict):
            continue
        values = lambda key: table.get(key, []) if isinstance(table.get(key), list) else []
        local = {'items': [ident, *values('items')][:LIMITS['items']],
                 'rooms': [room for room in values('rooms') if isinstance(room, str) and room in scope],
                 'recipes': []}
        # A recipe names its own ingredients and outputs. If that disclosure
        # would overflow this small initial background, leave it for real play.
        for recipe_id in values('recipes')[:LIMITS['recipes']]:
            if not isinstance(recipe_id, str) or recipe_id not in getattr(world, 'recipes', {}):
                continue
            recipe = world.recipes[recipe_id]
            names = [name for name in (*recipe.get('ingredients', {}), *recipe.get('outputs', {})) if name in world.items]
            if len(set([*pending['items'], *local['items'], *names])) <= LIMITS['items']:
                local['recipes'].append(recipe_id)
                local['items'] = list(dict.fromkeys([*local['items'], *names]))
        # Read recipe details only from the physically available authored book;
        # no list of every recipe or secret prerequisite is generated.
        teach(local, 'item', ident)
    # Preserve every previously learned fact. Initial knowledge has fixed caps;
    # these lists do not mark visits or satisfy any objective/action counter.
    current = knowledge.state(actor)
    for key, values in pending.items():
        current[key].extend(value for value in values if value not in current[key])
    for lesson in training:
        actor.progress.setdefault('skills', {}).setdefault(lesson['skill'], max(_level(definition, lesson['skill']), lesson['level']))
    notes = actor.progress.setdefault('town_talk', {'contacts': {}, 'roads': {}})
    for room, exits in roads.items():
        notes.setdefault('roads', {}).setdefault(room, {}).update({direction: dest for direction, dest in exits.items()
                                                               if direction not in notes.get('roads', {}).get(room, {})})
    saved = dict(version=1, seed=seed, initialized_at=_minute(world), origin='founding' if fresh else 'authored_migration',
                 home_room=home, training=training, interests=interests, sources=sources, rumors=rumors,
                 experiences=deepcopy(config.get('experiences', [])))
    actor.progress[KEY] = saved
    from engine import npc_emotions
    for index, lesson in enumerate(training):
        npc_emotions.founding_experience(world, actor, 'learning encouraging',
                                         event_id='founding:' + seed + ':lesson:' + str(index))
    for index, experience in enumerate(config.get('experiences', [])):
        npc_emotions.founding_experience(world, actor, experience['kind'],
                                         event_id='founding:' + seed + ':experience:' + str(index))
    return True


def interests(world, actor):
    """Prioritize only the caller's already permitted tasks; never enroll here."""
    saved = actor.progress.get(KEY, {})
    return dict(saved.get('interests', {})) if isinstance(saved, dict) else {}


def parameters(definition, rooms):
    """Conservative source parameters for a newly generated founder roster."""
    if 'background' in definition or definition.get('social_profile', {}).get('sentient') is not True:
        return None
    home, work = definition.get('home_room'), _work(definition)
    if home not in rooms:
        return None
    result = dict(version=1, enabled=True, home_room=home, nearby_limit=3)
    role = definition.get('occupation') or definition.get('profession')
    age = definition.get('social_profile', {}).get('age_years')
    tasks = OCCUPATIONS.get(role, ())
    if work in rooms and _range(age, 18, 10000) and tasks:
        result['training'] = [dict(skill=task, minimum=5, maximum=20,
                                   source=dict(kind='workplace', id=work)) for task in tasks]
    return result
