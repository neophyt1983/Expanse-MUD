"""Real physical-container commands share finite Burgling and Observation."""
from collections import Counter
from copy import deepcopy
import unittest

from engine import burglary, locks, mortality, task_skills, theft
from test_burglary import Rolls, fixture, observer


def container(level=0, contents=None):
    world, actor, row = fixture(level)
    state = locks.saved(world, 'hall', row)
    state['contents'] = list(contents if contents is not None else ['bread'] * 6)
    return world, actor, row, state


class ContainerBurglaryTests(unittest.TestCase):
    def test_take_all_takes_only_the_quality_limited_part_of_mixed_finite_contents(self):
        world, actor, row, state = container(20, ['bread', 'sword', 'bread', 'sword', 'bread'])
        total = Counter(actor.inventory + state['contents'])
        text = locks.act(world, actor, 'take', 'pantry', rng=Rolls(.1, .1))
        self.assertTrue(text.startswith('You steal 2 × Bread, 1 × Sword from Pantry cabinet.'))
        self.assertEqual(actor.inventory, ['bread', 'sword', 'bread'])
        self.assertEqual(state['contents'], ['sword', 'bread'])
        self.assertEqual(Counter(actor.inventory + state['contents']), total)
        self.assertEqual(burglary.skill(world, actor), 20)
        self.assertGreater(actor.progress[task_skills.KEY]['burglary']['xp'], 0)

    def test_selected_quantity_is_a_maximum_and_reports_the_actual_transfer(self):
        world, actor, row, state = container(0, ['bread'] * 6 + ['sword'])
        total = Counter(actor.inventory + state['contents'])
        text = locks.act(world, actor, 'take-item', 'pantry', item='bread', quantity=5,
                         rng=Rolls(.1, .9))
        self.assertTrue(text.startswith('You steal 1 × Bread from Pantry cabinet.'))
        self.assertEqual(actor.inventory, ['bread'])
        self.assertEqual(state['contents'], ['bread'] * 5 + ['sword'])
        self.assertEqual(Counter(actor.inventory + state['contents']), total)

    def test_high_skill_does_not_take_more_than_the_selected_quantity(self):
        world, actor, row, state = container(100)
        text = locks.transfer(world, actor, 'pantry', 'bread', 2, rng=Rolls(.1, .99))
        self.assertTrue(text.startswith('You steal 2 × Bread from Pantry cabinet.'))
        self.assertEqual(actor.inventory, ['bread', 'bread'])
        self.assertEqual(state['contents'], ['bread'] * 4)

    def test_failed_take_and_selected_take_preserve_both_collections_and_report_only_attempt(self):
        for action in ('take', 'take-item'):
            with self.subTest(action=action):
                world, actor, row, state = container()
                witness = observer(world, 'witness')
                before = deepcopy((actor.inventory, state['contents']))
                text = locks.act(world, actor, action, 'pantry', item='bread', quantity=4,
                                 rng=Rolls(.99, 0))
                self.assertIn('You fail to steal anything', text)
                self.assertEqual(before, (actor.inventory, state['contents']))
                self.assertEqual(burglary.skill(world, actor), 0)
                self.assertEqual(burglary.skill(world, witness, 'observation'), 0)
                self.assertGreater(witness.progress[task_skills.KEY]['observation']['xp'], 0)
                report = mortality.state(world)['wanted'][actor.id]
                self.assertEqual(report['kind'], 'lock tampering')
                self.assertEqual(report['evidence'][-1]['source']['quantity'], 0)
                self.assertEqual(report['evidence'][-1]['source']['action'], 'tamper')

    def test_cooldown_applies_across_container_actions_and_later_real_attempt_trains(self):
        world, actor, row, state = container()
        locks.transfer(world, actor, 'pantry', 'bread', 3, rng=Rolls(.1, .1))
        before = deepcopy((actor.inventory, state['contents'], actor.progress))
        rolls = Rolls()
        with self.assertRaisesRegex(ValueError, 'Wait 1 game minute'):
            locks.act(world, actor, 'take', 'pantry', rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.inventory, state['contents'], actor.progress))
        world.living_state['minute'] += 1
        locks.act(world, actor, 'take', 'pantry', rng=Rolls(.1, .1))
        self.assertEqual(actor.inventory, ['bread', 'bread'])
        self.assertEqual(burglary.skill(world, actor), 0)
        self.assertEqual(actor.progress[task_skills.KEY]['burglary']['attempts'], 2)

    def test_permitted_transfers_remain_full_size_without_rolls_cooldown_or_practice(self):
        for action in ('take', 'take-item'):
            with self.subTest(action=action):
                world, actor, row, state = container()
                row['public'] = True
                observer(world, 'watcher', 100)
                actor.progress[burglary.ATTEMPT_KEY] = {'next_minute': 500, 'count': 1}
                before = deepcopy(actor.progress)
                rolls = Rolls()
                text = locks.act(world, actor, action, 'pantry', item='bread', quantity=6, rng=rolls)
                self.assertTrue(text.startswith('You take '))
                self.assertEqual(actor.inventory, ['bread'] * 6)
                self.assertEqual(state['contents'], [])
                self.assertEqual(rolls.calls, 0)
                self.assertEqual(actor.progress, before)
                self.assertNotIn('mortality', world.living_state)
                self.assertFalse(getattr(world, 'runtime_notifications', []))

    def test_lock_fixed_item_missing_item_and_invalid_count_fail_before_rolls(self):
        for condition in ('locked', 'fixed', 'missing', 'too_many', 'bool', 'zero', 'fraction'):
            with self.subTest(condition=condition):
                world, actor, row, state = container()
                item, quantity = 'bread', 1
                if condition == 'locked':
                    state['locked'] = True
                elif condition == 'fixed':
                    item = 'notice'
                    state['contents'].append('notice')
                elif condition == 'missing':
                    item = 'sword'
                elif condition == 'too_many':
                    quantity = 7
                elif condition == 'bool':
                    quantity = True
                elif condition == 'zero':
                    quantity = 0
                else:
                    quantity = 1.5
                before = deepcopy((actor.inventory, state, actor.progress))
                rolls = Rolls()
                with self.assertRaises(ValueError):
                    locks.transfer(world, actor, 'pantry', item, quantity, rng=rolls)
                self.assertEqual(rolls.calls, 0)
                self.assertEqual(before, (actor.inventory, state, actor.progress))
                self.assertNotIn('mortality', world.living_state)

    def test_take_all_with_a_fixed_object_rejects_before_touching_partial_contents(self):
        world, actor, row, state = container(100, ['bread', 'notice', 'bread'])
        before = deepcopy((actor.inventory, state['contents'], actor.progress))
        rolls = Rolls()
        self.assertIn('Some contents cannot be moved', locks.act(world, actor, 'take', 'pantry', rng=rolls))
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.inventory, state['contents'], actor.progress))

    def test_only_detectors_get_evidence_but_real_failed_observation_also_practises(self):
        world, actor, row, state = container(20)
        missed = observer(world, 'a_missed')
        caught = observer(world, 'z_caught')
        sleeping = observer(world, 'sleeping', awake=False)
        remote = observer(world, 'remote', room='away')
        text = locks.transfer(world, actor, 'pantry', 'bread', 5, rng=Rolls(.1, .1, .99, 0))
        self.assertIn('Z_Caught notices the theft.', text)
        report = mortality.state(world)['wanted'][actor.id]
        self.assertEqual(report['witnesses'], [caught.id])
        self.assertEqual(report['evidence'][-1]['source']['quantity'], 3)
        self.assertEqual(burglary.skill(world, caught, 'observation'), 0)
        self.assertGreater(caught.progress[task_skills.KEY]['observation']['xp'], 0)
        self.assertGreater(missed.progress[task_skills.KEY]['observation']['xp'], 0)
        self.assertLess(missed.progress[task_skills.KEY]['observation']['xp'], caught.progress[task_skills.KEY]['observation']['xp'])
        for person in (sleeping, remote):
            self.assertNotIn(task_skills.KEY, person.progress)
            self.assertEqual(burglary.skill(world, person, 'observation'), 0)
            self.assertNotIn('npc_life', person.progress)

    def test_taking_the_permission_key_is_still_reported_and_labeled_as_theft(self):
        for action in ('take', 'take-item'):
            with self.subTest(action=action):
                world, actor, row, state = container(0, ['key'])
                world.items['key'] = {'id': 'key', 'name': 'Pantry key'}
                row['key'] = 'key'
                witness = observer(world, 'owner')
                row['owner'] = witness.source_def
                self.assertFalse(locks.permitted(world, actor, row))
                text = locks.act(world, actor, action, 'pantry', item='key', rng=Rolls(.1, .1, 0))
                self.assertTrue(locks.permitted(world, actor, row))
                self.assertTrue(text.startswith('You steal 1 × Pantry key from Pantry cabinet.'))
                self.assertEqual(actor.inventory, ['key'])
                self.assertEqual(state['contents'], [])
                self.assertEqual(mortality.state(world)['wanted'][actor.id]['kind'], 'theft')

    def test_actor_theft_and_container_theft_share_the_same_cooldown(self):
        world, actor, row, state = container()
        victim = observer(world, 'victim')
        victim.inventory = ['bread'] * 3
        theft.transfer(world, actor, victim.id, quantity=3, rng=Rolls(.1, .1, .99))
        before = deepcopy((actor.inventory, state['contents'], actor.progress))
        rolls = Rolls()
        with self.assertRaisesRegex(ValueError, 'Wait 1 game minute'):
            locks.transfer(world, actor, 'pantry', 'bread', rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.inventory, state['contents'], actor.progress))

    def test_burgling_and_lockpicking_levels_cannot_substitute_for_each_other(self):
        world, actor, row, state = container(100)
        world.items['lockpicks'] = {'id': 'lockpicks', 'name': 'Lockpicks', 'lockpick_tool': True}
        actor.inventory = ['lockpicks']
        state['locked'] = True
        self.assertIn('beyond your current lockpicking skill', locks.act(world, actor, 'pick', 'pantry'))
        self.assertTrue(state['locked'])
        actor.progress['skills'] = {'burglary': 0, 'lockpicking': 100}
        state['locked'] = False
        text = locks.transfer(world, actor, 'pantry', 'bread', rng=Rolls(.99))
        self.assertIn('You fail to steal anything', text)
        self.assertEqual(actor.inventory, ['lockpicks'])
        self.assertEqual(state['contents'], ['bread'] * 6)


if __name__ == '__main__':
    unittest.main()
