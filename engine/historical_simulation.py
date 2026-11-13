"""Bounded new-world historical simulation proof, never a live-world updater.

Fictional annual NPC development and decadal diplomatic turns. Output is staged
initial state, not installed content. No player saves, existing histories, RNGs
or world objects are mutated. Geography is supplied, never guessed from icons.
"""
from copy import deepcopy
from hashlib import sha256
import heapq
import json
import random
from engine import life_stages, worldtime
from engine.world_history import HistoryError, compile_history

MAX_STEPS = 500000
MAX_EVENTS = 100000
YEAR = worldtime.MINUTES_PER_YEAR
# Data-driven defaults suitable for future Creator controls; no Expanse IDs.
RULE_SCHEMA = {
    'skill_gain_per_work_year': (2, 0, 20, 'Annual occupation skill gain'),
    'health_recovery_per_year': (2, 0, 100, 'Annual recovery without an accident'),
    'mood_recovery_fraction': (.25, 0, 1, 'Annual return toward neutral mood'),
    'trade_relation_gain': (5, 0, 25, 'Relation gain per trade event'),
    'dispute_relation_loss': (10, 0, 25, 'Relation loss per dispute'),
    'treaty_relation_gain': (10, 0, 25, 'Relation gain per treaty'),
    'war_relation_loss': (15, 0, 25, 'Relation loss when war starts'),
    'peace_relation_gain': (15, 0, 25, 'Relation gain when war ends'),
}


def creator_schema():
    return {k:dict(default=v[0],minimum=v[1],maximum=v[2],label=v[3]) for k,v in RULE_SCHEMA.items()}


def _rng(seed, key):
    return random.Random(int.from_bytes(sha256(f'{seed}:{key}'.encode()).digest(), 'big'))


def _number(value, label, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise HistoryError(label + ' is outside allowed finite bounds')
    return value


def simulate_new_world(data, config):
    """Simulate explicitly selected synthetic/new NPCs and political pairs.

    fresh_world must be True. selection contains source IDs and fictional income,
    expenses and accident_probability. faction_pairs explicitly opts relations
    into evolution; locked pairs stay unchanged. Zero wars unless allow_war=True.
    Geological/civic authored facts can enter through history_plan. Return only;
    publishing and a save-existence guard belong to a separate future installer.
    """
    if not isinstance(config, dict) or config.get('fresh_world') is not True:
        raise HistoryError('Explicit fresh-world simulation required')
    settings = config.get('rules', {})
    if not isinstance(settings, dict) or set(settings)-set(RULE_SCHEMA):
        raise HistoryError('Unknown or invalid editable historical rules')
    tuning = {k:_number(settings.get(k,v[0]),k,v[1],v[2]) for k,v in RULE_SCHEMA.items()}
    plan = deepcopy(config.get('history_plan', {}))
    compiled = compile_history(data, plan)
    seed, now = plan['seed'], plan['present_minute']
    source = {r['id']:r for r in data.get('npc', [])}
    groups = {r['id']:r for r in data.get('group', [])}
    species = {r['id']:r for r in data.get('species', [])}
    selected = config.get('selection', [])
    pairs = config.get('faction_pairs', [])
    if not isinstance(selected, list) or not isinstance(pairs, list) or len(pairs) > 100:
        raise HistoryError('Invalid selection or faction pair budget')
    actors, polities, events, queue = {}, {}, [], []
    generators = {}
    steps = 0

    def record(kind, at, **payload):
        if len(events) >= MAX_EVENTS:
            raise HistoryError('Historical event budget exceeded; no state published')
        eid = f'sim:{len(events):06d}'
        events.append(dict(id=eid, kind=kind, at=at, **payload))
        return eid

    for rule in selected:
        if not isinstance(rule, dict) or rule.get('source_id') not in source:
            raise HistoryError('Unknown selected NPC')
        aid = rule['source_id']; npc = source[aid]
        if aid in actors or aid in compiled['skipped'] or aid not in compiled['actors']:
            raise HistoryError('Duplicate or incompatible NPC history selection')
        born = compiled['actors'][aid]['born_minute']
        stages = life_stages.resolve_profile(None, species.get(npc.get('social_profile', {}).get('species'), {}))
        income = _number(rule.get('annual_income', 10), 'annual income', 0, 10000)
        costs = _number(rule.get('annual_expenses', 8), 'annual expenses', 0, 10000)
        accident = _number(rule.get('accident_probability', 0), 'accident probability', 0, .2)
        hp = _number(npc.get('hp', 20), 'authored hp', 1, 100000)
        # Simulation owns selected initialization only; caller retains source copy.
        actors[aid] = dict(source_id=aid, born_minute=born, group=npc.get('group'),
            alive=True, health=100, savings=0, skill=0, education_years=0,
            mood=50, fortitude=50, income_security=50, experiences=[],
            _rules=dict(income=income,costs=costs,accident=accident,stages=stages,hp=hp,education=rule.get('education_available') is True,work=rule.get('work_available') is True))
        generators['npc:'+aid] = _rng(seed, 'npc:'+aid)
        record('birth', born, actor=aid)
        heapq.heappush(queue, (born+YEAR, 'npc', aid, 1))
    start = now - int(_number(config.get('civic_years', 100), 'civic years', 0, 2000)) * YEAR
    seen = set()
    for rule in pairs:
        if not isinstance(rule, dict): raise HistoryError('Invalid faction rule')
        a,b = rule.get('a'),rule.get('b')
        if a not in groups or b not in groups or a==b:
            raise HistoryError('Faction pair needs two distinct existing groups')
        key = ':'.join(sorted((a,b)))
        if key in seen:raise HistoryError('Duplicate faction pair')
        seen.add(key)
        score = _number(rule.get('initial_score',50), 'initial score',0,100)
        low = _number(rule.get('minimum',0),'minimum',0,100)
        high = _number(rule.get('maximum',100),'maximum',low,100)
        if not low <= score <= high:raise HistoryError('Initial relation outside creator bounds')
        war = _number(rule.get('war_probability',.1),'war probability',0,.25)
        polities[key] = dict(a=a,b=b,score=score,at_war=False,trade_balance=0,
            last_event=None,war_started=None,locked=rule.get('locked',False),
            _rules=dict(low=low,high=high,war=war,allow_war=rule.get('allow_war') is True))
        generators['civ:'+key] = _rng(seed,'civ:'+key)
        if not rule.get('locked',False):heapq.heappush(queue,(start+10*YEAR,'civ',key,1))
    # Caller-authored shared historical facts have real bounded state effects.
    by_event={e['id']:e for e in compiled['events']}
    for eid,event in by_event.items():
        if event['actors']:
            heapq.heappush(queue,(event['at'],'authored',eid,0))
    while queue:
        at,kind,key,turn=heapq.heappop(queue)
        if at>now:break
        steps+=1
        if steps>MAX_STEPS:raise HistoryError('Historical step budget exceeded; no state published')
        if kind=='authored':
            fact=by_event[key]
            for aid in fact['actors']:
                if aid not in actors:continue
                a=actors[aid]
                if fact['kind']=='war_started':
                    a['mood']=max(0,a['mood']-15)
                    a['income_security']=max(0,a['income_security']-10)
                elif fact['kind']=='war_ended':a['mood']=min(100,a['mood']+10)
                a['experiences'].append(key)
                a['experiences']=a['experiences'][-24:]
            record('authored_event_applied',at,cause=key,actors=fact['actors'])
        elif kind=='npc':
            a=actors[key];r=a['_rules'];rng=generators['npc:'+key];st=r['stages']
            a['mood'] += (50-a['mood'])*tuning['mood_recovery_fraction']
            if r['education'] and st['school_start_years'] <= turn < st['adulthood_years']:
                a['education_years']+=1
            if r['work'] and turn >= st['work_start_years']:
                earned=max(0,round(r['income']*(.8+.4*rng.random())))
                before=a['savings'];a['savings']=max(0,before+earned-round(r['costs']))
                a['skill']=min(100,a['skill']+tuning['skill_gain_per_work_year'])
                a['income_security']=max(0,min(100,50+5*(earned-r['costs'])))
                if turn==int(st['work_start_years']):record('work_started',at,actor=key)
            if rng.random()<r['accident']:
                loss=rng.randint(5,15);a['health']=max(20,a['health']-loss)
                a['mood']=max(0,a['mood']-10);a['fortitude']=min(100,a['fortitude']+1)
                eid=record('nonfatal_accident',at,actor=key,health_loss=loss)
                a['experiences']=(a['experiences']+[eid])[-24:]
            else:a['health']=min(100,a['health']+tuning['health_recovery_per_year'])
            heapq.heappush(queue,(at+YEAR,'npc',key,turn+1))
        else:
            p=polities[key];r=p['_rules'];rng=generators['civ:'+key]
            if p['at_war']:
                action='war_ended';p['at_war']=False;delta=tuning['peace_relation_gain']
            elif p['score']<35 and r['low']<25 and r['allow_war'] and rng.random()<r['war']:
                action='war_started';p['at_war']=True;delta=-tuning['war_relation_loss']
            else:
                action=rng.choice(('trade','trade','dispute','treaty','quiet'))
                delta={'trade':tuning['trade_relation_gain'],'dispute':-tuning['dispute_relation_loss'],'treaty':tuning['treaty_relation_gain'],'quiet':0}[action]
            p['score']=max(r['low'],min(r['high'],p['score']+delta))
            if p['at_war']:p['score']=min(24,p['score'])
            if action=='trade':p['trade_balance']+=10
            if action!='quiet':
                cause=p['war_started'] if action=='war_ended' else p['last_event']
                eid=record(action,at,parties=[p['a'],p['b']],cause=cause,relation_after=p['score'])
                p['last_event']=eid
                if action=='war_started':p['war_started']=eid
            heapq.heappush(queue,(at+10*YEAR,'civ',key,turn+1))
    # Concrete proposals use existing gameplay fields, but are not auto-applied.
    proposals={}
    for aid,a in actors.items():
        r=a.pop('_rules')
        proposals[aid]=dict(gold=a['savings'],hp=max(1,round(r['hp']*a['health']/100)),
            life_profile=dict(mood=round(a['mood'],2),fortitude=a['fortitude'],income=a['income_security']),
            social_profile={**deepcopy(source[aid].get('social_profile',{})), 'born_minute':a['born_minute']})
    relation_proposals=[]
    for p in polities.values():
        p.pop('_rules')
        relation_proposals.append(dict(a=p['a'],b=p['b'],base=p['score'],locked=p['locked'],
            relation='hostile' if p['at_war'] or p['score']<25 else 'allied' if p['score']>=80 else 'tolerated' if p['score']>=55 else 'neutral'))
    events.sort(key=lambda e:(e['at'],e['id']))
    result=dict(version=1,status='synthetic_proof_not_installed',source_hash=compiled['source_hash'],
        plan_hash=compiled['plan_hash'],config_hash=sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest(),effective_rules=tuning,actors=actors,factions=polities,events=events,
        npc_proposals=proposals,relation_proposals=relation_proposals,steps=steps,
        limitations=['No reproduction, ancestry generation, mortality or actual terrain generation.',
        'Annual learning and economic/health rules are fictional proof mechanics.',
        'Civic turns do not implement live war, troops, territory, roads or trade inventories.',
        'No save/startup hook or output application. Fresh-world ownership checks required before publishing.'])
    result['hash']=sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result
