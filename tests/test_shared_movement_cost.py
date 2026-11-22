"""Regressions for building patrols and data-derived public sprite details."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import commands, npc_attention, visual_mapping


class SharedMovementTests(unittest.TestCase):
    def test_only_patrol_candidates_and_active_timers_need_pause_checks(self):
        def resident(name):
            return SimpleNamespace(id=name, source_def=name, progress={}, alive=True, is_player=False, location='a')
        actors = {name: resident(name) for name in ('worker', 'guard', 'reader', 'trader', 'idler')}
        world = SimpleNamespace(entities=actors, npcs={
            'guard': {'guard_building':'keep', 'patrol_mode':'random', 'patrol_chance':1},
            'worker': {'workplace_building':'keep', 'patrol_mode':'random', 'patrol_chance':1},
        }, buildings={'keep':{'rooms':['a', 'b']}}, rooms={'a':SimpleNamespace(exits={'east':'b'},id='a')},
            trade_attention={'trader':{'stale':None}}, npc_attention_until={'reader':0})
        from unittest.mock import Mock
        world.move_entity = Mock()
        with patch.object(npc_attention, 'paused', side_effect=lambda w, actor: actor.id == 'guard') as paused, \
                patch.object(commands.frontiers, 'blocked', return_value=''):
            commands._advance_guards(world)
        self.assertEqual({'guard','worker','reader','trader'}, {args[1].id for args, _ in paused.call_args_list})
        world.move_entity.assert_called_once_with('worker', 'b')

    def test_outfit_retains_configuration_priority_and_changes_with_equipment(self):
        world = SimpleNamespace(items={'jacket':{'type':'armor','name':'blue armor','description':'steel shield'}})
        definition = {'appearance':{'clothing_color':'red'}, 'description':'wears a green coat and carries a staff'}
        actor = SimpleNamespace(id='test', is_player=False, progress={}, description='', equipped={'armor':'jacket'})
        read = lambda: visual_mapping.appearance_for(world, actor, definition, '', '', {}, False)
        first = read()
        self.assertEqual('armor', first['clothing'])
        self.assertEqual('configuration', first['sources']['clothing_color'])
        self.assertIn('shield', first['accessories'])
        actor.equipped.clear()
        second = read()
        self.assertEqual('coat', second['clothing'])
        self.assertNotIn('shield', second['accessories'])
        definition['description'] = 'wears a tunic; never wears armor'
        self.assertEqual('tunic', read()['clothing'])
