"""Nearby-only, authoritative companion acquisition advice."""
from engine import living, society, relationships, livelihoods

def requirement(w,p,e):
    d=w.npcs.get(e.source_def,{})
    if e.progress.get('zoo_exhibit') or d.get('zoo_exhibit'):
        raise ValueError('Zoo exhibits are protected regional animals and cannot be taken as companions.')
    if e.is_player or e.location!=p.location or not d.get('tameable'):raise ValueError('Choose a tameable creature that is here now.')
    if not p.alive or not e.alive:raise ValueError('Both you and the creature must be alive.')
    if e.progress.get('companion_owner'):raise ValueError('That animal already has a caregiver.')
    from engine import companion_union
    if companion_union.eligible(w,p):companion_union.check_space(w,p,new=True)
    elif len(living.progress(p)['companions'])>=2:raise ValueError('You can travel with at most two companions.')
    if society.enabled(w):
        if not livelihoods.awake(w,e):raise ValueError('The creature is sleeping. Return when it is awake.')
        relationships.eligible(w,p,e,'companion')
    bait=d.get('tame_item')
    if bait and bait not in w.items:raise ValueError('This creature has an unavailable food requirement. Ask the world creator to repair it.')
    if bait and bait not in p.inventory:raise ValueError('You need one '+w.items[bait]['name']+' to tame '+e.name+'.')
    if bait and bait in p.equipped.values():raise ValueError('Unequip the required food before offering it.')
    return bait

def view(w,p):
    if not living.enabled(w):return []
    rows=[]
    for e in w.entities_in_room(p.location):
        d=w.npcs.get(e.source_def,{})
        if e.is_player or e.location!=p.location or not d.get('tameable'):continue
        bait=d.get('tame_item');reason=''
        try:requirement(w,p,e)
        except ValueError as err:reason=str(err)
        rows.append(dict(id=e.id,name=e.name,food=w.items.get(bait,{}).get('name','No food required' if not bait else 'Unavailable food'),blocked=reason))
    return rows

def advice(w,p):
    rows=view(w,p)
    return '\n'.join(r['name']+': '+r['food']+'. '+(r['blocked'] or 'Ready. Use tame '+r['name']+'.') for r in rows) or 'No tameable creature here. Look for a companion yard and read its field notes.'
