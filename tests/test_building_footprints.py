"""N real rooms occupy N surveyed cells on their floor, with real frontages."""
from copy import deepcopy
import unittest

from engine import civic_layout, streets, locks
from engine.core import Entity, Room, World
from engine.mapping import compile_map, room_records, geometry_revision
from engine.local_visibility import sight
from engine.travel_window import window
from test_interior_room_visibility import interior_world, projection, tile_ids


def add(world,ident,point,exits=None,environment='interior',**extra):
    x,y,z=point
    row=dict(id=ident,name=ident,environment=environment,map_x=x,map_y=y,map_z=z,
             exits=dict(exits or {}),world_region='test-region',**extra)
    world.room_details[ident]=row
    world.add_room(Room(ident,ident,'',row['exits'],map_x=x,map_y=y,map_z=z,
                        map_visibility=row.get('map_visibility','discovered')))


def floor_world(points,ground=0):
    world=World();world.metadata={};world.rules={};world.room_details={}
    add(world,'street',(-3,0,ground),environment='road')
    for n,point in enumerate(points):add(world,'r'+str(n),point,{'out':'street'} if n==0 else {})
    world.rooms['street'].exits['in']='r0'
    world.buildings={'house':dict(id='house',name='Real house',rooms=['r'+str(n) for n in range(len(points))],street_level=ground)}
    return world


class BuildingFootprintTests(unittest.TestCase):
    def test_one_two_and_l_shaped_three_room_plans_never_invent_floor_cells(self):
        for points in ([(0,0,0)],[(0,0,0),(1,0,0)],[(0,0,0),(1,0,0),(1,1,0)]):
            world=floor_world(points);streets.install(world)
            surfaces={(world.rooms[r].map_x,world.rooms[r].map_y,world.rooms[r].map_z)
                      for r in world._street_origins}
            self.assertEqual(surfaces,set(points))
            self.assertEqual(len(world._street_origins),len(points))
            self.assertEqual([(world.rooms['r'+str(n)].map_x,world.rooms['r'+str(n)].map_y,
                               world.rooms['r'+str(n)].map_z) for n in range(len(points))],points)

    def test_true_storeys_stack_and_open_courtyard_stays_unroofed(self):
        points=[(0,0,0),(1,0,0),(0,0,1),(1,0,1)]
        world=floor_world(points)
        add(world,'courtyard',(1,1,0),environment='road')
        world.buildings['house']['rooms'].append('courtyard')
        streets.install(world)
        self.assertEqual(len(world._street_origins),2)
        self.assertNotIn('courtyard',world._street_origins.values())
        self.assertEqual(len({(r.map_x,r.map_y,r.map_z) for r in world.rooms.values() if r.id.startswith('r')}),4)

    def test_real_underground_city_uses_its_own_street_floor(self):
        world=floor_world([(0,0,-1),(1,0,-1),(0,0,0)],ground=-1)
        streets.install(world)
        self.assertEqual(len(world._street_origins),2)
        self.assertEqual({world.rooms[r].map_z for r in world._street_origins},{-1})

    def test_independent_buildings_do_not_share_roof_cells_and_each_shape_is_preserved(self):
        world=floor_world([(0,0,0),(1,0,0)])
        add(world,'other_a',(1,0,0));add(world,'other_b',(2,0,0))
        world.buildings['other']=dict(id='other',rooms=['other_a','other_b'])
        streets.install(world)
        footprints=[(world.rooms[r].map_x,world.rooms[r].map_y) for r in world._street_origins]
        self.assertEqual(len(footprints),len(set(footprints)))
        self.assertEqual(world.rooms['other_b'].map_x-world.rooms['other_a'].map_x,1)
        self.assertEqual(world.rooms['other_b'].map_y,world.rooms['other_a'].map_y)

    def test_legacy_civic_floor_repair_preserves_room_identity_exits_and_progress(self):
        world=World();world.metadata={'name':'Expanse Wild Lands 1.9.16'};world.rules={};world.room_details={}
        add(world,'street',(0,0,0),{'police':'station'},environment='road')
        add(world,'inn',(1,0,0),{'out':'street'})
        add(world,'station',(1,0,104),{'out':'street','jail':'jail','up':'barracks'})
        add(world,'jail',(2,0,84),{'station':'station'},locks=[{'id':'cell','direction':'station','locked':True}])
        add(world,'barracks',(1,0,105),{'down':'station'})
        world.buildings={'civic_test_police_building':dict(id='civic_test_police_building',location='station',rooms=['station','jail','barracks'])}
        actor=Entity('prisoner','Prisoner',20,20,2,2,location='jail',progress={'sentence':55})
        world.entities[actor.id]=actor
        before=deepcopy((actor,world.room_details['jail']['locks'],{r:dict(v.exits) for r,v in world.rooms.items()}))
        report=civic_layout.repair(world)
        self.assertEqual(len(report),3)
        self.assertEqual((world.rooms['station'].map_z,world.rooms['jail'].map_z,world.rooms['barracks'].map_z),(0,0,1))
        self.assertEqual((world.rooms['inn'].map_x,world.rooms['inn'].map_y,world.rooms['inn'].map_z),(1,0,0))
        self.assertEqual(len({(r.map_x,r.map_y,r.map_z) for r in world.rooms.values()}),len(world.rooms))
        self.assertEqual(before,(actor,world.room_details['jail']['locks'],{r:dict(v.exits) for r,v in world.rooms.items()}))
        coords=[(r.map_x,r.map_y,r.map_z) for r in world.rooms.values()]
        self.assertEqual(civic_layout.repair(world),report)
        self.assertEqual(coords,[(r.map_x,r.map_y,r.map_z) for r in world.rooms.values()])

    def test_other_authored_worlds_keep_their_deliberate_high_floors(self):
        world=floor_world([(0,0,80)]);world.metadata={'name':'A genuine sky city'}
        before=deepcopy(world.room_details)
        self.assertEqual(civic_layout.repair(world),[])
        self.assertEqual(world.room_details,before)

    def test_named_adjacent_door_is_visible_from_each_room_and_actual_lock_still_blocks(self):
        world,actor,_=interior_world('house','house')
        world.rooms['hall'].exits['archway']=world.rooms['hall'].exits.pop('east')
        world.rooms['chamber'].exits['hall door']=world.rooms['chamber'].exits.pop('west')
        compiled=compile_map(room_records(world))
        for origin in ('hall','chamber'):
            actor.location=origin
            self.assertEqual(tile_ids(window(world,actor,compiled,[4,4])),{'hall','chamber'})
            self.assertEqual(tile_ids(projection(world,actor,compiled)['tiles']),{'hall','chamber'})
        world.room_details['hall']['locks']=[{'id':'archway-lock','direction':'archway','locked':True}]
        locks.invalidate(world)
        compiled=compile_map(room_records(world))
        for origin in ('hall','chamber'):
            actor.location=origin
            self.assertEqual(tile_ids(window(world,actor,compiled,[4,4])),{origin})
            self.assertEqual(sight(world,actor,compiled)['rooms'],set())

    def test_geometry_revision_changes_only_when_map_geometry_is_recompiled(self):
        world,actor,compiled=interior_world()
        first=geometry_revision(world,compiled)
        self.assertEqual(geometry_revision(world,compiled),first)
        world.rooms['chamber'].map_x=3
        updated=compile_map(room_records(world))
        self.assertGreater(geometry_revision(world,updated),first)


if __name__=='__main__':unittest.main()
