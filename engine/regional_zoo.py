"""Regional, visitable zoos with one protected display for each recorded taxon.

Exhibits are instantiated only in a gallery a player visits. This keeps eight
large zoos from adding hundreds of active AI residents to every server tick.
"""
from collections import defaultdict
from copy import deepcopy
from engine import creature_catalog, living, regional_world

HABITATS = {
    'aquarium': ('River and Coastal Aquarium', 'indoor', 'Clear pools, shaded channels and tidal tanks reproduce local fresh and salt waters.'),
    'insectarium': ('Insect and Small-Life House', 'indoor', 'Planted glass cases hold leaf litter, flowering stems and humid soil.'),
    'terrarium': ('Warm Rock and Burrow House', 'indoor', 'Heated rocks, cool burrows and sheltered sand provide a choice of microclimates.'),
    'cave': ('Cave Habitat Hall', 'indoor', 'Low light, stone ledges and humid passages reproduce the region’s underground refuges.'),
    'aviary': ('Woodland Aviary', 'outdoor', 'An open-air flight enclosure surrounds living trees, nesting ledges and shallow pools.'),
    'wetland': ('Marsh and Riverbank Reserve', 'outdoor', 'Reed beds, muddy banks and pools shelter the animals of the local wetlands.'),
    'desert': ('Dryland Habitat', 'outdoor', 'Sandy ground, shade shelters and rocky dens reproduce the surrounding dry country.'),
    'cold': ('Highland and Cold-Country Range', 'outdoor', 'Cool caves, rocky slopes and sheltered meadow offer space for cold-country animals.'),
    'woodland': ('Woodland and Meadow Range', 'outdoor', 'Native trees, grasses, streams and secluded dens reproduce woodland and meadow habitats.'),
    'monsters': ('Warded Monster Habitats', 'outdoor', 'Individual double barriers and warded shelters separate dangerous supernatural exhibits from visitors and each other.'),
    'monster_cave': ('Warded Cavern Habitats', 'indoor', 'Dim caverns, damp rock shelves and isolated burrows recreate underground homes behind separate warded barriers.'),
    'monster_wetland': ('Warded Marsh Habitats', 'outdoor', 'Individual reed pools and muddy refuges recreate wetland homes; double barriers separate each supernatural exhibit.'),
    'monster_desert': ('Warded Dryland Habitats', 'outdoor', 'Individual sand basins, shaded rock dens and warm burrows recreate dry-country homes behind warded barriers.'),
    'monster_cold': ('Warded Cold-Country Habitats', 'indoor', 'Cooled stone chambers, snow beds and dark refuges recreate cold-country homes in separate secure exhibits.'),
    'monster_woodland': ('Warded Woodland Habitats', 'outdoor', 'Individual wooded runs, deep litter and secluded dens recreate forest and meadow homes behind double barriers.'),
}


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
    if regional_world.config(w,'zoos',True) is False:
        return
    species = getattr(w,'species',{})
    catalogues_by_city = catalogues(w)
    w.regional_zoo_catalog = {}
    for city_index, city in enumerate(regional_world.cities(w)):
        slug = regional_world.key(city['name'])
        base = 'rg_'+slug+'_zoo'
        entries = catalogues_by_city[city['name']]
        grouped = defaultdict(list)
        for taxon, row in sorted(entries.items()):
            if not row.get('regional_habitat'):
                room=row.get('spawn_room') or row.get('location')
                terrain=living.details(w,room).get('climate',{}).get('terrain')
                if not terrain:
                    region=next((r for r in getattr(w,'field_regions',[]) if str(room).startswith(r.prefix+'_')),None)
                    terrain=region.terrain if region else None
                if terrain:row={**row,'regional_habitat':terrain}
            grouped[habitat(row,species)].append((taxon,row))
        # Both indoor and outdoor visitor buildings exist in each city.
        regional_world.add_room(w,base,city['name']+' Regional Zoo',
            f"The regional zoo holds protected displays for {len(entries)} recorded local animal and monster taxa. "
            'The indoor galleries and outdoor habitat walks recreate the homes of their exhibits. '
            'Signs explain habitat, diet and regional sightings. Follow indoor or outdoor to explore; out returns to the city.',
            city,floor=city_index*3,facilities=('zoo','library'),zoo_city=city['name'])
        entrance = 'zoo'
        if not regional_world.connect(w,city['home'],entrance,base,'out'):
            entrance='regional zoo'
            regional_world.connect(w,city['home'],entrance,base,'out')
        for side in ('indoor','outdoor'):
            regional_world.add_room(w,base+'_'+side,city['name']+' Zoo '+('Natural History House' if side=='indoor' else 'Habitat Walk'),
                'Clearly marked paths lead to protected regional exhibits. '+
                ('Climate-controlled galleries house aquatic and small creatures.' if side=='indoor' else 'Outdoor habitats provide native vegetation, shelter and room to roam.'),
                city,x=1 if side=='indoor' else -1,floor=city_index*3,
                environment='building' if side=='indoor' else 'garden',facilities=('zoo','husbandry'),zoo_city=city['name'])
            regional_world.connect(w,base,side,base+'_'+side,'out')
        displays=[]
        for index,(kind,rows) in enumerate(sorted(grouped.items())):
            title,side,description=HABITATS[kind]
            rid=base+'_'+kind
            signs=[]
            for taxon,row in rows:
                sp=species.get(taxon,{})
                name=sp.get('name') or row.get('name',taxon)
                detail=sp.get('description') or row.get('description','A recorded regional creature.')
                diet=[w.items.get(i,{}).get('name',i) for i in sp.get('diet',[])][:5]
                signs.append(name+' — '+detail+(' Diet: '+', '.join(diet)+'.' if diet else ''))
                source_id=base+'_exhibit_'+regional_world.key(taxon)
                # Never reuse a live wild identity or overwrite a creator's record.
                if source_id not in w.npcs:
                    profile=deepcopy(row.get('social_profile') or {})
                    profile.update(sentient=False,species=sp.get('id') or profile.get('species') or taxon,
                                   fertile=False,family_enabled=False,autonomous=False,accepts=[])
                    w.npcs[source_id]=dict(id=source_id,name=name,description=detail+' Secured behind the habitat barrier.',
                        hp=max(1,int(row.get('hp',12))),attack=0,defense=0,gold=0,drops=[],
                        social_profile=profile,creature_kind=creature_catalog.kind(row,species),
                        species=sp.get('id') or row.get('species'),spawn_managed=True,
                        zoo_exhibit=True,zoo_taxon=taxon,zoo_home=rid,regional_generated=True,
                        aggressive=False,tameable=False)
                displays.append(dict(taxon=taxon,npc=source_id,room=rid))
            regional_world.add_room(w,rid,city['name']+' Zoo · '+title,
                description+'\n\n'+'\n\n'.join(signs)+'\n\nThe visitor barrier keeps these exhibits safe. Return with out.',
                city,x=(index%4)+2,y=(index//4)+1,floor=city_index*3+(1 if side=='indoor' else 0),
                environment='building' if side=='indoor' else 'garden',facilities=('zoo','husbandry'),
                zoo_city=city['name'],zoo_habitat=kind,zoo_exhibits=[d['npc'] for d in displays if d['room']==rid])
            regional_world.connect(w,base+'_'+side,kind.replace('_',' '),rid,'out')
        w.regional_zoo_catalog[city['name']]=dict(entrance=base,city_exit=entrance,native_count=len(entries),
            display_count=len(displays),taxa=sorted(entries),displays=displays,
            coverage_basis='Authored regional species locations, NPC sightings and room spawners; no claim about undiscovered species.')


def populate(w, room):
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
