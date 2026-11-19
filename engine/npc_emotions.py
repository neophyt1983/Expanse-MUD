"""Contextual NPC expressions grounded in their own recorded life.

The existing life model owns mood, needs own hunger, and relationships own
trust. This module combines those sources without choosing one exclusive
emotion. Small lifetime associations remember both helpful and adverse actual
experiences after short-lived mood memories expire. They never decide guilt,
grant knowledge, change permissions, or turn ordinary residents into thieves.

Only event hooks train the saved associations. ``project`` is read-only and
returns public expression labels, never a private memory, suspect or inventory.
"""
from hashlib import sha256
from math import isfinite
from time import monotonic

from engine import relationships, worldtime

KEY = 'npc_emotions_v1'
ASSOCIATIONS = ('social', 'support', 'loss', 'danger', 'authority', 'learning', 'performance')
MAX_SEEN = 64
MAX_COUNT = 1_000_000
CONTEXT_SECONDS = 20
EMOTIONS = {
    'happy': ('Happy', 'positive'), 'excited': ('Excited', 'positive'),
    'affectionate': ('Affectionate', 'positive'), 'amused': ('Amused', 'positive'),
    'calm': ('Calm', 'positive'), 'hopeful': ('Hopeful', 'positive'),
    'grateful': ('Grateful', 'positive'), 'relieved': ('Relieved', 'positive'),
    'sad': ('Sad', 'negative'), 'angry': ('Angry', 'negative'),
    'anxious': ('Anxious', 'negative'), 'afraid': ('Afraid', 'negative'),
    'irritated': ('Irritated', 'negative'), 'tired': ('Tired', 'negative'),
    'curious': ('Curious', 'neutral'), 'focused': ('Focused', 'neutral'),
}
SYMBOLS = dict(happy='🙂', excited='🤩', affectionate='💗', amused='😄', calm='😌',
               hopeful='🌤', grateful='🙏', relieved='😮‍💨', sad='😢', angry='😠',
               anxious='😟', afraid='😨', irritated='😒', tired='😴', curious='🤔', focused='🧐')
# Authored game-balance weights, not a claim about real human psychology.
# kind -> (association, signed life impact, independent expression weights).
EVENTS = {
    'happy': ('social', 2, {'happy': 24}),
    'excited': ('social', 3, {'happy': 18, 'excited': 32}),
    'in_love': ('social', 3, {'affectionate': 40, 'happy': 20}),
    'amusement': ('social', 2, {'amused': 35, 'happy': 15}),
    'sleepy': ('social', 1, {'tired': 28}),
    'serious': ('social', 1, {'focused': 28}),
    'conversation': ('social', 1, {'calm': 8}),
    'support received': ('support', 4, {'grateful': 35, 'hopeful': 20}),
    'strained interaction': ('social', -4, {'sad': 25, 'anxious': 25}),
    'irritated': ('social', -2, {'irritated': 35}),
    'angry': ('social', -4, {'angry': 40, 'anxious': 12}),
    'insulted': ('social', -2, {'sad': 25, 'angry': 30}),
    'insulting': ('social', -6, {'sad': 30, 'angry': 45, 'anxious': 20}),
    'gift_unwanted': ('social', -1, {'irritated': 18}),
    'gift_wanted': ('support', 5, {'grateful': 45, 'happy': 25}),
    'quest_complete': ('support', 5, {'grateful': 40, 'relieved': 25}),
    'encounter injury': ('danger', -4, {'afraid': 45, 'anxious': 35}),
    'encounter survived': ('danger', 3, {'relieved': 45, 'hopeful': 20}),
    'theft loss observed': ('loss', -8, {'sad': 52, 'angry': 60, 'anxious': 38}),
    'theft attempt observed': ('danger', -3, {'angry': 35, 'anxious': 35, 'afraid': 18}),
    'theft witnessed': ('danger', -3, {'angry': 28, 'anxious': 32}),
    'report received': ('authority', 2, {'hopeful': 28, 'anxious': 22}),
    'authority helped': ('authority', 5, {'grateful': 40, 'relieved': 38}),
    'authority harmed': ('authority', -6, {'afraid': 45, 'angry': 35, 'anxious': 40}),
    'learning encouraging': ('learning', 2, {'curious': 30, 'hopeful': 20}),
    'learning worrying': ('learning', -2, {'anxious': 28, 'focused': 20}),
    'performance welcomed': ('performance', 3, {'happy': 28, 'grateful': 25}),
    'performance rejected': ('performance', -3, {'sad': 25, 'anxious': 30}),
}
NEWS = {
    'Public safety': {'anxious': 28, 'focused': 20},
    'Watch': {'anxious': 16, 'hopeful': 14},
    'Education': {'curious': 28, 'hopeful': 24},
    'Culture': {'happy': 22, 'curious': 20},
    'Commerce': {'focused': 24, 'curious': 16},
    'Trade': {'focused': 24, 'curious': 16},
}


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def _bound(value):
    return round(max(0, min(100, value)), 2)


def _minute(world):
    value = getattr(world, 'living_state', {}).get('minute')
    return value if value is not None else worldtime.initial_minute(world.metadata)


class _ReadOnlyWorld:
    """Legacy profile helpers may initialize clock keys, but not our world."""
    def __init__(self, original):
        self.original = original
        self.living_state = dict(getattr(original, 'living_state', {}))

    def __getattr__(self, name):
        return getattr(self.original, name)


def _resident(world, person):
    return bool(person and not person.is_player and person.alive
                and relationships.sentient(world, person))


def _local_partner(world, person, partner):
    return bool(partner and partner is not person and partner.alive
                and person.location in world.rooms and partner.location == person.location
                and world.entities.get(partner.id) is partner)


def authority(world, person, partner):
    """An actual local, on-duty officer in the current jurisdiction."""
    if not _local_partner(world, person, partner) or partner.is_player:
        return False
    from engine import city_defense, livelihoods, sleep_movement
    projected = _ReadOnlyWorld(world)
    law = getattr(world, 'room_details', {}).get(person.location, {}).get('laws', {})
    return bool(law.get('enabled') and city_defense.is_guard(projected, partner)
                and (not law.get('authority') or partner.group_id == law['authority'])
                and livelihoods.on_shift(projected, partner) and not sleep_movement.asleep(projected, partner))


def validate_saved(progress):
    if KEY not in progress:
        return
    saved = progress[KEY]
    if not isinstance(saved, dict) or type(saved.get('version')) is not int or saved['version'] != 1:
        raise ValueError('Invalid saved NPC emotion experience version.')
    rows = saved.get('associations', {})
    if not isinstance(rows, dict) or set(rows) - set(ASSOCIATIONS):
        raise ValueError('Invalid saved NPC emotion associations.')
    for row in rows.values():
        if (not isinstance(row, dict) or any(not _number(row.get(key)) or not 0 <= row[key] <= 100
                                            for key in ('positive', 'negative'))
                or type(row.get('count')) is not int or not 0 <= row['count'] <= MAX_COUNT):
            raise ValueError('Invalid saved NPC emotion experience score.')
    seen = saved.get('seen', [])
    if (not isinstance(seen, list) or len(seen) > MAX_SEEN
            or any(not isinstance(token, str) or len(token) != 64 for token in seen)
            or len(set(seen)) != len(seen)):
        raise ValueError('Invalid saved NPC emotion event identifiers.')


def _train(saved, memory):
    spec = EVENTS.get(memory.get('kind'))
    if not spec:
        return
    ident = memory.get('id')
    token = sha256(str(ident).encode()).hexdigest() if ident is not None else None
    if token and token in saved['seen']:
        return
    if token:
        saved['seen'] = (saved['seen'] + [token])[-MAX_SEEN:]
    category, default, _ = spec
    impact = memory.get('impact', default)
    if not _number(impact):
        return
    row = saved['associations'].setdefault(category, dict(positive=0, negative=0, count=0))
    side = 'negative' if impact < 0 else 'positive'
    # Saturating independent traces preserve mixed experience. A helpful
    # encounter does not erase all past fear, nor does adversity erase support.
    amount = min(12, abs(impact))
    row[side] = _bound(row[side] + (100 - row[side]) * amount / 100)
    row['count'] = min(MAX_COUNT, row['count'] + 1)


def ensure(world, person):
    """Initialize on load/event boundaries, once from retained real memories."""
    if person.is_player:
        return None
    saved = person.progress.get(KEY)
    if saved is not None:
        return saved
    saved = dict(version=1, associations={}, seen=[])
    for memory in person.progress.get('npc_life', {}).get('memories', [])[-12:]:
        _train(saved, memory)
    person.progress[KEY] = saved
    return saved


def record_life_event(world, person, memory):
    """Called once by npc_life.event after its duplicate check."""
    if not person.is_player:
        saved = ensure(world, person)
        _train(saved, memory)
        spec = EVENTS.get(memory.get('kind'))
        source = world.entities.get(memory.get('source'))
        if (spec and spec[0] in ('social', 'support') and source
                and authority(world, person, source)):
            # The source really performed this local social action. No name,
            # faction score, global crime record or inferred biography is used.
            observed = dict(memory, kind='authority helped' if memory['impact'] >= 0 else 'authority harmed')
            if memory.get('id') is not None:
                observed['id'] = 'authority:' + memory['id']
            _train(saved, observed)


def founding_experience(world, person, kind, *, event_id):
    """An explicit new-founder history source, not a fresh event or a reroll.

    npc_backgrounds validates its actual authored source before calling here.
    No short-lived mood, time, inventory or life-event memory is manufactured.
    """
    if kind not in EVENTS or not isinstance(event_id, str) or not event_id:
        raise ValueError('A founding experience requires a supported kind and stable ID.')
    if not _resident(world, person):
        return
    _train(ensure(world, person), dict(kind=kind, impact=EVENTS[kind][1], id=event_id))


def record(world, person, kind, *, source='', event_id=None):
    """Trusted simulation hook for an event this NPC actually experienced."""
    if kind not in EVENTS:
        raise ValueError('Choose a supported experienced emotion event.')
    if not _resident(world, person):
        return False
    from engine import npc_life
    npc_life.event(world, person, kind, EVENTS[kind][1], source=source[:160], event_id=event_id)
    return True


def theft_observed(world, suspect, result):
    """Only actual detectors learn from a committed burglary result."""
    from engine import burglary
    burglary._validate_result(world, suspect, result)
    if result.permitted or not result.completed:
        return
    attempt = suspect.progress.get(burglary.ATTEMPT_KEY, {}).get('count', 0)
    ident = sha256(repr((suspect.id, result.target_key, result.minute, attempt)).encode()).hexdigest()
    for observer in result.detected:
        if not _resident(world, observer) or not _local_partner(world, suspect, observer):
            continue
        owner = observer.id == result.victim_id or bool(observer.source_def and observer.source_def == result.victim_id)
        kind = ('theft attempt observed' if not result.success or result.quantity <= 0 else
                'theft loss observed' if owner else 'theft witnessed')
        record(world, observer, kind, source=suspect.id, event_id='observed-theft:' + ident)


def report_received(world, reporter, officer, *, event_id):
    """A real report conversation; a global wanted entry alone is not a report.

    The caller supplies the reporter's own prior observed-event ID. No record
    means there is nothing this helper can safely claim was reported.
    """
    memories = reporter.progress.get('npc_life', {}).get('memories', [])
    known = next((row for row in memories if row.get('id') == event_id
                  and row.get('kind') in ('theft loss observed', 'theft attempt observed', 'theft witnessed')
                  and row.get('expires', 0) > _minute(world)), None)
    if not known or not _resident(world, reporter) or not authority(world, reporter, officer):
        return False
    token = 'report:' + sha256((event_id + ':' + officer.id).encode()).hexdigest()
    if any(row.get('id') == token for row in memories):
        return False
    record(world, reporter, 'report received', source=officer.id, event_id=token)
    context(world, reporter, partner=officer, topic='crime_report', event_id=event_id)
    return True


def authority_experience(world, person, officer, *, helpful, event_id):
    """Record an actual resolved helpful/adverse interaction, never a guess."""
    if type(helpful) is not bool or not authority(world, person, officer):
        return False
    return record(world, person, 'authority helped' if helpful else 'authority harmed',
                  source=officer.id, event_id=event_id)


def context(world, person, *, partner=None, topic=None, article_id=None, event_id=None,
            audience=(), theme=None):
    """Mark an actual conversation/reading, not every nearby map observation."""
    if not _resident(world, person):
        return
    prior = getattr(person, '_emotion_context', {})
    if topic is None and prior.get('room') == person.location and prior.get('until', 0) > monotonic():
        topic, article_id, event_id = (prior.get(key) for key in ('topic', 'article_id', 'event_id'))
    person._emotion_context = dict(room=person.location, until=monotonic() + CONTEXT_SECONDS,
                                   partner=partner.id if _local_partner(world, person, partner) else None,
                                   topic=topic, article_id=article_id, event_id=event_id,
                                   audience=[listener.id for listener in list(audience)[:32]
                                             if _local_partner(world,person,listener)], theme=theme)


def read_article(world, person, article_id):
    """A selected report already in this person's notebook, once per article."""
    article = person.progress.get('town_talk', {}).get('news', {}).get(article_id)
    if not isinstance(article, dict) or not _resident(world, person):
        return False
    section = article.get('section')
    kind = ('learning worrying' if section in ('Public safety', 'Watch') else
            'learning encouraging' if section in ('Education', 'Culture') else None)
    if kind:
        record(world, person, kind, event_id='read-news:' + sha256(str(article_id).encode()).hexdigest())
    context(world, person, topic='reading', article_id=article_id)
    return True


def speech_tone(world, person):
    """A delivery cue from the mixture, never keyword matching spoken words."""
    values = {row['id']: row['intensity'] for row in project(world, person)['emotions']}
    if values.get('angry', 0) >= 35 and max(values.get('sad', 0), values.get('anxious', 0)) >= 25:
        return 'says with a strained voice'
    if max(values.get('afraid', 0), values.get('anxious', 0)) >= 45:
        return 'says hesitantly'
    if values.get('sad', 0) >= 40 or values.get('tired', 0) >= 45:
        return 'says quietly'
    if values.get('angry', 0) >= 45:
        return 'says tensely'
    if max(values.get('happy', 0), values.get('excited', 0)) >= 40:
        return 'says brightly'
    return 'says'


def project(world, person, *, partner=None, topic=None, article_id=None, event_id=None,
            audience=(), theme=None):
    """Simultaneous public expressions, with no training or clock mutation."""
    if not _resident(world, person):
        return {'emotions': [], 'summary': ''}
    saved_context = getattr(person, '_emotion_context', {})
    if (topic is None and saved_context.get('room') == person.location
            and saved_context.get('until', 0) > monotonic()):
        topic, article_id, event_id = (saved_context.get(key) for key in ('topic', 'article_id', 'event_id'))
        partner = world.entities.get(saved_context.get('partner'))
        if topic == 'singing':
            audience = [world.entities.get(ident) for ident in saved_context.get('audience', [])[:32]]
            theme = saved_context.get('theme')
    if not _local_partner(world, person, partner):
        partner = None
    values, reasons = {}, {}

    def add(key, amount, cause):
        if key not in EMOTIONS or not _number(amount) or amount <= 0:
            return
        values[key] = _bound(values.get(key, 0) + amount)
        causes = reasons.setdefault(key, [])
        if cause not in causes:
            causes.append(cause)

    life = person.progress.get('npc_life', {})
    mood = life.get('mood', 50)
    if _number(mood):
        add('happy', (mood - 55) * .7, 'Current mood')
        add('sad', (45 - mood) * .7, 'Current mood')
    now = _minute(world)
    memories = life.get('memories', [])[-12:]
    for memory in memories:
        spec = EVENTS.get(memory.get('kind'))
        start, end = memory.get('at'), memory.get('expires')
        if not spec or not _number(start) or not _number(end) or not start <= now < end:
            continue
        fraction = min(1, (end - now) / max(1, end - start))
        for feeling, strength in spec[2].items():
            add(feeling, strength * fraction, 'Recent experience')
    from engine import needs_market
    if needs_market.applies(world, person):
        needs = person.progress.get('needs', {})
        threshold = needs_market.cfg(world, person)['threshold']
        for key, feelings in [('hunger', {'irritated': .7, 'tired': .4}),
                              ('thirst', {'irritated': .5, 'tired': .3}),
                              ('rest', {'tired': .9}),
                              ('safety', {'anxious': .8, 'afraid': .5}),
                              ('belonging', {'sad': .5})]:
            value = needs.get(key)
            if _number(value) and _number(threshold):
                for feeling, weight in feelings.items():
                    add(feeling, max(0, min(100, value) - threshold) * weight, 'Current ' + key + ' need')
    history = person.progress.get(KEY, {}).get('associations', {})

    def learned(category, positive, negative):
        row = history.get(category, {})
        for side, weights in (('positive', positive), ('negative', negative)):
            value = row.get(side, 0)
            if _number(value):
                for feeling, weight in weights.items():
                    add(feeling, value * weight, 'Past ' + category + ' experiences')

    if partner:
        bonds = getattr(world, 'living_state', {}).get('relationships', {}).get('bonds', {})
        bond = bonds.get(relationships.key(person, partner), {})
        trust = bond.get('trust', 0)
        if _number(trust):
            add('calm', max(0, trust) * .25, 'Trust in this conversation partner')
            add('anxious', max(0, -trust) * .3, 'Strained trust with this conversation partner')
        if any(kind in bond.get('kinds', []) for kind in ('friend', 'lover', 'married', 'parent')):
            add('affectionate', 20, 'An established close relationship')
        learned('social', {'calm': .15}, {'anxious': .2})
        learned('support', {'hopeful': .2}, {})
        if authority(world, person, partner):
            learned('authority', {'calm': .3, 'hopeful': .3}, {'anxious': .5, 'afraid': .25})
            known = any(row.get('id') == event_id and row.get('kind') in
                        ('theft loss observed', 'theft attempt observed', 'theft witnessed')
                        and row.get('expires', 0) > now for row in memories)
            if topic == 'crime_report' and known:
                add('anxious', 18, 'Reporting an experienced event to an officer')
                add('hopeful', 12, 'Seeking help from an officer')
                learned('loss', {}, {'sad': .2, 'anxious': .2})
                learned('danger', {'relieved': .15}, {'afraid': .2})
    notes = person.progress.get('town_talk', {})
    article = notes.get('news', {}).get(article_id) if article_id is not None else None
    if topic in ('reading', 'localnews') and isinstance(article, dict):
        for feeling, strength in NEWS.get(article.get('section'), {'curious': 16}).items():
            add(feeling, strength, 'A report this resident has read or heard')
        learned('learning', {'curious': .25, 'hopeful': .15}, {'anxious': .2})
    elif topic in ('work', 'activities', 'plans', 'people', 'creatures'):
        add('focused' if topic == 'work' else 'curious', 12, 'The current discussion')
    elif topic == 'singing':
        add('focused', 16, 'The current performance')
        learned('performance', {'happy': .25}, {'anxious': .35})
        bonds = getattr(world, 'living_state', {}).get('relationships', {}).get('bonds', {})
        trusted, strained = 0, 0
        for listener in list(audience)[:32]:
            if not _local_partner(world, person, listener):
                continue
            trust = bonds.get(relationships.key(person, listener), {}).get('trust', 0)
            if _number(trust):
                trusted, strained = max(trusted, trust), max(strained, -trust)
        add('calm', trusted * .25, 'A trusted person in the actual audience')
        add('anxious', strained * .3, 'A strained relationship in the actual audience')
        themes = {'celebration': {'happy': 15}, 'remembrance': {'sad': 15},
                  'work': {'focused': 15}, 'danger': {'anxious': 15},
                  'togetherness': {'affectionate': 15}, 'hope': {'hopeful': 15}}
        for feeling, value in themes.get(theme, {}).items():
            add(feeling, value, 'The song’s authored theme')
        if theme == 'remembrance':
            learned('loss', {'relieved': .2}, {'sad': .35})
        elif theme == 'danger':
            learned('danger', {'hopeful': .2}, {'afraid': .35})
        elif theme in ('togetherness', 'hope'):
            learned('support', {'grateful': .3}, {})
    rows = [dict(id=key, label=EMOTIONS[key][0], valence=EMOTIONS[key][1], symbol=SYMBOLS[key],
                 intensity=round(value), causes=reasons[key][:4])
            for key, value in values.items() if round(value) >= 3]
    rows.sort(key=lambda row: (-row['intensity'], row['id']))
    return {'emotions': rows, 'summary': ', '.join(row['label'].lower() for row in rows)}
