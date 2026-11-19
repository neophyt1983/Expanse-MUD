"""Actor theft uses real finite inventories and the shared detection model."""
from collections import Counter
from copy import deepcopy
import unittest

from engine import burglary, mortality, theft
from test_burglary import Rolls, fixture, observer


class ActorTheftTests(unittest.TestCase):
    def test_skill_limits_the_actual_haul_and_conserves_every_item(self):
        for level, expected in ((0, 1), (50, 6), (100, 11)):
            with self.subTest(level=level):
                world, actor, _ = fixture(level)
                target = observer(world, 'target')
                target.inventory = ['bread'] * 20 + ['sword']
                actor.inventory = ['sword']
                total = Counter(target.inventory + actor.inventory)
                result = theft.transfer(world, actor, target.id, 'bread', 20, rng=Rolls(.1, .99, .99))
                self.assertTrue(result.attempt.success)
                self.assertEqual(result.quantity, expected)
                self.assertEqual(target.inventory.count('bread'), 20 - expected)
                self.assertEqual(actor.inventory.count('bread'), expected)
                self.assertEqual(Counter(target.inventory + actor.inventory), total)
                self.assertEqual(result.item_id, 'bread')
                self.assertIn(str(expected) + ' × Bread', result.message)

    def test_requested_maximum_clamps_to_live_stock_without_creating_items(self):
        world, actor, _ = fixture(100)
        target = observer(world, 'target')
        target.inventory = ['bread', 'bread']
        result = theft.transfer(world, actor, target.id, 'bread', 1000, rng=Rolls(.1, .99, .99))
        self.assertEqual(result.quantity, 2)
        self.assertEqual(actor.inventory, ['bread', 'bread'])
        self.assertFalse(target.inventory)

    def test_blind_failure_never_reveals_selected_item_or_pocket_contents(self):
        world, actor, _ = fixture()
        target = observer(world, 'target')
        target.inventory = ['sword', 'bread']
        before = deepcopy((actor.inventory, target.inventory))
        result = theft.transfer(world, actor, target.id, quantity=10, rng=Rolls(.99, .99))
        self.assertFalse(result.attempt.success)
        self.assertIsNone(result.item_id)
        self.assertEqual(result.quantity, 0)
        self.assertEqual(before, (actor.inventory, target.inventory))
        self.assertNotIn('bread', str(result).lower())
        self.assertNotIn('sword', str(result).lower())
        self.assertNotIn('mortality', world.living_state)
        self.assertNotIn('npc_life', target.progress)

    def test_blind_success_discloses_only_the_actual_stolen_item(self):
        world, actor, _ = fixture()
        target = observer(world, 'target')
        target.inventory = ['sword', 'bread', 'bread']
        result = theft.transfer(world, actor, target.id, quantity=3, rng=Rolls(.1, .99, .99))
        self.assertEqual(result.item_id, 'bread')
        self.assertEqual(result.quantity, 1)
        self.assertIn('Bread', result.message)
        self.assertNotIn('Sword', result.message)
        self.assertEqual(Counter(target.inventory), Counter(['sword', 'bread']))
        self.assertNotIn('npc_life', target.progress)  # Unnoticed loss gives no invented knowledge.

    def test_equipped_fixed_and_unknown_items_are_not_eligible(self):
        world, actor, _ = fixture(100)
        target = observer(world, 'target')
        target.inventory = ['sword', 'notice', 'unknown_item']
        target.equipped = {'weapon': 'sword'}
        rolls = Rolls()
        before = deepcopy((actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))
        for item_id in (None, 'sword', 'notice', 'unknown_item', 'bread'):
            with self.subTest(item_id=item_id), self.assertRaisesRegex(ValueError, 'no eligible item'):
                theft.transfer(world, actor, target.id, item_id, rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))

    def test_spare_copies_can_be_taken_without_removing_equipped_copies(self):
        world, actor, _ = fixture(100)
        target = observer(world, 'target')
        target.inventory = ['sword'] * 4
        target.equipped = {'weapon': 'sword'}
        result = theft.transfer(world, actor, target.id, 'sword', 20, rng=Rolls(.1, .99, .99))
        self.assertEqual(result.quantity, 3)
        self.assertEqual(target.inventory, ['sword'])
        self.assertEqual(target.equipped, {'weapon': 'sword'})
        self.assertEqual(actor.inventory, ['sword'] * 3)

    def test_all_player_and_npc_directions_use_the_same_finite_transfer(self):
        for thief_player in (False, True):
            for target_player in (False, True):
                with self.subTest(thief_player=thief_player, target_player=target_player):
                    world, actor, _ = fixture(50)
                    actor.is_player = thief_player
                    if not thief_player:
                        actor.source_def = 'thief_definition'
                        world.npcs[actor.source_def] = {'burglary': 50}
                    target = observer(world, 'target', player=target_player)
                    target.inventory = ['bread'] * 7
                    online = {entity.id for entity in (actor, target) if entity.is_player}
                    result = theft.transfer(world, actor, target.id, 'bread', 7,
                                            online_players=online, rng=Rolls(.1, .99, .99))
                    self.assertEqual(result.quantity, 6)
                    self.assertEqual(target.inventory, ['bread'])
                    self.assertEqual(actor.inventory, ['bread'] * 6)
                    self.assertTrue(online <= world.dirty_players)

    def test_offline_remote_dead_self_and_stale_targets_reject_before_rolls(self):
        for condition in ('offline', 'remote', 'dead', 'self', 'missing', 'name', 'stale_thief'):
            with self.subTest(condition=condition):
                world, actor, _ = fixture()
                target = observer(world, 'target', player=True)
                target.inventory = ['bread'] * 3
                selected, caller, online = target.id, actor, {target.id}
                if condition == 'offline':
                    online = set()
                elif condition == 'remote':
                    world.move_entity(target.id, 'away')
                elif condition == 'dead':
                    target.hp = 0
                elif condition == 'self':
                    selected = actor.id
                elif condition == 'missing':
                    selected = 'not_an_entity'
                elif condition == 'name':
                    selected = target.name
                elif condition == 'stale_thief':
                    caller = deepcopy(actor)
                before = deepcopy((actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))
                rolls = Rolls()
                with self.assertRaises(ValueError):
                    theft.transfer(world, caller, selected, online_players=online, rng=rolls)
                self.assertEqual(rolls.calls, 0)
                self.assertEqual(before, (actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))

    def test_invalid_quantities_and_sleeping_thief_cannot_start_an_attempt(self):
        world, actor, _ = fixture()
        target = observer(world, 'target')
        target.inventory = ['bread'] * 3
        rolls = Rolls()
        for quantity in (True, 0, -1, 1.5, '2', burglary.MAX_QUANTITY + 1):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                theft.transfer(world, actor, target.id, quantity=quantity, rng=rolls)
        actor.progress['player_rest'] = {'kind': 'sleeping', 'state': 'active'}
        before = deepcopy((actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))
        with self.assertRaisesRegex(ValueError, 'awake'):
            theft.transfer(world, actor, target.id, rng=rolls)
        self.assertEqual(rolls.calls, 0)
        self.assertEqual(before, (actor.progress, target.progress, actor.inventory, target.inventory, world.living_state))

    def test_sleeping_victim_can_lose_items_but_does_not_observe_the_attempt(self):
        for player in (False, True):
            with self.subTest(player=player):
                world, actor, _ = fixture()
                target = observer(world, 'target', level=100, player=player, awake=False)
                target.inventory = ['bread', 'bread']
                rolls = Rolls(.1, .1)
                result = theft.transfer(world, actor, target.id, quantity=2,
                                        online_players={target.id} if player else set(), rng=rolls)
                self.assertEqual(result.quantity, 1)
                self.assertEqual(rolls.calls, 2)
                self.assertFalse(result.attempt.detected)
                self.assertFalse(result.attempt.player_observers)
                self.assertNotIn('mortality', world.living_state)
                self.assertNotIn('npc_life', target.progress)

    def test_caught_failure_reports_attempt_without_transferring_and_keeps_partial_practice(self):
        world, actor, _ = fixture()
        target = observer(world, 'target')
        target.inventory = ['bread'] * 3
        before = deepcopy((actor.inventory, target.inventory))
        result = theft.transfer(world, actor, target.id, 'bread', 3, rng=Rolls(.99, 0))
        self.assertFalse(result.attempt.success)
        self.assertEqual(before, (actor.inventory, target.inventory))
        self.assertEqual(burglary.skill(world, actor), 0)
        report = mortality.state(world)['wanted'][actor.id]
        self.assertEqual(report['kind'], 'lock tampering')
        source = report['evidence'][-1]['source']
        self.assertEqual(source['kind'], 'inventory')
        self.assertEqual(source['id'], target.id)
        self.assertEqual(source['action'], 'tamper')
        self.assertEqual(source['quantity'], 0)
        self.assertEqual(burglary.skill(world, target, 'observation'), 0)
        self.assertGreater(target.progress['task_practice_v1']['observation']['xp'], 0)
        self.assertGreater(actor.progress['task_practice_v1']['burglary']['xp'], 0)

    def test_player_owner_detection_is_private_and_never_automatic_testimony(self):
        world, actor, _ = fixture()
        target = observer(world, 'target', player=True)
        target.inventory = ['bread', 'bread']
        result = theft.transfer(world, actor, target.id, quantity=2,
                                online_players={actor.id, target.id}, rng=Rolls(.1, .1, 0))
        self.assertEqual(result.quantity, 1)
        self.assertEqual(result.attempt.player_observers, [target])
        self.assertNotIn('mortality', world.living_state)
        self.assertFalse(getattr(world, 'runtime_notifications', []))
        self.assertEqual(world.rest_notifications[-1][0], target.id)
        self.assertIn('You notice Traveller steal 1 item(s)', world.rest_notifications[-1][1])
        self.assertNotIn('shouts', str(world.rest_notifications))
        self.assertEqual(world.dirty_players, {actor.id, target.id})

    def test_second_call_cannot_repeat_loot_during_cooldown(self):
        world, actor, _ = fixture()
        target = observer(world, 'target')
        target.inventory = ['bread'] * 4
        first = theft.transfer(world, actor, target.id, quantity=4, rng=Rolls(.1, .1, 0))
        before = deepcopy((actor.inventory, target.inventory, actor.progress, target.progress,
                           world.living_state, world.rest_notifications, world.runtime_notifications))
        rolls = Rolls()
        with self.assertRaisesRegex(ValueError, 'Wait 1 game minute'):
            theft.transfer(world, actor, target.id, quantity=4, rng=rolls)
        self.assertEqual(rolls.calls, 0)
        burglary.complete(world, actor, first.attempt)
        self.assertEqual(before, (actor.inventory, target.inventory, actor.progress, target.progress,
                                 world.living_state, world.rest_notifications, world.runtime_notifications))


if __name__ == '__main__':
    unittest.main()
