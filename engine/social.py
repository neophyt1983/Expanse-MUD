"""NPC social signals and target-bound relationship quests. No faction reputation farming."""
from copy import deepcopy
from engine import living, relationships as rel, society

EMOTIONS = {'happy':'🙂', 'excited':'🤩', 'in_love':'😍', 'amusement':'😄',
            'sleepy':'😴', 'serious':'😐', 'irritated':'😒', 'angry':'😠',
            'insulted':'😧', 'insulting':'😏'}
DELTAS = dict(happy=2, excited=3, in_love=3, amusement=2, sleepy=1,
              serious=1, irritated=-2, angry=-4, insulted=-2, insulting=-6)
PREFERENCES = dict(wanted_items=[], wanted_types=[], disliked_items=[],
                   gift_limit=3, cooldown_minutes=10, emotions=['happy','serious','amusement'])
QUEST_DEFAULT = dict(enabled=False, minimum_trust=0, maximum_trust=100,
                     romantic=False, goals={'happy':1}, reward_trust=5)

def target(w, a, text):
    from engine.player_names import nearby
    return nearby(w,a,text)

def gate(w,a,b,romantic=False,gift=False):
    from engine import livelihoods
    if not livelihoods.awake(w,b):raise ValueError(b.name+' is sleeping. Choose Wake NPC or return during waking hours.')
    if not a.alive or not b.alive or a.id==b.id or a.location!=b.location:
        raise ValueError('Meet the living NPC at the same location first.')
    score=society.friendliness(w,a,b)
    if score < 50:
        raise ValueError('Faction standing does not permit this interaction.')
    if gift and score <= 50:
        # Unaligned NPCs have no faction whose reputation can rise above the
        # neutral baseline. Earn their personal trust instead, without granting
        # a bypass for named factions or explicitly hostile unaffiliated rules.
        if b.is_player or b.group_id:
            raise ValueError('Gifts require faction standing above 50; current standing is '+str(score)+'.')
        policy=w.groups.get(a.group_id,{})
        if ('*' in policy.get('hostile_to',[]) or
                society.standing(w,a,'unaffiliated') < 50):
            raise ValueError('Faction standing does not permit gifts to unaffiliated NPCs.')
        trust=rel.bond(w,a,b)['trust']
        if trust < 10:
            raise ValueError('This unaffiliated NPC needs personal trust of at least 10 for gifts; current trust is '+str(trust)+'.')
    if romantic:
        rel.eligible(w,a,b,'lover')
        if not b.is_player and not any(k in rel.profile(w,b)['accepts'] for k in rel.ROMANTIC):
            raise ValueError('This NPC does not welcome romantic attention.')

def prefs(w,b,include_needs=True):
    result={**deepcopy(PREFERENCES), **w.npcs.get(b.source_def,{}).get('gift_preferences',{})}
    from engine import needs_market
    if include_needs:result['wanted_items']=list(dict.fromkeys(result['wanted_items']+needs_market.wanted_items(w,b)))
    return result

def change(w,a,b,amount,action):
    row=rel.bond(w,a,b)
    cap=min(society.bounds(w,a.group_id,b.group_id)[1],society.bounds(w,b.group_id,a.group_id)[1])
    row['trust']=max(-100,min(cap,row['trust']+amount))
    counts=row.setdefault('social_actions',{}).setdefault(a.id,{})
    counts[action]=counts.get(action,0)+1
    from engine import npc_life
    npc_life.event(w,b,action,max(-10,min(10,amount)),source=a.id)

def cooldown(w,a,b,action):
    row=rel.bond(w,a,b); now=living.state(w)['minute']
    key=a.id+':'+action; times=row.setdefault('social_times',{})
    if now-times.get(key,-1000000)<prefs(w,b,include_needs=False)['cooldown_minutes']:
        raise ValueError('Give them a little time before repeating that interaction.')
    times[key]=now

def notify(w,a,b,emotion,note='',response=None,lines=None):
    from engine.npc_activity import note as visible
    from engine import speech_bubbles, npc_emotions
    npc_emotions.context(w,a,partner=b,topic=None if lines else '')
    npc_emotions.context(w,b,partner=a,topic=None if lines else '')
    speech_bubbles.mark(a, b, emotion, response, lines)
    if lines and getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        tone,words,answer=lines
        if words:resident_watch.note(w,[a.id,b.id],f'{a.name} {tone} to {b.name}, “{words}”')
        if answer and response:resident_watch.note(w,[a.id,b.id],f'{b.name} replied, “{answer}”')
    for actor in (a,b):visible(actor,'social','In conversation')
    text=a.name+' → '+b.name+': '+EMOTIONS[emotion]+' '+emotion.replace('_',' ')
    if response:text+=' — '+b.name+' responds: '+EMOTIONS[response]+' '+response.replace('_',' ')
    if lines:
        tone,words,answer=lines
        text=f'{a.name} {tone} to {b.name}, “{words}”'
        if response:text+=f' {b.name} replies, “{answer}”'
    text+=note
    rel.event(w,text,[a.id,b.id])
    # The player receives the command response; only other viewers need a broadcast.
    excluded=a.id if a.is_player else b.id if b.is_player else None
    style={'role':'character' if a.is_player else 'npc','emphasis':'shout' if lines and lines[0] in ('shouts','yells') else 'alert' if lines and lines[0]=='calls out' else 'normal'}
    w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(a.location,text,excluded,style)])[-500:]
    return text


def emote(w,a,b,emotion,*,town_turn=None):
    if emotion not in EMOTIONS: raise ValueError('Choose one of the ten social emotions.')
    if b.is_player: raise ValueError('Use normal chat with other players.')
    if not rel.sentient(w,b): raise ValueError('Use treats and play with animals; social conversations require sentience.')
    from engine import livelihoods
    for person in (a,b):
        if not livelihoods.awake(w,person):raise ValueError(person.name+' is sleeping. Choose Wake NPC or return during waking hours.')
    if DELTAS[emotion]>0: gate(w,a,b,romantic=emotion=='in_love')
    elif not a.alive or not b.alive or a.location!=b.location: raise ValueError('Meet the NPC first.')
    from engine import npc_attention
    npc_attention.begin(w,a,b)
    cooldown(w,a,b,'emotion:'+emotion)
    # An autonomous conversation is an actual social experience, not evidence
    # that both participants feel whichever emoji the old rotation selected.
    change(w,a,b,DELTAS[emotion] if town_turn is None else 1,
           emotion if town_turn is None else 'conversation')
    from engine import needs_market
    if needs_market.applies(w,b) and DELTAS[emotion]>0:needs_market.relieve(b,'belonging',10)
    response='insulted' if emotion=='insulting' else 'angry' if DELTAS[emotion]<0 else emotion
    from engine import town_talk
    town_talk.meet(w,a,b)
    lines = town_talk.exchange(w,a,b,town_turn) if town_turn is not None else None
    return notify(w,a,b,emotion,response=response,lines=lines)

def wake(w,a,b):
    """Wake deliberately, without granting cooperation or changing working hours."""
    from engine import livelihoods, npc_attention
    if not a.alive or not b.alive or a.id==b.id or a.location!=b.location:
        raise ValueError('Meet the living NPC at the same location first.')
    if b.is_player or not rel.profile(w,b)['sentient']:
        raise ValueError('Choose a living sentient NPC to wake.')
    from engine import sleep_movement
    sleep_movement.scheduled_wake(w,b)
    if livelihoods.awake(w,b) and not sleep_movement.asleep(w,b):return b.name+' is already awake.'
    row=rel.bond(w,a,b)
    tolerant=society.friendliness(w,a,b)>=50 and (row['trust']>=50 or row['trust']>=0 and any(k in row['kinds'] for k in ('friend','lover','married','parent')))
    b.progress['awakened_until']=living.state(w)['minute']+livelihoods.WAKE_MINUTES
    b.activity='awake after being disturbed'
    npc_attention.begin(w,a,b)
    response='sleepy' if tolerant else 'irritated'
    before=row['trust']
    if not tolerant:
        # This interruption has a small cost even if diplomacy changed since the
        # bond formed; do not also collapse an old bond to a new faction cap.
        row['trust']=max(-100,before-2)
        counts=row.setdefault('social_actions',{}).setdefault(a.id,{})
        counts['wake']=counts.get('wake',0)+1
    text=a.name+' wakes '+b.name+'. '+EMOTIONS[response]+' '+b.name+(' is sleepy, but tolerates the interruption.' if tolerant else ' is irritated at being disturbed.')
    if row['trust']<before:text+=' Personal trust falls by '+str(before-row['trust'])+'.'
    text+=' They will stay awake briefly. Use Quest dialogue to ask for help; their usual faction, relationship and quest requirements still apply.'
    rel.event(w,text,[a.id,b.id])
    w.runtime_notifications=(getattr(w,'runtime_notifications',[])+[(a.location,text,a.id if a.is_player else None,{'role':'character' if a.is_player else 'npc','emphasis':'normal'})])[-500:]
    return text

def gift(w,a,b,iid):
    gate(w,a,b,gift=True)
    from engine import npc_attention
    npc_attention.begin(w,a,b)
    if not rel.profile(w,b)['sentient']: raise ValueError('Use companion treats for animals.')
    if iid not in a.inventory or iid not in w.items: raise ValueError('Carry that item first.')
    if iid in a.equipped.values(): raise ValueError('Unequip the item before offering it.')
    cfg=prefs(w,b); item=w.items[iid]
    wanted=(iid in cfg['wanted_items'] or item.get('type') in cfg['wanted_types']) and iid not in cfg['disliked_items'] and b.inventory.count(iid)<cfg['gift_limit']
    cooldown(w,a,b,'gift')
    if not wanted:
        change(w,a,b,-1,'gift_unwanted')
        return notify(w,b,a,'irritated',note=' — gift declined; you keep the item.')
    a.inventory.remove(iid);b.inventory.append(iid)
    change(w,a,b,5,'gift_wanted')
    from engine import needs_market
    if needs_market.applies(w,b):needs_market.use(w,b,iid)
    return notify(w,b,a,'excited',note=' — accepts '+item['name']+'.')

def quests(w,a,b):
    result=[]
    for q in w.quests.values():
        cfg=q.get('relationship_quest',{})
        if not cfg.get('enabled'):continue
        ident=q['id']+'|'+b.id
        progress=a.progress.get('bond_quests',{}).get(ident,{})
        reason=''
        try:
            gate(w,a,b,romantic=cfg.get('romantic',False),gift='gift_wanted' in cfg['goals'])
            if not rel.profile(w,b)['sentient']: raise ValueError('Requires a sentient NPC.')
            trust=rel.bond(w,a,b)['trust']
            # Upper bound is an entry requirement (e.g. reconciliation after a quarrel).
            if trust<cfg.get('minimum_trust',0) or not progress and trust>cfg.get('maximum_trust',100):
                raise ValueError('Personal trust is outside this quest’s standing range.')
        except ValueError as exc:reason=str(exc)
        counts=rel.bond(w,a,b).get('social_actions',{}).get(a.id,{})
        goals={k:max(0,counts.get(k,0)-progress.get('baseline',{}).get(k,0)) if progress else 0 for k in cfg['goals']}
        result.append(dict(id=q['id'],name=q['name'],description=q.get('description',''), status=progress.get('status','available'),blocked=reason,goals=cfg['goals'],progress=goals))
    return result

def quest(w,a,b,qid,action):
    row=next((r for r in quests(w,a,b) if r['id']==qid),None)
    if row is None:raise ValueError('Unknown relationship quest.')
    if row['blocked']:raise ValueError(row['blocked'])
    from engine import npc_attention
    npc_attention.begin(w,a,b)
    ident=qid+'|'+b.id; store=a.progress.setdefault('bond_quests',{})
    if action=='accept':
        if row['status']!='available':raise ValueError('That quest has already been accepted for this NPC.')
        store[ident]=dict(status='active',target=b.id,name=b.name,baseline=deepcopy(rel.bond(w,a,b).get('social_actions',{}).get(a.id,{})))
        return 'Relationship quest accepted with '+b.name+': '+row['name']+'.'
    if action!='complete' or row['status']!='active':raise ValueError('Accept the quest with this NPC first.')
    if any(row['progress'][k]<n for k,n in row['goals'].items()):raise ValueError('Complete the social objectives after accepting this quest.')
    change(w,a,b,w.quests[qid]['relationship_quest'].get('reward_trust',5),'quest_complete')
    store[ident]['status']='complete'
    from engine import progression
    advancement=progression.social(w,a,w.quests[qid],b)
    return 'Relationship quest complete: '+row['name']+'.'+('\n'+advancement if advancement else '')

def command(ctx,args):
    action,_,rest=args.strip().partition(' '); w,a=ctx.world,ctx.player
    if action in ('about','directions','relay','tell','showroute','headline','localnews','people','memories','work','activities','plans','creatures'):
        from engine import town_talk
        query, sep, who = rest.rpartition(' to ')
        if not sep and rest.startswith('to '): who, sep = rest[3:], True
        if not sep: raise ValueError('Choose a nearby resident to ask.')
        return town_talk.ask(w,a,target(w,a,who),action,query.strip())
    if action=='wake':return wake(w,a,target(w,a,rest))
    if action=='begin':
        from engine import npc_attention, livelihoods, npc_emotions
        b=target(w,a,rest)
        if not livelihoods.awake(w,b):return b.name+' is sleeping. Choose Wake NPC if you want to disturb them.'
        npc_attention.begin(w,a,b)
        npc_emotions.context(w,b,partner=a,topic='')
        from engine import town_talk
        town_talk.meet(w,a,b)
        return 'You approach '+b.name+'. Choose an expression, gift or quest conversation.'
    if action in ('emote','gift'):
        value,sep,who=rest.partition(' to ')
        if not sep or not who.strip():raise ValueError('Choose a nearby NPC before offering a gift or expressing an emotion.')
        if not value.strip():raise ValueError('Choose an item to offer or an emotion first.')
        b=target(w,a,who)
        return emote(w,a,b,value) if action=='emote' else gift(w,a,b,value)
    if action in ('accept','complete'):
        qid,sep,who=rest.partition(' with ')
        if not sep:raise ValueError('Use social '+action+' <quest name> with <person>.')
        from engine.player_names import pick
        person=target(w,a,who);chosen=pick(quests(w,a,person),qid,'relationship quest')
        return quest(w,a,person,chosen['id'],action)
    if action=='quests':
        return '\n'.join(r['name']+': '+r['status']+' '+(r['blocked'] or str(r['progress'])) for r in quests(w,a,target(w,a,rest)))
    raise ValueError('Use wake <NPC>, social emote/gift <value> to <NPC>, social quests <NPC>, or social accept/complete <quest> with <NPC>.')

def _resident_profile(w, b):
    """Project only this nearby person's authored fields, never remote identity.

    Relationship/household runtime records contain IDs and remote names. Those
    are deliberately not copied to the player packet or shown on a map.
    """
    from engine import population
    source = population.local_view(w, b)
    if not source or not source.get('enrolled'):
        return None
    result = {key: deepcopy(source[key]) for key in
              ('age_years', 'life_stage', 'adult', 'household_type',
               'household_role', 'marital_status', 'care_need', 'care_provision_unavailable')
              if key in source}
    education = source.get('education')
    if isinstance(education, dict):
        result['education'] = {key: deepcopy(education[key]) for key in
            ('enrollment', 'attainment', 'literacy', 'skills', 'provision') if key in education}
    health = source.get('health')
    if isinstance(health, dict) and health.get('fictional') is True:
        result['health'] = dict(fictional=True, mechanical_effects=False,
            conditions=[{key: deepcopy(row[key]) for key in ('label','support_notes') if key in row}
                        for row in health.get('conditions', []) if isinstance(row, dict)],
            support_notes=deepcopy(health.get('support_notes', [])))
    return result


def view(w,a):
    nearby=[e for e in w.entities_in_room(a.location) if not e.is_player and e.alive and rel.profile(w,e)['sentient']]
    from engine import needs_market,barter,livelihoods,life_stages,npc_emotions
    rows=[]
    for b in nearby:
        row=dict(id=b.id,name=b.name,adult=life_stages.for_entity(w,b)['adult'],awake=livelihoods.awake(w,b),commerce=barter.view(w,a,b),needs=needs_market.describe(w,b)+' '+livelihoods.summary(w,b),trust=rel.bond(w,a,b)['trust'],likes=', '.join([w.items.get(i,{}).get('name',i) for i in prefs(w,b)['wanted_items']]+prefs(w,b)['wanted_types']),quests=quests(w,a,b))
        row['expression']=npc_emotions.project(w,b)
        profile = _resident_profile(w,b)
        if profile is not None: row['population'] = profile
        rows.append(row)
    return dict(emotions=EMOTIONS,npcs=rows)

def nearby_conversations(w, turn):
    from collections import defaultdict
    from engine import livelihoods, resident_watch, speech_bubbles, town_talk, npc_emotions
    from engine.npc_activity import note
    rooms=defaultdict(list)
    audience=set()
    for person in w.entities.values():
        if not person.alive:continue
        if person.is_player:
            audience.add(person.location)
        elif rel.sentient(w,person):
            rooms[person.location].append(person)
    for room,occupants in rooms.items():
        if len(occupants)<2:continue
        offset=(turn+sum(room.encode()))%len(occupants)
        ordered=occupants[offset:]+occupants[:offset]
        eligible=[]
        for person in ordered:
            cfg=w.npcs.get(person.source_def,{})
            profile=cfg.get('social_profile',{})
            age=profile.get('age_years',25)
            if (person.spawner_key or '').startswith('birth:'):age=rel.profile(w,person).get('age_years',0)
            if ((isinstance(age,(int,float)) and age<3) or not livelihoods.awake(w,person)
                    or not person.alive or str(getattr(person,'activity','')).lower().startswith('sleep')):
                continue
            eligible.append(person)
        if len(eligible)<2:continue
        speaker=next((p for p in eligible if w.npcs.get(p.source_def,{}).get('social_profile',{}).get('autonomous',True)),None)
        if not speaker:continue
        listener=next((p for p in eligible if p is not speaker and society.friendliness(w,speaker,p)>=50),None)
        if not listener:continue
        town_talk.meet(w,speaker,listener)
        lines=town_talk.exchange(w,speaker,listener,turn)
        if not lines:
            topics=getattr(w,'chronicles',{}).get('ambient_dialogue',[])
            words,answer=topics[(turn+offset)%len(topics)] if topics else speech_bubbles.WORDS['happy']
            lines=('says',words,answer)
        tone,words,answer=lines
        npc_emotions.context(w,speaker,partner=listener)
        npc_emotions.context(w,listener,partner=speaker)
        speech_bubbles.mark(speaker,listener,'serious','happy',lines)
        for p in (speaker,listener):note(p,'social','In conversation',7)
        statement=f'{speaker.name} {tone} to {listener.name}, “{words}” {listener.name} replies, “{answer}”'
        if room in audience:
            if not hasattr(w,'runtime_notifications'):w.runtime_notifications=[]
            w.runtime_notifications.append((room,statement,None,{'role':'npc','emphasis':'shout' if tone in ('shouts','yells') else 'alert' if tone=='calls out' else 'normal'}))
        if living.state(w).get('resident_watches'):
            resident_watch.note(w,[speaker.id,listener.id],statement)


def advance(w):
    s=living.state(w);hour=s['minute']//60
    turn=s['minute']//12
    if s.get('last_conversation_turn')!=turn:
        s['last_conversation_turn']=turn
        if s.get('last_emoji_hour')==hour:
            nearby_conversations(w,turn)
    if s.get('last_emoji_hour')==hour:return
    s['last_emoji_hour']=hour;used=set()
    from engine import livelihoods
    for a in list(w.entities.values()):
        if a.is_player or not a.alive or a.id in used:continue
        profile=rel.profile(w,a)
        if not profile['sentient'] or not profile['autonomous']:continue
        # emote requires both participants to be awake, even when an owed
        # reply reverses the speaker. Skip doomed scans before copying prefs.
        try:
            if not livelihoods.awake(w,a):continue
        except ValueError:continue
        neighbors = w.entities_in_room(a.location)
        offset = hour % len(neighbors) if neighbors else 0
        neighbors = neighbors[offset:] + neighbors[:offset]
        errands = a.progress.get('town_talk', {}).get('errands', {})
        def owes_reply(person):
            return a.id in person.progress.get('town_talk', {}).get('errands', {})
        neighbors.sort(key=lambda person: not (person.id in errands or owes_reply(person)))
        for b in neighbors:
            if b.id==a.id or b.is_player or b.id in used or not rel.sentient(w,b):continue
            try:
                if not livelihoods.awake(w,b):continue
            except ValueError:continue
            speaker, listener = (b,a) if owes_reply(b) else (a,b)
            options=prefs(w,speaker,include_needs=False)['emotions']
            if not options:continue
            try:emote(w,speaker,listener,options[hour%len(options)],town_turn=hour)
            except ValueError:continue
            used.update((a.id,b.id));break

def register(reg):
    from engine.commands import Command
    from engine import livelihoods
    reg.register(Command('social','NPC emotions, gifts and relationship quests','social <action>',command,available=lambda ctx:society.enabled(ctx.world),example='social emote happy to chef_ragnar'))
    reg.register(Command('wake','Deliberately wake a nearby sleeping NPC','wake <NPC name or ID>',lambda ctx,args:wake(ctx.world,ctx.player,target(ctx.world,ctx.player,args)),available=lambda ctx:livelihoods.wake_available(ctx.world,ctx.player),example='wake chef_ragnar'))

def validate(data):
    from engine import npc_life
    issues=npc_life.validate(data);items={i['id'] for i in data.get('item',[])}
    for n in data.get('npc',[]):
        duration=n.get('interaction_pause_seconds',15)
        if type(duration) is not int or not 1<=duration<=300:issues.append(n['id']+': interaction pause must be 1–300 real seconds')
        cfg=n.get('gift_preferences',{})
        if not isinstance(cfg,dict):issues.append(n['id']+': invalid gift preferences');continue
        cfg={**PREFERENCES,**cfg}
        for field in ('wanted_items','disliked_items'):
            if not isinstance(cfg[field],list) or any(i not in items for i in cfg[field]):issues.append(n['id']+': invalid '+field)
        if not isinstance(cfg['wanted_types'],list) or any(not isinstance(i,str) for i in cfg['wanted_types']):issues.append(n['id']+': invalid wanted_types')
        if not isinstance(cfg['emotions'],list) or any(e not in EMOTIONS for e in cfg['emotions']):issues.append(n['id']+': invalid emotions')
        from engine.speech_bubbles import valid_phrase
        from engine.town_talk import VOICES
        authored = cfg.get('everyday_lines', {})
        if not isinstance(authored, dict) or any(k not in VOICES or not valid_phrase(v) for k,v in authored.items()):
            issues.append(n['id'] + ': everyday speech must use a known situation and 1–3 words (30 characters maximum).')
        phrases = cfg.get('speech_lines', {})
        if not isinstance(phrases, dict) or any(k not in EMOTIONS or not valid_phrase(v) for k, v in phrases.items()):
            issues.append(n['id'] + ': speech lines must use known emotions and 1–3 words (30 characters maximum).')
        for f in ('gift_limit','cooldown_minutes'):
            if type(cfg[f]) is not int or cfg[f]<1:issues.append(n['id']+': '+f+' must be positive')
    for q in data.get('quest',[]):
        cfg=q.get('relationship_quest',{})
        if not isinstance(cfg,dict):issues.append(q['id']+': invalid relationship quest');continue
        if not cfg.get('enabled'):continue
        cfg={**QUEST_DEFAULT,**cfg}
        if type(cfg['romantic']) is not bool:issues.append(q['id']+': romantic must be boolean')
        if any(type(cfg[f]) is not int or not -100<=cfg[f]<=100 for f in ('minimum_trust','maximum_trust','reward_trust')):issues.append(q['id']+': invalid trust range')
        elif cfg['minimum_trust']>cfg['maximum_trust']:issues.append(q['id']+': reversed trust range')
        if not isinstance(cfg['goals'],dict) or not cfg['goals'] or any(k not in set(EMOTIONS)|{'gift_wanted'} or type(v) is not int or v<1 for k,v in cfg['goals'].items()):issues.append(q['id']+': invalid social goals')
    return issues
