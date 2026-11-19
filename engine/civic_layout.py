"""Repair the artificial civic map layers in older Wild Lands world files.

Those releases put zoos, courts, stations, prisons and bases on layers 50–158
to avoid surveyed-cell collisions. They are ordinary street buildings: their
actual front doors lead to the town below, not to another world or a sky city.
Only this identified legacy content is repaired. Room IDs, doors, locks,
occupants, possessions and saves are retained; genuine storeys still stack.
"""
from collections import deque
from copy import deepcopy


def repair(world):
    if getattr(world, '_civic_layout_repaired', False):
        return getattr(world, '_civic_layout_report', [])
    world._civic_layout_repaired = True
    report = world._civic_layout_report = []
    if not str(world.metadata.get('name', '')).startswith('Expanse Wild Lands'):
        return report
    rooms, details = world.rooms, world.room_details
    plans = []

    def add(ident, members, anchor, *, logical_floors=False, building=None):
        if anchor not in rooms or not members or any(r not in rooms for r in members):
            return
        entrance = rooms[anchor]
        street = entrance.exits.get('out')
        if street not in rooms or street in members or entrance.map_z is None or entrance.map_z < 50:
            return
        public = rooms[street]
        from engine.visual_mapping import room_style
        if public.map_z is None or abs(public.map_z) > 10 or room_style(details[street])[0] != 'outdoors':
            return
        if any(any(type(getattr(rooms[r], k)) is not int for k in ('map_x','map_y','map_z')) for r in members):
            return
        levels = {r: public.map_z + rooms[r].map_z - entrance.map_z for r in members}
        if logical_floors:
            # The old jail record was left on level 84 in every city. Recover
            # floors from actual internal stairs; a named office door is level.
            edges = {r: [] for r in members}
            for rid in members:
                for direction, target in rooms[rid].exits.items():
                    if target in edges:
                        delta = 1 if direction == 'up' else -1 if direction == 'down' else 0
                        edges[rid].append((target, delta)); edges[target].append((rid, -delta))
            levels = {anchor: public.map_z}; queue = deque([anchor])
            while queue:
                for target, delta in edges[queue[0]]:
                    level = levels[queue[0]] + delta
                    if target in levels and levels[target] != level:
                        return  # An ambiguous authored plan needs an editor, not a guess.
                    if target not in levels:
                        levels[target] = level; queue.append(target)
                queue.popleft()
            if set(levels) != set(members):
                return
        points = {(rooms[r].map_x, rooms[r].map_y, levels[r]) for r in members}
        if len(points) != len(members):
            return
        plans.append((ident, members, anchor, street, levels, building))

    for bid, building in sorted(world.buildings.items()):
        if bid.startswith('civic_') and bid.endswith(('_police_building', '_prison_building', '_military_building')):
            add(bid, list(dict.fromkeys(building.get('rooms', []))), building.get('location'),
                logical_floors=True, building=building)
    for rid in sorted(rooms):
        if rid.startswith('rg_') and rid.endswith('_court'):
            add(rid, [rid], rid)
        if rid.startswith('rg_') and rid.endswith('_zoo'):
            add(rid, [r for r in rooms if r == rid or r.startswith(rid+'_')], rid)
    moving = {r for _, members, *_ in plans for r in members}
    occupied = {(r.map_x, r.map_y, r.map_z) for rid, r in rooms.items() if rid not in moving}
    for ident, members, anchor, street, levels, building in plans:
        # Prefer the nearest genuinely vacant surveyed cells. Move the whole
        # plan, including its open courtyards, without filling an L-shaped gap.
        shift = None
        for radius in range(129):
            offsets = [(0,0)] if not radius else sorted(
                {(x,y) for x in range(-radius,radius+1) for y in (-radius,radius)} |
                {(x,y) for y in range(1-radius,radius) for x in (-radius,radius)},
                key=lambda p: (abs(p[0])+abs(p[1]), p[1], p[0]))
            for dx,dy in offsets:
                if all((rooms[r].map_x+dx, rooms[r].map_y+dy, levels[r]) not in occupied for r in members):
                    shift = dx,dy; break
            if shift is not None:
                break
        if shift is None:
            report.append({'plan':ident,'error':'No vacant surveyed footprint within 128 tiles.'})
            occupied.update((rooms[r].map_x,rooms[r].map_y,rooms[r].map_z) for r in members)
            continue
        dx,dy = shift
        for rid in members:
            room = rooms[rid]; before = (room.map_x,room.map_y,room.map_z)
            room.map_x += dx; room.map_y += dy; room.map_z = levels[rid]
            after = room.map_x,room.map_y,room.map_z
            details[rid].update(map_x=after[0],map_y=after[1],map_z=after[2])
            details[rid]['street_level']=rooms[street].map_z
            for field in ('planet','world_region','press_locality'):
                if field not in details[rid] and field in details[street]:
                    details[rid][field]=deepcopy(details[street][field])
            details[rid].pop('tile_position', None)
            occupied.add(after)
            report.append({'plan':ident,'room':rid,'before':list(before),'after':list(after),'street':street})
        if building is not None:
            building['street_level'] = rooms[street].map_z
    if report:
        for key in ('_compiled_map','_travel_index','_ground_lots','_country_surveys','_tile_survey_ready','_tile_survey_used'):
            world.__dict__.pop(key, None)
    return report
