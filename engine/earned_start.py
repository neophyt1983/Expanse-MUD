"""Default-off Dawnwatch starter employment, funded from existing kitchen assets."""
from engine import earned_lodging, geology_impacts, livelihoods, living, society

FLAG = 'earned_start_pilot'
VERSION = 'dawnwatch-kitchen-v1'
MARK = 'earned_start_v1'
BOOK = 'dawnwatch_kitchen_job_v1'
DECLINED = 'dawnwatch_kitchen_offer_declined'
INN = 'emberhollow_inn'
KITCHEN = 'emberhollow_inn_kitchen'
CHEF = 'chef_ragnar'
GUIDE = 'first_steps_good_guys_1__step_01'
SKIP = 'first_steps_good_guys_1_alternative'
CHAIN = 'first_steps_good_guys_1'
CONTINUATIONS = frozenset({CHAIN,'first_steps_good_guys_2','first_steps_good_guys_3'})
WELCOME = frozenset({'first_steps_good_guys_welcome_day', 'first_steps_good_guys_welcome_night'})
WELCOME_ITEMS = frozenset({'first_steps_good_guys_welcome_letter', 'quest_chain_note_first_steps_good_guys_1'})
RECIPE = 'lw_stew'
INPUTS = {'lw_carrot': 1, 'lw_onion': 1, 'lw_potato': 1}
WAGE = 4
# An explicitly authored service threshold for the existing kitchen, not a
# special-item target or promise. Normal kitchen stock above it means no work.
SERVICE_TARGET = 10
FALLBACK = ('No money or equipment is needed to look for work. Read the existing '
            'Civic Square request ledger or check Local quests for other open offers. '
            'Only accept work with actual pay or supplies listed.')
INTRO = ('The Gilded Tankard posts short kitchen work when the chef has a real '
         'order and ingredients and can reserve pay. Use startwork status. ' + FALLBACK)


def marked(p):
    return bool(p is not None and p.is_player and p.progress.get(MARK) == VERSION)


def retired(p, qid):
    return marked(p) and qid in (GUIDE, SKIP)


def gold_reward(p, quest):
    # The remaining story and progression are retained, but its old welcome
    # grant does not mint coins into the redesigned start.
    return 0 if marked(p) and quest['id'] in CONTINUATIONS else quest.get('reward_gold',0)


def omit_stage(p, chain_id, stages):
    if marked(p) and chain_id == CHAIN:
        return [qid for qid in stages if qid != GUIDE]
    return stages


def _installed(w):
    return (w.metadata.get(FLAG) == VERSION and living.enabled(w) and society.enabled(w)
            and INN in w.rooms and KITCHEN in w.rooms and CHEF in w.npcs
            and w.groups.get('good_guys', {}).get('start_room') == INN
            and all(i in w.items for i in (*INPUTS, RECIPE)))


def enroll_creation(w, p):
    if p.group_id != 'good_guys' or not _installed(w):
        return False
    p.progress[MARK] = VERSION
    return True


def _read(w):
    state = getattr(w, 'living_state', {})
    rows = state.get(BOOK, {})
    if not isinstance(rows, dict) or len(rows) > SERVICE_TARGET:
        raise ValueError('Kitchen records need review. No pay or ingredients were changed.')
    for party, row in rows.items():
        if (not isinstance(party, str) or not isinstance(row,dict)
                or set(row) != {'phase','ready_at'} or row['phase'] not in ('reserved','preparing','prepared')
                or type(row['ready_at']) is not int or row['ready_at']<0):
            raise ValueError('Kitchen records need review. No pay or ingredients were changed.')
    return rows


def _business(w):
    cfg = w.room_details.get(INN, {}).get('workshop', {})
    pocket = getattr(w, 'living_state', {}).get('economy', {}).get('shops', {}).get(INN)
    recipe = w.recipes.get(RECIPE, {})
    if (not isinstance(pocket, dict) or not isinstance(pocket.get('stock'), dict)
            or type(pocket.get('gold')) is not int or pocket['gold'] < 0
            or type(cfg.get('stock_limit')) is not int or cfg['stock_limit'] <= 0
            or RECIPE not in cfg.get('recipes', ()) or recipe.get('kind') != 'cooking'
            or recipe.get('station') != 'kitchen' or recipe.get('ingredients') != INPUTS
            or recipe.get('outputs') != {RECIPE: 1}):
        raise ValueError('The kitchen has not opened a usable stock and pay ledger.')
    stock = pocket['stock']
    if any(type(stock.get(i, 0)) is not int or stock.get(i, 0) < 0 for i in (*INPUTS, RECIPE)):
        raise ValueError('The kitchen must review its stock before offering work.')
    return cfg, pocket, recipe


def _chef(w):
    # Chef Ragnar is a managed spawn: identity comes from the existing
    # definition and work site, not the variable runtime entity ID or name.
    workers = (e for e in w.entities_in_room(KITCHEN) if e.source_def==CHEF
               and not e.is_player and e.alive and e.location==KITCHEN)
    chef = next((e for e in workers if livelihoods.service_open(w,e)), None)
    if not chef:
        hours=w.npcs.get(CHEF,{}).get('work_hours',{})
        start=hours.get('start') if isinstance(hours,dict) else None
        shift=(f' His posted shift begins at {start//60:02d}:{start%60:02d}.'
               if type(start) is int and 0<=start<1500 else '')
        raise ValueError('Chef Ragnar is not taking orders at his kitchen now.'+shift+' Do not buy supplies.')
    return chef


def _offer(w, p, jobs, *, housing_choice=None, housing_price=None):
    if not _installed(w):
        raise ValueError('There are no new kitchen jobs in this world.')
    if p.progress.get('dawnwatch_kitchen_job_paid') is True:
        raise ValueError('Your short kitchen shift is finished. Check existing local jobs for further work.')
    if p.progress.get(DECLINED) is True:
        raise ValueError('You declined this first offer. You can play, trade or look for other work normally.')
    if p.location != KITCHEN:
        raise ValueError('Ask Chef Ragnar in the Tankard Kitchens (west from the tavern).')
    chef = _chef(w)
    cfg, pocket, _ = _business(w)
    stock = pocket['stock']
    if stock.get(RECIPE, 0) + len(jobs) >= min(SERVICE_TARGET, cfg['stock_limit']):
        raise ValueError('The counter already has enough stew or enough cooks assigned. There is no job to invent.')
    if pocket['gold'] < WAGE:
        raise ValueError('The business cannot reserve 4 gold for another shift. It is not hiring on credit.')
    if any(stock.get(i, 0)<n for i,n in INPUTS.items()):
        raise ValueError('The kitchen lacks the actual ingredients for another stew. No work or pay was reserved.')
    return chef, pocket, earned_lodging.plan(w,p,pocket,WAGE,requested=housing_choice,price=housing_price)


def _describe(w, p, jobs):
    order = jobs.get(p.id,{})
    phase = order.get('phase')
    if phase == 'reserved':
        return ('Reserved: one batch of actual kitchen ingredients and 4 gold from the business. '
                'At the Tankard Kitchens use startwork cook. To return an uncooked order, use startwork cancel there.')
    if phase == 'preparing':
        left=max(0,order['ready_at']-getattr(w,'living_state',{}).get('minute',0))
        return f'Preparing: {left} game minutes left. At the kitchen, use startwork cook to check the bowl; no clock skip.'
    if phase == 'prepared':
        return ('Prepared: one real bowl of Vegetable Stew is awaiting handover. '
                'The 4-gold wage is reserved. In the Tankard Kitchens use startwork deliver.')
    try:chef,pocket,housing = _offer(w,p,jobs)
    except ValueError as exc:return str(exc) + ' ' + FALLBACK
    return (chef.name+' needs another bowl of Vegetable Stew for the Tankard. '
            'The business provides its own vegetables and reserves 4 gold. '
            'No purchase or tool is required. '+
            ('Choose the exact sponsored room below, then use startwork cook and startwork deliver.'
             if housing else 'Use startwork accept, then startwork cook, then startwork deliver.')+
            ' To turn down this job and play normally, use startwork decline.'+
            (earned_lodging.choices(w,p,pocket,WAGE) if housing else ''))


def command(ctx, args):
    w,p=ctx.world,ctx.player
    if not marked(p) or not p.alive:
        raise ValueError('This kitchen start is not available for this character.')
    ctx.time_accounted = True
    jobs = _read(w)
    verb = args.casefold().strip()
    if verb in ('','status'):
        result=_describe(w,p,jobs)
        return result+(' '+earned_lodging.status(w,p) if p.id in earned_lodging._rows(w) else '')
    if verb=='check-in':
        return earned_lodging.check_in(w,p)
    if verb=='lodging':
        return earned_lodging.status(w,p)
    words=verb.split()
    if words and words[0]=='accept':
        if p.id in jobs:
            return _describe(w,p,jobs)
        choice=price=None
        if earned_lodging.enabled(w):
            if len(words)!=3 or words[1] not in earned_lodging.CHOICES:
                raise ValueError('Choose the specific available lodging and quote shown in startwork status. No room has been reserved.')
            _,choice,price=words
        elif len(words)!=1:
            raise ValueError('Use startwork accept.')
        try:chef,pocket,housing=_offer(w,p,jobs,housing_choice=choice,housing_price=price)
        except ValueError as issue:raise ValueError(str(issue)+' '+FALLBACK) from None
        pocket['gold'] -= WAGE
        for i,n in INPUTS.items():
            pocket['stock'][i] -= n
        living.state(w).setdefault(BOOK,{})[p.id] = {'phase':'reserved','ready_at':0}
        earned_lodging.hold(w,p,pocket,housing)
        return (chef.name+' accepts the short order. '+_describe(w,p,_read(w))+
                (' '+earned_lodging.status(w,p) if housing else ''))
    order = jobs.get(p.id,{})
    phase = order.get('phase')
    if verb=='decline':
        if p.progress.get('dawnwatch_kitchen_job_paid'):
            raise ValueError('You already finished this job.')
        if phase in ('preparing','prepared'):
            raise ValueError('This job has already started. Finish the agreed order; the opening offer cannot now be declined.')
        if phase=='reserved':
            # Both raw inputs and pay still physically belong to the business.
            # Turning down work relinquishes the hold from any location.
            _,pocket,_=_business(w)
            earned_lodging.refund(w,p,pocket)
            for i,n in INPUTS.items():pocket['stock'][i]=pocket['stock'].get(i,0)+n
            pocket['gold']+=WAGE;del jobs[p.id]
        p.progress[DECLINED]=True
        w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
        return 'First job declined. No wage, accommodation or quest completion was granted. You are free to play. '+FALLBACK
    if verb not in ('cook','cancel','deliver'):
        raise ValueError('Use startwork status, accept, decline, cook, deliver, cancel, lodging, or check-in.')
    if phase not in ('reserved','preparing','prepared'):
        raise ValueError('No unsettled kitchen order. '+FALLBACK)
    if p.location != KITCHEN or geology_impacts.room_unusable(w,KITCHEN):
        raise ValueError('Return to the usable Tankard Kitchens. Your ingredients or cooked batch and wages remain reserved.')
    cfg,pocket,recipe = _business(w)
    stock = pocket['stock']
    if verb=='cancel':
        if phase!='reserved':raise ValueError('Once cooking starts, finish and deliver the stew to earn the reserved wages.')
        earned_lodging.refund(w,p,pocket)
        for i,n in INPUTS.items():stock[i]=stock.get(i,0)+n
        pocket['gold']+=WAGE;del jobs[p.id]
        return 'Uncooked vegetables and pay returned to the business. Nothing was earned.'
    if verb=='cook':
        if phase=='prepared':return 'The batch is already prepared. Use startwork deliver; nothing was cooked twice.'
        from engine import ecology,sleep_movement
        if ('kitchen' not in living.details(w,KITCHEN).get('facilities',())
                or sleep_movement.asleep(w,p) or not ecology.available(w,KITCHEN,recipe)
                or recipe.get('required_abilities') or recipe.get('prerequisites')):
            raise ValueError('The real requirements for this preparation are not met. The order remains reserved.')
        minutes=recipe.get('minutes',5)
        if type(minutes) is not int or not 1<=minutes<=60:
            raise ValueError('The kitchen must review the actual preparation time.')
        now=living.state(w)['minute']
        if phase=='reserved':
            order.update(phase='preparing',ready_at=now+minutes)
            return f'The kitchen batch is on the stove for {minutes} game minutes. Use startwork status or check the bowl with startwork cook.'
        if now<order['ready_at']:
            return _describe(w,p,jobs)
        # The recipe transforms exactly the reserved kitchen ingredients
        # into one cooked bowl still in the business order, not the backpack.
        order['phase']='prepared'
        pr=living.progress(p)
        pr['skills']['cooking']=pr['skills'].get('cooking',0)+1
        from engine import quest_progress
        quest_progress.action(p,'cook:'+RECIPE)
        return 'Prepared one bowl from the reserved vegetables. Check startwork status, then hand it over with startwork deliver.'
    if phase!='prepared':raise ValueError('Prepare the bowl first. There has been no handover or payment.')
    if stock.get(RECIPE,0)>=cfg['stock_limit']:
        raise ValueError('The kitchen shelf is full. Your cooked bowl and wages are still reserved.')
    # This is a counted delivery to the kitchen itself. It still accepts
    # previously agreed work off shift; no new work starts without the chef.
    earned_lodging.check_book(w,p)
    stock[RECIPE]=stock.get(RECIPE,0)+1
    p.gold+=WAGE
    p.progress['dawnwatch_kitchen_job_paid']=True
    del jobs[p.id]
    w.dirty_players=getattr(w,'dirty_players',set())|{p.id}
    return ('One bowl deposited on the real Tankard shelf. Paid 4 gold once from the reserved wages.'+
            earned_lodging.ready(w,p)+' '+FALLBACK)
