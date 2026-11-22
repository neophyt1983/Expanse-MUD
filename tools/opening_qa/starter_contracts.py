"""Exercise real starter commissions, payroll, housing and recovery on disposable copies."""
import argparse
import asyncio
from pathlib import Path
import random
import re
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from private_game import Game
from engine import commands, frontiers, living, mortality, persistence, settlements, society
from engine import earned_lodging as lodging
from engine import opening_contracts as c

def play(path):
    random.seed(73)
    with tempfile.TemporaryDirectory() as tmp:

        def load():
            g = Game(path, Path(tmp), 'Starter economics').server
            g.world.realtime = True
            return g
        g = load()
        w = g.world

        def create(name, city, gid):
            row = asyncio.run(g.create_character(dict(first_name=name, race='human', sex='male', faction=gid, starting_city=city.lower()), supports_city_choice=True))
            p = w.entities[row['player_id']]
            assert p.gold == 0
            return p

        def run(p, line):
            return commands.process_command(g.registry, w, p, line)

        def go(p, dest):
            steps = frontiers.path(w, p.location, dest, p)
            assert steps is not None
            for _, d, r in steps:
                result = run(p, 'go ' + d)
                assert p.location == r, (p.location, r, result)

        def options(p, job):
            response = run(p, 'startwork status')
            if job == 'cook' and p.location in ['emberhollow_inn', 'emberhollow_inn_kitchen']:
                for _ in range(24):
                    if 'Use startwork accept cook' in response:
                        break
                    if 'Ask Chef Ragnar in person at' not in response:
                        break
                    other = 'emberhollow_inn' if p.location == 'emberhollow_inn_kitchen' else 'emberhollow_inn_kitchen'
                    go(p, other)
                    response = run(p, 'startwork status')
            choices = re.findall('Use (startwork accept ' + job + ' [^ ]+ [0-9]+)\\.', response)
            if not choices:
                print('offer unavailable', p.location, 'minute', living.state(w)['minute'], [(x.name, x.location) for x in w.entities.values() if x.source_def == 'chef_ragnar'], flush=True)
            assert choices, (p.location, response)
            return choices

        def clock(minute):
            living.state(w)['minute'] = minute

        def bill():
            coins = sum((v['gold'] for v in society.economy(w)['shops'].values())) + sum((e.gold for e in w.entities.values())) + sum(settlements.state(w)['treasuries'].values())
            coins += sum((c.WAGE + j['invoice'] for j in living.state(w).get(c.BOOK, {}).values()))
            coins += sum((lodging.cost(row) for row in lodging._rows(w).values() if row['phase'] in lodging.HOLDING))
            return coins
        clock(900)
        society.produce(w)
        settlements.init(w)
        for i, (city, f) in enumerate(c.facilities(w).items()):
            p = create('Clara' + str(i), city, w.rooms[f['inn']].group)
            go(p, c.kitchen(f))
            cook = options(p, 'cook')
            go(p, f['market'])
            carry = options(p, 'deliver')
            print(city, 'cook', cook, 'delivery', carry, flush=True)
        city = 'Dawnwatch'
        f = c.facilities(w)[city]
        a = create('Nelia', city, 'good_guys')
        b = create('Tamas', city, 'good_guys')
        go(a, c.kitchen(f))
        go(b, c.kitchen(f))
        cook = options(a, 'cook')[0]
        dest = f['inn']
        market = f['market']
        src = society.economy(w)['shops'][dest]
        buyer = society.economy(w)['shops'][market]
        baseline = bill()
        stock0 = dict(src['stock'])
        assert 'Order accepted' in run(a, cook)
        assert all((src['stock'][i] == stock0[i] - 6 for i in c.VEGETABLES))
        assert 'Order accepted' not in run(b, cook)
        assert bill() == baseline
        assert 'returned' in run(a, 'startwork cancel') and src['stock'] == stock0 and (bill() == baseline)
        cook = options(a, 'cook')[0]
        assert 'Order accepted' in run(a, cook)
        go(a, c.kitchen(f))
        assert 'Preparing' in run(a, 'startwork cook')
        ids = (a.id, b.id)
        g._save_players_and_world(a.id)
        g.checkpoint_db.close()
        g.db.close()
        g = load()
        w = g.world

        def restore(pid):
            if pid not in w.entities:
                p = persistence.load_player(g.db, pid, 'single')
                w.add_entity(p, p.location)
            return w.entities[pid]
        a, b = map(restore, ids)
        assert c.BOOK in living.state(w) and a.gold == 0
        before = w.living_state[c.BOOK][a.id]['minutes']
        lodging.tick(w, 90)
        assert w.living_state[c.BOOK][a.id]['minutes'] == before
        g.local_save_player = a.id
        lodging.tick(w, before)
        assert 'use startwork deliver' in run(a, 'startwork status').lower()
        assert 'received 30' in run(a, 'startwork deliver')
        assert 'received 30' not in run(a, 'startwork deliver') and a.gold == 30
        row = lodging._rows(w)[a.id]
        unit = row['unit']
        go(a, lodging.ROOMS[unit])
        assert 'Checked in once' in run(a, 'startwork check-in')
        go(a, 'property_unit_' + __import__('hashlib').sha256(unit.encode()).hexdigest()[:24])
        assert a.gold == 30
        go(b, market)
        choices = options(b, 'deliver')
        cash_before = bill()
        assert 'Order accepted' in run(b, choices[0])
        go(b, dest)
        assert 'collect six' in run(b, 'startwork collect')
        assert 'collect six' not in run(b, 'startwork collect')
        go(b, market)
        assert 'received 30' in run(b, 'startwork deliver')
        assert b.gold == 30 and bill() == cash_before
        assert 'received 30' not in run(b, 'startwork deliver')
        print('PASS competing requests, cancel and refund, save/rejoin, inactive time, finite supplies, two distinct 30-gold workflows, sponsored check-in and conservation', flush=True)

def run(path):
    with tempfile.TemporaryDirectory() as temp:

        def open_game():
            game = Game(path, Path(temp), 'Recovery').server
            game.world.realtime = True
            return game
        g = open_game()
        w = g.world

        def create(name):
            data = asyncio.run(g.create_character(dict(first_name=name, race='human', sex='male', faction='cinder_throne', starting_city='cinderhold'), supports_city_choice=True))
            return w.entities[data['player_id']]

        def command(p, cmd):
            return commands.process_command(g.registry, w, p, cmd)
        living.state(w)['minute'] = 900
        society.produce(w)
        settlements.init(w)
        p = create('Rosie')
        stall = 'lw_cinder_inn'

        def stock_state():
            s = living.state(w)
            shop = s['economy']['shops'][stall]
            return (shop['stock'].copy(), shop['gold'], len(s.get(c.BOOK, {})), len(s.get(lodging.KEY, {})))

        def reserve(p):
            result = command(p, 'startwork status')
            assert 'startwork accept cook' in result, result
            quote = result.split('Use startwork accept cook ')[1].split('.')[0]
            command(p, 'startwork accept cook ' + quote)
            assert p.id in w.living_state[c.BOOK]
        assert 'startwork status' in command(p, 'look')
        shop = w.living_state['economy']['shops'][stall]
        money = shop['gold']
        shop['gold'] = 12
        assert 'cannot fund' in command(p, 'startwork status')
        assert p.id not in w.living_state.get(c.BOOK, {})
        shop['gold'] = money
        old = shop['stock']['lw_carrot']
        shop['stock']['lw_carrot'] = 0
        assert 'insufficient unreserved stock' in command(p, 'startwork status')
        shop['stock']['lw_carrot'] = old
        old = shop['stock']['lw_stew']
        shop['stock']['lw_stew'] = 14
        assert 'enough stew' in command(p, 'startwork status')
        shop['stock']['lw_stew'] = old
        before = stock_state()
        reserve(p)
        g._save_players_and_world(p.id)
        asyncio.run(g.delete_character(p.id, owner=True))
        assert stock_state() == before
        g.checkpoint_db.close()
        g.db.close()
        g = open_game()
        w = g.world
        assert stock_state() == before
        p = create('Fern')
        before = stock_state()
        reserve(p)
        w.metadata['player_death'] = 'permanent'
        p.hp = 0
        mortality.record_death(w, p)
        assert stock_state() == before and p.progress['permanently_dead']
        print('PASS insufficient wages, ingredients and demand; on-duty look; explicit deletion atomically restored escrow on disk and in memory; permanent death returned unpaid escrow once.')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world', type=Path, help='Extracted Founding Cities world')
    args = parser.parse_args()
    play(args.world.resolve())
    run(args.world.resolve())
