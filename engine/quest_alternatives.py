"""Single-payout alternatives to Creator-authored interface-guide quests.

The world supplies the actual alternative, objectives, rewards and sources.
Choosing it only accepts work; ordinary turn-in earns the shared payout. All
bookkeeping lives in character progress and uses the existing explicit Save.
"""
from collections import Counter
from hashlib import sha256
import json


KEY = 'quest_alternatives'


def reference(quest):
    tour = quest.get('interface_tour')
    value = tour.get('alternative_quest') if isinstance(tour, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def validate(data):
    """Optional references are checked together with both ordinary definitions."""
    quests = {q['id']: q for q in data.get('quest', [])
              if isinstance(q, dict) and isinstance(q.get('id'), str)}
    issues, owners = [], {}
    for qid, quest in quests.items():
        tour = quest.get('interface_tour')
        if not isinstance(tour, dict) or 'alternative_quest' not in tour:
            continue
        aid = reference(quest)
        label = qid + ': interface_tour alternative_quest '
        if aid is None or aid not in quests:
            issues.append(label + 'must name an existing quest'); continue
        if aid == qid:
            issues.append(label + 'cannot refer to itself'); continue
        if aid in owners:
            issues.append(label + 'is already an alternative for ' + owners[aid])
        owners[aid] = qid
        alternative = quests[aid]
        for member in (quest, alternative):
            if member.get('scope', 'character') != 'character' or member.get('repeatable'):
                issues.append(label + 'requires two nonrepeatable character quests')
            if any(member.get(key) for key in ('reputation', 'character_flags', 'world_flags', 'world_effects')):
                issues.append(label + 'supports XP, gold and item rewards only')
            relationship = member.get('relationship_quest', {})
            if not isinstance(relationship, dict) or relationship.get('enabled'):
                issues.append(label + 'cannot use a relationship quest')
            if type(member.get('reward_xp')) is not int or not 0 <= member['reward_xp'] <= 10000:
                issues.append(label + 'requires explicit integer reward_xp from 0 to 10000 on both quests')
            if type(member.get('reward_gold', 0)) is not int or member.get('reward_gold', 0) < 0:
                issues.append(label + 'requires nonnegative integer gold rewards')
            if not isinstance(member.get('reward_items', []), list) or any(
                    not isinstance(iid, str) for iid in member.get('reward_items', [])):
                issues.append(label + 'requires item IDs in reward_items')
            prerequisites = member.get('prerequisites', [])
            if not isinstance(prerequisites, list) or any(not isinstance(key, str) for key in prerequisites):
                issues.append(label + 'requires quest IDs in prerequisites')
        if quest.get('reward_xp') != alternative.get('reward_xp'):
            issues.append(label + 'must preserve the exact XP payout')
        if quest.get('reward_gold', 0) != alternative.get('reward_gold', 0):
            issues.append(label + 'must preserve the exact gold payout')
        rewards = [member.get('reward_items', []) for member in (quest, alternative)]
        if all(isinstance(items, list) and all(isinstance(i, str) for i in items) for items in rewards):
            if Counter(rewards[0]) != Counter(rewards[1]):
                issues.append(label + 'must preserve every reward item and its quantity')
        if any(alternative.get(key) for key in ('interface_tour', 'quest_chain', 'quest_split_migration')):
            issues.append(label + 'replacement must be an ordinary quest outside a chain')
        if alternative.get('escort'):
            issues.append(label + 'replacement cannot require an escort pickup')
        if alternative.get('progress_scope') != 'accepted':
            issues.append(label + 'replacement must count objectives after acceptance')
        if not any(alternative.get(key) for key in ('required_items', 'kills', 'actions',
                                                   'visit_rooms', 'talk_to', 'witnesses', 'escort')):
            issues.append(label + 'replacement requires an ordinary quest objective')
        # Dependencies on a later stage or the original would strand a player
        # after choosing the alternative, even through an indirect prerequisite.
        prerequisites = alternative.get('prerequisites', [])
        pending = [key for key in prerequisites if isinstance(key, str)] if isinstance(prerequisites, list) else []
        seen = set()
        while pending:
            dependency = pending.pop()
            if dependency == qid:
                issues.append(label + 'replacement cannot require the original guide'); break
            if dependency in seen or dependency not in quests:
                continue
            seen.add(dependency)
            parents = quests[dependency].get('prerequisites', [])
            if isinstance(parents, list):
                pending.extend(key for key in parents if isinstance(key, str))
        chain = quest.get('quest_chain')
        if isinstance(chain, dict) and isinstance(chain.get('id'), str) and quests.get(chain['id'], {}).get('repeatable'):
            issues.append(label + 'cannot replace a stage in a repeatable chain')
    return issues


def invalidate(world):
    world._quest_alternative_index = None


def _index(world):
    catalog = world.quests
    cached = getattr(world, '_quest_alternative_index', None)
    if cached is None or cached[0] is not catalog:
        originals = {qid: q for qid, q in catalog.items() if reference(q) in catalog}
        reverse = {reference(q): qid for qid, q in originals.items()}
        cached = (catalog, originals, reverse)
        world._quest_alternative_index = cached
    return cached[1], cached[2]


def selected(player, quest_id):
    records = player.progress.get(KEY, {})
    row = records.get(quest_id) if isinstance(records, dict) else None
    return row if (isinstance(row, dict) and type(row.get('version')) is int and row.get('version') == 1
                   and isinstance(row.get('quest_id'), str)) else None


def reward_id(world, quest):
    """Both paths share the original milestone; the quest's own amount remains."""
    return _index(world)[1].get(quest['id'], quest['id'])


def _reward(world, quest):
    from engine import progression
    cfg = progression.config(world)
    return {'xp': quest.get('reward_xp', cfg['quest_xp']) if cfg['enabled'] else 0,
            'gold': quest.get('reward_gold', 0),
            'items': [{'id': iid, 'name': world.items.get(iid, {}).get('name', iid), 'quantity': count}
                      for iid, count in sorted(Counter(quest.get('reward_items', [])).items())]}


def _revision(world, original, replacement):
    value = {'original': original, 'replacement': replacement,
             'rewards': [_reward(world, original), _reward(world, replacement)]}
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).hexdigest()[:24]


def _source_known(world, player, quest_id):
    rows = player.progress.get('quest_sources', {}).get(quest_id, [])
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        catalog = world.npcs if row.get('kind') == 'npc' else world.items if row.get('kind') == 'item' else {}
        source = catalog.get(row.get('id'), {})
        if quest_id in source.get('knowledge', {}).get('quests', []):
            return True
    return False


def _settled(world, player, original):
    qid = original['id']; statuses = player.progress.get('quests', {})
    if statuses.get(qid) == 'complete':
        return True
    if player.progress.get('advancement_v1', {}).get('earned', {}).get('quest:' + qid):
        return True
    chain = original.get('quest_chain')
    if isinstance(chain, dict):
        run = player.progress.get('quest_chain_runs', {}).get(chain.get('id'))
        if isinstance(run, dict):
            if qid in run.get('completed', []) or qid in run.get('pending_rewards', []):
                return True
        elif statuses.get(chain.get('id')) in ('active', 'complete'):
            # Binding a resumed character performs the legacy migration. A
            # preview must not perform it itself, or promise an already credited
            # stage to a not-yet-bound old character.
            return True
    return False


def _reason(world, player, original, replacement):
    from engine import living
    qid, aid = original['id'], replacement['id']
    statuses = player.progress.get('quests', {})
    if not player.alive or player.progress.get('permanently_dead'):
        return 'Return to play before choosing a different quest.'
    if selected(player, qid) is not None or statuses.get(qid) == 'replaced':
        return 'You already chose ' + replacement['name'] + '. The interface guide remains optional.'
    if _settled(world, player, original):
        return 'This guide stage is already completed or credited. Its reward cannot be claimed again.'
    if statuses.get(aid) in ('active', 'complete', 'replaced'):
        return 'The replacement quest is already recorded; it cannot be accepted again.'
    if player.progress.get('advancement_v1', {}).get('earned', {}).get('quest:' + aid):
        return 'The replacement reward has already been recorded.'
    replacement_room = replacement.get('offer_room')
    if replacement_room and replacement_room != player.location:
        room = world.rooms.get(replacement_room)
        return 'Choose the replacement quest at ' + (room.name if room else replacement_room) + '.'
    if statuses.get(qid) != 'active':
        room = original.get('offer_room')
        if room and room != player.location:
            return 'Choose this quest at ' + world.rooms[room].name + '.'
        if not _source_known(world, player, qid):
            return 'Read or discuss the original request before choosing its alternative.'
    for quest in (original, replacement):
        reason = living.quest_blocked(world, player, quest, alternatives=False, readonly=True)
        if reason:
            return reason
    return ''


def preview(world, player, quest_id):
    """Read only. In particular, do not migrate, initialize progress, or save."""
    if not player or not player.is_player:
        raise ValueError('Enter your character before choosing a quest.')
    if not isinstance(quest_id, str):
        raise ValueError('Choose an interface guide with an alternative quest.')
    original = _index(world)[0].get(quest_id)
    if original is None:
        raise ValueError('This interface guide does not offer another quest.')
    status = player.progress.get('quests', {}).get(quest_id)
    if status not in ('active', 'complete', 'replaced'):
        if not _source_known(world, player, quest_id):
            raise ValueError('Read or discuss the original request before choosing its alternative.')
        if original.get('offer_room') and original['offer_room'] != player.location:
            raise ValueError('Return to the original request location to review its alternative.')
    replacement = world.quests[reference(original)]
    reason = _reason(world, player, original, replacement)
    return {'quest_id': quest_id, 'revision': _revision(world, original, replacement),
            'available': not reason, 'reason': reason,
            'original': {'id': quest_id, 'name': original['name'], 'reward': _reward(world, original)},
            'replacement': {'id': replacement['id'], 'name': replacement['name'],
                            'description': replacement.get('description', ''),
                            'reward': _reward(world, replacement)}}


def affordance(world, player, quest):
    aid = reference(quest)
    if aid is None:
        return {}
    # Maps need only availability, not a freshly serialized definition digest.
    # The full preview is produced on demand when the player opens the choice.
    available = False
    if player and player.is_player and aid in world.quests:
        status = player.progress.get('quests', {}).get(quest['id'])
        known = status in ('active', 'complete', 'replaced') or (
            _source_known(world, player, quest['id']) and
            (not quest.get('offer_room') or quest['offer_room'] == player.location))
        available = known and not _reason(world, player, quest, world.quests[aid])
    return {'alternative_quest': aid, 'alternative_available': available}


def _track(player, old_id, new_id):
    tracked = player.progress.get('selected_quests')
    if isinstance(tracked, list) and old_id in tracked:
        player.progress['selected_quests'] = list(dict.fromkeys(
            new_id if qid == old_id else qid for qid in tracked))


def choose(world, player, quest_id, revision):
    """Explicit acceptance, never a completion, reward, or disk checkpoint."""
    proposal = preview(world, player, quest_id)
    existing = selected(player, quest_id)
    aid = proposal['replacement']['id']
    if existing is not None and existing['quest_id'] == aid and revision in (existing.get('revision'), proposal['revision']):
        return {'quest_id': quest_id, 'alternative_quest_id': aid,
                'accepted': True, 'already_selected': True}
    if not isinstance(revision, str) or revision != proposal['revision']:
        raise ValueError('This quest choice changed. Review its rewards again before choosing.')
    if not proposal['available']:
        raise ValueError(proposal['reason'])
    from engine import interface_tours, knowledge, quest_chains, quest_progress
    original, replacement = world.quests[quest_id], world.quests[aid]
    pr = player.progress
    chain = quest_chains.definition(original)
    if pr.get('quests', {}).get(quest_id) != 'active' or (
            chain and chain['id'] not in pr.get(quest_chains.KEY, {})):
        quest_chains.start(world, player, original)
    # The original stage stays active inside its parent chain until the real
    # replacement is turned in. Only its visible/raw quest status changes.
    pr.setdefault(KEY, {})[quest_id] = {'version': 1, 'quest_id': aid, 'revision': proposal['revision']}
    pr.setdefault('quests', {})[quest_id] = 'replaced'
    quest_progress.start(player, replacement)
    pr['quests'][aid] = 'active'
    guide = pr.setdefault(interface_tours.KEY, {}).setdefault(quest_id, {
        'acknowledged': [], 'paused': True, 'required': False, 'satisfied': False})
    guide['paused'], guide['required'] = True, False
    pr[interface_tours.SELECTED] = quest_id
    _track(player, quest_id, aid)
    knowledge.quest(world, player, replacement)
    world.dirty_players = getattr(world, 'dirty_players', set()) | {player.id}
    return {'quest_id': quest_id, 'alternative_quest_id': aid,
            'accepted': True, 'already_selected': False}


def blocked(world, player, quest):
    """Shared by command acceptance, turn-in, disclosure and list eligibility."""
    originals, reverse = _index(world)
    qid = quest.get('id')
    if qid in originals:
        row = selected(player, qid)
        if row or player.progress.get('quests', {}).get(qid) == 'replaced':
            aid = row['quest_id'] if row else reference(quest)
            name = world.quests.get(aid, {}).get('name', 'your replacement quest')
            return 'You chose ' + name + '. Its completion fulfills this guide stage; the guide is optional.'
        if _settled(world, player, quest) and player.progress.get('quests', {}).get(qid) != 'complete':
            return 'This guide stage has already been credited.'
    if qid in reverse:
        original_id = reverse[qid]; original = originals[original_id]
        row = selected(player, original_id)
        if row is None or row['quest_id'] != qid:
            return 'Choose this alternative from the original interface-guide offer or guide.'
        if row.get('completed') or _settled(world, player, original):
            return 'This alternative has already fulfilled its guide stage.'
        if player.progress.get('quests', {}).get(original_id) != 'replaced':
            return 'This replacement is no longer the active quest choice.'
        from engine import living
        return living.quest_blocked(world, player, original, alternatives=False, readonly=True)
    return ''


def completed(world, player, quest):
    """Settle the original stage after the replacement's one normal payout."""
    original_id = _index(world)[1].get(quest['id'])
    if original_id is None:
        return ''
    row = selected(player, original_id)
    if row is None or row.get('completed') or row['quest_id'] != quest['id']:
        return ''
    from engine import quest_chains
    row['completed'] = True
    player.progress['quests'][original_id] = 'complete'
    player.progress.setdefault('quest_times', {})[original_id] = player.progress.get('quest_times', {}).get(
        quest['id'], getattr(world, 'living_state', {}).get('minute', 0))
    _track(player, quest['id'], original_id)
    notice = quest_chains.completed(world, player, world.quests[original_id])
    world.dirty_players = getattr(world, 'dirty_players', set()) | {player.id}
    return 'The replacement fulfills your interface-guide quest. The guide remains available for reference.' + ('\n' + notice if notice else '')


def describe(proposal):
    replacement = proposal['replacement']; reward = replacement['reward']
    rewards = [str(reward['xp']) + ' XP', str(reward['gold']) + ' gold']
    rewards.extend(str(row['quantity']) + ' × ' + row['name'] for row in reward['items'])
    text = replacement['name'] + '\n' + replacement['description']
    text += '\nReward after ordinary completion: ' + ', '.join(rewards) + '.'
    text += '\nChoosing this quest pays nothing now. The original guide remains optional.'
    if proposal['available']:
        text += '\nTo confirm: interface choose ' + proposal['quest_id'] + ' ' + proposal['revision']
    else:
        text += '\n' + proposal['reason']
    return text
