"""Opt-in, shared resource batches and a read-only map projection.

Visuals describe actual authored resources. They never create a mine, a crop,
inventory, or a clock tick. Legacy resources keep their original harvesting
rules until a creator explicitly configures their ``visual`` metadata.
Explicit mine ``reserve_batches`` opt into finite deposits, never regeneration.
"""
import math
from engine.worldtime import initial_minute


MAX_RESERVE_BATCHES = 1_000_000
MAX_BATCH_ITEMS = 1_000_000


MATERIAL_COLORS = {
    'lw_grain': 'grain', 'eco_grain': 'grain',
    'lw_carrot': 'carrot', 'eco_carrot': 'carrot',
    'lw_potato': 'potato', 'eco_potato': 'potato',
    'lw_onion': 'onion', 'eco_onion': 'onion',
    'lw_flax': 'fiber', 'sx_fiber': 'fiber',
    'lw_ore': 'ore', 'sx_ore': 'ore',
    'lw_crystal': 'crystal', 'sx_crystal': 'crystal',
}


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def visual_config(resource, items=None):
    """Return valid opt-in metadata, or None; never guess from a name."""
    if not isinstance(resource, dict):
        return None
    visual = resource.get('visual')
    if not isinstance(visual, dict) or not visual:
        return None
    kind, material = visual.get('kind'), visual.get('material')
    if kind not in ('crop', 'mine') or not isinstance(material, str) or not material:
        return None
    if set(visual) - {'kind', 'material', 'cultivation'}:
        return None
    if kind == 'crop' and visual.get('cultivation') not in ('cultivated', 'wild'):
        return None
    if kind == 'mine' and 'cultivation' in visual:
        return None
    yields = resource.get('yields', {})
    if not isinstance(yields, dict) or type(yields.get(material)) is not int or yields[material] < 1:
        return None
    if items is not None and material not in items:
        return None
    renewal = resource.get('renewal_minutes', 60)
    if not _number(renewal) or renewal < 0:
        return None
    if 'reserve_batches' in resource:
        capacity = resource['reserve_batches']
        if kind != 'mine' or type(capacity) is not int or not 1 <= capacity <= MAX_RESERVE_BATCHES:
            return None
        # Every yield is transferred by callers after the shared commit. Check
        # the whole finite batch first, not just the material shown on the map.
        if any(not isinstance(iid, str) or not iid or type(count) is not int
               or not 1 <= count <= MAX_BATCH_ITEMS
               or (items is not None and iid not in items)
               for iid, count in yields.items()):
            return None
        if sum(yields.values()) > MAX_BATCH_ITEMS:
            return None
    return visual


def managed(resource, items=None):
    """Explicit finite metadata must not fall back to legacy unlimited stock."""
    return (isinstance(resource, dict) and 'reserve_batches' in resource
            or visual_config(resource, items) is not None)


def validate(data):
    issues = []
    items = {row['id'] for row in data.get('item', [])}
    for resource in data.get('resource', []):
        if 'reserve_batches' in resource and visual_config(resource, items) is None:
            issues.append(resource['id'] + ': invalid finite reserve; reserve_batches '
                          'must be an integer from 1 to ' + str(MAX_RESERVE_BATCHES) +
                          ' on an explicitly configured mine with valid positive '
                          'item yields (at most ' + str(MAX_BATCH_ITEMS) +
                          ' items per batch) (resources.json)')
        if 'visual' not in resource or resource['visual'] == {}:
            continue
        if visual_config(resource, items) is None:
            issues.append(resource['id'] + ': invalid visual resource metadata; use '
                          'kind crop or mine, a yielded material item, and crop '
                          'cultivation cultivated or wild (resources.json)')
    return issues


def _state(world):
    state = getattr(world, 'living_state', {})
    return state if isinstance(state, dict) else {}


def _minute(world, minute=None):
    value = _state(world).get('minute', initial_minute(world.metadata)) if minute is None else minute
    return value if _number(value) else initial_minute(world.metadata)


def active_resources(world, room):
    """Read the active parcel plan without initializing settlements."""
    rid = getattr(room, 'id', room)
    details = getattr(world, 'room_details', {}).get(rid, {})
    resources = details.get('resources', [])
    settlements = _state(world).get('settlements', {})
    parcels = settlements.get('parcels', {}) if isinstance(settlements, dict) else {}
    parcel = parcels.get(rid, {}) if isinstance(parcels, dict) else {}
    plans = details.get('land_uses', {})
    if isinstance(parcel, dict) and isinstance(plans, dict):
        kind = parcel.get('kind')
        plan = plans.get(kind, {}) if isinstance(kind, str) else {}
        if isinstance(plan, dict) and 'resources' in plan:
            resources = plan['resources']
    return [rid for rid in resources if isinstance(rid, str)] if isinstance(resources, list) else []


def _history(world, key):
    """Reconcile latest old/new timestamps without writing on a read."""
    state = _state(world)
    nodes = state.get('resource_nodes', {})
    record = nodes.get(key, {}) if isinstance(nodes, dict) else {}
    record = record if isinstance(record, dict) else {}
    old = state.get('nodes', {})
    economy = state.get('economy', {})
    times = economy.get('harvest_times', {}) if isinstance(economy, dict) else {}
    timestamps = [record.get('last_harvest'),
                  old.get(key) if isinstance(old, dict) else None,
                  times.get(key) if isinstance(times, dict) else None]
    last = max((value for value in timestamps if _number(value)), default=None)
    planted = record.get('planted_at')
    return last, planted if _number(planted) else None


def _extracted(world, key, capacity):
    """Read finite usage without inventing past extractions or repairing saves.

    Old saves have no count, so keep their cooldown and start explicit finite
    accounting at zero. An explicitly corrupt counter/ledger fails closed:
    resetting it to zero could silently refill an exhausted deposit.
    """
    ledger = _state(world).get('resource_nodes', {})
    if not isinstance(ledger, dict):
        return capacity
    record = ledger.get(key, {})
    if not isinstance(record, dict):
        return capacity
    count = record.get('extracted_batches', 0)
    if type(count) is not int or count < 0:
        return capacity
    return min(count, capacity)


def _in_season(world, resource, room, minute):
    # climate.conditions is pure when supplied a minute. ecology.in_season
    # obtains the clock through living.state(), which initializes old worlds.
    from engine import climate
    local = climate.conditions(world, room, minute=minute)
    if local['controlled_growing']:
        return True
    if resource.get('species') and not resource.get('temperature_min_c', 0) <= local['temperature_c'] <= resource.get('temperature_max_c', 45):
        return False
    return not resource.get('seasons') or local['season'] in resource['seasons']


def _feature(world, room, resource, minute):
    visual = visual_config(resource, getattr(world, 'items', {}))
    if visual is None:
        return None
    last, planted = _history(world, room + ':' + resource['id'])
    timestamps = [value for value in (last, planted) if value is not None]
    start = max(timestamps) if timestamps else None
    renewal = resource.get('renewal_minutes', 60)
    elapsed = max(0, minute - start) if start is not None else renewal
    fraction = min(1.0, elapsed / renewal) if renewal else 1.0
    ready = fraction >= 1
    # The early quarter of the real cooldown retains the visible aftermath.
    # Commands advance the clock, so an exact-minute-only phase would vanish
    # before the player can see their own harvest on the next map packet.
    early = fraction < .25
    if visual['kind'] == 'crop':
        newly_planted = planted is not None and (last is None or planted >= last)
        stage = 'mature' if ready else ('planted' if newly_planted else 'harvested') if early else 'growing'
    else:
        stage = 'available' if ready else 'depleted' if early else 'recovering'
    capacity = resource.get('reserve_batches')
    remaining = None
    if capacity is not None:
        remaining = capacity - _extracted(world, room + ':' + resource['id'], capacity)
        if remaining == 0:
            ready, fraction, stage = False, 0.0, 'exhausted'
        else:
            stage = 'available' if ready else 'recovering'
    in_season = _in_season(world, resource, room, minute)
    if visual['kind'] == 'crop' and not in_season:
        stage = 'dormant'
    from engine import geology_impacts
    closure = geology_impacts.resource_blocked(world, room, resource['id'])
    if not closure and geology_impacts.room_unusable(world, room):
        closure = 'This site is temporarily closed for hazard recovery.'
    if closure:
        ready = False
    material = visual['material']
    result = dict(resource_id=resource['id'], name=resource.get('name', resource['id']),
                  kind=visual['kind'], material=material,
                  material_name=world.items[material].get('name', material),
                  color_key=MATERIAL_COLORS.get(material, visual['kind']),
                  stage=stage, available=ready and in_season,
                  renewal_fraction=fraction, renewal_minutes=renewal,
                  in_season=in_season)
    if closure:
        result['closure_reason'] = closure
    if visual['kind'] == 'crop':
        result['cultivation'] = visual['cultivation']
    if capacity is not None:
        result.update(capacity_batches=capacity, remaining_batches=remaining)
    return result


def room_features(world, room, minute=None):
    """Pure resource state for active, explicitly configured room resources."""
    rid = getattr(room, 'id', room)
    if rid not in world.rooms:
        return []
    now = _minute(world, minute)
    catalog = getattr(world, 'resources', {})
    result = []
    for resource_id in dict.fromkeys(active_resources(world, rid)):
        resource = catalog.get(resource_id, {})
        if not isinstance(resource, dict) or resource.get('id') != resource_id:
            continue
        feature = _feature(world, rid, resource, now)
        if feature is not None:
            result.append(feature)
    return result


def available(world, room, resource, minute=None):
    """Availability of a configured batch, including active land use."""
    rid = getattr(room, 'id', room)
    if resource.get('id') not in active_resources(world, rid):
        return False
    feature = _feature(world, rid, resource, _minute(world, minute))
    return bool(feature and feature['available'])


def exhausted(world, room, resource):
    """Whether an explicit finite mine has no batches left, independent of time."""
    visual = visual_config(resource, getattr(world, 'items', {}))
    if visual is None or 'reserve_batches' not in resource:
        return False
    rid = getattr(room, 'id', room)
    capacity = resource['reserve_batches']
    return _extracted(world, rid + ':' + resource['id'], capacity) >= capacity


def request_manual_turn(world, room, resource, actor):
    """A short in-session opportunity at renewal, not stock or a saved claim."""
    rid = getattr(room, 'id', room)
    if not actor.is_player or not actor.alive or actor.location != rid:
        return False
    if resource.get('tool') and resource['tool'] not in actor.inventory:
        return False
    if visual_config(resource, getattr(world, 'items', {})) is None or exhausted(world, rid, resource):
        return False
    if resource['id'] not in active_resources(world, rid) or available(world, rid, resource):
        return False
    now = _minute(world)
    last, planted = _history(world, rid + ':' + resource['id'])
    start = max((v for v in (last, planted) if v is not None), default=now)
    renewal = resource.get('renewal_minutes', 60)
    due = max(now, start + renewal)
    turns = getattr(world, '_manual_resource_turns', None)
    if turns is None:
        turns = world._manual_resource_turns = {}
    # Bound transient records to actual live actors and configured nodes.
    for key, requests in list(turns.items()):
        active = {pid: expiry for pid, expiry in requests.items()
                  if expiry >= now and pid in world.entities and world.entities[pid].alive}
        if active: turns[key] = active
        else: turns.pop(key, None)
    turns.setdefault(rid + ':' + resource['id'], {})[actor.id] = due + 5
    return True


def manual_turn_delay(world, room, resource, actor):
    rid = getattr(room, 'id', room)
    expiry = getattr(world, '_manual_resource_turns', {}).get(rid + ':' + resource['id'], {}).get(actor.id)
    return max(0, math.ceil(expiry - 5 - _minute(world))) if expiry is not None else None


def clear_manual_turns(world, player_id):
    """A reconnect or character switch must not revive an old session's turn."""
    turns = getattr(world, '_manual_resource_turns', {})
    for key, requests in list(turns.items()):
        requests.pop(player_id, None)
        if not requests: turns.pop(key, None)


def _manual_turn_waiting(world, rid, resource):
    turns = getattr(world, '_manual_resource_turns', {})
    key = rid + ':' + resource['id']; requests = turns.get(key, {})
    now = _minute(world)
    active = {pid: expiry for pid, expiry in requests.items()
              if expiry >= now and pid in world.entities and world.entities[pid].is_player
              and world.entities[pid].alive and world.entities[pid].location == rid}
    if active: turns[key] = active
    else: turns.pop(key, None)
    return bool(active)


def harvest(world, room, resource, actor):
    """Consume one batch after the caller's faction/shift/access checks.

    The caller transfers the authored yields. Keeping tool, season, local
    presence and timer checks here makes all three harvesting paths agree.
    """
    rid = getattr(room, 'id', room)
    if not actor.alive or actor.location != rid:
        return False
    if resource.get('tool') and resource['tool'] not in actor.inventory:
        return False
    if not available(world, rid, resource):
        return False
    if not actor.is_player and _manual_turn_waiting(world, rid, resource):
        return False
    # Validate write destinations before any mutation. A corrupt save must not
    # consume a finite batch and then fail halfway through the compatibility
    # timestamp writes, nor be silently reset to fresh stock.
    state = getattr(world, 'living_state', {})
    if not isinstance(state, dict):
        return False
    key = rid + ':' + resource['id']
    ledger, old, economy = (state.get('resource_nodes', {}),
                            state.get('nodes', {}), state.get('economy', {}))
    if not all(isinstance(part, dict) for part in (ledger, old, economy)):
        return False
    if not isinstance(ledger.get(key, {}), dict) or not isinstance(economy.get('harvest_times', {}), dict):
        return False
    from engine import living
    now = _minute(world)
    state = living.state(world)
    ledger = state.setdefault('resource_nodes', {})
    record = ledger.setdefault(key, {})
    if 'reserve_batches' in resource:
        record['extracted_batches'] = _extracted(world, key, resource['reserve_batches']) + 1
    record['last_harvest'] = now
    # Existing consumers and downgraded engines also see the latest cooldown.
    state['nodes'][key] = now
    from engine import society
    society.economy(world).setdefault('harvest_times', {})[key] = now
    getattr(world, '_manual_resource_turns', {}).pop(key, None)
    return True


def plant_conversion(world, room):
    """Called only after a real conversion to farm, never during init/restore."""
    rid = getattr(room, 'id', room)
    from engine import living
    now = _minute(world)
    for resource_id in dict.fromkeys(active_resources(world, rid)):
        resource = getattr(world, 'resources', {}).get(resource_id, {})
        visual = visual_config(resource, getattr(world, 'items', {}))
        if not visual or visual['kind'] != 'crop' or visual['cultivation'] != 'cultivated':
            continue
        ledger = living.state(world).setdefault('resource_nodes', {})
        record = ledger.setdefault(rid + ':' + resource_id, {})
        record['planted_at'] = now
