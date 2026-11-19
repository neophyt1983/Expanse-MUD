"""Authored game-world clinics: actual staff, finite supplies and paid care.

This preserves the game's existing injury/disease treatment outcome. Rooms
without an enabled clinic retain legacy service behavior in living.command.
It models no real medical diagnoses, protocols or treatment advice.
"""
from collections import Counter

from engine import living, relationships, sleep_movement, task_skills, worldtime

KEY = 'clinical_care_v1'


def config(world, room):
    value = getattr(world, 'room_details', {}).get(room, {}).get('clinical_services', {})
    return value if isinstance(value, dict) and value.get('enabled') is True else None


def _plan(world, patient):
    if patient is None or world.entities.get(patient.id) is not patient or patient.location not in world.rooms:
        return None, 'Enter the clinic before requesting care.'
    cfg = config(world, patient.location)
    if cfg is None:
        return None, 'This room has no staffed clinical service.'
    if not patient.alive or sleep_movement.asleep(world, patient) or not relationships.sentient(world, patient):
        return None, 'The patient must be awake and able to request care.'
    from engine import geology_impacts, livelihoods
    minute = getattr(world, 'living_state', {}).get('minute', worldtime.initial_minute(world.metadata))
    hours = world.room_details[patient.location].get('opening_hours', {})
    if (geology_impacts.room_unusable(world, patient.location) or
            (livelihoods.enabled(world) and hours and
             (minute - hours.get('start', 420)) % worldtime.MINUTES_PER_DAY >= hours.get('duration', 600))):
        return None, 'This clinic is closed. Return during its opening hours.'
    if not (patient.progress.get('injury', 0) or patient.progress.get('disease', 0)):
        return None, 'You have no injury or disease needing this service.'
    from engine import frontiers
    staff = sorted((person for person in world.entities_in_room(patient.location)
                    if person is not patient and not person.is_player and person.alive
                    and person.location == patient.location and person.source_def in cfg['staff']
                    and relationships.sentient(world, person) and not sleep_movement.asleep(world, person)
                    and person.progress.get('restrained_until', 0) <= minute
                    and not frontiers.hostile(world, person, patient)
                    and task_skills.level(world, person, 'healing') >= cfg.get('min_skill', 0)),
                   key=lambda person: person.id)
    if not staff:
        return None, 'No qualified, awake medical professional is available here.'
    details = world.room_details[patient.location]
    fee = details.get('services', {}).get('treatment', 0)
    if patient.gold < fee:
        return None, 'Treatment costs ' + str(fee) + ' gold; you do not have enough.'
    rows = [row for row in details.get('locks', []) if row.get('id') == cfg['container'] and not row.get('direction')]
    if len(rows) != 1:
        return None, 'The clinic’s receiving cabinet is unavailable.'
    row = rows[0]
    stored = getattr(world, 'living_state', {}).get('physical_locks', {}).get(patient.location + ':' + row['id'])
    contents = stored.get('contents', []) if isinstance(stored, dict) else row.get('contents', [])
    counts = Counter(contents)
    if any(counts[item] < count for item, count in cfg['supplies'].items()):
        return None, 'The clinic needs supplies before it can provide treatment. Read its supply requests.'
    return dict(cfg=cfg, practitioner=staff[0], row=row, fee=fee, contents=list(contents)), ''


def projection(world, patient):
    """Read-only service availability; never expose staff private inventories."""
    cfg = config(world, getattr(patient, 'location', None))
    if cfg is None:
        return None
    plan, reason = _plan(world, patient)
    return dict(room=patient.location, name=world.rooms[patient.location].name,
                fee=world.room_details[patient.location].get('services', {}).get('treatment', 0),
                enabled=not reason, reason=reason,
                practitioner=plan['practitioner'].name if plan else None,
                command='service treatment')


def treat(world, patient):
    """Complete one revalidated finite service for either actor kind."""
    plan, reason = _plan(world, patient)
    if reason:
        raise ValueError(reason)
    cfg, practitioner = plan['cfg'], plan['practitioner']
    remaining = plan['contents']
    for item, count in cfg['supplies'].items():
        for _ in range(count):
            remaining.remove(item)
    from engine import locks
    stored = locks.saved(world, patient.location, plan['row'])
    stored['contents'][:] = remaining
    patient.gold -= plan['fee']
    practitioner.gold += plan['fee']
    patient.progress['injury'] = 0
    patient.progress['disease'] = 0
    ledger = living.state(world).setdefault(KEY, {'services': 0})
    ledger['services'] += 1
    ledger['last'] = dict(patient=patient.id, practitioner=practitioner.id,
                          room=patient.location, minute=living.state(world)['minute'])
    task_skills.practice(world, practitioner, 'healing', difficulty=cfg.get('min_skill', 0),
                         effort=3, event_id='clinical:' + str(ledger['services']))
    if patient.is_player:
        world.dirty_players = getattr(world, 'dirty_players', set()) | {patient.id}
    return (practitioner.name + ' treats your injury and disease using the clinic’s supplies. '
            'Treatment completed; paid ' + str(plan['fee']) + ' gold.')


def step(world, actor):
    """A local NPC can request care it actually needs; never seek hidden clinics."""
    if actor.is_player or not config(world, actor.location):
        return False
    plan, reason = _plan(world, actor)
    if reason:
        return False
    treat(world, actor)
    actor.progress['activity'] = 'received care at ' + world.rooms[actor.location].name
    return True


def validate(data):
    rooms = {row['id']: row for row in data.get('room', [])}
    npcs = {row['id']: row for row in data.get('npc', [])}
    items = {row['id']: row for row in data.get('item', [])}
    errors = []
    for ident, room in rooms.items():
        cfg = room.get('clinical_services', {})
        if not isinstance(cfg, dict):
            errors.append(ident + ': clinical_services must be an object')
            continue
        if not cfg:
            continue
        if set(cfg) - {'enabled', 'staff', 'container', 'supplies', 'min_skill'}:
            errors.append(ident + ': unsupported clinical service fields')
        if type(cfg.get('enabled', False)) is not bool:
            errors.append(ident + ': clinical enabled must be boolean')
        staff = cfg.get('staff', [])
        if (not isinstance(staff, list) or not 1 <= len(staff) <= 16 or
                any(not isinstance(person, str) or person not in npcs for person in staff) or len(set(staff)) != len(staff)):
            errors.append(ident + ': clinical staff must name 1–16 distinct existing NPC sources')
            staff = []
        minimum = cfg.get('min_skill', 0)
        if type(minimum) is not int or not 0 <= minimum <= 100:
            errors.append(ident + ': clinical min_skill must be 0–100')
        supplies = cfg.get('supplies', {})
        if (not isinstance(supplies, dict) or not 1 <= len(supplies) <= 8 or
                any(item not in items or items[item].get('anchored_readable') or type(count) is not int or not 1 <= count <= 10
                    for item, count in supplies.items())):
            errors.append(ident + ': clinical supplies need 1–8 real movable items with quantities 1–10')
        rows = [row for row in room.get('locks', []) if row.get('id') == cfg.get('container') and not row.get('direction')]
        if len(rows) != 1 or rows[0].get('owner') not in staff:
            errors.append(ident + ': clinic needs one actual cabinet owned by a staff member')
        fee = room.get('services', {}).get('treatment')
        if type(fee) is not int or not 0 <= fee <= 10000:
            errors.append(ident + ': clinic needs an authored treatment fee from 0 to 10000')
    return errors
