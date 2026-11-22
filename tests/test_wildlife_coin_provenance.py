from types import SimpleNamespace
import unittest

from engine import loot_tables, wildlife_coin_provenance as origin
from engine.core import Entity


def world(flag='v1'):
    return SimpleNamespace(
        metadata={origin.FLAG:flag}, species={
            'wolf': {'sentient':False, 'category':'mammal'},
            'oak': {'sentient':False, 'category':'plant'},
            'fox-person': {'sentient':True, 'category':'mammal'},
        }, npcs={})


def row(species='wolf', sentient=False, **extra):
    return dict(social_profile=dict(species=species,sentient=sentient),gold=7,**extra)


class WildlifeCoinProvenance(unittest.TestCase):
    def test_only_founding_cities_gets_the_default_and_explicit_choice_wins(self):
        metadata = {'civic_opening_release': '1.10.0-rc1',
                    'municipal_genesis': {'version': 1, 'seed': 20261122}}
        self.assertTrue(origin.enabled(metadata))
        self.assertFalse(origin.enabled(dict(metadata, wildlife_coin_provenance='off')))
        self.assertFalse(origin.enabled(dict(metadata, municipal_genesis={'version': 1, 'seed': 9})))
        self.assertFalse(origin.enabled(dict(metadata, civic_opening_release='other')))
        self.assertFalse(origin.enabled({'civic_opening_release': '1.10.0-rc1'}))

    def test_guard_is_explicit_and_requires_evidence(self):
        cases=[
            (row(),0),
            (row('unknown'),7),
            (row('unknown',creature_kind='creature'),0),
            (row('unknown',creature_kind='monster'),7),
            (row('expedition_wildlife',expedition_role='quarry'),0),
            (row('expedition_wildlife',expedition_role='predator'),0),
            (row('expedition_wildlife',expedition_role='traveller'),7),
            (row('wolf',True),7),
            (row('wolf',creature_kind='humanoid'),7),
            (row('fox-person'),7),
            (row('oak'),7),
            (row('oak',creature_kind='creature'),7),
            (row(species=None,sentient=None),7),
        ]
        for d,wanted in cases:
            with self.subTest(d=d):
                self.assertEqual(origin.initial_purse(world(),d),wanted)
                for off in [None,False,True,'v2']:
                    self.assertEqual(origin.initial_purse(world(off),d),7)
        d=row()
        d['social_profile']['undead']=True
        self.assertEqual(origin.initial_purse(world(),d),7)

    def test_items_and_rng_are_identical_with_only_coin_suppressed(self):
        d=row(loot_table=dict(version=1,tiers=[
            dict(min_level=1,max_level=100,chance=1,gold={'min':2,'max':9},
                 items=[dict(item='hide',weight=10,min=1,max=2)],
                 bonus=[dict(item='tail',chance=1,min=1,max=1)]),
        ]))
        actor=Entity('a','Grey wolf',0,20,1,0,gold=6,source_def='def')
        hits=iter((.75,.25,.75)); hits2=iter((.75,.25,.75))
        off,on=world(None),world()
        off.npcs['def']=on.npcs['def']=d
        a=loot_tables.roll(off,actor,rng=lambda:next(hits))
        b=loot_tables.roll(on,actor,rng=lambda:next(hits2))
        self.assertGreater(a['gold'],0)
        self.assertEqual(b,{**a,'gold':0})
        self.assertEqual(b['items'],['hide','hide','tail'])
        self.assertEqual(list(hits),list(hits2))
        self.assertEqual(actor.gold,6) # rolls cannot raid an actual purse
        actor.progress['social_profile']={'sentient':True}
        self.assertGreater(loot_tables.roll(on,actor,rng=lambda:.25)['gold'],0)
