"""Reusable regional systems enabled and authored by a world's own data."""


def enabled(w):
    cfg = getattr(w, 'rules', {}).get('regional_gameplay', {})
    return isinstance(cfg, dict) and cfg.get('enabled') is True


def config(w, name, default):
    cfg = getattr(w, 'rules', {}).get('regional_gameplay', {})
    value = cfg.get(name, default) if isinstance(cfg, dict) else default
    return value


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


def install(w):
    if not enabled(w):
        return
    from engine import regional_encounters, regional_zoo, city_justice, city_defense
    regional_encounters.install(w)
    regional_zoo.install(w)
    city_justice.install(w)
    city_defense.install(w)


def advance(w):
    if not enabled(w):
        return
    from engine import regional_encounters, regional_zoo, city_justice, city_defense
    regional_encounters.advance(w)
    regional_zoo.advance(w)
    city_justice.advance(w)
    city_defense.advance(w)


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
