"""Shared targeting, permissions, ammunition and combat resolution."""
from collections import Counter
from engine import living,society

def target(w,actor,query,players=True):
    query=query.strip().casefold()
    rows=[e for e in w.entities_in_room(actor.location) if e.id!=actor.id and (players or not e.is_player)]
    if not query:
        npcs=[e for e in rows if not e.is_player]
        if len(npcs)==1:return npcs[0]
        if not npcs:raise ValueError('Nothing here to attack.')
        raise ValueError('Choose a target by name or click its Attack button.')
    exact=[e for e in rows if query==e.id.casefold()]
    if not exact:exact=[e for e in rows if query==e.name.casefold()]
    if not exact:exact=[e for e in rows if not e.is_player and query in e.name.casefold()]
    if len(exact)>1:raise ValueError('More than one target matches. Choose the intended person using their Attack button.')
    if not exact:raise ValueError('No living target matching '+query+' is here.')
    return exact[0]

def validate(w,actor,victim,controller=None,*,check_starter=True,check_controller_restraint=True):
    from engine import regional_world
    regional_world.validate_combat(w,actor,victim)
    owner=controller or actor
    if owner is not actor:
        regional_world.validate_combat(w,owner,victim)
        from engine import spell_life
        reason=spell_life.control_restriction(w,owner)
        if reason and (check_controller_restraint or getattr(w,'living_state',{}).get('city_justice_v1',{}).get('cases',{}).get(owner.id,{}).get('status') in ('awaiting_hearing','sentenced')):
            raise ValueError(reason)
    if not actor.alive or not owner.alive or not victim.alive:raise ValueError('Combat requires living participants.')
    if actor.location!=victim.location or owner.location!=actor.location:raise ValueError('The target is no longer here.')
    if victim.id in (actor.id,owner.id) or victim.progress.get('companion_owner')==owner.id:raise ValueError('You cannot attack yourself or your own companion.')
    from engine import starter_safety
    if check_starter and starter_safety.blocked(w,actor,victim):
        raise ValueError('This character is protected from unprovoked NPC attacks in their starting area.')
    # Owned creatures have the same PvP protections as their caregiver, including offline caregivers.
    protected=victim.is_player or bool(victim.progress.get('companion_owner'))
    if protected and owner.is_player:
        if not w.metadata.get('pvp',True):raise ValueError('Player combat is disabled in this world, including attacks on owned companions.')
        if living.details(w,actor.location).get('truce'):raise ValueError('Player combat is forbidden in this sanctuary, including attacks on owned companions.')

def ammunition(w,e,consume=True):
    if not society.enabled(w):return {}
    required=Counter()
    for iid in e.equipped.values():
        item=w.items.get(iid,{})
        if item.get('type')=='weapon' and society.durability(e,iid)<=0:raise ValueError('Your '+item.get('name',iid)+' is broken. Repair or unequip it before attacking.')
        ammo=item.get('requires_ammo')
        if ammo:required[ammo]+=1
    missing=[w.items.get(i,{}).get('name',i) for i,n in required.items() if e.inventory.count(i)<n]
    if missing:raise ValueError('Missing ammunition: '+', '.join(missing)+'. Buy or craft ammunition, or equip another weapon.')
    if consume:living.consume(e,required)
    return dict(required)

def npc_attack(w,actor,victim,*,counter=False):
    """Commit a selected autonomous attack after target and ammunition checks.

    Starter protection reports an actual attempted assault through strike(),
    without spending ammunition or applying a hit. Ordinary validation remains
    a side-effect-free preflight; invalid targets and empty weapons never alarm.
    """
    if actor.is_player or actor.progress.get('companion_owner'):
        raise ValueError('An autonomous attack requires an unowned NPC.')
    validate(w,actor,victim,check_starter=False)
    from engine import npc_spellcasting
    spell=npc_spellcasting.try_cast(w,actor,victim,counter=counter)
    if spell is not None:return spell
    ammunition(w,actor,consume=False)
    from engine import starter_safety
    if not starter_safety.blocked(w,actor,victim):
        ammunition(w,actor)
    return strike(w,actor,victim,counter=counter)

def finish(w,dead,killer,credit=None):
    from engine import commands as cmd,mortality
    from engine import spell_life
    if spell_life.magical(dead):
        spell_life.retire(w,dead.id)
        return dead.name+' dies; the temporary magical body fades.'
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.death(w,dead,'combat',killer)
    if dead.is_player:
        mortality.record_death(w,dead,'combat',killer)
        return dead.name+' dies.'
    if dead.progress.get('_combat_death_resolved'):return ''
    dead.progress['_combat_death_resolved']=True
    from engine import combat_rewards
    loot=combat_rewards.settle(w,dead,killer,credit)
    from engine import encounter_stories
    encounter_stories.defeated(w,dead,killer)
    if dead.source_def and not dead.spawner_key:w.killed_npcs.add(dead.source_def)
    room=w.rooms[dead.location]
    mode=cmd._corpse_mode_for(w,dead)
    if mode=='disappear':cmd._remove_entity(w,room,dead.id)
    elif mode=='timed':
        import time
        dead.corpse_expires_at=time.monotonic()+cmd._corpse_ttl(w,dead)
    messages=cmd._on_npc_death(w,room,dead)
    return ' '.join([dead.name+' dies.'+loot]+messages)

def strike(w,actor,victim,power=None,ignore_defense=False,credit=None,counter=True,lawful=False,wear=True):
    from engine import commands as cmd,mortality
    from engine import regional_world,combat_rewards
    regional_world.validate_combat(w,actor,victim)
    from engine import starter_safety
    if not actor.alive or not victim.alive or actor.location!=victim.location:
        raise ValueError('Combat requires living participants in the same place.')
    starter_safety.provoke(w,actor,victim,credit=credit,lawful=lawful)
    if starter_safety.blocked(w,actor,victim):
        from engine import city_defense
        city_defense.note_attempt(w,actor,victim)
        return starter_safety.prevented(w,actor,victim)
    from engine import npc_attention
    npc_attention.begin(w,actor,victim)
    controller=credit or actor
    if society.enabled(w) and not lawful:mortality.assault(w,controller,victim)
    before=victim.hp
    from engine import task_skills
    if power is None:
        task_skills.practice(w,actor,'fighting',difficulty=task_skills.level(w,victim,'fighting'),effort=1)
    task_skills.practice(w,victim,'fighting',difficulty=task_skills.level(w,actor,'fighting'),effort=1)
    hit=victim.take_damage(cmd.effective_attack(w,actor) if power is None else power,0 if ignore_defense else cmd.effective_defense(w,victim),source=actor,cause='attack',kind='combat')
    combat_rewards.contribute(w,actor,victim,before-victim.hp,credit)
    from engine import encounter_stories
    encounter_stories.hit(w,actor,victim,before-victim.hp)
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[actor.id,victim.id],f'{actor.name} struck {victim.name} for {hit} damage.')
    from engine import ability_rules, fighting_pose
    fighting_pose.mark(actor,projectile=power is None and any(w.items.get(i,{}).get('requires_ammo') for i in actor.equipped.values()))
    fighting_pose.mark(victim,defending=True)
    if power is None:ability_rules.consume_hit(actor,'ability_focus_v1')
    ability_rules.consume_hit(victim,'ability_exposed_v1')
    if wear and society.enabled(w):society.wear(actor)
    text=('You' if actor.is_player else actor.name)+' hit'+('' if actor.is_player else 's')+' '+victim.name+' for '+str(hit)+' damage.'
    if victim.is_player:
        w.dirty_players=getattr(w,'dirty_players',set())|{victim.id}
        living.on_hit(w,victim,actor,hit)
    if not victim.alive:return text+' '+finish(w,victim,actor,controller)
    if not actor.alive:return text+' '+actor.name+' was defeated by a defending companion.'
    if counter:
        try:ammunition(w,victim)
        except ValueError as exc:return text+' '+victim.name+' cannot counterattack: '+str(exc)
        fighting_pose.mark(victim,projectile=any(w.items.get(i,{}).get('requires_ammo') for i in victim.equipped.values()))
        before=actor.hp
        task_skills.practice(w,victim,'fighting',difficulty=task_skills.level(w,actor,'fighting'),effort=1)
        task_skills.practice(w,actor,'fighting',difficulty=task_skills.level(w,victim,'fighting'),effort=1)
        damage=actor.take_damage(cmd.effective_attack(w,victim),cmd.effective_defense(w,actor),source=victim,cause='counterattack',kind='combat')
        combat_rewards.contribute(w,victim,actor,before-actor.hp)
        encounter_stories.hit(w,victim,actor,before-actor.hp)
        ability_rules.consume_hit(victim,'ability_focus_v1')
        ability_rules.consume_hit(actor,'ability_exposed_v1')
        if getattr(w,'living_state',{}).get('resident_watches'):
            from engine import resident_watch
            resident_watch.note(w,[actor.id,victim.id],f'{victim.name} countered {actor.name} for {damage} damage.')
        if actor.is_player:living.on_hit(w,actor,victim,damage)
        text+=' '+victim.name+' hits '+('you' if actor.is_player else actor.name)+' for '+str(damage)+' damage.'
        if not actor.alive:text+=' '+finish(w,actor,victim)
    return text

def starter_ammunition(w,p):
    if not society.enabled(w) or p.progress.get('starter_ammo_v1'):return
    equipment=w.classes.get(p.char_class,{}).get('starting_equipment',[])
    for ammo in {w.items.get(i,{}).get('requires_ammo') for i in equipment if i in p.inventory} - {None,''}:
        if ammo in w.items and not p.inventory.count(ammo):p.inventory.extend([ammo]*12)
    p.progress['starter_ammo_v1']=True
