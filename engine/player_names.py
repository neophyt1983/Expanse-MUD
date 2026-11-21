"""Display-name selection for player commands; stable IDs remain internal keys."""
def pick(rows, query, label='entry'):
    rows=list(rows);text=query.strip();key=text.casefold()
    exact=[r for r in rows if str(r['id'])==text]
    matches=exact or [r for r in rows if r['name'].casefold()==key]
    if not matches and key:matches=[r for r in rows if key in r['name'].casefold()]
    if not matches:raise ValueError('Choose a known '+label+' by name or from its panel.')
    if len(matches)!=1:
        names=list(dict.fromkeys(r['name'] for r in matches))
        raise ValueError('Be more specific: '+', '.join(names[:8])+'. Choose the matching entry in its panel if names are identical.')
    return matches[0]

def item(world, query, ids):
    return pick([{'id':i,'name':world.items[i].get('name','Unnamed item')} for i in dict.fromkeys(ids) if i in world.items],query,'item')['id']

def nearby(world, player, query):
    room_id = player.location
    rows=[{'id':e.id,'name':e.name} for e in world.entities_in_room(room_id)
          if not e.is_player and e.alive and e.location == room_id]
    if query.strip().casefold().startswith('npc:'):
        key = query.strip().casefold()
        matches = [row for row in rows if row['id'].casefold() == key]
        if len(matches) != 1:
            raise ValueError('That person is no longer here to talk to.')
        return world.entities[matches[0]['id']]
    return world.entities[pick(rows,query,'nearby person')['id']]

def known_items(world, player):
    try:
        from engine import knowledge
    except ImportError:return set(player.inventory)|set(world.rooms[player.location].items)
    return knowledge.ids(world,player,'items')
