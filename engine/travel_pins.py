"""Private saved destinations, authorized by physical visit history only.

Pins never move an actor, learn a room, fabricate coordinates, or plan through
unvisited rooms. Progress is saved by the normal per-player transaction path.
"""
import re
import unicodedata
import uuid
from collections import deque
from engine import local_visibility, frontiers

MAX_PINS = 50
MAX_NAME = 80
_ID = re.compile(r'[0-9a-f]{32}\Z')


def has_visited(world, player, rid):
    if not isinstance(rid,str):return False
    history=player.explored_rooms if isinstance(player.explored_rooms,list) else []
    return rid in world.rooms and (rid==player.location or rid in history)


def visited(world, player):
    # Bounded identities already referenced by history/pins; never enumerate all
    # discovered chunks or treat nonresidency as deletion.
    history=player.explored_rooms if isinstance(player.explored_rooms,list) else []
    return {rid for rid in history if has_visited(world,player,rid)} | ({player.location} if has_visited(world,player,player.location) else set())


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value)>MAX_NAME or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Use a pin name of 1–80 characters without control characters.')
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('Choose one of your saved travel pins.')
    return value


def records(world, player):
    """Validate saved progress again; stale or corrupt entries never leak rooms."""
    raw=player.progress.get('travel_pins',[])
    if not isinstance(raw,list):return []
    result=[];ids=set();rooms=set()
    for row in raw[:MAX_PINS]:
        if not isinstance(row,dict):continue
        rid=row.get('room_id')
        if not isinstance(rid,str) or not has_visited(world,player,rid) or rid in rooms:continue
        try:pid=_id(row.get('id'));name=_name(row.get('name'))
        except ValueError:continue
        if pid in ids:continue
        ids.add(pid);rooms.add(rid);result.append(dict(id=pid,name=name,room_id=rid))
    return result


def _selected(player, rows):
    selected=player.progress.get('selected_travel_pin')
    return next((row for row in rows if row['id']==selected),None)


def guidance(world, player, row):
    if row is None or not has_visited(world,player,row['room_id']):return None
    target=row['room_id'];result=dict(id=row['id'],name=row['name'],target=dict(id=target,name=world.rooms[target].name if target in world.rooms else 'Visited surface location'),direction=None,status='unknown')
    if player.location==target:result['status']='here';return result
    if local_visibility.blind(world,player):result['status']='dark';return result
    allowed=visited(world,player);seen={player.location};queue=deque([(player.location,None)])
    while queue:
        rid,first=queue.popleft()
        if rid==target:result.update(direction=first,status='travel');return result
        room=world.rooms.get(rid)
        if room is None:continue
        for direction,dest in room.exits.items():
            # Do not inspect hidden connectors, gate state, or boat needs there.
            if dest not in allowed or dest in seen:continue
            if frontiers.blocked(world,rid,direction,player):continue
            seen.add(dest);queue.append((dest,first or direction))
    # No distinction between disconnected/unknown/closed routes is exposed.
    return result


def projection(world, player):
    from engine.navigation import pin
    rows=records(world,player);allowed={row['room_id'] for row in rows};chosen=_selected(player,rows)
    return dict(travel_pins=[dict(**row,location=pin(world,player,row['room_id'],_known=allowed)) for row in rows],
                selected_travel_pin=chosen['id'] if chosen else None,
                travel_guidance=guidance(world,player,chosen))


def handle(world, player, payload):
    if not player.is_player:raise ValueError('A player session is required.')
    schemas={'list':{'action'},'create':{'action','room_id','name'},'rename':{'action','id','name'},'select':{'action','id'},'clear':{'action'},'remove':{'action','id'}}
    if not isinstance(payload,dict) or not isinstance(payload.get('action'),str) or payload['action'] not in schemas or set(payload)-schemas[payload['action']]:
        raise ValueError('Choose a supported travel-pin action without extra fields.')
    action=payload['action'];rows=records(world,player);chosen=_selected(player,rows);selected=chosen['id'] if chosen else None
    if action=='create':
        rid=payload.get('room_id')
        if not isinstance(rid,str) or len(rid)>256 or not has_visited(world,player,rid):
            raise ValueError('Travel pins must be somewhere you have personally visited.')
        if any(row['room_id']==rid for row in rows):raise ValueError('You already have a pin at that location.')
        if len(rows)>=MAX_PINS:raise ValueError('Keep at most 50 travel pins. Remove one first.')
        default=''.join(c if not unicodedata.category(c).startswith('C') else ' ' for c in (world.rooms[rid].name if rid in world.rooms else 'Visited surface location'))[:MAX_NAME].strip() or 'Visited location'
        rows.append(dict(id=uuid.uuid4().hex,name=_name(payload.get('name',default)),room_id=rid))
    elif action in ('rename','select','remove'):
        pid=_id(payload.get('id'));row=next((r for r in rows if r['id']==pid),None)
        if row is None:raise ValueError('Choose one of your saved travel pins at a visited location.')
        if action=='rename':row['name']=_name(payload.get('name'))
        elif action=='select':
            selected=pid
            player.progress.pop('globe_destination',None)
        else:
            rows.remove(row)
            if selected==pid:selected=None
    elif action=='clear':selected=None
    if action!='list':
        player.progress['travel_pins']=rows;player.progress['selected_travel_pin']=selected
        if not hasattr(world,'dirty_players'):world.dirty_players=set()
        world.dirty_players.add(player.id)
    return projection(world,player)
