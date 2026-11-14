"""Finite regional threats with advance warning, spatial caps and game-time cooldowns."""
import random
from hashlib import sha256
from engine import living, regional_world

KEY = 'regional_encounters_v1'
URBAN = [('Scrap Rat', 'creature', 'A defensive scavenger with sharp incisors and a torn ear.'),
         ('Soot Imp', 'monster', 'A soot-black imp picks through rubbish, clutching stolen scraps.')]
OUTDOOR = [('Thornback Prowler', 'monster', 'A low, thorn-armoured monster follows movement at the edge of the road.'),
           ('Glassjaw Scavenger', 'monster', 'A squat beast with translucent jaws scavenges abandoned packs.'),
           ('Mire Lantern', 'monster', 'A soft marsh creature lures insects into a faintly glowing mouth.')]

LOCAL_MONSTERS = {
    'desert': ('Dune Lantern','A sand-burrowing monster exposes a luminous lure between its jaws after dusk.'),
    'forest': ('Briar Maw','A creeping monster hides beneath thorny bark and snaps at passing feet.'),
    'tundra': ('Rime Leech','A pale cold-country monster slides under snow and clings to warm prey.'),
    'mountain': ('Rime Leech','A pale cold-country monster shelters among icy stones and clings to warm prey.'),
    'cave': ('Cave Lantern','A blind subterranean monster hangs a faintly glowing lure above its mouth.'),
    'plains': ('Meadow Lurker','A low, grass-coloured monster waits beneath the turf beside game trails.'),
}


def state(w):
    return living.state(w).setdefault(KEY, {'last': -1, 'checks': {}, 'cooldowns': {}, 'spawned': 0})


def install(w):
    for city in regional_world.cities(w):
        slug = regional_world.key(city['name'])
        terrain=living.details(w,city['home']).get('climate',{}).get('terrain','forest')
        for zone, rows in [('urban', URBAN), ('outdoor', OUTDOOR)]:
            for index, (name, category, description) in enumerate(rows):
                if zone=='outdoor' and index==2 and terrain in LOCAL_MONSTERS:
                    name,description=LOCAL_MONSTERS[terrain]
                ident = f'rg_{slug}_{zone}_{index}'
                if ident in w.npcs:
                    continue
                food = next((iid for iid in ('lw_rations', 'rations', 'bread', 'eco_rabbit_meat') if iid in w.items), None)
                gear = next((iid for iid in ('rusty_dagger', 'dagger', 'leather_cap', 'wooden_shield') if iid in w.items), None)
                drops = [x for x in [food, gear if zone == 'outdoor' and index == 1 else None] if x]
                w.npcs[ident] = dict(id=ident, name=name, description=description,
                    hp=8 if zone == 'urban' else 16 + index * 2, attack=2 if zone == 'urban' else 3 + index,
                    defense=0 if zone == 'urban' else 1, gold=2 if zone == 'urban' else 3 + index,
                    drops=drops, reward_xp=8 if zone == 'urban' else 15 + index * 3,
                    social_profile={'sentient':False, 'species':ident, 'fertile':False, 'autonomous':False},
                    creature_kind=category, aggressive=True, aggression_chance=.35,
                    group='wild_hunters' if 'wild_hunters' in w.groups else None,
                    spawn_managed=True, regional_generated=True,
                    regional_range=city['name'], regional_zone=zone,regional_habitat=terrain,corpse='timed')


def zone(w, room):
    if room not in w.rooms:
        return None
    d = living.details(w, room)
    if (room == w.start_room or room in {g.get('start_room') for g in w.groups.values()}
            or d.get('zoo_city') or d.get('justice_city') or d.get('truce')
            or d.get('property_unit_id') or d.get('requires_boat')
            or d.get('environment') in ('building', 'interior')
            or set(d.get('facilities', [])) & {'inn', 'temple', 'school', 'library', 'kitchen', 'hospital', 'court', 'jail', 'husbandry'}):
        return None
    if d.get('open_country') or d.get('environment') in ('wilderness', 'cave'):
        return 'outdoor'
    city = regional_world.city_for(w, room)
    if not city:
        return None
    # Only surveyed streets and open city spaces, never guessed interiors.
    if d.get('environment') in ('street', 'town', 'city', 'outdoors') or d.get('laws', {}).get('enabled') or d.get('route_surface'):
        return 'urban'
    return None


def nearby(w, source, reach=2):
    found = {source}
    frontier = {source}
    for _ in range(reach):
        new = {dest for rid in frontier for dest in w.rooms[rid].exits.values() if dest in w.rooms} - found
        found.update(new)
        frontier = new
    return found


def spawn(w, room, city, which, now, *, rng=random.random):
    """One actor per eligible location; no immediate attack on creation."""
    if zone(w, room) != which:
        return None
    s = state(w)
    if now < s['cooldowns'].get(room, -1):
        return None
    local = nearby(w, room)
    cap = 1 if which == 'urban' else 3
    if sum(bool(e.alive and e.progress.get('regional_encounter')) for rid in local for e in w.entities_in_room(rid)) >= cap:
        return None
    if which == 'urban' and any(e.alive and e.progress.get('regional_encounter', {}).get('city') == city['name']
                              and e.progress['regional_encounter'].get('zone') == 'urban' for e in w.entities.values()):
        return None
    rows = URBAN if which == 'urban' else OUTDOOR
    index = min(len(rows)-1, int(max(0, min(.99999, rng())) * len(rows)))
    ident = f"rg_{regional_world.key(city['name'])}_{which}_{index}"
    if ident not in w.npcs:
        return None
    from engine.commands import _spawn_npc_instance
    actor = _spawn_npc_instance(w, w.rooms[room], ident, spawner_key='regional:'+room+':'+str(now))
    if not actor:
        return None
    actor.progress['regional_encounter'] = dict(city=city['name'], zone=which, home=room, spawned=now, next_move=now+3, next_attack=now+2)
    actor.activity = 'prowling nearby'
    s['cooldowns'][room] = now + (180 if which == 'urban' else 60)
    s['spawned'] += 1
    text = actor.name+' emerges near '+w.rooms[room].name+'. Its movements look dangerous.'
    w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(rid, text) for rid in local])[-500:]
    return actor


def advance(w, rng=random.random):
    if regional_world.config(w, 'encounters', True) is False:
        return
    s = state(w)
    now = int(living.state(w)['minute'])
    if s['last'] == now:
        return
    s['last'] = now
    actors = [e for e in w.entities.values() if e.alive and e.progress.get('regional_encounter')]
    players = [e for e in w.entities.values() if e.is_player and e.alive]
    # Global cap also covers many simultaneous players. No unseen world filling.
    cap = max(1, min(64, int(regional_world.config(w, 'max_encounters', 24))))
    for player in players[:128]:
        which = zone(w, player.location)
        if which is None or len(actors) >= cap:
            continue
        city = regional_world.city_for(w, player.location)
        if not city:
            continue
        interval = 20 if which == 'urban' else 6
        old = s['checks'].get(player.id)
        if old is None:
            s['checks'][player.id] = now
            continue  # Arrival never spawns an attacker on the player.
        if now-old < interval:
            continue
        s['checks'][player.id] = now
        if rng() >= (.12 if which == 'urban' else .65):
            continue
        places = sorted(r for r in nearby(w, player.location) if r != player.location and zone(w,r)==which
                        and not any(e.is_player for e in w.entities_in_room(r)))
        if places:
            offset = int.from_bytes(sha256((player.id+str(now)).encode()).digest()[:2], 'big') % len(places)
            actor = spawn(w, places[offset], city, which, now, rng=rng)
            if actor:
                actors.append(actor)
    targeted = set()
    from engine import frontiers, combat, relationships
    for actor in actors:
        rec = actor.progress['regional_encounter']
        if not actor.alive:
            continue
        # Unseen threats disperse after an hour; this frees the global budget
        # without rewarding an unearned kill or respawning in front of a player.
        close=nearby(w,actor.location,5)
        if now-rec['spawned']>=60 and not any(p.location in close for p in players):
            from engine.commands import _remove_entity
            _remove_entity(w,w.rooms[actor.location],actor.id)
            continue
        # A protected location is never a combat venue, even after a forced move.
        if zone(w, actor.location) != rec['zone']:
            continue
        victims = [e for e in w.entities_in_room(actor.location) if e.id != actor.id and e.id not in targeted
                   and e.alive and (e.is_player or (relationships.sentient(w,e) and not e.progress.get('zoo_exhibit')))]
        if victims and now >= rec.get('next_attack', now):
            rec['next_attack'] = now + 5
            target = sorted(victims, key=lambda e: (not e.is_player, e.id))[0]
            try:
                combat.validate(w, actor, target)
                text = combat.strike(w, actor, target, counter=True)
            except ValueError:
                continue
            targeted.add(target.id)
            w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(actor.location,text)])[-500:]
        elif now >= rec.get('next_move', now):
            rec['next_move'] = now + 4
            places = [(di,r) for di,r in w.rooms[actor.location].exits.items()
                      if zone(w,r)==rec['zone'] and r in nearby(w,rec['home'],3)
                      and not frontiers.blocked(w,actor.location,di,actor)]
            if places and rng() < .6:
                _, dest = places[min(len(places)-1,int(rng()*len(places)))]
                w.move_entity(actor.id,dest)
    # Keep checkpoint size bounded by currently relevant actors and recent sites.
    live_ids = {p.id for p in players}
    s['checks'] = {k:v for k,v in s['checks'].items() if k in live_ids}
    if len(s['cooldowns']) > 256:
        s['cooldowns'] = {k:v for k,v in s['cooldowns'].items() if v > now}
