"""Creator-authored quest chains and in-memory upgrades of accepted quests.

The world supplies every stage, destination, reward and legacy objective. This
module never invents content or writes a checkpoint. Old completed quests earn
nothing on upgrade; an old accepted quest keeps its objective baselines. Rewards
for credited stages are deferred until an explicit successful completion.
"""
from copy import deepcopy

KEY = 'quest_chain_runs'


def definition(quest):
    value = quest.get('quest_chain')
    return value if isinstance(value, dict) and type(value.get('version')) is int and value.get('version') == 1 else None


def invalidate(world):
    """Creator reloads normally replace the world; in-place editors may call this."""
    world._quest_chain_index = None


def _index(world):
    catalog = getattr(world, 'quests', {})
    cached = getattr(world, '_quest_chain_index', None)
    if cached is None or cached[0] is not catalog:
        finals = {qid: q for qid, q in catalog.items()
                  if definition(q) and q.get('quest_split_migration')}
        cached = (catalog, object(), finals)
        world._quest_chain_index = cached
    return cached[1], cached[2]


def _dirty(world, player):
    world.dirty_players = getattr(world, 'dirty_players', set()) | {player.id}


def _run(player, chain):
    return player.progress.get(KEY, {}).get(chain['id'])


def _new_run(final, *, legacy=False, cycle=1):
    chain = definition(final)
    return dict(version=1, revision=final.get('quest_split_migration', {}).get('revision', ''),
                stages=list(chain['stages']), cycle=cycle, legacy=legacy,
                completed=[], pending_rewards=[], active=None, finished=False)


def _track(player, old_id, new_id):
    selected = player.progress.get('selected_quests')
    if isinstance(selected, list) and old_id in selected:
        player.progress['selected_quests'] = list(dict.fromkeys(
            new_id if qid == old_id else qid for qid in selected if qid != old_id or new_id))


def _copy_sources(world, player, old_id, new_id):
    """Only a real previously encountered source may disclose a new chain head."""
    sources = player.progress.get('quest_sources', {})
    changed = False
    for row in list(sources.get(old_id, [])):
        if not isinstance(row, dict):
            continue
        catalog = world.npcs if row.get('kind') == 'npc' else world.items if row.get('kind') == 'item' else {}
        source = catalog.get(row.get('id'), {})
        if new_id in source.get('knowledge', {}).get('quests', []):
            target = sources.setdefault(new_id, [])
            if row not in target:
                target.append(deepcopy(row))
                changed = True
    return changed


def _objectives_done(player, quest):
    from engine import interface_tours, quest_progress as qp
    if interface_tours.blocked(player, quest):
        return False
    for field, kind in (('kills', 'kills'), ('actions', 'actions')):
        if any(qp.count(player, quest, kind, key) < count for key, count in quest.get(field, {}).items()):
            return False
    if any(not qp.count(player, quest, 'visits', rid) for rid in quest.get('visit_rooms', [])):
        return False
    if any(not qp.count(player, quest, 'talks', nid) for nid in quest.get('talk_to', [])):
        return False
    if any(not qp.witnessed(player, quest, row) for row in quest.get('witnesses', [])):
        return False
    if quest.get('escort') and not player.progress.get('escort_arrivals', {}).get(quest['id']):
        return False
    # An explicit old guide exemption remains an exemption. An otherwise empty
    # travel stage needs evidence that the player has actually reached its stop.
    has_goal = any(quest.get(key) for key in ('kills', 'actions', 'visit_rooms', 'talk_to', 'witnesses', 'escort', 'interface_tour'))
    return bool(has_goal or player.location == quest.get('turn_in_room'))


def migrate(world, player):
    """Idempotent on bind/read; modify only the live character, never durable saves."""
    if not player or not player.is_player:
        return
    token, finals = _index(world)
    if getattr(player, '_quest_chain_token', None) is token:
        return
    player._quest_chain_token = token
    from engine import quest_progress as qp, interface_tours
    pr = player.progress
    statuses = pr.get('quests', {})
    relevant = set(statuses) | set(pr.get('quest_sources', {}))
    changed = False
    for final_id in relevant & finals.keys():
        final = finals[final_id]
        chain = definition(final)
        stages = [world.quests[qid] for qid in chain['stages']]
        old_status = statuses.get(final_id)
        changed = _copy_sources(world, player, final_id, chain['stages'][0]) or changed
        if old_status not in ('active', 'complete') or _run(player, chain) is not None:
            continue
        snapshot = final['quest_split_migration']['original']
        run = _new_run(final, legacy=old_status == 'active')
        pr.setdefault(KEY, {})[final_id] = run
        # Existing first-completion milestones remain milestones for new stage
        # IDs too, so a repeat cycle cannot reclassify old work as first-time XP.
        advancement = pr.get('advancement_v1', {})
        earned = advancement.get('earned', {})
        if earned.get('quest:' + final_id):
            for quest in stages[:-1]:
                earned['quest:' + quest['id']] = True
                last = advancement.get('practice_last', {})
                if 'quest:' + final_id in last:
                    last['quest:' + quest['id']] = last['quest:' + final_id]
        guide = next((q for q in stages if q.get('interface_tour')), None)
        old_guide = pr.get(interface_tours.KEY, {}).get(final_id)
        if guide and isinstance(old_guide, dict) and guide['id'] != final_id:
            pr[interface_tours.KEY][guide['id']] = deepcopy(old_guide)
            pr[interface_tours.KEY].pop(final_id, None)
            if pr.get(interface_tours.SELECTED) == final_id:
                pr[interface_tours.SELECTED] = guide['id']
        if old_status == 'complete':
            for quest in stages[:-1]:
                statuses[quest['id']] = 'complete'
            run['completed'] = list(chain['stages'])
            run['finished'] = True
            changed = True
            continue
        if snapshot.get('progress_scope', 'lifetime') == 'accepted':
            if final_id not in pr.get('quest_runs', {}):
                qp.start(player, snapshot)
            baseline = deepcopy(pr['quest_runs'][final_id])
            run['baseline'] = baseline
            for quest in stages:
                pr.setdefault('quest_runs', {})[quest['id']] = deepcopy(baseline)
        if pr.get('escort_arrivals', {}).get(final_id):
            for quest in stages:
                if quest.get('escort'):
                    pr['escort_arrivals'][quest['id']] = deepcopy(pr['escort_arrivals'][final_id])
        # The old final turn-in was never rewarded. It remains an explicit
        # completion, even if every travel/activity objective already succeeded.
        statuses.pop(final_id, None)
        for quest in stages[:-1]:
            qid = quest['id']
            if _objectives_done(player, quest):
                statuses[qid] = 'complete'
                run['completed'].append(qid)
                run['pending_rewards'].append(qid)
        active = next(qid for qid in chain['stages'] if qid not in run['completed'])
        statuses[active] = 'active'
        run['active'] = active
        _track(player, final_id, active)
        changed = True
    if changed:
        _dirty(world, player)


def blocked(world, player, quest, *, migrate_player=True):
    chain = definition(quest)
    if not chain:
        return ''
    if migrate_player:
        migrate(world, player)
    final = world.quests[chain['id']]
    if final.get('scope') == 'world' and chain['id'] in getattr(world, 'living_state', {}).get('completed_world', []):
        return 'This shared-world outcome has already been completed.'
    run = _run(player, chain)
    from engine import earned_start
    qid = quest['id']
    stages = earned_start.omit_stage(player, chain['id'], chain['stages'])
    if qid not in stages:
        return 'This former training request is not part of your in-world start.'
    index = stages.index(qid)
    if run is None:
        return '' if index == 0 else 'Begin with the first quest in this chain.'
    if run.get('finished'):
        if not final.get('repeatable'):
            return ''  # Normal completed-quest handling applies; no new rewards.
        if chain['index']:
            return 'Begin a new run with the first quest in this chain.'
        minute = getattr(world, 'living_state', {}).get('minute', 0)
        if minute - player.progress.get('quest_times', {}).get(chain['id'], -100000) < final.get('cooldown_minutes', 1500):
            return 'This work is not available again yet.'
        return ''
    completed = set(run.get('completed', []))
    if qid in completed:
        return 'This stage is already finished for the current chain.'
    if any(sid not in completed for sid in stages[:index]):
        return 'Complete the earlier quests in this chain first.'
    if run.get('active') and run['active'] != qid:
        return 'Finish the active quest in this chain first.'
    return ''


def start(world, player, quest):
    """An explicit accepted stage starts a run; future stages are not auto-offered."""
    from engine import quest_progress as qp
    chain = definition(quest)
    if not chain:
        qp.start(player, quest)
        return
    migrate(world, player)
    final = world.quests[chain['id']]
    run = _run(player, chain)
    if run is None or run.get('finished'):
        cycle = run.get('cycle', 0) + 1 if run else 1
        run = _new_run(final, cycle=cycle)
        player.progress.setdefault(KEY, {})[chain['id']] = run
        # Keep the old final completion as history for external unlocks until
        # that final quest is explicitly accepted again. Per-cycle gates use
        # this run's completed ledger rather than the retained history.
        for qid in chain['stages'][:-1]:
            for key in ('quests', 'quest_runs', 'quest_times', 'escort_arrivals'):
                player.progress.get(key, {}).pop(qid, None)
    qp.start(player, quest)
    run['active'] = quest['id']


def completed(world, player, quest):
    """Called only after successful explicit turn-in and its normal rewards."""
    chain = definition(quest)
    if not chain:
        return ''
    run = _run(player, chain)
    if run is None:
        return ''
    qid = quest['id']
    if qid not in run['completed']:
        run['completed'].append(qid)
    run['active'] = None
    messages = []
    pending = list(run.get('pending_rewards', []))
    if pending:
        from engine import progression
        gold = 0
        awards = []
        for credited in pending:
            row = world.quests[credited]
            gold += row.get('reward_gold', 0)
            text = progression.quest(world, player, row)
            if text:
                awards.append(text)
        player.gold += gold
        run['pending_rewards'] = []
        messages.append('Previously finished steps credited: ' + str(len(pending)) +
                        ('; ' + str(gold) + ' gold' if gold else '') + '.')
        messages.extend(awards)
    from engine import earned_start
    stages = earned_start.omit_stage(player, chain['id'], chain['stages'])
    next_id = next((sid for sid in stages if sid not in run['completed']), None)
    if next_id is None:
        run['finished'] = True
        run.pop('baseline', None)
    elif run.get('legacy'):
        # The player already accepted the original whole quest; preserve that
        # acceptance instead of forcing them back to a newly inserted source.
        player.progress['quests'][next_id] = 'active'
        run['active'] = next_id
        _track(player, qid, next_id)
        next_quest = world.quests[next_id]
        messages.append('Your accepted quest continues: ' + next_quest['name'] + '. ' + next_quest.get('description', ''))
    _dirty(world, player)
    return '\n'.join(messages)


def validate(data):
    """Validate authoring and migration references without changing the records."""
    issues = []
    quests = {q['id']: q for q in data.get('quest', []) if isinstance(q, dict) and 'id' in q}
    rooms = {r['id'] for r in data.get('room', []) if isinstance(r, dict) and 'id' in r}
    items = {r['id']: r for r in data.get('item', []) if isinstance(r, dict) and 'id' in r}
    for qid, quest in quests.items():
        raw = quest.get('quest_chain', {})
        migration = quest.get('quest_split_migration', {})
        if not isinstance(raw, dict) or not isinstance(migration, dict):
            issues.append(qid + ': quest_chain and quest_split_migration must be objects'); continue
        if not raw:
            if migration:
                issues.append(qid + ': quest_split_migration requires a quest_chain')
            continue
        where = qid + ': quest_chain'
        if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw.get('version') != 1:
            issues.append(where + ' requires version 1'); continue
        stages = raw.get('stages')
        if (not isinstance(stages, list) or not 2 <= len(stages) <= 64 or
                any(not isinstance(sid, str) or not sid for sid in stages) or len(set(stages)) != len(stages)):
            issues.append(where + ' requires 2–64 unique quest IDs'); continue
        index = raw.get('index')
        if type(index) is not int or not 0 <= index < len(stages) or stages[index] != qid:
            issues.append(where + ' index must identify this quest')
        if raw.get('id') != stages[-1]:
            issues.append(where + ' id must be the final quest ID')
        if any(sid not in quests for sid in stages):
            issues.append(where + ' references a missing stage')
        destination = raw.get('destination')
        if not isinstance(destination, str) or destination not in rooms or destination != quest.get('turn_in_room'):
            issues.append(where + ' destination must be its existing turn-in room')
        source = raw.get('source_item')
        if source and (not isinstance(source, str) or source not in items or not items[source].get('read_text')):
            issues.append(where + ' source_item must be a readable item')
        for n, sid in enumerate(stages):
            other = quests.get(sid, {}).get('quest_chain', {})
            if not isinstance(other, dict) or other.get('id') != raw.get('id') or other.get('stages') != stages or other.get('index') != n:
                issues.append(where + ' stages must agree on their chain and order'); break
        if not migration:
            continue
        where = qid + ': quest_split_migration'
        if qid != raw.get('id'):
            issues.append(where + ' belongs only on the original final quest')
        if (not isinstance(migration, dict) or type(migration.get('version')) is not int or migration.get('version') != 1
                or not isinstance(migration.get('revision'), str) or not migration.get('revision')):
            issues.append(where + ' requires version 1 and a revision'); continue
        original = migration.get('original')
        if not isinstance(original, dict) or original.get('id') != qid:
            issues.append(where + ' requires the original quest snapshot with the same ID'); continue
        if original.get('progress_scope', 'lifetime') not in ('lifetime', 'accepted'):
            issues.append(where + ' has an invalid original progress scope')
        for key in ('visit_rooms', 'talk_to'):
            if not isinstance(original.get(key, []), list) or any(not isinstance(v, str) for v in original.get(key, [])):
                issues.append(where + ' has invalid original ' + key)
        for key in ('kills', 'actions', 'required_items'):
            value = original.get(key, {})
            if not isinstance(value, dict) or any(not isinstance(k, str) or type(v) is not int or v < 1 for k, v in value.items()):
                issues.append(where + ' has invalid original ' + key)
        witnesses = original.get('witnesses', [])
        if (not isinstance(witnesses, list) or any(not isinstance(v, dict) or not isinstance(v.get('npc'), str)
                                                  or not isinstance(v.get('read_item'), str) for v in witnesses)):
            issues.append(where + ' has invalid original witnesses')
        from engine import interface_tours
        issues.extend(interface_tours.validate({'quest': [original]}))
    return issues
