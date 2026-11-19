"""Expressions use actual needs, remembered events and current social context."""
from copy import deepcopy
import json
import unittest

from engine import npc_emotions as emotions, npc_life, relationships, worldtime
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot


def fixture():
    world = World()
    world.metadata = {'living_world': True, 'society': True, 'needs_economy': True,
                      'daily_life': True}
    world.living_state = {'minute': 480}
    world.add_room(Room('square', 'Square', 'A public square.', {'east': 'lane'}))
    world.add_room(Room('lane', 'Lane', 'A quiet lane.', {'west': 'square'}))
    world.room_details = {'square': {'laws': {'enabled': True, 'authority': 'watch'}}, 'lane': {}}
    world.npcs = {
        'resident': {'id': 'resident', 'social_profile': {'sentient': True}, 'life_profile': {'mood': 50}},
        'guard': {'id': 'guard', 'profession': 'guard', 'social_profile': {'sentient': True},
                  'life_profile': {'mood': 50}, 'work_hours': {'start': 420, 'duration': 600}},
    }
    resident = Entity('mira', 'Mira', 50, 50, 3, 3, source_def='resident', group_id='town')
    officer = Entity('warden', 'Warden', 50, 50, 4, 4, source_def='guard', group_id='watch')
    friend = Entity('friend', 'Friend', 50, 50, 3, 3, source_def='resident', group_id='town')
    player = Entity('player', 'Player', 50, 50, 3, 3, is_player=True, group_id='town')
    for person in (resident, officer, friend, player):
        world.add_entity(person, 'square')
    return world, resident, officer, friend, player


def scores(result):
    return {row['id']: row['intensity'] for row in result['emotions']}


class NpcEmotionTests(unittest.TestCase):
    def test_projection_is_read_only_and_neutral_resident_has_no_invented_history(self):
        world, person, _, _, _ = fixture()
        before = deepcopy((person.progress, world.living_state))
        for _ in range(5):
            self.assertEqual(emotions.project(world, person), {'emotions': [], 'summary': ''})
        self.assertEqual((person.progress, world.living_state), before)
        self.assertEqual(person.progress[emotions.KEY]['associations'], {})

    def test_hunger_and_positive_mood_can_coexist_without_a_new_need_model(self):
        world, person, _, _, _ = fixture()
        person.progress['npc_life']['mood'] = 80
        person.progress['needs'] = {'hunger': 90, 'rest': 70, 'safety': 60}
        result = emotions.project(world, person)
        self.assertTrue({'happy', 'irritated', 'tired', 'anxious', 'afraid'} <= scores(result).keys())
        self.assertTrue(all(0 < row['intensity'] <= 100 for row in result['emotions']))
        before = deepcopy(person.progress)
        world.metadata['needs_economy'] = False
        self.assertEqual(set(scores(emotions.project(world, person))), {'happy'})
        self.assertEqual(person.progress, before)

    def test_accepted_life_events_train_once_and_keep_opposed_experiences(self):
        world, person, _, _, _ = fixture()
        npc_life.event(world, person, 'insulting', -6, source='actual-speaker', event_id='insult-1')
        npc_life.event(world, person, 'happy', 2, source='actual-speaker', event_id='greeting-1')
        before = deepcopy(person.progress)
        npc_life.event(world, person, 'happy', 2, source='actual-speaker', event_id='greeting-1')
        self.assertEqual(person.progress, before)
        association = person.progress[emotions.KEY]['associations']['social']
        self.assertEqual(association['count'], 2)
        self.assertGreater(association['positive'], 0)
        self.assertGreater(association['negative'], 0)
        self.assertTrue({'sad', 'angry', 'happy'} <= scores(emotions.project(world, person)).keys())

    def test_lifetime_authority_experiences_survive_expiry_save_reload_and_map_refresh(self):
        world, person, officer, friend, _ = fixture()
        for index in range(12):
            self.assertTrue(emotions.authority_experience(world, person, officer, helpful=False,
                                                         event_id='adverse-' + str(index)))
            self.assertTrue(emotions.authority_experience(world, person, officer, helpful=True,
                                                         event_id='helpful-' + str(index)))
        world.living_state['minute'] += 20 * worldtime.MINUTES_PER_DAY
        npc_life.step(world, person)
        self.assertEqual(person.progress['npc_life']['memories'], [])
        self.assertEqual(person.progress['npc_life']['mood'], 50)
        saved = json.loads(json.dumps(snapshot(person)['progress']))
        person.progress = saved
        npc_life.ensure(world, person, check=True)
        before = deepcopy(person.progress)
        with_officer = scores(emotions.project(world, person, partner=officer))
        self.assertTrue({'anxious', 'afraid', 'calm', 'hopeful'} <= with_officer.keys())
        self.assertNotIn('anxious', scores(emotions.project(world, person, partner=friend)))
        self.assertEqual(person.progress, before)

    def test_legacy_bootstrap_uses_only_retained_real_memories_and_is_idempotent(self):
        world, person, _, _, _ = fixture()
        person.progress.pop(emotions.KEY)
        life = person.progress['npc_life']
        life['memories'] = [dict(kind='gift_wanted', impact=5, source='known-donor',
                                  at=400, expires=1900, id='gift-actual')]
        npc_life.ensure(world, person, check=True)
        saved = deepcopy(person.progress[emotions.KEY])
        for _ in range(4):
            npc_life.ensure(world, person, check=True)
            emotions.project(world, person)
        self.assertEqual(person.progress[emotions.KEY], saved)
        self.assertEqual(set(saved['associations']), {'support'})
        self.assertEqual(saved['associations']['support']['count'], 1)

    def test_experience_memory_is_bounded_and_validated_at_load_boundary(self):
        world, person, _, _, _ = fixture()
        for index in range(200):
            emotions.record(world, person, 'authority harmed', event_id=str(index))
        saved = person.progress[emotions.KEY]
        self.assertEqual(len(saved['seen']), emotions.MAX_SEEN)
        self.assertEqual(len(person.progress['npc_life']['memories']), npc_life.MAX_MEMORIES)
        self.assertLessEqual(saved['associations']['authority']['negative'], 100)
        npc_life.validate_saved(person.progress)
        saved['associations']['authority']['positive'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'emotion experience score'):
            npc_life.ensure(world, person, check=True)

    def test_reporting_known_loss_keeps_sad_angry_anxious_and_hopeful_together(self):
        world, person, officer, _, _ = fixture()
        emotions.record(world, person, 'theft loss observed', event_id='own-observation')
        self.assertTrue(emotions.report_received(world, person, officer, event_id='own-observation'))
        result = emotions.project(world, person)
        self.assertTrue({'sad', 'angry', 'anxious', 'hopeful'} <= scores(result).keys())
        public = json.dumps(result)
        for private in ('own-observation', 'warden', 'source', 'inventory', 'associations'):
            self.assertNotIn(private, public)

    def test_report_cannot_be_fabricated_from_global_crime_record_or_remote_officer(self):
        world, person, officer, _, _ = fixture()
        world.living_state['mortality'] = {'wanted': {'player': {'victim': person.id, 'kind': 'theft'}}}
        before = deepcopy(person.progress)
        self.assertFalse(emotions.report_received(world, person, officer, event_id='unknown'))
        self.assertEqual(person.progress, before)
        emotions.record(world, person, 'theft loss observed', event_id='known')
        world.move_entity(officer.id, 'lane')
        self.assertFalse(emotions.report_received(world, person, officer, event_id='known'))
        world.move_entity(officer.id, 'square')
        officer.activity = 'sleeping'
        self.assertFalse(emotions.report_received(world, person, officer, event_id='known'))

    def test_trust_and_authority_context_use_existing_bond_without_creating_new_ones(self):
        world, person, officer, friend, _ = fixture()
        bond = relationships.bond(world, person, friend)
        bond.update(trust=-35, kinds=['friend'])
        before = deepcopy(world.living_state)
        self.assertTrue({'anxious', 'affectionate'} <= scores(emotions.project(world, person, partner=friend)).keys())
        emotions.project(world, person, partner=officer)
        self.assertEqual(world.living_state, before)
        officer.name = 'Very Scary Police Authority'
        world.npcs['guard']['profession'] = 'baker'
        self.assertFalse(emotions.authority(world, person, officer), 'Display names never grant authority.')

    def test_reading_reactions_require_the_residents_known_article_not_urgent_words(self):
        world, person, _, _, _ = fixture()
        person.progress['town_talk'] = {'news': {
            'education': {'section': 'Education', 'headline': 'THIEF! A classroom performance'},
            'safety': {'section': 'Public safety', 'headline': 'An actual local warning'},
        }}
        before = deepcopy(person.progress)
        self.assertEqual(scores(emotions.project(world, person, topic='reading', article_id='unknown')), {})
        learning = scores(emotions.project(world, person, topic='reading', article_id='education'))
        self.assertTrue({'curious', 'hopeful'} <= learning.keys())
        self.assertNotIn('afraid', learning)
        self.assertNotIn('anxious', learning)
        self.assertIn('anxious', scores(emotions.project(world, person, topic='reading', article_id='safety')))
        self.assertEqual(person.progress, before)

    def test_transient_context_expires_or_ends_on_departure_without_changing_history(self):
        world, person, _, friend, _ = fixture()
        relationships.bond(world, person, friend)['trust'] = -60
        emotions.context(world, person, partner=friend, topic='people')
        self.assertIn('anxious', scores(emotions.project(world, person)))
        friend.location = 'lane'
        self.assertNotIn('anxious', scores(emotions.project(world, person)))
        person._emotion_context['until'] = 0
        self.assertEqual(scores(emotions.project(world, person)), {})

    def test_player_and_dead_npc_do_not_get_inferred_emotions(self):
        world, person, _, _, player = fixture()
        self.assertFalse(emotions.record(world, player, 'theft loss observed', event_id='never'))
        self.assertNotIn(emotions.KEY, player.progress)
        self.assertEqual(scores(emotions.project(world, player)), {})
        person.hp = 0
        self.assertEqual(scores(emotions.project(world, person)), {})

    def test_actual_resident_conversation_reports_once_with_mixed_delivery(self):
        from engine import resident_discussion, speech_bubbles
        world, person, officer, _, player = fixture()
        emotions.record(world, person, 'theft loss observed', event_id='seen-taking')
        lines = resident_discussion.everyday(world, person, officer, 0)
        self.assertEqual(lines[0], 'says with a strained voice')
        self.assertIn('I saw it happen', lines[1])
        speech_bubbles.mark(person, officer, 'happy', 'serious', lines)
        who, bubble = speech_bubbles.visible(world, player, world.entities)
        self.assertEqual(who, person.id)
        self.assertTrue({'sad', 'angry', 'anxious', 'hopeful'} <= {row['id'] for row in bubble['emotions']})
        self.assertNotEqual(bubble['symbol'], '🙂', 'The old rotating symbol must not overwrite a mixed expression.')
        self.assertFalse(emotions.report_received(world, person, officer, event_id='seen-taking'))
        reports = [row for row in person.progress['npc_life']['memories'] if row['kind'] == 'report received']
        self.assertEqual(len(reports), 1)

    def test_known_read_article_trains_once_without_treating_refresh_as_reading(self):
        world, person, _, _, _ = fixture()
        person.progress['town_talk'] = {'news': {'paper': {'section': 'Education', 'headline': 'A local lesson'}}}
        self.assertFalse(emotions.read_article(world, person, 'remote-secret'))
        self.assertTrue(emotions.read_article(world, person, 'paper'))
        before = deepcopy(person.progress[emotions.KEY])
        for _ in range(5):
            emotions.project(world, person)
            emotions.read_article(world, person, 'paper')
        self.assertEqual(person.progress[emotions.KEY], before)
        self.assertIn('curious', scores(emotions.project(world, person)))

    def test_actual_guard_social_action_changes_future_authority_association(self):
        from engine import social
        world, person, officer, _, _ = fixture()
        social.change(world, officer, person, -6, 'insulting')
        adverse = person.progress[emotions.KEY]['associations']['authority']['negative']
        self.assertGreater(adverse, 0)
        social.change(world, officer, person, 5, 'gift_wanted')
        history = person.progress[emotions.KEY]['associations']['authority']
        self.assertEqual(history['negative'], adverse)
        self.assertGreater(history['positive'], 0)


if __name__ == '__main__':
    unittest.main()
