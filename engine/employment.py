"""Local funded vacancies and timed work on actual workshop stock.

Applying does not pay. Starting a batch reserves existing material and wages;
only completed work creates its real recipe output and earns those wages.
Interruptions return the escrow once, keeping the assignment available.
"""
from copy import copy,deepcopy
from hashlib import sha256
import json
import shlex
import uuid

KEY='employment_v1'
MAX_JOBS=256
READONLY={'look','map','inventory','score','status','help','skills','standing','workshop',
          'provenance','survey','recipes','catalog','wardrobe','materials','quests',
          'adventures','market','journal','condition','time','inspect','spells',
          'companions','services','route','guide','interface','track','untrack','save','atlas',
          'songs','jobs','job','rest','sleep','wait'}


def _now(world):
    from engine import worldtime
    return int(getattr(world,'living_state',{}).get('minute',worldtime.initial_minute(world.metadata)))


def _jobs(world,create=False):
    if create:
        from engine import living
        return living.state(world).setdefault(KEY,{'version':1,'jobs':{}})['jobs']
    return getattr(world,'living_state',{}).get(KEY,{}).get('jobs',{})


def active(world,actor):
    row=_jobs(world).get(actor.id,{})
    batch=row.get('batch')
    return batch if isinstance(batch,dict) and batch.get('state')=='working' else None


def _offers(world,room):
    return getattr(world,'room_details',{}).get(room,{}).get('employment',[])


def _offer(world,room,ident):
    return next((row for row in _offers(world,room) if row.get('id')==ident),None)


def _shop(world,room,create=False):
    if create:
        from engine import society
        return society.shop(world,room)[1]
    saved=getattr(world,'living_state',{}).get('economy',{}).get('shops',{}).get(room)
    if saved is not None:return saved
    cfg=getattr(world,'room_details',{}).get(room,{}).get('workshop',{}) or {}
    return {'gold':cfg.get('capital',0),'stock':dict(cfg.get('initial_stock',{}))}


def _employer(world,room,cfg):
    people=[actor for actor in world.entities_in_room(room) if not actor.is_player and actor.alive
            and actor.source_def==cfg.get('employer')]
    return people[0] if len(people)==1 else None


def _read_world(world):
    # Legacy eligibility helpers initialize clock defaults or expire short
    # conversation timers. Isolate these containers during pure preflight and
    # projection; the world's actual stock and the actors stay untouched.
    world=copy(world)
    world.living_state={**getattr(world,'living_state',{})}
    for key in ('nodes','encounters','camps'):world.living_state.setdefault(key,{})
    world.npc_attention_until=dict(getattr(world,'npc_attention_until',{}))
    world.trade_attention=deepcopy(getattr(world,'trade_attention',{}))
    return world


def _actor_problem(world,actor):
    from engine import city_justice,livelihoods,npc_attention,relationships,sleep_movement,resting
    if world.entities.get(actor.id) is not actor or not actor.alive or actor.location not in world.rooms:return 'The worker is unavailable.'
    if not relationships.sentient(world,actor) or not livelihoods.work_eligible(world,actor):return 'This work requires an eligible adult worker.'
    if not actor.is_player and (actor.progress.get('retired') or not livelihoods.on_shift(world,actor)):return 'The worker is off duty.'
    if sleep_movement.asleep(world,actor) or resting.active(actor):return 'Wake and stop resting before working.'
    case=getattr(world,'living_state',{}).get(city_justice.KEY,{}).get('cases',{}).get(actor.id,{})
    if actor.progress.get('restrained_until',0)>_now(world) or case.get('status') in ('awaiting_hearing','sentenced'):return 'Confinement or restraint prevents this work.'
    busy=any(actor.id in (row.get('worker'),row.get('cover')) or row.get('bound') and actor.id in row.get('targets',[])
             for row in getattr(world,'living_state',{}).get('community_jobs',{}).get('jobs',{}).values() if row.get('status')=='active')
    if busy or npc_attention.paused(world,actor):return 'Finish the current committed task or conversation first.'
    from engine import artworks
    artwork=artworks.active(world,actor)
    if artwork and not artwork.get('paused'):return 'Finish or pause the current artwork first.'
    if any(person.alive and not person.is_player and world.npcs.get(person.source_def,{}).get('disposition')=='hostile'
           for person in world.entities_in_room(actor.location)):return 'Nearby danger prevents safe work.'
    return ''


def _recipe_problem(world,actor,room,cfg):
    from engine import ecology,gathering,knowledge,livelihoods,quest_progress,task_skills
    recipe=world.recipes.get(cfg.get('recipe'))
    if not recipe or not recipe.get('ingredients') or not recipe.get('outputs'):return 'The production design is unavailable.'
    if recipe.get('artwork'):return 'Use the artistic work service for this project.'
    if not knowledge.recipe_source_ready(actor,recipe):return 'Read this recipe’s actual source before taking the work.'
    problem=gathering.prerequisite(world,actor,recipe)
    if problem:return problem
    if recipe.get('tool') and recipe['tool'] not in actor.inventory:return 'Bring '+world.items.get(recipe['tool'],{}).get('name','the required tool')+'.'
    if not livelihoods.room_open(world,room):return 'This workplace is closed or unusable.'
    station=recipe.get('station','hand')
    if station!='hand' and station not in world.room_details.get(room,{}).get('facilities',[]):return 'This workplace lacks the required '+station+'.'
    if not set(recipe.get('required_abilities',[]))<=set(actor.abilities):return 'Learn the recipe’s required abilities first.'
    if any(quest_progress.status(world,actor,q)!='complete' for q in recipe.get('prerequisites',[])):return 'Complete the recipe’s prerequisite quests first.'
    if not ecology.available(world,room,recipe):return 'Required local resources or mature livestock are unavailable.'
    skill=recipe.get('task_skill') or recipe.get('kind','crafting')
    if task_skills.level(world,actor,skill)<cfg.get('min_skill',0):return 'This vacancy requires more '+skill+' practice.'
    return ''


def _signature(cfg,recipe):
    return sha256(json.dumps([cfg,recipe],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _demand_problem(world,room,cfg,*,except_actor=None):
    stock=_shop(world,room)['stock'];recipe=world.recipes[cfg['recipe']]
    target=cfg.get('target_stock',world.room_details[room]['workshop'].get('stock_limit',40))
    promised={}
    for ident,job in _jobs(world).items():
        batch=job.get('batch')
        if ident!=except_actor and job['room']==room and batch and batch.get('state')=='working':
            for iid,count in batch['outputs'].items():promised[iid]=promised.get(iid,0)+count
    if any(stock.get(iid,0)+promised.get(iid,0)+count>target for iid,count in recipe['outputs'].items()):
        return 'Enough finished stock is already available or being made; there is no open production demand.'
    return ''


def _availability(world,actor,room,cfg,*,applying=False):
    world=_read_world(world)
    problem=_actor_problem(world,actor)
    if problem:return problem
    if actor.location!=room:return 'Return to the workplace before applying or working.'
    employer=_employer(world,room,cfg)
    if employer is None or employer is actor:return 'The actual hiring employer is not available here.'
    from engine import livelihoods,sleep_movement
    if not livelihoods.service_open(world,employer) or sleep_movement.asleep(world,employer):return 'The hiring employer is off duty.'
    problem=_recipe_problem(world,actor,room,cfg)
    if problem:return problem
    if applying:
        occupied=sum(job['room']==room and job['vacancy_id']==cfg['id'] for job in _jobs(world).values())
        if occupied>=cfg.get('slots',1):return 'This vacancy is already filled.'
    problem=_demand_problem(world,room,cfg,except_actor=actor.id)
    if problem:return problem
    shop=_shop(world,room);recipe=world.recipes[cfg['recipe']]
    missing=[world.items.get(iid,{}).get('name',iid) for iid,count in recipe['ingredients'].items() if shop['stock'].get(iid,0)<count]
    if missing:return 'Work is blocked by missing real supplies: '+', '.join(missing)+'.'
    if shop['gold']<cfg['wage']:return 'The employer’s workshop treasury cannot fund this batch’s wage.'
    return ''


def view(world,actor):
    vacancies=[];jobs=_jobs(world)
    for cfg in _offers(world,actor.location):
        recipe=world.recipes.get(cfg.get('recipe'),{});shop=_shop(world,actor.location)
        employer=_employer(world,actor.location,cfg)
        occupied=sum(row['room']==actor.location and row['vacancy_id']==cfg['id'] for row in jobs.values())
        blocked='You already hold an assignment. Leave it before applying elsewhere.' if actor.id in jobs else _availability(world,actor,actor.location,cfg,applying=True)
        vacancies.append(dict(id=cfg['id'],title=cfg['title'],employer_id=employer.id if employer else None,
            employer=employer.name if employer else world.npcs.get(cfg['employer'],{}).get('name',cfg['employer']),
            recipe_id=cfg['recipe'],recipe=recipe.get('name',cfg['recipe']),wage=cfg['wage'],
            minutes=recipe.get('minutes',5),slots=cfg.get('slots',1),open_slots=max(0,cfg.get('slots',1)-occupied),
            materials=[dict(id=iid,name=world.items.get(iid,{}).get('name',iid),quantity=count,available=shop['stock'].get(iid,0)) for iid,count in recipe.get('ingredients',{}).items()],
            outputs=[dict(id=iid,name=world.items.get(iid,{}).get('name',iid),quantity=count,available=shop['stock'].get(iid,0)) for iid,count in recipe.get('outputs',{}).items()],
            blocked=blocked,can_apply=not blocked))
    assignment=None;job=jobs.get(actor.id)
    if job:
        cfg=_offer(world,job['room'],job['vacancy_id']);batch=active(world,actor)
        blocked='The authored vacancy is no longer available.' if cfg is None else 'A batch is already in progress.' if batch else _availability(world,actor,job['room'],cfg)
        assignment=dict(vacancy_id=job['vacancy_id'],title=job['title'],room=job['room'],employer=job['employer_name'],
            batch={'state':'working','elapsed':batch['elapsed'],'remaining':batch['duration']-batch['elapsed'],'wage':batch['wage']} if batch else None,
            can_work=not blocked,blocked=blocked,message=job.get('message',''))
    return dict(actor_id=actor.id,room=actor.location,vacancies=vacancies,assignment=assignment)


def _dirty(world,actor):
    if actor.is_player:world.dirty_players=getattr(world,'dirty_players',set())|{actor.id}


def apply(world,actor,vacancy_id):
    if actor.id in _jobs(world):raise ValueError('Leave your current assignment before applying for another.')
    cfg=_offer(world,actor.location,vacancy_id)
    if cfg is None:raise ValueError('Choose an actual vacancy at this workplace.')
    problem=_availability(world,actor,actor.location,cfg,applying=True)
    if problem:raise ValueError(problem)
    if len(_jobs(world))>=MAX_JOBS:raise ValueError('No further work contracts can be accepted right now.')
    employer=_employer(world,actor.location,cfg)
    _jobs(world,True)[actor.id]=dict(room=actor.location,vacancy_id=cfg['id'],title=cfg['title'],
        employer_id=employer.id,employer_name=employer.name,applied_minute=_now(world),batch=None)
    from engine import knowledge
    knowledge.teach(world,actor,{'recipes':[cfg['recipe']]})
    _dirty(world,actor)
    return f'Accepted for {cfg["title"]}. Use job work to make one batch for {cfg["wage"]} gold after actual work is completed.'


def work(world,actor):
    job=_jobs(world).get(actor.id)
    if not job:raise ValueError('Apply for an actual vacancy first.')
    if active(world,actor):return 'This batch is already in progress; the shared world clock measures the work.'
    cfg=_offer(world,job['room'],job['vacancy_id'])
    if cfg is None:raise ValueError('The authored vacancy is no longer available.')
    problem=_availability(world,actor,job['room'],cfg)
    if problem:raise ValueError(problem)
    recipe=world.recipes[cfg['recipe']];shop=_shop(world,job['room'],True)
    token=uuid.uuid4().hex;now=_now(world)
    for iid,count in recipe['ingredients'].items():shop['stock'][iid]-=count
    shop['gold']-=cfg['wage']
    job['batch']=dict(state='working',token=token,recipe=cfg['recipe'],signature=_signature(cfg,recipe),
        last_minute=now,elapsed=0,duration=recipe.get('minutes',5),ingredients=deepcopy(recipe['ingredients']),
        outputs=deepcopy(recipe['outputs']),wage=cfg['wage'],hp=actor.hp)
    actor._employment_token=token;actor.activity='working on '+recipe.get('name',recipe['id'])
    job['message']='Materials and wages are reserved for this actual batch.';_dirty(world,actor)
    return f'Working on {recipe.get("name",recipe["id"])} for {recipe.get("minutes",5)} game minutes. {cfg["wage"]} gold is reserved; leaving or another action stops the batch.'


def interrupt(world,actor,reason):
    job=_jobs(world).get(actor.id);batch=active(world,actor)
    if not job or not batch:return ''
    return _refund(world,actor.id,job,reason)


def _refund(world,ident,job,reason):
    batch=job.get('batch')
    if not batch or batch.get('state')!='working':return ''
    # The existing escrow goes back to its exact workshop, even if a world
    # edit removed the room definition. No replacement stock is manufactured.
    shop=world.living_state['economy']['shops'][job['room']]
    for iid,count in batch['ingredients'].items():shop['stock'][iid]=shop['stock'].get(iid,0)+count
    shop['gold']+=batch['wage'];batch['state']='refunded';job['batch']=None
    text='Work stopped: '+reason+'. Reserved supplies and wages returned to the workshop.'
    job['message']=text;actor=world.entities.get(ident)
    if actor:
        actor._employment_token=None
        if str(getattr(actor,'activity','')).startswith('working on '):actor.activity='awake'
        _dirty(world,actor)
        if actor.is_player:world.rest_notifications=getattr(world,'rest_notifications',[])+[(actor.id,text)]
    return text


def leave(world,actor):
    interrupt(world,actor,'you left the assignment')
    job=_jobs(world).pop(actor.id,None)
    _dirty(world,actor)
    return 'You left '+job['title']+'.' if job else 'You have no employment assignment.'


def movement(world,actor,old,new):
    if old!=new:interrupt(world,actor,'you left the work site')


def before_command(world,actor,command,registry=None,*,resolve_shortcuts=True):
    if actor is None or not active(world,actor):return
    from engine import resting
    verb,args=resting.canonical(world,command,registry,resolve_shortcuts=resolve_shortcuts)
    if verb not in READONLY and not (verb=='art' and not args):interrupt(world,actor,'you began another action')


def advance(world,minutes):
    from engine import living
    if getattr(world,'realtime',False) and not getattr(world,'tick_authorized',False):return
    now=_now(world)
    for ident,job in list(_jobs(world).items()):
        batch=job.get('batch')
        if not batch or batch.get('state')!='working':continue
        if now==batch['last_minute']:continue  # A batch may have begun in this same actor tick.
        actor=world.entities.get(ident);cfg=_offer(world,job['room'],job['vacancy_id'])
        problem='the worker is unavailable' if actor is None else _actor_problem(world,actor)
        if actor and actor.location!=job['room']:problem='you left the work site'
        if actor and actor.is_player and (ident not in getattr(world,'online_player_ids',{ident}) or getattr(actor,'_employment_token',None)!=batch['token']):
            problem='the player session ended; offline time does not count'
        if actor and actor.hp<batch['hp']:problem='the worker was hurt'
        if not cfg or cfg['recipe'] not in world.recipes or _signature(cfg,world.recipes[cfg['recipe']])!=batch['signature']:
            problem='the work order changed'
        if not problem:problem=_recipe_problem(world,actor,job['room'],cfg)
        if not problem and (type(minutes) is not int or minutes<=0 or batch['last_minute']!=now-minutes):
            problem='the shared work clock changed or replayed'
        if problem:_refund(world,ident,job,problem.rstrip('.'));continue
        batch['elapsed']=min(batch['duration'],batch['elapsed']+minutes);batch['last_minute']=now
        if batch['elapsed']<batch['duration']:continue
        # Execute the same actual crafting authority. Its nested time advance
        # is suppressed because these minutes were already simulated above.
        from engine.commands import CommandContext
        from engine import knowledge
        knowledge.teach(world,actor,{'recipes':[batch['recipe']]})
        inventory_before=list(actor.inventory)
        for iid,count in batch['ingredients'].items():actor.inventory.extend([iid]*count)
        before=actor.progress.get('actions',{}).get('craft:'+batch['recipe'],0)
        simulating=getattr(world,'_community_simulating',False);world._community_simulating=True
        try:result=living.command(CommandContext(world,actor,world.rooms[actor.location]),batch['recipe'],'craft')
        except ValueError as exc:
            actor.inventory[:]=inventory_before
            _refund(world,ident,job,'the recipe could not be completed: '+str(exc));continue
        except Exception:
            # A failed integration must never leave injected escrow in the
            # worker's inventory for a replay to duplicate. Preserve the error
            # for diagnostics after restoring actual supplies and wages once.
            actor.inventory[:]=inventory_before
            _refund(world,ident,job,'the recipe could not be completed')
            raise
        finally:world._community_simulating=simulating
        if actor.progress.get('actions',{}).get('craft:'+batch['recipe'],0)<=before:
            actor.inventory[:]=inventory_before
            _refund(world,ident,job,'the recipe could not be completed: '+result);continue
        shop=_shop(world,job['room'],True)
        for iid,count in batch['outputs'].items():
            for _ in range(count):actor.inventory.remove(iid)
            shop['stock'][iid]=shop['stock'].get(iid,0)+count
        actor.gold+=batch['wage'];batch['state']='paid';job['batch']=None;actor._employment_token=None
        actor.activity='finished paid work';job['completed']=job.get('completed',0)+1
        job['message']=f'Completed one real batch and earned {batch["wage"]} gold.';_dirty(world,actor)
        from engine import npc_life
        npc_life.earned(world,actor,batch['wage'])
        if actor.is_player:world.rest_notifications=getattr(world,'rest_notifications',[])+[(actor.id,job['message'])]


def step(world,actor):
    """Hold an actual batch, or let an explicitly opted-in local NPC apply."""
    if actor.is_player:return False
    if active(world,actor):return True
    cfg=world.npcs.get(actor.source_def,{}).get('employment_plan',{})
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True or actor.location!=cfg.get('room'):return False
    now=_now(world);last=actor.progress.get('employment_attempt_minute',-1_000_000)
    if now<last+15:return False
    actor.progress['employment_attempt_minute']=now
    try:
        if actor.id not in _jobs(world):apply(world,actor,cfg['vacancy'])
        work(world,actor)
    except ValueError:return False
    return True


def command(ctx,args,name='job'):
    words=shlex.split(args)
    if name=='jobs' or not words or words==['status']:
        projection=view(ctx.world,ctx.player);lines=['Local employment']
        for row in projection['vacancies']:
            lines.append(f'{row["id"]}: {row["title"]} — {row["employer"]}, {row["wage"]} gold per {row["minutes"]}-minute batch. '+(row['blocked'] or 'Apply with job apply '+row['id']+'.'))
        if projection['assignment']:
            row=projection['assignment'];lines.append('Your assignment: '+row['title']+'. '+(row['message'] or 'Use job work to begin a real batch.'))
            if row['batch']:lines.append(str(row['batch']['remaining'])+' game minutes of work remain.')
            elif row['blocked']:lines.append(row['blocked'])
        if not projection['vacancies'] and not projection['assignment']:lines.append('No vacancies are posted here.')
        return '\n'.join(lines)
    if len(words)==2 and words[0]=='apply':return apply(ctx.world,ctx.player,words[1])
    if words==['work']:return work(ctx.world,ctx.player)
    if words==['stop']:return interrupt(ctx.world,ctx.player,'you stopped working') or 'No batch is in progress.'
    if words==['leave']:return leave(ctx.world,ctx.player)
    raise ValueError('Use jobs, job apply <vacancy>, job work, job stop, or job leave.')


def register(registry):
    from engine.commands import Command
    for name in ('jobs','job'):
        registry.register(Command(name,'View and perform funded local work','jobs / job apply <vacancy> / job work',
                                  lambda ctx,args,n=name:command(ctx,args,n),example='jobs'))


def validate(data):
    issues=[];npcs={row['id']:row for row in data.get('npc',[])}
    recipes={row['id']:row for row in data.get('recipe',[])};items={row['id'] for row in data.get('item',[])}
    rooms={row['id']:row for row in data.get('room',[])};offers={}
    for room in rooms.values():
        cfgs=room.get('employment',[])
        if not isinstance(cfgs,list) or len(cfgs)>8:issues.append(room['id']+': employment must list at most 8 vacancies');continue
        ids=set()
        for cfg in cfgs:
            if not isinstance(cfg,dict):issues.append(room['id']+': vacancy must be an object');continue
            label=room['id']+': employment '
            if not isinstance(cfg.get('id'),str) or not cfg['id'].strip() or not 1<=len(cfg['id'])<=64 or cfg['id'] in ids:issues.append(label+'requires a unique short ID');continue
            ids.add(cfg['id']);offers[room['id'],cfg['id']]=cfg
            if not isinstance(cfg.get('title'),str) or not cfg['title'].strip() or not 1<=len(cfg['title'])<=120:issues.append(label+'needs a short title')
            if not isinstance(cfg.get('employer'),str) or cfg['employer'] not in npcs:issues.append(label+'references a missing employer')
            rec=recipes.get(cfg.get('recipe')) if isinstance(cfg.get('recipe'),str) else None
            if not rec:issues.append(label+'references a missing recipe');continue
            workshop=room.get('workshop')
            if not isinstance(workshop,dict) or cfg['recipe'] not in workshop.get('recipes',[]):issues.append(label+'requires that recipe in the actual local workshop')
            if any(not isinstance(rec.get(field),dict) or not rec[field] or any(iid not in items or type(count) is not int or not 1<=count<=1000 for iid,count in rec[field].items()) for field in ('ingredients','outputs')):issues.append(label+'requires finite real recipe inputs and outputs')
            if rec.get('artwork'):issues.append(label+'artistic projects use the artistic work service')
            if type(rec.get('minutes',5)) is not int or not 1<=rec.get('minutes',5)<=120:issues.append(label+'recipe duration must be 1–120 minutes')
            for key,low,high,default in (('wage',1,1000,None),('slots',1,16,1),('target_stock',1,1000,40),('min_skill',0,100,0)):
                value=cfg.get(key,default)
                if type(value) is not int or not low<=value<=high:issues.append(label+'invalid '+key)
    for npc in npcs.values():
        cfg=npc.get('employment_plan',{})
        if not isinstance(cfg,dict):issues.append(npc['id']+': employment_plan must be an object');continue
        if not cfg:continue
        if type(cfg.get('enabled')) is not bool or set(cfg)-{'enabled','room','vacancy'}:issues.append(npc['id']+': invalid employment plan')
        if cfg.get('enabled') and (not isinstance(cfg.get('room'),str) or not isinstance(cfg.get('vacancy'),str) or (cfg['room'],cfg['vacancy']) not in offers):issues.append(npc['id']+': employment plan needs an actual local vacancy')
    return issues
