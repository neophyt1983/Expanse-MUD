"""Ephemeral trade pauses: bounded, shared by local traders, never saved."""
import time
import secrets

IDLE_SECONDS=30
MAX_SECONDS=180
COOLDOWN_SECONDS=10


def valid(world,record):
    from engine import livelihoods, society, trade_view
    now=time.monotonic();p=world.entities.get(record['player']);n=world.entities.get(record['npc'])
    basic=bool(now<record['expires'] and now<record['deadline'] and p and n and p.alive and n.alive
                and p.location==n.location==record['room'] and p.hp==record['player_hp'] and n.hp==record['npc_hp']
                and livelihoods.service_open(world,n) and (not society.enabled(world) or society.friendliness(world,p,n)>=50))
    if not basic:return False
    # Cheap conservative check: no demand/catalog scan on simulation ticks.
    # Exact interest is checked on deliberate input and quote/map refresh.
    possible_interest=any(iid in world.items and iid not in p.equipped.values() for iid in p.inventory)
    return trade_view.available(world,p,n,commerce={'buying':possible_interest})


def release(world,record):
    groups=getattr(world,'trade_attention',{});rows=groups.get(record['npc'],{})
    rows.pop(record['token'],None)
    if not rows:groups.pop(record['npc'],None)


def start(world,player,npc):
    now=time.monotonic();budgets=getattr(world,'trade_attention_budgets',None)
    if budgets is None:budgets={};world.trade_attention_budgets=budgets
    deadline=budgets.get(npc.id,now+MAX_SECONDS)
    if now>=deadline:
        if now<deadline+COOLDOWN_SECONDS:raise ValueError('This trader needs a brief break. Reopen Trade in ten seconds.')
        deadline=now+MAX_SECONDS
    budgets[npc.id]=deadline
    record=dict(token=secrets.token_urlsafe(18),npc=npc.id,player=player.id,room=player.location,
                expires=min(deadline,now+IDLE_SECONDS),deadline=deadline,player_hp=player.hp,npc_hp=npc.hp)
    groups=getattr(world,'trade_attention',None)
    if groups is None:groups={};world.trade_attention=groups
    groups.setdefault(npc.id,{})[record['token']]=record
    return record


def renew(world,record):
    if not valid(world,record):
        release(world,record);raise ValueError('Trade ended: time limit, duty hours, movement or danger changed. Reopen Trade when it is safe and available.')
    from engine import trade_view
    p=world.entities[record['player']];n=world.entities[record['npc']]
    if not trade_view.available(world,p,n):
        release(world,record);raise ValueError('Trade ended: this NPC has no goods for sale and no interest in your carried items.')
    record['expires']=min(record['deadline'],time.monotonic()+IDLE_SECONDS)


def paused(world,npc):
    held=False
    for record in list(getattr(world,'trade_attention',{}).get(npc.id,{}).values()):
        if valid(world,record):held=True
        else:release(world,record)
    return held
