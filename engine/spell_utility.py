"""World-authored practical magic over real light, defense and condition state.

There is no item creation, currency, quest credit, remote targeting, stacking
multiplier, or permission bypass here. Only the two timed boons are saved; their
animation is delivered separately through the transient visual event stream.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

EFFECTS = ('light', 'ally_ward', 'relief', 'weather_guard')
KEY = 'magic_utility_v1'
CONDITIONS = ('injury', 'disease', 'intoxication')


def _integer(value, lo, hi):
    return type(value) is int and lo <= value <= hi


def _finite(value):
    return type(value) is int or type(value) is float and math.isfinite(value)


def validate(data):
    issues = []
    for ability in data.get('ability', []):
        if not isinstance(ability, dict):
            continue
        rules = ability.get('ability_rules')
        effect = ability.get('effect')
        cfg = rules.get('utility') if isinstance(rules, dict) else None
        if cfg is None and effect not in EFFECTS:
            continue
        label = str(ability.get('id', 'Ability')) + ': utility '
        if effect not in EFFECTS:
            issues.append(label + 'settings require light, ally_ward, relief or weather_guard.')
        if not isinstance(cfg, dict):
            issues.append(label + 'settings must be an object.')
            continue
        if not _integer(cfg.get('version'), 1, 1):
            issues.append(label + 'version must be 1.')
        for key in ('players', 'companions'):
            if type(cfg.get(key)) is not bool:
                issues.append(label + key + ' must be true or false.')
        allowed = {'version', 'players', 'companions'}
        if effect in ('light', 'weather_guard'):
            allowed.add('duration_minutes')
            if not _integer(cfg.get('duration_minutes'), 1, 1440):
                issues.append(label + 'duration_minutes must be an integer from 1 to 1440.')
        if effect == 'weather_guard':
            allowed.add('reduction_percent')
            if not _integer(cfg.get('reduction_percent'), 1, 75):
                issues.append(label + 'reduction_percent must be an integer from 1 to 75.')
        if effect == 'ally_ward':
            allowed.add('hits')
            if not _integer(cfg.get('hits'), 1, 64):
                issues.append(label + 'hits must be an integer from 1 to 64.')
            if not _integer(ability.get('power'), 1, 100):
                issues.append(label + 'ally_ward power must be an integer from 1 to 100.')
        if effect == 'relief':
            allowed.add('conditions')
            conditions = cfg.get('conditions')
            if (not isinstance(conditions, dict) or not conditions
                    or any(k not in CONDITIONS or not _integer(v, 1, 100) for k, v in conditions.items())):
                issues.append(label + 'conditions must name injury, disease or intoxication with amounts from 1 to 100.')
        if set(cfg) - allowed:
            issues.append(label + 'contains unknown settings for this effect.')
    return issues


def _minute(world):
    from engine.worldtime import initial_minute
    return getattr(world, 'living_state', {}).get('minute', initial_minute(world.metadata))


def _config(ability):
    if ability.get('effect') not in EFFECTS or validate({'ability':[ability]}):
        raise ValueError('This utility spell needs valid settings in the Creator.')
    return ability['ability_rules']['utility']


def _active(world, actor, effect):
    """Read-only and fail-closed for expired or malformed saved boons."""
    if not actor.alive:
        return None
    state = actor.progress.get(KEY)
    value = state.get(effect) if isinstance(state, dict) else None
    if not isinstance(value, dict) or not _integer(value.get('version'), 1, 1):
        return None
    created, expires = value.get('created_minute'), value.get('expires_minute')
    if (type(created) is not int or type(expires) is not int or not 1 <= expires-created <= 1440
            or not created <= _minute(world) < expires):
        return None
    if effect == 'weather_guard' and not _integer(value.get('reduction_percent'), 1, 75):
        return None
    if effect not in ('light', 'weather_guard'):
        return None
    return value


def light(world, viewer):
    """A real living light-bearing actor illuminates its current room only.

Sight geometry still uses the normal open edges, locks, gates and sight cap.
No remote occupant, undisclosed room or secret passage is exposed by this read.
"""
    if viewer.location not in world.rooms:
        return False
    return any(actor.location == viewer.location and world.entities.get(actor.id) is actor
               and _active(world, actor, 'light') is not None
               for actor in world.entities_in_room(viewer.location))


def mitigate(world, actor, amount, kind):
    # Costs, combat, traffic collisions, harvesting and scripted conditions are
    # not weather/environment damage. Never turn a positive hazard into zero.
    if kind != 'environment' or not _finite(amount) or amount <= 0:
        return amount
    boon = _active(world, actor, 'weather_guard')
    if boon is None:
        return amount
    percent = 100-boon['reduction_percent']
    reduced = (amount*percent+99)//100 if type(amount) is int else math.ceil(amount*(percent/100))
    return max(1, reduced)


def _targets(world, actor, cfg):
    if actor.location not in world.rooms:
        return []
    return list({target.id: target for target in world.entities_in_room(actor.location)
                 if target.alive and target.location == actor.location
                 and world.entities.get(target.id) is target
                 and (target.id == actor.id or cfg['players'] and target.is_player
                      or cfg['companions'] and target.progress.get('companion_owner') == actor.id)}.values())


@dataclass(frozen=True)
class UtilityPlan:
    world: object
    actor_id: str
    room_id: str
    ability_id: str
    effect: str
    target_id: str
    config: dict


def prepare(world, actor, ability, target):
    from engine import living, sleep_movement
    cfg = _config(ability)
    if not living.enabled(world):
        raise ValueError('This spell requires a world with a running game clock.')
    if (world.entities.get(actor.id) is not actor or not actor.alive
            or actor.progress.get('permanently_dead') or actor.location not in world.rooms):
        raise ValueError('Only a living character here can cast this spell.')
    if sleep_movement.asleep(world, actor):
        raise ValueError('Wake up before casting this spell.')
    if not isinstance(target, str) or len(target) > 512:
        raise ValueError('Choose a living recipient here by exact name or ID.')
    query = target.strip().casefold()
    candidates = _targets(world, actor, cfg)
    if not query:
        recipient = actor
    else:
        matches = [e for e in candidates if e.id.casefold() == query]
        if not matches:
            matches = [e for e in candidates if e.name.casefold() == query]
        if len(matches) != 1:
            raise ValueError('Choose yourself or an allowed living player or owned companion here.')
        recipient = matches[0]
    effect, now = ability['effect'], _minute(world)
    if effect == 'relief':
        values = [recipient.progress.get(k, 0) for k in cfg['conditions']]
        if any(not _finite(v) or not 0 <= v <= 100 for v in values):
            raise ValueError('That recipient has invalid condition data.')
        if not any(v > 0 for v in values):
            raise ValueError('That recipient has none of the conditions this spell treats.')
    elif effect == 'ally_ward':
        pr = recipient.progress
        if not all(_finite(pr.get(k, 0)) and pr.get(k, 0) >= 0 for k in ('ward', 'ward_turns')):
            raise ValueError('That recipient has invalid ward data.')
        if pr.get('ward', 0) >= ability['power'] and pr.get('ward_turns', 0) >= cfg['hits']:
            raise ValueError('That recipient already has an equal or stronger ward with enough remaining hits.')
    else:
        active = _active(world, recipient, effect)
        strength = 1 if effect == 'light' else cfg['reduction_percent']
        existing = 1 if effect == 'light' else active.get('reduction_percent', 0) if active else 0
        if active and active['expires_minute'] >= now + cfg['duration_minutes'] and existing >= strength:
            raise ValueError('That recipient already has an equal or stronger effect for at least this duration.')
    return UtilityPlan(world, actor.id, actor.location, ability['id'], effect, recipient.id, deepcopy(cfg))


def execute(world, actor, ability, plan):
    if not isinstance(plan, UtilityPlan) or prepare(world, actor, ability, plan.target_id) != plan:
        raise ValueError('The spell target changed. Choose the recipient again.')
    recipient = world.entities[plan.target_id]
    cfg, effect, now = plan.config, plan.effect, _minute(world)
    from engine import living, magic_visuals
    if effect == 'relief':
        changed = []
        for key, amount in cfg['conditions'].items():
            before = recipient.progress.get(key, 0)
            if before > 0:
                recipient.progress[key] = max(0, before-amount)
                changed.append(str(before-recipient.progress[key]) + ' ' + key)
        text = 'relieved ' + ', '.join(changed) + ' for ' + recipient.name + '.'
    elif effect == 'ally_ward':
        progress = living.progress(recipient)
        # One ward replaces the previous ward. Different casters cannot stack
        # defense or add unlimited protected hits by alternating spells.
        progress['ward'] = ability['power']
        progress['ward_turns'] = cfg['hits']
        text = recipient.name + ' gains ' + str(ability['power']) + ' defense for ' + str(cfg['hits']) + ' incoming hits.'
    else:
        state = recipient.progress.get(KEY)
        state = {k: v for k, v in state.items() if k in ('light', 'weather_guard')} if isinstance(state, dict) else {}
        value = dict(version=1, ability_id=ability['id'], created_minute=now, expires_minute=now+cfg['duration_minutes'])
        if effect == 'weather_guard':
            value['reduction_percent'] = cfg['reduction_percent']
            text = recipient.name + ' has ' + str(cfg['reduction_percent']) + '% protection from environmental damage for ' + str(cfg['duration_minutes']) + ' game minutes.'
        else:
            text = recipient.name + ' lights the current room for ' + str(cfg['duration_minutes']) + ' game minutes.'
        state[effect] = value
        recipient.progress[KEY] = state
    if recipient.is_player:
        world.dirty_players = getattr(world, 'dirty_players', set()) | {recipient.id}
    magic_visuals.record(world, ability.get('presentation'), actor, [recipient])
    return ability['name'] + ': ' + text


def targets(world, actor, ability):
    return _targets(world, actor, _config(ability))


def describe(world, actor):
    parts = []
    now = _minute(world)
    light_boon = _active(world, actor, 'light')
    guard = _active(world, actor, 'weather_guard')
    if light_boon:
        parts.append('Magical light: '+str(light_boon['expires_minute']-now)+' game minutes remaining.')
    if guard:
        parts.append('Environmental protection: '+str(guard['reduction_percent'])+'% for '+str(guard['expires_minute']-now)+' more game minutes.')
    pr = actor.progress
    if pr.get('ward', 0) > 0 and pr.get('ward_turns', 0) > 0:
        parts.append('Ward: '+str(pr['ward'])+' defense for '+str(pr['ward_turns'])+' incoming hits.')
    return ' '.join(parts)
