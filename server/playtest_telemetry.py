"""Private, bounded playtest observations, separate from gameplay checkpoints.

Only the authenticated private worker opens a Store.  No method accepts an
account or an arbitrary storage path from a player request.  Command/chat text,
passwords, tokens and complete server responses are never written here.
"""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
import html
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

FILENAME = 'playtest.sqlite3'
RETENTION_DAYS = 30
MAX_SESSIONS = 100
MAX_EVENTS = 1500
MAX_PLACES = 300
MAX_TARGETS = 160
ACTIVE_WINDOW = 60.0
HEARTBEAT_GAP = 45.0
NOTICE = ('Playtest collection is on: actions, places visited, active-time estimates, '
          'injuries and errors help improve Expanse. Passwords and conversation text '
          'are not collected. The feedback form is optional.')
UNAVAILABLE_NOTICE = ('Playtest collection is unavailable for this session. You can still play '
                      'and save normally, but playtest feedback cannot be stored.')
TEXT_FIELDS = ('liked', 'disliked', 'next_goal', 'avoided_places', 'avoided_why')
RATINGS = ('enjoyment', 'clarity', 'difficulty')
MOVEMENT = frozenset(('go', 'north', 'south', 'east', 'west', 'northeast',
    'northwest', 'southeast', 'southwest', 'up', 'down', 'in', 'out',
    'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'u', 'd'))
INTERACTIONS = frozenset(('talk', 'ask', 'attack', 'hit', 'give', 'feed', 'treat',
    'pet', 'play', 'companion', 'friend', 'trade', 'buy', 'sell', 'inspect',
    'observe', 'wake', 'social', 'cast', 'challenge', 'tame', 'heal'))
READING = frozenset(('look', 'read', 'bookshelves', 'chronicles', 'newspaper',
    'guide', 'help', 'journal', 'quests', 'adventures', 'catalog', 'survey',
    'condition', 'status', 'score', 'inventory', 'recipes', 'wardrobe', 'abilities'))
KNOWN = MOVEMENT | INTERACTIONS | READING | frozenset(('save', 'save_exit', 'resume',
    'accept', 'complete', 'quest', 'use', 'eat', 'drink', 'equip', 'unequip', 'take',
    'drop', 'get', 'rest', 'sleep', 'revive', 'flee', 'run', 'craft', 'gather',
    'harvest', 'work', 'lock', 'unlock', 'open', 'close', 'route', 'equipment',
    'locks', 'calendar', 'ui', 'say', 'whisper', 'emote', 'local', 'resident'))
BACKGROUND = ('map', 'world asset', 'public chart', 'travel map window',
              'atlas refresh', 'atlas open', 'atlas close')
TOPICS = frozenset(('work', 'activities', 'plans', 'news', 'relationships',
    'feelings', 'quest', 'quests', 'stories', 'memories', 'gossip', 'history',
    'family', 'weather', 'trade', 'health'))


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _label(value, length=160):
    # Values passed here are authored/server-resolved names, never raw commands.
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value or ''))[:length]


def _utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')


def _number(value, default=0):
    return value if type(value) in (int, float) else default


class Store:
    """A single account/world's analytics.  It never opens a gameplay database."""

    def __init__(self, directory, *, clock=time.time, max_sessions=MAX_SESSIONS,
                 max_events=MAX_EVENTS, retention_days=RETENTION_DAYS):
        self.clock = clock
        self.max_sessions = max(1, min(MAX_SESSIONS, int(max_sessions)))
        self.max_events = max(1, min(MAX_EVENTS, int(max_events)))
        self.retention_days = max(1, min(RETENTION_DAYS, int(retention_days)))
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / FILENAME
        if self.path.exists() or self.path.is_symlink():
            self._check_existing()
        self.db = sqlite3.connect(self.path, timeout=2)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, player TEXT NOT NULL, game TEXT NOT NULL,
                started REAL NOT NULL, updated REAL NOT NULL, ended REAL,
                reason TEXT, summary TEXT NOT NULL,
                feedback_state TEXT NOT NULL DEFAULT 'none', feedback TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL, at REAL NOT NULL, kind TEXT NOT NULL,
                data TEXT NOT NULL, PRIMARY KEY(session, seq)
            );
            CREATE INDEX IF NOT EXISTS session_dates ON sessions(started);
            ''')
            # A worker restart does not pretend that a disconnected tab kept playing.
            self.db.execute("UPDATE sessions SET ended=updated, reason='interrupted' WHERE ended IS NULL")
            self.prune()
        except BaseException:
            self.db.close()
            raise

    def _check_existing(self):
        """Reject damaged/unrecognized stores before any writable connection.

        A read-only check may fail when recovery would require a write. That is
        intentionally an unavailable analytics store, not permission to repair,
        replace, truncate or delete the player's original analytics file.
        """
        if self.path.is_symlink() or not self.path.is_file():
            raise OSError('The analytics file is unavailable.')
        connection = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
        try:
            result = connection.execute('PRAGMA quick_check(1)').fetchall()
            if result != [('ok',)]:
                raise sqlite3.DatabaseError('Analytics integrity check failed.')
            connection.execute('SELECT id,player,game,started,updated,ended,reason,summary,feedback_state,feedback FROM sessions LIMIT 0')
            connection.execute('SELECT session,seq,at,kind,data FROM events LIMIT 0')
        finally:
            connection.close()

    def prune(self):
        self.db.execute('DELETE FROM sessions WHERE updated < ?',
                        (self.clock() - self.retention_days * 86400,))
        self.db.execute('DELETE FROM sessions WHERE id IN (SELECT id FROM sessions '
                        'ORDER BY started DESC LIMIT -1 OFFSET ?)', (self.max_sessions,))
        self.db.commit()

    def create(self, player, game, summary):
        sid, now = uuid.uuid4().hex, self.clock()
        self.db.execute('INSERT INTO sessions(id,player,game,started,updated,summary) '
                        'VALUES (?,?,?,?,?,?)', (sid, _label(player), _label(game), now, now, _json(summary)))
        self.prune()
        return sid

    def write(self, sid, summary, *, event=None, ended=None, reason=None):
        now = self.clock()
        if ended is None:
            self.db.execute('UPDATE sessions SET updated=?,summary=? WHERE id=? AND ended IS NULL',
                            (now, _json(summary), sid))
        else:
            self.db.execute('UPDATE sessions SET updated=?,summary=?,ended=?,reason=?,feedback_state=? '
                            'WHERE id=? AND ended IS NULL',
                            (now, _json(summary), ended, reason,
                             'pending' if reason == 'saved_exit' else 'none', sid))
        if event:
            seq = int(summary['events'])
            self.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',
                            (sid, seq, now, event[0], _json(event[1])))
            self.db.execute('DELETE FROM events WHERE session=? AND seq<=?',
                            (sid, seq - self.max_events))
        self.db.commit()

    def pending(self):
        rows = self.db.execute("SELECT id,ended,summary FROM sessions WHERE feedback_state='pending' "
                               'ORDER BY ended DESC LIMIT 10').fetchall()
        return [dict(session_id=r['id'], saved_at=_utc(r['ended']),
                     request_id=json.loads(r['summary']).get('save_request_id')) for r in rows]

    def feedback(self, body):
        sid = body.get('session_id')
        if not isinstance(sid, str) or not re.fullmatch(r'[0-9a-f]{32}', sid):
            raise ValueError('Choose a saved playtest session.')
        row = self.db.execute('SELECT ended,reason,feedback_state FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None or row['reason'] != 'saved_exit' or row['ended'] is None:
            raise ValueError('No saved playtest session is available in this account and world.')
        if body.get('skipped') not in (None, True, False):
            raise ValueError('Invalid feedback choice.')
        # Retry after a lost HTTP response is idempotent, including skip.
        if row['feedback_state'] in ('submitted', 'skipped'):
            return dict(session_id=sid, state=row['feedback_state'], text='Feedback choice already recorded.')
        state = 'skipped' if body.get('skipped') is True else 'submitted'
        result = {}
        if state == 'submitted':
            for field in TEXT_FIELDS:
                value = body.get(field, '')
                if not isinstance(value, str) or len(value) > 1600:
                    raise ValueError('Each feedback answer must be text of at most 1,600 characters.')
                result[field] = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', value).strip()
            ratings = body.get('ratings', {})
            if not isinstance(ratings, dict):
                raise ValueError('Ratings must be a form.')
            result['ratings'] = {}
            for field in RATINGS:
                value = ratings.get(field)
                if value in (None, ''):
                    continue
                if type(value) is not int or not 1 <= value <= 5:
                    raise ValueError('Choose ratings between 1 and 5, or leave them blank.')
                result['ratings'][field] = value
        result['submitted_at'] = _utc(self.clock())
        self.db.execute('UPDATE sessions SET feedback_state=?,feedback=? WHERE id=?',
                        (state, _json(result), sid))
        self.db.commit()
        return dict(session_id=sid, state=state, text='Thank you. Your feedback was recorded.'
                    if state == 'submitted' else 'Feedback skipped. Your game is already saved.')

    def close(self):
        self.db.close()


class UnavailableError(RuntimeError):
    pass


class UnavailableStore:
    """No filesystem writes and no success response for non-durable feedback."""

    def pending(self):
        return []

    def feedback(self, body):
        raise UnavailableError(UNAVAILABLE_NOTICE)

    def close(self):
        pass


class UnavailableCollector:
    def __init__(self, server):
        self.server = server
        self.store = UnavailableStore()
        self.session_id = None
        self.failures = 1

    def safely(self, method, *args):
        if method == 'packet':
            try:
                packet = json.loads(args[0])
            except (ValueError, TypeError):
                return args[0]
            if isinstance(packet, dict) and (packet.get('event') == 'character_entered'
                    or packet.get('checkpoint_saved') is True):
                packet['playtest'] = dict(enabled=False, collection_degraded=True,
                                          questionnaire=False, notice=UNAVAILABLE_NOTICE)
                return _json(packet)
            return args[0]
        return None

    def status(self):
        return dict(enabled=False, notice=UNAVAILABLE_NOTICE, current_session=None,
                    pending_feedback=[], collection_degraded=True)

    def configuration(self):
        return dict(enabled=False, notice=UNAVAILABLE_NOTICE, collection_degraded=True)

    def activity(self, body):
        return dict(recorded=False, available=False)


def open_collector(server, directory, game, **kwargs):
    """Analytics availability must never gate opening or saving a valid game."""
    try:
        return Collector(server, directory, game, **kwargs)
    except (sqlite3.Error, OSError, ValueError):
        return UnavailableCollector(server)


def classify(command):
    """Return only fixed vocabulary; never return a piece of unrecognized input."""
    lower = command.strip().lower()
    if any(lower == item or (item == 'world asset' and lower.startswith(item + ' ')) for item in BACKGROUND):
        return None
    words = lower.split()
    if not words:
        return None
    verb = words[0] if words[0] in KNOWN else 'other'
    if verb == 'resume':
        return None
    category = ('movement' if verb in MOVEMENT else 'interaction' if verb in INTERACTIONS
                else 'reading' if verb in READING else 'communication' if verb in ('say', 'whisper', 'emote')
                else 'save' if verb in ('save', 'save_exit') else 'action')
    if lower.startswith('walk to tile'):
        return dict(verb='route', category='navigation')
    if lower.startswith('resident watch'):
        return dict(verb='observe', category='interaction')
    if lower.startswith('local quests'):
        return dict(verb='quests', category='quest')
    if verb == 'ui':
        selected = words[2] if len(words) > 2 and words[1] == 'list' else words[1] if len(words) > 1 else ''
        if selected in READING:
            return dict(verb=selected, category='reading')
    return dict(verb='move' if verb in MOVEMENT else verb, category=category)


def failure_code(packet):
    """Recognize known failure messages in memory; store a code, never the prose."""
    if packet.get('save_failed'):
        return 'save_failed'
    message = packet.get('error') or packet.get('text') or ''
    if not isinstance(message, str):
        return None
    lower = message[:1500].lower()
    cases = (('save_failed', ('save failed', 'could not save')),
             ('missing_target', ('no living target', 'no target', 'not here', 'not present', 'cannot find', 'not found')),
             ('unavailable', ('not available', 'is closed', 'is asleep', 'must be awake')),
             ('insufficient_resources', ('not enough', 'insufficient', 'cannot afford')),
             ('unknown_command', ('unknown command', 'unrecognized command', 'not a command')),
             ('blocked', ("cannot go", "can't go", 'no exit', 'cannot move', 'locked', 'blocked', 'you must', 'you need')))
    for code, needles in cases:
        if any(needle in lower for needle in needles):
            return code
    return 'reported_error' if packet.get('type') == 'error' or packet.get('error') else None


class Collector:
    """Observe one live character/socket; state changes still belong to the game."""

    def __init__(self, server, directory, game, *, clock=time.time, monotonic=time.monotonic, store=None):
        self.server, self.game = server, _label(game)
        self.clock, self.monotonic = clock, monotonic
        self.store = store or Store(directory, clock=clock)
        self.session_id = self.player_id = None
        self.summary = None
        self.pending_command = None
        self.last_tick = self.monotonic()
        self.active_until = self.last_tick
        self.last_presence = self.last_tick
        self.visible = True
        self.position = None
        self.history = deque(maxlen=8)
        self.damage_ids = deque(maxlen=1000)
        self.damage_set = set()
        self.last_damage = -float('inf')
        self.last_heartbeat = -float('inf')
        self.failures = 0

    def safely(self, method, *args):
        # Analytics cannot turn a successful gameplay save into a failure.
        try:
            return getattr(self, method)(*args)
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError):
            self.failures += 1
            return None

    def player(self):
        return self.server.world.entities.get(self.player_id)

    def _place(self, location):
        room = self.server.world.rooms.get(location)
        return dict(id=_label(location), name=_label(getattr(room, 'name', location)))

    def _target(self, actor):
        from engine import relationships, creature_catalog
        authored = self.server.world.npcs.get(getattr(actor, 'source_def', None), {})
        kind = 'player' if actor.is_player else 'sentient_npc' if relationships.sentient(self.server.world, actor) else 'creature'
        # Monster distinction is an authored classification, never a guess from a name.
        if kind == 'creature' and creature_catalog.kind(authored, getattr(self.server.world, 'species', {})) == 'monster':
            kind = 'monster'
        return dict(id=_label(actor.id), name=_label(actor.name), kind=kind,
                    definition=_label(getattr(actor, 'source_def', '')))

    def _record(self, kind, data):
        if not self.session_id:
            return
        self.summary['events'] += 1
        self.store.write(self.session_id, self.summary, event=(kind, data))

    def start(self, player_id):
        if self.session_id and player_id == self.player_id:
            return
        self.finish('character_changed')
        actor = self.server.world.entities.get(player_id)
        if actor is None or not actor.is_player:
            return
        self.player_id = player_id
        self.summary = dict(events=0, actions=0, moves=0, damage_received=0, deaths=0,
                            active_seconds=0.0, idle_seconds=0.0, unobserved_seconds=0.0,
                            places={}, interactions={}, failures={}, action_counts={}, quick_returns=[],
                            truncated_places=0, truncated_targets=0)
        self.last_tick = self.monotonic()
        self.last_presence = self.last_tick
        self.active_until = self.last_tick + ACTIVE_WINDOW
        self.position = actor.location
        self.visible = True
        self.history.clear()
        self.history.append((actor.location, self.last_tick))
        self.damage_ids.clear()
        self.damage_set.clear()
        self.last_damage = -float('inf')
        self.session_id = self.store.create(player_id, self.game, self.summary)
        self._visit(actor.location)
        self._record('started', {'place': self._place(actor.location)})

    def _visit(self, location):
        key = _label(location)
        places = self.summary['places']
        if key not in places:
            if len(places) >= MAX_PLACES:
                self.summary['truncated_places'] += 1
                return
            places[key] = dict(**self._place(location), visits=0, active_seconds=0.0,
                               idle_seconds=0.0, injuries=0, failed_actions=0)
        places[key]['visits'] += 1

    def sample(self):
        if not self.session_id:
            return
        now = self.monotonic()
        elapsed = max(0.0, now - self.last_tick)
        # Long gaps are not silently counted as active play.  They are reported
        # separately from observed idle time (e.g. laptop sleep or lost network).
        measured_end = min(now, self.last_presence + HEARTBEAT_GAP)
        measured = max(0.0, measured_end - self.last_tick)
        active = max(0.0, min(measured_end, self.active_until) - self.last_tick) if self.visible else 0.0
        idle = max(0.0, measured - active)
        unobserved = max(0.0, elapsed - measured)
        for field, value in (('active_seconds', active), ('idle_seconds', idle), ('unobserved_seconds', unobserved)):
            self.summary[field] += value
        place = self.summary['places'].get(_label(self.position))
        if place:
            place['active_seconds'] += active
            place['idle_seconds'] += idle
        self.last_tick = now
        actor = self.player()
        if actor is None:
            return
        if actor.location != self.position:
            previous = self.position
            if len(self.history) >= 2 and self.history[-2][0] == actor.location and now - self.history[-1][1] <= 60:
                self.summary['quick_returns'] = (self.summary['quick_returns'] + [dict(
                    from_place=self._place(previous), to_place=self._place(actor.location),
                    seconds=round(now - self.history[-1][1], 1),
                    damage_within_60_seconds=now - self.last_damage <= 60)])[-30:]
            self.position = actor.location
            self.history.append((actor.location, now))
            self._visit(actor.location)
            self.summary['moves'] += 1
            self._record('moved', dict(origin=self._place(previous), destination=self._place(actor.location)))

    def activity(self, body):
        if type(body.get('visible')) is not bool or type(body.get('active')) is not bool:
            raise ValueError('Activity must contain visible and active flags.')
        now = self.monotonic()
        if now - self.last_heartbeat < 2:
            return {'recorded': False}
        self.last_heartbeat = now
        if not self.session_id:
            return {'recorded': False}
        self.sample()
        self.visible = body['visible']
        self.last_presence = now
        if self.visible and body['active']:
            self.active_until = now + ACTIVE_WINDOW
        elif not self.visible:
            self.active_until = now
        self.store.write(self.session_id, self.summary)
        return {'recorded': True}

    def before(self, raw):
        self.after()
        if not self.session_id:
            return
        try:
            packet = json.loads(raw)
        except (ValueError, TypeError):
            return
        command = packet.get('command') if isinstance(packet, dict) else None
        if not isinstance(command, str) or len(command) > 4096:
            return
        action = classify(command)
        if action is None:
            return
        self.sample()
        now = self.monotonic()
        self.last_presence = now
        self.active_until = now + ACTIVE_WINDOW
        actor = self.player()
        if actor is None:
            return
        action.update(origin=actor.location, outcome='responded', targets=[])
        if action['category'] == 'interaction':
            lower = command.lower()
            selected = [packet.get(k) for k in ('resident', 'target', 'npc', 'entity')]
            for other in self.server.world.entities_in_room(actor.location):
                if other.id == actor.id:
                    continue
                identifiers = (other.id, 'npc:' + str(getattr(other, 'source_def', '')))
                if (other.id in selected or any(i and i.lower() in lower for i in identifiers)
                        or (other.name and other.name.lower() in lower)):
                    action['targets'].append(self._target(other))
                    if len(action['targets']) >= 4:
                        break
            if action['verb'] in ('talk', 'ask', 'observe'):
                action['topic'] = next((topic for topic in TOPICS if re.search(r'\b' + topic + r'\b', lower)), 'other')
        self.pending_command = action

    def after(self):
        if not self.pending_command or not self.session_id:
            self.pending_command = None
            return
        self.sample()
        action, self.pending_command = self.pending_command, None
        actor = self.player()
        if action['category'] == 'movement':
            action['outcome'] = 'moved' if actor and actor.location != action['origin'] else 'no_movement'
        self.summary['actions'] += 1
        counts = self.summary['action_counts']
        counts[action['verb']] = counts.get(action['verb'], 0) + 1
        if action.get('failure'):
            failures = self.summary['failures']
            code = action['failure']
            failures[code] = failures.get(code, 0) + 1
            place = self.summary['places'].get(_label(action['origin']))
            if place:
                place['failed_actions'] += 1
        for target in action['targets']:
            key = target['id']
            if key not in self.summary['interactions']:
                if len(self.summary['interactions']) >= MAX_TARGETS:
                    self.summary['truncated_targets'] += 1
                    continue
                self.summary['interactions'][key] = dict(**target, attempts=0, failed=0, actions={})
            item = self.summary['interactions'][key]
            item['attempts'] += 1
            item['failed'] += bool(action.get('failure'))
            item['actions'][action['verb']] = item['actions'].get(action['verb'], 0) + 1
        action['place'] = self._place(action.pop('origin'))
        self._record('action', action)

    def damage(self, packet):
        if not self.session_id or packet.get('player_id') != self.player_id:
            return
        identity = packet.get('event_id')
        if not isinstance(identity, str) or identity in self.damage_set:
            return
        occurred = _number(packet.get('occurred_at'))
        row = self.store.db.execute('SELECT started FROM sessions WHERE id=?', (self.session_id,)).fetchone()
        if not row or occurred < row['started']:
            return  # A map replay from before this session is not a new injury.
        if len(self.damage_ids) == self.damage_ids.maxlen:
            self.damage_set.discard(self.damage_ids[0])
        self.damage_ids.append(identity)
        self.damage_set.add(identity)
        self.sample()
        amount = max(0, _number(packet.get('amount')))
        self.summary['damage_received'] += amount
        self.summary['deaths'] += packet.get('hp') == 0
        self.last_damage = self.monotonic()
        place = self.summary['places'].get(_label(self.position))
        if place:
            place['injuries'] += 1
        source = packet.get('source') if isinstance(packet.get('source'), dict) else {}
        actor = self.server.world.entities.get(source.get('id'))
        # Sources with no entity are kept as a fixed injury category, not copied prose.
        target = self._target(actor) if actor else dict(kind='environment_or_unknown')
        self._record('injury', dict(amount=amount, hp=max(0, _number(packet.get('hp'))),
                                   source=target, place=self._place(self.position)))

    def packet(self, message):
        packet = json.loads(message)
        if not isinstance(packet, dict):
            return message
        if packet.get('event') == 'character_entered':
            self.start(packet.get('player_id'))
            packet['playtest'] = {'session_id': self.session_id, 'notice': NOTICE}
        if self.session_id:
            if packet.get('type') == 'damage':
                self.damage(packet)
            if packet.get('type') == 'map':
                self.sample()
                for event in packet.get('damage_events', ()):
                    if isinstance(event, dict):
                        self.damage(event)
            if self.pending_command and packet.get('type') in ('error', 'response', 'local_quests',
                    'walk_plan', 'resident_watch', 'save_slots', 'player_calendar', 'calendar_error'):
                code = failure_code(packet)
                if code:
                    self.pending_command.update(failure=code, outcome='reported_error')
            if packet.get('type') in ('saved', 'saved_exit') and packet.get('checkpoint_saved') is True:
                self.after()
                self._record('checkpoint_saved', {'exit': packet['type'] == 'saved_exit'})
                if packet['type'] == 'saved_exit':
                    sid = self.session_id
                    rid = packet.get('request_id')
                    if isinstance(rid, str) and len(rid) <= 100:
                        self.summary['save_request_id'] = rid
                    self.finish('saved_exit')
                    packet['playtest'] = {'session_id': sid, 'questionnaire': True}
        return _json(packet)

    def finish(self, reason='disconnected'):
        if not self.session_id:
            return
        self.after()
        self.sample()
        self.store.write(self.session_id, self.summary, ended=self.clock(), reason=reason)
        self.session_id = self.player_id = None
        self.pending_command = None

    def status(self):
        self.sample()
        return dict(enabled=True, notice=NOTICE, current_session=self.session_id,
                    pending_feedback=self.store.pending(), collection_degraded=self.failures > 0)

    def configuration(self):
        return dict(enabled=True, notice=NOTICE, collection_degraded=self.failures > 0)


def owner_report(sources, *, limit=100):
    """Read only. Sources are provided by the owner-authorized main server.

    The caller supplies {directory, account, game} from its configured identities,
    never from player JSON. No directory or missing analytics DB is created here.
    """
    limit = max(1, min(200, int(limit)))
    sessions, unavailable = [], 0
    for source in list(sources)[:1000]:
        path = Path(source['directory']) / FILENAME
        if not path.is_file():
            continue
        try:
            db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
            db.row_factory = sqlite3.Row
            try:
                rows = db.execute('SELECT * FROM sessions WHERE updated>=? ORDER BY started DESC LIMIT ?',
                                  (time.time() - RETENTION_DAYS * 86400, limit)).fetchall()
            finally:
                db.close()
            for row in rows:
                summary = json.loads(row['summary'])
                sessions.append(dict(session_id=row['id'], account=_label(source['account']),
                    game=_label(source['game']), started=_utc(row['started']),
                    ended=_utc(row['ended']) if row['ended'] is not None else None,
                    reason=row['reason'] or 'connected', observations=summary,
                    feedback_state=row['feedback_state'], feedback=json.loads(row['feedback']) if row['feedback'] else None))
        except (sqlite3.Error, OSError, ValueError, TypeError):
            unavailable += 1
    sessions.sort(key=lambda row: row['started'], reverse=True)
    total = len(sessions)
    sessions = sessions[:limit]
    failures, verbs = Counter(), Counter()
    for session in sessions:
        failures.update(session['observations'].get('failures', {}))
        verbs.update(session['observations'].get('action_counts', {}))
        # These are prompts for review, deliberately separated from measured facts.
        signals = []
        for item in session['observations'].get('quick_returns', ()):
            signals.append(dict(kind='possible_caution' if item['damage_within_60_seconds'] else 'quick_return',
                evidence=item, interpretation=('Returned quickly after an injury; possible caution or recovery. '
                    'The reason is not known.' if item['damage_within_60_seconds'] else
                    'Returned to a recently visited place. This may be navigation or normal play, not avoidance.')))
        for item in session['observations'].get('places', {}).values():
            if item.get('failed_actions', 0) >= 3:
                signals.append(dict(kind='possible_friction', evidence=dict(place=item['name'],
                    failed_actions=item['failed_actions'], active_seconds=round(item['active_seconds'], 1)),
                    interpretation='Several actions failed here. The player may have been experimenting or encountered friction.'))
        session['review_signals'] = signals[:50]
    return dict(generated_at=_utc(time.time()), retention_days=RETENTION_DAYS,
                sessions=sessions, available_sessions=total, report_limit=limit,
                unavailable_sources=unavailable,
                totals=dict(sessions=len(sessions), actions=sum(s['observations']['actions'] for s in sessions),
                    moves=sum(s['observations']['moves'] for s in sessions),
                    active_seconds=round(sum(s['observations']['active_seconds'] for s in sessions), 1),
                    idle_seconds=round(sum(s['observations']['idle_seconds'] for s in sessions), 1),
                    failures=dict(failures), action_counts=dict(verbs)),
                definitions=dict(active_time='Estimate from server actions and visible-tab activity in the last 60 seconds; not proof of attention.',
                    idle_time='Connected, recently observed time without recent activity, or with the tab hidden.',
                    unobserved_time='Gaps longer than the presence allowance; not counted as active or known idle.',
                    avoidance='Unvisited places are not labeled avoided. Review signals are hypotheses; direct avoided-place answers are player reports.',
                    interactions='Selected or named nearby targets, classified from authored sentience. Attempts and reported failures are counted separately.'),
                limits=dict(sessions_per_account_world=MAX_SESSIONS, events_per_session=MAX_EVENTS,
                            places_per_session=MAX_PLACES, targets_per_session=MAX_TARGETS))


def report_html(report):
    """Owner report with escaped text, no third-party resources or inline script."""
    esc = lambda value: html.escape(str(value), quote=True)
    def table(headings, rows):
        return '<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+esc(x)+'</th>' for x in headings) + '</tr></thead><tbody>' + ''.join(
            '<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows) + '</tbody></table></div>'
    def duration(value):
        return f'{float(value) / 60:.1f} min'
    sections = []
    for session in report['sessions']:
        obs = session['observations']
        places = sorted(obs.get('places', {}).values(), key=lambda r: r['active_seconds'], reverse=True)
        targets = sorted(obs.get('interactions', {}).values(), key=lambda r: r['attempts'], reverse=True)
        body = '<p>'+esc(session['started'])+' · '+esc(session['reason'])+' · Active '+duration(obs['active_seconds'])+' · Idle '+duration(obs['idle_seconds'])+' · Unobserved '+duration(obs.get('unobserved_seconds',0))+'</p>'
        body += '<h3>Observed visits and time</h3>' + table(('Place', 'Visits', 'Active estimate', 'Idle', 'Injuries', 'Failed actions'), [
            (r['name'],r['visits'],duration(r['active_seconds']),duration(r['idle_seconds']),r['injuries'],r['failed_actions']) for r in places[:50]])
        body += '<h3>Observed interactions</h3>' + (table(('Character or creature', 'Type', 'Attempts', 'Failed', 'Actions'), [
            (r['name'],r['kind'].replace('_',' '),r['attempts'],r['failed'],', '.join(f'{k}: {v}' for k,v in r['actions'].items())) for r in targets[:40]]) if targets else '<p>No targeted interactions recorded.</p>')
        body += '<h3>Observed pain points</h3><p>'+esc(', '.join(f'{key.replace("_"," ")}: {value}' for key,value in obs.get('failures',{}).items()) or 'No recognized action errors.')+'</p><p>'+esc(f'Health lost: {obs["damage_received"]}; deaths: {obs["deaths"]}; actual room changes: {obs["moves"]}.')+'</p>'
        body += '<h3>Interpretations to review</h3>'
        body += '<ul>'+''.join('<li>'+esc(signal['interpretation'])+'<br><small>'+esc(_json(signal['evidence']))+'</small></li>' for signal in session['review_signals'])+'</ul>' if session['review_signals'] else '<p>No caution or friction signal identified. Unvisited places are not treated as avoided.</p>'
        body += '<h3>Direct player feedback</h3>'
        if session['feedback_state'] == 'submitted':
            feedback = session['feedback'] or {}
            body += '<p>'+esc(', '.join(f'{k.title()}: {v}/5' for k,v in feedback.get('ratings',{}).items()) or 'Ratings not supplied.')+'</p><dl>'+''.join('<dt>'+esc(field.replace('_',' ').title())+'</dt><dd>'+esc(feedback.get(field) or 'No answer')+'</dd>' for field in TEXT_FIELDS)+'</dl>'
        else:
            body += '<p>'+esc('Skipped by player.' if session['feedback_state']=='skipped' else 'Waiting for optional feedback.' if session['feedback_state']=='pending' else 'This session did not end with Save & quit.')+'</p>'
        if obs.get('truncated_places') or obs.get('truncated_targets'):
            body += '<p>Detailed place or target limits were reached; overall action counts remain available.</p>'
        sections.append('<details><summary>'+esc(session['account'])+' · '+esc(session['game'])+' · '+esc(session['started'])+'</summary>'+body+'</details>')
    totals = report['totals']
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Expanse playtest reports</title><style>' + '''
        :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#111920;color:#e3ece7;font:16px/1.55 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:24px}a{color:#9dddb6}h1,h2,h3{line-height:1.25}p,dd,small{overflow-wrap:anywhere}details{background:#1b272e;border:1px solid #466254;border-radius:10px;margin:20px 0;padding:18px}summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}.table-wrap{max-width:100%;overflow:auto}table{width:100%;border-collapse:collapse;font-size:.94rem}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #3a4c52}th{color:#bfe0cd}dt{font-weight:bold;margin-top:12px}dd{margin:0;white-space:pre-wrap}li{margin:10px 0}.notice{padding:14px;background:#24322d;border-radius:8px}@media(max-width:600px){main{padding:14px}details{padding:12px}th,td{padding:7px}h1{font-size:1.6rem}}
        ''' + '</style><main><nav><a href="/">Worlds &amp; saves</a> · <a href="/api/playtest/report">Download report JSON</a></nav><h1>Playtest reports</h1><p class="notice">Owner only. Observed events, estimates and player statements are shown separately. No passwords or conversation transcripts are collected.</p><p>'+esc(f'{totals["sessions"]} sessions shown · {totals["actions"]} actions · {totals["moves"]} actual room changes')+' · '+duration(totals['active_seconds'])+' active estimate</p><h2>How to read these reports</h2><ul>'+''.join('<li><strong>'+esc(key.replace('_',' ').title())+':</strong> '+esc(value)+'</li>' for key,value in report['definitions'].items())+'</ul><p>'+esc(f'Analytics retention: {RETENTION_DAYS} days, up to {MAX_SESSIONS} sessions per account/world and {MAX_EVENTS} recent events per session. Gameplay saves are separate.')+'</p>'+(''.join(sections) if sections else '<p>No playtest sessions have been recorded yet.</p>')+'</main></html>'
