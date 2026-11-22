"""Starter entry and workshop book controls. No live game state."""
from types import SimpleNamespace as Obj
from unittest.mock import patch
import unittest
from engine import earned_start as pilot


class EarnedStartTests(unittest.TestCase):
    def new(self):
        return Obj(id='a',is_player=True,group_id='good_guys',progress={},location=pilot.KITCHEN,gold=0,alive=True)

    def test_only_new_scoped_characters_are_marked_by_creation_hook(self):
        a=self.new(); old=self.new(); old.gold=25; stranger=self.new();stranger.group_id='roadkeepers'
        with patch.object(pilot,'_installed',return_value=False):
            self.assertFalse(pilot.enroll_creation(None,a))
        with patch.object(pilot,'_installed',return_value=True):
            self.assertFalse(pilot.enroll_creation(None,stranger))
            self.assertTrue(pilot.enroll_creation(None,a))
        self.assertTrue(pilot.retired(a,pilot.GUIDE))
        self.assertTrue(pilot.retired(a,pilot.SKIP))
        self.assertFalse(pilot.retired(old,pilot.GUIDE))
        self.assertEqual(25,old.gold)
        self.assertEqual(0,a.gold)
        after=dict(id='first_steps_good_guys_3',reward_gold=12)
        self.assertEqual(0,pilot.gold_reward(a,after))
        self.assertEqual(12,pilot.gold_reward(old,after))
        self.assertEqual([pilot.CHAIN],pilot.omit_stage(a,pilot.CHAIN,[pilot.GUIDE,pilot.CHAIN]))
        self.assertEqual([pilot.GUIDE,pilot.CHAIN],pilot.omit_stage(old,pilot.CHAIN,[pilot.GUIDE,pilot.CHAIN]))

    def test_unopened_business_does_not_instantiate_gold_or_stock(self):
        w=Obj(room_details={},living_state={},recipes={})
        with self.assertRaisesRegex(ValueError,'not opened'):
            pilot._business(w)
        self.assertEqual({},w.living_state)

    def test_existing_stock_or_other_reservations_preclude_unnecessary_job(self):
        p=self.new(); cfg={'stock_limit':40}; stock={**pilot.INPUTS,pilot.RECIPE:pilot.SERVICE_TARGET-1}
        pocket={'stock':stock,'gold':8}
        with patch.object(pilot,'_installed',return_value=True),patch.object(pilot,'_chef',return_value=object()),patch.object(pilot,'_business',return_value=(cfg,pocket,{})):
            self.assertEqual(pocket,pilot._offer(None,p,{})[1])
            with self.assertRaisesRegex(ValueError,'enough cooks assigned'):
                pilot._offer(None,p,{'other':{'phase':'reserved','ready_at':0}})
            pocket['gold']=pilot.WAGE-1
            with self.assertRaisesRegex(ValueError,'not hiring on credit'):
                pilot._offer(None,p,{})
            pocket['gold']=8
            stock[pilot.RECIPE]+=1
            with self.assertRaisesRegex(ValueError,'enough stew'):
                pilot._offer(None,p,{})

    def test_invalid_job_book_never_resets_existing_estate(self):
        value={'a':{'phase':'prepared','ready_at':False}}
        w=Obj(living_state={pilot.BOOK:value})
        with self.assertRaisesRegex(ValueError,'records need review'):
            pilot._read(w)
        self.assertIs(value,w.living_state[pilot.BOOK])
