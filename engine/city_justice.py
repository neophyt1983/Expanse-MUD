"""Witnessed accusations, hearings and finite sentences in authored facilities."""
from copy import deepcopy
from hashlib import sha256
from engine import living, regional_world, relationships

KEY = 'city_justice_v1'


def state(w):
    return living.state(w).setdefault(KEY, {'cases': {}, 'history': [], 'last': -1})


def install(w):
    """Courts, judges, station jails and prisons belong to the world file."""
    value = getattr(w, 'rules', {}).get('city_courts', {})
    w.city_courts = (deepcopy(value) if isinstance(value, dict)
                     and regional_world.config(w, 'courts', False) is True else {})


def court_for(w, room):
    city = regional_world.city_for(w, room)
    return getattr(w, 'city_courts', {}).get(city['name']) if city else None


def confined(w, actor):
    case = state(w)['cases'].get(actor.id)
    return bool(case and case.get('status') in ('awaiting_hearing', 'sentenced'))


def custody_room(case):
    if case.get('status') == 'awaiting_hearing':
        return case.get('holding', case['court'])
    return case.get('custody_room', case['jail'])


def blocked(w, actor, destination):
    case = state(w)['cases'].get(actor.id)
    if not case:
        return ''
    now = int(living.state(w)['minute'])
    if case['status'] == 'awaiting_hearing' and destination != custody_room(case):
        return 'You are in the watch’s custody pending a hearing in '+str(max(0, case['hearing_at']-now))+' game minutes. No verdict has been issued.'
    if case['status'] == 'sentenced' and now < case['release_at']:
        allowed = case.get('custody_rooms') or [custody_room(case)]
        if destination not in allowed:
            return 'The judge’s sentence has '+str(case['release_at']-now)+' game minutes remaining. You may use the facilities inside your place of custody.'
    return ''


def _case_evidence(case, ident):
    """The same retained witnessed acts considered by the hearing."""
    return [event for event in case.get('evidence', [])
            if event.get('actor') == ident and event.get('victim') == case.get('victim')
            and event.get('kind') == case.get('accusation') and event.get('witnesses')
            and set(event['witnesses']) & set(case.get('witnesses', []))]


def _place_name(w, rid):
    room = w.rooms.get(rid)
    return room.name if room else 'the recorded location'


def _case_reason(w, case, ident):
    accusation = str(case.get('accusation') or 'an unspecified offence')
    events = _case_evidence(case, ident)
    if not events:
        return 'The recorded accusation is '+accusation+'. The original incident details are not available in this saved case.'
    event = events[-1]
    source = event.get('source') or {}
    name = source.get('name') if isinstance(source, dict) else None
    action = ''
    if isinstance(name, str) and name.strip():
        if source.get('action') == 'take':
            action = ': taking contents from '+name
        elif source.get('action') == 'tamper':
            action = ': tampering with '+name
        else:
            action = ' involving '+name
    return 'The recorded accusation is '+accusation+action+' at '+_place_name(w, event.get('room'))+'.'


def projection(w, actor):
    """Read only this player's case; never export the shared court registry.

    Explicit resolved states let the UI show a release even if conversation is
    busy. A missing case is not evidence of a release. Old records remain valid
    without fabricating an incident source that they did not retain.
    """
    if actor is None or not actor.is_player:
        return None
    saved = getattr(w, 'living_state', {}) or {}
    justice = saved.get(KEY, {})
    case = justice.get('cases', {}).get(actor.id)
    if case is None:
        case = next((row for row in reversed(justice.get('history', []))
                     if row.get('actor') == actor.id), None)
    if not case:
        return None
    status = case.get('status')
    titles = {'awaiting_hearing': 'In custody — awaiting hearing',
              'sentenced': 'In custody — sentence', 'released': 'Released from custody',
              'dismissed': 'Case dismissed', 'closed_deceased': 'Court case closed'}
    if status not in titles:
        return None
    active = status in ('awaiting_hearing', 'sentenced')
    now = int(saved.get('minute', 0))
    next_event = 'hearing' if status == 'awaiting_hearing' else 'release' if status == 'sentenced' else None
    deadline = case.get('hearing_at' if next_event == 'hearing' else 'release_at') if next_event else None
    remaining = max(0, deadline-now) if type(deadline) is int else None
    holding = custody_room(case)
    allowed = (case.get('custody_rooms') or [holding]) if status != 'awaiting_hearing' else [holding]
    facilities = list(dict.fromkeys(_place_name(w, rid) for rid in allowed
                      if rid in w.rooms and (w.rooms[rid].map_visibility != 'hidden' or rid == actor.location)))
    realtime = bool(getattr(w, 'realtime', False))
    can_wait = bool(status == 'sentenced' and remaining and not realtime and living.enabled(w)
                    and actor.alive and actor.progress.get('restrained_until', 0) <= now)
    instructions = []
    outcome = None
    if status == 'awaiting_hearing':
        instructions = ['No verdict has been issued. The hearing happens automatically as game time advances.',
                        'You must remain in the holding area until the hearing.']
    elif status == 'sentenced':
        instructions = ['You may use the permitted custody facilities; leaving them is blocked until the sentence ends.',
                        'Release happens automatically when the game-time deadline is reached. You will be moved to '+
                        _place_name(w, case.get('release'))+'.']
    elif status == 'released':
        outcome = 'Your sentence is complete. You have been released to '+_place_name(w, case.get('release'))+'.'
    elif status == 'dismissed':
        outcome = 'The accusation was dismissed without a sentence or fine. You have been released to '+_place_name(w, case.get('release'))+'.'
    else:
        outcome = 'This court case was closed after the character died.'
    if active:
        instructions.append('These are game minutes, not real minutes. The clock advances while you are connected.')
        if realtime:
            instructions.append('The shared world clock cannot be skipped.')
        elif can_wait:
            instructions.append('Use Wait to advance game time, or stay connected while the clock runs.')
    identity = (actor.id, case.get('arrested'), case.get('reported'), case.get('origin'), case.get('accusation'))
    evidence = []
    for event in _case_evidence(case, actor.id):
        source = event.get('source') if isinstance(event.get('source'), dict) else {}
        evidence.append(dict(accusation=event['kind'], place=_place_name(w, event.get('room')),
                             minute=event.get('minute'), source_name=source.get('name'),
                             action=source.get('action'), witness_count=len(set(event['witnesses']))))
    return dict(id=sha256(repr(identity).encode()).hexdigest()[:20], status=status, active=active,
                title=titles[status], accusation=case.get('accusation'), reason=_case_reason(w, case, actor.id),
                witness_count=len(set(case.get('witnesses', []))), evidence=evidence,
                remaining_minutes=remaining, next_event=next_event, deadline_minute=deadline,
                custody_place=_place_name(w, holding), release_place=_place_name(w, case.get('release')),
                allowed_facilities=facilities, fine_paid=case.get('fine_paid'), instructions=instructions,
                outcome=outcome, can_wait=can_wait, wait_command='wait '+str(min(60, remaining)) if can_wait else None)


def apprehend(w, suspect, guard, report):
    """Accept an accusation for a hearing, without deciding guilt."""
    court = court_for(w, report.get('room'))
    if not court or not relationships.sentient(w, suspect):
        return False
    now = int(living.state(w)['minute'])
    if confined(w, suspect):
        return True
    delay = int(regional_world.config(w, 'hearing_delay_minutes', 1))
    case = dict(court, actor=suspect.id, name=suspect.name, origin=suspect.location,
                accusation=report.get('kind', 'assault'), victim=report.get('victim'), reported=report.get('reported'),
                witnesses=list(report.get('witnesses', [])), evidence=deepcopy(report.get('evidence', [])),
                arresting_officer=guard.id, status='awaiting_hearing', arrested=now, hearing_at=now+delay)
    state(w)['cases'][suspect.id] = case
    suspect.progress['restrained_until'] = case['hearing_at']+1
    suspect.progress['court_case'] = dict(status='awaiting_hearing', hearing_at=case['hearing_at'],
                                          court=case['court'], holding=custody_room(case))
    w.move_entity(suspect.id, custody_room(case), forced=True)
    subject = 'you' if suspect.is_player else suspect.name
    detail = ' '+_case_reason(w, case, suspect.id) if suspect.is_player else ''
    regional_world.notice(w, suspect, guard.name+' takes '+subject+' to '+w.rooms[custody_room(case)].name+
                          ' on a witnessed '+case['accusation']+' accusation.'+detail+
                          ' No guilt or fine has been decided. The magistrate hearing begins automatically in '+str(delay)+' game minutes.', room=suspect.location)
    from engine import gazette
    gazette.record(w, case['origin'], 'Watch', guard.name+' took '+suspect.name+
                   ' into custody on a '+case['accusation']+' accusation; a magistrate hearing is pending.', byline='Court reporter')
    return True


def _publish(w, actor, case, text):
    regional_world.notice(w, actor, text, room=actor.location)
    from engine import gazette
    gazette.record(w, case['release'], 'Watch', text, byline='Court reporter')


def _sentence(w, case):
    policies = regional_world.config(w, 'sentences', {})
    policy = policies.get(case['accusation'], policies.get('default', {}))
    minutes, fine = max(0, int(policy.get('minutes', 0))), max(0, int(policy.get('fine', 0)))
    place = policy.get('custody', 'auto')
    if place == 'auto':
        threshold = int(regional_world.config(w, 'prison_threshold_minutes', 1))
        place = 'prison' if minutes >= threshold and case.get('prison') else 'jail'
    target = case.get(place, case['jail'])
    allowed = list(case.get('prison_rooms', [])) if place == 'prison' else []
    if target not in allowed:
        allowed.append(target)
    return minutes, fine, target, allowed


def _release(w, actor, case):
    actor.progress.pop('court_case', None)
    actor.progress['restrained_until'] = int(living.state(w)['minute'])
    w.move_entity(actor.id, case['release'], forced=True)


def advance(w):
    if not getattr(w, 'city_courts', None):
        return
    s = state(w)
    now = int(living.state(w)['minute'])
    if s['last'] == now:
        return
    s['last'] = now
    for ident, case in list(s['cases'].items()):
        actor = w.entities.get(ident)
        if actor is None:
            continue  # Offline players retain their actual persisted case.
        if not actor.alive:
            case['status'] = 'closed_deceased'
            actor.progress.pop('court_case', None)
            actor.progress['restrained_until'] = now
        elif case['status'] == 'awaiting_hearing' and now >= case['hearing_at']:
            judge = next((e for e in w.entities_in_room(case['court'])
                          if e.alive and e.source_def == case['judge']), None)
            if judge is None and now-case['arrested'] < int(regional_world.config(w, 'judge_wait_minutes', 1)):
                case['hearing_at'] = now+1
                actor.progress['court_case']['hearing_at'] = case['hearing_at']
                continue
            # A retained witnessed act is required; faction dislike, allegation
            # text and mere presence do not establish guilt.
            evidence = [e for e in case.get('evidence', []) if e.get('actor') == ident
                        and e.get('victim') == case.get('victim') and e.get('kind') == case['accusation']
                        and e.get('witnesses') and set(e['witnesses']) & set(case['witnesses'])]
            if judge and evidence:
                w.move_entity(actor.id, case['court'], forced=True)
                sentence, fine, target, allowed = _sentence(w, case)
                paid = min(actor.gold, fine)
                actor.gold -= paid
                case.update(status='sentenced', verdict='guilty', verdict_at=now,
                            release_at=now+sentence, fine_paid=paid, custody_room=target, custody_rooms=allowed)
                actor.progress['restrained_until'] = now
                actor.progress['court_case'] = dict(status='sentenced', release_at=now+sentence,
                                                    jail=target, verdict='guilty', custody_rooms=allowed)
                w.move_entity(actor.id, target, forced=True)
                _publish(w, actor, case, judge.name+' finds '+actor.name+' guilty of witnessed '+case['accusation']+
                         ' after reviewing '+str(len(case['witnesses']))+' named witness report(s). Sentence: '+str(sentence)+
                         ' game minutes in '+w.rooms[target].name+' and '+str(paid)+' gold paid. Release happens automatically at world minute '+str(now+sentence)+'.')
            else:
                case.update(status='dismissed', verdict='not_proven', verdict_at=now)
                _release(w, actor, case)
                _publish(w, actor, case, ('The magistrate dismisses the accusation against ' if judge else 'The watch releases ')+actor.name+
                         (' because no sufficient witnessed act is recorded. No fine or sentence is imposed.' if judge else
                          ' because no judge is available for a timely hearing. No fine or sentence is imposed.'))
        # This also handles an authored fine-only, zero-time sentence.
        if case['status'] == 'sentenced' and now >= case['release_at']:
            place = custody_room(case)
            case.update(status='released', released_at=now)
            _release(w, actor, case)
            _publish(w, actor, case, actor.name+' has completed the judge’s sentence and is released from '+w.rooms[place].name+'.')
        if case['status'] not in ('awaiting_hearing', 'sentenced'):
            s['history'] = (s['history']+[dict(case)])[-100:]
            del s['cases'][ident]
