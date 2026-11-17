"""Player-list replies through the actual GameServer.handle command path.

The small world and in-process socket keep these checks independent of a live
server. Only world loading and storage paths are injected; dispatch, quest
rules, response construction and session staging use production code.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import interface_tours, loader, persistence
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot as snapshot_entity
from server import game_server


def fixture(directory, *, location='inn', guide_finished=True):
    world = World()
    world.metadata = {'living_world': True, 'society': False,
                      'start_room': 'inn', 'progression': {'threshold_step': 10000}}
    world.rules = {}
    world.start_room = 'inn'
    world.game_dir = directory / 'games' / 'fixture'
    world.game_dir.mkdir(parents=True)
    world.room_details = {'inn': {'id': 'inn', 'items': ['notice']},
                          'square': {'id': 'square'}}
    world.add_room(Room('inn', 'Travellers Inn', 'A public meeting place.',
                        exits={'out': 'square'}, items=['notice']))
    world.add_room(Room('square', 'Civic Square', 'A public square.',
                        exits={'in': 'inn'}))
    world.items = {
        'reward': {'id': 'reward', 'name': 'Reward token', 'type': 'misc'},
        'notice': {'id': 'notice', 'name': 'Public notice',
                   'description': 'An actual public request.',
                   'readable': True, 'text': 'Help with a local request.',
                   'knowledge': {'quests': ['offer']}},
    }
    world.quests = {
        'guide': {'id': 'guide', 'name': 'Interface lesson',
                  'description': 'Finish the lesson and return to the inn.',
                  'offer_room': 'inn', 'turn_in_room': 'inn',
                  'reward_gold': 7, 'reward_items': ['reward'], 'reward_xp': 25,
                  'interface_tour': {'version': 1, 'title': 'Interface lesson',
                                     'steps': [{'id': 'map', 'target': 'map',
                                                'title': 'Map', 'text': 'Read the map.'}]}},
        'offer': {'id': 'offer', 'name': 'Public request',
                  'description': 'A request disclosed by the public notice.',
                  'offer_room': 'inn', 'turn_in_room': 'inn'},
    }
    player = Entity('traveller', 'Traveller', 30, 30, 2, 1, is_player=True,
                    progress={'world_slug': 'fixture', 'quests': {'guide': 'active'}})
    world.add_entity(player, location)
    interface_tours.begin(world, player, world.quests['guide'])
    if guide_finished:
        # Covers the migrated-save case: ordered acknowledgements are complete
        # even though the old satisfied marker was never set.
        player.progress[interface_tours.KEY]['guide']['acknowledged'] = ['map']
    return world, player


class Socket:
    """Record each request's replies and state before disconnect cleanup."""
    def __init__(self, server, player, packets):
        self.server = server
        self.player = player
        self.commands = packets
        self.packets = []
        self.observations = []
        self.closed = False

    def state(self):
        return deepcopy({'player': snapshot_entity(self.player),
                         'living': self.server.world.living_state})

    async def send(self, raw):
        self.packets.append(json.loads(raw))

    async def close(self, **kwargs):
        self.closed = True

    async def __aiter__(self):
        for packet in self.commands:
            before = self.state()
            start = len(self.packets)
            yield json.dumps(packet)
            self.observations.append({'request': packet, 'before': before,
                                      'after': self.state(),
                                      'replies': self.packets[start:]})


class PlayerListTransport(unittest.IsolatedAsyncioTestCase):
    async def session(self, packets, *, location='inn', guide_finished=True,
                      resume=True):
        with tempfile.TemporaryDirectory(prefix='expanse-list-transport-') as temporary:
            directory = Path(temporary)
            world, player = fixture(directory, location=location,
                                    guide_finished=guide_finished)
            with ExitStack() as stack:
                stack.enter_context(patch.object(game_server, 'build_world', return_value=world))
                stack.enter_context(patch.object(game_server, 'SAVE_DIR', directory / 'save'))
                stack.enter_context(patch.object(game_server, 'WORLD_STATE_PATH', directory / 'world-state.json'))
                stack.enter_context(patch.object(loader, 'GAMES_DIR', directory / 'games'))
                stack.enter_context(patch.object(persistence, 'DB_PATH', directory / 'world.db'))
                server = game_server.GameServer(mode='single')
                sequence = ([{'command': 'resume traveller'}] if resume else []) + packets
                socket = Socket(server, player, sequence)
                try:
                    await server.handle(socket)
                    self.assertFalse((directory / 'world.db').exists(),
                                     'Ordinary list actions must not publish a manual save.')
                    self.assertFalse((directory / 'world-state.json').exists())
                    return socket
                finally:
                    server.db.close()
                    server.checkpoint_db.close()

    def response(self, observation, kind='response'):
        replies = [packet for packet in observation['replies'] if packet['type'] == kind]
        self.assertEqual(1, len(replies), observation)
        return replies[0]

    def assert_correlated(self, packet, request_id):
        self.assertIs(packet.get('player_list_action'), True)
        self.assertEqual(request_id, packet.get('request_id'))

    def payout(self, state):
        player = state['player']
        return player['gold'], player['inventory'], player['progress'].get('advancement_v1')

    async def test_complete_rejection_success_and_replay_are_correlated_without_duplicate_payout(self):
        socket = await self.session([
            {'command': 'complete guide', 'request_id': 'wrong-room', 'player_list_action': True},
            {'command': 'go in'},
            {'command': 'complete guide', 'request_id': 'complete-once', 'player_list_action': True},
            {'command': 'complete guide', 'request_id': 'complete-once', 'player_list_action': True},
        ], location='square')
        rejected, move, completed, replay = socket.observations[1:]
        reply = self.response(rejected)
        self.assert_correlated(reply, 'wrong-room')
        self.assertEqual('Turn this in at Travellers Inn.', reply['text'])
        self.assertEqual(self.payout(rejected['before']), self.payout(rejected['after']))
        self.assertEqual('active', rejected['after']['player']['progress']['quests']['guide'])
        reply = self.response(completed)
        self.assert_correlated(reply, 'complete-once')
        self.assertTrue(reply['text'].startswith('Quest complete.'), reply)
        self.assertEqual('complete', completed['after']['player']['progress']['quests']['guide'])
        self.assertEqual(7, completed['after']['player']['gold'])
        self.assertEqual(['reward'], completed['after']['player']['inventory'])
        reply = self.response(replay)
        self.assert_correlated(reply, 'complete-once')
        self.assertFalse(reply['text'].startswith('Quest complete.'))
        self.assertEqual(self.payout(completed['after']), self.payout(replay['after']))

    async def test_tag_is_correlation_only_and_cannot_finish_an_incomplete_guide(self):
        socket = await self.session([
            {'command': 'complete guide', 'request_id': 'unfinished', 'player_list_action': True,
             'completed': True, 'satisfied': True, 'reward_gold': 9999},
        ], guide_finished=False)
        observation = socket.observations[1]
        reply = self.response(observation)
        self.assert_correlated(reply, 'unfinished')
        self.assertIn('Finish the interface guide first.', reply['text'])
        self.assertEqual(self.payout(observation['before']), self.payout(observation['after']))
        self.assertEqual('active', observation['after']['player']['progress']['quests']['guide'])
        self.assertEqual([], observation['after']['player']['progress'][interface_tours.KEY]['guide']['acknowledged'])

    async def test_malformed_flags_and_request_ids_are_rejected_before_any_game_mutation(self):
        packets = [dict(command='complete guide', player_list_action=value, request_id='invalid-flag')
                   for value in (False, 1, 'true', None, {}, [])]
        packets += [dict(command='complete guide', player_list_action=True, request_id=value)
                    for value in (None, 1, True, '', 'x' * 101, {}, [])]
        packets.append(dict(command='complete guide', player_list_action=True))
        socket = await self.session(packets)
        for observation in socket.observations[1:]:
            with self.subTest(request=observation['request']):
                self.assertEqual(observation['before'], observation['after'])
                reply = self.response(observation, 'error')
                self.assertEqual('Invalid player-list action request.', reply['text'])
                request_id = observation['request'].get('request_id')
                if isinstance(request_id, str) and 1 <= len(request_id) <= 100:
                    self.assert_correlated(reply, request_id)
                else:
                    self.assertNotIn('request_id', reply)
                    self.assertNotIn('player_list_action', reply)

    async def test_untagged_ordinary_responses_keep_their_existing_shape(self):
        socket = await self.session([
            {'command': 'look', 'request_id': 'ordinary-look'},
            {'command': 'complete guide', 'request_id': 'ordinary-complete'},
        ])
        for observation in socket.observations[1:]:
            reply = self.response(observation)
            self.assertEqual({'type', 'text', 'source_quests'}, set(reply))
        self.assertTrue(self.response(socket.observations[2])['text'].startswith('Quest complete.'))

    async def test_source_offer_acceptance_keeps_its_separate_authoritative_packet(self):
        socket = await self.session([
            {'command': 'accept offer', 'request_id': 'undisclosed'},
            {'command': 'read notice'},
            {'command': 'accept offer', 'request_id': 'source-offer'},
            {'command': 'accept offer', 'request_id': 'also-list', 'player_list_action': True},
        ])
        rejected, reading, accepted, repeated = socket.observations[1:]
        reply = self.response(rejected)
        self.assertEqual({'quest_id': 'offer', 'accepted': False, 'status': 'available'}, reply['quest_accept'])
        self.assertEqual('undisclosed', reply['request_id'])
        self.assertNotIn('player_list_action', reply)
        choices = self.response(reading)['source_quests']
        self.assertEqual(['offer'], [choice['id'] for choice in choices])
        reply = self.response(accepted)
        self.assertEqual('source-offer', reply['request_id'])
        self.assertEqual({'quest_id': 'offer', 'accepted': True, 'status': 'active'}, reply['quest_accept'])
        self.assertNotIn('player_list_action', reply)
        reply = self.response(repeated)
        self.assert_correlated(reply, 'also-list')
        self.assertEqual({'quest_id': 'offer', 'accepted': True, 'status': 'active'}, reply['quest_accept'])
        self.assertEqual(self.payout(accepted['after']), self.payout(repeated['after']))

    async def test_tagged_action_before_resume_returns_a_correlated_character_requirement(self):
        socket = await self.session([
            {'command': 'complete guide', 'request_id': 'no-character', 'player_list_action': True},
        ], resume=False)
        observation = socket.observations[0]
        reply = self.response(observation, 'character_required')
        self.assert_correlated(reply, 'no-character')
        self.assertEqual(observation['before'], observation['after'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
