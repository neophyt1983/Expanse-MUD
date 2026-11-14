"""Opt-in ability families. Legacy definitions retain their existing execution.

Authoritative checks apply to learning and use, including scroll lessons. Recovery
uses saved world minutes, never wall-clock timers or a permanent one-use flag.
"""
from engine.item_catalog import counted
FAMILIES = ('mage', 'class', 'race')
EFFECTS = ('damage', 'ward', 'heal', 'ally_heal', 'cleanse', 'guarded_strike', 'focus', 'sunder', 'repair', 'mana_conversion')
DEFAULTS = dict(family='class', classes=[], races=[], minimum_level=1,
                cooldown_minutes=0, weapon_required=False, ward_hits=5,
                ignore_defense=False, components={}, requires_discovery=False)


def config(a):
    raw=a.get('ability_rules')
    return {**DEFAULTS, **raw} if isinstance(raw,dict) and raw else None


def eligibility(w,p,a,ignore_level=False):
    c=config(a)
    if not c:return ''
    for field,actual,defs in [('classes',p.char_class,w.classes),('races',p.race,w.races)]:
        if c[field] and actual not in c[field]:
            return 'Requires '+', '.join(defs.get(i,{}).get('name',i) for i in c[field])+'.'
    from engine import progression
    if not ignore_level and progression.config(w)['enabled'] and progression.state(p)['level']<c['minimum_level']:
        return f"Requires level {c['minimum_level']}."
    return ''


def ready(w,p,a):
    from engine import living
    reason=eligibility(w,p,a)
    if reason:return reason
    c=config(a)
    if not c:return ''
    until=p.progress.get('ability_recovery_v1',{}).get(a['id'],0)
    left=max(0,until-living.state(w)['minute'])
    if left:return f'You can use this ability again in {counted(left,"game minute")}.'
    return ''


def learning_eligibility(w,p,a,ignore_level=False):
    classes=a.get('training_classes',[])
    if classes and p.char_class not in classes:return 'Training is for '+', '.join(w.classes.get(i,{}).get('name',i) for i in classes)+'. Already-learned legacy abilities are retained.'
    return eligibility(w,p,a,ignore_level=ignore_level)


def lesson_check(w,p,a):
    c=config(a)
    if c and c.get('requires_discovery') and a['id'] not in p.progress.get('ability_lessons_v1',[]):
        raise ValueError('Read the relevant training handbook or speak to its instructor first.')
    reason=learning_eligibility(w,p,a)
    if reason:raise ValueError(reason)


def ally(w,p,target):
    if not target.strip():return p
    matches=[e for e in w.entities_in_room(p.location) if e.alive and
             (e.id==p.id or e.progress.get('companion_owner')==p.id) and
             target.casefold() in (e.id.casefold(),e.name.casefold())]
    if len(matches)!=1:raise ValueError('Choose yourself or one of your living companions here.')
    return matches[0]


def cast(w,p,a,target):
    """Execute opted-in templates only; caller handles legacy definitions separately."""
    from engine import living,combat
    c=config(a)
    reason=ready(w,p,a)
    if reason:raise ValueError(reason)
    if not p.alive:raise ValueError('You must be alive to use an ability.')
    effect=a.get('effect');power=a.get('power',0);pr=living.progress(p)
    if effect not in EFFECTS:raise ValueError('This configured ability has no supported effect.')
    cost=a.get('cost_mp',0) if c['family']=='mage' else 0
    if pr['mana']<cost:raise ValueError('Not enough mana. Rest at an inn or camp.')
    enemy=None;recipient=p
    if effect in ('damage','guarded_strike','sunder'):
        enemy=combat.target(w,p,target);combat.validate(w,p,enemy)
        if c['weapon_required'] and not any(w.items.get(i,{}).get('type')=='weapon' for i in p.equipped.values()):
            raise ValueError('Equip a weapon before using this technique.')
        # Class techniques use their actual equipment and finite ammunition.
        if c['family']=='class':combat.ammunition(w,p,consume=False)
    elif effect=='ally_heal':recipient=ally(w,p,target)
    elif effect=='repair':
        item=living.choose([w.items[i] for i in dict.fromkeys(p.inventory) if w.items.get(i,{}).get('slot') or w.items.get(i,{}).get('type') in ('weapon','armor')],target)
        from engine import society
        if society.durability(p,item['id'])>=100:raise ValueError('That equipment is already fully repaired.')
    elif target.strip() and target.casefold() not in (p.id.casefold(),p.name.casefold()):
        raise ValueError('This ability targets yourself.')
    if effect in ('heal','ally_heal') and recipient.hp>=recipient.max_hp:
        raise ValueError('That character is already at full health.')
    if effect=='cleanse' and not(pr['injury'] or pr['disease']):
        raise ValueError('You have no injury or disease to treat.')
    if effect=='mana_conversion':
        if pr['mana']>=pr['max_mana']:raise ValueError('Your mana is already full.')
        if p.hp<=a.get('health_cost',8):raise ValueError('You do not have enough health to convert safely.')
    # Verify every component before changing mana, inventory, recovery or health.
    from collections import Counter
    needed=Counter(c['components'])
    if enemy is not None and c['family']=='class':needed.update(combat.ammunition(w,p,consume=False))
    for iid,n in needed.items():
        if p.inventory.count(iid)<n:raise ValueError('Requires '+str(n)+' '+w.items.get(iid,{}).get('name',iid)+'.')
    living.consume(p,needed)
    pr['mana']-=cost
    if c['cooldown_minutes']:
        p.progress.setdefault('ability_recovery_v1',{})[a['id']]=living.state(w)['minute']+c['cooldown_minutes']
    if effect in ('ward','guarded_strike'):
        pr['ward']=power if effect=='ward' else a.get('ward_power',2)
        pr['ward_turns']=c['ward_hits']
    if effect=='focus':
        p.progress['ability_focus_v1']={'power':power,'hits':c['ward_hits'],'until':living.state(w)['minute']+a.get('duration_minutes',10)}
        return a['name']+f': weapon attack increased by {power} for up to {c["ward_hits"]} strikes or {a.get("duration_minutes",10)} game minutes.'
    if effect=='sunder':
        enemy.progress['ability_exposed_v1']={'power':a.get('weakness',2),'hits':c['ward_hits'],'until':living.state(w)['minute']+a.get('duration_minutes',5)}
    if effect=='repair':
        p.progress.setdefault('durability',{})[item['id']]=min(100,society.durability(p,item['id'])+power)
        return a['name']+': repaired '+item['name']+' by up to '+str(power)+' durability.'
    if effect=='mana_conversion':
        health_cost=a.get('health_cost',8)
        if health_cost>0:p.take_damage(health_cost,defense=0,cause='health spent on '+a['name'],kind='ability')
        pr['mana']=min(pr['max_mana'],pr['mana']+power)
        return a['name']+f': exchanged {a.get("health_cost",8)} health for up to {power} mana.'
    if enemy is not None:
        return a['name']+': '+combat.strike(w,p,enemy,power=power,
            ignore_defense=c['ignore_defense'] if c['family']=='mage' else False,
            wear=c['family']=='class')
    if effect in ('heal','ally_heal'):
        amount=living.heal(w,recipient,power)
        if recipient.is_player:w.dirty_players=getattr(w,'dirty_players',set())|{recipient.id}
        return a['name']+f': restored {amount} health to {recipient.name}.'
    if effect=='cleanse':
        pr['injury']=max(0,pr['injury']-power);pr['disease']=max(0,pr['disease']-power)
        return a['name']+': reduced injury and disease by up to '+str(power)+'.'
    return a['name']+f": defence increased by {power} for {c['ward_hits']} incoming hits."


def validate(data):
    issues=[]
    ids={k:{r['id'] for r in data.get(k,[])} for k in ('class','race','item')}
    for a in data.get('ability',[]):
        scope=a.get('training_classes',[])
        if not isinstance(scope,list) or any(not isinstance(i,str) or i not in ids['class'] for i in scope):issues.append(a['id']+': training_classes must reference existing classes')
        if 'ability_rules' not in a or a['ability_rules']=={}:continue
        raw=a['ability_rules'];prefix=a['id']+': '
        if not isinstance(raw,dict):issues.append(prefix+'ability_rules must be an object');continue
        c=config(a)
        if c['family'] not in FAMILIES:issues.append(prefix+'unknown ability family')
        if a.get('effect') not in EFFECTS:issues.append(prefix+'unsupported configured ability effect')
        if c['family']!='mage' and a.get('cost_mp',0):issues.append(prefix+'non-mage abilities must not cost mana')
        for field,kind in [('classes','class'),('races','race')]:
            if not isinstance(c[field],list) or any(not isinstance(i,str) or i not in ids[kind] for i in c[field]):issues.append(prefix+field+' must reference existing '+kind+' IDs')
        for field,lo,hi in [('minimum_level',1,100),('cooldown_minutes',0,15000),('ward_hits',1,20)]:
            if type(c[field]) is not int or not lo<=c[field]<=hi:issues.append(prefix+field+f' must be an integer from {lo} to {hi}')
        for field in ('weapon_required','ignore_defense','requires_discovery'):
            if type(c[field]) is not bool:issues.append(prefix+field+' must be true or false')
        if not isinstance(c['components'],dict) or any(i not in ids['item'] or type(n) is not int or not 1<=n<=100 for i,n in c['components'].items()):issues.append(prefix+'components require existing items and whole quantities 1–100')
        if c['family']=='mage' and not c['classes']:issues.append(prefix+'mage spells require explicit eligible classes')
        if c['family']=='race' and not c['races']:issues.append(prefix+'racial powers require explicit eligible races')
        for field in ('power','ward_power','cost_mp','weakness','health_cost','duration_minutes'):
            if type(a.get(field,0)) is not int or not 0<=a.get(field,0)<=1000:issues.append(prefix+field+' must be a whole number from 0 to 1000')
    abilities={a['id']:a for a in data.get('ability',[])}
    for item in data.get('item',[]):
        ident=item.get('prepared_ability')
        if not ident:continue
        a=abilities.get(ident) if isinstance(ident,str) else None
        c=config(a or {})
        if item.get('type')!='consumable' or not c or c['family']!='mage':issues.append(item['id']+': prepared_ability requires a configured mage spell and consumable item')
        if item.get('learn_ability'):issues.append(item['id']+': a prepared scroll cannot also be a learning scroll')
    for kind,field in [('item','teaches_abilities'),('npc','teaches_abilities'),('recipe','required_abilities')]:
        for record in data.get(kind,[]):
            value=record.get(field,[])
            if not isinstance(value,list) or any(not isinstance(i,str) or i not in abilities for i in value):issues.append(record['id']+': '+field+' must reference existing ability IDs')
    return issues


def rows(w,p,query=''):
    """Structured abilities panel: known actions and actual on-site lessons."""
    from engine import living,livelihoods
    school='school' in living.details(w,p.location).get('facilities',[])
    opened=school and livelihoods.room_open(w,p.location)
    result=[]
    for a in sorted(w.abilities.values(),key=lambda a:(a.get('name',''),a['id'])):
        known=a['id'] in p.abilities;c=config(a)
        # Do not expose remote catalogs; schools teach configured eligible classes.
        if not known and (not school or learning_eligibility(w,p,a,ignore_level=True) or (c and c.get('requires_discovery') and a['id'] not in p.progress.get('ability_lessons_v1',[]))):continue
        if query.casefold() not in (a.get('name','')+' '+a.get('description','')).casefold():continue
        family=c['family'] if c else 'legacy'
        detail=a.get('description','')
        if c:
            detail+=f" Level {c['minimum_level']}; recovery {c['cooldown_minutes']} game minutes."
            detail+=f" Mana {a.get('cost_mp',0)}." if family=='mage' else ' Does not use mana.'
            if c['weapon_required']:detail+=' Requires an equipped weapon; normal ammunition rules apply.'
            if c['components']:detail+=' Consumes '+', '.join(str(n)+' '+w.items.get(i,{}).get('name',i) for i,n in c['components'].items())+'.'
        row=dict(id=a['id'],label=a['name'],detail=detail,group=('Known '+family+' abilities') if known else 'School lessons',actions=[],children=[])
        if not known:
            fee=a.get('training_cost',20);reason=learning_eligibility(w,p,a) or ('' if opened else 'This school is closed.')
            if not reason and p.gold<fee:reason=f'Training costs {fee} gold.'
            row['actions']=[dict(label=f'Learn ({fee} gold)',command='study '+a['id'],disabled=bool(reason),reason=reason)]
        else:
            reason=ready(w,p,a);effect=a.get('effect')
            targets=[]
            if effect in ('damage','guarded_strike','sunder','tame'):
                targets=[e for e in w.entities_in_room(p.location) if e.alive and e.id!=p.id and not e.is_player and e.progress.get('companion_owner')!=p.id]
            elif effect=='repair':
                for iid in dict.fromkeys(p.inventory):
                    item=w.items.get(iid,{})
                    if item.get('slot') or item.get('type') in ('weapon','armor'):row['children'].append(dict(id=iid,label=item.get('name',iid),actions=[dict(label='Repair',command='cast '+a['id']+' at '+iid,disabled=bool(reason),reason=reason)]))
            elif effect=='ally_heal':targets=[e for e in w.entities_in_room(p.location) if e.alive and (e.id==p.id or e.progress.get('companion_owner')==p.id)]
            elif effect not in ('enchant','disenchant'):
                row['actions']=[dict(label='Use '+a['name'],command='cast '+a['id'],disabled=bool(reason),reason=reason)]
            else:row['detail']+=' Use an enchanting desk and specify the carried equipment and sigil; this panel does not choose those for you.'
            for e in targets:row['children'].append(dict(id=e.id,label=e.name,actions=[dict(label='Use '+a['name'],command='cast '+a['id']+' at '+e.id,disabled=bool(reason),reason=reason)]))
        result.append(row)
    return result


def invoke(w,p,args):
    """A prepared scroll executes once; it does not teach or require mage training."""
    from copy import deepcopy
    from engine import living
    query,_,target=args.partition(' at ')
    item=living.choose([w.items[i] for i in dict.fromkeys(p.inventory)
                       if i in w.items and w.items[i].get('prepared_ability')],query)
    a=w.abilities.get(item['prepared_ability']);c=config(a or {})
    if item.get('type')!='consumable' or not c or c['family']!='mage':
        raise ValueError('This item does not contain a valid prepared mage spell.')
    # Preparation paid for ingredients already. Only this physical item is spent.
    prepared=deepcopy(a);prepared['cost_mp']=0
    prepared['ability_rules'].update(classes=[],races=[],minimum_level=1,
        cooldown_minutes=0,components={item['id']:1},weapon_required=False)
    # A learned version's recovery is independent of a prepared scroll.
    prepared['id']='prepared:'+item['id']
    return item['name']+': '+cast(w,p,prepared,target)


def scroll_rows(w,p,query=''):
    from collections import Counter
    result=[]
    for iid,n in Counter(p.inventory).items():
        item=w.items.get(iid,{})
        a=w.abilities.get(item.get('prepared_ability'));c=config(a or {})
        if not c or c['family']!='mage':continue
        if query.casefold() not in item.get('name','').casefold():continue
        row=dict(id=iid,label=item['name'],group='Prepared spell scrolls',detail=f'{n} carried. Consumed only on a successful use; no mana cost and does not teach the spell.',actions=[],children=[])
        effect=a.get('effect')
        if effect in ('damage','guarded_strike','sunder'):
            targets=[e for e in w.entities_in_room(p.location) if e.alive and not e.is_player and e.id!=p.id and e.progress.get('companion_owner')!=p.id]
        elif effect=='ally_heal':targets=[e for e in w.entities_in_room(p.location) if e.alive and (e.id==p.id or e.progress.get('companion_owner')==p.id)]
        else:targets=[];row['actions']=[dict(label='Use scroll',command='invoke '+iid)]
        for e in targets:row['children'].append(dict(id=e.id,label=e.name,actions=[dict(label='Use scroll',command='invoke '+iid+' at '+e.id)]))
        result.append(row)
    return result


def disclose(w,p,source):
    known=p.progress.setdefault('ability_lessons_v1',[])
    for ident in source.get('teaches_abilities',[]):
        if ident in w.abilities and ident not in known:known.append(ident)


def combat_bonus(w,actor,key):
    from engine import living
    value=actor.progress.get(key,{})
    return value.get('power',0) if value.get('hits',0)>0 and living.state(w)['minute']<value.get('until',0) else 0


def consume_hit(actor,key):
    value=actor.progress.get(key,{})
    if value:value['hits']=max(0,value.get('hits',0)-1)
