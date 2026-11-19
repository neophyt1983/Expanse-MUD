"""Founders have bounded, sourced histories; saved lives are not rerolled."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from engine import founding_residents, knowledge, npc_backgrounds as backgrounds, npc_emotions
from engine.core import Entity, Room, World
from engine.entity_snapshot import snapshot


def fixture():
    world = World()
    world.metadata = {'living_world': True, 'society': True, 'resident_seed': 'fixed-seed'}
    world.living_state = {'minute': 480}
    for ident, exits in [('home', {'east': 'lane', 'west': 'danger', 'north': 'private'}),
                         ('work', {'west': 'lane'}), ('lane', {'west': 'home', 'east': 'work'}),
                         ('danger', {}), ('private', {}), ('remote', {})]:
        world.add_room(Room(ident, ident.title(), '', exits))
    world.room_details = {'home': {}, 'work': {}, 'lane': {}, 'danger': {'dangerous': True},
                          'private': {'property_unit_id': 'private'}, 'remote': {}}
    world.items = {
        'manual': {'id': 'manual', 'read_text': 'An authored local cooking manual.',
                   'knowledge': {'rooms': ['work', 'remote'], 'items': ['bowl'], 'recipes': ['stew'], 'quests': ['secret']}},
        'bowl': {'id': 'bowl'}, 'veg': {'id': 'veg'}, 'meal': {'id': 'meal'},
        'remote_book': {'id': 'remote_book', 'read_text': 'Distant text.', 'knowledge': {'rooms': ['remote']}}}
    world.rooms['home'].items = ['manual']
    world.recipes = {'stew': {'id': 'stew', 'ingredients': {'veg': 1}, 'outputs': {'meal': 1}}}
    world.quests = {'secret': {'id': 'secret'}}
    world.npcs = {
        'resident': {'id': 'resident', 'name': 'Mira', 'home_room': 'home', 'work_room': 'work',
                     'occupation': 'cook', 'hp': 20, 'attack': 2, 'defense': 2, 'spawn_room': 'home',
                     'social_profile': {'sentient': True, 'age_years': 30}},
        'teacher': {'id': 'teacher', 'name': 'Ada', 'home_room': 'home', 'work_room': 'work',
                    'social_profile': {'sentient': True}, 'task_skills': {'cooking': 45}},
        'officer': {'id': 'officer', 'name': 'Ivo', 'home_room': 'home', 'profession': 'guard',
                    'social_profile': {'sentient': True}}}
    world.npcs['resident']['background'] = dict(version=1, enabled=True, home_room='home', nearby_limit=8,
        caregivers=['teacher'], training=[dict(skill='cooking', minimum=8, maximum=22,
                                               source=dict(kind='npc', id='teacher'))],
        reading=['manual', 'remote_book'], experiences=[dict(kind='support received', source='teacher'),
                                                      dict(kind='authority harmed', source='officer')])
    actor = Entity('mira', 'Mira', 20, 20, 2, 2, source_def='resident')
    world.add_entity(actor, 'home')
    return world, actor


class BackgroundTests(unittest.TestCase):
    def test_only_real_bounded_sources_seed_initial_facts_and_practice(self):
        world, actor = fixture()
        before = deepcopy((actor.inventory, actor.gold, actor.explored_rooms, world.living_state,
                           actor.progress['npc_life']))
        self.assertTrue(backgrounds.initialize(world, actor, fresh=True))
        known = actor.progress['knowledge']
        self.assertEqual(set(known['rooms']), {'home', 'work', 'lane'})
        self.assertEqual(set(known['items']), {'manual', 'bowl', 'veg', 'meal'})
        self.assertEqual(known['recipes'], ['stew'])
        self.assertEqual(known['quests'], [])
        self.assertNotIn('quest_sources', actor.progress)
        self.assertNotIn('actions', actor.progress)
        self.assertEqual((actor.inventory, actor.gold, actor.explored_rooms, world.living_state,
                          actor.progress['npc_life']), before)
        self.assertGreaterEqual(actor.progress['skills']['cooking'], 8)
        self.assertLessEqual(actor.progress['skills']['cooking'], 22)
        saved = actor.progress[backgrounds.KEY]
        self.assertEqual(saved['rumors'], [dict(room='danger', source='home', familiarity='mention')])
        self.assertEqual(saved['experiences'][1]['source'], 'officer')
        self.assertGreater(saved['interests']['cooking'], 0)
        self.assertNotIn('danger', actor.progress['town_talk']['roads'].get('home', {}).values())
        self.assertEqual(set(actor.progress[npc_emotions.KEY]['associations']), {'learning', 'support', 'authority'})
        backgrounds.validate_saved(actor.progress)

    def test_saved_learning_and_same_identity_survive_reload_and_content_changes(self):
        world, actor = fixture()
        actor.progress['skills'] = {'cooking': 81, 'observation': 42}
        knowledge.teach(world, actor, {'rooms': ['remote']})
        self.assertTrue(backgrounds.initialize(world, actor, fresh=True))
        self.assertEqual(actor.progress['skills']['cooking'], 81)
        self.assertIn('remote', actor.progress['knowledge']['rooms'])
        saved = json.loads(json.dumps(snapshot(actor)['progress']))
        actor.progress = saved
        before = deepcopy(saved)
        world.metadata['resident_seed'] = 'a later editor revision'
        world.npcs['resident']['background']['training'][0]['maximum'] = 40
        self.assertFalse(backgrounds.initialize(world, actor, fresh=True))
        self.assertEqual(actor.progress, before)
        for _ in range(3):
            self.assertEqual(backgrounds.interests(world, actor), before[backgrounds.KEY]['interests'])
            npc_emotions.project(world, actor)
        self.assertEqual(actor.progress, before)

    def test_existing_life_requires_explicit_additive_migration(self):
        world, actor = fixture()
        before = deepcopy(actor.progress)
        self.assertFalse(backgrounds.initialize(world, actor))
        self.assertEqual(actor.progress, before)
        world.npcs['resident']['background']['migrate_existing'] = True
        self.assertTrue(backgrounds.initialize(world, actor))
        self.assertEqual(actor.progress[backgrounds.KEY]['origin'], 'authored_migration')
        old, other = fixture()
        self.assertTrue(backgrounds.initialize(old, other, fresh=True))
        self.assertEqual(actor.progress['skills'], other.progress['skills'])

    def test_invalid_sources_and_malformed_saved_facts_fail_before_writes(self):
        for change in (lambda c: c.update(home_room=['not-an-id']),
                       lambda c: c['training'][0].update(skill=['not-a-task']),
                       lambda c: c['training'][0]['source'].update(id='missing'),
                       lambda c: c['training'][0].update(maximum=90),
                       lambda c: c['experiences'].append(dict(kind='authority harmed', source='teacher'))):
            world, actor = fixture()
            change(world.npcs['resident']['background'])
            before = deepcopy(actor.progress)
            with self.assertRaises(ValueError): backgrounds.initialize(world, actor, fresh=True)
            self.assertEqual(actor.progress, before)
        world, actor = fixture()
        actor.progress['knowledge'] = {'rooms': 'saved data must not be discarded'}
        before = deepcopy(actor.progress)
        with self.assertRaises(ValueError): backgrounds.initialize(world, actor, fresh=True)
        self.assertEqual(actor.progress, before)

    def test_new_adventure_roster_persists_background_without_requiring_renaming(self):
        world, actor = fixture()
        definition = deepcopy(world.npcs['resident'])
        definition.pop('background')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'npcs.json').write_text(json.dumps([definition]))
            (path / 'rooms.json').write_text(json.dumps([{'id': key} for key in world.rooms]))
            (path / 'metadata.json').write_text('{}')
            roster = founding_residents.make(path, 77)
            self.assertEqual(roster, founding_residents.make(path, 77))
            background = roster['changes']['resident']['background']
            self.assertEqual(background['training'][0]['source'], dict(kind='workplace', id='work'))
            founding_residents.apply(path, roster)
            actual = json.loads((path / 'npcs.json').read_text())[0]
            self.assertEqual(actual['name'], definition['name'])
            self.assertEqual(actual['background'], background)
            self.assertNotIn('founding_profile', actual)

    def test_fresh_loader_and_restore_boundaries_preserve_the_same_record(self):
        from engine.loader import spawn_npcs
        from engine import living
        world, actor = fixture()
        world.entities.clear()
        for room in world.rooms.values(): room.entities.clear()
        spawn_npcs(world)
        person = world.entities['npc:resident']
        self.assertIn(backgrounds.KEY, person.progress)
        saved = living.snapshot(world)
        old = deepcopy(person.progress[backgrounds.KEY])
        living.restore(world, saved)
        self.assertEqual(world.entities[person.id].progress[backgrounds.KEY], old)


if __name__ == '__main__':
    unittest.main()
