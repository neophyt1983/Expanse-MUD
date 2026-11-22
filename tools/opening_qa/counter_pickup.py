"""Check local pickup, permissions, changing routes and checkpoint recovery."""
import argparse
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import household_provisions as provisions, living, meal_counters, needs_market
from private_game import Game


def run(path):
    with tempfile.TemporaryDirectory() as directory:
        def open_game():
            return Game(path.resolve(), Path(directory), 'Pickup regression').server
        server = open_game()
        world = server.world
        s = living.state(world)
        cfg = provisions.config(world)
        city = 'Starfall'
        rule = cfg['cities'][city]
        minute = cfg['issue_minute']
        s['minute'] = minute
        provisions.advance(world, minute-1, minute)
        ledger = s[provisions.KEY][city]
        lots = ledger['meal_counters']
        meal = rule['meal_item']
        wallet_before = sum(e.gold for e in world.entities.values())
        recipient = next(e for e in world.entities.values() if e.source_def == 'gen_star_person_1')
        recipient.inventory.clear()
        needs_market.state(recipient).update(hunger=89, thirst=90)
        s['minute'] = 1021
        inn = rule['kitchen']
        neighbor = next(room for room in world.rooms[inn].exits.values() if room in world.rooms and inn in world.rooms[room].exits.values())
        world.move_entity(recipient.id, neighbor)
        assert meal_counters.meal_break(world, recipient) and recipient.location == inn
        count = sum(lots.values())
        assert meal_counters.meal_break(world, recipient)
        assert sum(lots.values()) == count-2 and recipient.inventory.count(meal) == 1
        assert needs_market.state(recipient)['hunger'] == 54 and needs_market.state(recipient)['thirst'] == 90
        assert not meal_counters.meal_break(world, recipient)
        assert ledger['collected'] == 2
        assert sum(e.gold for e in world.entities.values()) == wallet_before
        assert ledger['cumulative']['counter_delivery'] == sum(lots.values()) + ledger['collected']

        # On-duty staff, foreign actors, unavailable stock and changed exits.
        remaining = list(recipient.inventory)
        recipient.inventory.clear()
        world.move_entity(recipient.id, neighbor)
        s['minute'] = 901
        assert not meal_counters.meal_break(world, recipient) and recipient.location == neighbor
        s['minute'] = 1021
        previous = recipient.group_id
        recipient.group_id = 'other-city'
        assert not meal_counters.meal_break(world, recipient)
        recipient.group_id = previous
        options = meal_counters.options(world, recipient, cfg['cities'])
        assert any(counter == inn and dest == inn for _, _, counter, direction, dest in options)
        exits = dict(world.rooms[neighbor].exits)
        try:
            world.rooms[neighbor].exits.clear()
            assert not meal_counters.meal_break(world, recipient) and recipient.location == neighbor
        finally:
            world.rooms[neighbor].exits.update(exits)
        world.move_entity(recipient.id, inn)
        saved = dict(lots)
        for counter in lots:
            lots[counter] = 0
        assert not meal_counters.meal_break(world, recipient)
        lots.update(saved)
        recipient.inventory[:] = remaining

        # Persist a partially collected account, then replay the previous daily issue.
        collected = ledger['collected']
        server._save_players_and_world()
        server.checkpoint_db.close()
        server.db.close()
        server = open_game()
        world = server.world
        restored = living.state(world)[provisions.KEY][city]
        assert restored['meal_counters'] == saved and restored['collected'] == collected
        reloaded = world.entities[recipient.id]
        assert reloaded.inventory == remaining and reloaded.inventory.count(meal) == 1
        assert needs_market.state(reloaded)['hunger'] == 54
        provisions.advance(world, minute-1, minute)
        assert restored['meal_counters'] == saved and restored['collected'] == collected
        final = restored['history'][-1]
        assert final['opening'] + final['cooked'] == final['issued'] + final['closing'] + final['market_delivery'] + final['counter_delivery']
        # Cold RC4 accounts without pickup columns keep their old history readable.
        for key in ('meal_counters', 'collected', 'cumulative'):
            restored.pop(key)
        final.pop('counter_delivery')
        context = SimpleNamespace(world=world, room=world.rooms[inn])
        assert 'household provision account' in provisions.report(context, city)
        assert 'cumulative' not in restored and 'meal_counters' not in restored
        tomorrow = minute + provisions.DAY
        provisions.advance(world, tomorrow-1, tomorrow)
        assert restored['cumulative']['since'] == 1
        assert 'Active pickup counters' in provisions.report(context, city)
        server.checkpoint_db.close()
        server.db.close()
        print('PASS legacy account read and next issue, finite physical pickup, no gold transfer, thirst preserved, no double claim, on-duty protection, faction, edited exits, empty counters, cold checkpoint and no daily replay.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world', type=Path)
    run(parser.parse_args().world)
