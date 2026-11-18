#!/usr/bin/env python3
"""Measure single-player application packet sizes in a disposable world COPY.

No host-mode/shared MMO, live accounts, manual Save or production data writes.
The socket is an in-process transport double: sizes exclude wire compression,
frames and TLS. Never use this as a player-per-hour or Render billing estimate.
"""
import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import loader, persistence
from server import game_server


class Socket:
    remote_address = None

    def __init__(self, packets):
        self.commands = packets
        self.sent = []
        self.samples = []

    async def send(self, raw):
        row = json.loads(raw)
        self.sent.append({'type': row.get('type'), 'bytes': len(raw.encode()),
                          **({'step_taken': row['step_taken']} if 'step_taken' in row else {}),
                          'pixel_asset_bytes': len(json.dumps(row.get('visual', {}).get('pixel_assets', {})).encode()) if row.get('type') == 'map' else 0})

    async def close(self, **kwargs):
        pass

    async def __aiter__(self):
        for index, packet in enumerate(self.commands):
            begin = len(self.sent)
            yield json.dumps(packet)
            frames = self.sent[begin:]
            self.samples.append({'step': index, 'kind': 'resume' if index == 0 else 'tagged_move' if packet.get('movement_id') else 'look',
                                 'json_response_bytes': sum(row['bytes'] for row in frames),
                                 'packets': frames})


async def measure(source):
    if not all((source / name).is_file() for name in ('metadata.json', 'rooms.json')):
        raise ValueError('Choose an extracted authored world containing metadata.json and rooms.json.')
    with tempfile.TemporaryDirectory(prefix='expanse-packet-audit-') as temporary:
        root = Path(temporary)
        target = root / 'games' / 'fixture'
        if source.is_symlink() or any(path.is_symlink() for path in source.rglob('*')):
            raise ValueError('Use a regular extracted authored world without linked files.')
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('save', '__pycache__', '.git', 'world.db*', 'world_state*.json*'))
        loader.GAMES_DIR = target.parent
        loader.set_game_dir(target)
        with patch.object(game_server, 'SAVE_DIR', root / 'save'), patch.object(persistence, 'DB_PATH', root / 'save/world.db'):
            server = game_server.GameServer(mode='single')
            try:
                world = server.world
                faction = next((key for key in ('good_guys',) if key in world.groups),
                               next(key for key, row in world.groups.items() if row.get('visibility') == 'playable'))
                created = await server.create_character({'first_name': 'Packet', 'last_name': 'Probe',
                    'race': 'human', 'class': 'mage', 'faction': faction})
                actor = world.entities[created['player_id']]
                initial_map_bytes = len(json.dumps(dict(type='map', **server.map_for(actor.id))).encode())
                direction = next(iter(world.rooms[actor.location].exits))
                socket = Socket([{'command': 'resume ' + actor.id}, {'command': 'look'},
                                 {'command': 'go ' + direction, 'movement_id': 'probe-step-1'}, {'command': 'look'}])
                await server.handle(socket)
                assert any(row['type'] == 'map' for row in socket.sent), 'Tagged movement must deliver a map.'
                assert any(row.get('step_taken') is True for row in socket.sent), 'The movement probe must move.'
                assert not (root / 'save/world.db').exists(), 'The probe must not publish a save.'
                counts = Counter(row['type'] for row in socket.sent)
                return {'mode': 'single', 'passed': True, 'source_world_copied': True,
                        'production_world_changed': False, 'manual_save_called': False,
                        'initial_map_constructed_json_bytes': initial_map_bytes,
                        'packet_counts': dict(counts), 'samples': socket.samples,
                        'scope': 'real GameServer.handle/map_for, temporary world and in-process socket; four actions only; no lifecycle timer',
                        'limitations': ['Not a live network trace or multiplayer/concurrency test',
                                        'No frame, compression, TLS, idle-period or whole-session measurement',
                                        'Generated fixture state can vary; no per-hour or invoice estimate']}
            finally:
                server.db.close()
                server.checkpoint_db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError('Choose a new report path; existing files are never replaced.')
    report = asyncio.run(measure(args.world.resolve(strict=True)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'packet_counts': report['packet_counts']}))


if __name__ == '__main__':
    main()
