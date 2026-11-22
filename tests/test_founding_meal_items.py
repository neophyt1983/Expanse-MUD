"""Release-world meal counters must issue actual consumable food."""
import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile


class FoundingMealItemTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('EXPANSE_TEST_FOUNDING_CITIES'), 'Requires the opening world archive')
    def test_every_active_counter_issues_consumable_food(self):
        with ZipFile(Path(os.environ['EXPANSE_TEST_FOUNDING_CITIES'])) as archive:
            meta = json.loads(archive.read('metadata.json'))
            if 'household_provisions' not in meta:
                self.skipTest('This archived edition predates the household co-operatives')
            items = {item['id']: item for item in json.loads(archive.read('items.json'))}
        rules = meta['household_provisions']['cities']
        self.assertEqual(8, len(rules))
        for city, rule in rules.items():
            with self.subTest(city=city):
                meal = items[rule['meal_item']]
                self.assertIs(meal.get('need_consumable'), True)
                self.assertGreater(meal.get('need_effects', {}).get('hunger', 0), 0)
