#!/usr/bin/env python3
"""Audit authored room cells and the actual runtime street/building projection.

This is creator-side tooling: its report includes undiscovered locations and
must never be served as a player's knowledge or navigation packet.
"""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def authored_world(data, metadata):
    from engine.core import Room, World
    world=World();world.metadata=deepcopy(metadata);world.rules={}
    world.room_details={r['id']:r for r in data['rooms']}
    world.buildings={b['id']:b for b in data.get('buildings',[])}
    for row in data['rooms']:
        world.add_room(Room(row['id'],row.get('name',row['id']),row.get('description',''),
                            dict(row.get('exits',{})),group=row.get('group'),
                            **{k:row[k] for k in ('map_x','map_y','map_z','map_visibility') if k in row}))
    return world


def repair_authored(data, metadata):
    """Persist only the narrowly identified legacy civic-coordinate repair."""
    from engine import civic_layout
    world=authored_world(data,metadata)
    return civic_layout.repair(world)


def audit(data, metadata):
    from engine import streets
    from engine.visual_mapping import room_style
    world=authored_world(deepcopy(data),metadata)
    source=set(world.rooms);points=defaultdict(list);issues=[]
    for rid,room in world.rooms.items():
        point=(room.map_x,room.map_y,room.map_z)
        if all(type(n) is int for n in point):points[point].append(rid)
        else:issues.append(dict(kind='unsurveyed',room=rid))
        for direction,target in room.exits.items():
            if target not in source:issues.append(dict(kind='missing_exit_target',room=rid,direction=direction,target=target))
    collisions=[dict(point=list(point),rooms=rooms) for point,rooms in points.items() if len(rooms)>1]
    issues.extend(dict(kind='room_cell_collision',**row) for row in collisions)
    membership={}
    for bid,b in world.buildings.items():
        if not b.get('rooms'):issues.append(dict(kind='empty_building',building=bid))
        for rid in b.get('rooms',[]):
            if rid not in source:issues.append(dict(kind='missing_building_room',building=bid,room=rid))
            membership.setdefault(rid,bid)
    streets.install(world)
    origins=world._street_origins
    roofs=defaultdict(set)
    for ext,rid in origins.items():
        if rid not in source:issues.append(dict(kind='phantom_roof',frontage=ext,room=rid));continue
        roof=world.rooms[ext]
        roofs[membership.get(rid,rid)].add((roof.map_x,roof.map_y))
    buildings=[]
    for bid,b in world.buildings.items():
        floors=defaultdict(list);indoor=[];outdoor=[]
        for rid in dict.fromkeys(b.get('rooms',[])):
            if rid not in source:continue
            row={**world.room_details[rid], '_visual_building':{'id':membership.get(rid,bid)}}
            room=world.rooms[rid]
            if room_style(row)[0]=='building':
                floors[room.map_z].append((rid,room.map_x,room.map_y));indoor.append(rid)
            else:outdoor.append(rid)
        floor_rows=[]
        for floor,rooms in sorted(floors.items()):
            distinct={(x,y) for _,x,y in rooms}
            floor_rows.append(dict(floor=floor,rooms=len(rooms),cells=len(distinct)))
            if len(distinct)!=len(rooms):issues.append(dict(kind='building_floor_overlap',building=bid,floor=floor,rooms=[r for r,_,_ in rooms]))
        # Basement-only buildings legitimately have no roof on the zero plane.
        # Mixed storeys share XY cells; courtyards are not included in the roof.
        ground=b.get('street_level',min(floors,default=0))
        expected={(world.rooms[r].map_x,world.rooms[r].map_y) for r in indoor
                  if membership.get(r)==bid and world.rooms[r].map_z>=ground}
        if ground>=0:
            missing=expected-roofs.get(bid,set())
            if missing:issues.append(dict(kind='missing_building_roof_cells',building=bid,cells=[list(p) for p in sorted(missing)]))
        buildings.append(dict(id=bid,name=b.get('name',bid),rooms=len(indoor),open_rooms=len(outdoor),
                              floors=floor_rows,roof_cells=len(roofs.get(bid,set()))))
    return dict(authored_rooms=len(source),authored_buildings=len(world.buildings),
                generated_frontages=len(origins),civic_repaired_rooms=len(getattr(world,'_civic_layout_report',[])),
                source_cell_collisions=len(collisions),issues=issues,buildings=buildings,
                scope='Authored topology and actual runtime footprint rules; visibility remains character-specific.')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--world',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    data={key:json.loads((args.world/(key+'.json')).read_text()) for key in ('rooms','buildings')}
    report=audit(data,json.loads((args.world/'metadata.json').read_text()))
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key not in ('buildings','issues')}|{'issues':len(report['issues'])}))
    raise SystemExit(bool(report['issues']))
