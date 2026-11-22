"""Exercise feeding phases, the real resident scheduler or local habitat recovery in an extracted world."""
import argparse
import asyncio
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from private_game import Game
from engine import combat, commands, frontiers, living, needs_market, society, wildlife
from engine import wildlife_coin_provenance as coin

def feed(world_path):
    random.seed(1122)
    with tempfile.TemporaryDirectory() as tmp:
        game = Game(world_path, Path(tmp), 'Wildlife week')
        w = game.server.world
        s = living.state(w)
        origin = s['minute']
        regions = {w.rooms[f['inn']].group: city for city, f in w.metadata['city_population_198']['facilities'].items()}

        def region(e):
            return regions.get(w.rooms[e.location].group, 'Outlying')

        def ordinary(e):
            return e.alive and (not e.is_player) and coin.guarded(w, w.npcs.get(e.source_def, {}), e)
        original = {e.id: region(e) for e in w.entities.values() if ordinary(e)}
        meals_by_region = Counter()
        last_fed = {}
        elapsed = time.monotonic()
        for i in range(451):
            now = origin + 30 * i
            s['minute'] = now
            society.produce(w)
            commands.advance_spawners(w)
            wildlife.advance(w)
            for e in w.entities.values():
                if ordinary(e) and e.progress.get('feeding', {}).get('last_meal') == now:
                    meals_by_region[region(e)] += 1
                    last_fed[e.id] = now
            if i % 50 == 0:
                animals = [e for e in w.entities.values() if ordinary(e)]
                stats = s['wildlife']
                j = {'day': i // 50, 'elapsed': round(time.monotonic() - elapsed, 1), 'animals_alive': len(animals), 'meals_recorded': stats['meals'], 'hunts_recorded': stats['hunts'], 'forage_sites_used': len(stats['forage']), 'initial_animals_lost': len(set(original) - {e.id for e in animals}), 'at_least_day_since_observed_meal': sum((now - last_fed.get(e.id, origin) >= 1500 for e in animals)), 'by_region': dict(meals_by_region)}
                print(json.dumps(j), flush=True)
        stocks = [n for shop in society.economy(w)['shops'].values() for n in shop['stock'].values()]
        assert min(stocks) >= 0 and s['wildlife']['meals'] > 0 and (set(regions.values()) <= meals_by_region.keys())
        print('PASS all eight regions had animals record meals, nonnegative workshop stock; no survival claim', flush=True)

def check(path, days=1):
    random.seed(1186)
    with tempfile.TemporaryDirectory() as tmp:
        game = Game(path, Path(tmp), 'Active food')
        w = game.server.world
        s = living.state(w)
        regions = {w.rooms[f['inn']].group: city for city, f in w.metadata['city_population_198']['facilities'].items()}

        def cohort(e):
            return e.alive and (not e.is_player) and (e.group_id in regions) and needs_market.applies(w, e)
        original = {e.id: regions[e.group_id] for e in w.entities.values() if cohort(e)}
        print('initial cohort', dict(Counter(original.values())), flush=True)
        eaten = Counter()
        consumers = set()
        use = needs_market.use

        def logged(world, actor, item):
            count = len(actor.inventory)
            success = use(world, actor, item)
            if success and len(actor.inventory) < count and (actor.id in original) and (world.items.get(item, {}).get('need_effects', {}).get('hunger', 0) > 0):
                eaten[original[actor.id]] += 1
                consumers.add(actor.id)
            return success
        needs_market.use = logged
        start = time.monotonic()
        for i in range(50 * days):
            living.advance(w, 30)
            if (i + 1) % 5 == 0:
                currently = [e for e in w.entities.values() if cohort(e)]
                wallets = {r: 0 for r in regions.values()}
                for e in currently:
                    if e.gold <= 0:
                        wallets[regions[e.group_id]] += 1
                levels = sorted((needs_market.state(e)['hunger'] for e in currently))
                print(json.dumps({'step': i + 1, 'minute': s['minute'], 'elapsed': round(time.monotonic() - start, 2), 'materialized': len(currently), 'median_hunger': round(levels[len(levels) // 2], 1), 'hunger_over_75': sum((n >= 75 for n in levels)), 'hunger_at_100': sum((n >= 100 for n in levels)), 'cash_exhausted': sum(wallets.values()), 'initial_residents_who_ate': len(consumers), 'hunger_reducing_items_consumed_by_city': dict(eaten), 'npc_market_purchases': society.economy(w).get('npc_purchases', 0)}), flush=True)
        print(f'PASS exercised {25 * days} game hours through the resident scheduler.', flush=True)

def measure(path):
    with tempfile.TemporaryDirectory() as tmp:
        g = Game(path, Path(tmp), 'Habitat recovery').server
        w = g.world
        p = w.entities[asyncio.run(g.create_character(dict(first_name='Siteobserver', race='human', sex='male', faction='good_guys', starting_city='dawnwatch'), supports_city_choice=True))['player_id']]
        targets = {}
        for city, f in w.metadata['city_population_198']['facilities'].items():
            group = w.rooms[f['inn']].group
            for e in w.entities.values():
                if e.source_def != 'species_deer_carrier' or not e.spawner_key or e.progress.get('companion_owner') or e.progress.get('zoo_exhibit'):
                    continue
                room, index = e.spawner_key.rsplit(':', 1)
                if w.rooms[room].group != group or e.location != room:
                    continue
                row = w.rooms[room].spawners[int(index)]
                if row.get('recovery', {}).get('minimum') == 1 and (not row.get('total_limit')) and (not row.get('on_death')):
                    break
            else:
                raise ValueError(city + ' lacks test habitat')
            targets[city] = (e, room, row)
        prior = {e.spawner_key: w.spawner_state[e.spawner_key]['total_spawned'] for e, _, _ in targets.values()}
        before = p.gold
        initial_time = max((w.spawner_state[e.spawner_key]['last_spawn_at'] for e, _, _ in targets.values()))
        for city, (e, room, row) in targets.items():
            w.move_entity(p.id, room, forced=True)
            combat.strike(w, p, e, power=10000, counter=False, wear=False)
            assert not e.alive

        def occupants(room, ident):
            return [v for v in w.entities_in_room(room) if v.alive and (not v.progress.get('companion_owner')) and (v.source_def == ident)]
        assert all((not occupants(room, e.source_def) for e, room, _ in targets.values()))
        with patch('time.monotonic', return_value=initial_time + 1):
            frontiers.population(w)
        assert all((not occupants(room, e.source_def) for e, room, _ in targets.values()))
        due = initial_time + max((row['cooldown'] for _, _, row in targets.values())) + 1
        with patch('time.monotonic', return_value=due):
            frontiers.population(w)
            frontiers.population(w)
        for e, room, _ in targets.values():
            group = occupants(room, e.source_def)
            assert len(group) == 1 and group[0].id != e.id and (group[0].gold == 0)
            assert w.spawner_state[e.spawner_key]['total_spawned'] == prior[e.spawner_key] + 1
        assert p.gold == before
        print('PASS: eight habitats lost one deer each; 0 before cooldown, 1 distinct deer after cooldown; second refresh created 0 excess deer, 0 gold generated. These nodes have no lifetime species reserve.')
def predation(path):
    with tempfile.TemporaryDirectory() as tmp:
        g = Game(path, Path(tmp), 'Predation').server
        w = g.world
        state = living.state(w)
        t0 = state['minute']
        random.seed(73)
        actors = [e for e in w.entities.values() if e.alive and (not e.is_player) and (not e.progress.get('companion_owner')) and (not e.progress.get('zoo_exhibit'))]
        species = {e.id: wildlife.species(w, e) for e in actors}
        lots = defaultdict(set)
        for e in actors:
            if species[e.id]:
                lots[e.location].add(species[e.id]['id'])
        counts = Counter()
        candidates = []
        for e in actors:
            s = species[e.id]
            allowed = set(s.get('prey_species', []))
            if not s or not allowed:
                continue
            counts['with_authored_prey'] += 1
            if s.get('consumption') == 'carnivore':
                counts['strict_carnivores'] += 1
            managed = 'husbandry' in living.details(w, e.location).get('facilities', [])
            if managed:
                counts['husbandry'] += 1
            if living.details(w, e.location).get('truce'):
                counts['truce'] += 1
            if not managed and (not living.details(w, e.location).get('truce')):
                counts['unprotected'] += 1
                if allowed & lots[e.location]:
                    counts['prey_here'] += 1
                if any((allowed & lots[dest] for dest in w.rooms[e.location].exits.values())):
                    counts['prey_near'] += 1
            if e.source_def == 'species_wolf_carrier':
                candidates.append(e)
        print('opening distribution', dict(counts), flush=True)
        attempts = []
        strike = combat.strike

        def watch(w, a, b, *args, **kw):
            hp = b.hp
            ret = strike(w, a, b, *args, **kw)
            attempts.append((a.id, b.id, hp, b.hp))
            return ret
        combat.strike = watch
        for step in range(30):
            state['minute'] = t0 + 30 * step
            society.produce(w)
            wildlife.advance(w)
        print('natural', len(attempts), 'attempts', sum((row[3] < row[2] for row in attempts)), 'damaging,', 'meals/hunts', state['wildlife']['meals'], state['wildlife']['hunts'], flush=True)
        wolf = next((e for e in actors if e.source_def == 'species_wolf_carrier' and e.alive))
        deer = next((e for e in actors if e.source_def == 'species_deer_carrier' and e.alive))
        room = next((r for r in w.rooms.values() if not r.entities and (not r.items) and (not r.exits) and (not living.details(w, r.id).get('facilities')) and (not living.details(w, r.id).get('truce')) and (not living.details(w, r.id).get('resources')) and (not living.details(w, r.id).get('workshop')) and (not living.details(w, r.id).get('property_unit_id'))))
        room = room.id
        for animal in (wolf, deer):
            w.move_entity(animal.id, room, forced=True)
        wolf.inventory[:] = [i for i in wolf.inventory if not wildlife.can_eat(w, wolf, i)]
        wolf.progress['feeding']['last_meal'] = state['minute'] - 360
        prev_hunts = state['wildlife']['hunts']
        oldcoins = wolf.gold
        start = time.monotonic()
        for step in range(12):
            state['minute'] += 30
            with patch('time.monotonic', return_value=start + 180 * (step + 1)):
                wildlife.advance(w)
            if not deer.alive:
                break
        trials = [row for row in attempts if row[:2] == (wolf.id, deer.id)]
        print('closed encounter', 'room', room, 'attacks', len(trials), 'damage', [(x[2], x[3]) for x in trials], 'prey_dead', not deer.alive, 'hunted_meals', state['wildlife']['hunts'] - prev_hunts, 'wolf_gold_delta', wolf.gold - oldcoins, 'meal', wolf.progress['feeding'], flush=True)
    assert not deer.alive and len(trials) > 0 and (state['wildlife']['hunts'] == prev_hunts + 1) and (wolf.gold == oldcoins)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=('wildlife-week', 'residents-day', 'residents-three-days', 'habitats', 'predation'))
    parser.add_argument('world', type=Path, help='Extracted .expanse world directory')
    opt = parser.parse_args()
    {'wildlife-week': feed, 'residents-day': check, 'residents-three-days': lambda p: check(p, 3), 'habitats': measure, 'predation': predation}[opt.scenario](opt.world.resolve())
