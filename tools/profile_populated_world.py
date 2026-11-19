#!/usr/bin/env python3
"""Profile a real isolated GameServer without opening a network listener."""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import random
import resource
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))


def run(path, *, ticks=3, profile_path=None, seed=119, profile_first=False):
    from engine import loader, living, persistence
    from server import game_server
    random.seed(seed)
    isolated = tempfile.TemporaryDirectory(prefix='expanse-profile-')
    folder = Path(isolated.name)
    with patch.object(game_server, 'build_world', lambda: loader.build_world(path)), \
            patch.object(game_server, 'SAVE_DIR', folder / 'save'), \
            patch.object(game_server, 'WORLD_STATE_PATH', folder / 'world_state.json'), \
            patch.object(loader, 'GAMES_DIR', folder / 'games'), \
            patch.object(persistence, 'DB_PATH', folder / 'world.db'):
        started = time.perf_counter()
        server = game_server.GameServer(mode='single')
        startup = time.perf_counter() - started
    world = server.world
    count = len(world.entities)
    timings = []
    profiler = cProfile.Profile()
    if profile_first:
        profiler.enable();living.advance(world, 1);profiler.disable()
    for _ in range(ticks):
        started = time.perf_counter();living.advance(world, 1)
        timings.append(time.perf_counter() - started)
    if not profile_first:
        profiler.enable();living.advance(world, 1);profiler.disable()
    if profile_path:
        target = Path(profile_path);target.parent.mkdir(parents=True, exist_ok=True);profiler.dump_stats(str(target))
    result = dict(world=str(Path(path).resolve()), seed=seed, rooms=len(world.rooms),
                  entities_initial=count, entities_final=len(world.entities), startup_seconds=round(startup, 4),
                  tick_seconds=[round(value, 4) for value in timings],
                  peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
                  minute=living.state(world)['minute'], profile_tick=1 if profile_first else ticks + 1,
                  timed_ticks=list(range(2, ticks + 2)) if profile_first else list(range(1, ticks + 1)),
                  profile_path=str(profile_path) if profile_path else None)
    print(json.dumps(result, indent=2))
    pstats.Stats(profiler).strip_dirs().sort_stats('cumulative').print_stats(30)
    server.db.close();server.checkpoint_db.close();isolated.cleanup()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', required=True)
    parser.add_argument('--ticks', type=int, default=3)
    parser.add_argument('--profile-path')
    parser.add_argument('--seed', type=int, default=119)
    parser.add_argument('--profile-first', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.ticks <= 10:parser.error('--ticks must be 1–10')
    run(args.world, ticks=args.ticks, profile_path=args.profile_path, seed=args.seed, profile_first=args.profile_first)
