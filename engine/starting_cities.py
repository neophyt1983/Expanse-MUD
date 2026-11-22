"""Server-owned landing addresses, not faction, ancestry, or housing."""
from pathlib import Path

FLAG='starting_city_pilot'
VERSION='wild-lands-public-entry-v1'
MARKER='starting_city_v1'
# Municipal slug, player label, validated authored public landing address and name.
REGISTRY=(
    ('dawnwatch','Dawnwatch','emberhollow_inn','Dawnwatch Gilded Tankard'),
    ('hollowcrown','Hollowcrown','emberhollow_underworld','Hollowcrown Lantern Inn'),
    ('hearthmere','Hearthmere','lw_hearth_inn','Hearthmere Evening Tavern'),
    ('reedwater','Reedwater','lw_reed_inn','Reedwater Evening Tavern'),
    ('cinderhold','Cinderhold','lw_cinder_inn','Cinderhold Evening Tavern'),
    ('glassreach','Glassreach','lw_glass_inn','Glassreach Evening Tavern'),
    ('pinewatch','Pinewatch','lw_pine_inn','Pinewatch Evening Tavern'),
    ('starfall','Starfall','lw_star_inn','Starfall Evening Tavern'),
)


def enabled(w):
    return (Path(str(w.game_dir)).name=='wild_lands' or w.metadata.get('civic_opening_release') == '1.10.0-rc1') and w.metadata.get(FLAG)==VERSION


def available(w):
    from engine import living
    result={}
    for ident,label,room_id,room_name in REGISTRY:
        room=w.rooms.get(room_id)
        data=living.details(w,room_id)
        if (room and room.name==room_name and 'inn' in data.get('facilities',())
            and not any(data.get(key) for key in ('property_unit_id','requires_boat','gates'))
            and any(target in w.rooms for target in room.exits.values())):
            result[ident]=(label,room_id,room_name)
    return result


def option_fields(w,*,supported=False):
    if not supported or not enabled(w):
        return {}
    return dict(choose_starting_city=True,starting_cities=[
        dict(id=ident,name=label,arrival=room_name) for ident,(label,_,room_name) in available(w).items()])


def choice(w,form,*,supported=False):
    if not supported or not enabled(w):
        if 'starting_city' in form:
            raise ValueError('Starting city choice is not available here. Reopen the character form.')
        return None
    value=form.get('starting_city')
    possible=available(w)
    if not possible:
        raise ValueError('No public starting cities are available in this adventure right now.')
    if not isinstance(value,str) or value not in possible:
        raise ValueError('Choose an available starting city from the list. No character was created.')
    return value,possible[value][1]
