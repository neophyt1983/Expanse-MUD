import unittest
from unittest.mock import patch

from engine import living, locks, wildlife
from engine.core import Entity, Room, World


class WildlifeForageLocks(unittest.TestCase):
    def test_roamers_share_only_the_door_lookup_and_recheck_locks_next_pass(self):
        world = World()
        world.metadata['wildlife_ecology'] = True
        world.add_room(Room('yard', 'Yard', '', exits={'north': 'field'}))
        world.add_room(Room('field', 'Field', '', exits={'south': 'yard'}))
        world.room_details = {
            'yard': {'locks': [{'id': 'gate', 'direction': 'north', 'key': 'key'}]},
            'field': {'resources': ['grassland']},
        }
        world.resources = {'grassland': {'yields': {'grass': 1}}}
        world.items['grass'] = {'food_origin': 'plant'}
        world.species = {'grazer': {'id': 'grazer', 'consumption': 'herbivore',
                                    'feeding_interval': 30, 'diet': ['grass']}}
        world.npcs['grazer'] = {'social_profile': {'species': 'grazer', 'sentient': False}}
        for name in ('first', 'second', 'third'):
            creature = Entity(name, name, 2, 2, 1, 0, source_def='grazer')
            world.add_entity(creature, 'yard')
        world.entities['second'].inventory.append('key')
        with patch.object(locks, 'index', wraps=locks.index) as index:
            wildlife.advance(world)
            scans = [call for call in index.call_args_list if call.kwargs.get('cache') is False]
            self.assertEqual(1, len(scans))
        self.assertEqual(['yard', 'field', 'yard'], [e.location for e in world.entities.values()])
        world.living_state['physical_locks'] = {'yard:gate': {'locked': False}}
        living.state(world)['minute'] += 30
        wildlife.advance(world)
        self.assertTrue(all(e.location == 'field' for e in world.entities.values()))
