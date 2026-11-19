"""Shared rest uses the real GameServer clock, recovery and living simulation."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import living, loader, persistence, resting
from engine.core import Entity
from server import game_server
from tests.test_player_list_transport import fixture


@contextmanager
def session(mode='host'):
    with tempfile.TemporaryDirectory(prefix='expanse-rest-') as temporary, ExitStack() as stack:
        directory=Path(temporary);world,player=fixture(directory)
        world.room_details['inn']['facilities']=['inn']
        world.living_state={'minute':480}
        player.hp=10
        stack.enter_context(patch.object(game_server,'build_world',return_value=world))
        stack.enter_context(patch.object(game_server,'SAVE_DIR',directory/'save'))
        stack.enter_context(patch.object(game_server,'WORLD_STATE_PATH',directory/'world.json'))
        stack.enter_context(patch.object(loader,'GAMES_DIR',directory/'games'))
        stack.enter_context(patch.object(persistence,'DB_PATH',directory/'world.db'))
        server=game_server.GameServer(mode=mode)
        server.clients[object()]=player.id
        world.online_player_ids=frozenset(server.clients.values())
        try:yield server,world,player
        finally:server.db.close();server.checkpoint_db.close()


def other_player(server, ident='other', *, connected=True):
    player=Entity(ident,ident.title(),10,30,2,1,is_player=True)
    server.world.add_entity(player,'inn')
    if connected:server.clients[object()]=ident
    server.world.online_player_ids=frozenset(server.clients.values())
    return player


def start(world, player, duration=120, kind='sleep'):
    result=resting.command(world,player,str(duration),kind)
    if not resting.active(player):raise AssertionError(result)
    return result


def fast_tick(server):
    # A deterministic cheap-world budget keeps the number of permitted quanta
    # independent of the test runner's CPU. The real world runs every quantum.
    with patch.object(game_server,'monotonic',return_value=0):
        return server.advance_rest_tick()


class RestAccelerationTests(unittest.TestCase):
    def test_lone_host_and_solo_player_get_six_real_quanta_and_proportional_recovery(self):
        for mode in ('host','single'):
            with self.subTest(mode=mode),session(mode) as (server,world,player):
                self.assertIn('moving quickly',start(world,player))
                real_advance=living.advance;steps=[]
                def observe(w,minutes):
                    steps.append(minutes)
                    self.assertTrue(w.tick_authorized)
                    return real_advance(w,minutes)
                with patch.object(living,'advance',side_effect=observe):
                    self.assertTrue(fast_tick(server))
                self.assertEqual(steps,[5]*6)
                self.assertEqual(living.state(world)['minute'],510)
                self.assertEqual(resting.active(player)['elapsed'],30)
                self.assertEqual(player.hp,20)
                self.assertFalse(world.tick_authorized)

    def test_awake_participant_blocks_fast_time_without_blocking_normal_recovery(self):
        with session() as (server,world,player):
            other=other_player(server)
            self.assertIn('normal shared pace',start(world,player))
            self.assertFalse(fast_tick(server))
            self.assertEqual(living.state(world)['minute'],480)
            world.tick_authorized=True
            try:living.advance(world,1)
            finally:world.tick_authorized=False
            self.assertEqual(resting.active(player)['elapsed'],1)
            start(world,other)
            self.assertTrue(fast_tick(server))
            self.assertEqual(resting.active(player)['elapsed'],31)
            self.assertEqual(resting.active(other)['elapsed'],30)
            self.assertTrue(any(pid==player.id and 'moving quickly' in text for pid,text in world.rest_notifications))
            self.assertFalse(any('cannot continue resting safely' in text for _,text in world.rest_notifications))

    def test_first_completion_stops_everyone_at_exact_same_shared_minute(self):
        with session() as (server,world,player):
            other=other_player(server)
            start(world,player,7);start(world,other)
            self.assertTrue(fast_tick(server))
            self.assertEqual(living.state(world)['minute'],487)
            self.assertIsNone(resting.active(player))
            self.assertEqual(resting.active(other)['elapsed'],7)
            self.assertIn('normal shared pace',resting.status(world,other))
            self.assertFalse(fast_tick(server))
            self.assertEqual(living.state(world)['minute'],487)

    def test_short_rest_finishes_without_a_five_minute_overshoot(self):
        with session() as (server,world,player):
            start(world,player,3);fast_tick(server)
            self.assertEqual(living.state(world)['minute'],483)
            self.assertEqual(player.progress[resting.KEY]['elapsed'],3)
            self.assertEqual(player.progress[resting.KEY]['state'],'complete')

    def test_join_between_quanta_stops_further_shared_advancement(self):
        with session() as (server,world,player):
            start(world,player);real_advance=living.advance
            def joining(w,minutes):
                real_advance(w,minutes)
                other_player(server,'arrival')
            with patch.object(living,'advance',side_effect=joining):fast_tick(server)
            self.assertEqual(living.state(world)['minute'],485)
            self.assertEqual(resting.active(player)['elapsed'],5)
            self.assertIn('normal shared pace',resting.status(world,player))

    def test_real_wake_command_between_quanta_stops_further_advancement(self):
        from engine.commands import process_command
        with session() as (server,world,player):
            start(world,player);real_advance=living.advance
            def waking(w,minutes):
                real_advance(w,minutes)
                process_command(server.registry,w,player,'wake self')
            with patch.object(living,'advance',side_effect=waking):fast_tick(server)
            self.assertEqual(living.state(world)['minute'],485)
            self.assertIsNone(resting.active(player))
            self.assertEqual(player.activity,'awake')

    def test_real_damage_during_a_quantum_interrupts_before_any_recovery(self):
        from engine import regional_weather
        with session() as (server,world,player):
            start(world,player);real_weather=regional_weather.actor_step
            def damage(w,actor,minutes):
                result=real_weather(w,actor,minutes)
                if actor is player:actor.take_damage(2,defense=0,cause='falling debris')
                return result
            with patch.object(regional_weather,'actor_step',side_effect=damage):fast_tick(server)
            self.assertEqual(living.state(world)['minute'],485)
            self.assertEqual(player.hp,8)
            self.assertIsNone(resting.active(player))
            self.assertIn('hurt',player.progress[resting.KEY]['message'])

    def test_new_hostile_presence_is_checked_before_the_next_quantum(self):
        with session() as (server,world,player):
            start(world,player);real_advance=living.advance
            def danger(w,minutes):
                real_advance(w,minutes)
                w.npcs['threat']={'id':'threat','disposition':'hostile'}
                w.add_entity(Entity('threat-1','Threat',20,20,1,1,source_def='threat'),'inn')
            with patch.object(living,'advance',side_effect=danger):fast_tick(server)
            self.assertEqual(living.state(world)['minute'],485)
            self.assertIsNone(resting.active(player))
            self.assertIn('hostile',player.progress[resting.KEY]['message'])

    def test_disconnected_active_token_gets_no_offline_recovery(self):
        with session() as (server,world,player):
            offline=other_player(server);start(world,player);start(world,offline)
            server.clients={socket:pid for socket,pid in server.clients.items() if pid!=offline.id}
            fast_tick(server)
            self.assertEqual(resting.active(player)['elapsed'],30)
            self.assertEqual(offline.hp,10)
            self.assertIsNone(resting.active(offline))
            self.assertIn('offline time does not count',offline.progress[resting.KEY]['message'])

    def test_invalid_saved_token_or_clock_rewind_cannot_begin_fast_time(self):
        for invalid in ('saved','rewind'):
            with self.subTest(invalid=invalid),session() as (server,world,player):
                start(world,player)
                if invalid=='saved':player._rest_token=None
                else:living.state(world)['minute']-=10
                before=living.state(world)['minute']
                self.assertFalse(fast_tick(server))
                self.assertEqual(living.state(world)['minute'],before)
                self.assertEqual(player.hp,10)
                self.assertIsNone(resting.active(player))

    def test_cpu_budget_yields_after_one_quantum_without_granting_unrun_time(self):
        with session() as (server,world,player):
            start(world,player)
            with patch.object(game_server,'monotonic',side_effect=[0,.03]):
                self.assertTrue(server.advance_rest_tick())
            self.assertEqual(living.state(world)['minute'],485)
            self.assertEqual(resting.active(player)['elapsed'],5)
            self.assertFalse(world.tick_authorized)

    def test_normal_living_npc_schedule_and_subsystems_run_each_small_quantum(self):
        from engine import regional_weather,needs_market,wildlife
        with session() as (server,world,player):
            world.npcs['patroller']={'id':'patroller','patrol_route':['inn','square'],'social_profile':{'sentient':True}}
            npc=Entity('patroller-1','Patroller',30,30,1,1,source_def='patroller')
            world.add_entity(npc,'inn');start(world,player)
            with patch.object(world,'move_entity',wraps=world.move_entity) as moves, \
                 patch.object(regional_weather,'advance',wraps=regional_weather.advance) as weather, \
                 patch.object(needs_market,'advance',wraps=needs_market.advance) as needs, \
                 patch.object(wildlife,'advance',wraps=wildlife.advance) as animals:
                fast_tick(server)
            self.assertEqual([c.args[1] for c in moves.call_args_list if c.args[0]==npc.id],['square','inn']*3)
            self.assertEqual([c.args[1] for c in weather.call_args_list],[5]*6)
            self.assertEqual([c.args[1] for c in needs.call_args_list],[5]*6)
            self.assertEqual(animals.call_count,6)

    def test_closing_and_empty_host_never_accelerate(self):
        for kind in ('closing','empty'):
            with self.subTest(kind=kind),session() as (server,world,player):
                start(world,player)
                if kind=='closing':server.closing=True
                else:server.clients.clear()
                self.assertFalse(fast_tick(server))
                self.assertEqual(living.state(world)['minute'],480)


if __name__=='__main__':unittest.main()
