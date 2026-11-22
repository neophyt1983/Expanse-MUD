"""Quest provenance is an actual conversation or reading, never a map lookup."""
def sourced(player):
    records=player.progress.get('quest_sources',{})
    return {qid for qid,rows in records.items() if isinstance(rows,list) and any(isinstance(r,dict) and r.get('kind') in ('npc','item') and isinstance(r.get('id'),str) for r in rows)} if isinstance(records,dict) else set()


def disclose(world,player,table,kind,source):
    from engine import knowledge,living
    if kind not in ('npc','item') or not isinstance(table,dict):return []
    catalog=world.npcs if kind=='npc' else world.items
    if source not in catalog:return []
    rows=[]
    for qid in table.get('quests',[]):
        q=world.quests.get(qid)
        if not q or q.get('relationship_quest',{}).get('enabled') or living.quest_blocked(world,player,q):continue
        entry={'kind':kind,'id':source};saved=player.progress.setdefault('quest_sources',{}).setdefault(qid,[])
        if entry not in saved:saved.append(entry)
        rows.append(qid)
    places=list(table.get('rooms',[]))
    places.extend(world.quests[qid]['offer_room'] for qid in rows if world.quests[qid].get('offer_room') in world.rooms)
    knowledge.teach(world,player,{**table,'quests':rows,'rooms':places})
    if rows:
        if not hasattr(world,'dirty_players'):world.dirty_players=set()
        world.dirty_players.add(player.id)
    return rows


def offer_text(world,player,quest_ids):
    from engine import knowledge,living
    available={q['id']:q for q in knowledge.local_offers(world,player)}
    choices=[qid for qid in quest_ids if qid in available]
    player._source_quest_choices=choices
    from engine import interface_tours
    text=''.join('\nRequest: '+available[qid]['name']+'. '+available[qid].get('description','')+
                 ('\nOpen quest offers below, then choose Accept quest & start guide. Text command: accept ' if interface_tours.definition(available[qid]) else '\nTo accept: accept ')+available[qid]['name'] for qid in choices)
    recorded=sourced(player);accepted=knowledge.accepted(world,player)
    for qid in quest_ids:
        q=world.quests.get(qid,{})
        if qid not in recorded or qid in accepted or qid in available or living.quest_blocked(world,player,q):continue
        rid=q.get('offer_room')
        if rid in world.rooms and rid!=player.location:
            text+='\nRequest mentioned: '+q['name']+'. Use Route to reach '+world.rooms[rid].name+' and accept this request there.'
    return text


def attention(world,player):
    """A present, awake authored greeter speaks once, not a global quest popup."""
    from engine import livelihoods,knowledge
    from engine.commands import _is_hostile_npc
    if not player.alive:return ''
    accepted=knowledge.accepted(world,player)
    greeted=player.progress.get('quest_greetings',[])
    for npc in world.entities_in_room(player.location):
        definition=world.npcs.get(npc.source_def,{})
        text=definition.get('quest_greeting')
        # Existing unrelated adventures must not hide a newly installed introduction.
        if any(qid in accepted for qid in definition.get('knowledge',{}).get('quests',[])):continue
        key=definition.get('quest_greeting_key',npc.source_def)
        if not npc.alive or not text or key in greeted or not livelihoods.awake(world,npc) or _is_hostile_npc(world,npc,player):continue
        if not isinstance(text,str):continue
        from engine import earned_start
        if earned_start.marked(player) and npc.source_def in earned_start.WELCOME:
            text=earned_start.INTRO
        if definition.get('work_hours') and not livelihoods.on_shift(world,npc):continue
        ids=disclose(world,player,definition.get('knowledge',{}),'npc',npc.source_def)
        if not ids:continue
        player.progress.setdefault('quest_greetings',[]).append(key)
        for qid in ids:
            quest=world.quests[qid]
            target=quest.get('turn_in_room')
            if quest.get('category')=='first steps' and target in world.rooms and target!=player.location:
                knowledge.teach(world,player,{'rooms':[target]})
                from engine import interface_tours
                text+=(' After the interface guide, your practice stop is ' if interface_tours.definition(quest) else ' Your first stop is ')+world.rooms[target].name+'. I have marked it on your globe.'
                break
        return npc.name+' calls to you: '+text+offer_text(world,player,ids)
    return ''


def restore_public_reading(world):
    """Fixed authored displays are not loose floor loot in an older save.

Only definitions still explicitly placed by the Creator are restored; ordinary
items, other saved floor stacks, removed displays and NPC deaths are untouched.
"""
    for iid,item in world.items.items():
        original=item.get('location')
        if not item.get('consolidated_at') or original not in world.rooms:continue
        if iid not in getattr(world,'room_details',{}).get(original,{}).get('items',[]) and iid in world.rooms[original].items:
            world.rooms[original].items.remove(iid)
    for rid,room in world.rooms.items():
        for iid in getattr(world,'room_details',{}).get(rid,{}).get('items',[]):
            if world.items.get(iid,{}).get('anchored_readable') is True and iid not in room.items:
                room.items.append(iid)


def take_choices(world,player):
    """Consume only the current person's/item's response; never browse prior sources."""
    ids=getattr(player,'_source_quest_choices',[])
    player._source_quest_choices=[]
    if not ids:return []
    from engine import knowledge
    available={q['id']:q for q in knowledge.local_offers(world,player)}
    from engine import interface_tours,quest_alternatives
    return [dict(id=qid,name=available[qid]['name'],description=available[qid].get('description',''),interface_guide=bool(interface_tours.definition(available[qid])),**quest_alternatives.affordance(world,player,available[qid])) for qid in ids if qid in available]
