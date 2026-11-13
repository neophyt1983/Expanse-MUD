"""Plan click travel only over places the player has walked or can see now."""
from engine import frontiers, local_visibility


def plan(world, player, destination, compiled):
    if not isinstance(destination,str) or not player.alive:
        raise ValueError('Choose a reachable tile while conscious.')
    view=local_visibility.sight(world,player,compiled)
    visible=view['rooms']|local_visibility.known_facades(world,player,compiled,view)
    remembered={r for r in player.progress.get('atlas_seen',{}) if r in compiled[0] and compiled[0][r].get('map_visibility')!='hidden'}
    allowed=set(player.explored_rooms)|visible|remembered|{player.location}
    from engine.political_map import geography
    survey,_=geography(world)
    if destination in survey:
        allowed.update(survey)
    from engine import knowledge
    known=destination in knowledge.ids(world,player,'rooms')
    if known and destination in world.rooms:
        # A known address can be reached along public outdoor edges. Intervening
        # interiors stay off the route unless the traveller starts or finishes there.
        rows=compiled[0]
        areas={rows[r]['_visual_style'][2].get('id') for r in (player.location,destination)
               if rows[r]['_visual_style'][0]=='building' and rows[r]['_visual_style'][2]}
        familiar=set(player.explored_rooms)|visible
        allowed={r for r,row in rows.items() if world.rooms[r].map_visibility!='hidden' and
                 (row['_visual_style'][0]=='outdoors' or (r in familiar and row['_visual_style'][0]=='cave') or
                  row['_visual_style'][0]=='building' and (row['_visual_style'][2] or {}).get('id') in areas)}
        allowed.update((player.location,destination))
    if destination not in allowed or destination not in world.rooms:
        raise ValueError('Choose a tile you have explored or can see.')
    rows=compiled[0]
    if all(rows[r]["_visual_style"][0]=="outdoors" for r in (player.location,destination)):
        allowed={r for r in allowed if r in rows and rows[r]["_visual_style"][0]=="outdoors"}
    steps=frontiers.path(world,player.location,destination,player,allowed=allowed)
    if steps is None:
        route=frontiers.path(world,player.location,destination,player,include_locked=True,allowed=allowed)
        for origin,direction,_ in route or ():
            reason=frontiers.blocked(world,origin,direction,player)
            if reason:raise ValueError(reason)
        raise ValueError('There is no open route to that tile through the area you know.')
    return steps
