"""Finite prepared meals that active residents can collect in person."""
from collections import defaultdict, deque
from engine import frontiers, geology_impacts, livelihoods, locks, needs_market


def fund(world, rule, ledger, budget, active, meal):
    lots = ledger.setdefault('meal_counters', {})
    rooms = list(dict.fromkeys((rule['market'], rule['kitchen'])))
    capacity = active * rule['daily_portions']
    available = min(budget, ledger['stock'].get(meal, 0), max(0, capacity - sum(lots.values())))
    sent = 0
    for index, room in enumerate(rooms):
        if geology_impacts.room_unusable(world, room):
            continue
        target = (capacity + len(rooms) - 1 - index) // len(rooms)
        quantity = min(available-sent, max(0, target-lots.get(room, 0)))
        if quantity:
            lots[room] = lots.get(room, 0) + quantity
            ledger['stock'][meal] -= quantity
            sent += quantity
    return sent


def routes(world, rules):
    """Rank same-region counters by walking distance; validate each actual move."""
    incoming = defaultdict(list)
    for room, data in world.rooms.items():
        for direction, dest in data.exits.items():
            if dest in world.rooms and world.rooms[dest].group == data.group:
                incoming[dest].append((room, direction))
    links = defaultdict(list)
    for city, rule in rules.items():
        for source in dict.fromkeys((rule['market'], rule['kitchen'])):
            if source not in world.rooms:
                continue
            found = {source}
            queue = deque([(source, 0)])
            links[source].append((0, city, source, None, None))
            while queue:
                dest, distance = queue.popleft()
                for room, direction in incoming.get(dest, ()):
                    if room in found or world.room_details.get(room, {}).get('requires_boat'):
                        continue
                    found.add(room)
                    links[room].append((distance+1, city, source, direction, dest))
                    queue.append((room, distance+1))
    for choices in links.values():
        choices.sort()
    return links


def options(world, actor, rules):
    # Refresh after edits to any authored exit within one game half-hour.
    # A replaced or removed next hop forces immediate local recalculation.
    key = world.living_state['minute'] // 30
    cached = getattr(world, '_meal_counter_routes', None)
    if cached and cached[0] == key:
        choices = cached[1].get(actor.location, ())
        exits = world.rooms[actor.location].exits
        if all(counter in world.rooms and (not direction or (exits.get(direction) == dest and dest in world.rooms))
               for _, _, counter, direction, dest in choices):
            return choices
    links = routes(world, rules)
    world._meal_counter_routes = (key, links)
    return links.get(actor.location, ())


def meal_break(world, actor):
    from engine import household_provisions as provisions, life_stages
    cfg = provisions.config(world)
    if not cfg or not needs_market.applies(world, actor) or actor.location not in world.rooms:
        return False
    ledger = world.living_state.get(provisions.KEY, {})
    if not ledger or needs_market.state(actor)['hunger'] < needs_market.cfg(world, actor)['threshold']:
        return False
    if any(needs_market.effects(world, item).get('hunger', 0) > 0 for item in actor.inventory):
        return False
    local = world.rooms[actor.location]
    if local.group != actor.group_id:
        return False
    for _, city, counter, direction, dest in options(world, actor, cfg['cities']):
        rule = cfg['cities'].get(city)
        if not rule or counter not in (rule['kitchen'], rule['market']) or world.rooms[counter].group != actor.group_id:
            continue
        account = ledger.get(city, {})
        lots = account.get('meal_counters', {})
        quantity = lots.get(counter, 0)
        if quantity <= 0 or not livelihoods.room_open(world, counter):
            continue
        if actor.location == counter:
            meal = rule['meal_item']
            if not needs_market.wants(world, actor, meal):
                return False
            take = min(quantity, rule['daily_portions'])
            lots[counter] -= take
            account['collected'] = account.get('collected', 0) + take
            actor.inventory.extend([meal] * take)
            needs_market.use(world, actor, meal)
            actor.activity = 'collecting prepared meals'
            return True
        # Dedicated schedules, public posts and private businesses keep their staff.
        # Family, escort, emergency and dependent routines have already claimed their turns.
        if (not life_stages.for_entity(world, actor)['adult'] or not livelihoods.scheduled_awake(world, actor)
                or livelihoods.on_shift(world, actor)):
            return False
        if (not direction or local.exits.get(direction) != dest or dest not in world.rooms
                or world.rooms[dest].group != actor.group_id or geology_impacts.room_unusable(world, dest)
                or frontiers.blocked(world, actor.location, direction, actor, lock_index=locks.index(world))):
            continue
        world.move_entity(actor.id, dest)
        actor.activity = 'walking to the co-operative meal counter'
        return True
    return False
