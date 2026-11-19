"""Character-owned knowledge. Knowing a place never means having visited it.

No global reveal flag: Creator uses its own authorized catalog endpoints. Actor
progress is saved by the existing character serializer. Optional authored
`knowledge` tables on NPCs/items/quests are explicit disclosures, not omniscience.
"""
KINDS = {'items': 'items', 'rooms': 'rooms', 'recipes': 'recipes', 'quests': 'quests'}


def state(player):
    k = player.progress.setdefault('knowledge', {'version': 1})
    for key in KINDS:
        if not isinstance(k.get(key), list): k[key] = []
    return k


def teach(world, player, table):
    if not isinstance(table, dict): return
    k = state(player)
    before = tuple(len(k[key]) for key in KINDS)
    for key, attr in KINDS.items():
        values = table.get(key, [])
        if not isinstance(values, (list, tuple, set)): continue
        existing = set(k[key]); valid = getattr(world, attr, {})
        k[key].extend(v for v in dict.fromkeys(x for x in values if isinstance(x, str))
                      if v in valid and v not in existing)
    # Learning an actual recipe includes the ingredient/output names it specifies.
    items = set(k['items'])
    for rid in table.get('recipes', []) if isinstance(table.get('recipes', []), list) else []:
        recipe = getattr(world, 'recipes', {}).get(rid, {})
        for iid in (*recipe.get('ingredients', {}), *recipe.get('outputs', {})):
            if iid in world.items and iid not in items: k['items'].append(iid); items.add(iid)
    if player.is_player and before != tuple(len(k[key]) for key in KINDS):
        if not hasattr(world, 'dirty_players'): world.dirty_players = set()
        world.dirty_players.add(player.id)


def accepted(world, player):
    from engine import quest_chains
    quest_chains.migrate(world, player)
    return {qid for qid, status in player.progress.get('quests', {}).items()
            if status in ('active', 'complete', 'replaced') and qid in world.quests}


def quest(world, player, q):
    """Accepted objectives disclose their stated places/items, not unseen routes."""
    rooms = [q.get('offer_room'), q.get('turn_in_room'), *q.get('visit_rooms', [])]
    items = [*q.get('required_items', {}), *q.get('reward_items', [])]
    recipes = []
    for action in q.get('actions', {}):
        kind, _, ident = action.partition(':')
        if kind == 'read': items.append(ident)
        if kind in ('craft', 'cook'): recipes.append(ident)
    items += [row.get('read_item') for row in q.get('witnesses', [])]
    teach(world, player, dict(rooms=rooms, items=items, recipes=recipes))
    teach(world, player, q.get('knowledge', {}))


def sync(world, player, observe=False):
    """Aggregate disclosures once; preserve exact per-category enrollment order.

Completed history can be thousands of quests. Rebuilding the entire learned
sets for each quest made map refresh quadratic. This request-local accumulator
keeps creator edits live and performs one final teach, without a stale cache.
"""
    pending={key:{} for key in KINDS}
    def collect(table):
        if not isinstance(table,dict):return
        for key in KINDS:
            values=table.get(key,[])
            if isinstance(values,(list,tuple,set)):
                pending[key].update((value,None) for value in values if isinstance(value,str))
        # Preserve the old teach order: explicit item names precede the recipe's
        # ingredient/output names within each actual disclosure.
        recipes=table.get('recipes',[])
        if isinstance(recipes,list):
            for rid in recipes:
                if not isinstance(rid,str):continue
                recipe=getattr(world,'recipes',{}).get(rid,{})
                pending['items'].update((iid,None) for iid in (*recipe.get('ingredients',{}),*recipe.get('outputs',{})))
    collect({'items':[*player.inventory,*player.equipped.values()],
             'rooms':[*player.explored_rooms,player.location]})
    for qid in accepted(world,player):
        q=world.quests[qid]
        rooms=[q.get('offer_room'),q.get('turn_in_room'),*q.get('visit_rooms',[])]
        items=[*q.get('required_items',{}),*q.get('reward_items',[])];recipes=[]
        for action in q.get('actions',{}):
            kind,_,ident=action.partition(':')
            if kind=='read':items.append(ident)
            if kind in ('craft','cook'):recipes.append(ident)
        items += [row.get('read_item') for row in q.get('witnesses',[])]
        collect(dict(rooms=rooms,items=items,recipes=recipes))
        collect(q.get('knowledge',{}))
    actions=player.progress.get('actions',{})
    collect({'recipes':[key.split(':',1)[1] for key,value in actions.items()
                        if value and key.startswith(('craft:','cook:'))]})
    if observe and player.location in world.rooms:
        room=world.rooms[player.location];collect({'items':room.items})
        details=getattr(world,'room_details',{}).get(room.id,{})
        for rid in details.get('resources',[]):
            resource=getattr(world,'resources',{}).get(rid,{})
            collect({'items':[*resource.get('yields',{}),resource.get('tool')]})
    teach(world,player,{key:list(values) for key,values in pending.items()})
    return state(player)


def known_ids(world, actor, kind):
    """Pure learned/authored view for eligibility and projections."""
    valid = getattr(world, KINDS[kind], {})
    if actor is None: return set(valid)
    known = {value for value in actor.progress.get('knowledge', {}).get(kind, []) if isinstance(value, str)}
    definition = {} if actor.is_player else world.npcs.get(actor.source_def, {})
    authored = definition.get('knowledge', {})
    known.update(value for value in authored.get(kind, []) if isinstance(value, str))
    if kind == 'rooms':
        known.update([actor.location, *actor.explored_rooms, definition.get('home_room'),
                      definition.get('work_room'), definition.get('workplace_room')])
    elif kind == 'items':
        known.update([*actor.inventory, *actor.equipped.values()])
        known.update(row.get('item') for row in definition.get('stock', []))
        for recipe_id in authored.get('recipes', []):
            recipe = getattr(world, 'recipes', {}).get(recipe_id, {})
            known.update([*recipe.get('ingredients', {}), *recipe.get('outputs', {})])
    return {value for value in known if value in valid}


def ids(world, player, kind):
    if player is None or not player.is_player:
        return known_ids(world, player, kind)
    valid=getattr(world,KINDS[kind],{})
    return {key for key in sync(world,player)[kind] if key in valid}


def local_offers(world, player):
    """Eligible offers already disclosed by an actual NPC or item."""
    from engine.quest_discovery import sourced
    disclosed=sourced(player)
    from engine.living import quest_blocked
    from engine import guilds
    already_accepted=accepted(world,player)
    return [q for q in world.quests.values()
            if q['id'] in disclosed and not q.get('relationship_quest', {}).get('enabled')
            and (not q.get('offer_room') or q.get('offer_room') == player.location)
            and (q['id'] not in already_accepted or guilds.available_again(world,player,q) and player.progress.get('quests',{}).get(q['id'])=='complete' or
                 (q.get('repeatable') and player.progress['quests'].get(q['id'])=='complete'
                  and getattr(world,'living_state',{}).get('minute',0)-player.progress.get('quest_times',{}).get(q['id'],-100000)>=q.get('cooldown_minutes',1500)))
            and not quest_blocked(world, player, q)]


def learn_local_recipes(world, player):
    """Visiting a design's authored workshop can expose its recipe, not all designs."""
    rows = getattr(world, 'recipes', {})
    known_items = ids(world, player, 'items')
    # An authored local workshop is a discoverable source of its own designs.
    # Do not consult another room's workshop or its live stock/occupants.
    room = getattr(world, 'room_details', {}).get(player.location, {})
    workshop = room.get('workshop', {})
    designs = workshop.get('recipes', []) if isinstance(workshop, dict) else []
    local_designs = {rid for rid in designs if isinstance(rid, str)} if isinstance(designs, list) else set()
    learned = [rid for rid, r in rows.items() if
               rid in local_designs or
               (r.get('knowledge_scope') != 'private' and r.get('location') and r['location'] == player.location) or
               (r.get('knowledge_scope') == 'public'
                and set(r.get('outputs', {})) and set(r.get('outputs', {})) <= known_items
                and set(r.get('ingredients', {})) <= known_items)]
    teach(world, player, {'recipes': learned})


def npc_topics(world, npc):
    # Knowing a name does not add a route. Posted local exits are read only by
    # actual direction/conversation actions in town_talk, not this projection.
    return ids(world, npc, 'rooms')


def from_npc(world, player, npc):
    definition = world.npcs.get(npc.source_def, {})
    from engine.quest_discovery import disclose
    disclose(world, player, definition.get('knowledge', {}), 'npc', npc.source_def)
    teach(world, player, {'items': [s.get('item') for s in definition.get('stock', [])]})
    from engine import knowledge_sources
    minute = int(getattr(world, 'living_state', {}).get('minute', 0))
    knowledge_sources.record(world, player, definition.get('knowledge', {}),
        source={'kind': 'npc', 'id': npc.source_def}, certainty='sourced',
        event_id='conversation:' + npc.id + ':' + str(minute))


def read_source(world, actor, item_id):
    """An actual full read; called after its action counter, never by a journal."""
    from engine import publications, knowledge_sources, task_skills
    identity = publications.source(world, item_id)
    previous = actor.progress.get(publications.MEMORY, {}).get((identity or {}).get('edition_id'), {})
    source = publications.record_read(world, actor, item_id)
    from engine import worldtime
    minute = int(getattr(world, 'living_state', {}).get('minute', worldtime.initial_minute(world.metadata)))
    if minute <= previous.get('read_minute', -10**15): return source
    item = world.items[item_id]
    table = item.get('knowledge', {})
    if not isinstance(table, dict): table = {}
    table = {**table, 'items': [item_id, *(table.get('items', []) if isinstance(table.get('items'), list) else [])]}
    teach(world, actor, table)
    event = 'read:' + source['edition_id'] + ':' + str(minute)
    knowledge_sources.record(world, actor, table,
                             source=source, certainty='sourced', event_id=event)
    text = item.get('read_text', '')
    task_skills.practice(world, actor, 'reading', effort=max(.25, min(3, len(text.split()) / 150)),
                         event_id=event)
    return source


def observe_room(world, actor, *, event_id=None):
    """Remember an executed look/arrival, never a passive map refresh."""
    from engine import knowledge_sources, local_visibility, worldtime
    if (actor.location not in world.rooms or not actor.alive
            or world.entities.get(actor.id) is not actor or local_visibility.blind(world, actor)):
        return False
    room = world.rooms[actor.location]
    people = [person for person in world.entities_in_room(actor.location)
              if person.alive and not person.is_player and person.id != actor.id]
    definitions = [world.npcs.get(person.source_def, {}) for person in people]
    table = {'rooms': [room.id], 'items': list(room.items), 'npcs': [person.source_def for person in people],
             'species': [definition.get('species') or definition.get('social_profile', {}).get('species') for definition in definitions]}
    teach(world, actor, table)
    minute = int(getattr(world, 'living_state', {}).get('minute', worldtime.initial_minute(world.metadata)))
    return knowledge_sources.record(world, actor, table,
        source={'kind': 'observation', 'id': actor.id + ':' + room.id}, certainty='observed',
        event_id=event_id or 'look:' + room.id + ':' + str(minute))


def validate(data):
    from engine.quest_next_stop import validate as validate_next_stop
    issues=validate_next_stop(data)
    for kind in ('npc','item','quest','resource'):
        for row in data.get(kind, []):
            if 'knowledge' not in row: continue
            table=row['knowledge']; where=row['id']+': knowledge'
            if not isinstance(table, dict): issues.append(where+' must be an object'); continue
            for field, values in table.items():
                target={'items':'item','rooms':'room','recipes':'recipe','quests':'quest'}.get(field)
                if not target: issues.append(where+' has unknown field '+field); continue
                valid={r['id'] for r in data.get(target, [])}
                if not isinstance(values,list) or any(not isinstance(v,str) or v not in valid for v in values):
                    issues.append(where+'.'+field+' must contain existing '+target+' IDs')
    readable = {row['id'] for row in data.get('item', []) if row.get('read_text')}
    for recipe in data.get('recipe', []):
        if recipe.get('knowledge_scope', 'local') not in ('public', 'local', 'private'):
            issues.append(recipe['id']+': knowledge_scope must be public, local or private')
        required = recipe.get('requires_reading', [])
        if (not isinstance(required, list) or len(required) > 8
                or any(not isinstance(ident, str) or ident not in readable for ident in required)):
            issues.append(recipe['id']+': requires_reading must contain at most eight real readable items')
    return issues


def recipe_source_ready(actor, recipe):
    """Copying a work requires an actually read source, including old journals."""
    required = recipe.get('requires_reading', [])
    if not required: return True
    from engine import publications
    known = set(actor.progress.get('reading_journal_v1', []))
    known.update(record.get('source', {}).get('id') for record in actor.progress.get(publications.MEMORY, {}).values())
    known.update(key[5:] for key, count in actor.progress.get('actions', {}).items() if count and key.startswith('read:'))
    known.update(row.get('id') for row in actor.progress.get('npc_background_v1', {}).get('sources', [])
                 if row.get('kind') == 'item')
    return set(required) <= known


def crafting_choice(world, player, query):
    """Unknown design can be learned by doing, never enumerated by fuzzy guessing.

An exact named attempt with real ingredients and an actual usable station is
an interaction. Unavailable unknown designs return no metadata or hints.
"""
    from engine import item_catalog, living, quest_progress
    learn_local_recipes(world, player)
    rows=getattr(world,'recipes',{})
    known=[rows[rid] for rid in ids(world,player,'recipes')]
    if item_catalog.matches(known,query):
        selected = item_catalog.choose(known,query)
        if not recipe_source_ready(player, selected):raise ValueError('Read the source text before copying this work.')
        return selected
    exact=[r for rid,r in rows.items() if rid==query or r.get('name','').casefold()==query.strip().casefold()]
    if len(exact)!=1:raise ValueError('That recipe has not been learned or is not available here.')
    r=exact[0];station=r.get('station','hand')
    if not recipe_source_ready(player, r):raise ValueError('Read the source text before copying this work.')
    facilities=getattr(world,'room_details',{}).get(player.location,{}).get('facilities',[])
    camp=getattr(world,'living_state',{}).get('camps',{}).get(player.id,{})
    usable=station=='hand' or station in facilities or (station=='kitchen' and camp.get('room')==player.location and camp.get('fire'))
    from collections import Counter
    count=Counter(player.inventory)
    if (not usable or any(count[i]<n for i,n in r.get('ingredients',{}).items())
        or any(quest_progress.status(world,player,qid)!='complete' for qid in r.get('prerequisites',[]))):
        raise ValueError('That recipe has not been learned or is not available here.')
    return r


def from_text(world, player, text, source=None):
    """Disclosure in actually read author prose, not inference from hidden records.

Only exact whole names (unique within a catalog) or explicit IDs are matched.
Ambiguous short place nicknames never invent geographic anchors.
"""
    import re
    disclosed={key:[] for key in KINDS};replacements={}
    lower=text.casefold()
    for kind,attr in KINDS.items():
        records=getattr(world,attr,{})
        # Keep duplicate-name checks local to this text. Unmentioned names
        # cannot match, and do not need lists or a second complete catalog
        # walk. There is no cache: live Creator edits remain visible.
        names={};candidates=[]
        for ident,obj in records.items():
            name=obj.name if kind=='rooms' else obj.get('name','')
            folded=name.casefold() if name else ''
            mentioned=bool(folded and folded in lower)
            if mentioned:names[folded]=names.get(folded,0)+1
            explicit_id=('_' in ident or ':' in ident or ('`'+ident+'`') in text)
            id_candidate=explicit_id and ident.casefold() in lower
            name_candidate=mentioned and len(name)>=4
            if id_candidate or name_candidate:
                candidates.append((ident,name,folded,id_candidate,name_candidate))
        for ident,name,folded,id_candidate,name_candidate in candidates:
            id_match=id_candidate and re.search(r'(?<![\w])'+re.escape(ident)+r'(?![\w])',text)
            name_match=name_candidate and names[folded]==1 and re.search(r'(?<![\w])'+re.escape(name)+r'(?![\w])',text,re.I)
            if id_match or name_match:disclosed[kind].append(ident)
            if id_match and name:replacements[ident]=name
    if source:
        from engine.quest_discovery import disclose
        # Exact mentions establish a name, not proof of a remote location or a
        # complete design. Explicit authored grants and quest leads retain
        # their existing semantics; casual names are qualified separately.
        kind, source_id = source
        definition = (world.items if kind == 'item' else world.npcs).get(source_id, {})
        explicit = definition.get('knowledge', {})
        certain = {**disclosed, 'rooms': [value for value in disclosed['rooms']
                                         if value in explicit.get('rooms', [])],
                   'recipes': [value for value in disclosed['recipes']
                               if value in explicit.get('recipes', [])]}
        disclose(world,player,certain,*source)
        from engine import knowledge_sources
        reference = {'kind': kind, 'id': source_id}
        if kind == 'item':
            from engine import publications
            reference = publications.source(world, source_id) or reference
        fiction = definition.get('publication', {}).get('kind') == 'fiction'
        qualities = {claim.get('certainty', 'sourced') for claim in reference.get('claims', [])}
        certainty = ('opinion' if fiction else next(iter(qualities))
                     if len(qualities) == 1 and qualities <= {'rumor', 'opinion', 'uncertain'} else 'uncertain')
        minute = int(getattr(world, 'living_state', {}).get('minute', 0))
        knowledge_sources.record(world, player, disclosed, source=reference,
            certainty=certainty,
            event_id='mention:' + kind + ':' + source_id + ':' + str(minute))
    else:
        teach(world,player,{**disclosed,'quests':[]})
    for ident,name in sorted(replacements.items(),key=lambda row:-len(row[0])):
        text=re.sub(r'(?<![\w])'+re.escape(ident)+r'(?![\w])',lambda match:name,text)
    return text


def action_label(world, key):
    kind, _, ident=key.partition(':')
    catalog={'read':world.items,'craft':getattr(world,'recipes',{}),'cook':getattr(world,'recipes',{}),'gather':getattr(world,'resources',{})}.get(kind,{})
    return kind.replace('_',' ').title()+(' '+catalog.get(ident,{}).get('name','the required task') if ident else '')
