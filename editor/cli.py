from engine.directions import normalize_exits, direction as canonical_direction
# editor/cli.py
import json
import os
import shlex
import socket
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "games" / "default"
GAMES_DIR = Path(__file__).parent.parent / "games"
WS_PORT = 8765


OPPOSITE_DIRECTIONS = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "down", "down": "up",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
    "in": "out", "out": "in",
    "enter": "exit", "exit": "enter"
}

FILE_MAP = {
    "room": "rooms.json",
    "item": "items.json",
    "npc": "npcs.json",
    "quest": "quests.json",
    "building": "buildings.json",
    "group": "groups.json",
    "race": "races.json",
    "class": "classes.json",
    "sex": "sexes.json",
    "ability": "abilities.json",
    "recipe": "recipes.json",
    "resource": "resources.json",
    "encounter": "encounters.json",
    "interaction": "interactions.json",
    "species": "species.json",
}

DEFAULT_SHORTCUTS = {
    "n": "go north", "s": "go south",
    "e": "go east", "w": "go west",
    "ne": "go northeast", "nw": "go northwest",
    "se": "go southeast", "sw": "go southwest",
    "u": "go up", "d": "go down",
}

HELP_TEXT = """\
Editor commands:
  list <type>                          List entries
  show <type> <id>                     Print full JSON of an entry
  new <type> <id>                      Create a new entry with defaults
  copy <type> <src_id> [new_id]        Duplicate (resets location/death)
  edit <type> <id> <field> <value>     Set a scalar field (int if numeric)
  setfield <type> <id> <field> <json>  Set any field to parsed JSON
  delete <type> <id>                   Delete an entry
  addexit <room> <dir> <target>        Add one exit
  rmexit <room> <dir>                  Remove one exit
  link <room> <dir> <other>            Add exits in both directions
  placeitem <room> <item>              Place an item into a room
  removeitem <room> <item>             Remove an item from a room
  validate                             Check referential integrity
  save                                 Write changes to disk
  revert                               Reload from disk
  creategame <slug> <name...> [--starter]
                                       Scaffold a new game
  help                                 This message
  quit                                 Leave
"""

def _write_blank_content(gd: Path):
    (gd / "rooms.json").write_text(json.dumps([
        {"id": "start", "name": "Start",
         "description": "The beginning.", "exits": {}, "items": []},
    ], indent=2) + "\n")
    for f in ("items", "npcs", "quests", "buildings", "groups", "abilities"):
        (gd / f"{f}.json").write_text("[]\n")
    (gd / "races.json").write_text(json.dumps([
        {"id": "human", "name": "Human", "description": "Adaptable and creative."}
    ], indent=2) + "\n")
    (gd / "classes.json").write_text(json.dumps([
        {"id": "fighter", "name": "Fighter", "description": "Master of arms and armor."}
    ], indent=2) + "\n")
    (gd / "sexes.json").write_text(json.dumps([
        {"id": "male", "name": "Male"}, {"id": "female", "name": "Female"},
        {"id": "nonbinary", "name": "Non-binary"}, {"id": "unspecified", "name": "Prefer not to say"}
    ], indent=2) + "\n")
    (gd / "shortcuts.json").write_text(json.dumps(DEFAULT_SHORTCUTS, indent=2) + "\n")

def _write_starter_content(gd: Path):
    (gd / "rooms.json").write_text(json.dumps([
        {"id": "start", "name": "Village Square", "description": "A cobbled square. The inn is north.", "exits": {"north": "inn", "east": "woods"}, "items": []},
        {"id": "inn", "name": "Common Room", "description": "Warm light, low beams. A trapdoor leads down.", "exits": {"south": "start", "down": "cellar"}, "items": ["bread", "rusty_blade", "leather_vest"]},
        {"id": "cellar", "name": "Cellar", "description": "Damp stone and barrels. Something moves.", "description_variants": [{"when": {"killed": ["giant_rat"]}, "text": "All is quiet now."}], "exits": {"up": "inn"}, "items": []},
        {"id": "woods", "name": "Whispering Woods", "description": "Pale trunks lean close.", "group": "wild_animals", "exits": {"west": "start"}, "items": []},
    ], indent=2) + "\n")

    (gd / "items.json").write_text(json.dumps([
        {"id": "bread", "name": "Bread", "type": "consumable", "value": 1, "heal": 10, "description": "A crusty loaf."},
        {"id": "stew", "name": "Stew", "type": "consumable", "value": 3, "heal": 15, "description": "Thick and hearty."},
        {"id": "rusty_blade", "name": "Rusty Blade", "type": "weapon", "value": 5, "attack_bonus": 2, "description": "Pitted iron."},
        {"id": "leather_vest", "name": "Leather Vest", "type": "armor", "value": 10, "defense_bonus": 1, "description": "Well-worn leather."},
        {"id": "oak_staff", "name": "Oak Staff", "type": "weapon", "value": 8, "attack_bonus": 1, "slot": "weapon", "description": "A mage's focus."},
        {"id": "robes", "name": "Robes", "type": "armor", "value": 6, "defense_bonus": 1, "slot": "armor", "description": "Simple cloth robes."},
        {"id": "short_bow", "name": "Short Bow", "type": "weapon", "value": 12, "attack_bonus": 2, "slot": "weapon", "description": "A hunter's bow."},
        {"id": "iron_sword", "name": "Iron Sword", "type": "weapon", "value": 15, "attack_bonus": 3, "slot": "weapon", "description": "A solid soldier's blade."},
        {"id": "iron_shield", "name": "Iron Shield", "type": "armor", "value": 12, "defense_bonus": 2, "slot": "armor", "description": "A round shield."},
        {"id": "dagger", "name": "Dagger", "type": "weapon", "value": 6, "attack_bonus": 1, "slot": "weapon", "description": "Small and quick."},
        {"id": "lockpicks", "name": "Lockpicks", "type": "tool", "value": 8, "description": "Fine steel picks."},
    ], indent=2) + "\n")

    (gd / "npcs.json").write_text(json.dumps([
        {"id": "giant_rat", "name": "Giant Rat", "hp": 8, "attack": 2, "defense": 0, "gold": 2, "spawn_room": "cellar", "corpse": "permanent", "corpse_name": "a rat corpse"},
        {"id": "innkeeper", "name": "Innkeeper", "role": "innkeeper", "group": "wayfarers", "hp": 10, "attack": 1, "defense": 0, "gold": 5, "workplace_room": "inn", "dialogue": "Welcome, traveler.", "greetings": {"wayfarers": "Ah, a Wayfarer!"}, "stock": [{"item": "bread", "price": 2, "qty": 10}]},
        {"id": "chef", "name": "Chef", "role": "chef", "group": "wayfarers", "hp": 8, "attack": 1, "defense": 0, "gold": 2, "workplace_room": "inn", "dialogue": "Fresh stew!", "greetings": {"wayfarers": "Hungry, friend?"}, "stock": [{"item": "stew", "price": 4, "qty": 3}]},
        {"id": "town_guard", "name": "Town Guard", "role": "guard", "group": "wayfarers", "hp": 15, "attack": 3, "defense": 2, "gold": 0, "guard_room": "start", "dialogue": "Keep the peace.", "greetings": {"wayfarers": "All quiet."}},
        {"id": "patrol_guard", "name": "Patrolling Guard", "role": "guard", "group": "wayfarers", "hp": 12, "attack": 2, "defense": 1, "gold": 0, "guard_building": "wayfarers_rest", "patrol_mode": "loop", "patrol_chance": 0.5},
        {"id": "grey_wolf", "name": "Grey Wolf", "role": "beast", "group": "wild_animals", "hp": 6, "attack": 2, "defense": 0, "gold": 0}
    ], indent=2) + "\n")

    (gd / "quests.json").write_text("[]\n")

    (gd / "buildings.json").write_text(json.dumps([
        {"id": "wayfarers_rest", "name": "The Wayfarer's Rest", "description": "An inn.", "rooms": ["inn", "cellar"]}
    ], indent=2) + "\n")

    (gd / "groups.json").write_text(json.dumps([
        {"id": "wayfarers", "name": "The Wayfarers", "description": "Travelers.", "visibility": "playable", "hostile_to": [], "roster": []},
        {"id": "wild_animals", "name": "Wild Animals", "description": "Beasts.", "visibility": "npc_only", "hostile_to": ["*"], "roster": ["grey_wolf"]}
    ], indent=2) + "\n")

    (gd / "abilities.json").write_text(json.dumps([
        {"id": "firebolt", "name": "Firebolt", "type": "spell", "target": "enemy", "description": "A searing bolt.", "power": 6, "cost_mp": 0},
        {"id": "cleave", "name": "Cleave", "type": "attack", "target": "enemy", "description": "A wide blow.", "power": 4, "cost_mp": 0}
    ], indent=2) + "\n")

    (gd / "races.json").write_text(json.dumps([
        {"id": "human", "name": "Human", "description": "Adaptable.", "bonuses": {}, "starting_abilities": []},
        {"id": "elf", "name": "Elf", "description": "Magical.", "bonuses": {"agi": 2, "int": 3}, "starting_abilities": []},
        {"id": "dwarf", "name": "Dwarf", "description": "Hardy.", "bonuses": {"str": 2, "vit": 2}, "starting_abilities": []},
        {"id": "zombie", "name": "Zombie", "description": "Undead.", "bonuses": {"str": 1, "vit": 3}, "starting_abilities": []}
    ], indent=2) + "\n")

    (gd / "classes.json").write_text(json.dumps([
        {"id": "fighter", "name": "Fighter", "description": "Arms and armor.", "starting_equipment": ["iron_sword", "iron_shield"], "starting_abilities": ["cleave"], "primary_stat": "str"},
        {"id": "mage", "name": "Mage", "description": "Spells.", "starting_equipment": ["oak_staff", "robes"], "starting_abilities": ["firebolt"], "primary_stat": "int"},
        {"id": "hunter", "name": "Hunter", "description": "Nature.", "starting_equipment": ["short_bow", "leather_vest"], "starting_abilities": [], "primary_stat": "agi"},
        {"id": "thief", "name": "Thief", "description": "Stealth.", "starting_equipment": ["dagger", "lockpicks"], "starting_abilities": [], "primary_stat": "agi"}
    ], indent=2) + "\n")

    (gd / "sexes.json").write_text(json.dumps([
        {"id": "male", "name": "Male"}, {"id": "female", "name": "Female"},
        {"id": "nonbinary", "name": "Non-binary"}, {"id": "unspecified", "name": "Prefer not to say"}
    ], indent=2) + "\n")

    (gd / "shortcuts.json").write_text(json.dumps(DEFAULT_SHORTCUTS, indent=2) + "\n")


_OPPOSITE = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "down", "down": "up",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
}


class Editor:
    def __init__(self, game_dir=None):
        if game_dir is None:
            game_dir = DATA_DIR
        self.data_dir = Path(game_dir)
        self.data = {typ: [] for typ in FILE_MAP}
        self.dirty = set()
        self._load()

    @staticmethod
    def create_game(games_dir, slug, name, template="blank"):
        import re
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", slug):
            return False, "slug must start with a letter, use lowercase/digits/underscores, max 32 chars"
        if not name or not name.strip():
            return False, "display name required"
        if template not in ("blank", "starter"):
            return False, "unknown template"
        name = name.strip()
        gd = Path(games_dir) / slug
        if gd.exists():
            return False, f"game '{slug}' already exists"
        try:
            gd.mkdir(parents=True)
            (gd / "metadata.json").write_text(json.dumps({"name": name, "start_room": "start"}, indent=2) + "\n")
            if template == "starter":
                _write_starter_content(gd)
            else:
                _write_blank_content(gd)
        except OSError as e:
            return False, f"could not create game: {e}"
        return True, f"Created game '{slug}' ({name}, {template})."

    def _load(self):
        # Population manifests are explicit authoring records, never runtime
        # saves. Reject corruption rather than losing cohort identity on Save.
        manifest_path = self.data_dir / 'population.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'version':1,'cohorts':{},'households':{}}
        if not isinstance(manifest, dict):
            raise ValueError('population.json must contain an object.')
        json.dumps(manifest, allow_nan=False)
        self.population_manifest = manifest
        self.population_manifest_dirty = False
        for typ, fname in FILE_MAP.items():
            path = self.data_dir / fname
            try:
                text = path.read_text(encoding="utf-8").strip()
                self.data[typ] = json.loads(text) if text else []
            except FileNotFoundError:
                self.data[typ] = []
            except json.JSONDecodeError as e:
                print(f"WARNING: {fname} is not valid JSON ({e}).")
                self.data[typ] = []
        self.dirty.clear()
        for room in self.data.get('room', []):
            try: clean = normalize_exits(room.get('exits', {}))
            except ValueError: continue  # Keep ambiguous content visible for correction.
            if clean != room.get('exits', {}):
                room['exits'] = clean
                self.dirty.add('room')

    def _reload(self):
        self._load()

    def _find(self, typ, ident):
        return next((x for x in self.data[typ] if x.get("id") == ident), None)

    def list_entries(self, typ):
        if typ not in self.data:
            return f"Unknown type '{typ}'."
        if not self.data[typ]:
            return f"(no {typ}s yet)"
        return "\n".join(f" {x.get('id', '?'):30} {x.get('name') or x.get('description', '')[:40]}" for x in self.data[typ])

    def show(self, typ, ident):
        obj = self._find(typ, ident)
        if obj is None:
            return f"No {typ} with id '{ident}'."
        return json.dumps(obj, indent=2)

    def item_types(self):
        types = {"misc"}
        for item in self.data["item"]:
            t = item.get("type")
            if t: types.add(t)
        return sorted(types)

    def new(self, typ, ident):
        if typ not in self.data:
            return f"Unknown type '{typ}'."
        if self._find(typ, ident):
            return f"{typ} '{ident}' already exists."
        obj = {"id": ident}
        if typ == "room":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "description_variants": [], "exits": {}, "items": [], "group": None, "spawners": []})
        elif typ == "item":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "type": "misc", "value": 1})
        elif typ == "npc":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "hp": 10, "attack": 3, "defense": 0, "gold": 1, "dialogue": "", "stock": [], "greetings": {}, "patrol_mode": "random", "patrol_chance": 0.5})
        elif typ == "quest":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "description_variants": []})
        elif typ == "building":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "rooms": [], "group": None})
        elif typ == "group":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "visibility": "playable", "hostile_to": [], "roster": []})
        elif typ == "race":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "bonuses": {"str": 0, "agi": 0, "int": 0, "vit": 0}, "starting_abilities": [], "traits": []})
        elif typ == "class":
            obj.update({"name": ident.replace("_", " ").title(), "description": "", "starting_equipment": [], "starting_abilities": [], "primary_stat": "str"})
        elif typ == "ability":
            obj.update({"name": ident.replace("_", " ").title(), "type": "spell", "target": "enemy", "description": "", "power": 0, "cost_mp": 0})
        elif typ == "sex":
            obj.update({"name": ident.replace("_", " ").title()})
        from engine.living_schema import DEFAULTS
        import copy
        for key,value in DEFAULTS.get(typ, {}).items(): obj.setdefault(key,copy.deepcopy(value))
        obj.setdefault("name",ident.replace("_"," ").title())
        obj.setdefault("description", "")
        if not obj.get("location"): obj["location"]=ident if typ=="room" else next((r["id"] for r in self.data["room"]),"")
        self.data[typ].append(obj)
        self.dirty.add(typ)
        return f"Created {typ} '{ident}'."

    def copy(self, typ, source_id, new_id=None):
        import copy as _copy
        src = self._find(typ, source_id)
        if src is None:
            return f"No {typ} with id '{source_id}'."
        if not new_id:
            base = source_id
            i = 2
            while self._find(typ, f"{base}_{i}"):
                i += 1
            new_id = f"{base}_{i}"
        if self._find(typ, new_id):
            return f"{typ} '{new_id}' already exists."
        new_obj = _copy.deepcopy(src)
        new_obj["id"] = new_id
        new_obj["name"] = new_id.replace("_", " ").title()
        if typ == "npc":
            for f in ("spawn_room", "workplace_room", "workplace_building", "guard_room", "guard_building", "corpse", "corpse_ttl", "corpse_name"):
                new_obj.pop(f, None)
        self.data[typ].append(new_obj)
        self.dirty.add(typ)
        return f"Copied {typ} '{source_id}' -> '{new_id}'."

    def setfield(self, typ, ident, field, value):
        obj = self._find(typ, ident)
        if obj is None:
            return f"No {typ} with id '{ident}'."
            
        if (typ=='room' and field in ('map_x','map_y','map_z','environment')) or (typ=='building' and field=='rooms'):
            from engine.streets import editor_collisions
            added=editor_collisions(self.data,(typ,ident,field),value)-editor_collisions(self.data)
            if added:
                (x,y),owners=sorted(added)[0]
                names=', '.join((self._find('building',b) or {}).get('name',b) for b in owners)
                raise ValueError(f'Building footprints overlap at ({x}, {y}): {names}. Choose a free tile.')
        if typ == "room" and field == "exits":
            try:
                value = normalize_exits(value)
                old_exits = obj.get("exits", {})
            except ValueError as exc:
                return "Invalid exits: " + str(exc)
            new_exits = value if isinstance(value, dict) else {}
            
            # 1. Remove reverse exits from old targets that are no longer valid
            for direction, old_target in old_exits.items():
                direction = canonical_direction(direction)
                if direction not in new_exits or new_exits[direction] != old_target:
                    rev = OPPOSITE_DIRECTIONS.get(direction)
                    if rev:
                        target_room = self._find("room", old_target)
                        if target_room and target_room.get("exits", {}).get(rev) == ident:
                            del target_room["exits"][rev]
                            self.dirty.add("room")
                            
            # 2. Add reverse exits to new targets
            for direction, target in new_exits.items():
                rev = OPPOSITE_DIRECTIONS.get(direction)
                if rev:
                    target_room = self._find("room", target)
                    if target_room:
                        if target_room.get("exits", {}).get(rev) != ident:
                            target_room.setdefault("exits", {})[rev] = ident
                            self.dirty.add("room")
                            
        if field=='location':
            if value not in {r['id'] for r in self.data['room']}:return 'Choose an existing room for location.'
            if typ=='npc':
                old=obj.get('spawn_room');obj['spawn_room']=value
                for r in self.data['room']:
                    moved=[sp for sp in r.get('spawners',[]) if sp.get('npc')==ident]
                    if moved and r['id']!=value:
                        r['spawners']=[sp for sp in r['spawners'] if sp.get('npc')!=ident]
                        self._find('room',value).setdefault('spawners',[]).extend(moved);self.dirty.add('room')
            if typ=='quest':obj['offer_room']=value
            if typ in ('resource','encounter'):
                plural=typ+'s'
                for room in self.data['room']:room[plural]=[i for i in room.get(plural,[]) if i!=ident]
                self._find('room',value).setdefault(plural,[]).append(ident);self.dirty.add('room')
            if typ=='recipe':
                for room in self.data['room']:
                    if room.get('workshop'):room['workshop']['recipes']=[i for i in room['workshop'].get('recipes',[]) if i!=ident]
                room=self._find('room',value)
                room.setdefault('workshop',{'capital':100,'interval':30,'initial_stock':{}}).setdefault('recipes',[]).append(ident)
                if obj.get('station','hand') not in room.setdefault('facilities',[]):room['facilities'].append(obj.get('station','hand'))
                self.dirty.add('room')
            if typ=='item':
                count=0
                for r in self.data['room']:
                    count+=r.get('items',[]).count(ident);r['items']=[i for i in r.get('items',[]) if i!=ident]
                if count:self._find('room',value).setdefault('items',[]).extend([ident]*count);self.dirty.add('room')
        obj[field] = value
        self.dirty.add(typ)
        return f"{typ}.{ident}.{field} = {value!r}"

    def edit(self, typ, ident, field, value):
        coerced = value
        try: coerced = int(value)
        except ValueError: pass
        return self.setfield(typ, ident, field, coerced)

    def delete(self, typ, ident):
        for i, x in enumerate(self.data[typ]):
            if x.get("id") == ident:
                self.data[typ].pop(i)
                self.dirty.add(typ)
                return f"Deleted {typ} '{ident}'."
        return f"No {typ} with id '{ident}'."

    def addexit(self, room_id, direction, target):
        direction = canonical_direction(direction)
        if target == room_id:
            return f"Cannot add exit {direction} from '{room_id}' to itself."
        room = self._find("room", room_id)
        if room is None: return f"No room '{room_id}'."
        target_room = self._find("room", target)
        missing = target_room is None
        new_exits = dict(room.get("exits", {}))
        new_exits[direction] = target
        self.setfield("room", room_id, "exits", new_exits)
        if missing: return f"Added exit {direction} -> {target} on {room_id}. (Target missing.)"
        target_exits = target_room.get("exits", {})
        if direction in target_exits and target_exits[direction] == room_id:
            return f"Added exit {direction} -> {target} on {room_id}. WARNING: impossible direction"
        return f"Added exit {direction} -> {target} on {room_id}."

    def rmexit(self, room_id, direction):
        direction = canonical_direction(direction)
        room = self._find("room", room_id)
        if room is None: return f"No room '{room_id}'."
        if direction not in room.get("exits", {}): return f"No exit '{direction}' on {room_id}."
        new_exits = dict(room.get("exits", {}))
        del new_exits[direction]
        self.setfield("room", room_id, "exits", new_exits)
        return f"Removed exit {direction} from {room_id}."

    def link(self, a, direction, b):
        direction = canonical_direction(direction)
        a_room, b_room = self._find("room", a), self._find("room", b)
        if not a_room or not b_room: return "Both rooms must exist."
        opposite = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up", "northeast": "southwest", "southwest": "northeast", "northwest": "southeast", "southeast": "northwest"}.get(direction)
        if opposite is None: return f"Unknown direction '{direction}'."
        a_room.setdefault("exits", {})[direction] = b
        b_room.setdefault("exits", {})[opposite] = a
        self.dirty.add("room")
        return f"Linked {a} <-{direction}-> {b}."

    def placeitem(self, room_id, item_id):
        room = self._find("room", room_id)
        if room is None: return f"No room '{room_id}'."
        if self._find("item", item_id) is None: return f"No item with id '{item_id}'."
        items = room.setdefault("items", [])
        if item_id in items: return f"Item '{item_id}' is already in '{room_id}'."
        items.append(item_id)
        self.dirty.add("room")
        return f"Placed '{item_id}' in '{room_id}'."

    def removeitem(self, room_id, item_id):
        room = self._find("room", room_id)
        if room is None: return f"No room '{room_id}'."
        items = room.get("items", [])
        if item_id not in items: return f"Item '{item_id}' is not in '{room_id}'."
        items.remove(item_id)
        self.dirty.add("room")
        return f"Removed '{item_id}' from '{room_id}'."

    def validate(self):
        room_ids = {r["id"] for r in self.data["room"]}
        item_ids = {i["id"] for i in self.data["item"]}
        npc_ids = {n["id"] for n in self.data["npc"]}
        group_ids = {g["id"] for g in self.data.get("group", [])}
        building_ids = {b["id"] for b in self.data.get("building", [])}
        race_ids = {r["id"] for r in self.data.get("race", [])}
        class_ids = {c["id"] for c in self.data.get("class", [])}
        sex_ids = {s["id"] for s in self.data.get("sex", [])}
        from engine.mapping import issues as map_issues
        from engine.character_style import validate_world
        issues = map_issues(self.data["room"])+validate_world(self.data)

        for npc in self.data["npc"]:
            pm = npc.get("patrol_mode")
            if pm and pm not in ("random", "loop", "none"):
                issues.append(f"npc '{npc['id']}' patrol_mode '{pm}' must be random, loop, or none")
            pc = npc.get("patrol_chance")
            if pc is not None:
                try:
                    if float(pc) < 0 or float(pc) > 1:
                        issues.append(f"npc '{npc['id']}' patrol_chance must be 0.0-1.0")
                except (TypeError, ValueError):
                    issues.append(f"npc '{npc['id']}' patrol_chance is not a number")

        for room in self.data["room"]:
            try: normalize_exits(room.get('exits', {}))
            except ValueError as exc: issues.append(room['id'] + ': ' + str(exc))
            for direction, target in room.get("exits", {}).items():
                if target not in room_ids: issues.append(f"room '{room['id']}' exit {direction} -> unknown '{target}'")
            for item_id in room.get("items", []):
                if item_id not in item_ids: issues.append(f"room '{room['id']}' references unknown item '{item_id}'")
            grp = room.get("group")
            if grp and grp not in group_ids: issues.append(f"room '{room['id']}' group '{grp}' not found")
            for spawner in room.get("spawners", []):
                if spawner.get("npc") and spawner["npc"] not in npc_ids: issues.append(f"room '{room['id']}' spawner references unknown npc '{spawner['npc']}'")

        for npc in self.data["npc"]:
            for field, ids in (("spawn_room", room_ids), ("workplace_room", room_ids), ("guard_room", room_ids), ("workplace_building", building_ids), ("guard_building", building_ids), ("group", group_ids), ("race", race_ids), ("class", class_ids), ("sex", sex_ids)):
                val = npc.get(field)
                if val and val not in ids: issues.append(f"npc '{npc['id']}' {field} '{val}' not found")
            for entry in npc.get("stock", []):
                if entry.get("item") and entry["item"] not in item_ids: issues.append(f"npc '{npc['id']}' stock item '{entry['item']}' not found")

        for bld in self.data.get("building", []):
            for r_id in bld.get("rooms", []):
                if r_id not in room_ids: issues.append(f"building '{bld['id']}' references unknown room '{r_id}'")
            grp = bld.get("group")
            if grp and grp not in group_ids: issues.append(f"building '{bld['id']}' group '{grp}' not found")

        for grp in self.data.get("group", []):
            sr = grp.get("start_room")
            if sr and sr not in room_ids: issues.append(f"group '{grp['id']}' start_room '{sr}' not found")
            for h in grp.get("hostile_to", []):
                if h != "*" and h not in group_ids: issues.append(f"group '{grp['id']}' hostile_to unknown '{h}'")
            for n_id in grp.get("roster", []):
                if n_id not in npc_ids: issues.append(f"group '{grp['id']}' roster unknown npc '{n_id}'")

        for grp in self.data.get("group", []):
            vis = grp.get("visibility")
            if vis and vis not in ("playable", "npc_only"):
                issues.append(f"group '{grp['id']}' visibility '{vis}' must be playable or npc_only")

        for npc in self.data["npc"]:
            greetings = npc.get("greetings") or {}
            if greetings and not isinstance(greetings, dict):
                issues.append(f"npc '{npc['id']}' greetings must be a dict")
            elif isinstance(greetings, dict):
                for gid, gtext in greetings.items():
                    if gid not in group_ids:
                        issues.append(f"npc '{npc['id']}' greeting group '{gid}' not found")
                    if not isinstance(gtext, str):
                        issues.append(f"npc '{npc['id']}' greeting for '{gid}' must be text")
            for entry in npc.get("stock", []):
                price = entry.get("price")
                if price is not None:
                    try:
                        if int(price) < 0:
                            issues.append(f"npc '{npc['id']}' stock price cannot be negative")
                    except (TypeError, ValueError):
                        issues.append(f"npc '{npc['id']}' stock price is not a number")
                qty = entry.get("qty")
                if qty is not None:
                    try:
                        if int(qty) < 0:
                            issues.append(f"npc '{npc['id']}' stock qty cannot be negative")
                    except (TypeError, ValueError):
                        issues.append(f"npc '{npc['id']}' stock qty is not a number")

        for room in self.data["room"]:
            for idx, spawner in enumerate(room.get("spawners", [])):
                count_v = spawner.get("count")
                if count_v is not None:
                    try:
                        if int(count_v) < 1:
                            issues.append(f"room '{room['id']}' spawner count must be >= 1")
                    except (TypeError, ValueError):
                        issues.append(f"room '{room['id']}' spawner count is not a number")
                chance_v = spawner.get("chance")
                if chance_v is not None:
                    try:
                        cf = float(chance_v)
                        if cf < 0 or cf > 1:
                            issues.append(f"room '{room['id']}' spawner chance must be 0-1")
                    except (TypeError, ValueError):
                        issues.append(f"room '{room['id']}' spawner chance is not a number")
                cd_v = spawner.get("cooldown")
                if cd_v is not None:
                    try:
                        if float(cd_v) < 0:
                            issues.append(f"room '{room['id']}' spawner cooldown must be >= 0")
                    except (TypeError, ValueError):
                        issues.append(f"room '{room['id']}' spawner cooldown is not a number")
                tl_v = spawner.get("total_limit")
                if tl_v is not None:
                    try:
                        if int(tl_v) < 1:
                            issues.append(f"room '{room['id']}' spawner total_limit must be >= 1")
                    except (TypeError, ValueError):
                        issues.append(f"room '{room['id']}' spawner total_limit is not a number")

        from engine.living import validate as validate_living
        issues.extend(validate_living(self.data))
        from engine import locks
        issues.extend(locks.validate(self.data))
        from engine.route_surfaces import validate as validate_route_surfaces
        issues.extend(validate_route_surfaces(self.data))
        metadata_path=self.data_dir/'metadata.json'
        metadata=json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        from engine import travel_pacing
        issues.extend(travel_pacing.validate(metadata))
        authored_rules = {}
        try:
            from engine.world_package import rules
            authored_rules = rules(self.data_dir,{r['id']:r for r in self.data['room']},{n['id']:n for n in self.data['npc']})
        except (ValueError, TypeError, KeyError) as exc:
            issues.append(str(exc))
        from engine import progression
        issues.extend(progression.validate_config(metadata.get('progression',{})))
        from engine import life_stages, population_health, population_content
        issues.extend(life_stages.validate(self.data,metadata))
        issues.extend(population_health.validate(self.data,metadata))
        issues.extend(population_content.validate_manifest(self.data,getattr(self,'population_manifest',None)))
        from engine import geology, geology_events
        issues.extend(geology.validate(self.data))
        issues.extend(geology_events.validate(self.data,metadata))
        from engine import facility_landmarks
        issues.extend(facility_landmarks.validate(self.data))
        from engine import local_visibility
        issues.extend(local_visibility.validate(self.data))
        from engine import regional_weather
        issues.extend(regional_weather.validate(self.data,metadata))
        if metadata.get('society'):
            from engine.society import validate
            issues.extend(validate(self.data,metadata))
        if metadata.get('frontiers'):
            from engine.frontiers import audit
            issues.extend(audit(self.data,metadata,authored_rules))
        summary = f"{len(self.data['room'])} rooms, {len(self.data['item'])} items, {len(self.data['npc'])} npcs, {len(self.data['quest'])} quests"
        if not issues: return f"OK - {summary}. No issues."
        return f"{len(issues)} issue(s):\n " + "\n ".join(issues)

    def validate_exits(self):
        """Return asymmetric-exit warnings."""
        warnings = []
        seen = set()
        for room in self.data["room"]:
            for direction, target in room.get("exits", {}).items():
                target_room = self._find("room", target)
                if not target_room:
                    continue
                opposite = _OPPOSITE.get(direction)
                if not opposite:
                    continue
                key = (room["id"], target, direction)
                rev = (target, room["id"], opposite)
                if key in seen or rev in seen:
                    continue
                seen.add(key)
                target_exits = target_room.get("exits", {})
                if (direction in target_exits
                        and target_exits[direction] == room["id"]):
                    continue
                if (opposite in target_exits
                        and target_exits[opposite] == room["id"]):
                    continue
                warnings.append(
                    f"room '{room['id']}' {direction} -> '{target}' no reciprocal {opposite}")
        return warnings

    def check_items(self):
        """Audit item placement."""
        item_ids = {i["id"] for i in self.data["item"]}
        referenced = set()
        issues = []
        for room in self.data["room"]:
            items = room.get("items", [])
            for item_id in items:
                referenced.add(item_id)
                if item_id not in item_ids:
                    issues.append(
                        f"room '{room['id']}' references unknown item '{item_id}'")
            for item_id in set(items):
                n = items.count(item_id)
                if n > 1:
                    issues.append(
                        f"room '{room['id']}' has {n}x '{item_id}' stacked")
        for item in self.data["item"]:
            if item["id"] not in referenced:
                issues.append(
                    f"item '{item['id']}' is defined but not placed in any room")
        if not issues:
            return f"OK — {len(item_ids)} items, all correctly placed."
        return f"{len(issues)} issue(s):\n " + "\n ".join(issues)

    def save(self):
        population_dirty = getattr(self, 'population_manifest_dirty', False)
        if not self.dirty and not population_dirty: return "Nothing to save."
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if population_dirty:
            # Keep generation identity and its new NPC definitions in one
            # rollback-protected write. Do not clear drafts on failed writes.
            from engine.population_content import atomic_write_files
            payloads = {FILE_MAP[typ]: self.data[typ] for typ in self.dirty}
            payloads['population.json'] = self.population_manifest
            atomic_write_files(self.data_dir, payloads)
            written = list(payloads)
            self.population_manifest_dirty = False
        else:
            written = []
            for typ in list(self.dirty):
                path = self.data_dir / FILE_MAP[typ]
                path.write_text(json.dumps(self.data[typ], indent=2) + "\n", encoding="utf-8")
                written.append(FILE_MAP[typ])
        self.dirty.clear()
        return "Wrote: " + ", ".join(sorted(written))

def server_running() -> bool:
    s = socket.socket(); s.settimeout(0.2)
    try:
        s.connect(("127.0.0.1", WS_PORT)); return True
    except (ConnectionRefusedError, socket.timeout, OSError): return False
    finally: s.close()

def _pick_game_from_argv() -> str:
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--game" and i + 1 < len(argv): return argv[i + 1]
        if arg.startswith("--game="): return arg.split("=", 1)[1]
    return "default"

def main():
    slug = _pick_game_from_argv()
    game_dir = GAMES_DIR / slug
    if not game_dir.exists():
        print(f"Game '{slug}' not found in {GAMES_DIR}.")
        return
    if server_running():
        print("WARNING: the game server appears to be running on port 8765.")
        if input("Continue anyway? [y/N] ").strip().lower() != "y": return
    print()
    ed = Editor(game_dir)
    print(f"Expanse Editor - game '{slug}' - {len(ed.data['room'])} rooms.")
    print("Type 'help' for commands, 'quit' to exit.\n")

    while True:
        try: line = input(f"[{slug}] editor> ").strip()
        except (EOFError, KeyboardInterrupt): break
        if not line: continue
        parts = shlex.split(line)
        verb, args = parts[0].lower(), parts[1:]

        if verb == "help": print(HELP_TEXT)
        elif verb == "creategame":
            if len(args) < 2: print("Usage: creategame <slug> <name...> [--starter]")
            else:
                template = "blank"
                name_args = list(args[1:])
                if "--starter" in name_args:
                    template = "starter"
                    name_args = [a for a in name_args if a != "--starter"]
                ok, msg = Editor.create_game(GAMES_DIR, args[0], " ".join(name_args), template=template)
                print(msg)
        elif verb == "list": print(ed.list_entries(args[0] if args else "room"))
        elif verb == "show": print(ed.show(args[0], args[1]) if len(args) >= 2 else "Usage: show <type> <id>")
        elif verb == "new": print(ed.new(args[0], args[1]) if len(args) >= 2 else "Usage: new <type> <id>")
        elif verb == "copy":
            if len(args) < 2: print("Usage: copy <type> <source_id> [new_id]")
            else: print(ed.copy(args[0], args[1], args[2] if len(args) >= 3 else None))
        elif verb == "edit":
            if len(args) < 4: print("Usage: edit <type> <id> <field> <value...>")
            else: print(ed.edit(args[0], args[1], args[2], " ".join(args[3:])))
        elif verb == "setfield":
            if len(args) < 4: print("Usage: setfield <type> <id> <field> <json>")
            else:
                try: print(ed.setfield(args[0], args[1], args[2], json.loads(" ".join(args[3:]))))
                except json.JSONDecodeError as e: print(f"Invalid JSON: {e}")
        elif verb == "delete": print(ed.delete(args[0], args[1]) if len(args) >= 2 else "Usage: delete <type> <id>")
        elif verb == "addexit": print(ed.addexit(*args) if len(args) == 3 else "Usage: addexit <room> <dir> <target>")
        elif verb == "rmexit": print(ed.rmexit(*args) if len(args) == 2 else "Usage: rmexit <room> <dir>")
        elif verb == "link": print(ed.link(*args) if len(args) == 3 else "Usage: link <room> <dir> <other>")
        elif verb == "placeitem": print(ed.placeitem(*args) if len(args) == 2 else "Usage: placeitem <room> <item>")
        elif verb == "removeitem": print(ed.removeitem(*args) if len(args) == 2 else "Usage: removeitem <room> <item>")
        elif verb == "validate": print(ed.validate())
        elif verb == "save": print(ed.save())
        elif verb == "revert": ed._load(); print("Reloaded from disk.")
        elif verb in ("quit", "exit"): break
        else: print(f"Unknown command '{verb}'.")

if __name__ == "__main__":
    main()
