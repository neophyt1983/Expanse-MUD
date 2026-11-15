"""Bounded personal encounter accounts, with explicit provenance for retellings.

Only nearby awake witnesses and actual participants learn firsthand facts.
Stories live in ordinary character progress and use the existing manual save.
No global news feed, remote sighting lookup, rewards, or map discovery is added.
"""
from copy import deepcopy
from hashlib import sha256
import json

from engine import creature_catalog, living, relationships, worldtime

KEY = 'encounter_stories_v1'
LIMIT = 8
WITNESSES = 32
MAX_HOPS = 2
SHARE_INTERVAL = 30


def _now(w):
    return int(living.state(w)['minute'])


def _resident(w, person):
    if (person is None or person.is_player or not person.alive
            or person.progress.get('zoo_exhibit') or not relationships.sentient(w, person)):
        return False
    from engine import livelihoods
    return livelihoods.awake(w, person) and not str(getattr(person, 'activity', '')).lower().startswith('sleep')


def _threat(w, actor):
    if (actor is None or actor.is_player or actor.progress.get('companion_owner')
            or actor.progress.get('zoo_exhibit') or relationships.sentient(w, actor)):
        return False
    row = w.npcs.get(actor.source_def, {})
    return not row.get('zoo_exhibit') and creature_catalog.kind(row, getattr(w, 'species', {})) in ('monster', 'creature')


def records(person):
    rows = person.progress.get(KEY, [])
    return rows if isinstance(rows, list) else []


def _put(person, row):
    rows = [old for old in records(person) if old.get('id') != row['id']]
    rows.append(row)
    person.progress[KEY] = rows[-LIMIT:]


def _witnesses(w, room, participants=()):
    direct = [p for p in participants if _resident(w, p) and p.location == room]
    seen = {p.id for p in direct}
    others = sorted((p for p in w.entities_in_room(room) if p.id not in seen and _resident(w, p)), key=lambda p: p.id)
    return (direct + others)[:WITNESSES]


def _account(w, observer, threat):
    existing = next((r for r in records(observer) if r.get('id') == threat.id and not r.get('hearsay')), None)
    if existing is not None:
        return existing
    detail = living.details(w, threat.location)
    row = dict(id=threat.id, threat=threat.name, category=creature_catalog.kind(w.npcs.get(threat.source_def, {}), getattr(w, 'species', {})),
               place_id=threat.location, place=w.rooms[threat.location].name,
               region=detail.get('world_region') or detail.get('press_locality') or '',
               at=_now(w), updated=_now(w), observer_id=observer.id, observer=observer.name,
               activity=str(getattr(observer, 'activity', '') or '').strip().rstrip('.')[:160],
               hearsay=False, hops=0, participated=False, attacked=False, struck=False,
               hurt=0, helpers=[], participants=[], attacked_people=[], casualties=[], outcome='sighted', killer='', killer_id='')
    _put(observer, row)
    return row


def observe(w, threat):
    if not _threat(w, threat) or not threat.alive or threat.location not in w.rooms:
        return
    for observer in _witnesses(w, threat.location):
        _account(w, observer, threat)


def hit(w, attacker, victim, damage):
    """Observe a real resolved strike; a counterattack calls this separately."""
    candidates = [p for p in (attacker, victim) if _threat(w, p)]
    if len(candidates) != 1:
        return
    threat = candidates[0]
    person = victim if attacker is threat else attacker
    if not (person.is_player or relationships.sentient(w, person) or person.progress.get('companion_owner')):
        return
    from engine import npc_life
    for observer in _witnesses(w, threat.location, (person,)):
        row = _account(w, observer, threat)
        row['updated'] = _now(w)
        people = [p for p in row.get('participants', []) if p['id'] != person.id]
        row['participants'] = (people + [dict(id=person.id, name=person.name)])[-8:]
        if attacker is threat:
            attacked = [p for p in row.get('attacked_people', []) if p['id'] != person.id]
            row['attacked_people'] = (attacked + [dict(id=person.id, name=person.name)])[-4:]
        if observer.id == person.id:
            if not row['participated']:
                row['place_id'], row['place'] = threat.location, w.rooms[threat.location].name
                detail = living.details(w, threat.location)
                row['region'] = detail.get('world_region') or detail.get('press_locality') or ''
                row['at'] = _now(w)
                row['activity'] = str(getattr(observer, 'activity', '') or '').strip().rstrip('.')[:160]
            row['participated'] = True
            row['outcome'] = 'fighting'
            if attacker is threat:
                row['attacked'] = True
                row['hurt'] += max(0, damage)
                if damage > 0:
                    npc_life.event(w, observer, 'encounter injury', -4, source=threat.name[:160], event_id=('encounter-hurt:' + threat.id)[:160])
            else:
                row['struck'] = True
        if victim is threat and attacker.id != observer.id:
            helpers = [r for r in row['helpers'] if r['id'] != attacker.id]
            row['helpers'] = (helpers + [dict(id=attacker.id, name=attacker.name)])[-4:]
        if not person.alive and person.name not in row['casualties']:
            row['casualties'] = (row['casualties'] + [person.name])[-4:]
        _put(observer, row)


def defeated(w, dead, killer):
    if not _threat(w, dead) or dead.location not in w.rooms:
        return
    from engine import npc_life
    for observer in _witnesses(w, dead.location, (killer,)):
        row = _account(w, observer, dead)
        row.update(outcome='defeated', updated=_now(w), killer=killer.name, killer_id=killer.id)
        npc_life.event(w, observer, 'encounter survived', 3 if row['participated'] else 1,
                       source=dead.name[:160], event_id=('encounter-ended:' + dead.id)[:160])
        _put(observer, row)


def departed(w, threat):
    """Losing sight of a threat is not evidence that it died or was defeated."""
    if not _threat(w, threat) or threat.location not in w.rooms:
        return
    for observer in _witnesses(w, threat.location):
        row = next((r for r in records(observer) if r.get('id') == threat.id and not r.get('hearsay')), None)
        if row and row['outcome'] != 'defeated':
            row.update(outcome='lost_sight', updated=_now(w))
            _put(observer, row)


def travel(w, person, start, end):
    if person.is_player or start == end or not relationships.sentient(w, person):
        return
    for row in list(records(person)):
        if row.get('hearsay') or row.get('outcome') not in ('sighted', 'fighting'):
            continue
        threat = w.entities.get(row.get('id'))
        if threat and threat.alive and threat.location == start:
            row.update(outcome='left', updated=_now(w))
            _put(person, row)


def _version(row):
    fields = {k: row.get(k) for k in ('id', 'updated', 'outcome', 'hurt', 'helpers', 'participants', 'attacked_people', 'casualties', 'killer_id', 'observer_id')}
    return sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


def learn(w, listener, speaker, account):
    """Transfer only a spoken account, never an omniscient current-world update."""
    if (not _resident(w, listener) or not _resident(w, speaker)
            or listener.location != speaker.location or account.get('hops', 0) >= MAX_HOPS):
        return False
    existing = next((r for r in records(listener) if r.get('id') == account['id']), None)
    if existing:
        if not existing.get('hearsay') or existing.get('updated', 0) > account.get('updated', 0):
            return False
        if _version(existing) == _version(account):
            return False
        if existing.get('outcome') == 'defeated' and account.get('outcome') != 'defeated':
            return False
    row = deepcopy(account)
    row.update(hearsay=True, heard_from=speaker.name, heard_from_id=speaker.id,
               heard_at=_now(w), hops=account.get('hops', 0) + 1)
    _put(listener, row)
    return True


def _name(row, listener):
    return 'you' if listener is not None and row.get('id') == listener.id else row.get('name', 'someone nearby')


def _names(values):
    return values[0] if len(values) == 1 else ', '.join(values[:-1]) + ' and ' + values[-1]


def words(w, row, listener=None):
    threat, place = row['threat'], row['place']
    hearsay = bool(row.get('hearsay'))
    subject = row.get('observer', 'the witness') if hearsay else 'I'
    if hearsay:
        text = row['heard_from'] + ' told me about ' + threat + ' at ' + place + '. '
        text += subject + (' took part in the encounter. ' if row['participated'] else ' was there and saw it. ')
    else:
        verb = 'fought ' if row['struck'] else 'was attacked by ' if row['attacked'] else 'saw '
        text = 'I ' + verb + threat + ' at ' + place + '. '
    activity = row.get('activity')
    if activity:
        text += (subject + ' was ' if hearsay else 'At the time, I was ') + activity[:1].lower() + activity[1:] + '. '
    if row['hurt']:
        text += (subject + ' was hurt during the encounter. ' if hearsay else 'I was hurt during the encounter. ')
    attacked = [p for p in row.get('attacked_people', []) if p['id'] != row['observer_id']]
    if attacked:
        text += 'It attacked ' + _names([_name(p, listener) for p in attacked]) + '. '
    if row['helpers']:
        helpers = _names([_name(p, listener) for p in row['helpers']])
        text += helpers[:1].upper() + helpers[1:] + ' also fought it. '
    if row['outcome'] == 'defeated':
        killer = 'I' if not hearsay and row['killer_id'] == row['observer_id'] else 'You' if listener is not None and row['killer_id'] == listener.id else row['killer']
        text += killer + ' brought it down. '
        if not hearsay:
            text += 'I felt relieved when the danger ended.'
    elif row['outcome'] == 'left':
        text += (subject + ' left the area without seeing it defeated.' if hearsay else 'I left the area, but I did not see it defeated.')
    elif row['outcome'] == 'lost_sight':
        text += (subject + ' lost sight of it; its fate was not known.' if hearsay else 'I lost sight of it. I do not know what happened to it afterwards.')
    else:
        text += ('That account did not establish what happened to it afterwards.' if hearsay else 'I have not seen it defeated, so I would be cautious around that place.')
    if row['casualties']:
        text += ' ' + _names(row['casualties']) + (' died there, according to that account.' if hearsay else ' died there. I saw it happen.')
    if hearsay:
        text += ' I did not witness this myself.'
    return text.strip()


def _rank(w, row, listener, duties):
    detail = living.details(w, listener.location) if listener else {}
    region = detail.get('world_region') or detail.get('press_locality') or ''
    shared = listener is not None and (row.get('killer_id') == listener.id or any(p['id'] == listener.id for p in row.get('participants', []) + row['helpers']))
    local = listener is not None and (row['place_id'] == listener.location or bool(region and region == row.get('region')))
    recent = _now(w) - row.get('updated', 0) <= 3 * worldtime.MINUTES_PER_DAY
    relevant = row['place_id'] in duties
    return (shared, recent and (local or relevant), not row.get('hearsay'), row.get('updated', 0))


def accounts(w, speaker, listener=None):
    # The speaker knows their own work and plans; do not inspect a listener's
    # private schedule to invent a reason for the speaker to raise a subject.
    definition = w.npcs.get(speaker.source_def, {})
    duties = {definition.get('work_room'), definition.get('home_room')}
    duties.update(shift.get('room') for shift in definition.get('schedule', []))
    for job in getattr(w, 'living_state', {}).get('community_jobs', {}).get('jobs', {}).values():
        if job.get('worker') == speaker.id and job.get('status') == 'active':
            duties.update(step.get('room') for step in job.get('steps', []))
    return sorted(records(speaker), key=lambda row: _rank(w, row, listener, duties), reverse=True)


def exchange(w, speaker, listener):
    """A relevant, new account within the existing local NPC conversation loop."""
    if not _resident(w, speaker) or not _resident(w, listener) or speaker.location != listener.location:
        return None
    from engine import town_talk
    notes = town_talk.notebook(speaker)
    now = _now(w)
    if now < notes.get('next_encounter_story', 0):
        return None
    told = notes.setdefault('encounter_stories_told', {})
    for row in accounts(w, speaker, listener):
        if now - row.get('updated', 0) > 3 * worldtime.MINUTES_PER_DAY or row.get('hops', 0) >= MAX_HOPS:
            continue
        key = listener.id + '|' + row['id']
        version = _version(row)
        if told.get(key) == version:
            continue
        known = next((r for r in records(listener) if r.get('id') == row['id']), None)
        if known and not known.get('hearsay'):
            if not any(p['id'] == listener.id for p in row['helpers']) and row.get('killer_id') != listener.id:
                continue
            reply = 'I remember being there. It is good to hear how it was for you.'
        elif learn(w, listener, speaker, row):
            reply = ('Thank you for telling me who saw it. I will remember that it is their account.' if row.get('hearsay')
                     else 'Thank you for telling me what happened. I will remember where you saw it.')
        else:
            continue
        town_talk.remember(told, key, version, 32)
        notes['next_encounter_story'] = now + SHARE_INTERVAL
        return 'says', words(w, row, listener), reply
    return None
