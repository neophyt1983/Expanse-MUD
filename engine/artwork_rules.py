"""Creator validation for finite artwork plans and authored patrons."""
from engine.artworks import KINDS


def validate(data):
    by = {kind: {row['id']: row for row in data.get(kind, [])} for kind in ('recipe', 'npc', 'item', 'building', 'room')}
    errors = []

    def issue(ident, text):errors.append(ident + ': ' + text)

    def number(row, key, low, high, ident, default=0):
        value = row.get(key, default)
        if type(value) is not int or not low <= value <= high:issue(ident, key + ' must be a whole number from ' + str(low) + ' to ' + str(high))

    for ident, row in by['recipe'].items():
        cfg = row.get('artwork', {})
        if not isinstance(cfg, dict):issue(ident, 'artwork must be an object');continue
        if not cfg:continue
        if set(cfg) - {'kind', 'style', 'title', 'description', 'text', 'difficulty', 'min_skill', 'building'}:
            issue(ident, 'unsupported artwork plan fields')
        if cfg.get('kind') not in KINDS:issue(ident, 'choose poetry, painting, sculpture or architecture')
        if not isinstance(cfg.get('style'), str) or not 1 <= len(cfg['style']) <= 64:issue(ident, 'artwork needs a bounded style')
        for field, limit in [('title', 100), ('description', 2000), ('text', 4000)]:
            if field in cfg and (not isinstance(cfg[field], str) or len(cfg[field]) > limit):issue(ident, field + ' is invalid or too long')
        number(cfg, 'difficulty', 0, 100, ident, 20);number(cfg, 'min_skill', 0, 100, ident)
        number(row, 'minutes', 1, 240, ident, 10)
        ingredients = row.get('ingredients')
        if (not isinstance(ingredients, dict) or not 1 <= len(ingredients) <= 8 or
                any(item not in by['item'] or by['item'][item].get('anchored_readable') or type(n) is not int or not 1 <= n <= 20
                    for item, n in ingredients.items())):
            issue(ident, 'artwork requires finite quantities of 1–8 actual movable materials')
        if row.get('outputs'):issue(ident, 'artwork plans create one unique work, without ordinary recipe outputs')
        if cfg.get('building'):
            if cfg.get('kind') != 'architecture' or cfg['building'] not in by['building']:
                issue(ident, 'architectural subject must be an actual building')
        elif cfg.get('kind') == 'architecture':issue(ident, 'architecture plans must identify their real building subject')
    for ident, row in by['npc'].items():
        taste = row.get('art_taste', {})
        if not isinstance(taste, dict):issue(ident, 'art_taste must be an object');taste = {}
        if set(taste) - {'styles', 'kinds'}:issue(ident, 'unsupported artistic taste fields')
        for field in ('styles', 'kinds'):
            values = taste.get(field, {})
            if (not isinstance(values, dict) or len(values) > 16 or any(not isinstance(key, str) or len(key) > 64 or
                    (field == 'kinds' and key not in KINDS) or type(value) is not int or not -30 <= value <= 30
                    for key, value in values.items())):issue(ident, 'taste weights must be bounded style/kind values from -30 to 30')
        offers = row.get('art_commissions', [])
        if not isinstance(offers, list) or len(offers) > 16:issue(ident, 'at most16 authored finite commissions are supported');continue
        seen = set()
        for offer in offers:
            if not isinstance(offer, dict):issue(ident, 'commission must be an object');continue
            if set(offer) - {'id', 'name', 'enabled', 'recipe', 'price', 'min_quality', 'min_appreciation'}:issue(ident, 'unsupported commission fields')
            if not isinstance(offer.get('id'), str) or not offer['id'] or offer['id'] in seen:issue(ident, 'commission IDs must be nonempty and distinct')
            else:seen.add(offer['id'])
            if not isinstance(offer.get('name'), str) or not 1 <= len(offer['name']) <= 160:issue(ident, 'commission needs a bounded name')
            if type(offer.get('enabled', True)) is not bool:issue(ident, 'commission enabled must be boolean')
            if not by['recipe'].get(offer.get('recipe'), {}).get('artwork'):issue(ident, 'commission must reference a real artistic plan')
            number(offer, 'price', 1, 10000, ident, 1)
            number(offer, 'min_quality', 0, 100, ident);number(offer, 'min_appreciation', 0, 100, ident)
        plan = row.get('art_plan', {})
        if not isinstance(plan, dict):issue(ident, 'art_plan must be an object');continue
        if not plan:continue
        if set(plan) - {'enabled', 'recipes', 'patrons', 'explore'}:issue(ident, 'unsupported art_plan fields')
        for key in ('enabled', 'explore'):
            if type(plan.get(key, False)) is not bool:issue(ident, 'art_plan.' + key + ' must be boolean')
        recipes, patrons = plan.get('recipes', []), plan.get('patrons', [])
        if (not isinstance(recipes, list) or not 1 <= len(recipes) <= 16 or
                any(not isinstance(value, str) or not by['recipe'].get(value, {}).get('artwork') for value in recipes)):
            issue(ident, 'art_plan needs explicitly selected existing artwork plans')
        if (not isinstance(patrons, list) or not 1 <= len(patrons) <= 16 or
                any(not isinstance(value, str) or value not in by['npc'] for value in patrons)):
            issue(ident, 'art_plan needs explicitly selected existing patron sources')
    return errors
