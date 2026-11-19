"""Real funded work, conserved inputs/wages and interrupted-session escrow."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from engine import employment,living,resting,society
from engine.core import Entity,Room,World
from engine.entity_snapshot import snapshot


def fixture(*,npc=False):
    world=World();world.metadata={'living_world':True,'society':False};world.rules={}
    world.living_state={'minute':480};world.deferred_rest=True
    world.add_room(Room('market','Produce Market','A real market.',{'out':'road'}))
    world.add_room(Room('road','Road','Outside.',{'in':'market'}))
    cfg={'id':'cook','title':'Kitchen batch helper','employer':'merchant','recipe':'stew','wage':3,'slots':1,'target_stock':4}
    world.room_details={'market':{'facilities':['kitchen','inn'],'employment':[cfg],
        'workshop':{'name':'Provision Counter','recipes':['stew'],'capital':30,'stock_limit':4,'interval':5,'initial_stock':{'vegetable':2,'stew':0}}},'road':{}}
    world.items={'vegetable':{'id':'vegetable','name':'Vegetable'},'stew':{'id':'stew','name':'Stew'},'keepsake':{'id':'keepsake','name':'Keepsake'}}
    world.recipes={'stew':{'id':'stew','name':'Stew','ingredients':{'vegetable':1},'outputs':{'stew':1},'kind':'cooking','station':'kitchen','minutes':5}}
    world.npcs={'merchant':{'id':'merchant','name':'Merchant','profession':'merchant','work_room':'market','social_profile':{'sentient':True}},
                'worker':{'id':'worker','name':'Worker','profession':'producer','work_room':'market','social_profile':{'sentient':True}}}
    boss=Entity('boss','Merchant',30,30,1,1,source_def='merchant')
    actor=Entity('worker-1','Worker',30,30,1,1,is_player=not npc,source_def='worker' if npc else None,inventory=['keepsake'],gold=5)
    world.add_entity(boss,'market');world.add_entity(actor,'market')
    world.online_player_ids=frozenset({actor.id} if actor.is_player else ())
    return world,actor,boss,cfg


def tick(world,minutes):
    world.living_state['minute']+=minutes
    employment.advance(world,minutes)


def begin(world,actor):
    employment.apply(world,actor,'cook');employment.work(world,actor)


class EmploymentTests(unittest.TestCase):
    def test_one_real_timed_batch_consumes_stock_and_pays_exactly_once(self):
        world,actor,_,_=fixture();begin(world,actor)
        shop=society.shop(world,'market')[1]
        self.assertEqual((shop['stock']['vegetable'],shop['gold'],actor.gold),(1,27,5))
        self.assertEqual(actor.inventory,['keepsake'])
        employment.work(world,actor)
        self.assertEqual((shop['stock']['vegetable'],shop['gold']),(1,27))
        tick(world,3)
        self.assertEqual((shop['stock']['stew'],actor.gold),(0,5))
        tick(world,2)
        self.assertEqual((shop['stock']['stew'],shop['stock']['vegetable'],shop['gold'],actor.gold),(1,1,27,8))
        self.assertEqual(actor.inventory,['keepsake'])
        self.assertEqual(living.state(world)['minute'],485)
        self.assertEqual(actor.progress['actions']['craft:stew'],1)
        self.assertEqual(actor.progress['task_practice_v1']['cooking']['attempts'],1)
        tick(world,5)
        self.assertEqual((shop['stock']['stew'],actor.gold),(1,8))

    def test_waiting_without_starting_work_never_pays_or_produces(self):
        world,actor,_,_=fixture();employment.apply(world,actor,'cook')
        tick(world,60)
        self.assertEqual(actor.gold,5)
        self.assertEqual(employment.view(world,actor)['assignment']['batch'],None)
        self.assertNotIn('economy',world.living_state)

    def test_leaving_and_returning_before_a_tick_refunds_only_once(self):
        world,actor,_,_=fixture();begin(world,actor)
        world.move_entity(actor.id,'road');world.move_entity(actor.id,'market')
        self.assertIsNone(employment.active(world,actor))
        shop=society.shop(world,'market')[1]
        self.assertEqual((shop['stock']['vegetable'],shop['gold'],actor.gold),(2,30,5))
        tick(world,5);employment.interrupt(world,actor,'replayed stop')
        self.assertEqual((shop['stock']['vegetable'],shop['stock']['stew'],shop['gold'],actor.gold),(2,0,30,5))

    def test_saved_player_batch_cannot_finish_offline_and_refund_survives_reload(self):
        for stopped in ('token','offline'):
            with self.subTest(stopped=stopped):
                world,actor,_,_=fixture();begin(world,actor)
                world.living_state=deepcopy(world.living_state);actor.progress=deepcopy(snapshot(actor)['progress'])
                if stopped=='token':actor._employment_token=None
                else:world.online_player_ids=frozenset()
                tick(world,5);tick(world,5)
                shop=society.shop(world,'market')[1]
                self.assertEqual((shop['stock']['vegetable'],shop['stock']['stew'],shop['gold'],actor.gold),(2,0,30,5))
                self.assertIn('offline time',employment.view(world,actor)['assignment']['message'])

    def test_actual_npc_uses_same_finite_transfer_and_can_continue_after_saved_state_restore(self):
        world,actor,_,_=fixture(npc=True);begin(world,actor)
        world.living_state=deepcopy(world.living_state);actor._employment_token=None
        tick(world,5)
        self.assertEqual(actor.gold,8)
        self.assertEqual(society.shop(world,'market')[1]['stock']['stew'],1)

    def test_missing_supplies_funds_demand_or_employer_blocks_before_any_escrow(self):
        for reason in ('supplies','funds','demand','employer'):
            with self.subTest(reason=reason):
                world,actor,boss,_=fixture();cfg=world.room_details['market']['workshop']
                if reason=='supplies':cfg['initial_stock']['vegetable']=0
                elif reason=='funds':cfg['capital']=2
                elif reason=='demand':cfg['initial_stock']['stew']=4
                else:world.move_entity(boss.id,'road')
                before=deepcopy((world.living_state,actor.inventory,actor.gold))
                with self.assertRaises(ValueError):employment.apply(world,actor,'cook')
                self.assertEqual((world.living_state,actor.inventory,actor.gold),before)
                self.assertFalse(employment.view(world,actor)['vacancies'][0]['can_apply'])

    def test_paid_work_cannot_bypass_real_reading_task_skill_or_carried_tool(self):
        from engine import publications
        for requirement in ('reading','skill','tool'):
            with self.subTest(requirement=requirement):
                world,actor,_,_=fixture();recipe=world.recipes['stew']
                if requirement=='reading':
                    recipe['requires_reading']=['manual']
                    world.items['manual']={'id':'manual','name':'Stew notes','type':'book','read_text':'A real source describing the recipe.'}
                    world.rooms['market'].items.append('manual')
                elif requirement=='skill':recipe.update(required_skill='cooking',required_skill_level=10)
                else:recipe['tool']='keepsake';actor.inventory=[]
                before=deepcopy((world.living_state,actor.progress,actor.inventory))
                with self.assertRaises(ValueError):employment.apply(world,actor,'cook')
                self.assertEqual((world.living_state,actor.progress,actor.inventory),before)
                if requirement=='reading':publications.record_read(world,actor,'manual')
                elif requirement=='skill':actor.progress.setdefault('skills',{})['cooking']=10
                else:actor.inventory=['keepsake']
                begin(world,actor);tick(world,5)
                self.assertEqual(actor.gold,8)

    def test_filled_slot_and_promised_output_prevent_duplicate_hiring_demand(self):
        world,actor,_,cfg=fixture();employment.apply(world,actor,'cook')
        other=Entity('other','Other',30,30,1,1,is_player=True);world.add_entity(other,'market')
        with self.assertRaisesRegex(ValueError,'filled'):employment.apply(world,other,'cook')
        cfg.update(slots=2,target_stock=1);employment.work(world,actor)
        with self.assertRaisesRegex(ValueError,'demand'):employment.apply(world,other,'cook')

    def test_damage_sleep_or_restraint_refunds_without_output(self):
        for reason in ('damage','sleep','restraint'):
            with self.subTest(reason=reason):
                world,actor,_,_=fixture();begin(world,actor)
                if reason=='damage':actor.take_damage(2,defense=0)
                elif reason=='sleep':resting.command(world,actor,'30','sleep')
                else:actor.progress['restrained_until']=600
                tick(world,5)
                shop=society.shop(world,'market')[1]
                self.assertEqual((shop['stock']['vegetable'],shop['stock']['stew'],shop['gold'],actor.gold),(2,0,30,5))

    def test_changed_recipe_or_clock_rewind_refunds_real_escrow(self):
        for reason in ('recipe','clock'):
            with self.subTest(reason=reason):
                world,actor,_,_=fixture();begin(world,actor)
                if reason=='recipe':world.recipes['stew']['outputs']['stew']=2
                else:world.living_state['minute']-=10
                tick(world,5)
                shop=society.shop(world,'market')[1]
                self.assertEqual((shop['stock']['vegetable'],shop['stock']['stew'],shop['gold']),(2,0,30))
                self.assertEqual(actor.gold,5)

    def test_real_crafting_rejection_cannot_duplicate_injected_material(self):
        world,actor,_,_=fixture();begin(world,actor)
        with patch.object(living,'command',side_effect=ValueError('Unavailable recipe.')):tick(world,5)
        self.assertEqual(actor.inventory,['keepsake'])
        self.assertEqual(society.shop(world,'market')[1]['stock']['vegetable'],2)
        self.assertIsNone(employment.active(world,actor))

    def test_unexpected_crafting_error_refunds_before_propagating(self):
        world,actor,_,_=fixture();begin(world,actor)
        with patch.object(living,'command',side_effect=RuntimeError('Broken integration.')):
            with self.assertRaises(RuntimeError):tick(world,5)
        self.assertEqual(actor.inventory,['keepsake'])
        shop=society.shop(world,'market')[1]
        self.assertEqual((shop['stock']['vegetable'],shop['stock']['stew'],shop['gold'],actor.gold),(2,0,30,5))
        tick(world,5)
        self.assertIsNone(employment.active(world,actor))

    def test_readonly_projection_does_not_initialize_clock_law_shop_or_actor_knowledge(self):
        world,actor,_,_=fixture();before=deepcopy((world.living_state,actor.progress,world.room_details))
        for _ in range(3):employment.view(world,actor)
        self.assertEqual((world.living_state,actor.progress,world.room_details),before)

    def test_command_hooks_allow_inspection_but_interrupt_real_competing_actions(self):
        from engine.commands import build_registry
        world,actor,_,_=fixture();begin(world,actor);registry=build_registry()
        resting.before_command(world,actor,'inventory',registry)
        self.assertIsNotNone(employment.active(world,actor))
        resting.before_command(world,actor,'rest status',registry)
        self.assertIsNotNone(employment.active(world,actor))
        resting.before_command(world,actor,'craft stew',registry)
        self.assertIsNone(employment.active(world,actor))
        self.assertEqual(actor.gold,5)

    def test_solo_wait_advances_committed_work_without_starting_an_unpaid_job(self):
        from engine.commands import CommandContext,build_registry
        world,actor,_,_=fixture();begin(world,actor)
        resting.before_command(world,actor,'wait 5',build_registry())
        living.command(CommandContext(world,actor,world.rooms['market']),'5','wait')
        self.assertEqual(actor.gold,8)
        self.assertEqual(society.shop(world,'market')[1]['stock']['stew'],1)

    def test_paused_art_keeps_its_materials_and_time_while_worker_takes_a_job(self):
        from engine import artworks,knowledge
        world,actor,_,_=fixture()
        world.items.update(paper={'id':'paper','name':'Paper'},ink={'id':'ink','name':'Ink'})
        world.recipes['verse']={'id':'verse','name':'Write a verse','ingredients':{'paper':1,'ink':1},'outputs':{},
            'station':'hand','kind':'crafting','minutes':5,'artwork':{'kind':'poetry','style':'pastoral','title':'A short verse','text':'A bell rings over the garden.'}}
        actor.inventory+=['paper','ink'];knowledge.teach(world,actor,{'recipes':['verse']})
        artworks.begin(world,actor,'verse')
        with self.assertRaisesRegex(ValueError,'pause'):employment.apply(world,actor,'cook')
        artworks.interrupt(world,actor,'another job');begin(world,actor);tick(world,5)
        artworks.advance(world,5)
        self.assertEqual(actor.gold,8)
        self.assertEqual(actor.inventory,['keepsake'])
        self.assertTrue(artworks.active(world,actor)['paused'])
        self.assertEqual(artworks.active(world,actor)['remaining'],5)

    def test_opted_in_npc_cannot_skip_family_care_or_work_off_shift(self):
        world,actor,_,_=fixture(npc=True)
        world.npcs['worker']['employment_plan']={'enabled':True,'room':'market','vacancy':'cook'}
        world.npcs['worker']['district_resident']=True
        with patch('engine.family_life.care_shift',return_value=True):living.advance(world,1)
        self.assertNotIn(actor.id,employment._jobs(world))
        world.metadata['daily_life']=True;world.npcs['worker']['work_hours']={'start':900,'duration':200}
        with self.assertRaisesRegex(ValueError,'off duty'):employment.apply(world,actor,'cook')

    def test_explicit_npc_plan_runs_on_real_living_ticks_without_double_producer_wages(self):
        world,actor,_,_=fixture(npc=True);world.metadata['society']=True
        world.npcs['worker']['employment_plan']={'enabled':True,'room':'market','vacancy':'cook'}
        living.advance(world,1)
        self.assertIsNotNone(employment.active(world,actor))
        self.assertEqual(actor.gold,5)
        living.advance(world,5)
        self.assertEqual(actor.gold,8)
        self.assertEqual(society.shop(world,'market')[1]['stock']['stew'],1)

    def test_no_opt_in_never_assigns_or_hires_an_unrelated_npc(self):
        world,actor,_,_=fixture(npc=True)
        living.advance(world,5)
        self.assertNotIn(actor.id,employment._jobs(world))
        self.assertEqual(actor.gold,5)

    def test_validation_rejects_unfunded_schema_or_nonphysical_recipe_references(self):
        world,_,_,cfg=fixture()
        data={'room':[{**value,'id':ident} for ident,value in world.room_details.items()],
              'npc':list(world.npcs.values()),'recipe':list(world.recipes.values()),'item':list(world.items.values())}
        self.assertEqual(employment.validate(data),[])
        cfg['wage']=0
        self.assertIn('wage',str(employment.validate(data)))
        cfg['wage']=3;world.recipes['stew']['ingredients']={'imaginary_supply':1}
        self.assertIn('real recipe inputs',str(employment.validate(data)))


if __name__=='__main__':unittest.main()
