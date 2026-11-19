"""Real custody, passage packets and release-clock regression coverage."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine import city_justice, frontiers, living, mortality
from engine.commands import CommandContext, _cmd_go, build_registry, process_command
from engine.core import Entity, Room, World
from engine.mapping import compile_map, room_records
from server.game_server import GameServer


def custody_world(directory, *, realtime=False):
    world = World()
    world.metadata = {'living_world': True}
    court = {'court': 'court', 'holding': 'jail', 'jail': 'jail', 'release': 'square', 'judge': 'magistrate'}
    world.rules = {
        'regional_gameplay': {'enabled': True, 'courts': True,
                             'hearing_delay_minutes': 2, 'judge_wait_minutes': 2,
                             'sentences': {'default': {'minutes': 10, 'fine': 0}}},
        'city_courts': {'Dawnwatch': court},
    }
    world.room_details = {}
    world.living_state = {'minute': 480}
    world.realtime = realtime
    world.game_dir = directory
    definitions = [
        ('jail', 'Dawnwatch Police Station Jail', (0, 0, 0), 'inside',
         {'station': 'station', 'court': 'court', 'washroom': 'washroom'}),
        ('station', 'Dawnwatch Police Station', (3, 0, 0), 'inside',
         {'jail': 'jail', 'out': 'square'}),
        ('court', 'Dawnwatch Magistrates Court', (-3, 0, 0), 'inside', {'jail': 'jail'}),
        ('washroom', 'Jail washroom', (0, 2, 0), 'inside', {'jail': 'jail', 'station': 'station'}),
        ('square', 'Dawnwatch Civic Square', (5, 0, 0), 'road', {'station': 'station'}),
    ]
    for rid, name, (x, y, z), environment, exits in definitions:
        world.add_room(Room(rid, name, 'Test location.', exits, map_x=x, map_y=y, map_z=z))
        world.room_details[rid] = {'environment': environment}
    world.buildings = {
        'jail': {'id': 'jail', 'name': 'Station Jail', 'rooms': ['jail', 'washroom']},
        'station': {'id': 'station', 'name': 'Police Station', 'rooms': ['station']},
        'court': {'id': 'court', 'name': 'Magistrates Court', 'rooms': ['court']},
    }
    city_justice.install(world)
    player = Entity('traveller', 'Traveller', 100, 100, 10, 10, gold=50,
                    is_player=True, location='jail')
    world.entities[player.id] = player
    world.rooms['jail'].entities.append(player.id)
    world._compiled_map = compile_map(room_records(world))
    server = GameServer.__new__(GameServer)
    server.world = world
    server.clients = {object(): player.id}
    server.map_markers = {}
    return world, player, server


def sentence(world, player):
    case = dict(world.city_courts['Dawnwatch'], actor=player.id, status='sentenced',
                verdict='guilty', custody_room='jail', custody_rooms=['jail', 'washroom'],
                release_at=490, fine_paid=0)
    city_justice.state(world)['cases'][player.id] = case
    player.progress['court_case'] = {'status': 'sentenced', 'release_at': 490,
                                    'custody_rooms': ['jail', 'washroom']}
    return case


def passages(server, player):
    return {row['direction']: row for row in server.map_for(player.id)['visual']['passages']}


def move(world, player, direction):
    return _cmd_go(CommandContext(world, player, world.rooms[player.location]), direction)


def notice_context(world):
    world.metadata['press_editions'] = [{'name': 'Dawnwatch', 'kind': 'city', 'home': 'square'}]
    world.metadata['society'] = True
    world.room_details['jail']['laws'] = {'enabled': True, 'authority': 'civic'}
    world.npcs['watch'] = {'profession': 'guard', 'social_profile': {'sentient': True}}
    guard = Entity('officer', 'Vale Hearthwell', 100, 100, 10, 10, source_def='watch',
                   group_id='civic', location='jail')
    world.entities[guard.id] = guard
    world.rooms['jail'].entities.append(guard.id)
    return guard


class CustodyPassageTests(unittest.TestCase):
    def test_visiting_the_jail_does_not_confine_a_player_without_a_case(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            inmate = Entity('inmate', 'Inmate', 100, 100, 10, 10, is_player=True, location='jail')
            world.entities[inmate.id] = inmate
            world.rooms['jail'].entities.append(inmate.id)
            sentence(world, inmate)
            choices = passages(server, player)
            self.assertEqual(choices['station']['blocked'], '')
            self.assertEqual(choices['court']['blocked'], '')
            move(world, player, 'station')
            self.assertEqual(player.location, 'station')
            self.assertEqual(passages(server, player)['out']['kind'], 'exit')
            self.assertEqual(passages(server, player)['out']['blocked'], '')
            move(world, player, 'out')
            self.assertEqual(player.location, 'square')
            self.assertNotIn('court_case', player.progress)
            self.assertIn(inmate.id, city_justice.state(world)['cases'])

    def test_sentence_blocks_departure_but_preserves_allowed_custody_facilities(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            sentence(world, player)
            choices = passages(server, player)
            for direction in ('station', 'court'):
                reason = choices[direction]['blocked']
                self.assertIn('10 game minutes remaining', reason)
                self.assertIn('facilities inside your place of custody', reason)
                self.assertEqual(frontiers.blocked(world, 'jail', direction, player), reason)
                self.assertEqual(move(world, player, direction), reason)
                self.assertEqual(player.location, 'jail')
            self.assertEqual(choices['washroom']['blocked'], '')
            move(world, player, 'washroom')
            self.assertEqual(player.location, 'washroom')
            self.assertIn('10 game minutes remaining', passages(server, player)['station']['blocked'])
            move(world, player, 'station')
            self.assertEqual(player.location, 'washroom')
            move(world, player, 'jail')
            self.assertEqual(player.location, 'jail')

    def test_countdown_and_release_follow_authorized_world_time_in_solo_and_host_modes(self):
        for realtime in (False, True):
            with self.subTest(realtime=realtime), TemporaryDirectory() as directory:
                world, player, server = custody_world(directory, realtime=realtime)
                sentence(world, player)
                definitions = deepcopy((world.metadata, world.rules, world.room_details))
                exits = {rid: dict(room.exits) for rid, room in world.rooms.items()}
                if realtime:
                    response = process_command(build_registry(), world, player, 'wait 10')
                    self.assertIn('shared world clock cannot be skipped', response)
                    self.assertEqual(living.state(world)['minute'], 480)
                    living.advance(world, 10)  # An ordinary command has no clock authority.
                    self.assertEqual(living.state(world)['minute'], 480)
                for elapsed in range(10):
                    self.assertEqual(living.state(world)['minute'], 480 + elapsed)
                    self.assertEqual(player.location, 'jail')
                    # Rendering again must neither reset the deadline nor advance it.
                    for _ in range(2):
                        choices = passages(server, player)
                        self.assertIn(str(10 - elapsed) + ' game minutes remaining', choices['station']['blocked'])
                        self.assertEqual(city_justice.state(world)['cases'][player.id]['release_at'], 490)
                        custody = server.map_for(player.id)['custody']
                        self.assertEqual(custody['status'], 'sentenced')
                        self.assertEqual(custody['remaining_minutes'], 10 - elapsed)
                        self.assertEqual(custody['can_wait'], not realtime)
                        self.assertEqual(custody['wait_command'], None if realtime else 'wait '+str(10-elapsed))
                    # This is the authorization used by GameServer.lifecycle_loop.
                    world.tick_authorized = True
                    try:
                        living.advance(world, 1)
                    finally:
                        world.tick_authorized = False
                self.assertEqual(living.state(world)['minute'], 490)
                self.assertEqual(player.location, 'square')
                self.assertNotIn(player.id, city_justice.state(world)['cases'])
                self.assertNotIn('court_case', player.progress)
                history = city_justice.state(world)['history'][-1]
                self.assertEqual((history['status'], history['release_at'], history['released_at']),
                                 ('released', 490, 490))
                packet = server.map_for(player.id)
                self.assertEqual(packet['visual']['center'], 'square')
                self.assertEqual(packet['custody']['status'], 'released')
                self.assertFalse(packet['custody']['active'])
                self.assertEqual(packet['custody']['id'], custody['id'])
                self.assertIn('sentence is complete', packet['custody']['outcome'])
                self.assertTrue(all(not row['blocked'] for row in packet['visual']['passages']))
                move(world, player, 'station')
                move(world, player, 'jail')
                self.assertEqual(passages(server, player)['station']['blocked'], '')
                self.assertEqual(player.gold, 50)
                self.assertEqual((world.metadata, world.rules, world.room_details), definitions)
                self.assertEqual({rid: room.exits for rid, room in world.rooms.items()}, exits)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_solo_wait_advances_to_the_authored_release_without_replacing_the_sentence(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            sentence(world, player)
            process_command(build_registry(), world, player, 'wait 10')
            self.assertEqual(living.state(world)['minute'], 490)
            self.assertEqual(player.location, 'square')
            self.assertNotIn(player.id, city_justice.state(world)['cases'])
            self.assertTrue(all(not row['blocked'] for row in passages(server, player).values()))
            self.assertEqual(city_justice.state(world)['history'][-1]['release_at'], 490)

    def test_pending_hearing_is_not_a_sentence_and_releases_without_a_timely_judge(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            case = dict(world.city_courts['Dawnwatch'], actor=player.id, status='awaiting_hearing',
                        holding='jail', hearing_at=482, arrested=480,
                        accusation='assault', witnesses=[], evidence=[])
            city_justice.state(world)['cases'][player.id] = case
            player.progress['court_case'] = {'status': 'awaiting_hearing', 'hearing_at': 482}
            for direction in ('station', 'court', 'washroom'):
                reason = passages(server, player)[direction]['blocked']
                self.assertIn('pending a hearing in 2 game minutes', reason)
                self.assertIn('No verdict has been issued', reason)
                self.assertEqual(move(world, player, direction), reason)
                self.assertEqual(player.location, 'jail')
            living.advance(world, 2)
            self.assertEqual(player.location, 'square')
            self.assertNotIn('court_case', player.progress)
            history = city_justice.state(world)['history'][-1]
            self.assertEqual(history['status'], 'dismissed')
            self.assertEqual(history['verdict'], 'not_proven')
            self.assertNotIn('release_at', history)
            self.assertTrue(all(not row['blocked'] for row in passages(server, player).values()))

    def test_custody_snapshot_is_read_only_and_contains_only_the_viewers_case(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            initial = deepcopy(world.living_state)
            self.assertIsNone(city_justice.projection(world, player))
            self.assertEqual(world.living_state, initial)
            case = sentence(world, player)
            case.update(accusation='theft', victim='pantry', witnesses=['named-witness'],
                        evidence=[dict(actor=player.id, victim='pantry', kind='theft', room='station',
                                       minute=479, witnesses=['named-witness'],
                                       source={'kind': 'container', 'name': 'Pantry cabinet', 'action': 'take'})])
            other = Entity('other-player', 'Private Other Player', 100, 100, 10, 10,
                           is_player=True, location='jail')
            foreign = sentence(world, other)
            foreign.update(accusation='PRIVATE OTHER CHARGE', status='released', evidence=[])
            city_justice.state(world)['history'].append(foreign)
            before = deepcopy(world.living_state)
            snapshot = city_justice.projection(world, player)
            self.assertEqual(world.living_state, before)
            self.assertEqual(snapshot['accusation'], 'theft')
            self.assertIn('taking contents from Pantry cabinet at Dawnwatch Police Station', snapshot['reason'])
            self.assertEqual(snapshot['witness_count'], 1)
            self.assertEqual(snapshot['evidence'][0]['source_name'], 'Pantry cabinet')
            self.assertEqual(snapshot['allowed_facilities'], ['Dawnwatch Police Station Jail', 'Jail washroom'])
            self.assertNotIn('PRIVATE OTHER', str(snapshot))
            self.assertEqual(server.map_for(player.id)['custody'], snapshot)
            # History is also scoped to the viewer, even if someone else's
            # newer case is the last entry in the shared court archive.
            case.update(status='released', released_at=490)
            del city_justice.state(world)['cases'][player.id]
            city_justice.state(world)['history'] = [deepcopy(case), foreign]
            resolved = city_justice.projection(world, player)
            self.assertEqual(resolved['id'], snapshot['id'])
            self.assertEqual(resolved['status'], 'released')
            self.assertNotIn('PRIVATE OTHER', str(resolved))

    def test_legacy_case_never_invents_a_container_source(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            case = sentence(world, player)
            case.update(accusation='theft', victim='pantry', witnesses=['witness'],
                        evidence=[dict(actor=player.id, victim='pantry', kind='theft', room='station',
                                       minute=479, witnesses=['witness'])])
            world.room_details['station']['locks'] = [{'id': 'pantry', 'name': 'Unverified container'}]
            snapshot = city_justice.projection(world, player)
            self.assertIn('theft at Dawnwatch Police Station', snapshot['reason'])
            self.assertNotIn('Unverified container', str(snapshot))
            self.assertIsNone(snapshot['evidence'][0]['source_name'])

    def test_npc_arrest_names_the_npc_in_room_notice_instead_of_addressing_the_player(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            guard = notice_context(world)
            suspect = Entity('pupil', 'Dawnwatch Pupil 4', 100, 100, 10, 10,
                             location='jail', progress={'social_profile': {'sentient': True}})
            world.entities[suspect.id] = suspect
            world.rooms['jail'].entities.append(suspect.id)
            report = dict(room='jail', kind='assault', victim=guard.id, reported=480,
                          witnesses=[guard.id], evidence=[dict(actor=suspect.id, victim=guard.id,
                          room='jail', kind='assault', minute=480, witnesses=[guard.id])])
            self.assertTrue(city_justice.apprehend(world, suspect, guard, report))
            room, message = world.runtime_notifications[-1]
            self.assertEqual(room, 'jail')
            self.assertIn('takes Dawnwatch Pupil 4 to', message)
            self.assertNotIn('takes you', message)
            self.assertFalse(getattr(world, 'rest_notifications', []))
            self.assertIsNone(server.map_for(player.id)['custody'])
            self.assertNotIn('court_case', player.progress)

    def test_player_notice_and_snapshot_retain_exact_report_source_without_changing_it(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            guard = notice_context(world)
            source = {'kind': 'container', 'id': 'linen', 'name': 'Issued-linen chest', 'action': 'take'}
            mortality.report_crime(world, player, 'theft', 'linen', [guard], source=source)
            source['name'] = 'Changed later'
            report = mortality.state(world)['wanted'][player.id]
            self.assertEqual(report['evidence'][-1]['source']['name'], 'Issued-linen chest')
            self.assertTrue(city_justice.apprehend(world, player, guard, report))
            recipient, message = world.rest_notifications[-1]
            self.assertEqual(recipient, player.id)
            self.assertIn('takes you to', message)
            self.assertIn('taking contents from Issued-linen chest', message)
            self.assertFalse(getattr(world, 'runtime_notifications', []))
            snapshot = server.map_for(player.id)['custody']
            self.assertEqual(snapshot['status'], 'awaiting_hearing')
            self.assertEqual(snapshot['next_event'], 'hearing')
            self.assertEqual(snapshot['remaining_minutes'], 2)
            self.assertIn('No verdict has been issued', ' '.join(snapshot['instructions']))
            self.assertIn('game minutes, not real minutes', ' '.join(snapshot['instructions']))
            self.assertIn('Issued-linen chest', snapshot['reason'])
            self.assertNotIn('Changed later', str(snapshot))

    def test_repeated_report_during_sentence_does_not_announce_a_new_pending_hearing(self):
        with TemporaryDirectory() as directory:
            world, player, server = custody_world(directory)
            guard = notice_context(world)
            case = sentence(world, player)
            before = deepcopy(case)
            mortality.report_crime(world, player, 'theft', 'linen', [guard],
                                   source={'kind': 'container', 'name': 'Issued-linen chest', 'action': 'take'})
            messages = mortality.advance(world, rng=lambda: 0)
            self.assertFalse(messages)
            self.assertFalse(getattr(world, 'rest_notifications', []))
            self.assertNotIn(player.id, mortality.state(world)['wanted'])
            self.assertEqual(city_justice.state(world)['cases'][player.id], before)
            self.assertEqual(player.location, 'jail')
            self.assertEqual(player.gold, 50)


if __name__ == '__main__':
    unittest.main()
