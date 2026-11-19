"""Personal knowledge comes from local and attributed sources, not catalogs."""
from copy import deepcopy
import json
import unittest

from engine import knowledge, knowledge_sources, publications, task_skills, town_talk
from engine.core import Entity
from tests.test_npc_backgrounds import fixture


class KnowledgeBoundaryTests(unittest.TestCase):
    def test_legacy_resident_without_background_knows_only_its_actual_baseline(self):
        world, actor = fixture()
        world.npcs['resident'].pop('background')
        self.assertEqual(knowledge.ids(world, actor, 'rooms'), {'home', 'work'})
        self.assertEqual(knowledge.ids(world, actor, 'recipes'), set())
        self.assertNotIn('remote_book', knowledge.ids(world, actor, 'items'))
        self.assertNotIn('danger', knowledge.npc_topics(world, actor))
        self.assertNotIn(knowledge_sources.KEY, actor.progress)
        self.assertEqual(knowledge.ids(world, None, 'rooms'), set(world.rooms), 'Creator has an explicit unscoped path.')

    def test_explicit_author_grants_and_saved_learning_survive_tightened_default(self):
        world, actor = fixture()
        world.npcs['resident']['knowledge'] = {'rooms': ['remote'], 'recipes': ['stew'], 'quests': ['secret']}
        knowledge.teach(world, actor, {'rooms': ['lane']})
        self.assertEqual(knowledge.ids(world, actor, 'rooms'), {'home', 'work', 'remote', 'lane'})
        self.assertEqual(knowledge.ids(world, actor, 'recipes'), {'stew'})
        self.assertIn('meal', knowledge.ids(world, actor, 'items'))
        self.assertEqual(knowledge.ids(world, actor, 'quests'), {'secret'})
        self.assertNotIn('quest_sources', actor.progress, 'Knowing an authored quest is not accepting or completing it.')

    def test_casual_remote_mentions_remain_rumor_after_repeated_reads(self):
        world, actor = fixture()
        world.rooms['remote'].name = 'Distant Dangerous Hollow'
        world.items['manual'].update(read_text='Travelers repeat a rumor about Distant Dangerous Hollow.',
            knowledge={}, publication={'work_id':'rumor-origin','edition_id':'rumor-first','author':'A local compiler',
            'genre':'Travel','kind':'nonfiction','claims':[{'id':'hollow','text':'A distant hollow is mentioned.',
                                                         'certainty':'rumor','evidence_root':'heard-at-market'}]})
        for minute in range(500, 506):
            world.living_state['minute'] = minute
            knowledge.read_source(world, actor, 'manual')
            knowledge.from_text(world, actor, world.items['manual']['read_text'], source=('item','manual'))
        self.assertNotIn('remote', knowledge.ids(world, actor, 'rooms'))
        row = knowledge_sources.view(actor, 'rooms', 'remote')
        self.assertEqual(row['familiarity'], 'studied')
        self.assertEqual(row['qualities'], ['rumor'])
        self.assertEqual(row['evidence_roots'], ['heard-at-market'])
        self.assertNotIn('remote', actor.progress.get('town_talk', {}).get('roads', {}))

    def test_recipe_names_do_not_disclose_complete_private_designs(self):
        world, actor = fixture()
        world.recipes['stew'].update(name='Secret Supper', knowledge_scope='private', location='home')
        world.items['manual'].update(read_text='I have heard of Secret Supper.', knowledge={})
        knowledge.from_text(world, actor, world.items['manual']['read_text'], source=('item','manual'))
        knowledge.teach(world, actor, {'items':['veg','meal']})
        knowledge.learn_local_recipes(world, actor)
        self.assertNotIn('stew', knowledge.ids(world, actor, 'recipes'))
        self.assertIsNotNone(knowledge_sources.view(actor,'recipes','stew'))
        world.room_details['home']['workshop'] = {'recipes':['stew']}
        knowledge.learn_local_recipes(world, actor)
        self.assertIn('stew', knowledge.ids(world, actor, 'recipes'), 'A real posted local instruction is a source.')

    def test_copies_share_roots_and_actual_reads_are_replay_safe(self):
        world, actor = fixture()
        world.items['manual']['publication'] = dict(work_id='cookery',edition_id='first',author='Ada',genre='Cookery')
        copied = deepcopy(world.items['manual']); copied.update(id='copy', name='A copied manual')
        copied['publication'].update(work_id='copied-cookery',edition_id='copy-edition',
                                    derives_from=[dict(edition_id='first',relation='copy')])
        world.items['copy'] = copied; actor.inventory.append('copy')
        knowledge.read_source(world, actor, 'manual')
        before = deepcopy(actor.progress)
        knowledge.read_source(world, actor, 'manual')
        self.assertEqual(actor.progress, before)
        world.living_state['minute'] += 1
        knowledge.read_source(world, actor, 'copy')
        row = knowledge_sources.view(actor, 'recipes', 'stew')
        self.assertEqual(row['evidence_roots'], ['cookery'])
        self.assertEqual(len(row['sources']), 2)
        self.assertEqual(actor.progress[task_skills.KEY]['reading']['attempts'], 2)
        stable = deepcopy((actor.progress,world.living_state))
        for _ in range(5):
            knowledge.ids(world,actor,'recipes');knowledge_sources.view(actor,'recipes','stew');publications.source(world,'manual')
        # ids can aggregate current possessions/home exactly once, but cannot practice or train familiarity.
        self.assertEqual(actor.progress[knowledge_sources.KEY], stable[0][knowledge_sources.KEY])
        self.assertEqual(actor.progress[task_skills.KEY], stable[0][task_skills.KEY])
        self.assertEqual(world.living_state, stable[1])

    def test_absent_book_and_sleeping_reader_do_not_learn_or_practice(self):
        world, actor = fixture()
        before = deepcopy((actor.progress,world.living_state))
        with self.assertRaises(ValueError): knowledge.read_source(world,actor,'remote_book')
        self.assertEqual((actor.progress,world.living_state),before)
        actor.activity='sleeping at home'
        with self.assertRaises(ValueError): knowledge.read_source(world,actor,'manual')
        self.assertNotIn(task_skills.KEY,actor.progress)

    def test_travel_and_shared_routes_train_from_actual_experience_only(self):
        world, actor = fixture()
        actor.location='lane'
        town_talk.travel(world,actor,'home','lane')
        self.assertIn('lane',knowledge.ids(world,actor,'rooms'))
        original=knowledge_sources.view(actor,'rooms','lane')
        self.assertEqual(original['qualities'],['observed'])
        listener=Entity('listener','Listener',20,20,2,2,source_def='resident')
        world.add_entity(listener,'lane')
        town_talk.pass_route(world,listener,[('home','east','lane')],source=actor)
        shared=knowledge_sources.view(listener,'rooms','lane')
        self.assertEqual(shared['qualities'],['sourced'])
        self.assertEqual(shared['evidence_roots'],original['evidence_roots'])
        before=deepcopy(actor.progress[knowledge_sources.KEY])
        for _ in range(5):knowledge.ids(world,actor,'rooms')
        self.assertEqual(actor.progress[knowledge_sources.KEY],before)

    def test_saved_familiarity_is_bounded_and_keeps_qualification_after_reload(self):
        world, actor = fixture()
        for index in range(knowledge_sources.MAX_TOPICS+20):
            ident='note_'+str(index);world.items[ident]={'id':ident}
            knowledge_sources.record(world,actor,{'items':[ident]},source={'kind':'item','id':ident},
                                     certainty='opinion',event_id='reading-'+str(index))
        actor.progress=json.loads(json.dumps(actor.progress))
        knowledge_sources.validate_saved(actor.progress)
        saved=actor.progress[knowledge_sources.KEY]
        self.assertEqual(len(saved['topics']),knowledge_sources.MAX_TOPICS)
        self.assertEqual(len(saved['events']),knowledge_sources.MAX_EVENTS)
        self.assertTrue(all(row['qualities']==['opinion'] for row in saved['topics'].values()))


if __name__ == '__main__':unittest.main()
