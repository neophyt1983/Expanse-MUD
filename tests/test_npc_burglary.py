"""Opt-in NPC plans use actual local inventory and the shared theft actions."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from engine import living, locks, npc_burglary, worldtime
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot


def fixture(*, kind='actor', player_victim=False, enabled=True, quantity=6):
    world = World()
    world.metadata = {'living_world': True, 'society': True}
    world.rules = {'regional_gameplay': {'enabled': True}}
    world.living_state = {'minute': 480}
    for rid, name, exits in [('market', 'Market', {'west': 'lane'}),
                             ('lane', 'Lane', {'east': 'market'})]:
        world.add_room(Room(rid, name, 'A real room.', exits))
    world.items = {'bread': {'id': 'bread', 'name': 'Bread'},
                   'notice': {'id': 'notice', 'name': 'Fixed notice', 'anchored_readable': True}}
    container = {'id': 'pantry', 'name': 'Pantry', 'locked': False,
                 'owner': 'merchant', 'contents': ['bread'] * 12}
    world.room_details = {'market': {'locks': [container]}, 'lane': {}}
    target = {'room': 'market', 'kind': kind, 'item': 'bread', 'quantity': quantity}
    if kind == 'container':
        target['id'] = 'pantry'
    elif player_victim:
        target['entity'] = 'player-target'
    else:
        target['npc'] = 'merchant'
    world.npcs = {
        'burglar': {'id': 'burglar', 'name': 'Authored Burglar', 'burglary': 0,
                    'spawn_room': 'market', 'social_profile': {'sentient': True},
                    'burglary_plan': {'enabled': enabled, 'targets': [target]}},
        'merchant': {'id': 'merchant', 'name': 'Merchant', 'social_profile': {'sentient': True}}}
    actor = Entity('burglar-1', 'Authored Burglar', 50, 50, 0, 0, source_def='burglar')
    victim = Entity('player-target' if player_victim else 'merchant-1', 'Local Merchant',
                    50, 50, 0, 0, source_def='' if player_victim else 'merchant',
                    inventory=['bread'] * 12, is_player=player_victim)
    world.add_entity(actor, 'market')
    world.add_entity(victim, 'market')
    if player_victim:
        victim.progress['player_rest'] = {'state': 'active', 'kind': 'sleeping'}
    else:
        victim.activity = 'sleeping'
    return world, actor, victim, container


class NpcBurglaryTests(unittest.TestCase):
    def test_skill_alone_does_not_opt_in_an_ordinary_resident(self):
        world, actor, victim, _ = fixture(enabled=False)
        world.npcs['burglar']['burglary'] = 100
        actor.progress['skills'] = {'burglary': 100}
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        world.npcs['burglar'].pop('burglary_plan')
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertNotIn(npc_burglary.KEY, actor.progress)
        self.assertEqual(actor.inventory, [])
        self.assertEqual(victim.inventory, ['bread'] * 12)

    def test_real_source_target_loses_exactly_the_quality_limited_amount(self):
        world, actor, victim, _ = fixture(quantity=9)
        world.npcs['burglar']['burglary'] = 100
        actor.progress['skills'] = {'burglary': 0}
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(actor.inventory, ['bread'])
        self.assertEqual(victim.inventory, ['bread'] * 11)
        self.assertEqual((actor.location, victim.location), ('market', 'market'))
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(victim.inventory, ['bread'] * 11)

    def test_requested_amount_is_a_ceiling_when_only_a_few_real_items_remain(self):
        world, actor, victim, _ = fixture(quantity=20)
        victim.inventory = ['bread', 'bread']
        actor.progress['skills'] = {'burglary': 100}
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(actor.inventory, ['bread', 'bread'])
        self.assertEqual(victim.inventory, [])

    def test_actor_plan_uses_authoritative_online_ids_for_player_victims(self):
        for online in ((), ('player-target',)):
            with self.subTest(online=online):
                world, actor, victim, _ = fixture(player_victim=True)
                npc_burglary.step(world, actor, online_players=online, rng=lambda: 0)
                expected = 1 if online else 0
                self.assertEqual(len(actor.inventory), expected)
                self.assertEqual(len(victim.inventory), 12 - expected)

    def test_living_tick_runs_only_the_authored_plan_with_current_online_players(self):
        world, actor, victim, _ = fixture(player_victim=True)
        world.online_player_ids = {victim.id}
        with patch('engine.burglary.random.random', return_value=0):
            living.advance(world, 1)
        self.assertEqual(actor.inventory, ['bread'])
        self.assertEqual(len(victim.inventory), 11)
        with patch('engine.burglary.random.random', return_value=0):
            living.advance(world, 10)
        self.assertEqual(actor.inventory, ['bread'])
        self.assertEqual(len(victim.inventory), 11)

    def test_an_explicit_plan_runs_for_existing_regional_npcs_without_generic_movement(self):
        for flag, value in (('district_resident', True), ('expedition_role', 'resident')):
            with self.subTest(flag=flag):
                world, actor, victim, _ = fixture()
                world.npcs['burglar'].update({flag: value, 'patrol_route': ['market', 'lane']})
                with patch('engine.burglary.random.random', return_value=0):
                    living.advance(world, 1)
                    living.advance(world, 1)
                self.assertEqual(actor.inventory, ['bread'])
                self.assertEqual(len(victim.inventory), 11)
                self.assertEqual(actor.location, 'market')

    def test_actor_source_is_exact_local_and_unique_without_name_guessing(self):
        world, actor, victim, _ = fixture()
        other = Entity('merchant-2', 'Second Merchant', 50, 50, 0, 0,
                       source_def='merchant', inventory=['bread'] * 4)
        world.add_entity(other, 'market')
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertNotIn(npc_burglary.KEY, actor.progress)
        world.move_entity(other.id, 'lane')
        target = world.npcs['burglar']['burglary_plan']['targets'][0]
        target.pop('npc'); target['entity'] = victim.name
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        target['entity'] = victim.id
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(len(victim.inventory), 11)
        self.assertEqual(other.inventory, ['bread'] * 4)

    def test_target_departure_and_hidden_rooms_never_trigger_remote_theft(self):
        world, actor, victim, _ = fixture()
        victim.activity = 'awake'
        self.assertTrue(world.move_entity(victim.id, 'lane'))
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        world.npcs['burglar']['burglary_plan']['targets'][0]['room'] = 'lane'
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(actor.location, 'market')
        self.assertEqual(victim.inventory, ['bread'] * 12)

    def test_a_container_plan_uses_the_real_fixture_and_finite_contents(self):
        world, actor, victim, container = fixture(kind='container', quantity=20)
        container['contents'] = ['bread', 'bread']
        actor.progress['skills'] = {'burglary': 100}
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(locks.saved(world, 'market', container)['contents'], [])
        self.assertEqual(actor.inventory, ['bread', 'bread'])
        self.assertEqual(victim.inventory, ['bread'] * 12)
        self.assertEqual(container['contents'], ['bread', 'bread'])

    def test_locked_or_stale_inventory_targets_consume_one_budget_without_retrying(self):
        for kind in ('actor', 'container'):
            with self.subTest(kind=kind):
                world, actor, victim, container = fixture(kind=kind)
                if kind == 'container':
                    container['locked'] = True
                else:
                    victim.inventory = []
                self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
                if kind == 'container':
                    locks.saved(world, 'market', container)['locked'] = False
                else:
                    victim.inventory = ['bread'] * 12
                world.living_state['minute'] += 60
                self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
                self.assertEqual(actor.inventory, [])

    def test_cooldown_survives_saved_progress_and_clock_rewind_without_catchup(self):
        world, actor, victim, _ = fixture()
        npc_burglary.step(world, actor, rng=lambda: 0)
        saved = deepcopy(snapshot(actor)['progress'])
        actor.progress = saved
        world.living_state['minute'] = 400
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        world.living_state['minute'] = 40 * worldtime.MINUTES_PER_DAY + 480
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(len(actor.inventory), 2)
        self.assertEqual(len(victim.inventory), 10)
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))

    def test_a_failed_roll_consumes_the_day_without_loot_or_an_invented_witness(self):
        world, actor, victim, _ = fixture()
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: .999999))
        self.assertEqual(actor.inventory, [])
        self.assertEqual(victim.inventory, ['bread'] * 12)
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(actor.progress['burglary_attempt_v1']['count'], 1)
        self.assertFalse(getattr(world, 'runtime_notifications', []))

    def test_each_daily_attempt_uses_only_the_witnesses_actually_here_now(self):
        world, actor, victim, _ = fixture()
        world.room_details['market']['laws'] = {'enabled': True, 'authority': 'watch'}
        world.npcs['visitor'] = {'id': 'visitor', 'social_profile': {'sentient': True}}
        witness = Entity('visitor-1', 'Visitor', 50, 50, 0, 0, source_def='visitor')
        world.add_entity(witness, 'market')
        world.move_entity(witness.id, 'lane')
        npc_burglary.step(world, actor, rng=lambda: 0)
        self.assertFalse(world.living_state.get('mortality', {}).get('wanted', {}))
        world.move_entity(witness.id, 'market')
        world.living_state['minute'] += worldtime.MINUTES_PER_DAY
        npc_burglary.step(world, actor, rng=lambda: 0)
        evidence = world.living_state['mortality']['wanted'][actor.id]['evidence'][-1]
        self.assertEqual(evidence['witnesses'], [witness.id])
        self.assertEqual(evidence['room'], 'market')
        self.assertEqual(evidence['victim'], victim.id)

    def test_asleep_dead_restrained_confined_and_interacting_npcs_do_not_attempt(self):
        for blocked in ('sleep', 'dead', 'restrained', 'custody', 'attention', 'companion'):
            with self.subTest(blocked=blocked):
                world, actor, victim, _ = fixture()
                if blocked == 'sleep': actor.activity = 'sleeping'
                elif blocked == 'dead': actor.hp = 0
                elif blocked == 'restrained': actor.progress['restrained_until'] = 600
                elif blocked == 'custody':
                    world.living_state['city_justice_v1'] = {'cases': {actor.id: {'status': 'awaiting_hearing'}}}
                elif blocked == 'attention':
                    from engine import npc_attention
                    npc_attention.begin(world, actor)
                else: actor.progress['companion_owner'] = 'owner'
                self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
                self.assertNotIn(npc_burglary.KEY, actor.progress)
                self.assertEqual(victim.inventory, ['bread'] * 12)

    def test_existing_schedule_cannot_reach_a_target_through_a_locked_door(self):
        world, actor, victim, _ = fixture()
        world.move_entity(actor.id, 'lane')
        world.npcs['burglar']['schedule'] = [{'hour': 0, 'room': 'market', 'activity': 'visiting'}]
        door = {'id': 'entry', 'direction': 'east', 'locked': True}
        world.room_details['lane']['locks'] = [door]
        locks.invalidate(world)
        living.advance(world, 1)
        self.assertFalse(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(actor.location, 'lane')
        self.assertEqual(victim.inventory, ['bread'] * 12)
        locks.saved(world, 'lane', door)['locked'] = False
        living.advance(world, 1)
        self.assertEqual(actor.location, 'market')
        self.assertTrue(npc_burglary.step(world, actor, rng=lambda: 0))
        self.assertEqual(len(victim.inventory), 11)


class NpcBurglaryValidationTests(unittest.TestCase):
    def data(self):
        world, _, _, _ = fixture()
        return {'npc': list(world.npcs.values()), 'item': list(world.items.values()),
                'room': [{'id': rid, **details} for rid, details in world.room_details.items()]}

    def test_valid_exact_actor_and_container_plans_and_absent_plans(self):
        data = self.data()
        self.assertEqual(npc_burglary.validate(data), [])
        plan = data['npc'][0]['burglary_plan']
        plan['targets'].append({'room': 'market', 'kind': 'container', 'id': 'pantry', 'item': 'bread'})
        plan['targets'].append({'room': 'market', 'kind': 'actor', 'entity': 'future-session-id', 'item': 'bread'})
        self.assertEqual(npc_burglary.validate(data), [])
        data['npc'][0].pop('burglary_plan')
        self.assertEqual(npc_burglary.validate(data), [])

    def test_invalid_plans_fail_closed_without_defaults_or_name_based_inference(self):
        mutations = [lambda p: p.update(enabled=1),
                     lambda p: p.update(targets=[]),
                     lambda p: p.update(targets=p['targets'] * 17),
                     lambda p: p['targets'][0].update(quantity=True),
                     lambda p: p['targets'][0].update(quantity=0),
                     lambda p: p['targets'][0].update(quantity=1000001),
                     lambda p: p['targets'][0].update(room='missing'),
                     lambda p: p['targets'][0].update(item='missing'),
                     lambda p: p['targets'][0].update(npc='missing'),
                     lambda p: p['targets'][0].update(entity='ambiguous'),
                     lambda p: p['targets'][0].update(name='Merchant'),
                     lambda p: p['targets'][0].update(kind='container', id='missing')]
        for mutation in mutations:
            data = self.data(); mutation(data['npc'][0]['burglary_plan'])
            self.assertTrue(npc_burglary.validate(data), data['npc'][0]['burglary_plan'])

    def test_skill_and_difficulty_validation_uses_only_explicit_task_fields(self):
        for key in ('burglary', 'observation', 'theft_difficulty'):
            for value in (True, -1, 101, 2.5, '50'):
                with self.subTest(key=key, value=value):
                    data = self.data();data['npc'][0][key] = value
                    self.assertTrue(any(key in error for error in locks.validate(data)))
                    data = self.data();data['class'] = [{'id': 'rogue', key: value}]
                    self.assertTrue(any(key in error for error in npc_burglary.validate(data)))
        data = self.data();data['npc'][0].update(burglary=0, observation=100, theft_difficulty=50)
        self.assertEqual(npc_burglary.validate(data), [])
        data['room'][0]['locks'][0]['theft_difficulty'] = False
        self.assertTrue(any('theft_difficulty' in error for error in locks.validate(data)))


if __name__ == '__main__':
    unittest.main()
