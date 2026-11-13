"""Shared authored faction relationship policy, with legacy behavior preserved."""
STATES = ('allied', 'tolerated', 'neutral', 'hostile')


def relation(group, other):
    if not group:return 'neutral'
    target=other or 'unaffiliated'
    if group.get('id')==target:return 'allied'
    explicit=group.get('relations',{}).get(target)
    if explicit in STATES:return explicit
    return 'hostile' if target in group.get('hostile_to',[]) or '*' in group.get('hostile_to',[]) else 'neutral'


def bounds(group, source, target):
    if source==target:return 100,100,100
    rule=group.get('diplomacy',{}).get(target,{})
    # Preserve old society behavior exactly, including wildcard distinction.
    old=group.get('relations',{}).get(target,'hostile' if target in group.get('hostile_to',[]) else 'neutral')
    base=rule.get('base',{'allied':100,'tolerated':60,'neutral':50,'hostile':0}.get(old,50))
    return rule.get('minimum',0),rule.get('maximum',100),base
