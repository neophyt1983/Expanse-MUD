"""A busy map refresh allows queued gameplay and honors a changed socket binding."""
import asyncio
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from server.game_server import GameServer


class MapFairnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_reconnect_yields_and_skips_previous_characters_map(self):
        server = GameServer.__new__(GameServer)
        first, changed = Mock(), Mock()
        first.send = AsyncMock()
        changed.send = AsyncMock()
        server.clients = {first: 'one', changed: 'previous'}
        server.last_maps = {}
        server.world = SimpleNamespace(entities={'one': object(), 'previous': object(), 'new': object()})

        def build_map(pid):
            if pid == 'one':
                # Simulate an expensive map with no transport backpressure.
                time.sleep(.03)
                asyncio.get_running_loop().call_soon(server.clients.__setitem__, changed, 'new')
            return {'location': {'id': pid}}

        server.map_for = Mock(side_effect=build_map)
        with patch('server.magic_delivery.note_map'), patch('server.magic_delivery.flush', new_callable=AsyncMock):
            await server.update_maps()
        server.map_for.assert_called_once_with('one')
        changed.send.assert_not_awaited()
