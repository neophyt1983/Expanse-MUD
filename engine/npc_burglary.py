"""Explicit local theft plans; ordinary residents never acquire this behavior.

An NPC's existing schedule supplies all travel. A plan can attempt one real
nearby target per world day, through the same transfer used by players. The
budget survives saves and cannot be reset by rewinding the game clock.

Example Creator setting (quantity is the requested maximum):
  burglary_plan = {"enabled": True, "targets": [
    {"room": "market", "kind": "actor", "npc": "merchant",
     "item": "bread", "quantity": 3},
    {"room": "kitchen", "kind": "container", "id": "pantry",
     "item": "bread", "quantity": 3}]}

An actor target uses exactly one of `npc` (a unique local source definition)
or `entity` (an exact runtime entity ID). Names and remote actors never match.
Player victims additionally require the host's current online-player IDs.
"""
from engine import living, worldtime

KEY = 'npc_burglary_v1'
MAX_TARGETS = 16


def _target_issues(target, where):
    if not isinstance(target, dict):
        return [where + ': target must be an object']
    issues = []
    kind = target.get('kind')
    fields = {'room', 'kind', 'item', 'quantity'}
    if kind == 'container':
        fields.add('id')
        selectors = ('id',)
    elif kind == 'actor':
        fields.update(('npc', 'entity'))
        selectors = tuple(key for key in ('npc', 'entity') if key in target)
        if len(selectors) != 1:
            issues.append(where + ': actor needs exactly one npc or entity selector')
    else:
        selectors = ()
        issues.append(where + ': kind must be container or actor')
    for key in ('room', 'item', *selectors):
        if not isinstance(target.get(key), str) or not target[key].strip():
            issues.append(where + ': ' + key + ' must be a nonempty exact ID')
    if set(target) - fields:
        issues.append(where + ': unsupported target fields')
    quantity = target.get('quantity', 1)
    from engine.burglary import MAX_QUANTITY
    if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
        issues.append(where + ': quantity must be a positive whole maximum')
    return issues


def _plan_issues(plan, where):
    if not isinstance(plan, dict):
        return [where + ': burglary_plan must be an object']
    issues = []
    if set(plan) - {'enabled', 'targets'}:
        issues.append(where + ': unsupported burglary_plan fields')
    if 'enabled' in plan and type(plan['enabled']) is not bool:
        issues.append(where + ': burglary_plan.enabled must be boolean')
    targets = plan.get('targets', [])
    if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
        return issues + [where + ': burglary_plan.targets must be a list of at most 16 targets']
    if plan.get('enabled') is True and not targets:
        issues.append(where + ': enabled burglary_plan needs a target')
    for index, target in enumerate(targets):
        issues.extend(_target_issues(target, where + ': burglary target ' + str(index + 1)))
    return issues


def validate(data):
    """Validate only explicit author settings; never create or alter targets."""
    issues = []
    rooms = {row['id']: row for row in data.get('room', [])}
    items = {row['id'] for row in data.get('item', [])}
    npcs = {row['id'] for row in data.get('npc', [])}
    for kind in ('npc', 'class'):
        for definition in data.get(kind, []):
            for key in ('burglary', 'observation', 'theft_difficulty'):
                if key in definition and (type(definition[key]) is not int or not 0 <= definition[key] <= 100):
                    issues.append(definition['id'] + ': ' + key + ' must be 0-100')
    for room in rooms.values():
        rows = room.get('locks', [])
        if not isinstance(rows, list):
            continue  # The existing physical-lock validator handles this field.
        for row in rows:
            if (isinstance(row, dict) and 'theft_difficulty' in row
                    and (type(row['theft_difficulty']) is not int or not 0 <= row['theft_difficulty'] <= 100)):
                issues.append(room['id'] + ': lock ' + str(row.get('id', '')) + ': theft_difficulty must be 0-100')
    for definition in data.get('npc', []):
        if 'burglary_plan' not in definition:
            continue
        plan = definition['burglary_plan']
        errors = _plan_issues(plan, definition['id'])
        issues.extend(errors)
        if errors:
            continue
        for target in plan.get('targets', []):
            where = definition['id'] + ': burglary target'
            room = rooms.get(target['room'])
            if room is None:
                issues.append(where + ': room is missing')
            if target['item'] not in items:
                issues.append(where + ': item is missing')
            if target['kind'] == 'actor':
                if 'npc' in target and target['npc'] not in npcs:
                    issues.append(where + ': NPC source is missing')
            elif room is not None:
                rows = room.get('locks', [])
                matches = [row for row in (rows if isinstance(rows, list) else [])
                           if isinstance(row, dict) and row.get('id') == target['id']]
                if len(matches) != 1 or matches[0].get('direction'):
                    issues.append(where + ': container is missing or is a door')
    return issues


def _local_actor(world, actor, target):
    if 'entity' in target:
        victim = world.entities.get(target['entity'])
        return victim if (victim and victim is not actor and victim.alive
                          and victim.location == actor.location) else None
    matches = [person for person in world.entities_in_room(actor.location)
               if person is not actor and not person.is_player and person.alive
               and person.source_def == target['npc']]
    return matches[0] if len(matches) == 1 else None


def step(world, actor, *, online_players=(), rng=None):
    """Use at most one eligible local plan target, without moving any actor.

    Return True when the daily action budget was consumed. Stale item choices,
    locks and unsuccessful rolls consume that budget too; they never trigger
    a retry loop. Missing/ambiguous people are not replaced by a guessed target.
    The caller runs this after ordinary family, quest and companion priorities.
    """
    if not living.enabled(world) or actor.is_player or not actor.alive:
        return False
    plan = world.npcs.get(actor.source_def, {}).get('burglary_plan', {})
    if not isinstance(plan, dict) or plan.get('enabled') is not True or _plan_issues(plan, actor.id):
        return False
    from engine import city_justice, npc_attention, sleep_movement
    now = int(living.state(world)['minute'])
    if (sleep_movement.asleep(world, actor) or npc_attention.paused(world, actor)
            or actor.progress.get('restrained_until', 0) > now
            or city_justice.confined(world, actor)
            or actor.progress.get('companion_owner') or actor.progress.get('retired')):
        return False
    saved = actor.progress.get(KEY, {})
    # Invalid saved budget data fails closed instead of granting a new attempt.
    if (not isinstance(saved, dict) or type(saved.get('day', -1)) is not int
            or type(saved.get('cursor', 0)) is not int or saved.get('cursor', 0) < 0):
        return False
    day = now // worldtime.MINUTES_PER_DAY
    if day <= saved.get('day', -1):
        return False
    targets = plan['targets']
    start = saved.get('cursor', 0) % len(targets)
    from engine import locks, theft
    for offset in range(len(targets)):
        index = (start + offset) % len(targets)
        target = targets[index]
        if target['room'] != actor.location:
            continue
        victim = None
        if target['kind'] == 'actor':
            victim = _local_actor(world, actor, target)
            if victim is None:
                continue
        else:
            matches = [(origin, row) for origin, row in locks.local(world, actor.location)
                       if origin == target['room'] and row['id'] == target['id']
                       and not row.get('direction')]
            if len(matches) != 1:
                continue
            origin, row = matches[0]
            if locks.permitted(world, actor, row):
                continue
        actor.progress[KEY] = {'day': day, 'cursor': (index + 1) % len(targets)}
        try:
            if victim is not None:
                theft.transfer(world, actor, victim.id, target['item'], target.get('quantity', 1),
                               online_players=online_players, rng=rng)
            else:
                # Container contents are only considered at the real fixture.
                # The shared action still checks its live lock and permissions.
                contents = locks.saved(world, origin, row)['contents']
                quantity = min(target.get('quantity', 1), contents.count(target['item']))
                if quantity:
                    locks.transfer(world, actor, origin + ':' + row['id'], target['item'], quantity, rng=rng)
        except ValueError:
            # An unavailable item or guarded action is a failed plan, not a new
            # roll every minute. Core validates before changing either inventory.
            pass
        return True
    return False
