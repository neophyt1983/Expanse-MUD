# server/game_server.py
import asyncio
import json
import uuid
import secrets
import hashlib
from pathlib import Path

import websockets
import websockets.exceptions

from engine.loader import build_world, spawn_npcs, start_room_for
from engine import loader as engine_loader
from engine.core import Entity
from engine import living, frontiers, society
from server.society_server import SocietyServer
import sqlite3
from engine.persistence import init_db, save_player, load_player
from engine.commands import (
    build_registry, process_command as dispatch,
    _roll_stats, _slot_for, advance_spawners,
)

SAVE_DIR = Path(__file__).parent.parent / "save"

# None = use per-mode default (see _state_path). Tests override this.
WORLD_STATE_PATH = None


class GameServer(SocietyServer):
    def __init__(self, mode="single", initial_slot=None):
        self.watch_views = {}
        self.selected_slots = {}
        self.detached_players = set()
        self.local_save_player = None
        self.loaded_named_world = initial_slot is not None
        self.mode = mode
        self.init_society()
        self.closing = False
        self.world = build_world()
        from engine import streets, chronicles
        streets.install(self.world)
        chronicles.attach(self.world)
        self.world.realtime = (self.mode == 'host')
        self.world.deferred_rest = True
        spawn_npcs(self.world)
        self._init_shop_state()
        self.registry = build_registry()
        from server.adventures import storage_dir,mode_for
        adventure_mode=mode_for(self.world.game_dir,SAVE_DIR,engine_loader.GAMES_DIR)
        if adventure_mode and adventure_mode!=self.mode:raise ValueError("Continue this adventure in its original solo/host mode.")
        self.adventure_storage = storage_dir(self.world.game_dir, SAVE_DIR, engine_loader.GAMES_DIR)
        from engine import persistence
        self.database_path = self.adventure_storage/"world.db" if self.adventure_storage else Path(persistence.DB_PATH)
        # A session database is never a durable save. All routine commits remain
        # in RAM; only an explicit Save publishes a paired checkpoint.
        self.db = init_db(self.database_path, memory=True)
        self.clients = {}
        self.map_markers = {}
        self.last_maps = {}
        self.atlas_subscribers = set()
        self.last_atlases = {}
        self._atlas_locks = {}
        try:
            if initial_slot:
                from server import save_slots
                meta,data=initial_slot
                save_slots.apply_players(self.db,data['players'],mode,Path(self.world.game_dir).name)
                self.local_save_player=meta['player']
                self.selected_slots[meta['player']]=meta
                self._apply_world_state(data['world'])
            else:self._load_world_state()
        except Exception:
            self.db.close()
            raise
        from engine import population
        population.ensure(self.world)
        # Place the starting housing stock before a player can see the first street.
        from engine import settlements
        if settlements.enabled(self.world):
            settlements.init(self.world)
        frontiers.population(self.world)
        from engine import dynamic_diplomacy
        try:dynamic_diplomacy.ensure(self.world)
        except Exception:
            self.db.close()
            raise
        for owner in list(living.state(self.world)["camps"]):
            if not self.db.execute("SELECT 1 FROM players WHERE id=?",(owner,)).fetchone():living.state(self.world)["camps"].pop(owner,None)
        self.capture_checkpoint()

    def capture_checkpoint(self):
        from engine import save_transaction
        self.db.commit()
        if hasattr(self,'checkpoint_db'):self.checkpoint_db.close()
        self.checkpoint_db=sqlite3.connect(':memory:')
        self.db.backup(self.checkpoint_db)
        path=self._state_path();self.checkpoint_path=path
        self.checkpoint_state=path.read_bytes() if path.exists() else None

    async def freeze_for_slot_load(self):
        if any(ws not in self.host_sockets for ws in self.clients):
            raise ValueError('Other players are connected. They must leave before the host can load a world checkpoint.')
        self.closing=True
        self.discarding=True

    async def discard_shutdown(self):
        self.closing=True
        self.discarding=True
        return True

    # ─── world state path resolution ─────────────────────────────────
    def _state_path(self) -> Path:
        """Where the world state JSON lives.

        Priority:
          1. Explicit WORLD_STATE_PATH (tests set this via monkeypatch)
          2. If DATA_DIR is outside games/ (a test tmp_path), isolate
             the state file next to it — prevents cross-test leakage.
          3. Standard save/world_state_<mode>.json for real games.
        """
        if WORLD_STATE_PATH is not None:
            return Path(WORLD_STATE_PATH)
        if getattr(self,"adventure_storage",None):
            return self.adventure_storage / "world_state.json"
        try:
            data_dir = Path(getattr(self.world, "game_dir", engine_loader.DATA_DIR)).resolve()
            games_dir = Path(engine_loader.GAMES_DIR).resolve()
            data_dir.relative_to(games_dir)
            # Standard game — use project save/
            suffix = "" if data_dir.name == "default" else "_" + data_dir.name
            return SAVE_DIR / f"world_state{suffix}_{self.mode}.json"
        except ValueError:
            # DATA_DIR is outside games/ → test isolation
            return Path(getattr(self.world, "game_dir", engine_loader.DATA_DIR)) / f"world_state_{self.mode}.json"

    # ─── shop state initialization ──────────────────────────────────
    def _init_shop_state(self):
        """Populate world.shop_state from NPC stock definitions.

        Called once after build_world()/spawn_npcs(), before saved
        state is loaded. Saved state then overrides quantities.
        Accepts stock entries as either {"item": id, "qty": n} or
        a bare item id string (qty defaults to 10).
        """
        if not hasattr(self.world, "shop_state"):
            self.world.shop_state = {}
        for npc_id, npc_def in self.world.npcs.items():
            stock = npc_def.get("stock") or []
            if not stock:
                continue
            quantities = {}
            for entry in stock:
                if isinstance(entry, str):
                    quantities[entry] = 10
                elif isinstance(entry, dict):
                    item_id = entry.get("item")
                    qty = entry.get("qty",
                                     entry.get("quantity",
                                               entry.get("initial", 10)))
                    if item_id:
                        try:
                            quantities[item_id] = int(qty)
                        except (TypeError, ValueError):
                            quantities[item_id] = 10
            if quantities:
                self.world.shop_state[npc_id] = quantities

    # ─── state load/save ────────────────────────────────────────────
    def _load_world_state(self):
        path = self._state_path()
        from engine import save_transaction
        save_transaction.recover(self.db, path)
        if not path.exists():
            return
        try:
            self._apply_world_state(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise RuntimeError(f"Cannot load world save {path.name}; original file preserved: {exc}") from exc

    def _apply_world_state(self, data):
        self._validate_saved_world(data)
        self.world.killed_npcs = set(data.get("killed_npcs", []))
        self.world.item_claims = data.get("item_claims", {})
        saved_shop = data.get("shop_state", {})
        # Merge saved quantities onto initialized state
        for def_id, state in saved_shop.items():
            if def_id in self.world.shop_state:
                for item_id, qty in state.items():
                    if item_id in self.world.shop_state[def_id]:
                        self.world.shop_state[def_id][item_id] = qty
            else:
                self.world.shop_state[def_id] = dict(state)

        # Sync killed NPCs so they don't spawn on boot
        for room in self.world.rooms.values():
            for eid in list(room.entities):
                ent = self.world.entities.get(eid)
                if (ent and not ent.is_player
                        and ent.source_def in self.world.killed_npcs):
                    room.entities.remove(eid)
                    del self.world.entities[eid]

        # Apply item claims so chests/rooms stay empty
        for room_id, room_claims in self.world.item_claims.items():
            room = self.world.rooms.get(room_id)
            if not room:
                continue
            used = dict(room_claims)
            kept = []
            for item_id in room.items:
                if used.get(item_id, 0) > 0:
                    used[item_id] -= 1
                else:
                    kept.append(item_id)
            room.items = kept
        living.restore(self.world, data.get("living", {}))

    @staticmethod
    def _validate_saved_world(data):
        if not isinstance(data, dict):raise ValueError("world state must be an object")
        killed=data.get('killed_npcs', [])
        if not isinstance(killed, list) or any(not isinstance(x,str) for x in killed):raise ValueError("invalid killed_npcs")
        for key in ('item_claims','shop_state'):
            records=data.get(key,{})
            if not isinstance(records,dict):raise ValueError('invalid '+key)
            for name,values in records.items():
                if not isinstance(name,str) or not isinstance(values,dict):raise ValueError('invalid '+key)
                if any(not isinstance(i,str) or type(q) is not int or q<0 for i,q in values.items()):raise ValueError('invalid '+key+' quantity')
        if not isinstance(data.get('living',{}),dict):raise ValueError('invalid living state')
        saved=data.get('living',{})
        for key in ('state','spawners','floors'):
            if not isinstance(saved.get(key,{}),dict):raise ValueError('invalid living '+key)
        npcs=saved.get('npcs',[])
        if not isinstance(npcs,list) or any(not isinstance(n,dict) or not isinstance(n.get('source_def'),str) for n in npcs):raise ValueError('invalid saved NPCs')
        if any(not isinstance(items,list) or any(not isinstance(item,str) for item in items) for items in saved.get('floors',{}).values()):raise ValueError('invalid saved floor items')
        from engine import npc_life
        for npc in npcs: npc_life.validate_saved(npc.get('progress', {}))


    def _save_world_state(self, *, explicit=True):
        from engine import save_transaction
        try:
            if not explicit:
                self.db.commit()
                return True
            from server.save_slots import world_data
            data = world_data(self.world)
            self.db.commit()
            if explicit:
                durable = init_db(self.database_path)
                try:
                    # Reuse the recoverable paired transaction: DB and world
                    # advance together, never as independent autosave writes.
                    save_transaction.restore_checkpoint(durable, self.db, self._state_path(),
                        json.dumps(data, separators=(',', ':')).encode('utf-8'))
                finally: durable.close()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Failed to save world state: {e}")
            return False

    def _stage_players_and_world(self):
        try:
            for player in list(self.world.entities.values()):
                if player.is_player:save_player(self.db,player,self.mode,commit=False,mark_saved=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        getattr(self.world,'dirty_players',set()).clear()

    def _save_players_and_world(self, player_id=None):
        """Publish gameplay only when the player explicitly requests it."""
        from server import save_slots
        player = player_id or self.local_save_player
        entry = self.selected_slots.get(player)
        if entry or player in self.detached_players or (self.loaded_named_world and player):
            actor = self.world.entities.get(player) or load_player(self.db,player,self.mode)
            name = entry['name'] if entry else actor.name
            self.selected_slots[player] = save_slots.write(self,SAVE_DIR,player,name,entry=entry)
            self.detached_players.discard(player)
            return
        self._stage_players_and_world()
        from server import adventures
        slug=Path(self.world.game_dir).name
        def checkpoint():
            if not self._save_world_state(explicit=True):
                raise OSError('World save failed; previous save preserved.')
        from datetime import datetime, timezone
        stamps=[]
        for pid,raw,saved_at in self.db.execute('SELECT id,progress,saved_at FROM players WHERE game_mode=?',(self.mode,)):
            if json.loads(raw or '{}').get('world_slug','default')==slug:stamps.append((pid,saved_at))
        now=datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.db.executemany('UPDATE players SET saved_at=? WHERE id=?',[(now,pid) for pid,_ in stamps]);self.db.commit()
        try:target=adventures.publish_pending(engine_loader.GAMES_DIR,SAVE_DIR,slug,checkpoint)
        except Exception:
            self.db.executemany('UPDATE players SET saved_at=? WHERE id=?',[(stamp,pid) for pid,stamp in stamps]);self.db.commit()
            raise
        if self.adventure_storage and target != Path(self.world.game_dir):
            self.world.game_dir=target
            engine_loader.set_game_dir(target)
            adventures.finish_publish(SAVE_DIR,slug)
        self.capture_checkpoint()

    def _persist_moderation(self):
        """Persist explicit ban/unban decisions without saving gameplay."""
        durable=init_db(self.database_path)
        try:
            from server import dm_console
            from types import SimpleNamespace
            dm_console.ensure(SimpleNamespace(db=durable,world=self.world,mode=self.mode))
            world=dm_console.world_key(self)
            durable.execute('DELETE FROM dm_bans WHERE world=?',(world,))
            for row in self.db.execute('SELECT * FROM dm_bans WHERE world=?',(world,)):
                durable.execute('INSERT INTO dm_bans VALUES(?,?,?,?,?,?,?,?)',row)
            durable.commit()
        finally:durable.close()

    def _save_dirty_players(self):
        if self.mode!='host' and getattr(self.world,'dirty_players',set()):self._stage_players_and_world()

    def _autosave_host_tick(self):
        # Ordinary host commands stay in memory until this shared world tick.
        # Never commit character rows ahead of their matching world generation.
        if self.mode=='host' and self.clients and not self.closing:
            self._stage_players_and_world()

    async def prepare_shutdown(self, *, require_empty=False, save=False):
        """Save synchronously on the game loop before allowing process shutdown."""
        # No await between the membership check and closing: both run on the
        # authoritative loop, so a player cannot join between them.
        if require_empty and self.clients:
            raise ValueError('Every player must Save and Return to Start before changing adventures. The current world is still running.')
        self.closing=True
        try:
            if save:self._save_players_and_world()
            else:self.discarding=True
        except Exception:
            self.closing=False
            raise
        return True

    async def delete_character(self, player_id, world_slug=None, *, owner=False, delete_token=None):
        if self.closing:raise ValueError("Expanse is shutting down.")
        if player_id in self.clients.values():raise ValueError("This character is playing. Save and return to the start screen before deleting it.")
        expected=world_slug or Path(self.world.game_dir).name
        row=self.db.execute("SELECT progress FROM players WHERE id=? AND game_mode=?",(player_id,self.mode)).fetchone()
        if row is None:raise ValueError("This save no longer exists in the selected mode.")
        details=json.loads(row[0] or '{}')
        supplied=hashlib.sha256((delete_token if isinstance(delete_token,str) else '').encode()).hexdigest()
        if not owner and not secrets.compare_digest(details.get('delete_token_hash',''),supplied):raise ValueError('Only the save owner or local host can delete this character.')
        if details.get('world_slug','default')!=expected:raise ValueError("This save belongs to another world.")
        camps=living.state(self.world)['camps']
        old_camp=camps.pop(player_id,None)
        try:
            # Deleting a chosen save is explicit, but must not also save every
            # unrelated change currently being tested in this session.
            if self.database_path.exists():
                durable=init_db(self.database_path)
                try:
                    from engine import save_transaction
                    save_transaction.recover(durable,self._state_path())
                    durable.execute("DELETE FROM players WHERE id=? AND game_mode=?",(player_id,self.mode))
                    path=self._state_path()
                    if path.exists():
                        saved=json.loads(path.read_text())
                        self._validate_saved_world(saved)
                        saved.get('living',{}).get('state',{}).get('camps',{}).pop(player_id,None)
                        save_transaction.commit(durable,path,saved)
                    else:durable.commit()
                finally:durable.close()
            self.db.execute("DELETE FROM players WHERE id=? AND game_mode=?",(player_id,self.mode))
            self.db.commit()
        except Exception:
            self.db.rollback()
            if old_camp is not None:camps[player_id]=old_camp
            raise
        ent=self.world.entities.pop(player_id,None)
        if ent and ent.location in self.world.rooms and player_id in self.world.rooms[ent.location].entities:
            self.world.rooms[ent.location].entities.remove(player_id)
        return {"ok":True,"deleted":player_id}

    async def saved_characters(self, world_slug=None):
        from engine.persistence import list_saves
        # Session rows also exist for characters who have never pressed Save.
        # Read the last published checkpoint, including undated legacy saves.
        if self.loaded_named_world:
            # Other members of a hosted checkpoint must also be able to rejoin.
            return [p for p in list_saves(self.db,self.mode,world_slug or Path(self.world.game_dir).name)
                    if p.get('saved_at')]
        if not self.database_path.is_file():
            return []
        durable = init_db(self.database_path, memory=True)
        try:
            result = list_saves(durable, self.mode, world_slug or Path(self.world.game_dir).name)
        finally:
            durable.close()
        for entry in result:
            room=self.world.rooms.get(entry['location'])
            if room:entry['location']=room.name
            entry['unsaved']=False
        from server.save_slots import visible_characters
        return visible_characters(SAVE_DIR,result)

    # ─── character creation ─────────────────────────────────────────
    async def create_account_character(self, account, data):
        from server.accounts import name_key, display_name, CharacterNameUnavailable
        requested=display_name(' '.join(filter(None,(data.get('first_name'),data.get('last_name')))))
        world=Path(self.world.game_dir).name
        existing=None
        for row in self.db.execute('SELECT id,name,progress FROM players WHERE game_mode=?',(self.mode,)):
            if json.loads(row[2] or '{}').get('world_slug','default')!=world:
                continue
            try:previous_key=name_key(row[1])
            except ValueError:continue
            if previous_key==name_key(requested):
                if not self.accounts.owns(account,row[0]):
                    raise CharacterNameUnavailable('That character name is already in use in this world.')
                existing=row[0]
        display=self.accounts.character_identity(account,requested)
        if existing:
            return {'player_id':existing,'name':display}
        first,_,last=display.partition(' ')
        result=await self.create_character({**data,'first_name':first,'last_name':last})
        try:
            self.accounts.claim(account,result['player_id'])
        except Exception:
            await self.delete_character(result['player_id'],world,owner=True)
            raise
        return result

    async def create_character(self, data: dict) -> dict:
        if self.closing:raise ValueError("Expanse is shutting down.")
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        if not first:
            raise ValueError("first name is required")

        race_id = (data.get("race") or "").strip() or None
        class_id = (data.get("class") or "").strip() or None
        sex_id = (data.get("sex") or "").strip() or None
        faction_id = (data.get("faction") or "").strip() or None

        if frontiers.active(self.world):
            if race_id not in self.world.races or class_id not in self.world.classes:
                raise ValueError("Choose a race and class for your character.")
            if faction_id not in self.world.groups or self.world.groups[faction_id].get('visibility')!='playable':
                raise ValueError("Choose a playable faction and its starting city.")
        notation = (getattr(self.world, "metadata", {}) or {}).get(
            "stat_roll", "3d6")
        stats = _roll_stats(notation)

        races = getattr(self.world, "races", {}) or {}
        classes = getattr(self.world, "classes", {}) or {}

        race = races.get(race_id) if race_id else None
        if race:
            for stat, bonus in (race.get("bonuses") or {}).items():
                if stat in stats:
                    stats[stat] += int(bonus)

        cls = classes.get(class_id) if class_id else None
        if cls:
            primary = cls.get("primary_stat")
            if primary and primary in stats:
                stats[primary] += 2

        attack = 4 + stats["str"] // 3
        defense = 1 + stats["agi"] // 3
        max_hp = 20 + stats["vit"]

        name = f"{first} {last}".strip()
        pid = str(uuid.uuid4())
        player = Entity(
            id=pid, name=name,
            hp=max_hp, max_hp=max_hp,
            attack=attack, defense=defense,
            is_player=True,
            first_name=first, last_name=last,
            race=race_id, char_class=class_id, sex=sex_id,
            description=data.get("description") or "",
            stats=dict(stats), group_id=faction_id,
        )

        from engine.character_style import validate, choices
        if 'appearance' in data:
            player.progress['character_style']=validate(data['appearance'],choices(race or {},cls or {}))
        abilities = []
        for source in (race, cls):
            if source:
                for ab in (source.get("starting_abilities") or []):
                    if ab not in abilities:
                        abilities.append(ab)
        player.abilities = abilities

        inventory = []
        if cls:
            for item_id in (cls.get("starting_equipment") or []):
                if item_id in self.world.items:
                    inventory.append(item_id)
        delete_token=secrets.token_urlsafe(32)
        player.progress["delete_token_hash"]=hashlib.sha256(delete_token.encode()).hexdigest()
        player.progress["world_slug"] = Path(self.world.game_dir).name
        player.inventory = inventory
        if living.enabled(self.world):
            player.gold = self.world.classes.get(player.char_class, {}).get("starting_gold", 25)
            living.progress(player)

        best_weapon_bonus = -1
        best_armor_bonus = -1
        best_offhand_bonus = -1
        for item_id in inventory:
            slot = _slot_for(self.world, item_id)
            if not slot:
                continue
            item_def = self.world.items.get(item_id, {})
            if slot == "weapon":
                bonus = item_def.get("attack_bonus", 0)
                if bonus > best_weapon_bonus:
                    player.equipped["weapon"] = item_id
                    best_weapon_bonus = bonus
            elif slot == "armor":
                bonus = item_def.get("defense_bonus", 0)
                if bonus > best_armor_bonus:
                    player.equipped["armor"] = item_id
                    best_armor_bonus = bonus

            elif slot == "offhand":
                bonus = item_def.get("defense_bonus", 0)
                if bonus > best_offhand_bonus:
                    player.equipped["offhand"] = item_id
                    best_offhand_bonus = bonus

        from engine import combat
        combat.starter_ammunition(self.world,player)
        start_room = None
        if faction_id:
            fdef = self.world.groups.get(faction_id) or {}
            sr = fdef.get("start_room")
            if sr and sr in self.world.rooms:
                start_room = sr
        if not start_room:
            start_room = start_room_for(self.world)

        self.world.add_entity(player, start_room)
        try:self._stage_players_and_world()
        except Exception:
            self.world.entities.pop(player.id,None)
            room=self.world.rooms.get(start_room)
            if room and player.id in room.entities:room.entities.remove(player.id)
            raise

        return {
            "player_id": pid, "delete_token": delete_token, "name": name, "start_room": start_room,
            "race": race_id, "class": class_id, "sex": sex_id,
            "faction": faction_id, "stats": stats,
            "attack": attack, "defense": defense, "max_hp": max_hp,
            "abilities": abilities, "inventory": inventory,
        }

    def mark_explored(self, player_id):
        player = self.world.entities[player_id]
        from engine import community_quests
        if community_quests.available(self.world):community_quests.meet(self.world,player)
        if player.location not in player.explored_rooms:
            player.explored_rooms.append(player.location)
        return player

    async def host_globe(self, slug, center):
        from engine.mapping import compile_map, room_records
        from engine.world_atlas import render
        if Path(self.world.game_dir).name != slug:
            raise ValueError('Choose the running game to view its host globe.')
        if not hasattr(self.world,'_compiled_map'):
            self.world._compiled_map=compile_map(room_records(self.world))
        packet=render(self.world._compiled_map,center,designer=True)
        players=await self.globe_players(slug)
        for room in packet['rooms']:
            if room['id'] in players:room['host_players']=sorted(players[room['id']])
        return packet

    async def globe_players(self, slug):
        if Path(self.world.game_dir).name != slug:
            return {}
        result = {}
        for pid in set(self.clients.values()):
            player = self.world.entities.get(pid)
            if player:
                result.setdefault(player.location, []).append(player.name)
        return result

    def map_for(self, player_id):
        from engine.mapping import render, room_records
        player = self.mark_explored(player_id)
        from engine import knowledge
        knowledge.sync(self.world, player, observe=True)
        from engine import chronicles
        chronicles.meet(self.world, player)
        known_rooms = knowledge.ids(self.world, player, 'rooms')
        active = []
        for pid in dict.fromkeys(self.clients.values()):
            ent = self.world.entities.get(pid)
            if ent is None: continue
            if pid not in self.map_markers:
                available = '123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                self.map_markers[pid] = next((c for c in available if c not in self.map_markers.values()), '*')
            active.append(dict(id=pid,name=ent.name,location=ent.location,marker=self.map_markers[pid]))
        # Ordinary maps contain only visited rooms and the viewer's marker.
        if not hasattr(self.world,'_compiled_map'):
            from engine.mapping import compile_map
            self.world._compiled_map=compile_map(room_records(self.world))
        from engine.local_visibility import sight,known_facades
        view=sight(self.world,player,self.world._compiled_map)
        from engine.world_atlas import remember
        remember(player,view['rooms'],self.world._compiled_map)
        packet = render([], player.location, player_id, [a for a in active if a['id']==player_id], player.explored_rooms, compiled=self.world._compiled_map, strict=True, local_visible=view['rooms'] | known_facades(self.world,player,self.world._compiled_map,view), local_positions=view.get('positions'))
        packet['visual']['travel_window']=True
        from engine.travel_window import window, paint_ground
        for tile in packet['visual']['tiles']:
            paint_ground(self.world, self.world._compiled_map, tile)
        from engine.build_info import BUILD
        packet['visual']['terrain_release'] = '1.9.1'
        packet['visual']['surface_survey'] = bool(self.world.rules.get('tile_survey'))
        packet['visual']['map_build'] = BUILD
        # Deliver the measured terrain with the movement itself. Ordinary updates
        # at the same location refresh nearby ground without resending the whole screen.
        extent = getattr(player, '_travel_view_extent', None)
        last_position, _ = getattr(self, 'map_positions', {}).get(player_id, (None, 0))
        opening = [5, 9]
        if extent:
            opening = extent if last_position != (self.world, player.location) else [
                min(size, default) for size, default in zip(extent, opening)]
        packet['visual'].update(follow_view=True, follow_extent=extent,
                                travel_world=Path(getattr(self.world, 'game_dir', '') or '').name,
                                opening_extent=opening,
                                opening_tiles=window(self.world, player, self.world._compiled_map, opening))
        packet['visual']['sight']={k:v for k,v in view.items() if k not in ('rooms','positions')}
        from engine.describe import resolve_description
        from engine.commands import _is_merchant
        room = self.world.rooms[player.location]
        def item_view(iid):
            item = self.world.items.get(iid, {})
            return dict(id=iid, name=item.get('name',iid), description=item.get('description',''),
                        publication=item.get('publication'),readable=bool(item.get('read_text')), anchored_readable=item.get('anchored_readable') is True, type=item.get('type','misc'),
                        slot=item.get('slot'), equipped=iid in player.equipped.values(),location=society.locate(self.world,player,iid),origin=self.world.rooms[item.get('location')].name if item.get('location') in known_rooms else 'Origin not learned',durability=society.durability(player,iid))
        from engine.visual_mapping import current_actors, apply_world_surfaces, apply_npc_counts
        lit=view['rooms'] if view['daylight'] or view['light_source'] else set()
        actors=current_actors(self.world,player_id,self.clients.values(),nearby_rooms=lit)
        packet['visual']['actors']=actors
        apply_world_surfaces(self.world, packet['visual'])
        from engine.pixel_art import apply as apply_pixel_art
        apply_pixel_art(self.world, packet['visual'])
        ground_art={'tiles':packet['visual']['opening_tiles']}
        apply_pixel_art(self.world, ground_art)
        if ground_art.get('pixel_assets'):
            packet['visual'].setdefault('pixel_assets',{}).update(ground_art['pixel_assets'])
        packet['visual']['actors']=[a for a in actors if a['room']==player.location]
        from engine.costumes import distant_portrait
        packet['visual']['nearby_actors']=[distant_portrait(a) for a in actors if a['room']!=player.location]
        blocked_exits = {direction: frontiers.blocked(self.world, room.id, direction, player) for direction in room.exits}
        for exit_row in packet['visual']['exits']:
            reason = blocked_exits.get(exit_row['direction'])
            if reason:
                exit_row['blocked'] = reason
        for link in packet['visual']['links']:
            if link['from'] == room.id and blocked_exits.get(link['direction']):
                link['blocked'] = blocked_exits[link['direction']]
        packet['exits'] = [line + (' [LOCKED: ' + blocked_exits[line.split(' -> ')[0]] + ']' if blocked_exits.get(line.split(' -> ')[0]) else '') for line in packet['exits']]
        apply_npc_counts(self.world, player_id, packet['visual'], blocked_exits)
        from engine import relationships, mortality
        from engine import companion_union
        if not companion_union.eligible(self.world,player):player.progress['companions']=[c for c in player.progress.get('companions',[]) if c['id'] not in mortality.state(self.world)['deaths']]
        if society.enabled(self.world):
            packet['relationships']=relationships.view(self.world,player)
            from engine import social,companions
            packet['social']=social.view(self.world,player)
            packet['companions']=companions.view(self.world,player)
        from engine import taming
        packet['taming']=taming.view(self.world,player)
        from engine import locks
        packet['locks']=locks.projection(self.world,player)
        packet['locksmiths']=locks.teachers(self.world,player)
        packet['lock_skill']=locks.skill(self.world,player)
        from engine import trade_view
        commerce_by_id={row['id']:row.get('commerce',{}) for row in packet.get('social',{}).get('npcs',[])}
        packet['location'] = dict(id=room.id, name=room.name,
            description=resolve_description(room,self.world,player),
            items=[item_view(i) for i in room.items if i in self.world.items],
            npcs=[dict(id=e.id,name=e.name,merchant=_is_merchant(self.world,e),trade_available=trade_view.available(self.world,player,e,commerce_by_id.get(e.id)),description=self.world.npcs.get(e.source_def,{}).get('description',''),title=self.world.npcs.get(e.source_def,{}).get('title',''),location=room.name) for e in self.world.entities_in_room(room.id) if not e.is_player],
            players=[p for p in active if p['location']==room.id])
        from engine import gathering, civic_program, soundtrack, streets
        if not hasattr(self.world,'media_session'):
            from uuid import uuid4
            self.world.media_session=uuid4().hex
        packet['media_world']=self.world.media_session
        packet['visual']['passages']=streets.doorways(self.world,player,packet['visual'],blocked_exits)
        packet['music_cue']=soundtrack.cue(self.world,player)
        packet['soundtrack']=packet['music_cue']['track']
        if living.enabled(self.world):
            packet['location']['gathering']=gathering.listing(self.world,player)
            packet['location']['services']=civic_program.view(self.world,player)
        from engine import settlements
        if settlements.enabled(self.world):packet['settlements']=settlements.view(self.world,player)
        from engine.trail_guidance import signs
        packet['waymarks']=signs(self.world,player)
        packet['needs_economy']=bool(self.world.metadata.get('needs_economy'))
        if self.world.metadata.get('market_shifts'):
            from engine import market_shifts
            packet['market_summary']=market_shifts.summary(self.world,player)
        packet['character'] = dict(id=player.id,name=player.name,hp=player.hp,max_hp=player.max_hp,
            gold=player.gold,race=player.race,char_class=player.char_class,
            race_name=self.world.races.get(player.race,{}).get("name",""),class_name=self.world.classes.get(player.char_class,{}).get("name",""),
            inventory=[item_view(i) for i in player.inventory if i in self.world.items])
        from engine import damage_feedback
        packet['damage_events'] = damage_feedback.recent(player)
        from engine import progression
        packet["character"]["advancement"]=progression.view(self.world,player)
        if living.enabled(self.world):
            from engine import worldtime,climate
            packet["calendar"]=worldtime.date(living.state(self.world)["minute"],self.world.metadata.get("sunrise_minute",375))
            packet["calendar_text"]=worldtime.describe(living.state(self.world)["minute"],self.world.metadata.get("sunrise_minute",375))
            packet["weather"]=climate.conditions(self.world,player.location)
            packet["living"] = dict(minute=living.state(self.world)["minute"], conditions={k:v for k,v in living.progress(player).items() if k in {'mana','max_mana','intoxication','injury','disease','hair'}}, facilities=living.details(self.world,room.id).get("facilities",[]))
        if not view['radius']:
            from engine.local_visibility import conceal_routes
            conceal_routes(packet)
        positions=self.__dict__.setdefault('map_positions',{})
        last,revision=positions.get(player_id,(None,0))
        if last!=(self.world,player.location):
            revision+=1
            positions[player_id]=((self.world,player.location),revision)
        packet['position_revision']=revision
        from engine import wildlands,ward_life
        if wildlands.enabled(self.world):
            here=wildlands.cell(self.world,player.location)
            options=[]
            for reach in self.world.field_regions:
                if player.location==reach.gate:options.append(('Enter '+reach.name,'expedition enter'))
            if here:
                i,x,y=here
                options.extend([('Read the trail','expedition'),('Seek shelter','expedition shelter'),('Check sanity and memories','sanity')])
                if (x,y)==(0,self.world.field_regions[i].trail_y):options.append(('Return to town','expedition return'))
                if (x,y)==(self.world.field_regions[i].landmark_x,self.world.field_regions[i].trail_y):options.extend([('Search for the relic','expedition search'),('Face the vigil','expedition face')])
            ward=self.world.rules.get('ward',{})
            if player.location==ward.get('gate'):options.append(('Visit '+ward['name'],'ward visit'))
            if ward and player.location.startswith(ward['prefix']):options.append(('Read the local register','ward'))
            packet['location']['field_actions']=[dict(id=cmd,label=label,command=cmd) for label,cmd in options]
            if here:
                reach=self.world.field_regions[here[0]]
                packet['location']['description']+=' '+reach.hazards[(living.state(self.world)['minute']//15)%3]

        from engine import escorts
        packet['companion_union']=companion_union.panel(self.world,player)
        if packet['companion_union']:
            known_rooms.update((packet['companion_union']['yard'],packet['companion_union']['hall']))
        packet['walking_destinations']=[dict(id=rid,name=self.world.rooms[rid].name) for rid in sorted(known_rooms) if rid in self.world.rooms and self.world.rooms[rid].map_visibility!='hidden']
        packet['escort']=escorts.advice(self.world,player)
        options=escorts.choices(self.world,player)
        for entry in packet['location']['npcs']:
            n=self.world.entities[entry['id']]
            entry['escorts']=[{'mode':q['escort']['mode'],'quest':q['id'],'name':q['name']} for q in options if q['escort']['npc']==n.source_def]
        return packet

    def _atlas_compiled(self):
        if not hasattr(self.world, '_compiled_map'):
            from engine.mapping import compile_map, room_records
            self.world._compiled_map = compile_map(room_records(self.world))
        return self.world._compiled_map

    def atlas_for(self, player_id):
        from engine.world_atlas import render
        player = self.world.entities[player_id]
        from engine.local_visibility import sight,known_facades
        compiled=self._atlas_compiled()
        from engine import world_atlas, country_edges
        country_edges.extend(self.world, player.location, 32, 18)
        visible=sight(self.world,player,compiled)['rooms']
        nearby=set(world_atlas.remember(player,visible,compiled)) | visible
        packet=render(compiled, player.location, player.explored_rooms,nearby=nearby)
        packet.update(world_atlas.terrain_map(self.world,compiled))
        from engine.pixel_art import decorate_rooms
        packet['pixel_assets']=decorate_rooms(self.world.game_dir,packet.get('rooms',[])) if getattr(self.world,'game_dir',None) else {}
        from engine.local_visibility import blind
        from engine.world_atlas import conceal_routes
        return conceal_routes(packet) if blind(self.world,player) else packet

    def close_atlas(self, websocket, discard_lock=False):
        getattr(self, 'atlas_subscribers', set()).discard(websocket)
        getattr(self, 'last_atlases', {}).pop(websocket, None)
        if discard_lock:
            getattr(self, '_atlas_locks', {}).pop(websocket, None)

    async def send_atlas(self, websocket, force=False):
        if websocket not in getattr(self, 'atlas_subscribers', ()):
            return
        if not hasattr(self, '_atlas_locks'):
            self._atlas_locks = {}
        lock = self._atlas_locks.setdefault(websocket, asyncio.Lock())
        async with lock:
            if websocket in getattr(self, 'atlas_subscribers', ()):
                await self._send_atlas_locked(websocket, force)

    async def _send_atlas_locked(self, websocket, force=False):
        pid = self.clients.get(websocket)
        player = self.world.entities.get(pid)
        if player is None:
            self.close_atlas(websocket)
            return
        location = player.location
        compiled = self._atlas_compiled()
        discovery = tuple(player.explored_rooms)
        from engine.local_visibility import sight,known_facades
        from engine import world_atlas
        local=sight(self.world,player,compiled)['rooms']
        nearby=set(world_atlas.remember(player,local,compiled)) | local
        if not hasattr(self, 'last_atlases'):
            self.last_atlases = {}
        old = self.last_atlases.get(websocket)
        from engine.local_visibility import blind
        dark=blind(self.world,player)
        if old is not None and old.get('blind')!=dark:force=True
        same_world = old is not None and old['compiled'] is compiled and old['pid'] == pid
        if not force and same_world and old['location'] == location and old['discovery'] == discovery and old.get('nearby',set()) == nearby and old.get('terrain_version')==getattr(self.world,'_atlas_ground',{}).get('version'):
            return
        byid = compiled[0]
        visible = (set(discovery) & set(byid)) | ({location} if location in byid else set()) | nearby
        center = location if location in byid else None
        packet = None
        if not force and same_world and (nearby or old.get('nearby')):
            from engine.world_atlas import render
            previous_visited=(set(old['discovery']) & set(byid)) | {old['location']}
            visited=(set(discovery) & set(byid)) | ({location} if location in byid else set())
            changed=(visible-old['visible']) | ((previous_visited ^ visited) & visible)
            changed.update(rid for rid in (location,old['location']) if rid in visible)
            packet=render(compiled,center,changed & visited,nearby=changed-visited)
            packet['type']='world_atlas_update'
            packet['removed']=sorted(old['visible']-visible)
            from engine.coordinates import project
            placed=old['placed']+sum(project(byid[rid],compiled[1][rid])['world'] is not None for rid in visible-old['visible'])-sum(project(byid[rid],compiled[1][rid])['world'] is not None for rid in old['visible']-visible)
            floors=({compiled[1][rid][2] for rid in visible} if previous_visited-visited else old['floors']|{r['z'] for r in packet['rooms']})
            packet['floors']=sorted(floors)
            packet['counts']=dict(visible=len(visible),placed=placed)
        elif not force and same_world and not nearby and not old.get('nearby') and visible == old['visible']:
            placed, floors = old['placed'], old['floors']
            if (old['location'] != location or
                    old.get('terrain_version') != getattr(self.world, '_atlas_ground', {}).get('version')):
                packet = dict(type='world_atlas_position', version=1, scope='explored', center=center)
        elif not force and same_world and not nearby and not old.get('nearby') and old['visible'] < visible:
            from engine.world_atlas import render
            added = visible - old['visible']
            packet = render(compiled, center, added)
            packet['type'] = 'world_atlas_update'
            placed = old['placed'] + sum(r['coordinates']['world'] is not None for r in packet['rooms'] if r['id'] in added)
            floors = old['floors'] | {r['z'] for r in packet['rooms']}
            packet['floors'] = sorted(floors)
            packet['counts'] = dict(visible=len(visible), placed=placed)
        else:
            packet = self.atlas_for(pid)
            placed = packet['counts']['placed']
            floors = set(packet['floors'])
        try:
            if packet is not None:
                if 'terrain_rows' not in packet:
                    packet.update(world_atlas.terrain_map(self.world,compiled,old.get('terrain_version',-1) if same_world else -1))
                if 'rooms' in packet and 'pixel_assets' not in packet and getattr(self.world,'game_dir',None):
                    from engine.pixel_art import decorate_rooms
                    packet['pixel_assets']=decorate_rooms(self.world.game_dir,packet['rooms'])
                if dark:
                    from engine.world_atlas import conceal_routes
                    conceal_routes(packet)
                await websocket.send(json.dumps(packet))
            if websocket not in self.atlas_subscribers or self.clients.get(websocket) != pid:
                return
            self.last_atlases[websocket] = dict(compiled=compiled, pid=pid,
                location=location, discovery=discovery, visible=visible, nearby=set(nearby), blind=dark,
                placed=placed, floors=floors, terrain_version=(packet or old).get('terrain_version',-1))
        except websockets.exceptions.ConnectionClosed:
            self.close_atlas(websocket)

    async def update_atlases(self):
        # Closed atlas has no projection/serialization cost. Open views only
        # rebuild on discovery, movement, character or compiled-world changes.
        for websocket in list(getattr(self, 'atlas_subscribers', ())):
            await self.send_atlas(websocket)

    async def update_maps(self):
        for ws,pid in list(self.clients.items()):
            if pid not in self.world.entities: continue
            packet = json.dumps(dict(type='map', **self.map_for(pid)))
            if self.last_maps.get(ws) != packet:
                try:
                    await ws.send(packet)
                    self.last_maps[ws] = packet
                except websockets.exceptions.ConnectionClosed:
                    pass

        await self.update_atlases()

    async def broadcast_room(self, room_id, text, exclude=None, exclude_player=None):
        for ws, pid in list(self.clients.items()):
            ent = self.world.entities.get(pid)
            if ws is not exclude and pid != exclude_player and ent is not None and ent.location == room_id:
                try:
                    await ws.send(json.dumps({"type": "system", "text": text}))
                except websockets.exceptions.ConnectionClosed:
                    pass

    async def flush_notifications(self):
        injuries=getattr(self.world,'damage_notifications',[])
        self.world.damage_notifications=[]
        for injury in injuries:
            for socket,owner in list(self.clients.items()):
                if owner==injury['player_id']:
                    try:await socket.send(json.dumps(injury))
                    except (websockets.exceptions.ConnectionClosed,ConnectionError):pass
        # Rest progress is personal; never broadcast it to room bystanders.
        messages=getattr(self.world,'rest_notifications',[])
        self.world.rest_notifications=[]
        for pid,text in messages:
            for socket,owner in list(self.clients.items()):
                if owner==pid:
                    try:await socket.send(json.dumps({'type':'system','text':text}))
                    except Exception:pass
        notifications=getattr(self.world,'runtime_notifications',[])
        self.world.runtime_notifications=[]
        for entry in notifications:
            rid,text=entry[:2]
            await self.broadcast_room(rid,text,exclude_player=entry[2] if len(entry)>2 else None)

    def advance_rest_tick(self):
        """One bounded single-player step; lifecycle yields between calls.

        Never accelerate a hosted world or an offline character. The existing
        world loop remains the only writer; no simulation thread is introduced.
        """
        if self.mode == 'host' or self.closing:return False
        from engine import resting
        actors=[self.world.entities.get(pid) for pid in set(self.clients.values())]
        rows=[]
        for p in actors:
            row=resting.active(p) if p else None
            if not row:continue
            if not resting._valid(row) or getattr(p,'_rest_token',None)!=row.get('token'):
                resting.cancel(self.world,p,'a saved session cannot resume automatically');continue
            rows.append(row)
        if not rows:return False
        step=min(5,min(max(1,row.get('duration',1)-row.get('elapsed',0)) for row in rows))
        living.advance(self.world,step)
        try:self._save_dirty_players()
        except Exception:
            for p in actors:
                if p:resting.cancel(self.world,p,'progress could not be saved; rest stopped, try Save before continuing')
        return True

    async def advance_guides(self):
        from engine import escorts
        for socket,pid in list(self.clients.items()):
            p=self.world.entities.get(pid)
            if not p or not p.alive or not p.progress.get('escort_party'):continue
            n,q=escorts.pair(self.world,p)
            run=p.progress['escort_party']
            if not n or q['escort']['mode']!='follow' or run.get('paused'):continue
            direction=escorts.next_direction(self.world,p,n,q)
            origin=p.location
            text=dispatch(self.registry,self.world,p,'go '+direction,resolve_shortcuts=False) if direction else 'The guide cannot reach the destination.'
            if p.location==origin:
                run['paused']=True;text+=' Choose Follow again to resume.'
            self.mark_explored(pid)
            try:await socket.send(json.dumps({'type':'response','text':text}))
            except websockets.exceptions.ConnectionClosed:pass

    async def update_watch_views(self):
        from engine import resident_watch
        for ws,(pid,ident,last,packet) in list(self.watch_views.items()):
            actor=self.world.entities.get(ident)
            player=self.world.entities.get(pid)
            if self.clients.get(ws)!=pid or not player or player.progress.get('resident_watch')!=ident:
                self.watch_views.pop(ws,None)
                continue
            place=actor.location if actor and actor.alive else None
            if place==last:continue
            reply=resident_watch.view(self.world,player,{**packet,'action':'view'})
            self.watch_views[ws]=(pid,ident,place,packet)
            try:await ws.send(json.dumps({**reply,'request_id':packet.get('request_id')}))
            except websockets.exceptions.ConnectionClosed:self.watch_views.pop(ws,None)

    async def lifecycle_loop(self):
        ticks = 0
        while True:
            await asyncio.sleep(0.25)
            if self.closing:continue
            for socket,token in list(getattr(self,'account_connections',{}).items()):
                if not self.accounts.authenticate(token):
                    await socket.close(code=1008,reason='Session expired. Sign in again.')
                    self.account_connections.pop(socket,None)
            ticks += 1
            if ticks%5==0:await self.advance_guides()
            accelerated=self.advance_rest_tick()
            if ticks % 20 == 0 and self.clients and not accelerated:
                self.world.tick_authorized=True
                try:living.advance(self.world,1)
                finally:self.world.tick_authorized=False
            if ticks % 20 == 0:
                self._autosave_host_tick()
            await self.flush_notifications()
            if getattr(self,'watch_views',None):await self.update_watch_views()
            await self.update_maps()
            for room_id, message in advance_spawners(self.world) + frontiers.population(self.world) + frontiers.fight(self.world):
                await self.broadcast_room(room_id, message)

    # ─── connection handler ─────────────────────────────────────────
    async def handle(self, websocket):
        player_id = None
        equipment_sequence = 0
        lock_sequence = 0
        account_token=''
        local_host=False
        accounts=getattr(self,'accounts',None)
        # Browser websocket requests must originate from this application's
        # HTTP listener. Non-browser LAN clients still require character tokens.
        if not accounts:
            headers=getattr(getattr(websocket,'request',None),'headers',{})
            origin=headers.get('Origin')
            if origin:
                from urllib.parse import urlparse
                parsed=urlparse(origin)
                host=headers.get('Host','').rsplit(':',1)[0].strip('[]')
                try:valid_origin=parsed.scheme=='http' and parsed.hostname==host and parsed.port in (getattr(self,'http_port',8000),getattr(self,'lan_http_port',getattr(self,'http_port',8000)))
                except ValueError:valid_origin=False
                remote=getattr(websocket,'remote_address',None)
                local=getattr(websocket,'local_address',None)
                import ipaddress
                try:
                    known_host=(parsed.hostname in ('localhost','127.0.0.1','::1') and remote and ipaddress.ip_address(remote[0]).is_loopback) or (local and parsed.hostname==local[0])
                except ValueError:known_host=False
                if not valid_origin or not known_host:
                    await websocket.close(code=1008,reason='Open the game through its own application address.');return
        if accounts:
            from server.accounts import token_from_cookie
            headers=websocket.request.headers
            from urllib.parse import urlparse
            import ipaddress,secrets
            origin=urlparse(headers.get('Origin',''))
            remote=getattr(websocket,'remote_address',None)
            if remote and ipaddress.ip_address(remote[0]).is_loopback and origin.scheme=='http' and origin.hostname in ('127.0.0.1','localhost','::1'):
                try:
                    first=json.loads(await asyncio.wait_for(websocket.recv(),timeout=5))
                    token=first.get('control_token','')
                    local_host=first.get('command')=='host_auth' and isinstance(token,str) and bool(self.host_token) and secrets.compare_digest(token,self.host_token)
                except Exception:local_host=False
                if local_host:self.host_sockets.add(websocket)
            if not local_host and headers.get('Origin')!=accounts.url:
                await websocket.close(code=1008,reason='Connect through the public HTTPS address.');return
            account_token=token_from_cookie(headers.get('Cookie'))
            if not local_host and not accounts.authenticate(account_token):
                await websocket.close(code=1008,reason='Sign in through Accounts first.');return
        if accounts and not local_host:
            if not hasattr(self,'account_connections'):self.account_connections={}
            self.account_connections[websocket]=account_token
            import os,ipaddress
            peer=websocket.remote_address[0]
            if peer==os.environ.get('EXPANSE_TRUSTED_PROXY',''):
                try:peer=str(ipaddress.ip_address(headers.get('X-Real-IP','')))
                except ValueError:
                    self.account_connections.pop(websocket,None)
                    await websocket.close(code=1008,reason='Invalid proxy metadata.');return
            with accounts.lock:
                accounts.event('game_connect',accounts.authenticate(account_token),{'ip':peer,'client':headers.get('User-Agent','')})
                accounts.db.commit()
        from server import dm_console
        if accounts and not local_host and dm_console.blocked(self,account=accounts.authenticate(account_token)):
            getattr(self,'account_connections',{}).pop(websocket,None)
            await websocket.close(code=1008,reason='This account is blocked from this world.');return
        if local_host:await websocket.send(json.dumps({'type':'host_ready','text':'Host controls ready.'}))
        await websocket.send(json.dumps({"type":"welcome", "text":"Create a character or load a saved character before playing."}))

        try:
            async for raw in websocket:
                account_id=accounts.authenticate(account_token) if accounts else None
                if accounts and not local_host and not account_id:
                    await websocket.close(code=1008,reason='Session expired. Sign in again.');break
                if websocket in dm_console.ensure(self)['kicked'] or (websocket not in self.host_sockets and dm_console.blocked(self,pid=player_id,account=account_id)):
                    await websocket.close(code=1008,reason='Blocked from this world by the Dungeon Master.');break
                if self.closing:
                    await websocket.send(json.dumps({"type":"system","text":"Expanse is saving and shutting down."}))
                    break
                packet = None
                try:
                    packet = json.loads(raw)
                    cmd = packet.get("command", "") if isinstance(packet, dict) else None
                    if not isinstance(cmd, str) or len(cmd) > 4096:
                        raise ValueError("command must be text, at most 4096 characters")
                    cmd = cmd.strip()
                    if not cmd:
                        await websocket.send(json.dumps({"type":"response","text":"Type a command or choose an action."}));continue
                    if cmd == "resume" and isinstance(packet.get("player_id"), str):
                        cmd = "resume " + packet["player_id"]
                except (ValueError, TypeError):
                    error={"type": "error", "text": "Invalid command message."}
                    rejected_id=packet.get('movement_id') if isinstance(packet,dict) else None
                    if isinstance(rejected_id,str) and 0 < len(rejected_id) <= 64:
                        error['movement_id']=rejected_id
                    await websocket.send(json.dumps(error))
                    continue

                if cmd == 'world asset':
                    from engine.world_package import asset_packet
                    asset=asset_packet(self.world.game_dir,packet.get('name'),packet.get('offset',0))
                    await websocket.send(json.dumps({**asset,'request_id':packet.get('request_id')}))
                    continue

                if cmd == 'public chart':
                    from engine import political_map
                    if player_id or websocket in self.host_sockets:
                        chart=political_map.publication(self.world,packet.get('revision'),packet.get('surface') is True)
                        if packet.get('weather') is True:chart.update(political_map.weather_chart(self.world,packet.get('weather_minute')))
                        await websocket.send(json.dumps({**chart,'world':Path(self.world.game_dir).name,'request_id':packet.get('request_id')}))
                    continue

                if cmd == 'travel map window':
                    if player_id:
                        from engine.travel_window import window
                        player=self.world.entities[player_id]
                        reply=dict(type='travel_window',request_id=packet.get('request_id'),center=player.location)
                        if packet.get('center')==player.location:
                            try:
                                extent = packet.get('extent')
                                reply['tiles']=window(self.world,player,self._atlas_compiled(),extent)
                                if packet.get('follow_view') is True:
                                    player._travel_view_extent = extent
                                from engine.pixel_art import apply
                                apply(self.world, reply)
                            except ValueError as exc:reply['error']=str(exc)
                        await websocket.send(json.dumps(reply))
                    continue

                if cmd == 'walk to tile':
                    from engine import travel
                    try:
                        if not player_id:raise ValueError('Enter the world before walking.')
                        player=self.world.entities[player_id]
                        if 'extent' in packet:
                            from engine.travel_window import window
                            if packet.get('center')!=player.location or not isinstance(packet.get('destination'),str):
                                raise ValueError('Your location changed. Choose the tile again.')
                            compiled=self._atlas_compiled()
                            try:
                                path=window(self.world,player,compiled,packet['extent'],packet['destination'])
                            except ValueError:
                                from engine import local_visibility
                                if packet['destination'] not in local_visibility.sight(self.world,player,compiled)['rooms']:
                                    raise
                                path=travel.plan(self.world,player,packet['destination'],compiled)
                        else:
                            path=travel.plan(self.world,player,packet.get('destination'),self._atlas_compiled())
                        result={'steps':path}
                    except ValueError as exc:result={'error':str(exc)}
                    await websocket.send(json.dumps({'type':'walk_plan','request_id':packet.get('request_id'),**result}))
                    continue

                if cmd == 'resident watch':
                    from engine import resident_watch
                    self.watch_views.pop(websocket,None)
                    if packet.get('action')=='close':continue
                    try:
                        if not player_id:raise ValueError('Enter the world before observing a resident.')
                        result=resident_watch.view(self.world,self.world.entities[player_id],packet)
                        if packet.get('follow_camera') is True and result.get('scene'):
                            self.watch_views[websocket]=(player_id,result['resident'],result['scene']['center'],packet)
                    except ValueError as exc:result={'type':'resident_watch','error':str(exc)}
                    result['request_id']=packet.get('request_id')
                    await websocket.send(json.dumps(result))
                    continue

                if cmd == 'save slots':
                    from server import save_slots
                    await save_slots.handle(self,websocket,player_id,packet)
                    continue

                # Graphical duration choices are canonical actions, not creator shortcuts.
                lock_ui=packet.get('lock_ui') is True
                if 'lock_ui' in packet:
                    from server import locks_ui
                    try:
                        if not lock_ui or cmd!='locks action':raise ValueError('Invalid lock action envelope.')
                        sequence=packet.get('sequence')
                        if type(sequence) is not int or not 1<=sequence<=9007199254740991 or sequence<=lock_sequence:raise ValueError('This lock action was already handled. Refresh local actions.')
                        lock_sequence=sequence
                        cmd=locks_ui.resolve(self.world,self.world.entities.get(player_id),packet)
                    except ValueError as exc:
                        await websocket.send(json.dumps({'type':'error','text':str(exc)}))
                        continue
                rest_ui=packet.get('rest_ui') is True
                if 'rest_ui' in packet:
                    words=cmd.split()
                    valid=cmd=='wake self' or (len(words)==2 and words[0] in ('rest','sleep') and words[1].isdigit() and 60<=int(words[1])<=1500 and int(words[1])%60==0)
                    if not rest_ui or not valid:
                        await websocket.send(json.dumps({'type':'error','text':'Choose 1 to 25 whole game hours, or Wake / stop resting.'}))
                        continue

                # Structured equipment listing is read-only, including while
                # resting. Actions resolve against this socket's actor, then use
                # the same lifecycle as ordinary equip/unequip commands.
                equipment_request = None
                if cmd.split()[0].lower() == 'equipment':
                    from server import equipment_ui
                    try:
                        equipment_request=equipment_ui.request_id(packet)
                        actor=self.world.entities.get(player_id)
                        if cmd.lower()=='equipment list':
                            await websocket.send(json.dumps(equipment_ui.build(self.world,actor,equipment_request)))
                            continue
                        if cmd.lower()!='equipment action':
                            raise ValueError('Use equipment list or select an equipment action.')
                        sequence=packet.get('sequence')
                        if type(sequence) is not int or not 1<=sequence<=9007199254740991 or sequence<=equipment_sequence:
                            raise ValueError('This equipment action was already handled or is out of order. Refresh equipment.')
                        equipment_sequence=sequence
                        cmd=equipment_ui.resolve(self.world,actor,packet)
                    except ValueError as exc:
                        await websocket.send(json.dumps({'type':'error','text':str(exc),'request_id':equipment_request,'equipment_action':True}))
                        continue

                from engine import resting
                from engine.directions import ALIASES
                verb = cmd.split(None, 1)[0].lower()
                movement_id = packet.get('movement_id')
                if not (isinstance(movement_id, str) and 0 < len(movement_id) <= 64
                        and (verb == 'go' or cmd.lower() in ALIASES or cmd.lower() in ALIASES.values()
                             or cmd.lower() in ('in', 'out'))):
                    movement_id = None
                if cmd=='local quests':
                    from engine import community_quests
                    try:
                        actor=self.world.entities.get(player_id)
                        reply=community_quests.handle(self.world,actor,packet)
                        if packet.get('action') not in ('quote','catalog','list'):
                            self.world.dirty_players=getattr(self.world,'dirty_players',set())|{p.id for p in self.world.entities.values() if p.is_player}
                            self._save_dirty_players()
                    except ValueError as exc:reply={'error':str(exc)}
                    await websocket.send(json.dumps(dict(type='local_quests',request_id=packet.get('request_id'),**reply)))
                    continue
                resting.before_command(self.world,self.world.entities.get(player_id),cmd,self.registry,resolve_shortcuts=not(equipment_request or rest_ui or lock_ui))
                if await dm_console.handle(self,websocket,packet,cmd):continue
                from engine import sleep_movement
                blocked=sleep_movement.blocked_command(self.world,self.world.entities.get(player_id),cmd,self.registry,resolve_shortcuts=not(equipment_request or rest_ui or lock_ui))
                if blocked:
                    reply={'type':'response','text':blocked,**({'request_id':equipment_request,'equipment_action':True} if equipment_request else {})}
                    if movement_id:reply['movement_id']=movement_id
                    await websocket.send(json.dumps(reply))
                    if equipment_request:await websocket.send(json.dumps(equipment_ui.build(self.world,self.world.entities[player_id],equipment_request)))
                    continue
                if player_id is not None:dm_console.record_activity(self,player_id,cmd)
                from server import calendar_ui
                if await calendar_ui.handle(self,websocket,player_id,packet,cmd):continue
                from server import trade_ui
                if resting.canonical(self.world,cmd,self.registry,resolve_shortcuts=not(equipment_request or rest_ui or lock_ui))[0] in ('rest','sleep'):
                    trade_ui.disconnect(self,websocket)
                if await trade_ui.handle(self,websocket,player_id,cmd):
                    try:self._save_dirty_players()
                    except Exception as exc:
                        await websocket.send(json.dumps({'type':'error','text':'Could not save new knowledge: '+str(exc)}))
                    continue
                if await self.society_command(websocket,packet,cmd,player_id):continue
                # Handlers above can yield. Recheck at the final admission point.
                if self.closing:
                    await websocket.send(json.dumps({"type":"system","text":"Expanse is saving and shutting down."}))
                    break
                if cmd.startswith("resume "):
                    new_pid = cmd.split(None, 1)[1].strip()
                    if accounts and not local_host and not accounts.owns(account_id,new_pid):
                        await websocket.send(json.dumps({'type':'error','text':'That character does not belong to your account.'}));continue
                    if self.mode=='host' and not accounts and websocket not in self.host_sockets and not self.valid_token(new_pid,packet.get('auth_token','')):
                        await websocket.send(json.dumps({'type':'error','text':'Character ownership token required. Load this character from its original browser or ask the host for recovery.'}));continue
                    if websocket not in self.host_sockets and dm_console.blocked(self,pid=new_pid,account=account_id):
                        await websocket.send(json.dumps({'type':'error','text':'This character is blocked from this world.'}));continue
                    resume_notice = ""
                    if len(self.clients)>=self.world.metadata.get('max_players',128) and websocket not in self.clients:
                        await websocket.send(json.dumps({'type':'error','text':'This world has reached its player limit.'}));continue
                    if new_pid in self.creator_roles and websocket not in self.host_sockets and not self.valid_token(new_pid,packet.get('auth_token','')):
                        await websocket.send(json.dumps({'type':'error','text':'Creator identity token required.'}));continue
                    if any(ws is not websocket and pid == new_pid for ws, pid in self.clients.items()):
                        await websocket.send(json.dumps({"type": "error", "text": "That character is already connected."}))
                        continue
                    target = self.world.entities.get(new_pid)

                    if target is None:
                        target = load_player(self.db, new_pid, self.mode)
                        if target and target.progress.get("world_slug", "default") != Path(self.world.game_dir).name:
                            target = None
                        if target:
                            from engine.country_edges import saved_room
                            target.location=saved_room(self.world,target.location)
                            if target.location not in self.world.rooms:
                                resume_notice = " Your saved room no longer exists; you were moved to your faction starting settlement."
                                target.location = frontiers.home(self.world,target)
                            self.world.entities[target.id] = target
                            self.world.rooms[target.location].entities.append(
                                target.id)

                    if target is not None and target.progress.get("world_slug", "default") != Path(self.world.game_dir).name:
                        await websocket.send(json.dumps({"type":"error", "text":"This character belongs to another world. Select that world before resuming."}))
                        continue
                    if target is None or not target.is_player:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "text": "Cannot resume: that character no "
                                    "longer exists.",
                        }))
                        continue

                    self.world.bind_entity(target)
                    from engine import combat
                    combat.starter_ammunition(self.world,target)
                    from engine.shield_compat import restore_equipped
                    restore_equipped(self.world,target)
                    rest_notice=resting.resume(self.world,target)
                    from engine import resource_nodes
                    resource_nodes.clear_manual_turns(self.world,target.id)
                    if rest_notice:resume_notice+=' '+rest_notice
                    old_pid = player_id
                    old = self.world.entities.get(old_pid)
                    if old and old is not target:
                        resting.cancel(self.world,old,'you switched characters',notify=False)
                        from engine import resource_nodes
                        resource_nodes.clear_manual_turns(self.world,old.id)
                        self._stage_players_and_world()
                        old_room = self.world.rooms.get(old.location)
                        if old_room and old_pid in old_room.entities:
                            old_room.entities.remove(old_pid)
                        self.world.entities.pop(old_pid, None)

                    self.close_atlas(websocket)
                    trade_ui.disconnect(self,websocket)
                    player_id = new_pid
                    self.clients[websocket] = player_id
                    if websocket in self.host_sockets:self.local_save_player=player_id
                    dm_console.record_activity(self,player_id,'resume')
                    room = self.world.rooms[target.location]
                    from engine.quest_discovery import attention
                    target._source_quest_choices=[]
                    greeting=attention(self.world,target)
                    from engine.quest_discovery import take_choices
                    greeting_choices=take_choices(self.world,target)
                    if greeting:resume_notice+="\n"+greeting

                    await websocket.send(json.dumps({
                        "type": "system",
                        "source_quests":greeting_choices,
                        "event":"character_entered", "player_id":target.id,
                        "text": f"Resumed as {target.name} in {room.name}." + resume_notice + (" This character has died permanently." if target.progress.get("permanently_dead") else " You are unconscious. Use revive to return to your starting settlement." if not target.alive else ""),
                    }))
                    continue

                if player_id is None:
                    await websocket.send(json.dumps({"type":"character_required", "text":"Create a character or load a save before entering the world."}))
                    continue
                if cmd.split()[0].lower() == 'ui':
                    from server import player_ui
                    request_id=packet.get('request_id')
                    if not isinstance(request_id,(str,int)) or isinstance(request_id,bool):request_id=None
                    elif request_id is not None:request_id=str(request_id)[:100]
                    try:
                        reply=player_ui.handle(self.world,self.world.entities[player_id],cmd.partition(' ')[2],request_id, director=websocket in self.host_sockets)
                    except ValueError as exc:
                        reply={'type':'error','text':str(exc),'request_id':request_id}
                    await websocket.send(json.dumps(reply))
                    if reply.get('type')=='character_appearance':
                        if reply.get('applied'):await self.update_maps()
                        continue
                    try:self._save_dirty_players()
                    except Exception as exc:
                        await websocket.send(json.dumps({'type':'error','text':'Could not save new knowledge: '+str(exc)}))
                    continue
                if cmd.split()[0].lower() == 'atlas':
                    action = cmd.lower()
                    if action == 'atlas close':
                        self.close_atlas(websocket)
                    elif action in ('atlas open', 'atlas refresh'):
                        if not hasattr(self, 'atlas_subscribers'):
                            self.atlas_subscribers = set()
                        self.atlas_subscribers.add(websocket)
                        await self.send_atlas(websocket, force=True)
                    else:
                        await websocket.send(json.dumps({'type':'error', 'text':'Use atlas open, atlas refresh or atlas close. Complete maps are host-only.'}))
                    continue
                if cmd.lower() in ('save', 'save_exit'):
                    ent = self.world.entities[player_id]
                    try:
                        if websocket in self.host_sockets:self.local_save_player=player_id
                        self._save_players_and_world(player_id)
                    except Exception as exc:
                        await websocket.send(json.dumps({"type":"error","text":"Save failed: "+str(exc)}))
                        continue
                    exiting = cmd.lower() != 'save'
                    await websocket.send(json.dumps({"type":"saved_exit" if exiting else "saved", "text":"Character and world saved.", "player_id":player_id}))
                    if exiting:
                        break
                    continue
                if cmd.lower() == 'map':
                    await websocket.send(json.dumps(dict(type='map', **self.map_for(player_id))))
                    continue
                if equipment_request:
                    # Earlier lifecycle hooks may await. Recheck ownership,
                    # slot and replacement immediately before synchronous dispatch.
                    try:cmd=equipment_ui.resolve(self.world,self.world.entities.get(player_id),packet)
                    except ValueError as exc:
                        await websocket.send(json.dumps({'type':'error','text':str(exc),'request_id':equipment_request,'equipment_action':True}))
                        continue
                if lock_ui:
                    try:cmd=locks_ui.resolve(self.world,self.world.entities.get(player_id),packet)
                    except ValueError as exc:
                        await websocket.send(json.dumps({'type':'error','text':str(exc)}))
                        await websocket.send(json.dumps(dict(type='map', **self.map_for(player_id))))
                        continue
                if 'walk_edge' in packet:
                    edge=packet['walk_edge'];walker=self.world.entities[player_id]
                    if (not movement_id or not isinstance(edge,list) or len(edge)!=3 or not all(isinstance(x,str) for x in edge)
                            or cmd!='go '+edge[1] or walker.location!=edge[0] or self.world.rooms[walker.location].exits.get(edge[1])!=edge[2]):
                        await websocket.send(json.dumps({'type':'error','text':'Your route changed. Choose the tile again.','movement_id':movement_id}))
                        continue
                    walk_hp=walker.hp
                # Record discovery without constructing and discarding a full map.
                self.mark_explored(player_id)
                self.world.entities[player_id]._source_quest_choices = []
                mover=self.world.entities[player_id]
                origin,initial_hp=mover.location,mover.hp
                mover._walking_exact_edge='walk_edge' in packet
                try:
                    response = dispatch(
                        self.registry, self.world,
                        self.world.entities.get(player_id), cmd,
                        **({"resolve_shortcuts":False} if equipment_request or rest_ui or lock_ui else {}),
                    )
                finally:
                    del mover._walking_exact_edge
                from engine.quest_discovery import take_choices
                source_choices = take_choices(self.world,self.world.entities[player_id])
                # A tagged UI step gets its authoritative map immediately,
                # before its acknowledgement permits the next input. No world
                # mutation is moved to a thread or skipped for responsiveness.
                if movement_id:
                    self.mark_explored(player_id)
                    map_packet=json.dumps(dict(type='map', **self.map_for(player_id)))
                    await websocket.send(map_packet)
                    self.last_maps[websocket]=map_packet
                    await websocket.send(json.dumps({'type':'response','text':response,'source_quests':source_choices,'movement_id':movement_id,'step_taken':mover.location!=origin and mover.alive and mover.hp>=initial_hp,**({'walk_arrived':walker.location==edge[2] and walker.alive and walker.hp>=walk_hp} if 'walk_edge' in packet else {})}))
                else:
                    await websocket.send(json.dumps({'type':'response','text':response,'source_quests':source_choices,**({'request_id':equipment_request,'equipment_action':True} if equipment_request else {})}))

                self.mark_explored(player_id)
                if websocket in getattr(self, 'atlas_subscribers', ()):
                    await self.send_atlas(websocket)
                ent = self.world.entities.get(player_id)
                readonly={'look','map','inventory','score','status','help','standing','workshop','provenance','survey','recipes','catalog','wardrobe','materials','quests','adventures','market','journal','condition','time','inspect','spells','companions','services','route','guide'}
                if self.mode!='host' and not society.enabled(self.world) and cmd.split()[0].lower() not in readonly:
                    self._stage_players_and_world()
                else:self._save_dirty_players()
                if lock_ui:
                    map_packet=json.dumps(dict(type='map', **self.map_for(player_id)))
                    await websocket.send(map_packet)
                    self.last_maps[websocket]=map_packet
                if equipment_request:
                    # Refresh after authoritative dispatch/persistence, never
                    # pretend a requested item is worn before the engine acts.
                    map_packet=json.dumps(dict(type='map', **self.map_for(player_id)))
                    await websocket.send(map_packet)
                    self.last_maps[websocket]=map_packet
                    await websocket.send(json.dumps(equipment_ui.build(self.world,self.world.entities[player_id],equipment_request)))

        except websockets.exceptions.ConnectionClosedError as exc:
            # Expected moderation closes are not server faults. Preserve all
            # other abnormal-close diagnostics and normal finally cleanup.
            if not any(frame is not None and frame.code==1008 for frame in (exc.sent,exc.rcvd)):
                raise
        finally:
            # Remove atlas references even when a pre-existing save error below
            # prevents ordinary connection cleanup.
            from server import calendar_ui
            calendar_ui.disconnect(self,websocket)
            from server import trade_ui
            trade_ui.disconnect(self,websocket)
            self.close_atlas(websocket, discard_lock=True)
            self.watch_views.pop(websocket,None)
            dm_console.forget_socket(self,websocket)
            ent=self.world.entities.get(player_id)
            if ent is not None:
                from engine import resting
                resting.cancel(self.world,ent,'you disconnected; offline time does not count',notify=False)
                from engine import resource_nodes
                resource_nodes.clear_manual_turns(self.world,ent.id)
            save_failed=False
            if ent is not None and not self.discarding and websocket not in getattr(self,'no_save_sockets',set()):
                try:self._stage_players_and_world()
                except Exception as exc:
                    save_failed=True
                    print('Disconnect save failed; unsaved character retained in memory:',exc)
            getattr(self,'account_connections',{}).pop(websocket,None)
            self.host_sockets.discard(websocket)
            self.clients.pop(websocket,None);self.last_maps.pop(websocket,None)
            self.creator_roles.discard(player_id)
            for oid,offer in list(self.offers.items()):
                if player_id in (offer['sender'],offer['recipient']):self.offers.pop(oid,None)
            if player_id not in self.clients.values():
                self.map_markers.pop(player_id,None)
                getattr(self,'map_positions',{}).pop(player_id,None)
                if not save_failed and ent and ent.location in self.world.rooms:
                    if player_id in self.world.rooms[ent.location].entities:self.world.rooms[ent.location].entities.remove(player_id)
                    self.world.entities.pop(player_id,None)

    # ─── reload ─────────────────────────────────────────────────────
    async def reload_world(self):
        from server.adventures import storage_dir
        target_storage=storage_dir(engine_loader.DATA_DIR,SAVE_DIR,engine_loader.GAMES_DIR)
        if target_storage != getattr(self,"adventure_storage",None):
            raise RuntimeError("Return to Start and use Continue adventure to switch save namespaces.")
        # 1. Validate content BEFORE swapping. Uses the editor's own
        #    validator so behavior matches the "Validate" button.
        from editor.cli import Editor
        try:
            ed = Editor(engine_loader.DATA_DIR)
            report = ed.validate()
        except Exception as e:
            raise RuntimeError(f"content has errors: validation failed: {e}")
        if not report.startswith("OK"):
            raise RuntimeError(f"content has errors: {report}")

        if Path(self.world.game_dir).resolve() != Path(engine_loader.DATA_DIR).resolve():
            if self.clients:
                raise RuntimeError("Disconnect players before switching to another world.")
            self._stage_players_and_world()
            self.world = build_world()
            from engine import streets
            streets.install(self.world)
            self.world.realtime = (self.mode == 'host')
            self.world.deferred_rest = True
            spawn_npcs(self.world)
            self._init_shop_state()
            self._load_world_state()
            from engine import population
            population.ensure(self.world)
            frontiers.population(self.world)
            for owner in list(living.state(self.world)['camps']):
                if not self.db.execute('SELECT 1 FROM players WHERE id=?',(owner,)).fetchone():living.state(self.world)['camps'].pop(owner,None)
            self.last_maps.clear()
            self.capture_checkpoint()
            return

        # 2. Snapshot player + world state from OLD world
        players = {pid: ent for pid, ent in self.world.entities.items()
                   if ent.is_player}
        killed = set(self.world.killed_npcs)
        old_claims = {rid: dict(cnts)
                      for rid, cnts in self.world.item_claims.items()}
        counter = dict(getattr(self.world, "spawner_counter", {}))
        living_saved = living.snapshot(self.world)
        living_saved.pop("floors", None)  # Editor room changes remain authoritative on reload.
        shop = {def_id: dict(state)
                for def_id, state in self.world.shop_state.items()}

        # 3. Build the new world
        new_world = build_world()
        from engine import streets
        streets.install(new_world)
        new_world.realtime = (self.mode == 'host')
        new_world.deferred_rest = True
        new_world.killed_npcs = killed
        new_world.spawner_counter = counter

        # 4. Filter item claims: preserve only where disk content
        #    matches expectation. If disk has more items than we
        #    originally had (editor added fresh ones), reset that
        #    claim so the new items are visible.
        filtered_claims = {}
        for room_id, room_claims in old_claims.items():
            new_room = new_world.rooms.get(room_id)
            old_room = self.world.rooms.get(room_id)
            if not new_room or not old_room:
                continue
            kept = {}
            for item_id, claim_count in room_claims.items():
                current = sum(1 for i in old_room.items if i == item_id)
                new_count = sum(1 for i in new_room.items if i == item_id)
                # Two valid readings of "what the disk originally held":
                #   A: claims already removed from room.items → original = current + claims
                #   B: claims reserved but items still present → original = current
                # Preserve the claim if the new disk matches either reading.
                if new_count in (current, current + claim_count):
                    kept[item_id] = claim_count
                # else: disk changed in a way neither reading accounts for —
                # drop the claim so new/removed content is visible
            if kept:
                filtered_claims[room_id] = kept
        new_world.item_claims = filtered_claims

        # 5. Merge shop state (preserve quantities where NPC still exists)
        for def_id, state in shop.items():
            if def_id not in new_world.shop_state:
                continue
            for item_id, qty in state.items():
                if item_id in new_world.shop_state[def_id]:
                    new_world.shop_state[def_id][item_id] = qty

        if not new_world.rooms:
            raise RuntimeError("content has zero rooms; aborting reload")

        # 6. Apply filtered claims to the new rooms
        for room_id, room_claims in filtered_claims.items():
            room = new_world.rooms.get(room_id)
            if room is None:
                continue
            used = dict(room_claims)
            kept = []
            for item_id in room.items:
                if used.get(item_id, 0) > 0:
                    used[item_id] -= 1
                else:
                    kept.append(item_id)
            room.items = kept

        # 7. Spawn fresh NPCs (skips killed_npcs), swap the world
        spawn_npcs(new_world)
        living.restore(new_world, living_saved)
        self.world = new_world
        start_room = start_room_for(self.world)

        # 8. Restore players
        for pid, ent in players.items():
            from engine import resting
            resting.cancel(self.world,ent,'the world was reloaded')
            from engine import resource_nodes
            resource_nodes.clear_manual_turns(self.world,ent.id)
            dest = ent.location if ent.location in self.world.rooms \
                   else start_room
            ent.location = dest
            self.world.bind_entity(ent)
            self.world.entities[pid] = ent
            self.world.rooms[dest].entities.append(pid)

        # 9. Notify connected clients
        for ws, pid in list(self.clients.items()):
            try:
                ent = self.world.entities.get(pid)
                if ent is None:
                    continue
                room = self.world.rooms[ent.location]
                await ws.send(json.dumps({
                    "type": "system",
                    "text": f"The world was reloaded by the editor. "
                            f"You are in {room.name}.",
                }))
            except Exception:
                pass

        # Reload may move players or interrupt rest. Commit them with the world.
        self._stage_players_and_world()


async def main():
    server = GameServer(mode="host")
    async with websockets.serve(server.handle, "localhost", 8765):
        print("Server running on ws://localhost:8765")
        await server.lifecycle_loop()


if __name__ == "__main__":
    asyncio.run(main())
