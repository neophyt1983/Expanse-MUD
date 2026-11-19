"""Host-resolved Burgling versus Observation; no inventory mutation here.

Call ``attempt`` only after validating a real local transfer and its finite
quantity. Its result is private runtime state, never a wire packet. After the
successful transfer commits (or a valid failed attempt finishes), call
``complete`` once to report detected acts and award bounded practice.

Initial game-balance rules, not measured real-world probabilities:
* Success: clamp(5%, 95%, 65% + (Burgling - difficulty) / 100 - stack noise).
* Each observer: clamp(5%, 95%, 35% + (Observation - Burgling) / 100
  + difficulty / 500 + 15% on failure + 10% for the owner + stack noise).
* Stack noise: one percentage point per requested unit after the first,
  capped at fifteen points. It affects success and detection independently.
* Successful haul: min(requested, 1 + floor((Burgling + 10 * quality) / 10)),
  with quality in [0, 1). Skill zero can take at most one unit. For a fixed
  roll, increasing Burgling cannot reduce either success or quantity.
"""
from dataclasses import dataclass, field
from math import floor, prod
import random

from engine import relationships, sleep_movement, worldtime


DISPLAY_NAME = 'Burgling'
SKILLS = frozenset(('burglary', 'observation'))
ATTEMPT_KEY = 'burglary_attempt_v1'
PRACTICE_KEY = 'theft_practice_v1'
MAX_QUANTITY = 1_000_000


def _level(value, default=0):
    return max(0, min(100, value)) if type(value) is int else default


def skill(world, actor, name='burglary'):
    """Task skill, never a character's general advancement level."""
    if name not in SKILLS:
        raise ValueError('Choose Burgling or Observation.')
    definitions = world.classes if actor.is_player else world.npcs
    key = actor.char_class if actor.is_player else actor.source_def
    default = _level(definitions.get(key, {}).get(name, 0))
    saved = actor.progress.get('skills', {})
    return _level(saved.get(name, default), default) if isinstance(saved, dict) else default


def difficulty(row):
    return _level(row.get('theft_difficulty', 25), 25)


def _quantity(quantity):
    if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
        raise ValueError('Choose a whole quantity from 1 to '+str(MAX_QUANTITY)+'.')
    return quantity


def _minute(world):
    saved = getattr(world, 'living_state', {}) or {}
    return int(saved['minute'] if 'minute' in saved else worldtime.initial_minute(world.metadata))


def _clamp(value):
    return max(.05, min(.95, value))


def _noise(quantity):
    return min(.15, .01 * (quantity - 1))


def _permitted(world, actor, row, target_actor):
    if target_actor is not None:
        return target_actor is actor
    from engine import locks
    return locks.permitted(world, actor, row)


def _owner(observer, row, target_actor):
    if target_actor is not None:
        return observer is target_actor
    return bool(observer.source_def and observer.source_def == row.get('owner'))


def _observers(world, actor, online_players=()):
    online = set(online_players)
    if actor.location not in world.rooms:
        return []
    eligible = {}
    for observer in world.entities_in_room(actor.location):
        if (observer.id == actor.id or observer.location != actor.location or not observer.alive
                or observer.is_player and observer.id not in online
                or not relationships.sentient(world, observer)
                or sleep_movement.asleep(world, observer)):
            continue
        eligible[observer.id] = observer
    return [eligible[ident] for ident in sorted(eligible)]


def _success(level, target_difficulty, quantity):
    return _clamp(.65 + (level - target_difficulty) / 100 - _noise(quantity))


def _detection(world, observer, level, row, quantity, success, target_actor):
    return _clamp(.35 + (skill(world, observer, 'observation') - level) / 100
                  + difficulty(row) / 500 + (.15 if not success else 0)
                  + (.10 if _owner(observer, row, target_actor) else 0) + _noise(quantity))


def chances(world, actor, row, quantity=1, *, target_actor=None, online_players=()):
    """Read-only UI summary; never expose observers' IDs or private skills."""
    _quantity(quantity)
    level = skill(world, actor)
    target_difficulty = difficulty(row)
    permitted = _permitted(world, actor, row, target_actor)
    observers = _observers(world, actor, online_players)
    success = 1.0 if permitted else _success(level, target_difficulty, quantity)
    risks = []
    for outcome in (True, False):
        risks.append(1 - prod(1 - _detection(world, person, level, row, quantity, outcome, target_actor)
                              for person in observers))
    risk = 0 if permitted else success * risks[0] + (1 - success) * risks[1]
    saved = actor.progress.get(ATTEMPT_KEY, {})
    ready = saved.get('next_minute', 0) if isinstance(saved, dict) else 0
    cooldown = max(0, ready - _minute(world)) if type(ready) is int and not permitted else 0
    return dict(skill_name=DISPLAY_NAME, level=level, difficulty=target_difficulty,
                success_chance=round(success, 6), permitted=permitted,
                observer_count=len(observers),
                detection_risk='none' if not risk else 'low' if risk < .25 else 'moderate' if risk < .65 else 'high',
                cooldown_remaining=cooldown)


@dataclass
class Attempt:
    success: bool
    quantity: int
    detected: list
    player_observers: list
    permitted: bool
    level: int
    difficulty: int
    minute: int
    target_key: str
    source: dict
    victim_id: str
    observing: list = field(default_factory=list, repr=False)
    completed: bool = False
    feedback: str = ''
    _reported: bool = field(default=False, repr=False)
    _world: object = field(default=None, repr=False)
    _actor: object = field(default=None, repr=False)


def attempt(world, actor, origin, row, quantity=1, rng=None, *, target_actor=None, online_players=()):
    """Resolve one validated local attempt; no loot, evidence or learning yet.

    Random order is success, quality on success, then one detection roll per
    eligible observer in ID order. Permitted transfers consume none of these.
    A rejected cooldown consumes no random draw and changes no state.
    """
    _quantity(quantity)
    if actor is None or not actor.alive or sleep_movement.asleep(world, actor):
        raise ValueError('You must be awake and able to act.')
    if origin != actor.location or origin not in world.rooms:
        raise ValueError('Visit the target before attempting to steal.')
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
        raise ValueError('Choose a real theft target.')
    if row.get('direction'):
        raise ValueError('A door has no contents. Use lockpicking for its lock.')
    if target_actor is not None and (target_actor is actor or not target_actor.alive
            or world.entities.get(target_actor.id) is not target_actor or target_actor.location != origin):
        raise ValueError('Choose a different living person here.')
    if target_actor is not None and target_actor.is_player and target_actor.id not in set(online_players):
        raise ValueError('That person is not available here.')
    now = _minute(world)
    restrained = actor.progress.get('restrained_until', 0)
    if type(restrained) is int and restrained > now:
        raise ValueError('You are restrained and cannot attempt a theft yet.')
    permitted = _permitted(world, actor, row, target_actor)
    level = skill(world, actor)
    target_difficulty = difficulty(row)
    source = dict(kind='inventory' if target_actor is not None else 'container',
                  id=target_actor.id if target_actor is not None else row['id'],
                  name=target_actor.name+'’s belongings' if target_actor is not None else row.get('name', row['id']))
    victim = target_actor.id if target_actor is not None else row.get('owner') or row['id']
    target_key = 'actor:'+target_actor.id if target_actor is not None else 'container:'+origin+':'+row['id']
    if permitted:
        return Attempt(True, quantity, [], [], True, level, target_difficulty, now, target_key,
                       source, victim, _world=world, _actor=actor)
    previous = actor.progress.get(ATTEMPT_KEY, {})
    ready = previous.get('next_minute', 0) if isinstance(previous, dict) else 0
    if type(ready) is int and now < ready:
        raise ValueError('Wait '+str(ready-now)+' game minute(s) before another theft attempt.')
    draw = rng if rng is not None else random.random
    success = draw() < _success(level, target_difficulty, quantity)
    taken = min(quantity, 1 + floor((level + 10 * draw()) / 10)) if success else 0
    observers = _observers(world, actor, online_players)
    noticed = [person for person in observers
               if draw() < _detection(world, person, level, row, quantity, success, target_actor)]
    count = previous.get('count', 0) if isinstance(previous, dict) else 0
    actor.progress[ATTEMPT_KEY] = {'next_minute': now+1, 'count': (count if type(count) is int else 0)+1}
    if actor.is_player:
        world.dirty_players = getattr(world, 'dirty_players', set()) | {actor.id}
    source.update(action='take' if success else 'tamper', quantity=taken)
    return Attempt(success, taken, [person for person in noticed if not person.is_player],
                   [person for person in noticed if person.is_player], False, level, target_difficulty,
                   now, target_key, source, victim, observing=observers, _world=world, _actor=actor)


def _validate_result(world, actor, result):
    if not isinstance(result, Attempt) or result._world is not world or result._actor is not actor:
        raise ValueError('This theft result does not belong to the current actor and world.')


def report_result(world, actor, result):
    """Report only actual detectors after the caller commits the attempt."""
    _validate_result(world, actor, result)
    if result._reported or result.permitted:
        return result.feedback
    result._reported = True
    crime = 'theft' if result.success else 'lock tampering'
    from engine import regional_world, mortality
    if result.detected:
        if regional_world.enabled(world):
            mortality.report_crime(world, actor, crime, result.victim_id, result.detected, source=result.source)
        speaker = next((person for person in result.detected if person.id == result.victim_id
                        or person.source_def == result.victim_id), result.detected[0])
        words = ('Stop! Taking from '+result.source['name']+' is theft!' if result.success else
                 'Stop tampering with '+result.source['name']+'!')
        from engine import speech_bubbles
        speech_bubbles.mark(speaker, actor, 'angry', None, ('shouts', words, ''))
        public = speaker.name+' shouts at '+actor.name+', “'+words+'”'
        style = {'role': 'npc', 'emphasis': 'shout'}
        notice = (actor.location, public, actor.id if actor.is_player else None, style)
        world.runtime_notifications = (getattr(world, 'runtime_notifications', [])+[notice])[-500:]
        if actor.is_player:
            personal = speaker.name+' shouts at you, “'+words+'”'
            world.rest_notifications = (getattr(world, 'rest_notifications', [])+[(actor.id, personal, style)])[-500:]
        result.feedback = speaker.name+' notices the '+('theft.' if result.success else 'attempt.')
    for observer in result.player_observers:
        text = (actor.name+' steal '+str(result.quantity)+' item(s) from '+result.source['name']+'.'
                if result.success else actor.name+' attempt to steal from '+result.source['name']+' but take nothing.')
        regional_world.notice(world, observer, 'You notice '+text)
    if result.player_observers and not result.feedback:
        result.feedback = 'Your attempt was noticed.'
    return result.feedback


def _practice(world, actor, name, token, ceiling, minute, effort=2):
    from engine import task_skills
    return task_skills.practice(world, actor, name, difficulty=max(0,ceiling-10), effort=effort,
                                event_id='theft:'+name+':'+token+':'+str(minute)) > 0


def complete(world, actor, result):
    """Finalize after a committed transfer or a finished valid failed attempt.

    Calling this twice cannot repeat reports, dialogue or skill gains. A caller
    whose transfer did not commit must not complete a successful result.
    """
    _validate_result(world, actor, result)
    if result.completed:
        return result.feedback
    result.completed = True
    if result.permitted:
        return ''
    report_result(world, actor, result)
    from engine import npc_emotions
    npc_emotions.theft_observed(world, actor, result)
    if _practice(world, actor, 'burglary', result.target_key,
                                                         result.difficulty+10, result.minute):
        gain='Your '+DISPLAY_NAME+' improves to '+str(skill(world, actor))+'.'
        result.feedback = (result.feedback+' '+gain).strip()
    detected={person.id for person in result.detected + result.player_observers}
    for observer in result.observing:
        _practice(world, observer, 'observation', actor.id+'|'+result.target_key,
                  result.level+10, result.minute,effort=2 if observer.id in detected else .5)
    return result.feedback
