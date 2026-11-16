"""Small authored spell loadouts used only in already-authorized NPC combat turns.

No population scan or passive healing loop is added. Mana recovery is calculated
from elapsed out-of-combat game minutes when an actual combat turn begins.
"""
from engine import living

KEY = 'npc_spellcasting_v1'
EFFECTS = ('damage', 'heal', 'ally_heal', 'ward', 'ally_ward')
FIELDS = {'version', 'class', 'level', 'abilities', 'max_mana', 'starting_mana',
          'regen_per_minute', 'regen_delay_minutes', 'cast_interval_minutes', 'heal_below_percent'}


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _issues(npc, abilities, classes):
    cfg = npc.get('spellcasting')
    if cfg in (None, {}):
        return []
    label = str(npc.get('id', 'NPC')) + ': spellcasting '
    if not isinstance(cfg, dict):
        return [label + 'must be an object']
    issues = []
    if not _integer(cfg.get('version'), 1, 1):
        issues.append(label + 'version must be 1')
    if not isinstance(cfg.get('class'), str) or cfg['class'] not in classes:
        issues.append(label + 'class must reference an existing casting discipline')
    for key, low, high in [('level', 1, 100), ('max_mana', 1, 500), ('starting_mana', 0, 500),
                           ('regen_per_minute', 0, 10), ('regen_delay_minutes', 1, 1440),
                           ('cast_interval_minutes', 1, 60), ('heal_below_percent', 1, 99)]:
        if not _integer(cfg.get(key), low, high):
            issues.append(label + f'{key} must be an integer from {low} to {high}')
    if _integer(cfg.get('starting_mana'), 0, 500) and _integer(cfg.get('max_mana'), 1, 500) and cfg['starting_mana'] > cfg['max_mana']:
        issues.append(label + 'starting_mana cannot exceed max_mana')
    ids = cfg.get('abilities')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 8 or any(not isinstance(i, str) or i not in abilities for i in ids):
        issues.append(label + 'abilities must name 1–8 existing configured spells')
    else:
        if len(set(ids)) != len(ids):
            issues.append(label + 'abilities must not contain duplicates')
        for ident in ids:
            ability = abilities[ident]
            rules = ability.get('ability_rules', {})
            if not isinstance(rules, dict) or rules.get('family') != 'mage' or ability.get('effect') not in EFFECTS:
                issues.append(label + ident + ' requires a configured damage, heal, ally_heal, ward or ally_ward spell')
                continue
            if not isinstance(rules.get('classes'), list) or cfg.get('class') not in rules['classes']:
                issues.append(label + ident + ' is not available to this casting discipline')
            races = rules.get('races', [])
            if not isinstance(races, list) or races and npc.get('race') not in races:
                issues.append(label + ident + ' does not permit the NPC\'s explicit race')
            minimum = rules.get('minimum_level', 1)
            if not _integer(minimum, 1, 100) or not _integer(cfg.get('level'), 1, 100) or minimum > cfg['level']:
                issues.append(label + ident + ' exceeds the authored initial casting level')
    if set(cfg) - FIELDS:
        issues.append(label + 'contains unknown settings')
    return issues


def validate(data):
    abilities = {a['id']: a for a in data.get('ability', [])}
    classes = {c['id'] for c in data.get('class', [])}
    return [issue for npc in data.get('npc', []) for issue in _issues(npc, abilities, classes)]


def config(world, actor):
    if actor.is_player or actor.progress.get('magic_summon_v1'):
        return None
    definition = world.npcs.get(actor.source_def, {})
    cfg = definition.get('spellcasting')
    if not cfg or _issues(definition, world.abilities, world.classes):
        return None
    return cfg


def discipline(world, actor):
    cfg = config(world, actor)
    if not cfg:
        return None
    earned = actor.progress.get('advancement_v1', {}).get('level', 1)
    earned = earned if _integer(earned, 1, 100) else 1
    race = actor.race or world.npcs.get(actor.source_def, {}).get('race')
    return dict(char_class=cfg['class'], level=max(cfg['level'], earned), race=race)


def _minute(world):
    from engine.worldtime import initial_minute
    return getattr(world, 'living_state', {}).get('minute', initial_minute(world.metadata))


def bind(world, actor):
    """Initialize an explicitly authored training grant once, never on a read."""
    cfg = config(world, actor)
    if not cfg:
        return
    state = actor.progress.get(KEY)
    if state is None:
        state = dict(version=1, updated_minute=_minute(world), last_combat_minute=None,
                     last_cast_minute=None, rotation=0, enemy_id=None, combat_room=None)
        actor.progress[KEY] = state
        actor.progress['mana'] = cfg['starting_mana']
    elif (not isinstance(state, dict) or not _integer(state.get('version'), 1, 1)
          or type(state.get('updated_minute')) is not int
          or any(state.get(k) is not None and type(state[k]) is not int for k in ('last_combat_minute', 'last_cast_minute'))
          or not _integer(state.get('rotation'), 0, 1000000)
          or not _integer(actor.progress.get('mana'), 0, 1000000)):
        raise ValueError('Invalid saved NPC spellcasting resources or clock.')
    for key in ('enemy_id','combat_room'):
        if state.get(key) is not None and not isinstance(state[key],str):
            raise ValueError('Invalid saved NPC combat context.')
    actor.progress['max_mana'] = cfg['max_mana']
    actor.progress['mana'] = min(actor.progress['mana'], cfg['max_mana'])
    for ident in cfg['abilities']:
        if ident not in actor.abilities:
            actor.abilities.append(ident)


def friendly_allies(world, actor, enemy, candidates=()):
    """Only actual fellow NPC responders named by the existing combat system."""
    rows = [actor]
    if not actor.group_id:
        return rows
    seen = {actor.id}
    for other in candidates:
        if (other is None or world.entities.get(getattr(other, 'id', None)) is not other
                or other.id in seen or other.id == enemy.id or other.is_player or not other.alive
                or other.location != actor.location or other.group_id != actor.group_id
                or other.progress.get('companion_owner')):
            continue
        rows.append(other)
        seen.add(other.id)
        if len(rows) >= 64:
            break
    return rows


def _turn(world, actor, cfg, enemy=None):
    bind(world, actor)
    state = actor.progress[KEY]
    now = _minute(world)
    start = state['updated_minute']
    if state['last_combat_minute'] is not None:
        start = max(start, state['last_combat_minute'] + cfg['regen_delay_minutes'])
    elapsed = max(0, now - start)
    prior=world.entities.get(state.get('enemy_id'))
    still_engaged=bool(actor.progress.get('city_defense_target') or
        prior and prior.alive and prior.location==actor.location==state.get('combat_room'))
    if still_engaged:elapsed=0
    if elapsed:
        actor.progress['mana'] = min(cfg['max_mana'], actor.progress['mana'] + elapsed * cfg['regen_per_minute'])
    state['updated_minute'] = max(state['updated_minute'], now)
    state['last_combat_minute'] = max(state['last_combat_minute'] or now, now)
    if enemy is not None:
        state['enemy_id']=enemy.id
        state['combat_room']=actor.location
    return state, now


def engage(world, actor):
    """Mark an existing response turn, including pursuit, as active combat."""
    cfg = config(world, actor)
    if cfg and actor.alive:
        _turn(world, actor, cfg)


def try_cast(world, actor, enemy, *, lawful=False, counter=False, allies=()):
    """Return the successful cast text or None for the normal physical attack."""
    cfg = config(world, actor)
    if not cfg or actor.progress.get('companion_owner'):
        return None
    from engine import combat, ability_rules, sleep_movement, spell_life
    if (not actor.alive or not enemy.alive or actor.location != enemy.location
            or sleep_movement.asleep(world, actor) or spell_life.control_restriction(world, actor)):
        return None
    # This is called only after a real NPC attack/incident selects its enemy.
    # Recheck current permissions before resource recovery or any spell effect.
    try:
        combat.validate(world, actor, enemy)
    except ValueError:
        return None
    state, now = _turn(world, actor, cfg, enemy)
    if state['last_cast_minute'] is not None and now - state['last_cast_minute'] < cfg['cast_interval_minutes']:
        return None
    allowed = friendly_allies(world, actor, enemy, allies)
    wounded = sorted((e for e in allowed if e.hp * 100 < e.max_hp * cfg['heal_below_percent']),
                     key=lambda e: (e.hp / max(1, e.max_hp), e.id))
    ids = cfg['abilities']
    start = state['rotation'] % len(ids)
    ordered = ids[start:] + ids[:start]
    options = []
    for priority in ('healing', 'ward', 'damage'):
        for ident in ordered:
            ability = world.abilities[ident]
            effect = ability['effect']
            if priority == 'healing':
                if effect not in ('heal', 'ally_heal'):
                    continue
                recipients = wounded if effect == 'ally_heal' else [e for e in wounded if e.id == actor.id]
                if not recipients:
                    continue
                target = recipients[0]
            elif priority == 'ward':
                if effect not in ('ward', 'ally_ward'):
                    continue
                hits = (ability['ability_rules'].get('utility') or {}).get('hits', ability['ability_rules'].get('ward_hits', 5))
                if actor.progress.get('ward', 0) >= ability.get('power', 0) and actor.progress.get('ward_turns', 0) >= hits:
                    continue
                target = actor
            else:
                if effect != 'damage':
                    continue
                target = enemy
            options.append((ident, target))
    for ident, target in options:
        try:
            text = ability_rules.cast_npc(world, actor, world.abilities[ident], target.id,
                                         lawful=lawful, counter=counter, allowed_allies=allowed)
        except ValueError:
            continue
        state['last_cast_minute'] = now
        state['rotation'] = (ids.index(ident) + 1) % len(ids)
        return actor.name + ' casts ' + text
    return None
