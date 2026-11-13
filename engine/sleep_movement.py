"""Sleep is a movement constraint, not a hidden automatic wake action."""

def asleep(world, entity):
    from engine import resting
    if entity.is_player:
        row=resting.active(entity)
        return bool(row and row.get('kind')=='sleeping')
    return str(getattr(entity,'activity','')).lower().startswith('sleeping')


def wake(world, entity, reason):
    from engine import resting, living
    if entity.is_player:
        resting.cancel(world,entity,reason)
    else:
        entity.activity='awake: '+reason
        # Emergency waking is bounded and does not make a closed shop open.
        entity.progress['awakened_until']=living.state(world)['minute']+30


def scheduled_wake(world, entity):
    if entity.is_player:return
    if getattr(entity,'_sleep_damage',False):
        entity._sleep_damage=False
        wake(world,entity,'you were hurt');return
    if not asleep(world,entity):return
    from engine import livelihoods, living, worldtime
    if livelihoods.population_member(entity) or livelihoods.applies(world,entity):
        if livelihoods.awake(world,entity):entity.activity='awake'
        return
    schedule=world.npcs.get(entity.source_def,{}).get('schedule',[])
    now=living.state(world)['minute'];weekday=worldtime.date(now)['weekday']
    rows=sorted([r for r in schedule if not r.get('weekdays') or weekday in r['weekdays']],key=lambda r:r['hour']*60+r.get('minute',0))
    if rows:
        current=next((r for r in reversed(rows) if r['hour']*60+r.get('minute',0)<=now%worldtime.MINUTES_PER_DAY),rows[-1])
        if not str(current.get('activity','')).startswith('sleep'):entity.activity='awake'


def blocked_command(world, entity, command, registry=None, *, resolve_shortcuts=True):
    from engine import resting
    if not entity or not asleep(world,entity):return ''
    row=resting.active(entity)
    if not entity.alive:
        resting.cancel(world,entity,'you are unconscious or dead');return ''
    if row and row.get('interrupted'):
        resting.cancel(world,entity,row['interrupted']);return ''
    verb,args=resting.canonical(world,command,registry,resolve_shortcuts=resolve_shortcuts)
    if verb in resting.READONLY | {'resume','save_exit','quit'} or (verb=='wake' and args.strip() in ('','self','me')):return ''
    if verb=='ui' and args.split(' ',1)[0] in ('list','focus','navigation','gazette'):return ''
    return 'You are sleeping. Wake up with wake self or sleep stop before moving or acting.'
