"""Persisted, opt-in objective baselines for creator-authored adventures.

Legacy quests keep their lifetime progress. New accepted-scope quests count only
successful activity after that acceptance, including subsequent repeat runs.
"""


def _counters(player, kind):
    key = {'visits': 'quest_visits', 'talks': 'quest_talks'}.get(kind, kind)
    return player.progress.get(key, {})


def visit(player, room_id):
    if player.is_player:
        counts = player.progress.setdefault('quest_visits', {})
        counts[room_id] = counts.get(room_id, 0) + 1


def talk(player, npc_id):
    counts = player.progress.setdefault('quest_talks', {})
    counts[npc_id] = counts.get(npc_id, 0) + 1


def action(player, key):
    counts = player.progress.setdefault('actions', {})
    counts[key] = counts.get(key, 0) + 1


def start(player, quest):
    if quest.get('progress_scope', 'lifetime') != 'accepted':
        return
    keys = {
        'visits': quest.get('visit_rooms', []),
        'talks': list(quest.get('talk_to', [])) + [r['npc'] for r in quest.get('witnesses', [])],
        'kills': quest.get('kills', {}),
        'actions': list(quest.get('actions', {})) + ['read:' + r['read_item'] for r in quest.get('witnesses', [])],
    }
    player.progress.setdefault('quest_runs', {})[quest['id']] = {
        kind: {key: _counters(player, kind).get(key, 0) for key in wanted}
        for kind, wanted in keys.items()
    }


def count(player, quest, kind, key):
    if quest.get('progress_scope', 'lifetime') != 'accepted':
        if kind == 'visits':
            return int(key in player.explored_rooms)
        if kind == 'talks':
            return int(key in player.progress.get('talked_to', []))
        return _counters(player, kind).get(key, 0)
    run = player.progress.get('quest_runs', {}).get(quest['id'])
    # Missing baselines must never retroactively credit an old save's activity.
    if run is None:
        if player.progress.get('quests', {}).get(quest['id']) != 'active':
            return 0
        start(player, quest)
        run = player.progress['quest_runs'][quest['id']]
    current = _counters(player, kind).get(key, 0)
    baseline = run.setdefault(kind, {}).setdefault(key, current)
    return max(0, current - baseline)


def witnessed(player, quest, row):
    return bool(count(player, quest, 'talks', row['npc']) or
                count(player, quest, 'actions', 'read:' + row['read_item']))


def status(world, player, quest_id):
    if world.quests.get(quest_id, {}).get('scope') == 'world':
        if quest_id in getattr(world, 'living_state', {}).get('completed_world', []):
            return 'complete'
    return player.progress.get('quests', {}).get(quest_id, 'available')
