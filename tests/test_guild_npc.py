"""NPC quest acquisition and work require actual sources, actions and travel."""
from copy import deepcopy
import unittest

from engine import guilds, guild_npc, living, locks, quest_discovery, quest_progress
from test_guilds import fixture, enroll


def plan(world, *, explore=True):
    world.npcs['worker']['guild_plan'] = {'enabled': True, 'guilds': ['farmers'],
                                         'learn': False, 'quests': True, 'explore': explore}


def only(world, ident):
    world.quests = {ident: world.quests[ident]}
    world.items['notice']['knowledge']['quests'] = [ident]
    world.npcs['steward']['knowledge']['quests'] = [ident]


def tick(world, worker, count=1):
    for _ in range(count):
        world.living_state['minute'] += 1
        guilds.step(world, worker)


class GuildNpcTests(unittest.TestCase):
    def test_ordinary_npc_does_not_automatically_join_or_inspect_the_quest_catalog(self):
        world, player, worker, steward = fixture()
        before = deepcopy((world.living_state, worker.progress, worker.inventory, worker.gold))
        self.assertFalse(guilds.step(world, worker))
        self.assertEqual(before, (world.living_state, worker.progress, worker.inventory, worker.gold))

    def test_unread_remote_offer_is_not_known_even_when_loaded_in_world(self):
        world, player, worker, steward = fixture()
        plan(world, explore=False)
        world.rooms['hall'].items = []
        world.move_entity(steward.id, 'library')
        tick(world, worker, 8)
        self.assertTrue(guilds.member(worker, 'farmers'))
        self.assertFalse(quest_discovery.sourced(worker))
        self.assertFalse(worker.progress.get('quests'))
        self.assertEqual(guilds.projection(world, worker)['guilds'][0]['quests'], [])
        self.assertEqual(worker.gold, 18)

    def test_actual_local_reading_and_conversation_disclose_only_their_authored_information(self):
        world, player, worker, steward = fixture()
        guilds.act(world, worker, 'farmers', 'join')
        with self.assertRaisesRegex(ValueError, 'local or carried'):
            guild_npc.read(world, worker, 'manual')
        guild_npc.read(world, worker, 'notice')
        self.assertEqual(quest_discovery.sourced(worker), {'supply', 'study'})
        self.assertEqual(worker.progress['quest_sources']['supply'], [{'kind': 'item', 'id': 'notice'}])
        self.assertNotIn('hidden', worker.progress['knowledge']['rooms'])
        guild_npc.converse(world, worker, steward.id)
        self.assertIn({'kind': 'npc', 'id': 'steward'}, worker.progress['quest_sources']['supply'])
        self.assertEqual(worker.progress['quest_talks']['steward'], 1)
        self.assertFalse(worker.progress.get('quests'))
        self.assertEqual(worker.gold, 18)

    def test_sleeping_hostile_remote_and_player_sources_do_not_become_invented_conversations(self):
        world, player, worker, steward = fixture()
        guilds.act(world, worker, 'farmers', 'join')
        for target in (player.id, worker.id, 'missing'):
            with self.assertRaises(ValueError):
                guild_npc.converse(world, worker, target)
        steward.activity = 'sleeping at home'
        with self.assertRaises(ValueError):
            guild_npc.converse(world, worker, steward.id)
        steward.activity = 'awake'
        world.move_entity(steward.id, 'library')
        with self.assertRaises(ValueError):
            guild_npc.converse(world, worker, steward.id)
        self.assertFalse(quest_discovery.sourced(worker))
        self.assertFalse(worker.progress.get('quest_talks'))

    def test_stock_request_is_completed_by_real_gathering_travel_and_finite_delivery(self):
        world, player, worker, steward = fixture()
        plan(world)
        only(world, 'supply')
        initial = worker.gold
        for _ in range(40):
            tick(world, worker)
            if worker.progress.get('quests', {}).get('supply') == 'complete':
                break
        self.assertEqual(worker.progress['quests']['supply'], 'complete')
        stock = locks.saved(world, 'hall', world.room_details['hall']['locks'][0])['contents']
        self.assertEqual(stock, ['grain'] * 3)
        self.assertEqual(worker.inventory, ['grain'])  # Two actual two-unit harvests.
        self.assertEqual(worker.progress['actions']['gather:wheat'], 2)
        self.assertEqual(worker.progress['quest_visits']['field'], 2)
        self.assertEqual(worker.location, 'hall')
        self.assertEqual(worker.gold, initial - 2 + 6)
        self.assertEqual(steward.gold, 14)
        self.assertNotIn('hidden', worker.progress['knowledge']['rooms'])

    def test_read_talk_and_visit_steps_must_happen_after_acceptance_before_classic_reward(self):
        world, player, worker, steward = fixture()
        only(world, 'study')
        plan(world)
        # Prior experiences are not retroactive credit for accepted-scope work.
        guilds.act(world, worker, 'farmers', 'join')
        guild_npc._observe(world, worker)
        guild_npc._move(world, worker, 'library')
        guild_npc.read(world, worker, 'manual')
        guild_npc.converse(world, worker, 'expert')
        guild_npc._move(world, worker, 'hall')
        guild_npc._move(world, worker, 'field')
        guild_npc._move(world, worker, 'hall')
        guild_npc.read(world, worker, 'notice')
        guilds.act(world, worker, 'farmers', 'accept', offer_id='study')
        self.assertEqual(quest_progress.count(worker, world.quests['study'], 'actions', 'read:manual'), 0)
        gold = worker.gold
        for _ in range(35):
            tick(world, worker)
            if worker.progress.get('quests', {}).get('study') == 'complete':
                break
        self.assertEqual(worker.progress['quests']['study'], 'complete')
        self.assertEqual(worker.progress['actions']['read:manual'], 2)
        self.assertEqual(worker.progress['quest_talks']['expert'], 2)
        self.assertEqual(worker.gold, gold + 4)
        tick(world, worker, 10)
        self.assertEqual(worker.gold, gold + 4)

    def test_remembered_route_respects_locked_door_and_unseen_shortcuts(self):
        world, player, worker, steward = fixture()
        only(world, 'supply')
        plan(world)
        world.room_details['hall']['locks'].append({'id': 'field_door', 'direction': 'north', 'locked': True})
        tick(world, worker, 20)
        self.assertNotIn('field', worker.explored_rooms)
        self.assertNotIn('hidden', worker.progress['knowledge']['rooms'])
        self.assertFalse(worker.inventory)
        self.assertEqual(worker.progress.get('actions', {}).get('gather:wheat', 0), 0)
        self.assertEqual(worker.gold, 18)
        locks.saved(world, 'hall', world.room_details['hall']['locks'][1])['locked'] = False
        tick(world, worker, 40)
        self.assertEqual(worker.progress['quests']['supply'], 'complete')

    def test_known_destination_does_not_supply_unobserved_edges_or_live_target_location(self):
        world, player, worker, steward = fixture()
        guild_npc._observe(world, worker)
        worker.progress['knowledge']['rooms'].append('hidden')  # A source may mention a place.
        self.assertIsNone(guild_npc.route(world, worker, 'hidden'))
        guild_npc._move(world, worker, 'library')
        self.assertEqual(worker.progress[guild_npc.KEY]['people']['expert'], 'library')
        world.move_entity('expert', 'hidden', forced=True)
        self.assertFalse(guild_npc._talk_goal(world, worker, 'expert'))
        self.assertEqual(worker.progress[guild_npc.KEY]['people']['expert'], 'library')
        self.assertFalse(worker.progress.get('quest_talks'))

    def test_known_recipe_is_really_crafted_with_consumed_ingredients_and_duration(self):
        world, player, worker, steward = fixture()
        only(world, 'supply')
        plan(world)
        spec = world.quests['supply']['guild']['need']
        spec.update(item='flour', target=2)
        world.quests['supply']['guild']['skill'] = 'crafting'
        for _ in range(50):
            tick(world, worker)
            if worker.progress.get('quests', {}).get('supply') == 'complete':
                break
        self.assertEqual(worker.progress['quests']['supply'], 'complete')
        self.assertEqual(worker.progress['actions']['craft:flour'], 2)
        self.assertEqual(worker.progress['actions']['gather:wheat'], 1)
        self.assertFalse(worker.inventory)
        self.assertEqual(locks.saved(world, 'hall', world.room_details['hall']['locks'][0])['contents'], ['flour', 'flour'])
        self.assertGreaterEqual(world.living_state['minute'], 486)

    def test_unsupported_combat_work_remains_pending_without_imaginary_rewards(self):
        world, player, worker, steward = fixture()
        only(world, 'study')
        plan(world, explore=False)
        world.quests['study'].update(actions={}, talk_to=[], visit_rooms=[], kills={'enemy': 1})
        enroll(world, worker, 'study')
        gold = worker.gold
        tick(world, worker, 12)
        self.assertEqual(worker.progress['quests']['study'], 'active')
        self.assertEqual(worker.progress.get('kills', {}).get('enemy', 0), 0)
        self.assertEqual(worker.gold, gold)
        self.assertIn('unsupported guild objective', worker.activity)

    def test_one_operation_per_minute_and_clock_rewind_cannot_repeat_work(self):
        world, player, worker, steward = fixture()
        plan(world)
        self.assertTrue(guilds.step(world, worker))
        before = deepcopy((worker.progress, worker.gold, worker.inventory))
        self.assertFalse(guilds.step(world, worker))
        world.living_state['minute'] -= 100
        self.assertFalse(guilds.step(world, worker))
        self.assertEqual(before, (worker.progress, worker.gold, worker.inventory))

    def test_real_living_tick_uses_only_the_explicit_guild_plan(self):
        world, player, worker, steward = fixture()
        plan(world)
        living.advance(world, 1)
        self.assertTrue(guilds.member(worker, 'farmers'))
        self.assertFalse(guilds.member(steward, 'farmers'))
        self.assertFalse(guilds.member(world.entities['expert'], 'farmers'))


if __name__ == '__main__':
    unittest.main()
