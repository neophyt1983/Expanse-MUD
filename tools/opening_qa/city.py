import asyncio,hashlib,json,random,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import classless,commands,loader,persistence,starter_safety,starting_cities as c
from private_game import Game

ARCH=Path(sys.argv[1]); assert hashlib.sha256(ARCH.read_bytes()).hexdigest()=='65ebebbe5bae932464ab2490c8ee87defc5c01178ef4d51fae79f2bfb3b6660c'
class Request:
    def __init__(self,path,body=None):
        self.path=path;self.method='GET' if body is None else 'POST';self.body=body
    async def json(self):return self.body
async def api(g,path,body=None):
    return json.loads((await g.api(Request('/api/character/'+path,body))).body)
def form(name,race,faction,**kwargs):return dict(first_name=name,race=race,faction=faction,sex='male',**kwargs)
def offline(g):g.server.checkpoint_db.close();g.server.db.close()
async def main():
 with TemporaryDirectory() as temp:
    root=Path(temp);wpath=root/'games/wild_lands';wpath.mkdir(parents=True)
    with ZipFile(ARCH) as z:z.extractall(wpath)
    metadata=wpath/'metadata.json';m=json.loads(metadata.read_text())
    random.seed(73)
    g=Game(wpath,root/'state','City fixture')
    assert 'starting_cities' not in await api(g,'options')
    old=await api(g,'create',form('Legacy Resident','human','roadkeepers',**{'class':'fighter'}))
    assert old['start_room']=='lw_hearth_inn' and 'starting_city' not in old
    g.server._save_players_and_world(old['player_id']);offline(g)
    m.update({classless.FLAG:classless.VERSION,c.FLAG:c.VERSION});metadata.write_text(json.dumps(m))
    g=Game(wpath,root/'state','City fixture');s=g.server;w=s.world
    options=await api(g,'options');assert options['classless_start'] and options['choose_starting_city']
    assert len(options['starting_cities'])==8
    assert len(options['races'])==6
    for race in options['races']:
        for city in options['starting_cities']:
            assert c.choice(w,{'starting_city':city['id'],'race':race['id']},supported=True)[0]==city['id']
    def actor_count():return sum(a.is_player for a in w.entities.values())
    for bad in (None,'',{},'emberhollow_underworld','world:secret','nobody'):
        before=actor_count()
        try:await api(g,'create',form('Invalid Choice','human','roadkeepers',starting_city=bad))
        except ValueError as e: assert 'No character was created' in str(e)
        else:raise AssertionError('bad city accepted')
        assert before==actor_count()
    try:await s.create_character(form('Unsupported City','human','roadkeepers',starting_city='hollowcrown'))
    except ValueError as e:assert 'not available here' in str(e)
    else:raise AssertionError('other mode accepted an unadvertised city')
    c1=await api(g,'create',form('Returned Visitor','zombie','good_guys',starting_city='reedwater'))
    c2=await api(g,'create',form('Human Visitor','human','roadkeepers',starting_city='hollowcrown'))
    pairs=[(c1,'reedwater','lw_reed_inn','good_guys','zombie'),(c2,'hollowcrown','emberhollow_underworld','roadkeepers','human')]
    moved={}
    for a,cid,rid,faction,race in pairs:
        assert (a['starting_city'],a['start_room'],a['faction'],a['race'],a['class'])==(cid,rid,faction,race,None)
        p=w.entities[a['player_id']]
        assert p.location==rid and p.progress[c.MARKER]==cid and p.gold==0 and classless.marked(p)
        assert p.progress.get('home_room') is None and p.progress.get('home_property') is None
        assert not p.progress.get('ancestral_origin')
        # An actual public tavern exit is usable, independent of selected faction.
        direction='out' if 'out' in w.rooms[rid].exits else ('north' if cid=='hollowcrown' else 'west')
        previous=p.location
        msg=commands.process_command(s.registry,w,p,'go '+direction)
        assert p.location!=previous,(p.name,msg,w.rooms[rid].exits)
        moved[p.id]=p.location
        s._save_players_and_world(p.id)
    offline(g)
    del m[c.FLAG];del m[classless.FLAG];metadata.write_text(json.dumps(m))
    g=Game(wpath,root/'state','City fixture')
    assert 'starting_cities' not in await api(g,'options')
    for a,cid,rid,faction,race in pairs:
        p=persistence.load_player(g.server.db,a['player_id'],'single')
        assert p.location==moved[p.id] and p.progress[c.MARKER]==cid and p.group_id==faction and p.race==race
    old_actor=persistence.load_player(g.server.db,old['player_id'],'single')
    assert old_actor.location=='lw_hearth_inn' and old_actor.char_class=='fighter' and c.MARKER not in old_actor.progress
    offline(g)
    print('EXACT_CITY_START_PASS: all 48 option combinations, two real crossed entries and public exits, clean invalid input, legacy and moved saved positions after cold reload/flags off.')
asyncio.run(main())
