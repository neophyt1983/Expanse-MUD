"""Witnessed accusations, hearings and finite sentences in authored facilities."""
from copy import deepcopy
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
    regional_world.notice(w, suspect, guard.name+' takes you to '+w.rooms[custody_room(case)].name+
                          ' on a witnessed '+case['accusation']+' accusation. No guilt or fine has been decided. The magistrate hearing begins in '+str(delay)+' game minutes.', room=suspect.location)
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
                         ' game minutes in '+w.rooms[target].name+' and '+str(paid)+' gold paid. Release is at world minute '+str(now+sentence)+'.')
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
