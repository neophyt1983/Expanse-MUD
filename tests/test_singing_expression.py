"""Performance directions guide an event; they are not repeated as lyrics."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from engine import npc_emotions, npc_life, relationships, singing
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot


def fixture(*, duet=False):
    world = World()
    world.metadata = {'living_world': True, 'society': True, 'singing': {'version': 1, 'enabled': True}}
    world.living_state = {'minute': 480}
    world.add_room(Room('hall', 'Hall', 'A public music room.', {'east': 'lane'}))
    world.add_room(Room('lane', 'Lane', 'Outside.', {'west': 'hall'}))
    world.races = {'human': {'id': 'human', 'singing': {
        'style': 'Cheery, folky and tongue in cheek, using the full vocal range.',
        'voices': [{'id': 'alto', 'label': 'alto', 'transpose': 0}], 'songs': ['song']}}}
    score = {'version': 1, 'tempo': 100, 'tracks': [{
        'role': 'lead', 'timbre': 'periodic', 'gain': .2, 'harmonics': [1, .25],
        'envelope': {'attack': .1, 'decay': .15, 'sustain': .7, 'release': .2},
        'notes': [[60, 0, 1, .6], [64, 1, 1, .7], [67, 2, 1, 0]]}]}
    if duet:
        score['tracks'].append(dict(deepcopy(score['tracks'][0]), role='response'))
    verse = {'call': 'The lantern waits beside the door.'}
    if duet:
        verse['response'] = 'Then leave a little light for me.'
    song = {'id': 'song', 'name': 'Lantern Song', 'read_text': 'An intentionally authored song.',
            'song': {'style': 'A lyrical line, with a warm final note.',
                     'form': 'call_response' if duet else 'solo', 'verses': [verse], 'score': score}}
    world.items = {'song': song}
    world.npcs = {
        'singer': {'id': 'singer', 'race': 'human', 'social_profile': {'sentient': True},
                   'life_profile': {'mood': 50}, 'singing': {'contexts': ['performance']}},
        'listener': {'id': 'listener', 'race': 'human', 'social_profile': {'sentient': True},
                     'life_profile': {'mood': 50}, 'singing': {'respond': duet}}}
    lead = Entity('lead', 'Mira', 50, 50, 2, 2, source_def='singer', race='human')
    listener = Entity('listener', 'Jon', 50, 50, 2, 2, source_def='listener', race='human')
    player = Entity('player', 'Player', 50, 50, 2, 2, is_player=True, race='human')
    for person in (lead, listener, player):
        world.add_entity(person, 'hall')
    return world, lead, listener, player, song


class SingingExpressionTests(unittest.TestCase):
    def test_directions_are_not_repeated_literally_and_intentional_lyrics_survive(self):
        world, lead, _, _, song = fixture()
        npc_emotions.record(world, lead, 'theft loss observed', event_id='known-loss')
        with patch.object(singing, 'monotonic', return_value=100):
            text = singing._perform(world, lead, song)
        self.assertNotIn(song['song']['style'], text)
        self.assertNotIn(world.races['human']['singing']['style'], text)
        self.assertIn('“The lantern waits beside the door.”', text)
        event = world._singing_events['hall']['event']
        self.assertEqual(event['lyrics'][0]['text'], song['song']['verses'][0]['call'])
        self.assertEqual(len(event['directions']), 2)
        names = {row['id'] for row in event['performers'][0]['expression']['emotions']}
        self.assertTrue({'sad', 'angry', 'anxious'} <= names)
        self.assertNotIn('happy', names, 'Cheerful cultural prose cannot overwrite this individual’s state.')

    def test_event_keeps_complete_emotional_mix_and_refresh_never_rerolls_or_trains(self):
        world, lead, _, player, song = fixture()
        npc_emotions.record(world, lead, 'theft loss observed', event_id='known-loss')
        npc_emotions.record(world, lead, 'gift_wanted', event_id='actual-help')
        with patch.object(singing, 'monotonic', return_value=100):
            singing._perform(world, lead, song)
            first = singing.view(world, player)
            before = deepcopy((lead.progress, world.living_state, world._singing_events))
            for _ in range(4):
                self.assertEqual(singing.view(world, player), first)
            self.assertEqual((lead.progress, world.living_state, world._singing_events), before)
            lead.progress['npc_life']['mood'] = 100
            self.assertEqual(singing.view(world, player), first, 'A playing phrase keeps its captured delivery.')
        names = {row['id'] for row in first['events'][0]['performers'][0]['expression']['emotions']}
        self.assertTrue({'sad', 'angry', 'anxious', 'grateful', 'happy'} <= names)

    def test_new_deliberate_performance_varies_dynamics_without_changing_the_score(self):
        world, lead, _, _, song = fixture()
        original = deepcopy(song)
        with patch.object(singing, 'monotonic', return_value=100):
            self.assertTrue(singing.npc_step(world, lead, 'performance'))
            first = deepcopy(world._singing_events['hall']['event'])
        world.living_state['minute'] += 100
        with patch.object(singing, 'monotonic', return_value=130):
            self.assertTrue(singing.npc_step(world, lead, 'performance'))
            second = world._singing_events['hall']['event']
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotEqual(first['score']['tracks'][0]['notes'], second['score']['tracks'][0]['notes'])
        self.assertEqual(song, original)
        for event in (first, second):
            self.assertEqual(event['score']['tempo'], original['song']['score']['tempo'])
            for track, base in zip(event['score']['tracks'], original['song']['score']['tracks']):
                self.assertEqual([note[:3] for note in track['notes']], [note[:3] for note in base['notes']])
                self.assertEqual(track['envelope']['release'], base['envelope']['release'])
                self.assertEqual(track['notes'][-1][3], 0, 'An authored silent note stays silent.')
                self.assertTrue(all(0 <= note[3] <= 1 for note in track['notes']))
                self.assertTrue(all((note[1] + note[2]) * 60 / event['score']['tempo'] + track['envelope']['release'] <= 20
                                    for note in track['notes']))

    def test_only_actual_local_audience_relationships_influence_delivery(self):
        world, lead, listener, player, song = fixture()
        relationships.bond(world, lead, listener)['trust'] = -80
        relationships.bond(world, lead, player)['trust'] = 80
        with patch.object(singing, 'monotonic', return_value=100):
            singing._perform(world, lead, song)
        expression = world._singing_events['hall']['event']['performers'][0]['expression']
        self.assertTrue({'calm', 'anxious'} <= {row['id'] for row in expression['emotions']})
        listener.location = 'lane'
        player.progress['player_rest'] = {'state': 'active', 'kind': 'sleeping'}
        with patch.object(singing, 'monotonic', return_value=130):
            singing._perform(world, lead, song)
        later = world._singing_events['hall']['event']['performers'][0]['expression']
        self.assertNotIn('anxious', {row['id'] for row in later['emotions']})
        self.assertNotIn('calm', {row['id'] for row in later['emotions']})

    def test_participation_is_real_and_missing_response_is_not_a_rejection_memory(self):
        world, lead, _, _, song = fixture()
        with patch.object(singing, 'monotonic', return_value=100):
            singing._perform(world, lead, song)
        self.assertNotIn('performance', lead.progress[npc_emotions.KEY]['associations'])
        world, lead, listener, _, song = fixture(duet=True)
        with patch.object(singing, 'monotonic', return_value=100):
            text = singing._perform(world, lead, song)
        self.assertIn('Then leave a little light for me.', text)
        event = world._singing_events['hall']['event']
        self.assertEqual({row['id'] for row in event['performers']}, {lead.id, listener.id})
        self.assertEqual({row['performer_id'] for row in event['score']['tracks']}, {lead.id, listener.id})
        self.assertGreater(lead.progress[npc_emotions.KEY]['associations']['performance']['positive'], 0)

    def test_save_reload_keeps_sequence_and_history_without_restoring_an_old_audio_event(self):
        world, lead, _, player, song = fixture()
        # Old singing progress has no emotion fields and still performs normally.
        lead.progress.pop(npc_emotions.KEY)
        lead.progress[singing.KEY] = {'sequence': 7, 'verses': {'song': 3}, 'voice': 'alto'}
        npc_life.ensure(world, lead, check=True)
        with patch.object(singing, 'monotonic', return_value=100):
            singing._perform(world, lead, song)
        saved = json.loads(json.dumps(snapshot(lead)['progress']))
        self.assertEqual(saved[singing.KEY]['sequence'], 8)
        lead.progress = saved
        npc_life.ensure(world, lead, check=True)
        singing.clear(world)
        self.assertEqual(singing.view(world, player), {'events': []})
        with patch.object(singing, 'monotonic', return_value=130):
            singing._perform(world, lead, song)
        self.assertEqual(lead.progress[singing.KEY]['sequence'], 9)
        self.assertEqual(lead.progress[singing.KEY]['verses']['song'], 5)
        self.assertEqual(lead.progress[singing.KEY]['voice'], 'alto')

    def test_player_performance_does_not_infer_private_emotions(self):
        world, _, _, player, song = fixture()
        with patch.object(singing, 'monotonic', return_value=100):
            text = singing._perform(world, player, song)
        expression = world._singing_events['hall']['event']['performers'][0]['expression']
        self.assertEqual(expression, {'emotions': [], 'summary': ''})
        self.assertNotIn('feel', text)
        self.assertNotIn(npc_emotions.KEY, player.progress)

    def test_themes_are_explicit_optional_authored_data(self):
        world, _, _, _, song = fixture()
        data = {'item': list(world.items.values()), 'race': list(world.races.values()), 'npc': list(world.npcs.values())}
        self.assertEqual(singing.validate(data, world.metadata), [])
        song['song']['theme'] = 'remembrance'
        self.assertEqual(singing.validate(data, world.metadata), [])
        song['song']['theme'] = 'all members of this race are always angry'
        self.assertTrue(any('theme must be' in error for error in singing.validate(data, world.metadata)))

    def test_legacy_festival_context_requires_its_authored_place_and_time(self):
        world, lead, _, _, _ = fixture()
        world.metadata['singing']['festivals'] = [dict(id='fair', name='Lantern Fair', room='hall',
                                                     weekday=1, start_minute=600, end_minute=900)]
        world.npcs['singer']['singing'].update(contexts=['festival'], festivals=['fair'])
        data = {'item': list(world.items.values()), 'race': list(world.races.values()),
                'npc': list(world.npcs.values()), 'room': [{'id': key} for key in world.rooms]}
        self.assertEqual(singing.validate(data, world.metadata), [])
        for minute, room in ((599, 'hall'), (900, 'hall'), (600, 'lane'), (2100, 'hall')):
            world.living_state['minute'], lead.location = minute, room
            self.assertFalse(singing.npc_step(world, lead, 'festival'))
        world.living_state['minute'], lead.location = 600, 'hall'
        with patch.object(singing, 'monotonic', return_value=100):
            self.assertTrue(singing.npc_step(world, lead, 'leisure'))
        self.assertEqual(world._singing_events['hall']['event']['festival']['id'], 'fair')
        self.assertEqual(lead.progress[singing.KEY]['next_minute'], 630)
        self.assertEqual(world._singing_events['hall']['next_minute'], 610)
        world.npcs['singer']['singing']['festivals'] = ['missing']
        self.assertTrue(any('unknown festival' in error for error in singing.validate(data, world.metadata)))


if __name__ == '__main__':
    unittest.main()
