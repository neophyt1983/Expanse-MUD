"""Ordered, creator-authored interface instructions attached to player quests.

Acknowledgements belong only to this guide. They never award general action
counters, move a character, save a checkpoint, or complete a quest. Projection
is read-only; ordinary explicit Save serializes the character's live progress.
"""
from hashlib import sha256
import json
import re


TARGETS = ('conversation', 'command', 'actions', 'quests', 'map', 'compass',
           'location', 'books', 'inventory', 'status', 'condition', 'save',
           'save_quit', 'panels', 'help')
KEY = 'interface_tours'
SELECTED = 'interface_tour_selected'
MAX_STEPS = 24
_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def _text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def validate(data):
    issues = []
    for quest in data.get('quest', []):
        tour = quest.get('interface_tour')
        if tour is None or tour == {}:
            continue
        label = str(quest.get('id', 'quest')) + ': interface_tour '
        if not isinstance(tour, dict):
            issues.append(label + 'must be an object'); continue
        if set(tour) - {'version', 'title', 'steps', 'completion_text', 'alternative_quest'}:
            issues.append(label + 'contains unsupported fields')
        if 'alternative_quest' in tour and not _text(tour['alternative_quest'], 240):
            issues.append(label + 'alternative_quest must be a nonempty quest ID')
        if type(tour.get('version')) is not int or tour['version'] != 1:
            issues.append(label + 'version must be 1')
        if not _text(tour.get('title'), 120):
            issues.append(label + 'title must be 1–120 characters')
        if 'completion_text' in tour and not _text(tour['completion_text'], 1200):
            issues.append(label + 'completion_text must be 1–1200 characters')
        if quest.get('scope', 'character') != 'character':
            issues.append(label + 'requires character scope')
        steps = tour.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            issues.append(label + 'requires 1–24 ordered steps'); continue
        seen = set()
        for index, step in enumerate(steps):
            where = label + 'step ' + str(index + 1) + ' '
            if not isinstance(step, dict):
                issues.append(where + 'must be an object'); continue
            if set(step) != {'id', 'target', 'title', 'text'}:
                issues.append(where + 'requires only id, target, title and text')
            ident = step.get('id')
            if not isinstance(ident, str) or not _ID.fullmatch(ident):
                issues.append(where + 'id must be 1–64 letters, digits, underscores or hyphens')
            elif ident in seen:
                issues.append(where + 'id must be unique')
            else:
                seen.add(ident)
            if step.get('target') not in TARGETS:
                issues.append(where + 'target is not a supported interface control')
            if not _text(step.get('title'), 120):
                issues.append(where + 'title must be 1–120 characters')
            if not _text(step.get('text'), 1200):
                issues.append(where + 'text must be 1–1200 characters')
    return issues


def definition(quest):
    tour = quest.get('interface_tour')
    if not tour or validate({'quest': [quest]}):
        return None
    return tour


def revision(tour):
    return sha256(json.dumps(tour, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).hexdigest()[:24]


def _saved(player, quest_id):
    records = player.progress.get(KEY, {})
    row = records.get(quest_id) if isinstance(records, dict) else None
    return row if isinstance(row, dict) else None


def _index(tour, row):
    acknowledgements = row.get('acknowledged', [])
    if not isinstance(acknowledgements, list):
        return 0
    # Only an ordered prefix counts. A malformed saved list cannot jump ahead.
    index = 0
    for step, acknowledged in zip(tour['steps'], acknowledgements):
        if step['id'] != acknowledged:
            break
        index += 1
    return index


def _dirty(world, player):
    world.dirty_players = getattr(world, 'dirty_players', set()) | {player.id}


def begin(world, player, quest):
    """Called only by a successful new acceptance, never by view/load/Look."""
    if not player.is_player or not definition(quest):
        return False
    records = player.progress.setdefault(KEY, {})
    records[quest['id']] = {'acknowledged': [], 'paused': False,
                            'required': True, 'satisfied': False}
    player.progress[SELECTED] = quest['id']
    _dirty(world, player)
    return True


def blocked(player, quest):
    """Old active/completed quests without an initialized guide stay valid."""
    tour = definition(quest)
    if not player.is_player or tour is None:
        return False
    row = _saved(player, quest['id'])
    # The same ordered acknowledgements drive both the journal and turn-in.
    # Older saves may have the complete prefix but no final satisfied marker.
    # Do not re-lock earned completion when an optional replay is restarted.
    return bool(row and row.get('required') is True and row.get('satisfied') is not True
                and _index(tour, row) < len(tour['steps']))


def summary(player, quest):
    tour = definition(quest)
    if tour is None:
        return None
    row = _saved(player, quest['id'])
    index = _index(tour, row) if row is not None else 0
    return {'started': row is not None, 'index': index, 'total': len(tour['steps']),
            'completed': row is not None and index == len(tour['steps']),
            'required': blocked(player, quest), 'paused': bool(row and row.get('paused'))}


def _learned(world, player):
    if not player or not player.is_player:
        return []
    statuses = player.progress.get('quests', {})
    return [world.quests[qid] for qid, status in statuses.items()
            if status in ('active', 'complete', 'replaced') and qid in world.quests
            and definition(world.quests[qid])]


def projection(world, player):
    """Return only accepted/completed guides, without initializing progress."""
    if not player or not player.is_player:
        return {'player_id': None, 'choices': [], 'current': None}
    quests = _learned(world, player)
    choices = []
    selected = player.progress.get(SELECTED)
    selected_quest = next((quest for quest in quests if quest['id'] == selected
                           and _saved(player, quest['id']) is not None), None)
    if selected_quest is None:
        selected_quest = next((quest for quest in quests if _saved(player, quest['id']) is not None), None)
    current = None
    for quest in quests:
        from engine import quest_alternatives
        tour = quest['interface_tour']
        row = _saved(player, quest['id'])
        index = _index(tour, row) if row else 0
        completed = row is not None and index == len(tour['steps'])
        alternative = quest_alternatives.affordance(world, player, quest)
        choices.append({'quest_id': quest['id'], 'quest_name': quest['name'],
                        'title': tour['title'], 'quest_status': player.progress['quests'][quest['id']],
                        'completed': completed, 'required': blocked(player, quest),
                        'paused': bool(row and row.get('paused')), **alternative})
        if selected_quest is not quest:
            continue
        step = tour['steps'][index] if not completed else None
        current = {'quest_id': quest['id'], 'quest_name': quest['name'],
                   'version': 1, 'title': tour['title'], 'revision': revision(tour),
                   'index': index, 'total': len(tour['steps']),
                   'step_id': step['id'] if step else None,
                   'target': step['target'] if step else None,
                   'step_title': step['title'] if step else 'Guide finished',
                   'text': step['text'] if step else tour.get('completion_text', quest.get('description', '')),
                   'paused': bool(row.get('paused')), 'completed': completed,
                   'required': blocked(player, quest), **alternative}
    return {'player_id': player.id, 'choices': choices, 'current': current}


def handle(world, player, packet):
    if not player or not player.is_player:
        raise ValueError('Enter your character before opening an interface guide.')
    if not isinstance(packet, dict):
        raise ValueError('Invalid interface guide request.')
    action = packet.get('action', 'view')
    if action not in ('view', 'next', 'pause', 'resume', 'restart'):
        raise ValueError('Unknown interface guide action.')
    if action == 'view':
        return projection(world, player)
    quests = {quest['id']: quest for quest in _learned(world, player)}
    qid = packet.get('quest_id')
    if qid is None:
        selected = player.progress.get(SELECTED)
        qid = selected if selected in quests else next(iter(quests)) if len(quests) == 1 else None
    if not isinstance(qid, str) or qid not in quests:
        raise ValueError('Choose an interface guide from an accepted quest.')
    quest = quests[qid]
    tour = quest['interface_tour']
    row = _saved(player, qid)
    if action == 'next':
        if row is None:
            raise ValueError('Resume this interface guide before continuing.')
        if packet.get('revision') != revision(tour):
            raise ValueError('This guide changed. Refresh it before continuing.')
        index = _index(tour, row)
        ident = packet.get('step_id')
        if not isinstance(ident, str):
            raise ValueError('Choose the current interface guide step.')
        # Retry of an already acknowledged step is harmless and cannot advance
        # the next one. Future IDs, unrelated IDs and stale definitions fail.
        if ident in [step['id'] for step in tour['steps'][:index]]:
            return projection(world, player)
        if index >= len(tour['steps']) or ident != tour['steps'][index]['id']:
            raise ValueError('The interface guide step changed. Refresh the guide.')
        if row.get('paused'):
            raise ValueError('Resume this interface guide before continuing.')
        row['acknowledged'] = [step['id'] for step in tour['steps'][:index + 1]]
        if index + 1 == len(tour['steps']):
            row['satisfied'] = True
    elif action == 'pause':
        if row is not None:
            row['paused'] = True
        else:
            # Pausing a never-started legacy guide must not introduce a gate.
            return projection(world, player)
    else:
        if row is None:
            row = {'acknowledged': [], 'paused': False, 'required': False, 'satisfied': False}
            player.progress.setdefault(KEY, {})[qid] = row
        if action == 'restart':
            row['acknowledged'] = []
        row['paused'] = False
    player.progress[SELECTED] = qid
    _dirty(world, player)
    return projection(world, player)


def describe(state):
    current = state['current']
    if current is None:
        if not state['choices']:
            return 'No accepted quest has an interface guide. Accept a request that includes one to begin.'
        return 'Interface guides:\n' + '\n'.join(
            row['quest_name'] + ' — interface resume ' + row['quest_id'] for row in state['choices'])
    label = 'finished' if current['completed'] else str(current['index'] + 1) + '/' + str(current['total'])
    text = current['title'] + ' — ' + label + '\n' + current['step_title'] + '\n' + current['text']
    if current['completed']:
        return text + '\nOptional replay: interface restart. Your quest rewards and completion stay unchanged.'
    if current['paused']:
        return text + '\nPaused. Use interface resume when ready.'
    return text + '\nAfter reading, use interface next. Use interface later to pause; interface guide reviews this step.'


def command(world, player, args):
    words = args.strip().split(maxsplit=1)
    verb = words[0].lower() if words else 'guide'
    qid = words[1].strip() if len(words) == 2 else None
    if verb in ('alternative', 'choose'):
        from engine import quest_alternatives
        if verb == 'alternative':
            if not qid:
                current = projection(world, player)['current']
                qid = current['quest_id'] if current else None
            return quest_alternatives.describe(quest_alternatives.preview(world, player, qid))
        selection = qid.split() if qid else []
        if len(selection) != 2:
            return 'Review interface alternative <quest ID> first, then confirm with interface choose <quest ID> <revision>.'
        choice = quest_alternatives.choose(world, player, selection[0], selection[1])
        replacement = world.quests[choice['alternative_quest_id']]
        return ('Already chosen. ' if choice['already_selected'] else 'Replacement quest accepted. ') + replacement['name'] + '\n' + replacement.get('description', '') + '\nNo reward is paid for choosing. Complete its objectives and turn it in normally. Actions → Interface guide remains available for reference.'
    action = {'guide': 'view', 'next': 'next', 'later': 'pause',
              'resume': 'resume', 'restart': 'restart'}.get(verb)
    if action is None:
        return 'Use interface guide, interface next, interface later, interface resume [quest ID], interface restart [quest ID], or interface alternative <quest ID>. Review an alternative before confirming interface choose <quest ID> <revision>.'
    packet = {'action': action}
    if qid:
        packet['quest_id'] = qid
    if action == 'next':
        current = projection(world, player)['current']
        if current is None:
            return describe(projection(world, player))
        if current['completed']:
            return describe(projection(world, player))
        packet.update(quest_id=current['quest_id'], revision=current['revision'], step_id=current['step_id'])
    return describe(handle(world, player, packet))
