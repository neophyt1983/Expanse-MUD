"""Public carriage props stay at their stand; the scheduled trip stays atomic."""
from copy import deepcopy
import unittest

from engine import civic_program, costumes, living, mortality
from engine.commands import CommandContext
from engine.core import Entity, Room, World
from engine.visual_mapping import actor_portrait


def fixture(*, traffic=False):
    world=World()
    world.metadata={'living_world':True,'society':True,'press_editions':[
        {'kind':'town','name':'Dawnwatch','home':'stand'},
        {'kind':'town','name':'Hearthmere','home':'arrival'}]}
    world.rules={};world.room_details={};world.living_state={'minute':478}
    for rid,name,exits in [('stand','Dawnwatch Civic Square',{'east':'lane'}),
                           ('lane','Town Lane',{'west':'stand'}),
                           ('arrival','Hearthmere Square',{})]:
        world.add_room(Room(rid,name,'Test location.',exits))
        world.room_details[rid]={'environment':'road'}
    definition={'id':'town_carriage','name':'Town Carriage','spawn_room':'stand',
                'patrol_route':['stand','lane'],'social_profile':{'sentient':False},
                'traffic':{'enabled':traffic,'accident_chance':1,'damage':12}}
    world.npcs[definition['id']]=definition
    carriage=Entity('npc:town_carriage','Town Carriage',50,50,0,0,source_def=definition['id'])
    player=Entity('traveller','Traveller',50,50,0,0,gold=10,is_player=True)
    world.add_entity(carriage,'stand');world.add_entity(player,'stand')
    return world,player,carriage


def book(world,player,destination='Hearthmere'):
    return civic_program.command(CommandContext(world,player,world.rooms[player.location]),destination,'carriage')


class CarriageServiceTests(unittest.TestCase):
    def test_carriage_holds_at_its_authored_stand_while_the_trip_runs_once(self):
        world,player,carriage=fixture()
        definitions=deepcopy((world.npcs,world.metadata,world.room_details))
        text=book(world,player)
        for phrase in ('Dawnwatch Civic Square','Hearthmere Square','08:00','2 game minutes',
                       'Arrive directly','leaving cancels','2 gold'):
            self.assertIn(phrase,text)
        living.advance(world,1)
        self.assertEqual((carriage.location,player.location,player.gold),('stand','stand',10))
        self.assertIn('1 game minute',civic_program.view(world,player)[0]['detail'])
        living.advance(world,1)
        self.assertEqual((carriage.location,player.location,player.gold),('stand','arrival',8))
        self.assertEqual(player.explored_rooms,['arrival'])
        self.assertIn('Dawnwatch Civic Square and reaches Hearthmere Square',world.rest_notifications[0][1])
        living.advance(world,5)
        self.assertEqual((carriage.location,player.location,player.gold),('stand','arrival',8))
        self.assertEqual(len(world.rest_notifications),1)
        self.assertNotIn(player.id,civic_program.state(world)['tickets'])
        self.assertEqual((world.npcs,world.metadata,world.room_details),definitions)

    def test_an_old_wandering_service_prop_returns_without_moving_the_player(self):
        world,player,carriage=fixture()
        world.move_entity(carriage.id,'lane')
        world._commute_routes={carriage.id:('lane',['stand'])}
        living.advance(world,1)
        self.assertEqual(carriage.location,'stand')
        self.assertEqual(player.location,'stand')
        self.assertNotIn(carriage.id,world._commute_routes)
        actor=actor_portrait(world,carriage,player.id)
        self.assertEqual(actor['subject'],'carriage')
        self.assertTrue(actor['stationary'])
        self.assertEqual(actor['activity']['label'],'Waiting at the carriage stand')
        nearby=costumes.distant_portrait(actor)
        self.assertTrue(nearby['stationary'])
        self.assertNotIn('id',nearby)

    def test_only_a_public_service_carriage_is_held(self):
        for ident,spawn in [('merchant_cart','stand'),('road_carriage','lane')]:
            with self.subTest(ident=ident):
                world,player,carriage=fixture()
                definition=world.npcs.pop(carriage.source_def)
                definition.update(id=ident,spawn_room=spawn)
                world.npcs[ident]=definition;carriage.source_def=ident
                self.assertIsNone(civic_program.carriage_stop(world,carriage))
                living.advance(world,1)
                self.assertEqual(carriage.location,'lane')
                self.assertNotIn('stationary',actor_portrait(world,carriage,player.id))

    def test_parked_service_is_not_a_traffic_collision_or_warning(self):
        world,player,carriage=fixture(traffic=True)
        self.assertEqual(mortality.advance(world,rng=lambda:0),[])
        self.assertEqual(player.hp,50)
        self.assertNotIn('traffic',living.on_entry(world,player).lower())
        # Renaming the source to an ordinary cart preserves its authored hazard.
        world.npcs['merchant_cart']={**world.npcs[carriage.source_def],'id':'merchant_cart'}
        carriage.source_def='merchant_cart';world.living_state['minute']+=1
        messages=mortality.advance(world,rng=lambda:0)
        self.assertEqual(player.hp,38)
        self.assertIn('runs into',messages[0][1])
        self.assertIn('traffic',living.on_entry(world,player).lower())

    def test_leaving_or_cancelling_never_moves_or_charges_the_passenger(self):
        for action in ('leave','leave-and-return','cancel'):
            with self.subTest(action=action):
                world,player,carriage=fixture();book(world,player)
                if action.startswith('leave'):
                    world.move_entity(player.id,'lane')
                    self.assertNotIn(player.id,civic_program.state(world)['tickets'])
                    if action=='leave-and-return':world.move_entity(player.id,'stand')
                else:book(world,player,'cancel')
                before=player.location
                living.advance(world,2)
                self.assertEqual(player.location,before)
                self.assertEqual(player.gold,10)
                self.assertEqual(carriage.location,'stand')
                self.assertFalse(getattr(world,'rest_notifications',[]))

    def test_failed_eligibility_never_collects_a_fare(self):
        for blocked in ('restrained','unaffordable','asleep'):
            with self.subTest(blocked=blocked):
                world,player,carriage=fixture();book(world,player)
                if blocked=='restrained':player.progress['restrained_until']=500
                elif blocked=='unaffordable':player.gold=1
                else:player.progress['player_rest']={'state':'active','kind':'sleeping'}
                gold=player.gold
                world.living_state['minute']=480
                civic_program.advance(world,478,480)
                self.assertEqual(player.location,'stand')
                self.assertEqual(player.gold,gold)
                self.assertIn('No fare was collected',world.rest_notifications[0][1])

    def test_late_booking_keeps_the_existing_next_day_departure(self):
        world,player,carriage=fixture();world.living_state['minute']=1200
        book(world,player)
        due=civic_program.state(world)['tickets'][player.id]['time']
        self.assertEqual(due,civic_program.DAY+420)
        self.assertIn(str(due-1200)+' game minutes',civic_program.view(world,player)[0]['detail'])
        world.living_state['minute']=due-1
        civic_program.advance(world,1200,due-1)
        self.assertEqual((player.location,player.gold),('stand',10))
        world.living_state['minute']=due
        civic_program.advance(world,due-1,due)
        self.assertEqual((player.location,player.gold),('arrival',8))


if __name__=='__main__':unittest.main()
