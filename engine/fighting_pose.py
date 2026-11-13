"""Ephemeral fighting poses follow actual nearby combat. Never written into a save."""
from time import monotonic

DURATION = 4.0
STANCES = ('unarmed','blade','dagger','haft','spear','staff','bow','shield','dual','instrument','natural')

def mark(actor, *, defending=False, projectile=False):
    actor._fight_display=(actor.location,monotonic()+DURATION,defending,projectile)

def stance(world,actor,gear,creature=False):
    main=next((g for g in gear if g.get('slot') in ('weapon','mainhand') and g.get('item_id')),None)
    off=next((g for g in gear if g.get('slot')=='offhand' and g.get('item_id')),None)
    shield=bool(off and off.get('kind')=='shield')
    item=world.items.get(main['item_id'],{}) if main else {}
    override=item.get('fighting_stance')
    if override in STANCES:style=override
    elif off and main and world.items.get(off['item_id'],{}).get('type')=='weapon' and not shield:style='dual'
    elif main:
        kind=main.get('kind')
        style={'bow':'bow','spear':'spear','staff':'staff','dagger':'dagger','lute':'instrument',
               'axe':'haft','hammer':'haft','mace':'haft','pick':'haft'}.get(kind,'blade')
        if item.get('requires_ammo'):style='bow'
    else:style='shield' if shield else 'natural' if creature else 'unarmed'
    return style,shield

def project(world,actor,gear,creature=False):
    active=getattr(actor,'_fight_display',None)
    if not active or active[0]!=actor.location or not actor.alive or active[1]<=monotonic():return None
    style,shield=stance(world,actor,gear,creature)
    return dict(stance=style,shield=shield,defending=active[2],projectile=active[3] and style=='bow')
