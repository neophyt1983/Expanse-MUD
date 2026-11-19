"""Authored task guilds, shared stock needs and ordinary quest services.

Guild membership is separate from political faction. A guild is an explicitly
enabled ``group.guild`` at authored rooms; this module creates no guildhalls.
Offers must already have been learned from a real NPC or readable item. Shared
stock requests keep their quest ID, fill an existing finite container and pay
from an actual recipient's purse. Time never renews a fulfilled stock need.
"""
from collections import Counter
from copy import copy, deepcopy
from hashlib import sha256
import json
import shlex

from engine import living, quest_progress, relationships, sleep_movement, worldtime

KEY = 'guilds_v1'
NEEDS_KEY = 'guild_needs_v1'
TASK_NAMES = {
    'farming': 'Farming', 'trading': 'Trading', 'journalism': 'Journalism',
    'spellcraft': 'Spellcraft', 'fighting': 'Fighting', 'burglary': 'Burgling',
    'observation': 'Observation', 'lockpicking': 'Lockpicking',
    'assassination': 'Assassination', 'brewing': 'Brewing', 'ranching': 'Ranching',
    'fieldcraft': 'Fieldcraft', 'crafting': 'Crafting', 'cooking': 'Cooking',
    'poetry': 'Poetry', 'painting': 'Painting', 'sculpture': 'Sculpture',
    'architecture': 'Architecture', 'healing': 'Healing',
}


def minute(world):
    saved = getattr(world, 'living_state', {})
    return saved['minute'] if 'minute' in saved else worldtime.initial_minute(world.metadata)


def skill(world, actor, task):
    """Read the same task levels used by physical skills and crafting."""
    from engine import task_skills
    return task_skills.level(world, actor, task)


def tier(difficulty):
    return ('Novice' if difficulty < 20 else 'Apprentice' if difficulty < 40 else
            'Journeyman' if difficulty < 60 else 'Expert' if difficulty < 80 else 'Master')


def definition(world, ident):
    group = world.groups.get(ident, {})
    config = group.get('guild', {})
    return config if isinstance(config, dict) and config.get('enabled') is True else None


def affiliation(quest):
    value = quest.get('guild', {})
    return value if isinstance(value, dict) and value.get('id') else None


def is_need(quest):
    config = affiliation(quest)
    return bool(config and isinstance(config.get('need'), dict) and config['need'].get('kind') == 'stock')


def member(actor, guild_id):
    return guild_id in actor.progress.get(KEY, {}).get('memberships', {})


def _dirty(world, *actors):
    ids = {actor.id for actor in actors if actor.is_player}
    if ids:
        world.dirty_players = getattr(world, 'dirty_players', set()) | ids


def _actor_reason(world, actor):
    if actor is None or world.entities.get(actor.id) is not actor or actor.location not in world.rooms:
        return 'Enter the world before using a guild service.'
    if not living.enabled(world):
        return 'Guild services require this world’s living rules.'
    if not actor.alive or sleep_movement.asleep(world, actor):
        return 'You must be awake and able to act.'
    if not relationships.sentient(world, actor):
        return 'This service is for people able to undertake its work.'
    if actor.progress.get('restrained_until', 0) > minute(world):
        return 'You are restrained and cannot use guild services yet.'
    from engine import city_justice
    case = getattr(world, 'living_state', {}).get(city_justice.KEY, {}).get('cases', {}).get(actor.id, {})
    if case.get('status') in ('awaiting_hearing', 'sentenced'):
        return 'Finish the custody process before undertaking guild work.'
    return ''


def _requirements(world, actor, config):
    if any(quest_progress.status(world, actor, ident) != 'complete'
           for ident in config.get('quests', [])):
        return 'Complete the required quests first.'
    for task, level in config.get('skills', {}).items():
        if skill(world, actor, task) < level:
            return TASK_NAMES.get(task, task.title()) + ' ' + str(level) + ' is required.'
    return ''


def quest_blocked(world, actor, quest):
    """Shared eligibility hook for the ordinary quest engine too."""
    config = affiliation(quest)
    if not config:
        return ''
    guild_id = config['id']
    guild = definition(world, guild_id)
    if guild is None:
        return 'This guild is not offering services in this world.'
    if not member(actor, guild_id):
        return 'Join ' + world.groups[guild_id].get('name', guild_id) + ' first.'
    task = config['skill']
    if skill(world, actor, task) < config.get('difficulty', 0):
        return TASK_NAMES.get(task, task.title()) + ' ' + str(config['difficulty']) + ' is required.'
    return ''


def _present(world, actor, source, room):
    candidates = [person for person in world.entities_in_room(room)
                  if person.id != actor.id and not person.is_player and person.alive
                  and person.location == room and person.source_def == source
                  and relationships.sentient(world, person) and not sleep_movement.asleep(world, person)]
    if len(candidates) != 1:
        return None
    from engine import frontiers
    return None if frontiers.hostile(world, candidates[0], actor) else candidates[0]


def _need(world, actor, quest):
    """Read physical stock and a local recipient without initializing state."""
    spec = affiliation(quest)['need']
    room = spec['room']
    rows = getattr(world, 'room_details', {}).get(room, {}).get('locks', [])
    matches = [row for row in rows if row.get('id') == spec['container'] and not row.get('direction')]
    row = matches[0] if len(matches) == 1 else None
    saved = getattr(world, 'living_state', {}).get('physical_locks', {}).get(room + ':' + spec['container'])
    stock = saved.get('contents', []) if isinstance(saved, dict) else row.get('contents', []) if row else []
    count = stock.count(spec['item'])
    remaining = max(0, spec['target'] - count) if row else 0
    recipient = _present(world, actor, spec['recipient'], room) if room == actor.location and room in world.rooms else None
    ledger = getattr(world, 'living_state', {}).get(NEEDS_KEY, {}).get(quest['id'], {})
    fingerprint = [quest['id'], spec, count, ledger.get('version', 0),
                   recipient.id if recipient else None, recipient.gold if recipient else None]
    revision = int.from_bytes(sha256(json.dumps(fingerprint, sort_keys=True, separators=(',', ':')).encode()).digest()[:6], 'big')
    return dict(spec=spec, row=row, remaining=remaining, recipient=recipient, revision=revision)


def available_again(world, actor, quest):
    return is_need(quest) and _need(world, actor, quest)['remaining'] > 0


def completion_blocked(world, actor, quest, *, readonly=False):
    """Return None for classic quests; stock requests share this public check."""
    if not is_need(quest):
        return None
    reason = (_actor_reason(world, actor) or quest_blocked(world, actor, quest) or
              living.quest_blocked(world, actor, quest, readonly=True))
    if reason:
        return reason
    ordinary = dict(quest)
    ordinary.pop('guild', None)
    viewer = actor
    if readonly:
        viewer = copy(actor)
        viewer.progress = deepcopy(actor.progress)
    reason = living.quest_completion_blocked(world, viewer, ordinary)
    if reason:
        return reason
    need = _need(world, actor, quest)
    spec = need['spec']
    if not need['row']:
        return 'The receiving container is unavailable.'
    if not need['remaining']:
        return 'This shared need has already been met. No more goods or payment are due.'
    if actor.location != spec['room']:
        return 'Deliver this work at ' + world.rooms[spec['room']].name + '.'
    recipient = need['recipient']
    if recipient is None:
        return 'The receiving guild representative is not available here.'
    movable = actor.inventory.count(spec['item']) - list(actor.equipped.values()).count(spec['item'])
    if movable < 1:
        return 'Bring an unequipped ' + world.items[spec['item']].get('name', spec['item']) + ' for the remaining need.'
    if recipient.gold < spec.get('gold_per_unit', 0):
        return 'The representative cannot fund another contribution yet.'
    return ''


def _join_reason(world, actor, guild_id, config):
    if member(actor, guild_id):
        return 'Already a member.'
    return (_actor_reason(world, actor) or
            ('Visit a guild service location.' if actor.location not in config.get('rooms', []) else '') or
            _requirements(world, actor, config.get('requirements', {})) or
            ('You need ' + str(config.get('join_fee', 0)) + ' gold to join.' if actor.gold < config.get('join_fee', 0) else ''))


def _lesson_reason(world, actor, guild_id, config, lesson):
    if not member(actor, guild_id):
        return 'Join this guild first.'
    reason = _actor_reason(world, actor)
    if reason:
        return reason
    if actor.location not in config.get('rooms', []):
        return 'Visit this guild’s service room.'
    saved = actor.progress.get(KEY, {})
    if guild_id + ':' + lesson['id'] in saved.get('lessons', {}):
        return 'You have already completed this lesson.'
    day = minute(world) // worldtime.MINUTES_PER_DAY
    if day <= saved.get('lesson_day', -1):
        return 'One guild lesson per world day. Time rewinding does not renew a lesson.'
    level = skill(world, actor, lesson['skill'])
    if level < lesson.get('min_level', 0):
        return 'Reach skill level ' + str(lesson['min_level']) + ' before this lesson.'
    if level >= lesson['max_level']:
        return 'Your skill is already beyond this lesson.'
    if any(quest_progress.status(world, actor, ident) != 'complete' for ident in lesson.get('requires_quests', [])):
        return 'Complete the lesson’s prerequisite quests first.'
    if actor.gold < lesson.get('cost', 0):
        return 'This lesson costs ' + str(lesson['cost']) + ' gold.'
    if _present(world, actor, lesson['trainer'], actor.location) is None:
        return 'The instructor is not available here.'
    return ''


def _accept_reason(world, actor, quest):
    from engine import quest_discovery
    reason = _actor_reason(world, actor) or living.quest_blocked(world, actor, quest, readonly=True)
    if reason:
        return reason
    if quest['id'] not in quest_discovery.sourced(actor):
        return 'Read the local notice or hear this request from its source first.'
    if quest.get('offer_room') != actor.location:
        return 'Accept this request at its actual offer location.'
    status = actor.progress.get('quests', {}).get(quest['id'])
    if status == 'active':
        return 'Already accepted; continue the actual work.'
    if is_need(quest):
        return '' if _need(world, actor, quest)['remaining'] else 'This shared need has already been met.'
    if status == 'complete' and not quest.get('repeatable'):
        return 'Already completed.'
    if minute(world) - actor.progress.get('quest_times', {}).get(quest['id'], -100000) < quest.get('cooldown_minutes', 1500):
        return 'This work is not available again yet.'
    return ''


def _completion_reason(world, actor, quest):
    reason = _actor_reason(world, actor) or living.quest_blocked(world, actor, quest, readonly=True)
    if reason:
        return reason
    # Legacy accepted-scope baselines can initialize on a completion check.
    # Check a copy so a packet never starts, repairs or completes a quest.
    viewer = copy(actor)
    viewer.progress = deepcopy(actor.progress)
    if is_need(quest):
        return completion_blocked(world, actor, quest, readonly=True)
    return living.quest_completion_blocked(world, viewer, quest)


def projection(world, actor):
    """Only local services and actor-sourced offers; no disclosure or mutation."""
    from engine import quest_discovery
    memberships = [dict(id=ident, name=world.groups[ident].get('name', ident))
                   for ident in actor.progress.get(KEY, {}).get('memberships', {}) if ident in world.groups]
    result = dict(room=actor.location, memberships=memberships, guilds=[])
    known = quest_discovery.sourced(actor) | set(actor.progress.get('quests', {}))
    for guild_id, group in world.groups.items():
        config = definition(world, guild_id)
        if not config or actor.location not in config.get('rooms', []):
            continue
        reason = _join_reason(world, actor, guild_id, config)
        view = dict(id=guild_id, name=group.get('name', guild_id), member=member(actor, guild_id),
                    tasks=[dict(id=task, name=TASK_NAMES.get(task, task.title()), level=skill(world, actor, task)) for task in config.get('tasks', [])],
                    join=dict(enabled=not reason, reason=reason, fee=config.get('join_fee', 0)), lessons=[], quests=[])
        for lesson in config.get('lessons', []):
            reason = _lesson_reason(world, actor, guild_id, config, lesson)
            view['lessons'].append(dict(id=lesson['id'], name=lesson.get('name', lesson['id']), skill=lesson['skill'],
                level=skill(world, actor, lesson['skill']), min_level=lesson.get('min_level', 0), max_level=lesson['max_level'],
                gain=lesson.get('gain', 1), cost=lesson.get('cost', 0), enabled=not reason, reason=reason))
        for ident in sorted(known):
            quest = world.quests.get(ident, {})
            affiliation_config = affiliation(quest)
            if not affiliation_config or affiliation_config['id'] != guild_id:
                continue
            task = affiliation_config['skill']
            difficulty = affiliation_config.get('difficulty', 0)
            status = actor.progress.get('quests', {}).get(ident, 'available')
            accept_reason = _accept_reason(world, actor, quest)
            complete_reason = _completion_reason(world, actor, quest)
            need = _need(world, actor, quest) if is_need(quest) else None
            view['quests'].append(dict(id=ident, name=quest['name'], description=quest.get('description', ''),
                skill=task, difficulty=difficulty, tier=tier(difficulty), status=status,
                remaining=need['remaining'] if need else None, revision=need['revision'] if need else None,
                accept=dict(enabled=not accept_reason, reason=accept_reason),
                complete=dict(enabled=not complete_reason, reason=complete_reason),
                reward=(str(need['spec'].get('gold_per_unit', 0)) + ' gold per accepted unit from the representative’s funds'
                        if need else str(quest.get('reward_gold', 0)) + ' gold; stated quest rewards')))
        result['guilds'].append(view)
    return result


def _complete_need(world, actor, quest):
    reason = completion_blocked(world, actor, quest)
    if reason:
        raise ValueError(reason)
    need = _need(world, actor, quest)
    spec, recipient = need['spec'], need['recipient']
    rate = spec.get('gold_per_unit', 0)
    quantity = min(need['remaining'], spec.get('batch', spec['target']),
                   actor.inventory.count(spec['item']) - list(actor.equipped.values()).count(spec['item']))
    if rate:
        quantity = min(quantity, recipient.gold // rate)
    if quantity < 1:
        raise ValueError('No contribution is currently due or funded.')
    remaining = list(actor.inventory)
    for _ in range(quantity):
        remaining.remove(spec['item'])
    from engine import locks
    stock = locks.saved(world, spec['room'], need['row'])
    received = list(stock['contents']) + [spec['item']] * quantity
    payment = quantity * rate
    # The entire finite transfer is prepared and rechecked synchronously.
    actor.inventory[:] = remaining
    stock['contents'][:] = received
    recipient.gold -= payment
    actor.gold += payment
    ledger = living.state(world).setdefault(NEEDS_KEY, {}).setdefault(quest['id'], {'version': 0, 'delivered': 0})
    ledger['version'] += 1
    ledger['delivered'] += quantity
    ledger['remaining'] = need['remaining'] - quantity
    ledger['last_contributor'] = actor.id
    ledger['updated'] = minute(world)
    own = actor.progress.setdefault(KEY, {})
    credit = own.setdefault('contributions', {}).setdefault(quest['id'], 0)
    own['contributions'][quest['id']] = credit + quantity
    if ledger['remaining'] == 0:
        actor.progress.setdefault('quests', {})[quest['id']] = 'complete'
        actor.progress.setdefault('quest_times', {})[quest['id']] = minute(world)
    config = affiliation(quest)
    from engine import task_skills
    task_skills.practice(world, actor, config['skill'], difficulty=config.get('difficulty', 0),
                         effort=min(5, quantity), event_id='guild:' + quest['id'] + ':' + str(ledger['version']))
    _dirty(world, actor, recipient)
    return ('Delivered ' + str(quantity) + ' × ' + world.items[spec['item']].get('name', spec['item']) +
            '. Received ' + str(payment) + ' gold. Shared need remaining: ' + str(ledger['remaining']) + '.')


def act(world, actor, guild_id, action, *, offer_id=None, expected_revision=None):
    """Authoritative service for a real player or explicitly directed NPC."""
    reason = _actor_reason(world, actor)
    if reason:
        raise ValueError(reason)
    config = definition(world, guild_id) if isinstance(guild_id, str) else None
    if config is None or actor.location not in config.get('rooms', []):
        raise ValueError('That guild does not offer services here.')
    if action == 'join':
        reason = _join_reason(world, actor, guild_id, config)
        if reason:
            raise ValueError(reason)
        fee = config.get('join_fee', 0)
        actor.gold -= fee
        saved = actor.progress.setdefault(KEY, {})
        saved.setdefault('memberships', {})[guild_id] = {'joined': minute(world)}
        treasury = living.state(world).setdefault('guild_treasuries_v1', {})
        treasury[guild_id] = treasury.get(guild_id, 0) + fee
        _dirty(world, actor)
        return 'You joined ' + world.groups[guild_id].get('name', guild_id) + '.'
    if action == 'learn':
        lesson = next((row for row in config.get('lessons', []) if row['id'] == offer_id), None)
        if lesson is None:
            raise ValueError('That lesson is not offered by this guild.')
        reason = _lesson_reason(world, actor, guild_id, config, lesson)
        if reason:
            raise ValueError(reason)
        instructor = _present(world, actor, lesson['trainer'], actor.location)
        cost = lesson.get('cost', 0)
        actor.gold -= cost
        instructor.gold += cost
        from engine import task_skills
        gained = task_skills.training(world, actor, lesson['skill'], lesson.get('gain', 1),
                                     difficulty=lesson.get('min_level', 0), ceiling=lesson['max_level'],
                                     event_id='guild-lesson:' + guild_id + ':' + lesson['id'])
        level = skill(world, actor, lesson['skill'])
        saved = actor.progress.setdefault(KEY, {})
        saved.setdefault('lessons', {})[guild_id + ':' + lesson['id']] = minute(world)
        saved['lesson_day'] = minute(world) // worldtime.MINUTES_PER_DAY
        _dirty(world, actor, instructor)
        return ('Lesson completed. Practised ' + TASK_NAMES.get(lesson['skill'], lesson['skill'].title()) +
                '; level ' + str(level) + ' (' + str(gained) + ' levels gained). ' +
                'Higher skill levels require more practice.')
    if action not in ('accept', 'complete'):
        raise ValueError('Choose join, learn, accept or complete.')
    quest = world.quests.get(offer_id, {}) if isinstance(offer_id, str) else {}
    if not affiliation(quest) or affiliation(quest)['id'] != guild_id:
        raise ValueError('That request is not offered by this guild.')
    if expected_revision is not None:
        if type(expected_revision) is not int or not is_need(quest) or expected_revision != _need(world, actor, quest)['revision']:
            raise ValueError('The shared need or payment changed. Refresh guild work before continuing.')
    if action == 'accept':
        reason = _accept_reason(world, actor, quest)
        if reason:
            raise ValueError(reason)
        if is_need(quest):
            from engine import knowledge, quest_chains
            quest_chains.start(world, actor, quest)
            actor.progress.setdefault('quests', {})[quest['id']] = 'active'
            knowledge.quest(world, actor, quest)
            _dirty(world, actor)
            return 'Quest accepted. ' + quest.get('description', '')
    elif is_need(quest):
        return _complete_need(world, actor, quest)
    from engine.commands import CommandContext
    previous = actor.progress.get('quests', {}).get(quest['id'])
    text = living.quest_command(CommandContext(world, actor, world.rooms[actor.location]), quest['id'], action)
    if action == 'complete' and previous == 'active' and actor.progress.get('quests', {}).get(quest['id']) == 'complete':
        from engine import task_skills
        task_skills.practice(world, actor, affiliation(quest)['skill'], difficulty=affiliation(quest).get('difficulty', 0),
                             effort=1, event_id='guild-complete:' + quest['id'] + ':' + str(actor.progress.get('quest_times', {}).get(quest['id'])))
    _dirty(world, actor)
    return text


def command(ctx, args):
    if not args.strip():
        ctx.time_accounted = True
        view = projection(ctx.world, ctx.player)
        return '\n'.join(group['name'] + (' — member' if group['member'] else ' — open for eligible applicants')
                         for group in view['guilds']) or 'No guild services are available here.'
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        raise ValueError('Close the quotes around guild and offer IDs.') from exc
    if not 2 <= len(parts) <= 4:
        raise ValueError('Use guild <join|learn|accept|complete> "<guild-id>" ["<offer-id>"] [revision].')
    action, guild_id = parts[:2]
    if (action == 'join' and len(parts) != 2) or (action in ('learn', 'accept', 'complete') and len(parts) < 3):
        raise ValueError('Choose the actual guild and offered lesson or request.')
    try:
        revision = int(parts[3]) if len(parts) == 4 else None
    except ValueError as exc:
        raise ValueError('Use the current numeric need revision.') from exc
    return act(ctx.world, ctx.player, guild_id, action,
               offer_id=parts[2] if len(parts) > 2 else None, expected_revision=revision)


def register(registry):
    from engine.commands import Command
    registry.register(Command('guild', 'Visit task guild services and persistent work',
        'guild [join|learn|accept|complete] "<guild-id>" ["<offer-id>"] [revision]', command,
        example='guild', aliases=['guilds']))


def validate(data):
    from engine.guild_rules import validate as check
    return check(data)


def step(world, actor):
    from engine.guild_npc import step as advance
    return advance(world, actor)
