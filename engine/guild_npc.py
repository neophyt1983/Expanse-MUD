"""Opted-in NPC guild work using remembered places and real local actions.

One operation is attempted per game minute. No global goal/target search,
teleport, simulated objective credit, or invented stock is permitted. An NPC
may wait for information or an unsupported objective; normal external events
can satisfy it later. Exploration follows only a currently visible open exit.
"""
from collections import deque
from hashlib import sha256
import json

from engine import frontiers, guilds, knowledge, living, quest_discovery, quest_progress, relationships, sleep_movement

KEY = 'guild_work_v1'


def _memory(actor):
    return actor.progress.setdefault(KEY, {'sources': {}, 'routes': {}, 'items': {}, 'resources': {}, 'people': {}})


def _observe(world, actor):
    saved = _memory(actor)
    room = world.rooms[actor.location]
    if room.id not in actor.explored_rooms:
        actor.explored_rooms.append(room.id)
    edges = [[direction, target] for direction, target in room.exits.items()
             if target in world.rooms and (world.rooms[target].map_visibility != 'hidden' or target in actor.explored_rooms)]
    saved.setdefault('routes', {})[room.id] = edges
    knowledge.teach(world, actor, {'rooms': [room.id] + [target for _, target in edges],
                                   'items': list(room.items) + list(actor.inventory)})
    for item in room.items:
        saved.setdefault('items', {}).setdefault(item, [])
        if room.id not in saved['items'][item]:
            saved['items'][item].append(room.id)
    details = getattr(world, 'room_details', {}).get(room.id, {})
    for ident in details.get('resources', []):
        if ident in getattr(world, 'resources', {}):
            saved.setdefault('resources', {}).setdefault(ident, [])
            if room.id not in saved['resources'][ident]:
                saved['resources'][ident].append(room.id)
    recipes = details.get('workshop', {}).get('recipes', [])
    knowledge.teach(world, actor, {'recipes': recipes})
    for person in world.entities_in_room(room.id):
        if person.id != actor.id and not person.is_player and person.source_def:
            saved.setdefault('people', {})[person.source_def] = room.id


def route(world, actor, target):
    """Search only actually observed edges, then check their current barriers."""
    if actor.location == target:
        return []
    known = set(actor.progress.get('knowledge', {}).get('rooms', []))
    if target not in known:
        return None
    routes = actor.progress.get(KEY, {}).get('routes', {})
    pending = deque([actor.location])
    previous = {actor.location: None}
    while pending and len(previous) <= 512:
        source = pending.popleft()
        for direction, destination in routes.get(source, []):
            if (destination not in known or destination in previous or source not in world.rooms or
                    world.rooms[source].exits.get(direction) != destination or destination not in world.rooms or
                    frontiers.blocked(world, source, direction, actor)):
                continue
            previous[destination] = (source, direction)
            if destination == target:
                steps = []
                while previous[destination] is not None:
                    origin, edge = previous[destination]
                    steps.append((origin, edge, destination))
                    destination = origin
                return list(reversed(steps))
            pending.append(destination)
    return None


def _move(world, actor, target):
    path = route(world, actor, target)
    if not path:
        return False
    destination = path[0][2]
    if not world.move_entity(actor.id, destination):
        return False
    # The common World hook intentionally counts player visits only. This
    # records the NPC's real successful arrival, never an intended destination.
    counts = actor.progress.setdefault('quest_visits', {})
    counts[destination] = counts.get(destination, 0) + 1
    actor.activity = 'travelling for guild work'
    _observe(world, actor)
    return True


def read(world, actor, item_id):
    if item_id not in actor.inventory + world.rooms[actor.location].items:
        raise ValueError('Read a real local or carried document first.')
    item = world.items.get(item_id, {})
    if not item.get('read_text'):
        raise ValueError('That item has no readable instructions.')
    from engine.commands import CommandContext, _cmd_read
    text = _cmd_read(CommandContext(world, actor, world.rooms[actor.location]), item_id)
    actor.activity = 'reading ' + item.get('name', item_id) + ' for guild work'
    return text


def converse(world, actor, target_id):
    person = world.entities.get(target_id)
    if (person is None or person.id == actor.id or person.is_player or not person.alive or
            person.location != actor.location or sleep_movement.asleep(world, person) or
            not relationships.sentient(world, person) or frontiers.hostile(world, person, actor)):
        raise ValueError('Speak to an awake, willing person actually here.')
    # The information comes from this person's actual authored reply. This is
    # an NPC-to-NPC interaction and never supplies a player's dialogue.
    quest_progress.talk(actor, person.source_def)
    talked = actor.progress.setdefault('talked_to', [])
    if person.source_def not in talked:
        talked.append(person.source_def)
    knowledge.from_npc(world, actor, person)
    definition = world.npcs.get(person.source_def, {})
    dialogue = definition.get('dialogue', '')
    if isinstance(dialogue, str):
        knowledge.from_text(world, actor, dialogue, source=('npc', person.source_def))
    actor.activity = 'asking ' + person.name + ' about guild work'
    text = actor.name + ' asks ' + person.name + ' about the work and listens to the reply.'
    world.runtime_notifications = (getattr(world, 'runtime_notifications', []) +
                                  [(actor.location, text, None, {'role': 'npc', 'emphasis': 'normal'})])[-500:]
    return text


def _source(world, actor):
    saved = _memory(actor)
    seen = saved.setdefault('sources', {})
    eligibility = [actor.progress.get('skills', {}), actor.progress.get('quests', {}),
                   actor.progress.get(guilds.KEY, {}).get('memberships', {})]
    for ident in dict.fromkeys(actor.inventory + world.rooms[actor.location].items):
        item = world.items.get(ident, {})
        table = item.get('knowledge', {})
        if not item.get('read_text') or not table:
            continue
        token = 'item:' + ident
        revision = sha256(json.dumps([item.get('read_text'), table, eligibility], sort_keys=True).encode()).hexdigest()[:16]
        if seen.get(token) != revision:
            read(world, actor, ident)
            seen[token] = revision
            return True
    for person in world.entities_in_room(actor.location):
        if person.id == actor.id or person.is_player:
            continue
        table = world.npcs.get(person.source_def, {}).get('knowledge', {})
        if not table:
            continue
        token = 'npc:' + person.id
        revision = sha256(json.dumps([table, eligibility], sort_keys=True).encode()).hexdigest()[:16]
        if seen.get(token) == revision:
            continue
        try:
            converse(world, actor, person.id)
        except ValueError:
            continue
        seen[token] = revision
        return True
    return False


def _execute(world, actor, verb, ident):
    from engine.commands import CommandContext
    saved = _memory(actor)
    operation = saved.get('operation', {})
    if (operation.get('verb'), operation.get('id'), operation.get('room')) != (verb, ident, actor.location):
        definition = (getattr(world, 'resources', {}).get(ident, {}) if verb == 'gather' else
                      getattr(world, 'recipes', {}).get(ident, {}))
        duration = max(1, int(definition.get('gather_minutes' if verb == 'gather' else 'minutes', 1)))
        saved['operation'] = dict(verb=verb, id=ident, room=actor.location, due=guilds.minute(world) + duration)
        actor.activity = 'working on ' + ident + ' for the guild'
        return True
    if guilds.minute(world) < operation['due']:
        return True
    saved.pop('operation', None)
    counter = verb + ':' + ident
    before = actor.progress.get('actions', {}).get(counter, 0)
    old = getattr(world, '_community_simulating', False)
    world._community_simulating = True
    try:
        text = living.command(CommandContext(world, actor, world.rooms[actor.location]), ident, verb)
    finally:
        world._community_simulating = old
    changed = actor.progress.get('actions', {}).get(counter, 0) > before
    _memory(actor)['note'] = text
    if changed:
        actor.activity = ('gathering ' if verb == 'gather' else 'making ') + ident + ' for guild work'
    return changed


def _gather(world, actor, resource_id):
    places = actor.progress.get(KEY, {}).get('resources', {}).get(resource_id, [])
    for room in places:
        if room == actor.location:
            from engine import gathering
            definition = getattr(world, 'resources', {}).get(resource_id, {})
            if resource_id in getattr(world, 'room_details', {}).get(room, {}).get('resources', []) and not gathering.resource_state(world, actor, room, definition):
                return _execute(world, actor, 'gather', resource_id)
        elif _move(world, actor, room):
            return True
    return False


def _supply(world, actor, item_id, *, depth=0, seen=()):
    if depth > 4 or item_id in seen:
        return False
    for resource in actor.progress.get(KEY, {}).get('resources', {}):
        if item_id in getattr(world, 'resources', {}).get(resource, {}).get('yields', {}) and _gather(world, actor, resource):
            return True
    # A known recipe is information legitimately learned; unseen recipes are
    # never searched even though the engine's catalog contains them.
    for ident in actor.progress.get('knowledge', {}).get('recipes', []):
        recipe = getattr(world, 'recipes', {}).get(ident, {})
        if item_id not in recipe.get('outputs', {}):
            continue
        if _craft(world, actor, ident, depth=depth + 1, seen=(*seen, item_id)):
            return True
    return False


def _craft(world, actor, ident, *, depth=0, seen=()):
    if ident not in actor.progress.get('knowledge', {}).get('recipes', []):
        return False
    recipe = getattr(world, 'recipes', {}).get(ident, {})
    for item, count in recipe.get('ingredients', {}).items():
        if actor.inventory.count(item) < count:
            return _supply(world, actor, item, depth=depth, seen=seen)
    station = recipe.get('station', 'hand')
    if station != 'hand' and station not in getattr(world, 'room_details', {}).get(actor.location, {}).get('facilities', []):
        for room in actor.explored_rooms:
            if room in world.rooms and station in getattr(world, 'room_details', {}).get(room, {}).get('facilities', []) and _move(world, actor, room):
                return True
        return False
    return _execute(world, actor, 'cook' if recipe.get('kind') == 'cooking' else 'craft', ident)


def _talk_goal(world, actor, source):
    candidates = [person for person in world.entities_in_room(actor.location)
                  if person.source_def == source and person.id != actor.id]
    for person in candidates:
        try:
            converse(world, actor, person.id)
            return True
        except ValueError:
            continue
    remembered = actor.progress.get(KEY, {}).get('people', {}).get(source)
    return bool(remembered and remembered != actor.location and _move(world, actor, remembered))


def _read_goal(world, actor, item):
    if item in actor.inventory + world.rooms[actor.location].items:
        try:
            read(world, actor, item)
            return True
        except ValueError:
            return False
    return any(_move(world, actor, room) for room in actor.progress.get(KEY, {}).get('items', {}).get(item, []) if room != actor.location)


def _work(world, actor, quest):
    config = guilds.affiliation(quest)
    if living.quest_blocked(world, actor, quest, readonly=True):
        return False
    if not guilds._completion_reason(world, actor, quest):
        text = guilds.act(world, actor, config['id'], 'complete', offer_id=quest['id'])
        _memory(actor)['note'] = text
        actor.activity = 'completing actual guild work'
        return True
    for key, count in quest.get('actions', {}).items():
        if quest_progress.count(actor, quest, 'actions', key) >= count:
            continue
        verb, _, ident = key.partition(':')
        if verb == 'read' and _read_goal(world, actor, ident):
            return True
        if verb == 'gather' and _gather(world, actor, ident):
            return True
        if verb in ('craft', 'cook') and _craft(world, actor, ident):
            return True
    for source in quest.get('talk_to', []):
        if not quest_progress.count(actor, quest, 'talks', source) and _talk_goal(world, actor, source):
            return True
    for witness in quest.get('witnesses', []):
        if not quest_progress.witnessed(actor, quest, witness) and (_read_goal(world, actor, witness['read_item']) or _talk_goal(world, actor, witness['npc'])):
            return True
    for room in quest.get('visit_rooms', []):
        if not quest_progress.count(actor, quest, 'visits', room) and _move(world, actor, room):
            return True
    goods = dict(quest.get('required_items', {}))
    if guilds.is_need(quest):
        need = guilds._need(world, actor, quest)
        if need['remaining']:
            goods[need['spec']['item']] = 1
    for item, count in goods.items():
        if actor.inventory.count(item) < count and _supply(world, actor, item):
            return True
    # Return only when the material and objective work really exists. A missing
    # route, person or capability never grants its objective as a shortcut.
    if all(actor.inventory.count(item) >= count for item, count in goods.items()):
        target = quest.get('turn_in_room')
        if target and actor.location != target and _move(world, actor, target):
            return True
    return False


def _explore(world, actor):
    remembered = actor.progress.get(KEY, {}).get('routes', {})
    locations = [actor.location] + [room for room in remembered if room != actor.location]
    for room in locations:
        for direction, target in remembered.get(room, []):
            if (target in actor.explored_rooms or target not in world.rooms or
                    world.rooms[target].map_visibility == 'hidden' or frontiers.blocked(world, room, direction, actor)):
                continue
            if _move(world, actor, target if room == actor.location else room):
                return True
    return False


def step(world, actor):
    if actor.is_player:
        return False
    plan = world.npcs.get(actor.source_def, {}).get('guild_plan', {})
    if not isinstance(plan, dict) or plan.get('enabled') is not True or guilds._actor_reason(world, actor):
        return False
    from engine import npc_attention
    if npc_attention.paused(world, actor):
        return False
    saved = _memory(actor)
    now = guilds.minute(world)
    if now <= saved.get('last_minute', -1):
        return False
    saved['last_minute'] = now
    _observe(world, actor)
    choices = [ident for ident in plan.get('guilds', []) if guilds.definition(world, ident)]
    # Background interests can order an authored choice, never enroll an NPC
    # into an unrequested guild or reveal an unavailable offer.
    from engine import npc_backgrounds
    interests = npc_backgrounds.interests(world, actor)
    if isinstance(interests, dict):
        choices.sort(key=lambda ident: -sum(value for task, value in interests.items()
                    if task in guilds.definition(world, ident).get('tasks', []) and type(value) in (int, float)))
    active = [world.quests[ident] for ident, status in actor.progress.get('quests', {}).items()
              if status == 'active' and ident in world.quests and guilds.affiliation(world.quests[ident])
              and guilds.affiliation(world.quests[ident])['id'] in choices]
    for quest in active:
        if guilds.is_need(quest) and not guilds._need(world, actor, quest)['remaining']:
            saved['note'] = 'The shared need is met. No duplicate hand-in is due.'
            continue
        if _work(world, actor, quest):
            return True
        if _source(world, actor):
            return True
        if plan.get('explore') is True and _explore(world, actor):
            return True
        actor.activity = 'awaiting known directions, supplies or an unsupported guild objective'
        saved['note'] = actor.activity
        return True
    for ident in choices:
        config = guilds.definition(world, ident)
        if actor.location not in config.get('rooms', []):
            continue
        if not guilds.member(actor, ident) and not guilds._join_reason(world, actor, ident, config):
            guilds.act(world, actor, ident, 'join')
            actor.activity = 'joining an authored task guild'
            return True
    if _source(world, actor):
        return True
    if plan.get('quests', True):
        for ident in sorted(quest_discovery.sourced(actor)):
            quest = world.quests.get(ident, {})
            config = guilds.affiliation(quest)
            if not config or config['id'] not in choices:
                continue
            if not guilds._accept_reason(world, actor, quest):
                guilds.act(world, actor, config['id'], 'accept', offer_id=ident)
                actor.activity = 'accepting a learned guild request'
                return True
    if plan.get('learn', True):
        for ident in choices:
            config = guilds.definition(world, ident)
            for lesson in config.get('lessons', []):
                if not guilds._lesson_reason(world, actor, ident, config, lesson):
                    guilds.act(world, actor, ident, 'learn', offer_id=lesson['id'])
                    actor.activity = 'studying an authored guild lesson'
                    return True
    return bool(plan.get('explore') is True and _explore(world, actor))
