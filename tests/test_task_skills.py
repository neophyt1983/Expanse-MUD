"""Real work uses one persistent, progressively slower player/NPC skill model."""
from copy import deepcopy
import json
import unittest

from engine import task_skills, living, knowledge, locks, combat
from engine.commands import CommandContext, build_registry, process_command as dispatch
from test_burglary import fixture, observer
from test_guilds import fixture as working_world


class TaskPracticeTests(unittest.TestCase):
    def test_successive_levels_strictly_increase_and_equal_work_slows_with_expertise(self):
        costs=[task_skills.threshold(n) for n in range(101)]
        self.assertTrue(all(b>a for a,b in zip(costs,costs[1:])))
        self.assertEqual([costs[n] for n in (0,25,50,75)], [10,91,235,441])
        attempts=[]
        for initial in (0,25,50,75):
            world,actor,_=fixture();actor.progress['skills']['crafting']=initial
            count=0
            while task_skills.level(world,actor,'crafting')==initial:
                count+=1
                task_skills.practice(world,actor,'crafting',difficulty=initial,effort=1)
            attempts.append(count)
        self.assertEqual(attempts,[10,91,235,441])

    def test_player_and_npc_follow_identical_fractional_progress(self):
        world,player,_=fixture();npc=observer(world,'worker')
        for actor in (player,npc):
            for number in range(16):
                task_skills.practice(world,actor,'cooking',difficulty=10,effort=2,event_id='meal:'+str(number))
        self.assertEqual(player.progress[task_skills.KEY],npc.progress[task_skills.KEY])
        self.assertEqual(task_skills.level(world,player,'cooking'),task_skills.level(world,npc,'cooking'))
        self.assertIn(player.id,world.dirty_players)

    def test_fractional_practice_and_event_replay_survive_json_reload(self):
        world,actor,_=fixture()
        task_skills.practice(world,actor,'observation',effort=.5,event_id='saw-one')
        self.assertEqual(actor.progress[task_skills.KEY]['observation']['xp'],.5)
        actor.progress=json.loads(json.dumps(actor.progress));before=deepcopy(actor.progress)
        task_skills.validate_saved(actor.progress)
        task_skills.practice(world,actor,'observation',effort=.5,event_id='saw-one')
        self.assertEqual(actor.progress,before)
        world.living_state['minute']-=1
        task_skills.practice(world,actor,'observation',event_id='rewound')
        self.assertEqual(actor.progress,before)

    def test_readonly_view_and_command_never_practice_or_reveal_other_knowledge(self):
        world,actor,_=fixture();npc=observer(world,'private_reader')
        world.recipes={'owned':{'name':'Learned bread'},'secret':{'name':'Secret recipe'}}
        world.abilities={'known':{'name':'Known technique'},'hidden':{'name':'Hidden technique'}}
        actor.progress.update(knowledge={'recipes':['owned']},reading_journal_v1=['notice'])
        actor.abilities=['known'];npc.progress['knowledge']={'recipes':['secret']}
        living.state(world)
        before=deepcopy((world.living_state,actor.progress,npc.progress))
        view=task_skills.projection(world,actor)
        self.assertEqual(view['knowledge']['recipes'],[{'id':'owned','name':'Learned bread'}])
        self.assertNotIn('Secret recipe',str(view));self.assertNotIn('Hidden technique',str(view))
        self.assertEqual(before,(world.living_state,actor.progress,npc.progress))
        registry=build_registry()
        text=dispatch(registry,world,actor,'skills')
        self.assertIn('Learned bread',text);self.assertIn('Burgling:',text)
        self.assertEqual(before[0],world.living_state)
        self.assertEqual(before[2],npc.progress)
        self.assertNotIn(task_skills.KEY,actor.progress)
        self.assertEqual(actor.progress['knowledge']['recipes'],['owned'])

    def test_training_is_progressive_and_respects_instructor_ceiling(self):
        results=[]
        for initial in (0,50):
            world,actor,_=fixture();actor.progress['skills']['lockpicking']=initial
            gained=task_skills.training(world,actor,'lockpicking',5,event_id='lesson')
            results.append(gained)
            before=deepcopy(actor.progress)
            task_skills.training(world,actor,'lockpicking',5,event_id='lesson')
            self.assertEqual(before,actor.progress)
        self.assertGreater(results[0],results[1]);self.assertEqual(results[1],0)
        world,actor,_=fixture()
        task_skills.training(world,actor,'lockpicking',5,ceiling=1)
        self.assertEqual(task_skills.level(world,actor,'lockpicking'),1)
        self.assertEqual(actor.progress[task_skills.KEY]['lockpicking']['xp'],0)

    def test_invalid_attempts_and_detached_or_dead_actors_cannot_gain(self):
        world,actor,_=fixture();before=deepcopy(actor.progress)
        for value in (True,0,-1,float('nan'),float('inf'),10**400):
            task_skills.practice(world,actor,'crafting',effort=value)
        for task in ('', 'bad skill', '__secret',None):
            task_skills.practice(world,actor,task)
        actor.hp=0;task_skills.practice(world,actor,'crafting');actor.hp=100
        del world.entities[actor.id];task_skills.practice(world,actor,'crafting')
        self.assertEqual(before,actor.progress)

    def test_corrupt_practice_is_rejected_without_silently_erasing_progress(self):
        for row in ({'xp':float('nan')},{'xp':-1},{'xp':10000},{'attempts':True},
                    {'last_minute':-1},{'events':['fake-token']},{'events':['f'*64]*129}):
            progress={task_skills.KEY:{'crafting':row}};before=deepcopy(progress)
            with self.assertRaisesRegex(ValueError,'practice'):task_skills.validate_saved(progress)
            self.assertEqual(str(progress),str(before))

    def test_gather_and_craft_credit_only_real_material_changes_for_both_actor_kinds(self):
        for ident in ('player','worker'):
            world,player,worker,_=working_world();actor=world.entities[ident]
            world.move_entity(ident,'field')
            ctx=CommandContext(world,actor,world.rooms['field'])
            knowledge.teach(world,actor,{'recipes':['flour']})
            self.assertIn('Gathered',living.command(ctx,'wheat','gather'))
            self.assertEqual(actor.inventory.count('grain'),2)
            self.assertEqual(actor.progress[task_skills.KEY]['fieldcraft']['attempts'],1)
            before=deepcopy(actor.progress[task_skills.KEY])
            self.assertIn('replenish',living.command(ctx,'wheat','gather'))
            self.assertEqual(before,actor.progress[task_skills.KEY])
            self.assertIn('Created',living.command(ctx,'flour','craft'))
            self.assertEqual(actor.inventory.count('grain'),1)
            self.assertEqual(actor.inventory.count('flour'),1)
            self.assertEqual(actor.progress[task_skills.KEY]['crafting']['attempts'],1)
            actor.inventory.clear();before=deepcopy(actor.progress[task_skills.KEY])
            with self.assertRaises(ValueError):living.command(ctx,'flour','craft')
            self.assertEqual(before,actor.progress[task_skills.KEY])

    def test_real_failed_lock_work_practises_but_missing_tools_and_refresh_do_not(self):
        world,actor,row=fixture()
        row.update(locked=True,pickable=True,difficulty=50,public=True)
        world.living_state['physical_locks']['hall:pantry']['locked']=True
        world.items['lockpicks']={'id':'lockpicks','name':'Lockpicks','lockpick_tool':True}
        self.assertIn('picks',locks.act(world,actor,'pick','pantry').lower())
        self.assertNotIn(task_skills.KEY,actor.progress)
        actor.inventory=['lockpicks']
        text=locks.act(world,actor,'pick','pantry')
        self.assertIn('beyond your current lockpicking skill',text)
        self.assertEqual(actor.progress[task_skills.KEY]['lockpicking']['attempts'],1)
        before=deepcopy(actor.progress[task_skills.KEY])
        locks.act(world,actor,'pick','pantry')
        self.assertEqual(before,actor.progress[task_skills.KEY])
        world.living_state['minute']+=1
        locks.act(world,actor,'pick','pantry')
        self.assertEqual(actor.progress[task_skills.KEY]['lockpicking']['attempts'],2)

    def test_actual_strike_and_defence_train_both_participants(self):
        world,actor,_=fixture();target=observer(world,'opponent')
        world.metadata['society']=False
        text=combat.strike(world,actor,target,counter=False)
        self.assertIn('hit',text)
        for person in (actor,target):
            self.assertEqual(person.progress[task_skills.KEY]['fighting']['attempts'],1)
        self.assertLess(target.hp,target.max_hp)


if __name__=='__main__':unittest.main()
