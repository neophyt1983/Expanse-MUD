"""Read-only visual projection of discovered rooms and their real exits.

Coordinates are those of the ASCII layout, never a second movement model.
Discovered entrances have exterior facades outdoors, never invented rooms.
"""
import re

from engine.mapping import VECTORS
VISUAL_SHAPES = frozenset(['ankle_boots', 'ankle_shoes', 'apron_tunic', 'arming_jacket', 'arming_sword', 'battle_skirt', 'bead_strand', 'beret', 'blouse', 'bodice', 'bolero', 'bonnet', 'bracers', 'breastplate', 'breeches', 'brigandine', 'brooch', 'buckler', 'cap', 'ceremonial_robe', 'chausses', 'cheek_helm', 'chemise', 'circle_cloak', 'coif', 'coif_cap', 'collared_cape', 'cowl', 'crested_helm', 'cuffed_boots', 'cuffed_gloves', 'cuirass', 'cuisses', 'culottes', 'dagger', 'dance_shoes', 'divided_skirt', 'doublet', 'drawstring_top', 'dress_gloves', 'duelist_gloves', 'ear_wrap', 'falchion', 'fauld_coat', 'festival_tunic', 'fingerless_gloves', 'flanged_mace', 'flat_hat', 'floppy_hat', 'forearm_wraps', 'full_helm', 'gaiters', 'gambeson', 'gauntlets', 'gloves', 'gorget_helm', 'greaves', 'half_cape', 'half_greaves', 'hand_axe', 'handwarmers', 'hauberk', 'headwrap', 'heater_shield', 'heraldic_surcoat', 'high_boots', 'high_collar_shirt', 'high_soft_boots', 'hood', 'hooded_cloak', 'hose', 'jerkin', 'kerchief', 'kite_shield', 'knee_guards', 'knot_charm', 'knuckle_guards', 'lace_cuffs', 'lamellar_coat', 'layered_gown', 'leggings', 'lobster_gauntlets', 'locket', 'long_coat', 'long_gloves', 'long_tabard', 'long_underrobe', 'longshirt', 'mantle', 'marching_boots', 'medallion', 'mitts', 'moccasins', 'nasal_helm', 'necklace', 'open_helm', 'oval_shield', 'over_robe', 'overboots', 'overgown', 'padded_robe', 'palm_wraps', 'pavise', 'pendant', 'pillbox', 'plated_mantle', 'pleated_skirt', 'pointed_boots', 'pointed_hat', 'poncho', 'prayer_wheel', 'quarterstaff', 'quilted_tunic', 'rapier', 'rectangular_cloak', 'riding_boots', 'riding_legs', 'rosette', 'round_hat', 'round_shield', 'sabatons', 'sailor_hat', 'sandals', 'scale_coat', 'scalloped_shield', 'scarf_mantle', 'seal', 'segmented_cuirass', 'shirt', 'short_jacket', 'shorts', 'shoulder_shawl', 'shoulder_stole', 'sleeve_guards', 'sleeveless_tabard', 'sleeveless_top', 'slippers', 'snood', 'soft_boots', 'soft_cap', 'spear', 'spiked_buckler', 'splint_legs', 'split_boots', 'split_cloak', 'split_tunic', 'strap_sandals', 'surcoat', 'tabard', 'tabbed_cape', 'talisman', 'tall_hat', 'targe', 'tassets', 'torc', 'tower_shield', 'travel_cape', 'travel_duster', 'travel_spats', 'tricorn', 'trousers', 'turban', 'undertunic', 'vambraces', 'veil', 'vest', 'visored_helm', 'waistcoat', 'walking_shoes', 'war_coat', 'war_hammer', 'war_pick', 'wide_hat', 'wide_trousers', 'work_mitts', 'wrap_shirt', 'wrap_shoes', 'wrap_skirt', 'wrap_top', 'wrapped_sash', 'wrist_wraps', 'wristguards'])
VISUAL_PATTERNS = frozenset(['beaded', 'braided', 'carved', 'crosshatch', 'diagonal', 'faceted', 'felted', 'filigree', 'grain', 'herringbone', 'inlay', 'knotted', 'lacing', 'lattice', 'layered', 'mosaic', 'plates', 'quilted', 'rings', 'rivets', 'scales', 'slats', 'solid', 'stitched', 'woven'])
VISUAL_DETAILS = frozenset(['ankle_boots', 'ankle_shoes', 'apron_tunic', 'arming_jacket', 'arming_sword', 'battle_skirt', 'bead_strand', 'beret', 'blouse', 'bodice', 'bolero', 'bonnet', 'bracers', 'breastplate', 'breeches', 'brigandine', 'brooch', 'buckler', 'cap', 'ceremonial_robe', 'chausses', 'cheek_helm', 'chemise', 'circle_cloak', 'coif', 'coif_cap', 'collared_cape', 'cowl', 'crested_helm', 'cuffed_boots', 'cuffed_gloves', 'cuirass', 'cuisses', 'culottes', 'dagger', 'dance_shoes', 'divided_skirt', 'doublet', 'drawstring_top', 'dress_gloves', 'duelist_gloves', 'ear_wrap', 'falchion', 'fauld_coat', 'festival_tunic', 'fingerless_gloves', 'flanged_mace', 'flat_hat', 'floppy_hat', 'forearm_wraps', 'full_helm', 'gaiters', 'gambeson', 'gauntlets', 'gloves', 'gorget_helm', 'greaves', 'half_cape', 'half_greaves', 'hand_axe', 'handwarmers', 'hauberk', 'headwrap', 'heater_shield', 'heraldic_surcoat', 'high_boots', 'high_collar_shirt', 'high_soft_boots', 'hood', 'hooded_cloak', 'hose', 'jerkin', 'kerchief', 'kite_shield', 'knee_guards', 'knot_charm', 'knuckle_guards', 'lace_cuffs', 'lamellar_coat', 'layered_gown', 'leggings', 'lobster_gauntlets', 'locket', 'long_coat', 'long_gloves', 'long_tabard', 'long_underrobe', 'longshirt', 'mantle', 'marching_boots', 'medallion', 'mitts', 'moccasins', 'nasal_helm', 'necklace', 'open_helm', 'oval_shield', 'over_robe', 'overboots', 'overgown', 'padded_robe', 'palm_wraps', 'pavise', 'pendant', 'pillbox', 'plated_mantle', 'pleated_skirt', 'pointed_boots', 'pointed_hat', 'poncho', 'prayer_wheel', 'quarterstaff', 'quilted_tunic', 'rapier', 'rectangular_cloak', 'riding_boots', 'riding_legs', 'rosette', 'round_hat', 'round_shield', 'sabatons', 'sailor_hat', 'sandals', 'scale_coat', 'scalloped_shield', 'scarf_mantle', 'seal', 'segmented_cuirass', 'shirt', 'short_jacket', 'shorts', 'shoulder_shawl', 'shoulder_stole', 'sleeve_guards', 'sleeveless_tabard', 'sleeveless_top', 'slippers', 'snood', 'soft_boots', 'soft_cap', 'spear', 'spiked_buckler', 'splint_legs', 'split_boots', 'split_cloak', 'split_tunic', 'strap_sandals', 'surcoat', 'tabard', 'tabbed_cape', 'talisman', 'tall_hat', 'targe', 'tassets', 'torc', 'tower_shield', 'travel_cape', 'travel_duster', 'travel_spats', 'tricorn', 'trousers', 'turban', 'undertunic', 'vambraces', 'veil', 'vest', 'visored_helm', 'waistcoat', 'walking_shoes', 'war_coat', 'war_hammer', 'war_pick', 'wide_hat', 'wide_trousers', 'work_mitts', 'wrap_shirt', 'wrap_shoes', 'wrap_skirt', 'wrap_top', 'wrapped_sash', 'wrist_wraps', 'wristguards'])
VISUAL_SILHOUETTES = frozenset(['armor', 'axe', 'boots', 'charm', 'cloak', 'coat', 'dagger', 'dress', 'gloves', 'hammer', 'hat', 'helmet', 'hood', 'leggings', 'mace', 'pick', 'robe', 'shield', 'spear', 'staff', 'sword', 'tunic'])
VISUAL_MATERIALS = frozenset(['bone', 'canvas', 'crystal', 'felt', 'flax', 'iron', 'leather', 'linen', 'pearl', 'scale', 'silk', 'stone', 'wood', 'wool'])

LAND_USES = {'house', 'rental', 'business', 'farm', 'ranch', 'recreation', 'hunting', 'reserve'}


def land_use_for(room, parcel=None):
    """Authored or persisted parcel type, not a guess from a room name."""
    plot = room.get('property_plot') or {}
    if not isinstance(plot, dict) or not plot.get('enabled'):
        return None
    value = parcel.get('kind') if isinstance(parcel, dict) else None
    value = value or room.get('active_land_use') or plot.get('kind')
    return value if value in LAND_USES else None


OUTDOORS = {'wilderness', 'outdoors', 'outdoor', 'ocean', 'forest', 'mountain', 'plains', 'coast', 'desert', 'wetland', 'rainforest', 'valley', 'shore', 'road', 'water', 'river', 'lake'}


def room_style(room):
    climate = room.get('climate') or {}
    living = room.get('living') or {}
    environment = str(room.get('environment', living.get('environment', ''))).lower()
    terrain = str(climate.get('terrain') or living.get('terrain') or room.get('terrain') or (environment if environment != 'settlement' else '') or 'unknown').lower()
    if environment in {'ocean', 'water', 'river', 'lake', 'road'}:
        terrain = environment
    elif environment == 'shore':
        terrain = 'coast'
    building = room.get('_visual_building') or {}
    # The original civic generator grouped public lanes in residential terraces
    # and marked them sheltered. Respect explicit Editor environments first.
    if (not environment and room.get('creation_method')=='Surveyed and constructed by the regional civic works office.'
        and room.get('name','').endswith((' Gateway Lane',' Household Court',' Garden Walk',' Well Court',' Market Approach',
            ' Workshop Row',' Foundry Lane',' Weavers Walk',' Warehouse Road',' Academy Court',' Training Grounds',
            ' Survey Road',' Pasture Trail',' Herb Verge',' Stream Path',' Woodland Track',' Valley Road',' Gorge Approach',
            ' Highland Trail',' Rocky Traverse',' Ridge Path',' Wind Pass',' Summit Approach',' Outer Reach'))):
        return 'outdoors','road',{}
    if (not environment and room.get('creation_method')=='Defined and placed by regional creators.'
        and room.get('name','').endswith((' Council Chamber',' Embassy',' Town Hall',' City Hall',' Throne Room'))):
        return 'building','floor',building
    if environment == 'cave' or terrain == 'cave':
        return 'cave', 'cave', building
    # A civic district may be a named building group, but its surveyed land
    # parcels are outdoor lots. Explicit indoor/sheltered creator settings win.
    if land_use_for(room) and room.get('land_uses') and environment not in {'inside', 'indoor', 'interior', 'building'} and climate.get('sheltered') is not True:
        return 'outdoors', terrain, {}
    # "settlement" is a generic schema default, including for true interiors.
    # Some campaign "buildings" are outdoor danger zones. Explicit outdoor
    # environments win even if an older content generator marked them sheltered.
    if environment in OUTDOORS or climate.get('sheltered') is False:
        return 'outdoors', terrain, {}
    if climate.get('sheltered') or environment in {'inside', 'indoor', 'interior', 'building'} or building:
        return 'building', 'floor', building
    return 'outdoors', terrain, {}


def crosses_seam(a,b,di):
    first,second=a.get('planet',{}),b.get('planet',{})
    if not any(first.get(k) and second.get(k) for k in ('cell','field')):return False
    if abs(first['lon']-second['lon'])>350:return di in ('east','west','northeast','northwest','southeast','southwest')
    return di in ('north','south') and first['lat']==second['lat'] and abs(first['lat'])>=86 and abs(first['lon']-second['lon'])==180


def render_visual(byid, positions, center, visible, radius=12, visited=None, local_positions=None):
    """Project only allowed rooms; never serialize unknown IDs or names."""
    visible = {rid for rid in visible if rid in byid}
    original_positions=positions
    if local_positions is not None:
        positions = {rid: local_positions.get(rid, original_positions[rid]) for rid in visible | {center}}
    elif len(visible)<=16:
        # Keep a single-step seam crossing adjacent in the local view. Atlas
        # geography and coordinate readouts retain their authoritative positions.
        origin=positions[center];local={rid:positions[rid] for rid in visible|{center}}
        for di,rid in byid[center].get('exits',{}).items():
            if rid in visible and crosses_seam(byid[center],byid[rid],di):
                local[rid]=tuple(origin[i]+VECTORS[di][i] for i in range(3))
        positions=local
    visible.add(center)
    visited=set(visible) if visited is None else set(visited)|{center}
    styles = {rid: byid[rid].get('_visual_style') or room_style(byid[rid]) for rid in visible}
    kind, _, building = styles[center]
    if kind == 'outdoors':
        context_rooms = {rid for rid in visible if styles[rid][0] == kind}
        context = dict(id='outdoors', label='Outdoors', kind=kind)
    elif building or kind == 'building':
        bid = building.get('id', center)
        context_rooms = {rid for rid in visible if styles[rid][0] == kind and styles[rid][2].get('id') == bid}
        if kind == 'building':
            # Adjacent rooms in the same real interior may have different
            # authored building ids. Keep all *already visible* connected
            # interior rooms in the projection, following either direction
            # of a real doorway; never add an unseen room or the outdoors.
            neighbors = {rid: set() for rid in visible if styles[rid][0] == kind}
            for rid in neighbors:
                for target in byid[rid].get('exits', {}).values():
                    if target in neighbors:
                        neighbors[rid].add(target)
                        neighbors[target].add(rid)
            pending = list(context_rooms | {center})
            context_rooms.add(center)
            while pending:
                for target in neighbors.get(pending.pop(), ()):
                    if target not in context_rooms:
                        context_rooms.add(target)
                        pending.append(target)
            # An annex without building metadata must keep the same projection
            # when it becomes the center. Pick the context from the already
            # visible component in a stable order, rather than the current room.
            named = sorted((styles[rid][2]['id'], rid) for rid in context_rooms
                           if styles[rid][2].get('id'))
            if named:
                bid, anchor = named[0]
                building = styles[anchor][2]
            else:
                bid = min(context_rooms)
                building = {'name': byid[bid].get('name', bid)}
        context = dict(id=kind + ':' + bid, label=building.get('name', byid[center]['name']), kind=kind)
    else:
        # An unnamed interior is the connected, discovered component only.
        # Include either direction of one-way passages when identifying a place.
        neighbors = {rid: set() for rid in visible if styles[rid][0] == kind and not styles[rid][2]}
        for rid in neighbors:
            for target in byid[rid].get('exits', {}).values():
                if target in neighbors:
                    neighbors[rid].add(target)
                    neighbors[target].add(rid)
        context_rooms, pending = {center}, [center]
        while pending:
            for target in neighbors.get(pending.pop(), ()):
                if target not in context_rooms:
                    context_rooms.add(target)
                    pending.append(target)
        anchor = min(context_rooms)
        context = dict(id=kind + ':' + anchor, label=byid[anchor].get('name', anchor), kind=kind)
    cx, cy, cz = positions[center]
    shown = {rid for rid in context_rooms if positions[rid][2] == cz and abs(positions[rid][0] - cx) <= radius and abs(positions[rid][1] - cy) <= radius}
    # A known entrance is the outside of its real room, not an exposed floor.
    # Only outgoing edges of visible outdoor tiles establish an entrance. Never
    # expand through these facades into the building or change authoritative IDs.
    exteriors = set()
    if kind == 'outdoors':
        for rid in shown:
            for target in byid[rid].get('exits', {}).values():
                if target in visible and styles[target][0] == 'building' and not byid[target].get('property_unit_id'):
                    x, y, z = positions[target]
                    if z == cz and abs(x - cx) <= radius and abs(y - cy) <= radius:
                        exteriors.add(target)
    tiles = [dict(id=rid, name=byid[rid].get('name', rid), x=positions[rid][0], y=positions[rid][1], z=positions[rid][2], terrain='building' if rid in exteriors else styles[rid][1], exterior=rid in exteriors, current=rid == center) for rid in sorted(shown | exteriors)]

    from engine.geology import descriptor
    from engine.coordinates import project as project_coordinates
    from engine.route_surfaces import descriptor as route_descriptor
    for tile in tiles:
        tile['visited']=tile['id'] in visited
        tile['visibility']='visited' if tile['visited'] else 'visible'
        from engine.facility_landmarks import descriptor as facility_descriptor
        landmark=facility_descriptor(byid[tile['id']])
        if landmark and styles[tile['id']][0]=='outdoors':tile['facility_landmark']=landmark
        route = route_descriptor(byid[tile['id']])
        if route and not tile['exterior'] and styles[tile['id']][0] == 'outdoors':
            tile['route_surface'] = route
        tile['coordinates'] = project_coordinates(byid[tile['id']], original_positions[tile['id']])
        if not tile['visited']:continue
        authored_geology = descriptor(byid[tile['id']].get('geology', {}))
        if authored_geology and not tile['exterior']:
            tile['geology'] = authored_geology
        land_use = land_use_for(byid[tile['id']])
        if land_use and not tile['exterior']:
            tile['surface'] = {'land_use': land_use}

    def link_kind(rid, direction, target):
        vector = VECTORS.get(direction)
        if target in context_rooms and vector and not vector[2] and positions[target] == tuple(positions[rid][i] + vector[i] for i in range(3)):
            return 'path'
        return 'portal'

    links = []
    for rid in sorted(shown):
        if rid not in visited:continue
        for direction, target in sorted(byid[rid].get('exits', {}).items()):
            if target not in visible:
                continue
            category = link_kind(rid, direction, target)
            if target not in shown and category == 'path':
                continue
            links.append(dict(**{'from': rid, 'to': target}, direction=direction, kind=category, one_way=rid not in byid[target].get('exits', {}).values()))
    exits = []
    for direction, target in sorted(byid[center].get('exits', {}).items()):
        known = target in visible
        row = dict(direction=direction, name=byid[target].get('name', target) if known else '? unexplored', known=known, kind=link_kind(center, direction, target) if known else 'portal')
        if known:
            row['target'] = target
        exits.append(row)
    return dict(version=1, center=center, context=context, floor=cz, coordinates=project_coordinates(byid[center], positions[center]), tiles=tiles, links=links, exits=exits, actors=[], warnings=[])


def apply_npc_counts(world, player_id, visual, blocked_exits):
    """Read-only local occupancy for the viewer and adjoining open path tiles.

    Explored terrain is not remote surveillance. Only an actual outgoing,
    same-floor compass path in this projection can extend the local count.
    Facades, portals, other floors and unseen rooms carry no count field.
    The server supplies its already-authoritative gate decisions, avoiding any
    new state initialization, route search or global NPC scan here.
    """
    player = world.entities.get(player_id)
    tiles = visual.get('tiles', [])
    for tile in tiles:
        tile.pop('npc_count', None)
    if player is None or visual.get('center') != player.location:
        return visual
    shown = {tile['id']: tile for tile in tiles
             if not tile.get('exterior') and tile.get('visited') is not False and tile.get('id') in world.rooms}
    center = shown.get(player.location)
    if center is None:
        return visual
    eligible = {player.location}
    room = world.rooms[player.location]
    for exit_row in visual.get('exits', []):
        direction = exit_row.get('direction')
        target = exit_row.get('target')
        vector = VECTORS.get(direction)
        if (not exit_row.get('known') or exit_row.get('kind') != 'path'
                or exit_row.get('blocked') or blocked_exits.get(direction)
                or not vector or vector[2] or room.exits.get(direction) != target
                or target not in shown):
            continue
        tile = shown[target]
        if all(tile.get(axis) == center.get(axis, 0) + vector[index]
               for index, axis in enumerate(('x', 'y', 'z'))):
            eligible.add(target)
    for rid in eligible:
        shown[rid]['npc_count'] = sum(
            1 for eid in dict.fromkeys(world.rooms[rid].entities)
            if (entity := world.entities.get(eid)) is not None
            and entity.alive and not entity.is_player and entity.location == rid
        )
    return visual


def apply_world_surfaces(world, visual):
    """Decorate only already-authorized tiles with current real resource state.

    The cached room topology stays authoritative. Live land conversions and
    shared harvest state are read separately so they cannot go stale in that
    cache. Facades never disclose interior resources. This never initializes or
    mutates simulation state, rooms, player discovery or save data.
    """
    from engine import resource_nodes, geology, geology_events, geology_impacts
    details = getattr(world, 'room_details', {})
    living_state = getattr(world, 'living_state', None) or {}
    parcels = (living_state.get('settlements') or {}).get('parcels') or {}
    for tile in visual.get('tiles', []):
        tile.pop('surface', None)
        tile.pop('geology', None)
        tile.pop('effects', None)
        tile.pop('impacts', None)
        rid = tile.get('id')
        if tile.get('exterior') or rid not in world.rooms:
            continue
        if tile.get('visited') is False:
            # A visible neighbouring house or shop is recognisable before entry.
            # Keep resource state, occupants, ownership and remote details hidden.
            use = land_use_for(details.get(rid, {}), parcels.get(rid))
            if tile.get('visibility') == 'visible' and use in {'house', 'rental', 'business'}:
                tile['surface'] = {'land_use': use}
            continue
        authored_geology = geology.room_geology(world, rid)
        if authored_geology:
            tile['geology'] = authored_geology
        effects = geology_events.room_effects(world, rid)
        if effects:
            tile['effects'] = effects
        # Persisted consequences are separate from short-lived event artwork.
        # Never serialize event targets, building membership, unknown routes,
        # or actor exposure through the discovered-room map projection.
        impact = geology_impacts.room_view(world, rid)
        def cause(row):return {'cause':'storm'} if row.get('type')=='storm' else {}
        structures = [dict(**cause(row), condition=row['condition'], unusable=row['unusable'],
                           remaining_minutes=row['remaining_minutes'])
                      for row in impact['structures']]
        routes = [dict(**cause(row), direction=row['direction'], remaining_minutes=row['remaining_minutes'])
                  for row in impact['routes']
                  if world.rooms[rid].exits.get(row['direction']) == row['destination']]
        resources = [dict(**cause(row), name=world.resources[row['resource']].get('name', 'Resource'),
                          remaining_minutes=row['remaining_minutes'])
                     for row in impact['resources']
                     if row['resource'] in resource_nodes.active_resources(world, rid)
                     and row['resource'] in getattr(world, 'resources', {})]
        ports = [dict(**cause(row), remaining_minutes=row['remaining_minutes'])
                 for row in impact['port_routes']]
        if structures or routes or resources or ports:
            tile['impacts'] = dict(
                condition=impact['condition'], unusable=impact['unusable'],
                remaining_minutes=max(row['remaining_minutes'] for row in structures + routes + resources + ports),
                structures=structures, routes=routes, resources=resources, port_routes=ports)
        surface = {}
        land_use = land_use_for(details.get(rid, {}), parcels.get(rid))
        if land_use:
            surface['land_use'] = land_use
        features = resource_nodes.room_features(world, rid)
        if features:
            surface['resources'] = features
        if surface:
            tile['surface'] = surface
    return visual


COLORS = {'black', 'white', 'gray', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'silver', 'gold', 'blond', 'auburn'}
COLOR_WORDS = r'(black|white|gr[ae]y|brown|red|orange|yellow|green|blue|purple|pink|silver|gold(?:en)?|blond(?:e)?|auburn)'
ACCESSORIES = {'helmet', 'hat', 'hood', 'shield', 'sword', 'staff', 'bow', 'crown', 'cloak'}
CLOTHES = {'armor', 'robe', 'tunic', 'coat', 'dress'}
SILHOUETTES = {'humanoid', 'quadruped', 'bird', 'insect', 'arachnid', 'crustacean', 'mollusk', 'reptile', 'fish', 'generic'}


def _color(value):
    value = str(value or '').lower().strip()
    value = {'grey': 'gray', 'golden': 'gold', 'blonde': 'blond'}.get(value, value)
    return value if value in COLORS else None


# Player layers are separate from NPC descriptive styling. In particular, a
# carried weapon or an old biography is never an equipped paper-doll layer.
GEAR_KINDS = {
    'body': {'armor', 'robe', 'tunic', 'coat', 'dress'},
    'head': {'helmet', 'hat', 'hood', 'crown'},
    'cloak': {'cloak'}, 'hands': {'gloves'}, 'legs': {'leggings'},
    'feet': {'boots'}, 'offhand': {'shield', 'offhand'}, 'charm': {'charm'},
    'weapon': {'sword', 'dagger', 'staff', 'bow', 'spear', 'axe', 'hammer', 'mace', 'lute', 'pick', 'weapon'},
    'other': {'generic'},
}
GEAR_WORDS = [
    ('shield', r'\b(?:shield|buckler)\b'),
    ('robe', r'\brobes?\b'), ('tunic', r'\btunics?\b'),
    ('coat', r'\bcoats?\b'), ('dress', r'\bdress\b'),
    ('armor', r'\b(?:armo[u]?r|mail|chainmail|breastplate)\b'),
    ('helmet', r'\b(?:helm|helmet)\b'), ('hat', r'\bhat\b'),
    ('hood', r'\bhood\b'), ('crown', r'\bcrown\b'),
    ('cloak', r'\b(?:cloak|cape)\b'), ('gloves', r'\b(?:gloves?|gauntlets?)\b'),
    ('leggings', r'\b(?:leggings|greaves|trousers|pants)\b'),
    ('boots', r'\b(?:boots?|shoes?)\b'), ('charm', r'\b(?:charm|amulet|pendant)\b'),
    ('sword', r'\b(?:sword|longsword|shortsword|greatsword|sabre|saber|rapier)\b'),
    ('dagger', r'\b(?:dagger|knife)\b'), ('staff', r'\b(?:staff|stave|wand)\b'),
    ('bow', r'\b(?:bow|longbow|shortbow|crossbow)\b'),
    ('spear', r'\b(?:spear|pike|lance)\b'), ('axe', r'\b(?:axe|battleaxe|hatchet)\b'),
    ('hammer', r'\b(?:hammer|warhammer)\b'), ('mace', r'\b(?:mace|club|cudgel)\b'),
    ('lute', r'\blute\b'), ('pick', r'\bpick(?:axe)?\b'),
]
GEAR_MATERIALS = {'iron', 'steel', 'leather', 'woven', 'cloth', 'wood', 'crystal', 'silk', 'wool', 'fur', 'hide', 'chitin', 'bone', 'bronze', 'copper', 'silver', 'gold', 'linen', 'cotton', 'velvet', 'canvas', 'scale'}
PLAYER_FEATURES = {
    'silhouette': SILHOUETTES,
    'hair_style': {'bald', 'short', 'long', 'braided'},
    'facial_hair': {'none', 'beard', 'mustache'},
    'stature': {'short', 'average', 'tall'},
    'build': {'slim', 'average', 'broad'},
    'ears': {'round', 'pointed'},
}
SKIN_COLORS = COLORS | {'pale', 'fair', 'tan', 'olive', 'dark'}


def _affirmative_description(text):
    """Conservative explicit clauses, not negated or hypothetical attributes."""
    return ' '.join(part for part in re.split(r'[.;,!]', str(text or '').lower())
                    if not re.search(r"\b(?:no|not|without|lacks?|never|isn't|isnt|used to|wishes?|wants?|would|could|might|may)\b", part))


def _player_equipment(world, ent):
    """The complete visual protocol remains a concrete ordered list."""
    return list(_equipment_rows(world, ent))


def _equipment_rows(world, ent):
    """Yield the same rows lazily for callers needing only one visible layer."""
    slots = {
        'armor': 'body', 'body': 'body', 'torso': 'body', 'chest': 'body',
        'appearance_tunic': 'body', 'head': 'head', 'appearance_hat': 'head',
        'cloak': 'cloak', 'back': 'cloak', 'appearance_cloak': 'cloak',
        'hands': 'hands', 'legs': 'legs', 'feet': 'feet', 'weapon': 'weapon',
        'mainhand': 'weapon', 'offhand': 'offhand', 'charm': 'charm',
    }
    defaults = dict(body='armor', head='helmet', cloak='cloak', hands='gloves',
                    legs='leggings', feet='boots', weapon='weapon', offhand='offhand', charm='charm', other='generic')
    for slot, iid in sorted(ent.equipped.items()):
        item = world.items.get(iid) or {}
        name = str(item.get('name') or iid)
        config = item.get('appearance') or {}
        config = config if isinstance(config, dict) else {}
        expected_layer = slots.get(slot, 'other')
        allowed = GEAR_KINDS.get(expected_layer, set())
        if expected_layer == 'body':
            allowed = allowed | {'shield'}  # Legacy shields use the armor slot.
        if expected_layer == 'other':
            allowed = set().union(*GEAR_KINDS.values())
        kind = str(config.get('kind', '')).lower()
        if not any(kind in kinds for kinds in GEAR_KINDS.values()):
            kind = next((kind for kind, pattern in GEAR_WORDS if kind in allowed and re.search(pattern, name.lower())), '') if item else ''
        layer = next((layer for layer, kinds in GEAR_KINDS.items() if kind in kinds), slots.get(slot, 'other'))
        # A missing item definition has no known appearance. Preserve its exact
        # equipped identity for the label but don't invent a sword/armor sprite.
        if not item:
            layer, kind = 'other', 'generic'
        elif not kind:
            if layer == 'body' and item.get('type') != 'armor':
                layer, kind = 'other', 'generic'
            else:
                kind = {'appearance_tunic': 'tunic', 'appearance_hat': 'hat'}.get(slot, defaults[layer])
        row = dict(slot=slot, item_id=iid, name=name, layer=layer, kind=kind)
        # Optional authored construction fields are additive to the original
        # version-1 protocol. Old packets/items retain their exact fallback.
        for field, allowed_values in (
                ('shape', VISUAL_SHAPES), ('pattern', VISUAL_PATTERNS),
                ('detail', VISUAL_DETAILS), ('silhouette', VISUAL_SILHOUETTES)):
            value = str(config.get(field, '')).lower()
            if value in allowed_values:
                row[field] = value
        trim_color = _color(config.get('trim_color'))
        if trim_color:
            row['trim_color'] = trim_color
        color = _color(config.get('color') or item.get('color'))
        if not color:
            match = re.search(r'\b' + COLOR_WORDS + r'\b', name.lower())
            color = _color(match.group(1)) if match else None
        if color:
            row['color'] = color
        material = str(config.get('material') or item.get('material') or '').lower()
        material = {'wooden': 'wood'}.get(material, material)
        if material not in GEAR_MATERIALS | VISUAL_MATERIALS:
            match = re.search(r'\b(iron|steel|leather|woven|cloth|wood(?:en)?|crystal|silk|wool|fur|hide|chitin|bone)\b', name.lower())
            material = {'wooden': 'wood'}.get(match.group(1), match.group(1)) if match else None
        if material:
            row['material'] = material
        from engine.art_catalog import bind
        bind(row,item.get("sprite_binding"))
        yield row


def player_paperdoll(world, ent):
    """Read only confirmed equipment and explicitly authored player features.

    Race/class IDs remain labels on the actor. They never imply skin, ears,
    beard, body proportions, or starting equipment being currently equipped.
    Unknown appearance fields are omitted so the client can use a neutral base.
    """
    features, sources = {}, {}

    def put(field, value, source):
        if value is not None and value != '' and field not in features:
            features[field] = value
            sources[field] = source

    hair = ent.progress.get('hair')
    put('hair_color', _color(hair), 'configuration')
    if hair == 'neatly trimmed':
        put('hair_style', 'short', 'configuration')
    for config, source in [(ent.progress.get('character_style'), 'configuration'),
                           (getattr(ent, 'appearance', None), 'configuration'),
                           ((world.races.get(ent.race) or {}).get('appearance'), 'race_configuration')]:
        if not isinstance(config, dict):
            continue
        for field, allowed in PLAYER_FEATURES.items():
            value = str(config.get(field, '')).lower()
            if value in allowed:
                put(field, value, source)
        for field in ('hair_color', 'body_color'):
            put(field, _color(config.get(field)), source)
        value = str(config.get('skin_color', '')).lower()
        if value in SKIN_COLORS:
            put('skin_color', _color(value) or value, source)
        for field in ('horns', 'tail'):
            if isinstance(config.get(field), bool):
                put(field, config[field], source)

    description = _affirmative_description(ent.description)
    for field, pattern in [
        ('hair_color', COLOR_WORDS + r'[- ]+(?:hair|haired|braids|locks)\b'),
        ('hair_color', r'\bhair (?:is |of )?' + COLOR_WORDS + r'\b'),
        ('body_color', COLOR_WORDS + r'[- ]+(?:fur|scales|feathers)\b'),
        ('skin_color', r'\b(pale|fair|tan|olive|dark|' + COLOR_WORDS[1:-1] + r')[- ]+(?:skin|skinned)\b'),
    ]:
        match = re.search(pattern, description)
        if match:
            put(field, _color(match.group(1)) or match.group(1), 'description')
    for field, value, pattern in [
        ('hair_style', 'bald', r'\b(?:is bald|bald head|bald headed)\b'),
        ('hair_style', 'short', r'\bshort[- ](?:hair|haired)\b'),
        ('hair_style', 'long', r'\blong[- ](?:hair|haired)\b'),
        ('hair_style', 'braided', r'\b(?:braided hair|hair in braids)\b'),
        ('facial_hair', 'none', r'\bclean[- ]shaven\b'),
        ('facial_hair', 'beard', r'\b(?:has|with|wears|sporting) (?:a |an )?(?:\w+ )?beard\b'),
        ('facial_hair', 'mustache', r'\b(?:has|with|wears|sporting) (?:a |an )?(?:\w+ )?(?:mustache|moustache)\b'),
        ('stature', 'short', r'\b(?:short stature|short in stature)\b'),
        ('stature', 'tall', r'\b(?:tall stature|tall in stature)\b'),
        ('build', 'slim', r'\b(?:slim|slender)[- ](?:build|built|frame)\b'),
        ('build', 'broad', r'\b(?:broad|stocky)[- ](?:build|built|frame)\b'),
        ('ears', 'pointed', r'\bpointed ears\b'),
        ('ears', 'round', r'\bround(?:ed)? ears\b'),
        ('horns', True, r'\b(?:has|with) (?:a pair of )?(?:\w+ )?horns\b'),
        ('tail', True, r'\b(?:has|with) (?:a |an )?(?:\w+ )?tail\b'),
    ]:
        if re.search(pattern, description):
            put(field, value, 'description')
    from engine.character_style import choices, selected_accent
    opts=choices(world.races.get(ent.race) or {},world.classes.get(ent.char_class) or {})
    return dict(version=1, characteristics=features, equipment=_player_equipment(world, ent), sources=sources,
                family=opts['family'],accent=selected_accent(ent.progress.get('character_style') or {},opts))


def player_actions(world, ent):
    """Current-room owned camp only; do not initialize state or leak its room."""
    state = getattr(world, 'living_state', None) or {}
    camps = state.get('camps') or {}
    camp = camps.get(ent.id) or {}
    pitched = bool(camp.get('room') == ent.location and camp.get('tent'))
    return dict(camping=pitched, tent=pitched, campfire=pitched and camp.get('fire') is True)


def _player_appearance(ent, race, char_class, paperdoll):
    """Compatibility projection, with the same equipment-only rule as layers."""
    features = paperdoll['characteristics']
    result = dict(seed='|'.join(str(v) for v in (ent.id, race, char_class)), creature=False,
                  silhouette=features.get('silhouette', 'humanoid'), accessories=[])
    sources = {'silhouette': paperdoll['sources'].get('silhouette', 'fallback')}
    for field in ('hair_color', 'body_color'):
        if field in features:
            result[field] = features[field]
            sources[field] = paperdoll['sources'][field]
    for item in paperdoll['equipment']:
        if item['layer'] == 'body' and item['kind'] in CLOTHES:
            result['clothing'] = item['kind']
            sources['clothing'] = 'equipment'
            if item.get('color'):
                result['clothing_color'] = item['color']
                sources['clothing_color'] = 'equipment'
        if item['kind'] in ACCESSORIES:
            result['accessories'].append(item['kind'])
            sources['accessories.' + item['kind']] = 'equipment'
    result['accessories'] = sorted(set(result['accessories']))
    result['sources'] = sources
    result['inferred_style'] = any(source in {'description', 'fallback'} for source in sources.values())
    return result


def appearance_for(world, ent, definition, race, char_class, species, creature):
    """Small conservative sprite vocabulary, never a generated biography.

    Structured descriptors and equipped objects outrank text. Unspecified colors
    remain unspecified; the client can use its neutral fallback palette.
    """
    if ent.is_player:
        return _player_appearance(ent, race, char_class, player_paperdoll(world, ent))
    result = dict(seed='|'.join(str(v) for v in (ent.id, race, char_class)), creature=creature)
    sources = {}
    accessories = set()

    def put(field, value, source):
        if value and field not in result:
            result[field] = value
            sources[field] = source

    config = getattr(ent, 'appearance', None) or definition.get('appearance') or {}
    if not isinstance(config, dict):
        config = {}
    for field, allowed in [('silhouette', SILHOUETTES), ('clothing', CLOTHES)]:
        value = str(config.get(field, '')).lower()
        if value in allowed:
            put(field, value, 'configuration')
    for field in ('clothing_color', 'hair_color', 'body_color'):
        put(field, _color(config.get(field) or definition.get(field)), 'configuration')
    for accessory in config.get('accessories', []) if isinstance(config.get('accessories', []), list) else []:
        if accessory in ACCESSORIES:
            accessories.add(accessory)
            sources['accessories.' + accessory] = 'configuration'
    # The existing barber customization is a saved explicit color choice.
    put('hair_color', _color(ent.progress.get('hair')), 'configuration')

    category = str(species.get('category', '')).lower()
    species_name = str(species.get('name', '')).lower()
    shape = {'bird': 'bird', 'insect': 'insect', 'arachnid': 'arachnid', 'crustacean': 'crustacean', 'mollusk': 'mollusk', 'reptile': 'reptile', 'fish': 'fish'}.get(category)
    if category == 'mammal' and re.search(r'\b(wolf|dog|cat|cattle|goat|sheep|pig|horse|donkey|deer|rabbit|fox|beaver|otter|bison|alpaca|badger)\b', species_name):
        shape = 'quadruped'
    put('silhouette', shape, 'taxonomy')

    def parse(text, source):
        text = re.sub(r'\bhelm\b', 'helmet', str(text or '').lower())
        # Ignore negated descriptive clauses instead of drawing absent gear.
        text = ' '.join(part for part in re.split(r'[.;,!]', text) if not re.search(r'\b(no|not|without|lacks|never|sells|selling|repairs|repairing|makes|making|crafts|crafting)\b', part))
        for pattern, value in [(r'\barmo(?:u)?r(?:ed)?\b|\bplate mail\b|\bchainmail\b', 'armor'), (r'\brobes?\b', 'robe'), (r'\btunic\b', 'tunic'), (r'\bcoat\b', 'coat'), (r'\bdress\b', 'dress')]:
            if re.search(pattern, text):
                put('clothing', value, source)
                break
        match = re.search(COLOR_WORDS + r'[- ]+(?:\w+[- ]+){0,1}(?:robes?|tunic|coat|dress|armo(?:u)?r)\b', text)
        if match:
            put('clothing_color', _color(match.group(1)), source)
        match = re.search(COLOR_WORDS + r'[- ]+(?:hair|haired|braids|locks)\b', text)
        if not match:
            match = re.search(r'\bhair (?:is |of )?' + COLOR_WORDS + r'\b', text)
        if match:
            put('hair_color', _color(match.group(1)), source)
        match = re.search(COLOR_WORDS + r'[- ]+(?:fur|scales|feathers|wolf|dog|cat|horse|bird|dragon)\b', text)
        if match:
            put('body_color', _color(match.group(1)), source)
        for accessory in ACCESSORIES:
            # Equipment names are explicit possession; prose needs a wearing or
            # carrying statement, or a concrete material/color adjective.
            pattern = r'\b(?:wears?|wearing|carries|carrying|holds?|holding|wields?|wielding|with) (?:a |an |the |his |her |their )?(?:\w+ ){0,2}' + accessory + r'\b'
            material = r'\b(?:iron|steel|wooden|leather|' + COLOR_WORDS[1:-1] + r') ' + accessory + r'\b'
            if (source == 'equipment' and re.search(r'\b' + accessory + r'\b', text)) or re.search(pattern, text) or re.search(material, text):
                if accessory not in accessories:
                    accessories.add(accessory)
                    sources['accessories.' + accessory] = source

    for slot, iid in sorted(ent.equipped.items()):
        item = world.items.get(iid, {})
        if item.get('type') == 'armor' and slot in {'armor', 'body', 'torso', 'chest'}:
            put('clothing', 'armor', 'equipment')
        parse(item.get('name', '') + '. ' + item.get('description', ''), 'equipment')
    description = ent.description or definition.get('description') or ''
    parse(description, 'description')
    if 'silhouette' not in result:
        # Description-based anatomy is explicitly marked as interpreted style.
        if re.search(r'\b(wolf|dog|cat|horse|deer|fox|bear)\b', description.lower()) and creature:
            put('silhouette', 'quadruped', 'description')
        else:
            put('silhouette', 'generic' if creature else 'humanoid', 'fallback')
    result['accessories'] = sorted(accessories)
    result['sources'] = sources
    result['inferred_style'] = any(source in {'description', 'fallback'} for source in sources.values())
    return result


def actor_portrait(world,ent,player_id):
    definition = world.npcs.get(ent.source_def, {}) if not ent.is_player else {}
    race = ent.race or definition.get('race') or ''
    char_class = ent.char_class or definition.get('char_class') or definition.get('class') or ''
    profile = definition.get('social_profile') or {}
    species_id = definition.get('species') or profile.get('species')
    species = getattr(world, 'species', {}).get(species_id, {})
    creature = not ent.is_player and (definition.get('sentient') is False or profile.get('sentient') is False or species.get('category') in {'mammal', 'bird', 'fish', 'insect', 'arachnid', 'crustacean', 'mollusk', 'reptile', 'amphibian', 'animal'})
    actor = dict(id=ent.id, name=ent.name, room=ent.location, kind='self' if ent.id == player_id else 'player' if ent.is_player else 'npc', race=race, char_class=char_class)
    if ent.is_player:
        actor['paperdoll'] = player_paperdoll(world, ent)
        actor['actions'] = player_actions(world, ent)
        actor['appearance'] = _player_appearance(ent, race, char_class, actor['paperdoll'])
    else:
        from engine.costumes import npc_doll, subject
        actor['appearance'] = appearance_for(world, ent, definition, race, char_class, species, creature)
        body=subject(definition,creature)
        from engine.npc_activity import activity
        actor['activity']=activity(world,ent)
        if body:
            actor['subject']=body
            if body=='carriage':
                from engine import civic_program
                if civic_program.carriage_stop(world,ent)==ent.location:actor['stationary']=True
        else:actor['paperdoll']=npc_doll(world,ent,definition,actor['appearance'],_player_equipment(world,ent))
        # A raised body retains the corpse's actual appearance without copying
        # its usable equipment, inventory, coins or reward tables.
        if ent.progress.get('magic_summon_v1'):
            from copy import deepcopy
            remembered=ent.progress.get('magic_appearance_v1',{})
            for key in ('appearance','subject','paperdoll','held_gear'):
                if key in remembered:actor[key]=deepcopy(remembered[key])
    from engine import fighting_pose
    doll=actor.get('paperdoll',{})
    gear=doll.get('equipment') if doll else _player_equipment(world,ent) if ent.equipped else []
    pose=fighting_pose.project(world,ent,gear,bool(actor.get('subject')))
    if pose:
        actor['combat_pose']=pose
        if not doll and gear:actor['held_gear']=gear
    return actor


def current_actors(world, player_id, connected_players=(), *, nearby_rooms=()):
    """Viewer plus actual living occupants; no remote tracking or save changes."""
    player = world.entities[player_id]
    connected = set(connected_players) | {player_id}
    actors = []
    occupants = {ent.id: ent for ent in world.entities_in_room(player.location)}
    for room_id in nearby_rooms:
        for entity in world.entities_in_room(room_id):
            if entity.alive and not entity.is_player:occupants[entity.id]=entity
    # The viewer's saved position remains authoritative while unconscious/dead.
    occupants[player_id] = player
    from engine import speech_bubbles
    speaker, bubble = speech_bubbles.visible(world, player, occupants)
    for ent in sorted(occupants.values(), key=lambda e: e.id):
        if (ent.location != player.location and ent.location not in nearby_rooms) or (ent.is_player and ent.id not in connected):
            continue
        actor=actor_portrait(world,ent,player_id)
        if ent.id == speaker:
            actor['speech_bubble'] = bubble
        actors.append(actor)
    return actors
