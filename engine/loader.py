from engine.directions import normalize_exits
# engine/loader.py
import json
from pathlib import Path
from typing import Optional, Tuple

from engine.core import World, Room, Entity

PROJECT_ROOT = Path(__file__).parent.parent
GAMES_DIR = PROJECT_ROOT / "games"
WORLD_UPDATE_TEMPLATES = ()
DEFAULT_GAME = "default"
GAME_DIR = GAMES_DIR / DEFAULT_GAME
DATA_DIR = GAME_DIR # legacy alias; kept as monkeypatch target for tests

def set_game_dir(path):
    global GAME_DIR, DATA_DIR
    GAME_DIR = Path(path)
    DATA_DIR = GAME_DIR

def list_games():
    if not GAMES_DIR.exists():
        return []
    games = []
    for child in sorted(GAMES_DIR.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        meta_path = child / "metadata.json"
        name = child.name.replace("_", " ").title()
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta.get("name", name)
            except (json.JSONDecodeError, OSError):
                pass
        
        img_dir = child / "images"
        image_url = None
        if img_dir.is_dir():
            for ext in ("jpg", "jpeg", "png", "webp"):
                if (img_dir / f"title.{ext}").exists():
                    image_url = f"/api/games/{child.name}/image"
                    break
        games.append({"slug": child.name, "name": name, "image_url": image_url})
    return games

def load_metadata(game_dir=None) -> dict:
    target_dir = Path(game_dir) if game_dir else DATA_DIR
    path = target_dir / "metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def load_json(name: str, game_dir=None):
    target_dir = Path(game_dir) if game_dir else DATA_DIR
    path = target_dir / name
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return json.loads(text)

def load_shortcuts(game_dir=None) -> dict:
    target_dir = Path(game_dir) if game_dir else DATA_DIR
    path = target_dir / "shortcuts.json"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)

def ensure_character_options(game_dir=None):
    """Create races/classes/sexes/abilities files if missing."""
    if game_dir is None:
        game_dir = DATA_DIR
    game_dir = Path(game_dir)
    defaults = {
        "races.json": [
            {"id": "human", "name": "Human",
             "description": "Adaptable and creative."},
        ],
        "classes.json": [
            {"id": "fighter", "name": "Fighter",
             "description": "Master of arms and armor."},
        ],
        "sexes.json": [
            {"id": "male", "name": "Male"},
            {"id": "female", "name": "Female"},
            {"id": "nonbinary", "name": "Non-binary"},
            {"id": "unspecified", "name": "Prefer not to say"},
        ],
        "abilities.json": [],
    }
    for name, default in defaults.items():
        path = game_dir / name
        if not path.exists():
            try:
                path.write_text(json.dumps(default, indent=2) + "\n",
                                encoding="utf-8")
            except OSError:
                pass

def build_world(game_dir=None) -> World:
    target_dir = Path(game_dir) if game_dir else DATA_DIR
    if (target_dir / 'history-build.pending').exists():
        raise ValueError('Historical world publication is incomplete; do not play this staged world.')
    from engine import world_additions
    patch=world_additions.additions(target_dir,GAMES_DIR,template_dirs=WORLD_UPDATE_TEMPLATES)
    def read_records(name, folder):
        return world_additions.records(name,load_json(name,folder),patch)
    world = World()
    world.game_dir = str(target_dir.resolve())
    world._pixel_art_update = {'pixel_art': patch['pixel_art']} if patch and patch.get('pixel_art') else None
    world.room_details = {r["id"]: r for r in read_records("rooms.json", target_dir)}
    for name in ("recipes", "resources", "encounters", "interactions", "species"):
        setattr(world, name, {r["id"]: r for r in read_records(name+".json", target_dir)})
    
    for r in world.room_details.values():
        world.add_room(Room(
            id=r["id"], name=r["name"], description=r["description"],
            exits=normalize_exits(r.get("exits", {})),
            items=r.get("items", []),
            description_variants=r.get("description_variants", []),
            group=r.get("group"),
            spawners=r.get("spawners", []),
            **{k: r[k] for k in ("map_x", "map_y", "map_z", "map_symbol", "map_visibility") if k in r},
        ))
        
    from engine.shield_compat import normalize_item
    world.items = {i["id"]: normalize_item(i) for i in read_records("items.json", target_dir)}
    world.npcs = {n["id"]: n for n in read_records("npcs.json", target_dir)}
    from engine import loot_tables
    loot_errors = loot_tables.validate({'npc': list(world.npcs.values()), 'item': list(world.items.values())})
    if loot_errors:
        raise ValueError('Combat loot content: ' + '; '.join(loot_errors))
    
    # Initialize shop state from NPC stocks
    world.shop_state = {}
    for npc_id, npc_def in world.npcs.items():
        stock = npc_def.get("stock") or []
        if not stock:
            continue
        world.shop_state[npc_id] = {}
        for entry in stock:
            item_id = entry.get("item")
            if not item_id:
                continue
            qty = int(entry.get("qty", 1) or 0)
            world.shop_state[npc_id][item_id] = qty
            
    world.quests = {q["id"]: q for q in read_records("quests.json", target_dir)}
    world.buildings = {b["id"]: b for b in read_records("buildings.json", target_dir)}
    world.groups = {g["id"]: g for g in read_records("groups.json", target_dir)}
    world.races = {r["id"]: r for r in read_records("races.json", target_dir)}
    world.classes = {c["id"]: c for c in read_records("classes.json", target_dir)}
    world.sexes = {s["id"]: s for s in read_records("sexes.json", target_dir)}
    
    world.metadata = world_additions.metadata(load_metadata(target_dir),patch)
    from engine import travel_pacing
    travel_errors=travel_pacing.validate(world.metadata)
    if travel_errors:raise ValueError('Travel content: '+'; '.join(travel_errors))
    from engine import dynamic_diplomacy
    dynamic_diplomacy.validate(world.metadata.get("dynamic_diplomacy",{}),world.groups)
    from engine import progression
    progression_errors=progression.validate_config(world.metadata.get("progression",{}))+progression.validate({"quest":list(world.quests.values()),"class":list(world.classes.values())})
    if progression_errors:raise ValueError("Progression content: "+"; ".join(progression_errors))
    world.start_room = world.metadata.get("start_room")
    world.abilities = {a["id"]: a for a in read_records("abilities.json", target_dir)}
    world.shortcuts = load_shortcuts(target_dir)
    # Population authoring is opt-in. Loading does not create residents or
    # anchor their ages before a saved clock and identities have been restored.
    world.population_manifest = read_records('population.json', target_dir)
    from engine import life_stages, population_health, population_content, npc_life
    population_data = {'npc': list(world.npcs.values()), 'race': list(world.races.values()),
                       'species': list(world.species.values()), 'room': list(world.room_details.values()),
                       'group': list(world.groups.values()), 'encounter': list(world.encounters.values())}
    population_errors = (npc_life.validate(population_data) + life_stages.validate(population_data, world.metadata) +
                         population_health.validate(population_data, world.metadata) +
                         population_content.validate_manifest(population_data, world.population_manifest))
    if population_errors:
        raise ValueError('Population content: ' + '; '.join(population_errors))
    
    from engine import wildlands
    from engine.world_package import rules
    world.rules = rules(target_dir,world.room_details,world.npcs)
    if patch:
        world.rules=world_additions.rules(world.rules,patch)
        from engine import regional_rules
        regional_rules.validate(world.rules,world.room_details,world.npcs)
    wildlands.install(world)
    from engine import regional_world
    regional_world.install(world)
    return world

def start_room_for(world: World) -> str:
    if not world.rooms:
        raise RuntimeError("world has no rooms - cannot pick a start room")
    if world.start_room and world.start_room in world.rooms:
        return world.start_room
    return next(iter(world.rooms))

def validate_world(world: World):
    errors = []
    warnings = []
    from engine import travel_pacing
    errors.extend(travel_pacing.validate(world.metadata))
    from engine import loot_tables
    errors.extend(loot_tables.validate({'npc': list(world.npcs.values()), 'item': list(world.items.values())}))
    room_ids = set(world.rooms.keys())
    item_ids = set(world.items.keys())
    npc_ids = set(world.npcs.keys())
    group_ids = set(world.groups.keys())
    building_ids = set(world.buildings.keys())
    
    for room in world.rooms.values():
        for direction, target in room.exits.items():
            if target not in room_ids:
                errors.append(f"room '{room.id}' exit {direction} -> '{target}' (no such room)")
                    
    for room in world.rooms.values():
        for item_id in room.items:
            if item_id not in item_ids:
                warnings.append(f"room '{room.id}' floor item '{item_id}' (no such item)")
                    
    for room in world.rooms.values():
        if room.group and room.group not in group_ids:
            warnings.append(f"room '{room.id}' group '{room.group}' (no such group)")
        for idx, spawner in enumerate(room.spawners or []):
            npc_ref = spawner.get("npc")
            if npc_ref and npc_ref not in npc_ids:
                warnings.append(f"room '{room.id}' spawner[{idx}] npc '{npc_ref}' (no such npc)")
                    
    npc_in_roster = set()
    from engine import regional_rules
    npc_in_roster.update(regional_rules.managed_npcs(getattr(world,'rules',{}),world.room_details))
    npc_in_roster.update(spawner.get('npc') for room in world.rooms.values() for spawner in (room.spawners or []))
    for grp in world.groups.values():
        for n in grp.get("roster", []) or []:
            npc_in_roster.add(n)
            
    for npc_id, npc_def in world.npcs.items():
        for field in ("spawn_room", "workplace_room", "guard_room"):
            val = npc_def.get(field)
            if val and val not in room_ids:
                warnings.append(f"npc '{npc_id}' {field} '{val}' (no such room)")
        for field in ("workplace_building", "guard_building"):
            val = npc_def.get(field)
            if val and val not in building_ids:
                warnings.append(f"npc '{npc_id}' {field} '{val}' (no such building)")
        grp = npc_def.get("group")
        if grp and grp not in group_ids:
            warnings.append(f"npc '{npc_id}' group '{grp}' (no such group)")
            
        pm = npc_def.get("patrol_mode")
        if pm and pm not in ("random", "loop", "none"):
            warnings.append(f"npc '{npc_id}' patrol_mode '{pm}' must be random, loop, or none")
        pc = npc_def.get("patrol_chance")
        if pc is not None:
            try:
                if float(pc) < 0 or float(pc) > 1:
                    warnings.append(f"npc '{npc_id}' patrol_chance must be 0.0-1.0")
            except (TypeError, ValueError):
                warnings.append(f"npc '{npc_id}' patrol_chance is not a number")
        has_location = any(npc_def.get(f) for f in ("spawn_room", "workplace_room", "workplace_building", "guard_room", "guard_building"))
        if not has_location and npc_id not in npc_in_roster:
            warnings.append(f"npc '{npc_id}' has no spawn/workplace/guard location and is not in any roster (will never appear)")
                
        rc = npc_def.get("race")
        if rc and rc not in world.races:
            warnings.append(f"npc '{npc_id}' race '{rc}' (no such race)")
        cl = npc_def.get("class") or npc_def.get("char_class")
        if cl and cl not in world.classes:
            warnings.append(f"npc '{npc_id}' class '{cl}' (no such class)")
        sx = npc_def.get("sex")
        if sx and sx not in world.sexes:
            warnings.append(f"npc '{npc_id}' sex '{sx}' (no such sex)")
            
        for entry in (npc_def.get("stock") or []):
            item_ref = entry.get("item")
            if item_ref and item_ref not in item_ids:
                warnings.append(f"npc '{npc_id}' stock item '{item_ref}' (no such item)")
                
    for bld_id, bld in world.buildings.items():
        for room_id in bld.get("rooms", []):
            if room_id not in room_ids:
                warnings.append(f"building '{bld_id}' room '{room_id}' (no such room)")
        grp = bld.get("group")
        if grp and grp not in group_ids:
            warnings.append(f"building '{bld_id}' group '{grp}' (no such group)")
            
    for grp_id, grp in world.groups.items():
        for h in grp.get("hostile_to", []) or []:
            if h == "*": continue
            if h not in group_ids:
                warnings.append(f"group '{grp_id}' hostile_to '{h}' (no such group)")
        for npc_ref in grp.get("roster", []) or []:
            if npc_ref not in npc_ids:
                warnings.append(f"group '{grp_id}' roster '{npc_ref}' (no such npc)")
        sr = grp.get("start_room")
        if sr and sr not in room_ids:
            warnings.append(f"group '{grp_id}' start_room '{sr}' (no such room)")
            
    from engine import geology, geology_events
    from engine.geology_impacts import world_data
    geology_data = world_data(world)
    errors.extend(geology.validate(geology_data))
    errors.extend(geology_events.validate(geology_data, world.metadata))
    return errors, warnings

def spawn_npcs(world: World):
    def _spawn_location(npc_def: dict) -> Optional[str]:
        spawn = npc_def.get("spawn_room")
        if spawn and spawn in world.rooms: return spawn
        wp_room = npc_def.get("workplace_room")
        if wp_room and wp_room in world.rooms: return wp_room
        wp_bld = npc_def.get("workplace_building")
        if wp_bld:
            bld = world.buildings.get(wp_bld)
            if bld and bld.get("rooms"):
                first = bld["rooms"][0]
                if first in world.rooms: return first
        gr_room = npc_def.get("guard_room")
        if gr_room and gr_room in world.rooms: return gr_room
        gr_bld = npc_def.get("guard_building")
        if gr_bld:
            bld = world.buildings.get(gr_bld)
            if bld and bld.get("rooms"):
                first = bld["rooms"][0]
                if first in world.rooms: return first
        return None

    for npc_def in world.npcs.values():
        if npc_def.get("spawn_managed"):continue
        if npc_def["id"] in world.killed_npcs:
            continue
        location = _spawn_location(npc_def)
        if not location:
            continue
        ent = Entity(
            id=f"npc:{npc_def['id']}",
            name=npc_def["name"],
            hp=npc_def["hp"], max_hp=npc_def["hp"],
            attack=npc_def["attack"], defense=npc_def["defense"],
            gold=npc_def.get("gold", 0),
            is_player=False,
            source_def=npc_def["id"],
            group_id=npc_def.get("group") or None,
            inventory=list(npc_def.get("inventory",[])),
            equipped=dict(npc_def.get("equipped",{})),
        )
        if 'historical_initial_hp' in npc_def:
            initial_hp = npc_def['historical_initial_hp']
            if type(initial_hp) is not int or not 0 < initial_hp <= ent.max_hp:
                raise ValueError('Invalid historical initial HP')
            ent.hp = initial_hp
        if npc_def.get("race"): ent.race = npc_def["race"]
        _cls = npc_def.get("class") or npc_def.get("char_class")
        if _cls: ent.char_class = _cls
        if npc_def.get("sex"): ent.sex = npc_def["sex"]
        if npc_def.get("first_name"): ent.first_name = npc_def["first_name"]
        if npc_def.get("last_name"): ent.last_name = npc_def["last_name"]
        if npc_def.get("description"): ent.description = npc_def["description"]
        if npc_def.get("stats"): ent.stats = dict(npc_def["stats"])
        if npc_def.get("abilities"): ent.abilities = list(npc_def["abilities"])
            
        from engine import names
        names.assign(world,ent)
        world.add_entity(ent, location)
