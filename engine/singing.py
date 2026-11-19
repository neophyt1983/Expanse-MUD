"""Authored songs, individual voices and brief local performances.

Songbooks and instruments are ordinary game-file items. No culture, lyrics,
melody, stock, reward or automatic checkpoint is created by this interpreter.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import math
from time import monotonic
from uuid import uuid4

KEY = 'singing_v1'
EVENT_SECONDS = 20
EVENT_ROOMS = 128
CONTEXTS = ('work', 'leisure', 'performance', 'festival')


def config(world):
    value = getattr(world, 'metadata', {}).get('singing', {})
    return value if isinstance(value, dict) else {}


def enabled(world):
    return config(world).get('version') == 1 and config(world).get('enabled') is True


def _definition(world, person):
    return getattr(world, 'npcs', {}).get(person.source_def, {}) if not person.is_player else {}


def _race(world, person):
    row = _definition(world, person)
    ident = person.race or row.get('race') or row.get('social_profile', {}).get('species')
    return getattr(world, 'races', {}).get(ident, {}).get('singing', {})


def voice(world, person):
    """Project the same individual choice without changing saved progress."""
    choices = _race(world, person).get('voices', [])
    if not choices:
        return {'id': '', 'label': '', 'transpose': 0}
    by_id = {row['id']: row for row in choices}
    explicit = _definition(world, person).get('singing', {}).get('voice')
    saved = person.progress.get(KEY, {}).get('voice')
    if explicit in by_id:
        return by_id[explicit]
    if saved in by_id:
        return by_id[saved]
    index = int.from_bytes(sha256(('singing:' + person.id).encode()).digest()[:8], 'big') % len(choices)
    return choices[index]


def repertoire(world, person):
    """Only authored starting songs and physically accessed/read songbooks."""
    ids = [*_race(world, person).get('songs', []),
           *_definition(world, person).get('singing', {}).get('songs', []),
           *person.inventory]
    room = world.rooms.get(person.location)
    # A player can deliberately sing from an open local score. Autonomous
    # residents do not silently learn every book on a mixed public shelf.
    if room and person.is_player:
        ids.extend(room.items)
    ids.extend(key[5:] for key, count in person.progress.get('actions', {}).items()
               if count and key.startswith('read:'))
    return [world.items[ident] for ident in dict.fromkeys(ids)
            if ident in world.items and world.items[ident].get('song')]


def _minute(world):
    return getattr(world, 'living_state', {}).get('minute', 0)


def _festival_active(world, festival):
    """An authored celebration on Expanse's nine-day calendar, not wall time."""
    from engine import worldtime
    minute = _minute(world)
    clock = minute % worldtime.MINUTES_PER_DAY
    weekday = (minute // worldtime.MINUTES_PER_DAY) % worldtime.DAYS_PER_WEEK + 1
    return (weekday == festival.get('weekday')
            and festival['start_minute'] <= clock < festival['end_minute'])


def festival_for(world, person):
    """Return a real scheduled festival the NPC is assigned to attend."""
    if not enabled(world) or person.is_player:
        return None
    singer = _definition(world, person).get('singing', {})
    if 'festival' not in singer.get('contexts', ()):
        return None
    ids = singer.get('festivals', [])
    if not ids:
        return None
    for festival in config(world).get('festivals', []):
        if festival['id'] in ids and _festival_active(world, festival):
            return festival
    return None


def festival_at(world, room_id):
    """Read-only view of an active authored festival at this actual location."""
    if not enabled(world):
        return None
    return next((festival for festival in config(world).get('festivals', [])
                 if festival['room'] == room_id and _festival_active(world, festival)), None)


def _available(world, person, *, attention=True):
    if not person.alive or person.location not in world.rooms:
        return False
    from engine import livelihoods, relationships, sleep_movement
    if not person.is_player and (not relationships.sentient(world, person) or not livelihoods.awake(world, person)):
        return False
    if sleep_movement.asleep(world, person):
        return False
    if person.progress.get('restrained_until', 0) > _minute(world):
        return False
    fighting = getattr(person, '_fight_display', None)
    if fighting and fighting[0] == person.location and fighting[1] > monotonic():
        return False
    if not person.is_player and attention:
        from engine import npc_attention
        if npc_attention.paused(world, person):
            return False
    return True


def _partners(world, lead, song_id, count):
    if not count:
        return []
    from engine import society
    found = []
    for person in sorted(world.entities_in_room(lead.location), key=lambda actor: actor.id):
        if person.id == lead.id or person.is_player:
            continue
        if not _definition(world, person).get('singing', {}).get('respond', False):
            continue
        if _minute(world) < person.progress.get(KEY, {}).get('next_minute', -1):
            continue
        if (not _available(world, person)
                or min(society.friendliness(world, lead, person), society.friendliness(world, person, lead)) < 50):
            continue
        if song_id not in {row['id'] for row in repertoire(world, person)}:
            continue
        found.append(person)
        if len(found) == count:
            break
    return found


def _instruments(world, people):
    found = {}
    for person in people:
        for ident in person.inventory:
            item = world.items.get(ident, {})
            tag = item.get('instrument', {}).get('tag')
            if tag:
                found.setdefault(tag, (person, ident))
    return found


def _score(authored, people, voices, instruments, form):
    if not authored or not authored.get('tracks'):
        return None
    result = {'version': 1, 'tempo': authored['tempo'], 'tracks': []}
    for original in authored['tracks']:
        role = original['role']
        track = deepcopy(original)
        if role == 'accompaniment':
            played = instruments.get(original['instrument'])
            if not played:
                continue
            person, ident = played
            track.update(performer_id=person.id, item_id=ident)
        else:
            index = 0 if role == 'lead' else 1 if role == 'response' else original['participant']
            if (index >= len(people) or role == 'response' and form != 'call_response'
                    or role == 'relay' and form != 'relay'):
                continue
            track['performer_id'] = people[index].id
            transpose = voices[index]['transpose']
            track['notes'] = [[midi + transpose, start, duration, velocity]
                              for midi, start, duration, velocity in original['notes']]
            if any(not 24 <= note[0] <= 108 for note in track['notes']):
                # A stale/unvalidated authoring revision must not emit an
                # invalid score or silently alter the intended melody.
                continue
        result['tracks'].append(track)
    return result if result['tracks'] else None


def _events(world):
    events = getattr(world, '_singing_events', None)
    if events is None:
        events = world._singing_events = OrderedDict()
    return events


def clear(world):
    """Discard transient cues when the owning world/session is discarded."""
    for name in ('_singing_events', '_singing_player_times'):
        if hasattr(world, name):
            delattr(world, name)


def _perform(world, lead, song=None, *, occasion=None):
    if not _available(world, lead):
        raise ValueError('Sing when you are awake, safe and available.')
    cfg = config(world)
    now = monotonic()
    if lead.is_player:
        times = getattr(world, '_singing_player_times', {})
        if now - times.get(lead.id, -1000000) < cfg.get('player_interval_seconds', 5):
            raise ValueError('Let the last phrase finish before singing again.')
    state = lead.progress.get(KEY, {})
    sequence = state.get('sequence', 0)
    authored = song['song'] if song else cfg.get('wordless', {})
    title = song['name'] if song else authored.get('title', 'Wordless singing')
    form = authored.get('form', 'solo')
    verse_count = state.get('verses', {}).get(song['id'], 0) if song else 0
    verse = authored['verses'][verse_count % len(authored['verses'])] if song else {}
    successors = ([verse['response']] if form == 'call_response'
                  else verse.get('relay', []) if form == 'relay' else [])
    others = _partners(world, lead, song['id'], len(successors)) if successors else []
    people = [lead, *others]
    voices = [voice(world, person) for person in people]
    instruments = _instruments(world, people)
    score = _score(authored.get('score'), people, voices, instruments, form)
    actual_tags = list(dict.fromkeys(track['instrument'] for track in (score or {}).get('tracks', [])
                                   if track['role'] == 'accompaniment'))
    # Unscored songs can still describe genuinely carried preferred instruments.
    if not authored.get('score'):
        actual_tags = [tag for tag in _race(world, lead).get('preferred_instruments', []) if tag in instruments]
    names = [world.items[instruments[tag][1]].get('name', instruments[tag][1]) for tag in actual_tags]
    register = ' in a ' + voices[0]['label'] + ' voice' if voices[0]['label'] else ''
    style = authored.get('style', '')
    text = lead.name + (' sings “' + title + '”' if song else ' sings without words') + register + '.'
    if occasion:
        text += ' During ' + occasion['name'] + ' at ' + world.rooms[lead.location].name + '.'
    if style:
        text += ' ' + style
    if names:
        named_players = [person.name + ' plays ' + world.items[ident].get('name', ident)
                         for tag, (person, ident) in instruments.items() if tag in actual_tags]
        text += ' ' + '; '.join(named_players) + '.'
    else:
        text += ' Unaccompanied.'
    lyrics = []
    if verse:
        text += '\n' + lead.name + ': “' + verse['call'] + '”'
        lyrics.append(dict(text=verse['call'], role='call', performer_id=lead.id))
    for person, words in zip(others, successors):
        text += '\n' + person.name + (' answers' if form == 'call_response' else ' passes the tune on') + ': “' + words + '”'
        lyrics.append(dict(text=words, role='response' if form == 'call_response' else 'relay', performer_id=person.id))
    if len(others) < len(successors):
        text += '\n' + ('The answering line waits for another singer.' if form == 'call_response'
                         else 'The relay pauses until another singer can join.')
    minute = _minute(world)
    from engine import npc_activity
    for index, person in enumerate(people):
        progress = person.progress.setdefault(KEY, {})
        if voices[index]['id']:
            progress['voice'] = voices[index]['id']
        progress['last_song'] = song['id'] if song else ''
        npc_cfg = _definition(world, person).get('singing', {})
        interval = (cfg.get('festival_npc_interval_minutes', 30) if occasion
                    else npc_cfg.get('interval_minutes', cfg.get('npc_interval_minutes', 60)))
        progress['next_minute'] = minute + interval
        person_instruments = [world.items[ident].get('name', ident)
                              for tag, (holder, ident) in instruments.items()
                              if tag in actual_tags and holder.id == person.id]
        label = 'Singing ' + title + (' and playing ' + ', '.join(person_instruments) if person_instruments else '')
        npc_activity.note(person, 'music', label, EVENT_SECONDS)
    lead.progress[KEY]['sequence'] = sequence + 1
    if song:
        verses = lead.progress[KEY].setdefault('verses', {})
        verses.pop(song['id'], None)
        verses[song['id']] = verse_count + 1
        while len(verses) > 128:
            del verses[next(iter(verses))]
    if lead.is_player:
        times = getattr(world, '_singing_player_times', None)
        if times is None:
            times = world._singing_player_times = OrderedDict()
        times.pop(lead.id, None)
        times[lead.id] = now
        while len(times) > EVENT_ROOMS:
            times.popitem(last=False)
        if not hasattr(world, 'dirty_players'):
            world.dirty_players = set()
        world.dirty_players.add(lead.id)
    roles = ['lead'] + [('response' if form == 'call_response' else 'relay')] * len(others)
    players = [dict(performer_id=holder.id, performer=holder.name,
                    item_id=ident, instrument=world.items[ident].get('name', ident))
               for tag, (holder, ident) in instruments.items() if tag in actual_tags]
    event = dict(id=uuid4().hex, room_id=lead.location, title=title, rendering='synthesized', score=score,
                 performers=[dict(id=person.id, name=person.name, role=role, voice=chosen['label'])
                             for person, role, chosen in zip(people, roles, voices)], lyrics=lyrics,
                 instruments=players, festival=occasion['name'] if occasion else None)
    events = _events(world)
    for room, entry in list(events.items()):
        if now - entry['created'] >= EVENT_SECONDS and entry['next_minute'] <= minute:
            del events[room]
    events.pop(lead.location, None)
    room_interval = cfg.get('festival_room_interval_minutes', 10) if occasion else cfg.get('room_interval_minutes', 15)
    events[lead.location] = dict(created=now, next_minute=minute + room_interval, event=event)
    while len(events) > EVENT_ROOMS:
        events.popitem(last=False)
    excluded = lead.id if lead.is_player else None
    world.runtime_notifications = (getattr(world, 'runtime_notifications', []) + [(lead.location, text, excluded)])[-500:]
    if getattr(world, 'living_state', {}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(world, [person.id for person in people], text)
    return text


def npc_step(world, person, context):
    """Called within an existing stationary routine, never a new global scan."""
    if not enabled(world) or person.is_player:
        return False
    cfg = _definition(world, person).get('singing', {})
    if context not in cfg.get('contexts', []):
        return False
    festival = festival_for(world, person) if context == 'festival' else None
    if context == 'festival' and (not festival or person.location != festival['room']):
        return False
    minute = _minute(world)
    if minute < person.progress.get(KEY, {}).get('next_minute', -1):
        return False
    current = getattr(world, '_singing_events', {}).get(person.location)
    if current and (minute < current['next_minute'] or monotonic() - current['created'] < EVENT_SECONDS):
        return False
    if not _available(world, person):
        return False
    songs = repertoire(world, person)
    sequence = person.progress.get(KEY, {}).get('sequence', 0)
    _perform(world, person, songs[sequence % len(songs)] if songs else None, occasion=festival)
    return True


def view(world, viewer):
    """Read-only, same-room projection; neither starts nor restores a cue."""
    if not enabled(world):
        return {'events': []}
    # Projection copies the small clock container: observing must not mutate state.
    class Projection:
        def __init__(self, original):
            self.original = original
            self.living_state = dict(getattr(original, 'living_state', {}))

        def __getattr__(self, name):
            return getattr(self.original, name)

    projected = Projection(world)
    festival = festival_at(world, viewer.location)
    result = {'events': []}
    if festival:
        # Only actual, locally present artists appear; no fabricated crowd.
        present = []
        for person in world.entities_in_room(viewer.location):
            if (not person.is_player and _available(projected, person, attention=False)
                    and (assigned := festival_for(world, person))
                    and assigned['id'] == festival['id']):
                carried = [world.items[ident].get('name', ident) for ident in person.inventory
                           if world.items.get(ident, {}).get('instrument', {}).get('tag')]
                present.append(dict(name=person.name, instruments=list(dict.fromkeys(carried))[:3]))
                if len(present) >= 12:
                    break
        result['festival'] = dict(id=festival['id'], name=festival['name'],
                                  description=festival.get('description', ''), performers=present)
    entry = getattr(world, '_singing_events', {}).get(viewer.location)
    if not entry or not entry['event'].get('score'):
        return result
    age = monotonic() - entry['created']
    if not 0 <= age < EVENT_SECONDS:
        return result
    for performer in entry['event']['performers']:
        person = world.entities.get(performer['id'])
        if not person or person.location != viewer.location or not _available(projected, person, attention=False):
            # End the whole short phrase coherently rather than leaving
            # orphaned responses, instruments or lyrics from departed people.
            return result
    for track in entry['event']['score']['tracks']:
        if track.get('item_id') and track['item_id'] not in world.entities[track['performer_id']].inventory:
            return result
    cue = deepcopy(entry['event'])
    cue['age_seconds'] = round(age, 3)
    result['events'] = [cue]
    return result


def songs_command(ctx, args):
    ctx.time_accounted = True
    songs = repertoire(ctx.world, ctx.player)
    if args.strip():
        words = args.strip().casefold()
        songs = [row for row in songs if words in (row['id'] + ' ' + row['name']).casefold()]
    chosen = voice(ctx.world, ctx.player)
    lines = ['Available songs' + (' — ' + chosen['label'] + ' voice' if chosen['label'] else '')]
    lines += ['• ' + row['name'] for row in songs[:64]]
    if len(songs) > 64:
        lines.append('Use songs <words> to narrow the list.')
    lines.append('Use sing <song title> to sing a listed song.' if songs
                 else 'Read or carry a songbook to learn a song. You can sing without words now.')
    return '\n'.join(lines)


def sing_command(ctx, args):
    songs = repertoire(ctx.world, ctx.player)
    if args.strip():
        from engine import item_catalog
        song = item_catalog.choose(songs, args.strip(), missing='That song is not in your repertoire. Read or carry its songbook first.')
    else:
        sequence = ctx.player.progress.get(KEY, {}).get('sequence', 0)
        song = songs[sequence % len(songs)] if songs else None
    return _perform(ctx.world, ctx.player, song)


def register(registry):
    from engine.commands import Command
    registry.register(Command('songs', 'List your available songs', 'songs [words]', songs_command,
                              available=lambda ctx: enabled(ctx.world), example='songs'))
    registry.register(Command('sing', 'Sing an available song', 'sing [song title]', sing_command,
                              available=lambda ctx: enabled(ctx.world), example='sing'))


def validate(data, metadata):
    """Validate optional authored data without modifying it or any world."""
    issues = []
    items = {row.get('id'): row for row in data.get('item', []) if isinstance(row, dict)}
    races = {row.get('id'): row for row in data.get('race', []) if isinstance(row, dict)}
    transpose_values = {0}
    tags = set()
    voice_pools = {}

    def error(where, text):
        issues.append(where + ': ' + text)

    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    def text(value, limit=240, *, empty=False):
        return isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= limit

    def object_field(row, field, where):
        value = row.get(field, {})
        if not isinstance(value, dict):
            error(where, field + ' must be an object')
            return {}
        return value

    def strings(value, where, limit=64):
        if not isinstance(value, list) or len(value) > limit or any(not text(entry, 128) for entry in value):
            error(where, 'expected at most ' + str(limit) + ' nonempty identifiers')
            return []
        if len(value) != len(set(value)):
            error(where, 'duplicate identifiers')
        return value

    def song_ids(value, where):
        for ident in strings(value, where):
            if not items.get(ident, {}).get('song'):
                error(where, 'unknown songbook ' + ident)

    for ident, row in items.items():
        instrument = object_field(row, 'instrument', str(ident))
        if instrument:
            if not text(instrument.get('tag'), 128):
                error(str(ident), 'instrument needs a nonempty tag')
            else:
                tags.add(instrument['tag'])
    for ident, row in races.items():
        where = str(ident) + '.singing'
        cfg = object_field(row, 'singing', str(ident))
        for key in ('tradition', 'style'):
            if key in cfg and not text(cfg[key], empty=True):
                error(where, key + ' must be text of at most 240 characters')
        voices = cfg.get('voices', [])
        if not isinstance(voices, list) or len(voices) > 32:
            error(where, 'voices must be a list of at most 32 registers')
            voices = []
        seen = set()
        voice_pools[ident] = seen
        for voice_row in voices:
            if (not isinstance(voice_row, dict) or not text(voice_row.get('id'), 128)
                    or not text(voice_row.get('label'), 80) or type(voice_row.get('transpose')) is not int
                    or not -36 <= voice_row['transpose'] <= 36):
                error(where, 'each voice needs id, label and integer transpose −36–36')
                continue
            if voice_row['id'] in seen:
                error(where, 'duplicate voice ' + voice_row['id'])
            seen.add(voice_row['id'])
            transpose_values.add(voice_row['transpose'])
        song_ids(cfg.get('songs', []), where + '.songs')
        for tag in strings(cfg.get('preferred_instruments', []), where + '.preferred_instruments'):
            if tag not in tags:
                error(where, 'unknown instrument tag ' + tag)
    festival_ids = set()
    festivals = getattr(metadata, 'get', lambda key, default: default)('singing', {}).get('festivals', [])
    if not isinstance(festivals, list) or len(festivals) > 32:
        error('metadata.singing.festivals', 'must be a list of at most 32 festivals')
        festivals = []
    known_rooms = {room.get('id') for room in data.get('room', []) if isinstance(room, dict)}
    for festival in festivals:
        where = 'metadata.singing.festivals'
        if not isinstance(festival, dict):
            error(where, 'each festival must be an object')
            continue
        ident = festival.get('id')
        if not text(ident, 128) or ident in festival_ids:
            error(where, 'festival needs a unique identifier')
        else:
            festival_ids.add(ident)
        if not text(festival.get('name'), 120) or not text(festival.get('description', ''), 240, empty=True):
            error(where, 'festival needs a name and optional short description')
        if festival.get('room') not in known_rooms:
            error(where, 'festival venue must refer to an authored room')
        if type(festival.get('weekday')) is not int or not 1 <= festival['weekday'] <= 9:
            error(where, 'weekday must be 1–9 on the Expanse calendar')
        start, end = festival.get('start_minute'), festival.get('end_minute')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1500:
            error(where, 'festival requires a same-day interval from 0 to 1500 minutes')

    for row in data.get('npc', []):
        where = str(row.get('id')) + '.singing'
        cfg = object_field(row, 'singing', str(row.get('id')))
        song_ids(cfg.get('songs', []), where + '.songs')
        contexts = strings(cfg.get('contexts', []), where + '.contexts', 4)
        if any(context not in CONTEXTS for context in contexts):
            error(where, 'contexts must be work, leisure, performance or festival')
        for festival_id in strings(cfg.get('festivals', []), where + '.festivals', 8):
            if festival_id not in festival_ids:
                error(where, 'unknown festival ' + festival_id)
        if 'respond' in cfg and type(cfg['respond']) is not bool:
            error(where, 'respond must be true or false')
        if 'interval_minutes' in cfg and (type(cfg['interval_minutes']) is not int or not 1 <= cfg['interval_minutes'] <= 1500):
            error(where, 'interval_minutes must be 1–1500')
        if 'voice' in cfg and not isinstance(cfg['voice'], str):
            error(where, 'voice must be a register identifier')
        elif cfg.get('voice'):
            race = row.get('race') or row.get('social_profile', {}).get('species')
            if cfg['voice'] not in voice_pools.get(race, set()):
                error(where, 'voice must name a register in this NPC race')

    def score(value, where, form, successor_count):
        if value in (None, {}):
            return
        if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
                or not number(value.get('tempo'), 40, 240)):
            error(where, 'score needs version 1 and tempo 40–240')
            return
        tracks = value.get('tracks')
        if not isinstance(tracks, list) or not 1 <= len(tracks) <= 8:
            error(where, 'score needs 1–8 tracks')
            return
        total = 0
        for index, track in enumerate(tracks):
            at = where + '.tracks[' + str(index) + ']'
            if not isinstance(track, dict):
                error(at, 'track must be an object')
                continue
            role = track.get('role')
            if role not in ('lead', 'response', 'relay', 'accompaniment'):
                error(at, 'invalid role')
            if role == 'response' and form != 'call_response':
                error(at, 'response track needs call_response form')
            if role == 'relay' and (form != 'relay' or type(track.get('participant')) is not int
                                    or not 1 <= track['participant'] <= successor_count):
                error(at, 'relay participant must name an authored successor')
            if role == 'accompaniment' and (not isinstance(track.get('instrument'), str) or track['instrument'] not in tags):
                error(at, 'accompaniment needs an existing instrument tag')
            timbre = track.get('timbre')
            if timbre not in ('periodic', 'noise') or role != 'accompaniment' and timbre != 'periodic':
                error(at, 'voices use periodic timbre; accompaniment uses periodic or noise')
            if not number(track.get('gain'), 0, 1):
                error(at, 'gain must be 0–1')
            if timbre == 'periodic':
                harmonics = track.get('harmonics')
                if (not isinstance(harmonics, list) or not 1 <= len(harmonics) <= 16
                        or any(not number(x, 0, 1) for x in harmonics) or not any(harmonics)):
                    error(at, 'periodic timbre needs 1–16 harmonic amplitudes in 0–1')
            envelope = track.get('envelope')
            if (not isinstance(envelope, dict) or any(not number(envelope.get(key), 0, limit)
                    for key, limit in (('attack', 1), ('decay', 2), ('sustain', 1), ('release', 2)))):
                error(at, 'invalid attack/decay/sustain/release envelope')
                envelope = {'release': 0}
            notes = track.get('notes')
            if not isinstance(notes, list) or not notes:
                error(at, 'notes must be a nonempty list')
                continue
            total += len(notes)
            if len(notes) > 128:
                error(at, 'track exceeds the 128-note score budget')
                continue
            for note in notes:
                if (not isinstance(note, list) or len(note) != 4 or type(note[0]) is not int
                        or not 24 <= note[0] <= 108 or not number(note[1], 0, 80)
                        or not number(note[2], .001, 80) or not number(note[3], 0, 1)):
                    error(at, 'notes use [MIDI 24–108, nonnegative start, positive duration, velocity 0–1]')
                    continue
                if (note[1] + note[2]) * 60 / value['tempo'] + envelope['release'] > EVENT_SECONDS:
                    error(at, 'score exceeds 20 seconds including release')
                if role != 'accompaniment' and any(not 24 <= note[0] + shift <= 108 for shift in transpose_values):
                    error(at, 'voice note exceeds MIDI 24–108 after an authored individual transpose')
        if total > 128:
            error(where, 'score exceeds 128 total notes')

    for ident, row in items.items():
        where = str(ident) + '.song'
        song = object_field(row, 'song', str(ident))
        if not song:
            continue
        if not text(row.get('read_text'), 100000):
            error(where, 'a songbook must contain readable authored text')
        form = song.get('form', 'solo')
        if form not in ('solo', 'call_response', 'relay'):
            error(where, 'form must be solo, call_response or relay')
        for key in ('tradition', 'style'):
            if key in song and not text(song[key], empty=True):
                error(where, key + ' must be text of at most 240 characters')
        verses = song.get('verses')
        if not isinstance(verses, list) or not 1 <= len(verses) <= 16:
            error(where, 'verses must have 1–16 entries')
            verses = []
        successor_counts = []
        for verse in verses:
            if not isinstance(verse, dict) or not text(verse.get('call')):
                error(where, 'each verse needs a nonempty call of at most 240 characters')
                continue
            if form == 'solo' and ('response' in verse or 'relay' in verse):
                error(where, 'solo verses cannot claim answering singers')
            if form == 'call_response':
                if not text(verse.get('response')) or 'relay' in verse:
                    error(where, 'call_response verses need one response and no relay')
                successor_counts.append(1)
            if form == 'relay':
                lines = verse.get('relay')
                if (not isinstance(lines, list) or not 1 <= len(lines) <= 3
                        or any(not text(line) for line in lines) or 'response' in verse):
                    error(where, 'relay verses need 1–3 successor lines and no response')
                else:
                    successor_counts.append(len(lines))
        score(song.get('score'), where, form, min(successor_counts, default=0))

    cfg = object_field(metadata, 'singing', 'metadata')
    if cfg:
        if type(cfg.get('version')) is not int or cfg['version'] != 1 or type(cfg.get('enabled')) is not bool:
            error('metadata.singing', 'requires version 1 and boolean enabled')
        for key, maximum in (('npc_interval_minutes', 1500), ('room_interval_minutes', 1500),
                             ('festival_npc_interval_minutes', 1500), ('festival_room_interval_minutes', 1500),
                             ('player_interval_seconds', 60)):
            if key in cfg and (type(cfg[key]) is not int or not 1 <= cfg[key] <= maximum):
                error('metadata.singing', key + ' must be 1–' + str(maximum))
        wordless = cfg.get('wordless', {})
        if not isinstance(wordless, dict):
            error('metadata.singing', 'wordless must be an object')
        elif wordless:
            if not text(wordless.get('title'), 128):
                error('metadata.singing.wordless', 'requires an authored title')
            if any(key in wordless for key in ('style', 'tradition', 'verses')):
                error('metadata.singing.wordless', 'neutral wordless singing has no style, tradition or lyrics')
            score(wordless.get('score'), 'metadata.singing.wordless', 'solo', 0)
    return issues
