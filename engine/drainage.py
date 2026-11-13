"""Directed waterways on the authored globe, including legacy campaign charts."""
from collections import defaultdict, deque
def chart(rooms):
    byid={r['id']:r for r in rooms}
    inbound=defaultdict(list)
    outlets=[]
    for row in rooms:
        info=row.get('waterway') or {}
        kind=info.get('kind',row.get('environment'))
        if kind=='ocean':
            outlets.append(row['id'])
        if kind not in ('river','stream','tributary','lake') or not info:continue
        direction=info.get('flow')
        for di,dest in row.get('exits',{}).items():
            if di not in ('north','south','east','west') or dest not in byid:continue
            if direction in ('north','south','east','west') and direction!=di:continue
            other=byid[dest]
            target=other.get('waterway') or {}
            recv=target.get('kind',other.get('environment'))
            joins=(recv=='ocean' or target.get('name') and (target['name']==info.get('name') or
                   target['name']==info.get('outlet') or (recv=='lake' and target.get('outlet')==info.get('name'))))
            if not joins:continue
            upper=(row.get('climate') or {}).get('elevation_m')
            lower=(other.get('climate') or {}).get('elevation_m')
            if isinstance(upper,(int,float)) and isinstance(lower,(int,float)) and recv!='ocean' and lower>upper:continue
            inbound[dest].append(row['id'])
            if direction==di:row['_downstream']=dest
    visited=set(outlets)
    queue=deque(outlets)
    while queue:
        dest=queue.popleft()
        for upstream in inbound[dest]:
            if upstream in visited:continue
            visited.add(upstream);queue.append(upstream)
            row=byid[upstream]
            row['_downstream']=dest
