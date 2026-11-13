"""Narrow compatibility for the two stock shields authored before offhand slots.

Never infer equipment rules from creator item names. Only known legacy stock
fields are repaired in memory; authored files and inventories are not rewritten.
"""
LEGACY = {
    'exp_buckler': dict(name='Wooden Buckler', type='armor', slot='armor',
                        defense_bonus=2, description='Equipment that protects its wearer. Uses the existing armor slot.'),
    'iron_shield': dict(name='Iron Shield', type='armor', slot='armor',
                        defense_bonus=2, description='A round shield.'),
}


def normalize_item(item):
    expected = LEGACY.get(item.get('id'))
    if expected and all(item.get(key) == value for key, value in expected.items()):
        return dict(item, slot='offhand')
    return item


def restore_equipped(world, entity):
    """Move a legacy equipped shield without evicting an existing offhand.

On conflict the shield stays carried, not equipped twice. Do not guess which
previous coat the player wanted or auto-equip an arbitrary inventory item.
"""
    iid = entity.equipped.get('armor')
    item = world.items.get(iid, {})
    expected = LEGACY.get(iid)
    if (expected and item.get('slot') == 'offhand'
            and all(item.get(k) == v for k, v in expected.items() if k not in ('slot', 'description'))
            and item.get('description') in (expected['description'], 'A wooden shield held in the offhand, alongside worn armor.')
            and iid in entity.inventory):
        del entity.equipped['armor']
        entity.equipped.setdefault('offhand', iid)
