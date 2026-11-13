"""One canonical exit name across gameplay, editing, and ASCII maps."""
ALIASES = dict(n='north',s='south',e='east',w='west',ne='northeast',nw='northwest',se='southeast',sw='southwest',u='up',d='down')

def direction(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('Exit direction must be nonempty text.')
    key=value.strip().lower()
    return ALIASES.get(key,key)

def normalize_exits(exits):
    if not isinstance(exits,dict): raise ValueError('Exits must be a direction-to-room object.')
    result={}
    for raw,target in exits.items():
        key=direction(raw)
        if key in result and result[key]!=target:
            raise ValueError(f"Conflicting {key} exits lead to '{result[key]}' and '{target}'. Choose one destination in the editor.")
        result[key]=target
    return result
