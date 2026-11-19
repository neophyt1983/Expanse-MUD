"""A contact's visible garment stays exact without rendering unused gear."""
import unittest

from engine.core import World, Room, Entity
from engine import costumes, town_talk, visual_mapping


class CountingItems(dict):
    def __init__(self, rows):super().__init__(rows);self.reads = []
    def get(self, key, default=None):
        self.reads.append(key)
        return super().get(key, default)


def full_protocol_feature(world, person):
    """Observable legacy behavior, using the full map equipment packet."""
    equipment = visual_mapping._player_equipment(world, person)
    body = next((row for row in equipment if row['layer'] == 'body'), {})
    label = (body.get('color', '') + ' ' + body.get('kind', '').replace('_', ' ')).strip()
    if label:return label
    row = world.npcs.get(person.source_def, {})
    appearance = visual_mapping.appearance_for(world, person, row,
        person.race or row.get('race', ''), person.char_class or row.get('char_class', ''), {}, False)
    doll = costumes.npc_doll(world, person, row, appearance, equipment)
    body = next((row for row in doll['equipment'] if row['layer'] == 'body'), {})
    label = (body.get('color', '') + ' ' + body.get('kind', '').replace('_', ' ')).strip()
    if label:return label
    traits = doll['characteristics']
    return 'shaved head' if traits.get('hair_style') == 'bald' else traits['hair_color'] + ' hair'


def fixture():
    world = World();world.metadata = {'living_world': True};world.living_state = {'minute': 400}
    world.add_room(Room('room', 'Room', ''))
    person = Entity('npc:test', 'Resident', 30, 30, 3, 2, source_def='resident', location='room')
    world.entities[person.id] = person;world.rooms['room'].entities.append(person.id)
    world.npcs = {'resident': {'id': 'resident', 'name': 'Resident', 'occupation': 'farmer',
        'social_profile': {'sentient': True, 'species': 'human', 'age_years': 30}}}
    world.items = CountingItems({
        'shirt': {'id': 'shirt', 'name': 'Red woven tunic', 'type': 'armor',
                  'appearance': {'kind': 'tunic', 'color': 'red'}},
        'hat': {'id': 'hat', 'name': 'Blue cap', 'appearance': {'kind': 'hat'}},
        'blade': {'id': 'blade', 'name': 'Steel sword', 'type': 'weapon'},
        'legacy': {'id': 'legacy', 'name': 'Green leather armor', 'type': 'armor'},
        'shield': {'id': 'shield', 'name': 'Wooden shield', 'type': 'armor'},
    })
    return world, person


class ConversationAppearanceTests(unittest.TestCase):
    def test_visible_label_matches_full_map_protocol_for_authored_legacy_and_missing_gear(self):
        cases = [
            {'armor': 'shirt', 'head': 'hat', 'weapon': 'blade'},
            {'armor': 'legacy', 'weapon': 'blade'},
            {'armor': 'shield', 'head': 'hat'},
            {'armor': 'missing', 'weapon': 'blade'},
            {'offhand': 'shirt', 'head': 'hat'},
            {'head': 'hat'}, {},
        ]
        for equipped in cases:
            with self.subTest(equipped=equipped):
                world, person = fixture();person.equipped = equipped
                self.assertEqual(town_talk.visible_feature(world, person), full_protocol_feature(world, person))

    def test_first_body_garment_avoids_rendering_later_unused_slots(self):
        world, person = fixture();person.equipped = {'armor': 'shirt', 'head': 'hat', 'weapon': 'blade'}
        self.assertEqual(town_talk.visible_feature(world, person), 'red tunic')
        self.assertEqual(world.items.reads, ['shirt'])
        packet = visual_mapping._player_equipment(world, person)
        self.assertIsInstance(packet, list)
        self.assertEqual([row['item_id'] for row in packet], ['shirt', 'hat', 'blade'])

    def test_actual_appearance_edits_are_immediately_observed_without_a_cache(self):
        world, person = fixture();person.equipped = {'armor': 'shirt'}
        first = town_talk.visible_feature(world, person)
        world.items['shirt']['appearance']['color'] = 'blue'
        self.assertNotEqual(town_talk.visible_feature(world, person), first)
        person.equipped = {'armor': 'legacy'}
        self.assertEqual(town_talk.visible_feature(world, person), full_protocol_feature(world, person))


if __name__ == '__main__':unittest.main()
