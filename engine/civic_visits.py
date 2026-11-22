"""Resolve a doorstep visit from a single opening register, on the world host."""
import json
import re
from pathlib import Path

from engine.core import Entity

COURT = re.compile(r'gen_(?:dawn|hollow|hearth|reed|cinder|glass|pine|star)_lane_[1-9][0-9]{0,2}')


def residents(world, court):
    if not COURT.fullmatch(str(court)) or court not in world.rooms:
        return ()
    path = Path(world.game_dir) / 'assets' / 'chronicles' / (court + '.json')
    if not path.is_file() or path.stat().st_size > 100000:
        return ()
    rows = json.loads(path.read_bytes())
    return [row for row in rows if row.get('home') == court]


def definition(world, row):
    return dict(id=row['id'], name=row['name'], home_room=row['home'],
                workplace_room=row['work'], group=world.rooms[row['home']].group,
                occupation=row['occupation'], hp=22, attack=2, defense=1, gold=0,
                spawn_managed=True, social_profile={'sentient': True},
                description=f"{row['name']} lives at door {row['door']} and works as a {row['occupation']}.")


def restore_definitions(world, ledger):
    for court, ids in ledger.items():
        for row in residents(world, court):
            if row['id'] in ids:
                world.npcs.setdefault(row['id'], definition(world, row))


def knock(ctx, args):
    world = ctx.world
    court = ctx.player.location
    rows = residents(world, court)
    if not rows:
        return 'There is no household roll at this address.'
    parts = args.split(maxsplit=1)
    if not parts or not parts[0].isascii() or not parts[0].isdigit() or len(parts[0])>2:
        return 'Use knock <door number> [resident name]. Read the Court Roll for names.'
    household = [r for r in rows if r['door'] == int(parts[0])]
    if len(parts)==2:
        household = [r for r in household if r['name'].casefold()==parts[1].casefold()]
    if not household:
        return 'No one by that description is listed at this door.'
    from engine import living
    ledger = living.state(world).setdefault('civic_visits_v1',{}).setdefault(court,[])
    for row in household:
        uid = row['id']
        actor = world.entities.get('npc:'+uid)
        if actor is None and uid not in world.killed_npcs and uid not in ledger and uid not in world.npcs:
            d = definition(world,row)
            actor = Entity(id='npc:'+uid,name=row['name'],hp=22,max_hp=22,attack=2,defense=1,
                           source_def=uid,group_id=d['group'],description=d['description'])
            world.npcs[uid]=d
            world.add_entity(actor,court)
            ledger.append(uid)
        if actor and actor.alive and actor.location==court:
            return f"{actor.name} answers the door. You can speak to {actor.name} here."
    return 'There is no answer at this door.'
