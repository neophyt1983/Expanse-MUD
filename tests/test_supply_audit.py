"""The Creator audit reports actual chains without creating or revealing stock."""
from copy import deepcopy
import unittest

from tools.audit_supply_chains import audit


def fixture():
    names=('pick','ore','bar','cycle_a','cycle_b','ghost','unplaced_yield','missing_book','milk','cheese','reward')
    items=[{'id':ident,'name':ident.title(),'location':'square'} for ident in names]
    items[names.index('missing_book')].update(read_text='An unplaced source.',knowledge={'recipes':['copy_book']})
    rooms=[{'id':'square','name':'Square','items':['pick'],'exits':{},'facilities':['forge'],
            'resources':['mine','dairy'],'workshop':{'recipes':['bar','a_from_b','b_from_a','copy_book','cheese'],
                                                  'initial_stock':{'ore':1}},
            'clinical_services':{'enabled':True,'container':'cabinet','supplies':{'bar':2}},
            'locks':[{'id':'cabinet','contents':['bar']}],
            'employment':[{'id':'smelter','recipe':'bar'}]}]
    recipes=[
        {'id':'bar','name':'Smelt Bar','ingredients':{'ore':2},'outputs':{'bar':1},'station':'forge'},
        {'id':'a_from_b','ingredients':{'cycle_b':1},'outputs':{'cycle_a':1}},
        {'id':'b_from_a','ingredients':{'cycle_a':1},'outputs':{'cycle_b':1}},
        {'id':'copy_book','ingredients':{'bar':1},'outputs':{'missing_book':1},'requires_reading':['missing_book']},
        {'id':'cheese','ingredients':{'milk':2},'outputs':{'cheese':1}},
        {'id':'art','ingredients':{'ghost':2},'outputs':{},'artwork':{'kind':'sculpture'},'location':'square'},
    ]
    resources=[{'id':'mine','yields':{'ore':1},'tool':'pick'},
               {'id':'dairy','yields':{'milk':1},'requires_species':{'cow':1}},
               {'id':'unplaced','yields':{'unplaced_yield':1},'location':'square'}]
    return {'items':items,'rooms':rooms,'recipes':recipes,'resources':resources,
            'quests':[{'id':'quest','reward_items':['reward']}],'npcs':[]}, {'start_room':'square'}


class SupplyAuditTests(unittest.TestCase):
    def test_actual_sources_and_material_chains_are_distinct_from_catalog_locations(self):
        data,meta=fixture();before=deepcopy((data,meta));report=audit(data,meta)
        self.assertEqual((data,meta),before)
        rows={row['id']:row for row in report['items']}
        self.assertEqual(rows['pick']['status'],'finite_initial')
        self.assertEqual(rows['pick']['initial_units'],1)
        self.assertEqual(rows['ore']['status'],'renewable')
        self.assertEqual(rows['bar']['status'],'renewable')
        self.assertEqual(rows['ghost']['status'],'unavailable')
        self.assertEqual(rows['unplaced_yield']['status'],'unavailable')
        self.assertEqual(rows['milk']['status'],'gated')
        self.assertEqual(rows['cheese']['status'],'gated','A live-animal dependency is not falsely reported as absent.')
        self.assertEqual(rows['reward']['status'],'gated','A future quest reward is not initial stock.')

    def test_bootstrap_cycles_include_unread_copy_sources(self):
        data,meta=fixture();report=audit(data,meta);rows={row['id']:row for row in report['items']}
        self.assertEqual(rows['cycle_a']['status'],'bootstrap_cycle')
        self.assertIn(['cycle_a','cycle_b'],report['bootstrap_cycles'])
        self.assertEqual(rows['missing_book']['status'],'bootstrap_cycle')
        self.assertIn(['missing_book'],report['bootstrap_cycles'])

    def test_service_report_separates_reachable_supply_from_stock_available_now(self):
        data,meta=fixture();report=audit(data,meta);tasks={row['kind']:row for row in report['tasks']}
        self.assertTrue(tasks['clinic']['material_chain_ready'])
        self.assertFalse(tasks['clinic']['initial_batch_supplied'])
        self.assertEqual(tasks['clinic']['initial_shortfall'],{'bar':1})
        self.assertTrue(tasks['employment']['material_chain_ready'])
        self.assertFalse(tasks['employment']['initial_batch_supplied'])
        self.assertEqual(tasks['employment']['initial_shortfall'],{'ore':1})
        self.assertEqual(tasks['artwork']['unavailable'],['ghost'])

    def test_unplaced_npc_and_finite_reserves_do_not_become_infinite_sources(self):
        data,meta=fixture()
        data['npcs']=[{'id':'unplaced','inventory':['ghost'],'stock':[{'item':'ghost','qty':9}]}]
        data['resources'][0]['reserve_batches']=3
        report=audit(data,meta);rows={row['id']:row for row in report['items']}
        self.assertEqual(rows['ghost']['status'],'unavailable')
        self.assertEqual(rows['ore']['status'],'finite_initial')
        self.assertEqual(rows['bar']['status'],'finite_initial')
        self.assertNotEqual(rows['bar']['status'],'renewable')

    def test_an_explicit_landmark_search_is_conditional_not_phantom_floor_stock(self):
        data,meta=fixture();data['rooms'][0]['search_reward']='ghost'
        report=audit(data,meta);row=next(row for row in report['items'] if row['id']=='ghost')
        self.assertEqual(row['status'],'gated')
        self.assertEqual(row['initial_units'],0)
        self.assertEqual(row['sources'][0]['kind'],'landmark_search')


if __name__=='__main__':unittest.main()
