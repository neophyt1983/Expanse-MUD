import tempfile
import unittest
from pathlib import Path

from engine.civic_census import apply_batch, census, open_register


class CensusTests(unittest.TestCase):
    def test_replay_move_departure_and_atomic_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.sqlite'
            db = open_register(path)
            events = [
                ('a', 1, 'ada', 'founder', None, 'Dawnwatch'),
                ('b', 1, 'ben', 'birth', None, 'Dawnwatch'),
                ('c', 2, 'ada', 'move', 'Dawnwatch', 'Hearthmere'),
            ]
            apply_batch(db, reversed(events))
            db.close()
            db = open_register(path)
            self.addCleanup(db.close)
            apply_batch(db, events)
            self.assertEqual(census(db), {'Dawnwatch': 1, 'Hearthmere': 1})
            with self.assertRaises(ValueError):
                apply_batch(db, [('d', 3, 'ben', 'death', 'Dawnwatch', None),
                                 ('e', 4, 'ben', 'return', None, 'Dawnwatch')])
            self.assertEqual(db.execute('SELECT count(*) FROM membership_event').fetchone(), (3,))
            apply_batch(db, [('d', 3, 'ben', 'emigration', 'Dawnwatch', None),
                             ('e', 4, 'ben', 'return', None, 'Hearthmere'),
                             ('f', 5, 'ada', 'death', 'Hearthmere', None)])
            self.assertEqual(census(db), {'Hearthmere': 1})
