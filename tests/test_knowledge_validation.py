import unittest
from unittest.mock import patch

from engine import knowledge


class CountingRows(list):
    def __init__(self, rows):
        super().__init__(rows)
        self.scans = 0

    def __iter__(self):
        self.scans += 1
        return super().__iter__()


class KnowledgeValidationTests(unittest.TestCase):
    def test_lookup_is_shared_within_one_validation_and_refreshed_after_edits(self):
        rooms = CountingRows([{'id': 'square'}])
        data = {'room': rooms, 'npc': [
            {'id': 'guard', 'knowledge': {'rooms': ['square']}},
            {'id': 'guide', 'knowledge': {'rooms': ['hall']}},
        ]}
        with patch('engine.quest_next_stop.validate', side_effect=lambda data: []):
            self.assertEqual(knowledge.validate(data),
                             ['guide: knowledge.rooms must contain existing room IDs'])
            self.assertEqual(rooms.scans, 1)
            rooms.append({'id': 'hall'})
            self.assertEqual(knowledge.validate(data), [])
            self.assertEqual(rooms.scans, 2)
