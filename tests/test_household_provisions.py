import copy
import unittest

from engine import household_provisions as provisions, worldtime


class ProvisionAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.cities = {
            'Alder': dict(member_count=4, member_prefix='alder_person_', daily_portions=2, store_days=3,
                          beds_per_grower=12, rotation_days=2, planting_beds=20, batches_per_cook=8,
                          servings_per_porter=8, field='allotments', garden='garden', kitchen='inn',
                          market='market', seasonal_yield_percent=dict.fromkeys(worldtime.SEASONS, 75),
                          crop_batch={'root': 1}, meal_item='stew', recipe='soup',
                          workforce={'growers': [1, 2], 'cooks': [3], 'porters': [4]})}
        self.cfg = {'version': 1, 'issue_minute': 900, 'cities': self.cities}
        self.rooms = {'allotments', 'garden', 'inn', 'market'}
        self.items = {'root', 'stew'}
        self.recipes = {'soup': {'ingredients': {'root': 1}, 'outputs': {'stew': 1}}}

    def check(self, cfg):
        return provisions.validate(cfg, self.rooms, self.items, self.recipes)

    def test_legacy_and_valid_rules(self):
        self.assertEqual([], self.check(None))
        self.assertEqual([], self.check(self.cfg))

    def test_configuration_and_register_boundaries(self):
        for cfg in ([], {'version': True}, dict(self.cfg, issue_minute=1500),
                    dict(self.cfg, issue_minute=-1), dict(self.cfg, cities=[])):
            with self.subTest(cfg=cfg):
                self.assertTrue(self.check(cfg))
        self.cities['Other'] = copy.deepcopy(self.cities['Alder'])
        self.assertTrue(any('prefix' in issue for issue in self.check(self.cfg)))

    def test_invalid_facilities_ingredients_and_double_assigned_workers(self):
        for key, value in (
            ('member_count', False), ('rotation_days', 0), ('crop_batch', {}),
            ('meal_item', []), ('field', ['allotments']), ('recipe', 'missing'),
            ('crop_batch', {'root': -1}), ('seasonal_yield_percent', {'winter': 20}),
            ('workforce', {'growers': [1], 'cooks': [1], 'porters': []}),
            ('workforce', {'growers': [-1], 'cooks': [3], 'porters': [4]}),
            ('workforce', {'growers': [5], 'cooks': [3], 'porters': [4]}),
        ):
            with self.subTest(key=key, value=value):
                cfg = copy.deepcopy(self.cfg)
                cfg['cities']['Alder'][key] = value
                self.assertTrue(self.check(cfg))

    def test_recipe_must_consume_crops_and_produce_one_meal(self):
        for recipe in ({'ingredients': {}, 'outputs': {'stew': 1}},
                       {'ingredients': {'root': 0}, 'outputs': {'stew': 1}},
                       {'ingredients': {'flour': 1}, 'outputs': {'stew': 1}},
                       {'ingredients': {'root': 1}, 'outputs': {'stew': 2}}):
            with self.subTest(recipe=recipe):
                self.recipes['soup'] = recipe
                self.assertTrue(self.check(self.cfg))
