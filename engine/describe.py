# engine/describe.py
"""Resolve descriptions that change based on world / player state.

Schema (on rooms, items, NPCs, quests):
    "description": "default text",
    "description_variants": [
        {"when": {"killed": ["rat"]},           "text": "..."},
        {"when": {"player_has": ["key"]},       "text": "..."},
        {"when": {"player_hp_below": 10},       "text": "..."},
        {"when": {"quest_active": ["q1"]},      "text": "..."},
        {"when": {"quest_completed": ["q1"]},   "text": "..."},
        {"when": {},                            "text": "..."}  # fallback
    ]

All keys inside a single "when" are AND'd. First matching variant wins.
No match -> falls back to the plain "description".

Resolved text supports references:
    {npc:<id>}    -> the NPC's display name
    {item:<id>}   -> the item's display name
    {quest:<id>}  -> the quest's display name
    {room:<id>}   -> the room's display name

Missing references are left as the raw token ({npc:ghost}) so the author
can spot a typo when it renders.
"""
import re

from engine.core import Entity, World


_TOKEN_RE = re.compile(r"\{(\w+):([\w_]+)\}")


def resolve_description(obj, world: World, player: Entity) -> str:
    """Pick a variant that matches current state, else default. Render tokens."""
    if isinstance(obj, dict):
        default = obj.get("description", "")
        variants = obj.get("description_variants", [])
    else:
        default = getattr(obj, "description", "")
        variants = getattr(obj, "description_variants", []) or []
    for variant in variants:
        if _matches(variant.get("when", {}), world, player):
            return _render_tokens(variant.get("text", default), world)
    return _render_tokens(default, world)


def _matches(when: dict, world: World, player: Entity) -> bool:
    if not when:
        return True
    if "world_flag" in when and not getattr(world,'living_state',{}).get('flags',{}).get(when['world_flag']):
        return False
    if "killed" in when:
        if not all(k in world.killed_npcs for k in when["killed"]):
            return False
    if "player_has" in when:
        if not all(i in player.inventory for i in when["player_has"]):
            return False
    if "player_hp_below" in when:
        if not player.hp < when["player_hp_below"]:
            return False
    if "quest_active" in when:
        from engine.quest_progress import status
        if not all(status(world, player, q) == "active" for q in when["quest_active"]):
            return False
    if "quest_completed" in when:
        from engine.quest_progress import status
        if not all(status(world, player, q) == "complete"
                   for q in when["quest_completed"]):
            return False
    return True


def _render_tokens(text: str, world: World) -> str:
    """Substitute {kind:id} references with friendly names."""
    def repl(m):
        kind, ident = m.group(1), m.group(2)
        if kind == "npc":
            d = world.npcs.get(ident)
            return d["name"] if d else m.group(0)
        if kind == "item":
            d = world.items.get(ident)
            return d["name"] if d else m.group(0)
        if kind == "quest":
            d = world.quests.get(ident)
            return d["name"] if d else m.group(0)
        if kind == "room":
            d = world.rooms.get(ident)
            return d.name if d else m.group(0)
        return m.group(0)
    return _TOKEN_RE.sub(repl, text or "")
