"""An authored patch binds real local holdings without changing source files."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import author_animal_profiles as author


def fixture():
    data={'species':[{'id':'species_chicken','name':'Chicken','category':'bird','sentient':False}],
          'npc':[{'id':'chicken','social_profile':{'species':'species_chicken','sentient':False}}],
          'room':[]}
    for ident in ('farm_a','farm_b'):
        data['npc'].append({'id':ident+'_keeper','spawn_room':ident,'work_room':ident,
                            'title':'Farm Keeper','social_profile':{'sentient':True},
                            'description':'A trained caretaker responsible for feeding, habitat maintenance and records.'})
        data['room'].append({'id':ident,'facilities':['husbandry'],'climate':{'sheltered':True},
                            'locks':[{'id':'feed','owner':ident+'_keeper','contents':['grain']}],
                            'spawners':[{'npc':'chicken','count':1}]})
    return data


class AnimalAuthoringTests(unittest.TestCase):
    def test_reused_template_gets_distinct_exact_local_keepers_without_extra_animals(self):
        data=fixture();before=deepcopy(data)
        patch=author.build_patch(data);updated=author.apply_patch(data,patch)
        self.assertEqual(data,before)
        self.assertEqual(updated['species'][0]['flight']['mode'],'short')
        self.assertEqual(len(updated['npc']),len(data['npc']))
        for room in updated['room']:
            cfg=room['spawners'][0]['livestock']
            self.assertEqual(cfg['owner'],room['id']+'_keeper')
            self.assertEqual(cfg['rooms'],[room['id']])
            self.assertEqual(room['spawners'][0]['count'],1)
            self.assertTrue(room['animal_shelter'])
        self.assertEqual(author.apply_patch(updated,patch),updated)
        self.assertEqual(author.build_patch(updated)['changes'],[])

    def test_a_nearby_worker_or_a_name_is_not_ownership_evidence(self):
        data=fixture()
        data['room'][0]['locks'][0].pop('owner')
        data['npc'][2]['description']='A resident named Farmer.'
        patch=author.build_patch(data)
        self.assertFalse(any(change['path'][-1]=='livestock' for change in patch['changes']))
        self.assertEqual(len(patch['skipped']),2)

    def test_existing_flight_authorship_and_livestock_are_preserved(self):
        data=fixture();data['species'][0]['flight']={'mode':'flightless'}
        data['room'][0]['spawners'][0]['livestock']={'owner':'farm_a_keeper','home':'farm_a'}
        patched=author.apply_patch(data,author.build_patch(data))
        self.assertEqual(patched['species'][0]['flight'],{'mode':'flightless'})
        self.assertEqual(patched['room'][0]['spawners'][0]['livestock'],{'owner':'farm_a_keeper','home':'farm_a'})

    def test_changed_spawner_or_field_is_rejected_before_staging_mutates(self):
        data=fixture();patch=author.build_patch(data)
        data['room'][0]['spawners'][0]['npc']='another_animal'
        before=deepcopy(data)
        with self.assertRaisesRegex(ValueError,'spawner changed'):author.apply_patch(data,patch)
        self.assertEqual(data,before)

    def test_cli_patches_only_separate_staging_and_refuses_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);original=directory/'original';staging=directory/'staging'
            original.mkdir();staging.mkdir();data=fixture()
            for kind,name in author.FILES.items():
                for folder in (original,staging):(folder/name).write_text(json.dumps(data[kind]))
            before={name:(original/name).read_bytes() for name in author.FILES.values()}
            command=[sys.executable,author.__file__,'--world',str(original),'--patch-output',str(directory/'patch.json')]
            result=subprocess.run(command+['--apply-to',str(staging)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual({name:(original/name).read_bytes() for name in before},before)
            self.assertIn('livestock',author.load(staging)['room'][0]['spawners'][0])
            denied=subprocess.run(command+['--apply-to',str(original)],capture_output=True,text=True)
            self.assertNotEqual(denied.returncode,0)
            self.assertIn('read-only',denied.stderr)
            self.assertEqual({name:(original/name).read_bytes() for name in before},before)


if __name__=='__main__':unittest.main()
