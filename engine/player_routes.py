"""Player walking: fewest legal exits, then the closest route to a straight line.

This is deliberately separate from NPC planning. Geometry only resolves equal
hop counts: it cannot invent an exit, cross a blocked corner, reveal a room or
turn a necessary detour into an unreachable greedy walk.
"""
from collections import deque

from engine import frontiers
from engine.mapping import VECTORS
from engine.visual_mapping import crosses_seam


def _shortest_graph(world, start, target, allowed, edge_allowed, blocked):
    """Keep all predecessors at the shortest depth; never expand a deeper layer."""
    rooms = world.rooms
    distance = {start: 0}
    previous = {start: []}
    queue = deque([start])
    finish = None
    while queue:
        source = queue.popleft()
        depth = distance[source]
        if finish is not None and depth >= finish:
            break
        for direction, destination in rooms[source].exits.items():
            if (destination not in rooms
                    or allowed is not None and destination not in allowed
                    or edge_allowed is not None and not edge_allowed(source, direction, destination)):
                continue
            old_depth = distance.get(destination)
            if old_depth is not None and old_depth < depth + 1:
                continue
            if blocked(source, direction, destination):
                continue
            if old_depth is None:
                distance[destination] = depth + 1
                previous[destination] = []
                queue.append(destination)
                if destination == target:
                    finish = depth + 1
            previous[destination].append((source, direction))
    if target not in distance:
        return None
    # Off-route branches cannot affect the geometry or its context fallback.
    needed = {target}
    pending = [target]
    while pending:
        for source, _ in previous[pending.pop()]:
            if source not in needed:
                needed.add(source)
                pending.append(source)
    return [(rid, previous[rid]) for rid in distance if rid in needed]


def _line_positions(graph, start, target, positions, rows):
    """A consistent local projection of the shortest routes, or no line bias.

    Ordinary edges use their authored displacement, including shared doorsteps
    and non-unit edges. Wrapped chart seams are unfolded along actual exits.
    Passing a pole reverses the local north/south axis. If equally short routes
    disagree on that unfolding, or cross map contexts/floors, no single flat
    line is meaningful.
    """
    if not positions or start not in positions or target not in positions:
        return None
    origin = positions[start]
    if len(origin) != 3 or any(type(n) is not int for n in origin):
        return None

    def context(rid):
        style = rows.get(rid, {}).get('_visual_style') if rows is not None else None
        if not style:
            return None
        return style[0], (style[2] or {}).get('id') if style[0] != 'outdoors' else None

    origin_context = context(start)
    local = {start: (0, 0, 1)}
    for rid, parents in graph:
        point = positions.get(rid)
        if (point is None or len(point) != 3 or any(type(n) is not int for n in point)
                or point[2] != origin[2] or context(rid) != origin_context):
            return None
        if rid == start:
            continue
        result = None
        for source, direction in parents:
            x, y, orientation = local[source]
            before = positions[source]
            dx, dy = point[0] - before[0], point[1] - before[1]
            bearing = direction.removeprefix('approach ')
            before_row = rows.get(source, {}) if rows is not None else {}
            after_row = rows.get(rid, {}) if rows is not None else {}
            before_planet, after_planet = before_row.get('planet') or {}, after_row.get('planet') or {}
            shared_chart = any(before_planet.get(k) and after_planet.get(k) for k in ('field', 'cell'))
            if shared_chart and any(k not in planet for planet in (before_planet, after_planet) for k in ('lon', 'lat')):
                return None
            if shared_chart and crosses_seam(before_row, after_row, bearing):
                vector = VECTORS.get(bearing)
                if vector is None or vector[2]:
                    return None
                dx, dy = vector[:2]
                # Polar seams have the same latitude and opposite longitude.
                # Longitude seams retain north/south orientation.
                if bearing in ('north', 'south'):
                    candidate = x + dx, y + orientation * dy, -orientation
                else:
                    candidate = x + dx, y + orientation * dy, orientation
            else:
                candidate = x + dx, y + orientation * dy, orientation
            if result is not None and candidate != result:
                return None
            result = candidate
        local[rid] = result
    if local[target][:2] == (0, 0):
        return None
    return local


def _choose(graph, start, target, positions, rows):
    local = _line_positions(graph, start, target, positions, rows)
    if local is not None:
        tx, ty, _ = local[target]
        length_squared = tx * tx + ty * ty
    costs = {start: 0}
    previous = {}
    for rid, parents in graph:
        if rid == start:
            continue
        # Stable room IDs and direction names resolve exact geometric ties;
        # insertion order in an authored exits object does not select the route.
        cost, source, direction = min((costs[src], src, di) for src, di in parents)
        deviation = 0
        if local is not None:
            x, y, _ = local[rid]
            cross = x * ty - y * tx
            along = x * tx + y * ty
            outside = min(along, 0) if along < 0 else max(along - length_squared, 0)
            # Exact squared distance to the segment, scaled by its length².
            # The scale is constant for every candidate; no floats are needed.
            deviation = cross * cross + outside * outside
        costs[rid] = cost + deviation
        previous[rid] = source, direction
    steps = []
    current = target
    while current != start:
        source, direction = previous[current]
        steps.append((source, direction, current))
        current = source
    return steps[::-1]


def path(world, start, target, player, *, allowed=None, positions=None, rows=None, edge_allowed=None):
    """Read-only player route over the caller's visible/known room graph.

    Physical water/corner checks first avoid checking permissions on every open
    field tile. The chosen route is then checked against live locks, gates,
    guards, property and hazards. A rejection reruns the shortest-layer search
    with those same live rules on every edge. No route or permission cache
    survives this call.
    """
    rooms = world.rooms
    if start not in rooms or target not in rooms:
        return None
    if start == target:
        return []
    details = getattr(world, 'room_details', {})
    boat = player is not None and any(world.items.get(i, {}).get('boat') for i in player.inventory)

    def physical_blocked(source, direction, destination):
        if not boat and details.get(destination, {}).get('requires_boat'):
            return True
        if direction in frontiers.DIAGONALS and details.get(source, {}).get('open_country'):
            sides = frontiers.DIAGONALS[direction]
            for first, second in (sides, sides[::-1]):
                via = rooms[source].exits.get(first)
                if (via not in rooms or rooms[via].exits.get(second) != destination
                        or not boat and details.get(via, {}).get('requires_boat')):
                    return True
        return False

    graph = _shortest_graph(world, start, target, allowed, edge_allowed, physical_blocked)
    if graph is None:
        return None
    candidate = _choose(graph, start, target, positions, rows)
    from engine import geology_impacts, locks
    hazards = geology_impacts.route_sources(world)
    lock_index = locks.index(world)
    checks = {}

    def live_blocked(source, direction, destination):
        if source not in checks:
            checks[source] = (bool(details.get(source, {}).get('gates')) or source in hazards
                              or bool(lock_index.get(source))
                              or any(details.get(r, {}).get('property_unit_id') for r in rooms[source].exits.values()))
        return frontiers.path_blocked(world, source, direction, destination, player,
                                      checks[source], lock_index, hazards, boat)

    if not any(live_blocked(*step) for step in candidate):
        return candidate
    graph = _shortest_graph(world, start, target, allowed, edge_allowed, live_blocked)
    return _choose(graph, start, target, positions, rows) if graph is not None else None
