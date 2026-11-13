"""Bounded player rest. Only authoritative simulation time earns recovery.

Progress is saved with the player; an ephemeral token prevents old/offline saved
sessions from earning recovery. Disconnect/resume interrupts, never catches up.
"""
from engine.item_catalog import counted
import uuid

KEY = 'player_rest'
MAX_MINUTES = 1500  # One 25-hour Expanse day.
READONLY = {'look','map','inventory','score','status','help','standing','workshop',
    'provenance','survey','recipes','catalog','wardrobe','materials','quests',
    'adventures','market','journal','condition','time','inspect','spells',
    'companions','services','route','guide','track','untrack','save','atlas',
    'rest','sleep','wait','tradeactive','tradeview','tradeclose','tradecancel'}


def dirty(w,p):
    if p.is_player:
        w.dirty_players=getattr(w,'dirty_players',set())|{p.id}


def active(p):
    row=p.progress.get(KEY)
    return row if isinstance(row,dict) and row.get('state')=='active' else None


def signal(p,reason):
    """Core damage hook: delay messaging until engine has its world context."""
    row=active(p)
    if row:row['interrupted']=str(reason)[:100]


def _notify(w,p,text):
    if getattr(w,'realtime',False) or getattr(w,'deferred_rest',False):
        w.rest_notifications=getattr(w,'rest_notifications',[])+[(p.id,text)]


def cancel(w,p,reason,notify=True):
    row=active(p)
    if not row:return ''
    elapsed=row.get('elapsed',0)
    if type(elapsed) is not int or not 0<=elapsed<=MAX_MINUTES:elapsed=0
    text=f'Your rest was interrupted after {counted(elapsed,"minute")}: {reason}.'
    p.progress[KEY]={'state':'interrupted','elapsed':elapsed,'message':text}
    p._rest_token=None
    if getattr(p,'activity','') in ('resting','sleeping'):p.activity='awake'
    dirty(w,p)
    if notify:_notify(w,p,text)
    return text


def canonical(w,command,registry=None,*,resolve_shortcuts=True):
    words=command.strip().split(maxsplit=1)
    verb=words[0].lower() if words else ''
    args=words[1] if len(words)>1 else ''
    expansion=getattr(w,'shortcuts',{}).get(verb) if resolve_shortcuts else None
    if expansion:
        words=(expansion+(' '+args if args else '')).split(maxsplit=1)
        verb=words[0].lower() if words else '';args=words[1] if len(words)>1 else ''
    resolved=registry.resolve(verb) if registry is not None else None
    return (resolved.name if resolved else verb),args.lower()


def before_command(w,p,command,registry=None,*,resolve_shortcuts=True):
    if not p or not active(p):return
    from engine import sleep_movement
    if sleep_movement.asleep(w,p):return
    if registry is not None:verb,args=canonical(w,command,registry,resolve_shortcuts=resolve_shortcuts)
    else:
        words=command.strip().split(maxsplit=1)
        verb=words[0].lower() if words else '';args=words[1].lower() if len(words)>1 else ''
    if verb in READONLY or (verb=='wake' and args.strip() in ('','self','me')):return
    if verb=='ui' and args.split(' ',1)[0] in ('list','focus','navigation','gazette'):return
    cancel(w,p,'you began another action')


def resume(w,p):
    return cancel(w,p,'the character session resumed; offline time does not count',notify=False)


def shelter_problem(w,p):
    from engine import living,geology_impacts
    if not p.alive or p.progress.get('permanently_dead'):return 'you are unconscious or dead'
    if p.location not in w.rooms:return 'your resting place is unavailable'
    if geology_impacts.room_unusable(w,p.location):return 'this shelter is temporarily unusable'
    details=living.details(w,p.location)
    camp=living.state(w)['camps'].get(p.id,{})
    from engine import property_interiors
    if 'inn' not in details.get('facilities',[]) and camp.get('room')!=p.location and not property_interiors.home_shelter(w,p):
        return 'rest at an inn or tavern with lodging, or your pitched tent (not every building provides lodging)'
    if any(not e.is_player and w.npcs.get(e.source_def,{}).get('disposition')=='hostile'
           for e in w.entities_in_room(p.location)):
        return 'hostile creatures prevent resting'
    return ''


def _valid(row):
    fields=('duration','elapsed','last_minute','hp','mana','injury','hp_rate','mana_rate','injury_rate')
    return (row.get('version')==1 and row.get('kind') in ('resting','sleeping') and all(type(row.get(k)) is int for k in fields)
        and 1<=row['duration']<=MAX_MINUTES and 0<=row['elapsed']<row['duration']
        and all(0<=row[k]<=10**9 for k in fields if k not in ('duration','elapsed'))
        and isinstance(row.get('room'),str) and isinstance(row.get('token'),str))


def status(w,p):
    row=active(p)
    if row:
        if not _valid(row) or getattr(p,'_rest_token',None)!=row.get('token'):
            return cancel(w,p,'a saved session cannot resume automatically',notify=False)
        if row.get('interrupted'):
            return cancel(w,p,row['interrupted'],notify=False)
        return (f"You are {row['kind']}: {row['elapsed']} of {counted(row['duration'],'minute')} elapsed, "
            f"{row['duration']-row['elapsed']} remaining. Use rest stop or wake self to stop. "
            + ('The shared world clock continues normally.' if getattr(w,'realtime',False) else 'Time advances in small steps; you can stop at any time.') if (getattr(w,'realtime',False) or getattr(w,'deferred_rest',False)) else
            f"Rest: {row['elapsed']} of {counted(row['duration'],'minute')} elapsed.")
    previous=p.progress.get(KEY,{})
    return previous.get('message','You are not resting.') if isinstance(previous,dict) else 'You are not resting.'


def command(w,p,args,kind):
    from engine import living
    value=args.strip().lower()
    if value in ('stop','cancel'):
        return cancel(w,p,'you woke up',notify=False) or 'You are not resting.'
    if value=='status':return status(w,p)
    if active(p):return status(w,p)  # Never reset/reward a repeated start request.
    try:duration=int(value or '60')
    except (ValueError,TypeError):return f'Use {kind} [1–1500 minutes], {kind} status, or {kind} stop.'
    if not 1<=duration<=MAX_MINUTES:return 'Rest or sleep between 1 and 1500 minutes at a time.'
    problem=shelter_problem(w,p)
    if problem:return problem[0].upper()+problem[1:]+'.'
    pr=living.progress(p);now=living.state(w)['minute'];token=uuid.uuid4().hex
    target=max(1,p.max_hp-pr['disease']//5)
    row={'version':1,'state':'active','kind':'sleeping' if kind=='sleep' else 'resting',
        'room':p.location,'duration':duration,'elapsed':0,'last_minute':now,'token':token,
        'hp':p.hp,'mana':pr['mana'],'injury':pr['injury'],
        'hp_rate':max(0,target-p.hp),'mana_rate':max(0,pr['max_mana']-pr['mana']),
        'injury_rate':min(5,pr['injury'])}
    p.progress[KEY]=row;p._rest_token=token;p.activity=row['kind'];dirty(w,p)
    if getattr(w,'realtime',False) or getattr(w,'deferred_rest',False):return status(w,p)
    # Small bounded steps retain the real simulation and check danger repeatedly.
    while active(p):
        step=min(5,row['duration']-row['elapsed']);before=living.state(w)['minute']
        living.advance(w,step)
        if active(p) and living.state(w)['minute']<=before:
            cancel(w,p,'the world clock did not advance safely',notify=False)
    return status(w,p)


def advance(w,minutes):
    from engine import living,quest_progress
    if getattr(w,'realtime',False) and not getattr(w,'tick_authorized',False):return
    now=living.state(w)['minute']
    for p in list(w.entities.values()):
        row=active(p)
        if not p.is_player or not row:continue
        if not _valid(row) or getattr(p,'_rest_token',None)!=row.get('token'):
            cancel(w,p,'a saved session cannot resume automatically');continue
        problem=row.get('interrupted') or shelter_problem(w,p)
        if p.location!=row['room']:problem='you left your resting place'
        pr=living.progress(p)
        if p.hp<row['hp'] or pr['injury']>row['injury']:problem='you were hurt'
        if pr['mana']!=row['mana'] or p.hp!=row['hp'] or pr['injury']!=row['injury']:
            problem=problem or 'your condition changed during rest'
        if problem:cancel(w,p,problem);continue
        if type(minutes) is not int or minutes<=0 or row['last_minute']!=now-minutes:
            cancel(w,p,'the world clock changed outside this resting session');continue
        old=row['elapsed'];elapsed=min(row['duration'],old+minutes)
        # One full safe hour grants the previous rest recovery. Shorter actual
        # durations earn only proportional recovery, not a fresh full heal.
        gain=lambda rate: rate*elapsed//60-rate*old//60
        hp=max(0,min(gain(row['hp_rate']),max(1,p.max_hp-pr['disease']//5)-p.hp))
        living.heal(w,p,hp)
        pr['mana']=min(pr['max_mana'],pr['mana']+gain(row['mana_rate']))
        pr['injury']=max(0,pr['injury']-gain(row['injury_rate']))
        row.update(elapsed=elapsed,last_minute=now,hp=p.hp,mana=pr['mana'],injury=pr['injury'])
        dirty(w,p)
        if elapsed>=row['duration']:
            text=f'You rest for {counted(elapsed,"minute")}. Health and mana recover. Illness may limit recovery.'
            p.progress[KEY]={'state':'complete','elapsed':elapsed,'message':text}
            p._rest_token=None;p.activity='awake'
            quest_progress.action(p,'rest')
            if row['kind']=='sleeping':quest_progress.action(p,'sleep')
            _notify(w,p,text)
        elif (getattr(w,'realtime',False) or getattr(w,'deferred_rest',False)) and elapsed//15>old//15:
            _notify(w,p,status(w,p))
