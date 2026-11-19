"""Finite artistic work and local commissions with recorded provenance.

Art quality and taste are authored game-balance rules, not objective judgments
about art or real psychology. A commissioned plan never constructs a building.
All materials, work time, carried objects and patron payment are real state.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import random
import shlex
import uuid

from engine import guilds, knowledge, living, npc_emotions, relationships, sleep_movement, task_skills

KEY = 'artworks_v1'
KINDS = ('poetry', 'painting', 'sculpture', 'architecture')
MAX_WORKS = 10000


def _state(world, create=False):
    state = living.state(world) if create else getattr(world, 'living_state', {})
    if create:
        return state.setdefault(KEY, {'version': 1, 'serial': 0, 'works': {}, 'jobs': {}, 'commissions': {}, 'judgments': {}})
    return state.get(KEY, {})


def _dirty(world, *actors):
    ids = {actor.id for actor in actors if actor.is_player}
    if ids:world.dirty_players = getattr(world, 'dirty_players', set()) | ids


def _text(value, maximum, label):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + ' must contain 1–' + str(maximum) + ' characters.')
    return value.strip()


def _recipe(world, ident):
    row = getattr(world, 'recipes', {}).get(ident, {})
    return row if isinstance(row.get('artwork'), dict) and row['artwork'].get('kind') in KINDS else None


def _known_recipes(world, actor):
    """Use the canonical pure personal-knowledge view, without sync."""
    return knowledge.known_ids(world, actor, 'recipes')


def _begin_reason(world, actor, recipe):
    reason = guilds._actor_reason(world, actor)
    if reason:return reason
    if actor.id in _state(world).get('jobs', {}):return 'Finish or cancel your current artistic work first.'
    if recipe is None or recipe['id'] not in _known_recipes(world, actor):
        return 'Read an actual local source or learn this artistic plan first.'
    if not knowledge.recipe_source_ready(actor, recipe):
        return 'Read this plan’s required source before beginning the work.'
    from engine import gathering
    missing = gathering.prerequisite(world, actor, recipe)
    if missing:return missing
    tool = recipe.get('tool')
    if tool and tool not in actor.inventory:
        return 'Bring ' + world.items.get(tool, {}).get('name', tool) + '.'
    if len(_state(world).get('works', {})) >= MAX_WORKS:return 'This world’s retained artwork capacity is full.'
    from engine import ecology, geology_impacts, quest_progress, resting
    if resting.active(actor):return 'Stop resting before beginning an artistic project.'
    from engine import employment
    if employment.active(world, actor):return 'Finish or pause the actual employment batch first.'
    if actor.progress.get('guild_work_v1', {}).get('operation'):
        return 'Finish the actual guild task already in progress first.'
    if geology_impacts.room_unusable(world, actor.location):return 'This station is currently unusable.'
    if any(ability not in actor.abilities for ability in recipe.get('required_abilities', [])):
        return 'Learn the required artistic technique first.'
    if any(quest_progress.status(world, actor, ident) != 'complete' for ident in recipe.get('prerequisites', [])):
        return 'Complete this plan’s actual prerequisite work first.'
    if not ecology.available(world, actor.location, recipe):
        return 'The required living resources are not actually available here.'
    station = recipe.get('station', 'hand')
    if station != 'hand' and station not in world.room_details.get(actor.location, {}).get('facilities', []):
        return 'Work at a real ' + station + ' station.'
    cfg = recipe['artwork']
    if task_skills.level(world, actor, cfg['kind']) < cfg.get('min_skill', 0):
        return cfg['kind'].title() + ' ' + str(cfg['min_skill']) + ' is required.'
    building = cfg.get('building')
    if building:
        rooms = getattr(world, 'buildings', {}).get(building, {}).get('rooms', [])
        if not rooms or any(room not in actor.explored_rooms for room in rooms):
            return 'Visit every actual room of the named building before preparing its architectural plan.'
    counts = Counter(actor.inventory)
    counts.subtract(actor.equipped.values())
    if any(counts[item] < count for item, count in recipe.get('ingredients', {}).items()):
        return 'Carry the required unequipped materials; artistic work cannot proceed without supplies.'
    return ''


def begin(world, actor, recipe_id, *, title=None, text=None):
    recipe = _recipe(world, recipe_id)
    reason = _begin_reason(world, actor, recipe)
    if reason:raise ValueError(reason)
    cfg = recipe['artwork']
    title = _text(title if title is not None else cfg.get('title', recipe['name']), 100, 'Title')
    if text is not None:
        if cfg['kind'] != 'poetry':raise ValueError('Written verse is available for poetry projects.')
        text = _text(text, 4000, 'Verse')
    materials = list(actor.inventory)
    for item, count in recipe['ingredients'].items():
        for _ in range(count):materials.remove(item)
    saved = _state(world, True)
    saved['serial'] += 1
    ident = 'artwork_' + str(saved['serial'])
    if ident in world.items:raise ValueError('Artwork identity conflicts with authored content.')
    actor.inventory[:] = materials
    token = uuid.uuid4().hex
    saved['jobs'][actor.id] = dict(id=ident, recipe=recipe_id, specification=deepcopy(recipe),
        title=title, text=text, room=actor.location, started=guilds.minute(world),
        last_minute=guilds.minute(world), remaining=recipe.get('minutes', 10),
        skill=task_skills.level(world, actor, cfg['kind']), token=token)
    actor._artwork_token = token
    actor.activity = 'working on ' + title
    _dirty(world, actor)
    return ('Started ' + title + '. Materials used; ' + str(recipe.get('minutes', 10)) +
            ' game minutes of awake work at this station are required. Use art finish when ready.')


def advance(world, minutes):
    """Count only actual active work at the authored place; no offline catch-up."""
    if type(minutes) not in (int, float) or minutes <= 0:return
    if getattr(world, 'realtime', False) and not getattr(world, 'tick_authorized', False):return
    now = guilds.minute(world)
    for actor_id, job in list(_state(world).get('jobs', {}).items()):
        if now <= job['last_minute']:continue
        elapsed = min(minutes, now - job['last_minute'])
        job['last_minute'] = now
        actor = world.entities.get(actor_id)
        from engine import resting, employment
        if (actor is None or not actor.alive or actor.location != job['room'] or
                sleep_movement.asleep(world, actor) or guilds._actor_reason(world, actor)):
            continue
        if actor.is_player and (getattr(actor, '_artwork_token', None) != job.get('token') or
                (hasattr(world, 'online_player_ids') and actor.id not in world.online_player_ids)):
            interrupt(world, actor, 'the work session ended; offline time does not count')
            continue
        if (resting.active(actor) or employment.active(world, actor) or job.get('paused') or
                actor.progress.get('guild_work_v1', {}).get('operation')):
            continue
        job['remaining'] = max(0, job['remaining'] - elapsed)
        _dirty(world, actor)


def _finish_reason(world, actor):
    reason = guilds._actor_reason(world, actor)
    if reason:return reason
    job = _state(world).get('jobs', {}).get(actor.id)
    if job is None:return 'You have no artistic work in progress.'
    if actor.location != job['room']:return 'Return to the actual work station to finish this piece.'
    if job.get('paused'):return 'Resume your paused artistic work before finishing it.'
    if actor.is_player and getattr(actor, '_artwork_token', None) != job.get('token'):
        return 'Resume this artistic work explicitly; a saved or detached session does not count as working.'
    if job['remaining'] > 0:return str(job['remaining']) + ' game minutes of active work remain.'
    return ''


def finish(world, actor, *, rng=None):
    reason = _finish_reason(world, actor)
    if reason:raise ValueError(reason)
    saved = _state(world, True);job = saved['jobs'][actor.id]
    recipe = job['specification'];cfg = recipe['artwork'];rng = rng or random
    # Fixed-roll higher skill can never yield lower quality.
    quality = round(max(0, min(100, 15 + .75 * job['skill'] + 20 * rng.random() - .25 * cfg.get('difficulty', 20))))
    creator = dict(id=actor.id, source=actor.source_def, name=actor.name, kind='player' if actor.is_player else 'npc')
    provenance = dict(version=1, kind=cfg['kind'], style=cfg['style'], creator=creator,
        attribution='recorded', created_minute=guilds.minute(world), created_room=job['room'],
        recipe=job['recipe'], quality=quality, building=cfg.get('building'), serial=int(job['id'].split('_')[-1]))
    description = cfg.get('description', recipe.get('description', 'An individually made artistic work.'))
    record = dict(id=job['id'], name=job['title'], description=description, type='artwork',
                  value=0, artwork=provenance, creation_method='Made through a recorded finite artistic project.')
    if cfg['kind'] == 'poetry':
        record['type'] = 'book'
        record['read_text'] = job['text'] or cfg.get('text', description)
        provenance['composition'] = 'original_text' if job['text'] else 'study_after_authored_form'
        record['publication'] = dict(kind='poetry', genre='poetry', author=actor.name,
            work_id=record['id'], edition_id=record['id'] + ':original',
            original_minute=provenance['created_minute'], edition_minute=provenance['created_minute'],
            evidence_roots=[record['id']], claims=[])
    saved['works'][record['id']] = deepcopy(record)
    world.items[record['id']] = record
    actor.inventory.append(record['id'])
    del saved['jobs'][actor.id]
    actor._artwork_token = None
    task_skills.practice(world, actor, cfg['kind'], difficulty=cfg.get('difficulty', 20),
                         effort=max(1, recipe.get('minutes', 10) / 5), event_id=record['id'])
    _dirty(world, actor)
    return 'Finished ' + record['name'] + ' [' + record['id'] + ']. One physical work is now in your inventory.'


def cancel(world, actor):
    reason = guilds._actor_reason(world, actor)
    if reason:raise ValueError(reason)
    job = _state(world).get('jobs', {}).get(actor.id)
    if job is None:raise ValueError('You have no artistic work in progress.')
    del _state(world, True)['jobs'][actor.id]
    actor._artwork_token = None
    _dirty(world, actor)
    return 'Cancelled ' + job['title'] + '. Materials already used are not restored.'


def active(world, actor):
    return _state(world).get('jobs', {}).get(actor.id)


def interrupt(world, actor, reason):
    job = active(world, actor)
    if not job or job.get('paused'):return False
    job['paused'] = str(reason)[:160]
    _dirty(world, actor)
    return True


def resume(world, actor):
    reason = guilds._actor_reason(world, actor)
    if reason:raise ValueError(reason)
    job = active(world, actor)
    if not job:raise ValueError('You have no artistic work in progress.')
    from engine import resting, employment
    if resting.active(actor):raise ValueError('Stop resting before resuming artistic work.')
    if employment.active(world, actor):raise ValueError('Finish or pause the actual employment batch first.')
    if actor.progress.get('guild_work_v1', {}).get('operation'):
        raise ValueError('Finish the actual guild task already in progress first.')
    if actor.location != job['room']:raise ValueError('Return to the actual work station before resuming.')
    job.pop('paused', None);job['last_minute'] = guilds.minute(world)
    job['token'] = uuid.uuid4().hex;actor._artwork_token = job['token']
    actor.activity = 'working on ' + job['title'];_dirty(world, actor)
    return 'Resumed ' + job['title'] + '.'


def provenance(world, item_id):
    record = world.items.get(item_id, {});info = record.get('artwork')
    if not isinstance(info, dict):return None
    result = deepcopy(info)
    creator = result.get('creator', {})
    actual = world.entities.get(creator.get('id'))
    if actual and (not creator.get('source') or actual.source_def == creator['source']):
        status = 'living' if actual.alive else 'dead'
    elif creator.get('source') in getattr(world, 'killed_npcs', set()):
        status = 'dead'
    else:status = creator.get('status', 'unknown')
    result['creator_status'] = status
    result['attribution_label'] = ('Created by ' if info.get('attribution') == 'recorded' else
        'Attributed to ' if info.get('attribution') == 'attributed' else 'Creator uncertain: ') + creator.get('name', 'unknown')
    return result


def _patron(world, actor, patron_id):
    reason = guilds._actor_reason(world, actor)
    if reason:return None, reason
    patron = world.entities.get(patron_id)
    if (patron is None or patron.is_player or patron is actor or not patron.alive or
            patron.location != actor.location or not relationships.sentient(world, patron) or sleep_movement.asleep(world, patron)):
        return None, 'Speak with the actual awake patron here.'
    from engine import frontiers
    if frontiers.hostile(world, patron, actor):return None, 'This patron is not willing to commission your work.'
    return patron, ''


def _offer(world, patron, ident):
    rows = world.npcs.get(patron.source_def, {}).get('art_commissions', [])
    return next((row for row in rows if row['id'] == ident and row.get('enabled', True)), None)


def _key(patron, offer):
    return patron.source_def + ':' + offer['id']


def _revision(world, patron, offer):
    row = _state(world).get('commissions', {}).get(_key(patron, offer), {})
    value = [offer, patron.id, patron.gold, row]
    return int.from_bytes(sha256(json.dumps(value, sort_keys=True).encode()).digest()[:6], 'big')


def _commission_reason(world, actor, patron, offer, action, work_id=None):
    row = _state(world).get('commissions', {}).get(_key(patron, offer), {})
    if row.get('status') == 'complete':return 'This commission is already fulfilled; time does not create another order.'
    if action == 'accept':
        if row.get('status') == 'accepted':return 'This commission has already been accepted.'
        if patron.gold < offer['price']:return 'This patron cannot currently fund the stated payment.'
        if offer['recipe'] not in _known_recipes(world, actor):
            return 'Learn the actual artistic plan before accepting this commission.'
        return ''
    if row.get('status') != 'accepted' or row.get('actor') != actor.id or row.get('patron') != patron.id:
        return 'Only the actual maker who accepted this patron’s commission can complete or decline it.'
    if action == 'decline':return ''
    if row.get('terms') != offer:return 'The commission changed. Decline it and read the new offer.'
    if patron.gold < offer['price']:return 'This patron cannot currently fund the stated payment.'
    item = world.items.get(work_id, {});art = item.get('artwork', {})
    if work_id not in actor.inventory or work_id in actor.equipped.values() or not art:
        return 'Carry the actual unequipped artwork you intend to deliver.'
    if art.get('creator', {}).get('id') != actor.id or art.get('attribution') != 'recorded':
        return 'This commission requires your own recorded work.'
    if art.get('recipe') != offer['recipe']:return 'This work does not match the commissioned plan.'
    if art.get('created_minute', -1) < row['accepted'] or art.get('serial', -1) <= row.get('after_serial', -1):
        return 'Create this commissioned work after accepting the request.'
    if art.get('quality', 0) < offer.get('min_quality', 0):return 'This work does not meet the patron’s stated craft standard.'
    return ''


def _judge(world, patron, actor, work_id):
    saved = _state(world, True);key = patron.id + ':' + work_id
    if key in saved['judgments']:return saved['judgments'][key]
    art = world.items[work_id]['artwork']
    tastes = world.npcs.get(patron.source_def, {}).get('art_taste', {})
    preference = tastes.get('styles', {}).get(art['style'], 0) + tastes.get('kinds', {}).get(art['kind'], 0)
    expression = npc_emotions.project(world, patron, partner=actor, topic='work')
    emotions = {row['id']: row['intensity'] for row in expression['emotions']}
    mood = .12 * emotions.get('happy', 0) + .08 * emotions.get('curious', 0) - .12 * emotions.get('angry', 0) - .1 * emotions.get('tired', 0)
    history = patron.progress.get(npc_emotions.KEY, {}).get('associations', {}).get('performance', {})
    experience = .08 * history.get('positive', 0) - .08 * history.get('negative', 0)
    score = round(max(0, min(100, art['quality'] + preference + mood + experience)))
    result = dict(score=score, minute=guilds.minute(world), opinion=True,
                  explanation='A personal judgment shaped by this patron’s taste, current feelings and remembered artistic experiences.')
    saved['judgments'][key] = result
    return result


def act(world, actor, patron_id, offer_id, action, *, work_id=None, expected_revision=None):
    if action not in ('accept', 'deliver', 'decline'):raise ValueError('Choose accept, deliver or decline.')
    patron, reason = _patron(world, actor, patron_id)
    if reason:raise ValueError(reason)
    offer = _offer(world, patron, offer_id)
    if offer is None:raise ValueError('That patron does not offer this commission.')
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision != _revision(world, patron, offer)):
        raise ValueError('The commission or patron’s available payment changed. Refresh the offer.')
    reason = _commission_reason(world, actor, patron, offer, action, work_id)
    if reason:raise ValueError(reason)
    saved = _state(world, True);key = _key(patron, offer)
    if action == 'accept':
        saved['commissions'][key] = dict(status='accepted', actor=actor.id, patron=patron.id,
                                         accepted=guilds.minute(world), after_serial=saved['serial'], terms=deepcopy(offer))
        _dirty(world, actor)
        return 'Accepted ' + offer['name'] + '. Make the actual work and return to this patron; payment requires acceptance and available funds.'
    if action == 'decline':
        saved['commissions'][key] = dict(status='declined', previous_actor=actor.id)
        _dirty(world, actor)
        return 'Declined the unfilled commission. No goods or payment changed hands.'
    judgment = _judge(world, patron, actor, work_id)
    if judgment['score'] < offer.get('min_appreciation', 0):
        npc_emotions.record(world, actor, 'performance rejected', source=patron.id,
                            event_id='art-rejected:' + patron.id + ':' + work_id)
        return (patron.name + ' declines this piece (personal appreciation ' + str(judgment['score']) + '/100). '
                'You keep your work. ' + judgment['explanation'])
    actor.inventory.remove(work_id);patron.inventory.append(work_id)
    patron.gold -= offer['price'];actor.gold += offer['price']
    saved['commissions'][key].update(status='complete', work=work_id, completed=guilds.minute(world), payment=offer['price'])
    task_skills.transaction(world, actor, patron)
    npc_emotions.record(world, actor, 'performance welcomed', source=patron.id,
                        event_id='art-accepted:' + patron.id + ':' + work_id)
    _dirty(world, actor, patron)
    return (patron.name + ' accepts ' + world.items[work_id]['name'] + ' and pays ' + str(offer['price']) +
            ' gold (personal appreciation ' + str(judgment['score']) + '/100). ' + judgment['explanation'])


def projection(world, actor):
    result = dict(room=actor.location, projects=[], job=None, works=[], commissions=[])
    for ident in sorted(_known_recipes(world, actor)):
        row = _recipe(world, ident)
        if row is None:continue
        reason = _begin_reason(world, actor, row)
        result['projects'].append(dict(id=ident, name=row['name'], kind=row['artwork']['kind'],
            style=row['artwork']['style'], minutes=row.get('minutes', 10),
            skill=task_skills.level(world, actor, row['artwork']['kind']),
            materials=[dict(id=item, name=world.items[item].get('name', item), required=count,
                carried=actor.inventory.count(item) - list(actor.equipped.values()).count(item)) for item, count in row['ingredients'].items()],
            enabled=not reason, reason=reason))
    job = _state(world).get('jobs', {}).get(actor.id)
    if job:
        reason = _finish_reason(world, actor)
        result['job'] = dict(id=job['id'], title=job['title'], remaining=job['remaining'], room=job['room'],
                             ready=not reason, reason=reason, paused=job.get('paused', ''))
    for ident in dict.fromkeys(actor.inventory):
        info = provenance(world, ident)
        if info:result['works'].append(dict(id=ident, name=world.items[ident]['name'], **info))
    for patron in world.entities_in_room(actor.location):
        if _patron(world, actor, patron.id)[1]:continue
        for offer in world.npcs.get(patron.source_def, {}).get('art_commissions', []):
            if not offer.get('enabled', True):continue
            state = _state(world).get('commissions', {}).get(_key(patron, offer), {})
            reason = _commission_reason(world, actor, patron, offer, 'accept')
            deliveries = []
            for work in result['works']:
                blocked = _commission_reason(world, actor, patron, offer, 'deliver', work['id'])
                deliveries.append(dict(item=work['id'], enabled=not blocked, reason=blocked))
            result['commissions'].append(dict(id=offer['id'], name=offer['name'], patron_id=patron.id,
                patron_name=patron.name, recipe=offer['recipe'], price=offer['price'],
                min_quality=offer.get('min_quality', 0), min_appreciation=offer.get('min_appreciation', 0),
                revision=_revision(world, patron, offer), status=state.get('status', 'available'),
                claimed_by_self=state.get('actor') == actor.id,
                accept=dict(enabled=not reason, reason=reason), deliveries=deliveries))
    return result


def restore(world):
    """Restore retained dynamic definitions before floor/inventory filtering."""
    saved = _state(world)
    for ident, item in list(saved.get('works', {}).items())[:MAX_WORKS]:
        if (isinstance(ident, str) and ident.startswith('artwork_') and isinstance(item, dict)
                and item.get('id') == ident and isinstance(item.get('artwork'), dict)):
            world.items.setdefault(ident, deepcopy(item))


def command(ctx, args):
    try:parts = shlex.split(args)
    except ValueError as exc:raise ValueError('Close the quotes around artistic IDs and titles.') from exc
    world, actor = ctx.world, ctx.player
    if not parts:
        ctx.time_accounted = True
        view = projection(world, actor)
        return ('Artistic work: ' + ', '.join(row['name'] for row in view['projects']) +
                '\nLocal commissions: ' + ', '.join(row['name'] for row in view['commissions']))
    action = parts[0]
    if action == 'begin' and 2 <= len(parts) <= 3:
        return begin(world, actor, parts[1], title=parts[2] if len(parts) == 3 else None)
    if action == 'finish' and len(parts) == 1:return finish(world, actor)
    if action == 'cancel' and len(parts) == 1:return cancel(world, actor)
    if action == 'resume' and len(parts) == 1:return resume(world, actor)
    if action in ('accept', 'decline', 'deliver'):
        count = 4 if action == 'deliver' else 3
        if len(parts) in (count, count + 1):
            try:revision = int(parts[-1]) if len(parts) == count + 1 else None
            except ValueError as exc:raise ValueError('Use the current numeric commission revision.') from exc
            return act(world, actor, parts[1], parts[2], action, work_id=parts[3] if action == 'deliver' else None,
                       expected_revision=revision)
    raise ValueError('Use art begin "plan", art finish, art cancel, or art accept|deliver|decline "patron" "offer" ["work"] [revision].')


def register(registry):
    from engine.commands import Command
    registry.register(Command('art', 'Make physical artistic works and fulfil finite commissions',
                              'art [begin|finish|cancel|accept|deliver|decline]', command, example='art'))


def validate(data):
    from engine.artwork_rules import validate as check
    return check(data)
