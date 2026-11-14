"""Opt-in regional civic places and bounded encounters for the Wild Lands pack.

Generated IDs are stable. Existing creator definitions and exits are never
replaced. This supplies the official pack's runtime supplement; custom worlds
may explicitly enable it with metadata.regional_gameplay.enabled.
"""
import re
from copy import deepcopy
from engine import living
from engine.core import Room


def enabled(w):
    cfg = w.metadata.get('regional_gameplay', {})
    if isinstance(cfg, dict) and 'enabled' in cfg:
        return cfg['enabled'] is True
    rules = getattr(w, 'rules', {})
    return bool(w.metadata.get('living_world') and w.metadata.get('civic_places_v1')
                and rules.get('regions') and rules.get('ward')
                and 'wl_horror_0' in w.npcs)


def config(w, name, default):
    cfg = w.metadata.get('regional_gameplay', {})
    value = cfg.get(name, default) if isinstance(cfg, dict) else default
    return value


def key(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).casefold()).strip('_')


def cities(w):
    return [row for row in w.metadata.get('press_editions', [])
            if row.get('kind') in ('city', 'town') and row.get('home') in w.rooms]


def city_for(w, room):
    from engine import gazette
    edition = gazette.local(w, room)
    group = w.rooms[room].group if room in w.rooms else None
    if edition and edition.get('kind') in ('city', 'town') and (not group or edition.get('group')==group):
        return edition
    return next((row for row in cities(w) if row.get('group') == group), None)


def add_room(w, ident, name, description, city, *, x=0, y=0, floor=0, environment='building', facilities=(), **extra):
    if ident in w.rooms:
        return w.rooms[ident]
    anchor = w.rooms[city['home']]
    base = deepcopy(living.details(w, city['home']).get('climate', {}))
    base['sheltered'] = environment == 'building'
    base['controlled_growing'] = environment == 'building'
    details = dict(id=ident, name=name, description=description, exits={}, items=[], spawners=[],
                   group=city.get('group'), map_x=(anchor.map_x or 0) + x,
                   map_y=(anchor.map_y or 0) + y, map_z=50 + floor,
                   map_visibility='discovered', environment=environment,
                   facilities=list(facilities), climate=base, truce=True, campable=False,
                   press_locality=city['name'], regional_generated=True, **extra)
    w.room_details[ident] = details
    room = Room(id=ident, name=name, description=description, group=city.get('group'),
                map_x=details['map_x'], map_y=details['map_y'], map_z=details['map_z'])
    w.add_room(room)
    return room


def connect(w, source, direction, destination, back=None):
    """Add an unused authored edge, without removing a creator's route."""
    current = w.rooms[source].exits.get(direction)
    if current not in (None, destination):
        return False
    w.rooms[source].exits[direction] = destination
    w.room_details.setdefault(source, {}).setdefault('exits', {})[direction] = destination
    if back:
        reverse = w.rooms[destination].exits.get(back)
        if reverse in (None, source):
            w.rooms[destination].exits[back] = source
            w.room_details[destination].setdefault('exits', {})[back] = source
    return True


def install(w):
    if not enabled(w):
        return
    from engine import regional_encounters, regional_zoo, city_justice
    regional_encounters.install(w)
    regional_zoo.install(w)
    city_justice.install(w)


def advance(w):
    if not enabled(w):
        return
    from engine import regional_encounters, regional_zoo, city_justice
    regional_encounters.advance(w)
    regional_zoo.advance(w)
    city_justice.advance(w)


def on_entry(w, actor):
    if not enabled(w) or not actor.is_player:
        return
    from engine import regional_zoo
    regional_zoo.populate(w, actor.location)


def blocked(w, actor, destination):
    if actor is None or (not actor.progress.get('zoo_exhibit') and not actor.progress.get('court_case')):
        return ''
    if not enabled(w):
        return ''
    exhibit = actor.progress.get('zoo_exhibit')
    if exhibit and destination != exhibit.get('home'):
        return 'The exhibit is secured inside its protected habitat.'
    from engine import city_justice
    return city_justice.blocked(w, actor, destination)


def validate_combat(w, actor, victim):
    if actor.progress.get('zoo_exhibit') or victim.progress.get('zoo_exhibit'):
        raise ValueError('Protected zoo exhibits are behind secure barriers; fighting and hunting are not permitted.')
    if (actor.progress.get('court_case') or victim.progress.get('court_case')) and enabled(w):
        from engine import city_justice
        if city_justice.confined(w, actor) or city_justice.confined(w, victim):
            raise ValueError('You are in court custody. Your case and release time are shown in the court notice.')


def notice(w, actor, text, *, room=None):
    if actor is not None and actor.is_player:
        w.rest_notifications = (getattr(w, 'rest_notifications', []) + [(actor.id, text)])[-500:]
    elif room in w.rooms:
        w.runtime_notifications = (getattr(w, 'runtime_notifications', []) + [(room, text)])[-500:]
