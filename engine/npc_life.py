"""Small persistent NPC life-state foundation, not a morality/violence model.

Scores are 0..100. Income is *security*, not coins or a wage promise. Health is
an acute HP percentage, not a disability rating. Real gold, HP, conditions and
relationship permissions remain authoritative in their existing systems.
"""
from hashlib import sha256
from math import isfinite
from engine.worldtime import MINUTES_PER_DAY, initial_minute

KEY = 'npc_life'
SCORES = ('day_quality', 'mood', 'fortitude', 'income')
# Fictional authoring presets, not statistical claims. Only explicit job tags.
OCCUPATIONS = {'guard': (65, 55), 'soldier': (65, 55), 'merchant': (50, 60),
               'farmer': (55, 50), 'miner': (60, 50), 'hunter': (60, 45),
               'artisan': (50, 55), 'producer': (50, 55)}
MAX_MEMORIES = 12


def number(value):
    if type(value) not in (int, float): return False
    try: return isfinite(value)
    except OverflowError: return False


def bounded(value):
    if not number(value): raise ValueError('Life score must be finite numeric data.')
    return round(max(0, min(100, value)), 2)


def minute(w):
    return getattr(w, 'living_state', {}).get('minute', initial_minute(w.metadata))


def config(w, e):
    d = w.npcs.get(e.source_def, {})
    place = d.get('home_room') or d.get('work_room') or e.location
    local = getattr(w, 'room_details', {}).get(place, {}).get('npc_life_defaults', {})
    return {**local, **d.get('life_profile', {})}


def validate_saved(progress):
    """Validate once at loading boundaries, never silently erase saved lives."""
    if not isinstance(progress, dict): raise ValueError('Invalid NPC progress object.')
    from engine import npc_emotions, npc_backgrounds, task_skills, knowledge_sources
    npc_emotions.validate_saved(progress)
    npc_backgrounds.validate_saved(progress)
    task_skills.validate_saved(progress)
    knowledge_sources.validate_saved(progress)
    if KEY not in progress: return
    s = progress[KEY]
    if not isinstance(s, dict): raise ValueError('Invalid saved NPC life object.')
    if 'version' in s and (type(s['version']) is not int or s['version'] != 1):
        raise ValueError('Unsupported NPC life version.')
    for key in (*SCORES, 'baseline_mood', 'health'):
        if key in s and (not number(s[key]) or not 0 <= s[key] <= 100):
            raise ValueError('Invalid saved NPC life score: ' + key)
    for key in ('updated_at', 'wages_today'):
        if key in s and (not number(s[key]) or s[key] < 0):
            raise ValueError('Invalid saved NPC life field: ' + key)
    if 'day' in s and (type(s['day']) is not int or s['day'] < 0):
        raise ValueError('Invalid saved NPC life day.')
    memories = s.get('memories', [])
    if not isinstance(memories, list) or len(memories) > MAX_MEMORIES:
        raise ValueError('Invalid saved NPC life memories.')
    for m in memories:
        if (not isinstance(m, dict) or not number(m.get('impact')) or
                not -100 <= m['impact'] <= 100 or not number(m.get('at')) or
                not number(m.get('expires')) or m['at'] < 0 or
                not 0 < m['expires'] - m['at'] <= 365 * MINUTES_PER_DAY or
                not isinstance(m.get('kind'), str) or not 0 < len(m['kind']) <= 80 or
                not isinstance(m.get('source', ''), str) or len(m.get('source', '')) > 160 or
                (m.get('id') is not None and (not isinstance(m['id'], str) or len(m['id']) > 160))):
            raise ValueError('Invalid saved NPC life memory.')


def ensure(w, e, *, check=False):
    """Only fill missing fields; saved values and creator extensions survive."""
    if e.is_player: return None
    from engine import npc_emotions
    s = e.progress.get(KEY)
    if check: validate_saved(e.progress)
    if not check and s is not None and s.get('version') == 1:
        npc_emotions.ensure(w, e)
        return s
    if s is None: s = e.progress.setdefault(KEY, {})
    d = w.npcs.get(e.source_def, {})
    c = config(w, e)
    role = d.get('occupation') or d.get('profession', '')
    fortitude, income = OCCUPATIONS.get(role, (50, 50))
    # Stable individual variation: never global RNG and never a reroll on load.
    seed = sha256((str(e.source_def) + ':' + e.id).encode()).digest()
    defaults = dict(day_quality=50, mood=50 + seed[0] % 11 - 5,
                    fortitude=fortitude + seed[1] % 21 - 10,
                    income=income + seed[2] % 21 - 10)
    for key in SCORES: s.setdefault(key, bounded(c.get(key, defaults[key])))
    s.setdefault('baseline_mood', s['mood'])
    s.setdefault('day', int(minute(w)) // MINUTES_PER_DAY)
    s.setdefault('updated_at', minute(w))
    s.setdefault('wages_today', 0)
    s.setdefault('memories', [])
    s.setdefault('health', health(e))
    s['version'] = 1
    npc_emotions.ensure(w, e)
    return s


def health(e):
    return round(min(100, 100 * max(0, e.hp) / e.max_hp), 2) if e.max_hp > 0 else 0


def step(w, e, now=None):
    if e.is_player: return None
    s = ensure(w, e)
    now = minute(w) if now is None else now
    day = int(now) // MINUTES_PER_DAY
    if day != s['day']:
        s['day'] = day
        s['day_quality'] = 50
        s['wages_today'] = 0
    # Mood returns slowly towards temperament. Persistent events have finite
    # duration; no invented tragedies, wealth changes or random daily drama.
    memories = s['memories']
    cursor = s['updated_at']
    # A rest/fast-forward must agree with minute ticks. Integrate over at most
    # twelve expiry boundaries; an event influences mood until it expires,
    # not as if it had already expired throughout the skipped interval.
    boundaries = sorted({m['expires'] for m in memories if cursor < m['expires'] < now})
    for stop in (*boundaries, now):
        duration = max(0, stop - cursor)
        target = bounded(s['baseline_mood'] + sum(m['impact'] for m in memories
                         if m['expires'] > cursor)) if memories else s['baseline_mood']
        if duration and s['mood'] != target:
            gap = target - s['mood']
            change = min(abs(gap), duration * 10 / MINUTES_PER_DAY)
            s['mood'] += change if gap > 0 else -change
        cursor = stop
    if memories:
        memories[:] = [m for m in memories if m['expires'] > now]
    s['health'] = health(e)
    s['updated_at'] = now
    return s


def event(w, e, kind, impact, *, duration=MINUTES_PER_DAY, source='', event_id=None):
    """Record an actual event once when an ID is provided; bounded memory work.

    Impact is signed, -100..100. Repeated social interactions are already
    cooldown-limited by social.py. Strong life events can use longer duration.
    """
    if e.is_player: return
    if not number(impact) or not -100 <= impact <= 100: raise ValueError('Invalid life-event impact.')
    if not number(duration) or not 0 < duration <= 365 * MINUTES_PER_DAY: raise ValueError('Invalid life-event duration.')
    if not isinstance(kind, str) or not kind or len(kind) > 80: raise ValueError('Invalid event kind.')
    if not isinstance(source, str) or len(source) > 160: raise ValueError('Invalid event source.')
    if event_id is not None and (not isinstance(event_id, str) or len(event_id) > 160): raise ValueError('Invalid event ID.')
    s = step(w, e)
    if event_id is not None and any(m.get('id') == event_id for m in s['memories']): return
    s['day_quality'] = bounded(s['day_quality'] + impact)
    s['mood'] = bounded(s['mood'] + impact)
    memory = dict(kind=kind, impact=impact, source=source, id=event_id,
                  at=minute(w), expires=minute(w) + duration)
    s['memories'].append(memory)
    del s['memories'][:-MAX_MEMORIES]
    from engine import npc_emotions
    npc_emotions.record_life_event(w, e, memory)


def earned(w, e, amount):
    """Observe actual paid wages only. Never mint money or infer wages from gold."""
    if not number(amount) or amount < 0: raise ValueError('Invalid wage amount.')
    if not e.is_player: step(w, e)['wages_today'] += amount


def overview(w, e):
    """Host/Creator view only. Private memories/income are not player packets."""
    s = step(w, e)
    return {key: s[key] for key in (*SCORES, 'health', 'wages_today')} if s else {}


def validate(data):
    errors = []
    for kind, field in (('npc', 'life_profile'), ('room', 'npc_life_defaults')):
        for row in data.get(kind, []):
            cfg = row.get(field, {})
            label = str(row.get('id', kind)) + ': ' + field
            if not isinstance(cfg, dict):
                errors.append(label + ' must be an object'); continue
            for key, value in cfg.items():
                if key not in SCORES or not number(value) or not 0 <= value <= 100:
                    errors.append(label + '.' + str(key) + ' must be a supported 0–100 score')
    return errors
