"""Actual book use, source identity, immutable corrections and finite copies."""
from copy import deepcopy
import unittest

from engine import publications
from engine.core import Entity,Room,World


def fixture():
    world=World();world.metadata={'living_world':True};world.living_state={'minute':500}
    world.add_room(Room('library','Library','Books on real shelves.'))
    world.add_room(Room('elsewhere','Elsewhere','A distant room.'))
    world.room_details={'library':{},'elsewhere':{}}
    book={'id':'book','name':'Field notes','type':'book','read_text':'The first local survey records a silver-winged bird beside the northern pond.',
          'publication':{'work_id':'field-notes','edition_id':'survey-1','author':'Recorder',
                         'genre':'Natural history','kind':'nonfiction','original_minute':100,
                         'edition_minute':200,'evidence_roots':['pond-observation'],
                         'claims':[{'id':'bird','text':'A silver-winged bird was observed by the pond.',
                                    'certainty':'observed','evidence_root':'pond-observation'}]}}
    world.items={'book':book};world.rooms['library'].items=['book']
    actor=Entity('reader','Reader',30,30,1,1,is_player=True)
    world.add_entity(actor,'library')
    return world,actor,book


class PublicationTests(unittest.TestCase):
    def test_source_is_read_only_and_retains_existing_authorship(self):
        world,actor,book=fixture();before=deepcopy((world.living_state,actor.progress,book))
        record=publications.source(world,'book')
        self.assertEqual((record['kind'],record['id']),('item','book'))
        self.assertEqual(record['evidence_roots'],['pond-observation'])
        self.assertEqual(record['claims'][0]['certainty'],'observed')
        self.assertEqual((world.living_state,actor.progress,book),before)
        self.assertEqual(publications.validate({'item':[book]}),[])

    def test_only_an_actual_readable_copy_records_use_and_same_minute_is_not_replayed(self):
        world,actor,_=fixture()
        publications.record_read(world,actor,'book')
        publications.record_read(world,actor,'book')
        self.assertEqual(publications.view(world,'book')['reads'],1)
        world.living_state['minute']-=1;publications.record_read(world,actor,'book')
        self.assertEqual(publications.view(world,'book')['reads'],1)
        world.living_state['minute']+=2;publications.record_read(world,actor,'book')
        self.assertEqual(publications.view(world,'book')['reads'],2)
        world.move_entity(actor.id,'elsewhere')
        with self.assertRaisesRegex(ValueError,'actual book'):publications.record_read(world,actor,'book')
        actor.inventory.append('book');world.rooms['library'].items.clear()
        world.living_state['minute']+=1;publications.record_read(world,actor,'book')
        self.assertEqual(publications.view(world,'book')['reads'],3)

    def test_circulation_ages_without_deleting_copies_or_changing_book_text(self):
        world,actor,book=fixture();original=deepcopy(book)
        self.assertEqual(publications.view(world,'book')['circulation'],'unrecorded_use')
        publications.record_read(world,actor,'book')
        world.living_state['minute']+=publications.QUIET_MINUTES
        self.assertEqual(publications.view(world,'book')['circulation'],'rarely_used')
        world.living_state['minute']+=publications.INACTIVE_MINUTES
        view=publications.view(world,'book')
        self.assertEqual(view['circulation'],'out_of_use')
        self.assertEqual(view['physical_copies'],1)
        self.assertEqual(book,original)
        publications.record_read(world,actor,'book')
        self.assertEqual(publications.view(world,'book')['circulation'],'in_circulation')

    def test_derived_excerpts_are_drafts_until_a_real_production_action_commits_a_copy(self):
        world,actor,book=fixture();before=deepcopy((world.items,actor.inventory,world.rooms['library'].items))
        with self.assertRaisesRegex(ValueError,'actually read'):
            publications.make_excerpt(world,actor,'book',new_item_id='excerpt',title='Later notes')
        publications.record_read(world,actor,'book')
        draft=publications.make_excerpt(world,actor,'book',new_item_id='excerpt',title='Later notes',claim_ids=['bird'])
        self.assertEqual((world.items,actor.inventory,world.rooms['library'].items),before)
        self.assertNotIn('task_practice_v1',actor.progress)
        self.assertEqual(draft['publication']['evidence_roots'],['pond-observation'])
        self.assertEqual(publications.validate({'item':[book,draft]}),[])

    def test_quote_survives_with_shared_roots_after_original_physical_copy_is_gone(self):
        world,actor,book=fixture();publications.record_read(world,actor,'book')
        excerpt=publications.make_excerpt(world,actor,'book',new_item_id='excerpt',title='Collected notes')
        # A real production fixture commits exactly one physical output.
        world.items['excerpt']=excerpt;actor.inventory.append('excerpt')
        world.rooms['library'].items.remove('book')
        view=publications.view(world,'book')
        self.assertEqual(view['physical_copies'],0)
        self.assertEqual(view['circulation'],'survives_in_excerpts')
        self.assertEqual(view['surviving_excerpts'][0]['copies'],1)
        self.assertEqual(publications.source(world,'excerpt')['evidence_roots'],['pond-observation'])
        self.assertEqual(publications.record_read(world,actor,'excerpt')['evidence_roots'],['pond-observation'])

    def test_lost_source_definition_keeps_explicit_evidence_root_and_attribution(self):
        world,actor,book=fixture();publications.record_read(world,actor,'book')
        excerpt=publications.make_excerpt(world,actor,'book',new_item_id='excerpt',title='Remembered notes')
        world.items={'excerpt':excerpt}
        self.assertEqual(publications.source(world,'excerpt')['evidence_roots'],['pond-observation'])
        self.assertEqual(publications.validate({'item':[excerpt]}),[])
        self.assertEqual(excerpt['publication']['derives_from'][0]['title'],book['name'])

    def test_a_correction_is_a_new_qualified_claim_and_never_edits_prior_text(self):
        world,actor,book=fixture();original=deepcopy(book)
        correction={'id':'revision','name':'Revised field notes','read_text':'A later closer examination identifies a moth.',
                    'publication':{'work_id':'field-notes','edition_id':'survey-2',
                                   'derives_from':[{'edition_id':'survey-1','relation':'revision'}],
                                   'claims':[{'id':'bird-correction','text':'The earlier bird identification is uncertain; the closer observation suggests a moth.',
                                              'certainty':'sourced','qualification':'A later interpretation, subject to further observation.',
                                              'evidence_root':'closer-observation',
                                              'revises':[{'edition_id':'survey-1','claim_id':'bird'}]}]}}
        world.items['revision']=correction
        self.assertEqual(publications.validate({'item':list(world.items.values())}),[])
        record=publications.source(world,'revision')
        self.assertEqual(set(record['evidence_roots']),{'pond-observation','closer-observation'})
        self.assertEqual(record['claims'][0]['revises'],[{'edition_id':'survey-1','claim_id':'bird'}])
        self.assertEqual(book,original)

    def test_copy_cannot_turn_rumor_into_independent_confirmation(self):
        world,actor,book=fixture();book['publication']['claims'][0]['certainty']='rumor'
        publications.record_read(world,actor,'book')
        copy=publications.make_excerpt(world,actor,'book',new_item_id='copy',title='Copied account',claim_ids=['bird'])
        world.items['copy']=copy;actor.inventory=['copy']
        record=publications.record_read(world,actor,'copy')
        self.assertEqual(record['claims'][0]['certainty'],'rumor')
        self.assertEqual(record['evidence_roots'],['pond-observation'])
        copy['publication']['evidence_roots'].append('invented-independent-source')
        self.assertIn('independent evidence',str(publications.validate({'item':list(world.items.values())})))

    def test_finite_census_includes_real_containers_stores_and_inventory_once(self):
        world,actor,_=fixture();actor.inventory=['book']
        world.room_details['library']['locks']=[{'id':'shelf','contents':['book','book']}]
        world.living_state['physical_locks']={'library:shelf':{'contents':['book']}}
        world.living_state['economy']={'shops':{'library':{'stock':{'book':3}}}}
        world.shop_state={'merchant':{'book':2},'infinite':{'book':-1}}
        self.assertEqual(publications.view(world,'book')['physical_copies'],8)

    def test_snapshot_reload_and_npc_reading_preserve_the_same_source_identity(self):
        from engine.entity_snapshot import snapshot
        world,actor,_=fixture();actor.is_player=False
        publications.record_read(world,actor,'book')
        actor.progress=deepcopy(snapshot(actor)['progress']);world.living_state=deepcopy(world.living_state)
        self.assertEqual(publications.source(world,'book')['edition_id'],'survey-1')
        self.assertEqual(publications.view(world,'book')['reads'],1)
        self.assertEqual(publications.make_excerpt(world,actor,'book',new_item_id='npc_excerpt',title='Notebook')['publication']['evidence_roots'],['pond-observation'])

    def test_validation_rejects_cycles_conflicting_editions_and_unqualified_revisions(self):
        world,_,book=fixture()
        bad=deepcopy(book);bad['id']='different';bad['read_text']='Conflicting text.'
        self.assertIn('conflicting texts',str(publications.validate({'item':[book,bad]})))
        cyclic=deepcopy(book);cyclic['publication']['derives_from']=[{'edition_id':'survey-1','relation':'copy'}]
        self.assertIn('cycle',str(publications.validate({'item':[cyclic]})))
        malformed=deepcopy(book);malformed['publication']['claims'][0]['revises']=[{'edition_id':'survey-1'}]
        self.assertIn('claim ID',str(publications.validate({'item':[malformed]})))
        malformed['publication']['derives_from']=7
        self.assertTrue(publications.validate({'item':[malformed]}))

    def test_no_clock_only_copy_creation_and_no_read_history_for_remote_projection(self):
        world,actor,_=fixture();before=deepcopy((world.items,world.rooms['library'].items,actor.progress))
        world.living_state['minute']+=10_000_000
        publications.source(world,'book');publications.view(world,'book')
        self.assertEqual((world.items,world.rooms['library'].items,actor.progress),before)
        self.assertNotIn(publications.KEY,world.living_state)


if __name__=='__main__':unittest.main()
