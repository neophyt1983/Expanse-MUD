from engine.item_catalog import counted
from engine import living, frontiers
from engine.directions import normalize_exits
# engine/commands.py
import difflib
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from engine.core import World, Room, Entity
from engine.describe import resolve_description
from engine import item_catalog


@dataclass
class CommandContext:
    world: World
    player: Entity
    room: Room
    registry: "CommandRegistry" = None
    raw: str = ""
    time_accounted: bool = False


@dataclass
class Command:
    name: str
    brief: str
    usage: str
    handler: Callable[[CommandContext, str], str]
    aliases: List[str] = field(default_factory=list)
    help_text: str = ""
    example: str = ""
    available: Optional[Callable[[CommandContext], bool]] = None


class CommandRegistry:
    def __init__(self):
        self._commands: List[Command] = []
        self._index: Dict[str, Command] = {}

    def register(self, cmd: Command):
        self._commands.append(cmd)
        self._index[cmd.name] = cmd
        for alias in cmd.aliases:
            self._index[alias] = cmd

    def resolve(self, word: str) -> Optional[Command]:
        return self._index.get(word.lower())

    def available(self, ctx: CommandContext) -> List[Command]:
        return [c for c in self._commands
                if c.available is None or c.available(ctx)]


# ---------- equipment helpers ----------

def effective_attack(world: World, entity: Entity) -> int:
    from engine import society
    bonus = 0
    for item_id in entity.equipped.values():
        item = world.items.get(item_id)
        if item and (not society.enabled(world) or society.durability(entity,item_id)>0):
            bonus += item.get("attack_bonus", 0) or 0
    if entity.is_player and living.enabled(world): bonus += living.attack_bonus(entity)
    from engine import ability_rules
    bonus+=ability_rules.combat_bonus(world,entity,'ability_focus_v1')
    return max(1, entity.attack + bonus)


def effective_defense(world: World, entity: Entity) -> int:
    from engine import society
    bonus = 0
    for item_id in entity.equipped.values():
        item = world.items.get(item_id)
        if item and (not society.enabled(world) or society.durability(entity,item_id)>0):
            bonus += item.get("defense_bonus", 0) or 0
    if entity.is_player and living.enabled(world): bonus += living.defense_bonus(entity)
    from engine import ability_rules
    penalty=ability_rules.combat_bonus(world,entity,'ability_exposed_v1')
    return max(0,entity.defense+bonus-penalty) if penalty else entity.defense+bonus


def _slot_for(world: World, item_id: str) -> Optional[str]:
    item = world.items.get(item_id)
    if not item:
        return None
    slot = item.get("slot")
    if slot:
        return slot
    t = item.get("type")
    if t == "weapon":
        return "weapon"
    if t == "armor":
        return "armor"
    return None


# ---------- fuzzy matching ----------

def _normalize_query(s: str) -> str:
    """Lowercase, strip directional prefixes, strip one article."""
    s = (s or "").strip().lower()
    for p in ("to ", "towards ", "toward "):
        if s.startswith(p):
            s = s[len(p):]
            break
    for p in ("the ", "a ", "an "):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.strip()


def _fuzzy_match(query: str, candidates: list) -> list:
    """Return candidates matching query, best first.

    Each candidate is a dict with at least key=str (the searchable
    text) plus arbitrary extra fields carried through. Order of
    preference: exact > prefix > word-boundary > substring.
    Falls back to difflib near-match if nothing else hits."""
    q = _normalize_query(query)
    if not q:
        return []
    exact, prefix, word, contains = [], [], [], []
    word_pat = re.compile(r"\b" + re.escape(q))
    for c in candidates:
        key = (c.get("key") or "").lower()
        if not key:
            continue
        if key == q:
            exact.append(c)
        elif key.startswith(q):
            prefix.append(c)
        elif word_pat.search(key):
            word.append(c)
        elif q in key:
            contains.append(c)
    if exact or prefix or word or contains:
        return exact + prefix + word + contains
    # Fuzzy fallback: compare q against the full key and each word
    scored = []
    for c in candidates:
        key = (c.get("key") or "").lower()
        if not key:
            continue
        tokens = [key] + [w for w in re.split(r"\W+", key) if w]
        best = max(
            (difflib.SequenceMatcher(None, q, t).ratio()
             for t in tokens),
            default=0.0,
        )
        if best >= 0.7:
            scored.append((best, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:3]]


def _npc_def_field(world: World, entity: Entity, field: str,
                    default=None):
    if not entity.source_def:
        return default
    return world.npcs.get(entity.source_def, {}).get(field, default)


# ---------- faction helpers ----------

def _is_hostile(owner_group, player) -> bool:
    """True if owner_group would attack a player in player.group_id."""
    if not owner_group:
        return False
    if "relations" in owner_group:
        return frontiers.relation(owner_group, player.group_id)=="hostile"
    hostile_to = owner_group.get("hostile_to") or []
    if "*" in hostile_to:
        return True
    if player.group_id and player.group_id in hostile_to:
        return True
    if not player.group_id and "unaffiliated" in hostile_to:
        return True
    return False


def _is_hostile_npc(world: World, npc: Entity, player: Entity) -> bool:
    if frontiers.active(world):return frontiers.hostile(world,npc,player)
    if not npc.group_id:
        return False
    return _is_hostile(world.groups.get(npc.group_id), player)


def _spawn_npc_instance(world: World, room: Room,
                        npc_id: str,
                        spawner_key: Optional[str] = None
                        ) -> Optional[Entity]:
    npc_def = world.npcs.get(npc_id)
    if not npc_def:
        return None
    # Enrolled residents are permanent loader identities, never encounter,
    # ambush or respawner templates. Reject before counters or state mutate.
    if npc_def.get('population_profile'):
        return None
    world.spawner_counter[npc_id] = world.spawner_counter.get(npc_id, 0) + 1
    ent = Entity(
        id=f"npc:{npc_id}:{uuid.uuid4().hex[:8]}",
        name=npc_def['name'],
        hp=npc_def["hp"], max_hp=npc_def["hp"],
        attack=npc_def["attack"], defense=npc_def["defense"],
        gold=npc_def.get("gold", 0),
        is_player=False,
        source_def=npc_id,
        group_id=npc_def.get("group") or None,
        spawner_key=spawner_key,
        inventory=list(npc_def.get('inventory',[])),
        equipped=dict(npc_def.get('equipped',{})),
    )
    from engine import names
    names.assign(world,ent)
    world.add_entity(ent, room.id)
    return ent

def _spawner_key(room_id: str, idx: int) -> str:
    return f"{room_id}:{idx}"


def _try_spawn(world: World, room: Room, spawner: dict,
                idx: int,
                trigger: str = "entry", *,
                alive_counts: Optional[dict] = None) -> Optional[Entity]:
    """Attempt a spawn. Returns the new entity, or None if blocked.

    trigger: "entry" (rolls chance), "death" (no chance roll).
    Count cap, cooldown, and total_limit gate all triggers.
    alive_counts is a per-refresh automatic-spawner snapshot, updated on success.
    """
    from engine import geology_impacts
    if geology_impacts.room_unusable(world,room.id):return None
    npc_id = spawner.get("npc")
    if not npc_id or npc_id not in world.npcs:
        return None

    key = _spawner_key(room.id, idx)
    state = world.spawner_state.get(key) or {
        "last_spawn_at": None, "total_spawned": 0,
    }

    if state.get('environmental_recovery_minute',0)>living.state(world)['minute']:return None
    total_limit = spawner.get("total_limit")
    if total_limit is not None:
        try:
            total_limit = int(total_limit)
        except (TypeError, ValueError):
            total_limit = None
    if total_limit is not None and state["total_spawned"] >= total_limit:
        return None

    count_cap = spawner.get("count", 1)
    try:
        count_cap = int(count_cap)
    except (TypeError, ValueError):
        count_cap = 1
    if spawner.get("automatic") and alive_counts is not None:
        alive = alive_counts.get(key, 0)
    else:
        alive = sum(
            1 for eid in (world.entities if spawner.get("automatic") else room.entities)
            if (e := world.entities.get(eid)) and e.alive
            and not e.is_player
            and getattr(e, "spawner_key", None) == key
        )
    if alive >= count_cap:
        return None

    cooldown = spawner.get("cooldown", 0) or 0
    try:
        cooldown = float(cooldown)
    except (TypeError, ValueError):
        cooldown = 0.0
    if cooldown > 0 and state["last_spawn_at"] is not None:
        elapsed = time.monotonic() - state["last_spawn_at"]
        if elapsed < cooldown:
            return None

    # Full or cooling-down spawners cannot recover yet. Count habitat occupants
    # only for otherwise eligible attempts, retaining the same pre-roll gate.
    from engine import wildlife
    if not wildlife.recovery_allowed(world,room,spawner,idx):return None

    if trigger == "entry":
        chance = spawner.get("chance", 1.0)
        try:
            chance = float(chance)
        except (TypeError, ValueError):
            chance = 1.0
        if random.random() >= chance:
            return None

    ent = _spawn_npc_instance(world, room, npc_id, spawner_key=key)
    if not ent:
        return None
    if state.pop('environmental_recovery_minute',None) is not None:
        ent.progress['geology_safe_until']=living.state(world)['minute']+60
    state["last_spawn_at"] = time.monotonic()
    state["total_spawned"] += 1
    world.spawner_state[key] = state
    if spawner.get("automatic") and alive_counts is not None and ent.alive:
        alive_counts[key] = alive_counts.get(key, 0) + 1
    return ent


def _on_npc_death(world: World, room: Room,
                   entity: Entity, *, defer=False) -> List[str]:
    """Resolve NPC identity/encounter/spawner death once, without kill rewards."""
    from engine import spell_life
    if spell_life.magical(entity):
        spell_life.retire(world,entity.id)
        return []
    from engine import mortality
    mortality.record_death(world, entity)
    if entity.progress.get('_npc_death_resolved'):return []
    entity.progress['_npc_death_resolved']=True
    if entity.spawner_key and entity.spawner_key.startswith('encounter:'):
        rec=living.state(world)['encounters'].get(entity.spawner_key[len('encounter:'):])
        if rec:
            rec['members']=[eid for eid in rec['members'] if eid!=entity.id and eid in world.entities and world.entities[eid].alive]
            if not rec['members']:rec['cleared']=True
    key = getattr(entity, "spawner_key", None)
    if not key:
        return []
    try:
        room_id, idx_str = key.rsplit(":", 1)
        idx = int(idx_str)
    except (ValueError, AttributeError):
        return []
    if room_id != room.id:
        room = world.rooms.get(room_id)
        if room is None:return []
    spawners = room.spawners or []
    if idx < 0 or idx >= len(spawners):
        return []
    spawner = spawners[idx]
    if not spawner.get("on_death"):
        return []
    state = world.spawner_state.setdefault(key, {"last_spawn_at": None, "total_spawned": 0})
    state["pending_deaths"] = state.get("pending_deaths", 0) + 1
    if defer:
        state['environmental_recovery_minute']=living.state(world)['minute']+60
        return []
    new_ent = _try_spawn(world, room, spawner, idx, trigger="death")
    if new_ent:
        state["pending_deaths"] -= 1
    if new_ent:
        return [f"{new_ent.name} appears."]
    return []


def advance_spawners(world: World):
    """Retry queued death respawns; return (room ID, message) notifications."""
    messages = []
    for key, state in list(world.spawner_state.items()):
        if not state.get("pending_deaths", 0):
            continue
        room_id, index = key.rsplit(":", 1)
        room = world.rooms.get(room_id)
        if room is None or int(index) >= len(room.spawners):
            state["pending_deaths"] = 0
            continue
        spawner = room.spawners[int(index)]
        limit = spawner.get("total_limit")
        if not spawner.get("on_death") or (limit is not None and state["total_spawned"] >= int(limit)):
            state["pending_deaths"] = 0
            continue
        entity = _try_spawn(world, room, spawner, int(index), trigger="death")
        if entity:
            state["pending_deaths"] -= 1
            messages.append((room_id, f"{entity.name} appears."))
    return messages


def _trigger_room_spawns(world: World, room: Room,
                          player: Entity) -> List[str]:
    """Called on entering a room. Returns ambush message lines."""
    lines: List[str] = []
    newly_spawned: List[Entity] = []

    # Group-based ambush (one per entry, if no hostiles present)
    if room.group and not frontiers.active(world):
        owner = world.groups.get(room.group)
        if owner and _is_hostile(owner, player):
            existing = [
                eid for eid in room.entities
                if (e := world.entities.get(eid))
                and not e.is_player and e.alive
                and e.group_id == room.group
            ]
            if not existing and random.random() < 0.5:
                roster = list(owner.get("roster") or [])
                if not roster:
                    roster = [nid for nid, nd in world.npcs.items()
                              if nd.get("group") == room.group and not nd.get('population_profile')]
                roster = [nid for nid in roster
                          if not world.npcs.get(nid, {}).get('population_profile')]
                if roster:
                    pick = random.choice(roster)
                    ent = _spawn_npc_instance(world, room, pick)
                    if ent:
                        lines.append(f"{ent.name} ambushes you!")
                        newly_spawned.append(ent)

    # Explicit spawners
    for idx, spawner in enumerate(room.spawners or []):
        ent = _try_spawn(world, room, spawner, idx, trigger="entry")
        if ent:
            lines.append(f"{ent.name} appears.")
            newly_spawned.append(ent)

    # Newly spawned hostile NPCs each get one free attack
    for npc in ([] if frontiers.active(world) else newly_spawned):
        if not _is_hostile_npc(world, npc, player):
            continue
        from engine import fighting_pose
        fighting_pose.mark(npc)
        fighting_pose.mark(player,defending=True)
        dmg = player.take_damage(
            effective_attack(world, npc),
            defense=effective_defense(world, player),
            source=npc, cause='ambush', kind='combat',
        )
        lines.append(f"{npc.name} hits you for {dmg} damage.")

    return lines


# ---------- trade / dialogue ----------

def _is_merchant(world: World, entity: Entity) -> bool:
    """True if this NPC has a non-empty stock list (data-driven)."""
    if not entity.source_def:
        return False
    npc_def = world.npcs.get(entity.source_def, {})
    return bool(npc_def.get("stock"))


TRADE_ROLES = {
    "chef", "innkeeper", "merchant", "blacksmith", "barkeep",
    "trader", "vendor", "shopkeeper", "smith", "cook",
}

DIRECTION_ROLES = {
    "guard", "sentry", "watcher", "scout", "watchman",
}


def _def_for(world: World, entity: Entity) -> Optional[dict]:
    if not entity.source_def:
        return None
    return world.npcs.get(entity.source_def)


def _greeting_for(world: World, npc: Entity, npc_def: dict,
                   player: Entity) -> str:
    """Return greeting for the player's faction, else dialogue."""
    greetings = npc_def.get("greetings") or {}
    if player.group_id and player.group_id in greetings:
        return greetings[player.group_id] or ""
    return npc_def.get("dialogue") or ""


def _npc_role_target(ctx,target):
    matches=[]
    for e in ctx.world.entities_in_room(ctx.room.id):
        if e.is_player or not e.alive:continue
        d=ctx.world.npcs.get(e.source_def,{})
        aliases=[e.source_def or '',d.get('title',''),d.get('name',''),*d.get('legacy_names',[])]
        if target.casefold() in [x.casefold() for x in aliases if isinstance(x,str)]:matches.append(e)
    if len(matches)==1:return matches[0],None
    if matches:return None,'Several people match that occupation. Use their personal name or choose their Talk button.'
    return None,f"There is no '{target}' here to talk to."


def _find_talkable_npc(ctx: CommandContext,
                        target_name: str):
    target = (target_name or "").strip()
    if not target:
        return None, "Talk to who?"
    candidates = []
    for eid in ctx.room.entities:
        ent = ctx.world.entities.get(eid)
        if not ent or ent.is_player or not ent.alive:
            continue
        if ent.id == ctx.player.id:
            continue
        if ent.id.lower() == target.lower():
            return ent, None
        candidates.append({"entity": ent, "key": ent.name})
    matches = _fuzzy_match(target, candidates)
    if not matches:
        return _npc_role_target(ctx,target)
    return matches[0]["entity"], None


def _find_talkable_npc_strict(ctx: CommandContext,
                                target_name: str):
    """Strict match: exact, prefix, or word-boundary. No fuzzy."""
    target = (target_name or "").strip()
    if not target:
        return None, "Talk to who?"
    candidates = []
    for eid in ctx.room.entities:
        ent = ctx.world.entities.get(eid)
        if not ent or ent.is_player or not ent.alive:
            continue
        if ent.id == ctx.player.id:
            continue
        if ent.id.lower() == target.lower():
            return ent, None
        candidates.append({"entity": ent, "key": ent.name})

    q = _normalize_query(target)
    if not q:
        return None, f"There is no '{target}' here to talk to."
    exact, prefix, word = [], [], []
    word_pat = re.compile(r"\b" + re.escape(q))
    for c in candidates:
        key = (c.get("key") or "").lower()
        if not key:
            continue
        if key == q:
            exact.append(c)
        elif key.startswith(q):
            prefix.append(c)
        elif word_pat.search(key):
            word.append(c)
    matches = exact + prefix + word
    if not matches:
        return _npc_role_target(ctx,target)
    return matches[0]["entity"], None


def _stock_for(world: World, def_id: str):
    """Return [{item, price, qty, initial}] skipping zero-qty entries."""
    from engine import needs_market
    needs_market.ensure(world)
    npc_def = world.npcs.get(def_id) or {}
    def_stock = npc_def.get("stock") or []
    state = world.shop_state.get(def_id, {})
    out = []
    for entry in def_stock:
        item_id = entry.get("item")
        if not item_id:
            continue
        price = int(entry.get("price", 0) or 0)
        initial = int(entry.get("qty", 1) or 0)
        if needs_market.enabled(world):
            current=state.get(item_id,0)
            price=needs_market.merchant_price(world,def_id,item_id,price)
            out.append({'item':item_id,'price':price,'qty':current,'initial':max(1,initial)})
        elif initial == 0:
            out.append({"item": item_id, "price": price, "qty": None, "initial": 0})
        else:
            current = state.get(item_id, initial)
            if current > 0:
                out.append({"item": item_id, "price": price, "qty": current, "initial": initial})
    return out

def _path_to_room(world: World, start_id: str, target_id: str):
    """BFS shortest path from start_id to target_id.

    Returns a list of (direction, room_id) tuples, `[]` if already at
    the target, or `None` if unreachable.
    """
    if start_id not in world.rooms or target_id not in world.rooms:
        return None
    if start_id == target_id:
        return []
    queue = deque([(start_id, [])])
    visited = {start_id}
    while queue:
        current, path = queue.popleft()
        room = world.rooms.get(current)
        if not room:
            continue
        for direction, next_id in room.exits.items():
            if next_id in visited or next_id not in world.rooms:
                continue
            next_path = path + [(direction, next_id)]
            if next_id == target_id:
                return next_path
            visited.add(next_id)
            queue.append((next_id, next_path))
    return None


DIR_MAP = {
    "n": "North", "north": "North",
    "s": "South", "south": "South",
    "e": "East", "east": "East",
    "w": "West", "west": "West",
    "u": "Up", "up": "Up",
    "d": "Down", "down": "Down",
    "ne": "Northeast", "northeast": "Northeast",
    "nw": "Northwest", "northwest": "Northwest",
    "se": "Southeast", "southeast": "Southeast",
    "sw": "Southwest", "southwest": "Southwest",
}


def _normalize_direction(d: str) -> str:
    """Convert any alias (n, N, north, NORTH) to its full form (North)."""
    return DIR_MAP.get(d.strip().lower(), d.strip().capitalize())


def _format_directions(path):
    """Format a path as 'North, east, east' (first capitalized, rest lower)."""
    dirs = [d for d, _ in path]
    if not dirs:
        return ""
    if len(dirs) == 1:
        return dirs[0].capitalize()
    return ", ".join([dirs[0].capitalize()] + dirs[1:])


def _directions_to_room(ctx: CommandContext, npc: Entity,
                         room: Room) -> str:
    from engine.local_visibility import blind
    if blind(ctx.world,ctx.player):
        return f"{npc.name}: Darkness conceals the current routes. Try a direction or use a working lantern."
    path = _path_to_room(ctx.world, ctx.player.location, room.id)
    if path is None:
        return f"{npc.name} is unsure of the way."
    if not path:
        return f"Welcome, you have arrived at {room.name}."
    return (f"{_format_directions(path)}. "
            f"That takes you to {room.name}.")



def _guard_directions(ctx: CommandContext, npc: Entity,
                       npc_def: dict) -> str:
    from engine.local_visibility import blind
    if blind(ctx.world,ctx.player):
        return f"{npc.name}: Darkness conceals the current exits. Try a direction or use a working lantern."
    npc_room = ctx.world.rooms.get(npc.location)
    greeting = (_greeting_for(ctx.world, npc, npc_def, ctx.player)
                or f"{npc.name} nods.")
    lines = [greeting]
    if not npc_room.exits:
        lines.append("There is only one way out.")
        return "\n".join(lines)
    from engine import knowledge
    knowledge.teach(ctx.world,ctx.player,{"rooms":list(npc_room.exits.values())})
    lines.append("Exits from here:")
    for direction, target_id in sorted(npc_room.exits.items()):
        target_room = ctx.world.rooms.get(target_id)
        room_name = (target_room.name if target_room
                     else f"<unknown {target_id}>")
        building = ctx.world.building_for_room(target_id)
        suffix = f" ({building['name']})" if building else ""
        lines.append(f"  {_normalize_direction(direction)}: {room_name}{suffix}")
    lines.append("")
    lines.append("Ask 'talk <name> about <room>' for the way ")
    lines.append("to a specific place.")
    return "\n".join(lines)

def _topic_is_valid(world: World, npc: Entity, npc_def: dict,
                    topic: str) -> bool:
    """True if `topic` names something the NPC could speak about."""
    if not topic:
        return True
    if topic.lower() in SPECIAL_TOPIC_WORDS:
        return True
    room_c = []
    for r in world.rooms.values():
        room_c.append({"key": r.name})
        room_c.append({"key": r.id})
    if _fuzzy_match(topic, room_c):
        return True
    bld_c = [{"key": b.get("name", b["id"])}
             for b in world.buildings.values()]
    if _fuzzy_match(topic, bld_c):
        return True
    role = (npc_def.get("role") or "").lower()
    if role in TRADE_ROLES and npc.source_def:
        stock = _stock_for(world, npc.source_def)
        item_c = []
        for s in stock:
            idef = world.items.get(s["item"], {})
            item_c.append({"key": idef.get("name", s["item"])})
        if _fuzzy_match(topic, item_c):
            return True
    return False


SPECIAL_TOPIC_WORDS = {"directions", "direction", "way", "path",
                       "where", "exits", "exit", "map", "route"}


def _render_stock(world: World, npc_name: str, greeting: str,
                  stock: list) -> str:
    lines = [greeting or f"{npc_name} has wares for sale:"]
    for s in stock:
        item_def = world.items.get(s["item"], {})
        item_name = item_def.get("name", s["item"])
        qty_str = "unlimited" if s["qty"] is None else f"{s['qty']} left"
        lines.append(f"  {item_name} \u2014 {s['price']} gold ({qty_str})")
    lines.append("")
    lines.append("Type 'buy <item>' to purchase.")
    return "\n".join(lines)

def _cmd_talk(ctx: CommandContext, args: str) -> str:
    # Authored quest/topics remain text; ordinary social conversation uses signals.
    if not ctx.world.metadata.get('social_content_version') or ' about ' in args.lower():
        return _cmd_dialogue(ctx,args)
    if not args.strip():return 'Talk to whom? Choose a nearby NPC in the Social panel.'
    npc,error=_find_talkable_npc_strict(ctx,args.strip())
    if npc is None:return error or 'Choose a nearby NPC.'
    if (_def_for(ctx.world,npc) or {}).get('teaches_abilities'):return _cmd_dialogue(ctx,args)
    if ctx.world.metadata.get('market_shifts') and (_def_for(ctx.world,npc) or {}).get('market_id'):
        return _cmd_dialogue(ctx,args)
    from engine import social
    return social.emote(ctx.world,ctx.player,npc,'happy')


def _cmd_dialogue(ctx: CommandContext, args: str) -> str:
    raw = args.strip()
    if not raw:
        return "Talk to who?"

    topic = ""
    npc = None
    err = None

    if " about " in raw.lower():
        idx = raw.lower().index(" about ")
        topic = raw[idx + 7:].strip()
        npc_name = raw[:idx].strip()
        npc, err = _find_talkable_npc_strict(ctx, npc_name)
        if npc is None:
            npc, err = _find_talkable_npc(ctx, npc_name)
        if npc is None:
            return err or f"There is no '{npc_name}' here to talk to."
    else:
        npc, err = _find_talkable_npc_strict(ctx, raw)
        if npc is None and " " in raw:
            words = raw.split()
            for split_at in range(len(words) - 1, 0, -1):
                head = " ".join(words[:split_at])
                tail = " ".join(words[split_at:])
                npc_try, _ = _find_talkable_npc_strict(ctx, head)
                if npc_try is not None:
                    npc = npc_try
                    topic = tail
                    break
        if npc is None:
            npc, err = _find_talkable_npc(ctx, raw)
        if npc is None:
            return err or f"There is no '{raw}' here to talk to."

    from engine import npc_attention
    from engine import livelihoods
    if not livelihoods.awake(ctx.world,npc):
        if ctx.world.metadata.get('market_shifts') and (_def_for(ctx.world,npc) or {}).get('market_id'):
            from engine import market_shifts
            return market_shifts.menu(ctx.world,ctx.player,npc)
        return npc.name+' is sleeping. Return during waking hours.'
    npc_attention.begin(ctx.world,ctx.player,npc)
    from engine.npc_activity import note
    note(npc,'social','In conversation')
    if _is_hostile_npc(ctx.world, npc, ctx.player):
        return f"{npc.name} glares at you and refuses to speak."

    if living.enabled(ctx.world):
        pr = living.progress(ctx.player)
        if npc.source_def not in pr.setdefault('talked_to', []): pr['talked_to'].append(npc.source_def)
        from engine import quest_progress
        quest_progress.talk(ctx.player, npc.source_def)
    npc_def = _def_for(ctx.world, npc) or {}
    from engine import ability_rules
    ability_rules.disclose(ctx.world,ctx.player,npc_def)
    from engine import knowledge
    knowledge.from_npc(ctx.world,ctx.player,npc)
    def sourced_reply(text):
        from engine.quest_discovery import offer_text
        text=knowledge.from_text(ctx.world,ctx.player,text,source=('npc',npc.source_def))
        return text+offer_text(ctx.world,ctx.player,npc_def.get('knowledge',{}).get('quests',[]))
    if ctx.world.metadata.get("market_shifts") and npc_def.get("market_id"):
        from engine import market_shifts
        return sourced_reply(market_shifts.menu(ctx.world,ctx.player,npc))
    role = (npc_def.get("role") or "").lower()

    if topic:
        if topic.lower() in SPECIAL_TOPIC_WORDS:
            if role in DIRECTION_ROLES:
                return sourced_reply(_guard_directions(ctx, npc, npc_def))
            if _is_merchant(ctx.world, npc):
                greeting = _greeting_for(ctx.world, npc, npc_def, ctx.player)
                stock = _stock_for(ctx.world, npc.source_def)
                if not stock:
                    line = f"{npc.name} has nothing to sell right now."
                    return sourced_reply(f"{greeting}\n{line}" if greeting else line)
                return sourced_reply(_render_stock(ctx.world, npc.name, greeting, stock))
        return sourced_reply(_answer_topic(ctx, npc, npc_def, topic))

    if _is_merchant(ctx.world, npc):
        stock = _stock_for(ctx.world, npc.source_def)
        greeting = _greeting_for(ctx.world, npc, npc_def, ctx.player)
        if not stock:
            line = f"{npc.name} has nothing to sell right now."
            return sourced_reply(f"{greeting}\n{line}" if greeting else line)
        return sourced_reply(_render_stock(ctx.world, npc.name, greeting, stock))
    if role in DIRECTION_ROLES:
        return sourced_reply(_guard_directions(ctx, npc, npc_def))
    greeting=(_greeting_for(ctx.world,npc,npc_def,ctx.player) or f'{npc.name} has nothing to say.')
    return sourced_reply(greeting)

def _answer_topic(ctx: CommandContext, npc: Entity,
                   npc_def: dict, topic: str) -> str:
    role = (npc_def.get("role") or "").lower()
    from engine import knowledge
    known_places=knowledge.npc_topics(ctx.world,npc)
    room_candidates = []
    for r in ctx.world.rooms.values():
        if r.id not in known_places:continue
        room_candidates.append({"room": r, "key": r.name})
    for r in ctx.world.rooms.values():
        if r.id not in known_places:continue
        room_candidates.append({"room": r, "key": r.id})
    room_matches = _fuzzy_match(topic, room_candidates)
    if room_matches:
        target=room_matches[0]['room']
        knowledge.teach(ctx.world,ctx.player,{'rooms':[target.id]})
        from engine.navigation import route_text
        return route_text(ctx.world,ctx.player,target.id)

    building_candidates = []
    for b in ctx.world.buildings.values():
        if not set(b.get("rooms",[])) & known_places:continue
        building_candidates.append({
            "building": b,
            "key": b.get("name", b["id"]),
        })
    building_matches = _fuzzy_match(topic, building_candidates)
    if building_matches:
        bld = building_matches[0]["building"]
        bld_name = bld.get("name", bld["id"])
        rooms_in_bld = [rid for rid in bld.get("rooms", []) if rid in known_places]
        best_path = None
        best_room_id = None
        for rid in rooms_in_bld:
            p = _path_to_room(ctx.world, ctx.player.location, rid)
            if p is None:
                continue
            if best_path is None or len(p) < len(best_path):
                best_path = p
                best_room_id = rid
        if best_room_id is None:
            return f"{npc.name} is unsure of the way."
        if not best_path:
            return f"Welcome, you have arrived at {bld_name}."
        target = ctx.world.rooms[best_room_id]
        knowledge.teach(ctx.world,ctx.player,{'rooms':[target.id]})
        from engine.navigation import route_text
        return route_text(ctx.world,ctx.player,target.id)

    if _is_merchant(ctx.world, npc):
        stock = _stock_for(ctx.world, npc.source_def)
        item_candidates = []
        for s in stock:
            item_def = ctx.world.items.get(s["item"], {})
            item_candidates.append({
                "entry": s,
                "key": item_def.get("name", s["item"]),
            })
        item_matches = _fuzzy_match(topic, item_candidates)
        if item_matches:
            m = item_matches[0]["entry"]
            item_def = ctx.world.items.get(m["item"], {})
            qty_str = "unlimited" if m["qty"] is None else f"{m['qty']} left"
            return (f"{item_def.get('name', m['item'])} \u2014 "
                    f"{m['price']} gold ({qty_str}).")

    return f"{npc.name} does not seem to know about '{topic}'."

def _cmd_trade(ctx: CommandContext, args: str) -> str:
    """Open a merchant's wares, or fall back to talking."""
    merchants = []
    for eid in ctx.room.entities:
        ent = ctx.world.entities.get(eid)
        if not ent or ent.is_player or not ent.alive:
            continue
        if _is_merchant(ctx.world, ent) or (ctx.world.metadata.get("market_shifts") and (_def_for(ctx.world,ent) or {}).get("market_id")):
            merchants.append(ent)

    # No merchants in the room - trade acts as an alias for talk
    if not merchants:
        return _cmd_talk(ctx, args)

    target = args.strip()
    chosen = None
    if target:
        candidates = [{"entity": m, "key": m.name} for m in merchants]
        matches = _fuzzy_match(target, candidates)
        if matches:
            chosen = matches[0]["entity"]
        else:
            # Named NPC isn't a merchant - fall back to talk
            return _cmd_talk(ctx, args)
    elif len(merchants) == 1:
        chosen = merchants[0]
    else:
        names = ", ".join(m.name for m in merchants)
        return f"Trade with which merchant? ({names})"

    from engine import npc_attention
    from engine import livelihoods
    if ctx.world.metadata.get('market_shifts') and (_def_for(ctx.world,chosen) or {}).get('market_id'):
        from engine import market_shifts
        return market_shifts.menu(ctx.world,ctx.player,chosen)
    if not livelihoods.service_open(ctx.world,chosen):return chosen.name+' is off duty. '+livelihoods.hours_text(ctx.world,chosen)
    npc_attention.begin(ctx.world,ctx.player,chosen)
    npc_def = _def_for(ctx.world, chosen) or {}
    greeting = _greeting_for(ctx.world, chosen, npc_def, ctx.player)
    stock = _stock_for(ctx.world, chosen.source_def)
    if not stock:
        line = f"{chosen.name} has nothing to sell right now."
        return f"{greeting}\n{line}" if greeting else line
    return _render_stock(ctx.world, chosen.name, greeting, stock)

def _cmd_buy(ctx: CommandContext, args: str) -> str:
    raw = args.strip()
    if not raw:
        return "Buy what? Try 'buy <item>'."
    merchant_hint = ""
    lower = raw.lower()
    if " from " in lower:
        idx = lower.index(" from ")
        merchant_hint = raw[idx + 6:].strip()
        raw_item = raw[:idx].strip()
    else:
        raw_item = raw
    if not raw_item:
        return "Buy what?"

    merchants = []
    for eid in ctx.room.entities:
        ent = ctx.world.entities.get(eid)
        if not ent or ent.is_player or not ent.alive:
            continue
        if _is_merchant(ctx.world, ent):
            merchants.append(ent)

    if not merchants:
        return "No merchant here to trade with."

    if merchant_hint:
        candidates = [{"entity": m, "key": m.name} for m in merchants]
        matches = [row for row in candidates if row['entity'].id == merchant_hint] or _fuzzy_match(merchant_hint, candidates)
        if not matches:
            names = ", ".join(m.name for m in merchants)
            return f"No merchant '{merchant_hint}' here. Try: {names}."
        merchants = [matches[0]["entity"]]

    offers = []
    for merchant in merchants:
        npc_def = _def_for(ctx.world, merchant) or {}
        for entry in (npc_def.get("stock") or []):
            item_id = entry.get("item")
            if item_id not in ctx.world.items:
                continue
            item_def = ctx.world.items.get(item_id, {})
            offers.append((merchant, entry, item_id, item_def))

    item_matches = item_catalog.matches(item_catalog.item_rows(ctx.world, (offer[2] for offer in offers)), raw_item)
    if len(item_matches) > 1:
        raise ValueError(item_catalog.ambiguity(item_matches))
    selected_id = item_matches[0]['id'] if item_matches else None
    matching_merchants = list({offer[0].id: offer for offer in offers if offer[2] == selected_id}.values())

    if not matching_merchants:
        if len(merchants) == 1:
            return f"{merchants[0].name} doesn't sell '{raw_item}'."
        names = ", ".join(m.name for m in merchants)
        return f"No merchant here sells '{raw_item}'. Try: {names}."

    if len(matching_merchants) > 1:
        names = ", ".join(m.name for m, _, _, _ in matching_merchants)
        return (f"Multiple merchants sell '{raw_item}': {names}. "
                f"Try 'buy {raw_item} from <name>'.")

    merchant, entry, item_id, item_def = matching_merchants[0]
    from engine import livelihoods
    if not livelihoods.service_open(ctx.world,merchant):return merchant.name+' is off duty. '+livelihoods.hours_text(ctx.world,merchant)
    from engine import npc_attention
    npc_attention.begin(ctx.world,ctx.player,merchant)
    npc_def = _def_for(ctx.world, merchant) or {}
    state = ctx.world.shop_state.setdefault(merchant.source_def, {})
    price = int(entry.get("price", 0) or 0)
    initial = int(entry.get("qty", 1) or 0)
    from engine import needs_market
    if needs_market.enabled(ctx.world):
        needs_market.ensure(ctx.world);initial=max(1,initial);price=needs_market.merchant_price(ctx.world,merchant.source_def,item_id,price)
    current = state.get(item_id, initial) if initial > 0 else None

    if current is not None and current <= 0:
        return f"{merchant.name} is out of {item_def.get('name', item_id)}."
    if ctx.player.gold < price:
        return (f"You can't afford the {item_def.get('name', item_id)} "
                f"({price} gold, you have {ctx.player.gold}).")

    ctx.player.gold -= price
    ctx.player.inventory.append(item_id)
    merchant.gold += price
    from engine import task_skills
    for trader in (ctx.player,merchant):task_skills.practice(ctx.world,trader,'trading',difficulty=10,effort=1)
    if getattr(ctx.world,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(ctx.world,[merchant.id],f"Sold {item_def.get('name','an item')} for {price} gold.")
    if initial > 0:
        state[item_id] = current - 1

    return (f"You buy the {item_def.get('name', item_id)} "
            f"from {merchant.name} for {price} gold.")

def _role_for(world: World, entity: Entity) -> Optional[str]:
    if not entity.source_def:
        return None
    return world.npcs.get(entity.source_def, {}).get("role") or None


def _guard_building_for(world: World, entity: Entity) -> Optional[str]:
    if not entity.source_def:
        return None
    return world.npcs.get(entity.source_def, {}).get("guard_building") or None


def _advance_guards(world: World):
    """Advance NPCs that occupy a building, per patrol_mode.

    guard_building takes precedence; workplace_building is used
    when set on a working NPC. Stationary NPCs (guard_room /
    workplace_room / spawn_room only) never move.
    """
    for entity in list(world.entities.values()):
        from engine import npc_attention
        if npc_attention.paused(world,entity):continue
        if entity.is_player or not entity.alive:
            continue
        building_id = _guard_building_for(world, entity)
        if not building_id:
            defn = (world.npcs.get(entity.source_def, {})
                    if entity.source_def else {})
            building_id = defn.get("workplace_building")
        if not building_id:
            continue
        building = world.buildings.get(building_id)
        if not building:
            continue
        rooms_in_building = building.get("rooms", [])
        if entity.location not in rooms_in_building:
            continue
        chance = _npc_def_field(world, entity, "patrol_chance", 0.5)
        try:
            chance = float(chance)
        except (TypeError, ValueError):
            chance = 0.5
        if random.random() >= chance:
            continue
        mode = (_npc_def_field(world, entity, "patrol_mode", "random")
                or "random").lower()
        if mode == "none":
            continue
        if mode == "loop":
            target_id=entity.progress.get('building_patrol_target')
            if target_id not in rooms_in_building or entity.location==target_id:
                idx=rooms_in_building.index(entity.location)
                target_id=rooms_in_building[(idx+1)%len(rooms_in_building)]
                entity.progress['building_patrol_target']=target_id
            steps=frontiers.path(world,entity.location,target_id,entity)
            if steps and all(step[2] in rooms_in_building for step in steps):
                world.move_entity(entity.id, steps[0][2])
            continue
        # random adjacent walk within building
        current_room = world.rooms.get(entity.location)
        if not current_room:
            continue
        candidates = [r for di,r in current_room.exits.items()
                      if r in rooms_in_building and not frontiers.blocked(world,current_room.id,di,entity)]
        if not candidates:
            continue
        world.move_entity(entity.id, random.choice(candidates))


# ---------- corpse helpers ----------

def _corpse_mode_for(world: World, entity: Entity) -> str:
    if not entity.source_def:
        return "disappear"
    defn = world.npcs.get(entity.source_def, {})
    return defn.get("corpse", "disappear")


def _corpse_ttl(world: World, entity: Entity) -> float:
    if not entity.source_def:
        return 0
    defn = world.npcs.get(entity.source_def, {})
    return defn.get("corpse_ttl", 300)


def _corpse_label(world: World, entity: Entity) -> str:
    if entity.source_def:
        defn = world.npcs.get(entity.source_def, {})
        if "corpse_name" in defn:
            return defn["corpse_name"]
    return f"{entity.name} (dead)"


def _remove_entity(world: World, room: Room, entity_id: str):
    if entity_id in room.entities:
        room.entities.remove(entity_id)
    world.entities.pop(entity_id, None)


def _purge_expired_corpses(world: World, room: Room):
    now = time.monotonic()
    for eid in list(room.entities):
        ent = world.entities.get(eid)
        if (ent and not ent.alive and not ent.is_player
                and ent.corpse_expires_at is not None
                and now >= ent.corpse_expires_at):
            room.entities.remove(eid)
            world.entities.pop(eid, None)


# ---------- handlers ----------

def _cmd_look(ctx: CommandContext, args: str) -> str:
    _purge_expired_corpses(ctx.world, ctx.room)
    room = ctx.room
    building = ctx.world.building_for_room(room.id)
    header = room.name
    if building and building.get("name") and building["name"].strip().casefold() != room.name.strip().casefold():
        header = f"{room.name} ({building['name']})"
    lines = [header, resolve_description(room, ctx.world, ctx.player)]
    from engine.local_visibility import blind
    dark=blind(ctx.world,ctx.player)
    for di in (() if dark else room.exits):
        why=frontiers.blocked(ctx.world,room.id,di,ctx.player)
        if why:lines.append("Locked "+di+": "+why)
    if room.group:
        grp = ctx.world.groups.get(room.group)
        if grp:
            lines.append(f"Territory: {grp.get('name', room.group)}")
    alive = []
    for eid in room.entities:
        ent = ctx.world.entities.get(eid)
        if not ent or not ent.alive or ent.is_player or ent.id == ctx.player.id:
            continue
        role = _role_for(ctx.world, ent)
        if role:
            alive.append(f"{ent.name} ({role})")
        else:
            alive.append(ent.name)
    now = time.monotonic()
    corpses = []
    for eid in room.entities:
        ent = ctx.world.entities.get(eid)
        if (ent and ent.id != ctx.player.id and not ent.alive
                and not ent.is_player
                and (ent.corpse_expires_at is None
                     or now < ent.corpse_expires_at)):
            corpses.append(_corpse_label(ctx.world, ent))
    if dark:
        lines.append("Darkness hides the exits. You may try any direction, or use a working lantern.")
    elif room.exits:
        lines.append("Exits: " + ", ".join(sorted({_normalize_direction(e) for e in room.exits})))
    if alive:
        lines.append("You see: " + ", ".join(alive))
    if corpses:
        lines.append("Corpses: " + ", ".join(corpses))
    if room.items:
        loose, posted,books = [], [],[]
        for iid in room.items:
            item=ctx.world.items.get(iid)
            if item:
                (books if item.get('publication') else posted if item.get('anchored_readable') is True else loose).append(item['name'])
        if loose:lines.append("On the ground: " + ", ".join(loose))
        if books:lines.append(f"Bookshelves: {len(books)} volumes. Type books to browse.")
        if posted:lines.append("Posted reading: " + ", ".join(dict.fromkeys(posted)))
    if not dark:
        from engine import knowledge
        knowledge.observe_room(ctx.world,ctx.player,event_id='look:'+room.id+':'+str(getattr(ctx.world,'living_state',{}).get('minute',0)))
    return "\n".join(lines)

def _cmd_go(ctx: CommandContext, args: str) -> str:
    direction = args.strip()
    if not direction:
        from engine.local_visibility import blind
        if blind(ctx.world,ctx.player):return "Go where? Darkness hides exits; try a direction."
        if not ctx.room.exits:
            return "There is nowhere to go from here."
        return "Go where? Exits: " + ", ".join(sorted({_normalize_direction(e) for e in ctx.room.exits}))
    
    try:
        ctx.room.exits = normalize_exits(ctx.room.exits)
    except ValueError as exc:
        return "Exit configuration error: " + str(exc)
    target_key = None
    dir_lower = _normalize_direction(direction).lower()
    if dir_lower=='out' and 'step outside' in ctx.room.exits and not getattr(ctx.player,'_walking_exact_edge',False):
        dir_lower='step outside'
    for k in ctx.room.exits:
        if k.lower() == dir_lower or _normalize_direction(k).lower() == dir_lower:
            target_key = k
            break
            
    if target_key is None:
        return f"You can't go '{direction}'."
        
    reason = frontiers.blocked(ctx.world, ctx.room.id, target_key, ctx.player)
    if reason:return reason
    target_room_id = ctx.room.exits[target_key]
    if target_room_id not in ctx.world.rooms:
        return (f"The way {direction} is blocked. "
                f"(content error: room '{target_room_id}' does not exist)")
    last_hit=ctx.player.progress.get('geology_last_hit_minute')
    travel_remainder=None
    if ctx.world.metadata.get('society'):
        from engine import climate
        # Directions are immediate actions; clear cooldowns left by older saves.
        ctx.player.progress.pop('travel_ready_minute',None)
        target_details=living.details(ctx.world,target_room_id)
        if target_details.get('requires_boat') and not any(ctx.world.items.get(i,{}).get('boat') for i in ctx.player.inventory):return 'You need a boat to enter open water. Craft or buy a folding boat at a harbour workshop.'
        cost=climate.conditions(ctx.world,target_room_id)['travel_minutes']
        if getattr(ctx.world,'walk_on_clock',False):ctx.time_accounted=True
        if not ctx.time_accounted and not getattr(ctx.world,'realtime',False):
            from engine import travel_pacing
            cost,travel_remainder=travel_pacing.quote(ctx.world,ctx.player,cost)
            if cost==0:ctx.time_accounted=True
            elif cost>1:living.advance(ctx.world,cost-1)
    # Travel time may have caused injury, death, a new closure, or relocation.
    if not ctx.player.alive:return 'Your journey was interrupted. You are unconscious.'
    if ctx.player.progress.get('geology_last_hit_minute')!=last_hit:return 'Your journey was interrupted by a geological injury.'
    if ctx.player.location!=ctx.room.id:return 'Your journey was interrupted before you could leave.'
    if ctx.room.exits.get(target_key)!=target_room_id:return 'The route changed before you could leave.'
    reason=frontiers.blocked(ctx.world,ctx.room.id,target_key,ctx.player)
    if reason:return 'Your journey was interrupted. '+reason
    from engine import progression
    from engine import escorts
    escort_block=escorts.check(ctx.world,ctx.player,target_key,target_room_id)
    if escort_block:return escort_block
    if not ctx.world.move_entity(ctx.player.id,target_room_id):return 'You cannot pass.'
    if travel_remainder is not None:
        travel_pacing.commit(ctx.player,travel_remainder)
    from engine import companions
    for record in ctx.player.progress.get('companions',[]):
        pet=ctx.world.entities.get(record['id'])
        if pet and pet.alive and pet.location==ctx.room.id and pet.progress.get('companion_owner')==ctx.player.id and pet.progress.get('companion_order','follow')=='follow' and not frontiers.blocked(ctx.world,ctx.room.id,target_key,pet):
            ctx.world.move_entity(pet.id,target_room_id)
    advancement = progression.discovery(ctx.world, ctx.player, target_room_id)
    escort_note=escorts.accompany(ctx.world,ctx.player,ctx.room.id,target_key)
    _advance_guards(ctx.world)
    new_room = ctx.world.rooms[ctx.player.location]
    ambush = _trigger_room_spawns(ctx.world, new_room, ctx.player)
    new_ctx = CommandContext(
        world=ctx.world, player=ctx.player,
        room=new_room,
        registry=ctx.registry, raw=ctx.raw,
    )
    look_out = _cmd_look(new_ctx, "")
    if escort_note:look_out += "\n"+escort_note
    if advancement: look_out += "\n" + advancement
    direction = _normalize_direction(target_key).casefold()
    if direction in {"north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest", "up", "down", "in", "out"}:
        arrival = f"You go {direction}."
    elif direction == "enter building":
        arrival = f"You enter {new_room.name}."
    elif direction == "step outside":
        arrival = "You step outside."
    else:
        arrival = f"You arrive at {new_room.name}."
    return "\n\n".join(part for part in (arrival, "\n".join(ambush), look_out) if part)

def _cmd_inventory(ctx: CommandContext, args: str) -> str:
    if not ctx.player.inventory:
        return "You are empty-handed."
    if args.strip() or len(ctx.player.inventory) > item_catalog.PAGE_SIZE:
        return item_catalog.browse(ctx.world, args, player=ctx.player, ids=ctx.player.inventory)
    equipped_ids = set(ctx.player.equipped.values())
    parts = []
    for item_id in ctx.player.inventory:
        item = ctx.world.items.get(item_id)
        if not item:
            continue
        marker = " [equipped]" if item_id in equipped_ids else ""
        parts.append(f"{item['name']}{marker}")
    return "You carry: " + ", ".join(parts)


def _roll_stats(notation: str = "3d6") -> dict:
    """Roll NdX per stat. Returns dict of str/agi/int/vit."""
    m = re.match(r"^(\d+)d(\d+)$", (notation or "3d6").strip().lower())
    if not m:
        n, x = 3, 6
    else:
        n, x = int(m.group(1)), int(m.group(2))
    def one():
        return sum(random.randint(1, x) for _ in range(n))
    return {"str": one(), "agi": one(), "int": one(), "vit": one()}


def _cmd_score(ctx: CommandContext, args: str) -> str:
    p = ctx.player
    base_atk = p.attack
    eff_atk = effective_attack(ctx.world, p)
    base_def = p.defense
    eff_def = effective_defense(ctx.world, p)

    lines = [f"{p.name} — HP {p.hp}/{p.max_hp}, gold {p.gold}"]
    from engine import progression
    if progression.summary(ctx.world,p):lines.append(progression.summary(ctx.world,p))

    if eff_atk != base_atk:
        lines.append(f"Attack: {eff_atk} (base {base_atk}, +{eff_atk - base_atk})")
    else:
        lines.append(f"Attack: {eff_atk}")

    if eff_def != base_def:
        lines.append(f"Defense: {eff_def} (base {base_def}, +{eff_def - base_def})")
    else:
        lines.append(f"Defense: {eff_def}")

    if p.equipped:
        slots = []
        for slot, item_id in sorted(p.equipped.items()):
            item = ctx.world.items.get(item_id)
            name = item["name"] if item else item_id
            slots.append(f"{slot}: {name}")
        lines.append("Equipped: " + ", ".join(slots))
    else:
        lines.append("Equipped: nothing")

    lines.append(f"Carrying: {counted(len(p.inventory),'item')}")
    return "\n".join(lines)


def _cmd_attack(ctx: CommandContext, args: str) -> str:
    from engine import combat
    target=combat.target(ctx.world,ctx.player,args)
    combat.validate(ctx.world,ctx.player,target)
    combat.ammunition(ctx.world,ctx.player)
    return combat.strike(ctx.world,ctx.player,target)


def _cmd_equip(ctx: CommandContext, args: str) -> str:
    target = args.strip()
    if not target:
        return "Equip what?"
    item = item_catalog.choose(item_catalog.item_rows(ctx.world, ctx.player.inventory), target,
                               missing=f"You don't have any '{target}'.")
    item_id = item['id']
    slot = _slot_for(ctx.world, item_id)
    if slot is None:
        from engine import fishing
        if fishing.is_rod(item):
            return f"Carry the {item['name']} in your inventory; no equipment slot is needed. At a fishing site, use fish or use {item['name']}. Use survey to find local fishing resources."
        return f"The {item['name']} can't be equipped."
    previous = ctx.player.equipped.get(slot)
    ctx.player.equipped[slot] = item_id
    if previous and previous != item_id:
        prev_item = ctx.world.items.get(previous)
        prev_name = prev_item["name"] if prev_item else previous
        return (f"You equip the {item['name']}, "
                f"replacing the {prev_name}.")
    return f"You equip the {item['name']}."


def _cmd_unequip(ctx: CommandContext, args: str) -> str:
    target = args.strip()
    if not target:
        return "Unequip what?"
    item = item_catalog.choose(item_catalog.item_rows(ctx.world, ctx.player.equipped.values()), target,
                               missing=f"You don't have '{target}' equipped.")
    for slot, item_id in list(ctx.player.equipped.items()):
        if item_id == item['id']:
            del ctx.player.equipped[slot]
    return f"You unequip the {item['name']}."


def _transfer_item(ctx: CommandContext, args: str, taking: bool) -> str:
    target=args.strip()
    all_units=target.casefold().startswith('all ')
    if all_units:target=target[4:].strip()
    verb='take' if taking else 'drop'
    if not target:return f"{verb.title()} what? Try '{verb} <item>' or '{verb} all <item>'."
    source=ctx.room.items if taking else ctx.player.inventory
    destination=ctx.player.inventory if taking else ctx.room.items
    item=item_catalog.choose(item_catalog.item_rows(ctx.world,source),target,
                             missing=f"No '{target}' here to take." if taking else f"You don't have any '{target}'.")
    iid=item['id']
    if taking and item.get('anchored_readable') is True:return f"The {item['name']} is fixed here for everyone to read; it cannot be carried away."
    if not taking and iid in ctx.player.equipped.values():return f"Unequip the {item['name']} first."
    quantity=source.count(iid) if all_units else 1
    for _ in range(quantity):source.remove(iid);destination.append(iid)
    claims=ctx.world.item_claims.setdefault(ctx.room.id,{})
    if taking:claims[iid]=claims.get(iid,0)+quantity
    elif claims.get(iid,0)>0:
        claims[iid]=max(0,claims[iid]-quantity)
        if not claims[iid]:del claims[iid]
    return f"You {verb} {quantity} × {item['name']}." if all_units else f"You {verb} the {item['name']}."


def _cmd_take(ctx: CommandContext, args: str) -> str:
    if args.strip().casefold() == 'all':
        # Reuse individual transfers, including their claims/eligibility rules.
        # Dispatch remains one action, so one pile does not advance N ticks.
        if not ctx.room.items:
            return 'There are no items on the floor to take.'
        results = []
        unavailable = 0
        fixed = False
        for item_id in list(dict.fromkeys(ctx.room.items)):
            if item_id not in ctx.world.items:
                unavailable += ctx.room.items.count(item_id)
                continue
            if ctx.world.items[item_id].get('anchored_readable') is True:
                fixed = True
                continue
            try:
                results.append(_transfer_item(ctx, 'all ' + item_id, True))
            except ValueError as exc:
                results.append(str(exc))
        if unavailable:
            results.append('Some floor items have unavailable definitions and were left in place.')
        if fixed and not results:
            return 'The reading material is fixed here. Use Read to open it.'
        return '\n'.join(results)
    return _transfer_item(ctx,args,True)


def _cmd_drop(ctx: CommandContext, args: str) -> str:
    return _transfer_item(ctx,args,False)


def _cmd_use(ctx: CommandContext, args: str) -> str:
    target = args.strip()
    if not target:
        return "Use what? Try 'use <item>'."
    item = item_catalog.choose(item_catalog.item_rows(ctx.world, ctx.player.inventory), target,
                               missing=f"You don't have any '{target}'.")
    from engine import fishing
    if fishing.is_rod(item):
        if not living.enabled(ctx.world):
            return 'Living-world fishing is not enabled for this world.'
        return fishing.fish(ctx,rod_id=item['id'])
    if item.get('prepared_ability'):
        return 'Use Abilities > Prepared spell scrolls to choose a target, or invoke <scroll> at <target>.'
    if item.get("type") != "consumable":
        return f"The {item['name']} isn't something you can use."
    if item.get('learn_ability') in ctx.world.abilities:
        from engine import ability_rules
        ability_rules.lesson_check(ctx.world,ctx.player,ctx.world.abilities[item['learn_ability']])
    gained = min(ctx.player.max_hp - ctx.player.hp, item.get("heal", 0))
    gained = living.heal(ctx.world,ctx.player,gained)
    ctx.player.inventory.remove(item['id'])
    if living.enabled(ctx.world):
        living.on_use(ctx.world, ctx.player, item)
        return f"You use the {item['name']}. Recovered {gained} HP. " + living.command(ctx, "", "condition")
    if gained:
        return f"You use the {item['name']} and recover {gained} HP."
    return f"You use the {item['name']}, but you're already at full HP."


def _cmd_map(ctx, args):
    from engine.mapping import render, room_records
    p=ctx.player
    if p.location not in p.explored_rooms: p.explored_rooms.append(p.location)
    packet=render(room_records(ctx.world), p.location, p.id, [dict(id=p.id,name=p.name,location=p.location,marker='@')], p.explored_rooms, strict=True)
    from engine.local_visibility import blind,conceal_routes
    if blind(ctx.world,p):
        packet=render(room_records(ctx.world),p.location,p.id,[dict(id=p.id,name=p.name,location=p.location,marker='@')],p.explored_rooms,strict=True,local_visible=set())
        conceal_routes(packet)
    from engine.coordinates import describe as describe_coordinates
    return ctx.world.rooms[p.location].name + '\n' + describe_coordinates(packet['coordinates']) + '\n' + '\n'.join(packet['exits'])


def _cmd_read(ctx, args):
    query = args.strip()
    if not query: return 'Read what? Use read <item>.'
    ids = list(dict.fromkeys(ctx.player.inventory + ctx.room.items))
    copies=item_catalog.item_rows(ctx.world,ids)
    if not item_catalog.matches(copies,query):
        journal=ctx.player.progress.get('reading_journal_v1',[])
        known=item_catalog.item_rows(ctx.world,journal)
        if item_catalog.matches(known,query):
            remembered=item_catalog.choose(known,query)
            from engine.reading_room import publication_text
            return publication_text(ctx.world,remembered)+remembered.get('read_text','')
    item=item_catalog.choose(copies,query,missing='That item is not here or in your inventory.')
    if item.get('newspaper'):
        from engine.gazette import browse
        return browse(ctx.world,ctx.player,item.get('press_edition',''))
    if item.get('read_text'):
        from engine import ability_rules
        ability_rules.disclose(ctx.world,ctx.player,item)
        from engine import quest_progress
        quest_progress.action(ctx.player, 'read:' + item['id'])
        from engine import knowledge
        knowledge.read_source(ctx.world,ctx.player,item['id'])
        from engine.quest_discovery import disclose
        disclose(ctx.world,ctx.player,item.get('knowledge',{}),'item',item['id'])
    from engine import knowledge
    from engine.quest_discovery import offer_text
    text=knowledge.from_text(ctx.world,ctx.player,item.get('read_text') or item.get('description') or 'There is nothing to read.', source=('item',item['id']))
    from engine.reading_room import finish, publication_text
    return publication_text(ctx.world,item)+text+offer_text(ctx.world,ctx.player,item.get('knowledge',{}).get('quests',[]))+finish(ctx.world,ctx.player,item)


def _cmd_say(ctx: CommandContext, args: str) -> str:
    if not args:
        return "Say what?"
    return f'You say: "{args}"'


def _cmd_help(ctx: CommandContext, args: str) -> str:
    from engine.help import command_help
    return command_help(ctx, ctx.registry, args)


def _cmd_groups(ctx: CommandContext, args: str) -> str:
    playable = [g for g in ctx.world.groups.values()
                if g.get("visibility") == "playable"]
    if not playable:
        return "No factions are available to join."
    lines = ["Available factions:"]
    for g in sorted(playable, key=lambda x: x.get("name", x["id"])):
        marker = " <-- you" if ctx.player.group_id == g["id"] else ""
        lines.append(f"  {g.get('name', 'Unnamed faction')}{marker}")
    if ctx.player.group_id:
        cur = ctx.world.groups.get(ctx.player.group_id)
        if cur:
            lines.append("")
            lines.append(f"You belong to {cur.get('name', ctx.player.group_id)}.")
    lines.append("")
    lines.append("Type 'join <faction name>' to choose.")
    return "\n".join(lines)


def _cmd_join(ctx: CommandContext, args: str) -> str:
    from engine.player_names import pick
    authored=ctx.world.groups.get(args.strip().lower())
    if authored and authored.get('visibility')!='playable':return 'They do not accept new members.'
    try:
        group=pick([dict(g,name=g.get('name','Unnamed faction')) for g in ctx.world.groups.values() if g.get('visibility')=='playable'],args,'faction')
    except ValueError as exc:return str(exc) if str(exc).startswith('Be more specific') else 'No faction matches that name.'
    target=group['id']
    if group.get("visibility") != "playable":
        return f"The {group.get('name', target)} do not accept new members."
    if ctx.player.group_id == target:
        return f"You are already a member of {group.get('name', target)}."
    ctx.player.group_id = target
    return f"You are now a member of {group.get('name', target)}."


def _cmd_leave(ctx: CommandContext, args: str) -> str:
    if not ctx.player.group_id:
        return "You are not in any faction."
    old = ctx.world.groups.get(ctx.player.group_id)
    old_name = old.get('name', ctx.player.group_id) if old else ctx.player.group_id
    ctx.player.group_id = None
    return f"You leave the {old_name}."


def _cmd_faction(ctx: CommandContext, args: str) -> str:
    if not ctx.player.group_id:
        return "You have no faction. Type 'groups' to see options."
    group = ctx.world.groups.get(ctx.player.group_id)
    if group is None:
        return f"You are in an unknown faction '{ctx.player.group_id}'."
    lines = [f"You belong to {group.get('name', ctx.player.group_id)}."]
    if group.get("description"):
        lines.append(group["description"])
    hostile_to = group.get("hostile_to") or []
    if hostile_to:
        names = []
        for h in hostile_to:
            if h == "*":
                names.append("all others")
            else:
                hg = ctx.world.groups.get(h)
                names.append(hg.get("name", h) if hg else h)
        lines.append("Hostile to: " + ", ".join(names))
    return "\n".join(lines)


# ---------- registry ----------

def build_registry() -> CommandRegistry:
    reg = CommandRegistry()
    reg.register(Command("look", "Describe your surroundings", "look",
                         _cmd_look, aliases=["l"], example="look"))
    reg.register(Command("go", "Move through an exit", "go <direction>",
                         _cmd_go, example="go north"))
    reg.register(Command("inventory", "List what you carry", "inventory",
                         _cmd_inventory, aliases=["i", "inv"], example="inventory"))
    from engine import navigation
    reg.register(Command("waypoint", "Set or clear a globe destination", "waypoint <known place|clear>", navigation.waypoint, example="waypoint <known place>"))
    reg.register(Command("track", "Track an accepted quest", "track <quest name>", lambda ctx,args:navigation.command(ctx,args), example="track Supper from the Land"))
    reg.register(Command("untrack", "Stop tracking a quest", "untrack <quest name|all>", lambda ctx,args:navigation.command(ctx,args,True), example="untrack all"))
    reg.register(Command("catalog", "Search items and their crafting recipes", "catalog [words] [slot:head] [collection:gear] [page:2]",
                         lambda ctx, args: item_catalog.browse(ctx.world, args, player=ctx.player),
                         example="catalog slot:head collection:gear"))
    reg.register(Command("wardrobe", "Browse gear and clothing", "wardrobe [words] [slot:head] [page:2]",
                         lambda ctx, args: item_catalog.browse(ctx.world, args, player=ctx.player, wardrobe=True),
                         example="wardrobe collection:clothing"))
    reg.register(Command("score", "Show your character status", "score",
                         _cmd_score, aliases=["sc", "me", "st"], example="score"))
    reg.register(Command("attack", "Attack a creature here", "attack [target]",
                         _cmd_attack, aliases=["a", "k"],
                         example="attack grey wolf",
                         help_text="Without a target, attacks the first hostile present."))
    reg.register(Command("equip", "Equip a weapon or armor", "equip <item>",
                         _cmd_equip, aliases=["wield", "wear"], example="equip rusty blade"))
    reg.register(Command("unequip", "Remove an equipped item", "unequip <item>",
                         _cmd_unequip, example="unequip rusty blade"))
    reg.register(Command("take", "Pick up an item", "take <item> | take all | take all <item>",
                         _cmd_take, aliases=["get"], example="take bread"))
    reg.register(Command("drop", "Drop an item onto the ground", "drop <item>",
                         _cmd_drop, aliases=["put"], example="drop bread"))
    reg.register(Command("use", "Consume an item", "use <item>",
                         _cmd_use, example="use bread"))
    reg.register(Command("groups", "List factions you can join", "groups",
                         _cmd_groups, example="groups"))
    reg.register(Command("join", "Join a faction", "join <group_id>",
                         _cmd_join, example="join wayfarers"))
    reg.register(Command("leave", "Leave your current faction", "leave",
                         _cmd_leave, example="leave"))
    reg.register(Command("faction", "Show your faction and enemies", "faction",
                         _cmd_faction, aliases=["whoami"], example="faction"))
    reg.register(Command("talk", "Talk to an NPC in the room", "talk <npc> [about <topic>]",
                         _cmd_talk, aliases=["speak", "greet"],
                         example="talk guard about graveyard",
                         help_text="Merchants list stock; guards give directions; others greet you."))
    reg.register(Command("trade", "Open a merchant's wares", "trade <npc>",
                         _cmd_trade, aliases=["shop", "browse"], example="trade innkeeper"))
    reg.register(Command("buy", "Buy an item from a merchant", "buy <item> [from <npc>]",
                         _cmd_buy, aliases=["purchase"], example="buy bread from innkeeper"))
    reg.register(Command("say", "Speak to the room", "say <message>",
                         _cmd_say, example="say hello"))
    reg.register(Command("help", "Show commands and hints", "help [command]",
                         _cmd_help, aliases=["h", "?"], example="help attack"))
    from engine import reading_room,gazette,npc_activity,chronicles
    reg.register(Command("history","Read the world's three histories","history [geology|civilization|individual] [search] [page]",
                         chronicles.command,aliases=["chronicles"],example="history geology"))
    from engine import wildlands,ward_life
    for word,fn,hint in [('expedition',wildlands.command,'Follow a trail or examine an expedition site'),('sanity',wildlands.command,'Check your resolve and memories'),('ward',ward_life.command,'Visit the ward register or help house')]:
        reg.register(Command(word,hint,word,fn,available=lambda ctx,word=word:bool(getattr(ctx.world,"rules",{}).get("ward")) if word=="ward" else wildlands.enabled(ctx.world)))
    from engine import escorts
    for mode in ('follow','lead'):
        reg.register(Command(mode,'Travel with a quest companion',mode+' <name|stop>',
            lambda ctx,args,mode=mode:escorts.command(ctx,args,mode),example=mode+' Rowan'))
    reg.register(Command("watch","See what nearby people and creatures are doing","watch [name]",lambda ctx,args:npc_activity.watch(ctx.world,ctx.player,args),example="watch"))
    reg.register(Command("books","Browse this room’s shelves or your reading journal","books [read] [filter]",lambda ctx,args:reading_room.browse(ctx.world,ctx.player,args),example="books read"))
    reg.register(Command("news","Read the local newspaper or choose an edition","news [editions | place] [yesterday] [/all]",lambda ctx,args:gazette.browse(ctx.world,ctx.player,args),example="news editions"))
    reg.register(Command("read", "Read an accessible item", "read <item>", _cmd_read, example="read village notice"))
    reg.register(Command("map", "Open the terrain map and show your location", "map", _cmd_map, example="map"))
    for name, (brief, example) in living.COMMANDS.items():
        reg.register(Command(name, brief, example, lambda ctx, args, name=name: living.command(ctx,args,name), example=example, available=lambda ctx: living.enabled(ctx.world)))
    from engine import society, trade_view
    society.register(reg)
    trade_view.register(reg)
    from engine import settlements
    settlements.register(reg)
    from engine import relationships
    reg.register(Command('dialogue','Quest dialogue, directions and NPC services',
        'dialogue <npc> [about <topic>]',_cmd_dialogue,
        example='dialogue Chef Ragnar',available=lambda ctx: living.enabled(ctx.world) or bool(ctx.world.metadata.get('society'))))
    relationships.register(reg)
    from engine import social,companions
    social.register(reg)
    companions.register(reg)
    from engine import singing
    singing.register(reg)
    from engine import locks
    locks.register(reg)
    from engine import theft_commands
    theft_commands.register(reg)
    from engine import guilds
    guilds.register(reg)
    from engine import artworks
    artworks.register(reg)
    from engine import employment
    employment.register(reg)
    from engine import task_skills
    task_skills.register(reg)
    from engine.interactions import combine
    reg.register(Command("combine","Use an editable object interaction","combine <interaction-id> on <target>",combine,example="combine Hammer and Repair Kit on lw_sword",available=lambda ctx:society.enabled(ctx.world)))
    return reg


# ---------- dispatcher ----------

def process_command(registry: CommandRegistry, world: World,
                    player: Entity, text: str, *, resolve_shortcuts: bool = True) -> str:
    text = text.strip()
    if not text:
        return "Type 'help' for commands."
    words = text.split(maxsplit=1)
    first = words[0].lower()
    rest = words[1] if len(words) > 1 else ""
    expansion = world.shortcuts.get(first) if resolve_shortcuts else None
    if expansion:
        text = expansion + (" " + rest if rest else "")
        words = text.split(maxsplit=1)
        first = words[0].lower()
        rest = words[1] if len(words) > 1 else ""
    # Wake self leaves NPC waking intact and never advances the world clock.
    if first=='wake' and rest.strip().lower() in ('','self','me') and living.enabled(world):
        from engine import resting
        return resting.command(world,player,'stop','rest')
    cmd = registry.resolve(first)
    if cmd is None:
        return f"Unknown command '{first}'. Type 'help'."
    ctx = CommandContext(
        world=world, player=player,
        room=world.rooms[player.location],
        registry=registry, raw=text,
    )
    if cmd.available is not None and not cmd.available(ctx):
        return "You can't do that here."
    if player.location not in player.explored_rooms: player.explored_rooms.append(player.location)
    if living.enabled(world) and not player.alive and first not in ("revive", "wait", "help", "condition", "quests", "map", "interface"):
        return "You are unconscious. Use revive to recover at the starting settlement."
    from engine import mortality, society
    if society.enabled(world) and player.progress.get('permanently_dead') and first!='interface':
        return 'This character has died permanently. Their history is retained; create a new character from the starting screen.'
    if society.enabled(world) and player.progress.get('restrained_until',0)>living.state(world)['minute'] and first not in ('look','help','condition','map','interface'):
        living.advance(world,1)
        return 'A guard is restraining you. Wait briefly before acting again.'
    from engine import knowledge
    knowledge.sync(world,player,observe=True)
    from engine import resting
    from engine import sleep_movement
    blocked=sleep_movement.blocked_command(world,player,text,registry,resolve_shortcuts=False)
    if blocked:return blocked
    resting.before_command(world,player,cmd.name+(' '+rest if rest else ''))
    old_location = player.location
    try:
        result = cmd.handler(ctx, rest)
        from engine import society
    except ValueError as exc:
        return str(exc)
    if living.enabled(world):
        if not ctx.time_accounted and cmd.name not in ("rest", "sleep", "wait", "help", "look", "map", "survey", "recipes", "songs", "skills", "catalog", "wardrobe", "materials", "market", "adventures", "quests", "journal", "condition", "inventory", "time", "inspect", "spells", "companions", "services", "route", "guide", "interface", "track", "untrack", "waypoint"):
            living.advance(world, 1)
        if player.alive and (old_location != player.location or first == "look"):
            event = living.on_entry(world, player)
            if event: result += "\n" + event
    if not player.alive: mortality.record_death(world,player)
    if player.location not in player.explored_rooms: player.explored_rooms.append(player.location)
    knowledge.sync(world,player,observe=True)
    return result
