"""Authenticated guild requests commit real fees, shared stock and player saves."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import loader,persistence,locks
from engine.entity_snapshot import snapshot
from server import game_server
from test_guilds import fixture,enroll,quest_view
from test_player_list_transport import Socket


def request(number=1,action='join',**changes):
    packet=dict(command='guild action',guild_ui=True,action=action,sequence=number,
                request_id='guild-'+str(number),actor_id='player',room='hall',guild_id='farmers')
    packet.update(changes);return packet


class GuildSocket(Socket):
    def state(self):
        view=super().state()
        view['people']={p.id:snapshot(p) for p in self.server.world.entities.values()}
        saved=persistence.load_player(self.server.db,self.player.id,self.server.mode)
        view['saved']=snapshot(saved) if saved else None
        return deepcopy(view)


class GuildTransport(unittest.IsolatedAsyncioTestCase):
    async def session(self,packets,*,prepare=None,race=None,resume=True):
        with tempfile.TemporaryDirectory(prefix='expanse-guild-transport-') as temporary:
            directory=Path(temporary);world,actor,worker,steward=fixture()
            world.game_dir=directory/'games'/'fixture';world.game_dir.mkdir(parents=True)
            world.start_room='hall';world.metadata['start_room']='hall';actor.progress['world_slug']='fixture'
            if prepare:prepare(world,actor,steward)
            commands=packets(world,actor) if callable(packets) else packets
            with ExitStack() as stack:
                for owner,key,value in [(game_server,'build_world',lambda:world),
                                        (game_server,'SAVE_DIR',directory/'save'),
                                        (game_server,'WORLD_STATE_PATH',directory/'world.json'),
                                        (loader,'GAMES_DIR',directory/'games'),
                                        (persistence,'DB_PATH',directory/'world.db')]:
                    stack.enter_context(patch.object(owner,key,value))
                server=game_server.GameServer(mode='single')
                if race:
                    original=server.society_command
                    async def intervening(ws,packet,cmd,pid):
                        if packet.get('guild_ui'):race(world,actor,steward)
                        return await original(ws,packet,cmd,pid)
                    server.society_command=intervening
                socket=GuildSocket(server,actor,([{'command':'resume player'}] if resume else [])+commands)
                server.host_sockets.add(socket)
                try:
                    await server.handle(socket)
                    return socket
                finally:
                    server.db.close();server.checkpoint_db.close()

    def reply(self,observation):
        rows=[p for p in observation['replies'] if p.get('guild_action')]
        self.assertEqual(len(rows),1,observation['replies'])
        return rows[0]

    async def test_join_and_lesson_pay_actual_recipients_once_and_are_staged(self):
        lesson=request(2,'learn',offer_id='basics')
        socket=await self.session([request(),request(),lesson,lesson])
        joined,replayed,learned,again=socket.observations[1:]
        self.assertEqual(joined['after']['player']['gold'],18)
        self.assertEqual(joined['after']['living']['guild_treasuries_v1']['farmers'],2)
        self.assertIn('already handled',self.reply(replayed)['text'])
        self.assertEqual(learned['after']['player']['gold'],15)
        self.assertEqual(learned['after']['people']['steward']['gold'],23)
        self.assertEqual(learned['after']['player']['progress']['task_practice_v1'],
                         learned['after']['saved']['progress']['task_practice_v1'])
        self.assertEqual(learned['after']['player'],again['after']['player'])
        self.assertEqual(self.reply(learned)['request_id'],'guild-2')
        self.assertEqual(len([p for p in learned['replies'] if p['type']=='map']),1)

    async def test_unread_quest_forged_identity_and_extra_rewards_cannot_mutate(self):
        packets=[request(actor_id='worker'),request(2,room='field'),request(3,reward_gold=999),
                 request(4),request(5,'accept',offer_id='supply')]
        socket=await self.session(packets)
        for observation in socket.observations[1:4]:
            self.assertEqual(observation['before']['player'],observation['after']['player'])
            self.assertEqual(self.reply(observation)['type'],'error')
        last=socket.observations[-1]
        self.assertEqual(last['before']['player'],last['after']['player'])
        self.assertIn('Read or ask',self.reply(last)['text'])

    async def test_shared_need_revision_prevents_stale_second_handin(self):
        def prepare(w,p,n):
            enroll(w,p);p.inventory=['grain']*5
        def packets(w,p):
            revision=quest_view(w,p)['revision']
            return [request(1,'complete',offer_id='supply',revision=revision),
                    request(2,'complete',offer_id='supply',revision=revision)]
        socket=await self.session(packets,prepare=prepare)
        first,stale=socket.observations[1:]
        self.assertEqual(first['after']['player']['inventory'],['grain']*3)
        self.assertEqual(first['after']['people']['steward']['gold'],16)
        self.assertEqual(first['after']['living']['physical_locks']['hall:pantry']['contents'],['grain']*2)
        self.assertEqual(first['after']['player'],stale['after']['player'])
        self.assertIn('need changed',self.reply(stale)['text'])

    async def test_funding_is_rechecked_after_await_before_dispatch(self):
        socket=await self.session([request(1,'learn',offer_id='basics')],
                                  prepare=lambda w,p,n:enroll(w,p),
                                  race=lambda w,p,n:setattr(p,'gold',0))
        observation=socket.observations[1]
        self.assertEqual(observation['after']['people']['steward']['gold'],20)
        self.assertNotIn('farming',observation['after']['player']['progress'].get('task_practice_v1',{}))
        self.assertEqual(self.reply(observation)['type'],'error')

    async def test_request_without_authenticated_character_is_correlated_and_rejected(self):
        socket=await self.session([request()],resume=False)
        obs=socket.observations[0]
        self.assertEqual(obs['before']['player'],obs['after']['player'])
        self.assertEqual(self.reply(obs)['request_id'],'guild-1')
        self.assertIn('player character',self.reply(obs)['text'])


if __name__=='__main__':unittest.main()
