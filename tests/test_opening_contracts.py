import copy
import unittest
from types import SimpleNamespace

from engine import earned_lodging, earned_start, opening_contracts


class OpeningContractTests(unittest.TestCase):
    def setUp(self):
        self.subject = 'player-a'
        self.ready = {'unit': 'ward_dawn_4_5:1', 'owner': '', 'rent': 2,
                      'phase': 'held', 'remaining': earned_lodging.WEEK}
        self.state = {
            'economy': {'shops': {
                'inn': {'gold': 240, 'stock': {'lw_stew': 2}},
                'market': {'gold': 120, 'stock': {'lw_stew': 8}},
            }},
            earned_lodging.KEY: {self.subject: self.ready},
            opening_contracts.BOOK: {
                self.subject: {
                    'job': 'deliver', 'source': 'inn', 'dest': 'market',
                    'phase': 'collected', 'invoice': 36, 'materials': {'lw_stew': 6},
                },
            },
        }
        self.progress = {opening_contracts.MARK: True}

    def test_order_cleanup_releases_stock_payment_payroll_and_rent_once(self):
        opening_contracts.relinquish(self.state, self.subject, self.progress)
        shops = self.state['economy']['shops']
        self.assertEqual(8, shops['inn']['stock']['lw_stew'])
        self.assertEqual(120 + 36 + 30 + 18, shops['market']['gold'])
        expected = copy.deepcopy(self.state)
        opening_contracts.relinquish(self.state, self.subject, self.progress)
        self.assertEqual(expected, self.state)

    def test_ready_room_refunds_only_unused_rent(self):
        self.state[opening_contracts.BOOK].clear()
        self.ready['phase'] = 'ready'
        self.progress[opening_contracts.DONE] = 'market'
        opening_contracts.relinquish(self.state, self.subject, self.progress)
        self.assertEqual(138, self.state['economy']['shops']['market']['gold'])
        self.assertEqual({}, self.state[earned_lodging.KEY])

    def test_active_room_keeps_landlord_payment_and_releases_only_own_tenancy(self):
        self.state[opening_contracts.BOOK].clear()
        self.ready['phase'] = 'active'
        self.progress[opening_contracts.DONE] = 'market'
        unit = {'tenant': self.subject, 'storage': ['a-book']}
        self.state['settlements'] = {'units': {self.ready['unit']: unit}}
        opening_contracts.relinquish(self.state, self.subject, self.progress)
        self.assertEqual(120, self.state['economy']['shops']['market']['gold'])
        self.assertEqual('', unit['tenant'])
        self.assertEqual(['a-book'], unit['storage'])

    def test_city_guide_and_old_welcome_payment_only_retired_for_new_start(self):
        p = SimpleNamespace(is_player=True, progress={
            earned_start.MARK: earned_start.VERSION, opening_contracts.MARK: True,
        })
        guide = 'first_steps_river_assembly_1__step_01'
        chain = 'first_steps_river_assembly_1'
        quest = {'id': 'first_steps_river_assembly_3', 'reward_gold': 12}
        self.assertTrue(earned_start.retired(p, guide))
        self.assertEqual([chain], earned_start.omit_stage(p, chain, [guide, chain]))
        self.assertEqual(0, earned_start.gold_reward(p, quest))
        del p.progress[opening_contracts.MARK]
        self.assertFalse(earned_start.retired(p, guide))
        self.assertEqual(12, earned_start.gold_reward(p, quest))

    def test_existing_character_enrollment_and_unrelated_templates_are_preserved(self):
        original = copy.deepcopy(self.state)
        opening_contracts.relinquish(self.state, self.subject, {})
        self.assertEqual(original, self.state)
        for metadata in ({}, {'municipal_genesis': None},
                         {'civic_opening_release': '1.10.0-rc1',
                          'municipal_genesis': {'version': 1, 'seed': 9}}):
            self.assertFalse(opening_contracts.enabled(SimpleNamespace(metadata=metadata)))
