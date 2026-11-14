"""Witnessed accusations, a magistrate's hearing and finite custodial sentences."""
from engine import living, regional_world, relationships

KEY='city_justice_v1'
JUDGES=('Rowan Alder','Mira Vale','Tamsin Reed','Ilan Sedge','Neris Flint','Orin Glass','Ada Pine','Soren Star')


def state(w):
    return living.state(w).setdefault(KEY,{'cases':{},'history':[],'last':-1})


def install(w):
    if regional_world.config(w,'courts',True) is False:
        return
    w.city_courts={}
    for index,city in enumerate(regional_world.cities(w)):
        slug=regional_world.key(city['name']);base='rg_'+slug+'_court';cell=base+'_jail'
        regional_world.add_room(w,base,city['name']+' Magistrates Court',
            'A public magistrate hears witnessed accusations here. An arrest is an accusation, not a conviction. '
            'The court reviews the recorded act, named witnesses and the defendant before deciding guilt. '
            'A posted notice gives each defendant the hearing and any release time. The city lies out.',
            city,x=2,y=-2,floor=30+index,facilities=('court','library'),justice_city=city['name'])
        regional_world.add_room(w,cell,city['name']+' Civic Jail',
            'Individual cells contain a bed, drinking water and a small washstand. '
            'Only a recorded guilty verdict starts a custodial sentence. The watch releases prisoners when their sentence ends.',
            city,x=3,y=-2,floor=30+index,facilities=('jail','inn'),justice_city=city['name'])
        if not regional_world.connect(w,city['home'],'court',base,'out'):
            regional_world.connect(w,city['home'],'magistrates court',base,'out')
        regional_world.connect(w,base,'jail',cell,'out')
        ident=base+'_magistrate'
        w.npcs.setdefault(ident,dict(id=ident,name='Magistrate '+JUDGES[index%len(JUDGES)],
            description='An appointed judge who hears evidence and records verdicts and finite sentences.',
            hp=30,attack=2,defense=4,gold=0,group=city.get('group'),spawn_room=base,location=base,
            profession='judge',social_profile={'sentient':True,'species':'human','age_years':42},
            dialogue='I hear evidence before passing sentence. A watch report must name the act and its witnesses.',
            regional_generated=True))
        w.city_courts[city['name']]=dict(court=base,jail=cell,release=city['home'],judge=ident,authority=city.get('group'))
    # Official city rooms without an authored law choice use the civic courts.
    # Explicit disabled or customized laws remain authoritative.
    for rid,details in w.room_details.items():
        if 'laws' in details or details.get('open_country') or details.get('environment') in ('wilderness','cave'):
            continue
        court=court_for(w,rid)
        if court and w.rooms[rid].group==court['authority']:
            details['laws']={'enabled':True,'authority':court['authority'],'arrest_room':court['court'],
                             'fine':5,'guard_radius':1,'traffic_reduction':.8}


def court_for(w,room):
    city=regional_world.city_for(w,room)
    return getattr(w,'city_courts',{}).get(city['name']) if city else None


def confined(w,actor):
    case=state(w)['cases'].get(actor.id)
    return bool(case and case.get('status') in ('awaiting_hearing','sentenced'))


def blocked(w,actor,destination):
    case=state(w)['cases'].get(actor.id)
    if not case:
        return ''
    now=int(living.state(w)['minute'])
    if case['status']=='awaiting_hearing' and destination!=case['court']:
        return 'The watch is keeping you at court for a hearing in '+str(max(0,case['hearing_at']-now))+' game minutes.'
    if case['status']=='sentenced' and now<case['release_at'] and destination!=case['jail']:
        return 'The judge’s sentence has '+str(case['release_at']-now)+' game minutes remaining.'
    return ''


def apprehend(w,suspect,guard,report):
    """Return True when this supplement accepts the accusation for a hearing."""
    court=court_for(w,report.get('room'))
    if not court or not relationships.sentient(w,suspect):
        return False
    now=int(living.state(w)['minute'])
    if confined(w,suspect):
        return True
    case=dict(court,actor=suspect.id,name=suspect.name,origin=suspect.location,
              accusation=report.get('kind','assault'),victim=report.get('victim'),reported=report.get('reported'),
              witnesses=list(report.get('witnesses',[])),evidence=list(report.get('evidence',[])),
              arresting_officer=guard.id,status='awaiting_hearing',arrested=now,hearing_at=now+2)
    state(w)['cases'][suspect.id]=case
    suspect.progress['restrained_until']=now+3
    suspect.progress['court_case']=dict(status='awaiting_hearing',hearing_at=now+2,court=court['court'])
    w.move_entity(suspect.id,court['court'],forced=True)
    regional_world.notice(w,suspect,guard.name+' takes you to '+w.rooms[court['court']].name+
                          ' on a witnessed '+case['accusation']+' accusation. No guilt or fine has been decided. The hearing begins in 2 game minutes.',room=court['court'])
    from engine import gazette
    gazette.record(w,case['origin'],'Watch',guard.name+' brought '+suspect.name+' before the magistrate on a '+case['accusation']+' accusation; a verdict is pending.',byline='Court reporter')
    return True


def _publish(w,actor,case,text):
    regional_world.notice(w,actor,text,room=actor.location)
    from engine import gazette
    gazette.record(w,case['release'],'Watch',text,byline='Court reporter')


def advance(w):
    if not getattr(w,'city_courts',None):
        return
    s=state(w);now=int(living.state(w)['minute'])
    if s['last']==now:
        return
    s['last']=now
    for ident,case in list(s['cases'].items()):
        actor=w.entities.get(ident)
        if actor is None:
            continue  # An offline player keeps the persisted case until loaded.
        if not actor.alive:
            case['status']='closed_deceased'
        elif case['status']=='awaiting_hearing' and now>=case['hearing_at']:
            judge=next((e for e in w.entities_in_room(case['court']) if e.alive and e.source_def==case['judge']),None)
            if judge is None and now-case['arrested']<15:
                case['hearing_at']=now+1
                continue
            # Evidence is a retained witnessed act, not a faction score or random verdict.
            evidence=[e for e in case.get('evidence',[]) if e.get('actor')==ident
                      and e.get('victim')==case.get('victim') and e.get('kind')==case['accusation']
                      and e.get('witnesses') and set(e['witnesses']) & set(case['witnesses'])]
            guilty=bool(judge and evidence)
            if guilty:
                sentence=max(1,min(1500,int(regional_world.config(w,'assault_sentence_minutes',30))))
                fine=max(0,min(100,int(regional_world.config(w,'assault_fine',5))))
                paid=min(actor.gold,fine);actor.gold-=paid
                case.update(status='sentenced',verdict='guilty',verdict_at=now,release_at=now+sentence,fine_paid=paid)
                actor.progress['restrained_until']=now+sentence
                actor.progress['court_case']=dict(status='sentenced',release_at=now+sentence,jail=case['jail'],verdict='guilty')
                w.move_entity(actor.id,case['jail'],forced=True)
                _publish(w,actor,case,judge.name+' finds '+actor.name+' guilty of witnessed '+case['accusation']+' after reviewing '+str(len(case['witnesses']))+
                         ' named witness report(s). Sentence: '+str(sentence)+' game minutes in '+w.rooms[case['jail']].name+
                         ' and '+str(paid)+' gold paid. Release is at world minute '+str(now+sentence)+'.')
            else:
                case.update(status='dismissed',verdict='not_proven',verdict_at=now)
                actor.progress.pop('court_case',None);actor.progress['restrained_until']=now
                w.move_entity(actor.id,case['release'],forced=True)
                _publish(w,actor,case,('The magistrate dismisses the accusation against ' if judge else 'The watch releases ')+actor.name+
                         (' because no sufficient witnessed act is recorded. No fine or sentence is imposed.' if judge else ' because no judge is available for a timely hearing. No fine or sentence is imposed.'))
        elif case['status']=='sentenced' and now>=case['release_at']:
            case['status']='released';case['released_at']=now
            actor.progress.pop('court_case',None);actor.progress['restrained_until']=now
            w.move_entity(actor.id,case['release'],forced=True)
            _publish(w,actor,case,actor.name+' has completed the judge’s sentence and is released from '+w.rooms[case['jail']].name+'.')
        if case['status'] not in ('awaiting_hearing','sentenced'):
            s['history']=(s['history']+[dict(case)])[-100:]
            del s['cases'][ident]
