"""Real notification delivery keeps speech roles, privacy and legacy packets."""
import json
import unittest

from engine import locks
from engine.core import Entity, Room, World
from server.game_server import GameServer


class Socket:
    def __init__(self):self.sent=[]
    async def send(self, body):self.sent.append(json.loads(body))


def fixture():
    world=World()
    world.metadata={'living_world':True}
    world.rules={}
    world.living_state={'minute':480}
    for rid in ('kitchen','square'):
        world.add_room(Room(rid,rid.title(),'Test room.',{}))
    world.items={'bread':{'name':'Bread'}}
    world.room_details={'kitchen':{'locks':[{'id':'pantry','name':'Pantry cabinet',
                         'locked':False,'owner':'chef','contents':['bread']}]}}
    sockets={}
    for ident,location in [('thief','kitchen'),('bystander','kitchen'),('remote','square')]:
        player=Entity(ident,ident.title(),20,20,2,2,is_player=True,location=location)
        world.entities[ident]=player;world.rooms[location].entities.append(ident)
        sockets[ident]=Socket()
    witness=Entity('arden','Arden Lightbrook',20,20,2,2,source_def='chef',location='kitchen')
    world.npcs['chef']={'social_profile':{'sentient':True}}
    world.entities[witness.id]=witness;world.rooms['kitchen'].entities.append(witness.id)
    server=GameServer.__new__(GameServer)
    server.world=world;server.clients={socket:ident for ident,socket in sockets.items()}
    return world,server,sockets


class ConversationNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_theft_shout_is_delivered_once_with_explicit_npc_emphasis(self):
        world,server,sockets=fixture()
        result=locks.act(world,world.entities['thief'],'take','pantry')
        self.assertIn('You steal',result)
        self.assertNotIn('shouts',result,'The spoken alert has its own styled message.')
        # A prompt arrest can move the thief before notification flush. Their
        # personal warning must still arrive, without broadcasting it remotely.
        world.rooms['kitchen'].entities.remove('thief')
        world.rooms['square'].entities.append('thief')
        world.entities['thief'].location='square'
        await server.flush_notifications()
        self.assertEqual(len(sockets['thief'].sent),1)
        self.assertEqual(len(sockets['bystander'].sent),1)
        self.assertEqual(sockets['remote'].sent,[])
        for ident in ('thief','bystander'):
            packet=sockets[ident].sent[0]
            self.assertEqual(packet['type'],'system','Old clients still receive readable text.')
            self.assertEqual(packet['conversation'],{'role':'npc','emphasis':'shout'})
            self.assertIn('Arden Lightbrook shouts',packet['text'])
            self.assertIn('Pantry cabinet is theft',packet['text'])
        self.assertIn('at you',sockets['thief'].sent[0]['text'])
        self.assertIn('at Thief',sockets['bystander'].sent[0]['text'])
        await server.flush_notifications()
        self.assertEqual(len(sockets['thief'].sent),1)
        self.assertEqual(len(sockets['bystander'].sent),1)

    async def test_ordinary_npc_speech_is_scoped_and_old_system_events_still_work(self):
        world,server,sockets=fixture()
        world.rest_notifications=[('thief','Your sentence is complete.')]
        world.runtime_notifications=[('kitchen','The bell rings.'),
                                     ('kitchen','Arden says hello.',None,{'role':'npc','emphasis':'normal'})]
        await server.flush_notifications()
        self.assertEqual(sockets['thief'].sent[0],{'type':'system','text':'Your sentence is complete.'})
        self.assertEqual(sockets['bystander'].sent[0],{'type':'system','text':'The bell rings.'})
        self.assertEqual(sockets['bystander'].sent[1]['conversation'],{'role':'npc','emphasis':'normal'})
        self.assertEqual(sockets['remote'].sent,[])

    async def test_words_do_not_supply_alert_style_and_unknown_metadata_is_ignored(self):
        world,server,sockets=fixture()
        await server.broadcast_room('kitchen','A sign says SHOUTS and ALERT.')
        await server.broadcast_room('kitchen','Unknown role',conversation={'role':'admin','emphasis':'shout'})
        await server.broadcast_room('kitchen','Ordinary NPC',conversation={'role':'npc','emphasis':'arbitrary-css'})
        packets=sockets['thief'].sent
        self.assertNotIn('conversation',packets[0])
        self.assertNotIn('conversation',packets[1])
        self.assertEqual(packets[2]['conversation'],{'role':'npc','emphasis':'normal'})


if __name__=='__main__':unittest.main()
