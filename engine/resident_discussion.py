"""Resident discussion grounded in known relationships, duties and local papers.

Public dialogue describes facts a resident can know. It does not reveal private
statistics, invent remote sightings, or create a hidden global news feed.
"""
from engine import living, livelihoods, relationships, society, worldtime


def _notes(person):
    from engine import town_talk
    return town_talk.notebook(person)


def _profile(world, person):
    if (person.spawner_key or '').startswith('birth:'):
        return {}
    return world.npcs.get(person.source_def, {}).get('founding_profile', {})


def _select(rows, turn):
    return rows[turn % len(rows)] if rows else ''


def _clock(minute):
    minute=int(minute)%worldtime.MINUTES_PER_DAY
    return f'{minute//60:02d}:{minute%60:02d}'


def feelings(world, speaker, turn=0):
    """Authored affection/grievances and this resident's actual saved bonds."""
    from engine import town_talk
    lines=[]
    for tie in _profile(world,speaker).get('feelings', []):
        other=world.npcs.get(tie.get('person'), {})
        if not other.get('name'):continue
        opening='I care deeply for ' if tie.get('kind')=='love' else 'I have a difficult relationship with '
        reason=str(tie.get('why','')).strip().rstrip('.')
        lines.append(opening+other['name']+'.'+(' '+other['name']+' '+reason+'.' if reason else ''))
    contacts=town_talk.contacts_for(world,speaker)
    bonds=relationships.state(world)['bonds']
    for ident,fact in list(contacts.items())[-24:]:
        row=bonds.get('|'.join(sorted((speaker.id,ident))))
        if not row or row.get('deceased'):continue
        name=fact['name'];kinds=row.get('kinds',[]);trust=row.get('trust',0)
        if 'married' in kinds:
            lines.append(name+' is my spouse. '+('We have been getting along well, and I value that closeness.' if trust>=0 else 'Things have been strained between us; I hope we can talk honestly.'))
        elif 'lover' in kinds:
            lines.append('I am close to '+name+'. '+('Our relationship means a great deal to me.' if trust>=0 else 'I still care, but we have disagreements to work through.'))
        elif trust<=-5:
            lines.append('I am upset with '+name+'. Our recent interactions have damaged my trust, and I need some space.')
        elif 'friend' in kinds or trust>=10:
            lines.append('I enjoy '+name+'’s company. We have built some trust, and I would welcome another conversation.')
        elif 'business' in kinds:
            lines.append(name+' is a business partner. Keeping our agreements and doing the work matters to me.')
        elif 'parent' in kinds:
            lines.append(name+' is part of my family. I think about how we can look after one another.')
    if lines:return _select(list(dict.fromkeys(lines)),turn)
    return ''


def work(world, speaker, turn=0):
    cfg=livelihoods.definition(world,speaker)
    role=cfg.get('occupation') or cfg.get('profession')
    if not role or speaker.progress.get('retired'):
        return 'I have retired from regular work. I still make time for the people and activities around me.' if speaker.progress.get('retired') else ''
    start,duration=livelihoods.hours(world,speaker)
    place=world.rooms.get(livelihoods.workplace(world,speaker))
    place_text=' at '+place.name if place else ''
    role_text=str(role).replace('_',' ')
    article='an ' if role_text[:1].lower() in 'aeiou' else 'a '
    text='I work as '+article+role_text+place_text+'. My shift runs from '+_clock(start)+' to '+_clock(start+duration)+'.'
    supplies=livelihoods.job_needs(world,speaker)
    if supplies:
        parts=[str(qty)+' '+world.items.get(iid,{}).get('name',iid) for iid,qty in list(supplies.items())[:3]]
        text+=' I still need '+', '.join(parts)+' for the work.'
    elif livelihoods.on_shift(world,speaker):
        text+=' I am on duty now, so I need to keep an eye on my responsibilities.'
    else:text+=' I am off duty just now; it is a chance to catch up with people.'
    return text


def activities(world, speaker, turn=0):
    from engine import community_quests
    book=getattr(world,'living_state',{}).get('community_jobs',{})
    job=next((j for j in book.get('jobs',{}).values() if j.get('worker')==speaker.id and j.get('status')=='active'),None)
    if job:
        step=job['steps'][job['index']]
        place=world.rooms.get(step['room'])
        stage={'gather':'gather supplies','make':'make the requested goods','watch':'supervise the children',
               'herd':'bring the animals together','arrive':'bring the herd to its destination',
               'find':'find the requested person or animal','deliver':'deliver the result and collect my pay'}.get(step['action'],'continue the request')
        return 'I accepted '+job['name']+'’s request: '+job['title']+'. Next I need to '+stage+(' at '+place.name if place else '')+'. The agreed payment is '+str(job['pay'])+' gold.'
    own=next((j for j in book.get('jobs',{}).values() if j.get('issuer')==speaker.id and j.get('status') in ('open','active')),None)
    if own:
        return 'I need help with '+own['title']+'. '+(own.get('worker_name','Someone')+' has taken the job.' if own['status']=='active' else 'I have put aside '+str(own['pay'])+' gold for someone who can do it. Check Local quests.')
    receipt=speaker.progress.get('community_receipt')
    if receipt and turn%3==0:return 'Someone helped me recently. '+receipt
    source=str(getattr(speaker,'activity','') or '').strip().rstrip('.')
    if source:
        text='At the moment I am '+source[:1].lower()+source[1:]+'.'
        mood=speaker.progress.get('npc_life',{}).get('mood',50)
        if mood<30:text+=' It has been a difficult day, and I could use a little patience.'
        elif mood>65:text+=' I am feeling good about how the day is going.'
        else:text+=' It is good to have a moment to talk while I am here.'
        return text
    return ''


def plans(world, speaker, turn=0):
    now=int(living.state(world)['minute']);cfg=livelihoods.definition(world,speaker)
    program=getattr(world,'living_state',{}).get('public_program_v1',{})
    ticket=program.get('tickets',{}).get(speaker.id)
    if ticket and ticket.get('to') in world.rooms:
        return 'I have a carriage booking to '+world.rooms[ticket['to']].name+' at '+_clock(ticket['time'])+'. I need to be at the stand when it leaves.'
    rows=[]
    for shift in cfg.get('schedule',[]):
        destination=world.rooms.get(shift.get('room'))
        if not destination:continue
        due=int(shift.get('hour',0))*60+int(shift.get('minute',0))
        wait=(due-now)%worldtime.MINUTES_PER_DAY
        if wait:rows.append((wait,'My schedule next calls for '+shift.get('activity','an activity')+' at '+destination.name+' at '+_clock(due)+'.'))
    if rows:return min(rows)[1]
    role=cfg.get('occupation') or cfg.get('profession')
    site=world.rooms.get(livelihoods.workplace(world,speaker)) if role else None
    if role and site and not speaker.progress.get('retired'):
        start,duration=livelihoods.hours(world,speaker)
        if livelihoods.on_shift(world,speaker):
            home=world.rooms.get(speaker.progress.get('home_room') or cfg.get('home_room'))
            return 'My shift ends at '+_clock(start+duration)+'.'+(' After that, I expect to head back to '+home.name+' and rest.' if home else ' After that, I will have some time away from work.')
        return 'My next shift starts at '+_clock(start)+' at '+site.name+'. I need to be there ready for '+str(role).replace('_',' ')+' work.'
    from engine import civic_program,gazette
    place=gazette.local(world,speaker.location)
    if place and place.get('home') in world.rooms:
        for day in (now//worldtime.MINUTES_PER_DAY,now//worldtime.MINUTES_PER_DAY+1):
            upcoming=[e for e in civic_program.entries(world,place,day) if e['begin']>now]
            if upcoming:
                event=min(upcoming,key=lambda e:e['begin'])
                return 'The local paper lists '+event['title']+' at '+event['name']+' at '+_clock(event['begin'])+'. I have not committed to attending yet, but it is something to consider.'
    return 'I do not have another appointment arranged. I will see what needs doing locally before making plans.'


def creatures(world, speaker, turn=0):
    nearby=[e for e in world.entities_in_room(speaker.location) if e.id!=speaker.id and e.alive and not e.is_player and not relationships.sentient(world,e)]
    if not nearby:return ''
    animal=nearby[turn%len(nearby)];definition=world.npcs.get(animal.source_def,{})
    row=relationships.state(world)['bonds'].get(relationships.key(speaker,animal),{})
    owner=animal.progress.get('companion_owner')
    if owner==speaker.id or 'companion' in row.get('kinds',[]):
        return animal.name+' is a companion I care about. '+('They look injured, and I want to help them recover.' if animal.hp<animal.max_hp else 'I like having them nearby, and keeping them fed and safe matters to me.')
    if definition.get('aggressive'):
        return 'I am wary of '+animal.name+' here. It has a dangerous temperament; I would rather give it space than risk someone being hurt.'
    if animal.hp<animal.max_hp:
        return animal.name+' looks injured. I feel sorry for it; I hope someone who knows how to care for it can help.'
    kind=definition.get('social_profile',{}).get('species')
    species=getattr(world,'species',{}).get(kind,{})
    diet=species.get('diet')
    return 'I have been watching '+animal.name+' here. '+('Its recorded diet is '+str(diet).replace('_',' ')+', so the right food matters.' if diet else 'I enjoy seeing local wildlife, provided we give it enough space and do not disturb it.')


def read_local_paper(world, speaker):
    """Reading requires a public local venue; no remote person/status lookup."""
    from engine import gazette,town_talk
    notes=_notes(speaker);minute=int(living.state(world)['minute'])
    if minute<notes.get('next_paper',0):return notes.get('news',{})
    notes['next_paper']=minute+30
    room=living.details(world,speaker.location)
    if not (room.get('quest_board') or set(room.get('facilities',())) & {'inn','tavern','market','library','guild','school','recreation'}):
        return notes.get('news',{})
    place=gazette.local(world,speaker.location)
    if not place:return notes.get('news',{})
    archive=getattr(world,'living_state',{}).get('press_archive_v1',{})
    records=[]
    for day in (minute//worldtime.MINUTES_PER_DAY,minute//worldtime.MINUTES_PER_DAY-1):
        records.extend((day,a) for a in archive.get(str(day),{}).get(place['name'],[]) if a.get('last',0)<=minute)
    reports=notes.setdefault('news',{})
    for day,article in sorted(records,key=lambda pair:(gazette.priority(pair[1]),-pair[1].get('last',0)))[:2]:
        key=str(day)+'/'+place['name']+'/'+str(article['key'])
        town_talk.remember(reports,key,dict(area=place['name'],headline=gazette.traffic_headline(world,article),section=article['section']),8)
    return reports


def news(world,speaker,turn=0):
    reports=read_local_paper(world,speaker)
    if not reports:return ''
    article=_select(list(reports.values()),turn)
    reaction={'Public safety':'That worries me; people need a clear warning about the danger.',
              'Watch':'I hope the watch follows up and keeps people informed.',
              'Education':'It is encouraging to hear about people learning something useful.',
              'Culture':'It gives people something to look forward to together.',
              'Commerce':'Changes like that can affect local work and supplies.',
              'Trade':'It is good to know what the local workshops have been doing.'}.get(article.get('section'),'I would like to hear how it affects the people involved.')
    return 'The '+article['area']+' Gazette reported: '+article['headline'].rstrip('.')+'. '+reaction


TOPICS={'people':feelings,'work':work,'activities':activities,'plans':plans,'creatures':creatures,'localnews':news}


def discuss(world,speaker,topic):
    notes=_notes(speaker)
    turns=notes.setdefault('topic_turns',{})
    turn=turns.get(topic,0);turns[topic]=turn+1
    text=TOPICS[topic](world,speaker,turn)
    fallback={'people':'I am still getting to know the people around me. I do not have a particular relationship to discuss yet.',
              'work':'I do not currently have a regular job. I can still look for local requests that fit my time and skills.',
              'activities':'I am taking a moment here to look around and talk with people.',
              'creatures':'I have not seen a creature here that I can describe from my own experience.',
              'localnews':'I have not read or been told a local report yet. We can look at the Newspaper, or you can share an article with me.'}
    return text or fallback.get(topic,'I do not have a definite plan to share yet.')


def everyday(world,speaker,listener,turn):
    """Two or three relevant sentences; the existing social loop owns cooldowns."""
    from time import monotonic
    fight=getattr(speaker,'_fight_display',None)
    if fight and fight[0]==speaker.location and fight[1]>monotonic():
        return 'calls out','There is fighting here! Keep an eye on the attackers and make room for anyone trying to get to safety.','I see it. We need to be careful.'
    if speaker.hp*3<=speaker.max_hp:
        return 'calls out','I am badly hurt and need help. I cannot keep going like this; is there a healer or a safe place nearby?','Let us see who can help you.'
    notes=_notes(speaker);counter=notes.get('discussion_turn',turn);notes['discussion_turn']=counter+1
    # Try only a small rotating subset. Full-world relationship scans are avoided.
    topics=tuple(TOPICS)
    for offset in range(len(topics)):
        topic=topics[(counter+offset)%len(topics)]
        words=TOPICS[topic](world,speaker,counter//len(topics))
        if not words:continue
        reply={'people':'It helps to hear why you feel that way. Relationships take time and care.',
               'work':'That sounds like a full day. Tell me if there is something practical I can help with.',
               'activities':'Now I understand what you are working on. I hope it goes well.',
               'plans':'I will keep that in mind. It is useful to know what is coming up.',
               'creatures':'We should pay attention to how they are doing and give them the space they need.',
               'localnews':'Thank you for telling me. I will look for the report in the Newspaper.'}[topic]
        if topic=='localnews':
            from engine import town_talk
            reports=_notes(listener).setdefault('news',{})
            for key,article in list(notes.get('news',{}).items())[-2:]:
                town_talk.remember(reports,key,dict(article),8)
        return 'says',words,reply
    return None
