"""Daily food production and distribution for authored household co-operatives.

Opening registers describe residents outside the ordinary actor simulation.
The co-op feeds these people in aggregate. Active NPCs use their individual
inventories and needs. All food moves on the authoritative game clock.
"""
from collections import defaultdict
from engine import gazette, geology_impacts, living, society, worldtime

KEY = 'household_provisions_v1'
DAY = worldtime.MINUTES_PER_DAY


def validate(cfg, rooms, items, recipes):
    """Check the editor's rules against the same records the engine will use."""
    if cfg is None:
        return []

    def integer(value, low=1):
        return type(value) is int and value >= low

    if not isinstance(cfg, dict) or type(cfg.get('version')) is not int or cfg['version'] != 1:
        return ['household_provisions requires version 1']
    if not integer(cfg.get('issue_minute'), 0) or cfg['issue_minute'] >= DAY:
        return ['household_provisions issue_minute must be on the 25-hour clock']
    cities = cfg.get('cities')
    if not isinstance(cities, dict) or not cities:
        return ['household_provisions requires named cities']
    errors = []
    prefixes = set()
    for city, rule in cities.items():
        if not isinstance(city, str) or not city.strip() or not isinstance(rule, dict):
            errors.append('household_provisions requires a name and rules for each city')
            continue
        def error(message):
            errors.append(f'{city} household provisions: {message}')
        for key in ('member_count', 'daily_portions', 'store_days', 'beds_per_grower', 'rotation_days',
                    'planting_beds', 'batches_per_cook', 'servings_per_porter'):
            if not integer(rule.get(key)):
                error(f'{key} must be a positive integer')
        prefix = rule.get('member_prefix')
        if not isinstance(prefix, str) or not prefix.endswith('_') or prefix in prefixes:
            error('choose a distinct register prefix ending in an underscore')
        else:
            prefixes.add(prefix)
        for key in ('field', 'garden', 'kitchen', 'market'):
            if not isinstance(rule.get(key), str) or rule[key] not in rooms:
                error(f'{key} needs a known room')
        yields = rule.get('seasonal_yield_percent')
        if (not isinstance(yields, dict) or set(yields) != set(worldtime.SEASONS)
                or any(not integer(n, 0) for n in yields.values())):
            error('set nonnegative yield percentages for all four seasons')
        crops = rule.get('crop_batch')
        if (not isinstance(crops, dict) or not crops
                or any(i not in items or not integer(n) for i, n in crops.items())):
            error('crop_batch needs known items and positive quantities')
            crops = {}
        meal = rule.get('meal_item')
        if not isinstance(meal, str) or meal not in items or meal in crops:
            error('meal_item must be a known prepared item')
            meal = None
        recipe_id = rule.get('recipe')
        recipe = recipes.get(recipe_id, {}) if isinstance(recipe_id, str) else {}
        ingredients = recipe.get('ingredients')
        if (not isinstance(ingredients, dict) or not ingredients or not ingredients.keys() <= crops.keys()
                or any(not integer(n) for n in ingredients.values()) or recipe.get('outputs') != {meal: 1}):
            error('choose a recipe that uses the crops and produces one meal')
        workforce = rule.get('workforce')
        if not isinstance(workforce, dict):
            error('specify a workforce')
            continue
        assigned = set()
        maximum = rule.get('member_count')
        for role in ('growers', 'cooks', 'porters'):
            members = workforce.get(role)
            if not isinstance(members, list):
                error(f'{role} must list register member numbers')
                continue
            for member in members:
                if not integer(member) or not integer(maximum) or member > maximum or member in assigned:
                    error(f'{role} contains an invalid or duplicate assignment')
                    break
                assigned.add(member)
    return errors


def config(world):
    cfg = world.metadata.get('household_provisions')
    if isinstance(cfg, dict) and cfg.get('version') == 1 and cfg.get('cities') and 'issue_minute' in cfg:
        return cfg
    return {}


def unavailable(world):
    """Index active and deceased members once for this distribution."""
    by_prefix = defaultdict(set)
    def add(uid):
        if isinstance(uid, str):
            prefix, sep, serial = uid.rpartition('_')
            if sep and serial.isascii() and serial.isdecimal() and len(serial) <= 9:
                by_prefix[prefix + '_'].add(int(serial))
    for actor in world.entities.values():
        if not actor.is_player:
            add(actor.source_def)
    for uid in world.killed_npcs:
        add(uid)
    return by_prefix


def distribute(world, city, rule, absent, ledger, day, minute):
    member_count = rule['member_count']
    population = member_count - sum(1 for uid in absent if 1 <= uid <= member_count)
    jobs = rule['workforce']
    def staffing(role):
        return sum(1 for uid in jobs[role] if uid not in absent)
    def ready(rid):
        return rid in world.rooms and not geology_impacts.room_unusable(world, rid)
    demand = population * rule['daily_portions']
    crops = rule['crop_batch']
    stock = ledger.setdefault('stock', {})
    meal = rule['meal_item']
    before = stock.get(meal, 0)
    raw_before = {iid: stock.get(iid, 0) for iid in crops}
    field = rule['field']
    latitude = world.room_details.get(field, {}).get('climate', {}).get('latitude', 45)
    season = worldtime.season(minute, latitude)
    # Beds rotate by cohort; a particular bed yields at most once per rotation.
    growers = staffing('growers')
    beds = min(rule['planting_beds'], growers * rule['beds_per_grower'])
    rotation = rule['rotation_days']
    share = (beds + rotation - 1 - day % rotation) // rotation
    potential = share * rule['seasonal_yield_percent'][season] // 100
    limit = member_count * rule['daily_portions'] * rule['store_days']
    batches = min(potential, *(max(0, limit * n - stock.get(iid, 0)) // n for iid, n in crops.items())) if ready(field) else 0
    for iid, count in crops.items():
        stock[iid] = stock.get(iid, 0) + batches * count

    recipe = world.recipes.get(rule['recipe'], {})
    inputs = recipe.get('ingredients') or {}
    outputs = recipe.get('outputs') or {}
    cooked = 0
    if (ready(rule['kitchen']) and inputs and inputs.keys() <= crops.keys() and outputs == {meal: 1}
            and all(type(n) is int and n > 0 for n in inputs.values())):
        cooked = min(staffing('cooks') * rule['batches_per_cook'], max(0, limit - before),
                     *(stock.get(iid, 0) // n for iid, n in inputs.items()))
        for iid, n in inputs.items():
            stock[iid] -= cooked * n
    stock[meal] = before + cooked

    market = rule['market']
    hours = world.room_details.get(market, {}).get('opening_hours') or {}
    open_for_issue = ready(market) and (minute-hours.get('start', 0)) % DAY < hours.get('duration', DAY)
    carrying = staffing('porters') * rule['servings_per_porter'] if open_for_issue else 0
    issued = min(stock[meal], demand, carrying)
    stock[meal] -= issued
    sent = 0
    if carrying > issued and stock[meal] > demand and world.room_details[market].get('workshop'):
        workshop, counter = society.shop(world, market)
        space = max(0, workshop.get('stock_limit', 40) - counter['stock'].get(meal, 0))
        sent = min(space, carrying-issued, stock[meal]-demand)
        counter['stock'][meal] = counter['stock'].get(meal, 0) + sent
        stock[meal] -= sent
    from engine import meal_counters, needs_market
    active = sum(1 for actor in world.entities.values()
                 if actor.group_id == world.rooms[market].group and needs_market.applies(world, actor))
    counter_delivery = meal_counters.fund(world, rule, ledger, max(0, carrying-issued-sent), active, meal)
    entry = dict(day=day, residents=population, growers=growers, beds=beds,
                 raw_before=raw_before, harvested={i: n*batches for i,n in crops.items()},
                 used={i: n*cooked for i,n in inputs.items()} if cooked else {},
                 opening=before, cooked=cooked, required=demand, issued=issued,
                 short=demand-issued, market_delivery=sent, counter_delivery=counter_delivery, closing=stock[meal])
    cumulative = ledger.setdefault('cumulative', {'since': day, 'short': 0, 'counter_delivery': 0})
    cumulative['short'] += entry['short']
    cumulative['counter_delivery'] += counter_delivery
    recent = ledger.setdefault('history', [])
    recent.append(entry)
    del recent[:-worldtime.DAYS_PER_WEEK]
    if entry['short']:
        headline = f"{city}'s co-operative issued {issued:,} of {demand:,} portions; {demand-issued:,} were short."
    else:
        headline = f"{city}'s co-operative issued {issued:,} portions to {population:,} registered residents."
    gazette.record(world, market, 'City life', headline, key=f'cooperative:{city}:{day}',
                   once=True, byline='Provision counter', minute=minute)


def advance(world, previous, now):
    cfg = config(world)
    if not cfg or now <= previous:
        return
    issue = cfg['issue_minute']
    first = (int(previous) - issue) // DAY + 1
    last = (int(now) - issue) // DAY
    if first > last:
        return
    state = living.state(world).setdefault(KEY, {})
    absent = unavailable(world)
    for day in range(max(0, first), last+1):
        for city, rule in cfg['cities'].items():
            ledger = state.setdefault(city, {})
            if ledger.get('day', -1) < day:
                distribute(world, city, rule, absent[rule['member_prefix']], ledger, day, day*DAY+issue)
                ledger['day'] = day


def report(ctx, args):
    cfg = config(ctx.world)
    # Reading the board never advances the clock or produces food.
    ctx.time_accounted = True
    cities = cfg['cities']
    group = ctx.room.group
    requested = args.strip().casefold()
    local = next((name for name, rule in cities.items()
                  if ctx.world.rooms.get(rule['market']) and ctx.world.rooms[rule['market']].group == group), None)
    city = next((name for name in cities if name.casefold() == requested), None) if requested else local
    if city is None:
        return 'Choose a city for the public provision account: ' + ', '.join(sorted(cities)) + '.'
    account = getattr(ctx.world, 'living_state', {}).get(KEY, {}).get(city, {})
    rows = account.get('history', [])
    clock = cfg['issue_minute']
    title = f"{city} household provision account"
    if not rows:
        return f"{title}\nThe first issue is due at {clock//60:02d}:{clock%60:02d} game time."
    row = rows[-1]
    harvested = ', '.join(f"{n:,} {ctx.world.items[iid]['name']}" for iid,n in row['harvested'].items())
    cumulative = account.get('cumulative')
    pickup = ''
    if cumulative:
        held = sum(account.get('meal_counters', {}).values())
        pickup = (f"Active pickup counters received {row.get('counter_delivery', 0):,} portions this issue "
                  f"and hold {held:,}. Household shortfall since day {cumulative['since']+1}: "
                  f"{cumulative['short']:,} portions.\n")
    return (f"{title} · day {row['day']+1}\n{row['growers']:,} growers harvested {harvested}. "
            f"The kitchens made {row['cooked']:,} portions.\nHouseholds received {row['issued']:,} of "
            f"{row['required']:,} portions for {row['residents']:,} residents. Shortfall: {row['short']:,}. "
            f"The market received {row['market_delivery']:,}. The co-operative has {row['closing']:,} portions in reserve.\n"
            f"{pickup}Last {len(rows)} issue(s): " + ', '.join(f"day {r['day']+1} — {r['short']:,} short" for r in rows) + '.')
