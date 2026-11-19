"""Timed finite artworks, individual opinions and conserved commissions."""
from copy import deepcopy
import json
import random
import unittest

from engine import artworks, artwork_npc, guild_npc, knowledge, living
from engine.commands import CommandContext, build_registry
from engine.core import Entity, Room, World


def fixture():
    world = World();world.metadata = {'living_world': True, 'society': False, 'community_requests': False}
    world.living_state = {'minute': 500};world.rules = {};world.resources = {};world.encounters = {};world.species = {}
    world.add_room(Room('studio', 'Studio', '', {'out': 'street'}, items=['manual']))
    world.add_room(Room('street', 'Street', '', {'in': 'studio'}))
    world.items = {'paper': {'id': 'paper', 'name': 'Paper'}, 'ink': {'id': 'ink', 'name': 'Ink'},
        'manual': {'id': 'manual', 'name': 'Local artistic plans', 'anchored_readable': True,
                   'read_text': 'An actual poetry exercise.', 'knowledge': {'recipes': ['verse', 'plan']}}}
    world.room_details = {'studio': {'id': 'studio', 'facilities': ['scriptorium']}, 'street': {'id': 'street'}}
    world.buildings = {'hall': {'id': 'hall', 'name': 'Surveyed hall', 'rooms': ['studio', 'street']}}
    world.recipes = {'verse': {'id': 'verse', 'name': 'Write a verse', 'ingredients': {'paper': 1, 'ink': 1},
        'outputs': {}, 'minutes': 5, 'station': 'scriptorium', 'kind': 'crafting',
        'artwork': {'kind': 'poetry', 'style': 'pastoral', 'title': 'Field Notes',
                    'text': 'Evening rain leaves rings on the garden gate.', 'difficulty': 10}},
        'plan': {'id': 'plan', 'name': 'Draw a hall plan', 'ingredients': {'paper': 1, 'ink': 1},
        'outputs': {}, 'minutes': 5, 'station': 'scriptorium', 'kind': 'crafting',
        'artwork': {'kind': 'architecture', 'style': 'measured', 'title': 'Hall plan', 'building': 'hall'}}}
    world.npcs = {'maker': {'id': 'maker', 'social_profile': {'sentient': True}, 'task_skills': {'poetry': 50}},
        'patron': {'id': 'patron', 'social_profile': {'sentient': True}, 'art_taste': {'styles': {'pastoral': 10}},
            'art_commissions': [{'id': 'verse_order', 'name': 'A verse for the reading room', 'recipe': 'verse',
                                 'price': 8, 'min_quality': 0, 'min_appreciation': 0}]}}
    for ident, player in [('player', True), ('maker', False), ('patron', False)]:
        actor = Entity(ident, ident.title(), 50, 50, 4, 4, location='studio', is_player=player,
                       source_def=None if player else ident, gold=20)
        actor.explored_rooms = ['studio'];world.entities[ident] = actor;world.rooms['studio'].entities.append(ident)
    player, maker, patron = (world.entities[key] for key in ('player', 'maker', 'patron'))
    for actor in (player, maker):actor.inventory = ['paper', 'ink'] * 4
    return world, player, maker, patron


def learn(world, actor):guild_npc.read(world, actor, 'manual')


def clock(world, minutes=5):
    world.living_state['minute'] += minutes
    artworks.advance(world, minutes)


def make(world, actor, recipe='verse'):
    artworks.begin(world, actor, recipe);clock(world);artworks.finish(world, actor, rng=random.Random(2))
    return actor.inventory[-1]


class ArtworkTests(unittest.TestCase):
    def test_direct_and_craft_art_require_real_reading_tools_skill_abilities_and_quests(self):
        for who in ('player', 'maker'):
            for via_craft in (False, True):
                with self.subTest(who=who, via_craft=via_craft):
                    world, _, _, _ = fixture();actor = world.entities[who]
                    world.items['chisel'] = {'id': 'chisel', 'name': 'Chisel'}
                    world.abilities = {'steady_hand': {'id': 'steady_hand', 'name': 'Steady hand'}}
                    world.quests = {'study': {'id': 'study', 'name': 'Studio practice'}}
                    recipe = world.recipes['verse']
                    recipe.update(requires_reading=['manual'], tool='chisel', required_skill='poetry',
                                  required_skill_level=60, required_abilities=['steady_hand'], prerequisites=['study'])
                    # An actual design grant is not proof that a required book
                    # has been read, nor a substitute for its work requirements.
                    knowledge.teach(world, actor, {'recipes': ['verse']})
                    actor.progress['skills'] = {'poetry': 0}

                    def start():
                        if via_craft:
                            return living.command(CommandContext(world, actor, world.rooms[actor.location]), 'verse', 'craft')
                        return artworks.begin(world, actor, 'verse')

                    def rejected(message):
                        before = (list(actor.inventory), actor.gold, world.living_state['minute'])
                        self.assertFalse(artworks.projection(world, actor)['projects'][0]['enabled'])
                        with self.assertRaisesRegex(ValueError, message):start()
                        self.assertEqual(before, (actor.inventory, actor.gold, world.living_state['minute']))
                        self.assertIsNone(artworks.active(world, actor))
                        self.assertNotIn('poetry', actor.progress.get('task_practice_v1', {}))

                    rejected('Read')
                    learn(world, actor)
                    rejected('Learn poetry')
                    actor.progress['skills']['poetry'] = 60
                    rejected('Bring Chisel')
                    actor.inventory.append('chisel')
                    rejected('required artistic technique')
                    actor.abilities.append('steady_hand')
                    rejected('prerequisite work')
                    actor.progress.setdefault('quests', {})['study'] = 'complete'
                    self.assertIn('Started', start())
                    self.assertEqual(actor.inventory.count('paper'), 3)
                    self.assertEqual(actor.inventory.count('ink'), 3)
                    self.assertIn('chisel', actor.inventory)
                    self.assertIsNotNone(artworks.active(world, actor))

    def test_readonly_projection_no_secret_plans_and_actual_timed_material_work(self):
        world, player, maker, patron = fixture()
        before = deepcopy((world.living_state, player.progress, patron.progress, player.inventory))
        self.assertEqual(artworks.projection(world, player)['projects'], [])
        self.assertEqual(before, (world.living_state, player.progress, patron.progress, player.inventory))
        with self.assertRaisesRegex(ValueError, 'Read an actual'):artworks.begin(world, player, 'verse')
        learn(world, player)
        before = deepcopy((world.living_state, player.progress, patron.progress, player.inventory))
        self.assertTrue(artworks.projection(world, player)['projects'])
        self.assertEqual(before, (world.living_state, player.progress, patron.progress, player.inventory))
        artworks.begin(world, player, 'verse', text='A new verse made with real ink.')
        self.assertEqual(player.inventory.count('paper'), 3)
        with self.assertRaisesRegex(ValueError, 'minutes'):artworks.finish(world, player)
        clock(world);artworks.finish(world, player, rng=random.Random(2))
        ident = player.inventory[-1];item = world.items[ident]
        self.assertEqual(item['read_text'], 'A new verse made with real ink.')
        self.assertEqual(item['artwork']['creator']['id'], player.id)
        self.assertEqual(item['publication']['edition_id'], ident + ':original')
        self.assertGreater(player.progress['task_practice_v1']['poetry']['xp'], 0)
        with self.assertRaisesRegex(ValueError, 'no artistic'):artworks.finish(world, player)

    def test_absence_sleep_pause_offline_and_clock_rewind_do_not_create_work_time(self):
        world, player, maker, patron = fixture();learn(world, maker);artworks.begin(world, maker, 'verse')
        world.move_entity(maker.id, 'street', forced=True);clock(world)
        self.assertEqual(artworks.active(world, maker)['remaining'], 5)
        world.move_entity(maker.id, 'studio', forced=True);maker.activity = 'sleeping';clock(world)
        self.assertEqual(artworks.active(world, maker)['remaining'], 5)
        maker.activity = 'awake';artworks.interrupt(world, maker, 'another task');clock(world)
        self.assertEqual(artworks.active(world, maker)['remaining'], 5)
        artworks.resume(world, maker);world.living_state['minute'] -= 50;clock(world)
        self.assertEqual(artworks.active(world, maker)['remaining'], 5)
        world.living_state['minute'] += 50;clock(world)
        self.assertEqual(artworks.active(world, maker)['remaining'], 0)
        learn(world, player);artworks.begin(world, player, 'verse');world.online_player_ids = set();clock(world)
        self.assertEqual(artworks.active(world, player)['remaining'], 5)

    def test_required_materials_equipped_units_and_real_building_survey(self):
        world, player, maker, patron = fixture();learn(world, player)
        player.inventory = ['paper', 'ink'];player.equipped = {'tool': 'ink'}
        with self.assertRaisesRegex(ValueError, 'materials'):artworks.begin(world, player, 'verse')
        player.equipped = {}
        with self.assertRaisesRegex(ValueError, 'Visit every'):artworks.begin(world, player, 'plan')
        world.move_entity(player.id, 'street', forced=True);guild_npc._observe(world, player)
        world.move_entity(player.id, 'studio', forced=True)
        old = deepcopy(world.buildings)
        ident = make(world, player, 'plan')
        self.assertEqual(world.items[ident]['artwork']['building'], 'hall')
        self.assertEqual(world.buildings, old)

    def test_actual_finite_commission_conserves_goods_money_and_cannot_repeat(self):
        for who in ('player', 'maker'):
            with self.subTest(who=who):
                world, player, maker, patron = fixture();actor = world.entities[who];learn(world, actor)
                offer = artworks.projection(world, actor)['commissions'][0]
                artworks.act(world, actor, patron.id, 'verse_order', 'accept', expected_revision=offer['revision'])
                ident = make(world, actor)
                before_gold = actor.gold + patron.gold
                reply = artworks.act(world, actor, patron.id, 'verse_order', 'deliver', work_id=ident)
                self.assertIn('accepts', reply)
                self.assertEqual((actor.gold, patron.gold), (28, 12))
                self.assertEqual(actor.gold + patron.gold, before_gold)
                self.assertNotIn(ident, actor.inventory);self.assertEqual(patron.inventory.count(ident), 1)
                clock(world, 3000)
                with self.assertRaisesRegex(ValueError, 'already fulfilled'):
                    artworks.act(world, actor, patron.id, 'verse_order', 'accept')

    def test_spoofed_remote_stale_wrong_maker_and_preexisting_work_are_rejected(self):
        world, player, maker, patron = fixture();learn(world, player);learn(world, maker)
        oldwork = make(world, player)
        offer = artworks.projection(world, player)['commissions'][0]
        patron.gold -= 1
        with self.assertRaisesRegex(ValueError, 'changed'):
            artworks.act(world, player, patron.id, 'verse_order', 'accept', expected_revision=offer['revision'])
        artworks.act(world, player, patron.id, 'verse_order', 'accept')
        with self.assertRaisesRegex(ValueError, 'after accepting'):
            artworks.act(world, player, patron.id, 'verse_order', 'deliver', work_id=oldwork)
        with self.assertRaisesRegex(ValueError, 'actual maker'):
            artworks.act(world, maker, patron.id, 'verse_order', 'deliver', work_id=oldwork)
        with self.assertRaisesRegex(ValueError, 'Enter the world'):
            artworks.act(world, deepcopy(player), patron.id, 'verse_order', 'decline')
        world.move_entity(patron.id, 'street', forced=True)
        with self.assertRaisesRegex(ValueError, 'patron here'):
            artworks.act(world, player, patron.id, 'verse_order', 'decline')

    def test_patron_opinion_uses_taste_mood_history_and_does_not_reroll_or_pay_rejection(self):
        world, player, maker, patron = fixture();learn(world, player)
        world.npcs['patron']['art_commissions'][0]['min_appreciation'] = 100
        artworks.act(world, player, patron.id, 'verse_order', 'accept');ident = make(world, player)
        before = (player.gold, patron.gold, list(player.inventory))
        reply = artworks.act(world, player, patron.id, 'verse_order', 'deliver', work_id=ident)
        self.assertIn('personal appreciation', reply);self.assertIn('declines', reply)
        key = patron.id + ':' + ident;score = artworks._state(world)['judgments'][key]['score']
        patron.progress['npc_life'] = {'mood': 100}
        world.npcs['patron']['art_taste']['styles']['pastoral'] = 30
        artworks.act(world, player, patron.id, 'verse_order', 'deliver', work_id=ident)
        self.assertEqual(artworks._state(world)['judgments'][key]['score'], score)
        self.assertEqual(before, (player.gold, patron.gold, player.inventory))
        # A distinct actual work can receive a different opinion after real context changes.
        second = make(world, player)
        newscore = artworks._judge(world, patron, player, second)['score']
        self.assertGreater(newscore, score)

    def test_save_restore_retains_unique_floor_works_creator_and_dead_unknown_attribution(self):
        world, player, maker, patron = fixture();learn(world, maker)
        ident = make(world, maker);maker.inventory.remove(ident);world.rooms['studio'].items.append(ident)
        saved = json.loads(json.dumps(living.snapshot(world)))
        restored, _, _, _ = fixture();living.restore(restored, saved)
        self.assertIn(ident, restored.items);self.assertIn(ident, restored.rooms['studio'].items)
        self.assertEqual(artworks.provenance(restored, ident)['creator_status'], 'living')
        restored.entities['maker'].hp = 0
        self.assertEqual(artworks.provenance(restored, ident)['creator_status'], 'dead')
        restored.items[ident]['artwork'].update(attribution='attributed', creator={'name': 'Unknown old poet', 'status': 'unknown'})
        self.assertIn('Attributed to', artworks.provenance(restored, ident)['attribution_label'])
        self.assertEqual(artworks.provenance(restored, ident)['creator_status'], 'unknown')

    def test_saved_player_work_requires_an_explicit_new_work_session(self):
        from engine.entity_snapshot import snapshot
        world, player, maker, patron = fixture();learn(world, player)
        artworks.begin(world, player, 'verse');clock(world, 2)
        saved_world = json.loads(json.dumps(living.snapshot(world)))
        saved_player = snapshot(player)
        restored, _, _, _ = fixture();living.restore(restored, saved_world)
        recovered = Entity(**{key: value for key, value in saved_player.items() if key in Entity.__dataclass_fields__})
        restored.entities[recovered.id] = recovered;restored.online_player_ids = {recovered.id}
        clock(restored, 20)
        self.assertEqual(artworks.active(restored, recovered)['remaining'], 3)
        self.assertTrue(artworks.active(restored, recovered)['paused'])
        self.assertFalse(any(ident.startswith('artwork_') for ident in recovered.inventory))
        artworks.resume(restored, recovered);clock(restored, 3)
        artworks.finish(restored, recovered, rng=random.Random(2))
        self.assertEqual(sum(ident.startswith('artwork_') for ident in recovered.inventory), 1)

    def test_npc_obtains_missing_materials_at_a_physically_remembered_resource(self):
        world, player, maker, patron = fixture()
        world.add_room(Room('field', 'Paper reed plot', '', {'west': 'studio'}))
        world.rooms['studio'].exits['east'] = 'field'
        world.room_details['field'] = {'id': 'field', 'resources': ['supplies']}
        world.resources['supplies'] = {'id': 'supplies', 'name': 'Workshop material salvage',
            'yields': {'paper': 1, 'ink': 1}, 'gather_minutes': 1, 'renewal_minutes': 30}
        maker.inventory = []
        world.move_entity(maker.id, 'field', forced=True);guild_npc._observe(world, maker)
        world.move_entity(maker.id, 'studio', forced=True);guild_npc._observe(world, maker)
        world.npcs['maker']['art_plan'] = {'enabled': True, 'recipes': ['verse'], 'patrons': ['patron']}
        for _ in range(24):
            clock(world, 1);artwork_npc.step(world, maker)
        self.assertEqual(artworks._state(world)['commissions']['patron:verse_order']['status'], 'complete')
        self.assertEqual(maker.progress['actions']['gather:supplies'], 1)
        self.assertEqual(maker.inventory.count('paper'), 0)
        self.assertEqual(maker.inventory.count('ink'), 0)
        self.assertEqual(len(patron.inventory), 1)

    def test_real_craft_command_begins_timed_art_and_art_command_is_registered(self):
        world, player, maker, patron = fixture();learn(world, player)
        self.assertIsNotNone(build_registry().resolve('art'))
        reply = living.command(CommandContext(world, player, world.rooms['studio']), 'verse', 'craft')
        self.assertIn('Started', reply);self.assertIsNotNone(artworks.active(world, player))
        self.assertFalse(any(ident.startswith('artwork_') for ident in player.inventory))

    def test_opted_npc_reads_actual_source_talks_accepts_makes_and_delivers_no_omniscience(self):
        world, player, maker, patron = fixture()
        self.assertFalse(artwork_npc.step(world, maker))
        world.npcs['maker']['art_plan'] = {'enabled': True, 'recipes': ['verse'], 'patrons': ['patron']}
        world.move_entity(patron.id, 'street', forced=True)
        world.rooms['studio'].items.remove('manual')
        self.assertFalse(artwork_npc.step(world, maker))
        self.assertFalse(maker.progress.get('knowledge', {}).get('recipes'))
        self.assertFalse(artworks._state(world).get('commissions'))
        world.move_entity(patron.id, 'studio', forced=True);world.rooms['studio'].items.append('manual')
        for _ in range(16):
            clock(world, 1);artwork_npc.step(world, maker)
        self.assertEqual(artworks._state(world)['commissions']['patron:verse_order']['status'], 'complete')
        self.assertEqual((maker.gold, patron.gold), (28, 12))
        self.assertTrue(maker.progress.get('quest_sources') is not None or maker.progress.get('knowledge'))

    def test_author_validation_requires_finite_materials_existing_patron_plan_and_building(self):
        world, player, maker, patron = fixture()
        data = {'recipe': list(world.recipes.values()), 'npc': list(world.npcs.values()),
                'item': list(world.items.values()), 'building': list(world.buildings.values()), 'room': list(world.room_details.values())}
        self.assertEqual(artworks.validate(data), [])
        changed = deepcopy(data);changed['recipe'][0]['ingredients'] = {}
        self.assertTrue(artworks.validate(changed))
        changed = deepcopy(data);changed['recipe'][1]['artwork']['building'] = 'imaginary'
        self.assertTrue(artworks.validate(changed))
        changed = deepcopy(data);changed['npc'][1]['art_commissions'][0]['price'] = -10
        self.assertTrue(artworks.validate(changed))


if __name__ == '__main__':unittest.main()
