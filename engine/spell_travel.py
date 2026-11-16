"""Authoritative, permission-checked spell travel to authored visited waypoints.

Teleportation changes only the actual destination. It never simulates walking,
unlocks a passage, transports an escort, or credits intermediate quest visits.
The spell's content, destinations, costs and presentation belong to the world.
"""
from dataclasses import dataclass
import math


MAX_DESTINATIONS = 128


@dataclass(frozen=True)
class TravelPlan:
    world: object
    actor_id: str
    ability_id: str
    origin: str
    destination: str


def validate(data):
    issues = []
    rooms = {row['id'] for row in data.get('room', [])
             if isinstance(row, dict) and isinstance(row.get('id'), str)}
    for ability in data.get('ability', []):
        if not isinstance(ability, dict):
            continue
        rules = ability.get('ability_rules')
        if not isinstance(rules, dict):
            continue
        cfg = rules.get('teleport')
        if cfg is None and ability.get('effect') != 'teleport':
            continue
        label = str(ability.get('id', 'Ability')) + ': teleport '
        if ability.get('effect') != 'teleport':
            issues.append(label + 'settings require the teleport effect.')
        if not isinstance(cfg, dict):
            issues.append(label + 'settings must be an object.')
            continue
        if type(cfg.get('version')) is not int or cfg['version'] != 1:
            issues.append(label + 'version must be 1.')
        if cfg.get('require_visited') is not True:
            issues.append(label + 'require_visited must be true.')
        destinations = cfg.get('destinations')
        if (not isinstance(destinations, list) or not 1 <= len(destinations) <= MAX_DESTINATIONS
                or any(not isinstance(rid, str) or not rid or rid not in rooms for rid in destinations)):
            issues.append(label + 'destinations must name 1–128 existing rooms.')
        elif len(set(destinations)) != len(destinations):
            issues.append(label + 'destinations must not contain duplicates.')
        if set(cfg) - {'version', 'destinations', 'require_visited'}:
            issues.append(label + 'contains unknown settings.')
    return issues


def _config(world, ability):
    rules = ability.get('ability_rules')
    cfg = rules.get('teleport') if isinstance(rules, dict) else None
    if validate({'ability': [ability], 'room': [{'id': rid} for rid in world.rooms]}):
        raise ValueError('This teleport spell needs valid, visited destinations in the Creator.')
    if ability.get('effect') != 'teleport' or not isinstance(cfg, dict):
        raise ValueError('This ability is not a waypoint teleport spell.')
    return cfg


def _available(world, actor, destination):
    """Read current permission state; never use a cached permission decision."""
    from engine import (frontiers, regional_world, sleep_movement,
                        community_quests, geology_impacts, property_interiors)
    if world.entities.get(actor.id) is not actor or not actor.alive or actor.progress.get('permanently_dead'):
        raise ValueError('Only a living character present in this world can teleport.')
    if actor.location not in world.rooms or destination not in world.rooms:
        raise ValueError('That teleport destination is unavailable.')
    if destination == actor.location:
        raise ValueError('You are already at that waypoint.')
    if destination not in actor.explored_rooms:
        raise ValueError('Visit that waypoint in person before teleporting there.')
    if actor.progress.get('escort_party'):
        raise ValueError('Finish or leave your escort journey before teleporting. Guides must travel with you.')
    now = getattr(world, 'living_state', {}).get('minute', 0)
    restrained = actor.progress.get('restrained_until', 0)
    if (type(restrained) not in (int, float) or type(restrained) is float and not math.isfinite(restrained)
            or restrained > now):
        raise ValueError('You cannot teleport while restrained.')
    reason = regional_world.blocked(world, actor, destination)
    if reason:
        raise ValueError(reason)
    if sleep_movement.asleep(world, actor):
        raise ValueError('Wake up before teleporting.')
    if community_quests.frozen(world, actor):
        raise ValueError('You cannot teleport while responsible for this local task.')
    reason = property_interiors.blocked(world, actor, actor.location, None, destination)
    if reason:
        raise ValueError(reason)
    if geology_impacts.room_unusable(world, destination):
        raise ValueError('That waypoint is closed by a physical hazard.')
    route = frontiers.path(world, actor.location, destination, actor)
    if route is None:
        raise ValueError('No permitted route reaches that waypoint. Teleportation cannot bypass locks, gates or closed routes.')
    # Recheck every edge, including actor-wide constraints that the ordinary
    # path accelerator can omit when a room has no authored gate/lock/hazard.
    for source, direction, target in route:
        if source not in world.rooms or world.rooms[source].exits.get(direction) != target:
            raise ValueError('The route changed. Choose your waypoint again.')
        reason = frontiers.blocked(world, source, direction, actor)
        if reason:
            raise ValueError('Teleportation cannot bypass this passage: ' + reason)


def prepare(world, actor, ability, target):
    cfg = _config(world, ability)
    if not isinstance(target, str) or len(target) > 512:
        raise ValueError('Choose an available waypoint by its exact name or ID.')
    query = target.strip().casefold()
    known = [rid for rid in cfg['destinations'] if rid in actor.explored_rooms and rid in world.rooms]
    matches = [rid for rid in known if rid.casefold() == query]
    if not matches:
        matches = [rid for rid in known if world.rooms[rid].name.casefold() == query]
    if len(matches) != 1:
        raise ValueError('Choose one of this spell’s visited waypoints by its exact name or ID.')
    destination = matches[0]
    _available(world, actor, destination)
    return TravelPlan(world, actor.id, str(ability.get('id', '')), actor.location, destination)


def prepare_escape(world, actor, ability):
    """Existing home-return spells obey the same movement restrictions."""
    from engine import frontiers
    if ability.get('effect') != 'escape':
        raise ValueError('This ability is not a home-return spell.')
    destination = frontiers.home(world, actor)
    if destination is None:
        raise ValueError('No safe recovery location is available yet.')
    _available(world, actor, destination)
    return TravelPlan(world, actor.id, str(ability.get('id', '')), actor.location, destination)


def execute(world, actor, ability, plan):
    if (not isinstance(plan, TravelPlan) or plan.world is not world or plan.actor_id != actor.id
            or plan.ability_id != str(ability.get('id', '')) or actor.location != plan.origin):
        raise ValueError('The teleport request is no longer valid. Choose the waypoint again.')
    if ability.get('effect') == 'teleport':
        if plan.destination not in _config(world, ability)['destinations']:
            raise ValueError('That destination is not permitted by this spell.')
    elif ability.get('effect') == 'escape':
        from engine import frontiers
        if plan.destination != frontiers.home(world, actor):
            raise ValueError('The home-return destination has changed.')
    else:
        raise ValueError('This ability cannot teleport a character.')
    # There is no await or simulation step between cast preflight and commit.
    # Revalidation still prevents accidental reuse by another engine caller.
    _available(world, actor, plan.destination)
    from engine import magic_visuals
    departed_witnesses = magic_visuals.witnesses(world, plan.origin)
    if not world.move_entity(actor.id, plan.destination):
        raise ValueError('You cannot leave this place by teleportation.')
    presentation = ability.get('presentation')
    magic_visuals.record(world, presentation, actor, [actor], room_id=plan.origin,
                         witnesses=departed_witnesses, phase='departure')
    magic_visuals.record(world, presentation, actor, [actor], phase='arrival')
    if actor.is_player:
        world.dirty_players = getattr(world, 'dirty_players', set()) | {actor.id}
    return str(ability.get('name', 'Teleportation')) + ': you arrive at ' + world.rooms[actor.location].name + '.'


def targets(world, actor, ability):
    """Only actual visited authored destinations; viewing never performs travel."""
    cfg = _config(world, ability)
    return [{'id': rid, 'name': world.rooms[rid].name} for rid in cfg['destinations']
            if rid in world.rooms and rid in actor.explored_rooms and rid != actor.location]
