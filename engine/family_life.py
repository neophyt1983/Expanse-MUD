"""Households and working lives for residents born during play."""
from hashlib import sha256
from engine import life_stages, living, population, worldtime

YEAR = worldtime.MINUTES_PER_YEAR


def roll(identity, label, limit):
    value = sha256(f'{identity}:{label}'.encode()).digest()
    return int.from_bytes(value[:4], 'big') % limit


def birth_sex(world, child):
    definition = world.npcs.get(child.source_def, {})
    authored = definition.get('sex') or definition.get('gender')
    if child.sex or authored:
        child.sex = child.sex or authored
        return
    options = [key for key in ('female', 'male', 'nonbinary') if key in world.sexes]
    if options:
        child.sex = options[roll(child.id, 'presentation', len(options))]


def register_birth(world, child, parents):
    if child.progress.get('population'):
        return
    family = [world.entities[i] for i in parents if i in world.entities]
    known_home = next((r for p in family for r in (
        p.progress.get('home_room'), world.npcs.get(p.source_def, {}).get('home_room')) if r in world.rooms), child.location)
    s = population.state(world)
    homes = [p.progress.get('population', {}).get('household_id') or p.progress.get('birth_household') for p in family]
    hid = next((h for h in homes if h in s['households']), 'family:'+'|'.join(sorted(parents)))
    house = s['households'].setdefault(hid, dict(id=hid, type='family', home_room=known_home,
        members=list(parents), eligible_guardians=list(parents), history=[], care_needs=[]))
    home = house['home_room'] if house['home_room'] in world.rooms else known_home
    for p in family:
        p.progress.setdefault('birth_household', hid)
    if child.id not in house['members']:
        house['members'].append(child.id)
    from engine import livelihoods
    job = next((livelihoods.definition(world,p) for p in family
                if livelihoods.definition(world,p).get('work_room') in world.rooms), {})
    vocation = {k:job[k] for k in ('work_room','occupation','profession','work_hours') if k in job}
    school = next((p.progress['population']['education'] for p in family
                   if p.progress.get('population',{}).get('education',{}).get('school_room') in world.rooms), {})
    room = school.get('school_room')
    providers = list(school.get('school_provider_ids', []))
    if not room:
        from engine import gazette
        area = gazette.local(world, home)
        for teacher in world.entities.values():
            if teacher.group_id != child.group_id or not teacher.alive:
                continue
            definition = livelihoods.definition(world, teacher)
            site = definition.get('work_room')
            if definition.get('occupation') == 'teacher' and site in world.rooms and (
                    site == home or (area and gazette.local(world,site) == area)):
                room, providers = site, [teacher.id]
                break
    child.progress['home_room'] = home
    child.progress['population'] = dict(born_resident=True, household_id=hid, home_room=home,
        biological_parent_ids=list(parents), guardian_ids=list(parents), guardian_eligible=False,
        marital_status='never_married', partnership_status='single', relationship_history=[], leisure_rooms=[],
        vocation=vocation, education=dict(phase='infant',enrollment='dependent',learning_room=home,
        learning_mode='school' if room else 'home',school_room=room or home,
        school_provider_ids=providers or list(parents), provider_ids=list(parents), history=[]))
    s['members'][child.id] = dict(entity_id=child.id, source_def=child.source_def, born_resident=True, status='living')
    birth_sex(world,child)
    population._care(world,child)


def care_shift(world, parent):
    hid = parent.progress.get('birth_household')
    if not hid or parent.is_player or parent.progress.get('population'):
        return False
    house = population.state(world)['households'].get(hid, {})
    for ident in house.get('members', []):
        child = world.entities.get(ident)
        if not child or not child.alive or not child.progress.get('population', {}).get('born_resident'):
            continue
        stage = life_stages.for_entity(world, child)
        if stage['adult'] or stage['in_school']:
            continue
        guardians = [world.entities[i] for i in child.progress['population']['guardian_ids']
                     if i in world.entities and world.entities[i].alive]
        # A player decides where to go. An available resident handles the home shift.
        carer = next((g for g in guardians if not g.is_player), None)
        if carer and parent.id == carer.id:
            home = child.progress['home_room']
            target = child.location if child.location != home else home
            path = population._safe_path(world,parent,target)
            if path:
                world.move_entity(parent.id,path[0])
            if parent.location == child.location and child.location != home:
                path = population._safe_path(world,parent,home)
                if path:
                    world.move_entity(parent.id,path[0])
                    world.move_entity(child.id,path[0])
            parent.activity = 'household caregiving' if parent.location == child.location else 'returning for household care'
            return True
    return False


def mature(world, person, profile, stage):
    if not profile.get('born_resident') or not stage['adult']:
        return
    household = population.state(world)['households'][profile['household_id']]
    if not profile.get('guardian_eligible'):
        profile['guardian_eligible'] = True
        if person.id not in household['eligible_guardians']:
            household['eligible_guardians'].append(person.id)
    if 'adult_choices' in profile:
        return
    # An NPC considers partnership independently once of age. Players never enter this path.
    prefs = world.npcs.get(person.source_def, {}).get('social_profile', {})
    allowed = prefs.get('grown_family_percent', 50)
    interested = roll(person.id, 'adult family preference', 100) < allowed
    social = person.progress['social_profile']
    social.update(autonomous=True, accepts=['friend', 'business'])
    if interested:
        social.update(romance_enabled=True, family_enabled=True, fertile=True,
                      reproductive_role=('carrier','contributor')[roll(person.id,'adult role',2)],
                      accepts=['friend','business','lover','married'])
    profile['adult_choices'] = True


def advance(world):
    if not world.metadata.get('society'):
        return
    from engine import relationships, mortality, gazette
    state = living.state(world)
    day = state['minute'] // worldtime.MINUTES_PER_DAY
    if state.get('resident_age_day') == day:
        return
    for person in list(world.entities.values()):
        if person.is_player or not person.alive:
            continue
        social = relationships.profile(world, person)
        if not social['sentient'] or social['undead']:
            continue
        born = person.progress.get('social_profile', {}).get('parents')
        if born and person.source_def == 'sx_child':
            register_birth(world,person,born)
        prof = person.progress.get('population', {})
        if not (prof or social['autonomous']) or not social.get('age_in_world', True):
            continue
        config = person.progress.setdefault('social_profile', {})
        if social.get('born_minute') is None and social.get('age_epoch_minute') is None:
            config.update(age_epoch_minute=state['minute'],age_epoch_years=social['age_years'])
            social.update(config)
        stage = life_stages.classify(social, getattr(world,'species',{}).get(social['species']), state['minute'])
        if prof:
            population._life_update(world,person,stage)
            mature(world,person,prof,stage)
        span = social.get('elder_lifespan_years', 25)
        if not span:
            continue
        plan = person.progress.get('old_age')
        if not plan:
            cfg = life_stages.resolve_profile(social['species'], getattr(world,'species',{}).get(social['species']))
            end = cfg['elder_years'] + max(1, span//2) + roll(person.id,'lifespan',1+span//2)
            plan = person.progress['old_age'] = dict(end_age=max(end, stage['age_years']+1),
                retirement_age=cfg['elder_years']+roll(person.id,'retirement',max(1,span//3)))
        if stage['age_years'] >= plan['end_age']:
            person.hp=0
            mortality.record_death(world,person,'old age')
            from engine.commands import _on_npc_death
            _on_npc_death(world,world.rooms[person.location],person)
            if person.source_def and not person.spawner_key:
                world.killed_npcs.add(person.source_def)
            gazette.record(world,person.location,'Community',f'{person.name} died of old age.')
            from engine import commands
            mode = commands._corpse_mode_for(world, person)
            if mode == 'disappear':
                commands._remove_entity(world, world.rooms[person.location], person.id)
            elif mode == 'timed':
                from time import monotonic
                person.corpse_expires_at = monotonic() + commands._corpse_ttl(world, person)
        elif stage['age_years'] >= plan['retirement_age']:
            person.progress['retired'] = True
    state['resident_age_day'] = day
