"""Private, deterministic prehistory compiler for *new* world creation.

This is a staging kernel, not automatic startup or a tick-by-tick civilization
simulator. Authored geological/civic events are required; it never invents a
continental history from a terrain icon. Negative minutes precede the campaign.
All dates share Expanse's local-year scale, not terrestrial years.
"""
from copy import deepcopy
from hashlib import sha256
import json
from engine import life_stages, worldtime

VERSION = 1
MAX_ACTORS = 10000
MAX_WORLD_EVENTS = 10000
MAX_EVENTS = 200000


class HistoryError(ValueError):
    pass


def _integer(value, label, low=None):
    if type(value) is not int or (low is not None and value < low):
        raise HistoryError(label + ' must be an integer' + (f' >= {low}' if low is not None else ''))
    return value


def _rows(data, kind):
    rows = data.get(kind, [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) or not r['id'] for r in rows):
        raise HistoryError(kind + ' must contain objects with nonempty string IDs')
    if len({r['id'] for r in rows}) != len(rows):
        raise HistoryError(kind + ' contains duplicate IDs')
    return {r['id']: r for r in rows}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def compile_history(data, plan):
    """Return a private review artifact without mutating content or live state.

    plan: seed, present_minute, events. Event domain is geology/civilization,
    at is signed absolute local minute, causes is a list of earlier event IDs,
    rooms references actual rooms. Civilization events require a group reference.
    NPCs without an explicit age are reported, never silently assigned one.
    Existing authored history_profile is retained verbatim, not overwritten.
    """
    if not isinstance(data, dict) or not isinstance(plan, dict):
        raise HistoryError('Content and plan must be objects')
    seed = _integer(plan.get('seed'), 'seed', 0)
    now = _integer(plan.get('present_minute'), 'present_minute', 0)
    rooms, groups, species, actors = (_rows(data, k) for k in ('room', 'group', 'species', 'npc'))
    if len(actors) > MAX_ACTORS:
        raise HistoryError('Actor work budget exceeded')
    raw = plan.get('events', [])
    if not isinstance(raw, list) or len(raw) > MAX_WORLD_EVENTS:
        raise HistoryError('World event work budget exceeded or malformed events')
    events = {}
    reference_budget = 0
    for original in raw:
        e = deepcopy(original)
        if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not e['id'] or e['id'].startswith('npc:') or e['id'] in events:
            raise HistoryError('World event ID missing, duplicate, or reserved')
        if e.get('domain') not in ('geology', 'civilization') or not isinstance(e.get('kind'), str) or not e['kind']:
            raise HistoryError('World event domain/kind invalid')
        if _integer(e.get('at'), 'event at') > now:
            raise HistoryError('Prehistory contains a future event')
        for field in ('rooms', 'causes', 'actors'):
            values = e.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
                raise HistoryError('Invalid event ' + field)
            reference_budget += len(values)
            if reference_budget > MAX_EVENTS:
                raise HistoryError('History reference work budget exceeded')
            e[field] = values
        if any(a not in actors for a in e['actors']):
            raise HistoryError('Event refers to a missing actor')
        if any(r not in rooms for r in e['rooms']):
            raise HistoryError('Event refers to a missing room')
        if e['domain'] == 'civilization' and e.get('group') not in groups:
            raise HistoryError('Civilization event requires an existing group')
        if e['kind'] in ('war_started', 'war_ended'):
            parties = e.get('parties', [])
            if e['domain'] != 'civilization' or not isinstance(parties, list) or len(parties) < 2 or any(not isinstance(g, str) or g not in groups for g in parties) or len(set(parties)) != len(parties):
                raise HistoryError('War requires at least two distinct existing factions')
            if e['group'] not in parties:
                raise HistoryError('War primary group must be a participant')
            if not e['rooms']:
                raise HistoryError('War requires explicit affected places')
        events[e['id']] = e
    for e in events.values():
        if e['kind'] == 'war_ended':
            starts = [events[c] for c in e['causes'] if c in events and events[c]['kind'] == 'war_started']
            if len(starts) != 1 or set(starts[0]['parties']) != set(e['parties']):
                raise HistoryError('War end must reference exactly one matching war start')
        for cause in e['causes']:
            if cause not in events or events[cause]['at'] >= e['at']:
                raise HistoryError('Causal events must exist and strictly precede their consequences')
            if e['domain'] == 'geology' and events[cause]['domain'] != 'geology':
                raise HistoryError('Deep geological events cannot be caused by civilization events')
    histories, skipped, births, profiles = {}, {}, {}, {}
    year = worldtime.MINUTES_PER_YEAR
    for aid, npc in sorted(actors.items()):
        if 'history_profile' in npc:
            histories[aid] = deepcopy(npc['history_profile'])
            skipped[aid] = 'creator-authored history retained'
            continue
        pp, sp = npc.get('population_profile', {}), npc.get('social_profile', {})
        if not isinstance(pp, dict) or not isinstance(sp, dict):
            raise HistoryError('Malformed population/social profile: ' + aid)
        if sp.get('sentient') is not True:
            skipped[aid] = 'no explicit sentient lifecycle profile'
            continue
        errors = life_stages.validate_age(sp, now)
        if errors:
            raise HistoryError('; '.join(errors))
        if sp.get('born_minute') is not None:
            born = sp['born_minute']
        elif sp.get('age_epoch_minute') is not None:
            age = sp.get('age_epoch_years', sp.get('age_years'))
            if age is None:
                raise HistoryError('Age epoch lacks age: ' + aid)
            born = sp['age_epoch_minute'] - round(age * year)
        else:
            age = pp.get('age_years', sp.get('age_years'))
            if age is None:
                skipped[aid] = 'no authored age; explicit population generation required'
                continue
            if type(age) not in (int, float) or not 0 <= age <= 10000:
                raise HistoryError('Invalid bounded age: ' + aid)
            fraction = _integer(pp.get('age_fraction_minutes', 0), 'age_fraction_minutes', 0)
            if fraction >= year:
                raise HistoryError('Age fraction must be less than a local year')
            born = now - round(age * year) - fraction
        if born > now or now - born > 10000 * year:
            raise HistoryError('Birth outside lifecycle budget: ' + aid)
        spec = species.get(pp.get('species', sp.get('species')), {})
        profile = life_stages.resolve_profile(None, spec)
        births[aid], profiles[aid] = born, profile
        local = []
        def add(kind, at, **extra):
            eid = 'npc:' + aid + ':' + kind
            event = dict(id=eid, domain='life', kind=kind, at=at, actor=aid, **extra)
            local.append(event)
        add('birth', born)
        for key, kind in [('infancy_end_years','infancy_ended'), ('adolescence_start_years','adolescence'), ('adulthood_years','adulthood'), ('elder_years','elder_life_stage')]:
            at = born + round(profile[key] * year)
            if at <= now:
                add(kind, at)
        # Current circumstances are observations, not invented historical dates.
        add('campaign_start', now, home=pp.get('home_room', npc.get('home_room')), occupation=npc.get('occupation'), education=deepcopy(pp.get('education', {})))
        histories[aid] = dict(version=VERSION, origin='generated_lifecycle_milestones', born_minute=born, events=local)
    # Add only real authored family links. Guardian is not synonymous with parent.
    for aid, born in births.items():
        pp = actors[aid].get('population_profile', {})
        parents = pp.get('biological_parent_source_ids', [])
        if not isinstance(parents, list) or len(parents) > 2 or any(not isinstance(p, str) for p in parents) or len(set(parents)) != len(parents):
            raise HistoryError('Invalid biological parent references')
        for parent in parents:
            if parent == aid or parent not in actors:
                raise HistoryError('Missing/self biological parent: ' + aid)
            if parent not in births:
                raise HistoryError('Parent needs a compatible authored birth epoch: ' + parent)
            if births[parent] + round(profiles[parent]['adulthood_years'] * year) > born:
                raise HistoryError('Biological parent was not adult at child birth: ' + aid)
            histories[parent]['events'].append(dict(id='npc:'+parent+':child:'+aid, domain='life', kind='child_born', at=born, actor=parent, child=aid))
        histories[aid]['events'][0]['parents'] = list(parents)
        partner = pp.get('current_partner_source_id')
        if partner:
            other = actors.get(partner, {}).get('population_profile', {})
            if partner == aid or other.get('current_partner_source_id') != aid:
                raise HistoryError('Current partnership must be reciprocal: ' + aid)
            # No invented wedding date; only the state known at campaign start.
            next(e for e in histories[aid]['events'] if e['kind'] == 'campaign_start')['partner'] = partner
    # Explicit participation only: residence today does not prove that someone
    # witnessed a historical war. Dead ancestors need a separate future archive.
    for event in events.values():
        for aid in event['actors']:
            if aid not in births or event['at'] < births[aid]:
                raise HistoryError('Historical participant lacks a compatible birth epoch: ' + aid)
            histories[aid]['events'].append(dict(id='npc:'+aid+':world:'+event['id'],
                domain='life', kind='experienced_world_event', at=event['at'],
                actor=aid, cause=event['id']))
    total = len(events)
    for aid in births:
        histories[aid]['events'].sort(key=lambda e:(e['at'], e['id']))
        total += len(histories[aid]['events'])
    if total > MAX_EVENTS:
        raise HistoryError('History event work budget exceeded')
    result = dict(version=VERSION, status='staged_not_installed', seed=seed, present_minute=now,
                  minutes_per_year=year, source_hash=_digest(data), plan_hash=_digest(plan),
                  events=sorted(events.values(), key=lambda e:(e['at'], e['id'])),
                  actors=histories, skipped=skipped,
                  limitations=['Milestone compilation is not a simulated biography.',
                              'Authored geological/civil events are validated, not generated.',
                              'No live state, relationships, health, skills, money or terrain changed.'])
    result['history_hash'] = _digest(result)
    return result
