"""Public activity visible to someone in the same room, projected without advancing time."""
from time import monotonic
from engine import item_catalog

def note(actor,kind,label,seconds=15):
    if not actor.is_player and actor.alive:
        actor._visible_action=(actor.location,monotonic()+seconds,kind,label)

def activity(w,actor):
    source=str(getattr(actor,'activity','') or '').strip()
    low=source.casefold()
    if low.startswith('sleep'):return dict(kind='sleep',label='Sleeping')
    leases=getattr(w,'trade_attention',{}).get(actor.id,{})
    if any(record.get('room')==actor.location and record.get('expires',0)>monotonic() for record in leases.values()):
        return dict(kind='trade',label='Trading')
    recent=getattr(actor,'_visible_action',None)
    if recent and recent[0]==actor.location and recent[1]>monotonic():
        return dict(kind=recent[2],label=recent[3])
    definition=w.npcs.get(actor.source_def,{})
    commute=getattr(w,'_commute_routes',{}).get(actor.id)
    if commute and commute[1] and commute[0]!=actor.location:
        destination=commute[0]
        if destination==definition.get('home_room'):return dict(kind='walk',label='Walking home')
        if destination in (definition.get('work_room'),definition.get('workplace_room')):return dict(kind='walk',label='Heading to work')
        return dict(kind='walk',label='Travelling')
    for tokens,kind in [
        (('travell','returning home','commut','walking','driving','viewing a home'),'walk'),
        (('buy','trad','market','shop','sell'),'trade'),(('forag','harvest','gather','tend'),'harvest'),
        (('hunt','stalk'),'hunt'),(('patrol','guard'),'patrol'),(('study','learn','read','school','teach'),'study'),
        (('perform','entertain','music','tavern','leisure'),'music'),(('cook','eat','feed','drink','meal'),'meal'),
        (('talk','social','family','friend','play','visiting'),'social'),(('seek','search'),'search'),
        (('rest','home','relax'),'rest'),(('work','produc','repair','craft','farm'),'work')]:
        if any(token in low for token in tokens):
            return dict(kind=kind,label=source[:1].upper()+source[1:120])
    if source:return dict(kind='idle',label=source[:1].upper()+source[1:120])
    return dict(kind='idle',label='Here')

def watch(w,player,query=''):
    from engine import fighting_pose
    rows=[]
    for n in w.entities_in_room(player.location):
        if n.is_player or not n.alive:continue
        active=getattr(n,'_fight_display',None)
        if active and active[0]==n.location and active[1]>fighting_pose.monotonic():label='Fighting'
        else:label=activity(w,n)['label']
        rows.append({'id':n.id,'name':n.name,'label':label})
    if query.strip():rows=[item_catalog.choose(rows,query,missing='No living NPC with that name is here.')]
    return '\n'.join(r['name']+' — '+r['label'] for r in rows) or 'There are no living NPCs here to watch.'
