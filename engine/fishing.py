"""Fishing is a local resource action; a rod is carried, not worn.

The shipped rod keeps its stable ID. Creator-authored rods may opt in with
``tool_kind: fishing``. Existing authored equipment slots remain authoritative.
"""


def is_rod(item):
    return item.get('type') == 'tool' and (
        item.get('id') == 'lw_rod' or item.get('tool_kind') == 'fishing')


def sites(world, room_id, rod_id=None):
    ids = getattr(world, 'room_details', {}).get(room_id, {}).get('resources', [])
    resources = getattr(world, 'resources', {})
    return [resources[rid] for rid in ids if rid in resources
            and is_rod(world.items.get(resources[rid].get('tool'), {}))
            and (rod_id is None or resources[rid].get('tool') == rod_id)]


def fish(ctx, query='', rod_id=None):
    from engine import item_catalog, living
    rows = sites(ctx.world, ctx.player.location, rod_id)
    if not rows:
        return 'There is no fishable resource here. Carry your fishing rod to a fishing site; use survey to check local resources.'
    if query.strip():
        selected = item_catalog.choose(rows, query, missing='That fishing site is not available here. Use survey to see local fishing sites.')
    elif len(rows) == 1:
        selected = rows[0]
    else:
        return 'Choose a fishing site: ' + '; '.join(row['name'] for row in rows) + '. Use fish <site name>.'
    # One shared harvest path enforces tools, seasons, damage, depletion,
    # cooldowns and quest credit. This never consumes or equips the rod.
    return living.command(ctx, selected['id'], 'gather')
