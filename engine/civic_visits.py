"""Resolve a doorstep visit from a single opening register, on the world host."""
import json
import re
import time
from pathlib import Path

from engine.core import Entity

COURT = re.compile(r'gen_(?:dawn|hollow|hearth|reed|cinder|glass|pine|star)_lane_[1-9][0-9]{0,2}')


def residents(world, court):
    if not COURT.fullmatch(str(court)) or court not in world.rooms:
        return ()
    path = Path(world.game_dir) / 'assets' / 'chronicles' / (court + '.json')
    if not path.is_file() or path.stat().st_size > 100000:
        return ()
    rows = json.loads(path.read_bytes())
    return [row for row in rows if row.get('home') == court]


def definition(world, row):
    return dict(id=row['id'], name=row['name'], home_room=row['home'],
                workplace_room=row['work'], group=world.rooms[row['home']].group,
                occupation=row['occupation'], hp=22, attack=2, defense=1, gold=0,
                spawn_managed=True, social_profile={'sentient': True},
                description=f"{row['name']} lives at door {row['door']} and works as a {row['occupation']}.")


PARKED = 'civic_households_at_home_v1'
VISITS = 'civic_visits_v1'
PERSON = re.compile(r'gen_(?:dawn|hollow|hearth|reed|cinder|glass|pine|star)_person_[0-9]+')
# Any new or Creator-defined activity/progress keeps the actor in full simulation.
IDLE_PROGRESS = {'npc_life', 'needs', 'needs_budget_assigned', 'supply_search', 'town_talk', 'awakened_until'}
IDLE_ACTIONS = {None, '', 'sleeping', 'resting', 'resting at home', 'relaxing at home', 'awake'}
PERSONAL = {'gold','inventory','equipped','progress'}
IDENTITY = {'id','source_def','location','is_player'}


def new_actor(world, row):
    source = definition(world, row)
    return Entity(id='npc:'+row['id'], name=row['name'], hp=22, max_hp=22, attack=2, defense=1,
                  source_def=row['id'], group_id=source['group'], description=source['description'],
                  location=row['home'])


def wake(world, row):
    """Return the exact resident to their doorstep; an existing tombstone wins."""
    uid, court = row['id'], row['home']
    room = getattr(world, 'living_state', {}).get(PARKED, {}).get(court, {})
    if uid in world.killed_npcs:
        room.pop(uid, None)
        return None
    if uid not in room:
        return world.entities.get('npc:'+uid)
    actor = world.entities.get('npc:'+uid)
    if actor is None:
        saved = room[uid]
        actor = new_actor(world, row)
        for name, value in saved['changes'].items():
            if name not in Entity.__dataclass_fields__ or name in IDENTITY:
                raise ValueError('Invalid household resident field: '+name)
            setattr(actor, name, value)
        if saved.get('activity') is not None:
            actor.activity = saved['activity']
        world.npcs.setdefault(uid, definition(world, row))
        world.add_entity(actor, court)
        from engine import npc_life, sleep_movement
        npc_life.step(world, actor)
        sleep_movement.scheduled_wake(world, actor)
    del room[uid]
    if not room:
        del world.living_state[PARKED][court]
    world._civic_active_courts.add(court)
    return actor


def enter_court(world, court):
    room = getattr(world, 'living_state', {}).get(PARKED, {}).get(court)
    if room:
        for row in residents(world, court):
            if row['id'] in room:
                wake(world, row)


def home_address(world, actor_id):
    if not isinstance(actor_id,str) or not actor_id.startswith('npc:gen_'):
        return None
    uid = actor_id[4:]
    if uid in world.killed_npcs:
        return None
    for court, members in getattr(world, 'living_state', {}).get(PARKED, {}).items():
        if uid in members:
            return court
    return None


def _referenced(world):
    """Include live cross-actor references, including Creator extension records."""
    state = world.living_state
    # Contacts are historical identities; an authorized observer can reopen
    # a dormant contact. An active watch explicitly pins its subject.
    records = {k:v for k,v in state.items() if k not in (PARKED, VISITS, 'resident_watches', 'relationships')}
    social = state.get('relationships', {})
    records['relationships'] = {k:v for k,v in social.items() if k not in ('bonds','events')}
    # Formal relationships and outstanding proposals remain live. Trust scores,
    # cooldowns and past conversations stay in the existing relationship ledger.
    records['formal_bonds'] = [bond for bond in social.get('bonds', {}).values() if bond.get('kinds')]
    refs = {ident[4:] for ident, entry in state.get('resident_watches', {}).items()
            if ident.startswith('npc:') and entry.get('observers')}
    # Only snapshot serializable state. Never traverse callbacks, socket maps or
    # room lists (a resident's own location membership isn't a dependency).
    # Encoding the nested state once avoids rescanning per doorstep resident.
    if records:
        refs.update(PERSON.findall(json.dumps(records, default=str)))
    progress = []
    history_keys = {'chronicle_contacts','observed_residents','npc_life','needs','talked_to','quest_talks','town_talk'}
    for person in world.entities.values():
        live = {k:v for k,v in person.progress.items() if k not in history_keys}
        errands = person.progress.get('town_talk', {}).get('errands', {})
        if errands:
            live['errands'] = errands
        progress.append(live)
    refs.update(PERSON.findall(json.dumps(progress, default=str)))
    return refs


def _nearby(world, occupied):
    radius = world.metadata.get('local_sight_tiles', 6)
    radius = max(1, min(16, radius)) if type(radius) is int else 6
    nearby, frontier = set(occupied), set(occupied)
    for _ in range(radius):
        frontier = {dest for rid in frontier for dest in world.rooms[rid].exits.values()
                    if dest in world.rooms and dest not in nearby}
        if not frontier:
            break
        nearby.update(frontier)
    return nearby


def _idle(world, actor, row):
    if (actor.location != row['home'] or not actor.alive or actor.hp != actor.max_hp or
            actor.spawner_key or not IDLE_PROGRESS.issuperset(actor.progress) or
            actor.progress.get('supply_search', {}).get('target') or
            actor.progress.get('town_talk', {}).get('errands') or
            actor.progress.get('awakened_until', 0) > world.living_state['minute'] or
            getattr(actor, 'activity', None) not in IDLE_ACTIONS or
            world.npcs.get(row['id']) != definition(world, row)):
        return False
    original = new_actor(world, row)
    if any(getattr(actor, field) != getattr(original, field)
           for field in Entity.__dataclass_fields__ if field not in PERSONAL):
        return False
    # An unrecognized runtime extension may need this identity to remain live.
    presentation = {'_visible_action','_fight_display','_public_expression','_town_words'}
    if set(vars(actor)) - Entity.__dataclass_fields__.keys() - {'_world_ref','activity'} - presentation:
        return False
    now = time.monotonic()
    for key in ('_visible_action', '_fight_display'):
        transient = getattr(actor, key, None)
        if transient and transient[1] > now:
            return False
    from engine import npc_attention, speech_bubbles
    exchange = getattr(actor, '_public_expression', None)
    if exchange and now < exchange[0] + speech_bubbles.TURN_SECONDS * (2 if exchange[5] else 1):
        return False
    return not npc_attention.paused(world, actor)


def retire_distant(world, visiting=None):
    """Move idle visitors behind their own doors when all observers are far away."""
    courts = getattr(world, '_civic_active_courts', None)
    state = getattr(world, 'living_state', {})
    if not courts and not state.get(PARKED):
        return
    occupied = {actor.location for actor in world.entities.values()
                if actor.is_player and actor.location in world.rooms}
    if visiting in world.rooms:
        occupied.add(visiting)
    # Retry engaged or traveling actors occasionally even when no player moves.
    stamp = (frozenset(occupied), state['minute']//15)
    if stamp == getattr(world, '_civic_last_sweep', None):
        return
    world._civic_last_sweep = stamp
    for occupied_room in occupied:
        enter_court(world, occupied_room)
    remote = world._civic_active_courts - _nearby(world, occupied)
    if not remote:
        return
    refs = _referenced(world)
    from engine.entity_snapshot import snapshot
    for court in remote:
        still_live = False
        members = set(state[VISITS].get(court, ()))
        for row in residents(world, court):
            uid = row['id']
            if uid not in members:
                continue
            actor = world.entities.get('npc:'+uid)
            if actor is None:
                continue
            if uid in refs or not _idle(world, actor, row):
                still_live = True
                continue
            # Retain every changed dataclass field and the human-readable activity.
            # Fresh mutable containers belong to the saved entry, not the live actor.
            original = new_actor(world, row)
            changes = {name:value for name,value in snapshot(actor).items()
                       if value != getattr(original, name)}
            state.setdefault(PARKED, {}).setdefault(court, {})[uid] = {
                'changes': changes, 'activity': getattr(actor, 'activity', None)}
            world.rooms[court].entities.remove(actor.id)
            del world.entities[actor.id]
        if not still_live:
            courts.discard(court)


def restore_definitions(world, ledger):
    world._civic_active_courts = set(ledger)
    world._civic_last_sweep = None
    for court, ids in ledger.items():
        members = set(ids)
        sleeping = world.living_state.get(PARKED, {}).get(court, {})
        if not sleeping.keys() <= members:
            raise ValueError('A dormant resident is missing from the household roll.')
        from engine import npc_life
        for record in sleeping.values():
            changes = record['changes']
            if not isinstance(changes, dict) or not changes.keys() <= PERSONAL:
                raise ValueError('Invalid saved household resident.')
            npc_life.validate_saved(changes.get('progress', {}))
        for row in residents(world, court):
            if row['id'] in members:
                world.npcs.setdefault(row['id'], definition(world, row))


def knock(ctx, args):
    world = ctx.world
    court = ctx.player.location
    rows = residents(world, court)
    if not rows:
        return 'There is no household roll at this address.'
    parts = args.split(maxsplit=1)
    if not parts or not parts[0].isascii() or not parts[0].isdigit() or len(parts[0])>2:
        return 'Use knock <door number> [resident name]. Read the Court Roll for names.'
    household = [r for r in rows if r['door'] == int(parts[0])]
    if len(parts)==2:
        household = [r for r in household if r['name'].casefold()==parts[1].casefold()]
    if not household:
        return 'No one by that description is listed at this door.'
    from engine import living
    ledger = living.state(world).setdefault(VISITS,{}).setdefault(court,[])
    if not hasattr(world, '_civic_active_courts'):
        world._civic_active_courts = set()
    if getattr(world, '_civic_last_knock', None) != court:
        retire_distant(world, court)
        world._civic_last_knock = court
    for row in household:
        uid = row['id']
        actor = wake(world, row)
        if actor is None and uid not in world.killed_npcs and uid not in ledger and uid not in world.npcs:
            d = definition(world,row)
            actor = new_actor(world, row)
            world.npcs[uid]=d
            world.add_entity(actor,court)
            ledger.append(uid)
            world._civic_active_courts.add(court)
        if actor and actor.alive and actor.location==court:
            return f"{actor.name} answers the door. You can speak to {actor.name} here."
    return 'There is no answer at this door.'
