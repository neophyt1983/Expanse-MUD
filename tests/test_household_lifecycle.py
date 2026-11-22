"""Generated doorstep residents move between the live room and the court roll."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from engine import civic_visits, living
from engine.core import Entity, Room, World


class HouseholdLifecycleTests(unittest.TestCase):
    court = 'gen_dawn_lane_1'

    def setUp(self):
        self.storage = TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.world = World()
        self.world.game_dir = Path(self.storage.name)
        self.world.metadata = {'living_world': True, 'local_sight_tiles': 1}
        self.world.room_details = {}
        for ident, exits in ((self.court, {'out':'street'}),
                             ('street', {'in':self.court, 'out':'road'}),
                             ('road', {'in':'street'})):
            self.world.add_room(Room(ident, ident, '', exits=exits))
        self.rows = [
            dict(id=f'gen_dawn_person_{i}', name=f'Resident {i}', home=self.court,
                 door=i, occupation='grower', work='street')
            for i in range(1,6)]
        path = self.world.game_dir / 'assets' / 'chronicles'
        path.mkdir(parents=True)
        (path / (self.court+'.json')).write_text(json.dumps(self.rows))
        self.context = SimpleNamespace(world=self.world, player=SimpleNamespace(location=self.court))

    def knock(self, index):
        row = self.rows[index]
        return civic_visits.knock(self.context, str(row['door']))

    def actor_id(self, index):
        return 'npc:'+self.rows[index]['id']

    def test_radius_watch_and_edits_preserve_live_actors(self):
        world = self.world
        for i in range(5):
            self.knock(i)
        nearby = Entity('player','Visitor',10,10,1,1,is_player=True)
        world.add_entity(nearby, 'street')
        civic_visits.retire_distant(world)
        self.assertTrue(all(self.actor_id(i) in world.entities for i in range(5)))
        world.living_state['resident_watches'] = {self.actor_id(0): {'observers':['offline-player']}}
        world.npcs[self.rows[1]['id']]['occupation'] = 'teacher'
        world.entities[self.actor_id(2)].progress['companion_owner'] = nearby.id
        world.living_state['extension'] = {'assignment': {'worker': self.actor_id(3)}}
        world.move_entity(nearby.id, 'road', forced=True)
        civic_visits.retire_distant(world)
        self.assertTrue(all(self.actor_id(i) in world.entities for i in range(4)))
        self.assertNotIn(self.actor_id(4), world.entities)
        self.assertEqual(self.court, civic_visits.home_address(world, self.actor_id(4)))

    def test_two_viewers_and_reentry_only_restore_previously_met(self):
        world = self.world
        for i in range(2):
            self.knock(i)
        for name, room in [('first','road'),('second',self.court)]:
            world.add_entity(Entity(name,name,10,10,1,1,is_player=True),room)
        civic_visits.retire_distant(world)
        self.assertIn(self.actor_id(0),world.entities)
        world.move_entity('second', 'road', forced=True)
        civic_visits.retire_distant(world)
        self.assertNotIn(self.actor_id(0),world.entities)
        civic_visits.enter_court(world, self.court)
        civic_visits.enter_court(world, self.court)
        self.assertEqual([1,1,0,0,0], [world.rooms[self.court].entities.count(self.actor_id(i)) for i in range(5)])

    def test_wake_and_missing_actor_cannot_duplicate_gold_or_revive_death(self):
        self.knock(0)
        actor = self.world.entities[self.actor_id(0)]
        actor.gold = 11
        actor.inventory = ['ring','ring']
        actor.equipped = {'right_hand':'ring'}
        actor.activity = 'sleeping'
        civic_visits.retire_distant(self.world)
        self.assertNotIn(actor.id,self.world.entities)
        self.assertIn(actor.name, self.knock(0))
        returned = self.world.entities[actor.id]
        self.assertEqual((11,['ring','ring'],{'right_hand':'ring'}),
                         (returned.gold,returned.inventory,returned.equipped))
        self.assertIn(actor.name,self.knock(0))
        self.assertIs(returned,self.world.entities[actor.id])
        self.world.living_state['minute'] += 15
        civic_visits.retire_distant(self.world)
        self.world.killed_npcs.add(actor.source_def)
        self.assertIn('no answer',self.knock(0))
        self.assertNotIn(actor.id,self.world.entities)
        self.assertIsNone(civic_visits.home_address(self.world,actor.id))
