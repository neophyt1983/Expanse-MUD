import json,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from engine import civic_visits,commands,living,needs_market,relationships,social
from engine.core import Entity
from private_game import Game
world_path=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as tmp:
    g=Game(world_path,Path(tmp),'Social household QA')
    w=g.server.world
    court='gen_dawn_lane_1';far='gen_reed_lane_12'
    w.realtime=True
    living.state(w)['minute']=550
    items=[i for i,v in w.items.items() if v.get('need_effects',{}).get('hunger',0)>0]
    gift_item=next(i for i in items if w.items[i].get('need_consumable'))
    actor=Entity('viewer','Passing visitor',10,10,1,1,is_player=True,group_id=w.rooms[court].group)
    w.add_entity(actor,court)
    records=[r for r in civic_visits.residents(w,court) if r['id'] not in w.npcs][:24]
    for row in records:
        name=row['name']; uid=row['id']; eid='npc:'+uid
        result=commands.process_command(g.server.registry,w,actor,'knock '+str(row['door'])+' '+name)
        assert name in result,result
        n=w.entities[eid]
        result=commands.process_command(g.server.registry,w,actor,'talk '+name)
        assert relationships.bond(w,actor,n)['trust']>0,(result,name)
        needs_market.state(n)['hunger']=90
        actor.inventory.append(gift_item)
        result=social.gift(w,actor,n,gift_item)
        assert 'accepts' in result and gift_item not in actor.inventory,result
    eids={'npc:'+r['id'] for r in records}
    w.move_entity(actor.id,far,forced=True)
    civic_visits.retire_distant(w)
    assert eids<=w.entities.keys(),'An ongoing conversation was interrupted'
    # A real conversation has both a real-time display lease and an attention lease.
    # Advance the two clocks independently, without sleeping in the regression.
    with patch('time.monotonic',return_value=time.monotonic()+20):
        living.state(w)['minute']+=15
        civic_visits.retire_distant(w)
    parked={eid for eid in eids if eid not in w.entities}
    print('talked, gifted, parked',len(eids),len(parked),flush=True)
    if parked!=eids:
        uid=next(iter(eids-parked));a=w.entities[uid]
        print('pinned',uid,'ref',a.source_def in civic_visits._referenced(w),'idle',civic_visits._idle(w,a,next(r for r in records if r['id']==a.source_def)),'progress',list(a.progress),'attributes',list(set(vars(a))-a.__dataclass_fields__.keys()),flush=True)
        raise AssertionError('Completed everyday conversations pinned residents')
    g.server._save_players_and_world();g.server.db.close();g.server.checkpoint_db.close()
    g=Game(world_path,Path(tmp),'Social household QA');w=g.server.world
    assert all(eid not in w.entities for eid in eids)
    civic_visits.enter_court(w,court)
    for eid in eids:
        n=w.entities[eid];bond=relationships.bond(w,actor,n)
        assert bond['trust']==7 and bond['social_actions'][actor.id]=={'happy':1,'gift_wanted':1},bond
        life=n.progress['npc_life'];assert {m['kind'] for m in life['memories']}=={'happy','gift_wanted'}
    print('PASS 24 accepted gifts and 24 conversations: active while interacting, dormant after both leases elapsed; trust, counters and memories persisted across cold restart')
