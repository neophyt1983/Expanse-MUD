"""Per-connection delivery of authoritative transient magic presentations.

Only players present for the actual event can receive it. Bind/resume starts at
the current cursor, so loading a character never replays an earlier spell.
No queue, cursor or screen position is written to a gameplay checkpoint.
"""
import asyncio
import json
import time


def _states(server):
    if not hasattr(server, '_magic_connections'):
        server._magic_connections = {}
    return server._magic_connections


def bind(server, socket, player_id):
    from engine import magic_visuals
    _states(server)[socket] = {'player_id': player_id,
        'cursor': magic_visuals.cursor(server.world), 'room': None,
        'actors': set(), 'previous': {}, 'lock': asyncio.Lock()}


def forget(server, socket):
    getattr(server, '_magic_connections', {}).pop(socket, None)


def reset(server):
    server._magic_connections = {}
    for socket, player_id in getattr(server, 'clients', {}).items():
        bind(server, socket, player_id)


def note_map(server, socket, player_id, packet):
    state = _states(server).get(socket)
    if state is None or state['player_id'] != player_id:
        bind(server, socket, player_id)
        state = _states(server)[socket]
    room = packet.get('location', {}).get('id')
    visual = packet.get('visual', {})
    # Same-room actors use detailed sprites. Nearby silhouettes do not grant
    # permission to receive hidden-room spell events.
    actors = {row['id'] for row in visual.get('actors', [])
              if isinstance(row, dict) and isinstance(row.get('id'), str)
              and row.get('room') == room}
    now = time.monotonic()
    if state['room'] != room:
        state['previous'] = {}
    else:
        prior = {ident: expiry for ident, expiry in state['previous'].items()
                 if expiry > now and ident not in actors}
        for ident in state['actors'] - actors:
            prior[ident] = now + 5.0
        # A disappeared, previously visible target authorizes only a bounded
        # impact/departure accent; the client never draws a replacement actor.
        state['previous'] = dict(list(prior.items())[-512:])
    state.update(room=room, actors=actors)
    return state


async def flush(server, *, refresh=False):
    for socket, player_id in list(getattr(server, 'clients', {}).items()):
        await _flush_socket(server, socket, player_id, refresh)


async def _flush_socket(server, socket, player_id, refresh):
    from engine import magic_visuals
    state = _states(server).get(socket)
    if state is None or state['player_id'] != player_id:
        bind(server, socket, player_id)
        return
    # The command handler and lifecycle can both flush. Keep a connection's
    # map/effect batch ordered, including while its transport applies pressure.
    # Re-read the cursor after acquiring the lock; an earlier batch may have
    # advanced it while this one waited.
    async with state['lock']:
        if server.clients.get(socket) != player_id or _states(server).get(socket) is not state:
            return
        world = server.world
        high = magic_visuals.cursor(world)
        if state['cursor'] == high:
            return
        actor = world.entities.get(player_id)
        if actor is None or not magic_visuals.has_pending(world, actor, state['cursor']):
            state['cursor'] = high
            return
        packet = None
        if refresh:
            packet = dict(type='map', **server.map_for(player_id))
            note_map(server, socket, player_id, packet)
        now = time.monotonic()
        previous = [ident for ident, expiry in state['previous'].items() if expiry > now]
        projected = magic_visuals.projection(world, actor, state['cursor'], state['actors'], previous)
        # Advance before awaiting the transport so a concurrent lifecycle flush
        # cannot send the same event again. No gameplay state is changed here.
        state['cursor'] = {key: projected[key] for key in ('session', 'sequence')}
        try:
            if packet is not None:
                encoded = json.dumps(packet)
                await socket.send(encoded)
                if server.clients.get(socket) != player_id or server.world is not world:
                    return
                server.last_maps[socket] = encoded
            for event in projected.get('events', []):
                if (server.clients.get(socket) != player_id or server.world is not world
                        or _states(server).get(socket) is not state
                        or world.entities.get(player_id) is not actor
                        or actor.location != event.get('room_id')):
                    break
                await socket.send(json.dumps({**event, 'viewer_id': player_id}))
        except (ConnectionError, RuntimeError):
            # Closed aiohttp transports use RuntimeError; no event survives to
            # a replacement connection. websockets closes are handled below.
            pass
        except Exception as exc:
            import websockets.exceptions
            if not isinstance(exc, websockets.exceptions.ConnectionClosed):
                raise
