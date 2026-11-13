"""World-authored companion facilities. Active animals remain ordinary world entities."""
from collections import deque
from dataclasses import asdict
from uuid import uuid4

from engine import companions, living, mortality, quest_progress
from engine.core import Entity


def rules(w):
    return getattr(w, 'rules', {}).get('companion_union', {})


def inside(w,p):
    hall=rules(w).get('hall')
    if p.location==hall:return True
    return any(hall in b.get('rooms',[]) and p.location in b['rooms'] for b in w.buildings.values())


def eligible(w, p):
    cfg = rules(w)
    return bool(cfg and p.char_class == cfg['profession'])


def roster(p):
    return living.progress(p)['companions']


def completed(p, qid):
    return p.progress.get('quests', {}).get(qid) == 'complete'


def active(w, p):
    return [c for c in roster(p) if (e := w.entities.get(c['id'])) and e.alive
            and e.progress.get('companion_owner') == p.id and e.progress.get('companion_order') != 'dismissed']


def check_space(w, p, *, new=False):
    if not eligible(w, p):
        return
    cfg = rules(w)
    if new and len(roster(p)) >= cfg['capacity']:
        raise ValueError('Your roster is full, including companions in stable care.')
    slots = 2 if completed(p, cfg['brace']) else 1
    if len(active(w, p)) >= slots:
        raise ValueError('Stable or dismiss an active companion first.' + (' Complete Brace Handling for a second active place.' if slots == 1 else ''))


def preserve_death(w, e):
    if not rules(w) or not e.progress.get('companion_owner'):
        return False
    owner=w.entities.get(e.progress['companion_owner'])
    if owner and not eligible(w,owner):return False
    companions.reserve(w)[e.id] = asdict(e)
    return True


def spec(w, source):
    return w.npcs.get(source, {}).get('handling') or {}


def lesson(w,source):
    configured=spec(w,source)
    if configured:
        return configured
    cfg=rules(w)
    species=w.npcs.get(source,{}).get('social_profile',{}).get('species')
    return cfg.get('species_lessons',{}).get(species,cfg['legacy_training'])


def fieldwork(w, p, e, effect):
    if effect == 'comfort':
        if p.hp >= p.max_hp:
            return e.name + ' settles quietly at your side. You already feel well.'
        gained = min(3, p.max_hp - p.hp)
        p.hp += gained
        return f'{e.name} steadies you. You regain {gained} health.'
    if effect in ('guard', 'pounce'):
        return e.name + (' plants its feet and holds the line.' if effect == 'guard' else ' springs cleanly to the training mark.')
    from engine import frontiers
    queue = deque([(p.location, '', 0)])
    seen = {p.location}
    while queue:
        rid, first, depth = queue.popleft()
        room = w.rooms[rid]
        data = w.room_details.get(rid, {})
        if depth:
            found = (effect == 'water' and (data.get('climate', {}).get('terrain') in ('lake','river','water','wetland','coast') or data.get('requires_boat'))
                     or effect == 'forage' and bool(data.get('resources'))
                     or effect == 'tracks' and any(a.alive and not a.progress.get('companion_owner') and
                        w.npcs.get(a.source_def, {}).get('social_profile', {}).get('sentient') is False for a in w.entities_in_room(rid))
                     or effect == 'scout' and depth >= 2)
            if found:
                from engine import knowledge
                knowledge.teach(w, p, {'rooms':[rid]})
                return f'{e.name} signals {room.name}, {depth} steps away. Start {first}.'
        if depth >= 3:
            continue
        for direction, dest in room.exits.items():
            if dest in seen or dest not in w.rooms or w.rooms[dest].map_visibility == 'hidden':
                continue
            if frontiers.blocked(w, rid, direction, p):
                continue
            seen.add(dest)
            queue.append((dest, first or direction, depth + 1))
    return e.name + ' finishes the search. Nothing matching the signal is within three steps.'


def command(ctx, args):
    w, p = ctx.world, ctx.player
    cfg = rules(w)
    if not eligible(w, p) or not p.alive:
        raise ValueError('A conscious licensed-class handler is required.')
    action, _, target = args.strip().partition(' ')
    target, _, selected_skill = target.partition(' | ')
    at_hall = inside(w,p)
    if action != 'use' and not at_hall:
        raise ValueError('Visit '+w.rooms[cfg['hall']].name+' at '+w.rooms[cfg['approach']].name+'.')
    if action in ('desk','study'):
        from engine import quest_discovery
        item = w.items[cfg['charter']]
        if cfg['charter'] not in w.rooms[p.location].items:
            raise ValueError('The charter is unavailable here.')
        ids = quest_discovery.disclose(w,p,item['knowledge'],'item',cfg['charter'])
        if action == 'study':
            quest_progress.action(p,'union_study')
        return item['read_text'] + quest_discovery.offer_text(w,p,ids)
    rows = roster(p)
    if action == 'adopt':
        if not completed(p,cfg['licence']):
            raise ValueError('Finish the introductory charter quest first.')
        source = next((i for i in cfg['stock'] if target.casefold() in (i.casefold(),w.npcs[i]['name'].casefold())),None)
        if not source:
            raise ValueError('Choose an animal from the register.')
        if len(rows) >= cfg['capacity']:
            raise ValueError('All roster places are occupied.')
        if any(c.get('source_def') == source for c in rows):
            raise ValueError('This animal type is already in your roster.')
        d = w.npcs[source]
        e = Entity('companion_'+uuid4().hex,d['name'],d['hp'],d['hp'],d['attack'],d['defense'],source_def=source,group_id=p.group_id)
        use_now = len(active(w,p)) < (2 if completed(p,cfg['brace']) else 1)
        e.progress.update(companion_owner=p.id,companion_mode='peaceful' if spec(w,source)['temperament']=='peaceful' else 'defend',
                          union_boarded=not use_now,companion_order='follow' if use_now else 'dismissed')
        if use_now:
            w.add_entity(e,p.location)
        else:
            e.location=p.location
            companions.reserve(w)[e.id]=asdict(e)
        rows.append(dict(id=e.id,name=e.name,kind='pet',source_def=source,attack=e.attack,description=d['description']))
        quest_progress.action(p,'union_bond')
        quest_progress.action(p,'tame')
        return e.name + (' joins you.' if use_now else ' is registered and waiting in the stable.')
    matches = [c for c in rows if target.casefold() in (c['id'].casefold(), c['name'].casefold())]
    if len(matches) != 1:
        raise ValueError('Choose one of your registered companions.')
    c, = matches
    eid = c['id']
    e = w.entities.get(eid)
    reserve = companions.reserve(w)
    saved = reserve.get(eid)
    if (e and e.progress.get('companion_owner')!=p.id) or (saved and saved['progress'].get('companion_owner')!=p.id):
        raise ValueError('This companion belongs to another handler.')
    if not e and not saved:
        raise ValueError('Recall this companion first to register its living identity.')
    dead = eid in mortality.state(w)['deaths'] or (e.hp if e else saved['hp']) <= 0
    if action == 'revive':
        if not dead:
            raise ValueError('This companion is alive.')
        snapshot = asdict(e) if e else saved.copy()
        snapshot['progress']=dict(snapshot['progress'])
        for key in ('death_recorded','_combat_death_resolved','_npc_death_resolved','_environmental_death_resolved','permanently_dead'):
            snapshot['progress'].pop(key,None)
        snapshot['progress'].update(companion_order='dismissed',union_boarded=True)
        snapshot.update(hp=snapshot['max_hp'],corpse_expires_at=None,location=p.location)
        reserve[eid]=snapshot
        if e:
            if eid in w.rooms[e.location].entities:w.rooms[e.location].entities.remove(eid)
            del w.entities[eid]
        mortality.state(w)['deaths'].pop(eid,None)
        from engine import relationships
        for bond in relationships.state(w)['bonds'].values():
            if eid in bond.get('deceased',[]):bond['deceased'].remove(eid)
        return c['name']+' lives again and is resting in the stable.'
    if dead:
        raise ValueError('Ask the healer to resurrect this companion first.')
    if action == 'present':
        quest_progress.action(p,'union_bond')
        return c['name']+' is confirmed on your licence.'
    if action == 'stable':
        if not e:
            raise ValueError('This companion is already stabled.')
        e.progress.update(companion_order='dismissed',union_boarded=True)
        reserve[eid]=asdict(e)
        w.rooms[e.location].entities.remove(eid)
        del w.entities[eid]
        quest_progress.action(p,'union_stable')
        return c['name']+' is resting in the stable.'
    if action == 'recall':
        if c in active(w,p):
            raise ValueError('This companion is already active.')
        text=companions.recall(w,p,c,e)
        quest_progress.action(p,'union_recall')
        return text
    if action == 'heal':
        if e:e.hp=e.max_hp
        else:saved['hp']=saved['max_hp']
        return c['name']+' is at full health.'
    if action in ('train','use'):
        if not completed(p,cfg['training']):
            raise ValueError('Finish the bonding quest before field training.')
        if not e or e.location!=p.location or c not in active(w,p):
            raise ValueError('Call this companion to your side first.')
        definition=lesson(w,c.get('source_def'))
        choices=[definition,*definition.get('other_skills',[])]
        if selected_skill:
            definition=next((r for r in choices if r['skill'].casefold()==selected_skill.casefold()),None)
            if not definition:raise ValueError('Choose a skill suited to this animal.')
        effect=definition['effect']
        learned=e.progress.setdefault('union_skills',[choices[0]['effect']] if e.progress.get('union_trained') else [])
        if action=='train':
            if effect not in learned:
                e.attack+=2 if effect=='pounce' else 0
                e.defense+=2 if effect=='guard' else 0
                learned.append(effect)
            quest_progress.action(p,'union_train')
            return e.name+' responds to the '+definition['skill']+' signal.'
        if effect not in learned:
            raise ValueError('Train this skill at the Union first.')
        now=living.state(w)['minute']
        if effect=='comfort' and p.hp<p.max_hp and now<e.progress.get('next_comfort',0):
            raise ValueError('Your companion needs a few minutes before it can comfort you again.')
        if effect=='comfort' and p.hp<p.max_hp:e.progress['next_comfort']=now+5
        text=fieldwork(w,p,e,effect)
        if at_hall:quest_progress.action(p,'union_train')
        quest_progress.action(p,'union_practice')
        return text
    raise ValueError('Choose a listed Union service.')


def panel(w,p):
    if not eligible(w,p):
        return None
    cfg=rules(w)
    hall=cfg['hall']; yard=cfg['approach']
    data=dict(title=w.rooms[hall].name, yard=yard, yard_name=w.rooms[yard].name, hall=hall, here=inside(w,p),at_desk=p.location==hall,
              capacity=cfg['capacity'], slots=2 if completed(p,cfg['brace']) else 1, active=len(active(w,p)), pets=[])
    from engine import knowledge
    knowledge.teach(w,p,{'rooms':[yard,hall]})
    for c in roster(p):
        e=w.entities.get(c['id']); saved=companions.reserve(w).get(c['id'],{})
        info=lesson(w,c.get('source_def'))
        status='Deceased' if c['id'] in mortality.state(w)['deaths'] or (e and not e.alive) else 'Active' if c in active(w,p) else 'Stabled'
        progress=e.progress if e else saved.get('progress',{})
        learned=progress.get('union_skills',[info['effect']] if progress.get('union_trained') else [])
        skills=[dict(name=r['skill'],trained=r['effect'] in learned) for r in [info,*info.get('other_skills',[])]]
        data['pets'].append(dict(id=c['id'],name=c['name'],status=status,skills=skills))
    if data['here']:
        data['stock']=[dict(name=w.npcs[i]['name'],**spec(w,i)) for i in cfg['stock']]
        data['licenced']=completed(p,cfg['licence'])
        data['quests']=[dict(name=w.quests[q]['name'],status=quest_progress.status(w,p,q)) for q in cfg['quests']
                       if (q in p.progress.get('quest_sources',{}) or q in p.progress.get('quests',{})) and not living.quest_blocked(w,p,w.quests[q]) and not completed(p,q)][:1]
    return data
