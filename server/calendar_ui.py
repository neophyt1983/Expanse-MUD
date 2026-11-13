"""Authorized, session-transaction calendar service. No external or offline delivery."""
import json
import time
from collections import deque
from engine import player_calendar as calendar


def disconnect(server, socket):
    getattr(server, '_calendar_subscribers', set()).discard(socket)


def _actor(server, socket, player_id):
    if server.clients.get(socket) != player_id: raise ValueError('Load your own character before opening Calendar.')
    player = server.world.entities.get(player_id)
    if player is None or not player.is_player: raise ValueError('Load your own character before opening Calendar.')
    return player


def _limit(server, actor, mutating, now):
    limits=getattr(server,'_calendar_limits',None)
    if limits is None:server._calendar_limits={};limits=server._calendar_limits
    key=(actor,mutating);bucket=limits.setdefault(key,deque())
    while bucket and bucket[0] <= now-60:bucket.popleft()
    if len(bucket) >= (12 if mutating else 90):raise ValueError('Too many calendar requests. Please wait a minute.')
    bucket.append(now)
    # Bound dormant per-session bookkeeping without deleting saved events.
    if len(limits)>512:
        for old in list(limits):
            if not limits[old] or limits[old][-1] <= now-60:limits.pop(old,None)


async def _send_snapshot(server,socket,player_id,now,request_id=None,message='',validated=None):
    packet=dict(type='player_calendar',request_id=request_id,**calendar.view(server.world,player_id,now,_validated=validated))
    if message:packet['message']=message
    await socket.send(json.dumps(packet))


async def handle(server,socket,player_id,packet,command,now=None):
    if command.lower() != 'calendar':return False
    # Wall-clock UTC is authoritative. Game ticks, seasons and accelerated time
    # deliberately never participate in appointment validation or due checks.
    now=time.time() if now is None else now
    request_id=packet.get('request_id')
    if type(request_id) is not int or not 0<=request_id<=2147483647:request_id=None
    try:
        player=_actor(server,socket,player_id)
        if 'calendar' not in packet:
            await socket.send(json.dumps({'type':'response','text':'Choose Calendar beside the session controls to schedule private real-world events with other players.'}))
            return True
        payload=packet.get('calendar')
        if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))>8192:raise ValueError('Calendar request is too large or invalid.')
        action=payload.get('action')
        if not isinstance(action,str):raise ValueError('Choose a calendar action.')
        if action=='close':
            disconnect(server,socket);return True
        if not hasattr(server,'_calendar_subscribers'):server._calendar_subscribers=set()
        _limit(server,player.id,action not in ('list',),now)
        if action=='list':
            if set(payload)!={'action'}:raise ValueError('Unsupported calendar field.')
            server._calendar_subscribers.add(socket)
            await _send_snapshot(server,socket,player.id,now,request_id)
            return True
        before=calendar.read(server.world)
        candidate=calendar.update(server.world,player,payload,now)
        if not hasattr(server.world,'living_state'):server.world.living_state={}
        existed=calendar.KEY in server.world.living_state
        previous=server.world.living_state.get(calendar.KEY)
        server.world.living_state[calendar.KEY]=candidate
        try:
            # Appointment changes are staged in the session, not a durable save. This
            # does not change batching of unrelated ordinary game commands.
            server._stage_players_and_world()
        except Exception:
            if existed:server.world.living_state[calendar.KEY]=previous
            else:server.world.living_state.pop(calendar.KEY,None)
            raise ValueError('The calendar change could not be applied. No appointment change was accepted; try again after the host resolves the problem.') from None
        server._calendar_subscribers.add(socket)
        changed=[e for ident,e in candidate['events'].items() if before['events'].get(ident)!=e]
        recipients=set()
        for event in changed:
            recipients.update(event['participants'])
            recipients.update(before['events'].get(event['id'],{}).get('participants',{}))
        validated=calendar.read(server.world)
        await _send_snapshot(server,socket,player.id,now,request_id,'Calendar change applied. Use Save to keep it.',validated)
        for peer in list(server._calendar_subscribers):
            if peer is socket:continue
            ident=server.clients.get(peer)
            if ident is None:disconnect(server,peer);continue
            if action!='register' and ident not in recipients:continue
            # Candidate updates replace the calendar object. Reuse validation
            # within this dispatch, but refresh after any intervening write or
            # reload while a socket send yielded. Authorization always uses the
            # current version, never a stale pre-removal participant list.
            if getattr(server.world,'living_state',{}).get(calendar.KEY) is not validated:
                validated=calendar.read(server.world)
            try:await _send_snapshot(server,peer,ident,now,validated=validated)
            except Exception:disconnect(server,peer)
        # Connected recipients get a generic change notice, never an offline
        # promise. Full event details are only in their authorized calendar.
        for peer,ident in list(server.clients.items()):
            if ident in recipients and peer is not socket:
                try:await peer.send(json.dumps({'type':'calendar_notice','text':'An event on your player calendar changed. Open Calendar to review it.'}))
                except Exception:pass
    except ValueError as exc:
        await socket.send(json.dumps(dict(type='calendar_error',request_id=request_id,text=str(exc))))
    return True
