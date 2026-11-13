"""Editable combinations: tools + components + target produce an effect."""
from engine import living

def combine(ctx,args):
    query,_,target=args.partition(' on ')
    rule=living.choose(list(getattr(ctx.world,'interactions',{}).values()),query)
    p,w=ctx.player,ctx.world
    if rule.get('tool') and rule['tool'] not in p.inventory:raise ValueError('You need '+w.items[rule['tool']]['name']+'.')
    effect=rule.get('interaction_effect','create')
    if effect=='damage':
        from engine import combat
        victim=combat.target(w,p,target)
        combat.validate(w,p,victim)
        tool=rule.get('tool')
        if tool and w.items.get(tool,{}).get('type')=='weapon' and __import__('engine.society',fromlist=['durability']).durability(p,tool)<=0:raise ValueError('Repair the broken tool before attacking.')
        ammo=w.items.get(tool,{}).get('requires_ammo')
        if ammo and rule.get('components',{}).get(ammo,0)<1:raise ValueError('This attack recipe must include its weapon ammunition.')
    elif effect=='repair':
        if target not in p.inventory or w.items[target].get('type') not in ('weapon','armor'):raise ValueError('Choose a carried weapon or armor item ID.')
    living.consume(p,rule.get('components',{}))
    if effect=='damage':
        power=rule.get('power',0)
        if tool and w.items.get(tool,{}).get('type')=='weapon':power+=p.attack+w.items[tool].get('attack_bonus',0)+p.progress.get('enchants',{}).get(tool,{}).get('attack',0)
        return combat.strike(w,p,victim,power=power,wear=False)
    if effect=='repair':p.progress.setdefault('durability',{})[target]=100
    if effect=='heal':living.heal(w,p,rule.get('power',0))
    for iid,n in rule.get('outputs',{}).items():p.inventory.extend([iid]*n)
    return rule.get('result_text','Combination completed.')
