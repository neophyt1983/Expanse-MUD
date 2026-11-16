"""Interpret optional authored combat loot; no world content is generated here.

A matching tier rolls one common bundle: its positive currency range and one
weighted item stack succeed together. Bonus entries roll independently of that
bundle and of one another. Existing carried money and fixed drops are separate.
"""
import math
import random


def configured(definition):
    table = definition.get('loot_table')
    return (isinstance(table, dict) and type(table.get('version')) is int and table['version'] == 1
            and isinstance(table.get('tiers'), list) and bool(table['tiers']))


def effective_level(definition, actor):
    """Read base threat and earned growth without changing either of them."""
    base = definition.get('combat_level', 1)
    advancement = actor.progress.get('advancement_v1', {})
    earned = advancement.get('level', 1) if isinstance(advancement, dict) else 1
    base = base if type(base) is int else 1
    earned = earned if type(earned) is int else 1
    return max(1, min(100, base + max(0, earned - 1)))


def _succeeds(chance, rng):
    return chance >= 1 or chance > 0 and rng() < chance


def _quantity(row, rng):
    low, high = row['min'], row['max']
    return low if low == high else low + min(high - low, int(rng() * (high - low + 1)))


def roll(world, victim, *, rng=None):
    """Return one finite supplemental pool, or None when not configured/eligible.

    Callers own death idempotency and distribution. This function never grants
    goods, alters progression, writes a save, or makes per-participant rolls.
    """
    from engine import spell_life
    if spell_life.no_rewards(victim):return None
    definition = world.npcs.get(victim.source_def, {})
    if (not configured(definition) or victim.is_player
            or victim.progress.get('companion_owner')
            or victim.progress.get('zoo_exhibit') or definition.get('zoo_exhibit')):
        return None
    level = effective_level(definition, victim)
    tiers = definition['loot_table']['tiers']
    selected = next(((index, tier) for index, tier in enumerate(tiers)
                     if tier['min_level'] <= level <= tier['max_level']), None)
    if selected is None:
        return None
    index, tier = selected
    rng = rng or random.random
    result = dict(level=level, tier=index, bundle=False, gold=0, items=[])
    if _succeeds(tier['chance'], rng):
        entries = tier['items']
        ticket = rng() * sum(entry['weight'] for entry in entries)
        chosen = entries[-1]
        for entry in entries:
            ticket -= entry['weight']
            if ticket < 0:
                chosen = entry
                break
        result['bundle'] = True
        result['gold'] = _quantity(tier['gold'], rng)
        result['items'].extend([chosen['item']] * _quantity(chosen, rng))
    for entry in tier.get('bonus', []):
        if _succeeds(entry['chance'], rng):
            result['items'].extend([entry['item']] * _quantity(entry, rng))
    return result


def possible_items(definition):
    """Item references with a possible roll at a reachable authored level."""
    if not configured(definition) or definition.get('zoo_exhibit'):
        return set()
    base = definition.get('combat_level', 1)
    base = base if type(base) is int else 1
    items = set()
    for tier in definition['loot_table']['tiers']:
        if not isinstance(tier, dict):
            continue
        low, high = tier.get('min_level'), tier.get('max_level')
        if type(low) is not int or type(high) is not int or not 1 <= low <= high <= 100 or high < max(1, base):
            continue
        chance = tier.get('chance')
        common = type(chance) in (int, float) and 0 < chance <= 1 and math.isfinite(chance)
        for key in ('items', 'bonus'):
            entries = tier.get(key, [])
            if not isinstance(entries, list) or key == 'items' and not common:
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get('item'), str):
                    continue
                amount, maximum = entry.get('min'), entry.get('max')
                if type(amount) is not int or type(maximum) is not int or not 1 <= amount <= maximum <= 100:
                    continue
                value = entry.get('weight' if key == 'items' else 'chance')
                possible = (type(value) is int and 0 < value <= 1000000) if key == 'items' else (
                    type(value) in (int, float) and 0 < value <= 1 and math.isfinite(value))
                if possible:
                    items.add(entry['item'])
    return items


def validate(data):
    """Validate creator data for the loader, editor and reference audit."""
    issues = []
    item_ids = {row['id'] for row in data.get('item', [])}

    def integer(value, low, high):
        return type(value) is int and low <= value <= high

    def probability(value):
        return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)

    def fields(row, allowed, where):
        extra = set(row) - set(allowed)
        if extra:
            issues.append(where + ': unknown field(s) ' + ', '.join(sorted(map(str, extra))))

    def quantity(row, maximum, where):
        if (not isinstance(row, dict) or not integer(row.get('min'), 1, maximum)
                or not integer(row.get('max'), 1, maximum)
                or row['min'] > row['max']):
            issues.append(where + ': requires integer 1 <= min <= max <= ' + str(maximum))

    for definition in data.get('npc', []):
        where = 'npc ' + str(definition.get('id', '?'))
        if 'combat_level' in definition and not integer(definition['combat_level'], 1, 100):
            issues.append(where + ': combat_level must be an integer from 1 to 100')
        table = definition.get('loot_table', {})
        if table == {}:
            continue
        if not isinstance(table, dict):
            issues.append(where + ': loot_table must be an object (empty {} disables it)')
            continue
        fields(table, ('version', 'tiers'), where + '.loot_table')
        if type(table.get('version')) is not int or table['version'] != 1:
            issues.append(where + ': loot_table.version must be 1')
        if not integer(definition.get('combat_level'), 1, 100):
            issues.append(where + ': a loot_table requires an explicit combat_level from 1 to 100')
        tiers = table.get('tiers')
        if not isinstance(tiers, list) or not 1 <= len(tiers) <= 100:
            issues.append(where + ': loot_table.tiers must contain 1–100 level tiers')
            continue
        ranges = []
        for index, tier in enumerate(tiers):
            at = where + '.loot_table.tiers[' + str(index) + ']'
            if not isinstance(tier, dict):
                issues.append(at + ': tier must be an object')
                continue
            fields(tier, ('min_level', 'max_level', 'chance', 'gold', 'items', 'bonus'), at)
            low, high = tier.get('min_level'), tier.get('max_level')
            if not integer(low, 1, 100) or not integer(high, 1, 100) or low > high:
                issues.append(at + ': requires integer 1 <= min_level <= max_level <= 100')
            else:
                if any(low <= other_high and high >= other_low for other_low, other_high in ranges):
                    issues.append(at + ': level tiers must not overlap')
                ranges.append((low, high))
            if not probability(tier.get('chance')):
                issues.append(at + ': chance must be a finite number from 0 to 1')
            quantity(tier.get('gold'), 1000000, at + '.gold')
            if isinstance(tier.get('gold'), dict):
                fields(tier['gold'], ('min', 'max'), at + '.gold')
            for key in ('items', 'bonus'):
                entries = tier.get(key, [] if key == 'bonus' else None)
                minimum = 1 if key == 'items' else 0
                if not isinstance(entries, list) or not minimum <= len(entries) <= 64:
                    issues.append(at + '.' + key + ': requires ' + str(minimum) + '–64 entries')
                    continue
                for pos, entry in enumerate(entries):
                    entry_at = at + '.' + key + '[' + str(pos) + ']'
                    if not isinstance(entry, dict):
                        issues.append(entry_at + ': entry must be an object')
                        continue
                    scale = 'weight' if key == 'items' else 'chance'
                    fields(entry, ('item', 'min', 'max', scale), entry_at)
                    item = entry.get('item')
                    if not isinstance(item, str) or item not in item_ids:
                        issues.append(entry_at + ': item must reference an authored item')
                    quantity(entry, 100, entry_at)
                    if scale == 'weight' and not integer(entry.get('weight'), 1, 1000000):
                        issues.append(entry_at + ': weight must be an integer from 1 to 1000000')
                    if scale == 'chance' and not probability(entry.get('chance')):
                        issues.append(entry_at + ': chance must be a finite number from 0 to 1')
    return issues
