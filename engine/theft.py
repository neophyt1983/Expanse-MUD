"""Finite, host-resolved theft from another live actor's unequipped inventory.

The UI may choose a target and maximum quantity without seeing pocket contents.
Blind attempts select a stable eligible item ID on the server. A failed attempt
never returns that selected item or lists the target's inventory.
"""
from collections import Counter
from dataclasses import dataclass

from engine import burglary


@dataclass
class TheftResult:
    attempt: burglary.Attempt
    quantity: int
    message: str
    item_id: str | None = None


def eligible(world, target):
    """Private internal counts; never include this mapping in a player packet."""
    counts = Counter(target.inventory)
    equipped = Counter(target.equipped.values())
    return {iid: count-equipped[iid] for iid, count in counts.items()
            if iid in world.items and world.items[iid].get('anchored_readable') is not True
            and count > equipped[iid]}


def transfer(world, thief, target_id, item_id=None, quantity=1, *, online_players=(), rng=None):
    """Try to take at most quantity units; conserve both actors' inventories.

    Exact actor IDs come from the authenticated caller or an authored NPC plan.
    Player victims must also be in the session layer's explicit online set.
    No selection or failed outcome publishes another character's item names.
    """
    burglary._quantity(quantity)
    if thief is None or world.entities.get(thief.id) is not thief:
        raise ValueError('Enter the world before attempting to steal.')
    if not isinstance(target_id, str):
        raise ValueError('Choose a different living person here.')
    target = world.entities.get(target_id)
    if (target is None or target is thief or not target.alive
            or target.location != thief.location or target.location not in world.rooms):
        raise ValueError('Choose a different living person here.')
    online = set(online_players)
    if target.is_player and target.id not in online:
        raise ValueError('That person is not available here.')
    available = eligible(world, target)
    if item_id is None:
        item_id = min(available) if available else None
    if not isinstance(item_id, str) or item_id not in available:
        raise ValueError('There is no eligible item to take from this person.')
    requested = min(quantity, available[item_id])
    definitions = world.classes if target.is_player else world.npcs
    definition = definitions.get(target.char_class if target.is_player else target.source_def, {})
    row = dict(id=target.id, name=target.name+'’s belongings',
               theft_difficulty=definition.get('theft_difficulty', 25))
    result = burglary.attempt(world, thief, thief.location, row, requested, rng,
                              target_actor=target, online_players=online)
    if result.success:
        remaining = []
        count = result.quantity
        for iid in target.inventory:
            if iid == item_id and count:
                count -= 1
            else:
                remaining.append(iid)
        # Whole validation and both replacements precede the first mutation.
        if count:
            raise ValueError('The target changed before the theft could complete.')
        received = thief.inventory + [item_id] * result.quantity
        target.inventory[:] = remaining
        thief.inventory[:] = received
        world.dirty_players = getattr(world, 'dirty_players', set()) | {
            person.id for person in (thief, target) if person.is_player}
        message = 'You steal '+str(result.quantity)+' × '+str(world.items[item_id].get('name') or item_id)+' from '+target.name+'.'
    else:
        message = 'You fail to steal anything from '+target.name+'.'
    feedback = burglary.complete(world, thief, result)
    if feedback:
        message += ' '+feedback
    return TheftResult(result, result.quantity, message, item_id if result.success else None)
