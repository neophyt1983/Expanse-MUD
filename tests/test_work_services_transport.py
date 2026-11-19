"""Real work/care commands through authenticated GameServer requests."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import loader, persistence
from server import game_server, work_services_ui
from test_artworks import fixture as art_fixture, learn
from test_clinical_services import fixture as care_fixture
from test_employment import fixture as job_fixture
from test_guild_transport import GuildSocket


def request(world, actor, service, action, number=1, **changes):
    offers=[offer for card in work_services_ui.projection(world,actor)['cards']
            for row in card['entries'] for offer in row['actions']
            if offer['service']==service and offer['action']==action]
    offer=next((row for row in offers if row['enabled']),offers[0])
    packet=dict(command='work action',work_ui=True,service=service,action=action,
                sequence=number,request_id='work-'+str(number),actor_id=actor.id,
                room=actor.location,offer_id=offer['id'],revision=offer['revision'])
    packet.update(changes);return packet


class WorkSocket(GuildSocket):
    async def __aiter__(self):
        for source in self.commands:
            packet=source(self.server.world,self.player) if callable(source) else source
            before=self.state();start=len(self.packets)
            yield json.dumps(packet)
            self.observations.append(dict(request=packet,before=before,after=self.state(),replies=self.packets[start:]))


class WorkServices(unittest.IsolatedAsyncioTestCase):
    async def session(self, factory, packets, *, prepare=None, race=None, resume=True):
        with tempfile.TemporaryDirectory(prefix='expanse-work-transport-') as temporary:
            directory=Path(temporary);world,actor,*_=factory()
            world.rules=getattr(world,'rules',{})
            for rid,details in world.room_details.items():
                details.setdefault('id',rid);details.setdefault('name',world.rooms[rid].name)
            world.game_dir=directory/'games'/'fixture';world.game_dir.mkdir(parents=True)
            world.start_room=actor.location;world.metadata['start_room']=actor.location
            actor.progress['world_slug']='fixture'
            if prepare:prepare(world,actor)
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
                        if packet.get('work_ui'):race(world,actor)
                        return await original(ws,packet,cmd,pid)
                    server.society_command=intervening
                socket=WorkSocket(server,actor,([{'command':'resume '+actor.id}] if resume else [])+packets)
                server.host_sockets.add(socket)
                try:
                    await server.handle(socket);return socket
                finally:server.db.close();server.checkpoint_db.close()

    def reply(self, observation):
        rows=[row for row in observation['replies'] if row.get('work_action')]
        self.assertEqual(len(rows),1,observation['replies']);return rows[0]

    def test_projections_are_pure_and_invalid_scopes_cannot_select_work(self):
        for factory in (art_fixture,care_fixture,job_fixture):
            world,actor,*_=factory()
            before=deepcopy((world.living_state,actor.progress,actor.inventory,actor.gold))
            view=work_services_ui.projection(world,actor)
            self.assertTrue(view['cards'])
            self.assertEqual(before,(world.living_state,actor.progress,actor.inventory,actor.gold))
        world,actor,*_=care_fixture()
        for change in (dict(actor_id='doctor'),dict(room='street'),dict(reward_gold=100),
                       dict(revision=True),dict(service='art'),dict(offer_id=['invalid'])):
            with self.subTest(change=change),self.assertRaises(ValueError):
                packet=request(world,actor,'clinical','treatment');packet.update(change)
                work_services_ui.resolve(world,actor,packet)
        self.assertEqual(actor.gold,10)

    async def test_treatment_consumes_real_supplies_pays_once_and_stages(self):
        remembered={}
        def first(w,p):
            remembered.update(request(w,p,'clinical','treatment'));return remembered
        def prepare(w,p):
            # Other patients and quest escrow have their own simulation tests.
            w.metadata['community_requests']=False
            w.entities['resident'].progress['injury']=0
        socket=await self.session(care_fixture,[first,lambda w,p:remembered],
                                  prepare=prepare)
        cared,replay=socket.observations[1:]
        self.assertIn('Treatment completed',self.reply(cared)['text'])
        self.assertEqual(cared['after']['player']['gold'],6)
        self.assertEqual(cared['after']['people']['doctor']['gold'],14)
        self.assertEqual(cared['after']['living']['physical_locks']['clinic:cabinet']['contents'],['bandage','water'])
        self.assertEqual(cared['after']['saved']['gold'],6)
        self.assertIn('already handled',self.reply(replay)['text'])
        self.assertEqual(cared['after']['player'],replay['after']['player'])
        self.assertEqual(len([r for r in cared['replies'] if r.get('type')=='map']),1)

    async def test_work_needs_an_application_real_elapsed_time_and_actual_stock(self):
        socket=await self.session(job_fixture,[
            lambda w,p:request(w,p,'employment','apply'),
            lambda w,p:request(w,p,'employment','work',2),
            {'command':'wait 5'},
        ])
        applied,working,finished=socket.observations[1:]
        self.assertEqual(applied['after']['player']['gold'],5)
        self.assertEqual(working['after']['player']['gold'],5)
        shop=working['after']['living']['economy']['shops']['market']
        self.assertEqual((shop['gold'],shop['stock']['vegetable'],shop['stock']['stew']),(27,1,0))
        self.assertEqual(finished['after']['player']['gold'],8)
        self.assertEqual(finished['after']['living']['economy']['shops']['market']['stock']['stew'],1)
        self.assertEqual(finished['after']['saved']['gold'],8)

    async def test_changed_batch_wage_invalidates_work_quote_before_escrow(self):
        from engine import employment
        def race(w,p):
            if employment.view(w,p)['assignment']:
                w.room_details['market']['employment'][0]['wage']=1
        socket=await self.session(job_fixture,[lambda w,p:request(w,p,'employment','apply'),
            lambda w,p:request(w,p,'employment','work',2)],race=race)
        changed=socket.observations[-1]
        self.assertIn('offer changed',self.reply(changed)['text'])
        self.assertEqual(changed['after']['player']['gold'],5)
        self.assertFalse(changed['after']['living'].get('economy',{}).get('shops'))

    async def test_art_begin_uses_materials_and_finish_creates_one_unique_work(self):
        socket=await self.session(art_fixture,[
            lambda w,p:request(w,p,'art','begin'),{'command':'wait 5'},
            lambda w,p:request(w,p,'art','finish',2),
        ],prepare=learn)
        begun,waited,finished=socket.observations[1:]
        self.assertEqual(len(begun['after']['player']['inventory']),6)
        self.assertFalse(any(i.startswith('artwork_') for i in begun['after']['player']['inventory']))
        works=[i for i in finished['after']['player']['inventory'] if i.startswith('artwork_')]
        self.assertEqual(len(works),1)
        self.assertIn('Finished',self.reply(finished)['text'])

    async def test_changed_terms_and_after_await_supply_race_cannot_charge(self):
        def depleted(w,p):
            w.room_details['clinic']['locks'][0]['contents']=[]
        socket=await self.session(care_fixture,[lambda w,p:request(w,p,'clinical','treatment')],race=depleted)
        action=socket.observations[1]
        self.assertEqual(action['after']['player']['gold'],10)
        self.assertEqual(action['after']['people']['doctor']['gold'],10)
        self.assertIn('offer changed',self.reply(action)['text'])
        self.assertEqual(self.reply(action)['type'],'error')

    async def test_unauthenticated_request_is_rejected_with_correlation(self):
        socket=await self.session(care_fixture,[lambda w,p:request(w,p,'clinical','treatment')],resume=False)
        action=socket.observations[0]
        self.assertEqual(self.reply(action)['request_id'],'work-1')
        self.assertIn('player character',self.reply(action)['text'])
        self.assertEqual(action['before']['player'],action['after']['player'])


if __name__=='__main__':unittest.main()
