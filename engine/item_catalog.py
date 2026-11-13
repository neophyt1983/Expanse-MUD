"""Live, bounded item/recipe browsing and unambiguous command selection.

Indexes here are request-local. Creator edits, including nested in-place edits,
are visible on the very next request; nothing derived is persisted in a save.
"""
from collections import Counter
from dataclasses import dataclass
import shlex

PAGE_SIZE = 20
CHOICE_LIMIT = 8
TEXT_LIMIT = 180


def short(value, limit=TEXT_LIMIT):
    text = ' '.join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def order(row):
    return str(row.get('name', '')).casefold(), str(row.get('id', '')).casefold(), str(row.get('id', ''))


def matches(rows, query):
    """Exact ID wins over exact name; partial matches never pick a first row."""
    query = query.strip()
    if not query:
        return []
    # Repeated inventory units are one selectable definition.
    rows = list({row.get('id', id(row)): row for row in rows}.values())
    exact_ids = [row for row in rows if str(row.get('id', '')) == query]
    if exact_ids:
        return exact_ids
    query = query.casefold()
    def plain(text):
        return text.replace("'",'').replace('’','').casefold()
    ids = [row for row in rows if str(row.get('id', '')).casefold() == query]
    if ids:
        return ids
    names = [row for row in rows if plain(str(row.get('name', ''))) == plain(query)]
    if names:
        return names
    return [row for row in rows if query in str(row.get('name', '')).casefold()
            or query in str(row.get('id', '')).casefold()]


def counted(value, singular, plural=None):
    label=singular if value==1 else (plural or singular+'s')
    return f'{value:g} {label}'


def goods_amount(row, number):
    unit=row.get('quantity_names')
    if isinstance(unit,list) and len(unit)==2:
        return counted(number,unit[0],unit[1])
    return f"{row['name']} × {number}"


def ambiguity(rows):
    choices = sorted(rows, key=order)
    shown = '; '.join(f"{short(row.get('name', 'Unnamed entry'), 70)}"
                      for row in choices[:CHOICE_LIMIT])
    more = f'; {len(choices) - CHOICE_LIMIT} more matches' if len(choices) > CHOICE_LIMIT else ''
    return f'Be more specific: {shown}{more}. Choose an entry in the list, or narrow the name search.'


def choose(rows, query, missing='No matching object is available.'):
    found = matches(rows, query)
    if not found:
        raise ValueError(missing)
    if len(found) != 1:
        raise ValueError(ambiguity(found))
    return found[0]


def item_rows(world, ids):
    return [dict(world.items[iid], id=iid) for iid in dict.fromkeys(ids) if iid in world.items]


@dataclass
class Request:
    words: list
    filters: dict
    page: int = 1


def parse(args, recipe=False):
    allowed = {'slot', 'type', 'collection', 'form', 'material', 'tier', 'owned'}
    if recipe:
        allowed |= {'station', 'kind', 'ingredient', 'output'}
        allowed.discard('owned')
    try:
        tokens = shlex.split(args)
    except ValueError as exc:
        raise ValueError('Close the quote in your catalog search.') from exc
    words, filters, page = [], {}, 1
    pos = 0
    while pos < len(tokens):
        token = tokens[pos]
        if token in ('page', '--page'):
            pos += 1
            if pos == len(tokens):
                raise ValueError('Use page:<positive number>, for example page:2.')
            key, value = 'page', tokens[pos]
        elif ':' in token or '=' in token:
            key, value = token.replace('=', ':', 1).split(':', 1)
            key = key.lstrip('-').casefold()
        else:
            words.append(token.casefold())
            pos += 1
            continue
        if key == 'page':
            if not value.isascii() or not value.isdigit() or len(value) > 6 or not 1 <= int(value) <= 100000:
                raise ValueError('Use page:<positive number>, for example page:2.')
            page = int(value)
        elif key not in allowed or not value:
            raise ValueError('Filters: ' + ', '.join(sorted(allowed)) + '; page:<number>.')
        elif key == 'owned' and value.casefold() not in ('true', 'false'):
            raise ValueError('Use owned:true or owned:false.')
        else:
            filters[key] = value.casefold()
        pos += 1
    return Request(words, filters, page)


def _item_field(item, field):
    wardrobe = item.get('wardrobe', {})
    if field == 'slot':
        return item.get('slot') or (item.get('type') if item.get('type') in ('weapon', 'armor') else '')
    if field in ('collection', 'form', 'tier'):
        return wardrobe.get(field, '')
    if field == 'material':
        return item.get('appearance', {}).get('material', wardrobe.get('construction', ''))
    return item.get(field, '')


def _fields(world, row, field, recipe):
    if not recipe:
        return [_item_field(row, field)]
    if field in ('station', 'kind'):
        return [row.get(field, 'hand' if field == 'station' else 'crafting')]
    if field in ('ingredient', 'output'):
        return list(row.get('ingredients' if field == 'ingredient' else 'outputs', {}))
    outputs = [world.items[iid] for iid in row.get('outputs', {}) if iid in world.items]
    return [_item_field(item, field) for item in outputs] or [_item_field(row, field)]


def _search_text(world, row, recipe):
    parts = [row.get('id', ''), row.get('name', '')]
    parts.extend(row.get('wardrobe', {}).values())
    if recipe:
        parts.extend([row.get('station', 'hand'), row.get('kind', 'crafting')])
        for field in ('ingredients', 'outputs'):
            for iid in row.get(field, {}):
                parts.extend([iid, world.items.get(iid, {}).get('name', '')])
    return ' '.join(str(part) for part in parts).casefold()


def page(world, args='', *, recipe=False, player=None, wardrobe=False, ids=None):
    """Return at most PAGE_SIZE definitions, plus a count and the parsed request."""
    request = parse(args, recipe)
    definitions = getattr(world, 'recipes', {}) if recipe else world.items
    owned = set(player.inventory) if player is not None else set()
    selected = set(ids) if ids is not None else None
    if player is not None and player.is_player:
        from engine import knowledge
        if recipe: knowledge.learn_local_recipes(world, player)
        visible = knowledge.ids(world, player, 'recipes' if recipe else 'items')
        selected = visible if selected is None else selected & visible
    rows = []
    for ident, definition in definitions.items():
        if selected is not None and ident not in selected:
            continue
        row = dict(definition, id=ident)
        if wardrobe and not row.get('wardrobe'):
            continue
        if any((ident in owned) != (value == 'true') if field == 'owned' else
               value not in {str(v).casefold() for v in _fields(world, row, field, recipe)}
               for field, value in request.filters.items()):
            continue
        if request.words:
            searchable = _search_text(world, row, recipe)
            if not all(word in searchable for word in request.words):
                continue
        rows.append(row)
    rows.sort(key=order)
    total = len(rows)
    start = (request.page - 1) * PAGE_SIZE
    return rows[start:start + PAGE_SIZE], total, request


def header(label, total, request):
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start = (request.page - 1) * PAGE_SIZE
    if not total:
        return f'{label}: no matching entries.'
    if request.page > pages:
        return f'{label}: page {request.page} is out of range. {total} matches; pages 1–{pages}.'
    return f'{label}: {total} matches | page {request.page}/{pages} | {start + 1}–{min(start + PAGE_SIZE, total)}'


def _quantities(world, quantities):
    parts = [f"{count} {short(world.items.get(iid, {}).get('name', iid), 55)}"
             for iid, count in list(quantities.items())[:CHOICE_LIMIT]]
    if len(quantities) > CHOICE_LIMIT:
        parts.append(f'+{len(quantities) - CHOICE_LIMIT} more')
    return ', '.join(parts) or 'none'


def browse(world, args='', *, recipe=False, player=None, wardrobe=False, ids=None):
    rows, total, request = page(world, args, recipe=recipe, player=player, wardrobe=wardrobe, ids=ids)
    label = 'Recipes' if recipe else ('Wardrobe' if wardrobe else ('Inventory' if ids is not None else 'Item catalog'))
    lines = [header(label, total, request)]
    counts = Counter(player.inventory) if player is not None else Counter()
    made_by = {}
    if not recipe:
        displayed = {row['id'] for row in rows}
        from engine import knowledge
        known_recipes = knowledge.ids(world, player, 'recipes') if player is not None else set(getattr(world, 'recipes', {}))
        for rid, rec in getattr(world, 'recipes', {}).items():
            if rid not in known_recipes: continue
            for iid in rec.get('outputs', {}):
                if iid in displayed:
                    made_by.setdefault(iid, []).append(rid)
    for row in rows:
        ident = row['id']
        if recipe:
            lines.append(f"{short(row.get('name', ident), 95)} | {short(row.get('station', 'hand'), 30)} | {row.get('minutes', 5)} min")
            lines.append('  Needs: ' + _quantities(world, row.get('ingredients', {})))
            lines.append('  Makes: ' + _quantities(world, row.get('outputs', {})))
        else:
            extra = [str(_item_field(row, 'slot') or row.get('type', 'item'))]
            if row.get('type'):
                extra.append(str(row['type']))
            if row.get('wardrobe', {}).get('collection'):
                extra.append(row['wardrobe']['collection'])
            if counts[ident]:
                extra.append(f'owned ×{counts[ident]}')
            if player is not None and ident in player.equipped.values():
                extra.append('[equipped]')
            if row.get('attack_bonus'):
                extra.append(f"attack {row['attack_bonus']:+}")
            if row.get('defense_bonus'):
                extra.append(f"defense {row['defense_bonus']:+}")
            lines.append(f"{short(row.get('name', ident), 95)} | " + ' | '.join(extra))
            recipes = sorted(made_by.get(ident, []))
            if recipes:
                lines.append('  Recipe: ' + short(world.recipes[recipes[0]].get('name', 'Recipe'), 110) + (f' (+{len(recipes) - 1} alternatives)' if len(recipes) > 1 else ''))
    if len(rows) == 1:
        description = rows[0].get('description')
        if description:
            lines.append(short(description, 500))
        visual = rows[0].get('appearance', {})
        if visual:
            lines.append('Appearance: ' + short(', '.join(f'{key}: {value}' for key, value in visual.items()), 350))
        if not recipe and rows[0].get('location') and (player is None or rows[0]['location'] in knowledge.ids(world,player,'rooms')):
            origin = rows[0]['location']
            lines.append('Origin: ' + short(world.rooms[origin].name if origin in world.rooms else origin, 150))
    if recipe:
        lines.append('Use craft <recipe name> (cook for cooking); materials <ingredient name> for known sources. Search: recipes <words> slot:head station:forge collection:gear ingredient:<name> page:2')
    else:
        lines.append('Use equip <item name> for carried items; browse known recipes for ingredients. Search: catalog <words> slot:head collection:gear owned:true page:2')
    return '\n'.join(lines)
