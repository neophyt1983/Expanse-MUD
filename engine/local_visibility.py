"""Nearby sight from real open edges; night dims terrain, never removes exits."""
import math
from engine.mapping import VECTORS, adjacent_step
from engine.visual_mapping import room_style, crosses_seam
from engine import frontiers, worldtime, locks, geology_impacts


def has_light(world,player):
    from engine import spell_utility
    if spell_utility.light(world,player):return True
    durability=player.progress.get('durability',{})
    for iid in set(player.inventory)|set(player.equipped.values()):
        item=world.items.get(iid,{})
        if item.get('light_source') is True:
            value=durability.get(iid,100) if isinstance(durability,dict) else None
            if type(value) in (int,float) and math.isfinite(value) and value>0:return True
    return False


def sight(world,player,compiled):
    byid,positions,_=compiled;center=player.location
    minute=(getattr(world,'living_state',{}) or {}).get('minute',worldtime.initial_minute(world.metadata))
    daylight=worldtime.date(minute,world.metadata.get('sunrise_minute',375))['daylight']
    light=has_light(world,player)
    radius=world.metadata.get('local_sight_tiles',6)
    if type(radius) is not int:radius=6
    radius=max(1,min(16,radius))
    result={'rooms':set(),'daylight':daylight,'light_source':light,'radius':radius}
    if center not in byid:return result
    from engine.travel_window import window
    tiles=window(world,player,compiled,[radius,radius],require_open=True)
    cells={(t['dx'],t['dy']):t['id'] for t in tiles}
    lock_index=locks.index(world)
    hazards=geology_impacts.route_sources(world)
    boat=any(world.items.get(item,{}).get('boat') for item in player.inventory)
    checked={}

    def edge(a,b):
        if (a,b) in checked:
            return checked[a,b]
        src,dst=cells.get(a),cells.get(b)
        if src is None or dst is None:
            return False
        exits=world.rooms[src].exits
        detailed=(src in hazards or src in lock_index or world.room_details.get(src,{}).get('gates')
                  or world.room_details.get(dst,{}).get('property_unit_id'))
        displacement=(b[0]-a[0],b[1]-a[1],0)
        checked[a,b]=any(target==dst and adjacent_step(byid,positions,src,direction,dst)==displacement
                        and not frontiers.path_blocked(world,src,direction,dst,player,detailed,lock_index,hazards,boat)
                        for direction,target in exits.items())
        return checked[a,b]

    def in_view(x,y):
        steps=max(abs(x),abs(y))
        a=(0,0)
        for step in range(1,steps+1):
            b=(round(x*step/steps),round(y*step/steps))
            if a[0]!=b[0] and a[1]!=b[1]:
                horizontal,vertical=(b[0],a[1]),(a[0],b[1])
                if not (edge(a,horizontal) and edge(horizontal,b) and edge(a,vertical) and edge(vertical,b)):
                    # An explicitly surveyed diagonal corridor can stand alone.
                    if horizontal in cells or vertical in cells or not edge(a,b):
                        return False
            elif not edge(a,b):
                return False
            a=b
        return True

    cx,cy,cz=positions[center]
    result['positions']={rid:(cx+x,cy+y,cz) for (x,y),rid in cells.items() if in_view(x,y)}
    result['rooms']=set(result['positions'])-{center}
    return result


def validate(data):
    return [str(row.get('id'))+': light_source must be boolean' for row in data.get('item',[]) if 'light_source' in row and type(row['light_source']) is not bool]


def known_facades(world,player,compiled,view):
    if not view['radius']:return set()
    rows,pos,_=compiled;c=player.location;origin=pos[c]
    if (rows[c].get('_visual_style') or room_style(rows[c]))[0]!='outdoors':return set()
    visited=set(player.explored_rooms);result=set()
    for direction,target in world.rooms[c].exits.items():
        if target not in visited or target not in rows or ("approach "+direction) in world.rooms[c].exits:continue
        xyz=pos[target]
        if xyz[2]!=origin[2] or max(abs(xyz[0]-origin[0]),abs(xyz[1]-origin[1]))>1:continue
        if world.rooms[target].map_visibility=='hidden' or frontiers.blocked(world,c,direction,player):continue
        if (rows[target].get('_visual_style') or room_style(rows[target]))[0]=='building':result.add(target)
    return result


def blind(world,player):
    """Compatibility hook: ordinary night is dim visibility, not blindness.

    Real exits and learned guidance stay usable at night. Retained for callers
    and older extensions; a future explicit blindness condition needs its own
    rules rather than treating sunset as loss of all route information.
    """
    return False


def conceal_routes(packet):
    """Withhold live exit geometry, not remembered locations or attempted results."""
    packet['blind_navigation']=True
    packet['exits']=[]
    packet['waymarks']=[]
    visual=packet.get('visual',{})
    visual['exits']=[];visual['links']=[]
    for tile in visual.get('tiles',[]):
        tile.pop('route_surface',None)
        if isinstance(tile.get('impacts'),dict):
            tile['impacts'].pop('routes',None)
            tile['impacts'].pop('port_routes',None)
    packet['caption']='@ you. Darkness hides exits; try a direction or use a working lantern.'
    return packet
