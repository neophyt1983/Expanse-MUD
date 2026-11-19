"""Graphical inventory theft resolves live scoped targets without inspecting them."""
from copy import deepcopy
import shlex
import unittest

from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot
from server import theft_ui


def fixture(*, player_target=False):
    world = World()
    world.add_room(Room('square', 'Square', 'A square.', {'east': 'lane'}))
    world.add_room(Room('lane', 'Lane', 'A lane.', {'west': 'square'}))
    world.npcs = {'merchant': {'id': 'merchant', 'social_profile': {'sentient': True}}}
    world.living_state = {'minute': 480}
    actor = Entity('player-1', 'Player', 50, 50, 0, 0, is_player=True)
    target = Entity('player-2' if player_target else 'merchant-1', 'Target', 50, 50, 0, 0,
                    is_player=player_target, source_def='' if player_target else 'merchant',
                    inventory=['private-item'])
    world.add_entity(actor, 'square');world.add_entity(target, 'square')
    packet = {'command': 'steal action', 'theft_ui': True, 'action': 'steal',
              'actor_id': actor.id, 'room': actor.location, 'target_id': target.id,
              'quantity': 7, 'request_id': 'theft-request-1'}
    return world, actor, target, packet


class TheftUiTests(unittest.TestCase):
    def test_scope_resolves_without_reading_inventory_or_mutating_live_state(self):
        world, actor, target, packet = fixture()
        before = deepcopy((world.living_state, snapshot(actor), snapshot(target)))
        self.assertEqual(theft_ui.resolve(world, actor, packet), 'steal merchant-1 7')
        self.assertEqual((world.living_state, snapshot(actor), snapshot(target)), before)
        # Empty, equipped-only or undefined items do not change this resolver:
        # the shared command later validates the real attempt and its result.
        target.inventory = []
        self.assertEqual(theft_ui.resolve(world, actor, packet), 'steal merchant-1 7')

    def test_player_target_needs_the_current_session_online_set(self):
        world, actor, target, packet = fixture(player_target=True)
        self.assertEqual(theft_ui.resolve(world, actor, packet, online_players={actor.id, target.id}),
                         'steal player-2 7')
        with self.assertRaises(ValueError):
            theft_ui.resolve(world, actor, packet, online_players={actor.id})

    def test_stale_actor_room_target_and_offline_membership_are_rejected(self):
        for stale in ('actor', 'room', 'target-moved', 'target-dead', 'target-removed', 'self', 'puppet'):
            with self.subTest(stale=stale):
                world, actor, target, packet = fixture()
                if stale == 'actor': packet['actor_id'] = 'another-player'
                elif stale == 'room': packet['room'] = 'lane'
                elif stale == 'target-moved': world.move_entity(target.id, 'lane')
                elif stale == 'target-dead': target.hp = 0
                elif stale == 'target-removed': world.rooms['square'].entities.remove(target.id)
                elif stale == 'self': packet['target_id'] = actor.id
                else: target.source_def = 'missing-definition'
                with self.assertRaises(ValueError): theft_ui.resolve(world, actor, packet)

    def test_non_sentient_targets_are_not_invented_as_inventory_people(self):
        world, actor, target, packet = fixture()
        world.npcs['merchant']['social_profile']['sentient'] = False
        with self.assertRaises(ValueError): theft_ui.resolve(world, actor, packet)

    def test_malformed_quantities_nonces_and_command_strings_do_not_resolve(self):
        invalid = [('quantity', value) for value in (None, 0, -1, True, 2.5, '2', 1000001)]
        invalid += [('request_id', value) for value in (None, '', '   ', 42, 'x' * 101)]
        invalid += [('command', 'steal someone-else 100'), ('theft_ui', 1),
                    ('action', 'take'), ('item_id', 'private-item'), ('item', 'private-item')]
        for key, value in invalid:
            with self.subTest(key=key, value=value):
                world, actor, _, packet = fixture();packet[key] = value
                with self.assertRaises(ValueError): theft_ui.resolve(world, actor, packet)

    def test_exact_ids_are_quoted_as_one_target_not_parsed_as_commands(self):
        world, actor, target, packet = fixture()
        old = target.id;world.entities.pop(old);world.rooms['square'].entities.remove(old)
        target.id = 'npc merchant; drop all'
        world.entities[target.id] = target;world.rooms['square'].entities.append(target.id)
        packet['target_id'] = target.id
        self.assertEqual(shlex.split(theft_ui.resolve(world, actor, packet)), ['steal', target.id, '7'])


if __name__ == '__main__':
    unittest.main()
