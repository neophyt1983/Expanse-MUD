"""Real material sources, local instruction, and work-based NPC practice."""
from copy import deepcopy
import unittest

from engine import knowledge,living,society
from engine.commands import CommandContext
from test_employment import fixture as employment_fixture


def fixture():
    world,worker,employer,_=employment_fixture(npc=True)
    world.metadata.update(society=True,community_requests=False)
    world.room_details['market'].pop('employment')
    world.resources={};world.encounters={};world.species={}
    return world,worker


class ProductionSupplies(unittest.TestCase):
    def test_real_work_consumes_one_batch_and_practices_only_its_maker(self):
        world,worker=fixture()
        society.produce(world)
        stock=society.shop(world,'market')[1]
        self.assertEqual((stock['stock']['vegetable'],stock['stock']['stew'],stock['gold'],worker.gold),(1,1,29,6))
        self.assertIn('stew',knowledge.known_ids(world,worker,'recipes'))
        self.assertEqual(worker.progress['task_practice_v1']['cooking']['attempts'],1)
        before=deepcopy((stock,worker.progress,worker.gold));society.produce(world)
        self.assertEqual(before,(stock,worker.progress,worker.gold))
        self.assertNotIn('task_practice_v1',world.entities['boss'].progress)

    def test_a_missing_input_blocks_output_wage_and_skill_then_real_delivery_restarts_it(self):
        world,worker=fixture();cfg=world.room_details['market']['workshop'];cfg['initial_stock']['vegetable']=0
        society.produce(world);stock=society.shop(world,'market')[1]
        self.assertEqual((stock['stock']['stew'],stock['gold'],worker.gold),(0,30,5))
        self.assertNotIn('task_practice_v1',worker.progress)
        self.assertIn('missing Vegetable',stock['shortages'][0])
        stock['stock']['vegetable']=1  # An explicit finite delivery, no restock clock.
        world.living_state['minute']+=5;society.produce(world)
        self.assertEqual((stock['stock']['vegetable'],stock['stock']['stew'],worker.gold),(0,1,6))
        self.assertFalse(stock['shortages'])

    def test_reading_tools_and_canonical_skill_are_required_for_npc_production(self):
        world,worker=fixture()
        world.items['manual']={'id':'manual','name':'Kitchen manual','read_text':'The complete local recipe.', 'knowledge':{'recipes':['stew']}}
        world.items['spoon']={'id':'spoon','name':'Spoon'}
        world.rooms['market'].items.append('manual')
        recipe=world.recipes['stew'];recipe.update(requires_reading=['manual'],tool='spoon',required_skill='cooking',required_skill_level=10)
        world.npcs['worker']['task_skills']={'cooking':20}
        for stage in ('unread','without tool','ready'):
            if stage=='without tool':knowledge.read_source(world,worker,'manual')
            if stage=='ready':worker.inventory.append('spoon')
            world.living_state['minute']+=5;society.produce(world)
            expected=1 if stage=='ready' else 0
            self.assertEqual(society.shop(world,'market')[1]['stock']['stew'],expected,stage)
        self.assertEqual(worker.progress['task_practice_v1']['cooking']['attempts'],1)

    def test_remote_resource_id_cannot_mint_local_goods_or_practice(self):
        world,worker=fixture()
        world.resources['remote']={'id':'remote','name':'Distant vegetables','yields':{'vegetable':1},'renewal_minutes':60}
        world.room_details['road']['resources']=['remote']
        before=list(worker.inventory)
        with self.assertRaises(ValueError):living.command(CommandContext(world,worker,world.rooms['market']),'remote','gather')
        self.assertEqual(worker.inventory,before)
        self.assertNotIn('task_practice_v1',worker.progress)
        world.move_entity(worker.id,'road',forced=True)
        text=living.command(CommandContext(world,worker,world.rooms['road']),'remote','gather')
        self.assertIn('Gathered',text);self.assertEqual(worker.inventory.count('vegetable'),1)

    def test_gathering_without_required_tools_never_stocks_a_workshop(self):
        world,worker=fixture()
        world.items['hoe']={'id':'hoe','name':'Hoe'}
        world.resources['garden']={'id':'garden','name':'Garden','tool':'hoe','yields':{'vegetable':1},'renewal_minutes':60}
        world.room_details['market']['resources']=['garden']
        world.room_details['market']['workshop'].update(recipes=[],initial_stock={'vegetable':0})
        society.produce(world);stock=society.shop(world,'market')[1]
        self.assertEqual(stock['stock']['vegetable'],0)
        self.assertNotIn('task_practice_v1',worker.progress)
        worker.inventory.append('hoe');world.living_state['minute']+=5;society.produce(world)
        self.assertEqual(stock['stock']['vegetable'],1)
        self.assertTrue(worker.progress['task_practice_v1'])

    def test_art_worker_cannot_produce_another_batch_even_on_completion_tick(self):
        from engine import artworks
        from test_artworks import fixture as art_fixture,learn
        world,player,worker,patron=art_fixture();learn(world,worker)
        world.metadata['society']=True
        world.npcs['maker'].update(profession='producer',art_plan={'enabled':True,'recipes':['verse'],'patrons':[]})
        world.recipes['ordinary']={'id':'ordinary','name':'Ordinary paper work','ingredients':{'paper':1},'outputs':{'ink':1},'minutes':1,'station':'scriptorium'}
        world.room_details['studio']['workshop']={'recipes':['ordinary'],'initial_stock':{'paper':1,'ink':0},'capital':10,'interval':1}
        artworks.begin(world,worker,'verse');society.produce(world)
        stock=society.shop(world,'studio')[1]
        self.assertEqual((stock['stock']['paper'],stock['stock']['ink'],worker.gold),(1,0,20))
        living.advance(world,5)
        self.assertIsNone(artworks.active(world,worker))
        self.assertTrue(any(i.startswith('artwork_') for i in worker.inventory))
        self.assertEqual((stock['stock']['paper'],stock['stock']['ink'],worker.gold),(1,0,20))

    def test_real_timed_guild_operation_excludes_workshop_output(self):
        from engine import guild_npc
        world,worker=fixture()
        worker.inventory.append('vegetable')
        self.assertTrue(guild_npc._execute(world,worker,'cook','stew'))
        society.produce(world);stock=society.shop(world,'market')[1]
        self.assertEqual((stock['stock']['vegetable'],stock['stock']['stew'],worker.gold),(2,0,5))


if __name__=='__main__':unittest.main()
