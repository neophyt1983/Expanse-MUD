"""Real finite meals, permitted animal movement and bounded keeper behavior."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from engine import animal_life, living, locks, npc_activity, relationships, resource_nodes, taming, wildlife
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot

CLEAR = {'weather': 'clear', 'wind_kph': 0, 'controlled_growing': False,
         'temperature_c': 18, 'latitude': 35}


def fixture(*, bird=False, owned=False):
    world = World();world.metadata = {'living_world': True};world.rules = {}
    world.living_state = {'minute': 480};world.room_details = {};world.resources = {}
    for rid, exits in [('pasture', {'east': 'lane', 'north': 'barn'}),
                       ('lane', {'west': 'pasture', 'east': 'far'}),
                       ('far', {'west': 'lane'}), ('barn', {'south': 'pasture'})]:
        world.add_room(Room(rid, rid.title(), 'A real place.', exits))
        world.room_details[rid] = {'id': rid, 'environment': 'inside' if rid == 'barn' else 'road'}
    world.items = {'grass': {'id': 'grass', 'name': 'Grass', 'food_origin': 'plant'},
                   'meat': {'id': 'meat', 'name': 'Meat', 'food_origin': 'animal'},
                   'key': {'id': 'key', 'name': 'Gate key'}}
    world.species = {'grazer': {'id': 'grazer', 'category': 'bird' if bird else 'mammal',
                              'sentient': False, 'consumption': 'herbivore', 'diet': ['grass'],
                              'feeding_interval': 30, 'animal_behavior': {'awake_start': 0, 'awake_minutes': 1500, 'action_minutes': 1}}}
    definition = {'id': 'animal', 'spawn_room': 'pasture', 'tameable': True,
                  'social_profile': {'sentient': False, 'species': 'grazer'}}
    if owned:definition['livestock'] = {'owner': 'keeper', 'home': 'pasture', 'rooms': ['pasture', 'barn']}
    world.npcs = {'animal': definition, 'keeper': {'id': 'keeper', 'social_profile': {'sentient': True}}}
    animal = Entity('animal-1', 'Animal', 40, 40, 0, 0, source_def='animal')
    keeper = Entity('keeper-1', 'Keeper', 40, 40, 0, 0, source_def='keeper')
    world.add_entity(animal, 'pasture');world.add_entity(keeper, 'pasture')
    animal.progress['feeding'] = {'last_meal': 450}
    return world, animal, keeper


def step(world, actor, minutes=0):
    world.living_state['minute'] += minutes
    with patch('engine.climate.conditions', return_value=CLEAR):
        return animal_life.step(world, actor)


class AnimalLifeTests(unittest.TestCase):
    def test_real_floor_food_is_consumed_once_and_not_replayed_by_refresh_or_rewind(self):
        world, animal, _ = fixture();world.rooms['pasture'].items = ['grass', 'grass']
        before = len(world.entities)
        self.assertTrue(step(world, animal))
        self.assertEqual(world.rooms['pasture'].items, ['grass'])
        self.assertEqual(world.living_state['wildlife']['meals'], 1)
        saved = deepcopy(snapshot(animal)['progress']);animal.progress = saved
        step(world, animal);step(world, animal, -10)
        self.assertEqual(world.rooms['pasture'].items, ['grass'])
        self.assertEqual(world.living_state['wildlife']['meals'], 1)
        self.assertEqual(len(world.entities), before)
        self.assertEqual(npc_activity.activity(world, animal)['kind'], 'meal')

    def test_forage_consumes_a_shared_real_batch_and_leaves_uneaten_yields(self):
        world, animal, _ = fixture()
        resource = {'id': 'grass_patch', 'yields': {'grass': 3}, 'renewal_minutes': 60,
                    'visual': {'kind': 'crop', 'material': 'grass', 'cultivation': 'wild'}}
        world.resources[resource['id']] = resource
        world.room_details['pasture']['resources'] = [resource['id']]
        step(world, animal)
        self.assertEqual(world.rooms['pasture'].items, ['grass', 'grass'])
        self.assertEqual(animal.inventory, [])
        self.assertFalse(resource_nodes.available(world, 'pasture', resource))
        self.assertEqual(world.living_state['resource_nodes']['pasture:grass_patch']['last_harvest'], 480)

    def test_food_search_moves_only_over_real_open_visible_edges(self):
        for barrier in ('open', 'locked', 'hidden', 'gate'):
            with self.subTest(barrier=barrier):
                world, animal, _ = fixture();world.rooms['lane'].items = ['grass']
                if barrier == 'locked':world.room_details['pasture']['locks'] = [{'id': 'gate', 'direction': 'east', 'locked': True}]
                elif barrier == 'hidden':world.rooms['lane'].map_visibility = 'hidden'
                elif barrier == 'gate':world.room_details['pasture']['gates'] = {'east': {'world_flag': 'opened'}}
                step(world, animal)
                self.assertEqual(animal.location, 'lane' if barrier == 'open' else 'pasture')
                self.assertEqual(world.rooms['lane'].items, ['grass'])
                if barrier == 'open':
                    step(world, animal, 1)
                    self.assertEqual(world.rooms['lane'].items, [])

    def test_sleep_and_waking_use_the_real_clock_without_implicit_external_wake(self):
        world, animal, _ = fixture();animal.progress['feeding']['last_meal'] = 480
        world.species['grazer']['animal_behavior'].update(awake_start=600, awake_minutes=600)
        step(world, animal)
        self.assertEqual(npc_activity.activity(world, animal)['kind'], 'sleep')
        step(world, animal, 121)
        self.assertNotIn('sleeping', animal.activity)
        animal.activity = 'sleeping after a command'
        step(world, animal, 1)
        self.assertIn('sleeping', animal.activity)

    def test_shelter_is_an_actual_reachable_room_and_containment_still_applies(self):
        world, animal, _ = fixture(owned=True)
        world.room_details['barn']['animal_shelter'] = True
        with patch('engine.climate.conditions', return_value={**CLEAR, 'weather': 'rain'}):
            animal_life.step(world, animal)
        self.assertEqual(animal.location, 'barn')
        world.living_state['minute'] += 1
        with patch('engine.climate.conditions', return_value={**CLEAR, 'weather': 'rain'}):
            animal_life.step(world, animal)
        self.assertIn('sheltering', animal.activity)

    def test_owned_stock_does_not_leave_its_enclosure_for_unreachable_food(self):
        world, animal, _ = fixture(owned=True);world.rooms['lane'].items = ['grass']
        step(world, animal)
        self.assertEqual(animal.location, 'pasture')
        self.assertIn('enclosure', animal.activity)
        self.assertEqual(world.rooms['lane'].items, ['grass'])

    def test_escape_is_bounded_by_open_gate_and_persisted_daily_opportunity(self):
        world, animal, _ = fixture(owned=True)
        world.npcs['animal']['livestock']['escape_chance'] = .25
        gate = {'id': 'gate', 'direction': 'east', 'locked': True}
        world.room_details['pasture']['locks'] = [gate]
        for day in range(10):
            world.living_state['minute'] = day*1500+480;step(world, animal)
            self.assertEqual(animal.location, 'pasture')
        locks.saved(world, 'pasture', gate)['locked'] = False
        for day in range(10, 40):
            world.living_state['minute'] = day*1500+480;step(world, animal)
            if animal.location == 'lane':break
        self.assertEqual(animal.location, 'lane')
        before = deepcopy(animal.progress[animal_life.KEY])
        step(world, animal)
        self.assertEqual(animal.progress[animal_life.KEY], before)

    def test_keeper_walks_to_the_known_stray_and_leads_the_same_animal_back(self):
        world, animal, keeper = fixture(owned=True)
        world.move_entity(animal.id, 'lane')
        self.assertTrue(animal_life.owner_step(world, keeper))
        self.assertEqual((keeper.location, animal.location), ('lane', 'lane'))
        self.assertFalse(animal_life.owner_step(world, keeper))
        self.assertEqual((keeper.location, animal.location), ('lane', 'lane'))
        world.living_state['minute'] += 1
        self.assertTrue(animal_life.owner_step(world, keeper))
        self.assertEqual((keeper.location, animal.location), ('pasture', 'pasture'))
        self.assertEqual(set(world.entities), {animal.id, keeper.id})
        public = animal_life.view(world, animal)
        self.assertIn('enclosure', public['label'])
        self.assertNotIn(keeper.id, str(public))
        self.assertNotIn('owner', public)

    def test_keeper_cannot_find_a_remote_stray_or_pass_a_locked_gate(self):
        for place in ('far', 'lane'):
            world, animal, keeper = fixture(owned=True)
            world.move_entity(animal.id, place)
            if place == 'lane':
                world.room_details['pasture']['locks'] = [{'id': 'gate', 'direction': 'east', 'locked': True}]
                locks.invalidate(world)
            self.assertFalse(animal_life.owner_step(world, keeper))
            self.assertEqual(keeper.location, 'pasture')
            self.assertEqual(animal.location, place)

    def test_flightless_and_short_flight_cannot_use_a_sustained_flight_budget(self):
        for mode in ('flightless', 'short', 'sustained'):
            with self.subTest(mode=mode):
                world, animal, _ = fixture(bird=True);world.rooms['far'].items = ['grass']
                if mode != 'flightless':world.species['grazer']['flight'] = {'mode': mode, 'endurance_steps': 2 if mode == 'sustained' else 1, 'range_steps': 3 if mode == 'sustained' else 1, 'recovery_minutes': 10}
                step(world, animal)
                self.assertEqual(animal.location, 'lane' if mode == 'sustained' else 'pasture')
                if mode == 'sustained':
                    step(world, animal, 1)
                    self.assertEqual(animal.location, 'far')
                    self.assertEqual(animal.progress[animal_life.KEY]['flight_left'], 0)
                    step(world, animal, 1)  # Eat the one real meal after landing.
                    step(world, animal, 1)
                    self.assertIn('resting its wings', animal.activity)
                    step(world, animal, 10)
                    self.assertEqual(animal.progress[animal_life.KEY]['flight_left'], 2)

    def test_flight_never_crosses_walls_indoor_routes_or_hidden_edges(self):
        for barrier in ('indoor', 'locked', 'hidden'):
            world, animal, _ = fixture(bird=True)
            world.species['grazer']['flight'] = {'mode': 'sustained', 'endurance_steps': 8, 'range_steps': 3, 'recovery_minutes': 10}
            world.rooms['far'].items = ['grass']
            if barrier == 'indoor':world.room_details['lane']['environment'] = 'inside'
            elif barrier == 'locked':world.room_details['pasture']['locks'] = [{'id': 'gate', 'direction': 'east', 'locked': True}]
            else:world.rooms['lane'].map_visibility = 'hidden'
            step(world, animal)
            self.assertEqual(animal.location, 'pasture')
            self.assertEqual(animal.progress[animal_life.KEY]['flight_left'], 8)

    def test_existing_carriage_and_unclassified_fixtures_are_not_animals(self):
        world, animal, _ = fixture()
        world.npcs['town_carriage'] = {**world.npcs['animal'], 'id': 'town_carriage'}
        animal.source_def = 'town_carriage'
        self.assertFalse(step(world, animal));self.assertNotIn(animal_life.KEY, animal.progress)
        animal.source_def = 'animal';world.npcs['animal'].pop('social_profile')
        self.assertFalse(step(world, animal))

    def test_living_tick_preserves_escorted_companions_and_pinned_exhibits(self):
        world, animal, keeper = fixture()
        animal.progress['companion_owner'] = keeper.id
        world.move_entity(keeper.id, 'lane')
        with patch('engine.climate.conditions', return_value=CLEAR):living.advance(world, 1)
        self.assertEqual(animal.location, 'lane')
        animal.progress.pop('companion_owner');animal.progress['zoo_exhibit'] = {'home': 'lane'}
        world.rooms['far'].items = ['grass']
        with patch('engine.climate.conditions', return_value=CLEAR):living.advance(world, 1)
        self.assertEqual(animal.location, 'lane')
        self.assertIn('protected enclosure', animal.activity)

    def test_living_tick_visits_each_actor_once_and_handles_later_actual_spawns(self):
        world,animal,keeper=fixture();world.rooms['pasture'].items=['grass','grass']
        newborn=Entity('animal-later','Later animal',40,40,0,0,source_def='animal')
        newborn.progress['feeding']={'last_meal':450}
        def later_spawn(_):world.add_entity(newborn,'pasture')
        with patch('engine.climate.conditions',return_value=CLEAR), \
                patch('engine.market_shifts.advance',side_effect=later_spawn), \
                patch.object(animal_life,'step',wraps=animal_life.step) as calls:
            living.advance(world,1)
        visits=[call.args[1].id for call in calls.call_args_list]
        self.assertEqual(visits.count(animal.id),1)
        self.assertEqual(visits.count(keeper.id),1)
        self.assertEqual(visits.count(newborn.id),1)
        self.assertEqual(world.rooms['pasture'].items,[])
        self.assertEqual(world.living_state['wildlife']['meals'],2)

    def test_standalone_wildlife_step_and_same_id_replacement_remain_live(self):
        world,animal,_=fixture();world.rooms['pasture'].items=['grass','grass']
        with patch('engine.climate.conditions',return_value=CLEAR):wildlife.advance(world)
        self.assertEqual(world.rooms['pasture'].items,['grass'])
        replacement=Entity(animal.id,'Replacement animal',40,40,0,0,source_def='animal')
        replacement.progress['feeding']={'last_meal':450}
        world.entities[animal.id]=replacement;replacement.location='pasture'
        with patch('engine.climate.conditions',return_value=CLEAR):
            wildlife.advance(world,stepped_entities=[animal])
        self.assertEqual(world.rooms['pasture'].items,[])

    def test_livestock_taming_is_rejected_and_real_birth_retains_ownership(self):
        world, animal, keeper = fixture(owned=True)
        player = Entity('player', 'Player', 30, 30, 0, 0, is_player=True)
        world.add_entity(player, 'pasture')
        with self.assertRaisesRegex(ValueError, 'livestock keeper'):taming.requirement(world, player, animal)
        world.npcs['sx_child'] = {'id': 'sx_child'}
        world.npcs['animal']['social_profile'].update(fertile=True, family_enabled=True, autonomous=True, reproductive_role='carrier', gestation_minutes=1)
        male = Entity('male', 'Mate', 30, 30, 0, 0, source_def='animal')
        male.progress['social_profile'] = {'reproductive_role': 'contributor'}
        world.add_entity(male, 'pasture')
        relationships.breed_animals(world, animal, male)
        world.living_state['minute'] += 1
        relationships.advance(world)
        children = [e for e in world.entities.values() if e.id.startswith('child_')]
        self.assertEqual(len(children), 1)
        self.assertEqual(animal_life.livestock(world, children[0])['owner'], 'keeper')
        self.assertTrue(animal_life.config(world, children[0]))

    def test_authoring_validation_rejects_unusable_flight_and_owner_data(self):
        world, _, _ = fixture(bird=True, owned=True)
        data = {'npc': list(world.npcs.values()), 'species': list(world.species.values()), 'room': list(world.room_details.values())}
        self.assertEqual(animal_life.validate(data), [])
        world.species['grazer']['flight'] = {'mode': 'short', 'endurance_steps': 0, 'recovery_minutes': 10}
        self.assertTrue(animal_life.validate(data))
        world.species['grazer']['flight'] = {}
        world.npcs['animal']['livestock']['owner'] = 'imaginary'
        self.assertTrue(animal_life.validate(data))

    def test_wild_adults_explore_real_local_habitat_then_rest_without_replaying_time(self):
        world, animal, _ = fixture();animal.progress['feeding']['last_meal'] = 480
        cfg = world.species['grazer']['animal_behavior']
        cfg.update(explore_minutes=30, rest_minutes=10, territory_steps=1)
        step(world, animal)
        self.assertEqual(animal.location, 'pasture')
        step(world, animal, 30)
        self.assertEqual(animal.location, 'lane')
        self.assertIn('searching another part', animal.activity)
        step(world, animal, 1)
        self.assertEqual(animal.location, 'lane')
        self.assertIn('resting after exploring', animal.activity)
        animal.progress = deepcopy(snapshot(animal)['progress'])
        step(world, animal, 3000)
        self.assertEqual(animal.location, 'pasture')
        self.assertNotEqual(animal.location, 'far')
        step(world, animal, -100)
        self.assertEqual(animal.location, 'pasture')

    def test_satiated_wild_adults_also_explore_but_juveniles_and_owned_animals_stay(self):
        for kind in ('wild', 'young', 'owned'):
            with self.subTest(kind=kind):
                world, animal, _ = fixture(owned=kind == 'owned')
                world.species['grazer']['feeding_interval'] = 1000
                if kind == 'young':animal.progress['social_profile'] = {'age_years': 0}
                step(world, animal);step(world, animal, 30)
                self.assertEqual(animal.location, 'lane' if kind == 'wild' else 'pasture')
                if kind == 'wild':self.assertIn('checking its nearby habitat', animal.activity)

    def test_exploration_cannot_cross_locks_hidden_rooms_water_or_wrong_habitat(self):
        for barrier in ('locked', 'hidden', 'water', 'habitat'):
            with self.subTest(barrier=barrier):
                world, animal, _ = fixture()
                if barrier == 'locked':world.room_details['pasture']['locks'] = [{'id': 'gate', 'direction': 'east', 'locked': True}]
                elif barrier == 'hidden':world.rooms['lane'].map_visibility = 'hidden'
                elif barrier == 'water':world.room_details['lane']['requires_boat'] = True
                else:world.room_details['lane']['environment'] = 'desert'
                step(world, animal);step(world, animal, 30)
                self.assertEqual(animal.location, 'pasture')

    def test_magical_animal_keeps_its_existing_lifecycle(self):
        from engine import spell_life
        world, animal, _ = fixture();animal.progress[spell_life.KEY] = {'kind': 'summon'}
        self.assertFalse(step(world, animal))
        self.assertNotIn(animal_life.KEY, animal.progress)

    def test_reused_animal_template_uses_only_its_actual_spawners_keeper(self):
        from engine.commands import _spawn_npc_instance
        world, _, keeper = fixture()
        world.npcs['animal'].update(name='Animal',hp=40,attack=0,defense=0)
        world.npcs['other_keeper'] = {'id': 'other_keeper', 'social_profile': {'sentient': True}}
        other = Entity('keeper-2','Other keeper',40,40,0,0,source_def='other_keeper')
        world.add_entity(other,'far')
        for rid, owner in [('pasture','keeper'),('far','other_keeper')]:
            world.rooms[rid].spawners = [{'npc':'animal','livestock':{'owner':owner,'home':rid,'rooms':[rid]}}]
        first = _spawn_npc_instance(world,world.rooms['pasture'],'animal',spawner_key='pasture:0')
        second = _spawn_npc_instance(world,world.rooms['far'],'animal',spawner_key='far:0')
        self.assertEqual(animal_life.livestock(world,first)['owner'],keeper.source_def)
        self.assertEqual(animal_life.livestock(world,second)['owner'],other.source_def)
        first.spawner_key='pasture:4'
        self.assertIsNone(animal_life.livestock(world,first))
        second.source_def='another_animal'
        self.assertIsNone(animal_life.livestock(world,second))


if __name__ == '__main__':unittest.main()
