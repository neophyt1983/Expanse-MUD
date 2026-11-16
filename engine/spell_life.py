"""Authored, finite life magic; presentation and gameplay remain separate.

Only real local corpses can be raised. Temporary bodies never manufacture
inventory or combat rewards, and their lifetime follows saved game minutes.
"""
from copy import deepcopy
from dataclasses import dataclass
import time
from uuid import uuid4

KEY = 'magic_summon_v1'
REVIVAL = 'magic_resurrection_v1'
EFFECTS = ('raise_dead', 'summon', 'resurrection')


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _non_sentient_definition(data, definition):
    profile = definition.get('social_profile', {})
    profile = profile if isinstance(profile, dict) else {}
    species = next((s for s in data.get('species', []) if s.get('id') == profile.get('species', definition.get('species'))), {})
    declared = species.get('sentient', profile.get('sentient', definition.get('sentient')))
    return declared is False


def validate(data):
    issues = []
    npcs = {r['id']: r for r in data.get('npc', [])}
    for ability in data.get('ability', []):
        effect = ability.get('effect')
        rules = ability.get('ability_rules', {})
        if not isinstance(rules, dict):
            continue
        label = str(ability.get('id', 'ability')) + ': '
        if 'ally_players' in rules and type(rules['ally_players']) is not bool:
            issues.append(label + 'ally_players must be true or false')
        if rules.get('ally_players') and effect != 'ally_heal':
            issues.append(label + 'ally_players is supported only for ally_heal')
        if 'summon' in rules or effect in ('summon', 'raise_dead'):
            cfg = rules.get('summon')
            if effect not in ('summon', 'raise_dead'):
                issues.append(label + 'summon settings require a summon or raise_dead effect')
            if not isinstance(cfg, dict):
                issues.append(label + 'summon requires a settings object')
                continue
            if type(cfg.get('version')) is not int or cfg['version'] != 1:
                issues.append(label + 'summon version must be 1')
            for key, low, high in [('duration_minutes', 1, 1440), ('max_active', 1, 8), ('max_level', 1, 100)]:
                if not _integer(cfg.get(key), low, high):
                    issues.append(label + f'summon {key} must be an integer from {low} to {high}')
            if set(cfg) - {'version', 'duration_minutes', 'max_active', 'max_level', 'npc'}:
                issues.append(label + 'summon contains unknown settings')
            if effect == 'raise_dead' and 'npc' in cfg:
                issues.append(label + 'raise_dead uses the actual corpse and must not name an NPC template')
            if effect == 'summon':
                definition = npcs.get(cfg.get('npc')) if isinstance(cfg.get('npc'), str) else None
                if not definition or not _non_sentient_definition(data, definition):
                    issues.append(label + 'summon npc must reference an explicitly non-sentient creature')
                elif not _integer(definition.get('combat_level', 1), 1, 100):
                    issues.append(label + 'summon npc must have a valid combat level')
                elif _integer(cfg.get('max_level'), 1, 100) and definition.get('combat_level', 1) > cfg['max_level']:
                    issues.append(label + 'summon npc exceeds the authored maximum level')
        if 'resurrection' in rules or effect == 'resurrection':
            cfg = rules.get('resurrection')
            if effect != 'resurrection':
                issues.append(label + 'resurrection settings require the resurrection effect')
            if not isinstance(cfg, dict):
                issues.append(label + 'resurrection requires a settings object')
                continue
            if type(cfg.get('version')) is not int or cfg['version'] != 1:
                issues.append(label + 'resurrection version must be 1')
            for key in ('players', 'companions'):
                if type(cfg.get(key)) is not bool:
                    issues.append(label + f'resurrection {key} must be true or false')
            if not (cfg.get('players') is True or cfg.get('companions') is True):
                issues.append(label + 'resurrection must allow at least one kind of recipient')
            for key, low, high in [('health_percent', 1, 100), ('recovery_minutes', 1, 1440), ('injury', 0, 100)]:
                if not _integer(cfg.get(key), low, high):
                    issues.append(label + f'resururrection {key} must be an integer from {low} to {high}')
            if set(cfg) - {'version', 'players', 'companions', 'health_percent', 'recovery_minutes', 'injury'}:
                issues.append(label + 'resurrection contains unknown settings')
        if effect in EFFECTS and not rules:
            issues.append(label + 'life magic requires explicit ability_rules')
    return issues


def magical(actor):
    return bool(actor.progress.get(KEY))


def no_rewards(actor):
    return magical(actor) or bool(actor.progress.get('magic_reward_ineligible'))


def _minute(world):
    from engine.worldtime import initial_minute
    return getattr(world, 'living_state', {}).get('minute', initial_minute(world.metadata))


def control_restriction(world, actor):
    """Read restraint/custody without initializing law or save state."""
    import math
    until = actor.progress.get('restrained_until', 0)
    try:
        valid = type(until) in (int, float) and math.isfinite(until)
    except (OverflowError,ValueError):
        valid = False
    if not valid or until > _minute(world):
        return 'You cannot direct magic or companions while restrained.'
    case = getattr(world, 'living_state', {}).get('city_justice_v1', {}).get('cases', {}).get(actor.id, {})
    if case.get('status') in ('awaiting_hearing', 'sentenced'):
        return 'You cannot summon or command fighting companions while in custody.'
    return ''


def _reserve(world):
    return getattr(world, 'living_state', {}).get('companion_reserve', {})


def _body_state(progress):
    value = progress.get(KEY)
    if value is None:
        return None
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or not isinstance(value.get('owner_id'), str) or not value['owner_id']
            or not isinstance(value.get('ability_id'), str) or not value['ability_id']
            or value.get('kind') not in ('raised', 'summoned')
            or type(value.get('created_minute')) is not int or type(value.get('expires_minute')) is not int
            or not 1 <= value['expires_minute'] - value['created_minute'] <= 1440
            or progress.get('companion_owner') != value['owner_id']):
        raise ValueError('Invalid saved magical companion lifetime or owner.')
    return value


def track(world, actor):
    """Bind one created/restored identity; no all-population scan on a tick."""
    value = _body_state(actor.progress)
    if value:
        index = getattr(world, '_magic_summon_ids', None)
        if index is None:
            index = world._magic_summon_ids = {}
        index.setdefault(value['owner_id'], set()).add(actor.id)
    if actor.is_player:
        now = _minute(world)
        rows = actor.progress.get('companions')
        if isinstance(rows, list):
            actor.progress['companions'] = [r for r in rows if not r.get(KEY) or
                (r[KEY].get('expires_minute', 0) > now and
                 (r.get('id') in world.entities or r.get('id') in _reserve(world)))]


def restore(world):
    """One restore-boundary rebuild includes living bodies and stored reserves."""
    world._magic_summon_ids = {}
    for actor in world.entities.values():
        if not actor.is_player and magical(actor):
            track(world, actor)
    for ident, saved in _reserve(world).items():
        value = _body_state(saved.get('progress', {}))
        if value:
            world._magic_summon_ids.setdefault(value['owner_id'], set()).add(ident)
    advance(world)


def _owned_bodies(world, owner_id):
    for ident in tuple(getattr(world, '_magic_summon_ids', {}).get(owner_id, ())):
        actor = world.entities.get(ident)
        saved = _reserve(world).get(ident)
        progress = actor.progress if actor else saved.get('progress', {}) if saved else {}
        value = progress.get(KEY)
        if value:
            yield ident, actor, saved, value


def retire(world, ident, *, notify=False):
    actor = world.entities.get(ident)
    saved = _reserve(world).get(ident)
    progress = actor.progress if actor else saved.get('progress', {}) if saved else {}
    value = progress.get(KEY)
    if not value:
        return False
    owner_id = value['owner_id']
    owner = world.entities.get(owner_id)
    if owner:
        owner.progress['companions'] = [r for r in owner.progress.get('companions', []) if r.get('id') != ident]
        if owner.is_player:
            world.dirty_players = getattr(world, 'dirty_players', set()) | {owner.id}
    if actor:
        room = world.rooms.get(actor.location)
        if room and ident in room.entities:
            room.entities.remove(ident)
        world.entities.pop(ident, None)
        if notify:
            world.runtime_notifications = (getattr(world, 'runtime_notifications', []) + [
                (actor.location, actor.name + "'s temporary magical form fades.")])[-500:]
    _reserve(world).pop(ident, None)
    index = getattr(world, '_magic_summon_ids', {})
    ids = index.get(owner_id, set())
    ids.discard(ident)
    if not ids:
        index.pop(owner_id, None)
    return True


def advance(world):
    now = _minute(world)
    for owner_id in tuple(getattr(world, '_magic_summon_ids', {})):
        for ident, actor, saved, value in tuple(_owned_bodies(world, owner_id)):
            hp = actor.hp if actor else saved.get('hp', 0) if saved else 0
            if hp <= 0 or value['expires_minute'] <= now:
                retire(world, ident, notify=hp > 0)


def _config(world, ability):
    rules = ability.get('ability_rules', {})
    summon = rules.get('summon', {}) if isinstance(rules, dict) else {}
    ident = summon.get('npc') if isinstance(summon, dict) else None
    definition = world.npcs.get(ident, {}) if isinstance(ident, str) else {}
    profile = definition.get('social_profile', {})
    species = getattr(world, 'species', {}).get(profile.get('species', definition.get('species')), {})
    data = dict(ability=[ability], npc=[definition] if definition else [], species=[species] if species else [])
    if validate(data):
        raise ValueError('This life spell needs valid settings in the Creator.')
    rules = ability.get('ability_rules')
    if ability.get('effect') not in EFFECTS or not isinstance(rules, dict):
        raise ValueError('This is not a configured life spell.')
    return rules['resurrection' if ability['effect'] == 'resurrection' else 'summon']


def _corpse(world, actor, text):
    if not isinstance(text, str) or not text.strip() or len(text) > 512:
        raise ValueError('Choose a real fallen character or creature here by exact name or ID.')
    query = text.strip().casefold()
    room = world.rooms[actor.location]
    rows = [world.entities[eid] for eid in room.entities if eid in world.entities
            and world.entities[eid].location == actor.location and not world.entities[eid].alive]
    matches = [e for e in rows if e.id.casefold() == query]
    if not matches:
        matches = [e for e in rows if e.name.casefold() == query]
    if len(matches) != 1:
        raise ValueError('Choose one actual corpse here by exact name or ID.')
    corpse = matches[0]
    if corpse.corpse_expires_at is not None and corpse.corpse_expires_at <= time.monotonic():
        raise ValueError('That body is no longer available.')
    return corpse


@dataclass(frozen=True)
class Plan:
    world: object
    actor_id: str
    room_id: str
    ability_id: str
    effect: str
    target_id: str | None
    config: dict


def prepare(world, actor, ability, target):
    from engine import geology_impacts, relationships, loot_tables, mortality, sleep_movement, living
    cfg = _config(world, ability)
    effect = ability['effect']
    if not living.enabled(world):
        raise ValueError('This spell requires a world with a running game clock.')
    if world.entities.get(actor.id) is not actor or not actor.alive or actor.progress.get('permanently_dead') or actor.location not in world.rooms:
        raise ValueError('Only a living character present here can cast this spell.')
    if sleep_movement.asleep(world, actor):
        raise ValueError('Wake up before using life magic.')
    if geology_impacts.room_unusable(world, actor.location):
        raise ValueError('This place cannot safely hold the spell.')
    now = _minute(world)
    corpse = None
    if effect in ('raise_dead', 'resurrection'):
        corpse = _corpse(world, actor, target)
        if magical(corpse) or corpse.progress.get('magic_body_used'):
            raise ValueError('A temporary magical body cannot be raised or resurrected again.')
    elif not isinstance(target, str) or target.strip():
        raise ValueError('This spell summons its authored creature; it does not take a creature or player target.')
    if effect in ('raise_dead', 'summon'):
        reason = control_restriction(world, actor)
        if reason:
            raise ValueError(reason)
        active = sum(1 for _, e, saved, value in _owned_bodies(world, actor.id)
                     if value['expires_minute'] > now and (e.hp if e else saved.get('hp', 0)) > 0)
        if active >= cfg['max_active']:
            raise ValueError('Your magical companion limit is already reached, including dismissed or stored companions.')
        if corpse:
            definition = world.npcs.get(corpse.source_def)
            profile = (definition or {}).get('social_profile', {})
            species = getattr(world, 'species', {}).get(profile.get('species', (definition or {}).get('species')), {})
            data = dict(species=[species] if species else [])
            if corpse.is_player or not definition or relationships.sentient(world, corpse) or not _non_sentient_definition(data, definition):
                raise ValueError('Only a non-sentient creature or monster corpse can be raised.')
            if corpse.progress.get('companion_owner') or corpse.progress.get('zoo_exhibit') or definition.get('zoo_exhibit'):
                raise ValueError('An owned companion or protected exhibit cannot be taken as a raised body.')
            if no_rewards(corpse):
                raise ValueError('This previously restored body cannot be raised into another companion.')
            if loot_tables.effective_level(definition, corpse) > cfg['max_level']:
                raise ValueError('That creature is too powerful for this raising spell.')
        else:
            definition = world.npcs[cfg['npc']]
            if definition.get('combat_level', 1) > cfg['max_level']:
                raise ValueError('The summoned creature exceeds this spell\'s level limit.')
    else:
        if corpse.is_player:
            if corpse.id == actor.id or not cfg['players']:
                raise ValueError('This spell does not restore that player.')
            if mortality.player_death_mode(world) != 'revival' or corpse.progress.get('permanently_dead'):
                raise ValueError('This world does not permit that player to return from death.')
        elif not cfg['companions'] or corpse.progress.get('companion_owner') != actor.id:
            raise ValueError('Choose another fallen player or one of your own fallen companions here.')
        recovery = corpse.progress.get(REVIVAL, {}).get('recovery_until', 0)
        if type(recovery) is not int or recovery > now:
            raise ValueError('That character has not recovered from the previous resurrection yet.')
    return Plan(world, actor.id, actor.location, ability['id'], effect, corpse.id if corpse else None, deepcopy(cfg))


def _roster(world, owner, body):
    row = dict(id=body.id, source_def=body.source_def, name=body.name, kind='companion',
               attack=body.attack, description=body.description or world.npcs.get(body.source_def, {}).get('description', ''))
    if magical(body):
        row[KEY] = deepcopy(body.progress[KEY])
    rows = owner.progress.setdefault('companions', [])
    if not any(r.get('id') == body.id for r in rows):
        rows.append(row)


def execute(world, actor, ability, plan):
    """Synchronous checked commit; caller commits affordable costs afterward."""
    if not isinstance(plan, Plan) or prepare(world, actor, ability, plan.target_id or '') != plan:
        raise ValueError('The spell target changed. Choose the actual target again.')
    from engine import living, magic_visuals
    now = _minute(world)
    cfg = plan.config
    if plan.effect == 'resurrection':
        target = world.entities[plan.target_id]
        target.hp = max(1, target.max_hp * cfg['health_percent'] // 100)
        target.corpse_expires_at = None
        for key in ('death_recorded', '_combat_death_resolved', '_environmental_death_resolved'):
            target.progress.pop(key, None)
        target.progress[REVIVAL] = dict(version=1, recovery_until=now + cfg['recovery_minutes'])
        progress = living.progress(target)
        progress['injury'] = min(100, progress['injury'] + cfg['injury'])
        from engine import geology_impacts, mortality
        geology_impacts.retire_wounds(world, target, target.hp)
        deaths = mortality.state(world)
        previous_death = deaths['deaths'].pop(target.id, None)
        if previous_death is not None:
            deaths['revivals'] = (deaths.get('revivals', []) + [dict(
                death=deepcopy(previous_death), minute=now, restored_by=actor.id,
                ability=ability['id'])])[-1000:]
        for bond in getattr(world, 'living_state', {}).get('relationships', {}).get('bonds', {}).values():
            if target.id in bond.get('deceased', []):
                bond['deceased'].remove(target.id)
        if not target.is_player:
            target.progress['magic_reward_ineligible'] = True
            target.progress['combat_rewards_settled_v1'] = True
            target.progress['combat_drops_distributed'] = True
            target.progress.update(companion_order='follow', companion_mode='defend')
            _reserve(world).pop(target.id, None)
            _roster(world, actor, target)
        else:
            world.dirty_players = getattr(world, 'dirty_players', set()) | {target.id}
        magic_visuals.record(world, ability.get('presentation'), actor, [target])
        return ability['name'] + ': ' + target.name + ' returns to life with ' + str(target.hp) + ' health.'
    from engine.core import Entity
    corpse = world.entities.get(plan.target_id)
    definition = world.npcs[corpse.source_def if corpse else cfg['npc']]
    body = Entity('magic_' + uuid4().hex, corpse.name if corpse else definition['name'],
                  corpse.max_hp if corpse else definition['hp'], corpse.max_hp if corpse else definition['hp'],
                  corpse.attack if corpse else definition['attack'], corpse.defense if corpse else definition['defense'],
                  source_def=definition['id'], group_id=actor.group_id,
                  race=corpse.race if corpse else definition.get('race'),
                  sex=corpse.sex if corpse else definition.get('sex'),
                  description=corpse.description if corpse else definition.get('description'))
    body.progress.update(companion_owner=actor.id, companion_order='follow', companion_mode='defend',
                         magic_reward_ineligible=True)
    body.progress['social_profile'] = dict(sentient=False, fertile=False,
        autonomous=False, romance_enabled=False, family_enabled=False, age_in_world=False)
    body.progress[KEY] = dict(version=1, owner_id=actor.id, ability_id=ability['id'],
                             kind='raised' if corpse else 'summoned', created_minute=now,
                             expires_minute=now + cfg['duration_minutes'])
    if corpse:
        from engine import visual_mapping
        portrait = visual_mapping.actor_portrait(world, corpse, actor.id)
        body.progress['magic_appearance_v1'] = {k: deepcopy(portrait[k]) for k in
            ('appearance', 'subject', 'paperdoll', 'held_gear') if k in portrait}
        body.progress['social_profile']['undead'] = True
    # The new body carries no copied coins, inventory, equipment, drops or spells.
    world.add_entity(body, actor.location)
    if corpse:
        corpse.progress['magic_body_used'] = True
        room = world.rooms[corpse.location]
        if corpse.id in room.entities:
            room.entities.remove(corpse.id)
        world.entities.pop(corpse.id, None)
    _roster(world, actor, body)
    advance(world)
    magic_visuals.record(world, ability.get('presentation'), actor, [body], spawned=body)
    return ability['name'] + ': ' + body.name + ' will defend you for ' + str(cfg['duration_minutes']) + ' game minutes.'


def targets(world, actor, ability):
    if ability.get('effect') not in ('raise_dead', 'resurrection'):
        return []
    rows = []
    for eid in world.rooms.get(actor.location).entities:
        target = world.entities.get(eid)
        if target is None or target.alive:
            continue
        try:
            prepare(world, actor, ability, target.id)
        except ValueError:
            continue
        rows.append(target)
    return rows
