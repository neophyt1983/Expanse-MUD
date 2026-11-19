"""Shared Burgling/Observation mechanics with real entities and local witnesses."""
from copy import deepcopy
import json
import unittest

from engine import burglary, mortality, task_skills, worldtime
from engine.core import Entity, Room, World


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return next(self.values)


def fixture(level=0):
    world = World()
    world.metadata = {'society': True}
    world.rules = {'regional_gameplay': {'enabled': True}}
    world.living_state = {'minute': 480}
    world.room_details = {'hall': {'laws': {'enabled': True, 'authority': 'civic'}}, 'away': {}}
    world.add_room(Room('hall', 'Hall', '', {'east': 'away'}))
    world.add_room(Room('away', 'Away', '', {'west': 'hall'}))
    world.items = {'bread': {'id': 'bread', 'name': 'Bread'},
                   'sword': {'id': 'sword', 'name': 'Sword'},
                   'notice': {'id': 'notice', 'name': 'Fixed notice', 'anchored_readable': True}}
    actor = Entity('thief', 'Traveller', 100, 100, 10, 10, is_player=True, location='hall',
                   progress={'skills': {'burglary': level}})
    world.entities[actor.id] = actor
    world.rooms['hall'].entities.append(actor.id)
    row = {'id': 'pantry', 'name': 'Pantry cabinet', 'locked': False,
           'contents': ['bread'] * 40, 'theft_difficulty': 25}
    world.room_details['hall']['locks'] = [row]
    world.living_state['physical_locks'] = {'hall:pantry': {'locked': False, 'contents': ['bread'] * 40}}
    return world, actor, row


def observer(world, ident, level=0, *, room='hall', player=False, awake=True, alive=True, sentient=True):
    source = 'definition_'+ident
    world.npcs[source] = {'observation': level, 'social_profile': {'sentient': sentient}}
    person = Entity(ident, ident.title(), 100 if alive else 0, 100, 10, 10,
                    source_def=source, is_player=player, location=room,
                    progress={'skills': {'observation': level}, 'social_profile': {'sentient': sentient}})
    if not awake:
        if player:
            person.progress['player_rest'] = {'kind': 'sleeping', 'state': 'active'}
        else:
            person.activity = 'sleeping at home'
    world.entities[ident] = person
    world.rooms[room].entities.append(ident)
    return person


def commit(world, actor, result):
    if result.success:
        stock = world.living_state['physical_locks']['hall:pantry']['contents']
        del stock[:result.quantity]
        actor.inventory.extend(['bread'] * result.quantity)
    return burglary.complete(world, actor, result)


class BurglaryTests(unittest.TestCase):
    def test_task_levels_use_saved_skills_and_authored_defaults_not_character_level(self):
        world, actor, row = fixture()
        actor.char_class = 'scout'
        world.classes['scout'] = {'burglary': 12, 'observation': 23}
        actor.progress = {'advancement_v1': {'level': 99}}
        self.assertEqual(burglary.skill(world, actor), 12)
        self.assertEqual(burglary.skill(world, actor, 'observation'), 23)
        actor.progress['skills'] = {'burglary': 42}
        self.assertEqual(burglary.skill(world, actor), 42)
        npc = observer(world, 'guard', 61)
        npc.progress.pop('skills')
        self.assertEqual(burglary.skill(world, npc, 'observation'), 61)
        self.assertEqual(burglary.skill(world, npc), 0)
        npc.progress['skills'] = {'observation': 80}
        self.assertEqual(burglary.skill(world, npc, 'observation'), 80)

    def test_chance_projection_is_read_only_and_does_not_publish_observer_skills(self):
        world, actor, row = fixture(30)
        observer(world, 'secret_observer_identity', 87)
        before = deepcopy((world.living_state, actor.progress, row))
        view = burglary.chances(world, actor, row)
        self.assertEqual(before, (world.living_state, actor.progress, row))
        self.assertEqual(view['skill_name'], 'Burgling')
        self.assertEqual(view['level'], 30)
        self.assertEqual(view['success_chance'], .70)
        self.assertEqual(view['observer_count'], 1)
        self.assertNotIn('secret_observer_identity', str(view))
        self.assertNotIn('87', str(view))
        row['public'] = True
        self.assertEqual(burglary.chances(world, actor, row)['success_chance'], 1)
        self.assertEqual(burglary.chances(world, actor, row)['detection_risk'], 'none')

    def test_success_threshold_is_separate_from_having_any_observer(self):
        world, actor, row = fixture()
        success = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.3999, .9))
        self.assertTrue(success.success)
        self.assertEqual(success.quantity, 1)
        world, actor, row = fixture()
        failure = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.4))
        self.assertFalse(failure.success)
        self.assertEqual(failure.quantity, 0)
        self.assertFalse(failure.detected)

    def test_observation_contests_roll_independently_in_stable_id_order(self):
        world, actor, row = fixture(50)
        high = observer(world, 'z_high', 80)
        observer(world, 'a_low', 0)
        observer(world, 'm_equal', 50)
        # Detection chances after success: 5%, 40%, 70% in sorted ID order.
        rolls = Rolls(.1, .1, .06, .41, .69)
        result = burglary.attempt(world, actor, 'hall', row, rng=rolls)
        self.assertEqual(result.detected, [high])
        self.assertEqual(rolls.calls, 5)
        commit(world, actor, result)
        report = mortality.state(world)['wanted'][actor.id]
        self.assertEqual(report['witnesses'], [high.id])

    def test_only_live_awake_sentient_local_npcs_roll_without_online_player_context(self):
        world, actor, row = fixture()
        valid = observer(world, 'valid')
        observer(world, 'asleep', awake=False)
        observer(world, 'dead', alive=False)
        observer(world, 'animal', sentient=False)
        observer(world, 'remote', room='away')
        observer(world, 'offline_player', player=True)
        world.rooms['hall'].entities.append(valid.id)  # A duplicate roster entry is not two witnesses.
        rolls = Rolls(.1, .1, 0)
        result = burglary.attempt(world, actor, 'hall', row, rng=rolls)
        self.assertEqual(result.detected, [valid])
        self.assertFalse(result.player_observers)
        self.assertEqual(rolls.calls, 3)

    def test_owner_bonus_is_chance_not_automatic_detection(self):
        world, actor, row = fixture()
        owner = observer(world, 'owner')
        row['owner'] = owner.source_def
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.1, .1, .51))
        self.assertFalse(result.detected)  # Owner chance is 50%, still not guaranteed.

    def test_failed_detected_attempt_preserves_loot_and_reports_tampering_only(self):
        world, actor, row = fixture()
        witness = observer(world, 'witness')
        before = deepcopy((actor.inventory, world.living_state['physical_locks']))
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.99, 0))
        self.assertFalse(result.success)
        self.assertNotIn('mortality', world.living_state)
        commit(world, actor, result)
        self.assertEqual(before, (actor.inventory, world.living_state['physical_locks']))
        report = mortality.state(world)['wanted'][actor.id]
        self.assertEqual(report['kind'], 'lock tampering')
        self.assertEqual(report['evidence'][-1]['source']['action'], 'tamper')
        self.assertEqual(report['evidence'][-1]['source']['quantity'], 0)
        self.assertEqual(burglary.skill(world, actor), 0)
        self.assertEqual(burglary.skill(world, witness, 'observation'), 0)
        self.assertGreater(witness.progress[task_skills.KEY]['observation']['xp'], 0)

    def test_reports_shouts_and_learning_commit_once_after_transfer(self):
        world, actor, row = fixture()
        witness = observer(world, 'witness')
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.1, .1, 0))
        self.assertNotIn('mortality', world.living_state)
        self.assertEqual(burglary.skill(world, actor), 0)
        feedback = commit(world, actor, result)
        self.assertIn('notices the theft', feedback)
        self.assertNotIn('shouts', feedback)
        self.assertEqual(world.runtime_notifications[-1][3], {'role': 'npc', 'emphasis': 'shout'})
        self.assertEqual(world.rest_notifications[-1][2], {'role': 'npc', 'emphasis': 'shout'})
        self.assertEqual(burglary.skill(world, actor), 0)
        self.assertGreater(actor.progress[task_skills.KEY]['burglary']['xp'], 0)
        self.assertEqual(burglary.skill(world, witness, 'observation'), 0)
        self.assertGreater(witness.progress[task_skills.KEY]['observation']['xp'], 0)
        before = deepcopy((world.living_state, actor.progress, witness.progress,
                           world.runtime_notifications, world.rest_notifications))
        self.assertEqual(burglary.complete(world, actor, result), feedback)
        self.assertEqual(before, (world.living_state, actor.progress, witness.progress,
                                 world.runtime_notifications, world.rest_notifications))

    def test_online_player_detector_gets_private_notice_without_speaking_or_reporting(self):
        world, actor, row = fixture()
        player = observer(world, 'viewer', player=True)
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.1, .1, 0), online_players={player.id})
        commit(world, actor, result)
        self.assertFalse(result.detected)
        self.assertEqual(result.player_observers, [player])
        self.assertNotIn('mortality', world.living_state)
        self.assertFalse(getattr(world, 'runtime_notifications', []))
        self.assertEqual(world.rest_notifications[-1][0], player.id)
        self.assertTrue(world.rest_notifications[-1][1].startswith('You notice Traveller steal'))
        self.assertNotIn('shouts', str(world.rest_notifications))

    def test_cooldown_restraint_and_bad_quantities_reject_without_rolls_or_state_changes(self):
        world, actor, row = fixture()
        burglary.attempt(world, actor, 'hall', row, rng=Rolls(.99))
        before = deepcopy((world.living_state, actor.progress))
        rolls = Rolls()
        with self.assertRaisesRegex(ValueError, 'Wait 1 game minute'):
            burglary.attempt(world, actor, 'hall', row, rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (world.living_state, actor.progress))
        world.living_state['minute'] += 1
        actor.progress['restrained_until'] = 500
        before = deepcopy(actor.progress)
        with self.assertRaisesRegex(ValueError, 'restrained'):
            burglary.attempt(world, actor, 'hall', row, rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(actor.progress, before)
        for value in (True, 0, -1, 1.5, '2', burglary.MAX_QUANTITY+1):
            with self.subTest(quantity=value), self.assertRaises(ValueError):
                burglary.attempt(world, actor, 'hall', row, value, rolls)
        self.assertEqual(rolls.calls, 0)

    def test_permitted_transfers_have_no_roll_cooldown_reporting_or_practice(self):
        world, actor, row = fixture()
        row['public'] = True
        observer(world, 'witness', 100)
        before = deepcopy((actor.progress, world.living_state))
        rolls = Rolls()
        result = burglary.attempt(world, actor, 'hall', row, 20, rolls)
        self.assertTrue(result.permitted)
        self.assertEqual(result.quantity, 20)
        self.assertEqual(burglary.complete(world, actor, result), '')
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.progress, world.living_state))

    def test_successful_quality_limited_amount_is_monotone_in_skill_with_fixed_rolls(self):
        quantities = []
        for level in range(101):
            world, actor, row = fixture(level)
            result = burglary.attempt(world, actor, 'hall', row, 30, Rolls(.1, .99))
            self.assertTrue(result.success)
            quantities.append(result.quantity)
        self.assertEqual(quantities, sorted(quantities))
        self.assertEqual(quantities[0], 1)
        self.assertEqual(quantities[50], 6)
        self.assertEqual(quantities[100], 11)
        world, actor, row = fixture(100)
        self.assertEqual(burglary.attempt(world, actor, 'hall', row, 2, Rolls(.1, .99)).quantity, 2)

    def test_every_completed_attempt_trains_without_instant_levels_or_daily_cutoff(self):
        world, actor, row = fixture()
        witness = observer(world, 'witness')
        for number in range(12):
            world.living_state['minute'] += 1
            result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.999, 0))
            commit(world, actor, result)
        self.assertEqual(actor.inventory, [])
        self.assertEqual(actor.progress[task_skills.KEY]['burglary']['attempts'], 12)
        self.assertEqual(witness.progress[task_skills.KEY]['observation']['attempts'], 12)
        self.assertGreater(burglary.skill(world, actor), 0)
        self.assertLess(burglary.skill(world, actor), 12)
        world.living_state['minute'] += worldtime.MINUTES_PER_DAY
        before = deepcopy(actor.progress[task_skills.KEY]['burglary'])
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(.999, 0))
        commit(world, actor, result)
        self.assertEqual(actor.progress[task_skills.KEY]['burglary']['attempts'], before['attempts']+1)
        # Easy work remains practice even after the actor outgrows its difficulty.
        world.living_state['minute'] += 1
        actor.progress['skills']['burglary'] = 70
        before = actor.progress[task_skills.KEY]['burglary']['xp']
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(0, 0, 0))
        commit(world, actor, result)
        self.assertEqual(burglary.skill(world, actor), 70)
        self.assertGreater(actor.progress[task_skills.KEY]['burglary']['xp'], before)

    def test_saved_progress_retains_cooldown_and_prevents_repeat_training_after_reload(self):
        world, actor, row = fixture()
        result = burglary.attempt(world, actor, 'hall', row, rng=Rolls(0, 0))
        commit(world, actor, result)
        restored = json.loads(json.dumps(actor.progress))
        other_world, restored_actor, restored_row = fixture()
        restored_actor.progress = restored
        with self.assertRaisesRegex(ValueError, 'Wait 1 game minute'):
            burglary.attempt(other_world, restored_actor, 'hall', restored_row, rng=Rolls())
        other_world.living_state['minute'] += worldtime.MINUTES_PER_DAY
        another = burglary.attempt(other_world, restored_actor, 'hall', restored_row, rng=Rolls(0, 0))
        commit(other_world, restored_actor, another)
        self.assertEqual(burglary.skill(other_world, restored_actor), 0)
        self.assertEqual(restored_actor.progress[task_skills.KEY]['burglary']['attempts'], 2)
        self.assertEqual(restored_actor.progress[task_skills.KEY]['burglary']['xp'], 6)


if __name__ == '__main__':
    unittest.main()
