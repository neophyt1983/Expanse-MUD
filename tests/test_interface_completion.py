"""Regression coverage for finished interface lessons and their ordinary turn-in.

Run with EXPANSE_TEST_WORLD pointing to an extracted authored Expanse game, or
from this review workspace where the unmodified 1.9.15 template is available.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from engine import interface_tours, living, quest_alternatives
from engine.commands import CommandContext, _cmd_read
from engine.core import Entity
from engine.loader import build_world


def authored_world():
    override=os.environ.get('EXPANSE_TEST_WORLD')
    workspace=Path(__file__).resolve().parents[3]
    candidates=([Path(override)] if override else [])+[
        workspace/'desktop-bundle/work/games/expanse',
        workspace/'audit-mainline/work/games/expanse',
    ]
    for path in candidates:
        if (path/'quests.json').is_file():return path
    raise unittest.SkipTest('Set EXPANSE_TEST_WORLD to the extracted authored 1.9.15 game directory.')


class InterfaceCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=build_world(authored_world())
        cls.heads=[q for q in cls.world.quests.values()
                   if quest_alternatives.reference(q)
                   and q.get('quest_chain',{}).get('index')==0]

    def new_player(self,quest):
        w=self.world;w.living_state={'minute':480};w.entities={}
        p=Entity('interface-regression','Traveller',100,100,10,10,is_player=True,
                 location=quest['offer_room'],race='human')
        w.entities[p.id]=p
        # Use the actually placed public reading source, as the game UI does.
        source=next(iid for iid in w.rooms[p.location].items
                    if quest['id'] in w.items.get(iid,{}).get('knowledge',{}).get('quests',[]))
        _cmd_read(self.ctx(p),source)
        accepted=living.quest_command(self.ctx(p),quest['id'],'accept')
        self.assertTrue(accepted.startswith('Quest accepted.'),accepted)
        return p

    def ctx(self,p):return CommandContext(self.world,p,self.world.rooms[p.location])

    def finish(self,p,quest):
        for _ in range(interface_tours.MAX_STEPS+1):
            current=interface_tours.projection(self.world,p)['current']
            self.assertEqual(quest['id'],current['quest_id'])
            if current['completed']:return
            interface_tours.handle(self.world,p,{'action':'next','quest_id':quest['id'],
                'revision':current['revision'],'step_id':current['step_id']})
        self.fail('Guide did not finish within its authored step bound.')

    def complete(self,p,quest):return living.quest_command(self.ctx(p),quest['id'],'complete')

    def payout_snapshot(self,p):
        return p.gold,list(p.inventory),json.dumps(p.progress.get('advancement_v1',{}),sort_keys=True)

    def test_all_eight_fresh_interface_only_lessons_complete_at_their_inn(self):
        self.assertEqual(8,len(self.heads))
        for quest in self.heads:
            with self.subTest(quest=quest['id']):
                self.assertEqual([],quest.get('prerequisites',[]))
                for field in ('actions','required_items','kills','visit_rooms','talk_to','witnesses','escort'):
                    self.assertFalse(quest.get(field),field)
                p=self.new_player(quest)
                before=self.payout_snapshot(p);actions=deepcopy(p.progress.get('actions',{}))
                self.assertIn('Finish the interface guide first.',self.complete(p,quest))
                self.finish(p,quest)
                self.assertEqual(actions,p.progress.get('actions',{}))
                self.assertEqual(before,self.payout_snapshot(p))
                self.assertFalse(interface_tours.blocked(p,quest))
                self.assertTrue(self.complete(p,quest).startswith('Quest complete.'))
                self.assertEqual('complete',p.progress['quests'][quest['id']])
                self.assertIn(quest['id'],p.progress['quest_chain_runs'][quest['quest_chain']['id']]['completed'])
                paid=self.payout_snapshot(p)
                self.assertFalse(self.complete(p,quest).startswith('Quest complete.'))
                self.assertEqual(paid,self.payout_snapshot(p))

    def test_all_eight_full_ordered_acknowledgements_settle_even_if_satisfied_flag_is_stale(self):
        for quest in self.heads:
            with self.subTest(quest=quest['id']):
                p=self.new_player(quest);row=p.progress[interface_tours.KEY][quest['id']]
                row['acknowledged']=[step['id'] for step in quest['interface_tour']['steps']]
                row['satisfied']=False
                before=deepcopy(p.progress)
                summary=interface_tours.summary(p,quest)
                self.assertTrue(summary['completed'])
                self.assertFalse(summary['required'])
                self.assertFalse(interface_tours.blocked(p,quest))
                self.assertEqual(before,p.progress,'Guide projections must remain read-only.')
                self.assertTrue(self.complete(p,quest).startswith('Quest complete.'))
                paid=self.payout_snapshot(p)
                self.assertFalse(self.complete(p,quest).startswith('Quest complete.'))
                self.assertEqual(paid,self.payout_snapshot(p))

    def test_incomplete_or_invalid_prefix_cannot_bypass_the_required_guide(self):
        quest=self.heads[0];ids=[step['id'] for step in quest['interface_tour']['steps']]
        for acknowledged in ([],ids[:-1],ids[1:],list(reversed(ids)),[ids[0],ids[0]],'not-a-list'):
            with self.subTest(acknowledged=acknowledged):
                p=self.new_player(quest);row=p.progress[interface_tours.KEY][quest['id']]
                row['acknowledged']=acknowledged;row['satisfied']=False
                before=self.payout_snapshot(p)
                self.assertFalse(interface_tours.summary(p,quest)['completed'])
                self.assertTrue(interface_tours.blocked(p,quest))
                self.assertIn('Finish the interface guide first.',self.complete(p,quest))
                self.assertEqual('active',p.progress['quests'][quest['id']])
                self.assertEqual(before,self.payout_snapshot(p))

    def test_optional_replay_keeps_previously_satisfied_guide_valid(self):
        quest=self.heads[0];p=self.new_player(quest);self.finish(p,quest)
        interface_tours.handle(self.world,p,{'action':'restart','quest_id':quest['id']})
        summary=interface_tours.summary(p,quest)
        self.assertFalse(summary['completed'])
        self.assertFalse(summary['required'])
        self.assertTrue(p.progress[interface_tours.KEY][quest['id']]['satisfied'])
        self.assertTrue(self.complete(p,quest).startswith('Quest complete.'))

    def test_finished_dawnwatch_lesson_still_requires_its_authored_turn_in_room(self):
        quest=next(q for q in self.heads if q['id']=='first_steps_good_guys_1__step_01')
        p=self.new_player(quest);self.finish(p,quest);p.location='emberhollow_square'
        before=self.payout_snapshot(p)
        self.assertEqual('Turn this in at Dawnwatch Gilded Tankard.',self.complete(p,quest))
        self.assertEqual('active',p.progress['quests'][quest['id']])
        self.assertEqual(before,self.payout_snapshot(p))

    def test_all_eight_alternative_paths_keep_one_shared_reward(self):
        for quest in self.heads:
            with self.subTest(quest=quest['id']):
                p=self.new_player(quest);alternative=self.world.quests[quest_alternatives.reference(quest)]
                proposal=quest_alternatives.preview(self.world,p,quest['id'])
                self.assertTrue(proposal['available'],proposal['reason'])
                before=self.payout_snapshot(p)
                quest_alternatives.choose(self.world,p,quest['id'],proposal['revision'])
                self.assertEqual(before,self.payout_snapshot(p))
                # Finishing the now-optional guide cannot bypass the choice.
                interface_tours.handle(self.world,p,{'action':'resume','quest_id':quest['id']})
                self.finish(p,quest)
                self.assertFalse(self.complete(p,quest).startswith('Quest complete.'))
                self.assertEqual(before,self.payout_snapshot(p))
                for key in alternative.get('actions',{}):
                    self.assertTrue(key.startswith('read:'))
                    _cmd_read(self.ctx(p),key.split(':',1)[1])
                for witness in alternative.get('witnesses',[]):_cmd_read(self.ctx(p),witness['read_item'])
                self.assertTrue(self.complete(p,alternative).startswith('Quest complete.'))
                self.assertEqual('complete',p.progress['quests'][quest['id']])
                paid=self.payout_snapshot(p)
                for member in (quest,alternative):self.assertFalse(self.complete(p,member).startswith('Quest complete.'))
                self.assertEqual(paid,self.payout_snapshot(p))

if __name__=='__main__':unittest.main()
