"""Short real-time pauses for NPC movement during local interactions."""
import time

def begin(w,*participants):
    now=time.monotonic()
    timers=getattr(w,'npc_attention_until',None)
    if timers is None:timers={};w.npc_attention_until=timers
    for e in participants:
        if e and not e.is_player and e.alive:
            seconds=w.npcs.get(e.source_def,{}).get('interaction_pause_seconds',15)
            timers[e.id]=now+seconds

def paused(w,e):
    if e.progress.get('escort_post'):return True
    if e.progress.get('escort_owner'):
        from engine import escorts
        owner=w.entities.get(e.progress['escort_owner'])
        if owner and owner.alive and escorts.pair(w,owner)[0] is e:return True
    from engine import trade_attention
    if trade_attention.paused(w,e):return True
    timers=getattr(w,'npc_attention_until',{})
    until=timers.get(e.id)
    if until is None:return False
    if 'awakened_until' in e.progress:
        from engine import livelihoods
        # A real-time conversation pause must not outlive a game-time wake period.
        if not livelihoods.awake(w,e):timers.pop(e.id,None);return False
    if time.monotonic()<until:return True
    timers.pop(e.id,None);return False
