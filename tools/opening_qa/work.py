"""Run only with the exact release archive and isolated disposable game state."""
import asyncio
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import commands, earned_start as es, interface_tours, living, loader, persistence, quest_alternatives, society
from server import game_server
from engine import classless

def say(g,p,command,want=None):
    ret=commands.process_command(g.registry,g.world,p,command)
    if want is not None:assert want in ret,(command,ret)
    return ret

def create(g,name):
    d={'first_name':name,'race':'human','class':'fighter','sex':'male','faction':'good_guys'}
    if classless.active(g.world):d.pop("class")
    result=asyncio.run(g.create_character(d))
    return g.world.entities[result['player_id']]

def stop(g):
    if getattr(g,'checkpoint_db',None):g.checkpoint_db.close()
    g.db.close()

def open_actors(g,ids):
    for who in ids:
        p=persistence.load_player(g.db,who,g.mode)
        assert p
        if who not in g.world.entities:g.world.add_entity(p,p.location)
        yield g.world.entities[who]

def active(w):
    return es._read(w)

def numbers(g,actors):
    book=active(g.world)
    cfg,pocket,_=es._business(g.world)
    return pocket['gold'],sum(p.gold for p in actors),4*len(book),dict(pocket['stock'])

def exercise(root):
    random.seed(int(os.environ.get('EXPANSE_FIXTURE_SEED','73')))
    p=root/'games'/'wild_lands';p.mkdir(parents=True)
    with ZipFile(ARCHIVE) as z:z.extractall(p)
    loader.GAMES_DIR=p.parent;loader.WORLD_UPDATE_TEMPLATES=();loader.set_game_dir(p)
    game_server.SAVE_DIR=root/'save';persistence.DB_PATH=root/'save'/'world.db'
    game_server.WORLD_STATE_PATH=root/'save'/'world_state_host.json'
    meta=p/'metadata.json';data=json.loads(meta.read_text())
    g=game_server.GameServer('host');old=create(g,'Legacy Starter');old_id=old.id
    assert old.gold==25 and not es.marked(old)
    assert es.GUIDE in g.world.quests
    say(g,old,'read first_steps_good_guys_welcome_letter','Learn the Interface')
    assert quest_alternatives.preview(g.world,old,es.GUIDE)['replacement']['id']==es.SKIP
    g._save_players_and_world(old.id);stop(g)
    data[es.FLAG]=es.VERSION;data[classless.FLAG]=classless.VERSION;meta.write_text(json.dumps(data))
    g=game_server.GameServer('host')
    old,=open_actors(g,[old_id])
    a,b=(create(g,'Fixture New A'),create(g,'Fixture New B'))
    ids=[a.id,b.id]
    w=g.world
    original_bags={t.id:tuple(t.inventory) for t in (a,b)}
    assert all(classless.marked(p) and p.char_class is None and not p.inventory for p in (a,b))
    assert old.gold==25 and not es.marked(old) and a.gold==b.gold==0 and es.marked(a) and es.marked(b)
    assert living.state(w)['minute']==375 and a.location==b.location==es.INN
    assert es.GUIDE not in say(g,a,'read first_steps_good_guys_welcome_letter','startwork status')
    assert interface_tours.projection(w,a)=={'player_id':a.id,'choices':[],'current':None,'earned_start':True}
    for q in (es.GUIDE,es.SKIP):
        assert 'not part of your in-world start' in living.quest_blocked(w,a,w.quests[q])
    try:quest_alternatives.preview(w,a,es.GUIDE)
    except ValueError as exc:assert 'not part of your in-world start' in str(exc)
    else:raise AssertionError('obsolete skip remained accessible')
    assert 'replacement' in quest_alternatives.preview(w,old,es.GUIDE)
    say(g,a,'interface guide',"can't do that here")
    say(g,a,'look','Kitchen work')
    say(g,a,'startwork status','west from the tavern')
    say(g,a,'go west','You go west')
    say(g,b,'go west','You go west')
    say(g,a,'startwork status','not taking orders')
    # The fixture waits for the real existing shop opening shift. For this
    # integration test only, place the authoritative clock at service opening.
    living.state(w)['minute']=420
    # Existing normal world phase, not creation by the job commands.
    society.produce(w)
    if os.environ.get('EXPANSE_TEST_CHEF_ABSENT')=='1':
        assert not any(e.source_def==es.CHEF and e.alive for e in w.entities_in_room(es.KITCHEN))
        initial=numbers(g,(a,b))
        say(g,a,'startwork status','not taking orders')
        say(g,a,'startwork accept','not taking orders')
        assert initial==numbers(g,(a,b))
        stop(g)
        print('PASS exact Wild Lands: chef at a different room during posted start; no work fabricated, no funds or stock moved, fallback available.')
        return
    assert es._chef(w).source_def==es.CHEF
    _,business,_=es._business(w)
    start=business['gold'];stock=dict(business['stock'])
    assert stock[es.RECIPE]<=8 and start>=2*es.WAGE,(start,stock.get(es.RECIPE))
    # Insufficient pay control: bankroll remains owned by the existing shops.
    _,other=society.shop(w,'fw_dawn_0')
    diff=start-(es.WAGE-1)
    business['gold']-=diff;other['gold']+=diff
    say(g,a,'startwork accept','cannot reserve 4 gold')
    say(g,a,'startwork status','Civic Square request ledger')
    assert not active(w) and business['gold']==es.WAGE-1 and a.gold==0
    business['gold']+=diff;other['gold']-=diff
    say(g,a,'startwork status','No purchase or tool is required')
    if os.environ.get('EXPANSE_TEST_DECLINE')=='1':
        before=numbers(g,(a,b))
        wallet=a.gold;quests=dict(a.progress.get('quests',{}))
        assert not a.progress.get('home_property')
        say(g,a,'startwork accept','Reserved:')
        assert active(w)
        say(g,a,'startwork decline','No wage, accommodation or quest completion was granted.')
        say(g,a,'startwork decline','First job declined')
        assert numbers(g,(a,b))==before and not active(w) and a.gold==wallet
        assert not a.progress.get('home_property') and a.progress.get('quests',{})==quests
        say(g,a,'go east','You go east')
        say(g,a,'go south','You go south')
        assert a.location=='emberhollow_square'
        g._save_players_and_world(a.id);stop(g)
        g=game_server.GameServer('host');a,b=open_actors(g,ids);w=g.world
        assert numbers(g,(a,b))==before and not active(w) and a.location=='emberhollow_square'
        assert a.progress.get(es.DECLINED) is True and a.progress.get('quests',{})==quests
        assert a.gold==wallet and not a.progress.get('home_property')
        stop(g)
        print('PASS exact Wild Lands: explicit Decline after escrow releases the exact old funds/stock, records no quest or bed, is harmless to repeat, permits ordinary departure, and persists after normal save/reopen.')
        return
    say(g,a,'startwork accept','Reserved:')
    say(g,a,'startwork accept','Reserved:')
    assert numbers(g,(a,b))[:3]==(start-4,0,4)
    say(g,b,'startwork accept','Reserved:')
    say(g,b,'startwork cancel','returned to the business')
    assert numbers(g,(a,b))[:3]==(start-4,0,4)
    say(g,b,'startwork accept','Reserved:')
    assert numbers(g,(a,b))[:3]==(start-8,0,8)
    for key,n in es.INPUTS.items():assert business['stock'][key]==stock[key]-2*n
    say(g,a,'startwork deliver','Prepare the bowl first')
    say(g,a,'startwork cook','on the stove for 5 game minutes')
    clock=living.state(w)['minute']
    say(g,a,'startwork cook','5 game minutes left')
    assert living.state(w)['minute']==clock
    g._save_players_and_world(a.id);stop(g)
    g=game_server.GameServer('host');a,b=open_actors(g,ids);w=g.world
    assert numbers(g,(a,b))[:3]==(start-8,0,8)
    say(g,a,'startwork status','Preparing')
    say(g,b,'startwork cook','on the stove')
    living.state(w)['minute']=max(v['ready_at'] for v in active(w).values())
    for row in (a,b):
        say(g,row,'startwork cook','Prepared one bowl')
        say(g,row,'startwork cook','nothing was cooked twice')
        say(g,row,'startwork deliver','Paid 4 gold once')
        say(g,row,'startwork deliver','No unsettled kitchen order')
        say(g,row,'startwork accept','shift is finished')
        assert row.gold==4
    assert all(tuple(t.inventory)==original_bags[t.id] for t in (a,b))
    gold,players,escrow,shelves=numbers(g,(a,b))
    assert (gold,players,escrow,shelves[es.RECIPE])==(start-8,8,0,stock[es.RECIPE]+2)
    # First Bearings really follows normal authored reading/actions and does not
    # pretend the old interface lesson was completed or generate old starter cash.
    say(g,a,'go east','You go east')
    say(g,a,'read first_steps_good_guys_welcome_letter','First Bearings')
    say(g,a,'accept '+es.CHAIN,'Quest accepted')
    say(g,a,'go south','You go south')
    say(g,a,'read first_steps_good_guys_local_notes')
    say(g,a,'complete '+es.CHAIN,'Quest complete')
    assert es.GUIDE not in a.progress['quests'] and a.gold==4
    say(g,a,'read first_steps_good_guys_local_notes','A Meal Before the Road')
    assert es.gold_reward(a, w.quests['first_steps_good_guys_3'])==0
    g._save_players_and_world(a.id);stop(g)
    g=game_server.GameServer('host');a,b=open_actors(g,ids);w=g.world
    assert numbers(g,(a,b))[:3]==(start-8,8,0)
    assert not active(w) and a.progress['quests'][es.CHAIN]=='complete' and es.GUIDE not in a.progress['quests']
    assert a.gold==b.gold==4 and all(es.marked(row) for row in (a,b))
    stop(g)
    print('PASS exact Wild Lands: both zero at 06:15; real budget refusal; two funded batches, no raw item grant or inventory duplicate, timed preparation/reopen, real shelf handover and exact finite wages once; guide and skip denied, ordinary continuation complete, old character remains eligible for old guide and original wallet intact.')

ARCHIVE=Path(sys.argv[1]).resolve(strict=True)
with ARCHIVE.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='65ebebbe5bae932464ab2490c8ee87defc5c01178ef4d51fae79f2bfb3b6660c'
with TemporaryDirectory(prefix='expanse-earned-start-') as d:exercise(Path(d))
