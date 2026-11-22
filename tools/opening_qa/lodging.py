"""Actual registered rental and ordinary gameplay against a disposable exact archive."""
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
OFFICIAL = os.environ.get('EXPANSE_TEST_OFFICIAL_STAGE')=='1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import commands,earned_lodging as el,earned_start as es,living,loader,persistence,property_interiors,settlements,society
from server import game_server

def run(g,p,line,want):
    result=commands.process_command(g.registry,g.world,p,line)
    assert want in result,(line,result)
    return result

def new(g,name):
    result=asyncio.run(g.create_character({'first_name':name,'race':'human','class':'fighter','sex':'male','faction':'good_guys'}))
    return next(open_actors(g,[result['player_id']]))

def stop(g):
    g.checkpoint_db.close();g.db.close()

def open_actors(g,ids):
    for which in ids:
        p=persistence.load_player(g.db,which,g.mode)
        assert p
        if which not in g.world.entities:g.world.add_entity(p,p.location)
        yield g.world.entities[which]

def reconcile(g,actors,expected):
    w=g.world
    book=el._rows(w);jobs=es._read(w)
    _,shelf,_=es._business(w)
    city=settlements.state(w)['treasuries']['good_guys']
    wages=es.WAGE*len(jobs)
    rent=sum(el.cost(r) for r in book.values() if r['phase'] in el.HOLDING)
    wallets=sum(p.gold for p in actors)
    assert city+shelf['gold']+wages+rent+wallets==expected,(city,shelf['gold'],wages,rent,wallets,expected)
    return city,shelf['gold'],wages,rent,wallets

def exercise(root):
    random.seed(73)
    world=root/'games'/'wild_lands';world.mkdir(parents=True)
    with ZipFile(ARCHIVE) as z:z.extractall(world)
    loader.GAMES_DIR=world.parent;loader.WORLD_UPDATE_TEMPLATES=();loader.set_game_dir(world)
    game_server.SAVE_DIR=root/'save';persistence.DB_PATH=root/'save'/'world.db'
    game_server.WORLD_STATE_PATH=root/'save'/'world_state_host.json'
    if OFFICIAL:
        from engine import stage_save_integrity
        stage=root/'private';stage.mkdir()
        game_server.SAVE_DIR=stage/'save'
        persistence.DB_PATH=stage/'save'/'world.db'
        game_server.WORLD_STATE_PATH=stage/'save'/'world_state_host.json'
        identity=stage_save_integrity.stage_identity(stage,DIGEST)
        make=lambda:game_server.GameServer(mode='host',verified_stage=identity,background_residents=True)
    else:
        make=lambda:game_server.GameServer('host')
    g=make();baseline=new(g,'Disposal Legacy')
    assert baseline.gold==25 and not el.enabled(g.world)
    g._save_players_and_world(baseline.id);stop(g)
    meta=world/'metadata.json';data=json.loads(meta.read_text());data.update({es.FLAG:es.VERSION,el.FLAG:el.VERSION});meta.write_text(json.dumps(data))
    g=make();w=g.world
    a=new(g,'Sponsored Fixture A');b=new(g,'Sponsored Fixture B');ids=(a.id,b.id)
    for p in (a,b):run(g,p,'go west','You go west')
    living.state(w)['minute']=420
    society.produce(w)
    s=settlements.init(w)
    city=s['treasuries']['good_guys'];_,shelf,_=es._business(w);start=shelf['gold'];frozen=dict(shelf['stock'])
    unit_ids=el.UNITS
    assert [s['units'][u]['rent'] for u in unit_ids]==[2,2]
    total=start+city
    assert reconcile(g,(a,b),total)==(city,start,0,0,0)
    run(g,a,'startwork status','18 existing sponsor gold')
    assert reconcile(g,(a,b),total)==(city,start,0,0,0)
    # Valid wage but insufficient combined accommodation. Move coins to a
    # second existing shop for this local failure-control; no new currency.
    _,other=society.shop(w,'fw_dawn_0')
    limited=start-21;shelf['gold']-=limited;other['gold']+=limited
    run(g,a,'startwork accept boarding-house 18','no longer confirmed or funded')
    assert not el._rows(w) and not es._read(w) and shelf['stock']==frozen and shelf['gold']==21
    shelf['gold']+=limited;other['gold']-=limited
    # Same game minute, sequential authoritative dispatch, not wall-time or
    # concurrent storage assumptions. Both initially quote the same top unit.
    assert unit_ids[0]==el.plan(w,a,shelf,4)['unit']==el.plan(w,b,shelf,4)['unit']
    run(g,a,'startwork accept','Choose the specific available lodging')
    run(g,a,'startwork accept boarding-house 17','quoted lodging rate changed')
    run(g,a,'startwork accept boarding-house 18','Charter Green Boarding House')
    run(g,b,'startwork accept boarding-house 18','no longer confirmed or funded')
    assert len(el._rows(w))==1
    assert 'Orchard Wall Cottage' in run(g,b,'startwork status','accept orchard-cottage 18')
    run(g,b,'startwork accept orchard-cottage 18','Orchard Wall Cottage')
    assert el._rows(w)[a.id]['unit']==unit_ids[0] and el._rows(w)[b.id]['unit']==unit_ids[1]
    assert reconcile(g,(a,b),total)==(city,start-44,8,36,0)
    assert all(property_interiors.acquisition_problem(w,s['units'][u]) for u in unit_ids)
    run(g,a,'startwork check-in','No earned prepaid room is ready')
    run(g,b,'startwork decline','No wage, accommodation or quest completion was granted.')
    run(g,b,'startwork decline','First job declined')
    assert reconcile(g,(a,b),total)==(city,start-22,4,18,0)
    assert not property_interiors.acquisition_problem(w,s['units'][unit_ids[1]]) and not b.progress.get('home_property')
    assert el._rows(w).get(b.id) is None and not b.gold
    for key,qty in es.INPUTS.items():assert shelf['stock'][key]==frozen[key]-qty
    run(g,a,'startwork cook','on the stove for 5 game minutes')
    living.state(w)['minute']=es._read(w)[a.id]['ready_at']
    run(g,a,'startwork cook','Prepared one bowl')
    run(g,a,'startwork deliver','Sponsored lodging is ready')
    assert reconcile(g,(a,b),total)==(city,start-22,0,18,4)
    g._save_players_and_world(a.id);stop(g)
    g=make();a,b=open_actors(g,ids);w=g.world;s=settlements.state(w)
    assert reconcile(g,(a,b),total)==(city,start-22,0,18,4)
    run(g,a,'startwork check-in','Visit the same eligible available parcel')
    unit=s['units'][unit_ids[0]]
    rid=unit['room']
    for d,target in el.PATHS[rid]:
        run(g,a,'go '+d,'You go '+d)
        assert a.location==target,(d,a.location,target)
    run(g,a,'startwork check-in','Checked in once and paid the lawful payee')
    run(g,a,'startwork check-in','already active; no additional payment')
    assert reconcile(g,(a,b),total)==(city+18,start-22,0,0,4)
    assert unit['tenant']==a.id and a.progress['home_property']==unit['id'] and a.gold==4
    run(g,a,'property enter '+unit['id'],'You arrive')
    assert a.location==property_interiors.room_id(unit['id']) and property_interiors.home_shelter(w,a)
    g._save_players_and_world(a.id);stop(g)
    g=make();a,b=open_actors(g,ids);w=g.world;s=settlements.state(w)
    assert property_interiors.home_shelter(w,a)
    row=el._rows(w)[a.id]
    assert row['remaining']==el.WEEK==13500
    # Real engine accounting functions at controlled clock edges; dict socket
    # placeholders stand for gameplay binding. A retained offline actor exists.
    g.clients[object()]=b.id
    # Freeze unrelated daily civic building/rental assignments in this
    # controlled interval; settlement's normal rent loop still executes.
    s['last']=living.state(w)['minute']
    el.tick(w,6000);settlements.advance(w)
    assert row['remaining']==el.WEEK and a.gold==4
    inlet=object();g.clients[inlet]=a.id;el.tick(w,1500)
    assert row['remaining']==12000 and a.gold==4
    del g.clients[inlet]
    el.tick(w,5000);settlements.advance(w)
    assert row['remaining']==12000 and a.gold==4
    assert reconcile(g,(a,b),total)==(city+18,start-22,0,0,4)
    g._save_players_and_world(a.id);stop(g)
    g=make();a,b=open_actors(g,ids);w=g.world;s=settlements.state(w)
    r=el._rows(w)[a.id];assert r['remaining']==12000 and not g.clients
    g.clients[object()]=a.id;el.tick(w,12000)
    assert not el._rows(w) and s['units'][unit_ids[0]]['tenant']=='' and not a.progress.get('home_property')
    assert a.gold==4 and reconcile(g,(a,b),total)==(city+18,start-22,0,0,4)
    stop(g)
    print('PASS: exact suitable two units; same-minute quotes did not double book; 18 currency prepaid once from sponsor to actual treasury, player spent 0; Decline restored resources and no bed; true entry and cold reopen; bound time only, hold while disconnected, expiry/no arrears or renewal; finite aggregate conserved.')

ARCHIVE=Path(sys.argv[1]).resolve(strict=True)
DIGEST='65ebebbe5bae932464ab2490c8ee87defc5c01178ef4d51fae79f2bfb3b6660c'
with ARCHIVE.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()==DIGEST
with TemporaryDirectory(prefix='expanse-lodging-') as t:exercise(Path(t))
