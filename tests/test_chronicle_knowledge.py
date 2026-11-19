"""A spawn catalog is not a public field survey."""
from copy import deepcopy
import unittest

from engine import chronicles, field_archive, knowledge, knowledge_sources
from engine.core import Entity
from tests.test_npc_backgrounds import fixture


class ChronicleKnowledgeTests(unittest.TestCase):
    def prepare(self):
        world, reader = fixture()
        world.npcs['horror'] = dict(id='horror',name='Unknown Horror',description='An unfamiliar many-limbed shape.',
            is_monster=True,spawn_room='remote',regional_range='Secret northern range',social_profile={'sentient':False})
        world.npcs['legend'] = dict(id='legend',name='A Published Legend',description='A figure in an attributed account.',
            is_monster=True,spawn_room='remote')
        horror=Entity('horror-body','Unknown Horror',20,20,2,2,source_def='horror')
        world.add_entity(horror,'remote')
        book={'version':1,'edition':'source-edition','frontier':[['Where the record ends','The hills remain poorly reported.']],
              'monsters':{'legend':{'text':'An old account says it was heard beyond the hills.',
                                     'range':'Rumored hills','title':'A traveler’s account'}}}
        archive={'version':1,'present':480,'seed':'fixed','events':[],'people':{},'field_catalog_revision':2}
        rooms=[dict(id=ident,name=room.name,**world.room_details.get(ident,{})) for ident,room in world.rooms.items()]
        field_archive.compile_volume(archive,book,rooms,list(world.npcs.values()),[],[],[],[],[])
        world.chronicles=archive
        return world,reader,horror

    def test_unobserved_catalog_monsters_and_spawn_sites_are_not_public(self):
        world,reader,horror=self.prepare()
        public=chronicles.page(world,reader,'monstorium')
        self.assertEqual([row['name'] for row in public['entries']],['A Published Legend'])
        text=str(public)
        self.assertNotIn('Secret northern range',text)
        self.assertNotIn('Documented sites',text)
        self.assertNotIn('remote',text)
        self.assertIn('An old account says',text)
        self.assertEqual(world.chronicles['field_catalog_revision'],3)

    def test_real_encounter_is_limited_identification_and_survives_departure(self):
        world,reader,horror=self.prepare()
        world.rooms['remote'].entities.remove(horror.id);world.rooms['home'].entities.append(horror.id);horror.location='home'
        current=chronicles.page(world,reader,'monstorium','Unknown Horror')
        self.assertEqual(current['total'],1)
        self.assertIn('does not establish a wider range',current['entries'][0]['text'])
        self.assertNotIn('Secret northern range',str(current))
        self.assertNotIn(knowledge_sources.KEY,reader.progress,'A chronicle projection cannot train an encounter.')
        knowledge.observe_room(world,reader,event_id='actual-look')
        horror.location='remote';world.rooms['home'].entities.remove(horror.id);world.rooms['remote'].entities.append(horror.id)
        before=deepcopy(reader.progress)
        self.assertEqual(chronicles.page(world,reader,'monstorium','Unknown Horror')['total'],1)
        self.assertEqual(reader.progress,before)
        self.assertNotIn('remote',knowledge.ids(world,reader,'rooms'))

    def test_generated_local_geology_does_not_claim_global_survey_coverage(self):
        world,reader,_=self.prepare()
        world.chronicles['events'].append(dict(domain='geology',at=480,place='remote',coverage='local',
            text='A local landform note.',heading='Distant rocks'))
        self.assertEqual(chronicles.page(world,reader,'geology')['total'],0)
        knowledge.teach(world,reader,{'rooms':['remote']})
        self.assertEqual(chronicles.page(world,reader,'geology')['total'],1)
        self.assertEqual(chronicles.page(world,reader,'knowledge')['entries'][0]['text'],
                         'The hills remain poorly reported.')


if __name__=='__main__':unittest.main()
