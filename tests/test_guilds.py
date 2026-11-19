"""Authored guild services and shared finite needs use real world state."""
from copy import deepcopy
import json
import unittest

from engine import guilds, guild_npc, living, locks, quest_discovery
from engine.commands import CommandContext, build_registry
from engine.core import Entity, Room, World


def fixture():
    world = World()
    world.metadata = {'living_world': True, 'society': False, 'community_requests': False,
                      'progression': {'enabled': False}}
    world.rules = {}
    world.living_state = {'minute': 480}
    world.resources = {'wheat': {'id': 'wheat', 'name': 'Wheat', 'yields': {'grain': 2},
                                'renewal_minutes': 2, 'gather_minutes': 2}}
    world.recipes = {'flour': {'id': 'flour', 'name': 'Mill flour', 'ingredients': {'grain': 1},
                              'outputs': {'flour': 1}, 'station': 'hand', 'kind': 'crafting', 'minutes': 2}}
    world.encounters = {}
    world.species = {}
    world.items = {'grain': {'id': 'grain', 'name': 'Grain'},
                   'flour': {'id': 'flour', 'name': 'Flour'},
                   'notice': {'id': 'notice', 'name': 'Guild request notice', 'anchored_readable': True,
                              'read_text': 'Supply the guild pantry. Ask the steward about the work.',
                              'knowledge': {'quests': ['supply', 'study'], 'rooms': ['hall', 'field', 'library'], 'recipes': ['flour']}},
                   'manual': {'id': 'manual', 'name': 'Field manual', 'anchored_readable': True,
                              'read_text': 'A practical account of the local field.'}}
    world.add_room(Room('hall', 'Guild hall', '', {'north': 'field', 'east': 'library'}, items=['notice']))
    world.add_room(Room('field', 'Field', '', {'south': 'hall', 'north': 'hidden'}))
    world.add_room(Room('library', 'Library', '', {'west': 'hall'}, items=['manual']))
    world.add_room(Room('hidden', 'Unseen store', '', {'south': 'field'}, map_visibility='hidden'))
    pantry = {'id': 'pantry', 'name': 'Guild pantry', 'owner': 'steward', 'locked': False, 'contents': []}
    world.room_details = {'hall': {'id': 'hall', 'locks': [pantry], 'facilities': ['guild']},
                          'field': {'id': 'field', 'resources': ['wheat']},
                          'library': {'id': 'library', 'facilities': ['library']},
                          'hidden': {'id': 'hidden'}}
    config = {'enabled': True, 'tasks': ['farming', 'crafting'], 'rooms': ['hall'], 'join_fee': 2,
              'lessons': [{'id': 'basics', 'name': 'Farming basics', 'skill': 'farming', 'min_level': 0,
                           'max_level': 10, 'gain': 2, 'cost': 3, 'trainer': 'steward'}]}
    world.groups = {'farmers': {'id': 'farmers', 'name': 'Farmers Guild', 'guild': config},
                    'town': {'id': 'town', 'name': 'Town faction'}}
    world.npcs = {'steward': {'id': 'steward', 'name': 'Steward', 'social_profile': {'sentient': True},
                              'knowledge': {'quests': ['supply', 'study'], 'rooms': ['field', 'library']}},
                   'worker': {'id': 'worker', 'name': 'Worker', 'social_profile': {'sentient': True}},
                   'expert': {'id': 'expert', 'name': 'Expert', 'social_profile': {'sentient': True}}}
    need = {'kind': 'stock', 'room': 'hall', 'container': 'pantry', 'item': 'grain',
            'target': 3, 'batch': 2, 'recipient': 'steward', 'gold_per_unit': 2}
    world.quests = {
        'supply': {'id': 'supply', 'name': 'Pantry supply', 'description': 'Supply real grain while it is needed.',
                   'offer_room': 'hall', 'turn_in_room': 'hall', 'progress_scope': 'accepted',
                   'guild': {'id': 'farmers', 'skill': 'farming', 'difficulty': 0, 'need': need}},
        'study': {'id': 'study', 'name': 'Study the field', 'description': 'Read and ask about the field.',
                  'offer_room': 'hall', 'turn_in_room': 'hall', 'progress_scope': 'accepted',
                  'actions': {'read:manual': 1}, 'talk_to': ['expert'], 'visit_rooms': ['field'], 'reward_gold': 4,
                  'guild': {'id': 'farmers', 'skill': 'farming', 'difficulty': 0}},
    }
    player = add_person(world, 'player', True)
    worker = add_person(world, 'worker', False)
    steward = add_person(world, 'steward', False)
    steward.gold = 20
    expert = add_person(world, 'expert', False, room='library')
    return world, player, worker, steward


def add_person(world, ident, player=False, *, room='hall'):
    actor = Entity(ident, ident.title(), 50, 50, 5, 5, gold=20, is_player=player,
                   source_def=None if player else ident, location=room, group_id='town' if player else None)
    world.entities[ident] = actor
    world.rooms[room].entities.append(ident)
    return actor


def enroll(world, actor, quest='supply'):
    guilds.act(world, actor, 'farmers', 'join')
    guild_npc.read(world, actor, 'notice')
    guilds.act(world, actor, 'farmers', 'accept', offer_id=quest)


def data(world):
    return {kind: list(getattr(world, attr).values()) for kind, attr in
            [('group', 'groups'), ('npc', 'npcs'), ('class', 'classes'), ('quest', 'quests'),
             ('room', 'room_details'), ('item', 'items'), ('recipe', 'recipes'), ('resource', 'resources')]}


def quest_view(world, actor, ident='supply'):
    return next(row for group in guilds.projection(world, actor)['guilds'] for row in group['quests'] if row['id'] == ident)


class GuildServiceTests(unittest.TestCase):
    def test_existing_world_without_guilds_is_unchanged(self):
        world, player, worker, steward = fixture()
        world.groups['farmers'].pop('guild')
        before = deepcopy((world.living_state, player.progress, worker.progress))
        self.assertEqual(guilds.projection(world, player)['guilds'], [])
        self.assertFalse(guilds.step(world, worker))
        self.assertEqual(before, (world.living_state, player.progress, worker.progress))

    def test_local_projection_is_read_only_and_unread_quests_are_not_offered(self):
        world, player, worker, steward = fixture()
        before = deepcopy((world.living_state, player.progress, worker.progress, steward.progress))
        view = guilds.projection(world, player)
        self.assertEqual(view['guilds'][0]['quests'], [])
        self.assertTrue(view['guilds'][0]['join']['enabled'])
        self.assertEqual(before, (world.living_state, player.progress, worker.progress, steward.progress))
        with self.assertRaisesRegex(ValueError, 'Join'):
            guilds.act(world, player, 'farmers', 'accept', offer_id='supply')
        guilds.act(world, player, 'farmers', 'join')
        with self.assertRaisesRegex(ValueError, 'Read the local notice'):
            guilds.act(world, player, 'farmers', 'accept', offer_id='supply')
        self.assertFalse(quest_discovery.sourced(player))

    def test_both_actor_kinds_join_without_replacing_faction_and_pay_real_training_once(self):
        for actor_kind in ('player', 'worker'):
            with self.subTest(actor_kind=actor_kind):
                world, player, worker, steward = fixture()
                actor = world.entities[actor_kind]
                old_faction = actor.group_id
                guilds.act(world, actor, 'farmers', 'join')
                self.assertEqual(actor.group_id, old_faction)
                self.assertEqual(actor.gold, 18)
                self.assertEqual(world.living_state['guild_treasuries_v1']['farmers'], 2)
                with self.assertRaisesRegex(ValueError, 'Already'):
                    guilds.act(world, actor, 'farmers', 'join')
                guilds.act(world, actor, 'farmers', 'learn', offer_id='basics')
                self.assertGreater(guilds.skill(world, actor, 'farming'), 0)
                self.assertGreater(actor.progress['task_practice_v1']['farming']['xp'], 0)
                self.assertEqual((actor.gold, steward.gold), (15, 23))
                before = deepcopy((actor.progress, actor.gold, steward.gold))
                world.living_state['minute'] += 1500
                with self.assertRaisesRegex(ValueError, 'already completed'):
                    guilds.act(world, actor, 'farmers', 'learn', offer_id='basics')
                self.assertEqual(before, (actor.progress, actor.gold, steward.gold))

    def test_task_difficulty_prerequisites_and_daily_lesson_limit_do_not_use_general_level(self):
        world, player, worker, steward = fixture()
        guilds.act(world, player, 'farmers', 'join')
        guild_npc.read(world, player, 'notice')
        world.quests['supply']['guild']['difficulty'] = 20
        player.progress['advancement_v1'] = {'level': 100}
        with self.assertRaisesRegex(ValueError, 'Farming 20'):
            guilds.act(world, player, 'farmers', 'accept', offer_id='supply')
        lesson = deepcopy(world.groups['farmers']['guild']['lessons'][0])
        lesson['id'] = 'more'
        world.groups['farmers']['guild']['lessons'].append(lesson)
        guilds.act(world, player, 'farmers', 'learn', offer_id='basics')
        with self.assertRaisesRegex(ValueError, 'One guild lesson'):
            guilds.act(world, player, 'farmers', 'learn', offer_id='more')
        world.living_state['minute'] = 10
        with self.assertRaisesRegex(ValueError, 'One guild lesson'):
            guilds.act(world, player, 'farmers', 'learn', offer_id='more')

    def test_shared_need_race_caps_real_contribution_and_never_duplicates_payment(self):
        world, player, worker, steward = fixture()
        for actor in (player, worker):
            enroll(world, actor)
            actor.inventory = ['grain'] * 4
        quoted = quest_view(world, player)['revision']
        self.assertEqual(quoted, quest_view(world, worker)['revision'])
        guilds.act(world, player, 'farmers', 'complete', offer_id='supply', expected_revision=quoted)
        self.assertEqual(quest_view(world, worker)['remaining'], 1)
        before = deepcopy((worker.inventory, worker.gold, steward.gold, world.living_state))
        with self.assertRaisesRegex(ValueError, 'changed'):
            guilds.act(world, worker, 'farmers', 'complete', offer_id='supply', expected_revision=quoted)
        self.assertEqual(before, (worker.inventory, worker.gold, steward.gold, world.living_state))
        guilds.act(world, worker, 'farmers', 'complete', offer_id='supply',
                   expected_revision=quest_view(world, worker)['revision'])
        stock = locks.saved(world, 'hall', world.room_details['hall']['locks'][0])['contents']
        self.assertEqual(stock, ['grain'] * 3)
        self.assertEqual((player.inventory.count('grain'), worker.inventory.count('grain')), (2, 3))
        self.assertEqual((player.gold, worker.gold, steward.gold), (22, 20, 14))
        self.assertEqual(world.living_state[guilds.NEEDS_KEY]['supply']['delivered'], 3)
        before = deepcopy((worker.inventory, worker.gold, steward.gold, world.living_state))
        with self.assertRaises(ValueError):
            guilds.act(world, worker, 'farmers', 'complete', offer_id='supply')
        self.assertEqual(before, (worker.inventory, worker.gold, steward.gold, world.living_state))

    def test_time_never_reopens_work_but_real_consumption_reopens_same_identity(self):
        world, player, worker, steward = fixture()
        enroll(world, player)
        player.inventory = ['grain'] * 6
        guilds.act(world, player, 'farmers', 'complete', offer_id='supply')
        guilds.act(world, player, 'farmers', 'complete', offer_id='supply')
        learned = guilds.skill(world, player, 'farming')
        stable = quest_view(world, player)
        world.living_state['minute'] += 100000
        self.assertEqual(quest_view(world, player)['revision'], stable['revision'])
        self.assertEqual(quest_view(world, player)['remaining'], 0)
        with self.assertRaisesRegex(ValueError, 'already been met'):
            guilds.act(world, player, 'farmers', 'accept', offer_id='supply')
        locks.transfer(world, steward, 'pantry', 'grain', 1)
        changed = quest_view(world, player)
        self.assertEqual(changed['id'], stable['id'])
        self.assertNotEqual(changed['revision'], stable['revision'])
        self.assertEqual(changed['remaining'], 1)
        guilds.act(world, player, 'farmers', 'accept', offer_id='supply')
        guilds.act(world, player, 'farmers', 'complete', offer_id='supply')
        self.assertEqual(guilds.skill(world, player, 'farming'), learned)

    def test_payer_budget_and_physical_items_are_rechecked_before_mutation(self):
        world, player, worker, steward = fixture()
        enroll(world, player)
        player.inventory = ['grain'] * 3
        player.equipped = {'hand': 'grain'}
        steward.gold = 3
        guilds.act(world, player, 'farmers', 'complete', offer_id='supply')
        self.assertEqual(steward.gold, 1)
        self.assertEqual(player.inventory, ['grain', 'grain'])
        self.assertEqual(player.equipped, {'hand': 'grain'})
        before = deepcopy((world.living_state, player.progress, player.inventory, player.gold, steward.gold))
        with self.assertRaisesRegex(ValueError, 'cannot fund'):
            guilds.act(world, player, 'farmers', 'complete', offer_id='supply')
        self.assertEqual(before, (world.living_state, player.progress, player.inventory, player.gold, steward.gold))

    def test_classic_authored_objectives_and_rewards_are_not_completed_by_accepting(self):
        world, player, worker, steward = fixture()
        for actor in (player, worker):
            enroll(world, actor, 'study')
            gold = actor.gold
            message = guilds.act(world, actor, 'farmers', 'complete', offer_id='study')
            self.assertIn('objectives are incomplete', message)
            self.assertEqual(actor.gold, gold)
            self.assertEqual(actor.progress['quests']['study'], 'active')

    def test_saved_world_and_character_progress_retain_shared_need_and_lessons(self):
        world, player, worker, steward = fixture()
        enroll(world, worker)
        worker.inventory = ['grain'] * 3
        guilds.act(world, worker, 'farmers', 'learn', offer_id='basics')
        guilds.act(world, worker, 'farmers', 'complete', offer_id='supply')
        learned = deepcopy(worker.progress['task_practice_v1'])
        level = guilds.skill(world, worker, 'farming')
        saved = json.loads(json.dumps(living.snapshot(world)))
        restored, other, _, _ = fixture()
        living.restore(restored, saved)
        recovered = restored.entities['worker']
        self.assertTrue(guilds.member(recovered, 'farmers'))
        self.assertEqual(guilds.skill(restored, recovered, 'farming'), level)
        self.assertEqual(recovered.progress['task_practice_v1'], learned)
        self.assertEqual(quest_view(restored, recovered)['remaining'], 1)
        with self.assertRaisesRegex(ValueError, 'already completed'):
            guilds.act(restored, recovered, 'farmers', 'learn', offer_id='basics')

    def test_spoofed_actor_wrong_location_unknown_offer_and_bad_revisions_fail(self):
        world, player, worker, steward = fixture()
        enroll(world, player)
        player.inventory = ['grain']
        before = deepcopy((world.living_state, player.progress, player.inventory, player.gold))
        with self.assertRaises(ValueError):
            guilds.act(world, deepcopy(player), 'farmers', 'complete', offer_id='supply')
        for revision in (True, -1, '123', 2**48):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                guilds.act(world, player, 'farmers', 'complete', offer_id='supply', expected_revision=revision)
        with self.assertRaises(ValueError):
            guilds.act(world, player, 'farmers', 'complete', offer_id='missing')
        self.assertEqual(before, (world.living_state, player.progress, player.inventory, player.gold))
        world.move_entity(player.id, 'library')
        with self.assertRaisesRegex(ValueError, 'does not offer services here'):
            guilds.act(world, player, 'farmers', 'complete', offer_id='supply')

    def test_canonical_command_is_registered_and_listing_does_not_account_time(self):
        world, player, worker, steward = fixture()
        registry = build_registry()
        context = CommandContext(world, player, world.rooms['hall'])
        text = registry.resolve('guild').handler(context, '')
        self.assertIn('Farmers Guild', text)
        self.assertTrue(context.time_accounted)
        registry.resolve('guild').handler(context, 'join "farmers"')
        self.assertTrue(guilds.member(player, 'farmers'))

    def test_schema_validates_real_sources_stock_owner_skills_and_funding(self):
        world, player, worker, steward = fixture()
        self.assertEqual(guilds.validate(data(world)), [])
        cases = [
            lambda d: d['group'][0]['guild'].update(rooms=['nonexistent']),
            lambda d: d['group'][0]['guild']['lessons'][0].update(gain=100),
            lambda d: d['quest'][0]['guild']['need'].update(target=True),
            lambda d: d['quest'][0]['guild']['need'].update(container='missing'),
            lambda d: d['quest'][0].update(reward_gold=100),
            lambda d: d['quest'][0].update(progress_scope='lifetime'),
            lambda d: d['quest'][0]['guild'].update(skill='general_level'),
            lambda d: d['npc'][1].update(guild_plan={'enabled': True, 'guilds': ['missing']}),
        ]
        for mutate in cases:
            authored = deepcopy(data(world))
            mutate(authored)
            self.assertTrue(guilds.validate(authored))


if __name__ == '__main__':
    unittest.main()
