"""Run one year of co-operative issues on a disposable copy of the loaded world."""
import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from engine import household_provisions as provisions, living, society, worldtime
from private_game import Game


def market_stock(world, rule):
    if not world.room_details[rule['market']].get('workshop'):
        return 0
    _, shop = society.shop(world, rule['market'])
    return shop['stock'].get(rule['meal_item'], 0)


def snapshot(world, rules):
    return json.dumps({
        'ledger': living.state(world).get(provisions.KEY),
        'market': {city:market_stock(world, rule) for city,rule in rules.items()},
        'press': living.state(world).get('press_archive_v1'),
    }, sort_keys=True)


def issue(world, rules, day, clock, totals=None):
    now = day * worldtime.MINUTES_PER_DAY + clock
    state = living.state(world)
    opening = {city: dict(state.get(provisions.KEY, {}).get(city, {}).get('stock', {}))
               for city in rules}
    shops = {city:market_stock(world, rule) for city,rule in rules.items()}
    held = {city: sum(state.get(provisions.KEY, {}).get(city, {}).get('meal_counters', {}).values()) for city in rules}
    state['minute'] = now
    provisions.advance(world, now-1, now)
    rows = {}
    for city, rule in rules.items():
        ledger = state[provisions.KEY][city]
        row = ledger['history'][-1]
        stock = ledger['stock']
        assert ledger['day'] == row['day'] == day
        assert 1 <= len(ledger['history']) <= worldtime.DAYS_PER_WEEK
        assert all(type(n) is int and n >= 0 for n in stock.values())
        assert row['opening'] == opening[city].get(rule['meal_item'], 0)
        assert row['required'] == row['issued'] + row['short']
        assert row['required'] == row['residents'] * rule['daily_portions']
        assert row['closing'] == stock[rule['meal_item']]
        assert row['opening'] + row['cooked'] == row['issued'] + row['market_delivery'] + row.get('counter_delivery', 0) + row['closing']
        assert market_stock(world, rule) - shops[city] == row['market_delivery']
        counter_stock = sum(ledger.get('meal_counters', {}).values())
        assert held[city] + row['counter_delivery'] == counter_stock
        assert ledger['cumulative']['counter_delivery'] == counter_stock + ledger.get('collected', 0)
        for item, n in world.recipes[rule['recipe']]['ingredients'].items():
            assert row['raw_before'][item] == opening[city].get(item, 0)
            assert row['used'].get(item, 0) == row['cooked'] * n
            assert stock[item] == opening[city].get(item,0) + row['harvested'][item] - row['used'].get(item,0)
        if totals is not None:
            result = totals[city]
            assert result['residents'] in (None,row['residents'])
            result['residents'] = row['residents']
            result['short_days'] += int(row['short']>0)
            result['raw_harvested'].update(row['harvested'])
            result['raw_used'].update(row['used'])
            for key in ('cooked','issued','required','short','market_delivery'):
                result[key] += row[key]
            latitude = world.room_details[rule['field']].get('climate', {}).get('latitude',45)
            season = worldtime.season(now,latitude)
            result['short_by_season'][season] += row['short']
            result['pantry'] = dict(stock)
        rows[city] = row
    recorded = snapshot(world,rules)
    provisions.advance(world, now-1, now)
    assert recorded == snapshot(world,rules), 'A repeated issue duplicated state.'
    return rows


def close(game):
    game.server.checkpoint_db.close()
    game.server.db.close()



def clock_crossing(path):
    """Use an actual simulation tick with a live and a deceased co-op grower."""
    from engine import civic_visits, mortality
    from engine.core import Entity
    with TemporaryDirectory(prefix='household-issue-clock-') as temp:
        game = Game(path.resolve(), Path(temp), 'Clock crossing')
        world = game.server.world
        settings = provisions.config(world)
        city = 'Dawnwatch'
        rule = settings['cities'][city]
        clock = settings['issue_minute']
        living.state(world)['minute'] = clock - 1
        prefix = rule['member_prefix']
        founders = provisions.unavailable(world)[prefix]
        baseline = rule['member_count'] - len(founders)
        growers = set(rule['workforce']['growers'])
        baseline_growers = len(growers - founders)
        court = 'gen_dawn_lane_1'
        rows = [r for r in civic_visits.residents(world, court)
                if r['id'].startswith(prefix) and int(r['id'][len(prefix):]) in growers-founders][:2]
        assert len(rows) == 2
        player = Entity('clock_viewer','Court visitor',10,10,1,1,is_player=True)
        world.add_entity(player, court)
        ctx = SimpleNamespace(world=world, player=player)
        for row in rows:
            assert row['name'] in civic_visits.knock(ctx, str(row['door'])+' '+row['name'])
        victim = world.entities['npc:'+rows[1]['id']]
        mortality.environmental_damage(world, victim, 1000, 'falling masonry in the test world')
        assert not victim.alive and rows[1]['id'] in world.killed_npcs
        assert world.entities['npc:'+rows[0]['id']].alive
        assert provisions.KEY not in living.state(world)
        world.tick_authorized = True
        living.advance(world, 1)
        assert living.state(world)['minute'] == clock
        ledger = living.state(world)[provisions.KEY]
        assert set(ledger) == set(settings['cities'])
        row = ledger[city]['history'][0]
        assert row['residents'] == baseline-2 and row['growers'] == baseline_growers-2
        recorded = json.dumps(ledger, sort_keys=True)
        living.advance(world, 1)
        assert living.state(world)['minute'] == clock+1
        assert recorded == json.dumps(ledger, sort_keys=True)
        close(game)
        return {'city':city,'clock_minutes':[clock-1, clock, clock+1],
                'cities_issuing':len(ledger),'ordinary_residents_baseline':baseline,
                'issued_population':row['residents'],'growers_baseline':baseline_growers,
                'growers_after_materialization_and_death':row['growers'],
                'live_and_dead_each_excluded_once':True,'following_tick_duplicated_issues':False}


def run(path):
    directory = path.resolve()
    with TemporaryDirectory(prefix='household-food-year-') as temp:
        def open_game():
            return Game(directory, Path(temp), 'Co-operative acceptance')
        game = open_game()
        world = game.server.world
        config = provisions.config(world)
        clock = config['issue_minute']
        rules = config['cities']
        assert len(rules) == 8
        totals = {
            city: {'residents':None,'cooked':0,'issued':0,'required':0,'short':0,
                   'market_delivery':0,'short_days':0,'raw_harvested':Counter(),'raw_used':Counter(),
                   'short_by_season':Counter()}
            for city in rules}
        restart = worldtime.DAYS_PER_YEAR // 2
        for day in range(worldtime.DAYS_PER_YEAR):
            issue(world, rules, day, clock, totals)
            # Stress stock conservation at maximum drawdown every day. Real individual
            # pickup and consumption are exercised separately by the live scheduler.
            for ledger in living.state(world)[provisions.KEY].values():
                lots = ledger['meal_counters']
                withdrawn = sum(lots.values())
                ledger['collected'] = ledger.get('collected', 0) + withdrawn
                lots.update(dict.fromkeys(lots, 0))
            if day + 1 == restart:
                saved = snapshot(world, rules)
                game.server._save_players_and_world()
                close(game)
                game = open_game()
                world = game.server.world
                rules = provisions.config(world)['cities']
                assert saved == snapshot(world, rules)
                minute = living.state(world)['minute']
                provisions.advance(world, minute-1, minute)
                assert saved == snapshot(world, rules), 'Restart replay duplicated provisions.'
        annual = {key: sum(row[key] for row in totals.values())
                  for key in ('residents','required','cooked','issued','short','market_delivery')}
        # One valid alternate opening window closes only this city's issue counter.
        city = 'Dawnwatch'
        rule = rules[city]
        market = world.room_details[rule['market']]
        market['opening_hours'] = {'start':(clock+60)%worldtime.MINUTES_PER_DAY,'duration':60}
        shortage = issue(world, rules, worldtime.DAYS_PER_YEAR, clock)[city]
        assert shortage['issued'] == shortage['market_delivery'] == 0
        assert shortage['short'] == shortage['required'] > 0
        assert shortage['closing'] >= shortage['opening']
        account = living.state(world)[provisions.KEY][city]
        assert shortage['counter_delivery'] == 0
        assert account['cumulative']['short'] == shortage['short']
        drawn = sum(ledger.get('collected', 0) for ledger in living.state(world)[provisions.KEY].values())
        close(game)
    return {'scope':'Daily co-operative provisions on the packaged world, stepwise through every season. '
                    'Individual NPC AI, wildlife, purchases and other simulation clocks were not advanced.',
            'worst_case_counter_portions_withdrawn':drawn,'days':worldtime.DAYS_PER_YEAR, 'cities_checked':len(totals),
            'cold_restart_after_issues':restart, 'issues_replayed':worldtime.DAYS_PER_YEAR+1,
            'conservation':'Raw ingredients, cooked portions and actual public market inventory checked every city/day.',
            'totals':annual,'cities':totals,'closed_market_control':{'city':city,
            'required':shortage['required'],'issued':shortage['issued'],'short':shortage['short'],
            'market_delivery':shortage['market_delivery'],'pantry_closing':shortage['closing']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    report = run(args.world)
    report['whole_simulation_clock_crossing'] = clock_crossing(args.world)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(report['totals']))
    print(json.dumps(report['closed_market_control']))
