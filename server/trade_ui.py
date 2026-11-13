"""Read-only, connection-owned trade previews; purchases use engine commands."""
import json
from copy import deepcopy
from engine import trade_view, trade_attention


def disconnect(server,websocket,expected=None):
    if expected is not None and getattr(server,'_trade_sessions',{}).get(websocket) is not expected:return
    record=getattr(server,'_trade_sessions',{}).pop(websocket,None)
    if record:trade_attention.release(server.world,record)


async def handle(server, websocket, player_id, command):
    words = command.split()
    if not words or words[0].lower() not in ('tradeopen','tradeview','tradeclose','tradeactive','tradecancel'): return False
    operation=words[0].lower()
    if operation=='tradecancel':
        record=getattr(server,'_trade_sessions',{}).get(websocket)
        if record and len(words)==2 and words[1]==str(record.get('request_id')):disconnect(server,websocket)
        return True
    if operation=='tradeclose':
        record=getattr(server,'_trade_sessions',{}).get(websocket)
        if record and len(words)==2 and words[1]==record['token']:disconnect(server,websocket)
        return True
    if operation=='tradeactive':
        record=getattr(server,'_trade_sessions',{}).get(websocket)
        if record and len(words)==2 and words[1]==record['token'] and record['player']==player_id:
            try:trade_attention.renew(server.world,record)
            except ValueError:disconnect(server,websocket)
        return True
    if operation=='tradeopen':disconnect(server,websocket)
    record=None;owns_request=False
    player = server.world.entities.get(player_id)
    request = words[1] if len(words) > 1 else ''
    request_id = int(words[2]) if len(words) in (3,4) and words[2].isascii() and words[2].isdigit() and len(words[2]) <= 12 else None
    if player is None or not player.is_player:
        packet = dict(type='trade_view', trader=request, error='Load your character first.')
    else:
        before = deepcopy(player.progress.get('knowledge'))
        try:
            record=getattr(server,'_trade_sessions',{}).get(websocket)
            if operation=='tradeview' and len(words)==4:
                owns_request=bool(record and record['token']==words[3] and record['npc']==request and record['player']==player_id)
                if not record or record['token']!=words[3] or record['npc']!=request or record['player']!=player_id:
                    raise ValueError('This trade session ended. Open Trade again.')
                if not trade_attention.valid(server.world,record):raise ValueError('Trade ended: inactivity, duty hours, movement or danger changed. Open Trade again when available.')
            packet = trade_view.view(server.world, player, request)
            has_goods=any(row.get('quantity') is None or row.get('quantity',0)>0 for row in packet['buy'])
            wants_items=any(row.get('price') is not None and row['id'] not in player.equipped.values() and row.get('reason','') in ('','The trader cannot afford this item right now.') for row in packet['sell'])
            if not has_goods and not wants_items:
                raise ValueError(packet['note'] if 'legacy stock' in packet['note'] else 'This NPC has no goods for sale and is not interested in your carried items right now.')
            if operation=='tradeopen':
                if request_id is None:raise ValueError('Trade opening requires a valid request generation.')
                record=trade_attention.start(server.world,player,server.world.entities[request])
                if not hasattr(server,'_trade_sessions'):server._trade_sessions={}
                record['request_id']=request_id
                server._trade_sessions[websocket]=record
                owns_request=True
            if record and record['npc']==request:
                packet['trade_session']=record['token']
                packet['note']+=' The NPC waits here while this Trade window is active (30 seconds without input, three minutes maximum); closing, lost connection, duty changes or danger ends the pause.'
        except ValueError as exc:
            if owns_request:disconnect(server,websocket,expected=record)
            packet = dict(type='trade_view', trader=request, error=str(exc))
        except Exception:
            if owns_request:disconnect(server,websocket,expected=record)
            raise
        if player.progress.get('knowledge') != before:
            if not hasattr(server.world, 'dirty_players'): server.world.dirty_players = set()
            server.world.dirty_players.add(player.id)
    packet['request_id'] = request_id
    try:await websocket.send(json.dumps(packet))
    except Exception:
        if owns_request:disconnect(server,websocket,expected=record)
        raise
    return True
