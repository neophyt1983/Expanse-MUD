"""Public editions drawn exclusively from witnessed in-world events."""
from engine import worldtime

def editions(w):
    return (w.metadata or {}).get('press_editions',[])

def local(w,rid):
    if rid not in w.rooms:return None
    rows=editions(w);group=w.rooms[rid].group
    detail=getattr(w,'room_details',{}).get(rid,{})
    authored=detail.get('press_locality')
    for r in rows:
        if r.get('kind')!='country' and (r.get('name')==authored or r.get('home')==rid or
                    any(rid.startswith(p) for p in r.get('prefixes',[]))):return r
    return next((r for r in rows if r.get('kind')=='country' and r.get('group')==group),None)

# Lower numbers lead the front page and are retained first in a full archive.
PRIORITY = {'Public safety': 0, 'Watch': 1, 'Civic works': 2, 'Harbour': 3,
            'Culture': 4, 'Education': 4, 'Commerce': 4, 'Community': 5, 'Trade': 7}


def priority(article):
    if article.get('topic') == 'business' or legacy_notice(article):
        return 6
    return PRIORITY.get(article['section'], 4)


def legacy_notice(article):
    return article['section'] == 'Community' and article['headline'].endswith(' became business.')


def record(w, rid, section, headline, *, byline=None, key=None, topic=None, once=False, minute=None):
    if not editions(w):
        return
    place = local(w, rid)
    state = getattr(w, 'living_state', None)
    if not place or not isinstance(state, dict):
        return
    now = int(state.get('minute', 375))
    if minute is None:
        minute = now
    day = minute // worldtime.MINUTES_PER_DAY
    oldest_day = now // worldtime.MINUTES_PER_DAY - 8
    if day < oldest_day:
        return
    archive = state.setdefault('press_archive_v1', {})
    for bucket in list(archive):
        if int(bucket) < oldest_day:
            del archive[bucket]
    edition = archive.setdefault(str(day), {}).setdefault(place['name'], [])
    key = key or headline
    for article in edition:
        if article['key'] == key:
            if not once:
                article['count'] += 1
                article['last'] = max(article['last'], minute)
            return
    entry = dict(key=key, section=section, headline=headline, room=w.rooms[rid].name,
                 minute=minute, last=minute, count=1, byline=byline or 'Local correspondent', topic=topic)
    if len(edition) >= 96:
        oldest = max(range(len(edition)), key=lambda i: (priority(edition[i]), -edition[i]['last']))
        if priority(edition[oldest]) < priority(entry):
            return
        edition.pop(oldest)
    edition.append(entry)


def geological_dispatch(w, event):
    if not editions(w):
        return
    from engine import relationships
    names = {'quake': 'an earthquake', 'flood': 'flooding', 'eruption': 'an eruption', 'tsunami': 'a tsunami'}
    reported = set()
    for rid in event['rooms']:
        area = local(w, rid)
        if not area or area['name'] in reported:
            continue
        if not any(relationships.sentient(w, e) for e in w.entities_in_room(rid)):
            continue
        reported.add(area['name'])
        headline = f"Witnesses at {w.rooms[rid].name} reported {names[event['type']]}."
        record(w, rid, 'Public safety', headline, key='geology:' + event['id'], once=True,
               byline='Local correspondent', minute=event['started_minute'])


def edition_stories(area, articles, detailed):
    notices, trades = [], []
    for article in articles:
        if legacy_notice(article):
            name = article['headline'].removesuffix(' became business.')
            article = {**article, 'headline': name + ' became business partners.', 'topic': 'business'}
        if article['section']=='Trade' and ':hatchery_prepare_fish:' in article.get('key','') and ' completed 1 × ' in article['headline']:
            article={**article,'headline':article['headline'].split(' completed 1 × ',1)[0]+' prepared one portion of river fish.'}
        elif article['section'] == 'Trade' and ' completed 1 × ' in article['headline']:
            worker,goods=article['headline'].split(' completed 1 × ',1)
            label=goods.removesuffix('.')
            if label=='Eggs':headline=worker+' collected one egg.'
            else:headline=worker+' finished work on '+goods
            article={**article,'headline':headline}
        if detailed:
            yield area, article
        elif article.get('topic') == 'business':
            notices.append(article)
        elif article['section'] == 'Trade':
            trades.append(article)
        else:
            yield area, article
    for group in (notices, trades):
        if not group:
            continue
        latest = max(group, key=lambda item: (item['last'], item['key']))
        count = sum(item['count'] for item in group)
        if len(group) == 1 and (group is trades or count == 1):
            yield area, latest
            continue
        if group is trades:
            sites = len({row['room'] for row in trades})
            label = 'workplace' if sites == 1 else 'workplaces'
            headline = f'Crafters at {sites} {label} in {area} finished {count} batches of goods. Latest from the workshops: '
        else:
            headline = f'{count} business partnerships reported in {area}. Latest notice: '
        yield area, {**latest, 'headline': headline + latest['headline'], 'count': 1, 'room': area}


def traffic_headline(w, article):
    """Credit an old traffic report only if a retained incident identifies the actor."""
    headline = article['headline']
    prefix = 'A traffic collision at '+article['room']+' '
    if article['section'] != 'Public safety' or not headline.startswith(prefix):
        return headline
    outcome, _, name = headline[len(prefix):].removesuffix('.').partition(' ')
    if outcome not in ('injured', 'killed') or not name:
        return headline
    history = (getattr(w,'living_state',{}) or {}).get('mortality', {})
    def actor_name(key):
        actor = w.entities.get(key)
        return actor.name if actor else history.get('deaths',{}).get(key,{}).get('name')
    matches = []
    for event in history.get('incidents', []):
        if event.get('kind') != 'traffic' or event.get('minute') != article['last']:
            continue
        room = w.rooms.get(event.get('room'))
        if room and room.name == article['room'] and actor_name(event.get('victim')) == name:
            matches.append(actor_name(event.get('actor')))
    if len(matches) == 1 and matches[0]:
        return headline+' The traffic report identifies '+matches[0]+'.'
    return headline


def browse(w,player,query='',*,dispatches=None,venues=None):
    rows=editions(w)
    if not rows:return 'No newspaper publishes in this world.'
    if query.strip().casefold()=='editions':
        return '\n'.join(k.title()+': '+', '.join(sorted(r['name'] for r in rows if r['kind']==k)) for k in ('country','city','town') if any(r['kind']==k for r in rows))
    day=int((getattr(w,'living_state',{}) or {}).get('minute',375))//1500
    words = query.split()
    detailed = bool(words and words[-1].casefold() == '/all')
    if detailed:
        words.pop()
    name = ' '.join(words)
    if name.lower().endswith(' yesterday') or name.lower()=='yesterday':day-=1;name=name[:-9].strip()
    selected=next((r for r in rows if r['name'].casefold()==name.casefold()),None) if name else local(w,player.location)
    if not selected:return 'Choose an edition by its printed name with news editions.'
    archive=(getattr(w,'living_state',{}) or {}).get('press_archive_v1',{}).get(str(day),{})
    allowed={selected['name']}
    if selected['kind']=='country':allowed.update(r['name'] for r in rows if r['group']==selected['group'])
    date=worldtime.date(max(0,day)*1500)
    lines=[selected['name']+' Gazette',f'Year {date["year"]}, month {date["month"]}, day {date["day"]} · '+selected['kind'].title()+' edition']
    if day<0:return '\n'.join(lines[:1]+['There is no earlier edition.'])
    from engine import civic_program
    lines.extend(civic_program.paper(w,allowed,day,venues))
    stories=[row for area in allowed for row in edition_stories(area, archive.get(area, []), detailed)]
    if not stories:lines.append('No local dispatches have been filed for this date.')
    shown = {}
    omitted = 0
    for area,a in sorted(stories,key=lambda row:(0 if detailed else priority(row[1]),-row[1]['last'],row[0],row[1]['key'])):
        section = a['section']
        if not detailed and shown.get(section, 0) >= 3:
            omitted += 1
            continue
        shown[section] = shown.get(section, 0) + 1
        if dispatches is not None:
            from hashlib import sha256
            key=sha256(repr((day, area, section, a['key'], a['last'], a['count'])).encode()).hexdigest()[:20]
            dispatches[key]={'area':area,'headline':traffic_headline(w,a),'section':section}
        hour,minute=divmod(a['last']%1500,60)
        times=' ('+str(a['count'])+' batches)' if a['count']>1 and a['section']=='Trade' else ''
        lines.append(f'{hour:02}:{minute:02} · {area} · '+a['section']+'\n'+traffic_headline(w,a)+times+'\n'+a['room']+' — '+a['byline'])
    if omitted:
        lines.append(f'{omitted} more reports inside.')
    lines.append('Read all dispatches with news /all. Use news editions to list papers, or news <place> yesterday for an earlier edition.')
    return '\n\n'.join(lines)
