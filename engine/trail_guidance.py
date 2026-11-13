"""Authored trail hints, without adding geography or revealing remote contents."""
from engine import frontiers, local_visibility, locks


def marks(room,key):
    value=room.get(key)
    return value if isinstance(value,dict) else {}


def marked(details,rid,direction,dest):
    here=details.get(rid,{})
    if direction in marks(here,'waymarks') and here.get('route_surface'):return True
    if here.get('route_surface') and details.get(dest,{}).get('route_surface'):return True
    return here.get('environment')=='road' and details.get(dest,{}).get('environment')=='road'


def signs(world,player):
    """Only signs in this room; their text is authored, not remote room metadata."""
    if player.location not in world.rooms or local_visibility.blind(world,player):return []
    details=getattr(world,'room_details',{})
    explicit={**marks(details.get(player.location,{}),'trail_signs'),
              **marks(details.get(player.location,{}),'waymarks')}
    room=world.rooms[player.location]
    index=locks.index(world,cache=False) if explicit else {}
    rows=[]
    for direction,dest in room.exits.items():
        label=explicit.get(direction)
        if dest not in world.rooms or not isinstance(label,str) or not label.strip():continue
        reason=frontiers.blocked(world,player.location,direction,player,lock_index=index)
        boat_required=details.get(dest,{}).get('requires_boat')
        boat=any(world.items.get(i,{}).get('boat') for i in player.inventory) if boat_required else True
        rows.append(dict(direction=direction,label=label,closed=bool(reason) or not boat))
    return rows
