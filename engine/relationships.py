"""Persistent social bonds built from creator-editable profiles and faction rules.

Player acceptance is always explicit. NPC decisions are deterministic preferences,
not a claim that the simulation has feelings. Romance is adult and sentient only.
"""
from collections import Counter
from copy import deepcopy
from uuid import uuid4
from engine import living, society, worldtime, life_stages

KINDS = ('friend', 'business', 'companion', 'lover', 'married')
ROMANTIC = ('lover', 'married')
CONTENT_PROFILE = dict(age_years=25, sentient=True, undead=False, fertile=False,
               species='human', reproductive_role='none', romance_enabled=False,
               family_enabled=False, accepts=['friend', 'business'], autonomous=False,
               compatible_species=['*'], maturity_years=1, breeding_seasons=['spring'],
               gestation_minutes=43200)
# Keep canonical, fingerprinted world templates byte-compatible. Older profiles
# acquire later gameplay defaults at runtime; explicit Creator values override them.
PROFILE = dict(CONTENT_PROFILE, business_meeting_days=3, business_partner_limit=1,
                        age_in_world=True, elder_lifespan_years=25, grown_family_percent=50)
POLICY = dict(minimum_standing=51, allowed_factions=[], forbidden_factions=[],
              marriage_allowed=True, exclusive=True, infidelity_allowed=True,
              infidelity_trust_penalty=30, reproduction_allowed=True,
              gestation_minutes=388800, parent_cooldown_minutes=43200,
              population_limit=5000)


def state(w):
    return living.state(w).setdefault('relationships', dict(bonds={}, proposals={},
        pregnancies={}, children=[], events=[], last_social=-1))


def sentient(w, e):
    """Read one effective field without copying/aging the whole social profile.

    Match profile's override order exactly, including its intentionally authored
    species selection before per-entity overrides. No cache survives mutations.
    """
    authored=(w.races.get(e.race,{}) if e.is_player else w.npcs.get(e.source_def,{})).get('social_profile',{})
    species=getattr(w,'species',{}).get(authored.get('species',PROFILE['species']),{})
    return e.progress.get('social_profile',{}).get('sentient',
        species.get('sentient',authored.get('sentient',PROFILE['sentient'] if e.is_player else False)))


def profile(w, e):
    # Defaults contain only scalars and flat string lists. Copy those lists
    # without recursively copying the entire profile on every NPC predicate.
    base = dict(PROFILE)
    for field in ('accepts','compatible_species','breeding_seasons'):
        base[field]=list(base[field])
    if not e.is_player:
        # Unknown creatures are never silently treated as romance-capable adults.
        base.update(sentient=False, accepts=['companion'])
        base.update(w.npcs.get(e.source_def, {}).get('social_profile', {}))
    else:
        base.update(w.races.get(e.race, {}).get('social_profile', {}))
    species=getattr(w,'species',{}).get(base['species'],{})
    for field in ('sentient','maturity_years','breeding_seasons','gestation_minutes'):
        if field in species:
            value=species[field]
            base[field]=list(value) if field=='breeding_seasons' else value
    base.update(e.progress.get('social_profile', {}))
    if base.get('born_minute') is not None or base.get('age_epoch_minute') is not None:
        base['age_years'] = int(life_stages.age_years(base, living.state(w)['minute']))
    return base


def policy(w, e):
    return {**POLICY, **w.groups.get(e.group_id, {}).get('coupling_rules', {})}


def key(a, b):
    return '|'.join(sorted((a.id, b.id)))


def bond(w, a, b):
    return state(w)['bonds'].setdefault(key(a, b),
        dict(participants=[a.id, b.id], names=[a.name, b.name], kinds=[], trust=0,
             history=[]))


def event(w, text, participants, *, public=False, topic=None):
    s = state(w)
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,participants,text)
    from engine import gazette
    if public:
        actor=next((w.entities.get(pid) for pid in participants if w.entities.get(pid)),None)
        if actor:gazette.record(w,actor.location,'Community',text,topic=topic)
    s['events'] = (s['events'] + [dict(minute=living.state(w)['minute'],
        text=text, participants=list(participants))])[-500:]


def eligible(w, a, b, kind):
    if kind not in KINDS: raise ValueError('Unknown relationship kind.')
    if a.id == b.id: raise ValueError('Choose another character.')
    if not a.alive or not b.alive: raise ValueError('Both participants must be alive.')
    if a.location != b.location: raise ValueError('Meet at the same location first.')
    pa, pb = profile(w, a), profile(w, b)
    if kind in ('business',) + ROMANTIC and not (pa['sentient'] and pb['sentient']):
        raise ValueError('This relationship requires sentient participants.')
    if kind not in ROMANTIC:
        if kind != 'companion' and society.friendliness(w,a,b)<50:
            raise ValueError('Faction standing does not permit this relationship.')
        if kind == 'companion' and b.group_id and a.group_id and society.friendliness(w,a,b)<50:
            raise ValueError('Faction standing does not permit this companionship.')
        return
    if any(not life_stages.for_entity(w, e, p)['adult'] or not p['romance_enabled']
           for e, p in ((a, pa), (b, pb))):
        raise ValueError('Romance requires opted-in adult characters.')
    if related(w, a.id, b.id): raise ValueError('Close relatives cannot form a romantic relationship.')
    for owner, other in ((a, b), (b, a)):
        rules = policy(w, owner)
        if other.group_id in rules['forbidden_factions']:
            raise ValueError('Faction coupling rules forbid this match.')
        if rules['allowed_factions'] and other.group_id not in rules['allowed_factions']:
            raise ValueError('Faction coupling rules do not permit this match.')
        if society.standing(w, owner, other.group_id) < rules['minimum_standing']:
            raise ValueError('Faction standing is too low for this match.')
        if kind == 'married' and not rules['marriage_allowed']:
            raise ValueError('Faction rules do not permit marriage.')
        if rules['exclusive'] and not rules['infidelity_allowed'] and other_partners(w, owner.id, other.id):
            raise ValueError('End the exclusive partnership before forming another.')


def related(w, aid, bid):
    parents = {row['id']: set(row['parents']) for row in state(w)['children']}
    def ancestors(pid):
        found = set(); pending = list(parents.get(pid, ()))
        while pending:
            node = pending.pop()
            if node not in found:
                found.add(node); pending.extend(parents.get(node, ()))
        return found
    aa, bb = ancestors(aid), ancestors(bid)
    return aid in bb or bid in aa or bool(aa & bb)


def other_partners(w, pid, except_id):
    return [row for row in state(w)['bonds'].values()
            if pid in row['participants'] and except_id not in row['participants']
            and not row.get('deceased') and any(k in row['kinds'] for k in ROMANTIC)]


def establish(w, a, b, kind):
    eligible(w, a, b, kind)
    row = bond(w, a, b)
    if kind in row['kinds']: raise ValueError('That relationship already exists.')
    if kind in ROMANTIC:
        for owner, other in ((a, b), (b, a)):
            rules = policy(w, owner)
            if not rules['exclusive']: continue
            for previous in other_partners(w, owner.id, other.id):
                previous['trust'] = max(-100, previous['trust'] - rules['infidelity_trust_penalty'])
                previous['history'].append(dict(minute=living.state(w)['minute'],
                    action='infidelity', actor=owner.id))
                event(w, owner.name + ' broke an exclusive commitment.', previous['participants'])
    if a.location == b.location and sentient(w,a) and sentient(w,b):
        from engine import town_talk
        town_talk.meet(w,a,b)
    row['kinds'].append(kind); row['trust'] = min(society.bounds(w,a.group_id,b.group_id)[1],society.bounds(w,b.group_id,a.group_id)[1], row['trust'] + 10)
    row['history'].append(dict(minute=living.state(w)['minute'], action='formed', kind=kind))
    if kind in ROMANTIC:
        for person, partner in ((a,b),(b,a)):
            household = person.progress.get('population')
            if household:
                household.update(current_partner_id=partner.id,partnership_status='partnered')
                if kind == 'married':
                    household['marital_status'] = 'married'
                household.setdefault('relationship_history',[]).append(dict(event=kind,partner_id=partner.id,
                                                                           minute=living.state(w)['minute']))
    label = 'business partners' if kind == 'business' else kind
    event(w, f'{a.name} and {b.name} became {label}.', [a.id, b.id],
          public=kind in ('business', 'married'), topic=kind)
    return 'Relationship formed: ' + kind + '.'


def family_eligible(w, a, b):
    eligible(w, a, b, 'lover')
    profiles = [profile(w, a), profile(w, b)]
    if any(p['undead'] or not p['fertile'] or not p['family_enabled'] for p in profiles):
        raise ValueError('Both parents must be living, fertile and opted in to parenthood.')
    for own, other in ((profiles[0], profiles[1]), (profiles[1], profiles[0])):
        compatible = own['compatible_species']
        if '*' not in compatible and other['species'] not in compatible:
            raise ValueError('These races are not reproductively compatible.')
    roles = [p['reproductive_role'] for p in profiles]
    if sorted(roles) != ['carrier', 'contributor']:
        raise ValueError('Compatible reproductive roles are required.')
    row = state(w)['bonds'].get(key(a, b), {})
    if not any(k in row.get('kinds', []) for k in ROMANTIC):
        raise ValueError('Form a consensual adult partnership first.')
    now = living.state(w)['minute']; s = state(w)
    for e in (a, b):
        if not policy(w, e)['reproduction_allowed']: raise ValueError('Faction rules prohibit reproduction.')
        if e.progress.get('family_ready_minute', 0) > now: raise ValueError('A parent is not ready for another pregnancy.')
        if any(e.id in r['parents'] for r in s['pregnancies'].values()): raise ValueError('A pregnancy is already underway.')
    if len(w.entities) >= min(policy(w, e)['population_limit'] for e in (a, b)):
        raise ValueError('The regional population limit has been reached.')
    return (a, b)[roles.index('carrier')]


def conceive(w, a, b):
    carrier = family_eligible(w, a, b)
    now = living.state(w)['minute']
    state(w)['pregnancies'][carrier.id] = dict(parents=[a.id, b.id],
        names=[a.name, b.name], carrier=carrier.id,
        due=now + max(policy(w, e)['gestation_minutes'] for e in (a, b)),
        ancestry=[dict(race=e.race, species=profile(w,e)['species']) for e in (a,b)])
    event(w, 'A child is expected by ' + a.name + ' and ' + b.name + '.', [a.id, b.id])
    return 'Parenthood accepted. A pregnancy has begun.'


def propose(w, a, b, kind):
    if kind == 'parenthood': family_eligible(w, a, b)
    else: eligible(w, a, b, kind)
    from engine import npc_attention
    npc_attention.begin(w,a,b)
    s = state(w); now = living.state(w)['minute']
    s['proposals'] = {k: v for k, v in s['proposals'].items() if v['expires'] > now}
    if sum(r['from'] == a.id for r in s['proposals'].values()) >= 5:
        raise ValueError('Resolve your pending proposals first.')
    if any(r['from'] == a.id and r['to'] == b.id and r['kind'] == kind for r in s['proposals'].values()):
        raise ValueError('That proposal is already pending.')
    if not b.is_player:
        preference = profile(w, b)
        if kind == 'parenthood': accepted = preference['family_enabled']
        else: accepted = kind in preference['accepts']
        # Friendly NPCs can consent by authored preference; hostile ones refuse.
        if not accepted or society.friendliness(w, a, b) < 50:
            return b.name + ' declines.'
        return conceive(w, a, b) if kind == 'parenthood' else establish(w, a, b, kind)
    ident = uuid4().hex[:12]
    s['proposals'][ident] = dict(id=ident, **{'from': a.id, 'to': b.id}, kind=kind,
        sender=a.name, expires=now + 60)
    return 'Proposal ' + ident + ' awaits ' + b.name + '\'s explicit acceptance.'


def respond(w, p, ident, accept):
    s = state(w); row = s['proposals'].get(ident)
    if not row or row['to'] != p.id: raise ValueError('No proposal addressed to you with that ID.')
    if not accept:
        del s['proposals'][ident]; return 'Proposal declined.'
    if row['expires'] <= living.state(w)['minute']:
        del s['proposals'][ident]; raise ValueError('That proposal has expired.')
    a = w.entities.get(row['from'])
    if a is None: raise ValueError('The proposer must be present.')
    result = conceive(w, a, p) if row['kind'] == 'parenthood' else establish(w, a, p, row['kind'])
    del s['proposals'][ident]
    return result


def season(w,room=None):
    from engine import climate
    latitude=climate.conditions(w,room)['latitude'] if room in w.rooms else 45
    return worldtime.season(living.state(w)['minute'],latitude)


def breed_animals(w, a, b):
    """Non-romantic animal reproduction; never mixes species or player characters."""
    if a.id == b.id or a.is_player or b.is_player or not a.alive or not b.alive or a.location != b.location:
        raise ValueError('Two living animals must meet.')
    profiles = [profile(w, e) for e in (a, b)]
    if any(p['sentient'] or p['undead'] or not p['fertile'] or not p['family_enabled'] or not p['autonomous'] for p in profiles):
        raise ValueError('This pair is not eligible for animal breeding.')
    if not profiles[0]['species'] or profiles[0]['species'] != profiles[1]['species']:
        raise ValueError('Animals can breed only with their own species.')
    if related(w, a.id, b.id): raise ValueError('Close relatives cannot breed.')
    if any(p['age_years'] < p['maturity_years'] or season(w,a.location) not in p['breeding_seasons'] for p in profiles):
        raise ValueError('These animals must be mature and in their breeding season.')
    roles = [p['reproductive_role'] for p in profiles]
    if sorted(roles) != ['carrier', 'contributor']: raise ValueError('Compatible reproductive roles are required.')
    now = living.state(w)['minute']; s = state(w)
    for e in (a, b):
        if e.progress.get('family_ready_minute', 0) > now or any(e.id in r['parents'] for r in s['pregnancies'].values()):
            raise ValueError('An animal is not ready for another pregnancy.')
    if len(w.entities) >= min(policy(w, e)['population_limit'] for e in (a, b)):
        raise ValueError('The population limit has been reached.')
    carrier = (a, b)[roles.index('carrier')]
    s['pregnancies'][carrier.id] = dict(parents=[a.id, b.id], names=[a.name, b.name],
        carrier=carrier.id, due=now + max(p['gestation_minutes'] for p in profiles),
        ancestry=[dict(race=e.race, species=profile(w,e)['species']) for e in (a,b)], animal=True)
    row = bond(w, a, b)
    if 'animal_pair' not in row['kinds']: row['kinds'].append('animal_pair')
    event(w, a.name + ' and ' + b.name + ' paired during ' + season(w,a.location) + '.', [a.id, b.id])
    return 'Seasonal animal pregnancy began.'


def trade_workplace(w, actor, profile, now):
    """Return the assigned workplace and whether it supports trade for this worker."""
    from engine import livelihoods
    job = livelihoods.definition(w, actor)
    if not (job.get('work_room') or actor.progress.get('job_property')):
        return None
    start, duration = livelihoods.hours(w, actor)
    if (actor.progress.get('retired') or (now - start) % worldtime.MINUTES_PER_DAY >= duration
            or str(getattr(actor, 'activity', '')).startswith('sleeping') or not profile['sentient']
            or not life_stages.for_entity(w, actor, profile)['adult']):
        return None
    room = livelihoods.workplace(w, actor)
    if room not in w.rooms:
        return None
    commercial = (getattr(w, 'room_details', {}).get(room, {}).get('workshop') or job.get('shop')
                  or job.get('market_id') or actor.progress.get('job_property')
                  or job.get('occupation') in ('merchant', 'producer', 'farmer', 'hunter'))
    return room, bool(commercial)


def business_meeting(w, a, b, pa, pb, work, counts, now):
    if any(counts[e.id] >= p['business_partner_limit'] for e, p in ((a, pa), (b, pb))):
        return False
    for e, p in ((a, pa), (b, pb)):
        if e.id not in work:
            work[e.id] = trade_workplace(w, e, p, now)
    if not work[a.id] or not work[b.id] or (a.location, True) not in (work[a.id], work[b.id]):
        return False
    if society.friendliness(w, a, b) < 50:
        return False
    row = bond(w, a, b)
    day = now // worldtime.MINUTES_PER_DAY
    if row.get('last_business_meeting_day') != day:
        row['last_business_meeting_day'] = day
        row['business_meeting_days'] = row.get('business_meeting_days', 0) + 1
    return row['business_meeting_days'] >= max(1, pa['business_meeting_days'], pb['business_meeting_days'])


def advance(w):
    s = state(w); now = living.state(w)['minute']
    s['proposals'] = {k: v for k, v in s['proposals'].items() if v['expires'] > now}
    for cid, pregnancy in list(s['pregnancies'].items()):
        carrier = w.entities.get(cid)
        if carrier is None: continue  # Offline player: wait for their return.
        if not carrier.alive or profile(w, carrier)['undead']:
            del s['pregnancies'][cid]
            event(w, 'The pregnancy ended after the carrier died.', pregnancy['parents']); continue
        if now < pregnancy['due']: continue
        from engine.core import Entity
        template = 'sx_child'
        if template not in w.npcs: continue
        # Population cap delays a birth; it never silently deletes a child.
        if len(w.entities) >= policy(w, carrier)['population_limit']: continue
        ident = 'child_' + uuid4().hex
        child = Entity(ident, 'Child of ' + carrier.name, 10, 10, 0, 0,
                       source_def=template, group_id=carrier.group_id, race=carrier.race, spawner_key='birth:'+ident)
        child.progress['social_profile'] = {**deepcopy(profile(w, carrier)), 'age_years': 0,
            'born_minute': now, 'species': profile(w, carrier)['species'],
            'fertile': True, 'reproductive_role': 'carrier' if int(ident[-1],16)%2 else 'contributor',
            'parents': pregnancy['parents'], 'ancestry': pregnancy.get('ancestry', [])}
        # A newborn is not a copy of a parent's consent. Animal reproduction
        # retains its separate seasonal/maturity semantics. No birthday opts
        # a sentient child into romance, fertility or autonomous parenthood.
        cp = child.progress['social_profile']
        cp.pop('age_epoch_minute', None); cp.pop('age_epoch_years', None)
        if cp['sentient']:
            cp.update(romance_enabled=False, family_enabled=False, fertile=False,
                      autonomous=False, reproductive_role='none', accepts=['friend'])
        from engine import family_life, names
        if cp['sentient']:
            family_life.birth_sex(w, child)
            names.assign(w,child,force=True)
        w.add_entity(child, carrier.location)
        s['children'].append(dict(id=ident, parents=pregnancy['parents'], born=now))
        if cp['sentient']:
            family_life.register_birth(w, child, pregnancy['parents'])
        for pid in pregnancy['parents']:
            parent = w.entities.get(pid)
            if parent:
                parent.progress['family_ready_minute'] = now + policy(w, parent)['parent_cooldown_minutes']
                bond(w, parent, child)['kinds'].append('parent')
                if cp['sentient']:
                    if parent.location == child.location:
                        from engine import town_talk
                        town_talk.meet(w,parent,child)
                    else:
                        if hasattr(w,'_town_known_bonds'):del w._town_known_bonds
                        for member in (parent,child):member.progress.get('town_talk',{}).pop('introduced_family',None)
        event(w, child.name + ' was born.', pregnancy['parents'], public=True)
        del s['pregnancies'][cid]
    if now // 60 == s['last_social']: return
    s['last_social'] = now // 60
    # At most one authored social decision per NPC per game hour, locally.
    used = set()
    work = {}
    partner_counts = Counter(pid for row in s['bonds'].values()
                             if 'business' in row['kinds'] and not row.get('deceased')
                             for pid in row['participants'])
    for a in list(w.entities.values()):
        if a.is_player or not a.alive or a.id in used: continue
        pa = profile(w, a)
        if not pa['autonomous']: continue
        for b in w.entities_in_room(a.location):
            if b.is_player or b.id == a.id or b.id in used: continue
            pb = profile(w, b)
            if not pb['autonomous']: continue
            # These local decisions do not change social profiles. Reuse the
            # current pair's values; nothing is cached across simulation calls.
            common = set(pa['accepts']) & set(pb['accepts'])
            existing = state(w)['bonds'].get(key(a, b), {}).get('kinds', [])
            if not pa['sentient'] and not pb['sentient']:
                try:
                    breed_animals(w, a, b); used.update((a.id, b.id)); break
                except ValueError: pass
            for kind in KINDS:
                if kind in common and kind not in existing:
                    if kind == 'business' and not business_meeting(w, a, b, pa, pb, work, partner_counts, now):
                        continue
                    try: propose(w, a, b, kind)
                    except ValueError: continue
                    if kind == 'business':
                        partner_counts.update((a.id, b.id))
                    used.update((a.id, b.id)); break
            else:
                if pa['family_enabled'] and pb['family_enabled']:
                    try: conceive(w, a, b); used.update((a.id, b.id))
                    except ValueError: pass
            if a.id in used: break


def view(w, p):
    s = state(w)
    return dict(bonds=[deepcopy(r) for r in s['bonds'].values() if p.id in r['participants'] and (r['kinds'] or r['trust'] or r.get('social_actions'))],
        proposals=[deepcopy(r) for r in s['proposals'].values() if r['to'] == p.id],
        events=[deepcopy(r) for r in s['events'] if p.id in r['participants']][-20:],
        profile=profile(w, p))


def command(ctx, args):
    w, p = ctx.world, ctx.player
    verb, _, rest = args.strip().partition(' ')
    if not verb or verb == 'list':
        data = view(w, p)
        lines = ['Your relationships:']
        lines += [', '.join(r['names']) + ': ' + ', '.join(r['kinds']) + ' (trust ' + str(r['trust']) + ')' for r in data['bonds']]
        lines += ['Proposal ' + r['id'] + ': ' + r['sender'] + ' requests ' + r['kind'] for r in data['proposals']]
        return '\n'.join(lines)
    if verb in ('accept', 'decline'): return respond(w, p, rest.strip(), verb == 'accept')
    if verb == 'preferences':
        # Players choose their own participation; gender never implies fertility.
        field, _, value = rest.partition(' ')
        if field not in ('romance_enabled', 'family_enabled', 'fertile', 'reproductive_role'):
            raise ValueError('Choose romance_enabled, family_enabled, fertile or reproductive_role.')
        if field == 'reproductive_role':
            if value not in ('none', 'carrier', 'contributor'): raise ValueError('Choose none, carrier or contributor.')
        else:
            if value not in ('on', 'off'): raise ValueError('Choose on or off.')
            value = value == 'on'
        p.progress.setdefault('social_profile', {})[field] = value
        return 'Your relationship preference was updated.'
    if verb in ('propose', 'end'):
        kind, _, target = rest.partition(' ')
        candidates = [e for e in w.entities_in_room(p.location) if e.id != p.id]
        exact = [e for e in candidates if target.lower() in (e.id.lower(), e.name.lower())]
        if len(exact) != 1: raise ValueError('Choose a nearby character by exact name or ID.')
        other = exact[0]
        if verb == 'propose': return propose(w, p, other, kind)
        row = state(w)['bonds'].get(key(p, other), {})
        if kind not in KINDS or kind not in row.get('kinds', []): raise ValueError('That relationship does not exist.')
        row['kinds'].remove(kind)
        if kind in ROMANTIC:
            for person, partner in ((p,other),(other,p)):
                household = person.progress.get('population')
                if household and household.get('current_partner_id') == partner.id:
                    if kind == 'married': household['marital_status'] = 'divorced'
                    if not any(k in ROMANTIC for k in row['kinds']):
                        household.update(current_partner_id=None,partnership_status='single')
        row['history'].append(dict(minute=living.state(w)['minute'], action='ended', kind=kind, actor=p.id))
        event(w, p.name + ' ended the ' + kind + ' relationship.', [p.id, other.id])
        return 'Relationship ended.'
    raise ValueError('Use relationship list, propose <kind> <name>, accept/decline <ID>, end <kind> <name>, or preferences <field> <value>.')


def register(reg):
    from engine.commands import Command
    reg.register(Command('relationship', 'Relationships, consent and family preferences',
        'relationship <action>', command, available=lambda ctx: society.enabled(ctx.world), example='relationship list'))


def validate(data):
    issues = []
    groups = {r['id'] for r in data.get('group', [])}
    for kind in ('npc', 'race', 'group'):
        for obj in data.get(kind, []):
            field = 'coupling_rules' if kind == 'group' else 'social_profile'
            supplied = obj.get(field, {})
            if not isinstance(supplied, dict):
                issues.append(obj['id'] + ': ' + field + ' must be an object'); continue
            defaults = POLICY if kind == 'group' else PROFILE
            cfg = {**defaults, **supplied}
            for name, default in defaults.items():
                value = cfg[name]
                valid = isinstance(value, type(default)) and not (isinstance(default, int) and not isinstance(default, bool) and isinstance(value, bool))
                if isinstance(default, list): valid = valid and all(isinstance(v, str) for v in value)
                if isinstance(default, int) and not isinstance(default, bool): valid = valid and value >= 0
                if name == 'grown_family_percent' and type(value) is int:
                    valid = 0 <= value <= 100
                if name == 'business_meeting_days' and type(value) is int:
                    valid = value >= 1
                if not valid: issues.append(obj['id'] + ': invalid ' + name)
            if kind == 'group':
                for name in ('minimum_standing', 'infidelity_trust_penalty'):
                    if type(cfg[name]) is int and cfg[name] > 100: issues.append(obj['id'] + ': ' + name + ' must be 0–100')
                for name in ('allowed_factions', 'forbidden_factions'):
                    if isinstance(cfg[name], list) and any(g not in groups for g in cfg[name]): issues.append(obj['id'] + ': unknown faction in ' + name)
                for name in ('gestation_minutes', 'population_limit'):
                    if cfg[name] == 0: issues.append(obj['id'] + ': ' + name + ' must be positive')
            else:
                if cfg['reproductive_role'] not in ('none', 'carrier', 'contributor'): issues.append(obj['id'] + ': invalid reproductive role')
                if isinstance(cfg['accepts'], list) and any(k not in KINDS for k in cfg['accepts']): issues.append(obj['id'] + ': invalid relationship preference')
                if isinstance(cfg['breeding_seasons'], list) and any(k not in ('spring', 'summer', 'autumn', 'winter') for k in cfg['breeding_seasons']): issues.append(obj['id'] + ': invalid breeding season')
                if cfg['gestation_minutes'] == 0: issues.append(obj['id'] + ': gestation must be positive')
    return issues
