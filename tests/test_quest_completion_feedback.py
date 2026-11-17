"""Journal turn-in explanations use the same rules as ordinary completion."""
from copy import deepcopy
import unittest

from engine import interface_tours, living
from engine.commands import CommandContext
from engine.core import Entity, Room, World
from server import player_ui


def fixture():
    w=World();w.metadata={'living_world':True,'society':False};w.rules={}
    w.living_state={'minute':480};w.room_details={'inn':{},'square':{}}
    w.add_room(Room('inn','Travellers Inn','A public meeting place.',exits={'out':'square'}))
    w.add_room(Room('square','Civic Square','A road.',exits={'in':'inn'}))
    w.items={'grain':{'id':'grain','name':'Grain','description':'Food grain.'}}
    q={'id':'job','name':'Local job','description':'Help locally.','offer_room':'inn','turn_in_room':'inn'}
    w.quests={'job':q}
    p=Entity('traveller','Traveller',20,20,1,1,is_player=True,location='inn',
             progress={'quests':{'job':'active'},'knowledge':{'version':1,'rooms':['inn','square']}})
    w.entities[p.id]=p;w.rooms['inn'].entities.append(p.id)
    return w,p,q


def quest_row(w,p):
    packet=player_ui.list_packet(w,p,'quests')
    return next(row for group in packet['groups'] for row in group['children'] if row['id']=='job')


class QuestCompletionFeedback(unittest.TestCase):
    def test_objective_failures_match_command_and_remain_visible(self):
        cases=[
            ({'required_items':{'grain':2}},'Missing ingredients: Grain × 2'),
            ({'kills':{'wolf':1}},'Combat objectives are incomplete.'),
            ({'visit_rooms':['square']},'Exploration objectives are incomplete.'),
            ({'actions':{'look':1}},'Activity objectives are incomplete.'),
            ({'talk_to':['keeper']},'Speak to the required witnesses first.'),
            ({'witnesses':[{'npc':'keeper','read_item':'ledger'}]},'Record the required witnesses or read their filed statements first.'),
            ({'escort':{'mode':'follow','npc':'guide','destination':'inn'}},'Arrive together with your quest companion first.'),
        ]
        for extra,expected in cases:
            with self.subTest(extra=extra):
                w,p,q=fixture();q.update(extra)
                self.assertEqual(expected,living.quest_completion_blocked(w,p,q))
                before=(p.gold,list(p.inventory),p.location)
                self.assertEqual(expected,living.quest_command(CommandContext(w,p,w.rooms[p.location]),'job','complete'))
                self.assertEqual(before,(p.gold,list(p.inventory),p.location))
                # The journal uses this same reason for all these conditions.
                if 'escort' not in extra:
                    row=quest_row(w,p)
                    self.assertEqual(expected,next(x['detail'] for x in row['children'] if x['id']=='turn-in-status'))

    def test_wrong_location_is_explicit_inside_journal(self):
        w,p,q=fixture();p.location='square'
        reason='Turn this in at Travellers Inn.'
        row=quest_row(w,p)
        self.assertEqual(reason,next(x['detail'] for x in row['children'] if x['id']=='turn-in-status'))
        self.assertEqual(reason,living.quest_command(CommandContext(w,p,w.rooms['square']),'job','complete'))

    def test_finished_guide_ready_here_and_turn_in_elsewhere_are_distinct(self):
        w,p,q=fixture()
        q['interface_tour']={'version':1,'title':'Interface lesson','steps':[
            {'id':'map','target':'map','title':'Map','text':'Read the map.'}]}
        interface_tours.begin(w,p,q)
        pending=quest_row(w,p)
        self.assertIn('Finish the interface guide',next(x['detail'] for x in pending['children'] if x['id']=='turn-in-status'))
        p.progress[interface_tours.KEY]['job']['acknowledged']=['map']
        before=deepcopy(p.progress)
        row=quest_row(w,p)
        self.assertIn('Choose Complete',next(x['detail'] for x in row['children'] if x['id']=='interface-guide'))
        self.assertEqual(before.get('interface_tours'),p.progress.get('interface_tours'))
        p.location='square';row=quest_row(w,p)
        self.assertEqual('Guide finished. Turn this in at Travellers Inn.',next(x['detail'] for x in row['children'] if x['id']=='interface-guide'))

    def test_shared_world_outcome_already_completed_is_not_ready(self):
        w,p,q=fixture();q['scope']='world';w.living_state['completed_world']=['job']
        reason='This shared-world outcome has already been completed.'
        self.assertEqual(reason,living.quest_completion_blocked(w,p,q))
        row=quest_row(w,p)
        self.assertEqual(reason,next(x['detail'] for x in row['children'] if x['id']=='turn-in-status'))

if __name__=='__main__':unittest.main(verbosity=2)
