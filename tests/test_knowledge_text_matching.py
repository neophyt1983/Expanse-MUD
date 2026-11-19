"""Text disclosure preserves exact legacy matching without two catalog walks."""
from copy import deepcopy
import re
import unittest

from engine import knowledge, knowledge_sources
from engine.core import Entity, Room, World


def former_matching(world, text):
    """The former two-pass recognition rule, retained as a differential oracle."""
    disclosed = {key: [] for key in knowledge.KINDS}
    replacements = {}
    lower = text.casefold()
    for kind, attr in knowledge.KINDS.items():
        records = getattr(world, attr, {})
        names = {}
        for ident, obj in records.items():
            name = obj.name if kind == 'rooms' else obj.get('name', '')
            if name:names.setdefault(name.casefold(), []).append(ident)
        for ident, obj in records.items():
            name = obj.name if kind == 'rooms' else obj.get('name', '')
            explicit_id = '_' in ident or ':' in ident or '`' + ident + '`' in text
            id_match = explicit_id and ident.casefold() in lower and re.search(
                r'(?<![\w])' + re.escape(ident) + r'(?![\w])', text)
            name_match = (name and len(name) >= 4 and len(names[name.casefold()]) == 1
                          and name.casefold() in lower and re.search(
                              r'(?<![\w])' + re.escape(name) + r'(?![\w])', text, re.I))
            if id_match or name_match:disclosed[kind].append(ident)
            if id_match and name:replacements[ident] = name
    for ident, name in sorted(replacements.items(), key=lambda row: -len(row[0])):
        text = re.sub(r'(?<![\w])' + re.escape(ident) + r'(?![\w])', lambda match: name, text)
    return disclosed, text


def fixture():
    world = World()
    world.metadata = {'living_world': True}
    world.living_state = {'minute': 400}
    for ident, name in [('home', 'Home'), ('room_square', 'Civic Square'),
                        ('room_other', 'CIVIC SQUARE'), ('room_far', 'Distant Hollow'),
                        ('room_punctuation', "The Smith's (Old) Hall")]:
        world.add_room(Room(ident, name, ''))
    world.room_details = {ident: {} for ident in world.rooms}
    world.items = {
        'source_book': {'id': 'source_book', 'name': 'Local ledger', 'read_text': 'Notes.'},
        'item_apple': {'id': 'item_apple', 'name': 'Green Apple'},
        'item_apple_long': {'id': 'item_apple_long', 'name': 'Green Apple Pie'},
        'namespace:ink': {'id': 'namespace:ink', 'name': 'Blue Ink'},
        'plain': {'id': 'plain', 'name': 'Axe'},
        'street_one': {'id': 'street_one', 'name': 'Straße'},
        'street_two': {'id': 'street_two', 'name': 'STRASSE'},
        'no_name': {'id': 'no_name'},
    }
    world.recipes = {
        'recipe_stew': {'id': 'recipe_stew', 'name': 'Garden Stew',
                        'ingredients': {'item_apple': 1}, 'outputs': {'namespace:ink': 1}},
        'recipe_secret': {'id': 'recipe_secret', 'name': 'Hidden Supper'},
    }
    world.quests = {'quest_delivery': {'id': 'quest_delivery', 'name': 'Village Delivery'}}
    actor = Entity('reader', 'Reader', 20, 20, 2, 2, is_player=True, location='home')
    world.add_entity(actor, 'home')
    world.rooms['home'].items.append('source_book')
    return world, actor


class CountedCatalog(dict):
    def __init__(self, rows):
        super().__init__(rows)
        self.walks = 0

    def items(self):
        self.walks += 1
        return super().items()


class TextMatchingTests(unittest.TestCase):
    def test_exact_ids_names_boundaries_case_and_order_match_the_former_rule(self):
        texts = [
            '', 'No catalog names appear in this ordinary sentence.',
            'Civic Square and Distant Hollow; Garden Stew; Village Delivery.',
            'room_square then room_far; item_apple_long and item_apple.',
            'ROOM_SQUARE room_square_extra preitem_apple namespace:ink.',
            'Green Apple Pie, GREEN APPLE, blue ink and Axe.',
            'plain is unquoted; `plain` is explicit. no_name.',
            "Visit The Smith's (Old) Hall, then home.",
            'Straße and STRASSE describe an ambiguous name.',
        ]
        for text in texts:
            with self.subTest(text=text):
                world, actor = fixture()
                expected, rendered = former_matching(world, text)
                other = deepcopy(actor)
                knowledge.teach(world, other, {**expected, 'quests': []})
                self.assertEqual(knowledge.from_text(world, actor, text), rendered)
                self.assertEqual(actor.progress, other.progress)

    def test_each_catalog_is_walked_once_and_unmentioned_names_are_not_cached(self):
        world, actor = fixture()
        for attr in knowledge.KINDS.values():
            setattr(world, attr, CountedCatalog(getattr(world, attr)))
        knowledge.from_text(world, actor, 'Green Apple and room_far.')
        self.assertEqual({attr: getattr(world, attr).walks for attr in knowledge.KINDS.values()},
                         {attr: 1 for attr in knowledge.KINDS.values()})
        self.assertIn('room_far', actor.progress['knowledge']['rooms'])
        # A new ambiguous name must apply immediately without any cache reset.
        world.rooms['new_hollow'] = Room('new_hollow', 'Distant Hollow', '')
        actor.progress = {}
        knowledge.from_text(world, actor, 'Distant Hollow')
        self.assertEqual(actor.progress['knowledge']['rooms'], [])
        world.rooms['new_hollow'].name = 'Nearby Hollow'
        knowledge.from_text(world, actor, 'Distant Hollow')
        self.assertEqual(actor.progress['knowledge']['rooms'], ['room_far'])
        world.rooms['room_far'].name = 'Renamed Hollow'
        actor.progress = {}
        knowledge.from_text(world, actor, 'Distant Hollow')
        self.assertEqual(actor.progress['knowledge']['rooms'], [])

    def test_source_qualification_remains_distinct_from_explicit_disclosures(self):
        world, actor = fixture()
        world.items['source_book'].update(
            knowledge={'rooms': ['room_square'], 'recipes': ['recipe_stew']},
            publication={'work_id': 'local-ledger', 'edition_id': 'first-ledger',
                         'author': 'A local compiler', 'genre': 'Travel', 'kind': 'nonfiction',
                         'claims': [{'id': 'heard', 'text': 'A distant place and design are rumored.',
                                     'certainty': 'rumor', 'evidence_root': 'local-hearsay'}]})
        text = 'room_square, Distant Hollow, Garden Stew and Hidden Supper.'
        result = knowledge.from_text(world, actor, text, source=('item', 'source_book'))
        self.assertIn('Civic Square', result)
        self.assertEqual(actor.progress['knowledge']['rooms'], ['room_square'])
        self.assertEqual(actor.progress['knowledge']['recipes'], ['recipe_stew'])
        for kind, ident in [('rooms', 'room_far'), ('recipes', 'recipe_secret')]:
            topic = knowledge_sources.view(actor, kind, ident)
            self.assertEqual(topic['qualities'], ['rumor'])
            self.assertEqual(topic['evidence_roots'], ['local-hearsay'])
        self.assertNotIn('town_talk', actor.progress, 'A name mention does not invent a route.')


if __name__ == '__main__':unittest.main()
