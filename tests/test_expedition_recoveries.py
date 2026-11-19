"""A physical landmark yields one relic across actors, transfers and saves."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from engine import living, loader, persistence, wildlands
from engine.commands import CommandContext, _cmd_drop, _cmd_take
from engine.core import Entity, Room, World
from server import game_server
from server.game_server import GameServer


def fixture(*, living_world=True, second=False):
    w=World();w.metadata={'living_world':living_world};w.living_state={'minute':480}
    w.rules={};w.game_dir=Path('/test/current');w.room_details={};w.start_room='gate'
    w.items={'relic':{'id':'relic','name':'The recovered bell','type':'quest'}}
    w.quests={'return_bell':{'id':'return_bell','required_items':{'relic':1}}}
    w.field_regions=[];w.field_prefixes={};w.field_chunks=set();w._field_sectors=set()
    w._field_travellers=set();w.expedition_country=True
    for rid in ('gate','field_1_0')+ (('other_1_0',) if second else ()):
        w.add_room(Room(rid,rid,'',items=[]))
        w.room_details[rid]={'id':rid,'items':[]}
    for prefix in ('field','other') if second else ('field',):
        w.field_prefixes[prefix]=len(w.field_regions)
        w.field_regions.append(SimpleNamespace(prefix=prefix,width=2,height=1,landmark_x=1,
            trail_y=0,relic='The recovered bell',name='Test valley',gate='gate',hazards=['Wind.']))
        w.room_details[prefix+'_1_0']['search_reward']='relic'
    a=Entity('first','First',30,30,2,1,is_player=True,progress={'world_slug':'current'})
    b=Entity('second','Second',30,30,2,1,is_player=True,progress={'world_slug':'current'})
    w.add_entity(a,'field_1_0');w.add_entity(b,'field_1_0')
    return w,a,b


def search(w,a):
    return wildlands.command(CommandContext(w,a,w.rooms[a.location],raw='expedition search'),'search')


def copies(w):
    return sum(a.inventory.count('relic') for a in w.entities.values())+sum(r.items.count('relic') for r in w.rooms.values())


class ExpeditionRecoveryTests(unittest.TestCase):
    def test_drop_transfer_and_another_actor_never_refill_the_source(self):
        w,a,b=fixture()
        self.assertIn('You recover',search(w,a));self.assertEqual(copies(w),1)
        _cmd_drop(CommandContext(w,a,w.rooms[a.location]),'relic')
        self.assertIn('already yielded',search(w,a));self.assertEqual(copies(w),1)
        _cmd_take(CommandContext(w,b,w.rooms[b.location]),'relic')
        self.assertIn('already yielded',search(w,b));self.assertEqual(copies(w),1)
        self.assertEqual(a.progress['actions']['search:field_1_0'],1)
        self.assertEqual(a.progress['task_practice_v1']['observation']['attempts'],1)
        self.assertNotIn('task_practice_v1',b.progress)
        self.assertEqual(w.item_claims['field_1_0']['relic'],1)

    def test_real_world_snapshot_restore_keeps_exhaustion_after_the_copy_is_consumed(self):
        for enabled in (True,False):
            with self.subTest(living_world=enabled):
                w,a,b=fixture(living_world=enabled);search(w,a);a.inventory.remove('relic')
                saved=json.loads(json.dumps(living.snapshot(w)))
                replacement,new_actor,_=fixture(living_world=enabled)
                living.restore(replacement,saved)
                self.assertIn('already yielded',search(replacement,new_actor))
                self.assertEqual(copies(replacement),0)
                self.assertEqual(replacement.living_state[wildlands.RECOVERIES],w.living_state[wildlands.RECOVERIES])

    def test_legacy_physical_copy_claim_or_completed_turn_in_seeds_without_deleting_anything(self):
        for evidence in ('inventory','equipped','floor','container','workshop','merchant','reserve','claim','turn_in','quest_time'):
            with self.subTest(evidence=evidence):
                w,a,b=fixture()
                if evidence=='inventory':b.inventory.extend(['relic','relic'])  # Old duplicates are preserved.
                if evidence=='equipped':b.equipped['hand']='relic'
                if evidence=='floor':w.rooms['gate'].items.append('relic')
                if evidence=='container':w.living_state['physical_locks']={'gate:box':{'contents':['relic']}}
                if evidence=='workshop':w.living_state['economy']={'shops':{'gate':{'stock':{'relic':1}}}}
                if evidence=='merchant':w.shop_state={'merchant':{'relic':1}}
                if evidence=='reserve':w.living_state['companion_reserve']={'retired':{'inventory':['relic']}}
                if evidence=='claim':w.item_claims={'gate':{'relic':1}}
                if evidence=='turn_in':b.progress['quests']={'return_bell':'complete'}
                if evidence=='quest_time':b.progress.update(quests={'return_bell':'active'},quest_times={'return_bell':300})
                before=deepcopy((a.inventory,b.inventory,b.equipped,b.progress,w.item_claims,w.shop_state,
                                 {rid:r.items for rid,r in w.rooms.items()},w.living_state))
                wildlands.reconcile_recoveries(w)
                self.assertIn('already yielded',search(w,a))
                after=deepcopy(w.living_state);after.pop(wildlands.RECOVERIES)
                self.assertEqual(before,(a.inventory,b.inventory,b.equipped,b.progress,w.item_claims,w.shop_state,
                                         {rid:r.items for rid,r in w.rooms.items()},after))

    def test_a_visit_or_active_quest_is_not_recovery_and_distinct_sources_remain_distinct(self):
        w,a,b=fixture();a.explored_rooms=['field_1_0'];a.progress['quests']={'return_bell':'active'}
        self.assertIn('You recover',search(w,a))
        w,a,b=fixture(second=True)
        self.assertIn('You recover',search(w,a))
        a.location='other_1_0'
        self.assertIn('You recover',search(w,a))
        self.assertEqual(copies(w),2)
        a.location='field_1_0';self.assertIn('already yielded',search(w,a))

    def test_an_authored_ordinary_copy_is_not_guessed_to_have_come_from_the_landmark(self):
        w,a,b=fixture();w.room_details['gate']['items']=['relic'];b.inventory=['relic']
        wildlands.reconcile_recoveries(w)
        self.assertIn('You recover',search(w,a));self.assertEqual(copies(w),2)
        # An editor adding a second physical source after this save creates
        # that source only; it does not reset the existing recovery.
        w.field_prefixes['other']=1
        w.field_regions.append(SimpleNamespace(prefix='other',width=2,height=1,landmark_x=1,trail_y=0,
                                               relic='The recovered bell',name='Other valley',gate='gate',hazards=['Wind.']))
        w.add_room(Room('other_1_0','Other landmark',''))
        w.room_details['other_1_0']={'search_reward':'relic'}
        wildlands.reconcile_recoveries(w)
        self.assertIn('already yielded',search(w,a))
        a.location='other_1_0';self.assertIn('You recover',search(w,a))

    def test_real_harvest_and_canonical_loot_copies_leave_an_untouched_landmark_available(self):
        from engine import combat_rewards
        for source in ('harvest','common_loot','bonus_loot'):
            with self.subTest(source=source):
                w,a,b=fixture()
                if source=='harvest':
                    w.encounters={'orchard':{'id':'orchard','name':'Orchard','harvest':{'relic':1}}}
                    w.room_details[a.location]['encounters']=['orchard']
                    living.state(w)['encounters'][a.location+':orchard']={
                        'active':True,'cleared':False,'last_harvest':-1000,'members':[]}
                    result=living.command(CommandContext(w,a,w.rooms[a.location]),'orchard','harvest')
                    self.assertIn('Harvested without destroying',result)
                else:
                    w.npcs['looter']={'id':'looter','name':'Looter','combat_level':1,
                        'loot_table':{'version':1,'tiers':[{
                            'min_level':1,'max_level':100,'chance':1 if source=='common_loot' else 0,
                            'gold':{'min':1,'max':1},
                            'items':[{'item':'relic','min':1,'max':1,'weight':1}],
                            'bonus':[] if source=='common_loot' else [{'item':'relic','min':1,'max':1,'chance':1}]}]}}
                    dead=Entity('dead','Looter',0,10,1,0,source_def='looter')
                    w.add_entity(dead,a.location)
                    combat_rewards.settle(w,dead,a,rng=lambda:0)
                self.assertEqual(a.inventory.count('relic'),1)
                before=list(a.inventory)
                wildlands.reconcile_recoveries(w)
                self.assertEqual(a.inventory,before)
                self.assertIn('You recover',search(w,a))
                self.assertEqual(a.inventory.count('relic'),2)
                self.assertIn('already yielded',search(w,b))

    def test_offline_migration_reads_only_this_mode_and_world_then_stops_querying(self):
        with tempfile.TemporaryDirectory() as temporary:
            db=persistence.init_db(Path(temporary)/'world.db',memory=True)
            try:
                for ident,mode,slug,has_copy in [('ours','host','current',True),('other-world','host','elsewhere',True),
                                               ('other-mode','single','current',True)]:
                    actor=Entity(ident,ident,30,30,2,1,is_player=True,inventory=['relic'] if has_copy else [],
                                 progress={'world_slug':slug})
                    persistence.save_player(db,actor,mode)
                db.execute("UPDATE players SET inventory='not JSON' WHERE id='other-world'")
                for mode,slug,has_copy,exhausted in [('host','current',True,True),('host','current',False,False),
                                                   ('single','empty',False,False),('empty','current',False,False)]:
                    db.execute('UPDATE players SET inventory=? WHERE id=?',(json.dumps(['relic'] if has_copy else []),'ours'))
                    rows_before=db.execute('SELECT * FROM players ORDER BY id').fetchall()
                    w,a,b=fixture();w.game_dir=Path('/test')/slug
                    a.progress['world_slug']=slug;b.progress['world_slug']=slug
                    server=GameServer.__new__(GameServer);server.world=w;server.db=db;server.mode=mode
                    server._migrate_expedition_recoveries()
                    self.assertEqual('already yielded' in search(w,a),exhausted)
                    queries=[];db.set_trace_callback(queries.append)
                    server._migrate_expedition_recoveries();search(w,a)
                    db.set_trace_callback(None)
                    self.assertEqual(queries,[],'A completed migration/search must never scan offline saves again.')
                    self.assertEqual(rows_before,db.execute('SELECT * FROM players ORDER BY id').fetchall())
            finally:db.close()

    def test_replacing_a_source_does_not_mistake_its_existing_relic_for_the_new_one(self):
        w,a,b=fixture();search(w,a)
        region=w.field_regions[0];region.prefix='replacement'
        w.field_prefixes={'replacement':0}
        w.add_room(Room('replacement_1_0','New landmark',''))
        w.room_details['replacement_1_0']={'search_reward':'relic'}
        del w.room_details['field_1_0'];del w.rooms['field_1_0']
        a.location='replacement_1_0';b.location='replacement_1_0'
        self.assertIn('You recover',search(w,a))
        self.assertEqual(a.inventory.count('relic'),2)
        self.assertIsNotNone(w.living_state[wildlands.RECOVERIES]['sources']['field_1_0']['relic'])
        self.assertIn('already yielded',search(w,b))

    def test_real_server_startup_migrates_an_offline_holder_before_the_first_search(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory=Path(temporary);w,a,b=fixture()
            w.game_dir=directory/'games'/'current';w.game_dir.mkdir(parents=True)
            database=directory/'world.db'
            db=persistence.init_db(database)
            holder=Entity('offline','Offline',30,30,2,1,is_player=True,inventory=['relic'],
                          progress={'world_slug':'current'})
            persistence.save_player(db,holder,'host');db.close()
            for owner,key,value in ((game_server,'build_world',lambda:w),(game_server,'SAVE_DIR',directory/'save'),
                                    (game_server,'WORLD_STATE_PATH',directory/'state.json'),
                                    (loader,'GAMES_DIR',directory/'games'),(persistence,'DB_PATH',database)):
                stack.enter_context(patch.object(owner,key,value))
            server=GameServer(mode='host')
            try:
                self.assertNotIn('offline',server.world.entities)
                self.assertIn('already yielded',search(w,a))
                self.assertEqual(persistence.load_player(server.db,'offline','host').inventory,['relic'])
                self.assertFalse((directory/'state.json').exists(),'Migration waits for the existing explicit-save boundary.')
            finally:server.db.close();server.checkpoint_db.close()

    def test_invalid_saved_ledger_fails_without_resetting_or_issuing_a_copy(self):
        for ledger in (None,{'version':True,'sources':{}}, {'version':1,'sources':{'field_1_0':{'relic':False}}},
                       {'version':1,'sources':{'field_1_0':{'relic':{'evidence':'search','minute':-1}}}}):
            with self.subTest(ledger=ledger):
                w,a,b=fixture();w.living_state[wildlands.RECOVERIES]=deepcopy(ledger)
                before=deepcopy(w.living_state)
                with self.assertRaises(ValueError):search(w,a)
                self.assertEqual(w.living_state,before);self.assertEqual(copies(w),0)
                with self.assertRaises(ValueError):GameServer._validate_saved_world({'living':{'state':w.living_state}})


if __name__=='__main__':unittest.main()
