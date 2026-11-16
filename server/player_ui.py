"""Session-bound player lists. Caller supplies the authenticated actor, never a body ID."""
from collections import Counter
from engine import knowledge, navigation, item_catalog, quest_progress

KINDS = ('abilities','quests','journal','adventures','inventory','catalog','wardrobe','recipes','markets','survey','condition')


def action(label, command): return dict(label=label,command=command)
def location(w,rid): return dict(id=rid,name=w.rooms[rid].name) if rid in w.rooms else None


def _quests(w,p,kind,query):
    rows=[];tracked=set(navigation.selected(w,p));counts=Counter(p.inventory);known_rooms=knowledge.ids(w,p,'rooms')
    pool=[w.quests[qid] for qid in knowledge.accepted(w,p)]
    for q in sorted(pool,key=lambda q:(q.get('name',''),q['id'])):
        if query and query.casefold() not in (' '.join([q['name'],q.get('region',''),q.get('arc_id','')])).casefold():continue
        status=p.progress.get('quests',{}).get(q['id'],'offered');children=[]
        for rid in q.get('visit_rooms',[]):
            if rid in w.rooms:children.append(dict(id='visit:'+rid,label=w.rooms[rid].name,
                detail='Visited' if quest_progress.count(p,q,'visits',rid) else 'Not yet visited',location=location(w,rid)))
        for iid,n in q.get('required_items',{}).items():
            if iid in w.items:children.append(dict(id='item:'+iid,label=w.items[iid]['name'],detail=f'{counts[iid]} / {n} carried'))
        for nid,n in q.get('kills',{}).items():
            if nid in w.npcs:children.append(dict(id='kill:'+nid,label=w.npcs[nid]['name'],detail=f"{quest_progress.count(p,q,'kills',nid)} / {n} defeated"))
        for key,n in q.get('actions',{}).items():
            kind_name,_,ident=key.partition(':');defs={'read':w.items,'cook':getattr(w,'recipes',{}),'craft':getattr(w,'recipes',{}),'gather':getattr(w,'resources',{})}.get(kind_name,{})
            label=kind_name.replace('_',' ').title()+(' '+defs.get(ident,{}).get('name','the required task') if ident else '')
            children.append(dict(id='action:'+key,label=label,detail=f"{quest_progress.count(p,q,'actions',key)} / {n}"))
        for nid in q.get('talk_to',[]):
            if nid in w.npcs:children.append(dict(id='talk:'+nid,label='Speak to '+w.npcs[nid]['name'],detail='Spoken' if quest_progress.count(p,q,'talks',nid) else 'Waiting'))
        row=dict(id=q['id'],label=q['name'],detail=status.title()+'. '+q.get('description',''),children=children,actions=[])
        if status=='offered':
            # Offer summaries do not give away objectives before acceptance.
            row['children']=[];row['actions']=[action('Accept','accept '+q['id'])]
        elif status=='active':row['actions']=[action('Untrack' if q['id'] in tracked else 'Track quest',('untrack ' if q['id'] in tracked else 'track ')+q['id']),action('Complete','complete '+q['id'])]
        from engine import interface_tours
        guide=interface_tours.summary(p,q)
        if guide is not None:
            if not guide['started']:detail='Optional interface guide available.'
            elif guide['completed']:detail='Guide finished. Continue your quest objectives.'
            else:detail=('Required guide: ' if guide['required'] else 'Optional review: ')+str(guide['index'])+' / '+str(guide['total'])+' steps acknowledged.'+(' Paused; resume when ready.' if guide['paused'] else '')
            children.insert(0,dict(id='interface-guide',label=q['interface_tour']['title'],detail=detail))
            row['actions'].append(action('Interface guide','interface resume '+q['id']))
        if q.get('escort') and status!='offered':
            spec=q['escort'];done=p.progress.get('escort_arrivals',{}).get(q['id'])
            who=w.npcs[spec['npc']]['name'];where=w.rooms[spec['destination']].name
            children.append(dict(id='escort',label=spec['mode'].title()+' '+who+' to '+where,detail='Arrived together' if done else 'Meet '+who+' and travel together.',location=location(w,spec['destination'])))
            from engine import escorts
            person=escorts.companion(w,p,q)
            if person and done:
                knowledge.teach(w,p,{'rooms':[person.location]})
                children.append(dict(id='guide-now',label=person.name,detail='Now at '+w.rooms[person.location].name+'.',location=location(w,person.location)))
            if status=='active' and not done:
                start=escorts.start_room(w,q)
                if start in w.rooms:children.append(dict(id='pickup',label='Starting point',detail=w.rooms[start].name,location=location(w,start)))
                joined=p.progress.get('escort_party',{}).get('quest')==q['id']
                next(child for child in children if child['id']=='escort')['detail']=escorts.report(w,p,q)
                if person:
                    knowledge.teach(w,p,{'rooms':[person.location]})
                    children.insert(0,dict(id='meet-guide',label=who,detail=escorts.report(w,p,q),location=location(w,person.location)))
                    if not joined and person.location==p.location:row['actions'].append(action(spec['mode'].title()+' '+who,spec['mode']+' '+q['id']))

        rid=q.get('turn_in_room') or q.get('offer_room')
        if rid in known_rooms:row['location']=location(w,rid)
        from engine import progression
        if progression.config(w)['enabled']:
            reward=q.get('reward_xp',progression.config(w)['quest_xp'])
            row['detail']+=f' First completion: {reward} XP.'
            if q.get('repeatable'):row['detail']+=' Repeat practice XP requires fresh objectives or newly supplied goods, within your daily budget.'
        row['group']=q.get('region') or ('Current work' if status=='active' else 'Completed work' if status=='complete' else 'Recorded work')
        rows.append(row)
    return rows


def list_packet(w,p,kind,query=''):
    if kind not in KINDS:raise ValueError('Choose a player list from the toolbar.')
    knowledge.sync(w,p,observe=True)
    rows=[];pagination=None;note='Only your own knowledge is shown. Names are displayed; internal references are not labels.'
    if kind=='abilities':
        from engine import ability_rules
        rows=ability_rules.rows(w,p,query)+ability_rules.scroll_rows(w,p,query)
        note='Your learned abilities and eligible lessons at this school. Requirements are checked again when you act; recovery uses game time.'
    elif kind in ('quests','journal','adventures'):
        import re
        page=1;match=re.search(r'(?:^|\s)page(?::|\s+)([0-9]{1,6})$',query)
        if match:
            page=max(1,int(match.group(1)));query=query[:match.start()].strip()
        rows=_quests(w,p,kind,query)
        if kind=='adventures':rows=[r for r in rows if w.quests[r['id']].get('arc_id')]
        pagination=dict(page=page,pages=max(1,(len(rows)+49)//50))
        rows=rows[(page-1)*50:page*50]
        note='Only accepted/completed work. Speak with people or read in-world items to receive quests. Tracking never moves your character.'
    elif kind in ('inventory','catalog','wardrobe','recipes'):
        recipe=kind=='recipes'
        if recipe:knowledge.learn_local_recipes(w,p)
        selected=p.inventory if kind=='inventory' else knowledge.ids(w,p,'recipes' if recipe else 'items')
        found,total,request=item_catalog.page(w,query,recipe=recipe,player=p,wardrobe=kind=='wardrobe',ids=selected)
        counts=Counter(p.inventory);known_rooms=knowledge.ids(w,p,'rooms')
        pagination=dict(page=request.page,pages=max(1,(total+item_catalog.PAGE_SIZE-1)//item_catalog.PAGE_SIZE))
        for obj in found:
            iid=obj['id'];row=dict(id=iid,label=obj['name'],detail=obj.get('description',''),children=[],actions=[])
            if recipe:
                row['group']=obj.get('station','hand').replace('_',' ').title()
                for key,label in [('ingredients','Needs'),('outputs','Makes')]:
                    row['children'].append(dict(id=key,label=label,children=[dict(id=i,label=w.items[i]['name'],detail=str(n)) for i,n in obj.get(key,{}).items() if i in w.items]))
                row['actions']=[action('Cook' if obj.get('kind')=='cooking' else 'Craft',('cook ' if obj.get('kind')=='cooking' else 'craft ')+iid)]
            else:
                row['group']=(obj.get('slot') or obj.get('type') or 'Items').replace('_',' ').title()
                row['detail']=f"{counts[iid]} carried"+(' · equipped' if iid in p.equipped.values() else '')+'. '+row['detail']
                if counts[iid] and (obj.get('slot') or obj.get('type') in ('weapon','armor')):row['actions']=[action('Unequip' if iid in p.equipped.values() else 'Equip',('unequip ' if iid in p.equipped.values() else 'equip ')+iid)]
            rid=obj.get('location')
            if rid in known_rooms:row['location']=location(w,rid)
            rows.append(row)
        note=item_catalog.header(kind.title(),total,request)+'. Page/search controls refer only to known records.'
    elif kind=='markets':
        from engine import market_shifts
        known=knowledge.ids(w,p,'rooms')
        for cfg in market_shifts.definitions(w).values():
            if cfg['room'] not in known:continue
            if query and query.casefold() not in cfg['name'].casefold():continue
            row=dict(id=cfg['id'],label=cfg['name'],detail='Finite provision counter. Convenience premium applies. Travel there to inspect live stock.',group='Known counters',location=location(w,cfg['room']),children=[])
            if cfg['room']==p.location:
                s=market_shifts.depot(w,cfg)
                teach_items=[i for i in s['stock'] if i in w.items];knowledge.teach(w,p,{'items':teach_items})
                row['children']=[dict(id=i,label=w.items[i]['name'],detail=f"{s['stock'][i]} left · {market_shifts.price(w,cfg,i)} gold") for i in teach_items]
            rows.append(row)
    else:
        from engine import living
        from engine.commands import CommandContext
        ctx=CommandContext(world=w,player=p,room=w.rooms[p.location],registry=None,raw=kind)
        text=living.command(ctx,'',kind)
        rows=[dict(id=kind,label='Here and now',detail=text,group=kind.title())]
        if kind=='survey' and living.enabled(w):
            from engine import gathering
            rows.extend(gathering.listing(w,p))
    groups={}
    for row in rows:groups.setdefault(row.pop('group','Entries'),[]).append(row)
    return dict(type='player_list',kind=kind,title=kind.title(),groups=[dict(id=str(i),label=k,children=v) for i,(k,v) in enumerate(groups.items())],note=note,pagination=pagination)


def handle(world, player, args, request_id=None, *, director=False):
    """Handle only the suffix after `ui `. No player/host ID accepted from client."""
    if not player.is_player:raise ValueError('A player session is required.')
    words=args.strip().split(maxsplit=2)
    if not words:raise ValueError('Choose a player list.')
    if words[0]=='list':
        if len(words)<2:raise ValueError('Choose a player list.')
        packet=list_packet(world,player,words[1],words[2] if len(words)>2 else '')
    elif words[0]=='globe-pins':
        import json
        from engine import travel_pins
        try:payload=json.loads(args.partition(' ')[2])
        except ValueError:raise ValueError('Choose a globe destination action.')
        packet={'type':'globe_pins',**travel_pins.handle(world,player,payload)}
        known=knowledge.ids(world,player,'rooms')
        packet['learned']=[navigation.pin(world,player,rid,_known=known) for rid in sorted(known)
                           if rid in world.rooms and rid!=player.location and rid not in player.explored_rooms]
    elif words[0]=='chronicles':
        from engine import chronicles
        import json
        value=json.loads(args.partition(' ')[2] or '{}')
        if not isinstance(value,dict):raise ValueError('Invalid history request.')
        section=value.get('section','geology');query=value.get('query','');n=value.get('page',1)
        if section not in chronicles.LABELS or not isinstance(query,str) or len(query)>120 or type(n) is not int:
            raise ValueError('Invalid history selection.')
        packet={'type':'chronicle_page','director':director,**chronicles.page(world,player,section,query,n,
                all_people=director and value.get('full') is True)}
    elif words[0]=='gazette':
        from engine import gazette
        query=args.strip().partition(' ')[2]
        dispatches={}
        venues={}
        text=gazette.browse(world,player,query,dispatches=dispatches,venues=venues)
        knowledge.teach(world,player,{'rooms':list(set(venues.values()))})
        event_pins={block:navigation.pin(world,player,rid,_known=set(venues.values())) for block,rid in venues.items()}
        player._read_news=dispatches
        packet=dict(type='press_edition', venues=event_pins, stories=[dict(ref=key,title=row['headline']) for key,row in dispatches.items()],editions=[dict(name=r['name'],kind=r['kind']) for r in gazette.editions(world)],text=text,local=(gazette.local(world,player.location) or {}).get('name'))
    elif words[0]=='appearance':
        import json
        from engine.character_style import choices, validate
        opts=choices(world.races.get(player.race,{}) or {},world.classes.get(player.char_class,{}) or {})
        raw=args.strip().partition(' ')[2]
        if raw:
            selected=validate(json.loads(raw),opts)
            player.progress['character_style']=selected
            if 'hair_style' in selected or 'hair_color' in selected:player.progress.pop('hair',None)
        packet=dict(type='character_appearance',options=opts,selection=player.progress.get('character_style',{}),applied=bool(raw))
    elif words[0]=='navigation':packet=navigation.packet(world,player)
    elif words[0]=='focus':
        if len(words)!=2:raise ValueError('Choose one learned location.')
        packet=dict(type='player_map_focus',pin=navigation.pin(world,player,words[1]))
    else:raise ValueError('Unknown player view.')
    if isinstance(request_id,(str,int)) and not isinstance(request_id,bool):packet['request_id']=str(request_id)[:100]
    return packet
