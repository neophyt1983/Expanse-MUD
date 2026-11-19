"""Read-only local service offers and authenticated, revalidated UI actions."""
import hashlib
import json
import shlex

from engine import artworks, clinical_services, employment, resting, sleep_movement


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def _build(world, actor):
    """Return public cards plus a private command lookup, without starting work."""
    result = dict(room=actor.location, cards=[])
    choices = {}

    def card(ident, title, lines=()):
        row = dict(id=ident, title=title, lines=list(lines), entries=[])
        result['cards'].append(row)
        return row

    def entry(parent, ident, title, lines=()):
        row = dict(id=ident, title=title, lines=list(lines), actions=[])
        parent['entries'].append(row)
        return row

    def action(parent, service, verb, label, command, quote, *, keys=(), enabled=True, reason=''):
        ident = _hash([service, verb, *keys])[:24]
        revision = int(_hash([quote, bool(enabled), reason, command])[:12], 16)
        offer = dict(id=ident, service=service, action=verb, label=label,
                     revision=revision, enabled=bool(enabled), reason=reason)
        parent['actions'].append(offer)
        choices[ident] = (offer, command)

    jobs = employment.view(world, actor)
    if jobs['vacancies'] or jobs['assignment']:
        section = card('employment', 'Paid work', [
            'Apply for an open job, then start a real batch. Wages are paid when the work finishes.',
            'Leaving, sleeping, injury or disconnection stops an unfinished batch and returns its reserved supplies and wage.'])
        assignment = jobs['assignment']
        if assignment:
            batch = assignment['batch']
            terms=next((offer for offer in jobs['vacancies'] if offer['id']==assignment['vacancy_id']),None)
            lines = ['Employer: ' + assignment['employer']]
            if batch:
                lines.append(str(round(batch['remaining'], 2)) + ' game minutes remaining · ' + str(batch['wage']) + ' gold on completion')
            elif terms:
                lines.append('Next batch: '+terms['recipe']+' · '+str(terms['minutes'])+' game minutes · '+str(terms['wage'])+' gold on completion')
                lines.extend(material['name']+': '+str(material['quantity'])+' needed, '+str(material['available'])+' in workplace stock'
                             for material in terms['materials'])
            if assignment.get('message'):lines.append(assignment['message'])
            row = entry(section, 'assignment', assignment['title'], lines)
            action(row, 'employment', 'work', 'Start paid work', 'job work', [assignment,terms],
                   enabled=assignment['can_work'], reason=assignment['blocked'])
            if batch:action(row, 'employment', 'stop', 'Stop this batch', 'job stop', assignment)
            action(row, 'employment', 'leave', 'Leave this job', 'job leave', assignment)
        for vacancy in jobs['vacancies']:
            lines = [vacancy['employer'] + ' · ' + str(vacancy['open_slots']) + '/' + str(vacancy['slots']) + ' places open',
                     vacancy['recipe'] + ' · ' + str(vacancy['minutes']) + ' game minutes · ' + str(vacancy['wage']) + ' gold per finished batch']
            lines.extend(material['name'] + ': ' + str(material['quantity']) + ' needed, ' +
                         str(material['available']) + ' in workplace stock' for material in vacancy['materials'])
            lines.extend('Makes ' + str(output['quantity']) + ' × ' + output['name'] +
                         ' for the shop' for output in vacancy['outputs'])
            row = entry(section, vacancy['id'], vacancy['title'], lines)
            action(row, 'employment', 'apply', 'Apply for this job', shlex.join(['job', 'apply', vacancy['id']]),
                   vacancy, keys=[vacancy['id']], enabled=vacancy['can_apply'], reason=vacancy['blocked'])

    care = clinical_services.projection(world, actor)
    if care:
        section = card('clinic', 'Medical care', ['Treatment uses this clinic’s supplies and a qualified professional who is present.'])
        lines = ['Treatment fee: ' + str(care['fee']) + ' gold']
        if care['practitioner']:lines.append('Practitioner: ' + care['practitioner'])
        row = entry(section, 'treatment', care['name'], lines)
        action(row, 'clinical', 'treatment', 'Request treatment', 'service treatment', care,
               enabled=care['enabled'], reason=care['reason'])

    art = artworks.projection(world, actor)
    if any(art[key] for key in ('projects', 'job', 'works', 'commissions')):
        section = card('art', 'Art and commissions', ['Make a physical work from known plans and actual materials. A patron’s appreciation is a personal opinion.'])
        job = art['job']
        if job:
            lines = [str(round(job['remaining'], 2)) + ' game minutes remaining']
            if job['paused']:lines.append('Paused: ' + job['paused'])
            row = entry(section, 'current-work', job['title'], lines)
            action(row, 'art', 'finish', 'Finish this work', 'art finish', job,
                   enabled=job['ready'], reason=job['reason'])
            if job['paused']:
                reason = ('Return to the work station before resuming.' if actor.location != job['room'] else
                          'Stop resting before resuming.' if resting.active(actor) else
                          'Finish or stop your paid batch first.' if employment.active(world, actor) else
                          'Finish the guild task already in progress.' if actor.progress.get('guild_work_v1', {}).get('operation') else '')
                action(row, 'art', 'resume', 'Resume this work', 'art resume', job, enabled=not reason, reason=reason)
            action(row, 'art', 'cancel', 'Cancel · used materials are lost', 'art cancel', job)
        for project in art['projects']:
            lines = [project['kind'].title() + ' · ' + project['style'] + ' · ' + str(project['minutes']) +
                     ' game minutes · skill ' + str(project['skill']) + '/100']
            lines.extend(material['name'] + ': ' + str(material['required']) + ' needed, ' +
                         str(material['carried']) + ' carried' for material in project['materials'])
            row = entry(section, 'plan:' + project['id'], project['name'], lines)
            action(row, 'art', 'begin', 'Begin this work', shlex.join(['art', 'begin', project['id']]),
                   project, keys=[project['id']], enabled=project['enabled'], reason=project['reason'])
        for work in art['works']:
            lines = [work.get('attribution_label', 'Creator unknown') + ' · ' + work.get('creator_status', 'unknown'),
                     'Quality ' + str(work.get('quality', 'unknown')) + '/100 · ' + work.get('style', 'unrecorded style')]
            if work.get('created_minute') is not None:lines.append('Recorded creation: world minute ' + str(work['created_minute']))
            elif work.get('date_label'):lines.append(work['date_label'])
            entry(section, 'work:' + work['id'], work['name'], lines)
        names = {work['id']: work['name'] for work in art['works']}
        for commission in art['commissions']:
            lines = [commission['patron_name'] + ' · ' + commission['status'],
                     str(commission['price']) + ' gold if accepted · minimum quality ' + str(commission['min_quality']) +
                     '/100 · minimum personal appreciation ' + str(commission['min_appreciation']) + '/100']
            row = entry(section, 'commission:' + commission['patron_id'] + ':' + commission['id'], commission['name'], lines)
            keys = [commission['patron_id'], commission['id']]
            words = ['art', 'accept', *keys, str(commission['revision'])]
            action(row, 'art', 'accept', 'Accept this commission', shlex.join(words), commission,
                   keys=keys, **commission['accept'])
            if commission['claimed_by_self'] and commission['status'] == 'accepted':
                action(row, 'art', 'decline', 'Release this commission',
                       shlex.join(['art', 'decline', *keys, str(commission['revision'])]), commission, keys=keys)
            for delivery in commission['deliveries']:
                action(row, 'art', 'deliver', 'Offer ' + names.get(delivery['item'], delivery['item']),
                       shlex.join(['art', 'deliver', *keys, delivery['item'], str(commission['revision'])]),
                       [commission, delivery], keys=[*keys, delivery['item']],
                       enabled=delivery['enabled'], reason=delivery['reason'])
    return result, choices


def projection(world, actor):
    return _build(world, actor)[0]


def resolve(world, actor, packet):
    if not isinstance(packet, dict):raise ValueError('Choose a current local work or care action.')
    if (actor is None or not actor.is_player or world.entities.get(actor.id) is not actor
            or not actor.alive or sleep_movement.asleep(world, actor)):
        raise ValueError('Choose a living, awake player character first.')
    if packet.get('actor_id') != actor.id:raise ValueError('The selected character changed. Refresh local services.')
    if packet.get('room') != actor.location:raise ValueError('You moved. Read the services at your current location.')
    if packet.get('command') != 'work action' or packet.get('work_ui') is not True:
        raise ValueError('Unknown local service action.')
    request = packet.get('request_id')
    if not isinstance(request, str) or not request.strip() or len(request) > 100:
        raise ValueError('Refresh local services to create a valid request.')
    if set(packet) - {'command', 'work_ui', 'service', 'action', 'sequence', 'request_id',
                      'actor_id', 'room', 'offer_id', 'revision'}:
        raise ValueError('Choose a current offer. The host determines its materials, price and outcome.')
    _, choices = _build(world, actor)
    choice = choices.get(packet.get('offer_id')) if isinstance(packet.get('offer_id'), str) else None
    if choice is None:raise ValueError('That offer is no longer available. Refresh local services.')
    offer, command = choice
    if (packet.get('service'), packet.get('action')) != (offer['service'], offer['action']):
        raise ValueError('Choose the action shown by the current offer.')
    supplied = packet.get('revision')
    if type(supplied) is not int or not 0 <= supplied < 2**48 or supplied != offer['revision']:
        raise ValueError('This offer changed. Read its current terms before choosing again.')
    if not offer['enabled']:raise ValueError(offer['reason'] or 'That action is unavailable now.')
    return command
