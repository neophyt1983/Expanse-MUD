"""Explicit artist plans use only local conversations and remembered supplies."""
from engine import artworks, guild_npc, guilds, knowledge

KEY = 'art_work_v1'


def step(world, actor):
    if actor.is_player:return False
    plan = world.npcs.get(actor.source_def, {}).get('art_plan', {})
    if not isinstance(plan, dict) or plan.get('enabled') is not True or guilds._actor_reason(world, actor):return False
    from engine import npc_attention
    if npc_attention.paused(world, actor):return False
    saved = actor.progress.setdefault(KEY, {})
    now = guilds.minute(world)
    if now <= saved.get('last_minute', -1):return False
    saved['last_minute'] = now
    guild_npc._observe(world, actor)
    job = artworks.active(world, actor)
    if job:
        if job.get('paused'):
            actor.activity = 'artistic work paused: ' + job['paused'];return False
        if actor.location != job['room']:
            return guild_npc._move(world, actor, job['room'])
        if not artworks._finish_reason(world, actor):
            saved['note'] = artworks.finish(world, actor)
        else:actor.activity = 'working on ' + job['title']
        return True
    # Only an actual co-located eligible patron discloses an order. Previously
    # observed people are remembered at their last seen place, never live-found.
    known = saved.setdefault('offers', {})
    for patron in world.entities_in_room(actor.location):
        if patron.source_def not in plan.get('patrons', []) or artworks._patron(world, actor, patron.id)[1]:continue
        for offer in world.npcs.get(patron.source_def, {}).get('art_commissions', []):
            if not offer.get('enabled', True) or offer['recipe'] not in plan.get('recipes', []):continue
            key = patron.source_def + ':' + offer['id']
            if key not in known:
                guild_npc.converse(world, actor, patron.id)
                known[key] = dict(patron=patron.source_def, id=offer['id'], recipe=offer['recipe'], room=actor.location)
                actor.activity = 'discussing a real artistic commission';return True
    for key, remembered in known.items():
        state = artworks._state(world).get('commissions', {}).get(key, {})
        if state.get('status') == 'complete':continue
        if state.get('status') == 'accepted' and state.get('actor') != actor.id:continue
        patron = next((person for person in world.entities_in_room(actor.location)
                       if person.source_def == remembered['patron'] and not artworks._patron(world, actor, person.id)[1]), None)
        if state.get('status') != 'accepted':
            if remembered['recipe'] not in artworks._known_recipes(world, actor):
                if guild_npc._source(world, actor):return True
                continue
            if patron:
                offer = artworks._offer(world, patron, remembered['id'])
                if offer and not artworks._commission_reason(world, actor, patron, offer, 'accept'):
                    saved['note'] = artworks.act(world, actor, patron.id, offer['id'], 'accept');return True
            continue
        recipe = artworks._recipe(world, remembered['recipe'])
        if recipe is None:continue
        if patron:
            offer = artworks._offer(world, patron, remembered['id'])
            if offer:
                for ident in actor.inventory:
                    if not artworks._commission_reason(world, actor, patron, offer, 'deliver', ident):
                        token = patron.id + ':' + ident
                        if token in artworks._state(world).get('judgments', {}):continue
                        saved['note'] = artworks.act(world, actor, patron.id, offer['id'], 'deliver', work_id=ident)
                        return True
        work = [ident for ident in actor.inventory if world.items.get(ident, {}).get('artwork', {}).get('recipe') == recipe['id']]
        if work:
            if actor.location != remembered['room'] and guild_npc._move(world, actor, remembered['room']):return True
            # A rejected piece never loops into infinite replacement production.
            actor.activity = 'awaiting patron or a new artistic decision';return True
        for item, count in recipe['ingredients'].items():
            if actor.inventory.count(item) < count:
                if guild_npc._supply(world, actor, item):return True
                if guild_npc._source(world, actor):return True
                if plan.get('explore') is True and guild_npc._explore(world, actor):return True
                actor.activity = 'awaiting known artistic material supplies';return True
        building = recipe['artwork'].get('building')
        if building:
            known_rooms = set(actor.progress.get('knowledge', {}).get('rooms', [])) | set(actor.explored_rooms)
            for room in world.buildings.get(building, {}).get('rooms', []):
                if room in actor.explored_rooms:continue
                if room in known_rooms and guild_npc._move(world, actor, room):return True
                if guild_npc._source(world, actor):return True
                if plan.get('explore') is True and guild_npc._explore(world, actor):return True
                actor.activity = 'awaiting actual access to the building to be surveyed';return True
        station = recipe.get('station', 'hand')
        if station != 'hand' and station not in world.room_details.get(actor.location, {}).get('facilities', []):
            for room in actor.explored_rooms:
                if station in world.room_details.get(room, {}).get('facilities', []) and guild_npc._move(world, actor, room):return True
            actor.activity = 'awaiting a known artistic work station';return True
        if not artworks._begin_reason(world, actor, recipe):
            saved['note'] = artworks.begin(world, actor, recipe['id']);return True
    return guild_npc._source(world, actor)
