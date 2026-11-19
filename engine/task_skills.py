"""Persistent practice for real player and NPC work, separate from character XP."""
from hashlib import sha256
from math import isfinite
import re

KEY = 'task_practice_v1'
NAMES = {
    'burglary':'Burgling','observation':'Observation','lockpicking':'Lockpicking',
    'farming':'Farming','ranching':'Ranching','fieldcraft':'Fieldcraft','mining':'Mining',
    'fishing':'Fishing','crafting':'Crafting','cooking':'Cooking','brewing':'Brewing',
    'trading':'Trading','repairing':'Repairing','journalism':'Journalism','reading':'Reading','writing':'Writing','teaching':'Teaching',
    'spellcraft':'Spellcraft','fighting':'Fighting','healing':'Healing',
    'singing':'Singing','poetry':'Poetry','painting':'Painting','sculpture':'Sculpture',
    'architecture':'Architecture','assassination':'Assassination',
}
TASK = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
TOKEN = re.compile(r'^[0-9a-f]{64}$')


def finite(value):
    return type(value) in (int,float) and -1e12 <= value <= 1e12 and isfinite(value)


def validate_saved(progress):
    """Reject damaged practice records at save/load boundaries."""
    if not isinstance(progress,dict):raise ValueError('Invalid character progress.')
    rows=progress.get(KEY,{})
    if not isinstance(rows,dict) or len(rows)>256:raise ValueError('Invalid saved task practice.')
    for task,row in rows.items():
        if not isinstance(task,str) or not TASK.fullmatch(task) or not isinstance(row,dict):
            raise ValueError('Invalid saved task practice record.')
        xp=row.get('xp',0);attempts=row.get('attempts',0);minute=row.get('last_minute',0)
        events=row.get('events',[])
        if (not finite(xp) or not 0<=xp<threshold(100) or type(attempts) is not int
                or not 0<=attempts<=1_000_000 or not finite(minute) or minute<0
                or not isinstance(events,list) or len(events)>128
                or any(not isinstance(token,str) or not TOKEN.fullmatch(token) for token in events)):
            raise ValueError('Invalid saved task practice: '+task)


def threshold(level):
    """Game-balance curve: each successive level requires more practice."""
    return 10 + 2*level + level*level//20


def level(world, actor, task):
    if task in ('burglary','observation'):
        from engine import burglary
        return burglary.skill(world,actor,task)
    if task == 'lockpicking':
        from engine import locks
        return locks.skill(world,actor)
    definitions=world.classes if actor.is_player else world.npcs
    definition=definitions.get(actor.char_class if actor.is_player else actor.source_def,{})
    default=definition.get('task_skills',{}).get(task,0)
    value=actor.progress.get('skills',{}).get(task,default)
    return max(0,min(100,value)) if type(value) is int else 0


def proficiency(value):
    return ('Unpractised' if value == 0 else 'Novice' if value < 20 else
            'Apprentice' if value < 40 else 'Journeyman' if value < 60 else
            'Expert' if value < 80 else 'Master')


def resource_task(world, source):
    if source.get('task_skill'):
        return source['task_skill']
    from engine import fishing, resource_nodes
    if fishing.is_rod(world.items.get(source.get('tool'),{})):
        return 'fishing'
    visual=resource_nodes.visual_config(source,world.items) or {}
    if visual.get('kind')=='mine':return 'mining'
    if visual.get('kind')=='crop':return 'farming'
    return source.get('required_skill') or 'fieldcraft'


def practice(world, actor, task, *, difficulty=0, effort=1, event_id=None, ceiling=100):
    """Credit an executed attempt. Callers own prerequisites and real work.

    Failed attempts may teach; rejected commands and projections must not call
    this function. Bounded event tokens make a particular completed action
    replay-safe. Easy work still teaches more slowly, and expertise increases
    the next-level requirement. Both actor kinds use precisely the same rule.
    """
    if (actor is None or not actor.alive or world.entities.get(actor.id) is not actor
            or not isinstance(task,str) or not TASK.fullmatch(task)):
        return 0
    if not finite(effort) or effort<=0:
        return 0
    if not finite(difficulty) or type(ceiling) is not int or not 0<=ceiling<=100:
        return 0
    from engine import worldtime
    minute=getattr(world,'living_state',{}).get('minute',worldtime.initial_minute(world.metadata))
    saved=actor.progress.get(KEY,{})
    row=saved.get(task,{})
    if minute < row.get('last_minute',minute):
        return 0
    token=sha256(str(event_id).encode()).hexdigest() if event_id is not None else None
    if token and token in row.get('events',[]):
        return 0
    before=level(world,actor,task)
    if before>=ceiling:
        return 0
    # A full effort unit is practical work, not a button click. Task handlers
    # supply actual duration/complexity, bounded here against burst rewards.
    gain=round(min(20,effort)*max(.25,min(2,1+(max(0,min(100,difficulty))-before)/50)),3)
    # Instruction cannot teach beyond the instructor's authored range.
    if ceiling<100:
        remaining=sum(threshold(value) for value in range(before,ceiling))-row.get('xp',0)
        gain=min(gain,max(0,remaining))
    row=actor.progress.setdefault(KEY,{}).setdefault(task,{'xp':0,'attempts':0,'events':[]})
    row['xp']=round(row.get('xp',0)+gain,3)
    row['attempts']=min(1_000_000,row.get('attempts',0)+1)
    row['last_minute']=minute
    if token:row['events']=(row.get('events',[])+[token])[-128:]
    current=before
    while current<100 and row['xp']>=threshold(current):
        row['xp']=round(row['xp']-threshold(current),3);current+=1
    if current==100:row['xp']=0
    actor.progress.setdefault('skills',{})[task]=current
    if actor.is_player:
        world.dirty_players=getattr(world,'dirty_players',set())|{actor.id}
    return current-before


def training(world,actor,task,units,*,difficulty=0,event_id=None,ceiling=100):
    """An executed lesson supplies bounded novice-equivalent practice.

    Authored intensity is 1–5 units. It is never a fixed number of levels:
    advanced learners need repeated real lessons to cross larger thresholds.
    """
    if type(units) is not int or not 1<=units<=5:return 0
    remaining=sum(threshold(value) for value in range(units));gained=0;part=0
    while remaining>0:
        amount=min(20,remaining)
        token=None if event_id is None else str(event_id)+':'+str(part)
        gained+=practice(world,actor,task,difficulty=difficulty,effort=amount,
                         event_id=token,ceiling=ceiling)
        remaining-=amount;part+=1
    return gained


def transaction(world,*actors):
    """Credit the participants after a real finite exchange has committed."""
    seen=set()
    for actor in actors:
        if actor is not None and actor.id not in seen:
            practice(world,actor,'trading',difficulty=10)
            seen.add(actor.id)


def projection(world, actor):
    """Only this character's skill/knowledge records, with no training side effect."""
    definitions=world.classes if actor.is_player else world.npcs
    definition=definitions.get(actor.char_class if actor.is_player else actor.source_def,{})
    tasks=set(NAMES)|set(actor.progress.get('skills',{}))|set(definition.get('task_skills',{}))
    practice_rows=actor.progress.get(KEY,{})
    skills=[]
    for task in sorted(tasks,key=lambda key:NAMES.get(key,key)):
        if not isinstance(task,str) or not TASK.fullmatch(task):continue
        value=level(world,actor,task);row=practice_rows.get(task,{})
        skills.append(dict(id=task,name=NAMES.get(task,task.replace('_',' ').title()),level=value,
                           proficiency=proficiency(value),practice=row.get('xp',0),
                           next_practice=threshold(value) if value<100 else None,
                           attempts=row.get('attempts',0)))
    known=actor.progress.get('knowledge',{})
    def names(ids,catalog):
        return [dict(id=i,name=catalog[i].get('name',i)) for i in dict.fromkeys(ids) if i in catalog]
    knowledge=dict(recipes=names(known.get('recipes',[]),getattr(world,'recipes',{})),
                   techniques=names(actor.abilities,getattr(world,'abilities',{})),
                   books=names(actor.progress.get('reading_journal_v1',[]),world.items))
    return dict(skills=skills,knowledge=knowledge,scale=100)


def describe(world, actor):
    view=projection(world,actor)
    lines=['Skills and knowledge','Task skill levels are separate from your overall character level.']
    for row in view['skills']:
        progress=(' · practice '+str(row['practice'])+' / '+str(row['next_practice'])
                  if row['next_practice'] is not None else ' · level cap')
        lines.append(row['name']+': '+str(row['level'])+'/100 · '+row['proficiency']+progress)
    for kind,label in [('recipes','Known recipes'),('techniques','Learned techniques'),('books','Reading journal')]:
        lines.append(label+': '+(', '.join(row['name'] for row in view['knowledge'][kind]) or 'None recorded.'))
    lines.append('Real attempts earn practice. Harder levels take longer; knowing a recipe is separate from proficiency.')
    return '\n'.join(lines)


def register(registry):
    from engine.commands import Command
    registry.register(Command('skills','Your task levels, practice and learned knowledge.','skills',
                              lambda ctx,args:describe(ctx.world,ctx.player)))
