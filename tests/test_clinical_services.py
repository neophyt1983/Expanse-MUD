"""Staffed care uses real people, physical supplies, and finite payment."""
from copy import deepcopy
import unittest

from engine import clinical_services, living, locks
from engine.commands import CommandContext
from engine.core import World, Room, Entity


def fixture():
    world = World()
    world.metadata = {'living_world': True, 'daily_life': True, 'society': False}
    world.living_state = {'minute': 480}
    world.add_room(Room('clinic', 'Clinic', '', {'out': 'street'}))
    world.add_room(Room('street', 'Street', '', {'in': 'clinic'}))
    world.items = {key: {'id': key, 'name': key.title()} for key in ('bandage', 'water')}
    world.npcs = {key: {'id': key, 'name': key.title(), 'social_profile': {'sentient': True}}
                  for key in ('doctor', 'resident')}
    world.npcs['doctor']['task_skills'] = {'healing': 30}
    world.room_details = {
        'clinic': {'id': 'clinic', 'services': {'treatment': 4}, 'opening_hours': {'start': 420, 'duration': 600},
                   'locks': [{'id': 'cabinet', 'name': 'Care cabinet', 'owner': 'doctor',
                              'contents': ['bandage', 'bandage', 'water', 'water'], 'locked': False}],
                   'clinical_services': {'enabled': True, 'staff': ['doctor'], 'container': 'cabinet',
                                         'supplies': {'bandage': 1, 'water': 1}, 'min_skill': 20}},
        'street': {'id': 'street'}}
    for key, player in [('patient', True), ('doctor', False), ('resident', False)]:
        actor = Entity(key, key.title(), 40, 50, 4, 2, location='clinic', source_def=None if player else key,
                       is_player=player, gold=10)
        world.entities[key] = actor
        world.rooms['clinic'].entities.append(key)
    world.entities['patient'].progress.update(injury=5, disease=3)
    world.entities['resident'].progress.update(injury=2)
    return world, world.entities['patient'], world.entities['doctor'], world.entities['resident']


class ClinicalServiceTests(unittest.TestCase):
    def test_projection_is_readonly_and_treatment_consumes_stock_pays_staff(self):
        world, patient, doctor, resident = fixture()
        before = deepcopy((world.living_state, patient.progress, doctor.progress))
        self.assertTrue(clinical_services.projection(world, patient)['enabled'])
        self.assertEqual(before, (world.living_state, patient.progress, doctor.progress))
        reply = clinical_services.treat(world, patient)
        self.assertIn('Doctor treats', reply)
        self.assertEqual((patient.gold, doctor.gold), (6, 14))
        self.assertEqual((patient.progress['injury'], patient.progress['disease']), (0, 0))
        self.assertEqual(patient.hp, 40)  # Existing game condition semantics, no fabricated HP effect.
        stored = locks.saved(world, 'clinic', world.room_details['clinic']['locks'][0])
        self.assertEqual(stored['contents'], ['bandage', 'water'])
        self.assertGreater(doctor.progress['task_practice_v1']['healing']['xp'], 0)
        self.assertIn(patient.id, world.dirty_players)
        unchanged = deepcopy((world.living_state, patient.progress, doctor.progress, doctor.gold))
        with self.assertRaisesRegex(ValueError, 'no injury'):
            clinical_services.treat(world, patient)
        self.assertEqual(unchanged, (world.living_state, patient.progress, doctor.progress, doctor.gold))

    def test_npc_patient_uses_same_service_and_empty_stock_blocks_both(self):
        world, patient, doctor, resident = fixture()
        self.assertTrue(clinical_services.step(world, resident))
        clinical_services.treat(world, patient)
        resident.progress['disease'] = 1
        before = deepcopy((world.living_state, resident.progress, resident.gold, doctor.gold))
        with self.assertRaisesRegex(ValueError, 'needs supplies'):
            clinical_services.treat(world, resident)
        self.assertEqual(before, (world.living_state, resident.progress, resident.gold, doctor.gold))
        self.assertFalse(clinical_services.step(world, resident))

    def test_absent_asleep_unqualified_restrained_staff_or_closed_clinic_never_charge(self):
        for condition in ('absent', 'asleep', 'unqualified', 'restrained', 'closed'):
            with self.subTest(condition=condition):
                world, patient, doctor, resident = fixture()
                if condition == 'absent':world.move_entity(doctor.id, 'street', forced=True)
                if condition == 'asleep':doctor.activity = 'sleeping'
                if condition == 'unqualified':doctor.progress['skills'] = {'healing': 1}
                if condition == 'restrained':doctor.progress['restrained_until'] = 500
                if condition == 'closed':world.living_state['minute'] = 1100
                before = deepcopy((world.living_state, patient.progress, patient.gold, doctor.gold))
                with self.assertRaises(ValueError):clinical_services.treat(world, patient)
                self.assertEqual(before, (world.living_state, patient.progress, patient.gold, doctor.gold))

    def test_insufficient_gold_remote_or_spoofed_patient_does_not_mutate(self):
        world, patient, doctor, resident = fixture()
        patient.gold = 0
        with self.assertRaisesRegex(ValueError, 'do not have enough'):clinical_services.treat(world, patient)
        patient.gold = 10
        with self.assertRaisesRegex(ValueError, 'Enter the clinic'):clinical_services.treat(world, deepcopy(patient))
        world.move_entity(patient.id, 'street', forced=True)
        with self.assertRaisesRegex(ValueError, 'no staffed'):clinical_services.treat(world, patient)
        self.assertEqual(doctor.gold, 10)
        self.assertNotIn('clinical_care_v1', world.living_state)

    def test_real_service_command_uses_staffed_path_and_legacy_rooms_keep_original_rule(self):
        world, patient, doctor, resident = fixture()
        text = living.command(CommandContext(world, patient, world.rooms['clinic']), 'treatment', 'service')
        self.assertIn('Doctor treats', text)
        self.assertEqual(doctor.gold, 14)
        world.room_details['clinic'].pop('clinical_services')
        patient.progress['injury'] = 2
        world.move_entity(doctor.id, 'street', forced=True)
        text = living.command(CommandContext(world, patient, world.rooms['clinic']), 'treatment', 'service')
        self.assertEqual(text, 'Treatment completed.')
        self.assertEqual(patient.progress['injury'], 0)

    def test_validation_rejects_nonphysical_supply_and_unstaffed_cabinet(self):
        world, patient, doctor, resident = fixture()
        data = {'room': list(world.room_details.values()), 'npc': list(world.npcs.values()), 'item': list(world.items.values())}
        self.assertEqual(clinical_services.validate(data), [])
        for field, value in [('staff', ['missing']), ('supplies', {'missing': 1}), ('min_skill', True), ('container', 'fake')]:
            changed = deepcopy(data)
            changed['room'][0]['clinical_services'][field] = value
            self.assertTrue(clinical_services.validate(changed), field)


if __name__ == '__main__':unittest.main()
