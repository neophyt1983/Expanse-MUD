"""Persistent, once-enrolled civilian households and safe dependent routines.

The loader creates ordinary unkeyed NPCs. Call ensure only AFTER restoring the
saved living state, or just before the first tick/snapshot in a new world. This
module never generates people, resets profiles, creates property or respawns.
"""
from copy import deepcopy

from engine import living, worldtime


def enabled(world):
    manifest=getattr(world,'population_manifest',None)
    return isinstance(manifest,dict) and manifest.get('version')==1 and bool(manifest.get('cohorts'))


def state(world):
    return living.state(world).setdefault('population',dict(version=1,members={},households={},events=[]))


def _remove(world,entity):
    room=world.rooms.get(entity.location)
    if room and entity.id in room.entities:room.entities.remove(entity.id)
    world.entities.pop(entity.id,None)


def ensure(world):
    """Initialize only manifest-enrolled new actors; persisted absence is final.

    A known member with a fresh loader instance but no saved enrollment marker
    was absent from the save. Remove that instance instead of resurrecting them.
    Definitions deliberately removed by a creator remain removed.
    """
    if not enabled(world):return
    manifest=world.population_manifest
    current=getattr(world,'living_state',None)
    stamp=(id(current),id(manifest),len(world.npcs))
    if getattr(world,'_population_ready',None)==stamp:return
    from engine.population_content import validate_manifest,PopulationError
    data=dict(npc=list(world.npcs.values()),room=list(getattr(world,'room_details',{}).values()) or [dict(id=r.id) for r in world.rooms.values()],species=list(getattr(world,'species',{}).values()),race=list(world.races.values()),group=list(world.groups.values()),encounter=list(getattr(world,'encounters',{}).values()))
    errors=validate_manifest(data,manifest)
    if errors:raise PopulationError('; '.join(errors))
    from engine import life_stages
    now=current.get('minute',worldtime.initial_minute(world.metadata)) if isinstance(current,dict) else worldtime.initial_minute(world.metadata)
    # Validate all authored explicit clocks before the first progress/state write.
    pending={sid for c in manifest['cohorts'].values() for sid in c['source_ids']}
    history_births={}
    for actor in world.entities.values():
        if actor.source_def in pending and actor.source_def in world.npcs and not actor.progress.get('population'):
            definition=world.npcs[actor.source_def];social=definition.get('social_profile',{})
            issues=life_stages.validate_age(social,now,label=actor.source_def+'.social_profile')
            if issues:raise PopulationError('; '.join(issues))
            # Relationship history needs a birth minute, but an authored age
            # epoch remains authoritative on the actor. Prepare this derived
            # history value before any enrollment mutation can occur.
            born=social.get('born_minute')
            if born is None and social.get('age_epoch_minute') is not None:
                try:born=social['age_epoch_minute']-round(social['age_epoch_years']*worldtime.MINUTES_PER_YEAR)
                except (OverflowError,ValueError):raise PopulationError(actor.source_def+': age epoch cannot be represented in whole Expanse minutes.') from None
            if born is None:
                pp=definition['population_profile']
                born=now-pp['age_years']*worldtime.MINUTES_PER_YEAR-pp.get('age_fraction_minutes',0)
            history_births[actor.source_def]=born
    current=living.state(world);s=state(world);now=current['minute']
    stamp=(id(current),id(manifest),len(world.npcs))
    by_source={e.source_def:e for e in world.entities.values() if not e.is_player}
    defs={sid:world.npcs[sid] for cohort in manifest['cohorts'].values() for sid in cohort['source_ids'] if sid in world.npcs}
    fresh=[]
    for sid,definition in defs.items():
        entity=by_source.get(sid);record=s['members'].get(sid)
        if sid in world.killed_npcs or (record and record.get('status') in ('dead','removed')):
            if entity:_remove(world,entity)
            continue
        if record and entity and (not entity.progress.get('population') or entity.id!=record['entity_id']):
            _remove(world,entity);record['status']='removed';record['removed_minute']=now
            continue
        if not entity or not entity.alive:continue
        if entity.progress.get('population'):
            # Restored profiles, names, jobs, health and education are authoritative.
            if not record:s['members'][sid]=dict(entity_id=entity.id,cohort_id=definition['population_profile']['cohort_id'],status='living')
            continue
        pp=definition['population_profile']
        initial=pp['age_years']*worldtime.MINUTES_PER_YEAR+pp.get('age_fraction_minutes',0)
        social=deepcopy(definition.get('social_profile',{}))
        if social.get('born_minute') is None and social.get('age_epoch_minute') is None:social['born_minute']=now-initial
        entity.progress['social_profile']=social
        profile={k:deepcopy(pp.get(k)) for k in ('version','cohort_id','household_id','home_room','marital_status','relationship_history','guardian_eligible','education','appearance','leisure_rooms','partnership_status','care_role')}
        profile.update(enrolled_minute=now,initial_age_years=life_stages.age_years(social,now),care_need=False)
        entity.progress['population']=profile
        # Home membership is not a property claim. Never assign home_property.
        entity.progress.setdefault('home_room',pp['home_room'])
        if pp.get('health') is not None:entity.progress.setdefault('population_health',deepcopy(pp['health']))
        s['members'][sid]=dict(entity_id=entity.id,cohort_id=pp['cohort_id'],status='living',enrolled_minute=now)
        fresh.append(entity)
    for sid,record in s['members'].items():
        if not record.get('born_resident') and sid not in world.npcs and record.get('status')=='living':
            record.update(status='removed',removed_minute=now)
            entity=world.entities.get(record['entity_id'])
            if entity:_remove(world,entity)
    def identity(sid):
        row=s['members'].get(sid)
        return row['entity_id'] if row else 'npc:'+sid
    for hid,authored in manifest['households'].items():
        if hid not in s['households']:
            s['households'][hid]=dict(id=hid,cohort_id=authored['cohort_id'],type=authored['type'],home_room=authored['home_room'],members=[identity(i) for i in authored['member_source_ids']],member_source_ids=list(authored['member_source_ids']),eligible_guardians=[identity(i) for i in authored['eligible_guardian_source_ids']],history=[dict(event='enrolled',minute=now)],care_needs=[])
    if fresh:
        from engine import relationships
        rs=relationships.state(world)
        existing_children={c['id'] for c in rs['children']}
        for entity in fresh:
            pp=defs[entity.source_def]['population_profile'];profile=entity.progress['population']
            profile['guardian_ids']=[identity(i) for i in pp['guardian_source_ids']]
            profile['biological_parent_ids']=[identity(i) for i in pp['biological_parent_source_ids']]
            partner=pp.get('current_partner_source_id');profile['current_partner_id']=identity(partner) if partner else None
            profile['education']['provider_ids']=[identity(i) for i in pp['education'].get('provider_source_ids',[])]
            profile['education']['school_provider_ids']=[identity(i) for i in pp['education'].get('school_provider_source_ids',[])]
            if profile['biological_parent_ids'] and entity.id not in existing_children:
                rs['children'].append(dict(id=entity.id,parents=list(profile['biological_parent_ids']),born=history_births[entity.source_def],origin='initial_population'))
                existing_children.add(entity.id)
            for pid in profile['guardian_ids']:
                guardian=world.entities.get(pid)
                if guardian:
                    bond=relationships.bond(world,entity,guardian)
                    if 'guardian' not in bond['kinds']:bond['kinds'].append('guardian')
                    bond['history'].append(dict(action='initial_guardianship',minute=now,dependent=entity.id))
            if partner:
                other=world.entities.get(profile['current_partner_id'])
                if other and other.alive:
                    bond=relationships.bond(world,entity,other)
                    kind='married' if profile['marital_status']=='married' else 'lover'
                    if kind not in bond['kinds']:
                        bond['kinds'].append(kind);bond['history'].append(dict(action='initial_partnership',kind=kind,minute=now,origin='authored_population'))
        for entity in fresh:_care(world,entity)
    # Persist missing/removed membership and care gaps without fabricating relatives.
    for entity in list(world.entities.values()):
        if entity.progress.get('population'):
            _life_update(world,entity,life_stages.for_entity(world,entity));_care(world,entity)
    world._population_ready=stamp


def _care(world,entity):
    from engine import life_stages
    profile=entity.progress.get('population')
    if not profile or not entity.alive or life_stages.for_entity(world,entity)['adult']:return
    s=state(world);house=s['households'].get(profile['household_id'],{})
    def eligible(eid):
        actor=world.entities.get(eid)
        return actor is not None and actor.alive and life_stages.for_entity(world,actor)['adult']
    current=[pid for pid in profile.get('guardian_ids',[]) if eligible(pid)]
    if not current:
        current=[pid for pid in house.get('eligible_guardians',[]) if eligible(pid)]
        if current:
            profile.setdefault('relationship_history',[]).append(dict(event='guardianship_reassigned',guardian_ids=current,minute=living.state(world)['minute']))
            house.setdefault('history',[]).append(dict(event='guardianship_reassigned',dependent=entity.id,guardian_ids=current,minute=living.state(world)['minute']))
    profile['guardian_ids']=current;profile['care_need']=not bool(current)
    profile['supervision_available']=any(world.entities[pid].location==entity.location for pid in current)
    # A caregiving role is only assigned to an already eligible guardian. No
    # adult, room or relationship is invented when a household loses support.
    stage=life_stages.for_entity(world,entity)
    if not stage['in_school'] and current and not any(world.entities[pid].progress.get('population',{}).get('care_role')=='home_caregiver' for pid in current):
        guardian=world.entities[current[0]]
        gp=guardian.progress.get('population')
        if gp:gp['care_role']='home_caregiver'
    needs=house.setdefault('care_needs',[])
    if profile['care_need'] and entity.id not in needs:needs.append(entity.id)
    if not profile['care_need'] and entity.id in needs:needs.remove(entity.id)



def _life_update(world,entity,stage):
    """Change current enrollment at thresholds, never invent attained credentials."""
    profile=entity.progress['population'];ed=profile['education']
    phase='adult' if stage['adult'] else 'infant' if stage['stage']=='infant' else 'preschool' if not stage['in_school'] else 'school'
    old=ed.get('phase',phase)
    if old!=phase:
        ed.setdefault('history',[]).append(dict(event='life_stage_transition',from_phase=old,to_phase=phase,minute=living.state(world)['minute'],previous_enrollment=ed.get('enrollment')))
        if phase=='adult':
            ed['enrollment']='none';ed['learning_room']=None;ed['provider_ids']=[]
            ed['provision']='adult learning remains available; no qualification inferred from age'
        elif phase=='school':
            ed['enrollment']=ed.get('learning_mode','home')
            ed['learning_room']=ed.get('school_room',profile['home_room'])
            ed['provider_ids']=list(ed.get('school_provider_ids',profile.get('guardian_ids',[])))
            ed['provision']='guardian-led home learning' if ed['enrollment']=='home' else 'authored '+ed['enrollment']+' teaching'
        elif phase=='preschool':ed.update(enrollment='early_learning',learning_room=profile['home_room'],provision='guardian-led home learning')
    ed['phase']=phase
    if stage['adult']:
        profile['care_need']=False;profile.pop('care_provision_unavailable',None);profile.pop('teaching_unavailable',None)
        house=state(world)['households'].get(profile['household_id'],{})
        if entity.id in house.get('care_needs',[]):house['care_needs'].remove(entity.id)


def on_death(world,entity):
    """Retain history, widow a spouse, and choose only already eligible guardians."""
    if entity.alive:return
    profile=entity.progress.get('population')
    if not profile:return
    s=state(world);record=s['members'].get(entity.id if profile.get('born_resident') else entity.source_def)
    if not record or record.get('status')=='dead':return
    now=living.state(world)['minute'];record.update(status='dead',death_minute=now)
    if not profile.get('born_resident'):world.killed_npcs.add(entity.source_def)
    profile.setdefault('relationship_history',[]).append(dict(event='death',minute=now))
    house=s['households'].get(profile['household_id'],{})
    house.setdefault('history',[]).append(dict(event='death',member=entity.id,minute=now))
    partner=world.entities.get(profile.get('current_partner_id'))
    if partner and partner.alive and partner.progress.get('population'):
        other=partner.progress['population']
        if other.get('current_partner_id')==entity.id:
            was_married=other.get('marital_status')=='married'
            other.update(current_partner_id=None,partnership_status='bereaved',marital_status='widowed' if was_married else other.get('marital_status','never_married'))
            other.setdefault('relationship_history',[]).append(dict(event='partner_death',partner_id=entity.id,minute=now,was_married=was_married))
    for eid in house.get('members',[]):
        member=world.entities.get(eid)
        if member:_care(world,member)
    s['events']=(s.get('events',[])+[dict(event='death',entity_id=entity.id,minute=now)])[-500:]


def _open(world,rid):
    from engine import livelihoods,geology_impacts
    if rid not in world.rooms or geology_impacts.room_unusable(world,rid):return False
    hours=living.details(world,rid).get('opening_hours')
    if hours and (living.state(world)['minute']-hours.get('start',420))%worldtime.MINUTES_PER_DAY>=hours.get('duration',600):return False
    return livelihoods.room_open(world,rid)


def _safe_path(world,entity,target):
    """Share bounded route suffixes; validate live edges without a world scan.

    Stored routes are suggestions, never permission. Doors, closures, faction
    restrictions, live threats and geological blocks along the short cached
    route are checked before moving. A changed edge triggers a fresh safe BFS.
    """
    from collections import deque,OrderedDict
    from engine import frontiers
    from engine.population_content import _safe_room
    if target not in world.rooms or entity.location not in world.rooms:return None
    groups=world.groups
    def safe_room(rid):
        if not _open(world,rid) or not _safe_room(living.details(world,rid),entity.group_id,groups):return False
        return not any(world.npcs.get(e.source_def,{}).get('aggressive') or world.npcs.get(e.source_def,{}).get('traffic',{}).get('enabled') for e in world.entities_in_room(rid))
    if not safe_room(target):return None
    if entity.location==target:return ()
    cache=getattr(world,'_population_route_cache',None)
    if cache is None:cache=world._population_route_cache=OrderedDict()
    key=(entity.group_id,entity.location,target)
    cached=cache.get(key)
    if cached:
        nodes,index=cached
        valid=True
        for before,next_room in zip(nodes[index:],nodes[index+1:]):
            if before not in world.rooms or next_room not in world.rooms or not safe_room(next_room) or not any(dest==next_room and not frontiers.blocked(world,before,di,entity) for di,dest in world.rooms[before].exits.items()):
                valid=False;break
        if valid:
            cache.move_to_end(key);return nodes[index+1:]
        del cache[key]
    queue=deque([entity.location]);prev={entity.location:None}
    while queue:
        here=queue.popleft()
        if here==target:
            nodes=[]
            while here is not None:nodes.append(here);here=prev[here]
            nodes=tuple(reversed(nodes))
            # All these entries share one tuple; no quadratic list copies.
            for index,room in enumerate(nodes[:-1]):
                cache[(entity.group_id,room,target)]=(nodes,index)
            while len(cache)>4096:cache.popitem(last=False)
            return nodes[1:]
        for di,dest in world.rooms[here].exits.items():
            if dest in prev or dest not in world.rooms or frontiers.blocked(world,here,di,entity):continue
            if not safe_room(dest):continue
            prev[dest]=here;queue.append(dest)
    return None



def _on_duty(world,entity):
    """One current work gate even when the optional economy is disabled."""
    from engine import livelihoods,life_stages
    if not entity.alive or entity.progress.get('retired') or not life_stages.for_entity(world,entity)['can_work']:return False
    start,duration=livelihoods.hours(world,entity)
    return (living.state(world)['minute']-start)%worldtime.MINUTES_PER_DAY<duration


def _adult_routine(world,entity,profile):
    """Residents without a shift still have a waking day, not invented jobs."""
    from engine import livelihoods
    clock=living.state(world)['minute']%worldtime.MINUTES_PER_DAY
    definition=livelihoods.definition(world,entity)
    work=definition.get('work_room')
    working=bool(work and _on_duty(world,entity))
    target=profile['home_room'];activity='sleeping at home' if clock<420 or clock>=1260 else 'at home'
    if working:target=work;activity='working'
    elif 1020<=clock<1260 and profile.get('leisure_rooms'):target=profile['leisure_rooms'][0];activity='leisure'
    path=_safe_path(world,entity,target)
    if path is None and target!=profile['home_room']:
        target=profile['home_room'];path=_safe_path(world,entity,target);activity='at home; destination unavailable'
    if path:world.move_entity(entity.id,path[0])
    if path is None:activity='waiting safely; route unavailable'
    elif entity.location!=target:activity='travelling to '+activity
    entity.activity=activity
    if work and target==work and entity.location==work and activity=='working' and livelihoods.enabled(world):
        # Reuse only stationary, finite interactions. Delegating general work
        # routines could choose an unsafe shortcut or autonomous supply trip.
        for item in list(entity.inventory):livelihoods.receive(world,entity,item)
        if definition.get('occupation') in ('teacher','entertainer'):livelihoods.work_activity(world,entity)
    return True


def routine(world,entity):
    """Protect dependents and preserve enrolled adults' authored waking schedules."""
    if entity.is_player or not entity.alive:return False
    profile=entity.progress.get('population')
    if not enabled(world) and not (profile and profile.get('born_resident')):return False
    if not profile:return False
    from engine import life_stages
    stage=life_stages.for_entity(world,entity)
    _life_update(world,entity,stage)
    from engine import livelihoods
    if livelihoods.roused(world,entity) and not livelihoods.scheduled_awake(world,entity):
        entity.activity='awake after being disturbed'
        return True
    if stage['adult']:
        if profile.get('care_role')!='home_caregiver':return _adult_routine(world,entity,profile)
        house=state(world)['households'].get(profile['household_id'],{})
        children=[world.entities.get(i) for i in house.get('members',[])]
        needs_home_care=any(c and c.alive and not life_stages.for_entity(world,c)['adult'] and not life_stages.for_entity(world,c)['in_school'] for c in children)
        if not needs_home_care:return _adult_routine(world,entity,profile)
        path=_safe_path(world,entity,profile['home_room'])
        if path:world.move_entity(entity.id,path[0])
        clock=living.state(world)['minute']%worldtime.MINUTES_PER_DAY
        entity.activity=('sleeping at home; care available' if clock<420 or clock>=1260 else 'household caregiving') if entity.location==profile['home_room'] else 'returning for household care' if path is not None else 'caregiving route blocked'
        return True
    _care(world,entity)
    home=profile['home_room'];clock=living.state(world)['minute']%worldtime.MINUTES_PER_DAY
    education=profile['education'];target=home
    activity='sleeping at home' if clock<420 or clock>=1260 else 'guardian-led home learning'
    # Infants and preschool children never walk unaccompanied between rooms.
    if stage['stage']=='infant' or not stage['in_school']:
        entity.activity=('sleeping with household care' if clock<420 or clock>=1260 else 'resting with household care') if profile['supervision_available'] else 'awaiting household care'
        profile['care_provision_unavailable']=not profile['supervision_available']
        return True
    if profile['care_need']:
        activity='awaiting household care'
    elif 480<=clock<840 and education.get('enrollment') in ('school','community'):
        classroom=education.get('learning_room')
        staff=[world.entities.get(i) for i in education.get('provider_ids',[])]
        available=any(p and p.location==classroom and _on_duty(world,p) for p in staff)
        if available and _safe_path(world,entity,classroom) is not None:
            target=classroom;activity='learning at '+education['enrollment']
        else:activity='home learning; teaching or route unavailable'
        profile['teaching_unavailable']=not available or target!=classroom
    elif 900<=clock<1170 and profile.get('leisure_rooms'):
        options=[r for r in profile['leisure_rooms'] if _safe_path(world,entity,r) is not None]
        if options:target=options[0];activity='leisure'
    path=_safe_path(world,entity,target)
    if path:world.move_entity(entity.id,path[0])
    if path is None:
        activity='waiting safely; route unavailable'
        profile['route_blocked']=True
    else:
        profile.pop('route_blocked',None)
        if entity.location!=target:activity='travelling to '+('home' if target==home else 'learning' if target==education.get('learning_room') else 'leisure')
    entity.activity=activity
    return True


def local_view(world,entity,viewer=None):
    """Read-only local inspection. No enrollment, health sampling or mutation."""
    profile=entity.progress.get('population')
    if not profile:return None
    from engine import life_stages
    stage=life_stages.for_entity(world,entity)
    house=getattr(world,'living_state',{}).get('population',{}).get('households',{}).get(profile['household_id'],{})
    # Counts and roles are visible locally; remote family identities are not.
    assigned_guardian=any(member and member.alive and entity.id in member.progress.get('population',{}).get('guardian_ids',[]) and not life_stages.for_entity(world,member)['adult'] for member in (world.entities.get(i) for i in house.get('members',[])))
    result=dict(enrolled=True,household_type=house.get('type',''),household_role='dependent' if not stage['adult'] else 'guardian' if assigned_guardian else 'adult_member',guardian_count=len(profile.get('guardian_ids',[])),parent_count=len(profile.get('biological_parent_ids',[])),marital_status=profile.get('marital_status'),partnership_status=profile.get('partnership_status'),care_need=profile.get('care_need',False),care_provision_unavailable=profile.get('care_provision_unavailable',False),education=deepcopy(profile.get('education',{})),health=deepcopy(entity.progress.get('population_health')),appearance=deepcopy(profile.get('appearance',{})),life_stage=stage['stage'],age_years=stage['age_years'],adult=stage['adult'])
    result['education'].pop('provider_ids',None);result['education'].pop('provider_source_ids',None);result['education'].pop('school_provider_ids',None);result['education'].pop('school_provider_source_ids',None)
    if viewer is not None:
        ids=profile.get('guardian_ids',[])+profile.get('biological_parent_ids',[])+([profile['current_partner_id']] if profile.get('current_partner_id') else [])
        result['nearby_family_names']=[world.entities[i].name for i in dict.fromkeys(ids) if i in world.entities and world.entities[i].alive and world.entities[i].location==viewer.location]
    return result
