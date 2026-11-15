"""Regional, visitable zoos with one protected display for each recorded taxon.

Exhibits are instantiated only in a gallery a player visits. This keeps eight
large zoos from adding hundreds of active AI residents to every server tick.
"""
from collections import defaultdict
from copy import deepcopy
from engine import creature_catalog, living, regional_world



def habitat(row, species):
    if creature_catalog.kind(row, species) == 'monster':
        terrain=str(row.get('regional_habitat','')).lower()
        if terrain in ('cave','underground'):return 'monster_cave'
        if terrain in ('wetland','swamp','coast','river'):return 'monster_wetland'
        if terrain in ('desert','arid'):return 'monster_desert'
        if terrain in ('tundra','mountain','alpine'):return 'monster_cold'
        if terrain in ('forest','woodland','plains','grassland'):return 'monster_woodland'
        return 'monsters'
    sp = species.get(row.get('species') or row.get('social_profile', {}).get('species'), row)
    cat = sp.get('category')
    place = str(sp.get('habitat', row.get('regional_habitat', ''))).lower()
    if cat in ('fish', 'crustacean', 'mollusk'):
        return 'aquarium'
    if cat in ('insect', 'arachnid'):
        return 'insectarium'
    if cat == 'reptile':
        return 'terrarium'
    if cat == 'bird':
        return 'aviary'
    if any(x in place for x in ('cave', 'underground')):
        return 'cave'
    if any(x in place for x in ('wetland', 'marsh', 'water', 'river', 'swamp')):
        return 'wetland'
    if any(x in place for x in ('desert', 'arid', 'sand')):
        return 'desert'
    if any(x in place for x in ('tundra', 'cold', 'alpine', 'mountain', 'arctic')):
        return 'cold'
    return 'woodland'


def _place_city(w, room):
    city = regional_world.city_for(w, room)
    if city:
        return city['name']
    for region in getattr(w, 'field_regions', []):
        if str(room).startswith(region.prefix+'_'):
            city = regional_world.city_for(w, region.gate)
            if city:
                return city['name']
    return None


def catalogues(w):
    result = {c['name']: {} for c in regional_world.cities(w)}
    species = getattr(w, 'species', {})
    representatives = {}
    for row in w.npcs.values():
        if row.get('zoo_exhibit') or creature_catalog.kind(row, species) not in ('creature', 'monster'):
            continue
        taxon = creature_catalog.taxon(row, species)
        representatives.setdefault(taxon, row)
        locales = {row.get('regional_range'), _place_city(w,row.get('spawn_room') or row.get('location'))}
        for city in locales & result.keys():
            result[city][taxon] = row
    # Species location and actual authored spawners supply regional evidence.
    for sid, row in species.items():
        if row.get('category') not in creature_catalog.ANIMALS or row.get('sentient'):
            continue
        city = _place_city(w, row.get('location'))
        if city in result:
            result[city][sid] = representatives.get(sid, row)
    for rid, room in w.rooms.items():
        city = _place_city(w,rid)
        if city not in result:
            continue
        for spawner in room.spawners:
            row = w.npcs.get(spawner.get('npc'), {})
            if row and creature_catalog.kind(row,species) in ('creature','monster'):
                result[city][creature_catalog.taxon(row,species)] = row
    return result


def install(w):
    """Index the authored galleries and exhibits without creating game content."""
    value = getattr(w, 'rules', {}).get('regional_zoos', {})
    w.regional_zoo_catalog = (deepcopy(value) if isinstance(value, dict)
                             and regional_world.config(w, 'zoos', False) is True else {})


def populate(w, room):
    if not regional_world.enabled(w) or regional_world.config(w,'zoos',False) is not True:
        return
    detail=living.details(w,room)
    sources=detail.get('zoo_exhibits',[])
    if not sources:
        return
    from engine.commands import _spawn_npc_instance
    occupied={e.spawner_key for e in w.entities.values() if e.spawner_key and e.spawner_key.startswith('zoo:')}
    for source in sources:
        stable='zoo:'+source
        if stable in occupied:
            continue
        animal=_spawn_npc_instance(w,w.rooms[room],source,spawner_key=stable)
        if animal:
            occupied.add(stable)
            animal.progress['zoo_exhibit']=dict(home=room,city=detail['zoo_city'],taxon=w.npcs[source]['zoo_taxon'])
            animal.progress['social_profile']={'fertile':False,'autonomous':False,'family_enabled':False}
            animal.activity='resting in a protected '+detail['zoo_habitat']+' habitat'


def advance(w):
    # Reconcile a loaded/teleported visitor without spawning every unseen gallery.
    for room in {e.location for e in w.entities.values() if e.is_player and e.alive}:
        populate(w,room)
