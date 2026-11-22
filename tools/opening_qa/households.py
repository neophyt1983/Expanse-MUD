"""Exercise household cold saves on a disposable copy of the packaged world."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from private_game import Game
from engine import civic_visits as visits,living
from engine.core import Entity
from engine import resident_watch

parser=argparse.ArgumentParser()
parser.add_argument('world',type=Path)
parser.add_argument('--count',type=int,default=2048)
args=parser.parse_args()
with TemporaryDirectory() as tmp:
    test_dir=Path(tmp); path=args.world.resolve()
    def opened():
        return Game(path,test_dir,'Household QA')
    g=opened();w=g.server.world
    courts=sorted(r for r in w.rooms if visits.COURT.fullmatch(r))
    origin=courts[0];entries=[]
    for court in courts:
        for record in visits.residents(w,court):
            if record['id'] not in w.npcs:entries.append((court,record))
        if len(entries)>=args.count:break
    entries=entries[:args.count]
    def knock(court,row):
        return visits.knock(SimpleNamespace(world=w,player=SimpleNamespace(location=court)),str(row['door'])+' '+row['name'])
    local=Entity('local','Local walker',10,10,1,1,is_player=True)
    w.add_entity(local, origin)
    for court,r in entries:
        if local.location!=court:
            assert w.move_entity(local.id, court, forced=True)
            living.on_entry(w,local)
        assert r['name'] in knock(court,r)
        e=w.entities['npc:'+r['id']]
        if r==entries[0][1]:
            e.gold=7;item=next(iter(w.items));e.inventory=[item,item]
        elif r==entries[1][1]:
            e.progress['escort_post']=court
        elif r==entries[2][1]:
            e.attack+=4
        elif r==entries[3][1]:
            e.activity='sleeping'
    def record(i):
        return entries[i][1]
    def uid(i):
        return record(i)['id']
    def eid(i):
        return 'npc:'+uid(i)
    ctx=SimpleNamespace(world=w,player=SimpleNamespace(location=origin))
    count=lambda:sum('npc:'+r['id'] in w.entities for _,r in entries)
    n=count()
    parked=sum(len(rows) for rows in w.living_state[visits.PARKED].values())
    assert n+parked==len(entries) and n<len(entries)//3,(n,parked)
    assert eid(0) not in w.entities and eid(1) in w.entities and eid(2) in w.entities
    assert w.living_state[visits.PARKED][origin][uid(3)]['activity']=='sleeping'
    g.server._save_players_and_world();g.server.checkpoint_db.close();g.server.db.close()
    del g,w
    g=opened();w=g.server.world; assert count()==n
    assert w.entities[eid(1)].progress['escort_post']==origin and w.entities[eid(2)].attack==6
    player=Entity('visitor','Local visitor',10,10,1,1,is_player=True)
    w.add_entity(player,entries[-1][0])
    try:resident_watch.start(w,player,eid(0))
    except ValueError:pass
    else:raise AssertionError('An unknown remote resident became observable')
    assert eid(0) not in w.entities
    player.progress['chronicle_contacts']={eid(0):{'name':record(0)['name'],'source':uid(0),'born':None}}
    resident_watch.start(w,player,eid(0))
    a=w.entities[eid(0)];assert a.gold==7 and a.inventory==[item,item]
    assert eid(3) not in w.entities
    w.killed_npcs.add(uid(3))
    assert record(0)['name'] in knock(origin,record(0)) and w.entities[eid(0)] is a
    assert knock(origin,record(0))==knock(origin,record(0))
    assert 'no answer' in knock(origin,record(3)).lower() and eid(3) not in w.entities
    g.server._save_players_and_world();g.server.checkpoint_db.close();g.server.db.close()
    g=opened();w=g.server.world;assert 'no answer' in knock(origin,record(3)).lower()
    assert w.entities[eid(0)].gold==7 and w.entities[eid(0)].inventory==[item,item]
    print(json.dumps(dict(met=len(entries),active=n,dormant=parked,active_after_restart=n, wallet=7,inventory_units=2,edited_and_escorting_active=True,authorized_watch=True,unseen_watch_rejected=True,no_resurrection_after_reload=True)))
