"""Opt-in ability families. Legacy definitions retain their existing execution.

Authoritative checks apply to learning and use, including scroll lessons. Recovery
uses saved world minutes, never wall-clock timers or a permanent one-use flag.
"""
from engine.item_catalog import counted
from engine import classless
FAMILIES = ('mage', 'class', 'race')
EFFECTS = ('damage', 'ward', 'heal', 'ally_heal', 'cleanse', 'guarded_strike', 'focus', 'sunder', 'repair', 'mana_conversion', 'raise_dead', 'summon', 'resurrection', 'teleport', 'light', 'ally_ward', 'relief', 'weather_guard')
PREPARED_UNSUPPORTED = ('raise_dead','summon','resurrection','teleport','light','ally_ward','relief','weather_guard')
DEFAULTS = dict(family='class', classes=[], races=[], minimum_level=1,
                cooldown_minutes=0, weapon_required=False, ward_hits=5,
                ignore_defense=False, components={}, requires_discovery=False)


def config(a):
    raw=a.get('ability_rules')
    return {**DEFAULTS, **raw} if isinstance(raw,dict) and raw else None


def eligibility(w,p,a,ignore_level=False):
    c=config(a)
    if not c:return ''
    actual_class,actual_race=p.char_class,p.race
    level=p.progress.get('advancement_v1',{}).get('level',1)
    if not p.is_player and c['family']=='mage':
        from engine import npc_spellcasting
        discipline=npc_spellcasting.discipline(w,p)
        if discipline:
            actual_class,actual_race,level=discipline['char_class'],discipline['race'],discipline['level']
    for field,actual,defs in [('classes',actual_class,w.classes),('races',actual_race,w.races)]:
        if c[field] and actual not in c[field] and not (field == "classes" and classless.converted(p,a)):
            return 'Requires '+', '.join(defs.get(i,{}).get('name',i) for i in c[field])+'.'
    from engine import progression
    if not ignore_level and progression.config(w)['enabled'] and level<c['minimum_level']:
        return f"Requires level {c['minimum_level']}."
    return ''


def ready(w,p,a):
    from engine import living
    reason=eligibility(w,p,a)
    if reason:return reason
    c=config(a)
    if not c:return ''
    until=p.progress.get('ability_recovery_v1',{}).get(a['id'],0)
    from engine.worldtime import initial_minute
    left=max(0,until-getattr(w,'living_state',{}).get('minute',initial_minute(w.metadata)))
    if left:return f'You can use this ability again in {counted(left,"game minute")}.'
    return ''


def learning_eligibility(w,p,a,ignore_level=False):
    classes=a.get('training_classes',[])
    if classes and p.char_class not in classes and not classless.converted(p,a):return 'Training is for '+', '.join(w.classes.get(i,{}).get('name',i) for i in classes)+'. Already-learned legacy abilities are retained.'
    return eligibility(w,p,a,ignore_level=ignore_level)


def lesson_check(w,p,a,*,via_school=False):
    reason=classless.study_reason(w,p,a,via_school=via_school)
    if reason:raise ValueError(reason)
    c=config(a)
    if c and c.get('requires_discovery') and a['id'] not in p.progress.get('ability_lessons_v1',[]):
        raise ValueError('Read the relevant training handbook or speak to its instructor first.')
    reason=learning_eligibility(w,p,a)
    if reason:raise ValueError(reason)


def _local(w,p):
    return list({e.id:e for e in w.entities_in_room(p.location) if e.alive
                 and e.location==p.location and w.entities.get(e.id) is e}.values())


def ally(w,p,target,*,allow_players=False,allowed_npcs=()):
    if not target.strip():return p
    matches=[e for e in _local(w,p) if
             (e.id==p.id or e.progress.get('companion_owner')==p.id or allow_players and e.is_player or e in allowed_npcs) and
             target.casefold() in (e.id.casefold(),e.name.casefold())]
    if len(matches)!=1:raise ValueError('Choose yourself, a living player or one of your living companions here.' if allow_players else 'Choose yourself or one of your living companions here.')
    return matches[0]


def cast(w,p,a,target):
    """Use an actual learned definition; prepared items have a separate entry."""
    actual=w.abilities.get(a.get('id')) if isinstance(a,dict) else None
    if actual is None or actual!=a or a['id'] not in p.abilities:
        raise ValueError('You must actually know that ability before casting it.')
    return _cast(w,p,actual,target)


def cast_npc(w,p,a,target,*,lawful=False,counter=False,allowed_allies=()):
    """Internal NPC turn entry; player commands cannot request lawful casts."""
    from engine import npc_spellcasting
    policy=npc_spellcasting.config(w,p)
    if p.is_player or not policy or a.get('id') not in policy['abilities'] or a['id'] not in p.abilities or w.abilities.get(a['id'])!=a:
        raise ValueError('This NPC is not trained to cast that authored spell.')
    allowed=[e for e in allowed_allies if w.entities.get(getattr(e,'id',None)) is e and e.alive
             and not e.is_player and e.location==p.location and (e.id==p.id or p.group_id and e.group_id==p.group_id)
             and not e.progress.get('companion_owner')]
    if a.get('effect')!='damage':
        permitted={p.id}|({e.id for e in allowed} if a.get('effect')=='ally_heal' else set())
        if target not in permitted:raise ValueError('An autonomous support spell requires an actual friendly responder in this fight.')
    return _cast(w,p,a,target,lawful=lawful,counter=counter,npc_allies=allowed)


def _cast(w,p,a,target,*,lawful=False,counter=True,npc_allies=None):
    """All preflight precedes costs; every cue follows a completed real effect."""
    from engine import living,combat,magic_visuals,spell_life,spell_travel,spell_utility
    if not isinstance(target,str):raise ValueError('Choose a target by its name or ID.')
    if not p.alive or p.progress.get('permanently_dead') or w.entities.get(p.id) is not p:raise ValueError('You must be alive and present to use an ability.')
    c=config(a)
    reason=ready(w,p,a)
    if reason:raise ValueError(reason)
    effect=a.get('effect');power=a.get('power',0);pr=p.progress
    if effect not in EFFECTS:raise ValueError('This configured ability has no supported effect.')
    cost=a.get('cost_mp',0) if c['family']=='mage' else 0
    if pr.get('mana',20)<cost:raise ValueError('Not enough mana. Rest at an inn or camp.')
    enemy=None;recipient=p;plan=None
    if effect in ('damage','guarded_strike','sunder'):
        enemy=combat.target(w,p,target);combat.validate(w,p,enemy)
        if c['weapon_required'] and not any(w.items.get(i,{}).get('type')=='weapon' for i in p.equipped.values()):
            raise ValueError('Equip a weapon before using this technique.')
        # Class techniques use their actual equipment and finite ammunition.
        if c['family']=='class':combat.ammunition(w,p,consume=False)
    elif effect=='ally_heal':recipient=ally(w,p,target,allow_players=c.get('ally_players') is True and npc_allies is None,allowed_npcs=npc_allies or ())
    elif effect in spell_life.EFFECTS:plan=spell_life.prepare(w,p,a,target)
    elif effect=='teleport':plan=spell_travel.prepare(w,p,a,target)
    elif effect in spell_utility.EFFECTS:plan=spell_utility.prepare(w,p,a,target)
    elif effect=='repair':
        item=living.choose([w.items[i] for i in dict.fromkeys(p.inventory) if w.items.get(i,{}).get('slot') or w.items.get(i,{}).get('type') in ('weapon','armor')],target)
        from engine import society
        if society.durability(p,item['id'])>=100:raise ValueError('That equipment is already fully repaired.')
    elif target.strip() and target.casefold() not in (p.id.casefold(),p.name.casefold()):
        raise ValueError('This ability targets yourself.')
    if effect in ('heal','ally_heal') and recipient.hp>=recipient.max_hp:
        raise ValueError('That character is already at full health.')
    if effect=='cleanse' and not(pr.get('injury',0) or pr.get('disease',0)):
        raise ValueError('You have no injury or disease to treat.')
    if effect=='mana_conversion':
        if pr.get('mana',20)>=pr.get('max_mana',20):raise ValueError('Your mana is already full.')
        if p.hp<=a.get('health_cost',8):raise ValueError('You do not have enough health to convert safely.')
    # Verify every component before changing mana, inventory, recovery or health.
    from collections import Counter
    needed=Counter(c['components'])
    if enemy is not None and c['family']=='class':needed.update(combat.ammunition(w,p,consume=False))
    for iid,n in needed.items():
        if p.inventory.count(iid)<n:raise ValueError('Requires '+str(n)+' '+w.items.get(iid,{}).get('name',iid)+'.')
    witness_ids=magic_visuals.witnesses(w,p.location)
    committed=False
    def commit():
        nonlocal committed,pr
        if committed:return
        living.consume(p,needed)
        pr=living.progress(p);pr['mana']-=cost
        if c['cooldown_minutes']:
            p.progress.setdefault('ability_recovery_v1',{})[a['id']]=living.state(w)['minute']+c['cooldown_minutes']
        committed=True
    def finish(text,targets,changed=True):
        commit()
        if changed:magic_visuals.record(w,a.get('presentation'),p,targets,witnesses=witness_ids)
        return text
    if effect in spell_life.EFFECTS:
        text=spell_life.execute(w,p,a,plan);commit();return text
    if effect=='teleport':
        text=spell_travel.execute(w,p,a,plan);commit();return text
    if effect in spell_utility.EFFECTS:
        text=spell_utility.execute(w,p,a,plan);commit();return text
    pr=living.progress(p)
    if effect in ('ward','guarded_strike'):
        pr['ward']=power if effect=='ward' else a.get('ward_power',2)
        pr['ward_turns']=c['ward_hits']
    if effect=='focus':
        p.progress['ability_focus_v1']={'power':power,'hits':c['ward_hits'],'until':living.state(w)['minute']+a.get('duration_minutes',10)}
        return finish(a['name']+f': weapon attack increased by {power} for up to {c["ward_hits"]} strikes or {a.get("duration_minutes",10)} game minutes.',[p],power>0)
    if effect=='sunder':
        enemy.progress['ability_exposed_v1']={'power':a.get('weakness',2),'hits':c['ward_hits'],'until':living.state(w)['minute']+a.get('duration_minutes',5)}
    if effect=='repair':
        p.progress.setdefault('durability',{})[item['id']]=min(100,society.durability(p,item['id'])+power)
        return finish(a['name']+': repaired '+item['name']+' by up to '+str(power)+' durability.',[p],power>0)
    if effect=='mana_conversion':
        commit()
        health_cost=a.get('health_cost',8)
        if health_cost>0:p.take_damage(health_cost,defense=0,cause='health spent on '+a['name'],kind='ability')
        pr['mana']=min(pr['max_mana'],pr['mana']+power)
        return finish(a['name']+f': exchanged {a.get("health_cost",8)} health for up to {power} mana.',[p],power>0 or health_cost>0)
    if enemy is not None:
        before=enemy.hp
        text=a['name']+': '+combat.strike(w,p,enemy,power=power,
            ignore_defense=c['ignore_defense'] if c['family']=='mage' else False,
            wear=c['family']=='class',lawful=lawful,counter=counter)
        return finish(text,[enemy],enemy.hp<before)
    if effect in ('heal','ally_heal'):
        amount=living.heal(w,recipient,power)
        if recipient.is_player:w.dirty_players=getattr(w,'dirty_players',set())|{recipient.id}
        return finish(a['name']+f': restored {amount} health to {recipient.name}.',[recipient],amount>0)
    if effect=='cleanse':
        pr['injury']=max(0,pr['injury']-power);pr['disease']=max(0,pr['disease']-power)
        return finish(a['name']+': reduced injury and disease by up to '+str(power)+'.',[p],power>0)
    return finish(a['name']+f": defence increased by {power} for {c['ward_hits']} incoming hits.",[p],power>0)


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
        if a and a.get('effect') in PREPARED_UNSUPPORTED:issues.append(item['id']+': life, travel and utility spells must be learned and cannot be prepared scrolls')
        if c and c.get('races'):issues.append(item['id']+': race-specific spells must be learned and cannot be prepared scrolls')
        if item.get('learn_ability'):issues.append(item['id']+': a prepared scroll cannot also be a learning scroll')
    for kind,field in [('item','teaches_abilities'),('npc','teaches_abilities'),('recipe','required_abilities')]:
        for record in data.get(kind,[]):
            value=record.get(field,[])
            if not isinstance(value,list) or any(not isinstance(i,str) or i not in abilities for i in value):issues.append(record['id']+': '+field+' must reference existing ability IDs')
    from engine import spell_life,spell_travel,spell_utility,npc_spellcasting,magic_visuals
    return issues+spell_life.validate(data)+spell_travel.validate(data)+spell_utility.validate(data)+npc_spellcasting.validate(data)+magic_visuals.validate(data)


def rows(w,p,query=''):
    """Structured abilities panel: known actions and actual on-site lessons."""
    from engine import living,livelihoods
    school='school' in living.details(w,p.location).get('facilities',[])
    opened=school and livelihoods.room_open(w,p.location)
    result=[]
    for a in sorted(w.abilities.values(),key=lambda a:(a.get('name',''),a['id'])):
        known=a['id'] in p.abilities;c=config(a)
        # Do not expose remote catalogs; schools teach configured eligible classes.
        if not known and (not school or classless.study_reason(w,p,a,via_school=True,preview=True) or learning_eligibility(w,p,a,ignore_level=True) or (c and c.get('requires_discovery') and a['id'] not in p.progress.get('ability_lessons_v1',[]))):continue
        if query.casefold() not in (a.get('name','')+' '+a.get('description','')).casefold():continue
        family=c['family'] if c else 'legacy'
        detail=a.get('description','')
        if c:
            detail+=f" Level {c['minimum_level']}; recovery {c['cooldown_minutes']} game minutes."
            detail+=f" Mana {a.get('cost_mp',0)}." if family=='mage' else ' Does not use mana.'
            if c['weapon_required']:detail+=' Requires an equipped weapon; normal ammunition rules apply.'
            if c['components']:detail+=' Consumes '+', '.join(str(n)+' '+w.items.get(i,{}).get('name',i) for i,n in c['components'].items())+'.'
        row=dict(id=a['id'],label=a['name'],detail=detail,group=('Known spells' if family=='mage' else 'Known '+family+' abilities') if known else 'School lessons',actions=[],children=[])
        if not known:
            fee=a.get('training_cost',20);reason=learning_eligibility(w,p,a) or ('' if opened else 'This school is closed.') or classless.study_reason(w,p,a,via_school=True)
            if not reason and p.gold<fee:reason=f'Training costs {fee} gold.'
            row['actions']=[dict(label=f'Learn ({fee} gold)',command='study '+a['id'],disabled=bool(reason),reason=reason)]
        else:
            reason=ready(w,p,a);effect=a.get('effect')
            targets=[]
            if effect in ('damage','guarded_strike','sunder','tame'):
                targets=[e for e in _local(w,p) if e.id!=p.id and not e.is_player and e.progress.get('companion_owner')!=p.id]
            elif effect=='repair':
                for iid in dict.fromkeys(p.inventory):
                    item=w.items.get(iid,{})
                    if item.get('slot') or item.get('type') in ('weapon','armor'):row['children'].append(dict(id=iid,label=item.get('name',iid),actions=[dict(label='Repair',command='cast '+a['id']+' at '+iid,disabled=bool(reason),reason=reason)]))
            elif effect=='ally_heal':targets=[e for e in _local(w,p) if e.id==p.id or e.progress.get('companion_owner')==p.id or c.get('ally_players') is True and e.is_player]
            elif effect in ('raise_dead','resurrection'):
                from engine import spell_life
                targets=spell_life.targets(w,p,a)
            elif effect in ('light','ally_ward','relief','weather_guard'):
                from engine import spell_utility
                targets=spell_utility.targets(w,p,a)
            elif effect=='teleport':
                from engine import spell_travel
                for place in spell_travel.targets(w,p,a):
                    row['children'].append(dict(id=place['id'],label=place['name'],actions=[dict(label='Travel',command='cast '+a['id']+' at '+place['id'],disabled=bool(reason),reason=reason)]))
            elif effect not in ('enchant','disenchant'):
                row['actions']=[dict(label='Use '+a['name'],command='cast '+a['id'],disabled=bool(reason),reason=reason)]
            else:row['detail']+=' Use an enchanting desk and specify the carried equipment and sigil; this panel does not choose those for you.'
            for e in targets:row['children'].append(dict(id=e.id,label=e.name,actions=[dict(label='Use '+a['name'],command='cast '+a['id']+' at '+e.id,disabled=bool(reason),reason=reason)]))
        result.append(row)
    return result


def cast_legacy(ctx,a,target):
    """Legacy spells keep their authored mechanics, with checked success cues."""
    from engine import living,combat,magic_visuals,spell_travel
    w,p=ctx.world,ctx.player
    if not p.alive or p.progress.get('permanently_dead') or w.entities.get(p.id) is not p:raise ValueError('You must be alive and present to cast a spell.')
    if w.abilities.get(a.get('id'))!=a or a['id'] not in p.abilities:raise ValueError('You must actually know that spell.')
    pr=living.progress(p);cost=a.get('cost_mp',0)
    if pr['mana']<cost:raise ValueError('Not enough mana. Rest at an inn or camp.')
    effect=a.get('effect');power=a.get('power',5)
    if effect in ('heal','ward') and target.strip() and target.strip().casefold() not in (p.id.casefold(),p.name.casefold()):
        raise ValueError('This spell targets yourself. Use an ally-healing spell for another player.')
    if effect=='group_heal' and target.strip():
        raise ValueError('This spell affects the living players gathered here and does not take an individual target.')
    witness_ids=magic_visuals.witnesses(w,p.location)
    def finish(text,targets,changed=True):
        if changed:
            pr['mana']-=cost
            magic_visuals.record(w,a.get('presentation'),p,targets,witnesses=witness_ids)
        return text
    if effect=='heal':
        if p.hp>=p.max_hp:raise ValueError('You are already at full health.')
        amount=living.heal(w,p,power)
        return finish('Healing magic restores '+str(amount)+' health.',[p],amount>0)
    if effect=='ward':
        pr['ward']=a.get('power',3);pr['ward_turns']=5
        return finish('A protective ward strengthens your defence for five incoming hits.',[p])
    if effect=='group_heal':
        targets=[e for e in _local(w,p) if e.is_player and e.hp<e.max_hp]
        if not targets:raise ValueError('The players gathered here are already at full health.')
        healed=[e for e in targets if living.heal(w,e,a.get('power',10))>0]
        return finish('Your song restores health to the players gathered here.',healed,bool(healed))
    if effect=='tame':
        nearby=[e for e in _local(w,p) if not e.is_player]
        before={e.id:e.progress.get('companion_owner') for e in nearby}
        text=living.command(ctx,target,'tame')
        changed=[e for e in nearby if before[e.id]!=p.id and (e.progress.get('companion_owner')==p.id or e.id not in w.entities)]
        return finish(text,[e for e in changed if e.id in w.entities],bool(changed))
    if effect=='escape':
        if target.strip():raise ValueError('This return spell does not accept a target.')
        plan=spell_travel.prepare_escape(w,p,a)
        text=spell_travel.execute(w,p,a,plan)
        pr['mana']-=cost
        return text
    if effect=='enchant':
        before=dict(pr['enchants'])
        text=living.command(ctx,target,'enchant')
        return finish(text,[p],before!=pr['enchants'])
    if effect=='disenchant':
        obj=living.choose([w.items[i] for i in p.inventory if i in w.items and i in pr['enchants']],target)
        del pr['enchants'][obj['id']]
        return finish('The enchantment is removed; the sigil is not recovered.',[p])
    if effect!='damage':raise ValueError('This ability has no implemented effect. Ask the creator to choose an effect.')
    enemy=combat.target(w,p,target);combat.validate(w,p,enemy);before=enemy.hp
    text=a['name']+': '+combat.strike(w,p,enemy,power=power,ignore_defense=True,wear=False)
    return finish(text,[enemy],enemy.hp<before)


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
    if a.get('effect') in PREPARED_UNSUPPORTED or c.get('races'):
        raise ValueError('This spell must be learned and cast with its normal training, resources and recovery.')
    # Preparation paid for ingredients already. Only this physical item is spent.
    prepared=deepcopy(a);prepared['cost_mp']=0
    prepared['ability_rules'].update(classes=[],races=[],minimum_level=1,
        cooldown_minutes=0,components={item['id']:1},weapon_required=False)
    # A learned version's recovery is independent of a prepared scroll.
    prepared['id']='prepared:'+item['id']
    return item['name']+': '+_cast(w,p,prepared,target)


def scroll_rows(w,p,query=''):
    from collections import Counter
    result=[]
    for iid,n in Counter(p.inventory).items():
        item=w.items.get(iid,{})
        a=w.abilities.get(item.get('prepared_ability'));c=config(a or {})
        if not c or c['family']!='mage' or a.get('effect') in PREPARED_UNSUPPORTED or c.get('races'):continue
        if query.casefold() not in item.get('name','').casefold():continue
        row=dict(id=iid,label=item['name'],group='Prepared spell scrolls',detail=f'{n} carried. Consumed only on a successful use; no mana cost and does not teach the spell.',actions=[],children=[])
        effect=a.get('effect')
        if effect in ('damage','guarded_strike','sunder'):
            targets=[e for e in _local(w,p) if not e.is_player and e.id!=p.id and e.progress.get('companion_owner')!=p.id]
        elif effect=='ally_heal':targets=[e for e in _local(w,p) if e.id==p.id or e.progress.get('companion_owner')==p.id or c.get('ally_players') is True and e.is_player]
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
