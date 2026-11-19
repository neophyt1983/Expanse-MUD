"""Passage choices must describe real exits from the player's current room."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine import frontiers, streets
from engine.commands import CommandContext, _cmd_go
from engine.core import Entity, Room, World
from engine.mapping import compile_map, room_records
from engine.visual_mapping import render_visual


def fixture():
    world = World()
    world.rules = {}
    world.living_state = {'minute': 480}
    world.room_details = {}
    definitions = [
        ('square', 'Dawnwatch Civic Square', 'road', (0, 0, 0),
         {'out': 'road', 'trail to the hollow hours': 'trail', 'approach east': 'front'}),
        ('road', 'Sheltered Vale Road', 'road', (-4, 0, 0), {'in': 'square'}),
        ('trail', 'The Hollow Hours Trailhead', 'outdoors', (0, 4, 0), {'back': 'square'}),
        ('front', 'Outside Dawnwatch Gilded Tankard', 'road', (1, 0, 0), {'enter building': 'hall'}),
        ('hall', 'Dawnwatch Gilded Tankard', 'inside', (1, 0, 0),
         {'step outside': 'front', 'out': 'square', 'west': 'garden', 'east': 'annex', 'archway': 'annex'}),
        ('annex', 'Side Chamber', 'inside', (2, 0, 0), {'west': 'hall'}),
        ('garden', 'Garden', 'outdoors', (0, 1, 0), {'east': 'hall'}),
    ]
    for rid, name, environment, xyz, exits in definitions:
        world.room_details[rid] = dict(id=rid, name=name, environment=environment,
                                      map_x=xyz[0], map_y=xyz[1], map_z=xyz[2], exits=exits)
        world.add_room(Room(rid, name, 'Test location.', exits=exits,
                            map_x=xyz[0], map_y=xyz[1], map_z=xyz[2]))
    world.buildings = {'inn': {'id': 'inn', 'name': 'Inn', 'rooms': ['hall', 'annex']}}
    world._compiled_map = compile_map(room_records(world))
    player = Entity('traveller', 'Traveller', 20, 20, 1, 1, is_player=True, location='hall')
    world.entities[player.id] = player
    world.rooms[player.location].entities.append(player.id)
    return world, player


def choices(world, player, visible=None):
    rows, positions, _ = world._compiled_map
    visual = render_visual(rows, positions, player.location,
                           set(visible or {player.location}))
    blocked = {di: frontiers.blocked(world, player.location, di, player)
               for di in world.rooms[player.location].exits}
    return streets.doorways(world, player, visual, blocked)


class StreetPassageTests(unittest.TestCase):
    def test_outdoor_square_routes_are_not_building_exits(self):
        world, player = fixture()
        player.location = 'square'
        actions = choices(world, player, {'square', 'front'})
        self.assertEqual({a['direction'] for a in actions},
                         {'out', 'trail to the hollow hours', 'approach east'})
        self.assertEqual({a['kind'] for a in actions}, {'passage'})

    def test_exit_keeps_distinct_outdoor_doors_and_omits_out_command_alias(self):
        world, player = fixture()
        actions = [a for a in choices(world, player) if a['kind'] == 'exit']
        self.assertEqual({a['direction'] for a in actions}, {'step outside', 'west'})
        self.assertEqual({a['label'] for a in actions},
                         {'Exit to Outside Dawnwatch Gilded Tankard', 'Exit to Garden'})
        # Each displayed choice takes the player to the location it names.
        for direction, target in [('step outside', 'front'), ('west', 'garden')]:
            with self.subTest(direction=direction):
                world, player = fixture()
                _cmd_go(CommandContext(world, player, world.rooms['hall']), direction)
                self.assertEqual(player.location, target)

    def test_hidden_generated_door_does_not_remove_other_exit(self):
        world, player = fixture()
        world.rooms['front'].map_visibility = 'hidden'
        actions = choices(world, player)
        self.assertEqual([a['direction'] for a in actions if a['kind'] == 'exit'], ['west'])
        self.assertFalse(any(a['direction'] == 'step outside' for a in actions))

    def test_out_alias_never_advertises_a_destination_the_command_will_not_use(self):
        world, player = fixture()
        world.rooms['hall'].exits['out'] = 'annex'
        world._compiled_map = compile_map(room_records(world))
        self.assertNotIn('out', {a['direction'] for a in choices(world, player)})
        _cmd_go(CommandContext(world, player, world.rooms['hall']), 'out')
        self.assertEqual(player.location, 'front')

    def test_equivalent_doorstep_choices_are_deduplicated_but_distinct_access_is_kept(self):
        world, player = fixture()
        world.rooms['hall'].exits['south'] = 'front'
        self.assertNotIn('south', {a['direction'] for a in choices(world, player)})
        world.room_details['hall']['gates'] = {'step outside': {'message': 'The main door is locked.'}}
        actions = {a['direction']: a for a in choices(world, player)}
        self.assertEqual(actions['step outside']['blocked'], 'The main door is locked.')
        self.assertEqual(actions['south']['blocked'], '')

    def test_named_passage_remains_when_its_destination_is_drawn(self):
        world, player = fixture()
        actions = choices(world, player, {'hall', 'annex'})
        self.assertIn('archway', {a['direction'] for a in actions})
        self.assertNotIn('east', {a['direction'] for a in actions})

    def test_misaligned_direction_keeps_a_passage_choice(self):
        world, player = fixture()
        world._compiled_map[1]['annex'] = (5, 0, 0)
        actions = choices(world, player, {'hall', 'annex'})
        self.assertIn('east', {a['direction'] for a in actions})

    def test_compass_door_into_interior_is_an_entry(self):
        world, player = fixture()
        player.location = 'garden'
        self.assertEqual(choices(world, player), [dict(direction='east', kind='entry',
                         label='Enter Dawnwatch Gilded Tankard', blocked='')])

    def test_locked_exit_keeps_its_reason_and_cannot_move_player(self):
        world, player = fixture()
        world.room_details['hall']['gates'] = {'west': {'message': 'The garden gate is locked.'}}
        actions = choices(world, player)
        gate = next(a for a in actions if a['direction'] == 'west')
        self.assertEqual(gate['blocked'], 'The garden gate is locked.')
        result = _cmd_go(CommandContext(world, player, world.rooms['hall']), 'west')
        self.assertEqual(result, gate['blocked'])
        self.assertEqual(player.location, 'hall')

    def test_complete_map_packets_follow_room_moves_and_front_door(self):
        from server.game_server import GameServer

        world, player = fixture()
        # A legacy annex has no building membership; the adjacent hall does.
        world.buildings['inn']['rooms'] = ['hall']
        world._compiled_map = compile_map(room_records(world))
        definitions = deepcopy(world.room_details)
        exits = {rid: dict(room.exits) for rid, room in world.rooms.items()}
        # Exercise the real packet producer and command path without starting
        # a host, loading a player save or writing a production world.
        with TemporaryDirectory() as temporary:
            world.game_dir = temporary
            server = GameServer.__new__(GameServer)
            server.world = world
            server.clients = {object(): player.id}
            server.map_markers = {}
            context = None
            revision = 0
            for direction in [None, 'east', 'west', 'east', 'west', 'step outside', 'enter building']:
                with self.subTest(direction=direction):
                    if direction:
                        _cmd_go(CommandContext(world, player, world.rooms[player.location]), direction)
                    packet = server.map_for(player.id)
                    visual = packet['visual']
                    self.assertEqual(visual['center'], player.location)
                    self.assertGreater(packet['position_revision'], revision)
                    revision = packet['position_revision']
                    if player.location in ('hall', 'annex'):
                        self.assertEqual({t['id'] for t in visual['tiles']}, {'hall', 'annex'})
                        self.assertEqual({t['id'] for t in visual['opening_tiles']}, {'hall', 'annex'})
                        if context is None:
                            context = visual['context']['id']
                        self.assertEqual(visual['context']['id'], context)
                    else:
                        self.assertEqual(player.location, 'front')
                        self.assertEqual(visual['context']['kind'], 'outdoors')
                        self.assertEqual({a['kind'] for a in visual['passages']}, {'entry'})
            self.assertEqual(list(Path(temporary).iterdir()), [])
        self.assertEqual(world.room_details, definitions)
        self.assertEqual({rid: room.exits for rid, room in world.rooms.items()}, exits)


if __name__ == '__main__':
    unittest.main()
