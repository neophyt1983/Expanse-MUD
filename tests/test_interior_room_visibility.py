"""Connected interior projections, using real visibility and access checks.

Run: python -m unittest discover -s tests -p 'test_interior_room_visibility.py' -v
"""
import unittest

from engine.core import Entity, Room, World
from engine.local_visibility import sight
from engine.mapping import compile_map, room_records
from engine.property_interiors import room_id as property_room_id
from engine.travel_window import window
from engine.visual_mapping import render_visual


def interior_world(hall_building='old-hall', chamber_building='old-chamber', *, chamber='chamber'):
    world = World()
    world.rules = {}
    world.room_details = {}
    world.living_state = {'minute': 480}
    definitions = [
        ('hall', 'Entry Hall', (0, 0, 0), {'east': chamber, 'west': 'street', 'up': 'loft'},
         'indoor', 'discovered', hall_building),
        (chamber, 'Side Chamber', (1, 0, 0), {'west': 'hall', 'east': 'secret'},
         'indoor', 'discovered', chamber_building),
        ('secret', 'Hidden Room', (2, 0, 0), {'west': chamber},
         'indoor', 'hidden', chamber_building),
        ('loft', 'Upper Floor', (0, 0, 1), {'down': 'hall'},
         'indoor', 'discovered', hall_building),
        ('street', 'Public Street', (-1, 0, 0), {'east': 'hall'},
         'road', 'discovered', None),
        ('detached', 'Separate Building', (4, 0, 0), {},
         'indoor', 'discovered', 'separate-building'),
    ]
    for rid, name, (x, y, z), exits, environment, visibility, bid in definitions:
        world.add_room(Room(rid, name, '', exits, map_x=x, map_y=y, map_z=z,
                            map_visibility=visibility))
        world.room_details[rid] = {'environment': environment}
        if bid:
            world.buildings.setdefault(bid, {'id': bid, 'name': 'Inn', 'rooms': []})['rooms'].append(rid)
    player = Entity('traveller', 'Traveller', 100, 100, 10, 10, is_player=True,
                    location='hall', explored_rooms=['hall', chamber])
    world.entities[player.id] = player
    return world, player, compile_map(room_records(world))


def projection(world, player, compiled):
    view = sight(world, player, compiled)
    return render_visual(compiled[0], compiled[1], player.location, view['rooms'],
                         visited=player.explored_rooms, local_positions=view['positions'])


def tile_ids(tiles):
    return {tile['id'] for tile in tiles}


class InteriorRoomVisibilityTests(unittest.TestCase):
    def test_real_open_rooms_remain_visible_from_either_center_with_legacy_or_missing_ids(self):
        for hall_bid, chamber_bid in [('old-hall', 'old-chamber'), ('inn', None),
                                      (None, 'inn'), (None, None), ('inn', 'inn')]:
            with self.subTest(hall=hall_bid, chamber=chamber_bid):
                world, player, compiled = interior_world(hall_bid, chamber_bid)
                contexts = []
                for center, destination, direction in [('hall', 'chamber', 'east'),
                                                        ('chamber', 'hall', 'west')]:
                    player.location = center
                    self.assertEqual(tile_ids(window(world, player, compiled, [3, 3], require_open=True)),
                                     {'hall', 'chamber'})
                    self.assertEqual(tile_ids(window(world, player, compiled, [5, 9])),
                                     {'hall', 'chamber'})
                    visual = projection(world, player, compiled)
                    self.assertEqual(tile_ids(visual['tiles']), {'hall', 'chamber'})
                    contexts.append(visual['context'])
                    self.assertEqual(window(world, player, compiled, [3, 3], destination),
                                     [(center, direction, destination)])
                self.assertEqual(contexts[0], contexts[1])

    def test_projection_never_adds_unknown_hidden_exterior_or_other_floor_rooms(self):
        world, player, compiled = interior_world()
        for center in ('hall', 'chamber'):
            player.location = center
            visual = projection(world, player, compiled)
            self.assertEqual(tile_ids(visual['tiles']), {'hall', 'chamber'})
            for name in ('Hidden Room', 'Public Street', 'Upper Floor', 'Separate Building'):
                self.assertNotIn(name, str(visual))
            # A renderer receives an authorization set, not permission to
            # discover connected rooms merely because their IDs match.
            alone = render_visual(compiled[0], compiled[1], center, {center})
            self.assertEqual(tile_ids(alone['tiles']), {center})

    def test_real_locked_door_stays_closed_from_both_sides_and_unlock_updates_immediately(self):
        world, player, compiled = interior_world()
        world.room_details['hall']['locks'] = [
            {'id': 'inner-door', 'name': 'Inner door', 'direction': 'east', 'locked': True}]
        for center, destination in [('hall', 'chamber'), ('chamber', 'hall')]:
            player.location = center
            self.assertEqual(tile_ids(window(world, player, compiled, [3, 3])), {center})
            self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {center})
            with self.assertRaisesRegex(ValueError, 'no open walking route'):
                window(world, player, compiled, [3, 3], destination)
        world.living_state['physical_locks'] = {'hall:inner-door': {'locked': False}}
        for center in ('hall', 'chamber'):
            player.location = center
            self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall', 'chamber'})

    def test_real_quest_gate_is_not_bypassed_by_building_metadata(self):
        world, player, compiled = interior_world()
        world.room_details['hall']['gates'] = {
            'east': {'world_flag': 'hall_open', 'message': 'The inner gate is closed.'}}
        # Compile as the server does so window sees the gate's detailed-check hint.
        compiled = compile_map(room_records(world))
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall'})
        with self.assertRaisesRegex(ValueError, 'no open walking route'):
            window(world, player, compiled, [3, 3], 'chamber')
        world.living_state['flags'] = {'hall_open': True}
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall', 'chamber'})

    def test_real_private_property_check_still_controls_interior_visibility(self):
        uid = 'guest-suite'
        suite = property_room_id(uid)
        world, player, compiled = interior_world(chamber=suite)
        world._property_generated_rooms = {suite}
        world.room_details[suite].update(property_unit_id=uid, unit_front='hall')
        unit = {'id': uid, 'kind': 'house', 'room': 'hall', 'owner': 'someone-else'}
        world.living_state['settlements'] = {'units': {uid: unit}}
        compiled = compile_map(room_records(world))
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall'})
        self.assertEqual(tile_ids(window(world, player, compiled, [3, 3])), {'hall'})
        with self.assertRaisesRegex(ValueError, 'no open walking route'):
            window(world, player, compiled, [3, 3], suite)
        unit['owner'] = player.id
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall', suite})

    def test_shifted_doorway_does_not_become_an_invented_adjacent_floor_tile(self):
        world, player, compiled = interior_world()
        world.rooms['chamber'].map_x = 3
        compiled = compile_map(room_records(world))
        self.assertEqual(tile_ids(window(world, player, compiled, [5, 9])), {'hall'})
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall'})
        with self.assertRaisesRegex(ValueError, 'no open walking route'):
            window(world, player, compiled, [5, 9], 'chamber')

    def test_real_corner_keeps_terrain_reachable_without_revealing_live_rooms_through_walls(self):
        world, player, compiled = interior_world('inn', 'inn')
        world.rooms['chamber'].exits['south'] = 'pantry'
        world.add_room(Room('pantry', 'Pantry', '', {'north': 'chamber'},
                            map_x=1, map_y=1, map_z=0))
        world.room_details['pantry'] = {'environment': 'indoor'}
        world.buildings['inn']['rooms'].append('pantry')
        compiled = compile_map(room_records(world))
        self.assertIn('pantry', tile_ids(window(world, player, compiled, [5, 9])))
        self.assertNotIn('pantry', tile_ids(projection(world, player, compiled)['tiles']))
        player.location = 'chamber'
        self.assertIn('pantry', tile_ids(projection(world, player, compiled)['tiles']))

    def test_existing_cave_context_boundaries_are_unchanged(self):
        world, player, compiled = interior_world()
        for rid in ('hall', 'chamber'):
            world.room_details[rid]['environment'] = 'cave'
        compiled = compile_map(room_records(world))
        self.assertEqual(tile_ids(window(world, player, compiled, [3, 3])), {'hall'})
        self.assertEqual(tile_ids(projection(world, player, compiled)['tiles']), {'hall'})


if __name__ == '__main__':
    unittest.main()
