"""Staged literature is finite, attributed, idempotent and source constrained."""
from copy import deepcopy
import unittest

from engine import knowledge, npc_backgrounds, publications
from tests.test_npc_backgrounds import fixture as world_fixture
from tools.stage_knowledge_content import apply, BIOGRAPHIES, COMMON, LIBRARIES, PATCH


def fixture():
    items=[dict(id=ident,name=ident.replace('_',' ').title()) for ident in ('sx_paper','sx_ink','material','result')]
    rooms=[dict(id=ident,name=ident+' Library',facilities=['library','scriptorium'],items=[]) for ident in LIBRARIES]
    npcs=[]
    for ident in ('rhome_oren','locks_lw_hearth_school_tutor',*(row[0] for row in BIOGRAPHIES)):
        npcs.append(dict(id=ident,name=ident.title(),description='A public account of '+ident+'.',
                         home_room=LIBRARIES[0],work_room=LIBRARIES[0],occupation='scribe',
                         social_profile={'sentient':True,'age_years':25},inventory=['private-token']))
    recipes=[dict(id=ident,name=ident.replace('_',' ').title(),kind='crafting',location=LIBRARIES[0],
                  station='workbench',minutes=5,ingredients={'material':1},outputs={'result':1})
             for _,_,ids,_ in COMMON for ident in ids]
    recipes.append(dict(id='local_pie',name='Local Pie',kind='cooking',location=LIBRARIES[0],
                        ingredients={'material':2},outputs={'result':1},station='kitchen',minutes=8))
    items.extend([
        dict(id='old_cookbook',name='The Local Kitchen',read_text='An older recipe in its own words.',
             publication={'author':'A prior writer','genre':'Food and cookery','kind':'nonfiction'},knowledge={'recipes':['local_pie']}),
        dict(id='old_poem',name='The Lantern on the Shelf',read_text='Leave a little light by the door.',
             publication={'author':'A local poet','genre':'Verse and performance','kind':'fiction'}),
    ])
    rooms[0]['items']=['old_cookbook','old_poem']
    return {'items':items,'rooms':rooms,'recipes':recipes,'npcs':npcs}, {'start_minute':375}


class KnowledgeContentTests(unittest.TestCase):
    def test_new_sources_have_finite_placements_and_material_copy_requirements(self):
        data,meta=fixture();old={item['id']:deepcopy(item) for item in data['items']}
        report=apply(data,meta);items={row['id']:row for row in data['items']};recipes={row['id']:row for row in data['recipes']}
        self.assertEqual(len(report['shared_designs']),5)
        self.assertEqual(len(report['local_sources']),1)
        self.assertEqual(len(report['books']),9)
        self.assertEqual(len(report['placements']),37)
        for placement in report['placements']:
            self.assertEqual(placement['quantity'],1)
            self.assertFalse(items[placement['item']].get('anchored_readable'))
        for row in report['books']:
            item=items[row['id']];copy=recipes['copy_'+row['id']]
            self.assertEqual(copy['ingredients'],{'sx_paper':2,'sx_ink':1})
            self.assertEqual(copy['requires_reading'],[row['id']])
            self.assertEqual(copy['knowledge_scope'],'private')
            self.assertNotIn('private-token',item['read_text'])
            self.assertNotIn('Authored working time',item['read_text'])
            self.assertNotIn('game’s authored',item['read_text'])
        for ident,item in old.items():self.assertEqual(items[ident],item,'An older work keeps its complete text and metadata.')
        self.assertEqual(publications.validate({'item':data['items']}),[])
        self.assertEqual(npc_backgrounds.validate({'npc':data['npcs'],'room':data['rooms'],'item':data['items']}),[])

    def test_twice_applied_patch_never_replenishes_removed_copies_or_rerolls_backgrounds(self):
        data,meta=fixture();apply(data,meta)
        data['rooms'][0]['items'].remove('knowledge119_paper_ink')
        before=deepcopy((data,meta))
        self.assertEqual(apply(data,meta),{'patch':PATCH,'already_applied':True})
        self.assertEqual((data,meta),before)

    def test_biographies_preserve_distinct_qualified_perspectives_and_unknown_dates(self):
        data,meta=fixture();apply(data,meta)
        biographies=[item for item in data['items'] if item.get('publication',{}).get('genre')=='Biography and civic criticism']
        self.assertEqual(len(biographies),3)
        for item in biographies:
            self.assertEqual([claim['certainty'] for claim in item['publication']['claims']],['sourced','opinion','opinion'])
            self.assertEqual(len(item['publication']['evidence_roots']),1)
            self.assertIn('does not supply a birth date',item['read_text'])
            self.assertIn('A sympathetic reading',item['read_text']);self.assertIn('A critical reading',item['read_text'])

    def test_knowing_the_copy_recipe_does_not_manufacture_an_unread_work(self):
        world,actor=world_fixture();world.recipes['copy']={'id':'copy','name':'Copy The Manual',
            'requires_reading':['manual'],'station':'hand','ingredients':{},'outputs':{'manual':1}}
        knowledge.teach(world,actor,{'recipes':['copy']})
        with self.assertRaisesRegex(ValueError,'Read the source text'):knowledge.crafting_choice(world,actor,'copy')
        knowledge.read_source(world,actor,'manual')
        self.assertTrue(knowledge.recipe_source_ready(actor,world.recipes['copy']))
        self.assertEqual(knowledge.crafting_choice(world,actor,'copy')['id'],'copy')
        actor.progress.pop(publications.MEMORY)
        actor.progress['reading_journal_v1']=['manual']
        self.assertTrue(knowledge.recipe_source_ready(actor,world.recipes['copy']),'A real legacy journal remains usable.')


if __name__=='__main__':unittest.main()
