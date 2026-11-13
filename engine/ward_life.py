"""An inhabited ward with witnessed incidents, private lives and scarce beds."""
from engine import gazette
from engine.wildlands import record,link,definition

def room(w,key):
    return w.rules['ward']['prefix'] + key

def actor(w,key):
    return w.entities.get('npc:' + room(w,key))

def state(w):
    return w.living_state.setdefault('lantern_district',{'cases':[],'beds':{},'queue':list(w.rules['ward']['waiting']),'last':''})

def move(w,a,r):
    if a and a.alive and a.location!=r:w.move_entity(a.id,r)

def action(w,who,words):
    if who and who.alive:
        who.activity=words
        from engine import resident_watch
        resident_watch.note(w,[who.id],who.name+' is '+words+'.')

def advance(w,before,now):
    if not w.rules.get("ward"):return
    first=before//30+1;last=now//30
    if first>last:return
    s=state(w)
    from engine import relationships,life_stages
    if not s.get('founding_household'):
        guest,partner=actor(w,'guest'),actor(w,'partner')
        if guest and partner:
            initial=relationships.bond(w,guest,partner)
            if 'married' not in initial['kinds']:initial['kinds'].append('married')
            initial['trust']=max(45,initial['trust']);s['founding_household']=True
    for period in range(max(first,last-49),last+1):
        k=period%12
        if k in (0,6):
            helper=actor(w,'relief')
            if helper and helper.alive:
                # A longer let frees the cottage when a resident secures a tenancy.
                occupant=s.get('cottage')
                if occupant and period>=occupant['until']:
                    tenant=actor(w,occupant['who'])
                    if tenant and tenant.alive:
                        tenant.progress['home_room']=room(w,'rooms');move(w,tenant,room(w,'rooms'));action(w,tenant,'moving into a rented room')
                    s.pop('cottage',None)
                for key,end in list(s['beds'].items()):
                    if end<=period:
                        del s['beds'][key]
                        if not s.get('cottage'):
                            s['cottage']={'who':key,'until':period+100}
                            move(w,actor(w,key),room(w,'bridge'))
                        else:
                            move(w,actor(w,key),room(w,'quay'));s['queue'].append(key)
                while s['queue'] and len(s['beds'])<3:
                    key=s['queue'].pop(0);person=actor(w,key)
                    if person and person.alive:
                        s['beds'][key]=period+50;move(w,person,room(w,'refuge'));action(w,person,'settling into a transitional bed')
                action(w,helper,'serving meals and keeping the bed register')
                s['last']='The kitchen served supper. '+str(len(s['queue']))+' residents are waiting for a bed.'
        elif k in (3,9):
            offender=actor(w,'dealer' if k==3 else 'runner');other=actor(w,'porter');witness=actor(w,'watch1')
            if not all(a and a.alive for a in (offender,other,witness)):continue
            for a in (offender,other,witness):move(w,a,room(w,'yard'))
            if len({a.location for a in (offender,other,witness)})!=1:continue
            event=w.rules['ward']['sale'] if k==3 else 'an assault on '+other.name
            if k==9:other.take_damage(1)
            action(w,witness,'taking a witness statement')
            s['cases'].append(dict(incident=event,person=offender.name,accused=offender.id,other=other.id,witness=witness.name,when=period,status='reported'))
            s['cases']=s['cases'][-16:]
            gazette.record(w,room(w,'yard'),'Watch',witness.name+' reported '+event+ ' at ' + w.rooms[room(w,'yard')].name + '.',key='lantern case '+str(period))
        elif k in (4,10):
            detective=actor(w,'detective')
            if detective and detective.alive:
                case=next((c for c in s['cases'] if c['status']=='reported'),None)
                if case:
                    move(w,detective,room(w,'yard'))
                    if detective.location==room(w,'yard'):
                        case['status']='witness interviewed';action(w,detective,'investigating '+case['incident'])
                        second=w.entities.get(case.get('other'));constable=actor(w,'watch2')
                        subject=w.entities.get(case.get('accused'))
                        if second and second.alive and second.location==detective.location and constable and constable.alive and subject and subject.alive:
                            move(w,constable,room(w,'yard'))
                            if subject.location==constable.location==detective.location:
                                case['status']='referred to the magistrate'
                                subject.progress['restrained_until']=now+10
                                action(w,constable,'escorting '+subject.name+' to the magistrate')
                                move(w,subject,room(w,'court'))
                                gazette.record(w,room(w,'court'),'Watch',detective.name+' referred the witnessed case to the magistrate.',key='lantern hearing '+str(period))
        else:
            who,place,act=w.rules['ward']['activities'][str(k)]
            a=actor(w,who)
            if a and a.alive:
                move(w,a,room(w,place))
                if k==11:
                    partner=actor(w,'partner');companion=actor(w,'companion')
                    if not all(b and b.alive for b in (partner,companion)) or a.location!=companion.location:continue
                    if not all(life_stages.for_entity(w,b)['adult'] and relationships.profile(w,b)['romance_enabled'] for b in (a,companion)):continue
                    marriage=relationships.bond(w,a,partner)
                    if 'married' not in marriage['kinds'] or marriage.get('deceased') or relationships.related(w,a.id,companion.id):continue
                    if a.gold>=1:
                        a.gold-=1;companion.gold+=1
                    marriage['trust']=max(-100,marriage['trust']-1)
                action(w,a,act)
                if k==2:
                    opponent=actor(w,'publican')
                    if opponent and opponent.alive and opponent.location==a.location:
                        payer,winner=(a,opponent) if (period//12)%2 else (opponent,a)
                        if payer.gold:payer.gold-=1;winner.gold+=1
                if k==7:a.progress['intoxication']=min(100,a.progress.get('intoxication',0)+3)
                if k==1:
                    for key in ('farmer','publican'):
                        for item in w.shop_state.get(room(w,key),{}):
                            w.shop_state[room(w,key)][item]=min(10,w.shop_state[room(w,key)][item]+1)

def command(ctx,args):
    w,p=ctx.world,ctx.player;s=state(w)
    if p.location==w.rules['ward']['gate'] and args.strip().lower()=='visit':
        from engine import frontiers
        steps=frontiers.path(w,p.location,room(w,'court'),p)
        if not steps:return 'The road to the ward is closed.'
        return 'The public road leads to '+w.rooms[room(w,'court')].name+'. Your next step is '+steps[0][1]+'.'
    if p.location==room(w,'court'):
        return '\n'.join([w.rooms[p.location].description]+[c['incident'].capitalize()+' · '+c['status']+' · witness '+c['witness'] for c in s['cases'][-4:]])
    if p.location==room(w,'bridge'):
        return w.rooms[p.location].name+' · '+('Occupied by '+actor(w,s['cottage']['who']).name if s.get('cottage') and actor(w,s['cottage']['who']) else 'Awaiting a referral from '+w.rooms[room(w,'refuge')].name+'.')
    if p.location==room(w,'refuge'):
        return f"Three transitional beds. {len(s['beds'])} occupied. {len(s['queue'])} residents waiting. "+s['last']
    if p.location.startswith(w.rules['ward']['prefix']):return w.rooms[p.location].description
    return w.rules['ward']['name']+' opens off '+w.rooms[w.rules['ward']['gate']].name+'.'
