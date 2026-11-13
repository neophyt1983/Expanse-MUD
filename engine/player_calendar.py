"""Private multiplayer appointments in real-world UTC, not Expanse game time.

Pure candidate updates let the server durably save before acknowledging a write.
No NPC integration, external invitations or background notification service.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import uuid
import hashlib
import json
import re

KEY = 'player_calendar'
UTC = timezone.utc
DEFAULTS = dict(enabled=True, max_events=1000, max_owner_events=64, max_invitees=16,
                max_duration_hours=168, max_ahead_days=366, max_directory=1000)


def rules(world):
    supplied = world.metadata.get('player_calendar_rules', {})
    if not isinstance(supplied, dict): raise ValueError('Calendar settings need Creator validation.')
    out = dict(DEFAULTS)
    for key, value in supplied.items():
        if key not in out: continue
        if key == 'enabled':
            if type(value) is not bool: raise ValueError('Calendar enabled must be true or false.')
        elif type(value) is not int or not 1 <= value <= dict(max_events=10000, max_owner_events=1000, max_invitees=32, max_duration_hours=744, max_ahead_days=730, max_directory=10000)[key]:
            raise ValueError('Calendar setting is out of bounds: ' + key)
        out[key] = value
    return out


def read(world):
    state = getattr(world, 'living_state', {}).get(KEY)
    if state is None: return dict(version=1, revision=0, directory={}, events={})
    if not isinstance(state, dict) or state.get('version') != 1 or not isinstance(state.get('directory'), dict) or not isinstance(state.get('events'), dict):
        raise ValueError('Calendar save needs recovery; its contents have not been reset.')
    validate_store(state)
    return state


def stamp(value):
    return datetime.fromtimestamp(value, UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def instant(value):
    if not isinstance(value, str) or len(value) > 40: raise ValueError('Invalid UTC appointment time.')
    try: dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: raise ValueError('Invalid UTC appointment time.')
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0): raise ValueError('Appointment instants must be UTC.')
    return dt.timestamp()


def zone(name):
    if not isinstance(name, str) or not name or len(name) > 80: raise ValueError('Choose an IANA timezone, such as America/Chicago or UTC.')
    try: return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError): raise ValueError('Unknown timezone. Use an IANA name such as America/Chicago or UTC.')


def local_time(text, name, fold=None):
    """Reject DST gaps, and require an explicit choice for repeated wall times."""
    tz = zone(name)
    if not isinstance(text, str) or len(text) not in (16, 19): raise ValueError('Enter a local date and time.')
    try: dt = datetime.fromisoformat(text)
    except ValueError: raise ValueError('Enter a valid local date and time.')
    if dt.tzinfo is not None: raise ValueError('Use the timezone field separately from local time.')
    if fold is not None and (type(fold) is not int or fold not in (0, 1)): raise ValueError('Choose the first or second occurrence of a repeated time.')
    choices = []
    for f in (0, 1):
        candidate = dt.replace(tzinfo=tz, fold=f)
        back = candidate.astimezone(UTC).astimezone(tz)
        if back.replace(tzinfo=None) == dt: choices.append(candidate)
    if not choices: raise ValueError('That local time does not exist because the clocks move forward. Choose another time.')
    ambiguous = len({c.utcoffset() for c in choices}) > 1
    if ambiguous and fold is None: raise ValueError('That local time occurs twice because the clocks move back. Choose first or second occurrence.')
    result = dt.replace(tzinfo=tz, fold=fold or 0)
    return stamp(result.timestamp())


def text(value, name, limit, optional=False):
    if not isinstance(value, str) or len(value) > limit: raise ValueError(name + ' is too long or is not text.')
    value = value.strip()
    if not value and not optional: raise ValueError('Enter ' + name.lower() + '.')
    if any(ord(c) < 32 and (not optional or c not in ('\n', '\t')) for c in value): raise ValueError(name + ' contains unsupported control characters.')
    return value


def authorized(event, actor):
    return event.get('owner') == actor or actor in event.get('participants', {})


def _event(data, ident, actor):
    if not isinstance(ident, str) or len(ident) > 128: raise ValueError('That event is not available to this character.')
    event = data['events'].get(ident)
    if not isinstance(event, dict) or not authorized(event, actor): raise ValueError('That event is not available to this character.')
    return event


def _revision(event, value):
    if type(value) is not int or value != event['revision']: raise ValueError('This event changed. Refresh the calendar before trying again.')


def event_view(event, actor):
    tz = zone(event['timezone'])
    out = {key: event[key] for key in ('id', 'revision', 'title', 'notes', 'expanse_note', 'timezone', 'starts_at', 'ends_at', 'status', 'updated_at')}
    out['owner'] = event['owner']; out['can_edit'] = actor == event['owner']
    out['participants'] = [dict(id=ident, name=p['name'], label=p['label'], response=p['response'], owner=ident == event['owner']) for ident,p in event['participants'].items()]
    for prefix, key in [('start', 'starts_at'), ('end', 'ends_at')]:
        dt = datetime.fromtimestamp(instant(event[key]), UTC).astimezone(tz)
        out[prefix + '_local'] = dt.strftime('%Y-%m-%dT%H:%M')
        out[prefix + '_fold'] = dt.fold
    return out


def view(world, actor, now, _validated=None):
    cfg = rules(world)
    if not cfg['enabled']: return dict(enabled=False, events=[], directory=[], notice='The Creator has disabled the player calendar in this world.')
    data = read(world) if _validated is None else _validated
    events = [event_view(e, actor) for e in data['events'].values() if authorized(e, actor)]
    events.sort(key=lambda e: (e['starts_at'], e['id']))
    for event in events:event['ended']=instant(event['ends_at'])<=now;event['phase']='cancelled' if event['status']=='cancelled' else 'ended' if instant(event['ends_at'])<=now else 'in progress' if instant(event['starts_at'])<=now else 'upcoming'
    directory = [dict(id=i, name=p['name'], label=p['label']) for i,p in data['directory'].items() if p.get('available')]
    directory.sort(key=lambda p: (p['label'].casefold(), p['id']))
    own = data['directory'].get(actor, {})
    return dict(enabled=True, actor=actor, revision=data['revision'], server_now=stamp(now), events=events, directory=directory,
                registration=dict(available=bool(own.get('available')), label=own.get('label', '')),
                notice='Real-world appointments. Only the owner and invited characters can see an event. This calendar sends no email, SMS or offline alerts.')


def update(world, player, payload, now, new_id=None):
    if not getattr(player, 'is_player', False):raise ValueError('Only player characters can schedule these events.')
    cfg = rules(world)
    if not cfg['enabled']: raise ValueError('The Creator has disabled the player calendar in this world.')
    if not isinstance(payload, dict): raise ValueError('Calendar request must be an object.')
    action = payload.get('action');actor = player.id
    fields = dict(register={'label', 'available'}, create={'client_token','title','notes','timezone','start_local','end_local','start_fold','end_fold','expanse_note','invitees'}, edit={'id','revision','title','notes','timezone','start_local','end_local','start_fold','end_fold','expanse_note','invitees'}, cancel={'id','revision'}, respond={'id','revision','response'})
    if not isinstance(action, str) or action not in fields or set(payload) - fields[action] - {'action'}: raise ValueError('Unsupported calendar action or field.')
    data = deepcopy(read(world)); current = data['directory'].get(actor)
    if action == 'register':
        if type(payload.get('available')) is not bool: raise ValueError('Choose whether to accept invitations.')
        label = text(payload.get('label', player.name), 'Invitation label', 80)
        if payload['available'] and any(i != actor and row.get('available') and row['label'].casefold() == label.casefold() for i,row in data['directory'].items()):
            raise ValueError('That invitation label is already used. Choose a distinct label; your character name stays unchanged.')
        if actor not in data['directory'] and len(data['directory']) >= cfg['max_directory']: raise ValueError('This world invitation directory is full. Ask the host about its calendar limits.')
        data['directory'][actor] = dict(name=player.name, label=label, available=payload['available'])
    else:
        if action == 'create':
            token=payload.get('client_token')
            if not isinstance(token,str) or not re.fullmatch(r'[a-f0-9]{32}',token):raise ValueError('Start a new event draft before submitting.')
            fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            previous=next((e for e in data['events'].values() if e['owner']==actor and e.get('creation_token')==token),None)
            if previous is not None:
                if previous.get('creation_fingerprint')!=fingerprint:raise ValueError('That draft was already submitted with different details. Refresh the calendar.')
                return data
            if not current or not current.get('available'): raise ValueError('Register an invitation label before creating events.')
            if len(data['events']) >= cfg['max_events']: raise ValueError('This world calendar is full. Ask the host about its calendar limits.')
            if sum(e['owner'] == actor and e['status'] == 'scheduled' and instant(e['ends_at']) > now for e in data['events'].values()) >= cfg['max_owner_events']: raise ValueError('You already have too many upcoming events.')
            ident = new_id or uuid.uuid4().hex
            if ident in data['events']: raise ValueError('Event identity conflict. Try again.')
            event = dict(id=ident, owner=actor, revision=0, created_at=stamp(now), status='scheduled',creation_token=token,creation_fingerprint=fingerprint)
        else:
            event = _event(data, payload.get('id'), actor);_revision(event, payload.get('revision'))
            if event['status'] != 'scheduled': raise ValueError('This event has already been cancelled.')
            if action in ('edit','cancel') and event['owner'] != actor: raise ValueError('Only the event owner can edit or cancel it.')
        if action in ('create', 'edit'):
            starts = local_time(payload.get('start_local'), payload.get('timezone'), payload.get('start_fold'))
            ends = local_time(payload.get('end_local'), payload.get('timezone'), payload.get('end_fold'))
            start, end = instant(starts), instant(ends)
            if start < now: raise ValueError('Choose a future start time; this calendar uses the server real-world clock.')
            if start - now > cfg['max_ahead_days'] * 86400: raise ValueError('This event is farther ahead than this world permits.')
            if not 60 <= end - start <= cfg['max_duration_hours'] * 3600: raise ValueError('Event duration must be at least one minute and within this world duration limit.')
            invited = payload.get('invitees', [])
            if not isinstance(invited, list) or len(invited) > cfg['max_invitees'] or any(not isinstance(i, str) for i in invited): raise ValueError('Choose a bounded list of invited players.')
            invited = list(dict.fromkeys(i for i in invited if i != actor))
            previous = event.get('participants', {})
            if any(i not in data['directory'] or not data['directory'][i].get('available') and i not in previous for i in invited): raise ValueError('An invited player is no longer accepting new invitations. Refresh the directory.')
            people = {}
            for ident in [actor, *invited]:
                row = data['directory'].get(ident) or previous.get(ident)
                if not row: raise ValueError('A participant is no longer available.')
                people[ident] = dict(name=row['name'], label=row['label'], response='accepted' if ident == actor else 'pending')
            event.update(title=text(payload.get('title',''), 'Event title', 100),notes=text(payload.get('notes',''), 'Notes', 1000, True),
                         expanse_note=text(payload.get('expanse_note',''), 'Optional Expanse-time note', 160, True),timezone=payload['timezone'],
                         starts_at=starts, ends_at=ends, participants=people)
        elif action == 'cancel': event['status'] = 'cancelled'
        elif action == 'respond':
            if actor == event['owner']: raise ValueError('The owner can cancel the event instead of declining it.')
            if payload.get('response') not in ('accepted','declined'): raise ValueError('Choose Accept or Decline.')
            if instant(event['ends_at']) <= now: raise ValueError('This event has ended.')
            event['participants'][actor]['response'] = payload['response']
        event['revision'] += 1; event['updated_at'] = stamp(now); data['events'][event['id']] = event
    data['revision'] += 1
    return data


def validate_store(data):
    """Refuse malformed saved calendar data rather than resetting it."""
    try:
        if len(data['directory'])>10000 or len(data['events'])>10000:raise ValueError()
        labels=[p.get('label','').casefold() for p in data['directory'].values() if isinstance(p,dict) and p.get('available') and isinstance(p.get('label'),str)]
        if len(labels)!=len(set(labels)):raise ValueError()
        if type(data.get('revision')) is not int or data['revision'] < 0: raise ValueError()
        for ident,row in data['directory'].items():
            if not isinstance(ident,str) or not ident or not isinstance(row,dict) or type(row.get('available')) is not bool: raise ValueError()
            text(row.get('name'), 'Character name', 200);text(row.get('label'), 'Invitation label', 80)
        for ident,event in data['events'].items():
            if not isinstance(ident,str) or not isinstance(event,dict) or event.get('id') != ident: raise ValueError()
            if not isinstance(event.get('creation_token'),str) or not re.fullmatch(r'[a-f0-9]{32}',event['creation_token']) or not isinstance(event.get('creation_fingerprint'),str) or not re.fullmatch(r'[a-f0-9]{64}',event['creation_fingerprint']):raise ValueError()
            if type(event.get('revision')) is not int or event['revision'] < 1 or event.get('status') not in ('scheduled','cancelled'): raise ValueError()
            people=event.get('participants')
            if not isinstance(people,dict) or len(people)>33 or not isinstance(event.get('owner'),str) or event['owner'] not in people: raise ValueError()
            for pid,row in people.items():
                if not isinstance(pid,str) or not isinstance(row,dict) or row.get('response') not in ('pending','accepted','declined'): raise ValueError()
                text(row.get('name'),'Character name',200);text(row.get('label'),'Invitation label',80)
            if people[event['owner']]['response']!='accepted':raise ValueError()
            text(event.get('title'),'Event title',100);text(event.get('notes'),'Notes',1000,True);text(event.get('expanse_note'),'Expanse-time note',160,True)
            zone(event.get('timezone'))
            if instant(event.get('ends_at')) <= instant(event.get('starts_at')): raise ValueError()
            instant(event.get('updated_at'));instant(event.get('created_at'))
    except (ValueError,TypeError,KeyError,OverflowError,OSError):
        raise ValueError('Calendar save needs recovery; its contents have not been reset.') from None
