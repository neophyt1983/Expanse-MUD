"""Theft wording, permissions and retained evidence use real container actions."""
import unittest

from engine import burglary, locks, mortality, speech_bubbles
from engine.core import Entity, Room, World
from test_burglary import Rolls


def kitchen(*, witness=True):
    world = World()
    world.metadata = {'living_world': True, 'society': True}
    world.rules = {'regional_gameplay': {'enabled': True}}
    world.living_state = {'minute': 480}
    world.add_room(Room('kitchen', 'Tankard Kitchens', 'A working kitchen.', {}))
    world.items = {'bread': {'id': 'bread', 'name': 'Bread'}, 'key': {'id': 'key', 'name': 'Pantry key'}}
    row = {'id': 'pantry', 'name': 'Pantry cabinet', 'locked': False,
           'owner': 'chef', 'key': 'key', 'contents': ['bread', 'bread']}
    world.room_details = {'kitchen': {'locks': [row], 'laws': {'enabled': True, 'authority': 'watch'}}}
    player = Entity('gorimore', 'Gorimore Wild', 100, 100, 10, 10,
                    is_player=True, location='kitchen', group_id='town')
    world.entities[player.id] = player
    world.rooms['kitchen'].entities.append(player.id)
    if witness:
        person = Entity('arden', 'Arden Lightbrook', 100, 100, 10, 10,
                        source_def='chef', location='kitchen', group_id='town')
        world.npcs['chef'] = {'social_profile': {'sentient': True}}
        world.entities[person.id] = person
        world.rooms['kitchen'].entities.append(person.id)
    return world, player, row


class ContainerTheftCommunicationTests(unittest.TestCase):
    def test_private_projection_and_inspection_explain_theft_before_taking(self):
        world, player, row = kitchen()
        view = locks.projection(world, player)[0]
        self.assertFalse(view['permitted'])
        self.assertIn('without permission is theft', view['permission_warning'])
        self.assertIn('theft', locks.act(world, player, 'inspect', 'pantry'))
        self.assertEqual(player.inventory, [])
        self.assertEqual(locks.saved(world, 'kitchen', row)['contents'], ['bread', 'bread'])
        self.assertEqual(mortality.state(world)['wanted'], {})

    def test_witnessed_theft_names_the_act_and_retains_the_exact_container_source(self):
        world, player, row = kitchen()
        player.progress['skills'] = {'burglary': 10}
        text = locks.act(world, player, 'take', 'pantry', rng=Rolls(.1, .1, 0))
        self.assertIn('You steal 2 × Bread from Pantry cabinet.', text)
        self.assertIn('Arden Lightbrook notices the theft.', text)
        self.assertEqual(world.runtime_notifications, [('kitchen',
                         'Arden Lightbrook shouts at Gorimore Wild, “Stop! Taking from Pantry cabinet is theft!”', player.id,
                         {'role':'npc','emphasis':'shout'})])
        self.assertEqual(world.rest_notifications, [(player.id,
                         'Arden Lightbrook shouts at you, “Stop! Taking from Pantry cabinet is theft!”',
                         {'role':'npc','emphasis':'shout'})])
        speaker, bubble = speech_bubbles.visible(world, player, world.entities)
        self.assertEqual(speaker, 'arden')
        self.assertEqual(bubble['tone'], 'shouts')
        self.assertEqual(bubble['words'], 'Stop! Taking from Pantry cabinet is theft!')
        self.assertEqual(player.inventory, ['bread', 'bread'])
        self.assertEqual(locks.saved(world, 'kitchen', row)['contents'], [])
        report = mortality.state(world)['wanted'][player.id]
        self.assertEqual(report['kind'], 'theft')
        self.assertEqual(report['witnesses'], ['arden'])
        evidence = report['evidence'][-1]
        self.assertEqual(evidence['source'], {'kind': 'container', 'id': 'pantry',
                                             'name': 'Pantry cabinet', 'action': 'take', 'quantity': 2})
        self.assertEqual(evidence['room'], 'kitchen')
        self.assertEqual(evidence['actor'], player.id)

    def test_unwitnessed_taking_still_says_steal_without_inventing_an_accusation(self):
        world, player, row = kitchen(witness=False)
        text = locks.transfer(world, player, 'pantry', 'bread', 1, rng=Rolls(.1, .1))
        self.assertTrue(text.startswith('You steal 1 × Bread from Pantry cabinet.'))
        self.assertNotIn('improves to 1', text)
        self.assertGreater(player.progress['task_practice_v1']['burglary']['xp'],0)
        self.assertEqual(burglary.skill(world,player,'burglary'),0)
        self.assertNotIn('notices', text)
        self.assertEqual(mortality.state(world)['wanted'], {})
        self.assertEqual(getattr(world, 'runtime_notifications', []), [])
        self.assertIsNone(speech_bubbles.visible(world, player, world.entities)[0])
        self.assertEqual(player.inventory, ['bread'])
        self.assertEqual(locks.saved(world, 'kitchen', row)['contents'], ['bread'])

    def test_public_key_owner_and_allowed_group_keep_the_normal_take_permission(self):
        for permission in ('public', 'key', 'owner', 'group'):
            with self.subTest(permission=permission):
                world, player, row = kitchen()
                if permission == 'public':row['public'] = True
                if permission == 'key':player.inventory.append('key')
                if permission == 'owner':player.source_def = row['owner']
                if permission == 'group':
                    player.group_id = 'kitchen_staff'
                    row['allowed_groups'] = ['kitchen_staff']
                view = locks.projection(world, player)[0]
                self.assertTrue(view['permitted'])
                self.assertEqual(view['permission_warning'], '')
                rolls = Rolls()
                text = locks.act(world, player, 'take', 'pantry', rng=rolls)
                self.assertEqual(text, 'You take the contents of Pantry cabinet.')
                self.assertEqual(rolls.calls, 0)
                self.assertNotIn(burglary.ATTEMPT_KEY, player.progress)
                self.assertNotIn(burglary.PRACTICE_KEY, player.progress)
                self.assertEqual(mortality.state(world)['wanted'], {})
                self.assertEqual(getattr(world, 'runtime_notifications', []), [])

    def test_a_detecting_owner_calls_out_once_and_only_detectors_remain_in_evidence(self):
        world, player, _ = kitchen()
        world.npcs['visitor'] = {'social_profile': {'sentient': True}}
        for ident, name in [('visitor1', 'First Visitor'), ('visitor2', 'Second Visitor')]:
            person = Entity(ident, name, 100, 100, 10, 10, source_def='visitor', location='kitchen')
            world.entities[ident] = person
            world.rooms['kitchen'].entities.insert(0, ident)
        # The owner and second visitor notice; the first visitor misses it.
        text = locks.act(world, player, 'take', 'pantry', rng=Rolls(.1, .1, 0, .99, 0))
        self.assertIn('Arden Lightbrook notices the theft.', text)
        self.assertIn('Arden Lightbrook shouts', world.rest_notifications[0][1])
        self.assertEqual(len(world.rest_notifications), 1)
        self.assertEqual(set(mortality.state(world)['wanted'][player.id]['witnesses']),
                         {'arden', 'visitor2'})
        self.assertEqual(len(world.runtime_notifications), 1)
        for ident in ('arden','visitor2','visitor1'):
            self.assertEqual(burglary.skill(world,world.entities[ident],'observation'),0)
            self.assertGreater(world.entities[ident].progress['task_practice_v1']['observation']['xp'],0)
        self.assertGreater(world.entities['visitor2'].progress['task_practice_v1']['observation']['xp'],
                           world.entities['visitor1'].progress['task_practice_v1']['observation']['xp'])


if __name__ == '__main__':
    unittest.main()
