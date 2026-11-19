"""Reviewed market content uses existing ownership, stock, cash and schedules."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from engine import employment,society
from engine.core import Entity,Room,World
from tools import stage_market_employment as staging


def catalogs():
    data={
        'rooms':[
            {'id':staging.MARKET,'name':'Produce Market','description':'An existing market.',
             'facilities':['kitchen','market'],'items':[],
             'workshop':{'name':'Provision Counter','recipes':[],'capital':240,
                         'initial_stock':{'lw_carrot':20,'lw_onion':20,'lw_potato':20,'lw_stew':8},'stock_limit':40},
             'locks':[{'id':'pantry','owner':staging.EMPLOYER,'contents':['lw_carrot']}]},
            {'id':staging.FISH,'name':'Fish Market','description':'An existing fish market.','items':[]}],
        'npcs':[
            {'id':staging.EMPLOYER,'name':'Aster','work_room':staging.MARKET,'spawn_room':staging.MARKET,'social_profile':{'sentient':True}},
            {'id':staging.WORKER,'name':'Eris','work_room':staging.MARKET,'social_profile':{'sentient':True},
             'schedule':[{'hour':7,'room':staging.MARKET,'activity':'working'}]},
            {'id':'fw_dawn_merchant_5','name':'Harper'}],
        'items':[{'id':iid,'name':iid} for iid in ('lw_carrot','lw_onion','lw_potato','lw_stew')],
        'recipes':[{'id':'lw_stew','name':'Vegetable Stew','kind':'cooking','station':'kitchen','minutes':5,
                    'ingredients':{'lw_carrot':1,'lw_onion':1,'lw_potato':1},'outputs':{'lw_stew':1}}],
    }
    return data,{'living_world':True,'society':False}


class MarketEmploymentStagingTests(unittest.TestCase):
    def test_posting_and_npc_plan_conserve_all_existing_supplies_money_and_people(self):
        data,metadata=catalogs();before=deepcopy(data);report=staging.apply(data,metadata)
        old=before['rooms'][0]['workshop'];new=data['rooms'][0]['workshop']
        self.assertEqual(new['initial_stock'],old['initial_stock'])
        self.assertEqual(new['capital'],old['capital'])
        self.assertEqual(len(data['rooms']),len(before['rooms']))
        self.assertEqual(len(data['npcs']),len(before['npcs']))
        self.assertEqual(report['stock_added'],{})
        self.assertEqual(report['gold_added'],0)
        self.assertEqual(data['rooms'][0]['employment'][0]['slots'],2)
        self.assertEqual(data['npcs'][1]['employment_plan']['room'],staging.MARKET)
        self.assertEqual(len(data['items']),len(before['items'])+2)
        self.assertEqual(employment.validate({k:data[p] for k,p in [('room','rooms'),('npc','npcs'),('recipe','recipes'),('item','items')]}),[])

    def test_reapplying_never_duplicates_notices_refills_stock_or_pays_workers(self):
        data,metadata=catalogs();staging.apply(data,metadata)
        data['rooms'][0]['workshop']['initial_stock']['lw_stew']=3
        data['rooms'][0]['workshop']['capital']=12
        before=deepcopy((data,metadata))
        self.assertTrue(staging.apply(data,metadata)['already_applied'])
        self.assertEqual((data,metadata),before)

    def test_changed_ownership_schedule_recipe_or_funding_is_rejected_before_mutation(self):
        for reason in ('owner','schedule','recipe','money','stock','demand','identity'):
            with self.subTest(reason=reason):
                data,metadata=catalogs()
                if reason=='owner':data['rooms'][0]['locks'][0]['owner']='unrelated'
                elif reason=='schedule':data['npcs'][1]['schedule']=[]
                elif reason=='recipe':data['recipes'][0]['ingredients']['lw_potato']=2
                elif reason=='money':data['rooms'][0]['workshop']['capital']=0
                elif reason=='stock':data['rooms'][0]['workshop']['initial_stock']['lw_onion']=0
                elif reason=='demand':data['rooms'][0]['workshop']['initial_stock']['lw_stew']=12
                else:data['items'].append({'id':staging.NOTICES[0]})
                before=deepcopy((data,metadata))
                with self.assertRaises(ValueError):staging.apply(data,metadata)
                self.assertEqual((data,metadata),before)

    def test_staged_player_and_actual_npc_both_do_real_work_from_same_treasury(self):
        data,metadata=catalogs();staging.apply(data,metadata)
        world=World();world.metadata=metadata;world.rules={};world.living_state={'minute':480}
        world.room_details={r['id']:r for r in data['rooms']}
        world.items={r['id']:r for r in data['items']};world.npcs={r['id']:r for r in data['npcs']}
        world.recipes={r['id']:r for r in data['recipes']}
        for r in data['rooms']:world.add_room(Room(r['id'],r['name'],r['description'],{}))
        boss=Entity('boss','Aster',30,30,1,1,source_def=staging.EMPLOYER)
        npc=Entity('worker','Eris',30,30,1,1,source_def=staging.WORKER,gold=5)
        player=Entity('player','Player',30,30,1,1,is_player=True,gold=5)
        for actor in (boss,npc,player):world.add_entity(actor,staging.MARKET)
        world.online_player_ids={player.id}
        self.assertTrue(employment.step(world,npc))
        employment.apply(world,player,staging.VACANCY);employment.work(world,player)
        shop=society.shop(world,staging.MARKET)[1]
        self.assertEqual(shop['gold'],234)
        self.assertEqual([shop['stock'][iid] for iid in ('lw_carrot','lw_onion','lw_potato')],[18,18,18])
        world.living_state['minute']+=5;employment.advance(world,5)
        self.assertEqual((player.gold,npc.gold,shop['stock']['lw_stew']),(8,8,10))
        self.assertEqual(player.inventory,[])
        self.assertEqual(npc.inventory,[])
        self.assertEqual(player.progress['actions']['craft:lw_stew'],1)
        self.assertEqual(npc.progress['actions']['craft:lw_stew'],1)

    def test_cli_stages_separately_and_never_modifies_input_files(self):
        data,metadata=catalogs()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.mkdir()
            for name,rows in {**data,'metadata':metadata}.items():(source/(name+'.json')).write_text(json.dumps(rows),encoding='utf-8')
            before={path.name:path.read_bytes() for path in source.iterdir()}
            with self.assertRaises(ValueError):staging.stage(source,source)
            with self.assertRaises(ValueError):staging.stage(source,source/'nested')
            target=Path(directory)/'staged';staging.stage(source,target)
            self.assertEqual({path.name:path.read_bytes() for path in source.iterdir()},before)
            self.assertTrue((target/'market-employment-staging-report.json').is_file())
            self.assertEqual(json.loads((target/'rooms.json').read_text())[0]['employment'][0]['wage'],3)


if __name__=='__main__':unittest.main()
