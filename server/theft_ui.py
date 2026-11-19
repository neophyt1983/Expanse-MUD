"""Resolve a scoped graphical theft request without rolling or reading pockets."""
import shlex

from engine import burglary, relationships, sleep_movement


def resolve(world, actor, packet, *, online_players=()):
    """Return one ordinary steal command for the authenticated player.

    Replay protection belongs to GameServer's per-session request tracking.
    This boundary checks the live character and target, without trusting a
    supplied command string, disclosing inventory, or changing world state.
    """
    if not isinstance(packet, dict):
        raise ValueError('Choose a current local theft action.')
    if (actor is None or not actor.is_player or world.entities.get(actor.id) is not actor
            or not actor.alive or sleep_movement.asleep(world, actor)):
        raise ValueError('Choose a living, awake player character first.')
    if packet.get('actor_id') != actor.id:
        raise ValueError('The selected character changed. Refresh local actions.')
    if packet.get('room') != actor.location or actor.location not in world.rooms:
        raise ValueError('You have moved. Refresh the local actions.')
    if (packet.get('command') != 'steal action' or packet.get('theft_ui') is not True
            or packet.get('action') != 'steal'):
        raise ValueError('Unknown theft action.')
    request_id = packet.get('request_id')
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
        raise ValueError('Refresh local actions to create a valid theft request.')
    quantity = packet.get('quantity')
    burglary._quantity(quantity)
    if 'item_id' in packet or 'item' in packet:
        raise ValueError('A local theft action selects a person and a maximum quantity, not pocket contents.')
    target_id = packet.get('target_id')
    target = world.entities.get(target_id) if isinstance(target_id, str) else None
    if (target is None or target is actor or not target.alive or target.location != actor.location
            or not relationships.sentient(world, target)):
        raise ValueError('Choose a different living person here.')
    if target.is_player:
        if target.id not in set(online_players):
            raise ValueError('That person is no longer available here. Refresh local actions.')
    elif not target.source_def or target.source_def not in world.npcs:
        raise ValueError('Choose a real person here.')
    if not any(person is target for person in world.entities_in_room(actor.location)):
        raise ValueError('That person is no longer here. Refresh local actions.')
    return shlex.join(['steal', target.id, str(quantity)])
