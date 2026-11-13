"""Atomic, need-aware NPC commerce. Player offers are handled by SocietyServer."""
from engine import relationships, social, society, needs_market, npc_attention, livelihoods

def quote_context(w,n):
    """One synchronous preview's demand index; never cached across actions."""
    applies=livelihoods.applies(w,n)
    return dict(valid=not n.is_player and n.alive and relationships.profile(w,n)['sentient'],
                applies=applies,demand=livelihoods.reasons(w,n) if applies else {},
                job=livelihoods.job_needs(w,n) if applies else {},prefs=social.prefs(w,n) if not applies else {})

def interested(w,n,iid,context=None):
    if context is not None:
        if iid not in w.items or not context['valid']:return False
        if context['applies']:return iid in context['demand']
        cfg=context['prefs']
        return iid not in cfg['disliked_items'] and (iid in cfg['wanted_items'] or w.items[iid].get('type') in cfg['wanted_types'])
    if iid not in w.items or n.is_player or not n.alive or not relationships.profile(w,n)['sentient']:return False
    if livelihoods.applies(w,n):return iid in livelihoods.reasons(w,n)
    cfg=social.prefs(w,n)
    return iid not in cfg['disliked_items'] and (iid in cfg['wanted_items'] or w.items[iid].get('type') in cfg['wanted_types'])

def eligible(w,p,n):
    if not p.alive or not n.alive or p.id==n.id or p.location!=n.location:raise ValueError('Meet a living trader in the same location.')
    if n.is_player or not relationships.profile(w,n)['sentient']:raise ValueError('Choose a sentient NPC; players must accept an exchange offer.')
    if not livelihoods.awake(w,n):raise ValueError(n.name+' is sleeping. Return during waking hours.')
    if not livelihoods.service_open(w,n):raise ValueError(n.name+' is off duty or the business is closed. '+livelihoods.hours_text(w,n))
    if society.friendliness(w,p,n)<=50:raise ValueError('Trade requires the same faction or mutual friendliness above 50%.')

def value(w,n,iid,context=None):
    if context is not None:
        if context['applies'] and context['demand'].get(iid,'').startswith('recover '):
            return max(1,sum(w.items[i].get('value',1)*q for i,q in w.items[iid].get('salvage',{}).items() if i in context['job']))
        return needs_market.quote(w,iid,n.inventory.count(iid),2,group=n.group_id)
    if livelihoods.applies(w,n) and livelihoods.reasons(w,n).get(iid,'').startswith('recover '):
        job=livelihoods.job_needs(w,n)
        return max(1,sum(w.items[i].get('value',1)*q for i,q in w.items[iid].get('salvage',{}).items() if i in job))
    return needs_market.quote(w,iid,n.inventory.count(iid),2,group=n.group_id)

def sale(w,p,n,iid):
    eligible(w,p,n)
    if iid not in p.inventory or iid in p.equipped.values():raise ValueError('Carry an unequipped item.')
    if not interested(w,n,iid):raise ValueError(n.name+' does not want that item right now.')
    cost=max(1,value(w,n,iid)//2)
    if n.gold<cost:raise ValueError(n.name+' cannot afford it right now.')
    npc_attention.begin(w,p,n)
    p.inventory.remove(iid);n.inventory.append(iid);n.gold-=cost;p.gold+=cost
    livelihoods.receive(w,n,iid) if livelihoods.applies(w,n) else needs_market.use(w,n,iid)
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[n.id],f"Bought {w.items[iid]['name']} for {cost} gold.")
    return 'Sold '+w.items[iid]['name']+' to '+n.name+' for '+str(cost)+' gold.'

def swap(w,p,n,give,take):
    eligible(w,p,n)
    if give==take:raise ValueError('Choose different items.')
    if give not in p.inventory or give in p.equipped.values():raise ValueError('Carry the unequipped item you offer.')
    if take not in n.inventory or take in n.equipped.values():raise ValueError('The requested item is no longer available.')
    if not interested(w,n,give):raise ValueError(n.name+' does not want your offer.')
    if interested(w,n,take):raise ValueError(n.name+' needs that possession and will not trade it.')
    if value(w,n,give)<value(w,n,take):raise ValueError('Your offered item is worth less than the requested item.')
    npc_attention.begin(w,p,n)
    p.inventory.remove(give);n.inventory.remove(take);n.inventory.append(give);p.inventory.append(take)
    livelihoods.receive(w,n,give) if livelihoods.applies(w,n) else needs_market.use(w,n,give)
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[n.id],f"Traded {w.items[take]['name']} for {w.items[give]['name']}.")
    return 'Traded '+w.items[give]['name']+' for '+w.items[take]['name']+' with '+n.name+'.'

def view(w,p,n):
    try:eligible(w,p,n)
    except ValueError:return dict(buying=[],offering=[])
    wanted=set(social.prefs(w,n)['wanted_items']);cfg=social.prefs(w,n,include_needs=False)
    demand=livelihoods.reasons(w,n) if livelihoods.applies(w,n) else None
    def likes(i):return i in demand if demand is not None else i not in cfg['disliked_items'] and (i in wanted or w.items.get(i,{}).get('type') in cfg['wanted_types'])
    return dict(buying=[dict(id=i,name=w.items[i]['name'],reason=(demand or {}).get(i,'personal interest'),price=max(1,value(w,n,i)//2),affordable=n.gold>=max(1,value(w,n,i)//2)) for i in dict.fromkeys(p.inventory) if i in w.items and i not in p.equipped.values() and likes(i)],offering=[dict(id=i,name=w.items[i]['name'],value=value(w,n,i)) for i in dict.fromkeys(n.inventory) if i in w.items and i not in n.equipped.values() and not likes(i)])
