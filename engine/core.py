# engine/core.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import weakref


@dataclass
class Entity:
    id: str
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    gold: int = 0
    inventory: List[str] = field(default_factory=list)
    location: Optional[str] = None
    is_player: bool = False
    source_def: Optional[str] = None
    corpse_expires_at: Optional[float] = None
    equipped: Dict[str, str] = field(default_factory=dict)
    group_id: Optional[str] = None
    reputation: Dict[str, int] = field(default_factory=dict)
    spawner_key: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    race: Optional[str] = None
    char_class: Optional[str] = None
    sex: Optional[str] = None
    description: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)
    abilities: List[str] = field(default_factory=list)
    explored_rooms: List[str] = field(default_factory=list)
    progress: dict = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int, defense: Optional[int] = None, *, source=None, cause=None, kind='injury') -> int:
        world_ref = getattr(self, '_world_ref', None)
        world = world_ref() if world_ref else None
        if world is not None and source is not None and kind == 'combat':
            from engine import starter_safety
            # Direct attack paths also honor the refuge. Automatic counters
            # are a response, not a new voluntary decision to begin a fight.
            if getattr(source, 'is_player', False) and cause != 'counterattack':
                starter_safety.provoke(world, source, self)
            if starter_safety.blocked(world, source, self):
                from engine import city_defense
                city_defense.note_attempt(world, source, self)
                return 0
        effective_def = self.defense if defense is None else defense
        dmg = max(1, amount - effective_def)
        before = self.hp
        self.hp = max(0, self.hp - dmg)
        if dmg and not self.is_player and str(getattr(self,"activity","")).startswith("sleeping"):
            self._sleep_damage=True
        if self.is_player:
            from engine import resting
            resting.signal(self,'you were hurt')
            if world is not None and before > self.hp:
                from engine import damage_feedback
                damage_feedback.record(world, self, before-self.hp, source=source, cause=cause, kind=kind)
        if world is not None and before > self.hp and source is not None and kind == 'combat':
            from engine import city_defense, starter_safety
            starter_safety.on_damage(world, source, self, before-self.hp)
            city_defense.on_damage(world, source, self, before-self.hp, cause=cause, kind=kind)
        return dmg


@dataclass
class Room:
    id: str
    name: str
    description: str
    exits: Dict[str, str] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    description_variants: List[dict] = field(default_factory=list)
    group: Optional[str] = None
    spawners: List[dict] = field(default_factory=list)
    map_x: Optional[int] = None
    map_y: Optional[int] = None
    map_z: Optional[int] = None
    map_symbol: str = "."
    map_visibility: str = "discovered"


class World:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.entities: Dict[str, Entity] = {}
        self.items: Dict[str, dict] = {}
        self.npcs: Dict[str, dict] = {}
        self.quests: Dict[str, dict] = {}
        self.buildings: Dict[str, dict] = {}
        self.groups: Dict[str, dict] = {}
        self.spawner_state: Dict[str, dict] = {}
        self.spawner_counter: Dict[str, int] = {}
        self.item_claims: Dict[str, Dict[str, int]] = {}
        self.shop_state: Dict[str, Dict[str, int]] = {}
        self.races: Dict[str, dict] = {}
        self.classes: Dict[str, dict] = {}
        self.sexes: Dict[str, dict] = {}
        self.abilities: Dict[str, dict] = {}
        self.metadata: dict = {}
        self.shortcuts: Dict[str, str] = {}
        self.killed_npcs: set = set()
        self.start_room: Optional[str] = None

    def index_spawners(self, room):
        if not hasattr(self,'spawner_rooms'):
            self.spawner_rooms={}
        if any(s.get('automatic') for s in room.spawners):
            self.spawner_rooms[room.id]=room
        else:
            self.spawner_rooms.pop(room.id,None)

    def add_room(self, room: Room):
        self.rooms[room.id] = room
        self.index_spawners(room)

    def bind_entity(self, entity: Entity):
        """Attach ephemeral callbacks when creating, resuming or reloading."""
        entity._world_ref = weakref.ref(self)

    def add_entity(self, entity: Entity, room_id: str):
        self.bind_entity(entity)
        from engine.shield_compat import restore_equipped
        restore_equipped(self, entity)
        from engine import property_interiors
        room_id=property_interiors.restored_location(self,entity,room_id)
        self.entities[entity.id] = entity
        entity.location = room_id
        self.rooms[room_id].entities.append(entity.id)
        from engine import property_interiors
        property_interiors.reconcile_home(self,entity)
        if not entity.is_player:
            from engine import npc_life
            npc_life.ensure(self, entity, check=True)

    def move_entity(self, entity_id: str, new_room_id: str, *, forced=False):
        ent = self.entities[entity_id]
        from engine import regional_world
        if new_room_id!=ent.location and not forced and regional_world.blocked(self,ent,new_room_id):
            return False
        if new_room_id!=ent.location and not ent.is_player and ent.progress.get('escort_post') and not forced and not getattr(ent,'_escort_step',False):
            return False
        from engine import sleep_movement
        if new_room_id != ent.location and sleep_movement.asleep(self, ent):
            if not forced:return False
            sleep_movement.wake(self, ent, 'you were moved by an external force')
        from engine import community_quests
        if new_room_id!=ent.location and not forced and not getattr(ent,'_herding',False) and community_quests.frozen(self,ent):return False
        old = self.rooms[ent.location]
        if not forced and new_room_id != ent.location:
            from engine import property_interiors
            if property_interiors.blocked(self,ent,ent.location,None,new_room_id):return False
            from engine import locks
            passages=[di for di,dest in old.exits.items() if dest==new_room_id]
            lock_index=locks.index(self,cache=True) if passages else {}
            if passages and all(locks.blocked(self,old.id,di,ent,lock_index=lock_index) for di in passages):return False
        if ent.is_player and new_room_id!=ent.location:
            from engine import resting
            resting.cancel(self,ent,'you left your resting place')
        if new_room_id!=ent.location:
            for key in ('_fight_display','_visible_action'):
                if hasattr(ent,key):delattr(ent,key)
        if entity_id in old.entities:
            old.entities.remove(entity_id)
        if new_room_id!=old.id:
            getattr(self,"living_state",{}).get("public_program_v1",{}).get("tickets",{}).pop(entity_id,None)
        ent.location = new_room_id
        self.rooms[new_room_id].entities.append(entity_id)
        if new_room_id!=old.id:community_quests.movement(self,ent,old.id,new_room_id)
        if new_room_id!=old.id and getattr(self,'living_state',{}).get('resident_watches'):
            from engine import resident_watch
            resident_watch.note(self,[ent.id],f'Left {old.name} for {self.rooms[new_room_id].name}.')
        if new_room_id != old.id and not forced:
            from engine import town_talk
            town_talk.travel(self, ent, old.id, new_room_id)
        if new_room_id != old.id and ent.is_player:
            from engine import resource_nodes
            resource_nodes.clear_manual_turns(self,ent.id)
            from engine import quest_progress
            quest_progress.visit(ent, new_room_id)
        if new_room_id != old.id and getattr(self,"expedition_country",False):
            from engine import wildlands
            wildlands.entered(self,ent,old.id)
        if new_room_id != old.id:
            regional_world.on_entry(self,ent)
            if ent.is_player:
                from engine import starter_safety
                starter_safety.on_move(self,ent,old.id,new_room_id)
        return True

    def entities_in_room(self, room_id: str) -> List[Entity]:
        return [self.entities[eid] for eid in self.rooms[room_id].entities
                if eid in self.entities and self.entities[eid].alive]

    def building_for_room(self, room_id: str) -> Optional[dict]:
        """Return the building dict containing this room, or None."""
        for bld in self.buildings.values():
            if room_id in bld.get("rooms", []):
                return bld
        return None
