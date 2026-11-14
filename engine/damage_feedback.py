"""Personal, ephemeral injury reports shared by all damage sources.

These messages describe actual health lost. They never publish a save and are
not part of the persistent character schema. A short replay survives a socket
reconnect to the same running world without duplicating the event identity.
"""
import time
import uuid


def record(world, actor, amount, *, source=None, cause=None, kind='injury'):
    if not actor.is_player or amount <= 0:
        return None
    if not hasattr(world, '_damage_session'):
        world._damage_session = uuid.uuid4().hex
        world._damage_sequence = 0
    world._damage_sequence += 1
    cause = str(cause or 'an unidentified injury')[:300]
    name = str(getattr(source, 'name', '') or cause)
    origin = name + (' (' + cause + ')' if source is not None and cause != name else '')
    room = world.rooms.get(actor.location)
    event = {
        'type': 'damage',
        'event_id': world._damage_session + ':' + str(world._damage_sequence),
        'player_id': actor.id,
        'amount': amount,
        'hp': actor.hp,
        'max_hp': actor.max_hp,
        'source': {'id': getattr(source, 'id', None), 'name': name, 'kind': kind},
        'cause': cause,
        'location': {'id': actor.location, 'name': room.name if room else actor.location},
        'source_location': getattr(source, 'location', actor.location),
        'occurred_at': time.time(),
        'game_minute': getattr(world, 'living_state', {}).get('minute'),
        'text': f'You take {amount} damage from {origin}. Health: {actor.hp}/{actor.max_hp}.'
                + (' You have died.' if not actor.alive else ''),
    }
    actor._recent_damage = (getattr(actor, '_recent_damage', []) + [event])[-10:]
    world.damage_notifications = (getattr(world, 'damage_notifications', []) + [event])[-500:]
    world.dirty_players = getattr(world, 'dirty_players', set()) | {actor.id}
    return event


def recent(actor):
    return list(getattr(actor, '_recent_damage', ()))
