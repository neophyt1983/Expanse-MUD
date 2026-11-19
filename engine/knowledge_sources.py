"""Bounded personal familiarity with attributed, qualified information.

Exposure makes a subject familiar, not true. Re-reading a rumor cannot turn it
into observation; copied editions retain their evidence roots. Only actual
action hooks write here. Ordinary knowledge/map projections are read-only.
"""
from copy import deepcopy
from hashlib import sha256

KEY = 'knowledge_familiarity_v1'
MAX_TOPICS = 192
MAX_SOURCES = 4
MAX_ROOTS = 8
MAX_EVENTS = 128
CERTAINTY = ('observed', 'sourced', 'uncertain', 'rumor', 'opinion')
KINDS = ('rooms', 'items', 'recipes', 'quests', 'npcs', 'species')


def _minute(world):
    from engine import worldtime
    return int(getattr(world, 'living_state', {}).get('minute', worldtime.initial_minute(world.metadata)))


def _reference(source, certainty):
    if not isinstance(source, dict) or certainty not in CERTAINTY:
        raise ValueError('A familiarity exposure needs a qualified real source.')
    kind, ident = source.get('kind'), source.get('id')
    if not isinstance(kind, str) or not isinstance(ident, str) or not ident:
        raise ValueError('A familiarity source needs kind and id.')
    value = dict(kind=kind[:40], id=ident[:200], certainty=certainty)
    for field in ('edition_id', 'work_id', 'source_id'):
        if isinstance(source.get(field), str): value[field] = source[field][:240]
    roots = source.get('evidence_roots') or [kind + ':' + ident]
    value['evidence_roots'] = list(dict.fromkeys(root for root in roots if isinstance(root, str)))[:MAX_ROOTS]
    # Keep claim qualifications intact in the publication ledger. This bounded
    # personal index keeps exact references, never recasts editorial opinions.
    value['claims'] = [dict(id=claim['id'], certainty=claim.get('certainty', 'sourced'))
                       for claim in source.get('claims', [])[:8]
                       if isinstance(claim, dict) and isinstance(claim.get('id'), str)]
    return value


def record(world, actor, table, *, source, certainty, event_id):
    """Remember an executed exposure, without granting routes/recipes/quests."""
    if (actor is None or not actor.alive or world.entities.get(actor.id) is not actor
            or not isinstance(table, dict) or not isinstance(event_id, str) or not event_id):
        return False
    reference = _reference(source, certainty)
    token = sha256(event_id.encode()).hexdigest()
    saved = actor.progress.get(KEY)
    if saved is not None:
        validate_saved(actor.progress)
        if token in saved['events']: return False
    now = _minute(world)
    saved = actor.progress.setdefault(KEY, {'version': 1, 'topics': {}, 'events': []})
    changed = False
    for kind in KINDS:
        values = table.get(kind, [])
        if not isinstance(values, (list, tuple, set)): continue
        for ident in dict.fromkeys(value for value in values if isinstance(value, str)):
            if ident not in getattr(world, kind, {}): continue
            key = kind + ':' + ident
            old = saved['topics'].get(key, {})
            if now < old.get('last_minute', now): continue
            sources = [row for row in old.get('sources', [])
                       if (row.get('edition_id') or row['kind'] + ':' + row['id']) !=
                       (reference.get('edition_id') or reference['kind'] + ':' + reference['id'])]
            sources.append(deepcopy(reference))
            roots = list(dict.fromkeys([*old.get('evidence_roots', []), *reference['evidence_roots']]))[-MAX_ROOTS:]
            # An opinion/rumor stays qualified even when it becomes familiar.
            qualities = list(dict.fromkeys([*old.get('qualities', []), certainty]))
            exposures = min(1_000_000, old.get('exposures', 0) + 1)
            saved['topics'].pop(key, None)
            saved['topics'][key] = dict(kind=kind, id=ident, exposures=exposures, last_minute=now,
                familiarity='studied' if exposures >= 5 else 'familiar' if exposures >= 2 else 'mention',
                qualities=qualities, evidence_roots=roots, sources=sources[-MAX_SOURCES:])
            changed = True
            while len(saved['topics']) > MAX_TOPICS: saved['topics'].pop(next(iter(saved['topics'])))
    saved['events'] = (saved['events'] + [token])[-MAX_EVENTS:]
    if changed and actor.is_player:
        world.dirty_players = getattr(world, 'dirty_players', set()) | {actor.id}
    return changed


def view(actor, kind, ident):
    """Project this actor's learned confidence unchanged; never train on reads."""
    return deepcopy(actor.progress.get(KEY, {}).get('topics', {}).get(kind + ':' + ident))


def validate_saved(progress):
    saved = progress.get(KEY)
    if saved is None: return
    if (not isinstance(saved, dict) or type(saved.get('version')) is not int or saved['version'] != 1
            or not isinstance(saved.get('topics'), dict) or len(saved['topics']) > MAX_TOPICS
            or not isinstance(saved.get('events'), list) or len(saved['events']) > MAX_EVENTS
            or any(not isinstance(token, str) or len(token) != 64 for token in saved['events'])):
        raise ValueError('Invalid saved knowledge familiarity.')
    for key, row in saved['topics'].items():
        if (not isinstance(row, dict) or row.get('kind') not in KINDS or not isinstance(row.get('id'), str)
                or key != row['kind'] + ':' + row['id'] or type(row.get('exposures')) is not int
                or not 1 <= row['exposures'] <= 1_000_000 or type(row.get('last_minute')) is not int
                or row.get('familiarity') not in ('mention', 'familiar', 'studied')
                or not isinstance(row.get('qualities'), list) or any(q not in CERTAINTY for q in row['qualities'])
                or not isinstance(row.get('sources'), list) or len(row['sources']) > MAX_SOURCES
                or not isinstance(row.get('evidence_roots'), list) or len(row['evidence_roots']) > MAX_ROOTS
                or any(not isinstance(root, str) for root in row['evidence_roots'])):
            raise ValueError('Invalid saved knowledge subject.')
        for source in row['sources']:
            if (not isinstance(source, dict) or not isinstance(source.get('kind'), str)
                    or not isinstance(source.get('id'), str) or source.get('certainty') not in CERTAINTY
                    or not isinstance(source.get('evidence_roots'), list) or len(source['evidence_roots']) > MAX_ROOTS):
                raise ValueError('Invalid saved knowledge source.')
