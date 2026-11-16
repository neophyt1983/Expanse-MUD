"""Short-lived, authoritative presentation of completed magical actions.

The queue is deliberately outside saved gameplay state. A socket starts at the
current cursor and can only receive an event it actually witnessed locally.
"""
from copy import deepcopy
import math
import re
import time
import uuid

STYLES = ('glow', 'ground_rise', 'portal_rise', 'projectile', 'ward', 'burst', 'fade')
MAX_EVENTS = 256
MAX_QUEUE_AGE = 10.0


def _issues(value, label):
    if value in (None, {}):
        return []
    if not isinstance(value, dict):
        return [label + ': presentation must be an object']
    issues = []
    if type(value.get('version')) is not int or value['version'] != 1:
        issues.append(label + ': presentation version must be 1')
    if value.get('style') not in STYLES:
        issues.append(label + ': unsupported presentation style')
    colors = value.get('colors')
    if not isinstance(colors, list) or not 1 <= len(colors) <= 3 or any(
            not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors):
        issues.append(label + ': presentation colors require 1–3 #RRGGBB values')
    for key, lo, hi in [('duration_ms', 300, 5000), ('particles', 0, 24)]:
        n = value.get(key)
        if type(n) is not int or not lo <= n <= hi:
            issues.append(label + f': presentation {key} must be an integer from {lo} to {hi}')
    scale = value.get('scale')
    if type(scale) not in (int, float) or not .5 <= scale <= 2 or not math.isfinite(scale):
        issues.append(label + ': presentation scale must be finite and from 0.5 to 2')
    return issues


def validate(data, metadata=None):
    issues = []
    for kind, field in [('ability', 'presentation'), ('npc', 'summon_presentation')]:
        for row in data.get(kind, []):
            issues.extend(_issues(row.get(field), str(row.get('id', kind))))
    return issues


def reset(world):
    world._magic_visuals = dict(session=uuid.uuid4().hex, sequence=0, events=[])


def cursor(world):
    state = getattr(world, '_magic_visuals', {})
    return dict(session=state.get('session'), sequence=state.get('sequence', 0))


def witnesses(world, room_id):
    room = world.rooms.get(room_id)
    if room is None:
        return ()
    return tuple(dict.fromkeys(e.id for eid in room.entities
                 if (e := world.entities.get(eid)) is not None
                 and e.is_player and e.alive and e.location == room_id))


def record(world, presentation, source, targets=(), *, spawned=None,
           room_id=None, witnesses=None, phase=None):
    """Record real engine outcomes, never caller-supplied actor/presentation IDs."""
    from engine.core import Entity
    if not presentation or _issues(presentation, 'magic'):
        return None
    if not isinstance(source, Entity) or not isinstance(targets, (tuple, list)):
        return None
    if any(not isinstance(e, Entity) for e in targets):
        return None
    if spawned is not None and not isinstance(spawned, Entity):
        return None
    room_id = room_id or source.location
    if room_id not in world.rooms or phase not in (None, 'departure', 'arrival'):
        return None
    if not getattr(world, '_magic_visuals', None):
        reset(world)
    state = world._magic_visuals
    now = time.monotonic()
    state['events'] = [e for e in state['events'] if now - e['_created'] <= MAX_QUEUE_AGE]
    state['sequence'] += 1
    event = dict(type='visual_effect', event_id=state['session'] + ':' + str(state['sequence']),
                 session=state['session'], sequence=state['sequence'], room_id=room_id,
                 source_id=source.id, target_ids=list(dict.fromkeys(e.id for e in targets)),
                 presentation={key:deepcopy(presentation[key]) for key in
                               ('version','style','colors','duration_ms','scale','particles')}, _created=now, _played=None,
                 _witnesses=tuple(witnesses) if witnesses is not None else globals()['witnesses'](world, room_id))
    if spawned is not None:
        event['spawned_id'] = spawned.id
    if phase is not None:
        event['phase'] = phase
    state['events'].append(event)
    state['events'] = state['events'][-MAX_EVENTS:]
    return {k: deepcopy(v) for k, v in event.items() if not k.startswith('_')}


def _candidates(world, viewer, since, now):
    state = getattr(world, '_magic_visuals', {})
    if not isinstance(since, dict) or since.get('session') != state.get('session'):
        return ()
    # A player who was alive in the witness snapshot can see the blow that
    # killed them. Binding a new socket at the current cursor prevents replay.
    if viewer is None or not viewer.is_player:
        return ()
    if world.entities.get(viewer.id) is not viewer:
        return ()
    sequence = since.get('sequence', 0)
    if type(sequence) is not int or sequence < 0:
        return ()
    return (event for event in state.get('events', ())
            if sequence < event['sequence'] and now - event['_created'] <= MAX_QUEUE_AGE
            and viewer.id in event['_witnesses'] and viewer.location == event['room_id']
            and (event['_played'] is None or (now - event['_played']) * 1000 < event['presentation']['duration_ms']))


def has_pending(world, viewer, since):
    """Cheap audience test before the server builds an authoritative actor map."""
    return next(iter(_candidates(world, viewer, since, time.monotonic())), None) is not None


def projection(world, viewer, since, current_actor_ids, previous_actor_ids=()):
    """Advance the cursor even when locality/visibility removes every cue.

    Only ephemeral delivery time is initialized here; no character, quest,
    inventory, save, or world-clock state changes on a presentation read.
    """
    result = {**cursor(world), 'events': []}
    now = time.monotonic()
    current = set(current_actor_ids)
    previous = set(previous_actor_ids)
    for event in _candidates(world, viewer, since, now):
        style = event['presentation']['style']
        prior_allowed = style in ('projectile', 'burst') or event.get('phase') == 'departure'
        visible = current | previous if prior_allowed else current
        if event['source_id'] not in visible:
            continue
        target_ids = [eid for eid in event['target_ids'] if eid in visible]
        if event['target_ids'] and not target_ids:
            continue
        spawned = event.get('spawned_id')
        if style in ('ground_rise', 'portal_rise'):
            actor = world.entities.get(spawned)
            if not actor or not actor.alive or actor.location != viewer.location or spawned not in current:
                continue
        elif not prior_allowed:
            target_ids = [eid for eid in target_ids if (actor := world.entities.get(eid)) is not None
                          and actor.alive and actor.location == viewer.location]
            if event['target_ids'] and not target_ids:
                continue
            actor = world.entities.get(event['source_id'])
            if not actor or not actor.alive or actor.location != viewer.location:
                continue
        if event['_played'] is None:
            event['_played'] = now
        packet = {k: deepcopy(v) for k, v in event.items() if not k.startswith('_')}
        packet['target_ids'] = target_ids
        packet['elapsed_ms'] = max(0, int((now - event['_played']) * 1000))
        result['events'].append(packet)
    return result
