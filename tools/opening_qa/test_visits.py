import json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from private_game import Game
from engine import civic_visits,living
from engine.core import Entity

world=Path(sys.argv[1]).resolve()
seen=set()
for path in sorted((world/'assets/chronicles').glob('genesis-*.json')):
    data=json.loads(path.read_bytes()); rr=data['residents']
    assert len(rr)==3000 and rr[-1]['entry_day']==0
    previous=None
    for row in rr:
        assert row['id'] not in seen
        assert previous is None or row['entry_day']>previous
        seen.add(row['id']);previous=row['entry_day']
    for row in rr:
        assert all(x in seen for x in row.get('parents',[]))
assert len(seen)==24000
with TemporaryDirectory() as temp:
    g=Game(world,Path(temp),'Genesis test')
    w=g.server.world;court='gen_dawn_lane_1'
    def visit(server):
        player=SimpleNamespace(location=court)
        return civic_visits.knock(SimpleNamespace(world=server.world,player=player),'2')
    result=visit(g.server);ledger=living.state(w)['civic_visits_v1'];uid=ledger[court][0];eid='npc:'+uid
    assert w.entities[eid].name in result and visit(g.server)==result and len(ledger[court])==1
    w.entities[eid].gold=7
    g.server._save_players_and_world()
    g.server.checkpoint_db.close();g.server.db.close()
    g=Game(world,Path(temp),'Genesis test')
    w=g.server.world
    assert w.entities[eid].gold==7 and visit(g.server)==result
    w.killed_npcs.add(uid);w.rooms[court].entities.remove(eid);del w.entities[eid]
    name=w.npcs[uid]['name']
    assert 'no answer' in civic_visits.knock(SimpleNamespace(world=w,player=SimpleNamespace(location=court)),'2 '+name).lower();assert eid not in w.entities
    print('PASS: 24000 unique entries, ordered chronology, repeated visit, cold save, wallet and death continuity')
