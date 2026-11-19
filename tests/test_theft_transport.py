"""Theft requests through the authenticated GameServer.handle path.

Only world loading, storage locations and the random source are injected.
Resolution, dispatch, transfers, projections and staged player saves are real.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import burglary, loader, persistence, theft
from engine.core import Entity
from engine.entity_snapshot import snapshot
from server import game_server
from test_player_list_transport import fixture, Socket


def request(number=1, **changes):
    row = dict(command='steal action', theft_ui=True, action='steal',
               sequence=number, request_id='theft-'+str(number),
               actor_id='traveller', room='inn', target_id='merchant-1', quantity=3)
    row.update(changes)
    return row


class Recipient:
    def __init__(self):
        self.packets = []

    async def send(self, raw):
        self.packets.append(json.loads(raw))


class TheftSocket(Socket):
    def state(self):
        rows = super().state()
        rows['people'] = {entity.id: snapshot(entity) for entity in self.server.world.entities.values()}
        rows['saved'] = {}
        for entity in self.server.world.entities.values():
            if entity.is_player:
                saved = persistence.load_player(self.server.db, entity.id, self.server.mode)
                rows['saved'][entity.id] = snapshot(saved) if saved else None
        return deepcopy(rows)


class TheftTransport(unittest.IsolatedAsyncioTestCase):
    async def session(self, packets, *, player_target=False, online=True, success=True, resume=True, host=False):
        with tempfile.TemporaryDirectory(prefix='expanse-theft-transport-') as temporary:
            directory = Path(temporary)
            world, actor = fixture(directory)
            actor.progress['skills'] = {'burglary': 60, 'observation': 20}
            world.items.update(bread={'id':'bread','name':'Bread'},
                               private_amulet={'id':'private_amulet','name':'Secret family amulet'})
            world.npcs['merchant'] = {'id':'merchant','name':'Merchant','social_profile':{'sentient':True}}
            victim = Entity('merchant-1', 'Merchant', 30, 30, 2, 1, is_player=player_target,
                            source_def=None if player_target else 'merchant',
                            inventory=['bread'] * 8 + ['private_amulet'],
                            progress={'world_slug':'fixture'})
            world.add_entity(victim, 'inn')
            draws = []
            real_transfer = theft.transfer
            def controlled(*args, **kwargs):
                values = iter((.1, .8, .99) if success else (.99, .99))
                def roll():
                    value = next(values);draws.append(value);return value
                return real_transfer(*args, **kwargs, rng=roll)
            with ExitStack() as stack:
                stack.enter_context(patch.object(game_server, 'build_world', return_value=world))
                stack.enter_context(patch.object(game_server, 'SAVE_DIR', directory/'save'))
                stack.enter_context(patch.object(game_server, 'WORLD_STATE_PATH', directory/'world.json'))
                stack.enter_context(patch.object(loader, 'GAMES_DIR', directory/'games'))
                stack.enter_context(patch.object(persistence, 'DB_PATH', directory/'world.db'))
                stack.enter_context(patch.object(theft, 'transfer', side_effect=controlled))
                server = game_server.GameServer(mode='host' if host else 'single')
                recipient = Recipient()
                if player_target and online:
                    server.clients[recipient] = victim.id
                sequence = ([{'command':'resume traveller'}] if resume else []) + packets
                socket = TheftSocket(server, actor, sequence)
                if host:
                    server.host_sockets.add(socket)
                try:
                    await server.handle(socket)
                    self.assertFalse((directory/'world.db').exists(), 'Ordinary actions must not publish a single-player manual save.')
                    return socket, draws
                finally:
                    server.db.close();server.checkpoint_db.close()

    def reply(self, observation):
        rows = [row for row in observation['replies'] if row.get('theft_action')]
        self.assertEqual(len(rows), 1, observation['replies'])
        return rows[0]

    def inventories(self, state):
        return state['people']['traveller']['inventory'],state['people']['merchant-1']['inventory']

    async def test_success_is_correlated_and_replay_cannot_repeat_the_transfer(self):
        socket, draws = await self.session([request(), request()],host=True)
        first, replay = socket.observations[1:]
        self.assertEqual('theft-1', self.reply(first)['request_id'])
        self.assertIn('3 × Bread', self.reply(first)['text'])
        self.assertEqual((['bread']*3, ['bread']*5+['private_amulet']), self.inventories(first['after']))
        self.assertEqual(self.inventories(first['after']),self.inventories(replay['after']))
        self.assertIn('already handled',self.reply(replay)['text'])
        self.assertEqual(len(draws),3)
        maps = [row for row in first['replies'] if row['type']=='map']
        self.assertEqual(len(maps),1)
        self.assertEqual(maps[0]['theft']['level'],60)
        self.assertIn('Wait',maps[0]['theft']['blocked'])

    async def test_both_online_player_inventories_are_staged_from_the_same_transfer(self):
        socket,_ = await self.session([request()],player_target=True)
        after = socket.observations[1]['after']
        for ident in ('traveller','merchant-1'):
            self.assertEqual(after['people'][ident]['inventory'],after['saved'][ident]['inventory'])
        self.assertEqual(len(after['saved']['traveller']['inventory']),3)
        self.assertEqual(len(after['saved']['merchant-1']['inventory']),6)

    async def test_failure_discloses_no_pocket_item_and_mutates_neither_inventory(self):
        socket,draws = await self.session([request()],success=False)
        obs=socket.observations[1]
        self.assertEqual(self.inventories(obs['before']),self.inventories(obs['after']))
        self.assertEqual(len(draws),2)
        text=json.dumps(obs['replies']).lower()
        self.assertNotIn('private_amulet',text);self.assertNotIn('secret family amulet',text)
        self.assertNotIn('bread',self.reply(obs)['text'].lower())

    async def test_cooldown_blocks_fresh_request_without_another_roll(self):
        socket,draws=await self.session([request(),request(2)],host=True)
        first,second=socket.observations[1:]
        self.assertIn('Wait',self.reply(second)['text'])
        self.assertEqual(self.inventories(first['after']),self.inventories(second['after']))
        self.assertEqual(len(draws),3)

    async def test_forged_actor_room_contents_and_command_are_rejected_before_rolls(self):
        changes=[{'actor_id':'merchant-1'},{'room':'square'},{'target_id':'missing'},
                 {'item_id':'private_amulet'},{'command':'drop all'},{'quantity':True},
                 {'theft_ui':1},{'sequence':True}]
        packets=[request(i+1,**change) for i,change in enumerate(changes)]
        socket,draws=await self.session(packets)
        self.assertFalse(draws)
        for obs in socket.observations[1:]:
            self.assertEqual('error',self.reply(obs)['type'])
            self.assertEqual(self.inventories(obs['before']),self.inventories(obs['after']))
            self.assertNotIn(burglary.ATTEMPT_KEY,obs['after']['player']['progress'])

    async def test_offline_player_is_not_available_for_graphical_theft(self):
        socket,draws=await self.session([request()],player_target=True,online=False)
        obs=socket.observations[1]
        self.assertIn('no longer available',self.reply(obs)['text']);self.assertFalse(draws)
        self.assertEqual(self.inventories(obs['before']),self.inventories(obs['after']))

    async def test_no_character_returns_a_correlated_requirement_without_transfer(self):
        socket,draws=await self.session([request()],resume=False)
        self.assertIn('player character',self.reply(socket.observations[0])['text'])
        self.assertFalse(draws)


if __name__=='__main__':
    unittest.main()
